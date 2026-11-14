"""Where the dashboard's log lines come from: the Pi over ssh (read only), local replay, demo.

A source has poll() -> (reachable, message) and feeds a state.Store. Nothing here writes to
the Pi: the only remote commands are ls, stat and tail.
"""
from __future__ import annotations

import csv
import os
import random
import shlex
import subprocess
import time
from pathlib import Path

import dashstate as state
import liverule as lr

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[5]
PATTERNS = ("steprun", "stoptest", "pass", "preflight")
MAX_FILES = 12
DEMO_STEPS = list(lr.DIST_STEPS)  # the distance-mode default
LOOP_FACTOR = 1.122  # the loop is 12% longer than the first lengths said
REF_CSV = REPO / "docs/jmri/speedmatching/profile-2026-11-08/speed_by_step.csv"


def reference_curves():
    """{'2121': [{step, mm_s}], ...} from the 2026-11-08 result, scaled to the corrected loop."""
    out = {}
    try:
        with open(REF_CSV, newline="") as fh:
            for r in csv.DictReader(fh):
                loco = r["loco"].split()[-1]
                out.setdefault(loco, []).append(
                    {"step": int(r["step"]), "mm_s": round(float(r["mean_mm_per_s"]) * LOOP_FACTOR, 1)})
    except OSError:
        pass
    return out


# ---------------------------------------------------------------- the Pi over ssh

def ssh_fetcher(host=None, timeout=12):
    """Return fetch(cmd) -> bytes running cmd on the Pi (BatchMode, so never a prompt)."""
    host = host or os.environ.get("HART_PI_SSH", "pi")

    def fetch(cmd):
        p = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6", host, cmd],
                           capture_output=True, timeout=timeout)
        if p.returncode != 0:
            raise OSError((p.stderr or b"ssh failed").decode("utf-8", "replace").strip()[:200])
        return p.stdout

    return fetch


def list_cmd():
    pats = " ".join("/tmp/%s_*.log" % p for p in PATTERNS)
    return ("echo \"@@NOW $(date +%%s)\"; "
            "for f in $(ls -t %s 2>/dev/null | head -%d); do echo \"@@FILE $f $(stat -c %%s $f)\"; done; true"
            % (pats, MAX_FILES))


def tail_cmd(path, offset):
    return "tail -c +%d %s" % (offset + 1, shlex.quote(path))


class SshSource:
    mode = "live"

    def __init__(self, fetch):
        self.fetch = fetch
        self.offsets = {}  # path -> bytes consumed
        self.carry = {}  # path -> partial last line
        self.listed = []

    def poll(self, store):
        try:
            listing = self.fetch(list_cmd()).decode("utf-8", "replace")
            files = []
            for ln in listing.splitlines():
                parts = ln.split()
                if len(parts) == 2 and parts[0] == "@@NOW" and parts[1].isdigit():
                    store.pi_clock = (float(parts[1]), state.clock())
                if len(parts) == 3 and parts[0] == "@@FILE" and parts[2].isdigit():
                    files.append((parts[1], int(parts[2])))
            self.listed = [p for p, _ in files]  # the newest MAX_FILES logs, as listed this poll
            for path, size in reversed(files):  # oldest first, so the newest run is last
                off = self.offsets.get(path, 0)
                if size < off:  # file replaced
                    off = 0
                    self.carry.pop(path, None)
                    store.drop(path)
                store.ensure(path)
                if size == off:
                    self.offsets.setdefault(path, off)
                    continue
                data = self.fetch(tail_cmd(path, off))
                self.offsets[path] = off + len(data)
                text = self.carry.pop(path, b"") + data
                body, nl, rest = text.rpartition(b"\n")
                if not nl:
                    self.carry[path] = text
                    continue
                self.carry[path] = rest
                for ln in body.decode("utf-8", "replace").splitlines():
                    store.feed(path, ln)
            return True, None
        except (OSError, subprocess.SubprocessError) as e:
            return False, "Pi not reachable, retrying (%s)" % (str(e) or e.__class__.__name__)


# ---------------------------------------------------------------- replay and demo

