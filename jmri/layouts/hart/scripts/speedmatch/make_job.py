#!/usr/bin/env python3
"""Build a job file for the Pi's jmri_cmd_watcher: settings, then the shared logic, then the runner.

    make_job.py steps     --loco "CSX 2738" --direction reverse --out /tmp/job_steps.py
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


# Every block sensor that is not on the test loop (analyze.LOOP). Checked against the sensor
# names in tables.xml by the tests. McKees Rocks and McKeesport are not here: their own
# detector sections are not on a node yet (wiki/STATUS.md).
DEFAULT_GUARD = [
    "BS S-R", "BS S-1", "BS S-2", "BS S-3", "BS S-4", "BS Switch 23b", "BS Switch 13",
    "BS Switch 15", "BS Scale", "BS Barn", "BS Switch 11", "BS Switch 9", "BS EH-1", "BS EH-2",
    "BS EH-3", "BS Switch 3", "BS W-1", "BS W-2", "BS Switch 7",
    "BS Switch 17", "BS Switch 19", "BS Switch 21", "BS Switch 25", "BS Switch 27",
    "BS Switch 29", "BS Switch 31",
]


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


def step_list(text):
    return [step_value(x) for x in text.split(",")]


def guards(values):
    """--guard values: sensor names, or the single word none to run without a guard on purpose
    (the runner then logs NO GUARD). The word default stands for DEFAULT_GUARD and may be
    combined with more names."""
    if "none" in values:
        if len(values) > 1:
            raise SystemExit("--guard none cannot be combined with sensor names")
        return []
    out = []
    for v in values:
        for n in (DEFAULT_GUARD if v == "default" else [v]):
            if n not in out:
                out.append(n)
    return out


def settings_text(d):
    return "".join("%s = %r\n" % (k, v) for k, v in d.items())


def build_steps(a, lengths):
    s = {
        "LOGF": a.log, "P_ID": a.loco, "P_FWD": a.direction == "forward",
        "FUNCS": [0] + ([8] if a.mute_sound else []),
        "GUARD": guards(a.guard), "REF": analyze.ORDER[0], "MID": "BS Switch 23a",
        "ORDER": analyze.ORDER, "LENGTHS": lengths,
        "STEPS_LIST": a.steps, "WARM_STEP": a.warm_step, "WARM_LAPS": a.warm_laps,
        "STOP_K": a.k, "STOP_REL": a.rel, "MAX_READINGS": a.max_n,
        "SETTLE_EVENTS": a.settle, "LOW_MAX": a.low_max, "HIGH_SPAN": a.high_span,
        "STALL0": a.stall, "STALL_CAP": a.stall_cap, "STALL_SKIP_BELOW": a.stall_skip_below,
        "STEP_MAX_S": a.step_max,
    }
    # liverule.py first (its defaults), then the settings (they override those defaults),
    # then the runner. The marker line lets a test run everything before the runner.
    return ((HERE / "liverule.py").read_text() + "\n" + settings_text(s) + RUNNER_MARK
            + (HERE / "jython" / "step_runner.py").read_text())


def build_move(a):
    s = {"LOGF": a.log, "P_ID": a.loco, "P_FWD": a.direction == "forward", "P_STEP": a.step,
         "UNTIL": list(a.until), "GUARD": guards(a.guard), "FUNCS": [0] + ([8] if a.mute_sound else []),
         "MAX_S": a.max_s}
    return settings_text(s) + (HERE / "jython" / "move_to.py").read_text()


def build_stoptest(a):
    g = guards(a.guard)
    if a.trigger in g:
        raise SystemExit("--trigger %r is also a guard: the run would end before it stops the loco" % a.trigger)
    if a.trigger in DEFAULT_GUARD:
        raise SystemExit("--trigger %r is off the test loop; pick a loop sensor" % a.trigger)
    s = {"LOGF": a.log, "P_ID": a.loco, "P_FWD": a.direction == "forward", "P_STEP": a.step,
         "TRIGGER": a.trigger, "GUARD": g, "FUNCS": [0] + ([8] if a.mute_sound else []),
         "MAX_S": a.max_s, "SETTLE_S": a.settle_s, "QUIET_S": a.quiet_s}
    return settings_text(s) + (HERE / "jython" / "stop_test.py").read_text()


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
    st.add_argument("--steps", type=step_list, default=DEFAULT_STEPS, help="whole steps 1..126, comma separated")
    st.add_argument("--warm-laps", type=int, default=DEFAULT_WARM_LAPS)
    st.add_argument("--warm-step", type=int, default=DEFAULT_WARM_STEP)
    st.add_argument("--k", type=int, default=lr.STOP_K)
    st.add_argument("--rel", type=float, default=lr.STOP_REL)
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
    for p in (st, pf, mv, sp, pr):
        p.add_argument("--out", required=True, help="job file to write")
    a = ap.parse_args(argv)
    tag = a.loco.replace(" ", "_") if getattr(a, "loco", None) else "profile"
    if a.job == "steps":
        a.log = a.log or "/tmp/steprun_%s_%s_%s.log" % (tag, a.direction, stamp)
        lengths = analyze.load_lengths(a.lengths, tuple(a.trusted.split(",")))
        if sum(v is not None for v in lengths.values()) == 0:
            sys.exit("no trusted block lengths: nothing to measure over (see --trusted)")
        text = build_steps(a, lengths)
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
