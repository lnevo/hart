#!/usr/bin/env python3
"""Speed profile analysis for the step runner logs (jython/step_runner.py).

Reads one or more runner logs and writes, per (loco, direction) and step, the speed over
known block lengths: a rolling median and relative standard deviation, found by replaying
the same stop rule the runner used live (liverule.py). Warm-up laps are discarded. It also
compares the two locos in the consist pairing (first loco forward against the second in
reverse, and the other way round), and reports the drift of the repeated top step.

    analyze.py LOG [LOG ...] [--route loop1|loop2] [--events-out CSV] [--lengths CSV] [--trusted timed] [--out DIR]
               [--pair "CSX 2121,CSX 2738"]

Lengths come from jmri/layouts/hart/data/block_lengths.csv (the AnyRail plan 5.3c length, inches) and
block_lengths_measured.csv beside it (the lengths speed matching measured): a block's operating length is its
measured one where it has a row there (source `timed`), else its plan length (source `plan`). Only trusted
sources are used: --trusted defaults to timed; a plan length counts only if you pass plan.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import liverule as lr  # noqa: E402

DEFAULT_LENGTHS = HERE.parents[1] / "data" / "block_lengths.csv"
DEFAULT_TRUSTED = ("timed",)  # "plan" counts only when passed explicitly
MM_PER_INCH = 25.4

# The test routes: the staging blocks in running order, each by its device ID (devices_generated.csv's id column,
# hartlib.device_ids), so a rename in devices_field.csv changes no line here. Only the order is
# typed here. build_routes.py (--check in tools/check.sh) gives each block its name from the name store
# (hartlib.devices.user_names) and its sensor from tables.xml, and writes both into routes.json, so this file needs
# neither hartlib nor tables.xml: the Pi's speed-match live publisher imports it. An ID the device master no longer
# has stops build_routes.py. loop1 is the 2026-11-08 loop, east from East Ext (block:5B-7A); loop2 runs through
# Scale, Barn and Track S-R and starts at Switch 5. A job, its log (the CFG line) and the analysis all name the route.
ROUTE_BLOCKS = {
    "loop1": [
        "block:5B-7A", "os:7:A-5B", "block:7B-33C", "os:33", "block:33A-35A",
        "os:35:A-33A", "os:37", "block:37C-39C#1", "block:37C-39C#2", "os:39", "os:35:A-39A",
        "block:23B-35B", "os:23:A-1A", "block:1A-23A", "os:1", "block:1C-5A#1+1C-5A#2",
        "os:5",
    ],
    "loop2": [
        "os:5", "block:5C-7B", "os:7:A-13C", "block:7A-13C", "os:13", "os:15",
        "block:15B-23B", "os:23:A-31B", "os:31", "os:33", "block:33A-35A",
        "os:35:A-33A", "os:37", "block:37C-39C#1", "block:37C-39C#2", "os:39", "os:35:A-39A",
        "block:23B-35B", "os:23:A-1A", "block:1A-23A", "os:1", "block:1C-5A#1+1C-5A#2",
    ],
}
# The warm-up lap counter counts REF (the route's first sensor) lit again after MID, the sensor
# of a block about half way round the route (OS Switch 23a on loop1, Track K-2 on loop2), by its ID.
ROUTE_MID_BLOCK = {"loop1": "os:23:A-1A", "loop2": "block:37C-39C#1"}


ROUTES_JSON = HERE / "routes.json"


def load_routes(path=ROUTES_JSON, order=ROUTE_BLOCKS, mid=ROUTE_MID_BLOCK):
    """(ROUTES, ROUTE_MID) from routes.json: {route: [(block sensor, block name)]}, {route: sensor}.

    Stops when the file's block IDs (its `ids`, one per pair) or mid blocks are not the ones typed here (rebuild
    it)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit("cannot read %s (%s); run speedmatch/build_routes.py" % (path, e))
    routes = {r: [tuple(pair) for pair in pairs] for r, pairs in data["routes"].items()}
    ids = data.get("ids", {})
    stale = sorted(r for r in set(order) | set(routes)
                   if list(ids.get(r, [])) != list(order.get(r, []))
                   or len(routes.get(r, [])) != len(order.get(r, [])))
    by_block = {r: dict(zip(ids[r], (s for s, _ in pairs))) for r, pairs in routes.items() if r not in stale}
    stale += sorted(r for r, b in mid.items()
                    if r not in stale and data["mid"].get(r) != by_block.get(r, {}).get(b))
    if stale:
        raise SystemExit("%s does not match ROUTE_BLOCKS / ROUTE_MID_BLOCK for %s; run "
                         "speedmatch/build_routes.py" % (path, ", ".join(stale)))
    return routes, dict(data["mid"])


