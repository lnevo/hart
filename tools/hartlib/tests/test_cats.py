"""hartlib.cats: the desk plate words build_cats_panel.py writes for each block."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import cats  # noqa: E402


class StationPlate(unittest.TestCase):
    def test_the_plate_is_the_switch_number_or_the_first_word_of_the_track(self) -> None:
        self.assertEqual("39", cats.station_plate("OS Switch 39"))
        self.assertEqual("West", cats.station_plate("Track West Ext"))
        self.assertEqual("S-1", cats.station_plate("Track S-1"))


if __name__ == "__main__":
    unittest.main()
