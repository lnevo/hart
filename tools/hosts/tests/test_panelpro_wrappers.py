"""The PanelPro wrappers (jmri/layouts/hart/scripts/run_*.sh) and their shared run lifecycle
(tools/hosts/panelpro_session.sh), run against a fake StartJMRI.

Every run uses a copy of the wrappers in a temporary checkout, a temporary HOME holding a fixture
profile, and a PATH of plain tools only (no MQTT client), so nothing reaches the live profile,
~/JMRI_UserFiles, the repo's tables or a broker. HART_GUARD_JMRI_RUNNING=0 (hartlib's override)
hides any real JMRI or CATS on this machine from the "already running" check.
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
# that sleeps (FAKE_MODE=hang; FAKE_IGNORE_TERM=1 makes it ignore SIGTERM) and waits on it.
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
if [[ "$FAKE_MODE" == hang ]]; then
  python3 -c '
import os, signal, sys, time
if sys.argv[2] == "1":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
open(sys.argv[1] + ".tmp", "w").write(str(os.getpid()))
os.rename(sys.argv[1] + ".tmp", sys.argv[1])
time.sleep(600)
' "$FAKE_STATE/java.pid" "${FAKE_IGNORE_TERM:-0}" "-Dorg.jmri.profile=$2" &
  wait
fi
exit 3
"""

def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return bool(state) and not state.startswith("Z")


