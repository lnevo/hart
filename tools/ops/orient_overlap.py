"""The overlap half of tools/ops/orient.py: which files two or more pieces of parallel work both change.

A place is a live worktree of the repo (not the main checkout) or, in the full view, an open PR. A worktree's
changes are its commits since its merge base with origin/main (`git diff --name-only --no-renames MB..HEAD`) plus
what `git status` shows: staged, unstaged and untracked files that git does not ignore. A PR's changes are the
files gh lists for it (gh lists at most 100 per PR). A PR whose head branch is a local worktree counts once, as
that worktree, whose copy is the newer one. A worktree whose branch is merged is skipped: its HEAD is on origin/main
but not on origin/main's first-parent line, so a merge commit brought it in (a branch just cut from origin/main
sits on that line and is read). With no origin/main the commits are not compared and one note says so.

A path changed in two or more places is a clash, unless git gives it a merge driver of the repo's own through
.gitattributes (`git check-attr merge`, read in the main checkout: union, pipeline-map): those merge by themselves
and are listed apart as auto-merges. A clash whose places are all branches of one session's lanes (one lane prefix,
see lane) is listed apart too, one line per prefix: a session's own lanes merge in its own order.

git runs with GIT_OPTIONAL_LOCKS=0, so `git status` in another session's worktree never rewrites its index. A
worktree that cannot be read is a note, never a stop. It imports nothing of the repo at load time; overlaps_for
loads tools/agent/worktrees.py through orient.py to list the worktrees.
"""
from __future__ import annotations

import os
import subprocess
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

BASE = "origin/main"
GIT_TIMEOUT = 20
WORKERS = 8  # worktrees read side by side
SHORT_PATHS = 3  # paths named on the --short line, then "and N more"
# check-attr values that are git's own text merge, not a driver
NO_DRIVER = {"unspecified", "unset", "set"}


class OverlapError(Exception):
    """A git command failed, could not run or hung."""


class TreeLike(Protocol):
    """What overlap reads of a worktree: orient's Tree and tools/agent/worktrees.py's Worktree both fit."""
    path: str
    branch: str | None
    head: str


@dataclass(frozen=True)
class PullRequest:
    number: int
    branch: str
    files: tuple[str, ...]


@dataclass(frozen=True)
class Overlap:
    path: str
    places: tuple[str, ...]  # labels: a branch (with its PR), "detached <worktree path>", or "PR #n (branch)"
    auto_merge: bool


@dataclass
class OverlapReport:
    clashes: list[Overlap] = field(default_factory=list)
    auto: list[Overlap] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    lanes: dict[str, list[Overlap]] = field(default_factory=dict)  # lane prefix -> clashes only its branches share


# ---------------------------------------------------------------- git

def git(cwd: str | Path, *args: str, stdin: str | None = None) -> str:
    """git's raw output in cwd; OverlapError naming the command when it fails."""
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    try:
        done = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, input=stdin,
                              timeout=GIT_TIMEOUT, env=env)
    except subprocess.TimeoutExpired as err:
        raise OverlapError(f"git {args[0]} took over {GIT_TIMEOUT} s in {cwd}") from err
    except OSError as err:
        raise OverlapError(f"git {args[0]} could not run in {cwd}: {err}") from err
    if done.returncode != 0:
        raise OverlapError(f"git {args[0]} failed in {cwd}: {done.stderr.strip() or f'exit {done.returncode}'}")
    return done.stdout


def base_line(root: str | Path) -> set[str] | None:
    """origin/main's first-parent commits, or None when the repo has no origin/main."""
    try:
        git(root, "rev-parse", "--verify", "--quiet", f"{BASE}^{{commit}}")
    except OverlapError:
        return None
    return set(git(root, "rev-list", "--first-parent", BASE).split())


def status_paths(out: str) -> set[str]:
    """Paths of `git status --porcelain -z --no-renames` output: staged, unstaged and untracked, not ignored."""
    paths = set()
    for entry in out.split("\0"):
        if len(entry) > 3 and entry[:2] != "!!":
            paths.add(entry[3:])
    return paths


def tree_changes(tree: TreeLike, line: set[str] | None) -> set[str] | None:
    """The paths a worktree changes, or None when its branch is merged."""
    paths = set()
    head = tree.head if tree.head and tree.head.strip("0") else ""
    if head and line is not None:
        base = git(tree.path, "merge-base", BASE, head).strip()
        if base == head and head not in line:
            return None
        if base != head:
            paths |= set(git(tree.path, "diff", "--name-only", "--no-renames", f"{base}..{head}").split("\n"))
    paths |= status_paths(git(tree.path, "status", "--porcelain", "-z", "--untracked-files=all", "--no-renames",
                              "--ignore-submodules=dirty"))
    paths.discard("")
    return paths


