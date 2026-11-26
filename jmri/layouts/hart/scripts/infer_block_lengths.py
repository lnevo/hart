#!/usr/bin/env python3
"""Infer the lengths of the test-loop blocks from timed laps and the AnyRail plan.

Part A of docs/jmri/speedmatching/RERUN_PLAN.md. The AnyRail plan 5.3c (ADR-026, staging
level) gives the length of the whole test loop along the route the locos ran (plan_routes.py
reads it from the plan file). It does not say where the block gaps are. The
2026-11-08 runs do: at one throttle step a loco runs at one speed, so the share of a
lap's time spent in a block is that block's share of the loop length.

    length(block) = median over laps of (transit(block) / lap time) * the plan loop length

then pinned(): the loop turnouts are on the plan too, so the timed positions are
re-fitted piecewise so each turnout's OS centre lands on the plan's turnout centre. Each
block then rests on the plan distance between the turnouts either side of it.

Only steps from MIN_STEP up are used (steady speed, no momentum effects). East
Ext is the lap reference block and is missing from some laps; for those laps the
other blocks' shares are scaled by (1 - the median East Ext share).

The result is the block's measured length: a row of block_lengths_measured.csv (its measured_in, the
run and the date), which sits over the plan length in block_lengths.csv (hartlib.block_lengths). Each
detector is one block (the hidden yard throats are gone, 2026-11-20).

Usage:
    python3 jmri/layouts/hart/scripts/infer_block_lengths.py            # report
    python3 jmri/layouts/hart/scripts/infer_block_lengths.py --apply [--date YYYY-MM-DD]   # write the measured rows
    python3 jmri/layouts/hart/scripts/infer_block_lengths.py --route loop2 --events EV.csv --locate
    python3 jmri/layouts/hart/scripts/infer_block_lengths.py --route loop2 --locate --pass-log P1.log P2.log
Then rebuild tables.xml (python3 tools/schematic/build_tables.py, which takes each block's operating
length) and run export_track_lengths.py. Loop 2 (S-R, Scale, Barn)
places OS Switch 7 and 13; see docs/jmri/speedmatching/RUNBOOK.md.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import block_lengths  # noqa: E402  the measured file's one writer; speed matching's operating lengths
from hartlib import paths  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_routes  # noqa: E402  the routes' plan lengths and turnout centres, read from the AnyRail plan

REPO = paths.REPO_ROOT
EVENTS = REPO / "docs/jmri/speedmatching/profile-2026-11-08/block_events.csv"
EVENTS_DATE = "2026-11-08"      # the run EVENTS holds
MM_PER_IN = 25.4

MIN_STEP = 24
DEFAULT_ROUTE = "loop1"

# The loop's sensors and their blocks come from the speed-match analysis
# (speedmatch/analyze.py LOOP), so there is one list to keep. block_events.csv names the
# sensors without the "BS " prefix.
sys.path.insert(0, str(Path(__file__).resolve().parent / "speedmatch"))
import analyze  # noqa: E402

SENSOR_ROWS = {sensor[3:]: row for sensor, row in analyze.LOOP}  # loop1
# The lap reference: loop1's first block (East Ext), the one the 2026-11-08 laps were timed on.
REF_BLOCK = next(iter(SENSOR_ROWS))


def route_rows(route):
    """{sensor without "BS ": csv row} for a route, in running order."""
    return {sensor[3:]: row for sensor, row in analyze.route_loop(route)}


def route_ref(route):
    """The lap reference block: each route's first sensor (loop1: East Ext)."""
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


def infer(rows, loop_mm: float, **kw):
    """Return {block: (median mm, half-range mm, n laps)}; loop_mm is the route's plan length (plan(route))."""
    out = {}
    for b, s in lap_shares(rows, **kw).items():
        mm = [x * loop_mm for x in s]
        q = statistics.quantiles(mm, n=4) if len(mm) >= 4 else [min(mm), 0, max(mm)]
        out[b] = (statistics.median(mm), (q[2] - q[0]) / 2, len(mm))
    return out


_ORDER = list(SENSOR_ROWS)
ROUTE_FROM_SW5 = _ORDER[_ORDER.index("Switch 5"):] + _ORDER[:_ORDER.index("Switch 5")]
# route -> the run a measured row names (block_lengths_measured.csv `run`)
RUN = {"loop1": "loop1 laps", "loop2": "loop2 passes"}


