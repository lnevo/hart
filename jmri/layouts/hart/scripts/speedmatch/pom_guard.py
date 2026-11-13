"""pom_guard.py - the one check every programming-on-the-main (POM) write goes through.

Part C of docs/jmri/speedmatching/RERUN_PLAN.md. Pure Python that runs both in CPython
(tests, the Mac dry-run CLI) and in the Pi JMRI's Jython 2.7 (pom_write.py loads it), so:
no f-strings, no type hints, no print function, nothing that needs Python 3.

What it refuses (each raises GuardRefusal with the reason):

* Address: the address comes only from the roster entry named in the proposal, never from
  typed input. Refused: address 0, a short address outside 1-127, a long address outside
  1-10239 (the NMRA long range; JMRI's ops-mode pane uses 0-10239), a long/short flag that
  disagrees between roster.xml, the entry file and the decoder CVs it records (CV17/CV18,
  CV29 bit 5), another roster entry with the same address number (either flag), a roster
  entry whose recorded CV19 holds an advanced-consist address, and a target address that
  another entry records as its CV19 consist address.
* Consist: the caller supplies the cs105_consist.py ACTION=query log. Refused unless the log
  is complete (ends with END, no ERROR or decode error), covers the target's train node and
  every named partner's node, every node answered ("listeners: None" is unknown, so it is
  refused), and every node has 0 listeners. Fail closed: no log, a failed query or an
  unknown answer is a refusal.
* CVs: only 3, 4, 25, 29, 66, 67-94 and 95. CV1, 17, 18, 19 (addresses, consist) and CV8
  (reset) are named in their refusal; everything else is refused as "not in the allowed
  list". Values are integers 0-255. Each CV at most once per proposal.
* CV29: may differ from the value it was checked against (read from the decoder, or the
  roster's value when no read is possible) only in bit 4 (value 16, speed table on/off).
* Old values: every planned CV needs an old value (read or roster) so the rollback file can
  be written; a CV with neither is refused.
* Apply: execute() writes only when apply is exactly True and a rollback path is given that
  does not already exist. The rollback file is written before the first write.

Proposal file (JSON), the input format shared with the speed-table tools:

    {
      "roster_id": "CSX 2738",            # required: roster entry id, as in roster.xml
      "writes": [                          # required: non-empty list
        {"cv": 67, "value": 14},           # cv: int, value: int 0-255
        {"cv": 68, "value": 28, "note": "anything"}
      ],
      "note": "free text",                 # optional, ignored
      "source": "propose_table.py round 2" # optional, ignored
    }

Only "cv", "value", "note" and "old_source" are allowed inside a write; any other key is
refused so a typo cannot slip through. Top-level keys other than roster_id and writes are
ignored. A rollback file is itself a valid proposal: it has the same roster_id and the old
values as "writes", each with "old_source" ("read" or "roster") saying where it came from.

Roster input: the JMRI user files directory that holds roster.xml and roster/<fileName>
(on the Pi, Roster.getDefault().getRosterLocation()). roster.xml is the index of record;
stray files in roster/ that the index does not list are ignored.

Mac dry run (never writes):

    python3 pom_guard.py proposal.json --roster-dir <JMRI user files dir> \
        --consist-log consist.log --partner "CSX 2121" [--reads reads.json]
"""

import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET

ALLOWED_CVS = frozenset([3, 4, 25, 29, 66, 95] + list(range(67, 95)))
NAMED_REFUSALS = {
    1: "CV1 is the short address",
    17: "CV17 is the long address (high byte)",
    18: "CV18 is the long address (low byte)",
    19: "CV19 is the advanced consist address",
    8: "CV8 is the decoder reset",
}
CV29_SPEED_TABLE_BIT = 0x10
CV29_LONG_BIT = 0x20
SHORT_RANGE = (1, 127)
LONG_RANGE = (1, 10239)
WRITE_KEYS = frozenset(["cv", "value", "note", "old_source"])


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

    Returns {id: {"id", "file", "number", "long", "cvs"}}. Refuses on a missing index, a
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
            continue
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
        entries[rid] = {"id": rid, "file": path, "number": number, "long": is_long,
                        "cvs": _entry_cvs(froot)}
    return entries


def check_roster_target(roster, roster_id):
    """Every address check for one roster entry. Returns the entry."""
    if roster_id not in roster:
        raise GuardRefusal("roster id %r is not in the roster" % (roster_id,))
    e = roster[roster_id]
    number, is_long = e["number"], e["long"]
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
        raise GuardRefusal("%r: roster CV19 = %d, the decoder is in an advanced consist" % (
            roster_id, cvs[19]))
    for oid, o in sorted(roster.items()):
        if oid == roster_id:
            continue
        if o["number"] == number:
            raise GuardRefusal("%r shares address %d with roster entry %r" % (roster_id, number, oid))
        # A CV19 consist address is a 7-bit short address: a short-address write to it
        # would reach every decoder in that consist.
        if not is_long and (o["cvs"].get(19, 0) & 0x7F) == number:
            raise GuardRefusal("address %d is the CV19 consist address of %r" % (number, oid))
    return e


