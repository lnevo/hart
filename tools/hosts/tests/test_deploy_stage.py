"""The layout deploy in --stage-only mode, with fake hosts and no ssh.

The package is what lands on the Pi and Windows. Its layout must not change when the
repo moves the scripts around (ADR-007 amendment 2026-11-12): the host scripts stay at
cats/scripts/pi and cats/scripts/windows inside it.
"""
from __future__ import annotations

import filecmp
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pi_drop import jython_rows  # noqa: E402
from win_jython import windows_jython  # noqa: E402
SYNC = ROOT / "tools/hosts/sync_hart_package.sh"
STEPS = ROOT / "tools/hosts/deploy"   # the entry point's steps: gate, stage, ship_mac, ship_pi, ship_win; common.sh is shared
WRAPPER = ROOT / "cats/scripts/sync_hart_package.sh"
PI_SRC = ROOT / "tools/hosts/pi"
WIN_SRC = ROOT / "tools/hosts/windows"
STAMP_KEYS = ("commit", "branch", "dirty", "dirty_paths", "tables_sha256", "tables_modified_by_deploy",
              "date", "deployed_from", "target", "source", "redeploy_from")


def python_stub(tmp: Path, digicon_dry: bool = False) -> None:
    """A python3 in the fake bin that stands in for the deploy's tables freshness check (build_tables.py --check,
    which regenerates the whole panel and is tools/check.sh's own job): it logs the call in tables_check.log and
    passes, or fails as a stale file does while `tmp`/tables_stale exists (as a missing plugin does, exit 3, while
    `tmp`/tables_no_plugin exists, and a source error, exit 2, while `tmp`/tables_source_error exists); the Digicon check fails while
    `tmp`/digicon_enabled exists. The gate's CI pass check (ci_pass.py) is logged in ci_pass.log and says CI covers
    the commit while `tmp`/ci_pass_skip exists, crashes (exit 7) while `tmp`/ci_pass_crash exists, says no with no reason while `tmp`/ci_pass_silent exists, and otherwise
    runs for real against the gh stand-in (fake_bin), which fails. With `digicon_dry` (keep_repo_tables) a
    writing call of the Digicon SML script runs as a dry run and is logged in gates.log. Every other python3 call
    goes to the real one unchanged."""
    real = shutil.which("python3")
    dry = f"""  if [[ "$a" == */disable_digicon_sml_in_tables.py && " $* " != *" --dry-run "* && " $* " != *" --check "* ]]; then
    echo "python3 $*" >>"{tmp}/gates.log"
    exec "{real}" "$@" --dry-run
  fi
""" if digicon_dry else ""
    tool = tmp / "bin/python3"
    tool.write_text(f"""#!/bin/bash
for a in "$@"; do
{dry}  if [[ "$a" == */disable_digicon_sml_in_tables.py && -f "{tmp}/digicon_enabled" ]]; then
    echo "ERROR: tables.xml has 1 Digicon SML destination(s) Enabled=yes" >&2
    exit 1
  fi
  if [[ "$a" == */tools/hosts/deploy/ci_pass.py ]]; then
    echo "python3 $*" >>"{tmp}/ci_pass.log"
    if [[ -f "{tmp}/ci_pass_skip" ]]; then
      echo "skipped G4: CI full pass for 0123456789ab (stand-in)"
      exit 0
    fi
    if [[ -f "{tmp}/ci_pass_silent" ]]; then
      exit 1
    fi
    if [[ -f "{tmp}/ci_pass_crash" ]]; then
      echo "Traceback (stand-in)" >&2
      exit 7
    fi
  fi
  if [[ "$a" == */tools/schematic/build_tables.py ]]; then
    echo "python3 $*" >>"{tmp}/tables_check.log"
    if [[ -f "{tmp}/tables_stale" ]]; then
      echo "STALE: jmri/layouts/hart/output/tables.xml is not what tools/schematic/build_tables.py writes" >&2
      exit 1
    fi
    if [[ -f "{tmp}/tables_no_plugin" ]]; then
      echo "build_tables.py: the schematic-maps plugin: not checked out" >&2
      exit 3
    fi
    if [[ -f "{tmp}/tables_source_error" ]]; then
      echo "build_tables.py: discovered_sml.xml names masts the tables do not hold" >&2
      exit 2
    fi
    exit 0
  fi
done
exec "{real}" "$@"
""", encoding="utf-8")
    tool.chmod(0o755)


