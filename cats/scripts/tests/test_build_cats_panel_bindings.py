"""tools/schematic/build_cats_panel.py: how the staging bindings come from the facts, on a tiny made-up band.

The band: Switch 1 (one OS) leads by an unnamed short track to Switch 2's half 2a; Switch 2 is a crossover of two
nodes (2a and 2b, its halves told apart by the named tracks they touch or by elimination); 2b leads through a
turnback to the named half Loop.
"""
from __future__ import annotations

import contextlib
import io
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
import cats_panel_facts  # noqa: E402  template_by_type looks appearance_templates up here
from layout_facts import Leg, Switch  # noqa: E402


def node(label, alias, ins, outs, kind="switch"):
    return {"kind": kind, "label": label, "alias": alias, "ins": ins, "outs": outs}


def strand(src, dst, name="", trial=None):
    """A drawn strand; `trial` its switch-and-leg trial key, as cats_panel.name_loop_halves keys a main or upper
    strand (staging_device_map.band_refs)."""
    return {"src": src, "dst": dst, "name": name, **({"trial": trial} if trial else {})}


def named(b) -> dict:
    """The name store's names of a hand-built band's strands, as cats_panel.staging_names gives the real band's: the
    test bands keep them in their strands' `name`, which the code under test no longer reads."""
    return {sid: st["name"] for sid, st in b["strands"].items() if st.get("name")}


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
        2: Switch(2, "1", "TO2", True, 2, True, (Leg("OS Switch 2a", "Track Main", "OS Switch 2b", "os:2:A-1B"),
                                                 Leg("OS Switch 2b", "Track East", "OS Switch 2a", "os:2:A-loop"))),
    }
    occupancy = {n: (str(i), "BS " + n) for i, n in enumerate(
        ["OS Switch 1", "OS Switch 2a", "OS Switch 2b", "Track West", "Track Yard", "Track Main", "Track East",
         "Track Loop"])}
    f = B.Facts(switches, {"TO1": ("11", "Switch 1"), "TO2": ("12", "Switch 2")}, occupancy, {},
                B.StagingTracks(CHAINS), {"Mast 1L": "single"}, {"Mast 1L"},
                half_letters={("1", "os:2:A-1B"): "a", ("1", "os:2:A-loop"): "b"})
    for k, v in kw.items():
        setattr(f, k, v)
    return f


class OsBlocks(unittest.TestCase):
    def test_by_named_track_then_by_elimination(self):
        b = band()
        self.assertEqual(B.os_blocks(b, facts(), named(b)),
                         {"N1": "OS Switch 1", "N2a": "OS Switch 2a", "N2b": "OS Switch 2b"})
        b["strands"]["e"]["name"] = ""            # 2b touches no named track of its row: the row left over
        b["strands"]["e"]["dst"] = ("END:e", "E")
        self.assertEqual(B.os_blocks(b, facts(), named(b))["N2b"], "OS Switch 2b")

    def test_two_nodes_on_one_row_stop(self):
        b = band()
        b["strands"]["e"]["name"] = "Main"        # both halves touch Track Main
        with self.assertRaisesRegex(B.CatsPanelError, "would both be OS Switch 2a"):
            B.os_blocks(b, facts(), named(b))

    def test_a_switch_not_in_the_facts_stops(self):
        b = band()
        b["nodes"]["N1"]["label"] = "9"
        with self.assertRaisesRegex(B.CatsPanelError, "not in switches.csv"):
            B.os_blocks(b, facts(), named(b))


class Dest(unittest.TestCase):
    def test_named_track_next_switch_and_through_a_turnback(self):
        b = band()
        os_of = B.os_blocks(b, facts(), named(b))
        self.assertEqual(B.dest(b, os_of, "N1", "C", None, named(b)), "Track Yard")
        self.assertEqual(B.dest(b, os_of, "N1", "B", None, named(b)), "OS Switch 2a")
        self.assertEqual(B.dest(b, os_of, "N2b", "A", None, named(b)), "Track Loop")

    def test_a_track_to_nowhere_stops(self):
        b = band()
        os_of = B.os_blocks(b, facts(), named(b))
        b["strands"]["loop1"]["name"] = ""
        with self.assertRaisesRegex(B.CatsPanelError, "reaches no named track or switch"):
            B.dest(b, os_of, "N2b", "A", None, named(b))

    def test_a_turnback_loop_stops_instead_of_hanging(self):
        b = band()
        os_of = B.os_blocks(b, facts(), named(b))
        b["strands"]["loop1"] = strand(("turn", 1), ("turn", 0))
        b["nodes"]["turn"]["outs"] = {0: "loop0", 1: "loop1"}
        with self.assertRaises(B.CatsPanelError):
            B.dest(b, os_of, "N2b", "A", None, named(b))


