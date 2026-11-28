""".claude/hooks/worktree_sweep.py: the sweep's and the progress prune's lines become one summary line in the
session context and go in full to a log; a sweep that fails, cannot start or runs out of time is one line too, and
the memory folder check gives at most one warning line. Fake tools/agent/ scripts stand in for the sweep and the
prune."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[3]


def _load(name: str, path: Path) -> ModuleType:
    """The module at `path`, loaded by path under `name`."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


HOOK = _load("worktree_sweep_hook_test", ROOT / ".claude/hooks/worktree_sweep.py")


class SweepLines(unittest.TestCase):
    def project(self, body: str) -> str:
        """A project folder whose sweep script runs ``body``."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        script = Path(tmp.name) / "tools/agent/worktrees.py"
        script.parent.mkdir(parents=True)
        script.write_text(f"import sys, time\n{body}\n", encoding="utf-8")
        return tmp.name

    def test_removed_kept_and_waiting_lines_are_kept_and_noise_dropped(self) -> None:
        project = self.project('print("removed a"); print("noise"); print("kept b"); print("waiting c")')
        self.assertEqual(HOOK.sweep_lines(project, project), HOOK.Lines(["removed a", "kept b", "waiting c"], []))

    def test_nothing_to_say_is_no_line(self) -> None:
        project = self.project("pass")
        self.assertEqual(HOOK.sweep_lines(project, project), HOOK.Lines([], []))

    def test_a_failure_is_one_line_with_its_last_error(self) -> None:
        project = self.project('print("removed a"); sys.stderr.write("Traceback\\nOSError: disk full\\n"); sys.exit(1)')
        self.assertEqual(HOOK.sweep_lines(project, project),
                         HOOK.Lines(["removed a"], ["Worktree sweep failed: OSError: disk full; run make wt-sweep"]))

    def test_a_silent_failure_names_the_exit_code(self) -> None:
        project = self.project("sys.exit(3)")
        self.assertEqual(HOOK.sweep_lines(project, project),
                         HOOK.Lines([], ["Worktree sweep failed: exit 3; run make wt-sweep"]))

    def test_a_timeout_is_one_line(self) -> None:
        project = self.project("time.sleep(5)")
        with mock.patch.object(HOOK, "TIMEOUT", 0.5):
            lines = HOOK.sweep_lines(project, project)
        self.assertEqual(lines, HOOK.Lines([], ["Worktree sweep took over 0.5 s and was stopped; run make wt-sweep"]))

    def test_a_checkout_without_the_script_has_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(HOOK.sweep_lines(tmp, tmp), HOOK.Lines([], []))


class Report(unittest.TestCase):
    """The sweep and prune lines become one summary line that names only the worktrees needing a look."""

    def log(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name) / "logs" / "sweep.log"

    def test_one_line_names_only_what_needs_a_look_and_the_log_has_every_line(self) -> None:
        swept = HOOK.Lines(["removed /w/a (agent/claude/a, PR merged)",
                            "kept /w/b (agent/claude/b): merged, but has uncommitted or untracked changes",
                            "waiting /w/c (agent/claude/c): locked",
                            "kept /w/d: git worktree remove refused: busy"], [])
        pruned = HOOK.Lines(["archived /p/x.md to /p/archive/2026-11-25"], [])
        log = self.log()
        lines = HOOK.report(swept, pruned, log)
        self.assertEqual(lines, [f"Worktree sweep: removed 1, kept 3 (2 need a look: b, d); progress files archived 1; "
                                 f"details: {log}"])
        self.assertEqual(log.read_text(encoding="utf-8").splitlines()[1:], swept.details + pruned.details)

    def test_problems_follow_the_summary_and_stand_alone_when_nothing_else_was_said(self) -> None:
        problem = "Worktree sweep failed: exit 3; run make wt-sweep"
        self.assertEqual(HOOK.report(HOOK.Lines([], [problem]), HOOK.Lines([], []), self.log()), [problem])
        lines = HOOK.report(HOOK.Lines(["left 2 merged worktree(s) for the next sweep"], [problem]),
                            HOOK.Lines([], []), self.log())
        self.assertEqual(len(lines), 2)
        self.assertIn("some left for the next sweep", lines[0])
        self.assertEqual(lines[1], problem)

    def test_a_quiet_run_says_nothing(self) -> None:
        self.assertEqual(HOOK.report(HOOK.Lines([], []), HOOK.Lines([], []), self.log()), [])


class PruneLines(unittest.TestCase):
    def run_prune(self, body: str) -> Any:  # a HOOK.Lines; HOOK is loaded by path, so mypy cannot name it
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        script = Path(tmp.name) / HOOK.PRUNE_SCRIPT
        script.parent.mkdir(parents=True)
        script.write_text(f"import sys, time\n{body}\n", encoding="utf-8")
        started = HOOK.start_prune(tmp.name)
        assert started is not None
        return HOOK.prune_lines(*started)

    def test_archived_lines_are_kept(self) -> None:
        self.assertEqual(self.run_prune('print("archived x"); print("noise")'), HOOK.Lines(["archived x"], []))

    def test_a_failure_and_a_timeout_are_one_line(self) -> None:
        failed = self.run_prune('sys.stderr.write("error: gh pr list failed\\n"); sys.exit(1)')
        self.assertEqual(failed.problems, [f"Progress files not pruned: error: gh pr list failed; run python3 "
                                           f"{HOOK.PRUNE_SCRIPT}"])
        with mock.patch.object(HOOK, "PRUNE_TIMEOUT", 0.5):
            slow = self.run_prune("time.sleep(5)")
        self.assertEqual(slow.problems, [f"Progress prune took over 0.5 s and was stopped; run python3 "
                                         f"{HOOK.PRUNE_SCRIPT}"])

    def test_a_checkout_without_the_script_starts_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(HOOK.start_prune(tmp))


class Memory(unittest.TestCase):
    """The memory check reads a temporary folder only, never the real one."""

    def folder(self, files: dict[str, str]) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for name, text in files.items():
            Path(tmp.name, name).write_text(text, encoding="utf-8")
        return Path(tmp.name)

    def test_a_tidy_folder_and_a_missing_one_say_nothing(self) -> None:
        tidy = self.folder({"MEMORY.md": "- [A](a.md) — x\n", "a.md": "see [[a]]\n"})
        self.assertEqual(HOOK.memory_line(tidy), [])
        self.assertEqual(HOOK.memory_line(tidy / "gone"), [])

    def test_every_problem_is_in_one_line(self) -> None:
        files = {f"m{i}.md": "" for i in range(41)}
        files["m0.md"] = "[[nowhere]]"
        files["MEMORY.md"] = "".join(f"- [M](m{i}.md)\n" for i in range(40)) + "- [Gone](gone.md)\n"
        lines = HOOK.memory_line(self.folder(files))
        self.assertEqual(lines, ["Memory: 41 files (cap 40), 1 dangling link(s) [[nowhere]], 1 MEMORY.md entry with "
                                 "no file: gone.md, 1 file(s) not in MEMORY.md: m40.md; move rulings into the skill "
                                 "or wiki they govern."])

    def test_the_folder_follows_the_main_checkout_and_the_env_var_overrides_it(self) -> None:
        with mock.patch.dict(os.environ, {HOOK.MEMORY_ENV: "/elsewhere/memory"}):
            self.assertEqual(HOOK.memory_folder("/any"), Path("/elsewhere/memory"))
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {HOOK.MEMORY_ENV: ""}):
            real = Path(tmp).resolve()
            slug = str(real).replace("/", "-").replace(".", "-").replace("_", "-")
            self.assertEqual(HOOK.memory_folder(tmp), Path.home() / ".claude" / "projects" / slug / "memory")


if __name__ == "__main__":
    unittest.main()
