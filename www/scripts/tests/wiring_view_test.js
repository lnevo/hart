// The wiring viewer, www/js/wiring.js, on a small inventory in a stub page (run: node wiring_view_test.js): the
// search rules, the tabs and their counts, the port map, the URL state, and the errors for a broken inventory.
"use strict";
const assert = require("assert");
const path = require("path");
const { loadPage, same, WWW } = require("./stub_page.js");

const WIRING_JS = path.join(WWW, "js", "wiring.js");
const IDS = ["wr-q", "wr-tabs", "wr-view", "wr-dialog", "wr-dialog-title", "wr-dialog-body", "wr-source", "wr-close"];

const pin = (port, n, device, kind, extra) => Object.assign({ pin: n, port, device, kind, place: "West" }, extra || {});
const INV = {
  source: { version: "v86" },
  nodes: [
    {
      id: "C4", address: "4", location: "West - Staging", type: "Client", turnouts: ["Switch 3"], signals: ["6LB"], blockNames: ["Track 1"],
      outputs: [{ board: "OU1", rail: "12V", pins: [pin("C4-OU1-1", 1, "Switch 3 N", "motor"), pin("C4-OU1-2", 2, "6LB R", "lamp", { color: "R", head: "6LB" })] }],
      inputs: [{ board: "IN1", pins: [pin("C4-IN1-1", 1, "Switch 3 N FB", "feedback")] }],
      detectors: [{ detector: "C4-B1", channels: [{ channel: "1", port: "C4-B1-1", block: "Track 1" }] }],
    },
    { id: "C35", address: "35", location: "East", type: "Client", turnouts: ["Switch 35"], signals: [], blockNames: [] },
  ],
  signals: [
    { head: "6LB", mast: "6LB", disc: "S", node: "C4", place: "West", type: "Digicon searchlight", lamps: { R: "C4-OU1-2" } },
  ],
  turnouts: [
    { name: "Switch 3", half: "", node: "C4", motorN: "C4-OU1-1", signals: { entry: "6LB" } },
    { name: "Switch 35", half: "35a", node: "C35", signals: {} },
    { name: "Switch 35", half: "35b", node: "C35", signals: {} },
  ],
  blocks: [{ port: "C4-B1-1", node: "C4", block: "Track 1", area: "West" }],
};

async function page(search, inv) {
  const p = loadPage(WIRING_JS, { ids: IDS, json: { "data/wiring-inventory.json": inv || INV }, search });
  await p.ctx.HARTWiring.mount();
  return p;
}

