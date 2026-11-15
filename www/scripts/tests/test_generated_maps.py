"""Station map sheets (ADR-023): every station SVG is published from docs/ops/stations, the crew
map pages show those sheets, and no hand-drawn station PNG or preview page is left."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PUBLISHED = json.loads((ROOT / "www/scripts/published-files.json").read_text())
CREW = json.loads((ROOT / "www/data/crew.json").read_text())
MAPS = ROOT / "www/crew/maps"
SHEETS = sorted((ROOT / "docs/ops/stations").glob("*.svg"))
FOLDER = "crew/maps/generated-sheets/"

sys.path.insert(0, str(ROOT / "www/scripts"))
import prepare_github_pages as pgp  # noqa: E402


class GeneratedMapsTest(unittest.TestCase):
    def test_every_station_svg_is_published_from_docs(self):
        for svg in SHEETS:
            self.assertEqual(PUBLISHED.get(FOLDER + svg.name), f"docs/ops/stations/{svg.name}")

    def test_published_sheets_exist(self):
        for rel, src in PUBLISHED.items():
            if rel.startswith(FOLDER):
                self.assertTrue((ROOT / src).is_file(), src)

    def test_every_sheet_is_on_a_crew_map_page(self):
        used = {s["img"] for m in CREW["maps"] for s in m["sheets"]}
        self.assertEqual(used, {FOLDER + svg.name for svg in SHEETS})

    def test_each_map_shows_only_published_sheets(self):
        for m in CREW["maps"]:
            self.assertEqual(m["img"], m["sheets"][0]["img"], m["id"])
            for s in m["sheets"]:
                self.assertIn(s["img"], PUBLISHED, m["id"])
            self.assertNotIn("source", m, m["id"])
            self.assertNotIn("rotated", m, m["id"])

    def test_sheet_shared_by_south_yard_and_east_end(self):
        shared = FOLDER + "south-yard-and-east-end.svg"
        homes = {m["id"] for m in CREW["maps"] if shared in {s["img"] for s in m["sheets"]}}
        self.assertEqual(homes, {"south-yard", "east-end"})

    def test_station_pages_are_indexed_and_have_no_preview_twin(self):
        self.assertFalse(list(MAPS.glob("**/generated.html")))
        for m in CREW["maps"]:
            page = (MAPS / m["id"] / "index.html").read_text()
            self.assertNotIn("noindex", page, m["id"])
            self.assertIn(f'HARTCrew.page("map", "{m["id"]}")', page)

    def test_hand_drawn_station_pngs_are_retired(self):
        for rel in PUBLISHED:
            self.assertNotRegex(rel, r"assets/maps/station_map_(west_yard|south_yard|barn|east_end|shenango)", rel)
        self.assertNotIn("station_map_west_yard", (ROOT / "www/data/crew.json").read_text())

    def test_revision_comes_from_schematic_preferences(self):
        prefs = json.loads(pgp.SCHEMATIC_PREFS.read_text())
        year, month, day = prefs["date"].split("-")
        rev = pgp.sheet_revision()
        self.assertTrue(rev.startswith(f"REV {prefs['revision']} · "), rev)
        self.assertTrue(rev.endswith(f" {int(day)}, {year}"), rev)
        for m in CREW["maps"]:  # never hand-typed in the source data
            self.assertNotIn("revision", m, m["id"])
            self.assertNotIn("effective", m, m["id"])
            self.assertNotIn("sheetRev", m, m["id"])
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / "data").mkdir()
            (dest / "data/crew.json").write_text(json.dumps(CREW))
            pgp._stamp_sheet_revision(dest)
            built = json.loads((dest / "data/crew.json").read_text())
        self.assertEqual({m["sheetRev"] for m in built["maps"]}, {rev})


if __name__ == "__main__":
    unittest.main()
