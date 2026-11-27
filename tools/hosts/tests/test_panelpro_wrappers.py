"""The PanelPro wrappers (jmri/layouts/hart/scripts/run_*.sh) and their shared run lifecycle
(tools/hosts/panelpro_session.sh), run against a fake StartJMRI.

Every run uses a copy of the wrappers in a temporary checkout, a temporary HOME holding a fixture
profile, and a PATH of plain tools only (no MQTT client), so nothing reaches the live profile,
~/JMRI_UserFiles, the repo's tables or a broker. HART_GUARD_JMRI_RUNNING=0 (hartlib's override)
hides any real JMRI or CATS on this machine from the "already running" check.

The cleanup tests (stops, signals, SIGKILL and restore) are in test_panelpro_wrappers_cleanup.py (split for size,
2026-11-26), which imports the sandbox from here.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = "jmri/layouts/hart/scripts"
WRAPPERS = ("run_panelpro_smoke_test.sh", "run_panelpro_stage1.sh", "run_panelpro_traininfo_repair.sh",
            "run_sml_discover.sh", "run_nx_discover.sh", "run_ctc_logic_smoke.sh")
PUBLISHING = ("panel_status.py", "signal_coordinator.py", "sts_car_sync.py", "jmri_cmd_watcher.py",
              "mimic_relay.py", "brand_new_publisher.py", "WebServerAction")
LIVE_ID = "My_JMRI_Railroad.3ef75bfd"
TOOLS = ("bash", "cp", "mv", "rm", "mkdir", "mktemp", "ps", "sleep", "awk", "sed", "head", "tail", "cat",
         "dirname", "basename", "id", "env", "grep", "chmod", "date", "cut", "cmp", "ls", "tr", "wc", "pgrep",
         "rmdir")

PROFILE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<auxiliary-configuration xmlns="http://www.netbeans.org/ns/auxiliary-configuration/1">
    <startup xmlns="http://jmri.org/xml/schema/auxiliary-configuration/startup-4-3-5.xsd">
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformFileModelXml" enabled="yes" name="preference:tables.xml" type="XmlFile"/>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" enabled="yes" name="preference:jython/panel_status.py" type="ScriptFile"/>
        <perform name="preference:jython/sts_car_sync.py" type="ScriptFile" enabled="yes" class="jmri.util.startup.configurexml.PerformScriptModelXml"/>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" enabled="yes" name="preference:jython/signal_coordinator.py" type="ScriptFile"/>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" enabled="yes" name="preference:jython/jmri_cmd_watcher.py" type="ScriptFile"/>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" enabled="yes" name="preference:jython/mimic_relay.py" type="ScriptFile"/>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" enabled="yes" name="preference:jython/hide_cats_desk_windows.py" type="ScriptFile"/>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" enabled="yes" name="preference:jython/brand_new_publisher.py" type="ScriptFile"/>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformActionModelXml" enabled="yes" name="jmri.web.server.WebServerAction" type="Action"/>
        <perform xmlns="" class="jmri.util.startup.configurexml.PerformActionModelXml" enabled="yes" name="apps.SystemConsoleAction" type="Action"/>
    </startup>
</auxiliary-configuration>
"""

TABLES = """\
<layout-config>
  <layoutblocks class="jmri.jmrit.display.layoutEditor.configurexml.LayoutBlockManagerXml" blockrouting="yes">
  </layoutblocks>
</layout-config>
"""

