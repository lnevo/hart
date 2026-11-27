#!/usr/bin/env node
/* Builds www/exam/answers.html, the answer key for the Extra East game, from the ask({...}) calls in the game's scripts
   (www/exam/run.js and the run files). The calls are read as object literals, never run: a name the game fills in at
   play time (station, train, clock time) shows as [station], [train] or […]. The reference panels come from the game's
   data module (exam/run-data.js: STATIONS, REGULARS, TIME_ORDER, SHEET_NOTES, TWC_PLAN), which run.html loads too, and
   the track warrant form (js/track-warrant.js). `--check` exits 1 when answers.html is out of date. */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
/* The section and source names, and the source labels, the game shows (js/game-engine.js). */
const ENGINE = require(path.join(__dirname, "..", "js", "game-engine.js"));

const EXAM = path.join(__dirname, "..", "exam");
/* The game's tables, the same object run.html loads before run.js. */
const DATA = require(path.join(EXAM, "run-data.js"));
/* The game's scripts in run.html's order, each with the run its questions belong to. A question in one of the event
   pools (POOLS) takes the pool's place instead. */
const RUN_FILES = { "run.js": "1949 run", "run-1949.js": "1949 run", "run-modern.js": "Modern run", "run-signals.js": "Signals run", "run-yard.js": "Yard job" };
/* The scripts as [{file, where, src}]. */
const readRun = () => Object.entries(RUN_FILES).map(([file, where]) => ({ file, where, src: fs.readFileSync(path.join(EXAM, file), "utf8") }));
const OUT = path.join(EXAM, "answers.html");
const TRACK_WARRANT = path.join(EXAM, "..", "js", "track-warrant.js");

/* "run-modern.js line 12": where index `at` falls in a script. */
const lineOf = (f, at) => `${f.file} line ${f.src.slice(0, at).split("\n").length}`;

/* ---------- reading the ask({...}) calls as data ---------- */
/* The tokens of script f from index i: strings and templates come cooked, comments and regex literals are skipped. With
   `until` null, src[i] is an opening bracket and the tokens run through the one that closes it; with `until` "}", they
   run up to an unmatched "}" (the end of a template's ${...}). Returns {toks, end}, end the closing bracket's index.
   A token is {t: "str"|"num"|"name"|"punct"|"tpl"|"re", v, at}; a template's is {t: "tpl", quasis, exprs, at}, exprs
   holding each ${...} as its own tokens. */
const OPEN = { "{": "}", "[": "]", "(": ")" };
const PUNCT = ["...", "===", "!==", "=>", "==", "!=", "<=", ">=", "&&", "||", "??", "?.", "++", "--", "+=", "-=", "*=", "/="];
const REGEX_AFTER = new Set(["return", "typeof", "case", "in", "of", "new", "delete", "void", "throw", "else", "do", "instanceof"]);
const NUMBER = /0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?/y;
const NAME = /[A-Za-z_$][\w$]*/y;
function lex(f, i, until) {
  const src = f.src, start = i, toks = [], stack = [];
  const regexMayStart = () => {
    const p = toks[toks.length - 1];
    return !p || (p.t === "punct" && !")]}".includes(p.v) && p.v !== "++" && p.v !== "--") || (p.t === "name" && REGEX_AFTER.has(p.v));
  };
  const sticky = (re) => { re.lastIndex = i; return re.exec(src)[0]; };
  while (i < src.length) {
    const c = src[i], two = src.slice(i, i + 2);
    if (/\s/.test(c)) { i++; continue; }
    if (two === "//") { const e = src.indexOf("\n", i); i = e < 0 ? src.length : e; continue; }
    if (two === "/*") {
      const e = src.indexOf("*/", i + 2);
      if (e < 0) throw new Error(`${lineOf(f, i)}: comment not closed`);
      i = e + 2; continue;
    }
    if (c === '"' || c === "'") { const s = readString(f, i); toks.push({ t: "str", v: s.v, at: i }); i = s.end + 1; continue; }
    if (c === "`") { const s = readTemplate(f, i); toks.push({ t: "tpl", quasis: s.quasis, exprs: s.exprs, at: i }); i = s.end + 1; continue; }
    if (/\d/.test(c) || (c === "." && /\d/.test(src[i + 1]))) { const m = sticky(NUMBER); toks.push({ t: "num", v: Number(m), at: i }); i += m.length; continue; }
    if (/[A-Za-z_$]/.test(c)) { const m = sticky(NAME); toks.push({ t: "name", v: m, at: i }); i += m.length; continue; }
    if (c === "/" && regexMayStart()) { toks.push({ t: "re", at: i }); i = regexEnd(f, i); continue; }
    const p = PUNCT.find(x => src.startsWith(x, i)) || c;
    if (OPEN[p]) stack.push(OPEN[p]);
    else if ("}])".includes(p)) {
      if (!stack.length && p === until) return { toks, end: i };
      if (stack.pop() !== p) throw new Error(`${lineOf(f, i)}: unbalanced ${p}`);
    }
    toks.push({ t: "punct", v: p, at: i });
    i += p.length;
    if (until === null && !stack.length) return { toks, end: i - 1 };
  }
  throw new Error(`${lineOf(f, start)}: no closing bracket`);
}

