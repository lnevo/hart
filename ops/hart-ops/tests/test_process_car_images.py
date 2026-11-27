"""process_car_images: roster rows, the metadata row of one photo, duplicates and the command guard."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "card_pipeline"))

import process_car_images as proc  # noqa: E402

ROSTER = """<?xml version="1.0" encoding="UTF-8"?>
<operations-config><cars>
  <car id="NW32800" roadName="NW" roadNumber="32800" type="Hopper" length="40" weight="2.5" weightTons="30" />
  <car id="BO600409" roadName="BO" roadNumber="600409" />
</cars></operations-config>
"""

NW = proc.RosterCar(
    roster_id="NW32800", roster_road="NW", road_number="32800", car_type="Hopper",
    roster_length_ft="40", roster_weight_oz="2.5", roster_weight_tons="30",
)


def photo_read(roster_car=None, confidence="none", marks="N&W", number="32800", text="N&W 32800"):
    return proc.PhotoRead(text, Image.new("L", (4, 4)), {"capy_lbs": "70000"}, marks, number, roster_car, confidence)


class Roster(unittest.TestCase):
    def test_roster_rows_use_the_metadata_column_names_and_blank_for_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "OperationsCarRoster.xml"
            path.write_text(ROSTER, encoding="utf-8")
            with mock.patch.object(proc, "ROSTER_XML", path):
                cars = proc.load_roster()
        self.assertEqual(cars[0], NW)
        self.assertEqual(cars[1]["car_type"], "")
        self.assertEqual(cars[1]["roster_weight_tons"], "")

    def test_norm_text_keeps_capital_letters_and_digits(self):
        self.assertEqual(proc.norm_text("n&w 32-800"), "NW32800")


class MetadataRow(unittest.TestCase):
    def test_unmatched_photo_keeps_what_ocr_read(self):
        row = proc._metadata_row(Path("Images/IMG_1.png"), photo_read(), "review")
        self.assertEqual(row["cropped_image"], "CarImages/IMG_1.png")
        self.assertEqual(row["ocr_zoom_image"], "OcrZoom/OCR_IMG_1.png")
        self.assertEqual(row["crop_status"], "review")
        self.assertEqual((row["reporting_marks"], row["road_name"], row["road_number"]), ("N&W", "N&W", "32800"))
        self.assertEqual(row["capy_lbs"], "70000")
        self.assertEqual(row["roster_id"], "")
        self.assertEqual(row["match_confidence"], "none")
        self.assertEqual(set(row), set(proc.CSV_COLUMNS) - {"out_of_service"})

    def test_matched_photo_takes_the_roster_columns(self):
        row = proc._metadata_row(Path("IMG_1.png"), photo_read(NW, "road_number", number="3280"), "ok")
        self.assertEqual(row["roster_id"], "NW32800")
        self.assertEqual(row["road_number"], "32800")
        self.assertEqual(row["car_type"], "Hopper")
        self.assertEqual(row["roster_weight_tons"], "30")

    def test_ocr_text_is_one_line_of_at_most_400_characters(self):
        row = proc._metadata_row(Path("IMG_1.png"), photo_read(text="A\nB" + "C" * 500), "ok")
        self.assertEqual(len(row["ocr_text"]), 400)
        self.assertTrue(row["ocr_text"].startswith("A B"))


class Duplicates(unittest.TestCase):
    def test_second_photo_of_a_roster_car_is_flagged(self):
        seen: dict[str, str] = {}
        first = proc._metadata_row(Path("IMG_1.png"), photo_read(NW, "road_number"), "ok")
        second = proc._metadata_row(Path("IMG_2.png"), photo_read(NW, "road_number"), "ok")
        proc._flag_duplicate(first, seen)
        proc._flag_duplicate(second, seen)
        self.assertEqual(first["duplicate_of"], "")
        self.assertEqual(second["duplicate_of"], "IMG_1.png")
        self.assertTrue(second["notes"].endswith("duplicate photo of same car"))

    def test_photo_with_no_identity_is_never_a_duplicate(self):
        seen: dict[str, str] = {}
        for name in ("IMG_1.png", "IMG_2.png"):
            row = proc._metadata_row(Path(name), photo_read(marks="", number=""), "ok")
            proc._flag_duplicate(row, seen)
            self.assertEqual(row["duplicate_of"], "")
        self.assertEqual(seen, {})


class Command(unittest.TestCase):
    def test_main_refuses_without_the_rebuild_flag(self):
        with mock.patch.object(sys, "argv", ["process_car_images.py"]), \
                mock.patch.object(proc, "process_all") as run:
            with self.assertRaises(SystemExit):
                proc.main()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
