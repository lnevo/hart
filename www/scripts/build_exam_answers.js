#!/usr/bin/env node
/* Builds www/exam/answers.html, the answer key for the Extra East game, from the ask({...}) calls in the game's scripts
   (www/exam/run.js and the run files). Each call is evaluated with every unknown name stubbed, so values the game fills
   in at play time (station, train, clock time) show as [station], [train] or […]. The reference panels come from the
   game's data literals (STATIONS, REGULARS, TIME_ORDER, TWC_PLAN) and the track warrant form (js/track-warrant.js).
   `--check` exits 1 when answers.html is out of date. */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
/* The section and source names, and the source labels, the game shows (js/game-engine.js). */
const ENGINE = require(path.join(__dirname, "..", "js", "game-engine.js"));

const EXAM = path.join(__dirname, "..", "exam");
/* The game's scripts in run.html's order, each with the run its questions belong to. A question in one of the event
   pools (POOLS) takes the pool's place instead. */
const RUN_FILES = { "run.js": "1949 run", "run-1949.js": "1949 run", "run-modern.js": "Modern run", "run-signals.js": "Signals run", "run-yard.js": "Yard job" };
/* The scripts as [{file, where, src}]. */
const readRun = () => Object.entries(RUN_FILES).map(([file, where]) => ({ file, where, src: fs.readFileSync(path.join(EXAM, file), "utf8") }));
const OUT = path.join(EXAM, "answers.html");
const TRACK_WARRANT = path.join(EXAM, "..", "js", "track-warrant.js");

/* The script named `file` among those read. */
function fileOf(files, file) {
  const f = files.find(x => x.file === file);
  if (!f) throw new Error(`${file} is not among the game's scripts`);
  return f;
}
/* "run-modern.js line 12": where index `at` falls in a script. */
const lineOf = (f, at) => `${f.file} line ${f.src.slice(0, at).split("\n").length}`;

/* Scans from the bracket at `open` to the one that closes it. Skips strings, comments and template text, and follows
   ${...} inside templates, nested to any depth. Returns the closing index and the code outside strings and comments.
   Regex literals are not followed; an ask({...}) holding one stops the build with an unbalanced-bracket error.
   f is the script, {file, src}. */
function scan(f, open) {
  const src = f.src;
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
      if (want !== c) throw new Error(`${lineOf(f, j)}: unbalanced ${c}`);
      if (!stack.length) return { end: j, code };
    }
  }
  throw new Error(`${lineOf(f, open)}: no closing bracket`);
}
const closing = (f, open) => scan(f, open).end;

/* The one way this script evaluates the game's code: the text from `from` through the bracket that closes `open`. */
const evalSlice = (f, from, open) => Function(`return (${f.src.slice(from, closing(f, open) + 1)})`)();

