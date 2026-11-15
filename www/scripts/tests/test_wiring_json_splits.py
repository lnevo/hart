"""build_wiring_json.py: the signal splits keep the lamp pins of the inventory the frozen RGB plan used (v85),
and say so, so the viewer does not link them into the newer published inventory."""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("build_wiring_json", ROOT / "www/scripts/build_wiring_json.py")
BW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BW)


class SplitsKeepOldPins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.splits = json.loads((ROOT / "www/data/signal-splits.json").read_text())
        cls.inventory = json.loads((ROOT / "www/data/wiring-inventory.json").read_text())

    def test_v8_splits_read_v85(self):
        self.assertEqual(BW.SPLITS_INVENTORY["signals_split_v8.xlsx"].name, "LCOS_Layout_Inventory_v85.xlsx")

    def test_published_splits_name_their_inventory(self):
        self.assertEqual(self.splits["source"]["inventory"], "v85")
        lamps = [s.get("lamps") for cp in self.splits["controlPoints"] for s in cp["signals"] if s.get("head") == "64R"]
        self.assertTrue(lamps and lamps[0], "64R (old upper-deck CP4) lost its lamp pins")

    def test_viewer_shows_pins_of_another_inventory_as_text(self):
        self.assertNotEqual(self.splits["source"]["inventory"], self.inventory["source"]["version"])
        js = (ROOT / "www/js/wiring.js").read_text()
        self.assertIn("spl.source.inventory !== inv.source.version", js)
        self.assertIn("lampRow({ lamps: lamps }, splitPinsPlain())", js)

    def test_published_inventory_is_the_newest(self):
        self.assertEqual(self.inventory["source"]["file"], BW.latest("LCOS_Layout_Inventory_v*.xlsx").name)


if __name__ == "__main__":
    unittest.main()
