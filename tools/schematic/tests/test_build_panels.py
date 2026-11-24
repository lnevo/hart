"""build_panels.sh: the steps it runs, their order, and what it says when one stops the run.

The script is run with a stand-in python3 on PATH that only records its arguments, so no build runs here.
"""
import contextlib
import io
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parents[1]
SCRIPT = HERE / "build_panels.sh"
WIKI = REPO / "wiki/pipelines/schematic-panels.md"
sys.path.insert(0, str(HERE))

# (step, script and arguments, True when it only checks in both modes), in the order the outputs depend on each other.
STEPS = [
    ("hands", "tools/schematic/build_hands.py", False),
    ("staging-sets", "tools/schematic/build_staging_sets.py", False),
    ("main-route", "tools/schematic/build_main_route.py", False),
    ("plan-lengths", "tools/schematic/plan_lengths.py --check", True),
    ("device-map", "tools/schematic/build_device_map.py", False),
    ("masts", "tools/schematic/build_masts.py", False),
    ("signals", "tools/schematic/build_signals.py", False),
    ("head-plan", "jmri/layouts/hart/scripts/build_hart_signal_heads.py --wiring-only", False),
    ("schematic", "tools/schematic/publish_draft.py", False),
    ("sml-current", "tools/schematic/check_sml_current.py", True),
    ("tables", "tools/schematic/build_tables.py", False),
    ("signals-sync", "tools/schematic/sync_signals.py --check", True),
    ("device-master", "tools/schematic/check_device_master.py --check", True),
    ("cats", "tools/schematic/build_cats_panel.py", False),
    ("approved-desks", "tools/schematic/check_approved.py cats-ctc cats-abs", True),
    ("approved-live", "tools/schematic/check_approved.py le-panel", True),
]
NAMES = [name for name, _cmd, _only in STEPS]
FAKE_PYTHON = """#!/bin/sh
case "$1" in */panel_stamps.py) [ "$2" = current ] && exit 1; exit 0 ;; esac    # the stamps: nothing is current
echo "$*" >> "$PANELS_LOG"
case "$1" in *"/$PANELS_FAIL") exit 1 ;; esac
exit 0
"""


class StepList(unittest.TestCase):
    def test_the_script_lists_these_steps_in_this_order(self):
        got = re.findall(r"^(step|guard) (\S+) python3 (.+)$", SCRIPT.read_text(encoding="utf-8"),
                         re.M)
        self.assertEqual([(name, cmd, kind == "guard") for kind, name, cmd in got], STEPS)

    def test_every_script_it_names_exists(self):
        for _name, cmd, _only in STEPS:
            self.assertTrue((REPO / cmd.split()[0]).is_file(), cmd)

    def test_the_header_comment_lists_the_steps_in_the_same_order(self):
        header = SCRIPT.read_text(encoding="utf-8").split("\nset -uo pipefail")[0]
        self.assertEqual(re.findall(r"^#   ([a-z][a-z-]+)  ", header, re.M), NAMES)

    def test_the_wiki_table_lists_the_steps_in_the_same_order(self):
        rows = re.findall(r"^\| ([a-z][a-z-]+) \| `([^`]+)` \|", WIKI.read_text(encoding="utf-8"), re.M)
        self.assertEqual(rows, [(name, cmd.rsplit('/', 1)[-1]) for name, cmd, _only in STEPS])

    def test_the_masts_come_after_the_device_map_and_before_what_reads_them(self):
        self.assertLess(NAMES.index("device-map"), NAMES.index("masts"))     # main and upper's rows are its
        # signals.json is drawn from masts.csv: in one run, after the masts are written (review of #859); nothing
        # before signals reads signals.json (device-map and masts gave the same outputs with every signal dropped)
        self.assertLess(NAMES.index("masts"), NAMES.index("signals"))
        for late in ("schematic", "cats", "tables"):
            self.assertLess(NAMES.index("masts"), NAMES.index(late), late)
        # what reads tables.xml runs after the step that writes it (ADR-029): the staging checks, the CATS desks
        # (their turnouts, sensors and masts) and the live fingerprint, so one make panels leaves them all current
        for check in ("signals-sync", "device-master", "cats", "approved-desks", "approved-live"):
            self.assertLess(NAMES.index("tables"), NAMES.index(check), check)


