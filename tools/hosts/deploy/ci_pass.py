#!/usr/bin/env python3
"""Whether CI's full check.sh pass covers the commit a deploy ships, so the gate may skip G4 (build_tables.py --check).

    ci_pass.py --commit SHA     exit 0 and print "skipped G4: CI full pass for <sha> ..." when every point below holds;
                                exit 1 and print "ran G4: <why>" when one does not (the gate then runs G4 as before);
                                exit 2 for a bad call, 3 for a failure of this script itself (the gate runs G4
                                for both)

The gate (tools/hosts/deploy/gate.sh) asks this only for a real deploy to the Pi or Windows, after check_on_main
(common.sh) has held the commit to origin/main. A skip needs all of these, read in this order; the first that fails
names the reason:

1. the checkout is SHA itself: HEAD is SHA and `git status --porcelain --ignore-submodules=dirty` is empty (the
   deploy ships the working tree, and CI checked the commit, not files beside it). A submodule at another commit
   counts as a change; local edits inside a submodule do not (the deploy ships none of their files, and the schematic
   plugin enters tables.xml by its pinned commit);
2. GitHub has a push run of .github/workflows/check.yml on main for SHA, the newest one completed with success;
3. its one job "check" passed, with its "Run ./tools/check.sh" step a success;
4. main's check stamps for SHA (the actions/cache entry check-stamps-SHA on refs/heads/main, which that run saves only
   after check.sh passed; tools/ci/stamp_gate.py "main's last full pass") are in CI's cache;
5. the job's log shows a full run: the check.sh step recorded stamps (CHECK_RECORD_TO set), skipped none on older ones
   (CHECK_SKIP_FROM empty), had no CHECK_ONLY, ended "ALL PASSED", ran the "panels" job (not "current, skipped"),
   and its "--- tables" check printed "ok: jmri/layouts/hart/output/tables.xml current" and no SKIPPED.

The stamps themselves cannot be downloaded off a runner (GitHub has no API for a cache's contents), so the cache entry
is read by its key and ref, and the run's own log is the record of what that check.sh run covered. Anything that cannot
be read (no gh, no network, no login, an unexpected answer) is "stamps unreadable" and G4 runs.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ".github/workflows/check.yml"
JOB = "check"
CHECK_STEP = "Run ./tools/check.sh"
TABLES_OK = "ok: jmri/layouts/hart/output/tables.xml current ("
SHA = re.compile(r"[0-9a-f]{40}")
GITHUB_URL = re.compile(r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([\w.-]+)/([\w.-]+?)(?:\.git)?/?")
LOG_TIME = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z ?")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
GH_TIMEOUT = 30
LOG_TIMEOUT = 90


class CiPassError(Exception):
    """Why G4 runs. `lead` starts the gate's line."""
    lead = "no CI pass"


class NoPass(CiPassError):
    """CI's record was read and does not show a full pass for this commit."""


class Unreadable(CiPassError):
    """CI's record could not be read (gh, the network, an answer of another shape)."""
    lead = "CI stamps unreadable"


class CheckoutUnreadable(CiPassError):
    """git could not say what the checkout holds."""
    lead = "the checkout cannot be read"


Gh = Callable[[list[str], int], str]


def git(root: Path, *args: str) -> str:
    try:
        done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=GH_TIMEOUT)
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError) as e:
        raise CheckoutUnreadable(f"git {args[0]} could not run: {e}") from None
    if done.returncode != 0:
        tail = (done.stderr.strip().splitlines() or ["no message"])[-1]
        raise CheckoutUnreadable(f"git {' '.join(args)} failed (exit {done.returncode}): {tail}")
    return done.stdout


