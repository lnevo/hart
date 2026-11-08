# cs105_roster_sync.py - push JMRI roster entries into the TCS CS-105 train roster.
#
# Runs inside the Pi's JMRI (Jython 2.7) because that host owns the LCC
# connection (TCS LCC-Buffer on ttyACM0). Normally dropped in through
# jmri_cmd_watcher.py by tools/ops/cs105_roster_sync.sh; it also works from
# PanelPro's Scripting menu. Under CPython 3 it only plans from the roster
# files (no CS-105 access); that path is what the unit tests cover.
#
# Per roster entry (DCC address + long/short flag):
#   1. Train node ID = 06.01.00.00.aa.aa (short) or 06.01.00.00.(C0|hi).lo
#      (long), the same mapping JMRI's OlcbThrottle and TcsUploadAction use.
#   2. If the CS-105 has no such node: send a Train Search "Identify Producer"
#      with the Allocate flag (OpenLCB Train Search Protocol, 2024-07-22).
#      The CS-105 then creates the virtual train node itself.
#   3. Write the train node's CDI: Train.Name (new nodes only, unless
#      CS105_RENAME), Train.User Description (roster comment) and
#      Train.Functions(n).Display / Momentary / Description, the way
#      jmri.jmrit.symbolicprog.TcsUploadAction does for one entry.
#      Functions(n) is DCC function F(n+1); F0 is the headlight group.
#      Consist Behavior is left alone (JMRI derives it from decoder CVs).
#
# Config: set these names in the exec globals (the shell wrapper prepends them):
#   CS105_APPLY=True        write to the CS-105 (default False = plan only)
#   CS105_ONLY="1827,572"   restrict to these roster IDs
#   CS105_RENAME=True       also set Train.Name on nodes that already exist
#   CS105_NAMES="road"      name trains "<road name> <road number>" instead of
#                           the roster ID (default "id")
#
# Never commands track or publishes track/cmd. Writes go only to CS-105 train
# node configuration memory.

import os
import sys
import time
import xml.etree.ElementTree as ET

SEARCH_PREFIX = (0x09, 0x00, 0x99, 0xFF)
FLAG_ALLOCATE = 0x80
FLAG_EXACT = 0x40
FLAG_ADDRESS_ONLY = 0x20
PROTO_DCC = 0x08
DCC_LONG = 0x04
TRAIN_NODE_PREFIX = "06.01.00.00"
N_FUNCTIONS = 28  # Train.Functions(0..27) = F1..F28, as in the CS-105 CDI

# Label text -> CS-105 "Display" icon code. Copied from JMRI 5.16
# jmri.jmrit.symbolicprog.TcsExportAction.intFromFunctionString so both tools
# agree. Unknown text -> 0 and the text is sent as the Description instead.
DISPLAY_CODES = {
    "unassigned": 0,
    "headlight": 1, "bell": 13, "horn": 14, "whistle": 15, "pantograph": 11,
    "smoke": 10, "engine": 4, "light": 74, "coupler clank": 28, "couple": 122,
    "uncouple": 9,
    "shunting mode": 7, "momentum": 8,
    "brake": 57, "brake release": 200, "dynamic brake": 41,
    "manual notch down": 31, "manual notch up": 30, "reverser": 69, "mute": 100,
    "far light": 12, "cab light": 3, "ditch lights": 48, "step lights": 98,
    "tail lights": 62, "switching lights": 58, "dimmer": 51, "interior lights": 2,
    "air compressor": 42, "air pump": 45, "injector": 60, "exhaust fan": 108,
    "radiator fan": 17, "steam generator": 66, "blower": 105, "blow down": 56,
    "safety": 38, "sanding": 55, "ash dump": 88, "shoveling": 18, "water fill": 35,
    "long whistle": 103, "short whistle": 64, "doppler horn": 63,
    "curve squeal": 36, "brake squeal": 21, "announce": 6, "cab chatter": 27,
}


def display_code(label):
    """CS-105 Display code for a roster function label (0 = plain text)."""
    if label is None:
        return 0
    return DISPLAY_CODES.get(label.strip().lower(), 0)


def _dotted(byte_values):
    return ".".join("%02X" % b for b in byte_values)


