#!/usr/bin/env node
/* The pure helpers of js/game-engine.js, the engine Extra East and Extra East: HART Railroad share: shuffle and pick
   with a seeded stream, rnd's bounds, fmt's 24-hour face, esc, and the shared source labels. Usage: node game_engine_test.js */
"use strict";
const assert = require("assert");
const path = require("path");
const E = require(path.join(__dirname, "..", "..", "js", "game-engine.js"));

// the same seed gives the same draws; a different seed gives others
const a = E.seeded("neville|2026-11-26"), b = E.seeded("neville|2026-11-26"), c = E.seeded("other");
const drawsA = [a(), a(), a()];
assert.deepStrictEqual(drawsA, [b(), b(), b()]);
assert.notDeepStrictEqual(drawsA, [c(), c(), c()]);
assert.ok(drawsA.every((x) => x >= 0 && x < 1));

// shuffle: a permutation, the input untouched, the same order from the same seed
const deck = [1, 2, 3, 4, 5, 6, 7, 8];
const s1 = E.shuffle(deck, E.seeded("x")), s2 = E.shuffle(deck, E.seeded("x"));
assert.deepStrictEqual(s1, s2);
assert.deepStrictEqual([...s1].sort(), deck);
assert.deepStrictEqual(deck, [1, 2, 3, 4, 5, 6, 7, 8]);
assert.deepStrictEqual(E.shuffle([], E.seeded("x")), []);

// pick and rnd: the ends of the stream
assert.strictEqual(E.pick(["a", "b", "c"], () => 0), "a");
assert.strictEqual(E.pick(["a", "b", "c"], () => 0.999), "c");
assert.strictEqual(E.rnd(3, 7, () => 0), 3);
assert.strictEqual(E.rnd(3, 7, () => 0.999), 7);

// fmt: h:mm, rounded, on a 24-hour face in both games
assert.strictEqual(E.fmt(360), "6:00");
assert.strictEqual(E.fmt(65.6), "1:06");
assert.strictEqual(E.fmt(1441), "0:01");
assert.strictEqual(E.fmt(-15), "23:45");
assert.strictEqual(E.fmt(1440 + 360), "6:00");

// source labels: the exam keeps every dot; play drops it after GC, YL and PV; an unknown key stays as written
assert.strictEqual(E.srcLabel("GC · 6.13"), "GCOR · 6.13");
assert.strictEqual(E.srcLabel("GC · 6.13", E.PLAY_DOTLESS), "GCOR 6.13");
assert.strictEqual(E.srcLabel("YL", E.PLAY_DOTLESS), "Yard Limits guide");
assert.strictEqual(E.srcLabel("TW · Selected rules", E.PLAY_DOTLESS), "Track Warrants guide · Selected rules");
assert.strictEqual(E.srcLabel("SC · Rule 14(l)", E.PLAY_DOTLESS), "1949 Standard Code · Rule 14(l)");
assert.strictEqual(E.srcLabel("GCX · 1"), "GCX · 1");
assert.strictEqual(E.srcLabel("Blog post"), "Blog post");
// the deck's eight sections, in its order; SECTIONS adds play's P&OV jobs at the end
assert.deepStrictEqual(Object.keys(E.DECK_SECTIONS), ["def", "sup", "to", "sig", "sem", "yl", "twc", "gcor"]);
assert.deepStrictEqual(Object.keys(E.SECTIONS), [...Object.keys(E.DECK_SECTIONS), "pov"]);

assert.strictEqual(E.esc(`<a href="x">'&'</a>`), "&lt;a href=&quot;x&quot;&gt;&#39;&amp;&#39;&lt;/a&gt;");
assert.strictEqual(E.MAX_MARKS, 5);
console.log("game engine OK");
