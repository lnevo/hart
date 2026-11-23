#!/usr/bin/env python3
"""build_pipeline_map.py

Write docs/pipeline-map/index.html, a zoomable map of every source, generator and output in the repo, from the graph
in docs/pipeline-map/pipeline_map.json.

    python3 tools/ops/build_pipeline_map.py            write the page
    python3 tools/ops/build_pipeline_map.py --check    exit 1 when the graph is broken or the page is out of date
    python3 tools/ops/build_pipeline_map.py --public --out www/... [--back HREF]   the website copy (with --check too)

The website copy renames the gitignored mirrors (PUBLIC_NAMES), whose real paths the site build treats as leaks, and
can carry a link back to the page that links to it.

The agent-doc lane (domain "agents": boxes and links marked "gen": "agent-docs") is generated from the files by
tools/ops/agent_docs_map.py: a plain run rewrites it in the graph file, and --check fails when the committed graph
differs. Everything else in the graph is hand-kept. The order of the nodes is kept as it is: the layout breaks
cycles in node order, so a sorted file draws a much wider map. Locally the file merges itself:
tools/ops/merge_pipeline_map.py is its git merge driver.

The graph file holds domains (the horizontal lanes), nodes and edges. A node's `path` must exist in the checkout
unless the node says `"local": true` (a gitignored mirror or a file made on a host). A node marked `"runner": true`
only runs other steps (tools/check.sh, build_panels.sh). An edge may carry `"side"`, one of SIDES, for a link that
carries no content on to the next step: "check" (a check or comparison reads it), "pointer" (a doc names another),
"pull" (a Store pull back into the sources), "mirror" (a folder holds a copy), "capture" (a page screenshot),
"history" (git history of a file). A hovered line's chain on the page stops at runners and does not walk side links;
both are still drawn, and a click still traces the full reach. This script checks the graph and
writes one self-contained page; the layout and the viewer are in tools/ops/pipeline_map.js, inlined into the page, so
the page can redraw any subset (some lanes, or the chain around one file) without build tools.
"""
from __future__ import annotations

import argparse
import functools
import html
import importlib.util
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "docs" / "pipeline-map" / "pipeline_map.json"
SIDES = ("check", "pointer", "pull", "mirror", "capture", "history")  # an edge's "side": why it carries no content on
PAGE = ROOT / "docs" / "pipeline-map" / "index.html"
SCRIPT = Path(__file__).resolve().with_name("pipeline_map.js")
# the website copy, as tools/check.sh checks it
SITE_BUILD = ("python3 tools/ops/build_pipeline_map.py --public --out www/library/pipeline-map.html "
              "--back repository-guide.html")

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
# Gitignored mirrors whose paths the website's leak check rejects; the public page names them like this instead.
PUBLIC_NAMES = {
    "external/sts-docker-data": "sts-docker-data (mirror)",
    "ops/car-cards": "car-cards workspace",
    "media/hart-research": "media mirror: hart-research",
}


class GraphError(Exception):
    pass


_agent_spec = importlib.util.spec_from_file_location("agent_docs_map", Path(__file__).resolve().with_name("agent_docs_map.py"))
AGENT_DOCS = importlib.util.module_from_spec(_agent_spec)
_agent_spec.loader.exec_module(AGENT_DOCS)


@functools.cache
def tracked_paths() -> frozenset[str]:
    """Every git-tracked file in the repo and every folder that holds one, so the check is the same on any clone."""
    out = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT, text=True)
    paths = set()
    for f in filter(None, out.split("\0")):
        parts = f.split("/")
        paths.update("/".join(parts[:k]) for k in range(1, len(parts) + 1))
    return frozenset(paths)


