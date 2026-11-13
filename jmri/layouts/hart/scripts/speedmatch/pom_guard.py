"""pom_guard.py - the one check every programming-on-the-main (POM) write goes through.

Part C of docs/jmri/speedmatching/RERUN_PLAN.md; operator notes in
docs/jmri/speedmatching/POM_GUARD.md. Pure Python that runs both in CPython (tests, the Mac
dry-run CLI) and in the Pi JMRI's Jython 2.7 (pom_write.py loads it), so: no f-strings, no
type hints, no print function, nothing that needs Python 3.

What it refuses (each raises GuardRefusal with the reason):

* Address: the address comes only from the roster entry named in the proposal, never from
  typed input. Refused: address 0, a short address outside 1-127, a long address outside
  1-10239 (the NMRA long range; JMRI's ops-mode pane uses 0-10239), a long/short flag that
  disagrees between roster.xml, the entry file and the decoder CVs it records (CV17/CV18,
  CV29 bit 5), another roster entry with the same address number (either flag), a roster
  entry whose recorded CV19 holds an advanced-consist address, a target address that
  another entry records as its CV19 consist address, and a roster.xml entry with no id.
* Consist: the caller supplies the cs105_consist.py ACTION=query log for the train node of
  every roster entry (query_nodes() gives the list). Refused unless the log is complete
  (END, no ERROR or decode error), covers every node, the target answered with 0
  listeners, and the target is no rostered node's listener. A node that did not answer is
  allowed only when its roster id is in the operator's explicit absent_ok list; a node whose
  listener count does not match the listeners it listed is refused (state unknown).
  Limit: a consist led by an address that is NOT in the roster cannot be seen, so apply
  also needs the operator's consists_broken=True (CONSISTS_BROKEN in pom_write.py).
* CVs: only 3, 4, 25, 66, 67-94 and 95. CV29 is refused: without RailCom its real value is
  unknown, and a whole-byte write could flip the direction or address-type bits, so it is
  set on the programming track only. CV1, 17, 18, 19 (addresses, consist) and CV8 (reset)
  are named in their refusal too; everything else is refused as "not in the allowed list".
  Values are integers 0-255. Each CV at most once per proposal.
* Old values, in this order: a read from the decoder in this run ("read"), then the loco's
  ledger entry ("ledger": the last value read or sent), then the roster ("roster"). A CV
  the ledger marks "unknown" (a write that timed out or failed) is refused until a read in
  this run succeeds or the operator clears it (clear-ledger). A CV with no old value at
  all is refused (no rollback possible).
* Skips: a CV is skipped as "already holds the value" only when its old value came from a
  read in this run. Ledger and roster values are never trusted for a skip.
* Apply: execute() writes only when apply is exactly True, consists_broken is True, and it
  has a ledger file and a rollback path that does not already exist. The rollback file
  (same precedence) is written before the first write. The ledger records each OK write; a
  write that times out or fails marks the CV "unknown" and stops the run, and the log names
  the exact recovery steps.

Proposal file (JSON), the input format shared with the speed-table tools:

    {
      "roster_id": "CSX 2738",            # required: roster entry id, as in roster.xml
      "writes": [                          # required: non-empty list
        {"cv": 67, "value": 14},           # cv: int, value: int 0-255
        {"cv": 68, "value": 28, "note": "anything"}
      ],
      "note": "free text",                 # optional, ignored (any other top-level key too)
      "source": "propose_table.py round 2" # optional, ignored
    }

Only "cv", "value", "note" and "old_source" are allowed inside a write; any other key is
refused so a typo cannot slip through. A rollback file is itself a valid proposal: the
same roster_id and the old values as "writes", each with "old_source".

Ledger (one per loco, <ledger dir>/<roster id>.json; a file that exists but does not parse
is a refusal, never an empty ledger):
    {"roster_id": "CSX 2738", "next_seq": 4,
     "cvs": {"67": {"value": 14, "state": "sent", "seq": 3, "at": "2026-11-13T15:00:00"},
             "68": {"value": null, "state": "unknown", "seq": 2, "at": ..., "note": "timeout"}}}
    state "read": read from the decoder; "sent": last value sent with an OK reply;
    "unknown": a write timed out or failed, so the decoder may hold either value.
    seq is a per-ledger counter (no wall clock), so the order of entries is exact.

Roster input: the JMRI user files directory that holds roster.xml and roster/<fileName>
(on the Pi, Roster.getDefault().getRosterLocation()). roster.xml is the index of record;
stray files in roster/ that the index does not list are ignored.

Mac dry run (never writes):

    python3 pom_guard.py proposal.json --roster-dir <JMRI user files dir> \
        --consist-log consist.log [--absent-ok "NWR 06" ...] [--reads reads.json] \
        [--ledger <roster id>.json]

Ledger upkeep (on the Pi, where the ledger lives):

    python3 pom_guard.py clear-ledger <ledger file> CV68 [CV69 ...]   accept an unknown CV
    python3 pom_guard.py archive-ledger "CSX 2738" [--ledger-dir DIR]   after the read-back
"""

