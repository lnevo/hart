"use strict";
// Speed-match dashboard client. Two data sources, one set of panels: live polls /api/state;
// recorded (the website page sets window.SM_RECORDED) reads the static JSON export_site_runs.py
// wrote, with a run picker. Every value from either source goes in with textContent.
const $ = (id) => document.getElementById(id);
const REC = window.SM_RECORDED || null;  // {base: folder of index.json, photos: {loco: url}, tz: time zone of the logs, poll: ms (live on the Pi)}
const POLL = REC && REC.poll ? REC.poll : 0;  // the Pi page re-reads the files the publisher keeps writing
const bare = (id) => String(id || "").replace(/\.log$/, "");  // run ids with or without the log suffix
const ROOT = document.querySelector(".smd") || document.documentElement;  // where the theme attribute lives
let INDEX = [];  // recorded: the published runs, newest first
const SVGNS = "http://www.w3.org/2000/svg";
const MAX_STEP = 126, TOL = 3;
let S = null, manual = null, picked = false, showTable = false;
let RP = null;  // recorded: the replay of the picked run while one is loaded (see replay below)

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
const clock = (t) => new Date(t * 1000).toLocaleTimeString([], { hour12: false, timeZone: REC ? REC.tz : undefined });
const when = (t) => new Date(t * 1000).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: REC ? REC.tz : undefined });
const locoVar = (loco) => (loco === "2738" ? "var(--c2738)" : "var(--c2121)");
const STATUS = { waiting: "Waiting", starting: "Starting", warming: "Warming up", settling: "Settling", measuring: "Measuring", computing: "Computing", done: "Done", stopped: "Stopped", error: "Error", aborted: "Aborted" };
const ICON = { waiting: "…", starting: "▸", warming: "♨", settling: "◔", measuring: "●", computing: "…", done: "✓", stopped: "■", error: "✕", aborted: "✕" };
const finished = (r) => ["done", "stopped", "error", "aborted"].includes(r.status);

function focusRun() {
  if (!S || !S.runs.length) return null;
  return S.runs.find((r) => r.id === S.focus) || null;  // the server sends full detail for this one
}

// ---------------------------------------------------------------- theme
function setTheme(t) {
  if (t) ROOT.dataset.theme = t; else delete ROOT.dataset.theme;
  try { t ? localStorage.setItem("sm-theme", t) : localStorage.removeItem("sm-theme"); } catch (e) {}
  if (S) render();
}
try { const t = localStorage.getItem("sm-theme"); if (t) ROOT.dataset.theme = t; } catch (e) {}
{ const q = new URLSearchParams(location.search).get("theme"); if (q === "dark" || q === "light") ROOT.dataset.theme = q; }
if (REC && !ROOT.dataset.theme) ROOT.dataset.theme = "light";  // the site itself has no dark theme
$("theme").addEventListener("click", () => {
  const dark = ROOT.dataset.theme
    ? ROOT.dataset.theme === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches;
  setTheme(dark ? "light" : "dark");
});
$("follow").addEventListener("click", () => { manual = null; picked = false; if (REC) { try { history.replaceState(null, "", location.pathname + location.search); } catch (e) {} } tick(); });
if ($("runpick")) $("runpick").addEventListener("change", (e) => pick(e.target.value));
if ($("pickwrap")) $("pickwrap").hidden = !REC;  // the live page shows the picker only when it reads files
$("tbl").addEventListener("click", () => { showTable = !showTable; $("tbl").textContent = showTable ? "Chart" : "Table"; renderChart(); });

