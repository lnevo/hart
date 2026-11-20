#!/usr/bin/env python3
"""Each staging block's length in the AnyRail plan 5.3c, written into block_lengths.csv's plan_in column.

    python3 tools/schematic/plan_lengths.py            # write plan_in
    python3 tools/schematic/plan_lengths.py --check    # exit 1 if plan_in is stale
    python3 tools/schematic/plan_lengths.py --show     # print the lengths, write nothing

The plan is the source (owner, 2026-11-20): the schematic, the Layout Editor panel and the signal rules measure every
staging block by plan_in; JMRI's block length is the measured one where a block was timed, else plan_in
(hartlib.railroad.BlockLength.jmri_in).

- An OS block takes its turnout's product length: from the points to the frog end of the plan part at its switch
  (one part per OS block; a crossover half is its own part), measured between the part's end points in parts.json
  (turnout_inches). PRODUCT_INCHES only checks the reading: a Peco code 83 #6 is about 9.2 in, a #8 11.0 to 11.2 in.
- A track block takes its drawn length: the plan's track between the turnout ends at either end of its run (or a
  buffer stop, or the switch beyond the helix), as AnyRail's export measures it (tools/anyrail/anyplan.py runs: flex
  track only, the turnouts left out). A run the schematic draws as two tracks (a balloon loop folded at its turnback,
  K-1 and K-2) gives each half; a block drawn on both (Brick-Plane) takes the whole.
- A track that holds an OS block too (Scale ends in OS Switch 7) keeps its whole run: the OS block is the turnout,
  which the run leaves out.

Track lengths need the plan file itself (PLAN, private, never committed; ANYRAIL_PLAN overrides the path). Without it,
--check checks the OS rows only and says so; a write stops. OS lengths need only parts.json (committed). Which block
is on which track comes from the staging device map (staging_device_map.load) on the staging band.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA, GRAPHS, hartlib paths and the pinned plugin
import staging_device_map as sdm  # noqa: E402  the staging band and its blocks
from hartlib import paths, railroad  # noqa: E402

sys.path.insert(0, str(pd.REPO / "tools/anyrail"))
import anyplan  # noqa: E402  the plan reader

LENGTHS = railroad.Sources.under().block_lengths
PARTS = pd.GRAPHS / "parts.json"
GRAPH = pd.GRAPHS / "staging.json"
PLAN = Path(os.environ.get("ANYRAIL_PLAN") or Path.home() / "Documents/Layout/Lee Nevo Design Version 5.3c.any")
CM = 2.54
# The product lengths a reading must give, points to frog end, in inches: a check on turnout_inches, not a source.
PRODUCT_INCHES = {"#6": (9.1, 9.3), "#8": (10.9, 11.3)}
PRODUCTS = {"SL-8361": "#6", "SL-8362": "#6", "SL-E8361": "#6", "SL-E8362": "#6",
            "SL-8377": "#8", "SL-8378": "#8", "SL-E8377": "#8", "SL-E8378": "#8"}
LEG_OF = {"points": "A", "straight": "B", "diverging": "C"}     # anyplan.classify's ends as the graph names legs


class LengthError(RuntimeError):
    pass


def turnout_inches(part: dict) -> float:
    """A turnout part's length from the points to the frog end, in inches: from its points end (the end farthest from
    the other two) to the middle of its two frog-end ends. LengthError on a part that is not a three-ended turnout, a
    product not in PRODUCTS, or a length outside its PRODUCT_INCHES."""
    eps = part.get("eps") or []
    if len(eps) != 3:
        raise LengthError(f"part {part.get('name')!r} has {len(eps)} ends, not a turnout's three")
    xy = [(e["x"], e["y"]) for e in eps]
    p = max(range(3), key=lambda i: sum(math.dist(xy[i], xy[j]) for j in range(3)))
    a, b = (xy[i] for i in range(3) if i != p)
    inches = math.dist(xy[p], ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)) / CM
    product = PRODUCTS.get(part["name"])
    if product is None:
        raise LengthError(f"part {part['name']!r} is no turnout product this knows (PRODUCTS)")
    lo, hi = PRODUCT_INCHES[product]
    if not lo <= inches <= hi:
        raise LengthError(f"part {part['name']} ({product}) reads {inches:.2f} in from points to frog end, "
                          f"outside {lo} to {hi}")
    return inches


def part_index(label: str) -> int:
    """The parts.json index of a plan graph node's label ("T139" -> 139: a part's T number is its place in the
    file)."""
    if not (label or "").startswith("T") or not label[1:].isdigit():
        raise LengthError(f"plan graph node label {label!r} is no part (T<n>)")
    return int(label[1:])


def os_lengths(band, names: dict, graph: dict, parts: list) -> dict:
    """{OS block: inches}: each OS block's turnout product length (turnout_inches), by the part at its switch node.
    LengthError on an OS block given to two switch nodes."""
    out, seen = {}, {}
    for node, block in names["os"].items():
        if block in seen:
            raise LengthError(f"{block} stands at switch nodes {seen[block]} and {node}; an OS block is one turnout")
        seen[block] = node
        i = part_index(graph["nodes"][node].get("label"))
        if i >= len(parts):
            raise LengthError(f"{block}: part T{i} is not in {PARTS.name} ({len(parts)} parts)")
        out[block] = turnout_inches(parts[i])
    return out


def plan_runs(plan: Path) -> dict:
    """{(part, leg): (inches, far end)} of every switch leg's run in the plan file (anyplan.runs): far end
    (part, leg), or None at a buffer stop or a free end. Legs are the graph's (LEG_OF)."""
    parts = anyplan.read(plan)
    links, _free = anyplan.joins(parts)
    legs = {}
    for p in parts:
        if p["kind"] == "turnout":
            legs[p["index"]] = {p[k]: v for k, v in LEG_OF.items()}
    out = {}
    for a, ka, b, kb, cm in anyplan.runs(parts, links):
        if a not in legs:
            continue                    # a three-way or crossing: staging has none
        far = (b, legs[b][kb]) if b is not None and b in legs else (None if b is None else (b, kb))
        out[(a, legs[a][ka])] = (cm / CM, far)
    return out


