#!/usr/bin/env node
/* Builds www/exam/answers.html, the answer key for the Extra East game, from the ask({...}) calls in www/exam/run.html.
   Each call is evaluated with every unknown name stubbed, so values the game fills in at play time (station, train,
   clock time) show as [station], [train] or […]. `--check` exits 1 when answers.html is out of date. */
"use strict";
const fs = require("fs");
const path = require("path");

const EXAM = path.join(__dirname, "..", "exam");
const RUN = path.join(EXAM, "run.html");
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
      if (want !== c) throw new Error(`run.html line ${src.slice(0, j).split("\n").length}: unbalanced ${c}`);
      if (!stack.length) return { end: j, code };
    }
  }
  throw new Error(`run.html line ${src.slice(0, open).split("\n").length}: no closing bracket`);
}
const closing = (src, open) => scan(src, open).end;

/* A stand-in for any name the game defines at play time; prints as [name]. */
function stub(name) {
  return new Proxy(function () {}, {
    get: (t, k) => (k === Symbol.toPrimitive ? () => `[${name}]` : stub(`${name}.${String(k)}`)),
    apply: () => `[${name}(…)]`,
  });
}
/* Helpers the key runs for real, read from run.html: the figures a question may show under its text. */
const FIGURES = ["semSvg"];
function figures(src) {
  const out = {};
  for (const name of FIGURES) {
    const at = src.indexOf(`function ${name}(`);
    if (at < 0) throw new Error(`run.html: figure helper ${name} not found`);
    out[name] = Function(`return (${src.slice(at, closing(src, src.indexOf("{", at)) + 1)})`)();
  }
  return out;
}
const scopeWith = real => new Proxy({}, {
  has: (t, k) => typeof k === "string" && !(k in globalThis),
  get: (t, k) => (k === Symbol.unscopables ? undefined : k in real ? real[k] : stub(String(k))),
});

