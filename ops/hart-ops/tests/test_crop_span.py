"""crop_span: the body-span steps and their fallbacks, on small drawn bands and column arrays."""
import sys
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "card_pipeline"))

import crop_span as span  # noqa: E402
from crop_settings import CROP  # noqa: E402

W = 1000  # band width: the body range is [350, 750) columns, a trusted silhouette 80 or more
WALL = 205
DARK = 60


def band(height: int = 100, fill: int = WALL) -> np.ndarray:
    return np.full((height, W), fill, dtype=np.uint8)


def flags_frac(*runs: tuple[int, int, float]) -> np.ndarray:
    """A per-column share array: each (first, last, share) run set, the rest 0."""
    out = np.zeros(W)
    for lo, hi, share in runs:
        out[lo : hi + 1] = share
    return out


def read(body_frac: np.ndarray, umean: np.ndarray | None = None, light: bool = False) -> span.BodyRead:
    return span.BodyRead(
        body_frac=body_frac,
        min_frac=CROP.span.dark_body_min_frac,
        umean=np.full(W, 100.0) if umean is None else umean,
        edge_med=float(WALL),
        light_car=light,
    )


class ReadBody(unittest.TestCase):
    def test_dark_car_uses_the_body_threshold(self):
        b = band()
        b[10:60, 300:700] = DARK
        r = span._read_body(b)
        self.assertFalse(r.light_car)
        self.assertEqual(r.min_frac, CROP.span.dark_body_min_frac)
        self.assertEqual(r.body_frac[500], 1.0)
        self.assertEqual(r.body_frac[100], 0.0)

    def test_light_car_threshold_sits_just_above_the_car_grey(self):
        b = band(fill=230)
        b[10:60, 300:700] = 160  # lighter than the body threshold: only the light-car rule sees it
        r = span._read_body(b)
        self.assertTrue(r.light_car)
        self.assertEqual(r.min_frac, CROP.span.light_body_min_frac)
        self.assertEqual(r.body_frac[500], 1.0)
        self.assertEqual(r.edge_med, 230.0)


class CoreBodySpan(unittest.TestCase):
    def test_a_body_in_range_needs_no_fallback(self):
        b = band()
        b[10:60, 300:700] = DARK
        self.assertEqual(span._core_body_span(b), (300, 699))

    def test_too_wide_body_takes_the_first_denser_rule_that_narrows_it(self):
        b = band()
        b[10:33, 50:950] = DARK  # about half the mid band: passes the 0.5 rule, so 0.5 does not narrow
        b[10:41, 200:800] = DARK  # two thirds: the 0.55 rule keeps only these columns
        self.assertEqual(span._core_body_span(b), (200, 799))

    def test_too_wide_body_falls_back_to_the_upper_band_mean(self):
        b = band(fill=100)  # dark across the whole band: body and deck rules see every column
        b[0:42, 250:750] = 50  # the car's upper body is darker than the rest
        self.assertEqual(span._core_body_span(b), (250, 749))

    def test_narrow_trusted_body_is_widened_by_the_deck_lettering(self):
        b = band()
        b[12:26, 300:700] = DARK  # lettering: under the body share in the mid band, over the deck core share
        b[10:60, 450:550] = DARK  # body block
        self.assertEqual(span._core_body_span(b), (300, 699))


class TooWideSteps(unittest.TestCase):
    def test_tighter_rule_skips_a_rule_that_does_not_narrow(self):
        body = flags_frac((0, 999, 0.52), (200, 799, 0.57))
        self.assertEqual(span._tighter_body_span(body, 999, W), (200, 799))

    def test_tighter_rule_gives_none_when_no_rule_narrows(self):
        self.assertIsNone(span._tighter_body_span(flags_frac((0, 999, 0.52)), 999, W))

    def test_tighter_rule_rejects_a_span_below_the_body_range(self):
        body = flags_frac((0, 999, 0.52), (450, 549, 0.9))
        self.assertIsNone(span._tighter_body_span(body, 999, W))

    def test_steps_run_in_order_and_stop_once_in_range(self):
        with mock.patch.object(span, "_tighter_body_span", return_value=None) as tighter, \
                mock.patch.object(span, "_deck_lettering_span", return_value=(100, 600)) as deck, \
                mock.patch.object(span, "_umean_cut_span") as umean:
            self.assertEqual(span._narrow_wide_span(band(), read(np.ones(W)), 0, 999), (100, 600, False))
        tighter.assert_called_once()
        deck.assert_called_once()
        umean.assert_not_called()

    def test_upper_mean_span_out_of_range_keeps_the_wide_span(self):
        with mock.patch.object(span, "_tighter_body_span", return_value=None), \
                mock.patch.object(span, "_deck_lettering_span", return_value=None), \
                mock.patch.object(span, "_umean_cut_span", return_value=(400, 500)):
            self.assertEqual(span._narrow_wide_span(band(), read(np.ones(W)), 0, 999), (0, 999, False))

    def test_a_span_in_range_is_left_alone(self):
        with mock.patch.object(span, "_tighter_body_span") as tighter:
            self.assertEqual(span._narrow_wide_span(band(), read(np.ones(W)), 300, 699), (300, 699, False))
        tighter.assert_not_called()


