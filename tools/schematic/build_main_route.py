"""build_main_route.py [--check]

Write the `main_route` key of main_upper.plan_overrides.json from the main_upper rows of main_lines.csv and the plan
graph, and staging's main track and mileposts from its staging rows (see the end of this text).

The schematic marks as main track what lies on `main_route`, hop by hop. Written by hand, each hop named two plan part
numbers (T281, T311 ...), which change whenever the plan is exported again. Here the owner gives the two main lines
by what the railroad calls things, and this works the hops out:

    sheet,line,from,via,to,loop,double,count,notes

  sheet   the schematic sheet the line is on: staging or main_upper (one file for every level, a section per sheet);
  line    its name, once per sheet;
  from    the helix end the line starts at (its name, McKees Rocks), or a switch number;
  via     switch numbers the line must pass, in order, where the shortest way would leave it (";" between them);
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
would turn on the direction letters of a route), so its lines write two other things in staging.plan_overrides.json.
Each track on a line gets "main" in the `name` edit and every other track in it loses it; a track on a line that the
edit does not name must be a helix end or the short link between the halves of a crossover, which the plugin marks
itself. A line with `count` yes is the way the mileposts run: milepost_route is its stops, one hop from each to the
next (the origin, Switch 1 at MP 5.7, stays in milepost_origin).
"""
from __future__ import annotations

import argparse
import csv
import heapq
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA, GRAPHS and the pinned plugin

OVERRIDES = pd.DATA / "main_upper.plan_overrides.json"
LINES = pd.DATA / "main_lines.csv"
GRAPH = pd.GRAPHS / "main.json"
COLUMNS = ["sheet", "line", "from", "via", "to", "loop", "double", "count", "notes"]
SHEETS = ("staging", "main_upper")
STAGING_OVERRIDES = pd.DATA / "staging.plan_overrides.json"
STAGING_GRAPH = pd.GRAPHS / "staging.json"
TIE = 1e-6          # centimetres: two ways this close are a tie


class RouteError(ValueError):
    """The main lines cannot be worked out from the plan; the message says why."""


def split(cell: str) -> list[str]:
    return [p.strip() for p in cell.split(";") if p.strip()]


def read_lines(sheet: str, path: Path = LINES) -> list[dict]:
    """The main lines of one sheet. The whole file is checked first: its columns, a known sheet on every row, a line
    name used once per sheet, from and to given, count yes or blank and only on staging (the main and upper mileposts
    follow main_route), loop and double only on main_upper (staging_text reads neither); the sheet asked for must have a line."""
    if sheet not in SHEETS:
        raise RouteError(f"unknown sheet {sheet!r}: the sheets are {', '.join(SHEETS)}")
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != COLUMNS:
            raise RouteError(f"{path.name}: expected the columns {', '.join(COLUMNS)}, got {reader.fieldnames}")
        rows = list(reader)
    seen = set()
    for n, r in enumerate(rows, 2):
        if None in r.values() or None in r:
            raise RouteError(f"{path.name} line {n}: expected {len(COLUMNS)} cells ({', '.join(COLUMNS)})")
        r["sheet"] = r["sheet"].strip()
        if r["sheet"] not in SHEETS:
            raise RouteError(f"{path.name} line {n}: sheet {r['sheet']!r} is not one of {', '.join(SHEETS)}")
        if not r["line"].strip() or (r["sheet"], r["line"]) in seen:
            raise RouteError(f"{path.name} line {n}: line name {r['line']!r} is empty or repeated on sheet {r['sheet']}")
        seen.add((r["sheet"], r["line"]))
        if not r["from"].strip() or not r["to"].strip():
            raise RouteError(f"{path.name} line {n} ({r['line']}): from and to are both needed")
        if r["count"].strip() not in ("", "yes"):
            raise RouteError(f"{path.name} line {n} ({r['line']}): count is yes or blank, not {r['count']!r}")
        if r["count"].strip() and r["sheet"] != "staging":
            raise RouteError(f"{path.name} line {n} ({r['line']}): count is only read on the staging sheet; the "
                             f"{r['sheet']} mileposts follow main_route")
        if r["sheet"] == "staging" and (r["loop"].strip() or r["double"].strip()):
            raise RouteError(f"{path.name} line {n} ({r['line']}): loop and double are only read on the main_upper "
                             "sheet; a staging line names its junctions in via")
    mine = [r for r in rows if r["sheet"] == sheet]
    if not mine:
        raise RouteError(f"{path.name} has no main line on sheet {sheet}")
    return mine


