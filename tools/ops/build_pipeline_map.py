#!/usr/bin/env python3
"""build_pipeline_map.py

Write docs/pipeline-map/index.html, a zoomable map of every source, generator and output in the repo, from the graph
in docs/pipeline-map/pipeline_map.json.

    python3 tools/ops/build_pipeline_map.py            write the page
    python3 tools/ops/build_pipeline_map.py --check    exit 1 when the graph is broken or the page is out of date

The graph file holds domains (the horizontal lanes), nodes and edges. A node's `path` must exist in the checkout
unless the node says `"local": true` (a gitignored mirror or a file made on a host). This script checks the graph and
writes one self-contained page; the layout and the viewer are in tools/ops/pipeline_map.js, inlined into the page, so
the page can redraw any subset (some lanes, or the chain around one file) without build tools.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "docs" / "pipeline-map" / "pipeline_map.json"
PAGE = ROOT / "docs" / "pipeline-map" / "index.html"
SCRIPT = Path(__file__).resolve().with_name("pipeline_map.js")

KINDS = {
    "structured": ("Structured data", "#dbeafe", "#1e40af"),
    "unstructured": ("Unstructured source", "#fef3c7", "#92400e"),
    "generator": ("Generator / script", "#dcfce7", "#166534"),
    "output": ("Generated output", "#f3e8ff", "#6b21a8"),
    "external": ("External tool / repo", "#e5e7eb", "#374151"),
    "host": ("Host / runtime", "#fee2e2", "#991b1b"),
    "human": ("Hand work", "#fce7f3", "#9d174d"),
}
STATUSES = ("live", "parked", "retired")


class GraphError(Exception):
    pass


def load(path: Path) -> dict:
    data = json.loads(path.read_text())
    domains = [d["id"] for d in data["domains"]]
    if len(set(domains)) != len(domains):
        raise GraphError("a domain id is repeated")
    ids: set[str] = set()
    problems = []
    if not data.get("nodes"):
        raise GraphError("the graph has no nodes")
    paths: dict[str, str] = {}
    for n in data["nodes"]:
        if not n.get("id"):
            problems.append(f"a node has no id: {n}")
            continue
        nid = n["id"]
        if nid in ids:
            problems.append(f"node {nid!r} is listed twice")
        ids.add(nid)
        if n.get("kind") not in KINDS:
            problems.append(f"node {nid!r}: kind {n.get('kind')!r} is not one of {', '.join(KINDS)}")
        if n.get("status", "live") not in STATUSES:
            problems.append(f"node {nid!r}: status {n.get('status')!r} is not one of {', '.join(STATUSES)}")
        if n.get("domain") not in domains:
            problems.append(f"node {nid!r}: domain {n.get('domain')!r} is not a listed domain")
        p = n.get("path", "")
        if p and p.rstrip("/") in paths:
            problems.append(f"node {nid!r}: path {p} is already node {paths[p.rstrip('/')]!r}")
        if p:
            paths[p.rstrip("/")] = nid
        if p and not n.get("local") and not (ROOT / p.rstrip("/")).exists():
            problems.append(f"node {nid!r}: path {p} does not exist (mark it \"local\": true if it is a gitignored mirror)")
    seen_edges = set()
    linked: set[str] = set()
    for e in data["edges"]:
        if not e.get("from") or not e.get("to"):
            problems.append(f"an edge lacks a from or to end: {e}")
            continue
        linked.update((e["from"], e["to"]))
        for end in ("from", "to"):
            if e[end] not in ids:
                problems.append(f"edge {e['from']} -> {e['to']}: {end} end is not a node")
        key = (e["from"], e["to"])
        if key in seen_edges:
            problems.append(f"edge {e['from']} -> {e['to']} is listed twice")
        seen_edges.add(key)
        if e["from"] == e["to"]:
            problems.append(f"edge {e['from']} points at itself")
    for nid in sorted(ids - linked):
        problems.append(f"node {nid!r} has no links; link it or remove it")
    if problems:
        raise GraphError("\n".join(problems))
    return data


def esc(s: str) -> str:
    return html.escape(s, quote=True)


PAGE_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HART pipeline map</title>
<style>
html,body{margin:0;height:100%;font:13px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#111;background:#fafafa}
#wrap{position:fixed;inset:0;overflow:hidden;cursor:grab}
#wrap.drag{cursor:grabbing}
svg{width:100%;height:100%;display:block;user-select:none}
.panel{background:#fff;border:1px solid #ccc;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.12)}
#bar{position:fixed;top:10px;left:10px;z-index:5;padding:8px 10px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;
 max-width:calc(100vw - 420px)}
#bar input[type=search]{width:240px;padding:4px 6px}
#bar button{padding:3px 9px}
#bar h1{font-size:14px;margin:0 6px 0 0}
#view{flex-basis:100%;color:#333}
#view:empty{display:none}
#lanes{position:relative}
#lanes summary{cursor:pointer;padding:3px 8px;border:1px solid #bbb;border-radius:4px;list-style:none}
#lanelist{position:absolute;top:30px;left:0;z-index:6;padding:8px 10px;white-space:nowrap;line-height:1.9}
#lanelist a{color:#1d4ed8;cursor:pointer;font-size:12px}
span.sw{display:inline-block;width:14px;height:11px;border:1px solid transparent;border-radius:3px;vertical-align:-1px;margin-right:4px}
#legend{position:fixed;bottom:10px;left:10px;max-width:440px;z-index:5;padding:8px 10px;font-size:12px}
#legend div{margin:2px 0}
#info{position:fixed;top:10px;right:10px;bottom:10px;width:360px;z-index:5;padding:12px 14px;overflow:auto;display:none}
#info h2{font-size:16px;margin:0 0 4px}
#info code{font-size:12px;word-break:break-all}
#info ul{padding-left:18px;margin:4px 0 10px}
#info a{cursor:pointer;color:#1d4ed8}
#info .off{color:#888;font-size:11px}
#info .close{float:right;cursor:pointer;border:0;background:none;font-size:18px}
#info .chain{background:#f1f5f9;border-radius:6px;padding:8px;margin:8px 0 12px;line-height:2}
.band{font-size:110px;font-weight:800;opacity:.35}
.band.small{font-size:22px;opacity:.6}
.edge{fill:none;stroke:#64748b;stroke-width:1.3;stroke-opacity:.55}
.edge.back{stroke-dasharray:6 4}
.elabel{font-size:10px;fill:#334155;paint-order:stroke;stroke:#fff;stroke-width:3px}
.node .box{stroke-width:1.2}
.node .t{font-size:13px;font-weight:700}
.node .p{font:10.5px ui-monospace,Menlo,monospace;fill:#334155}
.node .d{font-size:11px;fill:#1f2937}
.node{cursor:pointer}
.node.parked .box{stroke-dasharray:6 3}
.node.retired .box{stroke-dasharray:2 3}
.node.parked,.node.retired{opacity:.7}
.node.hit .box{stroke:#dc2626;stroke-width:4}
svg.focus .node,svg.focus .edge,svg.focus .elabel{opacity:.12}
svg.focus .node.on{opacity:.5}
svg.focus .node.near,svg.focus .elabel.near{opacity:1}
svg.focus .elabel.on:not(.near){opacity:0}
svg.focus .edge.on{opacity:.45;stroke-opacity:1;stroke-width:1.6;stroke:#1d4ed8}
svg.focus .edge.near{opacity:1;stroke-width:3}
svg.focus .edge.on.upstream{stroke:#b45309}
svg.focus .node.sel .box{stroke:#dc2626;stroke-width:4}
.hidden{display:none}
</style></head><body>
<div id="wrap"></div>
<div id="bar" class="panel"><h1>HART pipeline map</h1>
<input type="search" id="q" placeholder="Find a file, script or output…">
<span id="hits"></span>
<button id="fit" title="Show everything (F)">Fit</button><button id="zin">+</button><button id="zout">−</button>
<details id="lanes"><summary>Lanes ▾</summary><div id="lanelist" class="panel"></div></details>
<label><input type="checkbox" id="parked" checked> parked</label>
<label><input type="checkbox" id="retired" checked> retired</label>
<label title="Show edge labels"><input type="checkbox" id="labels" checked> edge labels</label>
<span id="view"></span>
</div>
<details id="legend" class="panel"><summary><b>Legend and help</b></summary><b>Kind</b> (box colour)__LEGEND__
<div style="margin-top:6px"><b>Lane stripe</b> = domain. Dashed box = parked, dotted = retired, dashed line = feeds back
to an earlier step.</div>
<div>Scroll or pinch to zoom, drag to pan, F fits, Esc clears. Click a box for what feeds it (amber) and what it feeds
(blue).</div>
<div><b>Subsets:</b> Lanes ▾ picks the lanes to draw (or "only" one). Double-click a box, or use "Show only this box's
chain" in its panel, to draw just that file and what feeds it and what it feeds, to a chosen number of steps. The
address bar keeps the view, so it can be bookmarked or shared.</div>
<div style="color:#666">Built __DATE__ from docs/pipeline-map/pipeline_map.json · __COUNTS__</div></details>
<div id="info" class="panel"></div>
<script>const DATA = __DATA__;</script>
<script>
__SCRIPT__
</script></body></html>
"""


