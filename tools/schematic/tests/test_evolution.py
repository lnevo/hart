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
        '<span data-film="last">14 November 2026</span>.</figcaption>')


def versions(n, first="2026-11-13 11:14", last="2026-11-21 09:00"):
    return [("h%d" % i, first if i == 0 else last if i == n - 1 else "2026-11-15 10:00", "s", "f") for i in range(n)]


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
    def test_always_thirty_seconds_with_the_last_held(self):
        for n in (2, 38, 70, 200):
            d = evolution.film_durations(n)
            self.assertEqual(len(d), n)
            self.assertAlmostEqual(sum(d), 30, places=2)
            self.assertAlmostEqual(d[-1], 2, places=2)

    def test_one_version_is_an_error(self):
        with self.assertRaises(ValueError):
            evolution.film_durations(1)


class PageTest(unittest.TestCase):
    def test_current_page_has_no_drift(self):
        self.assertEqual(evolution.page_drift(PAGE, evolution.page_values(versions(38, last="2026-11-14 09:00"))), [])

    def test_caption_and_aria_follow_the_versions(self):
        values = evolution.page_values(versions(70))
        text = evolution.page_text(PAGE, values)
        self.assertIn('aria-label="Seventy versions of the system schematic', text)
        self.assertIn('<span data-film="count">70</span>', text)
        self.assertIn('<span data-film="last">21 November 2026</span>', text)
        self.assertEqual(evolution.page_drift(text, values), [])
        self.assertEqual(evolution.page_text(text, values), text)

    def test_drift_names_what_differs(self):
        drift = evolution.page_drift(PAGE, evolution.page_values(versions(70)))
        self.assertEqual(len(drift), 3)
        self.assertTrue(any("count says 38" in d for d in drift))
        self.assertTrue(any("aria-label says thirty-eight" in d for d in drift))

    def test_missing_marker_is_an_error(self):
        values = evolution.page_values(versions(70))
        with self.assertRaises(ValueError):
            evolution.page_text(PAGE.replace('data-film="first"', 'data-x="first"'), values)
        with self.assertRaises(ValueError):
            evolution.page_text(PAGE.replace("versions of the system schematic", "versions"), values)
        self.assertTrue(evolution.page_drift("<p>nothing</p>", values))


class CheckTest(unittest.TestCase):
    def run_check(self, html, n):
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "panel-evolution.html"
            page.write_text(html)
            out = io.StringIO()
            with mock.patch.object(evolution, "PAGE", page), mock.patch.object(evolution, "REPO", Path(tmp)), \
                    mock.patch.object(evolution, "versions", lambda: versions(n)), contextlib.redirect_stdout(out):
                return evolution.check(), out.getvalue()

    def test_behind_fails(self):
        rc, out = self.run_check(PAGE, 70)
        self.assertEqual(rc, 1)
        self.assertIn("behind the drawing", out)

    def test_current_passes(self):
        rc, _ = self.run_check(evolution.page_text(PAGE, evolution.page_values(versions(70))), 70)
        self.assertEqual(rc, 0)


class SiteTest(unittest.TestCase):
    def test_no_ffmpeg_stops_with_a_message(self):
        with mock.patch.object(evolution.shutil, "which", return_value=None):
            with self.assertRaises(SystemExit) as e:
                evolution.site([], [], Path("."))
        self.assertIn("ffmpeg not found", str(e.exception))


if __name__ == "__main__":
    unittest.main()
