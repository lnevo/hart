/* The pipeline map viewer's filters, search, trail and status line as pure functions, no page state:
   build_pipeline_map.py inlines this file after pipeline_map_helpers.js, in the same script; under node it exports
   them for the unit tests (tools/audit/tests/test_pipeline_map_facets.py).

   A filter is a set of ticked values per facet: lane, kind, status, step type and writers on the boxes, side on the
   links. Values within a facet are joined with OR, facets with AND, and a facet with nothing ticked does not filter.
   Status is also what is drawn: with nothing ticked only live boxes are drawn (parked and retired hidden, as the
   page has always opened); ticking parked draws them too. */
"use strict";

// the box facets in the rail's order, with the address key each one is kept under
const BOX_FACETS = ["lane", "kind", "status", "step", "writers"];
const FACET_KEYS = { lane: "lanes", kind: "kind", status: "status", step: "step", writers: "writers", side: "side" };
const STATUS_VALUES = ["live", "parked", "retired"];
const STEP_VALUES = ["stamped", "guard", "none"];
const WRITER_VALUES = ["one", "many", "none"];

function emptyFacets() {
  return { lane: new Set(), kind: new Set(), status: new Set(), step: new Set(), writers: new Set(), side: new Set() };
}

/* A box's values for each box facet (each a list: a box run as a stamped step and a guard is both). writers is
   only on outputs (n.w, the writer count the build worked out); other boxes have none, so a writers filter leaves them
   out. */
function boxValues(n) {
  const step = n.eff && n.eff.length ? [...new Set(n.eff.map(e => (e.m === "guard" ? "guard" : "stamped")))] : ["none"];
  const writers = n.w ? [n.w.n === 0 ? "none" : n.w.n === 1 ? "one" : "many"] : [];
  return { lane: [n.domain], kind: [n.kind], status: [n.status || "live"], step, writers };
}
const edgeSide = e => e.side || "data";

/* Whether a box's values (boxValues) pass the facets in keys (all box facets by default), skip left out. */
function boxMatches(vals, f, keys = BOX_FACETS, skip = null) {
  return keys.every(k => k === skip || !f[k].size || vals[k].some(v => f[k].has(v)));
}
const facetsOn = f => Object.values(f).some(s => s.size > 0);

/* The statuses drawn: live only while no status is ticked; with Hide the rest, the ticked ones; otherwise live and
   the ticked ones (a box drawn but not ticked is faded). */
function drawnStatus(f, hide) {
  if (!f.status.size) return new Set(["live"]);
  return hide ? new Set(f.status) : new Set(["live", ...f.status]);
}

/* The rail's counts: for each box facet and value, [all, n]. all counts the boxes with that value among those whose
   status is drawn (for the status facet, every box); n those of them that also pass the other facets. */
function facetCounts(nodes, f, hide) {
  const drawn = drawnStatus(f, hide), out = {};
  BOX_FACETS.forEach(k => (out[k] = {}));
  for (const n of nodes) {
    const vals = boxValues(n), shown = drawn.has(vals.status[0]);
    for (const k of BOX_FACETS) {
      if (k !== "status" && !shown) continue;
      const pass = boxMatches(vals, f, BOX_FACETS, k);
      for (const v of vals[k]) {
        const c = (out[k][v] ||= [0, 0]);
        c[0]++;
        if (pass) c[1]++;
      }
    }
  }
  return out;
}

/* The link side counts, [all, n] per side ("data" for a link with none): n counts the links whose two ends pass the
   box facets (pass(id)). */
function sideCounts(edges, pass) {
  const out = {};
  for (const e of edges) {
    const c = (out[edgeSide(e)] ||= [0, 0]);
    c[0]++;
    if (pass(e.from) && pass(e.to)) c[1]++;
  }
  return out;
}

/* The filters into the address (URLSearchParams h): one key per facet with values (FACET_KEYS), and rest=hide. */
function writeFacets(h, f, hide) {
  for (const k in FACET_KEYS) if (f[k] && f[k].size) h.set(FACET_KEYS[k], [...f[k]].join(","));
  if (hide) h.set("rest", "hide");
}

/* The filters from an address (URLSearchParams h); known lists each facet's values, and anything else is dropped.
   Older links still load: hidekind= (the kinds left out, bridged over) becomes the kinds kept, with Hide the rest so
   the links run through as they did; show=parked,retired, hide=parked (shown unless named) and the older dir= or
   depth= file links (every status shown) tick those statuses beside live. Returns {f, hide}. */
function readFacets(h, known) {
  const f = emptyFacets(), list = key => (h.get(key) || "").split(",").filter(Boolean);
  for (const k in FACET_KEYS) list(FACET_KEYS[k]).forEach(v => { if (known[k].includes(v)) f[k].add(v); });
  let hide = h.get("rest") === "hide";
  const hidden = list("hidekind").filter(v => known.kind.includes(v));
  if (hidden.length && !f.kind.size) { known.kind.filter(v => !hidden.includes(v)).forEach(v => f.kind.add(v)); hide = true; }
  if (!f.status.size) {
    const old = h.get("hide");
    let more = [];
    if (old !== null) more = ["parked", "retired"].filter(s => !old.includes(s));
    else if (h.get("show") !== null) more = list("show").filter(s => s === "parked" || s === "retired");
    else if (h.get("dir") !== null || h.get("depth") !== null) more = ["parked", "retired"];
    if (more.length) ["live", ...more].forEach(s => f.status.add(s));
  }
  return { f, hide };
}

/* Address keys that leave the lane overview as it is: the overlay, pointer settings and the Steps slider (with the
   sharer's box size), which apply once a map is drawn. An address with only these opens on the overview. */