import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET

ALLOWED_CVS = frozenset([3, 4, 25, 66, 95] + list(range(67, 95)))
NAMED_REFUSALS = {
    1: "CV1 is the short address",
    17: "CV17 is the long address (high byte)",
    18: "CV18 is the long address (low byte)",
    19: "CV19 is the advanced consist address",
    8: "CV8 is the decoder reset",
    29: "CV29 is set on the programming track only (its real value cannot be read on the main)",
}
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
    """Every address check for one roster entry. Returns the entry."""
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
        raise GuardRefusal("%r: roster CV19 = %d, the decoder is in an advanced consist" % (
            roster_id, cvs[19]))
    for oid, o in sorted(roster.items()):
        if oid == roster_id:
            continue
        if o["address"] == number:
            raise GuardRefusal("%r shares address %d with roster entry %r" % (roster_id, number, oid))
        # A CV19 consist address is a 7-bit short address: a short-address write to it
        # would reach every decoder in that consist.
        if not is_long and (o["cvs"].get(19, 0) & 0x7F) == number:
            raise GuardRefusal("address %d is the CV19 consist address of %r" % (number, oid))
    return e




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
            state["nodes"][current] = {"count": count, "listeners": []}
            continue
        m = _LISTENER.match(line)
        if m and current is not None:
            state["nodes"][current]["listeners"].append(m.group(3).upper())
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
        if info["count"] != len(info["listeners"]):
            raise GuardRefusal("%r (train node %s) reports %d listener(s) but listed %d: state unknown" % (
                rid, n, info["count"], len(info["listeners"])))
    t = seen[target]
    if t["count"] or t["listeners"]:
        raise GuardRefusal("the target %r has listener(s) %s: break the consist first" % (
            target_id, ", ".join(t["listeners"])))
    for n, info in sorted(seen.items()):
        if target in info["listeners"]:
            raise GuardRefusal("the target %r is a listener of train node %s: break the consist first" % (
                target_id, n))
    return notes




# ---------------------------------------------------------------- CVs and values

def check_cv_value(cv, value):
    if not _is_int(cv):
        raise GuardRefusal("CV %r is not an integer" % (cv,))
    if cv in NAMED_REFUSALS:
        raise GuardRefusal("CV%d is never written on the main: %s" % (cv, NAMED_REFUSALS[cv]))
    if cv not in ALLOWED_CVS:
        raise GuardRefusal("CV%d is not in the allowed list (3, 4, 25, 66, 67-94, 95)" % cv)
    if not _is_int(value) or value < 0 or value > 255:
        raise GuardRefusal("CV%d value %r is not an integer 0-255" % (cv, value))


def _cv_key(k, what):
    if _is_int(k):
        return k
    if isinstance(k, (type(u""), type(""))):
        t = k.strip().upper()
        if t.startswith("CV"):
            t = t[2:]
        if t.isdigit():
            return int(t)
    raise GuardRefusal("%s key %r is not a CV number" % (what, k))


