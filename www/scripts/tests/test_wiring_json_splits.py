"""build_wiring_json.py: the signal splits keep the lamp pins of the inventory the frozen RGB plan used (v85)."""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("build_wiring_json", ROOT / "www/scripts/build_wiring_json.py")
BW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BW)
SPLITS = json.loads((ROOT / "www/data/signal-splits.json").read_text())
INVENTORY = json.loads((ROOT / "www/data/wiring-inventory.json").read_text())


class SplitsKeepOldPins(unittest.TestCase):
    def test_default_split_inventory_is_v85(self):
        self.assertEqual(BW.SPLITS_INVENTORY.name, "LCOS_Layout_Inventory_v85.xlsx")

    def test_published_splits_name_v85_and_keep_upper_deck_lamps(self):
        self.assertEqual(SPLITS["source"]["inventory"], "v85")
        lamps = [s.get("lamps") for cp in SPLITS["controlPoints"] for s in cp["signals"] if s.get("head") == "64R"]
        self.assertTrue(lamps and lamps[0], "64R (old upper-deck CP4) lost its lamp pins")

    def test_published_inventory_is_the_newest(self):
        self.assertEqual(INVENTORY["source"]["file"], BW.latest("LCOS_Layout_Inventory_v*.xlsx").name)


if __name__ == "__main__":
    unittest.main()
