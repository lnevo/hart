"""Car queue and Operations Pro merge rules."""
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

    def test_rename_keeps_session_state_and_header(self):
        live_text = '<?xml version="1.0"?>\n<!DOCTYPE operations-config SYSTEM "x.dtd">\n' + LIVE
        fixed = """<operations-config><cars>
<car id="NW2" roadName="NW" roadNumber="2" color="Black" />
</cars></operations-config>"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            live = tmp / "live.xml"
            live.write_text(live_text)
            merged = tmp / "merged.xml"
            merged.write_text(fixed)
            cars.MERGED, cars.OPS_MERGED = merged, tmp / "out.xml"
            self.assertEqual(cars.merge_ops(live, ["NW2"], {"PRR1": "NW2"}), [])
            found = ET.parse(live).getroot().findall("./cars/car")
            self.assertEqual([c.get("id") for c in found], ["NW2"])
            self.assertEqual(found[0].get("roadName"), "NW")
            self.assertEqual(found[0].get("locationId"), "9")
            self.assertEqual(found[0].get("moves"), "7")
            self.assertIn("DOCTYPE", live.read_text())

    def test_rename_refuses_when_both_ids_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            live = tmp / "live.xml"
            live.write_text(LIVE)
            merged = tmp / "merged.xml"
            merged.write_text(MERGED)
            cars.MERGED, cars.OPS_MERGED = merged, tmp / "out.xml"
            with self.assertRaises(SystemExit):
                cars.merge_ops(live, [], {"PRR1": "PRR1"})


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


if __name__ == "__main__":
    unittest.main()