// ---------------------------------------------------------------- banner and header
function renderTop(run) {
  $("mode").textContent = S.mode;
  $("livedot").className = "dot" + (S.reachable && run && !finished(run) && (!REC || POLL || (RP && RP.timer)) ? " on" : "");
  const c = $("conn");
  c.textContent = POLL ? (S.reachable ? "Live on the Pi" : (S.message || "Not updating, retrying")) : REC ? (RP ? "Replay " + clock(RP.frames[RP.i][0]) : run && run.t0 ? "Recorded " + when(run.t0) : "") : S.reachable ? (S.mode === "live" ? "Pi connected" : "Playing " + S.mode) : (S.message || "Pi not reachable, retrying");
  c.className = "conn" + (S.reachable ? "" : " bad");
  $("follow").hidden = POLL ? !picked : (REC || !manual);
  const b = $("banner");
  let level = null, text = null, why = null;
  if (!S.reachable) { level = "net"; text = S.message || "Pi not reachable, retrying"; }
  else if (REC && S.note && !(RP && RP.i < RP.frames.length - 1)) {  // recorded: what the record says about this run comes first
    level = S.note.level; text = S.note.headline; why = S.note.text;
    if (run && run.banner) why = (why ? why + " " : "") + "Run ended: " + run.banner[1] + ".";
  }
  else if (run && run.banner) { level = run.banner[0]; text = run.banner[1] + (run.road ? "  (" + run.road + ")" : ""); }
  b.hidden = !text;
  if (text) {
    b.className = "banner " + level;
    b.textContent = (level === "error" ? "✕ " : level === "used" ? "✓ " : "⚠ ") + text;
    if (why) b.append(el("span", { class: "why", text: why }));
  }
}