def validate_reads(raw, what="reads"):
    """{cv: value} with int keys (or digit strings) and int values 0-255, else refuse."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise GuardRefusal("%s is not an object of CV: value" % what)
    out = {}
    for k, v in raw.items():
        cv = _cv_key(k, what)
        if not _is_int(v) or v < 0 or v > 255:
            raise GuardRefusal("%s CV%d value %r is not an integer 0-255" % (what, cv, v))
        out[cv] = v
    return out


# ---------------------------------------------------------------- files

def _stamp():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _read_json(path, what):
    try:
        f = open(path, "r")
        try:
            return json.load(f)
        finally:
            f.close()
    except (IOError, OSError, ValueError) as e:
        raise GuardRefusal("%s %s cannot be read: %s" % (what, path, e))


def _write_json(path, doc):
    """Write a temp file, fsync it, rename it over the target (atomic on Linux and Jython)."""
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    tmp = path + ".tmp"
    f = open(tmp, "w")
    try:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    finally:
        f.close()
    os.rename(tmp, path)


def load_proposal(path):
    return _read_json(path, "proposal")


def safe_name(roster_id):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", roster_id).strip("_") or "loco"


def ledger_path(ledger_dir, roster_id):
    return os.path.join(ledger_dir, safe_name(roster_id) + ".json")


def load_ledger(path, roster_id):
    """The ledger for one loco; an empty one only when the file does not exist."""
    if not path or not os.path.exists(path):
        return {"roster_id": roster_id, "next_seq": 1, "cvs": {}}
    doc = _read_json(path, "ledger")
    if not isinstance(doc, dict) or not isinstance(doc.get("cvs"), dict):
        raise GuardRefusal("ledger %s is not a ledger" % path)
    if doc.get("roster_id") != roster_id:
        raise GuardRefusal("ledger %s is for %r, not %r" % (path, doc.get("roster_id"), roster_id))
    if not _is_int(doc.get("next_seq")):
        raise GuardRefusal("ledger %s has no next_seq" % path)
    for k, e in doc["cvs"].items():
        _cv_key(k, "ledger")
        if not isinstance(e, dict) or e.get("state") not in ("sent", "read", "unknown"):
            raise GuardRefusal("ledger %s CV%s has no valid state" % (path, k))
        if not _is_int(e.get("seq")) or e["seq"] >= doc["next_seq"]:
            raise GuardRefusal("ledger %s CV%s has a bad seq" % (path, k))
        if e["state"] != "unknown":
            validate_reads({k: e.get("value")}, "ledger")
    return doc


def ledger_mark(ledger, cv, value, state, note=None):
    seq = ledger.get("next_seq", 1)
    ledger["next_seq"] = seq + 1
    e = {"value": value, "state": state, "seq": seq, "at": _stamp()}
    if note:
        e["note"] = note
    ledger.setdefault("cvs", {})[str(cv)] = e


def ledger_note_reads(ledger, reads):
    for cv, v in sorted(reads.items()):
        ledger_mark(ledger, cv, v, "read")


def clear_ledger(path, cvs):
    """Forget the named CVs (e.g. an unknown one the operator has accepted)."""
    if not os.path.exists(path):
        raise GuardRefusal("no ledger at %s" % path)
    doc = _read_json(path, "ledger")
    keys = [str(_cv_key(cv, "clear-ledger")) for cv in cvs]
    for k in keys:
        doc.get("cvs", {}).pop(k, None)
    _write_json(path, doc)
    return keys


def archive_ledger(ledger_dir, roster_id):
    """Move the ledger aside after the programming-track read-back; returns the new path."""
    path = ledger_path(ledger_dir, roster_id)
    if not os.path.exists(path):
        raise GuardRefusal("no ledger at %s" % path)
    dest = os.path.join(ledger_dir, "%s.%s.json" % (
        safe_name(roster_id), time.strftime("%Y%m%dT%H%M%S")))
    if os.path.exists(dest):
        raise GuardRefusal("%s already exists" % dest)
    os.rename(path, dest)
    return dest


def old_value(cv, reads, ledger, roster_cvs):
    """(value, source) by precedence: read this run > ledger (read or sent) > roster."""
    if cv in reads:
        return reads[cv], "read"
    le = (ledger or {}).get("cvs", {}).get(str(cv))
    if le is not None:
        if le["state"] == "unknown":
            raise GuardRefusal("CV%d is unknown in the ledger since %s (%s): read it, or clear it "
                               "with clear-ledger, first" % (cv, le.get("at"),
                                                            le.get("note", "write not confirmed")))
        return le["value"], "ledger"
    if cv in roster_cvs:
        return roster_cvs[cv], "roster"
    raise GuardRefusal("CV%d has no read, ledger or roster value; no rollback possible" % cv)


# ---------------------------------------------------------------- proposal and plan

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


def prepare(proposal, roster, consist_state, absent_ok=()):
    """Every check that does not need old values: proposal, roster target, consist.

    Returns the context plan_rows() needs. pom_write.py calls this once after the consist
    query and before it reads; build_plan() is prepare() + plan_rows().
    """
    rid, writes = validate_proposal(proposal)
    entry = check_roster_target(roster, rid)
    nodes = query_nodes(roster, rid)
    notes = check_no_consist(consist_state, nodes, absent_ok)
    return {"roster_id": rid, "address": entry["address"], "long": entry["long"],
            "train_node": nodes[0][1], "checked_nodes": [n for _, n in nodes],
            "notes": notes, "writes": writes, "roster_cvs": entry["cvs"]}


def plan_rows(ctx, reads=None, ledger=None):
    """The plan: one row per CV with its old value and where that came from."""
    reads = validate_reads(reads)
    rows = []
    for cv, new in ctx["writes"]:
        old, src = old_value(cv, reads, ledger, ctx["roster_cvs"])
        rows.append({"cv": cv, "old": old, "old_source": src, "new": new,
                     "skip": src == "read" and old == new})
    plan = dict((k, v) for k, v in ctx.items() if k not in ("writes", "roster_cvs"))
    plan["rows"] = rows
    return plan


def build_plan(proposal, roster, consist_state, absent_ok=(), reads=None, ledger=None):
    """Validate everything and return the plan dict, or raise GuardRefusal."""
    return plan_rows(prepare(proposal, roster, consist_state, absent_ok), reads, ledger)


def recheck_row(plan, row):
    """Defence in depth: the per-write checks again, right before the write."""
    check_address(plan["address"], plan["long"])
    check_cv_value(row["cv"], row["new"])
    if row.get("skip") and row["old_source"] != "read":
        raise GuardRefusal("CV%d marked skip without a read" % row["cv"])


def plan_lines(plan):
    tag = "%d%s" % (plan["address"], "L" if plan["long"] else "S")
    lines = ["PLAN %s address %s (%s) train node %s" % (
        plan["roster_id"], tag, "long" if plan["long"] else "short", plan["train_node"])]
    lines.extend(plan.get("notes", []))
    for r in plan["rows"]:
        same = " (read this run, same, skipped)" if r["skip"] else ""
        lines.append("PLAN %s CV%d old=%d (%s) new=%d%s" % (
            tag, r["cv"], r["old"], r["old_source"], r["new"], same))
    return lines


def rollback_doc(plan):
    srcs = sorted(set(r["old_source"] for r in plan["rows"]))
    return {
        "roster_id": plan["roster_id"],
        "address": plan["address"],
        "long": plan["long"],
        "made": _stamp(),
        "old_values_from": srcs[0] if len(srcs) == 1 else "mixed",
        "note": "Rollback written by pom_guard before the first write. old_source: 'read' from "
                "the decoder this run, 'ledger' the value last read or sent, 'roster' the "
                "roster's recorded value.",
        "writes": [{"cv": r["cv"], "value": r["old"], "old_source": r["old_source"]}
                   for r in plan["rows"]],
    }


def execute(plan, write_cv, apply=False, consists_broken=False, rollback_path=None, ledger=None,
            ledger_file=None, log=None):
    """Dry run unless apply is True. write_cv(cv, value) -> (state, text), state one of
    "ok", "failed", "timeout".

    Dry run: prints the plan; with a rollback_path it saves the would-be rollback as
    <rollback_path>.dryrun. Apply (needs consists_broken=True, a ledger and a new rollback
    path): writes the rollback file first, then each CV in order; an OK write is recorded in
    the ledger; a failed or timed-out write marks the CV unknown, stops, and logs the exact
    recovery steps. Returns {"applied", "written", "failed", "timed_out"}.
    """
    log = log or (lambda m: None)
    for line in plan_lines(plan):
        log(line)
    result = {"applied": False, "written": [], "failed": None, "timed_out": False}
    if apply is not True:
        if rollback_path:
            _write_json(rollback_path + ".dryrun", rollback_doc(plan))
            log("DRY RUN would-be rollback saved %s.dryrun" % rollback_path)
        log("DRY RUN: nothing written (set APPLY = True to write)")
        return result
    if consists_broken is not True:
        raise GuardRefusal("apply needs CONSISTS_BROKEN = True: confirm every consist involving "
                           "%r is broken (cs105_consist.py detach), including leads not in the roster"
                           % plan["roster_id"])
    log("CONSISTS_BROKEN confirmed by the operator")
    if not rollback_path:
        raise GuardRefusal("apply needs a rollback file path")
    if ledger is None or not ledger_file:
        raise GuardRefusal("apply needs the loco's ledger file")
    if os.path.exists(rollback_path):
        raise GuardRefusal("rollback file %s already exists; keep it and pick a new name" % rollback_path)
    _write_json(rollback_path, rollback_doc(plan))
    log("ROLLBACK written %s" % rollback_path)
    result["applied"] = True
    for r in plan["rows"]:
        recheck_row(plan, r)
        if r["skip"]:
            log("SKIP CV%d read %d this run" % (r["cv"], r["new"]))
            continue
        state, text = write_cv(r["cv"], r["new"])
        if state == "ok":
            ledger_mark(ledger, r["cv"], r["new"], "sent")
            _write_json(ledger_file, ledger)
            log("WRITE CV%d=%d OK %s" % (r["cv"], r["new"], text))
            result["written"].append(r["cv"])
            continue
        ledger_mark(ledger, r["cv"], None, "unknown", note="%s: %s" % (state, text))
        _write_json(ledger_file, ledger)
        result["failed"] = r["cv"]
        result["timed_out"] = state == "timeout"
        log("WRITE CV%d=%d %s %s%s" % (r["cv"], r["new"], state.upper(), text,
                                      ": the CV may have been written" if state == "timeout" else ""))
        log("STOPPED at CV%d (%s): it may hold %d (new) or %d (old) and is marked unknown in the "
            "ledger. Writes before it stand. To roll back: 1) python3 pom_guard.py clear-ledger %s "
            "CV%d  2) apply %s as the proposal (APPLY = True, a new ROLLBACK name)" % (
                r["cv"], state, r["new"], r["old"], ledger_file, r["cv"], rollback_path))
        return result
    log("DONE %d write(s)" % len(result["written"]))
    return result


# ---------------------------------------------------------------- CLI

def _main(argv):
    try:
        if argv[:1] == ["clear-ledger"]:
            if len(argv) < 3:
                sys.stdout.write("usage: pom_guard.py clear-ledger <ledger file> CV [CV ...]\n")
                return 2
            keys = clear_ledger(argv[1], argv[2:])
            sys.stdout.write("cleared CV %s in %s\n" % (", ".join(keys), argv[1]))
            return 0
        if argv[:1] == ["archive-ledger"]:
            import argparse
            ap = argparse.ArgumentParser(prog="pom_guard.py archive-ledger")
            ap.add_argument("roster_id")
            ap.add_argument("--ledger-dir", default=os.path.expanduser("~/speedmatch/ledger"))
            a = ap.parse_args(argv[1:])
            sys.stdout.write("archived to %s\n" % archive_ledger(a.ledger_dir, a.roster_id))
            return 0
        import argparse
        ap = argparse.ArgumentParser(description="Dry-run a POM proposal against a roster and consist log.")
        ap.add_argument("proposal")
        ap.add_argument("--roster-dir", required=True, help="folder holding roster.xml and roster/")
        ap.add_argument("--consist-log", required=True, help="cs105_consist.py query log over every roster node")
        ap.add_argument("--absent-ok", action="append", default=[], help="roster id allowed not to answer")
        ap.add_argument("--reads", help="JSON {cv: value} read from the decoder")
        ap.add_argument("--ledger", help="the loco's ledger file")
        a = ap.parse_args(argv)
        f = open(a.consist_log)
        try:
            state = parse_consist_log(f.read())
        finally:
            f.close()
        proposal = load_proposal(a.proposal)
        reads = validate_reads(_read_json(a.reads, "reads")) if a.reads else {}
        ledger = load_ledger(a.ledger, proposal.get("roster_id")) if a.ledger else None
        plan = build_plan(proposal, load_roster(a.roster_dir), state, absent_ok=a.absent_ok,
                          reads=reads, ledger=ledger)
    except GuardRefusal as e:
        sys.stdout.write("REFUSED %s\n" % e)
        return 2
    execute(plan, None, apply=False, log=lambda m: sys.stdout.write(m + "\n"))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
