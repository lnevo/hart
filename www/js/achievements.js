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
      window.addEventListener("hashchange", openFromHash);
      openFromHash();
    }
  };
})();
