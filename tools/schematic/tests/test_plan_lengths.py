"""plan_lengths.py: each staging block's AnyRail plan 5.3c length."""
from __future__ import annotations

import contextlib
import csv
import io
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
                               {"OS Switch 7", "OS Switch 3", "OS Switch 1"}, {})
        self.assertEqual(got, {"Track K-1": 122.9, "Track K-2": 122.9, "Track BP": 71.6, "Track Scale": 158.0})

    def test_track_blocks_on_one_track_share_it_evenly_and_a_missing_run_stops(self):
        """Parts at both ends of a track (Track 1-3 at 1 and at 3) share its run evenly, as track_inches reads a k/n
        key; a part at one end with its own cm (block_overrides.csv) takes that cm and the track's own block the rest
        (the Scale-in-OS-7 shape); any other mix of track blocks on one strand stops."""
        b = band({"e22": ("e22", "")})
        names = {"blocks": {"e22": ["Track 1-3 at 1", "Track 1-3 at 3"]}}
        parts = {"Track 1-3 at 1": 10.0, "Track 1-3 at 3": 10.0}
        self.assertEqual(PL.track_lengths(b, names, {"e22": 21.0}, set(), parts),
                         {"Track 1-3 at 1": 10.5, "Track 1-3 at 3": 10.5})
        scale = {"blocks": {"e22": ["Track Scale", "Track Scale at 7"]}}
        got = PL.track_lengths(b, scale, {"e22": 100.0}, set(), {"Track Scale at 7": 25.4})
        self.assertEqual({k: round(v, 6) for k, v in got.items()}, {"Track Scale at 7": 10.0, "Track Scale": 90.0})
        with self.assertRaisesRegex(PL.LengthError, "Track Scale at 7: 254 cm is not under the track's 100.0 in"):
            PL.track_lengths(b, scale, {"e22": 100.0}, set(), {"Track Scale at 7": 254.0})
        with self.assertRaisesRegex(PL.LengthError, r"track e22: blocks \['Track A', 'Track B'\] share it"):
            PL.track_lengths(b, {"blocks": {"e22": ["Track A", "Track B"]}}, {"e22": 21.0}, set(), {})
        with self.assertRaisesRegex(PL.LengthError, "track e22: no run in the plan file"):
            PL.track_lengths(b, {"blocks": {"e22": ["Track A"]}}, {}, set(), {})

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


# the device IDs of the fixture blocks: block_lengths.csv is keyed by (level, id)
IDS = {("1", "Track A"): "block:A", ("1", "Track B"): "block:B", ("1", "OS Switch 1"): "os:1",
       ("1", "Track 1-3 at 1"): "block:1B-3A:1/2", ("1", "Track Gone"): "block:gone",
       ("2", "OS Switch 101"): "os:101", ("2", "Track 117-119"): "block:117B-119A", ("3", "Track 201-203"): "block:201B-203A"}
NAMES = {v: name for (_level, name), v in IDS.items()}


def row(level, name, plan_in, note=""):
    """A block_lengths.csv row (block_lengths.PLAN_COLUMNS) of block `name` on `level`, its id from IDS."""
    return [level, IDS[(level, name)], plan_in, note]


def csv_with(*args, **kw):
    return PL.csv_with(*args, ids=IDS, **kw)


def named(text):
    """The rows of a written plan file, each with its block's name from IDS."""
    return [dict(r, name=NAMES.get(r["id"], r["id"])) for r in csv.DictReader(io.StringIO(text))]