const FRIENDLY = [
  [/\[ST\.\[?\w+\]?\.n\]/g, "[station]"],
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
const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const text = v => (v == null ? "" : friendly(v));
const ENT = { "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&nbsp;": " " };
const plain = s => s.replace(/<[^>]+>/g, " ").replace(/&(?:amp|lt|gt|quot|#39|nbsp);/g, e => ENT[e]).replace(/\s+/g, " ");

/* Where in the game a question is asked: inside one of the event pools, or fixed in a scene. */
const POOLS = { ROAD_TTO: "1949 run, on the road", STN_TTO: "1949 run, at a station", ROAD_TWC: "Modern run, on the road" };
function poolRanges(src) {
  const out = [];
  for (const name of Object.keys(POOLS)) {
    const at = src.indexOf(`const ${name}=[`);
    if (at < 0) throw new Error(`run.html: pool ${name} not found`);
    const open = src.indexOf("[", at);
    out.push({ name, from: open, to: closing(src, open) });
  }
  return out;
}

function readSections(src) {
  const m = /const SEC=(\{[^}]*\})/.exec(src);
  if (!m) throw new Error("run.html: section names (const SEC) not found");
  return Function(`return ${m[1]}`)();
}

/* Fields the key shows. Others (ok, okText, note, after, miss) only matter during a run. */
const SHOWN = ["sec", "src", "title", "body", "right", "wrong", "why", "extra"];

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

function readSources(src) {
  const m = /const SRC=(\{[^}]*\})/.exec(src);
  if (!m) throw new Error("run.html: source names (const SRC) not found");
  const SRC = Function(`return ${m[1]}`)();
  const re = new RegExp(`^(${Object.keys(SRC).join("|")})\\b`);
  return s => s.replace(re, k => SRC[k]); // the same label the game shows (srcLabel)
}

/* The modern run's code sits between its warrant tables and the end-of-run scene; everything before is 1949. */
function modernRange(src) {
  const from = src.indexOf("const TW_SEL="), to = src.indexOf("function finish(");
  if (from < 0 || to < from) throw new Error("run.html: modern run code (const TW_SEL … function finish) not found");
  return { from, to };
}

function extract(src) {
  const pools = poolRanges(src);
  const modern = modernRange(src);
  const scope = scopeWith(figures(src));
  const srcLabel = readSources(src);
  const qs = [];
  const re = /\bask\(\{/g;
  let m;
  while ((m = re.exec(src))) {
    const open = m.index + 4;
    const line = src.slice(0, m.index).split("\n").length;
    const { end, code } = scan(src, open);
    // Stubs are always truthy, so a shown field chosen at play time would show one branch as the only answer.
    const chosen = SHOWN.filter(k => /\?|&&|\|\|/.test(fieldCode(code, k)));
    if (chosen.length) throw new Error(`run.html line ${line}: ${chosen.join(", ")} chosen at play time (?, && or ||); write one ask per case, or put a situational sentence in note`);
    const lit = src.slice(open, end + 1);
    let o;
    try {
      o = Function("P", `with(P){return (${lit})}`)(scope);
    } catch (e) {
      throw new Error(`run.html line ${line}: cannot read question (${e.message})`);
    }
    if (o.extra && /\[\w/.test(String(o.extra))) throw new Error(`run.html line ${line}: the figure under the question uses play-time values the key cannot draw`);
    for (const k of ["title", "body", "right", "why"]) if (!o[k]) throw new Error(`run.html line ${line}: question has no ${k}`);
    if (!Array.isArray(o.wrong) || !o.wrong.length) throw new Error(`run.html line ${line}: question has no wrong answers`);
    const pool = pools.find(p => m.index > p.from && m.index < p.to);
    qs.push({
      line, sec: o.sec, src: text(srcLabel(String(o.src || ""))), extra: o.extra ? String(o.extra) : "", title: text(o.title), body: text(o.body), right: text(o.right),
      wrong: o.wrong.map(w => ({ t: text(w[0]), why: text(w[2] || "") })),
      why: text(o.why), where: pool ? POOLS[pool.name] : m.index > modern.from && m.index < modern.to ? "Modern run" : "1949 run",
    });
  }
  return qs;
}

function render(qs, SEC) {
  const order = Object.keys(SEC);
  const unknown = qs.filter(q => !order.includes(q.sec));
  if (unknown.length) throw new Error(`run.html line ${unknown[0].line}: unknown section "${unknown[0].sec}"`);
  let n = 0;
  const groups = order.map(sec => {
    const list = qs.filter(q => q.sec === sec);
    if (!list.length) return "";
    const cards = list.map(q => {
      n++;
      const search = plain([q.title, q.body, q.right, q.src, q.why, ...q.wrong.flatMap(w => [w.t, w.why])].join(" ")).toLowerCase();
      // Alphabetical, so the right answer is not always first when answers are hidden.
      const opts = [{ t: q.right, ok: true }, ...q.wrong].sort((a, b) => a.t.localeCompare(b.t));
      return `<article class="xa-q" data-s="${esc(search)}">
  <p class="xa-meta">${n} · ${esc(q.where)} · ${esc(q.src)}</p>
  <h3>${esc(q.title)}</h3>
  <p>${q.body}</p>${q.extra ? `\n  <div class="xa-fig">${q.extra}</div>` : ""}
  <ul class="xa-opts">${opts.map(o => `<li${o.ok ? ' class="ok"' : ""}>${esc(o.t)}${o.why ? ` <span class="xa-ow">${o.why}</span>` : ""}</li>`).join("")}</ul>
  <p class="xa-why">${q.why}</p>
</article>`;
    }).join("\n");
    return `<section class="xa-sec" id="${sec}"><h2>${esc(SEC[sec])} <small>${list.length}</small></h2>\n${cards}\n</section>`;
  }).join("\n");
  const toc = order.filter(s => qs.some(q => q.sec === s)).map(s => `<a href="#${s}">${esc(SEC[s])}</a>`).join(" · ");
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Extra East answer key — HART</title>
  <meta name="description" content="Every question in the Extra East game with its answer, the wrong choices and the rule behind it.">
  <link rel="stylesheet" href="../css/ops.css">
  <link rel="stylesheet" href="../css/achievements.css">
  <!-- Generated by www/scripts/build_exam_answers.js from run.html. Do not edit by hand. -->
  <style>
.xa-tools{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;position:sticky;top:var(--header-h,0px);background:var(--paper);padding:8px 0;z-index:2}
.xa-tools input[type=search]{flex:1 1 240px;font:inherit;padding:8px 10px;border:1px solid #b9b4a6;border-radius:4px}
.xa-toc{font-size:14px;line-height:1.8}
.xa-q{border:1px solid #d6d0c0;border-radius:6px;padding:10px 14px;margin:10px 0}
.xa-q h3{margin:2px 0 6px}
.xa-meta{margin:0;font-size:12px;color:#5d5a4e;font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
.xa-opts{margin:6px 0;padding-left:22px}
.xa-opts li{margin:2px 0}
.xa-fig{margin:4px 0}
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
  })();
  document.addEventListener("DOMContentLoaded", function () { HARTOps.mountChrome("ap-exam").catch(function (err) { console.error(err); }); });
  </script>
</body>
</html>
`;
}

function main() {
  const src = fs.readFileSync(RUN, "utf8");
  const qs = extract(src);
  const calls = (src.match(/\bask\(\{/g) || []).length;
  if (qs.length !== calls) throw new Error(`read ${qs.length} questions but run.html has ${calls} ask({ calls`);
  const html = render(qs, readSections(src));
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
module.exports = { extract, render, readSections };
