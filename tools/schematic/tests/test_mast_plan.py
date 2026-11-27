"""mast_plan.py and the rules in mast_rule.py that replaced the hand lists: each rule on a small
hand-made band, its error paths, and, as data checks over the committed plan under RepoReadOnly, that the rules give
exactly what the deleted hand lists held."""
from __future__ import annotations

import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))     # repo_read_only.py

import mast_plan as mp  # noqa: E402
import mast_rule as mr  # noqa: E402
import block_override_rows  # noqa: E402
from map_error import MapError  # noqa: E402
import mast_routes  # noqa: E402
import plan_tracks  # noqa: E402
from plugin_needed import skip_or_fail  # noqa: E402
from repo_read_only import RepoReadOnly  # noqa: E402
from hartlib import hand_lists, track_names  # noqa: E402

CM_PER_SCALE_MILE = 63360 * 2.54 / 87.1


def node(label, legs, kind="switch", **more):
    """A band node whose legs map to strand ids (all as outs)."""
    return dict(kind=kind, label=label, ins={}, outs=dict(legs), **more)


def end(leg_strand, sub):
    return node("", {"E": leg_strand}, kind="end", sub=sub)


def link(src, dst, edge="e", cm=100.0):
    return dict(src=list(src), dst=list(dst), edge=edge, name="", cm=cm)


def track(name, legs, ends, main=False, level=1, band=0, cm=100.0, loop=False, row=0):
    return dict(name=name, legs=legs, ends=ends, main=main, level=level, band=band, cm=cm, loop=loop, row=row,
                trial=[name], strands=[])


# ---------------------------------------------------------------- numbers


class Numbers(unittest.TestCase):
    """An intermediate's number is its milepost in tenths, odd westbound and even eastbound."""

    def test_odd_west_even_east(self):
        self.assertEqual([mp.signal_number(6.7, w) for w in (True, False)], [67, 68])
        self.assertEqual([mp.signal_number(6.714, w) for w in (True, False)], [67, 68])
        # on an even tenth the eastward signal keeps it and the westward one takes the next odd number
        self.assertEqual([mp.signal_number(6.6, w) for w in (True, False)], [67, 66])

    def test_the_tenth_is_cut_not_rounded(self):
        self.assertEqual(mp.signal_number(6.799, False), 68)
        self.assertEqual(mp.signal_number(6.799, True), 67)

    def test_float_noise_under_a_tenth_still_counts_as_that_tenth(self):
        m = 0.7 + 0.1
        self.assertLess(m, 0.8)
        self.assertEqual((mp.signal_number(m, True), mp.signal_number(m, False)), (9, 8))

    def test_with_no_line_code_names_stop_under_100(self):
        self.assertEqual(mp.signal_number(9.8, False), 98)
        with self.assertRaisesRegex(MapError, "gives intermediate number 99; names with no line code stop at 98"):
            mp.signal_number(9.8, True)
        self.assertEqual(mp.signal_number(9.8, True, "A"), 99)
        for m in (9.9, 10.0, 12.34):
            for west in (True, False):
                with self.assertRaisesRegex(MapError, "names with no line code stop at 98"):
                    mp.signal_number(m, west)

    def test_with_a_line_code_there_is_no_stop(self):
        self.assertEqual([mp.signal_number(9.9, w, "B") for w in (True, False)], [99, 100])
        self.assertEqual(mp.signal_number(12.34, True, "A"), 123)

    def test_node_mileposts_take_each_strands_ends_first_one_wins(self):
        band = {"mp": {"s1": ("N1", 5.7, 0.5, "N2"), "s2": ("N2", 6.3, 0.25, "N3"), "s3": ("N4", 1.0, 0.0, "N1")}}
        got = mp.node_mileposts(band)
        self.assertEqual(got["N1"], 5.7)
        self.assertAlmostEqual(got["N2"], 6.2)
        self.assertAlmostEqual(got["N3"], 6.55)
        self.assertEqual(got["N4"], 1.0)

    def test_line_codes(self):
        self.assertEqual(mp.LINE_CODE, {1: "", 2: "A", 3: "B"})


