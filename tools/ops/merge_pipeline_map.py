#!/usr/bin/env python3
"""merge_pipeline_map.py

Git merge drivers for the pipeline map: a three-way merge of docs/pipeline-map/pipeline_map.json by key, and one
for the two pages built from it.

    merge_pipeline_map.py BASE OURS THEIRS [PATH]          merge the graph into OURS (git passes %O %A %B %P)
    merge_pipeline_map.py --page BASE OURS THEIRS [PATH]   a generated page: keep OURS and say how to rebuild it
    merge_pipeline_map.py --install                        set both drivers in this repo's git config

The graph merges entry by entry: domains by id, presets by label, nodes by id, edges by their two ends (the keys
tools/ops/build_pipeline_map.py checks), and "updated" takes the later date. For each key: what one side left alone
takes the other side's version, the same change on both sides is taken once, an add on one side is added, a delete
on one side of an entry the other left alone is deleted. Two different changes to one key are a conflict: the file
gets git-style markers around both versions of that entry and the driver exits 1, so git stops the merge there.
Lists keep the order of this branch, with the other branch's new entries after the entry they follow there (the
page's layout depends on node order). A clean merge is checked with build_pipeline_map.validate, all but the check
that each path is tracked (git has not written the merged tree yet; tools/check.sh runs that check after the
merge); a result that fails, such as an edge to a node the other side deleted, is left in place and exits 1.

The pages (docs/pipeline-map/index.html, www/library/pipeline-map.html) hold the graph on one line, so any two
changes conflict; the page driver keeps this branch's copy and prints the rebuild commands, and the page checks
in tools/check.sh fail until they are run.

Exit codes: 0 merged, 1 conflict left in OURS, 2 the inputs cannot be merged by key: OURS then holds git's own
line merge (git merge-file), so the clash still shows as conflict markers.
--install changes the shared git config of this clone and all its worktrees, and prints only what it changed.
In a checkout without this script (a branch from before it) the configured drivers run git's own line merge.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("build_pipeline_map", Path(__file__).resolve().with_name("build_pipeline_map.py"))
MAP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(MAP)

SCRIPT = "tools/ops/merge_pipeline_map.py"


def driver_command(flag: str) -> str:
    """The driver line for git config. git runs it through the shell from the top of the worktree being merged, so
    each worktree runs its own copy. git config is shared by every worktree, and a branch from before this script
    has no copy: there it runs git's own line merge (git merge-file, conflict markers as without a driver)."""
    return (f"if [ -f {SCRIPT} ]; then exec python3 {SCRIPT}{flag} %O %A %B %P; "
            f"else exec git merge-file -L ours -L base -L theirs %A %O %B; fi")


DRIVERS = {
    "pipeline-map": ("pipeline_map.json, merged by node id and edge ends", driver_command("")),
    "pipeline-map-page": ("pipeline map page: keep ours, rebuild after the merge", driver_command(" --page")),
}
REBUILD = f"python3 tools/ops/build_pipeline_map.py && {MAP.SITE_BUILD}"

# the lists merged entry by entry, and the fields that name an entry
KEY_FIELDS = {"domains": ("id",), "presets": ("label",), "nodes": ("id",), "edges": ("from", "to")}
OPTIONAL = {"presets"}  # build_pipeline_map reads a missing presets list as none
SENTINEL_STEM = "@@pipeline-map-conflict-"
SENTINEL = SENTINEL_STEM + "{}@@"
SENTINEL_LINE = re.compile(r'^( *)((?:"[^"\n]*": )?)"@@pipeline-map-conflict-(\d+)@@"(,?)$', re.M)


class MergeError(Exception):
    """The inputs cannot be merged at all (exit 2)."""


class _Absent:
    """An entry or key missing on one side (a JSON null is a value, so None cannot stand for this)."""
    def __repr__(self) -> str:
        return "ABSENT"


ABSENT = _Absent()


class Conflict:
    """Two different changes to one key. where names it ("node 'x'"); ours or theirs is ABSENT when that side
    deleted it; inline is False for a whole-list order clash, which the message names but no markers show."""

    def __init__(self, where: str, ours: object, theirs: object, inline: bool = True) -> None:
        self.where, self.ours, self.theirs, self.inline = where, ours, theirs, inline


def key_of(name: str, entry: dict) -> str | tuple[str, str]:
    if name == "nodes":
        return MAP.node_key(entry)
    if name == "edges":
        return MAP.edge_key(entry)
    return entry[KEY_FIELDS[name][0]]


