"""tools/anyrail/levels_svg.py: how a part gets its level, how a helix is drawn and each symbol, on made-up parts; and,
where the owner's plan 5.3c is on this machine (never in CI), that the committed drawings are what it gives and the
counts agree with the plan's own parts."""
import json
import math
import sys
import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import anyplan as A  # noqa: E402
import levels_svg as L  # noqa: E402

PLAN = L.DEFAULT_PLAN
LEVELS_DIR = HERE.parent / "levels"
HEIGHTS = {"staging": -38.1, "main": 0.0, "upper": 10.79}


def part(index, ends, curve=None):
    """A part from (x, y, z, heading degrees) ends, classified as anyplan does."""
    e = [dict(x=x, y=y, z=z, a=math.radians(d)) for x, y, z, d in ends]
    p = dict(index=index, name="t%d" % index, ends=e, curve=curve, cm=100.0 if len(e) == 2 else None)
    p.update(A.classify(e))
    return p


def flex(index, x, z0, z1=None):
    """A straight flex piece 100 cm long from x, climbing from z0 to z1."""
    z1 = z0 if z1 is None else z1
    return part(index, [(x, 0, z0, 0), (x + 100, 0, z1, 180)], [(x, 0), (x + 30, 0), (x + 70, 0), (x + 100, 0)])


def left_turnout(index, z):
    return part(index, [(0, 0, z, 180), (100, 0, z, 0), (100, 10, z, 10)])


class Levels(unittest.TestCase):
    def test_levels_come_from_the_heights_the_turnouts_sit_at(self) -> None:
        parts = [left_turnout(i, z) for i, z in enumerate((-38.1, 0.0, 10.79, 0.0))]
        self.assertEqual(L.level_heights(parts), HEIGHTS)

    def test_a_plan_with_other_heights_stops(self) -> None:
        with self.assertRaisesRegex(L.LevelsError, "expected three heights"):
            L.level_heights([left_turnout(i, z) for i, z in enumerate((-38.1, 5.0, 10.79))])
        with self.assertRaisesRegex(L.LevelsError, "expected three heights"):
            L.level_heights([left_turnout(i, z) for i, z in enumerate((0.0, 10.79))])

    def test_a_tilted_turnout_stops(self) -> None:
        tilted = part(3, [(0, 0, 0, 180), (100, 0, 1.0, 0), (100, 10, 0, 10)])
        parts = [left_turnout(0, -38.1), left_turnout(1, 0.0), left_turnout(2, 10.79), tilted]
        with self.assertRaisesRegex(L.LevelsError, "T3 is a turnout that is not level"):
            L.level_heights(parts)

    def test_flat_track_off_every_level_stops(self) -> None:
        with self.assertRaisesRegex(L.LevelsError, "not at a level"):
            L.nearest_level(5.0, HEIGHTS, "T9")
        self.assertEqual(L.nearest_level(10.7, HEIGHTS, "T9"), "upper")

    def plan(self):
        """A helix track of three pieces from staging to main (heights -38.1 to -20, -20 to -6, -6 to 0), a climb
        from main to upper, and a flat piece on each level."""
        return [flex(0, 0, -38.1, -20.0), flex(1, 100, -20.0, -6.0), flex(2, 200, -6.0, 0.0), flex(3, 1000, 0.0, 10.79),
                flex(4, 2000, -38.1), flex(5, 3000, 0.0), flex(6, 4000, 10.79)]

    def test_a_helix_is_drawn_on_staging_below_the_cut_and_on_the_level_it_reaches_above_it(self) -> None:
        where, ramp, _ = L.assign(self.plan(), HEIGHTS)
        # the pieces' mid heights are -29.05, -13 and -3 against the cut at -5
        self.assertEqual([where[i] for i in (0, 1, 2)], ["staging", "staging", "main"])
        self.assertEqual(ramp, {0, 1, 2, 3})

    def test_a_climb_that_starts_above_staging_is_drawn_on_the_level_it_climbs_from(self) -> None:
        where, _, _ = L.assign(self.plan(), HEIGHTS)
        self.assertEqual(where[3], "main")

    def test_every_part_gets_a_level_and_flat_ones_their_own(self) -> None:
        where, _, _ = L.assign(self.plan(), HEIGHTS)
        self.assertEqual(sorted(where), list(range(7)))
        self.assertEqual([where[i] for i in (4, 5, 6)], ["staging", "main", "upper"])

    def test_a_ramp_that_does_not_climb_to_a_higher_level_stops(self) -> None:
        with self.assertRaisesRegex(L.LevelsError, "not at a level"):
            L.assign([flex(0, 0, 0.0, 3.0)], HEIGHTS)       # ends at 3 cm: no level there

    def test_ramps_are_listed_by_foot_and_top(self) -> None:
        parts = self.plan()
        links, _ = A.joins(parts)
        got = L.ramps(parts, links, HEIGHTS)
        self.assertEqual([(r["foot"], r["top"], r["flex_m"]) for r in got], [("staging", "main", 3.0), ("main", "upper", 1.0)])


