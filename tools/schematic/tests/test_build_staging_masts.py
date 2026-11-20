"""build_staging_masts.py: staging's masts by rule. The rule functions on small hand-written inputs (names, numbers,
control points, ordering, the rows it writes), main() on temporary files, and, as data checks under a guard that fails
any write into the repo (repo_read_only.py), the repo's committed data.
The wired heads have their own tests (tools/audit/tests/test_staging_wired_heads.py)."""
from __future__ import annotations

import contextlib
import csv
import io
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))     # repo_read_only.py

import build_device_map as bdm  # noqa: E402
import build_staging_masts as bsm  # noqa: E402
import mast_rule  # noqa: E402
import staging_device_map as sdm  # noqa: E402
from hartlib import level_masts  # noqa: E402
from repo_read_only import RepoReadOnly, in_repo, repo_read_only  # noqa: E402

CM_PER_SCALE_MILE = 63360 * 2.54 / 87.1


def sw(label):
    return dict(kind="switch", label=label)


def strand(edge, name, cm=100.0):
    return dict(edge=edge, name=name, cm=cm)


def rows_of(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def write_rows(path: Path, columns, rows) -> Path:
    path.write_text(bsm.csv_text(rows, columns), encoding="utf-8")
    return path


class Names(unittest.TestCase):
    def test_internal_head_names(self):
        self.assertEqual(bsm.internal_head("Head 2R"), "IH:HART:C1:2R")
        self.assertEqual(bsm.internal_head("Head 24RA Top"), "IH:HART:C1:24RA_Top")
        self.assertEqual(bsm.internal_head("Head 67"), "IH:HART:C1:67")
        for bad in ("Mast 2R", "Head", "Head 2R Middle", "Head 2r", "head 2R", "Head 2R "):
            with self.assertRaisesRegex(bsm.RuleError, r"is not named Head <key>"):
                bsm.internal_head(bad)

    def test_one_head_takes_the_masts_key_two_take_top_and_bottom(self):
        self.assertEqual(bsm.head_users("Mast 4RA", 1), ["Head 4RA"])
        self.assertEqual(bsm.head_users("Mast 2L", 2), ["Head 2L Top", "Head 2L Bottom"])
        self.assertEqual(bsm.head_users("Mast 67", 1), ["Head 67"])

    def test_an_unwired_mast_gets_internal_heads(self):
        self.assertEqual(bsm.head_names("Mast 2L", 2, {}),
                         [("IH:HART:C1:2L_Top", "Head 2L Top"), ("IH:HART:C1:2L_Bottom", "Head 2L Bottom")])
        self.assertEqual(bsm.head_names("Mast 4RA", 1, {"Mast 6LB": {}}), [("IH:HART:C1:4RA", "Head 4RA")])


class Numbers(unittest.TestCase):
    """An intermediate's number is its milepost in tenths, odd westbound and even eastbound."""

    def test_odd_west_even_east(self):
        self.assertEqual([bsm.signal_number(6.7, w) for w in (True, False)], [67, 68])
        self.assertEqual([bsm.signal_number(6.714, w) for w in (True, False)], [67, 68])
        self.assertEqual([bsm.signal_number(5.7, w) for w in (True, False)], [57, 58])
        # on an even tenth the eastward signal keeps it and the westward one takes the next odd number
        self.assertEqual([bsm.signal_number(6.6, w) for w in (True, False)], [67, 66])
        self.assertEqual([bsm.signal_number(6.69, w) for w in (True, False)], [67, 66])

    def test_the_tenth_is_cut_not_rounded(self):
        self.assertEqual(bsm.signal_number(6.799, False), 68)
        self.assertEqual(bsm.signal_number(6.799, True), 67)

    def test_float_noise_under_a_tenth_still_counts_as_that_tenth(self):
        # the 1e-9 in signal_number: a milepost summed from parts can land a hair under its tenth
        mp = 0.7 + 0.1
        self.assertLess(mp, 0.8)
        self.assertEqual(int(mp * 10), 7)                           # without the guard this is tenth 7
        self.assertEqual(bsm.signal_number(mp, True), 9)            # tenth 8: westward takes the next odd number
        self.assertEqual(bsm.signal_number(mp, False), 8)
        self.assertEqual(bsm.signal_number(0.8, True), 9)

    def test_open_question_an_even_tenth_and_the_next_odd_tenth_share_the_westward_number(self):
        # OPEN QUESTION for the staging signal rule (not decided here; this only pins what the code does today).
        # At an even tenth the westward signal takes the next odd number, so MP 6.6 and MP 6.7 both give 67 westward,
        # and the pair at MP 6.6 is 67/66 (west above east) while the pair at MP 6.7 is 67/68 (west below east).
        # Two pairs a tenth apart would be given the same westward name, which generate() then stops on as a name
        # given twice. Whether an even tenth should count down (65/66) is the rule owner's call.
        self.assertEqual([bsm.signal_number(6.6, w) for w in (True, False)], [67, 66])
        self.assertEqual([bsm.signal_number(6.7, w) for w in (True, False)], [67, 68])
        self.assertEqual(bsm.signal_number(6.6, True), bsm.signal_number(6.7, True))

    def test_open_question_the_message_says_98_but_99_is_given(self):
        # OPEN QUESTION, same owner: the stop is on the tenth (99 and up), not on the number. MP 9.8 westward gives
        # 99 although the message says "staging names stop at 98", and MP 9.9 is refused westward too, where the
        # number would also be 99. Pinned as it is today.
        self.assertEqual(bsm.signal_number(9.8, True), 99)
        with self.assertRaisesRegex(bsm.RuleError, r"MP 9\.90 gives intermediate number 99 or more; "
                                                   r"staging names stop at 98"):
            bsm.signal_number(9.9, True)

    def test_numbers_stay_under_100(self):
        self.assertEqual([bsm.signal_number(9.8, w) for w in (True, False)], [99, 98])
        for mp in (9.9, 10.0, 12.34):
            for west in (True, False):
                with self.assertRaisesRegex(bsm.RuleError, "staging names stop at 98"):
                    bsm.signal_number(mp, west)

    def test_node_mileposts_take_each_strands_ends_first_one_wins(self):
        band = {"mp": {"s1": ("N1", 5.7, 0.5, "N2"), "s2": ("N2", 6.3, 0.25, "N3"), "s3": ("N4", 1.0, 0.0, "N1")}}
        got = bsm.node_mileposts(band)
        self.assertEqual(set(got), {"N1", "N2", "N3", "N4"})
        self.assertEqual(got["N1"], 5.7)                 # s3 reaches N1 at 1.0 later: the first value stays
        self.assertAlmostEqual(got["N2"], 6.2)           # s1's end, not s2's start
        self.assertAlmostEqual(got["N3"], 6.55)
        self.assertEqual(got["N4"], 1.0)


class PlanEdge(unittest.TestCase):
    BAND = {"strands": {"a": strand("e16.0", "K-1"), "b": strand("e16.1", "K-2"), "c": strand("e16.2", ""),
                        "d": strand("e9+e10", "Main West"), "e": strand("e160", "Other")}}

    def test_one_edge_with_every_name_it_carries(self):
        self.assertEqual(bsm.plan_edge(self.BAND, ["a"]), ("e16", ["K-1", "K-2"]))       # the unnamed part left out
        self.assertEqual(bsm.plan_edge(self.BAND, ["b", "c"]), ("e16", ["K-1", "K-2"]))
        self.assertEqual(bsm.plan_edge(self.BAND, ["d"]), ("e9+e10", ["Main West"]))
        self.assertEqual(bsm.plan_edge(self.BAND, ["e"]), ("e160", ["Other"]))           # e160 is not e16

    def test_a_run_over_two_edges_stops(self):
        with self.assertRaisesRegex(bsm.RuleError, r"spans plan edges \['e16', 'e9\+e10'\]"):
            bsm.plan_edge(self.BAND, ["a", "d"])


class Interlockings(unittest.TestCase):
    """interlockings_staging.csv: the signal rule's control points, a switch in at most one."""
    COLUMNS = ("interlocking", "switches", "notes")

    def read(self, rows, switches):
        with tempfile.TemporaryDirectory() as d:
            path = write_rows(Path(d) / "interlockings_staging.csv", self.COLUMNS,
                              [dict(interlocking=n, switches=s, notes="") for n, s in rows])
            return bsm.interlockings(set(switches), path)

    def test_each_switch_maps_to_its_interlocking(self):
        got = self.read([("Brick", "1, 3,5"), ("Barn", "7"), ("Empty", "")], {"1", "3", "5", "7", "9"})
        self.assertEqual(got, {"1": "Brick", "3": "Brick", "5": "Brick", "7": "Barn"})   # 9 is in no control point

    def test_a_switch_that_is_no_staging_switch_stops(self):
        with self.assertRaisesRegex(bsm.RuleError, r"interlockings_staging.csv: Brick: switch 101 is no staging switch"):
            self.read([("Brick", "1,101")], {"1"})

    def test_a_switch_in_two_interlockings_stops(self):
        with self.assertRaisesRegex(bsm.RuleError, "switch 3 is in interlockings Brick and Plane"):
            self.read([("Brick", "1,3"), ("Plane", "3")], {"1", "3"})

    def test_other_columns_stop(self):
        with tempfile.TemporaryDirectory() as d:
            path = write_rows(Path(d) / "x.csv", ("interlocking", "switches"), [dict(interlocking="A", switches="1")])
            with self.assertRaisesRegex(sdm.StagingMapError, "columns"):
                bsm.interlockings({"1"}, path)


def home(name, node, leg, **more):
    """A home mast as mast_rule.masts gives it."""
    m = dict(name=name, node=node, leg=leg, cp="Brick", switch="1", kind="one-low", heads=1, letter=name[-1],
             strand="s", running=False)
    m.update(more)
    return m


class Generate(unittest.TestCase):
    """generate() with the plan readers stubbed: what it makes of the home masts mast_rule.masts gives it."""

    BAND = {"nodes": {"N1": sw("1"), "N3": sw("3"), "N5": sw("5"), "END": dict(kind="bumper", label="")},
            "strands": {"west": strand("e1", "Main West", 300.0), "mid": strand("e2", "Scale", 120.0),
                        "short": strand("e3", "", 10.0), "stub": strand("e4", "Stub", 40.0)},
            "mp": {}}
    NAMES = {"os": {"N1": "OS Switch 1", "N3": "OS Switch 3", "N5": "OS Switch 5"}}
    RUNS = [(("N1", "A"), ["Track Main West"], ("END", "x")),
            (("N1", "B"), ["OS Switch 1", "Track Scale", "OS Switch 3"], ("N3", "A")),
            (("N3", "B"), [], ("N5", "A")),
            (("N5", "B"), [], ("END", "y"))]
    CHAINS = {("N1", "A"): ["west"], ("N1", "B"): ["mid"], ("N3", "A"): ["mid"], ("N3", "B"): ["short"],
              ("N5", "A"): ["short"], ("N5", "B"): ["stub"]}
    CM = {"Track Main West": 300.0, "OS Switch 1": 20.0, "Track Scale": 100.0, "OS Switch 3": 30.0}
    CPS = {"1": "Brick", "3": "Brick", "5": "Brick"}

    def generate(self, homes, facing=(), wired=None, cm=None, runs=None):
        """generate() over `homes`; `facing`: the (node, leg) whose routes meet facing points (facing_on_route)."""
        patch = unittest.mock.patch.object
        with patch(mast_rule, "tracks", lambda *a, **k: []), patch(mast_rule, "track_names", lambda found: None), \
                patch(mast_rule, "masts", lambda *a, **k: [dict(m) for m in homes]), \
                patch(mast_rule, "facing_on_route", lambda band, n, p, cps: ["9"] if (n, p) in facing else []), \
                patch(bsm, "block_cm", lambda: dict(self.CM if cm is None else cm)), \
                patch(sdm, "run_blocks", lambda band, names: list(self.RUNS if runs is None else runs)), \
                patch(bsm, "run_strands", lambda band: dict(self.CHAINS)):
            return bsm.generate(self.BAND, [], None, None, self.NAMES, self.CPS, wired or {})

    def one(self, m, **kw):
        (got,) = self.generate([m], **kw)
        return got

    def test_a_turnout_mast_where_the_block_boundary_is_at_the_leg(self):
        got = self.one(home("2L", "N1", "A", heads=2, running=True))
        self.assertEqual(got, dict(mast="Mast 2L", cp="Brick", switch="1", facing="Track Main West",
                                   protects="OS Switch 1", kind="two-searchlight", heads=2, dir="west", toward="1",
                                   run="1;", names=["Main West"], edge_cm=300.0, cm_from_toward=0.0, edge="e1",
                                   node="N1", leg="A", strand="s", running=True, signal_kind="planned"))

    def test_an_anchor_mast_where_the_os_block_runs_past_the_leg(self):
        got = self.one(home("2R", "N1", "B"))
        self.assertEqual((got["switch"], got["toward"], got["facing"], got["protects"]),
                         ("", "1", "Track Scale", "OS Switch 1"))
        self.assertEqual((got["run"], got["dir"], got["edge_cm"], got["cm_from_toward"]), ("1;3", "east", 150.0, 20.0))

    def test_an_anchor_past_the_drawn_track_is_measured_from_the_far_end(self):
        # the OS block is longer than the track the plan draws (120 cm): the distance is from the other end
        got = self.one(home("2R", "N1", "B"), cm=dict(self.CM, **{"OS Switch 1": 125.0}))
        self.assertEqual((got["edge_cm"], got["cm_from_toward"]), (255.0, 130.0))

    def test_the_other_end_of_a_run_reads_its_blocks_backwards(self):
        got = self.one(home("4L", "N3", "A", switch="3"))
        self.assertEqual((got["switch"], got["facing"], got["protects"], got["cm_from_toward"], got["run"]),
                         ("", "Track Scale", "OS Switch 3", 30.0, "3;1"))

    def test_with_no_block_between_two_switches_a_mast_faces_the_far_os_block(self):
        got = self.one(home("4R", "N3", "B", switch="3"))
        self.assertEqual((got["switch"], got["facing"], got["protects"], got["edge_cm"]),
                         ("3", "OS Switch 5", "OS Switch 3", 0.0))

    def test_no_block_to_face_stops(self):
        with self.assertRaisesRegex(bsm.RuleError, "switch 5 leg B: no block to face"):
            self.generate([home("6R", "N5", "B", switch="5")])

    def test_kind_two_heads_when_a_route_still_diverges_high_from_running_track(self):
        homes = [home("2L", "N1", "A", running=True), home("2R", "N1", "B", running=False)]
        kinds = lambda **kw: [(m["mast"], m["kind"], m["heads"]) for m in self.generate(homes, **kw)]  # noqa: E731
        self.assertEqual(kinds(), [("Mast 2L", "one-searchlight", 1), ("Mast 2R", "one-low", 1)])
        self.assertEqual(kinds(facing={("N1", "A"), ("N1", "B")}),
                         [("Mast 2L", "two-searchlight", 2), ("Mast 2R", "two-low", 2)])
        # two heads from the home rule stay two; the kind mast_rule gave is replaced by heads and running
        got = self.one(home("2R", "N1", "B", heads=2, kind="two-searchlight", running=False))
        self.assertEqual((got["kind"], got["heads"]), ("two-low", 2))

    def test_direction_follows_the_letter(self):
        self.assertEqual(self.one(home("2L", "N1", "A"))["dir"], "west")
        self.assertEqual(self.one(home("2R", "N1", "A"))["dir"], "east")

    def test_a_mast_with_wired_heads_is_a_field_signal(self):
        homes = [home("2L", "N1", "A"), home("2R", "N1", "B")]
        got = self.generate(homes, wired={"Mast 2R": {"Head 2R": {}}})
        self.assertEqual([(m["mast"], m["signal_kind"]) for m in got], [("Mast 2L", "planned"), ("Mast 2R", "field")])

    def test_order_by_number_then_name(self):
        homes = [home(n, "N1", "A") for n in ("24L", "4RB", "8RA", "4RA", "2R", "24RA", "2L", "36RA", "8LA")]
        self.assertEqual([m["mast"] for m in self.generate(homes)],
                         ["Mast 2L", "Mast 2R", "Mast 4RA", "Mast 4RB", "Mast 8LA", "Mast 8RA", "Mast 24L", "Mast 24RA",
                          "Mast 36RA"])

    def test_a_name_given_twice_stops(self):
        with self.assertRaisesRegex(bsm.RuleError, r"the rule names a mast twice: \['Mast 2L'\]"):
            self.generate([home("2L", "N1", "A"), home("2L", "N1", "B")])


class Intermediates(unittest.TestCase):
    """intermediates(): an APB pair at a block boundary of a track between two control-point switches (the signal
    rule's control points: interlockings_staging.csv) where both blocks hold a train."""

    NAMES = {"os": {"N37": "OS Switch 37", "N39": "OS Switch 39", "N9": "OS Switch 9"}}
    CPS = {"37": "Princess", "39": "Princess"}
    CHAINS = {("N39", "B"): ["k1", "k2"], ("N37", "A"): ["k1", "k2"], ("N9", "B"): ["k1", "k2"]}
    SEQ = ["OS Switch 39", "Track K-1", "Track K-2", "OS Switch 37"]
    CM = {"OS Switch 39": 20.0, "Track K-1": 300.0, "Track K-2": 250.0, "OS Switch 37": 30.0}

    def band(self, start_mp=6.5, end_mp=None, on_count=("N39", "N37")):
        length = 600.0 / CM_PER_SCALE_MILE
        end_mp = start_mp + length if end_mp is None else end_mp
        at = {"N39": start_mp, "N37": end_mp}
        return {"nodes": {"N39": sw("39"), "N37": sw("37"), "N9": sw("9"), "END": dict(kind="bumper", label="")},
                "strands": {"k1": strand("e16.0", "K-1"), "k2": strand("e16.1", "K-2")},
                "mp": {n: (n, at[n], 0.0, n) for n in on_count}}

    def pairs(self, band=None, run=None, cm=None, cps=None):
        run = run or (("N39", "B"), self.SEQ, ("N37", "A"))
        with unittest.mock.patch.object(sdm, "run_blocks", lambda band, names: [run]):
            return bsm.intermediates(band or self.band(), self.NAMES, self.CPS if cps is None else cps,
                                     self.CM if cm is None else cm, self.CHAINS)

    def test_a_pair_at_the_boundary_named_from_its_milepost(self):
        west, east = self.pairs()
        mp = round(6.5 + 320.0 / CM_PER_SCALE_MILE, 3)
        self.assertEqual(mp, 6.673)
        self.assertEqual(west, dict(mast="Mast 67", cp="Princess", switch="", facing="Track K-2", protects="Track K-1",
                                    kind="one-searchlight", heads=1, dir="west", toward="39", run="39;37",
                                    names=["K-1", "K-2"], edge_cm=600.0, cm_from_toward=320.0, edge="e16", node="N39",
                                    milepost=mp))
        self.assertEqual(east, dict(mast="Mast 66", cp="Princess", switch="", facing="Track K-1", protects="Track K-2",
                                    kind="one-searchlight", heads=1, dir="east", toward="37", run="37;39",
                                    names=["K-1", "K-2"], edge_cm=600.0, cm_from_toward=280.0, edge="e16", node="N37",
                                    milepost=mp))

    def test_west_is_toward_the_lower_milepost_whichever_end_that_is(self):
        # the count falls along the run: the far switch (37) is the west end, and the milepost counts from it
        west, east = self.pairs(self.band(start_mp=7.0, end_mp=6.5))
        mp = round(6.5 + 280.0 / CM_PER_SCALE_MILE, 3)
        self.assertEqual((west["mast"], west["toward"], west["facing"], west["protects"], west["cm_from_toward"],
                          west["milepost"]), ("Mast 67", "37", "Track K-1", "Track K-2", 280.0, mp))
        self.assertEqual((east["mast"], east["toward"], east["facing"], east["protects"], east["cm_from_toward"]),
                         ("Mast 66", "39", "Track K-2", "Track K-1", 320.0))

    def test_both_blocks_must_hold_a_train(self):
        self.assertEqual(mast_rule.LONG_CM, 150.0)
        self.assertEqual(self.pairs(cm=dict(self.CM, **{"Track K-2": 150.0})), [])       # exactly LONG_CM is short
        self.assertEqual(len(self.pairs(cm=dict(self.CM, **{"Track K-2": 150.1}))), 2)
        self.assertEqual(self.pairs(cm={"Track K-1": 300.0}), [])                        # no length counts as none

    def test_only_between_two_control_point_switches(self):
        self.assertEqual(self.pairs(cps={"39": "Princess"}), [])                         # 37 in no control point
        self.assertEqual(self.pairs(run=(("N9", "B"), ["OS Switch 9"] + self.SEQ[1:], ("N37", "A"))), [])
        self.assertEqual(self.pairs(run=(("N39", "B"), self.SEQ[:3], ("END", "x"))), [])  # a bumper at one end

    def test_a_single_block_between_the_switches_has_no_boundary(self):
        seq = ["OS Switch 39", "Track K-1", "OS Switch 37"]
        self.assertEqual(self.pairs(run=(("N39", "B"), seq, ("N37", "A"))), [])

    def test_a_switch_off_the_milepost_count_stops(self):
        with self.assertRaisesRegex(bsm.RuleError, r"Track K-1\|Track K-2 cannot be numbered: switch 37 is not on"):
            self.pairs(self.band(on_count=("N39",)))
        with self.assertRaisesRegex(bsm.RuleError, "switch 39 is not on the milepost count"):
            self.pairs(self.band(on_count=("N37",)))


GEN = [dict(mast="Mast 2L", cp="Brick", switch="1", facing="Track Main West", protects="OS Switch 1",
            kind="two-searchlight", heads=2, dir="west", toward="1", run="1;23", names=["Main West"], edge_cm=551.9,
            cm_from_toward=0.0, edge="e9+e10", node="N1", signal_kind="planned"),
       dict(mast="Mast 67", cp="Princess", switch="", facing="Track K-2", protects="Track K-1",
            kind="one-searchlight", heads=1, dir="west", toward="39", run="39;37", names=["K-1", "K-2"], edge_cm=602.94,
            cm_from_toward=314.25, edge="e16", node="N39", signal_kind="field")]
SHSM_2L = "IF$shsm:basic:two-searchlight(IH:HART:C1:2L_Top)(IH:HART:C1:2L_Bottom)"
VIRTUAL = dict(mast="Mast 4LA", cp="Brick", switch="", facing="Track W-1", protects="", leg="",
               system_name="IF$vsm:basic:one-low($1001)", head_system_names="",
               device_system_name="IF$vsm:basic:one-low($1001)")


def device(layer, user, system, **more):
    r = dict(level="1", cp="Brick", layer=layer, user_name=user, system_name=system, jmri_name=system, node="", dcc="",
             comment="", trial_name="", notes="")
    r.update(more)
    return r


class Rows(unittest.TestCase):
    """The rows written to staging_masts.csv, staging_signals.csv and device_map_staging.csv."""

    def test_mast_rows(self):
        wired = {"Mast 67": {"Head 67": device("head", "Head 67", "IH467")}}
        self.assertEqual(bsm.mast_rows(GEN, wired), [
            dict(mast="Mast 2L", cp="Brick", switch="1", facing="Track Main West", protects="OS Switch 1", leg="",
                 system_name=SHSM_2L, device_system_name=SHSM_2L,
                 head_system_names="IH:HART:C1:2L_Top=Head 2L Top;IH:HART:C1:2L_Bottom=Head 2L Bottom"),
            dict(mast="Mast 67", cp="Princess", switch="", facing="Track K-2", protects="Track K-1", leg="",
                 system_name="IF$shsm:basic:one-searchlight(IH467)", head_system_names="IH467=Head 67",
                 device_system_name="IF$shsm:basic:one-searchlight(IH467)")])
        self.assertEqual(list(bsm.mast_rows(GEN, {})[0]), level_masts.FIELDS)

    def test_signal_rows(self):
        self.assertEqual(bsm.signal_rows(GEN), [
            dict(mast="Mast 2L", signal="2L", toward="1", run="1;23", names="Main West", edge_cm="551.9",
                 cm_from_toward="0.0", dir="west", signal_kind="planned", heads="2", schematic_edge="e9+e10",
                 schematic_toward_node="N1"),
            dict(mast="Mast 67", signal="67", toward="39", run="39;37", names="K-1;K-2", edge_cm="602.9",
                 cm_from_toward="314.2", dir="west", signal_kind="field", heads="1", schematic_edge="e16",
                 schematic_toward_node="N39")])
        self.assertEqual(list(bsm.signal_rows(GEN)[0]), list(sdm.SIGNAL_COLUMNS))

    def test_csv_text_has_lf_ends_and_quotes_only_what_needs_it(self):
        text = bsm.csv_text([dict(a="1", b="x,y"), dict(a="", b='say "hi"')], ("a", "b"))
        self.assertEqual(text, 'a,b\n1,"x,y"\n,"say ""hi"""\n')
        self.assertEqual(bsm.csv_text([], ("a", "b")), "a,b\n")

    def test_device_rows_replace_mast_and_head_rows_and_keep_the_rest_in_place(self):
        old = [device("turnout", "Switch 1", "MT100", notes="kept"),
               device("mast", "Mast 99L", "IF$shsm:basic:one-low(IH:HART:C1:99L)", notes="an old mast"),
               device("block", "Track W-1", "IB7", notes="kept too"),
               device("head", "Head 99L", "IH:HART:C1:99L", notes="an old head")]
        masts = [dict(mast="Mast 67", cp="Princess", switch="", facing="Track K-2", protects="Track K-1",
                      system_name="IF$shsm:basic:one-searchlight(IH:HART:C1:67)",
                      head_system_names="IH:HART:C1:67=Head 67"),
                 dict(mast="Mast 2L", cp="Brick", switch="1", facing="Track Main West", protects="OS Switch 1",
                      system_name=SHSM_2L,
                      head_system_names="IH:HART:C1:2L_Top=Head 2L Top;IH:HART:C1:2L_Bottom=Head 2L Bottom")]
        got = bsm.device_rows(masts, [VIRTUAL], old, {})
        self.assertEqual([list(r) for r in got], [bdm.COLUMNS] * len(got))
        # the other rows first and unchanged, then the masts by user name, then the heads by user name (plain string
        # order: Mast 2L, Mast 4LA, Mast 67)
        self.assertEqual(got[:2], [old[0], old[2]])
        self.assertEqual([(r["layer"], r["user_name"]) for r in got[2:]],
                         [("mast", "Mast 2L"), ("mast", "Mast 4LA"), ("mast", "Mast 67"), ("head", "Head 2L Bottom"),
                          ("head", "Head 2L Top"), ("head", "Head 67")])
        by = {r["user_name"]: r for r in got}
        self.assertEqual(by["Mast 2L"], device("mast", "Mast 2L", SHSM_2L, comment="Brick | Switch 1",
                                               notes="facing Track Main West into OS Switch 1"))
        self.assertEqual(by["Mast 67"]["comment"], "Princess")              # an anchor mast names no switch
        self.assertEqual(by["Mast 4LA"], device("mast", "Mast 4LA", "IF$vsm:basic:one-low($1001)", comment="Brick",
                                                notes="facing Track W-1, buffer stop"))
        self.assertEqual(by["Head 2L Top"], device("head", "Head 2L Top", "IH:HART:C1:2L_Top",
                                                   comment="Brick | Switch 1", notes="internal, not wired"))

    def test_device_rows_sort_by_plain_string_order(self):
        masts = [dict(mast=f"Mast {n}", cp="", switch="", facing="x", protects="", system_name="IF$vsm:basic:one-low($1)",
                      head_system_names="") for n in ("8LA", "24L", "2L", "36RA", "4RA")]
        got = bsm.device_rows(masts, [], [], {})
        self.assertEqual([r["user_name"] for r in got], ["Mast 24L", "Mast 2L", "Mast 36RA", "Mast 4RA", "Mast 8LA"])


class Cli(unittest.TestCase):
    """main() on temporary files (build() stubbed): --check and --show write nothing; a rule error is exit 2."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.current = self.dir / "staging_masts.csv"
        self.current.write_text("mast\nMast 2L\n", encoding="utf-8")
        self.stale = self.dir / "staging_signals.csv"
        self.stale.write_text("mast\nold\n", encoding="utf-8")
        self.missing = self.dir / "device_map_staging.csv"
        want = {self.current: "mast\nMast 2L\n", self.stale: "mast\nnew\n", self.missing: "level\n1\n"}
        gen = [dict(GEN[0]), dict(GEN[1], milepost=6.714)]
        patch = unittest.mock.patch.object(bsm, "build", lambda: (want, gen))
        patch.start()
        self.addCleanup(patch.stop)

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = bsm.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_check_names_each_stale_or_missing_file_and_writes_nothing(self):
        code, out, err = self.run_main("--check")
        self.assertEqual((code, out), (1, ""))
        self.assertEqual(err.splitlines(),
                         ["staging_signals.csv is stale: run python3 tools/schematic/build_staging_masts.py",
                          "device_map_staging.csv is stale: run python3 tools/schematic/build_staging_masts.py"])
        self.assertEqual(self.stale.read_text(encoding="utf-8"), "mast\nold\n")
        self.assertFalse(self.missing.exists())

    def test_a_run_writes_only_the_stale_files_and_then_check_passes(self):
        before = self.current.stat().st_mtime_ns
        code, out, err = self.run_main()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.splitlines(), ["wrote staging_signals.csv", "wrote device_map_staging.csv"])
        self.assertEqual(self.stale.read_text(encoding="utf-8"), "mast\nnew\n")
        self.assertEqual(self.missing.read_text(encoding="utf-8"), "level\n1\n")
        self.assertEqual(self.current.stat().st_mtime_ns, before)
        self.assertEqual(self.run_main("--check"), (0, "", ""))
        self.assertEqual(self.run_main(), (0, "", ""))

    def test_show_prints_the_masts_and_writes_nothing(self):
        code, out, _err = self.run_main("--show")
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0].split(), ["Mast", "2L", "two-searchlight", "2h", "Track", "Main", "West", "->", "OS",
                                            "Switch", "1", "switch", "1", "west"])
        self.assertTrue(lines[1].endswith("anchor     west  MP 6.714"), lines[1])
        self.assertEqual(self.stale.read_text(encoding="utf-8"), "mast\nold\n")
        self.assertFalse(self.missing.exists())

    def test_check_and_show_do_not_go_together(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            bsm.main(["--check", "--show"])

    def test_a_rule_error_is_exit_2(self):
        def stop():
            raise bsm.RuleError("the rule names a mast twice: ['Mast 2L']")
        with unittest.mock.patch.object(bsm, "build", stop):
            code, out, err = self.run_main("--check")
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(err.strip(), "build_staging_masts.py: the rule names a mast twice: ['Mast 2L']")


class WriteGuard(unittest.TestCase):
    """The guard the data checks run under: a write inside the repo fails, one outside it goes through."""

    def test_a_write_inside_the_repo_is_refused_before_it_happens(self):
        target = Path(__file__).with_name("never_written.tmp")
        self.assertTrue(in_repo(target))
        with repo_read_only():
            for write in (lambda: target.write_text("x", encoding="utf-8"), lambda: target.write_bytes(b"x"),
                          lambda: open(target, "w"), lambda: target.open("a"), target.touch, target.mkdir,
                          lambda: Path(__file__).rename(target)):
                with self.assertRaisesRegex(AssertionError, "data checks only read it"):
                    write()
            self.assertEqual(Path(__file__).read_text(encoding="utf-8")[:3], '"""')      # reading still works
        self.assertFalse(target.exists())

    def test_a_write_outside_the_repo_goes_through(self):
        with tempfile.TemporaryDirectory() as d, repo_read_only():
            self.assertFalse(in_repo(d))
            (Path(d) / "sub").mkdir()
            (Path(d) / "sub" / "a.txt").write_text("x", encoding="utf-8")
            self.assertEqual((Path(d) / "sub" / "a.txt").read_text(encoding="utf-8"), "x")


class CommittedData(RepoReadOnly, unittest.TestCase):
    """Data checks, not rule tests: the real build() over the repo's committed plan and data (built once), under
    RepoReadOnly, so a write into the repo fails the test instead of changing a file. A failure here can mean the data
    changed, not the code. These hold whatever masts the rule places; they name no mast."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.files = {p: p.read_bytes() for p in (bsm.MASTS, bsm.SIGNALS, bsm.DEVICE_MAP)}
        cls.want, cls.gen = bsm.build()

    def test_check_reports_the_committed_files_current_and_writes_nothing(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = bsm.main(["--check"])
        self.assertEqual((code, err.getvalue()), (0, ""))
        for path, data in self.files.items():
            self.assertEqual(path.read_bytes(), data, path.name)

    def test_build_gives_the_three_files(self):
        self.assertEqual(set(self.want), {bsm.MASTS, bsm.SIGNALS, bsm.DEVICE_MAP})

    def test_masts_are_in_number_then_name_order_each_named_once(self):
        names = [m["mast"] for m in self.gen]
        self.assertEqual(len(set(names)), len(names))
        self.assertEqual(names, sorted(names, key=lambda n: (int("".join(c for c in n[5:] if c.isdigit())), n)))

    def test_home_masts_stand_only_at_switches_of_an_interlocking(self):
        # the signal rule's control points are interlockings_staging.csv, not the stations the drawings group by
        stations = {s.strip(): r["cp_name"] for r in sdm.read_rows(bsm.CPS, sdm.CP_COLUMNS)
                    for s in r["switches"].split(",")}
        locks = bsm.interlockings(set(stations))
        # every interlocking switch is a station switch; how many station switches stay outside is the data's choice
        self.assertLessEqual(set(locks), set(stations))
        for m in self.gen:
            self.assertIn(m["toward"], locks, m["mast"])
            self.assertEqual(m["cp"], stations[m["toward"]], m["mast"])       # the cp column is the station

    def test_kind_follows_heads_and_running_track(self):
        for m in self.gen:
            if "milepost" in m:
                self.assertEqual((m["kind"], m["heads"], m["switch"]), ("one-searchlight", 1, ""), m["mast"])
            else:
                want = f"{'two' if m['heads'] == 2 else 'one'}-{'searchlight' if m['running'] else 'low'}"
                self.assertEqual(m["kind"], want, m["mast"])
                self.assertIn(m["heads"], (1, 2))

    def test_intermediates_come_in_pairs_odd_west_even_east(self):
        inter = [m for m in self.gen if "milepost" in m]
        self.assertEqual(len(inter) % 2, 0)
        for m in inter:
            number = int(m["mast"].removeprefix("Mast "))
            self.assertEqual(number % 2, 1 if m["dir"] == "west" else 0, m["mast"])
            self.assertLess(number, 100)

    def test_the_files_list_the_rule_masts_first_then_the_virtual_ones(self):
        rule = [m["mast"] for m in self.gen]
        virtual_masts, virtual_signals = bsm.read_virtual()
        virtual = [r["mast"] for r in virtual_masts]
        self.assertEqual([r["mast"] for r in rows_of(self.want[bsm.MASTS])], rule + virtual)
        self.assertEqual([r["mast"] for r in rows_of(self.want[bsm.SIGNALS])],
                         rule + [r["mast"] for r in virtual_signals])
        self.assertFalse(set(rule) & set(virtual))
        for r in rows_of(self.want[bsm.MASTS]):
            self.assertEqual(r["system_name"].startswith("IF$vsm:"), r["mast"] in virtual, r["mast"])

    def test_the_device_map_keeps_other_rows_then_masts_then_heads_by_name(self):
        old = sdm.read_rows(bsm.DEVICE_MAP, bdm.COLUMNS)
        new = rows_of(self.want[bsm.DEVICE_MAP])
        other = [r for r in old if r["layer"] not in ("mast", "head")]
        self.assertEqual(new[:len(other)], other)
        masts = [r["user_name"] for r in new if r["layer"] == "mast"]
        heads = [r["user_name"] for r in new if r["layer"] == "head"]
        self.assertEqual([r["layer"] for r in new[len(other):]], ["mast"] * len(masts) + ["head"] * len(heads))
        self.assertEqual(masts, sorted(masts))
        self.assertEqual(heads, sorted(heads))
        self.assertEqual(sorted(masts), sorted(r["mast"] for r in rows_of(self.want[bsm.MASTS])))


if __name__ == "__main__":
    unittest.main()
