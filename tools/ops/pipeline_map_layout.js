/* Layout for the pipeline map pages (docs/pipeline-map/index.html and the website copy): pure functions, no page state.
   build_pipeline_map.py inlines this file, pipeline_map_helpers.js and then the viewer (pipeline_map_view.js,
   pipeline_map_view_frame.js, pipeline_map_view_input.js; its SCRIPTS) into one script in the page, after the graph
   data (DATA). The layout is a layered (Sugiyama) drawing, left to right, with one
   horizontal lane per domain; it runs in the page so any subset (some lanes, or the chain around one file) gets its
   own compact drawing. Under node the file exports these functions and the helpers', for the unit tests
   (tools/audit/tests/test_pipeline_map.py). */
"use strict";

const V_GAP = 14, BAND_PAD = 40, DUMMY_H = 2, DUMMY_GAP = 3;
const WRAP = 44, LEFT = 180, BAND_RUN = 100000;  // BAND_RUN: how far the lane colours run past the drawing's ends
/* Column geometry: box width, the gap between columns and the title's wrap width in characters. Full boxes carry a
   path and a description; compact boxes (names only) are narrower with a smaller gap, so the whole map is about 35%
   narrower and everything is drawn bigger at Fit. */
const WIDE = { nodeW: 250, colGap: 150, titleWrap: 30, descWrap: 44 };
const NARROW = { nodeW: 180, colGap: 80, titleWrap: 22, descWrap: 44 };
const stepOf = geo => geo.nodeW + geo.colGap;
/* How many times wider a step is when n of cols steps of geometry geo fill the width all of them fill unspread (the
   Steps slider): (n - 1) spread steps and one spread box span (cols - 1) steps and one box, the boxes widening up to
   BOX_GROW times (spreadGeo). All of them, or a map of one or two columns, is 1; n is at least 2 here (the slider keeps
   it at 3 or more). */
const BOX_GROW = 2.5;
function spreadFor(cols, n, geo = NARROW, cap = BOX_GROW) {
  if (cols < 2 || !(n < cols)) return 1;
  cap = Math.max(1, cap);  // boxes never shrink (spreadGeo)
  const step = stepOf(geo), span = (cols - 1) * step + geo.nodeW, gaps = (Math.max(2, Math.round(n)) - 1) * step;
  const k = span / (gaps + geo.nodeW);  // boxes widen as much as the steps
  return k <= cap ? k : (span - cap * geo.nodeW) / gaps;  // past cap the boxes stop and the steps go on
}
/* A geometry with its steps spread k times across: the boxes widen with the steps, up to BOX_GROW times (their title and
   description lines with them), and the gap between steps takes the rest, so fewer steps across give each box more
   room without making it a bar the width of the screen. The boxes grow whole, text and all (scale): as wide and as tall
   by the same factor, their lines wrapping as at 1x. */
const spreadGeo = (geo, k, cap = BOX_GROW) => {
  if (k === 1) return geo;
  const nodeW = Math.round(geo.nodeW * Math.max(1, Math.min(k, cap)));
  return { ...geo, nodeW, colGap: Math.round((geo.nodeW + geo.colGap) * k - nodeW), scale: nodeW / geo.nodeW };
};
/* A box's place and size on the map: moved to x, y and drawn scale times its own size (spreadGeo). */
const boxTransform = (n, scale = 1, px = false) => {  // px: the CSS form, with units (a style transform animates)
  const u = px ? "px" : "";
  return `translate(${n.x.toFixed(1)}${u},${n.y.toFixed(1)}${u})${scale !== 1 || px ? ` scale(${scale.toFixed(4)})` : ""}`;
};
/* Where a box glides from after a Steps layout: its screen rect b ({left, top, width}) before, in drawing units through
   the map's screen matrix m ({a, d, e, f}), and the scale its own width own fills that rect at. */
const settleFrom = (b, m, own) => ({ x: (b.left - m.e) / m.a, y: (b.top - m.f) / m.d, k: b.width / m.a / own });

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

