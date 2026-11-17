"""tools/schematic/build_cats_panel.py: how the staging bindings come from the facts, on a tiny made-up band.

The band: Switch 1 (one OS) leads by an unnamed short track to Switch 2's half 2a; Switch 2 is a crossover of two
nodes (2a and 2b, its halves told apart by the named tracks they touch or by elimination); 2b leads through a
turnback to the named half Loop.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest import mock
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


# the frozen Layout Editor tracks (staging_le/tracks.csv as le_inputs loads it): TO1 leg B to TO2 leg A holds
# OS Switch 1 then OS Switch 2a
CHAINS = [{"ends": [("TO1", "B"), ("TO2", "A")], "blocks": ["OS Switch 1", "OS Switch 2a"]},
          {"ends": [("TO1", "C"), ("END", "EB1")], "blocks": ["Track Yard"]},
          {"ends": [("TO2", "B"), ("TO3", "A")], "blocks": ["Track Main"]}]


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
                B.FrozenTracks(CHAINS), {"Mast 1L": "single"}, {"Mast 1L"})
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
        with self.assertRaises(SystemExit):                   # the second, unlettered leg too
            B.half_label(both, both.legs[1])
        taken = Switch(7, "1", "TO7", False, 7, True, (Leg("OS Switch 7", "Track A", "OS Switch 7a"),
                                                        Leg("OS Switch 7a", "Track B", "OS Switch 7")))
        with self.assertRaises(SystemExit):                   # 7 cannot be A when 7a already is
            B.half_label(taken, taken.legs[0])

    def test_fit_comes_from_the_window(self):
        self.assertEqual(B.FIT, ((B.WINDOW[0] - B.CHROME[0]) // B.GRID_PX, (B.WINDOW[1] - B.CHROME[1]) // B.GRID_PX))
        self.assertLessEqual(B.MAX_COLS, B.FIT[0])

    def test_legs_disagreeing_with_switch_legs_stop(self):
        f = facts()
        f.switches[1] = Switch(1, "1", "TO1", False, 1, True, (Leg("OS Switch 1", "Track Main", "Track Yard"),))
        b = band()
        with self.assertRaisesRegex(SystemExit, "switch_legs.csv says"):
            B.switch_bindings(b, f, B.os_blocks(b, f))


class FrozenLayoutEditorTracks(unittest.TestCase):
    def test_a_track_of_one_block_is_that_block(self):
        self.assertEqual(B.FrozenTracks(CHAINS).block_between("TO3", "TO2", "t"), "Track Main")

    def test_no_track_two_tracks_or_a_bumper_stop(self):
        tracks = B.FrozenTracks(CHAINS)
        with self.assertRaisesRegex(SystemExit, "no Layout Editor tracks join TO2 and TO9"):
            tracks.block_between("TO2", "TO9", "t")
        with self.assertRaisesRegex(SystemExit, "no Layout Editor tracks join"):
            tracks.block_between("TO1", "END", "t")               # a track to a bumper joins no two switches
        twice = B.FrozenTracks(CHAINS + [{"ends": [("TO2", "C"), ("TO1", "D")], "blocks": ["X"]}])
        with self.assertRaisesRegex(SystemExit, "2 Layout Editor tracks join"):
            twice.block_between("TO1", "TO2", "t")

    def test_a_track_of_several_blocks_needs_a_fixed_one_on_it(self):
        tracks = B.FrozenTracks(CHAINS)
        with self.assertRaisesRegex(SystemExit, "holds blocks OS Switch 1, OS Switch 2a; name the one"):
            tracks.block_between("TO1", "TO2", "t")
        self.assertEqual(tracks.block_between("TO1", "TO2", "t", "OS Switch 2a"), "OS Switch 2a")
        with self.assertRaisesRegex(SystemExit, "SHORT_TRACK_BLOCKS names OS Switch 9, but .* holds only "
                                    "OS Switch 1, OS Switch 2a"):
            tracks.block_between("TO1", "TO2", "t", "OS Switch 9")

    def test_the_35_37_track_is_os_switch_35a_on_the_frozen_track(self):
        # the generated Layout Editor panel splits it evenly; the hand-drawn one gave most of it to 35a
        self.assertEqual(B.SHORT_TRACK_BLOCKS, {"35-37": "OS Switch 35a"})
        sys.path.insert(0, str(ROOT / "tools/schematic"))
        import le_inputs
        frozen = B.FrozenTracks(le_inputs.load().chains)
        self.assertEqual(frozen.block_between("TOR36", "TO113", "t", "OS Switch 35a"), "OS Switch 35a")


class Blocks(unittest.TestCase):
    def test_jmri_blocks_and_the_short_track_rule(self):
        b = band()
        names = {("os", "b0:N1"): "OS Switch 1", ("track", "b0:w"): "West", ("track", "b0:s12"): "1-2"}
        with self.assertRaisesRegex(SystemExit, "block 1-2: .* holds blocks OS Switch 1, OS Switch 2a"):
            B.block_bindings(b, facts(), names)       # the frozen track holds two blocks and none is named
        with mock.patch.dict(B.SHORT_TRACK_BLOCKS, {"1-2": "OS Switch 1"}):
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


class StubCats:
    """The plugin's label_of, for the main and upper naming."""
    @staticmethod
    def label_of(bands, key):
        tag, n = key[1].split(":", 1)
        return bands[int(tag[1:])][1]["nodes"][n].get("label") or ""


