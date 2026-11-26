"""build_main_route.py [--check]

Write the `main_route` key of plan_generated.json's main_upper section from the main_upper rows of main_lines.csv
and the plan graph, and staging's main track and mileposts from its staging rows (see the end of this text).

The schematic marks as main track what lies on `main_route`, hop by hop. Written by hand, each hop named two plan part
numbers (T281, T311 ...), which change whenever the plan is exported again. Here the owner gives the two main lines
by what the railroad calls things, and this works the hops out:

    sheet,line,from,via,to,loop,double,count,notes

  sheet   the schematic sheet the line is on: staging or main_upper (one file for every level, a section per sheet);
  line    its name, once per sheet;
  from    the helix end the line starts at (its helix track's block id: block:39B-helix), or a switch number;
  via     switch numbers the line must pass, in order, where the shortest way would leave it (";" between them); the
          half of a crossover is its number and the block id of a track that meets it there (35@block:33A-35A);
  to      the switch the line ends at;
  loop    the switches of the turnback the line ends in, in order, ";" between them: the line runs from `to` round them
          and back to `to` (a balloon on one switch repeats `to`);
  double  switch pairs joined by two tracks that are both main ("223-225");
  count   yes on the lines the mileposts run along (staging only, see below), else blank;
  notes   free text.

Each stretch between two stops is the shortest way along the plan (centimetres plus one per track, as the plugin
counts) that does not cut across a crossover (the short track between the A and B halves of one crossover number,
131A and 131B), and stops when two ways tie. A loop's stretches that join neighbouring switches use that track, whatever its
length. A pair of switches the line crosses that has two tracks must be in `double`, so no choice between parallel
tracks is made silently. Every hop is written [a, b, "direct"], marking every track between the two, in the order the
line runs; switches are named by their number, so the hops do not depend on the plan's part numbers.

--check regenerates in memory and exits 1 if a file differs.

Staging (the rows whose sheet is staging). Staging's drawings take no main_route (it
would turn on the direction letters of a route), so its lines write two other things in plan_generated.json's staging
section (name_main, the runs of the tracks on a main line: "1A-23A", hartlib.track_names.run_of). The name store
gives each of them an entry flagged "main" in the plugin's `name` edit, and no other track is flagged; a helix end and
the short link between the halves of a crossover are left out, as the plugin marks them itself. A line with `count` yes is the way the mileposts run: milepost_route is its stops, one hop from each to the
next (the origin, Switch 1 at MP 5.7, stays in milepost_origin).
"""
from __future__ import annotations

import argparse
import heapq
import json
import os
import re
import sys
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA, GRAPHS and the pinned plugin
from hartlib import hand_lists, layer_files, track_names  # noqa: E402  (publish_draft put tools/hartlib/src on the path)

LINES = pd.DATA / hand_lists.MAIN_LINES_NAME
GRAPH = pd.GRAPHS / "main.json"
COLUMNS = hand_lists.MAIN_LINE_COLUMNS
SHEETS = hand_lists.SHEETS
STAGING_GRAPH = pd.GRAPHS / "staging.json"
TIE = 1e-6          # centimetres: two ways this close are a tie


class RouteError(ValueError):
    """The main lines cannot be worked out from the plan; the message says why."""


# main_lines.csv's reader is hartlib.hand_lists'; the names stay here
split = hand_lists.split
STOP_CELLS = hand_lists.STOP_CELLS
TRACK_PREFIX = hand_lists.TRACK_PREFIX


def resolve_stop(token: str, names, where: str) -> str:
    """hartlib.hand_lists.resolve_stop (a stop's block ids by the name store's names), its error a RouteError."""
    try:
        return hand_lists.resolve_stop(token, names, where)
    except hand_lists.HandListError as exc:
        raise RouteError(str(exc)) from exc


def read_lines(sheet: str, path: Path = LINES, names=None) -> list[dict]:
    """The main lines of one sheet (hartlib.hand_lists.read_main_lines: the whole file checked, each stop's block
    ids given back by name; `names` the name store's, default the repo's), its error a RouteError."""
    try:
        return hand_lists.read_main_lines(sheet, path, names)
    except hand_lists.HandListError as exc:
        raise RouteError(str(exc)) from exc


HALF = re.compile(r"(\d+)([AB])")


