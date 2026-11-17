"""tools/agent/worktrees.py: which merged worktrees the sweep removes, in the repository and in its submodules."""
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import worktrees as wt  # noqa: E402

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)


def tree(name, branch="b", locked=False):
    return wt.Worktree(f"/r/{name}", "abc", branch, locked)


class PlanTest(unittest.TestCase):
    def run_plan(self, trees, when, keep=(), dirty=()):
        return wt.plan([tree("main", "main")] + trees, lambda t: when.get(t.path), list(keep),
                       lambda p: p in dirty, now=NOW)

    def test_only_old_clean_merged_worktrees_are_removed(self):
        old, fresh, dirty, openw = tree("old"), tree("fresh"), tree("dirty"), tree("open")
        when = {old.path: NOW - timedelta(hours=2), fresh.path: NOW - timedelta(minutes=29),
                dirty.path: NOW - timedelta(hours=2)}
        remove, kept = self.run_plan([old, fresh, dirty, openw], when, dirty={dirty.path})
        self.assertEqual(remove, [old])
        self.assertEqual({t.path for t, _ in kept}, {fresh.path, dirty.path})  # open work is not even listed

    def test_the_grace_period_is_thirty_minutes(self):
        t = tree("t")
        remove, _ = self.run_plan([t], {t.path: NOW - timedelta(minutes=30)})
        self.assertEqual(remove, [t])

    def test_locked_and_kept_directories_stay(self):
        locked, mine = tree("locked", locked=True), tree("mine")
        when = {t.path: NOW - timedelta(days=1) for t in (locked, mine)}
        remove, kept = self.run_plan([locked, mine], when, keep=["/r/mine/sub"])
        self.assertEqual(remove, [])
        self.assertEqual(len(kept), 2)


def run(*args, cwd):
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
        run("init", "-q", "-b", "main", cwd=sub_src)
        (sub_src / "f").write_text("1")
        run("add", "f", cwd=sub_src)
        run("commit", "-q", "-m", "one", cwd=sub_src)
        self.parent = base / "parent"
        self.parent.mkdir()
        run("init", "-q", "-b", "main", cwd=self.parent)
        run("submodule", "add", "-q", str(sub_src), "ext/sub", cwd=self.parent)
        run("commit", "-q", "-m", "add sub", cwd=self.parent)
        self.sub = self.parent / "ext" / "sub"
        self.wts = self.sub / ".claude" / "worktrees"
        for name in ("merged", "open"):
            run("worktree", "add", "-q", "-b", f"agent/{name}", str(self.wts / name), cwd=self.sub)
        self.head = subprocess.run(["git", "-C", str(self.sub), "rev-parse", "HEAD"], capture_output=True, text=True,
                                   check=True).stdout.strip()
        self.old = (NOW - timedelta(days=1)).isoformat()

    def sweep(self, **kw):
        merged = {"agent/merged": [{"headRefOid": self.head, "mergedAt": self.old}]}
        for p in (mock.patch.object(wt, "ROOT", self.parent),
                  mock.patch.object(wt, "merged_by_branch", lambda main, limit=1000: merged),
                  mock.patch.object(wt.shutil, "which", lambda name: "/usr/bin/gh")):
            p.start()
            self.addCleanup(p.stop)
        return wt.sweep(**kw)

    def test_submodule_repos_lists_the_checked_out_submodule(self):
        self.assertEqual(wt.submodule_repos(str(self.parent)), [str(self.sub)])

    def test_dry_run_names_only_the_merged_submodule_worktree(self):
        lines = self.sweep(dry_run=True)
        self.assertEqual([l for l in lines if l.startswith("would remove")],
                         [f"would remove {self.wts}/merged (agent/merged)"])
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
        run("add", "g", cwd=self.wts / "merged")
        run("commit", "-q", "-m", "later", cwd=self.wts / "merged")
        lines = self.sweep(dry_run=True)
        self.assertEqual([l for l in lines if l.startswith("would remove")], [])


if __name__ == "__main__":
    unittest.main()
