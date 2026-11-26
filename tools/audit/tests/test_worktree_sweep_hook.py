""".claude/hooks/worktree_sweep.py: the sweep's lines reach the session context, and a sweep that fails, cannot
start or runs out of time is one line there too. A fake tools/agent/worktrees.py stands in for the sweep."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("worktree_sweep_hook_test", ROOT / ".claude/hooks/worktree_sweep.py")
HOOK = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = HOOK
_spec.loader.exec_module(HOOK)


class SweepLines(unittest.TestCase):
    def project(self, body: str) -> str:
        """A project folder whose sweep script runs ``body``."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        script = Path(tmp.name) / "tools/agent/worktrees.py"
        script.parent.mkdir(parents=True)
        script.write_text(f"import sys, time\n{body}\n", encoding="utf-8")
        return tmp.name

    def test_removed_and_kept_lines_come_under_a_heading(self) -> None:
        project = self.project('print("removed a"); print("noise"); print("kept b")')
        self.assertEqual(HOOK.sweep_lines(project, project), ["Worktree sweep:", "removed a", "kept b"])

    def test_nothing_to_say_is_no_line(self) -> None:
        project = self.project("pass")
        self.assertEqual(HOOK.sweep_lines(project, project), [])

    def test_a_failure_is_one_line_with_its_last_error(self) -> None:
        project = self.project('print("removed a"); sys.stderr.write("Traceback\\nOSError: disk full\\n"); sys.exit(1)')
        self.assertEqual(HOOK.sweep_lines(project, project),
                         ["Worktree sweep:", "removed a", "Worktree sweep failed: OSError: disk full; run make wt-sweep"])

    def test_a_silent_failure_names_the_exit_code(self) -> None:
        project = self.project("sys.exit(3)")
        self.assertEqual(HOOK.sweep_lines(project, project),
                         ["Worktree sweep:", "Worktree sweep failed: exit 3; run make wt-sweep"])

    def test_a_timeout_is_one_line(self) -> None:
        project = self.project("time.sleep(5)")
        old = HOOK.TIMEOUT
        HOOK.TIMEOUT = 0.5
        self.addCleanup(setattr, HOOK, "TIMEOUT", old)
        self.assertEqual(HOOK.sweep_lines(project, project),
                         ["Worktree sweep took over 0.5 s and was stopped; run make wt-sweep"])

    def test_a_checkout_without_the_script_has_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(HOOK.sweep_lines(tmp, tmp), [])


if __name__ == "__main__":
    unittest.main()
