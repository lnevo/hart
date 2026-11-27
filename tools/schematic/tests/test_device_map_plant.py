"""device_map_plant.py: the main and upper switch, OS block, part and track rows, run over a small MapBuild with a
stand-in node allocator (no plugin, no data file): each row maker, the wiring a device takes, and every stop."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parents[2] / "tools/hartlib/src")]
import device_map_plant as plant  # noqa: E402
import device_map_records as rec  # noqa: E402
from device_map_inputs import UID, Places  # noqa: E402
from map_error import MapError  # noqa: E402

NODE = 7        # the node the stand-in allocator picks


class Nodes:
    """A stand-in for device_map_nodes.Nodes: every pick is NODE, every take the next index of its kind there."""

    def __init__(self, frozen=None, pinned=None):
        self.frozen = dict(frozen or {})
        self.pinned = dict(pinned or {})
        self.taken = []

    def take_frozen(self, kind, device):
        return self.frozen.get((kind, device))

    def pick(self, level, area, what, n=1, prefer=()):
        return NODE

    def take(self, node, what):
        k = self.taken.count(what)
        self.taken.append(what)
        return k, node * 100 + UID[what] + k

    def detector(self, block, level, area, prefer, pin_level):
        return (prefer, 2, prefer * 100 + 2)

    def take_pinned(self, block):
        return self.pinned.pop(block, None)


def state(**over) -> rec.MapBuild:
    """A MapBuild with empty rows and tables, a stand-in allocator and `over` on top."""
    blank = rec.MapBuild(*[None] * len(rec.MapBuild._fields))
    start = dict(rows=[], block_ids={}, home={}, area_of={}, by_level={}, dcc={}, corner_blocks={}, trials={},
                 track_ids={}, os_pin_level={}, cp_of={}, split_names=set(), helix={}, nodes=Nodes(),
                 places=Places(of={}, order={}, level={}, tracks={}), lay=SimpleNamespace(parts={}))
    return blank._replace(**{**start, **over})


def track(name, ends, **over):
    return dict(dict(name=name, ends=ends, level=2, main=True, loop=False, cm=120.0), **over)


GROUP = rec.Group(2, "North", "CP 201")
LOCAL = rec.Group(2, "North", "")


class Rows(unittest.TestCase):
    def test_add_makes_a_whole_row_and_keeps_a_blocks_id(self):
        st = state()
        plant.add(st, 2, "CP 201", "block", "OS Switch 201", role="os", ident="os:201", trial="t", notes="n")
        plant.add(st, 2, "CP 201", "mast", "Mast 202L", role="home", ident="m", facing="Track 1-3", dir="west")
        self.assertEqual(set(st.rows[0]), set(rec.DeviceMapRow.__annotations__))
        self.assertEqual((st.rows[0]["id"], st.rows[0]["trial_name"], st.rows[0]["notes"]), ("os:201", "t", "n"))
        self.assertEqual((st.rows[1]["facing"], st.rows[1]["dir"], st.rows[1]["switch"]), ("Track 1-3", "west", ""))
        self.assertEqual(st.block_ids, {("2", "OS Switch 201"): "os:201"})

    def test_add_stops_on_a_column_that_is_no_fact(self):
        with self.assertRaisesRegex(MapError, "unknown fact columns"):
            plant.add(state(), 2, "", "block", "Track 1-3", role="track", ident="b", colour="red")

    def test_an_occupancy_row_states_its_detector(self):
        st = state(block_ids={("2", "Track 1-3"): "block:x"})
        plant.occupancy(st, 2, "", "Track 1-3", role="track", notes=plant.NO_DETECTOR)
        plant.occupancy(st, 2, "", "Track 1-3", role="track", notes=plant.NOT_WIRED)
        plant.detected(st, 2, "", "Track 1-3", (4, 0, 400), role="track")
        self.assertEqual([r["detector"] for r in st.rows], ["none", "not_wired", "planned"])
        last = st.rows[-1]
        self.assertEqual((last["user_name"], last["jmri_name"], last["blocks"], last["id"]),
                         ("BS 1-3", "IS:HART:C3:B:1-3", "Track 1-3", "det:block:x"))
        self.assertEqual((last["system_name"], last["node"], last["comment"]), ("M2S400", 4, "Node: 4 Block: 1"))

    def test_an_occupancy_row_with_no_input_and_no_reason_stops(self):
        st = state(block_ids={("2", "Track 1-3"): "block:x"})
        with self.assertRaisesRegex(MapError, "occupancy of Track 1-3: no detector and no reason why"):
            plant.occupancy(st, 2, "", "Track 1-3", role="track", notes="later")

    def test_a_block_name_with_no_clean_key_stops(self):
        with self.assertRaises(MapError):
            plant.block_sensor("Track 1/3")

    def test_a_block_on_no_strand_has_no_trial_name_and_no_id(self):
        st = state(trials={"Track 1-3": "e1"}, track_ids={"Track 1-3": "block:e1"})
        self.assertEqual((plant.trial_of(st, "Track 1-3"), plant.track_id(st, "Track 1-3")), ("e1", "block:e1"))
        for read in (plant.trial_of, plant.track_id):
            with self.subTest(read=read.__name__), self.assertRaisesRegex(MapError, "Track 5-7: the block layer"):
                read(st, "Track 5-7")


class Switches(unittest.TestCase):
    FROZEN = SimpleNamespace(node=4, index=1, wiring_text="Node: 4 Turnout: 1 | OU: 1 Ports: 3,4", address="M2S467")

    def test_a_frozen_turnout_keeps_its_wiring(self):
        st = state(nodes=Nodes(frozen={("turnout", "Switch 201"): self.FROZEN}))
        self.assertEqual(plant.turnout_wiring(st, "201", None),
                         plant.Wired(f"M2T{400 + UID['turnout'] + 1}", 4, self.FROZEN.wiring_text))

    def test_a_loose_turnout_takes_the_next_one_of_its_node(self):
        self.assertEqual(plant.turnout_wiring(state(), "201", NODE),
                         plant.Wired(f"M2T{NODE * 100 + UID['turnout']}", NODE, f"Node: {NODE} Turnout: 0"))

    def test_a_switch_with_no_node_and_no_frozen_turnout_stops(self):
        with self.assertRaisesRegex(MapError, "Switch 201: not frozen in wiring.csv, and no node was picked"):
            plant.switch_rows(state(), GROUP, "201", None)

    def test_feedback_is_frozen_or_the_next_sensor_input(self):
        st = state(nodes=Nodes(frozen={("fb", "FB Switch 201 N"): self.FROZEN}))
        self.assertEqual(plant.feedback_wiring(st, GROUP, "201", "N", 4),
                         plant.Wired("M2S467", 4, self.FROZEN.wiring_text))
        self.assertEqual(plant.feedback_wiring(st, GROUP, "201", "R", 4),
                         plant.Wired(f"M2S{NODE * 100 + UID['sensor']}", NODE, f"Node: {NODE} Sensor: 0"))

    def test_a_switch_gives_four_rows_and_its_home_node(self):
        st = state(by_level={2: {"201", "203"}}, dcc={"201": 120})
        plant.switch_rows(st, GROUP, "201", NODE, "a note")
        self.assertEqual([(r["layer"], r["user_name"], r["role"]) for r in st.rows],
                         [("turnout", "Switch 201", "turnout"), ("turnout", "DCC Switch 201", "lcc_alias"),
                          ("fb", "FB Switch 201 N", "fb"), ("fb", "FB Switch 201 R", "fb")])
        self.assertEqual((st.rows[0]["jmri_name"], st.rows[0]["dcc"], st.rows[0]["notes"], st.rows[0]["trial_name"]),
                         (plant.VIRTUAL_TURNOUT + "201", 120, "a note", "Switch 201"))
        self.assertEqual((st.home, st.area_of), ({"201": NODE}, {"201": (2, "North")}))

    def test_control_points_come_before_local_switches_and_turnouts_before_os_blocks(self):
        cp = SimpleNamespace(level=2, area="North", name="CP 201", switches=("201",))
        local = SimpleNamespace(level=2, area="Yard", notes="yard lead")
        st = state(by_level={2: {"201", "9"}}, dcc={"201": 120, "9": 121}, loc={"9": local})
        plant.switch_and_os_rows(st, [cp])
        self.assertEqual([r["user_name"] for r in st.rows if r["layer"] in ("turnout", "block")],
                         ["Switch 201", "DCC Switch 201", "Switch 9", "DCC Switch 9", "OS Switch 201", "OS Switch 9"])
        by_name = {r["user_name"]: r for r in st.rows}
        self.assertEqual(by_name["Switch 9"]["notes"], "no control point: yard lead")
        self.assertEqual((by_name[plant.occupancy_user("OS Switch 201")]["detector"], by_name[plant.occupancy_user("OS Switch 9")]["detector"]), ("planned", "none"))
        self.assertEqual((by_name["OS Switch 201"]["comment"], by_name["OS Switch 9"]["comment"]), ("CP 201", "Yard"))


class OsBlocks(unittest.TestCase):
    def test_an_os_block_off_the_main_line_has_no_detector(self):
        st = state()
        plant.os_rows(st, LOCAL, "9", detect=False)
        block, occ = st.rows
        self.assertEqual((block["user_name"], block["comment"], block["notes"], block["id"]),
                         ("OS Switch 9", "North", plant.OFF_MAIN, "os:9"))
        self.assertEqual((occ["detector"], occ["notes"], occ["system_name"]), ("none", plant.NO_DETECTOR, ""))

    def test_an_os_block_of_a_control_point_takes_a_detector(self):
        st = state(home={"201": 4})
        plant.os_rows(st, GROUP, "201")
        block, occ = st.rows
        self.assertEqual((block["node"], block["comment"], block["trial_name"]), (4, "CP 201", "OS Switch 201"))
        self.assertEqual((occ["system_name"], occ["comment"], occ["role"]), ("M2S402", "Node: 4 Block: 3", "os"))

    def test_a_double_crossover_is_a_block_per_corner_corner_a_detected(self):
        corners = {"225": {"B": "OS Switch 225b", "A": "OS Switch 225a"}}
        st = state(home={"225": 4}, corner_blocks=corners)
        plant.os_rows(st, GROUP, "225")
        got = {r["user_name"]: r for r in st.rows}
        self.assertEqual([r["user_name"] for r in st.rows if r["layer"] == "block"],
                         ["OS Switch 225a", "OS Switch 225b"])
        self.assertEqual((got["OS Switch 225a"]["notes"], got["OS Switch 225a"]["role"], got["OS Switch 225a"]["id"]),
                         ("corner A of the double crossover", plant.CORNER, "os:225:A"))
        self.assertEqual((got[plant.occupancy_user("OS Switch 225a")]["detector"], got[plant.occupancy_user("OS Switch 225b")]["detector"]), ("planned", "not_wired"))
        self.assertEqual(got[plant.occupancy_user("OS Switch 225b")]["notes"], plant.NOT_WIRED)

    def test_a_double_crossover_off_the_main_line_has_no_detectors(self):
        st = state(corner_blocks={"225": {"A": "OS Switch 225a"}})
        plant.os_rows(st, LOCAL, "225", detect=False)
        self.assertEqual(st.rows[0]["notes"], "corner A of the double crossover, " + plant.OFF_MAIN)
        self.assertEqual(st.rows[1]["detector"], "none")


class Tracks(unittest.TestCase):
    def lined(self, t, **over) -> rec.MapBuild:
        """A MapBuild in which track `t` (and its halves) has a trial name and both its switches a node."""
        names = [t["name"], f"{t['name']} 1", f"{t['name']} 2"]
        start = dict(found=[t], trials={n: "e1" for n in names}, track_ids={n: f"block:{n}" for n in names},
                     area_of={"201": (2, "North"), "203": (2, "North")}, home={"201": 4, "203": 5},
                     cp_of={"201": "CP 201", "203": "CP 203"})
        return state(**{**start, **over})

    def test_the_note_gives_the_length_and_which_half(self):
        t = track("Track 201-203", [("sw", "201"), ("sw", "203")])
        self.assertEqual(plant.track_note(t, None, False), "120.0 cm")
        self.assertEqual(plant.track_note(dict(t, main=False), None, False), "120.0 cm " + plant.OFF_MAIN)
        self.assertEqual(plant.track_note(t, 2, False), "60.0 cm, half of the balloon loop from leg C")
        self.assertEqual(plant.track_note(t, 1, True),
                         f"60.0 cm, half 1 of the split track ({plant.block_override_rows.OVERRIDES_NAME})")

    def test_a_main_track_takes_the_next_block_input(self):
        st = self.lined(track("Track 201-203", [("sw", "201"), ("sw", "203")]))
        plant.track_rows(st)
        block, occ = st.rows
        self.assertEqual((block["user_name"], block["comment"], block["role"], block["id"]),
                         ("Track 201-203", "CP 201 / CP 203", "track", "block:Track 201-203"))
        self.assertEqual((occ["system_name"], occ["comment"]),
                         (f"M2S{NODE * 100 + UID['block']}", f"Node: {NODE} Block: 1"))

    def test_the_owners_pin_wins(self):
        t = track("Track 201-203", [("sw", "201"), ("sw", "203")])
        st = self.lined(t, nodes=Nodes(pinned={"Track 201-203": (9, 3, 903)}))
        plant.track_rows(st)
        self.assertEqual((st.rows[1]["system_name"], st.rows[1]["node"]), ("M2S903", 9))

    def test_a_balloon_loop_is_two_blocks_the_second_not_wired(self):
        t = track("Track 201 Loop", [("sw", "201"), ("sw", "201")], loop=True)
        st = self.lined(t)
        plant.track_rows(st)
        occ = [r for r in st.rows if r["layer"] == "occupancy"]
        self.assertEqual([r["blocks"] for r in occ], ["Track 201 Loop 1", "Track 201 Loop 2"])
        self.assertEqual([r["detector"] for r in occ], ["planned", "not_wired"])
        self.assertEqual({r["role"] for r in st.rows}, {"loop_half"})

    def test_a_track_off_the_main_line_has_no_detector_and_a_pin_there_stops(self):
        t = track("Track 201 Spur", [("sw", "201"), ("bumper", None)], main=False)
        st = self.lined(t)
        plant.track_rows(st)
        self.assertEqual((st.rows[0]["role"], st.rows[1]["detector"]), ("spur", "none"))
        pinned = self.lined(t, nodes=Nodes(pinned={"Track 201 Spur": (9, 3, 903)}))
        with self.assertRaisesRegex(MapError, "wiring.csv pins a detector for Track 201 Spur, which the rule gives none"):
            plant.track_rows(pinned)

    def test_a_track_to_a_switch_of_neither_level_stops(self):
        st = self.lined(track("Track 201-57", [("sw", "201"), ("sw", "57")]))
        with self.assertRaisesRegex(MapError, "Track 201-57 ends at switch 57, which is on neither"):
            plant.track_rows(st)

    def test_a_part_gets_no_block_row_of_its_own(self):
        t = track("Track 201-203", [("sw", "201"), ("sw", "203")])
        st = self.lined(t, lay=SimpleNamespace(parts={"Track 201-203": {}}))
        plant.track_rows(st)
        self.assertEqual(st.rows, [])

    def test_a_track_detector_prefers_its_own_levels_switch(self):
        st = state(area_of={"131": (3, "Upper"), "201": (2, "North")}, home={"131": 8, "201": 4})
        sws = ["131", "201"]
        self.assertEqual(plant.track_detector(st, 2, sws), (NODE, 0, NODE * 100 + UID["block"]))
        self.assertEqual(sws, ["201", "131"])


class Parts(unittest.TestCase):
    def part(self, name="Track 201-203", part_of="OS Switch 201"):
        return {"track": {"name": name, "ends": [("sw", "201"), ("sw", "203")]}, "part_of": part_of, "level": 2,
                "why": "a link", "cm": 30.0}

    def test_a_piece_at_one_end_of_a_track_stops(self):
        st = state(lay=SimpleNamespace(parts={"Track 201-203 west": self.part()}))
        with self.assertRaisesRegex(MapError, "Track 201-203 west: a piece at one end of a main or upper track"):
            plant.part_rows(st)

    def test_a_part_of_no_main_or_upper_os_block_stops(self):
        for part_of in ("OS Switch 57", "Track 1-3"):
            st = state(lay=SimpleNamespace(parts={"Track 201-203": self.part(part_of=part_of)}), switches={})
            with self.subTest(part_of=part_of), self.assertRaisesRegex(MapError, f"is part of {part_of}, the OS block"):
                plant.part_rows(st)


class Wiring(unittest.TestCase):
    def row(self, layer, user, comment="", **over):
        base = dict(level=2, cp="CP 201", layer=layer, id="x", user_name=user, system_name="M2S1", node=4,
                    comment=comment, role=layer, blocks="")
        return {**base, **over}

    def test_ports_follow_the_board_layout(self):
        rows = [self.row("turnout", "Switch 201", "Node: 4 Turnout: 5"), self.row("fb", "FB Switch 201 N", "Node: 4 Sensor: 9"),
                self.row("occupancy", "BS 1-3", "Node: 4 Block: 1"), self.row("mast", "Mast 202L", "CP 201 | Switch 201")]
        plant.assign_ports(rows)
        self.assertEqual([r["comment"] for r in rows],
                         ["Node: 4 Turnout: 5 | OU: 2 Ports: 3,4", "Node: 4 Sensor: 9 | IN: 2 Ports: 2",
                          "Node: 4 Block: 1", "CP 201 | Switch 201"])

    def test_a_frozen_control_point_takes_no_new_device(self):
        fb = self.row("fb", "FB Switch 201 N")
        occ = self.row("occupancy", "BS OS201", blocks="OS Switch 201")
        plant.check_frozen_cps([fb, occ], frozenset({"CP 201"}), {("fb", "FB Switch 201 N")}, {"OS Switch 201"})
        plant.check_frozen_cps([fb, occ], frozenset({"CP 999"}), set(), set())
        plant.check_frozen_cps([dict(fb, node="")], frozenset({"CP 201"}), set(), set())
        with self.assertRaisesRegex(MapError, r"control point\(s\) CP 201 are frozen, but the rule proposes "
                                              "fb FB Switch 201 N, occupancy of OS Switch 201"):
            plant.check_frozen_cps([fb, occ], frozenset({"CP 201"}), set(), set())


if __name__ == "__main__":
    unittest.main()
