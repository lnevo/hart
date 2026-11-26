"""prepare_github_pages: an archive item's "max_px" sets the size of its web copy, within limits."""
import io
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
import portal_photos as photos  # noqa: E402  (a patch goes on the module that holds the name)

try:
    from PIL import Image
except ImportError:
    Image = None


class ArchivePx(unittest.TestCase):
    def test_unset_or_junk_keeps_the_default(self):
        self.assertEqual(build._archive_px(None, 1600), 1600)
        with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            self.assertEqual(build._archive_px("5220px", 1600, "map"), 1600)
        self.assertIn("map max_px '5220px' not usable", err.getvalue())

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
        with mock.patch.object(photos, "_source", return_value=self.big):
            build._vendor_archive_images(data, dest)
        out = json.loads(data.read_text())["items"][0]
        sizes = {}
        for key in ("src", "full"):
            if key in out:
                with Image.open(dest / out[key]) as im:
                    sizes[key] = im.size
        return out, sizes

    def test_max_px_adds_a_large_full_copy_and_keeps_src_small(self):
        out, sizes = self.build({"id": "map", "src": "../media/big.png", "bucket": "curated", "max_px": 2400})
        self.assertEqual(sizes, {"src": (1600, 800), "full": (2400, 1200)})
        self.assertNotIn("max_px", out)

    def test_without_max_px_there_is_no_full_copy(self):
        out, sizes = self.build({"id": "map", "src": "../media/big.png", "bucket": "curated"})
        self.assertEqual(sizes, {"src": (1600, 800)})


if __name__ == "__main__":
    unittest.main()