def read(path: Path) -> dict:
    """The graph file as data, with its three lists; not yet checked further (validate does that)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as err:
        raise GraphError(f"cannot read the graph: {err.strerror}") from None
    except json.JSONDecodeError as err:
        raise GraphError(f"the graph is not valid JSON: {err}") from None
    if not isinstance(data, dict):
        raise GraphError("the graph must be a JSON object")
    for key in ("domains", "nodes", "edges"):
        if not isinstance(data.get(key), list):
            raise GraphError(f"the graph needs a {key!r} list")
        bad = [item for item in data[key] if not isinstance(item, dict)]
        if bad:
            raise GraphError(f"every entry of {key!r} must be an object: {bad[0]!r}")
    bad_paths = [n for n in data["nodes"] if not isinstance(n.get("path", ""), str)]
    if bad_paths:
        raise GraphError(f"a node's path must be text: {bad_paths[0]!r}")
    return data


def node_key(n: dict) -> str:
    """What names a node: its id."""
    return n["id"]


def edge_key(e: dict) -> tuple[str, str]:
    """What names an edge: its two ends (the graph holds one edge per pair)."""
    return (e["from"], e["to"])


def graph_text(data: dict) -> str:
    """The graph as the committed file holds it."""
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n"


def regenerate(data: dict) -> dict:
    """The graph with its generated parts (the agent-doc lane, tools/ops/agent_docs_map.py) rebuilt from the files."""
    try:
        return AGENT_DOCS.regenerate(data)
    except AGENT_DOCS.AgentDocsMapError as err:
        raise GraphError(f"agent-doc lane: {err}") from None


def load(path: Path) -> dict:
    return validate(read(path))


def validate(data: dict, tracked: bool = True) -> dict:
    """The graph, or GraphError naming every problem. tracked=False leaves out only the check that each node's path
    is tracked in git: the merge driver (tools/ops/merge_pipeline_map.py) runs before git has written the merged
    tree, so the paths the other branch adds are not tracked yet; tools/check.sh checks them after the merge."""
    for key in ("domains", "nodes", "edges"):
        if not isinstance(data.get(key), list):
            raise GraphError(f"the graph needs a {key!r} list")
    for d in data["domains"]:
        missing = [k for k in ("id", "label", "color") if not d.get(k)]
        if missing:
            raise GraphError(f"domain {d} lacks {', '.join(missing)}")
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
        if not n.get("label"):
            problems.append(f"node {nid!r} has no label")
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
        if p and (Path(p).is_absolute() or ".." in Path(p).parts):
            problems.append(f"node {nid!r}: path {p} is outside the repo")
        if p and p.rstrip("/") in paths:
            problems.append(f"node {nid!r}: path {p} is already node {paths[p.rstrip('/')]!r}")
        if p:
            paths[p.rstrip("/")] = nid
        if tracked and p and not n.get("local") and p.rstrip("/") not in tracked_paths():
            problems.append(f"node {nid!r}: path {p} does not exist in git (mark it \"local\": true if it is a gitignored mirror, a submodule file or made on a host)")
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
        key = edge_key(e)
        if key in seen_edges:
            problems.append(f"edge {e['from']} -> {e['to']} is listed twice")
        seen_edges.add(key)
        if e["from"] == e["to"]:
            problems.append(f"edge {e['from']} points at itself")
        if "side" in e and e["side"] not in SIDES:
            problems.append(f"edge {e['from']} -> {e['to']}: side {e['side']!r} is not one of {', '.join(SIDES)}")
    for nid in sorted(ids - linked):
        problems.append(f"node {nid!r} has no links; link it or remove it")
    presets = data.get("presets", [])  # the page's start-here buttons
    if not isinstance(presets, list):
        problems.append("presets must be a list")
        presets = []
    for i, pr in enumerate(presets):
        if not isinstance(pr, dict):
            problems.append(f"preset {i + 1} must be an object: {pr!r}")
            continue
        if not isinstance(pr.get("label"), str) or not pr["label"] or not isinstance(pr.get("focus"), str) or pr["focus"] not in ids:
            problems.append(f"preset {i + 1} needs a label and a focus that is a node: {pr}")
        for side in ("up", "down"):
            v = pr.get(side)
            if not (v == "all" or isinstance(v, int) and not isinstance(v, bool) and v >= 0):
                problems.append(f"preset {pr.get('label')!r}: {side} must be a step count or \"all\"")
    if problems:
        raise GraphError("\n".join(problems))
    return data


def esc(s: str) -> str:
    return html.escape(s, quote=True)


PAGE_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HART pipeline map</title>__SITEHEAD__
<meta name="description" content="The source files, scripts and generated outputs in the HART repository, drawn as boxes and arrows by lane. Pick a file to see what feeds it and what it feeds, from the schematic to the panels, tables.xml and the website.">
<style>
html,body{margin:0;height:100%;font:13px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#111;background:#fafafa}
#stage{position:fixed;inset:0}
#wrap{position:absolute;inset:0;overflow:hidden;cursor:grab}
#wrap.drag{cursor:grabbing}
svg{width:100%;height:100%;display:block;user-select:none}
.panel{background:#fff;border:1px solid #ccc;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.12)}
#bar{position:absolute;top:10px;left:10px;z-index:8;padding:0;max-width:calc(100vw - 420px)}
#row1{position:relative;min-height:40px;box-sizing:border-box;padding:4px 10px;display:flex;gap:6px;align-items:center;flex-wrap:wrap}
#row1 label{white-space:nowrap}
#bar input[type=search]{width:90px;padding:4px 6px}
#bar #file{width:150px;padding:4px 6px}
#bar button{padding:3px 8px}
#bar h1{font-size:14px;margin:0 2px 0 0;white-space:nowrap}
#back{color:#1d4ed8;text-decoration:none;margin-right:2px;font-size:16px}
#bar [hidden]{display:none!important}
#btns{display:flex;gap:4px;align-items:center;flex-wrap:nowrap;white-space:nowrap}
#hits{color:#555;font-size:12px}
#strip2{display:flex;gap:6px 14px;align-items:center;flex-wrap:wrap;padding:4px 10px;border-top:1px solid #ddd;color:#333;font-size:12px}
#strip2 .sep{color:#bbb}
#view:empty{display:none}
#depth{display:flex;gap:6px 14px;flex-wrap:wrap}
#depth .side{white-space:nowrap}
#depth b{display:inline-block;min-width:22px;text-align:center}
#strip2 button{padding:1px 8px;font-size:12px}
.menu{position:relative}
.menu>summary{cursor:pointer;padding:3px 8px;border:1px solid #bbb;border-radius:4px;list-style:none;white-space:nowrap}
.menu>summary::-webkit-details-marker{display:none}
.pop{position:absolute;top:30px;left:0;z-index:6;padding:8px 10px;white-space:nowrap;line-height:1.9;max-height:70vh;overflow:auto;
 max-width:calc(100vw - 20px);box-sizing:border-box}
#viewlist label{display:block}
#viewlist>b{display:block;margin-top:6px;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#666}
#viewlist>b:first-child{margin-top:0}
#lanelist .foot{margin-top:6px}
#btns .gap{width:8px}
#lanelist a{color:#1d4ed8;cursor:pointer;font-size:12px}
#tree{line-height:1.7;min-width:260px}
#tree details details,#tree details>a{margin-left:14px}
#bar #tree summary{cursor:pointer;border:0;background:none;padding:0;list-style:revert}
#tree a{display:block;cursor:pointer;color:#1d4ed8}
#tree .c{color:#888;font-size:11px}
#lanelist>b{display:block;margin-top:6px}
#lanelist>b:first-child{margin-top:0}
#lanelist .note{color:#666;font-size:11px;white-space:normal}
#lanelist>label.inl{display:inline-block;margin-right:10px}
#presets{display:flex;flex-direction:column;gap:4px;align-items:stretch}
#more{display:none;position:static}
svg{--bsc:var(--bscale,1)} svg.far{--bsc:1}
svg.previewing #edges,svg.previewing #elabels{opacity:.3}
svg.settling .node{transition:transform .28s ease-out}
svg.settling #edges,svg.settling #elabels{animation:settlein .28s ease-out}
@keyframes settlein{from{opacity:.3}to{opacity:1}}
.node.folder .box{stroke-dasharray:7 4;stroke-width:calc(2 * var(--bsc))}
span.sw{display:inline-block;width:14px;height:11px;border:1px solid transparent;border-radius:3px;vertical-align:-1px;margin-right:4px}
#legend{position:absolute;bottom:10px;left:10px;max-width:440px;z-index:5;padding:8px 10px;font-size:12px}
#legend div{margin:2px 0}
#tour{position:fixed;z-index:20;width:min(330px,calc(100vw - 20px));padding:12px 14px;box-sizing:border-box}
#tour[hidden]{display:none}
#tour .tt{font-weight:700;font-size:14px;margin-bottom:4px}
#tour .tx{line-height:1.45}
#tour .tb{display:flex;gap:6px;align-items:center;margin-top:10px}
#tour .tn{color:#666;font-size:12px;margin-right:auto}
#tour .skip{border:0;background:none;color:#555;text-decoration:underline;cursor:pointer;padding:0 4px}
.tour-on{outline:3px solid #dc2626;outline-offset:3px;border-radius:4px}
#nav{position:absolute;right:10px;bottom:10px;z-index:6;padding:4px;cursor:crosshair;touch-action:none;user-select:none}
#nav[hidden]{display:none}
#nav svg{display:block;width:auto;height:auto}
#nav .vr{fill:rgba(220,38,38,.08);stroke:#dc2626;stroke-width:2;vector-effect:non-scaling-stroke}
#nav.focus rect.n{opacity:.2}
#nav.focus rect.n.on{opacity:1}
#rulers{position:absolute;inset:0;pointer-events:none;z-index:4;overflow:hidden}
#rulers[hidden]{display:none}
#steps{position:absolute;left:0;height:24px;overflow:hidden;background:rgba(250,250,250,.88);border-bottom:1px solid #ccc}
#spreadctl[hidden]{display:none}
#spreadctl{position:absolute;z-index:5;display:flex;align-items:center;gap:4px;height:22px;padding:0 6px;font-size:11px;font-weight:600;color:#475569;background:rgba(250,250,250,.95);border:1px solid #ccc;border-radius:4px;pointer-events:auto}
#spreadctl input{width:90px;margin:0}
#spreadn{min-width:44px}
#steps span{position:absolute;top:4px;transform:translateX(-50%);white-space:nowrap;font-size:12px;font-weight:600;color:#475569;pointer-events:auto;cursor:help}
#lanetags span{position:absolute;box-sizing:border-box;height:22px;line-height:18px;padding:1px 7px;font-size:12px;font-weight:800;background:rgba(255,255,255,.9);border:1px solid;border-radius:4px;white-space:nowrap;pointer-events:none}
#wrap.onlane{cursor:zoom-in}
#lens{position:fixed;width:320px;height:320px;border-radius:50%;overflow:hidden;z-index:9;pointer-events:none;background:#fafafa;
 border:3px solid #334155;box-shadow:0 4px 16px rgba(0,0,0,.3)}
#lens[hidden]{display:none}
#info{position:absolute;top:10px;right:10px;bottom:10px;width:360px;z-index:5;padding:12px 14px;overflow:auto;display:none}
#info h2{font-size:16px;margin:0 0 4px}
#info code{font-size:12px;word-break:break-all}
#info ul{padding-left:18px;margin:4px 0 10px}
#info a{cursor:pointer;color:#1d4ed8}
#info .off{color:#888;font-size:11px}
#info .close{float:right;cursor:pointer;border:0;background:none;font-size:18px}
.edge{fill:none;stroke:#64748b;stroke-width:1.3;stroke-opacity:.55}
.edge.back{stroke-dasharray:6 4}
.elabel{pointer-events:none;font-size:10px;fill:#334155;paint-order:stroke;stroke:#fff;stroke-width:3px}
.node .box{stroke-width:calc(1.2 * var(--bsc))}
.node .t{font-size:13px;font-weight:700}
.node .p{font:10.5px ui-monospace,Menlo,monospace;fill:#334155}
.node .d{font-size:11px;fill:#1f2937}
.node{cursor:pointer}
.node.parked .box{stroke-dasharray:6 3}
.node.retired .box{stroke-dasharray:2 3}
.node.parked,.node.retired{opacity:.7}
.node.hit .box{stroke:#dc2626;stroke-width:calc(4 * var(--bsc))}
svg.focus .node,svg.focus .edge,svg.focus .elabel{opacity:.12}
svg.focus .node.on{opacity:.5}
svg.focus .node.near,svg.focus .node.sn,svg.focus .elabel.near{opacity:1}
svg.focus .elabel.on:not(.near){opacity:0}
svg.focus .edge.on{opacity:.45;stroke-opacity:1;stroke-width:1.6;stroke:#1d4ed8}
svg.focus .edge.near{opacity:1;stroke-width:3}
svg.focus .edge.on.upstream{stroke:#b45309}
svg.focus .node.sel .box{stroke:#dc2626;stroke-width:calc(4 * var(--bsc))}
svg.far #elabels{display:none}
svg.far .edge,svg.far .node .box{vector-effect:non-scaling-stroke;stroke-width:1px}
svg.far .edge{stroke-width:.8px;stroke-opacity:.35}
svg.far.focus .edge.on{stroke-width:1.5px}
svg.far.focus .edge.near{stroke-width:2.5px}
svg.far .node.hit .box,svg.far.focus .node.sel .box{stroke-width:3px}
svg.hovering .edge{stroke-opacity:.25}
.eh{fill:none;stroke:transparent;stroke-width:8px;pointer-events:stroke;vector-effect:non-scaling-stroke}
svg.far .eh{stroke-width:6px}
#etip{position:fixed;z-index:9;pointer-events:none;padding:5px 8px;font-size:12px;max-width:360px}
#etip[hidden]{display:none}
#etip .off{color:#888;font-size:11px}
svg.hovering .edge.he.he{stroke:#7c3aed;stroke-opacity:1;opacity:1;stroke-width:2.5px}
svg.hovering .node.hn .box{stroke:#7c3aed;stroke-width:calc(2.5px * var(--bsc))}
svg.hovering .edge.he.he.he2{stroke-opacity:.7}
svg.hovering .edge.he.he.he3{stroke-opacity:.45;stroke-width:1.75px}
svg.hovering .node.hn.hn2 .box{stroke-opacity:.6}
svg.hovering .node.hn.hn3 .box{stroke-opacity:.35;stroke-width:calc(1.75px * var(--bsc))}
.node.mag .box{filter:drop-shadow(0 2px 4px rgba(0,0,0,.35))}
.node.mag{pointer-events:none}
svg.focus.hovering .node.hn{opacity:1}
.hidden{display:none}
.band{fill-opacity:.07}
.band.alt{fill-opacity:.17}
.lanerule{stroke-opacity:.85;stroke-width:1.5px;vector-effect:non-scaling-stroke}
body.clean #rulers,body.clean #legend,body.clean #nav{display:none!important}
html.dark{color-scheme:dark}
html.dark,html.dark body{background:#0f172a;color:#e2e8f0}
html.dark .panel{background:#1e293b;border-color:#334155;color:#e2e8f0;box-shadow:0 2px 10px rgba(0,0,0,.5)}
html.dark #bar input,html.dark #bar button,html.dark #bar summary,html.dark .panel button{background:#0f172a;color:#e2e8f0;border-color:#475569}
html.dark #tour .skip,html.dark #info .close{background:none;border:0}
html.dark #hits,html.dark #view,html.dark #strip2,html.dark #legend div[style]{color:#cbd5e1!important}
html.dark #strip2{border-top-color:#334155}
html.dark #back,html.dark #lanelist a,html.dark #info a,html.dark #tree a{color:#93c5fd}
html.dark #info .off,html.dark #tree .c,html.dark #lanelist .note,html.dark #viewlist>b,html.dark #tour .tn,html.dark #etip .off{color:#94a3b8}
html.dark #steps{background:rgba(15,23,42,.9);border-bottom-color:#334155}
html.dark #steps span{color:#cbd5e1}
html.dark #spreadctl{background:rgba(15,23,42,.95);border-color:#334155;color:#cbd5e1}
html.dark #lanetags span{background:rgba(15,23,42,.92)}
html.dark .band{fill-opacity:.13}
html.dark .band.alt{fill-opacity:.27}
html.dark .edge{stroke:#94a3b8}
html.dark svg.far .edge{stroke-opacity:.45}
html.dark .elabel{fill:#e2e8f0;stroke:#0f172a}
html.dark svg.focus .edge.on{stroke:#60a5fa}
html.dark svg.focus .edge.on.upstream{stroke:#f59e0b}
html.dark svg.hovering .edge.he.he{stroke:#c4b5fd}
html.dark svg.hovering .node.hn .box{stroke:#c4b5fd}
html.dark #lens{background:#0f172a;border-color:#94a3b8}
html.dark #nav .vr{fill:rgba(248,113,113,.12);stroke:#f87171}
@media (max-width:900px){#bar{right:10px;max-width:none}
 #bar h1{font-size:12px}
 #row1 .lbl{display:none}
 #bar input[type=search]{width:90px} #bar #file{width:auto;flex:1 1 90px;min-width:70px;max-width:170px}
 #more{display:block}
 #morebody{position:absolute;left:0;right:0;top:36px;z-index:6;padding:8px 10px;max-height:60vh;overflow:auto;box-sizing:border-box;
  display:flex;flex-direction:column;align-items:flex-start;gap:8px;max-width:calc(100vw - 20px)}
 #morebody .menu{position:static;width:100%}
 #morebody .pop{position:static;max-height:none;box-shadow:none;border:0;padding:4px 6px;white-space:normal;max-width:none}
 #morebody #btns{flex-wrap:wrap;white-space:normal}
 #info{left:10px;width:auto;top:auto;height:45vh;z-index:7}
 #nav svg{max-width:150px;height:auto} #legend{max-width:calc(100% - 200px)}}
__SITECSS__</style>
<script>/* dark before the first paint: the saved choice, else the system setting (app() keeps it in step after) */
try { const d = localStorage.getItem("pipelineMapDark"); if (d === "1" || (d === null && matchMedia("(prefers-color-scheme: dark)").matches)) document.documentElement.classList.add("dark"); } catch (e) {}</script>
</head><body>__SITEHEADER__
<div id="stage">
<div id="wrap"></div>
<div id="rulers" hidden><div id="steps"></div><div id="lanetags"></div></div>
<label id="spreadctl" hidden title="How many steps show across the screen (drag, or turn the wheel over it); the boxes grow as fewer show, the lanes keep their full height and you pan sideways for the rest. All of them is the whole map">Steps <input type="range" id="spread" min="3" max="50" step="1" value="50"> <span id="spreadn"></span></label>
<div id="bar" class="panel"><div id="row1">__BACK__<h1>HART pipeline map</h1>
<label title="Type a file's name to draw its whole chain"><span class="lbl">File </span><input list="files" id="file" placeholder="Pick a file to see its chain…" autocomplete="off"></label>
<datalist id="files"></datalist>
<details id="browse" class="menu"><summary title="Pick a file from a folder tree">Browse ▾</summary><div id="tree" class="pop panel"></div></details>
<label><span class="lbl">Find </span><input type="search" id="q" placeholder="Find text in boxes…" title="Highlight the boxes whose name, path or description holds this text"></label>
<span id="hits"></span>
<details id="startmenu" class="menu"><summary title="Open a common chain">Start ▾</summary><div id="presets" class="pop panel"></div></details>
<details id="viewmenu" class="menu"><summary title="How boxes, links and hover are drawn">View ▾</summary><div id="viewlist" class="pop panel">
<b>Boxes and links</b>
<label title="Draw each box as its name only; click it for the path and description"><input type="checkbox" id="compact" checked> Compact boxes</label>
<label title="Draw the whole map as one box per folder; double-click a folder to open it"><input type="checkbox" id="group"> Group by folder</label>
<label title="Write what each link carries on the line"><input type="checkbox" id="labels" checked> Edge labels</label>
<label title="Leave out the boxes and links a clicked box does not light up, and redraw the rest close together"><input type="checkbox" id="trim"> Highlighted chain only</label>
<b>Pointer</b>
<label title="Hovering a box or line lights its chain and grows its boxes when zoomed out; untick for a still map"><input type="checkbox" id="hover" checked> Hover highlights</label>
<label title="A clicked box lights its near pipeline, stopping at hubs and runners as a hover does, not everything it reaches; works with hover on or off"><input type="checkbox" id="near"> Near pipeline on click</label>
<b>Page</b>
<label title="Dark background; starts from the system setting and is remembered on this browser"><input type="checkbox" id="dark"> Dark background</label>
<label title="Hide the lane names, step headers, legend and overview, for a clear view of the map (H)"><input type="checkbox" id="clean"> Clean view (H)</label>
</div></details>
<details id="lanes" class="menu"><summary title="Choose lanes, kinds, parked and retired">Filters ▾</summary><div id="lanelist" class="pop panel">
<b>Lanes</b><div id="lanerows"></div>
<b>Kinds</b> <span class="note">Unticking a kind joins its links straight through (hosts, hand work and caches are left out with their links).</span><div id="kindlist"></div>
<b>Include</b>
<label class="inl" title="Parked features (NX, Dispatcher System, USS CTC)"><input type="checkbox" id="parked"> Parked features</label>
<label class="inl" title="Retired tools kept for reference"><input type="checkbox" id="retired"> Retired tools</label>
<div class="foot" hidden><a id="clearf2" title="Every lane and kind, parked and retired hidden; also puts View's boxes and links options back (compact on, no folders, edge labels on); keeps the file and the selected box">Clear filters</a></div>
</div></details>
<span id="btns"><button id="showall" hidden title="Back to the full map: all lanes and kinds, no folders. Parked and retired follow their ticks.">Whole map</button>
<button id="fit" title="Show the whole map (F)">Fit</button><button id="zout" title="Zoom out (scroll or pinch)" aria-label="Zoom out">−</button><button id="zin" title="Zoom in (scroll or pinch)" aria-label="Zoom in">+</button>
<span class="gap"></span>
<button id="share" title="Copy a link to this view: the file, filters, selected box, zoom and position">Share</button>
<button id="tourbtn" title="Run the tour of the controls again" aria-label="Tour">?</button></span>
<details id="more" class="menu"><summary title="The rest of the controls">More ▾</summary><div id="morebody" class="panel"></div></details>
</div>
<div id="strip2" hidden><span id="view"></span>
<span id="depth" hidden title="How many links to show either side of the file"><span class="sep">│</span>
 <span class="side">← Upstream: what feeds it <button data-side="up" data-step="-1" title="One step fewer upstream">−</button> <b id="upn">all</b>
 <button data-side="up" data-step="1" title="One step more upstream">+</button> <button data-side="up" data-step="all" title="Every step upstream">all</button></span>
 <span class="side">Downstream: what it feeds → <button data-side="down" data-step="-1" title="One step fewer downstream">−</button> <b id="downn">all</b>
 <button data-side="down" data-step="1" title="One step more downstream">+</button> <button data-side="down" data-step="all" title="Every step downstream">all</button></span></span>
<button id="clearf" hidden title="Every lane and kind, parked and retired hidden, compact on, no folders; keeps the file and the selected box">Clear filters</button></div>
</div>
<div id="tour" class="panel" hidden role="dialog" aria-label="Tour of the controls"><div class="tt"></div><div class="tx"></div>
<div class="tb"><span class="tn"></span><button class="skip">Skip tour</button><button class="back">Back</button><button class="next">Next</button></div></div>
<div id="nav" class="panel" hidden title="Overview of the whole drawing: click or drag to move the view"></div>
<details id="legend" class="panel"><summary><b>Legend and help</b></summary><b>Kind</b> (box colour)__LEGEND__
<div style="margin-top:6px"><b>Lane stripe</b> = domain. Dashed box = parked, dotted = retired, dashed line = feeds back
to an earlier step.</div>
<div><b>One file:</b> type or pick it in the File box, or find it under <b>Browse ▾</b> by folder (or double-click its box), to draw its
whole chain: everything that feeds it, back to the sources, and everything it feeds, out to the end products. A second row
under the toolbar names the file and holds the step counters for upstream and downstream (0 hides that side, all runs to the
end). <b>Start ▾</b> opens common chains. <b>Find</b> highlights the boxes that hold a piece of text.</div>
<div><b>View ▾</b>, boxes and links: <b>Compact boxes</b> (on to start with: names only; untick for each box's path and description),
<b>Group by folder</b> (one dashed box per folder; double-click a folder, or use Open in its panel, to see its files),
<b>Edge labels</b> and <b>Highlighted chain only</b> (leave out everything a clicked box does not light). Pointer:
<b>Hover highlights</b> and <b>Near pipeline on click</b>. Page: <b>Dark background</b> and <b>Clean view</b> (or H: hides the lane
names, step headers, this legend and the overview).</div>
<div><b>Filters ▾</b> picks the lanes and kinds of box to draw, and whether parked features and retired tools show. Untick a kind,
such as scripts, and its boxes are left out with their links joined up; <b>only</b> beside a lane or kind shows just that one (a second click shows them all again). <b>Clear filters</b>, at the foot of Filters or in the
second row, puts them back and keeps the file and the selected box. <b>Whole map</b> appears when the view is cut down.
<b>Share</b> copies a link to the view as it is, with the selected box, zoom and position. A first visit gets a short tour;
<b>?</b> runs it again. On a phone, Browse, Start, View, Filters and the buttons are under <b>More ▾</b>; Fit stays out.</div>
<div><b>Move:</b> scroll or pinch to zoom, drag to pan, F fits, Esc clears. <b>Steps</b>, at the right of the step headers, sets how many steps show across the screen: the lanes keep their full height and you pan sideways for the rest, the boxes growing with the steps, text and all, as far as the lanes have room (up to 2.5 times), and the gap taking the rest; the drawing follows the slider as you drag it (or turn the wheel over it) and is laid out properly when you let go; Fit then shows the first of them from the left, and all of them is the whole map. Click a lane's name on the left to zoom to that lane,
and again to go back (a box under the name takes the click first). Hold Shift for a magnifier. Zoomed in, the overview in the
corner shows the whole drawing with a red box round what is in view; click or drag in it to move.</div>
<div><b>Hover:</b> zoomed out, hover a line to light its chain, what feeds it and what it feeds, and grow its boxes to a readable
size; hover a box to do the same for its neighbours. A hovered chain stops at hubs where many pipelines meet (such as
tables.xml), runners such as check.sh, caches, hosts and hand work, and does not cross side links that carry nothing on (what a
check reads, a doc pointer, a Store pull back into the sources). Boxes more than two steps from the line are outlined fainter.
The note by the pointer names where the chain stopped.</div>
<div><b>Click:</b> a box lights what feeds it (amber) and what it feeds (blue), its full reach; with Near pipeline on click it stops
where a hover does. A line opens the box it leads to; Cmd-click (Ctrl-click off a Mac) opens the box it comes from. A click on
empty map, or Esc, clears the selection. A click-chain stops at deploy, host, hand-work and cache boxes: they show, but the chain
does not run on through them.</div>
<div style="color:#666">Built __DATE__ from docs/pipeline-map/pipeline_map.json · __COUNTS__</div></details>
<div id="info" class="panel"></div>
</div>
<script>const DATA = __DATA__;</script>
<script>
__SCRIPT__
</script>__SITESCRIPT__</body></html>
"""


