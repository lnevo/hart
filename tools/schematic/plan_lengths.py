#!/usr/bin/env python3
"""Each block's length in the AnyRail plan 5.3c, on every level, written into block_lengths.csv (the plan file).

    python3 tools/schematic/plan_lengths.py            # write plan_in
    python3 tools/schematic/plan_lengths.py --check    # exit 1 if plan_in is stale
    python3 tools/schematic/plan_lengths.py --show     # print the lengths, write nothing

Each row is keyed by its block's level and device ID: a length worked out for a block by its
name finds its row through the device master, and the file holds no name, so a rename in devices_field.csv changes no
row. This is the plan file's one writer; the lengths speed matching measured sit in block_lengths_measured.csv beside
it (infer_block_lengths.py, hartlib.block_lengths; ADR-039 lane L8).

The plan length serves the schematic, the Layout Editor panel and the signal rules on every level; JMRI's block length
is the operating length, a measured one where speed matching found it, else this (hartlib.block_lengths).

- An OS block takes its turnout's length: from the points to the frog end of the plan part at its switch
  (one part per OS block; a crossover half is its own part), measured between the part's end points in parts.json
  (turnout_inches). The turnout's class (#6 or #8) comes from the angle of its two leg ends (turnout_class), not
  from a maker's part name; TURNOUT_INCHES only checks the reading: a #6 is about 9.2 in, a #8 11.0 to 11.2 in.
- A track block takes its drawn length: the plan's track between the turnout ends at either end of its run (or a
  buffer stop, or the switch beyond the helix), as AnyRail's export measures it (the plugin's anyplan runs: flex
  track only, the turnouts left out). A run the schematic draws as two tracks (a balloon loop folded at its turnback,
  K-1 and K-2) gives each half; a block drawn on both (Brick-Plane) takes the whole.
- A track that holds an OS block too (Scale ends in OS Switch 7) keeps its whole run: the OS block is the turnout,
  which the run leaves out.

Main and upper (main_upper_lengths), from the device master's level 2 and 3 block rows and main.json, the plan graph of
those levels:
- a track block takes its plan edges' runs in the plan file (main_edge_inches), its share of each: each row's trial
  names are switch-and-leg keys ("Track 101BA-111C", "Track 107B-107C #1" for half of a balloon loop), resolved on
  the solved drawing to the plan edges their strands are drawn on (piece_edges: a loop half is one of its edge's two
  strands, so half the edge): flex track only, the turnouts left out, as staging's. The
  plan graph's own edge lengths (main.json's cm, which the drawing, the link rule and the mast places use) count
  part of each turnout as well, so they are not block lengths. A helix
  block is staging's row (one block across levels), not counted again here. A part (a link inside an OS block) adds
  nothing, as on staging;
- an OS block takes the turnouts its switch stands on: a turnout's product length (turnout_inches), both halves of a
  single crossover added (121, 125, 127, 131); the three-way (Switches 101 and 103) and the double crossover (225,
  corners a to d) share their part's span, its longest end-to-end distance (part_span_inches), evenly over their OS
  blocks.

Track lengths need the plan file itself (PLAN, private, never committed; ANYRAIL_PLAN overrides the path). Without it,
--check checks the OS rows only and says so; a write stops. OS lengths need only parts.json (committed). Which block
is on which track comes from the staging device map (staging_device_map.load) on the staging band, and from
the device master on main and upper.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA, GRAPHS, hartlib paths and the pinned plugin
import staging_device_map as sdm  # noqa: E402  the staging band and its blocks
from hartlib import block_lengths, paths, railroad  # noqa: E402


def anyplan():
    """The plan reader: the schematic-maps plugin's schematic.anyplan (le_common.plugin_module, the pinned plugin)."""
    return sdm.lc.plugin_module("anyplan")