def drivers(root: str | Path, paths: Iterable[str]) -> set[str]:
    """The paths that .gitattributes gives a merge driver of the repo's own (union, pipeline-map, ...)."""
    wanted = sorted(set(paths))
    if not wanted:
        return set()
    out = git(root, "check-attr", "-z", "--stdin", "merge", stdin="\0".join(wanted) + "\0").split("\0")
    return {out[i] for i in range(0, len(out) - 2, 3) if out[i + 2] not in NO_DRIVER}


# ---------------------------------------------------------------- places

def parse_prs(raw: object) -> list[PullRequest]:
    """PRs from gh's `--json number,headRefName,files` list; an entry of another shape is left out."""
    prs = []
    for p in raw if isinstance(raw, list) else []:
        if not isinstance(p, dict) or not isinstance(p.get("number"), int):
            continue
        files = tuple(f["path"] for f in p.get("files") or [] if isinstance(f, dict) and isinstance(f.get("path"), str))
        prs.append(PullRequest(p["number"], str(p.get("headRefName", "")), files))
    return prs


def tree_label(tree: TreeLike, root: str | Path, pr: int | None) -> str:
    if tree.branch:
        name = tree.branch
    else:
        try:
            name = "detached " + str(Path(tree.path).relative_to(root))
        except ValueError:
            name = f"detached {tree.path}"
    return name + (f" (PR #{pr})" if pr is not None else "")


def same_path(a: str | Path, b: str | Path) -> bool:
    return os.path.realpath(a) == os.path.realpath(b)


def collect(root: str | Path, trees: Sequence[TreeLike], prs: Sequence[PullRequest] = (),
            exclude: str | Path | None = None) -> tuple[dict[str, list[str]], list[str]]:
    """Every changed path with the labels of the places that change it, and the notes. trees[0] is the main
    checkout (git lists it first) and is skipped, as is the worktree at `exclude`."""
    notes = []
    line = None
    try:
        line = base_line(root)
    except OverlapError as err:
        notes.append(f"cannot read {BASE} ({err}); commits not compared")
    else:
        if line is None:
            notes.append(f"{BASE} not found; committed changes not compared, only uncommitted ones")
    pr_of = {p.branch: p.number for p in prs}
    work = [t for t in trees[1:] if os.path.isdir(t.path) and not (exclude and same_path(t.path, exclude))]

    def read(tree: TreeLike) -> set[str] | None | str:
        try:
            return tree_changes(tree, line)
        except OverlapError as err:
            return str(err)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(read, work))
    places: dict[str, list[str]] = {}
    local = {t.branch for t in trees if t.branch}
    for tree, got in zip(work, results):
        if isinstance(got, str):
            if os.path.isdir(tree.path):  # a folder the session-start sweep removed meanwhile is no note
                notes.append(f"worktree {tree.path} not read: {got}")
            continue
        label = tree_label(tree, root, pr_of.get(tree.branch or ""))
        for path in got or ():
            places.setdefault(path, []).append(label)
    for pr in prs:
        if pr.branch in local:
            continue
        for path in set(pr.files):
            places.setdefault(path, []).append(f"PR #{pr.number} ({pr.branch})")
    return places, notes


def classify(root: str | Path, places: dict[str, list[str]], notes: list[str]) -> OverlapReport:
    """Paths in two or more places, split into clashes and auto-merges."""
    shared = {p: tuple(sorted(labels)) for p, labels in places.items() if len(labels) > 1}
    rep = OverlapReport(notes=list(notes))
    try:
        auto = drivers(root, shared)
    except OverlapError as err:
        auto = set()
        rep.notes.append(f"merge drivers not read ({err}); every shared path is listed as a clash")
    for path in sorted(shared):
        item = Overlap(path, shared[path], path in auto)
        prefixes = {lane(label) for label in item.places}
        if item.auto_merge:
            rep.auto.append(item)
        elif len(prefixes) == 1 and None not in prefixes:
            rep.lanes.setdefault(str(next(iter(prefixes))), []).append(item)
        else:
            rep.clashes.append(item)
    return rep


