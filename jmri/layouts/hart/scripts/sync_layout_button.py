# Sync Digicon yard-ladder button indicators (IT:HART:YL:*) from live FB
# sensors, drive HART Railroad status lamps, and wire clicks on LCOS /
# Turnouts / Signals / Track Power panel icons.
#
# CRITICAL: IT:HART:YL:* are Route controlTurnouts (fire on THROWN) whose
# outputs are MQTT plants (M2T308… / M2T1208…). newKnownState(THROWN) still
# notifies the Route, which setCommandedState → track/cmd/turnout. Always
# disable the ladder routes while painting lamps. Never setCommandedState
# on M2T*/MTT*.
#
# Match peels from FB N/R only. JMRI KnownState defaults CLOSED, which would
# light S-R and command that canned alignment — not last field state.
#
# Boot: fill UNKNOWN MQTT sensors from broker retain (setOwnState).
#
# Turnouts lamp (Green / Yellow / Red): among M2T* and MTT* that have both FB
# sensors assigned — all TWOSENSOR → Green; all DIRECT → Red; mixed → Yellow.
# Click: toggle those plants between TWOSENSOR and DIRECT.
#
# Signals lamp (IS:SML_MODE): click → DigiconMqttSml.toggle_from_panel().
# LCOS lamp (M2S1567): click → MQTT track/bridge/cmd RESUBSCRIBE (not FORCE).
# Track Power lamp (IS:TRACK_POWER): mirrors LCC PowerManager; click toggles ON/OFF.
#
# Ladder/lamp arm as soon as watch turnouts exist. Panel click wiring retries
# quietly afterward (do not block on Layout Editor — EditorManager often lags).

import jmri
from java.awt.event import ActionListener, MouseAdapter, MouseEvent
from java.beans import PropertyChangeListener
from java.lang import Runnable
from javax.swing import SwingUtilities, Timer

CLOSED = jmri.Turnout.CLOSED
THROWN = jmri.Turnout.THROWN
TWOSENSOR = jmri.Turnout.TWOSENSOR
DIRECT = jmri.Turnout.DIRECT
ACTIVE = jmri.Sensor.ACTIVE

TURNOUT_FB_HEAD = "IH9990"
LCOS_SENSOR = "M2S1567"
SML_MODE_SENSOR = "IS:SML_MODE"
TRACK_POWER_SENSOR = "IS:TRACK_POWER"
BRIDGE_CMD_TOPIC = "track/bridge/cmd"
RESUBSCRIBE_PAYLOAD = "RESUBSCRIBE"

GREEN = jmri.SignalHead.GREEN
YELLOW = jmri.SignalHead.YELLOW
RED = jmri.SignalHead.RED

# First match wins — specific peels before S-5 / S-1.
LEFT_PATTERNS = [
    ("IT:HART:YL:L4", (("M2T308", THROWN), ("M2T309", CLOSED), ("M2T310", CLOSED), ("M2T311", THROWN))),
    ("IT:HART:YL:L3", (("M2T308", THROWN), ("M2T309", CLOSED), ("M2T310", THROWN), ("M2T311", CLOSED))),
    ("IT:HART:YL:L2", (("M2T308", THROWN), ("M2T309", THROWN), ("M2T310", CLOSED), ("M2T311", CLOSED))),
    ("IT:HART:YL:L5", (("M2T308", THROWN), ("M2T309", CLOSED), ("M2T310", CLOSED), ("M2T311", CLOSED))),
    ("IT:HART:YL:L1", (("M2T308", CLOSED),)),
]
RIGHT_PATTERNS = [
    ("IT:HART:YL:R4", (("M2T1211", THROWN), ("M2T1210", CLOSED), ("M2T1209", CLOSED), ("M2T1208", THROWN))),
    ("IT:HART:YL:R3", (("M2T1211", THROWN), ("M2T1210", CLOSED), ("M2T1209", THROWN), ("M2T1208", CLOSED))),
    ("IT:HART:YL:R2", (("M2T1211", THROWN), ("M2T1210", THROWN), ("M2T1209", CLOSED), ("M2T1208", CLOSED))),
    ("IT:HART:YL:R5", (("M2T1211", THROWN), ("M2T1210", CLOSED), ("M2T1209", CLOSED), ("M2T1208", CLOSED))),
    # Track S-R east: Switch 31 (110) and Switch 33 (112) both CLOSED.
    ("IT:HART:YL:R1", (("M2T1211", CLOSED), ("M2T1213", CLOSED))),
]

