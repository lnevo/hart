"""tools/anyrail/levels_svg.py: how a part gets its level, how a helix is drawn and each symbol, on made-up parts; and,
where the owner's plan 5.3c is on this machine (never in CI), that the committed drawings are what it gives and the
counts agree with the plan's own parts."""
import json
import math
import sys
import io
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import levels_svg as L  # noqa: E402

PLAN = L.DEFAULT_PLAN
LEVELS_DIR = HERE.parent / "levels"
HEIGHTS = {"staging": -38.1, "main": 0.0, "upper": 10.79}


def part(index, ends, curve=None):
    """A part from (x, y, z, heading degrees) ends, classified as the plan reader does."""
    e = [dict(x=x, y=y, z=z, a=math.radians(d)) for x, y, z, d in ends]
    p = dict(index=index, name="t%d" % index, ends=e, curve=curve, cm=100.0 if len(e) == 2 else None)
    p.update(L.anyplan().classify(e))
    return p


def flex(index, x, z0, z1=None, turn=0):
    """A flex piece 100 cm long from x, climbing from z0 to z1 and turning `turn` degrees (its end headings say so;
    the curve is drawn straight)."""
    z1 = z0 if z1 is None else z1
    return part(index, [(x, 0, z0, 0), (x + 100, 0, z1, 180 + turn)], [(x, 0), (x + 30, 0), (x + 70, 0), (x + 100, 0)])


