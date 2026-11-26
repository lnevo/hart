"""pom_guard_roster.py - the target checks of pom_guard.py: the address, the roster and the consist state.

Split out of pom_guard.py on 2026-11-26 with no change in behaviour, so the guard stays under the size limit
(tools/audit/check_py_sizes.py). pom_guard.py imports every name here and is the one module callers use; the rules
are in its docstring. Same constraints: runs in CPython and in the Pi JMRI's Jython 2.7, so no f-strings, no type
hints, no print function. It ships next to pom_guard.py (speedmatch.py POM_FILES).
"""

import os
import re
import xml.etree.ElementTree as ET

CV29_LONG_BIT = 0x20
SHORT_RANGE = (1, 127)
LONG_RANGE = (1, 10239)


class GuardRefusal(Exception):
    """A write the guard will not allow. The message says why."""


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


# ---------------------------------------------------------------- address helpers

def check_address(number, is_long):
    """Refuse address 0 and anything outside the short or long range."""
    if not _is_int(number):
        raise GuardRefusal("address %r is not an integer" % (number,))
    if number == 0:
        raise GuardRefusal("address 0 is the DCC broadcast address")
    lo, hi = LONG_RANGE if is_long else SHORT_RANGE
    if number < lo or number > hi:
        raise GuardRefusal("%s address %d is outside %d-%d" % (
            "long" if is_long else "short", number, lo, hi))


def train_node(number, is_long):
    """LCC train node id the CS-105 (and JMRI OlcbThrottle.guessDCCNodeID) uses for an address."""
    check_address(number, is_long)
    if is_long:
        return "06.01.00.00.%02X.%02X" % (0xC0 | ((number >> 8) & 0xFF), number & 0xFF)
    return "06.01.00.00.00.%02X" % (number & 0xFF)


# ---------------------------------------------------------------- roster parsing

_DOCTYPE = re.compile(r"<!DOCTYPE[^>]*>")


def _parse_xml(path):
    # Drop the DOCTYPE: the roster files name a DTD by an absolute path that only JMRI can
    # resolve, and Jython's parser may try to fetch it.
    f = open(path, "rb")
    try:
        data = f.read()
    finally:
        f.close()
    if bytes is str:  # Python 2 / Jython: str is bytes
        return ET.fromstring(_DOCTYPE.sub("", data))
    return ET.fromstring(re.sub(b"<!DOCTYPE[^>]*>", b"", data))


def _yes(v):
    return (v or "").strip().lower() in ("yes", "true")


def _loco_address(loco, where):
    """(number, is_long) from a <locomotive> element; refuse if its parts disagree."""
    attr = (loco.get("dccAddress") or "").strip()
    la = loco.find("locoaddress")
    if la is None:
        raise GuardRefusal("%s has no <locoaddress>" % where)
    dla = la.find("dcclocoaddress")
    if dla is None:
        raise GuardRefusal("%s has no <dcclocoaddress>" % where)
    num_s = (dla.get("number") or "").strip()
    flag = dla.get("longaddress")
    if flag is None:
        raise GuardRefusal("%s has no longaddress flag" % where)
    is_long = _yes(flag)
    try:
        number = int(num_s)
    except ValueError:
        raise GuardRefusal("%s address %r is not a number" % (where, num_s))
    if attr and attr != num_s:
        raise GuardRefusal("%s dccAddress %s disagrees with dcclocoaddress %s" % (where, attr, num_s))
    other = la.find("number")
    if other is not None and (other.text or "").strip() not in ("", num_s):
        raise GuardRefusal("%s <number> %s disagrees with %s" % (where, other.text, num_s))
    proto = la.find("protocol")
    if proto is not None and (proto.text or "").strip():
        want = "dcc_long" if is_long else "dcc_short"
        p = proto.text.strip()
        if p in ("dcc_long", "dcc_short") and p != want:
            raise GuardRefusal("%s protocol %s disagrees with longaddress=%s" % (where, p, flag))
    return number, is_long


def _entry_cvs(loco_config_root):
    cvs = {}
    for el in loco_config_root.iter("CVvalue"):
        name = (el.get("name") or "").strip()
        if name.isdigit():
            try:
                cvs[int(name)] = int(el.get("value"))
            except (TypeError, ValueError):
                pass
    return cvs


