#!/usr/bin/env python3
"""merge_pipeline_map.py

The git merge driver for the pipeline map: a three-way merge of docs/pipeline-map/pipeline_map.json by key.

    merge_pipeline_map.py BASE OURS THEIRS [PATH]          merge the graph into OURS (git passes %O %A %B %P)
    merge_pipeline_map.py --install                        set the driver in this repo's git config

The graph merges entry by entry: domains by id, presets by label, nodes by id, edges by their two ends (the keys
tools/ops/build_pipeline_map.py checks), and "updated" takes the later date. For each key: what one side left alone
takes the other side's version, the same change on both sides is taken once, an add on one side is added, a delete
on one side of an entry the other left alone is deleted. Two different changes to one key are a conflict: the file
gets git-style markers around both versions of that entry and the driver exits 1, so git stops the merge there.
Lists keep the order of this branch, with the other branch's new entries after the entry they follow there (the
page's layout depends on node order). A clean merge is checked with build_pipeline_map.validate, all but the check
that each path is tracked (git has not written the merged tree yet; tools/check.sh runs that check after the
merge); a result that fails, such as an edge to a node the other side deleted, is left in place and exits 1.

Generated entries (marked "gen": the agent-doc and manifest lanes, build_pipeline_map.GENERATED) merge like the
others, since each side's were current for that side's sources; the merge cannot rebuild them, because git has not
merged those sources yet. So a conflict on a generated entry names its lane and says to keep either side and rebuild
the lane, and a clean merge that takes a generated entry changed on the other branch names it, for --check to
confirm against the merged sources. A hand edit to a generated entry (one a branch from before the lane existed
made, say) is then a conflict or a --check failure naming it, never kept quietly.

The pages built from the graph are not committed (ADR-036), so they never conflict; the driver for them that kept
this branch's copy is retired, and --install removes its git config section (RETIRED) where it is still set.

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
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _load_map() -> ModuleType:
    """build_pipeline_map.py, loaded by path."""
    path = Path(__file__).resolve().with_name("build_pipeline_map.py")
    spec = importlib.util.spec_from_file_location("build_pipeline_map", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MAP = _load_map()
# The driver merges every top-level key and list by its name, so it holds a side as plain JSON data; the graph's
# own record types (build_pipeline_map.Graph, from map_lane.py) name the keys the build reads.
Graph = dict[str, Any]
SCRIPT = "tools/ops/merge_pipeline_map.py"


def driver_command(flag: str) -> str:
    """The driver line for git config. git runs it through the shell from the top of the worktree being merged, so
    each worktree runs its own copy. git config is shared by every worktree, and a branch from before this script
    has no copy: there it runs git's own line merge (git merge-file, conflict markers as without a driver)."""
    return (f"if [ -f {SCRIPT} ]; then exec python3 {SCRIPT}{flag} %O %A %B %P; "
            f"else exec git merge-file -L ours -L base -L theirs %A %O %B; fi")


DRIVERS = {
    "pipeline-map": ("pipeline_map.json, merged by node id and edge ends", driver_command("")),
}
# drivers this script no longer provides: --install removes their config section (the map pages' "keep ours"
# driver, retired when the pages stopped being committed, ADR-036)
RETIRED = ("pipeline-map-page",)
BUILD = "python3 tools/ops/build_pipeline_map.py"
CHECK = f"{BUILD} --check"

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


def key_of(name: str, entry: Mapping[str, Any]) -> str | tuple[str, str]:
    key: str | tuple[str, str]
    if name == "nodes":
        key = MAP.node_key(entry)
    elif name == "edges":
        key = MAP.edge_key(entry)
    else:
        key = entry[KEY_FIELDS[name][0]]
    return key


def show(name: str, key: str | tuple[str, str]) -> str:
    kind = {"domains": "domain", "presets": "preset", "nodes": "node", "edges": "edge"}[name]
    return f"{kind} {key[0]} -> {key[1]}" if name == "edges" else f"{kind} {key!r}"


