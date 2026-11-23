"""prepare_github_pages: an archive item's "max_px" sets the size of its web copy, within limits."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import prepare_github_pages as build  # noqa: E402

try:
    from PIL import Image
except ImportError:
    Image = None


class ArchivePx(unittest.TestCase):
    def test_unset_or_junk_keeps_the_default(self):
        self.assertEqual(build._archive_px(None, 1600), 1600)
        self.assertEqual(build._archive_px("big", 1600), 1600)

    def test_kept_between_default_and_the_cap(self):
        self.assertEqual(build._archive_px(4000, 1600), 4000)
        self.assertEqual(build._archive_px("4000", 1600), 4000)
        self.assertEqual(build._archive_px(800, 1600), 1600)
        self.assertEqual(build._archive_px(99999, 1600), build.ARCHIVE_MAX_PX)


@unittest.skipIf(Image is None, "Pillow is not installed")
class VendorArchive(unittest.TestCase):
    def setUp(self):
        build._jpeg_cache_at.cache_clear()
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.env = mock.patch.dict(os.environ, {build.JPEG_CACHE_ENV: str(self.tmp / "cache")})
        self.env.start()
        self.big = self.tmp / "media" / "big.png"
        self.big.parent.mkdir()
        Image.new("RGB", (3000, 1500), (90, 90, 90)).save(self.big)

    def tearDown(self):
        self.env.stop()
        self._tmp.cleanup()

    def build(self, item):
        dest = self.tmp / "site"
        data = dest / "data" / "archive.json"
        data.parent.mkdir(parents=True, exist_ok=True)
        data.write_text(json.dumps({"items": [item]}))
        with mock.patch.object(build, "_source", return_value=self.big):
            build._vendor_archive_images(data, dest)
        out = json.loads(data.read_text())["items"][0]
        with Image.open(dest / out["src"]) as im:
            return out, im.size

    def test_an_item_max_px_gives_a_larger_copy_and_is_not_published(self):
        out, size = self.build({"id": "map", "src": "../media/big.png", "bucket": "curated", "max_px": 2400})
        self.assertEqual(size, (2400, 1200))
        self.assertNotIn("max_px", out)

    def test_without_max_px_the_copy_is_1600(self):
        _, size = self.build({"id": "map", "src": "../media/big.png", "bucket": "curated"})
        self.assertEqual(size, (1600, 800))


if __name__ == "__main__":
    unittest.main()