def show(name: str, key) -> str:
    kind = {"domains": "domain", "presets": "preset", "nodes": "node", "edges": "edge"}[name]
    return f"{kind} {key[0]} -> {key[1]}" if name == "edges" else f"{kind} {key!r}"


def load_side(path: Path, side: str) -> dict:
    """One side of the merge as data, every list entry checked to have its key and no key twice."""
    try:
        data = MAP.read(path)
    except MAP.GraphError as err:
        raise MergeError(f"{side} ({path}): {err}") from None
    if SENTINEL_STEM in path.read_text(encoding="utf-8"):
        raise MergeError(f"{side} ({path}) already holds a conflict entry from this driver; resolve it first")
    for name, fields in KEY_FIELDS.items():
        if name in OPTIONAL and name not in data:
            continue
        entries = data[name]
        if not isinstance(entries, list) or any(not isinstance(e, dict) for e in entries):
            raise MergeError(f"{side} ({path}): {name!r} must be a list of objects")
        seen = set()
        for e in entries:
            missing = [f for f in fields if not isinstance(e.get(f), str) or not e[f]]
            if missing:
                raise MergeError(f"{side} ({path}): an entry of {name!r} has no {' or '.join(missing)} to merge it "
                                 f"by: {json.dumps(e, ensure_ascii=False)}")
            k = key_of(name, e)
            if k in seen:
                raise MergeError(f"{side} ({path}): {show(name, k)} is listed twice")
            seen.add(k)
    return data


def three_way(base, ours, theirs):
    """The merged value, or a Conflict with both sides' values. ABSENT stands for a missing entry."""
    if ours == theirs:
        return ours
    if ours == base:
        return theirs
    if theirs == base:
        return ours
    return Conflict("", ours, theirs)


def merge_order(base: list, ours: list, theirs: list, keep: set) -> tuple[list, bool]:
    """The merged order of the kept keys: the order of the side that changed the shared keys' order (ours when
    neither or both did; the bool says both did, differently), then each side's new keys after the key they follow
    on that side, ours before theirs."""
    common = set(base) & set(ours) & set(theirs)
    b, o, t = ([k for k in seq if k in common] for seq in (base, ours, theirs))
    both_reordered = o != b and t != b and o != t
    order = [k for k in (t if o == b else o) if k in keep]
    placed = set(order)
    ours_new = set(ours) - set(base) - set(theirs)
    for seq in (ours, theirs):
        for i, k in enumerate(seq):
            if k not in keep or k in placed:
                continue
            prev = next((seq[j] for j in range(i - 1, -1, -1) if seq[j] in placed), None)
            pos = order.index(prev) + 1 if prev is not None else 0
            while seq is theirs and pos < len(order) and order[pos] in ours_new:
                pos += 1
            order.insert(pos, k)
            placed.add(k)
    if placed != keep or len(order) != len(keep):
        raise MergeError(f"internal: the merged order lost or repeated keys ({sorted(map(str, keep ^ placed))})")
    return order, both_reordered


def merge_list(name: str, base: dict, ours: dict, theirs: dict, conflicts: list[Conflict]) -> list:
    seqs = [[key_of(name, e) for e in side.get(name, [])] for side in (base, ours, theirs)]
    maps = [dict(zip(seq, side.get(name, []))) for seq, side in zip(seqs, (base, ours, theirs))]
    merged: dict = {}
    for k in dict.fromkeys(seqs[0] + seqs[1] + seqs[2]):
        value = three_way(*(m.get(k, ABSENT) for m in maps))
        if isinstance(value, Conflict):
            value.where = show(name, k)
            conflicts.append(value)
        if value is not ABSENT:
            merged[k] = value
    order, both_reordered = merge_order(*seqs, set(merged))
    if both_reordered:
        conflicts.append(Conflict(f"the order of {name!r} (both sides reordered it; this file keeps ours)",
                                  ABSENT, ABSENT, inline=False))
    out = [merged[k] for k in order]
    # invariant: every entry is one side's version of its key, each key once
    for k, v in zip(order, out):
        if not isinstance(v, Conflict) and v not in (maps[1].get(k), maps[2].get(k)):
            raise MergeError(f"internal: merged {show(name, k)} matches neither side")
    return out


