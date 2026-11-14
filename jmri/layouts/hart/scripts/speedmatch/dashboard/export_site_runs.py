#!/usr/bin/env python3
"""Write recorded speed-match runs as static JSON for the website. Python 3 standard library only.

    python3 export_site_runs.py ~/speedmatch-logs/2026-11-13 \
        --labels docs/jmri/speedmatching/profile-2026-11-13/site_labels.json [--out www/data/speedmatch]

The logs are fed, oldest first, through the dashboard's own state code (dashstate.Store), so the
page shows what the live dashboard showed. For each published run the file runs/<id>.json holds
the snapshot the live page would send once that run had ended: every run up to and including it
(the chart and the comparison read their curves), the run itself in full detail, and `note`,
the label this script adds. runs/<id>.frames.json is the run's replay, one frame per log line
that changed the view (frames_of), which the page plays when asked. index.json lists the runs,
newest first.

Only steprun_, pass_ and stoptest_ logs are published. moveto_ (positioning) and the watch logs
are not. The logs themselves are never copied; the repo holds no *.log files.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dashsources as sources  # noqa: E402
import dashstate as state  # noqa: E402

PUBLISH = ("steprun", "pass", "stoptest")
DEFAULT_OUT = sources.REPO / "www/data/speedmatch"

def load_labels(path):
    """The session's labels file: {"runs": {log name: {level, headline, text}}, "skip": {log name: why}}.
    level is used, superseded or not-used. Every published log needs an entry; skipped logs are
    left out. The file is kept with the session's record (docs/jmri/speedmatching/profile-<date>/)."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    runs, skip = d.get("runs") or {}, d.get("skip") or {}
    bad = [k for k, v in runs.items() if v.get("level") not in ("used", "superseded", "not-used")]
    if bad:
        raise SystemExit("labels: unknown level for " + ", ".join(sorted(bad)))
    return {k: (v["level"], v["headline"], v["text"]) for k, v in runs.items()}, set(skip)


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


def read_published(logdir, skip=()):
    """[(id, lines)] for the published logs, oldest first by their first timestamp."""
    paths = [p for p in sorted(Path(logdir).glob("*.log"))
             if state.kind_of_log(p.name) in PUBLISH and p.name not in skip]
    logs = []
    for rid, lines in sources.read_logs(paths):
        first = next((p for p in map(state.parse_line, lines) if p), None)
        logs.append((first[0] if first else 0.0, rid, lines))
    logs.sort(key=lambda x: (x[0], x[1]))
    return [(rid, lines) for _, rid, lines in logs]


def fix_focus(focus, kind, lines, name, now=None):
    """Fill in what dashstate leaves out of the focused run's view, in place. lines are the log's
    lines so far; now is the time of the last one during a replay (None once the run has ended).
    Returns the stop-test view, or None for other kinds."""
    focus["photo"] = focus["model"] = None
    if kind == "stoptest":
        # dashstate does not read STOPTEST lines (no loco, a "stopped: quiet" banner): fill them in
        stop = stoptest_view(lines, name)
        loco = stop["loco"].split()[-1] if stop["loco"] else None
        end = stop["t_end"] if stop["t_end"] is not None else now
        status = ("done" if stop["started"] else "stopped") if stop["t_end"] is not None else (
            "measuring" if stop["started"] else "starting")
        focus.update(kind="stoptest", loco=loco, road=state.LOCO_ROAD.get(loco, stop["loco"]),
                     direction=stop["direction"], step=stop["step"], banner=None, stoptest=stop,
                     status=status, reason="did not start" if status == "stopped" else None,
                     t0=stop["t_first"], t_end=stop["t_end"],
                     elapsed=(end - stop["t_first"]) if end is not None and stop["t_first"] is not None else None)
        return stop
    if focus["banner"] and focus["status"] == "done":
        focus["banner"] = None  # a step run that finished is not a stop
    return None


