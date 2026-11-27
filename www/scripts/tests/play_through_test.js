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
/* The road runs: the least and most questions on average over the draws that tie up, and the sections every such draw asks. */
const ROAD = { coal: [14, 21, ["sup", "to", "sem"]], passenger: [15, 23, ["to"]], pcy: [15, 22, ["sig", "yl"]], pir: [15, 22, ["twc"]] };

const { El, roots, rects, mk, doc } = require("./fake_dom.js"); // the fake page the runs are played in

/* ---------- load the page's scripts into one context ---------- */
function load(seedBox, phone) { // phone: { scroll(o) } pretends to be a phone and records window.scrollTo
  roots.length = 0;
  ["xw", "xwStart", "xwGame", "xwStatus", "xwMap", "xwScene", "xwSheet", "xwLog", "xwBest"].forEach((id) => mk(id));
  const game = doc.getElementById("xwGame"); game.hidden = true;
  const runBtns = [];
  const ids = []; // the run ids come from the scripts; buttons are made after they load
  const ctx = vm.createContext({ document: doc, console, location: { origin: "http://localhost", pathname: "/play/" }, scrollY: 0,
    localStorage: { _d: {}, getItem(k) { return this._d[k] ?? null; }, setItem(k, v) { this._d[k] = String(v); } } });
  ctx.window = ctx; ctx.window.scrollTo = () => {};
  if (phone) { ctx.innerHeight = 844; ctx.matchMedia = () => ({ matches: true }); ctx.window.scrollTo = phone.scroll; }
  vm.runInContext("var __s=1;Math.random=function(){__s=(Math.imul(__s,1664525)+1013904223)>>>0;return __s/4294967296}", ctx);
  for (const f of ["js/game-engine.js", "play/runs.js", "exam/signals.js", "play/road-engine.js", "play/road.js", "js/track-warrant.js", "play/warrant.js", "play/passenger.js", "play/pcy.js", "play/pir.js"]) vm.runInContext(read(f), ctx, { filename: f });
  for (const id of Object.keys(ctx.window.NevilleRuns)) { const b = new El("button", { "data-run": id }); roots.push(b); runBtns.push(b); ids.push(id); }
  vm.runInContext(read("play/play.js"), ctx, { filename: "play/play.js" });
  /* The fake page has no checkboxes, so the warrant copy is read from this hook instead of the form: the warrant as the
     dispatcher gave it, or on some draws with one box wrong on the first read-back (twice on a few). */
  const twc = ctx.window.RoadEngine.twc;
  twc.read = (w, el, tries) => {
    const got = {};
    twc.BOXES.forEach(([n]) => { const want = w.boxes[n]; got[n] = { on: !!want, v: want ? want.slice() : [] }; });
    if (ctx.__wrongCopy && tries < ctx.__wrongCopy) got[16].on = !got[16].on;
    return got;
  };
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
  const expert = id === "coal" && stats.draw % 5 === 0; // a player who knows the time-table: every answer right, and the coal run's sound path
  const careful = expert ? 1 : rand() < 0.5 ? 0.95 : 0.6; // how often the player picks the right answer
  const patient = !expert && rand() < 0.4;
  let quiet = false;
  stats.cur = { n: 0, secs: new Set(), draw: stats.draw };
  ctx.__wrongCopy = id === "pir" ? [0, 1, 0, 2][stats.draw % 4] : 0; // read-backs of each warrant that come out wrong first
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
      if (id === "pir") { const copyMiss = /Copying track warrant/.test(html); if (ctx.__wrongCopy && !copyMiss) stats.badCopy = (stats.badCopy || 0) + 1; if (!ctx.__wrongCopy && copyMiss) stats.badCopy = (stats.badCopy || 0) + 1; if (ctx.__wrongCopy) stats.wrongCopies = (stats.wrongCopies || 0) + 1; }
      if (expert && !/Clean shift/.test(html)) stats.expertFail = (stats.expertFail || 0) + 1; // the sound path must come out clean
      if (expert) stats.experts = (stats.experts || 0) + 1;
      const home = btns.find((b) => b.id === "home"); home.onclick();
      return;
    }
    if (!btns.length) throw new Error(`${id}: no button to press at step ${step}`);
    const rb = btns.find((b) => b.id === "rb"); // a warrant copy: repeat it to the dispatcher
    if (rb) { rb.onclick(); continue; }
    if (/Nothing comes/.test(scene._inner)) quiet = true;
    const go = btns.find((b) => b.id === "xwGo");
    if (go) { go.onclick(); continue; }
    const opts = btns.filter((b) => b.cls.has("opt"));
    if (opts.length) {
      const title = (/<h2>([^<]*)<\/h2>/.exec(scene._inner) || [])[1] || "";
      stats.cur.n++; stats.cur.secs.add(right.sec(unesc(title)));
      if (!right.sec(unesc(title))) stats.unlisted.add(unesc(title)); // a question the answer key does not list
      const good = opts.filter((b) => right.is(unesc(title), label(b)));
      (good.length && rand() < careful ? good[0] : opts[Math.floor(rand() * opts.length)]).onclick();
      continue;
    }
    // the road's station decision: run to a siding, or wait for the next train. A patient player waits until nothing
    // more is due at the station and then runs; the others choose at random.
    const wait = btns.find((b) => b.id === "dw"), runs = btns.filter((b) => b !== wait);
    if (expert) { // Carnegie, Bridgeville (let No 305 by), Hills, Canonsburg, Houston; then wait for No 92 at Houston and run to Arden
      const at = /<h2>At ([^<,]*)/.exec(scene._inner)[1];
      const clk = (/<span>(\d+):(\d\d)<\/span>/.exec(scene._inner) || []).slice(1).reduce((h, m) => +h * 60 + +m);
      const next = { Carnegie: "Bridgeville", Bridgeville: "Hills", Hills: "Canonsburg", Canonsburg: "Houston", Houston: "Arden" }[at];
      const hold = (at === "Bridgeville" && clk < 453) || (at === "Houston" && clk < 554);
      (hold ? wait : runs.find((b) => label(b) === "Run to " + next) || wait).onclick(); continue;
    }
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
    const stats = { ends: 0, tied: 0, verdicts: {}, done: [], all: [], unlisted: new Set() };
    for (let d = 0; d < DRAWS; d++) {
      const seed = 7919 * (d + 1) + id.length * 104729;
      stats.draw = d;
      try { play(env, id, seed, right, stats); } catch (e) { failures.push(`${id} draw ${d}: ${e.stack.split("\n").slice(0, 4).join(" | ")}`); if (failures.length > 8) break; }
    }
    console.log(`${id}: ${stats.ends}/${DRAWS} ended, ${stats.tied} tied up. ${JSON.stringify(stats.verdicts)}`);
    if (id === "pir") { // the warrant copy: right on some draws, wrong first on others, and a wrong copy is a miss, not a mark
      if (!stats.wrongCopies) failures.push("pir: no draw read a warrant back wrong");
      if (stats.badCopy) failures.push(`pir: ${stats.badCopy} draws had a wrong read-back that was not recorded, or a right one that was`);
    }
    if (stats.expertFail) failures.push(`${id}: ${stats.expertFail} of ${stats.experts} well-played draws were not clean shifts`);
    if (!stats.tied) failures.push(`${id}: no draw reached a tied-up end screen`);
    if (!(id in ROAD) && stats.done.length) { const ns = stats.done.map((d) => d.n); console.log(`${id} questions per draw that tied up: mean ${(ns.reduce((x, y) => x + y, 0) / ns.length).toFixed(1)}, min ${Math.min(...ns)}, max ${Math.max(...ns)}`); }
    if (id in ROAD) { // a road run asks about 15 to 20 questions (the passenger run up to 23), and every draw that ends normally asks the sections the run is about
      const [lo, hi, secs] = ROAD[id];
      const ns = stats.done.map((d) => d.n), mean = ns.reduce((a, b) => a + b, 0) / ns.length, all = stats.all;
      console.log(`${id} questions per draw that tied up: mean ${mean.toFixed(1)}, min ${Math.min(...ns)}, max ${Math.max(...ns)}; all draws: mean ${(all.reduce((a, b) => a + b, 0) / all.length).toFixed(1)}`);
      if (mean < lo || mean > hi) failures.push(`${id}: mean ${mean.toFixed(1)} questions per draw is outside ${lo} to ${hi}`);
      stats.done.forEach((d) => { for (const sec of secs) if (!d.secs.has(sec)) failures.push(`${id} draw ${d.draw}: no ${sec} question`); });
    }
    if (stats.unlisted.size) failures.push(`${id}: asked questions that are not in the answer key: ${[...stats.unlisted].slice(0, 5).join(" | ")}`);
  }
  scrollCheck(failures);
  logicCheck(env.ctx, failures);
  if (failures.length) { console.error("FAIL\n" + failures.join("\n")); process.exit(1); }
  console.log("play-through OK");
}
/* On a phone a new scene that is off the screen brings the status bar (clock, marks, map) back into view; one that is
   already in view, and the first scene of a run, leave the page where it is. */
