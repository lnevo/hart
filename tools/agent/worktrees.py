#!/usr/bin/env python3
"""Agent worktrees: one per task under .claude/worktrees/, removed once its PR is merged.

Every agent works in its own worktree, never in the main checkout, so sessions cannot
switch a branch under each other (AGENTS.md, wiki/AGENTS_GIT.md). The main checkout
stays on main for pulls and deploys.

  worktrees.py new <topic> [--agent claude]   create .claude/worktrees/<topic> on
                                              agent/<agent>/<topic> from origin/main
  worktrees.py sweep [--dry-run] [--keep DIR] remove merged worktrees and idle ones with nothing new
  worktrees.py submodules [PATH]              check out CHECK_SUBMODULES where missing
                                              (tools/check.sh runs it, for worktrees not made by new)

`new` links the gitignored mirrors the website build and the hart-ops tests need
(media/, ops/car-cards/, ops/hart-ops/.venv) from the main checkout, and checks out the
submodules tools/check.sh needs (CHECK_SUBMODULES) at their pinned commits. A submodule that
cannot be fetched is reported and the worktree is still made.

`sweep` removes a worktree only when GitHub lists a merged PR for its branch whose head
is the worktree's commit or a descendant of it (so nothing local is lost), or an ancestor of it whose later commits
are all on the default branch already (extras_on_base), the merge (or that later commit) is
at least GRACE old, and the worktree has no uncommitted or untracked changes. Its local
branch goes with it. git refuses to remove a worktree with a submodule checked out; the
sweep then forces it only when no submodule holds work that exists nowhere else (see
submodule_risk). A fresh worktree with no PR yet, one with work after the merge, and the
ones holding a --keep directory (the caller's) are kept. A detached worktree has no PR to
judge it by: it is removed when its commit is already on the default branch, it is clean, no
rebase, bisect or merge is stopped in it, and its index has not changed for DETACHED_IDLE (a
day; reading files leaves no trace, so another session may still be using it before then; a running session's
lock keeps it longer). Every kept worktree except plain open work gets a line saying why: "waiting" when a later
sweep removes it without anyone acting (a live session's lock, the grace period, the detached idle time), "kept"
when it needs a look (uncommitted changes, commits on no remote branch, a refused removal). The grace
period lets another session finish in a worktree it just merged. Remote branches are left
alone. The same rules apply to the worktrees of each checked-out submodule (external/model-railroad-skills keeps
its own under its .claude/worktrees/), judged by that submodule's own GitHub PRs, with three limits: only branches
named agent/* are swept (the owner keeps other lines, such as the STS ones, even when merged), only worktrees under
that submodule's own .claude/worktrees/ are removed (any other merged one is reported "outside, kept"), and vendor
submodules (SKIP_SUBMODULES) are never entered. A submodule's default branch is fetched, whatever it is called.
A worktree with nothing beyond the default branch also goes, PR or not, once clean and idle (worktree_rules.py).
Runs from the merge hook and at session start (.claude/hooks/worktree_sweep.py), and after each land and hourly
(tools/agent/housekeeping.py).
"""
from __future__ import annotations

import argparse
import functools
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # also when loaded by path (orient.py, the tests)
from worktree_rules import Probe, idle_words, merged_by_branch, merged_prs, nothing_unique_since, open_branches  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MIRRORS = ("media", "ops/car-cards", "ops/hart-ops/.venv")
# Submodules the checks import from: the schematic-maps plugin behind make panels and the Layout Editor tests.
CHECK_SUBMODULES = ("external/model-railroad-skills",)
TOPIC = re.compile(r"[a-z0-9]+([-_][a-z0-9]+)*")
GRACE = timedelta(minutes=30)
# A detached worktree has no merge time; it counts as done once untouched this long and its commit is on main.
DETACHED_IDLE = timedelta(days=1)
# Files in a worktree's git dir that mean an operation is stopped part way; such a worktree is never removed.
IN_PROGRESS = ("rebase-merge", "rebase-apply", "BISECT_LOG", "MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD")


class Waiting(str):
    """Why a worktree is kept, when a later sweep removes it without anyone acting (a live lock, the grace period,
    the detached idle time). Any other reason is a plain str and needs a look; sweep_repo words the line by it."""


@dataclass
class Worktree:
    path: str
    head: str
    branch: str | None  # None when detached
    locked: bool = False
    lock_reason: str = ""  # git's lock text; Claude Code's agent locks name the session's "pid N"


