// Site search: loads search-index.json (written by the build) on first open and filters it as
// you type. js/nav.js draws the button and panel and loads this file on demand.
// Matching is a pure function (HARTSearch.match) so it can be tested with node.
(function () {
  var CAP = 8; // a flat list (one group) shows this many before "Show all"
  var GROUP_CAP = 3; // each group of a grouped list shows this many before its own "Show all"
  // Chip labels by record kind.
  var KINDS = {
    article: "Article",
    page: "Page",
    car: "Car",
    locomotive: "Locomotive",
    mow: "MOW",
    term: "Term",
    industry: "Industry",
    crew: "Crew",
    archive: "Archive",
    photo: "Photo",
  };

  function kindLabel(kind) {
    return KINDS[kind] || (kind ? String(kind).charAt(0).toUpperCase() + String(kind).slice(1) : "Page");
  }

  // Folding: lower case, accents off, apostrophes dropped, "&" read as "and", every other mark a space.
  // "B&O", "b and o" and "B & O" all fold to "b and o"; "YM-01" folds to "ym 01".
  function fold(s) {
    s = String(s || "").toLowerCase();
    if (s.normalize) s = s.normalize("NFD").replace(/[̀-ͯ]/g, "");
    return s.replace(/['’]/g, "").replace(/&/g, " and ").replace(/[^a-z0-9]+/g, " ").trim();
  }
  // Folded with the spaces and the word "and" taken out: "b and o" -> "bo", "ym 01" -> "ym01".
  function compact(s) {
    return fold(s).split(" ").filter(function (w) { return w && w !== "and"; }).join("");
  }
  function words(s) {
    var seen = {};
    return s.split(" ").filter(function (w) { return w && !seen[w] && (seen[w] = 1); });
  }

  // Folded copies of the searchable fields, made once per record.
  function prepare(records) {
    return (records || []).map(function (r, i) {
      var title = fold(r.title);
      var snippet = fold(r.snippet);
      return {
        rec: r,
        i: i,
        title: title,
        snippet: snippet,
        text: fold(r.text),
        raw: String(r.title || ""), // for the whole-word exact check
        tw: words(title), // whole words, for typo matching (title and snippet only)
        sw: words(snippet),
      };
    });
  }

  function atWordStart(s, at) {
    return at === 0 || s.charAt(at - 1) === " ";
  }

  // 0 = no hit, 1 = hit inside a word, 2 = hit at the start of a word (any occurrence counts).
  function hitKind(s, term) {
    var at = s.indexOf(term);
    if (at === -1) return 0;
    for (; at !== -1; at = s.indexOf(term, at + 1)) if (atWordStart(s, at)) return 2;
    return 1;
  }
  // Whole words only (used for synonyms, so "cr" never reaches "crew").
  function hasWhole(s, phrase) {
    return (" " + s + " ").indexOf(" " + phrase + " ") !== -1;
  }

  // Score of one term against one record: title beats snippet beats text; a hit at the start
  // of a word beats a hit inside one. 0 means no match.
  function termScore(p, term) {
    var s = 0;
    var t = hitKind(p.title, term);
    if (t) s = t === 2 ? 100 : 60;
    var n = hitKind(p.snippet, term);
    if (n) s = Math.max(s, n === 2 ? 25 : 20);
    if (p.text.indexOf(term) !== -1) s = Math.max(s, 5);
    return s;
  }

  // ---- Synonyms ------------------------------------------------------------------------------------------
  // Railroad names the site spells more than one way. Each row is one set of names that stand for the same
  // thing, and a search for any of them also finds the others (both ways, at half score, whole words only).
  // Every name here appears in the site's own pages or data. Keep the rows apart: P&CV and P&OV are
  // different names on purpose and must never share a row.
  var SYNONYMS = [
    ["chessie", "chessie system", "c&o", "b&o"], // the Chessie System roads on the roster
    ["p&le", "pittsburgh & lake erie"],
    ["conrail", "cr"],
    ["p&ov", "pittsburgh & ohio valley"],
    ["p&cv", "pittsburgh & chartiers valley"],
    ["pohc", "pittsburgh & ohio central"],
    ["wle", "w&le", "wheeling & lake erie"],
    ["nyc", "new york central"],
    ["prr", "pennsylvania railroad"],
    ["n&w", "norfolk & western"],
  ];
  var SYN_FACTOR = 0.5;
  var SYN_MAX = 5; // longest name, in words
  // compact key ("b and o" -> "bo") -> the folded names of its row
  var SYN_INDEX = {};
  SYNONYMS.forEach(function (row) {
    var folded = row.map(fold);
    folded.forEach(function (name) {
      SYN_INDEX[compact(name)] = folded;
    });
  });

  // ---- Typos ---------------------------------------------------------------------------------------------
  var FUZZY_MIN = 5; // shortest term that may be a typo; shorter terms and numbers stay exact
  var FUZZY_TITLE = 15; // well below exact (100/60 title, 25/20 snippet)
  var FUZZY_SNIPPET = 8;

  // True when a and b differ by exactly one insert, delete, substitute or swap of neighbours.
  function oneEdit(a, b) {
    if (a === b) return false;
    var la = a.length;
    var lb = b.length;
    if (Math.abs(la - lb) > 1) return false;
    var i = 0;
    while (i < la && i < lb && a.charAt(i) === b.charAt(i)) i++;
    if (la === lb) {
      if (a.slice(i + 1) === b.slice(i + 1)) return true; // substitute
      return a.charAt(i) === b.charAt(i + 1) && a.charAt(i + 1) === b.charAt(i) && a.slice(i + 2) === b.slice(i + 2); // swap
    }
    return la > lb ? a.slice(i + 1) === b.slice(i) : b.slice(i + 1) === a.slice(i);
  }
  function fuzzyOk(term) {
    return term.length >= FUZZY_MIN && /^[a-z]+$/.test(term);
  }
  function fuzzyScore(p, term) {
    var i;
    for (i = 0; i < p.tw.length; i++) if (oneEdit(p.tw[i], term)) return FUZZY_TITLE;
    for (i = 0; i < p.sw.length; i++) if (oneEdit(p.sw[i], term)) return FUZZY_SNIPPET;
    return 0;
  }

  // ---- Query ---------------------------------------------------------------------------------------------
  // The query as units. A unit is one typed word or a phrase ("b and o", "ym 01"), with the other spellings
  // that count as the same thing: variants ("ym01" -> "ym 01") and synonyms.
  function parse(query) {
    var pieces = String(query || "").split(/\s+/).map(fold).filter(Boolean);
    var i;
    // "b and o" typed with spaces becomes one phrase.
    for (i = 0; i + 2 < pieces.length; i++) {
      if (pieces[i].length === 1 && pieces[i + 1] === "and" && pieces[i + 2].length <= 2) {
        pieces.splice(i, 3, pieces[i] + " and " + pieces[i + 2]);
      }
    }
    var units = [];
    for (i = 0; i < pieces.length; ) {
      var done = false;
      for (var n = Math.min(SYN_MAX, pieces.length - i); n >= 1 && !done; n--) {
        var span = pieces.slice(i, i + n).join(" ");
        var row = SYN_INDEX[compact(span)];
        if (row) {
          // "bo" is the same name as "b&o" (a variant); the rest of the row are synonyms.
          var key = compact(span);
          units.push({
            text: span,
            variants: row.filter(function (x) { return compact(x) === key && x !== span; }),
            syns: row.filter(function (x) { return compact(x) !== key; }),
          });
          i += n;
          done = true;
        }
      }
      if (!done) {
        units.push({ text: pieces[i], variants: [], syns: [] });
        i++;
      }
    }
    // A lone "and" between other words only gets in the way.
    if (units.length > 1) units = units.filter(function (u) { return u.text !== "and"; });
    units.forEach(function (u) {
      var m = /^([a-z]{2,})([0-9]+)$/.exec(u.text); // "ym01" also reads as "ym 01"
      if (m) u.variants.push(m[1] + " " + m[2]);
    });
    return units;
  }

  function unitScore(p, u, fuzzy) {
    var s = termScore(p, u.text);
    var i;
    for (i = 0; i < u.variants.length; i++) s = Math.max(s, termScore(p, u.variants[i]));
    for (i = 0; i < u.syns.length; i++) {
      var sy = u.syns[i];
      var r = hasWhole(p.title, sy) ? 100 : hasWhole(p.snippet, sy) ? 25 : hasWhole(p.text, sy) ? 5 : 0;
      s = Math.max(s, r * SYN_FACTOR);
    }
    if (!s && fuzzy && fuzzyOk(u.text)) s = fuzzyScore(p, u.text);
    return s;
  }

  // Kind weights: articles and pages outrank photos, and rolling stock is the lowest of all (owner's call).
  var WEIGHT = {
    article: 1.2, page: 1.0, term: 0.9, industry: 0.9, crew: 0.9,
    photo: 0.5, archive: 0.5, car: 0.3, locomotive: 0.3, mow: 0.3,
  };
  var STOCK = ["car", "locomotive", "mow"];
  // Result groups, in tie-break order. Groups are then ordered by their best weighted score.
  var GROUPS = [
    { id: "pages", label: "Pages & articles", kinds: ["article", "page"] },
    { id: "railroad", label: "Railroad", kinds: ["term", "industry", "crew"] },
    { id: "stock", label: "Rolling stock", kinds: ["car", "locomotive", "mow"] },
    { id: "photos", label: "Photos & archive", kinds: ["photo", "archive"] },
  ];
  var BEST = { id: "best", label: "Best match" };

  function weight(kind) {
    return WEIGHT[kind] || 0.5;
  }
  function groupOf(kind) {
    for (var i = 0; i < GROUPS.length; i++) if (GROUPS[i].kinds.indexOf(kind) !== -1) return i;
    return GROUPS.length - 1;
  }

  // The whole query equals the whole title, or one whole word of it ("2738", "NVL", "YM-01"). Compared
  // folded and compact, so "ym01" is exact for "YM-01" and "bo" for "B&O".
  function isExact(p, q) {
    var c = compact(q);
    if (!c) return false;
    if (compact(p.raw) === c) return true;
    var ws = p.raw.toLowerCase().split(/[\s,;:()—–|/]+/);
    for (var i = 0; i < ws.length; i++) if (ws[i] && compact(ws[i]) === c) return true;
    return false;
  }

  // Scored matches (flat): every unit must hit somewhere. Best first; ties go to the shorter title.
  function scored(prepared, units, fuzzy) {
    var out = [];
    for (var i = 0; i < prepared.length; i++) {
      var p = prepared[i];
      var total = 0;
      for (var j = 0; j < units.length; j++) {
        var s = unitScore(p, units[j], fuzzy);
        if (!s) {
          total = 0;
          break;
        }
        total += s;
      }
      if (total) out.push({ p: p, score: total, w: total * weight(p.rec.kind) });
    }
    return out;
  }
  function byScore(a, b) {
    return b.w - a.w || a.p.title.length - b.p.title.length || a.p.i - b.p.i;
  }

  // Ranked, grouped results: { total, flat, groups: [{id, label, items: [record]}] }.
  // Exact hits form a leading "Best match" group; the rest go into kind groups ordered by their best
  // weighted score. When only one group has results, flat is true and the heading is not drawn.
  function rank(prepared, query) {
    var raw = String(query || "").toLowerCase().trim();
    var units = parse(raw);
    var res = { total: 0, flat: true, groups: [] };
    if (!units.length) return res;
    var hits = scored(prepared, units, false);
    // Typos are tried only when nothing matches as typed, so a real word never drags in near-misses.
    if (!hits.length && units.some(function (u) { return fuzzyOk(u.text); })) hits = scored(prepared, units, true);
    hits.sort(byScore);
    var whole = units.map(function (u) { return u.text; }).join(" ");
    var exact = [];
    var rest = [];
    // Only the best few exact hits lead; a query like "b&o" is a whole word of dozens of cars, and the
    // rest of those join their own groups so pages and articles are not pushed out.
    // Rolling stock leads only for a number ("2738"), never for a road name ("b&o").
    var numeric = /[0-9]/.test(raw);
    hits.forEach(function (h) {
      var lead = isExact(h.p, whole) && (numeric || STOCK.indexOf(h.p.rec.kind) === -1);
      (lead && exact.length < GROUP_CAP ? exact : rest).push(h);
    });
    var buckets = GROUPS.map(function (g) {
      return { id: g.id, label: g.label, items: [], best: 0, order: 0 };
    });
    rest.forEach(function (h) {
      var b = buckets[groupOf(h.p.rec.kind)];
      b.items.push(h);
      if (h.w > b.best) b.best = h.w;
    });
    buckets = buckets.filter(function (b) { return b.items.length; });
    buckets.forEach(function (b, i) { b.order = i; });
    // Rolling stock is always the last group, whatever its score.
    buckets.sort(function (a, b) {
      return (a.id === "stock") - (b.id === "stock") || b.best - a.best || a.order - b.order;
    });
    var groups = [];
    if (exact.length) groups.push({ id: BEST.id, label: BEST.label, items: exact });
    groups = groups.concat(buckets);
    groups.forEach(function (g) {
      g.items = g.items.map(function (h) { return h.p.rec; });
    });
    res.groups = groups;
    res.flat = groups.length < 2;
    res.total = hits.length;
    return res;
  }

  // Flat list in display order (kept for callers and tests that want only the order).
  function match(prepared, query) {
    var out = [];
    rank(prepared, query).groups.forEach(function (g) {
      out = out.concat(g.items);
    });
    return out;
  }

  // Searches offered when the box is empty (each is tested against the real index, so each finds something).
  var EXAMPLES = ["YM-01", "Shenango", "Conrail", "waybill", "hopper", "2738"];

  var api = {
    EXAMPLES: EXAMPLES, SYNONYMS: SYNONYMS, fold: fold, match: match, rank: rank, prepare: prepare, kindLabel: kindLabel, KINDS: KINDS, CAP: CAP,
    GROUP_CAP: GROUP_CAP, GROUPS: GROUPS, WEIGHT: WEIGHT,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window === "undefined") return;
  window.HARTSearch = api;

  var warned = false;
  var indexPromise = null;

  function loadIndex(base) {
    if (!indexPromise) {
      indexPromise = fetch(base + "search-index.json", { cache: "no-cache" })
        .then(function (res) {
          if (!res.ok) throw new Error("search-index.json " + res.status);
          return res.json();
        })
        .then(function (data) {
          return prepare(data && data.records);
        })
        .catch(function (err) {
          if (!warned) {
            warned = true;
            console.warn("Search unavailable: " + err.message);
          }
          indexPromise = null; // a later open or keystroke tries again
          return null;
        });
    }
    return indexPromise;
  }

  // Wire the markup nav.js drew: root holds the input, the live status and the results list.
  function attach(root, base) {
    var esc = window.HARTOps.esc;
    var input = root.querySelector(".search-input");
    var list = root.querySelector(".search-results");
    var status = root.querySelector(".search-status");
    var more = root.querySelector(".search-more");
    var empty = root.querySelector(".search-empty");
    var hint = root.querySelector(".search-hint");
    // "Try:" row under the hint while the box is empty; each button fills the box and runs the search.
    var tryRow = document.createElement("p");
    tryRow.className = "search-try small";
    tryRow.hidden = true;
    tryRow.appendChild(document.createTextNode("Try: "));
    EXAMPLES.forEach(function (q) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "search-try-btn";
      b.textContent = q;
      tryRow.appendChild(b);
    });
    hint.parentNode.insertBefore(tryRow, hint.nextSibling);
    tryRow.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest(".search-try-btn");
      if (!b) return;
      input.value = b.textContent;
      input.dispatchEvent(new Event("input"));
      input.focus();
    });
    var prepared = null;
    var unavailable = false;
    var shown = [];
    var active = -1;
    var showAll = false;
    var openGroups = {}; // group ids whose "Show all" was used

    function options() {
      return list.querySelectorAll(".search-item");
    }

    function setActive(n, fromMouse) {
      var items = options();
      if (active >= 0 && items[active]) items[active].removeAttribute("aria-selected");
      active = n;
      if (n >= 0 && items[n]) {
        items[n].setAttribute("aria-selected", "true");
        input.setAttribute("aria-activedescendant", items[n].id);
        if (!fromMouse) items[n].scrollIntoView({ block: "nearest" });
      } else {
        input.removeAttribute("aria-activedescendant");
      }
    }

    function fallbackLinks() {
      return [
        ["photos/index.html", "Photos"],
        ["operators/glossary/index.html", "Glossary"],
        ["briefing/index.html", "New Operator Primer"],
      ]
        .map(function (l) {
          return '<a href="' + esc(base + l[0]) + '">' + l[1] + "</a>";
        })
        .join(" · ");
    }

    function render() {
      var q = input.value;
      list.innerHTML = "";
      setActive(-1);
      shown = [];
      more.hidden = true;
      empty.hidden = true;
      hint.hidden = true;
      tryRow.hidden = true;
      if (unavailable) {
        input.setAttribute("aria-expanded", "false");
        empty.hidden = false;
        empty.innerHTML = "Search unavailable. Try " + fallbackLinks() + ".";
        status.textContent = "Search unavailable";
        return;
      }
      if (!q.trim()) {
        input.setAttribute("aria-expanded", "false");
        hint.hidden = false;
        tryRow.hidden = false;
        status.textContent = "";
        return;
      }
      if (!prepared) {
        status.textContent = "Loading search";
        return;
      }
      var res = rank(prepared, q);
      if (!res.total) {
        input.setAttribute("aria-expanded", "false");
        empty.hidden = false;
        empty.innerHTML = "No match. Try " + fallbackLinks() + ".";
        status.textContent = "No match";
        return;
      }
      input.setAttribute("aria-expanded", "true");
      var n = 0;
      function item(r) {
        var thumb = r.thumb
          ? '<img class="search-thumb" src="' + esc(base + r.thumb) + '" alt="" width="40" height="40" loading="lazy" decoding="async">'
          : "";
        return (
          '<li role="option" id="search-opt-' + n++ + '" class="search-item' + (thumb ? " has-thumb" : "") + '">' +
          '<a tabindex="-1" href="' + esc(base + (r.url || "")) + '">' +
          '<span class="search-kind">' + esc(kindLabel(r.kind)) + "</span>" +
          thumb +
          '<span class="search-title">' + esc(r.title) + "</span>" +
          (r.snippet ? '<span class="search-snippet">' + esc(r.snippet) + "</span>" : "") +
          "</a></li>"
        );
      }
      // "Show all N" is an option too, so the arrow keys reach it and Enter opens the rest.
      function moreOption(groupId, count) {
        return (
          '<li role="option" id="search-opt-' + n++ + '" class="search-item search-group-more" data-group="' + groupId + '">' +
          '<span class="search-more search-group-btn">Show all ' + count + "</span></li>"
        );
      }
      var html = "";
      if (res.flat) {
        var items = res.groups[0].items;
        var cut = showAll ? items : items.slice(0, CAP);
        html = cut.map(item).join("");
        if (items.length > cut.length) html += moreOption("", items.length);
      } else {
        res.groups.forEach(function (g) {
          var cut = openGroups[g.id] ? g.items : g.items.slice(0, GROUP_CAP);
          html +=
            '<li role="group" class="search-grp" aria-labelledby="search-grp-' + g.id + '">' +
            '<div class="search-group" id="search-grp-' + g.id + '">' + esc(g.label) + "</div>" +
            '<ul role="none" class="search-grp-items">' +
            cut.map(item).join("") +
            (g.items.length > cut.length ? moreOption(g.id, g.items.length) : "") +
            "</ul></li>";
        });
      }
      list.innerHTML = html;
      shown = options();
      status.textContent = res.total + (res.total === 1 ? " result" : " results");
    }

    var loading = false;
    function load() {
      if (loading || prepared) return;
      loading = true;
      loadIndex(base).then(function (p) {
        loading = false;
        unavailable = !p;
        if (p) prepared = p;
        render();
      });
    }
    load();

    input.addEventListener("input", function () {
      showAll = false;
      openGroups = {};
      if (unavailable) load();
      render();
    });
    input.addEventListener("keydown", function (e) {
      var n = shown.length;
      if (e.key === "ArrowDown" && n) {
        e.preventDefault();
        setActive(active + 1 >= n ? 0 : active + 1);
      } else if (e.key === "ArrowUp" && n) {
        e.preventDefault();
        setActive(active <= 0 ? n - 1 : active - 1);
      } else if (e.key === "Enter" && n) {
        e.preventDefault();
        var opt = shown[active >= 0 ? active : 0];
        if (opt.hasAttribute("data-group")) expand(opt);
        else go(opt.querySelector("a"), e);
      }
    });
    // Following a result that is the page and hash already shown changes nothing, so no hashchange
    // fires; send one, so the page opens the item again (a closed photo, a scrolled-away term).
    function go(a, e) {
      if (a.href === window.location.href) {
        if (e) e.preventDefault();
        window.dispatchEvent(new HashChangeEvent("hashchange"));
      } else if (e && e.type === "keydown") {
        window.location.href = a.href;
      }
    }
    list.addEventListener("click", function (e) {
      var a = e.target.closest && e.target.closest("a");
      if (a) go(a, e);
    });
    more.addEventListener("click", function () {
      showAll = true;
      render();
      input.focus();
    });
    // Open the rest of a group ("" = the single flat list) and keep the highlight on the first new row.
    function expand(opt) {
      var g = opt.getAttribute("data-group");
      var at = Array.prototype.indexOf.call(options(), opt);
      if (g) openGroups[g] = true;
      else showAll = true;
      render();
      input.focus();
      if (at >= 0) setActive(at);
    }
    list.addEventListener("click", function (e) {
      var opt = e.target.closest && e.target.closest(".search-group-more");
      if (opt) expand(opt);
    });
    // Mouse hover follows the keyboard highlight so the two never disagree.
    list.addEventListener("mousemove", function (e) {
      var li = e.target.closest && e.target.closest(".search-item");
      if (!li) return;
      var idx = Array.prototype.indexOf.call(options(), li);
      if (idx < 0) return;
      if (idx !== active) setActive(idx, true);
    });
    render();
  }

  api.attach = attach;
})();
