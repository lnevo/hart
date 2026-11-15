"""tools/schematic/build_cats_panel.py: how the staging bindings come from the facts, on a tiny made-up band.

The band: Switch 1 (one OS) leads by an unnamed short track to Switch 2's half 2a; Switch 2 is a crossover of two
nodes (2a and 2b, its halves told apart by the named tracks they touch or by elimination); 2b leads through a
turnback to the named half Loop.
"""
from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/schematic"))

import build_cats_panel as B  # noqa: E402
from layout_facts import Leg, Switch  # noqa: E402


def node(label, alias, ins, outs, kind="switch"):
    return {"kind": kind, "label": label, "alias": alias, "ins": ins, "outs": outs}


def strand(src, dst, name=""):
    return {"src": src, "dst": dst, "name": name}


def band():
    nodes = {
        "N1": node("1", "T1", {"A": "w"}, {"B": "s12", "C": "y"}),
        "N2a": node("2", "2a", {"A": "s12"}, {"B": "m", "C": "x"}),
        "N2b": node("2", "2b", {"A": "loop0", "C": "x"}, {"B": "e"}),
        "turn": node("", "", {}, {0: "loop0", 1: "loop1"}, kind="turnR"),
        "END:w": node("", "", {}, {}, kind="end"), "END:y": node("", "", {}, {}, kind="end"),
        "END:m": node("", "", {}, {}, kind="end"), "END:e": node("", "", {}, {}, kind="end"),
        "END:l": node("", "", {}, {}, kind="end"),
    }
    strands = {
        "w": strand(("END:w", "E"), ("N1", "A"), "West"),
        "y": strand(("N1", "C"), ("END:y", "E"), "Yard"),
        "s12": strand(("N1", "B"), ("N2a", "A")),
        "m": strand(("N2a", "B"), ("END:m", "E"), "Main"),
        "x": strand(("N2a", "C"), ("N2b", "C")),
        "e": strand(("N2b", "B"), ("END:e", "E"), "East"),
        "loop0": strand(("N2b", "A"), ("turn", 0)),
        "loop1": strand(("turn", 1), ("END:l", "E"), "Loop"),
    }
    return {"nodes": nodes, "strands": strands}


LE_XML = """<layout-config><LayoutEditor name="HART Railroad">
  <layoutturnout ident="TO1" xa="0" ya="0" xb="10" yb="0" xc="10" yc="5" />
  <layoutturnout ident="TO2" xa="40" ya="0" xb="50" yb="0" xc="50" yc="5" />
  <positionablepoint ident="P1" x="20" y="0" />
  <positionablepoint ident="P2" x="35" y="0" />
  <tracksegment ident="S1" blockname="OS Switch 1" connect1name="TO1" type1="TURNOUT_B" connect2name="P1" type2="POS_POINT" />
  <tracksegment ident="S2" blockname="" connect1name="P1" type1="POS_POINT" connect2name="P2" type2="POS_POINT" />
  <tracksegment ident="S3" blockname="OS Switch 2a" connect1name="P2" type1="POS_POINT" connect2name="TO2" type2="TURNOUT_A" />
</LayoutEditor></layout-config>"""


def facts(**kw):
    switches = {
        1: Switch(1, "1", "TO1", False, 1, True, (Leg("OS Switch 1", "OS Switch 2a", "Track Yard"),)),
        2: Switch(2, "1", "TO2", True, 2, True, (Leg("OS Switch 2a", "Track Main", "OS Switch 2b"),
                                                 Leg("OS Switch 2b", "Track East", "OS Switch 2a"))),
    }
    occupancy = {n: (str(i), "BS " + n) for i, n in enumerate(
        ["OS Switch 1", "OS Switch 2a", "OS Switch 2b", "Track West", "Track Yard", "Track Main", "Track East",
         "Track Loop"])}
    f = B.Facts(switches, {"TO1": ("11", "Switch 1"), "TO2": ("12", "Switch 2")}, occupancy, {},
                B.LayoutEditor(ET.fromstring(LE_XML)), {"Mast 1L": "single"}, {"Mast 1L"})
    for k, v in kw.items():
        setattr(f, k, v)
    return f