LOCK_PID = re.compile(r"\bpid (\d{1,9})\b")
LOCK_START = re.compile(r"\bstart (\w{3} \w{3} +\d{1,2} \d{2}:\d{2}:\d{2} \d{4})\b")
LOCK_IDLE = timedelta(hours=1)  # a dead session's worktree must also be untouched this long


def pid_running(pid: int) -> bool:
    """Whether a process with this id exists. Anything but a clear "no such process" counts as running, so an
    odd answer keeps the worktree."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (OSError, OverflowError, ValueError):
        return True
    return True


def process_start(pid: int) -> datetime | None:
    """When the process started (local time, as ps prints it), or None when ps cannot say."""
    try:
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=10)
        return datetime.strptime(" ".join(out.stdout.split()), "%a %b %d %H:%M:%S %Y")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def lock_session_gone(reason: str) -> bool:
    """Whether the lock text names a session that has exited: its pid runs no process, or runs one that started
    at another time than the lock records (the pid was reused), read as local time or as UTC. Unparseable text
    never counts as gone."""
    m = LOCK_PID.search(reason)
    if m is None:
        return False
    pid = int(m.group(1))
    if not pid_running(pid):
        return True
    s = LOCK_START.search(reason)
    if s is None:
        return False
    try:
        recorded = datetime.strptime(" ".join(s.group(1).split()), "%a %b %d %H:%M:%S %Y")
    except ValueError:
        return False
    started = process_start(pid)
    if started is None:
        return False
    # Claude Code writes the start time in UTC, ps prints local time; either reading of the same moment matches.
    started_utc = started.astimezone(timezone.utc).replace(tzinfo=None)
    return min(abs((t - recorded).total_seconds()) for t in (started, started_utc)) > 2


def idle_since(path: str) -> datetime | None:
    """The latest change time of the worktree's own git files (HEAD, index), or None when unreadable."""
    try:
        gitdir = Path(path) / ".git"
        base = Path(gitdir.read_text().split("gitdir:", 1)[1].strip()) if gitdir.is_file() else gitdir
        stamps = [f.stat().st_mtime for f in (base / "HEAD", base / "index") if f.exists()]
        return datetime.fromtimestamp(max(stamps), timezone.utc) if stamps else None
    except (OSError, IndexError):
        return None


def lock_held(tree: Worktree, now: datetime | None = None) -> bool:
    """Whether the worktree's lock still binds.

    Claude Code locks each agent worktree to its session's pid so the agent can be resumed. Once that session
    has exited the lock protects nothing, so it no longer binds when the session is gone
    and nothing in the worktree changed for LOCK_IDLE (a guard for a sweep that cannot see the session's
    process, such as one in another pid namespace). A live session's lock, or one with no pid, still binds."""
    if not tree.locked:
        return False
    if not lock_session_gone(tree.lock_reason):
        return True
    last = idle_since(tree.path)
    now = now or datetime.now(timezone.utc)
    return last is None or now - last < LOCK_IDLE


class GitCommandError(RuntimeError):
    """A git command failed, could not run or timed out; the message names the command, the folder and git's stderr."""


class WorktreeError(ValueError):
    """A worktree cannot be made as asked: a topic that is no branch word, or a folder already there."""


