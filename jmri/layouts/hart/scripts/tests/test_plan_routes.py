"""plan_routes: the walk of a route over plan parts, its errors, and the values read from the owner's plan 5.3c
where it is on this machine (never in CI: the .any file stays private)."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import infer_block_lengths as ibl  # noqa: E402
import lengths_fixture  # noqa: E402  the routes' values on the plan 5.3c
import plan_routes as pr  # noqa: E402

PLAN_C = Path.home() / "Documents/Layout/Lee Nevo Design Version 5.3c.any"


def turnout(index, x0=0.0):
    """A turnout part as the plugin's reader gives it: points end 0, straight end 1 10 cm on, diverging end 2."""
    ends = [dict(x=x0, y=0.0), dict(x=x0 + 10.0, y=0.0), dict(x=x0 + 10.0, y=1.0)]
    return dict(index=index, kind="turnout", ends=ends, points=0, straight=1, diverging=2)


# two turnouts in a loop: 5's straight leg to 7's points (100 cm), 7's straight leg back to 5's points (200 cm)
PARTS = [turnout(0), turnout(1, 500.0)]
RUNS = [(0, 1, 1, 0, 100.0), (1, 0, 0, 1, 100.0), (1, 1, 0, 0, 200.0), (0, 0, 1, 1, 200.0),
        (0, 2, None, None, 50.0), (1, 2, None, None, 50.0)]
LABELS = {0: "5", 1: "7"}
STEPS = (pr.Step("5", "straight", "Switch 5"), pr.Step("7", "straight", "Switch 7"))


class Walk(unittest.TestCase):
    def test_length_and_pins(self):
        got = pr.walk(PARTS, RUNS, LABELS, STEPS)
        # 100 mm through 5, 1000 mm run, 100 mm through 7, 2000 mm run
        self.assertEqual(got, pr.RoutePlan(3200.0, {"Switch 5": 50, "Switch 7": 1150}))

    def test_a_turnout_that_is_not_the_switch_named_stops(self):
        with self.assertRaisesRegex(pr.PlanRouteError, "reached is Switch 7"):
            pr.walk(PARTS, RUNS, LABELS, (STEPS[0], pr.Step("9", "straight")))

    def test_leaving_by_the_points_after_coming_in_at_them_stops(self):
        with self.assertRaisesRegex(pr.PlanRouteError, "cannot leave by them"):
            pr.walk(PARTS, RUNS, LABELS, (STEPS[0], pr.Step("7", "points")))

    def test_leaving_by_a_leg_after_coming_in_on_one_stops(self):
        runs = [(0, 1, 1, 1, 100.0), (1, 0, 0, 0, 200.0)]       # 5's straight leg meets 7's straight leg
        with self.assertRaisesRegex(pr.PlanRouteError, "leaves by the points, not the diverging leg"):
            pr.walk(PARTS, runs, LABELS, (STEPS[0], pr.Step("7", "diverging")))

    def test_a_track_end_stops(self):
        with self.assertRaisesRegex(pr.PlanRouteError, "reaches a track end"):
            pr.walk(PARTS, RUNS, LABELS, (pr.Step("5", "diverging"),))

    def test_a_route_that_does_not_close_stops(self):
        with self.assertRaisesRegex(pr.PlanRouteError, "does not close"):
            pr.walk(PARTS, RUNS, LABELS, STEPS[:1])

    def test_a_start_switch_on_two_parts_stops(self):
        with self.assertRaisesRegex(pr.PlanRouteError, "is 2 plan parts"):
            pr.walk(PARTS, RUNS, {0: "5", 1: "5"}, STEPS)

    def test_no_steps_stops(self):
        with self.assertRaisesRegex(pr.PlanRouteError, "no steps"):
            pr.walk(PARTS, RUNS, LABELS, ())

    def test_a_part_with_no_such_leg_stops(self):
        parts = [PARTS[0], dict(PARTS[1], kind="crossing", points=None)]
        with self.assertRaisesRegex(pr.PlanRouteError, "is a crossing"):
            pr.walk(parts, RUNS, LABELS, STEPS)


class Labels(unittest.TestCase):
    def test_t_numbers(self):
        self.assertEqual(pr.switch_labels({"T114": "5", "T33": "7"}), {114: "5", 33: "7"})

    def test_a_key_that_is_no_t_number_stops(self):
        with self.assertRaisesRegex(pr.PlanRouteError, "'X1' is no plan T number"):
            pr.switch_labels({"X1": "5"})


class Routes(unittest.TestCase):
    def test_both_routes_start_at_switch_5_and_pin_the_same_sensors_as_the_fixture(self):
        for route, steps in pr.ROUTE_STEPS.items():
            self.assertEqual(steps[0].switch, "5")
            self.assertEqual({s.pin for s in steps if s.pin}, set(lengths_fixture.PLAN_ROUTES[route].turnouts), route)

    def test_switches_23b_and_31_are_not_pinned_on_loop2(self):
        pins = {s.pin for s in pr.ROUTE_STEPS["loop2"]}
        self.assertFalse(pins & {"Switch 23b", "Switch 31"})

    def test_every_pin_is_a_sensor_of_its_route(self):
        for route, steps in pr.ROUTE_STEPS.items():
            self.assertLessEqual({s.pin for s in steps if s.pin}, set(ibl.route_rows(route)), route)

    def test_plan_names_the_routes_it_has(self):
        with mock.patch.object(pr, "plan_routes", return_value=lengths_fixture.PLAN_ROUTES):
            self.assertEqual(ibl.plan("loop2"), lengths_fixture.LOOP2)
            with self.assertRaisesRegex(pr.PlanRouteError, "no plan route 'loop9'"):
                ibl.plan("loop9")

    def test_a_missing_plan_file_stops(self):
        pr.plan_routes.cache_clear()
        try:
            with mock.patch.object(pr, "plan_path", return_value=Path("/nonexistent/plan.any")):
                with self.assertRaisesRegex(pr.PlanRouteError, "not on this machine"):
                    pr.plan_routes()
        finally:
            pr.plan_routes.cache_clear()


@unittest.skipUnless(PLAN_C.exists(), "the owner's plan 5.3c is not on this machine")
class ReaderFails(unittest.TestCase):
    def test_a_plugin_that_will_not_load_is_a_plan_route_error(self) -> None:
        pr._plan_lengths()                      # puts tools/schematic on the path, so le_common imports
        import le_common

        broken = mock.Mock()
        broken.anyplan.side_effect = le_common.BuildError("the schematic plugin is not checked out")
        with mock.patch.object(pr, "_plan_lengths", return_value=broken):
            with self.assertRaisesRegex(pr.PlanRouteError, "the plan reader failed: the schematic plugin"):
                pr.read_plan(Path("plan.any"))


class Plan53c(unittest.TestCase):
    """The values read from the plan file are the fixture's, which the tests without the plan use."""

    def test_routes_read_from_the_plan(self):
        self.assertEqual(pr.read_plan(PLAN_C), lengths_fixture.PLAN_ROUTES)


if __name__ == "__main__":
    unittest.main()
