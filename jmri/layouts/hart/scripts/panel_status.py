# Drive HART Railroad status lamps and wire clicks on LCOS / Turnouts /
# Signals / Track Power panel icons. Never setCommandedState on M2T*/MTT*.
#
# The Digicon yard-ladder buttons, their internal turnouts and routes
# IO:AUTO:0201-0210, and their lamp painting are gone (owner, 2026-11-17).
#
# Turnouts lamp (Green / Yellow / Red): among M2T* and MTT* that have both FB
# sensors assigned — all TWOSENSOR → Green; all DIRECT → Red; mixed → Yellow.
# Click: toggle those plants between TWOSENSOR and DIRECT.
#
# Signals lamp (IS:SML_MODE): click → DigiconMqttSml.toggle_from_panel().
# LCOS lamp (M2S1567): click → MQTT track/bridge/cmd RESUBSCRIBE (not FORCE).
# Track Power lamp (IS:TRACK_POWER): mirrors LCC PowerManager; click toggles ON/OFF.
#
# Lamps arm as soon as plant turnouts exist. Panel click wiring retries
# quietly afterward (do not block on Layout Editor — EditorManager often lags).

import jmri
from java.awt.event import ActionListener, MouseAdapter, MouseEvent
from java.beans import PropertyChangeListener
from java.lang import Runnable
from javax.swing import SwingUtilities, Timer

TWOSENSOR = jmri.Turnout.TWOSENSOR
DIRECT = jmri.Turnout.DIRECT

TURNOUT_FB_HEAD = "IH9990"
LCOS_SENSOR = "M2S1567"
SML_MODE_SENSOR = "IS:SML_MODE"
TRACK_POWER_SENSOR = "IS:TRACK_POWER"
BRIDGE_CMD_TOPIC = "track/bridge/cmd"
RESUBSCRIBE_PAYLOAD = "RESUBSCRIBE"

GREEN = jmri.SignalHead.GREEN
YELLOW = jmri.SignalHead.YELLOW
RED = jmri.SignalHead.RED

# Lamps: short settle, then arm when plant turnouts exist (no LE gate).
_ARM_FIRST_MS = 1000
_ARM_RETRY_MS = 1000
_ARM_MAX_ATTEMPTS = 15
# Clicks: quiet background retries after panel contents appear.
_CLICK_RETRY_MS = 2000
_CLICK_MAX_ATTEMPTS = 30

_armed = False
_clicks_armed = False
_panel_clicks = {}   # id(editor) -> its _PanelLampClick
_icon_rebound = False
_last_fb_appearance = None
_listener = None
_click_busy = False
_plant_count = 0
# sys name -> feedback mode of each included plant. A full scan fills it; a turnout's own event updates its entry.
_plant_modes = {}

# Every listener this script attaches carries this attribute, so a second run of the script can find the first
# run's listeners and remove them (otherwise one click toggles twice). Same approach as mimic_relay.py.
_MARK = "hart_panel_status"


def _ours(listener):
    return bool(getattr(listener, _MARK, False))


def _drop_ours(listeners, remove, keep=None):
    """Remove every listener of ours except `keep`; returns how many went."""
    n = 0
    for old in list(listeners):
        if old is not keep and _ours(old):
            try:
                remove(old)
                n += 1
            except Exception as e:
                print("panel_status: detach failed: %s" % e)
    return n


def _has_two_fb_sensors(to):
    try:
        return to.getFirstSensor() is not None and to.getSecondSensor() is not None
    except Exception:
        return False


def _is_plant(to):
    sn = to.getSystemName()
    return sn.startswith("M2T") or sn.startswith("MTT")


def _included_plant_turnouts():
    """M2T/MTT (MQTT/LCC plant) turnouts with both feedback sensors assigned."""
    out = []
    try:
        for to in turnouts.getNamedBeanSet():
            if _is_plant(to) and _has_two_fb_sensors(to):
                out.append(to)
    except Exception as e:
        print("panel_status: scan turnouts failed: %s" % e)
    return out


