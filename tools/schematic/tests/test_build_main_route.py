"""build_main_route.py: the main route worked out from the main_upper rows of main_lines.csv and the plan graph marks
the same track as the 21 hops written by hand against plan part numbers, and stops where it would have to guess."""
import copy
import csv
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_main_route as M  # noqa: E402

# The main route as 21 hops written by hand against plan 5.3c part numbers, its helix tracks by their plan names.
# The route derived from main_lines.csv must mark the same track.
HAND_ROUTE = [
    ["Helix Inner", "T281"], ["T281", "T311", "direct"], ["T311", "T294", "direct"], ["T294", "T316", "direct"],
    ["T316", "T310", "direct"], ["T310", "T283", "direct"], ["T283", "T261"], ["T261", "T307"], ["T307", "T289"],
    ["T289", "T331"], ["T331", "T322", "direct"], ["T322", "T268"], ["T268", "T270", "direct"], ["T270", "T322"],
    ["Helix Outer", "T210"], ["T210", "T215", "direct"], ["T215", "T194"], ["T194", "T200"],
    ["T200", "T165", "direct"], ["T165", "T204"], ["T204", "T204", "direct"]]


def lines_file(tmp, *rows):
    path = Path(tmp) / "lines.csv"
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(M.COLUMNS)
    w.writerows(rows)
    path.write_text(buf.getvalue())
    return path


def file_rows(sheet):
    """The committed main_lines.csv's rows of `sheet` as written. Their stops name tracks by block id, as a copy of the
    file must; read_lines gives the same stops back by name."""
    with open(M.LINES, newline="", encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r["sheet"] == sheet]


class RealPlan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import build_layout_le as bl
        try:
            cls.overrides = M.layer_files.read("plan_overrides", "main_upper", M.pd.DATA)
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
        hops = M.route(self.plan, M.read_lines("main_upper"))
        want = self.marked(HAND_ROUTE)
        self.assertEqual(len(want), 26)
        self.assertEqual(self.marked(hops), want)

    def test_the_file_holds_the_derived_route_and_names_no_part_number(self):
        self.assertEqual(M.layer_files.read(M.layer_files.GENERATED, "main_upper", M.pd.DATA)["main_route"], M.route(self.plan, M.read_lines("main_upper")))
        names = {n for hop in M.layer_files.read(M.layer_files.GENERATED, "main_upper", M.pd.DATA)["main_route"] for n in hop[:2]}
        self.assertEqual([n for n in names if n.startswith("T") and n[1:].isdigit()], [])

    def test_parallel_tracks_nobody_declared_stop_the_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = file_rows("main_upper")
            path = lines_file(tmp, *[[r[c] for c in M.COLUMNS[:6]] + ["", "", r["notes"]] for r in rows])
            with self.assertRaisesRegex(M.RouteError, "225 are joined by 2 tracks|223 and 225 are joined by 2 tracks"):
                M.route(self.plan, M.read_lines("main_upper", path))

    def test_a_double_that_is_one_track_or_not_crossed_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [[r[c] for c in M.COLUMNS] for r in file_rows("main_upper")]
            rows[0][6] = "131A-127A"
            with self.assertRaisesRegex(M.RouteError, "which has one track"):
                M.route(self.plan, M.read_lines("main_upper", lines_file(tmp, *rows)))
            rows[0][6] = "201-203"
            with self.assertRaisesRegex(M.RouteError, "which the line does not cross"):
                M.route(self.plan, M.read_lines("main_upper", lines_file(tmp, *rows)))

    def test_a_stop_the_plan_does_not_have_names_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [[r[c] for c in M.COLUMNS] for r in file_rows("main_upper")]
            rows[0][4] = "999"
            with self.assertRaisesRegex(M.RouteError, "main line stop '999'"):
                M.route(self.plan, M.read_lines("main_upper", lines_file(tmp, *rows)))

    def test_a_via_can_force_the_way_and_a_missing_track_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [[r[c] for c in M.COLUMNS] for r in file_rows("main_upper")]
            rows[0][3] = "119B"      # off the main line: 123 to 119B to 119A, the way round the crossover
            hops = M.route(self.plan, M.read_lines("main_upper", lines_file(tmp, *rows)))
            self.assertIn(["121B", "119B", "direct"], hops)
            rows[0][5] = "201"        # a loop that does not come back by any one track
            with self.assertRaises(M.RouteError):
                M.route(self.plan, M.read_lines("main_upper", lines_file(tmp, *rows)))


