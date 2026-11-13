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

# plant cell -> {route edge: (command, block that leg leads to, cell holding that block)}
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

    def test_desks(self):
        for desk in ("HART_Digicon.xml", "HART_CTC.xml", "HART_ABS.xml"):
            cells = _cells(ROOT / "cats/panels" / desk)
            for xy, legs in PLANTS.items():
                for edge, (cmd, dest, cell) in legs.items():
                    names = {b.get("NAME") for b in cells[cell].iter("BLOCK") if b.get("NAME")}
                    # the Designer source names only the track cells; the build fills the OS cells
                    if desk != "HART_Digicon.xml" or dest.startswith("Track "):
                        self.assertIn(dest, names, (desk, xy, edge))
                    if desk == "HART_Digicon.xml":
                        continue
                    route = [r for r in cells[xy].iter("ROUTEINFO") if r.get("ROUTEID") == edge][0]
                    self.assertEqual(cmd, route.find("ROUTECOMMAND/IOSPEC").text.strip(), (desk, xy, edge))
                    self.assertEqual(cmd, route.find("SELECTEDREPORT/IOSPEC").text.strip(), (desk, xy, edge))
                    # NORMAL is the closed leg
                    self.assertEqual(cmd == "close", route.get("NORMAL") == "true", (desk, xy, edge))


if __name__ == "__main__":
    unittest.main()
