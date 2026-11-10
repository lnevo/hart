"""panel_status.py behaviour, run against an in-memory JMRI (jmri_fake).

What matters most on the Pi: painting the yard-ladder lamps must never command a plant
turnout, lamps follow feedback sensors only (never JMRI's default CLOSED), and boot
publishes nothing. The MQTT adapter here only records; nothing reaches a broker.
"""
from __future__ import annotations

import contextlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jmri_fake as jf  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "panel_status.py"
T, S = jf.Turnout, jf.Sensor
WATCH = ["M2T308", "M2T309", "M2T310", "M2T311", "M2T1213", "M2T1211", "M2T1210", "M2T1209", "M2T1208"]


class PanelStatus(unittest.TestCase):
    def setUp(self) -> None:
        self.layout = jf.Layout()
        for sn in WATCH:
            self.plant(sn)
        self.west = self.layout.routes.add(jf.FakeRoute("IR:1", "Yard ladder west"))
        self.east = self.layout.routes.add(jf.FakeRoute("IR:2", "Yard ladder east"))
        self.ps = jf.load_script(SCRIPT, self.layout)
        stack = contextlib.ExitStack()
        stack.enter_context(jf.running(self.layout))
        self.addCleanup(stack.close)

    def plant(self, sn, mode=T.TWOSENSOR):
        s1 = self.layout.sensors.add(jf.FakeSensor(sn + ":R"))
        s2 = self.layout.sensors.add(jf.FakeSensor(sn + ":N"))
        return self.layout.turnouts.add(jf.FakeTurnout(sn, s1, s2, mode=mode))

    def fb(self, sn, state):
        """Set a plant's feedback sensors: THROWN lights sensor 1 (R), CLOSED sensor 2 (N)."""
        to = self.layout.turnouts.getTurnout(sn)
        to.first.state = S.ACTIVE if state == T.THROWN else S.INACTIVE
        to.second.state = S.ACTIVE if state == T.CLOSED else S.INACTIVE

    def lit(self):
        return sorted(sn for sn, to in self.layout.turnouts.beans.items()
                      if sn.startswith("IT:HART:YL:") and to.known == T.THROWN)

    def boot(self):
        jf.fire_timers()

    # --- ladder lamps ---------------------------------------------------------------

    def test_lamps_follow_feedback(self) -> None:
        for sn, st in (("M2T308", T.THROWN), ("M2T309", T.CLOSED), ("M2T310", T.CLOSED), ("M2T311", T.THROWN),
                       ("M2T1211", T.CLOSED), ("M2T1213", T.CLOSED)):
            self.fb(sn, st)
        self.boot()
        self.assertEqual(self.lit(), ["IT:HART:YL:L4", "IT:HART:YL:R1"])

    def test_first_matching_peel_wins(self) -> None:
        # L5's pattern is a subset of L4's; L4 is listed first and must win.
        for sn, st in (("M2T308", T.THROWN), ("M2T309", T.CLOSED), ("M2T310", T.CLOSED), ("M2T311", T.THROWN)):
            self.fb(sn, st)
        self.boot()
        self.assertIn("IT:HART:YL:L4", self.lit())
        self.assertNotIn("IT:HART:YL:L5", self.lit())

    def test_unknown_feedback_lights_nothing(self) -> None:
        # JMRI's KnownState default is CLOSED; reading it would light S-R (L1 / R1).
        for sn in WATCH:
            self.layout.turnouts.getTurnout(sn).known = T.CLOSED
        self.boot()
        self.assertEqual(self.lit(), [])

    def test_both_feedback_sensors_active_is_unknown(self) -> None:
        self.fb("M2T308", T.CLOSED)
        self.layout.turnouts.getTurnout("M2T308").first.state = S.ACTIVE
        self.boot()
        self.assertNotIn("IT:HART:YL:L1", self.lit())

    def test_painting_never_commands_a_plant(self) -> None:
        for sn in WATCH:
            self.fb(sn, T.CLOSED)
        self.boot()
        self.ps["sync_ladder_buttons"]()
        for sn in WATCH:
            self.assertEqual(self.layout.turnouts.getTurnout(sn).commanded, [], sn)
        # Ladder routes are switched off around each paint and always switched back on.
        self.assertTrue(self.west.enabled and self.east.enabled)
        self.assertEqual(self.west.history[:2], [False, True])

    def test_no_ladder_routes_skips_painting(self) -> None:
        self.layout.routes.beans.clear()
        self.fb("M2T308", T.CLOSED)
        self.boot()
        self.assertEqual(self.lit(), [])

    def test_routes_reenabled_even_if_painting_fails(self) -> None:
        def broken(sn, state):
            raise RuntimeError("paint failed")

        self.ps["_set_indicator_known"] = broken
        self.boot()
        self.assertTrue(self.west.enabled and self.east.enabled)

    def test_boot_publishes_nothing(self) -> None:
        for sn in WATCH:
            self.fb(sn, T.THROWN)
        self.boot()
        self.assertEqual(self.layout.adapter.published, [])

    # --- Turnouts lamp (IH9990) -----------------------------------------------------

    def head(self):
        return self.layout.heads.getSignalHead("IH9990")

    def test_turnouts_lamp_colours(self) -> None:
        self.ps["sync_turnout_fb_lamp"]()
        self.assertEqual(self.head().appearance, jf.SignalHead.GREEN)
        for sn in WATCH:
            self.layout.turnouts.getTurnout(sn).mode = T.DIRECT
        self.ps["sync_turnout_fb_lamp"]()
        self.assertEqual(self.head().appearance, jf.SignalHead.RED)
        self.layout.turnouts.getTurnout("M2T308").mode = T.TWOSENSOR
        self.ps["sync_turnout_fb_lamp"]()
        self.assertEqual(self.head().appearance, jf.SignalHead.YELLOW)

    def test_turnouts_lamp_ignores_turnouts_without_two_sensors(self) -> None:
        self.layout.turnouts.add(jf.FakeTurnout("M2T999", mode=T.DIRECT))  # no feedback sensors
        self.layout.turnouts.add(jf.FakeTurnout("IT:OTHER", mode=T.DIRECT))
        self.ps["sync_turnout_fb_lamp"]()
        self.assertEqual(self.head().appearance, jf.SignalHead.GREEN)

    def test_turnouts_lamp_click_flips_feedback_mode(self) -> None:
        jf.Timer.pending.clear()
        self.ps["toggle_turnout_fb_mode"]()
        self.assertEqual(self.head().appearance, jf.SignalHead.YELLOW)  # amber while pending
        jf.fire_timers()
        self.assertEqual({self.layout.turnouts.getTurnout(sn).mode for sn in WATCH}, {T.DIRECT})
        self.assertEqual(self.head().appearance, jf.SignalHead.RED)
        self.ps["toggle_turnout_fb_mode"]()
        jf.fire_timers()
        self.assertEqual({self.layout.turnouts.getTurnout(sn).mode for sn in WATCH}, {T.TWOSENSOR})
        self.assertEqual(self.layout.adapter.published, [])

    # --- LCOS, Signals and Track Power lamps ----------------------------------------

    def test_lcos_click_sends_resubscribe_not_force(self) -> None:
        lcos = self.layout.sensors.add(jf.FakeSensor("M2S1567", S.ACTIVE))
        jf.Timer.pending.clear()
        self.ps["publish_lcos_resubscribe"]()
        self.assertEqual(lcos.state, S.INCONSISTENT)  # amber
        jf.fire_timers()
        self.assertEqual(self.layout.adapter.published, [("track/bridge/cmd", "RESUBSCRIBE", False)])
        self.assertEqual(lcos.state, S.ACTIVE)  # bridge did not answer: restore the old state

    def test_lcos_lamp_keeps_a_fresh_bridge_state(self) -> None:
        lcos = self.layout.sensors.add(jf.FakeSensor("M2S1567", S.ACTIVE))
        jf.Timer.pending.clear()
        self.ps["publish_lcos_resubscribe"]()
        jf.fire_timers(limit=1)  # the publish
        lcos.state = S.INACTIVE  # bridge reported in the meantime
        jf.fire_timers()
        self.assertEqual(lcos.state, S.INACTIVE)

    def test_lcos_click_without_mqtt_publishes_nothing(self) -> None:
        self.layout.memo = None
        self.layout.sensors.add(jf.FakeSensor("M2S1567", S.ACTIVE))
        self.ps["publish_lcos_resubscribe"]()
        jf.fire_timers()
        self.assertEqual(self.layout.adapter.published, [])

    def test_signals_click_without_coordinator_clears_amber(self) -> None:
        import __main__

        with contextlib.suppress(AttributeError):
            delattr(__main__, "digicon_sml_controller")
        jf.Timer.pending.clear()
        self.ps["toggle_sml_mode"]()
        jf.fire_timers()
        self.assertEqual(self.layout.sensors.getSensor("IS:SML_MODE").state, S.INACTIVE)

    def test_signals_click_calls_the_coordinator(self) -> None:
        import __main__

        calls = []

        class Coordinator:
            _busy = False

            def toggle_from_panel(self):
                calls.append("toggle")

            def _sync_sml_mode_sensor(self):
                calls.append("sync")

        __main__.digicon_sml_controller = Coordinator()
        self.addCleanup(delattr, __main__, "digicon_sml_controller")
        jf.Timer.pending.clear()
        self.ps["toggle_sml_mode"]()
        jf.fire_timers()
        self.assertEqual(calls, ["toggle", "sync"])

    def test_track_power_click_toggles_and_mirrors(self) -> None:
        jf.Timer.pending.clear()
        self.ps["toggle_track_power"]()
        jf.fire_timers()
        self.assertEqual(self.layout.power.power, jf.PowerManager.ON)
        self.assertEqual(self.layout.sensors.getSensor("IS:TRACK_POWER").state, S.ACTIVE)
        self.ps["toggle_track_power"]()
        jf.fire_timers()
        self.assertEqual(self.layout.power.power, jf.PowerManager.OFF)
        self.assertEqual(self.layout.sensors.getSensor("IS:TRACK_POWER").state, S.INACTIVE)

    def test_only_left_clicks_act(self) -> None:
        calls = []
        click = self.ps["_LampClick"](lambda: calls.append(1))

        class Event:
            def __init__(self, button):
                self.button = button

            def getButton(self):
                return self.button

        click.mouseClicked(Event(3))
        click.mouseClicked(Event(1))
        self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main()
