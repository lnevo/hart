/* Layout and viewer for docs/pipeline-map/index.html. build_pipeline_map.py inlines this file into the page after the
   graph data (DATA). The layout is a layered (Sugiyama) drawing, left to right, with one horizontal lane per domain; it
   runs in the page so any subset (some lanes, or the chain around one file) gets its own compact drawing. Under node
   the file only exports the layout, for the unit tests. */
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
   spread out over it. geo is the column geometry (WIDE or NARROW). */
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
    for (const d of domains) { bandTop.set(d.id, top); if (bandH.get(d.id)) bandH.set(d.id, bandH.get(d.id) + spare / shown.length); top += bandH.get(d.id); }
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

/* Where the pinned lane name tags go, in screen px: lanes holds each lane's [top, bottom] on screen, floor is the
   first y under the step strip, bottom the end of the free area, and under the top of the legend beside the tags
   (Infinity when it is not there). A tag sits 6 px into its lane, or higher to stay above the legend; a lane with no
   room for the whole tag gets none. When the legend reaches up near the strip it is ignored, rather than hiding every
   lane name. Returns one y per lane, null for a lane left without a tag. */
const TAG_H = 22;
function laneTagTops(lanes, floor, bottom, under) {
  const clip = under > floor + TAG_H ? under : Infinity;
  return lanes.map(([y0, y1]) => {
    const y = Math.min(Math.max(y0 + 6, floor), Math.min(y1, bottom, clip) - TAG_H);
    return y < Math.max(y0 + 2, floor) ? null : y;  // out of view, behind the legend, or too thin on screen
  });
}

/* The note shown by the pointer over a link e ({from, to, label, back}): both ends' names (name(id) gives a box's
   label) and the link's label, escaped. */
function edgeTip(e, name) {
  const h = t => String(t).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  return `<b>${h(name(e.from))}</b> → <b>${h(name(e.to))}</b>` + (e.label ? `<div>${h(e.label)}</div>` : "") +
    (e.back ? '<div class="off">feeds back to an earlier step</div>' : "");
}

/* What a click on the map does, given what is under it: box (a box's id, or null), card (the grown box the pointer
   picks, pointerPick, when no box is drawn under it, or null), line (the id of the box a clicked line leads to, or null) and
   lineFirst (a tap, whose hover grew the cards just before it, or a Cmd-click, which asks for the line itself). A box
   wins, then a grown card (what a mouse user sees there), then the line; with lineFirst the line beats a card. Returns
   {pick: id, line: true when it came from a line} or {clear: true}. */
function clickTarget(box, card, line, lineFirst = false) {
  if (box) return { pick: box };
  if (line && (lineFirst || !card)) return { pick: line, line: true };
  if (card) return { pick: card };
  return { clear: true };
}

/* What the pointer is over on the map, from what is at its place (each an id, a line index, or null): box (a box drawn
   under it), spot (a grown box whose drawn spot holds it), own (the hovered box, when its grown card holds it),
   hovered (the hovered line, when it is under the pointer), card (the topmost grown card over it), line (a line under
   it). A box drawn there wins, so moving along a row reaches each box, also those a card covers; then a grown box's
   spot (often the next box along a row); then the hovered box's own card; then the hovered line, while on it; then a
   grown card (drawn over the lines); then a line. Returns {box}, {edge} or {}. Hover and click both use it. */
function pointerPick(c) {
  for (const k of ["box", "spot", "own"]) if (c[k]) return { box: c[k] };
  if (c.hovered !== null && c.hovered !== undefined) return { edge: c.hovered };
  if (c.card) return { box: c.card };
  if (c.line !== null && c.line !== undefined) return { edge: c.line };
  return {};
}

/* What is hidden after an "only" beside k is clicked, for kinds or lanes: everything in all (kind or lane ids) but k (off: what is hidden
   now). A second click on the one already shown alone shows them all again. */
function onlyOne(all, off, k) {
  const alone = all.every(x => x === k || off.includes(x)) && !off.includes(k);
  return alone ? [] : all.filter(x => x !== k);
}

/* The id of the first box in boxes ({id, x, y, w, h}) that holds the point x, y, or null. */
function boxAt(boxes, x, y) {
  const b = boxes.find(n => x >= n.x && x <= n.x + n.w && y >= n.y && y <= n.y + n.h);
  return b ? b.id : null;
}

/* Whether a click e asks for a line's source: Cmd or Alt held, or Ctrl off a Mac (a Mac turns Ctrl-click into a right
   click, so no click arrives); Shift is the magnifier. */
function sourceClick(e) {
  return !!(e.metaKey || e.ctrlKey || e.altKey);
}

/* The key the hover note names for that click on this platform: Cmd on a Mac (Ctrl-click is its right click), else Ctrl. */
function sourceKey(platform) {
  return /Mac|iPhone|iPad/.test(platform || "") ? "Cmd" : "Ctrl";
}

/* The box a click on a line opens: where it leads, or with source (sourceClick) where it comes from; null when that box is not drawn
   (drawn(id) is false). */
function lineEnd(edge, source, drawn) {
  const id = source ? edge.from : edge.to;
  return drawn(id) ? id : null;
}

/* Where a box grown about its middle (cx, cy, half sizes hw, hh, all screen px) goes: moved in by dx, dy to stay whole
   inside area ({left, top, right, bottom}), the hovered box too (its drawn spot keeps the hover, pointerPick, so its
   card need not stay under the pointer). Returns its rect with a 2 px margin and the move. */
function growRect(cx, cy, hw, hh, area) {
  const inside = (c, h, lo, hi) => Math.min(Math.max(c, lo + h), Math.max(hi - h, lo + h)) - c;
  const dx = inside(cx, hw + 4, area.left, area.right), dy = inside(cy, hh + 4, area.top, area.bottom);
  return { x0: cx + dx - hw - 2, y0: cy + dy - hh - 2, x1: cx + dx + hw + 2, y1: cy + dy + hh + 2, dx, dy };
}

/* A grown rect b (from growRect) moved the least way clear of the blocked rects (the lane names and the legend), staying
   inside area: right past one, or above or below it; up to four moves, then as it is. For the hovered box, which must
   show even where it starts under a lane name. */
function clearOf(b, blocked, area) {
  const hit = r => blocked.find(o => o.x0 < r.x1 && r.x0 < o.x1 && o.y0 < r.y1 && r.y0 < o.y1);
  const move = (r, mx, my) => ({ x0: r.x0 + mx, y0: r.y0 + my, x1: r.x1 + mx, y1: r.y1 + my, dx: r.dx + mx, dy: r.dy + my });
  const fits = r => r.x0 >= area.left && r.x1 <= area.right && r.y0 >= area.top && r.y1 <= area.bottom;
  let r = b;
  for (let i = 0; i < 4; i++) {
    const o = hit(r);
    if (!o) return r;
    const ways = [move(r, o.x1 + 1 - r.x0, 0), move(r, 0, o.y0 - 1 - r.y1), move(r, 0, o.y1 + 1 - r.y0)].filter(fits);
    if (!ways.length) return r;
    ways.sort((p, q) => Math.hypot(p.dx - r.dx, p.dy - r.dy) - Math.hypot(q.dx - r.dx, q.dy - r.dy));
    r = ways[0];
  }
  return r;
}

/* A link's drawn shape from its layout points: a straight piece where the height stays the same, otherwise an S-bend
   with level ends between the two points. Each segment is [from, control1, control2, to], the controls null for a
   straight piece. */
function pathSegments(pts) {
  const out = [];
  for (let i = 1; i < pts.length; i++) {
    const [px, py] = pts[i - 1], [x, y] = pts[i], mx = (px + x) / 2;
    out.push(Math.abs(y - py) < 0.5 ? [pts[i - 1], null, null, pts[i]] : [pts[i - 1], [mx, py], [mx, y], pts[i]]);
  }
  return out;
}

/* The room the step strip takes above the map, in px: none while the extras are hidden (clean) or the drawing has no
   boxes. */
const STRIP_H = 24;
function stripRoom(clean, boxes) { return clean || !boxes ? 0 : STRIP_H + 4; }

