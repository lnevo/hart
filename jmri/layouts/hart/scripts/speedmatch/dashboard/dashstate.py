"""Speed-match log parser and run state machine for the dashboard (stdlib only, no I/O).

Every log line is "<epoch seconds> <message>". Unknown lines are kept for the event feed and
otherwise ignored, so a runner that adds lines does not break the page.
"""
from __future__ import annotations

import json
import re
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
SM = HERE.parent
sys.path.insert(0, str(SM))

MM_S_TO_MPH_HO = 3.6 * 87 / 1609.34
MAX_STEP = 126
LOCO_ROAD = {"2121": "CSX 2121", "2738": "CSX 2738"}
EVENT_KEEP = 40


def mph_ho(mm_s):
    """HO scale mph for a speed in mm/s."""
    return None if mm_s is None else mm_s * MM_S_TO_MPH_HO


def kv(tokens):
    """key=value tokens to a dict; underscores in values stand for spaces."""
    out = {}
    for t in tokens:
        if "=" in t:
            k, v = t.split("=", 1)
            out[k] = v.replace("_", " ")
    return out


def num(v, default=None):
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return default


def parse_line(line):
    """(epoch, kind, rest-string) or None for a line that does not start with a time.

    kind is the first word of the message (RUN, STEP, SENS, ...); a message starting with
    "NO GUARD" has kind "NO_GUARD"."""
    line = line.strip()
    if not line:
        return None
    head, _, msg = line.partition(" ")
    try:
        t = float(head)
    except ValueError:
        return None
    msg = msg.strip()
    if msg.startswith("NO GUARD"):
        return t, "NO_GUARD", msg[len("NO GUARD"):].strip()
    kind, _, rest = msg.partition(" ")
    return t, kind, rest.strip()


def kind_of_log(name):
    base = Path(name).name
    for k in ("steprun", "stoptest", "pass", "preflight"):
        if base.startswith(k + "_"):
            return k
    return "other"


def norm(name):
    return re.sub(r"\s+", " ", name.replace("_", " ")).strip().lower()


def route_blocks(route, lengths_json=None):
    """[{sensor, name, mm}] in route order; mm from the log's LENGTHS line, else the CSV."""
    import analyze  # noqa: E402  (speedmatch/analyze.py)
    loop = analyze.ROUTES.get(route) or analyze.ROUTES[analyze.DEFAULT_ROUTE]
    csv_len = analyze.load_lengths(loop=loop, trusted=("anyrail", "inferred", "assigned", "estimate"))
    out = []
    for sensor, name in loop:
        mm = (lengths_json or {}).get(sensor)
        if mm is None:
            mm = csv_len.get(sensor)
        out.append({"sensor": sensor, "name": name, "mm": mm})
    return out