LEFT_INDICATORS = [p[0] for p in LEFT_PATTERNS]
RIGHT_INDICATORS = [p[0] for p in RIGHT_PATTERNS]
WATCH = [
    "M2T308", "M2T309", "M2T310", "M2T311",
    "M2T1213", "M2T1211", "M2T1210", "M2T1209", "M2T1208",
]

# Ladder/lamp: short settle, then arm when watch turnouts exist (no LE gate).
_ARM_FIRST_MS = 1000
_ARM_RETRY_MS = 1000
_ARM_MAX_ATTEMPTS = 15
# Clicks: quiet background retries after panel contents appear.
_CLICK_RETRY_MS = 2000
_CLICK_MAX_ATTEMPTS = 30

_busy = False
_armed = False
_clicks_armed = False
_icon_rebound = False
_last = (None, None)
_last_fb_appearance = None
_listener = None
_sensor_listener = None
_click_busy = False
_plant_count = 0


def _known_from_fb(to):
    """TWOSENSOR: sensor1 = thrown (R), sensor2 = closed (N). Read-only."""
    try:
        s1 = to.getFirstSensor()
        s2 = to.getSecondSensor()
    except Exception:
        return None
    if s1 is None or s2 is None:
        return None
    try:
        a1 = s1.getKnownState()
        a2 = s2.getKnownState()
    except Exception:
        return None
    if a1 == ACTIVE and a2 != ACTIVE:
        return THROWN
    if a2 == ACTIVE and a1 != ACTIVE:
        return CLOSED
    return None


def _known(to):
    """Plant position for YL match. FB sensors only — never commanded or default CLOSED."""
    if to is None:
        return None
    return _known_from_fb(to)


def _match(patterns):
    for ind, need in patterns:
        ok = True
        for sn, want in need:
            got = _known(turnouts.getTurnout(sn))
            if got != want:
                ok = False
                break
        if ok:
            return ind
    return None


def _set_indicator_known(sn, state):
    """Paint YL lamp KnownState. Caller must disable ladder routes first."""
    to = turnouts.getTurnout(sn)
    if to is None:
        try:
            to = turnouts.provideTurnout(sn)
        except Exception:
            return
    try:
        if to.getKnownState() == state:
            return
        if hasattr(to, "newKnownState"):
            to.newKnownState(state)
        else:
            print(
                "sync_layout_button: cannot light %s (no newKnownState)"
                % sn
            )
    except Exception as e:
        print("sync_layout_button: indicator %s → %s failed: %s" % (sn, state, e))


def _ladder_routes():
    out = []
    try:
        for route in routes.getNamedBeanSet():
            un = route.getUserName() or ""
            if "ladder" in un.lower():
                out.append(route)
    except Exception as e:
        print("sync_layout_button: list ladder routes failed: %s" % e)
    return out


def _paint_side_indicators(indicators, active):
    """Lit = THROWN on the matching peel; all others CLOSED."""
    for sn in indicators:
        _set_indicator_known(sn, THROWN if sn == active else CLOSED)


def _paint_indicators_without_commanding(left, right):
    """Light YL lamps with ladder routes disabled so M2T outputs are not commanded."""
    found = _ladder_routes()
    if not found:
        print("sync_layout_button: skip YL paint (ladder routes not loaded)")
        return
    disabled = []
    try:
        for route in found:
            try:
                if route.getEnabled():
                    route.setEnabled(False)
                    disabled.append(route)
            except Exception as e:
                print(
                    "sync_layout_button: disable %s failed: %s"
                    % (route.getUserName(), e)
                )
        _paint_side_indicators(LEFT_INDICATORS, left)
        _paint_side_indicators(RIGHT_INDICATORS, right)
    finally:
        for route in disabled:
            try:
                route.setEnabled(True)
            except Exception as e:
                print(
                    "sync_layout_button: re-enable %s failed: %s"
                    % (route.getUserName(), e)
                )