def plan(route: str) -> plan_routes.RoutePlan:
    """The route's plan length in mm and its pinned turnout centres by OS sensor, read from the AnyRail plan
    (plan_routes.py; its ROUTE_STEPS says which turnouts are pinned and why). PlanRouteError when the plan file
    is not on this machine or the route does not walk on it."""
    routes = plan_routes.plan_routes()
    if route not in routes:
        raise plan_routes.PlanRouteError(f"no plan route {route!r}: plan_routes.py has {', '.join(sorted(routes))}")
    return routes[route]


def route_from_sw5(route):
    names = list(route_rows(route))
    i = names.index("Switch 5")
    return names[i:] + names[:i]


def pinned(result, loop_mm: float, turnouts: dict[str, int], route=ROUTE_FROM_SW5):
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


def pass_centres(events, route, pins, targets=("Switch 7", "Switch 13"), frm="Switch 5", to="Switch 15",
                 path=None):
    """Place the targets' centres from one timed pass (pass_runner.py), the loco at one speed
    between the two pins. events: [(epoch, "BS ...")] ACTIVE events, the first of each sensor
    counts. A section's centre time is halfway between its entry and the entry of the next
    section in the direction of travel; the pins' centres sit at pins[frm] and pins[to] (mm
    from Switch 5's points), so a target's position is a straight-line interpolation on those
    times. frm and to must be pins of the route (BS prefix allowed); path, when the log has one,
    is the sensors expected from frm to to in order, and the order the sensors lit must match it.
    Returns {"speed": mm/s, target: (centre mm, mm before OS Switch 15's centre), ...}."""
    frm, to = (n[3:] if n.startswith("BS ") else n for n in (frm, to))
    for n in (frm, to):
        if n not in pins:
            raise ValueError(f"{n} is not a pin on the {route} plan; the pins are {', '.join(sorted(pins))}")
    seq = route_from_sw5(route)
    first = {}
    for t, name in events:
        first.setdefault(name[3:] if name.startswith("BS ") else name, t)
    for need in (frm, to):
        if need not in first:
            raise ValueError(f"the pass never lit BS {need}")
    if path:
        want = [n[3:] if n.startswith("BS ") else n for n in path]
        lit = sorted((first[n], n) for n in want if n in first)
        got = [n for _, n in lit]
        if got != want:
            raise ValueError("the sensors lit in the order " + ",".join(got) + " but the logged PATH is "
                             + ",".join(want) + " (the loco went the wrong way, or a sensor was missed)")
        sign = 1 if len(want) > 1 and seq[(seq.index(want[0]) + 1) % len(seq)] == want[1] else -1
    else:
        sign = 1 if first[to] > first[frm] else -1  # +1: the route's own order

    def centre(s):
        nxt = seq[(seq.index(s) + sign) % len(seq)]
        if s not in first or nxt not in first:
            raise ValueError(f"no entry time for BS {s if s not in first else nxt}")
        return (first[s] + first[nxt]) / 2

    t0, t1 = centre(frm), centre(to)
    if t0 == t1:
        raise ValueError("the pass has no time between the pins")
    per_s = (pins[to] - pins[frm]) / (t1 - t0)
    out = {"speed": abs(per_s)}
    for tg in targets:
        pos = pins[frm] + (centre(tg) - t0) * per_s
        out[tg] = (pos, pins["Switch 15"] - pos)
    return out


def measured_rows(result, route=DEFAULT_ROUTE, only=None, date=EVENTS_DATE, plan=block_lengths.PLAN):
    """The measured file's rows with the new lengths, not yet written: each of the route's blocks (only: the sensors
    to write, default all of the route's) gets its measured length, the run (RUN) and `date`; every other row
    is kept. Returns (rows, mm by block name)."""
    have = block_lengths.read_measured(plan=plan)
    sensor_rows = {s: n for s, n in route_rows(route).items() if only is None or s in only}
    mm = {}
    for sensor, name in sensor_rows.items():
        length, spread, n = result[sensor]
        ident = analyze.BLOCK_IDS[name]
        note = (f"timed share of the AnyRail 5.3c {route} loop, pinned to the plan turnouts either side; "
                f"+-{spread / MM_PER_IN:.1f} in over {n} laps")
        have[ident] = block_lengths.Measured(0, ident, round(length / MM_PER_IN, 1), RUN[route], date, note)
        mm[name] = have[ident].measured_in * MM_PER_IN
    return list(have.values()), mm


