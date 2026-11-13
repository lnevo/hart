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

// ---- stage 4: forgiving matching -------------------------------------------------------------------------
const has = (q, title) => S.match(P, q).some((r) => r.title === title);
// typos: one edit on a word of 5+ letters, whole words of title or snippet
assert(top("shenago", 3).some((t) => /Shenango/.test(t)), "shenago: " + top("shenago"));
assert(has("shenago", "Shenango Furnace history"));
{
  const W = S.prepare([R("article", "Waybill basics", "How a waybill moves.", ""), R("page", "Glossary", "Terms", "waybill")]);
  assert.strictEqual(S.match(W, "wayblil")[0].title, "Waybill basics"); // swap
  assert.strictEqual(S.match(W, "waybil")[0].title, "Waybill basics"); // delete
  assert.strictEqual(S.match(W, "waybilll")[0].title, "Waybill basics"); // insert
  assert.strictEqual(S.match(W, "waxbill")[0].title, "Waybill basics"); // substitute
  assert.strictEqual(S.match(W, "wxybil").length, 0); // two edits
  assert.strictEqual(S.match(W, "wayblil")[0].kind, "article");
}
// a typo hit never scores like a real one, and fuzzy runs only when nothing matches as typed
assert.strictEqual(S.rank(P, "shenago").groups.some((g) => g.id === "best"), false);
// short terms and numbers stay exact
{
  const N = S.prepare([R("locomotive", "CSX 2783", "", ""), R("crew", "NVL", "", ""), R("crew", "NVX", "", "")]);
  assert.strictEqual(S.match(N, "2738").length, 0);
  assert.strictEqual(S.match(N, "nvk").length, 0);
  assert.strictEqual(S.match(N, "nvl")[0].title, "NVL");
  assert.strictEqual(S.match(N, "csx2784").length, 0);
}
// folding
assert.strictEqual(top("ym01", 1)[0], "YM-01");
assert.strictEqual(top("tt23", 1)[0], "TT-23");
assert.strictEqual(labels("ym01")[0], "Best match");
assert.strictEqual(S.fold("B & O"), S.fold("b&o"));
assert.strictEqual(S.fold("Caf\u00e9 O\u2019Brien"), "cafe obrien");
{
  const l = labels("b and o");
  assert(l.includes("Pages & articles") && l[l.length - 1] === "Rolling stock", l.join());
  assert.deepStrictEqual(top("b and o", 3), top("b&o", 3));
  assert(has("bo", "B&O freight cars"));
}
// synonyms work both ways
const SYN = S.prepare([
  R("page", "Chessie notes", "", ""), R("page", "C&O history", "", ""), R("page", "Conrail 1993", "", ""),
  R("page", "CR facts", "", ""), R("page", "P&LE District", "", ""), R("page", "Pittsburgh & Lake Erie map", "", ""),
  R("page", "P&OV at a glance", "", ""), R("page", "Pittsburgh & Ohio Valley Railway", "", ""),
  R("page", "P&CV Division", "", ""), R("page", "Pittsburgh & Chartiers Valley Division", "", ""),
  R("page", "Crew sheets", "", ""),
]);
const sTitles = (q) => S.match(SYN, q).map((r) => r.title);
for (const row of S.SYNONYMS) {
  for (const a of row) for (const b of row) {
    if (a === b) continue;
    // each name finds a page titled with another name when one is in the fixture
    const hit = (t) => S.match(S.prepare([R("page", t + " page", "", "")]), a).length === 1;
    assert(hit(b), "synonym " + a + " -> " + b);
  }
}
assert(sTitles("chessie").includes("C&O history"));
assert(sTitles("c&o").includes("Chessie notes"));
assert(sTitles("conrail").includes("CR facts") && sTitles("cr").includes("Conrail 1993"));
assert(!sTitles("cr").includes("Crew sheets") || sTitles("cr").indexOf("CR facts") < sTitles("cr").indexOf("Crew sheets"));
assert(sTitles("p&le").includes("Pittsburgh & Lake Erie map"));
assert(sTitles("pittsburgh and lake erie").includes("P&LE District"));
assert(sTitles("p&ov").includes("Pittsburgh & Ohio Valley Railway"));
assert(sTitles("pittsburgh & ohio valley").includes("P&OV at a glance"));
// P&CV and P&OV never reach each other
for (const q of ["p&cv", "pcv", "p and cv", "pittsburgh & chartiers valley"]) {
  const t = sTitles(q);
  assert(!t.includes("P&OV at a glance") && !t.includes("Pittsburgh & Ohio Valley Railway"), q + ": " + t);
  assert(t.includes("P&CV Division"), q);
}
for (const q of ["p&ov", "pov", "pittsburgh & ohio valley"]) {
  const t = sTitles(q);
  assert(!t.includes("P&CV Division") && !t.includes("Pittsburgh & Chartiers Valley Division"), q + ": " + t);
}
for (const row of S.SYNONYMS) {
  const j = row.join("|").toLowerCase();
  assert(!(/p&cv|chartiers valley/.test(j) && /p&ov|ohio valley/.test(j)), "P&CV and P&OV share a row");
}
// rolling stock stays last, and leads only for a number
for (const q of ["b and o", "bo", "chessie", "hoper", "cokee"]) {
  const l = labels(q);
  if (l.includes("Rolling stock")) assert.strictEqual(l[l.length - 1], "Rolling stock", q + ": " + l.join());
}
assert.strictEqual(labels("2738")[0], "Best match");
assert(!S.rank(P, "chessie").groups.some((g) => g.id === "best"));

// every example search finds something in the real built index (set SEARCH_INDEX to its path)
const idxPath = process.env.SEARCH_INDEX;
if (idxPath && require("fs").existsSync(idxPath)) {
  const real = S.prepare(JSON.parse(require("fs").readFileSync(idxPath, "utf8")).records);
  assert(S.EXAMPLES.length >= 4 && S.EXAMPLES.length <= 6);
  for (const q of S.EXAMPLES) assert(S.rank(real, q).total > 0, "example finds nothing: " + q);
  for (const q of ["shenago", "wayblil", "ym01", "chessie", "b and o", "2738"]) {
    console.log(q + " ->", S.rank(real, q).groups.map((g) => g.label + ": " + g.items.slice(0, 3).map((r) => r.title).join(" / ")).join("  ||  "));
  }
}
console.log("search rank: all passed");
