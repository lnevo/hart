"""A frozen main or upper control point: freeze_wiring.py copies the rule's wiring into
wiring.csv, and build_device_map.py then gives those devices the same values and hands their node numbers and pins
to nothing else (Nodes.freeze, read_pins)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE.parent), str(ROOT / "tools/hartlib/src"), str(ROOT / "tools/wiring")]
import build_device_map as bdm  # noqa: E402
import freeze_wiring as fw  # noqa: E402
from unittest import mock  # noqa: E402

from hartlib import railroad, wiring  # noqa: E402

HEAD = ",".join(wiring.COLUMNS) + "\n"


# wiring.csv keys a device by its ID; the test's own devices, which the device master does not
# have, are named here beside the repo's name store
TEST_NAMES = {("2", "switch:9"): "Switch 9", ("2", "switch:999"): "Switch 999",
              ("2", "mast:1:A:west:single"): "Head 1L", ("2", "mast:9:A:west:single"): "Head 10L"}


def names():
    return {**wiring.names_beside(wiring.PATH), **TEST_NAMES}


def wires(text: str) -> list:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "wiring.csv"
        p.write_text(HEAD + text, encoding="utf-8")
        return wiring.read(p, names())


class TheNodes(unittest.TestCase):
    """Nodes.freeze holds a frozen device's number and pins; the rule gives the rest around them."""

    def nodes(self):
        return bdm.Nodes([railroad.LcosNode(2, 2, "North", 42), railroad.LcosNode(3, 2, "North", 52)])

    def test_a_frozen_turnout_keeps_its_number_and_the_rule_takes_the_next(self):
        nodes = self.nodes()
        nodes.freeze(wires('2,turnout,switch:123,,,,,,42,0,OU1,"1,2",wired,\n'))
        self.assertEqual(nodes.take(42, "turnout"), (1, 4209))
        self.assertEqual(nodes.take_frozen("turnout", "Switch 123").index, 0)
        self.assertIsNone(nodes.take_frozen("turnout", "Switch 123"))            # once

    def test_a_head_goes_round_frozen_pins(self):
        nodes = self.nodes()
        nodes.taken[(42, "turnout")] = {0, 1}                                   # one 12V board: OU1
        nodes.freeze(wires('2,head,mast:123:B:west:top,,,,,,42,0,OU2,"1,2,3",wired,\n'))
        self.assertEqual(nodes.place_mast(42, 1), [(1, 4233, 2, 4)])            # OU2-4..6, not on 1..3
        self.assertEqual(nodes.place_mast(42, 1), [(2, 4234, 3, 1)])            # OU2-7, 8 too few: OU3
        nodes.used[42]["block"] = 1
        self.assertNotIn(8, nodes._free(42, 2))                                 # the calibration relay's pin

    def test_a_frozen_turnout_board_is_never_a_heads(self):
        """Switch 123 frozen on Turnout 7 (OU2): OU2 is a 12V board, so the rule's heads go on OU3."""
        nodes = self.nodes()
        nodes.freeze(wires('2,turnout,switch:123,,,,,,42,7,OU2,"7,8",wired,\n'))
        self.assertEqual(nodes.n12(42), 2)
        self.assertEqual(nodes.place_mast(42, 2)[0][2], 3)

    def test_the_rules_turnouts_go_round_a_frozen_heads_board(self):
        """A head frozen on OU2: the rule's turnouts take OU1 (Turnout 0 to 3) and not OU2 (4 to 7, LCOS's last),
        so a fifth turnout on the node stops, naming the frozen board."""
        nodes = self.nodes()
        nodes.freeze(wires('2,head,mast:1:A:west:single,,,,,,42,0,OU2,"1,2,3",wired,\n'))
        self.assertEqual([nodes.take(42, "turnout")[0] for _ in range(4)], [0, 1, 2, 3])
        nodes.check_boards()                                                    # OU1 turnouts, OU2 the head
        with self.assertRaisesRegex(bdm.MapError, r"node 42: no turnout left \(frozen heads in wiring.csv hold "
                                                  r"boards \[2\]\)"):
            nodes.take(42, "turnout")

    def test_a_frozen_head_on_a_turnout_board_or_the_calibration_pin_stops(self):
        nodes = self.nodes()
        nodes.freeze(wires('2,turnout,switch:123,,,,,,42,0,OU1,"1,2",wired,\n'
                           '2,head,mast:1:A:west:single,,,,,,42,0,OU1,"3,4,5",wired,\n'))
        with self.assertRaisesRegex(bdm.MapError, "node 42: heads on OU1, a 12V board a turnout is on"):
            nodes.check_boards()
        nodes = self.nodes()
        nodes.freeze(wires('2,turnout,switch:123,,,,,,42,0,OU1,"1,2",wired,\n'
                           '2,head,mast:1:A:west:single,,,,,,42,0,OU2,"6,7,8",wired,\n'))
        nodes.used[42]["block"] = 1
        with self.assertRaisesRegex(bdm.MapError, "OU2-8, the calibration relay's pin"):
            nodes.check_boards()

    def test_a_frozen_head_across_two_boards_holds_both(self):
        nodes = self.nodes()
        nodes.freeze(wires('2,head,mast:1:A:west:single,,,,,,42,0,OU2,"7,8,OU3-1",wired,\n'))
        self.assertEqual((nodes.boards[42][2], nodes.boards[42][3]), ({7, 8}, {1}))

    def test_a_frozen_device_on_a_node_the_rule_does_not_hold_stops(self):
        with self.assertRaisesRegex(bdm.MapError, "Switch 9 is on node 13, which lcos_nodes.csv does not list"):
            self.nodes().freeze(wires('2,turnout,switch:9,,,,,,13,0,OU1,"1,2",wired,\n'))

    def test_what_a_node_gives_out_is_read_by_field(self):
        nodes = self.nodes()
        slot = nodes.take(42, "sensor")
        self.assertEqual((slot.slot, slot.packed), (0, 4267))
        (top, bottom) = nodes.place_mast(42, 2)
        self.assertEqual((top.signal, top.packed, top.board, top.pin), (0, 4232, 1, 1))
        self.assertEqual((bottom.signal, bottom.board, bottom.pin), (1, 1, 4))
        nodes.pin({"Track A": (52, 3)})
        got = nodes.detector("Track A", 2, "North", 42, {})
        self.assertEqual((got.node, got.slot, got.packed), (52, 3, 5203))
        free = nodes.detector("Track B", 2, "North", 42, {})
        self.assertEqual((free.node, free.slot, free.packed), (42, 0, 4200))

    def test_a_mast_placed_on_a_node_with_no_board_run_stops_by_name(self):
        nodes = self.nodes()
        for _ in range(8):                      # two heads a board: the node's four OU boards are full
            nodes.place_mast(42, 1)
        with self.assertRaisesRegex(bdm.MapError, "node 42: no 5V board run for a 1-head mast"):
            nodes.place_mast(42, 1)
        self.assertEqual(nodes.pick_mast(2, "North", 1), 52)     # pick_mast, asked first, passes the full node

    def test_a_frozen_row_with_no_lcos_number_stops_by_name(self):
        (wire,) = wires('2,turnout,switch:123,,,,,,42,0,OU1,"1,2",wired,\n')
        with self.assertRaisesRegex(bdm.MapError, "Switch 123 has no LCOS number to freeze"):
            self.nodes().freeze([wire._replace(index=None)])

    def test_a_frozen_row_the_map_does_not_use_stops(self):
        nodes = self.nodes()
        nodes.freeze(wires('2,turnout,switch:999,,,,,,42,0,OU1,"1,2",wired,\n'))
        with self.assertRaisesRegex(bdm.MapError, "frozen rows for devices the device map does not give: "
                                                  r"\['turnout Switch 999'\]"):
            nodes.check_frozen()