class Sandbox:
    """A checkout copy, HOME, fake JMRI install and PATH for one test."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.root = tmp / "checkout"
        for rel in [f"{SCRIPTS}/{w}" for w in WRAPPERS] + [
                "tools/hosts/profile_tables_guard.sh", "tools/hosts/panelpro_session.sh",
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
                   HART_GUARD_JMRI_RUNNING="0")
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
        self._td = tempfile.TemporaryDirectory()
        self.box = Sandbox(Path(self._td.name).resolve())

    def tearDown(self) -> None:
        pid_file = self.box.state / "java.pid"
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
        self._td.cleanup()

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

    def test_nx_defaults_paint_only(self) -> None:
        done = self.box.run("run_nx_discover.sh", self.box.env())
        self.assertEqual(1, done.returncode, done.stderr)
        env = (self.box.state / "env").read_text()
        self.assertIn("HART_NX_SMOKE=0\n", env)
        self.assertIn("HART_NX_THROW=\n", env)
        self.assertNotIn("commands MQTT turnouts", done.stderr)
        done = self.box.run("run_nx_discover.sh", self.box.env(HART_NX_THROW="1"))
        self.assertIn("HART_NX_THROW=1: the smoke sets a real NX route, which commands MQTT turnouts", done.stderr)


class Cleanup(WrapperCase):
    def test_success_waits_for_jmri_to_quit_then_restores(self) -> None:
        env = self.box.env(FAKE_MODE="marker", FAKE_MARKER_FROM="HART_PANELPRO_SMOKE_MARKER")
        done = self.box.run("run_panelpro_smoke_test.sh", env)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("PanelPro smoke: ok", done.stdout)
        self.assertNotIn("Stopping", done.stderr)
        self.assert_restored()

    def test_jmri_that_stays_after_the_marker_is_stopped(self) -> None:
        env = self.box.env(FAKE_MODE="hang", FAKE_MARKER_FROM="HART_CTC_LOGIC_SMOKE_MARKER",
                           HART_PANELPRO_EXIT_WAIT="1")
        done = self.box.run("run_ctc_logic_smoke.sh", env)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("PanelPro did not quit after the CTC Logic smoke; stopping it", done.stderr)
        self.assertFalse(_alive(self.box.java_pid()))
        self.assert_restored()

    def test_timeout_stops_java_even_when_it_ignores_term(self) -> None:
        env = self.box.env(FAKE_MODE="hang", FAKE_IGNORE_TERM="1", HART_PANELPRO_TIMEOUT="3")
        started = time.monotonic()
        done = self.box.run("run_panelpro_smoke_test.sh", env)
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn("did not produce a marker", done.stderr)
        self.assertIn("PanelPro ignored TERM; killing", done.stderr)
        self.assertFalse(_alive(self.box.java_pid()))
        self.assertLess(time.monotonic() - started, 30)
        self.assert_restored()

    def test_sigterm_sigint_and_sighup_stop_java_and_restore(self) -> None:
        for sig, code in ((signal.SIGTERM, 143), (signal.SIGINT, 130), (signal.SIGHUP, 129)):
            with self.subTest(signal=sig.name):
                (self.box.state / "java.pid").unlink(missing_ok=True)
                env = self.box.env(FAKE_MODE="hang", HART_PANELPRO_TIMEOUT="60")
                proc = subprocess.Popen(self.box.cmd("run_sml_discover.sh"), env=env, cwd=self.box.tmp,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                        preexec_fn=_default_signals)
                try:
                    java = self.box.java_pid()
                    self.assertIn(b'enabled="no"', self.box.profile.read_bytes())   # patched while running
                    proc.send_signal(sig)
                    _out, err = proc.communicate(timeout=30)
                finally:
                    if proc.poll() is None:
                        proc.kill()
                self.assertEqual(code, proc.returncode, err)
                self.assertFalse(_alive(java))
                self.assert_restored()

    def test_after_sigkill_the_next_run_refuses_and_restore_recovers(self) -> None:
        env = self.box.env(FAKE_MODE="hang", HART_PANELPRO_TIMEOUT="60")
        proc = subprocess.Popen(self.box.cmd("run_panelpro_stage1.sh"), env=env, cwd=self.box.tmp,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=_default_signals)
        java = self.box.java_pid()
        proc.kill()
        proc.wait(timeout=10)
        os.kill(java, signal.SIGKILL)   # the owner quits the PanelPro it left
        bak = self.box.profile.with_name("profile.xml.hart-run.bak")
        self.assertEqual(self.box.original, bak.read_bytes())
        self.assertNotEqual(self.box.original, self.box.profile.read_bytes())

        (self.box.state / "launch_arg").unlink()
        again = self.box.run("run_panelpro_smoke_test.sh", self.box.env())
        self.assertEqual(1, again.returncode)
        self.assertIn(f"restore --profile {self.box.profile}", again.stderr)
        self.assertFalse((self.box.state / "launch_arg").exists())

        restore = [sys.executable, str(self.box.root / "tools/hosts/panelpro_profile.py"), "restore",
                   "--profile", str(self.box.profile)]
        busy = subprocess.run(restore, capture_output=True, text=True, env={**env, "HART_GUARD_JMRI_RUNNING": "1"})
        self.assertNotEqual(0, busy.returncode)
        self.assertIn("running", busy.stderr)
        fixed = subprocess.run(restore, capture_output=True, text=True, env=env)
        self.assertEqual(0, fixed.returncode, fixed.stderr)
        self.assert_restored()
        self.assertFalse(self.box.profile.with_name("profile.xml.hart-run.sha256").exists())

    def test_cleanup_keeps_the_backup_when_the_started_jmri_cannot_be_stopped(self) -> None:
        script = self.box.tmp / "stuck.sh"
        script.write_text(f"""set -euo pipefail
ROOT={self.box.root}
source "$ROOT/tools/hosts/panelpro_session.sh"
pp_profile
pp_begin "$ROOT/{SCRIPTS}/panelpro_smoke_test.py"
pp_stop_jmri() {{ echo "Could not stop pids 99999" >&2; return 1; }}
exit 1
""", encoding="utf-8")
        done = subprocess.run(["/bin/bash", str(script)], env=self.box.env(), capture_output=True, text=True,
                              preexec_fn=_default_signals,
                              timeout=60)
        self.assertEqual(1, done.returncode)
        self.assertIn("PROFILE NOT RESTORED: quit that PanelPro, then run: python3", done.stderr)
        self.assertIn(f"restore --profile {self.box.profile}", done.stderr)
        self.assertTrue(self.box.profile.with_name("profile.xml.hart-run.bak").exists())
        self.assertNotEqual(self.box.original, self.box.profile.read_bytes())


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
        for rel in ("tools/hosts/sync_hart_package.sh", "tools/hosts/redeploy_commit.sh", "cats/scripts/launch_cats.sh"):
            dest = self.box.root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, dest)
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


if __name__ == "__main__":
    unittest.main()
