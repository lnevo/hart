#!/usr/bin/env python3
"""Turn analyze.py's profile.csv into the payload that write_profile.py puts in a roster entry.

    profile_to_roster.py profile.csv --loco "CSX 2121" --out /tmp/sm/payload_2121.json

Per direction it takes the latest complete run of the loco, and from it only the steps that
ended with reason `settled` (or `timed`, distance mode); the repeat of the top step (`126#2`) is skipped. A point needs a
speed in both directions, so only steps present in both are written; the others are listed
as skipped. It refuses if either direction has no complete run or no settled step.

With --merge, a direction's complete runs are combined: per step, the latest complete run that
settled it. Use it when a short re-run (say steps 8,16,24 after a CV change) follows a full run;
the payload lists which run each speed came from (`sources`).

The payload is {roster_id, points: [{step, forward_mm_s, reverse_mm_s}]}. Nothing is written
to a roster here: make_job.py profile builds the Jython job from it.
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze  # noqa: E402
import correct  # noqa: E402


class ProfileRefusal(Exception):
    """The data cannot make a complete profile."""


def merged_steps(path, loco, direction, route=analyze.DEFAULT_ROUTE):
    """(dict step -> mm/s, dict step -> run): per step, the latest complete run of (loco,
    direction) that settled it; latest by the time in the log name."""
    with open(path, newline="") as fh:
        mine = [r for r in csv.DictReader(fh) if r["loco"] == loco and r["direction"] == direction
                and (r.get("route") or analyze.DEFAULT_ROUTE) == route]
    stamp = {}
    for r in mine:
        m = re.search(r"_(\d{8}_\d{6})\.log$", r.get("log") or "")
        stamp.setdefault(int(r.get("run") or 1), m.group(1) if m else "")
    # oldest first by the time in the log name (run number when a name has none), so a later
    # run always wins whatever order the logs were given to analyze.py in
    done = sorted({int(r.get("run") or 1) for r in mine if (r.get("run_complete") or "True") == "True"},
                  key=lambda n: (stamp.get(n, ""), n))
    if not done:
        raise ProfileRefusal("%s %s: no complete run in profile.csv" % (loco, direction))
    out, src = {}, {}
    for n in done:
        got, _skipped = correct.read_profile(path, loco, direction, run=n, route=route)
        for step, v in got.items():
            out[step] = v
            src[step] = n
    if not out:
        raise ProfileRefusal("%s %s: no complete run has a settled step" % (loco, direction))
    return out, src


def settled_steps(path, loco, direction, route=analyze.DEFAULT_ROUTE):
    """dict step -> mm/s for the latest complete run of (loco, direction) in profile.csv. The
    reading of the file is correct.read_profile's (settled steps only, repeats skipped); this
    adds the refusals a roster write needs."""
    with open(path, newline="") as fh:
        mine = [r for r in csv.DictReader(fh) if r["loco"] == loco and r["direction"] == direction
                and (r.get("route") or analyze.DEFAULT_ROUTE) == route]
    if not mine:
        raise ProfileRefusal("%s %s: no row for route %s in profile.csv" % (loco, direction, route))
    if not any((r.get("run_complete") or "True") == "True" for r in mine):
        raise ProfileRefusal("%s %s: no complete run in profile.csv" % (loco, direction))
    out, _skipped = correct.read_profile(path, loco, direction, route=route)
    if not out:
        raise ProfileRefusal("%s %s: the latest complete run has no settled step" % (loco, direction))
    return out


def throttle_key(step):
    """RosterSpeedProfile key: throttle setting (step / 126) times 1000, rounded."""
    return int(round(step / 126.0 * 1000))


def build_payload(path, loco, route=analyze.DEFAULT_ROUTE, merge=False):
    if merge:
        fwd, fsrc = merged_steps(path, loco, "forward", route)
        rev, rsrc = merged_steps(path, loco, "reverse", route)
    else:
        fwd = settled_steps(path, loco, "forward", route)
        rev = settled_steps(path, loco, "reverse", route)
    both = sorted(set(fwd) & set(rev))
    if not both:
        raise ProfileRefusal("%s: no step settled in both directions" % loco)
    payload = {
        "roster_id": loco,
        "points": [{"step": s, "forward_mm_s": fwd[s], "reverse_mm_s": rev[s]} for s in both],
        "skipped_steps": sorted(set(fwd) ^ set(rev)),
    }
    if merge:
        payload["sources"] = [{"step": s, "forward_run": fsrc[s], "reverse_run": rsrc[s]} for s in both]
    return payload


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("profile_csv")
    ap.add_argument("--loco", required=True, help='roster id, e.g. "CSX 2121"')
    ap.add_argument("--route", choices=sorted(analyze.ROUTES), default=analyze.DEFAULT_ROUTE,
                    help="route of the runs to take the speeds from")
    ap.add_argument("--out", required=True, help="payload JSON to write")
    ap.add_argument("--merge", action="store_true",
                    help="combine complete runs: per step, the latest complete run that settled it")
    a = ap.parse_args(argv)
    try:
        payload = build_payload(a.profile_csv, a.loco, a.route, merge=a.merge)
    except ProfileRefusal as e:
        sys.exit("refused: %s" % e)
    Path(a.out).write_text(json.dumps(payload, indent=2) + "\n")
    print("wrote %s: %d points for %s%s" % (
        a.out, len(payload["points"]), a.loco,
        "; steps in one direction only, left out: %s" % payload["skipped_steps"] if payload["skipped_steps"] else ""))


if __name__ == "__main__":
    main()
