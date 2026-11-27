"""The pipeline map's git merge drivers (tools/ops/merge_pipeline_map.py), in-process and through real git merges."""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("merge_pipeline_map", ROOT / "tools/ops/merge_pipeline_map.py")
MERGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MERGE)
GRAPH = "docs/pipeline-map/pipeline_map.json"
PAGES = ("docs/pipeline-map/index.html", "www/library/pipeline-map.html")  # built, not committed (ADR-036)

DOMAINS = [{"id": "a", "label": "A", "color": "#000"}, {"id": "b", "label": "B", "color": "#111"}]


def node(nid: str, **extra) -> dict:
    return {"id": nid, "label": nid, "kind": "generator", "status": "live", "domain": "a", "desc": "", "path": "",
            **extra}


def edge(a: str, b: str, **extra) -> dict:
    return {"from": a, "to": b, **extra}


def graph(nodes: list[dict], edges: list[dict], **top) -> dict:
    return {"updated": "2026-11-20", "domains": copy.deepcopy(DOMAINS), "nodes": nodes, "edges": edges, **top}


BASE = graph([node("x"), node("y")], [edge("x", "y")])


def text(data: dict) -> str:
    return MERGE.MAP.graph_text(data)


class Files:
    """base, ours and theirs written to a scratch folder; run() merges them as git would."""

    def __init__(self, tmp: str, base, ours, theirs) -> None:
        self.paths = [Path(tmp, f"{n}.json") for n in ("base", "ours", "theirs")]
        for p, d in zip(self.paths, (base, ours, theirs)):
            p.write_text(d if isinstance(d, str) else text(d))

    def run(self) -> tuple[int, str]:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = MERGE.main([*map(str, self.paths), GRAPH])
        return rc, err.getvalue()

    @property
    def result(self) -> str:
        return self.paths[1].read_text()