HALF = re.compile(r"(\d+)([AB])")


class Plan:
    """The prepared graph (the plugin's edits applied, no main_route) and what the route needs of it."""

    def __init__(self, g: dict, by_label):
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
        except Exception as exc:     # SchematicError: none or several junctions answer to it
            raise RouteError(f"main line stop {ref!r}: {exc}") from None

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


def prepared(overrides: dict, layer: str = "main_upper", graph: Path = GRAPH):
    """(the plugin's graph with the overrides applied and no main_route, node_ref: how a route names a junction)."""
    import build_layout_le as bl
    sheet, _le, _core = bl.plugin()
    from schematic import edits   # the plugin's package: bl.plugin() has put it on the path
    opts = dict(sheet.options(layer, pd.DATA))
    opts.pop("main_route", None)
    g = sheet.prepare(json.loads(graph.read_text()), opts, set())
    return g, edits.node_ref


def overrides_text(overrides: dict, hops: list) -> str:
    over = dict(overrides)
    over["main_route"] = hops
    return json.dumps(over, indent=1, ensure_ascii=False) + "\n"


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


def staging_text(overrides: dict, plan: Plan, rows: list[dict]) -> str:
    """staging.plan_overrides.json with its `name` edit's main flags and its milepost_route from the lines."""
    from schematic import edits
    g = plan.g
    N = g["nodes"]

    def owned_by_plugin(e):         # a crossover's link between its halves, or a helix end: marked main by the plugin
        la, lb = (N[n].get("label") for n in (e["u"], e["v"]))
        return (la and la == lb) or any(N[n]["kind"] == "end" and N[n].get("sub") == "helix" for n in (e["u"], e["v"]))

    main_ids = line_edges(plan, rows)
    over = json.loads(json.dumps(overrides))
    named = [ed for ed in over["edits"] if ed.get("op") == "name"]
    if len(named) != 1:
        raise RouteError(f"{STAGING_OVERRIDES.name}: expected one `name` edit, found {len(named)}")
    seen, tracks = set(), []
    for a, b, name, *rest in named[0]["tracks"]:
        port = rest[0] if rest and rest[0] in ("A", "B", "C", "D") else None
        e = edits.edge_between(g, a, b, port)[0]
        seen.add(e["id"])
        tracks.append([a, b, name, *[r for r in rest if r != "main"], *(["main"] if e["id"] in main_ids else [])])
    named[0]["tracks"] = tracks
    lost = [e for e in g["edges"] if e["id"] in main_ids - seen and not owned_by_plugin(e)]
    if lost:
        raise RouteError("a main line runs over track the `name` edit does not name: "
                         + ", ".join(f"{plan.name(e['u'])} to {plan.name(e['v'])}" for e in lost))
    over["milepost_route"] = milepost_route(plan, rows)
    over["_main_lines"] = ("The main flags of the `name` edit and milepost_route are written by "
                           "tools/schematic/build_main_route.py from the staging rows of main_lines.csv; edit that "
                           "file, not these.")
    return json.dumps(over, indent=1, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if a main route or main line file is stale")
    args = ap.parse_args(argv)
    import build_layout_le as bl
    outputs = []
    try:
        overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))
        g, by_label = prepared(overrides)
        hops = route(Plan(g, by_label), read_lines("main_upper"))
        outputs.append((OVERRIDES, overrides_text(overrides, hops), f"main_route ({len(hops)} hops)"))
        st = json.loads(STAGING_OVERRIDES.read_text(encoding="utf-8"))
        sg, sby = prepared(st, "staging", STAGING_GRAPH)
        text = staging_text(st, Plan(sg, sby), read_lines("staging"))
        outputs.append((STAGING_OVERRIDES, text, "main flags and milepost_route"))
    except bl.BuildError as exc:      # the plugin is not checked out
        if not args.check:
            raise
        print(f"SKIPPED main route check: {exc}")
        return 1 if os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0
    except RouteError as exc:
        print(f"build_main_route.py: {exc}", file=sys.stderr)
        return 2
    stale = [(p, t, what) for p, t, what in outputs if p.read_text(encoding="utf-8") != t]
    if args.check:
        for p, _t, what in stale:
            print(f"{p.name} {what} is stale: run python3 tools/schematic/build_main_route.py", file=sys.stderr)
        if not stale:
            print("main route and staging main lines are current")
        return 1 if stale else 0
    for p, t, what in stale:
        p.write_text(t, encoding="utf-8")
        print(f"wrote {what} to {p.name}")
    if not stale:
        print("main route and staging main lines are current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