class DryRun(unittest.TestCase):
    """The script itself, with python3 replaced by a recorder that fails for one named script."""

    def run_script(self, *args, fail=""):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "python3"
            fake.write_text(FAKE_PYTHON, encoding="utf-8")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            log = Path(tmp) / "log"
            log.touch()
            env = dict(os.environ, PATH=f"{tmp}{os.pathsep}{os.environ['PATH']}", PANELS_LOG=str(log),
                       PANELS_FAIL=fail or "none", HART_PANELS_OS="Linux")    # no SML discovery here: SmlDiscovery
            r = subprocess.run(["bash", str(SCRIPT), *args], cwd=REPO, env=env, capture_output=True, text=True)
            return r.returncode, r.stdout + r.stderr, log.read_text(encoding="utf-8").splitlines()

    def test_a_write_runs_every_step_in_order(self):
        code, out, ran = self.run_script()
        self.assertEqual((code, ran), (0, [cmd for _n, cmd, _o in STEPS]), out)
        self.assertIn("all current", out)

    def test_a_check_runs_every_step_with_check_and_names_each_stale_one(self):
        code, out, ran = self.run_script("--check", fail="sync_signals.py")
        self.assertEqual(ran, [f"{cmd} --check" for _n, cmd, _o in STEPS])
        self.assertEqual(code, 1)
        self.assertIn("stale or failed: signals-sync\n", out)
        self.assertNotIn("stopped", out)

    def test_a_write_stops_at_a_failed_check_and_does_not_say_it_writes(self):
        for name, script in (("plan-lengths", "plan_lengths.py"), ("signals-sync", "sync_signals.py"),
                             ("sml-current", "check_sml_current.py")):
            with self.subTest(name):
                code, out, ran = self.run_script(fail=script)
                self.assertEqual((code, ran[-1].split()[0]), (1, f"tools/schematic/{script}"), out)
                self.assertEqual(len(ran), NAMES.index(name) + 1)
                self.assertIn(f"stopped: {name} only checks and it failed; later steps read the files it checks", out)
                self.assertNotIn("writes", out)

    def test_a_write_stops_at_a_failed_build(self):
        code, out, ran = self.run_script(fail="build_signals.py")
        self.assertEqual((code, len(ran)), (1, NAMES.index("signals") + 1), out)
        self.assertIn("stopped: later steps read what signals writes", out)

    def test_an_unknown_argument_is_refused(self):
        code, out, ran = self.run_script("--chek")
        self.assertEqual((code, ran), (2, []), out)


# A python3 stand-in whose sml-current guard says stale (exit 1) until the stand-in discovery has run, and which
# fails it with SML_RC when that is set (2: a build error, not staleness).
SML_PYTHON = """#!/bin/sh
case "$1" in */panel_stamps.py) [ "$2" = current ] && exit 1; exit 0 ;; esac
echo "$*" >> "$PANELS_LOG"
case "$1" in */check_sml_current.py)
  [ -n "$SML_RC" ] && exit "$SML_RC"
  [ -f "$DISCOVERED" ] && exit 0
  exit 1 ;;
esac
exit 0
"""
FAKE_DISCOVER = """#!/bin/sh
echo "discover" >> "$PANELS_LOG"
[ -n "$DISCOVER_FAIL" ] && { echo "The Layout Editor panel is not the one the owner approved" >&2; exit 1; }
if [ -n "$SML_ALWAYS_STALE" ]; then touch "$DISCOVERED.once"; else touch "$DISCOVERED"; fi
exit 0
"""


