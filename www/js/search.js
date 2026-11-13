// Site search: loads search-index.json (written by the build) on first open and filters it as
// you type. js/nav.js draws the button and panel and loads this file on demand.
// Matching is a pure function (HARTSearch.match) so it can be tested with node.
(function () {
  var CAP = 8;
  // Chip labels by record kind. Stage 1 sends only "page"; the rest are ready for later stages.
  var KINDS = {
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
  function termScore(p, term) {
    var s = 0;
    var t = p.title.indexOf(term);
    if (t !== -1) s = atWordStart(p.title, t) ? 100 : 60;
    var n = p.snippet.indexOf(term);
    if (n !== -1) s = Math.max(s, atWordStart(p.snippet, n) ? 25 : 20);
    if (p.text.indexOf(term) !== -1) s = Math.max(s, 5);
    return s;
  }

  // Every term must hit somewhere. Best score first; ties go to the shorter title, then index order.
  function match(prepared, query) {
    var terms = String(query || "").toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) return [];
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
      if (total) out.push({ p: p, score: total });
    }
    out.sort(function (a, b) {
      return b.score - a.score || a.p.title.length - b.p.title.length || a.p.i - b.p.i;
    });
    return out.map(function (x) {
      return x.p.rec;
    });
  }

  var api = { match: match, prepare: prepare, kindLabel: kindLabel, KINDS: KINDS, CAP: CAP };

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

    function setActive(n) {
      var items = list.children;
      if (active >= 0 && items[active]) items[active].removeAttribute("aria-selected");
      active = n;
      if (n >= 0 && items[n]) {
        items[n].setAttribute("aria-selected", "true");
        input.setAttribute("aria-activedescendant", items[n].id);
        items[n].scrollIntoView({ block: "nearest" });
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
      var all = match(prepared, q);
      shown = showAll ? all : all.slice(0, CAP);
      if (!all.length) {
        input.setAttribute("aria-expanded", "false");
        empty.hidden = false;
        empty.innerHTML = "No match. Try " + fallbackLinks() + ".";
        status.textContent = "No match";
        return;
      }
      input.setAttribute("aria-expanded", "true");
      list.innerHTML = shown
        .map(function (r, i) {
          return (
            '<li role="option" id="search-opt-' + i + '" class="search-item">' +
            '<a tabindex="-1" href="' + esc(base + (r.url || "")) + '">' +
            '<span class="search-kind">' + esc(kindLabel(r.kind)) + "</span>" +
            '<span class="search-title">' + esc(r.title) + "</span>" +
            (r.snippet ? '<span class="search-snippet">' + esc(r.snippet) + "</span>" : "") +
            "</a></li>"
          );
        })
        .join("");
      if (all.length > shown.length) {
        more.hidden = false;
        more.textContent = "Show all " + all.length;
      }
      status.textContent = all.length + (all.length === 1 ? " result" : " results");
    }

    loadIndex(base).then(function (p) {
      if (p) prepared = p;
      else unavailable = true;
      render();
    });

    input.addEventListener("input", function () {
      showAll = false;
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
        window.location.href = list.children[active >= 0 ? active : 0].querySelector("a").href;
      }
    });
    more.addEventListener("click", function () {
      showAll = true;
      render();
      input.focus();
    });
    // Mouse hover follows the keyboard highlight so the two never disagree.
    list.addEventListener("mousemove", function (e) {
      var li = e.target.closest && e.target.closest("li");
      if (!li) return;
      var idx = Array.prototype.indexOf.call(list.children, li);
      if (idx !== active) setActive(idx);
    });
    render();
  }

  api.attach = attach;
})();