/* A #rrggbb colour halfway to white, for text in that colour on a dark background; any other value is returned as is. */
function lighten(c) {
  if (!/^#[0-9a-f]{6}$/i.test(c)) return c;
  const mix = i => Math.round(parseInt(c.slice(i, i + 2), 16) * 0.5 + 255 * 0.5).toString(16).padStart(2, "0");
  return "#" + mix(1) + mix(3) + mix(5);
}

/* Greedy label placement: boxes ({x0, y0, x1, y1}, screen px) in order of priority; each is placed unless it overlaps
   one already placed or one of blocked (areas covered by something else). Returns the indexes placed. */
function placeTags(boxes, blocked = []) {
  const CELL = 64, grid = new Map(), placed = [];
  const cells = (b, f) => {
    for (let i = Math.floor(b.x0 / CELL); i <= Math.floor(b.x1 / CELL); i++)
      for (let j = Math.floor(b.y0 / CELL); j <= Math.floor(b.y1 / CELL); j++) f(i + "," + j);
  };
  const keep = b => cells(b, k => { if (!grid.has(k)) grid.set(k, []); grid.get(k).push(b); });
  blocked.forEach(keep);
  boxes.forEach((b, i) => {
    let clash = false;
    cells(b, k => { if (!clash) clash = (grid.get(k) || []).some(o => o.x0 < b.x1 && b.x0 < o.x1 && o.y0 < b.y1 && b.y0 < o.y1); });
    if (!clash) { keep(b); placed.push(i); }
  });
  return placed;
}

/* What a click on id lights up in a drawing of these edges: every box that feeds it (up) and every box it feeds
   (down), not walking on through a box where stops(box) is true, and the links inside one side (lit). steps maps
   each box of a side to its fewest links from id (upSteps, downSteps). */
function chainOf(edges, id, stops) {
  const walk = (key, other) => {
    const seen = new Map([[id, 0]]);
    let frontier = [id], k = 0;
    while (frontier.length) {
      const next = [];
      k++;
      for (const v of frontier) {
        if (v !== id && stops(v)) continue;
        for (const e of edges) if (e[other] === v && !seen.has(e[key])) { seen.set(e[key], k); next.push(e[key]); }
      }
      frontier = next;
    }
    return seen;
  };
  const upSteps = walk("from", "to"), downSteps = walk("to", "from");
  const up = new Set(upSteps.keys()), down = new Set(downSteps.keys());
  return { up, down, upSteps, downSteps, lit: e => (up.has(e.from) && up.has(e.to)) || (down.has(e.from) && down.has(e.to)) };
}

/* Whether box n is a cache or stamp store under .cache/: it saves time, it does not feed content, so a chain does
   not run on through it (a builder that reads it gives the same result without it). */
function isCache(n) {
  return !!n && [n.label, n.path].some(t => /(^|[\/\s])\.cache\//.test(t || ""));
}

/* Whether a chain stops at box n: the hosts lane (deploy, hosts, runtime apps), host and hand-work boxes, and caches.
   Runner boxes ("runner": true, such as check.sh) stop only a hovered line's chain (hoverStop). */
function stopsChain(n) {
  return !!n && (n.domain === "hosts" || n.kind === "host" || n.kind === "human" || isCache(n));
}

/* The hub boxes of a map: those at least min links go out of and at least one comes into, such as tables.xml or
   devices_generated.csv, where many pipelines meet. A hovered line's chain shows a hub but does not run on through
   it, or the line into it would light most of the map; a click still traces the full reach. */
const HUB_OUT = 6;
function hubs(edges, min = HUB_OUT) {
  const outs = new Map(), fed = new Set();  // the distinct boxes each box feeds; a link to itself counts for nothing
  edges.forEach(e => {
    if (e.from === e.to) return;
    if (!outs.has(e.from)) outs.set(e.from, new Set());
    outs.get(e.from).add(e.to); fed.add(e.to);
  });
  return new Set([...outs].filter(([id, to]) => to.size >= min && fed.has(id)).map(([id]) => id));
}

/* The hubs of the live map in data ({nodes, edges}): parked and retired boxes and their links left out, so filters
   do not move them. */
function liveHubs(data) {
  const live = new Set(data.nodes.filter(n => !n.status || n.status === "live").map(n => n.id));
  return hubs(data.edges.filter(e => live.has(e.from) && live.has(e.to)));
}

/* Whether a hovered line's chain stops at box n (hubs: liveHubs): where any chain stops (stopsChain), a hub, or a
   runner ("runner": true, such as check.sh, which only runs other steps). */
function hoverStop(n, hubSet) {
  return !!n && (stopsChain(n) || hubSet.has(n.id) || !!n.runner);
}

/* Why a chain stops at box n (hubs: liveHubs), as the hover note names it: "runner", "cache", "hub", "host" (the
   hosts lane and host boxes) or "hand work"; null when it does not stop there. */
function stopKind(n, hubSet) {
  if (!n) return null;
  if (n.runner) return "runner";
  if (isCache(n)) return "cache";
  if (n.kind === "human") return "hand work";
  if (n.domain === "hosts" || n.kind === "host") return "host";
  return hubSet.has(n.id) ? "hub" : null;
}

/* The hover note's line naming where a hovered line's chain stopped: the stop boxes it lit (stops: [name, kind]),
   escaped, at most four by name and a count of the rest; "" when none. */
function stopsNote(stops) {
  if (!stops.length) return "";
  const h = t => String(t).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const named = stops.slice(0, 4).map(([name, kind]) => `${h(name)} (${kind})`).join(", ");
  return `<div class="off">stops at ${named}${stops.length > 4 ? ` and ${stops.length - 4} more` : ""}</div>`;
}

/* Whether a hovered line's chain walks link e: not a side link ("side": a check's read, a doc pointer, a Store pull
   back into the sources, a folder mirror, a page capture, git history), which carries no content on, nor one
   bridged over a hidden box where it would stop (stopAt(id) true for one of e.via). */
function hoverWalks(e, stopAt) {
  return !e.side && !(e.via || []).some(stopAt);
}

/* The chain one link from -> to belongs to: everything that feeds from and everything to feeds (chainOf, not
   walking on through a box where stops(box) is true, an end of the link included: a line out of a host does not
   light everything deployed to it), and the links inside it (lit). */
function linkChain(edges, from, to, stops) {
  const upSteps = stops(from) ? new Map([[from, 0]]) : chainOf(edges, from, stops).upSteps;
  const downSteps = stops(to) ? new Map([[to, 0]]) : chainOf(edges, to, stops).downSteps;
  const up = new Set(upSteps.keys()), down = new Set(downSteps.keys());
  const lit = e => (e.from === from && e.to === to) || (up.has(e.from) && up.has(e.to)) || (down.has(e.from) && down.has(e.to));
  // steps: each box's fewest links from the nearer end of the line (its ends 0), for the fade with distance
  const steps = new Map(upSteps);
  downSteps.forEach((k, v) => steps.set(v, Math.min(k, steps.has(v) ? steps.get(v) : k)));
  return { boxes: new Set([...up, ...down]), lit, steps };
}

/* How faint a box or link steps links from a hovered line shows: "" (full) up to 2, "2" for 3 and 4, "3" beyond. */
function fadeOf(steps) {
  return steps <= 2 ? "" : steps <= 4 ? "2" : "3";
}

/* The free area is the part of the screen the reader can see the map in: below the toolbar and clear of the info
   panel. free gives it as shares of the map's width and height: {top, right, bottom}, each 0 to 1. */

/* Whether the view v (a viewBox) shows the whole drawing (x from -left, width W, height H) inside the free area;
   the corner overview hides while it does. */
function showsAll(v, W, H, left, free) {
  const top = v.y + free.top * v.height, bottom = v.y + free.bottom * v.height, right = v.x + free.right * v.width;
  return v.x <= -left + 1 && top <= 1 && right >= W - left - 1 && bottom >= H - 1;
}

/* The viewBox that fits the whole drawing into the free area, for a map of sw x sh px, with pad px of margin on each
   side: centred across, and pad below the top of the area (the step strip) so a wide drawing leaves no larger band
   above its first lane. */
/* The margin fitView keeps, in px: pad, but at most a quarter of the free area's width or height, so a small map
   (a phone with the info panel open) keeps most of its room. */
function fitPad(pad, free, sw, sh) {
  return Math.max(0, Math.min(pad, (free.right * sw) / 4, ((free.bottom - free.top) * sh) / 4));
}

function fitView(W, H, left, free, sw, sh, pad = 0) {
  const top = free.top * sh;
  const p = fitPad(pad, free, sw, sh);
  const w = Math.max(free.right * sw - 2 * p, 1), h = Math.max(free.bottom * sh - top - 2 * p, 1);
  const s = Math.max(W / w, H / h);
  const ox = p + (w - W / s) / 2, oy = top + p;  // where the drawing's top left lands, in px
  return { x: -left - ox * s, y: -oy * s, width: sw * s, height: sh * s };  // the viewBox's own field names
}

/* The view v kept on the drawing: no wider than maxW (the Fit width), and placed so the drawing (x from -left, width
   W; y from 0, height H) does not leave the free area at any side: across, left of the info panel; down, between
   the step strip and the bottom (or the panel, on a phone). A drawing bigger than the free area covers it edge to
   edge; a smaller one stays wholly inside it. The height follows the width, and a view cut to maxW keeps its middle. */
function clampView(v, W, H, left, free, maxW, padX = 0, padY = 0) {
  if (!(v.width > 0) || !(v.height > 0)) return v;  // a view with no size (a hidden map) is left alone
  const width = Math.min(v.width, maxW), height = v.height * width / v.width;
  const x0 = v.x + (v.width - width) / 2, y0 = v.y + (v.height - height) / 2;  // a cut width shrinks about the middle
  const between = (t, a, b) => Math.min(Math.max(t, Math.min(a, b)), Math.max(a, b));
  // the view's x with the drawing's left, or right, edge on the area's; and its y with the top, or bottom, on the area's
  // padX, padY: the margin kept inside the area, as shares of the view's width and height (fitPad), so at the Fit
  // width the drawing cannot be dragged into it
  const mx = padX * width, my = padY * height;
  const x = between(x0, -left - mx, W - left - free.right * width + mx);
  const y = between(y0, -free.top * height - my, H - free.bottom * height + my);
  return { x, y, width, height };
}

/* The graph with the boxes hide(id) is true for taken away: those drop(id) is also true for (where chains stop: the
   hosts lane, host, hand-work and cache boxes) are left out with their links, since bridging over a deploy script would
   link its every input to every host; the rest are bridged over (contract). */
function hideBoxes(nodes, edges, hide, drop) {
  const kept = nodes.filter(n => !(hide(n.id) && drop(n.id))), ids = new Set(kept.map(n => n.id));
  return contract(kept, edges.filter(e => ids.has(e.from) && ids.has(e.to)), hide);
}

/* The graph with the boxes hide(id) is true for taken out and bridged over: each link into a hidden box is joined to
   every shown box beyond it, through any run of hidden boxes, and the new link keeps the hidden boxes in via. So
   with the scripts hidden, a data file links straight to what it ends up in. */
function contract(nodes, edges, hide) {
  const outs = {};
  edges.forEach(e => (outs[e.from] ||= []).push(e));
  const kept = nodes.filter(n => !hide(n.id)), out = [], seen = new Set();
  // a link keeps its side; a bridged one is a side link when any hop on it is (content does not cross that hop)
  const add = (from, to, label, via, side) => {
    const key = from + "\u0000" + to;
    if (from === to || seen.has(key)) return;
    seen.add(key);
    const e = via.length ? { from, to, via } : (label ? { from, to, label } : { from, to });
    if (side) e.side = side;
    out.push(e);
  };
  for (const n of kept) {
    for (const e of outs[n.id] || []) if (!hide(e.to)) add(n.id, e.to, e.label, [], e.side);  // direct links win
    for (const e of outs[n.id] || []) {
      if (!hide(e.to)) continue;
      const stack = [[e.to, [e.to], e.side]], visited = new Set([e.to]);  // depth first through hidden boxes
      while (stack.length) {
        const [v, via, side] = stack.pop();
        for (const f of outs[v] || []) {
          if (!hide(f.to)) add(n.id, f.to, "", via, side || f.side);
          else if (!visited.has(f.to)) { visited.add(f.to); stack.push([f.to, via.concat(f.to), side || f.side]); }
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
    out.push({ id, folder: f, label: f.startsWith("outside") ? f : f === "top level" ? "repository root" : f + "/", kind: "folder", status: "live", domain,
               desc: `${list.length} boxes`, path: "" });
  }
  const merged = new Map();
  for (const e of edges) {
    const from = groupOf[e.from] || e.from, to = groupOf[e.to] || e.to;
    if (from === to) continue;
    const key = from + "\u0000" + to;
    if (!merged.has(key)) merged.set(key, { from, to, n: 0, label: e.label, side: e.side });
    const m = merged.get(key);
    m.n++;
    if (!e.side) m.side = undefined;  // a merged link is a side link only when every link in it is
  }
  const outEdges = [...merged.values()].map(m => {
    const grouped = groupOf[m.from] || groupOf[m.to] || m.from.startsWith("folder:") || m.to.startsWith("folder:");
    const label = m.n > 1 ? `${m.n} links` : grouped ? "" : m.label;
    const e = label ? { from: m.from, to: m.to, label } : { from: m.from, to: m.to };
    if (m.side) e.side = m.side;
    return e;
  });
  return { nodes: out, edges: outEdges, members, groupOf };
}

/* The box's file on GitHub, or "" for a box with no path or one outside the tracked files (a gitignored mirror or a
   host). links maps "" to this repository's base and each submodule path to its own repository's base; a path inside
   a submodule goes to that repository, and the submodule itself to its root. Folders open too: GitHub sends /blob/ on
   to /tree/. This repository's links go to main, so a file added on an unmerged branch has no page yet. */
function githubUrl(n, links) {
  if (!n.path || n.local || !links) return "";
  const enc = p => p.split("/").map(encodeURIComponent).join("/");
  const sub = Object.keys(links).filter(k => k && (n.path === k || n.path.startsWith(k + "/")))
    .sort((a, b) => b.length - a.length)[0];
  if (sub === undefined) return links[""] ? links[""] + enc(n.path) : "";
  const rest = n.path.slice(sub.length + 1);
  return rest ? links[sub] + enc(rest) : links[sub].replace(/\/blob\/[^/]+\/$/, "");
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { settleFrom, boxTransform, BOX_GROW, spreadFor, spreadGeo, onlyOne, stopKind, stopsNote, fitPad, clearOf, pointerPick, boxAt, hoverStop, hoverWalks, fadeOf, sourceClick, sourceKey, isCache, stopsChain, hubs, liveHubs, HUB_OUT, WIDE, NARROW, lineEnd, lighten, stripRoom, pathSegments, clickTarget, growRect, placeTags, edgeTip, linkChain, layout, wrap, nodeHeight, inversions, stepTicks, laneTagTops, firstColumnIsRaw, chainOf, showsAll, fitView, clampView, contract, hideBoxes, folderOf, groupByFolder, githubUrl };
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
                 kindsOff: new Set(), compact: true, group: false, open: new Set(), hover: true, near: false, steps: 0, spread: 1 };
  let groups = { members: {}, groupOf: {} }, gNodes = {}, lastBox = null;  // folder boxes in the current drawing; the last file box picked
  const nodeOf = id => byId[id] || gNodes[id];
  let selected = null, lay = null, svg = null, vb = null, W = 0, H = 0;
  let nodeEl = {}, edgeEls = [], sub = { nodes: [], edges: [] }, visible = new Set(), baseIds = new Set();

  /* ---- which boxes are shown */
  /* A chain is drawn through boxes but stops at deploy, hosts and runtime apps (the "hosts" lane) and at hand work:
     they are shown, not walked through, because everything deploys and the Pi's saved state comes back, so walking
     through them would reach most of the map. A chain also stops at a cache (isCache): it only saves time, so what
     reads it does not depend on what wrote it. */
  const endsChain = id => stopsChain(nodeOf(id));
  /* The hubs of the live map (liveHubs), where a hovered line's chain stops too; worked out once, so filters do not move
     them. A closed folder holding a hub is a hub, and a link bridged over a hidden hub (its via) is not walked. */
  const hubSet = liveHubs(DATA);
  /* A hovered line's chain also stops at runner boxes ("runner": true: check.sh, build_panels.sh, which only run other
     steps) and does not walk side links ("side": a check's read, a doc pointer, a Store pull back into the sources, a
     folder mirror, a page capture, git history), which carry no content on to the next step. */
  const isHub = id => hoverStop(nodeOf(id), hubSet);
  const endsHover = id => isHub(id) || (groups.members[id] || []).some(isHub);
  const overHub = e => !hoverWalks(e, isHub);
  // whether the lane filter draws a box (status and kind are applied in filtered()); the picked file always shows
  const isShown = id => id === view.focus || view.lanes.has(nodeOf(id).domain);
  /* The graph after the status and kind filters: parked and retired boxes are left out, and boxes of a hidden kind
     are bridged over, so the links run on through them, except where chains stop (endsChain: the hosts lane, host,
     hand-work and cache boxes), which are left out with their links (hideBoxes). The picked file always stays. */
  const dropKind = k => k === "host" || k === "human";  // kinds whose every box is a chain stop
  let g1Key = null, g1 = null, ins1 = {}, outs1 = {};
  function filtered() {
    const key = JSON.stringify([view.parked, view.retired, [...view.kindsOff].sort(), view.focus]);
    if (key === g1Key) return g1;
    const ok = n => n.id === view.focus || !n.status || n.status === "live" || view[n.status];
    const nodes = DATA.nodes.filter(ok), ids = new Set(nodes.map(n => n.id));
    const edges = DATA.edges.filter(e => ids.has(e.from) && ids.has(e.to));
    g1 = !view.kindsOff.size ? { nodes, edges }
      : hideBoxes(nodes, edges, id => id !== view.focus && view.kindsOff.has(byId[id].kind), endsChain);
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
      nodes.forEach(n => { if (n.kind === "folder" && !n.path && n.folder.startsWith("outside the repo: ")) n.label = "outside the repo: " + domainLabel[n.folder.slice(18)]; });
    }
    if (view.compact) nodes = nodes.map(n => (n.kind === "folder" ? n : { ...n, desc: "", path: "" }));
    baseIds = new Set(nodes.map(n => n.id));  // what the filters draw before "highlighted only" trims it
    return trimmed() && baseIds.has(selected) ? { ...chainOnly(nodes, edges, selected), trim: true } : { nodes, edges };
  }
  const trimmed = () => view.trim && selected !== null;
  /* A click lights everything up and downstream (endsChain stops only at hosts, hand work and caches); with View, near
     pipeline on click (view.near), it stops where a hover does: hubs and runners, and not across side links. */
  const chain = (edges, id) => (view.near ? chainOf(edges.filter(e => !overHub(e)), id, endsHover) : chainOf(edges, id, endsChain));
  function chainOnly(nodes, edges, id) {  // "highlighted only": drop what the selection leaves dim
    const c = chain(edges, id);
    return { nodes: nodes.filter(n => c.up.has(n.id) || c.down.has(n.id)), edges: edges.filter(e => c.lit(e) && !(view.near && overHub(e))) };
  }

  /* ---- drawing */
  function pathD(pts) {
    const f = v => v.toFixed(1), segs = pathSegments(pts), d = [`M${f(pts[0][0])},${f(pts[0][1])}`];
    for (const [, c1, c2, q] of segs) d.push(c1 ? `C${f(c1[0])},${f(c1[1])} ${f(c2[0])},${f(c2[1])} ${f(q[0])},${f(q[1])}` : `L${f(q[0])},${f(q[1])}`);
    return d.join(" ");
  }
  /* ---- zoomed out: below FAR_PX screen px a drawing unit the boxes' text is too small to read. The edges and box
     outlines then keep a fixed screen width, and the boxes a hover lights (a line's chain, or a box and its neighbours)
     grow in place to a readable size, as many as fit without covering each other; the rest of them stay small, lit. */
  const FAR_PX = 0.7, MAG_TITLE_PX = 12;  // a magnified box's title is drawn this big on screen
  let degree = {}, edgesAt = {}, hoverId = null, hoverEnds = new Set(), magnified = new Set();
  let farFrame = 0;
  function updateFar() {  // at most once a frame: a drag or wheel calls it on every event
    if (!farFrame) farFrame = requestAnimationFrame(() => { farFrame = 0; placeFar(); });
  }
  const layNode = {};  // id -> its box in lay, set in render
  function unmagnify(id) {
    const n = layNode[id], g = nodeEl[id];
    if (g && n) { g.setAttribute("transform", boxTransform(n, lay.geo.scale || 1)); g.classList.remove("mag"); }
  }
  function placeFar() {
    if (!svg || svg.classList.contains("settling")) return;  // after a Steps glide (settle calls it again at the end)
    const m = svg.getScreenCTM(), far = !!m && m.a > 0 && m.a < FAR_PX;
    svg.classList.toggle("far", far);
    const want = [];
    // boxes grow while their own text is too small to read: drawn larger (spreadGeo scale), they read at a smaller zoom
    if (far && m.a * ((lay && lay.geo.scale) || 1) < FAR_PX) {
      const r = wrapEl.getBoundingClientRect(), a = freeArea(), s = m.a, k = MAG_TITLE_PX / 13 / s;
      const sx = x => m.a * x + m.e - r.left, sy = y => m.d * y + m.f - r.top;
      // grown: the hovered box or the hovered line's ends, then the rest the hover lights, the selected box and search
      // hits, then the selected box's neighbours (select tags them near), so the boxes a hover grew stay grown after
      // the click; each group busiest first
      const has = (id, c) => nodeEl[id].classList.contains(c);
      const rank = id => (id === hoverId || hoverEnds.has(id) ? 0 : has(id, "hn") ? 1 : has(id, "sel") || has(id, "hit") ? 2 : has(id, "near") ? 3 : 4);
      const lit = lay.nodes.filter(n => rank(n.id) < 4 &&
        sx(n.x + n.w) > 0 && sx(n.x) < a.right && sy(n.y + n.h) > a.top && sy(n.y) < a.bottom);
      const near = id => (hoverSteps && hoverSteps.has(id) ? hoverSteps.get(id) : 0);  // a hovered line's nearer boxes grow first
      lit.sort((p, q) => rank(p.id) - rank(q.id) || near(p.id) - near(q.id) || (degree[q.id] || 0) - (degree[p.id] || 0));
      const area = { left: 0, top: a.top, right: a.right, bottom: a.bottom };
      const sc = lay.geo.scale || 1, kk = Math.max(k, sc);  // a box's own size times kk on the map (drawn sc times already)
      const boxes = lit.map(n => growRect(sx(n.x + n.w / 2), sy(n.y + n.h / 2), n.w / sc * s * kk / 2, n.h / sc * s * kk / 2, area));
      const blocked = [...laneTags.querySelectorAll("span"), legend].map(t => {  // the lane names and the legend sit over the map
        const q = t.getBoundingClientRect();
        return { x0: q.left - r.left, y0: q.top - r.top, x1: q.right - r.left, y1: q.bottom - r.top };
      });
      lit.forEach((n, i) => { if (n.id === hoverId) boxes[i] = clearOf(boxes[i], blocked, area); });  // the hovered box always shows
      for (const i of placeTags(boxes, blocked)) want.push([lit[i], kk, boxes[i].dx / s, boxes[i].dy / s]);
    }
    const now = new Set(want.map(([n]) => n.id));
    magnified.forEach(id => { if (!now.has(id)) unmagnify(id); });
    const top = svg.querySelector("#nodes");
    for (const [n, k, dx, dy] of want) {  // grown about the box's middle, and drawn over the other boxes
      const g = nodeEl[n.id];
      const sc = lay.geo.scale || 1, bw = n.w / sc * k, bh = n.h / sc * k;  // grown about the box's middle
      g.setAttribute("transform", `translate(${(n.x + dx + (n.w - bw) / 2).toFixed(1)},${(n.y + dy + (n.h - bh) / 2).toFixed(1)}) scale(${k.toFixed(3)})`);
      // drawn over the other boxes: moved to the end of the layer once, as it grows (the layer's order is only
      // stacking, so it need not be put back)
      if (!magnified.has(n.id)) top.appendChild(g);
      g.classList.add("mag");
    }
    magnified = now;
  }
  /* Hovering a box lights its own links and the boxes at their other ends, at any zoom, without selecting it. */
  /* Hovering a link (edge: its index in lay.edges) lights the chain it is on (linkChain), up to the hubs, and tags its boxes, the
     two ends first, and a note by the pointer names the ends and the link's label. */
  /* A click on a line with Cmd (Ctrl off a Mac) opens the box it comes from. Alt (Option) works too where the system
     lets it through; some Mac window tools take Option-click for themselves, and Shift is the magnifier. */
  const SOURCE_KEY = sourceKey(navigator.platform || navigator.userAgent);
  const etip = document.createElement("div");
  etip.id = "etip"; etip.className = "panel"; etip.hidden = true; document.getElementById("stage").append(etip);
  let hoverEdge = null, hoverSteps = null;  // the hovered line and its boxes' steps from it
  function placeTip() {
    if (etip.hidden || !ptr) return;
    const w = etip.offsetWidth, h = etip.offsetHeight;
    etip.style.left = `${Math.min(ptr.x + 14, innerWidth - w - 8)}px`;
    etip.style.top = `${ptr.y + 18 + h > innerHeight - 8 ? ptr.y - h - 12 : ptr.y + 18}px`;
  }
  function setEdgeHover(i) {
    if (i === hoverEdge || !svg) return;
    if (hoverId) setHover(null);
    svg.querySelectorAll(".he,.hn").forEach(el => el.classList.remove("he", "hn", "he2", "he3", "hn2", "hn3"));
    const e = i === null ? null : lay.edges[i];
    hoverEdge = e ? i : null; hoverSteps = null;
    svg.classList.toggle("hovering", !!e);
    etip.hidden = !e;
    hoverEnds = new Set(e ? [e.from, e.to] : []);
    if (e) {  // the whole chain the line is on: what feeds its start and what its end feeds
      // a side link carries nothing from its start, so hovering one lights its start alone on that side
      const c = linkChain(sub.edges.filter(x => !overHub(x)), e.from, e.to, id => endsHover(id) || (!!e.side && id === e.from));  // stops at hubs too: a hover shows the line's own pipeline
      // nearer boxes and links show fully, further ones fainter (fadeOf): a link takes its further end's distance
      const fade = v => fadeOf(c.steps.get(v) || 0);
      hoverSteps = c.steps;
      edgeEls.forEach(el => {
        const f = el.dataset.from, t = el.dataset.to;
        if (!c.lit({ from: f, to: t })) return;
        el.classList.add("he");
        const k = fadeOf(Math.max(c.steps.get(f) || 0, c.steps.get(t) || 0));
        if (k) el.classList.add("he" + k);
      });
      edgeEls[i].classList.remove("he2", "he3");
      edgeEls[i].classList.add("he");
      c.boxes.forEach(v => { if (!nodeEl[v]) return; nodeEl[v].classList.add("hn"); if (fade(v)) nodeEl[v].classList.add("hn" + fade(v)); });
      // the boxes it stopped at, the line's own ends included (not the start of a side link, which stops by its link);
      // a closed folder takes the reason of the first box in it that stops
      const kindOf = v => stopKind(nodeOf(v), hubSet) || (groups.members[v] || []).map(m => stopKind(nodeOf(m), hubSet)).find(Boolean) || "hub";
      const stops = [...c.boxes].filter(v => endsHover(v) && !(e.side && v === e.from))
        .sort((p, q) => (c.steps.get(p) || 0) - (c.steps.get(q) || 0))
        .map(v => [nodeOf(v).label, kindOf(v)]);
      etip.innerHTML = edgeTip(e, id => nodeOf(id).label) + stopsNote(stops) + (() => {
        const hint = [nodeEl[e.to] && "click: the box it leads to", nodeEl[e.from] && lastPointer !== "touch" && `${SOURCE_KEY}-click: the box it comes from`].filter(Boolean);
        return hint.length ? `<div class="off">${hint.join(" · ")}</div>` : "";
      })();
      placeTip();
    }
    updateFar();
  }
  function setHover(id) {
    if (id === hoverId || !svg) return;
    if (hoverEdge !== null) setEdgeHover(null);
    svg.querySelectorAll(".he,.hn").forEach(el => el.classList.remove("he", "hn", "he2", "he3", "hn2", "hn3"));
    hoverId = id && nodeEl[id] ? id : null;
    svg.classList.toggle("hovering", !!hoverId);
    if (hoverId) svg.dataset.hover = hoverId; else delete svg.dataset.hover;  // names the hovered box, for checks
    if (hoverId) {
      nodeEl[hoverId].classList.add("hn");
      (edgesAt[hoverId] || []).forEach(el => {
        el.classList.add("he");
        [el.dataset.from, el.dataset.to].forEach(v => nodeEl[v] && nodeEl[v].classList.add("hn"));
      });
    }
    updateFar();
  }
  /* What the pointer hovers, worked out from where it is on every move (pointerover alone misses a card growing or
     moving under a still target). Every grown card lets the pointer through (CSS: .node.mag), the hovered box's too,
     so moving along a row reaches each box in turn, also those a card covers. In order: a box drawn under the
     pointer; then the spot a grown box is drawn at; then the hovered box's own card keeps the hover; then a hovered
     line, while on it; then a grown card over the pointer (it is drawn over the lines); then a line; else nothing. */
  const inRect = (el, x, y) => { const q = el.getBoundingClientRect(); return x >= q.left && x <= q.right && y >= q.top && y <= q.bottom; };
  function cardUnder(x, y) {  // the topmost grown card at screen point x, y
    return [...svg.querySelectorAll("#nodes > .node.mag")].reverse().find(c => inRect(c, x, y)) || null;
  }
  function spotUnder(x, y, ids) {  // the box among ids whose drawn spot holds screen point x, y
    const m = svg.getScreenCTM();
    if (!m) return null;
    const p = new DOMPoint(x, y).matrixTransform(m.inverse());
    return boxAt(ids.map(id => layNode[id]).filter(Boolean), p.x, p.y);
  }
  function pointerAt(t, x, y) {  // what is at the pointer's place, for pointerPick
    const g = t.closest && t.closest(".node"), own = hoverId && nodeEl[hoverId];
    const line = t.classList && t.classList.contains("eh") ? Number(t.dataset.edge) : null, c = cardUnder(x, y);
    return {
      box: g ? g.dataset.id : null,
      spot: spotUnder(x, y, [...magnified, ...(hoverId ? [hoverId] : [])]),
      own: own && own.classList.contains("mag") && inRect(own, x, y) ? hoverId : null,
      hovered: line !== null && line === hoverEdge ? line : null,
      card: c ? c.dataset.id : null,
      line,
    };
  }
  const pickHover = (t, x, y) => pointerPick(pointerAt(t, x, y));
  let hoverAt = null, hoverFrame = 0;
  function hoverFrom(e) {
    if (drag || !svg || spreadDrag) return;  // not while a Steps preview has the boxes away from their places
    if (!view.hover) { if (hoverId || hoverEdge !== null) { setHover(null); setEdgeHover(null); } return; }  // View: hover highlights off
    hoverAt = { t: e.target, x: e.clientX, y: e.clientY };
    if (hoverFrame) return;
    hoverFrame = requestAnimationFrame(() => {  // at most once a frame
      hoverFrame = 0;
      if (!hoverAt || drag || !view.hover) return;
      const h = pickHover(hoverAt.t, hoverAt.x, hoverAt.y);
      laneHint(h.box || h.edge !== undefined ? null : laneAt(hoverAt.x, hoverAt.y));
      if (h.edge !== undefined) { setEdgeHover(h.edge); return; }
      setEdgeHover(null);
      setHover(h.box || null);
    });
  }
  wrapEl.addEventListener("pointerover", hoverFrom);
  wrapEl.addEventListener("pointermove", hoverFrom);
  wrapEl.addEventListener("pointerleave", () => { hoverAt = null; setHover(null); setEdgeHover(null); });

  function drawSvg(lay) {
    W = lay.width + LEFT + 60; H = Math.max(lay.height, 200);
    // --bscale: the box outlines keep their width when the boxes are drawn larger (spreadGeo scale)
    const p = [`<svg id="map" xmlns="http://www.w3.org/2000/svg" viewBox="${-LEFT} 0 ${W} ${H}" style="--bscale:${(1 / (lay.geo.scale || 1)).toFixed(4)}">`,
      '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">',
      '<path d="M0,0 L10,5 L0,10 z" fill="context-stroke"/></marker></defs><g id="bands">'];
    lay.bands.forEach((b, i) => {  // the lane names are pinned to the screen's left edge (drawRulers), not drawn here
      const c = esc(b.color);
      // run on past both ends, so a drawing narrower than the screen at Fit has its lanes out to the screen's sides;
      // every other lane is shaded stronger, so two lanes of near colours (deploy and agent docs) still part clearly
      p.push(`<rect class="band${i % 2 ? " alt" : ""}" x="${-LEFT - BAND_RUN}" y="${b.y}" width="${W + 2 * BAND_RUN}" height="${b.h}" fill="${c}"/>`,
        `<line class="lanerule" x1="${-LEFT - BAND_RUN}" x2="${W - LEFT + BAND_RUN}" y1="${b.y}" y2="${b.y}" stroke="${c}"/>`);
    });
    p.push('</g><g id="edges">');
    lay.edges.forEach((e, i) => {
      p.push(`<path class="edge${e.back ? " back" : ""}" id="e${i}" data-from="${esc(e.from)}" data-to="${esc(e.to)}" ` +
        `d="${pathD(e.pts)}" marker-end="url(#arrow)"/>`);
    });
    // a wide invisible copy of each link takes the pointer, so a thin line is easy to hover (setEdgeHover)
    p.push('</g><g id="ehit">');
    lay.edges.forEach((e, i) => p.push(`<path class="eh" data-edge="${i}" d="${pathD(e.pts)}"/>`));
    p.push(`</g><g id="elabels"${document.getElementById("labels").checked ? "" : ' class="hidden"'}>`);
    lay.edges.forEach((e, i) => { if (e.label) p.push(`<text class="elabel" data-edge="e${i}">${esc(e.label)}</text>`); });
    p.push('</g><g id="nodes">');
    for (const n of lay.nodes) {
      const [, fill, ink] = DATA.kinds[n.kind], status = n.status || "live";
      const sc = lay.geo.scale || 1, bw = n.w / sc, bh = n.h / sc;  // drawn at its own size, scaled up as a whole
      p.push(`<g class="node ${n.kind} ${status}" data-id="${esc(n.id)}" transform="${boxTransform(n, sc)}">`,
        `<rect class="box" width="${bw.toFixed(1)}" height="${bh.toFixed(1)}" rx="6" fill="${fill}" stroke="${ink}"/>`,
        `<rect width="6" height="${bh.toFixed(1)}" rx="3" fill="${esc(DATA.domainColor[n.domain])}"/>`);
      let ty = 2;
      for (const line of titleLines(n, lay.geo)) { ty += 16; p.push(`<text class="t" x="14" y="${ty}" fill="${ink}">${esc(line)}</text>`); }
      if (n.path) {
        ty += 15;
        const shown = n.path.length <= 37 ? n.path : "…" + n.path.slice(-36);
        p.push(`<text class="p" x="14" y="${ty}">${esc(shown)}</text>`);
      }
      ty += 2;
      for (const line of wrap(n.desc, lay.geo.descWrap || WRAP)) { ty += 13; p.push(`<text class="d" x="14" y="${ty}">${esc(line)}</text>`); }
      p.push("</g>");
    }
    p.push("</g></svg>");
    return p.join("\n");
  }

  /* aspect: the screen shape to stretch the lanes to (a shared link's own); by default the free area's now, and once
     the info panel has opened or closed the drawing is laid out again for the area as it is then. */
  let colsKey = "", colsOf = 0, natH = 0;  // the map's column count and unstretched height, and which map they are for
  /* The columns of the map as drawn now, and view.boxCap: the boxes grow no more than the lanes have room for at their
     height on screen, so every lane still fits top to bottom and n steps fill the width (only the steps spread, the
     view does not zoom). Laid out once per map, unstretched, the first time the Steps slider needs it. */
  function boxRoom(base, screen) {
    const key = `${view.compact}|${sub.nodes.map(n => n.id).join(",")}|${sub.edges.map(e => e.from + ">" + e.to).join(",")}`;
    if (colsKey !== key) {
      colsKey = key;
      const l0 = layout(sub.nodes, sub.edges, DATA.domains, 0, base);
      colsOf = l0.columns; natH = l0.height;
    }
    // a shared view (its own lane stretch, no screen of ours) takes the sharer's cap, so the boxes come out as they had them
    const tall = screen > 0 && natH > 0 ? ((colsOf - 1) * stepOf(base) + base.nodeW + LEFT + 60) * screen / natH : view.sharedCap || BOX_GROW;
    view.boxCap = Math.max(1, Math.min(BOX_GROW, tall));
    return colsOf;
  }
  function render(keepView, aspect, settled) {
    sub = subset();
    const old = vb && keepView ? { x: vb.x, y: vb.y, w: vb.width, h: vb.height } : null;
    const asked = aspect !== undefined;
    /* Steps slider (view.steps n, 0 for all): the steps spread so n fill the width all of them fill unspread, and the lane
       stretch scaled so the lanes keep the height they have then; the columns come from a first layout of the same map */
    const base = view.compact ? NARROW : WIDE, screen = asked ? 0 : fitAspect();
    let geo = base;
    view.spread = 1;
    if (view.steps) {
      const cols = boxRoom(base, screen);
      view.spread = spreadFor(cols, Math.max(Math.min(3, cols), view.steps), base, view.boxCap);
      geo = spreadGeo(base, view.spread, view.boxCap);
      if (!asked) {
        const w1 = (cols - 1) * stepOf(base) + base.nodeW + LEFT + 60, wk = (cols - 1) * stepOf(geo) + geo.nodeW + LEFT + 60;
        aspect = screen * w1 / wk;
      }
    } else if (!asked) aspect = screen;
    lay = layout(sub.nodes, sub.edges, DATA.domains, aspect, geo);
    lay.aspect = aspect; lay.screen = screen;
    wrapEl.innerHTML = drawSvg(lay);
    svg = document.getElementById("map");
    vb = svg.viewBox.baseVal;
    nodeEl = {};
    svg.querySelectorAll(".node").forEach(g => (nodeEl[g.dataset.id] = g));
    edgeEls = [...svg.querySelectorAll(".edge")];
    magnified = new Set(); degree = {}; edgesAt = {}; hoverId = null; hoverEdge = null; hoverSteps = null; hoverEnds = new Set(); etip.hidden = true; laneBack = null;
    closeLens();  // the lens holds a copy of the old drawing
    for (const k in layNode) delete layNode[k];
    lay.nodes.forEach(n => (layNode[n.id] = n));
    edgeEls.forEach(el => [el.dataset.from, el.dataset.to].forEach(v => { degree[v] = (degree[v] || 0) + 1; (edgesAt[v] ||= []).push(el); }));
    drawNav();
    columnKinds();
    svg.querySelectorAll(".elabel").forEach(l => {
      const path = document.getElementById(l.dataset.edge), m = path.getPointAtLength(path.getTotalLength() / 2);
      l.setAttribute("x", m.x); l.setAttribute("y", m.y - 3); l.setAttribute("text-anchor", "middle");
    });
    visible = new Set(sub.nodes.map(n => n.id));
    syncControls();
    showStatus(sub);  // before fit, which measures the toolbar with the status line in it
    if (old) setVB(old.x, old.y, old.w, old.h);
    runSearch(true);
    if (selected && !visible.has(selected) && visible.has(groups.groupOf[selected])) selected = groups.groupOf[selected];  // folded away: its folder
    if (selected && visible.has(selected)) select(selected, true);
    else { const had = selected; selected = null; info.style.display = "none"; if (had) writeHash(); }
    if (!old && !asked && !settled && Math.abs(fitAspect() - screen) > 0.01) { render(false, undefined, true); return; }  // the panel changed the area
    if (!old) fit();  // after the info panel is shown or hidden, so the fit leaves room for it
    else setVB(vb.x, vb.y, vb.width, vb.height);  // clamped again against the panel as it is now
    updateNav();
  }

  /* Redraw after a change that moves the boxes (compact, folders, a filter) without losing the reader's place: the
     selected box, or else the box nearest the middle of the screen, stays where it was on screen at the same zoom
     (unless the new drawing is narrower than that view, when the sideways clamp moves it).
     A view that showed everything fits again; a box now inside a folder is followed to the folder, and a folder that
     opened to its boxes, to the first of them. */
  function renderKeeping() {
    if (!lay || !lay.nodes.length || showsAll(vb, W, H, LEFT, freeShare())) { render(false); return; }
    const cx = vb.x + vb.width / 2, cy = vb.y + vb.height / 2, mid = n => [n.x + n.w / 2, n.y + n.h / 2];
    const dist = n => { const [x, y] = mid(n); return (x - cx) ** 2 + (y - cy) ** 2; };
    const a = lay.nodes.find(n => n.id === selected) || lay.nodes.reduce((b, n) => (dist(n) < dist(b) ? n : b));
    const members = (groups.members[a.id] || [a.id]).slice().sort((x, y) => (y === lastBox) - (x === lastBox));  // the box last picked first
    const [ax, ay] = mid(a), was = { members, dx: ax - vb.x, dy: ay - vb.y, w: vb.width, h: vb.height };
    render(true);
    const t = lay.nodes.find(n => n.id === a.id) || was.members.map(m => lay.nodes.find(n => n.id === m)).find(Boolean) ||
      lay.nodes.find(n => n.id === groups.groupOf[a.id]);
    if (!t) {  // the box itself was filtered out: a neighbour still drawn takes its place on screen, at the same zoom
      const near = [...(insAll[a.id] || []).map(e => e.from), ...(outsAll[a.id] || []).map(e => e.to)]
        .map(id => lay.nodes.find(n => n.id === id)).find(Boolean);
      if (!near) { fit(); return; }
      const [nx, ny] = mid(near);
      setVB(nx - was.dx, ny - was.dy, was.w, was.h);
      return;
    }
    if (t.id !== a.id && t.id === lastBox && !selected) { selected = t.id; select(t.id, true); }  // unfolded: pick the box again
    const [tx, ty] = mid(t);
    setVB(tx - was.dx, ty - was.dy, was.w, was.h);
  }
  // the filters as they start; Clear filters goes back to these and keeps the file and the selected box
  const filtersChanged = () => view.lanes.size !== allLanes.length || view.kindsOff.size || view.parked || view.retired ||
    !view.compact || view.group || view.trim || !document.getElementById("labels").checked;  // Steps is not counted: its row would push the map down on release
  function clearFilters() {
    view.lanes = new Set(allLanes); view.kindsOff.clear(); view.parked = view.retired = false;
    view.compact = true; view.group = false; view.open.clear(); view.trim = false;
    document.getElementById("labels").checked = true;
    syncControls(); renderKeeping(); writeHash();
  }

  function showStatus(sub) {
    const el = document.getElementById("view");
    const parts = [];
    if (view.focus) parts.push(`<b>${esc(byId[view.focus].label)}</b>`);
    if (sub.trim) parts.push(selected === view.focus ? "highlighted only" : `only the chain of <b>${esc(nodeOf(selected).label)}</b>`);
    const kindsOn = Object.keys(DATA.kinds).filter(k => hideable(k) && !view.kindsOff.has(k));
    if (view.kindsOff.size && kindsOn.length === 1) parts.push(`only ${esc(DATA.kinds[kindsOn[0]][0].toLowerCase())}`);
    else if (view.kindsOff.size) parts.push(`${[...view.kindsOff].map(k => DATA.kinds[k][0].toLowerCase()).join(", ")} hidden`);
    if (view.group && !view.focus) parts.push("grouped by folder");
    const lanesOff = allLanes.filter(d => !view.lanes.has(d));
    if (lanesOff.length) parts.push(`${view.lanes.size} of ${allLanes.length} lanes`);
    const off = [!view.parked && "parked", !view.retired && "retired"].filter(Boolean);
    if (off.length) parts.push(`${off.join(" and ")} hidden`);
    showDepth();
    const all = view.focus || sub.trim || view.kindsOff.size || view.group || view.lanes.size !== allLanes.length;
    const boxes = sub.nodes.reduce((n, b) => n + (groups.members[b.id] ? groups.members[b.id].length : 1), 0);  // a folder counts its boxes
    el.innerHTML = parts.length ? `Showing ${parts.join(" · ")} · ${boxes} of ${DATA.nodes.length} boxes`
      : `${DATA.nodes.length} boxes, ${DATA.edges.length} links`;
    document.getElementById("showall").hidden = !all;
    document.getElementById("clearf").hidden = !filtersChanged();
    document.getElementById("clearf2").parentElement.hidden = !filtersChanged();  // its twin at the foot of Filters
    strip2.hidden = !(view.focus || filtersChanged());  // the second row only while there is a file view or a changed filter
  }
  const strip2 = document.getElementById("strip2");
  document.getElementById("clearf").onclick = clearFilters;
  document.getElementById("clearf2").onclick = () => { clearFilters(); document.getElementById("lanes").open = false; };  // the same, in Filters
  document.getElementById("showall").onclick = () => {
    view.focus = null; if (view.trim) selected = null; view.lanes = new Set(allLanes);
    view.kindsOff.clear(); view.group = false; view.open.clear(); fileIn.value = "";
    syncControls(); render(false); writeHash();
  };

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
  // the free area as shares of the map (see showsAll)
  function freeShare() {
    const a = freeArea();
    return { top: a.top / a.r.height, right: a.right / a.r.width, bottom: a.bottom / a.r.height };
  }
  /* ---- step headers along the top and lane names down the left, pinned to the screen while the map moves under them */
  const spreadCtl = document.getElementById("spreadctl"), spreadIn = document.getElementById("spread"), spreadOut = document.getElementById("spreadn");
  const legend = document.getElementById("legend"), rulers = document.getElementById("rulers"), steps = document.getElementById("steps"), laneTags = document.getElementById("lanetags");
  legend.addEventListener("toggle", () => drawRulers());  // open, it is taller: the tags beside it move up
  let colKinds = [];  // per column: what its boxes are, for the header's tooltip
  let rawFirst = false;  // whether nothing in the whole graph builds any box of column 0 (a filtered view may hide what does)
  // the strip shows only over a drawing with boxes (sub is set before layout), and not while the extras are hidden
  const showRulers = () => stripRoom(clean, sub.nodes.length) > 0;
  /* ---- dark mode and hidden extras. Dark starts from the system setting and a choice is remembered on this browser;
     the lane names take a lighter shade of their colour on the dark background. Hide extras takes away the lane names,
     step headers, legend and overview, and gives the map the room the step strip had. */
  let clean = false;
  const DARK_KEY = "pipelineMapDark", darkBox = document.getElementById("dark");
  const isDark = () => document.documentElement.classList.contains("dark");
  const tagInk = c => (isDark() ? lighten(c) : c);
  function setDark(on, remember) {
    document.documentElement.classList.toggle("dark", on);
    darkBox.checked = on;
    if (remember) try { localStorage.setItem(DARK_KEY, on ? "1" : "0"); } catch (e) { /* storage off: not remembered */ }
    if (svg) drawRulers();
  }
  let darkSaved = null;
  try { darkSaved = localStorage.getItem(DARK_KEY); } catch (e) { darkSaved = null; }
  setDark(darkSaved === null ? matchMedia("(prefers-color-scheme: dark)").matches : darkSaved === "1", false);
  darkBox.onchange = e => setDark(e.target.checked, true);
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", e => {  // follows the system until a choice is saved
    let saved = null;
    try { saved = localStorage.getItem(DARK_KEY); } catch (err) { saved = null; }
    if (saved === null) setDark(e.matches, false);
  });
  const cleanBox = document.getElementById("clean");  // View, Clean view (H)
  function setClean(on) {
    clean = on;
    document.body.classList.toggle("clean", on);
    cleanBox.checked = on;
    if (!svg) return;
    if (fitted) fit();  // a whole-map view fits again into the room the step strip had, or gives it back
    else setVB(vb.x, vb.y, vb.width, vb.height);  // the free area changed: clamped again, rulers and overview redrawn
  }
  cleanBox.onchange = () => setClean(cleanBox.checked);
  function columnKinds() {
    const step = stepOf(lay.geo), cols = Array.from({ length: lay.columns }, () => ({}));
    lay.nodes.forEach(n => { const c = cols[Math.round(n.x / step)]; c[n.kind] = (c[n.kind] || 0) + 1; });
    rawFirst = firstColumnIsRaw(lay.nodes, DATA.edges, id => Object.hasOwn(byId, id), lay.geo);
    colKinds = cols.map(c => Object.entries(c).sort((a, b) => b[1] - a[1])
      .map(([k, n]) => `${n} ${(DATA.kinds[k] ? DATA.kinds[k][0] : k).toLowerCase()}`).join(", "));
  }
  /* The Steps slider sits at the right of the step strip, or in clean view (no strip) at the top right of the map, so
     it can always be moved back to all steps; it hides while the map has no boxes. */
  function placeSpread() {
    spreadCtl.hidden = !lay || !lay.nodes.length;
    if (spreadCtl.hidden) return;
    const a = freeArea(), top = showRulers() ? a.top - STRIP_H - 3 : a.top + 4;
    spreadCtl.style.top = `${top}px`; spreadCtl.style.left = `${Math.max(0, a.right - spreadCtl.offsetWidth - 8)}px`;
  }
  function drawRulers() {
    steps.style.visibility = "";  // shown again after a Steps preview
    placeSpread(); syncSpread();
    if (!showRulers()) { rulers.hidden = true; return; }
    rulers.hidden = false;
    const r = wrapEl.getBoundingClientRect(), m = svg.getScreenCTM(), a = freeArea();
    const lg = legend.getBoundingClientRect();  // read before the writes below, so a pan forces no extra layout
    const sx = x => m.a * x + m.e - r.left, sy = y => m.d * y + m.f - r.top;
    const top = a.top - STRIP_H - 4;  // the strip sits in the room freeArea keeps for it, just under the toolbar
    steps.style.top = `${top}px`; steps.style.width = `${a.right}px`;
    const x0 = (0 - m.e + r.left) / m.a, x1 = (a.right - m.e + r.left) / m.a, last = lay.columns - 1;
    const t = stepTicks(lay.columns, x0, x1, m.a, lay.geo), out = [];
    let edge = -Infinity;  // right end of the last label placed; a label that would overlap it is left out
    for (const c of t.cols) {
      const label = c.r === 0 ? (rawFirst ? "Step 0 · raw data" : "Step 0") : c.r === last && t.every === 1 ? `Step ${c.r} · built last` : `Step ${c.r}`;
      const half = label.length * 3.6 + 4;  // about 7.2 px a character at 12 px
      const x = c.r === 0 ? Math.max(sx(c.x), half + 4) : sx(c.x);  // step 0 stays readable at the left edge; others go when cut off
      if (x - half < Math.max(edge + 10, 0)) continue;
      if (!spreadCtl.hidden && x + half > a.right - spreadCtl.offsetWidth - 14) continue;  // under the Steps slider
      edge = x + half;
      out.push(`<span style="left:${x.toFixed(0)}px" title="Step ${c.r}: ${esc(c.r === 0 ? (rawFirst ? "nothing on the map builds these. " : "the first column of this view; boxes the filters hide may build these. ") : `${c.r} links from step 0. `)}${esc(colKinds[c.r] || "")}">${esc(label)}</span>`);
    }
    steps.innerHTML = out.join("");
    // the legend sits bottom left: tags beside it move up clear of it, unless it is below the free area (on a phone,
    // behind the open info panel)
    const left = Math.max(8, sx(-LEFT) + 8), floor = top + STRIP_H + 6, lgTop = lg.top - r.top - 4;
    const under = lg.width && left < lg.right - r.left && lgTop < a.bottom ? lgTop : Infinity;
    const tops = laneTagTops(lay.bands.map(b => [sy(b.y), sy(b.y + b.h)]), floor, a.bottom, under), tags = [];
    lay.bands.forEach((b, i) => {
      if (tops[i] !== null)
        tags.push(`<span data-lane="${i}" title="${atLane(b.id) ? "Click to go back to the view before" : "Click to zoom to this lane"}" style="top:${tops[i].toFixed(0)}px;left:${left.toFixed(0)}px;color:${esc(tagInk(b.color))};border-color:${esc(tagInk(b.color))}">${esc(b.label)}</span>`);
    });
    laneTags.innerHTML = tags.join("");
  }
  /* ---- a click on a lane's name: the lane's boxes fill the free area's height (at most at full size), from its first
     box, so they are big enough to read and the reader pans along the lane; a second click on the same name goes back
     to the view before. */
  let laneBack = null;  // {lane, v: [x, y, width, height] before, at: the lane view} after a lane zoom
  // whether the view is still the one the lane zoom set (a pan, zoom or Fit since leaves it)
  const atLane = id => !!laneBack && laneBack.lane === id && laneBack.at.length > 0 && laneBack.at.every((t, i) => Math.abs(t - [vb.x, vb.y, vb.width][i]) <= 1);
  /* The lane names let the pointer through (CSS), so the boxes under them hover and click; a click that finds no box
     or line there zooms to the lane whose name is under it (laneAt). */
  function laneAt(x, y) {
    const t = [...laneTags.querySelectorAll("span[data-lane]")].find(el => inRect(el, x, y));
    return t ? Number(t.dataset.lane) : null;
  }
  /* Over a lane name with no box or line under it: the zoom cursor and the lane name's hint (the names let the
     pointer through, so they cannot show their own). */
  function laneHint(i) {
    const b = i === null ? null : lay.bands[i];
    wrapEl.classList.toggle("onlane", !!b);
    if (b) wrapEl.title = atLane(b.id) ? "Click to go back to the view before" : "Click to zoom to this lane";
    else wrapEl.removeAttribute("title");
  }
  function zoomLane(i) {
    const b = lay.bands[i];
    if (!b) return;
    if (atLane(b.id)) { const v = laneBack.v; laneBack = null; setVB(...v); return; }
    if (laneBack && !lay.bands.some(o => atLane(o.id))) laneBack = null;  // moved away since: the view now is the one to go back to
    const was = laneBack ? laneBack.v : [vb.x, vb.y, vb.width, vb.height], a = freeArea();
    const mine = lay.nodes.filter(n => n.domain === b.id);
    if (!mine.length) return;
    const y0 = Math.min(...mine.map(n => n.y)) - 20, y1 = Math.max(...mine.map(n => n.y + n.h)) + 20;
    const s = Math.min((a.bottom - a.top) / (y1 - y0), 1), x0 = Math.min(...mine.map(n => n.x));
    laneBack = { lane: b.id, v: was, at: [] };  // at is set once the view has moved
    setVB(x0 - 240 / s, (y0 + y1) / 2 - (a.top + a.bottom) / 2 / s, a.r.width / s, a.r.height / s);  // 240 px left of the first box, for the lane names
    laneBack.at = [vb.x, vb.y, vb.width];
    drawRulers();
    laneHint(i);  // the hint now says a second click goes back
  }

  function updateNav() {
    drawRulers();
    updateFar();
    if (lensSvg && ptr) moveLens();
    if (!navRect) return;
    const open = info.style.display === "block", narrow = innerWidth <= 900;
    // hidden while the whole drawing is in view below the toolbar, as at Fit, and on a phone under the open info panel
    fitted = view.spread > 1 ? atSpreadFit() : showsAll(vb, W, H, LEFT, freeShare());  // spread: at the Fit view it shows
    nav.hidden = fitted || (open && narrow);
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
  const FIT_PAD = 28;  // px of margin round the whole drawing at Fit, the furthest zoom out
  /* The widest view allowed: the Fit width (at least 200), or Infinity while the map has no size yet (hidden). */
  function maxWidth(free = freeShare()) {
    const fw = fitView(W, H, LEFT, free, wrapEl.clientWidth, wrapEl.clientHeight, FIT_PAD).width;  // out to the whole drawing
    return Number.isFinite(fw) && fw > 0 ? Math.max(fw, 200) : Infinity;
  }
  /* The free area's height over its width, for layout's lanes; 0 while the map has no size yet (hidden). */
  function fitAspect() {
    const a = freeArea(), p = fitPad(FIT_PAD, freeShare(), wrapEl.clientWidth, wrapEl.clientHeight);
    const w = a.right - 2 * p, h = a.bottom - a.top - 2 * p;  // the shape Fit fills, inside its margin
    return w > 0 && h > 0 ? h / w : 0;
  }
  function setVB(x, y, w, h) {  // every move goes through here, kept on the drawing (clampView)
    const free = freeShare(), sw = wrapEl.clientWidth, sh = wrapEl.clientHeight, p = fitPad(FIT_PAD, free, sw, sh);
    const c = clampView({ x, y, width: w, height: h }, W, lay && lay.nodes.length ? lay.height : H, LEFT, free, maxWidth(free),  // the drawn height, not the 200 minimum
      sw > 0 ? p / sw : 0, sh > 0 ? p / sh : 0);
    vb.x = c.x; vb.y = c.y; vb.width = c.width; vb.height = c.height;
    if (hoverEdge !== null) setEdgeHover(null);  // the line has moved from under the pointer
    updateNav();
  }
  /* The part of the map the reader can see, in px inside #wrap: below the toolbar, and left of the info panel (or,
     on a phone, above it) while that is open. */
  function freeArea() {
    const r = wrapEl.getBoundingClientRect(), top = document.getElementById("bar").getBoundingClientRect().bottom - r.top + 10 + stripRoom(clean, sub.nodes.length);  // under the step headers, when they show
    let right = r.width, bottom = r.height;
    if (info.style.display === "block") {
      const i = info.getBoundingClientRect();
      if (innerWidth > 900) right = Math.max(200, i.left - r.left - 10);
      else bottom = Math.max(top + 40, i.top - r.top - 10);
    }
    return { r, top, right, bottom };
  }
  let fitted = false;  // whether the whole drawing was in the free area at the last move (updateNav)
  function atSpreadFit() {  // spread across: whether the view is the Fit view (the lanes' full height, from the left)
    const f = fitNow(), t = f.width / 200;
    return Math.abs(vb.width - f.width) <= t && Math.abs(vb.x - f.x) <= t && Math.abs(vb.y - f.y) <= t;
  }
  // the width Fit shows: the whole drawing, or spread (Steps slider) the first steps shown, lanes filling the height
  const fitW = () => (view.spread > 1 ? (Math.min(Math.max(view.steps, Math.min(3, lay.columns)), lay.columns) - 1) * stepOf(lay.geo) + lay.geo.nodeW + LEFT + 60 : W);
  /* The step strip's Steps slider: how many steps show across the screen, the lanes keeping their full height. The map
     is laid out again with the steps spread apart (spreadFor, spreadGeo: the boxes widen up to BOX_GROW times and the
     gap takes the rest), so fewer steps fill the width and each box has more room; the same part of the drawing stays in the middle. */
  let spreadDrag = false;  // while the thumb is held: the slider is left as the reader has it
  function syncSpread() {  // the slider and its label from the drawing: n of the columns across
    if (!lay || spreadDrag) return;
    const cols = Math.max(lay.columns || 1, 1), n = view.steps ? Math.min(Math.max(Math.min(3, cols), view.steps), cols) : cols;
    spreadIn.min = String(Math.min(3, cols)); spreadIn.max = String(cols); spreadIn.value = String(n);
    spreadOut.textContent = `${n} of ${cols}`;
  }
  function setSteps(n, quiet) {  // n steps across, or all of them (0)
    const cols = lay ? Math.max(lay.columns || 1, 1) : 0, want = !cols || n >= cols ? 0 : Math.max(Math.min(3, cols), Math.round(n));
    if (want === view.steps) {  // back where it began: put a preview's stretch back
      if (svg && svg.classList.contains("previewing")) render(true);
      syncSpread(); return;
    }
    // the drawing x at the middle of the free area (left of the info panel), as a share of the boxes' width
    const half = freeShare().right / 2, mid = lay && lay.width > 0 ? (vb.x + half * vb.width) / lay.width : 0;
    const before = boxesOnScreen();  // where the preview left the boxes, so they glide to their places (settle)
    view.steps = want;
    render(false);
    capReady = false;  // the next drag works the cap out for the map as drawn now
    if (mid > 0 && view.spread > 1) {  // back to the same part of the drawing, lanes still filling the height
      const f = fitNow();
      setVB(mid * lay.width - half * f.width, f.y, f.width, f.height);
    }
    settle(before);
    syncSpread();
    if (!quiet) writeHash();
  }
  /* The boxes on screen (id -> screen rect), and settle(before): after a Steps layout each box starts where it was on
     screen and glides to its place, the links fading back in, so letting go of the slider does not snap. */
  function boxesOnScreen() {
    const out = new Map();
    if (!svg) return out;
    const r = wrapEl.getBoundingClientRect(), a = freeArea();  // the part of the map the reader sees
    for (const id in nodeEl) {
      const q = nodeEl[id].querySelector(".box").getBoundingClientRect();
      if (q.width > 0 && q.right > r.left && q.left < r.left + a.right && q.bottom > r.top + a.top && q.top < r.top + a.bottom) out.set(id, q);
    }
    return out;
  }
  let settleEnd = 0;
  function settle(before) {
    const m = svg && svg.getScreenCTM();
    if (!m || !before.size || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const sc = lay.geo.scale || 1, moved = [];
    lay.nodes.forEach(n => {
      const b = before.get(n.id), g = nodeEl[n.id];
      if (!b || !g) return;
      const f = settleFrom(b, m, n.w / sc);  // its own size times f.k filled the old rect
      g.style.transition = "none";
      g.style.transform = boxTransform(f, f.k, true);
      moved.push([g, boxTransform(n, sc, true)]);
    });
    if (!moved.length) return;
    svg.classList.add("settling");
    svg.getBoundingClientRect();  // the start places take effect before the glide
    moved.forEach(([g, t]) => { g.style.transition = ""; g.style.transform = t; });
    clearTimeout(settleEnd);
    settleEnd = setTimeout(() => {  // the transform attribute, already the place, takes over again
      moved.forEach(([g]) => { g.style.transform = ""; g.style.transition = ""; });
      if (svg) svg.classList.remove("settling");
      updateFar();  // the boxes that grow when zoomed out take their places now
    }, 320);
  }
  // dragging moves the label; letting go (or a key) lays the map out once; a drag ended where it began fires no change
  spreadIn.addEventListener("pointerdown", () => { spreadDrag = true; capReady = false; clearTimeout(wheelRest); });
  ["pointerup", "pointercancel", "blur"].forEach(t => spreadIn.addEventListener(t, () => {
    spreadDrag = false;
    // a drag let go where it began fires no change: undo its preview (change, when it fires, has already laid out)
    setTimeout(() => { if (svg && svg.classList.contains("previewing")) setSteps(Number(spreadIn.value)); }, 0);
  }));
  /* While the thumb moves, the drawing stretches across at once as a preview (the steps spread about the middle of the
     view, the boxes and text drawn wide for the moment); letting go lays it out properly, once (a full layout takes a
     moment), and the boxes then grow in height too, so the lanes settle on release. */
  let previewFrame = 0, capReady = false;  // capReady: boxRoom worked out for this drag
  function previewSteps() {
    previewFrame = 0;
    if (!svg || !lay) return;
    if (magnified.size) { magnified.forEach(unmagnify); magnified = new Set(); }  // grown boxes would stretch with it
    steps.style.visibility = "hidden";  // the step headers come back with the layout on release
    const cols = Math.max(lay.columns || 1, 1), n = Number(spreadIn.value);
    if (!view.steps && !capReady) { boxRoom(view.compact ? NARROW : WIDE, lay.screen || fitAspect()); capReady = true; }  // from all steps: once a drag
    const sx = spreadFor(cols, n, view.compact ? NARROW : WIDE, view.boxCap) / view.spread, m = svg.getScreenCTM(), r = wrapEl.getBoundingClientRect();
    if (!m) return;
    const cx = (r.left + freeArea().right / 2 - m.e) / m.a;  // the drawing x at the middle of the free area
    const t = Math.abs(sx - 1) < 1e-3 ? "" : `matrix(${sx.toFixed(4)},0,0,1,${(cx * (1 - sx)).toFixed(1)},0)`;
    // the links stretch across with the steps, dimmed: they meet the boxes again on release
    ["edges", "ehit", "elabels"].forEach(id => { const g = svg.querySelector("#" + id); if (g) { if (t) g.setAttribute("transform", t); else g.removeAttribute("transform"); } });
    svg.classList.add("previewing");
    // each box moves with its step and grows whole, as wide and as tall; boxes spread up and down about their lane's
    // middle as they grow, so a column does not pile up (the lanes settle on release)
    const was = lay.geo.scale || 1, now = spreadGeo(view.compact ? NARROW : WIDE, view.spread * sx, view.boxCap).scale || 1, ry = now / was;
    svg.style.setProperty("--bscale", (1 / now).toFixed(4));  // outlines keep their width
    const mid = {};
    lay.bands.forEach(b => (mid[b.id] = b.y + b.h / 2));
    lay.nodes.forEach(n => {
      const g = nodeEl[n.id];
      if (!g) return;
      const w = n.w / was * now, h = n.h / was * now, mx = cx + (n.x + n.w / 2 - cx) * sx;
      const lm = mid[n.domain] !== undefined ? mid[n.domain] : n.y + n.h / 2, my = lm + (n.y + n.h / 2 - lm) * ry;
      g.setAttribute("transform", boxTransform({ x: mx - w / 2, y: my - h / 2 }, now));
    });
  }
  spreadIn.addEventListener("input", () => {
    spreadOut.textContent = `${spreadIn.value} of ${spreadIn.max}`;
    if (!previewFrame) previewFrame = requestAnimationFrame(previewSteps);
  });
  /* The wheel over the slider moves it a step for each notch (a trackpad's small deltas add up to one), like a zoom; the
     map is laid out when the wheel rests. A sideways swipe or a pinch (Ctrl) is left alone. */
  let wheelRest = 0, wheelSum = 0;
  spreadCtl.addEventListener("wheel", e => {
    e.preventDefault(); e.stopPropagation();
    if (e.ctrlKey || Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
    wheelSum += e.deltaY * (e.deltaMode === 1 ? 40 : e.deltaMode === 2 ? 400 : 1);
    if (Math.abs(wheelSum) < 50) return;
    const dir = Math.sign(wheelSum); wheelSum = 0;
    const n = Math.min(Number(spreadIn.max), Math.max(Number(spreadIn.min), Number(spreadIn.value) + dir));
    if (String(n) === spreadIn.value) return;
    spreadIn.value = String(n); spreadDrag = true;
    spreadIn.dispatchEvent(new Event("input"));
    clearTimeout(wheelRest);
    wheelRest = setTimeout(() => { spreadDrag = false; setSteps(Number(spreadIn.value)); }, 250);  // the value as it is then
  }, { passive: false });
  spreadIn.addEventListener("change", () => { spreadDrag = false; clearTimeout(wheelRest); setSteps(Number(spreadIn.value)); });
  /* The Fit view: the whole drawing in the free area, or with the Steps slider set that many steps across from the left,
     every lane top to bottom (the boxes grow only as far as the lanes have room). */
  function fitNow() {
    // lanes taller than the screen's shape for those steps (a map already tall at 1x): fit the steps across, pan down
    const tooTall = view.spread > 1 && lay.screen > 0 && H > fitW() * lay.screen * 1.02;
    return fitView(fitW(), tooTall ? 1 : H, LEFT, freeShare(), wrapEl.clientWidth, wrapEl.clientHeight, FIT_PAD);
  }
  function fit() {
    const f = fitNow();
    setVB(f.x, f.y, f.width, f.height);
  }
  function zoomAt(f, cx, cy) {
    const r = wrapEl.getBoundingClientRect();
    const px = vb.x + (cx - r.left) / r.width * vb.width, py = vb.y + (cy - r.top) / r.height * vb.height;
    const nw = Math.min(Math.max(vb.width * f, 200), Math.max(maxWidth(), vb.width)), nh = nw * vb.height / vb.width;  // capped before the corner is worked out, so a zoom-out at Fit stops instead of sliding the map
    setVB(px - (px - vb.x) * nw / vb.width, py - (py - vb.y) * nh / vb.height, nw, nh);
  }
  function centreOn(id, zoom) {  // the box in the middle of the free area, not under the toolbar or the info panel
    const n = lay.nodes.find(m => m.id === id), a = freeArea();
    if (!n) return;
    const w = zoom ? Math.min(1800, maxWidth()) : vb.width, h = w * a.r.height / a.r.width, s = w / a.r.width;  // capped first, so the box stays centred
    const cx = a.right / 2, cy = (a.top + a.bottom) / 2;
    setVB(n.x + n.w / 2 - cx * s, n.y + n.h / 2 - cy * s, w, h);
  }
  const onWheel = e => {
    e.preventDefault();
    const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? wrapEl.clientHeight : 1;
    const dx = e.deltaX * unit, dy = e.deltaY * unit;
    if (!e.ctrlKey && Math.abs(dx) > Math.abs(dy)) { setVB(vb.x + dx * vb.width / wrapEl.getBoundingClientRect().width, vb.y, vb.width, vb.height); return; }
    zoomAt(Math.exp((e.ctrlKey ? 0.012 : 0.0025) * dy), e.clientX, e.clientY);
  };
  wrapEl.addEventListener("wheel", onWheel, { passive: false });
  let drag = null, moved = false;
  const startDrag = e => { drag = { x: e.clientX, y: e.clientY, vx: vb.x, vy: vb.y }; moved = false; wrapEl.classList.add("drag"); };
  wrapEl.addEventListener("pointerdown", startDrag);
  steps.addEventListener("pointerdown", startDrag);
  window.addEventListener("pointermove", e => {
    if (!drag) return;
    const r = wrapEl.getBoundingClientRect(), dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
    setVB(drag.vx - dx * vb.width / r.width, drag.vy - dy * vb.height / r.height, vb.width, vb.height);
  });
  window.addEventListener("pointerup", () => { drag = null; wrapEl.classList.remove("drag"); });
  let relayTimer = 0;
  window.addEventListener("resize", () => {  // a fitted view fits again (the panel may have moved); others keep their middle
    clearTimeout(relayTimer);
    if (fitted) {  // fits now, and is laid out again once the resizing stops, so the lanes fill the new shape
      fit();
      relayTimer = setTimeout(() => { if (fitted) { render(true); fit(); } }, 150);
      return;
    }
    const r = wrapEl.getBoundingClientRect(), cy = vb.y + vb.height / 2, h = vb.width * r.height / r.width;
    setVB(vb.x, cy - h / 2, vb.width, h);
    if (selected && visible.has(selected)) centreOn(selected, false);
  });
  document.getElementById("fit").onclick = fit;
  const zoomCentre = f => { const a = freeArea(); zoomAt(f, a.r.left + a.right / 2, a.r.top + (a.top + a.bottom) / 2); };  // about the middle of the free area
  document.getElementById("zin").onclick = () => zoomCentre(0.6);
  document.getElementById("zout").onclick = () => zoomCentre(1.6);

  /* ---- magnifier: while Shift is held over the map, a round lens under the pointer shows that part of the drawing
     big enough to read (a copy of the drawing as it is, selection and search included). */
  const lens = document.createElement("div"), LENS = 320;
  lens.id = "lens"; lens.hidden = true; document.getElementById("stage").append(lens);
  let ptr = null, lensSvg = null;
  wrapEl.addEventListener("pointermove", e => { ptr = { x: e.clientX, y: e.clientY }; if (lensSvg) moveLens(); placeTip(); });
  wrapEl.addEventListener("pointerleave", () => { ptr = null; closeLens(); });
  function openLens() {
    if (!ptr || !svg) return;
    lensSvg = svg.cloneNode(true);
    lensSvg.classList.remove("far", "hovering");
    const hit = lensSvg.querySelector(".eh");
    if (hit) hit.parentNode.remove();
    lensSvg.querySelectorAll(".he,.hn").forEach(el => el.classList.remove("he", "hn", "he2", "he3", "hn2", "hn3"));
    lensSvg.querySelectorAll(".node.mag").forEach(g => {  // the lens shows the boxes at their own size
      const n = layNode[g.dataset.id];
      g.classList.remove("mag");
      if (n) g.setAttribute("transform", boxTransform(n, lay.geo.scale || 1));
    });
    lensSvg.querySelectorAll("[id]").forEach(el => { if (el.tagName !== "marker") el.removeAttribute("id"); });
    lensSvg.removeAttribute("id");
    lens.replaceChildren(lensSvg);
    lens.hidden = false;
    moveLens();
  }
  function moveLens() {
    const m = svg.getScreenCTM(), s = Math.max(m.a * 2.5, 0.8), w = LENS / s;
    const px = (ptr.x - m.e) / m.a, py = (ptr.y - m.f) / m.d;
    lensSvg.setAttribute("viewBox", `${px - w / 2} ${py - w / 2} ${w} ${w}`);
    lens.style.left = `${ptr.x - LENS / 2}px`; lens.style.top = `${ptr.y - LENS / 2}px`;
  }
  function closeLens() { lensSvg = null; lens.hidden = true; lens.replaceChildren(); }
  document.addEventListener("keydown", e => {
    if (e.key !== "Shift" || e.repeat || lensSvg) return;
    if (e.target.matches && e.target.matches("input:not([type=checkbox]):not([type=radio]),textarea,select")) return;
    openLens();
  });
  document.addEventListener("keyup", e => { if (e.key === "Shift") closeLens(); });
  window.addEventListener("blur", closeLens);

  /* ---- selection */
  function walk(start, adj, key) { return reach(start, adj, key, Infinity); }
  function clearFocus(user) {
    svg.classList.remove("focus");
    svg.querySelectorAll(".on,.sel,.upstream,.near").forEach(el => el.classList.remove("on", "sel", "upstream", "near"));
    info.style.display = "none";
    nav.classList.remove("focus"); nav.querySelectorAll("rect.on").forEach(r => r.classList.remove("on"));
    setVB(vb.x, vb.y, vb.width, vb.height);  // clamped again for the wider free area
    updateFar();
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
      if (view.near && lay.edges[i] && overHub(lay.edges[i])) return;  // near: a link the walk did not follow stays dim
      el.classList.add("on");
      if (isUp && !isDown) el.classList.add("upstream");
      const near = f === id || t === id;
      if (near) { el.classList.add("near"); nodeEl[f].classList.add("near"); nodeEl[t].classList.add("near"); }
      const l = svg.querySelector(`.elabel[data-edge="e${i}"]`);
      if (l) { l.classList.add("on"); if (near) l.classList.add("near"); }
    });
    updateFar();  // the selected box grows when zoomed out
    if (gNodes[id]) { folderInfo(id); return; }
    lastBox = id;
    const n = byId[id];
    const fullUp = walk(id, insAll, "from").size - 1, fullDown = walk(id, outsAll, "to").size - 1;
    const isFocus = view.focus === id;
    info.innerHTML = `<button class="close" title="Close (Esc)">×</button><h2>${esc(n.label)}</h2>
      <div>${esc(DATA.kinds[n.kind][0])} · ${esc(domainLabel[n.domain])} · ${esc(n.status || "live")}${n.local ? " · not in this checkout's tracked files (gitignored mirror, submodule or host)" : ""}</div>
      <p><code>${esc(n.path || n.id)}</code>${githubUrl(n, DATA.codeLinks) ? ` · <a class="gh" href="${esc(githubUrl(n, DATA.codeLinks))}" target="_blank" rel="noopener" title="Open this file's code on GitHub">GitHub ↗</a>` : ""}</p><p>${esc(n.desc || "")}</p>
      ${isFocus ? "" : '<p><button id="fgo">Show only this file\'s chain</button></p>'}
      ${view.kindsOff.size ? `<div class="off">Links as drawn: ${[...view.kindsOff].every(dropKind) ? "the hidden boxes left out with their links" : "hidden boxes bridged over, and those where chains stop (hosts lane, hand work, caches) left out with their links"}.</div>` : ""}
      <b>Fed by</b><ul>${((view.kindsOff.size ? ins1 : insAll)[id] || []).map(e => `<li>${link(e.from)}${e.label ? " — " + esc(e.label) : ""}</li>`).join("") || "<li>nothing (a source)</li>"}</ul>
      <b>Feeds</b><ul>${((view.kindsOff.size ? outs1 : outsAll)[id] || []).map(e => `<li>${link(e.to)}${e.label ? " — " + esc(e.label) : ""}</li>`).join("") || "<li>nothing (an end product)</li>"}</ul>
      <div style="color:#666">${fullUp} upstream, ${fullDown} downstream in the whole map.</div>`;
    info.style.display = "block";
    nav.classList.add("focus");
    nav.querySelectorAll("rect.n").forEach(r => { if (upSet.has(r.dataset.id) || downSet.has(r.dataset.id)) r.classList.add("on"); });
    setVB(vb.x, vb.y, vb.width, vb.height);  // clamped again for the narrower free area
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
    setVB(vb.x, vb.y, vb.width, vb.height);  // clamped again for the narrower free area
    info.querySelector(".close").onclick = () => clearFocus(true);
    info.querySelector("#fopen").onclick = () => openFolder(g.folder);
    info.querySelectorAll("a[data-go]").forEach(a => (a.onclick = () => goTo(a.dataset.go)));
  }
  function openFolder(folder, then) {
    view.open.add(folder);
    if (then) { selected = then; render(false); if (visible.has(then)) centreOn(then, false); }
    else renderKeeping();  // the folder's boxes appear where the folder was
    writeHash();
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
    clearTimeout(pending);
    // what the pointer is over, as the hover found it (pointerPick): a click opens what the hover lit
    const at = pointerAt(e.target, e.clientX, e.clientY), got = pointerPick(at);
    const back = sourceClick(e), lineFirst = lastPointer === "touch" || (back && at.line !== null);
    // a click on a line opens the box it leads to, Cmd (Ctrl off a Mac; Alt too) the box it comes from; a tap or a
    // Cmd-click takes the line under the pointer over a grown card; a line whose box is not drawn does nothing, rather
    // than clearing the view as a click on empty map would
    const li = lineFirst && at.line !== null ? at.line : got.edge !== undefined ? got.edge : at.line;
    const edge = li !== null && li !== undefined ? lay.edges[li] : null;
    const end = edge && lineEnd(edge, back, id => !!nodeEl[id]);
    const card = got.box && got.box !== at.box ? got.box : null;
    if (edge && !at.box && !card && !end) {  // a line whose box is not drawn does nothing, unless a lane name is over it
      const lane = laneAt(e.clientX, e.clientY);
      if (lane !== null) zoomLane(lane);
      return;
    }
    const t = clickTarget(at.box, card, got.box && !lineFirst ? null : end, lineFirst);
    if (t.clear) {
      const lane = laneAt(e.clientX, e.clientY);  // a lane name over empty map: zoom to that lane
      if (lane !== null) { zoomLane(lane); return; }
      clearFocus(true); return;
    }
    // a line's box is centred, which moves the map, and a trimmed redraw moves the boxes: either waits out a
    // double-click, so its second click does not land on whatever box moved under the pointer
    if (t.line || view.trim) { if (e.detail === 1) pending = setTimeout(() => pick(t.pick, t.line ? "pan" : undefined), 300); }
    else pick(t.pick);
  });
  let pending = null, lastPointer = "mouse";
  wrapEl.addEventListener("pointerdown", e => (lastPointer = e.pointerType), true);
  wrapEl.addEventListener("dblclick", e => {
    clearTimeout(pending);
    if (e.target.classList && e.target.classList.contains("eh")) return;  // a double-click on a line is a click on it
    const got = pickHover(e.target, e.clientX, e.clientY), g = got.box ? nodeEl[got.box] : null;
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
    updateFar();
  }
  q.addEventListener("input", () => runSearch(false));
  q.addEventListener("keydown", e => {
    if (e.key !== "Enter" || !found.length) return;
    const id = found[fi++ % found.length];
    if (!pickable(id)) goTo(id);
    else pick(id, "zoom");
  });
  document.addEventListener("keydown", e => {
    if (e.target.matches("input:not([type=checkbox]):not([type=radio]):not([type=button]),textarea,select") || e.target.isContentEditable || e.metaKey || e.ctrlKey || e.altKey) return;  // typing in any field, the site header's search too
    if (e.key === "Escape") clearFocus(true);
    if (e.key === "f" || e.key === "F") fit();
    if ((e.key === "h" || e.key === "H") && !e.shiftKey) setClean(!clean);  // not with Shift, held for the magnifier
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
    browse.open = false; document.getElementById("more").open = false;  // the phone Menu too
    focusOn(a.dataset.file);
  });
  fileIn.addEventListener("keydown", e => { if (e.key === "Enter") pickFile(); });

  /* ---- start-here buttons: a preset file view for the questions people ask first */
  const presetBtns = DATA.presets.map((pr, i) =>
    `<button data-preset="${i}" title="${esc(byId[pr.focus].label)}, ${pr.up} back and ${pr.down} on">${esc(pr.label)}</button>`).join("");
  document.getElementById("presets").innerHTML = presetBtns;
  document.getElementById("startmenu").hidden = !DATA.presets.length;
  function usePreset(e) {
    const b = e.target.closest("button[data-preset]");
    if (!b) return;
    const pr = DATA.presets[Number(b.dataset.preset)], steps = v => (v === "all" ? Infinity : v);
    document.getElementById("startmenu").open = false; document.getElementById("more").open = false;
    view.focus = selected = pr.focus; view.up = steps(pr.up); view.down = steps(pr.down);
    view.lanes = new Set(allLanes); view.kindsOff.clear(); view.trim = false;  // the preset's step counts as written
    fileIn.value = byId[pr.focus].path || byId[pr.focus].label;
    syncControls(); render(false); writeHash();
  }
  document.getElementById("presets").addEventListener("click", usePreset);

  /* ---- menus: opening one closes the others (a menu inside an open one stays); a click elsewhere closes them all.
     On a phone the menus and buttons after Find move into the Menu panel. */
  const menus = [...document.querySelectorAll("details.menu")];
  menus.forEach(m => m.addEventListener("toggle", () => {
    if (!m.open) return;
    menus.forEach(o => { if (o !== m && o.open && !o.contains(m) && !m.contains(o)) o.open = false; });
  }));
  document.addEventListener("click", e => {
    if (e.target.closest && e.target.closest("details.menu")) return;
    menus.forEach(m => (m.open = false));
  });
  const moveIds = ["startmenu", "viewmenu", "lanes", "browse", "btns"], more = document.getElementById("morebody");
  const homes = moveIds.map(id => { const el = document.getElementById(id), ph = document.createComment(id); el.before(ph); return [el, ph]; });
  const phone = matchMedia("(max-width: 900px)");
  // Fit stays on the toolbar on a phone, beside More, as the control used most
  const fitBtn = document.getElementById("fit"), fitHome = document.createComment("fit");
  fitBtn.before(fitHome);
  function placeMenus() {
    for (const [el, ph] of homes) { if (phone.matches) more.append(el); else ph.before(el); }
    if (phone.matches) document.getElementById("more").before(fitBtn); else fitHome.before(fitBtn);
    updateNav();
  }
  phone.addEventListener("change", () => { menus.forEach(m => (m.open = false)); placeMenus(); });
  placeMenus();

  /* ---- tour: a few steps over the main controls for a first visit; Skip or Done ends it for good on this browser,
     and the ? button runs it again. A visit that opens a shared link (any address after #) is not interrupted. */
  const tour = document.getElementById("tour"), TOUR_KEY = "pipelineMapTourDone";
  const TOUR = [
    { at: ["#file", "#browse"], title: "Pick a file",
      text: "Type a file's name, or find it by folder under Browse. The map then draws its chain: everything it is built from on the left, everything built from it on the right." },
    { at: ["#startmenu"], title: "Or start from a common chain",
      text: "Start opens the chains people ask about most" + (DATA.presets.length ? ": " + DATA.presets.map(p => p.label).join(", ") + "." : ".") },
    { at: [], title: "Click a box",
      text: "A click lights up what feeds the box (amber) and what it feeds (blue), and opens its details on the right. Double-click a box to draw its chain on its own." },
    { at: ["#viewmenu"], title: "Change how it looks",
      text: "View holds the drawing options: compact boxes (names only, on to start with), group by folder, edge labels and highlighted chain only (just the chain of the box you clicked); two pointer settings, hover highlights and near pipeline on click; and dark background and clean view." },
    { at: ["#lanes"], title: "Filter",
      text: "Filters picks the lanes and kinds of box, and whether parked features and retired tools show. Clear filters, at the foot of Filters or under the toolbar, puts them back." },
    { at: ["#q"], title: "Find text",
      text: "Find highlights the boxes whose name, path or description holds the text you type." },
    { at: [], title: "Hover",
      text: "Zoomed out, hover a line to light its chain and grow its boxes to a readable size, or hover a box to do the same for its neighbours. The note by the pointer names where the chain stops. Click a line to open the box it leads to, Cmd-click (Ctrl-click off a Mac) for the box it comes from. Click a lane's name to zoom to that lane, and hold Shift for a magnifier." },
    { at: ["#fit", "#btns"], title: "Move around and share",
      text: "Scroll or pinch to zoom and drag to pan; Fit shows the whole map. Share copies a link that opens this exact view. The ? button runs this tour again." },
  ];
  let tourAt = -1, tourOn = [];
  const shown = el => el && el.offsetParent !== null && !(el.closest("#morebody") && !document.getElementById("more").open);  // inside a shut phone Menu counts as hidden
  function tourShow(i) {
    tourOn.forEach(el => el.classList.remove("tour-on"));
    tourAt = i;
    const step = TOUR[i];
    // a control folded into the phone menu is pointed at through the Menu button
    tourOn = step.at.map(sel => document.querySelector(sel)).map(el => (shown(el) ? el : document.querySelector("#more"))).filter(shown);
    tourOn = [...new Set(tourOn)];
    tourOn.forEach(el => el.classList.add("tour-on"));
    tour.querySelector(".tt").textContent = step.title;
    tour.querySelector(".tx").textContent = step.text;
    tour.querySelector(".tn").textContent = `${i + 1} of ${TOUR.length}`;
    tour.querySelector(".back").hidden = i === 0;
    tour.querySelector(".next").textContent = i === TOUR.length - 1 ? "Done" : "Next";
    tour.hidden = false;
    const w = tour.offsetWidth, h = tour.offsetHeight;
    if (tourOn.length) {
      const rs = tourOn.map(el => el.getBoundingClientRect());
      const left = Math.min(...rs.map(r => r.left)), bottom = Math.max(...rs.map(r => r.bottom));
      tour.style.left = Math.max(10, Math.min(left, innerWidth - w - 10)) + "px";
      tour.style.top = Math.max(10, Math.min(bottom + 12, innerHeight - h - 10)) + "px";
    } else {  // the map itself: the middle of the screen
      tour.style.left = (innerWidth - w) / 2 + "px";
      tour.style.top = (innerHeight - h) / 2 + "px";
    }
    tour.querySelector(".next").focus({ preventScroll: true });  // a scroll would slide the toolbar under the site header
  }
  function tourEnd() {
    tourOn.forEach(el => el.classList.remove("tour-on"));
    tourOn = []; tourAt = -1; tour.hidden = true;
    try { localStorage.setItem(TOUR_KEY, "1"); } catch (e) { /* storage off: the tour may show again next visit */ }
  }
  tour.querySelector(".next").onclick = () => (tourAt === TOUR.length - 1 ? tourEnd() : tourShow(tourAt + 1));
  tour.querySelector(".back").onclick = () => tourShow(Math.max(0, tourAt - 1));
  tour.querySelector(".skip").onclick = tourEnd;
  document.getElementById("tourbtn").onclick = () => { menus.forEach(m => (m.open = false)); tourShow(0); };
  addEventListener("resize", () => { if (tourAt >= 0) tourShow(tourAt); });
  document.addEventListener("keydown", e => { if (tourAt >= 0 && e.key === "Escape") { e.stopImmediatePropagation(); tourEnd(); } }, true);
  let tourDone = false;
  try { tourDone = localStorage.getItem(TOUR_KEY) === "1"; } catch (e) { tourDone = false; }
  if (!tourDone && !location.hash) setTimeout(() => tourShow(0), 400);

  /* ---- share: the address with the view as it is now, zoom and position included, copied to the clipboard */
  document.getElementById("share").onclick = () => {
    writeHash(true);
    const done = t => { hits.textContent = t; setTimeout(() => { if (hits.textContent === t) runSearch(true); }, 4000); };
    if (navigator.clipboard) navigator.clipboard.writeText(location.href).then(() => done("Link copied"), () => done("Copy the address bar to share"));
    else done("Copy the address bar to share");
  };

  /* ---- lanes, kinds and status filters */
  const kindsBox = document.getElementById("kindlist");
  /* Every kind but folder can be hidden; boxes where chains stop are then left out rather than bridged over
     (filtered()). */
  const hideable = k => Object.hasOwn(DATA.kinds, k) && k !== "folder";
  kindsBox.innerHTML = Object.entries(DATA.kinds).filter(([k]) => hideable(k)).map(([k, [label, fill, ink]]) =>
    `<label><input type="checkbox" data-kind="${esc(k)}" checked> <span class="sw" style="background:${esc(fill)};border-color:${esc(ink)}"></span>${esc(label)}</label>` +
    ` <a data-kindonly="${esc(k)}">only</a>`).join("<br>");
  kindsBox.addEventListener("change", e => {
    const k = e.target.dataset.kind;
    if (!k) return;
    if (e.target.checked) view.kindsOff.delete(k); else view.kindsOff.add(k);
    renderKeeping(); writeHash();
  });
  // "only": every other kind hidden as if unticked (bridged over, but chain stops left out with their links), and the
  // view refit as a lane's "only" does; a second click on it shows every kind again (onlyOne)
  kindsBox.addEventListener("click", e => {
    const only = e.target.dataset && e.target.dataset.kindonly;
    if (!only) return;
    view.kindsOff = new Set(onlyOne(Object.keys(DATA.kinds).filter(hideable), [...view.kindsOff], only));
    syncControls(); render(false); writeHash();
  });
  document.getElementById("compact").onchange = e => { view.compact = e.target.checked; renderKeeping(); writeHash(); };
  document.getElementById("group").onchange = e => { view.group = e.target.checked; view.open.clear(); renderKeeping(); writeHash(); };
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
    document.getElementById("hover").checked = view.hover;
    document.getElementById("near").checked = view.near;
    syncSpread();
  }
  lanesBox.addEventListener("change", e => {
    const lane = e.target.dataset.lane;
    if (!lane) return;
    if (e.target.checked) view.lanes.add(lane); else view.lanes.delete(lane);
    renderKeeping(); writeHash();
  });
  lanesBox.addEventListener("click", e => {
    const only = e.target.dataset && e.target.dataset.only;
    if (!only) return;
    // a second click on the lane shown alone shows every lane again, as a kind's "only" does (onlyOne)
    const off = onlyOne(allLanes, allLanes.filter(d => !view.lanes.has(d)), only);
    view.lanes = new Set(allLanes.filter(d => !off.includes(d))); syncControls(); render(false); writeHash();
  });
  document.getElementById("parked").onchange = e => { view.parked = e.target.checked; renderKeeping(); writeHash(); };
  document.getElementById("retired").onchange = e => { view.retired = e.target.checked; renderKeeping(); writeHash(); };
  document.getElementById("trim").onchange = e => { view.trim = e.target.checked; render(selected === null); writeHash(); };
  document.getElementById("hover").onchange = e => {  // hover highlights on or off; off clears a hover now showing
    view.hover = e.target.checked;
    if (!view.hover) { setHover(null); setEdgeHover(null); }
    writeHash();
  };
  document.getElementById("near").onchange = e => {  // a click's chain stops where a hover's does: the lit box again
    view.near = e.target.checked;
    if (view.trim && selected !== null) render(false);
    else if (selected !== null && nodeEl[selected]) select(selected, true);
    writeHash();
  };
  document.getElementById("labels").onchange = e => { document.getElementById("elabels").classList.toggle("hidden", !e.target.checked); showStatus(sub); };

  /* ---- address bar: #focus=<id>&up=all&down=2&lanes=a,b&show=parked,retired&trim=1&hidekind=generator&compact=0
     &folders=1&open=<folder>,<folder>&node=<id>, and with share also at=<x>,<y>,<width>,<aspect> (the zoom, position and lane stretch) */
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
    if (!view.hover) h.set("hover", "0");  // hover highlights are on by default
    if (view.near) h.set("near", "1");
    if (view.steps) h.set("steps", String(view.steps));
    if (withView && view.steps && view.boxCap) h.set("cap", String(+view.boxCap.toFixed(3)));  // with the sharer's box size  // (an older width= link is ignored: it meant wider boxes)
    if (view.group) { h.set("folders", "1"); if (view.open.size) h.set("open", [...view.open].join(",")); }
    if (selected) h.set("node", selected);
    if (withView) h.set("at", [vb.x, vb.y, vb.width].map(v => Math.round(v)).concat(lay.aspect ? [+lay.aspect.toFixed(4)] : []).join(","));  // with the sharer's lane stretch
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
    view.hover = h.get("hover") !== "0";
    view.near = h.get("near") === "1";
    const st = Math.round(Number(h.get("steps")) || 0);
    view.steps = st > 0 ? Math.max(3, st) : 0;  // at least 3, as the slider; clamped to the map's columns when it is drawn
    const cap = Number(h.get("cap"));
    view.sharedCap = cap > 0 ? Math.min(BOX_GROW, Math.max(1, cap)) : 0;
    view.group = h.get("folders") === "1";
    view.open = new Set(view.group && h.get("open") ? h.get("open").split(",") : []);
    const node = h.get("node");
    selected = node && (Object.hasOwn(byId, node) || node.startsWith("folder:")) ? node : null;
    if (selected && Object.hasOwn(byId, selected) && !view.focus && byId[selected].status in view) view[byId[selected].status] = true;  // keep a shared box in view
    fileIn.value = view.focus ? byId[view.focus].path || byId[view.focus].label : "";
    syncControls();
  }
  /* A shared link's view: at=x,y,width[,aspect], the zoom and position, and the screen shape the sharer's lanes were
     stretched to (so the same y lands in the same lane); null when there is none or it is malformed. */
  function sharedView() {
    const at = (new URLSearchParams(location.hash.slice(1)).get("at") || "").split(",").map(Number);
    if (at.length < 3 || at.length > 4 || at.some(v => !Number.isFinite(v)) || at[2] <= 0 || at[3] < 0) return null;
    return at;
  }
  function restoreView(at) {  // kept to the window's shape
    if (!at) return false;
    const r = wrapEl.getBoundingClientRect();
    setVB(at[0], at[1], at[2], at[2] * r.height / r.width);
    return true;
  }
  function arrive(first) {  // first load: a file view opens at Fit; a later address change pans to the selected box
    readHash();
    const at = sharedView();
    render(false, at ? at[3] || 0 : undefined);  // an older link without the shape: no stretch, as it was drawn then
    if (restoreView(at) || !selected || !visible.has(selected) || view.trim) return;
    if (!view.focus) centreOn(selected, true);
    else if (!first) centreOn(selected, false);
  }
  arrive(true);
  window.addEventListener("hashchange", () => arrive(false));
}
