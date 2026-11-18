"""tools/schematic/build_cats_panel.py: how the staging bindings come from the facts, on a tiny made-up band.

The band: Switch 1 (one OS) leads by an unnamed short track to Switch 2's half 2a; Switch 2 is a crossover of two
nodes (2a and 2b, its halves told apart by the named tracks they touch or by elimination); 2b leads through a
turnback to the named half Loop.
"""
from __future__ import annotations

import json
import os
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


# the staging tracks (staging_device_map.staging_chains): TO1 leg B to TO2 leg A holds
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
                B.StagingTracks(CHAINS), {"Mast 1L": "single"}, {"Mast 1L"})
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
        o = desk_options()
        self.assertEqual((o["window"], o["fit"]), ((1900, 1020), (62, 30)))   # (1900 - 20) // 30, (1020 - 100) // 30
        with self.assertRaisesRegex(SystemExit, "no cats_window"):
            B.desk_options(plugin_cats(), {}, [])
        with self.assertRaisesRegex(SystemExit, "the desks need \"apart\""):
            B.desk_options(plugin_cats(), {"cats_window": [1900, 1020]}, [])

    def test_legs_disagreeing_with_switch_legs_stop(self):
        f = facts()
        f.switches[1] = Switch(1, "1", "TO1", False, 1, True, (Leg("OS Switch 1", "Track Main", "Track Yard"),))
        b = band()
        with self.assertRaisesRegex(SystemExit, "switch_legs.csv says"):
            B.switch_bindings(b, f, B.os_blocks(b, f))


class StagingTracks(unittest.TestCase):
    def test_a_track_of_one_block_is_that_block(self):
        self.assertEqual(B.StagingTracks(CHAINS).block_between("TO3", "TO2", "t"), "Track Main")

    def test_no_track_two_tracks_or_a_bumper_stop(self):
        tracks = B.StagingTracks(CHAINS)
        with self.assertRaisesRegex(SystemExit, "no staging tracks join TO2 and TO9"):
            tracks.block_between("TO2", "TO9", "t")
        with self.assertRaisesRegex(SystemExit, "no staging tracks join"):
            tracks.block_between("TO1", "END", "t")               # a track to a bumper joins no two switches
        twice = B.StagingTracks(CHAINS + [{"ends": [("TO2", "C"), ("TO1", "D")], "blocks": ["X"]}])
        with self.assertRaisesRegex(SystemExit, "2 staging tracks join"):
            twice.block_between("TO1", "TO2", "t")

    def test_a_track_of_several_blocks_needs_a_fixed_one_on_it(self):
        tracks = B.StagingTracks(CHAINS)
        with self.assertRaisesRegex(SystemExit, "holds blocks OS Switch 1, OS Switch 2a; name the one"):
            tracks.block_between("TO1", "TO2", "t")
        self.assertEqual(tracks.block_between("TO1", "TO2", "t", "OS Switch 2a"), "OS Switch 2a")
        with self.assertRaisesRegex(SystemExit, "SHORT_TRACK_BLOCKS names OS Switch 9, but .* holds only "
                                    "OS Switch 1, OS Switch 2a"):
            tracks.block_between("TO1", "TO2", "t", "OS Switch 9")

    def test_the_35_37_track_is_os_switch_35a_on_the_staging_track(self):
        # the generated Layout Editor panel splits it evenly; the hand-drawn one gave most of it to 35a. The track is
        # the staging device map's (staging_device_map.staging_chains)
        self.assertEqual(B.SHORT_TRACK_BLOCKS, {"35-37": "OS Switch 35a"})
        try:                    # the staging tracks need the plugin's solve: skipped without it, as the --check scripts
            B.pd.plugin()
        except SystemExit as exc:
            if os.environ.get("SCHEMATIC_REQUIRED") == "1":
                raise
            self.skipTest(f"schematic-maps plugin not available: {exc.code}")
        tracks = B.StagingTracks(B.staging_tracks())
        self.assertEqual(tracks.block_between("TOR36", "TO113", "t", "OS Switch 35a"), "OS Switch 35a")