def fake_bin(tmp: Path) -> Path:
    """ssh and scp that record any call and fail, so a stage that reached for the network fails; a gh that logs to
    gh.log and fails, so the gate's CI pass check (tools/hosts/deploy/ci_pass.py) never reaches GitHub and G4 runs;
    and the python3 stand-in for the tables freshness check (python_stub)."""
    bin_dir = tmp / "bin"
    bin_dir.mkdir()
    for name in ("ssh", "scp"):
        tool = bin_dir / name
        tool.write_text(f'#!/bin/sh\necho "{name} $*" >>"{tmp}/network.log"\nexit 99\n', encoding="utf-8")
        tool.chmod(0o755)
    gh = bin_dir / "gh"
    gh.write_text(f'#!/bin/sh\necho "gh $*" >>"{tmp}/gh.log"\necho "stand-in: no GitHub in the tests" >&2\nexit 4\n',
                  encoding="utf-8")
    gh.chmod(0o755)
    python_stub(tmp)
    return bin_dir


def keep_repo_tables(tmp: Path) -> None:
    """For tests that run the deploy for real (no --dry-run): a guard that the deploy never rewrites the repo's
    tables.xml. The deploy only checks Digicon (--check, R9c: the generator applies the rule); should a step call the
    script to write again, it runs as a dry run and is logged in gates.log, which the tests require to stay absent.
    Call after stage_env: it replaces the fake bin's python3 (python_stub)."""
    python_stub(tmp, digicon_dry=True)


def stage_env(tmp: Path) -> dict[str, str]:
    env = dict(os.environ)
    for name in list(env):
        if name.startswith(("HART_", "_hart")) or name in ("MQTT_HOST", "JMRI_JSON", "PI_HOST"):
            del env[name]
    env.update(
        PATH=f"{fake_bin(tmp)}{os.pathsep}{env.get('PATH', '')}",
        HART_ENV_FILE=str(tmp / "no-hart.env"),
        HART_PI_SSH="pi.example.invalid",
        HART_WIN_SSH="nobody@win.example.invalid",
        HART_WIN_SSH_PORT="1",
        HART_PI_USERFILES="/srv/fake-pi/JMRI_UserFiles",
        HART_WIN_USERFILES="X:/fake-win/JMRI_UserFiles",
        # the gate's own pull of a changed Pi (autopull_pi_changes) runs only in the tests that stub it
        HART_NO_AUTOPULL="1",
        # the owner's own operating flag must not stop a test deploy
        HART_OPERATING_FLAG=str(tmp / "no-operating-flag"),
        # the gate's origin/main check (check_on_main) against HEAD itself: passes on any branch, and no fetch
        HART_MAIN_REF="HEAD",
        # the stage's python3 calls import modules of the tree they run from: their bytecode goes under tmp, not
        # into __pycache__ folders of the live checkout
        PYTHONPYCACHEPREFIX=str(tmp / "pycache"),
    )
    return env


def run(script: Path, out: Path, env: dict[str, str], *flags: str, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(script), *flags, "--stage-only", str(out)],
                          cwd=cwd, env=env, capture_output=True, text=True, timeout=600)  # 106 s alone, near 300 s on a loaded box


def read_stamp(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines if line and not line.startswith("#"))


def tree(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def live_panels() -> list[str]:
    """The panels the deploy ships: the LIVE_PANELS array in the script."""
    src = (STEPS / "common.sh").read_text(encoding="utf-8")
    block = src[src.index("LIVE_PANELS=(") + len("LIVE_PANELS=("):]
    return block[:block.index(")")].split()


def git(*args: str, repo: Path = ROOT, raw: bool = False):
    """git's output in `repo`, stripped text, or the bytes as they are with `raw`."""
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True).stdout
    return out if raw else out.decode().strip()