def block_ids(path=ROUTES_JSON):
    """{block name: block ID} of every block on the routes (routes.json's pairs and their `ids`)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {name: ident for r, pairs in data["routes"].items()
            for (_sensor, name), ident in zip(pairs, data.get("ids", {}).get(r, []))}


ROUTES, ROUTE_MID = load_routes()
BLOCK_IDS = block_ids()
LOOP, LOOP2 = ROUTES["loop1"], ROUTES["loop2"]
DEFAULT_ROUTE = "loop1"
ORDER = [s for s, _ in LOOP]  # loop1 aliases: LOOP and ORDER

# Switch positions the owner sets by hand before a run (nothing here is ever sent to JMRI):
# (switch number, "closed" or "thrown"), checked against the legs of data/switches.csv by the tests.
ROUTE_LINEUP = {
    "loop1": [(5, "closed"), (7, "closed"), (33, "thrown"), (35, "closed"), (37, "thrown"),
              (39, "thrown"), (23, "closed"), (1, "thrown")],
    "loop2": [(5, "thrown"), (7, "closed"), (13, "closed"), (15, "closed"), (23, "closed"),
              (31, "closed"), (33, "closed"), (35, "closed"), (37, "thrown"), (39, "thrown"),
              (1, "thrown")],
}


def route_loop(route):
    """The (sensor, csv row) list of a route; SystemExit-friendly ValueError for an unknown one."""
    if route not in ROUTES:
        raise ValueError("unknown route %r: give one of %s" % (route, ", ".join(sorted(ROUTES))))
    return ROUTES[route]


def route_mid(route):
    mid = ROUTE_MID[route]
    assert mid in route_order(route), (route, mid)
    return mid


def route_order(route):
    return [s for s, _ in route_loop(route)]


def measured_path(path):
    """The measured file beside a plan file: block_lengths.csv -> block_lengths_measured.csv
    (hartlib.block_lengths.measured_path)."""
    path = Path(path)
    return path.with_name(path.stem + "_measured.csv")


def _id_rows(path, need):
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        missing = set(need) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: no column {', '.join(sorted(missing))}")
        return {r["id"]: r for r in reader}


def load_lengths(path=DEFAULT_LENGTHS, trusted=DEFAULT_TRUSTED, loop=LOOP, measured=None):
    """dict sensor -> length in mm, None where the block has no row or its source is not trusted.

    The operating length (hartlib.block_lengths.operating_lengths): a block with a row in the measured file
    (`measured`, default the one beside `path`) has source `timed` and its measured_in, any other its plan_in from
    `path` and source `plan`. Stops on a file without the id and length columns. A block is found by its ID, which
    routes.json gives each block of the loop (BLOCK_IDS). Read here with the standard library, not through hartlib:
    the Pi's live publisher runs this with copies of both files and no hartlib (tools/hosts/deploy/stage.sh), so
    tools/audit/check_data_readers.py lists this script by name; tools/hartlib/tests/test_block_lengths.py holds its
    answer to hartlib's."""
    plan = _id_rows(path, ("id", "plan_in"))
    timed = _id_rows(measured or measured_path(path), ("id", "measured_in"))
    out = {}
    for sensor, name in loop:
        ident = BLOCK_IDS.get(name)
        source = "timed" if ident in timed else "plan" if ident in plan else None
        if source is None or source not in trusted:
            out[sensor] = None
            continue
        row = timed[ident] if source == "timed" else plan[ident]
        out[sensor] = float(row["measured_in" if source == "timed" else "plan_in"]) * MM_PER_INCH
    return out


_LINE = re.compile(r"^([\d.]+) (.*)$")
_RUN = re.compile(r"RUN loco=(.*) direction=(\w+)")
_CFG = re.compile(r"(\w+)=([^\s@]+)")
STATES = ("ACTIVE", "INACTIVE", "UNKNOWN", "INCONSISTENT")
# CFG names the runner logs -> the keyword names used here
CFG_KEYS = {"k": ("k", int), "rel": ("rel", float), "max": ("max_n", int),
            "settle": ("settle", int), "route": ("route", str), "low_max": ("low_max", int), "high_span": ("high_span", int),
            # distance mode (jython/distance_runner.py)
            "mode": ("mode", str), "target_mm": ("target_mm", float), "min_blocks": ("min_blocks", int),
            "max_s": ("max_s", float)}


