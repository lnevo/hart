(function () {
  function base() {
    var p = (window.location.pathname || "").replace(/\\/g, "/");
    if (
      /\/ops-portal\/(layout|roster|guides|tools|reference|gallery|briefing|industries|photos|about|sessions)\//.test(
        p
      )
    ) {
      return "../";
    }
    return "";
  }

  async function loadSite() {
    var res = await fetch(base() + "data/site.json");
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
    return (
      '<div class="site-header-inner">' +
      '<a class="brand" href="' +
      b +
      'index.html">HART<span>Operator portal · Neville Island</span></a>' +
      '<nav class="nav" aria-label="Primary">' +
      links +
      "</nav>" +
      '<a class="eng-link" href="' +
      b +
      (site.engDesk || "../index.html") +
      '">Engineering desk</a>' +
      "</div>"
    );
  }

  async function mountChrome(pageId) {
    var site = await loadSite();
    var header = document.querySelector("[data-ops-header]");
    var footer = document.querySelector("[data-ops-footer]");
    if (header) header.innerHTML = headerHtml(site, pageId);
    if (footer) {
      footer.innerHTML =
        "HART Railroad · Neville Island · built from consolidation publications, invites, and media · " +
        '<a href="' +
        base() +
        (site.engDesk || "../index.html") +
        '">Engineering desk</a>';
    }
    return site;
  }

  async function loadJson(rel) {
    var res = await fetch(base() + rel);
    return res.json();
  }

  var api = {
    base: base,
    loadSite: loadSite,
    loadJson: loadJson,
    mountChrome: mountChrome,
  };
  window.HARTOps = api;
  window.HARTOps = api;
})();
