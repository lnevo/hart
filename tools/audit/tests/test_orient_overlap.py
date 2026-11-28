"""tools/ops/orient_overlap.py: files changed in two or more worktrees or open PRs, merge-driver paths apart, merged
branches skipped, and the lines orient prints.

Temporary repos with several worktrees stand in for hart; PR data is given as gh's JSON, so nothing here touches the
network or the real worktrees.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/ops"))  # orient.py imports its halves from its own folder, as when it runs
import orient_overlap as OV  # noqa: E402


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look the module up by name
    spec.loader.exec_module(module)
    return module


OR = load(ROOT / "tools/ops/orient.py", "hart_orient_for_overlap_test")
WT = load(ROOT / "tools/agent/worktrees.py", "hart_worktrees_for_overlap_test")


def sh(*args: str, cwd) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def commit(path: Path, files: dict[str, str], message: str = "c") -> None:
    for name, text in files.items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text(text)
        sh("git", "add", name, cwd=path)
    sh("git", "commit", "-q", "-m", message, cwd=path)


class Repo(unittest.TestCase):
    """main with origin/main and a merge driver on map.json, and these worktrees:
    a: commits x.py and map.json;  b: stages x.py, edits map.json unstaged;  c: untracked new.py, on a detached HEAD
    e: cut from origin/main with no commit, untracked new.py;  d: commits x.py, merged into main with --no-ff."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(os.path.realpath(tmp.name))
        self.main = self.base / "main"
        self.main.mkdir()
        sh("git", "init", "-q", "-b", "main", cwd=self.main)
        sh("git", "config", "user.email", "t@example.com", cwd=self.main)
        sh("git", "config", "user.name", "t", cwd=self.main)
        commit(self.main, {".gitattributes": "map.json merge=union\nplain.txt merge\n", "x.py": "0\n",
                           "map.json": "{}\n", "plain.txt": "p\n", ".gitignore": "*.log\n"}, "init")
        self.d = self.add("d")
        commit(self.d, {"x.py": "d\n"})
        sh("git", "merge", "-q", "--no-ff", "-m", "merge d", "agent/d", cwd=self.main)
        sh("git", "update-ref", "refs/remotes/origin/main", "HEAD", cwd=self.main)
        self.a = self.add("a")
        commit(self.a, {"x.py": "a\n", "map.json": "{\"a\": 1}\n", "plain.txt": "a\n"})
        self.b = self.add("b")
        (self.b / "x.py").write_text("b\n")
        sh("git", "add", "x.py", cwd=self.b)
        (self.b / "map.json").write_text("{\"b\": 1}\n")
        (self.b / "plain.txt").write_text("b\n")
        (self.b / "skip.log").write_text("ignored\n")
        self.c = self.base / "c"
        sh("git", "worktree", "add", "-q", "--detach", str(self.c), "origin/main", cwd=self.main)
        (self.c / "new.py").write_text("c\n")
        self.cl = f"detached {self.c}"
        self.e = self.add("e")
        (self.e / "new.py").write_text("e\n")
        (self.e / "skip.log").write_text("ignored\n")

    def add(self, name: str) -> Path:
        path = self.base / name
        sh("git", "worktree", "add", "-q", "-b", f"agent/{name}", str(path), "main", cwd=self.main)
        return path

    def report(self, prs: list[dict] | None = None) -> OV.OverlapReport:
        return OV.overlap_report(self.main, WT.worktrees(self.main), OV.parse_prs(prs or []))


