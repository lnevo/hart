/* The pipeline map viewer's pure helpers beside the layout (pipeline_map_layout.js): the lane tags, what a click or
   the pointer picks, link ends and tag places, the chains and hubs a hover walks, fitting and clamping the view,
   and hiding, contracting and folding boxes. No page state. build_pipeline_map.py inlines this file after the
   layout, in the same script (its "use strict" holds here too); under node it exports these functions, which the
   layout's exports include, and runs strict as in the page. */
"use strict";

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

/* The main line through box focus in a drawing of these edges, as a Start button lights it: the longest run of links
   from a source into focus, then the longest run on from focus to an end, as box ids in order. Side links and links
   from a box to itself are not walked, nor on through a box where stops(box) is true (it can end the line). up and
   down, when given, are the boxes drawn on each side (the steps the view shows): the upstream run stays inside up,
   the downstream run inside down. A link that would close a loop is skipped, and the downstream run does not pass
   through a box of the upstream one. Ties go to the neighbour whose id sorts first, so the same drawing always gives
   the same line. */
function mainLine(edges, focus, { stops = () => false, up = null, down = null } = {}) {
  const ins = new Map(), outs = new Map();
  const add = (m, k, v) => { if (!m.has(k)) m.set(k, new Set()); m.get(k).add(v); };
  edges.forEach(e => { if (!e.side && e.from !== e.to) { add(outs, e.from, e.to); add(ins, e.to, e.from); } });
  const longest = (adj, within, blocked) => {  // the longest run from focus along adj, focus first (depth first)
    // a run is memoised only when no loop was cut below it: a cut run depends on the path it was reached by
    const memo = new Map(), onPath = new Set();
    const go = v => {
      if (memo.has(v)) return { run: memo.get(v), cut: false };
      onPath.add(v);
      let best = [v], cut = false;
      const next = v !== focus && stops(v) ? [] : [...(adj.get(v) || [])].sort();
      for (const w of next) {
        if (blocked.has(w) || (within && !within.has(w))) continue;
        if (onPath.has(w)) { cut = true; continue; }
        const got = go(w);
        cut = cut || got.cut;
        if (got.run.length + 1 > best.length) best = [v, ...got.run];
      }
      onPath.delete(v);
      if (!cut) memo.set(v, best);
      return { run: best, cut };
    };
    return go(focus).run;
  };
  const upRun = longest(ins, up, new Set()).reverse();
  const downRun = longest(outs, down, new Set(upRun.slice(0, -1)));
  return [...upRun, ...downRun.slice(1)];
}

/* The main line a preset names for a Start button on box focus ("line" in pipeline_map.json: box ids in order, which
   build_pipeline_map.py checks), or null when no preset on focus names one (the page then lights mainLine). */
function presetLine(presets, focus) {
  const pr = (presets || []).find(p => p.focus === focus && Array.isArray(p.line) && p.line.length);
  return pr ? pr.line : null;
}
/* The boxes beside that line the preset also lights ("also": each linked to a line box, either way), or [] */
function presetAlso(presets, focus) {
  const pr = (presets || []).find(p => p.focus === focus && Array.isArray(p.line) && p.line.length);
  return pr && Array.isArray(pr.also) ? pr.also : [];
}
/* A drawing (nodes, edges) with a preset's line joined to it: each line box and each link from one line box to the
   next that the drawing left out (steps, hub stops, filters) is added from all (the whole map's nodes and edges), so
   the whole line is drawn; also (presetAlso) joins the same way, with its links to line boxes. What the drawing already holds is kept as it is, in its order; where all holds a box or a
   link twice, the first copy is taken. */
