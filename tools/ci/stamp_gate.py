#!/usr/bin/env python3
"""Decide whether a pull request's CI run may skip the check.sh jobs main's last full pass already covered.

    stamp_gate.py manifest DIR --sha SHA      main's push run, after check.sh passed with CHECK_RECORD_TO=DIR: write
                                              DIR/manifest.json (the commit and the runner the stamps were made on)
    stamp_gate.py decide DIR --base SHA [--pin-changed true|false] [--labels L1,L2] [--message-file F] < changed paths
                                              a pull request run: print "skip" or "full: <reason>"; exit 0 for skip
                                              (run check.sh with CHECK_SKIP_FROM=DIR), 3 for full
    stamp_gate.py record-skips RESULTS --pr N --run ID --base SHA --head SHA --out FILE
                                              a pull request run that passed: write FILE, the record of the jobs it
                                              skipped on main's stamps, from check.sh's CHECK_RESULTS_TO file
    stamp_gate.py check-skips RESULTS DIR     the weekly full run: exit 1 naming each job that failed in it and that
                                              a pull request run recorded in DIR (any *.json below it) skipped; 2 when
                                              the results or a record cannot be used

.github/workflows/check.yml restores main's stamps by the pull request's merge base (the merge commit's first parent)
from actions/cache, then asks `decide`. A skip means: a job whose stamp matches has inputs byte-identical to the ones
it passed with on that main commit (tools/audit/check_stamps.py: its traced read set, check.sh and the hook, the
interpreter, the plugin and the environment). Any doubt is a full run, with the reason in the log:

- the full-ci label on the pull request, or [full-ci] in one of its commit messages;
- the plugin pin differs from the base's;
- the change touches the machinery that makes or reads the stamps, or the workflow itself (MACHINERY);
- no manifest, an unreadable one, or one for another commit than the merge base, another runner image, OS,
  architecture, Python, git or bash (runner());
- no stamp files next to the manifest.

Stamps are only ever compared on the GitHub runner they were made on: check.sh refuses CHECK_SKIP_FROM off CI.

A wrong skip (a stamp key that leaves an input out) lets a pull request pass with a job that would fail. Each pull
request run that passed keeps the names of the jobs it skipped as an artifact (record-skips); the weekly full run of
main downloads the records of the last week's runs and fails when a job one of them skipped fails in full
(check-skips), so a wrong skip shows within a week, named as one, beside the job's own failure. A job failing in full
that a pull request skipped is not proof that the skip was wrong (main moved since), only the place to look first.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

MANIFEST = "manifest.json"
VERSION = 1
LABEL = "full-ci"
TOKEN = "[full-ci]"
# Changed paths that force a full run: the workflow, check.sh, this gate and the stamp code (a change to how stamps
# are made or compared must be proven by a full run, not judged by the stamps it changes).
MACHINERY = (
    ".github/workflows/check.yml",
    "tools/check.sh",
    "tools/pipeline/manifest.py",           # turns tools/pipeline/checks.toml into check.sh's job lines
    "tools/pipeline/manifest_base.py",      # its parts (manifest.FILES)
    "tools/pipeline/manifest_checks.py",
    "tools/pipeline/manifest_jobs.py",
    "tools/pipeline/manifest_panels.py",
    "tools/ci/",
    "tools/audit/check_stamps.py",
    "tools/audit/stamps_cache.py",          # its parts (check_stamps.FILES)
    "tools/audit/stamps_audit.py",
    "tools/audit/traced.py",
    "tools/audit/traced_read.py",           # its parts (traced.HOOK_FILES)
    "tools/audit/trace_hook/",
    "tools/schematic/panel_stamps.py",
    "tools/hosts/profile_tables_guard.sh",
    "tools/hartlib/src/hartlib/paths.py",     # check_stamps: the stamp folder and main_checkout (what counts as traced)
    "tools/audit/stamp_audit/",
)
SHA = re.compile(r"[0-9a-f]{40}")
RESULTS = ("passed", "failed", "skipped")       # check.sh's CHECK_RESULTS_TO: "<job><TAB><result>" per queued job
SKIPS_VERSION = 1


class GateError(Exception):
    """A results file or skip record that cannot be used; the message says which and why."""


def _version(*cmd: str) -> str:
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        return f"unavailable: {e}"
    return (done.stdout.splitlines() or [f"failed:{done.returncode}"])[0]


def runner() -> dict[str, str]:
    """The runner the stamps are tied to: GitHub's image (not its build number: runners of one image differ in it
    from hour to hour), the OS, the architecture, the Python, and the git and bash the untraced jobs run."""
    return {
        "image_os": os.environ.get("ImageOS", ""),
        "runner_os": os.environ.get("RUNNER_OS", ""),
        "arch": platform.machine(),
        "python": sys.version,
        "executable": os.path.realpath(sys.executable),
        "git": _version("git", "--version"),
        "bash": _version("bash", "--version"),
    }


def write_manifest(folder: Path, sha: str) -> Path:
    if not SHA.fullmatch(sha):
        raise SystemExit(f"not a commit sha: {sha!r}")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "filehash.json").unlink(missing_ok=True)      # mtimes of this checkout: never trusted by another
    stamps = sorted(p.name for p in folder.glob("*.json") if p.name != MANIFEST)
    path = folder / MANIFEST
    path.write_text(json.dumps({"version": VERSION, "sha": sha, "runner": runner(), "stamps": len(stamps)},
                               indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return path


def machinery(paths: list[str]) -> list[str]:
    out = []
    for p in paths:
        p = p.strip().removeprefix("./")
        if p and any(p == m or (m.endswith("/") and p.startswith(m)) for m in MACHINERY):
            out.append(p)
    return out


def decide(folder: Path, base: str, changed: list[str], pin_changed: bool = False, labels: list[str] | None = None,
           message: str = "", now: dict[str, str] | None = None) -> str | None:
    """None when the run may skip with `folder`'s stamps, else why it must run everything."""
    labels = [label.strip() for label in (labels or []) if label.strip()]
    changed = [p for p in changed if p.strip()]
    if LABEL in labels:
        return f"the pull request has the {LABEL} label"
    if TOKEN in message:
        return f"a commit message of the pull request has {TOKEN}"
    if pin_changed:
        return "the plugin pin differs from the base's"
    touched = machinery(changed)
    if touched:
        return f"the change touches the CI or stamp machinery ({', '.join(touched[:3])})"
    if not changed:
        return "no changed paths were given"
    if not SHA.fullmatch(base or ""):
        return f"no merge base commit ({base!r})"
    path = folder / MANIFEST
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return f"no stamps from main {base[:12]} (its push run is not done, failed, or the cache expired)"
    except (OSError, ValueError) as e:
        return f"the stamps' manifest cannot be read: {e}"
    if not isinstance(data, dict) or data.get("version") != VERSION:
        return "the stamps' manifest is of another version"
    if data.get("sha") != base:
        return f"the stamps were made on main {str(data.get('sha'))[:12]}, not on the merge base {base[:12]}"
    now = runner() if now is None else now
    made = data.get("runner")
    if not isinstance(made, dict):
        return "the stamps' manifest names no runner"
    for k in sorted(set(now) | set(made)):
        if made.get(k) != now.get(k):
            return f"the stamps were made on another runner ({k}: {made.get(k)!r}, now {now.get(k)!r})"
    if not any(p.name != MANIFEST and p.name != "filehash.json" for p in folder.glob("*.json")):
        return "the stamps folder holds no stamps"
    return None