class OverlapTest(Repo):
    def test_committed_staged_and_untracked_changes_clash(self):
        rep = self.report()
        got = {o.path: o.places for o in rep.clashes}
        self.assertEqual(got, {"x.py": ("agent/a", "agent/b"), "new.py": ("agent/e", self.cl),
                               "plain.txt": ("agent/a", "agent/b")})
        self.assertEqual(rep.notes, [])

    def test_a_merge_driver_path_auto_merges_and_plain_merge_does_not(self):
        rep = self.report()
        self.assertEqual([(o.path, o.places, o.auto_merge) for o in rep.auto],
                         [("map.json", ("agent/a", "agent/b"), True)])
        self.assertNotIn("map.json", {o.path for o in rep.clashes})

    def test_a_merged_branch_is_skipped(self):
        (self.d / "new.py").write_text("left over\n")
        got = {o.path: o.places for o in self.report().clashes}
        self.assertNotIn("agent/d", got["x.py"])
        self.assertEqual(got["new.py"], ("agent/e", self.cl))

    def test_the_main_checkout_is_skipped(self):
        (self.main / "x.py").write_text("main edit\n")
        self.assertEqual({o.path: o.places for o in self.report().clashes}["x.py"], ("agent/a", "agent/b"))

    def test_prs_count_once_with_their_worktree_and_alone_otherwise(self):
        prs = [{"number": 7, "headRefName": "agent/a", "files": [{"path": "x.py"}, {"path": "only_on_github.py"}]},
               {"number": 9, "headRefName": "agent/remote", "files": [{"path": "x.py"}, {"path": "q.py"}]},
               {"number": "bad"}]
        got = {o.path: o.places for o in self.report(prs).clashes}
        self.assertEqual(got["x.py"], ("PR #9 (agent/remote)", "agent/a (PR #7)", "agent/b"))
        self.assertNotIn("only_on_github.py", got)  # PR 7 is read from its worktree, which lacks it
        self.assertNotIn("q.py", got)

    def test_no_origin_main_compares_uncommitted_changes_only(self):
        sh("git", "update-ref", "-d", "refs/remotes/origin/main", cwd=self.main)
        rep = self.report()
        self.assertEqual({o.path: o.places for o in rep.clashes},
                         {"new.py": ("agent/e", self.cl)})
        self.assertEqual(rep.notes, ["origin/main not found; committed changes not compared, only uncommitted ones"])

    def test_a_worktree_that_cannot_be_read_is_a_note(self):
        real = OV.tree_changes

        def failing(tree, line):
            if tree.path == str(self.b):
                raise OV.OverlapError("git status failed in b: boom")
            return real(tree, line)

        with mock.patch.object(OV, "tree_changes", side_effect=failing):
            rep = self.report()
        self.assertEqual(rep.notes, [f"worktree {self.b} not read: git status failed in b: boom"])
        self.assertNotIn("x.py", {o.path for o in rep.clashes})

    def test_status_never_takes_another_worktrees_index_lock(self):
        with mock.patch.object(OV.subprocess, "run", wraps=subprocess.run) as run:
            self.report()
        status = [call for call in run.call_args_list if "status" in call.args[0]]
        self.assertEqual(len(status), 4)  # a, b, c and e; d is merged, so never read
        self.assertTrue(all(call.kwargs["env"]["GIT_OPTIONAL_LOCKS"] == "0" for call in status))


class OverlapsForTest(Repo):
    def test_the_callers_paths_against_the_other_worktrees(self):
        got = OV.overlaps_for(["x.py", "map.json", "lonely.py", "new.py"], self.a)
        self.assertEqual([(o.path, o.places, o.auto_merge) for o in got],
                         [("map.json", ("agent/b",), True), ("new.py", ("agent/e", self.cl), False),
                          ("x.py", ("agent/b",), False)])

    def test_prs_are_read_only_when_given(self):
        prs = OV.parse_prs([{"number": 9, "headRefName": "agent/remote", "files": [{"path": "q.py"}]}])
        self.assertEqual(OV.overlaps_for(["q.py"], self.e), [])
        self.assertEqual([o.places for o in OV.overlaps_for(["q.py"], self.e, root=self.main, prs=prs)],
                         [("PR #9 (agent/remote)",)])


class LinesTest(unittest.TestCase):
    def rep(self, clashes: int, notes: list[str] | None = None) -> OV.OverlapReport:
        return OV.OverlapReport([OV.Overlap(f"f{i}.py", ("a", "b"), False) for i in range(clashes)],
                                [OV.Overlap("map.json", ("a", "b"), True)], notes or [])

    def test_short_line(self):
        self.assertEqual(OV.short_line(self.rep(0)), [])
        self.assertEqual(OV.short_line(self.rep(0, ["x"])), ["Overlap: not checked in part (1 note(s)); make orient"])
        self.assertEqual(OV.short_line(self.rep(1)),
                         ["Overlap: 1 file changed in two or more places (f0.py: a, b); make orient"])
        self.assertEqual(OV.short_line(self.rep(5)),
                         ["Overlap: 5 files changed in two or more places (f0.py: a, b; f1.py: a, b; f2.py: a, b; "
                          "and 2 more); make orient"])

    def test_full_lines(self):
        self.assertEqual(OV.full_lines(self.rep(1, ["n"]), "2 open PRs"), [
            "Overlap (files changed in two or more places; local worktrees, 2 open PRs):", "  f0.py: a, b",
            "Auto-merges (1; a merge driver in .gitattributes joins both sides):", "  map.json: a, b", "  NOTE: n"])
        self.assertEqual(OV.full_lines(OV.OverlapReport(), "no open PRs read")[0],
                         "Overlap (files changed in two or more places; local worktrees, no open PRs read): none")