class Blocks(unittest.TestCase):
    def test_jmri_blocks_and_the_short_track_rule(self):
        b = band()
        names = {("os", "b0:N1"): "OS Switch 1", ("track", "b0:w"): "West", ("track", "b0:s12"): "1-2"}
        with self.assertRaisesRegex(SystemExit, "block 1-2: .* holds blocks OS Switch 1, OS Switch 2a"):
            B.block_bindings(b, facts(), names)       # the staging track holds two blocks and none is named
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


def block(*trial):
    """A main level block row of the device map holding the schematic tracks `trial`."""
    return B.railroad.DeviceRow(level=2, layer="block", user_name="", trial_name=", ".join(trial))


def device():
    return B.DeviceMap(
        blocks={"OS Switch 101": block("OS Switch 101"),
                "OS Switch 103": block("OS Switch 103"),
                "Track 101-111": block("Track e24"),
                "Track 101-103": block("Track e28"),
                "Track 135-H1": block("Track e34", "Track e35")},
        sensors={"BS Switch 101": "IS:HART:C3:B:OS101", "BS Switch 103": "IS:HART:C3:B:OS103",
                 "BS 101-111": "IS:HART:C3:B:101-111"},
        planned={"BS Switch 101": "M2S3300", "BS 101-111": "M2S3306"})


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

    def test_virtual_and_planned_detectors(self):
        f = facts(device=device())
        self.assertEqual(B.virtual_sensor("OS Switch 101", f)["occupied"],
                         {"DECADDR": ":HART:C3:B:OS101", "JMRIPREFIX": "IS", "USER_NAME": "BS Switch 101",
                          "command": "close"})
        self.assertEqual(B.virtual_sensor("Track 101-111", f)["unoccupied"],
                         {"DECADDR": ":HART:C3:B:101-111", "JMRIPREFIX": "IS", "command": "throw"})
        self.assertEqual(B.planned_sensor("OS Switch 101", f)["occupied"],
                         {"DECADDR": "3300", "JMRIPREFIX": "M2S", "USER_NAME": "BS Switch 101", "command": "close"})
        self.assertEqual(B.planned_sensor("Track 101-111", f)["unoccupied"],
                         {"DECADDR": "3306", "JMRIPREFIX": "M2S", "command": "throw"})
        self.assertIsNotNone(B.virtual_sensor("OS Switch 103", f))      # a virtual sensor, no detector planned
        self.assertIsNone(B.planned_sensor("OS Switch 103", f))
        self.assertIsNone(B.virtual_sensor("OS Switch 225", f))         # not a device map block

    def test_the_device_map_reads_blocks_and_detectors(self):
        dm = B.load_device_map()
        self.assertEqual(set(dm.sensors), {B.bdm.occupancy_user(b) for b in dm.blocks})   # one per block
        self.assertEqual(len(dm.sensors), 125)
        self.assertTrue(all(dm.sensors[B.bdm.occupancy_user(b)] == B.bdm.block_sensor(b) for b in dm.blocks))
        self.assertEqual(len(dm.planned), 35)
        self.assertTrue(all(v.startswith("M2S") for v in dm.planned.values()))
        # Loop 2 and 225's corners b to d wait for wiring: a virtual sensor and no planned detector (owner, 2026-11-16)
        self.assertFalse({"BS 107 Loop 2", "BS Switch 225b", "BS Switch 225c", "BS Switch 225d"} & set(dm.planned))
        self.assertEqual(dm.blocks["Track 107-109"].trial, {"Track e19"})

    def test_a_block_missing_from_the_desk_is_checked_on_the_drawing(self):
        class FakeP:
            def __init__(self, blocks):
                self.blocks = blocks

            def find(self, k):
                return ("os", "b1:A") if k == ("track", "b1:e24") else k
        bands = dark_bands()
        bands[1][1]["strands"]["e28"] = dict(strand(("A", "C"), ("C", "A")), edge="e28", cm=3.4)
        bands[1][1]["strands"]["e24"]["cm"] = 398.1
        row = block
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
        """The committed bindings: the 107 Loop is two dark desk blocks, Loop 2 on its virtual detector; double crossover
        225 is a desk block per corner on its corner's detector, as in the Layout Editor (owner, 2026-11-17), and the
        middle of its X, OS Switch 225, has no detector."""
        got = json.loads(B.BINDINGS.read_text(encoding="utf-8"))
        loop = {e["name"]: e for e in got["blocks"].values() if "107 Loop" in e.get("name", "")}
        self.assertEqual({k: (v["occupied"]["JMRIPREFIX"] + v["occupied"]["DECADDR"], v["occupied"]["USER_NAME"],
                              v.get("_planned_occupied", {}).get("JMRIPREFIX")) for k, v in loop.items()},
                         {"Track 107 Loop 1": ("IS:HART:C3:B:107_Loop_1", "BS 107 Loop 1", "M2S"),
                          "Track 107 Loop 2": ("IS:HART:C3:B:107_Loop_2", "BS 107 Loop 2", None)})
        x225 = {e.get("name", k): e for k, e in got["blocks"].items() if e.get("name", k).startswith("OS Switch 225")}
        self.assertEqual({k: e.get("occupied", {}).get("USER_NAME") for k, e in x225.items()},
                         {"OS Switch 225": None, **{f"OS Switch 225{c}": f"BS Switch 225{c}" for c in "abcd"}})
        self.assertEqual({k: "_planned_occupied" in e for k, e in x225.items()},
                         {"OS Switch 225": False, "OS Switch 225a": True,
                          **{f"OS Switch 225{c}": False for c in "bcd"}})
        self.assertFalse([k for k in got["_main_upper_not_on_desk"] if k.startswith("OS Switch 225")])

    def test_main_and_upper_are_ctc(self):
        # CTC: CATS holds their signals and releases them (owner, 2026-11-17)
        self.assertEqual(B.MAIN_UPPER_DISCIPLINE, "CTC")

    def test_label_clashes_stop_the_desk(self):
        log = ["label 'S-1' at (4, 5) UPCENT crosses 1 track lines, signals or labels", "no room for label 'K-2'",
               "Main level: grid column -9 is not widened (a one-row slope from switch to switch crosses it), so ...",
               "mast 130LB: its gap moved 1 cell(s) along track e75"]
        self.assertEqual(B.label_clashes(log), log[:2])

    def test_desk_preferences(self):
        """The desks' window (the Windows box's screen, owner 2026-11-18), one cell per grid unit, a helix block on
        each band (owner, 2026-11-17) and the tighter rows between bands (owner, 2026-11-18) are the page's CATS
        preferences, which the plugin reads."""
        page = json.loads((B.pd.DATA / "main_upper.preferences.json").read_text(encoding="utf-8"))
        keys = ("cats_window", "cats_cells_per_unit", "cats_helix_blocks", "cats_band_gap", "cats_title_gap")
        self.assertEqual({k: page[k] for k in keys},
                         {"cats_window": [1900, 1020], "cats_cells_per_unit": 1, "cats_helix_blocks": "apart",
                          "cats_band_gap": 1, "cats_title_gap": 0})

    def test_every_main_and_upper_desk_block_reports_its_virtual_sensor(self):
        """Every desk block of main and upper is bound to its block's virtual sensor, which tables.xml holds under
        that name; only the middle of 225's X, a desk-only block, stays dark (owner, 2026-11-17)."""
        got = json.loads(B.BINDINGS.read_text(encoding="utf-8"))
        dm = B.load_device_map()
        sensors = B.railroad.read_tables(B.paths.TABLES_XML).sensors
        level = {e.get("name", k): e for k, e in got["blocks"].items()
                 if e.get("name", k) in dm.blocks or e.get("name", k) == "OS Switch 225"}
        self.assertGreater(len(level), 100)
        for name, e in sorted(level.items()):
            with self.subTest(block=name):
                if name == "OS Switch 225":
                    self.assertNotIn("occupied", e)
                    continue
                occ = e["occupied"]
                self.assertEqual(occ["JMRIPREFIX"] + occ["DECADDR"], B.bdm.block_sensor(name))
                self.assertEqual(sensors.get(occ["USER_NAME"]), B.bdm.block_sensor(name))