def git(*args: str, cwd: str | Path | None = None) -> str:
    """git's stripped output, run in `cwd` (default the repo). GitCommandError when it fails, cannot run or hangs;
    a caller that expects a failure (an unset ref, an offline fetch) catches it."""
    where = cwd or ROOT
    command = f"git {' '.join(args)}"
    try:
        done = subprocess.run(["git", "-C", str(where), *args], capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired as err:
        raise GitCommandError(f"{command} took over 60 s in {where}") from err
    except OSError as err:
        raise GitCommandError(f"{command} could not run in {where}: {err}") from err
    if done.returncode != 0:
        raise GitCommandError(f"{command} failed in {where}: {done.stderr.strip() or f'exit {done.returncode}'}")
    return done.stdout.strip()


def worktrees(cwd: str | Path | None = None) -> list[Worktree]:
    """Every worktree of the repo; the first is the main checkout."""
    found, cur = [], None
    for line in git("worktree", "list", "--porcelain", cwd=cwd).splitlines() + [""]:
        if line.startswith("worktree "):
            cur = Worktree(line[9:], "", None)
        elif cur and line.startswith("HEAD "):
            cur.head = line[5:]
        elif cur and line.startswith("branch refs/heads/"):
            cur.branch = line[len("branch refs/heads/"):]
        elif cur and line.startswith("locked"):
            cur.locked = True
            cur.lock_reason = line[len("locked"):].strip()
        elif not line and cur:
            found.append(cur)
            cur = None
    return found


def last_touched(path: str) -> datetime:
    """When the worktree was last used: its index file's time (checkout, add, status refresh), else the folder's."""
    try:
        index = git("rev-parse", "--path-format=absolute", "--git-path", "index", cwd=path)
    except GitCommandError:
        index = ""
    target = index if index and os.path.exists(index) else path
    return datetime.fromtimestamp(os.path.getmtime(target), timezone.utc)


_ON_BASE: dict[tuple[str, str, str], bool] = {}


def on_base(tree: Worktree, main: str, base: str | None) -> bool:
    """True when the worktree's commit is already on `base` (e.g. origin/main), so removing it loses no commit."""
    if not base:
        return False
    key = (main, tree.head, base)
    if key not in _ON_BASE:
        _ON_BASE[key] = git_ok("merge-base", "--is-ancestor", tree.head, base, cwd=main)
    return _ON_BASE[key]


def in_progress(path: str) -> bool:
    """True when a rebase, bisect, merge, cherry-pick, revert or am is stopped part way in this worktree."""
    try:
        gitdir = git("rev-parse", "--path-format=absolute", "--git-dir", cwd=path)
    except GitCommandError:
        return False
    return bool(gitdir) and any(os.path.exists(os.path.join(gitdir, name)) for name in IN_PROGRESS)


def merged_at(tree: Worktree, main: str, prs: list[dict] | None = None, base: str | None = None,
              now: datetime | None = None) -> datetime | None:
    """When the worktree's work was merged: the latest merged PR for its branch whose head
    is its commit or a descendant of it. A detached worktree counts as merged at its last use
    once its commit is on `base` and it has been idle DETACHED_IDLE. None otherwise."""
    if not tree.branch:
        # A missing folder is git's to prune; a stopped operation is someone's work in progress.
        if not os.path.isdir(tree.path) or not on_base(tree, main, base) or in_progress(tree.path):
            return None
        touched = last_touched(tree.path)
        return touched if (now or datetime.now(timezone.utc)) - touched >= DETACHED_IDLE else None
    if prs is None:
        prs = merged_prs(tree.branch, main) or []
    times = [datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00")) for pr in prs
             if pr["headRefOid"] == tree.head or git_ok("merge-base", "--is-ancestor", tree.head, pr["headRefOid"], cwd=main)]
    if not times and base:  # commits after the merged head, each one already on base: counted from the last commit
        times = [max(datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00")), commit_time(tree.head, main))
                 for pr in prs if extras_on_base(main, pr["headRefOid"], tree.head, base) == 0]
    return max(times) if times else None


def commit_time(commit: str, cwd: str) -> datetime:
    return datetime.fromisoformat(git("log", "-1", "--format=%cI", commit, cwd=cwd))


@functools.lru_cache(maxsize=None)
def extras_on_base(main: str, merged: str, head: str, base: str) -> int | None:
    """How many commits after the merged PR head `merged` are not on `base`; None when `merged` is no ancestor of
    `head` or git cannot say. A commit counts as on base when its patch is (git cherry marks it "-"); a merge
    commit has no patch, so a range holding one counts in full unless merging `head` into base would change
    nothing (git merge-tree gives base's own tree), which also covers a branch that merged base back in."""
    if not git_ok("merge-base", "--is-ancestor", merged, head, cwd=main):
        return None
    try:
        new = [m for m in git("cherry", base, head, merged, cwd=main).splitlines() if m.startswith("+")]
        merges = git("rev-list", "--merges", head, f"^{merged}", f"^{base}", cwd=main).splitlines()
        if not new and not merges:
            return 0
        same = git("merge-tree", "--write-tree", base, head, cwd=main) == git("rev-parse", f"{base}^{{tree}}", cwd=main)
    except GitCommandError:
        return None
    return 0 if same else len(new) + len(merges)


def inside(path: str, keep: list[str]) -> bool:
    path = os.path.realpath(path)
    for k in keep:
        k = os.path.realpath(k)
        if k == path or k.startswith(path + os.sep):
            return True
    return False


def under(path: str, folder: str) -> bool:
    folder = os.path.realpath(folder)
    return os.path.realpath(path).startswith(folder + os.sep)


def plan(trees: list[Worktree], merged, keep: list[str], dirty, now: datetime | None = None,
         home: str | None = None, why_open=None) -> tuple[list, list]:
    """(to remove, kept with reason) for every worktree but the main checkout.

    `merged(tree)` returns when its work was merged, or None while it is open work; `why_open(tree)`, when given,
    names why such a worktree stays (None for plain open work, which is not listed). With `home` (the repository's
    own .claude/worktrees/ folder; given for submodules only) a worktree anywhere else is never removed: it may be
    another session's working copy.
    """
    now = now or datetime.now(timezone.utc)
    remove, kept = [], []
    for tree in trees[1:]:
        when = merged(tree)
        if when is None:
            reason = why_open(tree) if why_open else None
            if reason:
                kept.append((tree, reason))
            continue  # open work or a fresh worktree
        if home is not None and not under(tree.path, home):
            kept.append((tree, "outside, kept (not under .claude/worktrees/ of its repository)"))
        elif lock_held(tree, now):
            kept.append((tree, Waiting("locked")))
        elif inside(tree.path, keep):
            kept.append((tree, Waiting("in use by this session; a later sweep removes it")))
        elif now - when < GRACE:
            kept.append((tree, Waiting(f"merged under {int(GRACE.total_seconds() // 60)} minutes ago; a later sweep "
                                        "removes it")))
        elif dirty(tree.path):
            kept.append((tree, "merged, but has uncommitted or untracked changes"))
        else:
            remove.append(tree)
    return remove, kept


def is_dirty(path: str) -> bool:
    if not os.path.isdir(path):
        return False
    try:
        return bool(git("--no-optional-locks", "status", "--porcelain", cwd=path))
    except GitCommandError:
        return True  # a checkout git cannot read may hold work: keep it


# Submodules the sweep never enters: vendor source (AGENTS.md: external/lcos-bridge is not ours to change).
SKIP_SUBMODULES = ("external/lcos-bridge",)
# In a submodule only the agents' own branches are swept: the owner keeps other lines (the STS ones) even when merged.
SUBMODULE_BRANCH_PREFIX = "agent/"


def submodule_repos(main: str) -> list[str]:
    """The checked-out submodules of the main checkout, as absolute paths. A submodule keeps its own worktrees (the
    plugin's agents work in external/model-railroad-skills/.claude/worktrees/), which a sweep of the parent never
    sees, so each is swept as a repository of its own. Vendor submodules (SKIP_SUBMODULES) are left out."""
    listed = git_run("submodule", "foreach", "--quiet", "--recursive", 'echo "$toplevel/$sm_path"', cwd=main)
    if listed.returncode != 0:
        return []
    found = [p for p in listed.stdout.splitlines() if p and os.path.isdir(p)]
    skipped = {os.path.realpath(os.path.join(main, rel)) for rel in SKIP_SUBMODULES}
    return [p for p in found if os.path.realpath(p) not in skipped]


def default_branch(repo: str) -> str | None:
    """The repository's default branch as origin names it (origin/HEAD: main, master), or None when it is not set."""
    try:
        ref = git("symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", cwd=repo)
    except GitCommandError:  # --quiet: exit 1 and no message when origin/HEAD is not set
        return None
    return ref.split("/", 1)[1] if ref.startswith("origin/") else None


class Clock:
    """What a sweep has used so far: `removing` is the time spent removing worktrees (the budget counts only this,
    not planning or network time), `began` when the sweep started (for the submodule cap)."""

    def __init__(self) -> None:
        self.removing = 0.0
        self.began = time.monotonic()

    def elapsed(self) -> float:
        return time.monotonic() - self.began


# A sweep that has run this long (seconds) over its budget starts no further submodule: each costs a fetch and a
# GitHub call, and the hook's own timeout (TIMEOUT 45 s) must stay out of reach.
SUBMODULE_SLACK = 10.0


def spent(budget: float | None, clock: Clock) -> bool:
    return budget is not None and clock.removing > budget


def sweep(dry_run: bool = False, keep: list[str] | None = None, budget: float | None = None) -> list[str]:
    """Remove merged worktrees of this repository and of its submodules; return one line per action.

    With `budget` (seconds of removal time only; planning and network time do not count), no removal starts once it
    is spent, and no further submodule is looked at (its fetch and GitHub call are network time). A sweep also starts
    no further submodule once its total time passes budget + SUBMODULE_SLACK: the hook runs the sweep under a hard
    timeout, and a pile of worktrees is better left for the next sweep than cut off mid-delete. Every submodule
    line ends with the submodule's path. A git call that times out in a submodule is reported and the sweep goes on.
    """
    keep = keep or []
    trees = worktrees()
    if not trees:
        return ["worktree sweep skipped: no git worktrees found"]
    main = trees[0].path  # run from the main checkout, which is never removed
    if not shutil.which("gh"):
        return ["worktree sweep skipped: gh is not installed"]
    clock = Clock()
    lines = sweep_repo(main, trees, dry_run, keep, budget, clock, "main", None, None)
    try:
        subs = submodule_repos(main)
    except subprocess.TimeoutExpired:
        return lines + ["left the submodules for the next sweep: listing them timed out"]
    for sub in subs:
        tag = f" [submodule {os.path.relpath(sub, main)}]"
        if not dry_run and budget is not None and (spent(budget, clock) or clock.elapsed() > budget + SUBMODULE_SLACK):
            lines.append(f"left the remaining submodules for the next sweep (time budget {budget:g}s; "
                         f"make wt-sweep sweeps them now){tag}")
            break
        try:
            sub_trees = worktrees(sub)
            lines += [line + tag for line in
                      sweep_repo(sub, sub_trees, dry_run, keep, budget, clock, default_branch(sub),
                                 os.path.join(sub, ".claude", "worktrees"), SUBMODULE_BRANCH_PREFIX)]
        except subprocess.TimeoutExpired:
            lines.append(f"left this submodule for the next sweep: a git call timed out{tag}")
        except GitCommandError as err:      # a hung or broken submodule: report it, sweep the others
            lines.append(f"left this submodule for the next sweep: {err}{tag}")
    return lines


def sweep_repo(main: str, trees: list[Worktree], dry_run: bool, keep: list[str], budget: float | None,
               clock: Clock, branch: str | None, home: str | None, prefix: str | None) -> list[str]:
    """Sweep the worktrees of one repository whose working folder is `main`; `clock` is the sweep's.

    `trees` is `git worktree list`: its first entry is the main checkout, which is never removed (for a submodule
    whose git folder sits under the parent's .git/modules it is that folder, so `main`'s own path is dropped too).
    `branch` is the default branch to fetch. `home`, when given, is the only folder worktrees are removed from (a
    submodule's own .claude/worktrees/): others are reported "outside, kept". `prefix`, when given, limits the sweep
    to branches starting with it. A repository with nothing to sweep costs no network call."""
    own = os.path.realpath(main)
    candidates = [t for t in trees[1:] if os.path.realpath(t.path) != own
                  and (prefix is None or (t.branch or "").startswith(prefix))]
    if not candidates:
        return []
    try:
        git("fetch", "-q", "origin", *([branch] if branch else []), cwd=main)
    except GitCommandError:
        pass  # offline: the sweep works from the remote refs as last fetched
    by_branch = merged_by_branch(main)
    base = f"origin/{branch}" if branch else None
    opened, idle, now = functools.cache(lambda: open_branches(main)), set(), datetime.now(timezone.utc)

    def merged(t: Worktree) -> datetime | None:  # with no batch (GitHub refused it) merged_at asks per branch
        when = merged_at(t, main, None if by_branch is None else by_branch.get(t.branch or "", []), base=base)
        probe = Probe(lambda: on_base(t, main, base), lambda: in_progress(t.path), lambda: last_touched(t.path),
                      lambda: is_dirty(t.path))
        if when is None and (when := nothing_unique_since(t.path, t.branch, probe, opened, now)):
            idle.add(t.path)
        return when

    def why_open(tree: Worktree) -> str | None:
        if not os.path.isdir(tree.path):
            return None
        if not tree.branch:
            if not on_base(tree, main, base):
                return f"detached, with commits not on {base or 'the default branch'}"
            if in_progress(tree.path):
                return "detached, with a rebase, bisect or merge stopped part way"
            return Waiting(f"detached, its commit is on {base}; removed once untouched for {DETACHED_IDLE.days} day(s)")
        prs = by_branch.get(tree.branch, []) if by_branch is not None else (merged_prs(tree.branch, main) or [])
        # Commits after the merge: some merged head is an ancestor of this worktree's commit. A new worktree that
        # reuses an old topic name starts from main instead, and is plain open work.
        counts = [n for pr in prs if base and (n := extras_on_base(main, pr["headRefOid"], tree.head, base))]
        if counts:
            return f"its PR is merged, but {min(counts)} commit(s) after the merged head are not on {base}"
        if any(git_ok("merge-base", "--is-ancestor", pr["headRefOid"], tree.head, cwd=main) for pr in prs):
            return "its PR is merged, but this worktree has commits after the merged head"
        return None

    remove, kept = plan([Worktree(main, "", None)] + candidates, merged, keep, is_dirty, home=home,
                        why_open=why_open)
    lines = []
    for i, tree in enumerate(remove):
        label = tree.branch or tree.head[:8]
        if not dry_run and spent(budget, clock):
            lines.append(f"left {len(remove) - i} merged worktree(s) for the next sweep (time budget {budget:g}s; "
                         "make wt-sweep removes them now)")
            break
        if dry_run:
            lines.append(f"would remove {tree.path} ({label})")
            continue
        began = time.monotonic()
        try:
            if tree.locked:  # planned only when its session has exited and it sat idle
                unlocked = git_run("worktree", "unlock", tree.path, cwd=main)
                if unlocked.returncode != 0:
                    lines.append(f"kept {tree.path}: git worktree unlock refused: {unlocked.stderr.strip()}")
                    continue
            if os.path.isdir(tree.path):
                why = remove_worktree(tree.path, main)
                if why:
                    if tree.locked:  # put the lock back as it was, so the refusal changes nothing
                        git_run("worktree", "lock", "--reason", tree.lock_reason, tree.path, cwd=main)
                    lines.append(f"kept {tree.path}: {why}")
                    continue
            cleanup = after_removal(tree, main)
        finally:
            clock.removing += time.monotonic() - began
        why = ("PR merged" if tree.branch else f"detached, commit on {base}, untouched {DETACHED_IDLE.days} day(s)") \
            if tree.path not in idle else f"nothing beyond {base}, untouched {idle_words(tree.path)}"
        lines.append(f"removed {tree.path} ({label}, {why})" + "".join(f"; {c}" for c in cleanup))
    lines += [f"{'waiting' if isinstance(why, Waiting) else 'kept'} {tree.path} ({tree.branch or tree.head[:8]}): {why}"
              for tree, why in kept]
    return lines


def after_removal(tree: Worktree, main: str) -> list[str]:
    """Prune the removed worktree's record and delete its branch when it still points at the worktree's commit.
    The folder is already gone, so a failure here is reported, one note each, and the sweep goes on."""
    notes = []
    try:
        git("worktree", "prune", cwd=main)
    except GitCommandError as err:
        notes.append(f"worktree prune failed: {err}")
    try:
        if tree.branch and branch_head(tree.branch, main) == tree.head:
            git("branch", "-D", tree.branch, cwd=main)
    except GitCommandError as err:
        notes.append(f"branch delete failed: {err}")
    return notes


def remove_worktree(path: str, main: str) -> str | None:
    """Remove one planned worktree; None when it is gone, else why it was kept.

    git refuses any worktree with a submodule checked out, and check.sh needs one in every
    worktree. Only that refusal is forced, and only when the worktree is still clean and no
    submodule holds work that exists nowhere else.
    """
    done = git_run("worktree", "remove", path, cwd=main)
    if done.returncode == 0:
        return None
    refusal = done.stderr.strip()
    if "submodule" not in refusal:
        return f"git worktree remove refused: {refusal}"
    if is_dirty(path):
        return "git worktree remove refused: changes appeared since the plan"
    why = submodule_risk(path)
    if why:
        return f"git worktree remove refused ({why})"
    forced = git_run("worktree", "remove", "--force", path, cwd=main)
    return None if forced.returncode == 0 else f"forced remove failed: {forced.stderr.strip()}"


def submodule_risk(path: str) -> str | None:
    """Why a forced remove could lose work in this worktree's checked-out submodules, or None.

    A forced remove deletes each submodule's git dir (under .git/worktrees/<wt>/modules/), so
    besides its files it checks every local branch and HEAD are on a remote-tracking branch
    and there is no stash. The remote refs are as last fetched; the sweep does not fetch them.
    """
    listed = git_run("submodule", "foreach", "--quiet", "--recursive", 'echo "$displaypath"', cwd=path)
    if listed.returncode != 0:
        return "submodule listing failed"
    for rel in listed.stdout.splitlines():
        sub = os.path.join(path, rel)
        try:
            if os.path.realpath(git("rev-parse", "--show-toplevel", cwd=sub)) != os.path.realpath(sub):
                return f"submodule {rel} is not a readable checkout"
            # The parent's status already shows submodule changes, unless submodule.<name>.ignore hides them.
            if git("--no-optional-locks", "status", "--porcelain", cwd=sub):
                return f"changes in submodule {rel}"
            if git("rev-list", "-n1", "HEAD", "--branches", "--not", "--remotes", cwd=sub):
                return f"submodule {rel} has commits on no remote branch"
        except GitCommandError as err:
            return f"submodule {rel} is not a readable checkout: {err}"
        if git_ok("rev-parse", "-q", "--verify", "refs/stash", cwd=sub):
            return f"submodule {rel} has a stash"
    return None


def branch_head(branch: str, cwd: str | Path) -> str | None:
    """The commit a local branch points at, or None when there is no such branch."""
    try:
        return git("rev-parse", "--verify", "-q", f"refs/heads/{branch}", cwd=cwd)
    except GitCommandError:
        return None


def git_run(*args: str, cwd: str | Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd or ROOT), *args], capture_output=True, text=True, timeout=120)


