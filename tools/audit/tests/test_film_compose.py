"""compose of the CATS and Layout Editor films (tools/ctc_history/film_cats.py, film_le.py): where a screenshot lands
on the canvas, how it is scaled, and the caption band, on small made-up screenshots."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/ctc_history"))
import film_cats  # noqa: E402
import film_common  # noqa: E402
import film_le  # noqa: E402

RED = (200, 0, 0)


class Shot(unittest.TestCase):
    """A made-up screenshot in a temporary folder, and the built-in font."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.font = film_common.load_font(22, files=())

    def shot(self, size: tuple[int, int], colour: tuple[int, int, int] = RED) -> Path:
        path = self.dir / "shot.png"
        Image.new("RGB", size, colour).save(path)
        return path

    def assertCaptionInBand(self, canvas: Image.Image, top: int) -> None:
        """The band from `top` down holds text centred across the canvas, its strongest pixels in CAPTION_INK
        (the font smooths its edges, so only the strongest match exactly or nearly)."""
        band = canvas.crop((0, top, canvas.width, canvas.height))
        ground = band.getpixel((0, band.height - 1))
        ink = [(x, band.getpixel((x, y))) for y in range(band.height) for x in range(band.width)
               if band.getpixel((x, y)) != ground]
        self.assertTrue(ink, "no caption in the band")
        xs = [x for x, _c in ink]
        self.assertLessEqual(abs(min(xs) + max(xs) - canvas.width), 4, "the caption is not centred")
        strongest = max((c for _x, c in ink), key=sum)
        for got, want in zip(strongest, film_common.CAPTION_INK):
            self.assertLessEqual(abs(got - want), 8, strongest)


class LayoutEditor(Shot):
    def test_a_wide_shot_is_fitted_and_centred_over_the_caption_band(self) -> None:
        canvas = film_le.compose(self.shot((100, 50)), "20 May: first panel", self.font)
        self.assertEqual(canvas.size, film_le.CANVAS)
        # inner box 1256 x 656: the shot scales by 12.56 to 1256 x 628, at x 12 and y 8 + 14
        self.assertEqual(canvas.getpixel((12, 22)), RED)
        self.assertEqual(canvas.getpixel((1267, 649)), RED)
        self.assertEqual(canvas.getpixel((11, 22)), film_le.BG)
        self.assertEqual(canvas.getpixel((640, 21)), film_le.BG)
        top = film_le.CANVAS[1] - film_le.CAPTION_H
        self.assertEqual(canvas.getpixel((0, top)), film_le.CAPTION_BG)
        self.assertCaptionInBand(canvas, top)

    def test_a_missing_shot_is_a_film_error(self) -> None:
        with self.assertRaisesRegex(film_common.FilmError, "gone.png"):
            film_le.compose(self.dir / "gone.png", "x", self.font)


class Cats(Shot):
    def test_a_boxed_shot_is_cropped_scaled_and_anchored_top_left(self) -> None:
        canvas = film_cats.compose(self.shot((400, 200)), (0, 0, 100, 50), "First draft", self.font)
        self.assertEqual(canvas.size, film_cats.CANVAS)
        # the box scales by SCALE (0.88) to 88 x 44
        self.assertEqual(canvas.getpixel((0, 0)), RED)
        self.assertEqual(canvas.getpixel((87, 43)), RED)
        self.assertEqual(canvas.getpixel((89, 10)), film_cats.BG)
        self.assertEqual(canvas.getpixel((10, 45)), film_cats.BG)
        self.assertCaptionInBand(canvas, film_cats.CANVAS[1] - film_cats.CAPTION_H)

    def test_a_whole_shot_is_fitted_but_never_enlarged(self) -> None:
        small = film_cats.compose(self.shot((100, 100)), None, "Live", self.font)
        self.assertEqual(small.getpixel((99, 99)), RED)
        self.assertEqual(small.getpixel((100, 50)), film_cats.BG)
        wide = film_cats.compose(self.shot((2560, 400)), None, "Live", self.font)
        self.assertEqual(wide.getpixel((1279, 199)), RED)        # halved to the canvas width
        self.assertEqual(wide.getpixel((640, 201)), film_cats.BG)

    def test_the_caption_band_hides_a_tall_shot(self) -> None:
        canvas = film_cats.compose(self.shot((400, 2000)), (0, 0, 400, 2000), "x", self.font)
        top = film_cats.CANVAS[1] - film_cats.CAPTION_H
        self.assertEqual(canvas.getpixel((10, top - 1)), RED)
        self.assertEqual(canvas.getpixel((10, top + 1)), film_cats.BG)


if __name__ == "__main__":
    unittest.main()
