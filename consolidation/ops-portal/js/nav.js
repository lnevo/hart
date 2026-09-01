(function () {
  function base() {
    var p = (window.location.pathname || "").replace(/\\/g, "/");
    if (
      /\/ops-portal\/(layout|roster|guides|tools|reference|gallery|briefing|industries|photos|fleet|articles|docs|about)\//.test(
        p
      )
    ) {
      return "../";
    }
    return "";
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

  function headerEl() {
    return (
      document.querySelector("[data-ops-header]") ||
      document.querySelector("[data-ops-header]")
    );
  }

  function footerEl() {
    return (
      document.querySelector("[data-ops-footer]") ||
      document.querySelector("[data-ops-footer]")
    );
  }

  async function mountChrome(pageId) {
    var site = await loadSite();
    var header = headerEl();
    var footer = footerEl();
    if (header) header.innerHTML = headerHtml(site, pageId);
    if (footer) {
      footer.innerHTML =
        "HART Railroad · Neville Island · " +
        '<a href="' +
        base() +
        (site.engDesk || "../index.html") +
        '">Engineering desk</a>';
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
  // Back-compat for older page scripts
  window.HARTOps = api;
})();