class Switches(unittest.TestCase):
    def test_routes_by_closed_and_thrown_leg(self):
        b = band()
        out = B.switch_bindings(b, facts(), B.os_blocks(b, facts(), named(b)), named(b))
        self.assertEqual(set(out), {"1", "2/2a", "2/2b"})
        one = out["1"]                            # closed leg OS Switch 2a is leg B
        self.assertEqual((one["block"], one["normal"]), ("OS Switch 1", "B"))
        self.assertEqual(one["routes"]["B"]["ROUTECOMMAND"]["command"], "close")
        self.assertEqual(one["routes"]["C"]["SELECTEDREPORT"]["command"], "throw")
        self.assertEqual(out["2/2a"]["normal"], "C")   # CATS inverted: normal is the thrown leg
        self.assertEqual((out["2/2a"]["label"], out["2/2b"]["label"]), ("2A", "2B"))   # crossover halves lettered
        self.assertNotIn("label", out["1"])

    def test_a_crossover_half_is_lettered_by_its_id_not_its_name(self):
        # the letters are the crossover_half rows', by the half's OS block ID: an owner's name for
        # the half (OS Barn West, OS X) changes no label, and its plate is its number and letter
        letters = {("1", "os:7:A-13C"): "a", ("1", "os:7:A-5B"): "b"}
        for a, b in (("OS Switch 7", "OS Switch 7b"), ("OS Barn West", "OS Switch 7b"), ("OS Switch 7", "OS X"),
                     ("OS Switch 7b", "OS Switch 7a")):        # names swapped: label and plate still by the ID
            sw = Switch(7, "1", "TO7", False, 7, True, (Leg(a, "Track A", b, "os:7:A-13C"),
                                                         Leg(b, "Track B", a, "os:7:A-5B")))
            with self.subTest(names=(a, b)):
                self.assertEqual([B.half_label(sw, leg, letters) for leg in sw.legs], ["7A", "7B"])
                plates = B.os_plates(facts(switches={7: sw}, half_letters=letters))
                self.assertEqual((plates[a], plates[b]), ("7" if a == "OS Switch 7" else "7a", "7b"))
                self.assertEqual([plates[a][-1:].upper(), plates[b][-1:].upper()],
                                 ["7" if a == "OS Switch 7" else "A", "B"])
        sw = Switch(7, "1", "TO7", False, 7, True, (Leg("OS Barn West", "Track A", "OS Switch 7b", "os:7:A-13C"),
                                                     Leg("OS Switch 7b", "Track B", "OS Barn West", "os:7:A-5B")))
        self.assertEqual(B.os_plates(facts(switches={7: sw}, half_letters=letters)),
                         {"OS Barn West": "7a", "OS Switch 7b": "7b"})
        with self.assertRaisesRegex(B.CatsPanelError, "no crossover_half row"):
            B.half_label(sw, sw.legs[0], {("1", "os:7:A-5B"): "b"})
        one = Switch(19, "1", "TO19", False, 19, True, (Leg("OS South 19", "Track A", "Track B", "os:19"),))
        self.assertEqual(B.os_plates(facts(switches={19: one})), {"OS South 19": "19"})   # a renamed OS block

    def test_fit_comes_from_the_window(self):
        o = desk_options()
        self.assertEqual((o["window"], o["fit"]), ((1920, 1032), (63, 31)))   # (1920 - 20) // 30, (1032 - 100) // 30
        with self.assertRaisesRegex(B.CatsPanelError, "no cats_window"):
            B.desk_options(plugin_cats(), {}, [])
        with self.assertRaisesRegex(B.CatsPanelError, "the desks need \"one\""):
            B.desk_options(plugin_cats(), {"cats_window": [1920, 1032], "cats_helix_blocks": "apart"}, [])

    def test_legs_disagreeing_with_the_switch_facts_stop(self):
        f = facts()
        f.switches[1] = Switch(1, "1", "TO1", False, 1, True, (Leg("OS Switch 1", "Track Main", "Track Yard"),))
        b = band()
        with self.assertRaisesRegex(B.CatsPanelError, "switches.csv says"):
            B.switch_bindings(b, f, B.os_blocks(b, f, named(b)), named(b))


class StagingTracks(unittest.TestCase):
    def test_a_track_of_one_block_is_that_block(self):
        self.assertEqual(B.StagingTracks(CHAINS).block_between("TO3", "TO2", "t"), "Track Main")

    def test_no_track_two_tracks_or_a_bumper_stop(self):
        tracks = B.StagingTracks(CHAINS)
        with self.assertRaisesRegex(B.CatsPanelError, "no staging tracks join TO2 and TO9"):
            tracks.block_between("TO2", "TO9", "t")
        with self.assertRaisesRegex(B.CatsPanelError, "no staging tracks join"):
            tracks.block_between("TO1", "END", "t")               # a track to a bumper joins no two switches
        twice = B.StagingTracks(CHAINS + [{"ends": [("TO2", "C"), ("TO1", "D")], "blocks": ["X"]}])
        with self.assertRaisesRegex(B.CatsPanelError, "2 staging tracks join"):
            twice.block_between("TO1", "TO2", "t")

    def test_a_track_of_several_blocks_stops(self):
        # one desk cell takes one block: the device map must give the track to the block its gap leaves it in
        with self.assertRaisesRegex(B.CatsPanelError, "holds blocks OS Switch 1, OS Switch 2a; give it to the one"):
            B.StagingTracks(CHAINS).block_between("TO1", "TO2", "t")

    def test_the_35_37_track_is_its_own_part_block_on_the_staging_track(self):
        # the gap is at Switch 37's points (owner, 2026-11-19): the whole track is Track 35-37, a part of OS Switch
        # 35a and a JMRI block of its own (owner, 2026-11-20)
        try:                    # the staging tracks need the plugin's solve: skipped without it, as the --check scripts
            B.pd.plugin()
        except B.pd.PluginMissing as exc:
            if os.environ.get("SCHEMATIC_REQUIRED") == "1":
                raise
            self.skipTest(f"schematic-maps plugin not available: {exc}")
        tracks = B.StagingTracks(B.staging_tracks())
        self.assertEqual(tracks.block_between("TOR36", "TO113", "t"), "Track 35-37")


