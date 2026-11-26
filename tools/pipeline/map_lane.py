#!/usr/bin/env python3
"""map_lane.py

The manifest lane of the pipeline map (ADR-037 stages 3 and 5): a box for each script check.sh or make panels runs and
its links, read from the step manifests, tools/pipeline/checks.toml and tools/pipeline/panels.toml, so the map cannot
drift from what they run.
tools/ops/build_pipeline_map.py calls regenerate() after the agent-doc lane and writes the result into
docs/pipeline-map/pipeline_map.json; its --check fails when the committed graph differs.

    python3 tools/pipeline/map_lane.py     print the boxes and links it would generate

Each box and link is marked "gen": "manifest" in the graph. For each step (but those in HAND_KEPT_STEPS):
- a "generator" box for its script: id and path the script, label, domain and desc from the step;
- input -> script for each input, with its label and side;
- script -> output for each output, with its label;
- script -> tools/check.sh, side "check", label "check <step name>": check.sh runs it as that job.

For panels.toml, one box per box name (a step's box, or its script's), with the text of the box's first step, its
path the script, and "runner": true on the box of tools/schematic/build_panels.sh (checks.toml's panels step), which
runs them all:
- input -> box and box -> output as above; an output glob goes to each box it matches that the step names no other
  way, or with none, to the box of the folder it is in. Steps of one box list a link once, or with one label and side;
- tools/schematic/build_panels.sh -> box, label "step <name>", for each step (mode "step");
- box -> tools/schematic/build_panels.sh, side "check", label "guard <name>" (the guards of one box in one label), for
  each guard: it checks the files it reads and stops the run.

An input or output names a box by its path, so it must be one: a hand-kept box, an agent doc's, or another step's
script. A link another lane already draws (the agent-doc lane links each doc check_agent_docs.py reads to it) is left
to that lane, but only when its label and side are the same; otherwise it is an error. A hand-kept box or link with
the key of a generated one is an error: the generated one replaces it, so drop the hand one.

The graph's node order is the layout's tie-break, so the lane keeps each generated box and link where the file has it.
A new box goes after the box of the step before it in the manifest, and a new link after the last link of its script
box; with none, after the last hand-kept or manifest entry (another lane may move its own entries on the next run). Links between scripts and code (imports, calls), from hosts or external boxes,
and from tools/check.sh into a script stay hand-kept.
"""

import importlib.util
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Literal, NamedTuple, Required, TypedDict, TypeVar, get_args

ROOT = Path(__file__).resolve().parents[2]
if "pipeline_manifest" not in sys.modules:      # once per process: check_stamps.py and the tests load it by this name
    _spec = importlib.util.spec_from_file_location("pipeline_manifest", ROOT / "tools/pipeline/manifest.py")
    sys.modules["pipeline_manifest"] = importlib.util.module_from_spec(_spec)    # its dataclasses look it up there
    _spec.loader.exec_module(sys.modules["pipeline_manifest"])
MANIFEST = sys.modules["pipeline_manifest"]

# The graph's record types (docs/pipeline-map/pipeline_map.json): build_pipeline_map.py and merge_pipeline_map.py
# use them too, and validate() checks a kind, status or side against these fixed sets.
NodeKind = Literal["structured", "unstructured", "generator", "output", "external", "host", "human"]
Status = Literal["live", "parked", "retired"]
Side = Literal["check", "pointer", "pull", "mirror", "capture", "history"]   # why a link carries no content
NODE_KINDS: tuple[str, ...] = get_args(NodeKind)
STATUSES: tuple[str, ...] = get_args(Status)
SIDES: tuple[str, ...] = get_args(Side)


class Node(TypedDict, total=False):
    """One box. "gen" names the lane that generated it; "local" marks a box the public copy leaves out; "runner"
    marks the box that runs the others (make panels)."""
    id: Required[str]
    label: Required[str]
    kind: Required[NodeKind]
    status: Status
    domain: str
    desc: str
    path: str
    gen: str
    local: bool
    runner: bool


