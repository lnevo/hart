#!/usr/bin/env python3
"""Turn speed-profile runner logs into per-step lap times and speeds.

Input: one or more runner logs (lines "<epoch> STEP n" / "<epoch> REF n").
A lap is the time between two consecutive REF lines of the same step. The first
REF after a STEP line ends the transition lap and is not timed. A lap listed in
--drop (epoch start of the lap, +/- 2 s) is excluded.
"""
import argparse
import csv
import re
import sys

LOOP_MM = 31292.8  # sum of the block lengths on the loop (see README)


def parse(path):
    step, last, laps = None, None, []
    first = True
    for line in open(path):
        m = re.match(r"([\d.]+) (STEP (\d+)|REF (\d+)$)", line.strip())
        if not m:
            continue
        t = float(m.group(1))
        if m.group(3):
            step, last, first = int(m.group(3)), t, True
        elif m.group(4) and step is not None:
            if first:
                first, last = False, t
                laps.append((step, t, None))  # end of the transition lap
            else:
                laps.append((step, t, t - last))
                last = t
    return laps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--drop", type=float, action="append", default=[],
                    help="epoch of the REF that ends a lap to exclude")
    ap.add_argument("--loop-mm", type=float, default=LOOP_MM)
    a = ap.parse_args()
    w = csv.writer(sys.stdout)
    w.writerow(["log", "step", "lap_s", "mm_per_s", "ref_epoch"])
    for p in a.logs:
        for step, t, lap in parse(p):
            if lap is None or any(abs(t - d) < 2 for d in a.drop):
                continue
            w.writerow([p.split("/")[-1], step, round(lap, 1),
                        round(a.loop_mm / lap, 1), round(t, 1)])


if __name__ == "__main__":
    main()
