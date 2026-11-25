#!/usr/bin/env python3
"""Propose a 28-point speed table (CV67-94) that makes the follower loco run
at the same speed as the master at every throttle step. DRAFT ONLY - it writes
nothing to a decoder.

Assumptions (verify after programming by re-running the profile):
 * Table entry k acts at throttle step 126*k/28 (126-step mode, interpolated).
 * The follower's speed table was not in use during the measurement, so its
   effective drive was proportional to the throttle step: value = 255*step/126.
 * Speeds above step 64 are one plateau; the master's scatter there is +-3%.
 * Speeds below the lowest measured step (8) are extrapolated from zero.
"""
import csv
import statistics
import sys
from collections import defaultdict

LOOP = 31292.8


def curve(rows):
    d = defaultdict(list)
    for step, v in rows:
        d[step].append(v)
    return {s: statistics.mean(v) for s, v in d.items()}


def interp(x, pts):
    pts = sorted(pts)
    if x <= pts[0][0]:
        return pts[0][1] * x / pts[0][0] if pts[0][0] else pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


def main(results="results.csv", manual="manual_laps.csv", master="2121", follower="2738",
         plateau_from=64):
    m, f = [], []
    for r in csv.DictReader(open(results)):
        v = (int(r["step"]), float(r["mm_per_s"]))
        (m if master in r["log"] else f if follower in r["log"] else []).append(v)
    for r in csv.DictReader(open(manual)):
        if master in r["loco"]:
            m.append((int(r["step"]), float(r["mm_per_s"])))
    mc, fc = curve(m), curve(f)
    top = statistics.mean(v for s, v in mc.items() if s >= plateau_from)
    target = {s: (v if s < plateau_from else top) for s, v in mc.items()}
    # follower: speed as a function of table value (value = 255*step/126)
    fv = sorted((255.0 * s / 126.0, v) for s, v in fc.items())
    vmax = max(v for _, v in fv)
    out = []
    for k in range(1, 29):
        step = 126.0 * k / 28.0
        want = min(interp(step, list(target.items())), vmax)
        # invert the follower curve (monotone up to its own plateau)
        pts = [(v, t) for t, v in fv]
        # stop at the first point reaching its plateau so the inverse is single valued
        mono = []
        for v, t in sorted(pts):
            if mono and v <= mono[-1][0] + 2:
                continue
            mono.append((v, t))
        val = interp(want, [(0.0, 0.0)] + mono)
        out.append((k, round(step, 1), round(want, 1), min(255, round(val))))
    return mc, fc, top, out


if __name__ == "__main__":
    mc, fc, top, out = main(*sys.argv[1:3]) if len(sys.argv) > 2 else main()
    print("master speed by step (mm/s):", {s: round(v, 1) for s, v in sorted(mc.items())})
    print("follower speed by step (mm/s):", {s: round(v, 1) for s, v in sorted(fc.items())})
    print("master plateau (steps >= 64): %.1f mm/s" % top)
    print("k,step,target_mm_s,cv_value")
    for row in out:
        print(",".join(str(x) for x in row))
    print("CV67-94 =", [r[3] for r in out])
