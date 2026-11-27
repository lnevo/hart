// The photo galleries, www/js/gallery.js, on a small gallery.json in a stub page (run: node gallery_view_test.js):
// dates, album scoping, the three views, the month timeline, the curation switch and the deep-link opener.
"use strict";
const assert = require("assert");
const path = require("path");
const { StubEl, loadPage, same, WWW } = require("./stub_page.js");

const GALLERY_JS = path.join(WWW, "js", "gallery.js");
const BEFORE = [path.join(WWW, "js", "photo-viewer.js")];
const DATA = {
  title: "Photos",
  lede: "From the layout.",
  albums: [{ id: "layout", label: "Layout", count: 2 }, { id: "progress", label: "Progress", count: 2 }],
  items: [
    { id: "a", album: "layout", src: "assets/a.jpg", thumb: "assets/a-t.jpg", title: "Yard <A>", caption: "One", width: 4, height: 3 },
    { id: "b", album: "layout", src: "https://example.org/b.jpg", title: "B", caption: "Two", date: "2025-08-09", credit: "Club" },
    { id: "c", album: "progress", src: "assets/c.jpg", title: "C", caption: "Three", date: "2025-08-01" },
    { id: "d", album: "progress", src: "assets/d.jpg", title: "D", caption: "Four" },
  ],
};
const PHOTOS = { albums: ["layout", "progress"], album: "layout", heading: false, albumBar: "#bar", grid: "#grid", viewBar: "#views", monthAlbums: ["progress"], curate: "/api/gallery" };
const ok = async () => ({ ok: true, json: async () => ({}) });
const NO_STORAGE = { getItem() { throw new Error("denied"); }, setItem() { throw new Error("denied"); } };

async function page(mountOpts, opts) {
  const p = loadPage(GALLERY_JS, Object.assign({ before: BEFORE, ids: ["bar", "grid", "views", "gallery-title", "gallery-lede", "gallery-toast"], json: { "data/gallery.json": DATA } }, opts));
  await p.ctx.HARTGallery.mount(mountOpts);
  return p;
}

