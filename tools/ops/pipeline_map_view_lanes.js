  /* pipeline_map_view_lanes.js: part of app()'s body, inlined after pipeline_map_view_frame.js and before
     pipeline_map_view_rail.js (see pipeline_map_view.js). Not a script on its own. It holds the lane overview, the
     lanes opened from it, and the efficiency overlay.

     The lane overview is what the page opens on (an address with no view in it): one card per lane, drawn from the
     summaries the build worked out (DATA.lanes, DATA.bundles), so the page opens without laying out the whole map.
     A click on a card opens that lane (view.laneOpen): the map is drawn with the other lanes closed to one box each
     (collapseLanes), keeping their links counted. A click on an arrow opens the two lanes it joins. The address keeps
     the open lanes (lane=) and the overlay (eff=1); map=all marks the whole map when nothing else does.

     Every change of view goes through goOverview, openLanes, openLane or showWholeMap (and focusOn, in
     pipeline_map_view_input.js): each starts a history step (navStep, pipeline_map_view_nav.js) before it draws, so
     Back returns to the view before. After each drawing the page sends a "pipelinemap:view" event on document with
     the view as its detail (viewDetail). */
  const laneOf = {};
  DATA.lanes.forEach(l => (laneOf[l.id] = l));
  const KIND_WORD = { structured: ["data file"], unstructured: ["source"], generator: ["script"], output: ["output"],
                      external: ["external", "external"], host: ["host"], human: ["hand work", "hand work"] };
  const viewDetail = () => ({ overview: view.overview, lanes: [...view.laneOpen], focus: view.focus, selected, eff: view.eff });
  function announce() { document.dispatchEvent(new CustomEvent("pipelinemap:view", { detail: viewDetail() })); }

  /* ---- the lane overview */
  const plural = (n, one, many = one + "s") => `${n} ${n === 1 ? one : many}`;
  function stepLine(l) {  // the card's line of efficiency figures
    const s = l.steps, out = [];
    if (s.panels) out.push(`${plural(s.panels, "make panels step")}: ${[s.stamped && `${s.stamped} stamped`, s.guards && plural(s.guards, "guard")].filter(Boolean).join(", ")}`);
    if (s.checks) out.push(`${plural(s.checks, "check.sh job")}, all stamped`);
    if (!out.length) return "No make panels or check.sh steps";
    const timed = laneTimes(l.id);
    if (timed.length) out.push(`slowest: ${timed[0].s}, ${secs(timed[0].t)}`);
    return out.join(" · ");
  }
  function laneTimes(lane) {  // the lane's timed steps, slowest first: {s: step name, t: seconds}
    return DATA.nodes.filter(n => n.domain === lane && n.eff).flatMap(n => n.eff.filter(e => e.t).map(e => ({ s: e.s, t: runTime(e.t) })))
      .filter(e => e.t !== null).sort((a, b) => b.t - a.t);
  }
  function writerLine(lane) {  // shown with the overlay: the lane's outputs by writer count
    const outs = DATA.nodes.filter(n => n.domain === lane && n.w);
    if (!outs.length) return "No outputs";
    const bad = outs.filter(n => n.w.n > 1 && !n.w.ok).length, none = outs.filter(n => n.w.n === 0).length;
    return `${plural(outs.length, "output")}: ${bad} with two or more writers, ${none} with none`;
  }
  let ovSvg = null;
  function drawOverview() {
    lay = null; svg = null; vb = null; sub = { nodes: [], edges: [] }; nodeEl = {}; edgeEls = []; visible = new Set(); baseIds = new Set();
    groups = { members: {}, groupOf: {} }; gNodes = {};
    navSvg = null; navRect = null; nav.innerHTML = ""; nav.hidden = true; info.style.display = "none"; etip.hidden = true; closeLens();
    const narrow = innerWidth <= 900, cw = narrow ? 360 : 720, x0 = 16, wrapAt = Math.floor((cw - x0 - 12) / 6);
    const texts = {};  // each card's lines: its boxes by kind and status, then its steps
    DATA.lanes.forEach(l => {
      const st = Object.entries(l.status).filter(([k]) => k !== "live");
      const head = `${plural(l.n, "box", "boxes")}: ${Object.entries(l.kinds).map(([k, n]) => plural(n, ...(KIND_WORD[k] || [k]))).join(", ")}` +
        (st.length ? `; ${st.map(([k, n]) => `${n} ${k}`).join(", ")}` : "");
      texts[l.id] = [...wrap(head, wrapAt), ...wrap(stepLine(l), wrapAt)];
    });
    const lines = Math.max(...Object.values(texts).map(t => t.length)) + (view.eff ? 1 : 0);  // and the overlay's writer line
    const o = laneOverview(DATA.domains, DATA.bundles, cw, 50 + lines * 18, narrow ? 14 : 16, narrow ? 22 : 34);
    const name = id => domainLabel[id] || id, p = [];
    p.push(`<text class="ovhint" x="${cw / 2}" y="-14" text-anchor="middle">Click a lane to open it, or an arrow to open the two lanes it joins${DATA.timed ? "" : ". No step times are logged yet"}</text>`);
    o.arcs.slice().sort((a, b) => b.n - a.n).forEach(a => {  // the thickest first, so thin arcs stay on top to click
      const side = a.side ? `, ${a.side} of them side links that carry nothing on` : "", c = esc(DATA.domainColor[a.from]);
      p.push(`<g class="bundle" data-from="${esc(a.from)}" data-to="${esc(a.to)}" tabindex="0" role="button" aria-label="${esc(`${name(a.from)} to ${name(a.to)}: ${a.n} links. Open both lanes`)}">`,
        `<title>${esc(`${name(a.from)} → ${name(a.to)}: ${plural(a.n, "link")}${side}. Click to open both lanes.`)}</title>`,
        `<path class="bh" d="${a.d}"/><path class="bl" d="${a.d}" stroke="${c}" style="stroke-width:${a.w.toFixed(1)}px"/><path class="ah" d="${a.head}" fill="${c}"/>`,
        `<text class="bn" x="${a.lx.toFixed(1)}" y="${(a.ly + 4).toFixed(1)}" text-anchor="middle">${a.n}</text></g>`);
    });
    for (const c of o.cards) {
      const l = laneOf[c.id], d = DATA.domains.find(x => x.id === c.id), wide = c.w - x0 - 12, kinds = Object.entries(l.kinds);
      p.push(`<g class="lanecard" data-lane="${esc(c.id)}" tabindex="0" role="button" aria-label="${esc(`${d.label}: ${l.n} boxes. Open this lane`)}" transform="translate(${c.x},${c.y})">`,
        `<title>${esc(`${d.label}. Click to open this lane.`)}</title>`,
        `<rect class="cb" width="${c.w}" height="${c.h}" rx="8"/><rect width="7" height="${c.h}" rx="3" fill="${esc(d.color)}"/>`,
        `<text class="ct" x="${x0}" y="24" fill="${esc(tagInk(d.color))}">${esc(d.label)}</text>`);
      let bx = x0;  // the lane's boxes by kind, as a bar in the kinds' colours
      for (const [k, n] of kinds) {
        const w = wide * n / l.n;
        p.push(`<rect x="${bx.toFixed(1)}" y="32" width="${Math.max(w - 1, 0.5).toFixed(1)}" height="7" fill="${esc(DATA.kinds[k][2])}"><title>${n} ${esc(DATA.kinds[k][0].toLowerCase())}</title></rect>`);
        bx += w;
      }
      texts[c.id].forEach((t, i) => p.push(`<text class="cl" x="${x0}" y="${58 + i * 18}">${esc(t)}</text>`));
      if (view.eff) p.push(`<text class="cl" x="${x0}" y="${58 + texts[c.id].length * 18}">${esc(writerLine(c.id))}</text>`);
      p.push("</g>");
    }
    const a = freeArea(), pad = 24, top = 30;  // room above the cards for the hint
    const fullW = o.width, fullH = o.height + top;
    const s = Math.min((a.right - 2 * pad) / fullW, narrow ? Infinity : (a.bottom - a.top - 2 * pad) / fullH, 1.25);
    const pxH = Math.max(a.r.height, a.top + pad + fullH * s + pad);  // a phone scrolls down the cards
    const vx = o.left + fullW / 2 - a.right / 2 / s, vy = -top - (a.top + pad) / s;
    wrapEl.classList.add("ov");
    wrapEl.innerHTML = `<svg id="overview" xmlns="http://www.w3.org/2000/svg" style="height:${pxH.toFixed(0)}px" viewBox="${vx.toFixed(1)} ${vy.toFixed(1)} ${(a.r.width / s).toFixed(1)} ${(pxH / s).toFixed(1)}">${p.join("")}</svg>`;
    ovSvg = document.getElementById("overview");
    drawRulers();
    syncControls();
    showStatus(sub);
    announce();
  }
  function overviewTarget(t) {  // the lanes a click or key on the overview opens
    const card = t.closest && t.closest(".lanecard"), arc = t.closest && t.closest(".bundle");
    if (card) return [card.dataset.lane];
    if (arc) return [arc.dataset.from, arc.dataset.to];
    return null;
  }
  /* A lane opened from the overview: its click stops here, and the map below ignores clicks and double-clicks for a
     moment, so the second click of a double-click does not pick whatever box is drawn under the pointer. */
  let ovOpened = 0;
  const justOpened = () => performance.now() - ovOpened < 400;
  wrapEl.addEventListener("click", e => {
    if (!view.overview || !ovSvg) return;
    const lanes = overviewTarget(e.target);
    if (lanes) { e.stopImmediatePropagation(); ovOpened = performance.now(); openLanes(lanes); }
  });
  wrapEl.addEventListener("keydown", e => {
    if (!view.overview || (e.key !== "Enter" && e.key !== " ")) return;
    const lanes = overviewTarget(e.target);
    if (lanes) { e.preventDefault(); openLanes(lanes); }
  });

  /* ---- moving between the overview, open lanes and the whole map */
  function resetFilters() {  // the filters and View's boxes and links options as they start, without drawing
    view.f = emptyFacets(); view.hide = false;
    view.compact = true; view.group = false; view.open.clear(); view.trim = false;
    document.getElementById("labels").checked = true;
  }
  function goOverview() {  // the lane cards summarize every box, so the filters go back to none
    navStep();
    view.focus = null; selected = null; view.laneOpen.clear(); resetFilters(); fileIn.value = "";
    view.overview = true;
    render(false); writeHash();
  }
  function openLanes(ids) {  // these lanes open, the others closed to one box each; every lane open is the whole map
    navStep();
    view.overview = false; view.focus = null; selected = null; fileIn.value = "";
    view.laneOpen = new Set(ids.filter(id => allLanes.includes(id)));
    if (view.laneOpen.size === allLanes.length) view.laneOpen.clear();
    syncControls(); render(false); writeHash();
  }
  function openLane(lane, then) {  // one more lane open, from a closed lane's box; then: a box in it to pick
    openLanes([...view.laneOpen, lane]);
    if (then && visible.has(then)) { select(then); centreOn(then, false); }
  }
  function showWholeMap() {  // every lane drawn in full; the filters stay as they are
    navStep();
    view.overview = false; view.focus = null; view.laneOpen.clear(); if (view.trim) selected = null; fileIn.value = "";
    syncControls(); render(false); writeHash();
  }
  document.getElementById("showall").onclick = showWholeMap;
  const closedLaneName = d => `${domainLabel[d]} (closed)`;

  /* ---- efficiency overlay (E, or the Efficiency button): badges drawn with every box (effMarks), shown while the page
     has the class "eff". A stamped step is skipped while its inputs are unchanged; a guard always runs. */
  const SLOW = 10, VERY_SLOW = 60;  // seconds: amber from SLOW, red from VERY_SLOW
  const runTime = t => (t.warm_s ?? t.cold_s ?? null);  // a usual run: the warm time when the timings have one
  const secs = s => (s >= 10 ? `${Math.round(s)} s` : `${+s.toFixed(1)} s`);
  const effBtn = document.getElementById("effbtn");
  function setEff(on, quiet) {
    view.eff = on;
    document.body.classList.toggle("eff", on);
    effBtn.setAttribute("aria-pressed", on ? "true" : "false");
    if (ovSvg && !quiet) drawOverview();  // the cards take a line for the outputs' writers
    if (!quiet) writeHash();
  }
  effBtn.onclick = () => setEff(!view.eff);
  document.addEventListener("keydown", e => {
    if (e.target.matches("input:not([type=checkbox]):not([type=radio]):not([type=button]),textarea,select") || e.target.isContentEditable || e.metaKey || e.ctrlKey || e.altKey) return;
    if ((e.key === "e" || e.key === "E") && !e.shiftKey) setEff(!view.eff);
  });
  // the badges, centred on (x, y); also drawn in the legend's key
  const BADGE = {
    stamp: (x, y) => `<circle cx="${x}" cy="${y}" r="7" fill="#15803d"/><path d="M${x - 4},${y - 3} l3,3 l-3,3 M${x},${y - 3} l3,3 l-3,3" stroke="#fff" stroke-width="1.6" fill="none"/>`,
    guard: (x, y) => `<rect x="${x - 7}" y="${y - 7}" width="14" height="14" rx="3" fill="#1d4ed8"/><circle cx="${x}" cy="${y}" r="3.2" fill="none" stroke="#fff" stroke-width="1.6"/>`,
    writers: (x, y, n, cls) => `<circle class="wc ${cls}" cx="${x}" cy="${y}" r="8"/><text class="wn ${cls}" x="${x}" y="${y + 3.5}" text-anchor="middle">${n}</text>`,
    bar: (x, y, w, cls) => `<rect class="tb ${cls}" x="${x}" y="${y}" width="${w}" height="4" rx="2"/>`,
    ring: (x, y, w, h) => `<rect class="ring" x="${x}" y="${y}" width="${w}" height="${h}" rx="9"/>`,
  };
  const timeClass = s => (s >= VERY_SLOW ? "vslow" : s >= SLOW ? "slow" : "quick");
  const modeText = e => (e.m === "guard" ? "a guard: always runs" : "stamped: skipped while its inputs are unchanged");
  const runnerText = e => (e.r === "panels" ? `make panels step ${e.s}` : `check.sh job ${e.s}`);
  function writerText(w) {
    if (w.n === 0) return "No script on the map writes this output";
    if (w.n === 1) return "One script writes this output";
    if (w.ok === "updates") return `${w.n} scripts write this output; each is a make panels step that lists it in updates and rewrites only its part`;
    if (w.ok === "shared") return `${w.n} scripts write this output; SHARED_OUTPUTS in manifest_panels.py lists it, and both write it whole the same way`;
    return `${w.n} scripts write this output, and the step manifests do not list it as shared`;
  }
  function effMarks(n, bw, bh) {  // a box's badges (inside its own group, at its own size)
    if (!n.eff && !n.w) return "";
    const p = ['<g class="effb">'];
    let x = bw - 12;
    if (n.eff) {
      const times = n.eff.map(e => (e.t ? runTime(e.t) : null)), timed = times.filter(t => t !== null);
      if (!timed.length) p.push(BADGE.ring(-4, -4, bw + 8, bh + 8));
      for (const m of ["guard", "step"]) {
        const mine = n.eff.filter(e => e.m === m);
        if (!mine.length) continue;
        p.push(`<g><title>${esc(mine.map(e => `${runnerText(e)}, ${modeText(e)}`).join("\n"))}</title>${BADGE[m === "guard" ? "guard" : "stamp"](x, 0)}</g>`);
        x -= 18;
      }
      if (timed.length) {
        const s = timed.reduce((a, b) => a + b, 0), share = Math.min(1, Math.log10(1 + s) / Math.log10(1 + 600));
        const tip = n.eff.filter(e => e.t).map(e => `${e.s}: ${[e.t.warm_s != null && `warm ${secs(e.t.warm_s)}`, e.t.cold_s != null && `cold ${secs(e.t.cold_s)}`,
          e.t.runs != null && `${e.t.runs} runs`, e.t.skip_rate != null && `skipped ${Math.round(e.t.skip_rate * 100)}%`].filter(Boolean).join(", ")}`).join("\n");
        p.push(`<g><title>${esc(tip)}</title>${BADGE.bar(8, bh - 7, Math.max(4, (bw - 16) * share).toFixed(1), timeClass(s))}`,
          `<text class="tt ${timeClass(s)}" x="${x + 6}" y="4" text-anchor="end">${esc(secs(s))}</text></g>`);
      }
    }
    if (n.w) {
      const cls = n.w.n === 0 ? "none" : n.w.n > 1 && !n.w.ok ? "bad" : n.w.n > 1 ? "ok" : "one";
      p.push(`<g><title>${esc(writerText(n.w))}</title>${BADGE.writers(x, 0, n.w.n, cls)}</g>`);
    }
    p.push("</g>");
    return p.join("");
  }
  function effInfo(n) {  // the info panel's lines on how the box runs and who writes it
    const out = (n.eff || []).map(e => {
      const t = e.t ? [e.t.warm_s != null && `warm ${secs(e.t.warm_s)}`, e.t.cold_s != null && `cold ${secs(e.t.cold_s)}`, e.t.runs != null && `${e.t.runs} runs`,
        e.t.skip_rate != null && `skipped ${Math.round(e.t.skip_rate * 100)}% of runs`].filter(Boolean).join(", ") : "no logged time";
      return `<li>${esc(runnerText(e))}: ${esc(modeText(e))} · ${esc(t)}</li>`;
    });
    if (n.w) out.push(`<li>${esc(writerText(n.w))}</li>`);
    return out.length ? `<b>How it runs</b><ul>${out.join("")}</ul>` : "";
  }
  /* the legend's key for the overlay, from the same badges */
  (function effKey() {
    const icon = (body, w = 18) => `<svg class="ki" width="${w}" height="18" viewBox="${-w / 2} -9 ${w} 18">${body}</svg>`;
    const fill = (id, html) => { const el = document.getElementById(id); if (el) el.innerHTML = html; };
    fill("key-stamp", icon(BADGE.stamp(0, 0)));
    fill("key-guard", icon(BADGE.guard(0, 0)));
    fill("key-writers", icon(BADGE.writers(0, 0, 1, "one")) + icon(BADGE.writers(0, 0, 2, "bad")) + icon(BADGE.writers(0, 0, 0, "none")));
    fill("key-time", icon(BADGE.bar(-12, -2, 24, "slow"), 28) + icon(BADGE.bar(-12, -2, 24, "vslow"), 28));
    fill("key-ring", icon(BADGE.ring(-8, -7, 16, 14)));
    fill("key-timed", DATA.timed ? "" : " This build has no step timings (docs/pipeline-map/timings.json), so every step has the ring.");
  })();