def check_names(lines, source=""):
    """Stop on a log that still uses the extension-track names from before 2026-11-13: its East and
    West extension blocks would not match and the laps would come out short or missing."""
    import re
    old = re.compile(r"(East|West)[ _-]Main[ _-]Ext", re.I)
    if any(old.search(line) for line in lines):
        raise SystemExit("%s uses the old names East/West Main Ext; convert it first with "
                         "speedmatch/rename_extension_tracks.py --apply" % (source or "a log"))


Event = tuple[float, str]  # (epoch, sensor) a sensor went ACTIVE


class _LogParser:
    """The state of parse_log() while it reads one log: the runs so far, the current run and step,
    and every sensor's last state. One method per message kind (HANDLERS)."""

    def __init__(self, loco: str | None, direction: str | None, source: str) -> None:
        self.loco, self.direction, self.source = loco, direction, source
        self.runs: list[dict] = []
        self.run: dict | None = None
        self.cur: dict | None = None  # the current step
        self.seen: dict[int, int] = {}  # step -> times seen in this run
        self.active: dict[str, str] = {}  # sensor -> last state
        self.sensed: dict[int, set[str]] = {}  # id(run) -> sensor names the run logged, for check_route_sensors
        self.last_active: Event | None = None

    def new_run(self, loco: str, direction: str, t: float) -> dict:
        run: dict = {"loco": loco, "direction": direction, "steps": [], "cfg": {},
               "lengths": None, "log": self.source, "complete": False, "t0": t}
        self.runs.append(run)
        return run

    def on_run(self, t: float, msg: str) -> None:
        mm = _RUN.match(msg)
        if not mm:
            return
        self.run = self.new_run(mm.group(1), mm.group(2), t)
        self.seen.clear()
        self.active.clear()
        self.cur = None

    def on_step(self, t: float, msg: str) -> None:
        if self.run is None:
            if self.loco is None or self.direction is None:
                raise ValueError("log has no RUN line: give loco and direction")
            self.run = self.new_run(self.loco, self.direction, t)
        n = int(msg.split()[1])
        self.seen[n] = self.seen.get(n, 0) + 1
        self.cur = {"step": n, "occurrence": self.seen[n], "events": []}
        if self.run["cfg"].get("mode") == "distance":
            self.cur["measuring"] = False  # events count from this step's MEASURE line to its FREEZE
        self.run["steps"].append(self.cur)

    def on_cfg(self, t: float, msg: str) -> None:
        run = self.run
        if run is None:
            return
        for key, val in _CFG.findall(msg[4:]):
            if key in CFG_KEYS:
                name, conv = CFG_KEYS[key]
                run["cfg"][name] = conv(val)
        if run["cfg"].get("mode") == "pass":  # a pass-job log has no steps: not a run
            print("note: %s is a pass-job log (mode=pass), skipped here; use infer_block_lengths.py "
                  "--pass-log" % (self.source or "log"), file=sys.stderr)
            self.runs.remove(run)
            self.run = self.cur = None

    def on_lengths(self, t: float, msg: str) -> None:
        if self.run is not None:
            self.run["lengths"] = json.loads(msg[8:])

    def on_stop(self, t: float, msg: str) -> None:
        if self.run is not None:
            self.run["complete"] = msg.strip() == "STOP all steps complete"

    def on_warmup(self, t: float, msg: str) -> None:
        self.cur = None

    def on_freeze(self, t: float, msg: str) -> None:
        if self.cur is not None and "measuring" in self.cur:  # distance mode: the runner took no block after this line
            self.cur["measuring"] = False

    def on_stepdone(self, t: float, msg: str) -> None:
        if self.cur is None:
            return
        m = re.match(r"STEPDONE \d+ reason=(\w*)", msg)
        self.cur["done_reason"] = m.group(1) if m else ""
        if "measuring" in self.cur:  # distance mode: later events belong to the next step
            self.cur["measuring"] = False

    def on_settle(self, t: float, msg: str) -> None:
        if self.cur is not None:
            self.cur["measuring"] = False  # distance mode: events count only from MEASURE on

    def on_measure(self, t: float, msg: str) -> None:
        if self.cur is None or self.last_active is None:
            return
        # the runner logs the SENS line of the event first, then MEASURE for it
        m = re.match(r"MEASURE \d+ from=(.*)$", msg)
        self.cur["measuring"] = True
        if m and self.last_active[1] == m.group(1):
            self.cur["events"].append(self.last_active)

    def on_sens(self, t: float, msg: str) -> None:
        name, st = msg[5:].rsplit(" ", 1)
        if self.run is not None:
            self.sensed.setdefault(id(self.run), set()).add(name)
        if st == "ACTIVE" and self.active.get(name) != "ACTIVE":
            self.last_active = (t, name)
            if self.cur is not None and self.cur.get("measuring", True):
                self.cur["events"].append((t, name))
        if st in STATES:  # any state counts: UNKNOWN between two ACTIVEs is a new ACTIVE
            self.active[name] = st

    # the message prefix each handler takes, checked in this order
    HANDLERS = (("RUN ", on_run), ("STEP ", on_step), ("CFG ", on_cfg), ("LENGTHS ", on_lengths),
                ("STOP ", on_stop), ("WARMUP ", on_warmup), ("FREEZE ", on_freeze),
                ("STEPDONE ", on_stepdone), ("SETTLE ", on_settle), ("MEASURE ", on_measure),
                ("SENS ", on_sens))

    def line(self, line: str) -> None:
        m = _LINE.match(line.strip())
        if not m:
            return
        t, msg = float(m.group(1)), m.group(2)
        for prefix, handler in self.HANDLERS:
            if msg.startswith(prefix):
                handler(self, t, msg)
                return


