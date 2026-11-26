"""tools/promo/tiktok_promo.py's frame formats and tools/promo/promo_shots.py's tables, without rendering."""
from __future__ import annotations

import dataclasses
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("tiktok_promo_fmt_test", ROOT / "tools/promo/tiktok_promo.py")
assert spec is not None and spec.loader is not None
TP = importlib.util.module_from_spec(spec)
sys.modules["tiktok_promo_fmt_test"] = TP  # dataclasses look the module up by name
spec.loader.exec_module(TP)
import promo_shots  # noqa: E402  (tiktok_promo put tools/promo on sys.path)


class Formats(unittest.TestCase):
    def test_each_format_is_its_size_with_the_stage_inside_it(self) -> None:
        self.assertEqual({k: (f.w, f.h) for k, f in TP.FORMATS.items()},
                         {"vertical": (1080, 1920), "landscape": (1920, 1080)})
        for f in TP.FORMATS.values():
            x0, y0, x1, y1 = f.stage
            self.assertTrue(0 <= x0 < x1 <= f.w and 0 <= y0 < y1 <= f.h, f.name)

    def test_landscape_puts_the_stage_right_of_the_caption_column(self) -> None:
        land, vert = TP.FORMATS["landscape"], TP.FORMATS["vertical"]
        self.assertTrue(land.land)
        self.assertFalse(vert.land)
        self.assertEqual(land.centre(), (1290, 540))
        self.assertEqual(vert.centre(), (540, 960))

    def test_a_format_cannot_change_under_a_render(self) -> None:
        with self.assertRaises(dataclasses.FrozenInstanceError):
            TP.FORMATS["vertical"].w = 1920  # type: ignore[misc]


class Tables(unittest.TestCase):
    def test_every_site_region_is_a_page_the_site_cut_captures(self) -> None:
        pages = set(promo_shots.PAGES.values())
        for sec in promo_shots.SITE_SECTIONS:
            for r in sec.regions:
                self.assertIn(r.page, promo_shots.CUT_PAGES["site"], (sec.name, r))
                self.assertIn(r.page, pages)
                self.assertTrue(0 <= r.x0 < r.x1 <= 1080 and 0 <= r.y0 < r.y1, (sec.name, r))

    def test_every_cut_reads_only_pages_that_are_captured(self) -> None:
        pages = set(promo_shots.PAGES.values())
        self.assertEqual(set(promo_shots.CUT_PAGES), set(TP.CUT_NAMES))
        for cut, stems in promo_shots.CUT_PAGES.items():
            self.assertLessEqual(stems, pages, cut)

    def test_quick_photo_focus_lies_inside_the_photo(self) -> None:
        for q in promo_shots.BUILD_QUICK:
            self.assertTrue(0 <= q.focus.x <= 1 and 0 <= q.focus.y <= 1, q)


if __name__ == "__main__":
    unittest.main()