def device():
    return B.DeviceMap(
        blocks={"OS Switch 101": {"level": 2, "trial": {"OS Switch 101"}},
                "OS Switch 103": {"level": 2, "trial": {"OS Switch 103"}},
                "Track 101-111": {"level": 2, "trial": {"Track e24"}},
                "Track 101-103": {"level": 2, "trial": {"Track e28"}},
                "Track 135-H1": {"level": 2, "trial": {"Track e34", "Track e35"}}},
        sensors={"BS Switch 101": "M2S3300", "BS 101-111": "M2S3306"})


def dark_bands():
    nodes = {"A": node("101A", "", {}, {}), "B": node("101B", "", {}, {}), "C": node("103A", "", {}, {}),
             "END": node("", "", {}, {}, kind="end")}
    strands = {"e24": dict(strand(("B", "C"), ("END", "E")), edge="e24"),
               "e34x": dict(strand(("A", "B"), ("END", "E")), edge="e34x"),
               "e99": dict(strand(("A", "B"), ("END", "E")), edge="e99"),
               "e77": dict(strand(("A", "C"), ("B", "C")), edge="e77")}
    return [("Staging level", {"nodes": {}, "strands": {}}, {}),
            ("Main level", {"nodes": nodes, "strands": strands}, {})]


class MainAndUpper(unittest.TestCase):
    def test_os_blocks_take_the_switch_number_and_a_merge_the_lowest(self):
        f, log = facts(device=device()), []
        self.assertEqual(B.device_name(dark_bands(), StubCats, [("os", "b1:A"), ("os", "b1:B")], f, log),
                         "OS Switch 101")
        self.assertEqual(log, [])
        self.assertEqual(B.device_name(dark_bands(), StubCats, [("os", "b1:C"), ("os", "b1:A")], f, log),
                         "OS Switch 101")
        self.assertIn("switches 101, 103 share one OS block", log[0])

    def test_tracks_take_the_device_map_row_holding_their_schematic_tracks(self):
        f = facts(device=device())
        self.assertEqual(B.device_name(dark_bands(), StubCats, [("track", "b1:e24")], f, []), "Track 101-111")
        self.assertEqual(B.device_name(dark_bands(), StubCats, [("track", "b1:e34x")], f, []), "Track 135-H1")
        with self.assertRaisesRegex(SystemExit, "in no device map block rows"):
            B.device_name(dark_bands(), StubCats, [("track", "b1:e99")], f, [])

    def test_the_track_between_crossover_halves_is_the_crossovers_os_block(self):
        f = facts(device=device())          # e77 joins 101A and 101B and is in no device map row
        self.assertEqual(B.device_name(dark_bands(), StubCats, [("track", "b1:e77")], f, []), "OS Switch 101")

    def test_planned_detectors(self):
        f = facts(device=device())
        self.assertEqual(B.planned_sensor("OS Switch 101", f)["occupied"],
                         {"DECADDR": "3300", "JMRIPREFIX": "M2S", "USER_NAME": "BS Switch 101", "command": "close"})
        self.assertEqual(B.planned_sensor("Track 101-111", f)["unoccupied"],
                         {"DECADDR": "3306", "JMRIPREFIX": "M2S", "command": "throw"})
        self.assertIsNone(B.planned_sensor("OS Switch 103", f))

    def test_the_device_map_reads_blocks_and_detectors(self):
        dm = B.load_device_map()
        self.assertEqual(len(dm.sensors), 39)
        virtual = sorted(k for k, v in dm.sensors.items() if not v.startswith("M2S"))
        # Loop 2 and 225's corners b to d wait for wiring: internal sensors until then (owner, 2026-11-16)
        self.assertEqual(virtual, ["BS 107 Loop 2", "BS Switch 225b", "BS Switch 225c", "BS Switch 225d"])
        self.assertTrue(all(dm.sensors[k].startswith("IS:HART:C3:") for k in virtual))
        self.assertEqual(dm.blocks["Track 107-109"]["trial"], {"Track e19"})

    def test_a_block_missing_from_the_desk_is_checked_on_the_drawing(self):
        class FakeP:
            def __init__(self, blocks):
                self.blocks = blocks

            def find(self, k):
                return ("os", "b1:A") if k == ("track", "b1:e24") else k
        bands = dark_bands()
        bands[1][1]["strands"]["e28"] = dict(strand(("A", "C"), ("C", "A")), edge="e28", cm=3.4)
        bands[1][1]["strands"]["e24"]["cm"] = 398.1
        row = lambda *t: {"level": 2, "trial": set(t)}
        self.assertEqual(B.inside_os(bands, FakeP({}), 0, "Track 101-103", row("Track e28")),
                         "a short link (3.4 cm) inside its switches' OS blocks")
        # a track key joined to an OS block counts as inside it; a long one says why it has no block
        bands[1][1]["strands"]["e24"] = dict(strand(("B", "C"), ("C", "B")), edge="e24", cm=398.1)
        self.assertIn("398.1 cm, too short at one cell per grid unit",
                      B.inside_os(bands, FakeP({("track", "b1:e24"): None}), 0, "Track 101-111", row("Track e24")))
        with self.assertRaisesRegex(SystemExit, "Track X: its schematic track e28 is a desk block"):
            B.inside_os(bands, FakeP({("track", "b1:e28"): None}), 0, "Track X", row("Track e28"))
        with self.assertRaisesRegex(SystemExit, "Track Y: its schematic track e99 has no desk block and does not run "
                                    "between switches"):
            B.inside_os(bands, FakeP({}), 0, "Track Y", row("Track e99"))      # e99 ends at a bumper
        with self.assertRaisesRegex(SystemExit, "Track Z: the device map's tracks .* are not all drawn"):
            B.inside_os(bands, FakeP({}), 0, "Track Z", row("Track e28", "Track e500"))

    def test_staging_and_dark_blocks_never_take_one_name(self):
        B.check_apart({"West": {"name": "Track West"}}, {"OS 101": {"name": "OS Switch 101"}})
        with self.assertRaisesRegex(SystemExit, "share panel names West"):
            B.check_apart({"West": {}}, {"West": {"name": "Track 1-2"}})
        with self.assertRaisesRegex(SystemExit, "would both be Track West"):
            B.check_apart({"West": {"name": "Track West"}}, {"1-2": {"name": "Track West"}})

    def test_the_loop_halves_and_225s_corners_on_the_desk(self):
        """The committed bindings: the 107 Loop is two dark desk blocks, Loop 2 on its virtual detector; the desk draws
        double crossover 225 as one block, on corner a's detector, and lists the four corner blocks as not on it."""
        got = json.loads(B.BINDINGS.read_text(encoding="utf-8"))
        loop = {e["name"]: e["_planned_occupied"] for e in got["blocks"].values() if "107 Loop" in e.get("name", "")}
        self.assertEqual({k: (v["JMRIPREFIX"], v["USER_NAME"]) for k, v in loop.items()},
                         {"Track 107 Loop 1": ("M2S", "BS 107 Loop 1"), "Track 107 Loop 2": ("IS", "BS 107 Loop 2")})
        os225 = [e for e in got["blocks"].values() if e.get("name") == "OS Switch 225"]
        self.assertEqual([e["_planned_occupied"]["USER_NAME"] for e in os225], ["BS Switch 225a"])
        self.assertEqual(sorted(k for k in got["_main_upper_not_on_desk"] if k.startswith("OS Switch 225")),
                         [f"OS Switch 225{c}" for c in "abcd"])

    def test_main_and_upper_are_dtc_and_not_detected_yet(self):
        self.assertEqual(B.MAIN_UPPER_DISCIPLINE, "DTC")
        self.assertFalse(B.DETECT_MAIN_UPPER)