function scrollCheck(failures) {
  const calls = [];
  const env = load(undefined, { scroll: (o) => calls.push(o.top) });
  const scene = doc.getElementById("xwScene"), status = doc.getElementById("xwStatus");
  status.getBoundingClientRect = () => ({ top: 500 });
  let top = 900; scene.getBoundingClientRect = () => ({ top });
  env.runBtns.find((b) => b.dataset.run === "j105").onclick();
  if (calls.length !== 1) failures.push(`scroll: starting a run scrolled ${calls.length} times, not once`);
  const press = (n) => { for (let i = 0; i < n; i++) { const b = scene.querySelectorAll("button").filter((x) => !x.disabled)[0]; if (b) b.onclick(); } };
  const n1 = calls.length; press(4);
  if (!calls.slice(n1).includes(430)) failures.push(`scroll: a scene below the screen did not bring the status bar into view (${calls.slice(n1)})`);
  top = 300; const n2 = calls.length; press(4);
  if (calls.length !== n2) failures.push("scroll: a scene already in view moved the page");
  top = -50; const n3 = calls.length; press(4);
  if (!calls.slice(n3).includes(430)) failures.push("scroll: a scene above the screen did not bring the status bar into view");
  // after a choice the verdict and Continue come into view; when they are already in view the page stays
  top = 300;
  const toQuestion = () => { for (let i = 0; i < 40 && !scene.querySelectorAll("button").some((b) => b.cls.has("opt")); i++) { const b = scene.querySelectorAll("button").filter((x) => !x.disabled)[0]; if (!b) break; b.onclick(); } };
  const answer = () => scene.querySelectorAll("button").filter((b) => b.cls.has("opt"))[0].onclick();
  toQuestion();
  rects.result = { top: 700, bottom: 900 }; rects.go = { top: 840, bottom: 890 };
  const n4 = calls.length; answer();
  if (!calls.slice(n4).includes(630)) failures.push(`scroll: a verdict below the screen did not come into view (${calls.slice(n4)})`);
  scene.querySelectorAll("button").filter((b) => b.id === "xwGo")[0].onclick(); toQuestion();
  rects.result = { top: 200, bottom: 420 }; rects.go = { top: 360, bottom: 410 };
  const n5 = calls.length; answer();
  if (calls.length !== n5) failures.push("scroll: a verdict already in view moved the page");
  // the way out of a run: a link in the status bar that asks first
  const st = doc.getElementById("xwStatus");
  if (!/data-exit="ask"/.test(st._inner)) failures.push("exit: no Choose another run link in the status bar during a run");
  const click = (v) => st.onclick({ target: { closest: () => ({ dataset: { exit: v } }) } });
  click("ask");
  if (!/Leave this run\?/.test(st._inner)) failures.push("exit: the link did not ask first");
  click("no");
  if (/Leave this run\?/.test(st._inner)) failures.push("exit: Stay did not close the question");
  click("ask"); click("yes");
  if (doc.getElementById("xwStart").hidden) failures.push("exit: Leave did not return to the start screen");
}
/* The start screen's choices: the run suggested after a run, and which rows each view shows. */
function logicCheck(ctx, failures) {
  const L = ctx.window.PlayLogic, runs = ctx.window.NevilleRuns, keys = Object.keys(runs);
  if (!L) { failures.push("logic: window.PlayLogic is missing"); return; }
  const a = L.nextRun(runs, keys[0], new Set(), []);
  if (a !== keys[1]) failures.push(`suggest: after ${keys[0]} with nothing missed and nothing played, expected ${keys[1]}, got ${a}`);
  const b = L.nextRun(runs, keys[0], new Set([keys[1]]), []);
  if (b !== keys[2]) failures.push(`suggest: a run already finished should come after one not finished (got ${b})`);
  const last = keys[keys.length - 1];
  if (L.nextRun(runs, last, new Set(), []) !== keys[0]) failures.push("suggest: the list does not wrap round to its first run");
  const sec = "twc", want = keys.filter((k) => k !== "pir" && (runs[k].covers || []).includes(sec));
  const c = L.nextRun(runs, "coal", new Set(), [sec]);
  if (c !== "pir") failures.push(`suggest: a run that missed ${sec} should be sent to a run that tests it, got ${c} (${want})`);
  if (L.nextRun(runs, keys[0], new Set(), []) === keys[0]) failures.push("suggest: suggested the run just played");
  const group = (k) => runs[k].group || "island", covers = (k) => runs[k].covers || [];
  const all = keys.filter((k) => L.rowShown(covers(k), ""));
  if (all.length !== keys.length || new Set(all.map(group)).size < 2) failures.push("filter: All did not show every run of both groups");
  for (const s of ["def", "sup", "to", "sig", "sem", "yl", "twc", "gcor"]) {
    const got = keys.filter((k) => L.rowShown(covers(k), s)), exp = keys.filter((k) => covers(k).includes(s));
    if (!got.length || got.join() !== exp.join()) failures.push(`filter: chip ${s} showed ${got} instead of ${exp}`);
  }
}
main();