class AssignNumbers(unittest.TestCase):
    """Two pairs a tenth apart share a westward number (6.6 and 6.7 both give 67): the lower milepost keeps it, the
    other takes the next number of its parity no intermediate holds or would hold, and the shift is printed."""

    @staticmethod
    def masts(*mps, code="", west=True):
        return [mp.Pending(code, mp.signal_number(m, west, code), m,
                           dict(dir="west" if west else "east", milepost=round(m, 3))) for m in mps]

    def named(self, masts):
        with unittest.mock.patch("sys.stderr") as err:
            got = mp.assign_numbers(masts)
        return got, "".join(c.args[0] for c in err.write.call_args_list)

    def names(self, masts):
        got, printed = self.named(masts)
        return [m["name"] for m in got], printed

    def test_no_clash_keeps_every_natural_number_and_prints_nothing(self):
        got, printed = self.names(self.masts(6.6) + self.masts(6.6, west=False) + self.masts(6.9))
        self.assertEqual(got, ["67", "66", "69"])
        self.assertEqual(printed, "")

    def test_the_lower_milepost_keeps_the_number_whatever_the_order(self):
        for order in ((6.6, 6.7), (6.7, 6.6)):
            got, printed = self.names(self.masts(*order))
            self.assertEqual(dict(zip(order, got)), {6.6: "67", 6.7: "69"})
            self.assertIn("MP 6.700 would be intermediate 67, which MP 6.600 holds; named 69", printed)

    def test_a_shift_never_takes_another_masts_natural_number(self):
        got, _ = self.names(self.masts(6.6, 6.7, 6.9))
        self.assertEqual(got, ["67", "71", "69"])

    def test_name_comes_first_and_the_working_fields_are_left_out(self):
        got, _ = self.named(self.masts(6.7))
        self.assertEqual(got, [dict(name="67", dir="west", milepost=6.7)])
        self.assertEqual(list(got[0]), ["name", "dir", "milepost"])

    def test_the_masts_keep_their_order(self):
        got, _ = self.names(self.masts(6.9, 6.6, 6.7))
        self.assertEqual(got, ["69", "67", "71"])

    def test_the_line_code_keeps_the_levels_apart(self):
        got, _ = self.names(self.masts(6.7) + self.masts(6.7, code="A") + self.masts(6.6, code="A"))
        self.assertEqual(got, ["67", "A69", "A67"])

    def test_a_shift_past_98_with_no_line_code_stops_the_build(self):
        with self.assertRaisesRegex(MapError, "intermediate 97 is held by MP 9.600 and the next free number 99 "
                                                 "is over 98"):
            self.names(self.masts(9.6, 9.7))
        got, _ = self.names(self.masts(9.6, 9.7, code="B"))
        self.assertEqual(got, ["B97", "B99"])

# ---------------------------------------------------------------- running track and exit dwarfs


class LetterOrder(unittest.TestCase):
    """Two masts of one number and direction are lettered A and B in the plan order of the tracks they face
    (plan_tracks.letter_order), as parallel track numbers are (plan_order), not by drawn row."""

    @staticmethod
    def t(*ends, trial="Track e1"):
        return dict(plan_ends=ends, trial=[trial])

    def test_a_track_end_sorts_by_number_half_letter_and_leg_then_any_other_end(self):
        keys = ["end", "105B", "103BA", "helix", "103AB", "9C", "9B"]
        self.assertEqual(sorted(keys, key=track_names.end_order), ["9B", "9C", "103AB", "103BA", "105B", "end", "helix"])

    def test_spurs_follow_their_numbers(self):
        """Mast 210LA faces Track 209 Spur 1 (from 209B), 210LB Spur 2 (from 209C)."""
        one, two = self.t("209B", "end"), self.t("209C", "end", trial="Track e2")
        self.assertLess(plan_tracks.letter_order(one, 0, "B"), plan_tracks.letter_order(two, 0, "C"))

    def test_the_lower_plan_end_first_whatever_the_leg(self):
        """At Switch 203 the A mast faces Track 203-211 (from leg B), the B mast Track 203-207 (from leg C); at a
        crossover's halves the half letter of the lower end decides (217AB before 217BA)."""
        self.assertLess(plan_tracks.letter_order(self.t("203B", "211BB"), 0, "B"),
                        plan_tracks.letter_order(self.t("203C", "207A"), 0, "C"))
        self.assertLess(plan_tracks.letter_order(self.t("217AB", "221BB"), 0, "B"),
                        plan_tracks.letter_order(self.t("217BA", "219C"), 0, "A"))

    def test_a_balloon_loops_halves_by_half(self):
        loop = self.t("107B", "107C")
        self.assertLess(plan_tracks.letter_order(loop, 1, "B"), plan_tracks.letter_order(loop, 2, "C"))