def train_node_id(address, is_long):
    """Dotted node ID of the CS-105 virtual train node for a DCC address."""
    address = int(address)
    if is_long:
        hi = 0xC0 | ((address >> 8) & 0x3F)
    else:
        hi = 0
    return "%s.%02X.%02X" % (TRAIN_NODE_PREFIX, hi, address & 0xFF)


def search_event(address, is_long, allocate=True):
    """Train Search event ID (dotted) for a DCC address.

    Digits are packed as 6 BCD nibbles, left aligned and padded with 0xF.
    Flags: Exact + Address-only + DCC, plus Allocate and Force-long as asked.
    """
    digits = str(int(address))
    if not 1 <= len(digits) <= 6:
        raise ValueError("address out of range: %r" % (address,))
    nibbles = [int(d) for d in digits] + [0xF] * (6 - len(digits))
    query = [(nibbles[i] << 4) | nibbles[i + 1] for i in (0, 2, 4)]
    flags = FLAG_EXACT | FLAG_ADDRESS_ONLY | PROTO_DCC
    if allocate:
        flags |= FLAG_ALLOCATE
    if is_long:
        flags |= DCC_LONG
    return _dotted(list(SEARCH_PREFIX) + query + [flags])


def is_train_node(node_id):
    return str(node_id).upper().startswith(TRAIN_NODE_PREFIX + ".")


def load_entry(path, index_attrs=None):
    """One roster entry from its locomotive file as a plain dict."""
    root = ET.parse(path).getroot()
    loco = root.find("locomotive")
    if loco is None:
        raise ValueError("no <locomotive> in %s" % path)
    attrs = dict(index_attrs or {})
    attrs.update(loco.attrib)
    address = int(attrs.get("dccAddress") or 0)
    dcc = loco.find("locoaddress/dcclocoaddress")
    if dcc is not None and dcc.get("longaddress") is not None:
        is_long = dcc.get("longaddress") == "yes"
    else:
        is_long = address > 127
    labels = {}
    for fl in loco.iter("functionlabel"):
        try:
            num = int(fl.get("num"))
        except (TypeError, ValueError):
            continue
        labels[num] = ((fl.text or "").strip(), fl.get("lockable", "true") == "true")
    return {
        "id": attrs.get("id") or "",
        "address": address,
        "long": is_long,
        "comment": attrs.get("comment") or "",
        "road_name": (attrs.get("roadName") or "").strip(),
        "road_number": (attrs.get("roadNumber") or "").strip(),
        "labels": labels,
        "file": os.path.basename(path),
    }


def load_roster(index_path, files_dir):
    """All entries listed in roster.xml, read from their locomotive files."""
    root = ET.parse(index_path).getroot()
    entries = []
    for loco in root.iter("locomotive"):
        file_name = loco.get("fileName")
        if not file_name:
            continue
        entries.append(load_entry(os.path.join(files_dir, file_name), loco.attrib))
    return entries


NAME_SCHEMES = ("id", "road")


def train_name(entry, scheme="id"):
    """CS-105 Train.Name for an entry: the roster ID, or "<road> <number>"."""
    if scheme == "road":
        parts = [entry.get("road_name") or "", entry.get("road_number") or ""]
        name = " ".join(p for p in parts if p)
        if name:
            return name
    elif scheme != "id":
        raise ValueError("unknown name scheme %r" % (scheme,))
    return entry["id"]


def desired_values(entry, include_name, names="id"):
    """CDI key -> value to write for one entry (TcsUploadAction's rules)."""
    values = {}
    if include_name:
        values["Train.Name"] = train_name(entry, names)
    values["Train.User Description"] = entry.get("comment") or ""
    for i in range(N_FUNCTIONS):
        label, lockable = entry["labels"].get(i + 1, ("", True))
        code = display_code(label)
        values["Train.Functions(%d).Display" % i] = code
        values["Train.Functions(%d).Momentary" % i] = 0 if lockable else 1
        if code == 0:
            values["Train.Functions(%d).Description" % i] = label
    return values


