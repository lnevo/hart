"""Speed per loco and throttle step from whole laps of a route: the speed_by_step table (analyze.py speed-by-step).

One row per loco and step: laps, mean lap time, mean speed (route length / lap time, averaged over the laps), its
spread (sample standard deviation, '' for one lap) and the HO scale speed in mph. The laps come from lap CSVs (a
`step` and `lap_s` column, and a `loco` column or a `log` column that --log-loco maps to a loco) or from runner
logs. In a runner log a lap ends each time the route's first sensor lights again after its mid sensor lit, inside
one STEP; the first lighting in a step only starts the timing, so the partial lap after a step change is not used.

    analyze.py speed-by-step --laps results.csv --laps manual_laps.csv --log-loco "steprun_2121_b.log=CSX 2121" \\
        --loop-mm 31292.8 --out speed_by_step.csv
    analyze.py speed-by-step --log steps_2121_fwd.log --route loop1 --out speed_by_step.csv

The route length is --loop-mm, or the sum of the route's trusted block lengths (analyze.load_lengths); a route
with a block that has no trusted length stops.
"""
from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

import analyze
from analyze_records import AnalyzeError, Lengths, RunRecord

HO_SCALE = 87
MPH_PER_M_S = 2.23694
FIELDS = ["loco", "step", "laps", "mean_lap_s", "mean_mm_per_s", "stdev_mm_per_s", "mean_scale_mph_ho"]


class SpeedTableError(AnalyzeError):
    """Laps or a route length the speed table cannot use: a missing column, a bad number, an unknown log, no laps."""


class Lap(NamedTuple):
    """One whole lap of the route by one loco at one throttle step."""
    loco: str
    step: int
    lap_s: float


class StepSpeed(NamedTuple):
    """One row of the speed table; stdev_mm_s is None for a single lap."""
    loco: str
    step: int
    laps: int
    mean_lap_s: float
    mean_mm_s: float
    stdev_mm_s: float | None
    mph_ho: float


def speed_by_step(laps: Iterable[Lap], loop_mm: float) -> list[StepSpeed]:
    """The table, sorted by loco and step; a step's laps are averaged in the order given."""
    if loop_mm <= 0:
        raise SpeedTableError("route length must be above 0 mm, got %g" % loop_mm)
    by: dict[tuple[str, int], list[float]] = {}
    for lap in laps:
        if not math.isfinite(lap.lap_s) or lap.lap_s <= 0:
            raise SpeedTableError("lap of %s at step %d is %g s; a lap takes a finite time above 0"
                                  % (lap.loco, lap.step, lap.lap_s))
        by.setdefault((lap.loco, lap.step), []).append(lap.lap_s)
    if not by:
        raise SpeedTableError("no laps")
    rows = []
    for (loco, step), times in sorted(by.items()):
        speeds = [loop_mm / x for x in times]
        mean = statistics.mean(speeds)
        rows.append(StepSpeed(loco, step, len(times), round(statistics.mean(times), 1), round(mean, 1),
                              round(statistics.stdev(speeds), 1) if len(speeds) > 1 else None,
                              round(mean * HO_SCALE / 1000 * MPH_PER_M_S, 1)))
    return rows


def read_laps(path: str | Path, log_locos: Mapping[str, str]) -> list[Lap]:
    """The laps of a lap CSV, in file order. A row names its loco, or its log and log_locos gives the loco."""
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        cols = set(reader.fieldnames or [])
        missing = {"step", "lap_s"} - cols
        if missing or not cols & {"loco", "log"}:
            raise SpeedTableError("%s: needs columns step, lap_s and loco or log; has %s"
                                  % (path, ", ".join(reader.fieldnames or []) or "none"))
        laps = []
        for n, row in enumerate(reader, start=2):
            loco = row.get("loco") or log_locos.get(row.get("log") or "")
            if not loco:
                raise SpeedTableError("%s line %d: log %r has no loco; give --log-loco LOG=LOCO"
                                      % (path, n, row.get("log")))
            try:
                laps.append(Lap(loco, int(row["step"]), float(row["lap_s"])))
            except (ValueError, TypeError) as e:
                raise SpeedTableError("%s line %d: step and lap_s must be numbers (%s)" % (path, n, e)) from e
    return laps


