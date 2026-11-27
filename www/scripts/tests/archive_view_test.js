// The historical archive, www/js/archive.js, on a small archive.json in a stub page (run: node archive_view_test.js):
// the filters, the start view, the API errors, the public and desk pages, and the deep link.
"use strict";
const assert = require("assert");
const path = require("path");
const { StubEl, loadPage, same, WWW } = require("./stub_page.js");

const ARCHIVE_JS = path.join(WWW, "js", "archive.js");
const BEFORE = [path.join(WWW, "js", "photo-viewer.js")];
const IDS = ["archive-tabs", "archive-tab-note", "archive-kinds", "archive-tag", "archive-search", "archive-grid", "archive-empty",
  "archive-toast", "archive-lede", "archive-editbar", "archive-view-bar"];
const DATA = {
  lede: "Old pictures.",
  buckets: [{ id: "curated", label: "Curated" }, { id: "review", label: "To review" }, { id: "discard", label: "Discard" }],
  kinds: [{ id: "photo", label: "Photos" }, { id: "ad", label: "Ads" }, { id: "map", label: "Maps" }],
  items: [
    { id: "p1", bucket: "curated", kind: "photo", src: "media/a b.jpg", title: "Plant <1>", caption: "Coke ovens", date: "1949", tags: ["neville-island"], credit: "ACS", credit_confidence: "verified", source_url: "https://example.org/p1" },
    { id: "a1", bucket: "curated", kind: "ad", src: "media/ad.png", title: "Ad", caption: "Chemicals", tags: ["chemicals", "neville-island"] },
    { id: "d1", bucket: "discard", kind: "photo", src: "media/dup.jpg", title: "Dup", caption: "", reason: "Duplicate of p1", tags: ["chemicals"] },
  ],
};
const ok = async () => ({ ok: true, json: async () => ({}) });
const NO_STORAGE = { getItem() { throw new Error("denied"); }, setItem() { throw new Error("denied"); } };

async function page(opts, mountOpts) {
  const p = loadPage(ARCHIVE_JS, Object.assign({ before: BEFORE, ids: IDS, json: { "data/archive.json": DATA } }, opts));
  await p.ctx.HARTArchive.mount(mountOpts || { site: { public: !(opts && opts.fetch) } });
  return p;
}

