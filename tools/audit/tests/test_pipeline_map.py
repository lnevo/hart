"""The pipeline map's graph checks and its layered layout (tools/ops/build_pipeline_map.py)."""
from __future__ import annotations

import importlib.util
import json
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


class LayoutTest(unittest.TestCase):
    def graph(self) -> dict:
        nodes = [node("src", "structured"), node("gen"), node("out", "output", "b"), node("far", "output", "b")]
        edges = [{"from": "src", "to": "gen"}, {"from": "gen", "to": "out"}, {"from": "src", "to": "far"},
                 {"from": "out", "to": "gen", "label": "loops back"}]
        return {"domains": DOMAINS, "nodes": nodes, "edges": edges}

    def test_flow_runs_left_to_right_and_cycles_are_marked(self) -> None:
        lay = MAP.layout(self.graph())
        x = {n["id"]: n["x"] for n in lay["nodes"]}
        self.assertLess(x["src"], x["gen"])
        back = [e for e in lay["edges"] if e["back"]]
        self.assertEqual([(e["from"], e["to"]) for e in back], [("out", "gen")])

    def test_nodes_stay_in_their_lane_without_overlap(self) -> None:
        lay = MAP.layout(self.graph())
        bands = {b["id"]: b for b in lay["bands"]}
        by_col: dict[float, list[dict]] = {}
        for n in lay["nodes"]:
            band = bands[n["domain"]]
            self.assertGreaterEqual(n["y"], band["y"])
            self.assertLessEqual(n["y"] + n["h"], band["y"] + band["h"])
            by_col.setdefault(n["x"], []).append(n)
        for col in by_col.values():
            col.sort(key=lambda n: n["y"])
            for upper, lower in zip(col, col[1:]):
                self.assertLessEqual(upper["y"] + upper["h"], lower["y"])

    def test_page_escapes_text(self) -> None:
        g = self.graph()
        g["nodes"][0]["desc"] = "<script>alert(1)</script>"
        page = MAP.render(g)
        self.assertNotIn("<script>alert(1)", page)


if __name__ == "__main__":
    unittest.main()
