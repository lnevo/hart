"""The pipeline map's graph checks and its layered layout (tools/ops/build_pipeline_map.py)."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("build_pipeline_map", ROOT / "tools/ops/build_pipeline_map.py")
MAP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MAP)

DOMAINS = [{"id": "a", "label": "A", "color": "#000"}, {"id": "b", "label": "B", "color": "#111"}]


def node(nid: str, kind: str = "generator", domain: str = "a", **extra) -> dict:
    return {"id": nid, "label": nid, "kind": kind, "status": "live", "domain": domain, "desc": "", "path": "", **extra}


def load(nodes: list[dict], edges: list[dict]) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "g.json"
        p.write_text(json.dumps({"domains": DOMAINS, "nodes": nodes, "edges": edges}))
        return MAP.load(p)


class GraphChecksTest(unittest.TestCase):
    def test_dangling_edge_is_named(self) -> None:
        with self.assertRaisesRegex(MAP.GraphError, "to end is not a node"):
            load([node("x")], [{"from": "x", "to": "y"}])

    def test_unknown_kind_and_domain(self) -> None:
        with self.assertRaisesRegex(MAP.GraphError, "kind 'script'.*\n.*domain 'c'"):
            load([node("x", kind="script", domain="c")], [])

    def test_missing_tracked_path_fails_unless_local(self) -> None:
        with self.assertRaisesRegex(MAP.GraphError, "does not exist"):
            load([node("x", path="no/such/file.csv")], [])
        load([node("x", path="no/such/file.csv", local=True), node("y")], [{"from": "x", "to": "y"}])

    def test_isolated_node_and_shared_path(self) -> None:
        with self.assertRaisesRegex(MAP.GraphError, "node 'z' has no links"):
            load([node("x"), node("y"), node("z")], [{"from": "x", "to": "y"}])
        with self.assertRaisesRegex(MAP.GraphError, "path tools/ops/ is already node .x."):
            load([node("x", path="tools/ops"), node("y", path="tools/ops/")], [{"from": "x", "to": "y"}])

    def test_path_outside_repo(self) -> None:
        for bad in ("/etc/hosts", "../hart/tools"):
            with self.assertRaisesRegex(MAP.GraphError, "outside the repo"):
                load([node("x", path=bad), node("y")], [{"from": "x", "to": "y"}])

    def test_domain_without_colour(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "g.json"
            p.write_text(json.dumps({"domains": [{"id": "a", "label": "A"}], "nodes": [node("x")], "edges": []}))
            with self.assertRaisesRegex(MAP.GraphError, "lacks color"):
                MAP.load(p)

    def test_malformed_edge_is_reported_not_raised(self) -> None:
        with self.assertRaisesRegex(MAP.GraphError, "lacks a from or to end"):
            load([node("x"), node("y")], [{"form": "x", "to": "y"}])

    def test_repo_graph_loads_and_page_is_current(self) -> None:
        """The committed map: every tracked path exists and index.html matches the graph."""
        data = MAP.load(MAP.GRAPH)
        self.assertEqual(MAP.PAGE.read_text(), MAP.render(data), "run python3 tools/ops/build_pipeline_map.py")

    def test_repeated_node_and_edge(self) -> None:
        with self.assertRaisesRegex(MAP.GraphError, "listed twice"):
            load([node("x"), node("x")], [])
        with self.assertRaisesRegex(MAP.GraphError, "edge x -> y is listed twice"):
            load([node("x"), node("y")], [{"from": "x", "to": "y"}, {"from": "x", "to": "y"}])


NODE = shutil.which("node")


def js_layout(graph: dict) -> dict:
    """Run tools/ops/pipeline_map.js's layout under node on this graph."""
    script = (
        "const m = require(process.argv[1]); let s = '';"
        "process.stdin.on('data', d => s += d).on('end', () => { const g = JSON.parse(s);"
        "process.stdout.write(JSON.stringify(m.layout(g.nodes, g.edges, g.domains))); });"
    )
    out = subprocess.run([NODE, "-e", script, str(MAP.SCRIPT)], input=json.dumps(graph), capture_output=True,
                         text=True, check=True)
    return json.loads(out.stdout)