LENGTHS = block_lengths.PLAN
PARTS = pd.GRAPHS / "parts.json"
GRAPH = pd.GRAPHS / "staging.json"
MAIN_GRAPH = pd.GRAPHS / "main.json"            # main and upper's plan graph
MAIN_UPPER = ("2", "3")
RUN_TOLERANCE_CM = 0.1                          # main.json's runs are the plan's, rounded to 0.1 cm
PLAN = Path(os.environ.get("ANYRAIL_PLAN") or Path.home() / "Documents/Layout/Lee Nevo Design Version 5.3c.any")
CM = 2.54
# A turnout's class comes from its geometry, never from a maker's part name (any maker's track reads the same way).
# TURNOUT_NUMBERS: the leg-end chord number of each class, cot(angle at the points between the two leg ends); it reads
# above the printed frog number because the diverging route curves. A reading must fall in a class's range.
# TURNOUT_INCHES: the points-to-frog-end length per class, in inches: a check on turnout_inches, not a source.
TURNOUT_NUMBERS = {"#5": (7.7, 8.6), "#6": (8.65, 9.65), "#8": (10.6, 11.6)}     # #5: main and upper only
TURNOUT_INCHES = {"#5": (8.2, 8.4), "#6": (9.1, 9.3), "#8": (10.9, 11.3)}
LEG_OF = {"points": "A", "straight": "B", "diverging": "C"}     # anyplan.classify's ends as the graph names legs


class LengthError(RuntimeError):
    pass


def _points_end(xy: list) -> int:
    """Index of a three-ended part's points end: the end farthest from the other two (anyplan.classify's rule, which
    needs end headings that parts.json does not carry)."""
    return max(range(3), key=lambda i: sum(math.dist(xy[i], xy[j]) for j in range(3)))


def turnout_class(part: dict) -> str:
    """"#6" or "#8", from the part's end points alone: the angle at the points end between the two leg ends gives the
    chord number cot(angle), matched to TURNOUT_NUMBERS. LengthError on a part that is not a three-ended turnout or
    whose number is in no class's range (the part's name is a label in the message only). parts.json holds end
    points but no headings, so this cannot tell a straight turnout from a curved one or a wye whose leg ends happen
    to fall in a class's range; TURNOUT_INCHES then checks the length, and every part the plan holds today reads as
    the straight #6 or #8 it is."""
    eps = part.get("eps") or []
    if len(eps) != 3:
        raise LengthError(f"part {part.get('name')!r} has {len(eps)} ends, not a turnout's three")
    xy = [(e["x"], e["y"]) for e in eps]
    p = _points_end(xy)
    (ax, ay), (bx, by) = ((xy[i][0] - xy[p][0], xy[i][1] - xy[p][1]) for i in range(3) if i != p)
    angle = abs(math.atan2(ax * by - ay * bx, ax * bx + ay * by))
    if angle < 1e-9:
        raise LengthError(f"part {part.get('name')!r} has both leg ends on one line from its points end")
    number = 1 / math.tan(angle)
    for cls, (lo, hi) in TURNOUT_NUMBERS.items():
        if lo <= number <= hi:
            return cls
    raise LengthError(f"part {part.get('name')!r} has leg-end angle {math.degrees(angle):.2f} deg (chord number "
                      f"{number:.2f}), in no class of TURNOUT_NUMBERS {TURNOUT_NUMBERS}")


