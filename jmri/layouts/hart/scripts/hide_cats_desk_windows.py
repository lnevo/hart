# JMRI Jython: under CATS, hide the PanelPro desks that duplicate the Digicon.
#
# LogixNG IQ:AUTO:0001 runs this at init (tables.xml). PanelPro leaves USS CTC
# and HART Railroad visible. CATS is a separate JVM (cats.apps.Crandic); the
# same Start Up still loads those panels, so hide them here.

from __future__ import print_function

from java.awt import Frame, Window
from java.lang import System

from jmri.util import ThreadingUtil
from jmri.util.swing import JmriJFrame

CATS_HIDE_TITLES = ("USS CTC", "HART Railroad")


def under_cats():
    cmd = System.getProperty("sun.java.command") or ""
    cfg = System.getProperty("org.jmri.Apps.configFilename") or ""
    if "cats.apps" in cmd or cfg.lower() == "catsconfig.xml":
        return True
    for window in Window.getWindows():
        try:
            if window.getClass().getName().startswith("cats."):
                return True
        except Exception:
            pass
    return False


def hide_title(title):
    frame = JmriJFrame.getFrame(title)
    if frame is not None:
        frame.setVisible(False)
        return True
    for window in Window.getWindows():
        try:
            if isinstance(window, Frame) and window.getTitle() == title:
                window.setVisible(False)
                return True
        except Exception:
            pass
    return False


def hide_cats_desk_windows():
    if not under_cats():
        return
    hidden = []

    def _hide():
        for title in CATS_HIDE_TITLES:
            if hide_title(title):
                hidden.append(title)

    ThreadingUtil.runOnGUI(_hide)
    if hidden:
        print("HART: CATS control — hid " + ", ".join(hidden))


hide_cats_desk_windows()