def parse_log(lines: Sequence[str], loco: str | None = None, direction: str | None = None,
              source: str = "") -> list[dict]:
    """Split runner log lines into runs: list of dicts
    {loco, direction, log, complete, cfg, lengths, steps: [{step, occurrence, events}]}.
    Every RUN line starts a new run (the same loco and direction twice stay two runs);
    complete is True when the runner logged "STOP all steps complete".

    Warm-up events (between WARMUP and the first STEP) are dropped. A log without a RUN
    line (older logs) needs loco and direction given."""
    check_names(lines, source)
    parser = _LogParser(loco, direction, source)
    for line in lines:
        parser.line(line)
    for run in parser.runs:
        check_route_sensors(parser.sensed.get(id(run), ()), run["cfg"].get("route", DEFAULT_ROUTE), source)
    return parser.runs


def check_route_sensors(names, route, source=""):
    """Stop on a sensor the route does not have: a log recorded before a block or sensor rename
    (its blocks would not match and laps would come out short), or a log of another route."""
    if route not in ROUTES:
        return  # route_loop() names the unknown route when the run is analysed
    known = {s for s, _ in ROUTES[route]}
    stray = sorted(set(names) - known)
    if stray:
        raise SystemExit("%s logs sensor(s) not on route %s: %s. If a block or sensor was renamed, "
                         "convert the log first (as speedmatch/rename_extension_tracks.py did for the "
                         "2026-11-13 rename)" % (source or "a log", route, ", ".join(stray)))


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


_PASS = re.compile(r"PASS step=(\d+) from=(.*) to=(.*)$")


def parse_pass_log(lines, source=""):
    """The passes in a pass-job log (jython/pass_runner.py): list of dicts {loco, direction,
    step, frm, to, path (the PATH line before PASS: sensors expected from frm to to, [] in older
    logs), events [(epoch, sensor)] of every ACTIVE after the PASS line, reason (from PASSDONE,
    '' if the log has none), log}. Every PASS line starts a pass."""
    check_names(lines, source)
    passes, loco, direction, cur, active, path = [], "", "", None, {}, []
    for line in lines:
        m = _LINE.match(line.strip())
        if not m:
            continue
        t, msg = float(m.group(1)), m.group(2)
        if msg.startswith("RUN "):
            mm = _RUN.match(msg)
            if mm:
                loco, direction = mm.group(1), mm.group(2)
            active.clear()
            path = []
        elif msg.startswith("PATH "):
            path = msg[5:].strip().split(",")
        elif msg.startswith("PASS "):
            mm = _PASS.match(msg)
            if mm:
                cur = {"loco": loco, "direction": direction, "step": int(mm.group(1)),
                       "frm": mm.group(2), "to": mm.group(3), "path": path, "events": [], "reason": "",
                       "log": source}
                passes.append(cur)
        elif msg.startswith("PASSDONE ") and cur is not None:
            cur["reason"] = msg.split("reason=", 1)[-1].strip()
            cur = None
        elif msg.startswith("SENS "):
            name, st = msg[5:].rsplit(" ", 1)
            if cur is not None and st == "ACTIVE" and active.get(name) != "ACTIVE":
                cur["events"].append((t, name))
            if st in STATES:
                active[name] = st
    return passes


