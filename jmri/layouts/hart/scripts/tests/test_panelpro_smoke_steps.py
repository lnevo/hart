"""The PanelPro smoke test's steps that run without JMRI (panelpro_smoke_test.py, Jython inside JMRI): the bean
counts, the station sensors, a TrainInfo route's order and the marker file's text. Taken from the source as
test_panelpro_smoke_blocks.py takes them; the script itself is never run here."""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_panelpro_smoke_blocks import plain_parts  # noqa: E402

STEPS = ("MASTS", "SECTIONS", "TRANSITS", "TRAININFO", "BAND_PANELS", "STATIONS", "station_key", "bean_count",
         "station_sensor_errors", "count_errors", "ordered_route", "_line", "marker_text")


class _Beans:
    def __init__(self, n: int) -> None:
        self.n = n

    def getNamedBeanSet(self):
        return types.SimpleNamespace(size=lambda: self.n)


class _Sensors:
    def __init__(self, names: set[str]) -> None:
        self.names = names

    def getByUserName(self, name: str) -> object | None:
        return object() if name in self.names else None


def steps(parked: str = "") -> dict:
    return plain_parts(STEPS, {"PARKED": set(parked.split()), "unicode": type("unicode", (), {})})


class SmokeSteps(unittest.TestCase):
    def test_counts_name_each_manager_that_differs(self) -> None:
        ns = steps()
        ok = (_Beans(ns["MASTS"]), _Beans(ns["SECTIONS"]), _Beans(ns["TRANSITS"]))
        self.assertEqual(ns["count_errors"](*ok), [])
        self.assertEqual(ns["count_errors"](_Beans(1), ok[1], _Beans(0)),
                         [f"signal masts=1 expected={ns['MASTS']}", f"transits=0 expected={ns['TRANSITS']}"])

    def test_station_sensors_follow_the_dispatcher_parking(self) -> None:
        live = steps()
        key = live["station_key"](live["STATIONS"][0])
        every = {f"{p}{live['station_key'](s)}{q}" for s in live["STATIONS"]
                 for p, q in (("MoveTo", "_stored"), ("MoveInProgress", ""))}
        self.assertEqual(live["station_sensor_errors"](_Sensors(every)), [])
        self.assertEqual(live["station_sensor_errors"](_Sensors(every - {f"MoveTo{key}_stored"})),
                         [f"missing sensor MoveTo{key}_stored"])
        parked = steps("dispatcher")
        self.assertEqual(parked["station_sensor_errors"](_Sensors(set())), [])
        self.assertEqual(parked["station_sensor_errors"](_Sensors({f"MoveInProgress{key}"})),
                         [f"parked Dispatcher sensor MoveInProgress{key} loaded"])

    def test_a_route_needs_its_destination_after_its_start(self) -> None:
        ordered = steps()["ordered_route"]
        self.assertTrue(ordered(["A", "B", "C"], "A", "C"))
        self.assertFalse(ordered(["C", "B", "A"], "A", "C"))
        self.assertTrue(ordered(["A", "C", "A", "B"], "A", "B"))      # a later visit to the start counts
        self.assertFalse(ordered(["A"], "A", "A"))
        self.assertFalse(ordered([], "A", "B"))

    def test_marker_text(self) -> None:
        live = steps()
        self.assertEqual(live["marker_text"](["one", "two"], "x"), "fail\none\ntwo")
        ok = live["marker_text"]([], "LEVEL")
        self.assertTrue(ok.startswith(f"ok\n{live['MASTS']} masts; LEVEL; 24 station sensors; "))
        self.assertTrue(ok.endswith("band panels Staging Level, Main Level, Upper Level loaded and hidden\n"))
        parked = steps("nx dispatcher")["marker_text"]([], "LEVEL")
        self.assertIn("; parked dispatcher nx: no section, transit, Dispatcher sensor or parked window; ", parked)


if __name__ == "__main__":
    unittest.main()