class SmlDiscovery(unittest.TestCase):
    """A write on the Mac discovers when sml-current says stale, then checks again and goes on to tables
    (owner, 2026-11-24). Off the Mac, in CI, while operating, in --check or on a build error it stops as before."""

    def run_script(self, *args, os_name="Darwin", operating=False, **extra):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            fake = tmp / "python3"
            fake.write_text(SML_PYTHON, encoding="utf-8")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            discover = tmp / "discover.sh"
            discover.write_text(FAKE_DISCOVER, encoding="utf-8")
            log = tmp / "log"
            log.touch()
            flag = tmp / "operating"
            if operating:
                flag.write_text("by=owner\nsince=now\nreason=test\n", encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if k not in ("CI", "HART_SML_AUTO_DISCOVER", "HART_TABLES")}
            env.update(PATH=f"{tmp}{os.pathsep}{os.environ['PATH']}", PANELS_LOG=str(log),
                       DISCOVERED=str(tmp / "discovered"), HART_PANELS_OS=os_name,
                       HART_SML_DISCOVER_CMD=str(discover), HART_OPERATING_FLAG=str(flag), **extra)
            r = subprocess.run(["bash", str(SCRIPT), *args], cwd=REPO, env=env, capture_output=True, text=True)
            return r.returncode, r.stdout + r.stderr, log.read_text(encoding="utf-8").splitlines()

    def scripts(self, ran):
        return [line.split()[0].rsplit("/", 1)[-1] for line in ran]

    def test_a_stale_write_on_the_mac_discovers_checks_again_and_goes_on(self):
        code, out, ran = self.run_script()
        self.assertEqual(code, 0, out)
        got = self.scripts(ran)
        i = got.index("discover")
        self.assertEqual(got[i - 1:i + 3], ["check_sml_current.py", "discover", "check_sml_current.py",
                                             "build_tables.py"])
        self.assertEqual(got.count("discover"), 1)
        self.assertIn("sml-discover: ok", out)
        self.assertIn("all current", out)

    def test_it_discovers_once_and_stops_when_still_stale(self):
        code, out, ran = self.run_script(SML_ALWAYS_STALE="1")
        self.assertEqual(code, 1, out)
        got = self.scripts(ran)
        self.assertEqual(got.count("discover"), 1)
        self.assertEqual(got[-1], "check_sml_current.py")
        self.assertIn("stopped: sml-current only checks and it failed", out)

    def test_a_failed_discovery_stops_with_its_message(self):
        code, out, ran = self.run_script(DISCOVER_FAIL="1")
        self.assertEqual(code, 1, out)
        self.assertEqual(self.scripts(ran)[-1], "discover")
        self.assertIn("not the one the owner approved", out)
        self.assertIn("stopped: SML discovery failed", out)
        self.assertNotIn("build_tables.py", "\n".join(ran))

    def test_where_it_does_not_discover_it_stops_and_says_why(self):
        cases = {
            "off the Mac": (dict(os_name="Linux"), "discovery runs PanelPro on the Mac, and this is Linux"),
            "CI": (dict(CI="true"), "this is CI"),
            "operating": (dict(operating=True), "the operating flag is set"),
            "turned off": (dict(HART_SML_AUTO_DISCOVER="0"), "HART_SML_AUTO_DISCOVER=0"),
        }
        for label, (kw, why) in cases.items():
            with self.subTest(label):
                code, out, ran = self.run_script(**kw)
                self.assertEqual(code, 1, out)
                self.assertNotIn("discover", self.scripts(ran))
                self.assertIn(f"not discovering here: {why}", out)
                self.assertIn("stopped: sml-current only checks and it failed", out)

    def test_a_build_error_is_not_staleness(self):
        code, out, ran = self.run_script(SML_RC="2")
        self.assertEqual(code, 1, out)
        self.assertNotIn("discover", self.scripts(ran))
        self.assertNotIn("not discovering", out)

    def test_a_check_never_discovers(self):
        code, out, ran = self.run_script("--check")
        self.assertEqual(code, 1, out)
        self.assertNotIn("discover", self.scripts(ran))
        self.assertIn("stale or failed: sml-current\n", out)


# A python3 stand-in that runs the real sync_signals.py against a stale copy of masts.csv (a temp
# file: the repo's data files are only read) and answers every other script with success.
STALE_SYNC_PYTHON = """#!/bin/sh
case "$1" in
  */panel_stamps.py) [ "$2" = current ] && exit 1; exit 0 ;;
  */sync_signals.py) shift; exec "$REAL_PYTHON" "$STALE_RUNNER" "$SCHEMATIC_DIR" "$STALE_CSV" "$@" ;;
esac
echo "$*" >> "$PANELS_LOG"
exit 0
"""
STALE_RUNNER = """import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import sync_signals as sss
_want = sss.want_masts
sss.want_masts = lambda: _want(Path(sys.argv[2]))  # the default path is bound at import
sys.exit(sss.main(sys.argv[3:]))
"""