class MergeTest(unittest.TestCase):
    def merge(self, ours, theirs, base=BASE) -> tuple[int, str, str]:
        with tempfile.TemporaryDirectory() as tmp:
            f = Files(tmp, base, ours, theirs)
            rc, err = f.run()
            return rc, err, f.result

    def test_each_side_adds_different_nodes_and_edges(self) -> None:
        ours = graph([node("x"), node("y"), node("o")], [edge("x", "y"), edge("y", "o")])
        theirs = graph([node("x"), node("y"), node("t")], [edge("x", "y"), edge("x", "t")])
        rc, err, out = self.merge(ours, theirs)
        self.assertEqual(rc, 0, err)
        data = json.loads(out)
        self.assertEqual([n["id"] for n in data["nodes"]], ["x", "y", "o", "t"])  # ours, then theirs' new ones
        self.assertEqual([(e["from"], e["to"]) for e in data["edges"]], [("x", "y"), ("y", "o"), ("x", "t")])
        self.assertEqual(out, text(data))  # the file's own format
        self.assertIn("build_pipeline_map.py --check checks it", err)

    def test_new_entry_lands_after_the_one_it_follows(self) -> None:
        base = graph([node("x"), node("y"), node("z")], [edge("x", "y"), edge("y", "z")])
        theirs = graph([node("x"), node("t"), node("y"), node("z")], [edge("x", "y"), edge("y", "z"), edge("t", "z")])
        rc, err, out = self.merge(base, theirs, base)
        self.assertEqual(rc, 0, err)
        self.assertEqual([n["id"] for n in json.loads(out)["nodes"]], ["x", "t", "y", "z"])

    def test_one_side_edit_and_same_edit_both_sides(self) -> None:
        ours = graph([node("x", desc="new"), node("y")], [edge("x", "y", label="l")])
        theirs = graph([node("x", desc="new"), node("y", desc="t")], [edge("x", "y")])
        rc, err, out = self.merge(ours, theirs)
        self.assertEqual(rc, 0, err)
        data = json.loads(out)
        self.assertEqual([n["desc"] for n in data["nodes"]], ["new", "t"])
        self.assertEqual(data["edges"], [edge("x", "y", label="l")])

    def test_delete_on_one_side_of_an_unchanged_entry(self) -> None:
        base = graph([node("x"), node("y"), node("z")], [edge("x", "y"), edge("y", "z")])
        theirs = graph([node("x"), node("y")], [edge("x", "y")])
        rc, err, out = self.merge(base, theirs, base)
        self.assertEqual(rc, 0, err)
        self.assertEqual([n["id"] for n in json.loads(out)["nodes"]], ["x", "y"])

    def test_both_edit_one_node_differently_is_a_conflict(self) -> None:
        ours = graph([node("x", desc="ours"), node("y")], [edge("x", "y")])
        theirs = graph([node("x", desc="theirs"), node("y"), node("t")], [edge("x", "y"), edge("y", "t")])
        rc, err, out = self.merge(ours, theirs)
        self.assertEqual(rc, 1)
        self.assertIn("node 'x'", err)
        self.assertIn("<<<<<<< ours: node 'x'", out)
        self.assertIn('"desc": "ours"', out)
        self.assertIn('"desc": "theirs"', out)
        self.assertIn(">>>>>>> theirs: node 'x'", out)
        self.assertEqual(out.count("======="), 1)
        self.assertIn('"id": "t"', out)  # the clean parts are merged around it
        # with the markers resolved to one side the file is the merged graph
        kept = "\n".join(l for l in out.split("\n") if not l.startswith(("<<<<<<<", ">>>>>>>")))
        ours_only = kept.split("=======\n")[0] + kept.split("=======\n")[1].split("  },\n", 1)[1]
        self.assertEqual([n["desc"] for n in json.loads(ours_only)["nodes"]], ["ours", "", ""])

    def test_a_hand_edit_to_a_node_made_generated_is_a_conflict_naming_the_lane(self) -> None:
        """A branch from before the manifest lane edits a box main has since made generated."""
        ours = graph([node("x", desc="from checks.toml", gen="manifest"), node("y")], [edge("x", "y")])
        theirs = graph([node("x", desc="hand edit"), node("y")], [edge("x", "y")])
        rc, err, out = self.merge(ours, theirs)
        self.assertEqual(rc, 1)
        self.assertIn("node 'x' (generated: the manifest lane)", err)
        self.assertIn("keep either side of its block, then run python3 tools/ops/build_pipeline_map.py", err)
        self.assertIn("<<<<<<< ours: node 'x'", out)
        rc, err, _ = self.merge(ours, graph([node("x", desc="hand edit"), node("y", desc="t")], [edge("x", "y")]))
        self.assertEqual(rc, 1)
        self.assertNotIn("node 'y' (generated", err)          # only generated entries are named so

    def test_a_clean_merge_names_the_generated_entries_it_took_from_the_other_branch(self) -> None:
        base = graph([node("x", gen="manifest"), node("y")], [edge("x", "y", gen="manifest")])
        theirs = graph([node("x", desc="edited", gen="manifest"), node("y", desc="hand")],
                       [edge("x", "y", gen="manifest", label="new")])
        rc, err, out = self.merge(base, theirs, base)
        self.assertEqual(rc, 0, err)
        self.assertEqual(json.loads(out), theirs)
        self.assertIn("2 generated entries taken from the other branch, which python3 tools/ops/"
                      "build_pipeline_map.py --check checks against the merged sources", err)
        self.assertIn("node 'x' (manifest lane); edge x -> y (manifest lane)", err)
        self.assertNotIn("node 'y'", err)
        rc, err, _ = self.merge(theirs, base, base)          # ours changed them: nothing came from theirs
        self.assertEqual(rc, 0, err)
        self.assertNotIn("taken from the other branch", err)

    def test_delete_against_edit_is_a_conflict(self) -> None:
        base = graph([node("x"), node("y"), node("z")], [edge("x", "y"), edge("y", "z")])
        ours = graph([node("x"), node("y")], [edge("x", "y")])
        theirs = graph([node("x"), node("y"), node("z", desc="edited")], [edge("x", "y"), edge("y", "z")])
        rc, err, out = self.merge(ours, theirs, base)
        self.assertEqual(rc, 1)
        self.assertIn("<<<<<<< ours: node 'z' (deleted; if you keep this side, drop the comma the entry before it ends with)\n=======\n", out)
        self.assertIn('"desc": "edited"', out)

    def test_both_add_one_key_differently_is_a_conflict(self) -> None:
        ours = graph([node("x"), node("y")], [edge("x", "y", label="o")])
        theirs = graph([node("x"), node("y")], [edge("x", "y", label="t")])
        base = graph([node("x"), node("y")], [edge("y", "x")])
        rc, err, out = self.merge(ours, theirs, base)
        self.assertEqual(rc, 1)
        self.assertIn("edge x -> y", err)

    def test_dangling_edge_after_a_delete_fails_clearly(self) -> None:
        """Theirs deletes y and its edges; ours adds an edge to y: no key conflicts, but the graph is broken."""
        base = graph([node("x"), node("y"), node("z")], [edge("x", "y"), edge("x", "z")])
        ours = graph([node("x"), node("y"), node("z")], [edge("x", "y"), edge("x", "z"), edge("z", "y")])
        theirs = graph([node("x"), node("z")], [edge("x", "z")])
        rc, err, out = self.merge(ours, theirs, base)
        self.assertEqual(rc, 1)
        self.assertIn("fails the graph checks", err)
        self.assertIn("edge z -> y: to end is not a node", err)
        self.assertNotIn("Traceback", err)
        self.assertEqual([n["id"] for n in json.loads(out)["nodes"]], ["x", "z"])  # left in place to fix

    def test_untracked_paths_are_left_to_check_sh(self) -> None:
        ours = graph([node("x"), node("y", path="no/such/file.py")], [edge("x", "y")])
        rc, err, _ = self.merge(ours, BASE)
        self.assertEqual(rc, 0, err)

    def test_updated_takes_the_later_date(self) -> None:
        for o, t in (("2026-11-21", "2026-11-22"), ("2026-11-22", "2026-11-21")):
            rc, err, out = self.merge({**BASE, "updated": o}, {**BASE, "updated": t})
            self.assertEqual(rc, 0, err)
            self.assertEqual(json.loads(out)["updated"], "2026-11-22")

    def test_updated_that_is_not_a_date_is_a_conflict(self) -> None:
        rc, err, out = self.merge({**BASE, "updated": "today"}, {**BASE, "updated": "2026-11-22"})
        self.assertEqual(rc, 1)
        self.assertIn("top-level key 'updated'", err)
        self.assertIn('<<<<<<< ours: top-level key \'updated\'\n "updated": "today",\n=======\n', out)

    def test_updated_removed_or_not_text_is_a_conflict(self) -> None:
        removed = {k: v for k, v in BASE.items() if k != "updated"}
        for ours in (removed, {**BASE, "updated": 20261121}):
            rc, err, _ = self.merge(ours, {**BASE, "updated": "2026-11-22"})
            self.assertEqual(rc, 1, err)
            self.assertIn("top-level key 'updated'", err)
            self.assertNotIn("Traceback", err)

    def test_domains_and_presets_by_key_in_order(self) -> None:
        pre = [{"label": "P", "focus": "x", "up": 1, "down": 1}]
        base = {**BASE, "presets": pre}
        ours = {**base, "domains": DOMAINS[::-1]}
        theirs = {**base, "presets": pre + [{"label": "Q", "focus": "y", "up": 0, "down": "all"}],
                  "domains": DOMAINS + [{"id": "c", "label": "C", "color": "#222"}]}
        rc, err, out = self.merge(ours, theirs, base)
        self.assertEqual(rc, 0, err)
        data = json.loads(out)
        # ours' new order, and theirs' new lane after the lane it follows on theirs
        self.assertEqual([d["id"] for d in data["domains"]], ["b", "c", "a"])
        self.assertEqual([p["label"] for p in data["presets"]], ["P", "Q"])

    def test_presets_removed_on_one_side_and_changed_on_the_other_is_a_conflict(self) -> None:
        pre = [{"label": "P", "focus": "x", "up": 1, "down": 1}]
        base = {**BASE, "presets": pre}
        theirs = {**base, "presets": pre + [{"label": "Q", "focus": "y", "up": 0, "down": "all"}]}
        rc, err, out = self.merge(copy.deepcopy(BASE), theirs, base)
        self.assertEqual(rc, 1)
        self.assertIn("the 'presets' list (one side removed it", err)
        self.assertEqual([p["label"] for p in json.loads(out)["presets"]], ["P", "Q"])
        rc, err, out = self.merge(copy.deepcopy(BASE), base, base)  # removed, other side unchanged: removed
        self.assertEqual(rc, 0, err)
        self.assertNotIn("presets", json.loads(out))

    def test_deleted_last_entry_says_to_drop_the_comma(self) -> None:
        base = graph([node("x"), node("y")], [edge("x", "y"), edge("y", "x")])
        ours = graph([node("x"), node("y")], [edge("x", "y")])
        theirs = graph([node("x"), node("y")], [edge("x", "y"), edge("y", "x", label="t")])
        rc, _, out = self.merge(ours, theirs, base)
        self.assertEqual(rc, 1)
        self.assertIn("<<<<<<< ours: edge y -> x (deleted; if you keep this side, drop the comma", out)

    def test_both_reorder_differently_is_a_conflict(self) -> None:
        base = {**BASE, "domains": DOMAINS + [{"id": "c", "label": "C", "color": "#222"}]}
        ours = {**base, "domains": [base["domains"][i] for i in (2, 0, 1)]}
        theirs = {**base, "domains": [base["domains"][i] for i in (1, 2, 0)]}
        rc, err, _ = self.merge(ours, theirs, base)
        self.assertEqual(rc, 1)
        self.assertIn("the order of 'domains'", err)