class TheBuild(unittest.TestCase):
    """build() over the committed inputs with frozen rows: the frozen devices keep their values."""

    @classmethod
    def setUpClass(cls):
        import build_layout_le as bl
        try:
            cls.solved = bdm.solve()
        except bl.BuildError as exc:
            if os.environ.get("SCHEMATIC_REQUIRED") == "1":
                raise
            raise unittest.SkipTest(str(exc))
        cls.rr = bdm.railroad.Railroad(bdm.sources(), upto="inputs")

    def build(self, frozen, pins=None):
        bands, joined, runs, corners = self.solved
        rr = self.rr
        _cp, rows, _parts = bdm.build(bands, joined, runs, bdm.MapInputs.of(rr), corners, frozen=frozen, pins=pins)
        return {(r["layer"], r["user_name"]): r for r in rows}

    def freeze(self, cp, today="2026-11-21"):
        """wiring.csv as freezing `cp` writes it, read back: (the file, its rows' device wires, its detector pins)."""
        helix = {h["block"] for h in bdm.read_helix_tracks().values()}
        rows = fw.freeze_rows(cp, fw.device_rows(), fw.track_keys(), helix, today)
        text, _added, _turned = fw.merge(HEAD, rows)
        p = Path(tempfile.mkdtemp()) / "wiring.csv"
        p.write_text(text, encoding="utf-8")
        pins = bdm.read_pins() | bdm.read_pins(p)            # the committed file's pins, the frozen ones over them
        return p, bdm.frozen_wires(p), pins

    def test_frozen_where_the_rule_would_not_put_it(self):
        """Switch 123 frozen on node 42's Turnout 7 (OU2-7, 8) and Mast 124LA on OU4: the build keeps both, and no
        other device takes those numbers or pins."""
        got = self.build(wires('2,turnout,switch:123,,,,,,42,7,OU2,"7,8",wired,\n'
                               '2,head,mast:123:B:west:top,,,,,,42,8,OU4,"1,2,3",wired,\n'
                               '2,head,mast:123:B:west:bottom,,,,,,42,9,OU4,"4,5,6",wired,\n'))
        t = got[("turnout", "Switch 123")]
        self.assertEqual((t["system_name"], str(t["node"]), t["comment"]),
                         ("M2T4215", "42", "Node: 42 Turnout: 7 | OU: 2 Ports: 7,8"))
        self.assertEqual(got[("turnout", "DCC Switch 123")]["comment"], t["comment"])
        top = got[("head", "Head 124LA Top")]
        self.assertEqual((top["system_name"], top["comment"]), ("IH4240", "Node: 42 Signal: 8 | OU: 4 Ports: 1,2,3"))
        self.assertIn("(IH4240)(IH4241)", got[("mast", "Mast 124LA")]["system_name"])
        on42 = [r for r in got.values() if str(r["node"]) == "42" and r["user_name"] not in
                ("Switch 123", "DCC Switch 123", "Head 124LA Top", "Head 124LA Bottom")]
        self.assertNotIn("Node: 42 Turnout: 7", " ".join(r["comment"] for r in on42))
        self.assertFalse([r for r in on42 if "OU: 4 Ports: 1," in r["comment"]], "another head on OU4-1")
        self.assertFalse([r for r in on42 if r["layer"] == "head" and "OU: 2 " in r["comment"]],
                         "a head on OU2, the frozen turnout's 12V board")

    def test_a_frozen_heads_ports_are_its_own(self):
        """Ports as wired, not three in a row: the comment gives them, and the rule's heads keep off them."""
        got = self.build(wires('2,head,mast:123:B:west:top,,,,,,42,8,OU4,"2,4,6",wired,\n'
                               '2,head,mast:123:B:west:bottom,,,,,,42,9,OU4,"1,3,5",wired,\n'))
        self.assertEqual(got[("head", "Head 124LA Top")]["comment"], "Node: 42 Signal: 8 | OU: 4 Ports: 2,4,6")

    def test_freezing_a_mast_by_halves_stops(self):
        with self.assertRaisesRegex(bdm.MapError, "Mast 124LA: wiring.csv freezes 1 of its 2 head"):
            self.build(wires('2,head,mast:123:B:west:top,,,,,,42,8,OU4,"1,2,3",wired,\n'))

    def test_the_freeze_gives_the_same_map(self):
        """Freezing a control point as the rule has it changes no device row."""
        before = self.build([])
        p, frozen, pins = self.freeze("CP 123")
        self.assertEqual(wiring.digicon_rows(p), [])          # main and upper heads stay virtual: no Digicon head
        self.assertEqual(len([w for w in frozen if w.kind == "head"]), 8)
        self.assertEqual(self.build(frozen, pins), before)
        self.assertEqual(wiring.audit(p), [])                 # what the freeze wrote passes the audit

    def test_a_frozen_control_point_reads_back_identically_with_its_detectors(self):
        """The proposal, frozen and read back from wiring.csv (devices and detector pins both), is the same rows."""
        before = self.build([])
        p, frozen, pins = self.freeze("CP 123")
        self.assertTrue(pins, "CP 123 has detectors to pin")
        self.assertEqual(wiring.held(p).cps, {"CP 123"})
        self.assertEqual(self.build(frozen, pins), before)

    def test_a_frozen_control_point_proposes_nothing_more(self):
        """A frozen control point with one device dropped from wiring.csv is no longer proposed for by the rule."""
        p, frozen, pins = self.freeze("CP 123")
        gone = next(w for w in frozen if w.kind == "fb")
        with self.assertRaisesRegex(bdm.MapError, f"CP 123 are frozen, but the rule proposes fb {gone.device}"):
            self.build([w for w in frozen if w is not gone], pins)
        block = next(iter(bdm.read_pins(p)))
        with self.assertRaisesRegex(bdm.MapError, "CP 123 are frozen, but the rule proposes .*occupancy of "):
            self.build(frozen, {k: v for k, v in pins.items() if k != block})