class OsBlocks(unittest.TestCase):
    def test_by_named_track_then_by_elimination(self):
        b = band()
        self.assertEqual(B.os_blocks(b, facts()), {"N1": "OS Switch 1", "N2a": "OS Switch 2a", "N2b": "OS Switch 2b"})
        b["strands"]["e"]["name"] = ""            # 2b touches no named track of its row: the row left over
        b["strands"]["e"]["dst"] = ("END:e", "E")
        self.assertEqual(B.os_blocks(b, facts())["N2b"], "OS Switch 2b")

    def test_two_nodes_on_one_row_stop(self):
        b = band()
        b["strands"]["e"]["name"] = "Main"        # both halves touch Track Main
        with self.assertRaisesRegex(SystemExit, "would both be OS Switch 2a"):
            B.os_blocks(b, facts())

    def test_a_switch_not_in_the_facts_stops(self):
        b = band()
        b["nodes"]["N1"]["label"] = "9"
        with self.assertRaisesRegex(SystemExit, "not in switches.csv"):
            B.os_blocks(b, facts())


class Dest(unittest.TestCase):
    def test_named_track_next_switch_and_through_a_turnback(self):
        b = band()
        os_of = B.os_blocks(b, facts())
        self.assertEqual(B.dest(b, os_of, "N1", "C"), "Track Yard")
        self.assertEqual(B.dest(b, os_of, "N1", "B"), "OS Switch 2a")
        self.assertEqual(B.dest(b, os_of, "N2b", "A"), "Track Loop")

    def test_a_track_to_nowhere_stops(self):
        b = band()
        os_of = B.os_blocks(b, facts())
        b["strands"]["loop1"]["name"] = ""
        with self.assertRaisesRegex(SystemExit, "reaches no named track or switch"):
            B.dest(b, os_of, "N2b", "A")

    def test_a_turnback_loop_stops_instead_of_hanging(self):
        b = band()
        os_of = B.os_blocks(b, facts())
        b["strands"]["loop1"] = strand(("turn", 1), ("turn", 0))
        b["nodes"]["turn"]["outs"] = {0: "loop0", 1: "loop1"}
        with self.assertRaises(SystemExit):
            B.dest(b, os_of, "N2b", "A")


class Switches(unittest.TestCase):
    def test_routes_by_closed_and_thrown_leg(self):
        b = band()
        out = B.switch_bindings(b, facts(), B.os_blocks(b, facts()))
        self.assertEqual(set(out), {"1", "2/2a", "2/2b"})
        one = out["1"]                            # closed leg OS Switch 2a is leg B
        self.assertEqual((one["block"], one["normal"]), ("OS Switch 1", "B"))
        self.assertEqual(one["routes"]["B"]["ROUTECOMMAND"]["command"], "close")
        self.assertEqual(one["routes"]["C"]["SELECTEDREPORT"]["command"], "throw")
        self.assertEqual(out["2/2a"]["normal"], "C")   # CATS inverted: normal is the thrown leg
        self.assertEqual((out["2/2a"]["label"], out["2/2b"]["label"]), ("2A", "2B"))   # crossover halves lettered
        self.assertNotIn("label", out["1"])

    def test_a_crossover_half_without_a_letter_is_a(self):
        sw = Switch(7, "1", "TO7", False, 7, True, (Leg("OS Switch 7", "Track A", "OS Switch 7b"),
                                                     Leg("OS Switch 7b", "Track B", "OS Switch 7")))
        self.assertEqual([B.half_label(sw, l) for l in sw.legs], ["7A", "7B"])
        both = Switch(7, "1", "TO7", False, 7, True, (Leg("OS Switch 7", "Track A", "OS X"),
                                                       Leg("OS X", "Track B", "OS Switch 7")))
        with self.assertRaises(SystemExit):
            B.half_label(both, both.legs[0])

    def test_legs_disagreeing_with_switch_legs_stop(self):
        f = facts()
        f.switches[1] = Switch(1, "1", "TO1", False, 1, True, (Leg("OS Switch 1", "Track Main", "Track Yard"),))
        b = band()
        with self.assertRaisesRegex(SystemExit, "switch_legs.csv says"):
            B.switch_bindings(b, f, B.os_blocks(b, f))


