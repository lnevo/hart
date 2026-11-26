"""build_layout_le.build()'s record (LeBuild) and the steps that stop it. Uses staging drawn alone only, so it runs
without the three-level build."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_build_layout_le as T  # noqa: E402  loads the builder once

B = T.B


class BuildSteps(unittest.TestCase):
    def test_the_build_returns_its_parts_by_name(self) -> None:
        out = T.staging_alone()
        self.assertIsInstance(out, B.LeBuild)
        data, P, names, bands = out
        self.assertIsInstance(out.data, bytes)
        self.assertIs(out.panel, P)
        self.assertEqual(list(out.names), [B.band_key(bands[0][0])])
        self.assertEqual((out.data, out.names, out.bands), (data, names, bands))

    def test_a_page_with_no_le_labels_stops_before_drawing(self) -> None:
        page = {k: v for k, v in B.schematic()[1].items() if k != "le_labels"}
        with self.assertRaisesRegex(B.BuildError, "hold no le_labels"):
            B.build(as_live=True, page=page)

    def test_a_drawing_with_no_staging_band_first_stops(self) -> None:
        with self.assertRaisesRegex(B.BuildError, "must draw one band of level .* first; its bands are $"):
            B._staging_band([])

    def test_a_page_wide_band_align_stops_the_three_level_drawing(self) -> None:
        alone = T.staging_alone().panel
        with self.assertRaisesRegex(B.BuildError, "le_band_align"):
            B._draw_three_levels([], {}, "staging", alone, {"band_align": {"1": "left"}}, 1, B.plugin()[1])


if __name__ == "__main__":
    unittest.main()
