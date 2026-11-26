"""The after-edit hook (.claude/hooks/check_after_edit.py): which checks an edited file runs, and its ruff
pass. Split from test_guards.py."""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from guards_case import ROOT, load  # noqa: E402


class AfterEditMatchingTests(unittest.TestCase):
    """check_after_edit.py: an edited script runs the test files that name it; data files keep every check.

    The checks themselves are not started: run() records each argv and answers with fail_code.
    """

    TESTS = "jmri/layouts/hart/scripts/tests"
    FILES = {
        f"{TESTS}/test_one.py": "import one\n",
        f"{TESTS}/test_many_a.py": "from many import thing\n",
        f"{TESTS}/test_lists.py": 'SCRIPTS = ["jmri/scripts/many.py"]\n',
        f"{TESTS}/test_other.py": "import many_more, someone\n",
        f"{TESTS}/helper.py": "import one, many, lonely\n",
        "jmri/scripts/tests/test_many_b.py": 'SCRIPT = ROOT / "jmri/scripts/many.py"\n',
        "cats/scripts/tests/test_cats.py": "import unrelated\n",
    }

    def setUp(self) -> None:
        self.after = load(ROOT / ".claude/hooks/check_after_edit.py", "hart_check_after_edit_matching_test")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(os.path.realpath(tmp.name))
        for rel, text in self.FILES.items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(text, encoding="utf-8")
        # The real hook watches one script; the made-up ones stand in for it here.
        self.after.WATCHED = re.compile(self.after.WATCHED.pattern.replace("signal_coordinator", "(one|many|lonely)"))
        self.after.toplevel = lambda directory: str(self.root)
        self.after.manifest_checks = lambda root: [("one", ["python3", "t/one.py"]), ("two", ["python3", "t/two.py"])]
        self.ran: list[list[str]] = []
        self.fail_code = 0

        def run(argv, **kwargs):
            self.assertEqual(kwargs["cwd"], str(self.root))
            self.ran.append(argv)
            return subprocess.CompletedProcess(argv, self.fail_code, "", "boom" if self.fail_code else "")

        self.after.subprocess = type("FakeSubprocess", (), {
            "run": staticmethod(run), "TimeoutExpired": subprocess.TimeoutExpired})

    def hook(self, rel: str) -> tuple[int, str]:
        saved, err = sys.stdin, io.StringIO()
        sys.stdin = io.StringIO(json.dumps({"tool_input": {"file_path": str(self.root / rel)}}))
        try:
            with contextlib.redirect_stderr(err):
                return self.after.main(), err.getvalue()
        finally:
            sys.stdin = saved

    def unit_runs(self) -> list[list[str]]:
        """What follows `python3 -m unittest discover -b -q` in each unit run."""
        return [argv[6:] for argv in self.ran if "unittest" in argv]

    def every_check(self) -> list[list[str]]:
        return [argv for name, argv in self.after.quick_checks(str(self.root))]

    def test_script_with_one_matching_test_file_runs_only_that_file(self) -> None:
        code, err = self.hook("jmri/scripts/one.py")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.unit_runs(), [["-s", self.TESTS, "-p", "test_one.py"]])
        self.assertEqual([argv for argv in self.ran if "unittest" not in argv],
                         [argv for argv in self.every_check() if "unittest" not in argv])
        self.assertIn("test_one.py", err)

    def test_script_with_several_matching_test_files_runs_each(self) -> None:
        code, err = self.hook("jmri/scripts/many.py")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.unit_runs(), [["-s", self.TESTS, "-p", "test_lists.py"],
                                            ["-s", self.TESTS, "-p", "test_many_a.py"],
                                            ["-s", "jmri/scripts/tests", "-p", "test_many_b.py"]])
        self.assertIn("3 test file(s)", err)

    def test_script_with_no_matching_test_file_falls_back_to_the_whole_job_and_says_so(self) -> None:
        code, err = self.hook("jmri/scripts/lonely.py")  # only helper.py names it, and that is not a test file
        self.assertEqual(code, 0, err)
        self.assertEqual(self.ran, self.every_check())
        self.assertIn("no test file names lonely.py; ran the whole unit-jmri job", err)

    def test_tables_edit_runs_every_check_as_before(self) -> None:
        self.assertIn("unit-jmri", [name for name, argv in self.after.quick_checks(str(self.root))])
        for rel in ("jmri/layouts/hart/output/tables.xml", "jmri/layouts/hart/output/signal_head_plan.csv"):
            self.ran.clear()
            self.assertEqual(self.hook(rel), (0, ""), rel)
            self.assertEqual(self.ran, self.every_check(), rel)

    def test_failing_matched_test_file_is_reported(self) -> None:
        self.fail_code = 1
        code, err = self.hook("jmri/scripts/one.py")
        self.assertEqual(code, 2)
        self.assertIn(f"--- unit {self.TESTS}/test_one.py FAILED", err)
        self.assertIn("boom", err)

    def test_unsearchable_tests_stop_the_hook_with_a_reason(self) -> None:
        for rel in self.FILES:
            (self.root / rel).unlink()
        code, err = self.hook("jmri/scripts/one.py")
        self.assertEqual(code, 2)
        self.assertIn("Quick checks not run after editing one.py: no test files under", err)
        self.assertEqual(self.ran, [])

    def test_unreadable_test_file_stops_the_hook_with_a_reason(self) -> None:
        (self.root / self.TESTS / "test_bad.py").write_bytes(b"\xff\xfe one")
        code, err = self.hook("jmri/scripts/one.py")
        self.assertEqual(code, 2)
        self.assertIn(f"cannot read {self.TESTS}/test_bad.py", err)
        self.assertEqual(self.ran, [])

    def test_a_manifest_that_does_not_load_stops_the_hook_with_a_reason(self) -> None:
        self.after.manifest_checks = mock.Mock(side_effect=self.after.ManifestLoadError("checks.toml: not valid TOML"))
        for rel in ("jmri/layouts/hart/output/tables.xml", "jmri/scripts/one.py"):
            code, err = self.hook(rel)
            self.assertEqual((code, "not run after editing" in err and "TOML. Run ./tools/check.sh." in err), (2, True))
        self.assertEqual(self.ran, [])

    def hook_out(self, rel: str) -> tuple[int, str, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code, err = self.hook(rel)
        return code, err, out.getvalue()

    def slow(self, *names: str, fail: tuple[str, ...] = ()):
        """A run() that times out for the checks whose argv holds one of `names` and fails for those of `fail`."""
        def run(argv, **kwargs):
            self.ran.append(argv)
            if any(n in argv for n in names):
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
            return subprocess.CompletedProcess(argv, 1 if any(f in argv for f in fail) else 0, "",
                                               "boom" if any(f in argv for f in fail) else "")
        self.after.subprocess = type("FakeSubprocess", (), {
            "run": staticmethod(run), "TimeoutExpired": subprocess.TimeoutExpired})

    def test_a_check_past_the_budget_is_not_run_not_failed_and_said_plainly(self) -> None:
        """Row 7 of section E (pipeline-coverage-handoff): unit-jmri under load runs past 20 s on a tables.xml edit."""
        self.slow("discover")
        code, err, out = self.hook_out("jmri/layouts/hart/output/tables.xml")
        line = "check_after_edit: unit-jmri: not run in the edit hook (over the 20 s budget; check.sh runs it)"
        self.assertEqual((code, err.strip()), (0, line))
        self.assertNotIn("FAILED", err)
        context = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(context, {"hookEventName": "PostToolUse", "additionalContext": line})

    def test_a_budget_used_up_names_each_check_left(self) -> None:
        clock = iter([0.0, 0.0, 16.0, 16.0])    # start; check one starts at 0; then 16 s are used, 4 left
        self.after.time = type("FakeTime", (), {"monotonic": staticmethod(lambda: next(clock, 16.0))})
        code, err, out = self.hook_out("jmri/layouts/hart/output/tables.xml")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.ran, [["python3", "t/one.py"]])
        for name in ("two", "unit-jmri"):
            self.assertIn(f"check_after_edit: {name}: not run in the edit hook (over the 20 s budget", err)
        self.assertIn("two: not run", json.loads(out)["hookSpecificOutput"]["additionalContext"])

    def test_a_failure_still_fails_beside_a_check_past_the_budget(self) -> None:
        self.slow("discover", fail=("t/one.py",))
        code, err, out = self.hook_out("jmri/layouts/hart/output/tables.xml")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("--- one FAILED", err)
        self.assertIn("unit-jmri: not run in the edit hook (over the 20 s budget", err)
        self.assertNotIn("unit-jmri FAILED", err)

    def test_unwatched_file_runs_nothing(self) -> None:
        self.assertEqual(self.hook("jmri/scripts/README.md"), (0, ""))
        self.assertEqual(self.ran, [])


