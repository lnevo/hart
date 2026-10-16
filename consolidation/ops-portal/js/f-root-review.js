(function () {
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function resolveSrc(src) {
    if (!src) return "";
    var depth = HARTOps.base();
    if (src.startsWith("../external/")) {
      // JSON paths assume one portal level; add extra ../ per nesting depth.
      var extra = (depth.match(/\.\.\//g) || []).length - 1;
      if (extra > 0) {
        return "../".repeat(extra) + src;
      }
    }
    if (src.startsWith("assets/") || src.startsWith("data/")) {
      return depth + src;
    }
    if (/^https?:\/\//i.test(src) || src.startsWith("data:")) {
      return src;
    }
    return depth + src;
  }

  function encodePath(src) {
    if (!src) return "";
    var parts = src.split("/");
    return parts
      .map(function (part, i) {
        if (i === 0 && part === "..") return part;
        return encodeURIComponent(part);
      })
      .join("/");
  }

  function latestByPath(entries) {
    var map = {};
    (entries || []).forEach(function (entry) {
      if (entry && entry.path) {
        map[entry.path] = entry;
      }
    });
    return map;
  }

  window.HARTFRootReview = {
    mount: async function (opts) {
      opts = opts || {};
      var data = await HARTOps.loadJson(opts.dataUrl || "data/f-root-review.json");
      var albumBar = document.querySelector(opts.albumBar || "#album-bar");
      var statusBar = document.querySelector(opts.statusBar || "#status-bar");
      var grid = document.querySelector(opts.grid || "#gallery-grid");
      var lede = document.querySelector(opts.lede || "#gallery-lede");
      var title = document.querySelector(opts.title || "#gallery-title");
      var stats = document.querySelector(opts.stats || "#review-stats");
      var toast = document.querySelector(opts.toast || "#review-toast");

      if (title) title.textContent = data.title || "F-root review";
      if (lede) lede.textContent = data.lede || "";

      var items = (data.items || []).slice();
      var decisions = {};
      try {
        var res = await fetch("/api/f-root-review/log");
        if (res.ok) {
          var log = await res.json();
          decisions = latestByPath(log.entries);
        }
      } catch (err) {
        console.warn("Review log unavailable:", err);
      }

      items.forEach(function (it) {
        var d = decisions[it.path];
        if (d) {
          it._action = d.action;
          it._category = d.category || it.suggestedCategory || it.category;
          it._caption = d.caption != null ? d.caption : it.summary || it.caption;
        } else {
          it._action = "";
          it._category = it.suggestedCategory || it.category;
          it._caption = it.summary || it.caption;
        }
      });

      var currentAlbum = "all";
      var currentStatus = "all";
      var visible = items.slice();
      var panelIndex = 0;

      function filtered() {
        return items.filter(function (it) {
          if (currentAlbum !== "all" && it._category !== currentAlbum && it.category !== currentAlbum) {
            return false;
          }
          if (currentStatus === "all") return true;
          if (currentStatus === "pending") return !it._action;
          return it._action === currentStatus;
        });
      }

      function countStatus(id) {
        if (id === "all") return items.length;
        if (id === "pending") return items.filter(function (it) { return !it._action; }).length;
        return items.filter(function (it) { return it._action === id; }).length;
      }

      function showToast(msg, ok) {
        if (!toast) return;
        toast.textContent = msg;
        toast.className = "review-toast show" + (ok === false ? " err" : "");
        clearTimeout(showToast._t);
        showToast._t = setTimeout(function () {
          toast.classList.remove("show");
        }, 3200);
      }

      function updateStats() {
        if (!stats) return;
        var pending = countStatus("pending");
        var done = items.length - pending;
        stats.textContent =
          done + " decided · " + pending + " pending · log: sor/desktop/f_root_review_log.jsonl";
      }

      function renderStatusBar() {
        if (!statusBar) return;
        var statuses = [
          { id: "all", label: "All" },
          { id: "pending", label: "Pending" },
          { id: "delete", label: "Delete" },
          { id: "archive", label: "Archive" },
          { id: "review", label: "Review" },
        ];
        statusBar.innerHTML = statuses
          .map(function (s) {
            var pressed = s.id === currentStatus ? "true" : "false";
            return (
              '<button type="button" data-status="' +
              esc(s.id) +
              '" aria-pressed="' +
              pressed +
              '">' +
              esc(s.label) +
              " (" +
              countStatus(s.id) +
              ")</button>"
            );
          })
          .join("");
        statusBar.querySelectorAll("button").forEach(function (btn) {
          btn.addEventListener("click", function () {
            currentStatus = btn.getAttribute("data-status");
            renderStatusBar();
            renderAlbums();
            renderGrid();
          });
        });
      }

      function renderAlbums() {
        if (!albumBar) return;
        var albums = [{ id: "all", label: "All categories", count: items.length }].concat(
          (data.categories || []).map(function (a) {
            return { id: a.id, label: a.label, count: a.count };
          })
        );
        albumBar.innerHTML = albums
          .map(function (a) {
            var pressed = a.id === currentAlbum ? "true" : "false";
            return (
              '<button type="button" data-album="' +
              esc(a.id) +
              '" aria-pressed="' +
              pressed +
              '">' +
              esc(a.label) +
              " (" +
              a.count +
              ")</button>"
            );
          })
          .join("");
        albumBar.querySelectorAll("button").forEach(function (btn) {
          btn.addEventListener("click", function () {
            currentAlbum = btn.getAttribute("data-album");
            renderAlbums();
            renderGrid();
          });
        });
      }

      function thumbHtml(it) {
        var thumb = it.previewSrc || (it.media === "image" ? it.src : null);
        if (thumb) {
          return (
            '<img src="' +
            esc(encodePath(resolveSrc(thumb))) +
            '" alt="' +
            esc(it.title) +
            '" loading="lazy">'
          );
        }
        var label = (it.media || "file").toUpperCase();
        return '<div class="doc-thumb" data-kind="' + esc(it.media) + '"><span>' + esc(label) + "</span></div>";
      }

      function badgeHtml(it) {
        var parts = [];
        if (!it._action) {
          parts.push('<span class="review-badge pending">pending</span>');
          if (it.suggestedAction) {
            parts.push(
              '<span class="review-badge suggest">→ ' + esc(it.suggestedAction) + "</span>"
            );
          }
        } else {
          parts.push('<span class="review-badge ' + esc(it._action) + '">' + esc(it._action) + "</span>");
        }
        return parts.join("");
      }

      function renderGrid() {
        visible = filtered();
        if (!grid) return;
        grid.innerHTML = visible
          .map(function (it, i) {
            return (
              '<button type="button" class="g-item review-item' +
              (it._action ? " decided-" + it._action : "") +
              '" data-idx="' +
              i +
              '">' +
              thumbHtml(it) +
              "<figcaption><strong>" +
              esc(it.title) +
              "</strong>" +
              badgeHtml(it) +
              "<span>" +
              esc(it._caption || it.path) +
              "</span></figcaption></button>"
            );
          })
          .join("");
        grid.querySelectorAll(".review-item").forEach(function (el) {
          el.addEventListener("click", function () {
            openPanel(Number(el.getAttribute("data-idx")));
          });
        });
        updateStats();
      }

      var panel = document.createElement("div");
      panel.className = "lightbox review-panel";
      panel.innerHTML =
        '<button type="button" class="lightbox-close" aria-label="Close">Close</button>' +
        '<button type="button" class="lightbox-nav prev" aria-label="Previous">‹</button>' +
        '<button type="button" class="lightbox-nav next" aria-label="Next">›</button>' +
        '<div class="lightbox-card review-card">' +
        '<div class="review-preview"></div>' +
        '<form class="review-form meta">' +
        "<h2></h2>" +
        '<p class="review-path"></p>' +
        '<label>Caption <textarea name="caption" rows="3"></textarea></label>' +
        '<label>Category <input name="category" list="category-list"></label>' +
        '<datalist id="category-list"></datalist>' +
        '<p class="review-suggested muted"></p>' +
        '<p class="review-excerpt muted"></p>' +
        '<p class="review-tags muted"></p>' +
        '<p class="review-meta muted"></p>' +
        '<div class="review-actions">' +
        '<button type="button" data-action="delete" class="btn-danger">Mark delete</button>' +
        '<button type="button" data-action="archive" class="btn-archive">Mark archive</button>' +
        '<button type="button" data-action="review" class="btn-review">Mark review</button>' +
        "</div>" +
        "</form></div>";
      document.body.appendChild(panel);

      var preview = panel.querySelector(".review-preview");
      var form = panel.querySelector(".review-form");
      var h2 = panel.querySelector("h2");
      var pathEl = panel.querySelector(".review-path");
      var metaEl = panel.querySelector(".review-meta");
      var suggestedEl = panel.querySelector(".review-suggested");
      var excerptEl = panel.querySelector(".review-excerpt");
      var tagsEl = panel.querySelector(".review-tags");
      var captionEl = form.querySelector('[name="caption"]');
      var categoryEl = form.querySelector('[name="category"]');
      var datalist = panel.querySelector("#category-list");

      datalist.innerHTML = (data.categories || [])
        .map(function (c) {
          return '<option value="' + esc(c.id) + '">' + esc(c.label) + "</option>";
        })
        .join("");

      function paintPanel() {
        var it = visible[panelIndex];
        if (!it) return;
        h2.textContent = it.title || it.path;
        pathEl.textContent = it.path;
        captionEl.value = it._caption || "";
        categoryEl.value = it._category || it.category || "";
        metaEl.textContent =
          (it.disposition ? "Auto: " + it.disposition : "") +
          (it.size ? " · " + it.size : "") +
          (it.bucket ? " · " + it.bucket : "") +
          (it.confidence ? " · GPT " + it.confidence : "");

        if (it.suggestedAction && !it._action) {
          suggestedEl.textContent =
            "GPT suggests: " +
            it.suggestedAction +
            (it.suggestedCategoryLabel ? " · " + it.suggestedCategoryLabel : "");
        } else {
          suggestedEl.textContent = "";
        }

        excerptEl.textContent = it.excerpt ? "Excerpt: " + it.excerpt : "";
        tagsEl.textContent =
          it.tags && it.tags.length ? "Tags: " + it.tags.join(", ") : "";

        preview.innerHTML = "";
        var big = it.previewSrc || (it.media === "image" ? it.src : null);
        if (big) {
          var img = document.createElement("img");
          img.src = encodePath(resolveSrc(big));
          img.alt = it.title;
          preview.appendChild(img);
        } else if (it.media === "pdf" && it.src) {
          var iframe = document.createElement("iframe");
          iframe.src = encodePath(resolveSrc(it.src));
          iframe.title = it.title;
          preview.appendChild(iframe);
        } else {
          var box = document.createElement("div");
          box.className = "doc-thumb large";
          box.innerHTML = "<span>" + esc((it.media || "file").toUpperCase()) + "</span>";
          preview.appendChild(box);
        }
      }

      function openPanel(i) {
        panelIndex = i;
        paintPanel();
        panel.classList.add("open");
      }

      function closePanel() {
        panel.classList.remove("open");
      }

      async function saveAction(action) {
        var it = visible[panelIndex];
        if (!it) return;
        var payload = {
          path: it.path,
          action: action,
          category: categoryEl.value.trim() || it.category,
          caption: captionEl.value.trim(),
          title: it.title,
        };
        try {
          var res = await fetch("/api/f-root-review/log", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          if (!res.ok) throw new Error("HTTP " + res.status);
          it._action = action;
          it._category = payload.category;
          it._caption = payload.caption;
          decisions[it.path] = payload;
          showToast("Saved · " + it.path);
          renderStatusBar();
          renderGrid();
          paintPanel();
        } catch (err) {
          console.error(err);
          showToast("Save failed — is serve_portal.py running?", false);
        }
      }

      panel.querySelector(".lightbox-close").addEventListener("click", closePanel);
      panel.addEventListener("click", function (e) {
        if (e.target === panel) closePanel();
      });
      panel.querySelector(".prev").addEventListener("click", function (e) {
        e.stopPropagation();
        panelIndex = (panelIndex - 1 + visible.length) % visible.length;
        paintPanel();
      });
      panel.querySelector(".next").addEventListener("click", function (e) {
        e.stopPropagation();
        panelIndex = (panelIndex + 1 + visible.length) % visible.length;
        paintPanel();
      });
      panel.querySelectorAll("[data-action]").forEach(function (btn) {
        btn.addEventListener("click", function (e) {
          e.preventDefault();
          saveAction(btn.getAttribute("data-action"));
        });
      });

      document.addEventListener("keydown", function (e) {
        if (!panel.classList.contains("open")) return;
        if (e.key === "Escape") closePanel();
        if (e.key === "ArrowLeft") {
          panelIndex = (panelIndex - 1 + visible.length) % visible.length;
          paintPanel();
        }
        if (e.key === "ArrowRight") {
          panelIndex = (panelIndex + 1 + visible.length) % visible.length;
          paintPanel();
        }
      });

      renderStatusBar();
      renderAlbums();
      renderGrid();
      return data;
    },
  };
})();