def later_date(ours, theirs):
    """The later of two YYYY-MM-DD dates, or None when either is not one."""
    try:
        return max(dt.date.fromisoformat(ours), dt.date.fromisoformat(theirs)).isoformat()
    except (TypeError, ValueError):
        return None


def merge_graphs(base: dict, ours: dict, theirs: dict) -> tuple[dict, list[Conflict]]:
    conflicts: list[Conflict] = []
    out: dict = {}
    for key in dict.fromkeys([*ours, *theirs, *base]):
        if key in KEY_FIELDS:
            present = three_way(key in base, key in ours, key in theirs)  # True/False never conflict
            kept = [side for side in (ours, theirs) if key in side]
            if key in base and len(kept) == 1 and kept[0][key] != base[key]:
                # one side dropped the whole list, the other changed it: delete against edit
                conflicts.append(Conflict(f"the {key!r} list (one side removed it, the other changed it; this file "
                                          f"keeps the changed list)", ABSENT, ABSENT, inline=False))
                out[key] = kept[0][key]
                continue
            if present:
                out[key] = merge_list(key, base, ours, theirs, conflicts)
            continue
        b, o, t = (side.get(key, ABSENT) for side in (base, ours, theirs))
        value = three_way(b, o, t)
        if isinstance(value, Conflict) and key == "updated":
            value = later_date(o, t) or value
        if isinstance(value, Conflict):
            value.where = f"top-level key {key!r}"
            conflicts.append(value)
        if value is not ABSENT:
            out[key] = value
    return out, conflicts


def entry_text(value, indent: str, prefix: str, comma: str) -> str:
    lines = json.dumps(value, indent=1, ensure_ascii=False).split("\n")
    return "\n".join([indent + prefix + lines[0], *(indent + line for line in lines[1:])]) + comma


def render(data: dict, conflicts: list[Conflict]) -> str:
    """The merged file in the graph's own format; each conflicting entry between git conflict markers."""
    inline = [c for c in conflicts if c.inline]
    numbered = {id(c): i for i, c in enumerate(inline)}

    def swap(value):
        if isinstance(value, list):
            return [swap(v) for v in value]
        if isinstance(value, Conflict):
            return SENTINEL.format(numbered[id(value)])
        return value

    text = MAP.graph_text({k: swap(v) for k, v in data.items()})
    done: set[int] = set()

    def block(m: re.Match) -> str:
        indent, prefix, i, comma = m.group(1), m.group(2), int(m.group(3)), m.group(4)
        c = inline[i]
        done.add(i)
        sides = []
        for label, value in (("ours", c.ours), ("theirs", c.theirs)):
            gone = " (deleted; if you keep this side, drop the comma the entry before it ends with)" if not comma \
                else " (deleted)"
            sides.append(f"{label}: {c.where}" + (gone if value is ABSENT else ""))
            sides.append("" if value is ABSENT else entry_text(value, indent, prefix, comma) + "\n")
        return (f"<<<<<<< {sides[0]}\n{sides[1]}=======\n{sides[3]}>>>>>>> {sides[2]}")

    text = SENTINEL_LINE.sub(block, text)
    if done != set(range(len(inline))):
        raise MergeError("internal: a conflict entry was not written out")
    return text


def merge(base_path: Path, ours_path: Path, theirs_path: Path, name: str) -> int:
    base, ours, theirs = (load_side(p, side) for p, side in
                          ((base_path, "base"), (ours_path, "ours"), (theirs_path, "theirs")))
    data, conflicts = merge_graphs(base, ours, theirs)
    text = render(data, conflicts)
    if conflicts:
        ours_path.write_text(text, encoding="utf-8")
        print(f"{name}: {len(conflicts)} conflict(s) the driver will not pick for you:", file=sys.stderr)
        for c in conflicts:
            print(f"  {c.where}", file=sys.stderr)
        print(f"Edit the <<<<<<< blocks in {name}, then run {REBUILD}, and git add the three files.", file=sys.stderr)
        return 1
    if json.loads(text) != data:
        raise MergeError("internal: the written file does not read back as the merged graph")
    ours_path.write_text(text, encoding="utf-8")
    try:
        MAP.validate(json.loads(text), tracked=False)
    except MAP.GraphError as err:
        print(f"{name}: merged by key, but the result fails the graph checks:\n{err}\n"
              f"The merged file is in place: fix it, run {REBUILD}, and git add the three files.", file=sys.stderr)
        return 1
    print(f"{name}: merged by key ({len(data['nodes'])} nodes, {len(data['edges'])} edges); "
          f"now rebuild the pages: {REBUILD}", file=sys.stderr)
    return 0


