"""plan_lengths.py: each staging block's AnyRail plan 5.3c length (owner, 2026-11-20)."""
from __future__ import annotations

import csv
import io
import math
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import plan_lengths as PL  # noqa: E402

CM = 2.54


def turnout(name, points_to_frog_in, spread_in=1.0, at=(0.0, 0.0)):
    """A three-ended part: points at `at`, the two frog-end ends `points_to_frog_in` along x, `spread_in` apart."""
    x0, y0 = at
    L, h = points_to_frog_in * CM, spread_in * CM / 2
    return {"name": name, "eps": [{"x": x0 + L, "y": y0 + h, "z": 0}, {"x": x0, "y": y0, "z": 0},
                                  {"x": x0 + L, "y": y0 - h, "z": 0}]}


class TurnoutLength(unittest.TestCase):
    def test_points_to_the_middle_of_the_frog_end(self):
        self.assertAlmostEqual(PL.turnout_inches(turnout("Acme 6", 9.2)), 9.2, places=6)
        self.assertAlmostEqual(PL.turnout_inches(turnout("Acme 8", 11.1, at=(50, 7))), 11.1, places=6)

    def test_the_class_comes_from_the_geometry_not_the_maker_name(self):
        self.assertEqual(PL.turnout_class(turnout("Made-Up Maker 123", 9.2)), "#6")
        self.assertEqual(PL.turnout_class(turnout("Made-Up Maker 123", 11.1)), "#8")
        self.assertEqual(PL.turnout_class(turnout("SL-8377", 9.2)), "#6")     # a Peco #8 code on #6 geometry

    def test_a_turnout_with_the_angle_of_no_class_stops(self):
        with self.assertRaisesRegex(PL.LengthError, r"'Odd 4' has leg-end angle .* in no class"):
            PL.turnout_class(turnout("Odd 4", 7.0))
        with self.assertRaisesRegex(PL.LengthError, "in no class"):
            PL.turnout_inches(turnout("Odd 12", 14.0))

    def test_a_length_outside_the_class_range_stops(self):
        # the #6 angle (spread scaled with length) on a part 10.0 in long
        with self.assertRaisesRegex(PL.LengthError, r"'Long 6' \(#6\) reads 10.00 in .* outside 9.1 to 9.3"):
            PL.turnout_inches(turnout("Long 6", 10.0, spread_in=10.0 / 9.2))

    def test_a_part_that_is_no_turnout_stops(self):
        with self.assertRaisesRegex(PL.LengthError, "2 ends, not a turnout's three"):
            PL.turnout_inches({"name": "SL-8300", "eps": [{"x": 0, "y": 0}, {"x": 1, "y": 0}]})
        line = [{"x": x, "y": 0} for x in (0, 5, 10)]
        with self.assertRaisesRegex(PL.LengthError, "on one line"):
            PL.turnout_class({"name": "Flat", "eps": line})

    def test_the_committed_turnouts_read_as_their_classes(self):
        import json
        parts = json.loads(PL.PARTS.read_text(encoding="utf-8"))
        got = {}
        for p in parts:
            try:
                got[p["name"]] = PL.turnout_class(p)
            except PL.LengthError:
                pass                                    # other ends counts: no class, no reading
        self.assertEqual({n for n, c in got.items() if c == "#6"}, {"SL-8361", "SL-8362", "SL-E8362"})
        self.assertEqual({n for n, c in got.items() if c == "#8"}, {"SL-8377", "SL-E8377"})
        self.assertEqual({n for n, c in got.items() if c == "#5"}, {"SL-8351", "SL-8352"})     # main and upper
        self.assertEqual({round(PL.turnout_inches(p), 1) for p in parts if p["name"] in got}, {8.3, 9.2, 11.1})

    def test_a_part_label_is_its_index(self):
        self.assertEqual(PL.part_index("T139"), 139)
        for bad in ("139", "TX", "", None):
            with self.subTest(bad=bad), self.assertRaisesRegex(PL.LengthError, "is no part"):
                PL.part_index(bad)


def band(strands):
    """A band of `strands` ({sid: (edge, name)}) for track_lengths."""
    return {"strands": {sid: {"edge": edge, "name": name} for sid, (edge, name) in strands.items()}}


