#!/usr/bin/env python3
"""Archive the progress files of lanes that are done, from the main checkout's .claude/progress/ (gitignored).

  progress_prune.py [--dry-run]   move each done lane's file to .claude/progress/archive/<date>/ (its last change)

A progress file is a .md, .log or .dash.jsonl file directly in .claude/progress/ (the `handoff` skill's lane lines
and dashboards). Its topic is its name without that suffix. It is archived when it is untouched for STALE and no
name in use matches its topic. The names in use are each worktree's folder name and branch (last part after /),
each open PR's head branch (last part), each page in wiki/projects/ whose Status is active (the main checkout's and
every worktree's copy) and the branch of each Claimed line on one. A name matches a topic when they are equal, or
one is the other followed by "-" and more (the active page data-masters keeps data-masters-L3.md).

Files are moved, not deleted: the move keeps the file's time, and archive/ is never pruned. A file whose archive
name is taken stays and gets one line. When GitHub cannot list the open PRs nothing is archived, since a lane's PR
may still be open. Prints one line per file ("archived", "would archive", "left") and nothing when no file is
done. Runs from the session-start hook (.claude/hooks/worktree_sweep.py) beside the worktree sweep.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

from worktrees import GitCommandError, worktrees  # this folder is on sys.path when the script runs; the tests add it

ROOT = Path(__file__).resolve().parents[2]
PAGES = ROOT / "tools/ops/orient_pages.py"  # reads a project page's Status and Claimed lines
PROGRESS = Path(".claude/progress")
ARCHIVE = "archive"
SUFFIXES = (".dash.jsonl", ".md", ".log")  # longest first: x.dash.jsonl is topic x
STALE = timedelta(days=2)
GH_TIMEOUT = 20


class PruneError(RuntimeError):
    """The names in use cannot be read (git or gh failed), so no file is archived."""


@dataclass(frozen=True)
class ProgressFile:
    path: Path
    topic: str
    changed: datetime  # the file's last change, UTC


def progress_files(folder: Path) -> list[ProgressFile]:
    """The progress files directly in `folder`, sorted by name; other files and folders are left alone."""
    if not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.iterdir()):
        suffix = next((s for s in SUFFIXES if path.name.endswith(s)), None)
        if suffix is None or not path.is_file() or path.name == suffix:
            continue
        changed = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        found.append(ProgressFile(path, path.name[: -len(suffix)], changed))
    return found


def matches(name: str, topic: str) -> bool:
    name, topic = name.lower(), topic.lower()
    return bool(name) and (name == topic or topic.startswith(name + "-") or name.startswith(topic + "-"))


def done(files: list[ProgressFile], names: set[str], now: datetime) -> list[ProgressFile]:
    """The files untouched for STALE whose topic no name in `names` matches."""
    return [f for f in files if now - f.changed >= STALE and not any(matches(n, f.topic) for n in names)]


def last_part(branch: str) -> str:
    return branch.rsplit("/", 1)[-1]


def load_orient_pages(path: Path = PAGES) -> ModuleType:
    spec = importlib.util.spec_from_file_location("hart_orient_pages", path)
    if spec is None or spec.loader is None:
        raise PruneError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses look the module up by name
    spec.loader.exec_module(module)
    return module


def page_names(checkouts: list[Path], pages: ModuleType) -> set[str]:
    """Each active project page's name and the branch of each claim on it, from every checkout's wiki/projects/."""
    names: set[str] = set()
    for checkout in checkouts:
        folder = checkout / "wiki/projects"
        for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
            try:
                page = pages.parse_page(path.name, path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue  # a page being written or removed by another session; the others still count
            if page.status == "active":
                names.add(path.stem)
                names.update(last_part(c.branch) for c in page.claims)
    return names


def open_pr_branches(main: str) -> set[str]:
    """The head branch of each open PR, last part only. PruneError when gh cannot say."""
    try:
        listed = subprocess.run(["gh", "pr", "list", "--state", "open", "--limit", "200", "--json", "headRefName"],
                                cwd=main, capture_output=True, text=True, timeout=GH_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as err:
        raise PruneError(f"gh pr list did not run: {err}") from err
    if listed.returncode != 0:
        raise PruneError(f"gh pr list failed: {listed.stderr.strip() or f'exit {listed.returncode}'}")
    try:
        return {last_part(pr["headRefName"]) for pr in json.loads(listed.stdout or "[]")}
    except (ValueError, KeyError, TypeError) as err:
        raise PruneError(f"gh pr list gave unreadable output: {err}") from err


def names_in_use(main: str, checkouts: list[Path], branches: list[str]) -> set[str]:
    names = {p.name for p in checkouts[1:]} | {last_part(b) for b in branches}
    return names | page_names(checkouts, load_orient_pages()) | open_pr_branches(main)


def archive(files: list[ProgressFile], folder: Path, dry_run: bool) -> list[str]:
    """Move each file to folder/ARCHIVE/<date of its last change>/; one line per file."""
    lines = []
    for f in files:
        target = folder / ARCHIVE / f.changed.astimezone().strftime("%Y-%m-%d") / f.path.name
        if target.exists():
            lines.append(f"left {f.path}: {target} already exists")
        elif dry_run:
            lines.append(f"would archive {f.path} (untouched since {f.changed.astimezone():%Y-%m-%d %H:%M})")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(f.path, target)
            lines.append(f"archived {f.path} to {target.parent}")
    return lines


def prune(dry_run: bool = False, now: datetime | None = None, repo: Path = ROOT) -> list[str]:
    """Archive the done progress files of `repo`'s main checkout; one line per file. PruneError when the names in
    use cannot be read."""
    try:
        trees = worktrees(repo)
    except GitCommandError as err:
        raise PruneError(str(err)) from err
    main = trees[0].path
    folder = Path(main) / PROGRESS
    now = now or datetime.now(timezone.utc)
    stale = done(progress_files(folder), set(), now)
    if not stale:  # nothing old enough: no GitHub call
        return []
    checkouts = [Path(t.path) for t in trees if os.path.isdir(t.path)]
    names = names_in_use(main, checkouts, [t.branch for t in trees if t.branch])
    return archive(done(stale, names, now), folder, dry_run)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="name the files, move nothing")
    args = parser.parse_args(argv)
    try:
        lines = prune(args.dry_run)
    except PruneError as err:
        print(f"error: progress files not pruned: {err}", file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
