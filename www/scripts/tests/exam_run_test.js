#!/usr/bin/env node
/* Loads Extra East (exam/run.html's scripts, in its order) into the fake DOM and plays every run to its end screen,
   always taking the first button. It checks that the five scripts share their names through window.ExtraEast, that
   the clock reads 0:01 a minute past midnight, and that no run throws. No dependencies. Usage: node exam_run_test.js */
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const { El, roots, mk, doc } = require("./fake_dom.js");

const WWW = path.join(__dirname, "..", "..");
const SCRIPTS = ["js/game-engine.js", "exam/signals.js", "exam/run.js", "exam/run-1949.js", "exam/run-modern.js",
  "exam/run-signals.js", "exam/run-yard.js"]; // run.html's order
const ERAS = ["tto", "twc", "yard", "sig"];
const FORM_RUNS = new Set(["twc"]); // its warrant form needs boxes ticked, which the fake DOM has not: played 200 clicks, no end
const MAX_STEPS = 2000;

["xw", "xwStart", "xwGame", "xwStatus", "xwMap", "xwScene", "xwSheet", "xwLog", "xwBest", "sigRules"].forEach((id) => mk(id));
const sigSys = mk("sigSys"); sigSys.checked = false;
const sigSwitch = new El("div"); sigSwitch.classList.toggle = () => {}; sigSys.closest = () => sigSwitch; // the switch label run.js toggles
// run-modern.js asks the page for "#xwScene .result": descendant selectors, one compound part at a time
doc.querySelector = (sel) => sel.split(/\s+/).slice(1).reduce((found, part) => found.flatMap((e) => e.querySelectorAll(part)),
  doc.querySelectorAll(sel.split(/\s+/)[0]))[0] || null;
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

const scene = doc.getElementById("xwScene");
for (const [i, era] of ERAS.entries()) {
  eraBtns[i].onclick();
  let steps = 0;
  while (!scene.querySelector("#again")) {
    if (FORM_RUNS.has(era) && steps >= 200) break;
    assert.ok(++steps < MAX_STEPS, `${era}: no end screen after ${MAX_STEPS} clicks`);
    const b = scene.querySelectorAll("button").find((x) => !x.disabled && x.onclick);
    assert.ok(b, `${era}: a scene with no button to press:\n${scene.innerHTML.slice(0, 300)}`);
    b.onclick();
  }
  if (era === "tto") { // the clock on a 24-hour face, as in play: a minute past midnight is 0:01, not 24:01
    X.state.clock = 1441; X.renderStatus();
    assert.match(doc.getElementById("xwStatus").innerHTML, /<b>0:01<\/b>/);
    assert.strictEqual(X.fmt(1441), "0:01");
    assert.strictEqual(X.fmt(23 * 60 + 59), "23:59");
  }
  console.log(`${era}: ${scene.querySelector("#again") ? "ended" : "still running"} after ${steps} clicks, ${X.state.marks} marks`);
}
// every box of the track warrant form has a spoken line, so any warrant the exam builds can be read out
const { BOXES, SAY } = X.warrantForm;
const said = Array.from(BOXES, ([n]) => n).filter((n) => typeof SAY[n] !== "function");
assert.deepStrictEqual(said, [], `track warrant boxes with no spoken line: ${said}`);
console.log("exam run OK");
