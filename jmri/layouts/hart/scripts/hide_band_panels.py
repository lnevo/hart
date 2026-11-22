# JMRI Jython: hide the band panels (Staging Level, Main Level, Upper Level) once PanelPro or CATS has opened them.
#
# LogixNG IQ:AUTO:0001 ("Hide windows on start") runs this at init as IQC:AUTO:0005. The band panels are reference
# copies of HART Railroad, one per level (tools/schematic/band_panels.py, owner 2026-11-22). A LogixNG Window
# Management Hide fires before the Layout Editor load makes the windows visible, so this script retries: every
# half second it hides each band window it finds, and stops once all three have been there and hidden for
# STABLE passes in a row (a window shown again in that time is hidden again). It gives up after MAX_TRIES passes
# and says which windows it never found. It touches no bean and commands nothing on the layout.
#
# The names follow hartlib.tables.BAND_PANEL_NAMES (Jython cannot import hartlib; test_hide_band_panels.py holds
# the two equal).
#
# MUST stay ASCII, and no "from __future__ import print_function" (hide_cats_desk_windows.py says why).

from java.awt import Frame, Window

from jmri.util import JmriJFrame, ThreadingUtil

BAND_PANELS = ("Staging Level", "Main Level", "Upper Level")
STABLE = 6
MAX_TRIES = 120
DELAY_MS = 500

_state = {"tries": 0, "stable": 0, "said": False}


def band_frame(title):
    """The window titled `title`: JMRI's own frame, else any plain Frame with that title; None when not open."""
    frame = JmriJFrame.getFrame(title)
    if frame is not None:
        return frame
    for window in Window.getWindows():
        try:
            if isinstance(window, Frame) and window.getTitle() == title:
                return window
        except Exception:
            pass
    return None


def _pass():
    found = 0
    for title in BAND_PANELS:
        frame = band_frame(title)
        if frame is None:
            continue
        found += 1
        if frame.isVisible():
            frame.setVisible(False)
    if found == len(BAND_PANELS):
        _state["stable"] += 1
        if _state["stable"] >= STABLE:
            if not _state["said"]:
                print("HART: hid the band panels " + ", ".join(BAND_PANELS))
                _state["said"] = True
            return
    else:
        _state["stable"] = 0
    _state["tries"] += 1
    if _state["tries"] >= MAX_TRIES:
        missing = [t for t in BAND_PANELS if band_frame(t) is None]
        print("HART: band panels not all open after %d passes; never found: %s"
              % (MAX_TRIES, ", ".join(missing) or "none"))
        return
    ThreadingUtil.runOnGUIDelayed(_pass, DELAY_MS)


try:
    ThreadingUtil.runOnGUI(_pass)
except Exception as e:
    print("HART: hide_band_panels failed: %s" % e)