def read_results(path: Path) -> dict[str, str]:
    """check.sh's CHECK_RESULTS_TO file: job -> passed, failed or skipped, in its order. Raises GateError for a file
    that cannot be read, holds no job (check.sh stopped before the end), a line that is not "<job><TAB><result>", or
    a job named twice."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise GateError(f"{path}: cannot read check.sh's results: {e}") from e
    out: dict[str, str] = {}
    for n, line in enumerate(text.splitlines(), 1):
        name, tab, result = line.partition("\t")
        if not tab or not name.strip() or name != name.strip() or result not in RESULTS:
            raise GateError(f"{path} line {n}: {line!r} is not \"<job><TAB>{'|'.join(RESULTS)}\"")
        if name in out:
            raise GateError(f"{path} line {n}: job {name!r} is listed twice")
        out[name] = result
    if not out:
        raise GateError(f"{path} names no job: check.sh stopped before its jobs were done, or did not write it")
    return out


def skip_record(results: dict[str, str], pr: int, run: int, base: str, head: str) -> dict:
    """The record a passing pull request run keeps: which jobs it skipped on main's stamps for `base`. Raises GateError
    when the run did not pass (a failed job in it), or a number or commit is not one."""
    failed = sorted(job for job, r in results.items() if r == "failed")
    if failed:
        raise GateError(f"the run has failed jobs ({', '.join(failed[:5])}): a skip record is kept for a pass only")
    if pr <= 0 or run <= 0:
        raise GateError(f"pull request {pr} and run {run} must be positive numbers")
    for what, sha in (("base", base), ("head", head)):
        if not SHA.fullmatch(sha or ""):
            raise GateError(f"--{what} {sha!r} is not a commit sha")
    return {"version": SKIPS_VERSION, "pr": pr, "run": run, "base": base, "head": head,
            "skipped": sorted(job for job, r in results.items() if r == "skipped"),
            "ran": sum(r != "skipped" for r in results.values())}


def read_record(path: Path) -> dict:
    """One record-skips file. Raises GateError for one that is not JSON or not of that shape: a record that cannot be
    read would hide the skips it holds."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise GateError(f"{path}: not a skip record: {e}") from e
    if not isinstance(data, dict) or data.get("version") != SKIPS_VERSION:
        raise GateError(f"{path}: not a skip record of version {SKIPS_VERSION}")
    skipped = data.get("skipped")
    if (not isinstance(skipped, list) or not all(isinstance(j, str) and j for j in skipped)
            or not all(isinstance(data.get(k), int) and data[k] > 0 for k in ("pr", "run"))
            or not all(SHA.fullmatch(str(data.get(k))) for k in ("base", "head"))):
        raise GateError(f"{path}: a skip record needs pr, run (numbers), base, head (commits) and skipped (job names)")
    return data


