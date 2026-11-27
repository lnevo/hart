/* The pipeline map page's viewer: app() holds the page's state, drawing, hover, address and input. It runs only in
   the page, inlined by build_pipeline_map.py after pipeline_map_layout.js in the same script (so the layout's
   functions and its "use strict" apply here); it is never loaded under node. app() is one function in six files,
   inlined in this order as one text: this file (the state, which boxes are shown, the drawing),
   pipeline_map_view_frame.js (overview in the corner, headers, dark mode, lane zoom, pan and zoom),
   pipeline_map_view_lanes.js (the lane overview the page opens on, open lanes, the efficiency overlay),
   pipeline_map_view_rail.js (the filter rail, its chips, the list of boxes, the info panel's lists),
   pipeline_map_view_nav.js (history, the trail, the status line, search, keys, the address) and
   pipeline_map_view_input.js (magnifier, selection, search, filters, menus, tour, share, address; it closes app() and
   calls it). None of the six is a script on its own. */

function app() {
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const byId = {};
  DATA.nodes.forEach(n => (byId[n.id] = n));
  DATA.kinds.folder ||= ["Folder", "#f8fafc", "#334155"];
  DATA.kinds.lane ||= ["Closed lane", "#f1f5f9", "#475569"];
  DATA.presets ||= [];
  const insAll = {}, outsAll = {};
  DATA.edges.forEach(e => { (outsAll[e.from] ||= []).push(e); (insAll[e.to] ||= []).push(e); });
  const domainLabel = {};
  DATA.domains.forEach(d => (domainLabel[d.id] = d.label));
  const wrapEl = document.getElementById("wrap"), info = document.getElementById("info");
  const allLanes = DATA.domains.map(d => d.id);

  // f: the ticked filter values (pipeline_map_facets.js); hide: Hide the rest (left out, not faded)
  const view = { f: emptyFacets(), hide: false, focus: null, up: Infinity, down: Infinity, trim: false,
                 compact: true, group: false, open: new Set(), hover: true, near: false, steps: 0, spread: 1,
                 overview: true, laneOpen: new Set(), eff: false, line: false };  // overview: the lane cards; laneOpen: the lanes drawn open; line: a Start button's main line
  const boxVals = {};  // each box's filter values
  DATA.nodes.forEach(n => (boxVals[n.id] = boxValues(n)));
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
  /* Filters fade what they do not match; with Hide the rest they leave it out: a lane not ticked is not drawn, a box
     of an unticked kind, step type or writer count is bridged over (filtered()), a link of an unticked side dropped. */
  const laneOn = d => !view.hide || !view.f.lane.size || view.f.lane.has(d);
  const BRIDGED = ["kind", "step", "writers"];
  const bridging = () => view.hide && BRIDGED.some(k => view.f[k].size);
  // whether the lane filter draws a box (status and kind are applied in filtered()); the picked file always shows
  const isShown = id => id === view.focus || laneOn(nodeOf(id).domain);
  /* The graph after the status and kind filters: parked and retired boxes are left out unless ticked, and with Hide
     the rest boxes the filters do not match are bridged over, so the links run on through them, except where chains
     stop (endsChain: the hosts lane, host, hand-work and cache boxes), which are left out with their links
     (hideBoxes). The picked file always stays. */
  let g1Key = null, g1 = null, ins1 = {}, outs1 = {};
  function filtered() {
    const st = drawnStatus(view.f, view.hide), sides = view.hide ? view.f.side : new Set();
    const key = JSON.stringify([[...st].sort(), bridging() && BRIDGED.map(k => [...view.f[k]].sort()), [...sides].sort(), view.focus]);
    if (key === g1Key) return g1;
    const ok = n => n.id === view.focus || st.has(n.status || "live");
    const nodes = DATA.nodes.filter(ok), ids = new Set(nodes.map(n => n.id));
    const edges = DATA.edges.filter(e => ids.has(e.from) && ids.has(e.to) && (!sides.size || sides.has(edgeSide(e))));
    g1 = !bridging() ? { nodes, edges }
      : hideBoxes(nodes, edges, id => id !== view.focus && !boxMatches(boxVals[id], view.f, BRIDGED), endsChain);
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
    if (view.laneOpen.size && !view.focus) {  // lanes opened from the overview: the others closed to one box each
      groups = collapseLanes(nodes, edges, view.laneOpen, closedLaneName);
      ({ nodes, edges } = groups);
      nodes.forEach(n => { if (n.kind === "lane") gNodes[n.id] = n; });
    } else if (view.group && !view.focus) {  // folders: the whole map only; a file's chain is short enough already
      groups = groupByFolder(nodes, edges, view.open);
      ({ nodes, edges } = groups);
      nodes.forEach(n => { if (n.kind === "folder") gNodes[n.id] = n; });
      nodes.forEach(n => { if (n.kind === "folder" && !n.path && n.folder.startsWith("outside the repo: ")) n.label = "outside the repo: " + domainLabel[n.folder.slice(18)]; });
    }
    if (view.compact) nodes = nodes.map(n => (gNodes[n.id] ? n : { ...n, desc: "", path: "" }));
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
      // grown in growRank's order, each group busiest first
      const rank = id => growRank(id === hoverId || hoverEnds.has(id), c => nodeEl[id].classList.contains(c));
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
      // a Start button's main line: each card moved up or down clear of the line's cards before it, so all of them show
      const line = [];
      lit.forEach((n, i) => {
        if (n.id === hoverId) { line.push(boxes[i]); return; }  // placed first and already clear: the line's cards clear it
        if (!nodeEl[n.id].classList.contains("ml")) return;
        boxes[i] = clearOf(boxes[i], blocked.concat(line), area);
        line.push(boxes[i]);
      });
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
      p.push(effMarks(byId[n.id] || n, bw, bh), "</g>");
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
    // the lane overview while nothing asks for the map: no file, no changed filter (a filter changed there leaves it)
    if (view.overview && !view.focus && !filtersChanged()) { drawOverview(); return; }
    view.overview = false;
    if (ovSvg) { ovSvg = null; wrapEl.classList.remove("ov"); }
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
    // a lane closed to one box stays a thin strip: the open lanes take the height the screen has to spare
    const lanes = view.laneOpen.size && !view.focus ? DATA.domains.map(d => (view.laneOpen.has(d.id) ? d : { ...d, thin: true })) : DATA.domains;
    lay = layout(sub.nodes, sub.edges, lanes, aspect, geo);
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
    applyFade();
    if (selected && !visible.has(selected) && visible.has(groups.groupOf[selected])) selected = groups.groupOf[selected];  // folded away: its folder
    if (selected && visible.has(selected)) select(selected, true);
    else { const had = selected; selected = null; info.style.display = "none"; if (had) writeHash(); }
    if (!old && !asked && !settled && Math.abs(fitAspect() - screen) > 0.01) { render(false, undefined, true); return; }  // the panel changed the area
    const line = view.line && view.focus && !selected ? showLine() : null;  // a Start button's main line
    if (!old && line) fitBoxes(line);  // fitted to the main line, not the whole chain
    else if (!old) fit();  // after the info panel is shown or hidden, so the fit leaves room for it
    else setVB(vb.x, vb.y, vb.width, vb.height);  // clamped again against the panel as it is now
    updateNav();
    announce();
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
  // the filters as they start; Start over goes back to these
  const filtersChanged = () => facetsOn(view.f) || view.hide ||
    !view.compact || view.group || view.trim;  // Edge labels is not kept in the address, so not counted; Steps is not counted: its row would push the map down on release

  function showStatus(sub) {
    showDepth();
    drawTrail();
    const el = document.getElementById("view");
    el.textContent = view.overview ? `${DATA.domains.length} lanes, ${DATA.nodes.length} boxes, ${DATA.edges.length} links` : statusLine(statusCounts(sub));
    const whole = !view.overview && !view.focus && !view.laneOpen.size;
    document.getElementById("showall").hidden = whole;
    document.getElementById("startover").hidden = view.overview && !view.eff && !facetsOn(view.f) && !q.value;
    drawChips();
    if (drawerOpen()) fillDrawer();
  }
