// "Who became who" lineage charts (plants/, railroads/). Each page is a static skeleton
// (see plants/index.html) plus one JSON file:
//   title, lede, article, years {min, max, start}, pick ("Who ran it in"), trunkColor,
//   trunk [cards and {handoff}], split, lanes [{id, title, hart | link {label, href}, color, steps, end}],
//   merge {lanes [ids], label, steps, end}, table {headers, rows, note}.
// A card is {name, years, from, to, made, logo | wordmark, note, pcc, maybe [from, to]}.
// "to": null means still running. "maybe" marks years the articles leave open.
(function () {
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function $(id) {
    return document.getElementById(id);
  }

  // Logos are stored relative to the portal root ("../external/..." locally, "assets/logos/..." when built).
  function src(path) {
    return HARTOps.base() + path;
  }

  function card(c) {
    var logo = c.logo
      ? '<img src="' + esc(src(c.logo)) + '" alt="' + esc(c.name) + ' logo" loading="lazy">'
      : '<span class="wordmark">' + esc(c.wordmark || c.name) + "</span>";
    var maybe = c.maybe ? ' data-maybe="' + esc(c.maybe[0]) + "-" + esc(c.maybe[1]) + '"' : "";
    return (
      '<article class="lin-card" data-from="' + esc(c.from == null ? "" : c.from) + '" data-to="' +
      esc(c.to == null ? 9999 : c.to) + '"' + maybe + ">" +
      '<div class="lin-logo">' + logo + "</div>" +
      '<div class="lin-body">' + (c.pcc ? '<p class="under">Under PC&amp;C</p>' : "") +
      "<h3>" + esc(c.name) + '</h3><p class="yrs">' + esc(c.years) + "</p>" +
      '<p class="made">' + esc(c.made) + "</p>" +
      (c.note ? '<p class="note">' + esc(c.note) + "</p>" : "") +
      "</div></article>"
    );
  }

  function step(s) {
    return s.handoff
      ? '<li class="handoff"><span>' + esc(s.handoff) + "</span></li>"
      : "<li>" + card(s) + "</li>";
  }

  function endBox(end) {
    if (!end) return "";
    var open = end.state === "open";
    return (
      '<li class="handoff"><span>Today</span></li><li><p class="lane-end' + (open ? " is-open" : "") + '"><b>' +
      (open ? "Still here" : "Ended") + "</b>" + esc(end.text) + "</p></li>"
    );
  }

  function laneStyle(l, extra) {
    return ' style="' + (l.color ? "--lane:" + esc(l.color) + ";" : "") + (extra || "") + '"';
  }

  function lane(l, i, merge) {
    var hart = l.hart
      ? '<a href="' + esc(HARTOps.base() + (l.hartHref || "industries/index.html")) + '">On HART: ' + esc(l.hart) + "</a>"
      : l.link
        ? '<a href="' + esc(HARTOps.base() + l.link.href) + '">' + esc(l.link.label) + "</a>"
        : "";
    var merges = merge && (merge.lanes || []).indexOf(l.id) !== -1;
    var place = merge ? "grid-column:" + (i + 1) + ";grid-row:" + (merges ? "1" : "1 / span 2") + ";" : "";
    return (
      '<section class="lane' + (merges ? " merges" : "") + '" data-lane="' + esc(l.id) + '" aria-labelledby="lane-' + esc(l.id) + '"' +
      laneStyle(l, place) + ">" +
      '<div class="lane-head"><h2 id="lane-' + esc(l.id) + '">' + esc(l.title) + "</h2>" + hart + "</div>" +
      '<ol class="lane-steps">' + (l.steps || []).map(step).join("") + endBox(l.end) + "</ol>" +
      (merges ? '<div class="lane-tail" aria-hidden="true"></div>' : "") +
      "</section>"
    );
  }

  function mergeBlock(m, lanes) {
    var cols = (m.lanes || []).map(function (id) {
      for (var i = 0; i < lanes.length; i++) if (lanes[i].id === id) return i + 1;
      return 0;
    });
    var a = Math.min.apply(null, cols);
    var b = Math.max.apply(null, cols);
    return (
      '<section class="merge" aria-label="' + esc(m.label) + '" style="--k:' + (b - a + 1) +
      ";grid-column:" + a + " / " + (b + 1) + ';grid-row:2;">' +
      '<div class="merge-join" aria-hidden="true"><span class="bar"></span></div>' +
      '<p class="merge-label">' + esc(m.label) + "</p>" +
      '<ol class="lane-steps">' + (m.steps || []).map(step).join("") + endBox(m.end) + "</ol></section>"
    );
  }

  function table(t) {
    var heads = ["Years"].concat(t.headers || []);
    var sep = t.separator == null ? -1 : t.separator; // column index (0-based, after Years) that starts a second group
    var prev = null;
    var body = (t.rows || [])
      .map(function (r) {
        var cells = r.cells
          .map(function (cell, i) {
            var same = prev && prev[i] === cell;
            return '<td class="' + (same ? "same" : "") + (i === sep ? " sep" : "") + '">' + esc(cell) + "</td>";
          })
          .join("");
        prev = r.cells;
        return '<tr data-from="' + r.from + '" data-to="' + r.to + '"><th scope="row">' + esc(r.years) + "</th>" + cells + "</tr>";
      })
      .join("");
    return (
      "<thead><tr>" +
      heads.map(function (h, i) { return '<th scope="col"' + (i === sep + 1 ? ' class="sep"' : "") + ">" + esc(h) + "</th>"; }).join("") +
      "</tr></thead><tbody>" + body + "</tbody>"
    );
  }

  function mount(pageId, dataPath) {
    var page = document.querySelector("main.lineage-page");
    var range = $("year");
    var out = $("year-out");
    var clear = $("year-clear");
    var min = +range.min;
    var max = +range.max;

    // —— Year picker: highlights the cards and the table row that cover the year. ——
    function setYear(y) {
      var on = y != null;
      page.classList.toggle("has-year", on);
      clear.disabled = !on;
      out.textContent = on ? String(y) : "…";
      if (on) range.value = y;
      var els = page.querySelectorAll(".lin-card, #year-table tbody tr");
      for (var i = 0; i < els.length; i++) {
        var fs = els[i].getAttribute("data-from");
        var f = fs === "" ? Infinity : +fs;
        var t = +els[i].getAttribute("data-to");
        var hit = on && y >= f && y <= t;
        var m = (els[i].getAttribute("data-maybe") || "").split("-");
        var maybe = on && !hit && m.length === 2 && y >= +m[0] && y <= +m[1];
        els[i].classList.toggle("on", hit);
        els[i].classList.toggle("maybe", maybe);
      }
      var key = page.querySelector(".maybe-key");
      if (key) key.hidden = !page.querySelector(".lin-card.maybe");
      try {
        var u = new URL(window.location.href);
        if (on) u.searchParams.set("year", y);
        else u.searchParams.delete("year");
        history.replaceState(null, "", u);
      } catch (e) {}
    }

    range.addEventListener("input", function () { setYear(+range.value); });
    clear.addEventListener("click", function () { setYear(null); });

    // —— Tabs ——
    var tabs = page.querySelectorAll('[role="tab"]');
    function showTab(id) {
      for (var i = 0; i < tabs.length; i++) {
        var sel = tabs[i].id === id;
        tabs[i].setAttribute("aria-selected", sel ? "true" : "false");
        $(tabs[i].getAttribute("aria-controls")).hidden = !sel;
      }
    }
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].addEventListener("click", function () {
        showTab(this.id);
        try { history.replaceState(null, "", this.id === "tab-years" ? "#years" : window.location.pathname + window.location.search); } catch (e) {}
        if (this.id === "tab-years") {
          var row = page.querySelector("#year-table tr.on");
          if (row) row.scrollIntoView({ block: "center" });
        }
      });
    }

    document.addEventListener("DOMContentLoaded", async function () {
      try {
        await HARTOps.mountChrome(pageId);
        var d = await HARTOps.loadJson(dataPath);
        if (d.title) $("lin-title").textContent = d.title;
        // lede: one string, or a list of paragraphs.
        var lede = $("lin-lede");
        var paras = [].concat(d.lede || []);
        lede.textContent = paras[0] || "";
        paras.slice(1).reverse().forEach(function (txt) {
          var p = document.createElement("p");
          p.className = lede.className;
          p.textContent = txt;
          lede.parentNode.insertBefore(p, lede.nextSibling);
        });
        if (d.article) $("lin-article").href = HARTOps.base() + d.article;
        if (d.trunkColor) page.style.setProperty("--trunk", d.trunkColor);
        var lanes = d.lanes || [];
        page.style.setProperty("--n", String(lanes.length || 1));

        if (d.trunk && d.trunk.length) {
          $("trunk").innerHTML = d.trunk.map(step).join("");
          $("split-label").textContent = d.split || "";
        } else {
          page.classList.add("no-trunk");
          $("trunk").hidden = true;
          page.querySelector(".split").hidden = true;
        }

        var lanesEl = $("lanes");
        // Optional line filter (d.filter = its label): chips that show or hide lanes, kept in ?lines=.
        var shown = lanes.map(function (l) { return l.id; });
        var want = (new URLSearchParams(window.location.search).get("lines") || "").split(",").filter(Boolean);
        if (d.filter && want.length) {
          var keep = shown.filter(function (id) { return want.indexOf(id) !== -1; });
          if (keep.length) shown = keep;
        }

        function renderLanes() {
          var vis = lanes.filter(function (l) { return shown.indexOf(l.id) !== -1; });
          page.style.setProperty("--n", String(vis.length || 1));
          var merge = d.merge && (d.merge.lanes || []).some(function (id) { return shown.indexOf(id) !== -1; })
            ? Object.assign({}, d.merge, { lanes: d.merge.lanes.filter(function (id) { return shown.indexOf(id) !== -1; }) })
            : null;
          lanesEl.classList.toggle("has-merge", !!merge);
          // Lanes in DOM order, with the merge right after the last lane it joins (so phones read it in order).
          var html = [];
          var last = -1;
          if (merge) vis.forEach(function (l, i) { if (merge.lanes.indexOf(l.id) !== -1) last = i; });
          vis.forEach(function (l, i) {
            html.push(lane(l, i, merge));
            if (i === last) html.push(mergeBlock(merge, vis));
          });
          lanesEl.innerHTML = html.join("");
        }

        if (d.filter) {
          var bar = document.createElement("div");
          bar.className = "line-filter";
          bar.setAttribute("role", "group");
          bar.setAttribute("aria-label", d.filter);
          bar.innerHTML =
            '<span class="line-filter-label">' + esc(d.filter) + "</span>" +
            lanes.map(function (l) {
              return '<button type="button" data-line="' + esc(l.id) + '"' + laneStyle(l) + ' aria-pressed="' +
                (shown.indexOf(l.id) !== -1) + '">' + esc(l.title) + "</button>";
            }).join("") +
            '<button type="button" class="line-filter-all">All</button>';
          lanesEl.parentNode.insertBefore(bar, lanesEl);
          var sync = function () {
            bar.querySelectorAll("[data-line]").forEach(function (b) {
              b.setAttribute("aria-pressed", String(shown.indexOf(b.getAttribute("data-line")) !== -1));
            });
            try {
              var u = new URL(window.location.href);
              if (shown.length === lanes.length) u.searchParams.delete("lines");
              else u.searchParams.set("lines", shown.join(","));
              history.replaceState(null, "", u);
            } catch (e) {}
            renderLanes();
            setYear(range.value && !clear.disabled ? +range.value : null);
          };
          bar.addEventListener("click", function (e) {
            var b = e.target.closest("button");
            if (!b) return;
            if (b.classList.contains("line-filter-all")) {
              shown = lanes.map(function (l) { return l.id; });
            } else {
              var id = b.getAttribute("data-line");
              var on = shown.indexOf(id) !== -1;
              if (on && shown.length === 1) return; // keep at least one line
              shown = on
                ? shown.filter(function (x) { return x !== id; })
                : lanes.map(function (l) { return l.id; }).filter(function (x) { return x === id || shown.indexOf(x) !== -1; });
            }
            sync();
          });
        }
        renderLanes();

        if (d.table && (d.table.rows || []).length) {
          $("year-table").innerHTML = table(d.table);
          $("table-note").textContent = d.table.note || "";
          if (window.location.hash === "#years") showTab("tab-years");
        } else {
          page.querySelector('[role="tablist"]').hidden = true;
          $("panel-years").hidden = true;
        }

        if (page.querySelector(".lin-card[data-maybe]")) {
          var key = document.createElement("p");
          key.className = "maybe-key";
          key.hidden = true;
          key.textContent = d.maybeKey || "Dashed: may have run it that year. The articles give no exact date.";
          page.querySelector(".year-pick").appendChild(key);
        }

        var q = parseInt(new URLSearchParams(window.location.search).get("year"), 10);
        setYear(q >= min && q <= max ? q : null);
      } catch (err) {
        console.error(err);
      }
    });
  }

  window.HARTLineage = { mount: mount };
})();