class TooNarrowSteps(unittest.TestCase):
    def test_upper_mean_span_skips_deck_and_bridge(self):
        with mock.patch.object(span, "_deck_core_span") as deck, \
                mock.patch.object(span, "_bridge_outboard_runs") as bridge:
            self.assertEqual(span._widen_narrow_span(band(), read(np.zeros(W)), 480, 500, used_umean=True), (480, 500))
        deck.assert_not_called()
        bridge.assert_not_called()

    def test_trusted_silhouette_stops_after_the_deck_step(self):
        with mock.patch.object(span, "_deck_core_span", return_value=(480, 600)), \
                mock.patch.object(span, "_bridge_outboard_runs") as bridge, \
                mock.patch.object(span, "_span_from_flags") as flags:
            self.assertEqual(span._widen_narrow_span(band(), read(np.zeros(W)), 450, 550, used_umean=False), (480, 600))
        bridge.assert_not_called()
        flags.assert_not_called()

    def test_untrusted_span_is_bridged(self):
        with mock.patch.object(span, "_deck_core_span", return_value=(480, 500)), \
                mock.patch.object(span, "_bridge_outboard_runs", return_value=(250, 700)):
            self.assertEqual(span._widen_narrow_span(band(), read(np.zeros(W)), 480, 500, used_umean=False), (250, 700))

    def test_light_car_last_step_uses_the_high_upper_band_percentile(self):
        with mock.patch.object(span, "_deck_core_span", return_value=(480, 500)), \
                mock.patch.object(span, "_bridge_outboard_runs", return_value=None), \
                mock.patch.object(span, "_span_from_flags", return_value=(480, 500)), \
                mock.patch.object(span, "_umean_cut_span", return_value=(300, 700)) as cut:
            got = span._widen_narrow_span(band(), read(np.zeros(W), light=True), 480, 500, used_umean=False)
        self.assertEqual(got, (300, 700))
        cut.assert_called_once()
        self.assertEqual(cut.call_args.args[2:], (CROP.tone.light_umean_pctile, CROP.tone.light_umean_pad))

    def test_dark_car_skips_the_light_step(self):
        with mock.patch.object(span, "_deck_core_span", return_value=(480, 500)), \
                mock.patch.object(span, "_bridge_outboard_runs", return_value=None), \
                mock.patch.object(span, "_span_from_flags", return_value=(480, 500)), \
                mock.patch.object(span, "_umean_cut_span") as cut:
            self.assertEqual(span._widen_narrow_span(band(), read(np.zeros(W)), 480, 500, used_umean=False), (480, 500))
        cut.assert_not_called()


class Widen(unittest.TestCase):
    def test_wider_candidate_in_range_is_taken(self):
        self.assertEqual(span._maybe_widen_span(450, 550, 100, 300, 700, W), (300, 700, 400))

    def test_too_wide_or_narrower_candidate_is_refused(self):
        self.assertEqual(span._maybe_widen_span(450, 550, 100, 0, 999, W), (450, 550, 100))
        self.assertEqual(span._maybe_widen_span(400, 600, 200, 450, 550, W), (400, 600, 200))

    def test_ratio_cap_applies_once_the_span_is_a_quarter_wide(self):
        self.assertEqual(span._maybe_widen_span(300, 600, 300, 200, 700, W), (300, 600, 300))  # 500 > 1.35 x 300
        self.assertEqual(span._maybe_widen_span(300, 600, 300, 250, 640, W), (250, 640, 390))


class Bridge(unittest.TestCase):
    def test_runs_either_side_of_the_centre_are_bridged(self):
        body = flags_frac((200, 299, 1.0), (450, 549, 1.0), (700, 799, 1.0))
        self.assertEqual(span._bridge_outboard_runs(body, 0.35, W), (200, 799))

    def test_left_bridge_is_tried_before_the_right(self):
        body = flags_frac((100, 299, 1.0), (450, 549, 1.0), (700, 799, 1.0))
        self.assertEqual(span._bridge_outboard_runs(body, 0.35, W), (100, 549))

    def test_no_run_at_the_centre_gives_none(self):
        self.assertIsNone(span._bridge_outboard_runs(flags_frac((100, 299, 1.0)), 0.35, W))
        self.assertIsNone(span._bridge_outboard_runs(np.zeros(W), 0.35, W))


class EdgeSteps(unittest.TestCase):
    def test_peel_drops_bare_rail_columns_and_keeps_trucks(self):
        deck = np.zeros(W)
        upper = np.zeros(W)
        lower = flags_frac((150, 199, 0.2), (200, 299, 0.5), (700, 799, 0.5), (800, 849, 0.2))
        deck[300:700] = 1.0
        # Left: rail (0.2) is peeled and trucks (0.5) stop it. Right: trucks peel too, up to the
        # 80-column cap (track_peel_max_frac of the width).
        self.assertEqual(span._peel_bare_track(band(), 150, 849, deck, lower, upper), (200, 769))

    def test_crane_boom_columns_are_added_within_reach(self):
        b = band()
        b[15:40, 420:450] = DARK  # boom above the deck, outside the body columns
        body = flags_frac((450, 600, 1.0))
        self.assertEqual(span._extend_crane_arms(b, 450, 600, body), (420, 600))

    def test_strong_span_finds_the_dark_body_and_drops_its_shadow_edges(self):
        b = band()
        b[0:40, 300:700] = DARK
        self.assertEqual(span._strong_horizontal_span(b), (300, 699))

    def test_strong_span_of_an_empty_band_starts_past_the_vignette_and_shrinks_away(self):
        skip = CROP.span.strong_edge_skip
        self.assertEqual(span._strong_horizontal_span(band()), (W - skip, W - skip))


if __name__ == "__main__":
    unittest.main()