class BadInputTest(unittest.TestCase):
    def check(self, theirs, needle: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            f = Files(tmp, BASE, BASE, theirs)
            rc, err = f.run()
            self.assertEqual(rc, 2, err)
            self.assertIn(needle, err)
            self.assertNotIn("Traceback", err)
            self.assertIn("Falling back to git's line merge", err)
            # ours equals base here, so git's line merge takes theirs: nothing of either side is dropped
            self.assertEqual(f.result, theirs if isinstance(theirs, str) else text(theirs))

    def test_unmergeable_input_leaves_markers_not_ours(self) -> None:
        """Both sides changed and one cannot be merged by key: the file shows both, never ours alone."""
        ours = graph([node("x", desc="ours"), node("y")], [edge("x", "y")])
        theirs = graph([node("x", desc="theirs"), node("y"), node("y")], [edge("x", "y")])
        with tempfile.TemporaryDirectory() as tmp:
            f = Files(tmp, BASE, ours, theirs)
            rc, err = f.run()
            self.assertEqual(rc, 2)
            self.assertIn("node 'y' is listed twice", err)
            self.assertIn("<<<<<<< ours", f.result)
            self.assertIn('"desc": "theirs"', f.result)

    def test_internal_error_still_leaves_markers(self) -> None:
        ours = graph([node("x", desc="ours"), node("y")], [edge("x", "y")])
        theirs = graph([node("x", desc="theirs"), node("y")], [edge("x", "y")])
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.object(MERGE, "merge_graphs", side_effect=KeyError("boom")):
            f = Files(tmp, BASE, ours, theirs)
            rc, err = f.run()
            self.assertEqual(rc, 2)
            self.assertIn("internal error: KeyError", err)
            self.assertNotIn("Traceback", err)
            self.assertIn("<<<<<<< ours", f.result)

    def test_not_json(self) -> None:
        self.check("{ nope", "theirs")
        self.check("{ nope", "not valid JSON")

    def test_entry_without_its_key(self) -> None:
        self.check(graph([{"label": "no id"}, node("y")], []), "has no id to merge it by")
        self.check(graph([node("x"), node("y")], [{"from": "x"}]), "has no to to merge it by")

    def test_key_twice(self) -> None:
        self.check(graph([node("x"), node("x")], []), "node 'x' is listed twice")
        self.check(graph([node("x"), node("y")], [edge("x", "y"), edge("x", "y", label="2")]),
                   "edge x -> y is listed twice")

    def test_presets_not_a_list(self) -> None:
        self.check({**BASE, "presets": {"label": "P"}}, "'presets' must be a list of objects")

    def test_an_unresolved_conflict_from_this_driver(self) -> None:
        self.check(text(BASE).replace('"desc": ""', '"desc": "@@pipeline-map-conflict-0@@"', 1),
                   "already holds a conflict entry")

    def test_missing_file_and_wrong_arguments(self) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(MERGE.main(["/no/base.json", "/no/ours.json", "/no/theirs.json"]), 2)
        self.assertIn("no such file: /no/base.json", err.getvalue())
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stop:
            MERGE.main(["only-one"])
        self.assertEqual(stop.exception.code, 2)


def sh(*args: str, cwd: str | Path, check: bool = True) -> subprocess.CompletedProcess:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_CONFIG_NOSYSTEM": "1"}
    done = subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env)
    if check and done.returncode != 0:
        raise AssertionError(f"{' '.join(args)} failed: {done.stdout}{done.stderr}")
    return done


