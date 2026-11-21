(function () {
  var DATA_URL = "data/layout-index-cats.json";
  var IMAGE_FALLBACK = "assets/layout/HART_cats_digicon.png";
  var ZOOM_MAX = 1.5; // past the image's own pixels it only blurs
  var ZOOM_FACTOR = 1.25; // one press of + or -, and the most one wheel event may zoom
  var HOTSPOT_PX = 14; // a dot's size on the map image (.hotspot in ops.css)
  var HOTSPOT_MIN_PX = 12; // the smallest a dot may look on screen
  var MV = window.HARTMapView;

  var state = {
    data: null,
    kind: { turnout: true, signal: true },
    q: "",
    activeId: null,
    zoom: 1,
    fit: 1, // the zoom that shows the whole map; also the lowest zoom
    naturalW: 0,
    naturalH: 0,
  };

  function $(sel) {
    return document.querySelector(sel);
  }

  var base = HARTOps.base;
  var esc = HARTOps.esc;

  function row(k, v) {
    return (
      "<dt>" +
      esc(k) +
      "</dt><dd>" +
      esc(String(v == null || v === "" ? "—" : v)) +
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
      esc(item.publicName || item.systemName) +
      "</h2><dl>" +
      row("Kind", item.kind) +
      row("System", item.systemName) +
      row("Control point", (item.cp || "").split(";").filter(Boolean).join(", ")) +
      row("Hardware", item.hardware) +
      row("MQTT", item.mqtt) +
      row("Block", item.block) +
      row("Notes", item.comment) +
      '</dl><p><a href="' +
      base() +
      "roster/index.html#" +
      encodeURIComponent(item.id) +
      '">Open in device viewer →</a></p>';
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

  // The scroll box, the scaled map's box inside it, and where that box starts (centred while smaller than the view).
  function view() {
    var scroll = $("#map-scroll");
    var wrap = $("#map-zoom-wrap");
    return {
      scroll: scroll,
      v: {
        scrollLeft: scroll.scrollLeft,
        scrollTop: scroll.scrollTop,
        offX: wrap.offsetLeft,
        offY: wrap.offsetTop,
        zoom: state.zoom,
      },
      w: scroll.clientWidth,
      h: scroll.clientHeight,
    };
  }

  // Zoom to z keeping the map point under view position (fx, fy) where it is; the view centre when fx is null.
  function zoomTo(z, fx, fy) {
    if (!state.naturalW) return;
    var before = view();
    if (fx == null) {
      fx = before.w / 2;
      fy = before.h / 2;
    }
    var p = MV.pointAt(before.v, fx, fy);
    state.zoom = MV.clamp(z, state.fit, ZOOM_MAX);
    var stage = $("#map-stage");
    var wrap = $("#map-zoom-wrap");
    stage.style.transform = "scale(" + state.zoom + ")";
    stage.style.setProperty("--hotspot-scale", String(Math.max(1, HOTSPOT_MIN_PX / (HOTSPOT_PX * state.zoom))));
    // floor: a box rounded up past the frame would show scrollbars at Fit
    wrap.style.width = Math.floor(state.naturalW * state.zoom) + "px";
    wrap.style.height = Math.floor(state.naturalH * state.zoom) + "px";
    var after = view(); // the box has moved now the map is a new size
    var s = MV.scrollFor(p, state.zoom, fx, fy, after.v.offX, after.v.offY);
    after.scroll.scrollLeft = s.left;
    after.scroll.scrollTop = s.top;
    $("#zoom-label").textContent = Math.round(state.zoom * 100) + "%";
    $("#zoom-range").value = String(Math.round(state.zoom * 100));
    updateOverview();
  }

  // Measure the frame with nothing in it, so scrollbars from the current zoom do not shrink the fit.
  function measureFit() {
    var scroll = $("#map-scroll");
    var wrap = $("#map-zoom-wrap");
    var saved = [wrap.style.width, wrap.style.height];
    wrap.style.width = wrap.style.height = "0px";
    state.fit = MV.fitZoom(scroll.clientWidth, scroll.clientHeight, state.naturalW, state.naturalH);
    wrap.style.width = saved[0];
    wrap.style.height = saved[1];
    var range = $("#zoom-range");
    range.min = String(Math.ceil(state.fit * 100));
    range.max = String(Math.round(ZOOM_MAX * 100));
  }

  function fitAll() {
    measureFit();
    zoomTo(state.fit);
  }

  // The overview in the corner: the whole map, with a box round the part the main view shows. Hidden at Fit.
  function updateOverview() {
    var box = $("#overview");
    if (!box || !state.naturalW) return;
    var vw = view();
    var r = MV.viewRect(vw.v, vw.w, vw.h, state.naturalW, state.naturalH);
    box.hidden = MV.showsAll(r);
    var frame = $("#overview-view");
    frame.style.left = r.x * 100 + "%";
    frame.style.top = r.y * 100 + "%";
    frame.style.width = r.w * 100 + "%";
    frame.style.height = r.h * 100 + "%";
  }

  // Centre the main view on the map point under the pointer in the overview.
  function panFromOverview(ev) {
    var img = $("#overview-img").getBoundingClientRect();
    var p = {
      x: MV.clamp((ev.clientX - img.left) / img.width, 0, 1) * state.naturalW,
      y: MV.clamp((ev.clientY - img.top) / img.height, 0, 1) * state.naturalH,
    };
    var vw = view();
    var s = MV.scrollFor(p, state.zoom, vw.w / 2, vw.h / 2, vw.v.offX, vw.v.offY);
    vw.scroll.scrollLeft = s.left;
    vw.scroll.scrollTop = s.top;
  }

  function wireView() {
    var scroll = $("#map-scroll");
    scroll.addEventListener("scroll", updateOverview);

    // Pinch on a trackpad, or Ctrl/Cmd + wheel, zooms at the pointer; a plain wheel scrolls as usual.
    scroll.addEventListener(
      "wheel",
      function (ev) {
        if (!ev.ctrlKey && !ev.metaKey) return;
        ev.preventDefault();
        var b = scroll.getBoundingClientRect();
        var dy = ev.deltaY * (ev.deltaMode === 1 ? 16 : ev.deltaMode === 2 ? b.height : 1); // lines, pages → px
        var f = MV.clamp(Math.exp(-dy * 0.01), 1 / ZOOM_FACTOR, ZOOM_FACTOR); // a mouse notch is one + press
        zoomTo(state.zoom * f, ev.clientX - b.left, ev.clientY - b.top);
      },
      { passive: false }
    );

    // Double-click zooms in at the spot; Shift + double-click zooms out.
    scroll.addEventListener("dblclick", function (ev) {
      if (ev.target.closest(".hotspot") || Date.now() - lastDragEnd < 500) return; // two quick pans are not a zoom
      var b = scroll.getBoundingClientRect();
      var f = ev.shiftKey ? 1 / 2 : 2;
      zoomTo(state.zoom * f, ev.clientX - b.left, ev.clientY - b.top);
    });

    // Drag with the mouse to pan (touch already scrolls the box).
    var drag = null;
    var lastDragEnd = 0;
    scroll.addEventListener("pointerdown", function (ev) {
      if (ev.pointerType !== "mouse" || ev.button !== 0 || ev.target.closest(".hotspot")) return;
      var b = scroll.getBoundingClientRect();
      if (ev.clientX - b.left >= scroll.clientWidth || ev.clientY - b.top >= scroll.clientHeight) return; // a scrollbar
      drag = { x: ev.clientX, y: ev.clientY, left: scroll.scrollLeft, top: scroll.scrollTop, moved: false };
      scroll.setPointerCapture(ev.pointerId);
      ev.preventDefault(); // no image drag or text selection to take the gesture over
    });
    scroll.addEventListener("pointermove", function (ev) {
      if (!drag) return;
      var dx = ev.clientX - drag.x;
      var dy = ev.clientY - drag.y;
      if (!drag.moved && Math.abs(dx) + Math.abs(dy) < 4) return;
      drag.moved = true;
      scroll.classList.add("dragging");
      scroll.scrollLeft = drag.left - dx;
      scroll.scrollTop = drag.top - dy;
    });
    function endDrag() {
      if (drag && drag.moved) lastDragEnd = Date.now();
      drag = null;
      scroll.classList.remove("dragging");
    }
    scroll.addEventListener("pointerup", endDrag);
    scroll.addEventListener("pointercancel", endDrag);

    var ov = $("#overview");
    var ovDrag = false;
    ov.addEventListener("pointerdown", function (ev) {
      ovDrag = true;
      ov.setPointerCapture(ev.pointerId);
      panFromOverview(ev);
      ev.preventDefault();
    });
    ov.addEventListener("pointermove", function (ev) {
      if (ovDrag) panFromOverview(ev);
    });
    ov.addEventListener("pointerup", function () {
      ovDrag = false;
    });
    ov.addEventListener("pointercancel", function () {
      ovDrag = false;
    });

    // Keep the same part of the map in view when the window changes size; stay at Fit if it was at Fit.
    window.addEventListener("resize", function () {
      if (!state.naturalW) return;
      var atFit = state.zoom <= state.fit + 1e-6;
      measureFit();
      zoomTo(atFit ? state.fit : state.zoom);
    });
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
    var res = await fetch(b + DATA_URL, { cache: "no-cache" });
    if (!res.ok) throw new Error(DATA_URL + " " + res.status);
    state.data = await res.json();
    var img = $("#schematic");
    var imagePath = (state.data.image && state.data.image.path) || IMAGE_FALLBACK;

    function onReady() {
      state.naturalW = img.naturalWidth || (state.data.image && state.data.image.width) || 0;
      state.naturalH = img.naturalHeight || (state.data.image && state.data.image.height) || 0;
      $("#overview-img").src = img.src;
      $("#map-scroll").style.aspectRatio = state.naturalW + " / " + state.naturalH; // the board's own shape
      fitAll();
      paint();
    }

    if (img) {
      img.onload = onReady;
      img.onerror = function () {
        failed(new Error("Map image failed to load: " + imagePath));
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

    $("#zoom-range").addEventListener("input", function (ev) {
      zoomTo(Number(ev.target.value) / 100);
    });
    $("#zoom-in").addEventListener("click", function () {
      zoomTo(state.zoom * ZOOM_FACTOR);
    });
    $("#zoom-out").addEventListener("click", function () {
      zoomTo(state.zoom / ZOOM_FACTOR);
    });
    $("#zoom-fit").addEventListener("click", fitAll);
    wireView();

    await load();
  }

  // Friendly error box under the page title (HARTOps.renderError) in place of "Loading layout map…".
  function failed(err) {
    var meta = $("#layout-meta");
    if (!meta) return;
    meta.textContent = "";
    var box = $("#layout-error");
    if (!box) {
      box = document.createElement("div");
      box.id = "layout-error";
      meta.parentNode.appendChild(box);
    }
    HARTOps.renderError(box, { what: "the layout map", err: err });
  }

  window.HARTLayoutExplorer = {
    reload: function () {
      return load().catch(function (err) {
        console.error(err);
        failed(err);
      });
    },
  };

  document.addEventListener("DOMContentLoaded", function () {
    Promise.resolve(HARTOps.mountChrome("layout"))
      .then(init)
      .catch(function (err) {
        console.error(err);
        failed(err);
      });
  });
})();
