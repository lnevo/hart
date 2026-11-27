// Photo galleries from data/gallery.json: the Layout tab of Photos (albums, Grid / List / Gallery views) and the
// build chronology (one album as a month timeline). On the local review server the owner can move, reorder and
// caption photos (opts.curate names the API). The HTML is drawn by plain functions (HARTGallery.lib); mount() keeps
// the state and the listeners. Tests: scripts/tests/gallery_view_test.js.
(function () {
  var esc = HARTOps.esc;

  function resolveSrc(src) {
    if (!src) return "";
    if (/^https?:\/\//i.test(src) || src.startsWith("data:")) return src;
    // Paths in the JSON (assets/…, ../external/…) are relative to the portal root;
    // prefix the page's depth so they resolve from any nesting level.
    return HARTOps.base() + src;
  }

  var MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

  // "2025-08-09" -> {y, m, d}; null when the item has no usable date.
  function parseDate(s) {
    var m = /^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(String(s || ""));
    return m ? { y: +m[1], m: +m[2], d: m[3] ? +m[3] : 0 } : null;
  }

  function longDate(s) {
    var p = parseDate(s);
    if (!p) return "";
    return (p.d ? p.d + " " : "") + MONTHS[p.m - 1] + " " + p.y;
  }

  // —— Grid / List / Gallery, as on Rolling stock and Historical, remembered per browser ——
  var VIEW_KEY = "hart.gallery.view";
  var VIEWS = [
    { id: "grid", label: "Grid" },
    { id: "list", label: "List" },
    { id: "gallery", label: "Gallery" },
  ];

  function storedView() {
    try {
      var saved = localStorage.getItem(VIEW_KEY);
      return VIEWS.some(function (v) { return v.id === saved; }) ? saved : "grid";
    } catch (e) {
      return "grid"; // no storage (a private window): the page opens on Grid
    }
  }

  function storeView(view) {
    try {
      localStorage.setItem(VIEW_KEY, view);
    } catch (e) {
      return; // no storage: the view lasts until the page closes
    }
  }

  function viewBarHtml(view) {
    return VIEWS.map(function (v) {
      return '<button type="button" data-view="' + v.id + '" aria-pressed="' + (v.id === view) + '">' + v.label + "</button>";
    }).join("");
  }

  // —— Albums ——
  // only (opts.albums) limits a page to those album ids, in that order; null keeps them all.
  function scopeItems(list, only) {
    if (!only) return list || [];
    return (list || []).filter(function (it) {
      return only.indexOf(it.album) !== -1;
    });
  }

  function scopeAlbums(albums, only) {
    if (!only) return albums || [];
    return only
      .map(function (id) {
        return (albums || []).find(function (a) { return a.id === id; });
      })
      .filter(Boolean);
  }

  function albumLabel(albums, id) {
    var a = (albums || []).find(function (x) { return x.id === id; });
    return a ? a.label : "";
  }

  // One button per album with its count, and "All" first when there is more than one.
  function albumBarHtml(albums, total, current) {
    var bar = albums.map(function (a) {
      return { id: a.id, label: a.label, count: a.count };
    });
    if (bar.length > 1) bar.unshift({ id: "all", label: "All", count: total });
    return bar
      .map(function (a) {
        return (
          '<button type="button" data-album="' + esc(a.id) + '" aria-pressed="' + (a.id === current ? "true" : "false") + '">' +
          esc(a.label) + " (" + a.count + ")</button>"
        );
      })
      .join("");
  }

  // —— The photos ——
  function sizeAttrs(it) {
    return it.width && it.height ? ' width="' + Number(it.width) + '" height="' + Number(it.height) + '"' : "";
  }

  // The build's thumbnail (item.thumb) for the grid and lists; the lightbox opens the full src.
  function thumbImg(it, alt) {
    return '<img src="' + esc(resolveSrc(it.thumb || it.src)) + '" alt="' + esc(alt) + '"' + sizeAttrs(it) + ' loading="lazy" decoding="async">';
  }

  function curateControls(it, albums) {
    var albumOpts = (albums || [])
      .map(function (a) {
        return '<option value="' + esc(a.id) + '"' + (a.id === it.album ? " selected" : "") + ">" + esc(a.label) + "</option>";
      })
      .join("");
    var s = esc(it.src);
    return (
      '<div class="g-curate">' +
      '<select data-c-album="' + s + '" aria-label="Album">' + albumOpts + "</select>" +
      '<button type="button" data-c-move="up" data-src="' + s + '" aria-label="Move earlier">↑</button>' +
      '<button type="button" data-c-move="down" data-src="' + s + '" aria-label="Move later">↓</button>' +
      '<button type="button" data-c-edit="' + s + '">Edit</button>' +
      '<button type="button" data-c-archive="' + s + '">→ Photos review</button>' +
      "</div>"
    );
  }

  // One grid cell. look: {byMonth, canEdit, albums}; a month timeline shows the day and month on each photo.
  function cellHtml(it, i, look) {
    var p = look.byMonth ? parseDate(it.date) : null;
    var when = p ? '<time datetime="' + esc(it.date) + '">' + (p.d ? p.d + " " : "") + MONTHS[p.m - 1].slice(0, 3) + "</time>" : "";
    return (
      (look.canEdit ? '<div class="g-cell">' : "") +
      '<button type="button" class="g-item" data-idx="' + i + '">' + thumbImg(it, it.title) +
      "<figcaption>" + when + "<strong>" + esc(it.title) + "</strong><span>" + esc(it.caption) + "</span></figcaption></button>" +
      (look.canEdit ? curateControls(it, look.albums) + "</div>" : "")
    );
  }

  // The timeline: one row per month, in the album's own order.
  function monthGroupsHtml(visible, look) {
    var groups = [];
    visible.forEach(function (it, i) {
      var p = parseDate(it.date);
      var key = p ? p.y + "-" + p.m : "undated";
      var last = groups[groups.length - 1];
      if (!last || last.key !== key) {
        last = { key: key, label: p ? MONTHS[p.m - 1] : "Undated", year: p ? p.y : "", cells: [] };
        groups.push(last);
      }
      last.cells.push(cellHtml(it, i, look));
    });
    return groups
      .map(function (g) {
        return (
          '<section class="g-month"><h3 class="g-month-label">' + esc(g.label) + " <span>" + esc(g.year) + "</span></h3>" +
          '<div class="g-strip">' + g.cells.join("") + "</div></section>"
        );
      })
      .join("");
  }

  function gridHtml(visible, look) {
    return look.byMonth ? monthGroupsHtml(visible, look) : visible.map(function (it, i) { return cellHtml(it, i, look); }).join("");
  }

  function listHtml(visible, albums) {
    return (
      '<div class="fleet-list-wrap"><table class="fleet-list">' +
      '<thead><tr><th></th><th>Photo</th><th>Album</th><th>Date</th><th class="fl-note">Caption</th></tr></thead><tbody>' +
      visible
        .map(function (it, i) {
          return (
            '<tr data-idx="' + i + '" tabindex="0">' +
            '<td class="fl-thumb">' + thumbImg(it, "") + "</td>" +
            "<td>" + esc(it.title) + "</td>" +
            "<td>" + esc(albumLabel(albums, it.album)) + "</td>" +
            '<td class="fl-num">' + esc(longDate(it.date) || "—") + "</td>" +
            '<td class="fl-note">' + esc(it.caption) + "</td></tr>"
          );
        })
        .join("") +
      "</tbody></table></div>"
    );
  }

  // The Gallery view: photo stageIndex large, with a strip of every photo under it.
  function stageHtml(visible, stageIndex) {
    var it = visible[stageIndex];
    return (
      '<div class="fleet-stage">' +
      '<button type="button" class="fleet-stage-nav prev" aria-label="Previous">‹</button>' +
      '<figure><img src="' + esc(resolveSrc(it.src)) + '" alt="' + esc(it.title) + '">' +
      "<figcaption><strong>" + esc(it.title) + "</strong> " +
      '<span class="muted">' + (stageIndex + 1) + " of " + visible.length + "</span><br>" +
      esc(it.caption) + "</figcaption></figure>" +
      '<button type="button" class="fleet-stage-nav next" aria-label="Next">›</button>' +
      "</div>" +
      '<div class="fleet-strip" role="list">' +
      visible
        .map(function (x, i) {
          return (
            '<button type="button" role="listitem" data-stage="' + i + '"' + (i === stageIndex ? ' aria-current="true"' : "") +
            ' title="' + esc(x.title) + '">' + thumbImg(x, x.title) + "</button>"
          );
        })
        .join("") +
      "</div>"
    );
  }

  // (i + d) wrapped into 0..n-1; null when there is nothing to step through.
  function wrapIndex(i, d, n) {
    return n ? (i + d + n) % n : null;
  }

  // —— Photo viewer ——
  // A modal dialog like the crew map viewer: focus on Close, Tab kept inside, Esc closes, focus goes back to the
  // photo that opened it. photoAt(i) gives photo i of what is shown now; count() how many there are.
  function makeLightbox(photoAt, count) {
    var lb = document.createElement("div");
    lb.className = "lightbox";
    lb.setAttribute("role", "dialog");
    lb.setAttribute("aria-modal", "true");
    lb.setAttribute("aria-labelledby", "g-lightbox-title");
    lb.innerHTML =
      '<button type="button" class="lightbox-close" aria-label="Close">Close</button>' +
      '<button type="button" class="lightbox-nav prev" aria-label="Previous">‹</button>' +
      '<button type="button" class="lightbox-nav next" aria-label="Next">›</button>' +
      '<div class="lightbox-card">' +
      '<img alt="">' +
      '<div class="meta"><h2 id="g-lightbox-title"></h2><p></p><div class="credit"></div></div>' +
      "</div>";
    document.body.appendChild(lb);
    var index = 0;
    var returnTo = null;
    var img = lb.querySelector("img");
    var h = lb.querySelector("h2");
    var p = lb.querySelector("p");
    var credit = lb.querySelector(".credit");

    function paint() {
      var it = photoAt(index);
      if (!it) return;
      img.src = resolveSrc(it.src);
      img.alt = it.title || "";
      h.textContent = it.title || "";
      p.textContent = it.caption || "";
      credit.textContent = [longDate(it.date), it.credit].filter(Boolean).join(" · ");
    }

    function open(i) {
      index = i;
      paint();
      returnTo = document.activeElement;
      lb.classList.add("open");
      lb.querySelector(".lightbox-close").focus();
    }

    function close() {
      lb.classList.remove("open");
      if (returnTo && returnTo.focus) returnTo.focus();
      returnTo = null;
    }

    function step(d) {
      var next = wrapIndex(index, d, count());
      if (next === null) return;
      index = next;
      paint();
    }

    lb.querySelector(".lightbox-close").addEventListener("click", close);
    lb.addEventListener("click", function (e) {
      if (e.target === lb) close();
    });
    lb.querySelector(".prev").addEventListener("click", function (e) {
      e.stopPropagation();
      step(-1);
    });
    lb.querySelector(".next").addEventListener("click", function (e) {
      e.stopPropagation();
      step(1);
    });
    document.addEventListener("keydown", function (e) {
      if (!lb.classList.contains("open")) return;
      HARTOps.trapTab(lb, e);
      if (e.key === "Escape") close();
      if (e.key === "ArrowLeft") step(-1);
      if (e.key === "ArrowRight") step(1);
    });
    return { open: open };
  }

  // —— Local curation (engineering desk only) ——
  // opts.curate names the API; it is used only when the site is not public and the review server answers.
  async function curationOn(curate) {
    if (!curate) return false;
    try {
      var site = await HARTOps.loadSite();
      return !site.public && (await fetch(curate + "/ping", { cache: "no-cache" })).ok;
    } catch (e) {
      return false; // no site.json or no review server: the page is read-only
    }
  }

  // The curation controls under each grid cell; run(src, changes, message) saves one change.
  function bindCurate(grid, findItem, run) {
    grid.querySelectorAll("[data-c-album]").forEach(function (el) {
      el.addEventListener("change", function () {
        run(el.getAttribute("data-c-album"), { album: el.value }, "Moved to " + el.options[el.selectedIndex].text);
      });
    });
    grid.querySelectorAll("[data-c-move]").forEach(function (el) {
      el.addEventListener("click", function () {
        run(el.getAttribute("data-src"), { move: el.getAttribute("data-c-move") }, "Reordered");
      });
    });
    grid.querySelectorAll("[data-c-edit]").forEach(function (el) {
      el.addEventListener("click", function () {
        var src = el.getAttribute("data-c-edit");
        var it = findItem(src) || {};
        var t = window.prompt("Title", it.title || "");
        if (t === null) return;
        var c = window.prompt("Caption", it.caption || "");
        if (c === null) return;
        run(src, { title: t, caption: c }, "Saved “" + t + "”");
      });
    });
    grid.querySelectorAll("[data-c-archive]").forEach(function (el) {
      el.addEventListener("click", function () {
        run(el.getAttribute("data-c-archive"), { to_archive: true }, "Sent to Photos › To review");
      });
    });
  }

  function makeToast(toast) {
    var timer = null;
    return function (msg, bad) {
      if (!toast) return;
      toast.textContent = msg;
      toast.classList.toggle("bad", !!bad);
      toast.classList.add("show");
      clearTimeout(timer);
      timer = setTimeout(function () {
        toast.classList.remove("show");
      }, 2600);
    };
  }

  // —— The page ——
  // opts: dataUrl, albums (ids this page shows), album (the one open first), heading (false keeps the page's own
  // title and lede), groupBy ("month": a timeline), monthAlbums (albums shown as a timeline when picked), and the
  // selectors albumBar, grid, lede, title, editbar, toast, viewBar.
  async function mount(opts) {
    opts = opts || {};
    var data = await HARTOps.loadJson(opts.dataUrl || "data/gallery.json");
    var albumBar = document.querySelector(opts.albumBar || "#album-bar");
    var grid = document.querySelector(opts.grid || "#gallery-grid");
    var lede = document.querySelector(opts.lede || "#gallery-lede");
    var title = document.querySelector(opts.title || "#gallery-title");
    if (opts.heading !== false) {
      if (title) title.textContent = data.title || "Photo gallery";
      if (lede) lede.textContent = data.lede || "";
    }

    var only = opts.albums && opts.albums.length ? opts.albums : null;
    var items = scopeItems(data.items, only);
    var currentAlbum = opts.album || (only && only.length === 1 ? only[0] : "all");

    var canEdit = await curationOn(opts.curate);
    var editbar = document.querySelector(opts.editbar || "#gallery-editbar");
    if (editbar) editbar.hidden = !canEdit;
    var showToast = makeToast(document.querySelector(opts.toast || "#gallery-toast"));

    // Grid is the masonry (or the month timeline); curation controls show only there.
    var viewBar = opts.viewBar ? document.querySelector(opts.viewBar) : null;
    var view = viewBar ? storedView() : "grid";
    var stageIndex = 0;
    var visible = items.slice();

    async function save(src, changes) {
      var res = await fetch(opts.curate + "/item", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.assign({ src: src }, changes)),
      });
      var payload = await res.json().catch(function () { return {}; });
      if (!res.ok) throw new Error(payload.error || "HTTP " + res.status);
      data = payload.gallery;
      items = scopeItems(data.items, only);
    }

    async function runCurate(src, changes, msg) {
      try {
        await save(src, changes);
        showToast(msg);
        renderAlbums();
        renderGrid();
      } catch (err) {
        showToast("Not saved: " + err.message, true);
      }
    }

    function filtered() {
      if (currentAlbum === "all") return items;
      return items.filter(function (it) {
        return it.album === currentAlbum;
      });
    }

    function byMonth() {
      return opts.groupBy === "month" || (opts.monthAlbums || []).indexOf(currentAlbum) !== -1;
    }

    function renderViews() {
      if (!viewBar) return;
      viewBar.innerHTML = viewBarHtml(view);
      viewBar.querySelectorAll("button").forEach(function (b) {
        b.addEventListener("click", function () {
          view = b.getAttribute("data-view");
          storeView(view);
          renderViews();
          renderGrid();
        });
      });
    }

    function renderAlbums() {
      if (!albumBar) return;
      albumBar.innerHTML = albumBarHtml(scopeAlbums(data.albums, only), items.length, currentAlbum);
      albumBar.querySelectorAll("button").forEach(function (btn) {
        btn.addEventListener("click", function () {
          currentAlbum = btn.getAttribute("data-album");
          stageIndex = 0;
          renderAlbums();
          renderGrid();
        });
      });
    }

    function stageStep(d) {
      stageIndex = wrapIndex(stageIndex, d, visible.length);
      renderGrid();
    }

    function bindStage() {
      grid.querySelector(".fleet-stage-nav.prev").addEventListener("click", function () { stageStep(-1); });
      grid.querySelector(".fleet-stage-nav.next").addEventListener("click", function () { stageStep(1); });
      grid.querySelectorAll("[data-stage]").forEach(function (b) {
        b.addEventListener("click", function () {
          stageIndex = Number(b.getAttribute("data-stage"));
          renderGrid();
        });
      });
      var cur = grid.querySelector('.fleet-strip [aria-current="true"]');
      if (cur && cur.scrollIntoView) cur.scrollIntoView({ block: "nearest", inline: "center" });
    }

    function bindOpen(v) {
      grid.querySelectorAll(v === "list" ? "tr[data-idx]" : ".g-item").forEach(function (el) {
        el.addEventListener("click", function () {
          lightbox.open(Number(el.getAttribute("data-idx")));
        });
        if (v === "list") {
          el.addEventListener("keydown", function (e) {
            if (e.key === "Enter") lightbox.open(Number(el.getAttribute("data-idx")));
          });
        }
      });
    }

    function renderGrid() {
      visible = filtered();
      if (!grid) return;
      if (stageIndex >= visible.length) stageIndex = 0;
      var v = viewBar && visible.length ? view : "grid";
      var month = byMonth();
      if (opts.monthAlbums || viewBar) {
        grid.classList.toggle("build-timeline", v === "grid" && month);
        grid.classList.toggle("gallery-masonry", v === "grid" && !month);
      }
      if (v === "list") grid.innerHTML = listHtml(visible, data.albums);
      else if (v === "gallery") grid.innerHTML = stageHtml(visible, stageIndex);
      else grid.innerHTML = gridHtml(visible, { byMonth: month, canEdit: canEdit, albums: data.albums });
      if (v === "gallery") {
        bindStage();
        return;
      }
      if (canEdit && v === "grid") {
        bindCurate(grid, function (src) { return items.find(function (x) { return x.src === src; }); }, runCurate);
      }
      bindOpen(v);
    }

    var lightbox = makeLightbox(function (i) { return visible[i]; }, function () { return visible.length; });

    // Deep link: photos/#layout/<item id> (ids are in data/gallery.json; the search index links them).
    // Shows the item's album, scrolls to the item, highlights it and opens its lightbox.
    // Returns false when no item has that id. Kept per grid, so a page with two galleries opens the right one.
    window.HARTGallery.openers[opts.grid || "#gallery-grid"] = function (id) {
      var item = items.filter(function (it) { return it.id === id; })[0];
      if (!item) return false;
      currentAlbum = item.album;
      stageIndex = 0;
      renderAlbums();
      renderGrid();
      return HARTOps.revealItem({
        index: visible.indexOf(item),
        galleryView: !!viewBar && view === "gallery",
        setStage: function (i) { stageIndex = i; renderGrid(); },
        grid: grid,
        openLightbox: lightbox.open,
      });
    };

    renderViews();
    renderAlbums();
    renderGrid();
    return data;
  }

  window.HARTGallery = {
    mount: mount,
    openers: {},
    lib: {
      parseDate: parseDate, longDate: longDate, scopeItems: scopeItems, scopeAlbums: scopeAlbums, albumBarHtml: albumBarHtml,
      cellHtml: cellHtml, gridHtml: gridHtml, listHtml: listHtml, stageHtml: stageHtml, wrapIndex: wrapIndex,
    },
  };
})();
