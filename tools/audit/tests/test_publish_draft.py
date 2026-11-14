"""publish_draft.py bumps the title block only for a real drawing change."""
from __future__ import annotations

import datetime
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("publish_draft", ROOT / "tools/schematic/publish_draft.py")
PD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PD)

FIELD = '<text x="362" y="763.8" font-size="9.5" letter-spacing="1">REV {}</text>'


class PublishDraftTest(unittest.TestCase):
    def test_title_fields_are_not_a_drawing_change(self) -> None:
        a = "<svg>\n<path d=\"M0,0\"/>\n" + FIELD.format(1) + "\n</svg>"
        b = "<svg>\n<path d=\"M0,0\"/>\n" + FIELD.format(2) + "\n</svg>"
        self.assertEqual(PD.drawing_only(a), PD.drawing_only(b))
        self.assertNotEqual(PD.drawing_only(a), PD.drawing_only(b.replace("M0,0", "M1,0")))

    def test_other_text_counts(self) -> None:
        name = '<text x="34" y="748" font-size="14" font-weight="bold" letter-spacing="1">SYSTEM SCHEMATIC</text>'
        self.assertIn(name, PD.drawing_only(name))

    def test_bump_sets_date_and_adds_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "page.preferences.json"
            p.write_text(json.dumps({"title": ["x"], "date": "2026-11-14", "revision": 1}))
            self.assertEqual(PD.bump(p, datetime.date(2026, 12, 1)), ("2026-12-01", 2))
            self.assertEqual(json.loads(p.read_text())["title"], ["x"])
            p.write_text("{}")
            self.assertEqual(PD.bump(p, datetime.date(2026, 12, 1))[1], 1)


if __name__ == "__main__":
    unittest.main()
