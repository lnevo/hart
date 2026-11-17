"""Engine house on the CATS desks follows the Layout Editor after the Switch 9 rewiring (2026-11-12).

JMRI: Switch 11 closed -> Track EH-1, thrown -> Switch 9; Switch 9 closed -> Track EH-2, thrown -> Track EH-3.
CATS keeps its drawing; NORMAL is each plant's closed BOTTOM leg, as on the Princess plants.
"""
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "cats/scripts"))
import wire_digicon as wire  # noqa: E402
import desks  # noqa: E402  (cats/scripts/tests/desks.py: the live desks)

# Designer source plant cell -> {route edge: (command, block that leg leads to, cell holding that block)}
PLANTS = {
    (24, 8): {"BOTTOM": ("close", "Track EH-2", (24, 9)), "LEFT": ("throw", "Track EH-3", (21, 8))},
    (26, 8): {"BOTTOM": ("close", "Track EH-1", (26, 9)), "LEFT": ("throw", "OS Switch 9", (25, 8))},
}
TURNOUT = {(24, 8): "Switch 9", (26, 8): "Switch 11"}
OS_BLOCK = {(24, 8): "OS Switch 9", (26, 8): "OS Switch 11"}



def _cells(path):
    root = ET.parse(path).getroot()
    return {(int(s.get("X")), int(s.get("Y"))): s for s in root.iter("SECTION")}


def _jmri_paths():
    """{(OS block user name, turnout, setting): destination user name} from tables.xml."""
    root = ET.parse(ROOT / "jmri/layouts/hart/output/tables.xml").getroot()
    blocks = [b for b in root.iter("block") if b.find("path") is not None or b.find("userName") is not None]
    names = {b.get("systemName"): (b.findtext("userName") or "").strip() for b in blocks}
    out = {}
    for b in blocks:
        for path in b.findall("path"):
            for bs in path.findall("beansetting"):
                t = bs.find("turnout")
                if t is not None:
                    dest = path.get("block")
                    out[(names.get(b.get("systemName")), t.get("systemName"), bs.get("setting"))] = names.get(dest, dest)
    return out


class EngineHouse(unittest.TestCase):
    def test_plants_not_inverted(self):
        self.assertNotIn("TO10", wire.INVERT_VS_JMRI)
        self.assertNotIn("TO11", wire.INVERT_VS_JMRI)

    def test_expectations_match_jmri(self):
        paths = _jmri_paths()
        for xy, legs in PLANTS.items():
            for cmd, dest, _cell in legs.values():
                setting = "2" if cmd == "close" else "4"
                self.assertEqual(dest, paths[(OS_BLOCK[xy], TURNOUT[xy], setting)], (xy, cmd))

    def test_designer_source(self):
        cells = _cells(ROOT / "cats/panels/HART_Digicon.xml")
        for xy, legs in PLANTS.items():
            for edge, (_cmd, dest, cell) in legs.items():
                names = {b.get("NAME") for b in cells[cell].iter("BLOCK") if b.get("NAME")}
                if dest.startswith("Track "):           # the Designer source names only the track cells
                    self.assertIn(dest, names, (xy, edge))

    def test_live_desks(self):
        # the live (generated) desks: each engine house plant, found by its OS block, commands its turnout to the
        # leg JMRI's paths give, and NORMAL is the closed leg
        for desk in desks.LIVE:
            for xy, legs in PLANTS.items():
                with self.subTest(desk=desk.name, switch=TURNOUT[xy]):
                    want = {cmd: (dest, cmd == "close") for cmd, dest, _cell in legs.values()}
                    self.assertEqual(desks.routes(desk, OS_BLOCK[xy]), want)

if __name__ == "__main__":
    unittest.main()
