# JMRI Jython: under CATS, hide HART Railroad and add Help/Quit on CTC Panel.
#
# LogixNG IQ:AUTO:0001 runs this at init as IQC:AUTO:0004. IQC:AUTO:0001 already
# hides WiThrottle on every host. The USS CTC and Dispatcher System panels are
# parked out of tables.xml (hartlib.parked) with the ConditionalNGs that hid them
# (IQC:AUTO:0002/0003), so neither window opens and nothing here looks for them.
# PanelPro leaves HART Railroad up; CATS is a separate JVM (cats.apps.Crandic) and
# should not keep that geographic panel.
#
# MUST stay ASCII. Jython 2.7 LogixNG ActionScript crashes the whole file on a
# UnicodeDecodeError, so one non-ASCII byte stops it before the buttons go on.
# Do not add "from __future__ import print_function": JMRI's shared Jython
# engine keeps that flag and then stock Dispatcher System Startup.py fails
# on `print "closed Option"`.
#
# CTC Panel: Help/Quit go on Apps.buttonSpace() (bottom, with Restart RPi).
# Nothing goes at the top of the window, in its File menu (it has Exit) or on
# CATS's Dispatcher Panel.
#
# The menu, button and window calls below are Swing calls on windows that may be
# closing; each one that fails is printed and the pass goes on.

from java.awt import Frame, Window
from java.awt.event import ActionListener
from java.lang import System

from javax.swing import JButton

from jmri.util import JmriJFrame, ThreadingUtil

HART_RAILROAD = "HART Railroad"
CTC_PANEL = "CTC Panel"
HELP_NAME = "HART:CATS:Help"
QUIT_NAME = "HART:CATS:Quit"

_state = {"tries": 0, "hid": False, "chrome": False}
_MAX_TRIES = 40
_RETRY_MS = 500


def _failed(what, e):
    print("HART: CATS desk %s failed: %s" % (what, e))


def under_cats():
    cmd = System.getProperty("sun.java.command") or ""
    cfg = System.getProperty("org.jmri.Apps.configFilename") or ""
    if "cats.apps" in cmd or cfg.lower() == "catsconfig.xml":
        return True
    for window in Window.getWindows():
        try:
            if window.getClass().getName().startswith("cats."):
                return True
        except Exception as e:
            _failed("window class", e)
    return False


def frame_named(title):
    """JMRI's frame with this title, else the first plain Frame with it, else None."""
    frame = JmriJFrame.getFrame(title)
    if frame is not None:
        return frame
    for window in Window.getWindows():
        try:
            if isinstance(window, Frame) and window.getTitle() == title:
                return window
        except Exception as e:
            _failed("window title", e)
    return None


def hide_title(title):
    frame = frame_named(title)
    if frame is None:
        return False
    frame.setVisible(False)
    return True


class _Call(ActionListener):
    def __init__(self, fn):
        self.fn = fn

    def actionPerformed(self, event):
        self.fn()


def _quit_cats():
    from apps import Apps
    Apps.handleQuit()


def _show_jmri_help():
    from jmri.util import HelpUtil
    try:
        HelpUtil.displayHelpRef("index")
    except Exception:
        HelpUtil.displayHelpRef("package.apps.PanelPro.PanelPro")


def _has_named(container, name):
    if container is None:
        return False
    try:
        count = container.getComponentCount()
    except Exception:
        return False
    for i in range(count):
        try:
            if container.getComponent(i).getName() == name:
                return True
        except Exception as e:
            _failed("component name", e)
    return False


def _has_button_text(container, title):
    if container is None:
        return False
    want = (title or "").strip().lower()
    try:
        count = container.getComponentCount()
    except Exception:
        return False
    for i in range(count):
        try:
            label = container.getComponent(i).getText()
        except Exception:
            continue
        if label is not None and label.strip().lower() == want:
            return True
    return False


def _new_button(title, name, fn):
    btn = JButton(title)
    btn.setName(name)
    btn.setToolTipText(title)
    btn.addActionListener(_Call(fn))
    return btn


def add_script_style_buttons():
    """Help/Quit on the Apps button strip (bottom of CTC Panel)."""
    try:
        from apps import Apps
        space = Apps.buttonSpace()
    except Exception:
        return False
    if space is None:
        return False
    added = False
    if not _has_named(space, HELP_NAME) and not _has_button_text(space, "Help"):
        space.add(_new_button("Help", HELP_NAME, _show_jmri_help))
        added = True
    if not _has_named(space, QUIT_NAME) and not _has_button_text(space, "Quit"):
        space.add(_new_button("Quit", QUIT_NAME, _quit_cats))
        added = True
    if added:
        try:
            space.revalidate()
            space.repaint()
        except Exception as e:
            _failed("button strip repaint", e)
        print("HART: CATS Help/Quit on CTC Panel button strip")
    return True


def decorate_ctc_panel():
    if frame_named(CTC_PANEL) is None:
        return False
    return add_script_style_buttons()


def hide_cats_desk_windows():
    if not under_cats():
        return
    hidden = []

    def _hide():
        if hide_title(HART_RAILROAD):
            hidden.append(HART_RAILROAD)

    ThreadingUtil.runOnGUI(_hide)
    if hidden:
        print("HART: CATS control hid " + ", ".join(hidden))
        _state["hid"] = True


def _pass():
    if not under_cats():
        return
    if not _state["hid"]:
        if hide_title(HART_RAILROAD):
            _state["hid"] = True
            print("HART: CATS control hid " + HART_RAILROAD)
    ctc_ok = False
    try:
        ctc_ok = decorate_ctc_panel()
    except Exception as e:
        print("HART: CATS Help/Quit CTC Panel failed: %s" % e)
    if ctc_ok:
        _state["chrome"] = True
        if _state["hid"]:
            return
    _state["tries"] += 1
    if _state["tries"] >= _MAX_TRIES:
        if not _state["chrome"]:
            print("HART: CATS Help/Quit incomplete (CTC Panel button strip not found)")
        return
    ThreadingUtil.runOnGUIDelayed(_pass, _RETRY_MS)


try:
    if under_cats():
        hide_cats_desk_windows()
        ThreadingUtil.runOnGUI(_pass)
    else:
        hide_cats_desk_windows()
except Exception as e:
    print("HART: hide_cats_desk_windows failed: %s" % e)
