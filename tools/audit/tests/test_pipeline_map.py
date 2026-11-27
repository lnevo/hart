"""The pipeline map's graph checks and its layered layout (tools/ops/build_pipeline_map.py)."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import shutil
import subprocess
import tempfile
import unittest
import unittest.mock
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

    def test_repo_graph_loads_and_both_pages_build(self) -> None:
        """The committed map: every tracked path exists, and both pages draw from it and pass their checks (the pages
        are built, not committed: ADR-036)."""
        data = MAP.load(MAP.GRAPH)
        for public in (False, True):
            page = MAP.build(data, public, MAP.SITE_BACK if public else "")
            self.assertIn(f'{len(data["nodes"])} boxes, {len(data["edges"])} links', page)

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
    """Run tools/ops/pipeline_map_layout.js's layout under node on this graph (aspect: the screen's height over width)."""
    script = (
        "const m = require(process.argv[1]); let s = '';"
        "process.stdin.on('data', d => s += d).on('end', () => { const g = JSON.parse(s);"
        f"process.stdout.write(JSON.stringify(m.layout(g.nodes, g.edges, g.domains, {aspect}))); }});"
    )
    out = subprocess.run([NODE, "-e", script, str(MAP.LAYOUT_JS)], input=json.dumps(graph), capture_output=True,
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
        out = json.loads(subprocess.run([NODE, "-e", script, str(MAP.LAYOUT_JS), json.dumps(edges)], capture_output=True,
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
        out = json.loads(subprocess.run([NODE, "-e", script, str(MAP.LAYOUT_JS), json.dumps(cases)], capture_output=True,
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
        """layout with NARROW (compact boxes): the same columns at 260 units a column instead of 400, and stepTicks
        given the same geometry puts each header over the middle of its column's boxes."""
        g = self.graph()
        wide = self.run_js("m.layout(a.nodes, a.edges, a.domains, 0, m.WIDE)", g)
        narrow = self.run_js("m.layout(a.nodes, a.edges, a.domains, 0, m.NARROW)", g)
        self.assertEqual(narrow["columns"], wide["columns"])
        self.assertEqual(narrow["width"], wide["columns"] * 260 - 80)
        self.assertTrue(all(n["w"] == 180 and n["x"] % 260 == 0 for n in narrow["nodes"]))
        ticks = self.run_js("m.stepTicks(10, 0, 2600, 1, m.NARROW)", None)
        self.assertEqual(ticks["cols"][1]["x"], 260 + 90)

    def test_click_picks_box_then_card_then_line(self) -> None:
        """clickTarget: a box wins; a grown card over a line wins for a mouse, the line's box for a tap; a line alone
        opens its box; nothing under the pointer clears."""
        cases = [["b", "c", "l", False], [None, "c", "l", False], [None, "c", "l", True], [None, None, "l", False],
                 [None, None, None, False]]
        got = self.run_js("a.map(c => m.clickTarget(...c))", cases)
        self.assertEqual(got, [{"pick": "b"}, {"pick": "c"}, {"pick": "l", "line": True}, {"pick": "l", "line": True},
                               {"clear": True}])

    def test_line_click_opens_its_end_or_with_alt_its_start(self) -> None:
        """lineEnd: a click opens where the line leads, Alt where it comes from, nothing when that box is not drawn."""
        edge = {"from": "a", "to": "b"}
        got = self.run_js("[m.lineEnd(a, false, () => true), m.lineEnd(a, true, () => true), m.lineEnd(a, true, id => id === 'b')]", edge)
        self.assertEqual(got, ["b", "a", None])

    def test_grown_box_moves_in_to_stay_on_screen(self) -> None:
        """growRect: a box grown past the screen's right edge or above the free area moves in, the hovered one too."""
        area = {"left": 0, "top": 100, "right": 1000, "bottom": 800}
        mid = self.run_js("m.growRect(500, 400, 80, 20, a)", area)
        self.assertEqual((mid["dx"], mid["dy"], mid["x0"], mid["y1"]), (0, 0, 418, 422))
        edge = self.run_js("m.growRect(980, 110, 80, 20, a)", area)
        self.assertEqual((edge["dx"], edge["dy"]), (1000 - 84 - 980, 124 - 110))
        corner = self.run_js("m.growRect(5, 795, 80, 20, a)", area)  # bottom left: in from both edges
        self.assertEqual((corner["dx"], corner["dy"], corner["x0"], corner["y1"]), (79, -19, 2, 798))

    def test_hovered_card_moves_clear_of_lane_names(self) -> None:
        """clearOf: a grown rect under a lane name moves the least way clear of it inside the area; one already clear
        stays."""
        area = {"left": 0, "top": 100, "right": 1000, "bottom": 800}
        tag = {"x0": 0, "y0": 200, "x1": 150, "y1": 220}
        b = {"x0": 20, "y0": 190, "x1": 180, "y1": 240, "dx": 5, "dy": 0}  # down 31 beats up 41 and right 131
        got = self.run_js("m.clearOf(a.b, [a.tag], a.area)", {"b": b, "tag": tag, "area": area})
        self.assertEqual((got["y0"], got["dx"], got["dy"]), (221, 5, 31))
        tall = {"x0": 20, "y0": 110, "x1": 180, "y1": 790, "dx": 0, "dy": 0}  # no room above or below: right
        got = self.run_js("m.clearOf(a.b, [a.tag], a.area)", {"b": tall, "tag": tag, "area": area})
        self.assertEqual((got["x0"], got["dx"]), (151, 131))
        clear = {"x0": 300, "y0": 300, "x1": 400, "y1": 340, "dx": 0, "dy": 0}
        self.assertEqual(self.run_js("m.clearOf(a.b, [a.tag], a.area)", {"b": clear, "tag": tag, "area": area}), clear)

    def test_long_link_runs_level_across_the_columns_it_skips(self) -> None:
        """layout: a link that skips three columns runs through each at one height, so it is drawn as a straight run,
        not a bend at every step; the other boxes in those columns keep their lane."""
        nodes = [node(f"c{i}") for i in range(5)] + [node("x1"), node("x2", domain="b"), node("x3")]
        edges = [{"from": f"c{i}", "to": f"c{i + 1}"} for i in range(4)] + [{"from": "c0", "to": "c4"}]
        edges += [{"from": "x1", "to": "c2"}, {"from": "x2", "to": "c3"}, {"from": "c1", "to": "x3"}]
        lay = self.run_js("m.layout(a.nodes, a.edges, a.domains, 0, m.NARROW)", {"domains": DOMAINS, "nodes": nodes, "edges": edges})
        long = next(e for e in lay["edges"] if (e["from"], e["to"]) == ("c0", "c4"))
        way = long["pts"][1:-1]
        self.assertEqual([x for x, _ in way], [260, 440, 520, 700, 780, 960])  # in and out of each skipped column
        self.assertEqual(len({round(y, 3) for _, y in way}), 1)
        bands = {b["id"]: (b["y"], b["y"] + b["h"]) for b in lay["bands"]}
        for n in lay["nodes"]:
            lo, hi = bands[n["domain"]]
            self.assertTrue(lo <= n["y"] and n["y"] + n["h"] <= hi, n["id"])

    def test_no_link_crosses_another_box_on_the_real_map(self) -> None:
        """layout and pathSegments on the repo's graph, compact and full: no link's drawn curve passes through a box
        other than its own two ends (sampled along each segment)."""
        script = r"""
const m = require(process.argv[1]); const g = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
const out = {};
for (const geo of ['NARROW', 'WIDE']) {
  const nodes = g.nodes.filter(n => !n.status || n.status === 'live').map(n => geo === 'NARROW' ? { ...n, desc: '', path: '' } : n);
  const ids = new Set(nodes.map(n => n.id));
  const lay = m.layout(nodes, g.edges.filter(e => ids.has(e.from) && ids.has(e.to)), g.domains, 0, m[geo]);
  const bad = new Set();
  for (const e of lay.edges) for (const [p, c1, c2, q] of m.pathSegments(e.pts)) for (let t = 0.02; t < 1; t += 0.04) {
    const u = 1 - t, x = c1 ? u*u*u*p[0] + 3*u*u*t*c1[0] + 3*u*t*t*c2[0] + t*t*t*q[0] : p[0] + t * (q[0] - p[0]);
    const y = c1 ? u*u*u*p[1] + 3*u*u*t*c1[1] + 3*u*t*t*c2[1] + t*t*t*q[1] : p[1] + t * (q[1] - p[1]);
    for (const n of lay.nodes) if (n.id !== e.from && n.id !== e.to && x > n.x + 1 && x < n.x + n.w - 1 && y > n.y + 1 && y < n.y + n.h - 1) bad.add(e.from + ' -> ' + e.to + ' over ' + n.id);
  }
  out[geo] = [...bad].slice(0, 5);
}
process.stdout.write(JSON.stringify(out));"""
        out = json.loads(subprocess.run([NODE, "-e", script, str(MAP.LAYOUT_JS), str(MAP.GRAPH)], capture_output=True,
                                        text=True, check=True).stdout)
        self.assertEqual(out, {"NARROW": [], "WIDE": []})

    def test_hidden_extras_give_the_strip_room_back(self) -> None:
        """stripRoom: the step strip takes 28 px over a drawing with boxes, none with the extras hidden or no boxes."""
        self.assertEqual(self.run_js("a.map(c => m.stripRoom(...c))", [[False, 5], [True, 5], [False, 0]]), [28, 0, 0])

    def test_lane_names_lighten_for_dark_mode(self) -> None:
        """lighten: a lane colour goes halfway to white for the dark background; anything not #rrggbb is left alone."""
        self.assertEqual(self.run_js("a.map(m.lighten)", ["#1d4ed8", "#000000", "red", "#fff"]),
                         ["#8ea7ec", "#808080", "red", "#fff"])

    def test_name_tags_never_overlap(self) -> None:
        """placeTags: in priority order, a tag that overlaps one already placed or a blocked area is left out."""
        boxes = [{"x0": 0, "y0": 0, "x1": 100, "y1": 20},     # placed first
                 {"x0": 50, "y0": 10, "x1": 150, "y1": 30},   # overlaps the first
                 {"x0": 100, "y0": 0, "x1": 200, "y1": 20},   # touches the first only at its edge
                 {"x0": 300, "y0": 0, "x1": 400, "y1": 20}]   # under the blocked area
        got = self.run_js("m.placeTags(a, [{x0: 350, y0: 5, x1: 500, y1: 15}])", boxes)
        self.assertEqual(got, [0, 2])

    def test_hovered_line_lights_its_whole_chain(self) -> None:
        """linkChain: a line from a to b lights what feeds a and what b feeds, not a's other outputs, and stops at a
        chain stop."""
        edges = [{"from": "s", "to": "a"}, {"from": "a", "to": "b"}, {"from": "a", "to": "side"},
                 {"from": "b", "to": "c"}, {"from": "c", "to": "host"}, {"from": "host", "to": "past"}]
        got = self.run_js("(c => [[...c.boxes].sort(), a.filter(c.lit).map(e => e.from + e.to)])"
                          "(m.linkChain(a, 'a', 'b', id => id === 'host'))", edges)
        self.assertEqual(got, [["a", "b", "c", "host", "s"], ["sa", "ab", "bc", "chost"]])
        # a line out of a host lights only the host on that side, not everything that feeds the host
        got = self.run_js("(c => [...c.boxes].sort())(m.linkChain(a, 'host', 'past', id => id === 'host'))", edges)
        self.assertEqual(got, ["host", "past"])

    def test_cache_stops_a_chain(self) -> None:
        """isCache: a .cache/ store saves time and feeds no content, so on the real map the line from staging.json to
        publish_draft.py (which writes the schematic cache) lights publish_draft's own outputs, not all tables.xml feeds."""
        self.assertEqual(self.run_js("a.map(m.isCache)", [{"label": "<main checkout>/.cache/hart/schematic"},
                                                         {"label": ".cache/panel-stamps (per checkout)"},
                                                         {"label": "panel stamps", "path": ".cache/panel-stamps"},
                                                         {"label": "docs/cache_notes.md", "path": "docs/cache_notes.md"},
                                                         None]), [True, True, True, False, False])
        # the map is read from its file: passed on the command line it is over Linux's per-argument limit
        call = ("(g => { const by = {}; g.nodes.forEach(n => { by[n.id] = n; });"
                " return [...m.linkChain(g.edges, 'jmri/layouts/hart/data/schematic/inputs/staging.json',"
                " 'tools/schematic/publish_draft.py', id => m.stopsChain(by[id])).boxes]; })"
                "(JSON.parse(require('fs').readFileSync(a, 'utf8')))")
        lit = self.run_js(call, str(MAP.GRAPH))
        self.assertIn("ext:schematic-cache", lit)  # the cache itself still lights, as an end
        self.assertIn("docs/ops/schematic-system-draft.pdf", lit)  # publish_draft's own output
        for past in ("tools/schematic/build_tables.py", "jmri/layouts/hart/output/tables.xml"):
            self.assertNotIn(past, lit)  # reached only through the cache

    def test_hovered_line_stops_at_hubs(self) -> None:
        """hubs: a box with HUB_OUT or more links out and one in is a hub; on the real map a hovered line's chain stops
        at hubs, so the line from staging.json to build_main_route.py lights its own pipeline, not what tables.xml feeds."""
        edges = [{"from": "s", "to": "h"}] + [{"from": "h", "to": f"o{i}"} for i in range(6)] + \
                [{"from": "r", "to": f"p{i}"} for i in range(6)] + \
                [{"from": "q", "to": "q"}] + [{"from": "q", "to": f"p{i % 5}"} for i in range(6)]
        # r feeds six but nothing feeds it; q feeds five distinct boxes (one twice) and only itself feeds it
        self.assertEqual(self.run_js("[...m.hubs(a)]", edges), ["h"])
        call = ("(g => { const by = {}; g.nodes.forEach(n => { by[n.id] = n; });"
                " const hub = m.liveHubs(g);"
                " return [[...hub], [...m.linkChain(g.edges, 'jmri/layouts/hart/data/schematic/inputs/staging.json',"
                " 'tools/schematic/build_main_route.py', id => m.stopsChain(by[id]) || hub.has(id)).boxes]]; })"
                "(JSON.parse(require('fs').readFileSync(a, 'utf8')))")
        hub, lit = self.run_js(call, str(MAP.GRAPH))
        self.assertIn("jmri/layouts/hart/output/tables.xml", hub)
        self.assertIn("jmri/layouts/hart/data/schematic/plan_generated.json", lit)  # build_main_route's output
        self.assertTrue(set(hub) & set(lit))  # the hub the chain meets lights, as an end (the device master)
        for past in ("jmri/layouts/hart/output/tables.xml", "www/scripts/tables_page.py"):
            self.assertNotIn(past, lit)  # reached only through a hub

    def test_source_click_keys(self) -> None:
        """sourceClick, sourceKey: Cmd, Ctrl or Alt asks for a line's source, Shift (the magnifier) does not; the note
        names Cmd on a Mac and Ctrl elsewhere."""
        clicks = [{}, {"metaKey": True}, {"ctrlKey": True}, {"altKey": True}, {"shiftKey": True}]
        self.assertEqual(self.run_js("a.map(m.sourceClick)", clicks), [False, True, True, True, False])
        self.assertEqual(self.run_js("a.map(m.sourceKey)", ["MacIntel", "Win32", "Linux x86_64", ""]),
                         ["Cmd", "Ctrl", "Ctrl", "Ctrl"])

    def test_line_chain_fades_with_distance(self) -> None:
        """linkChain gives each box its fewest links from the nearer end of the line; fadeOf shows up to 2 fully, 3 and 4
        fainter, further fainter still."""
        edges = [{"from": f"u{i + 1}", "to": f"u{i}"} for i in range(5)] + [{"from": "u0", "to": "d0"}] + \
                [{"from": f"d{i}", "to": f"d{i + 1}"} for i in range(5)]
        got = self.run_js("(c => Object.fromEntries(c.steps))(m.linkChain(a, 'u0', 'd0', () => false))", edges)
        self.assertEqual(got, {**{f"u{i}": i for i in range(6)}, **{f"d{i}": i for i in range(6)}})
        self.assertEqual(self.run_js("a.map(m.fadeOf)", [0, 1, 2, 3, 4, 5, 9]), ["", "", "", "2", "2", "3", "3"])

    def test_grow_rank_keeps_selected_neighbours(self) -> None:
        """growRank: the hover first, then what it lights, the selection and hits, then the selected box's neighbours
        (sn, so the boxes a hover grew stay grown after the click); a box with none of these does not grow."""
        cases = [[True, []], [False, ["hn"]], [False, ["sel"]], [False, ["hit"]], [False, ["sn"]], [False, ["sn", "hn"]],
                 [False, ["near"]], [False, []], [False, ["ml"]]]  # ml: a Start button's main line, with the selection
        got = self.run_js("a.map(([h, cs]) => m.growRank(h, c => cs.includes(c)))", cases)
        self.assertEqual(got, [0, 1, 2, 2, 3, 1, 4, 4, 2])

    def test_hover_skips_side_links_and_runners(self) -> None:
        """hoverStop, hoverWalks: a hovered line's chain stops at runners and hubs and does not walk side links or a
        link bridged over a stop; on the real map every side value is known, and a line out of build_signals.py no
        longer reaches through the Store pull or the page captures."""
        hub = "new Set(['h'])"
        self.assertEqual(self.run_js(f"a.map(n => m.hoverStop(n, {hub}))",
                                     [{"id": "r", "runner": True}, {"id": "h"}, {"id": "x", "kind": "human"}, {"id": "p"}]),
                         [True, True, True, False])
        self.assertEqual(self.run_js("a.map(e => m.hoverWalks(e, id => id === 'h'))",
                                     [{"side": "check"}, {"via": ["q", "h"]}, {"via": ["q"]}, {}]),
                         [False, False, True, True])
        graph = json.loads(MAP.GRAPH.read_text())
        self.assertLessEqual({e["side"] for e in graph["edges"] if "side" in e}, set(MAP.SIDES))
        self.assertEqual(sorted(n["id"] for n in graph["nodes"] if n.get("runner")),
                         ["tools/check.sh", "tools/schematic/build_panels.sh"])
        call = ("(g => { const by = {}; g.nodes.forEach(n => { by[n.id] = n; }); const hub = m.liveHubs(g);"
                " const stop = id => m.hoverStop(by[id], hub);"
                " const live = g.edges.filter(e => by[e.from].status === 'live' && by[e.to].status === 'live');"
                " return [...m.linkChain(live.filter(e => m.hoverWalks(e, stop)), 'tools/schematic/build_signals.py',"
                " 'jmri/layouts/hart/data/schematic/signals.json', stop).boxes]; })"
                "(JSON.parse(require('fs').readFileSync(a, 'utf8')))")
        lit = self.run_js(call, str(MAP.GRAPH))
        page = MAP.render(graph)  # the page carries both marks, or the hover cannot see them
        self.assertIn('"side":"pull"', page)
        self.assertIn('"runner":true', page)
        self.assertIn("tools/schematic/build_cats_panel.py", lit)  # signals.json's reader
        for past in ("tools/schematic/split_store.py", "tools/promo/tiktok_promo.py", "tools/check.sh"):
            self.assertNotIn(past, lit)

    def test_side_survives_bridging_and_folders(self) -> None:
        """contract keeps a link's side, and a bridged link is a side link when any hop is; groupByFolder keeps side on
        a merged link only when every link in it is a side link."""
        nodes = [{"id": i} for i in ("a", "h", "b", "c")]
        edges = [{"from": "a", "to": "b", "side": "check"}, {"from": "a", "to": "h"}, {"from": "h", "to": "c", "side": "pull"},
                 {"from": "b", "to": "c"}]
        got = self.run_js("m.contract(a.nodes, a.edges, id => id === 'h').edges.map(e => e.from + e.to + ':' + (e.side || ''))",
                          {"nodes": nodes, "edges": edges})
        self.assertEqual(sorted(got), ["ab:check", "ac:pull", "bc:"])
        nodes = [{"id": f"d/{i}", "path": f"d/{i}", "domain": "x"} for i in ("p", "q")] + \
                [{"id": f"e/{i}", "path": f"e/{i}", "domain": "x"} for i in ("r", "s")] + [{"id": "f/t", "path": "f/t", "domain": "x"}]
        edges = [{"from": "d/p", "to": "e/r", "side": "check"}, {"from": "d/q", "to": "e/s", "side": "check"},
                 {"from": "d/p", "to": "f/t", "side": "pointer"}, {"from": "e/r", "to": "f/t"}]
        got = self.run_js("m.groupByFolder(a.nodes, a.edges, new Set()).edges.map(e => e.from + '>' + e.to + ':' + (e.side || ''))",
                          {"nodes": nodes, "edges": edges})
        self.assertIn("folder:d>folder:e:check", got)  # both links are checks
        self.assertIn("folder:d>f/t:pointer", got)

    def test_pointer_pick_order(self) -> None:
        """pointerPick: a box drawn under the pointer, then a grown box's drawn spot, then the hovered box's own card,
        then the hovered line, then a grown card, then a line; else nothing."""
        cases = [{"box": "b", "spot": "s", "own": "o", "hovered": 1, "card": "c", "line": 2},
                 {"spot": "s", "own": "o", "hovered": 1, "card": "c", "line": 2},
                 {"own": "o", "hovered": 1, "card": "c", "line": 2},
                 {"hovered": 0, "card": "c", "line": 0},
                 {"card": "c", "line": 2}, {"line": 0}, {"box": None, "line": None}]
        self.assertEqual(self.run_js("a.map(m.pointerPick)", cases),
                         [{"box": "b"}, {"box": "s"}, {"box": "o"}, {"edge": 0}, {"box": "c"}, {"edge": 0}, {}])

    def test_stop_kinds_and_note(self) -> None:
        """stopKind names why a chain stops at a box; stopsNote lists up to four, escaped, and counts the rest."""
        hub = "new Set(['h'])"
        nodes = [{"id": "r", "runner": True}, {"label": ".cache/x"}, {"kind": "human"}, {"domain": "hosts"},
                 {"id": "h"}, {"id": "p"}]
        self.assertEqual(self.run_js(f"a.map(n => m.stopKind(n, {hub}))", nodes),
                         ["runner", "cache", "hand work", "host", "hub", None])
        self.assertEqual(self.run_js("m.stopsNote(a)", []), "")
        note = self.run_js("m.stopsNote(a)", [["a<b>", "hub"], ["c", "runner"], ["d", "cache"], ["e", "hub"], ["f", "hub"]])
        self.assertEqual(note, '<div class="off">stops at a&lt;b&gt; (hub), c (runner), d (cache), e (hub) and 1 more</div>')

    def test_settle_start_and_transform_forms(self) -> None:
        """settleFrom: a box's old screen rect in drawing units through the screen matrix, with the scale its own width
        fills it at; boxTransform gives the SVG attribute and, with px, the CSS form the glide animates."""
        got = self.run_js("m.settleFrom({left: 110, top: 70, width: 40}, {a: 0.5, d: 0.5, e: 10, f: 20}, 40)", None)
        self.assertEqual(got, {"x": 200, "y": 100, "k": 2})
        self.assertEqual(self.run_js("[m.boxTransform({x: 1, y: 2}, 1, true), m.boxTransform({x: 1, y: 2}, 2, true)]", None),
                         ["translate(1.0px,2.0px) scale(1.0000)", "translate(1.0px,2.0px) scale(2.0000)"])

    def test_box_growth_cap(self) -> None:
        """spreadGeo and spreadFor take a cap on box growth (the lanes' room): the boxes stop there, the steps go on, and n
        steps still fill the width."""
        g = self.run_js("m.spreadGeo(m.NARROW, 3, 1.5)", None)
        self.assertEqual((g["nodeW"], g["scale"], g["nodeW"] + g["colGap"]), (270, 1.5, 3 * 260))
        self.assertEqual(self.run_js("m.spreadGeo(m.NARROW, 3, 0.5).nodeW", None), 180)  # never smaller than 1x
        span = self.run_js("(() => { const k = m.spreadFor(46, 6, m.NARROW, 1.5), g = m.spreadGeo(m.NARROW, k, 1.5);"
                           " return [5 * (g.nodeW + g.colGap) + g.nodeW, 45 * 260 + 180]; })()", None)
        self.assertLessEqual(abs(span[0] - span[1]), 5)
        self.assertAlmostEqual(self.run_js("m.spreadFor(46, 6, m.NARROW, 0.5)", None),
                               self.run_js("m.spreadFor(46, 6, m.NARROW, 1)", None))  # a cap below 1 is 1, as in spreadGeo

    def test_layout_uses_spread_geometry(self) -> None:
        """layout with spreadGeo: columns k steps apart and boxes at the spread width."""
        got = self.run_js("(() => { const g = m.spreadGeo(m.NARROW, 3), l1 = m.layout(a.nodes, a.edges, [{id: 'x'}], 0.5, m.NARROW),"
                          " l2 = m.layout(a.nodes, a.edges, [{id: 'x'}], 0.5, g);"
                          " return [(l2.nodes[1].x - l2.nodes[0].x) / (l1.nodes[1].x - l1.nodes[0].x), l2.nodes[0].w, g.nodeW]; })()",
                          {"nodes": [{"id": "a", "label": "a", "domain": "x"}, {"id": "b", "label": "b", "domain": "x"}],
                           "edges": [{"from": "a", "to": "b"}]})
        self.assertAlmostEqual(got[0], 3, places=2)
        self.assertEqual(got[1], got[2])

    def test_steps_shown(self) -> None:
        """spreadFor: n spread steps and a spread box span what all cols steps and a box span, the boxes widening up to
        BOX_GROW times; all of them, more than all, or a map of one column is 1."""
        self.assertEqual(self.run_js("[m.spreadFor(46, 46), m.spreadFor(46, 99), m.spreadFor(1, 3)]", None), [1, 1, 1])
        for n in (40, 23, 5, 3):  # below and above the box cap
            span = self.run_js(f"(() => {{ const g = m.spreadGeo(m.NARROW, m.spreadFor(46, {n})), s = x => x.nodeW + x.colGap;"
                               f" return [{n - 1} * s(g) + g.nodeW, 45 * s(m.NARROW) + m.NARROW.nodeW]; }})()", None)
            self.assertLessEqual(abs(span[0] - span[1]), 2 + 0.5 * (n - 1), n)  # each size is rounded to a whole unit

    def test_spread_geometry(self) -> None:
        """spreadGeo: a step k times as wide; the boxes grow whole (scale) with it up to BOX_GROW times, as tall as wide,
        their lines wrapping as at 1x, and the gap takes the rest; 1x is the geometry as it is."""
        g = self.run_js("m.spreadGeo(m.NARROW, 2)", None)
        self.assertEqual((g["nodeW"], g["scale"], g["titleWrap"], g["nodeW"] + g["colGap"]), (360, 2, 22, 2 * (180 + 80)))
        g = self.run_js("m.spreadGeo(m.NARROW, 6)", None)
        self.assertEqual((g["nodeW"], g["scale"], g["nodeW"] + g["colGap"]), (450, 2.5, 6 * 260))  # boxes stop at 2.5x
        self.assertEqual(self.run_js("m.spreadGeo(m.WIDE, 1) === m.WIDE", None), True)
        box = {"id": "a", "label": "a fairly long box name", "path": "x/y.py", "desc": "what it does"}
        h = self.run_js("[m.nodeHeight(a, m.NARROW), m.nodeHeight(a, m.spreadGeo(m.NARROW, 2))]", box)
        self.assertEqual(h[1], 2 * h[0])  # twice as tall too
        self.assertEqual(self.run_js("[m.boxTransform({x: 1, y: 2}), m.boxTransform({x: 1, y: 2}, 2)]", None),
                         ["translate(1.0,2.0)", "translate(1.0,2.0) scale(2.0000)"])

    def test_box_at_a_point(self) -> None:
        """boxAt: the box drawn at a point (a grown card lets the pointer through to it), edges included, else null."""
        boxes = [{"id": "a", "x": 0, "y": 0, "w": 10, "h": 5}, {"id": "b", "x": 20, "y": 0, "w": 10, "h": 5}]
        self.assertEqual(self.run_js("a.pts.map(([x, y]) => m.boxAt(a.boxes, x, y))",
                                     {"boxes": boxes, "pts": [[5, 2], [10, 5], [15, 2], [25, 4], [25, 6]]}),
                         ["a", "a", None, "b", None])

    def test_line_note_names_both_ends_escaped(self) -> None:
        """edgeTip: the note over a hovered link names its ends and label, escaped, and says when it feeds back."""
        names = {"a": "a<b>.py", "b": "out & more"}
        got = self.run_js("m.edgeTip(a[0], id => a[1][id])", [{"from": "a", "to": "b", "label": 'x "y"', "back": True}, names])
        self.assertEqual(got, '<b>a&lt;b&gt;.py</b> → <b>out &amp; more</b><div>x &quot;y&quot;</div>'
                              '<div class="off">feeds back to an earlier step</div>')
        self.assertEqual(self.run_js("m.edgeTip(a[0], id => a[1][id])", [{"from": "a", "to": "b"}, names]),
                         "<b>a&lt;b&gt;.py</b> → <b>out &amp; more</b>")

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
        return json.loads(subprocess.run([NODE, "-e", script, str(MAP.LAYOUT_JS), json.dumps(arg)], capture_output=True,
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

    def test_fit_keeps_a_margin(self) -> None:
        """fitView with pad: the drawing sits pad px inside the free area on the limiting sides, centred the other way,
        and showsAll still counts it as the whole map; clampView keeps that view as it is."""
        free = {"top": 0.1, "right": 1, "bottom": 1}
        out = self.run_js("(() => { const f = m.fitView(1000, 500, 100, a.free, 1000, 800, 28);"
                          " const c = v => m.clampView(v, 1000, 500, 100, a.free, f.width, 28 / 1000, 28 / 800);"
                          " return [f, m.showsAll(f, 1000, 500, 100, a.free), c(f),"
                          " c({...f, x: f.x + 40 * f.width / 1000}), c({...f, x: f.x - 40 * f.width / 1000})]; })()",
                          {"free": free})
        view, fits, clamped, right, left = out
        for dragged in (right, left):  # at the Fit width a drag across cannot eat the margin
            self.assertAlmostEqual(dragged["x"], view["x"], places=6)
        s = view["width"] / 1000
        left_px = (-100 - view["x"]) / s
        self.assertAlmostEqual(left_px, 28, places=3)  # width-limited: 28 px in from each side
        self.assertAlmostEqual(left_px + 1000 / s, 1000 - 28, places=3)
        self.assertAlmostEqual(-view["y"] / s, 80 + 28, places=3)  # 28 px under the step strip
        self.assertTrue(fits)
        for k in ("x", "y", "width", "height"):
            self.assertAlmostEqual(clamped[k], view[k], places=6)

    def test_fit_margin_when_height_limits_or_room_is_small(self) -> None:
        """fitView: a tall drawing is limited by height and sits pad px below the strip and above the bottom; fitPad
        keeps at most a quarter of a small area (a phone with the panel open) as margin."""
        free = {"top": 0.1, "right": 1, "bottom": 1}
        view = self.run_js("m.fitView(100, 1000, 0, a, 1000, 800, 28)", free)
        s = view["width"] / 1000
        top_px = -view["y"] / s
        self.assertAlmostEqual(top_px, 80 + 28, places=3)
        self.assertAlmostEqual(top_px + 1000 / s, 800 - 28, places=3)
        pads = self.run_js("[m.fitPad(28, a, 1000, 800), m.fitPad(28, {top: 0.9, right: 1, bottom: 0.95}, 1000, 800)]", free)
        self.assertEqual(pads[0], 28)
        self.assertAlmostEqual(pads[1], 10, places=6)  # a 40 px high area keeps 10 px each side

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


def run_main(args: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = MAP.main(args)
    return rc, out.getvalue(), err.getvalue()


class PageTest(unittest.TestCase):
    def test_check_builds_both_pages_and_writes_nothing(self) -> None:
        """The check check.sh and CI run: both pages drawn in memory and checked, no file written or compared."""
        with unittest.mock.patch.object(MAP, "write_page") as write, \
                unittest.mock.patch.object(MAP, "build", wraps=MAP.build) as build:
            rc, out, err = run_main(["--check"])
        self.assertEqual(rc, 0, err)
        self.assertIn("both pages build", out)
        write.assert_not_called()
        self.assertEqual(sorted(c.kwargs["public"] for c in build.call_args_list), [False, True])

    def test_check_refuses_an_out_file(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stop:
            MAP.main(["--check", "--public", "--out", "x.html"])
        self.assertEqual(stop.exception.code, 2)

    def test_public_needs_out(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stop:
            MAP.main(["--public"])
        self.assertEqual(stop.exception.code, 2)

    def test_plain_build_writes_both_local_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.object(MAP, "PAGE", Path(tmp, "docs/index.html")), \
                unittest.mock.patch.object(MAP, "SITE_PAGE", Path(tmp, "www/library/pipeline-map.html")):
            rc, out, err = run_main([])
            self.assertEqual(rc, 0, err)
            docs, site = MAP.PAGE.read_text(), MAP.SITE_PAGE.read_text()
        self.assertNotIn("data-ops-header", docs)
        self.assertIn("data-ops-header", site)
        self.assertIn('href="repository-guide.html"', site)
        self.assertEqual(out.count("wrote "), 2)

    def test_relative_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, contextlib.chdir(tmp):
            rc, out, err = run_main(["--public", "--out", "map.html"])
            self.assertEqual(rc, 0, err)
            self.assertIn("map.html", out)
            self.assertTrue(Path("map.html").read_text().startswith("<!doctype html>"))

    def test_site_page_is_the_checked_public_copy(self) -> None:
        page = MAP.site_page()
        self.assertIn("data-ops-header", page)
        self.assertIn(f'href="{MAP.SITE_BACK}"', page)

    def test_site_page_refuses_a_stale_graph(self) -> None:
        data = json.loads(MAP.GRAPH.read_text())
        data["edges"] = [e for e in data["edges"] if not e.get("gen")]
        with tempfile.TemporaryDirectory() as tmp:
            graph = Path(tmp, "g.json")
            graph.write_text(json.dumps(data))
            with self.assertRaisesRegex(MAP.GraphError, "lanes are generated from the files"):
                MAP.site_page(graph)

    def test_a_page_that_lost_its_parts_fails_its_check(self) -> None:
        data = MAP.load(MAP.GRAPH)
        page = MAP.render(data)
        MAP.check_page(page, data, site=False)
        cases = (
            (page.replace("const DATA = ", "const XDATA = "), "no graph data"),
            (page.replace(MAP.script_text(), ""), "does not inline " + re.escape(", ".join(p.name for p in MAP.SCRIPTS)) + "$"),
            (page.replace(MAP.script_parts()[1][1], ""), r"does not inline pipeline_map_helpers\.js$"),
            (page.replace(MAP.script_text(), "".join(t for _, t in MAP.script_parts()[::-1])), "in order, as one script"),
            (page + "__DATA__", "placeholders: __DATA__"),
            (page.replace('{"nodes":[{', '{"nodes":[{"id":"extra"},{', 1), r"holds \d+ nodes, the graph \d+"),
            (page.replace('{"nodes":[{', '{"nodes":[{"id":"extra"},{', 1).replace('"x":0}', '"x":0}', 1),
             r"not in the graph extra"),
            (page.replace('"edges":[{', '"edges":[{"to":"y"},{', 1), "malformed entry"),
        )
        for broken, why in cases:
            with self.subTest(why=why), self.assertRaisesRegex(MAP.GraphError, why):
                MAP.check_page(broken, data, site=False)
        with self.assertRaisesRegex(MAP.GraphError, "no site header"):
            MAP.check_page(page, data, site=True)

    def test_a_swapped_box_fails_even_when_the_counts_match(self) -> None:
        data = MAP.load(MAP.GRAPH)
        first, second = data["nodes"][0]["id"], data["nodes"][1]["id"]
        swapped = {**data, "nodes": [data["nodes"][1], *data["nodes"][1:]]}  # first box gone, second twice
        page = MAP.render(swapped)
        with self.assertRaisesRegex(MAP.GraphError, f"missing {re.escape(first)}"):
            MAP.check_page(page, data, site=False)
        self.assertIn(second, page)

    def test_check_fails_when_git_tracks_a_built_page(self) -> None:
        tracked = MAP.tracked_paths() | {"www/library/pipeline-map.html"}
        with unittest.mock.patch.object(MAP, "tracked_paths", return_value=tracked):
            rc, _, err = run_main(["--check"])
        self.assertEqual(rc, 1)
        self.assertIn("git rm --cached www/library/pipeline-map.html", err)

    def test_another_graph_needs_an_out_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            graph = Path(tmp, "g.json")
            graph.write_text(MAP.GRAPH.read_text())
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stop:
                MAP.main(["--graph", str(graph)])
            self.assertEqual(stop.exception.code, 2)
            self.assertIn("--out <page>", MAP.rebuild_command(graph))

    def test_a_write_that_fails_is_a_graph_error_and_exit_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp, "file")
            blocker.write_text("not a folder")
            with self.assertRaisesRegex(MAP.GraphError, "cannot write"):
                MAP.write_page(blocker / "map.html", "<p>page</p>")
            rc, _, err = run_main(["--out", str(blocker / "map.html")])
            self.assertEqual(rc, 1)
            self.assertIn("pipeline map: cannot write", err)
            self.assertNotIn("Traceback", err)

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
