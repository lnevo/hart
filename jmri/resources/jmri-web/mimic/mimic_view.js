// LCOS mimic markup and rendering, shared by the JMRI page (index.html) and the Mac
// mimic (tools/mqtt-mimic/lcos_mqtt_mimic.html). Each page keeps its own transport:
// it fills `state`, calls render(), and handles the clicks on [data-to], [data-occ]
// and #clear-occ. This file only draws and switches level tabs; it sends nothing.

const state = { sensors: {}, turnouts: {}, heads: {}, layout: null, level: "" };

// Level tabs, in this order; a layout record carries `level` (build: lcos_mqtt_mimic.load_layout).
const LEVEL_TITLES = { staging: "Staging", main: "Main", upper: "Upper" };

// The record lists a layout holds; each record has `level` and `plant`.
const KINDS = ["turnouts", "blocks", "heads"];

const $ = (id) => document.getElementById(id);

// Builds an element. Layout names and live JMRI values reach the page only as text
// nodes and attribute values, never as markup. `attrs.class` sets className; other
// keys are attributes. A null, undefined or false child is left out; any other
// child that is not a node becomes text.
function el(tag, attrs, ...kids) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (key === "class") node.className = value;
    else node.setAttribute(key, String(value));
  }
  for (const kid of kids) {
    if (kid === null || kid === undefined || kid === false) continue;
    node.appendChild(typeof kid === "object" ? kid : document.createTextNode(String(kid)));
  }
  return node;
}

// A layout or state value as text; a missing value shows as nothing.
const text = (v) => String(v ?? "");

const isActive = (addr) => text(state.sensors[addr]).toUpperCase() === "ACTIVE";

// Adds the shared markup ahead of the page's own <footer>. The page sets the
// signal-head heading with <body data-heads-title="...">.
function mountMimic() {
  document.body.insertAdjacentHTML("afterbegin", `
  <header>
    <div>
      <h1>HART LCOS mimic</h1>
      <div class="meta"><span id="mqtt-dot" class="dot"></span><span id="mqtt-label">connecting…</span></div>
    </div>
    <nav class="tabs" id="tabs"></nav>
    <input type="search" id="q" placeholder="Filter switches / blocks" />
    <button class="danger" id="clear-occ">Clear occupancy (this level)</button>
  </header>
  <div class="layout">
    <section>
      <h2>Turnouts</h2>
      <div id="turnouts"></div>
    </section>
    <section>
      <h2>Occupancy</h2>
      <div id="blocks"></div>
    </section>
  </div>
  <div class="heads">
    <h2 id="heads-title"></h2>
    <div id="heads"></div>
  </div>`);
  $("heads-title").textContent = document.body.dataset.headsTitle || "Signal heads";
  $("q").addEventListener("input", render);
  $("tabs").addEventListener("click", (e) => {
    const tab = e.target.closest("[data-level]");
    if (!tab) return;
    state.level = tab.dataset.level;
    history.replaceState(null, "", "#" + state.level);
    render();
  });
  // A link or bookmark to #main or #upper while the page is open.
  window.addEventListener("hashchange", () => {
    state.level = location.hash.slice(1);
    render();
  });
}

// A layout without one of its record lists is a build fault; name the list.
function checkLayout(layout) {
  for (const kind of KINDS) {
    if (!Array.isArray(layout[kind])) throw new Error(`mimic layout has no "${kind}" list`);
  }
}

// The levels the layout holds, in tab order.
function levels() {
  const have = new Set();
  for (const kind of KINDS) {
    for (const it of state.layout[kind]) have.add(it.level);
  }
  return Object.keys(LEVEL_TITLES).filter((lv) => have.has(lv));
}

// The records of one kind ("turnouts", "blocks", "heads") on the shown level.
function onLevel(kind) {
  if (!state.layout) return [];
  return state.layout[kind].filter((it) => it.level === state.level);
}

// Items grouped by one field, groups in first-seen order.
function groupBy(items, field) {
  const map = new Map();
  for (const it of items) {
    if (!map.has(it[field])) map.set(it[field], []);
    map.get(it[field]).push(it);
  }
  return map;
}

function matches(q, ...parts) {
  if (!q) return true;
  return parts.join(" ").toLowerCase().includes(q);
}

