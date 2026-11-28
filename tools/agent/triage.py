#!/usr/bin/env python3
"""Triage a /code-review's findings: one headless finding-verifier per finding, then one fix brief.

    triage.py PR --findings FILE [--out DIR] [--jobs N] [--timeout S]

`make triage PR=N FINDINGS=<file>` is the coordinator's way to verify review findings. FILE holds the findings as a
JSON list of {file, line, summary, failure_scenario, severity}. The run:

1. Reads the PR's head branch and full SHA (`gh pr view`) and fetches that branch once (`git fetch origin <branch>`),
   so the verifiers read the PR's code with `git show origin/<branch>:<path>`; they cannot fetch themselves.
2. Starts one `claude -p ... --agent finding-verifier` per finding, at most TRIAGE_JOBS (default 3) at once, each
   with a timeout, --max-turns and --max-budget-usd, and read-only tools. Before each start it counts the `claude`
   processes on the Mac and waits, with a line, while they are at or above HART_SESSION_CAP (default 10).
3. Writes to DIR (default ~/.cache/hart/triage/<PR>/): one JSON per finding (the finding, the verdict, the evidence
   text, cost and duration), summary.json, and fix-brief.md: CONFIRMED findings with evidence and fix, PLAUSIBLE ones
   marked "check against the code", WRONG ones with a one-line reason, the verifiers that errored or timed out as
   "not verified" with the reason, and the total cost. It prints the brief's path and the counts.

There is no option to run the review itself: `claude -p "/code-review low <PR>"` exits 0 but returns "(none)" with
no findings list, so the review stays a session's step and its findings JSON is saved by hand.

Exit 0 when every finding got a verdict, 1 when one or more are not verified, 2 for a bad call or when the PR, the
fetch or the findings cannot be read. It starts Claude processes, so it is the coordinator's: subagent_guard.py blocks
it and `make triage` for subagents.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Literal

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = Path.home() / ".cache" / "hart" / "triage"
DEFAULT_JOBS = 3
DEFAULT_CAP = 10
DEFAULT_TIMEOUT = 300
MAX_TURNS = 12
MAX_BUDGET_USD = 0.75
GH_TIMEOUT = 60
CAP_POLL = 15.0
VERIFIER_TOOLS = ["Read", "Grep", "Glob", "Bash(git show *)", "Bash(git grep *)"]
Verdict = Literal["CONFIRMED", "PLAUSIBLE", "WRONG", "NOT VERIFIED"]
NOT_VERIFIED: Literal["NOT VERIFIED"] = "NOT VERIFIED"
VERDICTS: dict[str, Verdict] = {"CONFIRMED": "CONFIRMED", "PLAUSIBLE": "PLAUSIBLE", "WRONG": "WRONG"}
VERDICT_WORD = re.compile(r"\b(CONFIRMED|PLAUSIBLE|WRONG)\b")


class TriageError(Exception):
    """A problem that stops the run before any verifier starts."""


@dataclass(frozen=True)
class Finding:
    file: str
    line: int | str
    summary: str
    failure_scenario: str = ""
    severity: str = ""


@dataclass(frozen=True)
class Head:
    branch: str
    sha: str


@dataclass
class Result:
    finding: Finding
    verdict: Verdict
    text: str = ""
    reason: str = ""
    cost_usd: float = 0.0
    duration_s: float = 0.0
    num_turns: int = 0


@dataclass(frozen=True)
class Run:
    """What one `claude -p` call returned: its exit code, stdout and stderr, or the timeout."""
    code: int
    out: str
    err: str
    timed_out: bool = False


def load_findings(data: object) -> list[Finding]:
    if not isinstance(data, list):
        raise TriageError("the findings must be a JSON list")
    found = []
    for i, item in enumerate(data, 1):
        if not isinstance(item, dict) or not item.get("file") or not item.get("summary"):
            raise TriageError(f"finding {i} needs at least file and summary")
        found.append(Finding(file=str(item["file"]), line=item.get("line", ""), summary=str(item["summary"]),
                             failure_scenario=str(item.get("failure_scenario", "")),
                             severity=str(item.get("severity", ""))))
    return found


def prompt_for(finding: Finding, head: Head) -> str:
    return (
        "Verify this one /code-review finding against the PR's code.\n"
        f"The PR's head is branch {head.branch} at {head.sha}. It is fetched: read its files with "
        f"`git show origin/{head.branch}:<path>` (or `git show {head.sha}:<path>`); the working tree may be older.\n\n"
        f"File: {finding.file}\nLine: {finding.line}\nSeverity: {finding.severity}\n"
        f"Summary: {finding.summary}\nFailure scenario: {finding.failure_scenario}\n\n"
        "Answer CONFIRMED, PLAUSIBLE or WRONG on the first line, then file:line evidence and the smallest fix.")


def claude_command(prompt: str) -> list[str]:
    return ["claude", "-p", prompt, "--agent", "finding-verifier", "--output-format", "json",
            "--permission-mode", "dontAsk", "--allowedTools", *VERIFIER_TOOLS, "--max-turns", str(MAX_TURNS),
            "--max-budget-usd", str(MAX_BUDGET_USD), "--no-session-persistence"]


def run_process(argv: list[str], timeout: float) -> Run:
    """Run argv from the repo root; kill it at the timeout. macOS has no `timeout` command."""
    try:
        proc = subprocess.Popen(argv, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
    except OSError as exc:
        return Run(code=127, out="", err=f"could not start {argv[0]}: {exc}")
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        return Run(code=proc.returncode, out=out, err=err, timed_out=True)
    return Run(code=proc.returncode, out=out, err=err)


def first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def parse_verdict(finding: Finding, run: Run, elapsed: float, timeout: float) -> Result:
    if run.timed_out:
        return Result(finding, NOT_VERIFIED, reason=f"timed out after {timeout:.0f} s", duration_s=elapsed)
    try:
        data = json.loads(run.out)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        tail = first_line(run.err) or first_line(run.out) or "no output"
        return Result(finding, NOT_VERIFIED, reason=f"exit {run.code}, no JSON result: {tail[:200]}",
                      duration_s=elapsed)
    text = str(data.get("result") or "")
    cost = float(data.get("total_cost_usd") or 0.0)
    turns = int(data.get("num_turns") or 0)
    duration = float(data.get("duration_ms") or elapsed * 1000) / 1000
    if data.get("is_error") or run.code != 0:
        reason = f"exit {run.code}, {data.get('subtype') or 'error'}: {first_line(text)[:200]}".rstrip(": ")
        return Result(finding, NOT_VERIFIED, text=text, reason=reason, cost_usd=cost, duration_s=duration,
                      num_turns=turns)
    match = VERDICT_WORD.search(first_line(text))
    if not match:
        return Result(finding, NOT_VERIFIED, text=text, reason="no verdict on the first line", cost_usd=cost,
                      duration_s=duration, num_turns=turns)
    return Result(finding, VERDICTS[match.group(1)], text=text, cost_usd=cost, duration_s=duration, num_turns=turns)


def verify(finding: Finding, head: Head, timeout: float, start: Callable[[list[str], float], Run] = run_process
           ) -> Result:
    began = time.monotonic()
    run = start(claude_command(prompt_for(finding, head)), timeout)
    return parse_verdict(finding, run, time.monotonic() - began, timeout)


def running_claude() -> int:
    """How many `claude` processes run on this machine (sessions, subagent hosts and headless runs)."""
    try:
        out = subprocess.run(["ps", "-axo", "comm="], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return 0
    return sum(1 for line in out.splitlines() if os.path.basename(line.strip()) == "claude")


class SessionCap:
    """Waits before each start while the count of Claude processes is at or above the cap. The lock makes the check
    and the start one step, so two workers never both take the last place."""

    def __init__(self, cap: int, count: Callable[[], int] = running_claude,
                 sleep: Callable[[float], None] = time.sleep, poll: float = CAP_POLL, settle: float = 0.5) -> None:
        self.cap, self.count, self.sleep, self.poll, self.settle = cap, count, sleep, poll, settle
        self.lock = threading.Lock()

    def wait(self, label: str) -> None:
        while True:
            now = self.count()
            if now < self.cap:
                return
            print(f"triage: {now} Claude processes running, cap {self.cap}; {label} waits", flush=True)
            self.sleep(self.poll)


def run_all(findings: list[Finding], work: Callable[[Finding], Result], jobs: int, cap: SessionCap) -> list[Result]:
    """Run work on each finding, at most `jobs` at once, each start held behind the session cap."""

    def one(index: int, finding: Finding) -> Result:
        label = f"finding {index} ({finding.file}:{finding.line})"
        with cap.lock:
            cap.wait(label)
            started = threading.Event()
            box: list[Result] = []

            def go() -> None:
                started.set()
                box.append(work(finding))

            thread = threading.Thread(target=go)
            thread.start()
            started.wait()
            time.sleep(cap.settle)  # give the process time to show in ps before the next count
        thread.join()
        result = box[0] if box else Result(finding, NOT_VERIFIED, reason="the verifier raised an error")
        print(f"triage: {label}: {result.verdict}{' - ' + result.reason if result.reason else ''}", flush=True)
        return result

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        return list(pool.map(lambda pair: one(*pair), enumerate(findings, 1)))


def evidence(result: Result) -> str:
    """The verdict text after its first line."""
    lines = result.text.strip().splitlines()
    return "\n".join(lines[1:]).strip() if lines else ""


def one_line_reason(result: Result) -> str:
    rest = first_line(evidence(result)) or first_line(result.text)
    return rest if len(rest) <= 240 else rest[:237] + "..."


def where(finding: Finding) -> str:
    return f"{finding.file}:{finding.line}" if str(finding.line) else finding.file


def brief(pr: int, head: Head, results: list[Result]) -> str:
    by: dict[str, list[Result]] = {v: [r for r in results if r.verdict == v]
                                   for v in ("CONFIRMED", "PLAUSIBLE", "WRONG", NOT_VERIFIED)}
    total = sum(r.cost_usd for r in results)
    out = [f"# Fix brief for PR #{pr}", "",
           f"Head {head.branch} at {head.sha}. {len(results)} findings: {len(by['CONFIRMED'])} confirmed, "
           f"{len(by['PLAUSIBLE'])} plausible, {len(by['WRONG'])} wrong, {len(by[NOT_VERIFIED])} not verified.", ""]
    out += ["## Confirmed: fix these", ""]
    for r in by["CONFIRMED"]:
        out += [f"### {where(r.finding)}: {r.finding.summary}", "", evidence(r) or "(no evidence text)", ""]
    if not by["CONFIRMED"]:
        out += ["None.", ""]
    out += ["## Plausible: check against the code", ""]
    for r in by["PLAUSIBLE"]:
        out += [f"### {where(r.finding)}: {r.finding.summary}", "", "Check against the code.", "",
                evidence(r) or "(no evidence text)", ""]
    if not by["PLAUSIBLE"]:
        out += ["None.", ""]
    out += ["## Wrong: no change", ""]
    out += [f"- {where(r.finding)}: {r.finding.summary} ({one_line_reason(r)})" for r in by["WRONG"]] or ["None."]
    out += ["", "## Not verified", ""]
    out += [f"- {where(r.finding)}: {r.finding.summary} ({r.reason})" for r in by[NOT_VERIFIED]] or ["None."]
    out += ["", f"Total cost: ${total:.2f}.", ""]
    return "\n".join(out)


def write_outputs(out_dir: Path, pr: int, head: Head, results: list[Result]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("finding-*.json"):
        old.unlink()
    for i, r in enumerate(results, 1):
        (out_dir / f"finding-{i:02d}.json").write_text(json.dumps(asdict(r), indent=1) + "\n")
    counts = {v: sum(1 for r in results if r.verdict == v) for v in ("CONFIRMED", "PLAUSIBLE", "WRONG", NOT_VERIFIED)}
    summary = {"pr": pr, "branch": head.branch, "sha": head.sha, "counts": counts,
               "total_cost_usd": round(sum(r.cost_usd for r in results), 4),
               "findings": [{"file": r.finding.file, "line": r.finding.line, "verdict": r.verdict,
                             "reason": r.reason, "cost_usd": r.cost_usd, "duration_s": r.duration_s}
                            for r in results]}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    path = out_dir / "fix-brief.md"
    path.write_text(brief(pr, head, results))
    return path


def pr_head(pr: int) -> Head:
    try:
        done = subprocess.run(["gh", "pr", "view", str(pr), "--json", "headRefName,headRefOid"], cwd=ROOT,
                              capture_output=True, text=True, timeout=GH_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        raise TriageError(f"gh pr view {pr} failed: {exc}") from exc
    if done.returncode != 0:
        raise TriageError(f"gh pr view {pr} failed: {first_line(done.stderr)}")
    data = json.loads(done.stdout)
    return Head(branch=str(data["headRefName"]), sha=str(data["headRefOid"]))


def fetch(head: Head) -> None:
    try:
        done = subprocess.run(["git", "fetch", "origin", head.branch], cwd=ROOT, capture_output=True, text=True,
                              timeout=GH_TIMEOUT)
        if done.returncode != 0:
            raise TriageError(f"git fetch origin {head.branch} failed: {first_line(done.stderr)}")
        got = subprocess.run(["git", "rev-parse", f"origin/{head.branch}"], cwd=ROOT, capture_output=True,
                             text=True, timeout=GH_TIMEOUT).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise TriageError(f"git fetch origin {head.branch} failed: {exc}") from exc
    if got != head.sha:
        print(f"triage: origin/{head.branch} is {got or 'missing'}, the PR's head is {head.sha}; the verifiers are "
              f"told to read {head.sha}", flush=True)


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("pr", type=int)
    ap.add_argument("--findings", type=Path, required=True, help="the /code-review findings JSON")
    ap.add_argument("--out", type=Path, help="output folder (default ~/.cache/hart/triage/<PR>)")
    ap.add_argument("--jobs", type=int, default=env_int("TRIAGE_JOBS", DEFAULT_JOBS))
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="seconds per verifier")
    args = ap.parse_args(argv)
    try:
        findings = load_findings(json.loads(args.findings.read_text()))
        head = pr_head(args.pr)
        fetch(head)
    except (OSError, ValueError, TriageError) as exc:
        print(f"triage: {exc}", file=sys.stderr)
        return 2
    cap = SessionCap(env_int("HART_SESSION_CAP", DEFAULT_CAP))
    print(f"triage: PR #{args.pr}, {len(findings)} findings, {args.jobs} at once, head {head.sha}", flush=True)
    results = run_all(findings, lambda f: verify(f, head, args.timeout), args.jobs, cap)
    path = write_outputs(args.out or DEFAULT_OUT / str(args.pr), args.pr, head, results)
    counts = {v: sum(1 for r in results if r.verdict == v) for v in ("CONFIRMED", "PLAUSIBLE", "WRONG", NOT_VERIFIED)}
    print(f"triage: {path}")
    print("triage: " + ", ".join(f"{n} {v.lower()}" for v, n in counts.items())
          + f"; ${sum(r.cost_usd for r in results):.2f}")
    return 1 if counts[NOT_VERIFIED] else 0


if __name__ == "__main__":
    sys.exit(main())
