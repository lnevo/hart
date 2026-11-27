// A stub page for running one www/js viewer (archive.js, gallery.js, wiring.js) in node: nav.js and the viewer run in
// a vm against stub elements that keep what the script writes. Elements do not parse their HTML: querySelectorAll
// finds nothing and querySelector hands back one stub per selector, so a test drives the page through its URL, its
// stored view, its public API and the listeners on the named elements and the document.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const WWW = path.join(__dirname, "..", "..");

class StubEl {
  constructor(tag, id) {
    this.tagName = String(tag || "div").toUpperCase();
    this.id = id || "";
    this.innerHTML = "";
    this.textContent = "";
    this.value = "";
    this.hidden = false;
    this.className = "";
    this.style = {};
    this.attrs = {};
    this.listeners = {};
    this.found = {};
    this.children = [];
    const cls = new Set();
    this.classList = {
      add: (...c) => c.forEach((x) => cls.add(x)),
      remove: (...c) => c.forEach((x) => cls.delete(x)),
      contains: (c) => cls.has(c),
      toggle: (c, on) => ((on === undefined ? !cls.has(c) : on) ? cls.add(c) : cls.delete(c)),
      list: () => [...cls].sort(),
    };
  }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  removeAttribute(k) { delete this.attrs[k]; }
  appendChild(c) { this.children.push(c); return c; }
  querySelector(sel) { return (this.found[sel] = this.found[sel] || new StubEl("div", "")); }
  querySelectorAll() { return []; }
  closest() { return null; }
  focus() {}
  // What the script left on this element, for a snapshot.
  state() {
    const found = {};
    for (const [sel, e] of Object.entries(this.found)) found[sel] = e.state();
    return {
      innerHTML: this.innerHTML, textContent: this.textContent, value: this.value, hidden: this.hidden,
      className: this.className, classes: this.classList.list(), attrs: this.attrs,
      src: this.src, alt: this.alt, href: this.href, found,
    };
  }
}

// opts: ids (elements the page has), json ({rel: data} for HARTOps.loadJson), search, hash, stored (localStorage),
// localStorage (in place of the stub store), fetch (the fetch the viewer sees; default: every request fails), site
// (HARTOps.loadSite's answer).
function loadPage(script, opts) {
  const els = {};
  for (const id of opts.ids) els[id] = new StubEl("div", id);
  const created = [];
  const docListeners = {};
  const urls = [];
  const store = new Map(Object.entries(opts.stored || {}));
  const document = {
    title: "",
    activeElement: null,
    body: new StubEl("body", ""),
    getElementById: (id) => els[id] || null,
    getElementsByTagName: () => [],
    querySelector: (sel) => (sel.startsWith("#") ? els[sel.slice(1)] || null : null),
    querySelectorAll: () => [],
    createElement: (tag) => { const e = new StubEl(tag, ""); created.push(e); return e; },
    addEventListener: (type, fn) => { (docListeners[type] = docListeners[type] || []).push(fn); },
    contains: () => true,
  };
  const ctx = {
    document, console,
    location: { search: opts.search || "", hash: opts.hash || "", pathname: "/page/" },
    history: { replaceState: (_s, _t, url) => urls.push(url) },
    localStorage: opts.localStorage || { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)) },
    fetch: opts.fetch || (async () => { throw new Error("offline"); }),
    setTimeout: () => 0, clearTimeout: () => {}, scrollTo: () => {}, URLSearchParams, Promise,
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(WWW, "js", "nav.js"), "utf8"), ctx, { filename: "nav.js" });
  Object.assign(ctx.HARTOps, {
    base: () => "../",
    loadJson: async (rel) => {
      if (!(rel in opts.json)) throw new Error("no stub data for " + rel);
      return JSON.parse(JSON.stringify(opts.json[rel]));
    },
    loadSite: async () => opts.site || { public: true },
  });
  vm.runInContext(fs.readFileSync(script, "utf8"), ctx, { filename: path.basename(script) });
  const fire = (type, e) => (docListeners[type] || []).forEach((fn) => fn(Object.assign({ preventDefault() {}, stopPropagation() {} }, e)));
  const snapshot = () => {
    const out = { title: document.title, urls: urls.slice(), stored: Object.fromEntries(store), els: {}, created: [] };
    for (const [id, e] of Object.entries(els)) out.els[id] = e.state();
    for (const e of created) out.created.push(e.state());
    return out;
  };
  return { ctx, els, created, fire, snapshot, urls, store };
}

// Read a JSON file under www/.
const wwwJson = (rel) => JSON.parse(fs.readFileSync(path.join(WWW, rel), "utf8"));

// deepStrictEqual for values made inside the page's vm, compared as plain JSON (their arrays and objects come from
// another realm, so they are never reference-equal in shape to the test's own).
const same = (actual, expected, msg) => assert.deepStrictEqual(JSON.parse(JSON.stringify(actual)), expected, msg);

module.exports = { StubEl, loadPage, same, wwwJson, WWW };
