"""Where the dashboard's log lines come from: the Pi over ssh (read only), local replay, demo.

A source has poll() -> (reachable, message) and feeds a state.Store. Nothing here writes to
the Pi: the only remote commands are ls, stat and tail.
"""
from __future__ import annotations

import csv
import json
import os
import random
import shlex
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import TypedDict

import dashstate as state
import liverule as lr

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[5]
PATTERNS = ("steprun", "stoptest", "pass", "preflight")
MAX_FILES = 12
DEMO_STEPS = list(lr.DIST_STEPS)  # the distance-mode default
LOOP_FACTOR = 1.122  # the loop is 12% longer than the first lengths said
# The 2026-11-08 speeds by step, the one copy (written by analyze.py speed-by-step, speed_table.py)
REF_CSV = REPO / "jmri/layouts/hart/data/speed_by_step_2026-11-08.csv"

Fetch = Callable[[str], bytes]
LogSet = list[tuple[str, list[str]]]  # [(run id, lines)]


class RefPoint(TypedDict):
    """One point of a reference curve, as the dashboard client reads it."""
    step: int
    mm_s: float


def reference_curves() -> dict[str, list[RefPoint]]:
    """{'2121': [{step, mm_s}], ...} from the 2026-11-08 result, scaled to the corrected loop.

    The curves are an overlay only: without the CSV the dashboard runs with none, and says so
    on stderr."""
    out: dict[str, list[RefPoint]] = {}
    try:
        with open(REF_CSV, newline="") as fh:
            for r in csv.DictReader(fh):
                loco = r["loco"].split()[-1]
                out.setdefault(loco, []).append(
                    {"step": int(r["step"]), "mm_s": round(float(r["mean_mm_per_s"]) * LOOP_FACTOR, 1)})
    except OSError as e:
        print("dashsources: no reference curves (%s)" % e, file=sys.stderr)
    return out


# ---------------------------------------------------------------- the Pi over ssh

def ssh_fetcher(host: str | None = None, timeout: float = 12) -> Fetch:
    """Return fetch(cmd) -> bytes running cmd on the Pi (BatchMode, so never a prompt)."""
    host = host or os.environ.get("HART_PI_SSH", "pi")

    def fetch(cmd: str) -> bytes:
        p = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6", host, cmd],
                           capture_output=True, timeout=timeout)
        if p.returncode != 0:
            raise OSError((p.stderr or b"ssh failed").decode("utf-8", "replace").strip()[:200])
        return p.stdout

    return fetch


def list_cmd() -> str:
    pats = " ".join("/tmp/%s_*.log" % p for p in PATTERNS)
    return ("echo \"@@NOW $(date +%%s)\"; "
            "for f in $(ls -t %s 2>/dev/null | head -%d); do echo \"@@FILE $f $(stat -c %%s $f)\"; done; true"
            % (pats, MAX_FILES))


def tail_cmd(path: str, offset: int) -> str:
    return "tail -c +%d %s" % (offset + 1, shlex.quote(path))


def parse_listing(listing: str) -> tuple[float | None, list[tuple[str, int]]]:
    """(Pi epoch or None, [(path, size)] newest first) from the list_cmd() output."""
    now, files = None, []
    for ln in listing.splitlines():
        parts = ln.split()
        if len(parts) == 2 and parts[0] == "@@NOW" and parts[1].isdigit():
            now = float(parts[1])
        if len(parts) == 3 and parts[0] == "@@FILE" and parts[2].isdigit():
            files.append((parts[1], int(parts[2])))
    return now, files