# Website copy only: the site stylesheet and header, the map filling the space under the header, panels in site tokens.
SITE_HEAD = '\n<link rel="stylesheet" href="../css/ops.css">'
SITE_HEADER = '\n<header class="site-header" data-ops-header></header>'
SITE_SCRIPT = ('<script src="../js/nav.js"></script>'
               '<script>HARTOps.mountChrome("behind-pipeline-map").catch(function (e) { console.error(e); });</script>')
SITE_CSS = """
/* site look: the page is a column of site header and map; the panels float over the map in site tokens */
html,body{height:100%;overflow:hidden}
body{display:flex;flex-direction:column;font:14px/1.4 var(--font-body);background:var(--paper)}
#stage{position:relative;inset:auto;flex:1;min-height:0;background:var(--paper-2)}
.panel{background:var(--card);border:1px solid var(--rule);border-radius:6px;box-shadow:var(--shadow);color:var(--ink)}
#bar h1{font:700 1.35rem/1 var(--font-display);letter-spacing:.04em;color:var(--brand);margin:0 8px 0 0}
#bar input,#bar button,#bar summary{font:inherit;color:var(--ink);background:#fff;border:1px solid var(--rule);border-radius:4px}
#bar button{cursor:pointer}
#bar button:hover,.menu>summary:hover{border-color:var(--brand-2)}
#strip2{border-top-color:var(--rule);color:var(--ink-soft)}
#back,#lanelist a,#info a,#tree a{color:var(--brand-2)}
#view{color:var(--ink-soft)}
#info h2{font:700 1.3rem/1.1 var(--font-display);letter-spacing:.03em;color:var(--brand)}
#info .off{color:var(--muted)}
#legend summary{cursor:pointer}
#legend b,#info b{color:var(--ink)}
#nav .vr{fill:rgba(179,58,58,.08);stroke:var(--signal)}
#steps{background:color-mix(in srgb,var(--paper-2) 90%,transparent);border-bottom-color:var(--rule)}
#steps span{color:var(--ink-soft);font-family:var(--font-body)}
#lanetags span{background:var(--card);font-family:var(--font-body)}
svg.focus .edge.on{stroke:var(--brand-2)}
svg.focus .node.sel .box,.node.hit .box{stroke:var(--signal)}
.node .t,.node .d{font-family:var(--font-body)}
html.dark #stage{--paper:#0f172a;--paper-2:#0b1220;--card:#1e293b;--ink:#e2e8f0;--ink-soft:#cbd5e1;--rule:#334155;--muted:#94a3b8;
 --brand:#93c5fd;--brand-2:#93c5fd}
"""


