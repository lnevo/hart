# Sync Digicon yard-ladder button indicators (IT:HART:YL:*) from live turnout states,
# and drive the HART Railroad Turnouts status lamp (IH:TURNOUT_FB).
# Startup + turnout listeners so idle lamps stay mutually exclusive after a click.
#
# CRITICAL: the same ITs are JMRI Route controlTurnouts (fire on THROWN).
# This script must NEVER setCommandedState(THROWN) — that re-fires routes and
# ping-pongs peels (e.g. R4 ↔ R5). Only CLOSE inactive indicators.
#
# Turnouts lamp (Green / Yellow / Red): among M2T* and MTT* that have both FB
# sensors assigned — all TWOSENSOR → Green; all DIRECT → Red; mixed → Yellow.

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
DARK = jmri.SignalHead.DARK

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

_busy = False
_last = (None, None)
_last_fb_appearance = None


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


def sync_turnout_fb_lamp():
    """Set IH:TURNOUT_FB Green/Yellow/Red from included plant feedback modes."""
    global _last_fb_appearance
    try:
        mgr = jmri.InstanceManager.getDefault(jmri.SignalHeadManager)
        head = mgr.getSignalHead(TURNOUT_FB_HEAD)
    except Exception as e:
        print("sync_turnout_buttons: no Turnouts lamp head: %s" % e)
        return
    if head is None:
        print("sync_turnout_buttons: missing %s" % TURNOUT_FB_HEAD)
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


class _StartupAction(ActionListener):
    def actionPerformed(self, event):
        sync_ladder_buttons()
        event.getSource().stop()


try:
    listener = _TurnoutListener()
    for sn in WATCH:
        turnouts.provideTurnout(sn).addPropertyChangeListener(listener)
    for sn in LEFT_INDICATORS + RIGHT_INDICATORS:
        turnouts.provideTurnout(sn)
    # Listen for FB mode / sensor assignment changes on all plant turnouts.
    for to in turnouts.getNamedBeanSet():
        sn = to.getSystemName()
        if sn.startswith("M2T") or sn.startswith("MTT"):
            try:
                to.addPropertyChangeListener(listener)
            except Exception:
                pass
    sync_ladder_buttons()
    t = Timer(3000, _StartupAction())
    t.setRepeats(False)
    t.start()
    print(
        "sync_turnout_buttons: armed (%d watch turnouts, close-only + Turnouts lamp)"
        % len(WATCH)
    )
except Exception as e:
    print("sync_turnout_buttons: init failed: %s" % e)