/* A string or template's text with its escapes applied, as JavaScript reads them. */
const ESCAPES = { n: "\n", t: "\t", r: "\r", b: "\b", f: "\f", v: "\v", 0: "\0", "\n": "", "\r\n": "" };
const cook = raw => raw.replace(/\\(u\{[0-9a-fA-F]+\}|u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|\r\n|[\s\S])/g, (_, e) =>
  e[0] === "u" && e.length > 1 ? String.fromCodePoint(parseInt(e.replace(/[u{}]/g, ""), 16))
    : e[0] === "x" && e.length === 3 ? String.fromCharCode(parseInt(e.slice(1), 16))
      : e in ESCAPES ? ESCAPES[e] : e);

/* The quoted string at i: {v, end}, end the closing quote's index. */
function readString(f, i) {
  const q = f.src[i];
  for (let j = i + 1; j < f.src.length; j++) {
    const c = f.src[j];
    if (c === "\\") { j++; continue; }
    if (c === "\n") break;
    if (c === q) return { v: cook(f.src.slice(i + 1, j)), end: j };
  }
  throw new Error(`${lineOf(f, i)}: string not closed`);
}

/* The template at i: {quasis, exprs, end}, its text pieces cooked and each ${...} as tokens. */
function readTemplate(f, i) {
  const quasis = [], exprs = [];
  let from = i + 1;
  for (let j = i + 1; j < f.src.length; j++) {
    const c = f.src[j];
    if (c === "\\") { j++; continue; }
    if (c === "`") { quasis.push(cook(f.src.slice(from, j))); return { quasis, exprs, end: j }; }
    if (c === "$" && f.src[j + 1] === "{") {
      quasis.push(cook(f.src.slice(from, j)));
      const r = lex(f, j + 2, "}");
      exprs.push(r.toks);
      j = r.end;
      from = j + 1;
    }
  }
  throw new Error(`${lineOf(f, i)}: template not closed`);
}

/* The index after the regex literal at i (its flags included). */
function regexEnd(f, i) {
  let inClass = false;
  for (let j = i + 1; j < f.src.length; j++) {
    const c = f.src[j];
    if (c === "\\") { j++; continue; }
    if (c === "\n") break;
    if (c === "[") inClass = true;
    else if (c === "]") inClass = false;
    else if (c === "/" && !inClass) { j++; while (/[a-z]/.test(f.src[j] || "")) j++; return j; }
  }
  throw new Error(`${lineOf(f, i)}: regex not closed`);
}

/* A name the game fills in at play time. It prints as [name]; a property of it or a call on it is one too. */
class Slot {
  constructor(name) { this.name = name; }
  [Symbol.toPrimitive]() { return `[${this.name}]`; }
}
/* The names a question may use for real: the figures it may show under its text, and Math. */
const REAL = { semSvg: DATA.semSvg, Math };
/* Math.random is left out: a question drawn at random would make the key differ from build to build. */
const RUNS_FOR_REAL = new Set([DATA.semSvg, ...Object.getOwnPropertyNames(Math).filter(k => k !== "random").map(k => Math[k]).filter(v => typeof v === "function")]);
const LITERALS = { true: true, false: false, null: null, undefined };

/* Reads one value from tokens: strings, numbers, templates, arrays, objects, + and unary -, and names with their
   properties and calls. A name not in REAL is a Slot. Anything else (a function, an operator other than +) stops the
   build: the key shows what the game shows, so a shown field must be readable as data. */
class Reader {
  constructor(f, toks) { this.f = f; this.toks = toks; this.i = 0; }
  fail(msg) {
    const t = this.toks[Math.min(this.i, this.toks.length - 1)];
    throw new Error(t ? `${lineOf(this.f, t.at)}: ${msg}` : msg);
  }
  is(v) { const t = this.toks[this.i]; return !!t && t.t === "punct" && t.v === v; }
  take(v) { if (!this.is(v)) this.fail(`expected ${v}`); this.i++; }
  /* The whole token list as one value. */
  all() {
    if (!this.toks.length) this.fail("no value");
    const v = this.value();
    if (this.i < this.toks.length) this.fail(`cannot read ${this.describe()}`);
    return v;
  }
  describe() { const t = this.toks[this.i]; return t.t === "punct" || t.t === "name" ? `"${t.v}"` : `a ${t.t}`; }
  value() {
    let v = this.unary();
    while (this.is("+")) { this.i++; v = v + this.unary(); }
    return v;
  }
  unary() {
    if (this.is("-")) { this.i++; return -this.unary(); }
    let v = this.primary();
    for (;;) {
      if (this.is(".")) {
        this.i++;
        const t = this.toks[this.i++];
        if (!t || t.t !== "name") this.fail("expected a name after .");
        v = this.member(v, t.v);
      } else if (this.is("[")) {
        this.i++;
        const k = this.value();
        this.take("]");
        v = this.member(v, k);
      } else if (this.is("(")) {
        this.i++;
        const args = this.list(")");
        v = this.call(v, args);
      } else return v;
    }
  }
  /* Values up to `close`, comma separated, a trailing comma allowed. */
  list(close) {
    const out = [];
    while (!this.is(close)) {
      out.push(this.value());
      if (!this.is(close)) this.take(",");
    }
    this.i++;
    return out;
  }
  member(v, k) {
    if (v instanceof Slot) return new Slot(`${v.name}.${String(k)}`);
    if (v === Math && typeof Math[k] === "function") return Math[k];
    return this.fail(`cannot read .${String(k)} of a value written in the question`);
  }
  call(fn, args) {
    if (fn instanceof Slot) return `[${fn.name}(…)]`;
    if (RUNS_FOR_REAL.has(fn)) return fn(...args);
    if (fn === Math.random) return this.fail("calls Math.random, which the key does not run");
    return this.fail("calls a function the key does not run");
  }
  primary() {
    const t = this.toks[this.i++];
    if (!t) return this.fail("value missing");
    if (t.t === "str" || t.t === "num") return t.v;
    if (t.t === "tpl") return t.quasis.reduce((s, q, k) => s + q + (k < t.exprs.length ? String(new Reader(this.f, t.exprs[k]).all()) : ""), "");
    if (t.t === "name") {
      if (this.is("=>")) this.fail("a function");
      if (Object.hasOwn(LITERALS, t.v)) return LITERALS[t.v];
      if (Object.hasOwn(REAL, t.v)) return REAL[t.v];
      if (t.v in globalThis) this.fail(`uses ${t.v}, which the key does not run`);
      return new Slot(t.v);
    }
    if (t.t === "punct" && t.v === "(") {
      if (this.is(")")) this.fail("a function"); // ()=>
      const v = this.value();
      this.take(")");
      if (this.is("=>")) this.fail("a function");
      return v;
    }
    if (t.t === "punct" && t.v === "[") return this.list("]");
    if (t.t === "punct" && t.v === "{") return this.object();
    this.i--;
    return this.fail(`cannot read ${this.describe()}`);
  }
  object() {
    const o = {};
    while (!this.is("}")) {
      const k = this.toks[this.i++];
      if (!k || !["name", "str", "num"].includes(k.t)) { this.i--; this.fail("expected a property name"); }
      if (this.is(":")) { this.i++; o[k.v] = this.value(); } else if (k.t === "name") { this.i--; o[k.v] = this.primary(); } else this.fail("expected :");
      if (!this.is("}")) this.take(",");
    }
    this.i++;
    return o;
  }
}