class StageOnly(unittest.TestCase):
    tmp: ClassVar[Path]
    env: ClassVar[dict[str, str]]
    out: ClassVar[Path]
    done: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp())
        cls.env = stage_env(cls.tmp)
        cls.out = cls.tmp / "stage"
        cls.done = run(WRAPPER, cls.out, cls.env)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_runs_without_the_network(self) -> None:
        self.assertEqual(self.done.returncode, 0, self.done.stderr[-2000:])
        self.assertFalse((self.tmp / "network.log").exists(), "stage-only called ssh or scp")
        self.assertIn("DONE (stage only)", self.done.stdout)

    def test_the_pi_package_holds_every_script_its_jython_list_names(self) -> None:
        """The Pi apply step reads cats/scripts/pi/jython_scripts.txt from the package and stops on a row whose
        script the package lacks: a real staged package holds each one, unchanged."""
        listing = self.out / "pi/cats/scripts/pi/jython_scripts.txt"
        self.assertTrue(listing.is_file())
        rows = jython_rows(listing)
        self.assertGreater(len(rows), 10, rows)
        for row in rows:
            staged = self.out / "pi" / row.path
            self.assertTrue(staged.is_file(), f"pi package lacks {row.path}")
            self.assertTrue(filecmp.cmp(ROOT / row.path, staged, shallow=False), row.path)

    def test_the_windows_package_holds_its_jython_list_and_reader(self) -> None:
        """The Windows apply step reads the same cats/scripts/pi/jython_scripts.txt with jython_list.ps1 and stops on
        a row it installs whose script the package lacks: the staged list is the repo's, the reader is staged, and
        each row Windows installs is in the package."""
        pkg = self.out / "win"
        listing = pkg / "cats/scripts/pi/jython_scripts.txt"
        self.assertTrue(filecmp.cmp(ROOT / "tools/hosts/pi/jython_scripts.txt", listing, shallow=False))
        self.assertTrue(filecmp.cmp(WIN_SRC / "jython_list.ps1", pkg / "cats/scripts/windows/jython_list.ps1",
                                    shallow=False))
        rows = windows_jython(listing, pkg)
        self.assertGreater(len(rows), 10, rows)
        self.assertEqual([r for r in rows if not (pkg / r).is_file()], [])

    def test_builds_both_packages(self) -> None:
        for host in ("pi", "win"):
            pkg = self.out / host
            self.assertTrue((pkg / "tables.xml").is_file(), host)
            self.assertTrue((pkg / "cats/panels/HART_CTC.xml").is_file(), host)
            self.assertTrue((pkg / "operations/Operations.xml").is_file(), host)

    def test_profile_resources_are_staged_where_the_apply_steps_read_them(self) -> None:
        """The panel background and the USS sensor icons tables.xml loads through preference: sit under cats/ in
        both packages, unchanged (test_package_contents.py installs them from there)."""
        for host in ("pi", "win"):
            for rel in ("resources/misc/hart_panel_bg_plain.jpg", "resources/icons/USS/sensor/yellow-on.gif"):
                staged = self.out / host / "cats" / rel
                self.assertTrue(staged.is_file(), f"{host}: {rel}")
                self.assertTrue(filecmp.cmp(ROOT / "jmri" / rel, staged, shallow=False), f"{host}: {rel}")

    def test_signal_coordinator_ships_with_its_modules(self) -> None:
        """The script and every sibling module it loads (hartlib.coordinator) land, unchanged, in both packages."""
        import sys
        sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
        from hartlib import coordinator
        files = coordinator.files()
        self.assertGreater(len(files), 1)
        for host in ("pi", "win"):
            for path in files:
                staged = self.out / host / path.relative_to(ROOT)
                self.assertTrue(staged.is_file(), f"{host}: {staged.name}")
                self.assertTrue(filecmp.cmp(path, staged, shallow=False), f"{host}: {staged.name}")

    def test_panel_status_ships_with_its_parts(self) -> None:
        """panel_status.py and every part it runs (its PARTS, hartlib.coordinator) land, unchanged, in both
        packages, in the folder the host apply scripts copy them from."""
        import sys
        sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
        from hartlib import coordinator
        files = coordinator.files(coordinator.PANEL_STATUS)
        self.assertGreater(len(files), 1)
        for host in ("pi", "win"):
            for path in files:
                staged = self.out / host / path.relative_to(ROOT)
                self.assertTrue(staged.is_file(), f"{host}: {staged.name}")
                self.assertTrue(filecmp.cmp(path, staged, shallow=False), f"{host}: {staged.name}")

    def test_host_scripts_keep_their_package_paths(self) -> None:
        """tools/hosts/pi and tools/hosts/windows land at cats/scripts/pi and cats/scripts/windows."""
        for host in ("pi", "win"):
            for src, dest in ((PI_SRC, "cats/scripts/pi"), (WIN_SRC, "cats/scripts/windows")):
                staged = self.out / host / dest
                self.assertEqual(tree(staged), tree(src), f"{host}:{dest}")
                for name in tree(src):
                    if (src / name).is_file():
                        self.assertTrue(filecmp.cmp(src / name, staged / name, shallow=False), name)
            for name in ("install_ops_files.sh", "patch_jmri_startup.py", "panel_window_sizes.py",
                         "rewrite_button_icon_paths.py", "install_jmri_web_override.sh"):
                self.assertTrue((self.out / host / "cats/scripts" / name).is_file(), name)
        self.assertTrue(os.access(self.out / "pi/cats/scripts/pi/apply_hart_package_local.sh", os.X_OK))

    def test_the_profile_scripts_run_from_the_package_on_the_hartlib_it_carries(self) -> None:
        """patch_jmri_startup.py and panel_window_sizes.py find hartlib in the package (no checkout there), which
        holds only the modules they import, unchanged."""
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from pi_drop import HARTLIB_HOST_MODULES
        for host in ("pi", "win"):
            pkg = self.out / host
            staged = pkg / "tools/hartlib/src/hartlib"
            self.assertEqual(tree(staged), sorted(HARTLIB_HOST_MODULES), host)
            for name in HARTLIB_HOST_MODULES:
                self.assertTrue(filecmp.cmp(ROOT / "tools/hartlib/src/hartlib" / name, staged / name,
                                            shallow=False), f"{host}: {name}")
            profile = self.tmp / f"{host}-profile.xml"
            profile.write_text('<startup><perform class="jmri.util.startup.configurexml.PerformFileModelXml" '
                               'name="preference:tables.xml"/></startup>', encoding="utf-8")
            for argv in (["patch_jmri_startup.py", "load-tables", "--profile", str(profile),
                          "--tables", "preference:tables.xml"],
                         ["panel_window_sizes.py", "--help"]):
                with self.subTest(host=host, script=argv[0]):
                    # -B: no __pycache__ left in the package the other tests read
                    done = subprocess.run([sys.executable, "-I", "-B", str(pkg / "cats/scripts" / argv[0]),
                                           *argv[1:]], cwd=self.tmp, capture_output=True, text=True, timeout=60)
                    self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn('name="preference:tables.xml"', profile.read_text(encoding="utf-8"))

    def test_parked_features_stay_out_of_the_package(self) -> None:
        """A parked feature's files outside tables.xml are not shipped (hartlib.parked), so the host apply scripts
        install none of them and leave the copies already on a host alone; an unparked one ships."""
        import sys
        sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
        from hartlib import parked
        dispatcher = "dispatcher" in parked.PARKED
        uss = "uss" in parked.PARKED
        for host in ("pi", "win"):
            pkg = self.out / host
            self.assertEqual((pkg / "jmri/layouts/hart/dispatcher").exists(), not dispatcher, host)
            self.assertEqual((pkg / "jmri/layouts/hart/scripts/repair_dispatcher_traininfo.py").exists(),
                             not dispatcher, host)
            self.assertEqual((pkg / "ctc").exists(), not uss, host)
            self.assertTrue((pkg / "jmri/layouts/hart/scripts/hide_cats_desk_windows.py").is_file(), host)

    def test_apply_scripts_are_where_deploy_calls_them(self) -> None:
        source = (STEPS / "ship_pi.sh").read_text(encoding="utf-8") + (STEPS / "ship_win.sh").read_text(encoding="utf-8")
        self.assertIn("${PI_DROP}/cats/scripts/pi/apply_hart_package_local.sh", source)
        self.assertIn("\\\\cats\\\\scripts\\\\windows\\\\apply_hart_package_local.ps1", source)
        self.assertTrue((self.out / "pi/cats/scripts/pi/apply_hart_package_local.sh").is_file())
        self.assertTrue((self.out / "win/cats/scripts/windows/apply_hart_package_local.ps1").is_file())

    def test_wrapper_and_script_stage_the_same_package(self) -> None:
        out = self.tmp / "direct"
        done = run(SYNC, out, self.env, "--pi")
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        self.assertFalse((out / "win").exists(), "--pi stages the Pi package only")
        self.assertEqual(tree(out / "pi"), tree(self.out / "pi"))
        cmp = filecmp.dircmp(out / "pi", self.out / "pi")

        def differing(d: filecmp.dircmp, prefix: str = "") -> list[str]:
            found = [prefix + n for n in d.diff_files]
            for name, sub in d.subdirs.items():
                found += differing(sub, f"{prefix}{name}/")
            return found

        # Only the stamp may differ (its date is taken per run).
        self.assertLessEqual(set(differing(cmp)), {"cats/deploy_stamp.txt"})

    def test_pi_and_windows_differ_only_in_panels_and_stamp(self) -> None:
        """What makes building the package once safe: the host's user files reach only the panels."""
        pi, win = self.out / "pi", self.out / "win"
        self.assertEqual(tree(pi), tree(win))
        differ = [n for n in tree(pi) if (pi / n).is_file() and not filecmp.cmp(pi / n, win / n, shallow=False)]
        panels = {f"cats/panels/{p}" for p in live_panels()}
        self.assertTrue(panels)
        self.assertLessEqual(set(differ), {"cats/deploy_stamp.txt"} | panels)
        self.assertIn("cats/deploy_stamp.txt", differ)