def _has_two_fb_sensors(to):
    try:
        return to.getFirstSensor() is not None and to.getSecondSensor() is not None
    except Exception:
        return False


def _included_plant_turnouts():
    """M2T/MTT (MQTT/LCC plant) turnouts with both feedback sensors assigned."""
    out = []
    try:
        for to in turnouts.getNamedBeanSet():
            sn = to.getSystemName()
            if not (sn.startswith("M2T") or sn.startswith("MTT")):
                continue
            if _has_two_fb_sensors(to):
                out.append(to)
    except Exception as e:
        print("sync_layout_button: scan turnouts failed: %s" % e)
    return out


def _watch_turnouts_present():
    """True when the MQTT ladder watch turnouts exist in the manager."""
    try:
        for sn in WATCH:
            if turnouts.getTurnout(sn) is None:
                return False
        return True
    except Exception:
        return False


def _ensure_turnout_fb_head():
    """Return IH9990, creating a VirtualSignalHead if tables omitted it."""
    try:
        mgr = jmri.InstanceManager.getDefault(jmri.SignalHeadManager)
        head = mgr.getSignalHead(TURNOUT_FB_HEAD)
        if head is None:
            try:
                head = mgr.getBySystemName(TURNOUT_FB_HEAD)
            except Exception:
                head = None
        if head is not None:
            return head
        from jmri.implementation import VirtualSignalHead

        head = VirtualSignalHead(TURNOUT_FB_HEAD)
        mgr.register(head)
        print("sync_layout_button: created VirtualSignalHead %s" % TURNOUT_FB_HEAD)
        return head
    except Exception as e:
        print("sync_layout_button: Turnouts lamp head unavailable: %s" % e)
        return None


def _set_head_appearance(head, appearance):
    """Apply appearance on the EDT; clear held so icon is not '?'."""

    class _Set(Runnable):
        def run(self):
            try:
                try:
                    head.setHeld(False)
                except Exception:
                    pass
                try:
                    head.setLit(True)
                except Exception:
                    pass
                head.setAppearance(appearance)
            except Exception as e:
                print("sync_layout_button: setAppearance failed: %s" % e)

    try:
        if SwingUtilities.isEventDispatchThread():
            _Set().run()
        else:
            SwingUtilities.invokeLater(_Set())
    except Exception:
        _Set().run()


def _rebind_turnout_fb_icons(head):
    """Once: if the LE icon loaded before the bean existed, re-point it."""
    global _icon_rebound
    if head is None or _icon_rebound:
        return
    try:
        from jmri.jmrit.display import EditorManager, SignalHeadIcon
    except Exception:
        return
    em = jmri.InstanceManager.getDefault(EditorManager)
    if em is None:
        return
    rebound = False
    for ed in list(em.getAll()):
        try:
            contents = list(ed.getContents())
        except Exception:
            continue
        for icon in contents:
            try:
                if not isinstance(icon, SignalHeadIcon):
                    continue
                hn = _head_sys(icon)
                if hn == TURNOUT_FB_HEAD:
                    rebound = True
                    continue
                try:
                    if abs(int(icon.getX()) - 24) > 8 or abs(int(icon.getY()) - 588) > 8:
                        continue
                except Exception:
                    continue
                try:
                    icon.setSignalHead(TURNOUT_FB_HEAD)
                    rebound = True
                    print(
                        "sync_layout_button: rebound Turnouts icon -> %s"
                        % TURNOUT_FB_HEAD
                    )
                except Exception:
                    try:
                        icon.setSignalHead(head)
                        rebound = True
                    except Exception:
                        pass
            except Exception:
                pass
    if rebound:
        _icon_rebound = True


