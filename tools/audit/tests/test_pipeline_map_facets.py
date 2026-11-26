"""The pipeline map page's filters, search, trail and status line (tools/ops/pipeline_map_facets.js), run under node:
the address keys round-trip and older share links still load, facets combine (OR within, AND across) and count, search
ranks the label before the path and the description, and the trail and status line read as they should."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("build_pipeline_map", ROOT / "tools/ops/build_pipeline_map.py")
assert SPEC is not None and SPEC.loader is not None
MAP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MAP)
NODE = shutil.which("node") or ""
# the values the page knows for each facet (pipeline_map_view_rail.js, KNOWN), cut down
KNOWN = {"lane": ["a", "b", "c"], "kind": ["structured", "generator", "output", "host"],
         "status": ["live", "parked", "retired"], "step": ["stamped", "guard", "none"],
         "writers": ["one", "many", "none"], "side": ["data", "check", "pointer"]}


def js(expr: str, data: Any = None) -> Any:
    """expr evaluated under node with m = pipeline_map_facets.js and d = data; F({...}) makes a filter from lists, and
    Sets come back as lists."""
    script = (
        "const m = require(process.argv[1]);"
        "const F = o => Object.assign(m.emptyFacets(), Object.fromEntries(Object.entries(o).map(([k, v]) => [k, new Set(v)])));"
        "const J = v => JSON.stringify(v, (k, x) => (x instanceof Set ? [...x] : x)); let s = '';"
        "process.stdin.on('data', c => (s += c)).on('end', () => { const d = JSON.parse(s);"
        f"process.stdout.write(J({expr})); }});"
    )
    out = subprocess.run([NODE, "-e", script, str(MAP.FACETS_JS)], input=json.dumps(data), capture_output=True, text=True,
                         check=True)
    return json.loads(out.stdout)


def box(nid: str, kind: str = "generator", domain: str = "a", **extra: Any) -> dict:
    return {"id": nid, "label": nid, "kind": kind, "status": "live", "domain": domain, "path": "", **extra}


def read(hash_: str) -> dict:
    """The filters an address loads, as {facet: sorted values} plus hide."""
    got = js("m.readFacets(new URLSearchParams(d.h), d.k)", {"h": hash_, "k": KNOWN})
    return {**{k: sorted(v) for k, v in got["f"].items() if v}, "hide": got["hide"]}


@unittest.skipUnless(NODE, "node is not installed")
class AddressTest(unittest.TestCase):
    def test_every_filter_key_round_trips_through_the_address(self) -> None:
        f = {"lane": ["b", "a"], "kind": ["output"], "status": ["parked"], "step": ["guard", "stamped"],
             "writers": ["many"], "side": ["check"]}
        text = js("(() => { const h = new URLSearchParams(); m.writeFacets(h, F(d), true); return h.toString(); })()", f)
        self.assertEqual(text, "lanes=b%2Ca&kind=output&status=parked&step=guard%2Cstamped&writers=many&side=check&rest=hide")
        self.assertEqual(read(text), {**{k: sorted(v) for k, v in f.items()}, "hide": True})

    def test_no_filter_writes_nothing_and_unknown_values_are_dropped(self) -> None:
        self.assertEqual(js("(() => { const h = new URLSearchParams(); m.writeFacets(h, m.emptyFacets(), false); return h.toString(); })()"), "")
        self.assertEqual(read("kind=output,script&lanes=zz&step=maybe"), {"kind": ["output"], "hide": False})

    def test_older_share_links_still_load(self) -> None:
        # hidekind: the kinds that were left out and bridged over; the rest are kept, with Hide the rest so it looks the same
        self.assertEqual(read("lanes=a,b&hidekind=generator,host&show=parked"),
                         {"lane": ["a", "b"], "kind": ["output", "structured"], "status": ["live", "parked"], "hide": True})
        self.assertEqual(read("hide=retired"), {"status": ["live", "parked"], "hide": False})  # shown unless named
        self.assertEqual(read("focus=x&dir=up&depth=2"), {"status": ["live", "parked", "retired"], "hide": False})
        self.assertEqual(read("show=retired"), {"status": ["live", "retired"], "hide": False})
        self.assertEqual(read("lanes=none"), {"hide": False})  # no lane named: every lane
        self.assertEqual(read("status=parked&show=retired"), {"status": ["parked"], "hide": False})  # the new key wins

    def test_an_address_of_overlay_pointer_and_steps_keys_is_the_overview(self) -> None:
        overview = lambda h: js("m.isOverviewHash(new URLSearchParams(d))", h)
        self.assertEqual([overview(h) for h in ("", "eff=1&hover=0", "steps=5&cap=1.5", "steps=5&lane=a", "map=all")],
                         [True, True, True, False, False])

    def test_a_shared_selection_may_be_a_box_folder_or_closed_lane(self) -> None:
        got = js("d.map(id => m.selectableId(id, x => x === 'box'))", ["box", "folder:tools/", "lane:wiring", "nope", ""])
        self.assertEqual(got, [True, True, True, False, False])


@unittest.skipUnless(NODE, "node is not installed")
class FacetTest(unittest.TestCase):
    def match(self, n: dict, f: dict) -> bool:
        return js("m.boxMatches(m.boxValues(d.n), F(d.f))", {"n": n, "f": f})

    def test_values_or_within_a_facet_and_facets_and_together(self) -> None:
        n = box("x", "output", "b")
        self.assertTrue(self.match(n, {}))
        self.assertTrue(self.match(n, {"kind": ["generator", "output"]}))
        self.assertTrue(self.match(n, {"kind": ["output"], "lane": ["a", "b"]}))
        self.assertFalse(self.match(n, {"kind": ["output"], "lane": ["a"]}))
        self.assertFalse(self.match(n, {"kind": ["generator"]}))

    def test_step_type_and_writers(self) -> None:
        both = box("s", eff=[{"m": "step"}, {"m": "guard"}])
        self.assertEqual(js("m.boxValues(d)", both)["step"], ["stamped", "guard"])
        self.assertEqual(js("m.boxValues(d)", box("p"))["step"], ["none"])
        self.assertTrue(self.match(both, {"step": ["guard"]}))
        self.assertFalse(self.match(box("p"), {"step": ["guard", "stamped"]}))
        # writers are on outputs only: a box without a count never passes a writers filter
        self.assertEqual([js("m.boxValues(d)", box("o", "output", w={"n": k}))["writers"] for k in (0, 1, 3)],
                         [["none"], ["one"], ["many"]])
        self.assertFalse(self.match(box("g"), {"writers": ["none"]}))

    def test_the_list_s_time_is_the_slowest_timed_step(self) -> None:
        eff = [{"s": "a", "t": {"warm_s": 2}}, {"s": "none"}, {"s": "b", "t": {"cold_s": 9}}, {"s": "c", "t": {"warm_s": 4}}]
        self.assertEqual(js("m.slowestStep(d, t => t.warm_s ?? t.cold_s ?? null).s", eff), "b")
        self.assertIsNone(js("m.slowestStep(d, t => null)", [{"s": "x"}]))

    def test_only_keeps_one_value_and_a_second_click_clears_the_facet(self) -> None:
        self.assertEqual(js("m.onlyValue(new Set(['a', 'b']), 'b')"), ["b"])
        self.assertEqual(js("m.onlyValue(new Set(), 'b')"), ["b"])
        self.assertEqual(js("m.onlyValue(new Set(['b']), 'b')"), [])

    def test_status_draws_live_alone_until_one_is_ticked(self) -> None:
        drawn = lambda f, hide=False: sorted(js("m.drawnStatus(F(d.f), d.h)", {"f": f, "h": hide}))
        self.assertEqual(drawn({}), ["live"])
        self.assertEqual(drawn({"status": ["parked"]}), ["live", "parked"])  # live drawn faded
        self.assertEqual(drawn({"status": ["parked"]}, True), ["parked"])
        self.assertEqual(sorted(js("m.withStatus(F({}), false, 'retired')")), ["live", "retired"])
        self.assertEqual(sorted(js("m.withStatus(F({status: ['parked']}), true, 'live')")), ["live", "parked"])

    def test_counts_give_each_value_its_boxes_and_those_left_with_the_other_facets(self) -> None:
        nodes = [box("g1"), box("g2", domain="b"), box("o1", "output"), box("o2", "output", "b"),
                 box("p", "output", status="parked")]
        counts = js("m.facetCounts(d.n, F(d.f), false)", {"n": nodes, "f": {"lane": ["b"]}})
        self.assertEqual(counts["kind"], {"generator": [2, 1], "output": [2, 1]})  # the parked one is not drawn
        self.assertEqual(counts["lane"], {"a": [2, 2], "b": [2, 2]})  # a facet's own ticks do not cut its counts
        self.assertEqual(counts["status"], {"live": [4, 2], "parked": [1, 0]})
        sides = js("m.sideCounts(d.e, id => id !== 'g1')", {"e": [{"from": "g1", "to": "o1"}, {"from": "g2", "to": "o2"},
                                                                   {"from": "g2", "to": "o1", "side": "check"}]})
        self.assertEqual(sides, {"data": [2, 1], "check": [1, 1]})

    def test_the_real_map_counts_add_up_to_its_boxes(self) -> None:
        data = MAP.load(MAP.GRAPH)
        extras = MAP.page_extras(data)  # the step and writer marks the page carries
        shown = [{**n, **{k: extras[k][n["id"]] for k in ("eff", "w") if n["id"] in extras[k]}} for n in data["nodes"]]
        counts = js("m.facetCounts(d, m.emptyFacets(), false)", shown)
        live = sum(1 for n in data["nodes"] if n.get("status", "live") == "live")
        for facet in ("lane", "kind"):
            self.assertEqual(sum(a for a, _ in counts[facet].values()), live, facet)
        self.assertEqual(sum(a for a, _ in counts["status"].values()), len(data["nodes"]))
        self.assertGreater(counts["step"]["stamped"][0], 0)
        self.assertEqual(sum(a for a, _ in counts["writers"].values()),
                         sum(1 for n in shown if "w" in n and n.get("status", "live") == "live"))


@unittest.skipUnless(NODE, "node is not installed")
class SearchTest(unittest.TestCase):
    def test_label_beats_path_beats_description(self) -> None:
        nodes = [box("d", desc="writes tables.xml"), box("p", path="out/tables.xml"),
                 {**box("sub"), "label": "gen_tables.xml.py"}, {**box("pre"), "label": "tables.xml.bak"},
                 {**box("x"), "label": "tables.xml"}, box("none")]
        self.assertEqual(js("m.searchHits(d, '  Tables.XML ')", nodes), ["x", "pre", "sub", "p", "d"])
        self.assertEqual(js("d.map(n => m.searchRank(n, 'tables.xml'))", nodes), [4, 3, 2, 1, 0, -1])
        self.assertEqual(js("m.searchHits(d, '')", nodes), [])

    def test_ties_go_to_live_boxes_then_shorter_names(self) -> None:
        nodes = [{**box("a", status="parked"), "label": "make a"}, {**box("b"), "label": "make bb"},
                 {**box("c"), "label": "make c"}]
        self.assertEqual(js("m.searchHits(d, 'make')", nodes), ["c", "b", "a"])


@unittest.skipUnless(NODE, "node is not installed")
class TrailTest(unittest.TestCase):
    def trail(self, d: dict) -> list:
        return js("m.trail(d, l => l.toUpperCase(), 'tables.xml')", d)

    def test_each_level_and_where_esc_goes(self) -> None:
        ov = self.trail({"overview": True, "lanes": [], "focus": None})
        self.assertEqual(ov, [{"label": "All lanes", "to": None}])
        lanes = self.trail({"overview": False, "lanes": ["a", "b"], "focus": None})
        self.assertEqual([c["label"] for c in lanes], ["All lanes", "A + B"])
        whole = self.trail({"overview": False, "lanes": [], "focus": None})
        self.assertEqual([c["label"] for c in whole], ["All lanes", "Whole map"])
        file = self.trail({"overview": False, "lanes": ["b"], "focus": "x", "focusLane": "a"})
        self.assertEqual(file, [{"label": "All lanes", "to": {"overview": True}}, {"label": "A", "to": {"lanes": ["a"]}},
                                {"label": "tables.xml", "to": None}])
        self.assertEqual([js("m.upFrom(d)", t) for t in (ov, lanes, file)], [None, {"overview": True}, {"lanes": ["a"]}])

    def test_status_line(self) -> None:
        line = lambda **s: js("m.statusLine(d)", {"boxes": 0, "faded": 0, "hidden": 0, "parked": 0, "retired": 0, **s})
        self.assertEqual(line(boxes=617, liveOnly=True, parked=27, retired=2),
                         "Showing 617 live boxes, 29 parked or retired hidden")
        self.assertEqual(line(boxes=617, liveOnly=True, faded=576, parked=27), "Showing 617 live boxes, 576 faded by the filters, 27 parked hidden")
        self.assertEqual(line(boxes=1, hidden=40, extra=["grouped by folder"]), "Showing 1 box, 40 hidden by the filters, grouped by folder")

    def test_long_lists_group_by_kind_in_the_legend_s_order(self) -> None:
        items = [{"id": f"{k}{i}"} for i, k in enumerate("ogsgogsgo")]
        kinds = {"o": "output", "g": "generator", "s": "structured"}
        got = js("m.groupByKind(d.items, id => d.kinds[id[0]], ['structured', 'generator', 'output'])",
                 {"items": items, "kinds": kinds})
        self.assertEqual([(g["kind"], len(g["items"])) for g in got], [("structured", 2), ("generator", 4), ("output", 3)])
        self.assertEqual(js("m.groupByKind(d.slice(0, 8), () => 'x', [])", items)[0]["kind"], None)


if __name__ == "__main__":
    unittest.main()
