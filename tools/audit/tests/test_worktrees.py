"""Agent worktrees: the sweep removes only merged, clean worktrees; the main checkout stays on main.

Temporary repos stand in for hart; GitHub is replaced by a dict of merged PR heads, so
nothing here touches the network or the real worktrees.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look the module up by name
    spec.loader.exec_module(module)
    return module


WT = load(ROOT / "tools/agent/worktrees.py", "hart_worktrees_test")


def sh(*args: str, cwd: str) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class Repo(unittest.TestCase):
    """A repo that uses agent worktrees (it holds tools/agent/worktrees.py) plus one worktree."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.main = os.path.realpath(tmp.name) + "/repo"
        os.makedirs(self.main + "/tools/agent")
        sh("git", "init", "-q", "-b", "main", self.main, cwd=tmp.name)
        sh("git", "config", "user.email", "t@example.invalid", cwd=self.main)
        sh("git", "config", "user.name", "t", cwd=self.main)
        Path(self.main, "tools/agent/worktrees.py").write_text("# marker\n")
        Path(self.main, ".gitignore").write_text("local.txt\n")
        sh("git", "add", ".", cwd=self.main)
        sh("git", "commit", "-q", "-m", "init", cwd=self.main)
        self.wt = os.path.realpath(tmp.name) + "/wt"
        sh("git", "worktree", "add", "-q", "-b", "agent/claude/x", self.wt, cwd=self.main)
        Path(self.wt, "f.txt").write_text("work\n")
        sh("git", "add", "f.txt", cwd=self.wt)
        sh("git", "commit", "-q", "-m", "work", cwd=self.wt)
        self.head = sh("git", "rev-parse", "HEAD", cwd=self.wt)


class Plan(Repo):
    def trees(self):
        return WT.worktrees(self.main)

    def test_merged_clean_worktree_is_removed(self) -> None:
        remove, kept = WT.plan(self.trees(), {"agent/claude/x": {self.head}}, None, WT.is_dirty)
        self.assertEqual([t.path for t in remove], [self.wt])
        self.assertEqual(kept, [])

    def test_unmerged_or_moved_on_worktree_is_kept(self) -> None:
        for heads in ({}, {"agent/claude/x": {"0" * 40}}, {"other": {self.head}}):
            remove, _ = WT.plan(self.trees(), heads, None, WT.is_dirty)
            self.assertEqual(remove, [], heads)

    def test_dirty_or_own_worktree_is_kept(self) -> None:
        heads = {"agent/claude/x": {self.head}}
        Path(self.wt, "new.txt").write_text("unsaved\n")
        remove, kept = WT.plan(self.trees(), heads, None, WT.is_dirty)
        self.assertEqual((remove, len(kept)), ([], 1))
        os.remove(Path(self.wt, "new.txt"))
        remove, kept = WT.plan(self.trees(), heads, self.wt + "/sub", WT.is_dirty)
        self.assertEqual((remove, len(kept)), ([], 1))

    def test_main_checkout_is_never_planned(self) -> None:
        main_head = sh("git", "rev-parse", "HEAD", cwd=self.main)
        remove, _ = WT.plan(self.trees(), {"main": {main_head}}, None, WT.is_dirty)
        self.assertEqual(remove, [])


class Sweep(Repo):
    def test_sweep_removes_worktree_and_branch(self) -> None:
        saved = (WT.ROOT, WT.merged_heads)
        WT.ROOT, WT.merged_heads = Path(self.main), lambda: {"agent/claude/x": {self.head}}
        try:
            lines = WT.sweep()
        finally:
            WT.ROOT, WT.merged_heads = saved
        self.assertTrue(lines[0].startswith("removed"), lines)
        self.assertFalse(os.path.exists(self.wt))
        self.assertEqual(sh("git", "branch", "--list", "agent/claude/x", cwd=self.main), "")

    def test_sweep_does_nothing_without_github(self) -> None:
        saved = (WT.ROOT, WT.merged_heads)
        WT.ROOT, WT.merged_heads = Path(self.main), lambda: None
        try:
            lines = WT.sweep()
        finally:
            WT.ROOT, WT.merged_heads = saved
        self.assertIn("skipped", lines[0])
        self.assertTrue(os.path.exists(self.wt))


class New(Repo):
    def test_new_worktree_is_on_an_agent_branch_and_clean(self) -> None:
        origin = self.main + "-origin.git"
        sh("git", "clone", "-q", "--bare", self.main, origin, cwd=self.main)
        sh("git", "remote", "add", "origin", origin, cwd=self.main)
        os.makedirs(self.main + "/ops/hart-ops/.venv")  # a gitignored mirror to link
        saved = WT.ROOT
        WT.ROOT = Path(self.main)
        try:
            path = WT.new("probe", "claude")
            with self.assertRaises(SystemExit):
                WT.new("Bad Topic", "claude")
        finally:
            WT.ROOT = saved
        self.assertEqual(path, Path(self.main, ".claude/worktrees/probe"))
        self.assertEqual(sh("git", "branch", "--show-current", cwd=str(path)), "agent/claude/probe")
        self.assertTrue(Path(path, "ops/hart-ops/.venv").is_symlink())
        self.assertEqual(sh("git", "status", "--porcelain", cwd=str(path)), "")


class MainCheckoutRules(Repo):
    def guard(self, hook: str, payload: dict, cwd: str) -> int:
        payload = dict(payload, cwd=cwd)
        env = dict(os.environ, CLAUDE_PROJECT_DIR=cwd, HART_GUARD_JMRI_RUNNING="0")
        done = subprocess.run([sys.executable, str(ROOT / ".claude/hooks" / hook)], input=json.dumps(payload),
                              capture_output=True, text=True, env=env)
        return done.returncode

    def bash(self, command: str, cwd: str) -> int:
        return self.guard("main_guard.py", {"tool_input": {"command": command}}, cwd)

    def edit(self, path: str, cwd: str) -> int:
        return self.guard("edit_guard.py", {"tool_input": {"file_path": path}}, cwd)

    def test_main_checkout_blocks_commits_and_branch_moves(self) -> None:
        for cmd in ("git commit -m x", "git switch -c agent/claude/y", "git checkout -b y",
                    "git switch agent/claude/x", "git checkout agent/claude/x", f"git checkout {self.head[:8]}"):
            self.assertEqual(self.bash(cmd, self.main), 2, cmd)

    def test_main_checkout_allows_staying_on_main(self) -> None:
        for cmd in ("git checkout main", "git switch main", "git checkout -- f.txt", "git pull --ff-only",
                    "git status", f"git worktree add ../wt2 -b agent/claude/z"):
            self.assertEqual(self.bash(cmd, self.main), 0, cmd)

    def test_worktree_commits_and_branches_pass(self) -> None:
        for cmd in ("git commit -m x", "git switch -c agent/claude/y"):
            self.assertEqual(self.bash(cmd, self.wt), 0, cmd)

    def test_edits_blocked_in_main_checkout_only(self) -> None:
        self.assertEqual(self.edit(self.main + "/notes.md", self.main), 2)
        self.assertEqual(self.edit(self.main + "/new/dir/file.py", self.main), 2)
        self.assertEqual(self.edit(self.main + "/local.txt", self.main), 0)  # gitignored
        self.assertEqual(self.edit(self.wt + "/notes.md", self.main), 0)
        with tempfile.TemporaryDirectory() as other:
            self.assertEqual(self.edit(other + "/x.md", other), 0)


if __name__ == "__main__":
    unittest.main()