def sync_turnout_fb_lamp():
    """Set IH9990 Green/Yellow/Red from included plant feedback modes."""
    global _last_fb_appearance
    head = _ensure_turnout_fb_head()
    if head is None:
        return
    _rebind_turnout_fb_icons(head)

    included = _included_plant_turnouts()
    if not included:
        appearance = YELLOW
        label = "yellow(empty)"
    else:
        modes = set()
        for to in included:
            try:
                modes.add(to.getFeedbackMode())
            except Exception:
                modes.add(None)
        if modes == {TWOSENSOR}:
            appearance = GREEN
            label = "green(all TWOSENSOR, n=%d)" % len(included)
        elif modes == {DIRECT}:
            appearance = RED
            label = "red(all DIRECT, n=%d)" % len(included)
        else:
            appearance = YELLOW
            label = "yellow(mixed %s, n=%d)" % (
                sorted(str(m) for m in modes),
                len(included),
            )

    try:
        _set_head_appearance(head, appearance)
        if appearance != _last_fb_appearance:
            _last_fb_appearance = appearance
            print("sync_layout_button: Turnouts lamp %s" % label)
    except Exception as e:
        print("sync_layout_button: Turnouts lamp set failed: %s" % e)


def _show_amber_head():
    """Pending click feedback on Turnouts lamp (yellow)."""
    global _last_fb_appearance
    head = _ensure_turnout_fb_head()
    if head is None:
        return
    _set_head_appearance(head, YELLOW)
    _last_fb_appearance = YELLOW


def _show_amber_sensor(sys_name):
    """Pending click feedback on LCOS/Signals (INCONSISTENT → yellow icon)."""
    try:
        s = sensors.getSensor(sys_name)
        if s is None:
            s = sensors.provideSensor(sys_name)
        s.setKnownState(jmri.Sensor.INCONSISTENT)
    except Exception as e:
        print("sync_layout_button: amber %s failed: %s" % (sys_name, e))


def _after_paint(fn, delay_ms=80):
    """Run fn after delay so amber can paint first (EDT redraw)."""

    class _Go(ActionListener):
        def actionPerformed(self, event):
            event.getSource().stop()
            try:
                fn()
            except Exception as e:
                print("sync_layout_button: deferred action failed: %s" % e)

    t = Timer(delay_ms, _Go())
    t.setRepeats(False)
    t.start()


def _toggle_turnout_fb_mode_body():
    included = _included_plant_turnouts()
    if not included:
        print("sync_layout_button: no 2-sensor M2T/MTT plants to toggle")
        sync_turnout_fb_lamp()
        return
    modes = set()
    for to in included:
        try:
            modes.add(to.getFeedbackMode())
        except Exception:
            pass
    if modes == {TWOSENSOR}:
        target = DIRECT
        label = "DIRECT"
    else:
        target = TWOSENSOR
        label = "TWOSENSOR"
    n = 0
    for to in included:
        try:
            to.setFeedbackMode(target)
            if target == TWOSENSOR:
                try:
                    to.setInitialKnownStateFromFeedback()
                except Exception:
                    pass
            n += 1
        except Exception as e:
            print(
                "sync_layout_button: setFeedbackMode %s failed: %s"
                % (to.getSystemName(), e)
            )
    print(
        "sync_layout_button: Turnouts lamp click → %s on %d plant(s)"
        % (label, n)
    )
    sync_turnout_fb_lamp()


# Hold amber long enough to feel like a click landed (FB flip itself is near-instant).
_LAMP_AMBER_MS = 500


def toggle_turnout_fb_mode():
    """Click Turnouts lamp: amber hold, then flip TWOSENSOR ↔ DIRECT, then final."""
    _show_amber_head()
    _after_paint(_toggle_turnout_fb_mode_body, delay_ms=_LAMP_AMBER_MS)


def _mqtt_publish(topic, payload):
    try:
        memo = jmri.InstanceManager.getDefault(
            jmri.jmrix.mqtt.MqttSystemConnectionMemo
        )
        if memo is None:
            print("sync_layout_button: no MQTT connection")
            return False
        adapter = memo.getMqttAdapter()
        if adapter is None:
            print("sync_layout_button: no MQTT adapter")
            return False
        adapter.publish(topic, payload)
        return True
    except Exception as e:
        print("sync_layout_button: MQTT publish failed: %s" % e)
        return False