def run_laps(runs: Iterable[RunRecord], route: str = analyze.DEFAULT_ROUTE) -> list[Lap]:
    """The whole laps of each run's steps, in log order. SpeedTableError when a run's CFG line names another route
    than `route`: the table divides every lap by one route length."""
    laps = []
    for run in runs:
        name = str((run.get("cfg") or {}).get("route", route))
        if name != route:
            raise SpeedTableError("run of %s is on route %s, not %s; give --route %s, and one route per table"
                                  % (run["loco"], name, route, name))
        ref, mid = analyze.route_order(name)[0], analyze.route_mid(name)
        for s in run["steps"]:
            start: float | None = None
            seen_mid = False
            for t, sensor in s["events"]:
                if sensor == mid:
                    seen_mid = True
                elif sensor == ref and (start is None or seen_mid):
                    if start is not None:
                        laps.append(Lap(run["loco"], s["step"], t - start))
                    start, seen_mid = t, False
    return laps


def route_mm(route: str, lengths: Lengths) -> float:
    """The route's length: the sum of its blocks' trusted lengths."""
    order = analyze.route_order(route)
    untrusted = [s for s in order if lengths.get(s) is None]
    if untrusted:
        raise SpeedTableError("route %s: no trusted length for %s; give --loop-mm or --trusted"
                              % (route, ", ".join(untrusted)))
    return sum(float(lengths[s] or 0.0) for s in order)


def write_table(rows: Iterable[StepSpeed], path: str | Path) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(FIELDS)
        for r in rows:
            w.writerow([r.loco, r.step, r.laps, r.mean_lap_s, r.mean_mm_s,
                        "" if r.stdev_mm_s is None else r.stdev_mm_s, r.mph_ho])


def log_loco_map(pairs: Sequence[str]) -> dict[str, str]:
    """--log-loco LOG=LOCO values as {log: loco}."""
    out = {}
    for p in pairs:
        log, sep, loco = p.partition("=")
        if not sep or not log or not loco:
            raise SpeedTableError("--log-loco %r: give LOG=LOCO" % p)
        out[log] = loco
    return out


def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="analyze.py speed-by-step", description=__doc__.split("\n\n")[0])
    ap.add_argument("--laps", action="append", default=[], help="a lap CSV (repeatable, read in order)")
    ap.add_argument("--log-loco", action="append", default=[], help="LOG=LOCO for a lap CSV with a log column")
    ap.add_argument("--log", action="append", default=[], help="a runner log (repeatable)")
    ap.add_argument("--route", default=analyze.DEFAULT_ROUTE, choices=sorted(analyze.ROUTES),
                    help="route for logs whose CFG line names none, and for the route length")
    ap.add_argument("--loop-mm", type=float, help="the route length in mm (default: its trusted block lengths)")
    ap.add_argument("--lengths", default=str(analyze.DEFAULT_LENGTHS))
    ap.add_argument("--trusted", default=",".join(analyze.DEFAULT_TRUSTED))
    ap.add_argument("--out", required=True, help="the CSV to write")
    a = ap.parse_args(argv)
    if not a.laps and not a.log:
        ap.error("give --laps or --log")
    locos = log_loco_map(a.log_loco)
    laps = [lap for p in a.laps for lap in read_laps(p, locos)]
    for p in a.log:
        laps += run_laps(analyze.parse_log(Path(p).read_text().splitlines(), source=Path(p).name), a.route)
    loop_mm = a.loop_mm
    if loop_mm is None:
        loop = analyze.ROUTES[a.route]
        loop_mm = route_mm(a.route, analyze.load_lengths(a.lengths, tuple(a.trusted.split(",")), loop))
    rows = speed_by_step(laps, loop_mm)
    write_table(rows, a.out)
    print("route %.1f mm, %d laps, wrote %d rows to %s" % (loop_mm, len(laps), len(rows), a.out))