@unittest.skipUnless(NODE, "node is not installed")
class LayoutTest(unittest.TestCase):
    def graph(self) -> dict:
        nodes = [node("src", "structured"), node("gen"), node("out", "output", "b"), node("far", "output", "b")]
        edges = [{"from": "src", "to": "gen"}, {"from": "gen", "to": "out"}, {"from": "src", "to": "far"},
                 {"from": "out", "to": "gen", "label": "loops back"}]
        return {"domains": DOMAINS, "nodes": nodes, "edges": edges}

    def test_flow_runs_left_to_right_and_cycles_are_marked(self) -> None:
        lay = js_layout(self.graph())
        x = {n["id"]: n["x"] for n in lay["nodes"]}
        self.assertLess(x["src"], x["gen"])
        back = [e for e in lay["edges"] if e["back"]]
        self.assertEqual([(e["from"], e["to"]) for e in back], [("out", "gen")])

    def test_nodes_stay_in_their_lane_without_overlap(self) -> None:
        for graph in (self.graph(), json.loads(MAP.GRAPH.read_text())):
            lay = js_layout(graph)
            bands = {b["id"]: b for b in lay["bands"]}
            by_col: dict[float, list[dict]] = {}
            for n in lay["nodes"]:
                band = bands[n["domain"]]
                self.assertGreaterEqual(n["y"], band["y"] - 0.01)
                self.assertLessEqual(n["y"] + n["h"], band["y"] + band["h"] + 0.01)
                by_col.setdefault(n["x"], []).append(n)
            for col in by_col.values():
                col.sort(key=lambda n: n["y"])
                for upper, lower in zip(col, col[1:]):
                    self.assertLessEqual(upper["y"] + upper["h"], lower["y"] + 0.01, (upper["id"], lower["id"]))

    def test_empty_subset(self) -> None:
        self.assertEqual(js_layout({"domains": DOMAINS, "nodes": [], "edges": []})["nodes"], [])


class PageTest(unittest.TestCase):
    def test_site_copy_is_current(self) -> None:
        """The website copy check.sh guards, with the same flags."""
        args = ["--public", "--out", str(ROOT / "www/library/pipeline-map.html"), "--back", "repository-guide.html", "--check"]
        self.assertEqual(MAP.main(args), 0)

    def test_relative_out_and_stale_hint(self) -> None:
        import contextlib
        import io
        import os
        with tempfile.TemporaryDirectory() as tmp, contextlib.chdir(tmp):
            rel = "map.html"
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(MAP.main(["--public", "--out", rel]), 0)
            self.assertIn("map.html", out.getvalue())
            Path(rel).write_text("stale")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(MAP.main(["--public", "--out", rel, "--check"]), 1)
            self.assertIn(f"--public --out {rel}", err.getvalue())

    def test_public_page_rejects_a_leak_anywhere(self) -> None:
        with self.assertRaisesRegex(MAP.GraphError, "leak check rejects: localhost"):
            MAP.check_public_page("<p>see localhost:8760</p>")

    def test_public_copy_passes_the_site_leak_check(self) -> None:
        spec = importlib.util.spec_from_file_location("prep", ROOT / "www/scripts/prepare_github_pages.py")
        prep = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(prep)
        page = MAP.render(MAP.public_copy(MAP.load(MAP.GRAPH)), "../library/repository-guide.html")
        hits = [line[:120] for line in page.splitlines() if prep.LEAK_PATTERNS.search(line)]
        self.assertEqual(hits, [])
        self.assertIn('href="../library/repository-guide.html"', page)
        self.assertIn("car-cards workspace", page)

    def test_page_escapes_text(self) -> None:
        g = {"domains": DOMAINS, "nodes": [node("x", desc="<script>alert(1)</script>"), node("y")],
             "edges": [{"from": "x", "to": "y"}], "updated": ""}
        page = MAP.render(g)
        self.assertNotIn("<script>alert(1)", page)


if __name__ == "__main__":
    unittest.main()
