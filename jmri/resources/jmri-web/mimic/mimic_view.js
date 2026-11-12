// LCOS mimic markup and rendering, shared by the JMRI page (index.html) and the Mac
// mimic (tools/mqtt-mimic/lcos_mqtt_mimic.html). Each page keeps its own transport:
// it fills `state`, calls render(), and handles the clicks on [data-to], [data-occ]
// and #clear-occ. This file only draws; it sends nothing.

const state = { sensors: {}, turnouts: {}, heads: {}, layout: null };

const $ = (id) => document.getElementById(id);

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
    <input type="search" id="q" placeholder="Filter switches / blocks" />
    <button class="danger" id="clear-occ">Clear all occupancy</button>
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
    <h2>${headsTitle}</h2>
    <div id="heads"></div>
  </div>`);
  $("q").addEventListener("input", render);
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

  const tRoot = $("turnouts");
  tRoot.innerHTML = "";
  for (const [plant, rows] of plantGroups(layout.turnouts)) {
    const wrap = document.createElement("div");
    wrap.className = "plant";
    wrap.innerHTML = `<h3>${plant}</h3>`;
    for (const t of rows) {
      const st = (state.turnouts[t.addr] || "").toUpperCase();
      const nOn = (state.sensors[t.n_addr] || "").toUpperCase() === "ACTIVE";
      const rOn = (state.sensors[t.r_addr] || "").toUpperCase() === "ACTIVE";
      const row = document.createElement("div");
      row.className = "row" + (matches(q, t.label, t.plant, t.addr, t.tip) ? "" : " hidden");
      const fb = t.n_addr
        ? `<div class="fb">FB N <span class="n${nOn ? " on" : ""}">${t.n_addr}${nOn ? " ACTIVE" : ""}</span>
           · R <span class="r${rOn ? " on" : ""}">${t.r_addr}${rOn ? " ACTIVE" : ""}</span></div>`
        : `<div class="fb">DIRECT — turnout topic only</div>`;
      row.innerHTML = `
        <div>
          <div class="name">${t.label} <span class="sub">M2T${t.addr}</span></div>
          <div class="sub">${t.tip || t.feedback}</div>
          ${fb}
        </div>
        <div class="btns">
          <button class="sw ${st === "CLOSED" ? "on-closed" : ""}" data-to="${t.addr}" data-st="CLOSED">Closed</button>
          <button class="sw ${st === "THROWN" ? "on-thrown" : ""}" data-to="${t.addr}" data-st="THROWN">Thrown</button>
        </div>`;
      wrap.appendChild(row);
    }
    tRoot.appendChild(wrap);
  }

  const bRoot = $("blocks");
  bRoot.innerHTML = "";
  for (const [plant, rows] of plantGroups(layout.blocks)) {
    const wrap = document.createElement("div");
    wrap.className = "plant";
    wrap.innerHTML = `<h3>${plant}</h3>`;
    for (const b of rows) {
      const occ = (state.sensors[b.addr] || "").toUpperCase() === "ACTIVE";
      const row = document.createElement("div");
      row.className = "row" + (matches(q, b.label, b.userName, b.plant, b.addr) ? "" : " hidden");
      row.innerHTML = `
        <div>
          <div class="name">${b.label}</div>
          <div class="sub">${b.userName} · M2S${b.addr}</div>
        </div>
        <div class="btns">
          <button class="occ ${occ ? "active" : "inactive"}" data-occ="${b.addr}" data-st="${occ ? "INACTIVE" : "ACTIVE"}">
            ${occ ? "Occupied" : "Clear"}
          </button>
        </div>`;
      wrap.appendChild(row);
    }
    bRoot.appendChild(wrap);
  }

  const hRoot = $("heads");
  hRoot.innerHTML = "";
  for (const [plant, rows] of plantGroups(layout.heads)) {
    const wrap = document.createElement("div");
    wrap.className = "plant";
    wrap.innerHTML = `<h3>${plant}</h3>`;
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
        return `<i class="lamp ${aspect}" title="${sys} ${aspect}"></i>`;
      }).join("");
      el.innerHTML = `${lampHtml}<span class="lbl" title="${mast}">${mast}</span>`;
      lamps.appendChild(el);
    }
    wrap.appendChild(lamps);
    hRoot.appendChild(wrap);
  }
}