def load_side(path: Path, side: str) -> Graph:
    """One side of the merge as data, every list entry checked to have its key and no key twice."""
    try:
        data: Graph = MAP.read(path)
    except MAP.GraphError as err:
        raise MergeError(f"{side} ({path}): {err}") from err
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


def three_way(base: object, ours: object, theirs: object) -> object:
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


def merge_list(name: str, base: Graph, ours: Graph, theirs: Graph, conflicts: list[Conflict]) -> list:
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
    order, both_reordered = merge_order(seqs[0], seqs[1], seqs[2], set(merged))
    if both_reordered:
        conflicts.append(Conflict(f"the order of {name!r} (both sides reordered it; this file keeps ours)",
                                  ABSENT, ABSENT, inline=False))
    out = [merged[k] for k in order]
    # invariant: every entry is one side's version of its key, each key once
    for k, v in zip(order, out):
        if not isinstance(v, Conflict) and v not in (maps[1].get(k), maps[2].get(k)):
            raise MergeError(f"internal: merged {show(name, k)} matches neither side")
    return out


def later_date(ours: object, theirs: object) -> str | None:
    """The later of two YYYY-MM-DD dates, or None when either is not one."""
    if not isinstance(ours, str) or not isinstance(theirs, str):
        return None
    try:
        return max(dt.date.fromisoformat(ours), dt.date.fromisoformat(theirs)).isoformat()
    except ValueError:
        return None


def merge_graphs(base: Graph, ours: Graph, theirs: Graph) -> tuple[Graph, list[Conflict]]:
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


def entry_text(value: object, indent: str, prefix: str, comma: str) -> str:
    lines = json.dumps(value, indent=1, ensure_ascii=False).split("\n")
    return "\n".join([indent + prefix + lines[0], *(indent + line for line in lines[1:])]) + comma


def render(data: Graph, conflicts: list[Conflict]) -> str:
    """The merged file in the graph's own format; each conflicting entry between git conflict markers."""
    inline = [c for c in conflicts if c.inline]
    numbered = {id(c): i for i, c in enumerate(inline)}

    def swap(value: object) -> object:
        if isinstance(value, list):
            return [swap(v) for v in value]
        if isinstance(value, Conflict):
            return SENTINEL.format(numbered[id(value)])
        return value

    text = MAP.graph_text({k: swap(v) for k, v in data.items()})
    done: set[int] = set()

    def block(m: re.Match[str]) -> str:
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


def _lanes(*values: object) -> list[str]:
    """The generated lanes (their "gen" marks) of the entries among `values`."""
    return sorted({v["gen"] for v in values if isinstance(v, dict) and isinstance(v.get("gen"), str)})


def from_theirs(data: Graph, ours: Graph) -> list[str]:
    """The generated nodes and edges of the merged graph that differ from ours: taken from the other branch."""
    out = []
    for name in ("nodes", "edges"):
        mine = {key_of(name, e): e for e in ours.get(name, [])}
        out += [f"{show(name, key_of(name, e))} ({', '.join(_lanes(e))} lane)" for e in data.get(name, [])
                if _lanes(e) and mine.get(key_of(name, e)) != e]
    return out


