"""Engine house on the CATS desks follows the Layout Editor after the Switch 9 rewiring (2026-11-12).

JMRI: Switch 11 closed -> Track EH-1, thrown -> Switch 9; Switch 9 closed -> Track EH-2, thrown -> Track EH-3.
CATS keeps its drawing: the drawn-through legs (LEFT) are the thrown ones, so both plants are inverted.
"""
import re
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
    text = (ROOT / "jmri/layouts/hart/output/tables.xml").read_text()
    names = dict(re.findall(r'<block systemName="(IB[^"]+)" length=[^>]*>\s*<systemName>[^<]*</systemName>\s*<userName>([^<]+)</userName>', text))
    out = {}
    for sysname, body in re.findall(r'<block systemName="(IB[^"]+)" length=[^>]*>(.*?)</block>', text, re.S):
        for dest, path in re.findall(r'<path [^>]*block="([^"]+)"[^>]*>(.*?)</path>', body, re.S):
            for setting, turnout in re.findall(r'<beansetting setting="(\d)">\s*<turnout systemName="([^"]+)"', path):
                out[(names.get(sysname), turnout, setting)] = names.get(dest, dest)
    return out


class EngineHouse(unittest.TestCase):
    def test_both_plants_inverted(self):
        self.assertIn("TO10", wire.INVERT_VS_JMRI)
        self.assertIn("TO11", wire.INVERT_VS_JMRI)

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


if __name__ == "__main__":
    unittest.main()
