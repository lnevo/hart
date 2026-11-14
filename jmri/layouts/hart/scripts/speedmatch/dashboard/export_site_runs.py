#!/usr/bin/env python3
"""Write recorded speed-match runs as static JSON for the website. Python 3 standard library only.

    python3 export_site_runs.py ~/speedmatch-logs/2026-11-13 [--out www/data/speedmatch]

The logs are fed, oldest first, through the dashboard's own state code (dashstate.Store), so the
page shows what the live dashboard showed. For each published run the file runs/<id>.json holds
the snapshot the live page would send once that run had ended: every run up to and including it
(the chart and the comparison read their curves), the run itself in full detail, and `note`,
the label this script adds. index.json lists the runs, newest first.

Only steprun_, pass_ and stoptest_ logs are published. moveto_ (positioning) and the watch logs
are not. The logs themselves are never copied; the repo holds no *.log files.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dashsources as sources  # noqa: E402
import dashstate as state  # noqa: E402

PUBLISH = ("steprun", "pass", "stoptest")
DEFAULT_OUT = sources.REPO / "www/data/speedmatch"

# What the record says about each run of 2026-11-13 (docs/jmri/speedmatching/profile-2026-11-13).
# level: used | superseded | not-used. Times are the Pi's clock, from the file names.
NOTES = {
    "steprun_CSX_2738_forward_20261113_114309.log": (
        "not-used", "Not used",
        "Before a fix in the run tool, the loco ran the opposite way to the one asked, so this "
        "is not a forward profile."),
    "steprun_CSX_2738_reverse_20261113_114309.log": (
        "used", "Used",
        "2738 reverse profile, steps 16 to 126, before any change to the decoder."),
    "steprun_CSX_2738_reverse_20261113_120156.log": (
        "used", "Used",
        "Steps 8 and 24 of the 2738 reverse profile, measured again."),
    "steprun_CSX_2738_forward_20261113_125138.log": (
        "superseded", "Superseded",
        "Replaced by the 16:57 run, made after CV66 went from 128 to 135."),
    "pass_CSX_2121_reverse_step24_20261113_154325.log": (
        "used", "Used",
        "Timed pass at step 24, Switch 5 to Switch 15, that places OS Switch 7 and OS Switch 13 on loop 2."),
    "pass_CSX_2121_reverse_step48_20261113_154720.log": (
        "used", "Used",
        "Timed pass at step 48, Switch 5 to Switch 15, that places OS Switch 7 and OS Switch 13 on loop 2."),
    "steprun_CSX_2121_reverse_20261113_161505.log": (
        "used", "Used for loop 2",
        "Lap survey of loop 2 at steps 32, 48 and 64, for block lengths, not a speed profile. "
        "Each step hit its reading limit, so one lap was usable: it confirmed the Switch 7 and "
        "Switch 13 placement within 20 mm and gave the S-R length."),
    "steprun_CSX_2121_forward_20261113_162410.log": (
        "used", "Used", "2121 forward profile, steps 16 to 126."),
    "steprun_CSX_2121_reverse_20261113_163539.log": (
        "used", "Used",
        "2121 reverse profile, steps 16 to 126. Step 8 read no speed here; the 17:29 run has it."),
    "steprun_CSX_2738_forward_20261113_165713.log": (
        "used", "Used",
        "2738 forward profile, steps 32 to 126, after CV66 went from 128 to 135."),
    "steprun_CSX_2738_forward_20261113_171458.log": (
        "used", "Used",
        "Steps 8 to 24 of the 2738 forward profile, after CV69 and CV70 each moved one notch."),
    "steprun_CSX_2738_reverse_20261113_171459.log": (
        "used", "Used",
        "Steps 16 and 24 of the 2738 reverse profile, after CV69 and CV70 each moved one notch."),
    "steprun_CSX_2121_forward_20261113_172606.log": (
        "used", "Used",
        "Step 16 of the 2121 forward profile, measured again. Step 8 was set by hand to 50.6 "
        "(the clean Main West block); this run's 54.7 includes one flicker reading."),
    "steprun_CSX_2121_reverse_20261113_172957.log": (
        "used", "Used", "Steps 8 and 16 of the 2121 reverse profile, measured again."),
    "stoptest_CSX_2121_reverse_20261113_174751.log": (
        "used", "Used", "Momentum test, step 32, in the 2738 against 2121 comparison."),
    "stoptest_CSX_2121_reverse_20261113_174927.log": (
        "used", "Used", "Momentum test, step 96, in the 2738 against 2121 comparison."),
    "stoptest_CSX_2738_forward_20261113_175212.log": (
        "used", "Used", "Momentum test, step 32, in the 2738 against 2121 comparison."),
    "stoptest_CSX_2738_forward_20261113_175331.log": (
        "used", "Used", "Momentum test, step 96, in the 2738 against 2121 comparison."),
}

# Logs that are never published. The 18:04 and 18:05 stop tests were the coupled pair, driven
# through 2121: Switch 33 had been closed under the pair, so the first ran the wrong route and
# the second refused to start. They are not 2121 solo tests and say nothing about momentum.
SKIP = {
    "stoptest_CSX_2121_reverse_20261113_180458.log",
    "stoptest_CSX_2121_reverse_20261113_180555.log",
}


def stoptest_view(lines, name):
    """The facts of a stop-test log: step, trigger, which block lit how long after the stop
    command, and the last block lit. parse_line splits the lines; nothing else is read."""
    m = re.match(r"stoptest_(CSX_\d+)_(forward|reverse)_", name)  # a log with no STOPTEST line (the run never began)
    info = {"step": None, "trigger": None, "loco": m.group(1).replace("_", " ") if m else None,
            "direction": m.group(2) if m else None}
    cmd_t, rows, last, t_first, t_end = None, [], None, None, None
    for ln in lines:
        p = state.parse_line(ln)
        if p is None:
            continue
        t, kind, rest = p
        t_first = t if t_first is None else t_first
        if kind == "STOPTEST":
            m = re.match(r"loco=(.*?)\s+direction=(\S+)\s+step=(\d+)\s+trigger=(.*)$", rest)  # the loco id holds a space
            if m:
                info.update(loco=m.group(1), direction=m.group(2), step=int(m.group(3)), trigger=m.group(4).strip())
        elif kind == "STOPCMD":
            cmd_t = t
        elif kind == "SENS" and rest.endswith(" ACTIVE"):
            if cmd_t is not None:
                last = rest[: -len(" ACTIVE")]
                rows.append({"sensor": last, "t_rel": round(t - cmd_t, 2)})
        elif kind in ("STOP", "END"):
            t_end = t
    info.update(rows=rows, rest=last, started=cmd_t is not None, t_first=t_first, t_end=t_end)
    return info


def read_published(logdir):
    """[(id, lines)] for the published logs, oldest first by their first timestamp."""
    paths = [p for p in sorted(Path(logdir).glob("*.log"))
             if state.kind_of_log(p.name) in PUBLISH and p.name not in SKIP]
    logs = []
    for rid, lines in sources.read_logs(paths):
        first = next((p for p in map(state.parse_line, lines) if p), None)
        logs.append((first[0] if first else 0.0, rid, lines))
    logs.sort(key=lambda x: (x[0], x[1]))
    return [(rid, lines) for _, rid, lines in logs]


def export(logdir, out):
    state.warm_caches()
    logs = read_published(logdir)
    unknown = [rid for rid, _ in logs if rid not in NOTES]
    if unknown:
        raise SystemExit("no label for: " + ", ".join(unknown))
    reference = sources.reference_curves()
    out = Path(out)
    (out / "runs").mkdir(parents=True, exist_ok=True)
    for old in (out / "runs").glob("*.json"):
        old.unlink()
    store = state.Store()
    index = []
    for rid, lines in logs:
        for ln in lines:
            store.feed(rid, ln)
        run = store.runs[rid]
        snap = store.snapshot(now=run.t_end or run.t_last, reachable=True, message=None, mode="recorded", focus=rid)
        focus = next(r for r in snap["runs"] if r["id"] == rid)
        level, headline, text = NOTES[rid]
        stop = None
        if run.kind == "stoptest":
            # dashstate does not read STOPTEST lines (no loco, a "stopped: quiet" banner): fill them in
            stop = stoptest_view(lines, rid)
            loco = stop["loco"].split()[-1] if stop["loco"] else None
            focus.update(kind="stoptest", loco=loco, road=state.LOCO_ROAD.get(loco, stop["loco"]),
                         direction=stop["direction"], step=stop["step"], banner=None, stoptest=stop,
                         status="done" if stop["started"] else "stopped",
                         reason=None if stop["started"] else "did not start", t0=stop["t_first"],
                         t_end=stop["t_end"], elapsed=(stop["t_end"] - stop["t_first"]) if stop["t_end"] else None)
        elif focus["banner"] and focus["status"] == "done":
            focus["banner"] = None  # a step run that finished is not a stop
        for r in snap["runs"]:
            r["photo"] = r["model"] = None
        snap["reference"] = reference
        snap["note"] = {"level": level, "headline": headline, "text": text}
        (out / "runs" / (rid[:-4] + ".json")).write_text(
            json.dumps(snap, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
        index.append({
            "id": rid[:-4], "file": "runs/%s.json" % rid[:-4], "kind": focus["kind"], "loco": focus["loco"],
            "road": focus["road"], "direction": focus["direction"], "route": focus["route"], "start": focus["t0"],
            "steps": [c["step"] for c in focus["curve"]], "pass_step": (focus["pass"] or {}).get("step"),
            "stop_step": stop["step"] if stop else None, "status": focus["status"], "reason": focus["reason"],
            "outcome": level, "headline": headline, "note": text})
    index.sort(key=lambda r: (-(r["start"] or 0), r["id"]))
    (out / "index.json").write_text(json.dumps({"runs": index}, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return index


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logdir", help="folder with the run logs, one session")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="where the JSON goes (default www/data/speedmatch)")
    a = ap.parse_args(argv)
    print("wrote %d runs to %s" % (len(export(a.logdir, a.out)), a.out))


if __name__ == "__main__":
    main()