class Running(unittest.TestCase):
    """mast_rule.running_tracks on a siding from Switch 1 (CP 1) through local crossover half 5A to Switch 3 (CP 3):
    5A's points A take the siding from Switch 1, its leg B runs on to Switch 3, leg C joins 5B."""

    def bands(self, x_label="5A"):
        n = {"N1": node("1", {"A": "m1", "B": "a"}), "X": node(x_label, {"A": "a", "B": "b", "C": "c"}),
             "Y": node(x_label[:-1] + "B" if x_label.endswith("A") else "9", {"A": "d", "B": "e", "C": "c"}),
             "N3": node("3", {"A": "m3", "C": "b"}), "E1": end("d", "bumper"), "E2": end("e", "bumper"),
             "O1": end("m1", "open"), "O3": end("m3", "open")}
        st = {"a": link(("N1", "B"), ("X", "A")), "b": link(("X", "B"), ("N3", "C")), "c": link(("X", "C"), ("Y", "C")),
              "d": link(("Y", "A"), ("E1", "E")), "e": link(("Y", "B"), ("E2", "E")),
              "m1": link(("N1", "A"), ("O1", "E")), "m3": link(("N3", "A"), ("O3", "E"))}
        return [("Main level", {"nodes": n, "strands": st}, {})]

    def found(self, second_main=False):
        return [track("Track 1-5", [("N1", "B"), ("X", "A")], (("sw", "1"), ("sw", "5"))),
                track("Track 3-5", [("X", "B"), ("N3", "C")], (("sw", "5"), ("sw", "3")), main=second_main),
                track("Track 5 Spur 1", [("Y", "A"), ("E1", "E")], (("sw", "5"), ("bumper", None)))]

    def test_a_siding_through_a_local_crossover_joins_two_interlockings(self):
        got = mr.running_tracks(self.bands(), self.found(), {"1": "CP 1", "3": "CP 3"})
        self.assertEqual(got, {"Track 1-5", "Track 3-5"})

    def test_one_interlocking_at_both_ends_is_no_running_track(self):
        self.assertEqual(mr.running_tracks(self.bands(), self.found(), {"1": "CP 1", "3": "CP 1"}), set())

    def test_an_end_in_no_interlocking_is_no_running_track(self):
        self.assertEqual(mr.running_tracks(self.bands(), self.found(), {"1": "CP 1"}), set())

    def test_a_main_track_ends_the_chain(self):
        self.assertEqual(mr.running_tracks(self.bands(), self.found(second_main=True), {"1": "CP 1", "3": "CP 3"}),
                         set())

    def test_a_plain_switch_is_no_crossover(self):
        self.assertEqual(mr.running_tracks(self.bands("5"), self.found(), {"1": "CP 1", "3": "CP 3"}), set())

    def test_through_leg_keeps_to_the_halfs_through_route(self):
        band = self.bands()[0][1]
        self.assertEqual([mr.through_leg(band, "X", p) for p in "ABC"], ["B", "A", None])
        self.assertIsNone(mr.through_leg(band, "N1", "B"))          # a switch with no partner half

    def test_a_track_between_two_interlockings_needs_no_crossover(self):
        found = [track("Track 1-3", [("N1", "B"), ("N3", "C")], (("sw", "1"), ("sw", "3")))]
        self.assertEqual(mr.running_tracks(self.bands(), found, {"1": "CP 1", "3": "CP 3"}), {"Track 1-3"})


class Spurs(unittest.TestCase):
    """mast_rule.signalled_spurs: a spur off a main track at a switch in no interlocking gets an exit dwarf."""

    def found(self, main=True):
        return [track("Track 7 Spur", [("N7", "C"), ("E", "E")], (("sw", "7"), ("bumper", None))),
                track("Track 5-7", [("N5", "B"), ("N7", "A")], (("sw", "5"), ("sw", "7")), main=main)]

    def test_a_spur_off_the_main_at_a_local_switch(self):
        self.assertEqual(mr.signalled_spurs(self.found(), {}), {"Track 7 Spur"})

    def test_not_at_an_interlocking_switch(self):
        self.assertEqual(mr.signalled_spurs(self.found(), {"7": "CP 5"}), set())

    def test_not_off_a_yard_track(self):
        self.assertEqual(mr.signalled_spurs(self.found(main=False), {}), set())


HEAD = ",".join(block_override_rows.OVERRIDE_COLUMNS) + "\n"


def split(level, a, b, parallel="", notes=""):
    """A block_overrides.csv split row."""
    return f"{level},split,{a},{b},{parallel},,,,,{notes}\n"


class BlockSplits(unittest.TestCase):
    """block_override_rows.read_block_splits: the owner's block splits (block_overrides.csv kind split), by level and end
    switches."""

    FOUND = [track("Track 227-241", [("A", "B"), ("B", "C")], (("sw", "227"), ("sw", "241")), level=3),
             track("Track 5-7", [("C", "B"), ("D", "C")], (("sw", "5"), ("sw", "7")), level=1)]

    def read(self, text, levels=None):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "block_overrides.csv"
            path.write_text(text, encoding="utf-8")
            return block_override_rows.read_block_splits(path, self.FOUND, levels or {"Upper": 3})

    def test_a_row_names_its_track(self):
        self.assertEqual(self.read(HEAD + split(3, 227, 241, notes="x")), {"Track 227-241"})

    def test_a_row_of_another_level_is_left_out(self):
        self.assertEqual(self.read(HEAD + split(3, 227, 241, notes="x"), {"Staging level": 1}), set())

    def test_the_other_kinds_are_not_splits(self):
        text = HEAD + "3,track,227,241,,,os:227,,,x\n" + split(1, 5, 7)
        self.assertEqual(self.read(text), set())

    def test_errors(self):
        for text, msg in (("level,switch_a,switch_b,parallel,notes\n3,227,241,,\n", "columns"),
                          (HEAD + split(4, 227, 241), r"line 2 \(level 4, kind split\): level is 1, 2 or 3"),
                          (HEAD + split(3, 241, 227), "lower first"),
                          (HEAD + split(3, 5, 7), "no track runs Switch 5 to Switch 7"),
                          (HEAD + split(3, 227, 241) * 2, "already split on line 2")):
            with self.assertRaisesRegex(MapError, msg):
                self.read(text)

    def test_a_missing_file_is_a_map_error(self):
        with self.assertRaisesRegex(MapError, "cannot read"):
            block_override_rows.read_block_splits(Path("/nonexistent/block_overrides.csv"), self.FOUND, {"Upper": 3})