class StagedOnce(unittest.TestCase):
    """--pi --win builds the shared package once (one mimic page build), then finishes each host."""

    def test_one_build_for_both_hosts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            env = stage_env(tmp)
            # Log every python3 call, then hand it to the shared stub (python_stub), which stands in for the deploy's
            # build_tables.py --check. That check regenerates the whole panel: on a CI runner whose schematic cache is
            # cold (a branch that bumps the plugin) it ran past 600 s (2026-11-21, #876, #889, #898). It is
            # test_deploy_gates' and check.sh's job; this test counts the builds of the package.
            python_stub(tmp)
            stub = tmp / "bin/python3-stub"
            (tmp / "bin/python3").rename(stub)
            tool = tmp / "bin/python3"
            tool.write_text(f'#!/bin/bash\necho "$*" >>"{tmp}/python.log"\nexec "{stub}" "$@"\n', encoding="utf-8")
            tool.chmod(0o755)
            done = run(SYNC, tmp / "stage", env, "--pi", "--win")
            self.assertEqual(done.returncode, 0, done.stderr[-2000:])
            calls = (tmp / "python.log").read_text(encoding="utf-8").splitlines()
            # the tables check went to the stub, not a real whole-panel solve
            self.assertIn("build_tables.py --check", (tmp / "tables_check.log").read_text(encoding="utf-8"))
            self.assertEqual(1, sum("build_mimic_web.py" in c for c in calls), calls)
            self.assertEqual(1, sum("publish_live.py --build-page" in c for c in calls), calls)
            # the panels are rewritten per host, each panel once per host
            panels = live_panels()
            rewrites = [c for c in calls if "rewrite_button_icon_paths.py" in c]
            self.assertEqual(2 * len(panels), len(rewrites), calls)
            for p in panels:
                self.assertEqual(2, sum(f"/cats/panels/{p} " in c for c in rewrites), (p, rewrites))
            for host in ("pi", "win"):
                self.assertEqual(read_stamp(tmp / "stage" / host / "cats/deploy_stamp.txt")["target"], host)


