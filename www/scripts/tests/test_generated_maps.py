"""Generated station map previews (ADR-023): every station SVG is published from docs/ops/stations,
every preview page points at a published sheet, and nothing on the live crew pages links them."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PUBLISHED = json.loads((ROOT / "www/scripts/published-files.json").read_text())
MAPS = ROOT / "www/crew/maps"
SHEETS = sorted((ROOT / "docs/ops/stations").glob("*.svg"))
FOLDER = "crew/maps/generated-sheets/"
WORDS = {6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten"}


class GeneratedMapsTest(unittest.TestCase):
    def test_every_station_svg_is_published_from_docs(self):
        for svg in SHEETS:
            self.assertEqual(PUBLISHED.get(FOLDER + svg.name), f"docs/ops/stations/{svg.name}")

    def test_published_sheets_exist(self):
        for rel, src in PUBLISHED.items():
            if rel.startswith(FOLDER):
                self.assertTrue((ROOT / src).is_file(), src)

    def test_pages_use_published_sheets_and_are_noindex(self):
        pages = list(MAPS.glob("*/generated.html")) + [MAPS / "generated.html"]
        self.assertTrue(pages)
        for page in pages:
            text = page.read_text()
            self.assertIn('<meta name="robots" content="noindex">', text, page)
            self.assertIn("Generated map, preview" if page.parent != MAPS else "Preview for review", text)
            for name in re.findall(r"generated-sheets/([\w-]+\.svg)", text):
                self.assertIn(FOLDER + name, PUBLISHED, page)

    def test_overview_lists_all_sheets_and_says_how_many(self):
        text = (MAPS / "generated.html").read_text()
        for svg in SHEETS:
            self.assertIn(f"generated-sheets/{svg.name}", text)
        self.assertEqual(len(re.findall(r"<li>", text)), len(SHEETS))
        self.assertIn(f"{WORDS[len(SHEETS)]} generated station map sheets", text)

    def test_live_pages_do_not_link_the_previews(self):
        link = re.compile(r"""(href|src)=["'][^"']*generated(\.html|-sheets/)""")
        live = [MAPS / "index.html", *[p for p in MAPS.glob("*/index.html")]]
        for page in live:
            self.assertIsNone(link.search(page.read_text()), page)
        for data in ("www/data/crew.json", "www/data/site.json"):
            path = ROOT / data
            if path.exists():
                self.assertNotRegex(path.read_text(), r"crew/maps/[\w/-]*generated", data)


if __name__ == "__main__":
    unittest.main()
