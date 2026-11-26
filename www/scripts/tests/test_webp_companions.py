"""The build's WebP step: rotated photos stay upright, an author's WebP is never touched, and lazy or
responsive images keep their own markup."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from PIL import Image
except ImportError:  # the step raises PillowMissing without Pillow
    Image = None

import prepare_github_pages as pgp


def _noisy_jpeg(path: Path, size=(900, 600), orientation=None) -> None:
    im = Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3))
    exif = Image.Exif()
    if orientation:
        exif[0x0112] = orientation
    im.save(path, "JPEG", quality=95, exif=exif.tobytes())


@unittest.skipIf(Image is None, "Pillow not installed")
class WebpCompanions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def page(self, body: str) -> Path:
        p = self.root / "index.html"
        p.write_text(f"<html><body>{body}</body></html>", encoding="utf-8")
        return p

    def test_wraps_large_jpeg_and_applies_exif_rotation(self):
        _noisy_jpeg(self.root / "a.jpg", orientation=6)   # stored landscape, shown portrait
        page = self.page('<img src="a.jpg" alt="">')
        self.assertGreater(pgp._webp_companions(self.root), 0)
        self.assertIn('<picture><source srcset="a.webp" type="image/webp"><img src="a.jpg"', page.read_text())
        with Image.open(self.root / "a.webp") as w:
            self.assertEqual(w.size, (600, 900))

    def test_existing_webp_is_left_alone(self):
        _noisy_jpeg(self.root / "b.jpg")
        (self.root / "b.webp").write_bytes(b"author's file")
        page = self.page('<img src="b.jpg" alt="">')
        pgp._webp_companions(self.root)
        self.assertEqual((self.root / "b.webp").read_bytes(), b"author's file")
        self.assertNotIn("<picture>", page.read_text())

    def test_lazy_and_responsive_images_are_skipped(self):
        _noisy_jpeg(self.root / "c.jpg")
        body = ('<img data-src="c.jpg" src="placeholder.gif" alt="">'
                '<img src="c.jpg" srcset="c.jpg 900w" sizes="100vw" alt="">')
        page = self.page(body)
        pgp._webp_companions(self.root)
        self.assertNotIn("<picture>", page.read_text())
        self.assertFalse((self.root / "c.webp").exists())


if __name__ == "__main__":
    unittest.main()