# Stands in for PanelPro.app/Contents/MacOS/StartJMRI. It saves the profile as JMRI would read it
# and its environment, then either quits without a marker (FAKE_MODE=exit) or starts a "java"
# that sleeps (FAKE_MODE=hang; FAKE_IGNORE_TERM=1 makes it ignore SIGTERM) and waits on it
# (FAKE_MODE=detach: quits a second after java started, leaving java running).
# FAKE_MARKER_FROM names the variable holding the marker path: it writes an ok marker first, and
# FAKE_MODE=marker then quits cleanly as JMRI does after the script's System.exit.
FAKE_STARTJMRI = """\
#!/bin/bash
cp "$FAKE_PROFILE_XML" "$FAKE_STATE/profile_at_launch.xml"
env > "$FAKE_STATE/env"
[[ -n "${HART_TRAININFO_DIR:-}" ]] && ls "$HART_TRAININFO_DIR" > "$FAKE_STATE/traininfo_at_launch"
echo "$2" > "$FAKE_STATE/launch_arg"
if [[ -n "${FAKE_MARKER_FROM:-}" ]]; then
  printf 'ok\nfake detail\n' > "${!FAKE_MARKER_FROM}"
fi
[[ "$FAKE_MODE" == marker ]] && exit 0
if [[ "$FAKE_MODE" == hang || "$FAKE_MODE" == detach ]]; then
  python3 -c '
import os, signal, sys, time
if sys.argv[2] == "1":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
open(sys.argv[1] + ".tmp", "w").write(str(os.getpid()))
os.rename(sys.argv[1] + ".tmp", sys.argv[1])
time.sleep(600)
' "$FAKE_STATE/java.pid" "${FAKE_IGNORE_TERM:-0}" "-Dorg.jmri.profile=$2" &
  if [[ "$FAKE_MODE" == detach ]]; then
    while [[ ! -f "$FAKE_STATE/java.pid" ]]; do sleep 0.1; done
    sleep 1          # the wrapper's wait finds java as this launcher's child, then the launcher is gone
    exit 0
  fi
  wait
fi
exit 3
"""


class Sandbox:
    """A checkout copy, HOME, fake JMRI install and PATH for one test."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.root = tmp / "checkout"
        for rel in [f"{SCRIPTS}/{w}" for w in WRAPPERS] + [
                "tools/hosts/profile_tables_guard.sh", "tools/hosts/panelpro_session.sh",
                "tools/hosts/pi/jmri_profile_match.sh",
                "tools/hosts/panelpro_profile.py", "cats/scripts/patch_jmri_startup.py"]:
            dest = self.root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, dest)
        shutil.copytree(ROOT / "tools/hartlib/src", self.root / "tools/hartlib/src",
                        ignore=shutil.ignore_patterns("__pycache__"))
        (self.root / "jmri/layouts/hart/output").mkdir(parents=True)
        (self.root / "jmri/layouts/hart/output/tables.xml").write_text(TABLES, encoding="utf-8")
        traininfo = self.root / "jmri/layouts/hart/dispatcher/traininfo"
        traininfo.mkdir(parents=True)
        (traininfo / "train1.xml").write_text("<traininfo/>", encoding="utf-8")
        # build_tables.py stands in for the generator (run_sml_discover.sh): it logs its arguments
        stub = self.root / "tools/schematic/build_tables.py"
        stub.parent.mkdir(parents=True)
        stub.write_text("import os, sys\nopen(sys.argv[0] + '.log', 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
                        "sys.exit(2 if os.environ.get('FAKE_TABLES_FAIL') and sys.argv[1] == '--discovered-from' "
                        "else 0)\n", encoding="utf-8")
        stub.write_text(stub.read_text(encoding="utf-8").replace(
            "sys.exit(2 if", "print('ab' * 32) if sys.argv[1] == '--base-hash' else None\nsys.exit(2 if"), encoding="utf-8")
        # check_approved.py stands in for the approval check (run_sml_discover.sh): it logs its arguments and passes
        # unless FAKE_UNAPPROVED is set
        approved = self.root / "tools/schematic/check_approved.py"
        approved.write_text("import os, sys\nopen(sys.argv[0] + '.log', 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
                            "sys.exit(1 if os.environ.get('FAKE_UNAPPROVED') else 0)\n", encoding="utf-8")
        (self.root / "jmri/layouts/hart/data/schematic").mkdir(parents=True)
        self.home = tmp / "home"
        self.profile = self.make_profile(self.home / "Library/Preferences/JMRI", "My_JMRI_Railroad", LIVE_ID,
                                         r"home\:JMRI_UserFiles/")
        self.original = self.profile.read_bytes()
        jmri = tmp / "jmri/PanelPro.app/Contents/MacOS"
        jmri.mkdir(parents=True)
        (jmri / "StartJMRI").write_text(FAKE_STARTJMRI, encoding="utf-8")
        (jmri / "StartJMRI").chmod(0o755)
        self.bin = tmp / "bin"
        self.bin.mkdir()
        for tool in TOOLS:
            found = shutil.which(tool)
            if found:
                (self.bin / tool).symlink_to("/bin/bash" if tool == "bash" else found)
        (self.bin / "python3").symlink_to(sys.executable)
        self.state = tmp / "state"
        self.state.mkdir()

    @staticmethod
    def make_profile(base: Path, name: str, pid: str, user_files: str) -> Path:
        folder = base / f"{name}.jmri" / "profile"
        folder.mkdir(parents=True)
        (folder / "profile.properties").write_text(
            f"#fixture\nprofile.name={name}\nprofile.id={pid}\njmri-implementation.user-files={user_files}\n",
            encoding="utf-8")
        (folder / "profile.xml").write_text(PROFILE_XML, encoding="utf-8")
        return folder / "profile.xml"

    def env(self, profile: Path | None = None, **extra: str) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("JMRI_", "HART_", "FAKE_")) and k not in ("JAVA_HOME", "PATH", "HOME")}
        env.update(HOME=str(self.home), PATH=str(self.bin), JMRI_HOME=str(self.tmp / "jmri"),
                   JAVA_HOME="/nonexistent-java", FAKE_STATE=str(self.state), FAKE_MODE="exit",
                   FAKE_PROFILE_XML=str(profile or self.profile), HART_PANELPRO_KILL_WAIT="3",
                   HART_PANELPRO_POLL="0.1", HART_GUARD_JMRI_RUNNING="0")
        for name, marker in (("SMOKE", "HART_PANELPRO_SMOKE"), ("STAGE1", "HART_STAGE1"),
                             ("TRAININFO", "HART_TRAININFO"), ("SML", "HART_SML_DISCOVER"),
                             ("NX", "HART_NX_DISCOVER"), ("CTC", "HART_CTC_LOGIC_SMOKE")):
            env[f"{marker}_MARKER"] = str(self.state / f"{name}.done")
            env[f"{marker}_LOG"] = str(self.state / f"{name}.log")
        env.update(extra)
        return env

    def cmd(self, wrapper: str) -> list[str]:
        return ["/bin/bash", str(self.root / SCRIPTS / wrapper)]

    def run(self, wrapper: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(self.cmd(wrapper), env=env, capture_output=True, text=True, timeout=90,
                              cwd=self.tmp, preexec_fn=_default_signals)

    def java_pid(self, timeout: float = 20) -> int:
        path = self.state / "java.pid"
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if path.exists():
                return int(path.read_text())
            time.sleep(0.1)
        raise AssertionError("fake java never started")


def _default_signals() -> None:
    """A wrapper started from a background job (check.sh runs the suites in parallel) inherits SIGINT and SIGQUIT
    ignored, and bash cannot trap a signal ignored on entry. The owner's terminal delivers them, so set them back."""
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGQUIT, signal.SIG_DFL)