class BlockOverrides(unittest.TestCase):
    """block_override_rows.read_block_overrides: the one reader of block_overrides.csv, which checks every row's shape for its
    kind whichever kinds the caller asks for, and names the file and line of a bad one."""

    def read(self, text, kinds=block_override_rows.OVERRIDE_KINDS):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "block_overrides.csv"
            path.write_text(text, encoding="utf-8")
            return block_override_rows.read_block_overrides(path, kinds)

    def test_rows_of_the_kinds_asked_for_with_their_lines(self):
        text = (HEAD + split(3, 227, 241, notes="the owner's choice") + "1,track,1,3,,1,os:1,12.5,,a\n"
                + "1,crossover_half,7,13,1,,os:7:A-13C,,,b\n")
        rows = self.read(text)
        self.assertEqual([(r["line"], r["kind"]) for r in rows], [(2, "split"), (3, "track"), (4, "crossover_half")])
        self.assertEqual(rows[1]["cm"], 12.5)
        # a track row's OS block comes back by its generated name, its id beside it
        self.assertEqual((rows[1]["block"], rows[1]["id"]), ("OS Switch 1", "os:1"))
        # a crossover half's too, named by its letter (parallel 1 is a), which it carries as `half`
        self.assertEqual((rows[2]["block"], rows[2]["id"], rows[2]["half"]), ("OS Switch 7a", "os:7:A-13C", "a"))
        self.assertIsNone(rows[0]["cm"])
        self.assertEqual(rows[0]["notes"], "the owner's choice")
        self.assertEqual([r["line"] for r in self.read(text, ("split",))], [2])
        self.assertEqual([r["line"] for r in self.read(text, ("track", "crossover_half"))], [3, 4])

    def test_a_bad_row_of_another_kind_still_stops(self):
        text = HEAD + split(3, 227, 241) + "1,track,1,3,,1,Track 1-3,,,\n"
        with self.assertRaisesRegex(MapError, r"block_overrides.csv: line 3 \(level 1, kind track\): block "
                                                 "'Track 1-3' is no OS block ID"):
            self.read(text, ("split",))

    def test_shapes(self):
        for row, msg in (("1,spur,9,11,,,OS Switch 9,,,\n", "kind one of split, track, crossover_half"),
                         ("3,split,227,241,,,OS Switch 227,,,\n", "no end, block, cm or inside"),
                         ("3,split,227,241,,241,,,,\n", "no end, block, cm or inside"),
                         ("3,split,227,241,,,,,yes,\n", "no end, block, cm or inside"),
                         ("1,track,9,11,,,os:9,,no,\n", "inside is yes or empty"),
                         ("1,track,9,11,,9,os:9,0,,\n", "cm '0' is a length in cm, more than 0"),
                         ("1,track,9,11,,9,os:9,abc,,\n", "cm 'abc' is a length"),
                         ("1,track,9,,,,os:9,,,\n", "a track between two switches"),
                         ("1,crossover_half,7,13,1,,os:7:A-13C,,yes,\n", "with no end, cm or inside"),
                         ("1,crossover_half,7,13,3,,os:7:A-13C,,,\n", r"parallel 1 or 2 \(its letter a or b\)"),
                         ("1,crossover_half,7,13,1,,os:7:A-5B,,,\n", "as its block ID has them"),
                         ("1,crossover_half,7,13,1,,OS Switch 7,,,\n", "is no crossover half's OS block ID"),
                         ("1,crossover_half,7,13,1,,os:7,,,\n", "is no crossover half's OS block ID"),
                         ("1,track,9,11\n", "block '' is no OS block"),        # short: its trailing fields empty
                         ("1,track,9,11,,,OS Switch 9,,,\n", "block 'OS Switch 9' is no OS block ID"),   # by name
                         ("1,track,9,11,,,os:9:A-13C,,,\n", "no crossover_half row of Switch 9 whose leg A runs to "
                                                              "Switch 13"),
                         ("1,track,9,11,,,os:9,,,a,extra\n", "more fields than the header's 10")):
            with self.subTest(row=row), self.assertRaisesRegex(MapError, f"block_overrides.csv: line 2.*{msg}"):
                self.read(HEAD + row)

    def test_a_short_row_reads_its_trailing_fields_as_empty(self):
        rows = self.read(HEAD + "1,crossover_half,7,13,2,,os:7:A-13C\n" + split(3, 227, 241).replace(",,,,,\n", "\n"))
        self.assertEqual([(r["kind"], r["block"], r["notes"], r["cm"]) for r in rows],
                         [("crossover_half", "OS Switch 7b", "", None), ("split", "", "", None)])

    def test_a_crossover_half_letter_is_given_once(self):
        with self.assertRaisesRegex(MapError, "line 3: Switch 7's half a is given on line 2 too"):
            self.read(HEAD + "1,crossover_half,7,13,1,,os:7:A-13C\n1,crossover_half,7,5,1,,os:7:A-5B\n")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / block_override_rows.OVERRIDES_NAME
            path.write_text(HEAD + "1,crossover_half,7,13,1,,os:7:A-13C\n1,crossover_half,7,5,2,,os:7:A-5B\n")
            self.assertEqual(hand_lists.half_letters(path),
                             {("1", "os:7:A-13C"): "a", ("1", "os:7:A-5B"): "b"})

    def test_an_unknown_kind_asked_for_stops(self):
        with self.assertRaisesRegex(MapError, "no kind helix"):
            self.read(HEAD, ("helix",))

    def test_the_committed_file_reads(self):
        import build_device_map as bdm
        rows = block_override_rows.read_block_overrides(bdm.block_overrides())
        self.assertEqual({r["kind"] for r in rows}, set(block_override_rows.OVERRIDE_KINDS))
        splits = [r for r in rows if r["kind"] == "split"]
        self.assertTrue(splits and all(r["notes"].startswith("OWNER'S CHOICE, not a rule") for r in splits))


