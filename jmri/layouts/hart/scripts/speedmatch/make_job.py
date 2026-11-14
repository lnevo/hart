#!/usr/bin/env python3
"""Build a job file for the Pi's jmri_cmd_watcher: settings, then the shared logic, then the runner.

    make_job.py steps     --loco "CSX 2738" --direction reverse --out /tmp/job_steps.py
    make_job.py steps     --loco "CSX 2121" --direction forward --mode distance --guard default --out job.py
    make_job.py pass      --loco "CSX 2121" --direction forward --step 24 --from "BS Switch 5" --to "BS Switch 15" \\
                          --route loop2 --guard default --out job.py
    make_job.py lineup    --route loop2        # the switch positions to set by hand
    make_job.py preflight --loco "CSX 2738" --out /tmp/job_preflight.py
    make_job.py stoptest  --loco "CSX 2121" --direction reverse --step 96 --trigger "BS Switch 33" --out job.py
    make_job.py profile   --payload payload_2121.json --out /tmp/job_profile.py   # dry run unless --apply

The job file is plain Jython 2.7. liverule.py (the stop rule and span arithmetic the tests
check) is pasted in front of step_runner.py, so the runner on the Pi runs exactly that code.
Nothing is sent: use drop_job.sh to copy a job to the Pi.
"""
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths, tables as tables_lib  # noqa: E402
import analyze  # noqa: E402
import liverule as lr  # noqa: E402
import preflight_compare as pc  # noqa: E402

# Creep steps, the 2026-11-08 steps, and a repeat of 126 at the end to measure drift.
DEFAULT_STEPS = [2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 80, 96, 112, 126, 126]
DEFAULT_WARM_STEP = 64
DEFAULT_WARM_LAPS = 3
# Decoder families differ in their back-EMF CVs; the lists below are the CVs that exist in
# the roster entries of CSX 2121 (Tsunami 2) and CSX 2738 (TCS MC). Check the manual for
# any other decoder before trusting them.
BACKEMF = {"tsunami2": [209, 210, 211, 212, 213], "tcs": [49, 56, 57], "none": []}
BASE_CVS = pc.BASE_CVS


TABLES = paths.TABLES_XML


def guard_for(route=analyze.DEFAULT_ROUTE, tables=TABLES):
    """Every block sensor ("BS ..." user name) in tables.xml that is not on the route, in the
    order tables.xml lists them: what --guard default stands for. Computed, not hand-listed, so a
    new block sensor is guarded at once. McKees Rocks and McKeesport share the Switch 37 and 39
    sensors (their own detector sections are not on a node yet, wiki/STATUS.md)."""
    on_route = set(analyze.route_order(route))
    key = (route, str(tables))
    if key not in _GUARD_CACHE:
        out = []
        for el in tables_lib.read(tables).iter("userName"):  # ElementTree unescapes entities
            n = (el.text or "").strip()
            if n.startswith("BS ") and n not in on_route and n not in out:
                out.append(n)
        _GUARD_CACHE[key] = out
    return list(_GUARD_CACHE[key])


_GUARD_CACHE = {}


def __getattr__(name):
    """DEFAULT_GUARD (loop1's guard) is computed on first use: importing this module reads nothing."""
    if name == "DEFAULT_GUARD":
        return guard_for(analyze.DEFAULT_ROUTE)
    raise AttributeError(name)


RUNNER_MARK = "# ---- runner ----\n"


def step_value(text):
    """One throttle step: an integer 1..126 (argparse type)."""
    try:
        n = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("%r is not a whole number" % text)
    if not 1 <= n <= 126:
        raise argparse.ArgumentTypeError("step %d is outside 1..126" % n)
    return n


def lineup_text(route):
    """The switch positions to set by hand for a route, as printed by the lineup job. Nothing
    here is ever sent anywhere."""
    lines = ["Line up for %s by hand (tools never command turnouts):" % route]
    lines += ["  Switch %-3d %s" % (n, pos) for n, pos in analyze.ROUTE_LINEUP[route]]
    lines.append("Route, in running order: " + ", ".join(s[3:] for s in analyze.route_order(route)))
    return "\n".join(lines)


def step_list(text):
    return [step_value(x) for x in text.split(",")]


