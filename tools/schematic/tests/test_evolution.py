"""evolution: the site film's page text follows the committed versions (no ffmpeg, no rendering)."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import evolution  # noqa: E402

PAGE = ('<video aria-label="Thirty-eight versions of the system schematic in order, from the first proof">'
        '<figcaption>The system schematic, <span data-film="count">38</span> committed versions from the first '
        'proof of staging on <span data-film="first">13 November</span> to the sheet of '
        '<span data-film="last">14 November 2026</span>.</figcaption>'
        '<img loading="lazy" width="1400" height="1080" src="../assets/x/schematic-poster.jpg" alt="a">')
SIZE = (1400, 1126)


def versions(n, first="2026-11-13 11:14", last="2026-11-21 09:00"):
    return [("h%d" % i, first if i == 0 else last if i == n - 1 else "2026-11-15 10:00", "s", "f") for i in range(n)]


class DefaultFolderTest(unittest.TestCase):
    def test_the_default_is_media_under_the_repo_root(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "media").mkdir()
            with mock.patch.object(evolution, "REPO", Path(d)):
                self.assertEqual(Path(d) / "media/schematic-evolution", evolution.default_folder())

    def test_without_media_it_stops_and_makes_nothing(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(evolution, "REPO", Path(d)):
            with self.assertRaises(SystemExit) as stop:
                evolution.default_folder()
            self.assertIn("media", str(stop.exception))
            self.assertEqual([], list(Path(d).iterdir()))


class WordsTest(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual([evolution.words(n) for n in (1, 13, 20, 38, 70, 99)],
                         ["one", "thirteen", "twenty", "thirty-eight", "seventy", "ninety-nine"])

    def test_out_of_range_is_an_error(self):
        for n in (0, 100):
            with self.assertRaises(ValueError):
                evolution.words(n)

    def test_day(self):
        self.assertEqual(evolution.day("2026-11-04 09:00", False), "4 November")
        self.assertEqual(evolution.day("2026-12-31 09:00", True), "31 December 2026")


class FilmTimingTest(unittest.TestCase):
    def test_site_film_uses_the_shared_pace(self):
        self.assertEqual(evolution.film_pace.STEP_S, 0.4)
        self.assertEqual(evolution.film_pace.FINAL_HOLD_S, 2.0)

    def test_length_grows_with_the_versions(self):
        for n in (2, 38, 70, 200):
            d = evolution.film_pace.durations(n)
            self.assertEqual(len(d), n)
            self.assertAlmostEqual(sum(d), 0.4 * (n - 1) + 2.0, places=3)
            self.assertEqual(d[-1], 2.0)

    def test_one_version_is_an_error(self):
        with self.assertRaises(ValueError):
            evolution.film_pace.durations(1)


class PageTest(unittest.TestCase):
    def test_current_page_has_no_drift(self):
        self.assertEqual(evolution.page_drift(PAGE, evolution.page_values(versions(38, last="2026-11-14 09:00")), (1400, 1080)), [])

    def test_caption_and_aria_follow_the_versions(self):
        values = evolution.page_values(versions(70))
        text = evolution.page_text(PAGE, values, SIZE)
        self.assertIn('aria-label="Seventy versions of the system schematic', text)
        self.assertIn('<span data-film="count">70</span>', text)
        self.assertIn('<span data-film="last">21 November 2026</span>', text)
        self.assertEqual(evolution.page_drift(text, values, SIZE), [])
        self.assertEqual(evolution.page_text(text, values, SIZE), text)

    def test_drift_names_what_differs(self):
        drift = evolution.page_drift(PAGE, evolution.page_values(versions(70)), SIZE)
        self.assertEqual(len(drift), 4)
        self.assertTrue(any("count says 38" in d for d in drift))
        self.assertTrue(any("aria-label says thirty-eight" in d for d in drift))

    def test_missing_marker_is_an_error(self):
        values = evolution.page_values(versions(70))
        with self.assertRaises(ValueError):
            evolution.page_text(PAGE.replace('data-film="first"', 'data-x="first"'), values, SIZE)
        with self.assertRaises(ValueError):
            evolution.page_text(PAGE.replace("versions of the system schematic", "versions"), values, SIZE)
        self.assertTrue(evolution.page_drift("<p>nothing</p>", values, SIZE))
        with self.assertRaises(ValueError):
            evolution.page_text(PAGE.replace("schematic-poster", "other"), values, SIZE)

    def test_poster_size_is_set_and_compared(self):
        text = evolution.page_text(PAGE, evolution.page_values(versions(38)), SIZE)
        self.assertIn('width="1400" height="1126" src=', text)
        self.assertIn("poster img says 1400x1126", evolution.page_drift(text, evolution.page_values(versions(38)), (1400, 1080))[-1])


class CheckTest(unittest.TestCase):
    def run_check(self, html, n, size=SIZE):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            Image.new("RGB", size).save(Path(tmp) / evolution.POSTER)
            page = Path(tmp) / "panel-evolution.html"
            page.write_text(html)
            out = io.StringIO()
            with mock.patch.object(evolution, "PAGE", page), mock.patch.object(evolution, "REPO", Path(tmp)), mock.patch.object(evolution, "SITE", Path(tmp)), \
                    mock.patch.object(evolution, "versions", lambda: versions(n)), contextlib.redirect_stdout(out):
                return evolution.check(), out.getvalue()

    def test_behind_fails(self):
        rc, out = self.run_check(PAGE, 70)
        self.assertEqual(rc, 1)
        self.assertIn("behind the drawing", out)

    def test_current_passes(self):
        rc, _ = self.run_check(evolution.page_text(PAGE, evolution.page_values(versions(70)), SIZE), 70)
        self.assertEqual(rc, 0)


    def test_no_versions_is_a_message_not_a_crash(self):
        rc, out = self.run_check(PAGE, 0)
        self.assertEqual(rc, 2)
        self.assertIn("no committed drawings", out)


class SiteTest(unittest.TestCase):
    def test_site_writes_the_page_it_is_given_not_the_repo_page(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(evolution.shutil, "which", return_value="/bin/true"), \
                mock.patch.object(evolution.subprocess, "run") as run:
            page = Path(tmp) / "p.html"
            page.write_text(PAGE)
            out = Path(tmp)
            run.side_effect = lambda *a, **k: (Path(k["cwd"], evolution.MP4).write_bytes(b"x"),
                                               mock.Mock(returncode=0))[1]
            evolution.site([Image.new("RGB", (1400, 1126))] * 3, versions(3), out, page)
            self.assertIn('<span data-film="count">3</span>', page.read_text())
            self.assertIn('height="1126"', page.read_text())
            self.assertTrue((out / evolution.POSTER).exists())

    def test_no_ffmpeg_stops_with_a_message(self):
        with mock.patch.object(evolution.shutil, "which", return_value=None):
            with self.assertRaises(SystemExit) as e:
                evolution.site([], [], Path("."))
        self.assertIn("ffmpeg not found", str(e.exception))


if __name__ == "__main__":
    unittest.main()
