"""--check on the two layout index builders: the committed JSON is current, and a stale copy fails.

A mast rename (16R, PR #441) used to leave www/data/layout-index.json behind
until someone rebuilt it by hand; tools/check.sh now runs both checks.
"""
from __future__ import annotations

import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_cats_layout_index as cats_index  # noqa: E402
import build_layout_index as le_index  # noqa: E402


class LayoutIndexCheckTest(unittest.TestCase):
    def check(self, mod, out: Path | None = None) -> tuple[int, str]:
        err = io.StringIO()
        patch = mock.patch.object(mod, "OUT_JSON", out) if out else contextlib.nullcontext()
        with patch, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            return mod.main(["--check"]), err.getvalue()

    def stale_copy(self, src: Path) -> Path:
        tmp = Path(tempfile.mkdtemp(dir=src.parent))
        self.addCleanup(shutil.rmtree, tmp)
        dst = tmp / src.name
        dst.write_text(src.read_text(encoding="utf-8").replace("Mast 2L", "Mast 2LX", 1), encoding="utf-8")
        return dst

    def test_committed_indexes_are_current(self) -> None:
        for mod in (le_index, cats_index):
            with self.subTest(index=mod.OUT_JSON.name):
                self.assertEqual(self.check(mod), (0, ""))

    def test_a_stale_index_fails(self) -> None:
        for mod in (le_index, cats_index):
            with self.subTest(index=mod.OUT_JSON.name):
                rc, err = self.check(mod, self.stale_copy(mod.OUT_JSON))
                self.assertEqual(rc, 1)
                self.assertIn("is stale", err)

    def test_a_change_to_what_the_png_is_drawn_from_fails(self) -> None:
        # The JSON records a hash of the render inputs; a renderer (or geometry) change must show up.
        for mod in (le_index, cats_index):
            with self.subTest(index=mod.OUT_JSON.name):
                tmp = Path(tempfile.mkdtemp())
                self.addCleanup(shutil.rmtree, tmp)
                render = tmp / mod.RENDER.name
                render.write_bytes(mod.RENDER.read_bytes() + b"\n# changed\n")
                with mock.patch.object(mod, "RENDER", render):
                    rc, err = self.check(mod)
                self.assertEqual(rc, 1)
                self.assertIn("is stale", err)


if __name__ == "__main__":
    unittest.main()
