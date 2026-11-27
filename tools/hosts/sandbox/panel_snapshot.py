# Paint the "HART Railroad" Layout Editor panel into a PNG at 100%, then quit without storing.
# OUT.done holds the size painted; on any failure OUT.error holds the reason (panel_snapshot.sh prints it) and
# PanelPro exits 1, so the wrapper never waits on a PanelPro that is left open.
import os, time, java, jmri
from java.awt.image import BufferedImage
from java.io import File
from javax.imageio import ImageIO
from javax.swing import SwingUtilities
from java.lang import Runnable

OUT = os.environ.get("HART_SNAPSHOT_OUT", "/tmp/hart_panel.png")
MARK = OUT + ".done"
ERROR = OUT + ".error"
PANEL = "HART Railroad"
WAIT = 120              # seconds for the panel to appear
MARGIN = 200            # pixels the window is grown past the panel


class SnapshotError(Exception):
    """The panel cannot be painted; the message goes to OUT.error."""


def write(path, text):
    with open(path, "w") as f:
        f.write(text)


def find():
    for p in jmri.InstanceManager.getDefault(jmri.jmrit.display.EditorManager).getList():
        if isinstance(p, jmri.jmrit.display.layoutEditor.LayoutEditor) and p.getLayoutName() == PANEL:
            return p
    return None


def wait_for_panel():
    deadline = time.time() + WAIT
    while time.time() < deadline:
        p = find()
        if p is not None:
            return p
        time.sleep(1)
    p = find()
    if p is None:
        raise SnapshotError('no Layout Editor panel "%s" appeared within %d s; nothing painted' % (PANEL, WAIT))
    return p


def fit(p):
    """Grow the panel's window to hold the whole panel (track is painted only inside the window); its target panel
    and size."""
    tp = p.getTargetPanel()
    w, h = int(tp.getPreferredSize().width), int(tp.getPreferredSize().height)
    if w <= 0 or h <= 0:
        raise SnapshotError('panel "%s" has no size to paint (%dx%d)' % (PANEL, w, h))
    frame = p.getTargetFrame()
    frame.setSize(w + MARGIN, h + MARGIN)
    frame.validate()
    return tp, w, h


class OnEdt(Runnable):
    """Run fn(panel) on the Swing thread; an error there is kept for the script thread to report."""
    def __init__(self, fn, panel):
        self.fn, self.panel, self.error = fn, panel, None

    def run(self):
        try:
            self.fn(self.panel)
        except (Exception, java.lang.Throwable) as exc:   # Python and Java errors alike reach OUT.error
            self.error = exc


def on_edt(fn, panel):
    job = OnEdt(fn, panel)
    SwingUtilities.invokeAndWait(job)
    if job.error is not None:
        raise SnapshotError("%s failed: %s" % (fn.__name__, job.error))


def grow(p):
    fit(p)


def paint(p):
    p.setZoom(1.0)
    tp, w, h = fit(p)
    tp.setSize(w, h)
    img = BufferedImage(w, h, BufferedImage.TYPE_INT_RGB)
    g = img.createGraphics()
    try:
        tp.paint(g)
    finally:
        g.dispose()
    if not ImageIO.write(img, "png", File(OUT)):
        raise SnapshotError("no PNG writer for %s" % OUT)
    write(MARK, "%dx%d\n" % (w, h))


try:
    panel = wait_for_panel()
    time.sleep(15)          # let icons, lamps and labels finish loading
    on_edt(grow, panel)
    time.sleep(5)
    on_edt(paint, panel)
except (Exception, java.lang.Throwable) as exc:
    msg = str(exc)
    print(msg)
    write(ERROR, msg + "\n")
    java.lang.System.exit(1)
time.sleep(1)
java.lang.System.exit(0)
