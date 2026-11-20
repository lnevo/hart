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
import le_tables as T  # noqa: E402
import mast_rule as mr  # noqa: E402
import staging_device_map as sdm  # noqa: E402
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


class Pins(unittest.TestCase):
    PINS = "block,node,block_input,notes\nTrack Helix Inner,41,1,\nTrack 227-241 2,41,4,\n"

    def test_read(self):
        self.assertEqual(bdm.read_pins(write(self.PINS)), {"Track Helix Inner": (41, 0), "Track 227-241 2": (41, 3)})
        self.assertEqual(bdm.read_pins()["Track Helix Outer"], (41, 1))        # the committed file

    def test_bad_pins_stop(self):
        for text, msg in ((self.PINS + "Track Helix Outer,41,1,\n", "pinned twice"),
                          (self.PINS + "Track Helix Inner,41,2,\n", "pinned twice"),
                          (self.PINS + "Track X,41,9,\n", "is not 1 to 8"),
                          (self.PINS + "Helix,41,2,\n", "not a track block"),
                          (self.PINS + "Track X,forty,2,\n", "are numbers")):
            with self.subTest(msg=msg), self.assertRaisesRegex(bdm.MapError, msg):
                bdm.read_pins(write(text))

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

    def test_the_committed_map_holds_the_pins(self):
        occ = {r["user_name"]: r for r in sdm.read_rows(bdm.OUT, bdm.COLUMNS) if r["layer"] == "occupancy"}
        for user, packed in (("BS Helix Inner", "M2S4100"), ("BS Helix Outer", "M2S4101"),
                             ("BS 227-241 1", "M2S4102"), ("BS 227-241 2", "M2S4103")):
            with self.subTest(user=user):
                self.assertEqual(occ[user]["system_name"], packed)
        self.assertNotIn("BS 131-H1", occ)
        self.assertNotIn("BS 131-H2", occ)


class StagingShares(unittest.TestCase):
    def test_only_the_helix_blocks_are_shared(self):
        rows = [dict(layer="block", user_name="Track Helix Inner"), dict(layer="block", user_name="Track K-1")]
        dm = railroad.DeviceMap()
        occ = railroad.DeviceRow(level=3, layer="occupancy", user_name="BS Helix Inner", jmri_name="IS:HART:C3:B:Helix_Inner")
        dm.rows.append(occ)
        dm.blocks["Track Helix Inner"] = railroad.DeviceRow(level=3, layer="block", user_name="Track Helix Inner")
        helix = {"McKeesport": {"block": "Track Helix Inner"}}
        self.assertEqual(sdm.shared_blocks(rows, dm, helix), {"Track Helix Inner": occ})
        dm.blocks["Track K-1"] = railroad.DeviceRow(level=3, layer="block", user_name="Track K-1")
        with self.assertRaisesRegex(sdm.StagingMapError, "only the helix blocks"):
            sdm.shared_blocks(rows, dm, helix)
        del dm.blocks["Track K-1"]
        dm.rows.remove(occ)
        with self.assertRaisesRegex(sdm.StagingMapError, "no occupancy row"):
            sdm.shared_blocks(rows, dm, helix)

    def test_a_shared_block_needs_no_staging_occupancy_row(self):
        rows = [dict(layer="block", user_name="Track Helix Inner", system_name="IB24", jmri_name="IB24")]
        sdm.check_rows(rows, {"Track Helix Inner"})
        with self.assertRaisesRegex(sdm.StagingMapError, "blocks and occupancy rows differ"):
            sdm.check_rows(rows)


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