def replay_schedule(logs, rate=20.0, max_gap=120.0):
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

    def __init__(self, logs, rate=20.0, clock=time.monotonic, max_gap=120.0):
        self.items = replay_schedule(logs, rate, max_gap)
        self.clock = clock
        self.start = None
        self.i = 0
        self.now = self.items[0][1] if self.items else time.time()

    def poll(self, store):
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
    def finished(self):
        return self.i >= len(self.items)


def read_logs(paths):
    out = []
    for p in paths:
        out.append((Path(p).name, Path(p).read_text(errors="replace").splitlines()))
    return out


def pass_sequence(names, frm, to):
    """The sensors a pass lights, in order: the path from `frm` to `to` (the shorter way round,
    modulo the ring) and then the sensor after `to`, whose lighting ends the pass."""
    return lr.path_between(names, frm, to) + [lr.next_after(names, frm, to)]


def demo_logs(seed=7, t0=1794300000.0):
    """Synthetic logs in the shape the distance-mode runner writes, in time order: CSX 2121 and
    CSX 2738 both directions on loop1 (the 60 s warm-up only before a loco's first run), then
    two Switch 13 passes on loop2. Block lengths from block_lengths.csv; speeds are the
    2026-11-08 result x1.122, with a little noise. The end rule is the runner's own
    (liverule.DistanceStep), so slow steps end as "max" and show as not valid."""
    import json
    rng = random.Random(seed)
    ref = {k: {r["step"]: r["mm_s"] for r in v} for k, v in reference_curves().items()}
    bias = {("2121", "forward"): 1.0, ("2121", "reverse"): 0.97,
            ("2738", "forward"): 1.0, ("2738", "reverse"): 1.04}

    def lens(route):
        bl = state.route_blocks(route)
        for b in bl:
            b["mm"] = float(b["mm"] if b["mm"] is not None else 150.0)
        return bl

    logs, clock = [], [t0]

    def new_log():
        lines = []

        def L(dt, msg):
            clock[0] += dt
            lines.append("%.3f %s" % (clock[0], msg))
        return lines, L

    for loco in ("2121", "2738"):
        warm = True
        for direction in ("forward", "reverse"):
            base = lens("loop1")
            blocks = base if direction == "forward" else list(reversed(base))
            n = len(blocks)
            lines, L = new_log()
            L(0, "RUN loco=%s direction=%s" % (loco, direction))
            L(0.1, "CFG route=loop1 mode=distance steps=%s target_mm=%g min_blocks=%d max_s=%g rel=%g warm_s=%g "
                   "warm_step=%d cv3=%d cv4=%d mid=BS_Switch_23a" % (
                       ",".join(map(str, DEMO_STEPS)), lr.DIST_TARGET_MM, lr.DIST_MIN_BLOCKS, lr.DIST_MAX_S,
                       lr.DIST_REL, lr.DIST_WARM_S if warm else 0, lr.DIST_WARM_STEP, lr.DIST_CV3, lr.DIST_CV4))
            L(0.1, "LENGTHS " + json.dumps({b["sensor"]: b["mm"] for b in base}))
            clock[0] += 1.0
            k = [rng.randrange(n)]  # index of the block the loco enters next
            v = [ref[loco][DEMO_STEPS[0]]]
            nxt = [clock[0] + 20.0]
            spike = [None]

            def vn(step):
                x = v[0] * (1 + rng.gauss(0, 0.012))
                if spike[0] == step and rng.random() < 0.25:
                    x *= 0.93
                return x

            def enter(step):
                """The loco enters the next block: SENS line at its time; returns (block, time)."""
                b = blocks[k[0] % n]
                clock[0] = nxt[0]
                lines.append("%.3f SENS %s ACTIVE" % (clock[0], b["sensor"]))
                nxt[0] = clock[0] + b["mm"] / vn(step)
                k[0] += 1
                return b, clock[0]

            def advance(until, step):
                while nxt[0] <= until:
                    enter(step)
                clock[0] = max(clock[0], until)

            def set_speed(step):
                left = max(nxt[0] - clock[0], 0) * v[0]
                v[0] = ref[loco][step] * bias[(loco, direction)]
                nxt[0] = clock[0] + left / v[0]

            prev = 0
            if warm:
                set_speed(lr.DIST_WARM_STEP)
                L(0, "WARMUP %d secs=%g" % (lr.DIST_WARM_STEP, lr.DIST_WARM_S))
                advance(clock[0] + lr.DIST_WARM_S, lr.DIST_WARM_STEP)
                L(0, "WARMUP_DONE")
                prev = lr.DIST_WARM_STEP
            for step in DEMO_STEPS:
                secs = lr.settle_time(lr.DIST_CV3, lr.DIST_CV4, prev, step)
                spike[0] = 64 if (loco, direction) == ("2738", "reverse") else None
                L(0.05, "STEP %d" % step)
                set_speed(step)
                L(0.01, "SETTLE %d secs=%.1f" % (step, secs))
                advance(clock[0] + secs, step)
                b0, mstart = enter(step)
                L(0, "MEASURE %d from=%s" % (step, b0["sensor"]))
                cur = (b0, mstart)
                ds = lr.DistanceStep(lr.DIST_TARGET_MM, lr.DIST_MIN_BLOCKS, lr.DIST_MAX_S, lr.DIST_REL)
                reason = ""
                while True:
                    if nxt[0] - mstart >= lr.DIST_MAX_S:
                        clock[0] = mstart + lr.DIST_MAX_S
                        done, reason = ds.check(lr.DIST_MAX_S)  # the runner's own time-out: timed or max
                        break
                    b2, t2 = enter(step)
                    dt = t2 - cur[1]
                    lines.append("%.3f BLOCK %d block=%s mm=%d dt=%.2f mm_s=%.1f" % (
                        t2, step, cur[0]["sensor"].replace(" ", "_"), round(cur[0]["mm"]), dt, cur[0]["mm"] / dt))
                    ds.add(cur[0]["mm"], dt)
                    cur = (b2, t2)
                    done, why = ds.check(t2 - mstart)
                    if ds.extra_new:
                        ds.extra_new = False
                        L(0.1, "EXTRA %d relsd=%.4f" % (step, ds.relsd))
                    if done:
                        reason = why
                        clock[0] = t2 + 0.1
                        break
                L(0.0, "FREEZE %d" % step)
                cnt, mm, secs_m, speed, rsd = lr.aggregate(ds.blocks)
                L(0.0, "STEPDONE %d reason=%s n=%d mm=%.1f s=%.2f mm_s=%.1f relsd=%.4f" % (
                    step, reason, cnt, mm, secs_m, speed, rsd))
                prev = step
            L(0.5, "speed 0")
            L(0.1, "STOP all steps complete")
            L(0.1, "END")
            logs.append(("steprun_CSX_%s_%s_demo.log" % (loco, direction), lines))
            clock[0] += 30
            warm = False

    # two Switch 13 passes on loop2: Switch 5 to Switch 15, the loco stops once the sensor after lights
    for step in (24, 48):
        names = [b["sensor"] for b in lens("loop2")]
        mm = {b["sensor"]: b["mm"] for b in lens("loop2")}
        seq = pass_sequence(names, "BS Switch 5", "BS Switch 15")
        lines, L = new_log()
        v = ref["2121"][step]
        L(0, "RUN loco=2121 direction=forward")
        L(0.1, "CFG route=loop2 mode=pass step=%d max_s=300" % step)
        L(0.5, "PATH " + ",".join(seq[:-1]))
        L(0.5, "PASS step=%d from=BS Switch 5 to=BS Switch 15" % step)
        L(8.0, "SENS %s ACTIVE" % seq[0])
        for prev, sensor in zip(seq, seq[1:]):
            L(mm[prev] / (v * (1 + rng.gauss(0, 0.01))), "SENS %s ACTIVE" % sensor)
        L(0.2, "PASSDONE reason=passed")
        L(0.1, "speed 0")
        L(0.1, "STOP passed")
        L(0.1, "END")
        logs.append(("pass_CSX_2121_forward_step%d_demo.log" % step, lines))
        clock[0] += 20
    return logs