def git_ok(*args: str, cwd: str | Path | None = None) -> bool:
    return subprocess.run(["git", "-C", str(cwd or ROOT), *args], capture_output=True, timeout=60).returncode == 0


def exclude_mirrors(main: Path) -> None:
    """List the mirror links in the shared info/exclude: .gitignore's `.venv/` matches only a
    directory, so a symlink would show as untracked and the sweep would keep the worktree."""
    common = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=main))
    exclude = common / "info" / "exclude"
    have = exclude.read_text(encoding="utf-8").splitlines() if exclude.exists() else []
    missing = [f"/{rel}" for rel in MIRRORS if f"/{rel}" not in have]
    if missing:
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a", encoding="utf-8") as f:
            f.write("".join(f"{line}\n" for line in ["# agent worktree mirror links (tools/agent/worktrees.py)", *missing]))


def new(topic: str, agent: str) -> Path:
    """A worktree for `topic` on the branch agent/<agent>/<topic>, from origin/main, its mirrors linked.
    WorktreeError on a bad topic or a folder already there; GitCommandError when git fails."""
    if not TOPIC.fullmatch(topic):
        raise WorktreeError(f"topic must be lower-case letters and digits, words joined by - or _: {topic!r}")
    main = Path(worktrees()[0].path)
    path = main / ".claude" / "worktrees" / topic
    branch = f"agent/{agent}/{topic}"
    if path.exists():
        raise WorktreeError(f"{path} already exists")
    try:
        git("fetch", "-q", "origin", "main", cwd=main)
    except GitCommandError as err:
        print(f"warning: {err}; the worktree starts from origin/main as last fetched", file=sys.stderr)
    git("worktree", "add", "-q", "-b", branch, str(path), "origin/main", cwd=main)
    exclude_mirrors(main)
    for rel in MIRRORS:
        src, dst = main / rel, path / rel
        if src.exists() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.symlink_to(src)
    init_check_submodules(path, main)
    install_merge_drivers(path)
    build_status_page(path)
    return path