class Blocks(unittest.TestCase):
    def test_jmri_blocks_and_the_short_track_rule(self):
        b = band()
        names = {("os", "b0:N1"): "OS Switch 1", ("track", "b0:w"): "West", ("track", "b0:s12"): "1-2"}
        with self.assertRaisesRegex(B.CatsPanelError, "block 1-2: .* holds blocks OS Switch 1, OS Switch 2a"):
            B.block_bindings(b, facts(), names, named(b))       # the staging track holds two blocks
        F = facts()
        F.layout = B.StagingTracks([{"ends": [("TO1", "C"), ("TO2", "A")], "blocks": ["OS Switch 1"]}])
        out = B.block_bindings(b, F, names, named(b))
        self.assertNotIn("name", out["OS Switch 1"])
        self.assertEqual(out["OS Switch 1"]["occupied"]["USER_NAME"], "BS OS Switch 1")
        self.assertEqual(out["West"]["name"], "Track West")
        self.assertEqual(out["1-2"], {"name": "OS Switch 1"})

    def test_a_jmri_block_with_no_detector_stops(self):
        """No staging block is bound by name alone any more (the helix tracks have their detectors, 2026-11-20): a
        block JMRI holds with no sensor stops the build rather than draw a block that never shows occupied."""
        F = facts()
        F.occupancy.pop("Track West")
        with self.assertRaisesRegex(B.CatsPanelError, "block West: no JMRI block West or Track West"):
            B.block_bindings(band(), F, {("track", "b0:w"): "West"}, named(band()))

    def test_a_helix_track_takes_its_helix_block(self):
        helix = {"Helix Inner": "Track Helix Inner"}
        self.assertEqual(B.track_block("Helix Inner", helix), "Track Helix Inner")
        self.assertEqual(B.track_block("K-2", helix), "Track K-2")
        b = {"strands": {"h": {"name": "Helix Inner"}, "k": {"name": "K-2"}}}
        self.assertEqual(B.helix_block(("track", "b0:h"), {"Helix Inner": {"block": "Track Helix Inner"}}, named(b)),
                         "Track Helix Inner")
        self.assertIsNone(B.helix_block(("track", "b0:k"), {"Helix Inner": {"block": "Track Helix Inner"}}, named(b)))
        self.assertIsNone(B.helix_block(("os", "b0:N1"), {}, named(b)))

    def test_a_block_with_no_jmri_block_that_is_no_short_track_stops(self):
        b = band()
        for names in ({("track", "b0:m"): "Mainline"},                 # named track, not in JMRI
                      {("track", "b0:loop0"): "2-turn"},               # unnamed, but not between two switches
                      {("os", "b0:N1"): "OS 1"}):                      # an OS block JMRI does not have
            with self.subTest(names=names):
                b["strands"]["m"]["name"] = "Mainline"
                with self.assertRaisesRegex(B.CatsPanelError, "not a short unnamed track between two switches"):
                    B.block_bindings(b, facts(), names, named(b))


class Masts(unittest.TestCase):
    def test_drawn_masts_once_each(self):
        sig = {"mast": "1L", "kind": "field"}
        opts = {"mast_prefix": "Mast ", "signals": [sig, {"mast": "9V", "kind": "virtual"}]}
        self.assertEqual(B.mast_bindings(opts, facts()), {"1L": {"name": "Mast 1L", "template": "single"}})
        with self.assertRaisesRegex(B.CatsPanelError, "listed twice"):
            B.mast_bindings(dict(opts, signals=[sig, dict(sig)]), facts())
        with self.assertRaisesRegex(B.CatsPanelError, "not a JMRI mast"):
            B.mast_bindings(dict(opts, signals=[{"mast": "2R", "kind": "planned"}]), facts())


class StubCats:
    """The plugin's label_of, for the main and upper naming."""
    @staticmethod
    def label_of(bands, key):
        tag, n = key[1].split(":", 1)
        return bands[int(tag[1:])][1]["nodes"][n].get("label") or ""


def block(*trial):
    """A main level block row of the device map holding the schematic tracks `trial`."""
    return B.railroad.DeviceRow(level=2, layer="block", user_name="", role="track", trial_name=", ".join(trial))


def occupancy(user, jmri, block, role, planned=""):
    """A main level occupancy row: the block it serves (its blocks column), its virtual sensor and planned detector."""
    return B.railroad.DeviceRow(level=2, layer="occupancy", user_name=user, role=role, jmri_name=jmri,
                                system_name=planned, blocks=block)


def device():
    rows = [occupancy("BS Switch 101", "IS:HART:C3:B:OS101", "OS Switch 101", "os", "M2S3300"),
            occupancy("BS Switch 103", "IS:HART:C3:B:OS103", "OS Switch 103", "os"),
            occupancy("BS 101-111", "IS:HART:C3:B:101-111", "Track 101-111", "track", "M2S3306")]
    return B.DeviceMap(
        rows=rows,
        blocks={"OS Switch 101": block("OS Switch 101"),
                "OS Switch 103": block("OS Switch 103"),
                "Track 101-111": block("Track 101BC-end"),
                "Track 101-103": block("Track 101AC-103AA"),
                "Track 135-H1": block("Track 101AB-end #1", "Track 101AB-end #2")})


