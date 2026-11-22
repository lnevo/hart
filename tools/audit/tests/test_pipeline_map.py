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

    def test_tracked_false_leaves_out_only_the_tracked_check(self) -> None:
        data = {"domains": DOMAINS, "nodes": [node("x", path="no/such/file.csv"), node("y")],
                "edges": [{"from": "x", "to": "y"}]}
        MAP.validate(data, tracked=False)
        with self.assertRaisesRegex(MAP.GraphError, "does not exist in git"):
            MAP.validate(data)
        data["edges"].append({"from": "x", "to": "gone"})
        with self.assertRaisesRegex(MAP.GraphError, "to end is not a node"):
            MAP.validate(data, tracked=False)


NODE = shutil.which("node")


def js_layout(graph: dict, aspect: float = 0) -> dict:
    """Run tools/ops/pipeline_map.js's layout under node on this graph (aspect: the screen's height over width)."""
    script = (
        "const m = require(process.argv[1]); let s = '';"
        "process.stdin.on('data', d => s += d).on('end', () => { const g = JSON.parse(s);"
        f"process.stdout.write(JSON.stringify(m.layout(g.nodes, g.edges, g.domains, {aspect}))); }});"
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

    def test_lanes_grow_to_fill_a_tall_screen(self) -> None:
        """layout with an aspect: a short drawing is stretched, its lanes sharing the spare height evenly, so the drawing's height over
        its page width (width + 240) matches the screen; boxes stay inside their lanes; a tall drawing is unchanged."""
        plain, tall = js_layout(self.graph()), js_layout(self.graph(), 2.0)
        page_w = tall["width"] + 240  # LEFT + 60 either side of the boxes, as drawSvg sets W
        self.assertAlmostEqual(tall["height"] / page_w, 2.0, places=6)
        grow = [t["h"] - p["h"] for p, t in zip(plain["bands"], tall["bands"])]
        self.assertAlmostEqual(grow[0], grow[1], places=6)
        self.assertGreater(grow[0], 0)
        bands = {b["id"]: b for b in tall["bands"]}
        for n in tall["nodes"]:
            b = bands[n["domain"]]
            self.assertTrue(b["y"] <= n["y"] and n["y"] + n["h"] <= b["y"] + b["h"], n["id"])
        self.assertEqual(js_layout(self.graph(), 0.0001)["height"], plain["height"])
        # stretched, not pushed to one edge: each box's centre keeps its share of the way down its lane
        pb, pn = {b["id"]: b for b in plain["bands"]}, {n["id"]: n for n in plain["nodes"]}
        for n in tall["nodes"]:
            p, bp, bt = pn[n["id"]], pb[n["domain"]], bands[n["domain"]]
            self.assertAlmostEqual((n["y"] + n["h"] / 2 - bt["y"]) / bt["h"], (p["y"] + p["h"] / 2 - bp["y"]) / bp["h"], places=6)

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

    def test_compact_geometry_is_narrower_and_the_headers_follow_it(self) -> None:
        """layout with NARROW (compact boxes): the same columns at 250 units a column instead of 400, and stepTicks
        given the same geometry puts each header over the middle of its column's boxes."""
        g = self.graph()
        wide = self.run_js("m.layout(a.nodes, a.edges, a.domains, 0, m.WIDE)", g)
        narrow = self.run_js("m.layout(a.nodes, a.edges, a.domains, 0, m.NARROW)", g)
        self.assertEqual(narrow["columns"], wide["columns"])
        self.assertEqual(narrow["width"], wide["columns"] * 250 - 80)
        self.assertTrue(all(n["w"] == 170 and n["x"] % 250 == 0 for n in narrow["nodes"]))
        ticks = self.run_js("m.stepTicks(10, 0, 2500, 1, m.NARROW)", None)
        self.assertEqual(ticks["cols"][1]["x"], 250 + 85)

    def test_name_tags_never_overlap(self) -> None:
        """placeTags: in priority order, a tag that overlaps one already placed or a blocked area is left out."""
        boxes = [{"x0": 0, "y0": 0, "x1": 100, "y1": 20},     # placed first
                 {"x0": 50, "y0": 10, "x1": 150, "y1": 30},   # overlaps the first
                 {"x0": 100, "y0": 0, "x1": 200, "y1": 20},   # touches the first only at its edge
                 {"x0": 300, "y0": 0, "x1": 400, "y1": 20}]   # under the blocked area
        got = self.run_js("m.placeTags(a, [{x0: 350, y0: 5, x1: 500, y1: 15}])", boxes)
        self.assertEqual(got, [0, 2])

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

    def test_lane_tags_clear_the_legend_and_fit_their_lane(self) -> None:
        """laneTagTops: a tag sits 6 px into its lane, moves up to clear the legend, is left out when its lane is
        behind the legend or too thin for it, and an open legend reaching up to the strip hides no names."""
        lanes = [[0, 200], [200, 300], [300, 320], [320, 900], [900, 1000]]
        out = self.run_js("m.laneTagTops(a, 50, 980, 880)", lanes)
        self.assertEqual(out, [50,   # under the strip, not 6 px into a lane that starts above it
                               206,  # 6 px in
                               None,  # 20 px on screen: no room for the 22 px tag
                               326,
                               None])  # behind the legend
        moved = self.run_js("m.laneTagTops(a, 50, 980, 880)", [[855, 1000], [800, 1000]])
        self.assertEqual(moved, [858, 806])  # 855: pushed up 3 px to sit just above the legend; 800: fits as it is
        tall_legend = self.run_js("m.laneTagTops(a, 50, 980, 60)", lanes)
        self.assertEqual(tall_legend[1], 206)  # the legend reaches the strip: it is ignored, the names stay

    def run_js(self, call: str, arg) -> dict:
        script = f"const m = require(process.argv[1]); const a = JSON.parse(process.argv[2]); process.stdout.write(JSON.stringify({call}));"
        return json.loads(subprocess.run([NODE, "-e", script, str(MAP.SCRIPT), json.dumps(arg)], capture_output=True,
                                         text=True, check=True).stdout)

    def test_github_link_only_for_tracked_paths(self) -> None:
        """githubUrl: this repo's files and folders on main, submodules in their own repo, nothing for local boxes."""
        links = {"": "https://github.com/o/r/blob/main/", "external/sub": "https://github.com/o/sub/blob/HEAD/"}
        cases = [{"path": "www/data/a b.json"}, {"path": "docs/benchwork"}, {"path": "external/sub"},
                 {"path": "external/sub/seed/x.py"}, {"path": "external/subway/y"}, {"path": "external/x", "local": True},
                 {"path": ""}, {}]
        out = self.run_js("a.cases.map(n => m.githubUrl(n, a.links))", {"cases": cases, "links": links})
        self.assertEqual(out, ["https://github.com/o/r/blob/main/www/data/a%20b.json",
                               "https://github.com/o/r/blob/main/docs/benchwork", "https://github.com/o/sub",
                               "https://github.com/o/sub/blob/HEAD/seed/x.py",
                               "https://github.com/o/r/blob/main/external/subway/y", "", "", ""])

    def test_code_links_cover_every_submodule(self) -> None:
        links = MAP.code_links()
        self.assertEqual(links[""], "https://github.com/lnevo/hart/blob/main/")
        self.assertEqual(links["external/sts-docker"], "https://github.com/lnevo/sts-docker/blob/HEAD/")
        self.assertEqual(len(links) - 1, (ROOT / ".gitmodules").read_text().count("[submodule "))

    def test_hidden_kinds_are_bridged_over(self) -> None:
        """contract: links run on through hidden boxes, keep the hidden boxes in via, and a direct link wins."""
        edges = [{"from": "a", "to": "s"}, {"from": "s", "to": "t"}, {"from": "t", "to": "b"}, {"from": "s", "to": "c"},
                 {"from": "a", "to": "c", "label": "direct"}, {"from": "t", "to": "s"}]
        out = self.run_js("m.contract(a.nodes, a.edges, id => id === 's' || id === 't')",
                          {"nodes": [{"id": i} for i in "astbc"], "edges": edges})
        self.assertEqual([n["id"] for n in out["nodes"]], ["a", "b", "c"])
        self.assertEqual(out["edges"], [{"from": "a", "to": "c", "label": "direct"},
                                        {"from": "a", "to": "b", "via": ["s", "t"]}])  # the s <-> t loop ends

    def test_hidden_chain_stops_are_left_out_not_bridged(self) -> None:
        """hideBoxes: a hidden box drop() marks (a chain stop: the host, the deploy script) goes with its links; a
        hidden box it does not mark is bridged over; with everything hidden, nothing is left."""
        nodes = [{"id": i} for i in ("data", "deploy", "pi", "pull", "repo")]
        edges = [{"from": "data", "to": "deploy"}, {"from": "deploy", "to": "pi"}, {"from": "pi", "to": "pull"},
                 {"from": "pull", "to": "repo"}]
        call = "m.hideBoxes(a.nodes, a.edges, id => a.hide.includes(id), id => ['pi', 'deploy'].includes(id))"
        scripts = self.run_js(call, {"nodes": nodes, "edges": edges, "hide": ["deploy", "pull"]})
        self.assertEqual([n["id"] for n in scripts["nodes"]], ["data", "pi", "repo"])
        self.assertEqual({(e["from"], e["to"]) for e in scripts["edges"]}, {("pi", "repo")})  # no data -> pi through the deploy
        host = self.run_js(call, {"nodes": nodes, "edges": edges, "hide": ["pi"]})
        self.assertEqual([n["id"] for n in host["nodes"]], ["data", "deploy", "pull", "repo"])
        self.assertEqual({(e["from"], e["to"]) for e in host["edges"]}, {("data", "deploy"), ("pull", "repo")})
        everything = self.run_js(call, {"nodes": nodes, "edges": edges, "hide": [n["id"] for n in nodes]})
        self.assertEqual(everything, {"nodes": [], "edges": []})

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
        """fitView: the drawing fills the free area left of an info panel, against its top, and showsAll agrees; the
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
        top_px = -view["y"] / s
        self.assertAlmostEqual(top_px, 80, places=3)  # starts just under the toolbar and step strip, no band above
        self.assertTrue(fits)
        self.assertFalse(covered)

    def test_view_stays_on_the_drawing_sideways(self) -> None:
        """clampView: zooming out stops at the Fit width (cut about the view's middle), a view with no size is left alone, and a pan cannot take either side edge of the drawing past
        the free area's edge, whether the drawing is wider than the area or narrower."""
        free = {"top": 0.1, "right": 0.5, "bottom": 1}
        call = "a.views.map(v => m.clampView(v, 1000, 100000, 100, a.free, 2000))"
        views = [{"x": 5000, "y": 7, "width": 4000, "height": 2000},  # too far out and off to the right
                 {"x": -900, "y": 7, "width": 400, "height": 200},    # zoomed in, panned past the left edge
                 {"x": 5000, "y": 7, "width": 400, "height": 200},    # zoomed in, panned past the right edge
                 {"x": 300, "y": 7, "width": 400, "height": 200}]     # inside: unchanged
        out = self.run_js(call, {"free": free, "views": views})
        self.assertEqual(out[0]["width"], 2000)
        self.assertEqual(out[0]["height"], 1000)
        self.assertEqual(out[0]["y"], 7 + (2000 - 1000) / 2)  # cut about the middle, not the top left corner
        self.assertEqual(out[0]["x"], -100)  # area 1000 wide, drawing fills it from its left edge
        self.assertEqual(out[1]["x"], -100)  # drawing's left edge on the screen's left edge
        self.assertEqual(out[2]["x"], 1000 - 100 - 200)  # drawing's right edge on the area's right edge
        self.assertEqual(out[3], views[3])
        hidden = {"x": 1, "y": 2, "width": 0, "height": 0}
        self.assertEqual(self.run_js("m.clampView(a.v, 1000, 100000, 100, a.free, 2000)", {"free": free, "v": hidden}), hidden)
        narrow = self.run_js("[m.clampView(a.views[0], 600, 100000, 100, a.free, 2000), m.clampView(a.views[1], 600, 100000, 100, a.free, 2000)]",
                             {"free": free, "views": [{"x": -900, "y": 0, "width": 2000, "height": 1000},
                                                      {"x": 900, "y": 0, "width": 2000, "height": 1000}]})
        self.assertEqual(narrow[0]["x"], 600 - 100 - 1000)  # a 600-wide drawing in a 1000-wide area: right edge on its right
        self.assertEqual(narrow[1]["x"], -100)  # left edge on its left

    def test_view_stays_on_the_drawing_up_and_down(self) -> None:
        """clampView down the page: the drawing's top stays at or below the step strip's edge of the free area and its
        bottom at or above the area's bottom; a drawing shorter than the area stays wholly inside it."""
        free = {"top": 0.1, "right": 1, "bottom": 0.9}
        views = [{"x": 0, "y": -5000, "width": 1000, "height": 500},  # dragged far down: the top of the drawing shows
                 {"x": 0, "y": 9000, "width": 1000, "height": 500},   # dragged far up: past the bottom
                 {"x": 0, "y": 300, "width": 1000, "height": 500}]    # inside: unchanged
        out = self.run_js("a.views.map(v => m.clampView(v, 1000, 2000, 0, a.free, 5000))", {"free": free, "views": views})
        self.assertEqual(out[0]["y"], -50)  # drawing top on the area's top (0.1 of 500 down the view)
        self.assertEqual(out[1]["y"], 2000 - 450)  # drawing bottom on the area's bottom (0.9 of 500 down)
        self.assertEqual(out[2]["y"], 300)
        short = self.run_js("[-900, 900].map(y => m.clampView({x: 0, y, width: 1000, height: 1000}, 1000, 300, 0, a.free, 5000).y)",
                            {"free": free})
        self.assertEqual(short, [300 - 900, -100])  # 300 tall in an 800 tall area: bottom on its bottom, top on its top

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