def plugin_cats():
    try:
        return B.plugin_modules(B.pd.plugin())[0]
    except SystemExit as e:
        raise unittest.SkipTest(f"no plugin: {e.code}") from None


class Header(unittest.TestCase):
    def doc(self, *labels):
        root = ET.Element("DOCUMENT", VERSION="3.1")
        ET.SubElement(root, "FONTDEFINITION", FONTKEY="FONT_TITLE", FONTSIZE="13")
        ET.SubElement(root, "COMPRESSIONTAG")
        ET.SubElement(root, "ROWWRAPTAG")
        tp = ET.SubElement(root, "TRACKPLAN")
        for x, text in labels:
            sec = ET.SubElement(tp, "SECTION", X=str(x), Y="1")
            ET.SubElement(sec, "SEC_NAME", LOC_NAME="LOWLEFT", NAME=text, FONT_NAME="FONT_TITLE")
        ET.SubElement(ET.SubElement(tp, "SECTION", X="5", Y="3"), "SEC_EDGE", EDGE="LEFT").append(
            ET.Element("BLOCK", NAME="Track X", DISCIPLINE="CTC"))
        return root

    def test_the_frozen_header_in_the_live_order_and_the_abs_plate(self):
        cats = plugin_cats()
        header, plate = B.frozen_header()
        out = ET.fromstring(B.dress(cats, self.doc((2, "STAGING")), header, plate, "ABS").split("\n", 1)[1])
        tags = [el.tag for el in out]
        self.assertEqual(sorted(set(tags), key=tags.index), [t for t in B.ORDER if t in tags])
        fonts = {el.get("FONTKEY"): el.get("FONTSIZE") for el in out.findall("FONTDEFINITION")}
        self.assertEqual((len(fonts), fonts["FONT_TITLE"]), (12, "13"))     # the plugin's own font kept
        words = {n.get("NAME") for n in out.iter("SEC_NAME")}
        self.assertIn("ABS DIGICON", words)
        self.assertTrue(any(w.startswith("DS-ABS ") for w in words))
        self.assertEqual({b.get("DISCIPLINE") for b in out.iter("BLOCK")}, {"ABS"})
        self.assertEqual(out.find("OPERATIONS").get("CONNECT"), "false")

    def test_header_tags_replace_the_plugins_only_when_the_header_has_them(self):
        cats = plugin_cats()
        header, plate = B.frozen_header()
        doc = self.doc((2, "STAGING"))
        doc.insert(1, ET.Element("COLORDEFINITION", COLORKEY="PLUGIN"))
        no_colours = [el for el in header if el.tag != "COLORDEFINITION"]
        out = ET.fromstring(B.dress(cats, doc, no_colours, plate, "CTC").split("\n", 1)[1])
        self.assertEqual([c.get("COLORKEY") for c in out.findall("COLORDEFINITION")], ["PLUGIN"])
        out = ET.fromstring(B.dress(cats, self.doc((2, "S")), header, plate, "CTC").split("\n", 1)[1])
        self.assertNotIn("PLUGIN", [c.get("COLORKEY") for c in out.findall("COLORDEFINITION")])
        odd = self.doc((2, "STAGING"))
        odd.insert(1, ET.Element("MYSTERY"))
        with self.assertRaisesRegex(SystemExit, "elements MYSTERY, which ORDER does not place"):
            B.dress(cats, odd, header, plate, "CTC")

    def test_a_header_without_signal_templates_or_jmri_names_stops(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        for tag in ("SIGNALTEMPLATE", "JMRINAME"):
            root = ET.parse(B.HEADER).getroot()
            for el in root.findall(tag):
                root.remove(el)
            path = tmp / f"no_{tag}.xml"
            ET.ElementTree(root).write(path)
            with self.subTest(tag=tag), self.assertRaisesRegex(SystemExit, f"no {tag} elements"):
                B.frozen_header(path)

    def test_a_plate_label_on_a_used_cell_or_over_another_label_stops(self):
        cats = plugin_cats()
        header, plate = B.frozen_header()
        with self.assertRaisesRegex(SystemExit, "a cell the desk uses"):
            B.dress(cats, self.doc((15, "X")), header, plate, "CTC")
        with self.assertRaisesRegex(SystemExit, "runs into the label"):
            B.dress(cats, self.doc((2, "A VERY LONG TITLE THAT RUNS FAR TO THE RIGHT")), header, plate, "CTC")


if __name__ == "__main__":
    unittest.main()
