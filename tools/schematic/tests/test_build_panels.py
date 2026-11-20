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
    ("hands", "build_hands.py", False),
    ("main-route", "build_main_route.py", False),
    ("staging-sets", "build_staging_sets.py", False),
    ("plan-lengths", "plan_lengths.py --check", True),
    ("staging-masts", "build_staging_masts.py --check", True),
    ("staging-sync", "sync_staging_signals.py --check", True),
    ("staging-map", "staging_device_map.py --check", True),
    ("signals", "build_signals.py", False),
    ("device-map", "build_device_map.py", False),
    ("main-upper-masts", "build_main_upper_masts.py", False),
    ("schematic", "publish_draft.py", False),
    ("cats", "build_cats_panel.py", False),
    ("approved-desks", "check_approved.py cats-ctc cats-abs", True),
    ("le-cutover", "build_layout_le.py --as-live", False),
    ("approved-candidate", "check_approved.py le-candidate", True),
    ("approved-live", "check_approved.py le-panel", True),
]
NAMES = [name for name, _cmd, _only in STEPS]
FAKE_PYTHON = """#!/bin/sh
echo "$*" >> "$PANELS_LOG"
case "$1" in *"/$PANELS_FAIL") exit 1 ;; esac
exit 0
"""


class StepList(unittest.TestCase):
    def test_the_script_lists_these_steps_in_this_order(self):
        got = re.findall(r"^(step|guard) (\S+) python3 tools/schematic/(.+)$", SCRIPT.read_text(encoding="utf-8"),
                         re.M)
        self.assertEqual([(name, cmd, kind == "guard") for kind, name, cmd in got], STEPS)

    def test_every_script_it_names_exists(self):
        for _name, cmd, _only in STEPS:
            self.assertTrue((HERE / cmd.split()[0]).is_file(), cmd)

    def test_the_header_comment_lists_the_steps_in_the_same_order(self):
        header = SCRIPT.read_text(encoding="utf-8").split("\nset -uo pipefail")[0]
        self.assertEqual(re.findall(r"^#   ([a-z][a-z-]+)  ", header, re.M), NAMES)

    def test_the_wiki_table_lists_the_steps_in_the_same_order(self):
        rows = re.findall(r"^\| ([a-z][a-z-]+) \| `([^`]+)` \|", WIKI.read_text(encoding="utf-8"), re.M)
        self.assertEqual(rows, [(name, cmd) for name, cmd, _only in STEPS])

    def test_the_staging_checks_come_before_what_reads_their_files(self):
        for early in ("staging-masts", "staging-sync"):
            for late in ("staging-map", "signals", "cats", "le-cutover"):
                self.assertLess(NAMES.index(early), NAMES.index(late), (early, late))


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
                       PANELS_FAIL=fail or "none")
            r = subprocess.run(["bash", str(SCRIPT), *args], cwd=REPO, env=env, capture_output=True, text=True)
            return r.returncode, r.stdout + r.stderr, log.read_text(encoding="utf-8").splitlines()

    def test_a_write_runs_every_step_in_order(self):
        code, out, ran = self.run_script()
        self.assertEqual((code, ran), (0, [f"tools/schematic/{cmd}" for _n, cmd, _o in STEPS]), out)
        self.assertIn("all current", out)

    def test_a_check_runs_every_step_with_check_and_names_each_stale_one(self):
        code, out, ran = self.run_script("--check", fail="sync_staging_signals.py")
        self.assertEqual(ran, [f"tools/schematic/{cmd} --check" for _n, cmd, _o in STEPS])
        self.assertEqual(code, 1)
        self.assertIn("stale or failed: staging-sync\n", out)
        self.assertNotIn("stopped", out)

    def test_a_write_stops_at_a_failed_check_and_does_not_say_it_writes(self):
        for name, script in (("staging-masts", "build_staging_masts.py"), ("staging-sync", "sync_staging_signals.py")):
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


# A python3 stand-in that runs the real sync_staging_signals.py against a stale copy of staging_masts.csv (a temp
# file: the repo's data files are only read) and answers every other script with success.
STALE_SYNC_PYTHON = """#!/bin/sh
case "$1" in
  */sync_staging_signals.py) shift; exec "$REAL_PYTHON" "$STALE_RUNNER" "$SCHEMATIC_DIR" "$STALE_CSV" "$@" ;;
esac
echo "$*" >> "$PANELS_LOG"
exit 0
"""
STALE_RUNNER = """import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import sync_staging_signals as sss
_want = sss.want_masts
sss.want_masts = lambda: _want(Path(sys.argv[2]))  # the default path is bound at import
sys.exit(sss.main(sys.argv[3:]))
"""


class StaleStagingCsv(unittest.TestCase):
    """build_panels.sh with the real sync_staging_signals.py --check and a staging_masts.csv missing its last mast,
    so tables.xml holds a staging mast the file does not: the check fails, and the run says so in both modes."""

    def run_script(self, *args, whole=False):
        import staging_device_map as sdm
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            current = sdm.MASTS
            lines = current.read_text(encoding="utf-8").splitlines(keepends=True)
            stale = tmp / "staging_masts.csv"
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
        self.assertIn("follow staging_masts.csv", out)

    def test_a_write_stops_at_the_stale_file_and_names_the_fix(self):
        code, out, ran = self.run_script()
        self.assertEqual(code, 1, out)
        self.assertIn("differs from staging_masts.csv", out)
        self.assertIn("run tools/schematic/sync_staging_signals.py", out)
        self.assertIn("stopped: staging-sync only checks and it failed; later steps read the files it checks", out)
        self.assertEqual(len(ran), NAMES.index("staging-sync"), ran)  # nothing after it ran

    def test_a_check_names_the_stale_step_and_never_says_it_stopped(self):
        code, out, ran = self.run_script("--check")
        self.assertEqual(code, 1, out)
        self.assertIn("differs from staging_masts.csv", out)
        self.assertIn("stale or failed: staging-sync\n", out)
        self.assertNotIn("stopped", out)
        self.assertNotIn("later steps read what", out)
        self.assertEqual(len(ran), len(NAMES) - 1, ran)  # every other step still ran


class MissingPlugin(unittest.TestCase):
    """build_staging_masts.py without the plugin submodule: a message, not a traceback."""

    def run_main(self, argv, required=""):
        import build_staging_masts as bsm
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
        self.assertIn("SKIPPED staging masts check: schematic-maps plugin not found: run git submodule update", out)
        self.assertEqual(self.run_main(["--check"], required="1")[0], 1)

    def test_a_write_and_show_name_the_fault(self):
        for argv in ([], ["--show"]):
            code, _out, err = self.run_main(argv)
            self.assertEqual(code, 2)
            self.assertIn("build_staging_masts.py: schematic-maps plugin not found", err)


if __name__ == "__main__":
    unittest.main()
