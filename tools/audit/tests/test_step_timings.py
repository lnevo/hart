"""tools/pipeline/timings.py and tools/pipeline/step_timings.sh: the log lines the runners append, the summary made
from them (medians, skip rate, the steps the manifests no longer name), its bytes, the seed and --check."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("pipeline_timings", ROOT / "tools/pipeline/timings.py")
assert _spec is not None and _spec.loader is not None
T = importlib.util.module_from_spec(_spec)
sys.modules["pipeline_timings"] = T      # its dataclasses look the module up by name
_spec.loader.exec_module(T)
HELPER = ROOT / "tools/pipeline/step_timings.sh"


def line(step="hands", secs="4", result="ok", mode="warm", runner="panels", when="2026-11-25T10:00:00Z"):
    return "\t".join((when, runner, step, secs, result, mode))


class Parse(unittest.TestCase):
    def test_a_line_reads_as_a_run(self):
        self.assertEqual(T.parse_line(line() + "\n"), T.Run("2026-11-25", "panels", "hands", 4.0, "ok", "warm"))
        self.assertEqual(T.parse_line(line(secs="", mode="", result="failed", runner="check")),
                         T.Run("2026-11-25", "check", "hands", None, "failed", ""))

    def test_bad_lines_are_counted_not_read(self):
        bad = [line(runner="make"), line(result="passed"), line(mode="hot"), line(secs="x"), line(secs="-1"),
               line(step="Has Space"), line(step="/Users/me/x"), line(when="yesterday"), "a\tb", line() + "\textra"]
        runs, n = T.parse_log("\n".join([line(), "", *bad, line(step="cats")]) + "\n")
        self.assertEqual(([r.step for r in runs], n), (["hands", "cats"], len(bad)))


class Summarize(unittest.TestCase):
    def runs(self, *lines):
        return T.parse_log("\n".join(lines))[0]

    def test_medians_per_mode_from_ok_runs_only(self):
        runs = self.runs(line(secs="4"), line(secs="6"), line(secs="100"), line(secs="9", result="failed"),
                         line(secs="0", result="skipped"), line(secs="30", mode="cold"),
                         line(secs="41", mode="cold"), line(secs="7", mode=""))
        s = T.summarize(runs)["steps"]["panels:hands"]
        self.assertEqual((s["warm_s"], s["cold_s"], s["runs"]), (6.0, 35.5, 8))

    def test_no_run_in_a_mode_is_null(self):
        s = T.summarize(self.runs(line(mode="cold", secs="3.14159")))["steps"]["panels:hands"]
        self.assertEqual((s["warm_s"], s["cold_s"]), (None, 3.1))

    def test_skip_rate_and_last_day(self):
        runs = self.runs(line(result="skipped", when="2026-11-26T01:00:00Z"), line(), line(result="skipped"))
        s = T.summarize(runs)["steps"]["panels:hands"]
        self.assertEqual((s["skip_rate"], s["last"]), (0.67, "2026-11-26"))

    def test_runners_are_kept_apart_and_unknown_steps_left_out(self):
        runs = self.runs(line(), line(runner="check", step="panels-hands", when="2026-11-24T00:00:00Z"),
                         line(step="gone"))
        out = T.summarize(runs, known={"panels:hands", "check:panels-hands"})
        self.assertEqual(sorted(out["steps"]), ["check:panels-hands", "panels:hands"])
        self.assertEqual((out["updated"], out["source"]), ("2026-11-25", "step-timings log"))

    def test_same_runs_in_any_order_give_the_same_bytes(self):
        lines = [line(step=s, secs=str(i), mode=m, when=f"2026-11-2{i % 6}T00:00:00Z")
                 for i, (s, m) in enumerate([(s, m) for s in ("a", "b", "c") for m in ("warm", "cold")] * 3)]
        first = T.render(T.summarize(self.runs(*lines)))
        random.Random(1).shuffle(lines)
        self.assertEqual(T.render(T.summarize(self.runs(*lines))), first)
        self.assertEqual(list(json.loads(first)), ["source", "steps", "updated"])     # sorted keys

    def test_the_summary_holds_no_path_or_name_beyond_steps(self):
        text = T.render(T.summarize(self.runs(line(), line(runner="check", step="ruff"))))
        self.assertNotIn("/", text.replace('"source": "step-timings log"', ""))


class Seed(unittest.TestCase):
    def test_the_seed_is_the_timed_cold_rebuild_and_names_real_steps(self):
        s = T.seed()
        self.assertEqual({k: v["cold_s"] for k, v in s["steps"].items()},
                         {"panels:plan-lengths": 37.0, "panels:schematic": 38.0, "panels:sml-current": 343.0,
                          "panels:cats": 4.0, "panels:tables": 2.0})
        self.assertTrue(all(v["warm_s"] is None and v["runs"] == 1 for v in s["steps"].values()))
        self.assertEqual(T.unknown_steps(s, T.known_steps()), [])

    def test_summarize_seeds_only_when_there_is_no_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            log, out = Path(tmp) / "log.tsv", Path(tmp) / "t.json"
            log.write_text("", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(T.main(["summarize", "--log", str(log), "--out", str(out)]), 0)
                self.assertEqual(json.loads(out.read_text())["source"], "efficiency-plan.md")
                out.write_text("{}\n", encoding="utf-8")
                T.main(["summarize", "--log", str(log), "--out", str(out)])
                self.assertEqual(out.read_text(), "{}\n")      # an empty log keeps what is there
                log.write_text(line(step="schematic") + "\n", encoding="utf-8")
                T.main(["summarize", "--log", str(log), "--out", str(out)])
                self.assertEqual(list(json.loads(out.read_text())["steps"]), ["panels:schematic"])
                kept = out.read_text()
                log.write_text(line(step="renamed-away") + "\n", encoding="utf-8")
                T.main(["summarize", "--log", str(log), "--out", str(out)])
            self.assertEqual(out.read_text(), kept)      # no run of a manifest step: kept, as for an empty log


class Check(unittest.TestCase):
    def run_check(self, summary):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "t.json"
            out.write_text(json.dumps(summary), encoding="utf-8")
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                return T.main(["--check", "--out", str(out)]), err.getvalue()

    def test_known_steps_follow_both_manifests(self):
        known = T.known_steps()
        self.assertTrue({"panels:sml-current", "check:ruff", "check:panels-schematic"} <= known)
        self.assertNotIn("check:panels", known)      # the panels step runs as one job per panels step

    def test_known_from_expands_the_step_that_runs_make_panels(self):
        known = T.known_from([{"name": "ruff", "cmd": ["python3", "x"]}, {"name": "panels", "cmd": ["bash", "p"]}],
                             [{"name": "hands"}], lambda cmd: cmd[:1] == ["bash"], "panels-")
        self.assertEqual(known, {"panels:hands", "check:ruff", "check:panels-hands"})

    def test_a_step_no_manifest_names_fails(self):
        entry = {"runner": "panels", "step": "renamed-away"}
        rc, err = self.run_check({"steps": {"panels:renamed-away": entry}})
        self.assertEqual(rc, 1)
        self.assertIn("panels:renamed-away: no such step", err)

    def test_a_key_that_does_not_match_its_entry_fails(self):
        rc, err = self.run_check({"steps": {"panels:cats": {"runner": "check", "step": "cats"}}})
        self.assertEqual(rc, 1)
        self.assertIn("do not match", err)

    def test_the_committed_summary_passes(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(T.main(["--check"]), 0)


class Shell(unittest.TestCase):
    """step_timings.sh as the runners source it."""

    def bash(self, script, **env):
        full = {**{k: v for k, v in os.environ.items() if k != "HART_STEP_TIMINGS_LOG"}, **env}
        return subprocess.run(["bash", "-c", f'source "{HELPER}"; {script}'], env=full, capture_output=True,
                              text=True, cwd=ROOT)

    def test_lines_it_appends_read_back_as_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "new" / "step-timings.tsv"
            r = self.bash('step_timings_open "$PWD"; step_timing panels hands 3 ok warm; '
                          'step_timing check ruff "" failed ""', HART_STEP_TIMINGS_LOG=str(log))
            self.assertEqual(r.returncode, 0, r.stderr)
            runs, bad = T.parse_log(log.read_text(encoding="utf-8"))
        self.assertEqual(bad, 0)
        self.assertEqual([(r.runner, r.step, r.seconds, r.result, r.mode) for r in runs],
                         [("panels", "hands", 3.0, "ok", "warm"), ("check", "ruff", None, "failed", "")])

    def test_a_log_it_cannot_write_or_one_turned_off_fails_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocked = Path(tmp) / "file"
            blocked.write_text("", encoding="utf-8")
            err = Path(tmp) / "cache" / "step-timings.err"
            for value, errs in ((str(blocked / "sub" / "log.tsv"), 1), ("", 0), ("   ", 0)):
                with self.subTest(value=value):
                    err.unlink(missing_ok=True)
                    r = self.bash('step_timings_open "$PWD" panels; step_timing panels hands 1 ok warm; echo done',
                                  HART_STEP_TIMINGS_LOG=value, HART_CACHE_DIR=f"{tmp}/cache")
                    self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "done\n", ""))
                    lines = err.read_text(encoding="utf-8").splitlines() if err.exists() else []
                    self.assertEqual(len(lines), errs, lines)
                    self.assertTrue(all(line.split("\t")[1] == "panels" for line in lines), lines)

    def test_a_log_named_with_spaces_and_tilde_is_the_file_under_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = self.bash('step_timings_open "$PWD" panels; step_timing panels hands 2 ok warm',
                          HART_STEP_TIMINGS_LOG="  ~/logs/t.tsv \t", HOME=tmp, HART_CACHE_DIR=f"{tmp}/cache")
            self.assertEqual((r.returncode, r.stderr), (0, ""))
            runs, _ = T.parse_log((Path(tmp) / "logs/t.tsv").read_text(encoding="utf-8"))
            with mock.patch.dict(os.environ, {"HART_STEP_TIMINGS_LOG": "  ~/logs/t.tsv ", "HOME": tmp}):
                self.assertEqual(T.default_log(), Path(tmp) / "logs/t.tsv")
            with mock.patch.dict(os.environ, {"HART_STEP_TIMINGS_LOG": "   "}):
                self.assertIsNone(T.default_log())
        self.assertEqual([r.step for r in runs], ["hands"])

    def test_check_sh_jobs_are_read_from_its_job_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs, log = Path(tmp) / "jobs", Path(tmp) / "log.tsv"
            jobs.mkdir()
            (jobs / "0.skip").write_text("", encoding="utf-8")
            for i, rc, secs in ((1, "0", "12"), (2, "1", "3"), (3, "0", "9"), (4, "0", "2")):
                (jobs / f"{i}.rc").write_text(rc + "\n", encoding="utf-8")
                (jobs / f"{i}.time").write_text(secs + "\n", encoding="utf-8")
                (jobs / f"{i}.log").write_text("SKIPPED: no plugin\n" if i == 4 else "fine\n", encoding="utf-8")
            r = self.bash(f'step_timings_jobs "$PWD" "{jobs}" " ruff mypy panels-cats layout-docs " ruff mypy '
                          f'panels-cats "unit-jmri test_x" layout-docs', HART_STEP_TIMINGS_LOG=str(log),
                          SCHEMATIC_CACHE="")
            self.assertEqual(r.returncode, 0, r.stderr)
            runs, bad = T.parse_log(log.read_text(encoding="utf-8"))
        self.assertEqual((bad, len({r.day for r in runs})), (0, 1))
        self.assertEqual([(r.step, r.seconds, r.result, r.mode) for r in runs],
                         [("ruff", 0.0, "skipped", "cold"), ("mypy", 12.0, "ok", "cold"),
                          ("panels-cats", 3.0, "failed", "cold"), ("layout-docs", 2.0, "skipped", "cold")])

    def test_a_log_it_cannot_write_leaves_one_err_line_and_the_run_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache, jobs = Path(tmp) / "cache", Path(tmp) / "jobs"
            jobs.mkdir()
            for i in (0, 1):
                (jobs / f"{i}.rc").write_text("0\n", encoding="utf-8")
                (jobs / f"{i}.time").write_text("5\n", encoding="utf-8")
            locked = Path(tmp) / "locked"
            locked.mkdir()
            locked.chmod(0o500)
            folder_log = Path(tmp) / "a-folder"
            folder_log.mkdir()
            try:
                for log, said in ((locked / "sub" / "log.tsv", "cannot make the log's folder"),
                                  (folder_log, "cannot append to")):
                    with self.subTest(said):
                        err = cache / "step-timings.err"
                        err.unlink(missing_ok=True)
                        r = self.bash(f'step_timings_jobs "$PWD" "{jobs}" " ruff mypy " ruff mypy; echo rc=$?',
                                      HART_STEP_TIMINGS_LOG=str(log), HART_CACHE_DIR=str(cache))
                        self.assertEqual((r.stdout, r.stderr), ("rc=0\n", ""))
                        lines = err.read_text(encoding="utf-8").splitlines()
                        self.assertEqual(len(lines), 1, lines)       # once per run, not once per job
                        when, runner, what = lines[0].split("\t")
                        self.assertRegex(when, T.TIME_RE)
                        self.assertEqual(runner, "check")
                        self.assertIn(said, what)
            finally:
                locked.chmod(0o700)

    def test_a_helper_that_does_not_source_leaves_an_err_line_and_make_panels_unchanged(self):
        guard = (ROOT / "tools/hosts/profile_tables_guard.sh").read_text(encoding="utf-8")
        fake = ('#!/bin/sh\ncase "$1" in */manifest.py) echo "step hands 1 --check python3 tools/x.py"; exit 0 ;; '
                '*/panel_stamps.py) [ "$2" = current ] && exit 1 ;; esac\nexit 0\n')
        runs = {}
        for helper in ("good", "broken"):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "repo"
                for rel, text in (("tools/schematic/build_panels.sh", (ROOT / "tools/schematic/build_panels.sh")
                                   .read_text(encoding="utf-8")), ("tools/hosts/profile_tables_guard.sh", guard),
                                  ("tools/pipeline/step_timings.sh", HELPER.read_text(encoding="utf-8")
                                   if helper == "good" else "step_timings_open() { :; }\nif then fi\n")):
                    (root / rel).parent.mkdir(parents=True, exist_ok=True)
                    (root / rel).write_text(text, encoding="utf-8")
                subprocess.run(["git", "init", "-q", str(root)], check=True)
                (Path(tmp) / "python3").write_text(fake, encoding="utf-8")
                (Path(tmp) / "python3").chmod(0o755)
                env = {**{k: v for k, v in os.environ.items() if k != "HART_STEP_TIMINGS_LOG"},
                       "PATH": f"{tmp}{os.pathsep}{os.environ['PATH']}", "HART_CACHE_DIR": f"{tmp}/cache",
                       "SCHEMATIC_CACHE": ""}
                r = subprocess.run(["bash", "tools/schematic/build_panels.sh"], cwd=root, env=env,
                                   capture_output=True, text=True)
                cache = Path(tmp) / "cache"
                runs[helper] = (r.returncode, re.sub(r"\d+ s\b", "N s", r.stdout), r.stderr,
                                {p.name: p.read_text(encoding="utf-8") for p in cache.glob("step-timings.*")})
        self.assertEqual(runs["good"][:3], runs["broken"][:3])
        self.assertEqual(runs["good"][0], 0, runs["good"])
        self.assertEqual(sorted(runs["good"][3]), ["step-timings.tsv"])
        self.assertEqual(sorted(runs["broken"][3]), ["step-timings.err"])
        self.assertRegex(runs["broken"][3]["step-timings.err"],
                         r"^\S+\tpanels\tsource tools/pipeline/step_timings.sh failed\n$")

    def test_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty, full = Path(tmp) / "empty", Path(tmp) / "full"
            empty.mkdir()
            full.mkdir()
            (full / "x").write_text("", encoding="utf-8")
            r = self.bash(f'step_timings_mode "{full}"; step_timings_mode "{empty}"; step_timings_mode ""; '
                          f'step_timings_mode "{tmp}/none"', FULL="1")
        self.assertEqual(r.stdout.split(), ["warm", "cold", "cold", "cold"])      # FULL=1 leaves a warm cache warm


if __name__ == "__main__":
    unittest.main()