def dark_bands():
    nodes = {"A": node("101A", "", {}, {}), "B": node("101B", "", {}, {}), "C": node("103A", "", {}, {}),
             "END": node("", "", {}, {}, kind="end")}
    strands = {"e24": dict(strand(("B", "C"), ("END", "E"), trial="Track 101BC-end"), edge="e24"),
               "e34x": dict(strand(("A", "B"), ("END", "E"), trial="Track 101AB-end #1"), edge="e34x"),
               "e99": dict(strand(("A", "B"), ("END", "E"), trial="Track 101AB-end #3"), edge="e99"),
               "e77": dict(strand(("A", "C"), ("B", "C"), trial="Track 101AC-101BC"), edge="e77")}
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
        with self.assertRaisesRegex(B.CatsPanelError, "in no device map block rows"):
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
        occ = dm.occupancy
        self.assertEqual(set(occ), set(dm.blocks))                          # one per block
        self.assertEqual(len(occ), 97)     # Track 227-241 two blocks (APB B92/B93); the 25 links are parts
        self.assertTrue(all(occ[b].user_name == B.bdm.occupancy_user(b) for b in dm.blocks))
        self.assertTrue(all(occ[b].jmri_name == B.bdm.block_sensor(b) for b in dm.blocks))
        planned = {r.user_name: r.system_name for r in occ.values() if r.system_name}
        self.assertEqual(len(planned), 36)        # 227-241 2 on Block 41-4 since 2026-11-20
        self.assertTrue(all(v.startswith("M2S") for v in planned.values()))
        # Loop 2 and 225's corners b to d wait for wiring: a virtual sensor and no planned detector (owner, 2026-11-16)
        self.assertFalse({"BS 107 Loop 2", "BS Switch 225b", "BS Switch 225c", "BS Switch 225d"} & set(planned))
        self.assertEqual(dm.blocks["Track 107-109"].trial, {"Track 107A-109B"})

    def test_a_block_missing_from_the_desk_is_checked_on_the_drawing(self):
        class FakeP:
            def __init__(self, blocks):
                self.blocks = blocks

            def find(self, k):
                return ("os", "b1:A") if k == ("track", "b1:e24") else k
        bands = dark_bands()
        bands[1][1]["strands"]["e28"] = dict(strand(("A", "C"), ("C", "A"), trial="Track 101AC-103AA"), edge="e28",
                                              cm=3.4)
        bands[1][1]["strands"]["e24"]["cm"] = 398.1
        row = block
        self.assertEqual(B.inside_os(bands, FakeP({}), 0, "Track 101-103", row("Track 101AC-103AA")),
                         "inside its switches' OS blocks on the desk (3.4 cm, too short at one cell per grid unit "
                         "for a block)")
        # a track key joined to an OS block counts as inside it; a long one says why it has no block
        bands[1][1]["strands"]["e24"] = dict(strand(("B", "C"), ("C", "B"), trial="Track 101BC-103AB"), edge="e24",
                                              cm=398.1)
        self.assertIn("398.1 cm, too short at one cell per grid unit",
                      B.inside_os(bands, FakeP({("track", "b1:e24"): None}), 0, "Track 101-111",
                                  row("Track 101BC-103AB")))
        with self.assertRaisesRegex(B.CatsPanelError, "Track X: its schematic track e28 is a desk block"):
            B.inside_os(bands, FakeP({("track", "b1:e28"): None}), 0, "Track X", row("Track 101AC-103AA"))
        with self.assertRaisesRegex(B.CatsPanelError, "Track Y: its schematic track e99 has no desk block and does not run "
                                    "between switches"):
            B.inside_os(bands, FakeP({}), 0, "Track Y", row("Track 101AB-end #3"))      # e99 ends at a bumper
        with self.assertRaisesRegex(B.CatsPanelError, "Track Z: the device map's tracks .* are not all drawn"):
            B.inside_os(bands, FakeP({}), 0, "Track Z", row("Track 101AC-103AA", "Track 500A-501A"))

    def test_staging_and_dark_blocks_never_take_one_name(self):
        B.check_apart({"West": {"name": "Track West"}}, {"OS 101": {"name": "OS Switch 101"}})
        with self.assertRaisesRegex(B.CatsPanelError, "share panel names West"):
            B.check_apart({"West": {}}, {"West": {"name": "Track 1-2"}})
        with self.assertRaisesRegex(B.CatsPanelError, "would both be Track West"):
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
        """The desks' window (the layout hosts' 1920 x 1080 screen less a 48 px taskbar, owner 2026-11-21, derived
        from host_screen as the Layout Editor panel's is), one cell per grid unit, each helix track one block over
        both bands (owner, 2026-11-20) and the tighter rows between bands (owner, 2026-11-18) are the page's CATS
        preferences, which the plugin reads."""
        page = B.pd.page_prefs().read()
        keys = ("cats_cells_per_unit", "cats_helix_blocks", "cats_band_gap", "cats_title_gap")
        self.assertEqual({k: page[k] for k in keys},
                         {"cats_cells_per_unit": 1, "cats_helix_blocks": "one", "cats_band_gap": 1, "cats_title_gap": 0})
        self.assertEqual(page["host_screen"], {"size": [1920, 1080], "taskbar": 48})
        self.assertNotIn("cats_window", page)                 # derived, never written: host_screen is the one source
        s = B.pd.solved_sheet(B.plugin_modules(B.pd.plugin())[1])
        self.assertEqual((s.opts["cats_window"], s.opts["le_window"]), ([1920, 1032], [1920, 1032]))

    def test_every_main_and_upper_desk_block_reports_its_virtual_sensor(self):
        """Every desk block of main and upper is bound to its block's virtual sensor, which tables.xml holds under
        that name; only the middle of 225's X, a desk-only block, stays dark (owner, 2026-11-17)."""
        got = json.loads(B.BINDINGS.read_text(encoding="utf-8"))
        dm = B.load_device_map()
        sensors = B.railroad.read_tables(B.paths.TABLES_XML).sensors
        level = {e.get("name", k): e for k, e in got["blocks"].items()
                 if e.get("name", k) in dm.blocks or e.get("name", k) == "OS Switch 225"}
        self.assertGreater(len(level), 90)     # the links are parts since step 5 part 2: not device map blocks
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
        "e33.0": s(("turn:e33", 0), ("S107", "B"), "e33", loop_half=1, trial="Track 107B-107C #1"),
        "e33.1": s(("turn:e33", 1), ("S107", "C"), "e33", loop_half=2, trial="Track 107B-107C #2"),
        "e19": s(("S107", "A"), ("S109", "B"), "e19", trial="Track 107A-109B"),
        "e9": s(("X1", "C"), ("X2", "C"), "e9", trial="Track 119AC-119BC"),
    }
    return {"nodes": nodes, "strands": strands}


