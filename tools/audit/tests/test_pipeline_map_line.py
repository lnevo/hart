"""The main line a Start button lights on the pipeline map: mainLine in tools/ops/pipeline_map_helpers.js, run under
node on small graphs and on each preset's chain in the real map."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("build_pipeline_map", ROOT / "tools/ops/build_pipeline_map.py")
assert SPEC is not None and SPEC.loader is not None
MAP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MAP)
NODE = shutil.which("node") or ""
# mainLine under node; a.stops lists the boxes where the line stops, a.up and a.down the boxes drawn on each side
SCRIPT = """const m = require(process.argv[1]); const a = JSON.parse(process.argv[2]);
const stops = new Set(a.stops), set = v => (v ? new Set(v) : null);
process.stdout.write(JSON.stringify(m.mainLine(a.edges, a.focus, { stops: id => stops.has(id), up: set(a.up), down: set(a.down) })));"""
# each preset's drawn sides and line on the real map: the sides walked as the page walks them, not on through a box
# where a hover's chain stops (hoverStop, liveHubs), and the line stopping there too
REAL = """const m = require(process.argv[1]); const a = JSON.parse(process.argv[2]);
const data = require(process.argv[3]), byId = {}, hubs = m.liveHubs(data);
data.nodes.forEach(n => (byId[n.id] = n));
const stops = id => m.hoverStop(byId[id], hubs);
const reach = (edges, focus, key, other, steps) => {
  const seen = new Set([focus]); let frontier = new Set([focus]), k = 0;
  while (frontier.size && (steps === "all" || k < steps)) {
    const next = new Set();
    edges.forEach(e => { const v = e[other]; if (frontier.has(v) && (v === focus || !stops(v)) && !seen.has(e[key])) next.add(e[key]); });
    next.forEach(v => seen.add(v)); frontier = next; k++;
  }
  return seen;
};
process.stdout.write(JSON.stringify(a.cases.map(c => {
  const up = reach(a.edges, c.focus, "from", "to", c.up), down = reach(a.edges, c.focus, "to", "from", c.down);
  const drawn = a.edges.filter(e => (up.has(e.from) || down.has(e.from)) && (up.has(e.to) || down.has(e.to)));
  return { up: [...up], down: [...down], edges: drawn, line: m.mainLine(drawn, c.focus, { stops, up, down }) };
})));"""


def links(*pairs: str, side: tuple[str, ...] = ()) -> list[dict]:
    """Links from "a>b" strings; those named in side are side links."""
    out = []
    for p in pairs:
        f, t = p.split(">")
        out.append({"from": f, "to": t, **({"side": "check"} if p in side else {})})
    return out


def run(script: str, arg: object, *extra: str) -> list:
    return json.loads(subprocess.run([NODE, "-e", script, str(MAP.HELPERS_JS), json.dumps(arg), *extra],
                                     capture_output=True, text=True, check=True).stdout)


def main_line(edges: list[dict], focus: str, stops: tuple[str, ...] = (), up: list[str] | None = None,
              down: list[str] | None = None) -> list[str]:
    return run(SCRIPT, {"edges": edges, "focus": focus, "stops": list(stops), "up": up, "down": down})


@unittest.skipUnless(NODE, "node is not installed")
class MainLineTest(unittest.TestCase):
    def test_longest_run_either_side_of_the_focus(self) -> None:
        edges = links("s1>a", "a>b", "b>f", "s2>f", "f>d1", "d1>d2", "f>e1")
        self.assertEqual(main_line(edges, "f"), ["s1", "a", "b", "f", "d1", "d2"])

    def test_ties_go_to_the_id_that_sorts_first(self) -> None:
        edges = links("y>f", "x>f", "f>q", "f>p")
        self.assertEqual(main_line(edges, "f"), ["x", "f", "p"])
        self.assertEqual(main_line(list(reversed(edges)), "f"), ["x", "f", "p"])

    def test_side_links_and_self_links_are_not_walked(self) -> None:
        edges = links("s>f", "far>s2", "s2>s", "f>f", "f>d", side=("far>s2", "s2>s"))
        self.assertEqual(main_line(edges, "f"), ["s", "f", "d"])

    def test_a_loop_is_cut_and_the_downstream_run_skips_upstream_boxes(self) -> None:
        edges = links("a>b", "b>f", "f>a", "f>d", "d>f")
        self.assertEqual(main_line(edges, "f"), ["a", "b", "f", "d"])

    def test_the_line_ends_at_a_stop_but_the_focus_never_stops_it(self) -> None:
        edges = links("s>hub", "hub>f", "f>run", "run>d")
        self.assertEqual(main_line(edges, "f", stops=("hub", "run", "f")), ["hub", "f", "run"])

    def test_each_run_stays_inside_its_own_side(self) -> None:
        """A box drawn upstream that the file also feeds (a loop) is not a downstream step when no downstream steps
        are drawn."""
        edges = links("o>p", "p>f", "f>o")
        self.assertEqual(main_line(edges, "f", up=["f", "p", "o"], down=["f"]), ["o", "p", "f"])
        self.assertEqual(main_line(edges, "f", up=["f", "p"], down=["f", "o"]), ["p", "f", "o"])

    def test_a_cut_loop_does_not_shorten_a_later_run(self) -> None:
        """A box reached first inside a loop is not remembered with the run the loop cut short."""
        edges = links("f>a", "f>b", "a>b", "b>a", "a>d", "d>e", "e>g")
        self.assertEqual(main_line(edges, "f"), ["f", "b", "a", "d", "e", "g"])

    def test_a_box_with_no_links_is_its_own_line(self) -> None:
        self.assertEqual(main_line([], "f"), ["f"])

    def test_each_preset_line_runs_through_its_file_on_drawn_links(self) -> None:
        """On the real map every preset's line is a run of links through its file, each box inside the steps drawn on
        its side."""
        data = json.loads(MAP.GRAPH.read_text(encoding="utf-8"))
        live = {n["id"] for n in data["nodes"] if n.get("status", "live") == "live"}
        edges = [e for e in data["edges"] if e["from"] in live and e["to"] in live and not e.get("side")]
        cases = [{"focus": pr["focus"], "up": pr["up"], "down": pr["down"]} for pr in data["presets"]]
        got = run(REAL, {"edges": edges, "cases": cases}, str(MAP.GRAPH))
        lines = [g["line"] for g in got]
        for pr, g, line in zip(data["presets"], got, lines):
            with self.subTest(preset=pr["label"]):
                pairs = {(e["from"], e["to"]) for e in g["edges"]}
                at = line.index(pr["focus"])
                self.assertEqual(len(set(line)), len(line))
                self.assertTrue(all((a, b) in pairs for a, b in zip(line, line[1:])))
                self.assertLessEqual(set(line[:at]), set(g["up"]))
                self.assertLessEqual(set(line[at:]), set(g["down"]))
                if pr["up"] and any(t == pr["focus"] for _, t in pairs):
                    self.assertGreater(at, 0, "a file with inputs drawn has an upstream run")
        self.assertEqual(lines[[p["label"] for p in data["presets"]].index("Car cards")][-1], "ops/car-cards/print")


# presetLine, presetAlso and withLine under node: a.presets, a.focus; a.drawn and a.all as {nodes, edges}
NAMED = """const m = require(process.argv[1]); const a = JSON.parse(process.argv[2]);
const line = m.presetLine(a.presets, a.focus), also = m.presetAlso(a.presets, a.focus);
process.stdout.write(JSON.stringify({ line, also, drawn: line && m.withLine(a.drawn.nodes, a.drawn.edges, a.all, line, also) }));"""


def named(presets: list[dict], focus: str, drawn: dict, every: dict) -> dict:
    return json.loads(subprocess.run([NODE, "-e", NAMED, str(MAP.HELPERS_JS),
                                      json.dumps({"presets": presets, "focus": focus, "drawn": drawn, "all": every})],
                                     capture_output=True, text=True, check=True).stdout)


class PresetLineCheckTest(unittest.TestCase):
    """line_problems: a preset's own line in build_pipeline_map.py."""
    IDS = {"a", "b", "f", "d"}
    EDGES = {("a", "b"), ("b", "f"), ("f", "d")}

    def problems(self, line: object, focus: str = "f") -> list[str]:
        return MAP.line_problems(line, focus, self.IDS, self.EDGES)

    def test_a_linked_line_through_the_focus_passes(self) -> None:
        self.assertEqual(self.problems(["a", "b", "f", "d"]), [])
        self.assertEqual(self.problems(["f"]), [])

    def test_the_focus_must_be_on_the_line(self) -> None:
        self.assertEqual(self.problems(["a", "b"]), ["line does not hold the focus 'f'"])

    def test_each_pair_needs_a_link_that_way(self) -> None:
        self.assertEqual(self.problems(["a", "f", "d"]), ["line: no link from 'a' to 'f'"])
        self.assertEqual(self.problems(["d", "f"]), ["line: no link from 'd' to 'f'"])

    def test_unknown_ids_repeats_and_a_bad_shape(self) -> None:
        self.assertEqual(self.problems(["x", "f"]), ["line: 'x' is not a node"])
        self.assertEqual(self.problems(["f", "d", "f"]),
                         ["line: 'f' is listed twice", "line: no link from 'd' to 'f'"])
        for bad in ([], "f", [1]):
            self.assertEqual(self.problems(bad), ["line must be a list of node ids"])

    def test_load_reports_a_bad_line_by_preset(self) -> None:
        data = json.loads(MAP.GRAPH.read_text(encoding="utf-8"))
        pr = data["presets"][0]
        pr["line"] = list(reversed(pr["line"]))
        with self.assertRaisesRegex(MAP.GraphError, f"preset {pr['label']!r}: line: no link from"):
            MAP.validate(data, tracked=False)

    def test_two_lines_may_not_share_a_focus(self) -> None:
        data = json.loads(MAP.GRAPH.read_text(encoding="utf-8"))
        data["presets"].append(dict(data["presets"][0], label="Copy"))
        with self.assertRaisesRegex(MAP.GraphError, "preset 'Copy': focus .* already has a line in preset"):
            MAP.validate(data, tracked=False)

    def test_every_preset_on_the_real_map_names_a_valid_line(self) -> None:
        data = json.loads(MAP.GRAPH.read_text(encoding="utf-8"))
        ids = {n["id"] for n in data["nodes"]}
        edges = {(e["from"], e["to"]) for e in data["edges"]}
        for pr in data["presets"]:
            with self.subTest(preset=pr["label"]):
                self.assertIn("line", pr)
                self.assertEqual(MAP.line_problems(pr["line"], pr["focus"], ids, edges), [])
                self.assertEqual(MAP.also_problems(pr.get("also", []), pr["line"], ids, edges), [])


