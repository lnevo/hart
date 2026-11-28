"""tools/agent/worktrees.py: a merged worktree with commits after the merged head goes only when each of those
commits is already on origin/main, and kept lines say "kept" (needs a look) or "waiting" (clears by itself).

Temporary repos stand in for hart, origin/main is a local ref, and GitHub is a dict of merged PR heads."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses look the module up by name
    spec.loader.exec_module(mod)
    return mod


WT = _load("hart_worktrees_extras_test", ROOT / "tools/agent/worktrees.py")
MERGED_AT = "2026-01-01T12:00:00Z"


# Commits are dated long ago, so the grace period (counted from the merge or the last commit) has passed.
DATED = {**os.environ, "GIT_AUTHOR_DATE": "2026-01-01T12:00:00Z", "GIT_COMMITTER_DATE": "2026-01-01T12:00:00Z"}


def git(*args: str, cwd: str) -> str:
    return subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True, text=True,
                          env=DATED).stdout.strip()


class Extras(unittest.TestCase):
    """main has a worktree on agent/claude/x whose PR (one commit) was merged into main with a merge commit."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = os.path.realpath(tmp.name)
        self.main, self.wt = f"{base}/repo", f"{base}/wt"
        os.makedirs(self.main)
        git("init", "-q", "-b", "main", cwd=self.main)
        git("config", "user.email", "t@example.invalid", cwd=self.main)
        git("config", "user.name", "t", cwd=self.main)
        git("commit", "-q", "--allow-empty", "-m", "init", cwd=self.main)
        git("worktree", "add", "-q", "-b", "agent/claude/x", self.wt, cwd=self.main)
        self.commit(self.wt, "a.txt")
        self.pr_head = git("rev-parse", "HEAD", cwd=self.wt)
        git("merge", "-q", "--no-ff", "agent/claude/x", "-m", "merge PR", cwd=self.main)
        self.sync()

    def commit(self, cwd: str, name: str) -> str:
        Path(cwd, name).write_text(f"{name}\n", encoding="utf-8")
        git("add", name, cwd=cwd)
        git("commit", "-q", "-m", name, cwd=cwd)
        return git("rev-parse", "HEAD", cwd=cwd)

    def sync(self) -> None:
        git("update-ref", "refs/remotes/origin/main", "main", cwd=self.main)

    def tree(self) -> Any:  # a WT.Worktree; WT is loaded by path, so mypy cannot name it
        return next(t for t in WT.worktrees(self.main) if t.path == self.wt)

    def prs(self) -> list[dict]:
        return [{"headRefOid": self.pr_head, "mergedAt": MERGED_AT}]

    def sweep_lines(self, dry_run: bool = True) -> list[str]:
        by_branch = {"agent/claude/x": self.prs()}
        with mock.patch.object(WT, "ROOT", Path(self.main)), \
                mock.patch.object(WT, "merged_by_branch", lambda main, limit=1000: by_branch), \
                mock.patch.object(WT.shutil, "which", lambda name: "/usr/bin/gh"):
            return WT.sweep(dry_run=dry_run)

    def test_a_later_commit_whose_patch_is_on_main_lets_it_go(self) -> None:
        extra = self.commit(self.wt, "b.txt")
        git("cherry-pick", extra, cwd=self.main)
        self.sync()
        self.assertEqual(WT.extras_on_base(self.main, self.pr_head, extra, "origin/main"), 0)
        self.assertIsNotNone(WT.merged_at(self.tree(), self.main, self.prs(), base="origin/main"))
        lines = self.sweep_lines(dry_run=False)
        self.assertTrue(lines and lines[0].startswith("removed"), lines)
        self.assertFalse(os.path.exists(self.wt))

    def test_a_later_commit_not_on_main_keeps_it_and_says_how_many(self) -> None:
        self.commit(self.wt, "b.txt")
        self.assertIsNone(WT.merged_at(self.tree(), self.main, self.prs(), base="origin/main"))
        lines = self.sweep_lines()
        self.assertEqual(lines, [f"kept {self.wt} (agent/claude/x): its PR is merged, but 1 commit(s) after the "
                                 "merged head are not on origin/main"])

    def test_a_branch_that_merged_main_back_after_the_pick_lets_it_go(self) -> None:
        extra = self.commit(self.wt, "b.txt")
        git("cherry-pick", extra, cwd=self.main)
        self.commit(self.main, "c.txt")
        self.sync()
        git("merge", "-q", "origin/main", "-m", "merge main back", cwd=self.wt)
        head = git("rev-parse", "HEAD", cwd=self.wt)
        self.assertEqual(WT.extras_on_base(self.main, self.pr_head, head, "origin/main"), 0)

    def test_a_merge_with_work_of_its_own_keeps_it(self) -> None:
        self.commit(self.main, "c.txt")
        self.sync()
        git("merge", "-q", "--no-commit", "origin/main", cwd=self.wt)
        Path(self.wt, "own.txt").write_text("own\n", encoding="utf-8")
        git("add", "own.txt", cwd=self.wt)
        git("commit", "-q", "-m", "merge main back, with a file of its own", cwd=self.wt)
        head = git("rev-parse", "HEAD", cwd=self.wt)
        self.assertEqual(WT.extras_on_base(self.main, self.pr_head, head, "origin/main"), 1)

    def test_a_pr_head_that_is_no_ancestor_counts_nothing(self) -> None:
        other = self.commit(self.main, "c.txt")
        self.assertIsNone(WT.extras_on_base(self.main, other, self.pr_head, "main"))

    def test_uncommitted_changes_keep_it_even_when_the_commits_are_on_main(self) -> None:
        extra = self.commit(self.wt, "b.txt")
        git("cherry-pick", extra, cwd=self.main)
        self.sync()
        Path(self.wt, "loose.txt").write_text("x\n", encoding="utf-8")
        lines = self.sweep_lines(dry_run=False)
        self.assertTrue(lines[0].startswith("kept") and "uncommitted" in lines[0], lines)
        self.assertTrue(os.path.isdir(self.wt))

    def test_a_live_sessions_lock_is_waiting_not_kept(self) -> None:
        git("worktree", "lock", "--reason", f"claude agent agent-x (pid {os.getpid()})", self.wt, cwd=self.main)
        lines = self.sweep_lines(dry_run=False)
        self.assertEqual(lines, [f"waiting {self.wt} (agent/claude/x): locked"])
        self.assertTrue(os.path.isdir(self.wt))


class DetachedWait(unittest.TestCase):
    def test_a_detached_worktree_waits_one_day(self) -> None:
        self.assertEqual(WT.DETACHED_IDLE, timedelta(days=1))
        self.assertIsInstance(WT.Waiting("locked"), str)


if __name__ == "__main__":
    unittest.main()