def level_facts(**kw):
    f = facts(device=B.DeviceMap(blocks={
        "Track 107 Loop 1": block("Track 107B-107C #1"),
        "Track 107 Loop 2": block("Track 107B-107C #2"),
        "Track 107-109": block("Track 107A-109B")}))
    f.turnouts = {f"Switch {n}": f"IT:HART:C3:{n}" for n in (107, 109, 119, 225)}
    f.templates = {"Mast 2L": "double", "Mast 4RA": "single"}
    f.mast_system = {"Mast 2L": "IF$shsm:basic:two-searchlight(IH438)(IH439)",
                     "Mast 4RA": "IF$shsm:basic:one-low(IH436)",
                     "Mast 108LA": "IF$shsm:basic:one-low(IH:HART:C3:108LA)",
                     "Mast 108LB": "IF$shsm:basic:one-low(IH:HART:C3:108LB)",
                     "Mast 108R": "IF$shsm:basic:two-searchlight(IH:HART:C3:108R_Top)(IH:HART:C3:108R_Bottom)"}
    row = lambda mast, facing, system, heads: {"mast": mast, "switch": "107", "facing": facing,
                                               "protects": "OS Switch 107", "system_name": system,
                                               "dir": "east" if mast.endswith("R") else "west",
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
        with self.assertRaisesRegex(B.CatsPanelError, "double crossover 225: no corners found"):
            B.level_switch_bindings(level_bands(), level_facts(), 0, {})

    def test_a_switch_binds_the_turnout_tables_xml_holds_and_stops_on_none(self):
        """The desk takes the turnout tables.xml holds for Switch <n>, its device-master row's bean (naming-layers
        step 11): a row swapped to a physical turnout (ADR-028) binds that one; no turnout stops."""
        f = level_facts()
        f.turnouts = dict(f.turnouts, **{"Switch 109": "M2T1300"})
        cmd = B.level_switch_bindings(level_bands(), f, 0)["109"]["routes"]["B"]["ROUTECOMMAND"]
        self.assertEqual(("M2T", "1300"), (cmd["JMRIPREFIX"], cmd["DECADDR"]))
        f.turnouts = {k: v for k, v in f.turnouts.items() if k != "Switch 109"}
        with self.assertRaisesRegex(B.CatsPanelError, "tables.xml has no turnout Switch 109"):
            B.level_switch_bindings(level_bands(), f, 0)

    def test_a_crossover_half_whose_thrown_leg_goes_elsewhere_stops(self):
        bands = level_bands()
        bands[1][1]["strands"]["e9"]["dst"] = ("S109", "C")
        with self.assertRaisesRegex(B.CatsPanelError, "switch 119A: a crossover half the plugin pairs with no other half"):
            B.level_switch_bindings(bands, level_facts(), 0)

    def test_a_half_with_an_added_branch_is_still_a_half(self):
        # "119A*": a half with a branch added (the * mark) is checked as a half all the same
        bands = level_bands()
        bands[1][1]["nodes"]["X1"]["label"] = "119A*"
        bands[1][1]["strands"]["e9"]["dst"] = ("S109", "C")
        with self.assertRaisesRegex(B.CatsPanelError, r"switch 119A\*: a crossover half the plugin pairs with no other half"):
            B.level_switch_bindings(bands, level_facts(), 0)

    def test_a_half_joined_by_its_leg_b_is_closed_on_leg_c(self):
        # the plan joins 121 and 125's halves leg C to leg B (AnyRail's leg B of T1 and T14 is the diagonal): the
        # half joined by leg B is thrown on B, so one turnout puts both halves on their through tracks closed
        bands = level_bands()
        band = bands[1][1]
        band["nodes"]["X2"] = node("119B", "T4", {"A": "e7", "B": "e9"}, {"C": "e8"})
        band["strands"]["e9"] = dict(strand(("X1", "C"), ("X2", "B")), edge="e9", cm=10.7)
        out = B.level_switch_bindings(bands, level_facts(), 0)
        self.assertEqual((out["119A"]["normal"], out["119B"]["normal"]), ("B", "C"))
        self.assertEqual(out["119B"]["routes"]["C"]["ROUTECOMMAND"]["command"], "close")
        self.assertEqual(out["119B"]["routes"]["B"]["ROUTECOMMAND"]["command"], "throw")

    def test_halves_joined_by_two_tracks_stop_with_the_plugins_reason(self):
        # a run-around between two lettered halves: the plugin pairs them as no crossover, so the build says why
        bands = level_bands()
        band = bands[1][1]
        band["nodes"]["X2"] = node("119B", "T4", {"A": "e7", "B": "e10"}, {"C": "e9"})
        band["strands"]["e10"] = dict(strand(("X1", "B"), ("X2", "B")), edge="e10", cm=10.0)
        with self.assertRaisesRegex(B.CatsPanelError, "switch 119A: a crossover half the plugin pairs with no other half"
                                                ".*joined by 2 tracks"):
            B.level_switch_bindings(bands, level_facts(), 0)


class LevelMasts(unittest.TestCase):
    def test_masts_stand_on_their_facing_leg_at_their_switch(self):
        bands = level_bands()
        B.level_signals(bands, level_facts(), 0)
        sig = {s["mast"]: s for s in bands[1][2]["signals"]}
        self.assertEqual(sorted(sig), ["108LA", "108LB", "108R"])
        # the loop halves get their own edges, so each loop mast finds its own half (the plugin's mast_piece)
        self.assertEqual((sig["108LA"]["_edge"], sig["108LB"]["_edge"]), ("e33~1", "e33~2"))
        self.assertEqual(B.placeholder(bands[1][1]["strands"]["e33.1"]), "Track 107B-107C #2")
        self.assertEqual((sig["108R"]["_edge"], sig["108R"]["_toward_node"], sig["108R"]["toward"]),
                         ("e19", "S107", "107"))
        self.assertEqual((sig["108LA"]["dir"], sig["108R"]["dir"], sig["108R"]["heads"]), ("west", "east", 2))

    def test_the_direction_is_the_rows_dir_not_the_name(self):
        # 108LA is an L mast (westbound by ADR-005) and 108R an R mast: the row's dir wins over both
        f = level_facts()
        f.level_masts = [dict(r, dir={"west": "east", "east": "west"}[r["dir"]]) for r in f.level_masts]
        bands = level_bands()
        B.level_signals(bands, f, 0)
        sig = {s["mast"]: s["dir"] for s in bands[1][2]["signals"]}
        self.assertEqual(sig, {"108LA": "east", "108LB": "east", "108R": "west"})

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
                         ("Track 107B-107C #1", "Track 107B-107C #2"))
        # the plugin's mast_piece takes the pieces whose edge is the mast's, or it plus x or y: one half each
        for mast, half in (("108LA", "e33.0"), ("108LB", "e33.1")):
            e = sig[mast]["_edge"]
            self.assertEqual([k for k, t in strands.items() if t["edge"] in (e, e + "x", e + "y")], [half])

    def test_a_mast_at_no_leg_or_two_stops(self):
        f = level_facts()
        f.level_masts[2] = dict(f.level_masts[2], facing="Track 105-109")
        with self.assertRaisesRegex(B.CatsPanelError, "Mast 108R: Switch 107 has 0 legs on track Track 105-109"):
            B.level_signals(level_bands(), f, 0)

    def test_templates_by_appearance_type_and_the_tables_mast(self):
        bands, f = level_bands(), level_facts()
        B.level_signals(bands, f, 0)
        self.assertEqual(B.level_mast_bindings(bands, f, 0),
                         {"108LA": {"name": "Mast 108LA", "template": "single"},
                          "108LB": {"name": "Mast 108LB", "template": "single"},
                          "108R": {"name": "Mast 108R", "template": "double"}})
        f.mast_system["Mast 108R"] = "IF$shsm:basic:one-low(IH1)"
        with self.assertRaisesRegex(B.CatsPanelError, "Mast 108R: tables.xml has IF.shsm:basic:one-low.IH1."):
            B.level_mast_bindings(bands, f, 0)
        # signal_head_plan.csv's templates win; the stock basic types fall back by head count (one single, two double)
        with mock.patch.object(cats_panel_facts, "appearance_templates", return_value={"one-low": "double"}):
            self.assertEqual(B.template_by_type(f), {"one-low": "double", "one-searchlight": "single",
                                                     "two-searchlight": "double", "two-low": "double"})
        clash = ValueError("signal_head_plan.csv gives one-low masts two templates, single and double")
        with mock.patch.object(cats_panel_facts, "appearance_templates", side_effect=clash):
            with self.assertRaisesRegex(B.CatsPanelError, "gives one-low masts two templates"):
                B.template_by_type(f)

    def test_a_level_mast_with_its_own_plan_row_takes_that_template(self):
        """One rule for every level (cats_panel.mast_template): a main or upper mast's own signal_head_plan.csv row
        wins over the template of its appearance type; with neither, the build stops naming the mast and its band."""
        bands, f = level_bands(), level_facts()
        B.level_signals(bands, f, 0)
        f.templates = dict(f.templates, **{"Mast 108R": "triple"})
        got = B.level_mast_bindings(bands, f, 0)
        self.assertEqual(got["108R"], {"name": "Mast 108R", "template": "triple"})
        self.assertEqual(got["108LA"]["template"], "single")                # no row of its own: by its type
        # a type no template covers, and no row of its own
        odd = "IF$shsm:basic:three-odd(IH:HART:C3:108R_Top)"
        f.templates, f.mast_system["Mast 108R"] = {}, odd
        next(r for r in f.level_masts if r["mast"] == "Mast 108R")["system_name"] = odd
        with self.assertRaisesRegex(B.CatsPanelError, "Mast 108R on Main level: no row of its own and no template for "
                                                "its type three-odd in signal_head_plan.csv"):
            B.level_mast_bindings(bands, f, 0)

    def test_a_row_not_drawn_stops(self):
        bands, f = level_bands(), level_facts()
        B.level_signals(bands, f, 0)
        bands[1][2]["signals"] = [s for s in bands[1][2]["signals"] if s["mast"] != "108LB"]
        with self.assertRaisesRegex(B.CatsPanelError, "main and upper masts not on the desk: Mast 108LB"):
            B.level_mast_bindings(bands, f, 0)


