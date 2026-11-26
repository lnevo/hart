#!/usr/bin/env python3
"""timings.py

Summarize the local step-timings log into docs/pipeline-map/timings.json, the committed figures the pipeline map
page reads, and check that summary against the step manifests.

    python3 tools/pipeline/timings.py summarize [--log FILE] [--out FILE]    write the summary (make timings)
    python3 tools/pipeline/timings.py --check [--out FILE]                   exit 1 if it names a step no manifest has

tools/check.sh and tools/schematic/build_panels.sh append one line per step run to the log (tools/pipeline/
step_timings.sh): step-timings.tsv in the shared cache (hartlib.paths.cache_dir, <main checkout>/.cache/hart), or the
file HART_STEP_TIMINGS_LOG names (spaces trimmed, ~ expanded; set and empty or spaces: no log). Each line is
tab-separated:

    iso_time  runner  step  seconds  result  mode

runner is panels or check; step is the panels.toml step name (runner panels) or check.sh's job name (runner check:
a checks.toml step's name, panels-<step> for the jobs the panels step expands into); result ok, failed or skipped
(its stamp held, or it printed SKIPPED); mode cold (the schematic cache off or empty; make panels FULL=1 ignores only
the stamps, so it can be warm), warm or empty. A line that does not read so is left out and counted.

The summary holds step names, counts, seconds and dates only, so it is safe to publish:

    {"updated": "YYYY-MM-DD", "source": "step-timings log",
     "steps": {"<runner>:<step>": {"runner", "step", "runs", "warm_s", "cold_s", "skip_rate", "last"}}}

warm_s and cold_s are the medians (one decimal) of the ok runs in that mode, null with none; skip_rate the share of
runs skipped (two decimals); last the day of the last run; updated the latest last. A step no manifest names any more
is left out. Keys are sorted, so the same log always gives the same bytes.

With an empty log, or one whose runs are all of steps no manifest names, summarize keeps a summary already there
and otherwise writes SEED: the cold figures of the timed
full rebuild in docs/pipeline-map/efficiency-plan.md ("Full rebuild timed"), source "efficiency-plan.md".
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, TypedDict, cast, get_args

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import files, paths  # noqa: E402

Runner = Literal["panels", "check"]
Result = Literal["ok", "failed", "skipped"]
Mode = Literal["warm", "cold", ""]
RUNNERS: tuple[str, ...] = get_args(Runner)
RESULTS: tuple[str, ...] = get_args(Result)
MODES: tuple[str, ...] = get_args(Mode)

HERE = Path(__file__).resolve().parent
OUT = paths.REPO_ROOT / "docs" / "pipeline-map" / "timings.json"
LOG_NAME = "step-timings.tsv"
SOURCE = "step-timings log"
SEED_SOURCE = "efficiency-plan.md"
# efficiency-plan.md's "Full rebuild timed" table: make panels FULL=1 with an empty plugin cache, so every figure is
# cold. Its "the other eleven steps, 7 s together" row names no step and is left out.
SEED_DAY = "2026-11-23"
SEED_COLD_S: dict[str, float] = {"plan-lengths": 37, "schematic": 38, "sml-current": 343, "cats": 4, "tables": 2}

STEP_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
TIME_RE = re.compile(r"(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}Z?")


@dataclass(frozen=True)
class Run:
    """One line of the log."""
    day: str
    runner: Runner
    step: str
    seconds: Optional[float]
    result: Result
    mode: Mode

    @property
    def key(self) -> str:
        return f"{self.runner}:{self.step}"


class StepSummary(TypedDict):
    runner: str
    step: str
    runs: int
    warm_s: Optional[float]
    cold_s: Optional[float]
    skip_rate: Optional[float]
    last: str


class Summary(TypedDict):
    updated: str
    source: str
    steps: dict[str, StepSummary]


def parse_line(line: str) -> Optional[Run]:
    """The run a log line records, or None when it does not read as one."""
    cols = line.rstrip("\r\n").split("\t")
    if len(cols) == 5:
        cols.append("")      # an empty mode at the end of a line some editor trimmed
    if len(cols) != 6:
        return None
    when, runner, step, secs, result, mode = cols
    day = TIME_RE.fullmatch(when)
    if not day or runner not in RUNNERS or not STEP_RE.fullmatch(step) or result not in RESULTS or mode not in MODES:
        return None
    seconds: Optional[float] = None
    if secs:
        try:
            seconds = float(secs)
        except ValueError:
            return None
        if seconds < 0:
            return None
    return Run(day.group(1), cast(Runner, runner), step, seconds, cast(Result, result), cast(Mode, mode))


def parse_log(text: str) -> tuple[list[Run], int]:
    """Every run in the log's text, and how many non-blank lines were not runs."""
    runs: list[Run] = []
    bad = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        run = parse_line(line)
        if run is None:
            bad += 1
        else:
            runs.append(run)
    return runs, bad


def _median(values: list[float]) -> Optional[float]:
    return round(statistics.median(values), 1) if values else None


def step_summary(runs: list[Run]) -> StepSummary:
    """One step's figures from its runs (at least one)."""
    def timed(mode: Mode) -> list[float]:
        return [r.seconds for r in runs if r.result == "ok" and r.mode == mode and r.seconds is not None]
    skipped = sum(r.result == "skipped" for r in runs)
    return StepSummary(runner=runs[0].runner, step=runs[0].step, runs=len(runs), warm_s=_median(timed("warm")),
                       cold_s=_median(timed("cold")), skip_rate=round(skipped / len(runs), 2),
                       last=max(r.day for r in runs))