def _restore_lcos_lamp(prev_state):
    """After RESUBSCRIBE: keep MQTT update if it arrived; else restore prior."""

    class _Restore(ActionListener):
        def actionPerformed(self, event):
            event.getSource().stop()
            try:
                s = sensors.getSensor(LCOS_SENSOR)
                if s is None:
                    return
                if s.getKnownState() != jmri.Sensor.INCONSISTENT:
                    return  # bridge/MQTT already painted final
                if prev_state in (jmri.Sensor.ACTIVE, jmri.Sensor.INACTIVE):
                    s.setKnownState(prev_state)
                else:
                    s.setKnownState(jmri.Sensor.INACTIVE)
            except Exception as e:
                print("sync_layout_button: LCOS restore failed: %s" % e)

    # RESUBSCRIBE is fire-and-forget; give the bridge a moment to refresh HBLOOP.
    t = Timer(2000, _Restore())
    t.setRepeats(False)
    t.start()


def publish_lcos_resubscribe():
    """Click LCOS lamp: amber → RESUBSCRIBE (not FORCE) → restore/final."""
    prev = jmri.Sensor.UNKNOWN
    try:
        s = sensors.getSensor(LCOS_SENSOR)
        if s is not None:
            prev = s.getKnownState()
    except Exception:
        pass
    _show_amber_sensor(LCOS_SENSOR)

    def _do():
        if _mqtt_publish(BRIDGE_CMD_TOPIC, RESUBSCRIBE_PAYLOAD):
            print(
                "sync_layout_button: LCOS lamp → %s %s"
                % (BRIDGE_CMD_TOPIC, RESUBSCRIBE_PAYLOAD)
            )
        _restore_lcos_lamp(prev)

    _after_paint(_do)


def _digicon_controller():
    """Find DigiconMqttSml from INSTANCE / __main__ (same JMRI jython engine)."""
    try:
        import __main__

        ctrl = getattr(__main__, "digicon_sml_controller", None)
        if ctrl is not None:
            return ctrl
    except Exception:
        pass
    try:
        for obj in globals().values():
            cls = getattr(obj, "__class__", None)
            if cls is not None and getattr(cls, "__name__", "") == "DigiconMqttSml":
                inst = getattr(cls, "INSTANCE", None)
                if inst is not None:
                    return inst
    except Exception:
        pass
    try:
        cls = DigiconMqttSml  # noqa: F821
        return getattr(cls, "INSTANCE", None)
    except NameError:
        return None


def _watch_sml_amber_clear():
    """If Digicon finishes (or stalls), ensure Signals lamp leaves amber."""

    class _Watch(ActionListener):
        def __init__(self, attempt):
            self.attempt = attempt

        def actionPerformed(self, event):
            event.getSource().stop()
            try:
                s = sensors.getSensor(SML_MODE_SENSOR)
                if s is None or s.getKnownState() != jmri.Sensor.INCONSISTENT:
                    return
                ctrl = _digicon_controller()
                busy = bool(ctrl is not None and getattr(ctrl, "_busy", False))
                if busy and self.attempt < 40:
                    t = Timer(500, _Watch(self.attempt + 1))
                    t.setRepeats(False)
                    t.start()
                    return
                if ctrl is not None:
                    try:
                        ctrl._sync_sml_mode_sensor()
                        return
                    except Exception:
                        pass
                # Fallback: assume disabled if Digicon missing.
                s.setKnownState(jmri.Sensor.INACTIVE)
            except Exception as e:
                print("sync_layout_button: SML amber clear failed: %s" % e)

    t = Timer(500, _Watch(0))
    t.setRepeats(False)
    t.start()


