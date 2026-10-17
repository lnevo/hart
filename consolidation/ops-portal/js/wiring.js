// Wiring viewer (behind/wiring.html): LCOS nodes as port grids, signal heads and their
// R/Y/G pins, the control-point signal splits, turnouts and block sensors, with one search
// across all of it. Data: data/wiring-inventory.json and data/signal-splits.json, built by
// scripts/build_wiring_json.py from the LCOS inventory and signal-split workbooks.
//
// Shareable URLs: ?tab=signals&q=6LB · ?node=C4 (opens its port map) · ?node=C4&pin=C4-OU2-7
// · ?tab=splits&cp=4
(function () {
  var TABS = [
    { id: "nodes", label: "Nodes" },
    { id: "signals", label: "Signals" },
    // Signal splits tab parked until the splits sheet is reviewed against the inventory.
    // { id: "splits", label: "Signal splits" },
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

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function norm(s) {
    return String(s || "").toLowerCase();
  }

  // The search is one phrase ("Switch 3", "Yard T1", "West Main Ext"); "sw 35" and
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

  // Lamp a single head shows for an aspect name (the sheets name aspects, not lamps).
  function aspectLamp(a) {
    var s = norm(a);
    if (/stop/.test(s)) return "R";
    if (/approach|restricting/.test(s)) return "Y";
    if (/clear/.test(s)) return "G";
    return "";
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

  function pinPart(port) {
    // C4-OU2-7 → OU2-7
    return String(port || "").replace(/^[A-Z]+\d+-/, "");
  }

  window.HARTWiring = {
    mount: async function () {
      var inv = await HARTOps.loadJson("data/wiring-inventory.json");
      // The splits data is optional (left out of the public build while it is under review).
      var spl = { source: {}, controlPoints: [] };

      var qInput = document.getElementById("wr-q");
      var tabBar = document.getElementById("wr-tabs");
      var out = document.getElementById("wr-view");
      var dlg = document.getElementById("wr-dialog");
      var dlgTitle = document.getElementById("wr-dialog-title");
      var dlgBody = document.getElementById("wr-dialog-body");

      document.getElementById("wr-source").innerHTML =
        "From the LCOS layout inventory " + esc(inv.source.version) +
        (inv.source.modified ? " (" + esc(inv.source.modified) + ")" : "") + ".";

      var nodeById = {};
      inv.nodes.forEach(function (n) {
        nodeById[n.id] = n;
      });
      var pinByPort = {};
      inv.nodes.forEach(function (n) {
        (n.outputs || []).concat(n.inputs || []).forEach(function (b) {
          b.pins.forEach(function (p) {
            pinByPort[p.port] = p;
          });
        });
      });

      // Masts: Digicon heads grouped by mast; RGB heads stand alone.
      var mastMap = {};
      var masts = [];
      inv.signals.forEach(function (h) {
        var key = h.type === "Digicon searchlight" && h.mast ? h.mast : h.head;
        if (!mastMap[key]) {
          mastMap[key] = { key: key, node: h.node, heads: [], type: h.type };
          masts.push(mastMap[key]);
        }
        mastMap[key].heads.push(h);
      });
      masts.forEach(function (m) {
        m.heads.sort(function (a, b) {
          var o = { T: 0, B: 1 };
          return (o[a.disc] || 0) - (o[b.disc] || 0);
        });
      });

      // —— State and URL ——
      var params = new URLSearchParams(location.search);
      var state = {
        tab: TABS.some(function (t) { return t.id === params.get("tab"); }) ? params.get("tab") : "nodes",
        q: params.get("q") || "",
        cp: params.get("cp") || (spl.controlPoints[0] && spl.controlPoints[0].id),
        node: params.get("node") || "",
        pin: params.get("pin") || "",
      };
      if (params.get("signal")) {
        state.tab = "signals";
        state.q = params.get("signal");
      }
      qInput.value = state.q;

      function syncUrl() {
        var p = new URLSearchParams();
        if (state.tab !== "nodes") p.set("tab", state.tab);
        if (state.q) p.set("q", state.q);
        if (state.tab === "splits" && state.cp) p.set("cp", state.cp);
        if (state.node) p.set("node", state.node);
        if (state.node && state.pin) p.set("pin", state.pin);
        var s = p.toString();
        history.replaceState(null, "", location.pathname + (s ? "?" + s : ""));
      }

      function link(params) {
        var p = new URLSearchParams(params);
        return "?" + p.toString();
      }

      // —— Search haystacks ——
      function nodeHay(n) {
        var parts = [n.id, n.legacy, "radio " + n.address, n.location, n.type]
          .concat(n.turnouts, n.signals, n.blockNames);
        (n.outputs || []).concat(n.inputs || []).forEach(function (b) {
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
      function sigHay(s, cp) {
        var parts = ["CP" + cp.id, cp.area, s.signal, s.mast, s.head, s.node];
        for (var c in s.lamps || {}) parts.push(s.lamps[c]);
        s.routes.forEach(function (r) {
          parts.push(r.from, r.to);
          parts = parts.concat(r.blocks || []);
          (r.switches || []).forEach(function (w) {
            parts.push(w.switch);
          });
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

      function matches() {
        var ts = terms(state.q);
        var res = {
          nodes: inv.nodes.filter(function (n) { return hit(nodeHay(n), ts); }),
          signals: masts.filter(function (m) { return hit(mastHay(m), ts); }),
          turnouts: inv.turnouts.filter(function (t) { return hit(objHay(t), ts); }),
          blocks: inv.blocks.filter(function (b) { return hit(objHay(b), ts); }),
          splits: {},
          splitCount: 0,
        };
        spl.controlPoints.forEach(function (cp) {
          var sigs = cp.signals.filter(function (s) { return hit(sigHay(s, cp), ts); });
          res.splits[cp.id] = sigs;
          res.splitCount += sigs.length;
        });
        return res;
      }

      // —— Shared bits ——
      function portLink(port) {
        if (!port) return '<span class="muted">—</span>';
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

      function miniBoard(b, isInput, ts) {
        var cells = [];
        for (var i = 1; i <= 8; i++) {
          var p = b.pins.find(function (x) { return x.pin === i; }) || { pin: i, kind: "spare", port: "" };
          var title = p.port + (p.device ? " · " + p.device : " · spare");
          var mark = ts.length && p.port && hit([p.port, p.device].join(" "), ts) ? " is-hit" : "";
          cells.push(
            '<span class="' + cellClass(p) + mark + '" title="' + esc(title) + '">' +
            (p.color ? esc(p.color) : i) + "</span>"
          );
        }
        var tag = isInput ? "IN" : (b.rail || "");
        return (
          '<div class="wr-mini-row"><span class="wr-mini-label">' + esc(b.board) +
          (tag && !isInput ? ' <small>' + esc(tag) + "</small>" : "") + "</span>" +
          '<span class="wr-mini">' + cells.join("") + "</span></div>"
        );
      }

      // —— Views ——
      function renderNodes(list) {
        if (!list.length) return empty();
        var ts = terms(state.q);
        return (
          '<div class="wr-node-grid">' +
          list
            .map(function (n) {
              var boards = (n.outputs || []).map(function (b) { return miniBoard(b, false, ts); })
                .concat((n.inputs || []).map(function (b) { return miniBoard(b, true, ts); }))
                .join("");
              var nBlocks = (n.detectors || []).reduce(function (a, d) { return a + d.channels.length; }, 0);
              var facts = [];
              if (n.turnouts.length) facts.push("<dt>Switches</dt><dd>" + esc(n.turnouts.map(function (t) { return t.replace(/^Switch /, ""); }).join(", ")) + "</dd>");
              var heads = inv.signals.filter(function (h) { return h.node === n.id; });
              var sigNames = [];
              heads.forEach(function (h) {
                var k = h.type === "Digicon searchlight" && h.mast ? h.mast : h.head;
                if (sigNames.indexOf(k) === -1) sigNames.push(k);
              });
              if (sigNames.length) facts.push("<dt>Signals</dt><dd>" + esc(sigNames.join(", ")) + "</dd>");
              if (nBlocks) facts.push("<dt>Blocks</dt><dd>" + nBlocks + " detected</dd>");
              var noIo = !(n.outputs || []).length && !(n.inputs || []).length;
              return (
                '<a class="wr-node card" href="' + esc(link({ node: n.id })) + '" data-node="' + esc(n.id) + '">' +
                '<span class="wr-node-head"><strong class="wr-node-id">' + esc(n.id) + "</strong>" +
                '<span class="wr-node-addr">' + esc(n.type === "Main" ? "main node" : n.type === "DCC" ? "DCC" : "radio " + n.address) + "</span></span>" +
                '<span class="wr-node-loc">' + esc(n.location) +
                (n.legacy ? ' <small class="muted">· old label ' + esc(n.legacy) + "</small>" : "") + "</span>" +
                (noIo ? '<span class="muted wr-node-none">No output or input boards.</span>' : '<span class="wr-minis">' + boards + "</span>") +
                (facts.length ? '<dl class="wr-facts">' + facts.join("") + "</dl>" : "") +
                "</a>"
              );
            })
            .join("") +
          "</div>" + legend()
        );
      }

      function legend() {
        return (
          '<p class="wr-legend" aria-label="Legend">' +
          '<span><span class="wr-cell k-motor">1</span> switch motor</span>' +
          '<span><span class="wr-cell k-lamp c-R">R</span><span class="wr-cell k-lamp c-Y">Y</span><span class="wr-cell k-lamp c-G">G</span> signal lamp</span>' +
          '<span><span class="wr-cell k-feedback">1</span> position</span>' +
          '<span><span class="wr-cell k-button">1</span> pushbutton</span>' +
          '<span><span class="wr-cell k-cal">8</span> detector cal</span>' +
          '<span><span class="wr-cell k-spare">1</span> spare</span>' +
          "</p>"
        );
      }

      function lampRow(h) {
        return ["R", "Y", "G"]
          .map(function (c) {
            return '<span class="wr-lamp-pin">' + chip(c) + " " + portLink(h.lamps[c]) + "</span>";
          })
          .join("");
      }

      function renderSignals(list) {
        if (!list.length) return empty();
        return (
          '<div class="wr-sig-grid">' +
          list
            .map(function (m) {
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
                m.heads
                  .map(function (h) {
                    var label = m.heads.length > 1 || h.disc === "T" || h.disc === "B"
                      ? { T: "Top", B: "Bottom" }[h.disc] || h.head
                      : "Head";
                    return (
                      '<div class="wr-head"><span class="wr-head-name">' + esc(label) +
                      (h.packed ? ' <small class="muted">' + esc(h.packed) + "</small>" : "") + "</span>" +
                      '<span class="wr-head-pins">' + lampRow(h) + "</span></div>"
                    );
                  })
                  .join("") +
                "</article>"
              );
            })
            .join("") +
          "</div>"
        );
      }

      function whenText(a, r) {
        var b = r.blocks || [];
        if (a.when === "clear") return "line clear";
        if (a.when === "B1") return (b[0] || "block 1") + " occupied";
        if (a.when === "B2") return (b[1] || "block 2") + " occupied";
        return a.when;
      }

      function renderSplits(found) {
        var cps = spl.controlPoints;
        var cpBar =
          '<div class="album-bar wr-cpbar" role="tablist" aria-label="Control point">' +
          cps
            .map(function (cp) {
              var n = (found[cp.id] || []).length;
              return (
                '<button type="button" data-cp="' + esc(cp.id) + '" aria-pressed="' + (cp.id === state.cp) + '"' +
                (state.q && !n ? ' class="is-empty"' : "") + ">CP" + esc(cp.id) +
                (state.q ? " (" + n + ")" : "") + "</button>"
              );
            })
            .join("") +
          "</div>";
        var cp = cps.find(function (c) { return c.id === state.cp; }) || cps[0];
        var sigs = found[cp.id] || [];
        var planned = cp.signals.some(function (s) { return s.planned; });
        var head =
          '<div class="wr-cp-head"><h2>Control point ' + esc(cp.id) + "</h2>" +
          '<span class="muted">' + esc(cp.area) + " · " + cp.signals.length + " signals</span></div>" +
          '<p class="muted wr-note">' +
          (planned
            ? "The November 2025 plan, under its working signal IDs. The lower deck has since been fitted with Digicon searchlights; their pins are under Signals."
            : "Each route lists the switch positions it needs and the aspect for each occupancy case, with the pin that lights it.") +
          " Lamp colour is read from the aspect: clear aspects green, approach and restricting yellow, stop red.</p>";
        if (!sigs.length) return cpBar + head + empty();
        return (
          cpBar + head +
          '<div class="wr-split-list">' +
          sigs
            .map(function (s) {
              var lamps = s.lamps || null;
              var top =
                '<header><h3>' + esc(s.signal) + "</h3>" +
                (s.mast ? '<span class="muted">' + esc(s.mast) + "</span>" : "") +
                (lamps
                  ? '<span class="wr-head-pins">' + lampRow({ lamps: lamps }) + "</span>"
                  : '<span class="muted wr-planned">' + (s.planned ? "planned ID" : "no pins in inventory") + "</span>") +
                "</header>";
              var routes = s.routes
                .map(function (r) {
                  var sw = (r.switches || [])
                    .map(function (w) {
                      return '<span class="wr-sw pos-' + esc(w.pos) + '">' + esc(w.switch.replace(/^Switch /, "")) + " " + esc(w.pos) + "</span>";
                    })
                    .join("");
                  var asp = r.aspects
                    .map(function (a) {
                      var c = aspectLamp(a.aspect);
                      var pin = lamps && c && lamps[c] ? '<span class="wr-asp-pin">' + esc(pinPart(lamps[c])) + "</span>" : "";
                      return (
                        '<li class="wr-asp">' + (c ? chip(c) : "") +
                        '<span class="wr-asp-text"><strong>' + esc(a.aspect || "—") + "</strong>" +
                        "<small>" + esc(whenText(a, r)) + "</small></span>" + pin + "</li>"
                      );
                    })
                    .join("");
                  return (
                    '<div class="wr-route"><div class="wr-route-name">' +
                    esc(r.from || "") + " <span aria-hidden=\"true\">→</span> " + esc(r.to || "") +
                    (sw ? '<span class="wr-sws">' + sw + "</span>" : "") + "</div>" +
                    '<ul class="wr-asps">' + asp + "</ul></div>"
                  );
                })
                .join("");
              return '<article class="wr-split card">' + top + routes + "</article>";
            })
            .join("") +
          "</div>"
        );
      }

      function renderTurnouts(list) {
        if (!list.length) return empty();
        return (
          '<div class="wr-table-wrap"><table class="wr-table wr-stack">' +
          "<thead><tr><th>Switch</th><th>Node</th><th>Motor N</th><th>Motor R</th><th>Button</th><th>Position N</th><th>Position R</th><th>Signals</th></tr></thead><tbody>" +
          list
            .map(function (t) {
              var sigs = [];
              [["entry", "entry"], ["normal", "normal"], ["reverse", "reverse"]].forEach(function (k) {
                var s = (t.signals || {})[k[0]];
                if (s) sigs.push('<span class="wr-nowrap">' + searchLink(s, "signals") + ' <small class="muted">' + k[1] + "</small></span>");
              });
              return (
                "<tr><th scope=\"row\">" + esc(t.turnout) +
                (t.elements && t.elements !== t.turnout ? '<small class="muted wr-sub">' + esc(t.elements) + "</small>" : "") +
                (t.area ? '<small class="muted wr-sub">' + esc(t.area) + "</small>" : "") + "</th>" +
                '<td data-label="Node">' + nodeLink(t.node) + "</td>" +
                '<td data-label="Motor N">' + portLink(t.motorN) + '</td><td data-label="Motor R">' + portLink(t.motorR) + "</td>" +
                '<td data-label="Button">' + portLink(t.button) + '</td><td data-label="Position N">' + portLink(t.fbN) +
                '</td><td data-label="Position R">' + portLink(t.fbR) + "</td>" +
                '<td data-label="Signals" class="wr-span">' + (sigs.join(" ") || '<span class="muted">—</span>') + "</td></tr>"
              );
            })
            .join("") +
          "</tbody></table></div>"
        );
      }

      function renderBlocks(list) {
        if (!list.length) return empty();
        return (
          '<div class="wr-table-wrap"><table class="wr-table wr-stack">' +
          '<thead><tr><th>Block</th><th>Detector</th><th>Area</th><th>District</th><th class="wr-wide">Track</th><th class="wr-wide">Notes</th></tr></thead><tbody>' +
          list
            .map(function (b) {
              return (
                "<tr><th scope=\"row\">" + esc(b.block || "—") + "</th>" +
                '<td data-label="Detector"><a href="' + esc(link({ node: b.node })) + '" data-node="' + esc(b.node) + '">' + esc(b.port) + "</a></td>" +
                '<td data-label="Area">' + esc(b.area || "") + '</td><td data-label="District">' + esc(b.district || "") + "</td>" +
                '<td class="wr-wide">' + esc(b.track || "") + '</td><td class="wr-wide muted">' + esc(b.note || "") + "</td></tr>"
              );
            })
            .join("") +
          "</tbody></table></div>"
        );
      }

      function empty() {
        return '<p class="muted wr-empty">Nothing here matches “' + esc(state.q) + "”. Try another tab, or a shorter search.</p>";
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

      function fullBoard(b, isInput) {
        var cells = [];
        for (var i = 1; i <= 8; i++) {
          var p = b.pins.find(function (x) { return x.pin === i; }) || { pin: i, kind: "spare", port: "" };
          cells.push(
            '<button type="button" class="wr-pin ' + cellClass(p).replace("wr-cell ", "") +
            (p.port && p.port === state.pin ? " is-sel" : "") + '" data-port="' + esc(p.port) + '">' +
            '<span class="wr-pin-top"><span class="wr-pin-n">' + i + "</span>" +
            (p.color ? chip(p.color) : "") + "</span>" +
            '<span class="wr-pin-dev">' + esc(shortDevice(p)) + "</span></button>"
          );
        }
        var sel = b.pins.find(function (x) { return x.port === state.pin; });
        return (
          '<section class="wr-board" data-board="' + esc(b.board) + '">' +
          "<h3>" + esc(b.board) + ' <small class="muted">' +
          esc(isInput ? "DNIN8 inputs" : "DNOU8 outputs · " + (b.rail || "")) +
          (b.place ? " · " + esc(b.place) : "") + "</small></h3>" +
          '<div class="wr-pins">' + cells.join("") + "</div>" +
          '<p class="wr-detail">' + (sel ? pinDetail(sel) : "") + "</p></section>"
        );
      }

      function openNode(nid) {
        var n = nodeById[nid];
        if (!n) return;
        state.node = nid;
        syncUrl();
        dlgTitle.innerHTML =
          esc(n.id) + ' <small class="muted">' +
          esc([n.type === "Main" ? "main node" : n.type === "DCC" ? "DCC" : "radio " + n.address, n.location]
            .concat(n.legacy ? ["old label " + n.legacy] : []).join(" · ")) +
          "</small>";
        var html = (n.outputs || []).length || (n.inputs || []).length
          ? '<p class="muted wr-hint">Tap a pin to see what it is wired to.</p>'
          : "";
        (n.outputs || []).forEach(function (b) { html += fullBoard(b, false); });
        (n.inputs || []).forEach(function (b) { html += fullBoard(b, true); });
        if ((n.detectors || []).length) {
          html +=
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
            "</ul></section>";
        }
        if (!(n.outputs || []).length && !(n.inputs || []).length && !(n.detectors || []).length) html = '<p class="muted">This node has no output or input boards in the inventory.</p>';
        dlgBody.innerHTML = html;
        if (!dlg.open) {
          if (dlg.showModal) dlg.showModal();
          else dlg.setAttribute("open", "");
        }
        var selEl = dlgBody.querySelector(".is-sel");
        if (selEl && selEl.scrollIntoView) selEl.scrollIntoView({ block: "center" });
        else dlgBody.scrollTop = 0;
      }

      function closeNode() {
        state.node = "";
        state.pin = "";
        syncUrl();
        if (dlg.open) {
          if (dlg.close) dlg.close();
          else dlg.removeAttribute("open");
        }
      }

      dlgBody.addEventListener("click", function (e) {
        var btn = e.target.closest(".wr-pin");
        if (btn) {
          var port = btn.getAttribute("data-port");
          state.pin = port || "";
          syncUrl();
          var sec = btn.closest(".wr-board");
          sec.querySelectorAll(".wr-pin").forEach(function (b) { b.classList.toggle("is-sel", b === btn); });
          sec.querySelector(".wr-detail").innerHTML = pinDetail(pinByPort[port] || { port: port || "", kind: "spare" });
          return;
        }
        var a = e.target.closest("a[data-q]");
        if (a) {
          e.preventDefault();
          closeNode();
          go(a.getAttribute("data-tab"), a.getAttribute("data-q"));
        }
      });
      document.getElementById("wr-close").addEventListener("click", closeNode);
      dlg.addEventListener("cancel", function (e) {
        e.preventDefault();
        closeNode();
      });
      dlg.addEventListener("click", function (e) {
        if (e.target === dlg) closeNode();
      });

      // —— Render ——
      function renderTabs(res) {
        var counts = {
          nodes: res.nodes.length,
          signals: res.signals.length,
          splits: res.splitCount,
          turnouts: res.turnouts.length,
          blocks: res.blocks.length,
        };
        tabBar.innerHTML = TABS.map(function (t) {
          return (
            '<button type="button" role="tab" data-tab="' + t.id + '" aria-selected="' + (t.id === state.tab) +
            '" aria-pressed="' + (t.id === state.tab) + '"' + (state.q && !counts[t.id] ? ' class="is-empty"' : "") + ">" +
            t.label + ' <span class="wr-count">' + counts[t.id] + "</span></button>"
          );
        }).join("");
      }

      function render() {
        var res = matches();
        // A search for one control point's signal lands on that CP.
        if (state.tab === "splits" && state.q && !(res.splits[state.cp] || []).length) {
          var first = spl.controlPoints.find(function (c) { return (res.splits[c.id] || []).length; });
          if (first) state.cp = first.id;
        }
        renderTabs(res);
        var html;
        if (state.tab === "signals") html = renderSignals(res.signals);
        else if (state.tab === "splits") html = renderSplits(res.splits);
        else if (state.tab === "turnouts") html = renderTurnouts(res.turnouts);
        else if (state.tab === "blocks") html = renderBlocks(res.blocks);
        else html = renderNodes(res.nodes);
        out.innerHTML = html;
        out.className = "wr-view view-" + state.tab;
        syncUrl();
      }

      function go(tab, q) {
        state.tab = tab;
        state.q = q == null ? state.q : q;
        qInput.value = state.q;
        render();
        window.scrollTo({ top: 0 });
      }

      tabBar.addEventListener("click", function (e) {
        var b = e.target.closest("button[data-tab]");
        if (b) go(b.getAttribute("data-tab"));
      });
      out.addEventListener("click", function (e) {
        var cpb = e.target.closest("button[data-cp]");
        if (cpb) {
          state.cp = cpb.getAttribute("data-cp");
          render();
          return;
        }
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
      qInput.addEventListener("input", function () {
        clearTimeout(timer);
        timer = setTimeout(function () {
          state.q = qInput.value.trim();
          render();
        }, 120);
      });
      // Enter on a node or pin id ("C4", "C4-OU2-7") opens that node's port map.
      qInput.addEventListener("keydown", function (e) {
        if (e.key !== "Enter") return;
        var v = qInput.value.trim();
        var m = v.toUpperCase().match(/^([A-Z]+\d+)-((?:OU|IN)\d+-\d+)$/);
        if (m && nodeById[m[1]]) {
          state.pin = m[1] + "-" + m[2];
          openNode(m[1]);
        } else if (nodeById[v.toUpperCase()]) {
          state.pin = "";
          openNode(v.toUpperCase());
        }
      });

      render();
      if (state.node && nodeById[state.node]) openNode(state.node);
    },
  };
})();