def summarize(runs: list[Run], known: Optional[set[str]] = None) -> Summary:
    """The summary of the runs, leaving out the steps `known` (of "<runner>:<step>" keys) does not hold."""
    by_step: dict[str, list[Run]] = defaultdict(list)
    for run in runs:
        if known is None or run.key in known:
            by_step[run.key].append(run)
    steps = {key: step_summary(by_step[key]) for key in sorted(by_step)}
    return Summary(updated=max((s["last"] for s in steps.values()), default=""), source=SOURCE, steps=steps)


def seed() -> Summary:
    """The summary from efficiency-plan.md's timed full rebuild, for a log with no runs yet."""
    steps = {f"panels:{name}": StepSummary(runner="panels", step=name, runs=1, warm_s=None,
                                           cold_s=round(float(secs), 1), skip_rate=0.0, last=SEED_DAY)
             for name, secs in sorted(SEED_COLD_S.items())}
    return Summary(updated=SEED_DAY, source=SEED_SOURCE, steps=steps)


def render(summary: Summary) -> str:
    return json.dumps(summary, indent=1, sort_keys=True) + "\n"


def _manifest():
    """tools/pipeline/manifest.py, loaded by path as its docstring asks (panel_stamps.py loads it the same way)."""
    if "pipeline_manifest" not in sys.modules:
        spec = importlib.util.spec_from_file_location("pipeline_manifest", HERE / "manifest.py")
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules["pipeline_manifest"] = mod
        try:
            spec.loader.exec_module(mod)
        except BaseException:
            del sys.modules["pipeline_manifest"]
            raise
    return sys.modules["pipeline_manifest"]


def known_from(checks: list[dict], panels: list[dict], runs_panels, prefix: str) -> set[str]:
    """The "<runner>:<step>" keys a run can have: each panels step's, and each check.sh job's (a checks.toml step's
    name, or panels-<step> for each panels step when the step runs make panels)."""
    panel_names = [str(s.get("name", "")) for s in panels]
    keys = {f"panels:{n}" for n in panel_names}
    for step in checks:
        if runs_panels(step.get("cmd", [])):
            keys |= {f"check:{prefix}{n}" for n in panel_names}
        else:
            keys.add(f"check:{step.get('name', '')}")
    return keys


def known_steps() -> set[str]:
    """known_from the checkout's two manifests, read as TOML (ManifestError when one cannot be read)."""
    m = _manifest()
    checks, _ = m.read(m.MANIFEST)
    panels, _ = m.read(m.PANELS)
    return known_from(checks.get("step", []), panels.get("step", []), m.runs_panels, m.PANEL_JOB_PREFIX)


def unknown_steps(summary: dict, known: set[str]) -> list[str]:
    """The summary's step keys no manifest names, and keys that do not match their runner and step."""
    problems = []
    for key, entry in sorted(summary.get("steps", {}).items()):
        if key not in known:
            problems.append(f"{key}: no such step in tools/pipeline/checks.toml or panels.toml")
        elif not isinstance(entry, dict) or f"{entry.get('runner')}:{entry.get('step')}" != key:
            problems.append(f"{key}: its runner and step do not match its key")
    return problems


def default_log() -> Optional[Path]:
    """The log the runners append to, or None when HART_STEP_TIMINGS_LOG is set and empty."""
    if "HART_STEP_TIMINGS_LOG" in os.environ:
        value = os.environ["HART_STEP_TIMINGS_LOG"].strip()
        return Path(value).expanduser() if value else None
    return paths.cache_dir(LOG_NAME)


def cmd_summarize(log: Optional[Path], out: Path) -> int:
    text = ""
    if log is not None and log.is_file():
        text = log.read_text(encoding="utf-8", errors="replace")
    runs, bad = parse_log(text)
    if bad:
        print(f"timings: left out {bad} line(s) of the log that are not runs", file=sys.stderr)
    summary: Optional[Summary] = None
    if runs:
        known = known_steps()
        summary = summarize(runs, known)
        gone = sorted({r.key for r in runs} - known)
        if gone:
            print(f"timings: left out steps no manifest names: {', '.join(gone)}", file=sys.stderr)
    if summary is None or not summary["steps"]:
        if out.exists():
            print(f"timings: the log has no runs of a manifest step; {paths.rel(out)} kept as it is")
            return 0
        summary = seed()
    text = render(summary)
    old = out.read_text(encoding="utf-8") if out.exists() else None
    if old != text:
        out.parent.mkdir(parents=True, exist_ok=True)
        files.write_atomic(out, text)
    print(f"timings: {paths.rel(out)} {'written' if old != text else 'current'}, "
          f"{len(summary['steps'])} step(s) from {summary['source']}")
    return 0


def cmd_check(out: Path) -> int:
    try:
        summary = json.loads(out.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        print(f"timings: cannot read {paths.rel(out)}: {err}", file=sys.stderr)
        return 1
    problems = unknown_steps(summary, known_steps())
    for problem in problems:
        print(f"timings: {paths.rel(out)}: {problem}", file=sys.stderr)
    if problems:
        print("timings: make timings rewrites it from the log", file=sys.stderr)
        return 1
    print(f"timings: {paths.rel(out)} names only manifest steps")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="?", choices=["summarize"])
    parser.add_argument("--check", action="store_true", help="exit 1 if the summary names a step no manifest has")
    parser.add_argument("--log", type=Path, help="the log to read (default: the shared cache's step-timings.tsv)")
    parser.add_argument("--out", type=Path, default=OUT, help="the summary (default: docs/pipeline-map/timings.json)")
    args = parser.parse_args(argv)
    if bool(args.command) == args.check:
        parser.error("give summarize or --check")
    try:
        if args.check:
            return cmd_check(args.out)
        return cmd_summarize(args.log if args.log is not None else default_log(), args.out)
    except _manifest().ManifestError as err:
        print(f"timings: cannot read the step manifests: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
