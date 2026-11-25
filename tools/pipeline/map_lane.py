#!/usr/bin/env python3
"""map_lane.py

The manifest lane of the pipeline map (ADR-037 stage 3): a box for each check.sh step's script and its links, read
from the step manifest, tools/pipeline/checks.toml, so the map cannot drift from what check.sh runs.
tools/ops/build_pipeline_map.py calls regenerate() after the agent-doc lane and writes the result into
docs/pipeline-map/pipeline_map.json; its --check fails when the committed graph differs.

    python3 tools/pipeline/map_lane.py     print the boxes and links it would generate

Each box and link is marked "gen": "manifest" in the graph. For each step (but those in HAND_KEPT_STEPS):
- a "generator" box for its script: id and path the script, label, domain and desc from the step;
- input -> script for each input, with its label and side;
- script -> output for each output, with its label;
- script -> tools/check.sh, side "check", label "check <step name>": check.sh runs it as that job.

An input or output names a box by its path, so it must be one: a hand-kept box, an agent doc's, or another step's
script. A link another lane already draws (the agent-doc lane links each doc check_agent_docs.py reads to it) is left
to that lane, but only when its label and side are the same; otherwise it is an error. A hand-kept box or link with
the key of a generated one is an error: the generated one replaces it, so drop the hand one.

The graph's node order is the layout's tie-break, so the lane keeps each generated box and link where the file has it.
A new box goes after the box of the step before it in the manifest, and a new link after the last link of its script
box; with none, after the last hand-kept or manifest entry (another lane may move its own entries on the next run). Links between scripts and code (imports, calls), from hosts or external boxes,
and from tools/check.sh into a script stay hand-kept.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if "pipeline_manifest" not in sys.modules:      # once per process: check_stamps.py and the tests load it by this name
    _spec = importlib.util.spec_from_file_location("pipeline_manifest", ROOT / "tools/pipeline/manifest.py")
    sys.modules["pipeline_manifest"] = importlib.util.module_from_spec(_spec)    # its dataclasses look it up there
    _spec.loader.exec_module(sys.modules["pipeline_manifest"])
MANIFEST = sys.modules["pipeline_manifest"]

GEN = "manifest"
RUNNER = "tools/check.sh"           # the box every step links to: check.sh runs each step as a job
# steps whose box and links stay hand-kept, with the reason
HAND_KEPT_STEPS = {
    "panels": "build_panels.sh is a runner box that only runs the panels steps, whose links it carries; the panels "
              "manifest (ADR-037 stage 5) generates it",
}


class MapLaneError(Exception):
    """The manifest lane cannot be drawn into this graph; the message says what to change."""


def _key(e: dict) -> tuple[str, str]:
    return (e["from"], e["to"])


def _edge(a: str, b: str, label: str, side: str) -> dict:
    e = {"from": a, "to": b}
    if label:
        e["label"] = label
    if side:
        e["side"] = side
    e["gen"] = GEN
    return e


def lane(steps, path_ids: dict[str, str], runner_id: str) -> tuple[list[dict], list[dict], list[str]]:
    """The generated boxes, links, and each box's id in manifest order. path_ids maps each box path of the graph
    (without a trailing /) to its id, the lane's own boxes included."""
    nodes, edges, order, problems = [], [], [], []
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
    keys = [_key(e) for e in edges]
    problems += sorted({f"{a} -> {b} comes from two entries of the manifest" for a, b in keys if keys.count((a, b)) > 1})
    if problems:
        raise MapLaneError("\n".join(problems))
    return nodes, edges, order


def _place(old: list, fresh: dict, owned, key, after) -> list:
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


def regenerate(data: dict, steps=None) -> dict:
    """The graph with its manifest lane replaced by a fresh one from the manifest (or from `steps`)."""
    if steps is None:
        try:
            steps = MANIFEST.load(where=MANIFEST.repo_from(MANIFEST.tracked_files(), data))
        except MANIFEST.ManifestError as err:
            raise MapLaneError(str(err)) from None
    names = {s.name for s in steps}
    stale = sorted(set(HAND_KEPT_STEPS) - names)
    if stale:
        raise MapLaneError(f"HAND_KEPT_STEPS in tools/pipeline/map_lane.py names {', '.join(stale)}, no step of the "
                           f"manifest; remove it")
    others = [n for n in data["nodes"] if n.get("gen") != GEN]
    other_paths = {n["path"].rstrip("/"): n["id"] for n in others if n.get("path")}
    other_ids = {n["id"] for n in others}
    scripts = {s.script: s.name for s in steps if s.name not in HAND_KEPT_STEPS}
    clash = sorted(p for p in scripts if p in other_paths or p in other_ids)
    if clash:
        raise MapLaneError("; ".join(f"{p} is a hand-kept box, but step {scripts[p]!r} of tools/pipeline/checks.toml "
                                     f"generates it: remove the hand-kept box and its links to and from the files "
                                     f"the step lists" for p in clash))
    missing = sorted(s.script for s in steps if s.name in HAND_KEPT_STEPS and s.script not in other_paths)
    if RUNNER not in other_paths:
        missing.append(RUNNER)
    if missing:
        raise MapLaneError(f"the graph has no hand-kept box for {', '.join(missing)}, which the manifest lane links "
                           f"to or leaves hand-kept; add it")
    nodes, edges, order = lane(steps, {**other_paths, **{p: p for p in scripts}}, other_paths[RUNNER])
    held = {_key(e): e for e in data["edges"] if e.get("gen") != GEN}
    fresh_edges, problems = {}, []
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
    def stays(entry: dict) -> bool:
        return entry.get("gen") in (None, GEN)

    def after_node(out: list, node: dict):
        before = set(order[:rank[node["id"]]])
        at = [i for i, n in enumerate(out) if n["id"] in before] or [i for i, n in enumerate(out) if stays(n)]
        return at[-1] if at else -1

    def after_edge(out: list, edge: dict):
        script = edge["to"] if edge["to"] in fresh_nodes else edge["from"]
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
