# JMRI jython -- panel_status.py's panel clicks on the status lamps (LCOS, Turnouts, Signals, Track Power) at any
# zoom, and the lift of buried BlockContentsIcon labels.
#
# A sibling module of panel_status.py: it imports this from preference:jython and reloads it on every run
# (jython_siblings.py), so a re-run starts from fresh state here. The script hands in the lamps' actions and its
# listener cleanup (arm_status_lamp_clicks), so this module imports nothing of the script.

import jmri
from java.awt.event import MouseAdapter, MouseEvent

_clicks_armed = False
_panel_clicks = {}   # id(editor) -> its _PanelLampClick
_click_busy = False


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

    hart_panel_status = True  # panel_status.py's _MARK: a re-run finds and replaces it

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


def arm_status_lamp_clicks(sensor_lamps, head_lamps, drop_ours):
    """Attach left-click handlers on the status lamp icons; True once every lamp was found.

    sensor_lamps maps a SensorIcon's sensor system name, and head_lamps a SignalHeadIcon's head system name, to
    (lamp, action): `lamp` names it in the count and `action` runs on a click. drop_ours(listeners, remove) takes
    an earlier run's click listener off a panel before this run's goes on.
    """
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

    found = {}
    for lamp, _action in list(sensor_lamps.values()) + list(head_lamps.values()):
        found[lamp] = 0
    for ed in list(em.getAll()):
        try:
            contents = list(ed.getContents())
        except Exception:
            continue
        lamps = []
        for icon in contents:
            try:
                if isinstance(icon, SensorIcon):
                    wired = sensor_lamps.get(_sensor_sys(icon))
                elif isinstance(icon, SignalHeadIcon):
                    wired = head_lamps.get(_head_sys(icon))
                else:
                    wired = None
                if wired is not None:
                    lamp, action = wired
                    _disable_icon_control(icon)
                    lamps.append((icon, action))
                    found[lamp] += 1
            except Exception as e:
                print("panel_status: icon wire failed: %s" % e)
        if lamps:
            try:
                # a retry (not every lamp found yet) refreshes this editor's lamps instead of adding a second listener
                handler = _panel_clicks.get(id(ed))
                if handler is None:
                    handler = _PanelLampClick(ed)
                    target = ed.getTargetPanel()
                    drop_ours(target.getMouseListeners(), target.removeMouseListener)
                    target.addMouseListener(handler)
                    _panel_clicks[id(ed)] = handler
                handler.lamps = lamps
            except Exception as e:
                print("panel_status: panel click wire failed on %s: %s" % (ed, e))

    if all(found.values()):
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
