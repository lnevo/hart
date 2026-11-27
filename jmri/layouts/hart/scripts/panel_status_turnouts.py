# -*- coding: utf-8 -*-
# JMRI jython -- panel_status.py's Turnouts lamp (IH9990): which plant turnouts it counts, its colour from their
# feedback modes, the amber shown while a click is pending, and the click that flips the plants between TWOSENSOR
# and DIRECT. Never setCommandedState on M2T*/MTT*.
#
# A sibling module of panel_status.py: it imports this from preference:jython and reloads it on every run
# (jython_siblings.py), so a re-run starts from fresh state here. JMRI binds `turnouts` in the script's globals
# only, so this module asks InstanceManager for the same default manager.

import jmri
from java.awt.event import ActionListener
from java.lang import Runnable
from javax.swing import SwingUtilities, Timer

from panel_status_clicks import head_sys

TWOSENSOR = jmri.Turnout.TWOSENSOR
DIRECT = jmri.Turnout.DIRECT

TURNOUT_FB_HEAD = "IH9990"
# The Turnouts lamp's tooltip on the panel (panel_items.json): the key that finds the icon when it lost its head.
TURNOUT_FB_TOOLTIP = "Click: toggle TWOSENSOR/DIRECT on 2-sensor M2T/MTT"

GREEN = jmri.SignalHead.GREEN
YELLOW = jmri.SignalHead.YELLOW
RED = jmri.SignalHead.RED

# Hold amber long enough to feel like a click landed (FB flip itself is near-instant).
_LAMP_AMBER_MS = 500

_icon_rebound = False
_last_fb_appearance = None
# sys name -> feedback mode of each included plant. A full scan fills it; a turnout's own event updates its entry.
_plant_modes = {}
# Messages already printed: a scan repeats on every turnout event, so a failure that repeats is printed once.
_logged = set()


def _log_once(msg):
    """Print msg the first time only."""
    if msg not in _logged:
        _logged.add(msg)
        print(msg)


def _turnouts():
    """The default TurnoutManager: the one JMRI binds as `turnouts` in a script's globals."""
    return jmri.InstanceManager.getDefault(jmri.TurnoutManager)


def _has_two_fb_sensors(to):
    """Whether both feedback sensors are assigned; a turnout whose sensors cannot be read is logged and left out."""
    try:
        return to.getFirstSensor() is not None and to.getSecondSensor() is not None
    except Exception as e:
        _log_once("panel_status: cannot read the feedback sensors of %s: %s" % (to.getSystemName(), e))
        return False


def _is_plant(to):
    sn = to.getSystemName()
    return sn.startswith("M2T") or sn.startswith("MTT")


def _included_plant_turnouts():
    """M2T/MTT (MQTT/LCC plant) turnouts with both feedback sensors assigned."""
    out = []
    try:
        for to in _turnouts().getNamedBeanSet():
            if _is_plant(to) and _has_two_fb_sensors(to):
                out.append(to)
    except Exception as e:
        print("panel_status: scan turnouts failed: %s" % e)
    return out


def _feedback_mode(to):
    """The turnout's feedback mode; None, logged, when it cannot be read (the lamp then shows mixed)."""
    try:
        return to.getFeedbackMode()
    except Exception as e:
        _log_once("panel_status: cannot read the feedback mode of %s: %s" % (to.getSystemName(), e))
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
            except Exception as e:
                _log_once("panel_status: lookup of %s by system name failed: %s" % (TURNOUT_FB_HEAD, e))
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


def _head_call(what, call):
    """Run one call on the Turnouts lamp head; a failure is printed once and the next call still runs."""
    try:
        call()
    except Exception as e:
        _log_once("panel_status: Turnouts lamp %s failed: %s" % (what, e))


