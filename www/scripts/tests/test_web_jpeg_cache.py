"""prepare_github_pages._web_jpeg: resized photos come from the cache when the source, size and settings match."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import prepare_github_pages as build  # noqa: E402

try:
    from PIL import Image
except ImportError:                      # CI without Pillow: _web_jpeg returns False before the cache
    Image = None


@unittest.skipIf(Image is None, "Pillow is not installed")
class WebJpegCache(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.cache = self.tmp / "cache"
        self.env = mock.patch.dict(os.environ, {build.JPEG_CACHE_ENV: str(self.cache)})
        self.env.start()
        self.src = self.photo("a.png", (200, 120, 40))

    def tearDown(self):
        self.env.stop()
        self._tmp.cleanup()

    def photo(self, name, colour, size=(400, 300)):
        p = self.tmp / name
        Image.new("RGB", size, colour).save(p)
        return p

    def renders(self, src, out, max_px=100):
        with mock.patch.object(build, "_render_jpeg", wraps=build._render_jpeg) as spy:
            self.assertTrue(build._web_jpeg(src, out, max_px))
        return spy.call_count

    def test_a_hit_is_the_same_bytes_and_time_stamp_without_resizing(self):
        self.assertEqual(self.renders(self.src, self.tmp / "o1.jpg"), 1)
        self.assertEqual(self.renders(self.src, self.tmp / "o2.jpg"), 0)
        fresh = self.tmp / "fresh.jpg"
        build._render_jpeg(self.src, fresh, 100)
        self.assertEqual((self.tmp / "o2.jpg").read_bytes(), fresh.read_bytes())
        self.assertEqual((self.tmp / "o1.jpg").stat().st_mtime, (self.tmp / "o2.jpg").stat().st_mtime)
        with Image.open(self.tmp / "o2.jpg") as im:
            self.assertEqual(im.size, (100, 75))

    def test_new_bytes_a_new_size_or_new_settings_resize_again(self):
        self.renders(self.src, self.tmp / "o.jpg")
        self.photo("a.png", (10, 20, 30))                      # same name, new picture
        self.assertEqual(self.renders(self.src, self.tmp / "o.jpg"), 1)
        self.assertEqual(self.renders(self.src, self.tmp / "o.jpg", max_px=50), 1)
        with mock.patch.object(build, "JPEG_SETTINGS", "changed"):
            self.assertEqual(self.renders(self.src, self.tmp / "o.jpg"), 1)
        self.assertEqual(len(list(self.cache.glob("*.jpg"))), 4)

    def test_off_when_the_variable_is_empty(self):
        with mock.patch.dict(os.environ, {build.JPEG_CACHE_ENV: ""}):
            self.assertEqual(self.renders(self.src, self.tmp / "o.jpg"), 1)
            self.assertEqual(self.renders(self.src, self.tmp / "o.jpg"), 1)
        self.assertFalse(self.cache.exists())

    def test_a_folder_that_cannot_be_made_resizes_and_says_so(self):
        blocker = self.tmp / "file"
        blocker.write_text("x")
        with mock.patch.dict(os.environ, {build.JPEG_CACHE_ENV: str(blocker / "sub")}), \
                mock.patch("sys.stderr") as err:
            self.assertEqual(self.renders(self.src, self.tmp / "o.jpg"), 1)
        self.assertIn("cannot use", "".join(c.args[0] for c in err.write.call_args_list))

    def test_a_failed_resize_leaves_nothing_in_the_cache(self):
        with mock.patch.object(build, "_render_jpeg", side_effect=OSError("broken image")):
            with self.assertRaises(OSError):
                build._web_jpeg(self.src, self.tmp / "o.jpg", 100)
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_pruning_drops_only_photos_unused_for_the_keep_period(self):
        self.renders(self.src, self.tmp / "o.jpg")
        self.renders(self.photo("b.png", (0, 0, 255)), self.tmp / "p.jpg")
        old, used = sorted(self.cache.glob("*.jpg"))
        long_ago = time.time() - (build.JPEG_CACHE_KEEP_DAYS + 1) * 86400
        os.utime(old, (long_ago, old.stat().st_mtime))
        build._prune_jpeg_cache()
        self.assertEqual(list(self.cache.glob("*.jpg")), [used])


if __name__ == "__main__":
    unittest.main()
