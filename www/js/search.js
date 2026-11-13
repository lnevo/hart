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

  // Lowercased copies of the searchable fields, made once per record.
  function prepare(records) {
    return (records || []).map(function (r, i) {
      return {
        rec: r,
        i: i,
        title: String(r.title || "").toLowerCase(),
        snippet: String(r.snippet || "").toLowerCase(),
        text: String(r.text || "").toLowerCase(),
      };
    });
  }

  function atWordStart(s, at) {
    return at === 0 || /[^a-z0-9]/.test(s.charAt(at - 1));
  }

  // Score of one term against one record: title beats snippet beats text; a hit at the start
  // of a word beats a hit inside one. 0 means no match.
  // 0 = no hit, 1 = hit inside a word, 2 = hit at the start of a word (any occurrence counts).
  function hitKind(s, term) {
    var at = s.indexOf(term);
    if (at === -1) return 0;
    for (; at !== -1; at = s.indexOf(term, at + 1)) if (atWordStart(s, at)) return 2;
    return 1;
  }

  function termScore(p, term) {
    var s = 0;
    var t = hitKind(p.title, term);
    if (t) s = t === 2 ? 100 : 60;
    var n = hitKind(p.snippet, term);
    if (n) s = Math.max(s, n === 2 ? 25 : 20);
    if (p.text.indexOf(term) !== -1) s = Math.max(s, 5);
    return s;
  }

  // Kind weights: articles and pages outrank the long tail of rolling stock and photos.
  var WEIGHT = {
    article: 1.2, page: 1.0, term: 0.9, industry: 0.9, crew: 0.9,
    car: 0.6, locomotive: 0.6, mow: 0.6, photo: 0.5, archive: 0.5,
  };
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

  // The whole query equals the whole title, or one whole word of it ("2738", "NVL", "YM-01").
  function isExact(p, q) {
    if (!q) return false;
    if (p.title === q) return true;
    var words = p.title.split(/[\s,;:()\u2014\u2013|/]+/);
    for (var i = 0; i < words.length; i++) {
      var w = words[i].replace(/^[^a-z0-9&]+|[^a-z0-9&]+$/g, "");
      if (w && w === q) return true;
    }
    return false;
  }

  // Scored matches (flat): every term must hit somewhere. Best first; ties go to the shorter title.
  function scored(prepared, terms) {
    var out = [];
    for (var i = 0; i < prepared.length; i++) {
      var p = prepared[i];
      var total = 0;
      for (var j = 0; j < terms.length; j++) {
        var s = termScore(p, terms[j]);
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
    var terms = raw.split(/\s+/).filter(Boolean);
    var res = { total: 0, flat: true, groups: [] };
    if (!terms.length) return res;
    var hits = scored(prepared, terms).sort(byScore);
    var exact = [];
    var rest = [];
    // Only the best few exact hits lead; a query like "b&o" is a whole word of dozens of cars, and the
    // rest of those join their own groups so pages and articles are not pushed out.
    hits.forEach(function (h) {
      (isExact(h.p, raw) && exact.length < GROUP_CAP ? exact : rest).push(h);
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
    buckets.sort(function (a, b) { return b.best - a.best || a.order - b.order; });
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

  var api = {
    match: match, rank: rank, prepare: prepare, kindLabel: kindLabel, KINDS: KINDS, CAP: CAP,
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
      var html = "";
      if (res.flat) {
        var items = res.groups[0].items;
        var cut = showAll ? items : items.slice(0, CAP);
        html = cut.map(item).join("");
        if (items.length > cut.length) {
          more.hidden = false;
          more.textContent = "Show all " + items.length;
        }
      } else {
        res.groups.forEach(function (g) {
          var cut = openGroups[g.id] ? g.items : g.items.slice(0, GROUP_CAP);
          html +=
            '<li role="presentation" class="search-group" id="search-grp-' + g.id + '">' + esc(g.label) + "</li>" +
            cut.map(item).join("");
          if (g.items.length > cut.length) {
            html +=
              '<li role="presentation" class="search-group-more"><button type="button" class="search-more search-group-btn" data-group="' +
              g.id + '">Show all ' + g.items.length + "</button></li>";
          }
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
        go(shown[active >= 0 ? active : 0].querySelector("a"), e);
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
    list.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest(".search-group-btn");
      if (!b) return;
      openGroups[b.getAttribute("data-group")] = true;
      render();
      input.focus();
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
