#!/usr/bin/env python3
"""pipeline_query.py

Ask the pipeline map (docs/pipeline-map/pipeline_map.json) what writes a file, what reads it and what is downstream.

    python3 tools/ops/pipeline_query.py find <text>             nodes whose id, path, label or desc contain the text
    python3 tools/ops/pipeline_query.py node <path-or-id>       the node, its inputs (writers) and outputs (readers)
    python3 tools/ops/pipeline_query.py up   <path-or-id> [--depth N]   what feeds it, transitively (default 2)
    python3 tools/ops/pipeline_query.py down <path-or-id> [--depth N]   what it feeds, transitively (default 2)

Add --json for machine output. A node is named by its id, its repo-relative path or an absolute path inside the repo.
An unknown name exits 1 with the closest matches. An edge runs from the writer or source to the reader.
"""
from __future__ import annotations

import argparse
import difflib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("build_pipeline_map", ROOT / "tools/ops/build_pipeline_map.py")
if _spec is None or _spec.loader is None:
    raise ImportError(f"cannot load {ROOT / 'tools/ops/build_pipeline_map.py'}")
BUILD = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BUILD)


Node = dict[str, Any]   # one node of the map's JSON: id, kind and path are str; the other fields vary by kind


class QueryError(Exception):
    pass


class Graph:
    def __init__(self, data: dict[str, Any], root: Path = ROOT):
        self.root = Path(os.path.abspath(root))
        self.nodes: dict[str, Node] = {n["id"]: n for n in data["nodes"]}
        self.by_path: dict[str, str] = {n["path"].rstrip("/"): n["id"] for n in data["nodes"] if n.get("path")}
        self.ins: dict[str, list[tuple[str, str]]] = {i: [] for i in self.nodes}
        self.outs: dict[str, list[tuple[str, str]]] = {i: [] for i in self.nodes}
        for e in data["edges"]:
            self.outs[e["from"]].append((e["to"], e.get("label", "")))
            self.ins[e["to"]].append((e["from"], e.get("label", "")))

    def _known(self, key: str) -> bool:
        return key in self.nodes or key in self.by_path or key.rstrip("/") in self.by_path

    def normalise(self, name: str) -> str:
        name = name.strip()
        if not name:
            raise QueryError("empty node name")
        # Lexical only: the worktree's media/ and ops/car-cards/ are symlinks out of the checkout, so never resolve them.
        if os.path.isabs(name):
            full = os.path.normpath(name)
        elif self._known(os.path.normpath(name)):
            full = os.path.normpath(os.path.join(self.root, name))  # a repo-relative path or id wins over the cwd
        elif os.path.exists(name):
            full = os.path.normpath(os.path.abspath(name))  # a path typed relative to the current folder
        else:
            full = os.path.normpath(os.path.join(self.root, name))  # an id, or a path relative to the repo
        rel = os.path.relpath(full, self.root)
        if rel == ".." or rel.startswith(".." + os.sep):
            raise QueryError(f"{name} is outside the repo {self.root}")
        return Path(rel).as_posix()

    def resolve(self, name: str) -> str:
        key = self.normalise(name)
        for cand in (key, key.rstrip("/")):
            if cand in self.nodes:
                return cand
            if cand in self.by_path:
                return self.by_path[cand]
        near = difflib.get_close_matches(key, list(self.nodes) + list(self.by_path), n=5, cutoff=0.5)
        near += [i for i in self.nodes if key.lower() in i.lower() and i not in near][:5]
        hint = "closest: " + ", ".join(near[:8]) if near else "no close match; try `find`"
        raise QueryError(f"no node {name!r} ({hint})")

    def find(self, text: str) -> list[Node]:
        t = text.lower()
        if not t:
            raise QueryError("empty search text")
        return [n for n in self.nodes.values()
                if any(t in str(n.get(k, "")).lower() for k in ("id", "path", "label", "desc"))]

    def walk(self, start: str, direction: str, depth: int) -> list[tuple[int, str, str, str]]:
        """Pre-order (level, id, edge label, ref). Each node sits at its shortest level and is expanded once;
        another edge to it is listed with ref "above" (already printed) or "below" (printed later), not expanded."""
        links = self.ins if direction == "up" else self.outs
        level = {start: 0}
        parent: dict[str, str] = {}
        queue = [start]
        for nid in queue:  # breadth first, so a node is first reached by a shortest path
            if level[nid] >= depth:
                continue
            for nxt, _ in links[nid]:
                if nxt not in level:
                    level[nxt] = level[nid] + 1
                    parent[nxt] = nid
                    queue.append(nxt)
        out: list[tuple[int, str, str, str]] = []

        printed = {start}

        def go(nid: str) -> None:
            if level[nid] >= depth:
                return
            for nxt, label in links[nid]:
                if nxt in printed:
                    out.append((level[nid] + 1, nxt, label, "above"))
                elif parent.get(nxt) == nid:
                    printed.add(nxt)
                    out.append((level[nid] + 1, nxt, label, ""))
                    go(nxt)
                else:  # reached by a shorter route that is printed later, at its own level
                    out.append((level[nid] + 1, nxt, label, "below"))
        go(start)
        return out


