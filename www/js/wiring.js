// Wiring viewer (behind/wiring.html): LCOS nodes as port grids, signal heads and their
// R/Y/G pins, turnouts and block sensors, with one search across all of it.
// Data: data/wiring-inventory.json, built by scripts/build_wiring_json.py from the wiring model
// (the sheets it writes as the v86 inventory, built in memory; the workbook file is never read).
// The HTML is drawn by plain functions of the inventory (HARTWiring.lib); mount() keeps the state, the URL and
// the listeners. Tests: scripts/tests/wiring_view_test.js.
//
// Shareable URLs: ?tab=signals&q=6LB · ?node=C4 (opens its port map) · ?node=C4&pin=C4-OU2-7
(function () {
  var TABS = [
    { id: "nodes", label: "Nodes" },
    { id: "signals", label: "Signals" },
    { id: "turnouts", label: "Turnouts" },
    { id: "blocks", label: "Block sensors" },
  ];
  var KIND_LABEL = {
    lamp: "Signal lamp",
    motor: "Switch motor",
    cal: "Detector calibration",
    relay: "Relay",
    reserved: "Reserved",
    spare: "Spare",
    feedback: "Switch position",
    button: "Pushbutton",
    other: "Other",
  };
  var COLOR_NAME = { R: "Red", Y: "Yellow", G: "Green" };
  var NONE = '<span class="muted">—</span>';

  var esc = HARTOps.esc;

  function norm(s) {
    return String(s || "").toLowerCase();
  }

  // The search is one phrase ("Switch 3", "Yard T1", "West Ext"); "sw 35" and
  // "switch35" both mean Switch 35.
  function terms(q) {
    var t = norm(q)
      .replace(/\bsw\.?\s*(\d)/g, "switch $1")
      .replace(/switch(\d)/g, "switch $1")
      .replace(/\s+/g, " ")
      .trim();
    return t ? [t] : [];
  }

  // A number in the search is matched whole, so "Switch 3" doesn't find Switch 35 and
  // "C1" doesn't find C11; letters still match partway ("6L" finds 6LA and 6LB).
  var reCache = {};
  function termRe(t) {
    if (!reCache[t]) {
      var body = t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      if (/^\d/.test(t)) body = "(?:^|[^0-9])" + body;
      if (/\d$/.test(t)) body += "(?![0-9])";
      reCache[t] = new RegExp(body);
    }
    return reCache[t];
  }

  function hit(hay, ts) {
    if (!ts.length) return true;
    var h = norm(hay);
    return ts.every(function (t) {
      return termRe(t).test(h);
    });
  }

  function chip(color, text) {
    return (
      '<span class="wr-lamp wr-' + esc(color) + '" title="' + esc(COLOR_NAME[color] || "") + '">' +
      esc(color) + "</span>" + (text ? " " + text : "")
    );
  }

  // Short label for a pin cell.
  function shortDevice(p) {
    if (!p.device) return p.kind === "spare" ? "spare" : "";
    if (p.kind === "lamp") return p.head;
    if (p.kind === "cal") return "BD cal";
    if (p.kind === "reserved") return "resv";
    return p.device
      .replace(/^Switch /, "Sw ")
      .replace(/ BTN$/, " btn")
      .replace(/ FB$/, " fb");
  }

  // —— The inventory, indexed ——
  var boards = (n) => (n.outputs || []).concat(n.inputs || []);
  var hasBoards = (n) => (n.outputs || []).length > 0 || (n.inputs || []).length > 0;
  // A Digicon searchlight's heads share a mast; an RGB head is a signal of its own.
  var mastKey = (h) => (h.type === "Digicon searchlight" && h.mast ? h.mast : h.head);
  var nodeAddr = (n) => (n.type === "Main" ? "main node" : n.type === "DCC" ? "DCC" : "radio " + n.address);

  // Pin i (1 to 8) of a board, or a spare stand-in when the board lists nothing there.
  function pinAt(b, i) {
    return b.pins.find(function (x) { return x.pin === i; }) || { pin: i, kind: "spare", port: "" };
  }

  // Nodes by id, pins by port and the masts, from data/wiring-inventory.json. A file without one of its lists is
  // an error naming the list, not a page that draws empty tabs.
  function indexInventory(inv) {
    ["nodes", "signals", "turnouts", "blocks"].forEach(function (k) {
      if (!Array.isArray(inv && inv[k])) throw new Error("data/wiring-inventory.json has no " + k + " list");
    });
    if (!inv.source || !inv.source.version) throw new Error("data/wiring-inventory.json has no source version");
    var nodeById = {};
    var pinByPort = {};
    inv.nodes.forEach(function (n) {
      nodeById[n.id] = n;
      boards(n).forEach(function (b) {
        b.pins.forEach(function (p) {
          pinByPort[p.port] = p;
        });
      });
    });
    var mastMap = {};
    var masts = [];
    inv.signals.forEach(function (h) {
      var key = mastKey(h);
      if (!mastMap[key]) {
        mastMap[key] = { key: key, node: h.node, heads: [], type: h.type };
        masts.push(mastMap[key]);
      }
      mastMap[key].heads.push(h);
    });
    var order = { T: 0, B: 1 };
    masts.forEach(function (m) {
      m.heads.sort(function (a, b) {
        return (order[a.disc] || 0) - (order[b.disc] || 0);
      });
    });
    return { inv: inv, nodeById: nodeById, pinByPort: pinByPort, masts: masts };
  }

  // —— Search haystacks ——
  function nodeHay(n) {
    var parts = [n.id, "radio " + n.address, n.location, n.type].concat(n.turnouts, n.signals, n.blockNames);
    boards(n).forEach(function (b) {
      b.pins.forEach(function (p) {
        parts.push(p.port, p.device, p.place);
      });
    });
    (n.detectors || []).forEach(function (d) {
      d.channels.forEach(function (c) {
        parts.push(c.port, c.block);
      });
    });
    return parts.join(" | ");
  }
  function mastHay(m) {
    var parts = [m.key, m.node, m.type];
    m.heads.forEach(function (h) {
      parts.push(h.head, h.mast, h.place, h.packed, h.cp, h.route, h.appearance);
      for (var c in h.lamps) parts.push(h.lamps[c]);
    });
    return parts.join(" | ");
  }
  function objHay(o) {
    var parts = [];
    (function walk(x) {
      if (x == null) return;
      if (typeof x === "object") for (var k in x) walk(x[k]);
      else parts.push(String(x));
    })(o);
    return parts.join(" | ");
  }

  // What each tab lists for the search q.
  function matchInventory(ix, q) {
    var ts = terms(q);
    var match = (hay) => (x) => hit(hay(x), ts);
    return {
      nodes: ix.inv.nodes.filter(match(nodeHay)),
      signals: ix.masts.filter(match(mastHay)),
      turnouts: ix.inv.turnouts.filter(match(objHay)),
      blocks: ix.inv.blocks.filter(match(objHay)),
    };
  }

  // —— Shared bits ——
  function link(params) {
    return "?" + new URLSearchParams(params).toString();
  }
  function portLink(port) {
    if (!port) return NONE;
    var nid = port.split("-")[0];
    return (
      '<a class="wr-port" href="' + esc(link({ node: nid, pin: port })) + '" data-node="' + esc(nid) +
      '" data-pin="' + esc(port) + '">' + esc(port) + "</a>"
    );
  }
  function searchLink(text, tab) {
    return '<a href="' + esc(link({ tab: tab, q: text })) + '" data-q="' + esc(text) + '" data-tab="' + tab + '">' + esc(text) + "</a>";
  }
  function nodeLink(nid) {
    if (!nid) return "—";
    return '<a href="' + esc(link({ node: nid })) + '" data-node="' + esc(nid) + '">' + esc(nid) + "</a>";
  }

  function cellClass(p) {
    var c = "wr-cell k-" + p.kind;
    if (p.color) c += " c-" + p.color;
    return c;
  }

  function emptyHtml(q) {
    return '<p class="muted wr-empty">Nothing here matches “' + esc(q) + "”. Try another tab, or a shorter search.</p>";
  }

  // —— Nodes tab ——
  function miniBoard(b, isInput, ts) {
    var cells = [];
    for (var i = 1; i <= 8; i++) {
      var p = pinAt(b, i);
      var title = p.port + (p.device ? " · " + p.device : " · spare");
      var mark = ts.length && p.port && hit([p.port, p.device].join(" "), ts) ? " is-hit" : "";
      cells.push('<span class="' + cellClass(p) + mark + '" title="' + esc(title) + '">' + (p.color ? esc(p.color) : i) + "</span>");
    }
    var tag = isInput ? "IN" : (b.rail || "");
    return (
      '<div class="wr-mini-row"><span class="wr-mini-label">' + esc(b.board) +
      (tag && !isInput ? ' <small>' + esc(tag) + "</small>" : "") + "</span>" +
      '<span class="wr-mini">' + cells.join("") + "</span></div>"
    );
  }

  // The switches, signals and block count under a node card.
  function nodeFacts(n, signals) {
    var facts = [];
    if (n.turnouts.length) facts.push("<dt>Switches</dt><dd>" + esc(n.turnouts.map(function (t) { return t.replace(/^Switch /, ""); }).join(", ")) + "</dd>");
    var sigNames = [];
    signals.forEach(function (h) {
      if (h.node !== n.id) return;
      var k = mastKey(h);
      if (sigNames.indexOf(k) === -1) sigNames.push(k);
    });
    if (sigNames.length) facts.push("<dt>Signals</dt><dd>" + esc(sigNames.join(", ")) + "</dd>");
    var nBlocks = (n.detectors || []).reduce(function (a, d) { return a + d.channels.length; }, 0);
    if (nBlocks) facts.push("<dt>Blocks</dt><dd>" + nBlocks + " detected</dd>");
    return facts.length ? '<dl class="wr-facts">' + facts.join("") + "</dl>" : "";
  }

  function nodeCard(n, signals, ts) {
    var minis = (n.outputs || []).map(function (b) { return miniBoard(b, false, ts); })
      .concat((n.inputs || []).map(function (b) { return miniBoard(b, true, ts); }))
      .join("");
    return (
      '<a class="wr-node card" href="' + esc(link({ node: n.id })) + '" data-node="' + esc(n.id) + '">' +
      '<span class="wr-node-head"><strong class="wr-node-id">' + esc(n.id) + "</strong>" +
      '<span class="wr-node-addr">' + esc(nodeAddr(n)) + "</span></span>" +
      '<span class="wr-node-loc">' + esc(n.location) + "</span>" +
      (hasBoards(n) ? '<span class="wr-minis">' + minis + "</span>" : '<span class="muted wr-node-none">No output or input boards.</span>') +
      nodeFacts(n, signals) +
      "</a>"
    );
  }

  var LEGEND =
    '<p class="wr-legend" aria-label="Legend">' +
    '<span><span class="wr-cell k-motor">1</span> switch motor</span>' +
    '<span><span class="wr-cell k-lamp c-R">R</span><span class="wr-cell k-lamp c-Y">Y</span><span class="wr-cell k-lamp c-G">G</span> signal lamp</span>' +
    '<span><span class="wr-cell k-feedback">1</span> position</span>' +
    '<span><span class="wr-cell k-button">1</span> pushbutton</span>' +
    '<span><span class="wr-cell k-cal">8</span> detector cal</span>' +
    '<span><span class="wr-cell k-spare">1</span> spare</span>' +
    "</p>";

  function nodesHtml(list, signals, q) {
    if (!list.length) return emptyHtml(q);
    var ts = terms(q);
    return '<div class="wr-node-grid">' + list.map(function (n) { return nodeCard(n, signals, ts); }).join("") + "</div>" + LEGEND;
  }

  // —— Signals tab ——
  function lampRow(h) {
    return ["R", "Y", "G"]
      .map(function (c) {
        return '<span class="wr-lamp-pin">' + chip(c) + " " + portLink(h.lamps[c]) + "</span>";
      })
      .join("");
  }

  function headRow(m, h) {
    var label = m.heads.length > 1 || h.disc === "T" || h.disc === "B" ? { T: "Top", B: "Bottom" }[h.disc] || h.head : "Head";
    return (
      '<div class="wr-head"><span class="wr-head-name">' + esc(label) +
      (h.packed ? ' <small class="muted">' + esc(h.packed) + "</small>" : "") + "</span>" +
      '<span class="wr-head-pins">' + lampRow(h) + "</span></div>"
    );
  }

  function mastCard(m) {
    var first = m.heads[0];
    var sub = [first.type === "Digicon searchlight" ? "Digicon searchlight" : "RGB LED"];
    if (first.appearance) sub.push(first.appearance.replace(/^CO-/, "C&O "));
    if (first.cp) sub.push(first.cp);
    return (
      '<article class="wr-sig card">' +
      '<header><h3>' + esc(m.key) + "</h3>" +
      '<span class="muted">' + esc(sub.join(" · ")) + "</span></header>" +
      '<p class="wr-sig-where">Node ' + nodeLink(m.node) + (first.place ? " · " + esc(first.place) : "") + "</p>" +
      (first.route ? '<p class="wr-sig-where">' + esc(first.route.replace(/^\?\s*→/, "from ? →")) + "</p>" : "") +
      m.heads.map(function (h) { return headRow(m, h); }).join("") +
      "</article>"
    );
  }

  function signalsHtml(list, q) {
    if (!list.length) return emptyHtml(q);
    return '<div class="wr-sig-grid">' + list.map(mastCard).join("") + "</div>";
  }

  // —— Turnouts tab ——
  // A crossover is one turnout with a row per half (same name, a half label each): group them under one heading.
  function groupTurnouts(list) {
    var groups = [];
    var byName = {};
    list.forEach(function (t) {
      if (!byName[t.name]) {
        byName[t.name] = { name: t.name, first: t, halves: [] };
        groups.push(byName[t.name]);
      }
      byName[t.name].halves.push(t);
    });
    return groups;
  }

  function turnoutSignals(t) {
    var sigs = [];
    ["entry", "normal", "reverse"].forEach(function (k) {
      var s = (t.signals || {})[k];
      if (s) sigs.push('<span class="wr-nowrap">' + searchLink(s, "signals") + ' <small class="muted">' + k + "</small></span>");
    });
    return sigs.join(" ");
  }

  function turnoutRow(g) {
    var t = g.first;
    var sigHtml = g.halves.length > 1 || t.half
      ? g.halves.map(function (h) { return '<div><small class="muted">' + esc(h.half) + "</small> " + (turnoutSignals(h) || NONE) + "</div>"; }).join("")
      : turnoutSignals(t) || NONE;
    return (
      "<tr><th scope=\"row\">" + esc(g.name) +
      (t.elements && t.elements !== g.name ? '<small class="muted wr-sub">' + esc(t.elements) + "</small>" : "") +
      (t.area ? '<small class="muted wr-sub">' + esc(t.area) + "</small>" : "") + "</th>" +
      '<td data-label="Node">' + nodeLink(t.node) + "</td>" +
      '<td data-label="Motor N">' + portLink(t.motorN) + '</td><td data-label="Motor R">' + portLink(t.motorR) + "</td>" +
      '<td data-label="Button">' + portLink(t.button) + '</td><td data-label="Position N">' + portLink(t.fbN) +
      '</td><td data-label="Position R">' + portLink(t.fbR) + "</td>" +
      '<td data-label="Signals" class="wr-span">' + sigHtml + "</td></tr>"
    );
  }

  function turnoutsHtml(list, q) {
    if (!list.length) return emptyHtml(q);
    return (
      '<div class="wr-table-wrap"><table class="wr-table wr-stack">' +
      "<thead><tr><th>Switch</th><th>Node</th><th>Motor N</th><th>Motor R</th><th>Button</th><th>Position N</th><th>Position R</th><th>Signals</th></tr></thead><tbody>" +
      groupTurnouts(list).map(turnoutRow).join("") +
      "</tbody></table></div>"
    );
  }

  // —— Blocks tab ——
  function blockRow(b) {
    return (
      "<tr><th scope=\"row\">" + esc(b.block || "—") + "</th>" +
      '<td data-label="Detector"><a href="' + esc(link({ node: b.node })) + '" data-node="' + esc(b.node) + '">' + esc(b.port) + "</a></td>" +
      '<td data-label="Area">' + esc(b.area || "") + '</td><td data-label="District">' + esc(b.district || "") + "</td>" +
      '<td class="wr-wide">' + esc(b.track || "") + '</td><td class="wr-wide muted">' + esc(b.note || "") + "</td></tr>"
    );
  }

  function blocksHtml(list, q) {
    if (!list.length) return emptyHtml(q);
    return (
      '<div class="wr-table-wrap"><table class="wr-table wr-stack">' +
      '<thead><tr><th>Block</th><th>Detector</th><th>Area</th><th>District</th><th class="wr-wide">Track</th><th class="wr-wide">Notes</th></tr></thead><tbody>' +
      list.map(blockRow).join("") +
      "</tbody></table></div>"
    );
  }

  // The view of one tab for matches res (from matchInventory).
  function viewHtml(tab, res, signals, q) {
    if (tab === "signals") return signalsHtml(res.signals, q);
    if (tab === "turnouts") return turnoutsHtml(res.turnouts, q);
    if (tab === "blocks") return blocksHtml(res.blocks, q);
    return nodesHtml(res.nodes, signals, q);
  }

  // The tab bar with each tab's count; with a search on, a tab with nothing found is marked empty.
  function tabsHtml(res, tab, q) {
    var counts = {
      nodes: res.nodes.length,
      signals: res.signals.length,
      turnouts: groupTurnouts(res.turnouts).length,
      blocks: res.blocks.length,
    };
    return TABS.map(function (t) {
      return (
        '<button type="button" role="tab" data-tab="' + t.id + '" aria-selected="' + (t.id === tab) + '"' + (q && !counts[t.id] ? ' class="is-empty"' : "") + ">" +
        t.label + ' <span class="wr-count">' + counts[t.id] + "</span></button>"
      );
    }).join("");
  }

  // —— Node port map (dialog) ——
  function pinDetail(p) {
    if (!p) return "";
    var bits = ['<strong>' + esc(p.port) + "</strong>", esc(p.device || "Spare")];
    bits.push('<span class="muted">' + esc(KIND_LABEL[p.kind] || p.kind) + (p.color ? ", " + COLOR_NAME[p.color].toLowerCase() : "") + "</span>");
    if (p.place) bits.push('<span class="muted">' + esc(p.place) + "</span>");
    var extra = "";
    if (p.note) extra += '<span class="wr-detail-note">' + esc(p.note) + "</span>";
    if (p.kind === "lamp") extra += " " + searchLink(p.head.split(" ")[0], "signals");
    if (/^Switch \d+/.test(p.device || "")) extra += " " + searchLink(p.device.match(/^Switch \d+/)[0], "turnouts");
    return bits.join(" · ") + (extra ? "<br>" + extra : "");
  }

  // One board of the port map; the pin whose port is selPin is selected and described under it.
  function fullBoard(b, isInput, selPin) {
    var cells = [];
    for (var i = 1; i <= 8; i++) {
      var p = pinAt(b, i);
      cells.push(
        '<button type="button" class="wr-pin ' + cellClass(p).replace("wr-cell ", "") +
        (p.port && p.port === selPin ? " is-sel" : "") + '" data-port="' + esc(p.port) + '">' +
        '<span class="wr-pin-top"><span class="wr-pin-n">' + i + "</span>" +
        (p.color ? chip(p.color) : "") + "</span>" +
        '<span class="wr-pin-dev">' + esc(shortDevice(p)) + "</span></button>"
      );
    }
    var sel = b.pins.find(function (x) { return x.port === selPin; });
    return (
      '<section class="wr-board" data-board="' + esc(b.board) + '">' +
      "<h3>" + esc(b.board) + ' <small class="muted">' +
      esc(isInput ? "DNIN8 inputs" : "DNOU8 outputs · " + (b.rail || "")) +
      (b.place ? " · " + esc(b.place) : "") + "</small></h3>" +
      '<div class="wr-pins">' + cells.join("") + "</div>" +
      '<p class="wr-detail">' + (sel ? pinDetail(sel) : "") + "</p></section>"
    );
  }

  function detectorsHtml(n) {
    return (
      '<section class="wr-board"><h3>Block detectors <small class="muted">two channels each</small></h3><ul class="wr-dets">' +
      n.detectors
        .map(function (d) {
          return (
            "<li><strong>" + esc(d.detector.replace(n.id + "-", "")) + "</strong> " +
            d.channels.map(function (c) { return '<span class="wr-nowrap">' + esc(c.channel) + ": " + searchLink(c.block || "—", "blocks") + "</span>"; }).join(" · ") +
            "</li>"
          );
        })
        .join("") +
      "</ul></section>"
    );
  }

  function nodeTitleHtml(n) {
    return esc(n.id) + ' <small class="muted">' + esc([nodeAddr(n), n.location].join(" · ")) + "</small>";
  }

  // The port map of node n: every board, then its block detectors.
  function portMapHtml(n, selPin) {
    var dets = (n.detectors || []).length > 0;
    if (!hasBoards(n) && !dets) return '<p class="muted">This node has no output or input boards in the inventory.</p>';
    var html = hasBoards(n) ? '<p class="muted wr-hint">Tap a pin to see what it is wired to.</p>' : "";
    (n.outputs || []).forEach(function (b) { html += fullBoard(b, false, selPin); });
    (n.inputs || []).forEach(function (b) { html += fullBoard(b, true, selPin); });
    if (dets) html += detectorsHtml(n);
    return html;
  }

  // "C4" or "C4-OU2-7" typed in the search: the node it names and the pin ("" for a node alone), or null.
  function nodeQuery(v, nodeById) {
    var m = v.toUpperCase().match(/^([A-Z]+\d+)-((?:OU|IN)\d+-\d+)$/);
    if (m && nodeById[m[1]]) return { node: m[1], pin: m[1] + "-" + m[2] };
    if (nodeById[v.toUpperCase()]) return { node: v.toUpperCase(), pin: "" };
    return null;
  }

  // The page state from the URL; ?signal= is the older link form of a signals search.
  function stateFromUrl(search) {
    var params = new URLSearchParams(search);
    var state = {
      tab: TABS.some(function (t) { return t.id === params.get("tab"); }) ? params.get("tab") : "nodes",
      q: params.get("q") || "",
      node: params.get("node") || "",
      pin: params.get("pin") || "",
    };
    if (params.get("signal")) {
      state.tab = "signals";
      state.q = params.get("signal");
    }
    return state;
  }

  function urlFor(state) {
    var p = new URLSearchParams();
    if (state.tab !== "nodes") p.set("tab", state.tab);
    if (state.q) p.set("q", state.q);
    if (state.node) p.set("node", state.node);
    if (state.node && state.pin) p.set("pin", state.pin);
    var s = p.toString();
    return s ? "?" + s : "";
  }

  // —— The page ——
  function mount(ix, els) {
    var state = stateFromUrl(location.search);
    els.q.value = state.q;

    function syncUrl() {
      history.replaceState(null, "", location.pathname + urlFor(state));
    }

    function openNode(nid) {
      var n = ix.nodeById[nid];
      if (!n) return;
      state.node = nid;
      syncUrl();
      els.dlgTitle.innerHTML = nodeTitleHtml(n);
      els.dlgBody.innerHTML = portMapHtml(n, state.pin);
      if (!els.dlg.open) {
        if (els.dlg.showModal) els.dlg.showModal();
        else els.dlg.setAttribute("open", "");
      }
      var selEl = els.dlgBody.querySelector(".is-sel");
      if (selEl && selEl.scrollIntoView) selEl.scrollIntoView({ block: "center" });
      else els.dlgBody.scrollTop = 0;
    }

    function closeNode() {
      state.node = "";
      state.pin = "";
      syncUrl();
      if (els.dlg.open) {
        if (els.dlg.close) els.dlg.close();
        else els.dlg.removeAttribute("open");
      }
    }

    // A pin tapped in the port map: select it and describe it under its board.
    function selectPin(btn) {
      var port = btn.getAttribute("data-port");
      state.pin = port || "";
      syncUrl();
      var sec = btn.closest(".wr-board");
      sec.querySelectorAll(".wr-pin").forEach(function (b) { b.classList.toggle("is-sel", b === btn); });
      sec.querySelector(".wr-detail").innerHTML = pinDetail(ix.pinByPort[port] || { port: port || "", kind: "spare" });
    }

    function render() {
      var res = matchInventory(ix, state.q);
      els.tabs.innerHTML = tabsHtml(res, state.tab, state.q);
      els.view.innerHTML = viewHtml(state.tab, res, ix.inv.signals, state.q);
      els.view.className = "wr-view view-" + state.tab;
      syncUrl();
    }

    function go(tab, q) {
      state.tab = tab;
      state.q = q == null ? state.q : q;
      els.q.value = state.q;
      render();
      window.scrollTo({ top: 0 });
    }

    els.dlgBody.addEventListener("click", function (e) {
      var btn = e.target.closest(".wr-pin");
      if (btn) {
        selectPin(btn);
        return;
      }
      var a = e.target.closest("a[data-q]");
      if (a) {
        e.preventDefault();
        closeNode();
        go(a.getAttribute("data-tab"), a.getAttribute("data-q"));
      }
    });
    els.close.addEventListener("click", closeNode);
    els.dlg.addEventListener("cancel", function (e) {
      e.preventDefault();
      closeNode();
    });
    els.dlg.addEventListener("click", function (e) {
      if (e.target === els.dlg) closeNode();
    });
    els.tabs.addEventListener("click", function (e) {
      var b = e.target.closest("button[data-tab]");
      if (b) go(b.getAttribute("data-tab"));
    });
    els.view.addEventListener("click", function (e) {
      var a = e.target.closest("a[data-q]");
      if (a) {
        e.preventDefault();
        go(a.getAttribute("data-tab"), a.getAttribute("data-q"));
        return;
      }
      var nl = e.target.closest("[data-node]");
      if (nl) {
        e.preventDefault();
        state.pin = nl.getAttribute("data-pin") || "";
        openNode(nl.getAttribute("data-node"));
      }
    });

    var timer = null;
    els.q.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(function () {
        state.q = els.q.value.trim();
        render();
      }, 120);
    });
    // Enter on a node or pin id ("C4", "C4-OU2-7") opens that node's port map.
    els.q.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      var hitNode = nodeQuery(els.q.value.trim(), ix.nodeById);
      if (hitNode) {
        state.pin = hitNode.pin;
        openNode(hitNode.node);
      }
    });

    render();
    if (state.node && ix.nodeById[state.node]) openNode(state.node);
  }

  // The page's elements by id; a missing one is an error naming it.
  function pageElements() {
    var ids = { q: "wr-q", tabs: "wr-tabs", view: "wr-view", dlg: "wr-dialog", dlgTitle: "wr-dialog-title", dlgBody: "wr-dialog-body", source: "wr-source", close: "wr-close" };
    var els = {};
    Object.keys(ids).forEach(function (k) {
      els[k] = document.getElementById(ids[k]);
      if (!els[k]) throw new Error("the wiring page has no #" + ids[k]);
    });
    return els;
  }

  window.HARTWiring = {
    mount: async function () {
      var ix = indexInventory(await HARTOps.loadJson("data/wiring-inventory.json"));
      var els = pageElements();
      els.source.innerHTML = "From the LCOS layout inventory " + esc(ix.inv.source.version) + ".";
      mount(ix, els);
    },
    lib: {
      terms: terms, hit: hit, shortDevice: shortDevice, pinAt: pinAt, indexInventory: indexInventory,
      matchInventory: matchInventory, groupTurnouts: groupTurnouts, viewHtml: viewHtml, tabsHtml: tabsHtml,
      portMapHtml: portMapHtml, pinDetail: pinDetail, nodeQuery: nodeQuery, stateFromUrl: stateFromUrl, urlFor: urlFor,
    },
  };
})();
