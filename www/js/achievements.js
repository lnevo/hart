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
  var LABELS = { done: "Done", wait: "Witness", part: "Partly", todo: "To do", ask: "Confirm" };

  /* A card's mark sums its checklist: all Done is Done, Done plus Witness only (paperwork
     ready, waiting for a signed witness) is Witness, any Done or Partly is Partly,
     all Confirm is Confirm, otherwise To do. The bar uses the score's "N of M" when it
     has one, else the share of Done items. */
  function certProgress(cert) {
    var n = { done: 0, wait: 0, part: 0, todo: 0, ask: 0 }, total = 0;
    if (cert) {
      cert.querySelectorAll(".ap-list .ap-mark").forEach(function (el) {
        total++;
        Object.keys(n).forEach(function (k) { if (el.classList.contains(k)) n[k]++; });
      });
    }
    var status = !total ? "" : n.done === total ? "done"
      : n.wait && n.done + n.wait === total ? "wait" : n.done || n.part ? "part"
      : n.ask === total ? "ask" : "todo";
    var score = cert && cert.querySelector(".ap-score");
    var text = score ? score.textContent.trim() : "";
    var m = text.match(/(\d+(?:\.\d+)?) of (\d+(?:\.\d+)?)/);
    var of = m ? parseFloat(m[2]) : 0;
    var pct = of ? Math.min(100, (100 * parseFloat(m[1])) / of) : total ? (100 * n.done) / total : 0;
    return { status: status, text: text === "\u2014" ? "" : text, pct: pct };
  }

  /* Dashboard cards copy each checklist's score, bar and mark; the summary counts Done cards. */
  function fillDashboard() {
    var earned = 0, waiting = 0;
    document.querySelectorAll("[data-ap-cert]").forEach(function (card) {
      var p = certProgress(document.getElementById(card.getAttribute("data-ap-cert")));
      var out = card.querySelector(".ap-dash-score");
      if (out) out.textContent = p.text;
      var bar = card.querySelector(".ap-dash-bar > span");
      if (bar) bar.style.width = p.pct + "%";
      card.classList.toggle("is-done", p.status === "done");
      card.classList.toggle("is-wait", p.status === "wait");
      var mark = card.querySelector(".ap-mark");
      if (mark && p.status) {
        mark.className = "ap-mark " + p.status;
        mark.textContent = LABELS[p.status];
      }
      if (p.status === "done") earned++;
      if (p.status === "wait") waiting++;
    });
    var count = document.querySelector("[data-ap-earned]");
    if (count) count.textContent = earned;
    var note = document.querySelector("[data-ap-waiting]");
    var noteCount = document.querySelector("[data-ap-waiting-count]");
    if (note && noteCount) {
      noteCount.textContent = waiting;
      note.hidden = !waiting;
    }
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