/* The top-level properties of an object literal's tokens ("{" … "}"), as [{key, toks, at}], toks the value's tokens
   unread (a shorthand property's are its name). A getter, get body(){return …}, gives the tokens of what it returns.
   A property appears once. */
const isPunct = (t, v) => !!t && t.t === "punct" && t.v === v;
function properties(f, toks) {
  const props = [];
  const last = toks.length - 1;
  for (let i = 1; i < last;) {
    const getter = toks[i].t === "name" && toks[i].v === "get" && !!toks[i + 1] && toks[i + 1].t === "name" && isPunct(toks[i + 2], "(");
    if (getter) i++;
    const k = toks[i];
    if (!["name", "str", "num"].includes(k.t)) throw new Error(`${lineOf(f, k.at)}: cannot read a property name here (a spread or a computed key)`);
    const key = String(k.v);
    if (props.some(p => p.key === key)) throw new Error(`${lineOf(f, k.at)}: ${key} is set twice`);
    const colon = isPunct(toks[i + 1], ":");
    let j = i + 1, depth = 0;
    for (; j < last; j++) {
      const v = toks[j].t === "punct" ? toks[j].v : "";
      if (depth === 0 && v === ",") break;
      if (OPEN[v]) depth++;
      else if (v && "}])".includes(v)) depth--;
    }
    props.push({ key, toks: getter ? returned(f, toks.slice(i + 1, j)) : toks.slice(colon ? i + 2 : i, j), at: k.at });
    i = j + 1;
  }
  return props;
}
/* A getter's tokens "( ) { return … }", a ; after the value allowed: the tokens of the value it returns. */
function returned(f, toks) {
  const end = toks.length - (isPunct(toks[toks.length - 2], ";") ? 2 : 1);
  const ok = isPunct(toks[0], "(") && isPunct(toks[1], ")") && isPunct(toks[2], "{") && !!toks[3] && toks[3].t === "name" &&
    toks[3].v === "return" && isPunct(toks[toks.length - 1], "}") && end > 4;
  if (!ok) throw new Error(`${lineOf(f, toks[0].at)}: a getter that does more than return one value`);
  return toks.slice(4, end);
}
/* True when the tokens choose between values at play time: ?, &&, || (or ?? and ?.), also inside a template. */
const CHOICE = new Set(["?", "&&", "||", "??", "?."]);
const choosesAtPlayTime = toks => toks.some(t => (t.t === "punct" && CHOICE.has(t.v)) || (t.t === "tpl" && t.exprs.some(choosesAtPlayTime)));
const FRIENDLY = [
  [/\[STATIONS\.\[?\w+\]?\.n\]/g, "[station]"],
  [/\[(?:p|time|o|f)\.tr\.name\]/g, "[train]"],
  [/\[(?:shown|nums)\.join\(…\)\]/g, "[order numbers]"],
  [/\[time\.no\]/g, "[order no]"],
  [/\[esc\(…\)\]/g, "[order text]"],
  [/\[fmt\(…\)\]/g, "[time]"],
  [/NaN|\[time\.L\]/g, "[n]"],
  // Any other stub: it has a dot or a call in it, which the friendly names above do not.
  [/\[\w+(?:\.[\w\[\]]+)*(?:\(…\))?\]/g, m => (/[.(]/.test(m) ? "[…]" : m)],
];
const friendly = s => FRIENDLY.reduce((t, [re, to]) => t.replace(re, to), String(s));
const { esc, srcLabel } = ENGINE;
const text = v => (v == null ? "" : friendly(v));
const ENT = { "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&nbsp;": " " };
const plain = s => s.replace(/<[^>]+>/g, " ").replace(/&(?:amp|lt|gt|quot|#39|nbsp);/g, e => ENT[e]).replace(/\s+/g, " ");


/* Where in the game a question is asked: inside one of the event pools, or fixed in a scene. */
const POOLS = { ROAD_TTO: "1949 run, on the road", STN_TTO: "1949 run, at a station", ROAD_TWC: "Modern run, on the road" };
/* Each pool's script and the span of its array there; each pool is declared in exactly one script. */
function poolRanges(files) {
  return Object.keys(POOLS).map(name => {
    const decl = `const ${name}=[`;
    const hits = files.filter(f => f.src.includes(decl));
    if (hits.length !== 1) throw new Error(`pool ${name} is declared in ${hits.length} scripts, not one`);
    const f = hits[0];
    const open = f.src.indexOf(decl) + decl.length - 1;
    return { name, file: f.file, from: open, to: lex(f, open, null).end };
  });
}

/* Fields the key shows. Others (ok, okText, note, after, miss) only matter during a run. */
const SHOWN = ["sec", "src", "title", "body", "right", "wrong", "why", "extra", "ref"];

/* The ask({...}) calls in script f, as [{at, props}]: the call's index and its object's top-level properties. */
function asks(f) {
  const out = [];
  const re = /\bask\(\{/g;
  let m;
  while ((m = re.exec(f.src))) out.push({ at: m.index, props: properties(f, lex(f, m.index + 4, null).toks) });
  return out;
}

/* The shown fields of one call, read as data: {key: value}. */
function shownFields(f, call) {
  const at = lineOf(f, call.at);
  const shown = call.props.filter(p => SHOWN.includes(p.key));
  // A shown field chosen at play time would show one branch as the only answer.
  const chosen = shown.filter(p => choosesAtPlayTime(p.toks)).map(p => p.key);
  if (chosen.length) throw new Error(`${at}: ${chosen.join(", ")} chosen at play time (?, && or ||); write one ask per case, or put a situational sentence in note`);
  const o = {};
  for (const p of shown) {
    try {
      o[p.key] = new Reader(f, p.toks).all();
    } catch (e) {
      throw new Error(`${at}: cannot read question's ${p.key} (${e.message})`, { cause: e });
    }
  }
  return o;
}

/* One question as the key shows it, from the call `call` in script f. */
function question(f, call, where) {
  const at = lineOf(f, call.at);
  const o = shownFields(f, call);
  if (o.extra && /\[\w/.test(String(o.extra))) throw new Error(`${at}: the figure under the question uses play-time values the key cannot draw`);
  for (const k of ["title", "body", "right", "why"]) if (!o[k]) throw new Error(`${at}: question has no ${k}`);
  if (!Array.isArray(o.wrong) || !o.wrong.length) throw new Error(`${at}: question has no wrong answers`);
  if (o.wrong.some(w => !Array.isArray(w) || !w[0])) throw new Error(`${at}: a wrong answer is not [text, effect, why]`);
  return {
    file: f.file, line: f.src.slice(0, call.at).split("\n").length, sec: o.sec, src: text(srcLabel(String(o.src || ""))),
    extra: o.extra ? String(o.extra) : "", title: text(o.title), body: text(o.body), right: text(o.right),
    wrong: o.wrong.map(w => ({ t: text(w[0]), why: text(w[2] || "") })),
    ref: o.ref ? String(o.ref) : "", why: text(o.why), where,
  };
}

/* Every question in the scripts (readRun()'s list), in order. qs.generated counts the calls drawn at a signal, which
   the key lists from signals.js instead (generatedHtml). */
function extract(files) {
  const pools = poolRanges(files);
  const qs = [];
  let generated = 0;
  for (const f of files) {
    if (!f.where) throw new Error(`${f.file}: no run named for its questions`);
    for (const call of asks(f)) {
      if (call.props.some(p => p.key === "gen")) { generated++; continue; } // gen:"speed", "route" or "plate"
      const pool = pools.find(p => p.file === f.file && call.at > p.from && call.at < p.to);
      qs.push(question(f, call, pool ? POOLS[pool.name] : f.where));
    }
  }
  qs.generated = generated;
  return qs;
}


/* signals.js, the tables the signals runs draw from (shared with the study deck), loaded in a sandbox. */
function loadSignals() {
  const file = path.join(EXAM, "signals.js");
  const ctx = {};
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(file, "utf8") + ";this.SIG={ASPECTS,ROUTE,PLATES,sigFig,lightFig,armWords,lampWords,plateWrongs,routeWhy};", ctx);
  const SIG = ctx.SIG;
  if (!SIG.ASPECTS.length || !SIG.ROUTE.length || !Object.keys(SIG.PLATES).length) throw new Error("signals.js: a table is empty");
  return SIG;
}

/* The questions the signals runs draw at each signal: every speed aspect, route indication and plate, with the
   choices the game can offer. */
function generatedHtml(SIG) {
  const byR = Object.fromEntries(SIG.ASPECTS.map(a => [a.r, a]));
  const card = (meta, title, body, fig, right, wrongs, why) => {
    const opts = [{ t: right, ok: true }, ...wrongs.map(t => ({ t }))].sort((a, b) => a.t.localeCompare(b.t));
    const search = plain([title, body, right, why, meta, ...wrongs].join(" ")).toLowerCase();
    return `<article class="xa-q" data-s="${esc(search)}">
  <p class="xa-meta">${esc(meta)}</p>
  <h3>${esc(title)}</h3>
  <p>${esc(body)}</p>
  <div class="xa-fig">${fig}</div>
  <ul class="xa-opts">${opts.map(o => `<li${o.ok ? ' class="ok"' : ""}>${esc(o.t)}</li>`).join("")}</ul>
  <p class="xa-why">${esc(why)}</p>
</article>`;
  };
  const speed = SIG.ASPECTS.map(a => card(`Speed signals · 1949 Standard Code · Rule ${a.r}`, `Rule ${a.r}`, `Arms top to bottom: ${SIG.armWords(a.arms)}. What does it indicate?`,
    SIG.sigFig(a.arms), a.ind, a.w.map(r => byR[r].ind), `Rule ${a.r}, ${a.name}: ${a.ind}.`));
  const inds = [...new Set(SIG.ROUTE.map(r => r.ind))];
  const route = SIG.ROUTE.filter((r, i, all) => all.findIndex(x => x.heads === r.heads) === i).map(r => card(`Route signals · Signals guide · chart`, r.name,
    `${SIG.lampWords(r.heads)}. What does it tell you?`, SIG.lightFig(r.heads, ""), r.ind, inds.filter(t => t !== r.ind), SIG.routeWhy(r)));
  // the plates the game draws (it never draws a signal with no plate)
  const plates = Object.entries(SIG.PLATES).filter(([k]) => k !== "none").map(([k, p]) => card(`Both signals runs · Signals guide · signage`, `${p.name} at Stop`,
    `The signal shows Stop and carries ${p.with}. What do you do?`, SIG.lightFig("R", k), p.act, SIG.plateWrongs(k).map(w => w.t), p.note));
  const n = speed.length + route.length + plates.length;
  return { n, html: `<section class="xa-sec" id="signals"><h2>Signals run: at each signal <small>${n}</small></h2>
<p class="xa-gen">On the signals runs each signal is drawn from these tables, which the study deck also uses. The game offers three of the wrong choices listed for a route signal or a plate.</p>
<h3 class="xa-sub">Speed semaphores (1949)</h3>
${speed.join("\n")}
<h3 class="xa-sub">Route signals (modern)</h3>
${route.join("\n")}
<h3 class="xa-sub">At a Stop: the plates</h3>
${plates.join("\n")}
</section>` };
}


/* ---------- references: what the game shows on its train sheet or warrant form, for questions that need it ---------- */
/* A question names one with ref:"<id>"; the game ignores the field. Each is drawn from the game's data (run-data.js). */

/* The data module's tables the references read, checked before any is used. */
function checkData(D) {
  const bad = [];
  if (!Array.isArray(D.STATIONS) || !D.STATIONS.length || D.STATIONS.some(s => typeof s.n !== "string" || typeof s.mp !== "number"))
    bad.push("STATIONS is not a list of stations with n and mp");
  if (!Array.isArray(D.REGULARS) || !D.REGULARS.length) bad.push("REGULARS is not a list of trains");
  if (!D.TIME_ORDER || typeof D.TIME_ORDER !== "object") bad.push("TIME_ORDER is missing");
  if (!D.TWC_PLAN || typeof D.TWC_PLAN.box5Lead !== "number" || !D.TWC_PLAN.warrants) bad.push("TWC_PLAN has no box5Lead or warrants");
  if (typeof D.semSvg !== "function") bad.push("semSvg is not a function");
  if (bad.length) throw new Error(`run-data.js: ${bad.join("; ")}`);
  return D;
}

/* The special instructions on the 1949 train sheet, as list items: SHEET_NOTES.tto, which renderSheet prints. */
function specialInstructions(SHEET_NOTES) {
  if (!SHEET_NOTES || typeof SHEET_NOTES !== "object") throw new Error("run-data.js: no SHEET_NOTES");
  const notes = SHEET_NOTES.tto;
  if (!Array.isArray(notes) || !notes.length || notes.some(t => typeof t !== "string" || !t))
    throw new Error("run-data.js: SHEET_NOTES.tto is not a list of special instructions");
  return notes.map(t => `<li>${t}</li>`).join("");
}

/* A warrant of the modern run's TWC_PLAN as the key shows it: {no, at, boxes: {n: {vals, some}}}.
   A box that is null in the plan is set at play time and shows as its slot, such as [time]; a box of a draw is on the
   warrant in some runs only. A box may appear only once across the boxes and the draws. */
function warrant(plan, name) {
  const w = plan.warrants && plan.warrants[name];
  if (!w || !w.no || !w.boxes) throw new Error(`run-data.js: TWC_PLAN has no warrant ${name} with a no and boxes`);
  const boxes = {};
  const put = (n, vals, some) => {
    if (boxes[n]) throw new Error(`run-data.js: warrant ${w.no} sets box ${n} twice`);
    if (vals !== null && !Array.isArray(vals)) throw new Error(`run-data.js: warrant ${w.no} box ${n} is not a list or null`);
    boxes[n] = { vals, some };
  };
  for (const [n, vals] of Object.entries(w.boxes)) put(n, vals, false);
  for (const [draw, sets] of Object.entries(w.draws || {})) {
    if (!Array.isArray(sets) || sets.length !== 2) throw new Error(`run-data.js: warrant ${w.no} draw ${draw} is not a pair of box sets`);
    for (const set of sets) for (const [n, vals] of Object.entries(set)) put(n, vals, true);
  }
  return { no: w.no, at: w.at, boxes };
}

function warrantHtml(w, BOXES) {
  const words = Object.fromEntries(BOXES);
  const rows = Object.keys(w.boxes).map(Number).sort((a, b) => a - b).map(n => {
    if (!words[n]) throw new Error(`run-data.js: warrant ${w.no} uses box ${n}, which js/track-warrant.js BOXES does not define`);
    const { vals, some } = w.boxes[n];
    const slots = words[n].match(/\{\w+\}/g) || [];
    if (vals && vals.length !== slots.length) throw new Error(`run-data.js: warrant ${w.no} box ${n} has ${vals.length} values for ${slots.length} blanks`);
    let i = 0;
    const line = words[n].replace(/\{(\w+)\}/g, (_, slot) => vals ? `<b>${esc(vals[i++])}</b>` : `<b>[${SLOT[slot] || slot}]</b>`);
    return `<tr><td class="xa-box">${n}</td><td>${line}${some ? ' <small class="xa-some">some runs</small>' : ""}</td></tr>`;
  });
  return `<p class="xa-wh">Track warrant no. <b>${esc(w.no)}</b> · copied at ${esc(w.at)} · to KV 812 East</p><table class="xa-w">${rows.join("")}</table>`;
}
const SLOT = { s: "station", t: "track", time: "time", train: "train", w: "warrant", mph: "mph", txt: "instructions" };

/* The time order the game writes at an open office (TIME_ORDER), filled with the first of each choice it makes, on the
   first westward regular train (REGULARS). */
function timeOrder({ TIME_ORDER: T, REGULARS }) {
  const train = REGULARS.find(tr => tr.dir === "W");
  if (!Array.isArray(T.no) || !Array.isArray(T.late) || !T.late.length || typeof T.words !== "function")
    throw new Error("run-data.js: TIME_ORDER needs no, late and words");
  if (!train) throw new Error("run-data.js: REGULARS has no westward train");
  return { no: String(T.no[0]), train: train.name, L: String(T.late[0]), words: T.words(train.name, T.late[0]) };
}

/* The track warrant form's boxes (js/track-warrant.js), loaded as the page loads it. */
function warrantBoxes() {
  const ctx = { window: {} };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(TRACK_WARRANT, "utf8"), ctx, { filename: TRACK_WARRANT });
  const TW = ctx.window.TrackWarrant;
  if (!TW || !Array.isArray(TW.BOXES) || !TW.BOXES.length) throw new Error("js/track-warrant.js: no BOXES on window.TrackWarrant");
  return TW.BOXES;
}

/* The reference panels, by id, from the game's data D (run-data.js by default). */
function references(D = DATA) {
  checkData(D);
  const ST = D.STATIONS;
  const BOXES = warrantBoxes();
  const plan = D.TWC_PLAN;
  const stations = `<table class="xa-tt"><thead><tr><th>Station</th><th>MP</th><th>Siding</th><th>Notes</th></tr></thead><tbody>${ST.map(st =>
    `<tr><td>${esc(st.n)}</td><td>${st.mp.toFixed(1)}</td><td>${st.sd ? "yes" : "no"}</td><td>${[st.off ? "open office (D)" : "", st.yl ? "yard limits" : ""].filter(Boolean).join(", ")}</td></tr>`).join("")}</tbody></table>`;
  const ord = timeOrder(D);
  const lead = plan.box5Lead;
  const w1 = warrant(plan, "w1"), w2 = warrant(plan, "w2");
  const some = "Rows marked <i>some runs</i> are on the warrant in only some runs.";
  return {
    tt: {
      label: "Show the time-table",
      title: "Time-table No 12, Kestrel Valley Second Subdivision",
      html: `<p>Ashby to Ironton: single track, with double track from Hollis to Ironton. The train columns change from run to run, so they are left out here.</p>${stations}<p><b>Special instructions</b></p><ul>${specialInstructions(D.SHEET_NOTES)}</ul>`,
    },
    order: {
      label: "Show the order",
      title: "The time order",
      html: `<p>At an open office the operator hands up a time order (Form E) on a westward regular train, for example:</p>
<div class="xa-order"><b>Order No ${esc(ord.no)}</b><br>${esc(ord.words)}</div>
<p>In the question, [train] is the train the order names and [n] its minutes: here ${esc(ord.train)} and ${esc(ord.L)}.</p>`,
    },
    w101: {
      label: "Show warrant 101",
      title: "Track warrant 101",
      html: `${warrantHtml(w1, BOXES)}<p>When you call for the warrant, the dispatcher sets Box 5 to the first 5-minute mark at least ${lead} minutes later. The question's two [time] values are that Box 5 time and the clock when you are ready to leave. ${some}</p>`,
    },
    w102: {
      label: "Show warrant 102",
      title: "Track warrant 102",
      html: `${warrantHtml(w2, BOXES)}<p>${some}</p>`,
    },
  };
}

/* ---------- the page ---------- */
/* The questions' references and sections must be known ones. */
function checkQuestions(qs, SEC, REFS) {
  const badRef = qs.find(q => q.ref && !REFS[q.ref]);
  if (badRef) throw new Error(`${badRef.file} line ${badRef.line}: unknown reference "${badRef.ref}" (known: ${Object.keys(REFS).join(", ")})`);
  const unknown = qs.filter(q => !Object.hasOwn(SEC, q.sec));
  if (unknown.length) throw new Error(`${unknown[0].file} line ${unknown[0].line}: unknown section "${unknown[0].sec}"`);
}

/* Question number n as a card: its text, its reference button, its choices and the rule behind it. */
function questionCard(q, n, REFS) {
  const search = plain([q.title, q.body, q.right, q.src, q.why, ...q.wrong.flatMap(w => [w.t, w.why]), q.ref ? REFS[q.ref].html : ""].join(" ")).toLowerCase();
  // Alphabetical, so the right answer is not always first when answers are hidden.
  const opts = [{ t: q.right, ok: true }, ...q.wrong].sort((a, b) => a.t.localeCompare(b.t));
  return `<article class="xa-q" data-s="${esc(search)}">
  <p class="xa-meta">${n} · ${esc(q.where)} · ${esc(q.src)}</p>
  <h3>${esc(q.title)}</h3>
  <p>${q.body}</p>${q.extra ? `\n  <div class="xa-fig">${q.extra}</div>` : ""}${q.ref ? `\n  <p><button type="button" class="xa-ref" data-ref="${q.ref}" aria-haspopup="dialog">${esc(REFS[q.ref].label)}</button></p>` : ""}
  <ul class="xa-opts">${opts.map(o => `<li${o.ok ? ' class="ok"' : ""}>${esc(o.t)}${o.why ? ` <span class="xa-ow">${o.why}</span>` : ""}</li>`).join("")}</ul>
  <p class="xa-why">${q.why}</p>
</article>`;
}

/* One deck section's questions, numbered on from `first`; "" for a section with none. */
function sectionHtml(sec, name, list, first, REFS) {
  if (!list.length) return "";
  const cards = list.map((q, i) => questionCard(q, first + i, REFS)).join("\n");
  return `<section class="xa-sec" id="${sec}"><h2>${esc(name)} <small>${list.length}</small></h2>\n${cards}\n</section>`;
}

/* The links to each section that has questions, and to the signals run's tables when there are any. */
const tocHtml = (qs, SEC, GEN) => Object.keys(SEC).filter(s => qs.some(q => q.sec === s)).map(s => `<a href="#${s}">${esc(SEC[s])}</a>`).join(" · ") +
  (GEN.n ? ` · <a href="#signals">Signals run: at each signal</a>` : "");

/* The answer key: qs grouped by the deck's sections SEC, the reference dialogs REFS, the signals run's tables GEN. */
function render(qs, SEC, REFS = {}, GEN = { n: 0, html: "" }) {
  checkQuestions(qs, SEC, REFS);
  let n = 0;
  const groups = Object.keys(SEC).map(sec => {
    const list = qs.filter(q => q.sec === sec);
    const html = sectionHtml(sec, SEC[sec], list, n + 1, REFS);
    n += list.length;
    return html;
  }).join("\n");
  return pageHtml(n, tocHtml(qs, SEC, GEN), groups, GEN, REFS);
}

/* The page around the cards: head, styles, filter, the reference dialogs and the page's script. */
function pageHtml(n, toc, groups, GEN, REFS) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Extra East answer key — HART</title>
  <meta name="description" content="Every question in the Extra East game with its answer, the wrong choices and the rule behind it.">
  <link rel="stylesheet" href="../css/ops.css">
  <link rel="stylesheet" href="../css/achievements.css">
  <!-- Generated by www/scripts/build_exam_answers.js from run.js. Do not edit by hand. -->
  <style>
.xa-tools{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;position:sticky;top:var(--header-h,0px);background:var(--paper);padding:8px 0;z-index:2}
.xa-tools input[type=search]{flex:1 1 240px;font:inherit;padding:8px 10px;border:1px solid #b9b4a6;border-radius:4px}
.xa-toc{font-size:14px;line-height:1.8}
.xa-q{border:1px solid #d6d0c0;border-radius:6px;padding:10px 14px;margin:10px 0}
.xa-q h3{margin:2px 0 6px}
.xa-meta{margin:0;font-size:12px;color:#5d5a4e;font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
.xa-opts{margin:6px 0;padding-left:22px}
.xa-opts li{margin:2px 0}
.xa-fig{margin:4px 0;color:#1d2733}
.xa-sub{font-size:17px;margin:14px 0 4px}
.xa-gen{color:#5d5a4e;font-size:14px}
.xa-ref{font:inherit;font-size:14px;padding:5px 12px;border:1.5px solid #1d2733;border-radius:4px;background:#f5f0e1;color:#1d2733;cursor:pointer}
.xa-ref:hover{background:#ece4cc}
.xa-dlg{max-width:min(640px,calc(100vw - 32px));width:100%;border:1.5px solid #1d2733;border-radius:6px;padding:14px 18px;background:#f5f0e1;color:#1d2733}
.xa-dlg::backdrop{background:rgba(29,39,51,.45)}
.xa-dlg-head{display:flex;justify-content:space-between;align-items:start;gap:12px}
.xa-dlg h2{margin:0 0 8px;font-size:20px}
.xa-close{font:inherit;font-size:22px;line-height:1;border:0;background:none;cursor:pointer;color:#1d2733;padding:0 4px}
.xa-dlg table{border-collapse:collapse;width:100%;font-size:14px;margin:6px 0}
.xa-dlg td,.xa-dlg th{border-bottom:1px solid #cdbf9c;padding:4px 6px;text-align:left;vertical-align:top}
.xa-dlg ul{padding-left:20px;font-size:15px}
.xa-some{font-size:12px;color:#5d5a4e;font-style:italic}
.xa-box{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;width:2.5em}
.xa-wh{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-size:13px}
.xa-order{background:#f3ecbf;border:1px solid #cdbf9c;padding:8px 12px;font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-size:14px;margin:6px 0}
.xa-opts li.ok{font-weight:600;color:#2d6a4f;list-style:"✓  "}
.xa-ow,.xa-why{color:#5d5a4e;font-size:14px}
.xa-sec h2 small{font-weight:400;color:#5d5a4e}
body.xa-hide .xa-opts li.ok{font-weight:inherit;color:inherit;list-style:disc}
body.xa-hide .xa-why,body.xa-hide .xa-ow{display:none}
  </style>
</head>
<body>
  <header class="site-header" data-ops-header></header>
  <main class="ap-wrap">
    <div class="page-head">
      <nav class="crumb" aria-label="Breadcrumb"><ol><li><a href="../ap/opsig.html#ce">OPSIG Achievement Program</a></li><li><a href="index.html">Conductor &amp; Engineer Exam Study Deck</a></li></ol></nav>
      <h1>Extra East answer key</h1>
      <p class="section-note">All ${n} questions in <a href="run.html">Extra East</a>, grouped by the study deck's sections. Each shows its choices in alphabetical order with the right one ticked, and the rule behind it.
        Names, numbers and times the game fills in during a run show in brackets, such as [station] or [time].</p>
    </div>
    <div class="xa-tools">
      <input type="search" id="xaFilter" placeholder="Filter by rule, word or answer" aria-label="Filter questions">
      <label><input type="checkbox" id="xaHide"> Hide answers</label>
    </div>
    <p class="xa-toc">${toc}</p>
${groups}
${GEN.html}
${Object.entries(REFS).map(([id, r]) => `<dialog class="xa-dlg" id="ref-${id}" aria-labelledby="ref-${id}-h">
  <div class="xa-dlg-head"><h2 id="ref-${id}-h">${esc(r.title)}</h2><button type="button" class="xa-close" aria-label="Close">×</button></div>
  ${r.html}
</dialog>`).join("\n")}
  </main>
  <footer class="site-footer" data-ops-footer></footer>
  <script src="../js/nav.js"></script>
  <script>
  (function(){
    var f=document.getElementById("xaFilter"),h=document.getElementById("xaHide");
    f.addEventListener("input",function(){var v=f.value.trim().toLowerCase();
      document.querySelectorAll(".xa-q").forEach(function(a){a.hidden=!!v&&a.dataset.s.indexOf(v)<0});
      document.querySelectorAll(".xa-sec").forEach(function(s){s.hidden=!s.querySelector(".xa-q:not([hidden])")});});
    h.addEventListener("change",function(){document.body.classList.toggle("xa-hide",h.checked)});
    document.querySelectorAll(".xa-ref").forEach(function(b){b.addEventListener("click",function(){
      var d=document.getElementById("ref-"+b.dataset.ref);if(!d)return;
      if(d.showModal)d.showModal();else{d.setAttribute("open","");d.scrollIntoView();}})}); // no <dialog> support: show it in place
    document.querySelectorAll(".xa-dlg").forEach(function(d){
      d.querySelector(".xa-close").addEventListener("click",function(){if(d.close)d.close();else d.removeAttribute("open");});
      d.addEventListener("click",function(e){var r=d.getBoundingClientRect(); // a click on the backdrop, outside the box, closes it
        if(e.target===d&&(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom))d.close();});});
  })();
  document.addEventListener("DOMContentLoaded", function () { HARTOps.mountChrome("ap-exam").catch(function (err) { console.error(err); }); });
  </script>
</body>
</html>
`;
}

function main() {
  const files = readRun();
  const qs = extract(files);
  const calls = files.reduce((n, f) => n + (f.src.match(/\bask\(\{/g) || []).length, 0);
  if (qs.length + qs.generated !== calls) throw new Error(`read ${qs.length} questions and ${qs.generated} signal templates but the game's scripts have ${calls} ask({ calls`);
  const GEN = qs.generated ? generatedHtml(loadSignals()) : { n: 0, html: "" };
  const html = render(qs, ENGINE.DECK_SECTIONS, references(), GEN);
  if (process.argv.includes("--check")) {
    const cur = fs.existsSync(OUT) ? fs.readFileSync(OUT, "utf8") : "";
    if (cur !== html) {
      console.error("www/exam/answers.html is out of date: run node www/scripts/build_exam_answers.js");
      process.exit(1);
    }
    console.log(`answers.html up to date (${qs.length} questions)`);
    return;
  }
  fs.writeFileSync(OUT, html);
  console.log(`wrote ${path.relative(process.cwd(), OUT)} (${qs.length} questions)`);
}

if (require.main === module) {
  try { main(); } catch (e) { console.error(`build_exam_answers: ${e.message}`); process.exit(1); }
}
module.exports = { DATA, readRun, extract, render, references, specialInstructions, warrant, warrantHtml, loadSignals, generatedHtml };