class WrapperCase(unittest.TestCase):
    def setUp(self) -> None:
        self.box = self.new_box()

    def new_box(self) -> Sandbox:
        """A fresh sandbox, removed after the test with any fake java still running in it."""
        td = tempfile.TemporaryDirectory()
        box = Sandbox(Path(td.name).resolve())
        self.addCleanup(td.cleanup)
        self.addCleanup(self._kill_java, box)
        return box

    @staticmethod
    def _kill_java(box: Sandbox) -> None:
        pid_file = box.state / "java.pid"
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass

    def assert_restored(self, profile: Path | None = None, original: bytes | None = None) -> None:
        profile = profile or self.box.profile
        self.assertEqual(original or self.box.original, profile.read_bytes())
        self.assertFalse(profile.with_name("profile.xml.hart-run.bak").exists())


class StartupScriptsOff(WrapperCase):
    def test_every_wrapper_starts_jmri_with_the_publishing_scripts_off_and_restores(self) -> None:
        for wrapper in WRAPPERS:
            with self.subTest(wrapper=wrapper):
                for f in self.box.state.iterdir():
                    f.unlink()
                done = self.box.run(wrapper, self.box.env())
                self.assertEqual(1, done.returncode, done.stderr)
                self.assertIn("did not produce a marker" if "discover" not in wrapper else "exited before",
                              done.stderr)
                launched = (self.box.state / "profile_at_launch.xml").read_text(encoding="utf-8")
                for name in PUBLISHING:
                    line = next(l for l in launched.splitlines() if name in l)
                    self.assertIn('enabled="no"', line, name)
                for name in ("hide_cats_desk_windows.py", "SystemConsoleAction"):
                    line = next(l for l in launched.splitlines() if name in l)
                    self.assertIn('enabled="yes"', line, name)
                runs = [l for l in launched.splitlines() if 'type="ScriptFile"' in l and 'enabled="yes"' in l
                        and "hide_cats" not in l]
                self.assertEqual(1, len(runs), runs)
                self.assertIn(f"{self.box.root}/{SCRIPTS}/", runs[0])
                self.assertIn(f'name="{self.box.root}/jmri/layouts/hart/output/tables.xml"', launched)
                self.assertEqual(LIVE_ID, (self.box.state / "launch_arg").read_text().strip())
                self.assert_restored()

    def test_traininfo_repair_works_on_the_profile_user_files_and_puts_them_back_on_failure(self) -> None:
        user_traininfo = self.box.home / "JMRI_UserFiles/dispatcher/traininfo"
        user_traininfo.mkdir(parents=True)
        (user_traininfo / "train1.xml").write_text("<before/>", encoding="utf-8")
        (user_traininfo / "only_before.xml").write_text("<kept/>", encoding="utf-8")
        done = self.box.run("run_panelpro_traininfo_repair.sh", self.box.env())
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn("train1.xml", (self.box.state / "traininfo_at_launch").read_text())
        env = (self.box.state / "env").read_text()
        self.assertIn(f"HART_TRAININFO_DIR={user_traininfo}\n", env)
        self.assertEqual("<before/>", (user_traininfo / "train1.xml").read_text(encoding="utf-8"))
        self.assertEqual("<kept/>", (user_traininfo / "only_before.xml").read_text(encoding="utf-8"))

    def test_traininfo_is_not_touched_when_the_profile_is_locked(self) -> None:
        self.box.profile.with_name("profile.xml.hart-run.bak").write_bytes(self.box.original)
        done = self.box.run("run_panelpro_traininfo_repair.sh", self.box.env())
        self.assertEqual(1, done.returncode)
        self.assertFalse((self.box.home / "JMRI_UserFiles").exists())

    def test_running_jmri_or_cats_is_refused_before_anything_changes(self) -> None:
        done = self.box.run("run_sml_discover.sh", self.box.env(HART_GUARD_JMRI_RUNNING="1"))
        self.assertEqual(1, done.returncode)
        self.assertIn("Quit CATS/PanelPro first", done.stderr)
        self.assertFalse((self.box.state / "launch_arg").exists())
        self.assert_restored()

    def test_sml_discovery_runs_on_the_base_then_takes_the_store(self) -> None:
        """run_sml_discover.sh writes the discovery base (no logic), lets PanelPro Store to a temporary file, then
        hands that Store to build_tables.py --discovered-from; the repo's tables.xml is never the Store target."""
        env = self.box.env(FAKE_MODE="marker", FAKE_MARKER_FROM="HART_SML_DISCOVER_MARKER")
        done = self.box.run("run_sml_discover.sh", env)
        self.assertEqual(0, done.returncode, done.stderr)
        calls = (self.box.root / "tools/schematic/build_tables.py.log").read_text().splitlines()
        self.assertEqual("--discovery-base", calls[0])
        self.assertEqual("--base-hash", calls[1])
        self.assertTrue(calls[2].startswith("--discovered-from "), calls)
        stored = calls[2].split(" ", 1)[1]
        stamp = self.box.root / "jmri/layouts/hart/data/schematic/discovered_sml.stamp"
        self.assertEqual("ab" * 32 + "\n", stamp.read_text(), "the stamp is the base's hash, written after the take")
        launched = (self.box.state / "env").read_text()
        self.assertIn(f"HART_SML_DISCOVER_FILE={stored}\n", launched)
        self.assertNotIn("output/tables.xml", stored)
        self.assertIn("DONE", done.stdout)
        self.assertNotIn("discovery base", done.stderr)          # a run that finished leaves no note
        self.assert_restored()

    def test_discovery_needs_the_approved_panel_unless_under_review(self) -> None:
        """The staging guard is retired (2026-11-22), so the wrapper checks the base's panel against the owner's
        approval (check_approved.py le-panel) before PanelPro starts; HART_TABLES_REVIEW=1 skips it for a review."""
        env = self.box.env(FAKE_MODE="marker", FAKE_MARKER_FROM="HART_SML_DISCOVER_MARKER", FAKE_UNAPPROVED="1")
        done = self.box.run("run_sml_discover.sh", env)
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn("not the one the owner approved; discovery not run", done.stderr)
        self.assertIn("HART_TABLES_REVIEW=1", done.stderr)
        self.assertFalse((self.box.state / "launch_arg").exists(), "PanelPro must not start")
        log = (self.box.root / "tools/schematic/check_approved.py.log").read_text().splitlines()
        self.assertEqual(["le-panel"], log)
        self.assert_restored()
        env = self.box.env(FAKE_MODE="marker", FAKE_MARKER_FROM="HART_SML_DISCOVER_MARKER", FAKE_UNAPPROVED="1",
                           HART_TABLES_REVIEW="1")
        done = self.box.run("run_sml_discover.sh", env)
        self.assertEqual(0, done.returncode, done.stderr)

    def test_a_failed_take_keeps_the_discovery_store(self) -> None:
        env = self.box.env(FAKE_MODE="marker", FAKE_MARKER_FROM="HART_SML_DISCOVER_MARKER", FAKE_TABLES_FAIL="1")
        done = self.box.run("run_sml_discover.sh", env)
        self.assertEqual(1, done.returncode, done.stderr)
        kept = sorted((self.box.root / "media/pulled-stores").glob("discovery-*.xml"))
        self.assertEqual(1, len(kept), done.stderr)
        self.assertIn(f"kept as {kept[0]}", done.stderr)
        self.assertIn(f"--discovered-from {kept[0]}", done.stderr)
        self.assertIn("tables.xml is now the discovery base", done.stderr)
        self.assertFalse((self.box.root / "jmri/layouts/hart/data/schematic/discovered_sml.stamp").exists())
        self.assertNotIn("DONE", done.stdout)
        self.assert_restored()

    def test_a_run_that_fails_after_the_base_says_how_to_restore(self) -> None:
        done = self.box.run("run_sml_discover.sh", self.box.env())     # PanelPro quits with no marker
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn("tables.xml is now the discovery base", done.stderr)
        self.assertIn("python3 tools/schematic/build_tables.py", done.stderr)
        self.assert_restored()

    def test_nx_defaults_paint_only(self) -> None:
        done = self.box.run("run_nx_discover.sh", self.box.env())
        self.assertEqual(1, done.returncode, done.stderr)
        env = (self.box.state / "env").read_text()
        self.assertIn("HART_NX_SMOKE=0\n", env)
        self.assertIn("HART_NX_THROW=\n", env)
        self.assertNotIn("commands MQTT turnouts", done.stderr)
        done = self.box.run("run_nx_discover.sh", self.box.env(HART_NX_THROW="1"))
        self.assertIn("HART_NX_THROW=1: the smoke sets a real NX route, which commands MQTT turnouts", done.stderr)


