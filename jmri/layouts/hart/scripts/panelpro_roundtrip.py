# JMRI jython - a PanelPro round trip of the generated tables.xml (ADR-029 gate 2), run by
# tools/hosts/run_panelpro_roundtrip.sh. Never put it on Start Up by hand.
#
# Waits for the "HART Railroad" panel, waits until every block's path count is steady (JMRI derives the
# block paths from the panel on load), writes one line per block (system name, user name, path count),
# stores the configuration and panels as the PanelPro menu "Store Configuration and Panels" does
# (ConfigureManager.storeUser), writes the marker and exits.
#
# Environment (set by the wrapper):
#   HART_ROUNDTRIP_STORE    the file to store to (a temporary file, never the repo's tables.xml)
#   HART_ROUNDTRIP_PATHS    the block path counts (tab-separated)
#   HART_ROUNDTRIP_MARKER   "ok" or "fail" on the first line, the detail on the second
#   HART_ROUNDTRIP_WAIT     seconds to wait for the panel and steady paths (default 180)

import os
import time
import traceback

import jmri
from java.io import File
from java.lang import Runnable, System, Thread
from javax.swing import SwingUtilities

PANEL = "HART Railroad"
STORE = os.environ.get("HART_ROUNDTRIP_STORE", "")
PATHS = os.environ.get("HART_ROUNDTRIP_PATHS", "")
MARKER = os.environ.get("HART_ROUNDTRIP_MARKER", "")
WAIT_S = int(os.environ.get("HART_ROUNDTRIP_WAIT", "180"))
STEADY_S = 10     # the path counts must stay the same this long


def _log(msg):
    print("panelpro_roundtrip: %s" % (msg,))


def _finish(status, detail):
    if MARKER:
        f = open(MARKER, "w")
        f.write(status + "\n" + detail + "\n")
        f.close()
    System.exit(0 if status == "ok" else 1)


def _on_edt(fn):
    holder = {"result": None, "err": None}

    class Go(Runnable):
        def run(self):
            try:
                holder["result"] = fn()
            except Exception as e:
                holder["err"] = e

    SwingUtilities.invokeAndWait(Go())
    if holder["err"] is not None:
        raise holder["err"]
    return holder["result"]


def _path_counts():
    bm = jmri.InstanceManager.getDefault(jmri.BlockManager)
    return [(b.getSystemName(), b.getUserName() or "", len(b.getPaths())) for b in bm.getNamedBeanSet()]


def _worker():
    try:
        deadline = time.time() + WAIT_S
        while jmri.util.JmriJFrame.getFrame(PANEL) is None:
            if time.time() > deadline:
                _finish("fail", "no %s panel after %ss" % (PANEL, WAIT_S))
                return
            Thread.sleep(1000)
        last, steady_since = None, time.time()
        while True:
            counts = _path_counts()
            if counts != last:
                last, steady_since = counts, time.time()
            elif time.time() - steady_since >= STEADY_S:
                break
            if time.time() > deadline:
                _finish("fail", "block paths still changing after %ss" % WAIT_S)
                return
            Thread.sleep(1000)
        f = open(PATHS, "w")
        for name, user, n in last:
            f.write("%s\t%s\t%d\n" % (name, user, n))
        f.close()
        cm = jmri.InstanceManager.getDefault(jmri.ConfigureManager)
        if not _on_edt(lambda: bool(cm.storeUser(File(STORE)))):
            _finish("fail", "storeUser returned false for %s" % STORE)
            return
        _log("stored %s" % STORE)
        _finish("ok", "blocks=%d paths=%d" % (len(last), sum(n for _a, _b, n in last)))
    except Exception as e:
        traceback.print_exc()
        _finish("fail", str(e))


if not (STORE and PATHS and MARKER):
    _log("HART_ROUNDTRIP_STORE, _PATHS and _MARKER must be set (run tools/hosts/run_panelpro_roundtrip.sh)")
else:
    t = Thread(_worker)
    t.setName("hart-panelpro-roundtrip")
    t.start()