def load_roster(roster_dir):
    """Read roster.xml and every entry file it lists.

    Returns {id: {"id", "file", "address", "long", "cvs"}}. Refuses on a missing index, a
    duplicate id, a missing entry file, or an entry whose index and file disagree.
    """
    index = os.path.join(roster_dir, "roster.xml")
    if not os.path.isfile(index):
        raise GuardRefusal("no roster index at %s" % index)
    root = _parse_xml(index)
    entries = {}
    for loco in root.iter("locomotive"):
        rid = loco.get("id")
        if not rid:
            raise GuardRefusal("roster.xml has a locomotive with no id (fileName %r)" % loco.get("fileName"))
        if rid in entries:
            raise GuardRefusal("roster id %r appears twice in roster.xml" % rid)
        where = "roster.xml entry %r" % rid
        number, is_long = _loco_address(loco, where)
        fname = loco.get("fileName") or ""
        path = os.path.join(roster_dir, "roster", fname)
        if not fname or not os.path.isfile(path):
            raise GuardRefusal("roster file for %r not found (%s)" % (rid, path))
        froot = _parse_xml(path)
        floco = froot.find("locomotive")
        if floco is None:
            raise GuardRefusal("%s has no <locomotive>" % path)
        if floco.get("id") != rid:
            raise GuardRefusal("%s holds id %r, roster.xml says %r" % (path, floco.get("id"), rid))
        fnum, flong = _loco_address(floco, "roster file %s" % fname)
        if (fnum, flong) != (number, is_long):
            raise GuardRefusal("%r: roster.xml says %d%s, %s says %d%s" % (
                rid, number, "L" if is_long else "S", fname, fnum, "L" if flong else "S"))
        entries[rid] = {"id": rid, "file": path, "address": number, "long": is_long,
                        "cvs": _entry_cvs(froot)}
    return entries


def check_roster_target(roster, roster_id):
    """Every address check for one roster entry. Returns (entry, warnings).

    Roster CVvalues can be decoder-definition defaults rather than what the decoder holds
    (BO 3545 and BO 6944 record CV19 = 127), so a roster-only CV19 is a warning here; a CV19
    from a read or the ledger is refused in plan_rows().
    """
    warnings = []
    if roster_id not in roster:
        raise GuardRefusal("roster id %r is not in the roster" % (roster_id,))
    e = roster[roster_id]
    number, is_long = e["address"], e["long"]
    check_address(number, is_long)
    cvs = e["cvs"]
    if is_long and 17 in cvs and 18 in cvs:
        rec = ((cvs[17] - 0xC0) << 8) + cvs[18]
        if cvs[17] < 0xC0 or rec != number:
            raise GuardRefusal("%r: roster CV17/CV18 (%d/%d) do not encode long address %d" % (
                roster_id, cvs[17], cvs[18], number))
    if not is_long and 1 in cvs and cvs[1] != number:
        raise GuardRefusal("%r: roster CV1 = %d but the short address is %d" % (roster_id, cvs[1], number))
    if 29 in cvs and bool(cvs[29] & CV29_LONG_BIT) != is_long:
        raise GuardRefusal("%r: roster CV29 = %d says %s address, the entry says %s" % (
            roster_id, cvs[29], "long" if cvs[29] & CV29_LONG_BIT else "short",
            "long" if is_long else "short"))
    if cvs.get(19, 0) & 0x7F:
        warnings.append("WARNING %r: roster CV19 = %d (may be a default); read CV19 on the "
                        "programming track (seed-ledger) to be sure it is not in an advanced consist"
                        % (roster_id, cvs[19]))
    for oid, o in sorted(roster.items()):
        if oid == roster_id:
            continue
        if o["address"] == number:
            raise GuardRefusal("%r shares address %d with roster entry %r" % (roster_id, number, oid))
        # A CV19 consist address is a 7-bit short address: a short-address write to it
        # would reach every decoder in that consist.
        if not is_long and (o["cvs"].get(19, 0) & 0x7F) == number:
            warnings.append("WARNING short address %d is the roster CV19 of %r (may be a default)"
                            % (number, oid))
    return e, warnings




# ---------------------------------------------------------------- consist state

