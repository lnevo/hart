"""Generated station map previews (ADR-023): every station SVG is published from docs/ops/stations,
every preview page points at a published sheet, and the crew map index does not link them."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PUBLISHED = json.loads((ROOT / "www/scripts/published-files.json").read_text())
MAPS = ROOT / "www/crew/maps"


class GeneratedMapsTest(unittest.TestCase):
    def test_every_station_svg_is_published_from_docs(self):
        for svg in (ROOT / "docs/ops/stations").glob("*.svg"):
            self.assertEqual(PUBLISHED.get(f"crew/maps/generated/{svg.name}"), f"docs/ops/stations/{svg.name}")

    def test_published_sheets_exist(self):
        for rel, src in PUBLISHED.items():
            if rel.startswith("crew/maps/generated/"):
                self.assertTrue((ROOT / src).is_file(), src)

    def test_pages_use_published_sheets_and_are_noindex(self):
        pages = list(MAPS.glob("*/generated.html")) + [MAPS / "generated.html"]
        self.assertEqual(len(pages), 6)
        for page in pages:
            text = page.read_text()
            self.assertIn('<meta name="robots" content="noindex">', text, page)
            self.assertIn("Generated map, preview" if page.parent != MAPS else "Preview for review", text)
            for name in re.findall(r"crew/maps/generated/([\w-]+\.svg)", text):
                self.assertIn(f"crew/maps/generated/{name}", PUBLISHED, page)

    def test_overview_lists_all_sheets(self):
        text = (MAPS / "generated.html").read_text()
        for svg in (ROOT / "docs/ops/stations").glob("*.svg"):
            self.assertIn(f"generated/{svg.name}", text)

    def test_hand_index_does_not_link_generated(self):
        self.assertNotIn("generated", (MAPS / "index.html").read_text())
        self.assertNotIn("generated", (ROOT / "www/data/crew.json").read_text())


if __name__ == "__main__":
    unittest.main()
