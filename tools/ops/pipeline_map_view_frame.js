  /* pipeline_map_view_frame.js: the middle of app()'s body, inlined straight after pipeline_map_view.js and before
     pipeline_map_view_input.js (see pipeline_map_view.js). Not a script on its own. */
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
    spreadCtl.style.top = `${top}px`; spreadCtl.style.left = `${wrapEl.offsetLeft + Math.max(0, a.right - spreadCtl.offsetWidth - 8)}px`;  // the filter rail moves the map right
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
  function setVB(x, y, w, h) {  // every move goes through here, kept on the drawing (clampView); none on the lane overview
    if (!vb) return;
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
    if (!lay) return;
    const f = fitNow();
    setVB(f.x, f.y, f.width, f.height);
  }
  function zoomAt(f, cx, cy) {
    if (!vb) return;
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
    if (!vb) return;  // the lane overview scrolls as a page
    e.preventDefault();
    const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? wrapEl.clientHeight : 1;
    const dx = e.deltaX * unit, dy = e.deltaY * unit;
    if (!e.ctrlKey && Math.abs(dx) > Math.abs(dy)) { setVB(vb.x + dx * vb.width / wrapEl.getBoundingClientRect().width, vb.y, vb.width, vb.height); return; }
    zoomAt(Math.exp((e.ctrlKey ? 0.012 : 0.0025) * dy), e.clientX, e.clientY);
  };
  wrapEl.addEventListener("wheel", onWheel, { passive: false });
  let drag = null, moved = false;
  const startDrag = e => { if (!vb) return; drag = { x: e.clientX, y: e.clientY, vx: vb.x, vy: vb.y }; moved = false; wrapEl.classList.add("drag"); };
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
    if (!lay) { if (view.overview) relayTimer = setTimeout(drawOverview, 100); return; }  // the cards fit the new shape
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