def level_band():
    """A main level band: a balloon loop from Switch 107 (legs B and C, one schematic track e33 drawn as two halves),
    Switch 109 joined to 107 by e19, crossover 119 (halves 119A and 119B joined C to C by e9), double crossover 225."""
    def s(src, dst, edge, cm=100.0, **kw):
        return dict(strand(src, dst), edge=edge, cm=cm, **kw)
    nodes = {
        "S107": node("107", "T1", {"A": "e19"}, {"B": "e33.0", "C": "e33.1"}),
        "S109": node("109", "T2", {"A": "e18"}, {"B": "e19", "C": "e20"}),
        "X1": node("119A", "T3", {"A": "e16"}, {"B": "e17", "C": "e9"}),
        "X2": node("119B", "T4", {"A": "e7", "C": "e9"}, {"B": "e8"}),
        "D": node("225", "T5", {"A": "e66", "B": "e80"}, {"C": "e71", "D": "e62"}, kind="dx"),
        "turn:e33": node("", "", {}, {0: "e33.0", 1: "e33.1"}, kind="turnR"),
    }
    strands = {
        "e33.0": s(("turn:e33", 0), ("S107", "B"), "e33", loop_half=1),
        "e33.1": s(("turn:e33", 1), ("S107", "C"), "e33", loop_half=2),
        "e19": s(("S107", "A"), ("S109", "B"), "e19"),
        "e9": s(("X1", "C"), ("X2", "C"), "e9"),
    }
    return {"nodes": nodes, "strands": strands}