def report_passes(logs, route, pins):
    """Print each pass's placement, then the mean and the difference of the passes."""
    found = []
    for p in logs:
        for ps in analyze.parse_pass_log(Path(p).read_text().splitlines(), Path(p).name):
            try:
                res = pass_centres(ps["events"], route, pins, frm=ps["frm"], to=ps["to"], path=ps["path"])
            except ValueError as e:
                print(f"pass at step {ps['step']} in {ps['log']} skipped: {e}")
                continue
            found.append((ps, res))
            print(f"pass {len(found)}: {ps['loco']} {ps['direction']} step {ps['step']} ({ps['log']}, "
                  f"ended {ps['reason'] or 'unknown'}): {res['speed']:.1f} mm/s between the pins")
            for t in ("Switch 7", "Switch 13"):
                pos, before = res[t]
                print(f"  OS {t} centre {pos:.0f} mm from Switch 5's points, {before:.0f} mm before OS Switch 15's centre")
    if not found:
        raise SystemExit("no usable pass in the logs")
    for t in ("Switch 7", "Switch 13"):
        pos = [r[t][0] for _, r in found]
        before = [r[t][1] for _, r in found]
        print(f"locate: OS {t} centre {statistics.mean(pos):.0f} mm from Switch 5's points, "
              f"{statistics.mean(before):.0f} mm before OS Switch 15's centre (mean of {len(found)} passes)")
        if len(found) > 1:
            print(f"  passes differ by {max(pos) - min(pos):.0f} mm (last minus first {pos[-1] - pos[0]:+.0f} mm)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--route", choices=sorted(analyze.ROUTES), default=analyze.DEFAULT_ROUTE)
    ap.add_argument("--events", type=Path, help="block_events-style CSV (analyze.py --events-out for "
                    "a new run); required for loop2, default for loop1 is the 2026-11-08 file")
    ap.add_argument("--apply", action="store_true", help="write the lengths into block_lengths_measured.csv")
    ap.add_argument("--date", help="with --apply: the date of the run (YYYY-MM-DD); given for --events, "
                                   "default %s for the 2026-11-08 file" % EVENTS_DATE)
    ap.add_argument("--overwrite", action="store_true",
                    help="loop2: also rewrite the rows loop 1 already set (loop 1 owns them otherwise)")
    ap.add_argument("--pass-log", nargs="+", type=Path, metavar="LOG",
                    help="with --locate: place OS Switch 7 and 13 from pass-job logs "
                         "(make_job.py pass), no laps needed")
    ap.add_argument("--locate", action="store_true",
                    help="print where the OS Switch 7 and 13 section centres fall along the route")
    a = ap.parse_args()
    route = a.route
    try:
        loop_mm, pins = plan(route)
    except plan_routes.PlanRouteError as exc:
        raise SystemExit(f"infer_block_lengths: {exc}") from exc
    if a.pass_log:
        if not a.locate or route != "loop2":
            ap.error("--pass-log goes with --locate and --route loop2")
        return report_passes(a.pass_log, route, pins)
    if a.events is None:
        if route != DEFAULT_ROUTE:
            ap.error("--events is required for %s" % route)
        a.events = EVENTS
        a.date = a.date or EVENTS_DATE
    if a.apply and not a.date:
        ap.error("--apply with --events needs --date, the date of the run")
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
        operating = block_lengths.operating_lengths()      # measured where there is one, else the plan length
        print("rows on both routes (loop 1 value from the block lengths, this run beside it):")
        for s in names:
            if s in owned:
                old = operating[names[s]] * MM_PER_IN
                print(f"  {s:34} loop1 {old:7.0f} mm   {route} {result[s][0]:7.0f} mm   {result[s][0] - old:+6.0f}")
        only = set(names) if a.overwrite else set(names) - owned
    if a.locate:
        for t, (pos, before) in locate(result, pins, route_from_sw5(route)).items():
            print(f"locate: OS {t} centre {pos:.0f} mm from Switch 5's points, "
                  f"{before:.0f} mm before OS Switch 15's centre")
    if a.apply:
        rows, mm = measured_rows(result, route, only, a.date)
        out = block_lengths.write_measured(rows)
        print(f"updated {len(mm)} rows in {out.relative_to(REPO)}; now run python3 tools/schematic/build_tables.py "
              "and export_track_lengths.py")


if __name__ == "__main__":
    main()
