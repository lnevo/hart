"""Backdrop clean-up for loco photos: neutral gradient, loco kept, stray wedge dropped."""
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "card_pipeline"))

import loco_backdrop  # noqa: E402


def synthetic() -> Image.Image:
    a = np.zeros((1050, 1400, 3))
    a[...] = (185, 178, 160)                      # warm backdrop
    a[300:320, :, :] -= 25                        # a crease
    a[100:200, 0:60, :] = 30                      # dark corner wedge, not touching the loco
    a[500:700, 300:1100, :] = (60, 70, 120)       # the loco
    a[700:760, :, :] = (70, 55, 45)               # track
    return Image.fromarray(np.uint8(a))


class CleanTests(unittest.TestCase):
    def setUp(self):
        self.out = np.asarray(loco_backdrop.clean(synthetic(), (0, 0, 1400, 1050)), float)

    def test_backdrop_is_neutral_and_even(self):
        for y, x in ((20, 20), (250, 700), (310, 700), (950, 1300)):
            r, g, b = self.out[y, x]
            self.assertLess(max(r, g, b) - min(r, g, b), 3, (y, x))
        self.assertLess(abs(self.out[310, 700, 0] - self.out[250, 700, 0]), 8)  # crease gone

    def test_stray_wedge_is_dropped(self):
        self.assertGreater(self.out[150, 30].mean(), 150)

    def test_loco_and_track_are_kept(self):
        self.assertLess(self.out[600, 700, 0], 100)   # loco still dark blue
        self.assertLess(self.out[730, 700].mean(), 110)


if __name__ == "__main__":
    unittest.main()