class SshSource:
    mode = "live"

    def __init__(self, fetch: Fetch) -> None:
        self.fetch = fetch
        self.offsets: dict[str, int] = {}  # path -> bytes consumed
        self.carry: dict[str, bytes] = {}  # path -> partial last line
        self.listed: list[str] = []

    def poll(self, store: state.Store) -> tuple[bool, str | None]:
        try:
            now, files = parse_listing(self.fetch(list_cmd()).decode("utf-8", "replace"))
            if now is not None:
                store.pi_clock = (now, state.clock())
            self.listed = [p for p, _ in files]  # the newest MAX_FILES logs, as listed this poll
            for path, size in reversed(files):  # oldest first, so the newest run is last
                self._read_new(store, path, size)
            return True, None
        except (OSError, subprocess.SubprocessError) as e:
            return False, "Pi not reachable, retrying (%s)" % (str(e) or e.__class__.__name__)

    def _read_new(self, store: state.Store, path: str, size: int) -> None:
        """Feed the complete lines added to path since the last poll; keep a partial last line."""
        off = self.offsets.get(path, 0)
        if size < off:  # file replaced
            off = 0
            self.carry.pop(path, None)
            store.drop(path)
        store.ensure(path)
        if size == off:
            self.offsets.setdefault(path, off)
            return
        data = self.fetch(tail_cmd(path, off))
        self.offsets[path] = off + len(data)
        text = self.carry.pop(path, b"") + data
        body, nl, rest = text.rpartition(b"\n")
        if not nl:
            self.carry[path] = text
            return
        self.carry[path] = rest
        for ln in body.decode("utf-8", "replace").splitlines():
            store.feed(path, ln)


# ---------------------------------------------------------------- replay and demo

def replay_schedule(logs: Iterable[tuple[str, Sequence[str]]], rate: float = 20.0,
                    max_gap: float = 120.0) -> list[tuple[float, float, str, str]]:
    """logs: [(run id, [lines])]. Returns [(wall_due_seconds, ts, run id, line)] in time order.

    Lines of all logs are merged by their own timestamps (stable for equal times), then spaced
    at 1/rate of the gap between them, any single gap capped at max_gap so logs recorded days
    apart do not stall the replay."""
    items = []
    seq = 0
    for rid, lines in logs:
        for ln in lines:
            p = state.parse_line(ln)
            if p is None:
                continue
            items.append((p[0], seq, rid, ln))
            seq += 1
    items.sort(key=lambda x: (x[0], x[1]))
    out, due, prev = [], 0.0, None
    for ts, _, rid, ln in items:
        if prev is not None:
            due += min(ts - prev, max_gap) / rate
        prev = ts
        out.append((due, ts, rid, ln))
    return out


class ReplaySource:
    mode = "replay"

    def __init__(self, logs: Iterable[tuple[str, Sequence[str]]], rate: float = 20.0,
                 clock: Callable[[], float] = time.monotonic, max_gap: float = 120.0) -> None:
        self.items = replay_schedule(logs, rate, max_gap)
        self.clock = clock
        self.start: float | None = None
        self.i = 0
        self.now = self.items[0][1] if self.items else time.time()

    def poll(self, store: state.Store) -> tuple[bool, str | None]:
        if self.start is None:
            self.start = self.clock()
        el = self.clock() - self.start
        while self.i < len(self.items) and self.items[self.i][0] <= el:
            _, ts, rid, ln = self.items[self.i]
            store.feed(rid, ln)
            self.now = ts
            self.i += 1
        return True, None

    @property
    def finished(self) -> bool:
        return self.i >= len(self.items)


def read_logs(paths: Iterable[str | Path]) -> LogSet:
    out = []
    for p in paths:
        out.append((Path(p).name, Path(p).read_text(errors="replace").splitlines()))
    return out


def pass_sequence(names: Sequence[str], frm: str, to: str) -> list[str]:
    """The sensors a pass lights, in order: the path from `frm` to `to` (the shorter way round,
    modulo the ring) and then the sensor after `to`, whose lighting ends the pass."""
    return lr.path_between(names, frm, to) + [lr.next_after(names, frm, to)]


DEMO_LOCOS = ("2121", "2738")


class DemoError(RuntimeError):
    """The demo logs cannot be made (no reference speeds to run at)."""


DEMO_BIAS = {("2121", "forward"): 1.0, ("2121", "reverse"): 0.97,
             ("2738", "forward"): 1.0, ("2738", "reverse"): 1.04}


def _demo_blocks(route: str) -> list[state.Block]:
    """route_blocks() with a missing length as 150 mm, so the demo always has a whole loop."""
    bl = state.route_blocks(route)
    for b in bl:
        b["mm"] = float(b["mm"] if b["mm"] is not None else 150.0)
    return bl