def arc(index, a0, a1, z0, z1, r=50.0):
    """A helix piece on a circle of radius r about the origin, from a0 to a1 degrees, climbing from z0 to z1, with its
    curve as one cubic Bezier."""
    t0, t1 = math.radians(a0), math.radians(a1)
    k = 4 / 3 * math.tan((t1 - t0) / 4) * r
    p0 = (r * math.cos(t0), r * math.sin(t0))
    p3 = (r * math.cos(t1), r * math.sin(t1))
    p1 = (p0[0] - k * math.sin(t0), p0[1] + k * math.cos(t0))
    p2 = (p3[0] + k * math.sin(t1), p3[1] - k * math.cos(t1))
    return part(index, [(*p0, z0, a0 - 90), (*p3, z1, a1 + 90)], [p0, p1, p2, p3])


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

    def plan(self, step=100):
        """A helix track of five pieces on one circle from staging to main, each turning `step` degrees, a climb from
        main to upper (piece 5), and a flat piece on each level (6 to 8)."""
        zs = [-38.1 + 38.1 * k / 5 for k in range(6)]
        return [arc(k, step * k, step * (k + 1), zs[k], zs[k + 1]) for k in range(5)] + [
            flex(5, 1000, 0.0, 10.79), flex(6, 2000, -38.1), flex(7, 3000, 0.0), flex(8, 4000, 10.79)]

    def test_a_helix_is_drawn_on_the_level_it_reaches_down_to_where_it_would_pass_under_itself(self) -> None:
        where, ramp, _, partial = L.assign(self.plan(), HEIGHTS)
        # walking down from 500 degrees, the track is over its own top at 140 degrees, inside piece 1
        self.assertEqual([where[i] for i in (2, 3, 4)], ["main"] * 3)
        self.assertEqual(where[0], "staging")
        self.assertEqual(set(partial), {1})
        (upper, up_cm), (lower, low_cm) = partial[1]["main"], partial[1]["staging"]
        self.assertEqual(upper[-1], lower[0])                          # split at one point, drawn on both levels
        self.assertAlmostEqual(up_cm + low_cm, 100.0)                  # the piece's plan length, shared
        angle = math.degrees(math.atan2(upper[-1][1], upper[-1][0]))
        self.assertAlmostEqual(angle, 140, delta=8)
        self.assertEqual(ramp, set(range(6)))

    def test_a_staging_climb_of_less_than_one_turn_is_split_at_the_cut(self) -> None:
        where, _, _, partial = L.assign(self.plan(step=60), HEIGHTS)     # 300 degrees in all
        # the pieces' mid heights are -34.3, -26.7, -19.1, -11.4 and -3.8 against the cut at -5
        self.assertEqual([where[i] for i in range(5)], ["staging"] * 4 + ["main"])
        self.assertEqual(partial, {})

    def test_a_one_piece_climb_from_staging_is_drawn(self) -> None:
        where, _, _, _ = L.assign([flex(0, 0, -38.1, 0.0), flex(1, 2000, -38.1), flex(2, 3000, 0.0),
                                   flex(3, 4000, 10.79)], HEIGHTS)
        self.assertEqual(where[0], "staging")                          # its middle, at -19 cm, is below the cut

    def test_a_track_crossing_under_a_higher_one_is_cut_there_and_not_under_a_lower_one(self) -> None:
        walk = [(0, [(0.0, 0.0, 0.0), (10.0, 0.0, -1.0), (20.0, 0.0, -2.0)])]
        higher = [((5.0, -5.0, 5.0), (5.0, 5.0, 5.0))]
        lower = [((5.0, -5.0, -9.0), (5.0, 5.0, -9.0))]
        whole, cut = L.top_layer(walk, higher)
        self.assertEqual((whole, cut[0], cut[1], cut[3]), (set(), 0, [(0.0, 0.0)], 0.0))
        self.assertIsNone(L.top_layer(walk, lower))

    def test_a_climb_that_starts_above_staging_is_drawn_on_the_level_it_climbs_from(self) -> None:
        where, _, _, _ = L.assign(self.plan(), HEIGHTS)
        self.assertEqual(where[5], "main")

    def test_every_part_gets_a_level_and_flat_ones_their_own(self) -> None:
        where, _, _, _ = L.assign(self.plan(), HEIGHTS)
        self.assertEqual(sorted(where), list(range(9)))
        self.assertEqual([where[i] for i in (6, 7, 8)], ["staging", "main", "upper"])

    def test_a_ramp_that_does_not_climb_to_a_higher_level_stops(self) -> None:
        with self.assertRaisesRegex(L.LevelsError, "not at a level"):
            L.assign([flex(0, 0, 0.0, 3.0)], HEIGHTS)       # ends at 3 cm: no level there

    def test_ramps_are_listed_by_foot_and_top(self) -> None:
        parts = self.plan()
        links, _ = L.anyplan().joins(parts)
        got = L.ramps(parts, links, HEIGHTS)
        self.assertEqual([(r["foot"], r["top"], r["flex_m"]) for r in got], [("staging", "main", 5.0), ("main", "upper", 1.0)])


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

    def test_a_double_crossover_finds_its_sides_with_any_end_headings(self) -> None:
        dx = part(0, [(0, 0, 0, 180), (0, 5, 0, 180), (50, 0, 0, 0), (50, 5, 0, 0)])
        for heading in (0.0, math.pi / 2):          # every end the same way, then every end across the track
            for e in dx["ends"]:
                e["a"] = heading
            rails = [l for l in L.turnout_lines(dx) if l[1] == l[3]]
            self.assertEqual(sorted((l[1], l[0], l[2]) for l in rails), [(0, 0, 50), (5, 0, 50)])

    def test_a_double_crossover_pairs_its_rails_by_position_not_by_the_end_headings(self) -> None:
        # plan 5.3c's T322: its end headings point across the track, and its far ends come in the other order
        dx = part(0, [(461.4, 325.0, 10.79, 270), (413.7, 320.0, 10.79, 90), (413.7, 325.1, 10.79, 90),
                      (461.4, 319.9, 10.79, 270)])
        self.assertEqual(dx["kind"], "double_crossover")
        rails = [l for l in L.turnout_lines(dx) if abs(l[1] - l[3]) < 0.5]
        self.assertEqual(sorted(round(l[1]) for l in rails), [320, 325])

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

    def test_a_flex_piece_without_its_length_stops(self) -> None:
        piece = flex(0, 0, 0.0)
        piece["cm"] = None
        with self.assertRaisesRegex(L.LevelsError, "T0 has no length"):
            L.draw([piece], {0: "main"}, set(), "main")

    def test_a_level_draws_each_part_and_counts_it(self) -> None:
        svg, counts = L.draw([flex(0, 0, 0.0), left_turnout(1, 0.0)], {0: "main", 1: "main"}, set(), "main")
        self.assertEqual(svg.count('<polyline class="trk"'), 1)
        self.assertEqual(svg.count('<line class="to"'), 3)
        self.assertIn('<text class="tl" x="69.7" y="0.3">', svg)
        self.assertEqual((counts["switches"], counts["flex"], counts["flex_m"], counts["bbox"]),
                         (1, 1, 1.0, [0.0, 0.0, 100.0, 10.0]))


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

    def test_a_missing_plugin_is_an_error_that_names_it(self) -> None:
        missing = L.le_common().BuildError("schematic-maps plugin not found: run git submodule update --init ...")
        with tempfile.TemporaryDirectory() as tmp, redirect_stderr(io.StringIO()) as err, \
                mock.patch.object(L.le_common(), "plugin_module", side_effect=missing):
            self.assertEqual(L.main(["/nonexistent/Version 9.9z.any", tmp]), 2)
        self.assertIn("the schematic-maps plugin: schematic-maps plugin not found", err.getvalue())

    def test_check_without_the_plugin_skips_unless_it_is_required(self) -> None:
        missing = L.le_common().BuildError("schematic-maps plugin not found")
        with tempfile.NamedTemporaryFile(suffix=".any") as plan, \
                mock.patch.object(L.le_common(), "plugin_module", side_effect=missing):
            for required, want in (("", 0), ("1", 2)):
                with mock.patch.dict("os.environ", {"SCHEMATIC_REQUIRED": required}), \
                        redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(L.main([plan.name, "--check"]), want)
                self.assertEqual("SKIPPED" in out.getvalue(), want == 0)

    def test_importing_it_loads_no_layout_editor_build(self) -> None:
        """levels_page.py imports this file for switch_key: le_common (and the plugin) load only to read a plan."""
        code = (f"import sys; sys.path.insert(0, {str(HERE.parent)!r}); import levels_svg; "
                "print('le_common' in sys.modules)")
        got = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
        self.assertEqual(got.stdout.strip(), "False")


@unittest.skipUnless(PLAN.exists(), "the owner's plan 5.3c is not on this machine")
class Plan53c(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = L.build(PLAN)
        cls.meta = json.loads(cls.files["levels_meta.json"])
        cls.parts = L.anyplan().read(PLAN)

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
                     and abs(p["ends"][0]["z"] - p["ends"][1]["z"]) > L.anyplan().LEVEL_CM)
        self.assertEqual(flat + sloped, sum(1 for p in self.parts if len(p["ends"]) == 2))
        # each helix track's top layer ends inside one piece, drawn in two parts (upper level and staging)
        self.assertEqual(sum(self.files[k + ".svg"].count('class="ramp"') for k in L.LEVELS), sloped + 2)

    def test_no_drawn_helix_track_runs_under_another_on_the_main_level(self) -> None:
        import re
        lines = [[tuple(map(float, q.split(","))) for q in m.split()]
                 for m in re.findall(r'class="ramp" points="([^"]+)"', self.files["main.svg"])]
        segs = [(n, a, b) for n, pts in enumerate(lines) for a, b in zip(pts, pts[1:])]
        crossings = [(n, m) for n, a, b in segs for m, c, d in segs if n < m and L._crosses(a, b, c, d)]
        self.assertEqual(crossings, [])

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
