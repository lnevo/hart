"""build_main_route.py: the main route worked out from main_lines_main_upper.csv and the plan graph marks the same
track as the 21 hops that were written by hand against plan part numbers, and stops where it would have to guess."""
import copy
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_main_route as M  # noqa: E402

# main_route as it was written by hand against plan 5.3c part numbers (before main_lines_main_upper.csv)
HAND_ROUTE = [
    ["McKeesport", "T281"], ["T281", "T311", "direct"], ["T311", "T294", "direct"], ["T294", "T316", "direct"],
    ["T316", "T310", "direct"], ["T310", "T283", "direct"], ["T283", "T261"], ["T261", "T307"], ["T307", "T289"],
    ["T289", "T331"], ["T331", "T322", "direct"], ["T322", "T268"], ["T268", "T270", "direct"], ["T270", "T322"],
    ["McKees Rocks", "T210"], ["T210", "T215", "direct"], ["T215", "T194"], ["T194", "T200"],
    ["T200", "T165", "direct"], ["T165", "T204"], ["T204", "T204", "direct"]]


def lines_file(tmp, *rows):
    path = Path(tmp) / "lines.csv"
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(M.COLUMNS)
    w.writerows(rows)
    path.write_text(buf.getvalue())
    return path


class RealPlan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import build_layout_le as bl
        try:
            cls.overrides = json.loads(M.OVERRIDES.read_text(encoding="utf-8"))
            cls.g, cls.node_ref = M.prepared(cls.overrides)
        except bl.BuildError as exc:
            raise unittest.SkipTest(str(exc))
        cls.plan = M.Plan(cls.g, cls.node_ref)

    def marked(self, route):
        from schematic import edits
        g = copy.deepcopy(self.g)
        edits.mark_main(g, route)
        return {e["id"] for e in g["edges"] if e["main"]}

    def test_the_derived_route_marks_what_the_hand_written_one_marked(self):
        hops = M.route(self.plan, M.read_lines())
        want = self.marked(HAND_ROUTE)
        self.assertEqual(len(want), 26)
        self.assertEqual(self.marked(hops), want)

    def test_the_file_holds_the_derived_route_and_names_no_part_number(self):
        self.assertEqual(self.overrides["main_route"], M.route(self.plan, M.read_lines()))
        names = {n for hop in self.overrides["main_route"] for n in hop[:2]}
        self.assertEqual([n for n in names if n.startswith("T") and n[1:].isdigit()], [])

    def test_parallel_tracks_nobody_declared_stop_the_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = M.read_lines()
            path = lines_file(tmp, *[[r[c] for c in M.COLUMNS[:5]] + ["", r["notes"]] for r in rows])
            with self.assertRaisesRegex(M.RouteError, "225 are joined by 2 tracks|223 and 225 are joined by 2 tracks"):
                M.route(self.plan, M.read_lines(path))

    def test_a_double_that_is_one_track_or_not_crossed_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [[r[c] for c in M.COLUMNS] for r in M.read_lines()]
            rows[0][5] = "131A-127A"
            with self.assertRaisesRegex(M.RouteError, "which has one track"):
                M.route(self.plan, M.read_lines(lines_file(tmp, *rows)))
            rows[0][5] = "201-203"
            with self.assertRaisesRegex(M.RouteError, "which the line does not cross"):
                M.route(self.plan, M.read_lines(lines_file(tmp, *rows)))

    def test_a_stop_the_plan_does_not_have_names_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [[r[c] for c in M.COLUMNS] for r in M.read_lines()]
            rows[0][3] = "999"
            with self.assertRaisesRegex(M.RouteError, "main line stop '999'"):
                M.route(self.plan, M.read_lines(lines_file(tmp, *rows)))

    def test_a_via_can_force_the_way_and_a_missing_track_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [[r[c] for c in M.COLUMNS] for r in M.read_lines()]
            rows[0][2] = "119B"      # off the main line: 123 to 119B to 119A, the way round the crossover
            hops = M.route(self.plan, M.read_lines(lines_file(tmp, *rows)))
            self.assertIn(["121B", "119B", "direct"], hops)
            rows[0][4] = "201"        # a loop that does not come back by any one track
            with self.assertRaises(M.RouteError):
                M.route(self.plan, M.read_lines(lines_file(tmp, *rows)))


