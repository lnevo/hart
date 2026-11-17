"""Princess on the CATS desks: K-1 / K-2 on the outer rows, the mains in the centre (ADR-017 item 8)."""
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "cats/scripts"))
import wire_digicon as wire  # noqa: E402
import desks  # noqa: E402  (cats/scripts/tests/desks.py: the live desks)



def _cells(path):
    root = ET.parse(path).getroot()
    return {(int(s.get("X")), int(s.get("Y"))): s for s in root.iter("SECTION")}


class PrincessRows(unittest.TestCase):
    def test_designer_source_rows(self):
        cells = _cells(ROOT / "cats/panels/HART_Digicon.xml")
        self.assertEqual("Track K-1", cells[(57, 5)].find(".//BLOCK").get("NAME"))
        self.assertEqual("Track McKees Rocks", cells[(57, 6)].find(".//BLOCK").get("NAME"))
        self.assertEqual("Track McKeesport", cells[(57, 7)].find(".//BLOCK").get("NAME"))
        self.assertEqual("Track K-2", cells[(57, 8)].find(".//BLOCK").get("NAME"))
        self.assertEqual("K-1", cells[(58, 5)].find("SEC_NAME").get("NAME"))
        self.assertEqual("McKees Rocks, PA", cells[(58, 6)].find("SEC_NAME").get("NAME"))
        self.assertEqual("McKeesport, PA", cells[(58, 7)].find("SEC_NAME").get("NAME"))
        self.assertEqual("K-2", cells[(58, 8)].find("SEC_NAME").get("NAME"))
        # the K tracks run east to the edge; the mains stop at column 59
        for x in range(60, 64):
            self.assertIn((x, 5), cells)
            self.assertIn((x, 8), cells)
            self.assertNotIn((x, 6), cells)
            self.assertNotIn((x, 7), cells)

    def test_generator_tables_follow(self):
        self.assertIn(((63, 5, "RIGHT"), (63, 8, "RIGHT")), wire.SHARED_LINKS)
        self.assertEqual("Mast 2035", wire.SIGNAL_NAMES[(61, 5, "RIGHT")])
        self.assertEqual("Mast 2036", wire.SIGNAL_NAMES[(62, 5, "LEFT")])
        self.assertEqual("Mast 40LB", wire.SIGNAL_NAMES[(56, 5, "RIGHT")])
        self.assertEqual("Mast 40LA", wire.SIGNAL_NAMES[(56, 6, "RIGHT")])
        self.assertEqual("Mast 38LA", wire.SIGNAL_NAMES[(56, 7, "RIGHT")])
        self.assertEqual("Mast 38LB", wire.SIGNAL_NAMES[(56, 8, "RIGHT")])
        # straight leg is the closed main now, so Switches 37/39 are no longer inverted
        self.assertNotIn("TOL29", wire.INVERT_VS_JMRI)
        self.assertNotIn("TOR36", wire.INVERT_VS_JMRI)

    def test_live_desk_polarity(self):
        # the live (generated) desks: Switches 37 and 39 close to the mains, NORMAL, and throw to the K tracks
        want = {"OS Switch 37": ("Track McKeesport", "Track K-2"), "OS Switch 39": ("Track McKees Rocks", "Track K-1")}
        for desk in desks.LIVE:
            for os_block, (closed, thrown) in want.items():
                with self.subTest(desk=desk.name, plant=os_block):
                    self.assertEqual(desks.routes(desk, os_block), {"close": (closed, True), "throw": (thrown, False)})

if __name__ == "__main__":
    unittest.main()
