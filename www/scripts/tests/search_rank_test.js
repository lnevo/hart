// Ranking tests for www/js/search.js (run: node search_rank_test.js). Fixture records mirror the real index.
const assert = require("assert");
const path = require("path");
const S = require(path.join(__dirname, "..", "..", "js", "search.js"));

const R = (kind, title, snippet, text, url) => ({ kind, title, snippet: snippet || "", text: text || "", url: url || "x/" + title });
const recs = [
  R("article", "Coke at the mill", "How coke moves from the ovens to the furnace.", "coke hopper loads, coke ovens"),
  R("article", "Hoppers on the line", "What a hopper is and how it is unloaded.", "hopper hoppers coal coke"),
  R("page", "Operations", "Run a session.", "hopper cars coke"),
  R("page", "Glossary", "Terms used on the railroad.", "NVL and more"),
  R("page", "Session paperwork", "Crew sheets for each job.", "YM-01 TT-23"),
  R("page", "B&O freight cars", "Baltimore and Ohio cars on the layout.", "b&o"),
  R("article", "Fleet roster", "Cars and locomotives, including B&O hoppers.", "b&o"),
  R("industry", "Coke Works", "Makes coke for the mill.", "coke"),
  R("term", "NVL", "A short line.", "NVL"),
  R("crew", "NVL local", "Crew sheet for the NVL local.", "NVL"),
  R("crew", "YM-01", "Yard master sheet.", "YM-01"),
  R("crew", "TT-23", "Tower sheet.", "TT-23"),
  R("locomotive", "CSX 2738", "SD40-2", "2738 b&o"),
  R("locomotive", "CSX 2121", "SD40-2", "2121"),
  R("mow", "B&O 90001", "Maintenance of way", "b&o"),
  R("archive", "Shenango Furnace history", "Notes on Shenango.", "shenango coke"),
  R("photo", "Shenango mill, 1950", "Photo", "shenango", "p/1"),
];
for (let i = 0; i < 40; i++) recs.push(R("car", "B&O hopper " + (1000 + i), "Hopper, B&O", "b&o hopper coke", "c/" + i));
for (let i = 0; i < 6; i++) recs.push(R("photo", "Hopper photo " + i, "Photo", "hopper", "ph/" + i));
const P = S.prepare(recs);
const top = (q, n) => S.match(P, q).slice(0, n || 3).map((r) => r.title);
const labels = (q) => S.rank(P, q).groups.map((g) => g.label);

// coke: an article or the industry in the top 3, no hopper car among them
{
  const t = S.match(P, "coke").slice(0, 3);
  assert(t.some((r) => r.kind === "article" || r.kind === "industry"), "coke top3: " + top("coke"));
  assert(!t.some((r) => r.kind === "car"), "coke top3 has a car");
}
// hopper: the article shows in its group though 40 cars match
{
  const r = S.rank(P, "hopper");
  const g = r.groups.find((x) => x.id === "pages");
  assert(g && g.items.slice(0, 3).some((x) => x.title === "Hoppers on the line"), "hopper article missing");
  assert(r.total >= 40);
}
// exact hits lead
assert.strictEqual(top("2738", 1)[0], "CSX 2738");
assert.strictEqual(top("csx  2738", 1)[0], "CSX 2738"); // extra spaces keep the exact lead
assert.strictEqual(labels("csx  2738")[0], "Best match");
assert.strictEqual(labels("2738")[0], "Best match");
assert(["NVL", "NVL local"].includes(top("NVL", 1)[0]), "NVL " + top("NVL"));
assert.strictEqual(top("yM-01", 1)[0], "YM-01");
assert.strictEqual(top("TT-23", 1)[0], "TT-23");
// b&o: rolling stock is the lowest priority: it never leads for a road name and its group comes last
{
  const l = labels("b&o");
  assert(l.includes("Rolling stock") && l.includes("Pages & articles"), l.join());
  assert.strictEqual(l[l.length - 1], "Rolling stock", l.join());
  assert(!S.rank(P, "b&o").groups.some((g) => g.id === "best" && g.items.some((r) => ["car", "locomotive", "mow"].includes(r.kind))));
}
// rolling stock is last in every grouped result
for (const q of ["coke", "hopper", "b&o"]) {
  const l = labels(q);
  if (l.includes("Rolling stock")) assert.strictEqual(l[l.length - 1], "Rolling stock", q + ": " + l.join());
}
// several groups are headed
assert(labels("coke").length >= 3);
// one-group query is flat, no match is empty
{
  const r = S.rank(P, "tower");
  assert.strictEqual(r.flat, true);
  assert.strictEqual(r.groups.length, 1);
  assert.strictEqual(S.rank(P, "zzzz").total, 0);
  assert.strictEqual(S.rank(P, "  ").total, 0);
}
// nothing is lost: group sizes add up to the total
{
  const r = S.rank(P, "hopper");
  assert.strictEqual(r.groups.reduce((n, g) => n + g.items.length, 0), r.total);
  assert.strictEqual(S.match(P, "hopper").length, r.total);
}
console.log("search rank: all passed");
