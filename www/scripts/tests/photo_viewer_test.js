// The parts the Photos viewers share, www/js/photo-viewer.js, in a stub page (run: node photo_viewer_test.js): the
// stored view, the view bar, the stage controls, the lightbox, the toast and the review server's errors.
"use strict";
const assert = require("assert");
const path = require("path");
const { StubEl, loadPage, same, WWW } = require("./stub_page.js");

const VIEWER_JS = path.join(WWW, "js", "photo-viewer.js");
const NO_STORAGE = { getItem() { throw new Error("denied"); }, setItem() { throw new Error("denied"); } };
const viewer = (opts) => loadPage(VIEWER_JS, Object.assign({ ids: [], json: {} }, opts));
const button = (attrs) => { const b = new StubEl("button", ""); Object.assign(b.attrs, attrs); return b; };
const click = (el, e) => el.listeners.click.forEach((fn) => fn(Object.assign({ stopPropagation() {} }, e)));

async function main() {
  // The stored view: a view name, else Grid (nothing stored, an unknown name, storage that throws).
  const p = viewer({ stored: { a: "list", b: "wall" } });
  const V = p.ctx.HARTViewer;
  same([V.storedView("a"), V.storedView("b"), V.storedView("none")], ["list", "grid", "grid"]);
  const blocked = viewer({ localStorage: NO_STORAGE }).ctx.HARTViewer;
  assert.strictEqual(blocked.storedView("a"), "grid");
  blocked.storeView("a", "list"); // storage that throws: the view is not kept, and nothing fails

  // The view bar: the view pressed; a click stores the pick, redraws and reports it; an unknown view is an error.
  const bar = new StubEl("div", "bar");
  const picked = [];
  bar.all.button = [button({ "data-view": "gallery" })];
  V.mountViewBar(bar, "k", "grid", (v) => picked.push(v));
  assert.match(bar.innerHTML, /data-view="grid" aria-pressed="true">Grid<\/button><button type="button" data-view="list" aria-pressed="false">/);
  click(bar.all.button[0]);
  same(picked, ["gallery"]);
  assert.strictEqual(p.store.get("k"), "gallery");
  assert.match(bar.innerHTML, /data-view="gallery" aria-pressed="true"/);
  assert.throws(() => V.mountViewBar(bar, "k", "wall", () => {}), /photo viewer: "wall" is not a view/);

  // Stepping wraps both ways, and there is nothing to step through in an empty list.
  same([V.wrapIndex(0, -1, 3), V.wrapIndex(2, 1, 3), V.wrapIndex(0, 1, 0)], [2, 0, null]);

  // The stage: ‹ › step, a strip thumbnail picks its index.
  const grid = new StubEl("div", "grid");
  grid.all["[data-stage]"] = [button({ "data-stage": "2" })];
  const calls = [];
  V.bindStage(grid, (d) => calls.push(["step", d]), (i) => calls.push(["pick", i]));
  click(grid.found[".fleet-stage-nav.prev"]);
  click(grid.found[".fleet-stage-nav.next"]);
  click(grid.all["[data-stage]"][0]);
  same(calls, [["step", -1], ["step", 1], ["pick", 2]]);

  // The lightbox: every option is checked when it is made.
  const items = [{ t: "A" }, { t: "B" }, { t: "C" }];
  const painted = [];
  const lbOpts = { className: "lightbox", titleId: "t", card: "<img>", at: (i) => items[i], count: () => items.length, paint: (it) => painted.push(it.t) };
  assert.throws(() => V.makeLightbox(Object.assign({}, lbOpts, { card: "" })), /the lightbox needs card/);
  assert.throws(() => V.makeLightbox(Object.assign({}, lbOpts, { paint: null })), /the lightbox needs a function paint/);

  // Open paints the item; the arrows step and wrap, not while typing in a field; Esc closes and the arrows then
  // do nothing.
  const lb = V.makeLightbox(lbOpts);
  const el = p.created[p.created.length - 1];
  assert.strictEqual(el.attrs["aria-labelledby"], "t");
  assert.match(el.innerHTML, /<div class="lightbox-card"><img><\/div>$/);
  lb.open(2);
  assert.ok(lb.isOpen());
  p.fire("keydown", { key: "ArrowRight", target: { tagName: "DIV" } });
  p.fire("keydown", { key: "ArrowRight", target: { tagName: "INPUT" } });
  click(el.found[".prev"]);
  same(painted, ["C", "A", "C"]);
  p.fire("keydown", { key: "Escape", target: { tagName: "DIV" } });
  assert.ok(!lb.isOpen());
  p.fire("keydown", { key: "ArrowRight", target: { tagName: "DIV" } });
  same(painted, ["C", "A", "C"]);
  // show(i) repaints item i, or closes when the list no longer has it; a click on the backdrop closes.
  lb.open(0);
  lb.show(1);
  assert.strictEqual(painted[painted.length - 1], "B");
  lb.show(7);
  assert.ok(!lb.isOpen());
  lb.open(0);
  click(el, { target: el });
  assert.ok(!lb.isOpen());

  // The toast shows the message, in the warning colour when bad; a page without its element is an error.
  const toastEl = new StubEl("div", "toast");
  const toast = V.makeToast(toastEl);
  toast("Saved", false);
  assert.strictEqual(toastEl.textContent, "Saved");
  same(toastEl.classList.list(), ["show"]);
  toast("Not saved", true);
  same(toastEl.classList.list(), ["bad", "show"]);
  assert.throws(() => V.makeToast(null), /photo viewer: the page has no toast element/);

  // The review server: its own error message, or the HTTP status when its answer is not JSON.
  const api = (res) => viewer({ fetch: async () => res }).ctx.HARTViewer;
  await assert.rejects(api({ ok: false, status: 400, json: async () => ({ error: "no item x" }) }).postJson("/api/x", {}), /^Error: no item x$/);
  await assert.rejects(api({ ok: false, status: 502, json: async () => { throw new SyntaxError("html"); } }).postJson("/api/x", {}), /^Error: HTTP 502$/);
  same(await api({ ok: true, json: async () => ({ item: { id: "p1" } }) }).postJson("/api/x", {}), { item: { id: "p1" } });

  // A viewer loaded without this file stops with an error naming it.
  for (const name of ["archive.js", "gallery.js"]) {
    assert.throws(() => loadPage(path.join(WWW, "js", name), { ids: [], json: {} }), new RegExp(name.replace(".", "\\.") + " needs js/photo-viewer\\.js loaded before it"));
  }

  console.log("photo_viewer_test: ok");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
