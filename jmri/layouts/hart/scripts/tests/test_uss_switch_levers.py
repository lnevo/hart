"""USS CTC switch columns and points follow the CTC code buttons in tables.xml and the CATS desk.

Plate N sits in lever column (N - 1) / 2. The lever there must be the CTC lever
of turnout Switch N, its OS sensors the code button's, and a column without
signal levers a code button without SIDL. Each points dot sits on the CATS frog
of that switch's OS block.
"""
from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parents[3]
TABLES = SCRIPTS.parent / "output" / "tables.xml"
CATS = ROOT / "cats/panels/HART_CTC.xml"

sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "cats/scripts"))
import digicon_trace as trace  # noqa: E402
import gen_ctc_track_plan as gen  # noqa: E402


def code_buttons() -> dict[str, dict[str, str]]:
    """Turnout user name -> code button fields, with the lever's system name."""
    root = ET.parse(TABLES).getroot()
    system = {
        (s.findtext("userName") or "").strip(): (s.findtext("systemName") or "").strip()
        for s in root.iter("sensor")
    }
    out = {}
    for cb in root.iter("ctcCodeButtonData"):
        get = lambda tag: (cb.findtext(tag) or "").strip()  # noqa: E731
        out[get("SWDI_ExternalTurnout")] = {
            "lever": system.get(get("SWDL_InternalSensor"), ""),
            "os": tuple(s for s in (get("OSSectionOccupiedExternalSensor"),
                                    get("OSSectionOccupiedExternalSensor2")) if s),
            "signals": get("SIDL_Enabled") == "true",
        }
    return out


def cats_frogs() -> dict[str, tuple[int, int]]:
    """OS block -> the CATS cell holding its SWITCHPOINTS."""
    cells = trace.track_cells(ET.parse(CATS).getroot().find("TRACKPLAN"))
    return {
        trace.plant_os(cells, xy): xy
        for xy, sec in cells.items()
        if sec.find("SEC_EDGE/SWITCHPOINTS/ROUTEINFO") is not None
    }


class LeverColumnsTest(unittest.TestCase):
    def test_each_column_works_its_plate_switch(self) -> None:
        buttons = code_buttons()
        self.assertEqual(len(buttons), gen.N_SLOTS)
        for slot in range(gen.N_SLOTS):
            turnout = "Switch %d" % (2 * slot + 1)
            with self.subTest(turnout=turnout):
                cb = buttons[turnout]
                self.assertEqual(cb["lever"], "IS%d:LEVER" % gen.SLOT_SW_NUM[slot])
                self.assertEqual(gen.SLOT_LOCK_UID[slot], gen.SLOT_SW_NUM[slot] + 1)
                self.assertEqual(gen.UID_SLOT[gen.SLOT_SW_NUM[slot]], slot)
                self.assertEqual(gen.UID_SLOT[gen.SLOT_LOCK_UID[slot]], slot)
                self.assertEqual(slot not in gen.SWITCH_ONLY_SLOTS, cb["signals"])

    def test_uid_slot_has_no_strays(self) -> None:
        self.assertEqual(set(gen.UID_SLOT),
                         set(gen.SLOT_SW_NUM.values()) | set(gen.SLOT_LOCK_UID.values()))


class PointsTest(unittest.TestCase):
    def test_points_dot_on_the_primary_os_frog(self) -> None:
        frogs = cats_frogs()
        buttons = code_buttons()
        seen = set()
        for xy, (turnout, _invert) in gen.PLANTS.items():
            with self.subTest(turnout=turnout):
                primary = buttons[turnout]["os"][0].split(" / ")[0].replace("BS Switch ", "OS Switch ")
                self.assertEqual(frogs[primary], xy)
                seen.add(turnout)
        self.assertEqual(seen, set(buttons))

    def test_os_frog_is_the_cats_desk(self) -> None:
        self.assertEqual(gen.OS_FROG, cats_frogs())


if __name__ == "__main__":
    unittest.main()
