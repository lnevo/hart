"""What the pipeline map page shows beside the graph (tools/ops/pipeline_map_eff.py, through build_pipeline_map.py): how
each step runs, writers per output, lane summaries and the links between lanes, step times; and the lane overview's
helpers in tools/ops/pipeline_map_helpers.js."""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("build_pipeline_map", ROOT / "tools/ops/build_pipeline_map.py")
assert SPEC is not None and SPEC.loader is not None
MAP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MAP)
EFF = MAP.EFF
StepRef = EFF.StepRef
NODE = shutil.which("node") or ""
DOMAINS = [{"id": "a", "label": "A", "color": "#000"}, {"id": "b", "label": "B", "color": "#111"},
           {"id": "c", "label": "C", "color": "#222"}]


def node(nid: str, kind: str = "generator", domain: str = "a", **extra) -> dict:
    return {"id": nid, "label": nid, "kind": kind, "status": "live", "domain": domain, "path": "", **extra}


def page_data(page: str) -> dict:
    return json.loads(MAP._PAGE_DATA.search(page).group(1))


class LanesTest(unittest.TestCase):
    def test_each_lane_counts_its_boxes_by_kind_status_and_steps(self) -> None:
        nodes = [node("s1", path="s1.py"), node("s2", path="s2.py"), node("o", "output", status="parked"),
                 node("h", "host", "b"), node("x", "structured", "c")]
        steps = [StepRef("panels", "one", "step", "s1", "s1.py"), StepRef("panels", "two", "guard", "s2", "s2.py"),
                 StepRef("check", "job", "step", "s2.py", "s2.py")]
        eff = EFF.node_eff(nodes, steps, {("check", "job"): {"warm_s": 3}})
        a, b, c = EFF.lanes(DOMAINS, nodes, eff)
        self.assertEqual((a["id"], a["n"], a["kinds"], a["status"]),
                         ("a", 3, {"generator": 2, "output": 1}, {"live": 2, "parked": 1}))
        self.assertEqual(a["steps"], {"panels": 2, "stamped": 1, "guards": 1, "checks": 1, "timed": 1})
        self.assertEqual((b["n"], b["kinds"], b["steps"]["panels"]), (1, {"host": 1}, 0))
        self.assertEqual(c["n"], 1)

    def test_bundles_count_the_links_between_two_lanes_each_way_and_their_side_links(self) -> None:
        nodes = [node("a1"), node("a2"), node("b1", domain="b"), node("c1", domain="c")]
        edges = [{"from": "a1", "to": "b1"}, {"from": "a2", "to": "b1", "side": "check"}, {"from": "b1", "to": "a1"},
                 {"from": "a1", "to": "a2"}, {"from": "c1", "to": "a1"}]
        self.assertEqual(EFF.bundles(nodes, edges), [
            {"from": "a", "to": "b", "n": 2, "side": 1}, {"from": "b", "to": "a", "n": 1, "side": 0},
            {"from": "c", "to": "a", "n": 1, "side": 0}])

    def test_the_real_map_bundles_add_up_to_its_cross_lane_links(self) -> None:
        data = MAP.load(MAP.GRAPH)
        lane = {n["id"]: n["domain"] for n in data["nodes"]}
        cross = [e for e in data["edges"] if lane[e["from"]] != lane[e["to"]]]
        found = EFF.bundles(data["nodes"], data["edges"])
        self.assertEqual(sum(b["n"] for b in found), len(cross))
        layout_hosts = sum(1 for e in cross if (lane[e["from"]], lane[e["to"]]) == ("layout", "hosts"))
        self.assertIn({"from": "layout", "to": "hosts", "n": layout_hosts}, [{k: b[k] for k in ("from", "to", "n")} for b in found])