def intermediate_bands(order=None):
    """level_bands with a second balloon loop (e44 at Switch 111) on the same band, its strands in `order`."""
    bands = level_bands()
    band = bands[1][1]
    band["nodes"]["S111"] = node("111", "T6", {"A": "e21"}, {"B": "e44.0", "C": "e44.1"})
    band["nodes"]["turn:e44"] = node("", "", {}, {0: "e44.0", 1: "e44.1"}, kind="turnR")
    band["strands"]["e44.0"] = dict(strand(("turn:e44", 0), ("S111", "B"), trial="Track 111B-111C #1"), edge="e44",
                                  cm=90.0, loop_half=1)
    band["strands"]["e44.1"] = dict(strand(("turn:e44", 1), ("S111", "C"), trial="Track 111B-111C #2"), edge="e44",
                                  cm=90.0, loop_half=2)
    if order is not None:
        band["strands"] = {k: band["strands"][k] for k in order}
    return bands


def intermediate_facts(blocks=None):
    """Facts whose only level masts are APB intermediates A83 and A84 at the e33 loop's turnback (masts.csv
    rows with no switch), as CP 107's are."""
    f = level_facts(device=B.DeviceMap(blocks=blocks or {
        "Track 107 Loop 1": block("Track 107B-107C #1"), "Track 107 Loop 2": block("Track 107B-107C #2"),
        "Track 111 Loop 1": block("Track 111B-111C #1"), "Track 111 Loop 2": block("Track 111B-111C #2"),
        "Track 107-109": block("Track 107A-109B")}))
    row = lambda mast, facing, protects: {"mast": mast, "switch": "", "facing": facing, "protects": protects,
                                          "dir": "west" if int(mast[6:]) % 2 else "east",
                                          "system_name": f"IF$shsm:basic:one-searchlight(IH:HART:C3:{mast[5:]})",
                                          "heads": [("h", "h")]}
    f.level_masts = [row("Mast A83", "Track 107 Loop 2", "Track 107 Loop 1"),
                     row("Mast A84", "Track 107 Loop 1", "Track 107 Loop 2")]
    return f