class TrackLengths(unittest.TestCase):
    def test_a_folded_run_gives_each_half_and_a_block_on_both_takes_the_whole(self):
        b = band({"e15.0": ("e15", "K-1"), "e15.1": ("e15", "K-2"), "e28.0": ("e28", "BP"), "e28.1": ("e28", ""),
                  "e29": ("e29", "Scale"), "e6": ("e6", "")})
        names = {"blocks": {"e15.0": ["Track K-1"], "e15.1": ["Track K-2"], "e28.0": ["Track BP"],
                            "e28.1": ["Track BP"], "e29": ["Track Scale", "OS Switch 7"],
                            "e6": ["OS Switch 3", "OS Switch 1"]}}
        got = PL.track_lengths(b, names, {"e15": 245.8, "e28": 71.6, "e29": 158.0, "e6": 10.0},
                               {"OS Switch 7", "OS Switch 3", "OS Switch 1"})
        self.assertEqual(got, {"Track K-1": 122.9, "Track K-2": 122.9, "Track BP": 71.6, "Track Scale": 158.0})

    def test_track_blocks_on_one_track_share_it_evenly_and_a_missing_run_stops(self):
        """The k-th of a strand's n track blocks takes 1/n of its run, as on main and upper (plan_lengths.track_inches)
        and in the block layer (a track with a part at each end: Track 1-3 at 1 and at 3)."""
        b = band({"e22": ("e22", "")})
        names = {"blocks": {"e22": ["Track 1-3 at 1", "Track 1-3 at 3"]}}
        self.assertEqual(PL.track_lengths(b, names, {"e22": 21.0}, set()),
                         {"Track 1-3 at 1": 10.5, "Track 1-3 at 3": 10.5})
        with self.assertRaisesRegex(PL.LengthError, "track e22: no run in the plan file"):
            PL.track_lengths(b, {"blocks": {"e22": ["Track A"]}}, {}, set())


class EdgeRuns(unittest.TestCase):
    GRAPH = {"nodes": {"a": {"kind": "switch", "label": "T1"}, "b": {"kind": "switch", "label": "T2"},
                       "end": {"kind": "end", "sub": "bumper"}, "hx": {"kind": "end", "sub": "helix"}},
             "edges": [{"id": "e0", "u": "a", "up": "B", "v": "b", "vp": "A"},
                       {"id": "e1", "u": "end", "up": "E", "v": "a", "vp": "C"},
                       {"id": "e2", "u": "b", "up": "B", "v": "hx", "vp": "E"}]}

    def test_each_edge_takes_its_run_from_its_switch_end(self):
        runs = {(1, "B"): (100.0, (2, "A")), (1, "C"): (50.0, None), (2, "B"): (900.0, (77, "B"))}
        self.assertEqual(PL.edge_runs(self.GRAPH, runs), {"e0": 100.0, "e1": 50.0, "e2": 900.0})

    def test_a_run_that_ends_elsewhere_stops(self):
        runs = {(1, "B"): (100.0, (3, "A")), (1, "C"): (50.0, (2, "C")), (2, "B"): (900.0, None)}
        with self.assertRaises(PL.LengthError) as stop:
            PL.edge_runs(self.GRAPH, runs)
        self.assertIn("edge e0: the plan's run from T1 leg B ends at (3, 'A'), the graph says T2 leg A", str(stop.exception))
        self.assertIn("edge e1: ends at a bumper in the graph, at (2, 'C') in the plan file", str(stop.exception))


