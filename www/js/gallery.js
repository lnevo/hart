// Photo galleries from data/gallery.json: the Layout tab of Photos (albums, Grid / List / Gallery views) and the
// build chronology (one album as a month timeline). On the local review server the owner can move, reorder and
// caption photos (opts.curate names the API). The HTML is drawn by plain functions (HARTGallery.lib); mount() builds
// the page state and the functions after it draw it and bind its listeners; the view bar, lightbox and toast are js/photo-viewer.js's, loaded first.
// Tests: scripts/tests/gallery_view_test.js.
(function () {
  if (!window.HARTViewer) throw new Error("gallery.js needs js/photo-viewer.js loaded before it");
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

  // Grid / List / Gallery, as on Rolling stock and Historical, remembered per browser (js/photo-viewer.js).
  var VIEW_KEY = "hart.gallery.view";

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

  // —— Photo viewer ——
  // The lightbox's card: the photo, its title, caption, and date and credit.
  var LIGHTBOX_CARD = '<img alt=""><div class="meta"><h2 id="g-lightbox-title"></h2><p></p><div class="credit"></div></div>';

  function paintLightbox(it, lb) {
    var img = lb.querySelector("img");
    img.src = resolveSrc(it.src);
    img.alt = it.title || "";
    lb.querySelector("h2").textContent = it.title || "";
    lb.querySelector("p").textContent = it.caption || "";
    lb.querySelector(".credit").textContent = [longDate(it.date), it.credit].filter(Boolean).join(" · ");
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

  // —— The page ——
  // pg is one mounted gallery: opts, data, only (the album ids it shows, or null for all), items (their photos),
  // album (the one picked, or "all"), view, stageIndex, visible (what the grid shows now), canEdit, the elements
  // (albumBar, grid, viewBar), showToast and lightbox. The functions below draw it and bind its listeners.

  function filtered(pg) {
    if (pg.album === "all") return pg.items;
    return pg.items.filter(function (it) {
      return it.album === pg.album;
    });
  }

  function byMonth(pg) {
    return pg.opts.groupBy === "month" || (pg.opts.monthAlbums || []).indexOf(pg.album) !== -1;
  }

  function showAlbum(pg, id) {
    pg.album = id;
    pg.stageIndex = 0;
    renderAlbums(pg);
    renderGrid(pg);
  }

  function setStage(pg, i) {
    pg.stageIndex = i;
    renderGrid(pg);
  }

  function renderAlbums(pg) {
    if (!pg.albumBar) return;
    pg.albumBar.innerHTML = albumBarHtml(scopeAlbums(pg.data.albums, pg.only), pg.items.length, pg.album);
    pg.albumBar.querySelectorAll("button").forEach(function (btn) {
      btn.addEventListener("click", function () { showAlbum(pg, btn.getAttribute("data-album")); });
    });
  }

  // A click on a photo (or Enter on a list row) opens it in the lightbox.
  function bindOpen(pg, v) {
    pg.grid.querySelectorAll(v === "list" ? "tr[data-idx]" : ".g-item").forEach(function (el) {
      el.addEventListener("click", function () {
        pg.lightbox.open(Number(el.getAttribute("data-idx")));
      });
      if (v === "list") {
        el.addEventListener("keydown", function (e) {
          if (e.key === "Enter") pg.lightbox.open(Number(el.getAttribute("data-idx")));
        });
      }
    });
  }

  // Grid is the masonry (or the month timeline); curation controls show only there.
  function renderGrid(pg) {
    pg.visible = filtered(pg);
    if (!pg.grid) return;
    if (pg.stageIndex >= pg.visible.length) pg.stageIndex = 0;
    var v = pg.viewBar && pg.visible.length ? pg.view : "grid";
    var month = byMonth(pg);
    if (pg.opts.monthAlbums || pg.viewBar) {
      pg.grid.classList.toggle("build-timeline", v === "grid" && month);
      pg.grid.classList.toggle("gallery-masonry", v === "grid" && !month);
    }
    if (v === "list") pg.grid.innerHTML = listHtml(pg.visible, pg.data.albums);
    else if (v === "gallery") pg.grid.innerHTML = stageHtml(pg.visible, pg.stageIndex);
    else pg.grid.innerHTML = gridHtml(pg.visible, { byMonth: month, canEdit: pg.canEdit, albums: pg.data.albums });
    if (v === "gallery") {
      HARTViewer.bindStage(
        pg.grid,
        function (d) { setStage(pg, HARTViewer.wrapIndex(pg.stageIndex, d, pg.visible.length)); },
        function (i) { setStage(pg, i); }
      );
      return;
    }
    if (pg.canEdit && v === "grid") {
      bindCurate(pg.grid, function (src) { return pg.items.find(function (x) { return x.src === src; }); }, function (src, changes, msg) {
        return runCurate(pg, src, changes, msg);
      });
    }
    bindOpen(pg, v);
  }

  // Save one change on the review server; its answer is the whole gallery, which replaces the page's copy.
  async function save(pg, src, changes) {
    var payload = await HARTViewer.postJson(pg.opts.curate + "/item", Object.assign({ src: src }, changes));
    if (!payload.gallery || !Array.isArray(payload.gallery.items)) throw new Error("the review server sent back no gallery");
    pg.data = payload.gallery;
    pg.items = scopeItems(pg.data.items, pg.only);
  }

  async function runCurate(pg, src, changes, msg) {
    try {
      await save(pg, src, changes);
      pg.showToast(msg);
      renderAlbums(pg);
      renderGrid(pg);
    } catch (err) {
      pg.showToast("Not saved: " + err.message, true);
    }
  }

  // Deep link: photos/#layout/<item id> (ids are in data/gallery.json; the search index links them).
  // Shows the item's album, scrolls to the item, highlights it and opens its lightbox.
  // Returns false when no item has that id.
  function openItem(pg, id) {
    var item = pg.items.filter(function (it) { return it.id === id; })[0];
    if (!item) return false;
    pg.album = item.album;
    pg.stageIndex = 0;
    renderAlbums(pg);
    renderGrid(pg);
    return HARTOps.revealItem({
      index: pg.visible.indexOf(item),
      galleryView: !!pg.viewBar && pg.view === "gallery",
      setStage: function (i) { setStage(pg, i); },
      grid: pg.grid,
      openLightbox: pg.lightbox.open,
    });
  }

  // opts: dataUrl, albums (ids this page shows), album (the one open first), heading (false keeps the page's own
  // title and lede), groupBy ("month": a timeline), monthAlbums (albums shown as a timeline when picked), curate (the
  // review server's API), and the selectors albumBar, grid, lede, title, editbar, toast, viewBar.
  async function mount(opts) {
    opts = opts || {};
    var data = await HARTOps.loadJson(opts.dataUrl || "data/gallery.json");
    if (opts.heading !== false) {
      var title = document.querySelector(opts.title || "#gallery-title");
      var lede = document.querySelector(opts.lede || "#gallery-lede");
      if (title) title.textContent = data.title || "Photo gallery";
      if (lede) lede.textContent = data.lede || "";
    }
    var only = opts.albums && opts.albums.length ? opts.albums : null;
    var canEdit = await curationOn(opts.curate);
    var editbar = document.querySelector(opts.editbar || "#gallery-editbar");
    if (editbar) editbar.hidden = !canEdit;
    var viewBar = opts.viewBar ? document.querySelector(opts.viewBar) : null;
    var pg = {
      opts: opts,
      data: data,
      only: only,
      items: scopeItems(data.items, only),
      album: opts.album || (only && only.length === 1 ? only[0] : "all"),
      view: viewBar ? HARTViewer.storedView(VIEW_KEY) : "grid",
      stageIndex: 0,
      visible: [],
      canEdit: canEdit,
      albumBar: document.querySelector(opts.albumBar || "#album-bar"),
      grid: document.querySelector(opts.grid || "#gallery-grid"),
      viewBar: viewBar,
      // Only the curation tools report saves, so a read-only page needs no toast.
      showToast: canEdit ? HARTViewer.makeToast(document.querySelector(opts.toast || "#gallery-toast")) : null,
    };
    pg.visible = pg.items.slice();
    pg.lightbox = HARTViewer.makeLightbox({
      className: "lightbox",
      titleId: "g-lightbox-title",
      card: LIGHTBOX_CARD,
      at: function (i) { return pg.visible[i]; },
      count: function () { return pg.visible.length; },
      paint: paintLightbox,
    });
    // Kept per grid, so a page with two galleries opens the right one.
    window.HARTGallery.openers[opts.grid || "#gallery-grid"] = function (id) { return openItem(pg, id); };

    if (viewBar) {
      HARTViewer.mountViewBar(viewBar, VIEW_KEY, pg.view, function (v) {
        pg.view = v;
        renderGrid(pg);
      });
    }
    renderAlbums(pg);
    renderGrid(pg);
    return data;
  }

  window.HARTGallery = {
    mount: mount,
    openers: {},
    lib: {
      parseDate: parseDate, longDate: longDate, scopeItems: scopeItems, scopeAlbums: scopeAlbums, albumBarHtml: albumBarHtml,
      cellHtml: cellHtml, gridHtml: gridHtml, listHtml: listHtml, stageHtml: stageHtml, wrapIndex: HARTViewer.wrapIndex,
    },
  };
})();
