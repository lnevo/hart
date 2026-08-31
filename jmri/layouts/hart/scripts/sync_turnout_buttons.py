# Sync Digicon yard-ladder button indicators (IT:HART:YL:*) from live turnout states,
# drive the HART Railroad Turnouts status lamp (IH:TURNOUT_FB), and wire clicks on
# the LCOS / Turnouts / Signals status lamps.
#
# CRITICAL: the same ITs are JMRI Route controlTurnouts (fire on THROWN).
# This script must NEVER setCommandedState(THROWN) — that re-fires routes and
# ping-pongs peels (e.g. R4 ↔ R5). Only CLOSE inactive indicators.
#
# Turnouts lamp (Green / Yellow / Red): among M2T* and MTT* that have both FB
# sensors assigned — all TWOSENSOR → Green; all DIRECT → Red; mixed → Yellow.
# Click: toggle those plants between TWOSENSOR and DIRECT.
#
# Signals lamp (IS:SML_MODE): click → DigiconMqttSml.toggle_from_panel().
# LCOS lamp (M2S1567): click → MQTT track/bridge/cmd RESUBSCRIBE (not FORCE).
#
# Arming is deferred until Layout Editor / turnout beans are up (Start Up scripts
# often run before panels finish opening).

import jmri
from java.awt.event import ActionListener, MouseAdapter, MouseEvent
from java.beans import PropertyChangeListener
from java.lang import Runnable
from javax.swing import SwingUtilities, Timer

CLOSED = jmri.Turnout.CLOSED
THROWN = jmri.Turnout.THROWN
TWOSENSOR = jmri.Turnout.TWOSENSOR
DIRECT = jmri.Turnout.DIRECT

TURNOUT_FB_HEAD = "IH:TURNOUT_FB"
LCOS_SENSOR = "M2S1567"
SML_MODE_SENSOR = "IS:SML_MODE"
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
    ("IT:HART:YL:R1", (("M2T1211", CLOSED),)),
]

LEFT_INDICATORS = [p[0] for p in LEFT_PATTERNS]
RIGHT_INDICATORS = [p[0] for p in RIGHT_PATTERNS]
WATCH = [
    "M2T308", "M2T309", "M2T310", "M2T311",
    "M2T1211", "M2T1210", "M2T1209", "M2T1208",
]

# Wait for LE / MQTT turnouts: first try after 5s, then every 2s up to ~60s.
_ARM_FIRST_MS = 5000
_ARM_RETRY_MS = 2000
_ARM_MAX_ATTEMPTS = 30

_busy = False
_armed = False
_clicks_armed = False
_last = (None, None)
_last_fb_appearance = None
_listener = None
_click_busy = False


def _known(to):
    if to is None:
        return None
    st = to.getKnownState()
    if st == CLOSED or st == THROWN:
        return st
    cmd = to.getCommandedState()
    if cmd == CLOSED or cmd == THROWN:
        return cmd
    return None


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


def _close_inactive(indicators, active):
    """Close non-active lamps only. Never THROWN — that fires Routes."""
    for sn in indicators:
        if sn == active:
            continue
        to = turnouts.getTurnout(sn)
        if to is None:
            continue
        try:
            if to.getCommandedState() != CLOSED:
                to.setCommandedState(CLOSED)
        except Exception as e:
            print("sync_turnout_buttons: close %s failed: %s" % (sn, e))


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
        print("sync_turnout_buttons: scan turnouts failed: %s" % e)
    return out


def _layout_editor_ready():
    """True once at least one Layout Editor panel is open (or editors exist)."""
    try:
        from jmri.jmrit.display import EditorManager

        em = jmri.InstanceManager.getDefault(EditorManager)
        if em is None:
            return False
        editors = list(em.getAll())
        if not editors:
            return False
        for ed in editors:
            name = ""
            try:
                name = ed.getTitle() or ed.getName() or ""
            except Exception:
                try:
                    name = str(ed)
                except Exception:
                    name = ""
            # Prefer HART Railroad; any LE is enough to know panels are up.
            if "HART" in name or "Layout" in name or "layout" in ed.getClass().getName():
                return True
        return len(editors) > 0
    except Exception:
        return False


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
    """Return IH:TURNOUT_FB, creating a VirtualSignalHead if tables omitted it."""
    try:
        mgr = jmri.InstanceManager.getDefault(jmri.SignalHeadManager)
        head = mgr.getSignalHead(TURNOUT_FB_HEAD)
        if head is not None:
            return head
        from jmri.implementation import VirtualSignalHead

        head = VirtualSignalHead(TURNOUT_FB_HEAD)
        mgr.register(head)
        print("sync_turnout_buttons: created VirtualSignalHead %s" % TURNOUT_FB_HEAD)
        return head
    except Exception as e:
        print("sync_turnout_buttons: Turnouts lamp head unavailable: %s" % e)
        return None