def _set_head_appearance(head, appearance):
    """Apply appearance on the EDT; clear held so icon is not '?'."""

    class _Set(Runnable):
        def run(self):
            _head_call("setHeld(False)", lambda: head.setHeld(False))
            _head_call("setLit(True)", lambda: head.setLit(True))
            _head_call("setAppearance(%s)" % appearance, lambda: head.setAppearance(appearance))

    try:
        if SwingUtilities.isEventDispatchThread():
            _Set().run()
        else:
            SwingUtilities.invokeLater(_Set())
    except Exception as e:
        _log_once("panel_status: cannot queue the Turnouts lamp on the EDT (%s); setting it on this thread" % e)
        _Set().run()


def _tooltip_text(icon):
    """The text of an icon's tooltip (Positionable.getToolTip), or None when it has none."""
    tip = icon.getToolTip()
    if tip is None:
        return None
    return tip.getText()


def _rebind_turnout_fb_icons(head):
    """Once: if the LE icon loaded before the bean existed, re-point it.

    The icon is the SignalHeadIcon that shows TURNOUT_FB_HEAD, or one with no head whose tooltip is
    TURNOUT_FB_TOOLTIP (the panel XML gives it that tooltip). An icon or editor that cannot be read is logged by
    name and skipped.
    """
    global _icon_rebound
    if head is None or _icon_rebound:
        return
    try:
        from jmri.jmrit.display import EditorManager, SignalHeadIcon
    except Exception as e:
        _log_once("panel_status: Turnouts icon rebind: display imports failed: %s" % e)
        return
    em = jmri.InstanceManager.getNullableDefault(EditorManager)
    if em is None:
        _log_once("panel_status: Turnouts icon rebind: no EditorManager yet")
        return
    rebound = False
    for ed in list(em.getAll()):
        try:
            contents = list(ed.getContents())
        except Exception as e:
            _log_once("panel_status: Turnouts icon rebind: cannot read the contents of %s: %s" % (ed, e))
            continue
        for icon in contents:
            if not isinstance(icon, SignalHeadIcon):
                continue
            try:
                shown = head_sys(icon)
            except Exception as e:
                _log_once("panel_status: Turnouts icon rebind: cannot read the head of %s: %s" % (icon, e))
                continue
            if shown == TURNOUT_FB_HEAD:
                rebound = True
                continue
            try:
                tip = _tooltip_text(icon)
            except Exception as e:
                _log_once("panel_status: Turnouts icon rebind: cannot read the tooltip of %s: %s" % (icon, e))
                continue
            if tip != TURNOUT_FB_TOOLTIP:
                continue
            try:
                icon.setSignalHead(TURNOUT_FB_HEAD)
            except Exception as e:
                print("panel_status: Turnouts icon rebind by name failed (%s); setting the head itself" % e)
                try:
                    icon.setSignalHead(head)
                except Exception as e2:
                    print("panel_status: Turnouts icon rebind failed on %s: %s" % (ed, e2))
                    continue
            rebound = True
            print("panel_status: rebound Turnouts icon -> %s" % TURNOUT_FB_HEAD)
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

    _set_head_appearance(head, appearance)      # each head call's failure is printed there
    if appearance != _last_fb_appearance:
        _last_fb_appearance = appearance
        print("panel_status: Turnouts lamp %s" % label)


def _show_amber_head():
    """Pending click feedback on Turnouts lamp (yellow)."""
    global _last_fb_appearance
    head = _ensure_turnout_fb_head()
    if head is None:
        return
    _set_head_appearance(head, YELLOW)
    _last_fb_appearance = YELLOW


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
        mode = _feedback_mode(to)      # one that cannot be read is logged and does not count
        if mode is not None:
            modes.add(mode)
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
                except Exception as e:
                    print("panel_status: %s known state from feedback failed: %s" % (to.getSystemName(), e))
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


def toggle_turnout_fb_mode():
    """Click Turnouts lamp: amber hold, then flip TWOSENSOR ↔ DIRECT, then final."""
    _show_amber_head()
    _after_paint(_toggle_turnout_fb_mode_body, delay_ms=_LAMP_AMBER_MS)
