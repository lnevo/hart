(function () {
  var data = null;

  function base() {
    return window.HARTOps ? window.HARTOps.base() : "../";
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function filtered() {
    var kind = document.querySelector("#kind-filter").value;
    var cp = document.querySelector("#cp-filter").value;
    var q = (document.querySelector("#roster-search").value || "").trim().toLowerCase();
    return (data.items || []).filter(function (item) {
      if (kind !== "all" && item.kind !== kind) return false;
      if (cp !== "all" && (item.cp || "") !== cp) return false;
      if (!q) return true;
      return [item.publicName, item.systemName, item.hardware, item.mqtt, item.comment, item.cp]
        .join(" ")
        .toLowerCase()
        .indexOf(q) >= 0;
    });
  }

  function render() {
    var list = filtered();
    document.querySelector("#roster-count").textContent = list.length + " shown";
    document.querySelector("#roster-body").innerHTML = list
      .map(function (item) {
        return (
          '<tr id="' +
          escapeHtml(item.id) +
          '"><td><span class="kind-pill ' +
          escapeHtml(item.kind) +
          '">' +
          escapeHtml(item.kind) +
          "</span></td><td>" +
          escapeHtml(item.publicName || "") +
          '</td><td class="mono">' +
          escapeHtml(item.systemName || "") +
          "</td><td>" +
          escapeHtml(item.cp || "—") +
          '</td><td class="mono">' +
          escapeHtml(item.hardware || "—") +
          '</td><td class="mono">' +
          escapeHtml(item.mqtt || "—") +
          "</td><td>" +
          escapeHtml(item.comment || "") +
          "</td></tr>"
        );
      })
      .join("");
    if (location.hash) {
      var el = document.getElementById(decodeURIComponent(location.hash.slice(1)));
      if (el) el.scrollIntoView({ block: "center" });
    }
  }

  async function init() {
    var res = await fetch(base() + "data/layout-index.json");
    data = await res.json();
    var cps = {};
    (data.items || []).forEach(function (it) {
      if (it.cp) cps[it.cp] = true;
    });
    var cpSel = document.querySelector("#cp-filter");
    Object.keys(cps)
      .sort()
      .forEach(function (cp) {
        var opt = document.createElement("option");
        opt.value = cp;
        opt.textContent = cp;
        cpSel.appendChild(opt);
      });
    ["#kind-filter", "#cp-filter", "#roster-search"].forEach(function (sel) {
      var el = document.querySelector(sel);
      el.addEventListener("input", render);
      el.addEventListener("change", render);
    });
    render();
  }

  document.addEventListener("DOMContentLoaded", function () {
    window.HARTOps.mountChrome("roster").then(init);
  });
})();