class HomeMasts(unittest.TestCase):
    """mast_plan.home_masts: two heads when a route still diverges inside the interlocking, high from running track."""

    def kinds(self, homes, facing=()):
        patch = unittest.mock.patch.object
        with patch(mr, "masts", lambda *a, **k: [dict(m) for m in homes]), \
                patch(mr, "signalled_spurs", lambda found, cp_of: set()), \
                patch(mast_routes, "facing_on_route", lambda band, n, p, cps: ["9"] if (n, p) in facing else []):
            got = mp.home_masts([("Staging level", {}, {})], {}, [], {}, set(), levels={"Staging level": 1})
        return [(m["name"], m["kind"], m["heads"]) for m in got]

    def test_kind_from_heads_and_running_track(self):
        homes = [dict(name="2L", band=0, node="N1", leg="A", heads=1, running=True),
                 dict(name="2R", band=0, node="N1", leg="B", heads=1, running=False)]
        self.assertEqual(self.kinds(homes), [("2L", "one-searchlight", 1), ("2R", "one-low", 1)])
        self.assertEqual(self.kinds(homes, facing={("N1", "A"), ("N1", "B")}),
                         [("2L", "two-searchlight", 2), ("2R", "two-low", 2)])
        # two heads from the home rule (facing the points) stay two
        self.assertEqual(self.kinds([dict(homes[1], heads=2)]), [("2R", "two-low", 2)])


# ---------------------------------------------------------------- intermediates


