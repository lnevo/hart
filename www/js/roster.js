(function () {
  var data = null;

  var base = HARTOps.base;
  var esc = HARTOps.esc;

  // a line block's cp lists the stations or control points it joins, ";" between (the device master)
  function places(item) {
    return (item.cp || "").split(";").filter(Boolean);
  }

  function filtered() {
    var kind = document.querySelector("#kind-filter").value;
    var cp = document.querySelector("#cp-filter").value;
    var q = (document.querySelector("#roster-search").value || "").trim().toLowerCase();
    return (data.items || []).filter(function (item) {
      if (kind !== "all" && item.kind !== kind) return false;
      if (cp !== "all" && places(item).indexOf(cp) < 0) return false;
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
          esc(item.id) +
          '"><td><span class="kind-pill ' +
          esc(item.kind) +
          '">' +
          esc(item.kind) +
          "</span></td><td>" +
          esc(item.publicName || "") +
          '</td><td class="mono">' +
          esc(item.systemName || "") +
          "</td><td>" +
          esc(places(item).join(", ") || "—") +
          '</td><td class="mono">' +
          esc(item.hardware || "—") +
          '</td><td class="mono">' +
          esc(item.mqtt || "—") +
          "</td><td>" +
          esc(item.comment || "") +
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
    var res = await fetch(base() + "data/layout-index.json", { cache: "no-cache" });
    data = await res.json();
    var cps = {};
    (data.items || []).forEach(function (it) {
      places(it).forEach(function (cp) {
        cps[cp] = true;
      });
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
    window.HARTA11y.scroller(document.querySelector("main .table-wrap"));
  }

  document.addEventListener("DOMContentLoaded", function () {
    window.HARTOps.mountChrome("roster")
      .then(init)
      .catch(function (err) {
        console.error(err);
        window.HARTOps.renderError(document.querySelector("main .table-wrap"), { what: "the device viewer", err: err });
      });
  });
})();