def private_clone(tmp: Path) -> tuple[Path, dict[str, str]]:
    """A clone of HEAD at `tmp`/repo with this checkout's own tools/hosts and roster master copied in (uncommitted
    edits to the deploy scripts are what runs), and stage_env for it, with the deploy audit's plugin taken from this checkout (the clone
    has no submodule checkout). A test that writes into the tree it stages from uses one, never the live checkout."""
    repo = tmp / "repo"
    subprocess.run(["git", "clone", "-q", "--shared", str(ROOT), str(repo)], check=True, capture_output=True)
    shutil.copytree(ROOT / "tools/hosts", repo / "tools/hosts", dirs_exist_ok=True)
    # the DecoderPro roster master the stage packs (stage.sh), as this checkout has it
    shutil.copytree(ROOT / "jmri/layouts/hart/roster", repo / "jmri/layouts/hart/roster", dirs_exist_ok=True)
    env = stage_env(tmp)
    env["SCHEMATIC_PLUGIN"] = str(ROOT / "external/model-railroad-skills/plugins/schematic-maps")
    return repo, env


class JythonListTheStageCannotShip(unittest.TestCase):
    """A jython_scripts.txt row the package would lack (here a script only a parked feature uses, which the stage
    leaves out) stops the stage, naming the row, before any host changes: the Pi apply step would stop on it."""

    ROW = "startup jmri/layouts/hart/scripts/repair_dispatcher_traininfo.py"

    def test_the_stage_stops_naming_the_row(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            repo, env = private_clone(tmp)
            listing = repo / "tools/hosts/pi/jython_scripts.txt"
            listing.write_text(listing.read_text(encoding="utf-8") + self.ROW + "\n", encoding="utf-8")
            done = run(repo / "tools/hosts/sync_hart_package.sh", tmp / "stage", env, cwd=repo)
            self.assertNotEqual(done.returncode, 0, done.stdout[-2000:])
            self.assertIn("stage: the package lacks jython that tools/hosts/pi/jython_scripts.txt lists", done.stderr)
            self.assertIn(self.ROW, done.stderr)
            self.assertNotIn("DONE (stage only)", done.stdout)
            self.assertFalse((tmp / "network.log").exists())


class MacStepStopsOnAMissingScript(unittest.TestCase):
    """The Mac step stops, naming the script, when a listed jython file is not in the repo, before this Mac
    changes (HOME and JMRI_HOME point into the test's folder)."""

    def test_names_the_script_and_installs_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            repo, env = private_clone(tmp)
            gone = next(r.path for r in jython_rows() if r.role == "sibling")
            (repo / gone).unlink()
            env.update(HOME=str(tmp / "home"), JMRI_HOME=str(tmp / "jmri"))
            done = subprocess.run(["bash", str(repo / "tools/hosts/deploy/ship_mac.sh")], cwd=repo, env=env,
                                  capture_output=True, text=True, timeout=300, check=False)
            self.assertEqual(done.returncode, 1, done.stdout[-2000:] + done.stderr[-2000:])
            self.assertIn(f"names jython the repo lacks: {gone}", done.stderr)
            self.assertFalse((tmp / "home/JMRI_UserFiles").exists(), "the Mac install began")
            self.assertFalse((tmp / "jmri").exists())


class StampNamesWhatWasShipped(unittest.TestCase):
    """The stamp, staged from a private clone of HEAD: other checks write into the live tree while this runs, so
    its dirty flag is read from a tree nothing else touches. The checkout's own tools/hosts is copied in, so
    uncommitted edits to the deploy scripts are what runs, and one untracked file makes the clone dirty on purpose,
    so the dirty stamp and its warning are always exercised."""

    MARKER = "stamp-test-untracked.txt"

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp())
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)
        cls.repo, env = private_clone(cls.tmp)
        (cls.repo / cls.MARKER).write_text("untracked\n", encoding="utf-8")
        cls.changes = git("status", "--porcelain", repo=cls.repo).splitlines()
        cls.out = cls.tmp / "stage"
        cls.done = run(cls.repo / "tools/hosts/sync_hart_package.sh", cls.out, env, cwd=cls.repo)
        if cls.done.returncode != 0:
            raise RuntimeError("staging from the clone failed:\n" + cls.done.stderr[-2000:])

    def cgit(self, *args: str) -> str:
        return git(*args, repo=self.repo)

    def test_stamp_names_what_was_shipped(self) -> None:
        self.assertIn(f"?? {self.MARKER}", self.changes)
        for host in ("pi", "win"):
            stamp = read_stamp(self.out / host / "cats/deploy_stamp.txt")
            self.assertEqual(tuple(stamp), STAMP_KEYS)
            self.assertEqual(stamp["commit"], self.cgit("rev-parse", "HEAD"))
            self.assertEqual(stamp["branch"], self.cgit("rev-parse", "--abbrev-ref", "HEAD"))
            self.assertEqual(stamp["dirty"], "yes")
            self.assertEqual(stamp["target"], host)
            self.assertEqual((stamp["source"], stamp["redeploy_from"]), ("deploy", "none"))
            self.assertRegex(stamp["date"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d{4}$")
            shipped = hashlib.sha256((self.out / host / "tables.xml").read_bytes()).hexdigest()
            self.assertEqual(stamp["tables_sha256"], shipped)
            committed = git("show", "HEAD:jmri/layouts/hart/output/tables.xml", repo=self.repo, raw=True)
            want = "no" if hashlib.sha256(committed).hexdigest() == shipped else "yes"
            self.assertEqual(stamp["tables_modified_by_deploy"], want)
        self.assertIn(f"WARNING: this checkout has {len(self.changes)} uncommitted or untracked path(s).",
                      self.done.stderr)


class FinderLitterStaysOut(unittest.TestCase):
    """A gitignored .DS_Store or ._ file in a staged folder must not reach the package.

    The litter is planted in a private clone the stage runs from (private_clone), never in the live checkout, where
    a killed run would leave it and other runs staging at the same time would copy it.
    """

    PLANTED = ("jmri/resources/jmri-web/.DS_Store", "jmri/resources/jmri-web/servlet/.DS_Store",
               "tools/hosts/pi/.DS_Store", "tools/hosts/windows/._apply_hart_package_local.ps1")

    def test_package_has_no_finder_files(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            repo, env = private_clone(tmp)
            for rel in self.PLANTED:
                self.assertTrue((repo / rel).parent.is_dir(), rel)     # a folder the stage copies
                (repo / rel).write_bytes(b"\0")
            out = tmp / "stage"
            done = run(repo / "tools/hosts/sync_hart_package.sh", out, env, cwd=repo)
            self.assertEqual(done.returncode, 0, done.stderr[-2000:])
            self.assertTrue((out / "pi").is_dir() and (out / "win").is_dir(), tree(out)[:20])
            litter = [p for p in tree(out) if Path(p).name == ".DS_Store" or Path(p).name.startswith("._")]
            self.assertEqual(litter, [])


class StageRsyncsSkipLitter(unittest.TestCase):
    """Every rsync in stage.sh skips Finder litter as it copies, so a .DS_Store that vanishes mid-copy (Finder
    writes and removes them in the checkout) is never read and cannot stop rsync with code 24."""

    def rsync_calls(self, script: str) -> list[str]:
        """Every rsync call in a deploy step, with backslash continuations joined and comments dropped, wherever
        rsync sits on the line (after &&, inside if ...; then)."""
        text = re.sub(r"\\\n\s*", " ", (STEPS / script).read_text(encoding="utf-8"))
        lines = [line.split("#", 1)[0] if line.lstrip().startswith("#") else line for line in text.splitlines()]
        return [line.strip() for line in lines if re.search(r"(^|[\s;&|(])rsync\s", line)]

    def test_every_rsync_in_stage_sh_carries_the_litter_excludes(self) -> None:
        text = (STEPS / "stage.sh").read_text(encoding="utf-8")
        self.assertIn("LITTER_EXCLUDES=(--exclude '.DS_Store' --exclude '._*')", text)
        calls = self.rsync_calls("stage.sh")
        self.assertGreater(len(calls), 0)
        for call in calls:
            self.assertIn('"${LITTER_EXCLUDES[@]}"', call, call)

    def test_the_mac_deploys_traininfo_rsync_skips_litter(self) -> None:
        calls = [c for c in self.rsync_calls("ship_mac.sh") if "traininfo" in c]
        self.assertEqual(len(calls), 1, calls)
        self.assertIn("--exclude '.DS_Store'", calls[0])
        self.assertIn("--exclude '._*'", calls[0])

    def test_the_call_finder_sees_chained_and_split_rsyncs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "fake.sh"
            fake.write_text('[[ -d x ]] && rsync -a "$a/" "$b/"\nif true; then rsync \\\n  -a "$c/" "$d/"; fi\n'
                            '# rsync -a "$commented/" out\n', encoding="utf-8")
            with unittest.mock.patch(f"{__name__}.STEPS", Path(tmp)):
                calls = self.rsync_calls("fake.sh")
        self.assertEqual(len(calls), 2, calls)


class StageOnlyRefusals(unittest.TestCase):
    def test_needs_a_folder(self) -> None:
        done = subprocess.run(["bash", str(SYNC), "--stage-only"], cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("--stage-only needs a folder", done.stderr)

    def test_empty_equals_form_never_deploys(self) -> None:
        """--stage-only= (an unset variable) must stop, not fall through to a real deploy."""
        with tempfile.TemporaryDirectory() as tmp:
            env = stage_env(Path(tmp))
            for flags in (["--stage-only="], ["--pi", "--stage-only="], ["--stage-only", ""]):
                done = subprocess.run(["bash", str(SYNC), *flags], cwd=ROOT, env=env,
                                      capture_output=True, text=True, timeout=60)
                self.assertNotEqual(done.returncode, 0, flags)
                self.assertIn("--stage-only needs a folder", done.stderr, flags)
            self.assertFalse((Path(tmp) / "network.log").exists())

    def test_apply_steps_get_the_configured_user_files(self) -> None:
        source = (STEPS / "ship_pi.sh").read_text(encoding="utf-8") + (STEPS / "ship_win.sh").read_text(encoding="utf-8")
        self.assertIn("JMRI_USERFILES='${PI_USERFILES}'", source)
        self.assertIn('-UserFiles \\"${WIN_USERFILES}\\"', source)
        win = (WIN_SRC / "apply_hart_package_local.ps1").read_text(encoding="utf-8")
        self.assertIn("[string]$UserFiles = ''", win)
        # Only the default when the deploy passes nothing; every install path uses $UserFiles.
        self.assertEqual(win.count("Join-Path $env:USERPROFILE 'JMRI_UserFiles"), 1)
        self.assertIn("& $desk -UserFiles $UserFiles", win)

    def test_refuses_a_folder_with_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            keep = Path(tmp) / "keep.txt"
            keep.write_text("mine", encoding="utf-8")
            done = subprocess.run(["bash", str(SYNC), "--stage-only", tmp], cwd=ROOT,
                                  capture_output=True, text=True)
            self.assertNotEqual(done.returncode, 0)
            self.assertIn("is not empty", done.stderr)
            self.assertEqual(keep.read_text(encoding="utf-8"), "mine")


class HostApplyInstallsStampLast(unittest.TestCase):
    def test_pi(self) -> None:
        source = (PI_SRC / "apply_hart_package_local.sh").read_text(encoding="utf-8")
        stamp = source.index('cp -f "$HART/cats/deploy_stamp.txt" "$CATS_HOME/deploy_stamp.txt"')
        self.assertGreater(stamp, source.index("install_desktop_icons.sh"))
        self.assertGreater(stamp, source.index("install_ops_files.sh"))

    def test_windows(self) -> None:
        source = (WIN_SRC / "apply_hart_package_local.ps1").read_text(encoding="utf-8")
        stamp = source.index("'cats\\deploy_stamp.txt'")
        self.assertGreater(stamp, source.index("& $desk"))
        self.assertIn("Join-Path $catsHome 'deploy_stamp.txt'", source)


class DirtyListUnderPipefail(unittest.TestCase):
    """A long dirty-path list must warn, not kill the deploy with SIGPIPE (exit 141)."""

    def test_long_list_prints_ten_and_exits_zero(self) -> None:
        line = next(l for l in (STEPS / "common.sh").read_text(encoding="utf-8").splitlines()
                    if 'printf \'%s\\n\' "$changes" |' in l and "wc -l" not in l)
        script = ("set -euo pipefail\n"
                  "changes=\"$(seq 1 20000 | sed 's/^/ M file/')\"\n"
                  + line.strip() + "\necho done\n")
        done = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.splitlines()[-1], "done")
        self.assertEqual(len(done.stdout.splitlines()), 11)


if __name__ == "__main__":
    unittest.main()