def sync_turnout_fb_lamp():
    """Set IH:TURNOUT_FB Green/Yellow/Red from included plant feedback modes."""
    global _last_fb_appearance
    head = _ensure_turnout_fb_head()
    if head is None:
        return

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
        if head.getAppearance() != appearance:
            head.setAppearance(appearance)
        if appearance != _last_fb_appearance:
            _last_fb_appearance = appearance
            print("sync_turnout_buttons: Turnouts lamp %s" % label)
    except Exception as e:
        print("sync_turnout_buttons: Turnouts lamp set failed: %s" % e)


def toggle_turnout_fb_mode():
    """Click Turnouts lamp: flip included plants TWOSENSOR ↔ DIRECT."""
    included = _included_plant_turnouts()
    if not included:
        print("sync_turnout_buttons: no 2-sensor M2T/MTT plants to toggle")
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
        # All DIRECT, mixed, or other → TWOSENSOR (recover feedback).
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
                "sync_turnout_buttons: setFeedbackMode %s failed: %s"
                % (to.getSystemName(), e)
            )
    print(
        "sync_turnout_buttons: Turnouts lamp click → %s on %d plant(s)"
        % (label, n)
    )
    sync_turnout_fb_lamp()


def _mqtt_publish(topic, payload):
    try:
        memo = jmri.InstanceManager.getDefault(
            jmri.jmrix.mqtt.MqttSystemConnectionMemo
        )
        if memo is None:
            print("sync_turnout_buttons: no MQTT connection")
            return False
        adapter = memo.getMqttAdapter()
        if adapter is None:
            print("sync_turnout_buttons: no MQTT adapter")
            return False
        adapter.publish(topic, payload)
        return True
    except Exception as e:
        print("sync_turnout_buttons: MQTT publish failed: %s" % e)
        return False


def publish_lcos_resubscribe():
    """Click LCOS lamp: plain RESUBSCRIBE (not FORCE) on track/bridge/cmd."""
    if _mqtt_publish(BRIDGE_CMD_TOPIC, RESUBSCRIBE_PAYLOAD):
        print(
            "sync_turnout_buttons: LCOS lamp → %s %s"
            % (BRIDGE_CMD_TOPIC, RESUBSCRIBE_PAYLOAD)
        )


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
        # Class may live in this interpreter if the publisher script shared ns.
        for obj in globals().values():
            cls = getattr(obj, "__class__", None)
            if cls is not None and getattr(cls, "__name__", "") == "DigiconMqttSml":
                inst = getattr(cls, "INSTANCE", None)
                if inst is not None:
                    return inst
    except Exception:
        pass
    try:
        # Publisher may have left DigiconMqttSml in this namespace.
        cls = DigiconMqttSml  # noqa: F821 — may exist after publisher load
        return getattr(cls, "INSTANCE", None)
    except NameError:
        return None


def toggle_sml_mode():
    """Click Signals lamp: Digicon global SML enable/disable."""
    ctrl = _digicon_controller()
    if ctrl is None:
        print(
            "sync_turnout_buttons: Digicon SML controller not found "
            "(is mqtt_signalhead_publisher running?)"
        )
        return
    try:
        ctrl.toggle_from_panel()
    except Exception as e:
        print("sync_turnout_buttons: SML toggle failed: %s" % e)


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
                "sync_turnout_buttons: left=%s right=%s"
                % (left or "none", right or "none")
            )
        _close_inactive(LEFT_INDICATORS, left)
        _close_inactive(RIGHT_INDICATORS, right)
        sync_turnout_fb_lamp()
    except Exception as e:
        print("sync_turnout_buttons: sync error: %s" % e)
    finally:
        _busy = False


# Debounce peel bursts from a single route.
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
        print("sync_turnout_buttons: schedule failed: %s" % e)


class _TurnoutListener(PropertyChangeListener):
    def propertyChange(self, event):
        try:
            name = event.getPropertyName()
            if name in ("KnownState", "FeedbackMode", "Sensor1", "Sensor2"):
                _schedule_sync()
        except Exception as e:
            print("sync_turnout_buttons: listener error: %s" % e)


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
    """Stop JMRI default click (toggle sensor / cycle head)."""
    try:
        icon.setControlling(False)
    except Exception:
        pass
    try:
        # SignalHeadIcon: 0=change aspect — leave mode but controlling off.
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
            print("sync_turnout_buttons: lamp click failed: %s" % e)
        finally:
            _click_busy = False


