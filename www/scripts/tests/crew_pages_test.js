// The session paperwork pages, www/js/crew.js, drawn from the real data/crew.json in a stub page (run: node
// crew_pages_test.js). Every page the site has renders, a sheet shows the job's own colours bright, the public site
// hides the source buttons, and a value from the data is escaped. renderAll() is also what a refactor of crew.js is
// compared with: `node crew_pages_test.js --dump other/crew.js` prints every page it draws as JSON.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const WWW = path.join(__dirname, "..", "..");
const CREW_JSON = JSON.parse(fs.readFileSync(path.join(WWW, "data", "crew.json"), "utf8"));

// The HARTCrew.page(kind, id) call of every crew page in www/, from the pages themselves.
function sitePages() {
  const out = [];
  const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).forEach((e) => {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p);
    else if (e.name.endsWith(".html")) {
      for (const m of fs.readFileSync(p, "utf8").matchAll(/HARTCrew\.page\("([\w-]+)", "([\w-]*)"\)/g)) {
        out.push({ page: path.relative(WWW, p), kind: m[1], id: m[2] });
      }
    }
  });
  walk(path.join(WWW, "crew"));
  return out.sort((a, b) => a.page.localeCompare(b.page));
}

// A stub element: it keeps what crew.js writes (innerHTML, textContent, inserted crumbs) and finds no children.
function stubEl(id) {
  return {
    id, innerHTML: "", textContent: "", inserted: [], hidden: false,
    insertAdjacentHTML(_where, html) { this.inserted.push(html); },
    querySelectorAll() { return []; },
    querySelector() { return null; },
    addEventListener() {},
  };
}

// One page drawn by the crew.js at crewPath: what it wrote into each element, and the document title.
async function render(crewPath, kind, id, opts = {}) {
  const els = {};
  for (const name of ["crew-root", "sheet-head", "page-title", "page-pub", "page-lede"]) els[name] = stubEl(name);
  const crumb = stubEl("crumb");
  const errors = [];
  const store = new Map();
  const document = {
    title: "",
    documentElement: { classList: { add() {}, remove() {} } },
    getElementById: (n) => els[n] || null,
    getElementsByTagName: () => [],
    querySelector: (sel) => (sel === "main .page-head .crumb ol" ? crumb : null),
    querySelectorAll: () => [],
    createElement: () => stubEl(""),
    addEventListener() {},
    body: { appendChild() {} },
  };
  const ctx = {
    document, console: { error: (e) => errors.push(String(e && e.message || e)) },
    location: { hash: "", pathname: "/", search: "" }, history: { replaceState() {} },
    localStorage: opts.localStorage || { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) },
    setTimeout, Promise, JSON, Math, Array, Number, String, Error, encodeURI, decodeURIComponent,
  };
  ctx.window = ctx;
  ctx.window.addEventListener = () => {};
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(WWW, "js", "nav.js"), "utf8"), ctx, { filename: "nav.js" });
  Object.assign(ctx.HARTOps, {
    base: () => "../../",
    mountChrome: async () => ({ public: !!opts.public }),
    loadJson: async (rel) => {
      assert.strictEqual(rel, "data/crew.json");
      if (opts.fail) throw new Error("data/crew.json 404");
      return JSON.parse(JSON.stringify(opts.data || CREW_JSON));
    },
    renderError: (el, o) => {
      el.innerHTML = "LOAD ERROR: " + (o.err && o.err.message);
      if (opts.keep) opts.keep.links = (o.links || []).map((l) => l.href);
    },
  });
  vm.runInContext(fs.readFileSync(crewPath, "utf8"), ctx, { filename: path.basename(crewPath) });
  if (opts.keep) opts.keep.ctx = ctx; // a test that calls HARTCrew.lib after the page is drawn
  await ctx.HARTCrew.page(kind, id);
  const wrote = {};
  for (const [n, e] of Object.entries(els)) if (e.innerHTML || e.textContent) wrote[n] = e.innerHTML || e.textContent;
  return { title: document.title, crumbs: crumb.inserted, wrote, errors };
}

// Every site page, on the local desk and on the public site.
async function renderAll(crewPath) {
  const out = {};
  for (const p of sitePages()) {
    for (const pub of [false, true]) out[p.page + (pub ? " (public)" : "")] = await render(crewPath, p.kind, p.id, { public: pub });
  }
  return out;
}

const CREW_JS = path.join(WWW, "js", "crew.js");

