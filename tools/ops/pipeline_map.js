/* Layout and viewer for docs/pipeline-map/index.html. build_pipeline_map.py inlines this file into the page after the
   graph data (DATA). The layout is a layered (Sugiyama) drawing, left to right, with one horizontal lane per domain; it
   runs in the page so any subset (some lanes, or the chain around one file) gets its own compact drawing. Under node
   the file only exports the layout, for the unit tests. */
"use strict";

const NODE_W = 250, COL_GAP = 150, V_GAP = 14, BAND_PAD = 40, DUMMY_H = 2, DUMMY_GAP = 3;
const WRAP = 44, TITLE_WRAP = 30, LEFT = 180;

/* Greedy word wrap; a word longer than the width is cut. */
function wrap(text, width) {
  const lines = [];
  let cur = "";
  for (let w of String(text || "").split(/\s+/).filter(Boolean)) {
    while (w.length > width) {
      if (cur) { lines.push(cur); cur = ""; }
      lines.push(w.slice(0, width));
      w = w.slice(width);
    }
    if (!w) continue;
    if (!cur) cur = w;
    else if (cur.length + 1 + w.length <= width) cur += " " + w;
    else { lines.push(cur); cur = w; }
  }
  if (cur) lines.push(cur);
  return lines;
}

function titleLines(n) {
  const status = n.status || "live";
  const lines = wrap(n.label + (status === "live" ? "" : `  [${status}]`), TITLE_WRAP);
  return lines.length ? lines : [""];
}

function nodeHeight(n) {
  return 8 + 16 * titleLines(n).length + (n.path ? 15 : 0) + 13 * wrap(n.desc, WRAP).length + 10;
}

/* Pairs i < j with arr[j] < arr[i], by merge sort. */
function inversions(arr) {
  if (arr.length < 2) return 0;
  const mid = arr.length >> 1, left = arr.slice(0, mid), right = arr.slice(mid);
  let count = inversions(left) + inversions(right), i = 0, j = 0, k = 0;
  while (i < left.length && j < right.length) {
    if (right[j] < left[i]) { arr[k++] = right[j++]; count += left.length - i; }
    else arr[k++] = left[i++];
  }
  while (i < left.length) arr[k++] = left[i++];
  while (j < right.length) arr[k++] = right[j++];
  return count;
}

/* nodes: [{id, domain, label, desc, path, status}], edges: [{from, to}], domains: [{id}] in lane order.
   Returns the nodes with x, y, w, h; the edges with pts and back (true when the edge closes a cycle and was drawn
   turned round); the lanes (bands) with y and h; and the drawing's width and height. */
function layout(nodes, edges, domains) {
  if (!nodes.length) return { nodes: [], edges: [], bands: [], width: NODE_W, height: 200 };
  const byId = new Map(nodes.map(n => [n.id, n]));
  const ids = nodes.map(n => n.id);
  const domRank = new Map(domains.map((d, i) => [d.id, i]));
  const getList = (m, k) => { if (!m.has(k)) m.set(k, []); return m.get(k); };

  // edges that close a cycle (depth-first search) are turned round
  const outAdj = new Map(ids.map(i => [i, []]));
  edges.forEach(e => outAdj.get(e.from).push(e.to));
  const state = new Map(), back = new Set();
  for (const start of ids) {
    if (state.has(start)) continue;
    state.set(start, 1);
    const stack = [[start, 0]];
    while (stack.length) {
      const top = stack[stack.length - 1], succ = outAdj.get(top[0]);
      if (top[1] < succ.length) {
        const w = succ[top[1]++], st = state.get(w);
        if (st === 1) back.add(top[0] + "\0" + w);
        else if (st === undefined) { state.set(w, 1); stack.push([w, 0]); }
      } else { state.set(top[0], 2); stack.pop(); }
    }
  }
  const dag = edges.map(e => (back.has(e.from + "\0" + e.to) ? [e.to, e.from, true] : [e.from, e.to, false]));

  // longest-path layers, then each source pulled right next to its first consumer
  const preds = new Map(ids.map(i => [i, []])), succs = new Map(ids.map(i => [i, []]));
  dag.forEach(([a, b]) => { preds.get(b).push(a); succs.get(a).push(b); });
  const rank = new Map();
  for (const v of ids) {
    const st = [v];
    while (st.length) {
      const x = st[st.length - 1];
      if (rank.has(x)) { st.pop(); continue; }
      const missing = preds.get(x).filter(p => !rank.has(p));
      if (missing.length) { st.push(...missing); continue; }
      rank.set(x, 1 + preds.get(x).reduce((m, p) => Math.max(m, rank.get(p)), -1));
      st.pop();
    }
  }
  for (let k = 0; k < 3; k++) {
    [...ids].sort((a, b) => rank.get(b) - rank.get(a)).forEach(v => {
      const s = succs.get(v);
      if (s.length) rank.set(v, Math.max(rank.get(v), Math.min(...s.map(x => rank.get(x))) - 1));
    });
  }

  // virtual points along edges longer than one layer
  const vdom = new Map(), chains = [];
  dag.forEach(([a, b, flipped], i) => {
    const chain = [a], ra = rank.get(a), rb = rank.get(b);
    for (let r = ra + 1; r < rb; r++) {
      const vid = `\u0001v${i}_${r}`;
      vdom.set(vid, byId.get((r - ra) <= (rb - ra) / 2 ? a : b).domain);
      rank.set(vid, r);
      chain.push(vid);
    }
    chain.push(b);
    chains.push([i, chain, flipped]);
  });
  const domain = v => (byId.has(v) ? byId.get(v).domain : vdom.get(v));
  const heights = new Map(ids.map(v => [v, nodeHeight(byId.get(v))]));
  const height = v => heights.get(v) ?? DUMMY_H;
  // the room a box or a passing link takes in its column; passing links pack close, so long links run as bundles
  const room = v => height(v) + (byId.has(v) ? V_GAP : DUMMY_GAP);
  const up = new Map(), down = new Map();
  chains.forEach(([, c]) => { for (let j = 0; j + 1 < c.length; j++) { getList(down, c[j]).push(c[j + 1]); getList(up, c[j + 1]).push(c[j]); } });

  const nRanks = Math.max(...rank.values()) + 1;
  let layers = Array.from({ length: nRanks }, () => []);
  [...ids, ...vdom.keys()].forEach(v => layers[rank.get(v)].push(v));
  const byDomain = (a, b) => domRank.get(domain(a)) - domRank.get(domain(b));
  layers.forEach(l => l.sort(byDomain));
  const pos = new Map();
  const reindex = () => layers.forEach(l => l.forEach((v, i) => pos.set(v, i)));
  reindex();
  const crossings = () => {
    let total = 0;
    for (let r = 0; r + 1 < nRanks; r++) {
      const es = [];
      layers[r].forEach(a => (down.get(a) || []).forEach(b => es.push([pos.get(a), pos.get(b)])));
      es.sort((x, y) => x[0] - y[0] || x[1] - y[1]);
      total += inversions(es.map(e => e[1]));
    }
    return total;
  };

  // barycentre sweeps, keeping each column grouped by lane; the order with fewest crossings wins
  let best = [layers.map(l => l.slice()), crossings()];
  for (let it = 0; it < 28; it++) {
    const forward = it % 2 === 0, nb = forward ? up : down;
    const order = [];
    if (forward) for (let r = 1; r < nRanks; r++) order.push(r);
    else for (let r = nRanks - 2; r >= 0; r--) order.push(r);
    for (const r of order) {
      const key = new Map();
      layers[r].forEach(v => {
        const ps = (nb.get(v) || []).map(u => pos.get(u));
        key.set(v, ps.length ? ps.reduce((a, b) => a + b, 0) / ps.length : pos.get(v));
      });
      layers[r].sort((a, b) => byDomain(a, b) || key.get(a) - key.get(b));
      layers[r].forEach((v, i) => pos.set(v, i));
    }
    const c = crossings();
    if (c < best[1]) best = [layers.map(l => l.slice()), c];
  }
  layers = best[0];
  reindex();

  // lanes: each as tall as its fullest column
  const bandH = new Map(), bandTop = new Map();
  let y = 0;
  for (const d of domains) {
    let tallest = 0;
    for (const layer of layers) {
      const used = layer.filter(v => domain(v) === d.id).reduce((s, v) => s + room(v), 0);
      tallest = Math.max(tallest, used);
    }
    bandH.set(d.id, tallest ? tallest + 2 * BAND_PAD : 0);
    bandTop.set(d.id, y);
    y += bandH.get(d.id);
  }
  const totalH = y;
  const ys = new Map();
  for (const layer of layers) {
    for (const d of domains) {
      const col = layer.filter(v => domain(v) === d.id);
      const used = col.reduce((s, v) => s + room(v), 0);
      let cur = bandTop.get(d.id) + BAND_PAD + (bandH.get(d.id) - 2 * BAND_PAD - used) / 2;
      for (const v of col) { ys.set(v, cur); cur += room(v); }
    }
  }
  const centre = v => ys.get(v) + height(v) / 2;

  // straighten: each box moves toward the mean of its neighbours, keeping its order and its lane
  for (let it = 0; it < 40; it++) {
    const order = [];
    if (it % 2 === 0) for (let r = 0; r < nRanks; r++) order.push(r);
    else for (let r = nRanks - 1; r >= 0; r--) order.push(r);
    for (const r of order) {
      for (const d of domains) {
        const col = layers[r].filter(v => domain(v) === d.id);
        if (!col.length) continue;
        const place = col.map(v => {
          const nbrs = (up.get(v) || []).concat(down.get(v) || []);
          return nbrs.length ? nbrs.reduce((s, u) => s + centre(u), 0) / nbrs.length - height(v) / 2 : ys.get(v);
        });
        const lo = bandTop.get(d.id) + BAND_PAD, hi = bandTop.get(d.id) + bandH.get(d.id) - BAND_PAD;
        for (let i = 0; i < col.length; i++) {
          const floor = i === 0 ? lo : place[i - 1] + room(col[i - 1]);
          place[i] = Math.max(place[i], floor);
        }
        for (let i = col.length - 1; i >= 0; i--) {
          const ceil = i === col.length - 1 ? hi - height(col[i]) : place[i + 1] - room(col[i]);
          place[i] = Math.min(place[i], ceil);
        }
        col.forEach((v, i) => ys.set(v, place[i]));
      }
    }
  }

  const xOf = v => rank.get(v) * (NODE_W + COL_GAP);
  const outNodes = nodes.map(n => ({ ...n, x: xOf(n.id), y: ys.get(n.id), w: NODE_W, h: height(n.id) }));
  const outEdges = chains.map(([i, chain, flipped]) => {
    const pts = [];
    chain.forEach((v, j) => {
      if (byId.has(v)) pts.push([j === 0 ? xOf(v) + NODE_W : xOf(v), centre(v)]);
      else { pts.push([xOf(v), centre(v)]); pts.push([xOf(v) + NODE_W, centre(v)]); }
    });
    if (flipped) pts.reverse();
    return { ...edges[i], pts, back: flipped };
  });
  const bands = domains.filter(d => bandH.get(d.id)).map(d => ({ ...d, y: bandTop.get(d.id), h: bandH.get(d.id) }));
  return { nodes: outNodes, edges: outEdges, bands, width: nRanks * (NODE_W + COL_GAP) - COL_GAP, height: totalH };
}

