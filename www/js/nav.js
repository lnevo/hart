(function () {
  function base() {
    var scripts = document.getElementsByTagName("script");
    for (var i = 0; i < scripts.length; i++) {
      var attr = scripts[i].getAttribute("src") || "";
      var m = attr.match(/^((?:\.\.\/)*|\/)js\/nav\.js(?:\?.*)?$/);
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

  // The one HTML escaper for every page and script (text and attribute values).
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

  // Search button and its panel; js/search.js fills the results when the panel first opens.
  // The build marks every page with <meta name="hart-search"> when it writes search-index.json, so
  // pages served from the source tree (no index) show no search button.
  function searchHtml() {
    if (!document.querySelector('meta[name="hart-search"]')) return "";
    return (
      '<div class="site-search">' +
      '<button type="button" class="search-toggle" aria-expanded="false" aria-controls="site-search-panel" aria-label="Search">' +
      '<svg class="nav-icon" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false">' +
      '<circle cx="10.5" cy="10.5" r="5.5"/><path d="M15 15l5 5"/></svg></button>' +
      '<div class="search-panel" id="site-search-panel" hidden>' +
      '<input type="text" class="search-input" role="combobox" aria-label="Search the site" ' +
      'aria-expanded="false" aria-controls="site-search-results" aria-autocomplete="list" ' +
      'autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Search the site">' +
      '<p class="search-hint small muted">Type to search pages. Press / anywhere to start.</p>' +
      '<p class="search-empty small" hidden></p>' +
      '<ul class="search-results" id="site-search-results" role="listbox" aria-label="Search results"></ul>' +
      '<button type="button" class="search-more" hidden></button>' +
      '<div class="search-status" role="status" aria-live="polite"></div>' +
      "</div></div>"
    );
  }

  function headerHtml(site, pageId) {
    var b = base();
    var section = sectionFor(site, pageId);
    var links = (site.nav || [])
      .map(function (item) {
        var cur = "";
        if (item.id === pageId) cur = ' aria-current="page"';
        else if (section && item.id === section.id) cur = ' aria-current="true"';
        var label = esc(item.label);
        return '<a href="' + b + item.href + '"' + cur + ">" + label + "</a>";
      })
      .join("");
    // The engineering desk link rides at the end of the menu (empty on the public site).
    var eng = site.engDesk
      ? '<a class="eng-link" href="' + b + site.engDesk + '">Engineering desk</a>'
      : "";
    return (
      '<a class="skip-link" href="#main">Skip to content</a>' +
      '<div class="site-header-inner">' +
      '<a class="brand" href="' +
      b +
      'index.html">HART<span>Railroad · Neville Island</span></a>' +
      searchHtml() +
      '<nav class="nav" aria-label="Primary">' +
      '<button type="button" class="nav-toggle" aria-expanded="false" aria-controls="site-menu" aria-label="Menu">' +
        '<svg class="nav-icon" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false">' +
        '<path class="nav-icon-bars" d="M4 7h16M4 12h16M4 17h16"/>' +
        '<path class="nav-icon-close" d="M8 8l8 8M16 8l-8 8"/>' +
        '</svg></button>' +
      '<div class="nav-panel" id="site-menu" hidden>' +
      links +
      eng +
      "</div></nav></div>"
    );
  }

  // One drop-down menu at every width. Closes on Escape (focus back to the button), on a click
  // outside, on choosing a link, and when focus Tabs out of the menu.
  function mountMenu(header) {
    var btn = header.querySelector(".nav-toggle");
    var panel = header.querySelector(".nav-panel");
    if (!btn || !panel) return;
    function setOpen(open) {
      panel.hidden = !open;
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    }
    btn.addEventListener("click", function () {
      setOpen(panel.hidden);
    });
    panel.addEventListener("click", function (e) {
      if (e.target.closest && e.target.closest("a")) setOpen(false);
    });
    document.addEventListener("click", function (e) {
      if (!panel.hidden && !btn.parentNode.contains(e.target)) setOpen(false);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !panel.hidden) {
        setOpen(false);
        btn.focus();
      }
    });
    btn.parentNode.addEventListener("focusout", function (e) {
      if (!panel.hidden && e.relatedTarget && !btn.parentNode.contains(e.relatedTarget)) setOpen(false);
    });
  }

  // Search drop-down. Closes like the menu: Escape (focus back to the button) and a click outside.
  // js/search.js is fetched on first open, and "/" opens the panel when no field has focus.
  var searchLoad = null;
  function mountSearch(header) {
    var btn = header.querySelector(".search-toggle");
    var wrap = header.querySelector(".site-search");
    var panel = header.querySelector(".search-panel");
    var input = header.querySelector(".search-input");
    var menuBtn = header.querySelector(".nav-toggle");
    var menu = header.querySelector(".nav-panel");
    if (!btn || !panel || !input) return;
    function load() {
      if (searchLoad) return;
      searchLoad = new Promise(function (resolve, reject) {
        if (window.HARTSearch && window.HARTSearch.attach) return resolve();
        var s = document.createElement("script");
        s.src = base() + "js/search.js";
        s.onload = resolve;
        s.onerror = reject;
        document.head.appendChild(s);
      }).then(
        function () {
          window.HARTSearch.attach(panel, base());
        },
        function () {
          console.warn("Search unavailable: js/search.js did not load");
          input.disabled = true;
          panel.querySelector(".search-hint").textContent = "Search unavailable";
        }
      );
    }
    function setOpen(open) {
      panel.hidden = !open;
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      if (!open) return;
      // One drop-down at a time.
      if (menu && !menu.hidden) {
        menu.hidden = true;
        menuBtn.setAttribute("aria-expanded", "false");
      }
      load();
      input.focus();
    }
    btn.addEventListener("click", function () {
      setOpen(panel.hidden);
    });
    document.addEventListener("click", function (e) {
      if (!panel.hidden && !wrap.contains(e.target)) setOpen(false);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !panel.hidden) {
        setOpen(false);
        btn.focus();
        return;
      }
      if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
      var t = e.target;
      var tag = t && t.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (t && t.isContentEditable)) return;
      e.preventDefault();
      setOpen(true);
    });
    wrap.addEventListener("focusout", function (e) {
      if (!panel.hidden && e.relatedTarget && !wrap.contains(e.relatedTarget)) setOpen(false);
    });
  }

  // Small "Section ›" trail above a child page's title so visitors can get back to the hub.
  // site.json "parents" adds a hub inside the section, e.g. guide → "Operations › Guides".
  function mountCrumb(site, pageId) {
    var section = sectionFor(site, pageId);
    if (!section || section.id === pageId || section.id === "home") return;
    var head = document.querySelector("main .page-head, main .feature-head");
    if (!head || head.querySelector(".crumb")) return;
    // A section may name a shorter crumb than its menu label (site.json "crumb").
    var top = { href: section.href, label: section.crumb || section.label };
    var trail = [top].concat((site.parents || {})[pageId] || []);
    var nav = document.createElement("nav");
    nav.className = "crumb";
    nav.setAttribute("aria-label", "Breadcrumb");
    nav.innerHTML =
      "<ol>" +
      trail
        .map(function (t) {
          return '<li><a href="' + base() + esc(t.href) + '">' + esc(t.label) + "</a></li>";
        })
        .join("") +
      "</ol>";
    head.insertBefore(nav, head.firstChild);
  }

  // Target for the skip link: the page's <main>, focusable so keyboard users land in it.
  function mountSkipTarget() {
    var main = document.querySelector("main");
    if (!main) return;
    if (!main.id) main.id = "main";
    else {
      var skip = document.querySelector(".skip-link");
      if (skip) skip.setAttribute("href", "#" + main.id);
    }
    if (!main.hasAttribute("tabindex")) main.setAttribute("tabindex", "-1");
  }

  function headerEl() {
    return document.querySelector("[data-ops-header]");
  }

  function footerEl() {
    return document.querySelector("[data-ops-footer]");
  }

  // Fill [data-voice] with a random P&OV saying, never the one shown on the last visit.
  // The quote already in the HTML stays as the fallback if voices.json can't load.
  async function mountVoice() {
    var el = document.querySelector("[data-voice]");
    if (!el) return;
    var quotes = ((await loadJson("data/voices.json")).quotes || []).filter(function (q) {
      return q && q.quote;
    });
    if (!quotes.length) return;
    var last = -1;
    try {
      last = parseInt(localStorage.getItem("hart.voice") || "-1", 10);
    } catch (e) {}
    var i = Math.floor(Math.random() * quotes.length);
    if (quotes.length > 1 && i === last) i = (i + 1 + Math.floor(Math.random() * (quotes.length - 1))) % quotes.length;
    try {
      localStorage.setItem("hart.voice", String(i));
    } catch (e) {}
    var q = quotes[i];
    // Credit the original Tumblr post.
    var post = q.url || "https://www.tumblr.com/pittsburghohiovalleyrailroad";
    el.innerHTML =
      '<a class="voice-quote" style="color:inherit;text-decoration:none" href="' + esc(post) + '">“' + esc(q.quote) + "”</a>" +
      "<cite>" + esc(q.who) + ' · <a href="' + esc(post) + '">Original post on Tumblr</a></cite>';
  }

  // "Follow along" links in the footer. A channel with an empty URL in site.json is left out.
  function channelsHtml(site) {
    var ch = site.channels || {};
    var links = [
      ["youtube", "YouTube"],
      ["tiktok", "TikTok"],
    ]
      .filter(function (c) {
        return ch[c[0]];
      })
      .map(function (c) {
        return '<a href="' + esc(ch[c[0]]) + '">' + c[1] + "</a>";
      });
    return links.length ? " · Follow along: " + links.join(" · ") : "";
  }

  // True when the page came from a developer's own machine (localhost or file://), where the
  // "serve it over HTTP" hint helps. Everyone else gets the visitor text.
  function isLocal() {
    var loc = window.location;
    if (loc.protocol === "file:") return true;
    return /^(localhost|127\.0\.0\.1|\[::1\])$/.test(loc.hostname || "");
  }

  var lastSite = null;

  // Friendly "couldn't load" box in place of el's contents, with a Reload button.
  // opts: what ("this page"), links ([{href, label}], relative to the portal root), err, site.
  function renderError(el, opts) {
    if (!el) return;
    opts = opts || {};
    var site = opts.site || lastSite || {};
    var visitor = site.public || !isLocal();
    var what = opts.what || "this page";
    var html =
      '<div class="load-error" role="alert"><p class="load-error-title">Couldn\u2019t load ' + esc(what) + ".</p>" +
      "<p>Check your connection and try again. If it keeps happening, the page may be updating; give it a minute.</p>";
    var links = (opts.links || [])
      .map(function (l) {
        var href = /^https?:/i.test(l.href) ? l.href : base() + l.href;
        return '<a href="' + esc(href) + '">' + esc(l.label) + "</a>";
      })
      .join(" · ");
    if (links) html += '<p class="small">Meanwhile: ' + links + "</p>";
    html += '<p><button type="button" class="btn btn-ink" data-reload>Reload</button></p>';
    if (!visitor) {
      html +=
        '<p class="small muted">Developer: serve the portal over HTTP (scripts/serve_portal.sh), not file://.' +
        (opts.err && opts.err.message ? " " + esc(opts.err.message) : "") + "</p>";
    }
    el.innerHTML = html + "</div>";
    var btn = el.querySelector("[data-reload]");
    if (btn) btn.addEventListener("click", function () {
      window.location.reload();
    });
  }

  // Keep Tab inside an open modal dialog (photo lightboxes, map viewer): from the last control
  // it wraps to the first, and Shift+Tab from the first wraps to the last.
  function trapTab(dialog, e) {
    if (e.key !== "Tab") return;
    var f = Array.prototype.filter.call(
      dialog.querySelectorAll('a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])'),
      function (x) {
        return x.getClientRects().length > 0;
      }
    );
    if (!f.length) return e.preventDefault();
    var first = f[0];
    var last = f[f.length - 1];
    var inside = dialog.contains(document.activeElement);
    if (e.shiftKey && (!inside || document.activeElement === first)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && (!inside || document.activeElement === last)) {
      e.preventDefault();
      first.focus();
    }
  }

  // Brand-only header and footer when site.json itself won't load, so the page isn't blank.
  function fallbackSite() {
    return { nav: [{ id: "home", href: "index.html", label: "Home", pages: ["home"] }], public: !isLocal(), fallback: true };
  }

  async function mountChrome(pageId) {
    var site;
    try {
      site = await loadSite();
    } catch (err) {
      console.error(err);
      site = fallbackSite();
    }
    lastSite = site;
    var header = headerEl();
    var footer = footerEl();
    if (header) {
      header.innerHTML = headerHtml(site, pageId);
      mountMenu(header);
      mountSearch(header);
    }
    mountSkipTarget();
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
      // About is here too, as a quiet second route to it.
      var about = (site.nav || []).filter(function (n) {
        return n.id === "about";
      })[0];
      var aboutLink = about ? ' · <a href="' + base() + about.href + '">About</a>' : "";
      footer.innerHTML = "HART Railroad · Neville Island" + aboutLink + channelsHtml(site) + eng;
    }
    mountVoice().catch(function (err) {
      console.error(err);
    });
    return site;
  }

  var api = {
    base: base,
    esc: esc,
    loadSite: loadSite,
    loadJson: loadJson,
    mountChrome: mountChrome,
    renderError: renderError,
    isLocal: isLocal,
    trapTab: trapTab,
  };
  window.HARTOps = api;
})();
