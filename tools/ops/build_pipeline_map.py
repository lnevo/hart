#!/usr/bin/env python3
"""build_pipeline_map.py

Draw docs/pipeline-map/index.html, a zoomable map of every source, generator and output in the repo, from the graph
in docs/pipeline-map/pipeline_map.json.

    python3 tools/ops/build_pipeline_map.py            write the page
    python3 tools/ops/build_pipeline_map.py --check    exit 1 when the graph is broken or the page is out of date

The graph file holds domains (the horizontal lanes), nodes and edges. A node's `path` must exist in the checkout
unless the node says `"local": true` (a gitignored mirror or a file made on a host). The layout is a layered
(Sugiyama) drawing, left to right, worked out here with the standard library so the page needs no build tools.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import textwrap
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "docs" / "pipeline-map" / "pipeline_map.json"
PAGE = ROOT / "docs" / "pipeline-map" / "index.html"

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

NODE_W = 250
COL_GAP = 150
V_GAP = 14
BAND_PAD = 40
DUMMY_H = 6
WRAP = 44  # characters per description line at the description font size
TITLE_WRAP = 30  # characters per title line (bold, larger)


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


# ---------------------------------------------------------------- layout


def wrap_desc(text: str) -> list[str]:
    return textwrap.wrap(text, WRAP) if text else []


def title_lines(n: dict) -> list[str]:
    status = n.get("status", "live")
    return textwrap.wrap(n["label"] + ("" if status == "live" else f"  [{status}]"), TITLE_WRAP) or [""]


def node_height(n: dict) -> int:
    h = 8 + 16 * len(title_lines(n))  # title
    if n.get("path"):
        h += 15
    h += 13 * len(wrap_desc(n.get("desc", "")))
    return h + 10


def acyclic(nodes: list[str], edges: list[tuple[str, str]]) -> list[tuple[str, str, bool]]:
    """The edges with the ones that close a cycle turned round (flag True), found by depth-first search."""
    out_adj = defaultdict(list)
    for a, b in edges:
        out_adj[a].append(b)
    state: dict[str, int] = {}
    back: set[tuple[str, str]] = set()
    for start in nodes:
        if start in state:
            continue
        stack = [(start, iter(out_adj[start]))]
        state[start] = 1
        while stack:
            v, it = stack[-1]
            for w in it:
                if state.get(w) == 1:
                    back.add((v, w))
                elif w not in state:
                    state[w] = 1
                    stack.append((w, iter(out_adj[w])))
                    break
            else:
                state[v] = 2
                stack.pop()
    return [((b, a, True) if (a, b) in back else (a, b, False)) for a, b in edges]


def layout(data: dict) -> dict:
    nodes = {n["id"]: n for n in data["nodes"]}
    order_ids = list(nodes)
    dom_rank = {d["id"]: i for i, d in enumerate(data["domains"])}
    dag = acyclic(order_ids, [(e["from"], e["to"]) for e in data["edges"]])

    preds, succs = defaultdict(list), defaultdict(list)
    for a, b, _ in dag:
        preds[b].append(a)
        succs[a].append(b)

    # longest path layering, then sources pulled right next to their first consumer
    rank: dict[str, int] = {}

    def rank_of(v: str) -> int:
        stack = [v]
        while stack:
            x = stack[-1]
            if x in rank:
                stack.pop()
                continue
            missing = [p for p in preds[x] if p not in rank]
            if missing:
                stack.extend(missing)
                continue
            rank[x] = 1 + max((rank[p] for p in preds[x]), default=-1)
            stack.pop()
        return rank[v]

    for v in order_ids:
        rank_of(v)
    for _ in range(3):
        for v in sorted(order_ids, key=lambda x: -rank[x]):
            if succs[v]:
                rank[v] = max(rank[v], min(rank[s] for s in succs[v]) - 1)

    # virtual nodes along edges longer than one layer
    vnodes: dict[str, dict] = {}
    chains = []  # (edge index, [ids along the edge])
    for i, (a, b, flipped) in enumerate(dag):
        chain = [a]
        for r in range(rank[a] + 1, rank[b]):
            vid = f"__v{i}_{r}"
            half = (r - rank[a]) <= (rank[b] - rank[a]) / 2
            vnodes[vid] = {"domain": nodes[a if half else b]["domain"]}
            rank[vid] = r
            chain.append(vid)
        chain.append(b)
        chains.append((i, chain, flipped))

    def domain(v: str) -> str:
        return nodes[v]["domain"] if v in nodes else vnodes[v]["domain"]

    def height(v: str) -> int:
        return node_height(nodes[v]) if v in nodes else DUMMY_H

    up, down = defaultdict(list), defaultdict(list)
    for _, chain, _ in chains:
        for a, b in zip(chain, chain[1:]):
            down[a].append(b)
            up[b].append(a)

    n_ranks = max(rank.values()) + 1
    layers: list[list[str]] = [[] for _ in range(n_ranks)]
    for v in list(order_ids) + list(vnodes):
        layers[rank[v]].append(v)
    for layer in layers:
        layer.sort(key=lambda v: dom_rank[domain(v)])

    pos = {}

    def reindex():
        for layer in layers:
            for i, v in enumerate(layer):
                pos[v] = i

    reindex()

    def crossings() -> int:
        total = 0
        for r in range(n_ranks - 1):
            es = [(pos[a], pos[b]) for a in layers[r] for b in down[a]]
            es.sort()
            for i in range(len(es)):
                for j in range(i + 1, len(es)):
                    if es[j][1] < es[i][1]:
                        total += 1
        return total

    best = ([list(l) for l in layers], crossings())
    for it in range(28):
        rng = range(1, n_ranks) if it % 2 == 0 else range(n_ranks - 2, -1, -1)
        for r in rng:
            nb = up if it % 2 == 0 else down
            layer = layers[r]

            def key(v, nb=nb):
                ps = [pos[u] for u in nb[v]]
                bc = sum(ps) / len(ps) if ps else pos[v]
                return (dom_rank[domain(v)], bc)

            layer.sort(key=key)
            for i, v in enumerate(layer):
                pos[v] = i
        c = crossings()
        if c < best[1]:
            best = ([list(l) for l in layers], c)
    layers = best[0]
    reindex()

    # bands: one horizontal lane per domain, as tall as its fullest column
    band_h = {}
    for d in dom_rank:
        tallest = 0
        for layer in layers:
            col = [height(v) + V_GAP for v in layer if domain(v) == d]
            tallest = max(tallest, sum(col))
        band_h[d] = tallest + 2 * BAND_PAD if tallest else 0
    band_top, y = {}, 0
    for d in sorted(dom_rank, key=dom_rank.get):
        band_top[d] = y
        y += band_h[d]
    total_h = y

    ys: dict[str, float] = {}
    for layer in layers:
        for d in dom_rank:
            col = [v for v in layer if domain(v) == d]
            used = sum(height(v) + V_GAP for v in col)
            cur = band_top[d] + BAND_PAD + (band_h[d] - 2 * BAND_PAD - used) / 2
            for v in col:
                ys[v] = cur
                cur += height(v) + V_GAP

    def centre(v):
        return ys[v] + height(v) / 2

    # straighten: move each node toward the mean of its neighbours, keeping order and the band
    for it in range(40):
        rng = range(n_ranks) if it % 2 == 0 else range(n_ranks - 1, -1, -1)
        for r in rng:
            for d in dom_rank:
                col = [v for v in layers[r] if domain(v) == d]
                if not col:
                    continue
                want = []
                for v in col:
                    nbrs = up[v] + down[v]
                    if nbrs:
                        want.append(sum(centre(u) for u in nbrs) / len(nbrs) - height(v) / 2)
                    else:
                        want.append(ys[v])
                lo, hi = band_top[d] + BAND_PAD, band_top[d] + band_h[d] - BAND_PAD
                place = list(want)
                for i in range(len(col)):  # push down to clear the one above
                    floor = lo if i == 0 else place[i - 1] + height(col[i - 1]) + V_GAP
                    place[i] = max(place[i], floor)
                for i in range(len(col) - 1, -1, -1):  # push up to clear the one below and the band floor
                    ceil = hi - height(col[i]) if i == len(col) - 1 else place[i + 1] - height(col[i]) - V_GAP
                    place[i] = min(place[i], ceil)
                for v, p in zip(col, place):
                    ys[v] = p

    xs = {v: rank[v] * (NODE_W + COL_GAP) for v in rank}
    out_nodes = []
    for v, n in nodes.items():
        out_nodes.append({**n, "x": xs[v], "y": ys[v], "w": NODE_W, "h": height(v)})
    out_edges = []
    for i, chain, flipped in chains:
        e = data["edges"][i]
        pts = []
        for j, v in enumerate(chain):
            if v in nodes:
                side = (xs[v] + NODE_W) if j == 0 else xs[v]
                pts.append((side, centre(v)))
            else:
                pts.append((xs[v], centre(v)))
                pts.append((xs[v] + NODE_W, centre(v)))
        if flipped:
            pts.reverse()
        out_edges.append({**e, "pts": pts, "back": flipped})
    width = n_ranks * (NODE_W + COL_GAP) - COL_GAP
    bands = [
        {"id": d["id"], "label": d["label"], "color": d["color"], "y": band_top[d["id"]], "h": band_h[d["id"]]}
        for d in data["domains"]
        if band_h[d["id"]]
    ]
    return {"nodes": out_nodes, "edges": out_edges, "bands": bands, "width": width, "height": total_h}


# ---------------------------------------------------------------- drawing


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def path_d(pts: list[tuple[float, float]]) -> str:
    (x0, y0), rest = pts[0], pts[1:]
    d = [f"M{x0:.1f},{y0:.1f}"]
    px, py = x0, y0
    for x, y in rest:
        if abs(y - py) < 0.5:
            d.append(f"L{x:.1f},{y:.1f}")
        else:
            mx = (px + x) / 2
            d.append(f"C{mx:.1f},{py:.1f} {mx:.1f},{y:.1f} {x:.1f},{y:.1f}")
        px, py = x, y
    return " ".join(d)


def svg(lay: dict, domains: dict) -> str:
    left = 180
    W, H = lay["width"] + left + 60, lay["height"]
    parts = [f'<svg id="map" xmlns="http://www.w3.org/2000/svg" viewBox="{-left} 0 {W} {H}" data-w="{W}" data-h="{H}">']
    parts.append(
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="context-stroke"/></marker></defs>'
    )
    parts.append('<g id="bands">')
    for b in lay["bands"]:
        parts.append(
            f'<rect x="{-left}" y="{b["y"]}" width="{W}" height="{b["h"]}" fill="{esc(b["color"])}" fill-opacity="0.10"/>'
            f'<line x1="{-left}" x2="{W - left}" y1="{b["y"]}" y2="{b["y"]}" stroke="{esc(b["color"])}" stroke-opacity="0.5"/>'
        )
        for x in range(-left + 10, int(W - left), 3000):
            parts.append(
                f'<text class="band" x="{x}" y="{b["y"] + 110}" fill="{esc(b["color"])}">{esc(b["label"])}</text>'
            )
    parts.append("</g><g id=\"edges\">")
    for i, e in enumerate(lay["edges"]):
        cls = "edge back" if e["back"] else "edge"
        parts.append(
            f'<path class="{cls}" id="e{i}" data-from="{esc(e["from"])}" data-to="{esc(e["to"])}" '
            f'd="{path_d(e["pts"])}" marker-end="url(#arrow)"><title>{esc(e["from"])} → {esc(e["to"])}'
            f'{(" (" + esc(e["label"]) + ")") if e.get("label") else ""}</title></path>'
        )
    parts.append('</g><g id="elabels">')
    for i, e in enumerate(lay["edges"]):
        if e.get("label"):
            x1, y1 = e["pts"][-1]
            parts.append(
                f'<text class="elabel" data-edge="e{i}" x="{x1 - 8:.1f}" y="{y1 - 4:.1f}" text-anchor="end">'
                f'{esc(e["label"])}</text>'
            )
    parts.append('</g><g id="nodes">')
    for n in lay["nodes"]:
        _, fill, ink = KINDS[n["kind"]]
        status = n.get("status", "live")
        dcol = esc(domains[n["domain"]]["color"])
        x, y, w, h = n["x"], n["y"], n["w"], n["h"]
        parts.append(
            f'<g class="node {n["kind"]} {status}" data-id="{esc(n["id"])}" transform="translate({x:.1f},{y:.1f})">'
            f'<rect class="box" width="{w}" height="{h}" rx="6" fill="{fill}" stroke="{ink}"/>'
            f'<rect width="6" height="{h}" rx="3" fill="{dcol}"/>'
        )
        ty = 2
        for line in title_lines(n):
            ty += 16
            parts.append(f'<text class="t" x="14" y="{ty}" fill="{ink}">{esc(line)}</text>')
        if n.get("path"):
            ty += 15
            p = n["path"] if len(n["path"]) <= 37 else "…" + n["path"][-36:]
            parts.append(f'<text class="p" x="14" y="{ty}">{esc(p)}</text>')
        ty += 2
        for line in wrap_desc(n.get("desc", "")):
            ty += 13
            parts.append(f'<text class="d" x="14" y="{ty}">{esc(line)}</text>')
        parts.append("</g>")
    parts.append("</g></svg>")
    return "\n".join(parts)


PAGE_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HART pipeline map</title>
<style>
html,body{margin:0;height:100%;font:13px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#111;background:#fafafa}
#wrap{position:fixed;inset:0;overflow:hidden;cursor:grab}
#wrap.drag{cursor:grabbing}
svg{width:100%;height:100%;display:block;user-select:none}
#bar{position:fixed;top:10px;left:10px;z-index:5;background:#fff;border:1px solid #ccc;border-radius:8px;padding:8px 10px;
 box-shadow:0 2px 8px rgba(0,0,0,.12);display:flex;gap:8px;align-items:center;flex-wrap:wrap;max-width:calc(100vw - 40px)}
#bar input[type=search]{width:240px;padding:4px 6px}
#bar button{padding:3px 9px}
#bar h1{font-size:14px;margin:0 6px 0 0}
#legend{position:fixed;bottom:10px;left:10px;max-width:420px;z-index:5;background:#fff;border:1px solid #ccc;border-radius:8px;padding:8px 10px;
 font-size:12px;box-shadow:0 2px 8px rgba(0,0,0,.12)}
#legend span.sw{display:inline-block;width:14px;height:11px;border:1px solid;border-radius:3px;vertical-align:-1px;margin-right:4px}
#legend div{margin:2px 0}
#info{position:fixed;top:10px;right:10px;bottom:10px;width:360px;z-index:5;background:#fff;border:1px solid #ccc;border-radius:8px;
 padding:12px 14px;overflow:auto;box-shadow:0 2px 8px rgba(0,0,0,.12);display:none}
#info h2{font-size:16px;margin:0 0 4px}
#info code{font-size:12px;word-break:break-all}
#info ul{padding-left:18px;margin:4px 0 10px}
#info a{cursor:pointer;color:#1d4ed8}
#info .close{float:right;cursor:pointer;border:0;background:none;font-size:18px}
.band{font-size:110px;font-weight:800;opacity:.35}
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
<div id="wrap">__SVG__</div>
<div id="bar"><h1>HART pipeline map</h1>
<input type="search" id="q" placeholder="Find a file, script or output…">
<span id="hits"></span>
<button id="fit" title="Show everything (F)">Fit</button><button id="zin">+</button><button id="zout">−</button>
<label><input type="checkbox" id="parked" checked> parked</label>
<label><input type="checkbox" id="retired" checked> retired</label>
<label title="Show edge labels"><input type="checkbox" id="labels" checked> edge labels</label>
</div>
<details id="legend"><summary><b>Legend and help</b></summary><b>Kind</b> (box colour)__LEGEND__<div style="margin-top:6px"><b>Lane stripe</b> = domain.
Dashed box = parked, dotted = retired, dashed line = feeds back to an earlier step.</div>
<div>Scroll or pinch to zoom, drag to pan, F fits, Esc clears. Click a box for what feeds it (amber) and what it feeds (blue).
The address bar keeps the selected box (#node=…), so a view can be shared.</div>
<div style="color:#666">Built __DATE__ from docs/pipeline-map/pipeline_map.json · __COUNTS__</div></details>
<div id="info"></div>
<script>
const DATA = __DATA__;
const svg = document.getElementById('map'), wrap = document.getElementById('wrap');
const W = +svg.dataset.w, H = +svg.dataset.h;
let vb = svg.viewBox.baseVal;
function setVB(x, y, w, h){ vb.x = x; vb.y = y; vb.width = w; vb.height = h; }
function fit(){ const r = wrap.getBoundingClientRect(); const s = Math.max(W / r.width, H / r.height);
  setVB(-180 - (r.width * s - W) / 2, -(r.height * s - H) / 2, r.width * s, r.height * s); }
function zoomAt(f, cx, cy){ const r = wrap.getBoundingClientRect();
  const px = vb.x + (cx - r.left) / r.width * vb.width, py = vb.y + (cy - r.top) / r.height * vb.height;
  const nw = Math.min(Math.max(vb.width * f, 200), W * 4), nh = nw * vb.height / vb.width;
  setVB(px - (px - vb.x) * nw / vb.width, py - (py - vb.y) * nh / vb.height, nw, nh); }
wrap.addEventListener('wheel', e => { e.preventDefault();
  const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? wrap.clientHeight : 1;
  const dx = e.deltaX * unit, dy = e.deltaY * unit;
  if (!e.ctrlKey && Math.abs(dx) > Math.abs(dy)) { const r = wrap.getBoundingClientRect(); vb.x += dx * vb.width / r.width; return; }
  zoomAt(Math.exp((e.ctrlKey ? 0.012 : 0.0025) * dy), e.clientX, e.clientY); }, {passive:false});
let drag = null, moved = false;
wrap.addEventListener('pointerdown', e => { drag = {x:e.clientX, y:e.clientY, vx:vb.x, vy:vb.y}; moved = false; wrap.classList.add('drag'); });
window.addEventListener('pointermove', e => { if (!drag) return; const r = wrap.getBoundingClientRect();
  const dx = e.clientX - drag.x, dy = e.clientY - drag.y; if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
  vb.x = drag.vx - dx * vb.width / r.width; vb.y = drag.vy - dy * vb.height / r.height; });
window.addEventListener('pointerup', () => { drag = null; wrap.classList.remove('drag'); });
document.getElementById('fit').onclick = fit;
document.getElementById('zin').onclick = () => { const r = wrap.getBoundingClientRect(); zoomAt(0.6, r.left + r.width/2, r.top + r.height/2); };
document.getElementById('zout').onclick = () => { const r = wrap.getBoundingClientRect(); zoomAt(1.6, r.left + r.width/2, r.top + r.height/2); };

const byId = {}; DATA.nodes.forEach(n => byId[n.id] = n);
const ins = {}, outs = {}; DATA.edges.forEach(e => { (outs[e.from] ||= []).push(e); (ins[e.to] ||= []).push(e); });
const nodeEl = {}; svg.querySelectorAll('.node').forEach(g => nodeEl[g.dataset.id] = g);
const edgeEls = [...svg.querySelectorAll('.edge')], labelEls = [...svg.querySelectorAll('.elabel')];
function walk(start, adj, key){ const seen = new Set([start]), st = [start];
  while (st.length) { const v = st.pop(); (adj[v] || []).forEach(e => { const w = e[key]; if (!seen.has(w)) { seen.add(w); st.push(w); } }); }
  return seen; }
function clearFocus(user){ if (user && location.hash) history.replaceState(null, '', location.pathname + location.search); svg.classList.remove('focus'); svg.querySelectorAll('.on,.sel,.upstream,.near').forEach(el => el.classList.remove('on','sel','upstream','near'));
  document.getElementById('info').style.display = 'none'; }
function centreOn(id, zoom){ const n = byId[id]; const r = wrap.getBoundingClientRect();
  const w = zoom ? 1800 : vb.width, h = w * r.height / r.width; setVB(n.x + n.w/2 - w/2, n.y + n.h/2 - h/2, w, h); }
function esc(s){ return String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function link(id){ const n = byId[id]; return `<a data-go="${esc(id)}">${esc(n.label)}</a>`; }
function select(id, fromUrl){
  clearFocus(false); if (!fromUrl) history.replaceState(null, '', '#node=' + encodeURIComponent(id)); const up = walk(id, ins, 'from'), down = walk(id, outs, 'to');
  svg.classList.add('focus'); nodeEl[id].classList.add('sel');
  up.forEach(v => nodeEl[v].classList.add('on')); down.forEach(v => nodeEl[v].classList.add('on'));
  edgeEls.forEach((el, i) => { const f = el.dataset.from, t = el.dataset.to;
    const isUp = up.has(f) && up.has(t), isDown = down.has(f) && down.has(t);
    if (isUp || isDown) { el.classList.add('on'); if (isUp && !isDown) el.classList.add('upstream');
      const near = f === id || t === id; if (near) { el.classList.add('near'); nodeEl[f].classList.add('near'); nodeEl[t].classList.add('near'); }
      const l = svg.querySelector(`.elabel[data-edge="e${i}"]`); if (l) { l.classList.add('on'); if (near) l.classList.add('near'); } } });
  const n = byId[id], info = document.getElementById('info');
  info.innerHTML = `<button class="close" title="Close (Esc)">×</button><h2>${esc(n.label)}</h2>
   <div>${esc(DATA.kinds[n.kind])} · ${esc(DATA.domains[n.domain])} · ${esc(n.status || 'live')}${n.local ? ' · local only (gitignored or on a host)' : ''}</div>
   ${n.path ? `<p><code>${esc(n.path)}</code></p>` : `<p><code>${esc(n.id)}</code></p>`}
   <p>${esc(n.desc || '')}</p>
   <b>Fed by</b><ul>${(ins[id] || []).map(e => `<li>${link(e.from)}${e.label ? ' — ' + esc(e.label) : ''}</li>`).join('') || '<li>nothing (a source)</li>'}</ul>
   <b>Feeds</b><ul>${(outs[id] || []).map(e => `<li>${link(e.to)}${e.label ? ' — ' + esc(e.label) : ''}</li>`).join('') || '<li>nothing (an end product)</li>'}</ul>
   <div style="color:#666">${up.size - 1} upstream, ${down.size - 1} downstream in all.</div>`;
  info.style.display = 'block';
  info.querySelector('.close').onclick = () => clearFocus(true);
  info.querySelectorAll('a[data-go]').forEach(a => a.onclick = () => { select(a.dataset.go); centreOn(a.dataset.go, false); });
}
svg.addEventListener('click', e => { if (moved) return; const g = e.target.closest('.node'); if (g) select(g.dataset.id); else clearFocus(true); });
const q = document.getElementById('q'), hits = document.getElementById('hits'); let found = [], fi = 0;
q.addEventListener('input', () => { svg.querySelectorAll('.node.hit').forEach(g => g.classList.remove('hit'));
  const t = q.value.trim().toLowerCase(); found = [];
  if (t) found = DATA.nodes.filter(n => (n.label + ' ' + n.id + ' ' + (n.path||'') + ' ' + (n.desc||'')).toLowerCase().includes(t)).map(n => n.id).filter(id => !nodeEl[id].classList.contains('hidden'));
  found.forEach(id => nodeEl[id].classList.add('hit')); hits.textContent = t ? `${found.length} found` + (found.length ? ' (Enter to step)' : '') : ''; fi = 0; });
q.addEventListener('keydown', e => { if (e.key === 'Enter' && found.length) { const id = found[fi++ % found.length]; centreOn(id, true); select(id); } });
document.addEventListener('keydown', e => { if (e.target === q) return; if (e.key === 'Escape') clearFocus(true); if (e.key === 'f' || e.key === 'F') fit(); });
function refreshFilters(){ const show = {live: true, parked: document.getElementById('parked').checked, retired: document.getElementById('retired').checked};
  const visible = id => show[byId[id].status || 'live'];
  DATA.nodes.forEach(n => nodeEl[n.id].classList.toggle('hidden', !visible(n.id)));
  edgeEls.forEach((el, i) => { const off = !visible(el.dataset.from) || !visible(el.dataset.to); el.classList.toggle('hidden', off);
    const l = svg.querySelector(`.elabel[data-edge="e${i}"]`); if (l) l.classList.toggle('hidden', off); }); }
document.getElementById('parked').onchange = refreshFilters;
document.getElementById('retired').onchange = refreshFilters;
document.getElementById('labels').onchange = e => document.getElementById('elabels').classList.toggle('hidden', !e.target.checked);
labelEls.forEach(l => { const p = document.getElementById(l.dataset.edge); const len = p.getTotalLength();
  const m = p.getPointAtLength(len / 2); l.setAttribute('x', m.x); l.setAttribute('y', m.y - 3); l.setAttribute('text-anchor', 'middle'); });
window.addEventListener('resize', () => { const r = wrap.getBoundingClientRect(); const cy = vb.y + vb.height / 2;
  const h = vb.width * r.height / r.width; setVB(vb.x, cy - h / 2, vb.width, h); }); fit();
function fromHash(){ const m = location.hash.match(/^#node=(.+)$/); const id = m && decodeURIComponent(m[1]);
  if (id && byId[id]) { centreOn(id, true); select(id, true); } }
fromHash(); window.addEventListener('hashchange', fromHash);
</script></body></html>
"""