async function main() {
  const p0 = await page({});
  const lib = p0.ctx.HARTArchive.lib;

  // Paths are encoded per part, with ../ kept; outside links and data URLs are left alone.
  assert.strictEqual(lib.resolveSrc("../media/a b.jpg"), "../../media/a%20b.jpg");
  assert.strictEqual(lib.resolveSrc("https://example.org/x y"), "https://example.org/x y");
  assert.strictEqual(lib.resolveSrc(""), "");

  // Filters: the bucket, the kind, the tag and the search (title, caption, credit, date, tags) together.
  const f = (o) => lib.filterItems(DATA.items, Object.assign({ bucket: "curated", kind: "all", tag: "", q: "" }, o)).map((i) => i.id);
  same(f({}), ["p1", "a1"]);
  same(f({ kind: "ad" }), ["a1"]);
  same(f({ tag: "chemicals" }), ["a1"]);
  same(f({ q: "ACS" }), ["p1"]);
  same(f({ q: "neville" }), ["p1", "a1"]);
  same(f({ bucket: "discard", q: "zzz" }), []);

  // The tag menu counts what the bucket has and drops a chosen tag the bucket does not have.
  const menu = lib.tagMenu(DATA.items.filter((i) => i.bucket === "discard"), "neville-island");
  assert.strictEqual(menu.tag, "");
  assert.strictEqual(menu.html, '<option value="">All tags</option><option value="chemicals">chemicals (1)</option>');
  assert.strictEqual(lib.tagMenu(DATA.items, "chemicals").tag, "chemicals");

  // Kinds: All and each kind that has items, with counts; Maps has none and is left out.
  const kinds = lib.kindsHtml(DATA.kinds, DATA.items, "ad");
  assert.match(kinds, /data-kind="all" aria-pressed="false">All \(3\)/);
  assert.match(kinds, /data-kind="ad" aria-pressed="true">Ads \(1\)/);
  assert.doesNotMatch(kinds, /Maps/);
  assert.match(lib.tabsHtml(DATA.buckets, DATA.items, "discard"), /data-bucket="discard" aria-selected="true" class="archive-tab tab-discard">Discard <span class="count">1</);

  // The start view: ?view= wins over the stored one; an unknown name, or storage that throws, is Grid.
  const sv = (search, stored, storage) => {
    const p = loadPage(ARCHIVE_JS, { before: BEFORE, ids: IDS, json: {}, stored, localStorage: storage });
    return p.ctx.HARTArchive.lib.startView(search);
  };
  assert.strictEqual(sv("?view=gallery", { "hart.archive.view": "list" }), "gallery");
  assert.strictEqual(sv("", { "hart.archive.view": "list" }), "list");
  assert.strictEqual(sv("?view=wall", { "hart.archive.view": "wall" }), "grid");
  assert.strictEqual(sv("", undefined, NO_STORAGE), "grid");
  assert.strictEqual(sv("?view=list", undefined, NO_STORAGE), "list");

  // The API: the server's own error message, or the HTTP status when its answer is not JSON.
  const api = (res) => loadPage(ARCHIVE_JS, { before: BEFORE, ids: IDS, json: {}, fetch: async () => res }).ctx.HARTArchive.lib;
  await assert.rejects(api({ ok: false, status: 400, json: async () => ({ error: "no item x" }) }).postJson("/api/archive/item", { id: "x" }), /^Error: no item x$/);
  await assert.rejects(api({ ok: false, status: 502, json: async () => { throw new SyntaxError("html"); } }).postJson("/api/archive/item", {}), /^Error: HTTP 502$/);
  same(await api({ ok: true, json: async () => ({ item: { id: "p1" } }) }).postJson("/api/archive/item", {}), { item: { id: "p1" } });

  // The public page: the curated set only, no tabs, no desk controls, and the discard bucket not reachable.
  assert.strictEqual(p0.els["archive-lede"].textContent, "Old pictures.");
  assert.ok(p0.els["archive-tabs"].hidden && p0.els["archive-tab-note"].hidden && p0.els["archive-editbar"].hidden);
  assert.match(p0.els["archive-grid"].innerHTML, /^<div class="gallery-masonry">/);
  assert.doesNotMatch(p0.els["archive-grid"].innerHTML, /archive-move|Dup/);
  assert.strictEqual(p0.ctx.HARTArchive.openItem("d1"), false);

  // The deep link opens the lightbox on the item, with its credit and source link.
  assert.strictEqual(p0.ctx.HARTArchive.openItem("p1"), true);
  const lb = p0.created[0];
  assert.ok(lb.classList.contains("open"));
  const meta = lb.found[".meta"].innerHTML;
  assert.match(meta, /<h2 id="archive-lb-title">Plant &lt;1&gt;<\/h2><p class="archive-date">1949<\/p>/);
  assert.match(meta, /ACS · <a href="https:\/\/example\.org\/p1" target="_blank" rel="noopener">Source<\/a> <em class="conf conf-verified">Source verified/);
  assert.doesNotMatch(meta, /archive-edit/);
  p0.fire("keydown", { key: "ArrowRight", target: { tagName: "DIV" } });
  assert.match(lb.found[".meta"].innerHTML, /<h2 id="archive-lb-title">Ad<\/h2>/);
  p0.fire("keydown", { key: "ArrowLeft", target: { tagName: "TEXTAREA" } });
  assert.match(lb.found[".meta"].innerHTML, /<h2 id="archive-lb-title">Ad<\/h2>/, "arrows in a field do not step");
  p0.fire("keydown", { key: "Escape", target: { tagName: "DIV" } });
  assert.ok(!lb.classList.contains("open"));
  assert.strictEqual(p0.ctx.HARTArchive.openItem("nope"), false);

  // The desk page (review server up): tabs, a bucket from the hash, move buttons and the edit form.
  const desk = await page({ fetch: ok, hash: "#discard" });
  assert.ok(!desk.els["archive-tabs"].hidden && !desk.els["archive-editbar"].hidden);
  assert.strictEqual(desk.els["archive-tab-note"].textContent, "Duplicates and out-of-scope items, kept here so the decision is visible.");
  assert.match(desk.els["archive-grid"].innerHTML, /<span class="archive-reason">Duplicate of p1<\/span><div class="archive-move"/);
  assert.strictEqual(desk.ctx.HARTArchive.openItem("d1"), true);
  assert.match(desk.created[0].found[".meta"].innerHTML, /<strong>Discarded:<\/strong> Duplicate of p1.*<details class="archive-edit">/);

  // On Photos the hash names the photo tab, so the archive starts on Curated whatever it says.
  const photos = await page({ fetch: ok, hash: "#discard" }, { site: { public: false }, hash: false });
  assert.doesNotMatch(photos.els["archive-grid"].innerHTML, /Dup/);

  // The Gallery view shows one item large; a search that finds nothing shows the empty note.
  const gal = await page({ search: "?view=gallery" });
  assert.match(gal.els["archive-grid"].innerHTML, /^<div class="fleet-stage">.*1 of 2/);
  assert.strictEqual(gal.els["archive-grid"].className, "archive-view view-gallery");
  gal.els["archive-search"].value = " nothing like it ";
  gal.els["archive-search"].listeners.input.forEach((fn) => fn());
  assert.strictEqual(gal.els["archive-grid"].innerHTML, "");
  assert.strictEqual(gal.els["archive-empty"].hidden, false);

  // A move on the desk: the toast says what was saved, or why not (the server's error, or an answer that is not the
  // item moved); the page's copy changes only on a good answer.
  const answers = [{ ok: true, json: async () => ({ item: { id: "p1", bucket: "review", title: "Plant <1>" } }) },
    { ok: true, json: async () => ({ item: { id: "a1", bucket: "review" } }) },
    { ok: false, status: 400, json: async () => ({ error: "bad bucket" }) },
    { ok: true, json: async () => ({ item: Object.assign({}, DATA.items[2], { bucket: "curated" }) }) }];
  const moves = loadPage(ARCHIVE_JS, { before: BEFORE, ids: IDS, json: { "data/archive.json": DATA }, hash: "#discard",
    fetch: async (url, init) => (init.method === "POST" ? answers.shift() : { ok: true }) });
  const move = new StubEl("button", "");
  Object.assign(move.attrs, { "data-move": "curated", "data-id": "d1" });
  moves.els["archive-grid"].all["[data-move]"] = [move];
  await moves.ctx.HARTArchive.mount({ site: { public: false } });
  const toast = moves.els["archive-toast"];
  const press = async () => { for (const fn of move.listeners.click.slice(0, 1)) await fn({ stopPropagation() {} }); };
  await press();
  assert.strictEqual(toast.textContent, 'Not saved: the review server sent back no item "d1"');
  await press();
  assert.strictEqual(toast.textContent, 'Not saved: the review server sent back no item "d1"');
  await press();
  assert.strictEqual(toast.textContent, "Not saved: bad bucket");
  assert.ok(toast.classList.contains("bad"));
  assert.match(moves.els["archive-grid"].innerHTML, /Dup/, "still in Discard");
  await press();
  assert.strictEqual(toast.textContent, "Moved “Dup” to Curated");
  assert.ok(!toast.classList.contains("bad"));
  assert.strictEqual(moves.els["archive-grid"].innerHTML, "", "Discard is empty now");
  Object.assign(move.attrs, { "data-id": "gone" });
  await press();
  assert.strictEqual(toast.textContent, 'Not saved: the page has no archive item "gone"');

  // A page without one of its elements is an error naming it.
  const broken = loadPage(ARCHIVE_JS, { before: BEFORE, ids: IDS.filter((i) => i !== "archive-toast"), json: { "data/archive.json": DATA } });
  await assert.rejects(broken.ctx.HARTArchive.mount({ site: { public: true } }), /the archive page has no #archive-toast/);

  console.log("archive_view_test: ok");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
