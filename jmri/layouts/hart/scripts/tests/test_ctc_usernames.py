from __future__ import annotations

import importlib.util
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
TABLES = SCRIPTS.parent / "output" / "tables.xml"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    import sys

    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


refresh = load_module("refresh_bean_comments", SCRIPTS / "refresh_bean_comments.py")


class CtcInternalNamesTest(unittest.TestCase):
    def test_ctc_user_names_use_live_switch_numbers(self) -> None:
        self.assertEqual(refresh.ctc_user_name("IS3:LEVER"), "CTC 1 lever")
        self.assertEqual(refresh.ctc_user_name("IS1:LEVER"), "CTC 3 lever")
        self.assertEqual(refresh.ctc_user_name("IS32:LOCKTOGGLE"), "CTC 9 lock local")
        self.assertEqual(refresh.ctc_user_name("IS14:LOCKTOGGLE"), "CTC 25 lock local")

    def test_tables_have_no_old_ctc_or_olcb_leftovers(self) -> None:

        root = ET.parse(TABLES).getroot()
        leftover: list[str] = []
        old_ctc: list[str] = []
        for sensor in root.iter("sensor"):
            user_name = (sensor.findtext("userName") or "").strip()
            system_name = (sensor.findtext("systemName") or "").strip()
            if "leftover" in user_name.lower():
                leftover.append(f"{system_name} {user_name}")
            if user_name.startswith("CTC 1") and len(user_name.split()) >= 2:
                num = user_name.split()[1]
                if num.isdigit() and int(num) >= 100:
                    old_ctc.append(user_name)
        mtt = sorted(
            (el.findtext("systemName") or "").strip()
            for el in root.iter("turnout")
            if (el.findtext("systemName") or "").startswith("MTT")
        )
        self.assertEqual(leftover, [])
        self.assertEqual(old_ctc, [])
        self.assertEqual(mtt, ["MTT100", "MTT111", "MTT113", "MTT114", "MTT115"])

    def test_every_switch_has_a_ctc_lever(self) -> None:
        root = ET.parse(TABLES).getroot()
        columns = list(root.iter("ctcCodeButtonData"))
        self.assertEqual(len(columns), 20)
        turnouts = {
            (col.findtext("SWDI_ExternalTurnout") or "").strip()
            for col in columns
            if (col.findtext("SWDL_Enabled") or "") == "true"
        }
        expected = {
            "Switch 1", "Switch 3", "Switch 5", "Switch 7", "Switch 9",
            "Switch 11", "Switch 13", "Switch 15", "Switch 17", "Switch 19",
            "Switch 21", "Switch 23", "Switch 25", "Switch 27", "Switch 29",
            "Switch 31", "Switch 33", "Switch 35", "Switch 37", "Switch 39",
        }
        self.assertEqual(turnouts, expected)
        levers = {
            (sensor.findtext("systemName") or "").strip()
            for sensor in root.iter("sensor")
            if (sensor.findtext("systemName") or "").endswith(":LEVER")
            and (sensor.findtext("systemName") or "").startswith("IS")
        }
        self.assertEqual(len(levers), 20)

    def test_gui_has_a_lever_icon_per_switch(self) -> None:
        gui = (SCRIPTS.parent / "ctc" / "GUIObjects.xml").read_text(encoding="utf-8")
        found = set()
        for match in __import__("re").findall(r'sensor="(IS\d+:LEVER)"', gui):
            found.add(match)
        self.assertEqual(len(found), 20)


if __name__ == "__main__":
    unittest.main()
