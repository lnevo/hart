// Rolling stock: album tabs, a road / car type / number filter bar, and three views
// (Grid = the masonry cards, List = a sortable-looking table, Gallery = one big image
// with a thumbnail strip). Data: data/fleet-gallery.json items carry road, number, type.
(function () {
  var VIEW_KEY = "hart.fleet.view";
  var VIEWS = [
    { id: "grid", label: "Grid" },
    { id: "list", label: "List" },
    { id: "gallery", label: "Gallery" },
  ];

  var esc = HARTOps.esc;

  // Grid, list, and strip show the build's thumbnail (item.thumb, with the full image's width/height
  // to reserve space); the stage and lightbox open the full src.
  function thumbImg(it, alt) {
    return (
      '<img src="' + esc(resolveSrc(it.thumb || it.src)) + '" alt="' + esc(alt) + '"' +
      (it.width && it.height ? ' width="' + Number(it.width) + '" height="' + Number(it.height) + '"' : "") +
      ' loading="lazy" decoding="async">'
    );
  }

  function resolveSrc(src) {
    if (!src) return "";
    if (/^https?:\/\//i.test(src) || src.startsWith("data:")) return src;
    return HARTOps.base() + src;
  }

  // The note after "ROAD · Type ·" in the caption; road and type have their own columns.
  // Captions without that shape (the power art) are shown whole.
  function note(it) {
    var parts = String(it.caption || "").split(" · ");
    if (parts.length > 2) return parts.slice(2).join(" · ");
    return parts.length === 2 ? "" : it.caption || "";
  }

  window.HARTFleet = {
    // opts.heading === false keeps the page's own title and lede (the Photos page).
    mount: async function (opts) {
      opts = opts || {};
      var data = await HARTOps.loadJson("data/fleet-gallery.json");
      var items = data.items || [];
      if (opts.heading !== false) {
        document.getElementById("gallery-title").textContent = "Rolling stock";
        document.getElementById("gallery-lede").textContent = data.lede || "";
      }

      var albumBar = document.getElementById("album-bar");
      var viewBar = document.getElementById("view-bar");
      var roadSel = document.getElementById("filter-road");
      var typeSel = document.getElementById("filter-type");
      var numInput = document.getElementById("filter-number");
      var clearBtn = document.getElementById("filter-clear");
      var countEl = document.getElementById("filter-count");
      var out = document.getElementById("fleet-view");

      var view = "grid";
      try {
        var saved = localStorage.getItem(VIEW_KEY);
        if (VIEWS.some(function (v) { return v.id === saved; })) view = saved;
      } catch (e) {}

      var state = { album: "all", road: "", type: "", q: "" };
      // ?view=list&road=B%26O&type=Hopper&q=4674 opens a shareable filtered view.
      var params = new URLSearchParams(location.search);
      if (VIEWS.some(function (v) { return v.id === params.get("view"); })) view = params.get("view");
      state.road = params.get("road") || "";
      state.type = params.get("type") || "";
      state.q = params.get("q") || "";
      numInput.value = state.q;
      var visible = [];
      var galleryIndex = 0;

      function inAlbum() {
        if (state.album === "all") return items;
        return items.filter(function (it) { return it.album === state.album; });
      }

      function filtered() {
        var q = state.q.trim().toLowerCase();
        return inAlbum().filter(function (it) {
          if (state.road && it.road !== state.road) return false;
          if (state.type && it.type !== state.type) return false;
          if (q) {
            var hay = (String(it.number || "") + " " + (it.title || "")).toLowerCase();
            if (hay.indexOf(q) === -1) return false;
          }
          return true;
        });
      }

      function optionList(sel, field, allLabel) {
        // Counts reflect the album and the other filter, so empty choices never appear.
        var pool = inAlbum().filter(function (it) {
          if (field !== "road" && state.road && it.road !== state.road) return false;
          if (field !== "type" && state.type && it.type !== state.type) return false;
          return true;
        });
        var counts = {};
        pool.forEach(function (it) {
          var v = it[field];
          if (v) counts[v] = (counts[v] || 0) + 1;
        });
        var keys = Object.keys(counts).sort();
        if (state[field] && keys.indexOf(state[field]) === -1) state[field] = "";
        sel.innerHTML =
          '<option value="">' + esc(allLabel) + "</option>" +
          keys
            .map(function (k) {
              return '<option value="' + esc(k) + '"' + (k === state[field] ? " selected" : "") + ">" + esc(k) + " (" + counts[k] + ")</option>";
            })
            .join("");
      }

      function renderAlbums() {
        var albums = [{ id: "all", label: "All", count: items.length }].concat(data.albums || []);
        albumBar.innerHTML = albums
          .map(function (a) {
            return (
              '<button type="button" data-album="' + esc(a.id) + '" aria-pressed="' + (a.id === state.album) + '">' +
              esc(a.label) + " (" + a.count + ")</button>"
            );
          })
          .join("");
        albumBar.querySelectorAll("button").forEach(function (b) {
          b.addEventListener("click", function () {
            state.album = b.getAttribute("data-album");
            galleryIndex = 0;
            renderAll();
          });
        });
      }

      function renderViews() {
        viewBar.innerHTML = VIEWS.map(function (v) {
          return '<button type="button" data-view="' + v.id + '" aria-pressed="' + (v.id === view) + '">' + v.label + "</button>";
        }).join("");
        viewBar.querySelectorAll("button").forEach(function (b) {
          b.addEventListener("click", function () {
            view = b.getAttribute("data-view");
            try {
              localStorage.setItem(VIEW_KEY, view);
            } catch (e) {}
            renderViews();
            renderItems();
          });
        });
      }

      function gridHtml() {
        return (
          '<div class="gallery-masonry">' +
          visible
            .map(function (it, i) {
              return (
                '<button type="button" class="g-item" data-idx="' + i + '">' +
                thumbImg(it, it.title) +
                "<figcaption><strong>" + esc(it.title) + "</strong><span>" + esc(it.caption) + "</span></figcaption></button>"
              );
            })
            .join("") +
          "</div>"
        );
      }

      function listHtml() {
        return (
          '<div class="fleet-list-wrap"><table class="fleet-list">' +
          "<thead><tr><th></th><th>Road</th><th>Number</th><th>Type</th><th class=\"fl-note\">Notes</th></tr></thead><tbody>" +
          visible
            .map(function (it, i) {
              return (
                '<tr data-idx="' + i + '" tabindex="0">' +
                '<td class="fl-thumb">' + thumbImg(it, "") + "</td>" +
                "<td>" + esc(it.road || "—") + "</td>" +
                '<td class="fl-num">' + esc(it.number || "—") + "</td>" +
                "<td>" + esc(it.type || "—") + "</td>" +
                '<td class="fl-note">' + esc(note(it)) + "</td></tr>"
              );
            })
            .join("") +
          "</tbody></table></div>"
        );
      }

      function galleryHtml() {
        var it = visible[galleryIndex];
        return (
          '<div class="fleet-stage">' +
          '<button type="button" class="fleet-stage-nav prev" aria-label="Previous">‹</button>' +
          '<figure><img src="' + esc(resolveSrc(it.src)) + '" alt="' + esc(it.title) + '">' +
          "<figcaption><strong>" + esc(it.title) + "</strong> " +
          '<span class="muted">' + esc(galleryIndex + 1) + " of " + visible.length + "</span><br>" +
          esc(it.caption) + "</figcaption></figure>" +
          '<button type="button" class="fleet-stage-nav next" aria-label="Next">›</button>' +
          "</div>" +
          '<div class="fleet-strip" role="list">' +
          visible
            .map(function (x, i) {
              return (
                '<button type="button" role="listitem" data-idx="' + i + '"' + (i === galleryIndex ? ' aria-current="true"' : "") +
                ' title="' + esc(x.title) + '">' + thumbImg(x, x.title) + "</button>"
              );
            })
            .join("") +
          "</div>"
        );
      }

      function step(d) {
        galleryIndex = (galleryIndex + d + visible.length) % visible.length;
        renderItems();
      }

      function renderItems() {
        visible = filtered();
        countEl.textContent = visible.length + " of " + inAlbum().length;
        clearBtn.hidden = !(state.road || state.type || state.q);
        if (!visible.length) {
          out.innerHTML = '<p class="muted fleet-empty">No cars match. Try another road, type, or number.</p>';
          return;
        }
        if (galleryIndex >= visible.length) galleryIndex = 0;
        out.className = "fleet-view view-" + view;
        if (view === "list") out.innerHTML = listHtml();
        else if (view === "gallery") out.innerHTML = galleryHtml();
        else out.innerHTML = gridHtml();

        if (view === "gallery") {
          out.querySelector(".prev").addEventListener("click", function () { step(-1); });
          out.querySelector(".next").addEventListener("click", function () { step(1); });
          out.querySelectorAll(".fleet-strip button").forEach(function (b) {
            b.addEventListener("click", function () {
              galleryIndex = Number(b.getAttribute("data-idx"));
              renderItems();
            });
          });
          var cur = out.querySelector('.fleet-strip [aria-current="true"]');
          if (cur && cur.scrollIntoView) cur.scrollIntoView({ block: "nearest", inline: "center" });
        } else {
          out.querySelectorAll("[data-idx]").forEach(function (el) {
            el.addEventListener("click", function () { openLightbox(Number(el.getAttribute("data-idx"))); });
            el.addEventListener("keydown", function (e) {
              if (e.key === "Enter") openLightbox(Number(el.getAttribute("data-idx")));
            });
          });
        }
      }

      function renderAll() {
        renderAlbums();
        optionList(roadSel, "road", "All roads");
        optionList(typeSel, "type", "All car types");
        renderItems();
      }

      roadSel.addEventListener("change", function () {
        state.road = roadSel.value;
        galleryIndex = 0;
        renderAll();
      });
      typeSel.addEventListener("change", function () {
        state.type = typeSel.value;
        galleryIndex = 0;
        renderAll();
      });
      numInput.addEventListener("input", function () {
        state.q = numInput.value;
        galleryIndex = 0;
        renderItems();
      });
      clearBtn.addEventListener("click", function () {
        state.road = state.type = state.q = "";
        numInput.value = "";
        renderAll();
      });

      // —— Lightbox (grid and list) ——
      var lb = document.createElement("div");
      lb.className = "lightbox";
      lb.innerHTML =
        '<button type="button" class="lightbox-close" aria-label="Close">Close</button>' +
        '<button type="button" class="lightbox-nav prev" aria-label="Previous">‹</button>' +
        '<button type="button" class="lightbox-nav next" aria-label="Next">›</button>' +
        '<div class="lightbox-card"><img alt=""><div class="meta"><h2></h2><p></p><div class="credit"></div></div></div>';
      document.body.appendChild(lb);
      var lbIndex = 0;

      function paint() {
        var it = visible[lbIndex];
        if (!it) return;
        lb.querySelector("img").src = resolveSrc(it.src);
        lb.querySelector("img").alt = it.title || "";
        lb.querySelector("h2").textContent = it.title || "";
        lb.querySelector("p").textContent = it.caption || "";
        lb.querySelector(".credit").textContent = it.credit || "";
      }
      function openLightbox(i) {
        lbIndex = i;
        paint();
        lb.classList.add("open");
      }
      function closeLightbox() {
        lb.classList.remove("open");
      }
      lb.querySelector(".lightbox-close").addEventListener("click", closeLightbox);
      lb.addEventListener("click", function (e) { if (e.target === lb) closeLightbox(); });
      lb.querySelector(".prev").addEventListener("click", function (e) {
        e.stopPropagation();
        lbIndex = (lbIndex - 1 + visible.length) % visible.length;
        paint();
      });
      lb.querySelector(".next").addEventListener("click", function (e) {
        e.stopPropagation();
        lbIndex = (lbIndex + 1) % visible.length;
        paint();
      });
      document.addEventListener("keydown", function (e) {
        if (lb.classList.contains("open")) {
          if (e.key === "Escape") closeLightbox();
          if (e.key === "ArrowLeft") { lbIndex = (lbIndex - 1 + visible.length) % visible.length; paint(); }
          if (e.key === "ArrowRight") { lbIndex = (lbIndex + 1) % visible.length; paint(); }
          return;
        }
        if (view === "gallery" && visible.length && document.activeElement !== numInput) {
          if (e.key === "ArrowLeft") step(-1);
          if (e.key === "ArrowRight") step(1);
        }
      });

      renderViews();
      renderAll();
    },
  };
})();