def toggle_sml_mode():
    """Click Signals lamp: amber → Digicon SML toggle → Digicon paints final."""
    _show_amber_sensor(SML_MODE_SENSOR)

    def _do():
        ctrl = _digicon_controller()
        if ctrl is None:
            print(
                "sync_layout_button: Digicon SML controller not found "
                "(is mqtt_signalhead_publisher running?)"
            )
            try:
                sensors.provideSensor(SML_MODE_SENSOR).setKnownState(
                    jmri.Sensor.INACTIVE
                )
            except Exception:
                pass
            return
        try:
            ctrl.toggle_from_panel()
        except Exception as e:
            print("sync_layout_button: SML toggle failed: %s" % e)
        _watch_sml_amber_clear()

    _after_paint(_do)


def _power_manager():
    try:
        return jmri.InstanceManager.getDefault(jmri.PowerManager)
    except Exception:
        return None


def _sync_track_power_sensor():
    """Drive Track Power lamp from JMRI LCC/OpenLCB PowerManager."""
    try:
        s = sensors.provideSensor(TRACK_POWER_SENSOR)
    except Exception as e:
        print("sync_layout_button: Track Power sensor unavailable: %s" % e)
        return
    pm = _power_manager()
    if pm is None:
        return
    try:
        on = pm.getPower() == jmri.PowerManager.ON
    except Exception:
        return
    want = jmri.Sensor.ACTIVE if on else jmri.Sensor.INACTIVE
    try:
        if s.getKnownState() != want:
            s.setKnownState(want)
    except Exception as e:
        print("sync_layout_button: Track Power lamp set failed: %s" % e)


class _PowerListener(PropertyChangeListener):
    def propertyChange(self, event):
        try:
            if event.getPropertyName() == "power":
                _sync_track_power_sensor()
        except Exception as e:
            print("sync_layout_button: power listener error: %s" % e)


_power_listener = None


def _arm_power_listener():
    global _power_listener
    if _power_listener is not None:
        return
    pm = _power_manager()
    if pm is None:
        return
    _power_listener = _PowerListener()
    pm.addPropertyChangeListener(_power_listener)


def toggle_track_power():
    """Click Track Power lamp: amber → PowerManager ON/OFF → sync sensor."""
    _show_amber_sensor(TRACK_POWER_SENSOR)

    def _do():
        pm = _power_manager()
        if pm is None:
            print("sync_layout_button: no PowerManager for Track Power toggle")
            _sync_track_power_sensor()
            return
        try:
            if pm.getPower() == jmri.PowerManager.ON:
                pm.setPower(jmri.PowerManager.OFF)
                label = "OFF"
            else:
                pm.setPower(jmri.PowerManager.ON)
                label = "ON"
            print("sync_layout_button: Track Power lamp click → %s" % label)
        except Exception as e:
            print("sync_layout_button: Track Power toggle failed: %s" % e)
        _sync_track_power_sensor()

    _after_paint(_do, delay_ms=_LAMP_AMBER_MS)


def sync_ladder_buttons(event=None):
    global _busy, _last
    if _busy:
        return
    _busy = True
    try:
        left = _match(LEFT_PATTERNS)
        right = _match(RIGHT_PATTERNS)
        if (left, right) != _last:
            _last = (left, right)
            print(
                "sync_layout_button: left=%s right=%s"
                % (left or "none", right or "none")
            )
        _paint_indicators_without_commanding(left, right)
        sync_turnout_fb_lamp()
    except Exception as e:
        print("sync_layout_button: sync error: %s" % e)
    finally:
        _busy = False


_sync_timer = Timer(250, None)
_sync_timer.setRepeats(False)


class _DebouncedSync(ActionListener):
    def actionPerformed(self, event):
        sync_ladder_buttons()


_sync_timer.addActionListener(_DebouncedSync())


def _schedule_sync():
    class _Restart(Runnable):
        def run(self):
            _sync_timer.restart()

    try:
        if SwingUtilities.isEventDispatchThread():
            _sync_timer.restart()
        else:
            SwingUtilities.invokeLater(_Restart())
    except Exception as e:
        print("sync_layout_button: schedule failed: %s" % e)


