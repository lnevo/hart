"""Gallery captions: a description that only repeats the car type is left out."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "card_pipeline"))

import site_gallery  # noqa: E402


class Caption(unittest.TestCase):
    def record(self, description):
        return {"Type": "Hopper", "RoadName": "CSX", "RoadNumber": "379702", "Description": description}

    def test_repeated_type_is_dropped(self):
        entry = site_gallery.entry_for(self.record("Hopper"), "a.jpg", {})
        self.assertEqual(entry["caption"], "CSX · Hopper")

    def test_repeated_type_keeps_the_length(self):
        entry = site_gallery.entry_for(self.record("Hopper · 40'"), "a.jpg", {})
        self.assertEqual(entry["caption"], "CSX · Hopper · 40'")

    def test_real_description_is_kept(self):
        entry = site_gallery.entry_for(self.record("coke hopper"), "a.jpg", {})
        self.assertEqual(entry["caption"], "CSX · Hopper · coke hopper")


if __name__ == "__main__":
    unittest.main()
