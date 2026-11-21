/* Layout and viewer for docs/pipeline-map/index.html. build_pipeline_map.py inlines this file into the page after the
   graph data (DATA). The layout is a layered (Sugiyama) drawing, left to right, with one horizontal lane per domain; it
   runs in the page so any subset (some lanes, or the chain around one file) gets its own compact drawing. Under node
   the file only exports the layout, for the unit tests. */
"use strict";

const NODE_W = 250, COL_GAP = 150, V_GAP = 14, BAND_PAD = 40, DUMMY_H = 6;
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
      const used = layer.filter(v => domain(v) === d.id).reduce((s, v) => s + height(v) + V_GAP, 0);
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
      const used = col.reduce((s, v) => s + height(v) + V_GAP, 0);
      let cur = bandTop.get(d.id) + BAND_PAD + (bandH.get(d.id) - 2 * BAND_PAD - used) / 2;
      for (const v of col) { ys.set(v, cur); cur += height(v) + V_GAP; }
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
          const floor = i === 0 ? lo : place[i - 1] + height(col[i - 1]) + V_GAP;
          place[i] = Math.max(place[i], floor);
        }
        for (let i = col.length - 1; i >= 0; i--) {
          const ceil = i === col.length - 1 ? hi - height(col[i]) : place[i + 1] - height(col[i]) - V_GAP;
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

if (typeof module !== "undefined" && module.exports) {
  module.exports = { layout, wrap, nodeHeight, inversions };
} else {
  app();
}

/* ------------------------------------------------------------------ page */

function app() {
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const byId = {};
  DATA.nodes.forEach(n => (byId[n.id] = n));
  const insAll = {}, outsAll = {};
  DATA.edges.forEach(e => { (outsAll[e.from] ||= []).push(e); (insAll[e.to] ||= []).push(e); });
  const domainLabel = {};
  DATA.domains.forEach(d => (domainLabel[d.id] = d.label));
  const wrapEl = document.getElementById("wrap"), info = document.getElementById("info");
  const allLanes = DATA.domains.map(d => d.id);

  const view = { lanes: new Set(allLanes), parked: false, retired: false, focus: null, dir: "both", depth: Infinity };
  let selected = null, lay = null, svg = null, vb = null, W = 0, H = 0;
  let nodeEl = {}, edgeEls = [], ins = {}, outs = {}, visible = new Set();

  /* ---- which boxes are shown */
  /* A chain is drawn through boxes but stops at deploy, hosts and runtime apps (the "hosts" lane) and at hand work:
     they are shown, not walked through, because everything deploys and the Pi's saved state comes back, so walking
     through them would reach most of the map. */
  const endsChain = id => byId[id].domain === "hosts" || byId[id].kind === "host" || byId[id].kind === "human";
  function reach(start, adj, key, depth) {
    const seen = new Set([start]);
    let frontier = [start];
    for (let d = 0; d < depth && frontier.length; d++) {
      const next = [];
      frontier.forEach(v => {
        if (v !== start && endsChain(v)) return;
        (adj[v] || []).forEach(e => { const w = e[key]; if (!seen.has(w)) { seen.add(w); next.push(w); } });
      });
      frontier = next;
    }
    return seen;
  }
  function subset() {
    let keep = new Set(DATA.nodes.map(n => n.id));
    if (view.focus) {
      keep = new Set([view.focus]);
      if (view.dir !== "down") reach(view.focus, insAll, "from", view.depth).forEach(v => keep.add(v));
      if (view.dir !== "up") reach(view.focus, outsAll, "to", view.depth).forEach(v => keep.add(v));
    }
    // a file view shows every box related to the file, whatever its lane or status
    const shown = n => view.focus || (view.lanes.has(n.domain) && (n.status === "live" || !n.status || view[n.status]));
    const nodes = DATA.nodes.filter(n => keep.has(n.id) && shown(n));
    const ids = new Set(nodes.map(n => n.id));
    const own = view.focus && view.depth === 1;  // only the file's own links, not those between its neighbours
    return { nodes, edges: DATA.edges.filter(e => ids.has(e.from) && ids.has(e.to) && (!own || e.from === view.focus || e.to === view.focus)) };
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
      const c = esc(b.color), size = Math.round(Math.max(18, Math.min(big ? 110 : 22, b.h * 0.3)));
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
    const sub = subset();
    const old = vb && keepView ? { x: vb.x, y: vb.y, w: vb.width, h: vb.height } : null;
    lay = layout(sub.nodes, sub.edges, DATA.domains);
    wrapEl.innerHTML = drawSvg(lay);
    svg = document.getElementById("map");
    vb = svg.viewBox.baseVal;
    nodeEl = {};
    svg.querySelectorAll(".node").forEach(g => (nodeEl[g.dataset.id] = g));
    edgeEls = [...svg.querySelectorAll(".edge")];
    svg.querySelectorAll(".elabel").forEach(l => {
      const path = document.getElementById(l.dataset.edge), m = path.getPointAtLength(path.getTotalLength() / 2);
      l.setAttribute("x", m.x); l.setAttribute("y", m.y - 3); l.setAttribute("text-anchor", "middle");
    });
    ins = {}; outs = {};
    sub.edges.forEach(e => { (outs[e.from] ||= []).push(e); (ins[e.to] ||= []).push(e); });
    visible = new Set(sub.nodes.map(n => n.id));
    syncControls();
    showStatus(sub);  // before fit, which measures the toolbar with the status line in it
    if (old) setVB(old.x, old.y, old.w, old.h); else fit();
    runSearch(true);
    if (selected && visible.has(selected)) select(selected, true);
    else { const had = selected; selected = null; info.style.display = "none"; if (had) writeHash(); }
  }

  function showStatus(sub) {
    const el = document.getElementById("view");
    const parts = [];
    if (view.focus) {
      const how = { both: "what feeds it and what it feeds", up: "what feeds it", down: "what it feeds" }[view.dir];
      const depth = view.depth === 1 ? "its own links only" : view.depth === Infinity ? "the whole chain" : `${view.depth} steps`;
      parts.push(`<b>${esc(byId[view.focus].label)}</b>: ${how}, ${depth}`);
    } else {
      const lanesOff = allLanes.filter(d => !view.lanes.has(d));
      if (lanesOff.length) parts.push(`${view.lanes.size} of ${allLanes.length} lanes`);
      const off = [!view.parked && "parked", !view.retired && "retired"].filter(Boolean);
      if (off.length) parts.push(`${off.join(" and ")} hidden`);
    }
    const all = view.focus || view.lanes.size !== allLanes.length;
    el.innerHTML = (parts.length ? `Showing ${parts.join(" · ")} · ${sub.nodes.length} of ${DATA.nodes.length} boxes`
      : `${DATA.nodes.length} boxes, ${DATA.edges.length} links`) +
      (all ? ' <button id="showall" title="Back to the whole map; parked and retired boxes follow their ticks">Whole map</button>' : "");
    const btn = document.getElementById("showall");
    if (btn) btn.onclick = () => { view.focus = null; view.lanes = new Set(allLanes); fileIn.value = ""; syncControls(); render(false); writeHash(); };
  }

  /* ---- pan and zoom */
  function setVB(x, y, w, h) { vb.x = x; vb.y = y; vb.width = w; vb.height = h; }
  function fit() {  // whole drawing in view, below the toolbar
    const r = wrapEl.getBoundingClientRect(), top = document.getElementById("bar").getBoundingClientRect().bottom + 10;
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
    if (!e.ctrlKey && Math.abs(dx) > Math.abs(dy)) { vb.x += dx * vb.width / wrapEl.getBoundingClientRect().width; return; }
    zoomAt(Math.exp((e.ctrlKey ? 0.012 : 0.0025) * dy), e.clientX, e.clientY);
  }, { passive: false });
  let drag = null, moved = false;
  wrapEl.addEventListener("pointerdown", e => { drag = { x: e.clientX, y: e.clientY, vx: vb.x, vy: vb.y }; moved = false; wrapEl.classList.add("drag"); });
  window.addEventListener("pointermove", e => {
    if (!drag) return;
    const r = wrapEl.getBoundingClientRect(), dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
    vb.x = drag.vx - dx * vb.width / r.width; vb.y = drag.vy - dy * vb.height / r.height;
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
    if (user) { selected = null; writeHash(); }
  }
  const link = id => `<a data-go="${esc(id)}">${esc(byId[id].label)}</a>${visible.has(id) ? "" : ' <span class="off">(not shown)</span>'}`;
  function select(id, quiet) {
    clearFocus(false);
    selected = id;
    if (!quiet) writeHash();
    const upSet = walk(id, ins, "from"), downSet = walk(id, outs, "to");
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
    const n = byId[id];
    const fullUp = walk(id, insAll, "from").size - 1, fullDown = walk(id, outsAll, "to").size - 1;
    const isFocus = view.focus === id;
    info.innerHTML = `<button class="close" title="Close (Esc)">×</button><h2>${esc(n.label)}</h2>
      <div>${esc(DATA.kinds[n.kind][0])} · ${esc(domainLabel[n.domain])} · ${esc(n.status || "live")}${n.local ? " · not in this checkout's tracked files (gitignored mirror, submodule or host)" : ""}</div>
      <p><code>${esc(n.path || n.id)}</code></p><p>${esc(n.desc || "")}</p>
      <div class="chain"><b>Show only this box's chain</b><br>
        <select id="fdir"><option value="both">what feeds it and what it feeds</option><option value="up">what feeds it</option><option value="down">what it feeds</option></select>
        <select id="fdepth"><option value="Infinity" selected>the whole chain</option><option value="1">its own links only</option><option value="2">2 steps</option><option value="3">3 steps</option></select>
        <button id="fgo">${isFocus ? "Update" : "Show"}</button></div>
      <b>Fed by</b><ul>${(insAll[id] || []).map(e => `<li>${link(e.from)}${e.label ? " — " + esc(e.label) : ""}</li>`).join("") || "<li>nothing (a source)</li>"}</ul>
      <b>Feeds</b><ul>${(outsAll[id] || []).map(e => `<li>${link(e.to)}${e.label ? " — " + esc(e.label) : ""}</li>`).join("") || "<li>nothing (an end product)</li>"}</ul>
      <div style="color:#666">${fullUp} upstream, ${fullDown} downstream in the whole map.</div>`;
    info.style.display = "block";
    if (isFocus) { info.querySelector("#fdir").value = view.dir; info.querySelector("#fdepth").value = String(view.depth); }
    info.querySelector(".close").onclick = () => clearFocus(true);
    info.querySelector("#fgo").onclick = () => focusOn(id, info.querySelector("#fdir").value, Number(info.querySelector("#fdepth").value));
    info.querySelectorAll("a[data-go]").forEach(a => (a.onclick = () => goTo(a.dataset.go)));
  }
  function goTo(id) {
    if (visible.has(id)) { select(id); centreOn(id, false); return; }
    view.lanes = new Set(allLanes);
    syncControls();
    focusOn(id, view.focus ? view.dir : "both", view.focus ? view.depth : Infinity);
  }
  function focusOn(id, dir, depth) {
    fileIn.value = byId[id].path || byId[id].label;
    view.focus = id; view.dir = dir; view.depth = depth; selected = id;
    render(false); writeHash();
  }
  wrapEl.addEventListener("click", e => {
    if (moved) return;
    const g = e.target.closest(".node");
    if (g) select(g.dataset.id); else clearFocus(true);
  });
  wrapEl.addEventListener("dblclick", e => { const g = e.target.closest(".node"); if (g) focusOn(g.dataset.id, view.focus ? view.dir : "both", view.focus ? view.depth : Infinity); });

  /* ---- search */
  const q = document.getElementById("q"), hits = document.getElementById("hits");
  let found = [], fi = 0;
  function runSearch(keepIndex) {
    svg.querySelectorAll(".node.hit").forEach(g => g.classList.remove("hit"));
    const t = q.value.trim().toLowerCase();
    found = !t ? [] : DATA.nodes.filter(n => (n.label + " " + n.id + " " + (n.path || "") + " " + (n.desc || "")).toLowerCase().includes(t)).map(n => n.id);
    const shown = found.filter(id => visible.has(id));
    shown.forEach(id => nodeEl[id].classList.add("hit"));
    hits.textContent = !t ? "" : `${shown.length} found` + (found.length > shown.length ? ` (+${found.length - shown.length} not shown)` : "") + (found.length ? " · Enter steps" : "");
    if (!keepIndex) fi = 0;
  }
  q.addEventListener("input", () => runSearch(false));
  q.addEventListener("keydown", e => {
    if (e.key !== "Enter" || !found.length) return;
    const id = found[fi++ % found.length];
    if (!visible.has(id)) goTo(id);
    else { centreOn(id, true); select(id); }
  });
  document.addEventListener("keydown", e => {
    if (e.target === q || e.target === fileIn || e.target.tagName === "SELECT" || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "Escape") clearFocus(true);
    if (e.key === "f" || e.key === "F") fit();
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
    if (id) focusOn(id, "both", Infinity);
    else hits.textContent = `no file named "${text}"`;
  }
  fileIn.addEventListener("change", pickFile);
  fileIn.addEventListener("keydown", e => { if (e.key === "Enter") pickFile(); });

  /* ---- lanes and status filters */
  const lanesBox = document.getElementById("lanelist");
  lanesBox.innerHTML = DATA.domains.map(d =>
    `<label><input type="checkbox" data-lane="${esc(d.id)}" checked> <span class="sw" style="background:${esc(d.color)}"></span>${esc(d.label)}</label>` +
    ` <a data-only="${esc(d.id)}">only</a>`).join("<br>");
  function syncControls() {
    lanesBox.querySelectorAll("input[data-lane]").forEach(c => (c.checked = view.lanes.has(c.dataset.lane)));
    document.getElementById("parked").checked = view.parked;
    document.getElementById("retired").checked = view.retired;
    for (const box of ["parked", "retired"]) {  // a file view shows every related box, so the ticks do not apply
      const el = document.getElementById(box);
      el.disabled = Boolean(view.focus);
      el.parentElement.title = view.focus ? "A file view shows every related box" : el.parentElement.dataset.title;
    }
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
  document.getElementById("labels").onchange = e => document.getElementById("elabels").classList.toggle("hidden", !e.target.checked);

  /* ---- address bar: #focus=<id>&dir=both&depth=1&lanes=a,b&show=parked,retired&node=<id> */
  function writeHash() {
    const h = new URLSearchParams();
    if (view.focus) { h.set("focus", view.focus); h.set("dir", view.dir); if (view.depth !== Infinity) h.set("depth", view.depth); }
    if (view.lanes.size !== allLanes.length) h.set("lanes", view.lanes.size ? [...view.lanes].join(",") : "none");
    const show = [view.parked && "parked", view.retired && "retired"].filter(Boolean);
    if (show.length) h.set("show", show.join(","));
    if (selected) h.set("node", selected);
    const s = h.toString();
    history.replaceState(null, "", s ? "#" + s : location.pathname + location.search);
  }
  function readHash() {
    const h = new URLSearchParams(location.hash.slice(1));
    const focus = h.get("focus");
    view.focus = focus && byId[focus] ? focus : null;
    view.dir = ["both", "up", "down"].includes(h.get("dir")) ? h.get("dir") : "both";
    const depth = Number(h.get("depth"));
    view.depth = depth > 0 ? depth : Infinity;
    const lanes = (h.get("lanes") || "").split(",").filter(l => allLanes.includes(l));
    view.lanes = new Set(lanes.length || h.get("lanes") === "none" ? lanes : allLanes);
    const show = (h.get("show") || "").split(","), hide = h.get("hide");
    if (hide !== null) { view.parked = !hide.includes("parked"); view.retired = !hide.includes("retired"); }  // older links
    else { view.parked = show.includes("parked"); view.retired = show.includes("retired"); }
    const node = h.get("node");
    selected = node && byId[node] ? node : null;
    if (selected && !view.focus && byId[selected].status in view) view[byId[selected].status] = true;  // keep a shared box in view
    fileIn.value = view.focus ? byId[view.focus].path || byId[view.focus].label : "";
    syncControls();
  }
  readHash();
  render(false);
  if (selected && visible.has(selected) && !view.focus) centreOn(selected, true);
  window.addEventListener("hashchange", () => { readHash(); render(false); if (selected && visible.has(selected)) centreOn(selected, !view.focus); });
}
