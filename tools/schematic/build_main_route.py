"""build_main_route.py [--check]

Write the `main_route` key of main_upper.plan_overrides.json from main_lines_main_upper.csv and the plan graph.

The schematic marks as main track what lies on `main_route`, hop by hop. Written by hand, each hop named two plan part
numbers (T281, T311 ...), which change whenever the plan is exported again. Here the owner gives the two main lines
by what the railroad calls things, and this works the hops out:

    line,from,via,to,loop,double,notes

  from    the helix end the line starts at (its name, McKees Rocks), or a switch number;
  via     switch numbers the line must pass, in order, where the shortest way would leave it (";" between them);
  to      the switch the line ends at;
  loop    the switches of the turnback the line ends in, in order, ";" between them: the line runs from `to` round them
          and back to `to` (a balloon on one switch repeats `to`);
  double  switch pairs joined by two tracks that are both main ("223-225");
  notes   free text.

Each stretch between two stops is the shortest way along the plan (centimetres plus one per track, as the plugin
counts) that does not cut across a crossover (the short track between the A and B halves of one crossover number,
131A and 131B), and stops when two ways tie. A loop's stretches that join neighbouring switches use that track, whatever its
length. A pair of switches the line crosses that has two tracks must be in `double`, so no choice between parallel
tracks is made silently. Every hop is written [a, b, "direct"], marking every track between the two, in the order the
line runs; switches are named by their number, so the hops do not depend on the plan's part numbers.

--check regenerates in memory and exits 1 if the file differs.
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
LINES = pd.DATA / "main_lines_main_upper.csv"
GRAPH = pd.GRAPHS / "main.json"
COLUMNS = ["line", "from", "via", "to", "loop", "double", "notes"]
TIE = 1e-6          # centimetres: two ways this close are a tie


class RouteError(ValueError):
    """The main lines cannot be worked out from the plan; the message says why."""


def split(cell: str) -> list[str]:
    return [p.strip() for p in cell.split(";") if p.strip()]


def read_lines(path: Path = LINES) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != COLUMNS:
            raise RouteError(f"{path.name}: expected the columns {', '.join(COLUMNS)}, got {reader.fieldnames}")
        rows = list(reader)
    if not rows:
        raise RouteError(f"{path.name} has no main line")
    seen = set()
    for n, r in enumerate(rows, 2):
        if not r["line"].strip() or r["line"] in seen:
            raise RouteError(f"{path.name} line {n}: line name {r['line']!r} is empty or repeated")
        seen.add(r["line"])
        if not r["from"].strip() or not r["to"].strip():
            raise RouteError(f"{path.name} line {n} ({r['line']}): from and to are both needed")
    return rows


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
        """What the hop calls this node: its switch number or helix name, which must find only it again."""
        d = self.g["nodes"][n]
        label = d.get("label")
        if d["kind"] == "end":      # a helix end is called by its track's name
            label = next((e["names"][0] for e in self.g["edges"] if n in (e["u"], e["v"]) and e["names"]), None)
        if not label or self.node(label) != n:
            raise RouteError(f"junction {n} has no unique name to write the route with (label {label!r})")
        return label

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


def line_hops(plan: Plan, row: dict) -> list[tuple[str, str, list[dict]]]:
    """[(from node, to node, [edges marked between them])] for one main line, in running order."""
    stops = [row["from"].strip(), *split(row["via"]), row["to"].strip()]
    double = {frozenset(p.split("-")) for p in split(row["double"])}
    steps: list[tuple[str, dict, str]] = []
    nodes = [plan.node(s) for s in stops]
    for a, b in zip(nodes, nodes[1:]):
        steps += plan.shortest(a, b, double)
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


def prepared(overrides: dict):
    """(the plugin's graph with the overrides applied and no main_route, node_ref: how a route names a junction)."""
    import build_layout_le as bl
    sheet, _le, _core = bl.plugin()
    from schematic import edits   # the plugin's package: bl.plugin() has put it on the path
    opts = dict(sheet.options("main_upper", pd.DATA))
    opts.pop("main_route", None)
    g = sheet.prepare(json.loads(GRAPH.read_text()), opts, set())
    return g, edits.node_ref


def overrides_text(overrides: dict, hops: list) -> str:
    over = dict(overrides)
    over["main_route"] = hops
    return json.dumps(over, indent=1, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if main_route is stale")
    args = ap.parse_args(argv)
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    import build_layout_le as bl
    try:
        g, by_label = prepared(overrides)
        hops = route(Plan(g, by_label), read_lines())
    except bl.BuildError as exc:      # the plugin is not checked out
        if not args.check:
            raise
        print(f"SKIPPED main route check: {exc}")
        return 1 if os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0
    except RouteError as exc:
        print(f"build_main_route.py: {exc}", file=sys.stderr)
        return 2
    text = overrides_text(overrides, hops)
    if OVERRIDES.read_text(encoding="utf-8") == text:
        print(f"main_route is current ({len(hops)} hops)")
        return 0
    if args.check:
        print(f"{OVERRIDES.name} main_route is stale: run python3 tools/schematic/build_main_route.py", file=sys.stderr)
        return 1
    OVERRIDES.write_text(text, encoding="utf-8")
    print(f"wrote main_route ({len(hops)} hops) to {OVERRIDES.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