class _Demo:
    """The shared clock, random source and reference speeds of one demo_logs() call."""

    def __init__(self, seed: int, t0: float) -> None:
        self.rng = random.Random(seed)
        self.ref = {k: {r["step"]: r["mm_s"] for r in v} for k, v in reference_curves().items()}
        missing = [loco for loco in DEMO_LOCOS if loco not in self.ref]
        if missing:
            raise DemoError("the demo needs reference speeds for %s from %s; none were read for them"
                            % (", ".join(missing), REF_CSV))
        self.t = t0
        self.lines: list[str] = []

    def new_log(self) -> list[str]:
        self.lines = []
        return self.lines

    def log(self, dt: float, msg: str) -> None:
        self.t += dt
        self.lines.append("%.3f %s" % (self.t, msg))


class _DistanceRun:
    """One distance-mode log on loop1: the loco laps the blocks at the reference speed."""

    def __init__(self, demo: _Demo, loco: str, direction: str, warm: bool) -> None:
        self.demo, self.loco, self.direction, self.warm = demo, loco, direction, warm
        self.base = _demo_blocks("loop1")
        self.blocks = self.base if direction == "forward" else list(reversed(self.base))
        self.n = len(self.blocks)
        self.lines = demo.new_log()
        self.k = 0  # index of the block the loco enters next
        self.v = 0.0  # mm/s now
        self.nxt = 0.0  # when the loco enters the next block
        self.spike: int | None = None  # the step whose blocks sometimes read 7% slow

    def vn(self, step: int) -> float:
        x = self.v * (1 + self.demo.rng.gauss(0, 0.012))
        if self.spike == step and self.demo.rng.random() < 0.25:
            x *= 0.93
        return x

    def enter(self, step: int) -> tuple[state.Block, float]:
        """The loco enters the next block: SENS line at its time; returns (block, time)."""
        d = self.demo
        b = self.blocks[self.k % self.n]
        d.t = self.nxt
        self.lines.append("%.3f SENS %s ACTIVE" % (d.t, b["sensor"]))
        self.nxt = d.t + b["mm"] / self.vn(step)
        self.k += 1
        return b, d.t

    def advance(self, until: float, step: int) -> None:
        while self.nxt <= until:
            self.enter(step)
        self.demo.t = max(self.demo.t, until)

    def set_speed(self, step: int) -> None:
        d = self.demo
        left = max(self.nxt - d.t, 0) * self.v
        self.v = d.ref[self.loco][step] * DEMO_BIAS[(self.loco, self.direction)]
        self.nxt = d.t + left / self.v

    def header(self) -> None:
        d = self.demo
        d.log(0, "RUN loco=%s direction=%s" % (self.loco, self.direction))
        d.log(0.1, "CFG route=loop1 mode=distance steps=%s target_mm=%g min_blocks=%d max_s=%g rel=%g warm_s=%g "
                   "warm_step=%d cv3=%d cv4=%d mid=BS_Switch_23a" % (
                       ",".join(map(str, DEMO_STEPS)), lr.DIST_TARGET_MM, lr.DIST_MIN_BLOCKS, lr.DIST_MAX_S,
                       lr.DIST_REL, lr.DIST_WARM_S if self.warm else 0, lr.DIST_WARM_STEP, lr.DIST_CV3,
                       lr.DIST_CV4))
        d.log(0.1, "LENGTHS " + json.dumps({b["sensor"]: b["mm"] for b in self.base}))
        d.t += 1.0
        self.k = d.rng.randrange(self.n)
        self.v = d.ref[self.loco][DEMO_STEPS[0]]
        self.nxt = d.t + 20.0

    def measure(self, step: int) -> tuple[lr.DistanceStep, str]:
        """Blocks until the runner's end rule says done; logs BLOCK, EXTRA and FREEZE lines.
        Returns the step's readings and its end reason."""
        d = self.demo
        b0, mstart = self.enter(step)
        d.log(0, "MEASURE %d from=%s" % (step, b0["sensor"]))
        cur = (b0, mstart)
        ds = lr.DistanceStep(lr.DIST_TARGET_MM, lr.DIST_MIN_BLOCKS, lr.DIST_MAX_S, lr.DIST_REL)
        reason = ""
        while True:
            if self.nxt - mstart >= lr.DIST_MAX_S:
                d.t = mstart + lr.DIST_MAX_S
                _, reason = ds.check(lr.DIST_MAX_S)  # the runner's own time-out: timed or max
                break
            b2, t2 = self.enter(step)
            dt = t2 - cur[1]
            self.lines.append("%.3f BLOCK %d block=%s mm=%d dt=%.2f mm_s=%.1f" % (
                t2, step, cur[0]["sensor"].replace(" ", "_"), round(cur[0]["mm"]), dt, cur[0]["mm"] / dt))
            ds.add(cur[0]["mm"], dt)
            cur = (b2, t2)
            done, why = ds.check(t2 - mstart)
            if ds.extra_new:
                ds.extra_new = False
                d.log(0.1, "EXTRA %d relsd=%.4f" % (step, ds.relsd))
            if done:
                reason = why
                d.t = t2 + 0.1
                break
        d.log(0.0, "FREEZE %d" % step)
        return ds, reason

    def run(self) -> list[str]:
        d = self.demo
        self.header()
        prev = 0
        if self.warm:
            self.set_speed(lr.DIST_WARM_STEP)
            d.log(0, "WARMUP %d secs=%g" % (lr.DIST_WARM_STEP, lr.DIST_WARM_S))
            self.advance(d.t + lr.DIST_WARM_S, lr.DIST_WARM_STEP)
            d.log(0, "WARMUP_DONE")
            prev = lr.DIST_WARM_STEP
        for step in DEMO_STEPS:
            secs = lr.settle_time(lr.DIST_CV3, lr.DIST_CV4, prev, step)
            self.spike = 64 if (self.loco, self.direction) == ("2738", "reverse") else None
            d.log(0.05, "STEP %d" % step)
            self.set_speed(step)
            d.log(0.01, "SETTLE %d secs=%.1f" % (step, secs))
            self.advance(d.t + secs, step)
            ds, reason = self.measure(step)
            cnt, mm, secs_m, speed, rsd = lr.aggregate(ds.blocks)
            d.log(0.0, "STEPDONE %d reason=%s n=%d mm=%.1f s=%.2f mm_s=%.1f relsd=%.4f" % (
                step, reason, cnt, mm, secs_m, speed, rsd))
            prev = step
        d.log(0.5, "speed 0")
        d.log(0.1, "STOP all steps complete")
        d.log(0.1, "END")
        return self.lines


