"""Agent worktrees: the sweep removes only merged, clean worktrees; the main checkout stays on main.

Temporary repos stand in for hart; GitHub is replaced by a dict of merged PR heads, so
nothing here touches the network or the real worktrees.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from contextlib import redirect_stderr
from datetime import datetime, timedelta, timezone
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


LONG_AGO = datetime(2026, 1, 1, tzinfo=timezone.utc)


class GitErrors(unittest.TestCase):
    """git() raises GitCommandError with the command and stderr; callers that expect a failure say what it means."""

    def test_failure_names_command_folder_and_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(WT.GitCommandError, r"git status --porcelain failed in .*not a git repository"):
                WT.git("status", "--porcelain", cwd=tmp)

    def test_timeout_and_missing_git_keep_their_cause(self) -> None:
        for err in (subprocess.TimeoutExpired("git", 60), FileNotFoundError("git")):
            with mock.patch.object(WT.subprocess, "run", side_effect=err):
                with self.assertRaises(WT.GitCommandError) as caught:
                    WT.git("status")
            self.assertIs(caught.exception.__cause__, err)

    def test_unreadable_checkout_counts_as_dirty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(WT.is_dirty(tmp))

    def test_unset_default_branch_and_missing_branch_are_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(WT.default_branch(tmp))
            self.assertIsNone(WT.branch_head("agent/x", tmp))

    def test_main_prints_one_error_line(self) -> None:
        err = io.StringIO()
        with mock.patch.object(WT, "worktrees", side_effect=WT.GitCommandError("git worktree list failed in /x: boom")), \
                redirect_stderr(err):
            self.assertEqual(WT.main(["sweep", "--dry-run"]), 1)
        self.assertEqual(err.getvalue(), "error: git worktree list failed in /x: boom\n")

    def test_main_reports_a_bad_topic_in_one_line(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(WT.main(["new", "Bad Topic"]), 1)
        self.assertEqual(err.getvalue(),
                         "error: topic must be lower-case letters and digits, words joined by - or _: 'Bad Topic'\n")


class SweepGoesOn(unittest.TestCase):
    """A broken submodule or a failed cleanup after a removal is one line; the sweep carries on."""

    def test_a_broken_submodule_is_left_and_the_next_is_swept(self) -> None:
        main = WT.Worktree("/repo", "abc", "main")

        def trees(cwd=None):
            if cwd == "/repo/sub/a":
                raise WT.GitCommandError("git worktree list --porcelain failed in /repo/sub/a: fatal: broken")
            return [main]
        with mock.patch.object(WT, "worktrees", side_effect=trees), \
                mock.patch.object(WT.shutil, "which", return_value="/bin/gh"), \
                mock.patch.object(WT, "submodule_repos", return_value=["/repo/sub/a", "/repo/sub/b"]), \
                mock.patch.object(WT, "default_branch", return_value="main"), \
                mock.patch.object(WT, "sweep_repo", side_effect=lambda m, *a: [f"swept {m}"]):
            lines = WT.sweep()
        self.assertEqual(lines, [
            "swept /repo",
            "left this submodule for the next sweep: git worktree list --porcelain failed in /repo/sub/a: "
            "fatal: broken [submodule sub/a]",
            "swept /repo/sub/b [submodule sub/b]",
        ])

    def test_a_failed_branch_delete_is_a_note_on_the_removed_line(self) -> None:
        tree = WT.Worktree("/repo/.claude/worktrees/x", "abc", "agent/claude/x")

        def fake_git(*args, cwd=None):
            if args[:2] == ("branch", "-D"):
                raise WT.GitCommandError("git branch -D agent/claude/x failed in /repo: error: locked")
            return ""
        with mock.patch.object(WT, "git", side_effect=fake_git), mock.patch.object(WT, "branch_head", return_value="abc"):
            self.assertEqual(WT.after_removal(tree, "/repo"),
                             ["branch delete failed: git branch -D agent/claude/x failed in /repo: error: locked"])
        with mock.patch.object(WT, "git", side_effect=WT.GitCommandError("git worktree prune failed in /repo: x")), \
                mock.patch.object(WT, "branch_head", return_value=None):
            self.assertEqual(WT.after_removal(tree, "/repo"), ["worktree prune failed: git worktree prune failed in /repo: x"])


class Plan(Repo):
    def trees(self):
        return WT.worktrees(self.main)

    def merged(self, when=LONG_AGO):
        return lambda tree: when if tree.branch == "agent/claude/x" else None

    def test_merged_clean_worktree_is_removed(self) -> None:
        remove, kept = WT.plan(self.trees(), self.merged(), [], WT.is_dirty)
        self.assertEqual([t.path for t in remove], [self.wt])
        self.assertEqual(kept, [])

    def test_open_work_is_not_planned(self) -> None:
        remove, kept = WT.plan(self.trees(), lambda tree: None, [], WT.is_dirty)
        self.assertEqual((remove, kept), ([], []))

    def test_dirty_kept_and_own_or_project_dir_kept(self) -> None:
        Path(self.wt, "new.txt").write_text("unsaved\n")
        remove, kept = WT.plan(self.trees(), self.merged(), [], WT.is_dirty)
        self.assertEqual((remove, len(kept)), ([], 1))
        os.remove(Path(self.wt, "new.txt"))
        for keep in ([self.wt + "/sub"], ["/elsewhere", self.wt]):
            remove, kept = WT.plan(self.trees(), self.merged(), keep, WT.is_dirty)
            self.assertEqual((remove, len(kept)), ([], 1), keep)

    def test_recent_merge_waits_for_the_grace_period(self) -> None:
        now = datetime.now(timezone.utc)
        remove, kept = WT.plan(self.trees(), self.merged(now - timedelta(minutes=5)), [], WT.is_dirty, now)
        self.assertEqual((remove, len(kept)), ([], 1))
        remove, _ = WT.plan(self.trees(), self.merged(now - WT.GRACE - timedelta(minutes=1)), [], WT.is_dirty, now)
        self.assertEqual(len(remove), 1)

    def test_main_checkout_is_never_planned(self) -> None:
        remove, _ = WT.plan(self.trees(), lambda tree: LONG_AGO, [], WT.is_dirty)
        self.assertNotIn(self.main, [t.path for t in remove])


class MergedAt(Repo):
    def tree(self):
        return next(t for t in WT.worktrees(self.main) if t.path == self.wt)

    def pr(self, oid):
        return [{"headRefOid": oid, "mergedAt": "2026-11-10T12:00:00Z"}]

    def test_exact_head_and_descendant_head_count(self) -> None:
        self.assertIsNotNone(WT.merged_at(self.tree(), self.main, self.pr(self.head)))
        # GitHub "Update branch" adds a commit on top before the merge: local HEAD is its ancestor
        sh("git", "commit", "-q", "--allow-empty", "-m", "update", cwd=self.wt)
        later = sh("git", "rev-parse", "HEAD", cwd=self.wt)
        sh("git", "reset", "-q", "--hard", "HEAD~1", cwd=self.wt)
        self.assertIsNotNone(WT.merged_at(self.tree(), self.main, self.pr(later)))

    def test_local_work_after_the_merge_counts_as_open(self) -> None:
        merged = self.head
        sh("git", "commit", "-q", "--allow-empty", "-m", "more", cwd=self.wt)
        self.assertIsNone(WT.merged_at(self.tree(), self.main, self.pr(merged)))
        self.assertIsNone(WT.merged_at(self.tree(), self.main, []))


class Detached(Repo):
    """A detached worktree is judged by whether its commit is on the default branch and how long it sat idle."""

    def setUp(self) -> None:
        super().setUp()
        # origin/main stands in for the default branch: point it at main's commit.
        sh("git", "update-ref", "refs/remotes/origin/main", "main", cwd=self.main)
        self.det = self.wt + "-detached"
        sh("git", "worktree", "add", "-q", "--detach", self.det, "main", cwd=self.main)

    def tree(self):
        return next(t for t in WT.worktrees(self.main) if t.path == self.det)

    def test_idle_detached_on_main_counts_as_merged(self) -> None:
        later = datetime.now(timezone.utc) + WT.DETACHED_IDLE + timedelta(minutes=1)
        self.assertIsNotNone(WT.merged_at(self.tree(), self.main, [], base="origin/main", now=later))

    def test_recent_detached_waits(self) -> None:
        self.assertIsNone(WT.merged_at(self.tree(), self.main, [], base="origin/main"))

    def test_detached_with_its_own_commit_is_never_merged(self) -> None:
        sh("git", "commit", "-q", "--allow-empty", "-m", "local", cwd=self.det)
        later = datetime.now(timezone.utc) + WT.DETACHED_IDLE + timedelta(days=30)
        self.assertIsNone(WT.merged_at(self.tree(), self.main, [], base="origin/main", now=later))
        self.assertIsNone(WT.merged_at(self.tree(), self.main, [], base=None, now=later))

    def test_kept_worktrees_say_why(self) -> None:
        trees = WT.worktrees(self.main)
        why = lambda t: "detached reason" if t.path == self.det else None  # noqa: E731
        remove, kept = WT.plan(trees, lambda t: None, [], WT.is_dirty, why_open=why)
        self.assertEqual(remove, [])
        self.assertEqual([(t.path, r) for t, r in kept], [(self.det, "detached reason")])

    def test_sweep_reports_a_fresh_detached_worktree(self) -> None:
        saved = (WT.ROOT, WT.merged_by_branch)
        WT.ROOT, WT.merged_by_branch = Path(self.wt), lambda main, limit=1000: {}
        try:
            lines = WT.sweep_repo(self.main, WT.worktrees(self.main), False, [], None, WT.Clock(), None, None, None)
        finally:
            WT.ROOT, WT.merged_by_branch = saved
        self.assertTrue(any(self.det in l and "detached" in l for l in lines), lines)

    def test_missing_folder_is_skipped_not_fatal(self) -> None:
        shutil.rmtree(self.det)
        later = datetime.now(timezone.utc) + WT.DETACHED_IDLE + timedelta(minutes=1)
        self.assertIsNone(WT.merged_at(self.tree(), self.main, [], base="origin/main", now=later))

    def test_stopped_operation_keeps_it(self) -> None:
        gitdir = sh("git", "rev-parse", "--path-format=absolute", "--git-dir", cwd=self.det)
        Path(gitdir, "BISECT_LOG").write_text("bisect\n")
        later = datetime.now(timezone.utc) + WT.DETACHED_IDLE + timedelta(minutes=1)
        self.assertIsNone(WT.merged_at(self.tree(), self.main, [], base="origin/main", now=later))


class Sweep(Repo):
    def sweep(self, merged, budget=None, by_branch=None):
        """Sweep with GitHub replaced: `merged(tree)` answers per worktree, or `by_branch` stands in for the batch."""
        saved = (WT.ROOT, WT.merged_at, WT.merged_by_branch)
        WT.ROOT, WT.merged_by_branch = Path(self.wt), lambda main, limit=1000: by_branch
        if merged is not None:
            WT.merged_at = lambda tree, main, prs=None, **kw: merged(tree)
        try:
            return WT.sweep(budget=budget)
        finally:
            WT.ROOT, WT.merged_at, WT.merged_by_branch = saved

    def test_sweep_removes_worktree_and_branch(self) -> None:
        lines = self.sweep(lambda t: LONG_AGO if t.branch == "agent/claude/x" else None)
        self.assertTrue(lines and lines[0].startswith("removed"), lines)
        self.assertFalse(os.path.exists(self.wt))
        self.assertEqual(sh("git", "branch", "--list", "agent/claude/x", cwd=self.main), "")

    def lock(self, reason: str) -> None:
        sh("git", "worktree", "lock", "--reason", reason, self.wt, cwd=self.main)

    def lock_text(self) -> str:
        return next((t.lock_reason for t in WT.worktrees(self.main) if t.path == self.wt and t.locked), "")

    def test_a_dead_sessions_lock_is_lifted_and_the_worktree_removed(self) -> None:
        self.lock("claude agent agent-x (pid 111 start Sat Nov 21 14:25:32 2026)")
        with mock.patch.object(WT, "pid_running", return_value=False), \
                mock.patch.object(WT, "idle_since", return_value=LONG_AGO):
            lines = self.sweep(lambda t: LONG_AGO if t.branch == "agent/claude/x" else None)
        self.assertTrue(lines and lines[0].startswith("removed"), lines)
        self.assertFalse(os.path.exists(self.wt))

    def test_a_live_sessions_lock_keeps_the_worktree(self) -> None:
        self.lock(f"claude agent agent-x (pid {os.getpid()})")
        lines = self.sweep(lambda t: LONG_AGO if t.branch == "agent/claude/x" else None)
        self.assertTrue(os.path.exists(self.wt))
        self.assertTrue(any("locked" in l for l in lines), lines)

    def test_a_refused_removal_puts_the_lock_back(self) -> None:
        reason = "claude agent agent-x (pid 111 start Sat Nov 21 14:25:32 2026)"
        self.lock(reason)
        with mock.patch.object(WT, "pid_running", return_value=False), \
                mock.patch.object(WT, "idle_since", return_value=LONG_AGO), \
                mock.patch.object(WT, "remove_worktree", return_value="refused for the test"):
            lines = self.sweep(lambda t: LONG_AGO if t.branch == "agent/claude/x" else None)
        self.assertTrue(os.path.exists(self.wt))
        self.assertTrue(any("refused for the test" in l for l in lines), lines)
        self.assertEqual(self.lock_text(), reason)

    def add_submodule(self) -> str:
        """Give the worktree a checked-out submodule cloned from a local 'remote' repo; return its path."""
        src = os.path.dirname(self.main) + "/subsrc"
        sh("git", "init", "-q", "-b", "main", src, cwd=os.path.dirname(self.main))
        sh("git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-q", "--allow-empty",
           "-m", "s", cwd=src)
        sh("git", "-c", "protocol.file.allow=always", "submodule", "add", "-q", src, "ext/sub", cwd=self.wt)
        sh("git", "commit", "-q", "-m", "submodule", cwd=self.wt)
        return self.wt + "/ext/sub"

    def test_sweep_removes_a_clean_worktree_with_a_submodule(self) -> None:
        self.add_submodule()
        lines = self.sweep(lambda t: LONG_AGO if t.branch == "agent/claude/x" else None)
        self.assertTrue(lines and lines[0].startswith("removed"), lines)
        self.assertFalse(os.path.exists(self.wt))

    def subcommit(self, sub: str, msg: str) -> None:
        sh("git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-q", "--allow-empty",
           "-m", msg, cwd=sub)

    def assert_kept(self, reason: str) -> None:
        lines = self.sweep(lambda t: LONG_AGO if t.branch == "agent/claude/x" else None)
        self.assertEqual(len(lines), 1, lines)
        self.assertTrue(lines[0].startswith("kept"), lines)
        self.assertIn(reason, lines[0])
        self.assertTrue(os.path.exists(self.wt + "/ext/sub"))

    def test_sweep_keeps_a_submodule_commit_that_is_on_no_remote(self) -> None:
        sub = self.add_submodule()
        self.subcommit(sub, "local only")
        sh("git", "commit", "-q", "-am", "bump", cwd=self.wt)  # the worktree itself stays clean
        self.assert_kept("submodule ext/sub has commits on no remote branch")

    def test_sweep_keeps_an_unpushed_submodule_branch_behind_a_pushed_head(self) -> None:
        sub = self.add_submodule()
        pushed = sh("git", "rev-parse", "HEAD", cwd=sub)
        sh("git", "checkout", "-q", "-b", "side", cwd=sub)
        self.subcommit(sub, "side work")
        sh("git", "checkout", "-q", "--detach", pushed, cwd=sub)  # HEAD back on the remote's commit
        self.assert_kept("submodule ext/sub has commits on no remote branch")

    def test_sweep_keeps_a_submodule_stash(self) -> None:
        sub = self.add_submodule()
        Path(sub, "scratch.txt").write_text("x\n")
        sh("git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", "stash", "push", "-q", "-u", cwd=sub)
        self.assert_kept("submodule ext/sub has a stash")

    def test_other_refusals_are_not_forced(self) -> None:
        self.add_submodule()
        saved = WT.git_run
        WT.git_run = lambda *a, cwd=None: subprocess.CompletedProcess(a, 1, "", "fatal: some other reason")
        try:
            self.assertEqual(WT.remove_worktree(self.wt, self.main), "git worktree remove refused: fatal: some other reason")
        finally:
            WT.git_run = saved
        self.assertTrue(os.path.exists(self.wt))

    def test_spent_budget_leaves_removals_for_the_next_sweep(self) -> None:
        lines = self.sweep(lambda t: LONG_AGO, budget=-1)
        self.assertEqual(len(lines), 1, lines)
        self.assertTrue(lines[0].startswith("left 1 merged worktree(s) for the next sweep"), lines)
        self.assertTrue(os.path.exists(self.wt))

    def test_planning_time_does_not_count_against_the_budget(self) -> None:
        def slow(tree):
            time.sleep(0.3)
            return LONG_AGO
        lines = self.sweep(slow, budget=0.2)
        self.assertTrue(lines and lines[0].startswith("removed"), lines)

    def test_one_batched_answer_feeds_every_worktree(self) -> None:
        self.assertEqual(self.sweep(None, by_branch={}), [])  # no merged PR for the branch: open work
        by_branch = {"agent/claude/x": [{"headRefOid": self.head, "mergedAt": "2026-01-01T00:00:00Z"}]}
        lines = self.sweep(None, by_branch=by_branch)
        self.assertTrue(lines and lines[0].startswith("removed"), lines)

    def test_sweep_keeps_unmerged_worktree(self) -> None:
        self.assertEqual(self.sweep(lambda t: None), [])
        self.assertTrue(os.path.exists(self.wt))

    def test_topic_must_be_a_valid_branch_word(self) -> None:
        for bad in ("fix..ids", "x.lock", "x.", "Bad", "a b", "-x"):
            with self.assertRaises(WT.WorktreeError, msg=bad):
                WT.new(bad, "claude")


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
            with self.assertRaises(WT.WorktreeError):
                WT.new("Bad Topic", "claude")
        finally:
            WT.ROOT = saved
        self.assertEqual(path, Path(self.main, ".claude/worktrees/probe"))
        self.assertEqual(sh("git", "branch", "--show-current", cwd=str(path)), "agent/claude/probe")
        self.assertTrue(Path(path, "ops/hart-ops/.venv").is_symlink())
        self.assertEqual(sh("git", "status", "--porcelain", cwd=str(path)), "")

    def new_with_submodule(self, url_ok: bool) -> tuple[Path, str]:
        """Commit a submodule ext/sub to main, push it to a bare origin, and run new() with it as a check
        submodule; return the new worktree and what new() wrote to stderr."""
        src = os.path.dirname(self.main) + "/subsrc"
        sh("git", "init", "-q", "-b", "main", src, cwd=os.path.dirname(self.main))
        sh("git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-q", "--allow-empty",
           "-m", "s", cwd=src)
        sh("git", "-c", "protocol.file.allow=always", "submodule", "add", "-q", src, "ext/sub", cwd=self.main)
        sh("git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-q", "-m", "sub",
           cwd=self.main)
        origin = self.main + "-origin.git"
        sh("git", "clone", "-q", "--bare", self.main, origin, cwd=self.main)
        sh("git", "remote", "add", "origin", origin, cwd=self.main)
        if not url_ok:
            shutil.rmtree(src)
        n = int(os.environ.get("GIT_CONFIG_COUNT", "0"))  # add to the caller's own config entries, not over them
        env = {"GIT_CONFIG_COUNT": str(n + 1), f"GIT_CONFIG_KEY_{n}": "protocol.file.allow",
               f"GIT_CONFIG_VALUE_{n}": "always"}
        err = io.StringIO()
        with mock.patch.object(WT, "ROOT", Path(self.main)), mock.patch.object(WT, "CHECK_SUBMODULES", ("ext/sub",)), \
                mock.patch.dict(os.environ, env), redirect_stderr(err):
            path = WT.new("probe", "claude")
        return path, err.getvalue()

    def test_new_checks_out_the_check_submodules(self) -> None:
        path, err = self.new_with_submodule(url_ok=True)
        self.assertTrue(Path(path, "ext/sub/.git").exists(), err)
        self.assertEqual(err, "")
        gitdir = sh("git", "rev-parse", "--absolute-git-dir", cwd=str(path) + "/ext/sub")
        self.assertFalse(Path(gitdir, "objects/info/alternates").exists(), "the borrowed objects were not copied in")

    def test_submodules_checks_out_a_missing_one_in_an_existing_worktree(self) -> None:
        path, _ = self.new_with_submodule(url_ok=True)
        sh("git", "submodule", "deinit", "-q", "-f", "ext/sub", cwd=str(path))
        self.assertFalse(Path(path, "ext/sub/.git").exists())
        n = int(os.environ.get("GIT_CONFIG_COUNT", "0"))
        env = {"GIT_CONFIG_COUNT": str(n + 1), f"GIT_CONFIG_KEY_{n}": "protocol.file.allow",
               f"GIT_CONFIG_VALUE_{n}": "always"}
        code, err = self.run_submodules(path, env)
        self.assertEqual(code, 0, err)
        self.assertTrue(Path(path, "ext/sub/.git").exists(), err)
        self.assertEqual(sh("git", "status", "--porcelain", cwd=str(path)), "")
        with mock.patch.object(WT, "init_submodule", side_effect=AssertionError("fetched again")):
            self.assertEqual(self.run_submodules(path, env)[0], 0)  # checked out already: left alone

    def run_submodules(self, path: Path, env: dict) -> tuple[int, str]:
        err = io.StringIO()
        with mock.patch.object(WT, "CHECK_SUBMODULES", ("ext/sub",)), mock.patch.dict(os.environ, env), \
                redirect_stderr(err):
            code = WT.main(["submodules", str(path)])
        return code, err.getvalue()

    def test_submodules_fails_when_the_fetch_fails_or_there_is_no_checkout(self) -> None:
        path, err = self.new_with_submodule(url_ok=False)
        code, err = self.run_submodules(path, {})
        self.assertEqual(code, 1)
        self.assertIn("warning: ext/sub is not checked out", err)
        code, err = self.run_submodules(Path(tempfile.mkdtemp()), {})
        self.assertEqual(code, 1)
        self.assertIn("is not a git checkout", err)

    def test_new_still_makes_the_worktree_when_a_submodule_cannot_be_fetched(self) -> None:
        path, err = self.new_with_submodule(url_ok=False)
        self.assertEqual(sh("git", "branch", "--show-current", cwd=str(path)), "agent/claude/probe")
        self.assertIn("warning: ext/sub is not checked out (fatal:", err)
        self.assertEqual(sh("git", "status", "--porcelain", cwd=str(path)), "")
        self.assertIsNone(WT.submodule_risk(str(path)))


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
                    "git switch agent/claude/x", "git checkout agent/claude/x", f"git checkout {self.head[:8]}",
                    "git checkout -", "git switch -", "git checkout HEAD~1", "git checkout @{-1}",
                    "git checkout FETCH_HEAD", "git checkout main~1", f"git checkout {self.head[:8].upper()}"):
            self.assertEqual(self.bash(cmd, self.main), 2, cmd)

    def test_main_checkout_allows_staying_on_main(self) -> None:
        for cmd in ("git checkout main", "git switch main", "git checkout -- f.txt", "git checkout .gitignore",
                    "git pull --ff-only",
                    "git status", "git worktree add ../wt2 -b agent/claude/z"):
            self.assertEqual(self.bash(cmd, self.main), 0, cmd)

    def test_worktree_commits_and_branches_pass(self) -> None:
        for cmd in ("git commit -m x", "git switch -c agent/claude/y"):
            self.assertEqual(self.bash(cmd, self.wt), 0, cmd)

    def test_edits_blocked_in_main_checkout_only(self) -> None:
        self.assertEqual(self.edit(self.main + "/notes.md", self.main), 2)
        self.assertEqual(self.edit(self.main + "/new/dir/file.py", self.main), 2)
        self.assertEqual(self.edit(self.main + "/local.txt", self.main), 0)  # gitignored
        self.assertEqual(self.edit(self.wt + "/notes.md", self.main), 0)
        os.makedirs(self.main + "/mirror")
        Path(self.main, ".gitignore").write_text("local.txt\n/mirror\n")
        os.symlink(self.main + "/mirror", self.wt + "/mirror")  # a make wt mirror link
        self.assertEqual(self.edit(self.wt + "/mirror/new.png", self.wt), 0)
        with tempfile.TemporaryDirectory() as other:
            self.assertEqual(self.edit(other + "/x.md", other), 0)


SWEEP_NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)


def fake_tree(name, branch="b", locked=False):
    return WT.Worktree(f"/r/{name}", "abc", branch, locked)


class SubmodulePlanTest(unittest.TestCase):
    def run_plan(self, trees, when, keep=(), dirty=()):
        return WT.plan([fake_tree("main", "main")] + trees, lambda t: when.get(t.path), list(keep),
                       lambda p: p in dirty, now=SWEEP_NOW)

    def test_only_old_clean_merged_worktrees_are_removed(self):
        old, fresh, dirty, openw = fake_tree("old"), fake_tree("fresh"), fake_tree("dirty"), fake_tree("open")
        when = {old.path: SWEEP_NOW - timedelta(hours=2), fresh.path: SWEEP_NOW - timedelta(minutes=29),
                dirty.path: SWEEP_NOW - timedelta(hours=2)}
        remove, kept = self.run_plan([old, fresh, dirty, openw], when, dirty={dirty.path})
        self.assertEqual(remove, [old])
        self.assertEqual({t.path for t, _ in kept}, {fresh.path, dirty.path})  # open work is not even listed

    def test_the_grace_period_is_thirty_minutes(self):
        t = fake_tree("t")
        remove, _ = self.run_plan([t], {t.path: SWEEP_NOW - timedelta(minutes=30)})
        self.assertEqual(remove, [t])

    def test_locked_and_kept_directories_stay(self):
        locked, mine = fake_tree("locked", locked=True), fake_tree("mine")
        when = {t.path: SWEEP_NOW - timedelta(days=1) for t in (locked, mine)}
        remove, kept = self.run_plan([locked, mine], when, keep=["/r/mine/sub"])
        self.assertEqual(remove, [])
        self.assertEqual(len(kept), 2)

    def test_a_lock_whose_session_has_exited_does_not_keep_it(self):
        dead = WT.Worktree("/r/dead", "abc", "b", True, "claude agent agent-x (pid 111 start Sat Nov 21 14:25:32 2026)")
        live = WT.Worktree("/r/live", "abc", "b", True, "claude agent agent-y (pid 222 start Sat Nov 21 14:25:32 2026)")
        bare = WT.Worktree("/r/bare", "abc", "b", True, "")
        when = {t.path: SWEEP_NOW - timedelta(days=1) for t in (dead, live, bare)}
        with mock.patch.object(WT, "pid_running", side_effect=lambda pid: pid == 222), \
                mock.patch.object(WT, "process_start", return_value=datetime(2026, 11, 21, 14, 25, 32)), \
                mock.patch.object(WT, "idle_since", return_value=SWEEP_NOW - timedelta(hours=2)):
            remove, kept = self.run_plan([dead, live, bare], when)
        self.assertEqual(remove, [dead])
        self.assertEqual({t.path: why for t, why in kept}, {live.path: "locked", bare.path: "locked"})

    def test_a_dead_sessions_worktree_waits_until_it_is_idle(self):
        dead = WT.Worktree("/r/dead", "abc", "b", True, "claude agent agent-x (pid 111 start Sat Nov 21 14:25:32 2026)")
        with mock.patch.object(WT, "pid_running", return_value=False):
            with mock.patch.object(WT, "idle_since", return_value=SWEEP_NOW - timedelta(minutes=20)):
                self.assertTrue(WT.lock_held(dead, SWEEP_NOW))
            with mock.patch.object(WT, "idle_since", return_value=None):
                self.assertTrue(WT.lock_held(dead, SWEEP_NOW))
            with mock.patch.object(WT, "idle_since", return_value=SWEEP_NOW - timedelta(hours=2)):
                self.assertFalse(WT.lock_held(dead, SWEEP_NOW))

    def test_a_reused_pid_counts_as_a_gone_session(self):
        reason = "claude agent agent-x (pid 333 start Sat Nov 21 14:25:32 2026)"
        with mock.patch.object(WT, "pid_running", return_value=True):
            with mock.patch.object(WT, "process_start", return_value=datetime(2026, 11, 22, 9, 0, 0)):
                self.assertTrue(WT.lock_session_gone(reason))
            with mock.patch.object(WT, "process_start", return_value=datetime(2026, 11, 21, 14, 25, 33)):
                self.assertFalse(WT.lock_session_gone(reason))
            with mock.patch.object(WT, "process_start", return_value=None):
                self.assertFalse(WT.lock_session_gone(reason))

    def test_a_lock_written_in_utc_matches_a_local_ps_time(self):
        """Claude Code records the session start in UTC; ps prints local time. The same moment is the same
        session, so a live session's lock must not count as gone (it did, hours off, before 2026-11-25)."""
        local = datetime(2026, 11, 24, 23, 8, 5)
        utc = local.astimezone(timezone.utc).replace(tzinfo=None)
        reason = f"claude agent agent-x (pid 333 start {utc:%a %b %d %H:%M:%S %Y})"
        with mock.patch.object(WT, "pid_running", return_value=True), \
                mock.patch.object(WT, "process_start", return_value=local):
            self.assertFalse(WT.lock_session_gone(reason))
        with mock.patch.object(WT, "pid_running", return_value=True), \
                mock.patch.object(WT, "process_start", return_value=local + timedelta(minutes=7)):
            self.assertTrue(WT.lock_session_gone(reason))

    def test_odd_pids_never_count_as_gone(self):
        self.assertFalse(WT.lock_session_gone("pid 99999999999999999999 start x"))  # too long for the pattern
        with mock.patch.object(WT.os, "kill", side_effect=OverflowError):
            self.assertTrue(WT.pid_running(2 ** 40))
        with mock.patch.object(WT.os, "kill", side_effect=ProcessLookupError):
            self.assertFalse(WT.pid_running(12345))
        self.assertTrue(WT.pid_running(os.getpid()))

    def test_a_merged_worktree_outside_the_home_folder_is_kept(self):
        inside, outside = fake_tree("main/.claude/worktrees/a"), fake_tree("elsewhere/b")
        when = {t.path: SWEEP_NOW - timedelta(days=1) for t in (inside, outside)}
        remove, kept = WT.plan([fake_tree("main", "main"), inside, outside], lambda t: when.get(t.path), [],
                               lambda p: False, now=SWEEP_NOW, home="/r/main/.claude/worktrees")
        self.assertEqual(remove, [inside])
        self.assertEqual([(t, why.split(",")[0]) for t, why in kept], [(outside, "outside")])


