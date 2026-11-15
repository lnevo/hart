// Status and bar rules for www/js/achievements.js (run: node achievements_status_test.js).
const assert = require("assert");
const path = require("path");
const A = require(path.join(__dirname, "..", "..", "js", "achievements.js"));

const N = (o) => Object.assign({ done: 0, ready: 0, part: 0, todo: 0, ask: 0 }, o);
const S = (o) => A.statusOf(N(o), Object.values(N(o)).reduce((a, b) => a + b, 0));

assert.strictEqual(S({}), "");
assert.strictEqual(S({ done: 3 }), "done");
assert.strictEqual(S({ done: 10, ready: 1 }), "ready");          // MRE Electrical today
assert.strictEqual(S({ ready: 1 }), "ready");
assert.strictEqual(S({ done: 6, todo: 4 }), "part");
assert.strictEqual(S({ ready: 1, todo: 1 }), "part");            // review finding: was "todo"
assert.strictEqual(S({ ready: 1, ask: 2 }), "part");
assert.strictEqual(S({ done: 1, ready: 1, todo: 1 }), "part");
assert.strictEqual(S({ part: 1, todo: 2 }), "part");
assert.strictEqual(S({ ask: 2 }), "ask");
assert.strictEqual(S({ todo: 2, ask: 1 }), "todo");

assert.strictEqual(A.barPct("10 of 11 done", N({}), 0).toFixed(1), "90.9");
assert.strictEqual(A.barPct("about 22 of 42 points", N({}), 0).toFixed(1), "52.4");
assert.strictEqual(A.barPct("1 of 0", N({ done: 1 }), 2), 50);   // no divide by zero
assert.strictEqual(A.barPct("", N({ done: 3, ready: 1 }), 4), 100);
assert.strictEqual(A.barPct("not logged", N({ ready: 1 }), 1), 100);
assert.strictEqual(A.barPct("—", N({ ask: 1 }), 1), 0);
assert.strictEqual(A.barPct("7 of 5", N({}), 0), 100);

console.log("achievements status: ok");
