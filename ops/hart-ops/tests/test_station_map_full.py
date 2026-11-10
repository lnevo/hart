"""The whole-railroad station map: where the Barn crossover (switch 7) is drawn."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "publications"))
import rebuild_station_map_full as full  # noqa: E402


class BarnCrossover(unittest.TestCase):
    def test_main_east_end_sits_under_switch_9(self):
        top, bottom = full.barn_crossover(1030, 370, 490)
        self.assertEqual(bottom, (1030, 490))

    def test_runs_at_45_degrees_like_switch_23(self):
        top, bottom = full.barn_crossover(1030, 370, 490)
        self.assertEqual(top[1], 370)
        self.assertEqual(bottom[0] - top[0], bottom[1] - top[1])


if __name__ == "__main__":
    unittest.main()
