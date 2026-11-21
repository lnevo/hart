#!/usr/bin/env python3
"""build_pipeline_map.py

Write docs/pipeline-map/index.html, a zoomable map of every source, generator and output in the repo, from the graph
in docs/pipeline-map/pipeline_map.json.

    python3 tools/ops/build_pipeline_map.py            write the page
    python3 tools/ops/build_pipeline_map.py --check    exit 1 when the graph is broken or the page is out of date
    python3 tools/ops/build_pipeline_map.py --public --out www/... [--back HREF]   the website copy (with --check too)

The website copy renames the gitignored mirrors (PUBLIC_NAMES), whose real paths the site build treats as leaks, and
can carry a link back to the page that links to it.

The graph file holds domains (the horizontal lanes), nodes and edges. A node's `path` must exist in the checkout
unless the node says `"local": true` (a gitignored mirror or a file made on a host). This script checks the graph and
writes one self-contained page; the layout and the viewer are in tools/ops/pipeline_map.js, inlined into the page, so
the page can redraw any subset (some lanes, or the chain around one file) without build tools.
"""
from __future__ import annotations

import argparse
import functools
import html
import importlib.util
import json
import shlex
import subprocess
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
# Gitignored mirrors whose paths the website's leak check rejects; the public page names them like this instead.
PUBLIC_NAMES = {
    "external/sts-docker-data": "sts-docker-data (mirror)",
    "ops/car-cards": "car-cards workspace",
    "media/hart-research": "media mirror: hart-research",
}


class GraphError(Exception):
    pass


@functools.cache
def tracked_paths() -> frozenset[str]:
    """Every git-tracked file in the repo and every folder that holds one, so the check is the same on any clone."""
    out = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT, text=True)
    paths = set()
    for f in filter(None, out.split("\0")):
        parts = f.split("/")
        paths.update("/".join(parts[:k]) for k in range(1, len(parts) + 1))
    return frozenset(paths)


def load(path: Path) -> dict:
    data = json.loads(path.read_text())
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
        if p and not n.get("local") and p.rstrip("/") not in tracked_paths():
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
        key = (e["from"], e["to"])
        if key in seen_edges:
            problems.append(f"edge {e['from']} -> {e['to']} is listed twice")
        seen_edges.add(key)
        if e["from"] == e["to"]:
            problems.append(f"edge {e['from']} points at itself")
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
#startcard{position:absolute;inset:0;z-index:4;display:flex;align-items:center;justify-content:center;pointer-events:none}
#startcard[hidden]{display:none}
#startcard .card{pointer-events:auto;position:relative;padding:14px 18px 16px;max-width:min(560px,calc(100vw - 40px));text-align:center;opacity:.96}
#startcard .t{font-size:15px;font-weight:700;margin-bottom:8px}
#startcard .btns{display:flex;gap:8px;flex-wrap:wrap;justify-content:center}
#startcard button[data-preset]{font-size:14px;padding:7px 14px;cursor:pointer}
#startcard .x{position:absolute;top:2px;right:6px;border:0;background:none;font-size:18px;cursor:pointer;color:#555}
.node.folder .box{stroke-dasharray:7 4;stroke-width:2}
span.sw{display:inline-block;width:14px;height:11px;border:1px solid transparent;border-radius:3px;vertical-align:-1px;margin-right:4px}
#legend{position:absolute;bottom:10px;left:10px;max-width:440px;z-index:5;padding:8px 10px;font-size:12px}
#legend div{margin:2px 0}
#nav{position:absolute;right:10px;bottom:10px;z-index:6;padding:4px;cursor:crosshair;touch-action:none;user-select:none}
#nav[hidden]{display:none}
#nav svg{display:block;width:auto;height:auto}
#nav .vr{fill:rgba(220,38,38,.08);stroke:#dc2626;stroke-width:2;vector-effect:non-scaling-stroke}
#nav.focus rect.n{opacity:.2}
#nav.focus rect.n.on{opacity:1}
#info{position:absolute;top:10px;right:10px;bottom:10px;width:360px;z-index:5;padding:12px 14px;overflow:auto;display:none}
#info h2{font-size:16px;margin:0 0 4px}
#info code{font-size:12px;word-break:break-all}
#info ul{padding-left:18px;margin:4px 0 10px}
#info a{cursor:pointer;color:#1d4ed8}
#info .off{color:#888;font-size:11px}
#info .close{float:right;cursor:pointer;border:0;background:none;font-size:18px}
.band{font-weight:800;opacity:.45}
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
 #nav svg{max-width:150px;height:auto} #legend{max-width:calc(100% - 200px)}
 #startcard{align-items:flex-start;padding-top:140px}}
