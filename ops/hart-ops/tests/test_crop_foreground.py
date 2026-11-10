"""Crop detection must ignore a dark table strip below the track."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "card_pipeline"))

import crop_car_image as crop  # noqa: E402


class TrimForeground(unittest.TestCase):
    def test_cuts_full_width_dark_strip(self):
        region = np.full((100, 200), 220, dtype=np.uint8)
        region[60:64, 20:180] = 40   # rails: dark but not full width
        region[80:, :] = 10          # table
        cut = crop._trim_foreground(region).shape[0]
        self.assertTrue(70 <= cut <= 80, cut)  # edge smoothing may take a few rows

    def test_leaves_normal_photo_alone(self):
        region = np.full((100, 200), 220, dtype=np.uint8)
        region[60:64, 20:180] = 40
        self.assertEqual(crop._trim_foreground(region).shape[0], 100)

    def test_cuts_the_fade_above_the_table(self):
        region = np.full((200, 200), 220, dtype=np.uint8)
        region[40:44, 20:180] = 40                      # rails
        for i, y in enumerate(range(150, 170)):          # backdrop edge fading to black
            region[y, : int(10 * (i + 1))] = 20
        region[170:, :] = 10
        cut = crop._trim_foreground(region).shape[0]
        self.assertLess(cut, 155)
        self.assertGreater(cut, 44)


if __name__ == "__main__":
    unittest.main()
