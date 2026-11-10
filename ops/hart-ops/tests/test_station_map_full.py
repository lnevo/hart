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


class EngineLead(unittest.TestCase):
    EH = {3: 300, 2: 258, 1: 216}

    def test_eh3_between_9_and_11_is_half_its_first_length(self):
        sw13, sw11, _, _ = full.engine_lead(1030, 370, self.EH)
        self.assertEqual(sw11, (1030 + 132, 300))
        self.assertEqual(sw13[1], 370)

    def test_both_diverging_lines_run_at_45_degrees_parallel_with_switch_7(self):
        sw13, sw11, eh1, eh2 = full.engine_lead(1030, 370, self.EH)
        for low, high in ((sw13, sw11), (sw13, eh1), ((1030, 300), eh2)):
            self.assertEqual(low[0] - high[0], low[1] - high[1])
        top, bottom = full.barn_crossover(1030, 370, 490)
        self.assertEqual(bottom[0] - top[0], bottom[1] - top[1])  # same slope, same hand


if __name__ == "__main__":
    unittest.main()