def guards(values, route=analyze.DEFAULT_ROUTE):
    """--guard values: sensor names, or the single word none to run without a guard on purpose
    (the runner then logs NO GUARD). The word default stands for guard_for(route), every block
    sensor off that route, and may be combined with more names."""
    if "none" in values:
        if len(values) > 1:
            raise SystemExit("--guard none cannot be combined with sensor names")
        return []
    out = []
    for v in values:
        for n in (guard_for(route) if v == "default" else [v]):
            if n not in out:
                out.append(n)
    return out


def runner_text(name):
    """The runner part of a job: the mark, the shared jobkit.py, then the runner itself. The
    three movers (steps, move, stoptest) share jobkit.py, so none keeps its own copy."""
    return RUNNER_MARK + (HERE / "jython" / "jobkit.py").read_text() + "\n" + (HERE / "jython" / name).read_text()


def settings_text(d):
    return "".join("%s = %r\n" % (k, v) for k, v in d.items())


def build_steps(a, lengths):
    order = analyze.route_order(a.route)
    s = {
        "LOGF": a.log, "P_ID": a.loco, "P_FWD": a.direction == "forward",
        "FUNCS": [0] + ([8] if a.mute_sound else []),
        "GUARD": guards(a.guard, a.route), "REF": order[0], "MID": analyze.route_mid(a.route),
        "ROUTE": a.route, "ORDER": order, "LENGTHS": lengths,
        "STEPS_LIST": a.steps, "WARM_STEP": a.warm_step, "WARM_LAPS": a.warm_laps,
        "STOP_K": a.k, "STOP_REL": a.rel, "MAX_READINGS": a.max_n,
        "SETTLE_EVENTS": a.settle, "LOW_MAX": a.low_max, "HIGH_SPAN": a.high_span,
        "STALL0": a.stall, "STALL_CAP": a.stall_cap, "STALL_SKIP_BELOW": a.stall_skip_below,
        "STEP_MAX_S": a.step_max,
    }
    # liverule.py first (its defaults), then the settings (they override those defaults),
    # then the runner. The marker line lets a test run everything before the runner.
    return ((HERE / "liverule.py").read_text() + "\n" + settings_text(s)
            + runner_text("step_runner.py"))


def build_distance(a, lengths):
    """steps --mode distance: one continuous pass, each step measured over a distance."""
    order = analyze.route_order(a.route)
    s = {
        "LOGF": a.log, "P_ID": a.loco, "P_FWD": a.direction == "forward",
        "FUNCS": [0] + ([8] if a.mute_sound else []),
        "GUARD": guards(a.guard, a.route), "MID": analyze.route_mid(a.route),
        "ROUTE": a.route, "ORDER": order, "LENGTHS": lengths,
        "STEPS_LIST": a.steps, "WARM_S": a.warm_s, "WARM_STEP": a.warm_step,
        "TARGET_MM": a.target_mm, "MIN_BLOCKS": a.min_blocks, "MAX_S": a.max_s, "REL": a.rel,
        "CV3": a.cv3, "CV4": a.cv4,
        "STALL0": a.stall, "STALL_CAP": a.stall_cap, "STALL_SKIP_BELOW": a.stall_skip_below,
    }
    return ((HERE / "liverule.py").read_text() + "\n" + settings_text(s)
            + runner_text("distance_runner.py"))


def build_pass(a):
    order = analyze.route_order(a.route)
    g = guards(a.guard, a.route)
    for n in (a.frm, a.to):
        if n not in order:
            raise SystemExit("%r is not a %s sensor user name; give one of: %s" % (n, a.route, ", ".join(order)))
    if a.frm == a.to:
        raise SystemExit("--from and --to are the same sensor")
    after = lr.next_after(order, a.frm, a.to)
    if after == a.frm:
        raise SystemExit("no sensor between --to and --from to end the pass on")
    for n in lr.path_between(order, a.frm, a.to) + [after]:
        if n in g:
            raise SystemExit("%r is also a guard: the run would end before the pass is done" % n)
    s = {"LOGF": a.log, "P_ID": a.loco, "P_FWD": a.direction == "forward", "P_STEP": a.step,
         "FUNCS": [0] + ([8] if a.mute_sound else []), "GUARD": g, "ROUTE": a.route, "ORDER": order,
         "FROM_S": a.frm, "TO_S": a.to, "AFTER_S": after, "PATH": lr.path_between(order, a.frm, a.to), "MAX_S": a.max_s, "STALL": a.stall}
    return ((HERE / "liverule.py").read_text() + "\n" + settings_text(s)
            + runner_text("pass_runner.py"))