def load_graph(path: Path) -> dict[str, Any]:
    """Read the graph with a structure check only: a stale path elsewhere in the map must not block a query."""
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or not all(isinstance(data.get(k), list) for k in ("nodes", "edges")):
        raise QueryError(f"{path} needs 'nodes' and 'edges' lists")
    ids: set[str] = set()
    for n in data["nodes"]:
        if not isinstance(n, dict) or not n.get("id") or not n.get("kind"):
            raise QueryError(f"{path}: a node lacks an id or kind: {n}")
        if n["id"] in ids:
            raise QueryError(f"{path}: node {n['id']!r} is listed twice")
        ids.add(n["id"])
    for e in data["edges"]:
        if not isinstance(e, dict) or e.get("from") not in ids or e.get("to") not in ids:
            raise QueryError(f"{path}: an edge has an end that is not a node: {e}")
    return data


def ident(n: Node) -> str:
    name: str = n.get("path") or n["id"]
    return name


def line(n: Node, label: str = "") -> str:
    tag = f" [{label}]" if label else ""
    return f"{ident(n)}{tag} ({n['kind']}, {n.get('status', 'live')})"


def cmd_find(g: Graph, a: argparse.Namespace) -> tuple[str, object]:
    hits = g.find(a.text)
    text = "\n".join(f"{ident(n)} | {n['kind']} | {n.get('status', 'live')} | {n.get('desc', '')}" for n in hits)
    return text or f"no node matches {a.text!r}", [{"node": h["id"], "detail": h} for h in hits]


def cmd_node(g: Graph, a: argparse.Namespace) -> tuple[str, object]:
    nid = g.resolve(a.name)
    n = g.nodes[nid]
    lines = [line(n), f"id: {nid}", f"desc: {n.get('desc', '')}", "inputs (written or fed by):"]
    lines += [f"  {line(g.nodes[s], lab)}" for s, lab in g.ins[nid]] or ["  none"]
    lines.append("outputs (read or used by):")
    lines += [f"  {line(g.nodes[t], lab)}" for t, lab in g.outs[nid]] or ["  none"]
    obj = {"node": nid, "detail": n, "inputs": [{"node": s, "label": lab} for s, lab in g.ins[nid]],
           "outputs": [{"node": t, "label": lab} for t, lab in g.outs[nid]]}
    return "\n".join(lines), obj


def cmd_walk(g: Graph, a: argparse.Namespace) -> tuple[str, object]:
    if a.depth < 0:
        raise QueryError("--depth must be 0 or more")
    nid = g.resolve(a.name)
    rows = g.walk(nid, a.cmd, a.depth)
    lines = [line(g.nodes[nid])]
    for level, rid, label, ref in rows:
        lines.append("  " * level + line(g.nodes[rid], label) + (f" (shown {ref})" if ref else ""))
    obj = {"node": nid, "direction": a.cmd, "depth": a.depth,
           "items": [{"level": lv, "node": rid, "label": lab, "shown": ag} for lv, rid, lab, ag in rows]}
    return "\n".join(lines), obj


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--graph", type=Path, default=BUILD.GRAPH, help="graph file (default: the repo's)")
    p.add_argument("--json", action="store_true", help="print JSON")
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("find", help="search id, path, label and desc")
    f.add_argument("text")
    n = sub.add_parser("node", help="a node with its direct inputs and outputs")
    n.add_argument("name")
    for d, h in (("up", "transitive upstream"), ("down", "transitive downstream")):
        w = sub.add_parser(d, help=h)
        w.add_argument("name")
        w.add_argument("--depth", type=int, default=2)
    return p


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    try:
        g = Graph(load_graph(a.graph))
        text, obj = {"find": cmd_find, "node": cmd_node, "up": cmd_walk, "down": cmd_walk}[a.cmd](g, a)
    except (QueryError, OSError, json.JSONDecodeError) as e:
        print(f"pipeline_query: {e}", file=sys.stderr)
        return 1
    print(json.dumps(obj, indent=1) if a.json else text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