async function main() {
  const pages = sitePages();
  assert.ok(pages.length >= 20, "found only " + pages.length + " crew pages");

  // Every page renders without a load error.
  const all = await renderAll(CREW_JS);
  for (const [page, r] of Object.entries(all)) {
    assert.deepStrictEqual(r.errors, [], page);
    assert.ok(r.wrote["crew-root"] && !r.wrote["crew-root"].startsWith("LOAD ERROR"), page + " drew nothing");
  }

  // A sheet: its title, and its own colours bright with the rest dimmed (or every colour when the job has them all).
  const job = CREW_JSON.jobs.find((j) => j.colors && j.colors.length && j.colors.length < CREW_JSON.colors.length);
  const sheet = await render(CREW_JS, "sheet", job.id);
  assert.strictEqual(sheet.title, job.code + " " + job.name + " — HART");
  const mine = (sheet.wrote["crew-root"].match(/class="is-mine"/g) || []).length;
  const other = (sheet.wrote["crew-root"].match(/class="is-other"/g) || []).length;
  assert.deepStrictEqual([mine, mine + other], [job.colors.length, CREW_JSON.colors.length]);

  // The source buttons are for the local desk only.
  const tt = CREW_JSON.timetable;
  assert.ok(tt.source, "TT-23 has a source file");
  assert.match((await render(CREW_JS, "tt23", "")).wrote["crew-root"], /Source pptx/);
  assert.doesNotMatch((await render(CREW_JS, "tt23", "", { public: true })).wrote["crew-root"], /Source pptx/);

  // The archive map page says it is the archive and links to the current map.
  const arch = await render(CREW_JS, "map-archive", CREW_JSON.maps[0].id);
  assert.match(arch.title, /^Archive: /);
  assert.strictEqual(arch.crumbs.length, 3);

  // A value from the data is escaped.
  const data = JSON.parse(JSON.stringify(CREW_JSON));
  data.timetable.note = '<b>"x"</b> & y';
  assert.match((await render(CREW_JS, "tt23", "", { data })).wrote["crew-root"], /&lt;b&gt;&quot;x&quot;&lt;\/b&gt; &amp; y/);

  // An unknown job or map is the page's load error, naming it.
  const lost = await render(CREW_JS, "sheet", "no-such-job");
  assert.strictEqual(lost.wrote["crew-root"], "LOAD ERROR: No job no-such-job");
  assert.deepStrictEqual(lost.errors, ["No job no-such-job"]);

  // crew.json that does not load: the load error links the schematic PDF, which opens without it.
  const failed = {};
  const gone = await render(CREW_JS, "sheet", job.id, { fail: true, keep: failed });
  assert.strictEqual(gone.wrote["crew-root"], "LOAD ERROR: data/crew.json 404");
  assert.ok(failed.links.includes("crew/maps/schematic/system-schematic.pdf"), failed.links.join(", "));

  // The step ticks: kept per job, and a browser with no storage (it throws) starts clear and keeps drawing.
  const kept = {};
  await render(CREW_JS, "sheet", job.id, { keep: kept });
  const lib = kept.ctx.HARTCrew.lib;
  lib.writeTicks(job, [true, false, true]);
  assert.deepStrictEqual(Array.from(lib.readTicks(job)), [true, false, true]);
  const noStore = { getItem() { throw new Error("denied"); }, setItem() { throw new Error("denied"); } };
  const closed = {};
  const blocked = await render(CREW_JS, "sheet", job.id, { keep: closed, localStorage: noStore });
  assert.deepStrictEqual(blocked.errors, []);
  assert.match(blocked.wrote["crew-root"], /data-step="0"/);
  assert.deepStrictEqual(Array.from(closed.ctx.HARTCrew.lib.readTicks(job)), []);
  closed.ctx.HARTCrew.lib.writeTicks(job, [true]); // does not throw

  // The map viewer's zoom: 1 to 6, about the stage centre when no point is given, and back to fit on reset.
  assert.deepStrictEqual([lib.clampScale(0.2), lib.clampScale(2.5), lib.clampScale(10)], [1, 2.5, 6]);
  const stage = { scrollLeft: 0, scrollTop: 0, getBoundingClientRect: () => ({ width: 400, height: 300, left: 0, top: 0 }) };
  const img = { style: { width: "100%" } };
  Object.defineProperty(img, "offsetWidth", { get: () => (parseFloat(img.style.width) / 100) * 400 });
  Object.defineProperty(img, "offsetHeight", { get: () => (parseFloat(img.style.width) / 100) * 300 });
  const zoom = lib.stageZoom(stage, img);
  zoom.set(2);
  assert.deepStrictEqual([zoom.scale(), img.style.width, stage.scrollLeft, stage.scrollTop], [2, "200%", 200, 150]);
  zoom.set(100, 0, 0);
  assert.deepStrictEqual([zoom.scale(), stage.scrollLeft, stage.scrollTop], [6, 600, 450]);
  zoom.reset();
  assert.deepStrictEqual([zoom.scale(), img.style.width, stage.scrollLeft, stage.scrollTop], [1, "100%", 0, 0]);

  console.log("crew pages: " + Object.keys(all).length + " renders OK");
}

if (require.main === module) {
  const i = process.argv.indexOf("--dump");
  if (i !== -1) renderAll(path.resolve(process.argv[i + 1])).then((o) => console.log(JSON.stringify(o, null, 1)));
  else main().catch((e) => { console.error(e); process.exit(1); });
}

module.exports = { render, renderAll, sitePages };