class FileShape(unittest.TestCase):
    def test_columns_and_names_are_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "x.csv"
            bad.write_text("line,from\nA,B\n")
            with self.assertRaisesRegex(M.RouteError, "expected the columns"):
                M.read_lines(bad)
            with self.assertRaisesRegex(M.RouteError, "line name 'A' is empty or repeated"):
                M.read_lines(lines_file(tmp, ["A", "x", "", "y", "", "", ""], ["A", "x", "", "y", "", "", ""]))
            with self.assertRaisesRegex(M.RouteError, "from and to are both needed"):
                M.read_lines(lines_file(tmp, ["A", "", "", "y", "", "", ""]))
            with self.assertRaisesRegex(M.RouteError, "has no main line"):
                M.read_lines(lines_file(tmp))


class Ties(unittest.TestCase):
    """The shortest-way rule on a four-switch diamond, where two ways are exactly as long."""

    def plan(self, cm_top):
        nodes = {n: {"kind": "switch", "label": n} for n in "ABCD"}
        edges = [dict(id=f"e{i}", u=u, v=v, cm=cm, names=[]) for i, (u, v, cm) in
                 enumerate([("A", "B", 10), ("B", "D", 10), ("A", "C", 10), ("C", "D", cm_top)])]
        g = {"nodes": nodes, "edges": edges}

        def ref(graph, name):
            if name not in graph["nodes"]:
                raise ValueError(f"0 junctions answer to {name}")
            return name
        return M.Plan(g, ref)

    def test_two_equally_short_ways_stop_the_build(self):
        with self.assertRaisesRegex(M.RouteError, "2 equally short ways"):
            self.plan(10).shortest("A", "D")

    def test_the_shorter_way_is_taken(self):
        way = self.plan(11).shortest("A", "D")
        self.assertEqual([(a, b) for a, _, b in way], [("A", "B"), ("B", "D")])

    def test_equal_parallel_tracks_of_a_declared_double_are_no_choice(self):
        nodes = {n: {"kind": "switch", "label": n} for n in "AB"}
        g = {"nodes": nodes, "edges": [dict(id="e0", u="A", v="B", cm=52.0, names=[]),
                                       dict(id="e1", u="A", v="B", cm=52.0, names=[])]}
        plan = M.Plan(g, lambda graph, name: name)
        with self.assertRaisesRegex(M.RouteError, "2 equally short ways"):
            plan.shortest("A", "B")
        self.assertEqual([(a, b) for a, _, b in plan.shortest("A", "B", {frozenset("AB")})], [("A", "B")])

    def test_mileposts_over_a_double_track_stop(self):
        nodes = {n: {"kind": "switch", "label": n} for n in "AB"}
        g = {"nodes": nodes, "edges": [dict(id="e0", u="A", v="B", cm=52.0, names=[]),
                                       dict(id="e1", u="A", v="B", cm=52.0, names=[])]}
        plan = M.Plan(g, lambda graph, name: name)
        row = {"line": "Test", "from": "A", "via": "", "to": "B", "count": "yes"}
        with self.assertRaisesRegex(M.RouteError, "Test: the mileposts would count from A to B over a double track"):
            M.milepost_route(plan, [row])
        self.assertEqual(M.milepost_route(plan, [dict(row, count="")]), [])



def staging_file(tmp, *rows):
    path = Path(tmp) / "staging_lines.csv"
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(M.STAGING_COLUMNS)
    w.writerows(rows)
    path.write_text(buf.getvalue())
    return path