class Plan:
    """The prepared graph (the plugin's edits applied, no main_route) and what the route needs of it."""

    def __init__(self, g: dict, by_label: Callable[[dict, str], str]):
        """`by_label(g, ref)` gives the node a route stop names and raises RouteError when none or several do."""
        self.g, self.by_label = g, by_label
        self.adj, self.run = defaultdict(list), defaultdict(list)
        for e in g["edges"]:
            for adj in (self.adj, self.run) if not self.crossing(e) else (self.adj,):
                adj[e["u"]].append((e["v"], e))
                if e["u"] != e["v"]:
                    adj[e["v"]].append((e["u"], e))

    def crossing(self, e: dict) -> bool:
        """The short track between the two halves of one crossover (131A to 131B): it is no part of a main line."""
        halves = [HALF.fullmatch(self.g["nodes"][n].get("label") or "") for n in (e["u"], e["v"])]
        return all(halves) and halves[0].group(1) == halves[1].group(1) and {h.group(2) for h in halves} == {"A", "B"}

    def node(self, ref: str) -> str:
        try:
            return self.by_label(self.g, ref)
        except RouteError as exc:    # none or several junctions answer to it
            raise RouteError(f"main line stop {ref!r}: {exc}") from exc

    def name(self, n: str) -> str:
        """What the hop calls this node: its switch number or helix name, or for the half of a crossover (two junctions
        of one number) "number@track", by a track named at it; it must find only this node again."""
        d = self.g["nodes"][n]
        label = d.get("label")
        if d["kind"] == "end":      # a helix end is called by its track's name
            label = next((e["names"][0] for e in self.g["edges"] if n in (e["u"], e["v"]) and e["names"]), None)
        tries = [label] if label else []
        if d["kind"] != "end" and label:
            tries += [f"{label}@{t}" for e in self.g["edges"] if n in (e["u"], e["v"]) for t in e["names"] if t]
        for ref in tries:
            try:
                if self.node(ref) == n:
                    return ref
            except RouteError:
                continue
        raise RouteError(f"junction {n} has no unique name to write the route with (label {label!r})")

    def between(self, a: str, b: str) -> list[dict]:
        return [e for v, e in self.adj[a] if v == b and (a != b or e["u"] == e["v"])]

    def shortest(self, a: str, b: str, double: frozenset | set = frozenset()) -> list[tuple[str, dict, str]]:
        """[(from, edge, to)] along the one shortest way; stops on a tie or when there is none. A tie only between
        parallel tracks joining one pair of switches named in `double` (both main) is no choice: either way runs
        through the same switches, and line_hops marks both tracks."""
        if a == b:
            return []
        dist, prev, heap = {a: 0.0}, {}, [(0.0, a)]
        while heap:
            d, n = heapq.heappop(heap)
            if d > dist[n]:
                continue
            for m, e in self.run[n]:
                nd = d + e["cm"] + 1
                if nd < dist.get(m, 1e18) - TIE:
                    dist[m], prev[m] = nd, [(n, e)]
                    heapq.heappush(heap, (nd, m))
                elif abs(nd - dist.get(m, 1e18)) <= TIE and (n, e) not in prev.get(m, []):
                    prev[m].append((n, e))
        if b not in dist:
            raise RouteError(f"no track joins {self.name(a)} and {self.name(b)}")
        ways = self._ways(prev, a, b)
        if len(ways) > 1 and self._parallel_only(ways, double):
            return ways[0]
        if len(ways) > 1:
            raise RouteError(f"{self.name(a)} to {self.name(b)} has {len(ways)} equally short ways; name a switch "
                             "between them in `via`")
        return ways[0]

    def _parallel_only(self, ways, double) -> bool:
        """Whether the tied `ways` pass the same switches in the same order and differ only on hops between a pair
        named in `double`."""
        stops = {tuple([w[0][0], *(t for _f, _e, t in w)]) for w in ways}
        if len(stops) != 1:
            return False
        for hops in zip(*ways):
            if len({id(e) for _f, e, _t in hops}) > 1 and \
                    frozenset(self.name(x) for x in (hops[0][0], hops[0][2])) not in double:
                return False
        return True

    def _ways(self, prev, a, b, limit=4):
        if b == a:
            return [[]]
        out = []
        for n, e in prev[b]:
            for way in self._ways(prev, a, n, limit):
                out.append(way + [(n, e, b)])
                if len(out) >= limit:
                    return out
        return out