def _demo_pass(demo: _Demo, step: int) -> list[str]:
    """One Switch 13 pass on loop2: Switch 5 to Switch 15, the loco stops once the sensor after lights."""
    names = [b["sensor"] for b in _demo_blocks("loop2")]
    mm = {b["sensor"]: b["mm"] for b in _demo_blocks("loop2")}
    seq = pass_sequence(names, "BS Switch 5", "BS Switch 15")
    lines = demo.new_log()
    v = demo.ref["2121"][step]
    demo.log(0, "RUN loco=2121 direction=forward")
    demo.log(0.1, "CFG route=loop2 mode=pass step=%d max_s=300" % step)
    demo.log(0.5, "PATH " + ",".join(seq[:-1]))
    demo.log(0.5, "PASS step=%d from=BS Switch 5 to=BS Switch 15" % step)
    demo.log(8.0, "SENS %s ACTIVE" % seq[0])
    for prev, sensor in zip(seq, seq[1:]):
        demo.log(mm[prev] / (v * (1 + demo.rng.gauss(0, 0.01))), "SENS %s ACTIVE" % sensor)
    demo.log(0.2, "PASSDONE reason=passed")
    demo.log(0.1, "speed 0")
    demo.log(0.1, "STOP passed")
    demo.log(0.1, "END")
    return lines


def demo_logs(seed: int = 7, t0: float = 1794300000.0) -> LogSet:
    """Synthetic logs in the shape the distance-mode runner writes, in time order: CSX 2121 and
    CSX 2738 both directions on loop1 (the 60 s warm-up only before a loco's first run), then
    two Switch 13 passes on loop2. Block lengths from block_lengths.csv; speeds are the
    2026-11-08 result x1.122, with a little noise. The end rule is the runner's own
    (liverule.DistanceStep), so slow steps end as "max" and show as not valid."""
    demo = _Demo(seed, t0)
    logs: LogSet = []
    for loco in DEMO_LOCOS:
        warm = True
        for direction in ("forward", "reverse"):
            lines = _DistanceRun(demo, loco, direction, warm).run()
            logs.append(("steprun_CSX_%s_%s_demo.log" % (loco, direction), lines))
            demo.t += 30
            warm = False
    for step in (24, 48):
        logs.append(("pass_CSX_2121_forward_step%d_demo.log" % step, _demo_pass(demo, step)))
        demo.t += 20
    return logs
