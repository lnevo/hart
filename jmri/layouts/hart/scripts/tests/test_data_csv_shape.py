from __future__ import annotations

import csv
import unittest
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"


class DataCsvShapeTest(unittest.TestCase):
    """A comma in an unquoted note adds a column, and DictReader then hands the
    extra text to a None key that breaks loaders (layout facts, 2026-11-12)."""

    def test_every_row_has_the_header_column_count(self):
        ragged = {}
        for path in sorted(DATA.rglob("*.csv")):
            with path.open(encoding="utf-8", newline="") as fh:
                rows = list(csv.reader(fh))
            if not rows:
                continue
            width = len(rows[0])
            bad = [n for n, row in enumerate(rows, start=1) if row and len(row) != width]
            if bad:
                ragged[str(path.relative_to(DATA))] = bad
        self.assertEqual({}, ragged)


if __name__ == "__main__":
    unittest.main()
