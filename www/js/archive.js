// Historical archive: three buckets (Curated / To review / Discard), kind + tag filters,
// lightbox with credit. On the local server (serve_portal.py) the owner can move items
// between buckets and fix captions; edits POST to /api/archive/item and land in
// data/archive.json. The public build (site.json "public": true) is read-only.
// The HTML is drawn by plain functions (HARTArchive.lib); mount() builds the page state and the functions after it
// draw it and bind its listeners. The view bar, lightbox and toast are js/photo-viewer.js's, loaded first.
// Tests: scripts/tests/archive_view_test.js.
(function () {
  if (!window.HARTViewer) throw new Error("archive.js needs js/photo-viewer.js loaded before it");
  var API_ITEM = "/api/archive/item";
  var API_PING = "/api/archive/ping";
  var API_TO_LAYOUT = "/api/archive/to-layout";

  var BUCKET_NOTES = {
    curated: "Historical, on-topic, and captioned. Credits link to the original where one was found.",
    review: "On-topic but unconfirmed: unknown source, date, or place, or a possible duplicate.",
    discard: "Duplicates and out-of-scope items, kept here so the decision is visible.",
  };
  var CONFIDENCE_LABEL = { verified: "Source verified", likely: "Source likely", none: "Source unknown" };

  var esc = HARTOps.esc;

  function encodePath(src) {
    return src
      .split("/")
      .map(function (part) {
        return part === ".." || part === "." ? part : encodeURIComponent(part);
      })
      .join("/");
  }

  // JSON paths are relative to ops-portal/; this page sits one level down.
  function resolveSrc(src) {
    if (!src) return "";
    if (/^https?:\/\//i.test(src) || src.startsWith("data:")) return src;
    return HARTOps.base() + encodePath(src);
  }

  function tagLabel(t) {
    return String(t).replace(/-/g, " ");
  }

  async function apiAvailable() {
    try {
      var res = await fetch(API_PING, { cache: "no-cache" });
      return res.ok;
    } catch (e) {
      return false; // no review server (the public site, or a plain file server): read-only
    }
  }

  // —— Grid / List / Gallery, remembered per browser (js/photo-viewer.js) and overridable with ?view= ——
  var VIEW_KEY = "hart.archive.view";

  function startView(search) {
    var param = new URLSearchParams(search).get("view");
    return HARTViewer.isView(param) ? param : HARTViewer.storedView(VIEW_KEY);
  }

  // —— Filters ——
  // The items of one bucket that pass the kind, tag and search filters. f: {bucket, kind, tag, q}.
  function filterItems(items, f) {
    var q = f.q.toLowerCase();
    return items.filter(function (it) {
      if (it.bucket !== f.bucket) return false;
      if (f.kind !== "all" && it.kind !== f.kind) return false;
      if (f.tag && (it.tags || []).indexOf(f.tag) === -1) return false;
      if (q) {
        var hay = [it.title, it.caption, it.credit, it.date, (it.tags || []).join(" ")].join(" ").toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });
  }

  function tabsHtml(buckets, items, bucket) {
    return buckets
      .map(function (b) {
        var n = items.filter(function (it) { return it.bucket === b.id; }).length;
        return (
          '<button type="button" role="tab" data-bucket="' + esc(b.id) + '" aria-selected="' +
          (b.id === bucket) + '" class="archive-tab tab-' + esc(b.id) + '">' + esc(b.label) +
          ' <span class="count">' + n + "</span></button>"
        );
      })
      .join("");
  }

  // "All" and each kind that has items in pool, with counts.
  function kindsHtml(kinds, pool, kind) {
    var opts = [{ id: "all", label: "All", count: pool.length }].concat(
      kinds
        .map(function (k) {
          return { id: k.id, label: k.label, count: pool.filter(function (it) { return it.kind === k.id; }).length };
        })
        .filter(function (k) { return k.count; })
    );
    return opts
      .map(function (k) {
        return '<button type="button" data-kind="' + esc(k.id) + '" aria-pressed="' + (k.id === kind) + '">' + esc(k.label) + " (" + k.count + ")</button>";
      })
      .join("");
  }

  // The tag menu for pool. Returns the options and the tag still chosen: one no item in pool has is dropped.
  function tagMenu(pool, tag) {
    var counts = {};
    pool.forEach(function (it) {
      (it.tags || []).forEach(function (t) {
        counts[t] = (counts[t] || 0) + 1;
      });
    });
    var kept = tag && counts[tag] ? tag : "";
    var html =
      '<option value="">All tags</option>' +
      Object.keys(counts)
        .sort()
        .map(function (t) {
          return '<option value="' + esc(t) + '"' + (t === kept ? " selected" : "") + ">" + esc(tagLabel(t)) + " (" + counts[t] + ")</option>";
        })
        .join("");
    return { html: html, tag: kept };
  }

  // —— Items ——  look: {kinds, buckets, canEdit} for every function below.
  function moveButtons(it, look) {
    return (
      '<div class="archive-move" role="group" aria-label="Move to">' +
      look.buckets
        .map(function (b) {
          return (
            '<button type="button" data-move="' + esc(b.id) + '" data-id="' + esc(it.id) + '"' +
            (b.id === it.bucket ? ' aria-pressed="true" disabled' : "") + ">" + esc(b.label) + "</button>"
          );
        })
        .join("") +
      '<button type="button" class="to-layout" data-to-layout="' + esc(it.id) + '">Session night</button>' +
      "</div>"
    );
  }

  var editMoves = (it, look) => (look.canEdit ? moveButtons(it, look) : "");
  var kindLabel = (it, look) => (look.kinds.find(function (k) { return k.id === it.kind; }) || {}).label;
  // Grid, list and strip show the build's thumbnail (item.thumb, with the original's width/height
  // to reserve space); the stage and lightbox open the full src.
  function thumbImg(it, alt) {
    return (
      '<img src="' + esc(resolveSrc(it.thumb || it.src)) + '" alt="' + esc(alt) + '"' +
      (it.width && it.height ? ' width="' + Number(it.width) + '" height="' + Number(it.height) + '"' : "") +
      ' loading="lazy" decoding="async">'
    );
  }

  function metaFor(it, look) {
    return [it.date, kindLabel(it, look)].filter(Boolean).map(esc).join(" · ");
  }

  function confBadge(it) {
    return (
      '<em class="conf conf-' + esc(it.credit_confidence || "none") + '">' +
      esc(CONFIDENCE_LABEL[it.credit_confidence] || CONFIDENCE_LABEL.none) + "</em>"
    );
  }

  function gridHtml(visible, look) {
    return (
      '<div class="gallery-masonry">' +
      visible
        .map(function (it, i) {
          return (
            '<figure class="g-item archive-card" data-idx="' + i + '">' +
            '<button type="button" class="archive-open" data-idx="' + i + '">' +
            thumbImg(it, it.title) +
            "</button>" +
            "<figcaption><strong>" + esc(it.title) + "</strong>" +
            '<span class="archive-meta">' + metaFor(it, look) + " " + confBadge(it) + "</span>" +
            (it.bucket !== "curated" && it.reason ? '<span class="archive-reason">' + esc(it.reason) + "</span>" : "") +
            editMoves(it, look) +
            "</figcaption></figure>"
          );
        })
        .join("") +
      "</div>"
    );
  }

  function listHtml(visible, look) {
    return (
      '<div class="fleet-list-wrap"><table class="fleet-list archive-list">' +
      "<thead><tr><th></th><th>Title</th><th>Date</th><th>Kind</th><th class=\"fl-note\">Credit</th></tr></thead><tbody>" +
      visible
        .map(function (it, i) {
          return (
            '<tr class="archive-row" data-idx="' + i + '" tabindex="0">' +
            '<td class="fl-thumb">' + thumbImg(it, "") + "</td>" +
            "<td><strong>" + esc(it.title) + "</strong>" + editMoves(it, look) + "</td>" +
            "<td>" + esc(it.date || "—") + "</td>" +
            "<td>" + esc(kindLabel(it, look) || "—") + "</td>" +
            '<td class="fl-note">' + esc(it.credit || "") + " " + confBadge(it) + "</td></tr>"
          );
        })
        .join("") +
      "</tbody></table></div>"
    );
  }

  // The Gallery view: item stageIndex large, with a strip of every item under it.
  function galleryHtml(visible, stageIndex, look) {
    var it = visible[stageIndex];
    return (
      '<div class="fleet-stage">' +
      '<button type="button" class="fleet-stage-nav prev" aria-label="Previous">‹</button>' +
      '<figure><button type="button" class="archive-open" data-idx="' + stageIndex + '" title="Details and credit">' +
      '<img src="' + esc(resolveSrc(it.src)) + '" alt="' + esc(it.title) + '"></button>' +
      "<figcaption><strong>" + esc(it.title) + "</strong> " +
      '<span class="muted">' + (stageIndex + 1) + " of " + visible.length + "</span>" +
      '<span class="archive-meta">' + metaFor(it, look) + "</span>" +
      (it.caption ? "<p>" + esc(it.caption) + "</p>" : "") +
      (it.credit ? '<span class="archive-meta">' + esc(it.credit) + "</span>" : "") +
      editMoves(it, look) +
      "</figcaption></figure>" +
      '<button type="button" class="fleet-stage-nav next" aria-label="Next">›</button>' +
      "</div>" +
      '<div class="fleet-strip archive-strip" role="list">' +
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

  function viewHtml(view, visible, stageIndex, look) {
    if (view === "list") return listHtml(visible, look);
    if (view === "gallery") return galleryHtml(visible, stageIndex, look);
    return gridHtml(visible, look);
  }

  // —— Lightbox content ——
  function creditHtml(it) {
    var parts = [];
    if (it.credit) parts.push(esc(it.credit));
    if (/^https?:\/\//i.test(it.source_url || "")) {
      parts.push('<a href="' + esc(it.source_url) + '" target="_blank" rel="noopener">Source</a>');
    }
    var conf = it.credit_confidence || "none";
    var line = parts.length ? parts.join(" · ") : "Credit unknown";
    return (
      '<p class="credit">' + line + ' <em class="conf conf-' + esc(conf) + '">' +
      esc(CONFIDENCE_LABEL[conf] || "") + "</em></p>" +
      (it.rights ? '<p class="credit">' + esc(it.rights) + "</p>" : "")
    );
  }

  function field(name, label, value, textarea) {
    var input = textarea
      ? '<textarea name="' + name + '" rows="3">' + esc(value) + "</textarea>"
      : '<input name="' + name + '" value="' + esc(value) + '">';
    return "<label>" + label + input + "</label>";
  }

  function editForm(it, kinds) {
    var confOpts = ["verified", "likely", "none"]
      .map(function (c) {
        return '<option value="' + c + '"' + (c === it.credit_confidence ? " selected" : "") + ">" + c + "</option>";
      })
      .join("");
    var kindOpts = kinds
      .map(function (k) {
        return '<option value="' + esc(k.id) + '"' + (k.id === it.kind ? " selected" : "") + ">" + esc(k.label) + "</option>";
      })
      .join("");
    return (
      '<details class="archive-edit"><summary>Edit details</summary><form>' +
      field("title", "Title", it.title) +
      field("caption", "Caption", it.caption, true) +
      field("date", "Date", it.date) +
      '<label>Kind<select name="kind">' + kindOpts + "</select></label>" +
      field("tags", "Tags (comma-separated)", (it.tags || []).join(", ")) +
      field("credit", "Credit", it.credit) +
      field("source_url", "Source URL", it.source_url) +
      '<label>Credit confidence<select name="credit_confidence">' + confOpts + "</select></label>" +
      field("rights", "Rights", it.rights) +
      field("reason", "Reason (review / discard)", it.reason) +
      '<button type="submit">Save</button></form></details>'
    );
  }

  // The text beside the lightbox photo: title, date, caption, credit, why it is not curated, links and tags.
  function lightboxMetaHtml(it, look) {
    var tags = (it.tags || []).map(function (t) { return '<span class="chip">' + esc(tagLabel(t)) + "</span>"; }).join("");
    return (
      '<h2 id="archive-lb-title">' + esc(it.title) + "</h2>" +
      (it.date ? '<p class="archive-date">' + esc(it.date) + "</p>" : "") +
      "<p>" + esc(it.caption) + "</p>" +
      creditHtml(it) +
      (it.bucket !== "curated" && it.reason
        ? '<p class="archive-reason"><strong>' + (it.bucket === "discard" ? "Discarded" : "To review") + ":</strong> " + esc(it.reason) + "</p>"
        : "") +
      (it.pdf ? '<p class="credit"><a href="' + esc(resolveSrc(it.pdf)) + '" target="_blank" rel="noopener">Open full PDF (local copy)</a></p>' : "") +
      (it.origin && look.canEdit ? '<p class="credit">Found in: ' + esc(it.origin) + "</p>" : "") +
      (tags ? '<p class="chips">' + tags + "</p>" : "") +
      (look.canEdit ? moveButtons(it, look) + editForm(it, look.kinds) : "")
    );
  }

  // The lightbox's card (js/photo-viewer.js draws the dialog round it): the photo, a link to its full copy, and the
  // text beside it.
  var LIGHTBOX_CARD = '<a class="lb-full" target="_blank" rel="noopener"><img alt=""></a><div class="meta"></div>';

  // The page's elements by id; a missing one is an error naming it.
  function pageElements() {
    var ids = {
      tabs: "archive-tabs", note: "archive-tab-note", kinds: "archive-kinds", tag: "archive-tag", search: "archive-search",
      grid: "archive-grid", empty: "archive-empty", toast: "archive-toast", lede: "archive-lede", editbar: "archive-editbar",
      viewBar: "archive-view-bar",
    };
    var els = {};
    Object.keys(ids).forEach(function (k) {
      els[k] = document.getElementById(ids[k]);
      if (!els[k]) throw new Error("the archive page has no #" + ids[k]);
    });
    return els;
  }

  // —— The page ——
  // pg is the mounted archive: data, items, buckets, look ({kinds, buckets, canEdit}), els (pageElements), ownHash
  // (the page keeps the bucket in the URL hash), state (the filters: bucket, kind, tag, q), visible (what the grid
  // shows now), stageIndex, view, showToast and lightbox. The functions below draw it and bind its listeners.

  var inBucket = (pg) => pg.items.filter(function (it) { return it.bucket === pg.state.bucket; });

  function showBucket(pg, id) {
    pg.state.bucket = id;
    pg.state.kind = "all";
    pg.state.tag = "";
    pg.stageIndex = 0;
    if (pg.ownHash) {
      try {
        history.replaceState(null, "", "#" + id);
      } catch (e) {
        console.warn("archive: the address bar keeps its old hash", e); // a file:// page may refuse it
      }
    }
    renderAll(pg);
  }

  function renderTabs(pg) {
    pg.els.tabs.innerHTML = tabsHtml(pg.buckets, pg.items, pg.state.bucket);
    pg.els.note.textContent = BUCKET_NOTES[pg.state.bucket] || "";
    pg.els.tabs.querySelectorAll("button").forEach(function (btn) {
      btn.addEventListener("click", function () { showBucket(pg, btn.getAttribute("data-bucket")); });
    });
  }

  function renderKinds(pg) {
    pg.els.kinds.innerHTML = kindsHtml(pg.look.kinds, inBucket(pg), pg.state.kind);
    pg.els.kinds.querySelectorAll("button").forEach(function (btn) {
      btn.addEventListener("click", function () {
        pg.state.kind = btn.getAttribute("data-kind");
        pg.stageIndex = 0;
        renderKinds(pg);
        renderGrid(pg);
      });
    });
  }

  function renderTags(pg) {
    var menu = tagMenu(inBucket(pg), pg.state.tag);
    pg.state.tag = menu.tag;
    pg.els.tag.innerHTML = menu.html;
  }

  function setStage(pg, i) {
    pg.stageIndex = i;
    renderGrid(pg);
  }

  function stageStep(pg, d) {
    setStage(pg, HARTViewer.wrapIndex(pg.stageIndex, d, pg.visible.length));
  }

  // A click (or Enter) on an item opens its lightbox; the Gallery view's stage controls; the desk's move buttons.
  function bindGrid(pg) {
    var grid = pg.els.grid;
    grid.querySelectorAll(".archive-open, .archive-row").forEach(function (el) {
      el.addEventListener("click", function (e) {
        if (e.target.closest(".archive-move")) return;
        pg.lightbox.open(Number(el.getAttribute("data-idx")));
      });
      el.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && e.target === el) pg.lightbox.open(Number(el.getAttribute("data-idx")));
      });
    });
    if (pg.view === "gallery") {
      HARTViewer.bindStage(grid, function (d) { stageStep(pg, d); }, function (i) { setStage(pg, i); });
    }
    bindMoves(pg, grid);
  }

  function renderGrid(pg) {
    pg.visible = filterItems(pg.items, pg.state);
    pg.els.empty.hidden = pg.visible.length > 0;
    if (!pg.visible.length) {
      pg.els.grid.innerHTML = "";
      return;
    }
    if (pg.stageIndex >= pg.visible.length) pg.stageIndex = 0;
    pg.els.grid.className = "archive-view view-" + pg.view;
    pg.els.grid.innerHTML = viewHtml(pg.view, pg.visible, pg.stageIndex, pg.look);
    bindGrid(pg);
  }

  function renderAll(pg) {
    renderTabs(pg);
    renderKinds(pg);
    renderTags(pg);
    renderGrid(pg);
  }

  // The index of item id in the page's copy; an error when the page has no such item.
  function itemIndex(pg, id) {
    var idx = pg.items.findIndex(function (it) { return it.id === id; });
    if (idx === -1) throw new Error("the page has no archive item " + JSON.stringify(id));
    return idx;
  }

  // Save changes to item id; the saved item the server sends back replaces the page's copy.
  async function save(pg, id, changes) {
    itemIndex(pg, id);
    var payload = await HARTViewer.postJson(API_ITEM, Object.assign({ id: id }, changes));
    if (!payload.item || payload.item.id !== id) throw new Error("the review server sent back no item " + JSON.stringify(id));
    // Looked up again: a move that finished during the wait may have shifted the list or taken the item out.
    var idx = pg.items.findIndex(function (it) { return it.id === id; });
    if (idx !== -1) pg.items[idx] = payload.item;
    return payload.item;
  }

  // Send item id to Session night (Operations); it leaves the archive.
  async function moveToLayout(pg, id) {
    itemIndex(pg, id);
    await HARTViewer.postJson(API_TO_LAYOUT, { id: id });
    return pg.items.splice(itemIndex(pg, id), 1)[0];
  }

  // One move button: act(value of attr) saves the move and gives the message for the toast.
  function onMove(pg, btn, attr, act) {
    btn.addEventListener("click", async function (e) {
      e.stopPropagation();
      try {
        pg.showToast(await act(btn.getAttribute(attr)));
        pg.lightbox.close();
        renderAll(pg);
      } catch (err) {
        pg.showToast("Not saved: " + err.message, true);
      }
    });
  }

  function bindMoves(pg, root) {
    root.querySelectorAll("[data-to-layout]").forEach(function (btn) {
      onMove(pg, btn, "data-to-layout", async function (id) {
        var it = await moveToLayout(pg, id);
        return "Moved “" + (it.title || "item") + "” to Session night (Operations)";
      });
    });
    root.querySelectorAll("[data-move]").forEach(function (btn) {
      onMove(pg, btn, "data-move", async function (to) {
        var it = await save(pg, btn.getAttribute("data-id"), { bucket: to });
        var label = (pg.buckets.find(function (b) { return b.id === to; }) || {}).label || to;
        return "Moved “" + it.title + "” to " + label;
      });
    });
  }

  function bindEditForm(pg, it, meta) {
    var form = meta.querySelector(".archive-edit form");
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      var changes = {};
      new FormData(form).forEach(function (v, k) { changes[k] = v; });
      try {
        var saved = await save(pg, it.id, changes);
        pg.showToast("Saved “" + saved.title + "”");
        renderAll(pg);
        pg.lightbox.show(Math.max(0, pg.visible.findIndex(function (x) { return x.id === saved.id; })));
      } catch (err) {
        pg.showToast("Not saved: " + err.message, true);
      }
    });
  }

  // The lightbox's card for item it: the photo, its full copy (a map's large copy loads only when asked for), the
  // text, and on the desk the move buttons and the edit form.
  function paintLightbox(pg, it, lb) {
    var src = resolveSrc(it.src);
    var img = lb.querySelector("img");
    img.src = src;
    img.alt = it.title || "";
    lb.querySelector(".lb-full").href = it.full ? resolveSrc(it.full) : src;
    var meta = lb.querySelector(".meta");
    meta.innerHTML = lightboxMetaHtml(it, pg.look);
    if (pg.look.canEdit) {
      bindMoves(pg, meta);
      bindEditForm(pg, it, meta);
    }
  }

  // The tag menu and the search box; the arrows step the Gallery view while the lightbox is shut (never while typing
  // in a field; with the lightbox open they step the lightbox, js/photo-viewer.js).
  function bindFilters(pg) {
    pg.els.tag.addEventListener("change", function () {
      pg.state.tag = pg.els.tag.value;
      pg.stageIndex = 0;
      renderGrid(pg);
    });
    pg.els.search.addEventListener("input", function () {
      pg.state.q = pg.els.search.value.trim();
      pg.stageIndex = 0;
      renderGrid(pg);
    });
    document.addEventListener("keydown", function (e) {
      if (pg.lightbox.isOpen() || pg.view !== "gallery" || !pg.visible.length) return;
      if (HARTViewer.isField(e.target && e.target.tagName)) return;
      if (e.key === "ArrowLeft") stageStep(pg, -1);
      if (e.key === "ArrowRight") stageStep(pg, 1);
    });
  }

  // Deep link: photos/#historical/<item id> (ids are in data/archive.json; the search index links them).
  // Clears the filters, scrolls to the item, highlights it and opens its lightbox. Returns false when
  // no item has that id, or it is outside the buckets this visitor sees.
  function openItem(pg, id) {
    var item = pg.items.filter(function (it) { return it.id === id; })[0];
    if (!item || (!pg.look.canEdit && item.bucket !== "curated")) return false;
    pg.state.bucket = item.bucket;
    pg.state.kind = "all";
    pg.state.tag = pg.state.q = "";
    pg.els.search.value = "";
    renderAll(pg);
    return HARTOps.revealItem({
      index: pg.visible.indexOf(item),
      galleryView: pg.view === "gallery",
      setStage: function (i) { setStage(pg, i); },
      grid: pg.els.grid,
      openLightbox: pg.lightbox.open,
    });
  }

  // opts.site: site.json (public is read-only); opts.hash === false leaves the URL hash to the page (Photos uses it
  // for its own tabs).
  async function mount(opts) {
    opts = opts || {};
    var site = opts.site || {};
    var data = await HARTOps.loadJson("data/archive.json");
    var buckets = data.buckets || [];
    var canEdit = !site.public && (await apiAvailable());
    var els = pageElements();
    var ownHash = opts.hash !== false;
    var hash = ownHash ? (location.hash || "").replace("#", "") : "";
    var pg = {
      data: data,
      items: data.items || [],
      buckets: buckets,
      look: { kinds: data.kinds || [], buckets: buckets, canEdit: canEdit },
      els: els,
      ownHash: ownHash,
      state: {
        bucket: canEdit && buckets.some(function (b) { return b.id === hash; }) ? hash : "curated",
        kind: "all",
        tag: "",
        q: "",
      },
      visible: [],
      stageIndex: 0,
      view: startView(location.search),
      showToast: HARTViewer.makeToast(els.toast),
    };
    // The page name stays in the HTML <h1> ("Photos") so it matches every link to it.
    els.lede.textContent = data.lede || "";
    els.editbar.hidden = !canEdit;
    // Curated / To review / Discard tabs are an engineering-desk tool: only the local
    // review server shows them. Everyone else sees the curated set.
    els.tabs.hidden = els.note.hidden = !canEdit;
    pg.lightbox = HARTViewer.makeLightbox({
      className: "lightbox archive-lightbox",
      titleId: "archive-lb-title",
      card: LIGHTBOX_CARD,
      at: function (i) { return pg.visible[i]; },
      count: function () { return pg.visible.length; },
      paint: function (it, lb) { paintLightbox(pg, it, lb); },
    });
    bindFilters(pg);
    window.HARTArchive.openItem = function (id) { return openItem(pg, id); };

    HARTViewer.mountViewBar(els.viewBar, VIEW_KEY, pg.view, function (v) {
      pg.view = v;
      renderGrid(pg);
    });
    renderAll(pg);
    return data;
  }

  window.HARTArchive = {
    mount: mount,
    lib: {
      resolveSrc: resolveSrc, startView: startView, filterItems: filterItems, tabsHtml: tabsHtml, kindsHtml: kindsHtml,
      tagMenu: tagMenu, viewHtml: viewHtml, lightboxMetaHtml: lightboxMetaHtml, postJson: HARTViewer.postJson,
    },
  };
})();