class TheCommand(unittest.TestCase):
    """freeze_wiring.py's rows and merge."""
    ROWS = [dict(level="2", cp="", layer="turnout", role="turnout", user_name="Switch 9", system_name="M2T4208", node="42",
                 comment="Node: 42 Turnout: 0 | OU: 1 Ports: 1,2", blocks="", id="switch:9"),
            dict(level="2", cp="", layer="turnout", role="lcc_alias", user_name="DCC Switch 9", system_name="MTT150", node="42",
                 comment="Node: 42 Turnout: 0 | OU: 1 Ports: 1,2", blocks="", id="dcc:9"),
            dict(level="2", cp="CP 9", layer="occupancy", role="os", user_name="BS Switch 9", system_name="M2S4200", node="42",
                 comment="Node: 42 Block: 1", blocks="OS Switch 9", id="det:os:9"),
            dict(level="2", cp="CP 9", layer="occupancy", role="track", user_name="BS 9-11", system_name="M2S4201", node="42",
                 comment="Node: 42 Block: 2", blocks="Track 9-11", id="det:block:9B-11A"),
            dict(level="2", cp="CP 9", layer="occupancy", role="spur", user_name="BS 9 Spur", system_name="", node="",
                 comment="", blocks="Track 9 Spur", id="det:block:9C-end")]
    KEYS = {"Track 9-11": dict(switch_a="9", switch_b="11", parallel="", half="")}

    def setUp(self):
        # a turnout row has no cp: its place is its switch's in the switch lists (devices.place), here CP 9's
        # (places.of stops on a place that is no id of the lists, so the stand-in is devices.place itself)
        patch = mock.patch.object(fw.devices, "place",
                                  lambda r, schematic=None: r["cp"] if r["layer"] != "turnout" else
                                  "CP 9" if (r["level"], r["id"].split(":")[1]) == ("2", "9") else "")
        patch.start()
        self.addCleanup(patch.stop)

    def test_rows(self):
        got = fw.freeze_rows("CP 9", self.ROWS, self.KEYS, set(), "2026-11-21")
        # each by its id, a track's detector by its switches; device stays empty
        self.assertEqual([(r["kind"], r["id"], r["device"], r["switch_a"], r["node"], r["index"], r["board"],
                           r["ports"]) for r in got],
                         [("turnout", "switch:9", "", "", "42", "0", "OU1", "1,2"),      # the LCC alias follows it
                          ("detector", "det:os:9", "", "", "42", "1", "", ""),
                          ("detector", "", "", "9", "42", "2", "", "")])                 # no node: not frozen
        self.assertTrue(all(r["status"] == "wired" for r in got))

    def test_a_planned_row_turns_wired_and_a_second_freeze_adds_nothing(self):
        planned = HEAD + "2,detector,,,9,11,,,42,2,,,planned,the owner's pin\n"
        rows = fw.freeze_rows("CP 9", self.ROWS, self.KEYS, set(), "2026-11-21")
        text, added, turned = fw.merge(planned, rows)
        self.assertEqual((len(added), len(turned)), (2, 1))
        self.assertIn('2,detector,,,9,11,,,42,2,,,wired,"the owner\'s pin; frozen from', text)
        again, added, turned = fw.merge(text, rows)
        self.assertEqual((again, added, turned), (text, [], []))

    def test_a_planned_row_the_map_does_not_follow_stops(self):
        planned = HEAD + "2,detector,,,9,11,,,42,5,,,planned,the owner's pin\n"
        rows = fw.freeze_rows("CP 9", self.ROWS, self.KEYS, set(), "2026-11-21")
        with self.assertRaisesRegex(fw.FreezeError, "wiring.csv plans node 42 input 5, the device map has node 42 "
                                                    "input 2"):
            fw.merge(planned, rows)

    def test_stray_spaces_are_read_as_wiring_csv_reads_them(self):
        planned = HEAD + " 2 ,detector,,,9,11,,,42,2,,,planned ,\n"
        rows = fw.freeze_rows("CP 9", self.ROWS, self.KEYS, set(), "2026-11-21")
        _text, added, turned = fw.merge(planned, rows)
        self.assertEqual((len(added), len(turned)), (2, 1))

    def test_a_line_block_is_frozen_with_its_own_levels_place(self):
        """A line block's cp lists its own level's places first (build_device_map.line_cp): a main level helix
        detector, "CP 127;Princess", is frozen with CP 127, never with the staging station."""
        rows = [dict(level="2", cp="CP 127;Princess", layer="occupancy", role="helix", user_name="BS Helix Outer",
                     system_name="M2S4101", node="41", comment="Node: 41 Block: 2", blocks="Track Helix Outer",
                     id="det:block:131AA-helix")]
        got = fw.freeze_rows("CP 127", rows, {}, {"Track Helix Outer"}, "2026-11-21")
        self.assertEqual([(r["kind"], r["id"], r["node"], r["index"]) for r in got],
                         [("detector", "det:block:131AA-helix", "41", "2")])
        with self.assertRaisesRegex(fw.FreezeError, "no main or upper control point 'Princess'"):
            fw.freeze_rows("Princess", rows, {}, {"Track Helix Outer"}, "2026-11-21")

    def test_a_head_across_two_boards_is_frozen_as_wired(self):
        rows = self.ROWS + [dict(level="2", cp="CP 9", layer="head", role="head", user_name="Head 10L", system_name="IH4232",
                                 node="42", comment="Node: 42 Signal: 0 | OU: 2 Ports: 7 | OU: 3 Ports: 8,7",
                                 blocks="", id="mast:9:A:west:single")]
        head = next(r for r in fw.freeze_rows("CP 9", rows, self.KEYS, set(), "2026-11-21") if r["kind"] == "head")
        self.assertEqual((head["board"], head["ports"]), ("OU2", "7,OU3-8,OU3-7"))
        [w] = wires(",".join(head[c] if "," not in head[c] else f'"{head[c]}"' for c in wiring.COLUMNS) + "\n")
        self.assertEqual(w.wiring_text, "Node: 42 Signal: 0 | OU: 2 Ports: 7 | OU: 3 Ports: 8,7")

    def test_the_kind_is_the_rows_role_not_its_name(self):
        """An OS block's detector is frozen by its block (role os), a track's by its end switches, whatever the
        names say; the LCC alias is skipped by its role (hand-off row 8)."""
        rows = [dict(self.ROWS[2], role="track"), dict(self.ROWS[1], role="turnout")]
        keys = {"OS Switch 9": dict(switch_a="9", switch_b="11", parallel="", half="")}
        got = fw.freeze_rows("CP 9", rows, keys, set(), "2026-11-21")
        self.assertEqual([(r["kind"], r["id"], r["switch_a"]) for r in got],
                         [("detector", "", "9"), ("turnout", "dcc:9", "")])

    def test_a_row_with_no_role_stops(self):
        rows = [{k: v for k, v in self.ROWS[2].items() if k != "role"}]
        with self.assertRaisesRegex(fw.devices.DevicesError, "occupancy 'BS Switch 9' has no role"):
            fw.freeze_rows("CP 9", rows, self.KEYS, set(), "2026-11-21")

    def test_a_turnout_across_two_boards_stops(self):
        rows = [dict(self.ROWS[0], comment="Node: 42 Turnout: 0 | OU: 1 Ports: 1 | OU: 2 Ports: 2")]
        with self.assertRaisesRegex(fw.FreezeError, "spans two boards; only a head's pins may"):
            fw.freeze_rows("CP 9", rows, self.KEYS, set(), "2026-11-21")

    def test_what_cannot_be_frozen_stops(self):
        with self.assertRaisesRegex(fw.FreezeError, "no main or upper control point 'CP 8'; they are CP 9"):
            fw.freeze_rows("CP 8", self.ROWS, self.KEYS, set(), "2026-11-21")
        unplaced = self.ROWS + [dict(level="2", cp="CP 9", layer="head", role="head", user_name="Head 10L", system_name="",
                                     node="", comment="CP 9 | Switch 9", blocks="", id="mast:9:A:west:single")]
        with self.assertRaisesRegex(fw.FreezeError, "Head 10L has no node .*place it first"):
            fw.freeze_rows("CP 9", unplaced, self.KEYS, set(), "2026-11-21")


class OsPins(unittest.TestCase):
    def test_an_os_block_is_pinned_by_its_id(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "wiring.csv"
            p.write_text(HEAD + "2,detector,det:os:123,,,,,,42,1,,,wired,\n", encoding="utf-8")
            self.assertEqual(bdm.read_pins(p, found=[], split=set()), {"OS Switch 123": (42, 0)})


if __name__ == "__main__":
    unittest.main()
