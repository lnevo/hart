  /* pipeline_map_view_nav.js: part of app()'s body, inlined after pipeline_map_view_rail.js and before
     pipeline_map_view_input.js (see pipeline_map_view.js). Not a script on its own. It holds the browser history, the
     trail of where the view is (All lanes ▸ a lane ▸ a file), search with its list of results, the keys, Start over
     and the address.

     History: a move into a view (a lane, a file's chain, a Start chain, the whole map, back to the lanes) is a new
     history entry, so Back returns to the view before; zoom, pan and filter changes replace the entry they are in. */
  let navPush = false, shownHash = location.hash;
  function navStep() {  // the next address written starts a history entry; set at the start of a move, cleared after it
    navPush = true;
    queueMicrotask(() => (navPush = false));
  }

  /* ---- the trail on the toolbar's second row; each crumb but the last goes back to that view */
  const crumbsEl = document.getElementById("crumbs");
  let crumbs = [];
  function currentTrail() {
    const f = view.focus && byId[view.focus];
    return trail({ overview: view.overview && !view.focus, lanes: [...view.laneOpen], focus: view.focus, focusLane: f && f.domain },
                 d => domainLabel[d], f && f.label);
  }
  function drawTrail() {
    crumbs = currentTrail();
    crumbsEl.innerHTML = crumbs.map((c, i) => (c.to ? `<button type="button" class="crumb" data-i="${i}">${esc(c.label)}</button>`
      : `<b aria-current="page">${esc(c.label)}</b>`)).join('<span class="sep" aria-hidden="true"> ▸ </span>');
  }
  function goCrumb(to) {
    if (!to) return;
    if (to.overview) goOverview();
    else if (to.lanes) openLanes(to.lanes);
    else showWholeMap();
  }
  crumbsEl.addEventListener("click", e => { const b = e.target.closest("button.crumb"); if (b) goCrumb(crumbs[Number(b.dataset.i)].to); });

  /* ---- search: a list of the boxes that match under the box, best first (searchHits); arrows move in it, Enter or a
     click draws that box's chain. While the list is open the boxes that do not match fade. */
  const q = document.getElementById("q"), qlist = document.getElementById("qlist"), hits = document.getElementById("hits");
  const LIST_ROWS = 12;
  let found = [], qAt = 0;
  const listOpen = () => !qlist.hidden;
  function runSearch() {
    if (svg) svg.querySelectorAll(".node.hit").forEach(g => g.classList.remove("hit"));
    found = searchHits(DATA.nodes, q.value);
    const where = id => (visible.has(id) ? id : visible.has(groups.groupOf[id]) ? groups.groupOf[id] : null);
    found.forEach(id => { const w = where(id); if (w) nodeEl[w].classList.add("hit"); });
    if (svg) svg.classList.toggle("searching", listOpen() && found.length > 0);
    hits.textContent = "";
    updateFar();
  }
  function showList(open) {
    const t = q.value.trim();
    qlist.hidden = !open || !t;
    q.setAttribute("aria-expanded", qlist.hidden ? "false" : "true");
    if (!qlist.hidden) {
      qAt = Math.min(qAt, Math.max(0, Math.min(found.length, LIST_ROWS) - 1));
      const rows = found.slice(0, LIST_ROWS).map((id, i) => {
        const n = byId[id], st = n.status && n.status !== "live" ? `, ${n.status}` : "";
        return `<li role="option" id="qo${i}" data-id="${esc(id)}" aria-selected="${i === qAt}"><span class="sw" style="background:${esc(DATA.domainColor[n.domain])}"></span>` +
          `<b>${esc(n.label)}</b> <span class="k">${esc(DATA.kinds[n.kind][0])}${esc(st)}</span></li>`;
      });
      if (!found.length) rows.push('<li class="none">No box holds that text</li>');
      else if (found.length > LIST_ROWS) rows.push(`<li class="none">${found.length - LIST_ROWS} more: type more of the name</li>`);
      qlist.innerHTML = rows.join("");
      if (found.length) q.setAttribute("aria-activedescendant", `qo${qAt}`); else q.removeAttribute("aria-activedescendant");
    }
    if (svg) svg.classList.toggle("searching", !qlist.hidden && found.length > 0);
  }
  function jump(id) {
    q.blur(); showList(false);
    goTo(id);  // opens what hides it (a closed lane or folder, a lane or status the filters leave out)
  }
  q.addEventListener("input", () => { qAt = 0; runSearch(); showList(true); });
  q.addEventListener("focus", () => showList(true));
  q.addEventListener("blur", () => setTimeout(() => { if (document.activeElement !== q) showList(false); }, 150));
  q.addEventListener("keydown", e => {
    const n = Math.min(found.length, LIST_ROWS);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!n) return;
      if (!listOpen()) { showList(true); return; }
      qAt = (qAt + (e.key === "ArrowDown" ? 1 : n - 1)) % n;
      showList(true);
    } else if (e.key === "Enter") {
      if (found.length) { e.preventDefault(); jump(found[Math.min(qAt, n - 1)]); }
    } else if (e.key === "Escape") {
      e.preventDefault(); e.stopPropagation();
      if (listOpen()) showList(false); else q.blur();
    }
  });
  qlist.addEventListener("pointerdown", e => e.preventDefault());  // the box keeps the focus
  qlist.addEventListener("click", e => { const li = e.target.closest("li[data-id]"); if (li) jump(li.dataset.id); });

  /* ---- keys (not while typing in a field): Esc up one level, / search, [ and ] one step fewer or more either side of
     a file, L the list of boxes, F fit, H clean view (E, the efficiency overlay, is in pipeline_map_view_lanes.js) */
  const typing = e => e.target.matches("input:not([type=checkbox]):not([type=radio]):not([type=button]),textarea,select") || e.target.isContentEditable;
  function upOneLevel() {
    const open = menus.find(m => m.open);
    if (open) { open.open = false; return; }
    if (drawerOpen()) { toggleDrawer(false); return; }
    if (railOpen() && innerWidth <= 900) { setRail(false); return; }
    if (selected && svg && !(view.focus && selected === view.focus)) { clearFocus(true); return; }
    goCrumb(upFrom(crumbs));
  }
  document.addEventListener("keydown", e => {
    if (typing(e) || e.metaKey || e.ctrlKey || e.altKey) return;  // typing in any field, the site header's search too
    const k = e.key;
    if (k === "Escape") upOneLevel();
    else if (k === "/") { e.preventDefault(); q.focus(); q.select(); }
    else if (k === "f" || k === "F") fit();
    else if ((k === "h" || k === "H") && !e.shiftKey) setClean(!clean);  // not with Shift, held for the magnifier
    else if (k === "l" || k === "L") toggleDrawer();
    else if ((k === "[" || k === "]") && view.focus) step(["up", "down"], k === "]" ? 1 : -1);
  });

  /* ---- Start over: the page as a first visit opens it (the lane overview, no filters, search or overlay) */
  document.getElementById("startover").onclick = () => {
    q.value = ""; runSearch(); showList(false);
    view.steps = 0; view.hover = true; view.near = false;
    setEff(false, true); toggleDrawer(false);
    goOverview();
  };

  /* ---- address bar: #focus=<id>&up=all&down=2 or lane=<lane>,<lane> or map=all, the filters (writeFacets:
     lanes=, kind=, status=, step=, writers=, side=, rest=hide), trim=1&compact=0&folders=1&open=<folder>,<folder>
     &hover=0&near=1&steps=N&eff=1&node=<id>, line=1 (a Start button's main line, with focus and no node), and with Share also at=<x>,<y>,<width>,<aspect> (the zoom, position and
     lane stretch) and cap= (the sharer's box size) */
  function writeHash(withView = false) {
    const h = new URLSearchParams();
    const steps = n => (n === Infinity ? "all" : String(n));
    if (view.focus) { h.set("focus", view.focus); h.set("up", steps(view.up)); h.set("down", steps(view.down)); }
    else if (view.laneOpen.size) h.set("lane", [...view.laneOpen].join(","));
    writeFacets(h, view.f, view.hide);
    if (view.trim) h.set("trim", "1");
    if (!view.compact) h.set("compact", "0");  // compact is the default
    if (!view.hover) h.set("hover", "0");  // hover highlights are on by default
    if (view.near) h.set("near", "1");
    if (view.steps) h.set("steps", String(view.steps));
    if (withView && view.steps && view.boxCap) h.set("cap", String(+view.boxCap.toFixed(3)));  // with the sharer's box size  // (an older width= link is ignored: it meant wider boxes)
    if (view.group) { h.set("folders", "1"); if (view.open.size) h.set("open", [...view.open].join(",")); }
    if (selected) h.set("node", selected);
    else if (view.line && view.focus) h.set("line", "1");
    if (view.eff) h.set("eff", "1");
    if (!view.overview && isOverviewHash(h)) h.set("map", "all");  // the whole map: an empty address is the overview
    if (withView && lay) h.set("at", [vb.x, vb.y, vb.width].map(v => Math.round(v)).concat(lay.aspect ? [+lay.aspect.toFixed(4)] : []).join(","));  // with the sharer's lane stretch
    const s = h.toString(), url = s ? "#" + s : location.pathname + location.search;
    if (navPush && (s ? "#" + s : "") !== location.hash) history.pushState(null, "", url);
    else history.replaceState(null, "", url);
    navPush = false; shownHash = location.hash;
  }
  function readHash() {
    const h = new URLSearchParams(location.hash.slice(1));
    view.overview = isOverviewHash(h);  // an address with no view in it opens on the lanes
    view.laneOpen = new Set((h.get("lane") || "").split(",").filter(l => allLanes.includes(l)));
    setEff(h.get("eff") === "1", true);
    const focus = h.get("focus");
    view.focus = focus && Object.hasOwn(byId, focus) ? focus : null;
    const steps = v => (v !== null && /^\d+$/.test(v) ? Number(v) : Infinity);
    view.up = steps(h.get("up")); view.down = steps(h.get("down"));
    if (h.get("up") === null && h.get("down") === null) {  // older links: dir=both|up|down and depth=N
      const depth = steps(h.get("depth")), dir = h.get("dir");
      view.up = dir === "down" ? 0 : depth; view.down = dir === "up" ? 0 : depth;
    }
    ({ f: view.f, hide: view.hide } = readFacets(h, KNOWN));  // older lanes=, show=, hide=, hidekind= links too
    view.trim = h.get("trim") === "1";
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
    selected = selectableId(node, id => Object.hasOwn(byId, id)) ? node : null;
    view.line = h.get("line") === "1" && !!view.focus && !selected;
    if (selected && Object.hasOwn(byId, selected) && !view.focus) view.f.status = withStatus(view.f, view.hide, byId[selected].status || "live");  // keep a shared box in view
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
  function arrive(first) {  // first load: a file view opens at Fit; Back, Forward or an edited address pans to the selected box
    shownHash = location.hash;
    readHash();
    const at = sharedView();
    render(false, at ? at[3] || 0 : undefined);  // an older link without the shape: no stretch, as it was drawn then
    if (restoreView(at) || !selected || !visible.has(selected) || view.trim) return;
    if (!view.focus) centreOn(selected, true);
    else if (!first) centreOn(selected, false);
  }
  // Back and Forward fire popstate, and also hashchange when the address after # differs: the view is drawn once
  const arriveOnce = () => { if (location.hash !== shownHash) arrive(false); };
  window.addEventListener("popstate", arriveOnce);
  window.addEventListener("hashchange", arriveOnce);
