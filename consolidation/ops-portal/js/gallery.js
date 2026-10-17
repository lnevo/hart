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

  window.HARTGallery = {
    mount: async function (opts) {
      opts = opts || {};
      var data = await HARTOps.loadJson(opts.dataUrl || "data/gallery.json");
      var albumBar = document.querySelector(opts.albumBar || "#album-bar");
      var grid = document.querySelector(opts.grid || "#gallery-grid");
      var lede = document.querySelector(opts.lede || "#gallery-lede");
      var title = document.querySelector(opts.title || "#gallery-title");
      // opts.heading === false keeps the page's own title and lede.
      if (opts.heading !== false) {
        if (title) title.textContent = data.title || "Photo gallery";
        if (lede) lede.textContent = data.lede || "";
      }

      // opts.albums limits the page to those album ids (e.g. ["plans", "build"]).
      var only = opts.albums && opts.albums.length ? opts.albums : null;
      function scoped(list) {
        if (!only) return list || [];
        return (list || []).filter(function (it) {
          return only.indexOf(it.album) !== -1;
        });
      }
      function scopedAlbums() {
        var albums = data.albums || [];
        if (!only) return albums;
        return only
          .map(function (id) {
            return albums.find(function (a) { return a.id === id; });
          })
          .filter(Boolean);
      }

      var items = scoped(data.items);
      var currentAlbum = opts.album || (only && only.length === 1 ? only[0] : "all");

      // Local curation (engineering desk only): opts.curate names the API; it is used only
      // when the site is not public and the local review server answers.
      var canEdit = false;
      if (opts.curate) {
        try {
          var site = await HARTOps.loadSite();
          if (!site.public) canEdit = (await fetch(opts.curate + "/ping", { cache: "no-cache" })).ok;
        } catch (e) {
          canEdit = false;
        }
      }
      var editbar = document.querySelector(opts.editbar || "#gallery-editbar");
      if (editbar) editbar.hidden = !canEdit;
      var toast = document.querySelector(opts.toast || "#gallery-toast");

      function showToast(msg, bad) {
        if (!toast) return;
        toast.textContent = msg;
        toast.classList.toggle("bad", !!bad);
        toast.classList.add("show");
        clearTimeout(showToast.t);
        showToast.t = setTimeout(function () {
          toast.classList.remove("show");
        }, 2600);
      }

      async function save(src, changes) {
        var res = await fetch(opts.curate + "/item", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(Object.assign({ src: src }, changes)),
        });
        var payload = await res.json().catch(function () { return {}; });
        if (!res.ok) throw new Error(payload.error || "HTTP " + res.status);
        data = payload.gallery;
        items = scoped(data.items);
      }

      function curateControls(it) {
        var albumOpts = (data.albums || [])
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

      function bindCurate() {
        async function run(src, changes, msg) {
          try {
            await save(src, changes);
            showToast(msg);
            renderAlbums();
            renderGrid();
          } catch (err) {
            showToast("Not saved: " + err.message, true);
          }
        }
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
            var it = items.find(function (x) { return x.src === src; }) || {};
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
      var visible = items.slice();
      var lbIndex = 0;

      function filtered() {
        if (currentAlbum === "all") return items;
        return items.filter(function (it) {
          return it.album === currentAlbum;
        });
      }

      function renderAlbums() {
        if (!albumBar) return;
        var albums = scopedAlbums().map(function (a) {
          return { id: a.id, label: a.label, count: a.count };
        });
        if (albums.length > 1) albums.unshift({ id: "all", label: "All", count: items.length });
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

      function cellHtml(it, i) {
        var p = opts.groupBy === "month" ? parseDate(it.date) : null;
        var when = p ? '<time datetime="' + esc(it.date) + '">' + (p.d ? p.d + " " : "") + MONTHS[p.m - 1].slice(0, 3) + "</time>" : "";
        return (
          (canEdit ? '<div class="g-cell">' : "") +
          '<button type="button" class="g-item" data-idx="' +
          i +
          '">' +
          '<img src="' +
          esc(resolveSrc(it.src)) +
          '" alt="' +
          esc(it.title) +
          '" loading="lazy">' +
          "<figcaption>" +
          when +
          "<strong>" +
          esc(it.title) +
          "</strong><span>" +
          esc(it.caption) +
          "</span></figcaption></button>" +
          (canEdit ? curateControls(it) + "</div>" : "")
        );
      }

      // opts.groupBy === "month": one row per month, in the album's own order (a timeline).
      function monthGroups() {
        var groups = [];
        visible.forEach(function (it, i) {
          var p = parseDate(it.date);
          var key = p ? p.y + "-" + p.m : "undated";
          var last = groups[groups.length - 1];
          if (!last || last.key !== key) {
            last = { key: key, label: p ? MONTHS[p.m - 1] : "Undated", year: p ? p.y : "", cells: [] };
            groups.push(last);
          }
          last.cells.push(cellHtml(it, i));
        });
        return groups
          .map(function (g) {
            return (
              '<section class="g-month">' +
              '<h3 class="g-month-label">' +
              esc(g.label) +
              " <span>" +
              esc(g.year) +
              "</span></h3>" +
              '<div class="g-strip">' +
              g.cells.join("") +
              "</div></section>"
            );
          })
          .join("");
      }

      function renderGrid() {
        visible = filtered();
        if (!grid) return;
        grid.innerHTML = opts.groupBy === "month" ? monthGroups() : visible.map(cellHtml).join("");
        if (canEdit) bindCurate();
        grid.querySelectorAll(".g-item").forEach(function (el) {
          el.addEventListener("click", function () {
            openLightbox(Number(el.getAttribute("data-idx")));
          });
        });
      }

      var lb = document.createElement("div");
      lb.className = "lightbox";
      lb.innerHTML =
        '<button type="button" class="lightbox-close" aria-label="Close">Close</button>' +
        '<button type="button" class="lightbox-nav prev" aria-label="Previous">‹</button>' +
        '<button type="button" class="lightbox-nav next" aria-label="Next">›</button>' +
        '<div class="lightbox-card">' +
        '<img alt="">' +
        '<div class="meta"><h2></h2><p></p><div class="credit"></div></div>' +
        "</div>";
      document.body.appendChild(lb);
      var lbImg = lb.querySelector("img");
      var lbH = lb.querySelector("h2");
      var lbP = lb.querySelector("p");
      var lbC = lb.querySelector(".credit");

      function paintLightbox() {
        var it = visible[lbIndex];
        if (!it) return;
        lbImg.src = resolveSrc(it.src);
        lbImg.alt = it.title || "";
        lbH.textContent = it.title || "";
        lbP.textContent = it.caption || "";
        lbC.textContent = [longDate(it.date), it.credit].filter(Boolean).join(" · ");
      }

      function openLightbox(i) {
        lbIndex = i;
        paintLightbox();
        lb.classList.add("open");
      }

      function closeLightbox() {
        lb.classList.remove("open");
      }

      lb.querySelector(".lightbox-close").addEventListener("click", closeLightbox);
      lb.addEventListener("click", function (e) {
        if (e.target === lb) closeLightbox();
      });
      lb.querySelector(".prev").addEventListener("click", function (e) {
        e.stopPropagation();
        lbIndex = (lbIndex - 1 + visible.length) % visible.length;
        paintLightbox();
      });
      lb.querySelector(".next").addEventListener("click", function (e) {
        e.stopPropagation();
        lbIndex = (lbIndex + 1) % visible.length;
        paintLightbox();
      });
      document.addEventListener("keydown", function (e) {
        if (!lb.classList.contains("open")) return;
        if (e.key === "Escape") closeLightbox();
        if (e.key === "ArrowLeft") {
          lbIndex = (lbIndex - 1 + visible.length) % visible.length;
          paintLightbox();
        }
        if (e.key === "ArrowRight") {
          lbIndex = (lbIndex + 1) % visible.length;
          paintLightbox();
        }
      });

      renderAlbums();
      renderGrid();
      return data;
    },
  };
})();
