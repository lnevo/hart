#!/usr/bin/env python3
"""Compare the CVs a preflight read (jython/preflight.py) found with the roster entry.

The roster entry is a DecoderPro XML file (~/JMRI_UserFiles/roster/<file>.xml on the Mac,
the Pi is the master). Its <locomotive> holds <values> with one <CVvalue name="67" value="0"/>
per CV. The preflight log has lines "<epoch> CV <n> <value>" or "<epoch> CV <n> FAIL ...".

    preflight_compare.py --log preflight.log --roster-xml ~/JMRI_UserFiles/roster/2738.xml \\
        [--save cvs.json]

Exit status 0 when every CV read matches, 1 on any difference or failed read. Run it before
each speed run and stop if it says DIFFERENT. It reads files only.
"""
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def roster_cvs(path, loco_id=None):
    """dict CV number -> value from a roster XML file. loco_id picks one <locomotive> when
    the file holds several; otherwise the first."""
    root = ET.parse(str(path)).getroot()
    locos = [e for e in root.iter("locomotive") if loco_id in (None, e.get("id"))]
    if not locos:
        raise ValueError("no locomotive %r in %s" % (loco_id, path))
    out = {}
    for e in locos[0].iter("CVvalue"):
        try:
            out[int(e.get("name"))] = int(e.get("value"))
        except (TypeError, ValueError):
            continue
    return out


_READ = re.compile(r"^[\d.]+ CV (\d+) (FAIL.*|\d+)\s*$")


def parse_preflight(lines):
    """(values, failures): dict CV -> value read, dict CV -> failure text. Later lines win."""
    values, fails = {}, {}
    for line in lines:
        m = _READ.match(line.strip())
        if not m:
            continue
        cv, rest = int(m.group(1)), m.group(2)
        if rest.startswith("FAIL"):
            fails[cv] = rest
            values.pop(cv, None)
        else:
            values[cv] = int(rest)
            fails.pop(cv, None)
    return values, fails


# The CVs every preflight must have read (CV2 to 6, 25, 29, 66, the 28 table entries, 95).
# make_job.py builds the job from this list; a back-EMF family adds its own.
BASE_CVS = [2, 3, 4, 5, 6, 25, 29, 66] + list(range(67, 95)) + [95]


def log_problems(lines, expected=None):
    """What makes a preflight log unusable: no END line, an ERROR or ABORTED line, or an
    expected CV that is neither read nor reported as failed. Returns (problems, missing).

    expected defaults to BASE_CVS plus the CVs the job logged as requested (its CVS line)."""
    lines = [l.strip() for l in lines]
    problems = []
    if not any(l.endswith(" END") for l in lines):
        problems.append("no END line: the preflight did not finish")
    for l in lines:
        if " ERROR " in l or " ABORTED" in l or " NO PROGRAMMER" in l:
            problems.append(l.split(" ", 1)[1])
    if expected is None:
        expected = set(BASE_CVS)
        for l in lines:
            if " CVS " in l:
                expected |= {int(x) for x in l.split(" CVS ", 1)[1].split(",") if x.strip().isdigit()}
    values, fails = parse_preflight(lines)
    missing = sorted(set(expected) - set(values) - set(fails))
    if missing:
        problems.append("%d expected CVs missing" % len(missing))
    return problems, missing


def compare(read, fails, roster):
    """List of {cv, read, roster, result}; result is ok, DIFFERENT, FAILED or not in roster."""
    rows = []
    for cv in sorted(set(read) | set(fails)):
        if cv in fails:
            rows.append({"cv": cv, "read": None, "roster": roster.get(cv), "result": "FAILED"})
        elif cv not in roster:
            rows.append({"cv": cv, "read": read[cv], "roster": None, "result": "not in roster"})
        else:
            ok = read[cv] == roster[cv]
            rows.append({"cv": cv, "read": read[cv], "roster": roster[cv],
                         "result": "ok" if ok else "DIFFERENT"})
    return rows


def blocking(rows):
    """Rows that should stop a run. A CV missing from the roster is reported, not blocking."""
    return [r for r in rows if r["result"] in ("DIFFERENT", "FAILED")]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--log", required=True)
    ap.add_argument("--roster-xml", required=True)
    ap.add_argument("--loco-id", help="roster id when the file holds several locomotives")
    ap.add_argument("--expect", help="CVs that must be present, comma separated (default: the "
                    "standard list plus what the job requested)")
    ap.add_argument("--save", help="write the CVs read to this JSON file (a rollback record)")
    a = ap.parse_args(argv)
    lines = Path(a.log).read_text().splitlines()
    expected = {int(x) for x in a.expect.split(",")} if a.expect else None
    problems, missing = log_problems(lines, expected)
    for p in problems:
        print("LOG PROBLEM: " + p)
    if missing:
        print("missing CVs: " + ",".join(str(c) for c in missing))
    read, fails = parse_preflight(lines)
    rows = compare(read, fails, roster_cvs(a.roster_xml, a.loco_id))
    for r in rows:
        if r["result"] != "ok":
            print("CV%-3d read %-5s roster %-5s %s" % (r["cv"], r["read"], r["roster"], r["result"]))
    bad = blocking(rows)
    print("%d CVs compared, %d ok, %d blocking" % (
        len(rows), sum(r["result"] == "ok" for r in rows), len(bad)))
    if a.save:
        Path(a.save).write_text(json.dumps({"read": read, "failed": fails}, indent=2) + "\n")
    return 1 if bad or not rows or problems else 0


if __name__ == "__main__":
    sys.exit(main())