def line_hops(plan: Plan, row: dict, exact: bool = False) -> list[tuple[str, str, list[dict]]]:
    """[(from node, to node, [edges marked between them])] for one main line, in running order. `exact`: the line
    names every junction it passes, each next to the one before (staging's loop has shorter ways round than the main
    track), so no way is worked out and a stop with no track to the next stops the build."""
    stops = [row["from"].strip(), *split(row["via"]), row["to"].strip()]
    double = {frozenset(p.split("-")) for p in split(row["double"])}
    steps: list[tuple[str, dict, str]] = []
    nodes = [plan.node(s) for s in stops]
    for a, b in zip(nodes, nodes[1:]):
        if not exact:
            steps += plan.shortest(a, b, double)
            continue
        near = plan.between(a, b)
        if not near:
            raise RouteError(f"{row['line']}: no track joins {plan.name(a)} and {plan.name(b)}; name the junctions "
                             "between them")
        steps += [(a, e, b) for e in near]       # two or more: the hops below stop unless `double` names the pair
    loop = [plan.node(s) for s in split(row["loop"])]
    if loop:
        ring = [nodes[-1], *loop, nodes[-1]]
        for a, b in zip(ring, ring[1:]):
            near = plan.between(a, b)
            steps += [(a, e, b) for e in near[:1]] if near else plan.shortest(a, b)
    hops, used = [], {}
    for a, e, b in steps:
        key = (a, b)
        if key in used:
            continue
        both = plan.between(a, b)
        if len(both) > 1:
            pair = frozenset(plan.name(x) for x in (a, b))
            if pair not in double:
                raise RouteError(f"{row['line']}: {plan.name(a)} and {plan.name(b)} are joined by {len(both)} tracks; "
                                 f"say in `double` ({plan.name(a)}-{plan.name(b)}) that both are main")
            double.discard(pair)
        elif frozenset(plan.name(x) for x in (a, b)) in double:
            raise RouteError(f"{row['line']}: `double` names {plan.name(a)}-{plan.name(b)}, which has one track")
        used[key] = used[(b, a)] = True
        hops.append((a, b, both))
    if double:
        raise RouteError(f"{row['line']}: `double` names {', '.join('-'.join(sorted(p)) for p in double)}, "
                         "which the line does not cross")
    return hops


def route(plan: Plan, rows: list[dict]) -> list[list[str]]:
    hops = []
    for row in rows:
        hops += [[plan.name(a), plan.name(b), "direct"] for a, b, _ in line_hops(plan, row)]
    return hops


def prepared(overrides: dict, layer: str = "main_upper", graph: Path = GRAPH) -> tuple[dict, Callable[[dict, str], str]]:
    """(the plugin's graph with the overrides applied and no main_route, node_ref: how a route names a junction,
    its SchematicError a RouteError)."""
    import build_layout_le as bl
    sheet, _le, _core = bl.plugin()
    from schematic import edits, layers   # the plugin's package: bl.plugin() has put it on the path
    from schematic.core import SchematicError

    def node_ref(g: dict, ref: str) -> str:
        try:
            return edits.node_ref(g, ref)
        except SchematicError as exc:
            raise RouteError(str(exc)) from exc
    # the hand preferences name tracks by block ID: the plugin takes the merged view's, which gives their names
    prefs = layer_files.merged(pd.DATA, "preferences").get(layer, {})
    opts = dict(sheet.DEFAULTS, **layers.merge(layers.load(layer, pd.DATA, preferences=False), prefs))
    # the plan with the name store's track names but without the main flags this script writes (name_main), so a
    # stale or old-form name_main never stops the script that rewrites it
    opts.update({k: v for k, v in layer_files.merged(pd.DATA, main=False)[layer].items() if not k.startswith("_")})
    opts.pop("main_route", None)
    g = sheet.prepare(json.loads(graph.read_text()), opts, set())
    return g, node_ref


def generated_main_upper(hops: list) -> dict:
    """The keys of plan_generated.json's main_upper section this writes."""
    return {"main_route": hops}


def line_edges(plan: Plan, rows: list[dict]) -> set[str]:
    """The ids of every track on any of staging's lines (each names its junctions: line_hops exact)."""
    return {e["id"] for row in rows for _a, _b, edges in line_hops(plan, row, exact=True) for e in edges}


