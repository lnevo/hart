# Paint the "HART Railroad" Layout Editor panel into a PNG at 100%, then quit without storing.
import os, time, java, jmri
from java.awt.image import BufferedImage
from java.io import File
from javax.imageio import ImageIO
from javax.swing import SwingUtilities
from java.lang import Runnable

OUT = os.environ.get("HART_SNAPSHOT_OUT", "/tmp/hart_panel.png")
MARK = OUT + ".done"

def find():
    for p in jmri.InstanceManager.getDefault(jmri.jmrit.display.EditorManager).getList():
        if isinstance(p, jmri.jmrit.display.layoutEditor.LayoutEditor) and p.getLayoutName() == "HART Railroad":
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

deadline = time.time() + 120
while find() is None and time.time() < deadline:
    time.sleep(1)
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