def git_in(*args, cwd):
    subprocess.run(["git", "-c", "protocol.file.allow=always", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    *args], cwd=cwd, check=True, capture_output=True)


class SubmoduleSweepTest(unittest.TestCase):
    """A parent repository whose submodule has a merged and an unmerged worktree."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(os.path.realpath(tmp.name))
        sub_src = base / "sub-src"
        sub_src.mkdir()
        git_in("init", "-q", "-b", "master", cwd=sub_src)   # not main: the default branch is looked up
        (sub_src / "f").write_text("1")
        git_in("add", "f", cwd=sub_src)
        git_in("commit", "-q", "-m", "one", cwd=sub_src)
        self.parent = base / "parent"
        self.parent.mkdir()
        git_in("init", "-q", "-b", "main", cwd=self.parent)
        git_in("submodule", "add", "-q", str(sub_src), "ext/sub", cwd=self.parent)
        git_in("commit", "-q", "-m", "add sub", cwd=self.parent)
        self.sub = self.parent / "ext" / "sub"
        # the submodule's git folder was absorbed: its worktree list starts with .git/modules/ext/sub
        self.assertTrue((self.parent / ".git" / "modules" / "ext" / "sub").is_dir())
        self.wts = self.sub / ".claude" / "worktrees"
        for name in ("merged", "open"):
            git_in("worktree", "add", "-q", "-b", f"agent/{name}", str(self.wts / name), cwd=self.sub)
        self.head = subprocess.run(["git", "-C", str(self.sub), "rev-parse", "HEAD"], capture_output=True, text=True,
                                   check=True).stdout.strip()
        self.old = (SWEEP_NOW - timedelta(days=1)).isoformat()

    def sweep(self, **kw):
        merged = {"agent/merged": [{"headRefOid": self.head, "mergedAt": self.old}]}
        for p in (mock.patch.object(WT, "ROOT", self.parent),
                  mock.patch.object(WT, "merged_by_branch", lambda main, limit=1000: merged),
                  mock.patch.object(WT.shutil, "which", lambda name: "/usr/bin/gh")):
            p.start()
            self.addCleanup(p.stop)
        return WT.sweep(**kw)

    def test_a_merged_submodule_worktree_outside_its_folder_is_kept(self):
        out = self.wts.parent.parent.parent / "elsewhere"
        git_in("worktree", "remove", "--force", str(self.wts / "merged"), cwd=self.sub)
        git_in("worktree", "add", "-q", str(out), "agent/merged", cwd=self.sub)
        lines = self.sweep()
        self.assertTrue(out.is_dir())
        self.assertTrue(any(str(out) in l and "outside, kept" in l for l in lines), lines)

    def test_the_first_worktree_entry_is_the_git_folder_and_the_real_ones_are_still_found(self):
        self.assertIn(".git/modules", WT.worktrees(str(self.sub))[0].path)
        self.assertTrue(any("worktrees/merged" in l for l in self.sweep(dry_run=True)))

    def test_every_submodule_line_names_its_repository(self):
        lines = self.sweep(dry_run=True)
        self.assertTrue(lines)
        self.assertTrue(all(l.endswith("[submodule ext/sub]") for l in lines), lines)

    def test_the_default_branch_is_master(self):
        self.assertEqual(WT.default_branch(str(self.sub)), "master")

    def test_only_agent_branches_are_swept_in_a_submodule(self):
        git_in("worktree", "add", "-q", "-b", "sts/line", str(self.wts / "line"), cwd=self.sub)
        merged = {"sts/line": [{"headRefOid": self.head, "mergedAt": self.old}],
                  "agent/merged": [{"headRefOid": self.head, "mergedAt": self.old}]}
        for p in (mock.patch.object(WT, "ROOT", self.parent),
                  mock.patch.object(WT, "merged_by_branch", lambda main, limit=1000: merged),
                  mock.patch.object(WT.shutil, "which", lambda name: "/usr/bin/gh")):
            p.start()
            self.addCleanup(p.stop)
        lines = WT.sweep(dry_run=True)
        self.assertEqual([l for l in lines if "worktrees/line" in l], [])
        self.assertTrue(any("worktrees/merged" in l for l in lines))

    def test_a_vendor_submodule_is_never_entered(self):
        with mock.patch.object(WT, "SKIP_SUBMODULES", ("ext/sub",)):
            self.assertEqual(WT.submodule_repos(str(self.parent)), [])
            self.assertEqual(self.sweep(dry_run=True), [])
        self.assertTrue((self.wts / "merged").is_dir())

    def test_a_spent_budget_skips_the_submodules_and_their_network_calls(self):
        for p in (mock.patch.object(WT, "ROOT", self.parent),
                  mock.patch.object(WT, "merged_by_branch", side_effect=AssertionError("network call")),
                  mock.patch.object(WT.shutil, "which", lambda name: "/usr/bin/gh")):
            p.start()
            self.addCleanup(p.stop)
        lines = WT.sweep(budget=-1)
        self.assertEqual(len(lines), 1)
        self.assertIn("left the remaining submodules", lines[0])
        self.assertTrue(lines[0].endswith("[submodule ext/sub]"))

    def test_a_git_timeout_in_a_submodule_is_reported_and_the_sweep_goes_on(self):
        real = WT.worktrees

        def listing(cwd=None):
            if cwd is not None and os.path.realpath(cwd) == os.path.realpath(self.sub):
                raise subprocess.TimeoutExpired("git", 60)
            return real(cwd)
        with mock.patch.object(WT, "worktrees", listing):
            lines = self.sweep()
        self.assertEqual(lines, ["left this submodule for the next sweep: a git call timed out [submodule ext/sub]"])

    def test_a_listing_timeout_leaves_the_submodules_for_later(self):
        with mock.patch.object(WT, "submodule_repos", side_effect=subprocess.TimeoutExpired("git", 60)):
            lines = self.sweep()
        self.assertEqual(lines, ["left the submodules for the next sweep: listing them timed out"])

    def test_a_repository_with_only_its_main_checkout_makes_no_network_call(self):
        with mock.patch.object(WT, "merged_by_branch", side_effect=AssertionError("network call")):
            self.assertEqual(WT.sweep_repo(str(self.parent), WT.worktrees(str(self.parent)), False, [], None, WT.Clock(),
                                           "main", None, None), [])

    def test_submodule_repos_lists_the_checked_out_submodule(self):
        self.assertEqual(WT.submodule_repos(str(self.parent)), [str(self.sub)])

    def test_dry_run_names_only_the_merged_submodule_worktree(self):
        lines = self.sweep(dry_run=True)
        self.assertEqual([l for l in lines if l.startswith("would remove")],
                         [f"would remove {self.wts}/merged (agent/merged) [submodule ext/sub]"])
        self.assertTrue((self.wts / "merged").is_dir())

    def test_sweep_removes_the_merged_one_and_keeps_the_rest(self):
        lines = self.sweep()
        self.assertTrue(any(l.startswith("removed") and "worktrees/merged" in l for l in lines), lines)
        self.assertFalse((self.wts / "merged").exists())
        self.assertTrue((self.wts / "open").is_dir())

    def test_uncommitted_work_keeps_a_merged_submodule_worktree(self):
        (self.wts / "merged" / "new.txt").write_text("x")
        lines = self.sweep()
        self.assertTrue(any("worktrees/merged" in l and "uncommitted" in l for l in lines), lines)
        self.assertTrue((self.wts / "merged").is_dir())

    def test_a_commit_after_the_merge_keeps_it(self):
        (self.wts / "merged" / "g").write_text("2")
        git_in("add", "g", cwd=self.wts / "merged")
        git_in("commit", "-q", "-m", "later", cwd=self.wts / "merged")
        lines = self.sweep(dry_run=True)
        self.assertEqual([l for l in lines if l.startswith("would remove")], [])


if __name__ == "__main__":
    unittest.main()
