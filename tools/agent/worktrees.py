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
is exactly the worktree's commit, and the worktree has no uncommitted or untracked
changes. Its local branch goes with it. A fresh worktree with no PR yet, one with work
after the merge, and the one holding DIR (the caller's own) are kept. The remote branch
is left alone. Runs from the merge hook and at session start (.claude/hooks/worktree_sweep.py).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIRRORS = ("media", "ops/car-cards", "ops/hart-ops/.venv")
TOPIC = re.compile(r"[a-z0-9][a-z0-9._-]*")


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


def merged_heads() -> dict[str, set[str]] | None:
    """Branch -> head commits of its merged PRs, or None when GitHub can't be asked."""
    try:
        done = subprocess.run(["gh", "pr", "list", "--state", "merged", "--limit", "300",
                               "--json", "headRefName,headRefOid"],
                              cwd=ROOT, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    heads: dict[str, set[str]] = {}
    for pr in json.loads(done.stdout or "[]"):
        heads.setdefault(pr["headRefName"], set()).add(pr["headRefOid"])
    return heads


def inside(path: str, keep: str | None) -> bool:
    if not keep:
        return False
    path, keep = os.path.realpath(path), os.path.realpath(keep)
    return keep == path or keep.startswith(path + os.sep)


def plan(trees: list[Worktree], heads: dict[str, set[str]], keep: str | None, dirty) -> tuple[list, list]:
    """(to remove, kept with reason) for every worktree but the main checkout."""
    remove, kept = [], []
    all_heads = set().union(*heads.values()) if heads else set()
    for tree in trees[1:]:
        if tree.branch:
            merged = tree.head in heads.get(tree.branch, set())
        else:
            merged = tree.head in all_heads
        if not merged:
            continue  # open work: no merged PR at this commit
        if tree.locked:
            kept.append((tree, "locked"))
        elif inside(tree.path, keep):
            kept.append((tree, "in use by this session; the next sweep removes it"))
        elif dirty(tree.path):
            kept.append((tree, "merged, but has uncommitted or untracked changes"))
        else:
            remove.append(tree)
    return remove, kept


def is_dirty(path: str) -> bool:
    if not os.path.isdir(path):
        return False
    return bool(git("status", "--porcelain", cwd=path))


def sweep(dry_run: bool = False, keep: str | None = None) -> list[str]:
    """Remove merged worktrees; return one line per action for the caller to show."""
    heads = merged_heads()
    if heads is None:
        return ["worktree sweep skipped: gh could not list merged PRs"]
    remove, kept = plan(worktrees(), heads, keep, is_dirty)
    lines = []
    for tree in remove:
        label = tree.branch or tree.head[:8]
        if dry_run:
            lines.append(f"would remove {tree.path} ({label})")
            continue
        if not os.path.isdir(tree.path):
            git("worktree", "prune")
        elif not git_ok("worktree", "remove", tree.path):
            lines.append(f"kept {tree.path}: git worktree remove refused")
            continue
        if tree.branch and git("rev-parse", f"refs/heads/{tree.branch}") == tree.head:
            git("branch", "-D", tree.branch)
        lines.append(f"removed {tree.path} ({label}, PR merged)")
    lines += [f"kept {tree.path} ({tree.branch or tree.head[:8]}): {why}" for tree, why in kept]
    if not dry_run:
        git("worktree", "prune")
    return lines


def git_ok(*args: str) -> bool:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, timeout=60).returncode == 0


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
        raise SystemExit(f"topic must be lower-case words joined by - or _: {topic!r}")
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
    p_sweep.add_argument("--keep", help="never remove the worktree holding this directory")
    args = parser.parse_args(argv)
    if args.cmd == "new":
        print(new(args.topic, args.agent))
    else:
        for line in sweep(args.dry_run, args.keep) or ["no merged worktrees"]:
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
