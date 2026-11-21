"""Each helix track one JMRI block from its staging switch up the helix (owner, 2026-11-20): helix_tracks.csv, the
detector pins, the staging map's shared blocks and the Layout Editor build's handling of them."""
from __future__ import annotations

import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/schematic"))
import build_device_map as bdm  # noqa: E402
from hartlib import devices  # noqa: E402
import le_tables as T  # noqa: E402
import mast_rule as mr  # noqa: E402
import check_device_master as cdm  # noqa: E402
from hartlib import railroad  # noqa: E402


def write(text: str) -> Path:
    tmp = Path(tempfile.mkdtemp())
    p = tmp / "f.csv"
    p.write_text(text, encoding="utf-8")
    return p


HELIX = ("helix,block,staging_switch,level_switch,notes\n"
         "McKees Rocks,Track Helix Outer,39,131A,\nMcKeesport,Track Helix Inner,37,131B,\n")


class HelixFile(unittest.TestCase):
    def test_the_committed_file(self):
        got = mr.read_helix_tracks()
        self.assertEqual({k: v["block"] for k, v in got.items()},
                         {"McKees Rocks": "Track Helix Outer", "McKeesport": "Track Helix Inner"})
        self.assertEqual((got["McKees Rocks"]["staging_switch"], got["McKees Rocks"]["level_switch"]), ("39", "131A"))

    def test_bad_rows_stop(self):
        for text, msg in ((HELIX + "McKeesport,Track X,37,131B,\n", "given twice"),
                          (HELIX.replace("Track Helix Inner", "Helix Inner"), "are all needed"),
                          (HELIX.replace(",131B,", ",,"), "are all needed"),
                          ("helix,block,staging_switch,level_switch,notes\n", "no helix tracks")):
            with self.subTest(msg=msg), self.assertRaisesRegex(mr.MapError, msg):
                mr.read_helix_tracks(write(text))

    def test_tags_follow_the_overrides_order(self):
        helix = mr.read_helix_tracks(write(HELIX))
        over = {"helix": {"T210": "McKees Rocks", "T281": "McKeesport"}}
        self.assertEqual(mr.helix_blocks(over, helix), {"H1": "Track Helix Outer", "H2": "Track Helix Inner"})
        with self.assertRaisesRegex(mr.MapError, "names helix tracks"):
            mr.helix_blocks({"helix": {"T210": "McKees Rocks"}}, helix)

    def test_a_helix_track_takes_its_block_name(self):
        found = [dict(ends=(("sw", "131"), ("helix", "H1")), trial=["Track e88"], row=0),
                 dict(ends=(("sw", "107"), ("sw", "109")), trial=["Track e1"], row=0)]
        mr.track_names(found, {"H1": "Track Helix Outer"})
        self.assertEqual([t["name"] for t in found], ["Track Helix Outer", "Track 107-109"])
        with self.assertRaisesRegex(mr.MapError, "names no block"):
            mr.track_names([dict(ends=(("sw", "131"), ("helix", "H2")), trial=["Track e89"], row=0)],
                           {"H1": "Track Helix Outer"})
        staging = [dict(ends=(("sw", "37"), ("helix", "H")), trial=["Track e37"], row=0)]
        mr.track_names(staging)                                  # staging's own mast rule names by the stem
        self.assertEqual(staging[0]["name"], "Track 37-H")


def track(name, a, b=None, row=0, trial=None, loop=False, helix=False, level=3):
    """An in-memory track entry, as mast_rule.tracks gives them: ends by switch, a bumper (b None) or the helix."""
    far = ("helix", "H1") if helix else ("sw", b) if b else ("bumper", None)
    return dict(name=name, ends=(("sw", a), far), row=row, trial=trial or [f"Track {name}"], loop=loop, main=True,
                level=level)


