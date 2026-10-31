// Session paperwork: crew sheets, YM-01, DS-01, station maps, TT-23, colors, EQ-01, spot sheets.
// Every page is a thin HTML shell that calls HARTCrew.page(kind, id); the content lives in data/crew.json.
(function () {
  var data = null;
  var site = null;

  var esc = HARTOps.esc;

  function u(rel) {
    return HARTOps.base() + rel;
  }

  function mapHref(id) {
    return u("crew/maps/" + id + "/index.html");
  }

  function spotHref(id) {
    return u("crew/industries/index.html") + "#" + id;
  }

  function colorById(id) {
    return (data.colors || []).filter(function (c) {
      return c.id === id;
    })[0];
  }

  function mapById(id) {
    return (data.maps || []).filter(function (m) {
      return m.id === id;
    })[0];
  }

  function pubLine(o) {
    var bits = [];
    if (o.pub) bits.push("Publication " + o.pub);
    if (o.revision) bits.push("Revision " + o.revision);
    if (o.effective) bits.push("Effective " + o.effective);
    return bits.join(" · ");
  }

  // —— Shared color chip ——
  function chip(c, opts) {
    if (!c) return "";
    opts = opts || {};
    var cls = "cchip" + (opts.dim ? " is-dim" : "") + (opts.small ? " is-small" : "");
    var inner = opts.swatchOnly ? "" : esc(c.label);
    return (
      '<span class="' + cls + '" style="--chip:' + esc(c.hex) + ";--chip-ink:" + esc(c.ink) + '"' +
      (opts.swatchOnly ? ' role="img" aria-label="' + esc(c.label) + '"' : "") +
      ">" + inner + "</span>"
    );
  }

  function chips(ids, opts) {
    return (ids || [])
      .map(function (id) {
        return chip(colorById(id), opts);
      })
      .join(" ");
  }

  function colorTable(withSpots) {
    return (
      '<div class="table-wrap"><table class="data-table color-table"><thead><tr><th>Color</th><th>Destination</th><th>Train</th></tr></thead><tbody>' +
      data.colors
        .map(function (c) {
          var dest = withSpots ? '<a href="' + spotHref(c.spot) + '">' + esc(c.dest) + "</a>" : esc(c.dest);
          return "<tr><td>" + chip(c) + "</td><td>" + dest + "</td><td>" + esc(c.train) + "</td></tr>";
        })
        .join("") +
      "</tbody></table></div>"
    );
  }

  function ttTable() {
    var tt = data.timetable;
    return (
      '<div class="table-wrap"><table class="data-table tt-table"><thead><tr>' +
      tt.columns
        .map(function (h) {
          return "<th>" + esc(h) + "</th>";
        })
        .join("") +
      "</tr></thead><tbody>" +
      tt.rows
        .map(function (r) {
          return "<tr><td>" + esc(r[0]) + "</td><th scope=\"row\">" + esc(r[1]) + "</th><td>" + esc(r[2]) + "</td></tr>";
        })
        .join("") +
      "</tbody></table></div>" +
      '<p class="tt-note">' + esc(tt.note) + "</p>"
    );
  }

  function sourceButton(rel, label) {
    // Published docx/pptx live in ../external (not on the public site): local desk only.
    if (!rel || (site && site.public)) return "";
    return '<a class="btn btn-ghost" href="' + esc(encodeURI(u(rel))) + '">' + esc(label || "Source docx") + "</a>";
  }

  function printButton(label) {
    return '<button type="button" class="btn btn-ghost" data-print>' + esc(label || "Print") + "</button>";
  }

  function wirePrint(root) {
    root.querySelectorAll("[data-print]").forEach(function (b) {
      b.addEventListener("click", function () {
        window.print();
      });
    });
  }

  // Closed <details> do not print; open the ones marked for print, then put them back.
  var printOpened = [];
  window.addEventListener("beforeprint", function () {
    printOpened = [];
    document.querySelectorAll("details[data-print-open]").forEach(function (d) {
      if (!d.open) {
        d.open = true;
        printOpened.push(d);
      }
    });
  });
  window.addEventListener("afterprint", function () {
    printOpened.forEach(function (d) {
      d.open = false;
    });
    printOpened = [];
  });

  // "Operations › Session paperwork ›" above the title.
  function extendCrumb(extra) {
    var crumb = document.querySelector("main .page-head .crumb ol");
    if (!crumb) return;
    (extra || []).forEach(function (e) {
      crumb.insertAdjacentHTML("beforeend", '<li><a href="' + esc(e.href) + '">' + esc(e.label) + "</a></li>");
    });
  }

  var PAPERWORK = function () {
    return { href: u("crew/index.html"), label: "Session paperwork" };
  };

  // —— Full-screen map viewer with pinch zoom ——
  var viewer = null;
  function openViewer(src, alt) {
    if (!viewer) viewer = buildViewer();
    viewer.open(src, alt);
  }

  function buildViewer() {
    var el = document.createElement("div");
    el.className = "zoomer";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-modal", "true");
    el.setAttribute("aria-label", "Map viewer");
    el.hidden = true;
    el.innerHTML =
      '<div class="zoomer-bar">' +
      '<button type="button" data-z="out" aria-label="Zoom out">−</button>' +
      '<button type="button" data-z="fit">Fit</button>' +
      '<button type="button" data-z="in" aria-label="Zoom in">+</button>' +
      '<button type="button" data-z="close" class="zoomer-close">Close</button>' +
      "</div>" +
      '<div class="zoomer-stage"><img alt=""></div>' +
      '<p class="zoomer-hint">Pinch or use + and − to zoom. <span class="rotate-hint">Turn your phone sideways for a bigger view.</span></p>';
    document.body.appendChild(el);
    var stage = el.querySelector(".zoomer-stage");
    var img = el.querySelector("img");
    var scale = 1;
    var lastFocus = null;

    function apply(newScale, cx, cy) {
      newScale = Math.max(1, Math.min(6, newScale));
      var rect = stage.getBoundingClientRect();
      if (cx == null) cx = rect.width / 2;
      if (cy == null) cy = rect.height / 2;
      var fx = (stage.scrollLeft + cx) / (img.offsetWidth || 1);
      var fy = (stage.scrollTop + cy) / (img.offsetHeight || 1);
      scale = newScale;
      img.style.width = scale * 100 + "%";
      stage.scrollLeft = fx * img.offsetWidth - cx;
      stage.scrollTop = fy * img.offsetHeight - cy;
    }

    el.querySelector(".zoomer-bar").addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      var z = b.getAttribute("data-z");
      if (z === "in") apply(scale * 1.5);
      else if (z === "out") apply(scale / 1.5);
      else if (z === "fit") apply(1);
      else if (z === "close") close();
    });

    var pinch = null;
    function dist(t) {
      var dx = t[0].clientX - t[1].clientX;
      var dy = t[0].clientY - t[1].clientY;
      return Math.sqrt(dx * dx + dy * dy);
    }
    stage.addEventListener(
      "touchstart",
      function (e) {
        if (e.touches.length === 2) {
          var r = stage.getBoundingClientRect();
          pinch = {
            d: dist(e.touches),
            s: scale,
            cx: (e.touches[0].clientX + e.touches[1].clientX) / 2 - r.left,
            cy: (e.touches[0].clientY + e.touches[1].clientY) / 2 - r.top,
          };
        }
      },
      { passive: true }
    );
    stage.addEventListener(
      "touchmove",
      function (e) {
        if (pinch && e.touches.length === 2) {
          e.preventDefault();
          apply(pinch.s * (dist(e.touches) / pinch.d), pinch.cx, pinch.cy);
        }
      },
      { passive: false }
    );
    stage.addEventListener("touchend", function (e) {
      if (e.touches.length < 2) pinch = null;
    });
    stage.addEventListener("dblclick", function (e) {
      var r = stage.getBoundingClientRect();
      apply(scale > 1 ? 1 : 2.5, e.clientX - r.left, e.clientY - r.top);
    });
    stage.addEventListener(
      "wheel",
      function (e) {
        if (!e.ctrlKey) return;
        e.preventDefault();
        var r = stage.getBoundingClientRect();
        apply(scale * (e.deltaY < 0 ? 1.15 : 1 / 1.15), e.clientX - r.left, e.clientY - r.top);
      },
      { passive: false }
    );
    document.addEventListener("keydown", function (e) {
      if (el.hidden) return;
      HARTOps.trapTab(el, e);
      if (e.key === "Escape") close();
      if (e.key === "+" || e.key === "=") apply(scale * 1.5);
      if (e.key === "-") apply(scale / 1.5);
    });

    function close() {
      el.hidden = true;
      document.documentElement.classList.remove("zoomer-open");
      if (lastFocus) lastFocus.focus();
    }

    return {
      open: function (src, alt) {
        lastFocus = document.activeElement;
        img.src = src;
        img.alt = alt || "";
        el.hidden = false;
        document.documentElement.classList.add("zoomer-open");
        scale = 1;
        img.style.width = "100%";
        stage.scrollTop = 0;
        stage.scrollLeft = 0;
        el.querySelector(".zoomer-close").focus();
      },
    };
  }

  function wireZoom(root) {
    root.querySelectorAll("[data-zoom]").forEach(function (b) {
      b.addEventListener("click", function () {
        var img = b.querySelector("img");
        openViewer(img.currentSrc || img.src, img.alt);
      });
    });
  }

  function mapCard(m) {
    if (!m) return "";
    return (
      '<a class="map-card" href="' + mapHref(m.id) + '">' +
      '<img src="' + esc(u(m.img)) + '" alt="" loading="lazy">' +
      "<span><strong>" + esc(m.title) + "</strong><small>" + esc(m.pub) + "</small></span></a>"
    );
  }

  // —— Crew sheet / YM-01 / DS-01 ——
  function storageKey(job) {
    return "hart.crew." + job.id + ".steps";
  }

  function readTicks(job) {
    try {
      return JSON.parse(localStorage.getItem(storageKey(job)) || "[]") || [];
    } catch (e) {
      return [];
    }
  }

  function writeTicks(job, ticks) {
    try {
      localStorage.setItem(storageKey(job), JSON.stringify(ticks));
    } catch (e) {}
  }

  function renderSheet(job) {
    var root = document.getElementById("crew-root");
    var head = document.getElementById("sheet-head");
    document.title = job.code + " " + job.name + " — HART";
    var engine = "";
    if (job.engine) {
      engine =
        '<div class="sheet-engine">' +
        (job.engine.img
          ? '<img src="' + esc(u(job.engine.img)) + '" alt="' + esc(job.engine.label) + '" width="160" height="45">'
          : '<span class="engine-none" aria-hidden="true">?</span>') +
        "<span><small>Engine</small>" + esc(job.engine.label) + "</span></div>";
    }
    head.innerHTML =
      '<div class="sheet-id"><p class="sheet-code">' + esc(job.code) + "</p>" +
      "<div><h1>" + esc(job.name) + '</h1><p class="sheet-pub">' + esc(job.pub) + " · Rev " + esc(job.revision) +
      ' <span class="sheet-eff">· Effective ' + esc(job.effective) + "</span></p></div></div>" +
      engine;

    var html = '<p class="sheet-summary">' + esc(job.summary) + "</p>";

    if (job.priority) {
      html +=
        '<section class="sheet-sec" aria-labelledby="prio-h"><h2 id="prio-h">Priority</h2><ol class="prio-strip">' +
        job.priority
          .map(function (p) {
            return "<li><span>" + esc(p) + "</span></li>";
          })
          .join("") +
        '</ol><p class="muted small">When moves conflict, the train further left goes first.</p></section>';
    }

    if (job.steps) {
      var ticks = readTicks(job);
      html +=
        '<section class="sheet-sec" aria-labelledby="steps-h"><div class="sec-head"><h2 id="steps-h">Crew steps</h2>' +
        '<button type="button" class="link-btn no-print" data-reset>Clear ticks</button></div><ol class="steps">' +
        job.steps
          .map(function (s, i) {
            return (
              '<li><label><input type="checkbox" class="no-print" data-step="' + i + '"' +
              (ticks[i] ? " checked" : "") + "><span>" + esc(s) + "</span></label></li>"
            );
          })
          .join("") +
        "</ol></section>";
    }

    function rowsTable(title, rows, actionHead) {
      return (
        '<section class="sheet-sec"><h2>' + esc(title) + '</h2><ol class="seq">' +
        rows
          .map(function (r) {
            return (
              '<li><span class="seq-n">' + esc(r.n) + '</span><div><p class="seq-train">' + esc(r.train) + "</p>" +
              '<p class="seq-action">' + esc(r.action) + "</p>" +
              (r.colors ? '<p class="seq-chips">' + chips(r.colors, { small: true }) + "</p>" : "") +
              "</div></li>"
            );
          })
          .join("") +
        "</ol></section>"
      );
    }
    if (job.sequence) html += rowsTable("Sequence", job.sequence);
    if (job.lineup) html += rowsTable("Train lineup", job.lineup);

    var mine = job.colors || [];
    var all = mine.length >= data.colors.length;
    html +=
      '<section class="sheet-sec sheet-colors" aria-labelledby="colors-h"><h2 id="colors-h">' +
      (all ? "Destination colors" : "Your colors") + "</h2>" +
      (all ? "" : '<p class="muted small">Your blocks are bright; the rest are dimmed.</p>') +
      '<ul class="cc-list">' +
      data.colors
        .map(function (c) {
          var on = mine.indexOf(c.id) !== -1;
          return (
            '<li class="' + (on ? "is-mine" : "is-other") + '">' + chip(c, { dim: !on }) +
            '<a href="' + spotHref(c.spot) + '">' + esc(c.dest) + "</a><small>" + esc(c.train) + "</small></li>"
          );
        })
        .join("") +
      "</ul></section>";

    if (job.maps && job.maps.length) {
      html +=
        '<section class="sheet-sec no-print" aria-labelledby="where-h"><h2 id="where-h">Where you work</h2><div class="map-cards">' +
        job.maps.map(function (id) {
          return mapCard(mapById(id));
        }).join("") +
        '</div><p class="small"><a href="' + u("crew/maps/index.html") + '">All station maps</a></p></section>';
    }

    if (job.talk && job.talk.length) {
      html +=
        '<section class="sheet-sec no-print" aria-labelledby="talk-h"><h2 id="talk-h">Who you talk to</h2><dl class="talk">' +
        job.talk
          .map(function (t) {
            return "<dt>" + esc(t.who) + "</dt><dd>" + esc(t.why) + "</dd>";
          })
          .join("") +
        "</dl>" +
        (job.links || [])
          .map(function (l) {
            return '<p class="small"><a href="' + u(l.href) + '">' + esc(l.label) + "</a></p>";
          })
          .join("") +
        "</section>";
    }

    html +=
      '<details class="sheet-more print-back" data-print-open' + (job.ttOpen ? " open" : "") + ">" +
      "<summary>Route 23 timetable (TT-23)</summary>" +
      '<div class="back-page"><figure class="back-map print-only"><img src="' + esc(u("assets/maps/station_map_diagram_only.png")) +
      '" alt="Subdivision diagram"></figure><div>' + ttTable() +
      '<p class="small no-print"><a href="' + u("crew/tt23/index.html") + '">Full timetable page</a></p></div></div></details>';

    html +=
      '<details class="sheet-more no-print"><summary>All destination colors</summary>' + colorTable(true) + "</details>";

    html +=
      '<div class="sheet-actions no-print">' + printButton("Print 5×8 card") + sourceButton(job.source) +
      '<a class="btn btn-ghost" href="' + u("crew/index.html") + '">All sheets</a>' +
      '<a class="btn btn-ghost" href="' + u("briefing/index.html") + '">Primer</a></div>';

    root.innerHTML = html;

    root.querySelectorAll("[data-step]").forEach(function (box) {
      box.addEventListener("change", function () {
        var t = readTicks(job);
        t[Number(box.getAttribute("data-step"))] = box.checked;
        writeTicks(job, t);
      });
    });
    var reset = root.querySelector("[data-reset]");
    if (reset) {
      reset.addEventListener("click", function () {
        writeTicks(job, []);
        root.querySelectorAll("[data-step]").forEach(function (b) {
          b.checked = false;
        });
      });
    }
    wirePrint(root);
  }

  // —— Station map page ——
  function renderMap(m) {
    var root = document.getElementById("crew-root");
    document.title = m.title + " station map — HART";
    document.getElementById("page-title").textContent = m.title;
    document.getElementById("page-pub").textContent = pubLine(m);
    document.getElementById("page-lede").textContent = m.what;

    var toggle = "";
    if (m.rotated) {
      toggle =
        '<div class="seg no-print" role="group" aria-label="Map orientation">' +
        '<button type="button" aria-pressed="true" data-src="' + esc(u(m.img)) + '">Standard</button>' +
        '<button type="button" aria-pressed="false" data-src="' + esc(u(m.rotated)) + '">Rotated (desk view)</button></div>';
    }

    var tracks =
      '<section class="sheet-sec no-print"><h2>Tracks</h2><div class="table-wrap"><table class="data-table"><thead><tr><th>Track</th><th>What is there</th><th>Color</th></tr></thead><tbody>' +
      m.tracks
        .map(function (t) {
          var purpose = esc(t.purpose);
          if (t.spots) {
            purpose +=
              '<br><span class="small">' +
              t.spots
                .map(function (s) {
                  var label = t.spots.length > 1 ? "Spot sheet: " + spotName(s) : "Spot sheet";
                  return '<a href="' + spotHref(s) + '">' + esc(label) + "</a>";
                })
                .join(" · ") +
              "</span>";
          }
          if (t.map) purpose += '<br><a class="small" href="' + mapHref(t.map) + '">' + esc(mapById(t.map).title) + " map</a>";
          return "<tr><th scope=\"row\">" + esc(t.track) + "</th><td>" + purpose + "</td><td>" + chips(t.colors, { small: true }) + "</td></tr>";
        })
        .join("") +
      "</tbody></table></div></section>";

    var switches =
      '<section class="sheet-sec no-print"><h2>Switches</h2><div class="table-wrap"><table class="data-table"><thead><tr><th>No.</th><th>What it does</th></tr></thead><tbody>' +
      m.switches
        .map(function (s) {
          return '<tr><th scope="row"><span class="sw-badge">' + esc(s.n) + "</span></th><td>" + esc(s.what) + "</td></tr>";
        })
        .join("") +
      "</tbody></table></div></section>";

    var connects =
      '<section class="sheet-sec no-print"><h2>Connects to</h2><div class="map-cards">' +
      (m.connects || []).map(function (id) {
        return mapCard(mapById(id));
      }).join("") +
      "</div></section>";

    root.innerHTML =
      toggle +
      '<figure class="map-figure"><button type="button" class="map-open" data-zoom aria-label="Open ' + esc(m.title) +
      ' map full screen"><img src="' + esc(u(m.img)) + '" alt="' + esc(m.alt) + '" width="1600" height="1000"></button>' +
      '<figcaption class="no-print">Tap the map to zoom. <span class="rotate-hint">Turn your phone sideways for a bigger view.</span></figcaption></figure>' +
      tracks + switches + connects +
      '<div class="sheet-actions no-print">' + printButton("Print map (8×5)") + sourceButton(m.source) +
      '<a class="btn btn-ghost" href="' + u("crew/maps/index.html") + '">All maps</a>' +
      '<a class="btn btn-ghost" href="' + u("crew/index.html") + '">Session paperwork</a></div>';

    root.querySelectorAll(".seg button").forEach(function (b) {
      b.addEventListener("click", function () {
        root.querySelectorAll(".seg button").forEach(function (o) {
          o.setAttribute("aria-pressed", o === b ? "true" : "false");
        });
        root.querySelector(".map-figure img").src = b.getAttribute("data-src");
      });
    });
    wireZoom(root);
    wirePrint(root);
  }

  function spotName(id) {
    var all = (data.spotsheet.industries || []).concat(data.spotsheet.offline || []);
    var hit = all.filter(function (i) {
      return i.id === id;
    })[0];
    return hit ? hit.name : id;
  }

  function renderMapsIndex() {
    var root = document.getElementById("crew-root");
    var o = data.overview;
    root.innerHTML =
      '<section class="maps-index">' +
      '<figure class="key-map"><button type="button" class="map-open" data-zoom aria-label="Open the subdivision diagram full screen">' +
      '<img src="' + esc(u(o.img)) + '" alt="' + esc(o.alt) + '"></button>' +
      "<figcaption><strong>" + esc(o.title) + "</strong> · " + esc(pubLine(o)) + "<br>" + esc(o.what) +
      ' <span class="no-print">Tap to zoom.</span></figcaption></figure>' +
      '<div><h2 class="sub-h">Station maps</h2><ul class="map-list">' +
      data.maps
        .map(function (m) {
          return (
            '<li><a href="' + mapHref(m.id) + '"><img src="' + esc(u(m.img)) + '" alt="" loading="lazy">' +
            "<span><strong>" + esc(m.title) + "</strong><small>" + esc(m.pub + (m.revision ? " · Rev " + m.revision : "")) +
            "</small><em>" + esc(m.what) + "</em></span></a></li>"
          );
        })
        .join("") +
      "</ul></div></section>" +
      '<div class="sheet-actions no-print">' + sourceButton(o.source, "SM-01 source docx") +
      '<a class="btn btn-ghost" href="' + u("crew/index.html") + '">Session paperwork</a></div>';
    wireZoom(root);
  }

  // —— Reference pages ——
  function renderColors() {
    var root = document.getElementById("crew-root");
    function group(g, title) {
      return (
        '<section class="sheet-sec"><h2>' + esc(title) + '</h2><ul class="cc-list cc-big">' +
        data.colors
          .filter(function (c) {
            return c.group === g;
          })
          .map(function (c) {
            return '<li>' + chip(c) + '<a href="' + spotHref(c.spot) + '">' + esc(c.dest) + "</a><small>" + esc(c.train) + "</small></li>";
          })
          .join("") +
        "</ul></section>"
      );
    }
    root.innerHTML =
      group("island", "Local industries") +
      group("interchange", "Interchange") +
      '<details class="sheet-more" data-print-open><summary>As a table</summary>' + colorTable(true) + "</details>" +
      '<div class="sheet-actions no-print">' + printButton() +
      '<a class="btn btn-ghost" href="' + u("crew/index.html") + '">Session paperwork</a></div>';
    wirePrint(root);
  }

  function renderTT23() {
    var root = document.getElementById("crew-root");
    var tt = data.timetable;
    document.getElementById("page-pub").textContent = pubLine(tt);
    root.innerHTML =
      '<p class="tt-sub">' + esc(tt.subtitle) + "</p>" +
      '<div class="tt-layout"><div>' + ttTable() + "</div>" +
      '<section class="sheet-sec"><h2>Special instructions</h2><ol>' +
      tt.instructions
        .map(function (i) {
          return "<li>" + esc(i) + "</li>";
        })
        .join("") +
      '</ol><p class="muted small">' + esc(tt.bulletin) + "</p>" +
      '<p class="small no-print">Where the stations are: <a href="' + u("crew/maps/index.html") + '">subdivision diagram and station maps</a>.</p></section></div>' +
      '<div class="sheet-actions no-print">' + printButton() + sourceButton(tt.source, "Source pptx") +
      '<a class="btn btn-ghost" href="' + u("crew/dispatcher/index.html") + '">Dispatcher train list</a>' +
      '<a class="btn btn-ghost" href="' + u("crew/index.html") + '">Session paperwork</a></div>';
    wirePrint(root);
  }

  function renderScale() {
    var root = document.getElementById("crew-root");
    var s = data.scale;
    document.getElementById("page-pub").textContent = pubLine(s);
    root.innerHTML =
      '<p class="sheet-summary">' + esc(s.summary) + "</p>" +
      s.sections
        .map(function (sec) {
          return (
            '<section class="sheet-sec"><h2>' + esc(sec.heading) + "</h2>" +
            sec.parts
              .map(function (p) {
                var tag = p.ordered ? "ol" : "ul";
                return (
                  "<h3>" + esc(p.h) + "</h3><" + tag + ' class="rule-list">' +
                  p.items
                    .map(function (i) {
                      var m = /^(PASS|REJECTED) — (.*)$/.exec(i);
                      if (m) return '<li><strong class="verdict verdict-' + m[1].toLowerCase() + '">' + m[1] + "</strong> " + esc(m[2]) + "</li>";
                      return "<li>" + esc(i) + "</li>";
                    })
                    .join("") +
                  "</" + tag + ">"
                );
              })
              .join("") +
            "</section>"
          );
        })
        .join("") +
      '<div class="sheet-actions no-print">' + printButton() + sourceButton(s.source) +
      '<a class="btn btn-ghost" href="' + u("crew/ck1/index.html") + '">CK1 crew sheet</a>' +
      '<a class="btn btn-ghost" href="' + u("crew/index.html") + '">Session paperwork</a></div>';
    wirePrint(root);
  }

  function renderIndustries() {
    var root = document.getElementById("crew-root");
    var sh = data.spotsheet;
    var jump =
      '<nav class="jump no-print" aria-label="Jump to"><ul>' +
      sh.industries
        .concat(sh.offline)
        .map(function (i) {
          return '<li><a href="#' + esc(i.id) + '">' + chip(colorById(i.color), { small: true, swatchOnly: true }) + esc(i.name) + "</a></li>";
        })
        .join("") +
      sh.desk
        .map(function (d) {
          return '<li><a href="#' + esc(d.id) + '">' + esc(d.name) + "</a></li>";
        })
        .join("") +
      "</ul></nav>";

    function where(i) {
      var m = mapById(i.map);
      if (!m) return "";
      return '<a href="' + mapHref(m.id) + '">' + esc(m.title) + " map</a>";
    }

    var inds = sh.industries
      .map(function (i) {
        var head = i.trackHead || ["Spot", "Track", "Cars", "In", "Out"];
        return (
          '<section class="panel spot-sheet" id="' + esc(i.id) + '"><div class="spot-head">' + chip(colorById(i.color)) +
          "<h2>" + esc(i.name) + '</h2></div><p class="spot-meta">Track ' + esc(i.track) + " · " + where(i) +
          " · Served by " + esc(i.served) + "</p>" +
          // The company history from the operator sheet, open under the header; off the printed card.
          '<details class="spot-history no-print" open><summary>About the company</summary><ul>' +
          i.history.map(function (h) {
            return "<li>" + esc(h) + "</li>";
          }).join("") +
          "</ul></details>" +
          '<p class="spot-traffic"><strong>Traffic:</strong> ' + esc(i.traffic) + "</p>" +
          '<h3>' + (i.trackHead ? "Tracks" : "Tracks &amp; spots") + '</h3><div class="table-wrap"><table class="data-table"><thead><tr>' +
          head.map(function (h) {
            return "<th>" + esc(h) + "</th>";
          }).join("") +
          "</tr></thead><tbody>" +
          i.spots
            .map(function (r) {
              return "<tr>" + r.map(function (c, ci) {
                return ci === 0 ? '<th scope="row">' + esc(c) + "</th>" : "<td>" + esc(c) + "</td>";
              }).join("") + "</tr>";
            })
            .join("") +
          "</tbody></table></div>" +
          (i.spotNote ? '<p class="small muted">' + esc(i.spotNote) + "</p>" : "") +
          "</section>"
        );
      })
      .join("");

    function list(label, items, ordered) {
      var tag = ordered ? "ol" : "ul";
      return "<h3>" + esc(label) + "</h3><" + tag + ">" + items.map(function (x) {
        return "<li>" + esc(x) + "</li>";
      }).join("") + "</" + tag + ">";
    }

    var off = sh.offline
      .map(function (o) {
        return (
          '<section class="panel spot-sheet" id="' + esc(o.id) + '"><div class="spot-head">' + chip(colorById(o.color)) +
          "<h2>" + esc(o.name) + '</h2></div><p class="spot-meta">' + esc(o.tag) + " · " + where(o) + "</p>" +
          o.about.map(function (p) {
            return "<p>" + esc(p) + "</p>";
          }).join("") +
          '<div class="two-col">' + "<div>" + list(o.inLabel, o.inbound) + "</div><div>" + list(o.outLabel, o.outbound) + "</div></div>" +
          list("Jobs", o.jobs) + "</section>"
        );
      })
      .join("");

    var desk = sh.desk
      .map(function (d) {
        return (
          '<section class="panel spot-sheet" id="' + esc(d.id) + '"><h2>' + esc(d.name) + '</h2><p class="spot-meta">' + esc(d.tag) +
          (d.map ? " · " + where(d) : "") + "</p>" +
          d.about.map(function (p) {
            return "<p>" + esc(p) + "</p>";
          }).join("") +
          d.lists.map(function (l) {
            return list(l.label, l.items, l.ordered);
          }).join("") +
          "</section>"
        );
      })
      .join("");

    root.innerHTML =
      '<p class="sheet-summary">' + esc(sh.summary) + "</p>" + jump +
      '<h2 class="sub-h">On the island</h2>' + inds +
      '<h2 class="sub-h">Interchange</h2>' + off +
      '<h2 class="sub-h">Yard and desk notes</h2>' + desk +
      '<div class="sheet-actions no-print">' + printButton() + sourceButton(sh.source) +
      '<a class="btn btn-ghost" href="' + u("briefing/index.html#industries") + '">Industries</a>' +
      '<a class="btn btn-ghost" href="' + u("crew/index.html") + '">Session paperwork</a></div>';
    wirePrint(root);
    // Re-apply the hash now that the anchors exist.
    if (location.hash) {
      var t = document.getElementById(decodeURIComponent(location.hash.slice(1)));
      if (t) t.scrollIntoView();
    }
  }

  // The publications shelf links here with #print: wait for the images, then open the print dialog.
  function printWhenReady() {
    var imgs = Array.prototype.slice.call(document.querySelectorAll("#crew-root img"));
    Promise.all(
      imgs.map(function (img) {
        img.loading = "eager";
        return img.complete
          ? null
          : new Promise(function (res) {
              img.addEventListener("load", res);
              img.addEventListener("error", res);
            });
      })
    ).then(function () {
      try {
        history.replaceState(null, "", location.pathname + location.search);
      } catch (e) {}
      setTimeout(function () {
        window.print();
      }, 150);
    });
  }

  async function page(kind, id) {
    var pageId = {
      sheet: "crew-sheet",
      map: "crew-map",
      maps: "crew-maps",
      colors: "crew-colors",
      tt23: "crew-tt23",
      scale: "crew-scale",
      industries: "crew-industries",
    }[kind];
    var root = document.getElementById("crew-root");
    try {
      site = await HARTOps.mountChrome(pageId);
      var crumbs = [PAPERWORK()];
      if (kind === "map") crumbs.push({ href: u("crew/maps/index.html"), label: "Station maps" });
      extendCrumb(crumbs);
      data = await HARTOps.loadJson("data/crew.json");
      if (kind === "sheet") {
        var job = (data.jobs || []).filter(function (j) {
          return j.id === id;
        })[0];
        if (!job) throw new Error("No job " + id);
        renderSheet(job);
      } else if (kind === "map") {
        var m = mapById(id);
        if (!m) throw new Error("No map " + id);
        renderMap(m);
      } else if (kind === "maps") renderMapsIndex();
      else if (kind === "colors") renderColors();
      else if (kind === "tt23") renderTT23();
      else if (kind === "scale") renderScale();
      else if (kind === "industries") renderIndustries();
      if (location.hash === "#print") printWhenReady();
    } catch (err) {
      console.error(err);
      if (root) {
        HARTOps.renderError(root, {
          what: "this sheet",
          err: err,
          links: [{ href: "docs/index.html", label: "Publications shelf" }],
        });
      }
    }
  }

  window.HARTCrew = { page: page, chip: chip };
})();