function withLine(nodes, edges, all, line, also = []) {
  const key = e => e.from + "\u0000" + e.to, ids = new Set(nodes.map(n => n.id)), byId = new Map();
  all.nodes.forEach(n => { if (!byId.has(n.id)) byId.set(n.id, n); });
  const pairs = new Set(line.slice(1).map((id, i) => line[i] + "\u0000" + id)), onLine = new Set(line), side = new Set(also);
  const wanted = e => pairs.has(key(e)) || (side.has(e.from) && onLine.has(e.to)) || (onLine.has(e.from) && side.has(e.to));
  const has = new Set(edges.map(key)), addEdges = [];
  all.edges.forEach(e => { if (wanted(e) && !has.has(key(e))) { has.add(key(e)); addEdges.push(e); } });
  const addNodes = [...new Set(line.concat(also))].filter(id => !ids.has(id) && byId.has(id)).map(id => byId.get(id));
  return { nodes: nodes.concat(addNodes), edges: edges.concat(addEdges) };
}

/* How faint a box or link steps links from a hovered line shows: "" (full) up to 2, "2" for 3 and 4, "3" beyond. */
function fadeOf(steps) {
  return steps <= 2 ? "" : steps <= 4 ? "2" : "3";
}
/* Which boxes grow first when zoomed out (lower first; 4: not grown): the hovered box or the hovered line's ends (0),
   the rest the hover lights (1), the selected box and search hits (2), then the selected box's neighbours (3, class
   "sn": every box a hover on it grew, so they stay grown after the click). A Start button's main line (class "ml",
   mainLine) ranks with the selected box. has(c): whether the box has class c. */
function growRank(isHovered, has) {
  return isHovered ? 0 : has("hn") ? 1 : has("sel") || has("hit") || has("ml") ? 2 : has("sn") ? 3 : 4;
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

/* The links of a graph whose boxes groupOf maps into group boxes (isGroup: whether an id is one): links between two
   boxes are merged and counted, links inside one group dropped. A merged link of two or more is labelled "N links", one
   touching a group takes `one` (a single link's own label means little there), and a merged link is a side link only
   when every link in it is. */
function mergeLinks(edges, groupOf, isGroup, one = "") {
  const merged = new Map();
  for (const e of edges) {
    const from = groupOf[e.from] || e.from, to = groupOf[e.to] || e.to;
    if (from === to) continue;
    const key = from + "\u0000" + to;
    if (!merged.has(key)) merged.set(key, { from, to, n: 0, label: e.label, side: e.side });
    const m = merged.get(key);
    m.n++;
    if (!e.side) m.side = undefined;
  }
  return [...merged.values()].map(m => {
    const grouped = isGroup(m.from) || isGroup(m.to);
    const label = m.n > 1 ? `${m.n} links` : grouped ? one : m.label;
    const e = label ? { from: m.from, to: m.to, label } : { from: m.from, to: m.to };
    if (m.side) e.side = m.side;
    return e;
  });
}

/* One box per folder that holds two or more of the boxes, except the folders named in open; links between
   folders are merged and counted, links inside one folder dropped (mergeLinks). members maps each group id to its
   box ids. */
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
  const isGroup = id => Object.hasOwn(members, id) || id.startsWith("folder:");
  return { nodes: out, edges: mergeLinks(edges, groupOf, isGroup), members, groupOf };
}

/* The lanes not in open, each closed to one box ("lane:<domain>", kind "lane") where its first box was, so the lane is
   a thin strip that keeps its links to the open lanes, merged and counted (mergeLinks; a single one reads "1 link").
   label(domain, count) gives the closed box its name. members and groupOf as groupByFolder's. */
function collapseLanes(nodes, edges, open, label) {
  const groupOf = {}, members = {}, out = [];
  for (const n of nodes) {
    if (open.has(n.domain)) { out.push(n); continue; }
    const id = "lane:" + n.domain;
    groupOf[n.id] = id;
    if (!members[id]) { members[id] = []; out.push({ id, lane: n.domain, kind: "lane", status: "live", domain: n.domain, path: "" }); }
    members[id].push(n.id);
  }
  out.forEach(n => { if (n.kind === "lane") { n.label = label(n.lane, members[n.id].length); n.desc = `${members[n.id].length} boxes, closed`; } });
  return { nodes: out, edges: mergeLinks(edges, groupOf, id => id.startsWith("lane:"), "1 link"), members, groupOf };
}