def run_gh(args: list[str], timeout: int) -> str:
    """gh's output, or Unreadable naming what failed. No prompt: the gate runs unattended."""
    env = dict(os.environ, GH_PROMPT_DISABLED="1")
    try:
        done = subprocess.run(["gh", *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout, env=env)
    except FileNotFoundError:
        raise Unreadable("gh (the GitHub CLI) is not installed") from None
    except subprocess.TimeoutExpired:
        raise Unreadable(f"gh {' '.join(args[:2])} took over {timeout} s") from None
    except OSError as e:
        raise Unreadable(f"gh could not run: {e}") from None
    except UnicodeDecodeError as e:
        raise Unreadable(f"gh {' '.join(args[:2])} answered with bytes that are not UTF-8: {e}") from None
    if done.returncode != 0:
        tail = (done.stderr.strip().splitlines() or ["no message"])[-1]
        raise Unreadable(f"gh {' '.join(args[:2])} failed (exit {done.returncode}): {tail}")
    return done.stdout


def repo_slug(root: Path) -> str:
    url = git(root, "remote", "get-url", "origin").strip()
    m = GITHUB_URL.fullmatch(url)
    if not m:
        raise Unreadable(f"origin is not a GitHub repository ({url!r})")
    return f"{m.group(1)}/{m.group(2)}"


def check_checkout(root: Path, sha: str) -> None:
    head = git(root, "rev-parse", "--verify", "HEAD^{commit}").strip()
    if head != sha:
        raise NoPass(f"the checkout is at {head[:12]}, not the commit {sha[:12]} the deploy names")
    changes = [line for line in git(root, "status", "--porcelain", "--ignore-submodules=dirty").splitlines() if line.strip()]
    if changes:
        raise NoPass(f"the checkout has {len(changes)} uncommitted or untracked path(s) (first: {changes[0].strip()}); "
                     "CI checked the commit, not these files")


def _json(text: str, what: str) -> dict:
    try:
        data = json.loads(text)
    except ValueError as e:
        raise Unreadable(f"{what} is not JSON: {e}") from None
    if not isinstance(data, dict):
        raise Unreadable(f"{what} is not a JSON object")
    return data


def _field(obj: dict, key: str, kind: type, what: str):
    value = obj.get(key)
    if not isinstance(value, kind) or isinstance(value, bool) and kind is not bool:
        raise Unreadable(f"{what} has no {kind.__name__} {key!r}")
    return value


def find_run(slug: str, sha: str, gh: Gh) -> int:
    """The id of the newest push run of check.yml on main for `sha`, which must have passed."""
    what = "the check.yml runs"
    data = _json(gh(["api", "-X", "GET", f"repos/{slug}/actions/workflows/check.yml/runs", "-f", f"head_sha={sha}",
                     "-f", "event=push", "-f", "branch=main", "-f", "per_page=100"], GH_TIMEOUT), what)
    runs = _field(data, "workflow_runs", list, what)
    total = _field(data, "total_count", int, what)
    if total > len(runs):
        raise Unreadable(f"{total} check.yml runs for {sha[:12]}, more than one page")
    mine = []
    for run in runs:
        if not isinstance(run, dict):
            raise Unreadable(f"{what} hold an entry that is not an object")
        if (run.get("head_sha"), run.get("event"), run.get("head_branch"), run.get("path")) == (sha, "push", "main",
                                                                                                WORKFLOW):
            mine.append(run)
    if not mine:
        raise NoPass(f"CI has no push run of {WORKFLOW} on main for it (not merged yet, or another commit)")
    run = max(mine, key=lambda r: _field(r, "run_number", int, "a check.yml run"))
    run_id = _field(run, "id", int, "a check.yml run")
    status = _field(run, "status", str, f"run {run_id}")
    if status != "completed":
        raise NoPass(f"CI's run {run_id} is {status}, not completed")
    conclusion = run.get("conclusion")
    if conclusion != "success":
        raise NoPass(f"CI's run {run_id} ended {conclusion}")
    return run_id


def find_job(slug: str, sha: str, run_id: int, gh: Gh) -> int:
    """The id of the run's one "check" job, which passed with its check.sh step."""
    what = f"run {run_id}'s jobs"
    data = _json(gh(["api", "-X", "GET", f"repos/{slug}/actions/runs/{run_id}/jobs", "-f", "filter=latest",
                     "-f", "per_page=100"], GH_TIMEOUT), what)
    jobs = [j for j in _field(data, "jobs", list, what) if isinstance(j, dict) and j.get("name") == JOB]
    if len(jobs) != 1:
        raise Unreadable(f"{what} hold {len(jobs)} jobs named {JOB!r}, not one")
    job = jobs[0]
    job_id = _field(job, "id", int, f"run {run_id}'s job")
    if job.get("head_sha") != sha:
        raise Unreadable(f"job {job_id} names commit {str(job.get('head_sha'))[:12]}, not {sha[:12]}")
    if job.get("conclusion") != "success":
        raise NoPass(f"CI's job {job_id} ended {job.get('conclusion')}")
    steps = [s for s in _field(job, "steps", list, f"job {job_id}") if isinstance(s, dict) and s.get("name") == CHECK_STEP]
    if len(steps) != 1:
        raise Unreadable(f"job {job_id} has {len(steps)} steps named {CHECK_STEP!r}, not one")
    if steps[0].get("conclusion") != "success":
        raise NoPass(f"CI's check.sh step in job {job_id} ended {steps[0].get('conclusion')}")
    return job_id


def check_stamps(slug: str, sha: str, gh: Gh) -> None:
    """main's check stamps for `sha` are in CI's cache (check.yml saves them only after check.sh passed)."""
    key = f"check-stamps-{sha}"
    what = "CI's cache list"
    data = _json(gh(["api", "-X", "GET", f"repos/{slug}/actions/caches", "-f", f"key={key}",
                     "-f", "ref=refs/heads/main", "-f", "per_page=100"], GH_TIMEOUT), what)
    caches = _field(data, "actions_caches", list, what)
    if not any(isinstance(c, dict) and c.get("key") == key and c.get("ref") == "refs/heads/main" for c in caches):
        raise NoPass(f"no check stamps {key[:25]} on main in CI's cache (not saved, or expired)")


def _section(lines: list[str], start: int) -> list[str]:
    """The lines after `start` up to the next "--- " heading."""
    out = []
    for line in lines[start + 1:]:
        if line.startswith("--- "):
            break
        out.append(line)
    return out


def check_log(text: str) -> None:
    """The check.sh step's log shows a full run that passed and checked tables.xml (see the module docstring, 5)."""
    lines = [ANSI.sub("", LOG_TIME.sub("", raw)).rstrip("\r") for raw in text.splitlines()]
    starts = [i for i, line in enumerate(lines) if line == f"##[group]{CHECK_STEP}"]
    if len(starts) != 1:
        raise Unreadable(f"the job log has {len(starts)} check.sh steps, not one")
    step = []
    for line in lines[starts[0] + 1:]:
        if line.startswith("##[group]"):
            break
        step.append(line)
    try:
        env_at, end_at = step.index("env:"), step.index("##[endgroup]")
    except ValueError:
        raise Unreadable("the check.sh step's log has no env block") from None
    if env_at > end_at:
        raise Unreadable("the check.sh step's env block is out of order")
    env = {}
    for line in step[env_at + 1:end_at]:
        k, sep, v = line.strip().partition(":")
        if sep:
            env[k] = v.strip()
    if not env.get("CHECK_RECORD_TO"):
        raise NoPass("its check.sh run recorded no stamps (CHECK_RECORD_TO empty): not main's full run")
    if env.get("CHECK_SKIP_FROM"):
        raise NoPass("its check.sh run skipped jobs on older stamps (CHECK_SKIP_FROM set)")
    if "CHECK_ONLY" in env:
        raise NoPass("its check.sh run had CHECK_ONLY: a partial run")
    out = step[end_at + 1:]
    if "ALL PASSED" not in out:
        raise NoPass("its check.sh log has no ALL PASSED line")
    if not any(line.startswith("--- panels (") for line in out):
        raise NoPass("its check.sh log shows no run of the panels job")
    heads = [i for i, line in enumerate(out) if line == "--- tables"]
    if len(heads) != 1:
        raise NoPass(f"its check.sh log has {len(heads)} '--- tables' checks, not one")
    body = _section(out, heads[0])
    if any("SKIPPED" in line for line in body):
        raise NoPass("its tables check printed SKIPPED")
    if not any(line.startswith(TABLES_OK) for line in body):
        raise NoPass("its tables check did not print that tables.xml is current")


def decide(sha: str, root: Path = ROOT, gh: Gh = run_gh) -> int:
    """The passing run's id; else a CiPassError naming why G4 must run."""
    check_checkout(root, sha)
    slug = repo_slug(root)
    run_id = find_run(slug, sha, gh)
    job_id = find_job(slug, sha, run_id, gh)
    check_stamps(slug, sha, gh)
    check_log(gh(["api", f"repos/{slug}/actions/jobs/{job_id}/logs"], LOG_TIMEOUT))
    return run_id


def main(argv: list[str] | None = None, root: Path = ROOT, gh: Gh = run_gh) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--commit", required=True, help="the 40-character commit the deploy ships")
    a = ap.parse_args(argv)
    if not SHA.fullmatch(a.commit):
        print(f"ci_pass.py: --commit must be a full 40-character commit sha, not {a.commit!r}", file=sys.stderr)
        return 2
    try:
        run_id = decide(a.commit, root, gh)
    except CiPassError as e:
        print(f"ran G4: {e.lead} for {a.commit[:12]}: {e}")
        return 1
    except Exception as e:  # a bug here: say so in the gate's line (exit 3), never as exit 1 with no reason
        print(f"ran G4: the CI pass check failed for {a.commit[:12]}: {type(e).__name__}: {e}")
        return 3
    print(f"skipped G4: CI full pass for {a.commit[:12]} (check.yml run {run_id}, stamps check-stamps-{a.commit[:12]}...)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
