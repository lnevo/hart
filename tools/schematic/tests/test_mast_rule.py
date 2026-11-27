"""mast_rule.py's home mast rule on small hand-written inputs: where a leg gets a mast (leg_mast), how it is named and
numbered (home_mast, letter_masts), which masts stay (signalled) and the error paths. masts() over the committed plan
is tested in tools/audit/tests/test_build_device_map.py."""
from __future__ import annotations

import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import publish_draft  # noqa: E402,F401  puts tools/hartlib/src on the path for mast_rule's hartlib import
import mast_rule as mr  # noqa: E402


def track(name: str, ends, legs, *, cm: float = 200.0, loop: bool = False, main: bool = False) -> mr.Track:
    """A track entry as mast_rule.tracks gives it, on band 0."""
    return mr.Track(level=2, ends=ends, legs=legs, band=0, plan_ends=("1A", "3A"), cm=cm, loop=loop, main=main,
                    row=0, strands=[f"s-{name}"], trial=[f"Track {name}"], name=name)


SWITCH = {"kind": "switch", "label": "101"}
RULE = mr.MastInputs(cp_of={"101": "CP 101", "103": "CP 103"}, corner_blocks={}, running_extra=frozenset(),
                     spurs=frozenset(), split=frozenset())


def spot(leg: str = "A", eastward: bool = True) -> mr.LegSpot:
    return mr.LegSpot(level=2, band=0, node="n101", leg=leg, strand="s1", row=3, eastward=eastward)


class HomeMast(unittest.TestCase):
    def test_number_letter_and_kind(self):
        m = mr.home_mast(spot(), cp="CP 101", switch="101", protects="", heads=2, track="Track 101-103", half=0,
                         running=True)
        self.assertEqual((m["number"], m["letter"], m["dir"], m["kind"], m["row"], m["node"], m["leg"]),
                         (102, "L", "west", "two-searchlight", 3, "n101", "A"))
        east = mr.home_mast(spot("B", eastward=False), cp="CP 101", switch="101", protects="", heads=1,
                            track="Track 101-103", half=0, running=False)
        self.assertEqual((east["letter"], east["dir"], east["kind"]), ("R", "east", "one-low"))
        run = mr.home_mast(spot("B"), cp="", switch="101", protects="", heads=1, track="T", half=0, running=True)
        self.assertEqual(run["kind"], "one-searchlight")


class LegMast(unittest.TestCase):
    def mast(self, t: mr.Track, leg: str = "A", rule: mr.MastInputs = RULE, node=SWITCH):
        far = t["ends"][1]
        return mr.leg_mast(spot(leg), node, (t, far), rule)

    def test_a_track_from_outside_the_control_point_gets_a_mast(self):
        t = track("Track 101-105", (("sw", "101"), ("sw", "105")), [("n101", "A"), ("n105", "A")], main=True)
        m, order = self.mast(t)
        self.assertEqual((m["cp"], m["heads"], m["kind"], m["track"], m["running"]),
                         ("CP 101", 2, "two-searchlight", "Track 101-105", True))
        self.assertEqual(order, mr.letter_order(t, 0, "A"))

    def test_a_short_track_inside_one_control_point_or_to_a_bumper_gets_none(self):
        inside = track("Track 101-103", (("sw", "101"), ("sw", "101")), [("n101", "B"), ("n103", "B")], cm=40.0)
        rule = RULE._replace(cp_of={"101": "CP 101"})
        self.assertIsNone(self.mast(inside, "B", rule))
        bumper = track("Track 101 Spur", (("sw", "101"), ("bumper", None)), [("n101", "C"), ("e", "x")], cm=40.0)
        self.assertIsNone(self.mast(bumper, "C"))

    def test_a_switch_in_no_control_point_gets_a_mast_only_for_a_signalled_spur(self):
        spur = track("Track 241 Spur", (("sw", "101"), ("bumper", None)), [("n101", "C"), ("e", "x")])
        none = RULE._replace(cp_of={})
        self.assertIsNone(self.mast(spur, "C", none))
        m, _order = self.mast(spur, "C", none._replace(spurs=frozenset({"Track 241 Spur"})))
        self.assertEqual((m["cp"], m["heads"], m["kind"], m["running"]), ("", 1, "one-low", False))

    def test_a_loop_names_its_half_and_must_leave_from_a_half_leg(self):
        loop = track("Track 101 Loop", (("sw", "101"), ("sw", "101")), [("n101", "B"), ("n101", "C")], loop=True)
        m, _order = self.mast(loop, "C")
        self.assertEqual((m["track"], m["half"]), ("Track 101 Loop 2", 2))
        with self.assertRaisesRegex(mr.MapError, "leaves from leg A; a loop's halves leave from legs B and C"):
            self.mast(loop, "A")

    def test_a_split_track_names_the_half_at_this_end(self):
        t = track("Track 101-105", (("sw", "101"), ("sw", "105")), [("n101", "A"), ("n105", "A")], main=True)
        m, _order = self.mast(t, rule=RULE._replace(split=frozenset({"Track 101-105"})))
        self.assertEqual(m["track"], "Track 101-105 1")

    def test_a_double_crossover_mast_protects_its_corner(self):
        t = track("Track 101-105", (("sw", "101"), ("sw", "105")), [("n101", "B"), ("n105", "A")], main=True)
        rule = RULE._replace(corner_blocks={"101": {"B": "OS 101 corner B"}})
        m, _order = self.mast(t, "B", rule, {"kind": "dx", "label": "101"})
        self.assertEqual((m["protects"], m["heads"]), ("OS 101 corner B", 2))


