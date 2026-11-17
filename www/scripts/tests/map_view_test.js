// Zoom and overview arithmetic for the Layout Explorer, www/js/map-view.js (run: node map_view_test.js).
const assert = require("assert");
const path = require("path");
const MV = require(path.join(__dirname, "..", "..", "js", "map-view.js"));

const near = (a, b, msg) => assert.ok(Math.abs(a - b) < 1e-9, msg + ": " + a + " != " + b);

// Fit: the Digicon board (3780 x 2055) fits by width in a wide frame and by height in a tall one.
near(MV.fitZoom(1260, 2000, 3780, 2055), 1 / 3, "fit by width");
near(MV.fitZoom(4000, 685, 3780, 2055), 1 / 3, "fit by height");
assert.throws(() => MV.fitZoom(1000, 500, 0, 2055), /positive/);
assert.throws(() => MV.fitZoom(NaN, 500, 3780, 2055), /not a number/);

// Zooming about a point keeps that map point under it.
const v = { scrollLeft: 300, scrollTop: 120, offX: 0, offY: 0, zoom: 0.5 };
const p = MV.pointAt(v, 200, 100);
near(p.x, 1000, "point x");
near(p.y, 440, "point y");
const s = MV.scrollFor(p, 1, 200, 100, 0, 0);
const back = MV.pointAt({ scrollLeft: s.left, scrollTop: s.top, offX: 0, offY: 0, zoom: 1 }, 200, 100);
near(back.x, p.x, "kept x");
near(back.y, p.y, "kept y");

// A centred map (offset inside the frame) counts its offset, and scroll never goes negative.
const c = MV.pointAt({ scrollLeft: 0, scrollTop: 0, offX: 50, offY: 20, zoom: 0.25 }, 50, 20);
near(c.x, 0, "centred map starts at its offset");
near(c.y, 0, "centred map starts at its offset (y)");
assert.deepStrictEqual(MV.scrollFor({ x: 10, y: 10 }, 0.5, 400, 300, 0, 0), { left: 0, top: 0 });

// The overview box: the whole map at Fit, a quarter of it at twice that zoom, kept inside the map.
const fit = { scrollLeft: 0, scrollTop: 0, offX: 0, offY: 0, zoom: 1 / 3 };
assert.ok(MV.showsAll(MV.viewRect(fit, 1260, 685, 3780, 2055)), "fit shows all");
const r = MV.viewRect({ scrollLeft: 630, scrollTop: 342.5, offX: 0, offY: 0, zoom: 2 / 3 }, 1260, 685, 3780, 2055);
near(r.x, 0.25, "box x");
near(r.y, 0.25, "box y");
near(r.w, 0.5, "box w");
near(r.h, 0.5, "box h");
assert.ok(!MV.showsAll(r), "zoomed does not show all");
const edge = MV.viewRect({ scrollLeft: 3000, scrollTop: 0, offX: 0, offY: 0, zoom: 1 }, 1260, 685, 3780, 2055);
near(edge.x + edge.w, 1, "box stops at the map's right edge");

console.log("map_view_test: ok");
