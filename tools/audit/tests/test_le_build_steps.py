"""build_layout_le.build()'s record (LeBuild) and the steps that stop it. Uses staging drawn alone only, so it runs
without the three-level build."""
from __future__ import annotations

import contextlib
import functools
import importlib.util
import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _builder():
    """build_layout_le, loaded once per process (shared with test_build_layout_le when both run in one process).
    This file does not import test_build_layout_le, so it stays out of check.sh's LE_TESTS job."""
    if "build_layout_le" in sys.modules:
        return sys.modules["build_layout_le"]
    spec = importlib.util.spec_from_file_location("build_layout_le", ROOT / "tools/schematic/build_layout_le.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_layout_le"] = mod
    spec.loader.exec_module(mod)
    return mod


B = _builder()


@functools.lru_cache(maxsize=None)
def staging_alone():
    """Staging drawn alone, built once for this file."""
    with contextlib.redirect_stdout(io.StringIO()):
        return B.build(levels="staging", as_live=True)


class BuildSteps(unittest.TestCase):
    def test_the_build_returns_its_parts_by_name(self) -> None:
        out = staging_alone()
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
        alone = staging_alone().panel
        with self.assertRaisesRegex(B.BuildError, "le_band_align"):
            B._draw_three_levels([], {}, "staging", alone, {"band_align": {"1": "left"}}, 1, B.plugin()[1])


if __name__ == "__main__":
    unittest.main()