/* What a click on id lights up in a drawing of these edges: every box that feeds it (up) and every box it feeds
   (down), not walking on through a box where stops(box) is true, and the links inside one side (lit). */
function chainOf(edges, id, stops) {
  const walk = (key, other) => {
    const seen = new Set([id]);
    let frontier = [id];
    while (frontier.length) {
      const next = [];
      for (const v of frontier) {
        if (v !== id && stops(v)) continue;
        for (const e of edges) if (e[other] === v && !seen.has(e[key])) { seen.add(e[key]); next.push(e[key]); }
      }
      frontier = next;
    }
    return seen;
  };
  const up = walk("from", "to"), down = walk("to", "from");
  return { up, down, lit: e => (up.has(e.from) && up.has(e.to)) || (down.has(e.from) && down.has(e.to)) };
}

/* Whether the view v (a viewBox) shows the whole drawing (x from -left, width W, height H), given that the top
   topFrac of the screen is under the toolbar; the corner overview hides while it does. */
function showsAll(v, W, H, left, topFrac) {
  const top = v.y + topFrac * v.height;
  return v.x <= -left + 1 && top <= 1 && v.x + v.width >= W - left - 1 && v.y + v.height >= H - 1;
}

/* The graph with the boxes hide(id) is true for taken out and bridged over: each link into a hidden box is joined to
   every shown box beyond it, through any run of hidden boxes, and the new link keeps the hidden boxes in via. So
   with the scripts hidden, a data file links straight to what it ends up in. */
function contract(nodes, edges, hide) {
  const outs = {};
  edges.forEach(e => (outs[e.from] ||= []).push(e));
  const kept = nodes.filter(n => !hide(n.id)), out = [], seen = new Set();
  const add = (from, to, label, via) => {
    const key = from + "\u0000" + to;
    if (from === to || seen.has(key)) return;
    seen.add(key);
    out.push(via.length ? { from, to, via } : (label ? { from, to, label } : { from, to }));
  };
  for (const n of kept) {
    for (const e of outs[n.id] || []) if (!hide(e.to)) add(n.id, e.to, e.label, []);  // direct links win
    for (const e of outs[n.id] || []) {
      if (!hide(e.to)) continue;
      const stack = [[e.to, [e.to]]], visited = new Set([e.to]);  // depth first through hidden boxes
      while (stack.length) {
        const [v, via] = stack.pop();
        for (const f of outs[v] || []) {
          if (!hide(f.to)) add(n.id, f.to, "", via);
          else if (!visited.has(f.to)) { visited.add(f.to); stack.push([f.to, via.concat(f.to)]); }
        }
      }
    }
  }
  return { nodes: kept, edges: out };
}

