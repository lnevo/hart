"""The road display table is one table, in engine_lookup, and the all-cards sheet reads it."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "card_pipeline"))

import engine_lookup  # noqa: E402
import generate_all_cards as gen  # noqa: E402


class RoadDisplay(unittest.TestCase):
    def test_the_card_sheet_uses_the_engine_lookup_table(self):
        self.assertIs(gen.ROAD_DISPLAY, engine_lookup.ROAD_DISPLAY)

    def test_rostered_car_shows_the_display_mark(self):
        self.assertEqual(gen.display_road({"roster_id": "NW1", "roster_road": "NW"}, {}), "N&W")
        self.assertEqual(gen.display_road({"roster_id": "X1", "roster_road": "CWRY"}, {}), "Ohio Central")

    def test_unknown_road_shows_itself_and_blank_shows_a_question_mark(self):
        self.assertEqual(gen.display_road({"roster_id": "X1", "roster_road": "ABC"}, {}), "ABC")
        self.assertEqual(gen.display_road({"roster_id": "X1", "roster_road": ""}, {}), "?")

    def test_unrostered_row_with_marks_shows_the_marks(self):
        self.assertEqual(gen.display_road({"reporting_marks": "B&O"}, {}), "B&O")


if __name__ == "__main__":
    unittest.main()
