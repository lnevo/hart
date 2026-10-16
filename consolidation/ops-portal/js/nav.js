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
    var res = await fetch(base() + "data/site.json", { cache: "no-cache" });
    if (!res.ok) throw new Error("site.json " + res.status);
    return res.json();
  }

  async function loadJson(rel) {
    var res = await fetch(base() + rel, { cache: "no-cache" });
    if (!res.ok) throw new Error(rel + " " + res.status);
    return res.json();
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // The nav entry (section) a page belongs to: a section lists its page ids in "pages".
  function sectionFor(site, pageId) {
    var nav = site.nav || [];
    for (var i = 0; i < nav.length; i++) {
      var pages = nav[i].pages || [nav[i].id];
      if (pages.indexOf(pageId) !== -1) return nav[i];
    }
    return null;
  }

  function headerHtml(site, pageId) {
    var b = base();
    var section = sectionFor(site, pageId);
    var links = (site.nav || [])
      .map(function (item) {
        var cur = "";
        if (item.id === pageId) cur = ' aria-current="page"';
        else if (section && item.id === section.id) cur = ' aria-current="true"';
        var label = item.short
          ? '<span class="nav-full">' + esc(item.label) + '</span><span class="nav-short">' +
            esc(item.short) + "</span>"
          : esc(item.label);
        var cls = item.id === "home" ? ' class="nav-home"' : "";
        return '<a href="' + b + item.href + '"' + cls + cur + ">" + label + "</a>";
      })
      .join("");
    var eng = site.engDesk
      ? '<a class="eng-link" href="' + b + site.engDesk + '">Engineering desk</a>'
      : "";
    return (
      '<div class="site-header-inner">' +
      '<a class="brand" href="' +
      b +
      'index.html">HART<span>Railroad · Neville Island</span></a>' +
      '<nav class="nav" aria-label="Primary">' +
      links +
      "</nav>" +
      eng +
      "</div>"
    );
  }

  // Small "Section ›" link above a child page's title so visitors can get back to the hub.
  function mountCrumb(site, pageId) {
    var section = sectionFor(site, pageId);
    if (!section || section.id === pageId || section.id === "home") return;
    var head = document.querySelector("main .page-head");
    if (!head || head.querySelector(".crumb")) return;
    var p = document.createElement("p");
    p.className = "crumb";
    p.innerHTML = '<a href="' + base() + section.href + '">' + esc(section.label) + "</a>";
    head.insertBefore(p, head.firstChild);
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
    mountCrumb(site, pageId);
    if (site.public) {
      // Links to localhost services and the engineering workspace are dead on the public site.
      var local = document.querySelectorAll("[data-local-only]");
      for (var i = 0; i < local.length; i++) local[i].hidden = true;
    }
    if (footer) {
      var eng = site.engDesk
        ? ' · <a href="' + base() + site.engDesk + '">Engineering desk</a>'
        : "";
      footer.innerHTML = "HART Railroad · Neville Island" + eng;
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