/* The folder a box is grouped under: its path's folder, or for a box with no path (hosts, hand work, outside
   tools) one group per lane. */
function folderOf(n) {
  if (!n.path) return `outside the repo: ${n.domain}`;
  const p = n.path.replace(/\/+$/, ""), i = p.lastIndexOf("/");
  return i < 0 ? "top level" : p.slice(0, i);
}

/* One box per folder that holds two or more of the boxes, except the folders named in open; links between
   folders are merged and counted, links inside one folder dropped. members maps each group id to its box ids. */
function groupByFolder(nodes, edges, open) {
  const byFolder = new Map();
  nodes.forEach(n => { const f = folderOf(n); if (!byFolder.has(f)) byFolder.set(f, []); byFolder.get(f).push(n); });
  const groupOf = {}, members = {}, out = [];
  for (const [f, list] of byFolder) {
    if (list.length < 2 || open.has(f)) { out.push(...list); continue; }
    const id = "folder:" + f, tally = {};
    list.forEach(n => { groupOf[n.id] = id; tally[n.domain] = (tally[n.domain] || 0) + 1; });
    const domain = Object.keys(tally).sort((a, b) => tally[b] - tally[a])[0];
    members[id] = list.map(n => n.id);
    out.push({ id, folder: f, label: f.startsWith("outside") ? f : f + "/", kind: "folder", status: "live", domain,
               desc: `${list.length} boxes`, path: "" });
  }
  const merged = new Map();
  for (const e of edges) {
    const from = groupOf[e.from] || e.from, to = groupOf[e.to] || e.to;
    if (from === to) continue;
    const key = from + "\u0000" + to;
    if (!merged.has(key)) merged.set(key, { from, to, n: 0, label: e.label });
    merged.get(key).n++;
  }
  const outEdges = [...merged.values()].map(m => {
    const grouped = groupOf[m.from] || groupOf[m.to] || m.from.startsWith("folder:") || m.to.startsWith("folder:");
    const label = m.n > 1 ? `${m.n} links` : grouped ? "" : m.label;
    return label ? { from: m.from, to: m.to, label } : { from: m.from, to: m.to };
  });
  return { nodes: out, edges: outEdges, members, groupOf };
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { layout, wrap, nodeHeight, inversions, chainOf, showsAll, contract, folderOf, groupByFolder };
} else {
  app();
}

/* ------------------------------------------------------------------ page */

