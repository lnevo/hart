/* Layout for the pipeline map pages (docs/pipeline-map/index.html and the website copy): pure functions, no page state.
   build_pipeline_map.py inlines this file and then pipeline_map_view.js into one script in the page, after the graph
   data (DATA). The layout is a layered (Sugiyama) drawing, left to right, with one horizontal lane per domain; it
   runs in the page so any subset (some lanes, or the chain around one file) gets its own compact drawing. Under node
   the file exports these functions, for the unit tests (tools/audit/tests/test_pipeline_map.py). */
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
/* Which boxes grow first when zoomed out (lower first; 4: not grown): the hovered box or the hovered line's ends (0),
   the rest the hover lights (1), the selected box and search hits (2), then the selected box's neighbours (3, class
   "sn": every box a hover on it grew, so they stay grown after the click). has(c): whether the box has class c. */
function growRank(isHovered, has) {
  return isHovered ? 0 : has("hn") ? 1 : has("sel") || has("hit") ? 2 : has("sn") ? 3 : 4;
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
  module.exports = { settleFrom, boxTransform, BOX_GROW, spreadFor, spreadGeo, onlyOne, stopKind, stopsNote, fitPad, clearOf, pointerPick, boxAt, hoverStop, hoverWalks, fadeOf, growRank, sourceClick, sourceKey, isCache, stopsChain, hubs, liveHubs, HUB_OUT, WIDE, NARROW, lineEnd, lighten, stripRoom, pathSegments, clickTarget, growRect, placeTags, edgeTip, linkChain, layout, wrap, nodeHeight, inversions, stepTicks, laneTagTops, firstColumnIsRaw, chainOf, showsAll, fitView, clampView, contract, hideBoxes, folderOf, groupByFolder, githubUrl };
}
