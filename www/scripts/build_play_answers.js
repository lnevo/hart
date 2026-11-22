#!/usr/bin/env node
/* Builds www/play/answers.html, the answer key for Extra East: HART Railroad, from the island shifts in www/play/runs.js
   and the road runs in www/play/road.js (which needs exam/signals.js). Each run's build() is run many times with a
   seeded random stream and a stand-in for the game's helpers, so every branch a draw can take is seen. Each run lists
   every question it can ask; words a draw changes (a time, a count) show as [varies]. Questions asked from inside an
   after() or info callback are not seen; none are today. A road run lists the questions that depend on the path
   through H.key(question), which the game ignores.
   `--check` exits 1 when answers.html is out of date. */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const PLAY = path.join(__dirname, "..", "play");
const RUNS = path.join(PLAY, "runs.js");
const ROAD = path.join(PLAY, "road.js");
const SIGNALS = path.join(PLAY, "..", "exam", "signals.js");
const OUT = path.join(PLAY, "answers.html");
const TUMBLR = "https://www.tumblr.com/pittsburghohiovalleyrailroad/";
const SEC = { gcor: "GCOR crew & speed", sig: "Signals & whistles", def: "Definitions", yl: "Yard limits", sup: "Superiority & movement", to: "Train orders", sem: "Semaphores", twc: "Track warrants" };
const SRC = { GC: "GCOR", YL: "Yard Limits guide", PV: "Mark Connolly's P&OV blog,", SC: "1949 Standard Code", TT: "TT&TO primer", SG: "Signals guide", SM: "Semaphores guide" };
/* The start screen's groups: the heading and its line, in the order the key lists them. */
const GROUPS = { island: ["On the island", "Pittsburgh & Ohio Valley · 1979 to 1990"], chartiers: ["Up the Chartiers", "Pennsylvania Railroad · 1949"] };
const DRAWS = 400; // runs per shift; enough to see every branch of today's draws

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const text = (h) => String(h).replace(/<[^>]*>/g, "").replace(/&amp;/g, "&").replace(/&nbsp;/g, " ");
const srcLabel = (s) => s.replace(/^(?:(GC|YL|PV)\b( ·)?|(SC|TT|SG|SM)\b)/, (m, k, _, j) => SRC[k || j]);

