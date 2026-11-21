"""prepare_github_pages.py: the photo group is reused from the last full run when its inputs are unchanged.

A skipped build must give the same files and bytes as a full one, read no original, and fall back to a full run
(saying so in one line) whenever the stamp is missing, unreadable, or no longer fits.
"""
import contextlib
import io
import json
import os
import random
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_prepare_pages_stages as base  # noqa: E402

build = base.build
Image = base.Image
real_open = Image.open if Image else None


def _large_photo(seed: int):
    """Blurred coloured dots: over 200 KB as a JPEG and more than 15% smaller as WebP, so the WebP stage has work."""
    from PIL import ImageDraw, ImageFilter
    rng = random.Random(seed)
    im = Image.new("RGB", (1400, 1400), (90, 120, 160))
    draw = ImageDraw.Draw(im)
    for _ in range(6000):
        x, y, r = rng.randint(0, 1400), rng.randint(0, 1400), rng.randint(4, 40)
        draw.ellipse((x, y, x + r, y + r), fill=tuple(rng.randint(0, 255) for _ in range(3)))
    return im.filter(ImageFilter.GaussianBlur(1.2))


@unittest.skipIf(Image is None, "Pillow is needed to build photos")
class PhotoSkip(base.FullBuild):
    """The FullBuild fixture, plus a page showing a large photo so the late stage (card thumbs, WebP) has work."""

    def setUp(self):
        super().setUp()
        _large_photo(1).save(self.repo / "media/p1.png")
        self.track("docs/photo.html", base._page("Photo — HART", '<h1>Photo</h1><p>A large photo on a page, shown in the page body for the build.</p><img src="../assets/gallery/night/p1.jpg" alt="p1">'))

    def build(self, *args):
        err, out = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["prepare", str(self.out), *args]), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = build.main()
        self.assertEqual(code, 0, err.getvalue())
        return out.getvalue()

    def snapshot(self):
        return {p.relative_to(self.out).as_posix(): p.read_bytes() for p in self.out.rglob("*") if p.is_file()}

    def store(self):
        return Path(self._tmp.name) / "cache" / build.PHOTO_STORE

    def no_original_read(self, fp, *args, **kwargs):
        """Image.open that refuses the originals in media/ (the search stage may still open its small grid thumbs)."""
        if "media" in Path(str(fp)).parts:
            raise AssertionError(f"original read: {fp}")
        return real_open(fp, *args, **kwargs)

    def test_a_matching_stamp_reuses_the_photos_and_reads_no_original(self):
        self.assertIn("photo stages: full run (no saved run)", self.build())
        with mock.patch.object(build, "_web_jpeg", side_effect=AssertionError("resized")), \
                mock.patch.object(build, "_render_jpeg", side_effect=AssertionError("rendered")), \
                mock.patch.object(Image, "open", side_effect=self.no_original_read), \
                mock.patch.object(build, "_webp_companions", side_effect=AssertionError("webp")):
            out = self.build()
        self.assertIn("photo stages: reused the saved run", out)
        self.assertIn("WebP companions:", out)

    def test_a_skipped_build_matches_a_full_build_in_files_and_bytes(self):
        self.build()
        full = self.snapshot()
        self.assertTrue(any(name.endswith(".webp") for name in full), "the fixture must exercise the WebP stage")
        self.assertIn("reused", self.build())
        skipped = self.snapshot()
        self.assertEqual(sorted(skipped), sorted(full))
        # assets/search/*.jpg carries the grid thumb's mtime in a JPEG comment, and search-index.json its build
        # time to the second, so two full builds differ there too: compare the index without "generated".
        def index(snap):
            data = json.loads(snap["search-index.json"])
            data.pop("generated", None)
            return data
        self.assertEqual(index(skipped), index(full))
        self.assertEqual([n for n in full if full[n] != skipped[n]
                          and not n.startswith("assets/search/") and n != "search-index.json"], [])

    def test_a_changed_data_file_misses(self):
        self.build()
        path = self.portal / "data/gallery.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["items"][0]["title"] = "renamed"
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("photo stages: full run (inputs changed)", self.build())

    def test_a_changed_source_photo_misses(self):
        self.build()
        _large_photo(2).save(self.repo / "media/p1.png")
        self.assertIn("photo stages: full run (inputs changed)", self.build())

    def test_a_changed_page_misses_only_the_late_stage(self):
        self.build()
        self.track("docs/photo.html", base._page("Photo — HART", '<h1>Photo again</h1><p>A large photo on a page, shown in the page body for the build.</p><img src="../assets/gallery/night/p1.jpg" alt="p1">'))
        with mock.patch.object(build, "_render_jpeg", side_effect=AssertionError("rendered")):
            out = self.build()
        self.assertIn("photo stages: reused", out)
        self.assertIn("<picture>", (self.out / "docs/photo.html").read_text(encoding="utf-8"))

    def test_a_missing_stamp_runs_in_full(self):
        self.build()
        (self.store() / "early/stamp.json").unlink()
        self.assertIn("photo stages: full run (no saved run)", self.build())

    def test_an_unreadable_stamp_runs_in_full(self):
        self.build()
        (self.store() / "early/stamp.json").write_text("{not json", encoding="utf-8")
        self.assertIn("photo stages: full run (saved stamp unreadable)", self.build())

    def test_a_saved_file_gone_runs_in_full(self):
        self.build()
        next((self.store() / "early/files").rglob("*.jpg")).unlink()
        self.assertIn("photo stages: full run (saved files incomplete)", self.build())

    def test_a_different_dest_folder_reuses_the_run_and_gives_the_same_files(self):
        self.build()
        first = self.snapshot()
        self.out = Path(self._tmp.name) / "elsewhere"
        self.assertIn("photo stages: reused", self.build())
        self.assertEqual(sorted(self.snapshot()), sorted(first))

    def test_a_changed_site_local_image_misses(self):
        local = base._png(self.portal / "assets/media/local.png")
        self.track("assets/media/local.png", "x")
        base._png(local)
        path = self.portal / "data/gallery.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["items"].append({"id": "loc", "album": "night", "src": "assets/media/local.png"})
        path.write_text(json.dumps(data), encoding="utf-8")
        self.build()
        self.assertIn("photo stages: reused", self.build())
        base._png(local, colour=(1, 2, 3), size=(310, 200))
        self.assertIn("photo stages: full run (inputs changed)", self.build())

    def test_a_changed_share_card_file_misses_the_late_part(self):
        cards = Path(self._tmp.name) / "share-cards.json"
        cards.write_text("{}", encoding="utf-8")
        with mock.patch.object(build.share_cards, "CARDS", cards):
            self.build()
            self.assertIn("photo stages: reused", self.build())
            cards.write_text('{"x": 1}', encoding="utf-8")
            out = self.build()
        self.assertIn("photo stages: reused", out)
        self.assertIn("photo stages, card thumbs and WebP: full run (inputs changed)", out)

    def test_reuse_leaves_the_resize_cache_unpruned_and_a_full_run_prunes(self):
        with mock.patch.object(build, "_prune_jpeg_cache") as prune:
            self.build()
            self.assertEqual(prune.call_count, 1)
            self.build()
            self.assertEqual(prune.call_count, 1)
            self.build("--full")
            self.assertEqual(prune.call_count, 2)

    def test_without_pillow_the_build_runs_as_before_and_saves_nothing(self):
        build._photo_code_key.cache_clear()
        build._render_key.cache_clear()
        self.addCleanup(build._photo_code_key.cache_clear)
        self.addCleanup(build._render_key.cache_clear)
        with mock.patch.dict(sys.modules, {"PIL": None, "PIL.Image": None, "PIL.ImageOps": None}):
            out = self.build()
        self.assertIn("photo stages: full run (Pillow is missing)", out)
        self.assertFalse(self.store().exists())

    def test_full_ignores_the_stamp_and_saves_a_new_one(self):
        self.build()
        with mock.patch.object(build, "_web_jpeg", wraps=build._web_jpeg) as spy:
            out = self.build("--full")
        self.assertGreater(spy.call_count, 0)
        self.assertIn("photo stages: full run (--full)", out)
        self.assertIn("reused", self.build())

    def test_no_photo_cache_means_a_full_run_every_time(self):
        with mock.patch.dict(os.environ, {build.JPEG_CACHE_ENV: ""}):
            build._jpeg_cache_at.cache_clear()
            self.build()
            self.assertIn("photo stages: full run (the photo cache is off)", self.build())


# The inherited FullBuild tests are not repeated here.
for _name in [n for n in dir(base.FullBuild) if n.startswith("test_")]:
    setattr(PhotoSkip, _name, None)


if __name__ == "__main__":
    unittest.main()