class _TurnoutListener(PropertyChangeListener):
    def propertyChange(self, event):
        try:
            name = event.getPropertyName()
            if name in ("KnownState", "FeedbackMode", "Sensor1", "Sensor2"):
                _schedule_sync()
        except Exception as e:
            print("sync_layout_button: listener error: %s" % e)


class _SensorListener(PropertyChangeListener):
    def propertyChange(self, event):
        try:
            if event.getPropertyName() == "KnownState":
                _schedule_sync()
        except Exception as e:
            print("sync_layout_button: sensor listener error: %s" % e)


def _sensor_sys(icon):
    try:
        s = icon.getSensor()
        if s is None:
            return None
        return s.getSystemName()
    except Exception:
        return None


def _head_sys(icon):
    try:
        h = icon.getSignalHead()
        if h is None:
            return None
        return h.getSystemName()
    except Exception:
        return None


def _disable_icon_control(icon):
    try:
        icon.setControlling(False)
    except Exception:
        pass
    try:
        if hasattr(icon, "setClickMode"):
            icon.setClickMode(0)
    except Exception:
        pass


class _LampClick(MouseAdapter):
    def __init__(self, action):
        self._action = action

    def mouseClicked(self, event):
        global _click_busy
        if event.getButton() != MouseEvent.BUTTON1:
            return
        if _click_busy:
            return
        _click_busy = True
        try:
            self._action()
        except Exception as e:
            print("sync_layout_button: lamp click failed: %s" % e)
        finally:
            _click_busy = False


def _arm_status_lamp_clicks():
    """Attach left-click handlers on LCOS / Turnouts / Signals / Track Power icons."""
    global _clicks_armed
    if _clicks_armed:
        return True
    try:
        from jmri.jmrit.display import EditorManager, SensorIcon, SignalHeadIcon
    except Exception as e:
        print("sync_layout_button: display imports failed: %s" % e)
        return False

    em = jmri.InstanceManager.getDefault(EditorManager)
    if em is None:
        return False

    found = {"lcos": 0, "turnouts": 0, "signals": 0, "power": 0}
    for ed in list(em.getAll()):
        try:
            contents = list(ed.getContents())
        except Exception:
            continue
        for icon in contents:
            try:
                if isinstance(icon, SensorIcon):
                    sn = _sensor_sys(icon)
                    if sn == LCOS_SENSOR:
                        _disable_icon_control(icon)
                        icon.addMouseListener(_LampClick(publish_lcos_resubscribe))
                        found["lcos"] += 1
                    elif sn == SML_MODE_SENSOR:
                        _disable_icon_control(icon)
                        icon.addMouseListener(_LampClick(toggle_sml_mode))
                        found["signals"] += 1
                    elif sn == TRACK_POWER_SENSOR:
                        _disable_icon_control(icon)
                        icon.addMouseListener(_LampClick(toggle_track_power))
                        found["power"] += 1
                elif isinstance(icon, SignalHeadIcon):
                    if _head_sys(icon) == TURNOUT_FB_HEAD:
                        _disable_icon_control(icon)
                        icon.addMouseListener(_LampClick(toggle_turnout_fb_mode))
                        found["turnouts"] += 1
            except Exception as e:
                print("sync_layout_button: icon wire failed: %s" % e)

    if found["lcos"] and found["turnouts"] and found["signals"] and found["power"]:
        _clicks_armed = True
        print(
            "sync_layout_button: status lamp clicks ready "
            "(LCOS/Turnouts/Signals/Track Power)"
        )
        return True
    return False


