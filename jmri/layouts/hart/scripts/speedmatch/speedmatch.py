#!/usr/bin/env python3
"""One command for the speed-matching tools (docs/jmri/speedmatching/RUNBOOK.md).

    speedmatch.py job ARGS...         make_job.py: build a job file (nothing is sent)
    speedmatch.py drop ARGS...        drop_job.sh: send a job to the Pi, --fetch a log, --kill a runner
    speedmatch.py pom PROPOSAL ...    build a POM write drop for pom_write.py; --send hands it to drop_job.sh
    speedmatch.py compare preflight ARGS...   preflight_compare.py: preflight CVs against the roster
    speedmatch.py compare stoptest ARGS...    stoptest_compare.py: two stop-test logs side by side
    speedmatch.py to-roster ARGS...   profile_to_roster.py: profile.csv to a write_profile.py payload
    speedmatch.py lengths ARGS...     infer_block_lengths.py: block lengths from timed laps and the plan
    speedmatch.py rename-ext ARGS...  rename_extension_tracks.py: old extension-track names in logs
    speedmatch.py ledger-dir          the Pi's POM ledger folder: pass it as --ledger-dir to pom_guard.py

`make speedmatch ARGS="job steps --loco 'CSX 2738' --out /tmp/job.py"` runs the same. Every subcommand but pom
runs its script with the arguments as given, so each script's own --help and behaviour are unchanged.

pom replaces the hand procedure that POM_GUARD.md used to give. It checks the proposal with pom_guard.py on the
Mac, then writes one drop file: the settings pom_write.py reads, the files it needs on the Pi (pom_guard.py,
pom_guard_roster.py, pom_guard_cli.py, cs105_consist.py and the proposal, unpacked into /tmp/speedmatch before the
writer starts), and pom_write.py itself. Nothing reaches the Pi unless --send is given, and then only through drop_job.sh, with its
gates: no job while the owner is operating, the operating flag set for the run, nothing while another command
waits, a runner is active (/tmp/speedrun.active) or a kill flag is left (/tmp/speedrun.kill). Never --force.
The Pi's home folder (ledger, rollback files) is the parent of HART_PI_USERFILES, read as tools/env/load_env.sh
reads it (environment, then hart.env, then defaults.env).
"""
import argparse
import base64
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
SCRIPTS = HERE.parent
LOAD_ENV = ROOT / "tools/env/load_env.sh"
DROP_JOB = HERE / "drop_job.sh"
WRITER = HERE / "pom_write.py"
GUARD = HERE / "pom_guard.py"
# Each subcommand that only runs a script: (interpreter, script). compare picks one by its first argument.
PASS = {
    "job": (sys.executable, HERE / "make_job.py"),
    "drop": ("bash", DROP_JOB),
    "to-roster": (sys.executable, HERE / "profile_to_roster.py"),
    "lengths": (sys.executable, SCRIPTS / "infer_block_lengths.py"),
    "rename-ext": (sys.executable, HERE / "rename_extension_tracks.py"),
}
COMPARE = {
    "preflight": (sys.executable, HERE / "preflight_compare.py"),
    "stoptest": (sys.executable, HERE / "stoptest_compare.py"),
}
# What the Pi needs next to the writer: the guard and its part pom_guard_roster.py (the guard imports it), the
# guard's command line (for the ledger steps a STOPPED line names) and the consist query.
POM_FILES = (GUARD, HERE / "pom_guard_roster.py", HERE / "pom_guard_cli.py", SCRIPTS / "cs105_consist.py")
PI_DIR = "/tmp/speedmatch"   # the Pi's /tmp, as drop_job.sh and the runners use it
POM_LOG = "/tmp/pom_write.log"
# The line drop_job.sh looks for (grep speedrun.active) before it runs its runner checks on a job.
RUNNER_MARK = "# drop_job.sh refuses this while /tmp/speedrun.active or /tmp/speedrun.kill exists on the Pi"
ROLLBACK_NAME = re.compile(r"^[A-Za-z0-9_.-]+\.json$")


def run_script(interpreter, script, args):
    return subprocess.call([interpreter, str(script)] + list(args))


def pi_userfiles():
    """HART_PI_USERFILES as load_env.sh resolves it (the one place the order is defined)."""
    done = subprocess.run(["bash", "-c", 'source "$1" >/dev/null && printf %s "$HART_PI_USERFILES"', "_",
                           str(LOAD_ENV)], capture_output=True, text=True)
    value = done.stdout.strip()
    if done.returncode != 0 or not value.startswith("/"):
        sys.exit("speedmatch pom: HART_PI_USERFILES not found through %s: %s" % (LOAD_ENV, done.stderr.strip()))
    return value


def pi_home():
    """The Pi's home folder: the parent of HART_PI_USERFILES (its ~/speedmatch holds the ledger and rollbacks)."""
    return os.path.dirname(pi_userfiles().rstrip("/"))


def ledger_dir(home=None):
    """The one ledger folder: the writer's LEDGER_DIR and every pom_guard.py ledger command's --ledger-dir."""
    return (home or pi_home()) + "/speedmatch/ledger"


def load_guard():
    sys.path.insert(0, str(HERE))
    import pom_guard
    return pom_guard