# ---------------------------------------------------------------- consist state

_LISTENERS = re.compile(r"^(\S+) listeners: (\S+)\s*$")
_LISTENER = re.compile(r"^\s*\[(\d+)\] flags 0x([0-9A-Fa-f]{2}) node (\S+)\s*$")


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
            state["nodes"][current] = {"count": count, "listeners": []}
            continue
        m = _LISTENER.match(line)
        if m and current is not None:
            state["nodes"][current]["listeners"].append(m.group(3).upper())
    return state


def check_no_consist(state, required_nodes):
    """Fail closed unless every required node answered with 0 listeners."""
    if state is None:
        raise GuardRefusal("no consist query result (run cs105_consist.py ACTION=query first)")
    if state.get("errors"):
        raise GuardRefusal("consist query failed: %s" % "; ".join(state["errors"]))
    if not state.get("complete"):
        raise GuardRefusal("consist query log is incomplete (no END)")
    nodes = state.get("nodes", {})
    req = [n.upper() for n in required_nodes]
    for n in req:
        if n not in nodes:
            raise GuardRefusal("consist query did not cover train node %s" % n)
        info = nodes[n]
        if info["count"] is None:
            raise GuardRefusal("train node %s did not answer the consist query (state unknown)" % n)
        if info["count"] != 0 or info["listeners"]:
            raise GuardRefusal("train node %s has %s listener(s) %s: break the consist first" % (
                n, info["count"], ", ".join(info["listeners"])))
    for n, info in sorted(nodes.items()):
        for lst in info["listeners"]:
            if lst in req:
                raise GuardRefusal("train node %s is a listener of %s: break the consist first" % (lst, n))


# ---------------------------------------------------------------- CVs and values

def check_cv_value(cv, value):
    if not _is_int(cv):
        raise GuardRefusal("CV %r is not an integer" % (cv,))
    if cv in NAMED_REFUSALS:
        raise GuardRefusal("CV%d is never written on the main: %s" % (cv, NAMED_REFUSALS[cv]))
    if cv not in ALLOWED_CVS:
        raise GuardRefusal("CV%d is not in the allowed list (3, 4, 25, 29, 66, 67-94, 95)" % cv)
    if not _is_int(value) or value < 0 or value > 255:
        raise GuardRefusal("CV%d value %r is not an integer 0-255" % (cv, value))


def check_cv29(old, new, is_long):
    if old is None:
        raise GuardRefusal("CV29 needs the value it holds now (read or roster) to check the bits")
    if bool(old & CV29_LONG_BIT) != is_long:
        raise GuardRefusal("CV29 old value %d disagrees with the %s address in the roster" % (
            old, "long" if is_long else "short"))
    changed = (old ^ new) & ~CV29_SPEED_TABLE_BIT & 0xFF
    if changed:
        raise GuardRefusal("CV29 %d -> %d changes bits 0x%02X; only bit 4 (16) may change" % (
            old, new, changed))


# ---------------------------------------------------------------- proposal and plan

def load_proposal(path):
    f = open(path, "r")
    try:
        return json.load(f)
    finally:
        f.close()


def validate_proposal(proposal):
    if not isinstance(proposal, dict):
        raise GuardRefusal("proposal is not a JSON object")
    rid = proposal.get("roster_id")
    if not rid or not isinstance(rid, (type(u""), type(""))):
        raise GuardRefusal("proposal has no roster_id")
    writes = proposal.get("writes")
    if not isinstance(writes, list) or not writes:
        raise GuardRefusal("proposal has no writes")
    seen = set()
    out = []
    for w in writes:
        if not isinstance(w, dict):
            raise GuardRefusal("write %r is not an object" % (w,))
        extra = set(w.keys()) - WRITE_KEYS
        if extra:
            raise GuardRefusal("write %r has unknown keys %s" % (w, ", ".join(sorted(extra))))
        cv, value = w.get("cv"), w.get("value")
        check_cv_value(cv, value)
        if cv in seen:
            raise GuardRefusal("CV%d appears twice in the proposal" % cv)
        seen.add(cv)
        out.append((cv, value))
    return rid, out


def build_plan(proposal, roster, consist_state, partners, reads=None):
    """Validate everything and return the plan dict, or raise GuardRefusal.

    roster: from load_roster(). consist_state: from parse_consist_log(). partners: roster
    ids whose train nodes must also show no listeners (for 2738, its lead CSX 2121).
    reads: {cv: value} read from the decoder just before; CVs missing there fall back to
    the roster's recorded value.
    """
    rid, writes = validate_proposal(proposal)
    if partners is None:
        raise GuardRefusal("consist partners not given: name the locos that consist with %r" % rid)
    entry = check_roster_target(roster, rid)
    number, is_long = entry["number"], entry["long"]
    nodes = [train_node(number, is_long)]
    for p in partners:
        if p == rid:
            continue
        if p not in roster:
            raise GuardRefusal("consist partner %r is not in the roster" % (p,))
        nodes.append(train_node(roster[p]["number"], roster[p]["long"]))
    check_no_consist(consist_state, nodes)
    reads = reads or {}
    rows = []
    for cv, new in writes:
        if cv in reads and reads[cv] is not None:
            old, src = reads[cv], "read"
        elif cv in entry["cvs"]:
            old, src = entry["cvs"][cv], "roster"
        else:
            old, src = None, None
        if old is None:
            raise GuardRefusal("CV%d has no read value and no roster value; no rollback possible" % cv)
        if cv == 29:
            check_cv29(old, new, is_long)
        rows.append({"cv": cv, "old": old, "old_source": src, "new": new})
    return {"roster_id": rid, "address": number, "long": is_long,
            "train_node": nodes[0], "checked_nodes": nodes, "rows": rows}