def diff_frame(prev, cur):
    """The fields of cur that differ from prev, small enough to publish one per log line. Two
    lists are sent as changes: blocks (the same route, so index -> changed fields) as "blocks~",
    and events (a window of the newest) as the new ones in "events+". app.js applyFrame() undoes it."""
    out = {}
    for k, v in cur.items():
        if k in prev and prev[k] == v:
            continue
        pv = prev.get(k)
        if k == "blocks" and isinstance(pv, list) and isinstance(v, list) and len(pv) == len(v):
            ch = {}
            for i, (a, b) in enumerate(zip(pv, v)):
                d = {f: x for f, x in b.items() if a.get(f) != x}
                if d and set(a) <= set(b):
                    ch[str(i)] = d
                elif d:
                    ch[str(i)] = {"=": b}
            out["blocks~"] = ch
        elif k == "events" and isinstance(pv, list) and pv and isinstance(v, list) and pv[-1] in v:
            out["events+"] = v[len(v) - 1 - v[::-1].index(pv[-1]) + 1:]
        else:
            out[k] = v
    gone = [k for k in prev if k not in cur]
    if gone:
        out["-"] = gone
    return out


EVENTS_SHOWN = 15  # dashstate sends the newest 15 events of the focused run


def apply_frame(prev, d):
    """The inverse of diff_frame (the test checks the pair; app.js has the same steps)."""
    cur = dict(prev)
    for k in d.get("-", []):
        cur.pop(k, None)
    for k, v in d.items():
        if k == "blocks~":
            bl = [dict(b) for b in cur["blocks"]]
            for i, ch in v.items():
                bl[int(i)] = dict(ch["="]) if "=" in ch else {**bl[int(i)], **ch}
            cur["blocks"] = bl
        elif k == "events+":
            cur["events"] = (cur["events"] + v)[-EVENTS_SHOWN:]
        elif k != "-":
            cur[k] = v
    return cur


def run_view(store, rid, lines, reference, note=None, now=None, mode="recorded"):
    """(snapshot, index entry) for one run already fed into store. rid is the store's id (a log
    name, or a path on the Pi); lines are the log's lines. The snapshot is what the live page
    would show with this run in focus; note is the record's label (None on the Pi, where a run
    has no label yet). Shared by this export and publish_live.py, so both write the same files."""
    run = store.runs[rid]
    name = Path(rid).name
    rid_out = name[:-4] if name.endswith(".log") else name
    snap = store.snapshot(now=now or run.t_end or run.t_last, reachable=True, message=None, mode=mode, focus=rid)
    focus = next(r for r in snap["runs"] if r["id"] == rid)
    stop = fix_focus(focus, run.kind, lines, name)
    # Only published kinds, and only this run and the ones that began before it, as the live page
    # showed at the time. The export feeds the logs in order so later runs are not in the store yet;
    # the Pi's store holds them all. A run with no time yet is newer than everything; equal times
    # go by the order the store met the logs.
    order = {r: i for i, r in enumerate(store.order)}
    def began(r):
        t = r["t0"] if r["t0"] is not None else r["t_last"]
        return (t if t is not None else float("inf"), order.get(r["id"], 0))
    upto = began(focus)
    snap["runs"] = [r for r in snap["runs"] if r is focus or (
        began(r) <= upto and state.kind_of_log(Path(r["id"]).name) in PUBLISH)]
    for r in snap["runs"]:
        r["photo"] = r["model"] = None
    snap["reference"] = reference
    snap["note"] = note
    note = note or {}
    entry = {
        "id": rid_out, "file": "runs/%s.json" % rid_out, "kind": focus["kind"], "loco": focus["loco"],
        "road": focus["road"], "direction": focus["direction"], "route": focus["route"], "start": focus["t0"],
        "steps": [c["step"] for c in focus["curve"]], "pass_step": (focus["pass"] or {}).get("step"),
        "stop_step": stop["step"] if stop else None, "status": focus["status"], "reason": focus["reason"],
        "outcome": note.get("level"), "headline": note.get("headline"), "note": note.get("text")}
    return snap, entry


def encode(prev, cur):
    """diff_frame, checked: a change the compact form cannot carry goes whole."""
    d = diff_frame(prev, cur)
    if d and apply_frame(prev, d) != cur:
        d = dict(cur)
        d["-"] = [k for k in prev if k not in cur]
    return d


