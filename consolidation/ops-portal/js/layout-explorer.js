(function () {
  var DATA_URL = "data/layout-index-cats.json";
  var IMAGE_FALLBACK = "assets/layout/HART_cats_digicon.png";

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
    renderList();
  }

  function renderList() {
    var list = $("#device-list");
    if (!list || !state.data) return;
    var rows = (state.data.items || []).filter(matches);
    rows.sort(function (a, b) {
      var ka = (a.kind + " " + (a.publicName || a.systemName || "")).toLowerCase();
      var kb = (b.kind + " " + (b.publicName || b.systemName || "")).toLowerCase();
      return ka < kb ? -1 : ka > kb ? 1 : 0;
    });
    list.innerHTML = rows
      .map(function (item) {
        var active = item.id === state.activeId ? " aria-current=\"true\"" : "";
        return (
          "<button type=\"button\" class=\"device-list-item\" data-id=\"" +
          escapeHtml(item.id) +
          "\"" +
          active +
          "><span class=\"kind\">" +
          escapeHtml(item.kind) +
          "</span><span class=\"name\">" +
          escapeHtml(item.publicName || item.systemName) +
          "</span></button>"
        );
      })
      .join("");
    list.querySelectorAll("button").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-id");
        var item = (state.data.items || []).find(function (it) {
          return it.id === id;
        });
        if (!item) return;
        state.activeId = id;
        paint();
        showDetail(item);
        var stage = $("#map-stage");
        var hot = stage && stage.querySelector('.hotspot.active');
        if (hot && hot.scrollIntoView) {
          hot.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
        }
      });
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
      " masts";
  }

  async function load() {
    state.activeId = null;
    var b = base();
    var res = await fetch(b + DATA_URL);
    if (!res.ok) throw new Error(DATA_URL + " " + res.status);
    state.data = await res.json();
    var img = $("#schematic");
    var imagePath = (state.data.image && state.data.image.path) || IMAGE_FALLBACK;
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