def edge_runs(graph: dict, runs: dict) -> dict:
    """{edge id: inches} of each plan graph edge from a switch: the run from its switch end. LengthError when the
    run does not reach the edge's other end (the other switch and leg, or a buffer stop), so the graph and the plan
    file are the same plan; a helix end reaches the switch beyond the helix, which the staging graph does not hold."""
    nodes = graph["nodes"]
    out, bad = {}, []
    for e in graph["edges"]:
        ends = [(e["u"], e["up"]), (e["v"], e["vp"])]
        sw = [(n, p) for n, p in ends if nodes[n]["kind"] == "switch"]
        if not sw:
            bad.append(f"edge {e['id']} has no switch end")
            continue
        n, p = sw[0]
        got = runs.get((part_index(nodes[n]["label"]), p))
        if got is None:
            bad.append(f"edge {e['id']}: no run from {nodes[n]['label']} leg {p} in the plan file")
            continue
        inches, far = got
        other = ends[1] if (n, p) == ends[0] else ends[0]
        kind = nodes[other[0]]["kind"]
        if kind == "switch":
            want = (part_index(nodes[other[0]]["label"]), other[1])
            if far != want:
                bad.append(f"edge {e['id']}: the plan's run from {nodes[n]['label']} leg {p} ends at {far}, the graph "
                           f"says T{want[0]} leg {want[1]}")
                continue
        elif nodes[other[0]].get("sub") == "bumper" and far is not None:
            bad.append(f"edge {e['id']}: ends at a bumper in the graph, at {far} in the plan file")
            continue
        out[e["id"]] = inches
    if bad:
        raise LengthError(f"{paths.rel(GRAPH)} and {PLAN.name} differ: " + "; ".join(bad))
    return out


def track_lengths(band, names: dict, runs: dict, os_blocks: set) -> dict:
    """{track block: inches} from `runs` ({plan edge id: inches}, edge_runs): each strand of the band takes its
    edge's run, split evenly over the strands the schematic draws it as (a balloon loop folded at its turnback). On a
    strand, OS blocks take nothing (the run leaves the turnouts out) and the one track block takes the rest; a block
    on several strands adds them up. LengthError on a strand with two track blocks."""
    strands = band["strands"]
    by_edge = defaultdict(list)
    for sid, s in strands.items():
        if names["blocks"].get(sid):
            by_edge[s["edge"].split(".")[0]].append(sid)
    out, bad = defaultdict(float), []
    for edge, sids in sorted(by_edge.items()):
        if edge not in runs:
            bad.append(f"track {edge}: no run in the plan file")
            continue
        share = runs[edge] / len(sids)
        for sid in sids:
            tracks = [b for b in names["blocks"][sid] if b not in os_blocks]
            if len(tracks) > 1:
                bad.append(f"track {sid}: blocks {tracks} share it and only one may take its length")
                continue
            if tracks:
                out[tracks[0]] += share
    if bad:
        raise LengthError("; ".join(bad))
    return dict(out)


