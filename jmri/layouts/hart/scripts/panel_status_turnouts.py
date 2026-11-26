# JMRI jython -- part of panel_status.py: the Turnouts lamp (IH9990): which plant turnouts it counts, its
# colour from their feedback modes, the amber shown while a click is pending, and the click that flips the plants
# between TWOSENSOR and DIRECT. Never setCommandedState on M2T*/MTT*.
#
# Not a module: panel_status.py runs this text in its own namespace at the place it was cut from (PARTS and
# _run_part there), so the names it defines and the globals it sets are the script's. Its imports, constants and
# state are the script's too.


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