# One link, keyed by its two ends. "from" is a Python keyword, so the class syntax cannot name it.
Edge = TypedDict("Edge", {"from": Required[str], "to": Required[str], "label": str, "side": Side, "gen": str},
                 total=False)


class Graph(TypedDict, total=False):
    updated: str
    domains: list[dict[str, str]]
    presets: list[dict[str, object]]   # a preset's fields belong to the viewer; the build reads only "label"
    nodes: Required[list[Node]]
    edges: Required[list[Edge]]


EdgeKey = tuple[str, str]

GEN = "manifest"
RUNNER = "tools/check.sh"           # the box every step links to: check.sh runs each step as a job
# steps of checks.toml whose box and links stay hand-kept, with the reason (none since stage 5 drew make panels)
HAND_KEPT_STEPS: dict[str, str] = {}


class MapLaneError(Exception):
    """The manifest lane cannot be drawn into this graph; the message says what to change."""


class Lane(NamedTuple):
    """What lane() or panels_lane() generates: the boxes, the links, each box's id in manifest order, and each link's
    own box (the step that lists it)."""
    nodes: list[Node]
    edges: list[Edge]
    order: list[str]
    owner: dict[EdgeKey, str]


def _key(e: Edge) -> EdgeKey:
    return (e["from"], e["to"])


def _edge(a: str, b: str, label: str, side: str) -> Edge:
    e: Edge = {"from": a, "to": b}
    if label:
        e["label"] = label
    if side:
        e["side"] = side
    e["gen"] = GEN
    return e


def lane(steps: Sequence["MANIFEST.Step"], path_ids: dict[str, str], runner_id: str) -> Lane:
    """The generated boxes, links, each box's id in manifest order, and each link's own script (the step that lists
    it: a link between two steps' scripts belongs to the one whose input or output it is). path_ids maps each box path
    of the graph (without a trailing /) to its id, the lane's own boxes included."""
    nodes: list[Node] = []
    edges: list[Edge] = []
    order: list[str] = []
    problems: list[str] = []
    owner: dict[EdgeKey, str] = {}
    seen: dict[str, str] = {}
    for step in steps:
        if step.name in HAND_KEPT_STEPS:
            continue
        if step.script in seen:
            problems.append(f"steps {seen[step.script]!r} and {step.name!r} both run {step.script}; the map draws "
                            f"one box per script")
            continue
        seen[step.script] = step.name
        nodes.append({"id": step.script, "label": step.label, "kind": "generator", "status": "live",
                      "domain": step.domain, "desc": step.desc, "path": step.script, "gen": GEN})
        order.append(step.script)
        for kind, items in (("input", step.inputs), ("output", step.outputs)):
            for item in items:
                other = path_ids.get(item.path)
                if other is None:
                    problems.append(f"step {step.name!r}: {kind} {item.path} is no box of the map; add a hand-kept box "
                                    f"with that path, or drop the {kind}")
                elif other == step.script:
                    problems.append(f"step {step.name!r}: {kind} {item.path} is the step's own script")
                elif kind == "input":
                    edges.append(_edge(other, step.script, item.label, item.side))
                else:
                    edges.append(_edge(step.script, other, item.label, ""))
        edges.append(_edge(step.script, runner_id, f"check {step.name}", "check"))
        owner.update((_key(e), step.script) for e in edges if _key(e) not in owner)
    keys = [_key(e) for e in edges]
    problems += sorted({f"{a} -> {b} comes from two entries of the manifest" for a, b in keys if keys.count((a, b)) > 1})
    if problems:
        raise MapLaneError("\n".join(problems))
    return Lane(nodes, edges, order, owner)


