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
        mtt = [
            (el.findtext("systemName") or "").strip()
            for el in root.iter("turnout")
            if (el.findtext("systemName") or "").startswith("MTT")
        ]
        self.assertEqual(leftover, [])
        self.assertEqual(old_ctc, [])
        self.assertEqual(mtt, [])


if __name__ == "__main__":
    unittest.main()
