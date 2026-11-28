#!/usr/bin/env python3
"""Archive the progress files of lanes that are done, from the main checkout's .claude/progress/ (gitignored).

  progress_prune.py [--dry-run]   move each done lane's file to .claude/progress/archive/<date>/ (its last change)

A progress file is a .md, .log or .dash.jsonl file directly in .claude/progress/ (the `handoff` skill's lane lines
and dashboards). Its topic is its name without that suffix. It is archived when it is untouched for STALE (LONG_STALE
for a dashboard, .dash.jsonl, or a file whose name holds one of LONG_WORDS, which a later session reads back) and no
name in use matches its topic. The names in use are each worktree's folder name and branch (last part after /),
each open PR's head branch (last part), each page in wiki/projects/ whose Status is active (the main checkout's and
every worktree's copy) and the branch of each Claimed line on one. A name matches a topic when they are equal, or
one is the other followed by "-" and more (the active page data-masters keeps data-masters-L3.md).

An active page keeps a lane's file (its topic is the page's name, "-" and the lane, such as data-masters-L3) only
until that lane merged: a merged PR's head branch ends in the topic (agent/claude/data-masters-l3, any case), or a
row of a table on the page that starts with the lane (`| L3 Wiring inputs | ...`) gives a merged PR as the lane's
own (lane_prs: after "Done", or in a PR column). The merged PRs are read only when such a file is otherwise done;
when GitHub cannot list them the page keeps the file.
A lane topic used again for new work, whose earlier branch merged, is archived once no worktree, branch or open PR
uses it (those names keep it while the new work runs).

Files are moved, not deleted: the move keeps the file's time, and archive/ is never pruned. A file whose archive
name is taken stays and gets one line. When GitHub cannot list the open PRs nothing is archived, since a lane's PR
may still be open. Prints one line per file ("archived", "would archive", "left") and nothing when no file is
done. Runs from the session-start hook (.claude/hooks/worktree_sweep.py) beside the worktree sweep, and after
each land and hourly from tools/agent/housekeeping.py.
"""
from __future__ import annotations

import argparse
import functools
import importlib.util
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
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
STALE = timedelta(days=1)
LONG_STALE = timedelta(days=2)  # dashboards and hand-off, coordinator and steward files
LONG_WORDS = ("handoff", "coordinator", "steward")
GH_TIMEOUT = 20
MERGED_LIMIT = 1000
PR_REF = re.compile(r"#(\d+)\b")
DONE_PR = re.compile(r"\bDone\b[^#]*?#(\d+)\b")


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
    """The files untouched for stale_after whose topic no name in `names` matches."""
    return [f for f in files if now - f.changed >= stale_after(f) and not any(matches(n, f.topic) for n in names)]


def stale_after(f: ProgressFile) -> timedelta:
    """How long a file must sit untouched: LONG_STALE for a dashboard or a hand-off, coordinator or steward file."""
    name = f.path.name.lower()
    return LONG_STALE if name.endswith(".dash.jsonl") or any(w in name for w in LONG_WORDS) else STALE


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


@dataclass(frozen=True)
class Merged:
    heads: frozenset[str]  # last part of each merged PR's head branch, lower case
    numbers: frozenset[int]


@dataclass
class Pages:
    texts: dict[str, list[str]]  # each active page's name -> its text in every checkout that has it active
    claims: set[str]  # the branch (last part) of each claim on an active page


def active_pages(checkouts: list[Path], pages: ModuleType) -> Pages:
    """The active project pages and their claims, from every checkout's wiki/projects/."""
    found = Pages({}, set())
    for checkout in checkouts:
        folder = checkout / "wiki/projects"
        for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
            try:
                text = path.read_text(encoding="utf-8")
                page = pages.parse_page(path.name, text)
            except (OSError, UnicodeDecodeError):
                continue  # a page being written or removed by another session; the others still count
            if page.status == "active":
                found.texts.setdefault(path.stem, []).append(text)
                found.claims.update(last_part(c.branch) for c in page.claims)
    return found


def lane_prs(text: str, lane: str) -> set[int]:
    """The PRs that a table row of `text` whose first cell starts with the word `lane` (any case) gives as the lane's
    own: the first #N after "Done" in a cell (`**Done** 2026-11-25 (#1145)`), and any #N in a column headed "PR".
    Other PRs a row cites (one it waits for, an earlier fix) do not count."""
    numbers: set[int] = set()
    pr_column: int | None = None
    for line in text.splitlines():
        cells = line.strip().split("|")
        if len(cells) <= 2 or cells[0].strip():  # not a table row: a later table has its own header
            pr_column = None
            continue
        names = [c.strip().lower() for c in cells]
        if "pr" in names and not any(PR_REF.search(c) for c in cells):
            pr_column = names.index("pr")  # a header row
            continue
        words = cells[1].split()
        if not words or words[0].lower() != lane.lower():
            continue
        for i, cell in enumerate(cells):
            if i == pr_column:
                numbers.update(int(n) for n in PR_REF.findall(cell))
            done = DONE_PR.search(cell)
            if done:
                numbers.add(int(done.group(1)))
    return numbers


def lane_of(page: str, topic: str) -> str | None:
    """The lane part of `topic` when it is `page` followed by "-" and more; None otherwise."""
    prefix = page.lower() + "-"
    return topic[len(prefix):] if topic.lower().startswith(prefix) and len(topic) > len(prefix) else None


def kept_by_page(topic: str, pages: Pages, merged: Callable[[], Merged | None]) -> bool:
    """Whether an active page keeps `topic`: it matches the page and is not a lane that merged (`merged` is asked
    only for a lane; None keeps it)."""
    for page, texts in pages.texts.items():
        if not matches(page, topic):
            continue
        lane = lane_of(page, topic)
        found = merged() if lane is not None else None
        if found is None:
            return True
        if topic.lower() in found.heads:
            continue
        if not any(n in found.numbers for text in texts for n in lane_prs(text, lane or "")):
            return True
    return False


def merged_prs(main: str, limit: int = MERGED_LIMIT) -> Merged | None:
    """The newest `limit` merged PRs' numbers and head branches; None when gh cannot say."""
    try:
        listed = subprocess.run(["gh", "pr", "list", "--state", "merged", "--limit", str(limit), "--json",
                                 "number,headRefName"], cwd=main, capture_output=True, text=True, timeout=GH_TIMEOUT * 3)
        prs = json.loads(listed.stdout or "[]") if listed.returncode == 0 else None
        if not isinstance(prs, list):
            return None
        return Merged(frozenset(last_part(str(p["headRefName"])).lower() for p in prs),
                      frozenset(int(p["number"]) for p in prs))
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return None


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


def names_in_use(main: str, checkouts: list[Path], branches: list[str], pages: Pages) -> set[str]:
    """Every name that keeps a matching file, the active pages' own names left out (kept_by_page judges those)."""
    names = {p.name for p in checkouts[1:]} | {last_part(b) for b in branches}
    return names | pages.claims | open_pr_branches(main)


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
    pages = active_pages(checkouts, load_orient_pages())
    names = names_in_use(main, checkouts, [t.branch for t in trees if t.branch], pages)
    merged = functools.cache(lambda: merged_prs(main))
    finished = [f for f in done(stale, names, now) if not kept_by_page(f.topic, pages, merged)]
    return archive(finished, folder, dry_run)


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