class Rehearsal(WrapperCase):
    def setUp(self) -> None:
        super().setUp()
        self.uf = self.box.tmp / "rehearsal-files"
        self.reh = self.box.make_profile(self.box.tmp / "rehearsal", "Rehearsal", "Rehearsal.42", f"{self.uf}/")
        self.reh_original = self.reh.read_bytes()

    def test_profile_xml_alone_runs_on_that_profile_and_its_user_files(self) -> None:
        live_mtime = self.box.profile.stat().st_mtime_ns
        env = self.box.env(profile=self.reh, JMRI_PROFILE_XML=str(self.reh))
        done = self.box.run("run_panelpro_traininfo_repair.sh", env)
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertEqual(str(self.reh.parent.parent), (self.box.state / "launch_arg").read_text().strip())
        self.assertIn('enabled="no"', (self.box.state / "profile_at_launch.xml").read_text(encoding="utf-8"))
        self.assertIn("train1.xml", (self.box.state / "traininfo_at_launch").read_text())
        self.assertIn(f"HART_TRAININFO_DIR={self.uf}/dispatcher/traininfo\n", (self.box.state / "env").read_text())
        self.assertFalse((self.box.home / "JMRI_UserFiles").exists())
        self.assertEqual(live_mtime, self.box.profile.stat().st_mtime_ns)
        self.assert_restored(self.reh, self.reh_original)
        self.assert_restored()

    def test_id_and_xml_that_disagree_stop_before_anything_changes(self) -> None:
        cases = ({"JMRI_PROFILE_XML": str(self.reh), "JMRI_PROFILE": LIVE_ID},
                 {"JMRI_PROFILE": "Rehearsal.42"},
                 {"JMRI_PROFILE_XML": str(self.reh), "JMRI_USER_FILES": str(self.box.tmp / "elsewhere")})
        for extra in cases:
            with self.subTest(**extra):
                done = self.box.run("run_panelpro_smoke_test.sh", self.box.env(**extra))
                self.assertEqual(1, done.returncode, done.stderr)
                self.assertRegex(done.stderr, "would patch one profile and start another|is not the user files folder|"
                                              "uses the live user files folder|holds a space")
                self.assertFalse((self.box.state / "launch_arg").exists())
                self.assert_restored(self.reh, self.reh_original)
                self.assert_restored()


    def test_a_copy_on_the_live_user_files_or_a_spaced_path_is_refused(self) -> None:
        clone = self.box.make_profile(self.box.tmp / "clone", "Clone", "Clone.1", r"home\:JMRI_UserFiles/")
        spaced = self.box.make_profile(self.box.tmp / "my rehearsal", "Spaced", "Spaced.1", f"{self.uf}/")
        for xml, message in ((clone, "uses the live user files folder"), (spaced, "holds a space")):
            with self.subTest(profile=str(xml)):
                original = xml.read_bytes()
                done = self.box.run("run_panelpro_smoke_test.sh", self.box.env(profile=xml, JMRI_PROFILE_XML=str(xml)))
                self.assertEqual(1, done.returncode, done.stderr)
                self.assertIn(message, done.stderr)
                self.assertFalse((self.box.state / "launch_arg").exists())
                self.assertEqual(original, xml.read_bytes())


