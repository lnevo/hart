"""A frozen main or upper control point (owner, 2026-11-20): freeze_wiring.py copies the rule's wiring into
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
from hartlib import railroad, wiring  # noqa: E402

HEAD = ",".join(wiring.COLUMNS) + "\n"


def wires(text: str) -> list:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "wiring.csv"
        p.write_text(HEAD + text, encoding="utf-8")
        return wiring.read(p)


class TheNodes(unittest.TestCase):
    """Nodes.freeze holds a frozen device's number and pins; the rule gives the rest around them."""

    def nodes(self):
        return bdm.Nodes([railroad.LcosNode(2, 2, "North", 42), railroad.LcosNode(3, 2, "North", 52)])

    def test_a_frozen_turnout_keeps_its_number_and_the_rule_takes_the_next(self):
        nodes = self.nodes()
        nodes.freeze(wires('2,turnout,Switch 123,,,,,42,0,OU1,"1,2",wired,\n'))
        self.assertEqual(nodes.take(42, "turnout"), (1, 4209))
        self.assertEqual(nodes.take_frozen("turnout", "Switch 123").index, 0)
        self.assertIsNone(nodes.take_frozen("turnout", "Switch 123"))            # once

    def test_a_head_goes_round_frozen_pins(self):
        nodes = self.nodes()
        nodes.taken[(42, "turnout")] = {0, 1}                                   # one 12V board: OU1
        nodes.freeze(wires('2,head,Head 124LA Top,,,,,42,0,OU2,"1,2,3",wired,\n'))
        self.assertEqual(nodes.place_mast(42, 1), [(1, 4233, 2, 4)])            # OU2-4..6, not on 1..3
        self.assertEqual(nodes.place_mast(42, 1), [(2, 4234, 3, 1)])            # OU2-7, 8 too few: OU3
        nodes.used[42]["block"] = 1
        self.assertNotIn(8, nodes._free(42, 2))                                 # the calibration relay's pin

    def test_a_frozen_turnout_board_is_never_a_heads(self):
        """Switch 123 frozen on Turnout 7 (OU2): OU2 is a 12V board, so the rule's heads go on OU3."""
        nodes = self.nodes()
        nodes.freeze(wires('2,turnout,Switch 123,,,,,42,7,OU2,"7,8",wired,\n'))
        self.assertEqual(nodes.n12(42), 2)
        self.assertEqual(nodes.place_mast(42, 2)[0][2], 3)

    def test_the_rules_turnouts_go_round_a_frozen_heads_board(self):
        """A head frozen on OU2: the rule's turnouts take OU1 (Turnout 0 to 3) and not OU2 (4 to 7, LCOS's last),
        so a fifth turnout on the node stops, naming the frozen board."""
        nodes = self.nodes()
        nodes.freeze(wires('2,head,Head 1L,,,,,42,0,OU2,"1,2,3",wired,\n'))
        self.assertEqual([nodes.take(42, "turnout")[0] for _ in range(4)], [0, 1, 2, 3])
        nodes.check_boards()                                                    # OU1 turnouts, OU2 the head
        with self.assertRaisesRegex(bdm.MapError, r"node 42: no turnout left \(frozen heads in wiring.csv hold "
                                                  r"boards \[2\]\)"):
            nodes.take(42, "turnout")

    def test_a_frozen_head_on_a_turnout_board_or_the_calibration_pin_stops(self):
        nodes = self.nodes()
        nodes.freeze(wires('2,turnout,Switch 123,,,,,42,0,OU1,"1,2",wired,\n'
                           '2,head,Head 1L,,,,,42,0,OU1,"3,4,5",wired,\n'))
        with self.assertRaisesRegex(bdm.MapError, "node 42: heads on OU1, a 12V board a turnout is on"):
            nodes.check_boards()
        nodes = self.nodes()
        nodes.freeze(wires('2,turnout,Switch 123,,,,,42,0,OU1,"1,2",wired,\n'
                           '2,head,Head 1L,,,,,42,0,OU2,"6,7,8",wired,\n'))
        nodes.used[42]["block"] = 1
        with self.assertRaisesRegex(bdm.MapError, "OU2-8, the calibration relay's pin"):
            nodes.check_boards()

    def test_a_frozen_device_on_a_node_the_rule_does_not_hold_stops(self):
        with self.assertRaisesRegex(bdm.MapError, "Switch 9 is on node 13, which lcos_nodes.csv does not list"):
            self.nodes().freeze(wires('2,turnout,Switch 9,,,,,13,0,OU1,"1,2",wired,\n'))

    def test_a_frozen_row_the_map_does_not_use_stops(self):
        nodes = self.nodes()
        nodes.freeze(wires('2,turnout,Switch 999,,,,,42,0,OU1,"1,2",wired,\n'))
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

    def build(self, frozen):
        bands, joined, runs, corners = self.solved
        rr = self.rr
        _cp, rows, _parts = bdm.build(bands, joined, runs, rr.plan_overrides.data, rr.level_control_points,
                                      rr.lcos_nodes, rr.local_switches, corners, frozen=frozen)
        return {(r["layer"], r["user_name"]): r for r in rows}

    def test_frozen_where_the_rule_would_not_put_it(self):
        """Switch 123 frozen on node 42's Turnout 7 (OU2-7, 8) and Mast 124LA on OU4: the build keeps both, and no
        other device takes those numbers or pins."""
        got = self.build(wires('2,turnout,Switch 123,,,,,42,7,OU2,"7,8",wired,\n'
                               '2,head,Head 124LA Top,,,,,42,8,OU4,"1,2,3",wired,\n'
                               '2,head,Head 124LA Bottom,,,,,42,9,OU4,"4,5,6",wired,\n'))
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
        got = self.build(wires('2,head,Head 124LA Top,,,,,42,8,OU4,"2,4,6",wired,\n'
                               '2,head,Head 124LA Bottom,,,,,42,9,OU4,"1,3,5",wired,\n'))
        self.assertEqual(got[("head", "Head 124LA Top")]["comment"], "Node: 42 Signal: 8 | OU: 4 Ports: 2,4,6")

    def test_freezing_a_mast_by_halves_stops(self):
        with self.assertRaisesRegex(bdm.MapError, "Mast 124LA: wiring.csv freezes 1 of its 2 head"):
            self.build(wires('2,head,Head 124LA Top,,,,,42,8,OU4,"1,2,3",wired,\n'))

    def test_the_freeze_gives_the_same_map(self):
        """Freezing a control point as the rule has it changes no device row."""
        before = self.build([])
        helix = {h["block"] for h in bdm.read_helix_tracks().values()}
        rows = fw.freeze_rows("CP 123", fw.device_rows(), fw.track_keys(), helix, "2026-11-21")
        text, _added, _turned = fw.merge(HEAD, rows)
        p = Path(tempfile.mkdtemp()) / "wiring.csv"
        p.write_text(text, encoding="utf-8")
        frozen = bdm.frozen_wires(p)
        self.assertEqual(wiring.digicon_rows(p), [])          # main and upper heads stay virtual: no Digicon head
        self.assertEqual(len([w for w in frozen if w.kind == "head"]), 8)
        self.assertEqual(self.build(frozen), before)


