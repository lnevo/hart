# Paint the "HART Railroad" Layout Editor panel into a PNG at 100%, then quit without storing.
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

def find():
    for p in jmri.InstanceManager.getDefault(jmri.jmrit.display.EditorManager).getList():
        if isinstance(p, jmri.jmrit.display.layoutEditor.LayoutEditor) and p.getLayoutName() == PANEL:
            return p
    return None

class Paint(Runnable):
    def run(self):
        p = find()
        p.setZoom(1.0)
        tp = p.getTargetPanel()
        w, h = int(tp.getPreferredSize().width), int(tp.getPreferredSize().height)
        frame = p.getTargetFrame()
        frame.setSize(w + 200, h + 200)        # track is painted only inside the window: make it hold the whole panel
        frame.validate()
        tp.setSize(w, h)
        img = BufferedImage(w, h, BufferedImage.TYPE_INT_RGB)
        g = img.createGraphics()
        tp.paint(g)
        g.dispose()
        ImageIO.write(img, "png", File(OUT))
        open(MARK, "w").write("%dx%d\n" % (w, h))

WAIT = 120              # seconds for the panel to appear
deadline = time.time() + WAIT
while find() is None and time.time() < deadline:
    time.sleep(1)
if find() is None:      # nothing to paint: say so in OUT.error, which panel_snapshot.sh prints
    msg = 'no Layout Editor panel "%s" appeared within %d s; nothing painted' % (PANEL, WAIT)
    print(msg)
    open(ERROR, "w").write(msg + "\n")
    java.lang.System.exit(1)
time.sleep(15)          # let icons, lamps and labels finish loading
class Grow(Runnable):
    def run(self):
        p = find()
        frame = p.getTargetFrame()
        tp = p.getTargetPanel()
        frame.setSize(int(tp.getPreferredSize().width) + 200, int(tp.getPreferredSize().height) + 200)
        frame.validate()
SwingUtilities.invokeAndWait(Grow())
time.sleep(5)
SwingUtilities.invokeAndWait(Paint())
time.sleep(1)
java.lang.System.exit(0)
