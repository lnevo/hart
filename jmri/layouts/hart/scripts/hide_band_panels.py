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
# JMRI runs every LogixNG script in one shared Jython engine, right after hide_cats_desk_windows.py, whose module
# names (_state, _pass, ...) its queued retries look up again: so this file defines one name only, the class
# HartBandPanelHider, and keeps its state on the instance.

from java.awt import Frame, Window

from jmri.util import JmriJFrame, ThreadingUtil


class HartBandPanelHider(object):
    BAND_PANELS = ("Staging Level", "Main Level", "Upper Level")
    STABLE = 6
    MAX_TRIES = 120
    DELAY_MS = 500

    def __init__(self):
        self.tries = 0
        self.stable = 0
        self.said = False

    def frame(self, title):
        """The window titled `title`: JMRI's own frame, else any plain Frame with that title; None when not open."""
        found = JmriJFrame.getFrame(title)
        if found is not None:
            return found
        for window in Window.getWindows():
            try:
                if isinstance(window, Frame) and window.getTitle() == title:
                    return window
            except Exception:
                pass
        return None

    def run(self):
        found = 0
        for title in self.BAND_PANELS:
            frame = self.frame(title)
            if frame is None:
                continue
            found += 1
            if frame.isVisible():
                frame.setVisible(False)
        if found == len(self.BAND_PANELS):
            self.stable += 1
            if self.stable >= self.STABLE:
                if not self.said:
                    print("HART: hid the band panels " + ", ".join(self.BAND_PANELS))
                    self.said = True
                return
        else:
            self.stable = 0
        self.tries += 1
        if self.tries >= self.MAX_TRIES:
            missing = [t for t in self.BAND_PANELS if self.frame(t) is None]
            print("HART: band panels not all open after %d passes; never found: %s"
                  % (self.MAX_TRIES, ", ".join(missing) or "none"))
            return
        ThreadingUtil.runOnGUIDelayed(self.run, self.DELAY_MS)


try:
    ThreadingUtil.runOnGUI(HartBandPanelHider().run)
except Exception as e:
    print("HART: hide_band_panels failed: %s" % e)
