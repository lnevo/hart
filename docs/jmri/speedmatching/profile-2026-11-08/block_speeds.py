#!/usr/bin/env python3
"""Per-block and per-step speed tables from the runner logs.

Writes block_events.csv (every block transit), block_summary.csv (mean speed per
loco, step and block, and its ratio to the loop mean at that step) and
speed_by_step.csv (loop-level speed per loco and step).

implied_len_mm is the loop length shared out by each block's share of the lap time,
i.e. the length the block would have if the loco ran at one speed all round.

A transit is entry-to-entry: the time from the loco's front lighting a block
sensor to it lighting the next block's sensor, over the length of the first block.
Only timed laps are used, plus the valid first laps listed in EXTRA_LAPS.
"""
import csv
import re
import statistics
import sys
from collections import defaultdict

# loop order in the east direction (2738's forward): sensor name -> length mm
EAST = [
    ("BS Switch 7b", 254.0), ("BS East Ext", 2235.2), ("BS Switch 5", 254.0)]
LOOP = [  # east order starting at East Ext
    ("BS East Ext", 2235.2), ("BS Switch 7b", 254.0), ("BS Main East", 4699.0),
    ("BS Switch 33", 254.0), ("BS East Lead", 4368.8), ("BS Switch 35a", 254.0),
    ("BS Switch 37 / BS McKeesport", 254.0), ("BS K-2", 3111.5), ("BS K-1", 3111.5),
    ("BS Switch 39 / BS McKees Rocks", 254.0), ("BS Switch 35b", 254.0),
    ("BS West Ext", 4064.0), ("BS Switch 23a", 254.0), ("BS Main West", 5588.0),
    ("BS Switch 1", 254.0), ("BS Brick-Plane", 1828.8), ("BS Switch 5", 254.0)]
LOOP_MM = sum(l for _, l in LOOP)
# direction of each log (2738 ran east, 2121 ran west)
LOGS = {"steprun_2121_b.log": "CSX 2121", "steprun_2121_c.log": "CSX 2121",
        "steprun_2121_d.log": "CSX 2121", "steprun_2738_b.log": "CSX 2738"}
# epoch windows to leave out (bad laps) and first laps that are valid full laps
DROP = [("steprun_2121_b.log", 1794132892.3, 1794132972.8)]
EXTRA_LAPS = [("steprun_2121_b.log", 8), ("steprun_2121_c.log", 8)]  # step 8 first lap


def read(path):
    # The raw logs of 2026-11-08 name the two extension tracks "BS East Main Ext" / "BS West Main Ext".
    seen, ev = set(), []
    for line in open(path):
        line = line.replace("BS East Main Ext", "BS East Ext").replace("BS West Main Ext", "BS West Ext")
        p = line.rstrip("\n").split(" ", 1)
        if len(p) < 2 or line in seen and p[1].startswith("SENS"):
            continue
        seen.add(line)
        try:
            ev.append((float(p[0]), p[1]))
        except ValueError:
            pass
    return ev


def main(logdir, outdir="."):
    rows = []
    for name, loco in LOGS.items():
        east = loco == "CSX 2738"
        order = LOOP if east else [(s, l) for s, l in reversed(LOOP)]
        names = [s for s, _ in order]
        length = dict(order)
        step, first_ref, lap_i, state = None, None, 0, {}
        acts = []  # (t, sensor, step, timed, lap)
        for t, m in read(f"{logdir}/{name}"):
            if m.startswith("STEP "):
                step, first_ref, lap_i = int(m.split()[1]), None, 0
            elif re.match(r"REF \d+$", m):
                if first_ref is None:
                    first_ref = t
                lap_i += 1
            elif m.startswith("SENS ") and step is not None:
                s, st = m[5:].rsplit(" ", 1)
                if st == "ACTIVE" and state.get(s) != "ACTIVE" and s in length:
                    timed = first_ref is not None and t > first_ref
                    extra = first_ref is None and (name, step) in EXTRA_LAPS and lap_i == 0
                    acts.append((t, s, step, timed or extra, lap_i))
                if st in ("ACTIVE", "INACTIVE"):
                    state[s] = st
        for (t0, s0, st0, ok0, lap0), (t1, s1, st1, ok1, lap1) in zip(acts, acts[1:]):
            i = names.index(s0)
            if names[(i + 1) % len(names)] != s1 or st0 != st1 or not ok0:
                continue
            if any(name == n and a <= t0 <= b for n, a, b in DROP):
                continue
            dt = t1 - t0
            rows.append((loco, name, st0, lap0, s0[3:], length[s0], round(t0, 3),
                         round(t1, 3), round(dt, 2), round(length[s0] / dt, 1)))
    with open(f"{outdir}/block_events.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["loco", "log", "step", "lap_index", "block", "block_len_mm",
                    "entry_epoch", "next_entry_epoch", "transit_s", "mm_per_s"])
        w.writerows(rows)
    by = defaultdict(list)
    for r in rows:
        by[(r[0], r[2], r[4])].append(r[9])
    step_tot = defaultdict(lambda: [0.0, 0.0, 0])
    for r in rows:
        k = (r[0], r[2])
        step_tot[k][0] += r[5]
        step_tot[k][1] += r[8]
    with open(f"{outdir}/block_summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["loco", "step", "block", "block_len_mm", "n", "mean_mm_per_s",
                    "stdev_mm_per_s", "ratio_to_loop_mean", "implied_len_mm",
                    "implied_vs_nominal_pct"])
        dts = defaultdict(list)
        for r in rows:
            dts[(r[0], r[2], r[4])].append(r[8])
        share = defaultdict(float)
        for (loco, step, blk), v in dts.items():
            share[(loco, step)] += statistics.mean(v)
        for (loco, step, blk), v in sorted(by.items(), key=lambda x: (x[0][0], x[0][1], x[0][2])):
            tot = step_tot[(loco, step)]
            loop_mean = tot[0] / tot[1]
            ln = next(r[5] for r in rows if r[0] == loco and r[2] == step and r[4] == blk)
            implied = LOOP_MM * statistics.mean(dts[(loco, step, blk)]) / share[(loco, step)]
            w.writerow([loco, step, blk, ln, len(v), round(statistics.mean(v), 1),
                        round(statistics.stdev(v), 1) if len(v) > 1 else "",
                        round(statistics.mean(v) / loop_mean, 3), round(implied, 0),
                        round(100.0 * (implied - ln) / ln, 0)])
    laps = defaultdict(list)
    for line in csv.DictReader(open(f"{outdir}/results.csv")):
        laps[(LOGS[line["log"]], int(line["step"]))].append(float(line["lap_s"]))
    for line in csv.DictReader(open(f"{outdir}/manual_laps.csv")):
        laps[(line["loco"], int(line["step"]))].append(float(line["lap_s"]))
    with open(f"{outdir}/speed_by_step.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["loco", "step", "laps", "mean_lap_s", "mean_mm_per_s", "stdev_mm_per_s",
                    "mean_scale_mph_ho"])
        for (loco, step), v in sorted(laps.items()):
            sp = [LOOP_MM / x for x in v]
            w.writerow([loco, step, len(v), round(statistics.mean(v), 1),
                        round(statistics.mean(sp), 1),
                        round(statistics.stdev(sp), 1) if len(sp) > 1 else "",
                        round(statistics.mean(sp) * 87 / 1000 * 2.23694, 1)])
    print("loop %.1f mm, %d block transits" % (LOOP_MM, len(rows)))


if __name__ == "__main__":
    main(*sys.argv[1:3]) if len(sys.argv) > 1 else sys.exit("usage: block_speeds.py LOGDIR [OUTDIR]")