def turnout_inches(part: dict) -> float:
    """A turnout part's length from the points to the frog end, in inches: from its points end to the middle of its
    two frog-end ends. LengthError on a part turnout_class rejects, or a length outside its class's TURNOUT_INCHES."""
    cls = turnout_class(part)
    xy = [(e["x"], e["y"]) for e in part["eps"]]
    p = _points_end(xy)
    a, b = (xy[i] for i in range(3) if i != p)
    inches = math.dist(xy[p], ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)) / CM
    lo, hi = TURNOUT_INCHES[cls]
    if not lo <= inches <= hi:
        raise LengthError(f"part {part.get('name')!r} ({cls}) reads {inches:.2f} in from points to frog end, "
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
    parts = anyplan().read(plan)
    links, _free = anyplan().joins(parts)
    legs = {}
    for p in parts:
        if p["kind"] == "turnout":
            legs[p["index"]] = {p[k]: v for k, v in LEG_OF.items()}
    out = {}
    for a, ka, b, kb, cm in anyplan().runs(parts, links):
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


def track_lengths(band, names: dict, runs: dict, os_blocks: set, parts: dict) -> dict:
    """{track block: inches} from `runs` ({plan edge id: inches}, edge_runs): each strand of the band takes its
    edge's run, split evenly over the strands the schematic draws it as (a balloon loop folded at its turnback). On a
    strand, OS blocks take nothing (the run leaves the turnouts out); one track block takes the rest; parts only
    (`parts`: {part: its cm}, block_layer.Layer.parts; a track with a part at each end: Track 1-3 at 1 and at 3) share
    it evenly, as track_inches reads a k/n key; a part at one end beside its track's own block takes its cm (the
    piece block_overrides.csv gives a length) and the track's block the rest. A block on several strands adds them
    up. LengthError on an edge with no run in the plan, a part's cm not under its strand's run, or any other mix of
    track blocks on one strand."""
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
            own = [b for b in tracks if b not in parts]
            if len(tracks) <= 1 or not own:
                for b in tracks:
                    out[b] += share / len(tracks)
            elif len(own) == 1:
                pieces = {b: parts[b] / CM for b in tracks if b in parts}
                if sum(pieces.values()) >= share:
                    bad.append("; ".join(f"{b}: {parts[b]:g} cm is not under the track's {share:.1f} in"
                                         for b in pieces))
                    continue
                for b, inches in pieces.items():
                    out[b] += inches
                out[own[0]] += share - sum(pieces.values())
            else:
                bad.append(f"track {sid}: blocks {tracks} share it and only one may take what its parts leave")
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
    import build_device_map as bdm
    with pd.cache_on():
        bands, joined, runs, _corners = bdm.solve()
    lay, _bi, _found = bdm.staging_layer(bands, joined, runs)
    part_cm = {name: p["cm"] for name, p in lay.parts.items()}
    out.update(track_lengths(band, names, edge_runs(graph, plan_runs(plan)), set(out), part_cm))
    drawn = {b for v in names["blocks"].values() for b in v} | set(names["os"].values())
    missing = sorted(drawn - set(out))
    if missing:
        raise LengthError(f"no plan length for drawn blocks {missing}")
    return out, True


def part_span_inches(part: dict) -> float:
    """A four-ended part's span (a three-way or a double crossover), in inches: its longest distance between two ends.
    LengthError on a part with other than four ends."""
    eps = part.get("eps") or []
    if len(eps) != 4:
        raise LengthError(f"part {part.get('name')!r} has {len(eps)} ends, not a three-way's or double crossover's four")
    xy = [(e["x"], e["y"]) for e in eps]
    return max(math.dist(a, b) for i, a in enumerate(xy) for b in xy[i + 1:]) / CM


def main_edge_inches(graph: dict, runs: dict, threeway_bumper: float | None) -> dict:
    """{plan edge: inches} of main.json's edges, from the plan file (`runs`, plan_runs: flex track only, the turnouts
    left out, as staging's tracks): each edge takes the run from a plain turnout at one of its ends (a "T" label, a
    turnout in the plan); an edge from the three-way to a buffer stop takes `threeway_bumper`, the three-way's one run
    to a buffer stop; the three-way's own inner edge (between its two switch nodes) takes nothing, as it is inside its
    OS blocks. LengthError on any other edge."""
    nodes = graph["nodes"]
    out, bad = {}, []
    for e in graph["edges"]:
        ends = [(e["u"], e["up"]), (e["v"], e["vp"])]
        got = None
        for n, port in ends:
            label = nodes[n].get("label") or ""
            if nodes[n]["kind"] == "switch" and label.startswith("T") and label[1:].isdigit():
                got = runs.get((int(label[1:]), port))
                if got is not None:
                    break
        if got is not None:
            out[e["id"]] = got[0]
            continue
        kinds = sorted("threeway" if n.startswith("TO_3W") else nodes[n]["kind"] for n, _p in ends)
        if kinds == ["end", "threeway"] and threeway_bumper is not None:
            out[e["id"]] = threeway_bumper
        elif kinds == ["threeway", "threeway"]:
            out[e["id"]] = 0.0
        else:
            bad.append(f"edge {e['id']} ({e['u']} {e['up']} to {e['v']} {e['vp']}): no run in {PLAN.name}")
    if bad:
        raise LengthError(f"{paths.rel(MAIN_GRAPH)}: " + "; ".join(bad))
    return out


def threeway_bumper_inches(plan_parts: list) -> float | None:
    """The run from the plan's one three-way to a buffer stop, in inches (anyplan.runs), or None with no three-way.
    LengthError when the three-way has other than one run to a buffer stop, or there is more than one three-way."""
    three = [p["index"] for p in plan_parts if p["kind"] == "threeway"]
    if not three:
        return None
    if len(three) != 1:
        raise LengthError(f"{PLAN.name} has {len(three)} three-ways; main_edge_inches reads one")
    links, _free = anyplan().joins(plan_parts)
    got = [cm for a, _ka, b, _kb, cm in anyplan().runs(plan_parts, links) if a == three[0] and b is None]
    if len(got) != 1:
        raise LengthError(f"the three-way (part {three[0]}) has {len(got)} runs to a buffer stop, not one")
    return got[0] / CM


def main_upper_os(bands, graph: dict, parts: list, threeways: list[int]) -> dict:
    """{OS block: inches} of main and upper (module text), from the solved `bands` (a switch node's number, the graph
    node it is) and the corner blocks of the double crossover (device_map_schematic.corner_blocks_of). `threeways`: the plan
    file's three-way parts (their graph nodes carry no part number)."""
    import build_device_map as bdm
    out, bad = defaultdict(float), []
    three = defaultdict(list)
    corners = None
    for title, band, _o in bands:
        if not bdm.band_level(title):
            continue
        for n, d in band["nodes"].items():
            if d["kind"] not in ("switch", "dx"):
                continue
            number = bdm.base(d["label"])
            label = graph["nodes"].get(n, {}).get("label") or ""
            if n.startswith("TO_3W"):
                three[re.sub(r"-\d+$", "", n)].append(f"OS Switch {number}")
                continue
            try:
                part = parts[part_index(label)]
            except (LengthError, IndexError):
                bad.append(f"switch {d['label']} ({n}): graph label {label!r} names no part in {PARTS.name}")
                continue
            if d["kind"] == "dx":
                if corners is None:
                    _b, _j, _r, dxc = bdm.solve()
                    corners = bdm.corner_blocks_of(bands, dxc)
                blocks = sorted(corners[number].values())
                for b in blocks:
                    out[b] += part_span_inches(part) / len(blocks)
            else:
                out[f"OS Switch {number}"] += turnout_inches(part)
    if len(three) != len(threeways):
        bad.append(f"{len(three)} three-way(s) drawn on main and upper, {len(threeways)} in {PLAN.name}")
    for (_key, blocks), index in zip(sorted(three.items()), sorted(threeways)):
        for b in blocks:
            out[b] += part_span_inches(parts[index]) / len(blocks)
    if bad:
        raise LengthError("; ".join(bad))
    return dict(out)


def piece_edges(strands: dict, refs: dict) -> dict[str, dict[str, float]]:
    """{piece: {plan edge: the piece's share of it}} of the main and upper drawing: `strands` ({band index: the band's
    strands}) and `refs` ({band index: staging_device_map.band_refs}), each strand's piece its switch-and-leg key
    without "Track " or a k/n (staging_device_map.piece_of reads a trial name back to it). A piece's share of an edge
    is its strands of that edge over all the edge's strands (a balloon loop half: one of two; a track cut by a
    connector: both of its pieces), the edge its strand's with a connector's x/y piece letter dropped."""
    held, count = defaultdict(lambda: defaultdict(int)), defaultdict(int)
    for bi, band_refs in refs.items():
        for sid, (piece, _against) in band_refs.items():
            edge = re.sub(r"(?<=\d)[xy]$", "", strands[bi][sid]["edge"])
            held[piece][edge] += 1
            count[edge] += 1
    return {piece: {e: n / count[e] for e, n in edges.items()} for piece, edges in held.items()}


def track_inches(r: dict, pieces: dict, edge_in: dict, bad: list) -> float | None:
    """A main or upper track block row's plan length, in inches: each trial name's piece (staging_device_map.piece_of)
    and its share of plan edges (`pieces`, piece_edges), a k/n key taking 1/n of it (the k-th of a strand's n blocks,
    staging_device_map.strand_placeholders), times each edge's length (`edge_in`, main_edge_inches). None, with the
    problem in `bad`, for a row with no trial name, a trial name that is no track key or is drawn on no strand, or an
    edge the plan graph does not have."""
    where = f"{r['user_name']} (level {r['level']})"
    trials = [t.strip() for t in r["trial_name"].split(",") if t.strip()]
    if not trials:
        bad.append(f"{where}: no trial_name, so no plan edge to measure")
        return None
    total = 0.0
    for trial in trials:
        try:
            piece, _k, n = sdm.piece_of(trial)
        except sdm.StagingMapError as exc:
            bad.append(f"{where}: {exc}")
            return None
        if piece not in pieces:
            bad.append(f"{where}: trial name {trial!r} is drawn on no main or upper strand")
            return None
        for edge, share in sorted(pieces[piece].items()):
            if edge not in edge_in:
                bad.append(f"{where}: trial name {trial!r} is drawn on plan edge {edge}, which {MAIN_GRAPH.name} "
                           "does not have")
                return None
            total += edge_in[edge] * share / n
    return total


def main_upper_lengths(plan: Path) -> dict:
    """{block: (level, inches, the block whose occupancy sensor it has)} of every main and upper block of the device master,
    its parts too (a JMRI block of their own whose sensor is their OS block's; a link whose turnouts touch in the plan
    is 0 in long), but the helix blocks (staging's rows; module
    text). LengthError on a row whose trial names give no plan edge, or a block left with no length."""
    import build_device_map as bdm
    from hartlib import devices
    graph = json.loads(MAIN_GRAPH.read_text(encoding="utf-8"))
    parts = json.loads(PARTS.read_text(encoding="utf-8"))
    plan_parts = anyplan().read(plan)
    runs = plan_runs(plan)
    edge_in = main_edge_inches(graph, runs, threeway_bumper_inches(plan_parts))
    helix = {h["block"] for h in bdm.read_helix_tracks().values()}
    bands, joined, _runs, _corners = bdm.solve()
    mine = [bi for bi, lv in enumerate(sdm.lc.band_levels(bands)) if lv not in sdm.lc.STAGING_LEVELS]   # main, upper
    try:
        pieces = piece_edges({bi: bands[bi][1]["strands"] for bi in mine},
                             {bi: sdm.band_refs(bands, joined, bi) for bi in mine})
    except sdm.StagingMapError as exc:
        raise LengthError(str(exc)) from exc
    os_in = main_upper_os(bands, graph, parts, [p["index"] for p in plan_parts if p["kind"] == "threeway"])
    out, bad = {}, []
    ix = devices.index()                        # built once: a row's location text only for a message
    for _n, r in ix.lines:
        if r["level"] not in MAIN_UPPER or r.layer != "block" or r.user_name in helix:
            continue
        name = r.user_name
        sensor = r.part_of or name           # a part's occupancy sensor is its OS block's
        if devices.is_os(r, ix.where(r)):
            if name not in os_in:
                bad.append(f"{name} (level {r['level']}): no turnout part found for it")
            else:
                out[name] = (r["level"], os_in[name], sensor)
            continue
        total = track_inches(r, pieces, edge_in, bad)
        if total is not None:
            out[name] = (r["level"], total, sensor)
    if bad:
        raise LengthError("; ".join(bad))
    return out


def block_ids(files=None) -> dict[tuple[str, str], str]:
    """{(level, block name): device ID} of every block row of the device master (the name store's names): how a
    length worked out by name finds its block_lengths.csv row, which is keyed by (level, id)."""
    from hartlib import devices
    return {(r["level"], r.user_name): r.id for r in devices.load(files) if r.level and r.layer == "block"}


def _read_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows or list(rows[0]) != list(block_lengths.PLAN_COLUMNS):
        raise LengthError(f"{paths.rel(path)}: columns are not {', '.join(block_lengths.PLAN_COLUMNS)}")
    return rows


def _text(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(block_lengths.PLAN_COLUMNS), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def csv_with(lengths: dict, main_upper: dict, path: Path = LENGTHS, parts: dict | None = None,
             ids: dict | None = None) -> str:
    """block_lengths.csv's text with plan_in set from `lengths` (staging's blocks, rounded to 0.1 in) and from
    `main_upper` ({block: (level, inches, sensor block)}, main_upper_lengths). Each length finds its row by its block's
    level and device ID (`ids`: block_ids, default the device master's). A row keeps its note; only plan_in is set. A
    new main or upper block gets a row; main and upper's rows come after staging's in level and name order. A staging
    part (`parts`: {part: its block}) with no row gets one. LengthError when another drawn staging block has no row, a
    row is a block of no level, or a block has no device ID."""
    ids = block_ids() if ids is None else ids
    rows = _read_rows(path)
    parts = parts or {}
    no_id = sorted({n for n in lengths if ("1", n) not in ids} |
                   {n for n, (lv, _i, _s) in main_upper.items() if (lv, n) not in ids}, key=railroad.natural)
    if no_id:
        raise LengthError(f"blocks with no device ID in the device master: {no_id}")
    key_of = {n: ("1", ids[("1", n)]) for n in lengths}          # a helix block is staging's row
    name_of = {k: n for n, k in key_of.items()}
    staging = [r for r in rows if (r["level"], r["id"]) in name_of]
    rest = [r for r in rows if (r["level"], r["id"]) not in name_of]
    have = {name_of[(r["level"], r["id"])] for r in staging}
    new = sorted(set(lengths) - have, key=railroad.natural)
    lost = [b for b in new if b not in parts]
    if lost:
        raise LengthError(f"{paths.rel(path)} and the staging drawing hold different blocks: only drawn {lost}")
    for b in new:            # a staging part (a JMRI block of its own since 2026-11-20): on its block's detector
        if parts[b] not in have:
            raise LengthError(f"{b} is part of {parts[b]}, which has no row in {paths.rel(path)}")
        staging.append(dict(level="1", id=key_of[b][1],
                            note=f"staging, the plan's length; a part of {parts[b]}, on its detector"))
    for r in staging:
        r["plan_in"] = f"{lengths[name_of[(r['level'], r['id'])]]:.1f}"
    want = {(lv, ids[(lv, n)]): n for n, (lv, _i, _s) in main_upper.items()}
    stray = sorted(r["id"] for r in rest if (r["level"], r["id"]) not in want)
    if stray:
        raise LengthError(f"{paths.rel(path)}: rows of no drawn block on any level: {stray}")
    held = {(r["level"], r["id"]): r for r in rest}
    rest = []
    for name, (level, inches, _sensor) in sorted(main_upper.items(),
                                                key=lambda kv: (kv[1][0], railroad.natural(kv[0]))):
        key = (level, ids[(level, name)])
        row = held.get(key) or dict(level=level, id=key[1],
                                    note=f"{'main' if level == '2' else 'upper'} level, the plan's length")
        rest.append(dict(row, plan_in=f"{inches:.1f}"))
    return _text([{c: r.get(c, "") for c in block_lengths.PLAN_COLUMNS} for r in staging + rest])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="exit 1 if plan_in is stale")
    g.add_argument("--show", action="store_true", help="print the lengths and write nothing")
    args = ap.parse_args(argv)
    try:
        reader = anyplan()
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
        main_upper = main_upper_lengths(plan) if whole else None
        if args.show:
            for b in sorted(lengths):
                print(f"{b:24} {lengths[b]:7.1f} in")
            for b, (level, inches, _sensor) in sorted((main_upper or {}).items()):
                print(f"{b:24} {inches:7.1f} in  level {level}")
            return 0
        if not whole:
            have = block_lengths.plan_lengths(LENGTHS)
            bad = [f"{b}: plan_in {have[b] if b in have else 'missing'}, the part gives {v:.1f}"
                   for b, v in sorted(lengths.items()) if b not in have or abs(have[b] - round(v, 1)) > 1e-9]
            print(f"plan lengths: no plan file {PLAN.name}; the OS rows only are checked")
            for b in bad:
                print(f"{LENGTHS.name}: {b}", file=sys.stderr)
            return 1 if bad else 0
        text = csv_with(lengths, main_upper, parts={r["user_name"]: r["part_of"] for _n, r in sdm.part_lines()})
    except (LengthError, sdm.StagingMapError, sdm.lc.BuildError, reader.PlanError, railroad.FactsError) as exc:
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