def build_move(a):
    s = {"LOGF": a.log, "P_ID": a.loco, "P_FWD": a.direction == "forward", "P_STEP": a.step,
         "UNTIL": list(a.until), "GUARD": guards(a.guard, a.route), "FUNCS": [0] + ([8] if a.mute_sound else []),
         "MAX_S": a.max_s}
    return settings_text(s) + runner_text("move_to.py")


def build_stoptest(a):
    g = guards(a.guard, a.route)
    order = analyze.route_order(a.route)
    if a.trigger in g:
        raise SystemExit("--trigger %r is also a guard: the run would end before it stops the loco" % a.trigger)
    if a.trigger not in order:
        raise SystemExit("--trigger %r is not a %s sensor user name; give one of: %s (system names are refused so "
                         "the off-loop check is reliable)" % (a.trigger, a.route, ", ".join(order)))
    s = {"LOGF": a.log, "P_ID": a.loco, "P_FWD": a.direction == "forward", "P_STEP": a.step,
         "TRIGGER": a.trigger, "GUARD": g, "FUNCS": [0] + ([8] if a.mute_sound else []),
         "MAX_S": a.max_s, "SETTLE_S": a.settle_s, "QUIET_S": a.quiet_s}
    return settings_text(s) + runner_text("stop_test.py")


def build_profile(a):
    payload = json.loads(Path(a.payload).read_text())
    pts = payload.get("points") or []
    if not payload.get("roster_id") or not pts:
        raise SystemExit("payload has no roster_id or no points")
    points = []
    for p in pts:
        fw, rv = p.get("forward_mm_s"), p.get("reverse_mm_s")
        if not isinstance(fw, (int, float)) or not isinstance(rv, (int, float)) or fw <= 0 or rv <= 0:
            raise SystemExit("point for step %r needs a forward and a reverse speed above 0" % p.get("step"))
        step = step_value(str(p["step"]))
        points.append({"key": int(round(step / 126.0 * 1000)), "step": step,
                       "forward": float(fw), "reverse": float(rv)})
    if len({p["key"] for p in points}) != len(points):
        raise SystemExit("two points share a throttle key")
    s = {"LOGF": a.log, "P_ID": payload["roster_id"], "POINTS": points, "APPLY": bool(a.apply)}
    return settings_text(s) + (HERE / "jython" / "write_profile.py").read_text()


