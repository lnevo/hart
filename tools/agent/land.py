#!/usr/bin/env python3
"""The coordinator's half of shipping a PR: `make land PR=N` (the lane's half is `make ready`).

    land.py N [--squash] [--wave W --dash-out DIR] [--poll S] [--no-watch-main] [--watch]

`make land` takes a ticket in the merge queue (tools/agent/land_queue.py), starts the steps below as a detached
background job writing to ~/.cache/hart/land/<N>-t<ticket>.log, prints the ticket and the log, and returns at once
(exit 0). Exit 0 then means queued, not merged: the job writes its exit code to ~/.cache/hart/land/<N>-t<ticket>.result,
and `make land-wait PR=N` waits for it. `--watch` (`WATCH=1`) runs the steps in the foreground instead and exits with their
code. `make land-status` shows the queue and the last lines of each log. A PR that already has a live ticket is not
queued again: the ticket and its log are printed and the exit is 0.

Steps, in order; the first problem stops the run with one line saying why (.claude/skills/coordinate/merging.md has
the rules). Steps 1 to 3 run while the ticket waits behind others; 4 and 5 only at the head of the queue:

1. The PR is open, its base is main and GitHub reports no conflict. A conflict is fixed by merging origin/main into
   the branch locally: the merge drivers in .gitattributes run only in a local merge, never in update-branch.
2. Main is not red: main's newest push run of check.yml did not end failure, cancelled or timed_out
   (tools/hosts/deploy/ci_pass.py's main_red, the deploy gate's G0c).
3. The required check `check` passes on the PR's head. A check run for that exact head SHA can take a minute to be
   registered, so the run waits for one to exist, then for it to finish. Anything but success stops. While the
   ticket waits, for its check or its turn, the PR is read again every poll: closed or conflicting stops; a new head
   re-targets the ticket, which keeps its place, says "head moved from <old> to <new>; waiting for its check", waits
   for the new head's check and merges that head. A draft PR (one `make ready` opened with GitHub's check as its gate) is
   refused until that check passed; on the pass it is marked ready (`gh pr ready N`) in step 4.
4. The head of the queue (LandQueue.wait_turn): one merge at a time across sessions, first come, first served,
   with no time limit while every ticket ahead is alive and a line every minute naming the place and the head. The
   head also takes the old merge lock (MergeLock, LOCK_PATH), so a land from older code that knows only the lock
   never merges beside it. After a wait main is checked again. A draft is marked ready only then, just before the
   merge. Then `gh pr merge N --merge --match-head-commit <head>` (`--squash` instead of `--merge` only when asked;
   never --admin). The ticket and the lock are held through the end of step 5.
5. Main's push run of check.yml for the merge commit, found by its full 40-character SHA and waited for the same way,
   is watched to the end. On red the Main red rule is printed and the exit is MAIN_RED_EXIT.
6. Every other open PR that changes a file the merged PR changed, merge-driver paths left out, gets a line saying it
   must merge origin/main locally, from tools/ops/orient_overlap.py's overlaps_for (the one overlap rule). Steps 6
   to 8 run after the merge, so a failure in one is a line, never a traceback or exit 1; the exit is then 5 unless main's run was red (4).
7. What the PR ships: the layout hosts (tools/hosts/live_paths.txt), the site (www/) or nothing. Nothing is deployed.
8. With --wave and --dash-out, and tools/agent/dash_rows.py present, the merge event is written for the dashboard
   and dash_rows.py's writes JSON is printed.

Exit 0 when the PR merged and main's run passed, 1 when it stopped before the merge (nothing merged), 2 for a bad
call, 4 (MAIN_RED_EXIT) when it merged and main's run ended red, 5 when it merged but main's run could not be
watched to the end (in the log for a detached land). Every gh call goes through one runner (Lander.gh), which the tests
replace.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parent))
from land_queue import (LOCK_PATH, LOG_DIR, QUEUE_DIR, LandQueue, MergeLock, Ticket,  # noqa: E402
                        append_event, event_line, find_log, log_path, result_path, session_name, write_result)
from land_queue import LOCK_CEILING as LOCK_CEILING, LOCK_STALE as LOCK_STALE  # noqa: E402  (the lock's rule, here too)

ROOT = Path(__file__).resolve().parents[2]
CHECK = "check"
WORKFLOW = "check.yml"
SITE = "www/"
GH_TIMEOUT = 60
POLL = 15                   # seconds between polls
REGISTER_WAIT = 600         # seconds to wait for GitHub to register a check run or a push run
RUN_WAIT = 3600             # seconds to wait for a registered run to finish
MERGED_WAIT = 120           # seconds to wait for GitHub to report the merge commit
MAIN_RED_EXIT = 4
UNWATCHED_EXIT = 5
OVERLAP_TOOL = "tools/ops/orient_overlap.py"
SHA = re.compile(r"[0-9a-f]{40}")
PR_LABEL = re.compile(r"PR #(\d+)")
MAIN_RED_RULE = ("Main red: give no go and deploy nothing until main is green again. The PR that broke it fixes "
                 "forward, or one PR reverts it (.claude/skills/coordinate/merging.md, After a merge).")

Gh = Callable[[list[str]], str]
Sleep = Callable[[float], None]
Clock = Callable[[], float]


class LandError(Exception):
    """A reason to stop, said in one line."""


class Refused(LandError):
    """Stopped before the merge: nothing was merged."""


class HeadMoved(LandError):
    """The PR has a new head while its ticket waits: the land re-targets `pr`, the PR as read again."""

    def __init__(self, pr: PullRequest) -> None:
        super().__init__(f"PR #{pr.number}'s head moved to {pr.head[:12]}")
        self.pr = pr


def run_gh(args: list[str]) -> str:
    """gh's stdout; LandError naming the call when it fails. No prompts."""
    try:
        done = subprocess.run(["gh", *args], cwd=ROOT, capture_output=True, text=True, timeout=GH_TIMEOUT,
                              env={**os.environ, "GH_PROMPT_DISABLED": "1"})
    except FileNotFoundError as e:
        raise LandError("gh (the GitHub CLI) is not installed") from e
    except (OSError, subprocess.SubprocessError) as e:
        raise LandError(f"gh {' '.join(args[:2])} could not run: {e}") from e
    if done.returncode != 0:
        tail = (done.stderr.strip().splitlines() or ["no message"])[-1]
        raise LandError(f"gh {' '.join(args[:2])} failed (exit {done.returncode}): {tail}")
    return done.stdout


