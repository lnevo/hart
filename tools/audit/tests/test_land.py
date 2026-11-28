"""make land (tools/agent/land.py): every refusal, the waits for late check runs, the merge and the lines after it.

GitHub is a fake: an injected callable answers each gh call from a FakeGitHub, and one test puts a fake gh script on
PATH. Nothing here reaches the network or merges a real PR.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import time
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
SLUG = "owner/repo"
HEAD = "a" * 40
NEW_HEAD = "b" * 40
MAIN = "c" * 40
MERGE = "d" * 40


def load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look the module up by name
    spec.loader.exec_module(module)
    return module


LAND = load(ROOT / "tools/agent/land.py", "hart_land_test")


def check_run(status: str, conclusion: str | None = None, sha: str = HEAD, run_id: int = 7) -> dict[str, object]:
    return {"id": run_id, "name": "check", "head_sha": sha, "status": status, "conclusion": conclusion,
            "html_url": f"https://example.test/check/{run_id}"}


def push_run(status: str, conclusion: str | None = None, sha: str = MERGE) -> dict[str, object]:
    return {"databaseId": 90, "headSha": sha, "status": status, "conclusion": conclusion or "",
            "url": "https://example.test/run/90"}


@dataclass
class FakeGitHub:
    pr: dict[str, object] = field(default_factory=lambda: {
        "state": "OPEN", "headRefOid": HEAD, "headRefName": "agent/x", "mergeable": "MERGEABLE",
        "baseRefName": "main", "files": [{"path": "tools/agent/land.py"}, {"path": "www/index.html"},
                                         {"path": "jmri/layouts/hart/output/tables.xml"},
                                         {"path": "tools/audit/py_sizes.csv"}]})
    heads: list[str] = field(default_factory=list)          # successive heads; the last one repeats
    main_conclusion: str | None = "success"
    check_runs: list[list[dict[str, object]]] = field(default_factory=lambda: [[check_run("completed", "success")]])
    push_runs: list[list[dict[str, object]]] = field(default_factory=lambda: [[push_run("completed", "success")]])
    open_prs: list[dict[str, object]] = field(default_factory=list)
    calls: list[list[str]] = field(default_factory=list)
    merged: bool = False

    def __call__(self, args: list[str]) -> str:
        self.calls.append(args)
        if args[:2] == ["pr", "view"] and "state,headRefOid,headRefName,mergeable,files,baseRefName,isDraft" in args:
            return json.dumps(self.pr)
        if args[:2] == ["pr", "ready"]:
            self.pr["isDraft"] = False
            return ""
        if args[:2] == ["pr", "view"] and "headRefOid,state" in args:
            head = self.heads.pop(0) if len(self.heads) > 1 else (self.heads[0] if self.heads else HEAD)
            return json.dumps({"headRefOid": head, "state": "OPEN"})
        if args[:2] == ["pr", "view"] and "state,mergeCommit" in args:
            return json.dumps({"state": "MERGED" if self.merged else "OPEN",
                               "mergeCommit": {"oid": MERGE} if self.merged else None})
        if args[:2] == ["pr", "merge"]:
            self.merged = True
            return ""
        if args[:2] == ["pr", "list"]:
            return json.dumps(self.open_prs)
        if args == ["api", f"repos/{SLUG}/commits/main"]:
            return json.dumps({"sha": MAIN})
        if args[:1] == ["api"] and "actions/workflows/check.yml/runs" in " ".join(args):
            runs = [] if self.main_conclusion is None else [{
                "id": 1, "run_number": 1, "head_sha": MAIN, "event": "push", "head_branch": "main",
                "path": ".github/workflows/check.yml", "status": "completed", "conclusion": self.main_conclusion,
                "html_url": "https://example.test/main/1"}]
            return json.dumps({"total_count": len(runs), "workflow_runs": runs})
        if args[:1] == ["api"] and "/check-runs?" in args[1]:
            return json.dumps({"check_runs": self.check_runs.pop(0) if len(self.check_runs) > 1 else self.check_runs[0]})
        if args[:2] == ["run", "list"]:
            return json.dumps(self.push_runs.pop(0) if len(self.push_runs) > 1 else self.push_runs[0])
        raise AssertionError(f"unexpected gh call {args}")


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


LOCKS = tempfile.TemporaryDirectory()      # every test's merge lock and queue live here, never in /tmp


def lander(gh: FakeGitHub, root: Path = ROOT, lock: Path | None = None,
           lock_sleep: Any = None, queue: Path | None = None) -> tuple[Any, Clock]:
    clock = Clock()
    path = lock or Path(tempfile.mkdtemp(dir=LOCKS.name)) / "land.lock"
    return LAND.Lander(gh=gh, root=root, sleep=clock.sleep, clock=clock, poll=30, lock_path=path,
                       lock_sleep=lock_sleep or clock.sleep, queue_dir=queue or path.parent / "queue"), clock


def land(gh: FakeGitHub, **kw: object) -> tuple[int, str]:
    lnd, _ = lander(gh)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = lnd.land(12, **kw)
    return code, buf.getvalue()


@mock.patch.dict(os.environ, {"HART_CI_REPO": SLUG})
class Refusals(unittest.TestCase):
    def assert_refused(self, gh: FakeGitHub, words: str) -> str:
        code, out = land(gh)
        self.assertEqual(code, 1, out)
        self.assertIn(words, out)
        self.assertIn("Nothing was merged", out)
        self.assertFalse(gh.merged)
        self.assertFalse(any(c[:2] == ["pr", "merge"] for c in gh.calls))
        return out

    def test_closed_pr(self) -> None:
        gh = FakeGitHub()
        gh.pr["state"] = "MERGED"
        self.assert_refused(gh, "is MERGED, not open")

    def test_base_not_main(self) -> None:
        gh = FakeGitHub()
        gh.pr["baseRefName"] = "release"
        self.assert_refused(gh, "targets 'release', not main")

    def test_conflict_says_merge_locally(self) -> None:
        gh = FakeGitHub()
        gh.pr["mergeable"] = "CONFLICTING"
        out = self.assert_refused(gh, "merge origin/main into agent/x locally")
        self.assertIn("never update-branch", out)

    def test_main_red(self) -> None:
        for conclusion in ("failure", "cancelled", "timed_out"):
            with self.subTest(conclusion=conclusion):
                gh = FakeGitHub(main_conclusion=conclusion)
                out = self.assert_refused(gh, "main is red")
                self.assertIn("fixes forward", out)

    def test_main_without_a_run_does_not_block(self) -> None:
        code, out = land(FakeGitHub(main_conclusion=None), watch_main=False)
        self.assertEqual(code, 0, out)
        self.assertIn("not blocking", out)

    def test_check_failed(self) -> None:
        gh = FakeGitHub(check_runs=[[check_run("completed", "failure")]])
        self.assert_refused(gh, "ended failure")

    def test_check_never_registered(self) -> None:
        gh = FakeGitHub(check_runs=[[]])
        self.assert_refused(gh, f"registered after {LAND.REGISTER_WAIT} s")

    def test_head_moves_while_waiting(self) -> None:
        gh = FakeGitHub(heads=[HEAD, NEW_HEAD], check_runs=[[check_run("in_progress")]])
        self.assert_refused(gh, f"head moved from {HEAD[:12]} to {NEW_HEAD[:12]}")

    def test_a_check_run_for_another_sha_does_not_count(self) -> None:
        gh = FakeGitHub(check_runs=[[check_run("completed", "success", sha=NEW_HEAD)]])
        self.assert_refused(gh, "registered after")


@mock.patch.dict(os.environ, {"HART_CI_REPO": SLUG})
class Merging(unittest.TestCase):
    def test_waits_for_a_late_check_then_merges_with_the_head(self) -> None:
        gh = FakeGitHub(check_runs=[[], [], [check_run("queued")], [check_run("in_progress")],
                                    [check_run("completed", "success")]])
        code, out = land(gh)
        self.assertEqual(code, 0, out)
        self.assertIn("waiting for GitHub to register", out)
        merge = [c for c in gh.calls if c[:2] == ["pr", "merge"]]
        self.assertEqual(merge, [["pr", "merge", "12", "--merge", "--match-head-commit", HEAD]])
        self.assertIn(f"Merged #12: {MERGE}", out)
        self.assertNotIn("--admin", json.dumps(gh.calls))

    def test_squash_only_when_asked(self) -> None:
        gh = FakeGitHub()
        land(gh, squash=True)
        self.assertIn(["pr", "merge", "12", "--squash", "--match-head-commit", HEAD], gh.calls)

    def test_main_push_run_is_found_by_the_full_sha(self) -> None:
        gh = FakeGitHub(push_runs=[[], [push_run("in_progress")], [push_run("completed", "success")]])
        code, out = land(gh)
        self.assertEqual(code, 0, out)
        lookups = [c for c in gh.calls if c[:2] == ["run", "list"]]
        self.assertEqual(len(lookups), 3)
        for call in lookups:
            self.assertEqual(call[call.index("--commit") + 1], MERGE)
        self.assertIn("main's push run 90 passed", out)

    def test_short_sha_is_refused(self) -> None:
        lnd, _ = lander(FakeGitHub())
        with self.assertRaises(LAND.LandError):
            lnd.push_run(MERGE[:12])

    def test_red_main_after_merge(self) -> None:
        gh = FakeGitHub(push_runs=[[push_run("completed", "failure")]])
        code, out = land(gh)
        self.assertEqual(code, LAND.MAIN_RED_EXIT, out)
        self.assertIn("ended failure", out)
        self.assertIn("fixes forward, or one PR reverts it", out)
        self.assertIn("ships:", out)  # the lines after the merge still print

    def test_push_run_never_registers(self) -> None:
        code, out = land(FakeGitHub(push_runs=[[]]))
        self.assertEqual(code, LAND.UNWATCHED_EXIT, out)
        self.assertIn(f"--commit {MERGE}", out)

    def test_no_watch_main(self) -> None:
        gh = FakeGitHub()
        code, _ = land(gh, watch_main=False)
        self.assertEqual(code, 0)
        self.assertFalse(any(c[:2] == ["run", "list"] for c in gh.calls))


@mock.patch.dict(os.environ, {"HART_CI_REPO": SLUG, "HART_SESSION_NAME": "hart-test"})
class MergeLocks(unittest.TestCase):
    """The old merge lock (/tmp/hart-land.lock, a folder under a temp dir here): the head of the queue still takes it,
    so a land from older code and one from this code never merge together."""

    def setUp(self) -> None:
        self.path = Path(tempfile.mkdtemp(dir=LOCKS.name)) / "land.lock"

    def first(self, pr: int = 11, holder: str = "hart-other") -> Any:
        lock = LAND.MergeLock(self.path, pr, lambda line: None, holder=holder)
        self.assertTrue(lock.claim())
        return lock

    def test_a_second_land_waits_for_the_first_then_merges(self) -> None:
        held = self.first()
        sleeps: list[float] = []

        def sleep(seconds: float) -> None:     # the first land ends after the second has waited twice
            sleeps.append(seconds)
            if len(sleeps) == 2:
                held.release()

        gh = FakeGitHub()
        lnd, _ = lander(gh, lock=self.path, lock_sleep=sleep)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = lnd.land(12, watch_main=False)
        out = buf.getvalue()
        self.assertEqual(0, code, out)
        self.assertEqual(2, len(sleeps))
        self.assertIn("waiting for the old merge lock", out)
        self.assertIn("hart-other holds it for PR #11", out)
        self.assertEqual(1, out.count("waiting for the old merge lock"))      # one line a minute, not one a poll
        main_checks = [c for c in gh.calls if c == ["api", f"repos/{SLUG}/commits/main"]]
        self.assertEqual(2, len(main_checks))                             # main checked again after the wait
        self.assertFalse(self.path.exists())                              # released after the land

    def test_two_concurrent_lands_merge_one_at_a_time(self) -> None:
        import threading
        in_merge, second_waited = threading.Event(), threading.Event()
        order: list[str] = []

        class Slow(FakeGitHub):
            def __call__(inner, args: list[str]) -> str:
                if args[:2] == ["pr", "merge"]:
                    order.append(f"merge {args[2]}")
                    if args[2] == "12":
                        in_merge.set()
                        self.assertTrue(second_waited.wait(10))      # the second land is waiting meanwhile
                return super().__call__(args)

        def waiting_sleep(_seconds: float) -> None:
            second_waited.set()
            time.sleep(0.01)

        one = lander(Slow(), lock=self.path)[0]
        two = lander(Slow(), lock=self.path, lock_sleep=waiting_sleep)[0]
        codes: dict[int, int] = {}
        with contextlib.redirect_stdout(io.StringIO()):
            t1 = threading.Thread(target=lambda: codes.__setitem__(12, one.land(12, watch_main=False)))
            t1.start()
            self.assertTrue(in_merge.wait(10))
            t2 = threading.Thread(target=lambda: codes.__setitem__(13, two.land(13, watch_main=False)))
            t2.start()
            t1.join(10)
            t2.join(10)
        self.assertEqual({12: 0, 13: 0}, codes)
        self.assertEqual(["merge 12", "merge 13"], order)
        self.assertTrue(any("waiting in the merge queue" in line for line in two.out))

    def test_the_lock_is_held_through_the_merge_and_names_the_pr_and_session(self) -> None:
        seen: list[str] = []

        class Watching(FakeGitHub):
            def __call__(inner, args: list[str]) -> str:
                if args[:2] == ["pr", "merge"]:
                    seen.append((self.path / "owner").read_text())
                return super().__call__(args)

        code, _ = (lambda lnd: (lnd.land(12, watch_main=False), None))(lander(Watching(), lock=self.path)[0])
        self.assertEqual(0, code)
        pid, _since, pr, holder = seen[0].split(None, 3)
        self.assertEqual((str(os.getpid()), "12", "hart-test"), (pid, pr, holder.strip()))
        self.assertFalse(self.path.exists())

    def test_a_stale_lock_is_reclaimed_with_a_line(self) -> None:
        self.path.mkdir()
        old = int(time.time()) - LAND.LOCK_STALE - 60
        (self.path / "owner").write_text(f"999999 {old} 9 hart-gone\n")
        said: list[str] = []
        lock = LAND.MergeLock(self.path, 12, said.append, sleep=lambda s: self.fail("waited"),
                              alive=lambda pid: False)
        self.assertFalse(lock.take())
        self.assertTrue(lock.held)
        self.assertIn("was stale (holder hart-gone", said[0])
        self.assertIn(" 12 ", (self.path / "owner").read_text())
        lock.release()
        self.assertFalse(self.path.exists())

    def test_a_young_or_live_lock_is_not_reclaimed(self) -> None:
        for since, alive in ((int(time.time()), False), (int(time.time()) - LAND.LOCK_STALE - 60, True)):
            with self.subTest(since=since, alive=alive):
                path = Path(tempfile.mkdtemp(dir=LOCKS.name)) / "land.lock"
                path.mkdir()
                (path / "owner").write_text(f"999999 {since} 9 hart-other\n")
                lock = LAND.MergeLock(path, 12, lambda line: None, alive=lambda pid, a=alive: a)
                lock.clear_if_stale(lock.owner())
                self.assertTrue((path / "owner").exists())

    def test_a_lock_without_an_owner_file_is_aged_by_its_folder(self) -> None:
        # a holder killed between mkdir and the write: os.stat's mtime (no stat program, so no GNU or BSD flags)
        self.path.mkdir()
        old = time.time() - LAND.LOCK_STALE - 60
        os.utime(self.path, (old, old))
        lock = LAND.MergeLock(self.path, 12, lambda line: None)
        self.assertGreater(lock.age(lock.owner()), LAND.LOCK_STALE)
        self.assertFalse(lock.take())

    def test_a_red_main_after_the_wait_leaves_a_draft_a_draft(self) -> None:
        held = self.first()
        gh = FakeGitHub()
        gh.pr["isDraft"] = True

        def sleep(_seconds: float) -> None:       # main turns red while the other land holds the lock
            gh.main_conclusion = "failure"
            held.release()

        lnd, _ = lander(gh, lock=self.path, lock_sleep=sleep)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = lnd.land(12, watch_main=False)
        self.assertEqual(1, code, buf.getvalue())
        self.assertIn("main is red", buf.getvalue())
        self.assertFalse(any(c[:2] in (["pr", "ready"], ["pr", "merge"]) for c in gh.calls), gh.calls)
        self.assertFalse(self.path.exists())

    def test_an_owner_file_that_cannot_be_written_gives_the_folder_back(self) -> None:
        lock = LAND.MergeLock(self.path, 12, lambda line: None)
        with mock.patch.object(Path, "write_text", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                lock.claim()
        self.assertFalse(self.path.exists())
        self.assertFalse(lock.held)

    def test_a_lock_past_the_ceiling_is_stale_with_its_holder_alive(self) -> None:
        self.path.mkdir()
        (self.path / "owner").write_text(f"{os.getpid()} {int(time.time()) - LAND.LOCK_CEILING - 60} 9 hart-hung\n")
        said: list[str] = []
        lock = LAND.MergeLock(self.path, 12, said.append, sleep=lambda s: self.fail("waited"))
        self.assertFalse(lock.take())
        self.assertIn("alive past", said[0])
        lock.release()

    def test_a_live_holder_is_waited_for_with_no_time_limit(self) -> None:
        self.first(pr=11, holder="hart-busy")
        slept: list[float] = []

        def sleep(seconds: float) -> None:      # far past the old 90-minute limit, then the holder ends
            slept.append(seconds)
            if sum(slept) >= 4 * 3600:
                (self.path / "owner").unlink()
                self.path.rmdir()

        said: list[str] = []
        lock = LAND.MergeLock(self.path, 12, said.append, sleep=sleep)
        self.assertTrue(lock.take())
        self.assertGreaterEqual(sum(slept), 4 * 3600)
        self.assertIn("hart-busy holds it for PR #11", said[0])
        lock.release()

    def test_a_stale_lock_whose_owner_changed_is_left_alone(self) -> None:
        self.path.mkdir()
        (self.path / "owner").write_text("999999 1 9 hart-gone\n")
        lock = LAND.MergeLock(self.path, 12, lambda line: None, alive=lambda pid: False)
        judged = lock.owner()
        (self.path / "owner").write_text(f"{os.getpid()} {int(time.time())} 13 hart-new\n")   # a new claim
        lock.clear_if_stale(judged)
        self.assertIn("hart-new", (self.path / "owner").read_text())


@mock.patch.dict(os.environ, {"HART_CI_REPO": SLUG})
class Drafts(unittest.TestCase):
    """A draft (make ready's GitHub gate) merges only after `check` passed on its head, marked ready first."""

    def test_a_draft_whose_check_failed_is_refused_and_stays_a_draft(self) -> None:
        gh = FakeGitHub(check_runs=[[check_run("completed", "failure")]])
        gh.pr["isDraft"] = True
        code, out = land(gh)
        self.assertEqual(1, code, out)
        self.assertIn("The PR stays a draft", out)
        self.assertFalse(any(c[:2] in (["pr", "ready"], ["pr", "merge"]) for c in gh.calls), gh.calls)

    def test_a_draft_still_waiting_is_never_marked_ready(self) -> None:
        gh = FakeGitHub(heads=[HEAD, NEW_HEAD], check_runs=[[check_run("in_progress")]])
        gh.pr["isDraft"] = True
        code, out = land(gh)
        self.assertEqual(1, code, out)
        self.assertFalse(any(c[:2] == ["pr", "ready"] for c in gh.calls))

    def test_a_draft_whose_check_passed_is_marked_ready_then_merged(self) -> None:
        gh = FakeGitHub()
        gh.pr["isDraft"] = True
        code, out = land(gh, watch_main=False)
        self.assertEqual(0, code, out)
        names = [c[:2] for c in gh.calls if c[:2] in (["pr", "ready"], ["pr", "merge"])]
        self.assertEqual([["pr", "ready"], ["pr", "merge"]], names)
        self.assertIn(["pr", "ready", "12"], gh.calls)
        self.assertIn("PR #12 is a draft", out)
        self.assertIn("PR #12 marked ready", out)

    def test_a_pr_that_is_not_a_draft_is_never_marked_ready(self) -> None:
        gh = FakeGitHub()
        code, _ = land(gh, watch_main=False)
        self.assertEqual(0, code)
        self.assertFalse(any(c[:2] == ["pr", "ready"] for c in gh.calls))


@mock.patch.dict(os.environ, {"HART_CI_REPO": SLUG})
class After(unittest.TestCase):
    OTHERS = [{"number": 20, "headRefName": "agent/y", "files": [{"path": "www/index.html"},
                                                                 {"path": "tools/audit/py_sizes.csv"}]},
              {"number": 21, "headRefName": "agent/z", "files": [{"path": "wiki/home.md"}]},
              {"number": 12, "headRefName": "agent/x", "files": [{"path": "www/index.html"}]}]

    def test_overlap_without_orient_overlap_is_one_line(self) -> None:
        code, out = land(FakeGitHub(open_prs=list(self.OTHERS)), watch_main=False)
        self.assertEqual(code, 0, out)
        self.assertIn("overlap not read (tools/ops/orient_overlap.py not found): check the open PRs by hand", out)

    def test_the_real_orient_overlap_skips_driver_paths(self) -> None:
        module = LAND.load_tool(ROOT / "tools/ops/orient_overlap.py", "orient_overlap")
        self.assertIsNotNone(module)
        self.assertEqual(module.drivers(ROOT, ["tools/audit/py_sizes.csv", "www/index.html"]),
                         {"tools/audit/py_sizes.csv"})

    def test_a_failure_after_the_merge_is_a_line_not_exit_1(self) -> None:
        def broken(*args: object, **kwargs: object) -> object:
            raise RuntimeError("worktree list failed")

        module = ModuleType("orient_overlap")
        module.overlaps_for = broken  # type: ignore[attr-defined]
        module.parse_prs = lambda raw: raw  # type: ignore[attr-defined]
        code, out = land(FakeGitHub(open_prs=list(self.OTHERS)), watch_main=False, overlap_module=module)
        self.assertEqual(code, LAND.UNWATCHED_EXIT, out)
        self.assertIn("overlap not read after the merge (RuntimeError: worktree list failed)", out)
        self.assertIn("ships: ", out)

    def test_overlap_from_orient_overlap(self) -> None:
        seen: dict[str, object] = {}

        def overlaps_for(paths, exclude_worktree, *, root=None, prs=()):
            seen.update(paths=list(paths), prs=prs)
            return [SimpleNamespace(path="www/index.html", places=("PR #20 (agent/y)", "agent/w"), auto_merge=False),
                    SimpleNamespace(path="tools/audit/py_sizes.csv", places=("PR #20 (agent/y)",), auto_merge=True),
                    SimpleNamespace(path="tools/agent/land.py", places=("agent/v (PR #30)",), auto_merge=False)]

        module = ModuleType("orient_overlap")
        module.overlaps_for = overlaps_for  # type: ignore[attr-defined]
        module.parse_prs = lambda raw: [p["number"] for p in raw]  # type: ignore[attr-defined]
        code, out = land(FakeGitHub(open_prs=list(self.OTHERS)), watch_main=False, overlap_module=module)
        self.assertEqual(code, 0, out)
        self.assertIn("overlap (from tools/ops/orient_overlap.py):", out)
        self.assertIn("PR #20 must merge origin/main locally: shares www/index.html\n", out)
        self.assertIn("PR #30 must merge origin/main locally: shares tools/agent/land.py", out)
        self.assertEqual(seen["prs"], [20, 21])

    def test_no_overlap(self) -> None:
        module = ModuleType("orient_overlap")
        module.overlaps_for = lambda *a, **k: []  # type: ignore[attr-defined]
        module.parse_prs = lambda raw: raw  # type: ignore[attr-defined]
        _, out = land(FakeGitHub(), watch_main=False, overlap_module=module)
        self.assertIn("overlap (from tools/ops/orient_overlap.py): none", out)

    def test_ships_line(self) -> None:
        lnd, _ = lander(FakeGitHub())
        self.assertEqual(lnd.ships(["wiki/home.md"]), "ships: nothing")
        line = lnd.ships(["jmri/layouts/hart/output/tables.xml", "www/index.html", "wiki/home.md"])
        self.assertIn("layout hosts (jmri/layouts/hart/output/tables.xml)", line)
        self.assertIn("site (www/index.html)", line)
        self.assertNotIn("wiki/home.md", line)

    def test_dashboard_skipped_without_its_options(self) -> None:
        _, out = land(FakeGitHub(), watch_main=False)
        self.assertNotIn("dashboard", out)

    def test_dashboard_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "tools/agent/dash_rows.py"
            script.parent.mkdir(parents=True)
            script.write_text("import json, sys\nprint(json.dumps(sys.argv[1:]))\n", encoding="utf-8")
            lnd, _ = lander(FakeGitHub(), root=root)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                lnd.dashboard(12, MERGE, "w3", str(root / "out"))
            self.assertIn(f'"--wave", "w3", "event", "Merged #12: {MERGE}"', buf.getvalue())


class Runner(unittest.TestCase):
    def test_gh_on_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "gh"
            fake.write_text('#!/bin/sh\nif [ "$1" = fail ]; then echo boom >&2; exit 3; fi\necho "args: $*"\n',
                            encoding="utf-8")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            with mock.patch.dict(os.environ, {"PATH": f"{tmp}{os.pathsep}{os.environ['PATH']}"}):
                self.assertEqual(LAND.run_gh(["pr", "view", "1"]).strip(), "args: pr view 1")
                with self.assertRaisesRegex(LAND.LandError, "exit 3.*boom"):
                    LAND.run_gh(["fail"])

    def test_help_and_bad_call(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(LAND.main(["--help"]), 0)
            self.assertEqual(LAND.main([]), 2)
            self.assertEqual(LAND.main(["twelve"]), 2)


if __name__ == "__main__":
    unittest.main()