def recheck_row(plan, row):
    """Defence in depth: the per-write checks again, right before the write."""
    check_address(plan["address"], plan["long"])
    check_cv_value(row["cv"], row["new"])
    if row["cv"] == 29:
        check_cv29(row["old"], row["new"], plan["long"])


def plan_lines(plan):
    tag = "%d%s" % (plan["address"], "L" if plan["long"] else "S")
    lines = ["PLAN %s address %s (%s) train node %s" % (
        plan["roster_id"], tag, "long" if plan["long"] else "short", plan["train_node"])]
    for r in plan["rows"]:
        same = " (same, skipped)" if r["old"] == r["new"] else ""
        lines.append("PLAN %s CV%d old=%d (%s) new=%d%s" % (
            tag, r["cv"], r["old"], r["old_source"], r["new"], same))
    return lines


def rollback_doc(plan):
    srcs = sorted(set(r["old_source"] for r in plan["rows"]))
    return {
        "roster_id": plan["roster_id"],
        "address": plan["address"],
        "long": plan["long"],
        "made": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "old_values_from": srcs[0] if len(srcs) == 1 else "mixed",
        "note": "Rollback written by pom_guard before the first write. old_source 'read' came "
                "from the decoder; 'roster' is the roster's recorded value (no read possible).",
        "writes": [{"cv": r["cv"], "value": r["old"], "old_source": r["old_source"]}
                   for r in plan["rows"]],
    }


def execute(plan, write_cv, apply=False, rollback_path=None, log=None):
    """Dry run unless apply is True. write_cv(cv, value) -> (ok, status_text).

    On apply: writes the rollback file first (refuses to overwrite one), then each changed CV
    in order, stopping at the first failure. Returns {"applied", "written", "failed"}.
    """
    log = log or (lambda m: None)
    for line in plan_lines(plan):
        log(line)
    result = {"applied": False, "written": [], "failed": None}
    if apply is not True:
        log("DRY RUN: nothing written (set APPLY = True to write)")
        return result
    if not rollback_path:
        raise GuardRefusal("apply needs a rollback file path")
    if os.path.exists(rollback_path):
        raise GuardRefusal("rollback file %s already exists; keep it and pick a new name" % rollback_path)
    f = open(rollback_path, "w")
    try:
        json.dump(rollback_doc(plan), f, indent=1, sort_keys=True)
    finally:
        f.close()
    log("ROLLBACK written %s" % rollback_path)
    result["applied"] = True
    for r in plan["rows"]:
        recheck_row(plan, r)
        if r["old"] == r["new"]:
            log("SKIP CV%d already %d" % (r["cv"], r["new"]))
            continue
        ok, status = write_cv(r["cv"], r["new"])
        log("WRITE CV%d=%d %s %s" % (r["cv"], r["new"], "OK" if ok else "FAILED", status))
        if not ok:
            result["failed"] = r["cv"]
            log("STOPPED at CV%d; earlier writes stand, roll back with %s" % (r["cv"], rollback_path))
            return result
        result["written"].append(r["cv"])
    log("DONE %d write(s)" % len(result["written"]))
    return result


# ---------------------------------------------------------------- Mac dry-run CLI

def _main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="Dry-run a POM proposal against a roster and consist log.")
    ap.add_argument("proposal")
    ap.add_argument("--roster-dir", required=True, help="folder holding roster.xml and roster/")
    ap.add_argument("--consist-log", required=True, help="cs105_consist.py ACTION=query log")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--partner", action="append", help="roster id of a consist partner (repeat)")
    grp.add_argument("--no-partners", action="store_true", help="the loco consists with no other")
    ap.add_argument("--reads", help="JSON {cv: value} read from the decoder")
    a = ap.parse_args(argv)
    try:
        f = open(a.consist_log)
        try:
            state = parse_consist_log(f.read())
        finally:
            f.close()
        reads = None
        if a.reads:
            raw = load_proposal(a.reads)
            reads = dict((int(k), v) for k, v in raw.items())
        plan = build_plan(load_proposal(a.proposal), load_roster(a.roster_dir), state,
                          partners=a.partner or [], reads=reads)
    except GuardRefusal as e:
        sys.stdout.write("REFUSED %s\n" % e)
        return 2
    execute(plan, None, apply=False, log=lambda m: sys.stdout.write(m + "\n"))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
