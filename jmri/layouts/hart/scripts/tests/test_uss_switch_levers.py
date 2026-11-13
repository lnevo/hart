"""USS CTC switch columns and points follow the CTC code buttons in tables.xml and the CATS desk.

Plate N sits in lever column (N - 1) / 2. The lever there must be the CTC lever
of turnout Switch N, its OS sensors the code button's, and a column without
signal levers a code button without SIDL. Each points dot sits on the CATS frog
of that switch's OS block.
"""
from __future__ import annotations

import dataclasses
import sys
import unittest
from unittest import mock
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
    return trace.desk_plants(trace.track_cells(ET.parse(CATS).getroot().find("TRACKPLAN")))


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


class GapsAndLevelsTest(unittest.TestCase):
    def test_a_plate_gap_draws_a_blank_column(self) -> None:
        switches = {n: sw for n, sw in gen.SWITCHES.items() if n != 5}
        cols = gen.uss_columns(switches)
        self.assertEqual(cols["blank"], {2})
        self.assertNotIn(2, cols["sw_num"])
        patch = {"N_SLOTS": cols["n_slots"], "BLANK_SLOTS": cols["blank"],
                 "SWITCH_ONLY_SLOTS": cols["switch_only"], "SLOT_SW_NUM": cols["sw_num"],
                 "SLOT_LOCK_UID": cols["lock_uid"], "UID_SLOT": cols["uid_slot"]}
        with mock.patch.multiple(gen, **patch):
            block = gen.build_block(gen.parse_cats(CATS))
        self.assertIn('x="142" y="0"', block)  # slot 2 background
        self.assertIn("Panel-blank-7.gif", block)
        self.assertNotIn("IS5:LEVER", block)

    def test_a_second_level_stops_the_generator(self) -> None:
        switches = dict(gen.SWITCHES)
        switches[41] = dataclasses.replace(switches[39], number=41, level="2", ctc_is=41)
        with self.assertRaisesRegex(SystemExit, r"level\(s\) \['2'\]"):
            gen.uss_columns(switches)

    def test_a_plant_cell_without_a_row_is_named(self) -> None:
        cells = dict(gen.PLANT_CELLS)
        cells[(60, 12)] = "OS Switch 99"
        with self.assertRaisesRegex(SystemExit, r"OS Switch 99 at \(60, 12\)"):
            gen.uss_plants(gen.SWITCHES, cells)

    def test_an_undrawn_os_block_is_named(self) -> None:
        cells = {xy: os for xy, os in gen.PLANT_CELLS.items() if os != "OS Switch 7b"}
        with self.assertRaisesRegex(SystemExit, "OS Switch 7b"):
            gen.uss_plants(gen.SWITCHES, cells)


if __name__ == "__main__":
    unittest.main()