def level_facts(**kw):
    f = facts(device=B.DeviceMap(blocks={
        "Track 107 Loop 1": block("Track e33 1"),
        "Track 107 Loop 2": block("Track e33 2"),
        "Track 107-109": block("Track e19")}))
    f.turnouts = {f"Switch {n}": f"IT:HART:C3:{n}" for n in (107, 109, 119, 225)}
    f.templates = {"Mast 2L": "double", "Mast 4RA": "single"}
    f.mast_system = {"Mast 2L": "IF$shsm:basic:two-searchlight(IH438)(IH439)",
                     "Mast 4RA": "IF$shsm:basic:one-low(IH436)",
                     "Mast 108LA": "IF$shsm:basic:one-low(IH:HART:C3:108LA)",
                     "Mast 108LB": "IF$shsm:basic:one-low(IH:HART:C3:108LB)",
                     "Mast 108R": "IF$shsm:basic:two-searchlight(IH:HART:C3:108R_Top)(IH:HART:C3:108R_Bottom)"}
    row = lambda mast, facing, system, heads: {"mast": mast, "switch": "107", "facing": facing,
                                               "protects": "OS Switch 107", "system_name": system,
                                               "heads": [(h, h) for h in heads]}
    f.level_masts = [row("Mast 108LA", "Track 107 Loop 1", f.mast_system["Mast 108LA"], ["IH:HART:C3:108LA"]),
                     row("Mast 108LB", "Track 107 Loop 2", f.mast_system["Mast 108LB"], ["IH:HART:C3:108LB"]),
                     row("Mast 108R", "Track 107-109", f.mast_system["Mast 108R"], ["IH:HART:C3:108R_Top",
                                                                                   "IH:HART:C3:108R_Bottom"])]
    for k, v in kw.items():
        setattr(f, k, v)
    return f


def level_bands():
    return [("Staging level", {"nodes": {}, "strands": {}}, {}), ("Main level", level_band(), {"mast_prefix": "Mast "})]