class CsvWith(unittest.TestCase):
    def write(self, rows):
        p = Path(tempfile.mkdtemp()) / "block_lengths.csv"
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(PL.railroad.BLOCK_LENGTH_COLUMNS)
        w.writerows(rows)
        p.write_text(buf.getvalue(), encoding="utf-8")
        return p

    def test_plan_in_is_written_and_the_rest_kept(self):
        p = self.write([["Track A", "x", "1.0", "", "plan", ""], ["OS Switch 1", "x", "1.0", "22.6", "timed", "laps"]])
        got = list(csv.DictReader(io.StringIO(PL.csv_with({"Track A": 104.04, "OS Switch 1": 9.2}, {}, p))))
        self.assertEqual([(r["user_name"], r["plan_in"], r["measured_in"], r["note"]) for r in got],
                         [("Track A", "104.0", "", ""), ("OS Switch 1", "9.2", "22.6", "laps")])

    def test_main_and_upper_rows_are_written_after_staging_in_level_and_name_order(self):
        p = self.write([["Track A", "x", "1.0", "", "plan", ""], ["Track 201-203", "BS 201-203", "3.0", "", "plan", ""]])
        got = list(csv.DictReader(io.StringIO(PL.csv_with(
            {"Track A": 1.0}, {"Track 201-203": ("3", 7.04, "OS Switch 201"), "OS Switch 101": ("2", 16.0, "OS Switch 101"),
                               "Track 117-119": ("2", 0.0, "OS Switch 117")}, p))))
        # a part (201-203, 117-119) carries its OS block's sensor; a link whose turnouts touch is 0 in long
        self.assertEqual([(r["user_name"], r["occupancy_sensor"], r["plan_in"], r["source"]) for r in got],
                         [("Track A", "x", "1.0", "plan"), ("OS Switch 101", "BS Switch 101", "16.0", "plan"),
                          ("Track 117-119", "BS Switch 117", "0.0", "plan"),
                          ("Track 201-203", "BS 201-203", "7.0", "plan")])     # a row it had keeps its columns

    def test_a_main_or_upper_row_keeps_its_own_columns(self):
        p = self.write([["Track A", "x", "1.0", "", "plan", ""],
                        ["Track 201-203", "BS Switch 201", "3.0", "4.4", "timed", "laps"]])
        got = list(csv.DictReader(io.StringIO(PL.csv_with({"Track A": 1.0}, {"Track 201-203": ("3", 7.04, "OS Switch 201")},
                                                          p))))
        self.assertEqual([(r["user_name"], r["plan_in"], r["measured_in"], r["source"], r["note"]) for r in got],
                         [("Track A", "1.0", "", "plan", ""), ("Track 201-203", "7.0", "4.4", "timed", "laps")])

    def test_the_file_and_the_drawing_must_hold_the_same_blocks(self):
        p = self.write([["Track A", "x", "1.0", "", "plan", ""]])
        with self.assertRaisesRegex(PL.LengthError, r"only drawn \['Track B'\]"):
            PL.csv_with({"Track A": 1.0, "Track B": 2.0}, {}, p)
        p = self.write([["Track A", "x", "1.0", "", "plan", ""], ["Track Gone", "x", "1.0", "", "plan", ""]])
        with self.assertRaisesRegex(PL.LengthError, r"rows of no drawn block on any level: \['Track Gone'\]"):
            PL.csv_with({"Track A": 1.0}, {}, p)