def keep_page(ours_path: Path, name: str) -> int:
    """Keep ours and exit 0, so a clean graph merge commits on its own: the merge commit carries stale pages, and
    the rebuild is a commit after it (tools/check.sh and CI fail until it is made)."""
    print(f"{name}: built from docs/pipeline-map/pipeline_map.json, so this branch's copy is kept; after the merge "
          f"run {REBUILD} and commit the pages (tools/check.sh fails until then)", file=sys.stderr)
    return 0


def line_merge(base: Path, ours: Path, theirs: Path, name: str, why: str) -> int:
    """The driver could not merge by key: leave git's own line merge in OURS, so the clash shows as conflict
    markers instead of a clean-looking copy of ours that a git add would commit. Always exits 2."""
    print(f"merge_pipeline_map: {name}: {why}\nFalling back to git's line merge (conflict markers in the file).",
          file=sys.stderr)
    try:
        done = subprocess.run(["git", "merge-file", "-L", "ours", "-L", "base", "-L", "theirs", str(ours), str(base),
                               str(theirs)], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as err:
        print(f"merge_pipeline_map: git merge-file could not run either ({err}); {name} still holds ours only: "
              f"merge it by hand", file=sys.stderr)
        return 2
    if done.returncode < 0 or done.returncode > 127:
        print(f"merge_pipeline_map: git merge-file failed ({done.stderr.strip()}); {name} still holds ours only: "
              f"merge it by hand", file=sys.stderr)
    return 2


def git_config(repo: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-C", str(repo), "config", *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as err:
        raise MergeError(f"cannot run git config in {repo}: {err}") from None


def install(repo: Path) -> list[str]:
    """Set both drivers in the repo's git config (shared by all its worktrees); return the keys it changed."""
    try:
        top = subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-dir"], capture_output=True, text=True,
                             timeout=30)
    except (OSError, subprocess.SubprocessError) as err:
        raise MergeError(f"cannot run git in {repo}: {err}") from None
    if top.returncode != 0:
        raise MergeError(f"{repo} is not a git checkout: {top.stderr.strip()}")
    changed = []
    for driver, (label, command) in DRIVERS.items():
        for field, value in (("name", label), ("driver", command)):
            key = f"merge.{driver}.{field}"
            got = git_config(repo, "--local", "--get", key)
            if got.returncode not in (0, 1):  # 1: not set
                raise MergeError(f"git config --get {key} failed in {repo}: {got.stderr.strip()}")
            if got.returncode == 0 and got.stdout.rstrip("\n") == value:
                continue
            put = git_config(repo, "--local", key, value)
            if put.returncode != 0:
                raise MergeError(f"git config {key} failed in {repo}: {put.stderr.strip()}")
            changed.append(key)
    return changed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[2])
    ap.add_argument("--install", action="store_true", help="set the merge drivers in this repo's git config")
    ap.add_argument("--repo", type=Path, default=ROOT, help="the repo for --install (default: this checkout)")
    ap.add_argument("--page", action="store_true", help="merge a generated page: keep ours, say how to rebuild")
    ap.add_argument("files", nargs="*", metavar="BASE OURS THEIRS [PATH]")
    args = ap.parse_args(argv)
    try:
        if args.install:
            if args.files or args.page:
                ap.error("--install takes no files")
            for key in install(args.repo):
                print(f"set git config {key}")
            return 0
        if len(args.files) not in (3, 4):
            ap.error("give BASE OURS THEIRS and optionally PATH (git: %O %A %B %P)")
        base, ours, theirs = (Path(f) for f in args.files[:3])
        name = args.files[3] if len(args.files) == 4 else str(ours)
        missing = [str(p) for p in (base, ours, theirs) if not p.is_file()]
        if missing:
            raise MergeError(f"no such file: {', '.join(missing)}")
        if args.page:
            return keep_page(ours, name)
        try:
            return merge(base, ours, theirs, name)
        except MergeError as err:
            return line_merge(base, ours, theirs, name, str(err))
        except Exception as err:  # a bug here must still leave a visible conflict, not ours alone
            return line_merge(base, ours, theirs, name, f"internal error: {type(err).__name__}: {err}")
    except MergeError as err:
        print(f"merge_pipeline_map: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
