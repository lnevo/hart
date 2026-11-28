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
        if args[:2] == ["pr", "view"] and "state,headRefOid,headRefName,mergeable,files,baseRefName" in args:
            return json.dumps(self.pr)
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


def lander(gh: FakeGitHub, root: Path = ROOT) -> tuple[Any, Clock]:
    clock = Clock()
    return LAND.Lander(gh=gh, root=root, sleep=clock.sleep, clock=clock, poll=30), clock


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


@mock.patch.dict(os.environ, {"HART_CI_REPO": SLUG})
class After(unittest.TestCase):
    OTHERS = [{"number": 20, "headRefName": "agent/y", "files": [{"path": "www/index.html"},
                                                                 {"path": "tools/audit/py_sizes.csv"}]},
              {"number": 21, "headRefName": "agent/z", "files": [{"path": "wiki/home.md"}]},
              {"number": 12, "headRefName": "agent/x", "files": [{"path": "www/index.html"}]}]

    def test_overlap_from_gh_skips_driver_paths_and_the_merged_pr(self) -> None:
        code, out = land(FakeGitHub(open_prs=list(self.OTHERS)), watch_main=False)
        self.assertEqual(code, 0, out)
        self.assertIn("overlap (from gh pr list (tools/ops/orient_overlap.py not found)):", out)
        self.assertIn("PR #20 must merge origin/main locally: shares www/index.html\n", out)
        self.assertNotIn("PR #21", out)
        self.assertNotIn("PR #12 must", out)

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
        _, out = land(FakeGitHub(), watch_main=False)
        self.assertIn("none", out.split("overlap (")[1].splitlines()[0])

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