class Deploy(WrapperCase):
    def test_deploy_and_cats_launch_refuse_while_a_backup_is_left(self) -> None:
        for rel in ("tools/hosts/sync_hart_package.sh", "tools/hosts/redeploy_commit.sh", "cats/scripts/launch_cats.sh",
                    "tools/hosts/pi/jython_list.sh", "tools/hosts/pi/jython_scripts.txt"):   # the last two: common.sh's
            dest = self.box.root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, dest)
        shutil.copytree(ROOT / "tools/hosts/deploy", self.box.root / "tools/hosts/deploy")   # the entry point's steps
        (self.box.root / "tools/env").mkdir(parents=True, exist_ok=True)
        for name in ("load_env.sh", "defaults.env"):   # the steps' shared file reads the host settings first
            shutil.copy2(ROOT / "tools/env" / name, self.box.root / "tools/env" / name)
        self.box.profile.with_name("profile.xml.hart-run.bak").write_bytes(self.box.original)
        env = self.box.env(HART_PI_SSH="nobody@example.invalid", HART_WIN_SSH="nobody@example.invalid")
        for rel, args in (("tools/hosts/sync_hart_package.sh", ["--stage-only", str(self.box.tmp / "stage")]),
                          ("tools/hosts/redeploy_commit.sh", ["HEAD", "--pi"]),
                          ("cats/scripts/launch_cats.sh", [])):
            with self.subTest(script=rel):
                done = subprocess.run(["/bin/bash", str(self.box.root / rel), *args], env=env, capture_output=True,
                                      preexec_fn=_default_signals,
                                      text=True, timeout=30)
                self.assertEqual(1, done.returncode, done.stderr)
                self.assertIn("is left from a PanelPro wrapper run that did not finish", done.stderr)
                self.assertIn(f"panelpro_profile.py restore --profile {self.box.profile}", done.stderr)
        self.assertFalse((self.box.tmp / "stage").exists())