def wrong_skips(results: dict[str, str], records: list[dict]) -> tuple[list[str], list[str]]:
    """The weekly full run's check: (one error line per job that failed in `results` and that a record skipped,
    notes). Raises GateError when `results` is not a full run (a job in it was skipped)."""
    skipped_now = sorted(job for job, r in results.items() if r == "skipped")
    if skipped_now:
        raise GateError(f"the results skip {len(skipped_now)} job(s) ({', '.join(skipped_now[:5])}): not a full run")
    by_job: dict[str, list[dict]] = {}
    for rec in records:
        for job in rec["skipped"]:
            by_job.setdefault(job, []).append(rec)
    errors = []
    for job in sorted(j for j, r in results.items() if r == "failed"):
        for rec in sorted(by_job.get(job, []), key=lambda r: r["run"]):
            errors.append(f"{job}: fails in this full run, and pull request #{rec['pr']} (run {rec['run']}, head "
                          f"{rec['head'][:12]}) skipped it on main {rec['base'][:12]}'s stamps: check its stamp key "
                          f"first (python3 tools/audit/check_stamps.py why {job})")
    gone = sorted(set(by_job) - set(results))
    notes = [f"{len(records)} skip record(s) from pull request runs, {sum(len(r['skipped']) for r in records)} skipped "
             f"job(s); {sum(r == 'failed' for r in results.values())} of {len(results)} jobs failed in this run"]
    if gone:
        notes.append(f"skipped then, not run now (renamed or removed): {', '.join(gone[:10])}")
    return errors, notes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("manifest")
    m.add_argument("dir", type=Path)
    m.add_argument("--sha", required=True)
    d = sub.add_parser("decide")
    d.add_argument("dir", type=Path)
    d.add_argument("--base", required=True)
    d.add_argument("--pin-changed", default="false", choices=("true", "false"))
    d.add_argument("--labels", default="")
    d.add_argument("--message-file", type=Path)
    r = sub.add_parser("record-skips")
    r.add_argument("results", type=Path)
    for flag in ("--pr", "--run"):
        r.add_argument(flag, type=int, required=True)
    for flag in ("--base", "--head"):
        r.add_argument(flag, required=True)
    r.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("check-skips")
    c.add_argument("results", type=Path)
    c.add_argument("dir", type=Path)
    a = ap.parse_args(argv)
    if a.cmd in ("record-skips", "check-skips"):
        try:
            return _skips(a)
        except GateError as e:
            print(f"stamp_gate.py {a.cmd}: {e}", file=sys.stderr)
            return 2
    if a.cmd == "manifest":
        path = write_manifest(a.dir, a.sha)
        print(f"wrote {path}: {json.loads(path.read_text())['stamps']} stamps for {a.sha[:12]}")
        return 0
    try:
        message = a.message_file.read_text(encoding="utf-8", errors="replace") if a.message_file else ""
    except OSError as e:
        print(f"full: the commit messages cannot be read: {e}")
        return 3
    reason = decide(a.dir, a.base, sys.stdin.read().splitlines(), a.pin_changed == "true", a.labels.split(","), message)
    print("skip" if reason is None else f"full: {reason}")
    return 0 if reason is None else 3


def _skips(a) -> int:
    results = read_results(a.results)
    if a.cmd == "record-skips":
        rec = skip_record(results, a.pr, a.run, a.base, a.head)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {a.out}: {len(rec['skipped'])} of {len(results)} jobs skipped on main {a.base[:12]}'s stamps")
        return 0
    if not a.dir.is_dir():
        raise GateError(f"{a.dir} is not a folder (the downloaded skip records)")
    records = [read_record(f) for f in sorted(a.dir.rglob("*.json"))]
    errors, notes = wrong_skips(results, records)
    print("\n".join(notes))
    for line in errors:
        print(f"::error::wrong skip? {line}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
