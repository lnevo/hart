/* Keyboard helpers shared by pages: tab sets and wide tables.
 *
 * HARTA11y.tabs(list): the WAI-ARIA tabs pattern on a role="tablist" element whose
 * page already selects a tab on click. Only the selected tab is in the Tab order
 * (roving tabindex); ArrowLeft/ArrowRight (with wrap), Home and End move focus and
 * select the tab by clicking it, so the page's own click code does the switching.
 * Tabs drawn later or redrawn by the page are picked up, since the keys are read on
 * the list and the tabindex follows aria-selected. Every role="tablist" in the
 * markup is wired when the page loads; a page may also call it, which does nothing more.
 *
 * HARTA11y.scroller(wrap): a .table-wrap that scrolls sideways shows the
 * .scroll-hint just before it only while its table is wider than the box. */
(function () {
  "use strict";

  var KEYS = { ArrowRight: 1, ArrowLeft: -1, Home: "first", End: "last" };

  function tabsOf(list) {
    return Array.prototype.filter.call(list.querySelectorAll('[role="tab"]'), function (t) {
      return !t.hidden && !t.disabled;
    });
  }

  function syncTabindex(list) {
    var tabs = tabsOf(list);
    var sel = tabs.filter(function (t) { return t.getAttribute("aria-selected") === "true"; })[0] || tabs[0];
    tabs.forEach(function (t) { t.tabIndex = t === sel ? 0 : -1; });
  }

  function tabs(list) {
    if (!list || list.dataset.a11yTabs) return;
    list.dataset.a11yTabs = "1";
    list.addEventListener("keydown", function (e) {
      var step = KEYS[e.key];
      var tab = e.target.closest('[role="tab"]');
      if (!step || !tab || e.altKey || e.ctrlKey || e.metaKey) return;
      var all = tabsOf(list);
      var i = all.indexOf(tab);
      var next = step === "first" ? all[0] : step === "last" ? all[all.length - 1] : all[(i + step + all.length) % all.length];
      e.preventDefault();
      e.stopPropagation();
      if (!next || next === tab) return;
      next.focus();
      next.click();
      syncTabindex(list);
      // A page that redraws its tabs on click drops the focused button: focus the new selected tab.
      if (!list.contains(document.activeElement)) {
        var sel = list.querySelector('[role="tab"][aria-selected="true"]');
        if (sel) sel.focus();
      }
    });
    syncTabindex(list);
    new MutationObserver(function () { syncTabindex(list); })
      .observe(list, { subtree: true, childList: true, attributes: true, attributeFilter: ["aria-selected", "hidden"] });
  }

  function scroller(wrap) {
    if (!wrap || wrap.dataset.a11yScroll) return;
    wrap.dataset.a11yScroll = "1";
    var hint = wrap.previousElementSibling;
    if (!hint || !hint.classList.contains("scroll-hint")) return;
    function check() {
      // A hidden panel measures 0 wide: leave the hint as it is until the panel shows.
      if (!wrap.clientWidth) return;
      hint.hidden = wrap.scrollWidth <= wrap.clientWidth + 1;
    }
    if (window.ResizeObserver) {
      var ro = new ResizeObserver(check);
      ro.observe(wrap);
      if (wrap.firstElementChild) ro.observe(wrap.firstElementChild);
    } else {
      window.addEventListener("resize", check);
    }
    check();
  }

  window.HARTA11y = { tabs: tabs, scroller: scroller };

  // Every tab set in the page's markup gets the keys; tabs drawn into it later are covered too.
  function wireAll() {
    Array.prototype.forEach.call(document.querySelectorAll('[role="tablist"]'), tabs);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wireAll);
  else wireAll();
})();