class PresetAlsoCheckTest(unittest.TestCase):
    """also_problems: the boxes a preset lights beside its line."""
    IDS = {"a", "f", "d", "s", "t"}
    EDGES = {("a", "f"), ("f", "d"), ("f", "s")}

    def problems(self, also: object, line: object = ("a", "f", "d")) -> list[str]:
        return MAP.also_problems(also, list(line) if isinstance(line, tuple) else line, self.IDS, self.EDGES)

    def test_a_box_linked_to_the_line_passes(self) -> None:
        self.assertEqual(self.problems(["s"]), [])
        self.assertEqual(self.problems([]), [])

    def test_each_box_needs_a_link_to_the_line_and_must_be_off_it(self) -> None:
        self.assertEqual(self.problems(["t"]), ["also: 't' has no link to or from the line"])
        self.assertEqual(self.problems(["d"]), ["also: 'd' is on the line"])
        self.assertEqual(self.problems(["x", "s", "s"]), ["also: 'x' is not a node", "also: 's' is listed twice"])

    def test_a_bad_shape_or_no_line(self) -> None:
        self.assertEqual(self.problems("s"), ["also must be a list of node ids"])
        self.assertEqual(self.problems(["s"], line=None), ["also needs a line"])


@unittest.skipUnless(NODE, "node is not installed")
class NamedLineDrawTest(unittest.TestCase):
    """presetLine finds the preset's own line; withLine adds the line's missing boxes and links to the drawing."""
    EVERY = {"nodes": [{"id": v} for v in "abfdx"], "edges": links("a>b", "b>f", "f>d", "x>f", "a>x")}

    def test_missing_boxes_and_links_join_the_drawing(self) -> None:
        drawn = {"nodes": [{"id": "f", "kept": 1}, {"id": "x"}], "edges": links("x>f")}
        got = named([{"focus": "f", "line": ["a", "b", "f", "d"]}], "f", drawn, self.EVERY)
        self.assertEqual(got["line"], ["a", "b", "f", "d"])
        self.assertEqual(got["drawn"]["nodes"], [{"id": "f", "kept": 1}, {"id": "x"}, {"id": "a"}, {"id": "b"}, {"id": "d"}])
        self.assertEqual([(e["from"], e["to"]) for e in got["drawn"]["edges"]], [("x", "f"), ("a", "b"), ("b", "f"), ("f", "d")])

    def test_a_link_already_drawn_or_listed_twice_is_added_once(self) -> None:
        every = {"nodes": self.EVERY["nodes"], "edges": self.EVERY["edges"] + links("f>d")}
        drawn = {"nodes": [{"id": "b"}, {"id": "f"}], "edges": links("b>f")}
        got = named([{"focus": "f", "line": ["b", "f", "d"]}], "f", drawn, every)
        self.assertEqual([(e["from"], e["to"]) for e in got["drawn"]["edges"]], [("b", "f"), ("f", "d")])

    def test_boxes_beside_the_line_join_with_their_links(self) -> None:
        drawn = {"nodes": [{"id": "f"}], "edges": []}
        got = named([{"focus": "f", "line": ["b", "f"], "also": ["x"]}], "f", drawn, self.EVERY)
        self.assertEqual(got["also"], ["x"])
        self.assertEqual([n["id"] for n in got["drawn"]["nodes"]], ["f", "b", "x"])
        self.assertEqual([(e["from"], e["to"]) for e in got["drawn"]["edges"]], [("b", "f"), ("x", "f")])

    def test_no_line_named_falls_back(self) -> None:
        empty = {"nodes": [], "edges": []}
        self.assertIsNone(named([{"focus": "f", "up": 1}], "f", empty, empty)["line"])
        self.assertIsNone(named([{"focus": "g", "line": ["g"]}], "f", empty, empty)["line"])


if __name__ == "__main__":
    unittest.main()