// ---------------------------------------------------------------- hero
function renderHero(run) {
  const h = $("hero");
  h.replaceChildren();
  if (!run) { h.append(el("p", { class: "empty", text: POLL ? (S.runs && !S.runs.length ? "No run logs on the Pi since it started. A run shows here as soon as it begins." : "Waiting for the publisher on the Pi.") : REC ? "Loading the recorded runs." : "Waiting for a run. Start one with drop_job.sh, or run this server with --demo." })); return; }
  h.style.setProperty("--loco", locoVar(run.loco));
  const src = run.photo || (REC && REC.photos && REC.photos[run.loco]);
  const photo = src ? el("img", { class: "photo", src, alt: run.road || "Locomotive" }) : el("div", { class: "photo none", text: "No photo" });
  const stepPct = run.step != null ? (100 * run.step) / MAX_STEP : 0;
  const gauge = el("div", { class: "gauge", role: "img", "aria-label": `Throttle step ${run.step ?? "none"} of ${MAX_STEP}` });
  gauge.append(el("i", { style: `width:${stepPct}%` }));
  for (const s of run.steps || []) gauge.append(el("b", { style: `left:${(100 * s) / MAX_STEP}%` }));
  let status = STATUS[run.status] || run.status;
  if (run.status === "warming") status += run.warm && run.warm.secs ? ` (${run.warm.secs} s)` : "";
  if (run.status === "computing") status = `Step ${run.step} done, computing`;
  if (run.status === "settling" && run.settle_left != null) status += ` (${Math.ceil(run.settle_left)} s)`;
  if (finished(run) && run.reason) status += ": " + run.reason;
  const eta = run.eta;
  const info = el("div", {},
    el("h2", { text: run.road || "Unknown loco" }),
    el("p", { class: "model", text: [run.model, run.kind === "pass" ? "Timed pass" : run.kind === "stoptest" ? "Stop test" : run.kind !== "steprun" ? run.kind : null].filter(Boolean).join("  ·  ") }),
    el("div", { class: "chips" },
      run.stale ? el("span", { class: "chip st-stopped", text: "⚠ No updates (stale)" }) : el("span", { class: "chip st-" + run.status, text: (ICON[run.status] || "") + " " + status }),
      el("span", { class: "chip", text: (run.direction === "reverse" ? "◀ " : "▶ ") + (run.direction || "direction ?") }),
      run.route || !REC ? el("span", { class: "chip", text: "Route " + (run.route || "?") }) : null),
    el("div", { class: "stats" },
      stat("Throttle step", run.step != null ? `${run.step}` : "-", ` / ${MAX_STEP}  (${fmt(stepPct)}%)`),
      stat("Speed", fmt(run.speed, 1), "mm/s"),
      stat("Scale speed", fmt(run.speed_mph, 1), "mph HO"),
      stat("Elapsed", dur(run.elapsed), ""),
      run.pass ? stat("Pass step", String(run.pass.step), "") : run.stoptest ? stat("Test step", String(run.step ?? "-"), "") : stat(finished(run) ? "Steps done" : "Time left (rough)", finished(run) ? `${run.done_steps}` : (eta != null ? dur(eta) : "-"), finished(run) ? ` / ${(run.steps || []).length || "?"}` : "")),
    gauge,
    el("div", { class: "gauge-l" }, el("span", { text: "0" }), el("span", { text: run.pass ? "pass job" : run.stoptest ? "stop test" : `${run.done_steps} of ${(run.steps || []).length || "?"} steps measured` }), el("span", { text: String(MAX_STEP) })));
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
  if (run.stoptest) {
    const st = run.stoptest;
    $("stepsub").textContent = st.started ? `stop test at step ${st.step}, stop command when ${(st.trigger || "").replace(/^BS /, "")} lit` : "stop test";
    if (!st.started) { p.append(el("p", { class: "empty", text: "The loco never started, so there is nothing to compare." })); return; }
    const t = el("table", {});
    t.append(el("tr", {}, ...["Block lit", "Seconds after the stop command"].map((x) => el("th", { text: x }))));
    for (const r of st.rows) t.append(el("tr", {}, el("td", { text: r.sensor.replace(/^BS /, "") }), el("td", { text: fmt(r.t_rel, 2) })));
    p.append(t);
    p.append(el("p", { class: "sub", text: st.rest ? `The last block lit was ${st.rest.replace(/^BS /, "")}.` : "No block lit after the stop command." }));
    return;
  }
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
  const sig = JSON.stringify([ser, S.runs.map((r) => r.flagged), S.reference, showTable, ROOT.dataset.theme, $("chart").clientWidth]);
  if (sig === chartSig && !force) return;
  chartSig = sig;
  const ref = S.reference || {};
  const lg = $("legend");
  lg.replaceChildren();
  for (const s of ser) lg.append(el("span", {}, lineKey(locoVar(s.loco), s.dir === "reverse"), `${s.road} ${s.dir}`));
  if (Object.keys(ref).length) lg.append(el("span", {}, lineKey("var(--ink-3)", false, true), "2026-11-08 result ×1.122"));
  const fl = [];
  for (const r of S.runs) if (!REC || r.id === S.focus) for (const f of r.flagged || []) fl.push(`${r.loco} ${r.direction === "reverse" ? "rev" : "fwd"} step ${f.step} (${f.reason})`);
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
  if (REC) {  // recorded: every published run, with what the record says about it
    const t = el("table", {});
    t.append(el("tr", {}, ...["Time", "Run", "Result"].map((x) => el("th", { text: x }))));
    for (const r of INDEX) {
      const go = () => pick(r.id);
      t.append(el("tr", { class: "click" + (run && bare(S.focus) === bare(r.id) ? " sel" : ""), tabindex: 0, onclick: go, onkeydown: (e) => { if (e.key === "Enter") go(); } },
        el("td", { text: when(r.start) }), el("td", { text: runTitle(r) }), el("td", {}, r.outcome ? el("span", { class: "tag " + r.outcome, text: r.headline }) : el("span", { text: (ICON[r.status] || "") + " " + (STATUS[r.status] || r.status || "") }))));
    }
    host.append(t);
    return;
  }
  if (!S.runs.length) { host.append(el("p", { class: "empty", text: "No logs seen yet." })); return; }
  const t = el("table", {});
  t.append(el("tr", {}, ...["Loco", "Dir", "Kind", "Steps", "Status"].map((x) => el("th", { text: x }))));
  for (const r of [...S.runs].reverse()) {
    const tr = el("tr", { class: "click" + (run && r.id === run.id ? " sel" : ""), tabindex: 0, onclick: () => pick(r.id), onkeydown: (e) => { if (e.key === "Enter") pick(r.id); } },
      el("td", { text: r.road || "?" }), el("td", { text: r.direction || "-" }), el("td", { text: r.kind }),
      el("td", { text: r.pass ? "pass " + r.pass.step : `${r.done_steps}${r.steps.length ? " / " + r.steps.length : ""}` }),
      el("td", { text: r.stale ? "⚠ No updates (stale)" : (ICON[r.status] || "") + " " + (STATUS[r.status] || r.status) }));
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

function runTitle(r) {
  const what = r.kind === "pass" ? `pass, step ${r.pass_step}` : r.kind === "stoptest" ? (r.stop_step == null ? "stop test, did not start" : `stop test, step ${r.stop_step}`) : `steps, ${r.steps.length} valid`;
  return `${r.road || "?"} ${r.direction || ""}, ${what}`;
}
function render() {
  const run = focusRun();
  renderTop(run); renderHero(run); renderStrip(run); renderStep(run);
  renderChart(); renderCompare(); renderRuns(run); renderFeed(run);
}
// ---------------------------------------------------------------- recorded source
function fillPicker(cur) {
  const sel = $("runpick");
  if (!sel) return;
  const ids = INDEX.map((r) => r.id).join(" ");
  if (sel.dataset.ids !== ids) {  // the Pi page adds runs as they start
    sel.replaceChildren(...INDEX.map((r) => el("option", { value: r.id, text: `${when(r.start)}  ${runTitle(r)}${r.headline ? "  (" + r.headline.toLowerCase() + ")" : ""}` })));
    sel.dataset.ids = ids;
  }
  sel.value = cur;
}
function pick(id) {
  manual = id;
  if (!REC) { tick(); return; }  // the Mac live page: just focus the run
  picked = true;
  try { history.replaceState(null, "", "#run=" + encodeURIComponent(id)); } catch (e) {}
  tick();
}
async function tickRecorded() {
  try {
    if (!INDEX.length || POLL) {
      const r = await fetch(REC.base + "index.json", { cache: POLL ? "no-store" : "no-cache" });
      INDEX = (await r.json()).runs;  // already newest first
      if (!picked) {
        const h = /^#run=(.+)$/.exec(location.hash);
        if (h && INDEX.some((x) => x.id === decodeURIComponent(h[1]))) { manual = decodeURIComponent(h[1]); picked = true; }
      }
    }
    if (!INDEX.length) { S = { runs: [], mode: "live", reachable: true, reference: {} }; render(); return; }
    let cur = picked && INDEX.find((x) => x.id === manual);
    if (!cur) { picked = false; cur = INDEX[0]; }  // follow the newest unless a run still listed was picked
    manual = cur.id;
    if (RP && RP.id !== cur.id) { clearTimeout(RP.timer); RP = null; setReplayBar(null); }  // another run was picked
    if (RP) { render(); return; }
    const r = await fetch(REC.base + cur.file, { cache: POLL ? "no-store" : "no-cache" });
    S = BASE = await r.json();
    fillPicker(cur.id);
    setReplayBar(cur);
  } catch (e) {
    if (POLL) {  // the Pi page keeps trying
      S = S ? { ...S, reachable: false, message: "Not updating, retrying" } : { runs: [], mode: "live", reachable: false, message: "Waiting for the publisher on the Pi", reference: {} };
      render();
      return;
    }
    $("banner").hidden = false;
    $("banner").className = "banner net";
    $("banner").textContent = "The recorded runs could not be loaded. Reload the page to try again.";
    return;
  }
  render();
}
// ---------------------------------------------------------------- replay (recorded mode)
// runs/<id>.frames.json holds the run as the live page drew it, one frame per log line: the first
// a full view of the run, later ones only what changed (diff_frame in export_site_runs.py, whose
// apply_frame this repeats). Playing swaps the frames into the run's slot of the record in time
// order, sped up; long waits between lines are cut short.
const RATES = [10, 30, 100], MAX_GAP = 60;
let BASE = null, LOADING = false;  // the record of the picked run, as loaded; a replay being fetched
function applyFrame(prev, d, shown) {  // shown: how many events a frame carries (frames.json events_shown)
  const cur = { ...prev };
  for (const k of d["-"] || []) delete cur[k];
  for (const [k, v] of Object.entries(d)) {
    if (k === "blocks~") {
      const bl = cur.blocks.map((b) => ({ ...b }));
      for (const [i, ch] of Object.entries(v)) bl[+i] = "=" in ch ? { ...ch["="] } : { ...bl[+i], ...ch };
      cur.blocks = bl;
    } else if (k === "events+") cur.events = [...cur.events, ...v].slice(-shown);
    else if (k !== "-") cur[k] = v;
  }
  return cur;
}
function replayBar() {
  let bar = $("replaybar");
  if (bar || !REC || POLL) return bar;
  bar = el("div", { class: "replay", id: "replaybar" },
    el("button", { class: "btn", id: "rp-play", type: "button", onclick: () => (RP && RP.timer ? pauseReplay() : playReplay()) }, "▶ Replay"),
    el("label", { for: "rp-rate", class: "sr-only", text: "Replay speed" }),
    el("select", { id: "rp-rate", onchange: (e) => { if (RP) RP.rate = +e.target.value; } }, ...RATES.map((r) => el("option", { value: r, text: "×" + r }))),
    el("input", { type: "range", id: "rp-seek", min: 0, max: 0, value: 0, "aria-label": "Replay position", disabled: "",
      oninput: (e) => RP && seekReplay(+e.target.value) }),
    el("span", { class: "rp-t", id: "rp-t" }),
    el("button", { class: "btn small", id: "rp-end", type: "button", hidden: "", onclick: () => endReplay() }, "Show the result"));
  bar.querySelector("#rp-rate").value = "30";
  const top = ROOT.querySelector(".top");
  top.after(bar);
  return bar;
}
function setReplayBar(entry) {
  const bar = replayBar();
  if (!bar) return;
  bar.hidden = !entry || !entry.frames;
  if (!RP) {
    $("rp-play").textContent = "▶ Replay";
    $("rp-seek").disabled = true; $("rp-seek").value = 0; $("rp-t").textContent = ""; $("rp-end").hidden = true;
  }
}
function showFrame() {
  const [t, run] = RP.frames[RP.i];
  S = { ...BASE, now: t, runs: BASE.runs.map((r) => (r.id === BASE.focus ? run : r)) };
  $("rp-seek").value = RP.i;
  $("rp-t").textContent = dur(t - RP.frames[0][0]) + " / " + dur(RP.frames[RP.frames.length - 1][0] - RP.frames[0][0]);
  render();
}
async function loadReplay() {
  const entry = INDEX.find((x) => x.id === manual);
  if (!entry || !entry.frames) return false;
  const r = await fetch(REC.base + entry.frames, { cache: "no-cache" });
  const data = await r.json(), raw = data.frames;
  if (!raw.length || manual !== entry.id) return false;
  const frames = [];
  let cur = null;
  for (const [t, d] of raw) { cur = cur ? applyFrame(cur, d, data.events_shown) : d; frames.push([t, cur]); }
  RP = { id: entry.id, frames, i: 0, rate: +$("rp-rate").value, timer: null };
  $("rp-seek").max = frames.length - 1; $("rp-seek").disabled = false; $("rp-end").hidden = false;
  return true;
}
async function playReplay() {
  if (LOADING || (RP && RP.timer)) return;  // a second click while the frames load, or already playing
  try {
    LOADING = true;
    if (!RP && !(await loadReplay())) return;
  } catch (e) { $("rp-t").textContent = "The replay could not be loaded."; return; }
  finally { LOADING = false; }
  if (RP.i >= RP.frames.length - 1) RP.i = 0;
  $("rp-play").textContent = "❚❚ Pause";
  showFrame();
  const step = () => {
    if (!RP) return;
    if (RP.i >= RP.frames.length - 1) { pauseReplay(); return; }
    const gap = Math.min(RP.frames[RP.i + 1][0] - RP.frames[RP.i][0], MAX_GAP);
    RP.timer = setTimeout(() => { if (!RP) return; RP.i++; showFrame(); step(); }, Math.max(16, (1000 * gap) / RP.rate));
  };
  RP.timer = -1;  // playing; step() replaces it with the pending timeout
  step();
}
function pauseReplay() {
  if (!RP) return;
  clearTimeout(RP.timer); RP.timer = null;
  $("rp-play").textContent = RP.i >= RP.frames.length - 1 ? "↺ Replay" : "▶ Play";
  render();
}
function seekReplay(i) {
  RP.i = Math.max(0, Math.min(i, RP.frames.length - 1));
  showFrame();
}
function endReplay() {  // back to the record as published
  if (RP) clearTimeout(RP.timer);
  RP = null;
  if (BASE) S = BASE;
  setReplayBar(INDEX.find((x) => x.id === manual));
  render();
}

async function tick() {
  if (REC) return tickRecorded();
  try {
    const r = await fetch("/api/state" + (manual ? "?run=" + encodeURIComponent(manual) : ""), { cache: "no-store" });
    S = await r.json();
  } catch (e) {
    S = S ? { ...S, reachable: false, message: "Dashboard server not responding, retrying" } : { runs: [], mode: "", reachable: false, message: "Dashboard server not responding, retrying", reference: {} };
  }
  render();
}
let rz;
addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => S && renderChart(), 150); });
tick();
if (!REC) setInterval(tick, 1000);
else if (POLL) setInterval(tick, POLL);