class OneSharedLifecycle(unittest.TestCase):
    def test_wrappers_use_the_shared_helper_and_no_live_paths(self) -> None:
        for wrapper in WRAPPERS:
            with self.subTest(wrapper=wrapper):
                text = (ROOT / SCRIPTS / wrapper).read_text(encoding="utf-8")
                for needed in ('source "$ROOT/tools/hosts/panelpro_session.sh"', "pp_profile", "pp_begin",
                               "pp_launch", "pp_wait_marker", "refuse_hart_tables "):
                    self.assertIn(needed, text)
                for banned in ("trap ", "pkill", "kill \"$JPID\"", "Library/Preferences/JMRI", "JMRI_UserFiles",
                               "--after signal_coordinator.py", "enabled=\"no\"", "My_JMRI_Railroad", "Crandic",
                               "PP_PATCH\" insert"):
                    self.assertNotIn(banned, text)

    def test_one_process_pattern(self) -> None:
        session = (ROOT / "tools/hosts/panelpro_session.sh").read_text(encoding="utf-8")
        self.assertNotIn("Crandic", session)
        self.assertIn('python3 "$PP_PROFILE_PY" jmri-running', session)


class SmokeTestNames(unittest.TestCase):
    def test_level_prefixes_are_hartlibs(self) -> None:
        """panelpro_smoke_test.py is Jython and cannot import hartlib: its main and upper prefixes must be
        hartlib.level_devices' and the Layout Editor build's (le_common.py, which build_layout_le.py imports)."""
        import re
        sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
        from hartlib import level_devices
        src = (ROOT / SCRIPTS / "panelpro_smoke_test.py").read_text(encoding="utf-8")
        got = dict(re.findall(r'^(LEVEL_\w+_PREFIX) = "([^"]+)"', src, re.M))
        builder = (ROOT / "tools/schematic/le_common.py").read_text(encoding="utf-8")
        self.assertEqual(got, {"LEVEL_SENSOR_PREFIX": level_devices.SENSOR_PREFIX,
                               "LEVEL_BLOCK_PREFIX": level_devices.BLOCK_PREFIX,
                               "LEVEL_TURNOUT_PREFIX": level_devices.TURNOUT_PREFIX})
        self.assertTrue(re.search(r"^BLOCK_SYS = level_devices\.BLOCK_PREFIX\b", builder, re.M))   # the build's