class Letters(unittest.TestCase):
    def home(self, node: str, leg: str) -> mr.HomeMast:
        return mr.home_mast(mr.LegSpot(2, 0, node, leg, "s", 0, True), cp="CP", switch="101", protects="", heads=1,
                            track="T", half=0, running=True)

    def test_two_masts_of_one_number_and_way_are_a_and_b_in_plan_order(self):
        a, b = self.home("n", "C"), self.home("n", "B")
        order = {(0, "n", "C"): (1,), (0, "n", "B"): (2,)}
        mr.letter_masts([a, b], order)
        self.assertEqual((a["name"], b["name"]), ("102LA", "102LB"))
        single = self.home("m", "A")
        mr.letter_masts([single], {(0, "m", "A"): ()})
        self.assertEqual(single["name"], "102L")

    def test_three_masts_of_one_number_and_way_stop(self):
        ms = [self.home("n", p) for p in "ABC"]
        with self.assertRaisesRegex(mr.MapError, "switch 101: 3 masts for direction L"):
            mr.letter_masts(ms, {(0, "n", p): () for p in "ABC"})

    def test_two_masts_on_one_leg_stop(self):
        order: dict = {}
        mr.put_order(order, (0, "n", "A"), (1,))
        with self.assertRaises(mr.MastOrderError):
            mr.put_order(order, (0, "n", "A"), (2,))


class Signalled(unittest.TestCase):
    def test_a_mast_kept_only_by_a_dropped_mast_is_dropped_too(self):
        """x reaches only y, y reaches nothing: both go, again until none is left out."""
        x = Letters.home(Letters(), "x", "A")
        y = Letters.home(Letters(), "y", "A")
        z = Letters.home(Letters(), "z", "A")

        def reaches(_bands, _bi, node, _leg, posts, _joined):
            return node == "z" or (node == "x" and ("y", "A") in posts[0])
        with unittest.mock.patch.object(mr, "reaches_signal", reaches):
            self.assertEqual(mr.signalled([], [x, y, z], {}), [z])


class HelixTracks(unittest.TestCase):
    def test_a_bad_helix_file_is_a_map_error(self):
        with self.assertRaises(mr.MapError):
            mr.read_helix_tracks(Path("/nonexistent/plan_overrides.json"))

    def test_the_helix_map_must_match_the_helix_tracks(self):
        helix = {"H-1": mr.HelixEntry(block="Track H-1", staging_switch="9", level_switch="131A", shown="Helix")}
        with self.assertRaisesRegex(mr.MapError, "the helix tracks are"):
            mr.helix_blocks({"helix": {"131": "H-2"}}, helix)
        self.assertEqual(mr.helix_blocks({"helix": {"131": "H-1"}}, helix), {"H1": "Track H-1"})


if __name__ == "__main__":
    unittest.main()
