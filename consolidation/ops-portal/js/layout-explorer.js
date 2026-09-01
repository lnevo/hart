(function () {
  var VIEWS = {
    cats: "data/layout-index-cats.json",
    le: "data/layout-index.json",
  };

  var state = {
    data: null,
    view: "cats",
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
      el.innerHTML =
        '<p class="empty">Click a switch plant on the Digicon board, or a switch/signal on the LE schematic.</p>';
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

  function updateMeta() {
    var c = (state.data && state.data.counts) || {};
    var meta = $("#layout-meta");
    if (!meta) return;
    var viewLabel = state.view === "cats" ? "Digicon Master plants" : "LE schematic devices";
    meta.textContent =
      viewLabel +
      " · " +
      (c.mapped || 0) +
      " mapped · " +
      (c.turnout || 0) +
      " turnout · " +
      (c.signal || 0) +
      " signal";
  }

  async function loadView(view) {
    state.view = view in VIEWS ? view : "cats";
    state.activeId = null;
    var b = base();
    var url = b + VIEWS[state.view];
    var res = await fetch(url);
    if (!res.ok) throw new Error(VIEWS[state.view] + " " + res.status);
    state.data = await res.json();
    var img = $("#schematic");
    var imagePath =
      (state.data.image && state.data.image.path) ||
      (state.view === "cats"
        ? "assets/layout/HART_cats_digicon.png"
        : "assets/layout/HART_le_schematic.png");
    if (img) {
      img.onload = paint;
      img.onerror = function () {
        var meta = $("#layout-meta");
        if (meta) meta.textContent = "Map image failed to load: " + imagePath;
      };
      img.src = b + imagePath;
      if (img.complete) paint();
    }
    updateMeta();
    showDetail(null);
    paint();
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
    await loadView("cats");
  }

  window.HARTLayoutExplorer = {
    setView: function (view) {
      return loadView(view).catch(function (err) {
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
    // layout/index.html may already mount chrome; still safe to call.
    Promise.resolve(ops.mountChrome("layout"))
      .then(init)
      .catch(function (err) {
        console.error(err);
        var meta = $("#layout-meta");
        if (meta) meta.textContent = "Layout failed to load — " + err.message;
      });
  });
})();