class WritersTest(unittest.TestCase):
    def test_writers_are_generators_with_a_content_link_in(self) -> None:
        nodes = [node("g1"), node("g2"), node("g3"), node("data", "structured"), node("one", "output"),
                 node("two", "output"), node("none", "output"), node("seen", "output")]
        edges = [{"from": "g1", "to": "one"}, {"from": "g1", "to": "two"}, {"from": "g2", "to": "two"},
                 {"from": "data", "to": "none"},                          # not a generator
                 {"from": "g3", "to": "none", "side": "check"},           # a check reads it: writes nothing
                 {"from": "g3", "to": "seen", "side": "pointer"}, {"from": "g2", "to": "seen", "side": "pull"},
                 {"from": "g1", "to": "seen", "side": "mirror"}]          # a mirror carries content
        self.assertEqual(EFF.writers(nodes, edges, []), {"one": {"n": 1}, "two": {"n": 2}, "none": {"n": 0},
                                                         "seen": {"n": 1}})

    def test_two_writers_are_allowed_when_each_lists_the_file_in_updates_or_shared_outputs_lists_it(self) -> None:
        nodes = [node("s1"), node("s2"), node("s3"), node("plan", "output", path="plan.json"),
                 node("half", "output", path="half.json"), node("crew", "output", path="crew.json")]
        edges = [{"from": w, "to": o} for w, o in (("s1", "plan"), ("s2", "plan"), ("s1", "half"), ("s3", "half"),
                                                   ("s2", "crew"), ("s3", "crew"))]
        steps = [StepRef("panels", "one", "step", "s1", "s1.py", ("plan.json", "half.json")),
                 StepRef("panels", "two", "step", "s2", "s2.py", ("plan.json",)),
                 StepRef("check", "three", "step", "s3", "s3.py")]
        got = EFF.writers(nodes, edges, steps, frozenset({"crew.json"}))
        self.assertEqual(got, {"plan": {"n": 2, "ok": "updates"}, "half": {"n": 2}, "crew": {"n": 2, "ok": "shared"}})

    def test_the_real_map_marks_its_shared_outputs_allowed(self) -> None:
        data = page_data(MAP.build(MAP.load(MAP.GRAPH), public=False))
        w = {n["id"]: n["w"] for n in data["nodes"] if "w" in n}
        self.assertEqual(set(w), {n["id"] for n in data["nodes"] if n["kind"] == "output"})
        self.assertEqual(w["jmri/layouts/hart/data/schematic/plan_generated.json"]["ok"], "updates")
        self.assertEqual(w["www/data/crew.json"]["ok"], "shared")
        self.assertNotIn("ok", w["jmri/layouts/hart/output/tables.xml"])


class EffTest(unittest.TestCase):
    def test_a_step_is_matched_to_its_box_by_id_then_by_its_script_path(self) -> None:
        nodes = [node("box"), node("tools/x.py", path="tools/x.py"), node("other", path="tools/y.py")]
        steps = [StepRef("panels", "p1", "step", "box", "tools/b.py"), StepRef("panels", "p2", "guard", "box", "tools/c.py"),
                 StepRef("check", "c1", "step", "tools/y.py", "tools/y.py"),
                 StepRef("check", "gone", "step", "tools/z.py", "tools/z.py")]   # no box: left out
        got = EFF.node_eff(nodes, steps, {("panels", "p1"): {"warm_s": 2.5, "runs": 4}})
        self.assertEqual(got, {"box": [{"r": "panels", "s": "p1", "m": "step", "t": {"warm_s": 2.5, "runs": 4}},
                                       {"r": "panels", "s": "p2", "m": "guard"}],
                               "other": [{"r": "check", "s": "c1", "m": "step"}]})

    def test_every_manifest_step_lands_on_a_box_of_the_real_map(self) -> None:
        steps = MAP.manifest_steps()
        mf = MAP.MANIFEST_LANE.MANIFEST
        self.assertEqual(sum(s.runner == "panels" for s in steps), len(mf.panel_steps()))
        self.assertEqual(sum(s.runner == "check" for s in steps), len(mf.load()))
        self.assertEqual({s.mode for s in steps if s.runner == "check"}, {"step"})   # check.sh stamps every job
        data = MAP.load(MAP.GRAPH)
        eff = EFF.node_eff(data["nodes"], steps, {})
        self.assertEqual(sum(len(v) for v in eff.values()), len(steps))
        guards = {e["s"] for v in eff.values() for e in v if e["m"] == "guard"}
        self.assertEqual(guards, {s.name for s in mf.panel_steps() if s.mode == "guard"})


class TimingsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def write(self, data: object) -> Path:
        path = self.tmp / "timings.json"
        path.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")
        return path

    def test_no_timings_file_is_no_times(self) -> None:
        self.assertEqual(EFF.read_timings(self.tmp / "timings.json"), {})

    def test_times_are_read_by_runner_and_step(self) -> None:
        path = self.write({"updated": "x", "source": "y", "steps": {
            "panels:schematic": {"runner": "panels", "step": "schematic", "runs": 3, "warm_s": 21, "cold_s": 38,
                                 "skip_rate": 0.5, "last": "2026-11-25"},
            "check:ruff": {"runner": "check", "step": "ruff", "warm_s": 4.2, "cold_s": None}}})
        self.assertEqual(EFF.read_timings(path), {
            ("panels", "schematic"): {"runs": 3, "warm_s": 21, "cold_s": 38, "skip_rate": 0.5, "last": "2026-11-25"},
            ("check", "ruff"): {"warm_s": 4.2}})

    def test_a_broken_timings_file_is_an_error_naming_it(self) -> None:
        for data, why in (("{", "cannot read"), ({"steps": []}, "needs a \"steps\" object"),
                          ({"steps": {"make:x": {}}}, "is not <panels|check>:<step>"),
                          ({"steps": {"check:x": {"warm_s": "slow"}}}, "warm_s must be a number"),
                          ({"steps": {"check:x": {"cold_s": -1}}}, "cold_s must be a number")):
            with self.subTest(why=why), self.assertRaisesRegex(EFF.TimingsError, re.escape(why)):
                EFF.read_timings(self.write(data))

    def test_the_page_carries_times_when_the_file_has_them_and_builds_without_it(self) -> None:
        data = MAP.load(MAP.GRAPH)
        with unittest.mock.patch.object(EFF, "TIMINGS", self.tmp / "timings.json"):
            plain = page_data(MAP.build(data, public=False))
            self.assertFalse(plain["timed"])
            self.assertFalse([e for n in plain["nodes"] for e in n.get("eff", ()) if "t" in e])
            self.write({"steps": {"panels:schematic": {"warm_s": 21, "cold_s": 38}}})
            timed = page_data(MAP.build(data, public=False))
            self.assertTrue(timed["timed"])
            self.assertEqual([(n["id"], e["t"]) for n in timed["nodes"] for e in n.get("eff", ()) if "t" in e],
                             [("tools/schematic/publish_draft.py", {"warm_s": 21, "cold_s": 38})])
            self.write("{")
            with self.assertRaisesRegex(MAP.GraphError, "docs/pipeline-map/cannot read timings.json"):
                MAP.build(data, public=False)