class FileShape(unittest.TestCase):
    def test_columns_and_names_are_checked(self):
        mu = ["main_upper", "A", "x", "", "y", "", "", "", ""]
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "x.csv"
            bad.write_text("line,from\nA,B\n")
            with self.assertRaisesRegex(M.RouteError, "expected the columns"):
                M.read_lines("main_upper", bad)
            with self.assertRaisesRegex(M.RouteError, "line name 'A' is empty or repeated on sheet main_upper"):
                M.read_lines("main_upper", lines_file(tmp, mu, mu))
            with self.assertRaisesRegex(M.RouteError, "from and to are both needed"):
                M.read_lines("main_upper", lines_file(tmp, ["main_upper", "A", "", "", "y", "", "", "", ""]))
            with self.assertRaisesRegex(M.RouteError, "has no main line on sheet main_upper"):
                M.read_lines("main_upper", lines_file(tmp))

    def test_one_name_may_serve_two_sheets(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = lines_file(tmp, ["staging", "A", "1", "", "5", "", "", "", ""],
                              ["main_upper", "A", "x", "", "y", "", "", "", ""])
            self.assertEqual([r["sheet"] for r in M.read_lines("staging", path)], ["staging"])
            self.assertEqual([r["sheet"] for r in M.read_lines("main_upper", path)], ["main_upper"])

    def test_a_bad_sheet_stops_the_whole_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = lines_file(tmp, ["main_upper", "A", "x", "", "y", "", "", "", ""],
                              ["mainline", "B", "x", "", "y", "", "", "", ""])
            with self.assertRaisesRegex(M.RouteError, "line 3: sheet 'mainline' is not one of"):
                M.read_lines("main_upper", path)
        with self.assertRaisesRegex(M.RouteError, "unknown sheet 'upper'"):
            M.read_lines("upper")

    def test_count_is_read_on_staging_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(M.RouteError, "count is only read on the staging sheet"):
                M.read_lines("staging", lines_file(tmp, ["main_upper", "A", "x", "", "y", "", "", "yes", ""],
                                                   ["staging", "B", "1", "", "5", "", "", "", ""]))

    def test_loop_and_double_are_read_on_main_upper_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(M.RouteError, "loop and double are only read on the main_upper sheet"):
                M.read_lines("staging", lines_file(tmp, ["staging", "A", "1", "", "5", "", "33-35", "", ""]))

    def test_a_short_row_names_its_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(M.RouteError, "line 2: expected 9 cells"):
                M.read_lines("main_upper", lines_file(tmp, ["main_upper", "A", "x", "", "y", "", "", ""]))

    def test_a_padded_sheet_is_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = lines_file(tmp, ["staging ", "A", "1", "", "5", "", "", "", ""])
            self.assertEqual(M.read_lines("staging", path)[0]["sheet"], "staging")



class Ties(unittest.TestCase):
    """The shortest-way rule on a four-switch diamond, where two ways are exactly as long."""

    def plan(self, cm_top):
        nodes = {n: {"kind": "switch", "label": n} for n in "ABCD"}
        edges = [dict(id=f"e{i}", u=u, v=v, cm=cm, names=[]) for i, (u, v, cm) in
                 enumerate([("A", "B", 10), ("B", "D", 10), ("A", "C", 10), ("C", "D", cm_top)])]
        g = {"nodes": nodes, "edges": edges}

        def ref(graph, name):
            if name not in graph["nodes"]:
                raise M.RouteError(f"0 junctions answer to {name}")
            return name
        return M.Plan(g, ref)

    def test_an_unknown_stop_is_named_and_a_bug_in_the_lookup_is_not_reworded(self):
        plan = self.plan(11)
        with self.assertRaisesRegex(M.RouteError, "main line stop 'Z': 0 junctions answer to Z"):
            plan.node("Z")
        broken = M.Plan(plan.g, lambda graph, name: graph["missing"][name])
        with self.assertRaises(KeyError):
            broken.node("A")

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
    """A main_lines.csv whose rows are staging rows (given without the sheet column)."""
    return lines_file(tmp, *(["staging", *r] for r in rows))


STAGING_COLUMNS = M.COLUMNS[1:]


class StagingLines(unittest.TestCase):
    """main_lines.csv's staging rows write the main runs (the name store flags them in the `name` edit) and the milepost_route; both match what was
    kept by hand (eight main tracks, seven milepost hops over the same track)."""

    @classmethod
    def setUpClass(cls):
        import build_layout_le as bl
        try:
            cls.overrides = M.layer_files.read("plan_overrides", "staging", M.pd.DATA)
            cls.g, cls.node_ref = M.prepared(cls.overrides, "staging", M.STAGING_GRAPH)
        except bl.BuildError as exc:
            raise unittest.SkipTest(str(exc))
        cls.plan = M.Plan(cls.g, cls.node_ref)
        cls.rows = M.read_lines("staging")

    def test_the_file_holds_what_the_lines_give(self):
        have = M.layer_files.read(M.layer_files.GENERATED, "staging", M.pd.DATA)
        self.assertEqual({k: have[k] for k in M.staging_keys(self.overrides, self.plan, self.rows)},
                         M.staging_keys(self.overrides, self.plan, self.rows))

    def test_the_hand_file_holds_no_name_edit_and_no_milepost_route(self):
        self.assertFalse([e for e in self.overrides["edits"] if e["op"] == "name"])
        self.assertNotIn("milepost_route", self.overrides)

    def test_the_eight_main_tracks_are_the_runs_the_hand_file_flagged(self):
        """The eight tracks flagged main by hand before the lines were the source, by their runs (block IDs' ends):
        Main West, Brick-Plane, West Ext, East Lead, the two tracks inside Switch 35's crossover to 37 and 39, East Ext
        and Main East."""
        self.assertEqual(M.staging_keys(self.overrides, self.plan, self.rows)["name_main"],
                         ["1A-23A", "1C-5A", "23B-35B", "33A-35A", "35A-39A", "35B-37A", "5B-7A", "7B-33C"])

    def test_the_milepost_route_is_the_counted_lines_stops(self):
        hops = M.staging_keys(self.overrides, self.plan, self.rows)["milepost_route"]
        self.assertEqual(hops[0], ["1", "5"])
        self.assertEqual(hops[-2:], [["35@West Ext", "39"], ["39", "Helix Outer"]])

    def test_a_stop_with_no_track_to_the_next_stops_with_the_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [[r[c] for c in STAGING_COLUMNS] for r in file_rows("staging")]
            rows[0][2] = "33;37"          # no track from 1 to 33
            with self.assertRaisesRegex(M.RouteError, "Upper level: no track joins"):
                M.staging_keys(self.overrides, self.plan, M.read_lines("staging", staging_file(tmp, *rows)))

    def test_an_unknown_switch_names_the_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [[r[c] for c in STAGING_COLUMNS] for r in file_rows("staging")]
            rows[0][2] = "99"
            with self.assertRaisesRegex(M.RouteError, "main line stop '99'"):
                M.staging_keys(self.overrides, self.plan, M.read_lines("staging", staging_file(tmp, *rows)))

    def test_a_track_in_a_stop_is_its_block_id(self):
        """naming-layers step 5: a stop gives a track by its block id and read_lines gives it back by the name
        store's name less "Track ", so a rename changes no row; a track by name, or an id the master lacks, stops."""
        raw = file_rows("staging")
        self.assertEqual((raw[1]["from"], self.rows[1]["from"]), ("35@block:33A-35A", "35@East Lead"))
        self.assertEqual((raw[1]["to"], self.rows[1]["to"]), ("block:39B-helix", "Helix Outer"))
        with tempfile.TemporaryDirectory() as tmp:
            rows = [[r[c] for c in STAGING_COLUMNS] for r in raw]
            path = staging_file(tmp, *rows)
            names = {("1", "block:33A-35A"): "Track Lead East", ("1", "block:39B-helix"): "Track Helix West",
                     ("1", "block:37B-helix"): "Track Helix Inner", ("1", "block:5B-7A"): "Track East Ext",
                     ("1", "block:23B-35B"): "Track West Ext", ("1", "block:1A-23A"): "Track Main West"}
            got = M.read_lines("staging", path, names)
            self.assertEqual((got[1]["from"], got[1]["to"]), ("35@Lead East", "Helix West"))
            for stop, msg in (("35@East Lead", r"stop '35@East Lead' names a track by its name; give its block id"),
                              ("Helix Outer", r"stop 'Helix Outer' names a track by its name"),
                              ("block:99Z-helix", r"block:99Z-helix is no block of the device master")):
                with self.subTest(stop=stop), self.assertRaisesRegex(M.RouteError, msg):
                    rows[1][1] = stop
                    M.read_lines("staging", staging_file(tmp, *rows))

    def test_count_is_yes_or_blank(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(M.RouteError, "line 2 .*count is yes or blank"):
                M.read_lines("staging", staging_file(tmp, ["A", "1", "", "5", "", "", "maybe", ""]))



if __name__ == "__main__":
    unittest.main()