def _glob_boxes(path: str, path_ids: dict[str, str], named: set[str]) -> list[str] | None:
    """The boxes a glob output is drawn to: those whose path it matches and the step does not name another way, or,
    when it matches none, the box of the nearest folder it is in (not a top-level one); None when there is none."""
    rx = MANIFEST.glob_regex(path)
    hits = sorted(p for p in path_ids if rx.fullmatch(p))
    if hits:
        return [path_ids[p] for p in hits if p not in named]
    folder = path[:min(i for i in (path.find("*"), path.find("?"), len(path)) if i >= 0)].rsplit("/", 1)[0]
    while "/" in folder:
        if folder in path_ids:
            return [path_ids[folder]]
        folder = folder.rsplit("/", 1)[0]
    return None


def panels_lane(steps: Sequence["MANIFEST.PanelStep"], path_ids: dict[str, str], runner_id: str) -> Lane:
    """lane() for the panels manifest's steps: a box per box name, its links, and the links to and from the runner
    box. path_ids maps each box path to its id, the lane's own boxes included (a script to its step's box)."""
    nodes: list[Node] = []
    order: list[str] = []
    problems: list[str] = []
    edges: dict[EdgeKey, Edge] = {}
    owner: dict[EdgeKey, str] = {}
    guards: dict[str, list[str]] = {}
    for step in steps:
        if step.box not in order:
            order.append(step.box)
            nodes.append({"id": step.box, "label": step.label, "kind": "generator", "status": "live",
                          "domain": step.domain, "desc": step.desc, "path": step.script, "gen": GEN})
    for step in steps:
        named = {i.path for i in (*step.inputs, *step.outputs)}
        links: list[Edge] = []
        for kind, items in (("input", step.inputs), ("output", step.outputs)):
            for item in items:
                if kind == "output" and item.path in step.undrawn:
                    continue
                if any(c in item.path for c in "*?") and kind == "output":
                    targets = _glob_boxes(item.path, path_ids, named)
                else:
                    targets = [path_ids[item.path]] if item.path in path_ids else None
                if targets is None:
                    problems.append(f"step {step.name!r}: {kind} {item.path} is no box of the map; add a hand-kept box "
                                    f"with that path, or drop the {kind}")
                    continue
                for other in targets:
                    if other == step.box:
                        problems.append(f"step {step.name!r}: {kind} {item.path} is the step's own box")
                    elif kind == "input":
                        links.append(_edge(other, step.box, item.label, item.side))
                    else:
                        links.append(_edge(step.box, other, item.label, ""))
        if step.mode == "guard":
            guards.setdefault(step.box, []).append(step.name)
        else:
            links.append(_edge(runner_id, step.box, f"step {step.name}", ""))
        for e in links:
            have = edges.get(_key(e))
            if have is None:
                edges[_key(e)] = e
                owner[_key(e)] = step.box
            elif have != e:
                problems.append(f"{e['from']} -> {e['to']}: listed by steps of box {step.box} as "
                                f"{have.get('label', '')!r} and {e.get('label', '')!r}; give it one label and side")
            elif owner[_key(e)] != step.box:
                problems.append(f"{e['from']} -> {e['to']} comes from two entries of tools/pipeline/panels.toml")
    for box, names in guards.items():
        e = _edge(box, runner_id, f"guard {', '.join(names)}", "check")
        if _key(e) in edges:
            problems.append(f"{e['from']} -> {e['to']} is both a guard's link to the runner and a step's input")
        edges[_key(e)] = e
        owner[_key(e)] = box
    if problems:
        raise MapLaneError("\n".join(problems))
    return Lane(nodes, list(edges.values()), order, owner)


Entry = TypeVar("Entry", Node, Edge)


def _place(old: list[Entry], fresh: dict, owned: Callable[[Entry], bool], key: Callable[[Entry], object],
           after: Callable[[list[Entry], Entry], int]) -> list[Entry]:
    """`old` with each owned entry replaced by its fresh version in place (dropped when it has none), then each fresh
    entry not yet placed inserted after the index `after` gives (-1: first)."""
    out = []
    for item in old:
        if not owned(item):
            out.append(item)
        elif key(item) in fresh:
            out.append(fresh[key(item)])
    placed = {key(i) for i in out if owned(i)}
    for k, item in fresh.items():
        if k in placed:
            continue
        out.insert(after(out, item) + 1, item)
        placed.add(k)
    return out


