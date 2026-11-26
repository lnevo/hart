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
import portal_photos as photos  # noqa: E402  (a patch goes on the module that holds the name)

try:
    from PIL import Image
except ImportError:                      # CI without Pillow: _web_jpeg raises PillowMissing before the cache
    Image = None


@unittest.skipIf(Image is None, "Pillow is not installed")
class WebJpegCache(unittest.TestCase):
    def setUp(self):
        build._jpeg_cache_at.cache_clear()
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
        with mock.patch.object(photos, "_render_jpeg", wraps=build._render_jpeg) as spy:
            build._web_jpeg(src, out, max_px)
        self.assertTrue(out.is_file())
        return spy.call_count

    def test_a_hit_is_the_same_bytes_without_resizing(self):
        self.assertEqual(self.renders(self.src, self.tmp / "o1.jpg"), 1)
        self.assertEqual(self.renders(self.src, self.tmp / "o2.jpg"), 0)
        fresh = self.tmp / "fresh.jpg"
        build._render_jpeg(self.src, fresh, 100)
        self.assertEqual((self.tmp / "o2.jpg").read_bytes(), fresh.read_bytes())
        with Image.open(self.tmp / "o2.jpg") as im:
            self.assertEqual(im.size, (100, 75))

    def test_new_bytes_a_new_size_or_new_drawing_code_resize_again(self):
        self.renders(self.src, self.tmp / "o.jpg")
        self.photo("a.png", (10, 20, 30))                      # same name, new picture
        self.assertEqual(self.renders(self.src, self.tmp / "o.jpg"), 1)
        self.assertEqual(self.renders(self.src, self.tmp / "o.jpg", max_px=50), 1)
        with mock.patch.object(photos, "_render_key", return_value=b"other drawing code"):
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
        with mock.patch.object(photos, "_render_jpeg", side_effect=OSError("broken image")):
            with self.assertRaises(OSError):
                build._web_jpeg(self.src, self.tmp / "o.jpg", 100)
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_pruning_drops_only_photos_unused_for_the_keep_period(self):
        self.renders(self.src, self.tmp / "o.jpg")
        self.renders(self.photo("b.png", (0, 0, 255)), self.tmp / "p.jpg")
        old, used = sorted(self.cache.glob("*.jpg"))
        long_ago = time.time() - (build.JPEG_CACHE_KEEP_DAYS + 1) * 86400
        mine = self.cache / "holiday.jpg"                        # not the cache's: never removed
        mine.write_bytes(b"x")
        for f in (old, mine):
            os.utime(f, (long_ago, long_ago))
        build._prune_jpeg_cache()
        self.assertEqual(sorted(self.cache.glob("*.jpg")), sorted([used, mine]))

    def test_the_cache_folder_is_private_and_a_bad_one_is_reported_once(self):
        self.renders(self.src, self.tmp / "o.jpg")
        self.assertEqual(self.cache.stat().st_mode & 0o777, 0o700)
        blocker = self.tmp / "file"
        blocker.write_text("x")
        with mock.patch.dict(os.environ, {build.JPEG_CACHE_ENV: str(blocker / "sub")}), \
                mock.patch("sys.stderr") as err:
            self.renders(self.src, self.tmp / "o.jpg")
            self.renders(self.src, self.tmp / "p.jpg")
        self.assertEqual("".join(c.args[0] for c in err.write.call_args_list).count("cannot use"), 1)

    def test_an_entry_pruned_by_another_build_is_resized_again(self):
        self.renders(self.src, self.tmp / "o.jpg")
        real = build.shutil.copyfile
        calls = []

        def vanish_once(a, b):
            calls.append(a)
            if len(calls) == 1:
                Path(a).unlink()
                raise FileNotFoundError(a)
            return real(a, b)
        with mock.patch.object(build.shutil, "copyfile", side_effect=vanish_once):
            self.assertEqual(self.renders(self.src, self.tmp / "o.jpg"), 1)
        self.assertTrue((self.tmp / "o.jpg").stat().st_size > 0)


if __name__ == "__main__":
    unittest.main()