class CsvWith(unittest.TestCase):
    def write(self, rows):
        p = Path(tempfile.mkdtemp()) / "block_lengths.csv"
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(PL.block_lengths.PLAN_COLUMNS)
        w.writerows(rows)
        p.write_text(buf.getvalue(), encoding="utf-8")
        return p

    def test_plan_in_is_written_and_the_note_kept(self):
        p = self.write([row("1", "Track A", "1.0"), row("1", "OS Switch 1", "1.0", "a note")])
        got = named(csv_with({"Track A": 104.04, "OS Switch 1": 9.2}, {}, p))
        self.assertEqual([(r["name"], r["plan_in"], r["note"]) for r in got],
                         [("Track A", "104.0", ""), ("OS Switch 1", "9.2", "a note")])
        self.assertEqual(list(got[0])[:4], list(PL.block_lengths.PLAN_COLUMNS))     # no names, no measured length

    def test_main_and_upper_rows_are_written_after_staging_in_level_and_name_order(self):
        p = self.write([row("1", "Track A", "1.0"), row("3", "Track 201-203", "3.0")])
        got = named(csv_with(
            {"Track A": 1.0}, {"Track 201-203": ("3", 7.04, "OS Switch 201"), "OS Switch 101": ("2", 16.0, "OS Switch 101"),
                               "Track 117-119": ("2", 0.0, "OS Switch 117")}, p))
        # a link whose turnouts touch is 0 in long; a new row says it is the plan's length
        self.assertEqual([(r["name"], r["plan_in"], r["note"]) for r in got],
                         [("Track A", "1.0", ""), ("OS Switch 101", "16.0", "main level, the plan's length"),
                          ("Track 117-119", "0.0", "main level, the plan's length"), ("Track 201-203", "7.0", "")])

    def test_a_new_staging_part_gets_a_row(self):
        p = self.write([row("1", "OS Switch 1", "9.0")])
        got = named(csv_with({"OS Switch 1": 9.0, "Track 1-3 at 1": 5.0}, {}, p, parts={"Track 1-3 at 1": "OS Switch 1"}))
        self.assertEqual([(r["name"], r["plan_in"], r["note"]) for r in got],
                         [("OS Switch 1", "9.0", ""),
                          ("Track 1-3 at 1", "5.0", "staging, the plan's length; a part of OS Switch 1, on its detector")])

    def test_the_file_and_the_drawing_must_hold_the_same_blocks(self):
        p = self.write([row("1", "Track A", "1.0")])
        with self.assertRaisesRegex(PL.LengthError, r"only drawn \['Track B'\]"):
            csv_with({"Track A": 1.0, "Track B": 2.0}, {}, p)
        p = self.write([row("1", "Track A", "1.0"), row("1", "Track Gone", "1.0")])
        with self.assertRaisesRegex(PL.LengthError, r"rows of no drawn block on any level: \['block:gone'\]"):
            csv_with({"Track A": 1.0}, {}, p)

    def test_a_row_is_found_by_its_blocks_id_so_a_rename_keeps_it(self):
        """naming-layers step 5: a length worked out by name finds its row by (level, id), so a renamed block keeps
        its row. A block with no id stops."""
        p = self.write([row("1", "OS Switch 1", "9.0", "kept")])
        got = list(csv.DictReader(io.StringIO(PL.csv_with({"OS Brick": 9.2}, {}, p, ids={("1", "OS Brick"): "os:1"}))))
        self.assertEqual([(r["level"], r["id"], r["plan_in"], r["note"]) for r in got], [("1", "os:1", "9.2", "kept")])
        with self.assertRaisesRegex(PL.LengthError, r"blocks with no device ID in the device master: \['Track Z'\]"):
            PL.csv_with({"OS Switch 1": 9.0, "Track Z": 1.0}, {}, p, ids=IDS)

    def test_a_file_with_other_columns_stops(self):
        p = Path(tempfile.mkdtemp()) / "block_lengths.csv"
        p.write_text("level,id,user_name,plan_in,note\n1,block:A,Track A,1.0,\n", encoding="utf-8")
        with self.assertRaisesRegex(PL.LengthError, "columns are not level, id, plan_in, note"):
            csv_with({"Track A": 1.0}, {}, p)


class MainUpper(unittest.TestCase):
    """Main and upper's plan lengths (step 5 part 2): runs from the plan file, OS blocks from their
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
        rows = PL.block_lengths.plan_blocks(PL.LENGTHS)
        for name, b in rows.items():
            if name.startswith("OS ") and b.occupancy_sensor.startswith("Block "):      # staging's
                self.assertIn(b.plan_in, (9.2, 11.1), name)

    def test_every_main_and_upper_block_has_a_plan_length(self):
        from hartlib import devices
        rows = PL.block_lengths.plan_blocks(PL.LENGTHS)
        want = {r.user_name for r in devices.load(devices.master_path(PL.pd.DATA.parents[0]))
                if r.level_cell in ("2", "3") and r.layer == "block" and r.role != "part"}
        self.assertEqual(sorted(want - set(rows)), [])
        self.assertFalse(hasattr(next(iter(rows.values())), "measured_in"))    # the plan file holds the plan length only


class NoPlugin(unittest.TestCase):
    """The plan reader is the schematic-maps plugin's: without the plugin, --check skips (fails under
    SCHEMATIC_REQUIRED=1) and a write stops, each naming what is missing."""

    def run_main(self, argv, required):
        missing = PL.sdm.lc.BuildError("schematic-maps plugin not found")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(PL.sdm.lc, "plugin_module", side_effect=missing), \
                mock.patch.dict("os.environ", {"SCHEMATIC_REQUIRED": "1" if required else ""}), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            return PL.main(argv), out.getvalue() + err.getvalue()

    def test_check_skips_unless_the_plugin_is_required(self):
        self.assertEqual(self.run_main(["--check"], False), (0, "SKIPPED plan lengths check: schematic-maps plugin "
                                                                "not found\n"))
        self.assertEqual(self.run_main(["--check"], True)[0], 1)

    def test_a_write_without_the_plugin_stops(self):
        self.assertEqual(self.run_main([], False), (2, "plan_lengths.py: schematic-maps plugin not found\n"))


if __name__ == "__main__":
    unittest.main()
