// LCOS mimic markup and rendering, shared by the JMRI page (index.html) and the Mac
// mimic (tools/mqtt-mimic/lcos_mqtt_mimic.html). Each page keeps its own transport:
// it fills `state`, calls render(), and handles the clicks on [data-to], [data-occ]
// and #clear-occ. This file only draws and switches level tabs; it sends nothing.

const state = { sensors: {}, turnouts: {}, heads: {}, layout: null, level: "" };

// Level tabs, in this order; a layout record carries `level` (build: lcos_mqtt_mimic.load_layout).
const LEVEL_TITLES = { staging: "Staging", main: "Main", upper: "Upper" };

const $ = (id) => document.getElementById(id);

// Layout names and live JMRI values go into innerHTML and attributes; escape them.
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// Adds the shared markup ahead of the page's own <footer>. The page sets the
// signal-head heading with <body data-heads-title="...">.
function mountMimic() {
  const headsTitle = document.body.dataset.headsTitle || "Signal heads";
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
    <h2>${esc(headsTitle)}</h2>
    <div id="heads"></div>
  </div>`);
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

// The levels the layout holds, in tab order.
function levels() {
  const have = new Set();
  for (const kind of ["turnouts", "blocks", "heads"]) {
    for (const it of state.layout[kind]) have.add(it.level);
  }
  return Object.keys(LEVEL_TITLES).filter((lv) => have.has(lv));
}

// The records of one kind ("turnouts", "blocks", "heads") on the shown level.
function onLevel(kind) {
  if (!state.layout) return [];
  return state.layout[kind].filter((it) => it.level === state.level);
}

function plantGroups(items) {
  const map = new Map();
  for (const it of items) {
    if (!map.has(it.plant)) map.set(it.plant, []);
    map.get(it.plant).push(it);
  }
  return map;
}

function matches(q, ...parts) {
  if (!q) return true;
  const blob = parts.join(" ").toLowerCase();
  return blob.includes(q);
}

function render() {
  const q = $("q").value.trim().toLowerCase();
  const layout = state.layout;
  if (!layout) return;

  const shown = levels();
  if (!shown.includes(state.level)) {
    const wanted = location.hash.slice(1);
    state.level = shown.includes(wanted) ? wanted : (shown[0] || "");
  }
  const tabs = $("tabs");
  tabs.hidden = shown.length < 2;
  tabs.innerHTML = shown.map((lv) =>
    `<button class="tab${lv === state.level ? " on" : ""}" data-level="${esc(lv)}">${esc(LEVEL_TITLES[lv])}</button>`).join("");

  const tRoot = $("turnouts");
  tRoot.innerHTML = "";
  for (const [plant, rows] of plantGroups(onLevel("turnouts"))) {
    const wrap = document.createElement("div");
    wrap.className = "plant";
    wrap.innerHTML = `<h3>${esc(plant)}</h3>`;
    for (const t of rows) {
      const st = (state.turnouts[t.addr] || "").toUpperCase();
      const nOn = (state.sensors[t.n_addr] || "").toUpperCase() === "ACTIVE";
      const rOn = (state.sensors[t.r_addr] || "").toUpperCase() === "ACTIVE";
      const row = document.createElement("div");
      row.className = "row" + (matches(q, t.label, t.plant, t.addr, t.tip) ? "" : " hidden");
      const fb = t.virtual
        ? `<div class="fb">Virtual turnout, set in JMRI (no MQTT)</div>`
        : t.n_addr
        ? `<div class="fb">FB N <span class="n${nOn ? " on" : ""}">${esc(t.n_addr)}${nOn ? " ACTIVE" : ""}</span>
           · R <span class="r${rOn ? " on" : ""}">${esc(t.r_addr)}${rOn ? " ACTIVE" : ""}</span></div>`
        : `<div class="fb">DIRECT — turnout topic only</div>`;
      row.innerHTML = `
        <div>
          <div class="name">${esc(t.label)} <span class="sub">${esc(t.name)}</span></div>
          ${t.virtual ? "" : `<div class="sub">${esc(t.tip || t.feedback)}</div>`}
          ${fb}
        </div>
        <div class="btns">
          <button class="sw ${st === "CLOSED" ? "on-closed" : ""}" data-to="${esc(t.addr)}" data-st="CLOSED">Closed</button>
          <button class="sw ${st === "THROWN" ? "on-thrown" : ""}" data-to="${esc(t.addr)}" data-st="THROWN">Thrown</button>
        </div>`;
      wrap.appendChild(row);
    }
    tRoot.appendChild(wrap);
  }

  const bRoot = $("blocks");
  bRoot.innerHTML = "";
  for (const [plant, rows] of plantGroups(onLevel("blocks"))) {
    const wrap = document.createElement("div");
    wrap.className = "plant";
    wrap.innerHTML = `<h3>${esc(plant)}</h3>`;
    for (const b of rows) {
      const occ = (state.sensors[b.addr] || "").toUpperCase() === "ACTIVE";
      const row = document.createElement("div");
      row.className = "row" + (matches(q, b.label, b.userName, b.plant, b.addr) ? "" : " hidden");
      row.innerHTML = `
        <div>
          <div class="name">${esc(b.label)}</div>
          <div class="sub">${esc(b.userName)} · ${esc(b.name)}</div>
        </div>
        <div class="btns">
          <button class="occ ${occ ? "active" : "inactive"}" data-occ="${esc(b.addr)}" data-st="${occ ? "INACTIVE" : "ACTIVE"}">
            ${occ ? "Occupied" : "Clear"}
          </button>
        </div>`;
      wrap.appendChild(row);
    }
    bRoot.appendChild(wrap);
  }

  const hRoot = $("heads");
  hRoot.innerHTML = "";
  for (const [plant, rows] of plantGroups(onLevel("heads"))) {
    const wrap = document.createElement("div");
    wrap.className = "plant";
    wrap.innerHTML = `<h3>${esc(plant)}</h3>`;
    const lamps = document.createElement("div");
    lamps.className = "lamps";
    const byMast = new Map();
    for (const h of rows) {
      if (!byMast.has(h.mast)) byMast.set(h.mast, []);
      byMast.get(h.mast).push(h);
    }
    for (const [mast, heads] of byMast) {
      const el = document.createElement("div");
      el.className = "mast";
      const lampHtml = heads.map(h => {
        const packed = (h.id || "").replace(/^IH/i, "");
        const aspect = (state.heads[packed] || state.heads[h.id] || "Dark").split(";")[0].trim();
        const sys = h.systemName || h.id;
        return `<i class="lamp ${esc(aspect)}" title="${esc(sys)} ${esc(aspect)}"></i>`;
      }).join("");
      el.innerHTML = `${lampHtml}<span class="lbl" title="${esc(mast)}">${esc(mast)}</span>`;
      lamps.appendChild(el);
    }
    wrap.appendChild(lamps);
    hRoot.appendChild(wrap);
  }
}
