"""Intake fill, lettering digits and the editable review sheet."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "card_pipeline"))

import intake_stages as stages  # noqa: E402
import process_car_images as proc  # noqa: E402


def row(photo, blur="100", **fields):
    r = {c: "" for c in stages.REVIEW_COLUMNS}
    r.update(photo=photo, kind="car", status="pending", blur=blur, **fields)
    return r


class Fill(unittest.TestCase):
    def test_best_row_has_most_details_then_sharpest(self):
        a = row("a", car_type="Hopper", lt_wt_lbs="42600")
        b = row("b", blur="900", car_type="Hopper", lt_wt_lbs="42600")
        c = row("c", blur="5000")
        self.assertIs(stages.best_row([a, b, c]), b)

    def test_digits_fix_letters_read_as_numbers(self):
        self.assertEqual(proc._digits("37 97 O2"), "379702")

    def test_sheet_is_editable_and_keeps_every_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "batch" / "review.html"
            path.parent.mkdir()
            stages.contact_sheet(path, [row("x.jpg", reporting_marks="CSX", road_number="1")])
            text = path.read_text(encoding="utf-8")
        self.assertIn('data-f="road_number"', text)
        self.assertIn("Download review.csv", text)
        self.assertIn('"roster_id"', text)


if __name__ == "__main__":
    unittest.main()