def _reload_mqtt_retain_at_boot():
    """Fill UNKNOWN MQTT sensors from broker retain. Do not touch plant turnouts.

    apply_maintain_mqtt already paints turnout KnownState on its own delay.
    This script only needs occupancy/FB sensors so YL icons can match.
    """
    import os

    path = None
    try:
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "apply_maintain_mqtt.py",
        )
    except Exception:
        path = None
    if not path or not os.path.isfile(path):
        try:
            from jmri.util import FileUtil

            path = FileUtil.getExternalFilename(
                "preference:jython/apply_maintain_mqtt.py"
            )
        except Exception:
            path = None
    if not path or not os.path.isfile(path):
        print("sync_layout_button: apply_maintain_mqtt.py not found; skip MQTT reload")
        return False

    ns = {
        "_HART_MQTT_RETAIN_AS_LIBRARY": True,
        "__name__": "apply_maintain_mqtt_lib",
        "__file__": path,
    }
    try:
        f = open(path, "r")
        try:
            src = f.read()
        finally:
            f.close()
        exec(compile(src, path, "exec"), ns)
        fn = ns.get("reload_mqtt_retain")
        if fn is None:
            print("sync_layout_button: reload_mqtt_retain missing")
            return False
        # Sensors only. Never paint M2T/MTT here (that can command field points).
        n_s, n_t = fn(
            turnout_delay_ms=0,
            settle_secs=0,
            paint_turnouts=False,
            unknown_sensors_only=True,
            log_prefix="sync_layout_button/mqtt",
        )
        print(
            "sync_layout_button: MQTT retain sensors=%s (turnouts skipped, queued=%s)"
            % (n_s, n_t)
        )
        return True
    except Exception as e:
        print("sync_layout_button: MQTT retain reload failed: %s" % e)
        return False


def _arm_listeners():
    """Attach ladder/plant listeners once. Independent of panel icons."""
    global _armed, _listener, _sensor_listener, _plant_count
    if _armed:
        return True
    _listener = _TurnoutListener()
    _sensor_listener = _SensorListener()
    for sn in WATCH:
        to = turnouts.getTurnout(sn)
        if to is None:
            continue
        to.addPropertyChangeListener(_listener)
        for getter in ("getFirstSensor", "getSecondSensor"):
            try:
                s = getattr(to, getter)()
                if s is not None:
                    s.addPropertyChangeListener(_sensor_listener)
            except Exception:
                pass
    for sn in LEFT_INDICATORS + RIGHT_INDICATORS:
        turnouts.provideTurnout(sn)
    plants = _included_plant_turnouts()
    _plant_count = len(plants)
    for to in plants:
        try:
            to.addPropertyChangeListener(_listener)
        except Exception:
            pass
    _armed = True
    print(
        "sync_layout_button: armed (watch=%d plantFB=%d)"
        % (len(WATCH), _plant_count)
    )
    return True


class _ArmAttempt(ActionListener):
    def __init__(self, attempt):
        self.attempt = attempt

    def actionPerformed(self, event):
        event.getSource().stop()
        if not _watch_turnouts_present():
            if self.attempt + 1 >= _ARM_MAX_ATTEMPTS:
                print("sync_layout_button: watch turnouts missing; arming anyway")
            else:
                if self.attempt == 0:
                    print("sync_layout_button: waiting for watch turnouts…")
                t = Timer(_ARM_RETRY_MS, _ArmAttempt(self.attempt + 1))
                t.setRepeats(False)
                t.start()
                return
        try:
            _reload_mqtt_retain_at_boot()
            _arm_listeners()
            _arm_power_listener()
            _sync_track_power_sensor()
            sync_ladder_buttons()
        except Exception as e:
            print("sync_layout_button: arm failed: %s" % e)
        t = Timer(_CLICK_RETRY_MS, _RetryClicks(0))
        t.setRepeats(False)
        t.start()


class _RetryClicks(ActionListener):
    def __init__(self, attempt):
        self.attempt = attempt

    def actionPerformed(self, event):
        event.getSource().stop()
        try:
            if _arm_status_lamp_clicks():
                return
        except Exception as e:
            print("sync_layout_button: click retry failed: %s" % e)
        if self.attempt + 1 < _CLICK_MAX_ATTEMPTS:
            t = Timer(_CLICK_RETRY_MS, _RetryClicks(self.attempt + 1))
            t.setRepeats(False)
            t.start()
        else:
            print("sync_layout_button: status lamp icons not found on panel")


print("sync_layout_button: loaded; arming in %dms" % _ARM_FIRST_MS)
_t0 = Timer(_ARM_FIRST_MS, _ArmAttempt(0))
_t0.setRepeats(False)
_t0.start()
