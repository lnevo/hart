// The parts the Photos viewers share (js/archive.js and js/gallery.js): the Grid / List / Gallery view bar and the
// view each browser remembers, the Gallery view's stage controls, the photo lightbox, the toast and the JSON POST to
// the local review server. Load it after nav.js and before either viewer. Tests: scripts/tests/photo_viewer_test.js.
(function () {
  var VIEWS = [
    { id: "grid", label: "Grid" },
    { id: "list", label: "List" },
    { id: "gallery", label: "Gallery" },
  ];
  var isView = (id) => VIEWS.some(function (v) { return v.id === id; });

  // —— Grid / List / Gallery ——
  // The view stored under key, or Grid when none is stored, the stored name is not a view, or there is no storage.
  function storedView(key) {
    try {
      var saved = localStorage.getItem(key);
      return isView(saved) ? saved : "grid";
    } catch (e) {
      return "grid"; // no storage (a private window): the page opens on Grid
    }
  }

  function storeView(key, view) {
    try {
      localStorage.setItem(key, view);
    } catch (e) {
      return; // no storage: the view lasts until the page closes
    }
  }

  function viewBarHtml(view) {
    return VIEWS.map(function (v) {
      return '<button type="button" data-view="' + v.id + '" aria-pressed="' + (v.id === view) + '">' + v.label + "</button>";
    }).join("");
  }

  // Draws the view bar into el with view pressed; a click stores the new view under key and calls onPick(view).
  function mountViewBar(el, key, view, onPick) {
    if (!isView(view)) throw new Error("photo viewer: " + JSON.stringify(view) + " is not a view");
    el.innerHTML = viewBarHtml(view);
    el.querySelectorAll("button").forEach(function (b) {
      b.addEventListener("click", function () {
        var picked = b.getAttribute("data-view");
        storeView(key, picked);
        mountViewBar(el, key, picked, onPick);
        onPick(picked);
      });
    });
  }

  // (i + d) wrapped into 0..n-1; null when there is nothing to step through.
  function wrapIndex(i, d, n) {
    return n ? (i + d + n) % n : null;
  }

  // The Gallery view drawn into grid: its ‹ › buttons call step(-1 or 1), a strip thumbnail calls pick(its index),
  // and the strip scrolls to the photo on stage.
  function bindStage(grid, step, pick) {
    grid.querySelector(".fleet-stage-nav.prev").addEventListener("click", function () { step(-1); });
    grid.querySelector(".fleet-stage-nav.next").addEventListener("click", function () { step(1); });
    grid.querySelectorAll("[data-stage]").forEach(function (b) {
      b.addEventListener("click", function () { pick(Number(b.getAttribute("data-stage"))); });
    });
    var cur = grid.querySelector('.fleet-strip [aria-current="true"]');
    if (cur && cur.scrollIntoView) cur.scrollIntoView({ block: "nearest", inline: "center" });
  }

  var isField = (t) => t === "INPUT" || t === "TEXTAREA" || t === "SELECT";

  // —— The lightbox ——
  // A modal dialog like the crew map viewer: focus on Close, Tab kept inside, Esc closes, arrows step (not while
  // typing in a field), and focus goes back to whatever opened it. o: className, titleId (the heading that names the
  // dialog), card (the HTML beside the ‹ › buttons), at(i) (item i of what the page shows now), count() (how many
  // there are) and paint(it, lb) (fills the card for item it).
  function makeLightbox(o) {
    ["className", "titleId", "card"].forEach(function (k) {
      if (typeof o[k] !== "string" || !o[k]) throw new Error("photo viewer: the lightbox needs " + k);
    });
    ["at", "count", "paint"].forEach(function (k) {
      if (typeof o[k] !== "function") throw new Error("photo viewer: the lightbox needs a function " + k);
    });
    var lb = document.createElement("div");
    lb.className = o.className;
    lb.setAttribute("role", "dialog");
    lb.setAttribute("aria-modal", "true");
    lb.setAttribute("aria-labelledby", o.titleId);
    lb.innerHTML =
      '<button type="button" class="lightbox-close" aria-label="Close">Close</button>' +
      '<button type="button" class="lightbox-nav prev" aria-label="Previous">‹</button>' +
      '<button type="button" class="lightbox-nav next" aria-label="Next">›</button>' +
      '<div class="lightbox-card">' + o.card + "</div>";
    document.body.appendChild(lb);
    var index = 0;
    var returnTo = null;

    function paint() {
      var it = o.at(index);
      if (it) o.paint(it, lb);
    }

    function isOpen() {
      return lb.classList.contains("open");
    }

    function open(i) {
      index = i;
      paint();
      if (!isOpen()) returnTo = document.activeElement;
      lb.classList.add("open");
      lb.querySelector(".lightbox-close").focus();
    }

    function close() {
      lb.classList.remove("open");
      // The opener may have been redrawn (a save re-renders the grid); then focus stays put.
      if (returnTo && returnTo.focus && document.contains(returnTo)) returnTo.focus();
      returnTo = null;
    }

    function step(d) {
      var next = wrapIndex(index, d, o.count());
      if (next === null) return;
      index = next;
      paint();
    }

    // Show item i again after a save, or close when the save moved it out of view.
    function show(i) {
      index = i;
      if (o.at(index)) paint();
      else close();
    }

    lb.querySelector(".lightbox-close").addEventListener("click", close);
    lb.addEventListener("click", function (e) {
      if (e.target === lb) close();
    });
    lb.querySelector(".prev").addEventListener("click", function (e) {
      e.stopPropagation();
      step(-1);
    });
    lb.querySelector(".next").addEventListener("click", function (e) {
      e.stopPropagation();
      step(1);
    });
    document.addEventListener("keydown", function (e) {
      if (!isOpen()) return;
      HARTOps.trapTab(lb, e);
      if (isField(e.target && e.target.tagName)) return;
      if (e.key === "Escape") close();
      if (e.key === "ArrowLeft") step(-1);
      if (e.key === "ArrowRight") step(1);
    });
    return { el: lb, open: open, close: close, step: step, show: show, isOpen: isOpen };
  }

  // —— The toast ——
  // A function (message, bad) that shows message in el for a moment, in the warning colour when bad.
  function makeToast(el) {
    if (!el) throw new Error("photo viewer: the page has no toast element");
    var timer = null;
    return function (msg, bad) {
      el.textContent = msg;
      el.classList.toggle("bad", !!bad);
      el.classList.add("show");
      clearTimeout(timer);
      timer = setTimeout(function () {
        el.classList.remove("show");
      }, 2600);
    };
  }

  // —— The review server ——
  // POST body to url as JSON; the answer, or an Error with the server's own message (the HTTP status when its
  // answer is not JSON).
  async function postJson(url, body) {
    var res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    var payload = await res.json().catch(function () { return {}; });
    if (!res.ok) throw new Error(payload.error || "HTTP " + res.status);
    return payload;
  }

  window.HARTViewer = {
    isView: isView, storedView: storedView, storeView: storeView, viewBarHtml: viewBarHtml, mountViewBar: mountViewBar,
    wrapIndex: wrapIndex, bindStage: bindStage, isField: isField, makeLightbox: makeLightbox, makeToast: makeToast,
    postJson: postJson,
  };
})();
