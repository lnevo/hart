(function () {
  function base() {
    var scripts = document.getElementsByTagName("script");
    for (var i = 0; i < scripts.length; i++) {
      var attr = scripts[i].getAttribute("src") || "";
      var m = attr.match(/^((?:\.\.\/)*)js\/nav\.js(?:\?.*)?$/);
      if (m) return m[1];
    }
    var p = (window.location.pathname || "").replace(/\\/g, "/");
    var m2 = p.match(/\/ops-portal\/(.*)$/);
    if (!m2) return "";
    var rest = m2[1];
    if (rest.endsWith("/")) {
      rest = rest.slice(0, -1);
    } else {
      rest = rest.replace(/\/[^/]+$/, "");
    }
    if (!rest) return "";
    var depth = rest.split("/").filter(Boolean).length;
    var out = "";
    for (var j = 0; j < depth; j++) out += "../";
    return out;
  }

  async function loadSite() {
    var res = await fetch(base() + "data/site.json");
    if (!res.ok) throw new Error("site.json " + res.status);
    return res.json();
  }

  async function loadJson(rel) {
    var res = await fetch(base() + rel);
    if (!res.ok) throw new Error(rel + " " + res.status);
    return res.json();
  }

  function headerHtml(site, pageId) {
    var b = base();
    var links = (site.nav || [])
      .map(function (item) {
        var cur = item.id === pageId ? ' aria-current="page"' : "";
        return '<a href="' + b + item.href + '"' + cur + ">" + item.label + "</a>";
      })
      .join("");
    var eng = site.engDesk
      ? '<a class="eng-link" href="' + b + site.engDesk + '">Engineering desk</a>'
      : "";
    return (
      '<div class="site-header-inner">' +
      '<a class="brand" href="' +
      b +
      'index.html">HART<span>Operator portal · Neville Island</span></a>' +
      '<nav class="nav" aria-label="Primary">' +
      links +
      "</nav>" +
      eng +
      "</div>"
    );
  }

  function headerEl() {
    return document.querySelector("[data-ops-header]");
  }

  function footerEl() {
    return document.querySelector("[data-ops-footer]");
  }

  async function mountChrome(pageId) {
    var site = await loadSite();
    var header = headerEl();
    var footer = footerEl();
    if (header) header.innerHTML = headerHtml(site, pageId);
    if (footer) {
      var eng = site.engDesk
        ? '<a href="' + base() + site.engDesk + '">Engineering desk</a>'
        : "Neville Island";
      footer.innerHTML = "HART Railroad · Neville Island · " + eng;
    }
    return site;
  }

  var api = {
    base: base,
    loadSite: loadSite,
    loadJson: loadJson,
    mountChrome: mountChrome,
  };
  window.HARTOps = api;
})();