class Run:
    def __init__(self, rid, source_name=None):
        self.id = rid
        self.kind = kind_of_log(source_name or rid)
        self.loco = None
        self.direction = None
        self.cfg = {}
        self.route = None
        self.lengths = None
        self.status = "waiting"
        self.reason = None
        self.banner = None  # (level, text)
        self.guard = None
        self.t0 = None
        self.t_last = None
        self.t_end = None
        self.step = None
        self.steps = []
        self.step_t0 = None
        self.step_durations = []
        self.settle_until = None
        self.settle_secs = None
        self.warm = None
        self.measure_from = None
        self.blocks = []  # BLOCK rows of the current step
        self.reads = []  # READ rows of the current step (older mode)
        self.done = {}  # step -> {mm_s, n, mm, s, relsd, reason, blocks}
        self.active = None  # last sensor that went ACTIVE
        self.sens = {}
        self.speed = None  # latest live mm/s
        self.events = []
        self.lines = 0

    # -- helpers
    def event(self, t, text, level="info"):
        self.events.append({"t": t, "text": text, "level": level})
        del self.events[:-EVENT_KEEP]

    def road(self):
        if self.loco is None:
            return None
        s = str(self.loco)
        return LOCO_ROAD.get(s, s if not s.isdigit() else "CSX " + s)

    # -- the state machine
    def feed_line(self, line):
        p = parse_line(line)
        if p is None:
            return False
        self.feed(*p)
        return True

    def feed(self, t, kind, rest):
        self.lines += 1
        if self.t0 is None:
            self.t0 = t
        self.t_last = t
        toks = rest.split()
        if kind == "RUN":
            d = kv(toks)
            self.loco = d.get("loco", self.loco)
            self.direction = d.get("direction", self.direction)
            self.status = "starting"
            self.t0 = t
            self.event(t, "Run started: %s %s" % (self.road(), self.direction))
        elif kind == "CFG":
            d = kv(toks)
            self.cfg.update(d)
            self.route = d.get("route", self.route)
            if "steps" in d:
                self.steps = [int(x) for x in d["steps"].replace(" ", "").split(",") if x.strip().isdigit()]
            self.event(t, "Settings: route %s, %s mode" % (self.route or "?", d.get("mode", "?")))
        elif kind == "LENGTHS":
            try:
                self.lengths = json.loads(rest)
            except ValueError:
                pass
        elif kind == "WARMUP":
            d = toks
            self.status = "warming"
            self.step = num(d[0]) if d else self.step
            self.warm = {"step": self.step, "t": t}
            kvs = kv(d[1:])
            self.warm.update({k: num(v) for k, v in kvs.items()})
            self.warm["lap"] = 0
            self.event(t, "Warming up at step %s" % self.step)
        elif kind == "WARMUP_LAP":
            if self.warm is not None:
                self.warm["lap"] = num(toks[0], self.warm.get("lap", 0)) if toks else self.warm.get("lap", 0)
            self.event(t, "Warm-up lap %s" % (toks[0] if toks else ""))
        elif kind == "WARMUP_DONE":
            self.warm = None
            self.status = "settling"
            self.event(t, "Warm-up done")
        elif kind == "STEP":
            n = num(toks[0]) if toks else None
            self.step = n
            self.step_t0 = t
            self.blocks = []
            self.reads = []
            self.settle_until = None
            self.status = "settling"
            self.warm = None
            self.event(t, "Step %s" % n)
        elif kind == "SETTLE":
            d = kv(toks[1:])
            secs = num(d.get("secs"), 0)
            self.settle_secs = secs
            self.settle_until = t + secs
            self.status = "settling"
        elif kind == "MEASURE":
            d = kv(toks[1:])
            self.measure_from = d.get("from")
            self.status = "measuring"
            self.settle_until = None
        elif kind == "SENS":
            if len(toks) >= 2:
                state = toks[-1]
                sensor = " ".join(toks[:-1])
                self.sens[sensor] = state
                if state == "ACTIVE":
                    self.active = sensor
        elif kind == "BLOCK":
            n = num(toks[0]) if toks else self.step
            d = kv(toks[1:])
            row = {"step": n, "block": d.get("block", ""), "mm": num(d.get("mm")),
                   "dt": num(d.get("dt")), "mm_s": num(d.get("mm_s")), "t": t}
            self.blocks.append(row)
            if row["mm_s"] is not None:
                self.speed = row["mm_s"]
            if self.status in ("settling", "starting", "warming"):
                self.status = "measuring"
        elif kind == "READ":
            d = kv(toks[2:]) if len(toks) > 2 else {}
            row = {"i": num(toks[0]) if toks else None, "mm_s": num(toks[1]) if len(toks) > 1 else None,
                   "dt": num(d.get("dt")), "mm": num(d.get("mm")), "blocks": num(d.get("blocks")), "t": t}
            self.reads.append(row)
            if row["mm_s"] is not None:
                self.speed = row["mm_s"]
            if self.status in ("settling", "starting"):
                self.status = "measuring"
        elif kind == "STEPDONE":
            n = num(toks[0]) if toks else self.step
            d = kv(toks[1:])
            mm_s = num(d.get("mm_s"), num(d.get("median")))
            self.done[n] = {"mm_s": mm_s, "n": num(d.get("n")), "mm": num(d.get("mm")),
                            "s": num(d.get("s")), "relsd": num(d.get("relsd")),
                            "reason": d.get("reason"), "blocks": list(self.blocks) or list(self.reads)}
            if mm_s is not None:
                self.speed = mm_s
            if self.step_t0 is not None:
                self.step_durations.append(t - self.step_t0)
            self.event(t, "Step %s done: %s mm/s" % (n, "%.1f" % mm_s if mm_s is not None else "?"))
        elif kind == "PASS":
            d = kv(toks)
            self.status = "measuring"
            self.event(t, "Pass %s to %s" % (d.get("from", "?"), d.get("to", "?")))
        elif kind == "PASSDONE":
            d = kv(toks)
            self.reason = d.get("reason")
            self.event(t, "Pass done (%s)" % self.reason)
        elif kind == "STOP":
            self.status = "stopped"
            self.reason = rest or "stop"
            self.t_end = t
            self.banner = ("stop", "Stopped: " + self.reason)
            self.event(t, "STOP " + rest, "warn")
        elif kind == "END":
            if self.status not in ("stopped", "error", "aborted"):
                self.status = "done"
            self.t_end = t
            self.event(t, "Run ended")
        elif kind == "ERROR":
            self.status = "error"
            self.reason = rest
            self.t_end = t
            self.banner = ("error", "Error: " + rest)
            self.event(t, "ERROR " + rest, "error")
        elif kind == "ABORTED":
            self.status = "aborted"
            self.reason = rest
            self.t_end = t
            self.banner = ("error", "Aborted: " + rest)
            self.event(t, "ABORTED " + rest, "error")
        elif kind == "NO_GUARD":
            self.guard = rest or "no guard"
            self.banner = ("error", "Guard tripped: NO GUARD " + rest)
            self.event(t, "NO GUARD " + rest, "error")
        else:
            self.event(t, (kind + " " + rest).strip(), "debug")

    # -- derived
    def finished(self):
        return self.status in ("done", "stopped", "error", "aborted")

    def eta(self, now):
        """Seconds left, from the mean duration of the steps done; None when unknown."""
        if self.finished() or not self.steps or not self.step_durations:
            return None
        mean = sum(self.step_durations) / len(self.step_durations)
        left = [s for s in self.steps if s not in self.done and s != self.step]
        into = (now - self.step_t0) if self.step_t0 and self.step not in self.done else 0
        cur = max(mean - into, 0) if self.step is not None and self.step not in self.done else 0
        return cur + mean * len(left)

    def blocks_view(self):
        """Route blocks in running order with crossing data from the current step."""
        route = self.route or "loop1"
        try:
            rb = route_blocks(route, self.lengths)
        except Exception:  # pragma: no cover - missing CSV etc.
            return []
        if (self.direction or "forward") == "reverse":
            rb = list(reversed(rb))
        look = {}
        for b in rb:
            look[norm(b["sensor"])] = b
            look[norm(b["name"])] = b
        for b in rb:
            b["mm_s"] = None
            b["current"] = b["sensor"] == self.active
        for row in self.blocks:
            hit = look.get(norm(row["block"]))
            if hit is not None:
                hit["mm_s"] = row["mm_s"]
        return rb

    def to_dict(self, now):
        d = self.done
        curve = [{"step": s, "mm_s": d[s]["mm_s"]} for s in sorted(d) if d[s]["mm_s"] is not None]
        step_rows = self.blocks or self.reads
        total_mm = sum(r["mm"] or 0 for r in step_rows) or None
        total_s = sum(r["dt"] or 0 for r in step_rows) or None
        vals = [r["mm_s"] for r in step_rows if r.get("mm_s") is not None]
        spread = None
        if len(vals) >= 2:
            m = sum(vals) / len(vals)
            sd = (sum((v - m) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5
            spread = sd / m if m else None
        end = self.t_end or now
        return {
            "id": self.id, "kind": self.kind, "loco": self.loco, "road": self.road(),
            "direction": self.direction, "route": self.route, "status": self.status,
            "reason": self.reason, "banner": self.banner, "cfg": self.cfg, "steps": self.steps,
            "step": self.step, "max_step": MAX_STEP, "done_steps": len(d),
            "settle_left": max(self.settle_until - now, 0) if self.settle_until else None,
            "settle_secs": self.settle_secs, "warm": self.warm,
            "speed": self.speed, "speed_mph": mph_ho(self.speed),
            "t0": self.t0, "t_last": self.t_last, "t_end": self.t_end,
            "elapsed": (end - self.t0) if self.t0 else None, "eta": self.eta(now),
            "blocks": self.blocks_view(), "step_rows": step_rows, "step_sum_mm": total_mm,
            "step_sum_s": total_s, "step_spread": spread, "curve": curve,
            "events": self.events[-15:], "lines": self.lines,
        }


class Store:
    """All runs seen, keyed by log path. Feed it (run id, line) pairs."""

    def __init__(self):
        self.runs = {}
        self.order = []
        self.lock = threading.RLock()  # the poller feeds while the web threads snapshot

    def ensure(self, rid):
        with self.lock:
            run = self.runs.get(rid)
            if run is None:
                run = self.runs[rid] = Run(rid)
                self.order.append(rid)
            return run

    def drop(self, rid):
        with self.lock:
            self.runs.pop(rid, None)
            if rid in self.order:
                self.order.remove(rid)

    def feed(self, rid, line):
        with self.lock:
            return self.ensure(rid).feed_line(line)

    def snapshot(self, now, reachable=True, message=None, mode="live"):
        with self.lock:
            return self._snapshot(now, reachable, message, mode)

    def _snapshot(self, now, reachable, message, mode):
        runs = [self.runs[r].to_dict(now) for r in self.order]
        focus = None
        if runs:
            focus = max(runs, key=lambda r: (not (r["status"] in ("done", "stopped", "error", "aborted")),
                                             r["t_last"] or 0))["id"]
        return {"now": now, "reachable": reachable, "message": message, "mode": mode,
                "runs": runs, "focus": focus}