def pom_text(proposal_path, a, home):
    """The drop file: settings, the Pi's support files, then pom_write.py unchanged."""
    raw = Path(proposal_path).read_bytes()
    settings = [
        ("PROPOSAL", a.pi_dir + "/proposal.json"),
        ("GUARD_PATH", a.pi_dir + "/pom_guard.py"),
        ("CONSIST_SCRIPT", a.pi_dir + "/cs105_consist.py"),
        ("ABSENT_OK", list(a.absent_ok)),
        ("CONSISTS_BROKEN", a.consists_broken),
        ("ROSTER_OLD_OK", a.roster_old_ok),
        ("LOGF", a.log),
        ("ROLLBACK", home + "/speedmatch/" + a.rollback),
        ("LEDGER_DIR", ledger_dir(home)),
        ("APPLY", a.apply),
        ("READ_FIRST", not a.no_read_first),
    ]
    files = [(p.name, p.read_bytes()) for p in POM_FILES] + [("proposal.json", raw)]
    out = ["# pom_write drop, made by speedmatch.py pom from %s at %s. %s" % (
               Path(proposal_path).name, time.strftime("%Y-%m-%dT%H:%M:%S"),
               "APPLY: it writes CVs" if a.apply else "dry run: it reads and plans, never writes"),
           RUNNER_MARK]
    out += ["%s = %r" % (k, v) for k, v in settings]
    out += ["", "# The files pom_write.py needs, unpacked into %s before it starts." % a.pi_dir,
            "import base64 as _pom_b64",
            "import os as _pom_os",
            "_POM_DIR = %r" % a.pi_dir,
            "_POM_FILES = ["]
    out += ["    (%r, %r)," % (name, base64.b64encode(data).decode("ascii")) for name, data in files]
    out += ["]",
            "for _pom_d in (_POM_DIR, LEDGER_DIR):",
            "    if not _pom_os.path.isdir(_pom_d):",
            "        _pom_os.makedirs(_pom_d)",
            "for _pom_name, _pom_data in _POM_FILES:",
            "    _pom_f = open(_pom_os.path.join(_POM_DIR, _pom_name), 'wb')",
            "    try:",
            "        _pom_f.write(_pom_b64.b64decode(_pom_data))",
            "    finally:",
            "        _pom_f.close()",
            "", "# ---- pom_write.py", ""]
    return "\n".join(out) + "\n" + WRITER.read_text()


def pom(argv):
    # allow_abbrev=False: --send is spelt out, so .claude/hooks/main_guard.py sees every send
    ap = argparse.ArgumentParser(prog="speedmatch.py pom", allow_abbrev=False, description="Build a POM write drop for the Pi's "
                                 "pom_write.py; --send hands it to drop_job.sh.")
    ap.add_argument("proposal", help="proposal JSON (schema in pom_guard.py); a rollback file works the same")
    ap.add_argument("--apply", action="store_true", help="write the CVs (default: a dry run)")
    ap.add_argument("--consists-broken", action="store_true",
                    help="every consist with this loco is broken, leads outside the roster included (apply needs it)")
    ap.add_argument("--roster-old-ok", action="store_true",
                    help="an apply may take old values from the roster (they may be defaults)")
    ap.add_argument("--absent-ok", action="append", default=[], metavar="ROSTER_ID",
                    help="a roster loco whose train node may not answer: only one that is not on the layout")
    ap.add_argument("--rollback", help="rollback file name in the Pi's ~/speedmatch (default "
                    "rollback_<loco>_<time>.json); it must not exist there yet")
    ap.add_argument("--no-read-first", action="store_true", help="skip the POM read of the old values")
    ap.add_argument("--out", default="/tmp/pom_drop.py", help="the drop file (default %(default)s)")
    ap.add_argument("--send", action="store_true", help="send it with drop_job.sh (its gates apply)")
    ap.add_argument("--pi-dir", default=PI_DIR, help=argparse.SUPPRESS)   # tests
    ap.add_argument("--log", default=POM_LOG, help=argparse.SUPPRESS)     # tests
    a = ap.parse_args(argv)
    if a.apply and not a.consists_broken:
        ap.error("--apply needs --consists-broken: break every consist with this loco first")
    guard = load_guard()
    try:
        rid, _ = guard.validate_proposal(guard.load_proposal(a.proposal))
    except guard.GuardRefusal as e:
        print("REFUSED %s" % e)
        return 2
    if not all(isinstance(x, str) and x.isascii() for x in [rid] + a.absent_ok):
        ap.error("roster ids must be plain ASCII (the drop file is Jython 2 source)")
    a.rollback = a.rollback or "rollback_%s_%s.json" % (guard.safe_name(rid), time.strftime("%Y%m%dT%H%M%S"))
    if not ROLLBACK_NAME.match(a.rollback):
        ap.error("--rollback is a file name ending in .json, not a path: %r" % a.rollback)
    home = pi_home()
    Path(a.out).write_text(pom_text(a.proposal, a, home))
    print("wrote %s: %s for %r, rollback %s/speedmatch/%s, ledger %s" % (
        a.out, "APPLY" if a.apply else "dry run", rid, home, a.rollback, ledger_dir(home)))
    print("ledger commands on the Pi: python3 %s/pom_guard.py clear-ledger|seed-ledger|archive-ledger ... "
          "--ledger-dir %s" % (a.pi_dir, ledger_dir(home)))
    if not a.send:
        print("send it with: speedmatch.py pom ... --send, or speedmatch.py drop %s" % a.out)
        return 0
    rc = run_script("bash", DROP_JOB, [a.out])
    if rc == 0:
        print("then: speedmatch.py drop --fetch %s until its last line is END, and clear the operating flag "
              "(tools/hosts/operating.sh off)" % a.log)
    return rc


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd in PASS:
        return run_script(*PASS[cmd], rest)
    if cmd == "compare":
        if not rest or rest[0] not in COMPARE:
            print("speedmatch.py compare preflight|stoptest ARGS...", file=sys.stderr)
            return 2
        return run_script(*COMPARE[rest[0]], rest[1:])
    if cmd == "ledger-dir":
        print(ledger_dir())
        return 0
    if cmd == "pom":
        return pom(rest)
    print("speedmatch.py: no subcommand %r (speedmatch.py --help lists them)" % cmd, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
