"""site_views: the files the site build makes instead of committing (ADR-036), and the PNG render stamp.

Each view is gitignored and untracked; a builder that fails or returns nothing is an error naming the view; the
local preview refresh writes every view it can and removes the old copy of one it cannot, so no page reads a stale
file; serve_portal says so at start. png_stamp writes, reads and checks the stamp the layout PNGs carry.
"""
from __future__ import annotations

import contextlib
import io
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import png_stamp  # noqa: E402
import serve_portal  # noqa: E402
import site_views  # noqa: E402

ROOT = SCRIPTS.parents[1]


def _png(path: Path, w: int = 3, h: int = 2) -> Path:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    raw = b"".join(b"\0" + b"\0\0\0" * w for _ in range(h))
    path.write_bytes(png_stamp.SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    return path


class TheViewsAreNotCommitted(unittest.TestCase):
    def test_every_view_is_gitignored_and_untracked(self) -> None:
        names = [f"www/{rel}" for rel in site_views.VIEWS]
        tracked = subprocess.run(["git", "ls-files", "--", *names], cwd=ROOT, capture_output=True, text=True,
                                 check=True).stdout.split()
        self.assertEqual(tracked, [], "git rm --cached them (ADR-036)")
        ignored = subprocess.run(["git", "check-ignore", "--no-index", *names], cwd=ROOT, capture_output=True,
                                 text=True).stdout.split()
        self.assertEqual(sorted(ignored), sorted(names))

    def test_the_views_are_the_four_files(self) -> None:
        self.assertEqual(sorted(site_views.VIEWS), ["data/layout-index-cats.json", "data/layout-index.json",
                                                    "data/tables-browser.json", "library/pipeline-map.html"])

    def test_every_real_view_builds(self) -> None:
        for rel in site_views.VIEWS:
            with self.subTest(view=rel):
                self.assertTrue(site_views.build(rel).strip())


class Build(unittest.TestCase):
    def test_each_domain_error_becomes_a_view_error_naming_the_view(self) -> None:
        for err in (site_views.pipeline_map.GraphError("graph"), site_views.build_tables_browser.BrowserDataError("t"),
                    site_views.build_layout_index.LayoutIndexError("li"),
                    site_views.build_cats_layout_index.CatsIndexError("c"), png_stamp.PngError("png"),
                    OSError("disk")):
            with self.subTest(err=type(err).__name__):
                with self.assertRaisesRegex(site_views.ViewError, f"Cannot build data/x.json:\n{err}"):
                    site_views.build("data/x.json", mock.Mock(side_effect=err))

    def test_a_builder_that_returns_nothing_is_an_error(self) -> None:
        for empty in ("", " \n", None, b"bytes"):
            with self.subTest(text=empty), self.assertRaisesRegex(site_views.ViewError, "returned no page"):
                site_views.build("data/x.json", lambda: empty)

    def test_another_exception_is_not_swallowed(self) -> None:
        with self.assertRaises(KeyError):
            site_views.build("data/x.json", mock.Mock(side_effect=KeyError("bug")))


class Refresh(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)

    def test_every_view_is_written(self) -> None:
        views = {"data/a.json": lambda: "{}\n", "library/b.html": lambda: "<p>b</p>"}
        self.assertEqual(site_views.refresh(self.root, views), [])
        self.assertEqual((self.root / "data/a.json").read_text(), "{}\n")
        self.assertEqual((self.root / "library/b.html").read_text(), "<p>b</p>")

    def test_a_view_that_fails_loses_its_old_copy_and_the_others_are_written(self) -> None:
        (self.root / "data").mkdir()
        (self.root / "data/a.json").write_text("stale\n")

        def broken():
            raise site_views.build_layout_index.LayoutIndexError("missing panel: x")

        failed = site_views.refresh(self.root, {"data/a.json": broken, "data/b.json": lambda: "{}\n"})
        self.assertEqual(len(failed), 1)
        self.assertIn("Cannot build data/a.json", failed[0])
        self.assertIn("missing panel: x", failed[0])
        self.assertFalse((self.root / "data/a.json").exists(), "a stale copy would be served")
        self.assertTrue((self.root / "data/b.json").is_file())

    def test_a_broken_tables_file_removes_the_stale_layout_index(self) -> None:
        # review of #1147: the real builders' source errors reach refresh as view errors, not a traceback
        (self.root / "data").mkdir()
        (self.root / "data/layout-index.json").write_text("stale\n")
        bad = self.root / "tables.xml"
        bad.write_text("<layout-config>", encoding="utf-8")
        site_views._layout_index.cache_clear()
        self.addCleanup(site_views._layout_index.cache_clear)
        with mock.patch.object(site_views.build_layout_index, "PANEL", bad):
            failed = site_views.refresh(self.root, {"data/layout-index.json": site_views.VIEWS["data/layout-index.json"]})
        self.assertEqual(len(failed), 1)
        self.assertIn("ParseError", failed[0])
        self.assertFalse((self.root / "data/layout-index.json").exists())

    def test_a_root_that_is_not_a_folder_stops(self) -> None:
        with self.assertRaisesRegex(site_views.ViewError, "is not a folder"):
            site_views.refresh(self.root / "absent", {})

    def test_make_site_data_fails_when_a_view_fails(self) -> None:
        err = io.StringIO()
        with mock.patch.object(site_views, "refresh", return_value=["Cannot build data/a.json:\nbroken"]), \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(site_views.main([]), 1)
        self.assertIn("views not built", err.getvalue())


class ServePortalStart(unittest.TestCase):
    def start(self, failed: list[str]) -> tuple[str, str]:
        out, err = io.StringIO(), io.StringIO()
        server = mock.Mock()
        server.serve_forever.side_effect = KeyboardInterrupt
        with mock.patch.object(serve_portal.site_views, "refresh", return_value=failed) as refresh, \
                mock.patch.object(serve_portal, "HTTPServer", return_value=server), \
                mock.patch.object(sys, "argv", ["serve_portal.py", "0"]), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(serve_portal.main(), 0)
        refresh.assert_called_once_with()
        return out.getvalue(), err.getvalue()

    def test_the_views_are_built_before_serving(self) -> None:
        out, err = self.start([])
        self.assertIn("built 4 files the site build makes", out)
        self.assertEqual(err, "")

    def test_a_view_that_cannot_be_built_is_named_with_the_command(self) -> None:
        _, err = self.start(["Cannot build data/layout-index.json:\nmissing panel"])
        self.assertIn("Cannot build data/layout-index.json", err)
        self.assertIn("NOT SERVED", err)
        self.assertIn("make site-data", err)


class PngStamp(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.png = _png(Path(tmp.name) / "a.png")

    def test_size_and_a_stamp_round_trip(self) -> None:
        self.assertEqual(png_stamp.size(self.png), (3, 2))
        self.assertIsNone(png_stamp.stamp(self.png))
        png_stamp.write_stamp(self.png, "abc")
        self.assertEqual(png_stamp.stamp(self.png), "abc")
        png_stamp.write_stamp(self.png, "def")   # replaced, not added
        self.assertEqual(png_stamp.stamp(self.png), "def")
        self.assertEqual(png_stamp.size(self.png), (3, 2))

    def test_the_stamped_png_still_opens(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed")
        png_stamp.write_stamp(self.png, "abc")
        with Image.open(self.png) as im:
            im.load()
            self.assertEqual(im.size, (3, 2))

    def test_the_committed_pngs_carry_a_stamp(self) -> None:
        for png in ("www/assets/layout/HART_le_schematic.png", "www/assets/layout/HART_cats_digicon.png"):
            with self.subTest(png=png):
                self.assertRegex(png_stamp.stamp(ROOT / png) or "", r"^[0-9a-f]{64}$")

    def test_a_broken_png_is_refused(self) -> None:
        cases = {"not a PNG": b"GIF89a",
                 "CRC is wrong": self.png.read_bytes()[:-1] + b"\0",
                 "cut off": self.png.read_bytes()[:-6]}
        for why, data in cases.items():
            with self.subTest(why=why):
                self.png.write_bytes(data)
                with self.assertRaisesRegex(png_stamp.PngError, why):
                    png_stamp.stamp(self.png)

    def test_a_missing_png_or_a_bad_stamp_is_refused(self) -> None:
        with self.assertRaisesRegex(png_stamp.PngError, "cannot read"):
            png_stamp.size(self.png.with_name("gone.png"))
        for bad in ("", "a\0b", "é"):
            with self.subTest(value=bad), self.assertRaisesRegex(png_stamp.PngError, "non-empty ASCII"):
                png_stamp.write_stamp(self.png, bad)


if __name__ == "__main__":
    unittest.main()
