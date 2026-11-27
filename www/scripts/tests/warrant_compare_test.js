#!/usr/bin/env node
/* Unit test for the track warrant form's check and blank form (js/track-warrant.js compare and formHtml, used by
   www/play/warrant.js and exam/run-modern.js): the warrant as the dispatcher gave it
   against the form as the player filled it. A box is wrong when it is checked but not given, given but not checked,
   or has a blank that differs or is empty. No dependencies. */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const WWW = path.join(__dirname, "..", "..");
const ctx = vm.createContext({ window: {} });
for (const f of ["js/track-warrant.js", "play/road-engine.js", "play/warrant.js"]) vm.runInContext(fs.readFileSync(path.join(WWW, f), "utf8"), ctx, { filename: f });
const { BOXES, SAY } = ctx.window.RoadEngine.twc;
const compare = (w, g) => [...ctx.window.RoadEngine.twc.compare(w, g)]; // a plain array, from this realm

const w = { no: "118", boxes: { 2: ["Bridgeville", "Canonsburg", "Main"], 7: ["Local 2", "Bridgeville"], 10: [] } };
const right = () => { const g = {}; BOXES.forEach(([n]) => { g[n] = { on: !!w.boxes[n], v: w.boxes[n] ? w.boxes[n].slice() : [] }; }); return g; };

assert.deepStrictEqual(compare(w, right()), [], "a right copy has no bad boxes");
let g = right(); g[8].on = true;
assert.deepStrictEqual(compare(w, g), [8], "a box checked that was not given");
g = right(); g[10].on = false;
assert.deepStrictEqual(compare(w, g), [10], "a box given but not checked");
g = right(); g[2].v[1] = "Hills";
assert.deepStrictEqual(compare(w, g), [2], "a blank with the wrong value");
g = right(); g[7].v = ["", "Bridgeville"];
assert.deepStrictEqual(compare(w, g), [7], "a blank left empty");
g = right(); g[16].on = true; g[2].v[0] = "Duff Junction"; g[10].on = false;
assert.deepStrictEqual(compare(w, g), [2, 10, 16], "several wrong, in box order");
assert.deepStrictEqual(compare(w, {}), [2, 7, 10], "an empty form misses every given box");
assert.deepStrictEqual(compare({ boxes: {} }, {}), [], "nothing given, nothing checked");
// the dispatcher's words for a box come from the same values
assert.strictEqual(SAY[1](["121"]), "Track warrant number 1 2 1 is void");
assert.strictEqual(SAY[13](["20", "Carnegie", "Bridgeville"]), "Do not exceed 20 MPH between Carnegie and Bridgeville");
// the blank form: a select per blank with the game's choices, escaped
const TW = ctx.window.TrackWarrant;
const esc = (t) => String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;");
const sel = { s: ["A&B", "C"], t: ["Main"], w: ["1"], train: ["X"], time: ["6:00"], mph: ["10"], txt: ["Joint"] };
const html = TW.formHtml(sel, esc);
assert.strictEqual((html.match(/<label class="box"/g) || []).length, BOXES.length, "one row per box");
assert.ok(html.includes('<select id="b2_1" aria-label="Box 2 blank 2"><option value="">—</option><option>A&amp;B</option><option>C</option></select>'));
assert.throws(() => TW.formHtml({ ...sel, mph: undefined }, esc), /no choices for the \{mph\} blank of box 13/);
assert.strictEqual(ctx.window.RoadEngine.twc.compare, TW.compare, "play checks with the shared compare");
console.log("warrant compare OK");