class StaleMastsCsv(unittest.TestCase):
    """build_panels.sh with the real sync_signals.py --check and a masts.csv missing its last mast,
    so tables.xml holds a staging mast the file does not: the check fails, and the run says so in both modes."""

    def run_script(self, *args, whole=False):
        import staging_device_map as sdm
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            current = sdm.MASTS
            lines = current.read_text(encoding="utf-8").splitlines(keepends=True)
            stale = tmp / "masts.csv"
            stale.write_text("".join(lines[:-1]), encoding="utf-8")
            (tmp / "runner.py").write_text(STALE_RUNNER, encoding="utf-8")
            fake = tmp / "python3"
            fake.write_text(STALE_SYNC_PYTHON, encoding="utf-8")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            log = tmp / "log"
            log.touch()
            env = dict(os.environ, PATH=f"{tmp}{os.pathsep}{os.environ['PATH']}", PANELS_LOG=str(log),
                       REAL_PYTHON=sys.executable, STALE_RUNNER=str(tmp / "runner.py"), SCHEMATIC_DIR=str(HERE),
                       STALE_CSV=str(current if whole else stale))
            r = subprocess.run(["bash", str(SCRIPT), *args], cwd=REPO, env=env, capture_output=True, text=True)
            return r.returncode, r.stdout + r.stderr, log.read_text(encoding="utf-8").splitlines()

    def test_the_unmodified_file_passes_so_the_dropped_row_is_the_cause(self):
        code, out, _ran = self.run_script("--check", whole=True)
        self.assertEqual(code, 0, out)
        self.assertIn("follow masts.csv", out)

    def test_a_write_stops_at_the_stale_file_and_names_the_fix(self):
        code, out, ran = self.run_script()
        self.assertEqual(code, 1, out)
        self.assertIn("differs from masts.csv", out)
        self.assertIn("run tools/schematic/build_masts.py, then tools/schematic/build_tables.py", out)
        self.assertIn("stopped: signals-sync only checks and it failed; later steps read the files it checks", out)
        self.assertEqual(len(ran), NAMES.index("signals-sync"), ran)  # nothing after it ran

    def test_a_check_names_the_stale_step_and_never_says_it_stopped(self):
        code, out, ran = self.run_script("--check")
        self.assertEqual(code, 1, out)
        self.assertIn("differs from masts.csv", out)
        self.assertIn("stale or failed: signals-sync\n", out)
        self.assertNotIn("stopped", out)
        self.assertNotIn("later steps read what", out)
        self.assertEqual(len(ran), len(NAMES) - 1, ran)  # every other step still ran


class MissingPlugin(unittest.TestCase):
    """build_masts.py without the plugin submodule: a message, not a traceback."""

    def run_main(self, argv, required=""):
        import build_masts as bsm
        import publish_draft as pd

        def gone():
            sys.exit("schematic-maps plugin not found: run git submodule update --init external/model-railroad-skills")
        bsm.sdm.lc.plugin.cache_clear()
        self.addCleanup(bsm.sdm.lc.plugin.cache_clear)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(pd, "plugin", gone), mock.patch.dict(os.environ, {"SCHEMATIC_REQUIRED": required}), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = bsm.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_check_is_skipped_and_fails_only_when_required(self):
        code, out, _err = self.run_main(["--check"])
        self.assertEqual(code, 0)
        self.assertIn("SKIPPED masts check: schematic-maps plugin not found: run git submodule update", out)
        self.assertEqual(self.run_main(["--check"], required="1")[0], 1)

    def test_a_write_and_show_name_the_fault(self):
        for argv in ([], ["--show"]):
            code, _out, err = self.run_main(argv)
            self.assertEqual(code, 2)
            self.assertIn("build_masts.py: schematic-maps plugin not found", err)


if __name__ == "__main__":
    unittest.main()