def _arm_status_lamp_clicks():
    """Attach left-click handlers on LCOS / Turnouts / Signals panel icons."""
    global _clicks_armed
    if _clicks_armed:
        return True
    try:
        from jmri.jmrit.display import EditorManager, SensorIcon, SignalHeadIcon
    except Exception as e:
        print("sync_turnout_buttons: display imports failed: %s" % e)
        return False

    em = jmri.InstanceManager.getDefault(EditorManager)
    if em is None:
        return False

    found = {"lcos": 0, "turnouts": 0, "signals": 0}
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
                elif isinstance(icon, SignalHeadIcon):
                    hn = _head_sys(icon)
                    if hn == TURNOUT_FB_HEAD:
                        _disable_icon_control(icon)
                        icon.addMouseListener(_LampClick(toggle_turnout_fb_mode))
                        found["turnouts"] += 1
            except Exception as e:
                print("sync_turnout_buttons: icon wire failed: %s" % e)

    if found["lcos"] or found["turnouts"] or found["signals"]:
        _clicks_armed = True
        print(
            "sync_turnout_buttons: status lamp clicks "
            "LCOS=%d Turnouts=%d Signals=%d"
            % (found["lcos"], found["turnouts"], found["signals"])
        )
        return True
    return False


def _arm_listeners():
    """Attach listeners once beans exist. Safe to call only once."""
    global _armed, _listener
    if _armed:
        _arm_status_lamp_clicks()
        return True
    _listener = _TurnoutListener()
    for sn in WATCH:
        turnouts.provideTurnout(sn).addPropertyChangeListener(_listener)
    for sn in LEFT_INDICATORS + RIGHT_INDICATORS:
        turnouts.provideTurnout(sn)
    for to in turnouts.getNamedBeanSet():
        sn = to.getSystemName()
        if sn.startswith("M2T") or sn.startswith("MTT"):
            try:
                to.addPropertyChangeListener(_listener)
            except Exception:
                pass
    _armed = True
    print(
        "sync_turnout_buttons: armed (%d watch turnouts, close-only + Turnouts lamp)"
        % len(WATCH)
    )
    _arm_status_lamp_clicks()
    return True


class _ArmAttempt(ActionListener):
    def __init__(self, attempt):
        self.attempt = attempt

    def actionPerformed(self, event):
        event.getSource().stop()
        ready = _watch_turnouts_present()
        le_ok = _layout_editor_ready()
        if not ready or not le_ok:
            if self.attempt + 1 >= _ARM_MAX_ATTEMPTS:
                print(
                    "sync_turnout_buttons: giving up wait "
                    "(turnouts=%s layoutEditor=%s); arming anyway"
                    % (ready, le_ok)
                )
            else:
                if self.attempt == 0 or (self.attempt % 5) == 0:
                    print(
                        "sync_turnout_buttons: waiting for panel/turnouts "
                        "(try %d, LE=%s, watch=%s)"
                        % (self.attempt + 1, le_ok, ready)
                    )
                t = Timer(_ARM_RETRY_MS, _ArmAttempt(self.attempt + 1))
                t.setRepeats(False)
                t.start()
                return
        try:
            _arm_listeners()
            sync_ladder_buttons()
            # Icons may appear slightly after LE; retry click wiring a few times.
            if not _clicks_armed:
                t = Timer(2000, _RetryClicks(0))
                t.setRepeats(False)
                t.start()
        except Exception as e:
            print("sync_turnout_buttons: arm failed: %s" % e)
            if self.attempt + 1 < _ARM_MAX_ATTEMPTS:
                t = Timer(_ARM_RETRY_MS, _ArmAttempt(self.attempt + 1))
                t.setRepeats(False)
                t.start()


class _RetryClicks(ActionListener):
    def __init__(self, attempt):
        self.attempt = attempt

    def actionPerformed(self, event):
        event.getSource().stop()
        if _arm_status_lamp_clicks():
            return
        if self.attempt + 1 < 10:
            t = Timer(2000, _RetryClicks(self.attempt + 1))
            t.setRepeats(False)
            t.start()
        else:
            print("sync_turnout_buttons: status lamp icons not found on panel")


print(
    "sync_turnout_buttons: loaded; arming after %dms (waits for Layout Editor)"
    % _ARM_FIRST_MS
)
_t0 = Timer(_ARM_FIRST_MS, _ArmAttempt(0))
_t0.setRepeats(False)
_t0.start()
