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
  var LABELS = { done: "Done", ready: "Ready", part: "Partly", todo: "To do", ask: "Confirm" };

  /* A card's mark sums its checklist counts: all Done is Done; Done plus Ready only
     (paperwork ready, waiting for a signed witness) is Ready; any Done, Ready or Partly
     is Partly; all Confirm is Confirm; otherwise To do. */
  function statusOf(n, total) {
    if (!total) return "";
    if (n.done === total) return "done";
    if (n.ready && n.done + n.ready === total) return "ready";
    if (n.done || n.ready || n.part) return "part";
    if (n.ask === total) return "ask";
    return "todo";
  }

  /* Bar width: the score's "N of M" when it has one, else the share of Done and Ready items. */
  function barPct(text, n, total) {
    var m = String(text || "").match(/(\d+(?:\.\d+)?) of (\d+(?:\.\d+)?)/);
    var of = m ? parseFloat(m[2]) : 0;
    if (of) return Math.min(100, (100 * parseFloat(m[1])) / of);
    return total ? (100 * (n.done + n.ready)) / total : 0;
  }

  function certProgress(cert) {
    var n = { done: 0, ready: 0, part: 0, todo: 0, ask: 0 }, total = 0;
    if (cert) {
      cert.querySelectorAll(".ap-list .ap-mark").forEach(function (el) {
        total++;
        Object.keys(n).forEach(function (k) { if (el.classList.contains(k)) n[k]++; });
      });
    }
    var score = cert && cert.querySelector(".ap-score");
    var text = score ? score.textContent.trim() : "";
    return { status: statusOf(n, total), text: text === "\u2014" ? "" : text, pct: barPct(text, n, total) };
  }

  var RANK = { done: 4, ready: 3, part: 2, todo: 1, ask: 1 };
  function bestStatus(list) {
    return list.reduce(function (best, s) { return (RANK[s] || 0) > (RANK[best] || 0) ? s : best; }, "");
  }

  function setMark(mark, status) {
    if (!mark || !status) return;
    mark.className = "ap-mark " + status;
    mark.textContent = LABELS[status];
  }

  /* Dashboard cards copy each checklist's score, bar and mark; the summary counts Done and Ready cards. */
  function fillDashboard() {
    var earned = 0, ready = 0, byId = {};
    document.querySelectorAll("[data-ap-cert]").forEach(function (card) {
      var id = card.getAttribute("data-ap-cert");
      var p = byId[id] = certProgress(document.getElementById(id));
      var out = card.querySelector(".ap-dash-score");
      if (out) out.textContent = p.text;
      var bar = card.querySelector(".ap-dash-bar > span");
      if (bar) bar.style.width = p.pct + "%";
      card.classList.toggle("is-done", p.status === "done");
      card.classList.toggle("is-ready", p.status === "ready");
      setMark(card.querySelector(".ap-mark"), p.status);
      if (p.status === "done") earned++;
      if (p.status === "ready") ready++;
    });
    /* The "path to seven" table reads the same checklists, so it cannot disagree with the cards.
       A row that names several certificates (Prototype Models, or Structures, or Scenery) shows the furthest along. */
    document.querySelectorAll("[data-ap-path]").forEach(function (mark) {
      var ids = mark.getAttribute("data-ap-path").split(/\s+/);
      var status = bestStatus(ids.map(function (id) { return (byId[id] || certProgress(document.getElementById(id))).status; }));
      if (!status) console.warn("achievements: no checklist marks for path row", ids.join(" "));
      setMark(mark, status);
    });
    var count = document.querySelector("[data-ap-earned]");
    if (count) count.textContent = earned;
    var note = document.querySelector("[data-ap-ready]");
    var noteCount = document.querySelector("[data-ap-ready-count]");
    if (note && noteCount) {
      noteCount.textContent = ready;
      note.hidden = !ready;
    }
  }
  var api = { statusOf: statusOf, barPct: barPct, bestStatus: bestStatus };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
    return;
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