/* The value of a declaration such as "const STATIONS=" (an object or array literal) in script f. There must be one. */
function literal(f, decl) {
  const at = f.src.indexOf(decl);
  if (at < 0) throw new Error(`${f.file}: ${decl.trim()} not found`);
  if (f.src.indexOf(decl, at + 1) >= 0) throw new Error(`${f.file}: ${decl.trim()} is declared twice`);
  const open = at + decl.length;
  if (!"{[".includes(f.src[open])) throw new Error(`${f.file}: ${decl.trim()} is not followed by a literal`);
  return evalSlice(f, open, open);
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
function figures(files) {
  const f = fileOf(files, "run.js");
  const out = {};
  for (const name of FIGURES) {
    const at = f.src.indexOf(`function ${name}(`);
    if (at < 0) throw new Error(`run.js: figure helper ${name} not found`);
    out[name] = evalSlice(f, at, f.src.indexOf("{", at));
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
/* Each pool's script and the span of its array there; each pool is declared in exactly one script. */
function poolRanges(files) {
  return Object.keys(POOLS).map(name => {
    const decl = `const ${name}=[`;
    const hits = files.filter(f => f.src.includes(decl));
    if (hits.length !== 1) throw new Error(`pool ${name} is declared in ${hits.length} scripts, not one`);
    const f = hits[0];
    const open = f.src.indexOf(decl) + decl.length - 1;
    return { name, file: f.file, from: open, to: closing(f, open) };
  });
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


/* The ask({...}) calls in script f, as [{at, end, code}]: the call's index, its closing brace and its code outside
   strings and comments. */
function asks(f) {
  const out = [];
  const re = /\bask\(\{/g;
  let m;
  while ((m = re.exec(f.src))) {
    const open = m.index + 4;
    out.push({ at: m.index, open, ...scan(f, open) });
  }
  return out;
}

/* One question as the key shows it, from the call at `call` in script f; the scope stubs every play-time name. */
function question(f, call, scope, where) {
  const at = lineOf(f, call.at);
  // Stubs are always truthy, so a shown field chosen at play time would show one branch as the only answer.
  const chosen = SHOWN.filter(k => /\?|&&|\|\|/.test(fieldCode(call.code, k)));
  if (chosen.length) throw new Error(`${at}: ${chosen.join(", ")} chosen at play time (?, && or ||); write one ask per case, or put a situational sentence in note`);
  let o;
  try {
    o = Function("P", `with(P){return (${f.src.slice(call.open, call.end + 1)})}`)(scope);
  } catch (e) {
    throw new Error(`${at}: cannot read question (${e.message})`, { cause: e });
  }
  if (o.extra && /\[\w/.test(String(o.extra))) throw new Error(`${at}: the figure under the question uses play-time values the key cannot draw`);
  for (const k of ["title", "body", "right", "why"]) if (!o[k]) throw new Error(`${at}: question has no ${k}`);
  if (!Array.isArray(o.wrong) || !o.wrong.length) throw new Error(`${at}: question has no wrong answers`);
  return {
    file: f.file, line: f.src.slice(0, call.at).split("\n").length, sec: o.sec, src: text(srcLabel(String(o.src || ""))),
    extra: o.extra ? String(o.extra) : "", title: text(o.title), body: text(o.body), right: text(o.right),
    wrong: o.wrong.map(w => ({ t: text(w[0]), why: text(w[2] || "") })),
    ref: o.ref ? String(o.ref) : "", why: text(o.why), where,
  };
}

/* Every question in the scripts (readRun()'s list), in order. qs.generated counts the calls drawn at a signal, which
   the key lists from signals.js instead (generatedHtml). */
function extract(files) {
  const pools = poolRanges(files);
  const scope = scopeWith(figures(files));
  const qs = [];
  let generated = 0;
  for (const f of files) {
    if (!f.where) throw new Error(`${f.file}: no run named for its questions`);
    for (const call of asks(f)) {
      // gen:"speed", "route" or "plate": its value is a string, which scan() leaves out of code
      if (/[{,]\s*gen\s*:/.test(call.code)) { generated++; continue; }
      const pool = pools.find(p => p.file === f.file && call.at > p.from && call.at < p.to);
      qs.push(question(f, call, scope, pool ? POOLS[pool.name] : f.where));
    }
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
  const sheet = src.indexOf("function renderSheet(");
  if (sheet < 0) throw new Error("run.js: function renderSheet not found");
  const from = src.indexOf('if(state.era==="tto"){', sheet);
  const to = src.indexOf("}else{", from);
  if (from < 0 || to < 0) throw new Error('run.js: renderSheet\'s state.era==="tto" branch not found');
  const branch = src.slice(from, to).replace(/`\+\n\s*`/g, ""); // run.js wraps a long template as `…`+`…`
  const m = /<div class="xw-si"><b>Special instructions<\/b><ul>(.*?)<\/ul><\/div>/.exec(branch);
  if (!m) throw new Error("run.js: special instructions not found in the 1949 branch of renderSheet");
  return m[1];
}

/* A warrant of the modern run's TWC_PLAN (run-modern.js) as the key shows it: {no, at, boxes: {n: {vals, some}}}.
   A box that is null in the plan is set at play time and shows as its slot, such as [time]; a box of a draw is on the
   warrant in some runs only. A box may appear only once across the boxes and the draws. */
function warrant(plan, name) {
  const w = plan.warrants && plan.warrants[name];
  if (!w || !w.no || !w.boxes) throw new Error(`run-modern.js: TWC_PLAN has no warrant ${name} with a no and boxes`);
  const boxes = {};
  const put = (n, vals, some) => {
    if (boxes[n]) throw new Error(`run-modern.js: warrant ${w.no} sets box ${n} twice`);
    if (vals !== null && !Array.isArray(vals)) throw new Error(`run-modern.js: warrant ${w.no} box ${n} is not a list or null`);
    boxes[n] = { vals, some };
  };
  for (const [n, vals] of Object.entries(w.boxes)) put(n, vals, false);
  for (const [draw, sets] of Object.entries(w.draws || {})) {
    if (!Array.isArray(sets) || sets.length !== 2) throw new Error(`run-modern.js: warrant ${w.no} draw ${draw} is not a pair of box sets`);
    for (const set of sets) for (const [n, vals] of Object.entries(set)) put(n, vals, true);
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

/* The time order the game writes at an open office (run.js TIME_ORDER), filled with the first of each choice it makes,
   on the first westward regular train (REGULARS). */
function timeOrder(core) {
  const T = literal(core, "const TIME_ORDER=");
  const train = literal(core, "const REGULARS=").find(tr => tr.dir === "W");
  if (!Array.isArray(T.no) || !Array.isArray(T.late) || !T.late.length || typeof T.words !== "function")
    throw new Error("run.js: TIME_ORDER needs no, late and words");
  if (!train) throw new Error("run.js: REGULARS has no westward train");
  return { no: String(T.no[0]), train: train.name, L: String(T.late[0]), words: T.words(train.name, T.late[0]) };
}

/* The track warrant form's boxes (js/track-warrant.js), loaded as the page loads it. */
function warrantBoxes() {
  const ctx = { window: {} };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(TRACK_WARRANT, "utf8"), ctx, { filename: TRACK_WARRANT });
  const TW = ctx.window.TrackWarrant;
  if (!TW || !Array.isArray(TW.BOXES) || !TW.BOXES.length) throw new Error("js/track-warrant.js: no BOXES on window.TrackWarrant");
  return TW.BOXES;
}

function references(files) {
  const core = fileOf(files, "run.js");
  const ST = literal(core, "const STATIONS=");
  const BOXES = warrantBoxes();
  const plan = literal(fileOf(files, "run-modern.js"), "const TWC_PLAN=");
  if (typeof plan.box5Lead !== "number") throw new Error("run-modern.js: TWC_PLAN has no box5Lead");
  const stations = `<table class="xa-tt"><thead><tr><th>Station</th><th>MP</th><th>Siding</th><th>Notes</th></tr></thead><tbody>${ST.map(st =>
    `<tr><td>${esc(st.n)}</td><td>${st.mp.toFixed(1)}</td><td>${st.sd ? "yes" : "no"}</td><td>${[st.off ? "open office (D)" : "", st.yl ? "yard limits" : ""].filter(Boolean).join(", ")}</td></tr>`).join("")}</tbody></table>`;
  const ord = timeOrder(core);
  const lead = plan.box5Lead;
  const w1 = warrant(plan, "w1"), w2 = warrant(plan, "w2");
  const some = "Rows marked <i>some runs</i> are on the warrant in only some runs.";
  return {
    tt: {
      label: "Show the time-table",
      title: "Time-table No 12, Kestrel Valley Second Subdivision",
      html: `<p>Ashby to Ironton: single track, with double track from Hollis to Ironton. The train columns change from run to run, so they are left out here.</p>${stations}<p><b>Special instructions</b></p><ul>${specialInstructions(core.src)}</ul>`,
    },
    order: {
      label: "Show the order",
      title: "The time order",
      html: `<p>At an open office the operator hands up a time order (Form E) on a westward regular train, for example:</p>
<div class="xa-order"><b>Order No ${esc(ord.no)}</b><br>${esc(ord.words)}</div>
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
  if (badRef) throw new Error(`${badRef.file} line ${badRef.line}: unknown reference "${badRef.ref}" (known: ${Object.keys(REFS).join(", ")})`);
  const unknown = qs.filter(q => !order.includes(q.sec));
  if (unknown.length) throw new Error(`${unknown[0].file} line ${unknown[0].line}: unknown section "${unknown[0].sec}"`);
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
  const files = readRun();
  const qs = extract(files);
  const calls = files.reduce((n, f) => n + (f.src.match(/\bask\(\{/g) || []).length, 0);
  if (qs.length + qs.generated !== calls) throw new Error(`read ${qs.length} questions and ${qs.generated} signal templates but the game's scripts have ${calls} ask({ calls`);
  const GEN = qs.generated ? generatedHtml(loadSignals()) : { n: 0, html: "" };
  const html = render(qs, ENGINE.DECK_SECTIONS, references(files), GEN);
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
module.exports = { readRun, extract, render, references, warrant, warrantHtml, loadSignals, generatedHtml };
