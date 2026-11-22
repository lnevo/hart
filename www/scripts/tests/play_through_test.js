#!/usr/bin/env node
/* Plays every run of Extra East: HART Railroad (island shifts and road runs) to its end screen, over many draws, in a
   small fake DOM. A player answers from the answer key most of the time and at random otherwise, and picks any button on
   the road's decision screens. It fails on any exception, on a run that does not end within the step limit, and on a
   run that never ends well (so the end screen of a clean run is exercised). No dependencies. Usage: node
   play_through_test.js [draws per run] */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const WWW = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(WWW, p), "utf8");
const DRAWS = +process.argv[2] || 60;
const MAX_STEPS = 4000;

/* ---------- a fake DOM: just the elements the game reads back (buttons, choices, the result box) ---------- */
const VOID = new Set(["br", "hr", "img", "input", "line", "path", "circle", "rect", "meta", "link", "use"]);
class El {
  constructor(tag, attrs = {}) {
    this.tag = tag; this.attrs = attrs; this.id = attrs.id || ""; this.children = []; this.parent = null; this.hidden = false; this.disabled = false;
    this.cls = new Set((attrs.class || "").split(/\s+/).filter(Boolean)); this._inner = ""; this.textContent = ""; this.dataset = {}; this.onclick = null;
    for (const [k, v] of Object.entries(attrs)) if (k.startsWith("data-")) this.dataset[k.slice(5).replace(/-(\w)/g, (_, c) => c.toUpperCase())] = v;
    this.classList = { add: (...c) => c.forEach((x) => this.cls.add(x)), remove: (...c) => c.forEach((x) => this.cls.delete(x)), contains: (c) => this.cls.has(c) };
    this.style = {}; this.offsetWidth = 0; this.clientWidth = 0;
  }
  set innerHTML(h) { this._inner = String(h); this.children = []; parse(this, this._inner); }
  get innerHTML() { return this._inner; }
  appendChild(c) { c.parent = this; this.children.push(c); return c; }
  hasAttribute(a) { return a in this.attrs; }
  getAttribute(a) { return this.attrs[a] ?? null; }
  closest() { return null; }
  focus() {}
  getBoundingClientRect() { return { top: 0 }; }
  insertBefore(c) { return this.appendChild(c); }
  all() { const out = []; const walk = (e) => e.children.forEach((c) => { out.push(c); walk(c); }); walk(this); return out; }
  querySelectorAll(sel) { return select(this.all(), sel); }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
}
function parse(root, html) {
  const re = /<(\/?)([a-zA-Z][a-zA-Z0-9]*)((?:\s+[a-zA-Z-]+(?:="[^"]*")?)*)\s*(\/?)>/g;
  let cur = root, m;
  while ((m = re.exec(html))) {
    const [, close, tag, attrText, selfClose] = m, t = tag.toLowerCase();
    if (close) { for (let e = cur; e && e !== root; e = e.parent) if (e.tag === t) { e._inner = html.slice(e._start, m.index); cur = e.parent; break; } continue; }
    const attrs = {};
    attrText.replace(/([a-zA-Z-]+)(?:="([^"]*)")?/g, (_, k, v) => { attrs[k] = v === undefined ? "" : v; });
    const el = new El(t, attrs); if ("disabled" in attrs) el.disabled = true;
    cur.appendChild(el); el._start = m.index + m[0].length;
    if (!selfClose && !VOID.has(t)) cur = el;
  }
}
/* one compound selector at a time: tag, #id, .class, [attr] */
function matches(e, sel) {
  const m = sel.match(/^([a-z0-9]*)(#[\w-]+)?((?:\.[\w-]+)*)(\[[\w-]+\])?$/);
  if (!m) throw new Error("fake DOM does not support the selector " + sel);
  if (m[1] && e.tag !== m[1]) return false;
  if (m[2] && e.id !== m[2].slice(1)) return false;
  if (m[3] && !m[3].slice(1).split(".").every((c) => e.cls.has(c))) return false;
  if (m[4] && !(m[4].slice(1, -1) in e.attrs)) return false;
  return true;
}
const select = (els, sel) => els.filter((e) => matches(e, sel));

const roots = [];
const mk = (id, attrs = {}) => { const e = new El("div", Object.assign({ id }, attrs)); roots.push(e); return e; };
const doc = {
  getElementById(id) { for (const r of roots) { if (r.id === id) return r; const f = r.all().find((e) => e.id === id); if (f) return f; } return null; },
  createElement(tag) { return new El(tag); },
  querySelectorAll(sel) { return roots.flatMap((r) => [r, ...r.all()]).filter((e) => matches(e, sel)); },
  addEventListener() {},
};

/* ---------- load the page's scripts into one context ---------- */
function load(seedBox) {
  roots.length = 0;
  ["xw", "xwStart", "xwGame", "xwStatus", "xwMap", "xwScene", "xwSheet", "xwLog", "xwBest"].forEach((id) => mk(id));
  const game = doc.getElementById("xwGame"); game.hidden = true;
  const runBtns = [];
  const ids = []; // the run ids come from the scripts; buttons are made after they load
  const ctx = vm.createContext({ document: doc, console, location: { origin: "http://localhost", pathname: "/play/" }, scrollY: 0,
    localStorage: { _d: {}, getItem(k) { return this._d[k] ?? null; }, setItem(k, v) { this._d[k] = String(v); } } });
  ctx.window = ctx; ctx.window.scrollTo = () => {};
  vm.runInContext("var __s=1;Math.random=function(){__s=(Math.imul(__s,1664525)+1013904223)>>>0;return __s/4294967296}", ctx);
  for (const f of ["play/runs.js", "play/road.js"]) vm.runInContext(read(f), ctx, { filename: f });
  for (const id of Object.keys(ctx.window.NevilleRuns)) { const b = new El("button", { "data-run": id }); roots.push(b); runBtns.push(b); ids.push(id); }
  vm.runInContext(read("play/play.js"), ctx, { filename: "play/play.js" });
  return { ctx, ids, runBtns };
}

/* ---------- the player ---------- */
/* The right answers in the answer key, by question title: "[varies]" in the key stands for any words. */
function rightTexts() {
  const m = require(path.join(WWW, "scripts", "build_play_answers.js"));
  const pat = (t) => new RegExp("^" + t.split("[varies]").map((x) => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join(".+") + "$");
  const entries = [];
  for (const s of m.extract(read("play/runs.js"))) for (const q of s.qs) entries.push({ t: pat(q.title), r: pat(q.right), sec: q.sec });
  return { is: (title, text) => entries.some((e) => e.t.test(title) && e.r.test(text)),
    sec: (title) => (entries.find((e) => e.t.test(title)) || {}).sec };
}
/* the text of a button as the game wrote it: its label plus any small line */
const unesc = (t) => t.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&");
const label = (b) => unesc(b._inner.replace(/<small>.*?<\/small>/g, "").replace(/<[^>]+>/g, ""));

function play(env, id, seed, right, stats) {
  const { ctx, runBtns } = env;
  vm.runInContext("__s=" + (seed >>> 0), ctx);
  let r = seed >>> 0;
  const rand = () => { r = (Math.imul(r, 1103515245) + 12345) >>> 0; return r / 4294967296; };
  const careful = rand() < 0.5 ? 0.95 : 0.6; // how often the player picks the right answer
  const patient = rand() < 0.4;
  let quiet = false;
  stats.cur = { n: 0, secs: new Set(), draw: stats.draw };
  runBtns.find((b) => b.dataset.run === id).onclick();
  const scene = doc.getElementById("xwScene");
  for (let step = 0; step < MAX_STEPS; step++) {
    const btns = scene.querySelectorAll("button").filter((b) => !b.disabled);
    const again = btns.find((b) => b.id === "again");
    if (again) { // the end screen
      const html = scene._inner, verdict = /xw-stamp[^>]*>([^<]*)</.exec(html);
      if (process.env.PLAY_DEBUG) console.log(id, patient ? "patient" : "", careful, (/<p>([^<]*)<\/p>/.exec(html) || [])[1], [...html.matchAll(/<summary>([^<]*)<\/summary>/g)].map((x) => x[1]).join(" | "));
      stats.ends++; stats.verdicts[verdict ? verdict[1] : "?"] = (stats.verdicts[verdict ? verdict[1] : "?"] || 0) + 1;
      if (/Tied up/.test(html) && !/The shift ends/.test(html)) { stats.tied++; stats.done.push(stats.cur); }
      stats.all.push(stats.cur.n);
      const home = btns.find((b) => b.id === "home"); home.onclick();
      return;
    }
    if (!btns.length) throw new Error(`${id}: no button to press at step ${step}`);
    if (/Nothing comes/.test(scene._inner)) quiet = true;
    const go = btns.find((b) => b.id === "xwGo");
    if (go) { go.onclick(); continue; }
    const opts = btns.filter((b) => b.cls.has("opt"));
    if (opts.length) {
      const title = (/<h2>([^<]*)<\/h2>/.exec(scene._inner) || [])[1] || "";
      stats.cur.n++; stats.cur.secs.add(right.sec(unesc(title)));
      const good = opts.filter((b) => right.is(unesc(title), label(b)));
      (good.length && rand() < careful ? good[0] : opts[Math.floor(rand() * opts.length)]).onclick();
      continue;
    }
    // the road's station decision: run to a siding, or wait for the next train. A patient player waits until nothing
    // more is due at the station and then runs; the others choose at random.
    const wait = btns.find((b) => b.id === "dw"), runs = btns.filter((b) => b !== wait);
    if (patient) { if (quiet || !wait) { quiet = false; runs[0].onclick(); } else wait.onclick(); continue; }
    (rand() < 0.4 ? wait : runs[Math.floor(rand() * runs.length)] || wait).onclick();
  }
  throw new Error(`${id}: draw ${seed} did not end in ${MAX_STEPS} steps`);
}

function main() {
  const right = rightTexts();
  const env = load();
  const failures = [];
  for (const id of env.ids) {
    const stats = { ends: 0, tied: 0, verdicts: {}, done: [], all: [] };
    for (let d = 0; d < DRAWS; d++) {
      const seed = 7919 * (d + 1) + id.length * 104729;
      stats.draw = d;
      try { play(env, id, seed, right, stats); } catch (e) { failures.push(`${id} draw ${d}: ${e.stack.split("\n").slice(0, 4).join(" | ")}`); if (failures.length > 8) break; }
    }
    console.log(`${id}: ${stats.ends}/${DRAWS} ended, ${stats.tied} tied up. ${JSON.stringify(stats.verdicts)}`);
    if (!stats.tied) failures.push(`${id}: no draw reached a tied-up end screen`);
    if (id === "coal") { // a road run asks 15 to 20 questions, and every draw that ends normally asks the sections only the road runs cover
      const ns = stats.done.map((d) => d.n), mean = ns.reduce((a, b) => a + b, 0) / ns.length, all = stats.all;
      console.log(`coal questions per draw that tied up: mean ${mean.toFixed(1)}, min ${Math.min(...ns)}, max ${Math.max(...ns)}; all draws: mean ${(all.reduce((a, b) => a + b, 0) / all.length).toFixed(1)}`);
      if (mean < 14 || mean > 21) failures.push(`coal: mean ${mean.toFixed(1)} questions per draw is outside 14 to 21 (about 15 to 20)`);
      stats.done.forEach((d) => { for (const sec of ["sup", "to", "sem"]) if (!d.secs.has(sec)) failures.push(`coal draw ${d.draw}: no ${sec} question`); });
    }
  }
  if (failures.length) { console.error("FAIL\n" + failures.join("\n")); process.exit(1); }
  console.log("play-through OK");
}
main();
