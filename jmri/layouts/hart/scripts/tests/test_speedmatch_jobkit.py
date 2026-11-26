"""speedmatch/jython/jobkit.py end_job: every stop step runs and every failure is logged.

jobkit.py is pasted in front of a runner and run inside JMRI, so here it runs as Python 3 with
stand-in java and jmri modules and a fake throttle. No JMRI, no layout, no MQTT.
"""
from __future__ import annotations

import sys
import tempfile
import types
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import cast

KIT = Path(__file__).resolve().parents[1] / "speedmatch" / "jython" / "jobkit.py"


class Throwable(Exception):
    """Stands in for java.lang.Throwable, which Python's Exception does not catch in Jython."""


class Throttle:
    def __init__(self, fail: set[str]) -> None:
        self.fail = fail
        self.calls: list[str] = []

    def _do(self, name: str) -> None:
        self.calls.append(name)
        if name in self.fail:
            raise Throwable("%s broke" % name)

    def setSpeedSetting(self, x: float) -> None:
        self._do("speed %s" % x)

    def setF1(self, on: bool) -> None:
        self._do("F1 %s" % on)

    def release(self, tl: object) -> None:
        self._do("release")


class Sensor:
    def __init__(self, fail: bool) -> None:
        self.fail = fail

    def removePropertyChangeListener(self, listener: object) -> None:
        if self.fail:
            raise RuntimeError("listener stuck")


class EndJob(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.log = self.tmp / "run.log"
        java = types.ModuleType("java")
        java.lang = types.SimpleNamespace(Throwable=Throwable)
        java.beans = types.SimpleNamespace(PropertyChangeListener=object)
        jmri = types.ModuleType("jmri")
        jmri.ThrottleListener = object
        self.saved = {k: sys.modules.get(k) for k in ("java", "jmri")}
        sys.modules["java"], sys.modules["jmri"] = java, jmri
        src = KIT.read_text().replace("/tmp/speedrun", str(self.tmp / "speedrun"))
        self.ns: dict[str, object] = {"LOGF": str(self.log), "ORDER": []}
        exec(compile(src, str(KIT), "exec"), self.ns)

    def tearDown(self) -> None:
        self.ns["f"].close()
        for k, v in self.saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    def msgs(self) -> list[str]:
        return [ln.split(" ", 1)[1] for ln in self.log.read_text().splitlines()]

    def test_clean_stop_in_order(self) -> None:
        self.assertTrue(self.ns["claim"]())
        t = Throttle(set())
        self.ns["end_job"](t, "tl", [0, 1])
        self.assertEqual(t.calls, ["speed 0.0", "F1 False", "release"])
        self.assertEqual(self.msgs(), ["STOP ", "speed 0", "F0 not switched off", "F1 off",
                                       "throttle released", "END"])
        self.assertFalse((self.tmp / "speedrun.active").exists())

    def test_every_failure_is_logged_and_the_rest_still_runs(self) -> None:
        t = Throttle({"speed 0.0", "F1 False", "release"})
        self.ns["reg"].append((Sensor(True), "l"))
        self.ns["end_job"](t, "tl", [1])
        self.assertEqual(t.calls, ["speed 0.0", "F1 False", "release"])
        self.assertEqual(self.msgs(), ["STOP ", "speed 0 failed speed 0.0 broke", "F1 off failed F1 False broke",
                                       "release failed release broke", "listener removal failed listener stuck",
                                       "END"])

    def test_a_marker_that_cannot_be_removed_is_logged(self) -> None:
        self.ns["own"][0] = True  # claimed, but the marker is already gone
        self.ns["end_job"](None, None, [])
        msgs = self.msgs()
        self.assertEqual(msgs[-1], "END")
        self.assertTrue(msgs[-2].startswith("marker removal failed"), msgs)

    def test_a_late_throttle_is_released_and_logged(self) -> None:
        tl = self.ns["TL"]()
        tl.gave_up = True
        t = Throttle({"release"})
        tl.notifyThrottleFound(t)
        self.assertIsNone(tl.t)
        self.assertEqual(self.msgs(), ["late release failed release broke"])
        tl.notifyThrottleFound(Throttle(set()))
        self.assertEqual(self.msgs()[-1], "late throttle released")

    def test_route_sensor_takes_block_sensors_but_the_brick_yard_spurs(self) -> None:
        route_sensor = cast(Callable[[str], bool], self.ns["route_sensor"])
        self.assertTrue(route_sensor("BS Switch 33"))
        self.assertTrue(route_sensor("BS W-3"))
        for name in ("BS W-1", "BS W-2", "Track W-1", "", "IS12"):
            self.assertFalse(route_sensor(name), name)

    def test_scan_with_route_sensor_hears_a_spur_only_as_a_guard(self) -> None:
        beans = [Bean("BS Switch 33", "IS1"), Bean("BS W-1", "IS2"), Bean("BS W-2", "IS3"), Bean("", "IS4")]
        manager = types.SimpleNamespace(getNamedBeanSet=lambda: beans)
        setattr(sys.modules["jmri"], "InstanceManager", types.SimpleNamespace(sensorManagerInstance=lambda: manager))
        heard: list[tuple[str, bool]] = []

        def listener(name: str, isg: bool, bean: Bean) -> str:
            heard.append((name, isg))
            return "listener " + name

        scan = cast(Callable[..., dict[str, Bean]], self.ns["scan"])
        found = scan(["BS W-2"], [], self.ns["route_sensor"], listener)
        self.assertEqual(heard, [("BS Switch 33", False), ("BS W-2", True)])
        self.assertEqual(found, {"BS W-2": beans[2]})
        self.assertEqual(beans[1].listeners, [])


class Bean:
    """A JMRI sensor as scan() sees it: names and a listener list."""

    def __init__(self, user: str, system: str) -> None:
        self.user, self.system = user, system
        self.listeners: list[object] = []

    def getUserName(self) -> str:
        return self.user

    def getSystemName(self) -> str:
        return self.system

    def addPropertyChangeListener(self, listener: object) -> None:
        self.listeners.append(listener)


if __name__ == "__main__":
    unittest.main()
