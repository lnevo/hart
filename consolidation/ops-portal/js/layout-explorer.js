(function () {
  var state = {
    data: null,
    kind: { turnout: true, signal: true },
    q: "",
    activeId: null,
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
      el.innerHTML = '<p class="empty">Click a switch or signal on the schematic.</p>';
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
      btn.addEventListener("click", function () {
        state.activeId = item.id;
        paint();
        showDetail(item);
      });
      stage.appendChild(btn);
    });
  }

  async function init() {
    var b = base();
    var res = await fetch(b + "data/layout-index.json");
    if (!res.ok) throw new Error("layout-index.json " + res.status);
    state.data = await res.json();
    var img = $("#schematic");
    var imagePath =
      (state.data.image && state.data.image.path) ||
      "assets/layout/HART_le_schematic.png";
    if (img) {
      img.src = b + imagePath;
      img.onload = paint;
      img.onerror = function () {
        var meta = $("#layout-meta");
        if (meta) meta.textContent = "Schematic image failed to load: " + imagePath;
      };
    }
    var c = state.data.counts || {};
    var meta = $("#layout-meta");
    if (meta) {
      meta.textContent =
        (c.mapped || 0) +
        " mapped · " +
        (c.turnout || 0) +
        " turnout rows · " +
        (c.signal || 0) +
        " signal rows";
    }
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
    showDetail(null);
    paint();
  }

  document.addEventListener("DOMContentLoaded", function () {
    var ops = api();
    if (!ops) {
      console.error("HARTOps nav.js did not load");
      return;
    }
    ops.mountChrome("layout").then(init).catch(function (err) {
      console.error(err);
      var meta = $("#layout-meta");
      if (meta) meta.textContent = "Layout failed to load — " + err.message;
    });
  });
})();
