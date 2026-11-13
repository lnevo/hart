#!/usr/bin/env python3
"""Measured correction of a 28-entry speed table (CV67-CV94). Proposes; never writes.

Table entry k (1..28) acts at throttle step 126*k/28 (126-step mode, interpolated), the
assumption already used by the 2026-11-08 propose_table.py. For each entry the loco's
measured speed there is compared with the target speed (2121's profile in the paired
direction), and the entry is scaled by target / measured. Entries within the tolerance
(default 3%) are left alone. An entry that is changed is clamped to 1..255 and never
moved the wrong way by the clamp. The table is kept non-decreasing: an entry below its
predecessor is raised, but a deliberate cut pulls the higher entries before it down instead
(unless they are themselves out of tolerance, then the cut is blocked).

This module does not touch a decoder. Its output (proposal.json and proposal.csv) is what
the write guard (pom_guard.py) takes; address, long/short flag and the consist check come
from the roster there, not from here.

    correct.py --table 0,26,... --profile profile.csv --loco "CSX 2738" --direction reverse \\
        --target-loco "CSX 2121" --target-direction forward --round 1 --out proposal/

Exit status: 0 every anchor within tolerance (done), 2 a proposal was written (apply it,
measure again, run this again with --round N+1), 3 out of rounds and still outside, a cut blocked by the rising table (status
blocked), or no entry able to change (status stuck); proposal.json gives the reason. Only
status continue carries writes.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import analyze
import liverule as lr

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

N = 28
CV_START = 67
ANCHOR_STEPS = [126.0 * k / N for k in range(1, N + 1)]
TOLERANCE = 0.03
MAX_ROUNDS = 5
RAISED_NOTE = "raised to keep the table rising"
LOWERED_NOTE = "lowered to follow a cut"
BLOCKED_NOTE = "cut blocked by the rising table; kept at its old value"
CAPPED_NOTE = "raise capped at the blocked entry's old value"


def interp(x, pts):
    """Linear interpolation over (step, speed) points. None outside the measured range:
    nothing is extrapolated, above or below."""
    pts = sorted(pts)
    if not pts or x < pts[0][0] or x > pts[-1][0]:
        return None
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[0][1]  # a single point


def propose(table, measured, target, tol=TOLERANCE, gain=1.0, max_ratio=1.5):
    """Propose a corrected table.

    table     28 current values (CV67..CV94)
    measured  {step: mm/s} of the loco being corrected, with the current table
    target    {step: mm/s} to match (e.g. 2121's profile in the paired direction)
    tol       relative tolerance (0.03 = 3%)
    gain      1.0 applies the whole measured ratio; less applies a fraction
    max_ratio the largest factor one round may apply to an entry (and its inverse)

    Returns {"values": [28 ints], "anchors": [per entry dict], "all_within": bool}.
    Each anchor dict: k, cv, step, old, new, measured, target, error (measured/target - 1),
    within, note.
    """
    if len(table) != N:
        raise ValueError("a speed table has %d entries, got %d" % (N, len(table)))
    mp, tp = list(measured.items()), list(target.items())
    anchors, raw = [], []
    for k, (old, step) in enumerate(zip(table, ANCHOR_STEPS), start=1):
        old = int(old)
        m, t = interp(step, mp), interp(step, tp)
        row = {"k": k, "cv": CV_START + k - 1, "step": round(step, 2), "old": old,
               "measured": m, "target": t, "error": None, "within": None, "note": "",
               "kind": "keep"}
        val = old
        if not m or not t or m <= 0 or t <= 0:
            row["note"] = "no usable measurement (outside the measured steps or none)"
        else:
            row["error"] = m / t - 1.0
            row["within"] = abs(row["error"]) <= tol
            if not row["within"]:
                ratio = max(1.0 / max_ratio, min(max_ratio, (t / m) ** gain))
                val = int(round(old * ratio))
                if ratio > 1:   # raised: never lowered by rounding or the clamp
                    row["kind"] = "raise"
                    val = max(old, min(255, max(val, old + 1)))
                    if val >= 255:
                        row["note"] = "reaches 255: this loco may not be able to reach the target here"
                else:           # cut: never raised by rounding or the clamp
                    row["kind"] = "cut"
                    val = min(old, max(1, min(val, old - 1)))
                    if val == old:
                        row["note"] = "already at the floor"
        if val == old:
            row["kind"] = "keep" if row["within"] is not False else row["kind"]
        anchors.append(row)
        raw.append(val)
    # an entry at 0..2 that must rise would creep up by 1 a round: start it from its neighbour
    for i in range(N - 2, -1, -1):
        if anchors[i]["kind"] == "raise" and anchors[i]["old"] <= 2:
            guess = int(round(raw[i + 1] * ANCHOR_STEPS[i] / ANCHOR_STEPS[i + 1]))
            if guess > raw[i]:
                raw[i] = min(255, guess)
                anchors[i]["note"] = (anchors[i]["note"] + "; " if anchors[i]["note"] else "") + \
                    "started from the next entry's value"
    new, blocked = _rising(raw, anchors)
    for row, v, r in zip(anchors, new, raw):
        row["new"] = v
        if v != r and r == row["old"] and row.get("pass") == "raised":
            row["raised"] = True  # changed only to keep the table rising
            row["note"] = (row["note"] + "; " if row["note"] else "") + RAISED_NOTE
        elif v != r and row.get("pass") == "lowered":
            row["note"] = (row["note"] + "; " if row["note"] else "") + LOWERED_NOTE
        elif row.get("pass") == "capped":
            row["note"] = (row["note"] + "; " if row["note"] else "") + CAPPED_NOTE
        if row.get("blocked"):
            row["note"] = (row["note"] + "; " if row["note"] else "") + BLOCKED_NOTE
    measured_any = any(r["within"] is not None for r in anchors)
    # within the tolerance AND nothing to write: an entry the rising pass moves is a change
    done = measured_any and all(r["within"] is not False for r in anchors) \
        and all(r["new"] == r["old"] for r in anchors)
    return {"values": new, "anchors": anchors, "all_within": done, "blocked": blocked}


def _rising(raw, anchors):
    """Make the table non-decreasing without undoing a deliberate cut.

    In order: an entry below its predecessor that was NOT cut is raised to it. A cut entry
    instead pulls the preceding entries that are higher down to it, provided each of them
    was not measured outside the tolerance. If one of them was (it was measured too slow or
    fast and is being corrected itself), the cut is blocked: the entry stays at its
    predecessor's value and the result is reported as blocked. Returns (values, blocked cvs).
    """
    new = list(raw)
    blocked = []
    for i in range(1, N):
        if new[i] >= new[i - 1]:
            continue
        if anchors[i]["kind"] == "cut" and new[i] < anchors[i]["old"]:
            j = i - 1
            chain = []
            while j >= 0 and new[j] > new[i]:
                chain.append(j)
                j -= 1
            if all(anchors[c]["within"] is not False for c in chain):
                for c in chain:
                    new[c] = new[i]
                    anchors[c]["pass"] = "lowered"
                continue
            # keep the old value, never past it; the predecessors' raises stop there too
            new[i] = anchors[i]["old"]
            anchors[i]["blocked"] = True
            blocked.append(anchors[i]["cv"])
            for c in chain:
                if anchors[c]["kind"] == "raise" and new[c] > new[i]:
                    new[c] = max(new[i], anchors[c]["old"])
                    anchors[c]["pass"] = "capped"
            if new[i] < new[i - 1]:   # only if the table was not rising to begin with
                new[i] = new[i - 1]
        else:
            new[i] = new[i - 1]
            anchors[i]["pass"] = "raised"
    return new, blocked


def status(report, round_no, max_rounds):
    """done / blocked / stuck / continue / max_rounds.

    blocked: a cut cannot be made because of the rising table. stuck: some anchor is out of
    tolerance but no entry can change (all at 255 or the floor, or nothing measured)."""
    if report["all_within"]:
        return "done"
    if report.get("blocked"):
        return "blocked"
    if report.get("anchors") and all(r["new"] == r["old"] for r in report["anchors"]):
        return "stuck"
    return "max_rounds" if round_no >= max_rounds else "continue"


def proposal(loco, report, round_no, max_rounds, tol):
    """The record the write guard takes. Nothing in it is an address: the guard looks the
    loco up in the roster."""
    changes = []
    for r in report["anchors"]:
        if r["new"] != r["old"]:
            c = {"cv": r["cv"], "old": r["old"], "new": r["new"], "anchor_step": r["step"],
                 "error_pct": None if r["error"] is None else round(100 * r["error"], 2)}
            if r.get("raised"):
                c["note"] = RAISED_NOTE
            elif r.get("pass") == "lowered":
                c["note"] = LOWERED_NOTE
            if r.get("blocked"):
                c["note"] = BLOCKED_NOTE
            changes.append(c)
    st = status(report, round_no, max_rounds)
    # only a proposal that is meant to be applied carries writes; blocked, stuck, done and
    # out-of-rounds keep the details in changes and proposal.csv
    writes = [{"cv": c["cv"], "value": c["new"]} for c in changes] if st == "continue" else []
    reason = {"blocked": "a cut is blocked by the rising table (see blocked_cvs); nothing is written",
              "stuck": "no entry can change: they are at 255 or the floor, or not measured",
              "max_rounds": "out of rounds; nothing further is written"}.get(st, "")
    return {"schema": 1, "kind": "speed_table_proposal", "loco": loco, "reason": reason,
            # roster_id and writes are what pom_guard.py reads (POM_GUARD.md); the rest is ignored
            "roster_id": loco, "writes": writes,
            "round": round_no,
            "max_rounds": max_rounds, "tolerance_pct": round(100 * tol, 2),
            "status": st, "cv_start": CV_START,
            "old": [r["old"] for r in report["anchors"]], "new": report["values"],
            "changes": changes, "blocked_cvs": report.get("blocked", []), "applied": False,
            "note": "A proposal only. Writing goes through the write guard, dry run first."}


def read_profile(path, loco, direction, run=None, route=analyze.DEFAULT_ROUTE):
    """({step: median mm/s}, [skipped]) for one loco and direction from analyze.py's
    profile.csv. One run only: `run` if given, else the latest complete run (the latest run
    if none completed). Only the first measurement of a step, and only if the stop rule
    settled (the `settled` column; a file without it, by reason); every other step is listed in skipped as (step, reason).
    Only runs of `route` count (a profile.csv without a route column is loop1)."""
    with open(path, newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r["loco"] == loco and r["direction"] == direction
                and (r.get("route") or analyze.DEFAULT_ROUTE) == route]
    runs = {}
    for r in rows:
        runs.setdefault(int(r.get("run") or 1), (r.get("run_complete") or "True") == "True")
    if run is None:
        done = [n for n, c in runs.items() if c]
        run = max(done) if done else (max(runs) if runs else 1)
    out, skipped = {}, []
    for r in rows:
        if int(r.get("run") or 1) != run or "#" in r["step"]:
            continue
        flag = (r.get("settled") or "").strip()  # analyze.py's own verdict; old files only have the reason
        if r["median_mm_s"] and (flag == "True" if flag else lr.is_valid_reason(r["reason"])):
            out[int(r["step"])] = float(r["median_mm_s"])
        else:
            skipped.append((int(r["step"]), r["reason"] or "no readings"))
    return out, skipped


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--table", help="the 28 current values, comma separated")
    ap.add_argument("--roster-xml", help="read CV67-94 from this roster file instead")
    ap.add_argument("--profile", required=True, help="profile.csv of the loco being corrected")
    ap.add_argument("--loco", required=True)
    ap.add_argument("--direction", required=True)
    ap.add_argument("--run", type=int, help="run number in profile.csv (default: the latest complete run)")
    ap.add_argument("--target-run", type=int, help="run number for the target (default: the latest complete run)")
    ap.add_argument("--target-profile", help="profile.csv of the target (default: --profile)")
    ap.add_argument("--target-loco", required=True)
    ap.add_argument("--target-direction", required=True)
    ap.add_argument("--route", choices=sorted(analyze.ROUTES), default=analyze.DEFAULT_ROUTE,
                    help="use only runs of this route in the profiles")
    ap.add_argument("--round", type=int, default=1)
    ap.add_argument("--max-rounds", type=int, default=MAX_ROUNDS)
    ap.add_argument("--tol", type=float, default=TOLERANCE)
    ap.add_argument("--gain", type=float, default=1.0)
    ap.add_argument("--out", required=True, help="directory for proposal.json and proposal.csv")
    a = ap.parse_args(argv)
    if a.table:
        table = [int(x) for x in a.table.split(",")]
    elif a.roster_xml:
        import preflight_compare as pc
        cvs = pc.roster_cvs(a.roster_xml)
        table = [cvs[CV_START + i] for i in range(N)]
    else:
        ap.error("give --table or --roster-xml")
    measured, skip_m = read_profile(a.profile, a.loco, a.direction, a.run, a.route)
    target, skip_t = read_profile(a.target_profile or a.profile, a.target_loco, a.target_direction, a.target_run, a.route)
    skipped = ["%s %s step %d: %s" % (a.loco, a.direction, st, why) for st, why in skip_m] + \
              ["%s %s step %d: %s" % (a.target_loco, a.target_direction, st, why) for st, why in skip_t]
    if not measured or not target:
        sys.exit("no profile rows for %s %s or for the target" % (a.loco, a.direction))
    rep = propose(table, measured, target, a.tol, a.gain)
    prop = proposal(a.loco, rep, a.round, a.max_rounds, a.tol)
    prop["skipped_steps"] = skipped
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "proposal.json").write_text(json.dumps(prop, indent=2) + "\n")
    with open(out / "proposal.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["cv", "old", "new", "anchor_step", "error_pct", "within", "note"])
        for r in rep["anchors"]:
            w.writerow([r["cv"], r["old"], r["new"], r["step"],
                        "" if r["error"] is None else round(100 * r["error"], 2),
                        r["within"], r["note"]])
        for line in skipped:  # steps left out of the measurement, and why
            w.writerow(["", "", "", "", "", "", "skipped " + line])
    inside = sum(1 for r in rep["anchors"] if r["within"])
    print("round %d: %d of %d anchors within %.1f%%; status %s" % (
        a.round, inside, N, 100 * a.tol, prop["status"]))
    for r in rep["anchors"]:
        if r["new"] != r["old"] or r["within"] is False:
            err = "n/a" if r["error"] is None else "%+.1f%%" % (100 * r["error"])
            print("  CV%d step %.1f: %s  %d -> %d %s" % (r["cv"], r["step"], err, r["old"], r["new"], r["note"]))
    return {"done": 0, "continue": 2, "max_rounds": 3, "blocked": 3, "stuck": 3}[prop["status"]]


if __name__ == "__main__":
    sys.exit(main())