class Symbols(unittest.TestCase):
    def test_a_turnout_is_the_toe_to_each_leg_and_the_legs_to_each_other(self) -> None:
        lines = L.turnout_lines(left_turnout(0, 0.0))
        self.assertEqual(len(lines), 3)
        for x1, y1, x2, y2 in lines:
            self.assertNotEqual((x1, y1), (x2, y2))

    def test_a_double_crossover_is_two_rails_and_two_diagonals(self) -> None:
        dx = part(0, [(0, 0, 0, 180), (0, 5, 0, 180), (50, 0, 0, 0), (50, 5, 0, 0)])
        self.assertEqual(dx["kind"], "double_crossover")
        lines = L.turnout_lines(dx)
        self.assertEqual(len(lines), 4)
        rails = [l for l in lines if l[1] == l[3]]
        self.assertEqual(sorted((l[1], l[0], l[2]) for l in rails), [(0, 0, 50), (5, 0, 50)])

    def test_a_crossing_has_no_symbol_and_stops(self) -> None:
        cross = part(0, [(0, 0, 0, 180), (50, 0, 0, 0), (25, -25, 0, 90), (25, 25, 0, 270)])
        self.assertEqual(cross["kind"], "crossing")
        with self.assertRaisesRegex(L.LevelsError, "no symbol"):
            L.turnout_lines(cross)

    def test_a_threeway_label_joins_the_halves_the_owner_numbered(self) -> None:
        threeway = part(7, [(0, 0, 0, 180), (50, 0, 0, 0), (50, 5, 0, 10), (50, -5, 0, 350)])
        self.assertEqual(threeway["kind"], "threeway")
        names = {"T7": "wrong", "TO_3W1-1": "101A", "TO_3W1-2": "103A", "T9": "105"}
        self.assertEqual(L.label_of(threeway, names), "101A/103A")
        self.assertEqual(L.label_of(dict(left_turnout(9, 0.0), index=9), names), "105")
        self.assertEqual(L.label_of(dict(left_turnout(8, 0.0), index=8), names), "T8")    # no number: its T name

    def test_the_plan_version_is_read_from_the_file_name(self) -> None:
        self.assertEqual(L.plan_version("/x/Lee Nevo Design Version 5.3c.any"), "5.3c")
        with self.assertRaisesRegex(L.LevelsError, "no 'Version"):
            L.plan_version("/x/plan.any")

    def test_a_flex_piece_without_its_curve_stops(self) -> None:
        bare = part(0, [(0, 0, 0, 0), (100, 0, 0, 180)])
        with self.assertRaisesRegex(L.LevelsError, "no curve"):
            L.draw([bare], {0: "main"}, set(), "main")


