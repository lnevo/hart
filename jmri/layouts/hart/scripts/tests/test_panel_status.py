"""panel_status.py behaviour, run against an in-memory JMRI (jmri_fake).

What matters most on the Pi: the lamps never command a plant turnout and boot publishes nothing.
The yard-ladder lamps are gone (owner, 2026-11-17): nothing makes or paints IT:HART:YL:* turnouts. The MQTT adapter here only records; nothing reaches a broker.
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
PLANTS = ["M2T308", "M2T309", "M2T310", "M2T311", "M2T1213", "M2T1211", "M2T1210", "M2T1209", "M2T1208"]


class PanelStatus(unittest.TestCase):
    def setUp(self) -> None:
        self.layout = jf.Layout()
        for sn in PLANTS:
            self.plant(sn)
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

    def boot(self):
        jf.fire_timers()

    # --- boot ---------------------------------------------------------------------

    def test_boot_makes_no_yard_ladder_turnouts_and_commands_no_plant(self) -> None:
        for sn in PLANTS:
            self.fb(sn, T.CLOSED)
        self.boot()
        self.ps["sync_lamps"]()
        self.assertFalse([sn for sn in self.layout.turnouts.beans if sn.startswith("IT:HART:YL:")])
        for sn in PLANTS:
            self.assertEqual(self.layout.turnouts.getTurnout(sn).commanded, [], sn)

    def test_arms_once_the_plant_count_settles(self) -> None:
        # a connection that registers its turnouts after the first look still gets its listeners
        jf.fire_timers(limit=1)                              # first look: 9 plants, not yet settled
        self.assertFalse(self.ps["_armed"])
        self.plant("MTT120")                                 # a later connection's plant
        self.boot()
        self.assertTrue(self.ps["_armed"])
        self.assertEqual(self.ps["_plant_count"], len(PLANTS) + 1)

    def test_boot_publishes_nothing(self) -> None:
        for sn in PLANTS:
            self.fb(sn, T.THROWN)
        self.boot()
        self.assertEqual(self.layout.adapter.published, [])

    # --- Turnouts lamp (IH9990) -----------------------------------------------------

    def head(self):
        return self.layout.heads.getSignalHead("IH9990")

    def test_turnouts_lamp_colours(self) -> None:
        self.ps["sync_turnout_fb_lamp"]()
        self.assertEqual(self.head().appearance, jf.SignalHead.GREEN)
        for sn in PLANTS:
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
        self.assertEqual({self.layout.turnouts.getTurnout(sn).mode for sn in PLANTS}, {T.DIRECT})
        self.assertEqual(self.head().appearance, jf.SignalHead.RED)
        self.ps["toggle_turnout_fb_mode"]()
        jf.fire_timers()
        self.assertEqual({self.layout.turnouts.getTurnout(sn).mode for sn in PLANTS}, {T.TWOSENSOR})
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

    def test_lamp_click_finds_the_lamp_at_any_zoom(self) -> None:
        # the editor paints scaled but keeps the icon's unscaled bounds: a lamp at (2310, 568), 20 x 20 px,
        # is drawn at (1756, 432) when zoomed to fit at 0.76, and a click there must hit it
        class Icon:
            def __init__(self, x, y, visible=True):
                self.x, self.y, self.visible = x, y, visible

            def getX(self): return self.x
            def getY(self): return self.y
            def getWidth(self): return 20
            def getHeight(self): return 20
            def isVisible(self): return self.visible

        lamp_at = self.ps["_lamp_at"]
        lamps = [(Icon(2310, 540), "sml"), (Icon(2310, 568), "power")]
        self.assertEqual(lamp_at(lamps, 1.0, 2315, 575), "power")
        self.assertEqual(lamp_at(lamps, 0.76, 2310 * 0.76 + 4, 568 * 0.76 + 4), "power")
        self.assertEqual(lamp_at(lamps, 0.76, 2310 * 0.76 + 4, 540 * 0.76 + 4), "sml")
        self.assertIsNone(lamp_at(lamps, 0.76, 2315, 575))          # the unscaled spot is not the lamp at 0.76
        self.assertEqual(lamp_at(lamps, 2.0, 4630, 1146), "power")
        self.assertIsNone(lamp_at([(Icon(2310, 568, visible=False), "power")], 1.0, 2315, 575))

    def test_panel_click_runs_the_lamp_under_the_scaled_point(self) -> None:
        calls = []

        class Editor:
            def getPaintScale(self): return 0.5

        class Icon:
            def getX(self): return 100
            def getY(self): return 200
            def getWidth(self): return 20
            def getHeight(self): return 20
            def isVisible(self): return True

        class Event:
            def __init__(self, button, x, y): self.b, self.x, self.y = button, x, y
            def getButton(self): return self.b
            def getX(self): return self.x
            def getY(self): return self.y

        handler = self.ps["_PanelLampClick"](Editor())
        handler.lamps = [(Icon(), lambda: calls.append("power"))]
        handler.mouseClicked(Event(1, 55, 105))    # drawn at (50, 100) at half zoom
        handler.mouseClicked(Event(1, 105, 205))   # the unscaled spot: empty at half zoom
        handler.mouseClicked(Event(3, 55, 105))    # right click does nothing
        self.assertEqual(calls, ["power"])


if __name__ == "__main__":
    unittest.main()