class PageTest(unittest.TestCase):
    def test_both_pages_keep_every_box_and_link_and_add_the_lane_summaries(self) -> None:
        data = MAP.load(MAP.GRAPH)
        for public in (False, True):
            drawn = MAP.public_copy(data) if public else data
            shown = page_data(MAP.build(data, public, MAP.SITE_BACK if public else ""))
            with self.subTest(public=public):
                self.assertEqual([n["id"] for n in shown["nodes"]], [n["id"] for n in drawn["nodes"]])
                self.assertEqual([(e["from"], e["to"]) for e in shown["edges"]],
                                 [(e["from"], e["to"]) for e in drawn["edges"]])
                self.assertEqual([lane["id"] for lane in shown["lanes"]], [d["id"] for d in data["domains"]])
                self.assertEqual(sum(lane["n"] for lane in shown["lanes"]), len(data["nodes"]))
                self.assertEqual(sum(b["n"] for b in shown["bundles"]),
                                 sum(1 for e in shown["edges"] if {n["id"]: n["domain"] for n in shown["nodes"]}[e["from"]]
                                     != {n["id"]: n["domain"] for n in shown["nodes"]}[e["to"]]))

    def test_check_page_stops_a_page_whose_lane_summaries_miss_a_lane(self) -> None:
        data = MAP.load(MAP.GRAPH)
        page = MAP.render(data)
        MAP.check_page(page, data, site=False)
        shown = page_data(page)
        shown["lanes"] = shown["lanes"][:-1]
        broken = MAP._PAGE_DATA.sub(lambda _m: "<script>const DATA = " + json.dumps(shown) + ";</script>", page)
        with self.assertRaisesRegex(MAP.GraphError, "lane summaries .* do not cover the graph's"):
            MAP.check_page(broken, data, site=False)


@unittest.skipUnless(NODE, "node is not installed")
class OverviewHelpersTest(unittest.TestCase):
    def js(self, expr: str, arg: object) -> Any:
        script = f"const m = require({json.dumps(str(MAP.LAYOUT_JS))}); const a = JSON.parse(process.argv[1]); " \
                 f"console.log(JSON.stringify({expr}));"
        out = subprocess.run([NODE, "-e", script, json.dumps(arg)], capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    def test_closed_lanes_become_one_box_each_with_their_links_counted(self) -> None:
        g = {"nodes": [node("a1"), node("b1", domain="b"), node("b2", domain="b"), node("a2"), node("c1", domain="c")],
             "edges": [{"from": "a1", "to": "b1", "label": "x"}, {"from": "a1", "to": "b2"},
                       {"from": "b1", "to": "b2"}, {"from": "b2", "to": "a2", "side": "check"},
                       {"from": "a2", "to": "c1", "label": "y"}]}
        got = self.js("m.collapseLanes(a.nodes, a.edges, new Set(['a']), (d, n) => d + ':' + n)", g)
        self.assertEqual([n["id"] for n in got["nodes"]], ["a1", "lane:b", "a2", "lane:c"])
        self.assertEqual(got["nodes"][1]["label"], "b:2")
        self.assertEqual(got["members"], {"lane:b": ["b1", "b2"], "lane:c": ["c1"]})
        self.assertEqual(got["edges"], [{"from": "a1", "to": "lane:b", "label": "2 links"},
                                        {"from": "lane:b", "to": "a2", "label": "1 link", "side": "check"},
                                        {"from": "a2", "to": "lane:c", "label": "1 link"}])

    def test_the_overview_stacks_the_cards_and_puts_bundles_down_right_and_up_left(self) -> None:
        lanes = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        bundles = [{"from": "a", "to": "c", "n": 70}, {"from": "c", "to": "b", "n": 7}, {"from": "a", "to": "zz", "n": 1}]
        got = self.js("m.laneOverview(a.lanes, a.bundles, 600, 100, 20, 30)", {"lanes": lanes, "bundles": bundles})
        self.assertEqual([(c["id"], c["y"]) for c in got["cards"]], [("a", 0), ("b", 120), ("c", 240)])
        down, up = got["arcs"]   # the bundle to a lane not drawn is left out
        self.assertEqual((down["from"], down["to"], down["n"]), ("a", "c", 70))
        self.assertGreater(down["lx"], 600)    # right of the cards
        self.assertLess(up["lx"], 0)           # left of them
        self.assertGreater(down["w"], up["w"])
        self.assertEqual(got["height"], 340)
        self.assertLessEqual(got["left"], min(up["lx"], 0))
        self.assertGreaterEqual(got["left"] + got["width"], down["lx"])


if __name__ == "__main__":
    unittest.main()