class GitMergeTest(unittest.TestCase):
    """Real merges in a scratch repo that has the repo's .gitattributes and the drivers set by --install. The
    drivers are the real script: tools/ is a link to this checkout's tools/, untracked in the scratch repo."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name, "repo")
        self.repo.mkdir()
        sh("git", "init", "-q", "-b", "main", cwd=self.repo)
        (self.repo / "tools").symlink_to(ROOT / "tools")
        (self.repo / ".git/info/exclude").write_text("tools\n")
        (self.repo / ".gitattributes").write_text((ROOT / ".gitattributes").read_text())
        self.write(BASE)
        sh("git", "add", ".gitattributes", GRAPH, cwd=self.repo)
        sh("git", "commit", "-q", "-m", "base", cwd=self.repo)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(MERGE.main(["--install", "--repo", str(self.repo)]), 0)
        self.assertIn("set git config merge.pipeline-map.driver", out.getvalue())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, data: dict) -> None:
        (self.repo / GRAPH).parent.mkdir(parents=True, exist_ok=True)
        (self.repo / GRAPH).write_text(text(data))

    def branch(self, name: str, data: dict, start: str = "main") -> None:
        sh("git", "checkout", "-q", "-b", name, start, cwd=self.repo)
        self.write(data)
        sh("git", "commit", "-q", "-am", name, cwd=self.repo)

    def merge_theirs(self, ours: dict, theirs: dict) -> subprocess.CompletedProcess:
        self.branch("theirs", theirs)
        self.branch("ours", ours, "main")
        sub = self.repo / "docs"  # git runs the driver from the top of the worktree, wherever the merge starts
        return sh("git", "merge", "--no-edit", "theirs", cwd=sub, check=False)

    def test_install_is_quiet_once_set(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(MERGE.main(["--install", "--repo", str(self.repo)]), 0)
        self.assertEqual(out.getvalue(), "")
        got = sh("git", "config", "--get", "merge.pipeline-map.driver", cwd=self.repo).stdout.strip()
        self.assertIn("exec python3 tools/ops/merge_pipeline_map.py %O %A %B %P", got)

    def test_branch_without_the_script_gets_a_line_merge(self) -> None:
        """git config is shared, but a branch from before the driver has no copy of it: plain git markers."""
        (self.repo / "tools").unlink()
        done = self.merge_theirs(graph([node("x"), node("y"), node("o")], [edge("x", "y"), edge("y", "o")]),
                                 graph([node("x"), node("y"), node("t")], [edge("x", "y"), edge("y", "t")]))
        self.assertNotEqual(done.returncode, 0)
        self.assertNotIn("can't open file", done.stderr)
        merged = (self.repo / GRAPH).read_text()
        self.assertIn("<<<<<<< ours", merged)
        self.assertIn(">>>>>>> theirs", merged)

    def test_install_outside_a_checkout_is_a_clear_error(self) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(MERGE.main(["--install", "--repo", self.tmp.name]), 2)
        self.assertIn("is not a git checkout", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

    def test_clean_merge(self) -> None:
        ours = graph([node("x"), node("y"), node("o")], [edge("x", "y"), edge("y", "o")])
        theirs = graph([node("x"), node("y"), node("t")], [edge("x", "y"), edge("x", "t")])
        done = self.merge_theirs(ours, theirs)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        data = json.loads((self.repo / GRAPH).read_text())
        self.assertEqual([n["id"] for n in data["nodes"]], ["x", "y", "o", "t"])
        self.assertIn("build_pipeline_map.py --check checks it", done.stderr)
        self.assertEqual(sh("git", "status", "--porcelain", cwd=self.repo).stdout, "")

    def test_conflicting_edit_stops_the_merge(self) -> None:
        done = self.merge_theirs(graph([node("x", desc="ours"), node("y")], [edge("x", "y")]),
                                 graph([node("x", desc="theirs"), node("y")], [edge("x", "y")]))
        self.assertNotEqual(done.returncode, 0)
        unmerged = sh("git", "diff", "--name-only", "--diff-filter=U", cwd=self.repo).stdout.split()
        self.assertEqual(unmerged, [GRAPH])
        self.assertIn("<<<<<<< ours: node 'x'", (self.repo / GRAPH).read_text())

    def test_dangling_edge_stops_the_merge(self) -> None:
        base3 = graph([node("x"), node("y"), node("z")], [edge("x", "y"), edge("x", "z")])
        self.write(base3)
        sh("git", "commit", "-q", "-am", "three", cwd=self.repo)
        done = self.merge_theirs(graph([node("x"), node("y"), node("z")], [edge("x", "y"), edge("x", "z"), edge("z", "y")]),
                                 graph([node("x"), node("z")], [edge("x", "z")]))
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("edge z -> y: to end is not a node", done.stderr)
        unmerged = sh("git", "diff", "--name-only", "--diff-filter=U", cwd=self.repo).stdout.split()
        self.assertEqual(unmerged, [GRAPH])


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # worktrees.py's dataclasses look their module up there
    spec.loader.exec_module(mod)
    return mod


class SetupSpotsTest(unittest.TestCase):
    """make wt (tools/agent/worktrees.py) and the session-start hook set the drivers, and say so when they cannot."""

    WT = load(ROOT / "tools/agent/worktrees.py", "worktrees_for_merge_test")
    HOOK = load(ROOT / ".claude/hooks/worktree_sweep.py", "worktree_sweep_for_merge_test")

    def scratch(self, repo: bool) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name)
        if repo:
            sh("git", "init", "-q", cwd=path)
        (path / "tools").symlink_to(ROOT / "tools")
        return path

    def test_make_wt_sets_them_once(self) -> None:
        path = self.scratch(repo=True)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertTrue(self.WT.install_merge_drivers(path))
        self.assertIn("set git config merge.pipeline-map.driver", err.getvalue())
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertTrue(self.WT.install_merge_drivers(path))
        self.assertEqual(err.getvalue(), "")

    def test_make_wt_warns_when_it_cannot(self) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertFalse(self.WT.install_merge_drivers(self.scratch(repo=False)))
        self.assertIn("warning: could not set the git merge drivers", err.getvalue())
        self.assertIn("is not a git checkout", err.getvalue())

    def test_hook_reports_changes_then_nothing(self) -> None:
        path = self.scratch(repo=True)
        first = self.HOOK.merge_drivers(str(path))
        self.assertEqual(first[0], "Merge drivers:")
        self.assertIn("set git config merge.pipeline-map.driver", first)
        self.assertEqual(self.HOOK.merge_drivers(str(path)), [])

    def test_hook_reports_a_failure(self) -> None:
        lines = self.HOOK.merge_drivers(str(self.scratch(repo=False)))
        self.assertEqual(len(lines), 1)
        self.assertIn("Merge drivers not set", lines[0])

    def test_checkout_without_the_script_has_nothing_to_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.HOOK.merge_drivers(tmp), [])
            self.assertTrue(self.WT.install_merge_drivers(Path(tmp)))


class RetiredDriverTest(unittest.TestCase):
    """--install removes the retired page driver's config section (ADR-036), once, and says so; a git config failure
    is a clear error, not a traceback."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        sh("git", "init", "-q", cwd=self.repo)

    def install(self) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = MERGE.main(["--install", "--repo", str(self.repo)])
        return rc, out.getvalue(), err.getvalue()

    def test_a_left_over_page_driver_is_removed_once(self) -> None:
        sh("git", "config", "merge.pipeline-map-page.name", "old", cwd=self.repo)
        sh("git", "config", "merge.pipeline-map-page.driver", "exec old --page %O %A %B %P", cwd=self.repo)
        rc, out, err = self.install()
        self.assertEqual(rc, 0, err)
        self.assertIn("removed git config merge.pipeline-map-page (a retired driver)", out)
        left = sh("git", "config", "--get-regexp", "^merge\\.pipeline-map-page\\.", cwd=self.repo, check=False)
        self.assertEqual(left.returncode, 1, left.stdout)
        rc, out, err = self.install()
        self.assertEqual((rc, out), (0, ""), err)

    def test_nothing_to_remove_says_nothing_about_it(self) -> None:
        rc, out, err = self.install()
        self.assertEqual(rc, 0, err)
        self.assertNotIn("removed", out)

    def test_a_failed_removal_is_a_clear_error(self) -> None:
        sh("git", "config", "merge.pipeline-map-page.name", "old", cwd=self.repo)
        real = MERGE.git_config

        def failing(repo, *args):
            if "--remove-section" in args:
                return subprocess.CompletedProcess(args, 3, "", "could not lock config file")
            return real(repo, *args)

        with unittest.mock.patch.object(MERGE, "git_config", side_effect=failing):
            rc, _, err = self.install()
        self.assertEqual(rc, 2)
        self.assertIn("git config --remove-section merge.pipeline-map-page failed", err)
        self.assertIn("could not lock config file", err)
        self.assertNotIn("Traceback", err)

    def test_the_page_mode_is_gone(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stop:
            MERGE.main(["--page", "a", "b", "c"])
        self.assertEqual(stop.exception.code, 2)


class RepoTest(unittest.TestCase):
    def test_gitattributes_name_the_driver_and_no_page_driver(self) -> None:
        for path, driver in ((GRAPH, "pipeline-map"), *((page, "unspecified") for page in PAGES)):
            got = subprocess.run(["git", "check-attr", "merge", "--", path], cwd=ROOT, capture_output=True,
                                 text=True, check=True).stdout.strip()
            self.assertEqual(got, f"{path}: merge: {driver}")
        self.assertEqual(set(MERGE.DRIVERS), {"pipeline-map"})
        self.assertEqual(set(MERGE.RETIRED) & set(MERGE.DRIVERS), set())

    def test_the_pages_are_ignored_not_tracked(self) -> None:
        for page in PAGES:
            tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "--", page], cwd=ROOT,
                                     capture_output=True, text=True)
            self.assertNotEqual(tracked.returncode, 0, f"{page} is tracked; it is built, not committed (ADR-036)")
            ignored = subprocess.run(["git", "check-ignore", "-q", "--no-index", "--", page], cwd=ROOT)
            self.assertEqual(ignored.returncode, 0, f"{page} is not in .gitignore")


