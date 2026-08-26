# JMRI jython — Signal Mast Logic Discover (PanelPro).
#
# Requires Layout Editor facing (signalAMast / eastboundsignalmast) already
# stored in tables, and Layout Block advanced routing (blockrouting=yes).
# Do not leave this on Start Up (slow; overwrites pairs).
#
# Must not block the JMRI startup/EDT thread: routingStablised uses a Swing
# timer, so sleeping on MainThread freezes PanelPro and routing never settles.
#
# Optional env (one-shot launcher):
#   HART_SML_DISCOVER_STORE=1   store tables.xml after pairs exist
#   HART_SML_DISCOVER_EXIT=1    System.exit after store/fail
#   HART_SML_DISCOVER_MARKER    write ok/fail status to this file
#   HART_SML_DISCOVER_FILE      tables path to store (default: loaded user file)

from __future__ import print_function

import os
import time
import traceback

import jmri
from java.beans import PropertyChangeListener
from java.lang import Runnable, System, Thread
from javax.swing import SwingUtilities
from jmri.util import FileUtil

STORE = os.environ.get("HART_SML_DISCOVER_STORE", "") == "1"
EXIT = os.environ.get("HART_SML_DISCOVER_EXIT", "") == "1"
MARKER = os.environ.get("HART_SML_DISCOVER_MARKER", "")
STORE_PATH = os.environ.get("HART_SML_DISCOVER_FILE", "")
WAIT_S = int(os.environ.get("HART_SML_DISCOVER_WAIT", "180"))


def _log(msg):
    print("discover_sml:", msg)
    try:
        import sys
        sys.stdout.flush()
    except Exception:
        pass


def _mark(status, detail=""):
    if not MARKER:
        return
    try:
        f = open(MARKER, "w")
        f.write(status + "\n" + detail + "\n")
        f.close()
    except Exception as e:
        _log("marker write failed: %s" % e)


def _finish(status, detail=""):
    _mark(status, detail)
    if EXIT:
        System.exit(0 if status == "ok" else 1)


def _sml_count(smlm):
    return len(list(smlm.getSignalMastLogicList()))


def _wait_until(pred, seconds, label):
    deadline = time.time() + seconds
    last = 0
    while time.time() < deadline:
        if pred():
            return True
        elapsed = int(time.time() - (deadline - seconds))
        if elapsed >= last + 5:
            last = elapsed
            _log("waiting for %s (%ss)" % (label, elapsed))
        Thread.sleep(250)
    _log("timeout waiting for %s" % label)
    return False


class _CompleteListener(PropertyChangeListener):
    def __init__(self, bucket):
        self.bucket = bucket

    def propertyChange(self, event):
        name = event.getPropertyName()
        if name in ("autoGenerateComplete", "autoSignalMastGenerateComplete"):
            self.bucket.append(name)


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


def _settle_unknown_turnouts():
    """Layout may be off; UNKNOWN points keep routing from ever stabilising."""
    mgr = jmri.InstanceManager.turnoutManagerInstance()
    n = 0
    for to in mgr.getNamedBeanSet():
        try:
            if to.getKnownState() != jmri.Turnout.UNKNOWN:
                continue
            if hasattr(to, "newKnownState"):
                to.newKnownState(jmri.Turnout.CLOSED)
            else:
                to.setCommandedState(jmri.Turnout.CLOSED)
            n += 1
        except Exception as e:
            _log("turnout %s: %s" % (to, e))
    _log("set Closed on %s UNKNOWN turnouts (layout-off settle)" % n)


def _store_tables():
    path = STORE_PATH
    if not path:
        path = FileUtil.getUserFilesPath() + "tables.xml"
    abs_path = FileUtil.getAbsoluteFilename(path) or path
    target = FileUtil.getFile(abs_path)
    cm = jmri.InstanceManager.getDefault(jmri.ConfigureManager)

    def go():
        return bool(cm.storeUser(target))

    if not _on_edt(go):
        raise RuntimeError("storeUser returned false for %s" % abs_path)
    _log("stored %s" % abs_path)


def _worker():
    try:
        _worker_body()
    except Exception as e:
        traceback.print_exc()
        _log("failed: %s" % e)
        _finish("fail", str(e))


def _worker_body():
    lbm = jmri.InstanceManager.getDefault(
        jmri.jmrit.display.layoutEditor.LayoutBlockManager
    )
    smlm = jmri.InstanceManager.getDefault(jmri.SignalMastLogicManager)
    before = _sml_count(smlm)
    _log("pairs before %s" % before)
    _log(
        "advanced routing %s stabilised %s"
        % (lbm.isAdvancedRoutingEnabled(), lbm.routingStablised())
    )

    if not lbm.isAdvancedRoutingEnabled():
        _log("enabling advanced routing")
        lbm.enableAdvancedRouting(True)

    try:
        _settle_unknown_turnouts()
    except Exception as e:
        _log("turnout settle skipped: %s" % e)

    if not _wait_until(lbm.routingStablised, WAIT_S, "layout-block routing"):
        _finish("fail", "routing not stabilised")
        return

    complete = []
    listener = _CompleteListener(complete)
    smlm.addPropertyChangeListener(listener)
    try:
        smlm.automaticallyDiscoverSignallingPairs()
    except Exception as e:
        _log("discover threw: %s" % e)
        _finish("fail", str(e))
        return

    def have_pairs():
        return bool(complete) or _sml_count(smlm) > before

    if not _wait_until(have_pairs, WAIT_S, "SML pairs"):
        after = _sml_count(smlm)
        _log("pairs after %s (no new pairs)" % after)
        _finish("fail", "pairs=%s" % after)
        return

    Thread.sleep(1500)
    try:
        smlm.initialise()
    except Exception as e:
        _log("initialise: %s" % e)

    after = _sml_count(smlm)
    dests = 0
    lines = []
    for sml in smlm.getSignalMastLogicList():
        src = sml.getSourceMast().getDisplayName()
        for dest in sml.getDestinationList():
            dests += 1
            if len(lines) < 40:
                lines.append("%s -> %s" % (src, dest.getDisplayName()))
    _log("pairs after %s sources, %s destinations" % (after, dests))
    for line in lines:
        _log(line)
    if dests > 40:
        _log("... %s more destinations not listed" % (dests - 40))

    if dests == 0:
        _finish("fail", "sources=%s dests=0" % after)
        return

    if STORE:
        try:
            _store_tables()
        except Exception as e:
            _log("store failed: %s" % e)
            _finish("fail", "store: %s" % e)
            return
    else:
        _log("Store tables.xml in PanelPro (quit CATS first).")

    _finish("ok", "sources=%s dests=%s" % (after, dests))


def main():
    t = Thread(_worker)
    t.setName("hart-sml-discover")
    t.setDaemon(True)
    t.start()
    _log("scheduled on background thread (UI stays live)")


try:
    main()
except Exception as e:
    traceback.print_exc()
    _log("failed: %s" % e)
    _finish("fail", str(e))
