# JMRI Jython: under CATS, hide HART Railroad (the PanelPro layout).
#
# LogixNG IQ:AUTO:0001 runs this at init as IQC:AUTO:0004. IQC:0001–0003 already
# hide WiThrottle, USS CTC, and Dispatcher System on every host. PanelPro leaves
# HART Railroad up; CATS is a separate JVM (cats.apps.Crandic) and should not
# keep that geographic panel.

from __future__ import print_function

from java.awt import Frame, Window
from java.lang import System

from jmri.util import JmriJFrame, ThreadingUtil

HART_RAILROAD = "HART Railroad"


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
        if hide_title(HART_RAILROAD):
            hidden.append(HART_RAILROAD)

    ThreadingUtil.runOnGUI(_hide)
    if hidden:
        print("HART: CATS control — hid " + ", ".join(hidden))


hide_cats_desk_windows()
