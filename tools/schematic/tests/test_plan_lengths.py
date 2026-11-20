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
        self.assertAlmostEqual(PL.turnout_inches(turnout("SL-8362", 9.2)), 9.2, places=6)
        self.assertAlmostEqual(PL.turnout_inches(turnout("SL-E8377", 11.1, at=(50, 7))), 11.1, places=6)

    def test_a_reading_outside_the_product_range_stops(self):
        with self.assertRaisesRegex(PL.LengthError, r"SL-8361 \(#6\) reads 11.10 in .* outside 9.1 to 9.3"):
            PL.turnout_inches(turnout("SL-8361", 11.1))

    def test_an_unknown_product_or_a_part_that_is_no_turnout_stops(self):
        with self.assertRaisesRegex(PL.LengthError, "no turnout product this knows"):
            PL.turnout_inches(turnout("SL-99", 9.2))
        with self.assertRaisesRegex(PL.LengthError, "2 ends, not a turnout's three"):
            PL.turnout_inches({"name": "SL-8300", "eps": [{"x": 0, "y": 0}, {"x": 1, "y": 0}]})

    def test_the_committed_parts_read_as_their_products(self):
        import json
        parts = json.loads(PL.PARTS.read_text(encoding="utf-8"))
        got = {round(PL.turnout_inches(p), 1) for p in parts if p["name"] in PL.PRODUCTS}
        self.assertEqual(got, {9.2, 11.1})

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

    def test_two_track_blocks_on_one_track_or_a_missing_run_stop(self):
        b = band({"e22": ("e22", "S-1")})
        names = {"blocks": {"e22": ["Track A", "Track B"]}}
        with self.assertRaisesRegex(PL.LengthError, r"blocks \['Track A', 'Track B'\] share it"):
            PL.track_lengths(b, names, {"e22": 210.0}, set())
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
        got = list(csv.DictReader(io.StringIO(PL.csv_with({"Track A": 104.04, "OS Switch 1": 9.2}, p))))
        self.assertEqual([(r["user_name"], r["plan_in"], r["measured_in"], r["note"]) for r in got],
                         [("Track A", "104.0", "", ""), ("OS Switch 1", "9.2", "22.6", "laps")])

    def test_the_file_and_the_drawing_must_hold_the_same_blocks(self):
        p = self.write([["Track A", "x", "1.0", "", "plan", ""], ["Track Gone", "x", "1.0", "", "plan", ""]])
        with self.assertRaisesRegex(PL.LengthError, r"only in the file \['Track Gone'\], only drawn \['Track B'\]"):
            PL.csv_with({"Track A": 1.0, "Track B": 2.0}, p)


class Repo(unittest.TestCase):
    def test_the_os_rows_hold_their_turnout_lengths(self):
        rows = PL.railroad.read_block_lengths(PL.LENGTHS)
        for name, b in rows.items():
            if name.startswith("OS "):
                self.assertIn(b.plan_in, (9.2, 11.1), name)
        self.assertTrue(all(math.isclose(b.jmri_in, b.measured_in if b.source == "timed" else b.plan_in)
                            for b in rows.values()))


if __name__ == "__main__":
    unittest.main()