class Intermediates(unittest.TestCase):
    """mast_plan.intermediates: an APB pair at a block boundary inside a running track with at least one end in an
    interlocking, where both blocks hold a train."""

    OS = {"N39": "OS Switch 39", "N37": "OS Switch 37", "N9": "OS Switch 9"}
    SEQ = ["OS Switch 39", "Track K-1", "Track K-2", "OS Switch 37"]
    CM = {"OS Switch 39": 20.0, "Track K-1": 300.0, "Track K-2": 250.0, "OS Switch 37": 30.0, "OS Switch 9": 20.0}
    CPS = {"37": "Princess", "39": "Princess"}

    def bands(self, start_mp=6.5, end_mp=None, on_count=("N39", "N37"), title="Staging level"):
        length = 600.0 / CM_PER_SCALE_MILE
        at = {"N39": start_mp, "N37": start_mp + length if end_mp is None else end_mp}
        band = {"nodes": {"N39": node("39", {}), "N37": node("37", {}), "N9": node("9", {}),
                          "END": node("", {}, kind="end", sub="bumper")},
                "mp": {n: (n, at[n], 0.0, n) for n in on_count}}
        return [(title, band, {})]

    def pairs(self, bands=None, run=None, cm=None, cps=None, main=True, levels=None, running=frozenset()):
        run = run or (("N39", "B"), self.SEQ, ("N37", "A"))
        found = [track("Track K", [run[0], run[2]], (("sw", "39"), ("sw", "37")), main=main)]
        return mp.intermediates(bands or self.bands(), found, {0: [run]}, {0: {"os": self.OS}},
                                self.CM if cm is None else cm, self.CPS if cps is None else cps, set(running),
                                levels or {"Staging level": 1})

    def test_a_pair_at_the_boundary_named_from_its_milepost(self):
        west, east = self.pairs()
        m = round(6.5 + 320.0 / CM_PER_SCALE_MILE, 3)
        self.assertEqual(m, 6.673)
        self.assertEqual(west, dict(name="67", level=1, band=0, dir="west", protects="Track K-1", facing="Track K-2",
                                    milepost=m, start=("N39", "B"), end=("N37", "A"), to=("N39", "B"), toward="39",
                                    other="37", dist=320.0, total=600.0, cp="Princess"))
        self.assertEqual((east["name"], east["dir"], east["facing"], east["protects"], east["toward"], east["dist"]),
                         ("66", "east", "Track K-1", "Track K-2", "37", 280.0))

    def test_west_is_toward_the_lower_milepost_whichever_end_that_is(self):
        west, east = self.pairs(self.bands(start_mp=7.0, end_mp=6.5))
        self.assertEqual((west["name"], west["toward"], west["facing"], west["protects"], west["dist"]),
                         ("67", "37", "Track K-1", "Track K-2", 280.0))
        self.assertEqual((east["name"], east["toward"]), ("66", "39"))

    def test_both_blocks_must_hold_a_train(self):
        self.assertEqual(mast_routes.LONG_CM, 150.0)
        self.assertEqual(self.pairs(cm=dict(self.CM, **{"Track K-2": 150.0})), [])
        self.assertEqual(len(self.pairs(cm=dict(self.CM, **{"Track K-2": 150.1}))), 2)

    def test_a_block_with_no_length_stops(self):
        with self.assertRaisesRegex(MapError, r"no length for block\(s\) \['OS Switch 37', 'OS Switch 39', "
                                                 r"'Track K-2'\]"):
            self.pairs(cm={"Track K-1": 300.0})

    def test_one_interlocking_end_is_enough(self):
        west, east = self.pairs(cps={"39": "Princess"}, main=True)
        self.assertEqual((west["cp"], east["cp"]), ("Princess", "Princess"))     # 37 in none: the other end's
        self.assertEqual(self.pairs(cps={}), [])

    def test_only_on_running_track(self):
        self.assertEqual(self.pairs(cps={"39": "Princess"}, main=False), [])                    # a yard track
        self.assertEqual(len(self.pairs(main=False)), 2)                 # a long track inside one interlocking
        self.assertEqual(len(self.pairs(cps={"39": "A", "37": "B"}, main=False, running={"Track K"})), 2)

    def test_a_bumper_end_or_a_single_block_has_none(self):
        self.assertEqual(self.pairs(run=(("N39", "B"), self.SEQ[:3], ("END", "x"))), [])
        self.assertEqual(self.pairs(run=(("N39", "B"), ["OS Switch 39", "Track K-1", "OS Switch 37"], ("N37", "A"))), [])

    def test_a_switch_off_the_milepost_count_stops(self):
        with self.assertRaisesRegex(MapError, r"Track K-1\|Track K-2 cannot be numbered: switch 37 is not on"):
            self.pairs(self.bands(on_count=("N39",)))

    def test_the_line_code_comes_first(self):
        west, east = self.pairs(self.bands(title="Main level"), levels={"Main level": 2})
        self.assertEqual((west["name"], east["name"], west["level"]), ("A67", "A66", 2))

    def test_a_balloon_loop_is_read_from_its_half_1(self):
        # the run from leg C (Loop 2) is turned round: the eastbound mast faces Loop 1, the westbound Loop 2
        cm = {"OS Switch 107": 0.0, "Track 107 Loop 1": 388.0, "Track 107 Loop 2": 388.0}
        band = {"nodes": {"N1": node("107", {})}, "mp": {"N1": ("N1", 8.185, 0.0, "N1")}}
        run = (("N1", "C"), ["Track 107 Loop 2", "Track 107 Loop 1"], ("N1", "B"))
        found = [track("Track 107 Loop", [("N1", "C"), ("N1", "B")], (("sw", "107"), ("sw", "107")), main=True,
                       loop=True, level=2)]
        got = mp.intermediates([("Main level", band, {})], found, {0: [run]}, {0: {"os": {"N1": "OS Switch 107"}}}, cm,
                               {"107": "CP 107"}, set(), {"Main level": 2})
        self.assertEqual({(m["name"], m["dir"], m["facing"], m["protects"]) for m in got},
                         {("A83", "west", "Track 107 Loop 2", "Track 107 Loop 1"),
                          ("A84", "east", "Track 107 Loop 1", "Track 107 Loop 2")})


# ---------------------------------------------------------------- virtual masts


