"""Station maps: every generated sheet is published from docs/ops/stations, the crew data names only
published sheets, the schematic is published, and no page links the removed preview pages."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PUBLISHED = json.loads((ROOT / "www/scripts/published-files.json").read_text())
CREW = json.loads((ROOT / "www/data/crew.json").read_text())
MAPS = ROOT / "www/crew/maps"
FOLDER = "crew/maps/generated-sheets/"


class StationMapsTest(unittest.TestCase):
    def test_every_station_svg_is_published_from_docs(self):
        svgs = sorted((ROOT / "docs/ops/stations").glob("*.svg"))
        self.assertTrue(svgs)
        for svg in svgs:
            self.assertEqual(PUBLISHED.get(FOLDER + svg.name), f"docs/ops/stations/{svg.name}")

    def test_crew_data_uses_published_sheets(self):
        for m in CREW["maps"]:
            self.assertTrue(m["sheets"], m["id"])
            for sheet in m["sheets"]:
                self.assertIn(sheet, CREW["sheets"])
        for sheet in CREW["sheets"]:
            self.assertIn(FOLDER + sheet + ".svg", PUBLISHED)

    def test_schematic_is_published_with_its_pdf(self):
        sc = CREW["schematic"]
        self.assertEqual(PUBLISHED[sc["svg"]], "docs/ops/schematic-system-draft.svg")
        self.assertEqual(PUBLISHED[sc["pdf"]], "docs/ops/schematic-system-draft.pdf")
        self.assertIn("DRAFT", (ROOT / PUBLISHED[sc["svg"]]).read_text())

    def test_every_map_has_a_live_and_an_archive_page(self):
        for m in CREW["maps"]:
            self.assertTrue((MAPS / m["id"] / "index.html").is_file(), m["id"])
            self.assertTrue((MAPS / "archive" / m["id"] / "index.html").is_file(), m["id"])

    def test_no_preview_pages_remain(self):
        self.assertEqual(list(MAPS.rglob("generated.html")), [])
        for page in MAPS.rglob("*.html"):
            self.assertNotRegex(page.read_text(), r"generated\.html|preview", str(page))


if __name__ == "__main__":
    unittest.main()