class LevelSwitches(unittest.TestCase):
    def test_each_switch_and_half_commands_its_internal_turnout_closed_on_leg_b(self):
        out = B.level_switch_bindings(level_bands(), level_facts(), 0)
        self.assertEqual(sorted(out), ["107", "109", "119A", "119B", "225"])
        b = out["119B"]
        self.assertEqual(b["normal"], "B")
        self.assertEqual(b["routes"]["B"]["ROUTECOMMAND"], {"DECADDR": ":HART:C3:119", "JMRIPREFIX": "IT",
                                                             "USER_NAME": "Switch 119", "command": "close"})
        self.assertEqual(b["routes"]["C"]["SELECTEDREPORT"]["command"], "throw")
        # a double crossover: one turnout moves its four points, B along the through tracks, C into the X
        self.assertEqual((out["225"]["normal"], out["225"]["routes"]["C"]["ROUTECOMMAND"]["USER_NAME"]),
                         ("B", "Switch 225"))

    def test_a_double_crossover_takes_a_block_per_corner_named_by_its_legs(self):
        # corners keyed by band leg, named by the Layout Editor corner each leg reaches (owner, 2026-11-17)
        legs = {"A": "C", "B": "D", "C": "A", "D": "B"}
        out = B.level_switch_bindings(level_bands(), level_facts(), 0, {"225": legs})
        self.assertEqual(out["225"]["corners"], {"A": "OS Switch 225c", "B": "OS Switch 225d", "C": "OS Switch 225a",
                                                 "D": "OS Switch 225b", "X": "OS Switch 225"})
        self.assertNotIn("corners", out["109"])
        self.assertNotIn("corners", B.level_switch_bindings(level_bands(), level_facts(), 0)["225"])
        with self.assertRaisesRegex(SystemExit, "double crossover 225: no corners found"):
            B.level_switch_bindings(level_bands(), level_facts(), 0, {})

    def test_a_turnout_that_is_not_internal_stops(self):
        for turnouts in ({}, {"Switch 109": "M2T1300"}):
            with self.subTest(turnouts=turnouts), self.assertRaisesRegex(SystemExit, "no internal turnout Switch"):
                f = level_facts()
                f.turnouts = {k: v for k, v in f.turnouts.items() if k != "Switch 109"} | turnouts
                B.level_switch_bindings(level_bands(), f, 0)

    def test_a_crossover_half_whose_thrown_leg_goes_elsewhere_stops(self):
        bands = level_bands()
        bands[1][1]["strands"]["e9"]["dst"] = ("S109", "C")
        with self.assertRaisesRegex(SystemExit, "switch 119A: a crossover half whose leg C"):
            B.level_switch_bindings(bands, level_facts(), 0)


class LevelMasts(unittest.TestCase):
    def test_masts_stand_on_their_facing_leg_at_their_switch(self):
        bands = level_bands()
        B.level_signals(bands, level_facts(), 0)
        sig = {s["mast"]: s for s in bands[1][2]["signals"]}
        self.assertEqual(sorted(sig), ["108LA", "108LB", "108R"])
        # the loop halves get their own edges, so each loop mast finds its own half (the plugin's mast_piece)
        self.assertEqual((sig["108LA"]["_edge"], sig["108LB"]["_edge"]), ("e33~1", "e33~2"))
        self.assertEqual(B.placeholder(bands[1][1]["strands"]["e33.1"]), "Track e33 2")
        self.assertEqual((sig["108R"]["_edge"], sig["108R"]["_toward_node"], sig["108R"]["toward"]),
                         ("e19", "S107", "107"))
        self.assertEqual((sig["108LA"]["dir"], sig["108R"]["dir"], sig["108R"]["heads"]), ("west", "east", 2))

    def test_a_loop_whose_edge_is_a_cut_piece_keeps_its_halves_apart(self):
        # a loop drawn from a connector's or helix's piece (e33x): its halves are not read as x/y pieces again
        bands = level_bands()
        for k in ("e33.0", "e33.1"):
            bands[1][1]["strands"][k]["edge"] = "e33x"
        B.level_signals(bands, level_facts(), 0)
        sig = {s["mast"]: s for s in bands[1][2]["signals"]}
        self.assertEqual((sig["108LA"]["_edge"], sig["108LB"]["_edge"]), ("e33x~1", "e33x~2"))
        strands = bands[1][1]["strands"]
        self.assertEqual((B.placeholder(strands["e33.0"]), B.placeholder(strands["e33.1"])),
                         ("Track e33 1", "Track e33 2"))
        # the plugin's mast_piece takes the pieces whose edge is the mast's, or it plus x or y: one half each
        for mast, half in (("108LA", "e33.0"), ("108LB", "e33.1")):
            e = sig[mast]["_edge"]
            self.assertEqual([k for k, t in strands.items() if t["edge"] in (e, e + "x", e + "y")], [half])

    def test_a_mast_at_no_leg_or_two_stops(self):
        f = level_facts()
        f.level_masts[2] = dict(f.level_masts[2], facing="Track 105-109")
        with self.assertRaisesRegex(SystemExit, "Mast 108R: Switch 107 has 0 legs on track Track 105-109"):
            B.level_signals(level_bands(), f, 0)

    def test_templates_by_appearance_type_and_the_tables_mast(self):
        bands, f = level_bands(), level_facts()
        B.level_signals(bands, f, 0)
        self.assertEqual(B.level_mast_bindings(bands, f, 0),
                         {"108LA": {"name": "Mast 108LA", "template": "single"},
                          "108LB": {"name": "Mast 108LB", "template": "single"},
                          "108R": {"name": "Mast 108R", "template": "double"}})
        f.mast_system["Mast 108R"] = "IF$shsm:basic:one-low(IH1)"
        with self.assertRaisesRegex(SystemExit, "Mast 108R: tables.xml has IF.shsm:basic:one-low.IH1."):
            B.level_mast_bindings(bands, f, 0)
        f = level_facts(templates={"Mast 4RA": "single", "Mast 108LA": "double"})      # both one-low
        with self.assertRaisesRegex(SystemExit, "gives one-low masts two templates"):
            B.template_by_type(f)

    def test_a_row_not_drawn_stops(self):
        bands, f = level_bands(), level_facts()
        B.level_signals(bands, f, 0)
        bands[1][2]["signals"] = [s for s in bands[1][2]["signals"] if s["mast"] != "108LB"]
        with self.assertRaisesRegex(SystemExit, "main and upper masts not on the desk: Mast 108LB"):
            B.level_mast_bindings(bands, f, 0)