class Virtual(unittest.TestCase):
    """mast_plan.virtual_masts on Switch 119 (leg A from an open main, B to Switch 101, C a spur to a buffer stop) and
    Switch 101 (B and C spurs to buffer stops); a home mast 120RA enters Switch 119 at A."""

    def bands(self):
        n = {"N5": node("119", {"A": "m", "B": "s1", "C": "sp"}), "N1": node("101", {"A": "s1", "B": "b1", "C": "b2"}),
             "O": end("m", "open"), "E1": end("b1", "bumper"), "E2": end("b2", "bumper"), "E3": end("sp", "bumper")}
        st = {"m": link(("N5", "A"), ("O", "E")), "s1": link(("N5", "B"), ("N1", "A")),
              "sp": link(("N5", "C"), ("E3", "E")), "b1": link(("N1", "B"), ("E1", "E")),
              "b2": link(("N1", "C"), ("E2", "E"))}
        band = {"nodes": n, "strands": st, "rail": {k: 1 for k in n}, "R": {"srow": {"b1": 1, "b2": 2, "sp": 3}}}
        return [("Main level", band, {})]

    RUNS = {0: [(("N1", "B"), ["Track 101 Spur 1"], ("E1", "E")), (("N1", "C"), ["Track 101 Spur 2"], ("E2", "E")),
                (("N5", "C"), ["Track 119 Spur"], ("E3", "E")), (("N5", "B"), ["Track 101-119"], ("N1", "A"))]}
    CM = {"Track 101 Spur 1": 80.0, "Track 101 Spur 2": 90.0, "Track 119 Spur": 70.0, "Track 101-119": 50.0}
    HOME = [dict(name="120RA", band=0, node="N5", leg="A")]

    def virtual(self, taken=("120RA",), runs=None, home=None):
        return mp.virtual_masts(self.bands(), {}, self.HOME if home is None else home, runs or self.RUNS, self.CM,
                                set(taken), {"Main level": 2})

    def test_a_bumper_mast_where_a_route_reaches_a_buffer_stop_first(self):
        got = {m["name"]: (m["facing"], m["switch"], m["dir"], m["total"], m["needed_by"]) for m in self.virtual()}
        self.assertEqual(got, {"102RA": ("Track 101 Spur 1", "101", "east", 80.0, ["120RA"]),
                               "102RB": ("Track 101 Spur 2", "101", "east", 90.0, ["120RA"]),
                               "120RB": ("Track 119 Spur", "119", "east", 70.0, ["120RA"])})

    def test_a_clash_with_a_visible_name_takes_the_next_letter(self):
        self.assertIn("120RC", {m["name"] for m in self.virtual(taken=("120RA", "120RB"))})

    def test_a_visible_mast_with_the_bare_name_stops(self):
        with self.assertRaisesRegex(MapError, "Mast 120R stands already"):
            self.virtual(taken=("120R",))

    def test_more_than_four_of_one_number_and_letter_stops(self):
        with self.assertRaisesRegex(MapError, "Mast 120R: 5 masts of one number and letter"):
            self.virtual(taken=("120RA", "120RB", "120RC", "120RD"))

    def test_a_route_that_meets_a_visible_mast_needs_none_beyond_it(self):
        home = self.HOME + [dict(name="102L", band=0, node="N1", leg="A")]     # a mast at Switch 101 stops 120RA there
        got = {m["name"]: m["needed_by"] for m in self.virtual(taken=("120RA", "102L"), home=home)}
        self.assertEqual(got, {"102RA": ["102L"], "102RB": ["102L"], "120RB": ["120RA"]})

    def test_a_buffer_stop_no_track_from_a_switch_reaches_stops(self):
        runs = {0: [r for r in self.RUNS[0] if r[2][0] != "E3"]}
        with self.assertRaisesRegex(MapError, "end at buffer stop E3 on 'Main level', which no track from a switch"):
            self.virtual(runs=runs)

    def test_a_block_with_no_length_stops(self):
        runs = {0: [(("N5", "C"), ["Track X"], ("E3", "E"))] + self.RUNS[0][:2]}
        with self.assertRaisesRegex(MapError, r"no length for block\(s\) \['Track X'\]"):
            self.virtual(runs=runs)