# Merges of origin/main into PR #895's branch (agent/claude/anyplan-from-plugin) where both sides had changed the
# graph and it was merged by hand; the driver gives the same graph.
HAND_MERGES = ("73e0a5cf", "0e2ceeb1")


def have(commit: str) -> bool:
    return subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=ROOT, capture_output=True).returncode == 0


@unittest.skipUnless(all(map(have, HAND_MERGES)), "the #895 merges are not in this clone's history (shallow clone)")
class HandMergeReplayTest(unittest.TestCase):
    def test_895_merges_match_the_hand_merge(self) -> None:
        def show(rev: str) -> str:
            return subprocess.run(["git", "show", f"{rev}:{GRAPH}"], cwd=ROOT, capture_output=True, text=True,
                                  check=True).stdout

        def git(*args: str) -> str:
            return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()

        for m in HAND_MERGES:
            ours, theirs = git("rev-parse", f"{m}^1"), git("rev-parse", f"{m}^2")
            base = git("merge-base", ours, theirs)
            with self.subTest(merge=m), tempfile.TemporaryDirectory() as tmp:
                f = Files(tmp, show(base), show(ours), show(theirs))
                rc, err = f.run()
                self.assertEqual(rc, 0, err)
                got, hand = json.loads(f.result), json.loads(show(m))

                def keyed(d: dict) -> dict:
                    return {k: sorted(json.dumps(x, sort_keys=True) for x in v) if isinstance(v, list) else v
                            for k, v in d.items()}

                self.assertEqual(keyed(got), keyed(hand))


if __name__ == "__main__":
    unittest.main()
