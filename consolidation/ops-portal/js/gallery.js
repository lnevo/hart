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
    if (/^https?:\/\//i.test(src) || src.startsWith("data:") || src.startsWith("../")) {
      // Already rooted outside the page (e.g. ../external/...) — leave alone.
      // For nested pages, ../external from portal JSON is wrong; rewrite to ../../external.
      var depth = HARTOps.base();
      if (src.startsWith("../external/") && depth === "../") {
        return src.replace(/^\.\.\//, "../../");
      }
      if (src.startsWith("assets/") || src.startsWith("data/")) {
        return depth + src;
      }
      return src;
    }
    return HARTOps.base() + src;
  }

  window.HARTGallery = {
    mount: async function (opts) {
      opts = opts || {};
      var data = await HARTOps.loadJson(opts.dataUrl || "data/gallery.json");
      var albumBar = document.querySelector(opts.albumBar || "#album-bar");
      var grid = document.querySelector(opts.grid || "#gallery-grid");
      var lede = document.querySelector(opts.lede || "#gallery-lede");
      var title = document.querySelector(opts.title || "#gallery-title");
      if (title) title.textContent = data.title || "Photo gallery";
      if (lede) lede.textContent = data.lede || "";

      var items = data.items || [];
      var currentAlbum = "all";
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
        var albums = [{ id: "all", label: "All", count: items.length }].concat(
          (data.albums || []).map(function (a) {
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

      function renderGrid() {
        visible = filtered();
        if (!grid) return;
        grid.innerHTML = visible
          .map(function (it, i) {
            return (
              '<button type="button" class="g-item" data-idx="' +
              i +
              '">' +
              '<img src="' +
              esc(resolveSrc(it.src)) +
              '" alt="' +
              esc(it.title) +
              '" loading="lazy">' +
              "<figcaption><strong>" +
              esc(it.title) +
              "</strong><span>" +
              esc(it.caption) +
              "</span></figcaption></button>"
            );
          })
          .join("");
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
        lbC.textContent = it.credit || "";
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