class IntermediateMasts(unittest.TestCase):
    """APB intermediates (a main or upper masts.csv row with no switch) stand at the turnback where the half they face
    meets the half they protect."""

    def test_they_stand_at_their_turnback_on_their_own_half(self):
        bands = intermediate_bands()
        B.level_signals(bands, intermediate_facts(), 0)
        sig = {s["mast"]: s for s in bands[1][2]["signals"]}
        self.assertEqual({m: (s["_edge"], s["_toward_node"], s["dir"]) for m, s in sig.items()},
                         {"A83": ("e33~2", "turn:e33", "west"), "A84": ("e33~1", "turn:e33", "east")})

    def test_the_direction_is_the_rows_dir_not_the_number(self):
        # A83 has an odd number (westbound by the name) and A84 an even one: the rows say the other way
        f = intermediate_facts()
        f.level_masts = [dict(r, dir={"west": "east", "east": "west"}[r["dir"]]) for r in f.level_masts]
        bands = intermediate_bands()
        B.level_signals(bands, f, 0)
        self.assertEqual({s["mast"]: s["dir"] for s in bands[1][2]["signals"]}, {"A83": "east", "A84": "west"})

    def test_only_the_loop_they_stand_on_gets_half_edges(self):
        # the e44 loop at Switch 111 has no mast of its own: its halves keep the plan edge
        bands = intermediate_bands()
        B.level_signals(bands, intermediate_facts(), 0)
        strands = bands[1][1]["strands"]
        self.assertEqual({k: t["edge"] for k, t in strands.items() if t.get("loop_half")},
                         {"e33.0": "e33~1", "e33.1": "e33~2", "e44.0": "e44", "e44.1": "e44"})
        self.assertNotIn("plan_edge", strands["e44.0"])

    def test_the_strand_order_does_not_matter(self):
        # the facing block also holds a track away from the turnback (e19): whichever comes first, the mast stands on
        # the piece that meets the half it protects
        blocks = {"Track 107 Loop 1": block("Track 107B-107C #1"),
                  "Track 107 Loop 2": block("Track 107A-109B", "Track 107B-107C #2"),
                  "Track 111 Loop 1": block("Track 111B-111C #1"), "Track 111 Loop 2": block("Track 111B-111C #2")}
        keys = list(intermediate_bands()[1][1]["strands"])
        results = []
        for order in (keys, keys[::-1], sorted(keys, key=lambda k: k != "e19")):
            with self.subTest(order=order):
                bands = intermediate_bands(order)
                B.level_signals(bands, intermediate_facts(blocks), 0)
                results.append((sorted((s["mast"], s["_edge"], s["_toward_node"], s["edge_cm"])
                                       for s in bands[1][2]["signals"]),
                                {k: t["edge"] for k, t in bands[1][1]["strands"].items()}))
        self.assertEqual(results[0][0], [("A83", "e33~2", "turn:e33", 100.0), ("A84", "e33~1", "turn:e33", 100.0)])
        for got in results[1:]:
            self.assertEqual(got, results[0])

    def test_a_half_that_meets_the_protected_half_at_no_turnback_stops(self):
        f = intermediate_facts()
        f.level_masts = [dict(f.level_masts[0], protects="Track 111 Loop 1")]
        with self.assertRaisesRegex(B.CatsPanelError, "Mast A83: Track 107 Loop 2 meets Track 111 Loop 1 at no turnback"):
            B.level_signals(intermediate_bands(), f, 0)

    def test_a_facing_piece_at_a_level_link_is_passed_over(self):
        # a level link's end (LINK:...) is no node of the band: the piece ending there is not read as a turnback
        bands = intermediate_bands()
        bands[1][1]["strands"]["e50"] = dict(strand(("S111", "A"), ("LINK:A1", 0), trial="Track 111A-201A"),
                                              edge="e50", cm=40.0)
        blocks = {"Track 107 Loop 1": block("Track 107B-107C #1"),
                  "Track 107 Loop 2": block("Track 111A-201A", "Track 107B-107C #2"),
                  "Track 111 Loop 1": block("Track 111B-111C #1"), "Track 111 Loop 2": block("Track 111B-111C #2")}
        B.level_signals(bands, intermediate_facts(blocks), 0)
        sig = {s["mast"]: s for s in bands[1][2]["signals"]}
        self.assertEqual((sig["A83"]["_edge"], sig["A83"]["_toward_node"]), ("e33~2", "turn:e33"))

    def test_a_facing_block_on_two_bands_stands_where_it_meets_the_protected_half(self):
        # the facing block is drawn on the main band away from any turnback and on the upper band at the loop's
        # turnback: the main band's piece does not stop the build before the upper band is read
        bands = intermediate_bands()
        main = {"nodes": {"S1": node("1", "T1", {}, {}), "END:z": node("", "", {}, {}, kind="end")},
                "strands": {"e50": dict(strand(("S1", "B"), ("END:z", "E"), trial="Track 111A-201A"), edge="e50",
                                         cm=40.0)}}
        bands = [bands[0], ("Main level", main, {"mast_prefix": "Mast "}),
                 ("Upper level, 4.25 in", bands[1][1], {"mast_prefix": "Mast "})]
        blocks = {"Track 107 Loop 1": block("Track 107B-107C #1"),
                  "Track 107 Loop 2": block("Track 111A-201A", "Track 107B-107C #2"),
                  "Track 111 Loop 1": block("Track 111B-111C #1"), "Track 111 Loop 2": block("Track 111B-111C #2")}
        B.level_signals(bands, intermediate_facts(blocks), 0)
        self.assertNotIn("signals", bands[1][2])
        sig = {s["mast"]: s for s in bands[2][2]["signals"]}
        self.assertEqual((sig["A83"]["_edge"], sig["A84"]["_edge"]), ("e33~2", "e33~1"))
        # met at two turnbacks, one per band: ambiguous, so it stops
        two = intermediate_bands()
        bands[1] = ("Main level", two[1][1], {"mast_prefix": "Mast "})
        with self.assertRaisesRegex(B.CatsPanelError, "Mast A83: .* at 2 turnbacks on the desk"):
            B.level_signals(bands, intermediate_facts(blocks), 0)

    def test_a_track_no_band_draws_stops(self):
        f = intermediate_facts()
        f.level_masts = [dict(f.level_masts[0], facing="Track 999")]
        with self.assertRaisesRegex(B.CatsPanelError, "Mast A83: no desk band draws Track 999"):
            B.level_signals(intermediate_bands(), f, 0)