class AfterEditRuffTests(unittest.TestCase):
    """check_after_edit.py runs tools/audit/check_ruff.py on each edited .py file of the checkout.

    A scratch checkout holds a copy of the real check script, ruff.toml, requirements.txt and hartlib; the ruff it
    runs is the real pinned one (linked in as the checkout's .venv/bin/ruff), or a stub for the case where it is missing.
    """

    def setUp(self) -> None:
        sys.path.insert(0, str(ROOT / "tools/audit"))
        import check_ruff
        try:
            self.ruff = check_ruff.find_ruff(check_ruff.pinned_version(ROOT), check_ruff.candidates(ROOT))
        except check_ruff.RuffSetupError as err:
            self.skipTest(str(err))
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(os.path.realpath(tmp.name))
        for rel in ("ruff.toml", "requirements.txt", "tools/audit/check_ruff.py"):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / rel, self.root / rel)
        shutil.copytree(ROOT / "tools/hartlib/src", self.root / "tools/hartlib/src",
                        ignore=shutil.ignore_patterns("__pycache__"))
        (self.root / ".venv/bin").mkdir(parents=True)
        (self.root / ".venv/bin/ruff").symlink_to(self.ruff)
        self.after = load(ROOT / ".claude/hooks/check_after_edit.py", "hart_check_after_edit_ruff_test")
        self.after.toplevel = lambda directory: str(self.root)
        self.ran: list[list[str]] = []
        self.after.subprocess = type("FakeSubprocess", (), {     # the table checks: none here
            "run": staticmethod(lambda argv, **kw: self.ran.append(argv)), "TimeoutExpired": subprocess.TimeoutExpired})

    def hook(self, path: Path) -> tuple[int, str]:
        saved, err = sys.stdin, io.StringIO()
        sys.stdin = io.StringIO(json.dumps({"tool_input": {"file_path": str(path)}}))
        try:
            with contextlib.redirect_stderr(err):
                return self.after.main(), err.getvalue()
        finally:
            sys.stdin = saved

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_a_finding_blocks_with_ruffs_output(self) -> None:
        code, err = self.hook(self.write("tools/x.py", "import os\n"))
        self.assertEqual(code, 2, err)
        self.assertIn("--- ruff FAILED (1 pyflakes finding(s)", err)
        self.assertIn("tools/x.py:1:8: F401", err)
        self.assertEqual(self.ran, [])

    def test_a_clean_file_and_an_excluded_file_pass_quietly(self) -> None:
        self.assertEqual(self.hook(self.write("tools/x.py", "import os\nprint(os.sep)\n")), (0, ""))
        self.assertEqual(self.hook(self.write("archive/old.py", "import os\n")), (0, ""))

    def test_a_relative_dotted_path_is_the_same_file(self) -> None:
        self.write("tools/x.py", "import os\n")
        cwd = os.getcwd()
        os.chdir(self.root / "tools")
        try:
            code, err = self.hook(Path("../tools/./x.py"))
        finally:
            os.chdir(cwd)
        self.assertEqual(code, 2, err)
        self.assertIn("F401", err)

    def test_a_path_through_a_symlink_is_still_checked(self) -> None:
        self.write("tools/x.py", "import os\n")
        with tempfile.TemporaryDirectory() as d:
            link = Path(d) / "link"
            link.symlink_to(self.root)           # git gives the resolved root, the edit names the link
            code, err = self.hook(link / "tools/x.py")
        self.assertEqual(code, 2, err)
        self.assertIn("F401", err)

    def test_missing_ruff_says_so_on_one_line_and_does_not_block(self) -> None:
        (self.root / ".venv/bin/ruff").unlink()
        with mock.patch.dict(os.environ, {"PATH": str(self.root / "no-bin")}):
            code, err = self.hook(self.write("tools/x.py", "import os\n"))
        self.assertEqual(code, 0)
        self.assertEqual(len(err.strip().splitlines()), 1, err)
        self.assertIn("check_after_edit: ruff not run on x.py: ruff ", err)

    def test_a_checkout_without_the_check_script_says_so_and_does_not_block(self) -> None:
        (self.root / "tools/audit/check_ruff.py").unlink()
        code, err = self.hook(self.write("tools/x.py", "import os\n"))
        self.assertEqual(code, 0)
        self.assertIn("has no tools/audit/check_ruff.py", err)

    def test_a_broken_check_script_blocks(self) -> None:
        (self.root / "tools/audit/check_ruff.py").write_text("def broken(:\n", encoding="utf-8")
        code, err = self.hook(self.write("tools/x.py", "x = 1\n"))
        self.assertEqual(code, 2)
        self.assertIn("tools/audit/check_ruff.py did not load", err)

    def test_a_file_outside_the_checkout_is_not_checked(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            outside = Path(d) / "bad.py"
            outside.write_text("import os\n", encoding="utf-8")
            self.assertEqual(self.hook(outside), (0, ""))

    def test_a_watched_script_gets_ruff_and_its_checks(self) -> None:
        self.after.checks_for = lambda root, path: ([("phase02", ["python3", "phase02.py"])], "")
        self.after.subprocess = type("FakeSubprocess", (), {
            "run": staticmethod(lambda argv, **kw: (self.ran.append(argv), subprocess.CompletedProcess(argv, 0, "", ""))[1]),
            "TimeoutExpired": subprocess.TimeoutExpired})
        code, err = self.hook(self.write("jmri/scripts/signal_coordinator.py", "x = latch.await(1)\n"))
        self.assertEqual(code, 0, err)       # excluded by ruff.toml: Jython that Python 3 cannot parse
        self.assertEqual(self.ran, [["python3", "phase02.py"]])
        code, err = self.hook(self.write("jmri/scripts/sml_beans.py", "import os\n"))
        self.assertEqual(code, 2, err)
        self.assertIn("F401", err)


if __name__ == "__main__":
    unittest.main()
