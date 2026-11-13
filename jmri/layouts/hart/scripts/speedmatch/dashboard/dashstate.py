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
WRONG_WAY = "Pass went the wrong way, loco stopped"
INVALID_REASONS = ("max", "stalled")  # settled and timed count as measured


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
        self.loco_raw = None
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
        self.extra = None  # relsd of the extra reading in the current step
        self.pass_info = None  # {step, from, to, t, reason}
        self.pass_events = []  # (t, sensor) ACTIVE after the PASS line
        self.pass_path = None  # PATH line: sensors expected from `from` to `to`
        self.frozen = False  # FREEZE seen for the current step: no more blocks count

    # -- helpers
    def event(self, t, text, level="info"):
        self.events.append({"t": t, "text": text, "level": level})
        del self.events[:-EVENT_KEEP]

    def road(self):
        if self.loco is None:
            return None
        s = str(self.loco)
        return LOCO_ROAD.get(s, (self.loco_raw or s) if not s.isdigit() else "CSX " + s)

    def set_loco(self, raw):
        """Roster id as logged ("2121", or a road name like "CSX 2121"): keep the number as the key."""
        raw = (raw or "").strip()
        self.loco_raw = raw
        self.loco = raw.split()[-1] if raw else None

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
            m = re.match(r"loco=(.*?)\s+direction=(\S+)", rest)  # the roster id may hold a space
            if m:
                self.set_loco(m.group(1).replace("_", " "))
                self.direction = m.group(2)
            self.status = "starting"
            self.t0 = t
            self.event(t, "Run started: %s %s" % (self.road(), self.direction))
        elif kind == "CFG":
            d = kv(toks)
            self.cfg.update(d)
            self.route = d.get("route", self.route)
            if d.get("mode") == "pass":
                self.kind = "pass"
                if "step" in d:
                    self.step = num(d["step"])
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
            self.extra = None
            self.frozen = False
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
            m = re.match(r"\d+\s+from=(.*)$", rest)
            self.measure_from = m.group(1).strip() if m else None
            self.status = "measuring"
            self.settle_until = None
        elif kind == "FREEZE":
            self.frozen = True
            self.status = "computing"
            self.settle_until = None
            self.event(t, "Step %s done, computing" % (toks[0] if toks else self.step))
        elif kind == "PATH":
            self.pass_path = [x.strip() for x in rest.split(",") if x.strip()]
        elif kind == "EXTRA":
            d = kv(toks[1:])
            self.extra = num(d.get("relsd"), 0)
            self.event(t, "Step %s spread %.1f%%, taking one more reading" % (toks[0] if toks else "?", (self.extra or 0) * 100))
        elif kind == "SENS":
            if len(toks) >= 2:
                state = toks[-1]
                sensor = " ".join(toks[:-1])
                self.sens[sensor] = state
                if state == "ACTIVE" and not self.frozen:
                    self.active = sensor
                if state == "ACTIVE" and self.pass_info is not None and self.pass_info.get("reason") is None:
                    self.pass_events.append((t, sensor))
        elif kind == "BLOCK":
            if self.frozen:  # a block after FREEZE belongs to no step
                return
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
            nb = num(d.get("n"))
            reason = d.get("reason")
            # no reading (n=0 or a zero speed) is a gap, never 0 mm/s; max and stalled steps are not valid
            self.frozen = True
            if self.status == "computing":
                self.status = "measuring"
            has = mm_s is not None and mm_s > 0 and nb != 0
            valid = has and reason not in INVALID_REASONS
            self.done[n] = {"mm_s": mm_s if has else None, "n": nb, "mm": num(d.get("mm")),
                            "s": num(d.get("s")), "relsd": num(d.get("relsd")), "valid": valid,
                            "reason": reason, "blocks": list(self.blocks) or list(self.reads)}
            if has:
                self.speed = mm_s
            if self.step_t0 is not None:
                self.step_durations.append(t - self.step_t0)
            if valid:
                self.event(t, "Step %s done: %.1f mm/s (%s)" % (n, mm_s, reason or "measured"))
            else:
                self.event(t, "Step %s not valid: %s%s" % (n, reason or "no reading", "" if has else ", no reading"), "warn")
        elif kind == "PASS":
            m = re.match(r"step=(\d+)\s+from=(.*?)\s+to=(.*)$", rest)
            if m:
                self.pass_info = {"step": int(m.group(1)), "from": m.group(2).strip(), "to": m.group(3).strip(),
                                  "t": t, "reason": None}
                self.pass_events = []
                self.step = int(m.group(1))
                self.kind = "pass"
                self.route = self.route or self.cfg.get("route")
            self.status = "measuring"
            self.event(t, "Pass at step %s: %s to %s" % (self.step, self.pass_info and self.pass_info["from"], self.pass_info and self.pass_info["to"]))
        elif kind == "PASSDONE":
            d = kv(toks)
            self.reason = d.get("reason")
            if self.pass_info is not None:
                self.pass_info["reason"] = self.reason
            if self.reason == "passed":
                self.status = "done"
                self.event(t, "Pass done")
            elif (self.reason or "").replace("_", " ") == "wrong way":
                self.status = "stopped"
                self.banner = ("error", WRONG_WAY)
                self.event(t, WRONG_WAY, "error")
            else:
                self.status = "stopped"
                self.banner = ("stop", "Pass ended: %s" % self.reason)
                self.event(t, "Pass ended: %s" % self.reason, "warn")
            self.t_end = t
        elif kind == "STOP" and rest in ("all steps complete", "passed"):
            if self.status not in ("stopped", "error", "aborted"):
                self.status = "done"
            self.t_end = t
            self.event(t, "Run complete" if rest != "passed" else "Pass complete")
        elif kind == "STOP" and rest.replace("_", " ") == "wrong way":
            self.status = "stopped"
            self.reason = "wrong way"
            self.t_end = t
            self.banner = ("error", WRONG_WAY)
            self.event(t, WRONG_WAY, "error")
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
        pv = self.pass_view() if self.pass_info else None
        for row in (pv or {}).get("rows", []):
            if row["mm_s"] is not None:
                look[norm(row["sensor"])]["mm_s"] = row["mm_s"]
        return rb

    def pass_view(self):
        """The stretch of a pass job: route sensors from `from` through `to` and the one after,
        with the time each lit (seconds after the PASS line) and the speed across each block."""
        pi = self.pass_info
        if pi is None:
            return None
        try:
            rb = route_blocks(self.route or "loop2", self.lengths)
        except Exception:  # pragma: no cover
            return None
        if (self.direction or "forward") == "reverse":
            rb = list(reversed(rb))
        names = [b["sensor"] for b in rb]
        first = {}
        for t, sn in self.pass_events:
            first.setdefault(sn, t)
        rows = []
        span = None
        n = len(names)
        if self.pass_path and all(x in names for x in self.pass_path):
            span = [names.index(x) for x in self.pass_path]
            k = span[-1] + (1 if len(span) < 2 or (span[-1] - span[-2]) % n == 1 else -1)
            span.append(k % n)  # the sensor after the last one ends the pass
        elif pi["from"] in names and pi["to"] in names:
            i, j = names.index(pi["from"]), names.index(pi["to"])
            span = [(i + k) % n for k in range(((j - i) % n) + 2)]  # from .. to, and the sensor after
        if span:
            for pos, idx in enumerate(span):
                b = rb[idx]
                t_in = first.get(b["sensor"])
                nxt = first.get(rb[span[pos + 1]]["sensor"]) if pos + 1 < len(span) else None
                dt = (nxt - t_in) if (t_in is not None and nxt is not None) else None
                rows.append({"sensor": b["sensor"], "name": b["name"], "mm": b["mm"],
                             "t_rel": (t_in - pi["t"]) if t_in is not None else None, "dt": dt,
                             "mm_s": (b["mm"] / dt) if (dt and b["mm"]) else None})
        return {"step": pi["step"], "from": pi["from"], "to": pi["to"], "reason": pi["reason"], "rows": rows}

    def to_dict(self, now):
        d = self.done
        curve = [{"step": s, "mm_s": d[s]["mm_s"]} for s in sorted(d) if d[s]["valid"]]
        flagged = [{"step": s, "reason": d[s]["reason"] or "no reading", "mm_s": d[s]["mm_s"]}
                   for s in sorted(d) if not d[s]["valid"]]
        last = d.get(self.step)
        pv = self.pass_view()
        speed = self.speed
        if speed is None and pv:
            seen = [r["mm_s"] for r in pv["rows"] if r["mm_s"] is not None]
            speed = seen[-1] if seen else None
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
            "step": self.step, "max_step": MAX_STEP, "done_steps": len(d), "flagged": flagged,
            "last_done": ({k: last[k] for k in ("mm_s", "n", "mm", "s", "relsd", "reason", "valid")} if last else None),
            "extra": self.extra, "pass": pv,
            "settle_left": max(self.settle_until - now, 0) if self.settle_until else None,
            "settle_secs": self.settle_secs, "warm": self.warm,
            "speed": speed, "speed_mph": mph_ho(speed),
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
