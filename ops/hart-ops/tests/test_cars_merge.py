"""cars.merge_car (shared by intake and records), the stage dispatcher and the field-difference records."""
import argparse
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "card_pipeline"))

import cars  # noqa: E402
from car_records import FieldDiff, IntakeContext, MergeOutcome  # noqa: E402

COLUMNS = ["source_image", "reporting_marks", "road_name", "road_number", "car_type", "roster_id",
           "roster_road", "roster_length_ft", "roster_weight_oz", "roster_weight_tons"]


def new_row(**values: str) -> dict[str, str]:
    row = {c: "" for c in COLUMNS}
    row.update({"reporting_marks": "N&W", "road_number": "32800", "car_type": "Flatcar"}, **values)
    return row


def known_car(**values: str) -> dict[str, str]:
    row = {c: "" for c in COLUMNS}
    row.update({"roster_id": "NW32800", "road_number": "32800", "reporting_marks": "N&W",
                "road_name": "N&W"}, **values)
    return row


class MergeCarTest(unittest.TestCase):
    def test_new_car_is_appended_and_queued(self) -> None:
        rows, queue = [], []
        merged = cars.merge_car(new_row(source_image="a.png"), rows, COLUMNS, queue, dry_run=False)
        self.assertEqual((merged.roster_id, merged.outcome), ("NW32800", MergeOutcome.NEW_CAR))
        self.assertEqual(len(rows), 1)
        self.assertEqual((queue[0]["roster_id"], queue[0]["reason"]), ("NW32800", "new car"))

    def test_dry_run_reports_and_changes_nothing(self) -> None:
        rows, queue = [known_car()], []
        merged = cars.merge_car(new_row(source_image="a.png"), rows, COLUMNS, queue, dry_run=True)
        self.assertIs(merged.outcome, MergeOutcome.PHOTO_ADDED)
        self.assertEqual(rows[0]["source_image"], "")
        self.assertEqual(queue, [])

    def test_car_with_a_photo_is_left_alone(self) -> None:
        rows, queue = [known_car(source_image="old.png")], []
        merged = cars.merge_car(new_row(source_image="new.png"), rows, COLUMNS, queue, dry_run=False)
        self.assertEqual((merged.outcome, merged.existing_image), (MergeOutcome.SKIPPED, "old.png"))
        self.assertEqual(rows[0]["source_image"], "old.png")
        self.assertEqual(queue, [])

    def test_blank_values_do_not_overwrite_the_known_car(self) -> None:
        rows, queue = [known_car(car_type="Boxcar")], []
        cars.merge_car(new_row(source_image="a.png", car_type=""), rows, COLUMNS, queue, dry_run=False)
        self.assertEqual((rows[0]["car_type"], rows[0]["source_image"]), ("Boxcar", "a.png"))
        self.assertEqual(queue[0]["reason"], "photo added")

    def test_row_without_marks_stops(self) -> None:
        with self.assertRaises(cars.CardPipelineError):
            cars.merge_car(new_row(reporting_marks=""), [], COLUMNS, [], dry_run=False)


class StageTest(unittest.TestCase):
    def test_stage_passes_a_context_built_at_call_time(self) -> None:
        seen: list[IntakeContext] = []
        fake = mock.Mock()
        fake.cmd_review = lambda args, ctx: seen.append(ctx) or 7
        with mock.patch.object(cars.importlib, "import_module", return_value=fake) as imp, \
                mock.patch.object(cars, "IMAGES_DIR", Path("/patched")):
            rc = cars.stage("intake_stages", "cmd_review")(argparse.Namespace())
        imp.assert_called_once_with("intake_stages")
        self.assertEqual(rc, 7)
        self.assertEqual(seen[0].IMAGES_DIR, Path("/patched"))
        self.assertIs(seen[0].record_car, cars.record_car)


class FieldDiffTest(unittest.TestCase):
    def test_field_diffs_names_each_part(self) -> None:
        diffs = cars.field_diffs({"A1": {"type": "Boxcar", "color": ""}},
                                 {"A1": {"type": "Hopper", "color": "Red"}}, {"t": "type", "c": "color"})
        self.assertEqual(diffs, [FieldDiff(car_id="A1", field="type", repo="Boxcar", tool="Hopper")])


if __name__ == "__main__":
    unittest.main()
