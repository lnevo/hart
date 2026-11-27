"""build_panels.sh and its step list, the panels manifest (tools/pipeline/panels.toml, ADR-037): what the loader
refuses (the order, two writers, bad fields), the steps it runs, and what it says when one stops the run.

The script is run with a stand-in python3 on PATH that only records its arguments (and runs the real manifest.py), so
no build runs here.
"""
import contextlib
import importlib.util
import io
import os
import re
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple
from unittest import mock

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parents[1]
SCRIPT = HERE / "build_panels.sh"
WIKI = REPO / "wiki/pipelines/schematic-panels.md"
sys.path.insert(0, str(HERE))
if "pipeline_manifest" not in sys.modules:      # the name panel_stamps.py and check_stamps.py load it by
    _spec = importlib.util.spec_from_file_location("pipeline_manifest", REPO / "tools/pipeline/manifest.py")
    sys.modules["pipeline_manifest"] = importlib.util.module_from_spec(_spec)    # its dataclasses look it up there
    _spec.loader.exec_module(sys.modules["pipeline_manifest"])
M = sys.modules["pipeline_manifest"]

# (step, script and arguments, what --check adds, True when it only checks in both modes), in the manifest's order
STEPS = [(s.name, " ".join(s.cmd[1:]), " ".join(s.check_args), s.mode == "guard") for s in M.panel_steps()]
NAMES = [name for name, _cmd, _check, _only in STEPS]
FAKE_PYTHON = """#!/bin/sh
case "$1" in */panel_stamps.py) [ "$2" = current ] && exit 1; exit 0 ;; esac    # the stamps: nothing is current
case "$1" in */manifest.py)
  case "${MANIFEST_STUB:-}" in
    fail) echo "manifest.py: panels.toml: step 'x': mode: 'run' is not one of step, guard" >&2; exit 1 ;;
    empty) exit 0 ;;
    junk) echo "stop hands 1 --check python3 tools/schematic/build_hands.py"; exit 0 ;;
    nocmd) echo "step hands 1 --check python3"; exit 0 ;;
  esac
  exec "$REAL_PYTHON" "$@" ;;
esac
echo "$*" >> "$PANELS_LOG"
case "$1" in *"/$PANELS_FAIL") exit 1 ;; esac
case "$1" in *"/${PANELS_SAY_SKIPPED:-none}") echo "SKIPPED: the stand-in" ;; esac
exit 0
"""
GOOD = {"name": "a", "mode": "step", "cmd": ["python3", "tools/schematic/build_hands.py"], "check_args": ["--check"],
        "domain": "layout", "label": "a", "desc": "A."}


class Ran(NamedTuple):
    """One run of build_panels.sh: its exit code, stdout and stderr together, and the lines the stand-in logged."""
    code: int
    out: str
    ran: list[str]