const rowClass = (shown) => "row" + (shown ? "" : " hidden");

function turnoutFeedback(t) {
  if (t.virtual) return el("div", { class: "fb" }, "Virtual turnout, set in JMRI (no MQTT)");
  if (!t.n_addr) return el("div", { class: "fb" }, "DIRECT — turnout topic only");
  const sensor = (cls, addr) => {
    const on = isActive(addr);
    return el("span", { class: cls + (on ? " on" : "") }, text(addr) + (on ? " ACTIVE" : ""));
  };
  return el("div", { class: "fb" }, "FB N ", sensor("n", t.n_addr), " · R ", sensor("r", t.r_addr));
}

function turnoutRow(t, q) {
  const st = text(state.turnouts[t.addr]).toUpperCase();
  const button = (want, label) => el("button", {
    class: "sw" + (st === want ? " on-" + want.toLowerCase() : ""), "data-to": text(t.addr), "data-st": want,
  }, label);
  return el("div", { class: rowClass(matches(q, t.label, t.plant, t.addr, t.tip)) },
    el("div", null,
      el("div", { class: "name" }, text(t.label), " ", el("span", { class: "sub" }, text(t.name))),
      !t.virtual && el("div", { class: "sub" }, text(t.tip || t.feedback)),
      turnoutFeedback(t)),
    el("div", { class: "btns" }, button("CLOSED", "Closed"), button("THROWN", "Thrown")));
}

function blockRow(b, q) {
  const occ = isActive(b.addr);
  return el("div", { class: rowClass(matches(q, b.label, b.userName, b.plant, b.addr)) },
    el("div", null,
      el("div", { class: "name" }, text(b.label)),
      el("div", { class: "sub" }, `${text(b.userName)} · ${text(b.name)}`)),
    el("div", { class: "btns" },
      el("button", { class: "occ " + (occ ? "active" : "inactive"), "data-occ": text(b.addr),
        "data-st": occ ? "INACTIVE" : "ACTIVE" }, occ ? "Occupied" : "Clear")));
}

// The aspect JMRI reports for a head, keyed by its packed id (IH dropped) or its id.
// The first field of the reported value is the aspect; a head with no report is Dark.
function headAspectOf(h) {
  const packed = text(h.id).replace(/^IH/i, "");
  return text(state.heads[packed] || state.heads[h.id] || "Dark").split(";")[0].trim();
}

function mastLamps(heads) {
  const masts = [];
  for (const [mast, group] of groupBy(heads, "mast")) {
    const lamps = group.map((h) => {
      const aspect = headAspectOf(h);
      return el("i", { class: "lamp " + aspect, title: `${text(h.systemName || h.id)} ${aspect}` });
    });
    masts.push(el("div", { class: "mast" }, ...lamps, el("span", { class: "lbl", title: text(mast) }, text(mast))));
  }
  return el("div", { class: "lamps" }, ...masts);
}

// Redraws one section: a div.plant per plant on the shown level, each with its
// heading and what `draw` makes of that plant's records.
function renderPlants(kind, draw) {
  const groups = [];
  for (const [plant, rows] of groupBy(onLevel(kind), "plant")) {
    groups.push(el("div", { class: "plant" }, el("h3", null, text(plant)), ...draw(rows)));
  }
  $(kind).replaceChildren(...groups);
}

function renderTabs(shown) {
  const tabs = $("tabs");
  tabs.hidden = shown.length < 2;
  tabs.replaceChildren(...shown.map((lv) =>
    el("button", { class: "tab" + (lv === state.level ? " on" : ""), "data-level": lv }, LEVEL_TITLES[lv])));
}

function render() {
  const q = $("q").value.trim().toLowerCase();
  if (!state.layout) return;
  checkLayout(state.layout);

  const shown = levels();
  if (!shown.includes(state.level)) {
    const wanted = location.hash.slice(1);
    state.level = shown.includes(wanted) ? wanted : (shown[0] || "");
  }
  renderTabs(shown);
  renderPlants("turnouts", (rows) => rows.map((t) => turnoutRow(t, q)));
  renderPlants("blocks", (rows) => rows.map((b) => blockRow(b, q)));
  renderPlants("heads", (rows) => [mastLamps(rows)]);
}
