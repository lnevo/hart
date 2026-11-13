#!/usr/bin/env python3
"""Speed profile analysis for the step runner logs (jython/step_runner.py).

Reads one or more runner logs and writes, per (loco, direction) and step, the speed over
known block lengths: a rolling median and relative standard deviation, found by replaying
the same stop rule the runner used live (liverule.py). Warm-up laps are discarded. It also
compares the two locos in the consist pairing (first loco forward against the second in
reverse, and the other way round), and reports the drift of the repeated top step.

    analyze.py LOG [LOG ...] [--lengths CSV] [--trusted anyrail,inferred] [--out DIR]
               [--pair "CSX 2121,CSX 2738"]

Lengths come from jmri/layouts/hart/data/block_lengths.csv (inches). Only trusted rows are
used: the value in the `basis` column (or the `flag` column when there is no basis column)
must be in --trusted, which defaults to anyrail,inferred. "assigned" counts only if you
pass it.
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import liverule as lr  # noqa: E402

DEFAULT_LENGTHS = HERE.parents[1] / "data" / "block_lengths.csv"
DEFAULT_TRUSTED = ("anyrail", "inferred")  # "assigned" counts only when passed explicitly
MM_PER_INCH = 25.4

# The loop in the east direction, starting at East Main Ext: (block sensor, block_lengths.csv
# user_name). The pairing is explicit because the CSV names tracks and switches, not sensors.
LOOP = [
    ("BS East Main Ext", "Track East Main Ext"), ("BS Switch 7b", "OS Switch 7b"),
    ("BS Main East", "Track Main East"), ("BS Switch 33", "OS Switch 33"),
    ("BS East Lead", "Track East Lead"), ("BS Switch 35a", "OS Switch 35a"),
    ("BS Switch 37 / BS McKeesport", "OS Switch 37"), ("BS K-2", "Track K-2"),
    ("BS K-1", "Track K-1"), ("BS Switch 39 / BS McKees Rocks", "OS Switch 39"),
    ("BS Switch 35b", "OS Switch 35b"), ("BS West Main Ext", "Track West Main Ext"),
    ("BS Switch 23a", "OS Switch 23a"), ("BS Main West", "Track Main West"),
    ("BS Switch 1", "OS Switch 1"), ("BS Brick-Plane", "Track Brick-Plane"),
    ("BS Switch 5", "OS Switch 5"),
]
ORDER = [s for s, _ in LOOP]


def load_lengths(path=DEFAULT_LENGTHS, trusted=DEFAULT_TRUSTED, loop=LOOP):
    """dict sensor -> length in mm, None where the CSV row is missing or not trusted."""
    with open(path, newline="") as fh:
        rows = {r["user_name"]: r for r in csv.DictReader(fh)}
    out = {}
    for sensor, name in loop:
        row = rows.get(name)
        if row is None:
            out[sensor] = None
            continue
        if "basis" in row:
            ok = (row["basis"] or "").strip() in trusted
        else:
            # block_lengths.csv keeps the basis in its "flag" column (anyrail, inferred, ...);
            # the same set applies: "assigned" (the pre-AnyRail value) only if passed
            ok = (row.get("flag") or "").strip() in trusted
        try:
            mm = float(row["inches"]) * MM_PER_INCH if ok else None
        except ValueError:
            mm = None
        if mm is not None:
            # a hidden throat stub shares this track's detector, so the sensor covers both
            for r in rows.values():
                if (r.get("flag") or "").strip() == "stub" and \
                        (r.get("occupancy_sensor") or "").strip() == sensor:
                    try:
                        mm += float(r["inches"]) * MM_PER_INCH
                    except ValueError:
                        pass
        out[sensor] = mm
    return out


_LINE = re.compile(r"^([\d.]+) (.*)$")
_RUN = re.compile(r"RUN loco=(.*) direction=(\w+)")
_CFG = re.compile(r"(\w+)=([^\s@]+)")
STATES = ("ACTIVE", "INACTIVE", "UNKNOWN", "INCONSISTENT")
# CFG names the runner logs -> the keyword names used here
CFG_KEYS = {"k": ("k", int), "rel": ("rel", float), "max": ("max_n", int),
            "settle": ("settle", int), "low_max": ("low_max", int), "high_span": ("high_span", int)}


def parse_log(lines, loco=None, direction=None, source=""):
    """Split runner log lines into runs: list of dicts
    {loco, direction, log, complete, cfg, lengths, steps: [{step, occurrence, events}]}.
    Every RUN line starts a new run (the same loco and direction twice stay two runs);
    complete is True when the runner logged "STOP all steps complete".

    Warm-up events (between WARMUP and the first STEP) are dropped. A log without a RUN
    line (older logs) needs loco and direction given."""
    runs, run, cur, seen, active = [], None, None, {}, {}
    for line in lines:
        m = _LINE.match(line.strip())
        if not m:
            continue
        t, msg = float(m.group(1)), m.group(2)
        if msg.startswith("RUN "):
            mm = _RUN.match(msg)
            if not mm:
                continue
            run = {"loco": mm.group(1), "direction": mm.group(2), "steps": [], "cfg": {},
                   "lengths": None, "log": source, "complete": False}
            runs.append(run)
            seen.clear()
            active.clear()
            cur = None
        elif msg.startswith("STEP "):
            if run is None:
                if loco is None or direction is None:
                    raise ValueError("log has no RUN line: give loco and direction")
                run = {"loco": loco, "direction": direction, "steps": [], "cfg": {},
                       "lengths": None, "log": source, "complete": False}
                runs.append(run)
            n = int(msg.split()[1])
            seen[n] = seen.get(n, 0) + 1
            cur = {"step": n, "occurrence": seen[n], "events": []}
            run["steps"].append(cur)
        elif msg.startswith("CFG ") and run is not None:
            for key, val in _CFG.findall(msg[4:]):
                if key in CFG_KEYS:
                    name, conv = CFG_KEYS[key]
                    run["cfg"][name] = conv(val)
        elif msg.startswith("LENGTHS ") and run is not None:
            run["lengths"] = json.loads(msg[8:])
        elif msg.startswith("STOP ") and run is not None:
            run["complete"] = msg.strip() == "STOP all steps complete"
        elif msg.startswith("WARMUP "):
            cur = None
        elif msg.startswith("SENS "):
            name, st = msg[5:].rsplit(" ", 1)
            if cur is not None and st == "ACTIVE" and active.get(name) != "ACTIVE":
                cur["events"].append((t, name))
            if st in STATES:  # any state counts: UNKNOWN between two ACTIVEs is a new ACTIVE
                active[name] = st
    return runs


def step_readings(events, step, lengths, order=ORDER, settle=lr.SETTLE_EVENTS,
                  low_max=lr.LOW_MAX, high_span=lr.HIGH_SPAN):
    """Readings for one step, taken the way the runner took them live.

    Each is (mm_per_s, seconds, mm, blocks)."""
    reader = lr.SpanReader(order, lengths, settle)
    reader.restart(lr.span_for_step(step, low_max, high_span))
    out = []
    for t, sensor in events:
        r = reader.feed(t, sensor)
        if r is not None:
            out.append(r)
    return out


def travel(events, order=ORDER):
    """'east' (the order of LOOP) or 'west', from the order the sensors lit; '' if unclear."""
    up = down = 0
    for (_, a), (_, b) in zip(events, events[1:]):
        if a in order and b in order:
            d = (order.index(b) - order.index(a)) % len(order)
            up += d == 1
            down += d == len(order) - 1
    return "east" if up > down else "west" if down > up else ""


def summarize_runs(runs, lengths, k=lr.STOP_K, rel=lr.STOP_REL, max_n=lr.MAX_READINGS,
                   use_logged=True, csv_lengths=False, **kw):
    """One entry per run, in input order: {run, loco, direction, log, complete, rows}.

    A run's own CFG line (stop rule settings) and LENGTHS line (the lengths the job was built
    with) are replayed as the runner had them; the arguments are used only for logs that lack
    them. use_logged=False ignores both; csv_lengths=True swaps only the lengths for the ones
    given (the logged stop-rule settings still apply)."""
    out = []
    for n, run in enumerate(runs, start=1):
        rows = []
        p = {"k": k, "rel": rel, "max_n": max_n}
        p.update(kw)
        run_lengths = lengths
        if use_logged:
            p.update(run.get("cfg") or {})
            if not csv_lengths:
                run_lengths = run.get("lengths") or lengths
        k_, rel_, max_ = p.pop("k"), p.pop("rel"), p.pop("max_n")
        for s in run["steps"]:
            rd = step_readings(s["events"], s["step"], run_lengths, **p)
            speeds = [r[0] for r in rd]
            row = {"loco": run["loco"], "direction": run["direction"], "step": s["step"],
                   "occurrence": s["occurrence"], "travel": travel(s["events"]),
                   "n": len(speeds), "blocks": rd[-1][3] if rd else 0, "run": n}
            if speeds:
                used, why, win = lr.replay(speeds, k_, rel_, max_)
                row.update(used=used, reason=why or "open", median=lr.median(win),
                           rel_sd=lr.rel_stdev(win) if len(win) > 1 else None,
                           settled=(why == "settled"))
            else:
                row.update(used=0, reason="no readings", median=None, rel_sd=None,
                           settled=False)
            rows.append(row)
        out.append({"run": n, "loco": run["loco"], "direction": run["direction"],
                    "log": run.get("log", ""), "complete": bool(run.get("complete")), "rows": rows})
    return out


def latest_runs(summaries):
    """dict (loco, direction) -> rows of the latest complete run (else the latest run)."""
    pick = {}
    for r in summaries:
        key = (r["loco"], r["direction"])
        old = pick.get(key)
        if old is None or (r["complete"] or not old["complete"]):
            pick[key] = r
    return {k: v["rows"] for k, v in pick.items()}


def summarize(runs, lengths, *args, **kw):
    """dict (loco, direction) -> rows of the latest complete run of that loco and direction.
    Runs are never merged; summarize_runs keeps all of them."""
    return latest_runs(summarize_runs(runs, lengths, *args, **kw))


def step_label(row):
    return str(row["step"]) if row["occurrence"] == 1 else "%d#%d" % (row["step"], row["occurrence"])


def top_drift(rows):
    """Percent change of the last repeat of the highest step against its first measurement."""
    if not rows:
        return None
    top = max(r["step"] for r in rows)
    same = [r for r in rows if r["step"] == top and r["median"] is not None]
    if len(same) < 2:
        return None
    return {"step": top, "first": same[0]["median"], "last": same[-1]["median"],
            "drift_pct": 100.0 * (same[-1]["median"] - same[0]["median"]) / same[0]["median"]}


def first_by_step(rows):
    """step -> median of the first measurement of that step."""
    return {r["step"]: r["median"] for r in rows if r["occurrence"] == 1 and r["median"] is not None}


def compare(result, a, b):
    """Compare run key a = (loco, direction) with b: per step, b against a in percent.

    same_travel is False when the two ran in different physical directions round the loop."""
    ra, rb = result.get(a, []), result.get(b, [])
    sa, sb = first_by_step(ra), first_by_step(rb)
    ta = {r["step"]: r["travel"] for r in ra if r["occurrence"] == 1}
    tb = {r["step"]: r["travel"] for r in rb if r["occurrence"] == 1}
    out = []
    for step in sorted(set(sa) & set(sb)):
        out.append({"step": step, "a": sa[step], "b": sb[step],
                    "b_vs_a_pct": 100.0 * (sb[step] - sa[step]) / sa[step],
                    "same_travel": ta.get(step) == tb.get(step) and ta.get(step) != ""})
    return out


def pairings(first, second):
    """The consist pairings: first forward with second reversed, and the other way round."""
    return [((first, "forward"), (second, "reverse")),
            ((first, "reverse"), (second, "forward"))]


def fmt(x, nd=1):
    return "" if x is None else round(x, nd)


def write_outputs(result, pair, out_dir, summaries=None):
    """profile.csv and drift.csv hold every run (one `run` number each); compare.csv uses the
    latest complete run of each loco and direction. Without summaries, result is one run."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if summaries is None:
        summaries = [{"run": 1, "loco": k[0], "direction": k[1], "log": "", "complete": True,
                      "rows": rows} for k, rows in sorted(result.items())]
    with open(out_dir / "profile.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["loco", "direction", "step", "travel", "blocks_per_reading", "readings",
                    "readings_used", "median_mm_s", "rel_sd_pct", "settled", "reason",
                    "run", "run_complete", "log"])
        for sm in summaries:
            for r in sm["rows"]:
                w.writerow([r["loco"], r["direction"], step_label(r), r["travel"], r["blocks"],
                            r["n"], r["used"], fmt(r["median"]),
                            fmt(None if r["rel_sd"] is None else 100 * r["rel_sd"], 2),
                            r["settled"], r["reason"], sm["run"], sm["complete"], sm["log"]])
    with open(out_dir / "drift.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["loco", "direction", "run", "top_step", "first_mm_s", "last_mm_s", "drift_pct"])
        for sm in summaries:  # a run is compared with itself only
            d = top_drift(sm["rows"])
            if d:
                w.writerow([sm["loco"], sm["direction"], sm["run"], d["step"], fmt(d["first"]),
                            fmt(d["last"]), fmt(d["drift_pct"], 2)])
    if pair:
        with open(out_dir / "compare.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["pairing", "step", "a_mm_s", "b_mm_s", "b_vs_a_pct", "same_travel"])
            for a, b in pairings(*pair):
                for c in compare(result, a, b):
                    w.writerow(["%s %s vs %s %s" % (a + b), c["step"], fmt(c["a"]), fmt(c["b"]),
                                fmt(c["b_vs_a_pct"], 1), c["same_travel"]])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--lengths", default=str(DEFAULT_LENGTHS))
    ap.add_argument("--trusted", default=",".join(DEFAULT_TRUSTED),
                    help="values that count as trusted in the basis column (or the flag column when there is\n                         no basis column); default anyrail,inferred, add assigned only on purpose")
    ap.add_argument("--out", default=".")
    ap.add_argument("--pair", default="CSX 2121,CSX 2738",
                    help="the consist pair: leader,follower (follower runs reversed)")
    ap.add_argument("--loco", help="for logs without a RUN line")
    ap.add_argument("--direction", help="for logs without a RUN line")
    ap.add_argument("--csv-lengths", action="store_true",
                    help="use the lengths from --lengths, not the ones logged by the runner (the logged\n                         stop-rule settings still apply)")
    ap.add_argument("--k", type=int, default=lr.STOP_K)
    ap.add_argument("--rel", type=float, default=lr.STOP_REL)
    ap.add_argument("--max", type=int, default=lr.MAX_READINGS, dest="max_n")
    a = ap.parse_args(argv)
    lengths = load_lengths(a.lengths, tuple(a.trusted.split(",")))
    n_ok = sum(v is not None for v in lengths.values())
    print("trusted block lengths: %d of %d loop blocks" % (n_ok, len(lengths)))
    runs = []
    for p in a.logs:
        runs += parse_log(Path(p).read_text().splitlines(), a.loco, a.direction, Path(p).name)
    summaries = summarize_runs(runs, lengths, a.k, a.rel, a.max_n, csv_lengths=a.csv_lengths)
    result = latest_runs(summaries)
    pair = tuple(a.pair.split(",")) if a.pair else None
    write_outputs(result, pair, a.out, summaries)
    for key, rows in sorted(result.items()):
        d = top_drift(rows)
        print("%s %s: %d steps%s" % (key[0], key[1], len(rows),
              "" if not d else ", step %d drift %+.1f%%" % (d["step"], d["drift_pct"])))
    print("wrote profile.csv, drift.csv%s in %s" % (", compare.csv" if pair else "", a.out))


if __name__ == "__main__":
    main()