class Cli(unittest.TestCase):
    def test_check_skips_when_the_default_plan_is_not_on_the_machine(self) -> None:
        with mock.patch.object(L, "DEFAULT_PLAN", Path("/nonexistent/Version 9.9z.any")):
            self.assertEqual(L.main(["/nonexistent/Version 9.9z.any", "--check"]), 0)

    def test_check_of_a_named_plan_that_is_missing_fails(self) -> None:
        with redirect_stderr(io.StringIO()) as err:
            self.assertEqual(L.main(["/nonexistent/typo.any", "--check"]), 2)
        self.assertIn("does not exist", err.getvalue())

    def test_switch_labels_sort_by_their_number_then_text(self) -> None:
        self.assertEqual(sorted(["211A", "T12", "101A/103A", "7", "211"], key=L.switch_key),
                         ["7", "101A/103A", "211", "211A", "T12"])

    def test_two_three_ways_on_one_level_stop(self) -> None:
        names = {"TO_3Wa-1": "101A", "TO_3Wa-2": "103A", "TO_3Wb-1": "105A"}
        with self.assertRaisesRegex(L.LevelsError, "more than one three-way"):
            L.label_of({"index": 4, "kind": "threeway"}, names)

    def test_writing_without_the_plan_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, redirect_stderr(io.StringIO()) as err:
            self.assertEqual(L.main(["/nonexistent/Version 9.9z.any", tmp]), 2)
        self.assertIn("No such file", err.getvalue())


@unittest.skipUnless(PLAN.exists(), "the owner's plan 5.3c is not on this machine")
class Plan53c(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = L.build(PLAN)
        cls.meta = json.loads(cls.files["levels_meta.json"])
        cls.parts = A.read(PLAN)

    def test_the_committed_drawings_are_what_the_plan_gives(self) -> None:
        self.assertEqual(L.main([str(PLAN), str(LEVELS_DIR), "--check"]), 0)
        self.assertEqual(sorted(p.name for p in LEVELS_DIR.iterdir()), sorted(self.files))

    def test_switch_counts_match_the_plans_heights(self) -> None:
        by_height = {}
        for p in self.parts:
            if len(p["ends"]) > 2:
                h = round(p["ends"][0]["z"], 2)
                by_height[h] = by_height.get(h, 0) + 1
        self.assertEqual({lv["height_cm"]: lv["switches"] for lv in self.meta["levels"].values()}, by_height)

    def test_every_flex_piece_is_drawn_once_and_the_ramps_are_the_sloped_ones(self) -> None:
        flat = sum(lv["flex"] for lv in self.meta["levels"].values())
        sloped = sum(1 for p in self.parts if len(p["ends"]) == 2
                     and abs(p["ends"][0]["z"] - p["ends"][1]["z"]) > A.LEVEL_CM)
        self.assertEqual(flat + sloped, sum(1 for p in self.parts if len(p["ends"]) == 2))
        self.assertEqual(sum(self.files[k + ".svg"].count('class="ramp"') for k in L.LEVELS), sloped)

    def test_the_helix_runs_are_the_plans(self) -> None:
        self.assertEqual(sorted((t["foot"], t["top"], round(t["cm"] / 2.54, 1)) for t in self.meta["helix"]),
                         [("37", "131B", 916.5), ("39", "131A", 947.2)])
        self.assertEqual([(r["foot"], r["top"]) for r in self.meta["ramps"]],
                         [("staging", "main"), ("staging", "main"), ("main", "upper")])

    def test_every_turnout_has_the_owners_number(self) -> None:
        labels = [s for lv in self.meta["levels"].values() for s in lv["labels"]]
        self.assertEqual([s for s in labels if s.startswith("T")], [])
        self.assertIn("101A/103A", labels)

    def test_only_track_reaches_a_drawing(self) -> None:
        for name, text in self.files.items():
            if name.endswith(".svg"):
                tags = {line.split(" ")[0] for line in text.replace("<", "\n<").split("\n") if line.startswith("<") and line[1] != "/"}
                self.assertEqual(tags, {"<polyline", "<line", "<text"})


if __name__ == "__main__":
    unittest.main()
