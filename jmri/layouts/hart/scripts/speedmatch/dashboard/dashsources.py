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

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[5]
PATTERNS = ("steprun", "stoptest", "pass", "preflight")
MAX_FILES = 12
DEMO_STEPS = [8, 12, 16, 24, 32, 48, 64, 80, 96, 112, 126]
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
    return ("for f in $(ls -t %s 2>/dev/null | head -%d); do echo \"@@FILE $f $(stat -c %%s $f)\"; done; true"
            % (pats, MAX_FILES))


def tail_cmd(path, offset):
    return "tail -c +%d %s" % (offset + 1, shlex.quote(path))


class SshSource:
    mode = "live"

    def __init__(self, fetch):
        self.fetch = fetch
        self.offsets = {}  # path -> bytes consumed
        self.carry = {}  # path -> partial last line
        self.now = None

    def poll(self, store):
        try:
            listing = self.fetch(list_cmd()).decode("utf-8", "replace")
            files = []
            for ln in listing.splitlines():
                parts = ln.split()
                if len(parts) == 3 and parts[0] == "@@FILE" and parts[2].isdigit():
                    files.append((parts[1], int(parts[2])))
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
            self.now = time.time()
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

    def __init__(self, logs, rate=20.0, clock=time.monotonic, max_gap=120.0, loop=False):
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


def demo_logs(seed=7, t0=1794300000.0):
    """Synthetic distance-mode logs for CSX 2121 and 2738, both directions, in time order."""
    rng = random.Random(seed)
    ref = {k: {r["step"]: r["mm_s"] for r in v} for k, v in reference_curves().items()}
    bias = {("2121", "forward"): 1.0, ("2121", "reverse"): 0.97,
            ("2738", "forward"): 1.0, ("2738", "reverse"): 1.04}
    base = state.route_blocks("loop1")
    for b in base:
        if b["mm"] is None:
            b["mm"] = 150.0
        b["mm"] = float(b["mm"])
    logs, t = [], t0
    for loco in ("2121", "2738"):
        for direction in ("forward", "reverse"):
            blocks = base if direction == "forward" else list(reversed(base))
            lens = {b["sensor"]: b["mm"] for b in base}
            lines = []

            def L(dt, msg):
                nonlocal t
                t += dt
                lines.append("%.3f %s" % (t, msg))

            L(0, "RUN loco=%s direction=%s" % (loco, direction))
            L(0.1, "CFG route=loop1 mode=distance steps=%s target_mm=6000 min_blocks=6 max_s=900 rel=0.03 "
                   "warm_s=40 warm_step=64 cv3=0 cv4=0 mid=BS_Switch_23a" % ",".join(map(str, DEMO_STEPS)))
            L(0.1, "LENGTHS " + __import__("json").dumps(lens))
            L(0.5, "WARMUP 64 secs=40")
            for _ in range(4):
                L(10, "SENS %s ACTIVE" % blocks[rng.randrange(len(blocks))]["sensor"])
            L(0.5, "WARMUP_DONE")
            pos = 0
            for step in DEMO_STEPS:
                v0 = ref[loco][step] * bias[(loco, direction)]
                L(1, "STEP %d" % step)
                L(0.2, "SETTLE %d secs=%d" % (step, 8))
                for _ in range(4):
                    b = blocks[pos % len(blocks)]
                    L(2, "SENS %s ACTIVE" % b["sensor"])
                    pos += 1
                b = blocks[pos % len(blocks)]
                L(0.5, "MEASURE %d from=%s" % (step, b["sensor"].replace(" ", "_")))
                tot_mm = tot_s = 0.0
                rows = []
                k = 0
                while True:
                    b = blocks[pos % len(blocks)]
                    v = v0 * (1 + rng.gauss(0, 0.012))
                    dt = b["mm"] / v
                    L(dt, "SENS %s ACTIVE" % b["sensor"])
                    pos += 1
                    k += 1
                    tot_mm += b["mm"]
                    tot_s += dt
                    L(0, "BLOCK %d block=%s mm=%d dt=%.2f mm_s=%.1f" % (
                        step, b["sensor"].replace(" ", "_"), round(b["mm"]), dt, b["mm"] / dt))
                    rows.append(b["mm"] / dt)
                    if tot_mm >= 6000 and k >= 6:
                        break
                    if tot_s >= 900:
                        break
                m = sum(rows) / len(rows)
                sd = (sum((x - m) ** 2 for x in rows) / max(len(rows) - 1, 1)) ** 0.5
                L(0.2, "STEPDONE %d reason=target n=%d mm=%d s=%.1f mm_s=%.1f relsd=%.3f" % (
                    step, k, round(tot_mm), tot_s, tot_mm / tot_s, sd / m))
            L(1, "END")
            logs.append(("steprun_%s_%s_demo.log" % (loco, direction), lines))
            t += 30
    return logs