def public_copy(data: dict) -> dict:
    """The graph with every mirror path in PUBLIC_NAMES renamed, in ids, paths, labels, descriptions and links."""
    def fix(value):
        if isinstance(value, str):
            for real, shown in PUBLIC_NAMES.items():
                value = value.replace(real, shown)
            return value
        if isinstance(value, list):
            return [fix(v) for v in value]
        if isinstance(value, dict):
            return {k: fix(v) for k, v in value.items()}
        return value

    return fix(data)


def check_public_page(page: str) -> None:
    """Fail on text in the finished public page that the website build would reject: its leak patterns and the
    private name (www/scripts/prepare_github_pages.py), over the graph, the template and the inlined script."""
    spec = importlib.util.spec_from_file_location("prepare_github_pages", ROOT / "www/scripts/prepare_github_pages.py")
    site = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(site)
    leaks = sorted({m.group() for m in site.LEAK_PATTERNS.finditer(page)})
    if leaks:
        raise GraphError(f"the public page holds text the website's leak check rejects: {', '.join(leaks)}")
    if site.contains_private_name(page):
        raise GraphError("the public page holds the private name")


REPO_URL = "https://github.com/lnevo/hart"


def code_links() -> dict:
    """Where the sidebar's GitHub link points: this repository's main branch, and each submodule's own repository at its
    default branch (GitHub has no page for a submodule path inside this repository)."""
    links = {"": REPO_URL + "/blob/main/"}
    gm = ROOT / ".gitmodules"
    text = gm.read_text() if gm.exists() else ""
    for path, url in re.findall(r"^\s*path = (\S+)\s*\n\s*url = (\S+)", text, re.M):
        m = re.match(r"(?:git@github\.com:|https://github\.com/)([^/]+/[^/]+?)(?:\.git)?$", url)
        if m:
            links[path] = f"https://github.com/{m.group(1)}/blob/HEAD/"
    return links