def load_tool(path: Path, name: str) -> ModuleType | None:
    """A repo script imported by path, or None when it is not there."""
    if not path.is_file():
        return None
    folder = str(path.parent)
    if folder not in sys.path:
        sys.path.insert(0, folder)
    return importlib.import_module(name)


def parse_json(text: str, what: str) -> object:
    try:
        return json.loads(text)
    except ValueError as e:
        raise LandError(f"{what} is not JSON: {e}") from e


def as_dict(value: object, what: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise LandError(f"{what} is not a JSON object")
    return value


def as_list(value: object, what: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        raise LandError(f"{what} is not a list of objects")
    return value


@dataclass(frozen=True)
class PullRequest:
    number: int
    state: str
    head: str
    branch: str
    base: str
    mergeable: str
    files: tuple[str, ...]
    draft: bool = False

    @classmethod
    def parse(cls, obj: dict[str, object], number: int) -> PullRequest:
        what = f"PR #{number}"
        files = tuple(str(f["path"]) for f in as_list(obj.get("files") or [], f"{what}'s files") if "path" in f)
        return cls(number=number, state=str(obj.get("state", "")), head=str(obj.get("headRefOid", "")),
                   branch=str(obj.get("headRefName", "")), base=str(obj.get("baseRefName", "")),
                   mergeable=str(obj.get("mergeable", "")), files=files, draft=obj.get("isDraft") is True)


@dataclass(frozen=True)
class Run:
    """A check run or a workflow run: whether it finished and how."""
    id: int
    status: str
    conclusion: str | None
    url: str


@dataclass
class Lander:
    gh: Gh = run_gh
    root: Path = ROOT
    sleep: Sleep = time.sleep
    clock: Clock = time.monotonic
    poll: float = POLL
    out: list[str] = field(default_factory=list)
    lock_path: Path = LOCK_PATH
    lock_sleep: Sleep = time.sleep
    queue_dir: Path = QUEUE_DIR
    ticket_number: int | None = None
    events_dir: Path | None = None      # where events.log is appended; None (the tests) writes none
    _last_read: float | None = field(default=None, repr=False)

    def event(self, pr: int, code: int | None, reason: str) -> None:
        """One line in events.log (land_queue.event_line); a failure to write it is a line in the log."""
        if self.events_dir is None:
            return
        try:
            append_event(event_line(time.strftime("%H:%M:%S"), self.ticket_number, pr, "", code, reason),
                         self.events_dir)
        except OSError as e:
            self.say(f"events.log not written: {e}")

    def say(self, line: str) -> None:
        print(line, flush=True)
        self.out.append(line)

    def gh_json(self, args: list[str], what: str) -> object:
        return parse_json(self.gh(args), what)

    # ------------------------------------------------------------ 1. the PR

    def read_pr(self, number: int) -> PullRequest:
        obj = as_dict(self.gh_json(["pr", "view", str(number), "--json",
                                    "state,headRefOid,headRefName,mergeable,files,baseRefName,isDraft"],
                                   f"PR #{number}"),
                      f"PR #{number}")
        return PullRequest.parse(obj, number)

    def check_pr(self, pr: PullRequest) -> None:
        if pr.state != "OPEN":
            raise Refused(f"PR #{pr.number} is {pr.state or 'in no known state'}, not open")
        if pr.base != "main":
            raise Refused(f"PR #{pr.number} targets {pr.base!r}, not main")
        if pr.mergeable == "CONFLICTING":
            raise Refused(f"PR #{pr.number} conflicts with main: merge origin/main into {pr.branch} locally and push "
                          "(never update-branch or the web editor: the merge drivers run only in a local merge)")
        if not SHA.fullmatch(pr.head):
            raise Refused(f"PR #{pr.number} has no full head SHA ({pr.head!r})")

    # ------------------------------------------------------------ 2. main red

    def slug(self) -> str:
        ci_pass = self.ci_pass()
        try:
            return str(ci_pass.repo_slug(self.root))
        except ci_pass.CiPassError as e:
            raise LandError(f"cannot name the GitHub repository: {e}") from e

    def ci_pass(self) -> ModuleType:
        module = load_tool(self.root / "tools/hosts/deploy/ci_pass.py", "ci_pass")
        if module is None:
            raise LandError("tools/hosts/deploy/ci_pass.py is missing")
        return module

    def check_main(self) -> None:
        ci_pass = self.ci_pass()

        def gh(args: list[str], _timeout: int) -> str:
            try:
                return self.gh(args)
            except LandError as e:
                raise ci_pass.Unreadable(str(e)) from e

        slug = self.slug()
        main_sha = str(as_dict(self.gh_json(["api", f"repos/{slug}/commits/main"], "main's commit"),
                               "main's commit").get("sha", ""))
        red, line = ci_pass.main_red(main_sha, self.root, gh)
        self.say(line)
        if red:
            raise Refused(f"main is red: no merges. {MAIN_RED_RULE}")

    # ------------------------------------------------------------ 3. the check on the head

    def head_now(self, number: int) -> tuple[str, str, str]:
        """The PR's head SHA, state and mergeable, read again."""
        obj = as_dict(self.gh_json(["pr", "view", str(number), "--json", "headRefOid,state,mergeable"],
                                   f"PR #{number}"), f"PR #{number}")
        return str(obj.get("headRefOid", "")), str(obj.get("state", "")), str(obj.get("mergeable", ""))

    def head_guard(self, pr: PullRequest, *, every: float = 0) -> None:
        """Read the PR again (at most once per `every` seconds): Refused when it closed or conflicts, HeadMoved with
        the PR read whole when its head is not `pr.head`."""
        if self._last_read is not None and self.clock() - self._last_read < every:
            return
        self._last_read = self.clock()
        head, state, mergeable = self.head_now(pr.number)
        if state != "OPEN" or mergeable == "CONFLICTING" or head != pr.head:
            moved = self.read_pr(pr.number)
            self.check_pr(moved)
            if moved.head != pr.head:
                line = f"head moved from {pr.head[:12]} to {moved.head[:12]}; waiting for its check"
                self.say(line)
                self.event(pr.number, None, line)
                raise HeadMoved(moved)

    def turn_guard(self, pr: PullRequest) -> None:
        """head_guard for the wait for the queue's head: a gh read that fails is one line and is tried again at the
        next poll; a PR that closed, conflicts or has a new head still stops the wait."""
        try:
            self.head_guard(pr, every=self.poll)
        except (Refused, HeadMoved):
            raise
        except LandError as e:
            self._last_read = None
            self.say(f"PR #{pr.number} not read again while waiting for its turn ({e}); trying again at the next poll")

    def check_run(self, slug: str, sha: str) -> Run | None:
        data = as_dict(self.gh_json(["api", f"repos/{slug}/commits/{sha}/check-runs?check_name={CHECK}&per_page=100"],
                                    f"the check runs of {sha[:12]}"), "the check runs")
        runs = [r for r in as_list(data.get("check_runs") or [], "check_runs")
                if r.get("name") == CHECK and r.get("head_sha") == sha]
        if not runs:
            return None
        newest = max(runs, key=lambda r: int(str(r.get("id", 0))))
        return Run(int(str(newest["id"])), str(newest.get("status", "")),
                   None if newest.get("conclusion") is None else str(newest.get("conclusion")),
                   str(newest.get("html_url", "")))

    def wait(self, what: str, fetch: Callable[[], Run | None], *, guard: Callable[[], None] = lambda: None) -> Run:
        """Poll `fetch` until a run exists (REGISTER_WAIT) and then until it completes (RUN_WAIT); `guard` runs
        before every poll and raises to stop."""
        start = self.clock()
        registered: float | None = None
        said = False
        while True:
            guard()
            run = fetch()
            if run is None:
                if self.clock() - start > REGISTER_WAIT:
                    raise LandError(f"no {what} registered after {REGISTER_WAIT} s")
                if not said:
                    self.say(f"waiting for GitHub to register the {what}")
                    said = True
            else:
                if registered is None:
                    registered = self.clock()
                    self.say(f"{what}: run {run.id} {run.status} {run.url}".rstrip())
                if run.status == "completed":
                    return run
                if self.clock() - registered > RUN_WAIT:
                    raise LandError(f"the {what} ({run.url or run.id}) did not finish in {RUN_WAIT} s")
            self.sleep(self.poll)

    def wait_check(self, pr: PullRequest, slug: str) -> PullRequest:
        """Wait for `check` to pass on the PR's head; a new head is waited for in its place (HeadMoved). Returns the
        PR whose head passed."""
        while True:
            try:
                self._wait_check_once(pr, slug)
                return pr
            except HeadMoved as moved:
                pr = moved.pr

    def _wait_check_once(self, pr: PullRequest, slug: str) -> None:
        def guard() -> None:
            self.head_guard(pr)

        if pr.draft:
            self.say(f"PR #{pr.number} is a draft: GitHub's `{CHECK}` is its gate; it is marked ready only once that "
                     "passed")
        run = self.wait(f"`{CHECK}` check on {pr.head[:12]}", lambda: self.check_run(slug, pr.head), guard=guard)
        guard()             # a push during the last poll: its check is the one to wait for
        if run.conclusion != "success":
            stays = " The PR stays a draft." if pr.draft else ""
            raise Refused(f"`{CHECK}` on {pr.head[:12]} ended {run.conclusion} ({run.url}): not merging.{stays}")

    # ------------------------------------------------------------ 3b. a draft leaves draft on the pass

    def mark_ready(self, pr: PullRequest) -> None:
        """`gh pr ready N` for a draft whose check passed on its head (wait_check ran first)."""
        if not pr.draft:
            return
        self.gh(["pr", "ready", str(pr.number)])
        self.say(f"PR #{pr.number} marked ready: `{CHECK}` passed on {pr.head[:12]}")

    # ------------------------------------------------------------ 4. merge

    def merge(self, pr: PullRequest, squash: bool) -> str:
        self.gh(["pr", "merge", str(pr.number), "--squash" if squash else "--merge", "--match-head-commit", pr.head])
        start = self.clock()
        while True:
            obj = as_dict(self.gh_json(["pr", "view", str(pr.number), "--json", "state,mergeCommit"],
                                       f"PR #{pr.number}"), f"PR #{pr.number}")
            commit = obj.get("mergeCommit")
            sha = str(commit.get("oid", "")) if isinstance(commit, dict) else ""
            if obj.get("state") == "MERGED" and SHA.fullmatch(sha):
                return sha
            if self.clock() - start > MERGED_WAIT:
                raise LandError(f"gh merged PR #{pr.number} but GitHub names no merge commit after {MERGED_WAIT} s")
            self.sleep(self.poll)

    # ------------------------------------------------------------ 5. main's push run

    def push_run(self, sha: str) -> Run | None:
        if not SHA.fullmatch(sha):
            raise LandError(f"main's push run is looked up by the full 40-character SHA, not {sha!r}")
        runs = as_list(self.gh_json(["run", "list", "--workflow", WORKFLOW, "--branch", "main", "--event", "push",
                                     "--commit", sha, "--json", "databaseId,status,conclusion,url,headSha"],
                                    "main's push runs"), "main's push runs")
        mine = [r for r in runs if r.get("headSha") == sha]
        if not mine:
            return None
        newest = max(mine, key=lambda r: int(str(r.get("databaseId", 0))))
        conclusion = newest.get("conclusion")
        return Run(int(str(newest["databaseId"])), str(newest.get("status", "")),
                   str(conclusion) if conclusion else None, str(newest.get("url", "")))

    def watch_main(self, sha: str) -> int:
        try:
            run = self.wait(f"push run of {WORKFLOW} on main for {sha[:12]}", lambda: self.push_run(sha))
        except LandError as e:
            self.say(f"main's push run not watched to the end: {e}. Watch it by hand: gh run list --workflow "
                     f"{WORKFLOW} --branch main --event push --commit {sha}")
            return UNWATCHED_EXIT
        if run.conclusion == "success":
            self.say(f"main's push run {run.id} passed ({run.url})")
            return 0
        self.say(f"main's push run {run.id} ended {run.conclusion} ({run.url}). {MAIN_RED_RULE}")
        return MAIN_RED_EXIT

    # ------------------------------------------------------------ 6. overlap

    def open_prs(self, merged: int) -> list[dict[str, object]]:
        raw = as_list(self.gh_json(["pr", "list", "--state", "open", "--limit", "200", "--json",
                                    "number,headRefName,files"], "the open PRs"), "the open PRs")
        return [p for p in raw if p.get("number") != merged]

    def overlaps(self, files: Sequence[str], prs: list[dict[str, object]], module: ModuleType) -> dict[int, list[str]]:
        """Open PR number -> the merged PR's files it also changes, merge-driver paths left out
        (tools/ops/orient_overlap.py's overlaps_for, the one overlap rule)."""
        shared: dict[int, list[str]] = {}
        for item in module.overlaps_for(files, self.root, root=self.root, prs=module.parse_prs(prs)):
            if item.auto_merge:
                continue
            for label in item.places:
                m = PR_LABEL.search(label)
                if m:
                    shared.setdefault(int(m.group(1)), []).append(item.path)
        return shared

    def report_overlap(self, pr: PullRequest, module: ModuleType | None) -> None:
        if module is None or not hasattr(module, "overlaps_for"):
            self.say(f"overlap not read ({OVERLAP_TOOL} not found): check the open PRs by hand")
            return
        try:
            shared = self.overlaps(pr.files, self.open_prs(pr.number), module)
        except LandError as e:
            self.say(f"overlap not read ({e}): check the open PRs by hand")
            return
        self.say(f"overlap (from {OVERLAP_TOOL}):" + ("" if shared else " none"))
        for number in sorted(shared):
            self.say(f"PR #{number} must merge origin/main locally: shares {', '.join(sorted(set(shared[number])))}")

    # ------------------------------------------------------------ 7. ships

    def ships(self, files: Sequence[str]) -> str:
        live = load_tool(self.root / "tools/hosts/live_paths.py", "live_paths")
        listed = live.shipped() if live is not None else []
        hosts = sorted(f for f in files if any(f == p or f.startswith(p + "/") for p in listed))
        site = sorted(f for f in files if f.startswith(SITE))
        parts = []
        if hosts:
            parts.append(f"layout hosts ({', '.join(hosts)})")
        if site:
            parts.append(f"site ({', '.join(site)})")
        return "ships: " + ("; ".join(parts) + ". A deploy is due; land does not deploy." if parts else "nothing")

    # ------------------------------------------------------------ 8. dashboard

    def dashboard(self, number: int, sha: str, wave: str | None, dash_out: str | None) -> None:
        script = self.root / "tools/agent/dash_rows.py"
        if not wave or not dash_out or not script.is_file():
            return
        done = subprocess.run([sys.executable, str(script), dash_out, "--wave", wave, "event", f"Merged #{number}: {sha}"],
                              capture_output=True, text=True, timeout=GH_TIMEOUT)
        if done.returncode != 0:
            self.say(f"dashboard event not written: {done.stderr.strip()}")
            return
        self.say(f"dashboard writes: {done.stdout.strip()}")

    # ------------------------------------------------------------ all of it

    def queue(self) -> LandQueue:
        return LandQueue(self.queue_dir, self.say, self.lock_sleep)

    def land(self, number: int, *, squash: bool = False, watch_main: bool = True, wave: str | None = None,
             dash_out: str | None = None, overlap_module: ModuleType | None = None, ticket: Path | None = None) -> int:
        """Steps 1 to 8 for PR `number` under the ticket at `ticket` (one is taken here when None), released at the
        end."""
        queue = self.queue()
        if ticket is None:
            other = queue.live(number)
            if other is not None:
                self.say(already_queued(other))
                return 0
            held: Ticket | None = queue.take(number, session_name())
        else:
            try:
                held = queue.adopt(ticket)      # the job's own PID on its ticket first
            except OSError:
                held = None
        if held is None:
            self.say(f"STOP: the ticket {ticket} is not in the merge queue. Nothing was merged.")
            return 1
        self.ticket_number = held.number
        try:
            return self._queued(queue, held, number, squash, watch_main, wave, dash_out, overlap_module)
        finally:
            queue.release(held)

    def _queued(self, queue: LandQueue, ticket: Ticket, number: int, squash: bool, watch_main: bool,
                wave: str | None, dash_out: str | None, overlap_module: ModuleType | None) -> int:
        """Steps 1 to 3 behind the tickets ahead, then the head of the queue and the old lock for the rest."""
        try:
            ticket = queue.update(ticket, state="waiting for its check")
            pr = self.read_pr(number)
            self.check_pr(pr)
            self.check_main()
            slug = self.slug()
            while True:
                pr = self.wait_check(pr, slug)
                ticket = queue.update(ticket, state="check passed, waiting for its turn")
                current = pr
                try:
                    ticket, waited = queue.wait_turn(ticket, lambda: self.turn_guard(current))
                    break
                except HeadMoved as moved:      # the ticket keeps its place and waits for the new head's check
                    pr = moved.pr
                    ticket = queue.update(ticket, state="waiting for its check")
        except (LandError, OSError) as e:
            self.say(f"STOP: {e}. Nothing was merged.")
            return 1
        held = ticket

        def mark(state: str) -> None:
            try:
                queue.update(held, state=state)
            except OSError as e:        # the state is for make land-status only: the land goes on
                self.say(f"ticket state {state!r} not written: {e}")

        lock = MergeLock(self.lock_path, number, self.say, self.lock_sleep)
        try:
            return self._locked(lock, pr, squash, watch_main, wave, dash_out, overlap_module,
                                waited=waited, mark=mark)
        finally:
            lock.release()

    def _locked(self, lock: MergeLock, pr: PullRequest, squash: bool, watch_main: bool, wave: str | None,
                dash_out: str | None, overlap_module: ModuleType | None, *, waited: bool = False,
                mark: Callable[[str], object] = lambda state: None) -> int:
        """Steps 4 to 8 at the head of the queue, under the old merge lock (released by the caller)."""
        number = pr.number
        try:
            if lock.take() or waited:
                self.check_main()       # main may have moved while another land merged
            mark("merging")
            self.mark_ready(pr)         # a draft leaves draft only here, just before its merge
        except LandError as e:
            self.say(f"STOP: {e}. Nothing was merged.")
            return 1
        try:
            sha = self.merge(pr, squash)
        except LandError as e:
            self.say(f"STOP after the merge call: {e}. Check PR #{number} on GitHub before anything else.")
            return UNWATCHED_EXIT
        self.say(f"Merged #{number}: {sha}")
        mark("watching main's push run")
        code = self.watch_main(sha) if watch_main else 0
        # The PR has merged: a failure from here on is one line, never a traceback, and never exit 1 ("nothing merged").
        steps: tuple[tuple[str, Callable[[], None]], ...] = (
            ("overlap", lambda: self.report_overlap(pr, overlap_module)),
            ("ships", lambda: self.say(self.ships(pr.files))),
            ("dashboard", lambda: self.dashboard(number, sha, wave, dash_out)),
        )
        for name, step in steps:
            try:
                step()
            except Exception as e:  # after the merge every step is a report; the merge stands
                self.say(f"{name} not read after the merge ({type(e).__name__}: {e}); check it by hand")
                code = code or UNWATCHED_EXIT
        return code


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="land.py", description="Merge one PR the coordinator's way: open, main not red, "
                                 "`check` passed on the head, its turn in the merge queue, merge with "
                                 "--match-head-commit, watch main's push run, then overlap and ships lines. A "
                                 "background job unless --watch. Never deploys.")
    ap.add_argument("pr", type=int, help="the PR number")
    ap.add_argument("--squash", action="store_true", help="squash-merge (the coordinator's choice only)")
    ap.add_argument("--wave", help="dashboard wave, with --dash-out")
    ap.add_argument("--dash-out", help="folder for tools/agent/dash_rows.py's documents, with --wave")
    ap.add_argument("--poll", type=float, default=POLL, help=f"seconds between polls (default {POLL})")
    ap.add_argument("--no-watch-main", action="store_true", help="tests only: skip watching main's push run")
    ap.add_argument("--watch", action="store_true", help="run in the foreground to the end, not as a background job")
    ap.add_argument("--ticket", type=Path, help=argparse.SUPPRESS)     # the background job's ticket, from detach()
    return ap


def job_args(a: argparse.Namespace, ticket: Path) -> list[str]:
    """The background job's arguments: the caller's, in the foreground, under the caller's ticket."""
    args = [str(a.pr), "--watch", "--ticket", str(ticket), "--poll", str(a.poll)]
    args += ["--squash"] if a.squash else []
    args += ["--wave", a.wave] if a.wave else []
    args += ["--dash-out", a.dash_out] if a.dash_out else []
    args += ["--no-watch-main"] if a.no_watch_main else []
    return args


Spawn = Callable[..., "subprocess.Popen[bytes]"]
MAIN_ENDS = {0: "main green", MAIN_RED_EXIT: "main red", UNWATCHED_EXIT: "main's run not watched to the end"}


def end_reason(out: Sequence[str], code: int) -> str:
    """The events.log reason for a land that ended with `code`: "merged <sha>, main green" (or red, or not
    watched) once it merged, else its last STOP line, else its last line."""
    merged = next((line for line in reversed(out) if line.startswith("Merged #")), None)
    if merged is not None:
        return f"merged {merged.rsplit(' ', 1)[-1]}, {MAIN_ENDS.get(code, f'exit {code}')}"
    stop = next((line for line in reversed(out) if line.startswith("STOP")), None)
    return stop or (out[-1] if out else "no output")


def already_queued(ticket: Ticket, log_dir: Path = LOG_DIR) -> str:
    return (f"#{ticket.pr} is already in the merge queue as {ticket.label()}, {ticket.state}; log: "
            f"{find_log(ticket.pr or 0, ticket.number, log_dir)}. Nothing new was queued.")


def detach(a: argparse.Namespace, queue_dir: Path = QUEUE_DIR, log_dir: Path = LOG_DIR,
           spawn: Spawn = subprocess.Popen) -> int:
    """Take a ticket, start the land as a background job in a session of its own, and return once the job has put
    its own PID on the ticket (this process never writes the ticket after the job starts). Exit 0 means queued, not
    merged: the job's code lands in the result file (make land-wait)."""
    queue = LandQueue(queue_dir, print)
    other = queue.live(a.pr)
    if other is not None:
        print(already_queued(other, log_dir))
        return 0
    ticket = queue.take(a.pr, session_name())
    log = log_path(a.pr, log_dir, ticket.number)
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        result_path(a.pr, log_dir).unlink(missing_ok=True)       # the old-name result is an earlier land's
        with log.open("a", encoding="utf-8") as out:
            out.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} make land PR={a.pr}: ticket {ticket.number}\n")
            out.flush()
            job = spawn([sys.executable, str(Path(__file__).resolve()), *job_args(a, ticket.path)], cwd=ROOT,
                        stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
    except BaseException:
        queue.release(ticket)
        raise
    if not queue.wait_adopted(ticket, job.pid):
        print(f"the job (PID {job.pid}) has not taken ticket {ticket.number} yet; see {log}")
    print(f"queued #{a.pr} as ticket {ticket.number} (job PID {job.pid}); log: {log}. Exit 0 means queued, not "
          f"merged: make land-status shows the queue, make land-wait PR={a.pr} waits for the result.")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        a = parser().parse_args(argv)
    except SystemExit as e:
        return 0 if e.code == 0 else 2
    if not a.watch:
        return detach(a)
    module = load_tool(ROOT / "tools/ops/orient_overlap.py", "orient_overlap")
    lander = Lander(poll=a.poll, events_dir=LOG_DIR)
    code = lander.land(a.pr, squash=a.squash, watch_main=not a.no_watch_main, wave=a.wave, dash_out=a.dash_out,
                       overlap_module=module, ticket=a.ticket)
    try:
        write_result(a.pr, lander.ticket_number, code)
    except OSError as e:
        print(f"result not written for make land-wait: {e}")
    lander.event(a.pr, code, end_reason(lander.out, code))
    print(f"land of #{a.pr} ended with exit {code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
