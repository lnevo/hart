# JMRI jython — Entry/Exit Discover + Brick occupancy smoke (PanelPro).
#
# Requires ISNX sensors bound on HART Railroad and layout-block advanced routing.
# SML-mode pairs throw from stored SML auto-turnouts when a dest exists; Start Up
# prepare_nx_sml_paths.py fills those lists without enabling Digicon dests.
# Do not leave this on Start Up.
#
# Optional env (one-shot launcher):
#   HART_NX_DISCOVER_STORE=1   store tables.xml after pairs exist
#   HART_NX_DISCOVER_EXIT=1    System.exit after store/fail
#   HART_NX_DISCOVER_MARKER    write ok/fail status to this file
#   HART_NX_DISCOVER_FILE      tables path to store
#   HART_NX_SMOKE=1            occupancy simulation of Brick pairs (default)
#   HART_NX_THROW=1            actually set NX routes (commands MQTT turnouts)

from __future__ import print_function

import os
import sys
import time
import traceback

import jmri
from java.beans import PropertyChangeListener
from java.lang import Runnable, System, Thread
from javax.swing import SwingUtilities
from jmri.util import FileUtil

from jmri.jmrit.display.layoutEditor import LayoutBlockConnectivityTools
from jmri.jmrit.entryexit import EntryExitPairs

STORE = os.environ.get("HART_NX_DISCOVER_STORE", "") == "1"
EXIT = os.environ.get("HART_NX_DISCOVER_EXIT", "") == "1"
MARKER = os.environ.get("HART_NX_DISCOVER_MARKER", "")
STORE_PATH = os.environ.get("HART_NX_DISCOVER_FILE", "")
WAIT_S = int(os.environ.get("HART_NX_DISCOVER_WAIT", "180"))
SMOKE = os.environ.get("HART_NX_SMOKE", "1") == "1"
THROW = os.environ.get("HART_NX_THROW", "") == "1"
LOCK = os.environ.get("HART_NX_LOCK", "") == "1"
NX_TYPE = EntryExitPairs.FULLINTERLOCK if LOCK else EntryExitPairs.SETUPSIGNALMASTLOGIC

REQUIRED = (
    ("NX Mast 2L", "NX Mast 6LB"),
    ("NX Mast 4RA", "NX Mast 2L"),
)
OS100_SENSOR = "BS Switch 1"


NX_SENSORS = (
    "NX Mast 2L", "NX Mast 4RA", "NX Mast 4RB",
    "NX Mast 6LA", "NX Mast 6LB",
    "NX Mast 8RA", "NX Mast 8RB", "NX Mast 8LA", "NX Mast 8LB",
    "NX Mast 24RA", "NX Mast 24RB", "NX Mast 24L", "NX Mast 32R", "NX Mast 34R", "NX Mast 34L",
    "NX Mast 36RA", "NX Mast 36RB", "NX Mast 2036", "NX Mast 38LA", "NX Mast 38LB",
    "NX Mast 2035", "NX Mast 40LA", "NX Mast 40LB",
)


def _log(msg):
    print("discover_nx: %s" % msg)
    try:
        sys.stdout.flush()
    except Exception:
        pass
    try:
        System.out.flush()
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


class _CompleteListener(PropertyChangeListener):
    def __init__(self, bucket):
        self.bucket = bucket

    def propertyChange(self, event):
        if event.getPropertyName() in ("autoGenerateComplete", "autoSignalMastGenerateComplete"):
            self.bucket.append(event.getPropertyName())


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


def _settle_unknown_turnouts():
    # Paint KnownState only. Never setCommandedState / MQTT track/cmd.
    mgr = jmri.InstanceManager.turnoutManagerInstance()
    n = 0
    for to in mgr.getNamedBeanSet():
        try:
            if to.getKnownState() != jmri.Turnout.UNKNOWN:
                continue
            if hasattr(to, "newKnownState"):
                to.newKnownState(jmri.Turnout.CLOSED)
            elif hasattr(to, "setOwnState"):
                to.setOwnState(jmri.Turnout.CLOSED)
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


GEOGRAPHIC_PANEL_NAMES = ("HART Railroad", "HART", "My Layout")


