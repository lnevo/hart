# Sync Digicon yard-ladder button indicators (IT:HART:YL:*) from live turnout states,
# and drive the HART Railroad Turnouts status lamp (IH:TURNOUT_FB).
#
# CRITICAL: the same ITs are JMRI Route controlTurnouts (fire on THROWN).
# This script must NEVER setCommandedState(THROWN) — that re-fires routes and
# ping-pongs peels (e.g. R4 ↔ R5). Only CLOSE inactive indicators.
#
# Turnouts lamp (Green / Yellow / Red): among M2T* and MTT* that have both FB
# sensors assigned — all TWOSENSOR → Green; all DIRECT → Red; mixed → Yellow.
#
# Arming is deferred until Layout Editor / turnout beans are up (Start Up scripts
# often run before panels finish opening).

import jmri
from java.beans import PropertyChangeListener
from java.awt.event import ActionListener
from java.lang import Runnable
from javax.swing import SwingUtilities, Timer

CLOSED = jmri.Turnout.CLOSED
THROWN = jmri.Turnout.THROWN
TWOSENSOR = jmri.Turnout.TWOSENSOR
DIRECT = jmri.Turnout.DIRECT

TURNOUT_FB_HEAD = "IH:TURNOUT_FB"
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
_last = (None, None)
_last_fb_appearance = None
_listener = None


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
    """M2T/MTT turnouts with both feedback sensors assigned."""
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


def _arm_listeners():
    """Attach listeners once beans exist. Safe to call only once."""
    global _armed, _listener
    if _armed:
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
        except Exception as e:
            print("sync_turnout_buttons: arm failed: %s" % e)
            if self.attempt + 1 < _ARM_MAX_ATTEMPTS:
                t = Timer(_ARM_RETRY_MS, _ArmAttempt(self.attempt + 1))
                t.setRepeats(False)
                t.start()


print(
    "sync_turnout_buttons: loaded; arming after %dms (waits for Layout Editor)"
    % _ARM_FIRST_MS
)
_t0 = Timer(_ARM_FIRST_MS, _ArmAttempt(0))
_t0.setRepeats(False)
_t0.start()
