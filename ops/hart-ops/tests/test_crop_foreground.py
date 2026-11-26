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


class CropSettingsTest(unittest.TestCase):
    def test_settings_are_frozen(self) -> None:
        import dataclasses

        with self.assertRaises(dataclasses.FrozenInstanceError):
            crop.CROP.tone.track_thresh = 1  # type: ignore[misc]

    def test_tuned_values_are_kept(self) -> None:
        c = crop.CROP
        self.assertEqual((c.frame.y0, c.frame.y1, c.frame.min_rotation_deg), (0.36, 0.90, 0.05))
        self.assertEqual((c.tone.content_thresh, c.tone.track_thresh, c.tone.body_thresh), (238, 95, 120))
        self.assertEqual(c.tone.fleet_lightbox_wall, (212.8, 208.8, 203.8))
        self.assertEqual(c.span.full_dark_frac, 0.25)


if __name__ == "__main__":
    unittest.main()