def frames_of(store, rid, lines, name, kind_hint=None):
    """Feed one run's lines into store and return its replay: [[t, view or diff], ...], the
    first a full view of the run and each later one only what changed (diff_frame). Each frame
    is what the live page showed of the run after that log line; lines that change nothing are
    left out. The last frame matches the run in runs/<id>.json."""
    frames, prev = [], None
    for i, ln in enumerate(lines):
        store.feed(rid, ln)
        p = state.parse_line(ln)
        if p is None or rid not in store.runs:
            continue
        snap = store.snapshot(now=p[0], reachable=True, message=None, mode="recorded", focus=rid)
        cur = next(r for r in snap["runs"] if r["id"] == rid)
        fix_focus(cur, store.runs[rid].kind, lines[: i + 1], name, now=p[0])
        if prev is None:
            frames.append([p[0], cur])
        else:
            d = encode(prev, cur)
            if not d:
                continue
            frames.append([p[0], d])
        prev = cur
    return frames


def export(logdir, out, labels):
    """Write this session's runs into out, keeping runs of other sessions already there. Built in
    a folder next to out and swapped in at the end, so a failure leaves out as it was."""
    notes, skip = load_labels(labels)
    state.warm_caches()
    logs = read_published(logdir, skip)
    unknown = [rid for rid, _ in logs if rid not in notes]
    if unknown:
        raise SystemExit("no label for: " + ", ".join(unknown))
    reference = sources.reference_curves()
    out = Path(out)
    tmp = out.with_name(out.name + ".new")
    if tmp.exists():
        shutil.rmtree(tmp)
    (tmp / "runs").mkdir(parents=True)
    mine = {rid[:-4] for rid, _ in logs} | {n[:-4] for n in skip}
    store = state.Store()
    index = []
    for rid, lines in logs:
        frames = frames_of(store, rid, lines, Path(rid).name)
        run = store.runs.get(rid)
        if run is None or not any(state.parse_line(ln) for ln in lines):
            shutil.rmtree(tmp)
            raise SystemExit("%s: no readable line, nothing to publish (label it in skip or fix the log)" % rid)
        level, headline, text = notes[rid]
        snap, entry = run_view(store, rid, lines, reference, {"level": level, "headline": headline, "text": text})
        (tmp / entry["file"]).write_text(json.dumps(snap, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
        if frames:
            final = frames[0][1]
            for _, d in frames[1:]:
                final = apply_frame(final, d)
            frames.append([run.t_end or run.t_last or frames[-1][0], encode(final, next(r for r in snap["runs"] if r["id"] == rid))])
            if not frames[-1][1]:
                frames.pop()  # the replay already ends where the record does
            entry["frames"] = "runs/%s.frames.json" % entry["id"]
            (tmp / entry["frames"]).write_text(json.dumps({"frames": frames}, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
        index.append(entry)
    old_index = out / "index.json"
    if old_index.exists():  # keep the runs of other sessions
        for r in json.loads(old_index.read_text(encoding="utf-8")).get("runs", []):
            f = out / r["file"]
            if r["id"] not in mine and f.exists():
                shutil.copy2(f, tmp / r["file"])
                if r.get("frames") and (out / r["frames"]).exists():
                    shutil.copy2(out / r["frames"], tmp / r["frames"])
                else:
                    r.pop("frames", None)
                index.append(r)
    index.sort(key=lambda r: (-(r["start"] or 0), r["id"]))
    (tmp / "index.json").write_text(json.dumps({"runs": index}, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    if out.exists():
        gone = out.with_name(out.name + ".old")
        if gone.exists():
            shutil.rmtree(gone)
        out.rename(gone)
        tmp.rename(out)
        shutil.rmtree(gone)
    else:
        tmp.rename(out)
    return index


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logdir", help="folder with the run logs, one session")
    ap.add_argument("--labels", required=True, help="the session's labels JSON (docs/jmri/speedmatching/profile-<date>/site_labels.json)")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="where the JSON goes (default www/data/speedmatch)")
    a = ap.parse_args(argv)
    print("%d runs published in %s" % (len(export(a.logdir, a.out, a.labels)), a.out))


if __name__ == "__main__":
    main()
