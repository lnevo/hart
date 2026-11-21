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

    def test_presets_name_a_node_and_steps(self) -> None:
        g = {"domains": DOMAINS, "nodes": [node("x"), node("y")], "edges": [{"from": "x", "to": "y"}]}
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "g.json"
            p.write_text(json.dumps({**g, "presets": [{"label": "X", "focus": "x", "up": 1, "down": "all"}]}))
            MAP.load(p)
            p.write_text(json.dumps({**g, "presets": [{"label": "Z", "focus": "z", "up": -1, "down": 1}]}))
            with self.assertRaisesRegex(MAP.GraphError, "preset 1 needs a label and a focus(.|\n)*up must be"):
                MAP.load(p)
            p.write_text(json.dumps({**g, "presets": ["x", {"label": "X", "focus": "x", "up": True, "down": 0}]}))
            with self.assertRaisesRegex(MAP.GraphError, "preset 1 must be an object(.|\n)*'X': up must be"):
                MAP.load(p)

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

    def test_highlighted_only_keeps_the_lit_chain(self) -> None:
        """chainOf: both sides of the clicked box, stopping at a stop box, and only links inside one side."""
        edges = [{"from": "a", "to": "x"}, {"from": "x", "to": "b"}, {"from": "a", "to": "b"},
                 {"from": "c", "to": "b"}, {"from": "b", "to": "host"}, {"from": "host", "to": "d"}]
        script = (
            "const m = require(process.argv[1]); const c = m.chainOf(JSON.parse(process.argv[2]), 'x', v => v === 'host');"
            "process.stdout.write(JSON.stringify({up: [...c.up].sort(), down: [...c.down].sort(),"
            "lit: JSON.parse(process.argv[2]).filter(c.lit).map(e => e.from + e.to)}));"
        )
        out = json.loads(subprocess.run([NODE, "-e", script, str(MAP.SCRIPT), json.dumps(edges)], capture_output=True,
                                        text=True, check=True).stdout)
        self.assertEqual(out["up"], ["a", "x"])
        self.assertEqual(out["down"], ["b", "host", "x"])  # c feeds b but is not on x's chain; d is past the host
        self.assertEqual(out["lit"], ["ax", "xb", "bhost"])  # a -> b bypasses x, so it stays dim and is left out

    def test_overview_hides_only_when_everything_is_in_view(self) -> None:
        """showsAll: the corner overview hides at Fit, and shows once part of the drawing is off screen or under the
        toolbar (the top tenth of the screen here)."""
        cases = {"fit": ({"x": -200, "y": -150, "width": 1400, "height": 1300}, True),
                 "zoomed": ({"x": 0, "y": 0, "width": 500, "height": 400}, False),
                 "under toolbar": ({"x": -200, "y": -50, "width": 1400, "height": 1100}, False)}
        script = ("const m = require(process.argv[1]); const c = JSON.parse(process.argv[2]); const o = {};"
                  "for (const k in c) o[k] = m.showsAll(c[k][0], 1100, 1000, 100, {top: 0.1, right: 1, bottom: 1});"
                  "process.stdout.write(JSON.stringify(o));")
        out = json.loads(subprocess.run([NODE, "-e", script, str(MAP.SCRIPT), json.dumps(cases)], capture_output=True,
                                        text=True, check=True).stdout)
        self.assertEqual(out, {k: want for k, (_, want) in cases.items()})

    def test_step_headers_thin_out_when_zoomed_out(self) -> None:
        """stepTicks: every column named when columns are wide on screen, every 20th at a whole-map zoom (step 0 always
        among them), and only the columns near the part in view."""
        wide = self.run_js("m.stepTicks(65, 0, 1200, 1)", None)
        self.assertEqual(wide["every"], 1)
        self.assertEqual([c["r"] for c in wide["cols"]], [0, 1, 2, 3])  # 400 units a column; up to one column past each edge
        far = self.run_js("m.stepTicks(65, 0, 26000, 0.01)", None)
        self.assertEqual((far["every"], [c["r"] for c in far["cols"]]), (20, [0, 20, 40, 60]))
        self.assertEqual(far["cols"][1]["x"], 20 * 400 + 125)  # the middle of the column's boxes

    def test_step_zero_is_raw_data_only_when_the_whole_graph_feeds_none_of_it(self) -> None:
        """firstColumnIsRaw: a filtered view whose first column a hidden box builds, or a folder box, is plain step 0."""
        cases = {
            "raw": ([{"id": "a", "x": 0}, {"id": "b", "x": 400}], [{"from": "a", "to": "b"}], ["a", "b"], True),
            "fed by a hidden box": ([{"id": "b", "x": 0}], [{"from": "a", "to": "b"}], ["a", "b"], False),
            "folder box": ([{"id": "folder:x", "x": 0}], [], ["a"], False),
            "no boxes": ([], [], [], False),
        }
        for name, (nodes, edges, known, want) in cases.items():
            with self.subTest(name):
                got = self.run_js("m.firstColumnIsRaw(a[0], a[1], id => a[2].includes(id))", [nodes, edges, known])
                self.assertIs(got, want)

    def run_js(self, call: str, arg) -> dict:
        script = f"const m = require(process.argv[1]); const a = JSON.parse(process.argv[2]); process.stdout.write(JSON.stringify({call}));"
        return json.loads(subprocess.run([NODE, "-e", script, str(MAP.SCRIPT), json.dumps(arg)], capture_output=True,
                                         text=True, check=True).stdout)

    def test_hidden_kinds_are_bridged_over(self) -> None:
        """contract: links run on through hidden boxes, keep the hidden boxes in via, and a direct link wins."""
        edges = [{"from": "a", "to": "s"}, {"from": "s", "to": "t"}, {"from": "t", "to": "b"}, {"from": "s", "to": "c"},
                 {"from": "a", "to": "c", "label": "direct"}, {"from": "t", "to": "s"}]
        out = self.run_js("m.contract(a.nodes, a.edges, id => id === 's' || id === 't')",
                          {"nodes": [{"id": i} for i in "astbc"], "edges": edges})
        self.assertEqual([n["id"] for n in out["nodes"]], ["a", "b", "c"])
        self.assertEqual(out["edges"], [{"from": "a", "to": "c", "label": "direct"},
                                        {"from": "a", "to": "b", "via": ["s", "t"]}])  # the s <-> t loop ends

    def test_folders_group_two_or_more_and_merge_links(self) -> None:
        nodes = [{"id": i, "path": p, "domain": "a"} for i, p in
                 (("x1", "tools/x/one.py"), ("x2", "tools/x/two.py"), ("y", "www/y.html"), ("h", ""), ("top", "Makefile"))]
        edges = [{"from": "x1", "to": "y"}, {"from": "x2", "to": "y"}, {"from": "x1", "to": "x2"}, {"from": "h", "to": "x1", "label": "runs"}]
        out = self.run_js("[m.groupByFolder(a.nodes, a.edges, new Set()), m.groupByFolder(a.nodes, a.edges, new Set(['tools/x'])),"
                          " a.nodes.map(m.folderOf)]", {"nodes": nodes, "edges": edges})
        shut, opened, folders = out
        self.assertEqual(folders, ["tools/x", "tools/x", "www", "outside the repo: a", "top level"])
        self.assertEqual(shut["members"], {"folder:tools/x": ["x1", "x2"]})  # single-box folders stay as the box
        self.assertEqual(sorted(n["id"] for n in shut["nodes"]), ["folder:tools/x", "h", "top", "y"])
        self.assertEqual(shut["edges"], [{"from": "folder:tools/x", "to": "y", "label": "2 links"}, {"from": "h", "to": "folder:tools/x"}])
        self.assertEqual(opened["members"], {})
        self.assertEqual(len(opened["edges"]), 4)

    def test_fit_leaves_room_for_the_panel(self) -> None:
        """fitView: the drawing fills the free area left of an info panel, centred there, and showsAll agrees; the
        same view counts as not showing everything once the panel covers part of it."""
        free = {"top": 0.1, "right": 0.6, "bottom": 1}
        out = self.run_js("(() => { const f = m.fitView(1000, 500, 100, a.free, 1000, 800);"
                          " return [f, m.showsAll(f, 1000, 500, 100, a.free), m.showsAll(f, 1000, 500, 100, {top: 0.1, right: 0.3, bottom: 1})]; })()",
                          {"free": free})
        view, fits, covered = out
        s = view["width"] / 1000  # drawing units per px
        left_px = (-100 - view["x"]) / s  # where the drawing's left edge lands on screen
        right_px = left_px + 1000 / s
        self.assertAlmostEqual(left_px, 0, places=3)  # width-limited: it spans the 600 px left of the panel
        self.assertAlmostEqual(right_px, 600, places=3)
        top_px, bottom_px = -view["y"] / s, (-view["y"] + 500) / s
        self.assertAlmostEqual((top_px + bottom_px) / 2, (80 + 800) / 2, places=3)  # centred below the toolbar
        self.assertTrue(fits)
        self.assertFalse(covered)

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
