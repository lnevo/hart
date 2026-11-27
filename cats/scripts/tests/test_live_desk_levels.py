"""The main and upper levels on the live, generated desks (cats/panels/HART_CTC.xml and its ABS twin HART_ABS.xml):
their plants command only the turnouts their device-master rows give (internal today), their masts are masts.csv's main and upper rows', and their
blocks take the desk's discipline and report their virtual occupancy sensors (IS:HART:C3:B:<block key>, the device
map's jmri_name).
"""
from __future__ import annotations

import json
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import devices, level_devices, level_masts, tables_build  # noqa: E402

LEVEL_MASTS = level_masts.visible_names(levels=(2, 3))    # the hidden virtual masts are never drawn
BINDINGS = ROOT / "cats/panels/HART_CTC.bindings.json"
# DECADDR of a main or upper virtual occupancy sensor (IS:HART:C3:B:<block key>): the prefix less JMRIPREFIX "IS"
LEVEL_SENSOR = level_devices.SENSOR_PREFIX.removeprefix("IS")


def ios(el: ET.Element) -> tuple:
    return tuple(sorted(el.attrib.items())) + ((el.text or "").strip(),)


def blocks(root: ET.Element) -> dict[str, set[tuple]]:
    """Block name -> every distinct definition of it (STATION, DISCIPLINE and IOSPECs)."""
    out: dict[str, set[tuple]] = {}
    for b in root.iter("BLOCK"):
        if not b.get("NAME"):
            continue
        spec = tuple((tag, tuple(ios(i) for i in el.iter("IOSPEC")))
                     for tag in ("OCCUPIEDSPEC", "UNOCCUPIEDSPEC") for el in [b.find(tag)] if el is not None)
        out.setdefault(b.get("NAME"), set()).add((b.get("STATION"), b.get("DISCIPLINE"), spec))
    return out


class LiveDeskLevels(unittest.TestCase):
    DESK, DISCIPLINE = ROOT / "cats/panels/HART_CTC.xml", "CTC"

    @classmethod
    def setUpClass(cls) -> None:
        cls.desk = ET.parse(cls.DESK).getroot()

    def test_main_and_upper_bind_only_their_rows_turnouts_and_masts(self) -> None:
        turnouts = tables_build.level_turnouts([r.cells() for r in devices.load()])   # {user name: bean name}
        level = [i for i in self.desk.iter("IOSPEC") if i.get("USER_NAME") in turnouts]
        self.assertEqual({i.get("USER_NAME") for i in level}, set(turnouts))
        on_routes = {id(i) for ri in self.desk.iter("ROUTEINFO") for c in ri for i in c.iter("IOSPEC")}
        for i in level:
            with self.subTest(turnout=i.get("USER_NAME")):
                self.assertEqual(i.get("JMRIPREFIX") + i.get("DECADDR"), turnouts[i.get("USER_NAME")])
                self.assertIn(id(i), on_routes, "a main or upper turnout outside a route")
        drawn = {(s.text or "").strip() for s in self.desk.iter("SECSIGNAL")}
        self.assertEqual(drawn & LEVEL_MASTS, LEVEL_MASTS)

    def test_main_and_upper_take_the_desk_discipline_and_their_virtual_sensors(self) -> None:
        # CTC on the CTC desk, as staging is: CATS holds their signals and releases them (owner, 2026-11-17);
        # ABS on the ABS twin. Each reports its virtual occupancy sensor; only the middle of 225's X has none.
        bound = json.loads(BINDINGS.read_text(encoding="utf-8"))["blocks"]
        level = {e.get("name", k): e for k, e in bound.items() if "_planned_occupied" in e or
                 e.get("occupied", {}).get("DECADDR", "").startswith(LEVEL_SENSOR) or k == "OS Switch 225"}
        self.assertGreater(len(level), 100)
        self.assertEqual(sorted(n for n, e in level.items() if "occupied" not in e), ["OS Switch 225"])
        found = blocks(self.desk)
        for name, e in sorted(level.items()):
            with self.subTest(block=name):
                self.assertEqual({d[1] for d in found[name]}, {self.DISCIPLINE})
                if name == "OS Switch 225":
                    self.assertEqual({d[2] for d in found[name]}, {()}, "the middle of 225's X stays dark")
                    continue
                (spec,) = {d[2] for d in found[name]}
                self.assertEqual([t for t, _ in spec], ["OCCUPIEDSPEC", "UNOCCUPIEDSPEC"])
                for _tag, specs in spec:
                    self.assertEqual([dict(x[:-1])["JMRIPREFIX"] for x in specs], ["IS"])
                    self.assertEqual([dict(x[:-1])["DECADDR"] for x in specs],
                                     [e["occupied"]["DECADDR"]])
        self.assertEqual({d[1] for defs in found.values() for d in defs}, {self.DISCIPLINE})


class LiveDeskLevelsABS(LiveDeskLevels):
    DESK, DISCIPLINE = ROOT / "cats/panels/HART_ABS.xml", "ABS"


if __name__ == "__main__":
    unittest.main()
