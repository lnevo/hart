"""The GitHub half of the worktree sweep (tools/agent/worktrees.py), and its rule for a worktree with nothing of its own.

merged_prs and merged_by_branch read the merged PRs that judge a branch; open_branches reads the head branches of
the open PRs. nothing_unique_since is the second way a worktree goes: it holds nothing beyond the default branch
(its commit is on origin/main, so nothing is lost whether or not a PR ever existed, and also when its PR was closed
unmerged), no rebase, bisect or merge is stopped in it, it is untouched for idle_limit (IDLE_AGENT for an
`agent-*` folder, Claude Code's own agent worktrees; IDLE_OTHER for any other), its branch has no open PR, and it
has no uncommitted or untracked changes. The sweep's plan then still keeps a worktree a live session holds, the
caller's own and the main checkout. This module imports nothing of the repo; worktrees.py imports it from their
shared folder and hands it the git reads as a Probe.
"""
from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

IDLE_AGENT = timedelta(hours=1)  # an agent-* worktree: a subagent's, locked to its session while that runs
IDLE_OTHER = timedelta(days=1)  # any other worktree (make wt, an auto-pull): its owner may come back to it
AGENT_PREFIX = "agent-"
GH_TIMEOUT = 30
PR_LIMIT = 1000


def merged_prs(branch: str, main: str) -> list[dict] | None:
    """Merged PRs for `branch` from GitHub, or None when GitHub can't be asked."""
    try:
        done = subprocess.run(["gh", "pr", "list", "--state", "merged", "--head", branch, "--limit", "20",
                               "--json", "headRefOid,mergedAt"], cwd=main, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return json.loads(done.stdout or "[]") if done.returncode == 0 else None


def merged_by_branch(main: str, limit: int = PR_LIMIT) -> dict[str, list[dict]] | None:
    """Every merged PR on GitHub, grouped by head branch, in one call; None when GitHub can't be asked.

    One call instead of one per worktree keeps a sweep of many worktrees inside the hook's timeout. A branch
    whose PR is older than the newest `limit` merges is missing here, so it counts as open work and is kept.
    """
    try:
        done = subprocess.run(["gh", "pr", "list", "--state", "merged", "--limit", str(limit),
                               "--json", "headRefName,headRefOid,mergedAt"],
                              cwd=main, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    grouped: dict[str, list[dict]] = {}
    for pr in json.loads(done.stdout or "[]"):
        grouped.setdefault(pr["headRefName"], []).append(pr)
    return grouped


def open_branches(main: str, limit: int = PR_LIMIT) -> frozenset[str] | None:
    """The head branch of every open PR, in one call; None when GitHub can't be asked, or when the list is full
    (`limit` PRs), since a branch past the limit may have one."""
    try:
        done = subprocess.run(["gh", "pr", "list", "--state", "open", "--limit", str(limit), "--json", "headRefName"],
                              cwd=main, capture_output=True, text=True, timeout=GH_TIMEOUT)
        prs = json.loads(done.stdout or "[]") if done.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if not isinstance(prs, list) or len(prs) >= limit:
        return None
    return frozenset(str(p.get("headRefName", "")) for p in prs if isinstance(p, dict))


def idle_limit(path: str) -> timedelta:
    """How long a worktree with nothing of its own must sit untouched before the sweep removes it."""
    return IDLE_AGENT if os.path.basename(os.path.normpath(path)).startswith(AGENT_PREFIX) else IDLE_OTHER


def idle_words(path: str) -> str:
    limit = idle_limit(path)
    return f"{limit.days} day(s)" if limit.days else f"{int(limit.total_seconds() // 3600)} hour(s)"


@dataclass(frozen=True)
class Probe:
    """The git reads of one worktree, each made only when the rule gets to it (cheapest first)."""
    on_base: Callable[[], bool]  # its commit is on the default branch
    stopped: Callable[[], bool]  # a rebase, bisect or merge is stopped part way
    touched: Callable[[], datetime]  # when it was last used
    dirty: Callable[[], bool]  # uncommitted or untracked changes (also when git cannot read it)


def nothing_unique_since(path: str, branch: str | None, probe: Probe, opened: Callable[[], frozenset[str] | None],
                         now: datetime) -> datetime | None:
    """When a worktree that holds nothing beyond the default branch was last used, once it qualifies for removal
    (see the module docstring); None while it holds anything, is too fresh, or GitHub cannot say whether its
    branch has an open PR (`opened`, asked only for a branch that got this far)."""
    if not os.path.isdir(path) or not probe.on_base() or probe.stopped():
        return None
    touched = probe.touched()
    if now - touched < idle_limit(path):
        return None
    if branch:
        live = opened()
        if live is None or branch in live:
            return None
    return None if probe.dirty() else touched
