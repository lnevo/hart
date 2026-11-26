"""signal_coordinator.py: message routing, the Signals lamp sensor and the stored-Enabled warning.

Run against an in-memory JMRI (jmri_fake); the MQTT adapter only records. The hand-off,
quit and two-host behaviour is in test_signal_coordinator_behaviour.py.
"""
from __future__ import annotations

import contextlib
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jmri_fake as jf  # noqa: E402
from test_signal_coordinator_behaviour import FakeLogic  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[5] / "jmri/scripts/signal_coordinator.py"
H = jf.SignalHead


class Routing(unittest.TestCase):
    def setUp(self) -> None:
        import __main__

        saved = getattr(__main__, "digicon_sml_controller", None)
        if saved is not None:
            del __main__.digicon_sml_controller

        def restore() -> None:
            if saved is not None:
                __main__.digicon_sml_controller = saved
            elif hasattr(__main__, "digicon_sml_controller"):
                del __main__.digicon_sml_controller

        self.addCleanup(restore)
        self.layout = jf.Layout(mqtt=False)
        self.sc = jf.load_script(SCRIPT, self.layout)
        stack = contextlib.ExitStack()
        stack.enter_context(jf.running(self.layout))
        self.addCleanup(stack.close)
        self.head = self.layout.heads.add(jf.FakeHead("IH432", H.GREEN))
        self.mast = self.layout.masts.add(jf.FakeMast("IF$shsm:basic:one-searchlight(IH432)", "Mast 6LB"))
        self.logic = FakeLogic(self.mast, "Mast 8RA", "Mast 8RB")
        c = self.sc["DigiconMqttSml"]()
        c.mqtt = jf.RecordingAdapter()
        c._masts = [self.mast]
        c._head_to_mast = {"IH432": self.mast}
        c._sml_by_mast = {self.mast: self.logic}
        c._smls = [self.logic]
        c._set_button_label = lambda: None
        self.calls: list[tuple[str, str]] = []
        c._on_sml_mode = lambda m: self.calls.append(("mode", m))
        c._on_sml_claim = lambda m: self.calls.append(("claim", m))
        c._enroll_packed = lambda leaf: self.calls.append(("enroll", leaf))
        c._apply_mast_payload_to_head = lambda leaf, m: self.calls.append(("apply", leaf))
        self.c = c

    def test_sml_mode_full_and_channel_relative_topics(self) -> None:
        for topic in ("track/bridge/sml_mode", "bridge/sml_mode", "other/bridge/sml_mode", "sml_mode"):
            self.calls.clear()
            self.c.notifyMqttMessage(topic, " enabled ")
            self.assertEqual(self.calls, [("mode", "enabled")], topic)

    def test_sml_claim_topics(self) -> None:
        for topic in ("track/bridge/sml_claim", "bridge/sml_claim"):
            self.calls.clear()
            self.c.notifyMqttMessage(topic, "pi 1")
            self.assertEqual(self.calls, [("claim", "pi 1")], topic)

    def test_mast_report_enrols_before_it_paints(self) -> None:
        for topic in ("track/signalmast/432", "signalmast/432", "x/signalmast/432/state"):
            self.calls.clear()
            self.c.notifyMqttMessage(topic, "Stop")
            self.assertEqual(self.calls, [("enroll", "432"), ("apply", "432")], topic)

    def test_signalhead_and_other_topics_are_ignored(self) -> None:
        for topic in ("track/signalhead/432", "x/signalhead/432", "signalhead/432",
                      "track/signalmast/abc", "track/turnout/7"):
            self.c.notifyMqttMessage(topic, "Stop")
        self.assertEqual(self.calls, [])

    def test_signals_lamp_sensor_follows_global_enabled(self) -> None:
        sensor = self.layout.sensors.add(jf.FakeSensor(self.sc["SML_MODE_SENSOR"]))
        self.c._global_enabled = True
        self.c._sync_sml_mode_sensor()
        self.assertEqual(sensor.state, jf.Sensor.ACTIVE)
        self.c._global_enabled = False
        self.c._sync_sml_mode_sensor()
        self.assertEqual(sensor.state, jf.Sensor.INACTIVE)

    def test_panel_lamp_click_is_the_button_toggle(self) -> None:
        toggles = []
        self.c._on_toggle = lambda: toggles.append(1)
        self.c.toggle_from_panel()
        self.assertEqual(toggles, [1])

    def _dialogs(self) -> list[tuple[str, str]]:
        shown: list[tuple[str, str]] = []
        swing = sys.modules["jmri.util.swing"]
        saved = swing.JmriJOptionPane
        swing.JmriJOptionPane = types.SimpleNamespace(
            WARNING_MESSAGE=2, showMessageDialog=lambda parent, msg, title, kind: shown.append((title, msg)))
        self.addCleanup(setattr, swing, "JmriJOptionPane", saved)
        return shown

    def test_stored_enabled_warns_with_the_sources(self) -> None:
        shown = self._dialogs()
        self.assertTrue(self.c._warn_if_stored_sml_enabled())
        self.assertEqual(len(shown), 1)
        title, msg = shown[0]
        self.assertEqual(title, "Digicon SML stored Enabled")
        self.assertIn("2 destination(s) on 1 source(s)", msg)
        self.assertIn("Mast 6LB", msg)

    def test_stored_disabled_shows_nothing(self) -> None:
        shown = self._dialogs()
        self.logic.setDisabled(self.logic.dests[0])
        self.logic.setDisabled(self.logic.dests[1])
        self.assertFalse(self.c._warn_if_stored_sml_enabled())
        self.assertEqual(shown, [])


if __name__ == "__main__":
    unittest.main()
