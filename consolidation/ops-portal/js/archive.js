// Historical archive: three buckets (Curated / To review / Discard), kind + tag filters,
// lightbox with credit. On the local server (serve_portal.py) the owner can move items
// between buckets and fix captions; edits POST to /api/archive/item and land in
// data/archive.json. The public build (site.json "public": true) is read-only.
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

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

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
      return false;
    }
  }

  window.HARTArchive = {
    mount: async function (opts) {
      opts = opts || {};
      var site = opts.site || {};
      var data = await HARTOps.loadJson("data/archive.json");
      var items = data.items || [];
      var buckets = data.buckets || [];
      var kinds = data.kinds || [];
      var canEdit = !site.public && (await apiAvailable());

      var tabsEl = document.getElementById("archive-tabs");
      var noteEl = document.getElementById("archive-tab-note");
      var kindsEl = document.getElementById("archive-kinds");
      var tagEl = document.getElementById("archive-tag");
      var searchEl = document.getElementById("archive-search");
      var grid = document.getElementById("archive-grid");
      var emptyEl = document.getElementById("archive-empty");
      var toast = document.getElementById("archive-toast");
      document.getElementById("archive-title").textContent = data.title || "Photos";
      document.getElementById("archive-lede").textContent = data.lede || "";
      document.getElementById("archive-editbar").hidden = !canEdit;

      var hash = (location.hash || "").replace("#", "");
      var state = {
        bucket: buckets.some(function (b) { return b.id === hash; }) ? hash : "curated",
        kind: "all",
        tag: "",
        q: "",
      };
      var visible = [];
      var lbIndex = 0;

      function inBucket() {
        return items.filter(function (it) {
          return it.bucket === state.bucket;
        });
      }

      function filtered() {
        var q = state.q.toLowerCase();
        return inBucket().filter(function (it) {
          if (state.kind !== "all" && it.kind !== state.kind) return false;
          if (state.tag && (it.tags || []).indexOf(state.tag) === -1) return false;
          if (q) {
            var hay = [it.title, it.caption, it.credit, it.date, (it.tags || []).join(" ")]
              .join(" ")
              .toLowerCase();
            if (hay.indexOf(q) === -1) return false;
          }
          return true;
        });
      }

      function showToast(msg, bad) {
        toast.textContent = msg;
        toast.classList.toggle("bad", !!bad);
        toast.classList.add("show");
        clearTimeout(showToast.t);
        showToast.t = setTimeout(function () {
          toast.classList.remove("show");
        }, 2600);
      }

      function renderTabs() {
        tabsEl.innerHTML = buckets
          .map(function (b) {
            var n = items.filter(function (it) { return it.bucket === b.id; }).length;
            var sel = b.id === state.bucket;
            return (
              '<button type="button" role="tab" data-bucket="' + esc(b.id) + '" aria-selected="' +
              sel + '" class="archive-tab tab-' + esc(b.id) + '">' + esc(b.label) +
              ' <span class="count">' + n + "</span></button>"
            );
          })
          .join("");
        noteEl.textContent = BUCKET_NOTES[state.bucket] || "";
        tabsEl.querySelectorAll("button").forEach(function (btn) {
          btn.addEventListener("click", function () {
            state.bucket = btn.getAttribute("data-bucket");
            state.kind = "all";
            state.tag = "";
            try {
              history.replaceState(null, "", "#" + state.bucket);
            } catch (e) {}
            renderAll();
          });
        });
      }

      function renderKinds() {
        var pool = inBucket();
        var opts = [{ id: "all", label: "All", count: pool.length }].concat(
          kinds
            .map(function (k) {
              return {
                id: k.id,
                label: k.label,
                count: pool.filter(function (it) { return it.kind === k.id; }).length,
              };
            })
            .filter(function (k) { return k.count; })
        );
        kindsEl.innerHTML = opts
          .map(function (k) {
            return (
              '<button type="button" data-kind="' + esc(k.id) + '" aria-pressed="' +
              (k.id === state.kind) + '">' + esc(k.label) + " (" + k.count + ")</button>"
            );
          })
          .join("");
        kindsEl.querySelectorAll("button").forEach(function (btn) {
          btn.addEventListener("click", function () {
            state.kind = btn.getAttribute("data-kind");
            renderKinds();
            renderGrid();
          });
        });
      }

      function renderTags() {
        var counts = {};
        inBucket().forEach(function (it) {
          (it.tags || []).forEach(function (t) {
            counts[t] = (counts[t] || 0) + 1;
          });
        });
        var tags = Object.keys(counts).sort();
        if (state.tag && !counts[state.tag]) state.tag = "";
        tagEl.innerHTML =
          '<option value="">All tags</option>' +
          tags
            .map(function (t) {
              return (
                '<option value="' + esc(t) + '"' + (t === state.tag ? " selected" : "") + ">" +
                esc(tagLabel(t)) + " (" + counts[t] + ")</option>"
              );
            })
            .join("");
      }

      function moveButtons(it) {
        return (
          '<div class="archive-move" role="group" aria-label="Move to">' +
          buckets
            .map(function (b) {
              return (
                '<button type="button" data-move="' + esc(b.id) + '" data-id="' + esc(it.id) + '"' +
                (b.id === it.bucket ? ' aria-pressed="true" disabled' : "") + ">" + esc(b.label) + "</button>"
              );
            })
            .join("") +
          '<button type="button" class="to-layout" data-to-layout="' + esc(it.id) + '">Layout photos</button>' +
          "</div>"
        );
      }

      function renderGrid() {
        visible = filtered();
        emptyEl.hidden = visible.length > 0;
        grid.innerHTML = visible
          .map(function (it, i) {
            var meta = [it.date, (kinds.find(function (k) { return k.id === it.kind; }) || {}).label]
              .filter(Boolean)
              .map(esc)
              .join(" · ");
            return (
              '<figure class="g-item archive-card" data-idx="' + i + '">' +
              '<button type="button" class="archive-open" data-idx="' + i + '">' +
              '<img src="' + esc(resolveSrc(it.thumb || it.src)) + '" alt="' + esc(it.title) + '" loading="lazy">' +
              "</button>" +
              "<figcaption><strong>" + esc(it.title) + "</strong>" +
              '<span class="archive-meta">' + meta +
              ' <em class="conf conf-' + esc(it.credit_confidence || "none") + '">' +
              esc(CONFIDENCE_LABEL[it.credit_confidence] || CONFIDENCE_LABEL.none) + "</em></span>" +
              (it.bucket !== "curated" && it.reason
                ? '<span class="archive-reason">' + esc(it.reason) + "</span>"
                : "") +
              (canEdit ? moveButtons(it) : "") +
              "</figcaption></figure>"
            );
          })
          .join("");
        grid.querySelectorAll(".archive-open").forEach(function (el) {
          el.addEventListener("click", function () {
            openLightbox(Number(el.getAttribute("data-idx")));
          });
        });
        bindMoves(grid);
      }

      function renderAll() {
        renderTabs();
        renderKinds();
        renderTags();
        renderGrid();
      }

      async function save(id, changes) {
        var res = await fetch(API_ITEM, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(Object.assign({ id: id }, changes)),
        });
        var payload = await res.json().catch(function () { return {}; });
        if (!res.ok) throw new Error(payload.error || "HTTP " + res.status);
        var idx = items.findIndex(function (it) { return it.id === id; });
        if (idx !== -1) items[idx] = payload.item;
        return payload.item;
      }

      async function moveToLayout(id) {
        var res = await fetch(API_TO_LAYOUT, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: id }),
        });
        var payload = await res.json().catch(function () { return {}; });
        if (!res.ok) throw new Error(payload.error || "HTTP " + res.status);
        var idx = items.findIndex(function (it) { return it.id === id; });
        var gone = idx !== -1 ? items.splice(idx, 1)[0] : null;
        return gone;
      }

      function bindMoves(root) {
        root.querySelectorAll("[data-to-layout]").forEach(function (btn) {
          btn.addEventListener("click", async function (e) {
            e.stopPropagation();
            try {
              var it = await moveToLayout(btn.getAttribute("data-to-layout"));
              showToast("Moved “" + ((it && it.title) || "item") + "” to Layout photos");
              closeLightbox();
              renderAll();
            } catch (err) {
              showToast("Not saved: " + err.message, true);
            }
          });
        });
        root.querySelectorAll("[data-move]").forEach(function (btn) {
          btn.addEventListener("click", async function (e) {
            e.stopPropagation();
            var id = btn.getAttribute("data-id");
            var to = btn.getAttribute("data-move");
            try {
              var it = await save(id, { bucket: to });
              var label = (buckets.find(function (b) { return b.id === to; }) || {}).label || to;
              showToast("Moved “" + it.title + "” to " + label);
              closeLightbox();
              renderAll();
            } catch (err) {
              showToast("Not saved: " + err.message, true);
            }
          });
        });
      }

      // —— Lightbox ——
      var lb = document.createElement("div");
      lb.className = "lightbox archive-lightbox";
      lb.innerHTML =
        '<button type="button" class="lightbox-close" aria-label="Close">Close</button>' +
        '<button type="button" class="lightbox-nav prev" aria-label="Previous">‹</button>' +
        '<button type="button" class="lightbox-nav next" aria-label="Next">›</button>' +
        '<div class="lightbox-card"><a class="lb-full" target="_blank" rel="noopener"><img alt=""></a>' +
        '<div class="meta"></div></div>';
      document.body.appendChild(lb);
      var lbImg = lb.querySelector("img");
      var lbFull = lb.querySelector(".lb-full");
      var lbMeta = lb.querySelector(".meta");

      function creditHtml(it) {
        var parts = [];
        if (it.credit) parts.push(esc(it.credit));
        if (it.source_url) {
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

      function editForm(it) {
        function field(name, label, value, textarea) {
          var input = textarea
            ? '<textarea name="' + name + '" rows="3">' + esc(value) + "</textarea>"
            : '<input name="' + name + '" value="' + esc(value) + '">';
          return "<label>" + label + input + "</label>";
        }
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

      function paintLightbox() {
        var it = visible[lbIndex];
        if (!it) return;
        var full = resolveSrc(it.src);
        lbImg.src = full;
        lbImg.alt = it.title || "";
        lbFull.href = full;
        var tags = (it.tags || [])
          .map(function (t) { return '<span class="chip">' + esc(tagLabel(t)) + "</span>"; })
          .join("");
        lbMeta.innerHTML =
          "<h2>" + esc(it.title) + "</h2>" +
          (it.date ? '<p class="archive-date">' + esc(it.date) + "</p>" : "") +
          "<p>" + esc(it.caption) + "</p>" +
          creditHtml(it) +
          (it.bucket !== "curated" && it.reason
            ? '<p class="archive-reason"><strong>' + (it.bucket === "discard" ? "Discarded" : "To review") +
              ":</strong> " + esc(it.reason) + "</p>"
            : "") +
          (it.pdf ? '<p class="credit"><a href="' + esc(resolveSrc(it.pdf)) + '" target="_blank" rel="noopener">Open full PDF (local copy)</a></p>' : "") +
          (it.origin && canEdit ? '<p class="credit">Found in: ' + esc(it.origin) + "</p>" : "") +
          (tags ? '<p class="chips">' + tags + "</p>" : "") +
          (canEdit ? moveButtons(it) + editForm(it) : "");
        if (canEdit) {
          bindMoves(lbMeta);
          var form = lbMeta.querySelector(".archive-edit form");
          form.addEventListener("submit", async function (e) {
            e.preventDefault();
            var fd = new FormData(form);
            var changes = {};
            fd.forEach(function (v, k) { changes[k] = v; });
            try {
              var saved = await save(it.id, changes);
              visible[lbIndex] = saved;
              showToast("Saved “" + saved.title + "”");
              renderAll();
              visible = filtered();
              lbIndex = Math.max(0, visible.findIndex(function (x) { return x.id === saved.id; }));
              if (visible[lbIndex]) paintLightbox();
              else closeLightbox();
            } catch (err) {
              showToast("Not saved: " + err.message, true);
            }
          });
        }
      }

      function openLightbox(i) {
        lbIndex = i;
        paintLightbox();
        lb.classList.add("open");
      }

      function closeLightbox() {
        lb.classList.remove("open");
      }

      function step(d) {
        if (!visible.length) return;
        lbIndex = (lbIndex + d + visible.length) % visible.length;
        paintLightbox();
      }

      lb.querySelector(".lightbox-close").addEventListener("click", closeLightbox);
      lb.addEventListener("click", function (e) {
        if (e.target === lb) closeLightbox();
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
        var t = e.target && e.target.tagName;
        if (t === "INPUT" || t === "TEXTAREA" || t === "SELECT") return;
        if (e.key === "Escape") closeLightbox();
        if (e.key === "ArrowLeft") step(-1);
        if (e.key === "ArrowRight") step(1);
      });

      tagEl.addEventListener("change", function () {
        state.tag = tagEl.value;
        renderGrid();
      });
      searchEl.addEventListener("input", function () {
        state.q = searchEl.value.trim();
        renderGrid();
      });

      renderAll();
      return data;
    },
  };
})();
