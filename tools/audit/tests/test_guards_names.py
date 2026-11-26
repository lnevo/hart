"""The main guard keeps the private name out of publishing text and no longer blocks table work. Split from
test_guards.py, whose rule holds here too: command text is data, never run.
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from guards_case import ROOT, load, mock_env  # noqa: E402

MAIN_GUARD = ROOT / ".claude/hooks/main_guard.py"


class PrivateNameAndTables(unittest.TestCase):
    """The private name stays out of publishing text, and table work is no longer blocked.

    Checked in this process with the command as data. The name check is replaced by a stand-in
    for a marker word, so no test file holds the real name.
    """
    MARK = "zz-private-marker"

    def guard(self):
        guard = load(MAIN_GUARD, "hart_main_guard_names_test")
        guard.contains_private_name = lambda text: self.MARK in text
        guard.main_checkout = lambda target: False  # CI's clone is a main checkout; tested in test_worktrees
        guard.on_main = lambda target, branched: False  # the checkout's branch must not matter; MainGuard tests the rule
        return guard

    def code(self, command: str) -> int:
        guard = self.guard()
        saved = sys.stdin
        sys.stdin = io.StringIO(json.dumps({"tool_input": {"command": command}, "cwd": str(ROOT)}))
        try:
            with mock_env(CLAUDE_PROJECT_DIR=str(ROOT)), contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                return guard.main()
        finally:
            sys.stdin = saved

    def test_table_writers_and_deploys_pass(self) -> None:
        # Owner's call (2026-11-18): a PanelPro or CATS open on the Mac blocks nothing; JMRI changes
        # tables.xml only on a Store, and the Mac is expendable. What must be kept lives on the Pi.
        for cmd in ("make tables-pull", "make ops-pull", "make deploy-all", "make redeploy COMMIT=abc123 HOSTS=--pi",
                    "./tools/hosts/sync_hart_package.sh --pi --win", "./tools/ops/pull_tables.sh"):
            self.assertEqual(self.code(cmd), 0, cmd)

    def test_private_name_blocked_in_publishing_text(self) -> None:
        m = self.MARK
        for cmd in (f'git commit -m "fix {m} text"', f"git -C . commit --message='{m}'",
                    f'gh pr create --title "{m}" --body ok', f'gh pr edit 3 --body "see {m}"',
                    f'gh issue create --title t --body "{m}"',
                    f'git commit -m "$(cat <<EOF\nfirst line\nmore {m}\nEOF\n)"'):
            self.assertEqual(self.code(cmd), 2, cmd)

    def test_clean_publishing_text_passes(self) -> None:
        for cmd in ('gh pr create --title t --body "clean"', f"echo {self.MARK}", "gh pr view 3"):
            self.assertEqual(self.code(cmd), 0, cmd)

    def test_private_name_in_body_file_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad, good = Path(tmp, "bad.md"), Path(tmp, "good.md")
            bad.write_text(f"body {self.MARK}\n")
            good.write_text("body\n")
            self.assertEqual(self.code(f"gh pr create --title t --body-file {bad}"), 2)
            self.assertEqual(self.code(f"git commit -F {bad}"), 2)
            self.assertEqual(self.code(f"gh pr create --title t --body-file {good}"), 0)

    def test_more_publishing_text_checked(self) -> None:
        m = self.MARK
        for cmd in (f'gh pr comment 3 --body "{m}"', f'gh issue comment 3 --body "{m}"',
                    f'gh issue edit 3 --body "{m}"', f'gh pr review 3 --comment --body "{m}"',
                    f'gh release create v1 --notes "{m}"', f'git tag -a v1 -m "{m}"'):
            self.assertEqual(self.code(cmd), 2, cmd)

    def test_attached_body_file_forms_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp, "bad.md")
            bad.write_text(f"body {self.MARK}\n")
            for cmd in (f"gh pr create --title t --body-file={bad}", f"git commit -F{bad}",
                        f"git commit --file={bad}"):
                self.assertEqual(self.code(cmd), 2, cmd)

    def test_name_in_an_earlier_part_does_not_block_a_clean_commit(self) -> None:
        cmd = f"git grep -n {self.MARK} ; git commit -m 'remove the leaked name'"
        self.assertEqual(self.code(cmd), 0)

    def test_publishing_blocked_when_name_check_cannot_load(self) -> None:
        guard = load(MAIN_GUARD, "hart_main_guard_missing_check_test")
        guard.NAME_CHECK = str(ROOT / "no" / "such" / "private_name.py")
        saved = sys.stdin
        sys.stdin = io.StringIO(json.dumps({"tool_input": {"command": "gh pr create --title t --body ok"},
                                            "cwd": str(ROOT)}))
        try:
            with mock_env(CLAUDE_PROJECT_DIR=str(ROOT)), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(guard.main(), 2)
        finally:
            sys.stdin = saved

    def test_after_edit_reads_its_checks_from_the_manifest(self) -> None:
        after = load(ROOT / ".claude/hooks/check_after_edit.py", "hart_check_after_edit_test")
        steps = tomllib.loads((ROOT / "tools/pipeline/checks.toml").read_text(encoding="utf-8"))["step"]
        want = [(e["name"], e["cmd"]) for e in steps if e.get("after_edit")]    # `manifest.py check` checks each field
        # Read without git: a hook that ran git, or the map check, here would cost seconds on every edit.
        with mock.patch("subprocess.run", side_effect=AssertionError("the manifest read ran a process")):
            got = after.manifest_checks(str(ROOT))
        self.assertEqual((got, len(got) >= 7), (want, True))
        self.assertEqual(after.quick_checks(str(ROOT))[-1], (after.UNIT_JMRI, after.UNIT_JMRI_ARGV))
        # unit-jmri is a unit-test job, not a manifest step (ADR-037 point 4): check.sh runs it as the hook does.
        self.assertIn(f"unit {after.UNIT_JMRI} " + " ".join(after.UNIT_JMRI_ARGV),
                      (ROOT / "tools/check.sh").read_text(encoding="utf-8"))

    def test_after_edit_manifest_problems_are_errors_not_an_empty_list(self) -> None:
        after = load(ROOT / ".claude/hooks/check_after_edit.py", "hart_check_after_edit_broken_test")
        step = '[[step]]\nname = "a"\ncmd = ["python3", "a.py"]\n'
        with tempfile.TemporaryDirectory() as tmp:
            for i, (text, why) in enumerate((("[[step]\n", "not valid TOML"), (step, "no step is marked after_edit"),
                                             (step.replace("python3", "{python}") + "after_edit = true\n",
                                              "but its name or cmd"), (None, "cannot read it"))):
                path = Path(tmp, f"{i}.toml")
                _ = text is None or path.write_text(text, encoding="utf-8")
                with self.subTest(why), self.assertRaisesRegex(after.ManifestLoadError, why):
                    after.manifest_checks(str(ROOT), path)
            self.assertRaisesRegex(after.NotMarked, "has no tools/pipeline/manifest.py", after.manifest_checks, tmp)
            shutil.copytree(ROOT / "tools/pipeline", Path(tmp, "tools/pipeline"), ignore=lambda d, n: ["checks.toml"])
            Path(tmp, "tools/pipeline/checks.toml").write_text(step, encoding="utf-8")    # split, but no marks yet
            with contextlib.redirect_stderr(io.StringIO()) as err:      # a worktree from before the marks
                self.assertEqual(after.quick_checks(tmp), after.quick_checks(str(ROOT)))
            self.assertIn("ran the checks", err.getvalue())
            after.HOME = tmp
            self.assertRaises(after.NotMarked, after.quick_checks, tmp)

    def test_real_signal_coordinator_edit_runs_its_own_test_files(self) -> None:
        after = load(ROOT / ".claude/hooks/check_after_edit.py", "hart_check_after_edit_real_test")
        tests = after.matching_tests(str(ROOT), "jmri/scripts/signal_coordinator.py")
        self.assertIn("jmri/layouts/hart/scripts/tests/test_signal_coordinator_behaviour.py", tests)
        sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
        from hartlib import coordinator
        for path in coordinator.files():    # an edit to the script or a module it loads is checked, by its tests
            rel = path.relative_to(ROOT).as_posix()
            self.assertTrue(after.WATCHED.search(rel), path.name)
            checks, _note = after.checks_for(str(ROOT), rel)
            self.assertIn("unit jmri/layouts/hart/scripts/tests/test_signal_coordinator_behaviour.py",
                          [name for name, _argv in checks], path.name)
        check_sh = (ROOT / "tools/check.sh").read_text(encoding="utf-8")
        for folder in after.TEST_DIRS:  # each searched folder is a unit job of check.sh, so nothing only runs here
            self.assertIn(f"python3 -m unittest discover -b -q -s {folder}\n", check_sh, folder)

    def test_real_name_check_loads_and_passes_clean_text(self) -> None:
        guard = load(MAIN_GUARD, "hart_main_guard_real_name_test")
        self.assertFalse(guard.contains_private_name("a clean commit message about masts"))


if __name__ == "__main__":
    unittest.main()