def regenerate(data: Graph, steps: Sequence["MANIFEST.Step"] | None = None,
               panels: Sequence["MANIFEST.PanelStep"] | None = None) -> Graph:
    """The graph with its manifest lane replaced by a fresh one from the manifests (or from `steps` and `panels`, the
    panels steps; none when only `steps` is given)."""
    if steps is None:
        try:
            where = MANIFEST.repo_from(MANIFEST.tracked_files(), data)
            if panels is None:      # both manifests, checked against each other too (no file with two writers)
                steps, panels = MANIFEST.load_both(where=where)
            else:
                steps = MANIFEST.load(where=where)
        except MANIFEST.ManifestError as err:
            raise MapLaneError(str(err)) from err
    panels = panels or ()
    names = {s.name for s in steps}
    stale = sorted(set(HAND_KEPT_STEPS) - names)
    if stale:
        raise MapLaneError(f"HAND_KEPT_STEPS in tools/pipeline/map_lane.py names {', '.join(stale)}, no step of the "
                           f"manifest; remove it")
    others = [n for n in data["nodes"] if n.get("gen") != GEN]
    other_paths = {n["path"].rstrip("/"): n["id"] for n in others if n.get("path")}
    other_ids = {n["id"] for n in others}
    scripts = {s.script: s.name for s in steps if s.name not in HAND_KEPT_STEPS}
    boxes: dict[str, tuple[str, str]] = {}          # a panels box -> (its path, its first step)
    for s in panels:
        boxes.setdefault(s.box, (s.script, s.name))
    clash = sorted(p for p in scripts if p in other_paths or p in other_ids)
    clash_p = sorted(b for b, (p, _) in boxes.items() if {b, p} & (set(other_paths) | other_ids))
    both = sorted(b for b, (p, _) in boxes.items() if {b, p} & set(scripts))
    if clash or clash_p or both:
        raise MapLaneError("; ".join(
            [f"{p} is a hand-kept box, but step {scripts[p]!r} of tools/pipeline/checks.toml generates it: remove "
             f"the hand-kept box and its links to and from the files the step lists" for p in clash]
            + [f"{b} is a hand-kept box, but step {boxes[b][1]!r} of tools/pipeline/panels.toml generates it: remove "
               f"the hand-kept box and its links to and from the files the step lists" for b in clash_p]
            + [f"{b}: step {boxes[b][1]!r} of tools/pipeline/panels.toml and a step of tools/pipeline/checks.toml "
               f"both draw it; the map draws one box per script" for b in both]))
    missing = sorted(s.script for s in steps if s.name in HAND_KEPT_STEPS and s.script not in other_paths)
    if RUNNER not in other_paths:
        missing.append(RUNNER)
    if missing:
        raise MapLaneError(f"the graph has no hand-kept box for {', '.join(missing)}, which the manifest lane links "
                           f"to or leaves hand-kept; add it")
    path_ids = {**other_paths, **{p: p for p in scripts}, **{p: b for b, (p, _) in boxes.items()}}
    nodes, edges, order, owner = lane(steps, path_ids, other_paths[RUNNER])
    if panels:
        if MANIFEST.PANELS_RUNNER not in path_ids:
            raise MapLaneError(f"the graph has no box for {MANIFEST.PANELS_RUNNER}, which runs the steps of "
                               f"tools/pipeline/panels.toml; it is checks.toml's panels step")
        runner = path_ids[MANIFEST.PANELS_RUNNER]
        p_nodes, p_edges, p_order, p_owner = panels_lane(panels, path_ids, runner)
        twice = sorted({_key(e) for e in edges} & {_key(e) for e in p_edges})
        if twice:
            raise MapLaneError("\n".join(f"{a} -> {b} comes from both tools/pipeline/checks.toml and "
                                         f"tools/pipeline/panels.toml; list it in one" for a, b in twice))
        nodes, edges, order, owner = nodes + p_nodes, edges + p_edges, order + p_order, {**owner, **p_owner}
    for n in nodes:
        if n["path"] == MANIFEST.PANELS_RUNNER:     # it only runs other steps: a hovered chain stops there
            n.pop("gen")
            n.update(runner=True, gen=GEN)
    held = {_key(e): e for e in data["edges"] if e.get("gen") != GEN}
    fresh_edges: dict[EdgeKey, Edge] = {}
    problems: list[str] = []
    for e in edges:
        have = held.get(_key(e))
        if have is None:
            fresh_edges[_key(e)] = e
        elif not have.get("gen"):
            problems.append(f"hand-kept link {e['from']} -> {e['to']}: the manifest lane generates it; remove it from "
                            f"the graph (its label and side come from tools/pipeline/checks.toml)")
        elif (have.get("label", ""), have.get("side", "")) != (e.get("label", ""), e.get("side", "")):
            problems.append(f"link {e['from']} -> {e['to']} is drawn by the {have['gen']} lane as "
                            f"{have.get('label', '')!r} ({have.get('side', 'content')}) and listed in "
                            f"tools/pipeline/checks.toml as {e.get('label', '')!r} ({e.get('side', 'content')}); "
                            f"make them agree")
        # else: the same link, drawn by the other lane
    if problems:
        raise MapLaneError("\n".join(problems))
    rank = {nid: i for i, nid in enumerate(order)}
    fresh_nodes = {n["id"]: n for n in nodes}

    # Another lane rewrites its own entries where it likes (the agent-doc lane puts them last), so a new entry is
    # placed only after a hand-kept or manifest one: a place the next run finds again.
    def stays(entry: Node | Edge) -> bool:
        return entry.get("gen") in (None, GEN)

    def after_node(out: list[Node], node: Node) -> int:
        before = set(order[:rank[node["id"]]])
        at = [i for i, n in enumerate(out) if n["id"] in before] or [i for i, n in enumerate(out) if stays(n)]
        return at[-1] if at else -1

    def after_edge(out: list[Edge], edge: Edge) -> int:
        script = owner[_key(edge)]
        at = ([i for i, e in enumerate(out) if stays(e) and script in _key(e)]
              or [i for i, e in enumerate(out) if stays(e)])
        return at[-1] if at else -1

    new_nodes = _place(data["nodes"], fresh_nodes, lambda n: n.get("gen") == GEN, lambda n: n["id"], after_node)
    new_edges = _place(data["edges"], fresh_edges, lambda e: e.get("gen") == GEN, _key, after_edge)
    # invariants: the lane is exactly what was generated, and nothing else moved or went
    got_nodes = [n for n in new_nodes if n.get("gen") == GEN]
    got_edges = [e for e in new_edges if e.get("gen") == GEN]
    if (sorted(n["id"] for n in got_nodes) != sorted(fresh_nodes)
            or sorted(_key(e) for e in got_edges) != sorted(fresh_edges)
            or [n for n in new_nodes if n.get("gen") != GEN] != others
            or [e for e in new_edges if e.get("gen") != GEN] != [e for e in data["edges"] if e.get("gen") != GEN]):
        raise MapLaneError("internal: placing the lane lost, repeated or moved an entry")
    return {**data, "nodes": new_nodes, "edges": new_edges}


def main() -> int:
    graph_file = ROOT / "docs/pipeline-map/pipeline_map.json"
    try:
        graph = json.loads(graph_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        print(f"manifest map lane: cannot read {graph_file.relative_to(ROOT)}: {err}", file=sys.stderr)
        return 1
    try:
        fresh = regenerate(graph)
    except MapLaneError as err:
        print(f"manifest map lane: {err}", file=sys.stderr)
        return 1
    for n in fresh["nodes"]:
        if n.get("gen") == GEN:
            print(f"box  {n['id']}")
    for e in fresh["edges"]:
        if e.get("gen") == GEN:
            print(f"link {e['from']} -> {e['to']} ({e.get('label', '')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
