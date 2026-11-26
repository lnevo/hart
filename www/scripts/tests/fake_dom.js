/* The small fake DOM the play-through tests run the games in (play_through_test.js, exam_run_test.js): just the
   elements the games read back (buttons, choices, the result box). One page per process: roots holds its elements. */
"use strict";
const VOID = new Set(["br", "hr", "img", "input", "line", "path", "circle", "rect", "meta", "link", "use"]);
class El {
  constructor(tag, attrs = {}) {
    this.tag = tag; this.attrs = attrs; this.id = attrs.id || ""; this.children = []; this.parent = null; this.hidden = false; this.disabled = false;
    this.cls = new Set((attrs.class || "").split(/\s+/).filter(Boolean)); this._inner = ""; this.textContent = ""; this.dataset = {}; this.onclick = null;
    for (const [k, v] of Object.entries(attrs)) if (k.startsWith("data-")) this.dataset[k.slice(5).replace(/-(\w)/g, (_, c) => c.toUpperCase())] = v;
    this.classList = { add: (...c) => c.forEach((x) => this.cls.add(x)), remove: (...c) => c.forEach((x) => this.cls.delete(x)), contains: (c) => this.cls.has(c) };
    this.style = {}; this.offsetWidth = 0; this.clientWidth = 0;
  }
  set innerHTML(h) { this._inner = String(h); this.children = []; parse(this, this._inner); }
  get innerHTML() { return this._inner; }
  appendChild(c) { c.parent = this; this.children.push(c); return c; }
  hasAttribute(a) { return a in this.attrs; }
  getAttribute(a) { return this.attrs[a] ?? null; }
  closest() { return null; }
  focus() {}
  getBoundingClientRect() { return (this.cls.has("result") ? rects.result : this.id === "xwGo" ? rects.go : null) || { top: 0, bottom: 0 }; }
  insertBefore(c) { return this.appendChild(c); }
  all() { const out = []; const walk = (e) => e.children.forEach((c) => { out.push(c); walk(c); }); walk(this); return out; }
  querySelectorAll(sel) { return select(this.all(), sel); }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
}
function parse(root, html) {
  const re = /<(\/?)([a-zA-Z][a-zA-Z0-9]*)((?:\s+[a-zA-Z-]+(?:="[^"]*"|='[^']*')?)*)\s*(\/?)>/g; // either quote
  let cur = root, m;
  while ((m = re.exec(html))) {
    const [, close, tag, attrText, selfClose] = m, t = tag.toLowerCase();
    if (close) { for (let e = cur; e && e !== root; e = e.parent) if (e.tag === t) { e._inner = html.slice(e._start, m.index); cur = e.parent; break; } continue; }
    const attrs = {};
    attrText.replace(/([a-zA-Z-]+)(?:="([^"]*)"|='([^']*)')?/g, (_, k, v, v1) => { attrs[k] = v ?? v1 ?? ""; });
    const el = new El(t, attrs); if ("disabled" in attrs) el.disabled = true;
    cur.appendChild(el); el._start = m.index + m[0].length;
    if (!selfClose && !VOID.has(t)) cur = el;
  }
}
/* one compound selector at a time: tag, #id, .class, [attr] */
function matches(e, sel) {
  const m = sel.match(/^([a-z0-9]*)(#[\w-]+)?((?:\.[\w-]+)*)(\[[\w-]+\])?$/);
  if (!m) throw new Error("fake DOM does not support the selector " + sel);
  if (m[1] && e.tag !== m[1]) return false;
  if (m[2] && e.id !== m[2].slice(1)) return false;
  if (m[3] && !m[3].slice(1).split(".").every((c) => e.cls.has(c))) return false;
  if (m[4] && !(m[4].slice(1, -1) in e.attrs)) return false;
  return true;
}
const select = (els, sel) => els.filter((e) => matches(e, sel));

const rects = {}; // the boxes a phone check gives to the result and the Continue button
const roots = [];
const mk = (id, attrs = {}) => { const e = new El("div", Object.assign({ id }, attrs)); roots.push(e); return e; };
const doc = {
  getElementById(id) { for (const r of roots) { if (r.id === id) return r; const f = r.all().find((e) => e.id === id); if (f) return f; } return null; },
  createElement(tag) { return new El(tag); },
  querySelectorAll(sel) { return roots.flatMap((r) => [r, ...r.all()]).filter((e) => matches(e, sel)); },
  addEventListener() {},
};

module.exports = { El, roots, rects, mk, doc };
