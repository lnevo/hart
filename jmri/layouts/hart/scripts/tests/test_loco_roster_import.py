from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "loco_roster_import.py"
spec = importlib.util.spec_from_file_location("loco_roster_import", SCRIPT)
imp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(imp)

ENTRY = {"id": "NW 1776", "road_name": "NW", "road_number": "1776", "mfg": "Atlas",
         "model": "SW1200", "dcc_address": "1776", "long_address": True,
         "image": "preference:resources/roster/1776.jpg", "comment": ""}


class PlanTests(unittest.TestCase):
    def test_new_entry_is_created(self):
        self.assertEqual([a["action"] for a in imp.plan([ENTRY], set())], ["create"])

    def test_existing_id_is_skipped(self):
        self.assertEqual([a["action"] for a in imp.plan([ENTRY], {"NW 1776"})], ["skip"])

    def test_describe_names_address_type(self):
        text = imp.describe(imp.plan([ENTRY], set())[0])
        self.assertIn("1776 (long)", text)

    def test_cpython_run_does_not_touch_jmri(self):
        self.assertFalse(imp._jmri_available())


if __name__ == "__main__":
    unittest.main()