class StagingLines(unittest.TestCase):
    """main_lines_staging.csv writes the main flags of the `name` edit and the milepost_route; both match what was
    kept by hand (eight main tracks, seven milepost hops over the same track)."""

    @classmethod
    def setUpClass(cls):
        import build_layout_le as bl
        try:
            cls.overrides = json.loads(M.STAGING_OVERRIDES.read_text(encoding="utf-8"))
            cls.g, cls.node_ref = M.prepared(cls.overrides, "staging", M.STAGING_GRAPH)
        except bl.BuildError as exc:
            raise unittest.SkipTest(str(exc))
        cls.plan = M.Plan(cls.g, cls.node_ref)
        cls.rows = M.read_lines(M.STAGING_LINES, M.STAGING_COLUMNS)

    def flagged(self, text):
        edit = next(e for e in json.loads(text)["edits"] if e["op"] == "name")
        return sorted(t[2] or f"{t[0]}-{t[1]}" for t in edit["tracks"] if "main" in t[3:])

    def test_the_file_holds_what_the_lines_give(self):
        self.assertEqual(M.STAGING_OVERRIDES.read_text(encoding="utf-8"),
                         M.staging_text(self.overrides, self.plan, self.rows))

    def test_the_eight_hand_flagged_tracks_are_the_main_ones(self):
        self.assertEqual(self.flagged(M.staging_text(self.overrides, self.plan, self.rows)),
                         sorted(["Main West", "West Ext", "East Lead", "Brick-Plane", "East Ext", "Main East",
                                 "35@West Ext-39", "35@East Lead-37"]))

    def test_the_milepost_route_is_the_counted_lines_stops(self):
        hops = json.loads(M.staging_text(self.overrides, self.plan, self.rows))["milepost_route"]
        self.assertEqual(hops[0], ["1", "5"])
        self.assertEqual(hops[-2:], [["35@West Ext", "39"], ["39", "McKees Rocks"]])

    def test_a_stale_flag_is_caught_by_the_comparison(self):
        stale = json.loads(json.dumps(self.overrides))
        next(e for e in stale["edits"] if e["op"] == "name")["tracks"][2].append("main")     # S-R
        text = json.dumps(stale, indent=1, ensure_ascii=False) + "\n"
        self.assertNotEqual(text, M.staging_text(stale, self.plan, self.rows))
        self.assertEqual(M.staging_text(stale, self.plan, self.rows), M.staging_text(self.overrides, self.plan, self.rows))

    def test_a_stop_with_no_track_to_the_next_stops_with_the_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [[r[c] for c in M.STAGING_COLUMNS] for r in self.rows]
            rows[0][2] = "33;37"          # no track from 1 to 33
            with self.assertRaisesRegex(M.RouteError, "Upper level: no track joins"):
                M.staging_text(self.overrides, self.plan, M.read_lines(staging_file(tmp, *rows), M.STAGING_COLUMNS))

    def test_an_unknown_switch_names_the_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [[r[c] for c in M.STAGING_COLUMNS] for r in self.rows]
            rows[0][2] = "99"
            with self.assertRaisesRegex(M.RouteError, "main line stop '99'"):
                M.staging_text(self.overrides, self.plan, M.read_lines(staging_file(tmp, *rows), M.STAGING_COLUMNS))

    def test_count_is_yes_or_blank(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(M.RouteError, "line 2 .*count is yes or blank"):
                M.read_lines(staging_file(tmp, ["A", "1", "", "5", "", "", "", "maybe"]), M.STAGING_COLUMNS)

    def test_a_track_the_name_edit_does_not_name_stops(self):
        over = json.loads(json.dumps(self.overrides))
        edit = next(e for e in over["edits"] if e["op"] == "name")
        edit["tracks"] = [t for t in edit["tracks"] if t[2] != "Brick-Plane"]
        with self.assertRaisesRegex(M.RouteError, "does not name: (1 to 5|5 to 1)"):
            M.staging_text(over, self.plan, self.rows)



if __name__ == "__main__":
    unittest.main()