function titleLines(n, geo = WIDE) {
  const status = n.status || "live";
  const lines = wrap(n.label + (status === "live" ? "" : `  [${status}]`), geo.titleWrap);
  return lines.length ? lines : [""];
}

function nodeHeight(n, geo = WIDE) {
  return (8 + 16 * titleLines(n, geo).length + (n.path ? 15 : 0) + 13 * wrap(n.desc, geo.descWrap || WRAP).length + 10) * (geo.scale || 1);
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
   turned round); the lanes (bands) with y and h; and the drawing's width and height. aspect (height over width of
   the screen area the map is fitted to, 0 for none) stretches the drawing downward to that shape when it would
   otherwise leave an empty band under its last lane at Fit: the lanes share the spare height evenly and their boxes
   spread out over it; a domain marked thin (a lane closed to one box) takes no share while another lane can. geo is
   the column geometry (WIDE or NARROW). */
function layout(nodes, edges, domains, aspect = 0, geo = WIDE) {
  const NODE_W = geo.nodeW, COL_GAP = geo.colGap;
  if (!nodes.length) return { nodes: [], edges: [], bands: [], width: NODE_W, height: 200, geo };
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
  const heights = new Map(ids.map(v => [v, nodeHeight(byId.get(v), geo)]));
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
  const drawW = nRanks * (NODE_W + COL_GAP) - COL_GAP;
  let totalH = y;
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

  // level: each long link's waypoints (one per column it crosses) are set to one height for as long a run of columns
  // as the boxes and links beside them allow, longest links first, so a long link runs straight across the steps
  // instead of bending at each one. A run next to an end of the link takes that box's height when it can.
  const slotOf = new Map();  // waypoint -> [its column's items in its lane, in order, and its index there]
  layers.forEach(l => {
    const byLane = new Map();
    l.forEach(v => getList(byLane, domain(v)).push(v));
    byLane.forEach(col => col.forEach((v, i) => slotOf.set(v, [col, i])));
  });
  const slot = v => {  // the tops v can take without passing the items above and below it
    const [col, i] = slotOf.get(v), d = domain(v);
    const lo = i === 0 ? bandTop.get(d) + BAND_PAD : ys.get(col[i - 1]) + room(col[i - 1]);
    const hi = i === col.length - 1 ? bandTop.get(d) + bandH.get(d) - BAND_PAD - height(v) : ys.get(col[i + 1]) - room(v);
    return [lo, hi];
  };
  const runsOf = chains.map(([, c]) => c).filter(c => c.length > 3).sort((a, b) => b.length - a.length);
  // a few passes: a link levelled later can free room for one levelled earlier; stops once a pass moves nothing
  for (let pass = 0, moved = true; pass < 6 && moved; pass++) for (const c of (moved = false, runsOf)) {
    const way = c.slice(1, -1);
    for (let start = 0; start < way.length;) {
      let [lo, hi] = slot(way[start]), end = start + 1;
      while (end < way.length) {
        const [l2, h2] = slot(way[end]);
        if (Math.max(lo, l2) > Math.min(hi, h2)) break;
        lo = Math.max(lo, l2); hi = Math.min(hi, h2); end++;
      }
      if (end - start > 1) {
        const run = way.slice(start, end), tops = run.map(v => ys.get(v)).sort((a, b) => a - b);
        const fits = t => t >= lo && t <= hi;
        const atA = centre(c[0]) - DUMMY_H / 2, atB = centre(c[c.length - 1]) - DUMMY_H / 2;
        const top = start === 0 && fits(atA) ? atA : end === way.length && fits(atB) ? atB : Math.min(Math.max(tops[tops.length >> 1], lo), hi);
        run.forEach(v => { if (Math.abs(ys.get(v) - top) > 0.01) { ys.set(v, top); moved = true; } });
      }
      start = end;
    }
  }

  // stretch: a drawing shorter than the screen's shape at Fit is stretched downward lane by lane, each lane getting an
  // equal share of the spare height. Box centres move apart in proportion and boxes keep their size, so each lane's
  // boxes spread over its new height, centred as they were, and no two come closer.
  const shown = domains.filter(d => bandH.get(d.id));
  const spare = aspect > 0 && shown.length ? (drawW + LEFT + 60) * aspect - totalH : 0;  // the page's W is drawW + LEFT + 60
  if (spare > 0) {
    const was = new Map(shown.map(d => [d.id, [bandTop.get(d.id), bandH.get(d.id)]]));
    let top = 0;
    const grow = shown.some(d => !d.thin) ? shown.filter(d => !d.thin) : shown, share = new Set(grow.map(d => d.id));
    for (const d of domains) { bandTop.set(d.id, top); if (share.has(d.id)) bandH.set(d.id, bandH.get(d.id) + spare / grow.length); top += bandH.get(d.id); }
    totalH = top;
    for (const [v, vy] of ys) {
      const d = domain(v), [t0, h0] = was.get(d), c = vy + height(v) / 2;
      ys.set(v, bandTop.get(d) + (c - t0) * bandH.get(d) / h0 - height(v) / 2);
    }
  }

  const xOf = v => rank.get(v) * (NODE_W + COL_GAP);
  const outNodes = nodes.map(n => ({ ...n, x: xOf(n.id), y: ys.get(n.id), w: NODE_W, h: height(n.id) }));
  const outEdges = chains.map(([i, chain, flipped]) => {
    const pts = [];
    chain.forEach((v, j) => {
      // a waypoint runs level through its column, in the slot kept for it, and bends only in the gaps between
      // columns, so a link never crosses a box (the levelling above keeps those bends few)
      if (byId.has(v)) pts.push([j === 0 ? xOf(v) + NODE_W : xOf(v), centre(v)]);
      else { pts.push([xOf(v), centre(v)]); pts.push([xOf(v) + NODE_W, centre(v)]); }
    });
    if (flipped) pts.reverse();
    return { ...edges[i], pts, back: flipped };
  });
  const bands = domains.filter(d => bandH.get(d.id)).map(d => ({ ...d, y: bandTop.get(d.id), h: bandH.get(d.id) }));
  return { nodes: outNodes, edges: outEdges, bands, columns: nRanks, width: drawW, height: totalH, geo };
}

