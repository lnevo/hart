"""discover_nx.py publishes nothing: the smoke is opt-in (HART_NX_SMOKE=1) and HART_NX_THROW is unset.

setKnownState on an MQTT sensor publishes it (stock MqttSensor.setKnownState), so occupancy for
the Brick smoke and the clear before Discover must be painted with setOwnState. The script runs
here in CPython against small stand-ins; its background worker never starts and nothing can reach
a broker (the stand-in sensors record what would have been sent).
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "discover_nx.py"
UNKNOWN, ACTIVE, INACTIVE = 1, 2, 4


class Sensor:
    def __init__(self, system, user, state=ACTIVE, mqtt=True):
        self.system, self.user, self.state, self.mqtt = system, user, state, mqtt
        self.published = []

    def getSystemName(self):
        return self.system

    def getUserName(self):
        return self.user

    def getDisplayName(self):
        return self.user or self.system

    def getKnownState(self):
        return self.state

    def setKnownState(self, state):   # MqttSensor: publish, then setOwnState
        if self.mqtt:
            self.published.append(state)
        self.state = state

    setState = setKnownState

    def setOwnState(self, state):
        self.state = state


class SensorManager:
    def __init__(self, sensors):
        self.by_name = {}
        for s in sensors:
            self.by_name[s.system] = s
            if s.user:
                self.by_name[s.user] = s

    def getSensor(self, name):
        return self.by_name.get(name)

    def getNamedBeanSet(self):
        return list({id(s): s for s in self.by_name.values()}.values())


class Thread:
    started = []

    def __init__(self, target=None):
        self.target = target

    def setName(self, name):
        pass

    def setDaemon(self, value):
        pass

    def start(self):
        Thread.started.append(self.target)   # never run

    @staticmethod
    def sleep(ms):
        pass


def _modules(manager):
    def mod(name, **attrs):
        m = types.ModuleType(name)
        m.__dict__.update(attrs)
        return m

    iface = type("Iface", (), {})
    entryexit = mod("jmri.jmrit.entryexit", EntryExitPairs=types.SimpleNamespace(FULLINTERLOCK=1,
                                                                               SETUPSIGNALMASTLOGIC=2))
    layout_editor = mod("jmri.jmrit.display.layoutEditor", LayoutBlockConnectivityTools=iface)
    display = mod("jmri.jmrit.display", layoutEditor=layout_editor)
    jmrit = mod("jmri.jmrit", display=display, entryexit=entryexit)
    util = mod("jmri.util", FileUtil=types.SimpleNamespace())
    jmri = mod("jmri", Sensor=types.SimpleNamespace(UNKNOWN=UNKNOWN, ACTIVE=ACTIVE, INACTIVE=INACTIVE),
               InstanceManager=types.SimpleNamespace(sensorManagerInstance=lambda: manager),
               jmrit=jmrit, util=util)
    lang = mod("java.lang", Runnable=iface, System=types.SimpleNamespace(exit=lambda code: None), Thread=Thread)
    beans = mod("java.beans", PropertyChangeListener=iface)
    swing = mod("javax.swing", SwingUtilities=types.SimpleNamespace())
    return {"jmri": jmri, "jmri.jmrit": jmrit, "jmri.jmrit.display": display,
            "jmri.jmrit.display.layoutEditor": layout_editor, "jmri.jmrit.entryexit": entryexit,
            "jmri.util": util, "java": mod("java", lang=lang, beans=beans), "java.lang": lang,
            "java.beans": beans, "javax": mod("javax", swing=swing), "javax.swing": swing}


class DefaultPathPublishesNothing(unittest.TestCase):
    def setUp(self) -> None:
        self.sensors = [Sensor("M2S100", "Block East Lead"), Sensor("M2S101", "BS Switch 1", INACTIVE),
                        Sensor("M2S102", None), Sensor("IS:SML_MODE", "Signals", mqtt=False)]
        self.manager = SensorManager(self.sensors)
        env = {k: v for k, v in os.environ.items() if not k.startswith("HART_NX_")}
        self.patches = [mock.patch.dict(os.environ, env, clear=True),
                        mock.patch.dict(sys.modules, _modules(self.manager))]
        for p in self.patches:
            p.start()
        Thread.started.clear()
        self.ns = {"__name__": "discover_nx_under_test"}
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec"), self.ns)

    def tearDown(self) -> None:
        for p in reversed(self.patches):
            p.stop()

    def test_defaults_are_smoke_off_throw_off(self) -> None:
        self.assertFalse(self.ns["SMOKE"])
        self.assertFalse(self.ns["THROW"])
        self.assertEqual(1, len(Thread.started))   # worker scheduled, not run here

    def test_occupancy_is_painted_never_published(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            cleared = self.ns["_clear_all_occupancy"]()
            self.ns["_set_occupancy"](True)
            occupied = self.manager.getSensor("BS Switch 1").state
            self.ns["_set_occupancy"](False)
        self.assertEqual(2, cleared)   # Block East Lead and M2S102; BS Switch 1 was already clear
        self.assertEqual(ACTIVE, occupied)
        for s in self.sensors:
            self.assertEqual([], s.published, s.system)
        self.assertEqual(INACTIVE, self.manager.getSensor("M2S100").state)
        self.assertEqual(ACTIVE, self.manager.getSensor("IS:SML_MODE").state)   # not an occupancy sensor

    def test_a_sensor_without_a_paint_only_setter_stops_the_smoke(self) -> None:
        odd = types.SimpleNamespace(getDisplayName=lambda: "BS Switch 1", published=[])
        self.manager.by_name["BS Switch 1"] = odd
        with self.assertRaises(RuntimeError), contextlib.redirect_stdout(io.StringIO()):
            self.ns["_set_occupancy"](True)
        self.assertEqual([], odd.published)

    def test_no_state_setter_that_publishes_is_called_anywhere(self) -> None:
        code = "\n".join(line.split("#", 1)[0] for line in SCRIPT.read_text(encoding="utf-8").splitlines())
        self.assertIsNone(re.search(r"\.(setKnownState|setState|setCommandedState)\(", code))


if __name__ == "__main__":
    unittest.main()