class CommittedMainAndUpper(unittest.TestCase):
    """The committed bindings and desk against the committed tables.xml (every name bound must be in it)."""

    @classmethod
    def setUpClass(cls):
        from hartlib import paths, tables
        root = tables.read(paths.REPO_TABLES_XML)
        cls.turnouts = {tables.system_name(t): tables.user_name(t) for t in tables.turnouts(root)}
        cls.sensors = {tables.system_name(s): tables.user_name(s) for s in tables.sensors(root)}
        cls.masts = {tables.user_name(m) for m in tables.masts(root)}
        cls.bound = json.loads(B.BINDINGS.read_text(encoding="utf-8"))

    def test_every_bound_name_is_in_the_tables(self):
        for key, e in self.bound["switches"].items():
            for leg in e["routes"].values():
                for pin in leg.values():
                    with self.subTest(switch=key):
                        system = pin["JMRIPREFIX"] + pin["DECADDR"]
                        self.assertEqual(self.turnouts.get(system), pin["USER_NAME"])
        for key, e in self.bound["blocks"].items():
            if "occupied" in e:
                with self.subTest(block=key):
                    pin = e["occupied"]
                    self.assertEqual(self.sensors.get(pin["JMRIPREFIX"] + pin["DECADDR"]), pin["USER_NAME"])
        self.assertLessEqual({e["name"] for e in self.bound["masts"].values()}, self.masts)

    def test_main_and_upper_turnouts_and_masts_are_bound(self):
        level = {k: e for k, e in self.bound["switches"].items()
                 if e["routes"]["B"]["ROUTECOMMAND"]["JMRIPREFIX"] == "IT"}
        numbers = {B.bdm.base(k) for k in level}
        internal = {u.removeprefix("Switch ") for s, u in self.turnouts.items() if s.startswith(B.level_devices.TURNOUT_PREFIX)}
        self.assertEqual(numbers, internal)                         # double crossover 225 too
        self.assertEqual(len(numbers), 39)                         # 121 and 125: one crossover each (2026-11-19)
        # closed on leg B, but for the crossover halves the plan joins by their leg B: closed on leg C
        self.assertEqual({k for k, e in level.items() if e["normal"] != "B"}, {"121B", "125B"})
        self.assertEqual({e["normal"] for e in level.values()}, {"B", "C"})
        names = {e["name"] for e in self.bound["masts"].values()}
        self.assertLessEqual(B.level_masts.visible_names(levels=(2, 3)), names)
        self.assertEqual(len(B.level_masts.visible_names(levels=(2, 3))), 44)    # masts.csv main and upper rows, APB intermediates too
        hidden = B.level_masts.names(levels=(2, 3)) - B.level_masts.visible_names(levels=(2, 3))
        self.assertEqual(len(hidden), 24)                            # buffer-stop destinations, never on a desk
        self.assertFalse(hidden & names)

    def test_each_helix_track_is_one_block_on_the_desk(self):
        """The plugin joins each helix track drawn on staging and on main or upper logically (SHARED), so a train runs
        from staging to the main and upper levels on the desk, and the join parts no blocks (owner, 2026-11-20): each
        helix track is one desk block, bound once, to the virtual sensor of its helix block, with its planned
        detector on helix node 41."""
        root = ET.parse(B.OUT).getroot()
        self.assertEqual(len(list(root.iter("SHARED"))), 8)        # two helix tracks and two links, both ends
        at_join = [se.find("BLOCK").get("NAME") for se in root.iter("SEC_EDGE")
                   if se.find("SHARED") is not None and se.find("BLOCK") is not None]
        self.assertEqual(at_join, [])                              # no block boundary at the joins
        for name, planned in (("Track Helix Outer", "4101"), ("Track Helix Inner", "4100")):
            with self.subTest(block=name):
                bound = [e for k, e in self.bound["blocks"].items() if e.get("name", k) == name]
                self.assertEqual(len(bound), 1)
                self.assertEqual(bound[0]["occupied"]["USER_NAME"], "BS " + name.removeprefix("Track "))
                self.assertEqual(bound[0]["_planned_occupied"]["DECADDR"], planned)
                self.assertNotIn(name, self.bound["_main_upper_not_on_desk"])
        names = {e.get("name", k) for k, e in self.bound["blocks"].items()}
        self.assertFalse(names & {"Track 131-H1", "Track 131-H2", "Track McKees Rocks", "Track McKeesport"})
        helix = {e.get("name", k) for k, e in self.bound["blocks"].items() if e.get("station") == "Helix"}
        self.assertEqual(helix, {"Track Helix Outer", "Track Helix Inner"})     # "Track <plan name>", the ordinary rule


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
    except B.pd.PluginMissing as e:
        raise unittest.SkipTest(f"no plugin: {e}") from None


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
        with self.assertRaisesRegex(B.CatsPanelError, "elements MYSTERY, which ORDER does not place"):
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
            with self.subTest(tag=tag), self.assertRaisesRegex(B.CatsPanelError, f"no {tag} elements"):
                B.frozen_header(path)

    def test_a_plate_label_on_a_used_cell_or_over_another_label_stops(self):
        cats = plugin_cats()
        header, plate = B.frozen_header()
        with self.assertRaisesRegex(B.CatsPanelError, "a cell the desk uses"):
            B.dress(cats, self.doc((15, "X")), header, plate, "CTC", fit())
        with self.assertRaisesRegex(B.CatsPanelError, "runs into the label"):
            B.dress(cats, self.doc((2, "A VERY LONG TITLE THAT RUNS FAR TO THE RIGHT")), header, plate, "CTC", fit())


class Arguments(unittest.TestCase):
    """Only --check is an option: --help and a typo stop before the plugin is loaded, and write no desk."""

    def run_main(self, argv):
        with tempfile.TemporaryDirectory() as tmp:
            outs = {n: Path(tmp) / n for n in ("OUT", "OUT_ABS", "BINDINGS")}
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.multiple(B, **outs), mock.patch.object(B, "generate") as generate, \
                    mock.patch.object(B.pd, "plugin") as plugin, \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                status = B.main(argv)
            generate.assert_not_called()
            plugin.assert_not_called()
            self.assertEqual(os.listdir(tmp), [])
        return status, out.getvalue(), err.getvalue()

    def test_unknown_argument_is_refused(self):
        for argv in (["--chek"], ["--check", "--verbose"], ["staging"]):
            status, out, err = self.run_main(argv)
            self.assertEqual(status, 2, argv)
            self.assertIn(repr(argv[-1]), err)
            self.assertEqual(out, "")

    def test_help_prints_the_usage(self):
        for argv in (["--help"], ["-h"], ["--check", "--help"], ["--help", "--check"], ["--chek", "-h"]):
            status, out, err = self.run_main(argv)
            self.assertEqual(status, 0, argv)
            self.assertIn("build_cats_panel.py [--check]", out)
            self.assertEqual(err, "")

    def test_help_without_a_docstring(self):
        """python -OO strips the docstring; --help still prints the usage line, not 'None'."""
        with mock.patch.object(B, "__doc__", None):
            status, out, err = self.run_main(["--check", "--help"])
        self.assertEqual((status, out, err), (0, "build_cats_panel.py [--check]\n", ""))


if __name__ == "__main__":
    unittest.main()