def plan(entries, existing_node_ids, rename=False, only=None, names="id"):
    """Decide create/update per entry against the node IDs the CS-105 has."""
    existing = set(str(n).upper() for n in existing_node_ids)
    actions = []
    for entry in entries:
        if only and entry["id"] not in only:
            continue
        if not entry["address"]:
            actions.append({"entry": entry, "action": "skip", "node": None,
                            "values": {}, "reason": "no DCC address"})
            continue
        node = train_node_id(entry["address"], entry["long"])
        create = node not in existing
        actions.append({
            "entry": entry,
            "action": "create" if create else "update",
            "node": node,
            "event": search_event(entry["address"], entry["long"]) if create else None,
            "values": desired_values(entry, include_name=create or rename, names=names),
        })
    return actions


def unmanaged_train_nodes(existing_node_ids, entries):
    """CS-105 train nodes with no roster entry at all (reported, never touched)."""
    rostered = set(train_node_id(e["address"], e["long"]) for e in entries if e["address"])
    return sorted(n for n in existing_node_ids if is_train_node(n) and n.upper() not in rostered)


def describe(action):
    e = action["entry"]
    kind = "long" if e["long"] else "short"
    labelled = sum(1 for i in range(N_FUNCTIONS) if e["labels"].get(i + 1, ("", True))[0])
    name = action["values"].get("Train.Name")
    return "%-6s %-6s addr %4d %-5s node %s  %2d labels%s%s" % (
        action["action"].upper(), e["id"], e["address"], kind, action["node"] or "-",
        labelled, "  name -> %r" % name if name is not None else "",
        "  (%s)" % action["reason"] if action.get("reason") else "")


def parse_only(value):
    if not value:
        return None
    if isinstance(value, (list, tuple, set)):
        return set(str(v) for v in value)
    return set(p.strip() for p in str(value).split(",") if p.strip())


# ---------------------------------------------------------------- JMRI side

def _jmri_available():
    """True only inside JMRI's Jython. (A CPython run from the repo root can
    import the repo's own ``jmri/`` folder as a namespace package.)"""
    if not sys.platform.startswith("java"):
        return False
    try:
        import jmri
        return hasattr(jmri, "InstanceManager")
    except ImportError:
        return False