def run_panels(tmp: Path, python: str, args: tuple[str, ...], env: Mapping[str, str],
               base: Mapping[str, str] | None = None) -> Ran:
    """build_panels.sh run from the repo with the shell script `python` as python3 on PATH. The stand-in logs to
    PANELS_LOG and finds the real interpreter in REAL_PYTHON; `env` goes over those, on `base` (default os.environ)."""
    fake = tmp / "python3"
    fake.write_text(python, encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    log = tmp / "log"
    log.touch()
    full = dict(os.environ if base is None else base, PATH=f"{tmp}{os.pathsep}{os.environ['PATH']}",
                PANELS_LOG=str(log), REAL_PYTHON=sys.executable)
    full.update(env)
    r = subprocess.run(["bash", str(SCRIPT), *args], cwd=REPO, env=full, capture_output=True, text=True)
    return Ran(r.returncode, r.stdout + r.stderr, log.read_text(encoding="utf-8").splitlines())


def entry(**fields):
    """A step for a stand-in manifest: GOOD with `fields` over it (None drops a field)."""
    out = {**GOOD, **fields}
    return {k: v for k, v in out.items() if v is not None}


def parse(*entries, where=None):
    return M.parse_panels({"step": list(entries)}, "t.toml", where)


class Manifest(unittest.TestCase):
    """The loader's checks of a panels manifest: it refuses, naming the file, the step and the field."""

    def assertRefused(self, entries, pattern, where=None):
        with self.assertRaisesRegex(M.ManifestError, pattern):
            parse(*entries, where=where)

    def test_the_repo_manifest_loads_against_git_and_the_map_and_alone(self):
        full = M.load_panels()
        self.assertEqual(full, M.panel_steps())
        self.assertEqual(len(full), 17)
        self.assertEqual(full[0].name, "hands")
        self.assertEqual(full[-1].name, "approved-live")

    def test_the_masts_step_only_reads_the_device_master(self):
        # build_masts.py writes masts.csv alone (hartlib.devices.WRITERS)
        sys.path.insert(0, str(REPO / "tools/hartlib/src"))
        from hartlib import devices
        masts = next(s for s in M.panel_steps() if s.name == "masts")
        self.assertEqual([o.path for o in masts.outputs], ["jmri/layouts/hart/data/schematic/masts.csv"])
        writers = [s.name for s in M.panel_steps() if f"jmri/layouts/hart/data/{devices.MASTER_FILE}"
                   in [o.path for o in s.outputs]]
        self.assertEqual(writers, ["device-map", "panel-items"])
        self.assertNotIn("build_masts.py", devices.WRITERS)

    def test_no_step_and_bad_fields(self):
        with self.assertRaisesRegex(M.ManifestError, r"t.toml: no \[\[step\]\] in it"):
            M.parse_panels({}, "t.toml", None)
        with self.assertRaisesRegex(M.ManifestError, "no panels step; make panels would run nothing"):
            M.panel_lines(())
        self.assertRefused([entry(mode="run")], r"t.toml: step 'a': mode: 'run' is not one of step, guard")
        self.assertRefused([entry(runner="panels")], r"step 'a': runner: not a field")
        self.assertRefused([entry(check_args=None)], r"step 'a': check_args: missing")
        self.assertRefused([entry(cmd=["python3", "tools/schematic/build_hands.py", "a b"])], r"split the line|splits")
        self.assertRefused([entry(cmd=["bash", "tools/x.sh"])], r"cmd: .* must be python3 and a script")
        self.assertRefused([entry(cmd=["python3", "tools/schematic/no_such.py"])], r"no_such.py is not a file")
        self.assertRefused([entry(), entry()], r"step 'a': name: also step 1's name")
        self.assertRefused([entry(inputs=[{"path": "x/../y"}])], r"inputs: x/\.\./y has an empty")
        for bad in ([1], [{"path": 1}], [{"label": "x"}]):      # a bad item is a ManifestError, not a crash
            self.assertRefused([entry(outputs=bad, updates=["a.csv"])], r"outputs: (1 is not a path|.*no path)")
        self.assertRefused([entry(outputs=[{"path": "a.csv", "written_later": ["b"]}])],
                           r"outputs: .*written_later not allowed here")

    def test_a_box_takes_its_text_from_its_first_step(self):
        self.assertRefused([entry(desc=None)], r"step 'a': desc: missing \(the first step drawn in box")
        self.assertRefused([entry(), entry(name="b", domain=None, desc=None)], r"step 'b': label: step 'a' gives box")
        two = parse(entry(), entry(name="b", domain=None, label=None, desc=None))
        self.assertEqual([s.box for s in two], ["tools/schematic/build_hands.py"] * 2)
        self.assertRefused([entry(), entry(name="b", cmd=["python3", "tools/schematic/build_masts.py"],
                                           box="tools/schematic/build_hands.py", domain=None, label=None, desc=None)],
                           r"step 'b': box: tools/schematic/build_hands.py is the box of step 'a', which runs")
        self.assertRefused([entry(box="tools/schematic/build_hands.py")], r"box: .* is the script cmd runs; drop box")

    def test_a_writer_comes_before_its_readers(self):
        later = {"domain": None, "label": None, "desc": None}    # a second step in one box takes the first's text
        parse(entry(name="w", outputs=["d/f.csv"]), entry(name="r", inputs=["d/f.csv"], **later))
        self.assertRefused([entry(name="r", inputs=[{"path": "d/f.csv", "label": "reads"}]),
                            entry(name="w", outputs=["d/f.csv"], **later)],
                           r"t.toml: step 'r' \(step 1\) reads d/f.csv, which 'w' writes later \(step 2\); run the "
                           r"writer first, or name it in the input's written_later")
        late = {"path": "d/f.csv", "written_later": ["w"]}
        parse(entry(name="r", inputs=[late]), entry(name="w", outputs=["d/f.csv"], **later))
        # a written_later name must be a step that writes the file after this one
        self.assertRefused([entry(name="w", outputs=["d/f.csv"]),
                            entry(name="r", inputs=[late], domain=None, label=None, desc=None)],
                           r"step 'r': inputs: d/f.csv: written_later names 'w', which does not write it after")
        self.assertRefused([entry(name="r", inputs=[{"path": "d/f.csv", "written_later": ["gone"]}])],
                           r"written_later names 'gone', no step")
        # a step that reads what it writes lists the file in updates
        self.assertRefused([entry(name="s", inputs=["d/f.csv"], outputs=["d/f.csv"])], r"'s' writes itself")
        parse(entry(name="s", inputs=["d/f.csv"], outputs=["d/f.csv"], updates=["d/f.csv"]))

    def test_two_writers_of_one_file_both_list_it_in_updates(self):
        a = entry(name="a", outputs=["d/f.csv"])
        b = entry(name="b", outputs=["d/*.csv"], domain=None, label=None, desc=None)
        self.assertRefused([a, b], r"steps 'a' and 'b' both write d/\*.csv; list it in both steps' updates")
        self.assertRefused([a | {"updates": ["d/f.csv"]}, b | {"outputs": ["d/f.csv"]}], r"'a' and 'b' both write")
        parse(a | {"updates": ["d/f.csv"]}, b | {"outputs": ["d/f.csv"], "updates": ["d/f.csv"]})
        self.assertRefused([entry(updates=["d/f.csv"])], r"updates: d/f.csv is not one of the step's outputs")

    def test_against_the_repo_paths_must_be_tracked_and_the_domain_a_map_domain(self):
        where = M.repo()
        self.assertRefused([entry(inputs=["no/such/file.csv"])], r"inputs: no/such/file.csv names no tracked file",
                           where=where)
        self.assertRefused([entry(domain="nowhere")], r"domain: 'nowhere' is not a map domain", where=where)
        self.assertRefused([entry(inputs=[{"path": "jmri/layouts/hart/data/wiring.csv", "side": "odd"}])],
                           r"side 'odd' is not a map edge side", where=where)

    def test_the_lines_build_panels_sh_reads(self):
        steps = parse(entry(), entry(name="g", mode="guard", check_args=[], domain=None, label=None, desc=None,
                                     cmd=["python3", "tools/schematic/build_hands.py", "--x"]))
        self.assertEqual(M.panel_lines(steps), ["step a 1 --check python3 tools/schematic/build_hands.py",
                                                "guard g 0 python3 tools/schematic/build_hands.py --x"])

    def test_the_command_line_reports_a_bad_manifest_without_a_traceback(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.toml"
            p.write_text('[[step]]\nname = "a"\nmode = "run"\n', encoding="utf-8")
            for argv in (("jobs", "panels"), ("check",)):
                with self.subTest(argv=argv):
                    out, err = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        rc = M.main(["--panels", str(p), *argv])
                    self.assertEqual((rc, out.getvalue()), (1, ""))
                    self.assertIn("bad.toml: step 'a': cmd: missing", err.getvalue())
                    self.assertNotIn("Traceback", err.getvalue())

    def test_the_file_is_toml_with_its_header_naming_every_field(self):
        text = M.PANELS.read_text(encoding="utf-8")
        tomllib.loads(text)
        header = text.split("\n[[step]]")[0]
        for key in M.PANEL_FIELDS:
            self.assertRegex(header, rf"(?m)^#   (?:\w+, )*{key}\b", key)

    def test_the_wiki_table_lists_the_steps_in_the_same_order(self):
        rows = re.findall(r"^\| ([a-z][a-z-]+) \| `([^`]+)` \|", WIKI.read_text(encoding="utf-8"), re.M)
        self.assertEqual(rows, [(name, cmd.rsplit('/', 1)[-1]) for name, cmd, _check, _only in STEPS])


class DryRun(unittest.TestCase):
    """The script itself, with python3 replaced by a recorder that fails for one named script."""

    def run_script(self, *args: str, fail: str = "", manifest: str = "", **extra: str) -> Ran:
        with tempfile.TemporaryDirectory() as tmp:
            timings = Path(tmp) / "timings" / "step-timings.tsv"     # the stub runs stay out of the real log
            got = run_panels(Path(tmp), FAKE_PYTHON, args, {
                "PANELS_FAIL": fail or "none", "HART_PANELS_OS": "Linux",    # no SML discovery here: SmlDiscovery
                "MANIFEST_STUB": manifest, "HART_STEP_TIMINGS_LOG": str(timings), **extra})
            self.timings = timings.read_text(encoding="utf-8").splitlines() if timings.exists() else []
            return got

    def test_a_write_logs_each_step_it_runs_and_a_check_logs_none(self):
        code, out, _ran = self.run_script(fail="build_signals.py")
        cols = [line.split("\t") for line in self.timings]
        self.assertEqual(code, 1, out)
        self.assertEqual([(c[1], c[2], c[4]) for c in cols],
                         [("panels", n, "ok") for n in NAMES[:NAMES.index("signals")]] + [("panels", "signals", "failed")])
        self.assertTrue(all(len(c) == 6 and c[3].isdigit() and c[5] in ("warm", "cold") for c in cols), cols)
        self.run_script(SCHEMATIC_CACHE="")
        self.assertEqual({line.split("\t")[5] for line in self.timings}, {"cold"})
        with tempfile.TemporaryDirectory() as cache:
            (Path(cache) / "solved").write_text("", encoding="utf-8")
            self.run_script("--full", SCHEMATIC_CACHE=cache)       # --full ignores the stamps, not the cache
        self.assertEqual({line.split("\t")[5] for line in self.timings}, {"warm"})
        self.run_script(PANELS_SAY_SKIPPED="build_signals.py")
        self.assertEqual([line.split("\t")[4] for line in self.timings if line.split("\t")[2] == "signals"],
                         ["skipped"])
        self.run_script("--check")
        self.assertEqual(self.timings, [])

    def test_a_write_runs_every_step_in_order(self):
        code, out, ran = self.run_script()
        self.assertEqual((code, ran), (0, [cmd for _n, cmd, _c, _o in STEPS]), out)
        self.assertIn("all current", out)

    def test_a_check_runs_every_step_with_check_and_names_each_stale_one(self):
        code, out, ran = self.run_script("--check", fail="sync_signals.py")
        self.assertEqual(ran, [f"{cmd} {check}".strip() for _n, cmd, check, _o in STEPS])
        self.assertTrue(all("--check" in line for line in ran), ran)    # every step only checks
        self.assertEqual(code, 1)
        self.assertIn("stale or failed: signals-sync\n", out)
        self.assertNotIn("stopped", out)

    def test_a_write_stops_at_a_failed_check_and_does_not_say_it_writes(self):
        # (plan-lengths runs plan_lengths.py, a guard: device-master stands in)
        for name, script in (("device-master", "check_device_master.py"), ("signals-sync", "sync_signals.py"),
                             ("sml-current", "check_sml_current.py")):
            with self.subTest(name):
                code, out, ran = self.run_script(fail=script)
                self.assertEqual((code, ran[-1].split()[0]), (1, f"tools/schematic/{script}"), out)
                self.assertEqual(len(ran), NAMES.index(name) + 1)
                self.assertIn(f"stopped: {name} only checks and it failed; later steps read the files it checks", out)
                self.assertNotIn("writes", out)

    def test_a_write_stops_at_a_failed_build(self):
        code, out, ran = self.run_script(fail="build_signals.py")
        self.assertEqual((code, len(ran)), (1, NAMES.index("signals") + 1), out)
        self.assertIn("stopped: later steps read what signals writes", out)

    def test_an_unknown_argument_is_refused(self):
        code, out, ran = self.run_script("--chek")
        self.assertEqual((code, ran), (2, []), out)

    def test_a_manifest_that_fails_lists_nothing_or_prints_junk_stops_before_any_step(self):
        for stub, said in (("fail", "jobs panels failed (its error is above); no step ran"),
                           ("empty", "jobs panels listed no step; no step ran"),
                           ("junk", 'printed "stop hands 1 --check python3 tools/schematic/build_hands.py", not a step '
                                    'line; no step ran'),
                           ("nocmd", 'printed "step hands 1 --check python3", with no command; no step ran')):
            for args in ((), ("--check",)):
                with self.subTest(stub=stub, args=args):
                    code, out, ran = self.run_script(*args, manifest=stub)
                    self.assertEqual((code, ran), (2, []), out)
                    self.assertIn(f"stopped: {'tools/pipeline/manifest.py ' if stub in ('fail', 'empty') else ''}"
                                  f"{'' if stub in ('fail', 'empty') else 'manifest.py '}{said}", out)
                    self.assertNotIn("all current", out)


# A python3 stand-in whose sml-current guard says stale (exit 4, check_sml_current.EXIT_STALE) until the stand-in
# discovery has run, and which fails it with SML_RC when that is set (1: a crash, 2: a build error; not staleness).
SML_PYTHON = """#!/bin/sh
case "$1" in */manifest.py) exec "$REAL_PYTHON" "$@" ;; esac
case "$1" in */panel_stamps.py) [ "$2" = current ] && exit 1; exit 0 ;; esac
echo "$*" >> "$PANELS_LOG"
case "$1" in */check_sml_current.py)
  [ -n "$SML_RC" ] && exit "$SML_RC"
  [ -f "$DISCOVERED" ] && exit 0
  exit 4 ;;
esac
exit 0
"""
FAKE_DISCOVER = """#!/bin/sh
echo "discover" >> "$PANELS_LOG"
[ -n "$DISCOVER_FAIL" ] && { echo "The Layout Editor panel is not the one the owner approved" >&2; exit 1; }
if [ -n "$SML_ALWAYS_STALE" ]; then touch "$DISCOVERED.once"; else touch "$DISCOVERED"; fi
exit 0
"""


class SmlDiscovery(unittest.TestCase):
    """A write on the Mac discovers when sml-current says stale, then checks again and goes on to tables. Off the
    Mac, in CI, while operating, in --check or on a build error it does not discover: the stale step stops the run."""

    def run_script(self, *args: str, os_name: str = "Darwin", operating: bool = False, lock_pid: int | str | None = None,
                   **extra: str) -> Ran:
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            discover = tmp / "discover.sh"
            discover.write_text(FAKE_DISCOVER, encoding="utf-8")
            flag = tmp / "operating"
            if operating:
                flag.write_text("by=owner\nsince=now\nreason=test\n", encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if k not in ("CI", "HART_SML_AUTO_DISCOVER", "HART_TABLES")}
            lock = tmp / "discover.lock"
            if lock_pid is not None:
                lock.mkdir()
                if lock_pid != "":
                    (lock / "pid").write_text(f"{lock_pid}\n", encoding="utf-8")
            got = run_panels(tmp, SML_PYTHON, args, {
                "DISCOVERED": str(tmp / "discovered"), "HART_PANELS_OS": os_name,
                "HART_SML_DISCOVER_CMD": str(discover), "HART_OPERATING_FLAG": str(flag),
                "HART_SML_DISCOVER_LOCK": str(lock), "HART_STEP_TIMINGS_LOG": "", **extra}, base=env)
            self.lock_left = lock.exists()
            return got

    def scripts(self, ran):
        return [line.split()[0].rsplit("/", 1)[-1] for line in ran]

    def test_a_stale_write_on_the_mac_discovers_checks_again_and_goes_on(self):
        code, out, ran = self.run_script()
        self.assertEqual(code, 0, out)
        got = self.scripts(ran)
        i = got.index("discover")
        self.assertEqual(got[i - 1:i + 3], ["check_sml_current.py", "discover", "check_sml_current.py",
                                             "build_tables.py"])
        self.assertEqual(got.count("discover"), 1)
        self.assertIn("sml-discover: ok", out)
        self.assertIn("all current", out)

    def test_a_discovered_retry_logs_sml_current_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            timings = Path(tmp) / "step-timings.tsv"
            code, out, _ran = self.run_script(HART_STEP_TIMINGS_LOG=str(timings))
            rows = [line.split("\t") for line in timings.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(code, 0, out)
        self.assertEqual([r[4] for r in rows if r[2] == "sml-current"], ["ok"])

    def test_it_discovers_once_and_stops_when_still_stale(self):
        code, out, ran = self.run_script(SML_ALWAYS_STALE="1")
        self.assertEqual(code, 1, out)
        got = self.scripts(ran)
        self.assertEqual(got.count("discover"), 1)
        self.assertEqual(got[-1], "check_sml_current.py")
        self.assertIn("stopped: sml-current only checks and it failed", out)

    def test_a_failed_discovery_stops_with_its_message(self):
        code, out, ran = self.run_script(DISCOVER_FAIL="1")
        self.assertEqual(code, 1, out)
        self.assertEqual(self.scripts(ran)[-1], "discover")
        self.assertIn("not the one the owner approved", out)
        self.assertIn("stopped: SML discovery failed", out)
        self.assertNotIn("build_tables.py", "\n".join(ran))

    def test_where_it_does_not_discover_it_stops_and_says_why(self):
        cases = {
            "off the Mac": (dict(os_name="Linux"), "discovery runs PanelPro on the Mac, and this is Linux"),
            "CI": (dict(CI="true"), "this is CI"),
            "operating": (dict(operating=True), "the operating flag is set"),
            "turned off": (dict(HART_SML_AUTO_DISCOVER="0"), "HART_SML_AUTO_DISCOVER=0"),
            "turned off with false": (dict(HART_SML_AUTO_DISCOVER="false"), "HART_SML_AUTO_DISCOVER=false"),
            "HART_TABLES": (dict(HART_TABLES="/elsewhere/tables.xml"), "HART_TABLES is set"),
            "another run discovering": (dict(lock_pid=os.getpid()), f"another make panels (pid {os.getpid()})"),
            "another run starting": (dict(lock_pid=""), "another make panels is starting a discovery"),
        }
        for label, (kw, why) in cases.items():
            with self.subTest(label):
                code, out, ran = self.run_script(**kw)
                self.assertEqual(code, 1, out)
                self.assertNotIn("discover", self.scripts(ran))
                self.assertIn(f"not discovering here: {why}", out)
                self.assertIn("stopped: sml-current only checks and it failed", out)

    def test_a_build_error_or_a_crash_is_not_staleness(self):
        for rc in ("1", "2"):
            with self.subTest(rc):
                code, out, ran = self.run_script(SML_RC=rc)
                self.assertEqual(code, 1, out)
                self.assertNotIn("discover", self.scripts(ran))
                self.assertNotIn("not discovering", out)

    def test_the_lock_is_released_and_a_dead_holder_is_taken_over(self):
        code, out, _ran = self.run_script()
        self.assertEqual(code, 0, out)
        self.assertFalse(self.lock_left)
        dead = subprocess.run(["sh", "-c", "echo $$"], capture_output=True, text=True).stdout.strip()
        code, out, ran = self.run_script(lock_pid=int(dead))
        self.assertEqual(code, 0, out)
        self.assertIn("taking over", out)
        self.assertEqual(self.scripts(ran).count("discover"), 1)
        self.assertFalse(self.lock_left)
        code, out, _ran = self.run_script(DISCOVER_FAIL="1")
        self.assertFalse(self.lock_left, out)

    def test_a_check_never_discovers(self):
        code, out, ran = self.run_script("--check")
        self.assertEqual(code, 1, out)
        self.assertNotIn("discover", self.scripts(ran))
        self.assertIn("stale or failed: sml-current\n", out)


# A python3 stand-in that runs the real sync_signals.py against a stale copy of masts.csv (a temp
# file: the repo's data files are only read) and answers every other script with success.
STALE_SYNC_PYTHON = """#!/bin/sh
case "$1" in */manifest.py) exec "$REAL_PYTHON" "$@" ;; esac
case "$1" in
  */panel_stamps.py) [ "$2" = current ] && exit 1; exit 0 ;;
  */sync_signals.py) shift; exec "$REAL_PYTHON" "$STALE_RUNNER" "$SCHEMATIC_DIR" "$STALE_CSV" "$@" ;;
esac
echo "$*" >> "$PANELS_LOG"
exit 0
"""
STALE_RUNNER = """import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import sync_signals as sss
_want = sss.want_masts
sss.want_masts = lambda: _want(Path(sys.argv[2]))  # the default path is bound at import
sys.exit(sss.main(sys.argv[3:]))
"""


class StaleMastsCsv(unittest.TestCase):
    """build_panels.sh with the real sync_signals.py --check and a masts.csv missing its last mast,
    so tables.xml holds a staging mast the file does not: the check fails, and the run says so in both modes."""

    def run_script(self, *args: str, whole: bool = False) -> Ran:
        import staging_device_map as sdm
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            current = sdm.MASTS
            lines = current.read_text(encoding="utf-8").splitlines(keepends=True)
            stale = tmp / "masts.csv"
            stale.write_text("".join(lines[:-1]), encoding="utf-8")
            (tmp / "runner.py").write_text(STALE_RUNNER, encoding="utf-8")
            return run_panels(tmp, STALE_SYNC_PYTHON, args, {
                "STALE_RUNNER": str(tmp / "runner.py"), "SCHEMATIC_DIR": str(HERE),
                "STALE_CSV": str(current if whole else stale), "HART_STEP_TIMINGS_LOG": ""})

    def test_the_unmodified_file_passes_so_the_dropped_row_is_the_cause(self):
        code, out, _ran = self.run_script("--check", whole=True)
        self.assertEqual(code, 0, out)
        self.assertIn("follow masts.csv", out)

    def test_a_write_stops_at_the_stale_file_and_names_the_fix(self):
        code, out, ran = self.run_script()
        self.assertEqual(code, 1, out)
        self.assertIn("differs from masts.csv", out)
        self.assertIn("run tools/schematic/build_masts.py, then tools/schematic/build_tables.py", out)
        self.assertIn("stopped: signals-sync only checks and it failed; later steps read the files it checks", out)
        self.assertEqual(len(ran), NAMES.index("signals-sync"), ran)  # nothing after it ran

    def test_a_check_names_the_stale_step_and_never_says_it_stopped(self):
        code, out, ran = self.run_script("--check")
        self.assertEqual(code, 1, out)
        self.assertIn("differs from masts.csv", out)
        self.assertIn("stale or failed: signals-sync\n", out)
        self.assertNotIn("stopped", out)
        self.assertNotIn("later steps read what", out)
        self.assertEqual(len(ran), len(NAMES) - 1, ran)  # every other step still ran


class MissingPlugin(unittest.TestCase):
    """build_masts.py without the plugin submodule: a message, not a traceback."""

    def run_main(self, argv, required=""):
        import build_masts as bsm
        import publish_draft as pd

        def gone():
            raise pd.PluginMissing("schematic-maps plugin not found: run git submodule update --init "
                                   "external/model-railroad-skills")
        bsm.sdm.lc.plugin.cache_clear()
        self.addCleanup(bsm.sdm.lc.plugin.cache_clear)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(pd, "plugin", gone), mock.patch.dict(os.environ, {"SCHEMATIC_REQUIRED": required}), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = bsm.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_check_is_skipped_and_fails_only_when_required(self):
        code, out, _err = self.run_main(["--check"])
        self.assertEqual(code, 0)
        self.assertIn("SKIPPED masts check: schematic-maps plugin not found: run git submodule update", out)
        self.assertEqual(self.run_main(["--check"], required="1")[0], 1)

    def test_a_write_and_show_name_the_fault(self):
        for argv in ([], ["--show"]):
            code, _out, err = self.run_main(argv)
            self.assertEqual(code, 2)
            self.assertIn("build_masts.py: schematic-maps plugin not found", err)


if __name__ == "__main__":
    unittest.main()
