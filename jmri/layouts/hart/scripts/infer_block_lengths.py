#!/usr/bin/env python3
"""Infer the lengths of the test-loop blocks from timed laps and the AnyRail plan.

Part A of docs/jmri/speedmatching/RERUN_PLAN.md. The AnyRail plan (5.3b, staging
level, which is the built layout) gives the length of the whole test loop along the
route the locos ran: PLAN_LOOP_MM. It does not say where the block gaps are. The
2026-11-08 runs do: at one throttle step a loco runs at one speed, so the share of a
lap's time spent in a block is that block's share of the loop length.

    length(block) = median over laps of (transit(block) / lap time) * PLAN_LOOP_MM

then pinned(): the loop turnouts are on the plan too, so the timed positions are
re-fitted piecewise so each turnout's OS centre lands on the plan's turnout centre. Each
block then rests on the plan distance between the turnouts either side of it.

Only steps from MIN_STEP up are used (steady speed, no momentum effects). East Main
Ext is the lap reference block and is missing from some laps; for those laps the
other blocks' shares are scaled by (1 - the median East Main Ext share).

Where a detector also covers a hidden throat stub (a separate row in
block_lengths.csv sharing the sensor), the stub's length is taken off the track row.

Usage:
    python3 jmri/layouts/hart/scripts/infer_block_lengths.py            # report
    python3 jmri/layouts/hart/scripts/infer_block_lengths.py --apply    # update CSV
    python3 jmri/layouts/hart/scripts/infer_block_lengths.py --route loop2 --events EV.csv --locate
Then regenerate with export_track_lengths.py, as for any CSV change. Loop 2 (S-R, Scale, Barn)
places OS Switch 7 and 13; see docs/jmri/speedmatching/RUNBOOK.md.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
EVENTS = REPO / "docs/jmri/speedmatching/profile-2026-11-08/block_events.csv"
CSV = REPO / "jmri/layouts/hart/data/block_lengths.csv"
MM_PER_IN = 25.4

# Length of the test loop on the AnyRail plan 5.3b, staging level, along the route of
# the 2026-11-08 runs (Switch 5 -> Switch 33 -> East Lead -> Switch 35 -> 37 -> K loop
# -> 39 -> 35 -> West Main Ext -> 23 -> Main West -> 1 -> Brick-Plane -> 5): flex arc
# lengths plus turnout route lengths. See docs/jmri/speedmatching/ANYRAIL_LENGTHS.md.
# Both PLAN_ constants are printed by tools/anyrail/prototype/loop_route.py (steps in its README).
PLAN_LOOP_MM = 35108.2
MIN_STEP = 24
REF_BLOCK = "East Main Ext"
DEFAULT_ROUTE = "loop1"

# The loop's sensors and their block_lengths.csv rows come from the speed-match analysis
# (speedmatch/analyze.py LOOP), so there is one list to keep. block_events.csv names the
# sensors without the "BS " prefix.
sys.path.insert(0, str(Path(__file__).resolve().parent / "speedmatch"))
import analyze  # noqa: E402

SENSOR_ROWS = {sensor[3:]: row for sensor, row in analyze.LOOP}  # loop1


def route_rows(route):
    """{sensor without "BS ": csv row} for a route, in running order."""
    return {sensor[3:]: row for sensor, row in analyze.route_loop(route)}


def route_ref(route):
    """The lap reference block: loop1 keeps East Main Ext, every other route its first sensor."""
    return REF_BLOCK if route == DEFAULT_ROUTE else next(iter(route_rows(route)))


def lap_shares(rows, min_step=MIN_STEP, ref=REF_BLOCK, blocks=None):
    """Return {block: [share of lap time, one per lap]} from block_events rows."""
    blocks = set(blocks or SENSOR_ROWS)
    laps = defaultdict(dict)
    doubled = set()
    for r in rows:
        if int(r["step"]) < min_step or r["block"] not in blocks:
            continue
        key = (r["loco"], r["log"], r["step"], r["lap_index"])
        if r["block"] in laps[key]:
            doubled.add(key)  # a block seen twice in one lap (bounce, re-entry): lap unusable
        laps[key][r["block"]] = float(r["transit_s"])
    for key in doubled:
        del laps[key]
    full = [lap for lap in laps.values() if len(lap) == len(blocks)]
    if not full:
        raise ValueError("no complete laps")
    ref_share = statistics.median(lap[ref] / sum(lap.values()) for lap in full)
    shares = defaultdict(list)
    for lap in laps.values():
        if len(lap) == len(blocks):
            total, scale = sum(lap.values()), 1.0
        elif len(lap) == len(blocks) - 1 and ref not in lap:
            total, scale = sum(lap.values()), 1.0 - ref_share
        else:
            continue  # partial lap
        for b, t in lap.items():
            shares[b].append(t / total * scale)
    shares[ref] = [lap[ref] / sum(lap.values()) for lap in full]
    return shares


def infer(rows, loop_mm=PLAN_LOOP_MM, **kw):
    """Return {block: (median mm, half-range mm, n laps)}."""
    out = {}
    for b, s in lap_shares(rows, **kw).items():
        mm = [x * loop_mm for x in s]
        q = statistics.quantiles(mm, n=4) if len(mm) >= 4 else [min(mm), 0, max(mm)]
        out[b] = (statistics.median(mm), (q[2] - q[0]) / 2, len(mm))
    return out


# Where each turnout on the loop sits on the plan: the centre of its route, in mm along the
# test route from Switch 5's points (same route as PLAN_LOOP_MM). Keyed by the OS sensor.
# Switches 37 and 39 are left out: they sit 0.4 m and 0.2 m from the Switch 35 crossover, so
# pinning both ends of such a short stretch would turn a few cm of gap placement into a large
# error in the OS lengths between them.
PLAN_TURNOUT_MM = {
    "Switch 5": 142, "Switch 33": 12427, "Switch 35a": 15402,
    "Switch 35b": 22541, "Switch 23a": 27071, "Switch 1": 33172,
}
_ORDER = list(SENSOR_ROWS)
ROUTE_FROM_SW5 = _ORDER[_ORDER.index("Switch 5"):] + _ORDER[:_ORDER.index("Switch 5")]

# Loop 2 (Switch 5 thrown into Scale, Barn, Switch 13, 15, Track S-R, 23b, 31, 33, then as loop 1
# from East Lead): the plan route is T106 A->C, run T106C, T52 A->B, run T52B, T41 A->B (not
# built, counted as track), S-R run T41B, T118 B->A, run T118A, T59 B->A, run T59A, T77 B->A, then
# East Lead onward as loop 1. tools/anyrail/prototype/loop_route.py prints both constants.
# Switches 23b (12000 mm) and 31 (12382) are not pinned: too close to Switch 33 (12748) for a
# pinned stretch of a few cm to stay meaningful. Switches 7 and 13 are the ones to find.
PLAN_LOOP2_MM = 35428.7
PLAN_LOOP2_TURNOUT_MM = {
    "Switch 5": 140, "Switch 15": 5909, "Switch 33": 12748, "Switch 35a": 15723,
    "Switch 35b": 22861, "Switch 23a": 27392, "Switch 1": 33492,
}
# route -> (plan loop length mm, plan turnout centres by OS sensor)
PLAN = {"loop1": (PLAN_LOOP_MM, PLAN_TURNOUT_MM), "loop2": (PLAN_LOOP2_MM, PLAN_LOOP2_TURNOUT_MM)}


def route_from_sw5(route):
    names = list(route_rows(route))
    i = names.index("Switch 5")
    return names[i:] + names[:i]


def pinned(result, loop_mm=PLAN_LOOP_MM, turnouts=PLAN_TURNOUT_MM, route=ROUTE_FROM_SW5):
    """Re-fit the timed lengths so each turnout's OS centre lands on the plan's turnout centre.

    Between two plan turnouts, the timed positions are scaled to the plan distance between
    them, so each block's length rests on the nearest known plan lengths instead of on one
    scale for the whole loop. Returns the same shape as infer()."""
    edges = [0.0]
    for s in route:
        edges.append(edges[-1] + result[s][0])
    total = edges[-1]
    centre = {s: (edges[k] + edges[k + 1]) / 2 for k, s in enumerate(route)}
    pins = [s for s in route if s in turnouts]
    xs = [centre[s] for s in pins]
    ys = [float(turnouts[s]) for s in pins]
    xs = [xs[-1] - total] + xs + [xs[0] + total]
    ys = [ys[-1] - loop_mm] + ys + [ys[0] + loop_mm]

    def to_plan(x):
        for k in range(len(xs) - 1):
            if xs[k] <= x <= xs[k + 1]:
                return ys[k] + (x - xs[k]) / (xs[k + 1] - xs[k]) * (ys[k + 1] - ys[k])
        raise ValueError(x)

    out = {}
    for k, s in enumerate(route):
        mm = to_plan(edges[k + 1]) - to_plan(edges[k])
        # the lap spread scales with the block: the same factor pinning applied to it
        out[s] = (mm, result[s][1] * mm / result[s][0], result[s][2])
    return out


def locate(result, turnouts, route, targets=("Switch 7", "Switch 13"), anchor="Switch 15"):
    """Where the target sections' centres fall along the route, in mm from Switch 5's points
    (the plan frame the pins use), and their distance from the anchor's centre (positive =
    before the anchor along the route). result is the pinned() output. Returns
    {sensor: (centre mm, mm before the anchor's centre)}."""
    start = turnouts["Switch 5"] - result["Switch 5"][0] / 2
    centre, pos = {}, start
    for s in route:
        centre[s] = pos + result[s][0] / 2
        pos += result[s][0]
    return {t: (centre[t], centre[anchor] - centre[t]) for t in targets}


def stubs_of(rows, sensor):
    """Hidden throat stub rows that share this sensor's detector."""
    return [r["user_name"] for r in rows
            if r["flag"] == "stub" and r["occupancy_sensor"] == "BS " + sensor]


def plan_rows(result, csv_path=CSV, route=DEFAULT_ROUTE, only=None):
    """The CSV rows with the new lengths, not yet written. Returns (fields, rows, mm by row).
    only: the sensors to write (default all of the route's)."""
    rows = list(csv.DictReader(open(csv_path, newline="")))
    fields = list(rows[0].keys())
    by_name = {r["user_name"]: r for r in rows}
    sensor_rows = {s: n for s, n in route_rows(route).items() if only is None or s in only}
    for sensor, name in sensor_rows.items():
        stubs = stubs_of(rows, sensor)
        mm, spread, n = result[sensor]
        stub_mm = sum(float(by_name[s]["inches"]) * MM_PER_IN for s in stubs)
        r = by_name[name]
        r["inches"] = f"{(mm - stub_mm) / MM_PER_IN:.1f}"
        r["flag"] = "inferred"
        note = (f"timed share of the AnyRail 5.3b {route} loop, pinned to the plan turnouts either side; "
                f"+-{spread / MM_PER_IN:.1f} in over {n} laps")
        if stubs:
            note += "; detector length minus " + ", ".join(stubs)
        r["old_source"] = note
    return fields, rows, {n: float(by_name[n]["inches"]) * MM_PER_IN for n in sensor_rows.values()}


def write_csv(fields, rows, csv_path=CSV):
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def apply_tables(lengths_mm):
    """Set <block length> in tables.xml for the given userName -> mm (hartlib refuses while JMRI runs)."""
    sys.path.insert(0, str(REPO / "tools/hartlib/src"))
    from hartlib import tables

    t = tables.load()
    seen = set()
    for b in tables.blocks(t.root):
        name = tables.user_name(b)
        if name in lengths_mm:
            b.set("length", f"{lengths_mm[name]:.1f}")
            seen.add(name)
    missing = set(lengths_mm) - seen
    if missing:
        raise SystemExit(f"blocks not in tables.xml: {sorted(missing)}")
    t.save()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--route", choices=sorted(analyze.ROUTES), default=analyze.DEFAULT_ROUTE)
    ap.add_argument("--events", type=Path, help="block_events-style CSV (analyze.py --events-out for "
                    "a new run); required for loop2, default for loop1 is the 2026-11-08 file")
    ap.add_argument("--apply", action="store_true", help="write the lengths into block_lengths.csv")
    ap.add_argument("--overwrite", action="store_true",
                    help="loop2: also rewrite the rows loop 1 already set (loop 1 owns them otherwise)")
    ap.add_argument("--locate", action="store_true",
                    help="print where the OS Switch 7 and 13 section centres fall along the route")
    a = ap.parse_args()
    route = a.route
    loop_mm, pins = PLAN[route]
    if a.events is None:
        if route != DEFAULT_ROUTE:
            ap.error("--events is required for %s" % route)
        a.events = EVENTS
    names = route_rows(route)
    result = pinned(infer(list(csv.DictReader(open(a.events, newline=""))), loop_mm=loop_mm,
                          ref=route_ref(route), blocks=list(names)),
                    loop_mm, pins, route_from_sw5(route))
    print(f"{route}: {'sensor':30} {'mm':>8} {'+-mm':>6} {'in':>7} {'laps':>5}")
    for sensor in route_from_sw5(route):
        mm, spread, n = result[sensor]
        print(f"{sensor:36} {mm:8.0f} {spread:6.0f} {mm / MM_PER_IN:7.1f} {n:5d}")
    print(f"{'total':36} {sum(v[0] for v in result.values()):8.0f}   (plan loop {loop_mm:.0f})")
    only = None
    if route != DEFAULT_ROUTE:
        owned = set(SENSOR_ROWS)  # loop 1 owns its 17 rows
        csv_rows = {r["user_name"]: r for r in csv.DictReader(open(CSV, newline=""))}
        print("rows on both routes (loop 1 value from block_lengths.csv, this run beside it):")
        for s in names:
            if s in owned:
                old = float(csv_rows[names[s]]["inches"]) * MM_PER_IN
                print(f"  {s:34} loop1 {old:7.0f} mm   {route} {result[s][0]:7.0f} mm   {result[s][0] - old:+6.0f}")
        only = set(names) if a.overwrite else set(names) - owned
    if a.locate:
        for t, (pos, before) in locate(result, pins, route_from_sw5(route)).items():
            print(f"locate: OS {t} centre {pos:.0f} mm from Switch 5's points, "
                  f"{before:.0f} mm before OS Switch 15's centre")
    if a.apply:
        fields, rows, mm = plan_rows(result, CSV, route, only)
        apply_tables(mm)          # tables first: it refuses while PanelPro or CATS is open
        write_csv(fields, rows)   # so the CSV only changes once tables.xml has
        print(f"updated {len(mm)} rows in {CSV.relative_to(REPO)} and tables.xml; now run export_track_lengths.py")


if __name__ == "__main__":
    main()