class OrientWiringTest(Repo):
    def setUp(self):
        super().setUp()
        # the fixture's worktrees sit beside main, not under main/.claude/worktrees/: count that folder as home
        for patch in (mock.patch.object(OR, "ROOT", self.main), mock.patch.object(OR, "ROOT_MAIN", self.main),
                      mock.patch.object(OR, "WORKTREES", Path("..")),
                      mock.patch.object(OR, "load_worktrees_module", return_value=WT)):
            patch.start()
            self.addCleanup(patch.stop)

    def test_short_report_ends_with_the_overlap_line_and_runs_no_network(self):
        with mock.patch.object(OR, "run", side_effect=AssertionError("network part called")):
            out = OR.report(short=True, here=str(self.a))
        self.assertTrue(out[-1].startswith(f"Overlap: 3 files changed in two or more places (new.py: agent/e, {self.cl}; "))

    def test_full_report_reads_pr_files_from_the_one_pr_call(self):
        prs = [{"number": 9, "title": "t", "headRefName": "agent/remote", "isDraft": False,
                "files": [{"path": "new.py"}]}]
        calls = []

        def fake(cmd, timeout):
            calls.append(cmd)
            return (0, json.dumps(prs), "") if cmd[0] == "gh" else (0, "", "")

        with mock.patch.object(OR, "run", side_effect=fake):
            text = "\n".join(OR.report(short=False, here="/"))
        self.assertEqual([c for c in calls if c[0] == "gh"][0][-1], "number,title,headRefName,isDraft,updatedAt,files")
        self.assertEqual(sum(c[0] == "gh" for c in calls), 1)
        self.assertIn("Overlap (files changed in two or more places; local worktrees, 1 open PRs):", text)
        self.assertIn(f"  new.py: PR #9 (agent/remote), agent/e, {self.cl}", text)
        self.assertIn("  map.json: agent/a, agent/b", text)


class HomeAndLanesTest(Repo):
    def setUp(self):
        super().setUp()
        for patch in (mock.patch.object(OR, "ROOT", self.main), mock.patch.object(OR, "ROOT_MAIN", self.main),
                      mock.patch.object(OR, "load_worktrees_module", return_value=WT)):
            patch.start()
            self.addCleanup(patch.stop)

    def test_worktrees_outside_home_are_left_out_unless_a_session_runs_there(self):
        out = OR.report(short=True, here="/")
        self.assertFalse(any(line.startswith("Overlap:") for line in out), out)  # a, b, c, e all sit outside
        running = (str(self.a), str(self.b))
        with mock.patch.object(OR, "lock_state", side_effect=lambda wt, t: "session running" if t.path in running
                               else ""):
            out = OR.report(short=True, here="/")
        self.assertIn("Overlap: 2 files changed in two or more places (plain.txt: agent/a, agent/b; x.py: agent/a, "
                      "agent/b); make orient", out)

    def test_one_lane_prefixs_branches_are_grouped(self):
        home = self.main / ".claude/worktrees"
        for name in ("ux-nav", "ux-cards", "ax-gate"):
            self.add_at(home / name, f"agent/claude/{name}")
            (home / name / "shared.py").write_text(name)
        (home / "ux-nav/ux_only.py").write_text("1")
        (home / "ux-cards/ux_only.py").write_text("2")
        out = OR.report(short=True, here="/")
        self.assertIn("Overlap: 1 file changed in two or more places (shared.py: agent/claude/ax-gate, "
                      "agent/claude/ux-cards, agent/claude/ux-nav); within one lane prefix: agent/claude/ux-*: "
                      "1 file(s) (ux_only.py) in agent/claude/ux-cards, agent/claude/ux-nav; make orient", out)
        rep = OV.classify(self.main, {"q.py": ["agent/claude/ux-a (PR #3)", "PR #4 (agent/claude/ux-b)"]}, [])
        self.assertEqual((rep.clashes, list(rep.lanes)), ([], ["agent/claude/ux-"]))
        self.assertEqual(OV.short_line(rep), ["Overlap: none between lane prefixes; within one: agent/claude/ux-*: "
                                              "1 file(s) (q.py) in PR #4 (agent/claude/ux-b), agent/claude/ux-a "
                                              "(PR #3); make orient"])
        self.assertIn("Lane overlaps (1; only branches of one lane prefix share them):", OV.full_lines(rep, "0 PRs"))

    def add_at(self, path: Path, branch: str) -> None:
        sh("git", "worktree", "add", "-q", "-b", branch, str(path), "origin/main", cwd=self.main)

    def test_lane_prefixes(self):
        self.assertEqual([OV.lane(x) for x in ("agent/claude/ux-a", "agent/a", "detached wt/c", "fix-x",
                                               "PR #2 (agent/claude/data-masters-L3)")],
                         ["agent/claude/ux-", None, None, "fix-", "agent/claude/data-"])


if __name__ == "__main__":
    unittest.main()