class PollInterval(unittest.TestCase):
    """HART_PANELPRO_POLL: a number above 0 overrides the poll interval; anything else keeps the default."""

    def poll(self, value: str | None) -> subprocess.CompletedProcess[str]:
        env = {k: v for k, v in os.environ.items() if k != "HART_PANELPRO_POLL"}
        if value is not None:
            env["HART_PANELPRO_POLL"] = value
        return subprocess.run(["bash", "-c", f'source "{ROOT}/tools/hosts/panelpro_session.sh"; _pp_poll 2'],
                              env=env, capture_output=True, text=True, timeout=30)

    def test_a_number_above_zero_overrides_and_anything_else_keeps_the_default(self) -> None:
        self.assertEqual("2", self.poll(None).stdout.strip())
        self.assertEqual("0.1", self.poll("0.1").stdout.strip())
        self.assertEqual("3", self.poll("3").stdout.strip())
        for bad in ("0", "0.0", "1s", "-1", "x"):
            with self.subTest(value=bad):
                done = self.poll(bad)
                self.assertEqual("2", done.stdout.strip())
                self.assertIn("is not a number above 0", done.stderr)


class UnknownJmriState(unittest.TestCase):
    """pp_jmri_running is true when the probe cannot say (exit 2), so pp_refuse_running refuses."""

    def run_probe(self, code: int) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "probe.py"
            fake.write_text(f"import sys\nsys.exit({code})\n", encoding="utf-8")
            script = (f'source "{ROOT}/tools/hosts/panelpro_session.sh"; PP_PROFILE_PY="{fake}"; '
                      'pp_jmri_running; echo "running=$?"; (pp_refuse_running refused); echo "refuse=$?"')
            return subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=60)

    def test_each_answer(self) -> None:
        for code, running, refuse in ((0, 0, 1), (1, 1, 0), (2, 0, 1)):
            with self.subTest(code=code):
                done = self.run_probe(code)
                self.assertIn(f"running={running}", done.stdout)
                self.assertIn(f"refuse={refuse}", done.stdout)
        self.assertIn("cannot tell whether", self.run_probe(2).stderr)


if __name__ == "__main__":
    unittest.main()
