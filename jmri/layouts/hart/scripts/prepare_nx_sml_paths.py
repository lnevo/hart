# JMRI jython — fill SML auto-turnouts so NX can throw with Digicon dests Disabled.
#
# SETUPSIGNALMASTLOGIC NX uses stored SML getAutoTurnouts when a dest exists.
# Digicon dests boot Enabled=no, so those lists stay empty after load (routing
# was not stable yet, and initialise never runs). East-end pairs all have
# stored dests; west Brick pairs without dests still use live connectivity.
#
# Do not enable dests. Do not command field turnouts or MQTT track/cmd.
# Not a Discover. Safe on PanelPro and CATS Start Up.

from __future__ import print_function

import traceback

import jmri
from java.lang import Runnable, Thread
from javax.swing import SwingUtilities

WAIT_S = 120


def _log(msg):
    print("prepare_nx_sml_paths: %s" % msg)
    try:
        import sys
        sys.stdout.flush()
    except Exception:
        pass


def _wait_until(pred, seconds, label):
    import time
    end = time.time() + seconds
    while time.time() < end:
        if pred():
            return True
        Thread.sleep(250)
    _log("timeout waiting for %s" % label)
    return False


def _on_layout(fn):
    holder = {"err": None, "result": None}

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


def _prepare():
    lbm = jmri.InstanceManager.getDefault(
        jmri.jmrit.display.layoutEditor.LayoutBlockManager
    )
    smlm = jmri.InstanceManager.getDefault(jmri.SignalMastLogicManager)
    if not lbm.isAdvancedRoutingEnabled():
        lbm.enableAdvancedRouting(True)
        _log("enabled advanced routing")
    if not _wait_until(lbm.routingStablised, WAIT_S, "layout-block routing"):
        _log("routing not stabilised; NX auto-turnouts may stay empty")
        return

    def go():
        n_sml = 0
        n_dest = 0
        n_fail = 0
        n_tos = 0
        for sml in smlm.getSignalMastLogicList():
            n_sml += 1
            try:
                sml.setupLayoutEditorDetails()
            except Exception as e:
                n_fail += 1
                src = sml.getSourceMast()
                name = src.getDisplayName() if src is not None else str(sml)
                _log("setupLayoutEditorDetails %s: %s" % (name, e))
            try:
                dests = sml.getDestinationList()
            except Exception:
                dests = None
            if dests is None:
                continue
            try:
                it = dests.iterator()
                while it.hasNext():
                    dest = it.next()
                    n_dest += 1
                    try:
                        autos = sml.getAutoTurnouts(dest)
                        if autos is None:
                            continue
                        try:
                            n_tos += autos.size()
                        except Exception:
                            n_tos += len(autos)
                    except Exception:
                        pass
            except Exception as e:
                _log("dest iterate: %s" % e)
        return n_sml, n_dest, n_fail, n_tos

    n_sml, n_dest, n_fail, n_tos = _on_layout(go)
    _log(
        "sml=%s dests=%s setup_fail=%s autoTurnouts=%s (dests stay Disabled)"
        % (n_sml, n_dest, n_fail, n_tos)
    )


def _worker():
    try:
        _prepare()
    except Exception:
        traceback.print_exc()
        _log("failed")


def main():
    t = Thread(_worker)
    t.setName("hart-prepare-nx-sml-paths")
    t.setDaemon(True)
    t.start()
    _log("scheduled after routing (does not enable SML dests)")


try:
    main()
except Exception:
    traceback.print_exc()
    _log("failed to schedule")