function seeded(n) {
  let a = n >>> 0;
  return () => { a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

/* One body for all the draws: where they differ word by word, the word shows as [varies]. */
function merge(bodies) {
  if (bodies.length === 1) return bodies[0];
  const split = bodies.map((b) => b.split(" "));
  if (split.some((w) => w.length !== split[0].length)) return bodies[0];
  return split[0].map((w, i) => (split.every((x) => x[i] === w) ? w : "[varies]")).join(" ");
}

/* The shifts in the order the game lists them, with every question each can ask. */
function extract(src) {
  const sandbox = vm.createContext({ window: {} });
  vm.runInContext(fs.readFileSync(SIGNALS, "utf8"), sandbox, { filename: SIGNALS });
  vm.runInContext(src, sandbox, { filename: RUNS });
  vm.runInContext(fs.readFileSync(ROAD, "utf8"), sandbox, { filename: ROAD });
  const runs = sandbox.window.NevilleRuns;
  const shifts = [];
  for (const [id, def] of Object.entries(runs)) {
    const byKey = new Map(); // title|right -> the question, with every body a draw gave it
    const idSeed = [...id].reduce((h, c) => Math.imul(h ^ c.charCodeAt(0), 16777619), 2166136261);
    for (let d = 0; d < DRAWS; d++) {
      const R = seeded(idSeed + d * 7919);
      const S = { pace: 1, parAdd: 0, clock: 0, jobs: [] };
      const ask = (o) => { const key = o.title + "|" + o.right; const q = byKey.get(key); if (q) q.bodies.add(o.body); else byKey.set(key, Object.assign({}, o, { bodies: new Set([o.body]) })); return null; };
      const H = {
        ask, key: (o) => { ask(o); },
        info: () => null, mv: () => null, wait: () => null, done: () => null,
        front: () => {}, scene: () => null, next: () => {}, renderStatus: () => {}, finish: () => {}, $: () => null, srcHtml: () => "", shuffle: (a) => a,
        rnd: (a, b) => a + Math.floor(R() * (b - a + 1)), pick: (a) => a[Math.floor(R() * a.length)],
        fmt: (m) => String(m), esc, log: () => {}, addTime: () => 0, get S() { return S; }, get R() { return R; },
      };
      def.build(H);
    }
    const qs = [...byKey.values()].map((q) => Object.assign(q, { body: merge([...q.bodies]) }));
    shifts.push({ id, def, qs, group: def.group || "island" });
  }
  return shifts;
}

function render(shifts) {
  const total = shifts.reduce((n, s) => n + s.qs.length, 0);
  let n = 0;
  const inGroup = (g) => shifts.filter((s) => s.group === g);
  const toc = Object.keys(GROUPS).map((g) => `<strong>${esc(GROUPS[g][0])}</strong>: ` + inGroup(g).map((s) => `<a href="#${s.id}">${esc(s.def.code)} ${esc(s.def.name)}</a>`).join(" · ")).join("<br>");
  const runHtml = (s) => {
    const items = s.qs.map((o) => {
      n++;
      const opts = [{ t: o.right, ok: true }, ...o.wrong.map((w) => ({ t: w[0], ok: false, why: w[2] }))].sort((a, b) => (a.t < b.t ? -1 : a.t > b.t ? 1 : 0)); // code-point order: the same on every host
      const link = o.url ? `<a href="${o.url.startsWith("http") ? o.url : TUMBLR + o.url}" rel="noopener">${esc(srcLabel(o.src))}</a>` : esc(srcLabel(o.src));
      const ow = opts.filter((x) => !x.ok && x.why).map((x) => `<p class="xa-ow">${esc(x.t)}: ${esc(x.why)}</p>`).join("");
      const search = [o.title, text(o.body), o.right, ...o.wrong.map((w) => w[0]), o.why, srcLabel(o.src)].join(" ").toLowerCase();
      return `<article class="xa-q" data-s="${esc(search)}">
  <p class="xa-meta">${n} · ${esc(srcLabel(o.src))} · ${esc(SEC[o.sec] || o.sec)}</p>
  <h4>${esc(o.title)}</h4>
  <p>${o.body}</p>${o.extra || ""}
  <ul class="xa-opts">${opts.map((x) => `<li${x.ok ? ' class="ok"' : ""}>${esc(x.t)}</li>`).join("")}</ul>
  <p class="xa-why">${esc(o.why)}</p>${ow}
  <p class="xa-meta">${link}</p>
</article>`;
    }).join("\n");
    return `<section class="xa-sec" id="${s.id}"><h3>${esc(s.def.code)}, ${esc(s.def.name)} <small>${esc(s.def.dateLine)} · ${s.qs.length} questions</small></h3>\n${items}\n</section>`;
  };
  const secs = Object.keys(GROUPS).map((g) => `<section class="xa-grp"><h2>${esc(GROUPS[g][0])} <small>${esc(GROUPS[g][1])}</small></h2>\n${inGroup(g).map(runHtml).join("\n")}\n</section>`).join("\n");
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Extra East: HART Railroad answer key — HART</title>
  <meta name="description" content="Every question in Extra East: HART Railroad with its answer, the wrong choices and the rule behind it, by shift on the island and by run up the Chartiers.">
  <link rel="stylesheet" href="../css/ops.css">
  <!-- Generated by www/scripts/build_play_answers.js from runs.js. Do not edit by hand. -->
  <style>
.xa-tools{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;position:sticky;top:var(--header-h,0px);background:var(--paper);padding:8px 0;z-index:2}
.xa-tools input[type=search]{flex:1 1 240px;font:inherit;padding:8px 10px;border:1px solid #a9b0bc;border-radius:4px}
.xa-toc{font-size:14px;line-height:1.8}
.xa-q{border:1px solid #c9ced7;border-left:3px solid #e8913a;border-radius:6px;padding:10px 14px;margin:10px 0;background:#f5f6f8}
.xa-q h4{margin:2px 0 6px;font-size:1.05rem}
.xa-meta{margin:0;font-size:12px;color:#545b67;font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
.xa-opts{margin:6px 0;padding-left:22px}
.xa-opts li{margin:2px 0}
.xa-opts li.ok{font-weight:600;color:#2f6b3f;list-style:"✓  "}
.xa-ow,.xa-why{color:#545b67;font-size:14px}
.xa-sec h3 small,.xa-grp h2 small{font-weight:400;color:#545b67}
body.xa-hide .xa-opts li.ok{font-weight:inherit;color:inherit;list-style:disc}
body.xa-hide .xa-why,body.xa-hide .xa-ow{display:none}
  </style>
</head>
<body>
  <header class="site-header" data-ops-header></header>
  <main class="ap-wrap">
    <div class="page-head">
      <h1>Extra East: HART Railroad answer key</h1>
      <p class="section-note">Every question in <a href="index.html">Extra East: HART Railroad</a>, by shift and run: ${total} in all, with a rule that comes up on several runs listed under each. Each shows its choices in alphabetical order with the right one ticked, and the rule behind it. Some questions come up only on some draws, and a word that changes from draw to draw shows as [varies]. The rules are in the <a href="../exam/index.html">C&amp;E study deck</a>.</p>
    </div>
    <div class="xa-tools">
      <input type="search" id="xaFilter" placeholder="Filter by rule, word or answer" aria-label="Filter questions">
      <label><input type="checkbox" id="xaHide"> Hide answers</label>
    </div>
    <p class="xa-toc">${toc}</p>
${secs}
  </main>
  <footer class="site-footer" data-ops-footer></footer>
  <script src="../js/nav.js"></script>
  <script>
  (function(){
    var f=document.getElementById("xaFilter"),h=document.getElementById("xaHide");
    f.addEventListener("input",function(){var v=f.value.trim().toLowerCase();
      document.querySelectorAll(".xa-q").forEach(function(a){a.hidden=!!v&&a.dataset.s.indexOf(v)<0});
      document.querySelectorAll(".xa-sec,.xa-grp").forEach(function(s){s.hidden=!s.querySelector(".xa-q:not([hidden])")});});
    h.addEventListener("change",function(){document.body.classList.toggle("xa-hide",h.checked)});
  })();
  document.addEventListener("DOMContentLoaded", function () { HARTOps.mountChrome("play").catch(function (err) { console.error(err); }); });
  </script>
</body>
</html>
`;
}

if (require.main === module) {
  const html = render(extract(fs.readFileSync(RUNS, "utf8")));
  if (process.argv.includes("--check")) {
    const cur = fs.existsSync(OUT) ? fs.readFileSync(OUT, "utf8") : "";
    if (cur !== html) { console.error("play/answers.html is out of date: run node www/scripts/build_play_answers.js"); process.exit(1); }
    console.log("play/answers.html is current");
  } else {
    fs.writeFileSync(OUT, html);
    console.log("Wrote " + OUT);
  }
}
module.exports = { extract, render };