class SystemNames(unittest.TestCase):
    """mast_plan.virtual_system_names and read_retired: ordinals fixed once given, from each level's thousand."""

    def test_old_names_stay_and_new_ones_take_the_next_ordinal_of_the_level(self):
        old = {"Mast 4LA": "IF$vsm:basic:one-low($1001)", "Mast 12L": "IF$vsm:basic:one-low($1026)"}
        retired = {"Mast 40RB": "IF$vsm:basic:one-low($1030)", "Mast 12L": "IF$vsm:basic:one-low($1026)"}
        got = mp.virtual_system_names(["4LA", "99L"], 1, old, retired)
        self.assertEqual(got, {"4LA": "IF$vsm:basic:one-low($1001)", "99L": "IF$vsm:basic:one-low($1031)"})

    def test_each_level_starts_in_its_own_thousand(self):
        self.assertEqual(mp.virtual_system_names(["102RA", "102RB"], 2, {}, {"Mast 4LA": "IF$vsm:basic:one-low($1001)"}),
                         {"102RA": "IF$vsm:basic:one-low($2001)", "102RB": "IF$vsm:basic:one-low($2002)"})
        self.assertEqual(mp.virtual_system_names(["206L"], 3, {}, {}), {"206L": "IF$vsm:basic:one-low($3001)"})

    def test_a_mast_being_dropped_may_still_be_in_the_master(self):
        old = {"Mast 10RA": "IF$vsm:basic:one-low($1021)"}
        self.assertEqual(mp.virtual_system_names([], 1, old, {"Mast 10RA": "IF$vsm:basic:one-low($1021)"}), {})

    def test_errors(self):
        r = {"Mast 10RA": "IF$vsm:basic:one-low($1021)"}
        with self.assertRaisesRegex(MapError, "lists Mast 10RA, which the rule places again"):
            mp.virtual_system_names(["10RA"], 1, {}, r)
        with self.assertRaisesRegex(MapError, "gives Mast 10RA another system name"):
            mp.virtual_system_names([], 1, {"Mast 10RA": "IF$vsm:basic:one-low($1030)"}, r)
        with self.assertRaisesRegex(MapError, r"Mast 102RA of level 2 have ordinals outside 2001 to 2999"):
            mp.virtual_system_names(["102RA"], 2, {"Mast 102RA": "IF$vsm:basic:one-low($1040)"}, {})
        with self.assertRaisesRegex(MapError, "level 3 has no virtual mast ordinal left"):
            mp.virtual_system_names(["X"], 3, {"Mast Y": "IF$vsm:basic:one-low($3999)"},
                                    {"Mast Y": "IF$vsm:basic:one-low($3999)"})
        with self.assertRaisesRegex(MapError, "no longer places Mast 104R: add each to retired_virtual_masts.csv"):
            mp.virtual_system_names(["102RA"], 2, {"Mast 102RA": "IF$vsm:basic:one-low($2001)",
                                                   "Mast 104R": "IF$vsm:basic:one-low($2003)"}, {})
        with self.assertRaisesRegex(MapError, "'IH:HART:C1:8LC' is not a virtual mast system name"):
            mp.virtual_system_names(["10RA"], 1, {}, {"Mast 8LC": "IH:HART:C1:8LC"})

    def test_read_retired(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "retired_virtual_masts.csv"
            path.write_text("mast,system_name,dropped,notes\nMast 8LC,IF$vsm:basic:one-low($1018),2026-11-20,x\n")
            self.assertEqual(mp.read_retired(path), {"Mast 8LC": "IF$vsm:basic:one-low($1018)"})
            for text in ("mast,system_name,dropped,notes\nMast 8LC,IF$vsm:basic:one-low($1018),,\n"
                         "Mast 8LD,IF$vsm:basic:one-low($1018),,\n",
                         "mast,system_name,dropped,notes\nMast 8LC,IH:HART:C1:8LC,,\n"):
                path.write_text(text)
                with self.assertRaisesRegex(MapError, "line \\d+"):
                    mp.read_retired(path)
            path.write_text("mast,system_name\n")
            with self.assertRaisesRegex(MapError, "columns"):
                mp.read_retired(path)
        with self.assertRaisesRegex(MapError, "cannot read"):
            mp.read_retired(Path("/nonexistent/retired.csv"))


class Plan(unittest.TestCase):
    """mast_plan.plan's own checks."""

    BANDS = [("Staging level", {"nodes": {}, "strands": {}}, {})]

    def test_a_band_with_no_block_layer_stops(self):
        with self.assertRaisesRegex(MapError, r"no block layer for band\(s\) \['Staging level'\]"):
            mp.plan(self.BANDS, {}, [], levels={"Staging level": 1}, cp_of={}, layer={}, cm={})

    def test_a_name_given_twice_stops(self):
        patch = unittest.mock.patch.object
        with patch(mp, "run_blocks", lambda band, names: []), patch(mr, "running_tracks", lambda *a: set()), \
                patch(mp, "home_masts", lambda *a, **k: [dict(name="67")]), \
                patch(mp, "intermediates", lambda *a: [dict(name="67")]), \
                patch(mp, "virtual_masts", lambda *a: []), \
                self.assertRaisesRegex(MapError, "mast names given twice: 67"):
            mp.plan(self.BANDS, {}, [], levels={"Staging level": 1}, cp_of={}, layer={0: {}}, cm={})


# ---------------------------------------------------------------- the committed plan


class CommittedPlan(RepoReadOnly, unittest.TestCase):
    """The rules over the committed plan give exactly what the hand lists they replaced held (running_tracks_,
    signalled_spurs_ and split_tracks_main_upper.csv, deleted 2026-11-20), and on staging Scale is running track."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import build_device_map as bdm
        import build_layout_le as bl
        from hartlib import railroad
        cls.levels = bdm.LEVELS
        try:
            bands, joined, runs, _corners = bdm.solve()
        except bl.BuildError as exc:
            skip_or_fail(exc, "these data checks")
        rr = railroad.Railroad(bdm.sources(), upto="inputs")
        cls.bands = bands
        cls.found = bdm.named_tracks(bands, joined, runs, rr.plan_overrides.data)
        cls.cp_of = {s: i.name for i in rr.level_control_points for s in i.switches}
        cls.staging = plan_tracks.tracks(bands, runs, joined, {1: "H"}, levels={"Staging level": 1})
        plan_tracks.track_names(cls.staging)
        cls.staging_cp = {s: i.name for i in rr.interlockings if i.level == 1 for s in i.switches}
        cls.splits = bdm.block_overrides()

    def test_running_track_on_main_and_upper_is_the_old_hand_list(self):
        self.assertEqual(mr.running_tracks(self.bands, self.found, self.cp_of),
                         {"Track 119-121", "Track 121-123", "Track 211-217 1", "Track 217-219"})

    def test_running_track_on_staging_is_scale(self):
        # staging's own rule names its two 5-7 tracks in plan order (plan_tracks.plan_order): East Ext (5B-7A) is 1,
        # Scale (5C-7B) is 2
        self.assertEqual(mr.running_tracks(self.bands, self.staging, self.staging_cp), {"Track 5-7 2"})

    def test_exit_dwarfs_are_the_old_hand_list(self):
        self.assertEqual(mr.signalled_spurs(self.found, self.cp_of), {"Track 241 Spur"})
        self.assertEqual(mr.signalled_spurs(self.staging, self.staging_cp), set())

    def test_the_owners_block_splits(self):
        self.assertEqual(block_override_rows.read_block_splits(self.splits, self.found, self.levels), {"Track 227-241"})
        # staging's: the Princess balloon, K-2 and K-1 (a level 1 row since step 5 part 1)
        self.assertEqual(block_override_rows.read_block_splits(self.splits, self.staging, {"Staging level": 1}), {"Track 37-39"})


if __name__ == "__main__":
    unittest.main()
