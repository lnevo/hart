#!/usr/bin/env python3
"""Compare two stop-test logs (jython/stop_test.py): when each sensor lit after the speed-0 command.

    stoptest_compare.py LOG_A LOG_B [--out table.md]

For each log: the seconds after the STOPCMD line at which each block sensor lit (only sensors
that lit after the command), and the block the loco came to rest in (the last sensor that lit
and is still lit at the end, else the last one that lit). The table is the one in the
2026-11-08 momentum test (docs/jmri/speedmatching/profile-2026-11-08/README.md).
A consist driven through its lead is one log.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import liverule as lr  # noqa: E402

_LINE = re.compile(r"^(\d+\.\d+) (.*)$")
_HEAD = re.compile(r"^STOPTEST loco=(.+) direction=(\w+) step=(\d+) trigger=(.+)$")


def parse_stoptest(lines, source=""):
    """dict {loco, direction, step, trigger, source, stopped, complete, enters: [(sensor, seconds)],
    rest, end_reason}. `enters` are the sensors that lit after STOPCMD, in order, first lighting
    only; seconds are after the command."""
    res = {"loco": None, "direction": None, "step": None, "trigger": None, "source": source,
           "stopped": False, "complete": False, "enters": [], "rest": None, "end_reason": ""}
    t_stop = None
    state = {}
    last_lit = None
    seen = set()
    for line in lines:
        m = _LINE.match(lr.current_names(line.strip()))
        if not m:
            continue
        t, msg = float(m.group(1)), m.group(2)
        h = _HEAD.match(msg)
        if h:
            res.update(loco=h.group(1), direction=h.group(2), step=int(h.group(3)), trigger=h.group(4))
        elif msg.startswith("STOPCMD") and t_stop is None:
            t_stop = t
            res["stopped"] = True
        elif msg.startswith("SENS "):
            name, st = msg[5:].rsplit(" ", 1)
            if t_stop is not None and st == "ACTIVE" and state.get(name) != "ACTIVE" \
                    and name != res["trigger"]:
                last_lit = name
                if name not in seen:
                    seen.add(name)
                    res["enters"].append((name, round(t - t_stop, 2)))
            state[name] = st
        elif msg.startswith("STOP "):
            res["end_reason"] = msg[5:]
        elif msg == "END":
            res["complete"] = True
    if t_stop is not None:
        still = [n for n, _ in res["enters"] if state.get(n) == "ACTIVE"]
        # the last block lit after the command, if it is still occupied; else the last one lit
        res["rest"] = last_lit if last_lit in still or not still else still[-1]
        if res["rest"] is None and not res["enters"]:
            res["rest"] = res["trigger"]  # the trigger block: the loco stopped where it was
    return res


def table(a, b):
    """Markdown comparison of two parsed logs."""
    def label(r):
        return "%s (%s, step %s)" % (r["loco"], r["direction"], r["step"])
    ea, eb = dict(a["enters"]), dict(b["enters"])
    order = sorted(set(ea) | set(eb), key=lambda n: min(x for x in (ea.get(n), eb.get(n)) if x is not None))
    out = ["| Seconds after the stop command | %s | %s | difference |" % (label(a), label(b)),
           "|---|---:|---:|---:|"]
    for n in order:
        x, y = ea.get(n), eb.get(n)
        diff = "" if x is None or y is None else "%+.2f" % (y - x)
        out.append("| enters %s | %s | %s | %s |" % (
            n.replace("BS ", ""), "-" if x is None else "%.2f" % x, "-" if y is None else "%.2f" % y, diff))
    out.append("| comes to rest | in %s | in %s | %s |" % (
        (a["rest"] or "?").replace("BS ", ""), (b["rest"] or "?").replace("BS ", ""),
        "same block" if a["rest"] == b["rest"] else "different block"))
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("log_a")
    ap.add_argument("log_b")
    ap.add_argument("--out", help="write the table here as well")
    ns = ap.parse_args(argv)
    runs = []
    for p in (ns.log_a, ns.log_b):
        r = parse_stoptest(Path(p).read_text().splitlines(), Path(p).name)
        if r["loco"] is None or not r["stopped"]:
            sys.exit("%s: no STOPTEST line or no STOPCMD (the loco never reached the trigger)" % p)
        if not r["complete"]:
            print("warning: %s has no END line (still running?)" % p, file=sys.stderr)
        runs.append(r)
    text = table(*runs)
    print(text)
    if ns.out:
        Path(ns.out).write_text(text)


if __name__ == "__main__":
    main()