/* The step headers over the columns in view: column r is r links from a file nothing on the map builds (step 0). px is
   how many screen pixels one drawing unit takes; when the columns are too narrow for every number, only every 2nd, 5th,
   10th or 20th is named, always with step 0. Returns {every, cols: [{r, x}]}, x the column's middle in drawing units. */
/* Whether column 0 of a drawing is raw data: it has boxes and nothing in the whole graph (edges, every link, filtered
   or not) builds any of them. A filtered view can hide what builds its first column, and a folder box (unknown id)
   stands for files that may be built, so either makes it plain "Step 0". */
function firstColumnIsRaw(layNodes, edges, known, geo = WIDE) {
  const step = stepOf(geo), fed = new Set(edges.map(e => e.to));
  const first = layNodes.filter(n => Math.round(n.x / step) === 0);
  return first.length > 0 && first.every(n => known(n.id) && !fed.has(n.id));
}

function stepTicks(columns, x0, x1, px, geo = WIDE) {
  const step = stepOf(geo), wide = step * px;
  const every = [1, 2, 5, 10, 20, 50].find(k => k * wide >= 64) || 100;
  const cols = [];
  for (let r = 0; r < columns; r += every) {
    const x = r * step + geo.nodeW / 2;
    if (x >= x0 - step && x <= x1 + step) cols.push({ r, x });
  }
  return { every, cols };
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { ...require("./pipeline_map_helpers.js"), settleFrom, boxTransform, BOX_GROW, spreadFor, spreadGeo, WIDE, NARROW, layout, wrap, nodeHeight, inversions, stepTicks, firstColumnIsRaw };
}
