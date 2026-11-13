"use strict";
// Speed-match dashboard client. Polls /api/state; every value from the server goes in with textContent.
const $ = (id) => document.getElementById(id);
const SVGNS = "http://www.w3.org/2000/svg";
const MAX_STEP = 126, TOL = 3;
let S = null, manual = null, showTable = false;

function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") e.className = v; else if (k === "text") e.textContent = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v);
  }
  for (const c of kids) if (c != null) e.append(c);
  return e;
}
function svg(tag, attrs, text) {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
  if (text != null) e.textContent = text;
  return e;
}
const fmt = (v, d = 0) => (v == null || isNaN(v) ? "-" : Number(v).toFixed(d));
function dur(s) {
  if (s == null) return "-";
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}` : `${m}:${String(x).padStart(2, "0")}`;
}
const clock = (t) => new Date(t * 1000).toLocaleTimeString([], { hour12: false });
const locoVar = (loco) => (loco === "2738" ? "var(--c2738)" : "var(--c2121)");
const STATUS = { waiting: "Waiting", starting: "Starting", warming: "Warming up", settling: "Settling", measuring: "Measuring", done: "Done", stopped: "Stopped", error: "Error", aborted: "Aborted" };
const ICON = { waiting: "…", starting: "▸", warming: "♨", settling: "◔", measuring: "●", done: "✓", stopped: "■", error: "✕", aborted: "✕" };
const finished = (r) => ["done", "stopped", "error", "aborted"].includes(r.status);

function focusRun() {
  if (!S || !S.runs.length) return null;
  return S.runs.find((r) => r.id === manual) || S.runs.find((r) => r.id === S.focus) || S.runs[S.runs.length - 1];
}

// ---------------------------------------------------------------- theme
function setTheme(t) {
  if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
  try { t ? localStorage.setItem("sm-theme", t) : localStorage.removeItem("sm-theme"); } catch (e) {}
  if (S) render();
}
try { const t = localStorage.getItem("sm-theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) {}
{ const q = new URLSearchParams(location.search).get("theme"); if (q === "dark" || q === "light") document.documentElement.dataset.theme = q; }
$("theme").addEventListener("click", () => {
  const dark = document.documentElement.dataset.theme
    ? document.documentElement.dataset.theme === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches;
  setTheme(dark ? "light" : "dark");
});
$("follow").addEventListener("click", () => { manual = null; render(); });
$("tbl").addEventListener("click", () => { showTable = !showTable; $("tbl").textContent = showTable ? "Chart" : "Table"; renderChart(); });

// ---------------------------------------------------------------- banner and header
function renderTop(run) {
  $("mode").textContent = S.mode;
  $("livedot").className = "dot" + (S.reachable && run && !finished(run) ? " on" : "");
  const c = $("conn");
  c.textContent = S.reachable ? (S.mode === "live" ? "Pi connected" : "Playing " + S.mode) : (S.message || "Pi not reachable, retrying");
  c.className = "conn" + (S.reachable ? "" : " bad");
  $("follow").hidden = !manual;
  const b = $("banner");
  let level = null, text = null;
  if (!S.reachable) { level = "net"; text = S.message || "Pi not reachable, retrying"; }
  else if (run && run.banner) { level = run.banner[0]; text = run.banner[1] + (run.road ? "  (" + run.road + ")" : ""); }
  b.hidden = !text;
  if (text) { b.className = "banner " + level; b.textContent = (level === "error" ? "✕ " : "⚠ ") + text; }
}

// ---------------------------------------------------------------- hero
function renderHero(run) {
  const h = $("hero");
  h.replaceChildren();
  if (!run) { h.append(el("p", { class: "empty", text: "Waiting for a run. Start one with drop_job.sh, or run this server with --demo." })); return; }
  h.style.setProperty("--loco", locoVar(run.loco));
  const photo = run.photo ? el("img", { class: "photo", src: run.photo, alt: run.road || "Locomotive" }) : el("div", { class: "photo none", text: "No photo" });
  const stepPct = run.step != null ? (100 * run.step) / MAX_STEP : 0;
  const gauge = el("div", { class: "gauge", role: "img", "aria-label": `Throttle step ${run.step ?? "none"} of ${MAX_STEP}` });
  gauge.append(el("i", { style: `width:${stepPct}%` }));
  for (const s of run.steps || []) gauge.append(el("b", { style: `left:${(100 * s) / MAX_STEP}%` }));
  let status = STATUS[run.status] || run.status;
  if (run.status === "warming") status += run.warm && run.warm.secs ? ` (${run.warm.secs} s)` : "";
  if (run.status === "settling" && run.settle_left != null) status += ` (${Math.ceil(run.settle_left)} s)`;
  if (finished(run) && run.reason) status += ": " + run.reason;
  const eta = run.eta;
  const info = el("div", {},
    el("h2", { text: run.road || "Unknown loco" }),
    el("p", { class: "model", text: (run.model || "") + (run.kind !== "steprun" ? "  ·  " + run.kind : "") }),
    el("div", { class: "chips" },
      el("span", { class: "chip st-" + run.status, text: (ICON[run.status] || "") + " " + status }),
      el("span", { class: "chip", text: (run.direction === "reverse" ? "◀ " : "▶ ") + (run.direction || "direction ?") }),
      el("span", { class: "chip", text: "Route " + (run.route || "?") })),
    el("div", { class: "stats" },
      stat("Throttle step", run.step != null ? `${run.step}` : "-", ` / ${MAX_STEP}  (${fmt(stepPct)}%)`),
      stat("Speed", fmt(run.speed, 1), "mm/s"),
      stat("Scale speed", fmt(run.speed_mph, 1), "mph HO"),
      stat("Elapsed", dur(run.elapsed), ""),
      run.pass ? stat("Pass step", String(run.pass.step), "") : stat(finished(run) ? "Steps done" : "Time left (rough)", finished(run) ? `${run.done_steps}` : (eta != null ? dur(eta) : "-"), finished(run) ? ` / ${(run.steps || []).length || "?"}` : "")),
    gauge,
    el("div", { class: "gauge-l" }, el("span", { text: "0" }), el("span", { text: run.pass ? "pass job" : `${run.done_steps} of ${(run.steps || []).length || "?"} steps measured` }), el("span", { text: String(MAX_STEP) })));
  h.append(photo, info);
}
function stat(k, v, unit) {
  return el("div", { class: "stat" }, el("div", { class: "v" }, v, unit ? el("small", { text: unit }) : null), el("div", { class: "k", text: k }));
}

// ---------------------------------------------------------------- track strip
function renderStrip(run) {
  const card = $("stripcard");
  card.hidden = !run || !run.blocks.length;
  if (card.hidden) return;
  $("stripsub").textContent = `${run.direction === "reverse" ? "reverse" : "forward"} running order, width in proportion to length`;
  const wrap = el("div", { class: "strip", style: `--loco:${locoVar(run.loco)}` });
  for (const b of run.blocks) {
    const w = b.mm ? Math.max(b.mm, 120) : 160;
    const s = el("div", { class: "seg" + (b.current ? " cur" : "") + (b.mm_s != null ? " hit" : "") + (b.mm ? "" : " nolen"), style: `flex:${w} 1 0`, title: `${b.name}: ${b.mm ? fmt(b.mm / 25.4, 1) + " in" : "length unknown"}${b.mm_s != null ? ", " + fmt(b.mm_s, 1) + " mm/s" : ""}` },
      el("div", { class: "tr", text: b.current ? "▼" : "" }),
      el("div", { class: "nm", text: b.name.replace(/^(Track|OS) /, "") }),
      el("div", { class: "in", text: b.mm ? fmt(b.mm / 25.4, 1) + '"' : "?" }),
      el("div", { class: "sp", text: b.mm_s != null ? fmt(b.mm_s, 0) : "" }));
    wrap.append(s);
  }
  const host = $("strip");
  host.className = "strip-wrap";
  host.replaceChildren(wrap);
}

// ---------------------------------------------------------------- current step
function renderStep(run) {
  const card = $("stepcard");
  card.hidden = !run;
  if (!run) return;
  const p = $("steppanel");
  p.replaceChildren();
  if (run.pass) {
    const ps = run.pass;
    $("stepsub").textContent = `pass at step ${ps.step}: ${ps.from} to ${ps.to}`;
    const t = el("table", {});
    t.append(el("tr", {}, ...["Sensor", "Block mm", "Lit at s", "Across s", "mm/s"].map((x) => el("th", { text: x }))));
    for (const r of ps.rows) {
      t.append(el("tr", {}, el("td", { text: r.sensor.replace(/^BS /, "") }), el("td", { text: fmt(r.mm) }),
        el("td", { text: fmt(r.t_rel, 1) }), el("td", { text: fmt(r.dt, 1) }), el("td", { text: fmt(r.dt && r.mm ? r.mm / r.dt : null, 1) })));
    }
    p.append(t);
    p.append(el("p", { class: "sub", text: ps.reason ? `Pass ended: ${ps.reason}` : "Waiting for the loco to cross the stretch. Times are seconds after the pass started." }));
    return;
  }
  $("stepsub").textContent = run.step != null ? `step ${run.step}` : "";
  const rows = run.step_rows || [];
  if (run.status === "settling" && run.settle_left != null)
    p.append(el("p", {}, "Settling, measuring starts in ", el("span", { class: "countdown tnum", text: Math.ceil(run.settle_left) + " s" })));
  if (run.status === "warming") p.append(el("p", { text: "Warming up the motor and gears before measuring." }));
  if (rows.length) {
    const t = el("table", {});
    t.append(el("tr", {}, ...["Block", "mm", "Time s", "mm/s"].map((x) => el("th", { text: x }))));
    for (const r of rows) {
      t.append(el("tr", {}, el("td", { text: (r.block || (r.i != null ? "reading " + r.i : "")).replace(/^(Track|OS|BS) /, "") }),
        el("td", { text: fmt(r.mm) }), el("td", { text: fmt(r.dt, 1) }), el("td", { text: fmt(r.mm_s, 1) })));
    }
    p.append(t);
    p.append(el("div", { class: "sumrow" },
      el("span", {}, "Sum ", el("b", { text: fmt(run.step_sum_mm) + " mm in " + fmt(run.step_sum_s, 1) + " s" })),
      el("span", {}, "Average ", el("b", { text: run.step_sum_s ? fmt(run.step_sum_mm / run.step_sum_s, 1) + " mm/s" : "-" })),
      el("span", {}, "Spread ", el("b", { text: run.step_spread != null ? fmt(run.step_spread * 100, 1) + "%" : "-" }))));
  } else if (run.status !== "settling" && run.status !== "warming") {
    p.append(el("p", { class: "empty", text: "No readings yet for this step." }));
  }
  if (run.extra != null)
    p.append(el("p", { class: "sub", text: `Readings spread ${fmt(run.extra * 100, 1)}%, so one more reading is being taken.` }));
  const ld = run.last_done;
  if (ld) {
    const bad = !ld.valid;
    const why = ld.reason === "max" ? "time ran out before the distance was reached" : ld.reason === "stalled" ? "the loco stalled" : ld.reason === "timed" ? "time limit reached with good data" : "";
    p.append(el("p", { class: bad ? "flagline" : "okline", text: (bad ? "▲ Not valid: " : "✓ Measured: ") + (ld.mm_s ? fmt(ld.mm_s, 1) + " mm/s" : "no reading") + ` (${ld.reason || "done"}${why ? ", " + why : ""})` }));
  }
}

// ---------------------------------------------------------------- chart
function series() {
  // latest run per loco+direction, its completed steps
  const m = new Map();
  for (const r of S.runs) if (r.loco && r.curve.length) m.set(r.loco + "|" + r.direction, r);
  return [...m.values()].sort((a, b) => (a.loco + a.direction).localeCompare(b.loco + b.direction))
    .map((r) => ({ key: r.loco + " " + r.direction, loco: r.loco, dir: r.direction, pts: r.curve, road: r.road }));
}
function lineKey(color, dash, dots) {
  const s = svg("svg", { viewBox: "0 0 28 8" });
  s.append(svg("line", { x1: 1, x2: 27, y1: 4, y2: 4, stroke: color, "stroke-width": 2.5, "stroke-linecap": "round", "stroke-dasharray": dots ? "1 4" : dash ? "5 4" : "none", "stroke-opacity": dots ? 0.6 : 1 }));
  return s;
}
let chartSig = "";
function renderChart(force) {
  const ser = series();
  const sig = JSON.stringify([ser, S.runs.map((r) => r.flagged), S.reference, showTable, document.documentElement.dataset.theme, $("chart").clientWidth]);
  if (sig === chartSig && !force) return;
  chartSig = sig;
  const ref = S.reference || {};
  const lg = $("legend");
  lg.replaceChildren();
  for (const s of ser) lg.append(el("span", {}, lineKey(locoVar(s.loco), s.dir === "reverse"), `${s.road} ${s.dir}`));
  if (Object.keys(ref).length) lg.append(el("span", {}, lineKey("var(--ink-3)", false, true), "2026-11-08 result ×1.122"));
  const fl = [];
  for (const r of S.runs) for (const f of r.flagged || []) fl.push(`${r.loco} ${r.direction === "reverse" ? "rev" : "fwd"} step ${f.step} (${f.reason})`);
  $("flagnote").textContent = fl.length ? "▲ Not on the curve, not valid or no reading: " + fl.join(", ") : "";
  $("chart").parentNode.hidden = showTable;
  $("datatable").hidden = !showTable;
  if (showTable) return renderDataTable(ser);
  const svgEl = $("chart");
  const W = svgEl.clientWidth || 600, H = svgEl.clientHeight || 360;
  svgEl.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svgEl.replaceChildren();
  const m = { l: 46, r: 92, t: 12, b: 34 };
  const allv = ser.flatMap((s) => s.pts.map((p) => p.mm_s)).concat(...Object.values(ref).map((a) => a.map((p) => p.mm_s)));
  const ymax = Math.max(100, Math.ceil((Math.max(...allv, 0) * 1.05) / 100) * 100);
  const X = (v) => m.l + (v / MAX_STEP) * (W - m.l - m.r);
  const Y = (v) => H - m.b - (v / ymax) * (H - m.t - m.b);
  const tc = "var(--ink-3)";
  for (let v = 0; v <= ymax; v += ymax > 400 ? 100 : 50) {
    svgEl.append(svg("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), stroke: "var(--grid)", "stroke-width": 1 }));
    svgEl.append(svg("text", { x: m.l - 6, y: Y(v) + 4, "text-anchor": "end", fill: tc, "font-size": 12 }, v));
  }
  for (let s = 0; s <= MAX_STEP; s += 21) svgEl.append(svg("text", { x: X(s), y: H - m.b + 18, "text-anchor": "middle", fill: tc, "font-size": 12 }, s));
  svgEl.append(svg("text", { x: (m.l + W - m.r) / 2, y: H - 3, "text-anchor": "middle", fill: tc, "font-size": 12 }, "throttle step"));
  const path = (pts) => pts.map((p, i) => (i ? "L" : "M") + X(p.step).toFixed(1) + " " + Y(p.mm_s).toFixed(1)).join(" ");
  for (const [loco, pts] of Object.entries(ref))
    svgEl.append(svg("path", { d: path(pts), fill: "none", stroke: locoVar(loco), "stroke-opacity": 0.28, "stroke-width": 1.5, "stroke-dasharray": "1 4", "stroke-linecap": "round" }));
  const labelY = [];
  for (const s of ser) {
    const c = locoVar(s.loco), rev = s.dir === "reverse";
    svgEl.append(svg("path", { d: path(s.pts), fill: "none", stroke: c, "stroke-width": 2.5, "stroke-linejoin": "round", "stroke-linecap": "round", "stroke-dasharray": rev ? "7 5" : "none" }));
    for (const p of s.pts) svgEl.append(svg("circle", { cx: X(p.step), cy: Y(p.mm_s), r: 4, fill: c, stroke: "var(--surface)", "stroke-width": 2 }));
    const last = s.pts[s.pts.length - 1];
    let ly = Y(last.mm_s);
    for (const o of labelY) if (Math.abs(o - ly) < 14) ly = o + 14;
    labelY.push(ly);
    svgEl.append(svg("text", { x: X(last.step) + 8, y: ly + 4, fill: "var(--ink)", "font-size": 12, "font-weight": 600 }, `${s.loco} ${rev ? "rev" : "fwd"}`));
  }
  const cross = svg("line", { y1: m.t, y2: H - m.b, stroke: "var(--ink-3)", "stroke-width": 1, visibility: "hidden" });
  svgEl.append(cross);
  const steps = [...new Set(ser.flatMap((s) => s.pts.map((p) => p.step)))].sort((a, b) => a - b);
  const tip = $("tip");
  const move = (ev) => {
    const r = svgEl.getBoundingClientRect(), x = ((ev.clientX - r.left) / r.width) * W;
    if (!steps.length) return;
    let best = steps[0];
    for (const s of steps) if (Math.abs(X(s) - x) < Math.abs(X(best) - x)) best = s;
    cross.setAttribute("x1", X(best)); cross.setAttribute("x2", X(best)); cross.setAttribute("visibility", "visible");
    tip.replaceChildren(el("div", { class: "t", text: "Step " + best }));
    for (const s of ser) {
      const p = s.pts.find((q) => q.step === best);
      if (p) tip.append(el("div", { class: "r" }, lineKey(locoVar(s.loco), s.dir === "reverse"), `${s.loco} ${s.dir}`, el("b", { text: fmt(p.mm_s, 1) + " mm/s · " + fmt(p.mm_s * 3.6 * 87 / 1609.34, 1) + " mph" })));
    }
    tip.hidden = false;
    const px = (X(best) / W) * r.width;
    tip.style.left = (px > r.width * 0.6 ? px - tip.offsetWidth - 12 : px + 12) + "px";
    tip.style.top = "10px";
  };
  svgEl.onpointermove = move;
  svgEl.onpointerleave = () => { tip.hidden = true; cross.setAttribute("visibility", "hidden"); };
  if (!ser.length) svgEl.append(svg("text", { x: W / 2, y: H / 2, "text-anchor": "middle", fill: tc, "font-size": 14 }, "No steps measured yet"));
}
function renderDataTable(ser) {
  const d = $("datatable");
  d.replaceChildren();
  const steps = [...new Set(ser.flatMap((s) => s.pts.map((p) => p.step)))].sort((a, b) => a - b);
  const t = el("table", {});
  t.append(el("tr", {}, el("th", { text: "Step" }), ...ser.map((s) => el("th", { text: `${s.loco} ${s.dir}` }))));
  for (const st of steps) t.append(el("tr", {}, el("td", { text: st }), ...ser.map((s) => { const p = s.pts.find((q) => q.step === st); return el("td", { text: p ? fmt(p.mm_s, 1) : "-" }); })));
  d.append(t);
}

// ---------------------------------------------------------------- comparison
function renderCompare() {
  const host = $("compare");
  host.replaceChildren();
  const ser = series();
  const pick = (loco, dir) => ser.find((s) => s.loco === loco && s.dir === dir);
  const wrap = el("div", { class: "pairs" });
  let any = false;
  for (const dir of ["forward", "reverse"]) {
    const a = pick("2121", dir), b = pick("2738", dir);
    const steps = [...new Set([...(a ? a.pts : []), ...(b ? b.pts : [])].map((p) => p.step))].sort((x, y) => x - y);
    const t = el("table", {});
    t.append(el("tr", {}, ...["Step", "2121", "2738", "2738 vs 2121"].map((x) => el("th", { text: x }))));
    for (const st of steps) {
      const va = a && a.pts.find((p) => p.step === st), vb = b && b.pts.find((p) => p.step === st);
      let cell = el("td", { text: "-" });
      if (va && vb) {
        const dev = (vb.mm_s / va.mm_s - 1) * 100, out = Math.abs(dev) > TOL;
        cell = el("td", { class: out ? "flag" : "good", text: (out ? (dev > 0 ? "▲ " : "▼ ") : "✓ ") + (dev > 0 ? "+" : "") + fmt(dev, 1) + "%" });
      }
      t.append(el("tr", {}, el("td", { text: st }), el("td", { text: va ? fmt(va.mm_s, 1) : "-" }), el("td", { text: vb ? fmt(vb.mm_s, 1) : "-" }), cell));
      any = true;
    }
    wrap.append(el("div", {}, el("p", { class: "pair", text: `Both ${dir}` }), steps.length ? t : el("p", { class: "empty", text: "No data yet." })));
  }
  host.append(any ? wrap : el("p", { class: "empty", text: "Appears once both locos have steps measured." }));
}

// ---------------------------------------------------------------- run list and feed
function renderRuns(run) {
  const host = $("runs");
  host.replaceChildren();
  if (!S.runs.length) { host.append(el("p", { class: "empty", text: "No logs seen yet." })); return; }
  const t = el("table", {});
  t.append(el("tr", {}, ...["Loco", "Dir", "Kind", "Steps", "Status"].map((x) => el("th", { text: x }))));
  for (const r of [...S.runs].reverse()) {
    const tr = el("tr", { class: "click" + (run && r.id === run.id ? " sel" : ""), tabindex: 0, onclick: () => { manual = r.id; render(); }, onkeydown: (e) => { if (e.key === "Enter") { manual = r.id; render(); } } },
      el("td", { text: r.road || "?" }), el("td", { text: r.direction || "-" }), el("td", { text: r.kind }),
      el("td", { text: r.pass ? "pass " + r.pass.step : `${r.done_steps}${r.steps.length ? " / " + r.steps.length : ""}` }),
      el("td", { text: (ICON[r.status] || "") + " " + (STATUS[r.status] || r.status) }));
    t.append(tr);
  }
  host.append(t);
}
function renderFeed(run) {
  const f = $("feed");
  f.replaceChildren();
  if (!run) return;
  for (const e of [...run.events].reverse().filter((x) => x.level !== "debug").slice(0, 15))
    f.append(el("li", {}, el("span", { class: "tm", text: clock(e.t) }), el("span", { class: e.level, text: e.text })));
}

function render() {
  const run = focusRun();
  renderTop(run); renderHero(run); renderStrip(run); renderStep(run);
  renderChart(); renderCompare(); renderRuns(run); renderFeed(run);
}
async function tick() {
  try {
    const r = await fetch("/api/state", { cache: "no-store" });
    S = await r.json();
  } catch (e) {
    S = S ? { ...S, reachable: false, message: "Dashboard server not responding, retrying" } : { runs: [], mode: "", reachable: false, message: "Dashboard server not responding, retrying", reference: {} };
  }
  render();
}
let rz;
addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => S && renderChart(), 150); });
tick();
setInterval(tick, 1000);