class Pins(unittest.TestCase):
    HEAD = "level,switch_a,switch_b,parallel,half,block,node,block_input,notes\n"
    PINS = HEAD + "3,,,,,Track Helix Inner,41,1,\n3,227,241,,2,,41,4,\n"
    FOUND = [track("Track 227-241", "241", "227"), track("Track Helix Inner", "131", helix=True),
             track("Track Helix Outer", "131", helix=True, row=1, level=2), track("Track 241 Spur", "241")]
    SPLIT = {"Track 227-241"}

    def read(self, text):
        return bdm.read_pins(write(text), self.FOUND, self.SPLIT)

    def test_read(self):
        self.assertEqual(self.read(self.PINS), {"Track Helix Inner": (41, 0), "Track 227-241 2": (41, 3)})
        # staging's rows (level 1) are read_staging_pins': this reader passes them by
        self.assertEqual(self.read(self.PINS + "1,,,,,Track Barn,13,1,\n"), self.read(self.PINS))
        self.assertEqual(bdm.read_pins()["Track Helix Outer"], (41, 1))        # the committed file

    def test_bad_pins_stop(self):
        for text, msg in ((self.PINS + "2,,,,,Track Helix Outer,41,1,\n", "pinned twice"),
                          (self.PINS + "2,,,,,Track Helix Outer,41,4,\n", "pinned twice"),
                          (self.PINS + "2,,,,,Track Helix Outer,41,9,\n", "is not 1 to 8"),
                          (self.PINS + "3,,,,,Helix,41,2,\n", "is no helix block"),
                          (self.PINS + "3,37,39,,,Track Helix Inner,41,2,\n", "named by its block alone"),
                          (self.PINS + "2,,,,,Track Helix Outer,forty,2,\n", "are numbers"),
                          (self.PINS + "3,227,241,,,,41,2,\n", "in two halves"),            # half missing
                          (self.PINS + "3,241,,,1,,41,2,\n", "one block: no half"),          # half on a plain track
                          (self.PINS + "3,241,227,,1,,41,2,\n", "lower first"),
                          (self.PINS + "3,9,10,,,,41,2,\n", "no track runs Switch 9 to Switch 10"),
                          # the level: a track is looked for on its row's level only, a helix block is on one
                          (self.PINS + "2,241,,,,,41,2,\n", "no track runs Switch 241 spur"),
                          (self.PINS + "3,,,,,Track Helix Outer,41,2,\n", "level 2 block, not level 3"),
                          (self.PINS + ",,,,,Track Helix Outer,41,2,\n", "is not 1, 2 or 3"),
                          ("switch_a,switch_b,parallel,half,block,node,block_input,notes\n,,,,Track Helix Inner,41,1,\n",
                           "columns")):
            with self.subTest(msg=msg), self.assertRaisesRegex(bdm.MapError, msg):
                self.read(text)

    def test_a_helix_block_on_two_levels_stops(self):
        found = self.FOUND + [track("Track Helix Inner", "131", helix=True, row=2, level=2)]
        with self.assertRaisesRegex(bdm.MapError, "Track Helix Inner is found on levels 3 and 2"):
            bdm.read_pins(write(self.PINS), found, self.SPLIT)

    def test_the_rule_never_hands_out_a_pinned_input(self):
        nodes = bdm.Nodes([railroad.LcosNode(2, 3, "Helix", 41)])
        nodes.pin({"Track A": (41, 0), "Track B": (41, 2)})
        self.assertEqual([nodes.take(41, "block")[0] for _ in range(3)], [1, 3, 4])
        self.assertEqual(nodes.take_pinned("Track B"), (41, 2, 4102))
        self.assertIsNone(nodes.take_pinned("Track B"))         # once
        with self.assertRaisesRegex(bdm.MapError, r"Track A"):
            nodes.check_pins()                                   # Track A was never placed
        with self.assertRaisesRegex(bdm.MapError, "does not list"):
            bdm.Nodes([]).pin({"Track A": (41, 0)})

    def test_staging_nodes_are_never_handed_out_or_pinned(self):
        """lcos_nodes.csv holds staging's nodes as built: the rule neither picks one nor lets a pin take it."""
        nodes = bdm.Nodes([railroad.LcosNode(2, 1, "Helix", 11), railroad.LcosNode(3, 3, "Helix", 41)])
        self.assertEqual(nodes.pick(3, "Helix", "block"), 41)
        for pick in (lambda: nodes.pick(1, "Helix", "block"), lambda: nodes.pick_mast(1, "Helix", 1)):
            with self.assertRaisesRegex(bdm.MapError, "level 1 is staging: its nodes .* are as built"):
                pick()
        with self.assertRaisesRegex(bdm.MapError, "does not list"):
            nodes.pin({"Track A": (11, 0)})

    def test_the_committed_map_holds_the_pins(self):
        occ = {r["user_name"]: r for _n, r in devices.device_map_lines(("2", "3"), bdm.OUT) if r["layer"] == "occupancy"}
        for user, packed in (("BS Helix Inner", "M2S4100"), ("BS Helix Outer", "M2S4101"),
                             ("BS 227-241 1", "M2S4102"), ("BS 227-241 2", "M2S4103")):
            with self.subTest(user=user):
                self.assertEqual(occ[user]["system_name"], packed)
        self.assertNotIn("BS 131-H1", occ)
        self.assertNotIn("BS 131-H2", occ)


