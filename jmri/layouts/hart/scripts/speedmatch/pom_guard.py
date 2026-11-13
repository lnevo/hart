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
  CV29 bit 5), another roster entry with the same address number (either flag), and a
  roster.xml entry with no id. CV19 (advanced consist) is refused when a read or the
  ledger says it is not 0; a roster-only CV19 is a WARNING, because roster CVvalues can be
  decoder-definition defaults (BO 3545 and BO 6944 record 127).
* Consist: the caller supplies the cs105_consist.py ACTION=query log for the train node of
  every roster entry (query_nodes() gives the list). Refused unless the log is complete
  (a line that is exactly END, no ERROR or decode error), covers every node, lists each
  node's listener indices exactly 0..count-1 once each, the target answered with 0
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
  all is refused (no rollback possible). Roster values are tagged "roster (may be a
  default)", and an apply that relies on any of them needs roster_old_ok=True
  (ROSTER_OLD_OK); seed-ledger records a programming-track preflight read instead.
* Skips: a CV is skipped as "already holds the value" only when its old value came from a
  read in this run. Ledger and roster values are never trusted for a skip.
* Apply: execute() writes only when apply is exactly True, consists_broken is True, and it
  has a ledger file and a rollback path that does not already exist. The rollback file
  (same precedence) is written before the first write. The ledger records each OK write; a
  write that is not OK marks the CV "unknown", writes <rollback>.partial.json (the CVs
  this run touched), stops the run, and the log names the exact recovery steps. One run
  per loco at a time: pom_write.py holds <ledger dir>/<roster id>.lock, as do the ledger
  subcommands.

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