def compute(plan: Path | None) -> tuple[dict, bool]:
    """({block: inches} of every staging block, whether the track lengths are in it: False when `plan` is None)."""
    with pd.cache_on():
        band, _opts, _core = sdm.staging_band()
    names = sdm.load(band, with_masts=False, turnout_idents=False)
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    parts = json.loads(PARTS.read_text(encoding="utf-8"))
    out = os_lengths(band, names, graph, parts)
    if plan is None:
        return out, False
    out.update(track_lengths(band, names, edge_runs(graph, plan_runs(plan)), set(out)))
    drawn = {b for v in names["blocks"].values() for b in v} | set(names["os"].values())
    missing = sorted(drawn - set(out))
    if missing:
        raise LengthError(f"no plan length for drawn blocks {missing}")
    return out, True


def csv_with(lengths: dict, path: Path = LENGTHS) -> str:
    """block_lengths.csv's text with plan_in set from `lengths` (rounded to 0.1 in). LengthError when the file's
    blocks and the drawn staging blocks differ."""
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows or list(rows[0]) != list(railroad.BLOCK_LENGTH_COLUMNS):
        raise LengthError(f"{paths.rel(path)}: columns are not {', '.join(railroad.BLOCK_LENGTH_COLUMNS)}")
    have = {r["user_name"] for r in rows}
    if have != set(lengths):
        raise LengthError(f"{paths.rel(path)} and the staging drawing hold different blocks: only in the file "
                          f"{sorted(have - set(lengths))}, only drawn {sorted(set(lengths) - have)}")
    for r in rows:
        r["plan_in"] = f"{lengths[r['user_name']]:.1f}"
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(railroad.BLOCK_LENGTH_COLUMNS), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="exit 1 if plan_in is stale")
    g.add_argument("--show", action="store_true", help="print the lengths and write nothing")
    args = ap.parse_args(argv)
    try:
        sdm.lc.plugin()
    except sdm.lc.BuildError as exc:
        if args.check:
            print(f"SKIPPED plan lengths check: {exc}")
            return 1 if os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0
        print(f"plan_lengths.py: {exc}", file=sys.stderr)
        return 2
    plan = PLAN if PLAN.exists() else None
    if plan is None and not args.check:
        print(f"plan_lengths.py: no plan file {PLAN} (set ANYRAIL_PLAN): the track lengths need it", file=sys.stderr)
        return 2
    try:
        lengths, whole = compute(plan)
        if args.show:
            for b in sorted(lengths):
                print(f"{b:24} {lengths[b]:7.1f} in")
            return 0
        if not whole:
            have = railroad.read_block_lengths(LENGTHS)
            bad = [f"{b}: plan_in {have[b].plan_in if b in have else 'missing'}, the part gives {v:.1f}"
                   for b, v in sorted(lengths.items()) if b not in have or abs(have[b].plan_in - round(v, 1)) > 1e-9]
            print(f"plan lengths: no plan file {PLAN.name}; the OS rows only are checked")
            for b in bad:
                print(f"{LENGTHS.name}: {b}", file=sys.stderr)
            return 1 if bad else 0
        text = csv_with(lengths)
    except (LengthError, sdm.StagingMapError, sdm.lc.BuildError, anyplan.PlanError, railroad.FactsError) as exc:
        print(f"plan_lengths.py: {exc}", file=sys.stderr)
        return 2
    stale = LENGTHS.read_text(encoding="utf-8") != text
    if args.check:
        if stale:
            print(f"{LENGTHS.name}: plan_in is stale: run python3 tools/schematic/plan_lengths.py", file=sys.stderr)
        return 1 if stale else 0
    if stale:
        LENGTHS.write_text(text, encoding="utf-8")
        print(f"wrote {paths.rel(LENGTHS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