__SITECSS__</style></head><body>__SITEHEADER__
<div id="stage">
<div id="wrap"></div>
<div id="bar" class="panel"><div id="row1">__BACK__<h1>HART pipeline map</h1>
<label><span class="lbl">File </span><input list="files" id="file" placeholder="Pick a file to see its chain…" autocomplete="off"></label>
<datalist id="files"></datalist>
<details id="browse" class="menu"><summary title="Pick a file from a folder tree">Browse ▾</summary><div id="tree" class="pop panel"></div></details>
<label><span class="lbl">Find </span><input type="search" id="q" placeholder="text in a box…" title="Highlight the boxes that hold this text"></label>
<span id="hits"></span>
<details id="startmenu" class="menu"><summary title="Open a chain people ask about most">Start ▾</summary><div id="presets" class="pop panel"></div></details>
<details id="viewmenu" class="menu"><summary>View ▾</summary><div id="viewlist" class="pop panel">
<label title="Draw each box as its name only; click it for the path and description"><input type="checkbox" id="compact" checked> compact</label>
<label title="Draw the whole map as one box per folder; double-click a folder to open it"><input type="checkbox" id="group"> folders</label>
<label title="Leave out the boxes and links a clicked box does not light up, and redraw the rest close together"><input type="checkbox" id="trim"> highlighted only</label>
<label title="Show edge labels"><input type="checkbox" id="labels" checked> edge labels</label>
</div></details>
<details id="lanes" class="menu"><summary>Filters ▾</summary><div id="lanelist" class="pop panel">
<b>Lanes</b><div id="lanerows"></div>
<b>Kinds</b> <span class="note">an unticked kind is bridged over: its links run straight through, except at deploy and host boxes, where chains stop</span><div id="kindlist"></div>
<b>Also show</b>
<label class="inl" title="Parked features (NX, Dispatcher System, USS CTC)"><input type="checkbox" id="parked"> parked</label>
<label class="inl" title="Retired tools kept for reference"><input type="checkbox" id="retired"> retired</label>
</div></details>
<span id="btns"><button id="showall" hidden title="Back to the whole map, every lane and kind, no folders; parked and retired boxes follow their ticks">Whole map</button>
<button id="fit" title="Show everything (F)">Fit</button><button id="zin" title="Zoom in">+</button><button id="zout" title="Zoom out">−</button>
<button id="share" title="Copy a link to this view: the file, filters, selected box, zoom and position">Share</button></span>
<details id="more" class="menu"><summary>Menu ▾</summary><div id="morebody" class="panel"></div></details>
</div>
<div id="strip2" hidden><span id="view"></span>
<span id="depth" hidden title="How many links to show either side of the file"><span class="sep">│</span>
 <span class="side">← feeds it <button data-side="up" data-step="-1">−</button> <b id="upn">all</b>
 <button data-side="up" data-step="1">+</button> <button data-side="up" data-step="all">all</button></span>
 <span class="side">it feeds → <button data-side="down" data-step="-1">−</button> <b id="downn">all</b>
 <button data-side="down" data-step="1">+</button> <button data-side="down" data-step="all">all</button></span></span>
