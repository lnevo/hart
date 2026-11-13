#!/usr/bin/env python3
"""Measured correction of a 28-entry speed table (CV67-CV94). Proposes; never writes.

Table entry k (1..28) acts at throttle step 126*k/28 (126-step mode, interpolated), the
assumption already used by the 2026-11-08 propose_table.py. For each entry the loco's
measured speed there is compared with the target speed (2121's profile in the paired
direction), and the entry is scaled by target / measured. Entries within the tolerance
(default 3%) are left alone. The new table is clamped to 1..255 and kept monotonic
non-decreasing.

This module does not touch a decoder. Its output (proposal.json and proposal.csv) is what
the write guard (pom_guard.py) takes; address, long/short flag and the consist check come
from the roster there, not from here.

    correct.py --table 0,26,... --profile profile.csv --loco "CSX 2738" --direction reverse \\
        --target-loco "CSX 2121" --target-direction forward --round 1 --out proposal/

Exit status: 0 every anchor within tolerance (done), 2 a proposal was written (apply it,
measure again, run this again with --round N+1), 3 out of rounds and still outside.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

N = 28
CV_START = 67
ANCHOR_STEPS = [126.0 * k / N for k in range(1, N + 1)]
TOLERANCE = 0.03
MAX_ROUNDS = 5
RAISED_NOTE = "raised to keep the table rising"


def interp(x, pts):
    """Linear interpolation over (step, speed) points. Below the first point the speed is
    scaled towards zero at step 0; above the last it stays flat."""
    pts = sorted(pts)
    if not pts:
        return None
    if x <= pts[0][0]:
        return pts[0][1] * x / pts[0][0] if pts[0][0] else pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


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
        m, t = interp(step, mp), interp(step, tp)
        row = {"k": k, "cv": CV_START + k - 1, "step": round(step, 2), "old": int(old),
               "measured": m, "target": t, "error": None, "within": None, "note": ""}
        val = int(old)
        if not m or not t or m <= 0 or t <= 0:
            row["note"] = "no usable measurement"
        else:
            row["error"] = m / t - 1.0
            row["within"] = abs(row["error"]) <= tol
            if not row["within"]:
                ratio = max(1.0 / max_ratio, min(max_ratio, (t / m) ** gain))
                val = int(round(old * ratio))
                if val == old:
                    val = old + (1 if ratio > 1 else -1)  # a real error must move the entry
                if old <= 1 and ratio < 1:
                    row["note"] = "already at the floor"
                if val >= 255 and ratio > 1:
                    row["note"] = "reaches 255: this loco may not be able to reach the target here"
        anchors.append(row)
        raw.append(max(1, min(255, val)))
    new = list(raw)
    for i in range(1, N):  # monotonic non-decreasing, before anything is judged
        if new[i] < new[i - 1]:
            new[i] = new[i - 1]
    for row, v, r in zip(anchors, new, raw):
        row["new"] = v
        if v != r and r == row["old"]:
            row["raised"] = True  # changed only to keep the table rising
            row["note"] = (row["note"] + "; " if row["note"] else "") + RAISED_NOTE
    measured_any = any(r["within"] is not None for r in anchors)
    # within the tolerance AND nothing to write: an entry the rising pass moves is a change
    done = measured_any and all(r["within"] is not False for r in anchors) \
        and all(r["new"] == r["old"] for r in anchors)
    return {"values": new, "anchors": anchors, "all_within": done}


def status(report, round_no, max_rounds):
    """done / continue / max_rounds."""
    if report["all_within"]:
        return "done"
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
            changes.append(c)
    return {"schema": 1, "kind": "speed_table_proposal", "loco": loco,
            # roster_id and writes are what pom_guard.py reads (POM_GUARD.md); the rest is ignored
            "roster_id": loco, "writes": [{"cv": c["cv"], "value": c["new"]} for c in changes],
            "round": round_no,
            "max_rounds": max_rounds, "tolerance_pct": round(100 * tol, 2),
            "status": status(report, round_no, max_rounds), "cv_start": CV_START,
            "old": [r["old"] for r in report["anchors"]], "new": report["values"],
            "changes": changes, "applied": False,
            "note": "A proposal only. Writing goes through the write guard, dry run first."}


def read_profile(path, loco, direction):
    """({step: median mm/s}, [skipped]) for one loco and direction from analyze.py's
    profile.csv. Only the first measurement of a step, and only if the stop rule settled
    (reason "settled"); every other step is listed in skipped as (step, reason)."""
    out, skipped = {}, []
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            if r["loco"] == loco and r["direction"] == direction and "#" not in r["step"]:
                if r["median_mm_s"] and r["reason"] == "settled":
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
    ap.add_argument("--target-profile", help="profile.csv of the target (default: --profile)")
    ap.add_argument("--target-loco", required=True)
    ap.add_argument("--target-direction", required=True)
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
    measured, skip_m = read_profile(a.profile, a.loco, a.direction)
    target, skip_t = read_profile(a.target_profile or a.profile, a.target_loco, a.target_direction)
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
        if r["within"] is False:
            print("  CV%d step %.1f: %+.1f%%  %d -> %d %s" % (
                r["cv"], r["step"], 100 * r["error"], r["old"], r["new"], r["note"]))
    return {"done": 0, "continue": 2, "max_rounds": 3}[prop["status"]]


if __name__ == "__main__":
    sys.exit(main())