STATUS_PAGE = "tools/ops/status_counts.py"  # builds the gitignored wiki/STATUS.md from wiki/status/ (ADR-038)


def build_status_page(path: Path) -> bool:
    """Build wiki/STATUS.md in the new worktree from its own STATUS_PAGE, so readers by path find it there too. A
    checkout from before ADR-038 has no folder to build from. Warn on stderr and return False when it fails."""
    script = path / STATUS_PAGE
    if not (path / "wiki/status").is_dir() or not script.is_file():
        return True
    try:
        done = subprocess.run([sys.executable, str(script), "--quiet"], cwd=path, capture_output=True, text=True,
                              timeout=60)
    except (OSError, subprocess.SubprocessError) as err:
        print(f"warning: wiki/STATUS.md not built ({err}); run make status", file=sys.stderr)
        return False
    if done.returncode != 0:
        print(f"warning: wiki/STATUS.md: {(done.stdout + done.stderr).strip()}; run make status", file=sys.stderr)
        return False
    return True


MERGE_DRIVERS = "tools/ops/merge_pipeline_map.py"  # sets the pipeline map's git merge drivers (--install)


def install_merge_drivers(path: Path) -> bool:
    """Set the repo's git merge drivers from the new worktree's own copy of MERGE_DRIVERS. git config is shared by
    every worktree, so this is a no-op once set. A checkout without the script has no driver to set. Warn on stderr
    and return False when it fails; what it changed goes to stderr too (stdout is the worktree path)."""
    script = path / MERGE_DRIVERS
    if not script.is_file():
        return True
    try:
        done = subprocess.run([sys.executable, str(script), "--install", "--repo", str(path)], capture_output=True,
                              text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as err:
        print(f"warning: could not set the git merge drivers ({err}); run python3 {MERGE_DRIVERS} --install",
              file=sys.stderr)
        return False
    if done.returncode != 0:
        print(f"warning: could not set the git merge drivers: {done.stderr.strip()}; run python3 {MERGE_DRIVERS} "
              f"--install", file=sys.stderr)
        return False
    if done.stdout.strip():
        print(done.stdout.strip(), file=sys.stderr)
    return True


def init_check_submodules(path: Path, main: Path) -> bool:
    """Check out each CHECK_SUBMODULES entry that is not checked out at path; warn on stderr when one fails.
    Return False when one failed."""
    ok = True
    for rel in CHECK_SUBMODULES:
        if not (path / rel).is_dir() or (path / rel / ".git").exists():  # not a submodule here, or checked out
            continue
        problem = init_submodule(path, rel, main)
        if problem:
            ok = False
            print(f"warning: {rel} is not checked out ({problem}); run git submodule update --init {rel}",
                  file=sys.stderr)
    return ok


# One git call in init_submodule may take this long (seconds); kept under the 120 s an agent's shell call allows.
SUBMODULE_TIMEOUT = 90


def init_submodule(path: Path, rel: str, main: Path | None = None) -> str:
    """Check out the submodule at rel in the worktree at path; return why it failed, or "" when it worked.

    The clone borrows objects from the main checkout's copy of the submodule when there is one, then copies them
    in and drops the link (what git clone --dissociate does), so only missing commits come over the network and
    the worktree does not depend on the main checkout afterwards. Git never prompts: no terminal, ssh in batch mode.
    """
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_SSH_COMMAND": "ssh -o BatchMode=yes"}
    cmd = ["git", "-C", str(path), "submodule", "update", "--init", "-q"]
    if main is not None and (main / rel / ".git").exists():
        cmd += ["--reference", str(main / rel)]
    try:
        done = subprocess.run([*cmd, "--", rel], capture_output=True, text=True, timeout=SUBMODULE_TIMEOUT, env=env)
        if done.returncode != 0:
            lines = done.stderr.strip().splitlines()
            causes = [ln for ln in lines if ln.lower().startswith(("fatal:", "error:"))]
            return (causes or lines or ["git failed"])[0]
        sub = path / rel
        gitdir = Path(git("rev-parse", "--absolute-git-dir", cwd=sub))
        alternates = gitdir / "objects/info/alternates"
        if alternates.exists():
            done = subprocess.run(["git", "-C", str(sub), "repack", "-a", "-d", "-q"], capture_output=True,
                                  text=True, timeout=SUBMODULE_TIMEOUT)
            if done.returncode != 0:
                return f"checked out, but copying the borrowed objects failed: {done.stderr.strip()[:200]}"
            alternates.unlink()
    except subprocess.TimeoutExpired:
        return f"timed out after {SUBMODULE_TIMEOUT} s"
    except GitCommandError as err:
        return str(err)
    except OSError as e:
        return f"could not run git: {e}"
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_new = sub.add_parser("new", help="create a worktree for a task")
    p_new.add_argument("topic")
    p_new.add_argument("--agent", default="claude")
    p_subs = sub.add_parser("submodules", help="check out the submodules the checks need, if missing")
    p_subs.add_argument("path", nargs="?", default=".", help="the checkout (default: the current folder)")
    p_sweep = sub.add_parser("sweep", help="remove worktrees whose PR is merged")
    p_sweep.add_argument("--dry-run", action="store_true")
    p_sweep.add_argument("--budget", type=float, help="seconds after which no further removal starts")
    p_sweep.add_argument("--keep", action="append", default=[], help="never remove the worktree holding this directory")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (GitCommandError, WorktreeError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1


def run(args: argparse.Namespace) -> int:
    if args.cmd == "new":
        print(new(args.topic, args.agent))
    elif args.cmd == "submodules":
        try:
            top = git("rev-parse", "--show-toplevel", cwd=args.path)
        except GitCommandError:
            top = ""
        found = worktrees(top) if top else []
        if not found:
            print(f"warning: {args.path} is not a git checkout; no submodules checked out", file=sys.stderr)
            return 1
        return 0 if init_check_submodules(Path(top), Path(found[0].path)) else 1
    else:
        for line in sweep(args.dry_run, args.keep, args.budget) or ["no merged worktrees"]:
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
