"""pom_guard_cli.py - the command line of pom_guard.py: the Mac dry run and the ledger upkeep.

Split out of pom_guard.py on 2026-11-25 with no change in behaviour, so the guard that pom_write.py loads into the
Pi's JMRI stays under the size limit (tools/audit/check_py_sizes.py). `python3 pom_guard.py ...` runs _main() here,
so every command below works under that name too; copy both files together. Same style as the guard (no f-strings,
no print function): the two are read as one.

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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pom_guard import (  # noqa: E402
    GuardRefusal,
    DEFAULT_LEDGER_DIR,
    Locked,
    _cv_key,
    _read_json,
    _read_text,
    _write_json,
    build_plan,
    execute,
    ledger_note_reads,
    ledger_path,
    load_ledger,
    load_proposal,
    load_roster,
    parse_consist_log,
    safe_name,
    validate_proposal,
    validate_reads,
)


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


# "CV 67 12" is what jython/preflight.py logs; "CV67 = 12" and "CV67: 12" are also accepted.
# "CV 67 FAIL ..." lines do not match and are skipped.
_PREFLIGHT_LINE = re.compile(r"^\s*CV\s*(\d+)\s*[=:]?\s+(\d+)\s*$|^\s*CV\s*(\d+)\s*[=:]\s*(\d+)\s*$",
                             re.I | re.M)
_PREFLIGHT_ID = re.compile(r"^PREFLIGHT (.+?) cvs=\d+\s*$", re.M)
_LOG_STAMP = re.compile(r"^\d+\.\d+ ", re.M)  # preflight.py starts each line with time.time()


def _check_preflight_text(text, roster_id):
    """A preflight.py log must be for this loco, finished, and not aborted."""
    m = _PREFLIGHT_ID.search(text)
    if m and m.group(1) != roster_id:
        raise GuardRefusal("preflight log is for %r, not %r" % (m.group(1), roster_id))
    lines = [ln.strip() for ln in text.splitlines()]
    if m:  # a preflight.py log: it has to have finished cleanly
        if "END" not in lines:
            raise GuardRefusal("preflight log has no END line; it is incomplete")
        bad = [ln for ln in lines if ln.startswith("ABORTED") or ln.startswith("ERROR")]
        if bad:
            raise GuardRefusal("preflight log did not finish cleanly: %s" % bad[0])


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
        text = _LOG_STAMP.sub("", text)
        _check_preflight_text(text, roster_id)
        out = {}
        for m in _PREFLIGHT_LINE.finditer(text):
            g = m.groups()
            cv, v = (int(g[0]), int(g[1])) if g[0] is not None else (int(g[2]), int(g[3]))
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