def lane(label: str) -> str | None:
    """The lane prefix of a place's branch: the branch up to and with the first "-" of its last part, so
    agent/claude/ux-scorecard and agent/claude/ux-nav share agent/claude/ux-. None for a detached worktree or a
    branch whose last part has no "-". Branches of two sessions that chose the same word share a prefix too."""
    if label.startswith("detached "):
        return None
    branch = label.split(" (", 1)[1].rstrip(")") if label.startswith("PR #") else label.split(" (PR #", 1)[0]
    head, _, last = branch.rpartition("/")
    word, dash, _ = last.partition("-")
    return f"{head}/{word}-" if dash and head else (f"{word}-" if dash and word else None)


def overlap_report(root: str | Path, trees: Sequence[TreeLike], prs: Sequence[PullRequest] = ()) -> OverlapReport:
    return classify(root, *collect(root, trees, prs))


def overlaps_for(paths: Iterable[str], exclude_worktree: str | Path, *, root: str | Path | None = None,
                 prs: Sequence[PullRequest] = ()) -> list[Overlap]:
    """The given paths that another live worktree (or one of `prs`) also changes, each with the places that do; the
    worktree at exclude_worktree (the caller's own) is not counted. `root` is any checkout of the repo (default
    exclude_worktree). For a check before a push: no network unless the caller passes PRs."""
    import orient  # orient.py imports this module; loaded here, when its worktree reader is needed
    root = root or exclude_worktree
    trees = orient.load_worktrees_module().worktrees(root)
    places, _ = collect(trees[0].path, trees, prs, exclude=exclude_worktree)
    wanted = {p: tuple(sorted(places[p])) for p in set(paths) if p in places}
    try:
        auto = drivers(trees[0].path, wanted)
    except OverlapError:
        auto = set()  # the warning still names the path, as a clash
    return [Overlap(p, wanted[p], p in auto) for p in sorted(wanted)]


# ---------------------------------------------------------------- output

def full_lines(rep: OverlapReport, with_prs: str) -> list[str]:
    """The Overlap section of make orient; with_prs says where the PR data came from."""
    out = [f"Overlap (files changed in two or more places; local worktrees, {with_prs})"
           + (":" if rep.clashes else ": none")]
    out += [f"  {o.path}: {', '.join(o.places)}" for o in rep.clashes]
    if rep.lanes:
        out.append(f"Lane overlaps ({sum(map(len, rep.lanes.values()))}; only branches of one lane prefix share them):")
        out += [f"  {lane_text(prefix, items)}" for prefix, items in sorted(rep.lanes.items())]
    if rep.auto:
        out.append(f"Auto-merges ({len(rep.auto)}; a merge driver in .gitattributes joins both sides):")
        out += [f"  {o.path}: {', '.join(o.places)}" for o in rep.auto]
    out += [f"  NOTE: {n}" for n in rep.notes]
    return out


def lane_text(prefix: str, items: list[Overlap]) -> str:
    """One prefix's lane overlaps: "<prefix>*: N file(s) (a, b, c and N more) in <branches>"."""
    names = ", ".join(o.path for o in items[:SHORT_PATHS]) + (f" and {len(items) - SHORT_PATHS} more"
                                                              if len(items) > SHORT_PATHS else "")
    places = sorted({p for o in items for p in o.places})
    return f"{prefix}*: {len(items)} file(s) ({names}) in {', '.join(places)}"


def short_line(rep: OverlapReport) -> list[str]:
    """One line for the session-start hook, or none when no file is changed in two places. Lane overlaps (one lane
    prefix's branches only) follow the clashes on the same line, one part per prefix."""
    lanes = "; ".join(lane_text(p, items) for p, items in sorted(rep.lanes.items()))
    if not rep.clashes:
        if lanes:
            return [f"Overlap: none between lane prefixes; within one: {lanes}; make orient"]
        return [f"Overlap: not checked in part ({len(rep.notes)} note(s)); make orient"] if rep.notes else []
    named = "; ".join(f"{o.path}: {', '.join(o.places)}" for o in rep.clashes[:SHORT_PATHS])
    more = f"; and {len(rep.clashes) - SHORT_PATHS} more" if len(rep.clashes) > SHORT_PATHS else ""
    count = len(rep.clashes)
    within = f"; within one lane prefix: {lanes}" if lanes else ""
    return [f"Overlap: {count} file{'s' if count > 1 else ''} changed in two or more places ({named}{more}){within}; "
            f"make orient"]