class CommittedMainAndUpper(unittest.TestCase):
    """The committed bindings and desk against the release candidate tables (every name bound must be in it)."""

    @classmethod
    def setUpClass(cls):
        if not B.TABLES_CANDIDATE.exists():
            raise unittest.SkipTest("no release candidate tables (make panels writes them)")
        from hartlib import tables
        root = tables.read(B.TABLES_CANDIDATE)
        cls.turnouts = {tables.system_name(t): tables.user_name(t) for t in tables.turnouts(root)}
        cls.sensors = {tables.system_name(s): tables.user_name(s) for s in tables.sensors(root)}
        cls.masts = {tables.user_name(m) for m in tables.masts(root)}
        cls.bound = json.loads(B.BINDINGS.read_text(encoding="utf-8"))

    def test_every_bound_name_is_in_the_candidate_tables(self):
        for key, e in self.bound["switches"].items():
            for leg in e["routes"].values():
                for io in leg.values():
                    with self.subTest(switch=key):
                        system = io["JMRIPREFIX"] + io["DECADDR"]
                        self.assertEqual(self.turnouts.get(system), io["USER_NAME"])
        for key, e in self.bound["blocks"].items():
            if "occupied" in e:
                with self.subTest(block=key):
                    io = e["occupied"]
                    self.assertEqual(self.sensors.get(io["JMRIPREFIX"] + io["DECADDR"]), io["USER_NAME"])
        self.assertLessEqual({e["name"] for e in self.bound["masts"].values()}, self.masts)

    def test_main_and_upper_turnouts_and_masts_are_bound(self):
        level = {k: e for k, e in self.bound["switches"].items()
                 if e["routes"]["B"]["ROUTECOMMAND"]["JMRIPREFIX"] == B.LEVEL_TURNOUT_PREFIX}
        numbers = {B.bdm.base(k) for k in level}
        internal = {u.removeprefix("Switch ") for s, u in self.turnouts.items() if s.startswith(B.LEVEL_TURNOUT)}
        self.assertEqual(numbers, internal)                         # double crossover 225 too
        self.assertEqual(len(numbers), 41)
        self.assertEqual({e["normal"] for e in level.values()}, {"B"})
        names = {e["name"] for e in self.bound["masts"].values()}
        self.assertLessEqual(B.level_masts.names(), names)
        self.assertEqual(len(B.level_masts.names()), 41)

    def test_the_helix_is_joined_on_the_desk_with_a_block_on_each_level(self):
        """The plugin joins each helix track drawn on staging and on main or upper logically (SHARED), so a train runs
        from staging to the main and upper levels on the desk; the join parts the blocks (owner, 2026-11-17):
        staging's McKees Rocks and McKeesport, and Track 135-H1 and 135-H2 with their own planned detectors."""
        root = ET.parse(B.OUT).getroot()
        self.assertEqual(len(list(root.iter("SHARED"))), 8)        # two helix tracks and two links, both ends
        at_join = sorted(se.find("BLOCK").get("NAME") for se in root.iter("SEC_EDGE")
                         if se.find("SHARED") is not None and se.find("BLOCK") is not None)
        self.assertEqual(at_join, ["Track 135-H1", "Track 135-H2", "Track McKees Rocks", "Track McKeesport"])
        level = {e.get("name"): e for e in self.bound["blocks"].values()}
        for name in ("Track 135-H1", "Track 135-H2"):
            with self.subTest(block=name):
                self.assertEqual(level[name]["_planned_occupied"]["USER_NAME"], "BS " + name.removeprefix("Track "))
                self.assertEqual(level[name]["occupied"]["USER_NAME"], "BS " + name.removeprefix("Track "))
                self.assertNotIn(name, self.bound["_main_upper_not_on_desk"])