def render(data: dict) -> str:
    legend = "".join(
        f'<div><span class="sw" style="background:{fill};border-color:{ink}"></span>{esc(label)}</div>'
        for label, fill, ink in KINDS.values()
    )
    page_data = {
        "nodes": [
            {k: n[k] for k in ("id", "label", "kind", "status", "domain", "desc", "path", "local") if k in n}
            for n in data["nodes"]
        ],
        "edges": [{k: e[k] for k in ("from", "to", "label") if k in e} for e in data["edges"]],
        "kinds": {k: list(v) for k, v in KINDS.items()},
        "domains": [{"id": d["id"], "label": d["label"], "color": d["color"]} for d in data["domains"]],
        "domainColor": {d["id"]: d["color"] for d in data["domains"]},
    }
    counts = f'{len(data["nodes"])} boxes, {len(data["edges"])} links'
    return (
        PAGE_TEMPLATE.replace("__LEGEND__", legend)
        .replace("__DATE__", esc(data.get("updated", "")))
        .replace("__COUNTS__", counts)
        .replace("__DATA__", json.dumps(page_data, separators=(",", ":")).replace("<", "\\u003c"))
        .replace("__SCRIPT__", SCRIPT.read_text())
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[2])
    ap.add_argument("--check", action="store_true", help="fail when the graph is broken or the page is stale")
    ap.add_argument("--graph", type=Path, default=GRAPH)
    ap.add_argument("--out", type=Path, default=PAGE)
    args = ap.parse_args(argv)
    try:
        data = load(args.graph)
    except GraphError as err:
        print(f"{args.graph}: the graph has problems:\n{err}", file=sys.stderr)
        return 1
    page = render(data)
    if args.check:
        if not args.out.exists() or args.out.read_text() != page:
            print(f"{args.out} is out of date: run python3 tools/ops/build_pipeline_map.py", file=sys.stderr)
            return 1
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(page)
    print(f"wrote {args.out.relative_to(ROOT)}: {len(data['nodes'])} nodes, {len(data['edges'])} edges")
    return 0


if __name__ == "__main__":
    sys.exit(main())
