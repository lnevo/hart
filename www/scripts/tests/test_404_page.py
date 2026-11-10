"""The 404 page is served for any missing path, so nothing in it may be a relative link."""
import re
import unittest
from pathlib import Path

PAGE = Path(__file__).resolve().parents[2] / "404.html"


class NotFoundPage(unittest.TestCase):
    def setUp(self):
        self.html = PAGE.read_text(encoding="utf-8")

    def test_every_link_starts_at_the_site_root(self):
        refs = re.findall(r'\b(?:href|src)="([^"]*)"', self.html)
        self.assertTrue(refs)
        for ref in refs:
            self.assertTrue(ref.startswith("/") and not ref.startswith("//"), ref)

    def test_has_a_way_home_without_scripts(self):
        self.assertIn('href="/"', self.html)

    def test_is_kept_out_of_search_results(self):
        self.assertIn('<meta name="robots" content="noindex">', self.html)

    def test_asked_for_path_is_written_as_text(self):
        self.assertNotIn("innerHTML", self.html)


if __name__ == "__main__":
    unittest.main()