<button id="clearf" hidden title="Every lane and kind, parked and retired hidden, compact on, no folders; keeps the file and the selected box">Clear filters</button></div>
</div>
<div id="startcard" hidden><div class="card panel"><button class="x" title="Hide these buttons">×</button>
<div class="t">Start with a chain</div><div class="btns" id="startbtns"></div>
<div style="color:#666;margin-top:8px;font-size:12px">or pick a file in the File box, or click a box</div></div></div>
<div id="nav" class="panel" hidden title="Overview of the whole drawing: click or drag to move the view"></div>
<details id="legend" class="panel"><summary><b>Legend and help</b></summary><b>Kind</b> (box colour)__LEGEND__
<div style="margin-top:6px"><b>Lane stripe</b> = domain. Dashed box = parked, dotted = retired, dashed line = feeds back
to an earlier step.</div>
<div>Scroll or pinch to zoom, drag to pan, F fits, Esc clears. When zoomed in, the overview in the corner shows the whole drawing with a red box round what is in view; click or drag in it to move. Click a box for what feeds it (amber) and what it feeds
(blue). Tick <b>highlighted only</b> to leave out everything else and draw that chain on its own.</div>
<div><b>One file:</b> type or pick it in the File box, find it under <b>Browse ▾</b> by folder (or double-click its box) to draw its whole chain: everything
that feeds it, back to the sources, and everything it feeds, out to the end products. Boxes off that chain are left
out. A chain stops at deploy, host and hand-work boxes: they show, but the chain does not run on through them. A second row under the toolbar
names the file and holds the step counters: left is what feeds it, right is what it feeds (0 hides that side, all runs to the end).
<b>Start ▾</b> opens the chains people ask about most; the same buttons sit over the map until you pick a file or a box.
<b>Find</b> highlights the boxes that hold a piece of text.</div>
<div><b>View ▾</b> holds <b>compact</b> (on to start with: boxes as names only; untick it for each box's path and description),
<b>folders</b> (the whole map as one dashed box per folder; double-click a folder, or use Open in its panel, to see its files),
<b>highlighted only</b> and <b>edge labels</b>. <b>Filters ▾</b> picks the lanes and the kinds of box to draw, and whether parked and retired boxes show. Untick a
kind, such as scripts, and its boxes are left out with their links joined up, so data runs straight to what it ends
up in. When a filter is changed, <b>Clear filters</b> in the second row puts them back and keeps the file and the selected box.
<b>Whole map</b> appears when the view is cut down and goes back to the full drawing. <b>Share</b> copies a link to the view as it is,
with the selected box, zoom and position; the address bar also keeps the view, without the zoom. On a phone, Browse and everything after Find are under <b>Menu ▾</b>.</div>
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
#startcard .t{font:700 1.2rem/1.1 var(--font-display);letter-spacing:.03em;color:var(--brand)}
#startcard button[data-preset]{font:inherit;color:var(--ink);background:#fff;border:1px solid var(--rule);border-radius:4px}
#startcard button:hover{border-color:var(--brand-2)}
#back,#lanelist a,#info a,#tree a{color:var(--brand-2)}
#view{color:var(--ink-soft)}
#info h2{font:700 1.3rem/1.1 var(--font-display);letter-spacing:.03em;color:var(--brand)}
#info .off{color:var(--muted)}
#legend summary{cursor:pointer}
#legend b,#info b{color:var(--ink)}
#nav .vr{fill:rgba(179,58,58,.08);stroke:var(--signal)}
svg.focus .edge.on{stroke:var(--brand-2)}
svg.focus .node.sel .box,.node.hit .box{stroke:var(--signal)}
.node .t,.node .d{font-family:var(--font-body)}
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


def render(data: dict, back: str = "", site: bool = False) -> str:
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
        "presets": data.get("presets", []),
        "domains": [{"id": d["id"], "label": d["label"], "color": d["color"]} for d in data["domains"]],
        "domainColor": {d["id"]: d["color"] for d in data["domains"]},
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
    try:
        data = load(args.graph)
    except GraphError as err:
        print(f"{args.graph}: the graph has problems:\n{err}", file=sys.stderr)
        return 1
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
            again = shlex.join(a for a in (argv if argv is not None else sys.argv[1:]) if a != "--check")
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