def _layout(name=None):
    from jmri.jmrit.display import EditorManager

    em = jmri.InstanceManager.getDefault(EditorManager)
    names = list(GEOGRAPHIC_PANEL_NAMES)
    if name and name not in names:
        names.insert(0, name)
    elif name:
        names = [name] + [candidate for candidate in names if candidate != name]
    for candidate in names:
        for editor in em.getAll():
            title = editor.getTitle()
            layout_name = getattr(editor, "getLayoutName", lambda: "")()
            if title == candidate or layout_name == candidate:
                return editor
        found = em.get(candidate)
        if found is not None:
            return found
    return None


def _pair_count(eem):
    try:
        return len(list(eem.getEntryExitList()))
    except Exception:
        return 0


def _pair_bean(eem, uuid):
    for getter in ("getBySystemName", "getNamedBean", "getByUserName"):
        if not hasattr(eem, getter):
            continue
        try:
            bean = getattr(eem, getter)(uuid)
        except Exception:
            bean = None
        if bean is not None:
            return bean
    return None


def _pair_names(eem, panel):
    pairs = []
    uuids = list(eem.getEntryExitList() or [])
    _log("entryExitList %s" % len(uuids))
    for uuid in uuids:
        bean = _pair_bean(eem, uuid)
        if bean is None:
            pairs.append(str(uuid))
            continue
        label = bean.getDisplayName()
        if " to " in label and " -> " not in label:
            label = label.replace(" to ", " -> ")
        pairs.append(label)
    if pairs:
        return pairs
    try:
        sources = list(eem.getNxSource(panel) or [])
    except Exception as e:
        _log("getNxSource: %s" % e)
        return pairs
    for src in sources:
        try:
            dests = eem.getNxDestinationList(src, panel) or []
        except Exception:
            dests = []
        src_name = src.getDisplayName() if hasattr(src, "getDisplayName") else str(src)
        for dest in dests:
            dest_name = dest.getDisplayName() if hasattr(dest, "getDisplayName") else str(dest)
            pairs.append("%s -> %s" % (src_name, dest_name))
    return pairs


def _nx_name(label):
    label = (label or "").strip()
    if " to " in label and " -> " not in label:
        label = label.replace(" to ", " -> ", 1)
    if "(" in label:
        label = label.split(" (", 1)[0].strip()
    return label


def _has_required(pairs):
    have = set()
    for line in pairs:
        if " -> " in line:
            a, b = line.split(" -> ", 1)
        elif " to " in line:
            a, b = line.split(" to ", 1)
        else:
            continue
        have.add((_nx_name(a), _nx_name(b)))
    missing = [p for p in REQUIRED if p not in have]
    return missing, have


def _sensor(name):
    return jmri.InstanceManager.sensorManagerInstance().getSensor(name)


def _set_sensor(name, state, known=True):
    sensor = _sensor(name)
    if sensor is None:
        raise RuntimeError("missing sensor %s" % name)
    if known and hasattr(sensor, "setKnownState"):
        sensor.setKnownState(state)
    else:
        sensor.setState(state)
    return sensor


def _clear_all_occupancy():
    mgr = jmri.InstanceManager.sensorManagerInstance()
    cleared = 0
    for sensor in mgr.getNamedBeanSet():
        user = sensor.getUserName() or ""
        sysn = sensor.getSystemName() or ""
        if not (user.startswith("Block ") or user.startswith("BS ") or sysn.startswith("M2S")):
            continue
        try:
            if sensor.getKnownState() != jmri.Sensor.INACTIVE:
                sensor.setKnownState(jmri.Sensor.INACTIVE)
                cleared += 1
        except Exception:
            pass
    _log("cleared %s occupancy sensors to INACTIVE" % cleared)
    return cleared


def _set_occupancy(active):
    state = jmri.Sensor.ACTIVE if active else jmri.Sensor.INACTIVE
    sensor = _set_sensor(OS100_SENSOR, state)
    _log("%s %s" % (OS100_SENSOR, "ACTIVE" if active else "INACTIVE"))
    return sensor


def _dump_bindings(panel):
    found = []
    missing = []
    for name in NX_SENSORS:
        sensor = _sensor(name)
        if sensor is None:
            missing.append(name)
        else:
            found.append("%s=%s" % (name, sensor.getSystemName()))
    _log("nx sensors present %s missing %s" % (len(found), missing or "none"))
    if panel is not None and hasattr(panel, "getLayoutTurnouts"):
        bound = 0
        for turnout in panel.getLayoutTurnouts():
            for letter, getter in (
                ("A", "getSensorA"),
                ("B", "getSensorB"),
                ("C", "getSensorC"),
                ("D", "getSensorD"),
            ):
                try:
                    bean = getattr(turnout, getter)()
                except Exception:
                    bean = None
                if bean is not None:
                    bound += 1
                    _log("turnout %s sensor%s=%s" % (turnout.getId(), letter, bean.getDisplayName()))
        _log("layout turnout NX bindings %s" % bound)


