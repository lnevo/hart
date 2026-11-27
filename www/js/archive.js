// Historical archive: three buckets (Curated / To review / Discard), kind + tag filters,
// lightbox with credit. On the local server (serve_portal.py) the owner can move items
// between buckets and fix captions; edits POST to /api/archive/item and land in
// data/archive.json. The public build (site.json "public": true) is read-only.
// The HTML is drawn by plain functions (HARTArchive.lib); mount() keeps the state and the listeners.
// Tests: scripts/tests/archive_view_test.js.
(function () {
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

  // POST body to an archive API; the item it sends back, or an Error with the server's own message.
  async function postJson(url, body) {
    var res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    var payload = await res.json().catch(function () { return {}; });
    if (!res.ok) throw new Error(payload.error || "HTTP " + res.status);
    return payload;
  }

  // —— Grid / List / Gallery, remembered per browser and overridable with ?view= ——
  var VIEW_KEY = "hart.archive.view";
  var VIEWS = [
    { id: "grid", label: "Grid" },
    { id: "list", label: "List" },
    { id: "gallery", label: "Gallery" },
  ];
  var isView = (id) => VIEWS.some(function (v) { return v.id === id; });

  function startView(search) {
    var view = "grid";
    try {
      var saved = localStorage.getItem(VIEW_KEY);
      if (isView(saved)) view = saved;
    } catch (e) {
      view = "grid"; // no storage (a private window): Grid unless the URL names a view
    }
    var param = new URLSearchParams(search).get("view");
    return isView(param) ? param : view;
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
  var thumbSrc = (it) => esc(resolveSrc(it.thumb || it.src));

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
            '<img src="' + thumbSrc(it) + '" alt="' + esc(it.title) + '" loading="lazy">' +
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
            '<td class="fl-thumb"><img src="' + thumbSrc(it) + '" alt="" loading="lazy"></td>' +
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
            ' title="' + esc(x.title) + '"><img src="' + thumbSrc(x) + '" alt="' + esc(x.title) + '" loading="lazy"></button>'
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

  // The lightbox: a modal dialog like the crew map viewer: focus on Close, Tab kept inside, Esc closes, focus goes
  // back to whatever opened it. at(i) gives item i of what the page shows now and count() how many there are;
  // painted(it, meta) binds the desk controls drawn into meta.
  function makeLightbox(look, at, count, painted) {
    var lb = document.createElement("div");
    lb.className = "lightbox archive-lightbox";
    lb.setAttribute("role", "dialog");
    lb.setAttribute("aria-modal", "true");
    lb.setAttribute("aria-labelledby", "archive-lb-title");
    lb.innerHTML =
      '<button type="button" class="lightbox-close" aria-label="Close">Close</button>' +
      '<button type="button" class="lightbox-nav prev" aria-label="Previous">‹</button>' +
      '<button type="button" class="lightbox-nav next" aria-label="Next">›</button>' +
      '<div class="lightbox-card"><a class="lb-full" target="_blank" rel="noopener"><img alt=""></a>' +
      '<div class="meta"></div></div>';
    document.body.appendChild(lb);
    var img = lb.querySelector("img");
    var full = lb.querySelector(".lb-full");
    var meta = lb.querySelector(".meta");
    var index = 0;
    var returnTo = null;

    function paint() {
      var it = at(index);
      if (!it) return;
      var src = resolveSrc(it.src);
      img.src = src;
      img.alt = it.title || "";
      full.href = it.full ? resolveSrc(it.full) : src; // a map's large copy loads only when asked for
      meta.innerHTML = lightboxMetaHtml(it, look);
      if (look.canEdit) painted(it, meta);
    }

    function open(i) {
      index = i;
      paint();
      if (!lb.classList.contains("open")) returnTo = document.activeElement;
      lb.classList.add("open");
      lb.querySelector(".lightbox-close").focus();
    }

    function close() {
      lb.classList.remove("open");
      // The opener may have been redrawn (a save re-renders the grid); then focus stays put.
      if (returnTo && returnTo.focus && document.contains(returnTo)) returnTo.focus();
      returnTo = null;
    }

    function step(d) {
      if (!count()) return;
      index = wrap(index, d, count());
      paint();
    }

    // Show item i again after a save, or close when the save moved it out of view.
    function show(i) {
      index = i;
      if (at(index)) paint();
      else close();
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
    return { el: lb, open: open, close: close, step: step, show: show, isOpen: () => lb.classList.contains("open") };
  }

  var isField = (t) => t === "INPUT" || t === "TEXTAREA" || t === "SELECT";
  var wrap = (i, d, n) => (i + d + n) % n;

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
  // opts.site: site.json (public is read-only); opts.hash === false leaves the URL hash to the page (Photos uses it
  // for its own tabs).
  async function mount(opts) {
    opts = opts || {};
    var site = opts.site || {};
    var data = await HARTOps.loadJson("data/archive.json");
    var items = data.items || [];
    var buckets = data.buckets || [];
    var look = { kinds: data.kinds || [], buckets: buckets, canEdit: !site.public && (await apiAvailable()) };
    var canEdit = look.canEdit;
    var els = pageElements();
    // The page name stays in the HTML <h1> ("Photos") so it matches every link to it.
    els.lede.textContent = data.lede || "";
    els.editbar.hidden = !canEdit;

    var ownHash = opts.hash !== false;
    var hash = ownHash ? (location.hash || "").replace("#", "") : "";
    // Curated / To review / Discard tabs are an engineering-desk tool: only the local
    // review server shows them. Everyone else sees the curated set.
    els.tabs.hidden = els.note.hidden = !canEdit;
    var state = {
      bucket: canEdit && buckets.some(function (b) { return b.id === hash; }) ? hash : "curated",
      kind: "all",
      tag: "",
      q: "",
    };
    var visible = [];
    var stageIndex = 0;
    var view = startView(location.search);
    var toastTimer = null;
    var inBucket = () => items.filter(function (it) { return it.bucket === state.bucket; });

    function showToast(msg, bad) {
      els.toast.textContent = msg;
      els.toast.classList.toggle("bad", !!bad);
      els.toast.classList.add("show");
      clearTimeout(toastTimer);
      toastTimer = setTimeout(function () {
        els.toast.classList.remove("show");
      }, 2600);
    }

    function showBucket(id) {
      state.bucket = id;
      state.kind = "all";
      stageIndex = 0;
      state.tag = "";
      if (ownHash) {
        try {
          history.replaceState(null, "", "#" + state.bucket);
        } catch (e) {
          console.warn("archive: the address bar keeps its old hash", e); // a file:// page may refuse it
        }
      }
      renderAll();
    }

    function renderViews() {
      els.viewBar.innerHTML = viewBarHtml(view);
      els.viewBar.querySelectorAll("button").forEach(function (b) {
        b.addEventListener("click", function () {
          view = b.getAttribute("data-view");
          storeView(view);
          renderViews();
          renderGrid();
        });
      });
    }

    function renderTabs() {
      els.tabs.innerHTML = tabsHtml(buckets, items, state.bucket);
      els.note.textContent = BUCKET_NOTES[state.bucket] || "";
      els.tabs.querySelectorAll("button").forEach(function (btn) {
        btn.addEventListener("click", function () { showBucket(btn.getAttribute("data-bucket")); });
      });
    }

    function renderKinds() {
      els.kinds.innerHTML = kindsHtml(look.kinds, inBucket(), state.kind);
      els.kinds.querySelectorAll("button").forEach(function (btn) {
        btn.addEventListener("click", function () {
          state.kind = btn.getAttribute("data-kind");
          stageIndex = 0;
          renderKinds();
          renderGrid();
        });
      });
    }

    function renderTags() {
      var menu = tagMenu(inBucket(), state.tag);
      state.tag = menu.tag;
      els.tag.innerHTML = menu.html;
    }

    function stageStep(d) {
      stageIndex = wrap(stageIndex, d, visible.length);
      renderGrid();
    }

    function bindGrid() {
      var grid = els.grid;
      grid.querySelectorAll(".archive-open, .archive-row").forEach(function (el) {
        el.addEventListener("click", function (e) {
          if (e.target.closest(".archive-move")) return;
          lightbox.open(Number(el.getAttribute("data-idx")));
        });
        el.addEventListener("keydown", function (e) {
          if (e.key === "Enter" && e.target === el) lightbox.open(Number(el.getAttribute("data-idx")));
        });
      });
      if (view === "gallery") {
        grid.querySelector(".fleet-stage-nav.prev").addEventListener("click", function () { stageStep(-1); });
        grid.querySelector(".fleet-stage-nav.next").addEventListener("click", function () { stageStep(1); });
        grid.querySelectorAll("[data-stage]").forEach(function (b) {
          b.addEventListener("click", function () {
            stageIndex = Number(b.getAttribute("data-stage"));
            renderGrid();
          });
        });
        var cur = grid.querySelector('.archive-strip [aria-current="true"]');
        if (cur && cur.scrollIntoView) cur.scrollIntoView({ block: "nearest", inline: "center" });
      }
      bindMoves(grid);
    }

    function renderGrid() {
      visible = filterItems(items, state);
      els.empty.hidden = visible.length > 0;
      if (!visible.length) {
        els.grid.innerHTML = "";
        return;
      }
      if (stageIndex >= visible.length) stageIndex = 0;
      els.grid.className = "archive-view view-" + view;
      els.grid.innerHTML = viewHtml(view, visible, stageIndex, look);
      bindGrid();
    }

    function renderAll() {
      renderTabs();
      renderKinds();
      renderTags();
      renderGrid();
    }

    // Save changes to item id; the saved item replaces the page's copy.
    async function save(id, changes) {
      var payload = await postJson(API_ITEM, Object.assign({ id: id }, changes));
      var idx = items.findIndex(function (it) { return it.id === id; });
      if (idx !== -1) items[idx] = payload.item;
      return payload.item;
    }

    // Send item id to Session night (Operations); it leaves the archive.
    async function moveToLayout(id) {
      await postJson(API_TO_LAYOUT, { id: id });
      var idx = items.findIndex(function (it) { return it.id === id; });
      return idx !== -1 ? items.splice(idx, 1)[0] : null;
    }

    // One move button: act(value of attr) saves the move and gives the message for the toast.
    function onMove(btn, attr, act) {
      btn.addEventListener("click", async function (e) {
        e.stopPropagation();
        try {
          showToast(await act(btn.getAttribute(attr)));
          lightbox.close();
          renderAll();
        } catch (err) {
          showToast("Not saved: " + err.message, true);
        }
      });
    }

    function bindMoves(root) {
      root.querySelectorAll("[data-to-layout]").forEach(function (btn) {
        onMove(btn, "data-to-layout", async function (id) {
          var it = await moveToLayout(id);
          return "Moved “" + ((it && it.title) || "item") + "” to Session night (Operations)";
        });
      });
      root.querySelectorAll("[data-move]").forEach(function (btn) {
        onMove(btn, "data-move", async function (to) {
          var it = await save(btn.getAttribute("data-id"), { bucket: to });
          var label = (buckets.find(function (b) { return b.id === to; }) || {}).label || to;
          return "Moved “" + it.title + "” to " + label;
        });
      });
    }

    function bindEditForm(it, meta) {
      var form = meta.querySelector(".archive-edit form");
      form.addEventListener("submit", async function (e) {
        e.preventDefault();
        var changes = {};
        new FormData(form).forEach(function (v, k) { changes[k] = v; });
        try {
          var saved = await save(it.id, changes);
          showToast("Saved “" + saved.title + "”");
          renderAll();
          lightbox.show(Math.max(0, visible.findIndex(function (x) { return x.id === saved.id; })));
        } catch (err) {
          showToast("Not saved: " + err.message, true);
        }
      });
    }

    var lightbox = makeLightbox(look, function (i) { return visible[i]; }, function () { return visible.length; }, function (it, meta) {
      bindMoves(meta);
      bindEditForm(it, meta);
    });

    // Arrows step the lightbox, or the Gallery view while the lightbox is shut; never while typing in a field.
    document.addEventListener("keydown", function (e) {
      var t = e.target && e.target.tagName;
      if (!lightbox.isOpen()) {
        if (view === "gallery" && visible.length && !isField(t)) {
          if (e.key === "ArrowLeft") stageStep(-1);
          if (e.key === "ArrowRight") stageStep(1);
        }
        return;
      }
      HARTOps.trapTab(lightbox.el, e);
      if (isField(t)) return;
      if (e.key === "Escape") lightbox.close();
      if (e.key === "ArrowLeft") lightbox.step(-1);
      if (e.key === "ArrowRight") lightbox.step(1);
    });

    els.tag.addEventListener("change", function () {
      state.tag = els.tag.value;
      stageIndex = 0;
      renderGrid();
    });
    els.search.addEventListener("input", function () {
      state.q = els.search.value.trim();
      stageIndex = 0;
      renderGrid();
    });

    // Deep link: photos/#historical/<item id> (ids are in data/archive.json; the search index links them).
    // Clears the filters, scrolls to the item, highlights it and opens its lightbox. Returns false when
    // no item has that id, or it is outside the buckets this visitor sees.
    window.HARTArchive.openItem = function (id) {
      var item = items.filter(function (it) { return it.id === id; })[0];
      if (!item || (!canEdit && item.bucket !== "curated")) return false;
      state.bucket = item.bucket;
      state.kind = "all";
      state.tag = state.q = "";
      els.search.value = "";
      renderAll();
      return HARTOps.revealItem({
        index: visible.indexOf(item),
        galleryView: view === "gallery",
        setStage: function (i) { stageIndex = i; renderGrid(); },
        grid: els.grid,
        openLightbox: lightbox.open,
      });
    };

    renderViews();
    renderAll();
    return data;
  }

  window.HARTArchive = {
    mount: mount,
    lib: {
      resolveSrc: resolveSrc, startView: startView, filterItems: filterItems, tabsHtml: tabsHtml, kindsHtml: kindsHtml,
      tagMenu: tagMenu, viewHtml: viewHtml, lightboxMetaHtml: lightboxMetaHtml, postJson: postJson,
    },
  };
})();
