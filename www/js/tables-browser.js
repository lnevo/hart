/* Tables browser for behind/tables-file.html: tabs or a dropdown, a text filter, and rows
   shown in pages of 100 so the 746 transits stay quick. Data: data/tables-browser.json. */
(function () {
  var PAGE = 100;
  var esc = HARTOps.esc;
  var data = null;
  var cur = null;   // current table
  var shown = PAGE;
  var q = "";
  var cache = {};   // table id -> lowercased row text

  function $(id) { return document.getElementById(id); }

  function rowsNow() {
    var t = cur;
    if (!q) return t.rows;
    var hay = cache[t.id] || (cache[t.id] = t.rows.map(function (r) { return r.join(" \u0001 ").toLowerCase(); }));
    return t.rows.filter(function (r, i) { return hay[i].indexOf(q) >= 0; });
  }

  function isNum(v) { return typeof v === "number"; }

  function render(resetPage) {
    if (resetPage) shown = PAGE;
    var list = rowsNow();
    var head = "<tr>" + cur.cols.map(function (c, i) {
      return "<th" + (isNum(cur.rows[0] && cur.rows[0][i]) ? ' class="num"' : "") + ">" + esc(c.label) + "</th>";
    }).join("") + "</tr>";
    $("tb-table").tHead.innerHTML = head;
    $("tb-table").tBodies[0].innerHTML = list.slice(0, shown).map(function (r) {
      return "<tr>" + r.map(function (v, i) {
        var k = cur.cols[i].k;
        var cls = k === "note" ? "note" : isNum(v) ? "num" : (k === "sys" || k === "sens" || k === "occ" || k === "ctl" || k === "src" || k === "dst" ? "mono" : (k === "user" ? "user" : ""));
        return "<td" + (cls ? ' class="' + cls + '"' : "") + ">" + esc(String(v === "" ? "—" : v)) + "</td>";
      }).join("") + "</tr>";
    }).join("") || '<tr><td colspan="' + cur.cols.length + '">No rows match.</td></tr>';
    $("tb-count").textContent = "Showing " + list.length + " of " + cur.rows.length;
    var more = $("tb-more");
    var left = list.length - shown;
    more.hidden = left <= 0;
    more.textContent = "Show " + Math.min(PAGE, left) + " more (" + left + " not shown yet)";
  }

  function pick(id) {
    cur = data.tables.filter(function (t) { return t.id === id; })[0];
    $("tb-pick").value = id;
    Array.prototype.forEach.call($("tb-tabs").children, function (b) {
      b.setAttribute("aria-selected", b.dataset.id === id ? "true" : "false");
    });
    $("tb-wrap").scrollTop = 0;
    render(true);
  }

  function init() {
    return fetch(HARTOps.base() + "data/tables-browser.json", { cache: "no-cache" })
      .then(function (res) { if (!res.ok) throw new Error("HTTP " + res.status); return res.json(); })
      .then(function (d) {
        data = d;
        $("tb-tabs").innerHTML = d.tables.map(function (t) {
          return '<button type="button" role="tab" data-id="' + esc(t.id) + '">' + esc(t.label) + "</button>";
        }).join("");
        $("tb-pick").innerHTML = d.tables.map(function (t) {
          return '<option value="' + esc(t.id) + '">' + esc(t.label) + " (" + t.rows.length + ")</option>";
        }).join("");
        $("tb-tabs").addEventListener("click", function (e) {
          var b = e.target.closest("button");
          if (b) pick(b.dataset.id);
        });
        $("tb-pick").addEventListener("change", function () { pick(this.value); });
        $("tb-q").addEventListener("input", function () { q = this.value.trim().toLowerCase(); render(true); });
        $("tb-more").addEventListener("click", function () { shown += PAGE; render(false); });
        pick(d.tables[0].id);
      });
  }

  document.addEventListener("DOMContentLoaded", function () {
    // mountChrome is started by the page script; wait for HARTOps only for helpers.
    init().catch(function (err) {
      console.error(err);
      HARTOps.renderError($("tb-app"), { what: "the tables browser", err: err });
    });
  });
})();
