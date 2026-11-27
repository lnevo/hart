"""The operator sheet's industry files agree with the spots: every industry of spot_assignments.csv has an
industry_sheet.csv row under the same name and a waybill order (the sheet and the waybill decks key spots by that
name), every sheet industry has its history notes, and every spot usage has a label (spot_usages.csv). A one-sided
rename in one file fails here instead of crashing the sheet build or dropping a page."""
from __future__ import annotations

import csv
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path[:0] = [str(REPO / "tools/hartlib/src")]
from hartlib import operations  # noqa: E402

SPOTS = operations.HART_OPS_DATA / "spot_assignments.csv"


def spot_rows() -> list[dict[str, str]]:
    with SPOTS.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


class SheetMatchesSpots(unittest.TestCase):
    def setUp(self) -> None:
        self.sheet = {r.industry_id: r for r in operations.read_industry_sheet()}
        self.spots = spot_rows()

    def test_every_spot_industry_is_on_the_sheet_by_the_same_name_with_a_waybill_order(self):
        for row in self.spots:
            r = self.sheet.get(row["industry_id"])
            self.assertIsNotNone(r, f"{row['industry_id']} has spots but no industry_sheet.csv row")
            assert r is not None
            self.assertEqual(r.sheet_name, row["Industry"],
                             f"{row['industry_id']}: industry_sheet.csv calls it {r.sheet_name!r}, the spots "
                             f"{row['Industry']!r}; the sheet and the waybills key spots by this name")
            self.assertIsNotNone(r.waybill_order, f"{row['industry_id']} has spots but no waybill_order")

    def test_every_sheet_industry_has_notes(self):
        notes = operations.read_industry_notes()
        self.assertEqual(sorted(i for i in self.sheet if not notes.get(i)), [])

    def test_every_spot_usage_has_a_label(self):
        labels = operations.read_spot_usages()
        self.assertEqual(sorted({r["Usage"].lower() for r in self.spots} - set(labels)), [])


if __name__ == "__main__":
    unittest.main()
