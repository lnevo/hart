#!/usr/bin/env node
/* Builds www/exam/answers.html, the answer key for the Extra East game, from the ask({...}) calls in www/exam/run.js.
   Each call is evaluated with every unknown name stubbed, so values the game fills in at play time (station, train,
   clock time) show as [station], [train] or […]. `--check` exits 1 when answers.html is out of date. */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
/* The section and source names, and the source labels, the game shows (js/game-engine.js). */
const ENGINE = require(path.join(__dirname, "..", "js", "game-engine.js"));

const EXAM = path.join(__dirname, "..", "exam");
/* The game's scripts in the order run.html loads them; the key reads them as one text. */
const RUN_FILES = ["run.js", "run-1949.js", "run-modern.js", "run-signals.js", "run-yard.js"].map(f => path.join(EXAM, f));
const readRun = () => RUN_FILES.map(f => fs.readFileSync(f, "utf8")).join("\n");
const OUT = path.join(EXAM, "answers.html");

/* Scans from the bracket at `open` to the one that closes it. Skips strings, comments and template text, and follows
   ${...} inside templates, nested to any depth. Returns the closing index and the code outside strings and comments.
   Regex literals are not followed; an ask({...}) holding one stops the build with an unbalanced-bracket error. */
function scan(src, open) {
  const pair = { "{": "}", "[": "]", "(": ")" };
  const stack = []; // closers; "T" closes a ${...} and returns to template text
  let mode = "code";
  let code = "";
  for (let j = open; j < src.length; j++) {
    const c = src[j];
    const two = src.slice(j, j + 2);
    if (mode === '"' || mode === "'") {
      if (c === "\\") j++;
      else if (c === mode) mode = "code";
      continue;
    }
    if (mode === "`") {
      if (c === "\\") j++;
      else if (c === "`") mode = "code";
      else if (two === "${") { stack.push("T"); mode = "code"; j++; }
      continue;
    }
    if (mode === "//") { if (c === "\n") mode = "code"; continue; }
    if (mode === "/*") { if (two === "*/") { mode = "code"; j++; } continue; }
    if (two === "//" || two === "/*") { mode = two; j++; continue; }
    if (c === '"' || c === "'" || c === "`") { mode = c; continue; }
    code += c;
    if (pair[c]) stack.push(pair[c]);
    else if (c === "}" || c === "]" || c === ")") {
      const want = stack.pop();
      if (want === "T" && c === "}") { mode = "`"; continue; }
      if (want !== c) throw new Error(`run.js line ${src.slice(0, j).split("\n").length}: unbalanced ${c}`);
      if (!stack.length) return { end: j, code };
    }
  }
  throw new Error(`run.js line ${src.slice(0, open).split("\n").length}: no closing bracket`);
}
const closing = (src, open) => scan(src, open).end;

/* The one way this script evaluates code from run.js: the text from `from` through the bracket that closes `open`. */
const evalSlice = (src, from, open) => Function(`return (${src.slice(from, closing(src, open) + 1)})`)();

/* The value of a declaration such as "const STATIONS=" (an object or array literal), searched for from `after`. */
function literal(src, decl, after = 0) {
  const at = src.indexOf(decl, after);
  if (at < 0) throw new Error(`run.js: ${decl.trim()} not found`);
  const open = at + decl.length;
  if (!"{[".includes(src[open])) throw new Error(`run.js: ${decl.trim()} is not followed by a literal`);
  return evalSlice(src, open, open);
}

