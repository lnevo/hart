#!/usr/bin/env node
/* Loads Extra East (exam/run.html's scripts, in its order) into the fake DOM and plays every run to its end screen,
   always taking the first button. On a track warrant it first copies the warrant as the dispatcher reads it. It checks
   that the five scripts share their names through window.ExtraEast, that the clock reads 0:01 a minute past midnight,
   and that no run throws. No dependencies. Usage: node exam_run_test.js [--dump], where --dump prints every screen of
   every run as JSON instead, to compare two versions of the scripts. */
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const { El, roots, mk, doc } = require("./fake_dom.js");

const WWW = path.join(__dirname, "..", "..");
const SCRIPTS = ["js/game-engine.js", "js/track-warrant.js", "exam/signals.js", "exam/run-data.js", "exam/run.js", "exam/run-1949.js", "exam/run-modern.js",
  "exam/run-signals.js", "exam/run-yard.js", "exam/run-title.js"]; // run.html's order
const ERAS = ["tto", "twc", "yard", "sig"]; // the start buttons
const RUNS = ["tto", "twc", "yard", "sigs", "sigr"]; // "sig" plays speed signals, or route signals with the switch on
const MAX_STEPS = 2000;
const DUMP = process.argv.includes("--dump");

["xw", "xwStart", "xwGame", "xwStatus", "xwMap", "xwScene", "xwSheet", "xwLog", "xwBest", "sigRules"].forEach((id) => mk(id));
const sigSys = mk("sigSys"); sigSys.checked = false;
const sigSwitch = new El("div"); sigSwitch.classList.toggle = () => {}; sigSys.closest = () => sigSwitch; // the switch label run.js toggles
// run-modern.js asks the page for "#xwScene .result": descendant selectors, one compound part at a time
doc.querySelector = (sel) => sel.split(/\s+/).slice(1).reduce((found, part) => found.flatMap((e) => e.querySelectorAll(part)),
  doc.querySelectorAll(sel.split(/\s+/)[0]))[0] || null;
// the warrant is read out a line at a time while its box is on the page; every element of the fake page is on it
Object.defineProperty(El.prototype, "isConnected", { get: () => true });
const eraBtns = ERAS.map((era) => { const b = new El("button", { "data-era": era }); roots.push(b); return b; });

const ctx = vm.createContext({ document: doc, console, scrollY: 0, setTimeout: (f) => f(), performance: { now: () => 0 },
  requestAnimationFrame: () => 0, Date, Math,
  localStorage: { _d: {}, getItem(k) { return this._d[k] ?? null; }, setItem(k, v) { this._d[k] = String(v); } } });
ctx.window = ctx; ctx.window.scrollTo = () => {}; ctx.matchMedia = () => ({ matches: true }); // reduced motion: no animation
vm.runInContext("var __s=7;Math.random=function(){__s=(Math.imul(__s,1664525)+1013904223)>>>0;return __s/4294967296}", ctx);
for (const f of SCRIPTS) vm.runInContext(fs.readFileSync(path.join(WWW, f), "utf8"), ctx, { filename: f });

const X = ctx.window.ExtraEast;
for (const name of ["ROAD_TTO", "STN_TTO", "ROAD_TWC", "startTWC", "startSIG", "YLOC", "renderYardMap", "startYARD"])
  assert.ok(X[name], `window.ExtraEast has no ${name}: a later script did not add it`);
assert.strictEqual(typeof ctx.STATIONS, "undefined", "run.js leaks its names as globals");

/* The values for a box's blanks that make the dispatcher's line for it, tried over every choice its selects offer. */
function blanksFor(n, line, selects) {
  const { SAY } = X.warrantForm;
  const options = selects.map((s) => s.querySelectorAll("option").filter((o) => o.getAttribute("value") !== "").map((o) => o.innerHTML));
  const combos = options.reduce((acc, opts) => acc.flatMap((c) => opts.map((o) => [...c, o])), [[]]);
  const hit = combos.find((c) => `Box ${n}. ${SAY[n](c)}.` === line);
  assert.ok(hit, `no choice of the box ${n} blanks reads "${line}"`);
  return hit;
}

/* Copy the warrant on screen: tick each box the dispatcher read and fill its blanks to match his words. */
function copyWarrant() {
  const lines = doc.getElementById("dict").textContent.split("\n").filter((l) => /^Box \d+\. /.test(l));
  assert.ok(lines.length, "a warrant with no boxes read out");
  for (const box of doc.getElementById("xwScene").querySelectorAll("input")) box.checked = false; // a page's checkbox starts clear
  for (const line of lines) {
    const n = +/^Box (\d+)\./.exec(line)[1];
    const row = doc.getElementById("row" + n);
    const selects = row.querySelectorAll("select");
    doc.getElementById("c" + n).checked = true;
    blanksFor(n, line, selects).forEach((v, k) => { selects[k].value = v; });
  }
}

const scene = doc.getElementById("xwScene");
/* Plays one run of era to its end screen. choose picks the button to press from the ones that can be pressed; screens,
   when given, collects every screen and its result box and, at the end, the log, the misses and the status line. */
