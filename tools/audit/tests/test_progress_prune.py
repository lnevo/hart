"""tools/agent/progress_prune.py: a lane's progress file moves to .claude/progress/archive/<date>/ once it is a
day old and no worktree, open PR or active project page uses its topic.

A temporary repo stands in for hart and gh is replaced by a canned list of open PR branches."""
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
from types import ModuleType
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/agent"))  # progress_prune imports worktrees from its own folder


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


PP = _load("hart_progress_prune_test", ROOT / "tools/agent/progress_prune.py")
OLD = time.time() - 3 * 86400


def git(*args: str, cwd: str) -> str:
    return subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True, text=True).stdout.strip()


class Matches(unittest.TestCase):
    def test_equal_or_one_extends_the_other(self) -> None:
        self.assertTrue(PP.matches("data-masters", "data-masters-L3"))
        self.assertTrue(PP.matches("ax-sweep", "ax-sweep"))
        self.assertTrue(PP.matches("night-n6-remote", "night-n6"))
        self.assertFalse(PP.matches("data", "database"))
        self.assertFalse(PP.matches("", "x"))


class Prune(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = os.path.realpath(tmp.name)
        self.main = f"{base}/repo"
        os.makedirs(f"{self.main}/wiki/projects")
        git("init", "-q", "-b", "main", cwd=self.main)
        git("config", "user.email", "t@example.invalid", cwd=self.main)
        git("config", "user.name", "t", cwd=self.main)
        git("commit", "-q", "--allow-empty", "-m", "init", cwd=self.main)
        git("worktree", "add", "-q", "-b", "agent/claude/live-lane", f"{base}/live-lane", cwd=self.main)
        Path(self.main, "wiki/projects/big-project.md").write_text("# Big\n\nStatus: active\n", encoding="utf-8")
        Path(self.main, "wiki/projects/old-project.md").write_text("# Old\n\nStatus: done\n", encoding="utf-8")
        self.progress = Path(self.main, ".claude/progress")
        self.progress.mkdir(parents=True)
        self.open_prs = {"pr-lane"}
        patch = mock.patch.object(PP, "open_pr_branches", lambda main: set(self.open_prs))
        patch.start()
        self.addCleanup(patch.stop)

    def prune(self, dry_run: bool = False) -> list[str]:
        return PP.prune(dry_run, repo=Path(self.main))

    def file(self, name: str, old: bool = True) -> Path:
        path = self.progress / name
        path.write_text("line\n", encoding="utf-8")
        if old:
            os.utime(path, (OLD, OLD))
        return path

    def test_only_old_files_no_name_uses_are_archived(self) -> None:
        done = [self.file("finished.md"), self.file("finished.dash.jsonl"), self.file("old-project-L1.log")]
        kept = [self.file("fresh.md", old=False), self.file("live-lane.log"), self.file("pr-lane.md"),
                self.file("big-project-L3.md"), self.file("notes.txt")]
        lines = self.prune()
        self.assertEqual(len(lines), 3, lines)
        day = datetime.fromtimestamp(OLD).strftime("%Y-%m-%d")
        for path in done:
            self.assertFalse(path.exists())
            moved = self.progress / "archive" / day / path.name
            self.assertTrue(moved.is_file())
            self.assertAlmostEqual(moved.stat().st_mtime, OLD, delta=1)  # the move keeps the time
        self.assertTrue(all(p.exists() for p in kept))

    def test_dry_run_moves_nothing(self) -> None:
        path = self.file("finished.md")
        lines = self.prune(dry_run=True)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith(f"would archive {path}"))
        self.assertTrue(path.exists())

    def test_a_taken_archive_name_leaves_the_file(self) -> None:
        path = self.file("finished.md")
        day = datetime.fromtimestamp(OLD).strftime("%Y-%m-%d")
        (self.progress / "archive" / day).mkdir(parents=True)
        (self.progress / "archive" / day / "finished.md").write_text("earlier\n", encoding="utf-8")
        self.assertEqual(self.prune(), [f"left {path}: {self.progress / 'archive' / day / 'finished.md'} already exists"])
        self.assertTrue(path.exists())

    def test_a_claim_on_an_active_page_keeps_its_branch_topic(self) -> None:
        Path(self.main, "wiki/projects/big-project.md").write_text(
            "# Big\n\nStatus: active\nClaimed: agent/claude/claimed-lane, /x, since 2026-11-27 10:00\n", encoding="utf-8")
        path = self.file("claimed-lane.md")
        self.assertEqual(self.prune(), [])
        self.assertTrue(path.exists())

    def test_nothing_old_makes_no_github_call(self) -> None:
        self.file("fresh.md", old=False)
        with mock.patch.object(PP, "open_pr_branches", side_effect=AssertionError("network call")):
            self.assertEqual(self.prune(), [])

    def test_no_open_pr_list_archives_nothing(self) -> None:
        path = self.file("finished.md")
        with mock.patch.object(PP, "open_pr_branches", side_effect=PP.PruneError("gh pr list failed: offline")):
            with self.assertRaises(PP.PruneError):
                self.prune()
        self.assertTrue(path.exists())

    def test_one_day_is_the_line(self) -> None:
        now = datetime.now(timezone.utc)
        young = PP.ProgressFile(Path("a.md"), "a", now - timedelta(hours=23, minutes=59))
        old = PP.ProgressFile(Path("b.md"), "b", now - timedelta(days=1))
        self.assertEqual(PP.done([young, old], set(), now), [old])

    def test_dashboards_and_handoff_files_wait_two_days(self) -> None:
        now = datetime.now(timezone.utc)
        day_old = [PP.ProgressFile(Path(n), n.split(".")[0], now - timedelta(days=1, hours=1))
                   for n in ("w.dash.jsonl", "wave-handoff.md", "hart-coordinator.log", "steward.md")]
        self.assertEqual(PP.done(day_old, set(), now), [])
        two_days = [PP.ProgressFile(f.path, f.topic, now - timedelta(days=2)) for f in day_old]
        self.assertEqual(PP.done(two_days, set(), now), two_days)


if __name__ == "__main__":
    unittest.main()
