"""tools/agent/worktree_rules.py through the sweep: a worktree that holds nothing beyond origin/main goes once it is
clean and idle, PR or not; one with work of its own, a stopped merge, an open PR or a live session's lock stays.

Temporary repos stand in for hart; GitHub is replaced (no merged PRs, a canned set of open PR branches), so nothing
here touches the network or the real worktrees.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look the module up by name
    spec.loader.exec_module(module)
    return module


WT = load(ROOT / "tools/agent/worktrees.py", "hart_worktrees_rules_test")
import worktree_rules as RULES  # noqa: E402  (worktrees.py put its folder on sys.path)

HOUR = 3600


def sh(*args: str, cwd: str) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class NothingUnique(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = os.path.realpath(tmp.name)
        self.main = self.base + "/repo"
        os.makedirs(self.main)
        sh("git", "init", "-q", "-b", "main", self.main, cwd=self.base)
        sh("git", "config", "user.email", "t@example.invalid", cwd=self.main)
        sh("git", "config", "user.name", "t", cwd=self.main)
        Path(self.main, "a.txt").write_text("a\n")
        sh("git", "add", ".", cwd=self.main)
        sh("git", "commit", "-q", "-m", "init", cwd=self.main)
        sh("git", "update-ref", "refs/remotes/origin/main", "main", cwd=self.main)
        self.open: frozenset[str] | None = frozenset()

    def tree(self, name: str, branch: str | None = None, idle_hours: float = 2) -> str:
        path = f"{self.main}/.claude/worktrees/{name}"
        sh("git", "worktree", "add", "-q", *(["-b", branch] if branch else ["--detach"]), path, "origin/main",
           cwd=self.main)
        self.age(path, idle_hours)
        return path

    def age(self, path: str, hours: float) -> None:
        index = sh("git", "rev-parse", "--path-format=absolute", "--git-path", "index", cwd=path)
        stamp = time.time() - hours * HOUR
        os.utime(index, (stamp, stamp))

    def sweep(self, dry_run: bool = False) -> list[str]:
        with mock.patch.object(WT, "merged_by_branch", lambda main, limit=1000: {}), \
                mock.patch.object(WT, "open_branches", lambda main, limit=1000: self.open):
            return WT.sweep_repo(self.main, WT.worktrees(self.main), dry_run, [], None, WT.Clock(), "main", None, None)

    def test_a_clean_agent_worktree_on_main_is_removed_with_its_branch(self) -> None:
        path = self.tree("agent-a1", "agent/claude/done-lane")
        lines = self.sweep()
        self.assertIn(f"removed {path} (agent/claude/done-lane, nothing beyond origin/main, untouched 1 hour(s))",
                      lines)
        self.assertFalse(os.path.isdir(path))
        self.assertIsNone(WT.branch_head("agent/claude/done-lane", self.main))

    def test_dry_run_names_it_and_removes_nothing(self) -> None:
        path = self.tree("agent-a2", "agent/claude/x")
        self.assertIn(f"would remove {path} (agent/claude/x)", self.sweep(dry_run=True))
        self.assertTrue(os.path.isdir(path))

    def test_dirty_or_untracked_changes_keep_it(self) -> None:
        edited, untracked = self.tree("agent-b1", "agent/claude/b1"), self.tree("agent-b2", "agent/claude/b2")
        Path(edited, "a.txt").write_text("changed\n")
        Path(untracked, "new.txt").write_text("new\n")
        self.age(edited, 2)
        self.age(untracked, 2)
        self.sweep()
        self.assertTrue(os.path.isdir(edited) and os.path.isdir(untracked))

    def test_a_commit_of_its_own_keeps_it(self) -> None:
        path = self.tree("agent-c1", "agent/claude/c1")
        sh("git", "commit", "-q", "--allow-empty", "-m", "mine", cwd=path)
        self.age(path, 2)
        self.sweep()
        self.assertTrue(os.path.isdir(path))

    def test_a_live_sessions_lock_keeps_it(self) -> None:
        path = self.tree("agent-d1", "agent/claude/d1")
        sh("git", "worktree", "lock", "--reason", f"claude agent d1 (pid {os.getpid()})", path, cwd=self.main)
        self.assertIn(f"waiting {path} (agent/claude/d1): locked", self.sweep())
        self.assertTrue(os.path.isdir(path))

    def test_an_open_pr_or_no_answer_from_github_keeps_it(self) -> None:
        path = self.tree("agent-e1", "agent/claude/e1")
        for answer in (frozenset({"agent/claude/e1"}), None):
            self.open = answer
            self.sweep()
            self.assertTrue(os.path.isdir(path), answer)

    def test_a_stopped_merge_keeps_it(self) -> None:
        path = self.tree("agent-f1", "agent/claude/f1")
        gitdir = sh("git", "rev-parse", "--path-format=absolute", "--git-dir", cwd=path)
        Path(gitdir, "MERGE_HEAD").write_text("0" * 40 + "\n")
        self.sweep()
        self.assertTrue(os.path.isdir(path))

    def test_age_thresholds_one_hour_for_agent_worktrees_one_day_for_others(self) -> None:
        fresh_agent = self.tree("agent-g1", "agent/claude/g1", idle_hours=0.5)
        old_agent = self.tree("agent-g2", "agent/claude/g2", idle_hours=1.1)
        topic = self.tree("my-topic", "agent/claude/my-topic", idle_hours=23)
        old_topic = self.tree("old-topic", "agent/claude/old-topic", idle_hours=25)
        self.sweep()
        self.assertEqual([os.path.isdir(p) for p in (fresh_agent, old_agent, topic, old_topic)],
                         [True, False, True, False])

    def test_a_detached_agent_worktree_on_main_goes_after_an_hour(self) -> None:
        path = self.tree("agent-h1", None, idle_hours=2)
        lines = self.sweep()
        self.assertFalse(os.path.isdir(path), lines)
        self.assertTrue(any(l.startswith(f"removed {path}") and "nothing beyond origin/main" in l for l in lines))

    def test_the_main_checkout_is_never_removed(self) -> None:
        self.age(self.main, 48)
        self.sweep()
        self.assertTrue(os.path.isdir(self.main + "/.git"))


class Rule(unittest.TestCase):
    """nothing_unique_since on its own: each read is made only when the earlier ones pass."""

    NOW = datetime(2026, 11, 28, 12, 0, tzinfo=timezone.utc)

    def probe(self, on_base=True, stopped=False, idle=timedelta(hours=2), dirty=False) -> RULES.Probe:
        return RULES.Probe(lambda: on_base, lambda: stopped, lambda: self.NOW - idle, lambda: dirty)

    def test_github_is_asked_only_for_a_branch_that_got_that_far(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "agent-x")
            os.mkdir(path)
            asked: list[int] = []

            def opened() -> frozenset[str]:
                asked.append(1)
                return frozenset()
            self.assertIsNone(RULES.nothing_unique_since(path, "b", self.probe(on_base=False), opened, self.NOW))
            self.assertIsNone(RULES.nothing_unique_since(path, "b", self.probe(idle=timedelta(minutes=5)), opened,
                                                         self.NOW))
            self.assertEqual(asked, [])
            self.assertEqual(RULES.nothing_unique_since(path, "b", self.probe(), opened, self.NOW),
                             self.NOW - timedelta(hours=2))
            self.assertEqual(asked, [1])
            self.assertIsNone(RULES.nothing_unique_since(path, "b", self.probe(dirty=True), opened, self.NOW))

    def test_idle_limit_and_words(self) -> None:
        self.assertEqual(RULES.idle_limit("/r/.claude/worktrees/agent-abc/"), RULES.IDLE_AGENT)
        self.assertEqual(RULES.idle_limit("/r/.claude/worktrees/ux-lane"), RULES.IDLE_OTHER)
        self.assertEqual(RULES.idle_words("/x/agent-1"), "1 hour(s)")
        self.assertEqual(RULES.idle_words("/x/topic"), "1 day(s)")

    def test_open_branches_from_gh(self) -> None:
        done = subprocess.CompletedProcess([], 0, '[{"headRefName": "agent/claude/a"}]', "")
        with mock.patch.object(RULES.subprocess, "run", return_value=done):
            self.assertEqual(RULES.open_branches("/r"), frozenset({"agent/claude/a"}))
            self.assertIsNone(RULES.open_branches("/r", limit=1), "a full list may hide a branch")
        with mock.patch.object(RULES.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "x")):
            self.assertIsNone(RULES.open_branches("/r"))
        with mock.patch.object(RULES.subprocess, "run", side_effect=OSError("no gh")):
            self.assertIsNone(RULES.open_branches("/r"))


if __name__ == "__main__":
    unittest.main()
