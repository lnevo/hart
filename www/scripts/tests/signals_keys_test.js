#!/usr/bin/env node
/* Unit test for the signal tables' lookups (exam/signals.js): an arm or lamp letter, or a plate, that the tables do not
   hold throws UnknownSignalKey naming the table, the key and the call it came in, and the known keys still draw.
   No dependencies. */
"use strict";
const path = require("path");
const assert = require("assert");

const S = require(path.join(__dirname, "..", "..", "exam", "signals.js"));
const { UnknownSignalKey } = S;

/* The call must throw UnknownSignalKey for key in table, with a message that names the call. */
function unknown(call, table, key, where) {
  assert.throws(call, (e) => {
    assert.ok(e instanceof UnknownSignalKey, `${where}: ${e && e.name} instead of UnknownSignalKey`);
    assert.ok(e instanceof Error);
    assert.strictEqual(e.name, "UnknownSignalKey");
    assert.strictEqual(e.table, table);
    assert.strictEqual(e.key, key);
    assert.ok(e.message.startsWith(where), `the message names the call: ${e.message}`);
    assert.ok(e.message.includes(`"${key}" is not in ${table}`), e.message);
    return true;
  });
}

unknown(() => S.sigFig("GXR"), "ARM", "X", 'sigFig("GXR")');
unknown(() => S.armWords("Z"), "ARM", "Z", 'armWords("Z")');
unknown(() => S.lightFig("RQ", ""), "LAMP", "Q", 'lightFig("RQ")');
unknown(() => S.lampWords("B"), "LAMP", "B", 'lampWords("B")');
unknown(() => S.plateWrongs("Q"), "PLATES", "Q", 'plateWrongs("Q")');
// a key that is only on Object.prototype is not a table entry
unknown(() => S.plateWrongs("toString"), "PLATES", "toString", 'plateWrongs("toString")');
// a plate whose near list names a plate that is not there
S.PLATES.T = { name: "T plate", with: "a T plate", near: ["W"], act: "Test" };
try { unknown(() => S.plateWrongs("T"), "PLATES", "W", 'plateWrongs("T"), its near list'); } finally { delete S.PLATES.T; }
// arms or heads that are not a string of letters
for (const bad of ["", null, undefined, 3]) {
  assert.throws(() => S.sigFig(bad), TypeError, `sigFig(${bad})`);
  assert.throws(() => S.lightFig(bad, ""), TypeError, `lightFig(${bad})`);
}

// the known keys still draw
for (const a of S.ASPECTS) assert.match(S.sigFig(a.arms), /^<svg class="ce-sig"/, `Rule ${a.r}`);
for (const r of S.ROUTE) assert.match(S.lightFig(r.heads, ""), /^<svg class="ce-sig"/, r.k);
assert.strictEqual(S.armWords("GRR"), "green, vertical; red, horizontal; red, horizontal");
assert.strictEqual(S.lampWords("RY"), "red over yellow");
for (const k of Object.keys(S.PLATES)) assert.ok(S.plateWrongs(k).length > 0, `plate ${k} has wrong choices`);

console.log("signal keys OK");
