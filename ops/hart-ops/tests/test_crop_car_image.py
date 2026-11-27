"""crop_car_image and its parts (crop_runs, crop_span, crop_level) on drawn light-box photos."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "card_pipeline"))

import crop_car_image as crop  # noqa: E402
import crop_level  # noqa: E402
import crop_runs  # noqa: E402
from crop_settings import CROP  # noqa: E402

WALL = (205, 205, 205)
BODY = (60, 60, 60)
CAR_X = (300, 900)
CAR_Y = (400, 560)


def photo(tilt: float = 0.0) -> Image.Image:
    """A 1200 x 800 light-box photo: a dark car body on two trucks over a rail line."""
    img = Image.new("RGB", (1200, 800), WALL)
    d = ImageDraw.Draw(img)
    d.rectangle([CAR_X[0], CAR_Y[0], CAR_X[1], CAR_Y[1]], fill=BODY)
    for x in (330, 780):
        d.rectangle([x, CAR_Y[1], x + 90, 600], fill=(40, 40, 40))
    d.rectangle([100, 600, 1100, 612], fill=(30, 30, 30))
    return img.rotate(tilt, resample=Image.BICUBIC, fillcolor=WALL) if tilt else img


class Runs(unittest.TestCase):
    def test_runs_are_the_true_stretches(self):
        flags = np.array([0, 1, 1, 0, 0, 1, 0, 1, 1, 1], dtype=bool)
        self.assertEqual(crop_runs._runs_from_flags(flags), [(1, 2), (5, 5), (7, 9)])

    def test_close_runs_merge_and_far_runs_stay_apart(self):
        self.assertEqual(crop_runs._merge_close_runs([(0, 4), (6, 9), (30, 40)], max_gap=3), [(0, 9), (30, 40)])
        self.assertEqual(crop_runs._merge_close_runs([], max_gap=3), [])

    def test_span_is_first_to_past_last(self):
        self.assertEqual(crop_runs._span(np.array([0, 0, 1, 0, 1, 0], dtype=bool)), (2, 5))
        self.assertEqual(crop_runs._span(np.zeros(4, dtype=bool)), (0, 0))

    def test_span_from_flags_takes_the_run_around_the_centre_when_none_is_significant(self):
        flags = np.zeros(1000, dtype=bool)
        flags[100:110] = True
        flags[495:505] = True
        self.assertEqual(crop_runs._span_from_flags(flags), (495, 504))


class Detect(unittest.TestCase):
    def test_box_holds_the_car_and_its_trucks(self):
        x0, y0, x1, y1 = crop.detect_car_bbox(photo())
        self.assertLessEqual(x0, CAR_X[0])
        self.assertGreaterEqual(x1, CAR_X[1])
        self.assertLessEqual(y0, CAR_Y[0])
        self.assertGreaterEqual(y1, 600)
        self.assertLess(x1 - x0, 1000)  # the rail stubs past the couplers are not the car

    def test_small_box_is_flagged_for_review(self):
        self.assertEqual(crop.assess_crop((0, 0, 600, 300), (1200, 800)), "ok")
        self.assertEqual(crop.assess_crop((0, 0, 200, 300), (1200, 800)), "review")
        self.assertEqual(crop.assess_crop((0, 0, 600, 90), (1200, 800)), "review")


class Level(unittest.TestCase):
    def test_a_level_photo_is_not_turned(self):
        self.assertAlmostEqual(crop_level.estimate_rotation(photo()), 0.0, places=9)
        img, angle = crop_level._level_image(photo())
        self.assertEqual(img.size, (1200, 800))
        self.assertLess(abs(angle), CROP.frame.min_rotation_deg)

    def test_a_tilted_photo_is_turned_back(self):
        angle = crop_level.estimate_rotation(photo(tilt=1.0))
        self.assertLess(angle, -0.5)
        self.assertGreater(angle, -1.5)

    def test_backdrop_colour_follows_the_image_mode(self):
        img = photo()
        self.assertEqual(crop_level._backdrop_color(img), WALL)
        self.assertEqual(crop_level._backdrop_color(img.convert("RGBA")), WALL + (255,))
        self.assertEqual(crop_level._backdrop_color(img.convert("L")), 205)

    def test_white_balance_moves_the_wall_to_the_target(self):
        out = crop_level.match_lightbox_white_balance(Image.new("RGB", (100, 100), (210, 200, 220)), (200, 200, 200))
        self.assertEqual(out.getpixel((50, 5)), (200, 200, 200))

    def test_white_balance_gain_is_capped(self):
        out = crop_level.match_lightbox_white_balance(Image.new("RGB", (100, 100), (100, 100, 100)), (200, 200, 200))
        self.assertEqual(out.getpixel((50, 5)), (120, 120, 120))


class Process(unittest.TestCase):
    def test_process_image_writes_the_crop_and_reports_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "IMG_0001.png", Path(tmp) / "out" / "IMG_0001.png"
            photo().save(src)
            meta = crop.process_image(src, dst)
            with Image.open(dst) as written:
                self.assertEqual(written.size, meta["output_size"])
        self.assertEqual(meta["source"], "IMG_0001.png")
        self.assertEqual(meta["crop_status"], "ok")
        self.assertAlmostEqual(meta["rotation_deg"], 0.0, places=9)
        x0, _, x1, _ = meta["bbox"]
        w, _ = meta["output_size"]
        self.assertGreater(w, x1 - x0)  # tie margins past the couplers
        self.assertEqual(set(meta), set(crop.Crop.__annotations__))

    def test_fixed_size_window_is_padded_with_the_wall(self):
        img = crop._crop_at_fixed_size(photo(), 100.0, 400.0, 600, 200)
        self.assertEqual(img.size, (600, 200))
        self.assertEqual(img.getpixel((5, 100)), WALL)  # past the photo's left edge
        self.assertEqual(img.getpixel((500, 100)), BODY)  # photo x 500 sits at window x 500


class RowBandQuirk(unittest.TestCase):
    """detect_car_bbox tests index arrays with .any(): a body found only in row 0 counts as none.

    Kept as main has it so crop boxes stay the same; these tests pin it.
    """

    def test_center_body_only_in_row_0_falls_back_to_the_track_rows(self):
        region = np.full((50, 200), 205, dtype=np.uint8)
        region[40:46, 0:40] = 30  # track, outside the centre band
        region[0, 50:150] = 100  # the only centre body row is row 0 (body grey, not track dark)
        self.assertEqual(crop._row_band(region), (40, 46))

    def test_left_band_body_only_in_row_0_does_not_raise_the_top(self):
        region = np.full((50, 200), 205, dtype=np.uint8)
        region[0, 16:64] = 60  # left band, row 0 only
        self.assertEqual(crop._left_end_top(region, 5), 5)
        region[1, 16:64] = 60  # a match past row 0 is taken
        self.assertEqual(crop._left_end_top(region, 5), 0)


class TiePitch(unittest.TestCase):
    def gray_with_ties(self, pitch: int) -> np.ndarray:
        """Ties every ``pitch`` columns, darkest at the tie centre so the smoothed profile peaks there."""
        gray = np.full((40, 1040), 205, dtype=np.uint8)
        for offset, rows in ((0, 40), (1, 20), (-1, 20), (2, 10), (-2, 10)):
            gray[:rows, pitch + offset :: pitch] = 30
        return gray

    def test_pitch_blends_the_tie_peaks_with_the_car_width(self):
        # Peaks every 30 px, width pitch 1040 / 52 = 20: blend 25, over the floor 0.82 x 20.
        self.assertEqual(crop._estimate_tie_pitch(self.gray_with_ties(30), 0, 1040, 0, 40), 25.0)

    def test_without_enough_peaks_the_pitch_is_the_clipped_width_pitch(self):
        plain = np.full((40, 1040), 205, dtype=np.uint8)
        self.assertEqual(crop._estimate_tie_pitch(plain, 0, 1040, 0, 40), 20.0)
        self.assertEqual(crop._estimate_tie_pitch(plain, 0, 100, 0, 40), CROP.frame.tie_pitch_width_range[0])

    def test_an_empty_image_is_an_error(self):
        with self.assertRaises(crop.CardPipelineError):
            crop._estimate_tie_pitch(np.zeros((0, 0), dtype=np.uint8), 0, 10, 0, 10)


class CenteredCropBox(unittest.TestCase):
    def test_box_is_centred_on_the_car_with_tie_margins(self):
        gray = np.full((800, 1200), 205, dtype=np.uint8)
        left, top, right, bottom = crop._centered_crop_box(gray, 400, 400, 800, 600)
        self.assertEqual((left + right) / 2, 600)
        pad = int(CROP.frame.tie_margin_count * CROP.frame.tie_pitch_width_range[0])
        self.assertEqual((left, right), (400 - pad, 800 + pad))
        self.assertEqual((top, bottom), (400 - int(200 * CROP.frame.pad_top), 600 + int(200 * CROP.frame.pad_bottom)))

    def test_long_car_side_margin_is_capped(self):
        gray = np.full((800, 1200), 205, dtype=np.uint8)
        left, _, right, _ = crop._centered_crop_box(gray, 200, 400, 1000, 600)
        pad = int(800 * CROP.frame.long_car_pad_x)
        self.assertEqual((left, right), (200 - pad, 1000 + pad))

    def test_box_at_the_photo_edge_is_clamped(self):
        gray = np.full((800, 1200), 205, dtype=np.uint8)
        left, _, right, _ = crop._centered_crop_box(gray, 0, 400, 300, 600)
        self.assertEqual(left, 0)
        self.assertLessEqual(right, 1200)


class Settings(unittest.TestCase):
    def test_top_edge_bands_are_ordered_fractions(self):
        top = CROP.top
        for band in (top.center_band, top.left_band, top.handbrake_band, top.handbrake_frac):
            with self.subTest(band=band):
                self.assertTrue(0.0 <= band[0] < band[1] <= 1.0)


if __name__ == "__main__":
    unittest.main()
