"""panel_status.py behaviour, run against an in-memory JMRI (jmri_fake).

What matters most on the Pi: the lamps never command a plant turnout and boot publishes nothing.
The yard-ladder lamps are gone (owner, 2026-11-17): nothing makes or paints IT:HART:YL:* turnouts. The MQTT adapter here only records; nothing reaches a broker.
"""
from __future__ import annotations

import contextlib
import sys
import types
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

    def test_resubscribe_is_not_retained(self) -> None:
        # A retained RESUBSCRIBE would replay to the bridge on every reconnect. JMRI's
        # two-argument publish retains, so the flag must be passed as False.
        self.assertTrue(self.ps["_mqtt_publish"]("track/bridge/cmd", "RESUBSCRIBE"))
        self.assertEqual([m[2] for m in self.layout.adapter.published], [False])

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

    def test_lamp_click_finds_the_lamp_at_any_zoom(self) -> None:
        # the editor paints scaled but keeps the icon's unscaled bounds: a lamp at (2310, 568), 20 x 20 px,
        # is drawn at (1756, 432) when zoomed to fit at 0.76, and a click there must hit it
        class Icon:
            def __init__(self, x, y, visible=True, level=10):
                self.x, self.y, self.visible, self.level = x, y, visible, level

            def getX(self): return self.x
            def getY(self): return self.y
            def getWidth(self): return 20
            def getHeight(self): return 20
            def isVisible(self): return self.visible
            def getDisplayLevel(self): return self.level

        lamp_at = self.ps["_lamp_at"]
        lamps = [(Icon(2310, 540), "sml"), (Icon(2310, 568), "power")]
        self.assertEqual(lamp_at(lamps, 1.0, 2315, 575), "power")
        self.assertEqual(lamp_at(lamps, 0.76, 2310 * 0.76 + 4, 568 * 0.76 + 4), "power")
        self.assertEqual(lamp_at(lamps, 0.76, 2310 * 0.76 + 4, 540 * 0.76 + 4), "sml")
        self.assertIsNone(lamp_at(lamps, 0.76, 2315, 575))          # the unscaled spot is not the lamp at 0.76
        self.assertEqual(lamp_at(lamps, 2.0, 4630, 1146), "power")
        # like the editor: a hidden icon still counts, and the topmost of overlapping lamps wins
        self.assertEqual(lamp_at([(Icon(2310, 568, visible=False), "power")], 1.0, 2315, 575), "power")
        self.assertEqual(lamp_at([(Icon(2310, 568, level=4), "under"), (Icon(2310, 568, level=10), "top")],
                                 1.0, 2315, 575), "top")

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
            def getDisplayLevel(self): return 10

        class Event:
            def __init__(self, button, x, y, mod=None): self.b, self.x, self.y, self.mod = button, x, y, mod
            def getButton(self): return self.b
            def isPopupTrigger(self): return self.mod == "popup"
            def isMetaDown(self): return self.mod == "meta"
            def isAltDown(self): return self.mod == "alt"
            def isShiftDown(self): return self.mod == "shift"
            def isControlDown(self): return self.mod == "ctrl"
            def getX(self): return self.x
            def getY(self): return self.y

        handler = self.ps["_PanelLampClick"](Editor())
        handler.lamps = [(Icon(), lambda: calls.append("power"))]
        handler.mouseClicked(Event(1, 55, 105))    # drawn at (50, 100) at half zoom
        handler.mouseClicked(Event(1, 105, 205))   # the unscaled spot: empty at half zoom
        handler.mouseClicked(Event(3, 55, 105))    # right click does nothing
        for mod in ("popup", "meta", "alt", "shift", "ctrl"):
            handler.mouseClicked(Event(1, 55, 105, mod))   # nor a modified or popup click
        self.assertEqual(calls, ["power"])


    # --- a second run of the script (JMRI Scripting > Run Script again) -------------

    def panel(self):
        """One editor holding the four status lamps, as the HART panel does."""
        display = sys.modules["jmri.jmrit.display"]

        class Target:
            def __init__(self):
                self.mouse = []

            def addMouseListener(self, listener): self.mouse.append(listener)
            def removeMouseListener(self, listener): self.mouse = [m for m in self.mouse if m is not listener]
            def getMouseListeners(self): return list(self.mouse)

        def icon(kind, bean, x, y):
            class Icon(kind):
                def getSensor(self): return bean
                def getSignalHead(self): return bean
                def setControlling(self, value): pass
                def getX(self): return x
                def getY(self): return y
                def getWidth(self): return 20
                def getHeight(self): return 20
                def getDisplayLevel(self): return 10
            return Icon()

        head = self.ps["_ensure_turnout_fb_head"]()
        sensors = self.layout.sensors
        target = Target()
        contents = [
            icon(display.SensorIcon, sensors.provideSensor("M2S1567"), 0, 0),
            icon(display.SensorIcon, sensors.provideSensor("IS:SML_MODE"), 40, 0),
            icon(display.SensorIcon, sensors.provideSensor("IS:TRACK_POWER"), 80, 0),
            icon(display.SignalHeadIcon, head, 120, 0),
        ]
        editor = types.SimpleNamespace(getContents=lambda: contents, getTargetPanel=lambda: target,
                                       getPaintScale=lambda: 1.0, getTitle=lambda: "Other")
        self.layout.editors.append(editor)
        return target

    def click(self, handler, x, y):
        event = types.SimpleNamespace(getButton=lambda: 1, isPopupTrigger=lambda: False, isMetaDown=lambda: False,
                                      isAltDown=lambda: False, isShiftDown=lambda: False,
                                      isControlDown=lambda: False, getX=lambda: x, getY=lambda: y)
        handler.mouseClicked(event)

    def ours(self, listeners):
        return [l for l in listeners if getattr(l, "hart_panel_status", False)]

    def test_a_second_run_replaces_the_first_runs_listeners(self) -> None:
        target = self.panel()
        self.boot()
        self.assertEqual(len(target.mouse), 1)
        jf.load_script(SCRIPT, self.layout)                  # the script run again in the same JMRI
        self.boot()
        for sn in PLANTS:
            self.assertEqual(len(self.ours(self.layout.turnouts.getTurnout(sn).listeners)), 1, sn)
        self.assertEqual(len(self.ours(self.layout.power.listeners)), 1)
        self.assertEqual(len(target.mouse), 1)

    def test_one_click_toggles_once_after_a_second_run(self) -> None:
        target = self.panel()
        self.boot()
        jf.load_script(SCRIPT, self.layout)
        self.boot()
        for handler in target.mouse:
            self.click(handler, 85, 5)                       # the Track Power lamp
        jf.fire_timers()
        self.assertEqual(self.layout.power.power, jf.PowerManager.ON)

    def test_detaching_leaves_other_listeners_alone(self) -> None:
        target = self.panel()
        other = object()
        to = self.layout.turnouts.getTurnout("M2T308")
        to.addPropertyChangeListener(other)
        target.addMouseListener(other)
        self.boot()
        jf.load_script(SCRIPT, self.layout)
        self.boot()
        self.assertIn(other, to.listeners)
        self.assertIn(other, target.mouse)

    def test_a_run_started_again_before_it_armed_arms_only_once(self) -> None:
        target = self.panel()
        first_timers = list(jf.Timer.pending)               # the first run has not armed yet
        second = jf.load_script(SCRIPT, self.layout)
        jf.Timer.pending[:0] = first_timers                  # its timers still fire, before the second run's
        self.boot()
        self.assertFalse(self.ps["_armed"])                  # the first run stood down
        self.assertTrue(second["_armed"])
        for sn in PLANTS:
            self.assertEqual(len(self.ours(self.layout.turnouts.getTurnout(sn).listeners)), 1, sn)
        self.assertEqual(len(target.mouse), 1)

    def test_a_listener_from_before_the_mark_is_replaced_too(self) -> None:
        # the first re-run after this change was deployed: the old run's listeners carry no mark yet
        class _PowerListener:
            def propertyChange(self, event): pass

        self.layout.power.addPropertyChangeListener(_PowerListener())
        self.boot()
        self.assertEqual(len(self.layout.power.listeners), 1)
        self.assertTrue(getattr(self.layout.power.listeners[0], "hart_panel_status", False))

    # --- a turnout change updates only that turnout ---------------------------------

    def turnout_event(self, sn, name):
        to = self.layout.turnouts.getTurnout(sn)
        for listener in self.ours(to.listeners):
            listener.propertyChange(jf._ValueEvent(name, None, None, to))
        jf.fire_timers()

    def count_scans(self):
        scans = []
        real = self.layout.turnouts.getNamedBeanSet

        def counted():
            scans.append(1)
            return real()

        self.layout.turnouts.getNamedBeanSet = counted
        return scans

    def test_a_turnout_event_does_not_rescan_every_turnout(self) -> None:
        self.boot()
        self.assertEqual(self.head().appearance, jf.SignalHead.GREEN)
        scans = self.count_scans()
        self.turnout_event("M2T308", "KnownState")
        self.assertEqual(self.head().appearance, jf.SignalHead.GREEN)
        self.layout.turnouts.getTurnout("M2T309").mode = T.DIRECT
        self.turnout_event("M2T309", "FeedbackMode")
        self.assertEqual(self.head().appearance, jf.SignalHead.YELLOW)
        self.assertEqual(scans, [])

    def test_a_turnout_event_still_follows_mode_and_sensor_changes(self) -> None:
        self.boot()
        for sn in PLANTS[1:]:
            self.layout.turnouts.getTurnout(sn).mode = T.DIRECT
            self.turnout_event(sn, "FeedbackMode")
        self.assertEqual(self.head().appearance, jf.SignalHead.YELLOW)   # M2T308 still TWOSENSOR
        self.layout.turnouts.getTurnout("M2T308").first = None          # it loses a feedback sensor
        self.turnout_event("M2T308", "Sensor1")
        self.assertEqual(self.head().appearance, jf.SignalHead.RED)      # the rest are all DIRECT
        self.layout.turnouts.getTurnout("M2T308").first = jf.FakeSensor("M2T308:R")
        self.turnout_event("M2T308", "Sensor1")
        self.assertEqual(self.head().appearance, jf.SignalHead.YELLOW)

    def test_a_plant_that_gains_its_second_sensor_joins_the_lamp(self) -> None:
        late = self.layout.turnouts.add(jf.FakeTurnout("M2T1207", jf.FakeSensor("M2T1207:R"), mode=T.DIRECT))
        self.boot()
        self.assertEqual(self.head().appearance, jf.SignalHead.GREEN)   # one sensor: not counted yet
        late.second = jf.FakeSensor("M2T1207:N")
        self.turnout_event("M2T1207", "Sensor2")
        self.assertEqual(self.head().appearance, jf.SignalHead.YELLOW)  # now mixed

if __name__ == "__main__":
    unittest.main()
