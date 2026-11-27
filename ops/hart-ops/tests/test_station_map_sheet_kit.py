"""ops/station_maps/scripts/sheet_kit.py and the local station map font loader."""
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw

HART = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(HART / "ops/station_maps/scripts"))
sys.path.insert(0, str(HART / "ops/hart-ops/publications"))

import sheet_kit  # noqa: E402
from local_station_maps import kit  # noqa: E402

CORE = (b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        b'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Old</dc:title></cp:coreProperties>')


def template(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/media/image1.png", b"old-png")
        z.writestr("word/document.xml", b"<doc>station_map_west_yard.png</doc>")
        z.writestr("docProps/core.xml", CORE)
        z.writestr("word/styles.xml", b"<styles/>")
    return path


class WriteSheetDocx(unittest.TestCase):
    def test_swaps_image_renames_media_and_sets_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            png = root / "map.png"
            png.write_bytes(b"new-png")
            dest = root / "out" / "sheet.docx"
            with mock.patch.object(sys, "stdout", io.StringIO()):
                sheet_kit.write_sheet_docx(template(root / "t.docx"), png, dest,
                                           media_names=("station_map_west_yard.png", "station_map_barn.png"),
                                           title="Barn")
            with zipfile.ZipFile(dest) as z:
                self.assertEqual(z.read("word/media/image1.png"), b"new-png")
                self.assertEqual(z.read("word/document.xml"), b"<doc>station_map_barn.png</doc>")
                self.assertIn(b"<dc:title>Barn</dc:title>", z.read("docProps/core.xml"))
                self.assertEqual(z.read("word/styles.xml"), b"<styles/>")

    def test_without_names_or_title_only_the_image_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            png = root / "map.png"
            png.write_bytes(b"new-png")
            dest = root / "sheet.docx"
            with mock.patch.object(sys, "stdout", io.StringIO()):
                sheet_kit.write_sheet_docx(template(root / "t.docx"), png, dest)
            with zipfile.ZipFile(dest) as z:
                self.assertEqual(z.read("docProps/core.xml"), CORE)
                self.assertEqual(z.read("word/document.xml"), b"<doc>station_map_west_yard.png</doc>")

    def test_missing_template_is_a_named_error_with_its_name(self) -> None:
        with self.assertRaises(sheet_kit.SheetTemplateMissing) as cm:
            sheet_kit.write_sheet_docx(Path("/nowhere/t.docx"), Path("/nowhere/p.png"), Path("/nowhere/d.docx"))
        self.assertIn("/nowhere/t.docx", str(cm.exception))
        self.assertFalse(Path("/nowhere/d.docx").exists())

    def test_returns_dest_and_prints_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            png = root / "map.png"
            png.write_bytes(b"new-png")
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out):
                written = sheet_kit.write_sheet_docx(template(root / "t.docx"), png, root / "d.docx")
            self.assertEqual(written, root / "d.docx")
            self.assertEqual(out.getvalue(), "")


class Drawing(unittest.TestCase):
    def test_along_follows_the_slope(self) -> None:
        self.assertEqual(sheet_kit.along((10.0, 20.0), 4.0, run=3.0, rise=2.0), (16.0, 24.0))

    def test_badge_corner_is_checked(self) -> None:
        d = ImageDraw.Draw(Image.new("RGB", (200, 200), (255, 255, 255)))
        font = sheet_kit.arial(12)
        kw = {"dot_r": 5, "gap": 4, "fill": (15, 71, 97), "ink": (255, 255, 255)}
        for corner in ("ne", "nw", "w", "e"):
            sheet_kit.badge_near(d, (100, 100), "7", font, corner, **kw)
        with self.assertRaises(ValueError) as cm:
            sheet_kit.badge_near(d, (100, 100), "7", font, "sw", **kw)  # type: ignore[arg-type]
        self.assertIn("sw", str(cm.exception))


class Fonts(unittest.TestCase):
    def test_missing_arial_warns_with_the_names(self) -> None:
        err = io.StringIO()
        with mock.patch.object(sheet_kit, "SANS_DIRS", ()), mock.patch.object(sys, "stderr", err):
            sheet_kit.arial(12, bold=True)
        self.assertIn("Arial Bold.ttf, Arial.ttf", err.getvalue())

    def test_local_map_font_warns_with_the_path(self) -> None:
        err = io.StringIO()
        with mock.patch.object(sys, "stderr", err):
            kit._font("/nowhere/Missing.ttf", 12)
        self.assertIn("/nowhere/Missing.ttf", err.getvalue())


class Arrow(unittest.TestCase):
    def test_arrow_points_the_named_way(self):
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (60, 40), sheet_kit.WHITE)
        d = ImageDraw.Draw(img)
        sheet_kit.arrow(d, (10, 20), "left", size=20)
        sheet_kit.arrow(d, (50, 20), "right", size=20, fill=(255, 0, 0))
        self.assertEqual(img.getpixel((25, 20)), sheet_kit.TRACK)
        self.assertEqual(img.getpixel((40, 20)), (255, 0, 0))
        self.assertEqual(img.getpixel((5, 20)), sheet_kit.WHITE)

    def test_sheet_is_eight_by_five_inches(self):
        self.assertEqual((sheet_kit.W, sheet_kit.H), (8 * sheet_kit.DPI, 5 * sheet_kit.DPI))


if __name__ == "__main__":
    unittest.main()