def render(data: dict) -> str:
    lay = layout(data)
    domains = {d["id"]: d for d in data["domains"]}
    legend = "".join(
        f'<div><span class="sw" style="background:{fill};border-color:{ink}"></span>{esc(label)}</div>'
        for label, fill, ink in KINDS.values()
    )
    legend += "<div style='margin-top:6px'><b>Domains</b></div>" + "".join(
        f'<div><span class="sw" style="background:{esc(d["color"])};border-color:{esc(d["color"])}"></span>{esc(d["label"])}</div>'
        for d in data["domains"]
    )
    page_data = {
        "nodes": [
            {k: n[k] for k in ("id", "label", "kind", "status", "domain", "desc", "path", "local", "x", "y", "w", "h") if k in n}
            for n in lay["nodes"]
        ],
        "edges": [{k: e[k] for k in ("from", "to", "label") if k in e} for e in data["edges"]],
        "kinds": {k: v[0] for k, v in KINDS.items()},
        "domains": {d["id"]: d["label"] for d in data["domains"]},
    }
    counts = f'{len(data["nodes"])} boxes, {len(data["edges"])} links'
    return (
        PAGE_TEMPLATE.replace("__SVG__", svg(lay, domains))
        .replace("__LEGEND__", legend)
        .replace("__DATE__", esc(data.get("updated", "")))
        .replace("__COUNTS__", counts)
        .replace("__DATA__", json.dumps(page_data, separators=(",", ":")).replace("<", "\\u003c"))
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