def replay_distance(events, order, lengths, target_mm, min_blocks, max_s, rel):
    """Distance mode, replayed as the runner took it: events are the ACTIVE events from the
    MEASURE one on. Returns (blocks [(sensor, mm, s)], reason, relsd, extra); reason is
    'settled', 'timed', 'max' or '' (the data ended first)."""
    reader = lr.SpanReader(order, lengths, 0, True)
    reader.restart(1)
    step = lr.DistanceStep(target_mm, min_blocks, max_s, rel)
    blocks, t0 = [], None
    for t, sensor in events:
        if t0 is None:
            t0 = t
        done, why = step.check(t - t0)  # the clock may run out between two events
        if done and why in ("max", "timed"):
            return blocks, why, step.relsd, step.extra
        b = reader.feed(t, sensor)
        if b is not None:
            blocks.append((b[4], b[2], b[1]))  # (sensor, mm, seconds), as the BLOCK line has them
            step.add(b[2], b[1])
            done, why = step.check(t - t0)
            if done:
                return blocks, why, step.relsd, step.extra
    return blocks, "", step.relsd, step.extra


def travel(events, order=ORDER):
    """'east' (the order of LOOP) or 'west', from the order the sensors lit; '' if unclear."""
    up = down = 0
    for (_, a), (_, b) in zip(events, events[1:]):
        if a in order and b in order:
            d = (order.index(b) - order.index(a)) % len(order)
            up += d == 1
            down += d == len(order) - 1
    return "east" if up > down else "west" if down > up else ""


def _window_row(run: dict, s: dict, n: int, order: Sequence[str], lengths: Mapping[str, float | None],
                rule: tuple[int, float, int], reader_kw: Mapping[str, int]) -> dict:
    """One step of a time-window run: the readings replayed through the runner's stop rule."""
    k_, rel_, max_ = rule
    rd = step_readings(s["events"], s["step"], lengths, order=order, **reader_kw)
    speeds = [r[0] for r in rd]
    row = {"loco": run["loco"], "direction": run["direction"], "step": s["step"],
           "occurrence": s["occurrence"], "travel": travel(s["events"], order),
           "n": len(speeds), "blocks": rd[-1][3] if rd else 0, "run": n}
    if speeds:
        used, why, win = lr.replay(speeds, k_, rel_, max_)
        row.update(used=used, reason=why or "open", median=lr.median(win),
                   rel_sd=lr.rel_stdev(win) if len(win) > 1 else None,
                   settled=(why == "settled"))
    else:
        row.update(used=0, reason="no readings", median=None, rel_sd=None,
                   settled=False)
    return row


def _run_rows(run: dict, n: int, order: Sequence[str], lengths: Mapping[str, float | None], p: dict,
              use_logged: bool) -> list[dict]:
    """The rows of one run; p is the stop-rule settings with route already taken out."""
    k_, rel_, max_ = p.pop("k"), p.pop("rel"), p.pop("max_n")
    logged = {name: p.pop(name, None) for name in ("mode", "target_mm", "min_blocks", "max_s")}
    if (run.get("cfg") or {}).get("mode") == "distance":  # the log's own mode, whatever use_logged says
        dist = logged if use_logged else {"target_mm": None, "min_blocks": None, "max_s": None}
        rel_d = rel_ if use_logged else lr.DIST_REL
        return [distance_row(run, s, n, order, lengths, dist, rel_d) for s in run["steps"]]
    return [_window_row(run, s, n, order, lengths, (k_, rel_, max_), p) for s in run["steps"]]


