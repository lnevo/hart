# JMRI jython — dump runtime SML criteria (auto blocks/turnouts per destination).
#
# One-shot diagnostic: waits for layout-block routing, initialises SML, then
# writes every source->dest with JMRI's computed turnout settings and block
# lists to HART_SML_DUMP_FILE. Marker/exit env identical to discover_sml.py.

from __future__ import print_function

import os
import time
import traceback

import jmri
from java.lang import System, Thread

MARKER = os.environ.get("HART_SML_DISCOVER_MARKER", "")
DUMP = os.environ.get("HART_SML_DUMP_FILE", "/tmp/hart_sml_criteria.txt")
WAIT_S = int(os.environ.get("HART_SML_DISCOVER_WAIT", "180"))
EXIT = os.environ.get("HART_SML_DISCOVER_EXIT", "") == "1"


def _log(msg):
    print("dump_sml_criteria:", msg)


def _finish(status, detail=""):
    if MARKER:
        try:
            f = open(MARKER, "w")
            f.write(status + "\n" + detail + "\n")
            f.close()
        except Exception as e:
            _log("marker write failed: %s" % e)
    if EXIT:
        System.exit(0 if status == "ok" else 1)


def _wait_until(pred, seconds, label):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if pred():
            return True
        Thread.sleep(250)
    _log("timeout waiting for %s" % label)
    return False


def _settle_unknown_turnouts():
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
    _log("settled %s UNKNOWN turnouts" % n)


def _state_name(v):
    return {2: "closed", 4: "thrown"}.get(v, str(v))


def _fmt_collection(obj, state_fn=None):
    out = []
    try:
        # map-like (Hashtable / LinkedHashMap)
        it = obj.entrySet().iterator()
        while it.hasNext():
            e = it.next()
            out.append("%s=%s" % (e.getKey().getDisplayName(), _state_name(e.getValue())))
        return out
    except Exception:
        pass
    try:
        for item in obj:
            name = item.getDisplayName() if hasattr(item, "getDisplayName") else str(item)
            if state_fn is not None:
                try:
                    out.append("%s=%s" % (name, _state_name(state_fn(item))))
                    continue
                except Exception:
                    pass
            out.append(name)
    except Exception as e:
        out.append("<unreadable: %s>" % e)
    return out


def _worker():
    try:
        _worker_body()
    except Exception as e:
        traceback.print_exc()
        _finish("fail", str(e))


def _worker_body():
    lbm = jmri.InstanceManager.getDefault(
        jmri.jmrit.display.layoutEditor.LayoutBlockManager
    )
    smlm = jmri.InstanceManager.getDefault(jmri.SignalMastLogicManager)

    if not lbm.isAdvancedRoutingEnabled():
        lbm.enableAdvancedRouting(True)
    _settle_unknown_turnouts()
    if not _wait_until(lbm.routingStablised, WAIT_S, "routing"):
        _finish("fail", "routing not stabilised")
        return

    try:
        smlm.initialise()
    except Exception as e:
        _log("initialise: %s" % e)
    Thread.sleep(3000)

    lines = []
    ndest = 0
    for sml in smlm.getSignalMastLogicList():
        src = sml.getSourceMast().getDisplayName()
        for dest in sml.getDestinationList():
            ndest += 1
            lines.append("PAIR: %s -> %s" % (src, dest.getDisplayName()))
            try:
                lines.append("  useLE=%s active=%s enabled=%s" % (
                    sml.useLayoutEditor(dest), sml.isActive(dest), sml.isEnabled(dest)))
            except Exception as e:
                lines.append("  flags error: %s" % e)
            for label, getter, state_fn in (
                ("autoTurnouts", "getAutoTurnouts",
                 lambda t, s=sml, d=dest: s.getAutoTurnoutState(t, d)),
                ("autoBlocks", "getAutoBlocks", None),
                ("turnouts", "getTurnouts", None),
                ("blocks", "getBlocks", None),
            ):
                try:
                    obj = getattr(sml, getter)(dest)
                    lines.append("  %s: %s" % (label, ", ".join(_fmt_collection(obj, state_fn)) or "-"))
                except Exception as e:
                    lines.append("  %s error: %s" % (label, e))
    import codecs
    f = codecs.open(DUMP, "w", "utf-8")
    f.write(u"\n".join(u"%s" % ln for ln in lines) + u"\n")
    f.close()
    _log("wrote %s (%s dests)" % (DUMP, ndest))
    _finish("ok", "dests=%s" % ndest)


def main():
    t = Thread(_worker)
    t.setName("hart-sml-dump")
    t.setDaemon(True)
    t.start()
    _log("scheduled on background thread")


try:
    main()
except Exception as e:
    traceback.print_exc()
    _finish("fail", str(e))
