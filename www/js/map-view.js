// Zoom and overview-map arithmetic for the Layout Explorer (www/js/layout-explorer.js).
// Pure functions, no DOM: map points are in the image's own pixels; the view is the scroll box.
// Tests: www/scripts/tests/map_view_test.js (node).
(function (root) {
  "use strict";

  function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(hi, v));
  }

  function check(name, v) {
    if (typeof v !== "number" || !isFinite(v)) throw new Error("map-view: " + name + " is not a number: " + v);
    return v;
  }

  // The zoom that shows the whole map inside a view of viewW x viewH.
  function fitZoom(viewW, viewH, natW, natH) {
    check("viewW", viewW);
    check("viewH", viewH);
    if (!(natW > 0 && natH > 0)) throw new Error("map-view: map size must be positive: " + natW + " x " + natH);
    return Math.min(viewW / natW, viewH / natH);
  }

  // The map point under view position (fx, fy). v: {scrollLeft, scrollTop, offX, offY, zoom}, where offX/offY is
  // where the scaled map starts inside the scroll box (it is centred while smaller than the view).
  function pointAt(v, fx, fy) {
    check("zoom", v.zoom);
    return { x: (v.scrollLeft + fx - v.offX) / v.zoom, y: (v.scrollTop + fy - v.offY) / v.zoom };
  }

  // The scroll that puts map point p under view position (fx, fy) at zoom z, for a map starting at (offX, offY).
  function scrollFor(p, z, fx, fy, offX, offY) {
    return { left: Math.max(0, offX + p.x * z - fx), top: Math.max(0, offY + p.y * z - fy) };
  }

  // The part of the map the view shows, as fractions 0..1 of the map's width and height (for the overview box).
  function viewRect(v, viewW, viewH, natW, natH) {
    var a = pointAt(v, 0, 0);
    var b = pointAt(v, viewW, viewH);
    var x0 = clamp(a.x / natW, 0, 1);
    var y0 = clamp(a.y / natH, 0, 1);
    var x1 = clamp(b.x / natW, 0, 1);
    var y1 = clamp(b.y / natH, 0, 1);
    return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
  }

  // True when the whole map is in view (the overview has nothing to add).
  function showsAll(r) {
    var eps = 0.002;
    return r.x <= eps && r.y <= eps && r.x + r.w >= 1 - eps && r.y + r.h >= 1 - eps;
  }

  var api = { clamp: clamp, fitZoom: fitZoom, pointAt: pointAt, scrollFor: scrollFor, viewRect: viewRect, showsAll: showsAll };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.HARTMapView = api;
})(this);