def summarize_runs(runs: Iterable[dict], lengths: Mapping[str, float | None], k: int = lr.STOP_K,
                   rel: float = lr.STOP_REL, max_n: int = lr.MAX_READINGS, use_logged: bool = True,
                   csv_lengths: bool = False, route_lengths: Mapping[str, Mapping[str, float | None]] | None = None,
                   **kw: object) -> list[dict]:
    """One entry per run, oldest first by the time in the log (the RUN line, else the first
    STEP line; equal or missing times keep input order), so the highest run number is the
    latest run whatever order the logs were given in: {run, loco, direction, log, complete, rows}.

    A run's own CFG line (stop rule settings) and LENGTHS line (the lengths the job was built
    with) are replayed as the runner had them; the arguments are used only for logs that lack
    them. use_logged=False ignores both; csv_lengths=True swaps only the lengths for the ones
    given (the logged stop-rule settings still apply). Each run is replayed over the route its
    CFG line names (loop1 for logs that do not); route_lengths (route -> lengths) gives
    csv_lengths a set per route."""
    out = []
    runs = sorted(runs, key=lambda r: r.get("t0") or 0.0)  # stable
    for n, run in enumerate(runs, start=1):
        p: dict[str, object] = {"k": k, "rel": rel, "max_n": max_n}
        p.update(kw)
        if use_logged:
            p.update(run.get("cfg") or {})
        route = str(p.pop("route", DEFAULT_ROUTE))
        try:
            order = route_order(route)
        except ValueError as e:
            print("warning: run of %s %s in %s skipped: %s" % (
                run["loco"], run["direction"], run.get("log") or "log", e), file=sys.stderr)
            continue
        run_lengths = (route_lengths or {}).get(route, lengths)
        if use_logged and not csv_lengths:
            run_lengths = run.get("lengths") or run_lengths
        out.append({"run": n, "loco": run["loco"], "direction": run["direction"], "route": route,
                    "log": run.get("log", ""), "complete": bool(run.get("complete")),
                    "rows": _run_rows(run, n, order, run_lengths, p, use_logged)})
    return out


def distance_row(run, s, n, order, lengths, cfg, rel):
    """One profile row for a distance-mode step: speed = sum(mm) / sum(s) over the whole blocks."""
    blocks, why, relsd, _ = replay_distance(
        s["events"], order, lengths, cfg["target_mm"] or lr.DIST_TARGET_MM,
        cfg["min_blocks"] or lr.DIST_MIN_BLOCKS, cfg["max_s"] or lr.DIST_MAX_S, rel)
    cnt, mm, secs, v, rsd = lr.aggregate([(b[1], b[2]) for b in blocks])
    reason = why or s.get("done_reason") or ("open" if s["events"] else "no readings")
    return {"loco": run["loco"], "direction": run["direction"], "step": s["step"],
            "occurrence": s["occurrence"], "travel": travel(s["events"], order),
            "n": cnt, "blocks": 1, "run": n, "used": cnt,
            "reason": reason,
            "median": v if cnt else None, "rel_sd": rsd if cnt > 1 else None,
            "settled": lr.is_valid_reason(reason) and cnt > 0}


EVENT_FIELDS = ["loco", "log", "step", "lap_index", "block", "block_len_mm", "entry_epoch",
                "next_entry_epoch", "transit_s", "mm_per_s"]


def block_events(runs, route=DEFAULT_ROUTE):
    """Rows in the shape of docs/jmri/speedmatching/profile-2026-11-08/block_events.csv, for
    infer_block_lengths.py. A block's transit is the time from its sensor lighting to the next
    sensor of the route lighting (the next one in the direction the loco ran, found from the
    order the sensors lit). A lap is one pass of the route's sensors, counted from its first
    sensor; per step, the run's own logged settle count of events after the step change and
    everything before the first sensor are dropped, and a block whose next sensor is not the
    expected one (a missed or doubled event) gets no row. A run's own CFG route wins over the
    route argument; a run with no rows is reported on stderr."""
    rows = []
    for run in runs:
        cfg = run.get("cfg") or {}
        try:
            order = route_order(cfg.get("route", route))
        except ValueError as e:
            print("warning: events of a run in %s skipped: %s" % (run.get("log") or "log", e), file=sys.stderr)
            continue
        settle = 0 if cfg.get("mode") == "distance" else cfg.get("settle", lr.SETTLE_EVENTS)
        first = order[0]
        before = len(rows)
        for s in run["steps"]:
            ev = [(t, n) for t, n in s["events"][settle:] if n in order]
            step = 1 if travel(ev, order) != "west" else -1
            lap, started = -1, False
            for (t, n), (t2, n2) in zip(ev, ev[1:]):
                if n == first:
                    lap += 1
                    started = True
                if not started:
                    continue
                if n2 != order[(order.index(n) + step) % len(order)]:
                    continue
                dt = t2 - t
                mm = (run.get("lengths") or {}).get(n)
                rows.append({"loco": run["loco"], "log": run.get("log", ""), "step": s["step"],
                             "lap_index": lap, "block": n[3:], "block_len_mm": "" if mm is None else round(mm, 1),
                             "entry_epoch": "%.3f" % t, "next_entry_epoch": "%.3f" % t2,
                             "transit_s": round(dt, 2),
                             "mm_per_s": "" if mm is None or dt <= 0 else round(mm / dt, 1)})
        if len(rows) == before:
            print("warning: no block events from the run of %s %s in %s (no complete pass of %s)" % (
                run["loco"], run["direction"], run.get("log") or "log", order[0]), file=sys.stderr)
    return rows