_LISTENERS = re.compile(r"^(\S+) listeners: (\S+)\s*$")
_LISTENER = re.compile(r"^\s*\[(\d+)\] flags 0x([0-9A-Fa-f]{2}) node (\S+)\s*$")


def query_nodes(roster, target_id):
    """[(roster id, train node)] for every roster entry, the target first.

    pom_write.py queries exactly this list, and build_plan checks the log against it, so a
    consist led by any rostered loco is seen without anyone naming the lead. A consist led by
    an address that is not in the roster cannot be listed this way; the operator confirms
    those are broken (CONSISTS_BROKEN, required for apply). An entry whose address has no
    train node (0, out of range) is refused: fail closed.
    """
    if target_id not in roster:
        raise GuardRefusal("roster id %r is not in the roster" % (target_id,))
    ids = [target_id] + sorted(r for r in roster if r != target_id)
    out = []
    for rid in ids:
        e = roster[rid]
        try:
            out.append((rid, train_node(e["address"], e["long"])))
        except GuardRefusal as err:
            raise GuardRefusal("roster entry %r has no train node to query: %s" % (rid, err))
    return out


def parse_consist_log(text):
    """Parse the cs105_consist.py ACTION=query log.

    Returns {"complete": bool, "errors": [..], "nodes": {node: {"count": int|None,
    "listeners": [node, ..]}}}. Node ids are upper case.
    """
    state = {"complete": False, "errors": [], "nodes": {}}
    current = None
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.strip() == "END":
            state["complete"] = True
            continue
        if line.startswith("ERROR") or "decode error" in line:
            state["errors"].append(line.strip())
            continue
        m = _LISTENERS.match(line)
        if m:
            current = m.group(1).upper()
            c = m.group(2)
            count = int(c) if c.isdigit() else None
            state["nodes"][current] = {"count": count, "listeners": [], "indices": []}
            continue
        m = _LISTENER.match(line)
        if m and current is not None:
            state["nodes"][current]["listeners"].append(m.group(3).upper())
            state["nodes"][current]["indices"].append(int(m.group(1)))
    return state


def check_no_consist(state, nodes, absent_ok=()):
    """Fail closed unless the target (nodes[0]) is in no consist.

    nodes: query_nodes() output. absent_ok: roster ids whose node may stay silent. Returns
    the list of notes for silent nodes that were allowed, for the log.
    """
    if state is None:
        raise GuardRefusal("no consist query result (run cs105_consist.py ACTION=query first)")
    if state.get("errors"):
        raise GuardRefusal("consist query failed: %s" % "; ".join(state["errors"]))
    if not state.get("complete"):
        raise GuardRefusal("consist query log is incomplete (no END)")
    seen = state.get("nodes", {})
    target_id, target = nodes[0][0], nodes[0][1].upper()
    absent_ok = list(absent_ok or ())
    if target_id in absent_ok:
        raise GuardRefusal("the target %r cannot be in ABSENT_OK" % target_id)
    notes = []
    for rid, node in nodes:
        n = node.upper()
        if n not in seen:
            raise GuardRefusal("consist query did not cover %r (train node %s)" % (rid, n))
        info = seen[n]
        if info["count"] is None:
            if n == target:
                raise GuardRefusal("the target %r (train node %s) did not answer the consist query" % (rid, n))
            if rid not in absent_ok:
                raise GuardRefusal("%r (train node %s) did not answer the consist query; add it to "
                                   "ABSENT_OK only if that loco has no train node on the CS-105" % (rid, n))
            notes.append("ABSENT_OK %r train node %s did not answer" % (rid, n))
            continue
        if sorted(info.get("indices", [])) != list(range(info["count"])):
            raise GuardRefusal("%r (train node %s) reports %d listener(s) but listed indices %s: "
                               "state unknown" % (rid, n, info["count"], sorted(info.get("indices", []))))
    t = seen[target]
    if t["count"] or t["listeners"]:
        raise GuardRefusal("the target %r has listener(s) %s: break the consist first" % (
            target_id, ", ".join(t["listeners"])))
    for n, info in sorted(seen.items()):
        if target in info["listeners"]:
            raise GuardRefusal("the target %r is a listener of train node %s: break the consist first" % (
                target_id, n))
    return notes