def build_preflight(a):
    cvs = BASE_CVS + BACKEMF[a.backemf]
    s = {"LOGF": a.log, "P_ID": a.loco, "CVS": cvs, "CV_WAIT": a.cv_wait}
    return settings_text(s) + (HERE / "jython" / "preflight.py").read_text()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="job", required=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    st = sub.add_parser("steps", help="warm-up and step profile of one loco in one direction")
    st.add_argument("--loco", required=True, help='roster id, e.g. "CSX 2738"')
    st.add_argument("--direction", required=True, choices=["forward", "reverse"])
    st.add_argument("--mode", choices=["laps", "distance"], default="laps",
                    help="laps (default): readings per step, warm-up in laps; distance: one continuous pass, "
                         "each step measured over --target-mm of whole blocks")
    st.add_argument("--steps", type=step_list, default=None,
                    help="whole steps 1..126, comma separated (default: laps %s, distance %s)" % (
                        ",".join(map(str, DEFAULT_STEPS)), ",".join(map(str, lr.DIST_STEPS))))
    st.add_argument("--warm-laps", type=int, default=DEFAULT_WARM_LAPS, help="laps mode: laps before measuring")
    st.add_argument("--warm-step", type=int, default=None,
                    help="step of the warm-up (default 64 laps, 48 distance)")
    st.add_argument("--warm-s", type=float, default=lr.DIST_WARM_S, help="distance mode: warm-up seconds (0 = none)")
    st.add_argument("--target-mm", type=float, default=lr.DIST_TARGET_MM, help="distance mode: distance per step")
    st.add_argument("--min-blocks", type=int, default=lr.DIST_MIN_BLOCKS, help="distance mode: fewest blocks per step")
    st.add_argument("--max-s", type=float, default=lr.DIST_MAX_S, help="distance mode: seconds of measuring per step")
    st.add_argument("--cv3", type=int, default=lr.DIST_CV3, help="distance mode: acceleration CV (settle time)")
    st.add_argument("--cv4", type=int, default=lr.DIST_CV4, help="distance mode: deceleration CV (settle time)")
    st.add_argument("--k", type=int, default=lr.STOP_K)
    st.add_argument("--rel", type=float, default=None,
                    help="spread that settles a step (default laps %g, distance %g)" % (lr.STOP_REL, lr.DIST_REL))
    st.add_argument("--max", type=int, default=lr.MAX_READINGS, dest="max_n")
    st.add_argument("--settle", type=int, default=lr.SETTLE_EVENTS)
    st.add_argument("--low-max", type=int, default=lr.LOW_MAX)
    st.add_argument("--high-span", type=int, default=lr.HIGH_SPAN)
    st.add_argument("--stall", type=float, default=120.0, help="seconds without a sensor event")
    st.add_argument("--stall-cap", type=float, default=lr.STALL_CAP,
                    help="the no-event limit never grows past this many seconds")
    st.add_argument("--stall-skip-below", type=int, default=6,
                    help="a stall at or below this step skips the step instead of ending the run")
    st.add_argument("--step-max", type=float, default=900.0, help="seconds allowed for one step")
    st.add_argument("--guard", action="append", required=True,
                    help="sensor (user or system name) that aborts the run; repeatable. Required: "
                         "pass --guard default for every block sensor off the test loop, or "
                         "--guard none to run without one (logged as NO GUARD)")
    st.add_argument("--mute-sound", action="store_true", help="also switch F8 on (2121's mute)")
    st.add_argument("--lengths", default=str(analyze.DEFAULT_LENGTHS))
    st.add_argument("--trusted", default=",".join(analyze.DEFAULT_TRUSTED))
    st.add_argument("--log", help="log path on the Pi")
    mv = sub.add_parser("move", help="run a loco until a sensor lights, then stop it")
    mv.add_argument("--loco", required=True)
    mv.add_argument("--direction", required=True, choices=["forward", "reverse"])
    mv.add_argument("--step", type=step_value, default=24)
    mv.add_argument("--until", action="append", required=True,
                    help="sensor to stop at (user or system name); repeatable, any one counts")
    mv.add_argument("--guard", action="append", required=True,
                    help="as for steps: sensor names, or none")
    mv.add_argument("--max-s", type=float, default=90.0)
    mv.add_argument("--mute-sound", action="store_true")
    mv.add_argument("--log")
    ps = sub.add_parser("pass", help="one timed pass through a stretch, to place a switch (infer_block_lengths.py --pass-log)")
    ps.add_argument("--loco", required=True)
    ps.add_argument("--direction", required=True, choices=["forward", "reverse"])
    ps.add_argument("--step", type=step_value, required=True)
    ps.add_argument("--from", dest="frm", required=True, help="sensor user name the pass starts at")
    ps.add_argument("--to", required=True, help="sensor user name the pass goes through; it ends one block later")
    ps.add_argument("--guard", action="append", required=True, help="as for steps: sensor names, default, or none")
    ps.add_argument("--max-s", type=float, default=240.0, help="seconds allowed before the pass is cut off")
    ps.add_argument("--stall", type=float, default=120.0, help="seconds without a route sensor event")
    ps.add_argument("--mute-sound", action="store_true")
    ps.add_argument("--log")
    pf = sub.add_parser("preflight", help="read the decoder's CVs on the programming track")
    pf.add_argument("--loco", required=True)
    pf.add_argument("--backemf", choices=sorted(BACKEMF), default="none")
    pf.add_argument("--cv-wait", type=float, default=20.0)
    pf.add_argument("--log", help="log path on the Pi")
    sp = sub.add_parser("stoptest", help="start from rest, send speed 0 when a sensor lights, log the stop")
    sp.add_argument("--loco", required=True, help="roster id; for a consist the lead loco only")
    sp.add_argument("--direction", required=True, choices=["forward", "reverse"])
    sp.add_argument("--step", type=step_value, required=True)
    sp.add_argument("--trigger", required=True, help="sensor whose lighting sends speed 0")
    sp.add_argument("--guard", action="append", required=True, help="as for steps: sensor names, default, or none")
    sp.add_argument("--max-s", type=float, default=180.0, help="seconds allowed before the trigger lights")
    sp.add_argument("--settle-s", type=float, default=30.0, help="seconds logged after the command")
    sp.add_argument("--quiet-s", type=float, default=10.0, help="end earlier after this long without an event")
    sp.add_argument("--mute-sound", action="store_true")
    sp.add_argument("--log")
    pr = sub.add_parser("profile", help="write measured speeds into a roster entry's speed profile")
    pr.add_argument("--payload", required=True, help="JSON from profile_to_roster.py")
    pr.add_argument("--apply", action="store_true", help="write (the job is a dry run without it)")
    pr.add_argument("--log")
    for p in (st, mv, sp, ps):
        p.add_argument("--route", choices=sorted(analyze.ROUTES), default=analyze.DEFAULT_ROUTE,
                       help="test route (default loop1); --guard default is every block sensor off it")
    li = sub.add_parser("lineup", help="print the switch positions to set by hand for a route")
    li.add_argument("--route", choices=sorted(analyze.ROUTES), default=analyze.DEFAULT_ROUTE)
    for p in (st, pf, mv, sp, pr, ps):
        p.add_argument("--out", required=True, help="job file to write")
    a = ap.parse_args(argv)
    if a.job == "lineup":
        print(lineup_text(a.route))
        return
    tag = a.loco.replace(" ", "_") if getattr(a, "loco", None) else "profile"
    if a.job == "steps":
        dist = a.mode == "distance"
        if a.steps is None:
            a.steps = list(lr.DIST_STEPS if dist else DEFAULT_STEPS)
        if a.warm_step is None:
            a.warm_step = lr.DIST_WARM_STEP if dist else DEFAULT_WARM_STEP
        if a.rel is None:
            a.rel = lr.DIST_REL if dist else lr.STOP_REL
        if (a.warm_s > 0 if dist else a.warm_laps > 0) and not 1 <= a.warm_step <= 126:
            sys.exit("--warm-step %d is outside 1..126" % a.warm_step)
        if dist and (a.target_mm <= 0 or a.min_blocks < 1 or a.max_s <= 0 or a.warm_s < 0):
            sys.exit("distance mode needs --target-mm and --max-s above 0, --min-blocks 1 or more, --warm-s 0 or more")
        a.log = a.log or "/tmp/steprun_%s_%s_%s.log" % (tag, a.direction, stamp)
        lengths = analyze.load_lengths(a.lengths, tuple(a.trusted.split(",")), analyze.route_loop(a.route))
        if sum(v is not None for v in lengths.values()) == 0:
            sys.exit("no trusted block lengths: nothing to measure over (see --trusted)")
        text = build_distance(a, lengths) if dist else build_steps(a, lengths)
    elif a.job == "pass":
        a.log = a.log or "/tmp/pass_%s_%s_step%d_%s.log" % (tag, a.direction, a.step, stamp)
        text = build_pass(a)
    elif a.job == "move":
        a.log = a.log or "/tmp/moveto_%s_%s.log" % (tag, stamp)
        text = build_move(a)
    elif a.job == "stoptest":
        a.log = a.log or "/tmp/stoptest_%s_%s_%s.log" % (tag, a.direction, stamp)
        text = build_stoptest(a)
    elif a.job == "profile":
        a.log = a.log or "/tmp/writeprofile_%s.log" % stamp
        text = build_profile(a)
    else:
        a.log = a.log or "/tmp/preflight_%s_%s.log" % (tag, stamp)
        text = build_preflight(a)
    Path(a.out).write_text(text)
    print("wrote %s (log on the Pi: %s)" % (a.out, a.log))


if __name__ == "__main__":
    main()