def _feedback_mode(to):
    try:
        return to.getFeedbackMode()
    except Exception:
        return None


def _rescan_plant_modes():
    """Full scan: refill the mode cache from every plant turnout."""
    global _plant_modes
    modes = {}
    for to in _included_plant_turnouts():
        modes[to.getSystemName()] = _feedback_mode(to)
    _plant_modes = modes


def _note_plant(to):
    """One turnout changed: update only its entry (it may also have gained or lost a feedback sensor)."""
    try:
        sn = to.getSystemName()
        if _is_plant(to) and _has_two_fb_sensors(to):
            _plant_modes[sn] = _feedback_mode(to)
        else:
            _plant_modes.pop(sn, None)
    except Exception as e:
        print("panel_status: plant update failed: %s" % e)


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
        print("panel_status: created VirtualSignalHead %s" % TURNOUT_FB_HEAD)
        return head
    except Exception as e:
        print("panel_status: Turnouts lamp head unavailable: %s" % e)
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
                print("panel_status: setAppearance failed: %s" % e)

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
                        "panel_status: rebound Turnouts icon -> %s"
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
    """Set IH9990 Green/Yellow/Red from included plant feedback modes (full scan of the turnouts)."""
    _rescan_plant_modes()
    _paint_turnout_fb_lamp()


def _paint_turnout_fb_lamp():
    """Set IH9990 from the mode cache, without scanning the turnouts."""
    global _last_fb_appearance
    head = _ensure_turnout_fb_head()
    if head is None:
        return
    _rebind_turnout_fb_icons(head)

    count = len(_plant_modes)
    if not count:
        appearance = YELLOW
        label = "yellow(empty)"
    else:
        modes = set(_plant_modes.values())
        if modes == {TWOSENSOR}:
            appearance = GREEN
            label = "green(all TWOSENSOR, n=%d)" % count
        elif modes == {DIRECT}:
            appearance = RED
            label = "red(all DIRECT, n=%d)" % count
        else:
            appearance = YELLOW
            label = "yellow(mixed %s, n=%d)" % (
                sorted(str(m) for m in modes),
                count,
            )

    try:
        _set_head_appearance(head, appearance)
        if appearance != _last_fb_appearance:
            _last_fb_appearance = appearance
            print("panel_status: Turnouts lamp %s" % label)
    except Exception as e:
        print("panel_status: Turnouts lamp set failed: %s" % e)


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
        print("panel_status: amber %s failed: %s" % (sys_name, e))


def _after_paint(fn, delay_ms=80):
    """Run fn after delay so amber can paint first (EDT redraw)."""

    class _Go(ActionListener):
        def actionPerformed(self, event):
            event.getSource().stop()
            try:
                fn()
            except Exception as e:
                print("panel_status: deferred action failed: %s" % e)

    t = Timer(delay_ms, _Go())
    t.setRepeats(False)
    t.start()


