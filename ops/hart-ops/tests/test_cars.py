"""Car queue and Operations Pro merge rules."""
import contextlib
import io
import sys
import tempfile
import unittest
import unittest.mock
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "card_pipeline"))

import cars  # noqa: E402

LIVE = """<operations-config><roads><road name="PRR" /></roads><types /><colors />
<cars><car id="PRR1" roadName="PRR" roadNumber="1" locationId="9" moves="7" /></cars>
</operations-config>"""
MERGED = """<operations-config><cars>
<car id="PRR1" roadName="PRR" roadNumber="1" moves="0" />
<car id="NW2" roadName="NW" roadNumber="2" type="Flatcar" color="Black" />
</cars></operations-config>"""


class QueueTests(unittest.TestCase):
    def test_new_car_needs_every_step(self):
        queue = []
        cars.enqueue(queue, "NW2", "new car")
        self.assertEqual((queue[0]["sts"], queue[0]["ops"]), ("", ""))

    def test_photo_only_needs_a_card(self):
        queue = []
        cars.enqueue(queue, "NW2", "photo added")
        self.assertTrue(queue[0]["sts"] and queue[0]["ops"])
        self.assertEqual(queue[0]["card_built"], "")

    def test_requeue_resets_unprinted_card(self):
        queue = []
        cars.enqueue(queue, "NW2", "new car")
        queue[0]["card_built"] = "2026-10-31"
        cars.enqueue(queue, "NW2", "photo added")
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["card_built"], "")
        self.assertEqual(queue[0]["sts"], "")


class OpsMergeTests(unittest.TestCase):
    def test_adds_car_and_keeps_session_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            live = tmp / "live.xml"
            live.write_text(LIVE)
            merged = tmp / "merged.xml"
            merged.write_text(MERGED)
            cars.MERGED, cars.OPS_MERGED = merged, tmp / "out.xml"
            self.assertEqual(cars.merge_ops(live, ["PRR1", "NW2"]), ["NW2"])
            root = ET.parse(live).getroot()
            found = {c.get("id"): c for c in root.findall("./cars/car")}
            self.assertEqual(found["PRR1"].get("locationId"), "9")
            self.assertEqual(found["PRR1"].get("moves"), "7")
            self.assertIn("NW", [r.get("name") for r in root.find("roads")])

    def test_keeps_header(self):
        live_text = '<?xml version="1.0"?>\n<!DOCTYPE operations-config SYSTEM "x.dtd">\n' + LIVE
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            live = tmp / "live.xml"
            live.write_text(live_text)
            merged = tmp / "merged.xml"
            merged.write_text(MERGED)
            cars.MERGED, cars.OPS_MERGED = merged, tmp / "out.xml"
            self.assertEqual(cars.merge_ops(live, ["NW2"]), ["NW2"])
            self.assertIn("DOCTYPE", live.read_text())


class OutOfServiceTests(unittest.TestCase):
    def merge(self, live_text, out):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            live = tmp / "live.xml"
            live.write_text(live_text)
            merged = tmp / "merged.xml"
            merged.write_text(MERGED)
            with (
                unittest.mock.patch.object(cars, "MERGED", merged),
                unittest.mock.patch.object(cars, "OPS_MERGED", tmp / "out.xml"),
            ):
                cars.merge_ops(live, [], out_of_service=out)
            return ET.parse(live).getroot().find("cars/car")

    def test_flag_set_and_session_state_kept(self):
        car = self.merge(LIVE, {"PRR1"})
        self.assertEqual(car.get("outOfService"), "true")
        self.assertEqual(car.get("moves"), "7")

    def test_flag_cleared_when_repository_clears_it(self):
        car = self.merge(LIVE.replace('moves="7"', 'moves="7" outOfService="true"'), set())
        self.assertIsNone(car.get("outOfService"))

    def test_ids_come_from_the_column(self):
        rows = [{"roster_id": "NW2", "out_of_service": "yes"}, {"roster_id": "PRR1"}]
        self.assertEqual(cars.out_of_service_ids(rows), {"NW2"})


class SeedCopyTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.data = tmp / "data"
        self.inputs = tmp / "inputs"
        self.data.mkdir()
        self.inputs.mkdir()
        self.masters = (self.data / "a.csv", self.data / "b.xml")
        for m in self.masters:
            m.write_text("master " + m.name)
            (self.inputs / m.name).write_text("master " + m.name)

    def test_same(self):
        lines = cars.seed_copy_report(self.inputs, self.masters)
        self.assertEqual(lines, ["  a.csv: same", "  b.xml: same"])

    def test_differs_names_the_fix(self):
        (self.inputs / "b.xml").write_text("old")
        lines = cars.seed_copy_report(self.inputs, self.masters)
        self.assertEqual(lines[0], "  a.csv: same")
        self.assertEqual(lines[1], "  b.xml: differs")
        self.assertIn("bin/cars seed-copy", lines[-1])

    def test_missing_copy_differs(self):
        (self.inputs / "a.csv").unlink()
        lines = cars.seed_copy_report(self.inputs, self.masters)
        self.assertIn("differs", lines[0])

    def test_submodule_missing_is_said(self):
        lines = cars.seed_copy_report(self.inputs / "nope", self.masters)
        self.assertEqual(len(lines), 1)
        self.assertIn("submodule", lines[0])

    def test_missing_master_is_reported_and_compare_continues(self):
        self.masters[0].unlink()
        lines = cars.seed_copy_report(self.inputs, self.masters)
        self.assertEqual(lines[0], "  a.csv: master is missing")
        self.assertEqual(lines[1], "  b.xml: same")

    def test_hint_names_the_narrow_command(self):
        (self.inputs / "b.xml").write_text("old")
        self.assertIn("bin/cars seed-copy", cars.seed_copy_report(self.inputs, self.masters)[-1])

    def test_sync_copies_only_the_masters(self):
        (self.inputs / "b.xml").write_text("old")
        (self.inputs / "other.txt").write_text("keep")
        cars.sync_seed_copies(self.inputs, self.masters)
        self.assertEqual((self.inputs / "b.xml").read_text(), "master b.xml")
        self.assertEqual((self.inputs / "other.txt").read_text(), "keep")

    def test_sync_stops_clearly_without_the_submodule(self):
        with self.assertRaises(cars.CardPipelineError) as ctx:
            cars.sync_seed_copies(self.inputs / "nope", self.masters)
        self.assertIn("submodule", str(ctx.exception))

    def test_sync_stops_on_missing_master_before_copying(self):
        self.masters[1].unlink()
        (self.inputs / "a.csv").write_text("old")
        with self.assertRaises(cars.CardPipelineError):
            cars.sync_seed_copies(self.inputs, self.masters)
        self.assertEqual((self.inputs / "a.csv").read_text(), "old")