function play(era, choose, screens) {
  sigSys.checked = era === "sigr";
  eraBtns[ERAS.indexOf(era.startsWith("sig") ? "sig" : era)].onclick();
  assert.strictEqual(X.state.era, era);
  let steps = 0;
  while (!scene.querySelector("#again")) {
    assert.ok(++steps < MAX_STEPS, `${era}: no end screen after ${MAX_STEPS} clicks`);
    if (screens) screens.push(scene.innerHTML, doc.getElementById("xwSheet").innerHTML);
    const live = scene.querySelectorAll("button").filter((x) => !x.disabled && x.onclick);
    assert.ok(live.length, `${era}: a scene with no button to press:\n${scene.innerHTML.slice(0, 300)}`);
    const b = choose(live);
    if (b.id === "rb") copyWarrant();
    b.onclick();
    const result = scene.querySelector(".result"); // the fake page keeps a child's innerHTML apart from its parent's
    if (screens && result) screens.push(result.innerHTML);
  }
  if (screens) screens.push(scene.innerHTML, X.state.log.join("\n"), JSON.stringify(X.state.misses), doc.getElementById("xwStatus").innerHTML);
  return steps;
}

if (DUMP) { // --dump N: N draws of each run, each button chosen from a second seeded stream
  const draws = +process.argv[process.argv.indexOf("--dump") + 1] || 1;
  let seed = 11;
  const choice = (bs) => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return bs[seed % bs.length]; };
  // every other draw takes the answer key's right answer most of the time, so runs get past the early questions
  const KEY = require(path.join(WWW, "scripts", "build_exam_answers.js"));
  const pat = (t) => new RegExp("^" + t.split(/\[[^\]]*\]/).map((x) => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join(".+") + "$");
  const key = KEY.extract(KEY.readRun()).map((q) => ({ t: pat(q.title), r: pat(q.right) }));
  const unesc = (t) => t.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&amp;/g, "&");
  const careful = (bs) => {
    const title = unesc((scene.querySelector("h2") || { innerHTML: "" }).innerHTML);
    const right = bs.find((b) => key.some((q) => q.t.test(title) && q.r.test(unesc(b.innerHTML))));
    return right && choice([0, 1, 2, 3, 4, 5, 6, 7, 8]) ? right : choice(bs);
  };
  const screens = {};
  for (const era of RUNS) for (let d = 0; d < draws; d++) play(era, d ? (d % 2 ? careful : choice) : (bs) => bs[0], screens[`${era} ${d}`] = []);
  console.log(JSON.stringify(screens, null, 1));
  process.exit(0);
}

for (const era of RUNS) {
  const steps = play(era, (bs) => bs[0]);
  if (era === "tto") { // the clock on a 24-hour face, as in play: a minute past midnight is 0:01, not 24:01
    X.state.clock = 1441; X.renderStatus();
    assert.match(doc.getElementById("xwStatus").innerHTML, /<b>0:01<\/b>/);
    assert.strictEqual(X.fmt(1441), "0:01");
    assert.strictEqual(X.fmt(23 * 60 + 59), "23:59");
  }
  console.log(`${era}: ended after ${steps} clicks, ${X.state.marks} marks`);
}
// a warrant run that copies each warrant right and takes the "Continue" buttons reaches warrant 103 (Granite)
const copied = [];
for (let d = 0; d < 40 && !copied.some((l) => /Warrant 103 OK/.test(l)); d++) {
  let seed = d + 1;
  play("twc", (bs) => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return bs[seed % bs.length]; });
  copied.push(X.state.log.join("\n"));
}
assert.ok(copied.some((l) => /Warrant 101 OK/.test(l)), "no warrant run got warrant 101 read back right");
// every box of the track warrant form has a spoken line, so any warrant the exam builds can be read out
const { BOXES, SAY } = X.warrantForm;
const said = Array.from(BOXES, ([n]) => n).filter((n) => typeof SAY[n] !== "function");
assert.deepStrictEqual(said, [], `track warrant boxes with no spoken line: ${said}`);
// the copy check: a box checked when not given, one given but not checked, and a blank that differs are wrong
const { wrongBoxes } = X.warrantForm;
const form = (on) => Object.fromEntries(BOXES.map(([n]) => [n, { on: false, v: [] }]).concat(on));
const w = { no: "1", boxes: { 2: ["Ashby", "Dunmore", "Main"], 10: [] } };
assert.deepStrictEqual([...wrongBoxes(w, form([[2, { on: true, v: ["Ashby", "Dunmore", "Main"] }], [10, { on: true, v: [] }]]))], []);
assert.deepStrictEqual([...wrongBoxes(w, form([[2, { on: true, v: ["Ashby", "Cobb", "Main"] }], [15, { on: true, v: [] }]]))], [2, 10, 15]);
// run.js shares only what it names, and reads back exactly the names it expects from run-modern.js
assert.strictEqual(X.take("t.js", ["fmt"]).fmt, X.fmt);
assert.throws(() => X.take("t.js", ["fmt", "nope"]), /t\.js takes nope, which run\.js does not share/);
assert.throws(() => X.give("t.js", {}), /run\.js reads nothing from t\.js/);
assert.throws(() => X.give("run-modern.js", { startTWC: X.startTWC, ROAD_TWC: X.ROAD_TWC }), /run-modern\.js gives startTWC, ROAD_TWC; run\.js reads/);
assert.throws(() => X.give("run-modern.js", { startTWC: X.startTWC, ROAD_TWC: X.ROAD_TWC, warrantForm: {}, extra: 1 }), /gives .*extra/);
console.log("exam run OK");