def render(data: dict, back: str = "", site: bool = False) -> str:
    legend = "".join(
        f'<div><span class="sw" style="background:{fill};border-color:{ink}"></span>{esc(label)}</div>'
        for label, fill, ink in KINDS.values()
    )
    page_data = {
        "nodes": [
            {k: n[k] for k in ("id", "label", "kind", "status", "domain", "desc", "path", "local", "runner") if k in n}
            for n in data["nodes"]
        ],
        "edges": [{k: e[k] for k in ("from", "to", "label", "side") if k in e} for e in data["edges"]],
        "kinds": {k: list(v) for k, v in KINDS.items()},
        "presets": data.get("presets", []),
        "domains": [{"id": d["id"], "label": d["label"], "color": d["color"]} for d in data["domains"]],
        "domainColor": {d["id"]: d["color"] for d in data["domains"]},
        "codeLinks": code_links(),
    }
    counts = f'{len(data["nodes"])} boxes, {len(data["edges"])} links'
    back_link = f'<a id="back" href="{esc(back)}" title="Back to Inside the repository">←</a>' if back else ""
    return (
        PAGE_TEMPLATE.replace("__SITEHEAD__", SITE_HEAD if site else "")
        .replace("__SITECSS__", SITE_CSS if site else "")
        .replace("__SITEHEADER__", SITE_HEADER if site else "")
        .replace("__SITESCRIPT__", SITE_SCRIPT if site else "")
        .replace("__BACK__", back_link)
        .replace("__LEGEND__", legend)
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
    ap.add_argument("--public", action="store_true", help="write the website copy (mirror paths renamed); needs --out")
    ap.add_argument("--back", default="", help="link at the top left of the page, back to the page that links to it")
    args = ap.parse_args(argv)
    if args.public and args.out.resolve() == PAGE.resolve():
        ap.error("--public writes the website copy; give it --out")
    again = shlex.join(a for a in (argv if argv is not None else sys.argv[1:]) if a != "--check")
    try:
        raw = read(args.graph)
        data = validate(regenerate(raw))
    except GraphError as err:
        print(f"{args.graph}: the graph has problems:\n{err}", file=sys.stderr)
        return 1
    fresh = graph_text(data)
    plain = "python3 tools/ops/build_pipeline_map.py" + (
        f" --graph {shlex.quote(str(args.graph))}" if args.graph.resolve() != GRAPH.resolve() else "")
    if args.graph.read_text() != fresh:
        # Only the plain build writes the graph, so a website build or a --check never changes a tracked source.
        if args.check or args.public:
            print(f"{args.graph} is out of date (its agent-doc lane is generated from the files): run {plain} "
                  f"(it rewrites the graph and the docs page), then {SITE_BUILD}", file=sys.stderr)
            return 1
        args.graph.write_text(fresh)
        print(f"updated {args.graph.name}: the agent-doc lane, from the files; rebuild the website copy too: "
              f"{SITE_BUILD}")
    page = render(public_copy(data) if args.public else data, args.back, args.public)
    if args.public:
        try:
            check_public_page(page)
        except GraphError as err:
            print(f"{args.out}: the public page fails the website's checks (graph, template or {SCRIPT.name}):\n{err}",
                  file=sys.stderr)
            return 1
    if args.check:
        if not args.out.exists() or args.out.read_text() != page:
            print(f"{args.out} is out of date: run python3 tools/ops/build_pipeline_map.py {again}".rstrip(), file=sys.stderr)
            return 1
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(page)
    shown = args.out.resolve().relative_to(ROOT) if args.out.resolve().is_relative_to(ROOT) else args.out
    print(f"wrote {shown}: {len(data['nodes'])} nodes, {len(data['edges'])} edges")
    return 0


if __name__ == "__main__":
    sys.exit(main())