class FieldDifferenceTests(unittest.TestCase):
    """compare: field differences for cars held by the repository and a tool."""

    def row(self, rid="NW2", **kw):
        base = {"roster_id": rid, "roster_road": "NW", "road_number": rid[2:], "car_type": "Flatcar",
                "roster_length_ft": "52", "color": "Black", "notes": "owner note"}
        base.update(kw)
        return base

    def ops(self, tmp, cars_xml):
        path = Path(tmp) / "ops.xml"
        path.write_text(f"<operations-config><cars>{cars_xml}</cars></operations-config>")
        return path

    def diffs(self, rows, path):
        return cars.field_diffs(
            cars.expected_cars(rows, cars.OPS_SKIP_TYPES), cars.ops_car_attrs(path),
            cars.OPS_FIELDS,
        )

    def test_match_reports_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.ops(tmp, '<car id="NW2" roadName="NW" roadNumber="2" type="Flatcar" length="52" color="Black"/>')
            self.assertEqual(self.diffs([self.row()], path), [])

    def test_single_field_difference(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.ops(tmp, '<car id="NW2" roadName="NW" roadNumber="2" type="Flatcar" length="50" color="Black"/>')
            self.assertEqual(self.diffs([self.row()], path), [("NW2", "length", "52", "50")])

    def test_field_the_tool_does_not_carry_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.ops(tmp, '<car id="NW2" roadName="NW" roadNumber="2" type="Flatcar" length="52" color="Black" weight="1"/>')
            row = self.row(notes="changed", capy_lbs="99", ld_lmt_lbs="5")
            self.assertEqual(self.diffs([row], path), [])

    def test_type_is_not_compared_and_missing_cars_are_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.ops(tmp, '<car id="NW2" roadName="NW" roadNumber="2" type="Coke Hopper" length="52" color="Black"/>')
            rows = [self.row("NW2", car_type="Hopper"), self.row("NW6")]  # NW6 is not in the tool
            self.assertEqual(self.diffs(rows, path), [])

    def test_blank_repository_column_is_skipped_before_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.ops(tmp, '<car id="NW2" roadName="NW" roadNumber="2" type="Flatcar" length="50" color="Red"/>')
            row = self.row(roster_length_ft="", color="")
            self.assertEqual(self.diffs([row], path), [])

    def test_missing_tool_file_is_not_reported_as_zero(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cars.print_if_present(Path("/nonexistent/ops.xml"), False, lambda: [])
        self.assertIn("Cannot check: /nonexistent/ops.xml is missing", out.getvalue())
        self.assertNotIn("Field differences", out.getvalue())

    def test_seed_metadata_copy(self):
        gen, reason = cars.seed_helpers()
        if gen is None:
            self.skipTest(reason)
        header = "roster_id,road_name,road_number,car_type,car_class,notes\n"
        repo = [
            {"roster_id": "NW1", "car_type": "Coal", "car_class": "HM", "notes": "CarImagesFinal/a"},
            {"roster_id": "NW2", "car_type": "Boxcar", "car_class": "XM", "notes": "CarImagesFinal/b"},
            {"roster_id": "NW3", "car_type": "Coach", "car_class": "", "notes": "CarImagesFinal/c"},
            {"roster_id": "NW4", "car_type": "Boxcar", "car_class": "XM", "notes": "no photo"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "m.csv"
            copy.write_text(
                header
                + "NW1,,,Hopper,HM,CarImagesFinal/a\n"  # Coal reads as Hopper: same
                + "NW2,,,Flatcar,XI,CarImagesFinal/x\n"  # type, class and notes differ
                + "NW3,,,Boxcar,,CarImagesFinal/c\n"  # passenger car: skipped
                + "NW4,,,Flatcar,XM,other\n"  # no photo: skipped
            )
            diffs = cars.seed_meta_diffs(repo, copy, gen)
        self.assertEqual(
            diffs,
            [("NW2", "car_class", "XM", "XI"), ("NW2", "car_type", "Boxcar", "Flatcar"),
             ("NW2", "notes", "CarImagesFinal/b", "CarImagesFinal/x")],
        )

    def test_added_cars_marks_and_remarks(self):
        gen, reason = cars.seed_helpers()
        if gen is None:
            self.skipTest(reason)
        rows = [self.row("NW2", car_type="Hopper"), self.row("NW3", car_type="Caboose")]
        added = {
            "NW2": {"reporting_marks": "NW2", "remarks": "Hopper 50ft"},
            "NW3": {"reporting_marks": "XX", "remarks": "x"},  # caboose: not an STS freight car
        }
        self.assertEqual(
            cars.added_cars_diffs(rows, added, gen),
            [("NW2", "remarks", "Hopper 52ft", "Hopper 50ft")],
        )

    def test_limit_and_all(self):
        diffs = [(f"NW{i}", "length", "52", "50") for i in range(25)]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cars.print_diffs(diffs, False)
        text = out.getvalue()
        self.assertIn("Field differences: 25", text)
        self.assertEqual(text.count("repo="), 20)
        self.assertIn("+5 more (--all)", text)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cars.print_diffs(diffs, True)
        self.assertEqual(out.getvalue().count("repo="), 25)
        self.assertNotIn("more (--all)", out.getvalue())

    def test_line_format(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cars.print_diffs([("NW2", "length", "52", "50")], False)
        self.assertIn("NW2 length: repo='52' tool='50'", out.getvalue())


if __name__ == "__main__":
    unittest.main()