class LevelSensorsFromTheDeviceMap(unittest.TestCase):
    def test_the_bindings_need_no_level_sensor_in_tables_xml(self):
        """make panels builds the desks before build_layout_le.py adds a new block's sensor to the tables, so the
        desk binds each main and upper block from the device map alone (check_layout_facts.py checks it against
        tables.xml afterwards): the bindings are the same with no main or upper sensor in the tables."""
        import contextlib
        import io
        cats = plugin_cats()
        sheet = B.pd.solved_sheet(B.plugin_modules(B.pd.plugin())[1])
        bands = B.name_loop_halves(sheet.bands)
        F = B.load_facts()
        B.level_signals(bands, F, B.bound_index(bands))
        F.sensors = {u: sn for u, sn in F.sensors.items() if not B.level_devices.is_block_sensor(sn)}
        with contextlib.redirect_stdout(io.StringIO()):
            got = B.bindings(bands, cats, F, B.desk_options(cats, sheet.opts, bands),
                             sheet.opts)
        self.assertEqual(json.dumps(got, indent=1, sort_keys=True) + "\n", B.BINDINGS.read_text(encoding="utf-8"))


def fit():
    """The cells the desks must fit, from the page's cats_window."""
    return desk_options()["fit"]


def desk_options():
    cats = plugin_cats()                                   # skips without the plugin
    s = B.pd.solved_sheet(B.plugin_modules(B.pd.plugin())[1])
    return B.desk_options(cats, s.opts, s.bands)


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
        out = ET.fromstring(B.dress(cats, self.doc((2, "STAGING")), header, plate, "ABS", fit()).split("\n", 1)[1])
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
        out = ET.fromstring(B.dress(cats, doc, no_colours, plate, "CTC", fit()).split("\n", 1)[1])
        self.assertEqual([c.get("COLORKEY") for c in out.findall("COLORDEFINITION")], ["PLUGIN"])
        out = ET.fromstring(B.dress(cats, self.doc((2, "S")), header, plate, "CTC", fit()).split("\n", 1)[1])
        self.assertNotIn("PLUGIN", [c.get("COLORKEY") for c in out.findall("COLORDEFINITION")])
        odd = self.doc((2, "STAGING"))
        odd.insert(1, ET.Element("MYSTERY"))
        with self.assertRaisesRegex(SystemExit, "elements MYSTERY, which ORDER does not place"):
            B.dress(cats, odd, header, plate, "CTC", fit())

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
            B.dress(cats, self.doc((15, "X")), header, plate, "CTC", fit())
        with self.assertRaisesRegex(SystemExit, "runs into the label"):
            B.dress(cats, self.doc((2, "A VERY LONG TITLE THAT RUNS FAR TO THE RIGHT")), header, plate, "CTC", fit())


if __name__ == "__main__":
    unittest.main()
