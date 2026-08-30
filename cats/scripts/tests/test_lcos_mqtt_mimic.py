from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]


def load_module():
    spec = importlib.util.spec_from_file_location(
        "lcos_mqtt_mimic", SCRIPTS / "lcos_mqtt_mimic.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class LcosMimicNamingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.m = load_module()
        cls.layout = cls.m.load_layout()

    def test_turnouts_use_ctc_numbers_and_cps(self) -> None:
        by_label = {t["label"]: t for t in self.layout["turnouts"]}
        self.assertIn("Switch 1", by_label)
        self.assertNotIn("Switch 100", by_label)
        self.assertEqual(by_label["Switch 1"]["plant"], "Brick")
        self.assertEqual(by_label["Switch 7"]["plant"], "Barn")
        self.assertEqual(by_label["Switch 13"]["plant"], "Engine House")
        self.assertEqual(by_label["Switch 9"]["plant"], "Engine House")
        self.assertNotIn("West Yard", {t["plant"] for t in self.layout["turnouts"]})

    def test_occupancy_uses_os_labels(self) -> None:
        labels = {b["label"] for b in self.layout["blocks"]}
        self.assertIn("Track 1", labels)
        self.assertIn("Track S-R", labels)
        self.assertIn("Track Barn", labels)
        self.assertNotIn("West Yard", {b["plant"] for b in self.layout["blocks"]})

    def test_heads_use_mast_prefix_and_cps(self) -> None:
        masts = {h["mast"] for h in self.layout["heads"]}
        self.assertIn("Mast 2L", masts)
        self.assertIn("Mast 2035", masts)
        self.assertNotIn("100L", masts)
        by_mast = {h["mast"]: h["plant"] for h in self.layout["heads"]}
        self.assertEqual(by_mast["Mast 2L"], "Brick")
        self.assertEqual(by_mast["Mast 8LA"], "Barn")
        self.assertEqual(by_mast["Mast 2035"], "Princess")

    def test_head_ids_are_packed_mqtt_leaves(self) -> None:
        ids = {h["id"] for h in self.layout["heads"]}
        self.assertIn("432", ids)
        self.assertIn("438", ids)
        self.assertNotIn("IH432", ids)
        by_id = {h["id"]: h for h in self.layout["heads"]}
        self.assertEqual(by_id["432"]["systemName"], "IH432")
        self.assertEqual(self.m._head_leaf("IH432"), "432")
        self.assertEqual(self.m._head_leaf("432"), "432")


if __name__ == "__main__":
    unittest.main()