async function main() {
  const lib = (await page({ grid: "#grid" })).ctx.HARTGallery.lib;

  // Dates: a day is optional, and anything else is no date.
  same(lib.parseDate("2025-08"), { y: 2025, m: 8, d: 0 });
  assert.strictEqual(lib.longDate("2025-08-09"), "9 August 2025");
  assert.strictEqual(lib.longDate("summer"), "");

  // Scoping keeps the page's albums in the page's order.
  same(lib.scopeAlbums(DATA.albums, ["progress", "layout", "gone"]).map((a) => a.id), ["progress", "layout"]);
  same(lib.scopeItems(DATA.items, ["progress"]).map((i) => i.id), ["c", "d"]);
  same(lib.scopeItems(undefined, null), []);
  assert.match(lib.albumBarHtml(DATA.albums, 4, "layout"), /^<button type="button" data-album="all" aria-pressed="false">All \(4\)/);
  assert.doesNotMatch(lib.albumBarHtml(DATA.albums.slice(0, 1), 2, "layout"), /data-album="all"/);

  // Stepping wraps both ways, and there is nothing to step through in an empty list.
  same([lib.wrapIndex(0, -1, 3), lib.wrapIndex(2, 1, 3), lib.wrapIndex(0, 1, 0)], [2, 0, null]);

  // A cell: the thumbnail and its size, the title escaped, and the day and month on a timeline.
  const cell = lib.cellHtml(DATA.items[0], 0, { byMonth: false, canEdit: false, albums: DATA.albums });
  assert.match(cell, /<img src="\.\.\/assets\/a-t\.jpg" alt="Yard &lt;A&gt;" width="4" height="3" loading="lazy" decoding="async">/);
  const timeline = lib.gridHtml(DATA.items.slice(1), { byMonth: true, canEdit: false, albums: DATA.albums });
  assert.strictEqual((timeline.match(/class="g-month"/g) || []).length, 2, "August 2025, then undated");
  assert.match(timeline, /<time datetime="2025-08-09">9 Aug<\/time>/);
  assert.match(timeline, /Undated <span><\/span>/);
  assert.match(lib.listHtml(DATA.items.slice(1, 2), DATA.albums), /<td>Layout<\/td><td class="fl-num">9 August 2025<\/td>/);
  assert.match(lib.stageHtml(DATA.items, 1), /<img src="https:\/\/example\.org\/b\.jpg" alt="B">.*2 of 4/);

  // The Photos page: its album first, the masonry, no curation on the public site.
  const pub = await page(PHOTOS);
  assert.match(pub.els.bar.innerHTML, /data-album="layout" aria-pressed="true">Layout \(2\)/);
  same(pub.els.grid.classList.list(), ["gallery-masonry"]);
  assert.doesNotMatch(pub.els.grid.innerHTML, /g-curate/);
  assert.match(pub.els.views.innerHTML, /data-view="grid" aria-pressed="true"/);

  // The stored view opens the page; an unknown one, or storage that throws, falls back to Grid.
  const list = await page(PHOTOS, { stored: { "hart.gallery.view": "list" } });
  assert.match(list.els.grid.innerHTML, /^<div class="fleet-list-wrap">/);
  const odd = await page(PHOTOS, { stored: { "hart.gallery.view": "wall" } });
  assert.match(odd.els.views.innerHTML, /data-view="grid" aria-pressed="true"/);
  const blocked = await page(PHOTOS, { localStorage: NO_STORAGE });
  assert.match(blocked.els.views.innerHTML, /data-view="grid" aria-pressed="true"/);
  assert.match(blocked.els.grid.innerHTML, /class="g-item"/);

  // On the local desk with the review server up, the grid carries the curation controls.
  const desk = await page(PHOTOS, { site: { public: false }, fetch: ok });
  assert.match(desk.els.grid.innerHTML, /<div class="g-cell">.*<div class="g-curate">/);
  const down = await page(PHOTOS, { site: { public: false } });
  assert.doesNotMatch(down.els.grid.innerHTML, /g-curate/, "no review server: read-only");

  // The deep link shows the item's album as a timeline and opens the lightbox on it; an unknown id is false.
  const opener = desk.ctx.HARTGallery.openers["#grid"];
  assert.strictEqual(opener("c"), true);
  same(desk.els.grid.classList.list(), ["build-timeline"]);
  const lb = desk.created[0];
  assert.ok(lb.classList.contains("open"));
  assert.strictEqual(lb.found["h2"].textContent, "C");
  assert.strictEqual(lb.found[".credit"].textContent, "1 August 2025");
  desk.fire("keydown", { key: "ArrowRight" });
  assert.strictEqual(lb.found["h2"].textContent, "D");
  desk.fire("keydown", { key: "ArrowRight" });
  assert.strictEqual(lb.found["h2"].textContent, "C", "the lightbox wraps");
  desk.fire("keydown", { key: "Escape" });
  assert.ok(!lb.classList.contains("open"));
  assert.strictEqual(opener("nope"), false);

  // A curation save: an answer without the gallery is not saved; a good one replaces the page's photos.
  const answers = [{ ok: true, json: async () => ({ saved: true }) },
    { ok: true, json: async () => ({ gallery: Object.assign({}, DATA, { items: DATA.items.slice(1) }) }) }];
  const cur = loadPage(GALLERY_JS, { before: BEFORE, ids: ["bar", "grid", "views", "gallery-toast"], json: { "data/gallery.json": DATA }, site: { public: false },
    fetch: async (url, init) => (init.method === "POST" ? answers.shift() : { ok: true }) });
  const up = new StubEl("button", "");
  Object.assign(up.attrs, { "data-c-move": "up", "data-src": "assets/a.jpg" });
  cur.els.grid.all["[data-c-move]"] = [up];
  await cur.ctx.HARTGallery.mount(PHOTOS);
  const press = async () => { up.listeners.click[0](); await new Promise((r) => setImmediate(r)); }; // the save runs after the click returns
  await press();
  assert.strictEqual(cur.els["gallery-toast"].textContent, "Not saved: the review server sent back no gallery");
  assert.match(cur.els.bar.innerHTML, /All \(4\)/);
  await press();
  assert.strictEqual(cur.els["gallery-toast"].textContent, "Reordered");
  assert.match(cur.els.bar.innerHTML, /All \(3\)/);

  // On the desk the curation tools report through the toast, so a desk page without one is an error.
  const noToast = loadPage(GALLERY_JS, { before: BEFORE, ids: ["bar", "grid", "views"], json: { "data/gallery.json": DATA }, site: { public: false }, fetch: ok });
  await assert.rejects(noToast.ctx.HARTGallery.mount(PHOTOS), /photo viewer: the page has no toast element/);

  // The page's own heading is filled unless heading is false.
  const plain = await page({ grid: "#grid" });
  assert.strictEqual(plain.els["gallery-title"].textContent, "Photos");
  assert.strictEqual(pub.els["gallery-title"].textContent, "");

  console.log("gallery_view_test: ok");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
