/* Achievement checklists (ap/): page chrome, Open all / Close all, and opening a
   closed card when the URL hash or an in-page link points at it. */
(function () {
  function openFromHash() {
    var id = decodeURIComponent(location.hash.slice(1));
    var el = id && document.getElementById(id);
    if (el && el.tagName === "DETAILS" && !el.open) {
      el.open = true;
      el.scrollIntoView();
    }
  }
  var LABELS = { done: "Done", part: "Partly", todo: "To do", ask: "Confirm" };
  /* A card's mark sums its checklist: all Done is Done, any Done or Partly is Partly,
     all Confirm is Confirm, otherwise To do. */
  function cardStatus(cert) {
    if (!cert) return "";
    var all = cert.querySelectorAll(".ap-list .ap-mark");
    var n = { done: 0, part: 0, todo: 0, ask: 0 };
    all.forEach(function (el) {
      ["done", "part", "todo", "ask"].forEach(function (k) { if (el.classList.contains(k)) n[k]++; });
    });
    if (!all.length) return "";
    if (n.done === all.length) return "done";
    if (n.done || n.part) return "part";
    if (n.ask === all.length) return "ask";
    return "todo";
  }

  /* Dashboard cards copy each certificate's score and draw its bar from "N of M". */
  function fillDashboard() {
    document.querySelectorAll("[data-ap-cert]").forEach(function (card) {
      var cert = document.getElementById(card.getAttribute("data-ap-cert"));
      var score = cert && cert.querySelector(".ap-score");
      var text = score ? score.textContent.trim() : "";
      var out = card.querySelector(".ap-dash-score");
      if (out) out.textContent = text === "\u2014" ? "" : text;
      var m = text.match(/(\d+(?:\.\d+)?) of (\d+(?:\.\d+)?)/);
      var marks = cert ? cert.querySelectorAll(".ap-list .ap-mark") : [];
      var done = cert ? cert.querySelectorAll(".ap-list .ap-mark.done").length : 0;
      var pct = m ? Math.min(100, (100 * parseFloat(m[1])) / parseFloat(m[2]))
        : marks.length ? (100 * done) / marks.length : 0;
      var bar = card.querySelector(".ap-dash-bar > span");
      if (bar) bar.style.width = pct + "%";
      card.classList.toggle("is-done", pct >= 100);
      var status = cardStatus(cert);
      var mark = card.querySelector(".ap-mark");
      if (mark && status) {
        mark.className = "ap-mark " + status;
        mark.textContent = LABELS[status];
      }
    });
  }
  window.HARTAchievements = {
    mount: function (pageId) {
      HARTOps.mountChrome(pageId).catch(function (err) {
        console.error(err);
      });
      document.querySelectorAll("[data-ap-toggle]").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var open = btn.getAttribute("data-ap-toggle") === "open";
          document.querySelectorAll(".ap-cert").forEach(function (d) { d.open = open; });
        });
      });
      fillDashboard();
      window.addEventListener("hashchange", openFromHash);
      openFromHash();
    }
  };
})();
