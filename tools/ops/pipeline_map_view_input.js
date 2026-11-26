  /* pipeline_map_view_input.js: the end of app()'s body, inlined straight after pipeline_map_view_frame.js (see
     pipeline_map_view.js); it closes app() and calls it. Not a script on its own. */
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
    svg.querySelectorAll(".on,.sel,.upstream,.near,.sn").forEach(el => el.classList.remove("on", "sel", "upstream", "near", "sn"));
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
    // the boxes a hover on it grew (every link's other end, as setHover lights them) stay grown and lit after the click
    (edgesAt[id] || []).forEach(el => [el.dataset.from, el.dataset.to].forEach(v => nodeEl[v] && nodeEl[v].classList.add("sn")));
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

app();