class StagingShares(unittest.TestCase):
    """A helix block is one block on two levels (check_device_master.check_rows): its staging row and its main or
    upper row, and one occupancy row on either level."""

    @staticmethod
    def row(level, layer, user, **cols):
        return dict(dict(level=level, layer=layer, user_name=user, system_name="", jmri_name="", role="", dcc="",
                         blocks="", assignment="virtual"), **cols)

    def lines(self, *extra):
        return list(enumerate([self.row("1", "block", "Track Helix Inner", system_name="IB24"),
                               self.row("3", "block", "Track Helix Inner"),
                               self.row("3", "occupancy", "BS Helix Inner", blocks="Track Helix Inner"), *extra], 2))

    def test_only_the_helix_blocks_are_on_two_levels(self):
        self.assertEqual(cdm.check_rows(self.lines(), {"Track Helix Inner"}), [])
        got = cdm.check_rows(self.lines(self.row("1", "block", "Track K-1"), self.row("3", "block", "Track K-1"),
                                        self.row("1", "occupancy", "BS K-1", blocks="Track K-1")),
                             {"Track Helix Inner"})
        self.assertTrue(any("blocks named on more than one level: ['Track Helix Inner', 'Track K-1']" in p
                            for p in got), got)
        self.assertTrue(any("exactly the helix blocks" in p for p in cdm.check_rows(self.lines(), set())))

    def test_a_helix_block_has_one_occupancy_row_on_either_level(self):
        lines = self.lines()[:2]
        self.assertEqual(cdm.check_rows(lines, {"Track Helix Inner"}),
                         ["devices.csv line 2, 3: block Track Helix Inner has 0 occupancy rows naming it (none), "
                          "not one"])


class LayoutEditor(unittest.TestCase):
    def test_retired_blocks_keep_their_numbers_taken(self):
        order = T.numbered_blocks({"Track 127-131 1", "Track 201-203"} | set(T.RETIRED_BLOCKS))
        self.assertEqual(order.index("Track 131-H1") + 1, order.index("Track 131-H2"))
        self.assertLess(order.index("Track 127-131 1"), order.index("Track 131-H1"))
        self.assertLess(order.index("Track 131-H2"), order.index("Track 201-203"))

    def test_a_helix_blocks_detector_is_the_builds_own(self):
        root = ET.fromstring(
            "<layout-config><blocks><block systemName='IB24'><systemName>IB24</systemName>"
            "<userName>Track Helix Inner</userName><permissive>no</permissive>"
            "<occupancysensor>BS Helix Inner</occupancysensor></block>"
            "<block systemName='IB1'><systemName>IB1</systemName><userName>Track K-1</userName>"
            "<permissive>no</permissive><occupancysensor>BS K-1</occupancysensor></block></blocks>"
            "<layoutblocks><layoutblock systemName='ILB77' occupancysensor='BS Helix Inner'>"
            "<systemName>ILB77</systemName><userName>Track Helix Inner</userName></layoutblock></layoutblocks>"
            "</layout-config>")
        counts = T.strip_build_owned(root)
        self.assertEqual(counts[T.STRIPPED[5]], 2)                   # the block and its layout block
        self.assertIsNone(root.find("blocks/block[@systemName='IB24']/occupancysensor"))
        self.assertIsNone(root.find("layoutblocks/layoutblock").get("occupancysensor"))
        self.assertEqual(root.findtext("blocks/block[@systemName='IB1']/occupancysensor"), "BS K-1")

    def test_the_guard_compares_a_helix_block_without_its_binding(self):
        b = ET.fromstring("<block><systemName>IB24</systemName><permissive>no</permissive>"
                          "<occupancysensor>BS Helix Inner</occupancysensor></block>")
        self.assertIsNone(T.without_level_detector(b, {"BS Helix Inner"}).find("occupancysensor"))
        self.assertIsNotNone(b.find("occupancysensor"))                  # a copy: the candidate keeps it
        self.assertIs(T.without_level_detector(b, {"BS K-1"}), b)
        lb = ET.fromstring("<layoutblock occupancysensor='BS Helix Inner'><systemName>ILB77</systemName></layoutblock>")
        self.assertIsNone(T.without_level_detector(lb, {"BS Helix Inner"}).get("occupancysensor"))


if __name__ == "__main__":
    unittest.main()