def _check_path(src_name, dest_name):
    src = _sensor(src_name)
    dest = _sensor(dest_name)
    if src is None or dest is None:
        return False, "missing %s or %s" % (src_name, dest_name)
    lbm = jmri.InstanceManager.getDefault(
        jmri.jmrit.display.layoutEditor.LayoutBlockManager
    )
    tools = lbm.getLayoutBlockConnectivityTools()
    try:
        ok = tools.checkValidDest(src, dest, LayoutBlockConnectivityTools.Routing.SENSORTOSENSOR)
        return bool(ok), "checkValidDest=%s" % ok
    except Exception as e:
        return False, str(e)


def _unhold_ctc():
    n = 0
    mgr = jmri.InstanceManager.getDefault(jmri.SignalMastManager)
    for mast in mgr.getNamedBeanSet():
        name = mast.getDisplayName()
        if name.split(":")[-1] in (
            "Mast 2L", "Mast 4RA", "Mast 4RB", "Mast 6LA", "Mast 6LB",
            "Mast 8RA", "Mast 8RB", "Mast 8LA", "Mast 8LB",
            "Mast 24RA", "Mast 24RB", "Mast 24L", "Mast 32R", "Mast 34R", "Mast 34L",
            "Mast 36RA", "Mast 36RB", "Mast 2036", "Mast 38LA", "Mast 38LB",
            "Mast 2035", "Mast 40LA", "Mast 40LB",
        ) or name in (
            "Mast 2L", "Mast 4RA", "Mast 4RB", "Mast 6LA", "Mast 6LB",
            "Mast 8RA", "Mast 8RB", "Mast 8LA", "Mast 8LB",
            "Mast 24RA", "Mast 24RB", "Mast 24L", "Mast 32R", "Mast 34R", "Mast 34L",
            "Mast 36RA", "Mast 36RB", "Mast 2036", "Mast 38LA", "Mast 38LB",
            "Mast 2035", "Mast 40LA", "Mast 40LB",
        ):
            try:
                if mast.getHeld():
                    mast.setHeld(False)
                    n += 1
            except Exception:
                pass
    _log("unheld %s CTC masts" % n)


def _add_pair(eem, panel, src_name, dest_name):
    src = _sensor(src_name)
    dest = _sensor(dest_name)
    if src is None or dest is None:
        return False, "missing %s or %s" % (src_name, dest_name)
    try:
        eem.addNXSourcePoint(src, panel)
    except Exception as e:
        _log("addNXSourcePoint %s: %s" % (src_name, e))
    try:
        already = False
        try:
            already = bool(eem.getUniqueId(src, panel, dest))
        except Exception:
            already = False
        if not already:
            eem.addNXDestination(src, dest, panel)
        eem.setEntryExitType(src, panel, dest, NX_TYPE)
        return True, "exists" if already else "added"
    except Exception as e:
        return False, str(e)


def _add_valid_pairs(eem, panel):
    added = 0
    failed = 0
    for src_name in NX_SENSORS:
        for dest_name in NX_SENSORS:
            if src_name == dest_name:
                continue
            ok, detail = _check_path(src_name, dest_name)
            if not ok:
                continue
            done, add_detail = _add_pair(eem, panel, src_name, dest_name)
            if done:
                added += 1
            else:
                failed += 1
                _log("add %s -> %s failed: %s (%s)" % (src_name, dest_name, add_detail, detail))
    _log("added %s valid NX pairs (%s failed)" % (added, failed))
    return added


def _ensure_required(eem, panel, pairs):
    missing, _have = _has_required(pairs)
    if not missing:
        return []
    _log("adding required pairs that discover missed: %s" % (missing,))
    still = []
    for src, dest in missing:
        ok, detail = _add_pair(eem, panel, src, dest)
        if not ok:
            still.append("%s -> %s (%s)" % (src, dest, detail))
    return still