class MainUpper(unittest.TestCase):
    """Main and upper's plan lengths (step 5 part 2, owner 2026-11-20): runs from the plan file, OS blocks from their
    parts."""
    GRAPH = {"nodes": {"a": {"kind": "switch", "label": "T1"}, "w1": {"kind": "switch", "label": "51"},
                       "w2": {"kind": "switch", "label": "50"}, "end": {"kind": "end", "sub": "bumper"}},
             "edges": [{"id": "e0", "u": "a", "up": "B", "v": "w1", "vp": "C", "cm": 30.0},
                       {"id": "e1", "u": "TO_3W1-1", "up": "A", "v": "end", "vp": "E", "cm": 60.0},
                       {"id": "e2", "u": "TO_3W1-1", "up": "B", "v": "TO_3W1-2", "vp": "A", "cm": 3.4}]}
    GRAPH["nodes"]["TO_3W1-1"] = {"kind": "switch", "label": "51"}
    GRAPH["nodes"]["TO_3W1-2"] = {"kind": "switch", "label": "50"}

    def test_a_track_row_measures_its_trial_edges(self):
        """A row's switch-and-leg keys give its share of each plan edge: a balloon loop half one of its edge's two
        strands, a track folded at a turnback both, the k-th of a strand's n blocks 1/n of its strand's share."""
        bad = []
        pieces = {"107B-107C #1": {"e33": 0.5}, "201A-219B #1": {"e58": 0.5}, "201A-219B #2": {"e58": 0.5},
                  "101BA-111C": {"e24": 1.0}}
        edge_in = {"e33": 300.0, "e58": 40.0, "e24": 100.0}
        row = {"user_name": "Track 107 Loop 1", "level": "2", "trial_name": "Track 107B-107C #1"}
        self.assertEqual(PL.track_inches(row, pieces, edge_in, bad), 150.0)
        both = dict(row, user_name="Track 201-219", trial_name="Track 201A-219B #1, Track 201A-219B #2")
        self.assertEqual(PL.track_inches(both, pieces, edge_in, bad), 40.0)
        quarter = dict(row, trial_name="Track 101BA-111C 2/4")           # one of four blocks on one strand
        self.assertEqual(PL.track_inches(quarter, pieces, edge_in, bad), 25.0)
        self.assertIsNone(PL.track_inches(dict(row, trial_name=""), pieces, edge_in, bad))
        self.assertIsNone(PL.track_inches(dict(row, trial_name="Track 9A-11C"), pieces, edge_in, bad))
        self.assertIsNone(PL.track_inches(dict(row, trial_name="Track e33 1"), pieces, edge_in, bad))
        self.assertIsNone(PL.track_inches(row, pieces, {}, bad))
        self.assertEqual(bad, ["Track 107 Loop 1 (level 2): no trial_name, so no plan edge to measure",
                               "Track 107 Loop 1 (level 2): trial name 'Track 9A-11C' is drawn on no main or upper "
                               "strand",
                               "Track 107 Loop 1 (level 2): 'Track e33 1' is no track trial key (Track <end>-<end>[ "
                               "#i][ k/n])",
                               "Track 107 Loop 1 (level 2): trial name 'Track 107B-107C #1' is drawn on plan edge "
                               "e33, which main.json does not have"])

    def test_piece_edges_share_each_edge_by_strands(self):
        strands = {"e33.0": {"edge": "e33"}, "e33.1": {"edge": "e33"}, "e35x": {"edge": "e35x"}}
        other = {"e35y": {"edge": "e35y"}}
        refs = {1: {"e33.0": ("107B-107C #1", False), "e33.1": ("107B-107C #2", True),
                    "e35x": ("131AC-131BC", False)},
                2: {"e35y": ("131AC-131BC", False)}}
        got = PL.piece_edges({1: strands, 2: other}, refs)
        self.assertEqual(got, {"107B-107C #1": {"e33": 0.5}, "107B-107C #2": {"e33": 0.5},
                               "131AC-131BC": {"e35": 1.0}})

    def test_edges_take_the_plans_run_not_the_graphs_length(self):
        got = PL.main_edge_inches(self.GRAPH, {(1, "B"): (10.0, None)}, threeway_bumper=20.0)
        self.assertEqual(got, {"e0": 10.0, "e1": 20.0, "e2": 0.0})

    def test_an_edge_with_no_run_stops(self):
        with self.assertRaisesRegex(PL.LengthError, "edge e0 .*no run"):
            PL.main_edge_inches(self.GRAPH, {}, threeway_bumper=20.0)

    def test_the_main_and_upper_number_5_turnout_reads_from_its_geometry(self):
        self.assertEqual(PL.turnout_class(turnout("Made-Up Maker 5", 8.3, spread_in=1.0)), "#5")
        self.assertAlmostEqual(PL.turnout_inches(turnout("Made-Up Maker 5", 8.3)), 8.3, places=6)

    def test_a_four_ended_part_spans_its_longest_end_to_end(self):
        part = {"name": "X", "eps": [{"x": 0, "y": 0}, {"x": 10 * CM, "y": 0}, {"x": 0, "y": 1 * CM},
                                     {"x": 10 * CM, "y": 1 * CM}]}
        self.assertAlmostEqual(PL.part_span_inches(part), math.hypot(10, 1), places=6)
        with self.assertRaisesRegex(PL.LengthError, "not a three-way's or double crossover's four"):
            PL.part_span_inches(turnout("Y", 9.2))


class Repo(unittest.TestCase):
    def test_the_os_rows_hold_their_turnout_lengths(self):
        rows = PL.railroad.read_block_lengths(PL.LENGTHS)
        for name, b in rows.items():
            if name.startswith("OS ") and b.occupancy_sensor.startswith("Block "):      # staging's
                self.assertIn(b.plan_in, (9.2, 11.1), name)

    def test_every_main_and_upper_block_has_a_plan_length(self):
        import csv as _csv
        rows = PL.railroad.read_block_lengths(PL.LENGTHS)
        with open(PL.pd.DATA.parents[0] / "devices.csv", newline="", encoding="utf-8") as fh:
            want = {r["user_name"] for r in _csv.DictReader(fh)
                    if r["level"] in ("2", "3") and r["layer"] == "block" and r["role"] != "part"}
        self.assertEqual(sorted(want - set(rows)), [])
        self.assertFalse(hasattr(next(iter(rows.values())), "jmri_in"))    # JMRI's length is plan_in


if __name__ == "__main__":
    unittest.main()