Mac dry run (never writes; warns when it finds no ledger, since the Pi's may differ):

    python3 pom_guard.py proposal.json --roster-dir <JMRI user files dir> \
        --consist-log consist.log [--absent-ok "NWR 06" ...] [--reads reads.json] \
        [--ledger-dir DIR]            # default ~/speedmatch/ledger, as on the Pi

Ledger upkeep (on the Pi, where the ledger lives; each takes --ledger-dir DIR):

    python3 pom_guard.py seed-ledger "CSX 2738" preflight.log   programming-track read -> "read"
    python3 pom_guard.py clear-ledger "CSX 2738" CV68 [CV69 ...]   accept an unknown CV
    python3 pom_guard.py archive-ledger "CSX 2738"                 after the read-back

A preflight log is JSON ({"roster_id": .., "cvs": {cv: value}} or a bare {cv: value}) or
text with one "CV<n> = <value>" per line.
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

DEFAULT_LEDGER_DIR = os.path.expanduser("~/speedmatch/ledger")
ROSTER_TAG = "roster (may be a default)"


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


def _read_text(path, what):
    try:
        f = open(path, "r")
        try:
            return f.read()
        finally:
            f.close()
    except (IOError, OSError) as e:
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
    doc = _read_json(path, "proposal")
    if not isinstance(doc, dict):
        raise GuardRefusal("proposal %s is not a JSON object" % path)
    return doc


def safe_name(roster_id):
    if not isinstance(roster_id, (type(u""), type(""))) or not roster_id:
        raise GuardRefusal("roster id %r is not a name" % (roster_id,))
    return re.sub(r"[^A-Za-z0-9_-]+", "_", roster_id).strip("_") or "loco"


def ledger_path(ledger_dir, roster_id):
    return os.path.join(ledger_dir, safe_name(roster_id) + ".json")


def lock_path(ledger_dir, roster_id):
    return os.path.join(ledger_dir, safe_name(roster_id) + ".lock")


def acquire_lock(path, owner):
    """Create the lock exclusively; a lock that is already there is refused."""
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except OSError:
        raise GuardRefusal("lock %s exists: another run may be going. If none is (its log ends with "
                           "END), remove the lock by hand and run again" % path)
    try:
        os.write(fd, ("%s %s\n" % (_stamp(), owner)).encode("utf-8"))
    finally:
        os.close(fd)
    return path


def release_lock(path):
    if path and os.path.exists(path):
        os.remove(path)


class Locked(object):
    """with Locked(ledger_dir, roster_id, owner): ... for the CLI subcommands."""

    def __init__(self, ledger_dir, roster_id, owner):
        self.path = lock_path(ledger_dir, roster_id)
        self.owner = owner

    def __enter__(self):
        acquire_lock(self.path, self.owner)
        return self

    def __exit__(self, *exc):
        release_lock(self.path)
        return False


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


def clear_ledger(ledger_dir, roster_id, cvs):
    """Forget the named CVs (an unknown one the operator has accepted). Validated like any load."""
    path = ledger_path(ledger_dir, roster_id)
    if not os.path.exists(path):
        raise GuardRefusal("no ledger at %s" % path)
    doc = load_ledger(path, roster_id)
    keys = [str(_cv_key(cv, "clear-ledger")) for cv in cvs]
    for k in keys:
        doc["cvs"].pop(k, None)
    _write_json(path, doc)
    return keys


def archive_ledger(ledger_dir, roster_id):
    """Move the ledger aside after the programming-track read-back; returns the new path."""
    path = ledger_path(ledger_dir, roster_id)
    if not os.path.exists(path):
        raise GuardRefusal("no ledger at %s" % path)
    load_ledger(path, roster_id)
    dest = os.path.join(ledger_dir, "%s.%s.json" % (
        safe_name(roster_id), time.strftime("%Y%m%dT%H%M%S")))
    if os.path.exists(dest):
        raise GuardRefusal("%s already exists" % dest)
    os.rename(path, dest)
    return dest


_PREFLIGHT_LINE = re.compile(r"\bCV\s*(\d+)\s*[=:]\s*(\d+)\b", re.I)


def parse_preflight(text, roster_id):
    """{cv: value} from a programming-track preflight log.

    Either JSON ({"roster_id": .., "cvs" or "reads": {cv: value}} or a bare {cv: value}),
    or text with one "CV<n> = <value>" (or "CV<n>: <value>") per line. A JSON log naming
    another roster id is refused; the same CV with two different values is refused.
    """
    try:
        doc = json.loads(text)
    except ValueError:
        doc = None
    if isinstance(doc, dict):
        if "roster_id" in doc and doc["roster_id"] != roster_id:
            raise GuardRefusal("preflight log is for %r, not %r" % (doc["roster_id"], roster_id))
        raw = doc.get("cvs", doc.get("reads", doc))
        raw = dict((k, v) for k, v in raw.items() if k != "roster_id")
        out = validate_reads(raw, "preflight")
    else:
        out = {}
        for m in _PREFLIGHT_LINE.finditer(text):
            cv, v = int(m.group(1)), int(m.group(2))
            if v > 255:
                raise GuardRefusal("preflight CV%d value %d is not 0-255" % (cv, v))
            if cv in out and out[cv] != v:
                raise GuardRefusal("preflight gives CV%d twice (%d and %d)" % (cv, out[cv], v))
            out[cv] = v
    if not out:
        raise GuardRefusal("preflight log has no CV values")
    return out


def seed_ledger(ledger_dir, roster_id, preflight_text):
    """Record a programming-track read as state "read" in the ledger. Returns the CVs seeded."""
    reads = parse_preflight(preflight_text, roster_id)
    path = ledger_path(ledger_dir, roster_id)
    led = load_ledger(path, roster_id)
    ledger_note_reads(led, reads)
    _write_json(path, led)
    return sorted(reads)


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
        return roster_cvs[cv], ROSTER_TAG
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
    entry, warnings = check_roster_target(roster, rid)
    nodes = query_nodes(roster, rid)
    notes = check_no_consist(consist_state, nodes, absent_ok)
    return {"roster_id": rid, "address": entry["address"], "long": entry["long"],
            "train_node": nodes[0][1], "checked_nodes": [n for _, n in nodes],
            "notes": warnings + notes, "writes": writes, "roster_cvs": entry["cvs"]}


def plan_rows(ctx, reads=None, ledger=None):
    """The plan: one row per CV with its old value and where that came from.

    Refuses if CV19 read this run or recorded in the ledger is not 0 (advanced consist).
    """
    reads = validate_reads(reads)
    for src, val in (("read", reads.get(19)),
                     ("ledger", ((ledger or {}).get("cvs", {}).get("19") or {}).get("value"))):
        if val is not None and val & 0x7F:
            raise GuardRefusal("%r: CV19 = %d (%s): the decoder is in an advanced consist" % (
                ctx["roster_id"], val, src))
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


def rollback_doc(plan, rows=None):
    rows = plan["rows"] if rows is None else rows
    srcs = sorted(set(r["old_source"] for r in rows))
    return {
        "roster_id": plan["roster_id"],
        "address": plan["address"],
        "long": plan["long"],
        "made": _stamp(),
        "old_values_from": srcs[0] if len(srcs) == 1 else "mixed",
        "note": "Rollback written by pom_guard. old_source: 'read' from the decoder this run, "
                "'ledger' the value last read or sent, 'roster' the roster's recorded value, "
                "which may be a decoder-definition default.",
        "writes": [{"cv": r["cv"], "value": r["old"],
                    "old_source": "roster" if r["old_source"] == ROSTER_TAG else r["old_source"]}
                   for r in rows],
    }


def execute(plan, write_cv, apply=False, consists_broken=False, roster_old_ok=False,
            rollback_path=None, ledger=None, ledger_file=None, log=None):
    """Dry run unless apply is True. write_cv(cv, value) -> (state, text); state "ok" or
    anything else ("failed", "timeout", "exception").

    Dry run: prints the plan; with a rollback_path it saves the would-be rollback as
    <rollback_path>.dryrun. Apply needs consists_broken=True, roster_old_ok=True when any old
    value comes from the roster, a ledger and a new rollback path. It writes the full
    rollback file first, then each CV in order; an OK write is recorded in the ledger. A
    write that is not OK marks the CV unknown, writes <rollback>.partial.json (the CVs
    written so far plus that one), stops, and logs the exact recovery steps.
    Returns {"applied", "written", "failed", "timed_out", "partial"}.
    """
    log = log or (lambda m: None)
    for line in plan_lines(plan):
        log(line)
    result = {"applied": False, "written": [], "failed": None, "timed_out": False, "partial": None}
    roster_rows = [r["cv"] for r in plan["rows"] if r["old_source"] == ROSTER_TAG]
    if apply is not True:
        if rollback_path:
            _write_json(rollback_path + ".dryrun", rollback_doc(plan))
            log("DRY RUN would-be rollback saved %s.dryrun" % rollback_path)
        if roster_rows:
            log("NOTE old values for CV %s come from the roster and may be defaults; apply needs "
                "ROSTER_OLD_OK = True, or seed the ledger from a programming-track read first"
                % ", ".join(str(c) for c in roster_rows))
        log("DRY RUN: nothing written (set APPLY = True to write)")
        return result
    if consists_broken is not True:
        raise GuardRefusal("apply needs CONSISTS_BROKEN = True: confirm every consist involving "
                           "%r is broken (cs105_consist.py detach), including leads not in the roster"
                           % plan["roster_id"])
    log("CONSISTS_BROKEN confirmed by the operator")
    if roster_rows:
        if roster_old_ok is not True:
            raise GuardRefusal("old values for CV %s would come from the roster, which may hold "
                               "defaults: seed the ledger from a programming-track read "
                               "(seed-ledger), or set ROSTER_OLD_OK = True" %
                               ", ".join(str(c) for c in roster_rows))
        log("ROSTER_OLD_OK confirmed by the operator for CV %s" % ", ".join(str(c) for c in roster_rows))
    if not rollback_path:
        raise GuardRefusal("apply needs a rollback file path")
    if ledger is None or not ledger_file:
        raise GuardRefusal("apply needs the loco's ledger file")
    if os.path.exists(rollback_path):
        raise GuardRefusal("rollback file %s already exists; keep it and pick a new name" % rollback_path)
    _write_json(rollback_path, rollback_doc(plan))
    log("ROLLBACK written %s" % rollback_path)
    result["applied"] = True
    done = []
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
            done.append(r)
            continue
        ledger_mark(ledger, r["cv"], None, "unknown", note="%s: %s" % (state, text))
        _write_json(ledger_file, ledger)
        partial = rollback_path + ".partial.json"
        _write_json(partial, rollback_doc(plan, done + [r]))
        result.update(failed=r["cv"], timed_out=(state == "timeout"), partial=partial)
        log("WRITE CV%d=%d %s %s%s" % (r["cv"], r["new"], state.upper(), text,
                                      "" if state == "failed" else ": the CV may have been written"))
        log("STOPPED at CV%d (%s): it may hold %d (new) or %d (old) and is marked unknown in the "
            "ledger. Writes before it stand. To roll back: 1) python3 pom_guard.py clear-ledger "
            "\"%s\" CV%d --ledger-dir %s  2) apply %s as the proposal (APPLY = True, a new ROLLBACK "
            "name; it holds only the CVs this run touched)" % (
                r["cv"], state, r["new"], r["old"], plan["roster_id"], r["cv"],
                os.path.dirname(ledger_file), partial))
        return result
    log("DONE %d write(s)" % len(result["written"]))
    return result


# ---------------------------------------------------------------- CLI

def _main(argv):
    import argparse
    try:
        if argv[:1] in (["clear-ledger"], ["archive-ledger"], ["seed-ledger"]):
            cmd = argv[0]
            ap = argparse.ArgumentParser(prog="pom_guard.py " + cmd)
            ap.add_argument("roster_id")
            if cmd == "clear-ledger":
                ap.add_argument("cvs", nargs="+", help="CV68 or 68")
            if cmd == "seed-ledger":
                ap.add_argument("preflight_log")
            ap.add_argument("--ledger-dir", default=DEFAULT_LEDGER_DIR)
            a = ap.parse_args(argv[1:])
            with Locked(a.ledger_dir, a.roster_id, "pom_guard.py " + cmd):
                if cmd == "clear-ledger":
                    keys = clear_ledger(a.ledger_dir, a.roster_id, a.cvs)
                    sys.stdout.write("cleared CV %s for %r; their old values now come from the roster "
                                     "(may be defaults) until read\n" % (", ".join(keys), a.roster_id))
                elif cmd == "archive-ledger":
                    sys.stdout.write("archived to %s\n" % archive_ledger(a.ledger_dir, a.roster_id))
                else:
                    cvs = seed_ledger(a.ledger_dir, a.roster_id, _read_text(a.preflight_log, "preflight log"))
                    sys.stdout.write("seeded %d CV(s) as read for %r\n" % (len(cvs), a.roster_id))
            return 0
        ap = argparse.ArgumentParser(description="Dry-run a POM proposal against a roster and consist log.")
        ap.add_argument("proposal")
        ap.add_argument("--roster-dir", required=True, help="folder holding roster.xml and roster/")
        ap.add_argument("--consist-log", required=True, help="cs105_consist.py query log over every roster node")
        ap.add_argument("--absent-ok", action="append", default=[], help="roster id allowed not to answer")
        ap.add_argument("--reads", help="JSON {cv: value} read from the decoder")
        ap.add_argument("--ledger-dir", default=DEFAULT_LEDGER_DIR,
                        help="ledger folder (default %s, the same as on the Pi)" % DEFAULT_LEDGER_DIR)
        a = ap.parse_args(argv)
        state = parse_consist_log(_read_text(a.consist_log, "consist log"))
        proposal = load_proposal(a.proposal)
        rid, _ = validate_proposal(proposal)
        lpath = ledger_path(a.ledger_dir, rid)
        if not os.path.exists(lpath):
            sys.stdout.write("WARNING no ledger at %s: old values come from the roster here; the Pi's "
                             "ledger may differ, so the Pi's plan may differ\n" % lpath)
        reads = validate_reads(_read_json(a.reads, "reads")) if a.reads else {}
        plan = build_plan(proposal, load_roster(a.roster_dir), state, absent_ok=a.absent_ok,
                          reads=reads, ledger=load_ledger(lpath, rid))
    except GuardRefusal as e:
        sys.stdout.write("REFUSED %s\n" % e)
        return 2
    execute(plan, None, apply=False, log=lambda m: sys.stdout.write(m + "\n"))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