class TheCommand(unittest.TestCase):
    """freeze_wiring.py's rows and merge."""
    ROWS = [dict(level="2", cp="CP 9", layer="turnout", user_name="Switch 9", system_name="M2T4208", node="42",
                 comment="Node: 42 Turnout: 0 | OU: 1 Ports: 1,2", blocks=""),
            dict(level="2", cp="CP 9", layer="turnout", user_name="DCC Switch 9", system_name="MTT150", node="42",
                 comment="Node: 42 Turnout: 0 | OU: 1 Ports: 1,2", blocks=""),
            dict(level="2", cp="CP 9", layer="occupancy", user_name="BS Switch 9", system_name="M2S4200", node="42",
                 comment="Node: 42 Block: 1", blocks="OS Switch 9"),
            dict(level="2", cp="CP 9", layer="occupancy", user_name="BS 9-11", system_name="M2S4201", node="42",
                 comment="Node: 42 Block: 2", blocks="Track 9-11"),
            dict(level="2", cp="CP 9", layer="occupancy", user_name="BS 9 Spur", system_name="", node="",
                 comment="", blocks="Track 9 Spur")]
    KEYS = {"Track 9-11": dict(switch_a="9", switch_b="11", parallel="", half="")}

    def test_rows(self):
        got = fw.freeze_rows("CP 9", self.ROWS, self.KEYS, set(), "2026-11-21")
        self.assertEqual([(r["kind"], r["device"], r["switch_a"], r["node"], r["index"], r["board"], r["ports"])
                          for r in got],
                         [("turnout", "Switch 9", "", "42", "0", "OU1", "1,2"),          # the LCC alias follows it
                          ("detector", "OS Switch 9", "", "42", "1", "", ""),
                          ("detector", "", "9", "42", "2", "", "")])                     # no node: not frozen
        self.assertTrue(all(r["status"] == "wired" for r in got))

    def test_a_planned_row_turns_wired_and_a_second_freeze_adds_nothing(self):
        planned = HEAD + "2,detector,,9,11,,,42,2,,,planned,the owner's pin\n"
        rows = fw.freeze_rows("CP 9", self.ROWS, self.KEYS, set(), "2026-11-21")
        text, added, turned = fw.merge(planned, rows)
        self.assertEqual((len(added), len(turned)), (2, 1))
        self.assertIn('2,detector,,9,11,,,42,2,,,wired,"the owner\'s pin; frozen from', text)
        again, added, turned = fw.merge(text, rows)
        self.assertEqual((again, added, turned), (text, [], []))

    def test_a_planned_row_the_map_does_not_follow_stops(self):
        planned = HEAD + "2,detector,,9,11,,,42,5,,,planned,the owner's pin\n"
        rows = fw.freeze_rows("CP 9", self.ROWS, self.KEYS, set(), "2026-11-21")
        with self.assertRaisesRegex(fw.FreezeError, "wiring.csv plans node 42 input 5, the device map has node 42 "
                                                    "input 2"):
            fw.merge(planned, rows)

    def test_stray_spaces_are_read_as_wiring_csv_reads_them(self):
        planned = HEAD + " 2 ,detector,,9,11,,,42,2,,,planned ,\n"
        rows = fw.freeze_rows("CP 9", self.ROWS, self.KEYS, set(), "2026-11-21")
        _text, added, turned = fw.merge(planned, rows)
        self.assertEqual((len(added), len(turned)), (2, 1))

    def test_what_cannot_be_frozen_stops(self):
        with self.assertRaisesRegex(fw.FreezeError, "no main or upper control point 'CP 8'; they are CP 9"):
            fw.freeze_rows("CP 8", self.ROWS, self.KEYS, set(), "2026-11-21")
        unplaced = self.ROWS + [dict(level="2", cp="CP 9", layer="head", user_name="Head 10L", system_name="",
                                     node="", comment="CP 9 | Switch 9", blocks="")]
        with self.assertRaisesRegex(fw.FreezeError, "Head 10L has no node .*place it first"):
            fw.freeze_rows("CP 9", unplaced, self.KEYS, set(), "2026-11-21")


class OsPins(unittest.TestCase):
    def test_an_os_block_is_pinned_by_its_name(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "wiring.csv"
            p.write_text(HEAD + "2,detector,OS Switch 123,,,,,42,1,,,wired,\n", encoding="utf-8")
            self.assertEqual(bdm.read_pins(p, found=[], split=set()), {"OS Switch 123": (42, 0)})


if __name__ == "__main__":
    unittest.main()