async function main() {
  const lib = (await page("")).ctx.HARTWiring.lib;

  // The search: "sw 35" and "switch35" mean Switch 35, and a number matches whole.
  same(lib.terms("sw 35"), ["switch 35"]);
  same(lib.terms("Switch35"), ["switch 35"]);
  same(lib.terms("  "), []);
  assert.ok(lib.hit("Switch 3 N", lib.terms("switch 3")));
  assert.ok(!lib.hit("Switch 35 N", lib.terms("switch 3")), "Switch 3 does not find Switch 35");
  assert.ok(lib.hit("6LA 6LB", lib.terms("6l")), "letters match partway");

  // The index: masts from the heads, pins by port, and a missing list is an error naming it.
  const ix = lib.indexInventory(INV);
  same(ix.masts.map((m) => m.key), ["6LB"]);
  assert.strictEqual(ix.pinByPort["C4-IN1-1"].device, "Switch 3 N FB");
  assert.throws(() => lib.indexInventory(Object.assign({}, INV, { blocks: undefined })), /has no blocks list/);
  assert.throws(() => lib.indexInventory(Object.assign({}, INV, { source: {} })), /no source version/);

  // A board with nothing at a pin shows a spare there.
  same(lib.pinAt(INV.nodes[0].outputs[0], 5), { pin: 5, kind: "spare", port: "" });

  // Matches and tabs: a crossover's halves count once, and a tab with nothing found is marked while searching.
  const res = lib.matchInventory(ix, "switch 35");
  same(res.nodes.map((n) => n.id), ["C35"]);
  assert.strictEqual(lib.groupTurnouts(res.turnouts).length, 1);
  const tabs = lib.tabsHtml(res, "turnouts", "switch 35");
  assert.match(tabs, /data-tab="turnouts" aria-selected="true">Turnouts <span class="wr-count">1</);
  assert.match(tabs, /data-tab="signals" aria-selected="false" class="is-empty">/);

  // Nothing found: the message names the search, escaped.
  const none = lib.matchInventory(ix, "<b>");
  assert.match(lib.viewHtml("nodes", none, INV.signals, "<b>"), /Nothing here matches “&lt;b&gt;”/);

  // The port map: the chosen pin is selected and described; a node with no boards says so.
  const map = lib.portMapHtml(INV.nodes[0], "C4-OU1-2");
  assert.match(map, /class="wr-pin k-lamp c-R is-sel" data-port="C4-OU1-2"/);
  assert.match(map, /Signal lamp, red/);
  assert.match(map, /Block detectors/);
  assert.strictEqual(lib.portMapHtml(INV.nodes[1], ""), '<p class="muted">This node has no output or input boards in the inventory.</p>');

  // Typed ids: a node, a pin of a node, and nothing for an unknown node.
  same(lib.nodeQuery("c4-ou1-2", ix.nodeById), { node: "C4", pin: "C4-OU1-2" });
  same(lib.nodeQuery("c35", ix.nodeById), { node: "C35", pin: "" });
  assert.strictEqual(lib.nodeQuery("C9", ix.nodeById), null);

  // URL state: ?signal= is a signals search, an unknown tab is Nodes, and the URL leaves out what is default.
  same(lib.stateFromUrl("?signal=6LB"), { tab: "signals", q: "6LB", node: "", pin: "" });
  assert.strictEqual(lib.stateFromUrl("?tab=bogus").tab, "nodes");
  assert.strictEqual(lib.urlFor({ tab: "nodes", q: "", node: "", pin: "x" }), "");
  assert.strictEqual(lib.urlFor({ tab: "blocks", q: "T 1", node: "C4", pin: "C4-B1-1" }), "?tab=blocks&q=T+1&node=C4&pin=C4-B1-1");

  // The page: the source line, the Nodes tab, and ?node= opening that node's port map.
  const home = await page("");
  assert.strictEqual(home.els["wr-source"].innerHTML, "From the LCOS layout inventory v86.");
  assert.match(home.els["wr-view"].innerHTML, /data-node="C4"/);
  assert.strictEqual(home.els["wr-view"].className, "wr-view view-nodes");
  const opened = await page("?node=C4&pin=C4-OU1-1");
  assert.strictEqual(opened.els["wr-dialog"].getAttribute("open"), "");
  assert.match(opened.els["wr-dialog-title"].innerHTML, /^C4 <small class="muted">radio 4 · West - Staging<\/small>$/);
  assert.match(opened.els["wr-dialog-body"].innerHTML, /is-sel" data-port="C4-OU1-1"/);
  assert.strictEqual(opened.urls[opened.urls.length - 1], "/page/?node=C4&pin=C4-OU1-1");

  // Enter on a pin id opens its node; closing clears the node and the pin from the URL.
  const typed = await page("");
  typed.els["wr-q"].value = "c4-in1-1";
  typed.els["wr-q"].listeners.keydown.forEach((f) => f({ key: "Enter" }));
  assert.match(typed.els["wr-dialog-body"].innerHTML, /is-sel" data-port="C4-IN1-1"/);
  typed.els["wr-close"].listeners.click.forEach((f) => f());
  assert.strictEqual(typed.urls[typed.urls.length - 1], "/page/");

  // A page without one of its elements is an error naming it.
  const broken = loadPage(WIRING_JS, { ids: IDS.filter((i) => i !== "wr-close"), json: { "data/wiring-inventory.json": INV } });
  await assert.rejects(broken.ctx.HARTWiring.mount(), /the wiring page has no #wr-close/);

  console.log("wiring_view_test: ok");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