def _toggle_turnout_fb_mode_body():
    included = _included_plant_turnouts()
    if not included:
        print("panel_status: no 2-sensor M2T/MTT plants to toggle")
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
                "panel_status: setFeedbackMode %s failed: %s"
                % (to.getSystemName(), e)
            )
    print(
        "panel_status: Turnouts lamp click → %s on %d plant(s)"
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
            print("panel_status: no MQTT connection")
            return False
        adapter = memo.getMqttAdapter()
        if adapter is None:
            print("panel_status: no MQTT adapter")
            return False
        # Host commands to the bridge are not retained. JMRI's two-argument publish retains,
        # so the flag is named here. The three-argument form needs JMRI 5.9.1 or later.
        adapter.publish(topic, payload, False)
        return True
    except Exception as e:
        print("panel_status: MQTT publish failed: %s" % e)
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
                print("panel_status: LCOS restore failed: %s" % e)

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
                "panel_status: LCOS lamp → %s %s"
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
                print("panel_status: SML amber clear failed: %s" % e)

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
                "panel_status: Digicon SML controller not found "
                "(is signal_coordinator running?)"
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
            print("panel_status: SML toggle failed: %s" % e)
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
        print("panel_status: Track Power sensor unavailable: %s" % e)
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
        print("panel_status: Track Power lamp set failed: %s" % e)


class _PowerListener(PropertyChangeListener):
    hart_panel_status = True  # _MARK: a re-run finds and replaces it

    def propertyChange(self, event):
        try:
            if event.getPropertyName() == "power":
                _sync_track_power_sensor()
        except Exception as e:
            print("panel_status: power listener error: %s" % e)


_power_listener = None


def _arm_power_listener():
    global _power_listener
    if _power_listener is not None:
        return
    pm = _power_manager()
    if pm is None:
        return
    _power_listener = _PowerListener()
    _drop_ours(pm.getPropertyChangeListeners(), pm.removePropertyChangeListener)
    pm.addPropertyChangeListener(_power_listener)


def toggle_track_power():
    """Click Track Power lamp: amber → PowerManager ON/OFF → sync sensor."""
    _show_amber_sensor(TRACK_POWER_SENSOR)

    def _do():
        pm = _power_manager()
        if pm is None:
            print("panel_status: no PowerManager for Track Power toggle")
            _sync_track_power_sensor()
            return
        try:
            if pm.getPower() == jmri.PowerManager.ON:
                pm.setPower(jmri.PowerManager.OFF)
                label = "OFF"
            else:
                pm.setPower(jmri.PowerManager.ON)
                label = "ON"
            print("panel_status: Track Power lamp click → %s" % label)
        except Exception as e:
            print("panel_status: Track Power toggle failed: %s" % e)
        _sync_track_power_sensor()

    _after_paint(_do, delay_ms=_LAMP_AMBER_MS)


def sync_lamps(event=None):
    """The lamps that follow plant state: the Turnouts lamp (sync_turnout_fb_lamp catches its own errors)."""
    sync_turnout_fb_lamp()


_sync_timer = Timer(250, None)
_sync_timer.setRepeats(False)


class _DebouncedSync(ActionListener):
    def actionPerformed(self, event):
        # turnout events have already updated their own cache entries; repaint without a full scan
        _paint_turnout_fb_lamp()


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
        print("panel_status: schedule failed: %s" % e)


class _TurnoutListener(PropertyChangeListener):
    hart_panel_status = True  # _MARK: a re-run finds and replaces it

    def propertyChange(self, event):
        try:
            name = event.getPropertyName()
            if name in ("KnownState", "FeedbackMode", "Sensor1", "Sensor2"):
                _note_plant(event.getSource())
                _schedule_sync()
        except Exception as e:
            print("panel_status: listener error: %s" % e)


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


def _run_lamp_action(action):
    global _click_busy
    if _click_busy:
        return
    _click_busy = True
    try:
        action()
    except Exception as e:
        print("panel_status: lamp click failed: %s" % e)
    finally:
        _click_busy = False


def _lamp_at(lamps, scale, x, y):
    """The action of the lamp drawn under panel point (x, y), or None.

    The editor paints its contents scaled by its zoom (Editor.getPaintScale) but leaves each icon's Swing bounds
    unscaled, so a listener on the icon itself only fires where the unscaled icon would be: at zoom to fit the lamp
    is drawn in one place and clickable in another. Convert the click the way the editor does (divide by the scale)
    and test it against the icon's unscaled bounds; like the editor, the topmost hit wins and hidden icons count.
    """
    if not scale or scale <= 0:
        scale = 1.0
    px, py = x / float(scale), y / float(scale)
    hits = []
    for icon, action in lamps:
        try:
            ix, iy = icon.getX(), icon.getY()
            if ix <= px < ix + icon.getWidth() and iy <= py < iy + icon.getHeight():
                hits.append((icon.getDisplayLevel(), action))
        except Exception:
            continue
    if not hits:
        return None
    # the editor acts on the topmost item (highest display level), so overlapping lamps resolve the same way
    hits.sort(key=lambda h: h[0], reverse=True)
    return hits[0][1]


class _PanelLampClick(MouseAdapter):
    """One listener on an editor's target panel that finds the clicked status lamp at any zoom."""

    hart_panel_status = True  # _MARK: a re-run finds and replaces it

    def __init__(self, editor):
        self._editor = editor
        self.lamps = []
        self._scale_warned = False

    def mouseClicked(self, event):
        # the same filter as LayoutEditor.mouseClicked: a plain left click only (Ctrl-click is the Mac popup,
        # Shift/Ctrl/Meta/Alt-click amend the edit selection)
        if event.getButton() != MouseEvent.BUTTON1:
            return
        if (event.isPopupTrigger() or event.isMetaDown() or event.isAltDown() or event.isShiftDown()
                or event.isControlDown()):
            return
        try:
            scale = self._editor.getPaintScale()
        except Exception as e:
            if not self._scale_warned:
                print("panel_status: getPaintScale failed, lamp clicks assume 100%% zoom: %s" % e)
                self._scale_warned = True
            scale = 1.0
        action = _lamp_at(self.lamps, scale, event.getX(), event.getY())
        if action is not None:
            _run_lamp_action(action)


def _arm_status_lamp_clicks():
    """Attach left-click handlers on LCOS / Turnouts / Signals / Track Power icons."""
    global _clicks_armed
    if _clicks_armed:
        return True
    try:
        from jmri.jmrit.display import EditorManager, SensorIcon, SignalHeadIcon
    except Exception as e:
        print("panel_status: display imports failed: %s" % e)
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
        lamps = []
        for icon in contents:
            try:
                if isinstance(icon, SensorIcon):
                    sn = _sensor_sys(icon)
                    if sn == LCOS_SENSOR:
                        _disable_icon_control(icon)
                        lamps.append((icon, publish_lcos_resubscribe))
                        found["lcos"] += 1
                    elif sn == SML_MODE_SENSOR:
                        _disable_icon_control(icon)
                        lamps.append((icon, toggle_sml_mode))
                        found["signals"] += 1
                    elif sn == TRACK_POWER_SENSOR:
                        _disable_icon_control(icon)
                        lamps.append((icon, toggle_track_power))
                        found["power"] += 1
                elif isinstance(icon, SignalHeadIcon):
                    if _head_sys(icon) == TURNOUT_FB_HEAD:
                        _disable_icon_control(icon)
                        lamps.append((icon, toggle_turnout_fb_mode))
                        found["turnouts"] += 1
            except Exception as e:
                print("panel_status: icon wire failed: %s" % e)
        if lamps:
            try:
                # a retry (not every lamp found yet) refreshes this editor's lamps instead of adding a second listener
                handler = _panel_clicks.get(id(ed))
                if handler is None:
                    handler = _PanelLampClick(ed)
                    target = ed.getTargetPanel()
                    _drop_ours(target.getMouseListeners(), target.removeMouseListener)
                    target.addMouseListener(handler)
                    _panel_clicks[id(ed)] = handler
                handler.lamps = lamps
            except Exception as e:
                print("panel_status: panel click wire failed on %s: %s" % (ed, e))

    if found["lcos"] and found["turnouts"] and found["signals"] and found["power"]:
        _clicks_armed = True
        print(
            "panel_status: status lamp clicks ready "
            "(LCOS/Turnouts/Signals/Track Power)"
        )
        return True
    return False


_BCI_LEVEL = 4
_bci_raised = False


def _raise_block_labels():
    """Lift buried BlockContentsIcon labels (Stage 1 Store writes level 0)."""
    global _bci_raised
    if _bci_raised:
        return 0
    try:
        from jmri.jmrit.display import BlockContentsIcon, EditorManager
    except Exception as e:
        print("panel_status: BlockContentsIcon import failed: %s" % e)
        return 0
    em = jmri.InstanceManager.getDefault(EditorManager)
    if em is None:
        return 0
    titles = set(["HART Railroad", "HART", "My Layout"])
    n = 0
    for ed in list(em.getAll()):
        try:
            if (ed.getTitle() or "") not in titles:
                continue
            contents = list(ed.getContents())
        except Exception:
            continue
        for icon in contents:
            try:
                if not isinstance(icon, BlockContentsIcon):
                    continue
                if icon.getDisplayLevel() != _BCI_LEVEL:
                    icon.setDisplayLevel(_BCI_LEVEL)
                    n += 1
            except Exception as e:
                print("panel_status: raise BCI failed: %s" % e)
        if n:
            try:
                frame = ed.getTargetFrame()
                if frame is not None:
                    frame.repaint()
            except Exception:
                pass
    if n:
        print(
            "panel_status: raised %d BlockContentsIcon(s) to level %d"
            % (n, _BCI_LEVEL)
        )
    _bci_raised = True
    return n


def _arm_listeners():
    """Attach plant listeners once (the Turnouts lamp). Independent of panel icons."""
    global _armed, _listener, _plant_count
    if _armed:
        return True
    _listener = _TurnoutListener()
    plants = _included_plant_turnouts()
    _plant_count = len(plants)
    for to in plants:
        try:
            _drop_ours(to.getPropertyChangeListeners(), to.removePropertyChangeListener)
            to.addPropertyChangeListener(_listener)
        except Exception:
            pass
    _armed = True
    print("panel_status: armed (plantFB=%d)" % _plant_count)
    return True


class _ArmAttempt(ActionListener):
    """Arm once the plant turnouts have loaded: some present and their count unchanged since the last try, so a
    connection that registers its turnouts later is not left without listeners."""
    def __init__(self, attempt, last=-1):
        self.attempt = attempt
        self.last = last

    def actionPerformed(self, event):
        event.getSource().stop()
        n = len(_included_plant_turnouts())
        if n == 0 or n != self.last:
            if self.attempt + 1 >= _ARM_MAX_ATTEMPTS:
                print("panel_status: plant turnouts not settled (%d); arming anyway" % n)
            else:
                if self.attempt == 0:
                    print("panel_status: waiting for plant turnouts…")
                t = Timer(_ARM_RETRY_MS, _ArmAttempt(self.attempt + 1, n))
                t.setRepeats(False)
                t.start()
                return
        try:
            _arm_listeners()
            _arm_power_listener()
            _sync_track_power_sensor()
            _raise_block_labels()
            sync_lamps()
        except Exception as e:
            print("panel_status: arm failed: %s" % e)
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
            print("panel_status: click retry failed: %s" % e)
        if self.attempt + 1 < _CLICK_MAX_ATTEMPTS:
            t = Timer(_CLICK_RETRY_MS, _RetryClicks(self.attempt + 1))
            t.setRepeats(False)
            t.start()
        else:
            print("panel_status: status lamp icons not found on panel")


def _detach_previous_run():
    """A second run of this script: take the first run's listeners off now, before this run arms its own."""
    n = 0
    try:
        for to in turnouts.getNamedBeanSet():
            if _is_plant(to):
                n += _drop_ours(to.getPropertyChangeListeners(), to.removePropertyChangeListener)
    except Exception as e:
        print("panel_status: detach turnout listeners failed: %s" % e)
    pm = _power_manager()
    if pm is not None:
        try:
            n += _drop_ours(pm.getPropertyChangeListeners(), pm.removePropertyChangeListener)
        except Exception as e:
            print("panel_status: detach power listener failed: %s" % e)
    try:
        from jmri.jmrit.display import EditorManager

        em = jmri.InstanceManager.getDefault(EditorManager)
        for ed in list(em.getAll()) if em is not None else []:
            try:
                target = ed.getTargetPanel()
                n += _drop_ours(target.getMouseListeners(), target.removeMouseListener)
            except Exception:
                continue
    except Exception as e:
        print("panel_status: detach click listeners failed: %s" % e)
    if n:
        print("panel_status: removed %d listener(s) left by an earlier run" % n)


_detach_previous_run()
print("panel_status: loaded; arming in %dms" % _ARM_FIRST_MS)
_t0 = Timer(_ARM_FIRST_MS, _ArmAttempt(0))
_t0.setRepeats(False)
_t0.start()
