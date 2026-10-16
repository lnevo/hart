(function () {
  var DATA_URL = "data/layout-index-cats.json";
  var IMAGE_FALLBACK = "assets/layout/HART_cats_digicon.png";
  var ZOOM_MIN = 0.2;
  var ZOOM_MAX = 1.2;
  var ZOOM_STEP = 0.05;
  var DEFAULT_ZOOM = 0.75;

  var state = {
    data: null,
    kind: { turnout: true, signal: true },
    q: "",
    activeId: null,
    zoom: DEFAULT_ZOOM,
    naturalW: 0,
    naturalH: 0,
  };

  function $(sel) {
    return document.querySelector(sel);
  }

  function api() {
    return window.HARTOps || window.HARTOps;
  }

  function base() {
    return api() ? api().base() : "../";
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function row(k, v) {
    return (
      "<dt>" +
      escapeHtml(k) +
      "</dt><dd>" +
      escapeHtml(String(v == null || v === "" ? "—" : v)) +
      "</dd>"
    );
  }

  function showDetail(item) {
    var el = $("#detail");
    if (!el) return;
    if (!item) {
      el.innerHTML =
        '<p class="empty">Click a switch or mast on the Digicon board.</p>';
      return;
    }
    el.innerHTML =
      "<h2>" +
      escapeHtml(item.publicName || item.systemName) +
      "</h2><dl>" +
      row("Kind", item.kind) +
      row("System", item.systemName) +
      row("Control point", item.cp) +
      row("Hardware", item.hardware) +
      row("MQTT", item.mqtt) +
      row("Block", item.block) +
      row("Notes", item.comment) +
      '</dl><p><a href="' +
      base() +
      "roster/index.html#" +
      encodeURIComponent(item.id) +
      '">Open in roster →</a></p>';
  }

  function matches(item) {
    if (!state.kind[item.kind]) return false;
    if (item.x == null) return false;
    if (!state.q) return true;
    var q = state.q.toLowerCase();
    return [item.publicName, item.systemName, item.cp, item.hardware, item.mqtt, item.comment]
      .join(" ")
      .toLowerCase()
      .indexOf(q) >= 0;
  }

  function centerInView() {
    var scroll = $(".map-scroll");
    var wrap = $("#map-zoom-wrap");
    if (!scroll || !wrap) return;
    requestAnimationFrame(function () {
      var maxX = Math.max(0, wrap.offsetWidth - scroll.clientWidth);
      var maxY = Math.max(0, wrap.offsetHeight - scroll.clientHeight);
      scroll.scrollLeft = maxX / 2;
      scroll.scrollTop = maxY / 2;
    });
  }

  function applyZoom() {
    var z = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, state.zoom));
    state.zoom = z;
    var stage = $("#map-stage");
    var wrap = $("#map-zoom-wrap");
    var label = $("#zoom-label");
    var range = $("#zoom-range");
    if (stage) {
      stage.style.transform = "scale(" + z + ")";
      stage.style.transformOrigin = "0 0";
    }
    if (wrap && state.naturalW && state.naturalH) {
      wrap.style.width = Math.ceil(state.naturalW * z) + "px";
      wrap.style.height = Math.ceil(state.naturalH * z) + "px";
    }
    if (label) label.textContent = Math.round(z * 100) + "%";
    if (range) range.value = String(Math.round(z * 100));
    centerInView();
  }

  function fitWidth() {
    var scroll = $(".map-scroll");
    if (!scroll || !state.naturalW) return;
    var avail = Math.max(200, scroll.clientWidth - 8);
    state.zoom = Math.max(ZOOM_MIN, Math.min(1, avail / state.naturalW));
    applyZoom();
  }

  function resetDefaultZoom() {
    state.zoom = DEFAULT_ZOOM;
    applyZoom();
  }

  function paint() {
    var stage = $("#map-stage");
    if (!stage || !state.data) return;
    stage.querySelectorAll(".hotspot").forEach(function (n) {
      n.remove();
    });
    (state.data.items || []).forEach(function (item) {
      if (item.x == null || item.y == null) return;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "hotspot " + item.kind + (matches(item) ? "" : " dim");
      if (item.id === state.activeId) btn.classList.add("active");
      btn.style.left = item.x + "px";
      btn.style.top = item.y + "px";
      btn.title = item.publicName || item.systemName;
      btn.setAttribute("aria-label", item.publicName || item.systemName || item.kind);
      btn.addEventListener("click", function () {
        state.activeId = item.id;
        paint();
        showDetail(item);
      });
      stage.appendChild(btn);
    });
  }

  function updateMeta() {
    var c = (state.data && state.data.counts) || {};
    var meta = $("#layout-meta");
    if (!meta) return;
    meta.textContent =
      "Digicon Master · " +
      (c.mapped || 0) +
      " devices · " +
      (c.turnout || 0) +
      " switches · " +
      (c.signal || 0) +
      " masts · panel photos in Photos → Control panels";
  }

  async function load() {
    state.activeId = null;
    var b = base();
    var res = await fetch(b + DATA_URL);
    if (!res.ok) throw new Error(DATA_URL + " " + res.status);
    state.data = await res.json();
    var img = $("#schematic");
    var imagePath = (state.data.image && state.data.image.path) || IMAGE_FALLBACK;

    function onReady() {
      state.naturalW = img.naturalWidth || (state.data.image && state.data.image.width) || 0;
      state.naturalH = img.naturalHeight || (state.data.image && state.data.image.height) || 0;
      resetDefaultZoom();
      paint();
    }

    if (img) {
      img.onload = onReady;
      img.onerror = function () {
        var meta = $("#layout-meta");
        if (meta) meta.textContent = "Map image failed to load: " + imagePath;
      };
      img.src = b + imagePath;
      if (img.complete && img.naturalWidth) onReady();
    }
    updateMeta();
    showDetail(null);
  }

  async function init() {
    document.querySelectorAll("[data-kind]").forEach(function (el) {
      el.addEventListener("change", function () {
        state.kind[el.getAttribute("data-kind")] = el.checked;
        paint();
      });
    });
    var search = $("#layout-search");
    if (search) {
      search.addEventListener("input", function () {
        state.q = search.value.trim();
        paint();
      });
    }

    var range = $("#zoom-range");
    if (range) {
      range.addEventListener("input", function () {
        state.zoom = Number(range.value) / 100;
        applyZoom();
      });
    }
    var zin = $("#zoom-in");
    if (zin) {
      zin.addEventListener("click", function () {
        state.zoom = Math.min(ZOOM_MAX, state.zoom + ZOOM_STEP);
        applyZoom();
      });
    }
    var zout = $("#zoom-out");
    if (zout) {
      zout.addEventListener("click", function () {
        state.zoom = Math.max(ZOOM_MIN, state.zoom - ZOOM_STEP);
        applyZoom();
      });
    }
    var zfit = $("#zoom-fit");
    if (zfit) {
      zfit.addEventListener("click", fitWidth);
    }
    window.addEventListener("resize", function () {
      // Keep current zoom on resize; user can hit Fit.
    });

    await load();
  }

  window.HARTLayoutExplorer = {
    reload: function () {
      return load().catch(function (err) {
        console.error(err);
        var meta = $("#layout-meta");
        if (meta) meta.textContent = "Layout failed to load — " + err.message;
      });
    },
  };

  document.addEventListener("DOMContentLoaded", function () {
    var ops = api();
    if (!ops) {
      console.error("HARTOps nav.js did not load");
      return;
    }
    Promise.resolve(ops.mountChrome("layout"))
      .then(init)
      .catch(function (err) {
        console.error(err);
        var meta = $("#layout-meta");
        if (meta) meta.textContent = "Layout failed to load — " + err.message;
      });
  });
})();