function app() {
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const byId = {};
  DATA.nodes.forEach(n => (byId[n.id] = n));
  DATA.kinds.folder ||= ["Folder", "#f8fafc", "#334155"];
  DATA.presets ||= [];
  const insAll = {}, outsAll = {};
  DATA.edges.forEach(e => { (outsAll[e.from] ||= []).push(e); (insAll[e.to] ||= []).push(e); });
  const domainLabel = {};
  DATA.domains.forEach(d => (domainLabel[d.id] = d.label));
  const wrapEl = document.getElementById("wrap"), info = document.getElementById("info");
  const allLanes = DATA.domains.map(d => d.id);

  const view = { lanes: new Set(allLanes), parked: false, retired: false, focus: null, up: Infinity, down: Infinity, trim: false,
                 kindsOff: new Set(), compact: true, group: false, open: new Set() };
  let groups = { members: {}, groupOf: {} }, gNodes = {};  // folder boxes in the current drawing
  const nodeOf = id => byId[id] || gNodes[id];
  let selected = null, lay = null, svg = null, vb = null, W = 0, H = 0;
  let nodeEl = {}, edgeEls = [], sub = { nodes: [], edges: [] }, visible = new Set(), baseIds = new Set();

  /* ---- which boxes are shown */
  /* A chain is drawn through boxes but stops at deploy, hosts and runtime apps (the "hosts" lane) and at hand work:
     they are shown, not walked through, because everything deploys and the Pi's saved state comes back, so walking
     through them would reach most of the map. */
  const endsChain = id => nodeOf(id).domain === "hosts" || nodeOf(id).kind === "host" || nodeOf(id).kind === "human";
  // whether the lane filter draws a box (status and kind are applied in filtered()); the picked file always shows
  const isShown = id => id === view.focus || view.lanes.has(nodeOf(id).domain);
  /* The graph after the status and kind filters: parked and retired boxes are left out, and boxes of a hidden kind
     are bridged over (contract), so the links run on through them. The picked file always stays. */
  let g1Key = null, g1 = null, ins1 = {}, outs1 = {};
  function filtered() {
    const key = JSON.stringify([view.parked, view.retired, [...view.kindsOff].sort(), view.focus]);
    if (key === g1Key) return g1;
    const ok = n => n.id === view.focus || !n.status || n.status === "live" || view[n.status];
    const nodes = DATA.nodes.filter(ok), ids = new Set(nodes.map(n => n.id));
    const edges = DATA.edges.filter(e => ids.has(e.from) && ids.has(e.to));
    g1 = !view.kindsOff.size ? { nodes, edges } : contract(nodes, edges, id => id !== view.focus && view.kindsOff.has(byId[id].kind));
    g1.edges = g1.edges.map(e => !e.via ? e : { ...e, label: e.via.length === 1 ? "via " + byId[e.via[0]].label : `via ${e.via.length} steps` });
    ins1 = {}; outs1 = {};
    g1.edges.forEach(e => { (outs1[e.from] ||= []).push(e); (ins1[e.to] ||= []).push(e); });
    g1Key = key;
    return g1;
  }
  /* Boxes within depth links of start; with onlyShown the walk does not pass through a box the filters hide, so
     nothing past a hidden box is drawn cut off from the file. */
  function reach(start, adj, key, depth, onlyShown = false) {
    const seen = new Set([start]);
    let frontier = [start];
    for (let d = 0; d < depth && frontier.length; d++) {
      const next = [];
      frontier.forEach(v => {
        if (v !== start && endsChain(v)) return;
        (adj[v] || []).forEach(e => {
          const w = e[key];
          if (!seen.has(w) && (!onlyShown || isShown(w))) { seen.add(w); next.push(w); }
        });
      });
      frontier = next;
    }
    return seen;
  }
  function subset() {
    const g = filtered();
    groups = { members: {}, groupOf: {} }; gNodes = {};
    let keep = new Set(g.nodes.map(n => n.id));
    if (view.focus) {
      keep = new Set([view.focus]);
      reach(view.focus, ins1, "from", view.up, true).forEach(v => keep.add(v));
      reach(view.focus, outs1, "to", view.down, true).forEach(v => keep.add(v));
    }
    let nodes = g.nodes.filter(n => keep.has(n.id) && isShown(n.id));
    const ids = new Set(nodes.map(n => n.id));
    const own = view.focus && view.up <= 1 && view.down <= 1;  // only the file's own links, not its neighbours' links
    let edges = g.edges.filter(e => ids.has(e.from) && ids.has(e.to) && (!own || e.from === view.focus || e.to === view.focus));
    if (view.group && !view.focus) {  // folders: the whole map only; a file's chain is short enough already
      groups = groupByFolder(nodes, edges, view.open);
      ({ nodes, edges } = groups);
      nodes.forEach(n => { if (n.kind === "folder") gNodes[n.id] = n; });
    }
    if (view.compact) nodes = nodes.map(n => (n.kind === "folder" ? n : { ...n, desc: "", path: "" }));
    baseIds = new Set(nodes.map(n => n.id));  // what the filters draw before "highlighted only" trims it
    return trimmed() && baseIds.has(selected) ? { ...chainOnly(nodes, edges, selected), trim: true } : { nodes, edges };
  }
  const trimmed = () => view.trim && selected !== null;
  const chain = (edges, id) => chainOf(edges, id, endsChain);
  function chainOnly(nodes, edges, id) {  // "highlighted only": drop what the selection leaves dim
    const c = chain(edges, id);
    return { nodes: nodes.filter(n => c.up.has(n.id) || c.down.has(n.id)), edges: edges.filter(c.lit) };
  }

  /* ---- drawing */
  function pathD(pts) {
    let [px, py] = pts[0];
    const d = [`M${px.toFixed(1)},${py.toFixed(1)}`];
    for (const [x, y] of pts.slice(1)) {
      if (Math.abs(y - py) < 0.5) d.push(`L${x.toFixed(1)},${y.toFixed(1)}`);
      else { const mx = ((px + x) / 2).toFixed(1); d.push(`C${mx},${py.toFixed(1)} ${mx},${y.toFixed(1)} ${x.toFixed(1)},${y.toFixed(1)}`); }
      [px, py] = [x, y];
    }
    return d.join(" ");
  }
  function drawSvg(lay) {
    W = lay.width + LEFT + 60; H = Math.max(lay.height, 200);
    const p = [`<svg id="map" xmlns="http://www.w3.org/2000/svg" viewBox="${-LEFT} 0 ${W} ${H}">`,
      '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">',
      '<path d="M0,0 L10,5 L0,10 z" fill="context-stroke"/></marker></defs><g id="bands">'];
    const big = lay.width > 4000;
    for (const b of lay.bands) {
      const c = esc(b.color), size = Math.round(Math.max(18, Math.min(big ? 110 : 22, b.h * 0.15)));
      p.push(`<rect x="${-LEFT}" y="${b.y}" width="${W}" height="${b.h}" fill="${c}" fill-opacity="0.10"/>`,
        `<line x1="${-LEFT}" x2="${W - LEFT}" y1="${b.y}" y2="${b.y}" stroke="${c}" stroke-opacity="0.5"/>`);
      for (let x = -LEFT + 10; x < W - LEFT; x += 3000)
        p.push(`<text class="band" x="${x}" y="${b.y + size + 4}" font-size="${size}" fill="${c}">${esc(b.label)}</text>`);
    }
    p.push('</g><g id="edges">');
    lay.edges.forEach((e, i) => {
      p.push(`<path class="edge${e.back ? " back" : ""}" id="e${i}" data-from="${esc(e.from)}" data-to="${esc(e.to)}" ` +
        `d="${pathD(e.pts)}" marker-end="url(#arrow)"><title>${esc(e.from)} → ${esc(e.to)}${e.label ? " (" + esc(e.label) + ")" : ""}</title></path>`);
    });
    p.push(`</g><g id="elabels"${document.getElementById("labels").checked ? "" : ' class="hidden"'}>`);
    lay.edges.forEach((e, i) => { if (e.label) p.push(`<text class="elabel" data-edge="e${i}">${esc(e.label)}</text>`); });
    p.push('</g><g id="nodes">');
    for (const n of lay.nodes) {
      const [, fill, ink] = DATA.kinds[n.kind], status = n.status || "live";
      p.push(`<g class="node ${n.kind} ${status}" data-id="${esc(n.id)}" transform="translate(${n.x.toFixed(1)},${n.y.toFixed(1)})">`,
        `<rect class="box" width="${n.w}" height="${n.h}" rx="6" fill="${fill}" stroke="${ink}"/>`,
        `<rect width="6" height="${n.h}" rx="3" fill="${esc(DATA.domainColor[n.domain])}"/>`);
      let ty = 2;
      for (const line of titleLines(n)) { ty += 16; p.push(`<text class="t" x="14" y="${ty}" fill="${ink}">${esc(line)}</text>`); }
      if (n.path) {
        ty += 15;
        const shown = n.path.length <= 37 ? n.path : "…" + n.path.slice(-36);
        p.push(`<text class="p" x="14" y="${ty}">${esc(shown)}</text>`);
      }
      ty += 2;
      for (const line of wrap(n.desc, WRAP)) { ty += 13; p.push(`<text class="d" x="14" y="${ty}">${esc(line)}</text>`); }
      p.push("</g>");
    }
    p.push("</g></svg>");
    return p.join("\n");
  }

  function render(keepView) {
    sub = subset();
    const old = vb && keepView ? { x: vb.x, y: vb.y, w: vb.width, h: vb.height } : null;
    lay = layout(sub.nodes, sub.edges, DATA.domains);
    wrapEl.innerHTML = drawSvg(lay);
    svg = document.getElementById("map");
    vb = svg.viewBox.baseVal;
    nodeEl = {};
    svg.querySelectorAll(".node").forEach(g => (nodeEl[g.dataset.id] = g));
    edgeEls = [...svg.querySelectorAll(".edge")];
    drawNav();
    svg.querySelectorAll(".elabel").forEach(l => {
      const path = document.getElementById(l.dataset.edge), m = path.getPointAtLength(path.getTotalLength() / 2);
      l.setAttribute("x", m.x); l.setAttribute("y", m.y - 3); l.setAttribute("text-anchor", "middle");
    });
    visible = new Set(sub.nodes.map(n => n.id));
    syncControls();
    showStatus(sub);  // before fit, which measures the toolbar with the status line in it
    if (old) setVB(old.x, old.y, old.w, old.h); else fit();
    runSearch(true);
    if (selected && visible.has(selected)) select(selected, true);
    else { const had = selected; selected = null; info.style.display = "none"; if (had) writeHash(); }
    updateNav();
  }

  function showStatus(sub) {
    const el = document.getElementById("view");
    const parts = [];
    if (view.focus) parts.push(`<b>${esc(byId[view.focus].label)}</b>`);
    if (sub.trim) parts.push(selected === view.focus ? "highlighted only" : `only the chain of <b>${esc(nodeOf(selected).label)}</b>`);
    if (view.kindsOff.size) parts.push(`${[...view.kindsOff].map(k => DATA.kinds[k][0].toLowerCase()).join(", ")} bridged over`);
    if (view.group && !view.focus) parts.push("grouped by folder");
    const lanesOff = allLanes.filter(d => !view.lanes.has(d));
    if (lanesOff.length) parts.push(`${view.lanes.size} of ${allLanes.length} lanes`);
    const off = [!view.parked && "parked", !view.retired && "retired"].filter(Boolean);
    if (off.length) parts.push(`${off.join(" and ")} hidden`);
    showDepth();
    const all = view.focus || sub.trim || view.kindsOff.size || view.group || view.lanes.size !== allLanes.length;
    const boxes = sub.nodes.reduce((n, b) => n + (groups.members[b.id] ? groups.members[b.id].length : 1), 0);  // a folder counts its boxes
    el.innerHTML = (parts.length ? `Showing ${parts.join(" · ")} · ${boxes} of ${DATA.nodes.length} boxes`
      : `${DATA.nodes.length} boxes, ${DATA.edges.length} links`) +
      (all ? ' <button id="showall" title="Back to the whole map, every lane and kind, no folders; parked and retired boxes follow their ticks">Whole map</button>' : "");
    const btn = document.getElementById("showall");
    if (btn) btn.onclick = () => {
      view.focus = null; if (view.trim) selected = null; view.lanes = new Set(allLanes);
      view.kindsOff.clear(); view.group = false; view.open.clear(); fileIn.value = "";
      syncControls(); render(false); writeHash();
    };
  }

  /* ---- overview in the corner: the whole drawing as plain boxes, with a box round what the main view shows */
  const nav = document.getElementById("nav");
  let navSvg = null, navRect = null;
  function drawNav() {
    const w = Math.min(240, 160 * W / H), h = w * H / W;  // at most 240 wide or 160 tall
    const p = [`<svg width="${w.toFixed(0)}" height="${h.toFixed(0)}" viewBox="${-LEFT} 0 ${W} ${H}">`];
    for (const b of lay.bands) p.push(`<rect x="${-LEFT}" y="${b.y}" width="${W}" height="${b.h}" fill="${esc(b.color)}" fill-opacity="0.15"/>`);
    for (const n of lay.nodes)
      p.push(`<rect class="n" data-id="${esc(n.id)}" x="${n.x}" y="${n.y}" width="${n.w}" height="${n.h}" fill="${esc(DATA.kinds[n.kind][2])}"/>`);
    p.push('<rect class="vr"/></svg>');
    nav.innerHTML = p.join("");
    navSvg = nav.firstChild; navRect = nav.querySelector(".vr");
  }
  function updateNav() {
    if (!navRect) return;
    const r = wrapEl.getBoundingClientRect(), open = info.style.display === "block", narrow = innerWidth <= 900;
    const topFrac = Math.max(0, document.getElementById("bar").getBoundingClientRect().bottom + 10 - r.top) / r.height;
    // hidden while the whole drawing is in view below the toolbar, as at Fit, and on a phone under the open info panel
    nav.hidden = showsAll(vb, W, H, LEFT, topFrac) || (open && narrow);
    nav.style.right = open && !narrow ? `${innerWidth - info.getBoundingClientRect().left + 10}px` : "";
    navRect.setAttribute("x", vb.x); navRect.setAttribute("y", vb.y);
    navRect.setAttribute("width", vb.width); navRect.setAttribute("height", vb.height);
  }
  function panFromNav(e) {  // centre the main view on the drawing point under the pointer
    const pt = navSvg.createSVGPoint();
    pt.x = e.clientX; pt.y = e.clientY;
    const m = pt.matrixTransform(navSvg.getScreenCTM().inverse());
    setVB(m.x - vb.width / 2, m.y - vb.height / 2, vb.width, vb.height);
  }
  let navDrag = false;
  nav.addEventListener("pointerdown", e => { navDrag = true; nav.setPointerCapture(e.pointerId); panFromNav(e); e.preventDefault(); });
  nav.addEventListener("pointermove", e => { if (navDrag) panFromNav(e); });
  nav.addEventListener("pointerup", () => (navDrag = false));
  nav.addEventListener("pointercancel", () => (navDrag = false));
  nav.addEventListener("wheel", e => e.preventDefault(), { passive: false });

  /* ---- pan and zoom */
  function setVB(x, y, w, h) { vb.x = x; vb.y = y; vb.width = w; vb.height = h; updateNav(); }
  function fit() {  // whole drawing in view, below the toolbar
    const r = wrapEl.getBoundingClientRect(), top = document.getElementById("bar").getBoundingClientRect().bottom - r.top + 10;
    const s = Math.max(W / r.width, H / Math.max(r.height - top, 100));
    setVB(-LEFT - (r.width * s - W) / 2, -top * s - (r.height * s - top * s - H) / 2, r.width * s, r.height * s);
  }
  function zoomAt(f, cx, cy) {
    const r = wrapEl.getBoundingClientRect();
    const px = vb.x + (cx - r.left) / r.width * vb.width, py = vb.y + (cy - r.top) / r.height * vb.height;
    const nw = Math.min(Math.max(vb.width * f, 200), Math.max(W, 2000) * 4), nh = nw * vb.height / vb.width;
    setVB(px - (px - vb.x) * nw / vb.width, py - (py - vb.y) * nh / vb.height, nw, nh);
  }
  function centreOn(id, zoom) {
    const n = lay.nodes.find(m => m.id === id), r = wrapEl.getBoundingClientRect();
    if (!n) return;
    const w = zoom ? 1800 : vb.width, h = w * r.height / r.width;
    setVB(n.x + n.w / 2 - w / 2, n.y + n.h / 2 - h / 2, w, h);
  }
  wrapEl.addEventListener("wheel", e => {
    e.preventDefault();
    const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? wrapEl.clientHeight : 1;
    const dx = e.deltaX * unit, dy = e.deltaY * unit;
    if (!e.ctrlKey && Math.abs(dx) > Math.abs(dy)) { vb.x += dx * vb.width / wrapEl.getBoundingClientRect().width; updateNav(); return; }
    zoomAt(Math.exp((e.ctrlKey ? 0.012 : 0.0025) * dy), e.clientX, e.clientY);
  }, { passive: false });
  let drag = null, moved = false;
  wrapEl.addEventListener("pointerdown", e => { drag = { x: e.clientX, y: e.clientY, vx: vb.x, vy: vb.y }; moved = false; wrapEl.classList.add("drag"); });
  window.addEventListener("pointermove", e => {
    if (!drag) return;
    const r = wrapEl.getBoundingClientRect(), dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
    vb.x = drag.vx - dx * vb.width / r.width; vb.y = drag.vy - dy * vb.height / r.height;
    updateNav();
  });
  window.addEventListener("pointerup", () => { drag = null; wrapEl.classList.remove("drag"); });
  window.addEventListener("resize", () => {
    const r = wrapEl.getBoundingClientRect(), cy = vb.y + vb.height / 2, h = vb.width * r.height / r.width;
    setVB(vb.x, cy - h / 2, vb.width, h);
  });
  document.getElementById("fit").onclick = fit;
  const zoomCentre = f => { const r = wrapEl.getBoundingClientRect(); zoomAt(f, r.left + r.width / 2, r.top + r.height / 2); };
  document.getElementById("zin").onclick = () => zoomCentre(0.6);
  document.getElementById("zout").onclick = () => zoomCentre(1.6);

  /* ---- selection */
  function walk(start, adj, key) { return reach(start, adj, key, Infinity); }
  function clearFocus(user) {
    svg.classList.remove("focus");
    svg.querySelectorAll(".on,.sel,.upstream,.near").forEach(el => el.classList.remove("on", "sel", "upstream", "near"));
    info.style.display = "none";
    nav.classList.remove("focus"); nav.querySelectorAll("rect.on").forEach(r => r.classList.remove("on"));
    updateNav();
    if (!user) return;
    const was = trimmed();
    selected = null;
    if (was) render(false);  // "highlighted only" drew just that chain: bring the rest back
    writeHash();
  }
  /* Select a box the user picked; with "highlighted only" the drawing is redone around its chain. */
  function pick(id, centre) {
    if (!view.trim) { select(id); if (centre) centreOn(id, centre === "zoom"); return; }
    selected = id; render(false); writeHash();
    if (centre) centreOn(id, centre === "zoom");
  }
  // a box the user can pick in place: with "highlighted only" it may be off the drawn chain but inside the filters
  const pickable = id => (view.trim ? baseIds : visible).has(id);
  const link = id => `<a data-go="${esc(id)}">${esc(byId[id].label)}</a>${visible.has(id) || visible.has(groups.groupOf[id]) ? "" : ' <span class="off">(not shown)</span>'}`;
  function select(id, quiet) {
    clearFocus(false);
    selected = id;
    if (!quiet) writeHash();
    const { up: upSet, down: downSet } = chain(sub.edges, id);
    svg.classList.add("focus");
    nodeEl[id].classList.add("sel");
    upSet.forEach(v => nodeEl[v].classList.add("on"));
    downSet.forEach(v => nodeEl[v].classList.add("on"));
    edgeEls.forEach((el, i) => {
      const f = el.dataset.from, t = el.dataset.to;
      const isUp = upSet.has(f) && upSet.has(t), isDown = downSet.has(f) && downSet.has(t);
      if (!isUp && !isDown) return;
      el.classList.add("on");
      if (isUp && !isDown) el.classList.add("upstream");
      const near = f === id || t === id;
      if (near) { el.classList.add("near"); nodeEl[f].classList.add("near"); nodeEl[t].classList.add("near"); }
      const l = svg.querySelector(`.elabel[data-edge="e${i}"]`);
      if (l) { l.classList.add("on"); if (near) l.classList.add("near"); }
    });
    if (gNodes[id]) { folderInfo(id); return; }
    const n = byId[id];
    const fullUp = walk(id, insAll, "from").size - 1, fullDown = walk(id, outsAll, "to").size - 1;
    const isFocus = view.focus === id;
    info.innerHTML = `<button class="close" title="Close (Esc)">×</button><h2>${esc(n.label)}</h2>
      <div>${esc(DATA.kinds[n.kind][0])} · ${esc(domainLabel[n.domain])} · ${esc(n.status || "live")}${n.local ? " · not in this checkout's tracked files (gitignored mirror, submodule or host)" : ""}</div>
      <p><code>${esc(n.path || n.id)}</code></p><p>${esc(n.desc || "")}</p>
      ${isFocus ? "" : '<p><button id="fgo">Show only this file\'s chain</button></p>'}
      <b>Fed by</b><ul>${(insAll[id] || []).map(e => `<li>${link(e.from)}${e.label ? " — " + esc(e.label) : ""}</li>`).join("") || "<li>nothing (a source)</li>"}</ul>
      <b>Feeds</b><ul>${(outsAll[id] || []).map(e => `<li>${link(e.to)}${e.label ? " — " + esc(e.label) : ""}</li>`).join("") || "<li>nothing (an end product)</li>"}</ul>
      <div style="color:#666">${fullUp} upstream, ${fullDown} downstream in the whole map.</div>`;
    info.style.display = "block";
    nav.classList.add("focus");
    nav.querySelectorAll("rect.n").forEach(r => { if (upSet.has(r.dataset.id) || downSet.has(r.dataset.id)) r.classList.add("on"); });
    updateNav();
    info.querySelector(".close").onclick = () => clearFocus(true);
    if (!isFocus) info.querySelector("#fgo").onclick = () => focusOn(id);
    info.querySelectorAll("a[data-go]").forEach(a => (a.onclick = () => goTo(a.dataset.go)));
  }
  function folderInfo(id) {  // the info panel for a folder box
    const g = gNodes[id], list = groups.members[id];
    info.innerHTML = `<button class="close" title="Close (Esc)">×</button><h2>${esc(g.label)}</h2>
      <div>Folder · ${list.length} boxes · ${esc(domainLabel[g.domain])}</div>
      <p><button id="fopen">Open this folder</button></p>
      <b>Boxes in it</b><ul>${list.map(m => `<li><a data-go="${esc(m)}">${esc(byId[m].label)}</a></li>`).join("")}</ul>`;
    info.style.display = "block";
    updateNav();
    info.querySelector(".close").onclick = () => clearFocus(true);
    info.querySelector("#fopen").onclick = () => openFolder(g.folder);
    info.querySelectorAll("a[data-go]").forEach(a => (a.onclick = () => goTo(a.dataset.go)));
  }
  function openFolder(folder, then) {
    view.open.add(folder);
    selected = then || null;
    render(false); writeHash();
    if (then && visible.has(then)) centreOn(then, false);
  }
  function goTo(id) {
    if (groups.groupOf[id]) { openFolder(folderOf(byId[id]), id); return; }  // a box inside a closed folder
    if (pickable(id)) { pick(id, "pan"); return; }
    view.lanes = new Set(allLanes);
    if (byId[id].status in view) view[byId[id].status] = true;
    focusOn(id, !view.focus);
  }
  /* Draw one file's chain. fresh (the default) starts both sides at the whole chain; fresh = false keeps the current
     step counts, as moving from one file view to another does. */
  function focusOn(id, fresh = true) {
    fileIn.value = byId[id].path || byId[id].label;
    if (fresh) { view.up = Infinity; view.down = Infinity; }
    view.focus = id; selected = id;
    render(false); writeHash();
  }
  wrapEl.addEventListener("click", e => {
    if (moved) return;
    const g = e.target.closest(".node");
    clearTimeout(pending);
    if (!g) { clearFocus(true); return; }
    // a trimmed redraw moves the boxes, so wait out a double-click before doing it
    if (view.trim) { if (e.detail === 1) pending = setTimeout(() => pick(g.dataset.id), 300); }
    else pick(g.dataset.id);
  });
  let pending = null;
  wrapEl.addEventListener("dblclick", e => {
    clearTimeout(pending);
    const g = e.target.closest(".node");
    if (g && gNodes[g.dataset.id]) openFolder(gNodes[g.dataset.id].folder);
    else if (g) focusOn(g.dataset.id, !view.focus);
  });

  /* ---- search */
  const q = document.getElementById("q"), hits = document.getElementById("hits");
  let found = [], fi = 0;
  function runSearch(keepIndex) {
    svg.querySelectorAll(".node.hit").forEach(g => g.classList.remove("hit"));
    const t = q.value.trim().toLowerCase();
    found = !t ? [] : DATA.nodes.filter(n => (n.label + " " + n.id + " " + (n.path || "") + " " + (n.desc || "")).toLowerCase().includes(t)).map(n => n.id);
    const where = id => (visible.has(id) ? id : visible.has(groups.groupOf[id]) ? groups.groupOf[id] : null);
    const shown = found.filter(where);
    shown.forEach(id => nodeEl[where(id)].classList.add("hit"));
    hits.textContent = !t ? "" : `${shown.length} found` + (found.length > shown.length ? ` (+${found.length - shown.length} not shown)` : "") + (found.length ? " · Enter steps" : "");
    if (!keepIndex) fi = 0;
  }
  q.addEventListener("input", () => runSearch(false));
  q.addEventListener("keydown", e => {
    if (e.key !== "Enter" || !found.length) return;
    const id = found[fi++ % found.length];
    if (!pickable(id)) goTo(id);
    else pick(id, "zoom");
  });
  document.addEventListener("keydown", e => {
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable || e.metaKey || e.ctrlKey || e.altKey) return;  // typing in any field, the site header's search too
    if (e.key === "Escape") clearFocus(true);
    if (e.key === "f" || e.key === "F") fit();
  });

  /* ---- steps either side of a file: how far the chain runs left (what feeds it) and right (what it feeds) */
  const depthBox = document.getElementById("depth");
  const stepText = n => (n === Infinity ? "all" : String(n));
  function showDepth() {
    depthBox.hidden = !view.focus;
    document.getElementById("upn").textContent = stepText(view.up);
    document.getElementById("downn").textContent = stepText(view.down);
  }
  function maxSteps(adj, key) {  // the longest chain on that side, so "+" from a number can reach "all"
    let n = 0;
    for (let d = 1; d < 400; d++) { if (reach(view.focus, adj, key, d, true).size === reach(view.focus, adj, key, d - 1, true).size) break; n = d; }
    return n;
  }
  function step(side, change) {
    const adj = side === "up" ? [ins1, "from"] : [outs1, "to"], most = maxSteps(...adj);
    let n = view[side] === Infinity ? most : view[side];
    n = change === "all" ? Infinity : Math.max(0, n + change);
    if (most > 0 && n >= most) n = Infinity;  // a side with no links stays at the number chosen
    view[side] = n;
    render(true); writeHash();
  }
  depthBox.addEventListener("click", e => {
    const b = e.target.closest("button[data-side]");
    if (b) step(b.dataset.side, b.dataset.step === "all" ? "all" : Number(b.dataset.step));
  });

  /* ---- file filter: pick a file to see its whole chain, sources to end products */
  const fileIn = document.getElementById("file");
  document.getElementById("files").innerHTML = DATA.nodes.slice().sort((a, b) => a.label.localeCompare(b.label))
    .map(n => `<option value="${esc(n.path || n.label)}">${esc(n.label)}</option>`).join("");
  const byName = {};
  DATA.nodes.forEach(n => { byName[(n.path || n.label).toLowerCase()] = n.id; byName[n.label.toLowerCase()] ??= n.id; byName[n.id.toLowerCase()] ??= n.id; });
  function pickFile() {
    const text = fileIn.value.trim();
    if (!text) {  // an emptied box goes back to the whole map
      if (view.focus) { view.focus = null; syncControls(); render(false); writeHash(); }
      return;
    }
    const id = byName[text.toLowerCase()];
    if (id) focusOn(id);
    else hits.textContent = `no file named "${text}"`;
  }
  fileIn.addEventListener("change", pickFile);

  /* ---- Browse: the map's files as a folder tree; a folder holding only one folder is shown joined to it
     (jmri/layouts/hart), and boxes with no path sit under "outside the repo" by lane */
  const treeBox = document.getElementById("tree"), browse = document.getElementById("browse");
  const root = { dirs: new Map(), files: [] };
  for (const n of DATA.nodes) {
    const segs = n.path ? n.path.replace(/\/+$/, "").split("/") : ["outside the repo", domainLabel[n.domain]];
    let at = root;
    for (const seg of (n.path ? segs.slice(0, -1) : segs)) {
      if (!at.dirs.has(seg)) at.dirs.set(seg, { dirs: new Map(), files: [] });
      at = at.dirs.get(seg);
    }
    at.files.push({ id: n.id, name: n.path ? segs[segs.length - 1] : n.label, n });
  }
  const count = d => d.files.length + [...d.dirs.values()].reduce((s, c) => s + count(c), 0);
  function treeHtml(d) {
    const dirs = [...d.dirs].sort(([a], [b]) => a.localeCompare(b)).map(([name, sub]) => {
      while (!sub.files.length && sub.dirs.size === 1) { const [[n2, s2]] = sub.dirs; name += "/" + n2; sub = s2; }
      return `<details><summary>${esc(name)}/ <span class="c">${count(sub)}</span></summary>${treeHtml(sub)}</details>`;
    });
    const files = d.files.slice().sort((a, b) => a.name.localeCompare(b.name)).map(f => {
      const st = f.n.status && f.n.status !== "live" ? ` <span class="c">${esc(f.n.status)}</span>` : "";
      return `<a data-file="${esc(f.id)}" title="${esc(f.n.label)}">${esc(f.name)}${st}</a>`;
    });
    return dirs.join("") + files.join("");
  }
  treeBox.innerHTML = treeHtml(root);
  treeBox.addEventListener("click", e => {
    const a = e.target.closest("a[data-file]");
    if (!a) return;
    browse.open = false;
    focusOn(a.dataset.file);
  });
  fileIn.addEventListener("keydown", e => { if (e.key === "Enter") pickFile(); });

  /* ---- start-here buttons: a preset file view for the questions people ask first */
  document.getElementById("presets").innerHTML = DATA.presets.length ? "Start with: " + DATA.presets.map((pr, i) =>
    `<button data-preset="${i}" title="${esc(byId[pr.focus].label)}, ${pr.up} back and ${pr.down} on">${esc(pr.label)}</button>`).join(" ") : "";
  document.getElementById("presets").addEventListener("click", e => {
    const b = e.target.closest("button[data-preset]");
    if (!b) return;
    const pr = DATA.presets[Number(b.dataset.preset)], steps = v => (v === "all" ? Infinity : v);
    view.focus = selected = pr.focus; view.up = steps(pr.up); view.down = steps(pr.down);
    view.lanes = new Set(allLanes); view.kindsOff.clear(); view.trim = false;  // the preset's step counts as written
    fileIn.value = byId[pr.focus].path || byId[pr.focus].label;
    syncControls(); render(false); writeHash();
  });

  /* ---- share: the address with the view as it is now, zoom and position included, copied to the clipboard */
  document.getElementById("share").onclick = () => {
    writeHash(true);
    const done = t => { hits.textContent = t; setTimeout(() => { if (hits.textContent === t) runSearch(true); }, 4000); };
    if (navigator.clipboard) navigator.clipboard.writeText(location.href).then(() => done("Link copied"), () => done("Copy the address bar to share"));
    else done("Copy the address bar to share");
  };

  /* ---- lanes, kinds and status filters */
  const kindsBox = document.getElementById("kindlist");
  /* Host and hand-work boxes are where a chain stops (endsChain), so they are not offered: bridging over them would
     run every chain on through the deploys. */
  const hideable = k => Object.hasOwn(DATA.kinds, k) && !["folder", "host", "human"].includes(k);
  kindsBox.innerHTML = Object.entries(DATA.kinds).filter(([k]) => hideable(k)).map(([k, [label, fill, ink]]) =>
    `<label><input type="checkbox" data-kind="${esc(k)}" checked> <span class="sw" style="background:${esc(fill)};border-color:${esc(ink)}"></span>${esc(label)}</label>`).join("<br>");
  kindsBox.addEventListener("change", e => {
    const k = e.target.dataset.kind;
    if (!k) return;
    if (e.target.checked) view.kindsOff.delete(k); else view.kindsOff.add(k);
    render(false); writeHash();
  });
  document.getElementById("compact").onchange = e => { view.compact = e.target.checked; render(false); writeHash(); };
  document.getElementById("group").onchange = e => { view.group = e.target.checked; view.open.clear(); render(false); writeHash(); };
  const lanesBox = document.getElementById("lanerows");
  lanesBox.innerHTML = DATA.domains.map(d =>
    `<label><input type="checkbox" data-lane="${esc(d.id)}" checked> <span class="sw" style="background:${esc(d.color)}"></span>${esc(d.label)}</label>` +
    ` <a data-only="${esc(d.id)}">only</a>`).join("<br>");
  function syncControls() {
    lanesBox.querySelectorAll("input[data-lane]").forEach(c => (c.checked = view.lanes.has(c.dataset.lane)));
    document.getElementById("parked").checked = view.parked;
    document.getElementById("retired").checked = view.retired;
    document.getElementById("trim").checked = view.trim;
    kindsBox.querySelectorAll("input[data-kind]").forEach(c => (c.checked = !view.kindsOff.has(c.dataset.kind)));
    document.getElementById("compact").checked = view.compact;
    document.getElementById("group").checked = view.group;
  }
  lanesBox.addEventListener("change", e => {
    const lane = e.target.dataset.lane;
    if (!lane) return;
    if (e.target.checked) view.lanes.add(lane); else view.lanes.delete(lane);
    render(false); writeHash();
  });
  lanesBox.addEventListener("click", e => {
    const only = e.target.dataset && e.target.dataset.only;
    if (!only) return;
    view.lanes = new Set([only]); syncControls(); render(false); writeHash();
  });
  document.getElementById("parked").onchange = e => { view.parked = e.target.checked; render(true); writeHash(); };
  document.getElementById("retired").onchange = e => { view.retired = e.target.checked; render(true); writeHash(); };
  document.getElementById("trim").onchange = e => { view.trim = e.target.checked; render(selected === null); writeHash(); };
  document.getElementById("labels").onchange = e => document.getElementById("elabels").classList.toggle("hidden", !e.target.checked);

  /* ---- address bar: #focus=<id>&up=all&down=2&lanes=a,b&show=parked,retired&trim=1&hidekind=generator&compact=0
     &folders=1&open=<folder>,<folder>&node=<id>, and with share also at=<x>,<y>,<width> (the zoom and position) */
  function writeHash(withView = false) {
    const h = new URLSearchParams();
    const steps = n => (n === Infinity ? "all" : String(n));
    if (view.focus) { h.set("focus", view.focus); h.set("up", steps(view.up)); h.set("down", steps(view.down)); }
    if (view.lanes.size !== allLanes.length) h.set("lanes", view.lanes.size ? [...view.lanes].join(",") : "none");
    const show = [view.parked && "parked", view.retired && "retired"].filter(Boolean);
    if (show.length) h.set("show", show.join(","));
    if (view.trim) h.set("trim", "1");
    if (view.kindsOff.size) h.set("hidekind", [...view.kindsOff].join(","));
    if (!view.compact) h.set("compact", "0");  // compact is the default
    if (view.group) { h.set("folders", "1"); if (view.open.size) h.set("open", [...view.open].join(",")); }
    if (selected) h.set("node", selected);
    if (withView) h.set("at", [vb.x, vb.y, vb.width].map(v => Math.round(v)).join(","));
    const s = h.toString();
    history.replaceState(null, "", s ? "#" + s : location.pathname + location.search);
  }
  function readHash() {
    const h = new URLSearchParams(location.hash.slice(1));
    const focus = h.get("focus");
    view.focus = focus && Object.hasOwn(byId, focus) ? focus : null;
    const steps = v => (v !== null && /^\d+$/.test(v) ? Number(v) : Infinity);
    view.up = steps(h.get("up")); view.down = steps(h.get("down"));
    if (h.get("up") === null && h.get("down") === null) {  // older links: dir=both|up|down and depth=N
      const depth = steps(h.get("depth")), dir = h.get("dir");
      view.up = dir === "down" ? 0 : depth; view.down = dir === "up" ? 0 : depth;
    }
    const lanes = (h.get("lanes") || "").split(",").filter(l => allLanes.includes(l));
    view.lanes = new Set(lanes.length || h.get("lanes") === "none" ? lanes : allLanes);
    const show = (h.get("show") || "").split(","), hide = h.get("hide");
    if (hide !== null) { view.parked = !hide.includes("parked"); view.retired = !hide.includes("retired"); }  // older links
    else if (h.get("show") === null && (h.get("dir") !== null || h.get("depth") !== null)) view.parked = view.retired = true;  // older file links showed every status
    else { view.parked = show.includes("parked"); view.retired = show.includes("retired"); }
    view.trim = h.get("trim") === "1";
    view.kindsOff = new Set((h.get("hidekind") || "").split(",").filter(hideable));
    view.compact = h.get("compact") !== "0";
    view.group = h.get("folders") === "1";
    view.open = new Set(view.group && h.get("open") ? h.get("open").split(",") : []);
    const node = h.get("node");
    selected = node && (Object.hasOwn(byId, node) || node.startsWith("folder:")) ? node : null;
    if (selected && Object.hasOwn(byId, selected) && !view.focus && byId[selected].status in view) view[byId[selected].status] = true;  // keep a shared box in view
    fileIn.value = view.focus ? byId[view.focus].path || byId[view.focus].label : "";
    syncControls();
  }
  /* A shared link's zoom and position (at=x,y,width), kept to the window's shape. */
  function restoreView() {
    const at = (new URLSearchParams(location.hash.slice(1)).get("at") || "").split(",").map(Number);
    if (at.length !== 3 || at.some(v => !Number.isFinite(v)) || at[2] <= 0) return false;
    const r = wrapEl.getBoundingClientRect();
    setVB(at[0], at[1], at[2], at[2] * r.height / r.width);
    return true;
  }
  function arrive(first) {  // first load: a file view opens at Fit; a later address change pans to the selected box
    readHash();
    render(false);
    if (restoreView() || !selected || !visible.has(selected) || view.trim) return;
    if (!view.focus) centreOn(selected, true);
    else if (!first) centreOn(selected, false);
  }
  arrive(true);
  window.addEventListener("hashchange", () => arrive(false));
}