/* The lane overview's drawing, in its own units: one card per lane stacked in the graph's order (cards: {id, x, y, w,
   h}), and one arc per bundle of links between two lanes (arcs: {from, to, n, d, lx, ly, w}): a bundle down the list
   on the right of the cards, one up it on the left, bulging further the more lanes it spans, so arcs nest; each card
   side spreads the ends of its arcs over its height. w is the arc's stroke width, by its share of the biggest bundle,
   and head the arrowhead at its end, sized to the stroke (a marker would scale with it). left, width and height: the
   drawing's extent, arcs included. */
function laneOverview(lanes, bundles, cardW = 600, cardH = 96, gap = 28, span = 34) {
  const cards = lanes.map((l, i) => ({ id: l.id, x: 0, y: i * (cardH + gap), w: cardW, h: cardH }));
  const at = {};
  cards.forEach((c, i) => (at[c.id] = i));
  const list = bundles.filter(b => b.from in at && b.to in at && b.from !== b.to);
  const ends = {};  // card index and side -> its arcs' ends, ordered by the other end, to spread over the card's height
  list.forEach((b, k) => {
    const i = at[b.from], j = at[b.to], side = j > i ? "r" : "l";
    (ends[i + side] ||= []).push([j, k, "from"]);
    (ends[j + side] ||= []).push([i, k, "to"]);
  });
  const y = {};
  for (const key in ends) {
    const i = Number(key.slice(0, -1)), c = cards[i], list2 = ends[key].sort((p, q) => p[0] - q[0] || p[1] - q[1]);
    list2.forEach(([, k, end], m) => ((y[k] ||= {})[end] = c.y + 12 + (c.h - 24) * (m + 0.5) / list2.length));
  }
  const most = Math.max(1, ...list.map(b => b.n));
  let reach = 0;
  const arcs = list.map((b, k) => {
    const i = at[b.from], j = at[b.to], right = j > i, bulge = 26 + Math.abs(j - i) * span;
    const x0 = right ? cardW : 0, dir = right ? 1 : -1, cx = x0 + dir * bulge, y0 = y[k].from, y1 = y[k].to;
    const w = 1.5 + 9 * Math.sqrt(b.n / most), len = 5 + w * 0.7, half = 3 + w * 0.6, f = v => v.toFixed(1);
    reach = Math.max(reach, bulge * 0.75 + 24);
    return { from: b.from, to: b.to, n: b.n, side: b.side || 0, w, lx: x0 + dir * bulge * 0.75, ly: (y0 + y1) / 2,
             d: `M${x0},${f(y0)} C${cx},${f(y0)} ${cx},${f(y1)} ${f(x0 + dir * len * 0.8)},${f(y1)}`,
             head: `M${x0},${f(y1)} L${f(x0 + dir * len)},${f(y1 - half)} L${f(x0 + dir * len)},${f(y1 + half)} z` };
  });
  const height = cards.length ? cards[cards.length - 1].y + cardH : 0;
  return { cards, arcs, left: -reach, width: cardW + 2 * reach, height };
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
  module.exports = { stopKind, stopsNote, fitPad, clearOf, pointerPick, boxAt, hoverStop, hoverWalks, fadeOf, growRank, mainLine, presetLine, presetAlso, withLine, sourceClick, sourceKey, isCache, stopsChain, hubs, liveHubs, HUB_OUT, lineEnd, lighten, stripRoom, pathSegments, clickTarget, growRect, placeTags, edgeTip, linkChain, laneTagTops, chainOf, showsAll, fitView, clampView, contract, hideBoxes, folderOf, mergeLinks, groupByFolder, collapseLanes, laneOverview, githubUrl };
}
