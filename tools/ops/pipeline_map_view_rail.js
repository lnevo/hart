  /* pipeline_map_view_rail.js: part of app()'s body, inlined after pipeline_map_view_lanes.js and before
     pipeline_map_view_nav.js (see pipeline_map_view.js). Not a script on its own. It holds the filter rail (a side
     panel on a wide screen, a sheet from the bottom on a phone), the filter chips under the toolbar, the fading of
     boxes the filters do not match, the list of boxes shown (L) and the info panel's long lists.

     The filters themselves are pure (pipeline_map_facets.js): ticked values within a facet are joined with OR,
     facets with AND, and a facet with nothing ticked does not filter. What they do not match is faded, or with Hide
     the rest left out (filtered(), in pipeline_map_view.js). */
  const hideable = k => Object.hasOwn(DATA.kinds, k) && k !== "folder" && k !== "lane";
  const SIDES = ["data", "check", "pointer", "pull", "mirror", "capture", "history"];
  const KNOWN = { lane: allLanes, kind: Object.keys(DATA.kinds).filter(hideable), status: STATUS_VALUES, step: STEP_VALUES,
                  writers: WRITER_VALUES, side: SIDES.filter(s => DATA.edges.some(e => edgeSide(e) === s)) };
  const FACET_NAME = { lane: "Lane", kind: "Kind", status: "Status", step: "Step type", writers: "Writers", side: "Link" };
  const VALUE_NAME = {
    status: { live: "Live", parked: "Parked", retired: "Retired" },
    step: { stamped: "Stamped step", guard: "Guard", none: "Not a step" },
    writers: { one: "One script", many: "Two or more", none: "None" },
    side: { data: "Carries data", check: "A check reads it", pointer: "Doc pointer", pull: "Pull back to the sources",
            mirror: "Folder mirror", capture: "Page capture", history: "Git history" },
  };
  const valueName = (k, v) => (k === "lane" ? domainLabel[v] : k === "kind" ? DATA.kinds[v][0] : VALUE_NAME[k][v]) || v;
  const FACET_NOTE = {
    status: "None ticked: live boxes only.",
    writers: "Outputs only: how many scripts write each one.",
    side: "Links that carry content, or side links that carry nothing on.",
  };

  /* ---- the rail: built the first time it opens, its counts kept up to date while it is open */
  const rail = document.getElementById("rail"), railBtn = document.getElementById("railbtn"), facetsBox = document.getElementById("facets");
  const hideRest = document.getElementById("hiderest");
  let railBuilt = false;
  function buildRail() {
    facetsBox.innerHTML = [...BOX_FACETS, "side"].map(k => `<fieldset data-facet="${k}"><legend>${FACET_NAME[k]}</legend>` +
      (FACET_NOTE[k] ? `<div class="note">${esc(FACET_NOTE[k])}</div>` : "") +
      KNOWN[k].map(v => {
        const sw = k === "lane" ? `<span class="sw" style="background:${esc(DATA.domainColor[v])}"></span>`
          : k === "kind" ? `<span class="sw" style="background:${esc(DATA.kinds[v][1])};border-color:${esc(DATA.kinds[v][2])}"></span>` : "";
        return `<div class="fv"><label><input type="checkbox" data-facet="${k}" value="${esc(v)}"> ${sw}${esc(valueName(k, v))}</label>` +
          ` <span class="n" data-n="${k}:${esc(v)}"></span><button type="button" class="only" data-facet="${k}" data-value="${esc(v)}" ` +
          `aria-label="${esc(`Only ${valueName(k, v)}`)}" title="Tick only this one (again: untick it)">only</button></div>`;
      }).join("") + "</fieldset>").join("");
    railBuilt = true;
  }
  const railOpen = () => !rail.hidden;
  function setRail(on) {
    if (on && !railBuilt) buildRail();
    rail.hidden = !on;
    document.body.classList.toggle("railon", on);
    railBtn.setAttribute("aria-expanded", on ? "true" : "false");
    if (on) { placeRail(); syncRail(); }
    // the map's room changed (on a wide screen the rail takes the left of it)
    if (ovSvg) drawOverview();
    else if (svg) { if (fitted) fit(); else setVB(vb.x, vb.y, vb.width, vb.height); }
  }
  function placeRail() {  // under the toolbar on a wide screen; a phone's sheet sits at the bottom (CSS)
    const top = document.getElementById("bar").getBoundingClientRect().bottom - document.getElementById("stage").getBoundingClientRect().top + 8;
    rail.style.top = innerWidth > 900 ? `${Math.round(top)}px` : "";
  }
  addEventListener("resize", () => { if (railOpen()) placeRail(); });
  railBtn.onclick = () => { menus.forEach(m => (m.open = false)); setRail(!railOpen()); };
  document.getElementById("railclose").onclick = () => { setRail(false); railBtn.focus(); };
  function syncRail() {
    hideRest.checked = view.hide;
    if (!railBuilt || !railOpen()) return;
    const counts = facetCounts(DATA.nodes, view.f, view.hide);
    const pass = id => boxMatches(boxVals[id], view.f) && drawnStatus(view.f, view.hide).has(byId[id].status || "live");
    counts.side = sideCounts(DATA.edges, pass);
    const any = facetsOn(view.f);
    facetsBox.querySelectorAll("input[data-facet]").forEach(c => (c.checked = view.f[c.dataset.facet].has(c.value)));
    facetsBox.querySelectorAll("[data-n]").forEach(el => {
      const [k, v] = el.dataset.n.split(":"), [all, n] = (counts[k] && counts[k][v]) || [0, 0];
      el.textContent = any && n !== all ? `${all} → ${n}` : String(all);
      el.closest(".fv").classList.toggle("none", any && n === 0);
    });
  }
  /* After a filter change: a change that alters what is drawn (statuses, or anything with Hide the rest) lays the map
     out again, keeping the reader's place; one that only fades boxes redraws nothing. */
  const drawnKey = () => JSON.stringify([[...drawnStatus(view.f, view.hide)].sort(), view.hide && Object.entries(view.f).map(([k, s]) => [k, [...s].sort()])]);
  function changeFilters(edit) {
    const was = drawnKey();
    edit();
    if (view.overview || drawnKey() !== was) { view.overview = false; renderKeeping(); }
    else { applyFade(); showStatus(sub); }
    syncRail(); writeHash();
  }
  facetsBox.addEventListener("change", e => {
    const c = e.target.closest("input[data-facet]");
    if (c) changeFilters(() => { const s = view.f[c.dataset.facet]; if (c.checked) s.add(c.value); else s.delete(c.value); });
  });
  facetsBox.addEventListener("click", e => {
    const b = e.target.closest("button.only");
    if (!b) return;
    const k = b.dataset.facet;
    changeFilters(() => (view.f[k] = onlyValue(view.f[k], b.dataset.value)));
  });
  hideRest.onchange = () => changeFilters(() => (view.hide = hideRest.checked));
  function clearFacets() { changeFilters(() => { view.f = emptyFacets(); view.hide = false; }); }

  /* ---- fading: the boxes the filters do not match (a folder or closed lane when none of its boxes matches), and the
     links of an unticked side or with a faded end */
  function applyFade() {
    if (!svg) return;
    const on = facetsOn(view.f);
    svg.classList.toggle("faceted", on);
    const dim = {};
    for (const id in nodeEl) {
      const members = groups.members[id];
      dim[id] = on && (members ? !members.some(m => boxMatches(boxVals[m], view.f)) : !!boxVals[id] && !boxMatches(boxVals[id], view.f));
      nodeEl[id].classList.toggle("dim", dim[id]);
    }
    edgeEls.forEach((el, i) => {
      const e = lay.edges[i], off = on && (dim[e.from] || dim[e.to] || (view.f.side.size > 0 && !view.f.side.has(edgeSide(e))));
      el.classList.toggle("dim", !!off);
      const l = svg.querySelector(`.elabel[data-edge="e${i}"]`);
      if (l) l.classList.toggle("dim", !!off);
    });
  }
  /* The figures for the status line (statusLine, pipeline_map_facets.js); a folder or closed lane counts its boxes. */
  function drawnIds(sub, closed = true) {
    const ids = [];
    sub.nodes.forEach(n => {
      const m = groups.members[n.id];
      if (m) { if (closed || n.kind !== "lane") ids.push(...m); } else if (byId[n.id]) ids.push(n.id);
    });
    return ids;
  }
  function statusCounts(sub) {
    // the boxes in view: with lanes opened from the overview, those of the open lanes (a closed lane is one box)
    const lanes = view.laneOpen.size && !view.focus ? view.laneOpen : null;
    const ids = drawnIds(sub, !lanes), st = drawnStatus(view.f, view.hide), on = facetsOn(view.f);
    const out = { boxes: ids.length, liveOnly: st.size === 1 && st.has("live"), faded: 0, hidden: 0, parked: 0, retired: 0, extra: [] };
    if (on && !view.hide) out.faded = ids.filter(id => !boxMatches(boxVals[id], view.f)).length;
    if (!view.focus && !sub.trim) {
      const scope = DATA.nodes.filter(n => !lanes || lanes.has(n.domain));
      // statuses left out while none is ticked are named; anything else Hide the rest leaves out is "hidden by the filters"
      if (!view.f.status.size || !view.hide) scope.forEach(n => { const s = n.status || "live"; if (!st.has(s) && s in out) out[s]++; });
      if (view.hide) out.hidden = Math.max(0, scope.length - out.parked - out.retired - ids.length);
    }
    if (sub.trim) out.extra.push(`only the chain of ${nodeOf(selected).label}`);
    if (view.group && !view.focus) out.extra.push("grouped by folder");
    return out;
  }

  /* ---- chips: one per ticked value under the toolbar, each removing its filter, and Clear all */
  const chips = document.getElementById("chips");
  function drawChips() {
    syncRail();
    const list = [];
    for (const k of [...BOX_FACETS, "side"]) for (const v of view.f[k])
      list.push(`<button type="button" class="chip" data-facet="${k}" data-value="${esc(v)}" aria-label="${esc(`Remove the filter ${FACET_NAME[k]}: ${valueName(k, v)}`)}">${esc(FACET_NAME[k])}: ${esc(valueName(k, v))} <span aria-hidden="true">×</span></button>`);
    if (view.hide) list.push('<button type="button" class="chip" data-hide="1" aria-label="Fade the rest instead of hiding it">Hide the rest <span aria-hidden="true">×</span></button>');
    chips.hidden = !list.length;
    chips.innerHTML = list.length ? list.join("") + '<button type="button" id="clearall">Clear all</button>' : "";
  }
  chips.addEventListener("click", e => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.id === "clearall") { clearFacets(); return; }
    if (b.dataset.hide) { changeFilters(() => (view.hide = false)); return; }
    changeFilters(() => view.f[b.dataset.facet].delete(b.dataset.value));
  });

  /* ---- the list of boxes shown (L, or List on the toolbar): a table that sorts by any column; a row draws that box's
     chain. On the lane overview it lists every box the filters draw. */
  const drawer = document.getElementById("drawer"), listBtn = document.getElementById("listbtn"), dbody = drawer.querySelector("tbody");
  let sortBy = "label", sortDir = 1;
  const drawerOpen = () => !drawer.hidden;
  function toggleDrawer(on = drawer.hidden) {
    drawer.hidden = !on;
    listBtn.setAttribute("aria-pressed", on ? "true" : "false");
    if (on) fillDrawer();
  }
  listBtn.onclick = () => toggleDrawer();
  document.getElementById("drawerclose").onclick = () => { toggleDrawer(false); listBtn.focus(); };
  const stepWord = n => (boxVals[n.id].step.map(v => VALUE_NAME.step[v]).join(", "));
  const timeOf = n => { const t = (n.eff || []).map(e => (e.t ? runTime(e.t) : null)).filter(v => v !== null); return t.length ? Math.max(...t) : null; };
  function timeText(n) {
    const t = (n.eff || []).find(e => e.t);
    if (!t) return "";
    return [t.t.warm_s != null && `warm ${secs(t.t.warm_s)}`, t.t.cold_s != null && `cold ${secs(t.t.cold_s)}`].filter(Boolean).join(", ");
  }
  const COLS = { label: n => n.label.toLowerCase(), lane: n => domainLabel[n.domain], kind: n => DATA.kinds[n.kind][0],
                 step: stepWord, writers: n => (n.w ? n.w.n : -1), time: n => timeOf(n) ?? -1 };
  function fillDrawer() {
    const st = drawnStatus(view.f, view.hide);
    let ids = view.overview || !svg ? DATA.nodes.filter(n => st.has(n.status || "live")).map(n => n.id) : drawnIds(sub, false);
    if (facetsOn(view.f)) ids = ids.filter(id => boxMatches(boxVals[id], view.f));
    const key = COLS[sortBy], rows = ids.map(id => byId[id]).sort((a, b) => {
      const x = key(a), y = key(b);
      return (x < y ? -1 : x > y ? 1 : 0) * sortDir || a.label.localeCompare(b.label);
    });
    document.getElementById("drawn").textContent = `${rows.length} ${rows.length === 1 ? "box" : "boxes"}`;
    drawer.querySelectorAll("th[data-sort]").forEach(th => th.setAttribute("aria-sort", th.dataset.sort === sortBy ? (sortDir > 0 ? "ascending" : "descending") : "none"));
    dbody.innerHTML = rows.map(n => `<tr tabindex="0" data-id="${esc(n.id)}"><td>${esc(n.label)}</td>` +
      `<td><span class="sw" style="background:${esc(DATA.domainColor[n.domain])}"></span>${esc(domainLabel[n.domain])}</td>` +
      `<td>${esc(DATA.kinds[n.kind][0])}</td><td>${esc(stepWord(n))}</td><td>${n.w ? n.w.n : ""}</td><td>${esc(timeText(n))}</td></tr>`).join("");
  }
  drawer.querySelector("thead").addEventListener("click", e => {
    const th = e.target.closest("th[data-sort]");
    if (!th) return;
    if (sortBy === th.dataset.sort) sortDir = -sortDir; else { sortBy = th.dataset.sort; sortDir = 1; }
    fillDrawer();
  });
  const rowGo = tr => { if (tr && tr.dataset.id) focusOn(tr.dataset.id); };
  dbody.addEventListener("click", e => rowGo(e.target.closest("tr")));
  dbody.addEventListener("keydown", e => { if (e.key === "Enter") rowGo(e.target.closest("tr")); });

  /* ---- the info panel's lists: more than eight entries are grouped by kind and cut to the first eight, with a
     button that shows the rest */
  const LIST_MAX = 8;
  function boxList(items, li, empty) {
    if (!items.length) return `<ul><li>${empty}</li></ul>`;
    const parts = groupByKind(items, id => (nodeOf(id) || {}).kind, Object.keys(DATA.kinds), LIST_MAX);
    if (parts[0].kind === null) return `<ul>${items.map(it => `<li>${li(it)}</li>`).join("")}</ul>`;
    let i = 0;
    const html = parts.map(g => {
      const first = i;
      const rows = g.items.map(it => `<li${i++ >= LIST_MAX ? " hidden" : ""}>${li(it)}</li>`).join("");
      return `<li class="kh"${first >= LIST_MAX ? " hidden" : ""}>${esc((DATA.kinds[g.kind] || [g.kind])[0])} <span class="off">${g.items.length}</span></li>${rows}`;
    }).join("");
    return `<ul class="grouped">${html}</ul><button type="button" class="showall">Show all ${items.length}</button>`;
  }
  info.addEventListener("click", e => {
    const b = e.target.closest("button.showall");
    if (!b) return;
    b.previousElementSibling.querySelectorAll("li[hidden]").forEach(li => (li.hidden = false));
    b.remove();
  });
