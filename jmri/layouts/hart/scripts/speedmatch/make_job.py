#!/usr/bin/env python3
"""Build a job file for the Pi's jmri_cmd_watcher: settings, then the shared logic, then the runner.

    make_job.py steps     --loco "CSX 2738" --direction reverse --out /tmp/job_steps.py
    make_job.py preflight --loco "CSX 2738" --out /tmp/job_preflight.py

The job file is plain Jython 2.7. liverule.py (the stop rule and span arithmetic the tests
check) is pasted in front of step_runner.py, so the runner on the Pi runs exactly that code.
Nothing is sent: use drop_job.sh to copy a job to the Pi.
"""
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze  # noqa: E402
import liverule as lr  # noqa: E402

# Creep steps, the 2026-11-08 steps, and a repeat of 126 at the end to measure drift.
DEFAULT_STEPS = [2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 80, 96, 112, 126, 126]
DEFAULT_WARM_STEP = 64
DEFAULT_WARM_LAPS = 3
GUARD = []  # sensors that abort the run if lit; set with --guard "BS W-1" (repeatable)
# Decoder families differ in their back-EMF CVs; the lists below are the CVs that exist in
# the roster entries of CSX 2121 (Tsunami 2) and CSX 2738 (TCS MC). Check the manual for
# any other decoder before trusting them.
BACKEMF = {"tsunami2": [209, 210, 211, 212, 213], "tcs": [49, 56, 57], "none": []}
BASE_CVS = [2, 3, 4, 5, 6, 25, 29, 66] + list(range(67, 95)) + [95]


def settings_text(d):
    return "".join("%s = %r\n" % (k, v) for k, v in d.items())


def build_steps(a, lengths):
    s = {
        "LOGF": a.log, "P_ID": a.loco, "P_FWD": a.direction == "forward",
        "FUNCS": [0] + ([8] if a.mute_sound else []),
        "GUARD": [], "REF": analyze.ORDER[0], "MID": "BS Switch 23a",
        "ORDER": analyze.ORDER, "LENGTHS": lengths,
        "STEPS_LIST": a.steps, "WARM_STEP": a.warm_step, "WARM_LAPS": a.warm_laps,
        "STOP_K": a.k, "STOP_REL": a.rel, "MAX_READINGS": a.max_n,
        "SETTLE_EVENTS": a.settle, "LOW_MAX": a.low_max, "HIGH_SPAN": a.high_span,
        "STALL0": a.stall, "STALL_SKIP_BELOW": 6, "STEP_MAX_S": a.step_max,
    }
    s["GUARD"] = [g for g in a.guard]
    body = (HERE / "liverule.py").read_text() + "\n" + (HERE / "jython" / "step_runner.py").read_text()
    return settings_text(s) + body


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
    st.add_argument("--steps", type=lambda x: [int(i) for i in x.split(",")], default=DEFAULT_STEPS)
    st.add_argument("--warm-laps", type=int, default=DEFAULT_WARM_LAPS)
    st.add_argument("--warm-step", type=int, default=DEFAULT_WARM_STEP)
    st.add_argument("--k", type=int, default=lr.STOP_K)
    st.add_argument("--rel", type=float, default=lr.STOP_REL)
    st.add_argument("--max", type=int, default=lr.MAX_READINGS, dest="max_n")
    st.add_argument("--settle", type=int, default=lr.SETTLE_EVENTS)
    st.add_argument("--low-max", type=int, default=lr.LOW_MAX)
    st.add_argument("--high-span", type=int, default=lr.HIGH_SPAN)
    st.add_argument("--stall", type=float, default=120.0, help="seconds without a sensor event")
    st.add_argument("--step-max", type=float, default=900.0, help="seconds allowed for one step")
    st.add_argument("--guard", action="append", default=list(GUARD))
    st.add_argument("--mute-sound", action="store_true", help="also switch F8 on (2121's mute)")
    st.add_argument("--lengths", default=str(analyze.DEFAULT_LENGTHS))
    st.add_argument("--trusted", default=",".join(analyze.DEFAULT_TRUSTED))
    st.add_argument("--log", help="log path on the Pi")
    pf = sub.add_parser("preflight", help="read the decoder's CVs on the programming track")
    pf.add_argument("--loco", required=True)
    pf.add_argument("--backemf", choices=sorted(BACKEMF), default="none")
    pf.add_argument("--cv-wait", type=float, default=20.0)
    pf.add_argument("--log", help="log path on the Pi")
    for p in (st, pf):
        p.add_argument("--out", required=True, help="job file to write")
    a = ap.parse_args(argv)
    tag = a.loco.replace(" ", "_")
    if a.job == "steps":
        a.log = a.log or "/tmp/steprun_%s_%s_%s.log" % (tag, a.direction, stamp)
        lengths = analyze.load_lengths(a.lengths, tuple(a.trusted.split(",")))
        if sum(v is not None for v in lengths.values()) == 0:
            sys.exit("no trusted block lengths: nothing to measure over (see --trusted)")
        text = build_steps(a, lengths)
    else:
        a.log = a.log or "/tmp/preflight_%s_%s.log" % (tag, stamp)
        text = build_preflight(a)
    Path(a.out).write_text(text)
    print("wrote %s (log on the Pi: %s)" % (a.out, a.log))


if __name__ == "__main__":
    main()
