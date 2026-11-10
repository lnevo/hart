#!/usr/bin/env python3
"""Agent worktrees: one per task under .claude/worktrees/, removed once its PR is merged.

Every agent works in its own worktree, never in the main checkout, so sessions cannot
switch a branch under each other (AGENTS.md, wiki/AGENTS_GIT.md). The main checkout
stays on main for pulls and deploys.

  worktrees.py new <topic> [--agent claude]   create .claude/worktrees/<topic> on
                                              agent/<agent>/<topic> from origin/main
  worktrees.py sweep [--dry-run] [--keep DIR] remove the worktrees whose PR is merged

`new` links the gitignored mirrors the website build and the hart-ops tests need
(media/, ops/car-cards/, ops/hart-ops/.venv) from the main checkout.

`sweep` removes a worktree only when GitHub lists a merged PR for its branch whose head
is the worktree's commit or a descendant of it (so nothing local is lost), the merge is
at least GRACE old, and the worktree has no uncommitted or untracked changes. Its local
branch goes with it. A fresh worktree with no PR yet, one with work after the merge, a
detached one, and the ones holding a --keep directory (the caller's) are kept. The grace
period lets another session finish in a worktree it just merged. Remote branches are left
alone. Runs from the merge hook and at session start (.claude/hooks/worktree_sweep.py).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIRRORS = ("media", "ops/car-cards", "ops/hart-ops/.venv")
TOPIC = re.compile(r"[a-z0-9]+([-_][a-z0-9]+)*")
GRACE = timedelta(minutes=30)


@dataclass
class Worktree:
    path: str
    head: str
    branch: str | None  # None when detached
    locked: bool = False


def git(*args: str, cwd: str | Path | None = None, check: bool = False) -> str:
    done = subprocess.run(["git", "-C", str(cwd or ROOT), *args], capture_output=True, text=True, timeout=60)
    if check and done.returncode != 0:
        raise SystemExit(done.stderr.strip() or f"git {' '.join(args)} failed")
    return done.stdout.strip() if done.returncode == 0 else ""


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
        elif not line and cur:
            found.append(cur)
            cur = None
    return found


def merged_prs(branch: str, main: str) -> list[dict] | None:
    """Merged PRs for `branch` from GitHub, or None when GitHub can't be asked."""
    try:
        done = subprocess.run(["gh", "pr", "list", "--state", "merged", "--head", branch, "--limit", "20",
                               "--json", "headRefOid,mergedAt"], cwd=main, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return json.loads(done.stdout or "[]") if done.returncode == 0 else None


def merged_at(tree: Worktree, main: str, prs: list[dict] | None = None) -> datetime | None:
    """When the worktree's work was merged: the latest merged PR for its branch whose head
    is its commit or a descendant of it. None for open work, detached HEADs, or no answer."""
    if not tree.branch:
        return None
    if prs is None:
        prs = merged_prs(tree.branch, main) or []
    times = [datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00")) for pr in prs
             if pr["headRefOid"] == tree.head or git_ok("merge-base", "--is-ancestor", tree.head, pr["headRefOid"], cwd=main)]
    return max(times) if times else None


def inside(path: str, keep: list[str]) -> bool:
    path = os.path.realpath(path)
    for k in keep:
        k = os.path.realpath(k)
        if k == path or k.startswith(path + os.sep):
            return True
    return False


def plan(trees: list[Worktree], merged, keep: list[str], dirty, now: datetime | None = None) -> tuple[list, list]:
    """(to remove, kept with reason) for every worktree but the main checkout.

    `merged(tree)` returns when its work was merged, or None while it is open work.
    """
    now = now or datetime.now(timezone.utc)
    remove, kept = [], []
    for tree in trees[1:]:
        when = merged(tree)
        if when is None:
            continue  # open work, a fresh worktree, or detached
        if tree.locked:
            kept.append((tree, "locked"))
        elif inside(tree.path, keep):
            kept.append((tree, "in use by this session; a later sweep removes it"))
        elif now - when < GRACE:
            kept.append((tree, f"merged under {int(GRACE.total_seconds() // 60)} minutes ago; a later sweep removes it"))
        elif dirty(tree.path):
            kept.append((tree, "merged, but has uncommitted or untracked changes"))
        else:
            remove.append(tree)
    return remove, kept


def is_dirty(path: str) -> bool:
    if not os.path.isdir(path):
        return False
    return bool(git("status", "--porcelain", cwd=path))


def sweep(dry_run: bool = False, keep: list[str] | None = None) -> list[str]:
    """Remove merged worktrees; return one line per action for the caller to show."""
    trees = worktrees()
    if not trees:
        return ["worktree sweep skipped: no git worktrees found"]
    main = trees[0].path  # run from the main checkout, which is never removed
    if not shutil.which("gh"):
        return ["worktree sweep skipped: gh is not installed"]
    git("fetch", "-q", "origin", "main", cwd=main)
    remove, kept = plan(trees, lambda t: merged_at(t, main), keep or [], is_dirty)
    lines = []
    for tree in remove:
        label = tree.branch or tree.head[:8]
        if dry_run:
            lines.append(f"would remove {tree.path} ({label})")
            continue
        if os.path.isdir(tree.path) and not git_ok("worktree", "remove", tree.path, cwd=main):
            lines.append(f"kept {tree.path}: git worktree remove refused")
            continue
        git("worktree", "prune", cwd=main)
        if tree.branch and git("rev-parse", f"refs/heads/{tree.branch}", cwd=main) == tree.head:
            git("branch", "-D", tree.branch, cwd=main)
        lines.append(f"removed {tree.path} ({label}, PR merged)")
    lines += [f"kept {tree.path} ({tree.branch or tree.head[:8]}): {why}" for tree, why in kept]
    return lines


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
    if not TOPIC.fullmatch(topic):
        raise SystemExit(f"topic must be lower-case letters and digits, words joined by - or _: {topic!r}")
    main = Path(worktrees()[0].path)
    path = main / ".claude" / "worktrees" / topic
    branch = f"agent/{agent}/{topic}"
    if path.exists():
        raise SystemExit(f"{path} already exists")
    git("fetch", "-q", "origin", "main", cwd=main)
    git("worktree", "add", "-q", "-b", branch, str(path), "origin/main", cwd=main, check=True)
    exclude_mirrors(main)
    for rel in MIRRORS:
        src, dst = main / rel, path / rel
        if src.exists() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.symlink_to(src)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_new = sub.add_parser("new", help="create a worktree for a task")
    p_new.add_argument("topic")
    p_new.add_argument("--agent", default="claude")
    p_sweep = sub.add_parser("sweep", help="remove worktrees whose PR is merged")
    p_sweep.add_argument("--dry-run", action="store_true")
    p_sweep.add_argument("--keep", action="append", default=[], help="never remove the worktree holding this directory")
    args = parser.parse_args(argv)
    if args.cmd == "new":
        print(new(args.topic, args.agent))
    else:
        for line in sweep(args.dry_run, args.keep) or ["no merged worktrees"]:
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