def _wait_until(predicate, timeout, step=0.2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return predicate()


def _jmri_write_values(iface, node_dotted, values, log, timeout=60.0):
    """Load a train node's CDI, write differing values, wait for completion."""
    from java.beans import PropertyChangeListener
    from org.openlcb import NodeID
    from org.openlcb.cdi.impl import ConfigRepresentation

    state = {"loaded": False, "pending": 0}

    class _Loaded(PropertyChangeListener):
        def propertyChange(self, ev):
            if ev.getPropertyName() == ConfigRepresentation.UPDATE_CACHE_COMPLETE:
                state["loaded"] = True

    class _Written(PropertyChangeListener):
        def propertyChange(self, ev):
            if ev.getPropertyName() == ConfigRepresentation.UPDATE_WRITE_COMPLETE:
                state["pending"] -= 1

    rep = ConfigRepresentation(iface, NodeID(node_dotted))
    rep.addPropertyChangeListener(_Loaded())
    if not _wait_until(lambda: state["loaded"], timeout):
        log("  CDI load timed out for %s: %s" % (node_dotted, rep.getStatus()))
        return None
    written = _Written()
    changed = 0
    missing = []
    for key in sorted(values):
        entry = rep.getVariableForKey(key)
        if entry is None:
            missing.append(key)
            continue
        want = values[key]
        if isinstance(entry, ConfigRepresentation.StringEntry):
            if (entry.getValue() or "") == want:
                continue
            entry.addPropertyChangeListener(written)
            state["pending"] += 1
            entry.setValue(want)
        elif isinstance(entry, ConfigRepresentation.IntegerEntry):
            if int(entry.getValue()) == int(want):
                continue
            entry.addPropertyChangeListener(written)
            state["pending"] += 1
            entry.setValue(long(want))  # noqa: F821  (Jython 2.7)
        else:
            missing.append(key + " (unexpected type)")
            continue
        changed += 1
    if missing:
        log("  CDI keys not found on %s: %s" % (node_dotted, ", ".join(missing)))
    if not _wait_until(lambda: state["pending"] <= 0, timeout):
        log("  %d write(s) still unconfirmed on %s" % (state["pending"], node_dotted))
    return changed


def _jmri_run(apply=False, only=None, rename=False, names="id"):
    import jmri
    from org.openlcb import NodeID, EventID, OlcbInterface, IdentifyProducersMessage

    lines = []

    def log(msg):
        lines.append(msg)
        print(msg)

    memo = jmri.InstanceManager.getNullableDefault(jmri.jmrix.can.CanSystemConnectionMemo)
    iface = memo.get(OlcbInterface) if memo is not None else None
    if iface is None:
        raise RuntimeError("no OpenLCB/LCC connection in this JMRI")
    store = iface.getNodeStore()
    roster = jmri.jmrit.roster.Roster.getDefault()
    entries = load_roster(roster.getRosterIndexPath(), roster.getRosterFilesLocation())
    existing = [str(nm.getNodeID()) for nm in store.getNodeMemos()]
    actions = plan(entries, existing, rename=rename, only=parse_only(only), names=names)

    log("CS-105 roster sync: %s, %d roster entries, %d train nodes on the bus" % (
        "APPLY" if apply else "PLAN ONLY", len(entries),
        sum(1 for n in existing if is_train_node(n))))
    for a in actions:
        log(describe(a))
    for n in unmanaged_train_nodes(existing, entries):
        ident = store.getSimpleNodeIdent(NodeID(n))
        name = ident.getUserName() if ident is not None else ""
        log("KEEP   train node %s (%s) has no roster entry; untouched" % (n, name))
    if not apply:
        log("Nothing written. Re-run with CS105_APPLY=True to write.")
        return "\n".join(lines)

    created = updated = failed = 0
    for a in actions:
        if a["action"] == "skip":
            continue
        node = a["node"]
        if a["action"] == "create":
            log("allocating %s via Train Search %s" % (node, a["event"]))
            iface.getOutputConnection().put(
                IdentifyProducersMessage(iface.getNodeId(), EventID(a["event"])), None)
            if not _wait_until(lambda: store.findNode(NodeID(node)) is not None, 15.0):
                log("  CS-105 did not announce %s; skipping %s" % (node, a["entry"]["id"]))
                failed += 1
                continue
            created += 1
        changed = _jmri_write_values(iface, node, a["values"], log)
        if changed is None:
            failed += 1
            continue
        if a["action"] == "update":
            updated += 1
        log("  %s: %d field(s) written" % (a["entry"]["id"], changed))
    log("done: %d created, %d updated, %d failed" % (created, updated, failed))
    return "\n".join(lines)


# ---------------------------------------------------------------- CLI side

def _cli(argv):
    import argparse
    p = argparse.ArgumentParser(description="Plan a CS-105 roster sync from roster files (no device access).")
    p.add_argument("roster_dir", help="folder holding roster.xml and roster/")
    p.add_argument("--only", help="comma-separated roster IDs")
    p.add_argument("--existing", help="comma-separated train node IDs the CS-105 already has")
    p.add_argument("--rename", action="store_true", help="plan Train.Name for existing trains too")
    p.add_argument("--names", choices=NAME_SCHEMES, default="id", help="train name scheme")
    p.add_argument("--values", action="store_true", help="also print the CDI values per entry")
    args = p.parse_args(argv)
    entries = load_roster(os.path.join(args.roster_dir, "roster.xml"),
                          os.path.join(args.roster_dir, "roster"))
    existing = parse_only(args.existing) or set()
    actions = plan(entries, existing, rename=args.rename, only=parse_only(args.only), names=args.names)
    for a in actions:
        print(describe(a))
        if args.values:
            for k in sorted(a["values"]):
                print("    %s = %r" % (k, a["values"][k]))
    return 0


if _jmri_available():
    _g = globals()
    RESULT = _jmri_run(apply=bool(_g.get("CS105_APPLY", False)),
                       only=_g.get("CS105_ONLY"),
                       rename=bool(_g.get("CS105_RENAME", False)),
                       names=str(_g.get("CS105_NAMES") or "id"))
elif __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