class LayoutEditorTracks(unittest.TestCase):
    def test_the_block_holding_most_of_the_track(self):
        le = facts().layout
        self.assertEqual([[blk for blk, _ in p] for p in le.paths("TO1", "TO2")],
                         [["OS Switch 1", "", "OS Switch 2a"]])
        # OS Switch 1: 10 long, unnamed 15 (ignored), OS Switch 2a: 5
        self.assertEqual(le.block_between("TO1", "TO2", "t"), "OS Switch 1")

    def test_no_track_two_tracks_no_block_or_a_tie_stop(self):
        xml = LE_XML
        le = B.LayoutEditor(ET.fromstring(xml))
        with self.assertRaisesRegex(SystemExit, "no Layout Editor tracks join"):
            le.block_between("TO2", "TO9", "t")
        twice = xml.replace("</LayoutEditor>", '<tracksegment ident="S4" blockname="X" connect1name="TO1" '
                            'type1="TURNOUT_C" connect2name="TO2" type2="TURNOUT_C" /></LayoutEditor>')
        with self.assertRaisesRegex(SystemExit, "2 Layout Editor tracks join"):
            B.LayoutEditor(ET.fromstring(twice)).block_between("TO1", "TO2", "t")
        blank = xml.replace('blockname="OS Switch 1"', 'blockname=""').replace('blockname="OS Switch 2a"',
                                                                               'blockname=""')
        with self.assertRaisesRegex(SystemExit, "has no block"):
            B.LayoutEditor(ET.fromstring(blank)).block_between("TO1", "TO2", "t")
        tie = xml.replace('xb="10"', 'xb="15"')        # OS Switch 1 now 5 long, like OS Switch 2a
        with self.assertRaisesRegex(SystemExit, "split evenly"):
            B.LayoutEditor(ET.fromstring(tie)).block_between("TO1", "TO2", "t")


class Blocks(unittest.TestCase):
    def test_jmri_blocks_and_the_short_track_rule(self):
        b = band()
        names = {("os", "b0:N1"): "OS Switch 1", ("track", "b0:w"): "West", ("track", "b0:s12"): "1-2"}
        out = B.block_bindings(b, facts(), names)
        self.assertNotIn("name", out["OS Switch 1"])
        self.assertEqual(out["OS Switch 1"]["occupied"]["USER_NAME"], "BS OS Switch 1")
        self.assertEqual(out["West"]["name"], "Track West")
        self.assertEqual(out["1-2"], {"name": "OS Switch 1"})

    def test_a_block_with_no_jmri_block_that_is_no_short_track_stops(self):
        b = band()
        for names in ({("track", "b0:m"): "Mainline"},                 # named track, not in JMRI
                      {("track", "b0:loop0"): "2-turn"},               # unnamed, but not between two switches
                      {("os", "b0:N1"): "OS 1"}):                      # an OS block JMRI does not have
            with self.subTest(names=names):
                b["strands"]["m"]["name"] = "Mainline"
                with self.assertRaisesRegex(SystemExit, "not a short unnamed track between two switches"):
                    B.block_bindings(b, facts(), names)


class Masts(unittest.TestCase):
    def test_drawn_masts_once_each(self):
        sig = {"mast": "1L", "kind": "field"}
        opts = {"mast_prefix": "Mast ", "signals": [sig, {"mast": "9V", "kind": "virtual"}]}
        self.assertEqual(B.mast_bindings(opts, facts()), {"1L": {"name": "Mast 1L", "template": "single"}})
        with self.assertRaisesRegex(SystemExit, "listed twice"):
            B.mast_bindings(dict(opts, signals=[sig, dict(sig)]), facts())
        with self.assertRaisesRegex(SystemExit, "not a JMRI mast"):
            B.mast_bindings(dict(opts, signals=[{"mast": "2R", "kind": "planned"}]), facts())


if __name__ == "__main__":
    unittest.main()