/* A stand-in for any name the game defines at play time; prints as [name]. */
function stub(name) {
  return new Proxy(function () {}, {
    get: (t, k) => (k === Symbol.toPrimitive ? () => `[${name}]` : stub(`${name}.${String(k)}`)),
    apply: () => `[${name}(…)]`,
  });
}
/* Helpers the key runs for real, read from run.js: the figures a question may show under its text. */
const FIGURES = ["semSvg"];
function figures(src) {
  const out = {};
  for (const name of FIGURES) {
    const at = src.indexOf(`function ${name}(`);
    if (at < 0) throw new Error(`run.js: figure helper ${name} not found`);
    out[name] = evalSlice(src, at, src.indexOf("{", at));
  }
  return out;
}
const scopeWith = real => new Proxy({}, {
  has: (t, k) => typeof k === "string" && !(k in globalThis),
  get: (t, k) => (k === Symbol.unscopables ? undefined : k in real ? real[k] : stub(String(k))),
});

const FRIENDLY = [
  [/\[STATIONS\.\[?\w+\]?\.n\]/g, "[station]"],
  [/\[(?:p|time|o|f)\.tr\.name\]/g, "[train]"],
  [/\[(?:shown|nums)\.join\(…\)\]/g, "[order numbers]"],
  [/\[time\.no\]/g, "[order no]"],
  [/\[esc\(…\)\]/g, "[order text]"],
  [/\[fmt\(…\)\]/g, "[time]"],
  [/NaN|\[time\.L\]/g, "[n]"],
  // Any other stub: it has a dot or a call in it, which the friendly names above do not.
  [/\[\w+(?:\.[\w\[\]]+)*(?:\(…\))?\]/g, m => (/[.(]/.test(m) ? "[…]" : m)],
];
const friendly = s => FRIENDLY.reduce((t, [re, to]) => t.replace(re, to), String(s));
const { esc, srcLabel } = ENGINE;
const text = v => (v == null ? "" : friendly(v));
const ENT = { "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&nbsp;": " " };
const plain = s => s.replace(/<[^>]+>/g, " ").replace(/&(?:amp|lt|gt|quot|#39|nbsp);/g, e => ENT[e]).replace(/\s+/g, " ");

/* Where in the game a question is asked: inside one of the event pools, or fixed in a scene. */
const POOLS = { ROAD_TTO: "1949 run, on the road", STN_TTO: "1949 run, at a station", ROAD_TWC: "Modern run, on the road" };
function poolRanges(src) {
  const out = [];
  for (const name of Object.keys(POOLS)) {
    const at = src.indexOf(`const ${name}=[`);
    if (at < 0) throw new Error(`run.js: pool ${name} not found`);
    const open = src.indexOf("[", at);
    out.push({ name, from: open, to: closing(src, open) });
  }
  return out;
}

/* Fields the key shows. Others (ok, okText, note, after, miss) only matter during a run. */
const SHOWN = ["sec", "src", "title", "body", "right", "wrong", "why", "extra", "ref"];

/* The code of one top-level field of an object literal, from scan()'s string-free code. */
function fieldCode(code, key) {
  let depth = 0, from = 1;
  const parts = [];
  for (let i = 0; i < code.length; i++) {
    const c = code[i];
    if ("{[(".includes(c)) depth++;
    else if ("}])".includes(c)) depth--;
    if ((c === "," && depth === 1) || i === code.length - 1) { parts.push(code.slice(from, i)); from = i + 1; }
  }
  const hit = parts.find(p => new RegExp(`^\\s*${key}\\s*:`).test(p));
  return hit ? hit.replace(/^\s*\w+\s*:/, "") : "";
}


/* The modern run's code starts at its warrant tables in run-modern.js. Everything after it in readRun()'s text is
   modern, but for the runs in FUNC_RUNS, which are checked first; any other question before TW_SEL is 1949. */
function modernRange(src) {
  const from = src.indexOf("const TW_SEL=");
  if (from < 0) throw new Error("run-modern.js: const TW_SEL not found");
  return { from, to: src.length };
}

/* Runs whose questions all sit inside one start function: the yard job. */
const FUNC_RUNS = { startYARD: "Yard job", startSIG: "Signals run" };
function funcRanges(src) {
  return Object.entries(FUNC_RUNS).map(([fn, label]) => {
    const at = src.indexOf(`function ${fn}(`);
    if (at < 0) throw new Error(`run.js: function ${fn} not found`);
    return { label, from: at, to: closing(src, src.indexOf("{", at)) };
  });
}

function extract(src) {
  const pools = poolRanges(src);
  const modern = modernRange(src);
  const runs = funcRanges(src);
  const scope = scopeWith(figures(src));
  const qs = [];
  let generated = 0;
  const re = /\bask\(\{/g;
  let m;
  while ((m = re.exec(src))) {
    const open = m.index + 4;
    const line = src.slice(0, m.index).split("\n").length;
    const { end, code } = scan(src, open);
    // A question drawn at a signal (gen:"speed", "route" or "plate") is built at play time from signals.js; the key lists
    // those from the tables (generatedHtml) instead of reading the call.
    if (/[{,]\s*gen\s*:/.test(code)) { generated++; continue; } // its value is a string, which scan() leaves out of code
    // Stubs are always truthy, so a shown field chosen at play time would show one branch as the only answer.
    const chosen = SHOWN.filter(k => /\?|&&|\|\|/.test(fieldCode(code, k)));
    if (chosen.length) throw new Error(`run.js line ${line}: ${chosen.join(", ")} chosen at play time (?, && or ||); write one ask per case, or put a situational sentence in note`);
    const lit = src.slice(open, end + 1);
    let o;
    try {
      o = Function("P", `with(P){return (${lit})}`)(scope);
    } catch (e) {
      throw new Error(`run.js line ${line}: cannot read question (${e.message})`);
    }
    if (o.extra && /\[\w/.test(String(o.extra))) throw new Error(`run.js line ${line}: the figure under the question uses play-time values the key cannot draw`);
    for (const k of ["title", "body", "right", "why"]) if (!o[k]) throw new Error(`run.js line ${line}: question has no ${k}`);
    if (!Array.isArray(o.wrong) || !o.wrong.length) throw new Error(`run.js line ${line}: question has no wrong answers`);
    const pool = pools.find(p => m.index > p.from && m.index < p.to);
    qs.push({
      line, sec: o.sec, src: text(srcLabel(String(o.src || ""))), extra: o.extra ? String(o.extra) : "", title: text(o.title), body: text(o.body), right: text(o.right),
      wrong: o.wrong.map(w => ({ t: text(w[0]), why: text(w[2] || "") })),
      ref: o.ref ? String(o.ref) : "", why: text(o.why), where: pool ? POOLS[pool.name] : (runs.find(r => m.index > r.from && m.index < r.to) || {}).label || (m.index > modern.from && m.index < modern.to ? "Modern run" : "1949 run"),
    });
  }
  qs.generated = generated;
  return qs;
}

/* signals.js, the tables the signals runs draw from (shared with the study deck), loaded in a sandbox. */
function loadSignals() {
  const file = path.join(EXAM, "signals.js");
  const ctx = {};
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(file, "utf8") + ";this.SIG={ASPECTS,ROUTE,PLATES,sigFig,lightFig,armWords,lampWords,plateWrongs,routeWhy};", ctx);
  const SIG = ctx.SIG;
  if (!SIG.ASPECTS.length || !SIG.ROUTE.length || !Object.keys(SIG.PLATES).length) throw new Error("signals.js: a table is empty");
  return SIG;
}

/* The questions the signals runs draw at each signal: every speed aspect, route indication and plate, with the
   choices the game can offer. */
function generatedHtml(SIG) {
  const byR = Object.fromEntries(SIG.ASPECTS.map(a => [a.r, a]));
  const card = (meta, title, body, fig, right, wrongs, why) => {
    const opts = [{ t: right, ok: true }, ...wrongs.map(t => ({ t }))].sort((a, b) => a.t.localeCompare(b.t));
    const search = plain([title, body, right, why, meta, ...wrongs].join(" ")).toLowerCase();
    return `<article class="xa-q" data-s="${esc(search)}">
  <p class="xa-meta">${esc(meta)}</p>
  <h3>${esc(title)}</h3>
  <p>${esc(body)}</p>
  <div class="xa-fig">${fig}</div>
  <ul class="xa-opts">${opts.map(o => `<li${o.ok ? ' class="ok"' : ""}>${esc(o.t)}</li>`).join("")}</ul>
  <p class="xa-why">${esc(why)}</p>
</article>`;
  };
  const speed = SIG.ASPECTS.map(a => card(`Speed signals · 1949 Standard Code · Rule ${a.r}`, `Rule ${a.r}`, `Arms top to bottom: ${SIG.armWords(a.arms)}. What does it indicate?`,
    SIG.sigFig(a.arms), a.ind, a.w.map(r => byR[r].ind), `Rule ${a.r}, ${a.name}: ${a.ind}.`));
  const inds = [...new Set(SIG.ROUTE.map(r => r.ind))];
  const route = SIG.ROUTE.filter((r, i, all) => all.findIndex(x => x.heads === r.heads) === i).map(r => card(`Route signals · Signals guide · chart`, r.name,
    `${SIG.lampWords(r.heads)}. What does it tell you?`, SIG.lightFig(r.heads, ""), r.ind, inds.filter(t => t !== r.ind), SIG.routeWhy(r)));
  // the plates the game draws (it never draws a signal with no plate)
  const plates = Object.entries(SIG.PLATES).filter(([k]) => k !== "none").map(([k, p]) => card(`Both signals runs · Signals guide · signage`, `${p.name} at Stop`,
    `The signal shows Stop and carries ${p.with}. What do you do?`, SIG.lightFig("R", k), p.act, SIG.plateWrongs(k).map(w => w.t), p.note));
  const n = speed.length + route.length + plates.length;
  return { n, html: `<section class="xa-sec" id="signals"><h2>Signals run: at each signal <small>${n}</small></h2>
<p class="xa-gen">On the signals runs each signal is drawn from these tables, which the study deck also uses. The game offers three of the wrong choices listed for a route signal or a plate.</p>
<h3 class="xa-sub">Speed semaphores (1949)</h3>
${speed.join("\n")}
<h3 class="xa-sub">Route signals (modern)</h3>
${route.join("\n")}
<h3 class="xa-sub">At a Stop: the plates</h3>
${plates.join("\n")}
</section>` };
}

/* ---------- references: what the game shows on its train sheet or warrant form, for questions that need it ---------- */
/* A question names one with ref:"<id>" in run.js; the game ignores the field. Each is drawn from run.js's own data. */


/* The special instructions on the 1949 train sheet: renderSheet's state.era==="tto" branch, up to its }else{. */
function specialInstructions(src) {
  const from = src.indexOf('if(state.era==="tto"){', src.indexOf("function renderSheet("));
  const to = src.indexOf("}else{", from);
  if (from < 0 || to < 0) throw new Error('run.js: renderSheet\'s state.era==="tto" branch not found');
  const branch = src.slice(from, to).replace(/`\+\n\s*`/g, ""); // run.js wraps a long template as `…`+`…`
  const m = /<div class="xw-si"><b>Special instructions<\/b><ul>(.*?)<\/ul><\/div>/.exec(branch);
  if (!m) throw new Error("run.js: special instructions not found in the 1949 branch of renderSheet");
  return m[1];
}

/* A warrant as the game fills it. Starts from the `const wN={…}` literal in startTWC, then applies every later
   `wN.boxes[n]=[…]` there: a value set at play time (not a literal) shows as its slot, such as [time], and a box set
   under if/else is marked as appearing in some runs only. */
function warrant(src, name) {
  const from = src.indexOf("function startTWC(");
  if (from < 0) throw new Error("run.js: function startTWC not found");
  const body = src.slice(from, closing(src, src.indexOf("{", from)) + 1);
  const w = literal(body, `const ${name}=`);
  if (!w.no || !w.boxes) throw new Error(`run.js: ${name} in startTWC has no no or boxes`);
  const boxes = Object.fromEntries(Object.entries(w.boxes).map(([n, v]) => [n, { vals: v, some: false }]));
  const re = new RegExp(`\\b${name}\\.boxes\\[(\\d+)\\]=`, "g");
  let m;
  while ((m = re.exec(body))) {
    const open = m.index + m[0].length;
    if (body[open] !== "[") throw new Error(`run.js: ${name}.boxes[${m[1]}] is not set to an array`);
    let vals;
    try { vals = evalSlice(body, open, open); } catch (e) { vals = null; } // built at play time, e.g. [fmt(t)]
    const lineStart = body.lastIndexOf("\n", m.index) + 1;
    const some = /^\s*(if\s*\(|else\b|}\s*else\b)/.test(body.slice(lineStart, m.index));
    boxes[m[1]] = { vals, some };
  }
  return { no: w.no, at: w.at, boxes };
}

function warrantHtml(w, BOXES) {
  const words = Object.fromEntries(BOXES);
  const rows = Object.keys(w.boxes).map(Number).sort((a, b) => a - b).map(n => {
    if (!words[n]) throw new Error(`run.js: warrant ${w.no} uses box ${n}, which BOXES does not define`);
    const { vals, some } = w.boxes[n];
    const slots = words[n].match(/\{\w+\}/g) || [];
    if (vals && vals.length !== slots.length) throw new Error(`run.js: warrant ${w.no} box ${n} has ${vals.length} values for ${slots.length} blanks`);
    let i = 0;
    const line = words[n].replace(/\{(\w+)\}/g, (_, slot) => vals ? `<b>${esc(vals[i++])}</b>` : `<b>[${SLOT[slot] || slot}]</b>`);
    return `<tr><td class="xa-box">${n}</td><td>${line}${some ? ' <small class="xa-some">some runs</small>' : ""}</td></tr>`;
  });
  return `<p class="xa-wh">Track warrant no. <b>${esc(w.no)}</b> · copied at ${esc(w.at)} · to KV 812 East</p><table class="xa-w">${rows.join("")}</table>`;
}
const SLOT = { s: "station", t: "track", time: "time", train: "train", w: "warrant", mph: "mph", txt: "instructions" };

/* The time order the game writes at an open office, filled with the first of each choice it makes. */
function timeOrder(src) {
  const nums = /const n1=rnd\((\d+),(\d+),randOrders\)/.exec(src);
  const mins = /L=pick\(\[([\d,\s]+)\],randOrders\)/.exec(src);
  const words = /text:`\$\{tr\.name\} run \$\{L\} mins late ([^`]+)`/.exec(src);
  const tt = src.slice(src.indexOf("function makeTT("));
  const train = /name:"([^"]+)",dir:"W",cls:"(?:First|Second) class"/.exec(tt);
  if (!nums || !mins || !words || !train) throw new Error("run.js: the time order's number, minutes, wording or westward train not found");
  return { no: nums[1], train: train[1], L: mins[1].split(",")[0].trim(), rest: words[1] };
}

/* How far ahead Box 5 is set when the crew calls the dispatcher (setBox5: rounded up to 5 minutes). */
function box5Lead(src) {
  const m = /Math\.ceil\(\(state\.clock\+(\d+)\)\/5\)\*5/.exec(src);
  if (!m) throw new Error("run.js: setBox5's lead time not found");
  return +m[1];
}

function references(src) {
  const ST = literal(src, "const STATIONS=");
  const BOXES = literal(src, "const BOXES=");
  const stations = `<table class="xa-tt"><thead><tr><th>Station</th><th>MP</th><th>Siding</th><th>Notes</th></tr></thead><tbody>${ST.map(st =>
    `<tr><td>${esc(st.n)}</td><td>${st.mp.toFixed(1)}</td><td>${st.sd ? "yes" : "no"}</td><td>${[st.off ? "open office (D)" : "", st.yl ? "yard limits" : ""].filter(Boolean).join(", ")}</td></tr>`).join("")}</tbody></table>`;
  const ord = timeOrder(src);
  const lead = box5Lead(src);
  const w1 = warrant(src, "w1"), w2 = warrant(src, "w2");
  const some = "Rows marked <i>some runs</i> are on the warrant in only some runs.";
  return {
    tt: {
      label: "Show the time-table",
      title: "Time-table No 12, Kestrel Valley Second Subdivision",
      html: `<p>Ashby to Ironton: single track, with double track from Hollis to Ironton. The train columns change from run to run, so they are left out here.</p>${stations}<p><b>Special instructions</b></p><ul>${specialInstructions(src)}</ul>`,
    },
    order: {
      label: "Show the order",
      title: "The time order",
      html: `<p>At an open office the operator hands up a time order (Form E) on a westward regular train, for example:</p>
<div class="xa-order"><b>Order No ${esc(ord.no)}</b><br>${esc(ord.train)} run ${esc(ord.L)} mins late ${esc(ord.rest)}</div>
<p>In the question, [train] is the train the order names and [n] its minutes: here ${esc(ord.train)} and ${esc(ord.L)}.</p>`,
    },
    w101: {
      label: "Show warrant 101",
      title: "Track warrant 101",
      html: `${warrantHtml(w1, BOXES)}<p>When you call for the warrant, the dispatcher sets Box 5 to the first 5-minute mark at least ${lead} minutes later. The question's two [time] values are that Box 5 time and the clock when you are ready to leave. ${some}</p>`,
    },
    w102: {
      label: "Show warrant 102",
      title: "Track warrant 102",
      html: `${warrantHtml(w2, BOXES)}<p>${some}</p>`,
    },
  };
}

function render(qs, SEC, REFS = {}, GEN = { n: 0, html: "" }) {
  const order = Object.keys(SEC);
  const badRef = qs.find(q => q.ref && !REFS[q.ref]);
  if (badRef) throw new Error(`run.js line ${badRef.line}: unknown reference "${badRef.ref}" (known: ${Object.keys(REFS).join(", ")})`);
  const unknown = qs.filter(q => !order.includes(q.sec));
  if (unknown.length) throw new Error(`run.js line ${unknown[0].line}: unknown section "${unknown[0].sec}"`);
  let n = 0;
  const groups = order.map(sec => {
    const list = qs.filter(q => q.sec === sec);
    if (!list.length) return "";
    const cards = list.map(q => {
      n++;
      const search = plain([q.title, q.body, q.right, q.src, q.why, ...q.wrong.flatMap(w => [w.t, w.why]), q.ref ? REFS[q.ref].html : ""].join(" ")).toLowerCase();
      // Alphabetical, so the right answer is not always first when answers are hidden.
      const opts = [{ t: q.right, ok: true }, ...q.wrong].sort((a, b) => a.t.localeCompare(b.t));
      return `<article class="xa-q" data-s="${esc(search)}">
  <p class="xa-meta">${n} · ${esc(q.where)} · ${esc(q.src)}</p>
  <h3>${esc(q.title)}</h3>
  <p>${q.body}</p>${q.extra ? `\n  <div class="xa-fig">${q.extra}</div>` : ""}${q.ref ? `\n  <p><button type="button" class="xa-ref" data-ref="${q.ref}" aria-haspopup="dialog">${esc(REFS[q.ref].label)}</button></p>` : ""}
  <ul class="xa-opts">${opts.map(o => `<li${o.ok ? ' class="ok"' : ""}>${esc(o.t)}${o.why ? ` <span class="xa-ow">${o.why}</span>` : ""}</li>`).join("")}</ul>
  <p class="xa-why">${q.why}</p>
</article>`;
    }).join("\n");
    return `<section class="xa-sec" id="${sec}"><h2>${esc(SEC[sec])} <small>${list.length}</small></h2>\n${cards}\n</section>`;
  }).join("\n");
  const toc = order.filter(s => qs.some(q => q.sec === s)).map(s => `<a href="#${s}">${esc(SEC[s])}</a>`).join(" · ") + (GEN.n ? ` · <a href="#signals">Signals run: at each signal</a>` : "");
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Extra East answer key — HART</title>
  <meta name="description" content="Every question in the Extra East game with its answer, the wrong choices and the rule behind it.">
  <link rel="stylesheet" href="../css/ops.css">
  <link rel="stylesheet" href="../css/achievements.css">
  <!-- Generated by www/scripts/build_exam_answers.js from run.js. Do not edit by hand. -->
  <style>
.xa-tools{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;position:sticky;top:var(--header-h,0px);background:var(--paper);padding:8px 0;z-index:2}
.xa-tools input[type=search]{flex:1 1 240px;font:inherit;padding:8px 10px;border:1px solid #b9b4a6;border-radius:4px}
.xa-toc{font-size:14px;line-height:1.8}
.xa-q{border:1px solid #d6d0c0;border-radius:6px;padding:10px 14px;margin:10px 0}
.xa-q h3{margin:2px 0 6px}
.xa-meta{margin:0;font-size:12px;color:#5d5a4e;font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
.xa-opts{margin:6px 0;padding-left:22px}
.xa-opts li{margin:2px 0}
.xa-fig{margin:4px 0;color:#1d2733}
.xa-sub{font-size:17px;margin:14px 0 4px}
.xa-gen{color:#5d5a4e;font-size:14px}
.xa-ref{font:inherit;font-size:14px;padding:5px 12px;border:1.5px solid #1d2733;border-radius:4px;background:#f5f0e1;color:#1d2733;cursor:pointer}
.xa-ref:hover{background:#ece4cc}
.xa-dlg{max-width:min(640px,calc(100vw - 32px));width:100%;border:1.5px solid #1d2733;border-radius:6px;padding:14px 18px;background:#f5f0e1;color:#1d2733}
.xa-dlg::backdrop{background:rgba(29,39,51,.45)}
.xa-dlg-head{display:flex;justify-content:space-between;align-items:start;gap:12px}
.xa-dlg h2{margin:0 0 8px;font-size:20px}
.xa-close{font:inherit;font-size:22px;line-height:1;border:0;background:none;cursor:pointer;color:#1d2733;padding:0 4px}
.xa-dlg table{border-collapse:collapse;width:100%;font-size:14px;margin:6px 0}
.xa-dlg td,.xa-dlg th{border-bottom:1px solid #cdbf9c;padding:4px 6px;text-align:left;vertical-align:top}
.xa-dlg ul{padding-left:20px;font-size:15px}
.xa-some{font-size:12px;color:#5d5a4e;font-style:italic}
.xa-box{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;width:2.5em}
.xa-wh{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-size:13px}
.xa-order{background:#f3ecbf;border:1px solid #cdbf9c;padding:8px 12px;font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-size:14px;margin:6px 0}
.xa-opts li.ok{font-weight:600;color:#2d6a4f;list-style:"✓  "}
.xa-ow,.xa-why{color:#5d5a4e;font-size:14px}
.xa-sec h2 small{font-weight:400;color:#5d5a4e}
body.xa-hide .xa-opts li.ok{font-weight:inherit;color:inherit;list-style:disc}
body.xa-hide .xa-why,body.xa-hide .xa-ow{display:none}
  </style>
</head>
<body>
  <header class="site-header" data-ops-header></header>
  <main class="ap-wrap">
    <div class="page-head">
      <nav class="crumb" aria-label="Breadcrumb"><ol><li><a href="../ap/opsig.html#ce">OPSIG Achievement Program</a></li><li><a href="index.html">Conductor &amp; Engineer Exam Study Deck</a></li></ol></nav>
      <h1>Extra East answer key</h1>
      <p class="section-note">All ${n} questions in <a href="run.html">Extra East</a>, grouped by the study deck's sections. Each shows its choices in alphabetical order with the right one ticked, and the rule behind it.
        Names, numbers and times the game fills in during a run show in brackets, such as [station] or [time].</p>
    </div>
    <div class="xa-tools">
      <input type="search" id="xaFilter" placeholder="Filter by rule, word or answer" aria-label="Filter questions">
      <label><input type="checkbox" id="xaHide"> Hide answers</label>
    </div>
    <p class="xa-toc">${toc}</p>
${groups}
${GEN.html}
${Object.entries(REFS).map(([id, r]) => `<dialog class="xa-dlg" id="ref-${id}" aria-labelledby="ref-${id}-h">
  <div class="xa-dlg-head"><h2 id="ref-${id}-h">${esc(r.title)}</h2><button type="button" class="xa-close" aria-label="Close">×</button></div>
  ${r.html}
</dialog>`).join("\n")}
  </main>
  <footer class="site-footer" data-ops-footer></footer>
  <script src="../js/nav.js"></script>
  <script>
  (function(){
    var f=document.getElementById("xaFilter"),h=document.getElementById("xaHide");
    f.addEventListener("input",function(){var v=f.value.trim().toLowerCase();
      document.querySelectorAll(".xa-q").forEach(function(a){a.hidden=!!v&&a.dataset.s.indexOf(v)<0});
      document.querySelectorAll(".xa-sec").forEach(function(s){s.hidden=!s.querySelector(".xa-q:not([hidden])")});});
    h.addEventListener("change",function(){document.body.classList.toggle("xa-hide",h.checked)});
    document.querySelectorAll(".xa-ref").forEach(function(b){b.addEventListener("click",function(){
      var d=document.getElementById("ref-"+b.dataset.ref);if(!d)return;
      if(d.showModal)d.showModal();else{d.setAttribute("open","");d.scrollIntoView();}})}); // no <dialog> support: show it in place
    document.querySelectorAll(".xa-dlg").forEach(function(d){
      d.querySelector(".xa-close").addEventListener("click",function(){if(d.close)d.close();else d.removeAttribute("open");});
      d.addEventListener("click",function(e){var r=d.getBoundingClientRect(); // a click on the backdrop, outside the box, closes it
        if(e.target===d&&(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom))d.close();});});
  })();
  document.addEventListener("DOMContentLoaded", function () { HARTOps.mountChrome("ap-exam").catch(function (err) { console.error(err); }); });
  </script>
</body>
</html>
`;
}

function main() {
  const src = readRun();
  const qs = extract(src);
  const calls = (src.match(/\bask\(\{/g) || []).length;
  if (qs.length + qs.generated !== calls) throw new Error(`read ${qs.length} questions and ${qs.generated} signal templates but run.js has ${calls} ask({ calls`);
  const GEN = qs.generated ? generatedHtml(loadSignals()) : { n: 0, html: "" };
  const html = render(qs, ENGINE.DECK_SECTIONS, references(src), GEN);
  if (process.argv.includes("--check")) {
    const cur = fs.existsSync(OUT) ? fs.readFileSync(OUT, "utf8") : "";
    if (cur !== html) {
      console.error("www/exam/answers.html is out of date: run node www/scripts/build_exam_answers.js");
      process.exit(1);
    }
    console.log(`answers.html up to date (${qs.length} questions)`);
    return;
  }
  fs.writeFileSync(OUT, html);
  console.log(`wrote ${path.relative(process.cwd(), OUT)} (${qs.length} questions)`);
}

if (require.main === module) {
  try { main(); } catch (e) { console.error(`build_exam_answers: ${e.message}`); process.exit(1); }
}
module.exports = { readRun, extract, render, references, warrantHtml, loadSignals, generatedHtml };
