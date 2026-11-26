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

The command line (the Mac dry run, and the ledger upkeep on the Pi) is in pom_guard_cli.py, next to this file;
`python3 pom_guard.py ...` runs it. The address, roster and consist checks are in pom_guard_roster.py, which this
file imports, so copy the three together (speedmatch.py POM_FILES does).
"""

import json
import os
import re
import sys
import time

# The address, roster and consist checks live in pom_guard_roster.py, next to this file (split for size,
# 2026-11-26). Drop any copy an earlier load left in sys.modules: JMRI's Jython keeps modules between scripts, and
# each pom_write.py run must use the part that came with this guard.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:  # once: JMRI's Jython keeps sys.path between runs
    sys.path.insert(0, _HERE)
sys.modules.pop("pom_guard_roster", None)
from pom_guard_roster import (  # noqa: E402,F401 (re-exported: callers and tests use pom_guard.<name>)
    CV29_LONG_BIT,
    LONG_RANGE,
    SHORT_RANGE,
    GuardRefusal,
    _DOCTYPE,
    _LISTENER,
    _LISTENERS,
    _entry_cvs,
    _is_int,
    _loco_address,
    _parse_xml,
    _yes,
    check_address,
    check_no_consist,
    check_roster_target,
    load_roster,
    parse_consist_log,
    query_nodes,
    train_node,
)


ALLOWED_CVS = frozenset([3, 4, 25, 66, 95] + list(range(67, 95)))
NAMED_REFUSALS = {
    1: "CV1 is the short address",
    17: "CV17 is the long address (high byte)",
    18: "CV18 is the long address (low byte)",
    19: "CV19 is the advanced consist address",
    8: "CV8 is the decoder reset",
    29: "CV29 is set on the programming track only (its real value cannot be read on the main)",
}
WRITE_KEYS = frozenset(["cv", "value", "note", "old_source"])


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

# The Pi's ledger: the guard runs in the Pi's JMRI and its python3 without hartlib, so ~ is the Pi user's home
# (speedmatch.py pom passes LEDGER_DIR from HART_PI_USERFILES). On the Mac a dry run reads ~/speedmatch/ledger.
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


# ---------------------------------------------------------------- CLI (pom_guard_cli.py)

if __name__ == "__main__":
    sys.modules.setdefault("pom_guard", sys.modules[__name__])  # the CLI uses this module, not a second copy
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import pom_guard_cli
    sys.exit(pom_guard_cli._main(sys.argv[1:]))