def milepost_route(plan: Plan, rows: list[dict]) -> list[list[str]]:
    """One hop from each stop to the next of every line marked `count`; line_edges has checked that a track joins them.
    A hop over a declared double track stops the build: the plugin would count along either track, not the one the
    line means."""
    hops = []
    for row in rows:
        if row["count"].strip() != "yes":
            continue
        stops = [row["from"].strip(), *split(row["via"]), row["to"].strip()]
        for a, b in zip(stops, stops[1:]):
            if len(plan.between(plan.node(a), plan.node(b))) > 1:
                raise RouteError(f"{row['line']}: the mileposts would count from {a} to {b} over a double track; "
                                 "name a junction between them, or leave count blank")
            hops.append([a, b])
    return hops


def staging_keys(overrides: dict, plan: Plan, rows: list[dict]) -> dict:
    """The keys of plan_generated.json's staging section this writes: name_main (the runs of the tracks on a main
    line, hartlib.track_names.edge_run: "1A-23A", which the name store's `name` edit flags main) and milepost_route,
    from the lines. A crossover's link between its halves and a helix track are left out: the plugin marks those
    main itself. `overrides` (the hand section) is not read: the plan graph names every junction."""
    g = plan.g
    N = g["nodes"]

    def owned_by_plugin(e):         # a crossover's link between its halves, or a helix end: marked main by the plugin
        la, lb = (N[n].get("label") for n in (e["u"], e["v"]))
        return (la and la == lb) or any(N[n]["kind"] == "end" and N[n].get("sub") == "helix" for n in (e["u"], e["v"]))

    main_ids = line_edges(plan, rows)     # each run by the name store's end keys (track_names.edge_run, as plan_runs)
    flagged = sorted({track_names.edge_run(N, e) for e in g["edges"] if e["id"] in main_ids and not owned_by_plugin(e)})
    return {layer_files.NAME_MAIN: flagged, "milepost_route": milepost_route(plan, rows),
            "_main_lines": ("name_main (the runs of the tracks on a main line, which the name store's `name` edit "
                            "flags main: hartlib.track_names) and milepost_route are written by "
                            "tools/schematic/build_main_route.py from the staging rows of main_lines.csv; edit that "
                            "file, not these.")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if a main route or main line file is stale")
    args = ap.parse_args(argv)
    import build_layout_le as bl
    try:
        overrides = layer_files.read("plan_overrides", "main_upper", pd.DATA)
        g, by_label = prepared(overrides)
        hops = route(Plan(g, by_label), read_lines("main_upper"))
        st = layer_files.read("plan_overrides", "staging", pd.DATA)
        sg, sby = prepared(st, "staging", STAGING_GRAPH)
        updates = {"main_upper": generated_main_upper(hops),
                   "staging": staging_keys(st, Plan(sg, sby), read_lines("staging"))}
        want = layer_files.generated_texts(updates, pd.DATA)
    except bl.BuildError as exc:      # the plugin is not checked out
        if not args.check:
            raise
        print(f"SKIPPED main route check: {exc}")
        return 1 if os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0
    except (RouteError, layer_files.LayerFileError) as exc:
        print(f"build_main_route.py: {exc}", file=sys.stderr)
        return 2
    # which section differs, to say what is stale: main_upper's main_route, staging's main flags and milepost_route
    what = {"main_upper": f"main_route ({len(hops)} hops)", "staging": "main flags and milepost_route"}
    stale = [what[sheet] for sheet, keys in updates.items()
             if any(layer_files.read(layer_files.GENERATED, sheet, pd.DATA).get(k) != v for k, v in keys.items())]
    stale_files = [p for p, text in want.items() if p.read_text(encoding="utf-8") != text]
    if args.check:
        for p in stale_files:
            print(f"{p.name} {', '.join(stale) or 'formatting'} is stale: run python3 tools/schematic/build_main_route.py",
                  file=sys.stderr)
        if not stale_files:
            print("main route and staging main lines are current")
        return 1 if stale_files else 0
    for p in stale_files:
        p.write_text(want[p], encoding="utf-8")
        print(f"wrote {', '.join(stale) or 'its formatting'} to {p.name}")
    if not stale_files:
        print("main route and staging main lines are current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