def _smoke(eem, panel, pairs):
    missing, _have = _has_required(pairs)
    if missing:
        return False, "required pairs missing: %s" % missing

    _unhold_ctc()
    _clear_all_occupancy()
    Thread.sleep(500)

    results = []
    for src, dest in REQUIRED:
        ok, detail = _check_path(src, dest)
        results.append("%s -> %s clear:%s (%s)" % (src, dest, ok, detail))
        if not ok:
            return False, "; ".join(results)

    _set_occupancy(True)
    Thread.sleep(400)
    blocked_ok, blocked_detail = _check_path("NX Mast 2L", "NX Mast 6LB")
    results.append("Mast 2L -> Mast 6LB occupied:%s (%s)" % (blocked_ok, blocked_detail))
    _set_occupancy(False)
    if blocked_ok:
        _log("occupied OS 1 still reported a valid path; NX GUI should still refuse")

    if THROW:
        uuid = None
        for item in list(eem.getEntryExitList() or []):
            bean = eem.getBySystemName(item) or eem.getNamedBean(item)
            if bean is None:
                continue
            label = bean.getDisplayName()
            if "Mast 2L" in label and "Mast 6LB" in label:
                uuid = item
                break
        if uuid is None:
            return False, "no uniqueid for Mast 2L->Mast 6LB"
        _log("setSingleSegmentRoute %s" % uuid)
        eem.setSingleSegmentRoute(str(uuid))
        Thread.sleep(1500)
        results.append("threw Mast 2L->Mast 6LB")
        try:
            eem.cancelInterlock(str(uuid))
        except Exception as e:
            _log("cancelInterlock: %s" % e)

    return True, "; ".join(results)


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
    eem = jmri.InstanceManager.getDefault(EntryExitPairs)
    panel = _layout()
    if panel is None:
        _finish("fail", "HART Railroad editor not found")
        return

    # Keep SML aspects until NX locking is wanted (Tools → Entry Exit).
    try:
        eem.setAbsSignalMode(not LOCK)
        _log("ABS signal mode %s (lock=%s)" % ("off" if LOCK else "on", LOCK))
    except Exception as e:
        _log("setAbsSignalMode: %s" % e)

    before = _pair_count(eem)
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

    _dump_bindings(panel)
    _clear_all_occupancy()
    Thread.sleep(400)

    complete = []
    listener = _CompleteListener(complete)
    eem.addPropertyChangeListener(listener)
    try:
        eem.automaticallyDiscoverEntryExitPairs(panel, NX_TYPE)
    except Exception as e:
        _log("discover threw: %s" % e)
        _finish("fail", str(e))
        return

    def have_pairs():
        return _pair_count(eem) > before

    if not _wait_until(have_pairs, 30, "NX auto-generate"):
        _log("auto-generate produced %s pairs; adding from connectivity" % _pair_count(eem))
        _add_valid_pairs(eem, panel)

    Thread.sleep(500)
    pairs = [p.replace(" to ", " -> ") for p in _pair_names(eem, panel)]
    still = _ensure_required(eem, panel, pairs)
    pairs = [p.replace(" to ", " -> ") for p in _pair_names(eem, panel)]
    _log("pairs after %s" % len(pairs))
    for line in pairs[:80]:
        _log(line)
    if len(pairs) > 80:
        _log("... %s more pairs not listed" % (len(pairs) - 80))

    missing, _have = _has_required(pairs)
    if missing or still:
        _log("required pairs missing: %s still=%s" % (missing, still))
        _finish("fail", "missing %s" % (missing or still))
        return

    smoke_detail = "skip"
    if SMOKE:
        ok, smoke_detail = _smoke(eem, panel, [p.replace(" to ", " -> ") for p in pairs])
        _log("smoke %s" % smoke_detail)
        if not ok:
            _finish("fail", smoke_detail)
            return

    if STORE:
        try:
            eem.setAbsSignalMode(not LOCK)
        except Exception:
            pass
        try:
            _store_tables()
        except Exception as e:
            traceback.print_exc()
            _log("store failed: %s" % e)
            _finish("fail", "store: %s" % e)
            return
    else:
        _log("Store tables.xml in PanelPro (quit CATS first).")

    _finish("ok", "pairs=%s smoke=%s" % (len(pairs), smoke_detail))


def main():
    t = Thread(_worker)
    t.setName("hart-nx-discover")
    t.setDaemon(True)
    t.start()
    _log("scheduled on background thread (UI stays live)")


try:
    main()
except Exception as e:
    traceback.print_exc()
    _log("failed: %s" % e)
    _finish("fail", str(e))