def merge(base_path: Path, ours_path: Path, theirs_path: Path, name: str) -> int:
    base, ours, theirs = (load_side(p, side) for p, side in
                          ((base_path, "base"), (ours_path, "ours"), (theirs_path, "theirs")))
    data, conflicts = merge_graphs(base, ours, theirs)
    text = render(data, conflicts)
    if conflicts:
        ours_path.write_text(text, encoding="utf-8")
        print(f"{name}: {len(conflicts)} conflict(s) the driver will not pick for you:", file=sys.stderr)
        generated = False
        for c in conflicts:
            lanes = _lanes(c.ours, c.theirs)
            generated = generated or bool(lanes)
            print(f"  {c.where}" + (f" (generated: the {', '.join(lanes)} lane)" if lanes else ""), file=sys.stderr)
        if generated:
            print(f"A generated entry is rebuilt from its sources: keep either side of its block, then run {BUILD} "
                  f"(make map) once the merge has its sources, so the lane is drawn from them.", file=sys.stderr)
        print(f"Edit the <<<<<<< blocks in {name}, check it with {CHECK}, and git add it.", file=sys.stderr)
        return 1
    if json.loads(text) != data:
        raise MergeError("internal: the written file does not read back as the merged graph")
    ours_path.write_text(text, encoding="utf-8")
    try:
        MAP.validate(json.loads(text), tracked=False)
    except MAP.GraphError as err:
        print(f"{name}: merged by key, but the result fails the graph checks:\n{err}\n"
              f"The merged file is in place: fix it, check it with {CHECK}, and git add it.", file=sys.stderr)
        return 1
    print(f"{name}: merged by key ({len(data['nodes'])} nodes, {len(data['edges'])} edges); {CHECK} checks it "
          f"with every path tracked (make map rebuilds the local pages)", file=sys.stderr)
    theirs_gen = from_theirs(data, ours)
    if theirs_gen:
        print(f"{name}: {len(theirs_gen)} generated entr{'y' if len(theirs_gen) == 1 else 'ies'} taken from the other "
              f"branch, which {CHECK} checks against the merged sources (make map rebuilds them): "
              f"{'; '.join(theirs_gen[:5])}{' ...' if len(theirs_gen) > 5 else ''}", file=sys.stderr)
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
        raise MergeError(f"cannot run git config in {repo}: {err}") from err


def install(repo: Path) -> list[str]:
    """Set the drivers in the repo's git config (shared by all its worktrees) and remove the RETIRED ones' sections;
    return what it changed, as the lines to print."""
    try:
        top = subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-dir"], capture_output=True, text=True,
                             timeout=30)
    except (OSError, subprocess.SubprocessError) as err:
        raise MergeError(f"cannot run git in {repo}: {err}") from err
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
            changed.append(f"set git config {key}")
    for driver in RETIRED:
        section = f"merge.{driver}"
        got = git_config(repo, "--local", "--get-regexp", rf"^{re.escape(section)}\.")
        if got.returncode == 1:  # nothing set
            continue
        if got.returncode != 0:
            raise MergeError(f"git config --get-regexp {section} failed in {repo}: {got.stderr.strip()}")
        gone = git_config(repo, "--local", "--remove-section", section)
        if gone.returncode != 0:
            raise MergeError(f"git config --remove-section {section} failed in {repo}: {gone.stderr.strip()}")
        left = git_config(repo, "--local", "--get-regexp", rf"^{re.escape(section)}\.")
        if left.returncode != 1:
            raise MergeError(f"git config still holds {section} in {repo} after removing it: {left.stdout.strip()}")
        changed.append(f"removed git config {section} (a retired driver)")
    return changed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[2])
    ap.add_argument("--install", action="store_true", help="set the merge drivers in this repo's git config")
    ap.add_argument("--repo", type=Path, default=ROOT, help="the repo for --install (default: this checkout)")
    ap.add_argument("files", nargs="*", metavar="BASE OURS THEIRS [PATH]")
    args = ap.parse_args(argv)
    try:
        if args.install:
            if args.files:
                ap.error("--install takes no files")
            for line in install(args.repo):
                print(line)
            return 0
        if len(args.files) not in (3, 4):
            ap.error("give BASE OURS THEIRS and optionally PATH (git: %O %A %B %P)")
        base, ours, theirs = (Path(f) for f in args.files[:3])
        name = args.files[3] if len(args.files) == 4 else str(ours)
        missing = [str(p) for p in (base, ours, theirs) if not p.is_file()]
        if missing:
            raise MergeError(f"no such file: {', '.join(missing)}")
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
