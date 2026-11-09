// AI in Model Railroading pages: mount the site chrome for the page id on <body data-page>,
// and mark the contents entry for the section being read (same as the feature articles).
document.addEventListener("DOMContentLoaded", function () {
  var id = document.body.getAttribute("data-page") || "behind";
  HARTOps.mountChrome(id).catch(function (err) {
    console.error(err);
  });

  var links = Array.prototype.slice.call(document.querySelectorAll(".feature-toc a"));
  if (!("IntersectionObserver" in window) || !links.length) return;
  var byId = {};
  links.forEach(function (a) {
    var href = a.getAttribute("href") || "";
    if (href.charAt(0) === "#") byId[href.slice(1)] = a;
  });
  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting || !byId[e.target.id]) return;
      links.forEach(function (a) { a.removeAttribute("aria-current"); });
      byId[e.target.id].setAttribute("aria-current", "true");
    });
  }, { rootMargin: "-20% 0px -70% 0px" });
  Object.keys(byId).forEach(function (key) {
    var el = document.getElementById(key);
    if (el) observer.observe(el);
  });
});