def write_events(rows, path):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=EVENT_FIELDS)
        w.writeheader()
        w.writerows(rows)


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
                    "run", "run_complete", "log", "route"])
        for sm in summaries:
            for r in sm["rows"]:
                w.writerow([r["loco"], r["direction"], step_label(r), r["travel"], r["blocks"],
                            r["n"], r["used"], fmt(r["median"]),
                            fmt(None if r["rel_sd"] is None else 100 * r["rel_sd"], 2),
                            r["settled"], r["reason"], sm["run"], sm["complete"], sm["log"],
                            sm.get("route", DEFAULT_ROUTE)])
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
    ap.add_argument("--lengths", default=str(DEFAULT_LENGTHS),
                    help="the plan lengths file; its measured file is read beside it (measured_path)")
    ap.add_argument("--trusted", default=",".join(DEFAULT_TRUSTED),
                    help="length sources that count as trusted (timed: block_lengths_measured.csv, plan: "
                         "block_lengths.csv); default timed, add plan only on purpose")
    ap.add_argument("--out", default=".")
    ap.add_argument("--pair", default="CSX 2121,CSX 2738",
                    help="the consist pair: leader,follower (follower runs reversed)")
    ap.add_argument("--loco", help="for logs without a RUN line")
    ap.add_argument("--direction", help="for logs without a RUN line")
    ap.add_argument("--route", default=DEFAULT_ROUTE, choices=sorted(ROUTES),
                    help="route for logs whose CFG line does not name one (a logged route wins)")
    ap.add_argument("--events-out", help="also write block_events-style rows (for infer_block_lengths.py "
                    "--events) to this CSV")
    ap.add_argument("--csv-lengths", action="store_true",
                    help="use the lengths from --lengths, not the ones logged by the runner (the logged\n                         stop-rule settings still apply)")
    ap.add_argument("--k", type=int, default=lr.STOP_K)
    ap.add_argument("--rel", type=float, default=lr.STOP_REL)
    ap.add_argument("--max", type=int, default=lr.MAX_READINGS, dest="max_n")
    a = ap.parse_args(argv)
    trusted = tuple(a.trusted.split(","))
    route_lengths = {r: load_lengths(a.lengths, trusted, loop) for r, loop in ROUTES.items()}
    lengths = route_lengths[a.route]
    n_ok = sum(v is not None for v in lengths.values())
    print("trusted block lengths: %d of %d %s blocks" % (n_ok, len(lengths), a.route))
    runs = []
    for p in a.logs:
        runs += parse_log(Path(p).read_text().splitlines(), a.loco, a.direction, Path(p).name)
    summaries = summarize_runs(runs, lengths, a.k, a.rel, a.max_n, csv_lengths=a.csv_lengths,
                               route_lengths=route_lengths, route=a.route)
    result = latest_runs(summaries)
    pair = tuple(a.pair.split(",")) if a.pair else None
    write_outputs(result, pair, a.out, summaries)
    if a.events_out:
        rows = block_events(runs, a.route)
        write_events(rows, a.events_out)
        print("wrote %d block events to %s" % (len(rows), a.events_out))
    for key, rows in sorted(result.items()):
        d = top_drift(rows)
        print("%s %s: %d steps%s" % (key[0], key[1], len(rows),
              "" if not d else ", step %d drift %+.1f%%" % (d["step"], d["drift_pct"])))
    print("wrote profile.csv, drift.csv%s in %s" % (", compare.csv" if pair else "", a.out))


if __name__ == "__main__":
    main()