const OV_KEYS = ["eff", "hover", "near", "steps", "cap"];
const isOverviewHash = h => [...h.keys()].every(k => OV_KEYS.includes(k));

/* Whether an address's node= can be selected: a box (isBox), a folder box or a closed lane's box. */
const selectableId = (id, isBox) => !!id && (isBox(id) || id.startsWith("folder:") || id.startsWith("lane:"));

/* A box's slowest timed step (eff entries, t: its timings; time(t) the usual run's seconds), or null when none is
   timed: the List sorts by it and shows its times. */
function slowestStep(eff, time) {
  let best = null, most = -Infinity;
  for (const e of eff || []) { const s = e.t ? time(e.t) : null; if (s !== null && s > most) { most = s; best = e; } }
  return best;
}

/* The values a facet keeps after "only" beside v (set: its ticked values): v alone, or none when v alone was ticked. */
function onlyValue(set, v) { return set.size === 1 && set.has(v) ? new Set() : new Set([v]); }

/* The status set with status s drawn (for a box the reader asked for): unchanged when it is drawn already. */
function withStatus(f, hide, s) {
  if (drawnStatus(f, hide).has(s)) return f.status;
  return new Set([...(f.status.size ? f.status : ["live"]), s]);
}

/* How well a box matches search text t (lower case, trimmed): 0 the label itself, 1 the label starts with it, 2 the
   label holds it, 3 the path or id holds it, 4 the description does; -1 no match. */
function searchRank(n, t) {
  if (!t) return -1;
  const label = n.label.toLowerCase();
  if (label === t) return 0;
  if (label.startsWith(t)) return 1;
  if (label.includes(t)) return 2;
  if ((n.path || "").toLowerCase().includes(t) || n.id.toLowerCase().includes(t)) return 3;
  if ((n.desc || "").toLowerCase().includes(t)) return 4;
  return -1;
}
/* The boxes that match text, best first: by searchRank, then live before parked and retired, then the shorter label,
   then by label. Returns their ids. */
function searchHits(nodes, text) {
  const t = String(text || "").trim().toLowerCase();
  if (!t) return [];
  const dead = n => (n.status && n.status !== "live" ? 1 : 0);
  return nodes.map(n => [searchRank(n, t), n]).filter(([r]) => r >= 0)
    .sort(([ra, a], [rb, b]) => ra - rb || dead(a) - dead(b) || a.label.length - b.label.length || a.label.localeCompare(b.label))
    .map(([, n]) => n.id);
}

/* The trail on the toolbar's second row, from where the view is: d is {overview, lanes (the open lanes), focus,
   focusLane (the focused box's lane)}, name(lane) a lane's label, label the focused box's. Each crumb is {label, to};
   to says where a click goes ({overview: true} or {lanes: [...]}), and is null on the last crumb, the view itself. */
function trail(d, name, label) {
  const top = { label: "All lanes", to: { overview: true } };
  if (d.overview) return [{ label: top.label, to: null }];
  const lanes = d.focus ? [d.focusLane] : d.lanes;  // a file's crumb sits under its own lane
  const middle = { label: lanes.length ? lanes.map(name).join(" + ") : "Whole map", to: lanes.length ? { lanes } : { whole: true } };
  if (!d.focus) return [top, { label: middle.label, to: null }];
  return [top, middle, { label, to: null }];
}
/* Where Esc goes from a trail: the crumb before the last, or null on the overview. */
function upFrom(crumbs) { return crumbs.length > 1 ? crumbs[crumbs.length - 2].to : null; }

/* The status line, one plain sentence: s is {boxes (drawn), liveOnly (only live statuses drawn), faded (drawn but
   not matching), hidden (left out by Hide the rest), parked, retired (not drawn because of their status), extra (more
   to say, such as "grouped by folder")}. */
function statusLine(s) {
  const out = [`Showing ${s.boxes} ${s.liveOnly ? "live " : ""}${s.boxes === 1 ? "box" : "boxes"}`];
  if (s.faded) out.push(`${s.faded} faded by the filters`);
  if (s.hidden) out.push(`${s.hidden} hidden by the filters`);
  const st = [s.parked && "parked", s.retired && "retired"].filter(Boolean);
  if (st.length) out.push(`${(s.parked || 0) + (s.retired || 0)} ${st.join(" or ")} hidden`);
  return out.join(", ") + (s.extra && s.extra.length ? `, ${s.extra.join(", ")}` : "");
}

/* An info panel list of boxes (items: [{id, ...}], kindOf(id) the box's kind, order the kinds in the legend's order),
   grouped by kind when it has more than max entries; returns [{kind, items}] (one group with kind null when short). */
function groupByKind(items, kindOf, order, max = 8) {
  if (items.length <= max) return [{ kind: null, items }];
  const by = new Map();
  for (const it of items) { const k = kindOf(it.id); if (!by.has(k)) by.set(k, []); by.get(k).push(it); }
  const rank = k => (order.includes(k) ? order.indexOf(k) : order.length);
  return [...by].sort(([a], [b]) => rank(a) - rank(b)).map(([kind, list]) => ({ kind, items: list }));
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { BOX_FACETS, FACET_KEYS, STATUS_VALUES, STEP_VALUES, WRITER_VALUES, emptyFacets, boxValues, edgeSide,
                     boxMatches, facetsOn, drawnStatus, facetCounts, sideCounts, writeFacets, readFacets, withStatus, onlyValue, OV_KEYS, isOverviewHash, selectableId, slowestStep,
                     searchRank, searchHits, trail, upFrom, statusLine, groupByKind };
}
