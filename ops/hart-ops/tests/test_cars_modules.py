"""Behaviour of the car workflow modules: live STS records, sync flags, roster errors, locos and gallery records."""
import argparse
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "card_pipeline"))

import car_live_sts  # noqa: E402
import car_ops_roster  # noqa: E402
import car_sync  # noqa: E402
import cars  # noqa: E402
import locos  # noqa: E402
import site_gallery  # noqa: E402
from car_paths import CardPipelineError  # noqa: E402
from car_records import FieldDiff  # noqa: E402

URL = "http://sts.example.invalid/sts/api/v1"


class LiveCarTests(unittest.TestCase):
    def test_blank_and_null_fields_read_as_empty_text(self) -> None:
        car = car_live_sts.LiveCar.from_api({"id": 4, "reporting_marks": None}, URL)
        self.assertEqual(car, car_live_sts.LiveCar(4, "", ""))

    def test_a_car_that_is_not_an_object_is_refused(self) -> None:
        with self.assertRaises(car_live_sts.LiveStsError) as ctx:
            car_live_sts.LiveCar.from_api(["NW2"], URL)
        self.assertIn("not an object", str(ctx.exception))

    def test_a_text_id_is_refused(self) -> None:
        with self.assertRaises(car_live_sts.LiveStsError):
            car_live_sts.LiveCar.from_api({"id": "4"}, URL)

    def test_a_car_without_an_id_stops_the_write_before_any_patch(self) -> None:
        class Api:
            ApiError = RuntimeError
            calls: list[str] = []

            def patch(self, path: str, body: object) -> object:
                self.calls.append(path)
                return {}

        api = Api()
        live = [car_live_sts.LiveCar(None, "NW2", "Flatcar 50ft")]
        with self.assertRaises(car_live_sts.LiveStsError) as ctx:
            car_live_sts.write_live_cars(api, live, [FieldDiff("NW2", "remarks", "Flatcar 52ft", "Flatcar 50ft")])
        self.assertIn("has no id", str(ctx.exception))
        self.assertEqual(api.calls, [])

    def test_read_back_unwraps_an_envelope(self) -> None:
        self.assertEqual(car_live_sts.read_back({"data": {"remarks": "x"}}, "remarks"), "x")
        self.assertEqual(car_live_sts.read_back({"remarks": "y"}, "remarks"), "y")


class SyncRequestTests(unittest.TestCase):
    def ns(self, **kw: object) -> argparse.Namespace:
        base: dict[str, object] = dict(ops_live="ops.xml", apply=False, live_sts=False, sts_url=None)
        base.update(kw)
        return argparse.Namespace(**base)

    def test_url_without_live_is_refused(self) -> None:
        with self.assertRaises(car_sync.SyncRefused):
            car_sync.SyncRequest.from_args(self.ns(sts_url=URL))

    def test_live_apply_without_url_is_refused(self) -> None:
        with self.assertRaises(car_sync.SyncRefused):
            car_sync.SyncRequest.from_args(self.ns(apply=True, live_sts=True))

    def test_plan_parts(self) -> None:
        diff = FieldDiff("NW2", "length", "52", "50")
        plan = car_sync.SyncPlan({car_sync.OPS_TARGET: [diff], car_sync.SEED_META_TARGET: [diff, diff]})
        self.assertEqual((len(plan.ops), len(plan.seed), plan.live, plan.total()), (1, 2, [], 3))


class RosterErrorTests(unittest.TestCase):
    def test_merge_into_a_roster_without_cars_is_a_named_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "live.xml"
            live.write_text("<operations-config></operations-config>")
            with self.assertRaises(CardPipelineError) as ctx:
                car_ops_roster.merge_ops(live, [], live)
        self.assertIn("no <cars> section", str(ctx.exception))

    def test_engine_roster_without_engines_is_a_named_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "engines.xml"
            path.write_text("<operations-config><models/></operations-config>")
            with self.assertRaises(CardPipelineError):
                locos.merge_engines(path, [])

    def test_a_dcc_address_that_is_not_a_number_is_a_named_error(self) -> None:
        row = {"roster_id": "NW 6", "road_name": "NW", "road_number": "6", "model": "GP9", "dcc_address": "six"}
        with self.assertRaises(CardPipelineError) as ctx:
            locos.roster_entry(row)
        self.assertIn("NW 6", str(ctx.exception))


class QueueChoiceTests(unittest.TestCase):
    def test_only_limits_the_queue(self) -> None:
        item = {"roster_id": "NW2", "reason": "", "queued": "", "card_built": "", "card_printed": "",
                "sts": "", "ops": ""}
        self.assertTrue(cars.is_chosen(item, None))
        self.assertTrue(cars.is_chosen(item, ["NW2"]))
        self.assertFalse(cars.is_chosen(item, ["BO1"]))

    def test_parser_lists_every_command_in_order(self) -> None:
        sub = next(a for a in cars.build_parser()._actions if isinstance(a, argparse._SubParsersAction))
        self.assertEqual(list(sub.choices)[:3], ["import-legacy", "intake", "add"])
        self.assertEqual(list(sub.choices)[-2:], ["compare", "sync"])
        self.assertEqual(len(sub.choices), 21)


class GalleryTests(unittest.TestCase):
    def test_locomotive_types_go_in_locos(self) -> None:
        self.assertEqual(site_gallery.album_for("Diesel", {}), "locos")
        self.assertEqual(site_gallery.album_for("Hopper", {"Hopper": "coal"}), "coal")
        self.assertEqual(site_gallery.album_for("Tank", {}), site_gallery.DEFAULT_ALBUM)


if __name__ == "__main__":
    unittest.main()
