// Session paperwork: crew sheets, YM-01, DS-01, station maps, TT-23, colors, EQ-01, spot sheets.
// Every page is a thin HTML shell that calls HARTCrew.page(kind, id); the content lives in data/crew.json.
// Tested by scripts/tests/crew_pages_test.js, which draws every crew page from the real data.
(function () {
  "use strict";
  let data = null;
  let site = null;

  const esc = HARTOps.esc;
  const u = (rel) => HARTOps.base() + rel;
  const join = (items, fn, sep = "") => (items || []).map(fn).join(sep);

  // The archive pages (crew/maps/archive/) keep the earlier hand-drawn maps and link only among themselves.
  let archive = false;

  const mapHref = (id) => u(`crew/maps/${archive ? "archive/" : ""}${id}/index.html`);
  const sheetSrc = (file) => u(`crew/maps/generated-sheets/${file}.svg`);
  // Thumbnail for a map card: the generated sheet, or the hand-drawn picture in the archive.
  const mapThumb = (m) => (archive || !m.sheets || !m.sheets.length ? u(m.img) : sheetSrc(m.sheets[0]));
  const spotHref = (id) => `${u("crew/industries/index.html")}#${id}`;
  const colorById = (id) => (data.colors || []).find((c) => c.id === id);
  const mapById = (id) => (data.maps || []).find((m) => m.id === id);

  function pubLine(o) {
    const bits = [];
    if (o.pub) bits.push(`Publication ${o.pub}`);
    if (o.revision) bits.push(`Revision ${o.revision}`);
    if (o.effective) bits.push(`Effective ${o.effective}`);
    return bits.join(" · ");
  }

  // —— Shared HTML pieces ——
  function chip(c, opts = {}) {
    if (!c) return "";
    const cls = `cchip${opts.dim ? " is-dim" : ""}${opts.small ? " is-small" : ""}`;
    const label = opts.swatchOnly ? ` role="img" aria-label="${esc(c.label)}"` : "";
    return `<span class="${cls}" style="--chip:${esc(c.hex)};--chip-ink:${esc(c.ink)}"${label}>${opts.swatchOnly ? "" : esc(c.label)}</span>`;
  }

  const chips = (ids, opts) => join(ids, (id) => chip(colorById(id), opts), " ");

  // A data table: a head row, then one row per item from rowHtml.
  const dataTable = (cls, heads, rows, rowHtml) =>
    `<div class="table-wrap"><table class="${cls}"><thead><tr>${join(heads, (h) => `<th>${h}</th>`)}</tr></thead>` +
    `<tbody>${join(rows, rowHtml)}</tbody></table></div>`;

  function colorTable(withSpots) {
    return dataTable("data-table color-table", ["Color", "Destination", "Train"], data.colors, (c) => {
      const dest = withSpots ? `<a href="${spotHref(c.spot)}">${esc(c.dest)}</a>` : esc(c.dest);
      return `<tr><td>${chip(c)}</td><td>${dest}</td><td>${esc(c.train)}</td></tr>`;
    });
  }

  function ttTable() {
    const tt = data.timetable;
    return (
      dataTable("data-table tt-table", tt.columns.map(esc), tt.rows,
        (r) => `<tr><td>${esc(r[0])}</td><th scope="row">${esc(r[1])}</th><td>${esc(r[2])}</td></tr>`) +
      `<p class="tt-note">${esc(tt.note)}</p>`
    );
  }

  function sourceButton(rel, label) {
    // Published docx/pptx live in ../external (not on the public site): local desk only.
    if (!rel || (site && site.public)) return "";
    return `<a class="btn btn-ghost" href="${esc(encodeURI(u(rel)))}">${esc(label || "Source docx")}</a>`;
  }

  const printButton = (label) => `<button type="button" class="btn btn-ghost" data-print>${esc(label || "Print")}</button>`;
  const ghostLink = (rel, label) => `<a class="btn btn-ghost" href="${u(rel)}">${label}</a>`;
  const actions = (html) => `<div class="sheet-actions no-print">${html}</div>`;
  const listItems = (items, fn = esc) => join(items, (x) => `<li>${fn(x)}</li>`);

  function wirePrint(root) {
    root.querySelectorAll("[data-print]").forEach((b) => b.addEventListener("click", () => window.print()));
  }

  // Closed <details> do not print; open the ones marked for print, then put them back.
  let printOpened = [];
  window.addEventListener("beforeprint", () => {
    printOpened = [];
    document.querySelectorAll("details[data-print-open]").forEach((d) => {
      if (!d.open) {
        d.open = true;
        printOpened.push(d);
      }
    });
  });
  window.addEventListener("afterprint", () => {
    printOpened.forEach((d) => {
      d.open = false;
    });
    printOpened = [];
  });

  // "Operations › Session paperwork ›" above the title.
  function extendCrumb(extra) {
    const crumb = document.querySelector("main .page-head .crumb ol");
    if (!crumb) return;
    (extra || []).forEach((e) => {
      crumb.insertAdjacentHTML("beforeend", `<li><a href="${esc(e.href)}">${esc(e.label)}</a></li>`);
    });
  }

  // —— Full-screen map viewer with pinch zoom ——
  let viewer = null;
  function openViewer(src, alt) {
    if (!viewer) viewer = buildViewer();
    viewer.open(src, alt);
  }

  function buildViewer() {
    const el = document.createElement("div");
    el.className = "zoomer";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-modal", "true");
    el.setAttribute("aria-label", "Map viewer");
    el.hidden = true;
    el.innerHTML =
      '<div class="zoomer-bar">' +
      '<button type="button" data-z="out" aria-label="Zoom out">−</button>' +
      '<button type="button" data-z="fit">Fit</button>' +
      '<button type="button" data-z="in" aria-label="Zoom in">+</button>' +
      '<button type="button" data-z="close" class="zoomer-close">Close</button>' +
      "</div>" +
      '<div class="zoomer-stage"><img alt=""></div>' +
      '<p class="zoomer-hint">Pinch or use + and − to zoom. <span class="rotate-hint">Turn your phone sideways for a bigger view.</span></p>';
    document.body.appendChild(el);
    const stage = el.querySelector(".zoomer-stage");
    const img = el.querySelector("img");
    let scale = 1;
    let lastFocus = null;

    function apply(newScale, cx, cy) {
      newScale = Math.max(1, Math.min(6, newScale));
      const rect = stage.getBoundingClientRect();
      if (cx == null) cx = rect.width / 2;
      if (cy == null) cy = rect.height / 2;
      const fx = (stage.scrollLeft + cx) / (img.offsetWidth || 1);
      const fy = (stage.scrollTop + cy) / (img.offsetHeight || 1);
      scale = newScale;
      img.style.width = scale * 100 + "%";
      stage.scrollLeft = fx * img.offsetWidth - cx;
      stage.scrollTop = fy * img.offsetHeight - cy;
    }

    function close() {
      el.hidden = true;
      document.documentElement.classList.remove("zoomer-open");
      if (lastFocus) lastFocus.focus();
    }

    el.querySelector(".zoomer-bar").addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      const z = b.getAttribute("data-z");
      if (z === "in") apply(scale * 1.5);
      else if (z === "out") apply(scale / 1.5);
      else if (z === "fit") apply(1);
      else if (z === "close") close();
    });

    let pinch = null;
    const dist = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
    // A point on the stage, from a pointer's page position.
    const onStage = (x, y) => {
      const r = stage.getBoundingClientRect();
      return [x - r.left, y - r.top];
    };
    stage.addEventListener("touchstart", (e) => {
      if (e.touches.length !== 2) return;
      const [cx, cy] = onStage((e.touches[0].clientX + e.touches[1].clientX) / 2, (e.touches[0].clientY + e.touches[1].clientY) / 2);
      pinch = { d: dist(e.touches), s: scale, cx, cy };
    }, { passive: true });
    stage.addEventListener("touchmove", (e) => {
      if (pinch && e.touches.length === 2) {
        e.preventDefault();
        apply(pinch.s * (dist(e.touches) / pinch.d), pinch.cx, pinch.cy);
      }
    }, { passive: false });
    stage.addEventListener("touchend", (e) => {
      if (e.touches.length < 2) pinch = null;
    });
    stage.addEventListener("dblclick", (e) => apply(scale > 1 ? 1 : 2.5, ...onStage(e.clientX, e.clientY)));
    stage.addEventListener("wheel", (e) => {
      if (!e.ctrlKey) return;
      e.preventDefault();
      apply(scale * (e.deltaY < 0 ? 1.15 : 1 / 1.15), ...onStage(e.clientX, e.clientY));
    }, { passive: false });
    document.addEventListener("keydown", (e) => {
      if (el.hidden) return;
      HARTOps.trapTab(el, e);
      if (e.key === "Escape") close();
      if (e.key === "+" || e.key === "=") apply(scale * 1.5);
      if (e.key === "-") apply(scale / 1.5);
    });

    return {
      open(src, alt) {
        lastFocus = document.activeElement;
        img.src = src;
        img.alt = alt || "";
        el.hidden = false;
        document.documentElement.classList.add("zoomer-open");
        scale = 1;
        img.style.width = "100%";
        stage.scrollTop = 0;
        stage.scrollLeft = 0;
        el.querySelector(".zoomer-close").focus();
      },
    };
  }

  function wireZoom(root) {
    root.querySelectorAll("[data-zoom]").forEach((b) => {
      b.addEventListener("click", () => {
        const img = b.querySelector("img");
        openViewer(img.currentSrc || img.src, img.alt);
      });
    });
  }

  function mapCard(m) {
    if (!m) return "";
    return (
      `<a class="map-card" href="${mapHref(m.id)}"><img src="${esc(mapThumb(m))}" alt="" loading="lazy">` +
      `<span><strong>${esc(m.title)}</strong><small>${esc(m.pub)}</small></span></a>`
    );
  }

  const ROTATE_HINT = '<span class="rotate-hint">Turn your phone sideways for a bigger view.</span>';

  // —— Crew sheet / YM-01 / DS-01 ——
  const storageKey = (job) => `hart.crew.${job.id}.steps`;

  function readTicks(job) {
    try {
      return JSON.parse(localStorage.getItem(storageKey(job)) || "[]") || [];
    } catch (e) {
      return []; // no storage (a private window): the boxes start clear
    }
  }

  function writeTicks(job, ticks) {
    try {
      localStorage.setItem(storageKey(job), JSON.stringify(ticks));
    } catch (e) {} // no storage: the ticks last until the page closes
  }

  function sheetHead(job) {
    let engine = "";
    if (job.engine) {
      const pic = job.engine.img
        ? `<img src="${esc(u(job.engine.img))}" alt="${esc(job.engine.label)}" width="160" height="45">`
        : '<span class="engine-none" aria-hidden="true">?</span>';
      engine = `<div class="sheet-engine">${pic}<span><small>Engine</small>${esc(job.engine.label)}</span></div>`;
    }
    return (
      `<div class="sheet-id"><p class="sheet-code">${esc(job.code)}</p>` +
      `<div><h1>${esc(job.name)}</h1><p class="sheet-pub">${esc(job.pub)} · Rev ${esc(job.revision)}` +
      ` <span class="sheet-eff">· Effective ${esc(job.effective)}</span></p></div></div>` +
      engine
    );
  }

  function stepsSection(job) {
    const ticks = readTicks(job);
    return (
      '<section class="sheet-sec" aria-labelledby="steps-h"><div class="sec-head"><h2 id="steps-h">Crew steps</h2>' +
      '<button type="button" class="link-btn no-print" data-reset>Clear ticks</button></div><ol class="steps">' +
      join(job.steps, (s, i) =>
        `<li><label><input type="checkbox" class="no-print" data-step="${i}"${ticks[i] ? " checked" : ""}><span>${esc(s)}</span></label></li>`) +
      "</ol></section>"
    );
  }

  function rowsSection(title, rows) {
    return (
      `<section class="sheet-sec"><h2>${esc(title)}</h2><ol class="seq">` +
      join(rows, (r) =>
        `<li><span class="seq-n">${esc(r.n)}</span><div><p class="seq-train">${esc(r.train)}</p>` +
        `<p class="seq-action">${esc(r.action)}</p>` +
        (r.colors ? `<p class="seq-chips">${chips(r.colors, { small: true })}</p>` : "") +
        "</div></li>") +
      "</ol></section>"
    );
  }

  // The job's colors: every color when the job has them all, else every color with the job's own bright.
  function colorsSection(job) {
    const mine = job.colors || [];
    const all = mine.length >= data.colors.length;
    // every color in the job's order, then its rows with no id or spot (YM-01's NONE)
    const shown = all ? mine.map(colorById).concat(job.legend_extra || []) : data.colors;
    return (
      `<section class="sheet-sec sheet-colors" aria-labelledby="colors-h"><h2 id="colors-h">${all ? "Destination colors" : "Your colors"}</h2>` +
      (all ? "" : '<p class="muted small">Your blocks are bright; the rest are dimmed.</p>') +
      '<ul class="cc-list">' +
      join(shown, (c) => {
        const on = !c.id || mine.includes(c.id);
        const dest = c.spot ? `<a href="${spotHref(c.spot)}">${esc(c.dest)}</a>` : `<strong>${esc(c.dest)}</strong>`;
        return `<li class="${on ? "is-mine" : "is-other"}">${chip(c, { dim: !on })}${dest}<small>${esc(c.train)}</small></li>`;
      }) +
      "</ul></section>"
    );
  }

  function talkSection(job) {
    return (
      '<section class="sheet-sec no-print" aria-labelledby="talk-h"><h2 id="talk-h">Who you talk to</h2><dl class="talk">' +
      join(job.talk, (t) => `<dt>${esc(t.who)}</dt><dd>${esc(t.why)}</dd>`) +
      "</dl>" +
      join(job.links, (l) => `<p class="small"><a href="${u(l.href)}">${esc(l.label)}</a></p>`) +
      "</section>"
    );
  }

  function renderSheet(job) {
    const root = document.getElementById("crew-root");
    document.title = `${job.code} ${job.name} — HART`;
    document.getElementById("sheet-head").innerHTML = sheetHead(job);

    let html = `<p class="sheet-summary">${esc(job.summary)}</p>`;
    if (job.priority) {
      html +=
        '<section class="sheet-sec" aria-labelledby="prio-h"><h2 id="prio-h">Priority</h2><ol class="prio-strip">' +
        listItems(job.priority, (p) => `<span>${esc(p)}</span>`) +
        '</ol><p class="muted small">When moves conflict, the train further left goes first.</p></section>';
    }
    if (job.steps) html += stepsSection(job);
    if (job.sequence) html += rowsSection("Sequence", job.sequence);
    if (job.lineup) html += rowsSection("Train lineup", job.lineup);
    html += colorsSection(job);
    if (job.maps && job.maps.length) {
      html +=
        '<section class="sheet-sec no-print" aria-labelledby="where-h"><h2 id="where-h">Where you work</h2><div class="map-cards">' +
        join(job.maps, (id) => mapCard(mapById(id))) +
        `</div><p class="small"><a href="${u("crew/maps/index.html")}">All station maps</a></p></section>`;
    }
    if (job.talk && job.talk.length) html += talkSection(job);
    html +=
      `<details class="sheet-more print-back" data-print-open${job.ttOpen ? " open" : ""}>` +
      "<summary>Route 23 timetable (TT-23)</summary>" +
      `<div class="back-page"><figure class="back-map print-only"><img src="${esc(u("assets/maps/station_map_diagram_only.png"))}"` +
      ` alt="Subdivision diagram"></figure><div>${ttTable()}` +
      `<p class="small no-print"><a href="${u("crew/tt23/index.html")}">Full timetable page</a></p></div></div></details>`;
    html += `<details class="sheet-more no-print"><summary>All destination colors</summary>${colorTable(true)}</details>`;
    html += actions(printButton("Print 5×8 card") + sourceButton(job.source) +
      ghostLink("crew/index.html", "All sheets") + ghostLink("briefing/index.html", "Primer"));
    root.innerHTML = html;

    root.querySelectorAll("[data-step]").forEach((box) => {
      box.addEventListener("change", () => {
        const t = readTicks(job);
        t[Number(box.getAttribute("data-step"))] = box.checked;
        writeTicks(job, t);
      });
    });
    const reset = root.querySelector("[data-reset]");
    if (reset) {
      reset.addEventListener("click", () => {
        writeTicks(job, []);
        root.querySelectorAll("[data-step]").forEach((b) => {
          b.checked = false;
        });
      });
    }
    wirePrint(root);
  }

  // One generated sheet (docs/ops/stations, published under crew/maps/generated-sheets/), tap to zoom.
  function sheetFigure(id, withTitle) {
    const info = (data.sheets || {})[id];
    if (!info) throw new Error(`No sheet ${id}`);
    const [title, what] = info;
    const src = esc(sheetSrc(id));
    return (
      `<figure class="map-figure">${withTitle ? `<h2 class="sub-h">${esc(title)}</h2>` : ""}` +
      `<button type="button" class="map-open" data-zoom aria-label="Open ${esc(title)} map full screen">` +
      `<img src="${src}" alt="${esc(`${title} station map, ${what.charAt(0).toLowerCase()}${what.slice(1)}`)}" width="1056" height="816"></button>` +
      `<figcaption class="no-print">${esc(`${title}: ${what}`)}. Tap the map to zoom. <a href="${src}">Open the drawing full size</a>. ${ROTATE_HINT}</figcaption></figure>`
    );
  }

  // —— Station map page ——
  function mapTracks(m) {
    return (
      '<section class="sheet-sec no-print"><h2>Tracks</h2>' +
      dataTable("data-table", ["Track", "What is there", "Color"], m.tracks, (t) => {
        let purpose = esc(t.purpose);
        if (t.spots) {
          const links = join(t.spots, (s) => {
            const label = t.spots.length > 1 ? `Spot sheet: ${spotName(s)}` : "Spot sheet";
            return `<a href="${spotHref(s)}">${esc(label)}</a>`;
          }, " · ");
          purpose += `<br><span class="small">${links}</span>`;
        }
        if (t.map) purpose += `<br><a class="small" href="${mapHref(t.map)}">${esc(mapById(t.map).title)} map</a>`;
        return `<tr><th scope="row">${esc(t.track)}</th><td>${purpose}</td><td>${chips(t.colors, { small: true })}</td></tr>`;
      }) +
      "</section>"
    );
  }

  function mapSwitches(m) {
    return (
      '<section class="sheet-sec no-print"><h2>Switches</h2>' +
      dataTable("data-table", ["No.", "What it does"], m.switches,
        (s) => `<tr><th scope="row"><span class="sw-badge">${esc(s.n)}</span></th><td>${esc(s.what)}</td></tr>`) +
      "</section>"
    );
  }

  function renderMap(m) {
    const root = document.getElementById("crew-root");
    document.title = `${archive ? "Archive: " : ""}${m.title} station map — HART`;
    document.getElementById("page-title").textContent = m.title;
    // A current map is drawn from the system schematic, so it carries the schematic's revision and date.
    const sc = data.schematic;
    // a crew.json without the schematic's fields (a stale copy) keeps the line the page was published with
    if (archive || (sc.revision && sc.effective))
      document.getElementById("page-pub").textContent = pubLine(archive ? m : { pub: m.pub, revision: sc.revision, effective: sc.effective });
    document.getElementById("page-lede").textContent = archive ? m.what : m.now || m.what;

    const toggle = !m.rotated ? "" :
      '<div class="seg no-print" role="group" aria-label="Map orientation">' +
      `<button type="button" aria-pressed="true" data-src="${esc(u(m.img))}">Standard</button>` +
      `<button type="button" aria-pressed="false" data-src="${esc(u(m.rotated))}">Rotated (desk view)</button></div>`;
    const connects =
      `<section class="sheet-sec no-print"><h2>Connects to</h2><div class="map-cards">${join(m.connects, (id) => mapCard(mapById(id)))}</div></section>`;
    const figures = archive
      ? `<figure class="map-figure"><button type="button" class="map-open" data-zoom aria-label="Open ${esc(m.title)}` +
        ` map full screen"><img src="${esc(u(m.img))}" alt="${esc(m.alt)}" width="1600" height="1000"></button>` +
        `<figcaption class="no-print">Tap the map to zoom. ${ROTATE_HINT}</figcaption></figure>`
      : join(m.sheets, (id) => sheetFigure(id, m.sheets.length > 1));
    const note = !archive ? "" :
      `<p class="muted small no-print">Earlier hand-drawn map with the old switch numbers. <a href="${u(`crew/maps/${m.id}/index.html`)}">Current ${esc(m.title)} map</a></p>`;

    root.innerHTML =
      note + toggle + figures + mapTracks(m) + (archive ? mapSwitches(m) : "") + connects +
      actions((archive ? printButton("Print map (8×5)") + sourceButton(m.source) : "") +
        ghostLink(archive ? "crew/maps/archive/index.html" : "crew/maps/index.html", "All maps") +
        ghostLink("crew/index.html", "Session paperwork"));

    root.querySelectorAll(".seg button").forEach((b) => {
      b.addEventListener("click", () => {
        root.querySelectorAll(".seg button").forEach((o) => {
          o.setAttribute("aria-pressed", o === b ? "true" : "false");
        });
        root.querySelector(".map-figure img").src = b.getAttribute("data-src");
      });
    });
    wireZoom(root);
    wirePrint(root);
  }

  function spotName(id) {
    const hit = (data.spotsheet.industries || []).concat(data.spotsheet.offline || []).find((i) => i.id === id);
    return hit ? hit.name : id;
  }

  // One entry of a map list: a picture, a title, a small line and a description.
  const mapListItem = (href, img, title, small, what) =>
    `<li><a href="${href}"><img src="${esc(img)}" alt="" loading="lazy">` +
    `<span><strong>${esc(title)}</strong><small>${esc(small)}</small><em>${esc(what)}</em></span></a></li>`;

  function renderMapsIndex() {
    const root = document.getElementById("crew-root");
    if (archive) return renderMapsArchive(root);
    const sc = data.schematic;
    const levels = join(data.levels, (id) =>
      `<li><a href="${esc(sheetSrc(id))}"><img src="${esc(sheetSrc(id))}" alt="" loading="lazy" width="1056" height="816">` +
      `<span><strong>${esc(data.sheets[id][0])}</strong><em>${esc(data.sheets[id][1])}</em></span></a></li>`);
    const revision = sc.revision ? ` Revision ${sc.revision}${sc.effective ? ` · Effective ${sc.effective}` : ""}.` : "";
    root.innerHTML =
      '<section class="maps-index">' +
      '<figure class="key-map"><button type="button" class="map-open" data-zoom aria-label="Open the system schematic full screen">' +
      `<img src="${esc(u(sc.svg))}" alt="${esc(sc.alt)}" width="1056" height="816"></button>` +
      `<figcaption>${esc(sc.caption + revision)} <a href="${esc(u(sc.pdf))}">PDF to print</a>. <span class="no-print">Tap to zoom.</span></figcaption></figure>` +
      '<div><h2 class="sub-h">Station maps</h2><ul class="map-list">' +
      join(data.maps, (m) => mapListItem(mapHref(m.id), mapThumb(m), m.title, m.pub + (sc.revision ? ` · Rev ${sc.revision}` : ""), m.now || m.what)) +
      "</ul>" +
      `<h2 class="sub-h">Levels</h2><ul class="map-list">${levels}</ul>` +
      `<p class="small">The earlier hand-drawn maps, with the old switch numbers, are in the <a href="${u("crew/maps/archive/index.html")}">archive</a>.</p></div></section>` +
      actions(ghostLink("crew/index.html", "Session paperwork"));
    wireZoom(root);
  }

  function renderMapsArchive(root) {
    const o = data.overview;
    root.innerHTML =
      '<section class="maps-index">' +
      '<figure class="key-map"><button type="button" class="map-open" data-zoom aria-label="Open the subdivision diagram full screen">' +
      `<img src="${esc(u(o.img))}" alt="${esc(o.alt)}"></button>` +
      `<figcaption><strong>${esc(o.title)}</strong> · ${esc(pubLine(o))}<br>${esc(o.what)}` +
      ' <span class="no-print">Tap to zoom.</span></figcaption></figure>' +
      '<div><h2 class="sub-h">Station maps</h2><ul class="map-list">' +
      join(data.maps, (m) => mapListItem(mapHref(m.id), u(m.img), m.title, m.pub + (m.revision ? ` · Rev ${m.revision}` : ""), m.what)) +
      "</ul></div></section>" +
      actions(sourceButton(o.source, "SM-01 source docx") + ghostLink("crew/maps/index.html", "Current station maps"));
    wireZoom(root);
  }

  // —— Reference pages ——
  function renderColors() {
    const root = document.getElementById("crew-root");
    const group = (g, title) =>
      `<section class="sheet-sec"><h2>${esc(title)}</h2><ul class="cc-list cc-big">` +
      join(data.colors.filter((c) => c.group === g),
        (c) => `<li>${chip(c)}<a href="${spotHref(c.spot)}">${esc(c.dest)}</a><small>${esc(c.train)}</small></li>`) +
      "</ul></section>";
    root.innerHTML =
      group("island", "Local industries") +
      group("interchange", "Interchange") +
      `<details class="sheet-more" data-print-open><summary>As a table</summary>${colorTable(true)}</details>` +
      actions(printButton() + ghostLink("crew/index.html", "Session paperwork"));
    wirePrint(root);
  }

  function renderTT23() {
    const root = document.getElementById("crew-root");
    const tt = data.timetable;
    document.getElementById("page-pub").textContent = pubLine(tt);
    root.innerHTML =
      `<p class="tt-sub">${esc(tt.subtitle)}</p>` +
      `<div class="tt-layout"><div>${ttTable()}</div>` +
      `<section class="sheet-sec"><h2>Special instructions</h2><ol>${listItems(tt.instructions)}` +
      `</ol><p class="muted small">${esc(tt.bulletin)}</p>` +
      `<p class="small no-print">Where the stations are: <a href="${u("crew/maps/index.html")}">subdivision diagram and station maps</a>.</p></section></div>` +
      actions(printButton() + sourceButton(tt.source, "Source pptx") +
        ghostLink("crew/dispatcher/index.html", "Dispatcher train list") + ghostLink("crew/index.html", "Session paperwork"));
    wirePrint(root);
  }

  // A scale rule; "PASS — ..." and "REJECTED — ..." lead with the verdict as a badge.
  function ruleItem(i) {
    const m = /^(PASS|REJECTED) — (.*)$/.exec(i);
    if (m) return `<li><strong class="verdict verdict-${m[1].toLowerCase()}">${m[1]}</strong> ${esc(m[2])}</li>`;
    return `<li>${esc(i)}</li>`;
  }

  function renderScale() {
    const root = document.getElementById("crew-root");
    const s = data.scale;
    document.getElementById("page-pub").textContent = pubLine(s);
    root.innerHTML =
      `<p class="sheet-summary">${esc(s.summary)}</p>` +
      join(s.sections, (sec) =>
        `<section class="sheet-sec"><h2>${esc(sec.heading)}</h2>` +
        join(sec.parts, (p) => {
          const tag = p.ordered ? "ol" : "ul";
          return `<h3>${esc(p.h)}</h3><${tag} class="rule-list">${join(p.items, ruleItem)}</${tag}>`;
        }) +
        "</section>") +
      actions(printButton() + sourceButton(s.source) +
        ghostLink("crew/ck1/index.html", "CK1 crew sheet") + ghostLink("crew/index.html", "Session paperwork"));
    wirePrint(root);
  }

  // —— Spot sheets (EQ-01) ——
  function industryHtml(i, where) {
    const head = i.trackHead || ["Spot", "Track", "Cars", "In", "Out"];
    return (
      `<section class="panel spot-sheet" id="${esc(i.id)}"><div class="spot-head">${chip(colorById(i.color))}` +
      `<h2>${esc(i.name)}</h2></div><p class="spot-meta">Track ${esc(i.track)} · ${where(i)}` +
      ` · Served by ${esc(i.served)}</p>` +
      // The company history from the operator sheet, open under the header; off the printed card.
      `<details class="spot-history no-print" open><summary>About the company</summary><ul>${listItems(i.history)}</ul></details>` +
      `<p class="spot-traffic"><strong>Traffic:</strong> ${esc(i.traffic)}</p>` +
      `<h3>${i.trackHead ? "Tracks" : "Tracks &amp; spots"}</h3>` +
      dataTable("data-table", head.map(esc), i.spots,
        (r) => `<tr>${join(r, (c, ci) => (ci === 0 ? `<th scope="row">${esc(c)}</th>` : `<td>${esc(c)}</td>`))}</tr>`) +
      (i.spotNote ? `<p class="small muted">${esc(i.spotNote)}</p>` : "") +
      "</section>"
    );
  }

  function renderIndustries() {
    const root = document.getElementById("crew-root");
    const sh = data.spotsheet;
    const jump =
      '<nav class="jump no-print" aria-label="Jump to"><ul>' +
      join(sh.industries.concat(sh.offline),
        (i) => `<li><a href="#${esc(i.id)}">${chip(colorById(i.color), { small: true, swatchOnly: true })}${esc(i.name)}</a></li>`) +
      join(sh.desk, (d) => `<li><a href="#${esc(d.id)}">${esc(d.name)}</a></li>`) +
      "</ul></nav>";

    const where = (i) => {
      const m = mapById(i.map);
      return m ? `<a href="${mapHref(m.id)}">${esc(m.title)} map</a>` : "";
    };
    const list = (label, items, ordered) => {
      const tag = ordered ? "ol" : "ul";
      return `<h3>${esc(label)}</h3><${tag}>${listItems(items)}</${tag}>`;
    };
    const paragraphs = (ps) => join(ps, (p) => `<p>${esc(p)}</p>`);

    const off = join(sh.offline, (o) =>
      `<section class="panel spot-sheet" id="${esc(o.id)}"><div class="spot-head">${chip(colorById(o.color))}` +
      `<h2>${esc(o.name)}</h2></div><p class="spot-meta">${esc(o.tag)} · ${where(o)}</p>` +
      paragraphs(o.about) +
      `<div class="two-col"><div>${list(o.inLabel, o.inbound)}</div><div>${list(o.outLabel, o.outbound)}</div></div>` +
      `${list("Jobs", o.jobs)}</section>`);

    const desk = join(sh.desk, (d) =>
      `<section class="panel spot-sheet" id="${esc(d.id)}"><h2>${esc(d.name)}</h2><p class="spot-meta">${esc(d.tag)}` +
      `${d.map ? ` · ${where(d)}` : ""}</p>` +
      paragraphs(d.about) +
      join(d.lists, (l) => list(l.label, l.items, l.ordered)) +
      "</section>");

    root.innerHTML =
      `<p class="sheet-summary">${esc(sh.summary)}</p>${jump}` +
      `<h2 class="sub-h">On the island</h2>${join(sh.industries, (i) => industryHtml(i, where))}` +
      `<h2 class="sub-h">Interchange</h2>${off}` +
      `<h2 class="sub-h">Yard and desk notes</h2>${desk}` +
      actions(printButton() + sourceButton(sh.source) +
        ghostLink("briefing/index.html#industries", "Industries") + ghostLink("crew/index.html", "Session paperwork"));
    wirePrint(root);
    // Re-apply the hash now that the anchors exist.
    if (location.hash) {
      const t = document.getElementById(decodeURIComponent(location.hash.slice(1)));
      if (t) t.scrollIntoView();
    }
  }

  // The publications shelf links here with #print: wait for the images, then open the print dialog.
  function printWhenReady() {
    const imgs = Array.from(document.querySelectorAll("#crew-root img"));
    Promise.all(imgs.map((img) => {
      img.loading = "eager";
      return img.complete ? null : new Promise((res) => {
        img.addEventListener("load", res);
        img.addEventListener("error", res);
      });
    })).then(() => {
      try {
        history.replaceState(null, "", location.pathname + location.search);
      } catch (e) {} // a file:// page may refuse it: the #print stays in the address bar
      setTimeout(() => window.print(), 150);
    });
  }

  const PAGE_IDS = {
    sheet: "crew-sheet",
    map: "crew-map",
    maps: "crew-maps",
    colors: "crew-colors",
    tt23: "crew-tt23",
    scale: "crew-scale",
    industries: "crew-industries",
  };
  const RENDER = { maps: renderMapsIndex, colors: renderColors, tt23: renderTT23, scale: renderScale, industries: renderIndustries };

  function crumbsFor(kind) {
    const crumbs = [{ href: u("crew/index.html"), label: "Session paperwork" }];
    if (kind === "map") crumbs.push({ href: u("crew/maps/index.html"), label: "Station maps" });
    if (kind === "map" && archive) crumbs.push({ href: u("crew/maps/archive/index.html"), label: "Archive" });
    if (kind === "maps" && archive) crumbs.push({ href: u("crew/maps/index.html"), label: "Station maps" });
    return crumbs;
  }

  async function page(kind, id) {
    if (/-archive$/.test(kind)) {
      archive = true;
      kind = kind.replace(/-archive$/, "");
    }
    const root = document.getElementById("crew-root");
    try {
      if (!PAGE_IDS[kind]) throw new Error(`No crew page kind ${kind}`);
      site = await HARTOps.mountChrome(PAGE_IDS[kind]);
      extendCrumb(crumbsFor(kind));
      data = await HARTOps.loadJson("data/crew.json");
      if (kind === "sheet") {
        const job = (data.jobs || []).find((j) => j.id === id);
        if (!job) throw new Error(`No job ${id}`);
        renderSheet(job);
      } else if (kind === "map") {
        const m = mapById(id);
        if (!m) throw new Error(`No map ${id}`);
        renderMap(m);
      } else RENDER[kind]();
      if (location.hash === "#print") printWhenReady();
    } catch (err) {
      console.error(err);
      if (root) {
        HARTOps.renderError(root, {
          what: "this sheet",
          err,
          links: [{ href: "docs/index.html", label: "Publications shelf" }],
        });
      }
    }
  }

  window.HARTCrew = { page, chip };
})();
