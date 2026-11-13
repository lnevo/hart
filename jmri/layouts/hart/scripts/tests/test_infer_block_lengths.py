"""infer_block_lengths: lap shares, the missing reference block, and the 2026-11-08 data."""
import csv
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import infer_block_lengths as m  # noqa: E402

BLOCKS = ["R", "A", "B"]


def lap(lap_index, times, step=32):
    return [dict(loco="L", log="x.log", step=str(step), lap_index=str(lap_index), block=b,
                 transit_s=str(t)) for b, t in times.items()]


class Shares(unittest.TestCase):
    def test_full_laps(self):
        rows = lap(0, {"R": 10, "A": 30, "B": 60}) + lap(1, {"R": 10, "A": 30, "B": 60})
        out = m.infer(rows, loop_mm=1000, ref="R", blocks=BLOCKS)
        self.assertAlmostEqual(out["A"][0], 300)
        self.assertAlmostEqual(out["B"][0], 600)
        self.assertAlmostEqual(out["R"][0], 100)

    def test_lap_without_reference_is_scaled(self):
        # second lap is slower and lacks R: its A/B shares must still sum to 1 - share(R)
        rows = lap(0, {"R": 10, "A": 30, "B": 60}) + lap(1, {"A": 60, "B": 120})
        shares = m.lap_shares(rows, ref="R", blocks=BLOCKS)
        self.assertEqual(len(shares["A"]), 2)
        for a, b in zip(shares["A"], shares["B"]):
            self.assertAlmostEqual(a + b, 0.9)

    def test_low_steps_and_partial_laps_ignored(self):
        rows = (lap(0, {"R": 10, "A": 30, "B": 60}) + lap(1, {"R": 99, "A": 1, "B": 1}, step=8)
                + lap(2, {"A": 5}))
        self.assertEqual(len(m.lap_shares(rows, ref="R", blocks=BLOCKS)["A"]), 1)

    def test_no_full_lap_raises(self):
        with self.assertRaises(ValueError):
            m.lap_shares(lap(0, {"A": 1, "B": 1}), ref="R", blocks=BLOCKS)


class RecordedRuns(unittest.TestCase):
    def test_2026_11_08_lengths_sum_to_plan_loop(self):
        rows = list(csv.DictReader(open(m.EVENTS, newline="")))
        out = m.infer(rows)
        self.assertEqual(set(out), set(m.SENSOR_ROWS))
        total = sum(v[0] for v in out.values())
        self.assertAlmostEqual(total / m.PLAN_LOOP_MM, 1.0, delta=0.002)
        # every block is pinned to within 5 cm across laps
        self.assertTrue(all(v[1] < 50 for v in out.values()), out)


    def test_pinned_puts_turnouts_on_the_plan_and_keeps_the_loop(self):
        rows = list(csv.DictReader(open(m.EVENTS, newline="")))
        out = m.pinned(m.infer(rows))
        self.assertAlmostEqual(sum(v[0] for v in out.values()), m.PLAN_LOOP_MM, delta=1)
        # the route starts where Switch 5's section starts, which is before Switch 5's points
        start = m.PLAN_TURNOUT_MM["Switch 5"] - out["Switch 5"][0] / 2
        pos = start
        for s in m.ROUTE_FROM_SW5:
            if s in m.PLAN_TURNOUT_MM:
                self.assertAlmostEqual(pos + out[s][0] / 2, m.PLAN_TURNOUT_MM[s], delta=10, msg=s)
            pos += out[s][0]
        # the barn crossover: Switch 7b's section centre about 4.15 m from Switch 5's points
        c7 = start + sum(out[s][0] for s in m.ROUTE_FROM_SW5[:2]) + out["Switch 7b"][0] / 2
        self.assertAlmostEqual(c7, 4146, delta=30)


if __name__ == "__main__":
    unittest.main()
