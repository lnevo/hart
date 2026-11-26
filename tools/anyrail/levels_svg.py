#!/usr/bin/env python3
"""Draw the staging, main and upper levels of an AnyRail plan to scale, as SVG fragments.

    python3 tools/anyrail/levels_svg.py [PLAN.any] [OUT_DIR] [--check]

Reads the plan with the schematic-maps plugin's plan reader (`schematic anyplan`, its schematic.anyplan module, from
the pinned submodule) and writes staging.svg, main.svg, upper.svg and levels_meta.json into OUT_DIR
(`tools/anyrail/levels/`, committed, so the track plan page builds without the plan). `--check` writes nothing and
stops when the committed files differ from what the plan gives, and prints SKIPPED, passing, when the default plan
is not on this machine (never in CI). PLAN.any is DEFAULT_PLAN unless given. The plan is the owner's, private, and never committed;
only track is read, so custom objects, scenery and buildings (third-party copyright) never reach a drawing.

Coordinates are plan centimetres, y down, so the three drawings line up. What a drawing holds:

- A level is a height. The turnouts of the plan sit at three heights (staging, main, upper); a flat flex piece goes to
  the level it lies at.
- A flex piece whose ends differ in height is a ramp (the helix and the climb to the upper level), drawn dotted. A
  helix track that starts on staging is drawn on the level it reaches for its top layer, down to where it first
  passes under itself or under the other helix track, and on staging below that. A staging climb of less than one
  turn is split at HELIX_CUT_CM, the cut the schematic parts the levels at (also each track's share in
  levels_meta.json); a climb that starts higher is drawn on the level it climbs from.
- A turnout is labelled with the owner's switch number from the relabel map of the staging or main_upper section of
  plan_overrides.json (the plan's T number is the part's place in the file); one the maps do not name carries its T
  number.
"""
from __future__ import annotations

import argparse
import collections
import importlib
import json
import math
import os
import re
import sys
import types
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Literal, NamedTuple, NotRequired, TypedDict

SCHEMATIC_TOOLS = Path(__file__).resolve().parents[1] / "schematic"

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import railroad_facts  # noqa: E402

Level = Literal["staging", "main", "upper"]
LEVELS: tuple[Level, Level, Level] = ("staging", "main", "upper")          # lowest to highest


def le_common() -> types.ModuleType:
    """tools/schematic/le_common.py, which finds the pinned schematic-maps plugin. Imported only when the plan is read,
    so levels_page.py (which imports this file for switch_key) never loads the Layout Editor build's modules."""
    if str(SCHEMATIC_TOOLS) not in sys.path:
        sys.path.insert(0, str(SCHEMATIC_TOOLS))
    return importlib.import_module("le_common")


def anyplan() -> types.ModuleType:
    """The plugin's plan reader, schematic.anyplan (le_common.plugin_module: the pinned submodule, or SCHEMATIC_PLUGIN;
    le_common.BuildError when it is missing, off its pin or has no such module)."""
    module: types.ModuleType = le_common().plugin_module("anyplan")
    return module


def switch_key(label: str) -> tuple[int, str]:
    """Sort key for switch labels: by the leading number ("7", "101A/103A", "211A"), then the text; T labels last."""
    m = re.match(r"\d+", label)
    return (int(m.group()) if m else 10 ** 6, label)


OVERLAP_CM = 1.5        # a helix track lies this close in plan to where it ran one turn higher
SELF_GAP_CM = 100.0     # ... and that far back along the track, so a piece's own next points never count
CLEAR_CM = 1.0          # another helix track this much higher where they cross is over this one
HELIX_CUT_CM = -5.0     # the height that parts staging's graph from the main and upper graph (anyplan --cut -5)
SNAP_CM = 0.5           # a flat part this close to a level's height is on that level
CM_PER_IN = 2.54
DEFAULT_PLAN = Path.home() / "Documents/Layout/Lee Nevo Design Version 5.3c.any"
OVERRIDES: dict[Level, str] = {"staging": "staging", "main": "main_upper", "upper": "main_upper"}   # plan_overrides.json section
VERSION = re.compile(r"Version (\d+(?:\.\d+)*[a-z]?)\b")
THREEWAY_KEY = re.compile(r"TO_3W\w+-\d+")       # the relabel keys of the three-way's halves: no T number


class LevelsError(ValueError):
    pass


# The plan as the schematic-maps plugin's reader (schematic.anyplan.read) gives it: plain dicts, typed here by the
# keys this file reads.
class End(TypedDict):
    x: float
    y: float
    z: float
    a: float                # heading, radians


PartKind = Literal["end", "track", "turnout", "threeway", "double_crossover", "crossing"]


class Part(TypedDict):
    index: int
    kind: PartKind
    ends: list[End]
    curve: Sequence[Sequence[float]] | None     # cubic Bezier control points (x, y) of a two-ended part
    cm: float | None                            # a two-ended part's length
    points: NotRequired[int]                    # a turnout's or three-way's points end


Link = tuple[int, int, int, int]                # (part, end, part, end): two ends that meet


class LevelCut(TypedDict):
    """anyplan.level_cuts: a run that climbs through the cut, its ends and its length on each side."""
    low: tuple[int, int]
    high: tuple[int, int]
    low_cm: float
    high_cm: float


Point = tuple[float, float]
Point3 = tuple[float, float, float]
Segment3 = tuple[Point3, Point3]
Line = tuple[float, float, float, float]        # (x1, y1, x2, y2)


class Cut(NamedTuple):
    """The piece a helix track's top layer ends in, split there: (x, y) points above and below the split, and the
    share of the piece's length above it."""
    piece: int
    upper: list[Point]
    lower: list[Point]
    share: float


class TopLayer(NamedTuple):
    whole: set[int]         # the pieces of the top layer drawn whole
    cut: Cut


class Split(NamedTuple):
    """One level's part of a helix piece split between two levels: its points and its share of the plan length."""
    points: list[Point]
    cm: float


class Assignment(NamedTuple):
    """assign()'s result: each part's level, the helix pieces drawn dotted, the plan's joins, and the pieces a helix
    layer splits between two levels."""
    where: dict[int, Level]
    ramp: set[int]
    links: list[Link]
    partial: dict[int, dict[Level, Split]]


class LevelCounts(TypedDict):
    """A level's entry in levels_meta.json, less its height."""
    switches: int
    crossovers: int
    threeways: int
    flex: int
    flex_m: float
    ramp_m: float
    bbox: list[float]
    labels: list[str]


class HelixTrack(TypedDict):
    foot: str               # the owner's number of the switch at its foot
    top: str                # ... and at its top
    cm: float               # its length along the flex
    below_cut_cm: float     # the part of it below the schematic's cut


class Ramp(TypedDict):
    foot: Level
    top: Level
    flex_m: float


def bezier(ctrl: Sequence[Sequence[float]], n: int = 14) -> list[Point]:
    """Points along the cubic Bezier segments of ``ctrl``, n + 1 per segment."""
    out: list[Point] = []
    for s in range(0, len(ctrl) - 3, 3):
        q = ctrl[s:s + 4]
        for i in range(n + 1):
            t = i / n
            u = 1 - t
            x, y = (u ** 3 * q[0][j] + 3 * u * u * t * q[1][j] + 3 * u * t * t * q[2][j] + t ** 3 * q[3][j]
                    for j in range(2))
            out.append((x, y))
    return out


def poly(pts: Iterable[Sequence[float]]) -> str:
    return " ".join("%.1f,%.1f" % (x, y) for x, y in pts)


def plan_version(path: str | Path) -> str:
    m = VERSION.search(Path(path).name)
    if not m:
        raise LevelsError(f"{Path(path).name}: no 'Version 5.3c' style plan version in the file name")
    return m.group(1)


def _height_span(p: Part) -> float:
    return max(e["z"] for e in p["ends"]) - min(e["z"] for e in p["ends"])


def _cm(p: Part) -> float:
    """A two-ended part's length; the plan reader gives one for every two-ended part."""
    if p["cm"] is None:
        raise LevelsError(f"T{p['index']} has no length in the plan")
    return p["cm"]


def level_heights(parts: Sequence[Part]) -> dict[Level, float]:
    """{level: height cm} from the heights the plan's turnouts sit at: three, the middle one the main level at 0."""
    heights = sorted({round(p["ends"][0]["z"], 2) for p in parts if len(p["ends"]) > 2})
    if len(heights) != len(LEVELS) or abs(heights[1]) > SNAP_CM:
        raise LevelsError(f"the turnouts sit at {heights} cm; expected three heights with main at 0")
    for p in parts:
        if len(p["ends"]) > 2 and _height_span(p) > anyplan().LEVEL_CM:
            raise LevelsError(f"T{p['index']} is a turnout that is not level")
    return dict(zip(LEVELS, heights))


def nearest_level(z: float, heights: Mapping[Level, float], what: str) -> Level:
    level = min(heights, key=lambda k: abs(heights[k] - z))
    if abs(heights[level] - z) > SNAP_CM:
        raise LevelsError(f"{what} lies at {z:.2f} cm, not at a level ({heights})")
    return level


def helix_chains(parts: Sequence[Part], links: Iterable[Link]) -> list[set[int]]:
    """The sloped flex pieces joined end to end: a list of sets of part indices, one per helix track. A level piece
    partway up a helix is not part of a chain and stops the build in assign() ('not at a level'): plans 5.3b and 5.3c
    have none, and the drawing would need a rule for one."""
    sloped = {p["index"] for p in parts if len(p["ends"]) == 2 and _height_span(p) > anyplan().LEVEL_CM}
    root = {i: i for i in sloped}

    def find(x: int) -> int:
        while root[x] != x:
            root[x] = root[root[x]]
            x = root[x]
        return x
    for a, _, b, _ in links:
        if a in sloped and b in sloped:
            root[find(a)] = find(b)
    groups: dict[int, set[int]] = collections.defaultdict(set)
    for i in sloped:
        groups[find(i)].add(i)
    return sorted(groups.values(), key=min)


def helix_walk(parts: Sequence[Part], links: Iterable[Link], chain: set[int]) -> list[tuple[int, list[Point3]]]:
    """A helix track's pieces from its highest end down: [(piece, points)], each piece's points (x, y, z) in walking
    order."""
    nxt: dict[int, set[int]] = collections.defaultdict(set)
    for a, _ea, b, _eb in links:
        if a in chain and b in chain:
            nxt[a].add(b)
            nxt[b].add(a)
    ends = list(chain) if len(chain) == 1 else [i for i in chain if len(nxt[i]) < 2]
    if len(ends) not in (1, 2):
        raise LevelsError(f"the helix track of T{min(chain)} does not form one run (its ends are "
                          f"{', '.join('T%d' % i for i in sorted(ends))})")
    start = max(ends, key=lambda i: max(e["z"] for e in parts[i]["ends"]))
    top_end = max(parts[start]["ends"], key=lambda e: e["z"])
    here: int | None = start
    last: Point = (top_end["x"], top_end["y"])
    seen: set[int] = set()
    out: list[tuple[int, list[Point3]]] = []
    while here is not None:
        curve = parts[here]["curve"]
        if not curve:
            raise LevelsError(f"T{here} has no curve in the plan")
        pts = bezier(curve)
        if math.dist(pts[-1], last) < math.dist(pts[0], last):
            pts = pts[::-1]
        e0, e1 = sorted(parts[here]["ends"], key=lambda e: math.dist((e["x"], e["y"]), pts[0]))
        n = max(len(pts) - 1, 1)        # the height runs evenly along the piece from the end the walk enters at
        out.append((here, [(q[0], q[1], e0["z"] + (e1["z"] - e0["z"]) * k / n) for k, q in enumerate(pts)]))
        seen.add(here)
        last = pts[-1]
        here = next(iter(nxt[here] - seen), None)
    return out


def _crossing(p1: Sequence[float], p2: Sequence[float], q1: Sequence[float],
              q2: Sequence[float]) -> tuple[float, float] | None:
    """(t, u) where segment p1-p2 crosses segment q1-q2 at p1 + t (p2 - p1) = q1 + u (q2 - q1), or None when they do
    not cross (touching at an end, or running along each other, does not count)."""
    rx, ry = p2[0] - p1[0], p2[1] - p1[1]
    sx, sy = q2[0] - q1[0], q2[1] - q1[1]
    den = rx * sy - ry * sx
    if abs(den) < 1e-12:
        return None
    qx, qy = q1[0] - p1[0], q1[1] - p1[1]
    t, u = (qx * sy - qy * sx) / den, (qx * ry - qy * rx) / den
    return (t, u) if 0 < t < 1 and 0 < u < 1 else None


def _crosses(p1: Sequence[float], p2: Sequence[float], q1: Sequence[float], q2: Sequence[float]) -> bool:
    """True when segment p1-p2 crosses segment q1-q2."""
    return _crossing(p1, p2, q1, q2) is not None


def _to_segment(q: Sequence[float], a: Sequence[float], b: Sequence[float]) -> float:
    """Distance in plan from point q to segment a-b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    d2 = dx * dx + dy * dy
    t = 0.0 if d2 == 0 else max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / d2))
    return math.dist(q[:2], (a[0] + t * dx, a[1] + t * dy))


def top_layer(walk: Sequence[tuple[int, Sequence[Point3]]], others: Sequence[Segment3] = ()) -> TopLayer | None:
    """The top layer of one helix track, as the level it reaches draws it: its walk down to the first point where it
    passes under track: its own track more than SELF_GAP_CM back along it (within OVERLAP_CM in plan of that track,
    or crossing it), or a segment of another helix track in `others` that is more than CLEAR_CM higher where they
    cross. None when the track never passes under anything (less than one turn).
    """
    segs: list[tuple[Point3, Point3, float]] = []   # (a, b, distance along the track at b)
    whole: set[int] = set()
    s = 0.0
    for piece, pts in walk:
        run = sum(math.dist(a[:2], b[:2]) for a, b in zip(pts, pts[1:])) or 1.0
        done = 0.0
        for k in range(1, len(pts)):
            a, q = pts[k - 1], pts[k]
            step = math.dist(a[:2], q[:2])
            s += step
            old = [o for o in segs if s - o[2] > SELF_GAP_CM]
            under = (any(_to_segment(q, o[0], o[1]) < OVERLAP_CM or _crosses(a, q, o[0], o[1]) for o in old)
                     or any(_higher(a, q, o) for o in others))
            if under:
                flat: list[Point] = [(p[0], p[1]) for p in pts]
                return TopLayer(whole, Cut(piece, flat[:k], flat[k - 1:], done / run))
            segs.append((a, q, s))
            done += step
        whole.add(piece)
    return None


def _higher(a: Point3, q: Point3, other: Segment3) -> bool:
    """True when segment `other` ((x, y, z), (x, y, z)) crosses a-q and lies more than CLEAR_CM above it there."""
    hit = _crossing(a, q, other[0], other[1])
    if hit is None:
        return False
    t, u = hit
    return other[0][2] + u * (other[1][2] - other[0][2]) > a[2] + t * (q[2] - a[2]) + CLEAR_CM


def top_layers(parts: Sequence[Part], links: Sequence[Link], chains: Sequence[set[int]]) -> dict[int, TopLayer | None]:
    """{chain index: top layer or None} for the helix tracks from staging: each cut where it first passes under
    itself or under a higher part of another track. Every other track is taken whole, so the result does not depend
    on the order the tracks are taken in."""
    walks = {n: helix_walk(parts, links, c) for n, c in enumerate(chains)}
    segs = {n: [(a, b) for _piece, pts in w for a, b in zip(pts, pts[1:])] for n, w in walks.items()}
    return {n: top_layer(w, [o for m in walks if m != n for o in segs[m]]) for n, w in walks.items()}


def _flat_levels(parts: Sequence[Part], heights: Mapping[Level, float]) -> dict[int, Level]:
    """{part index: level} for every part whose ends lie at one height."""
    return {p["index"]: nearest_level(p["ends"][0]["z"], heights, f"T{p['index']}")
            for p in parts if _height_span(p) <= anyplan().LEVEL_CM}


def _helix_spans(parts: Sequence[Part], chains: Sequence[set[int]],
                 heights: Mapping[Level, float]) -> list[tuple[Level, Level]]:
    """(top, bottom) level of each helix track; one that does not climb stops."""
    span: list[tuple[Level, Level]] = []
    for chain in chains:
        top = nearest_level(max(e["z"] for i in chain for e in parts[i]["ends"]), heights, "the top of a helix track")
        bottom = nearest_level(min(e["z"] for i in chain for e in parts[i]["ends"]), heights,
                               "the foot of a helix track")
        if LEVELS.index(top) <= LEVELS.index(bottom):
            raise LevelsError(f"a helix track runs from {bottom} to {top}; it must climb")
        span.append((top, bottom))
    return span


def _helix_piece_level(p: Part, top: Level, bottom: Level, layer: TopLayer | None) -> Level:
    """The level a helix piece is drawn on. A helix track from staging is drawn on the level it reaches for its top
    layer and on staging below it (the piece the layer ends in is split, see Assignment.partial); a staging climb of
    less than one turn is split at HELIX_CUT_CM; any other climb is drawn on the level it climbs from."""
    if layer:
        return top if p["index"] in layer.whole else bottom
    if bottom == LEVELS[0]:
        return bottom if sum(e["z"] for e in p["ends"]) / 2 < HELIX_CUT_CM else top
    return bottom


def assign(parts: Sequence[Part], heights: Mapping[Level, float]) -> Assignment:
    """{part index: level} for every flat part and every helix piece (the dotted ones are `ramp`)."""
    links: list[Link] = anyplan().joins(parts)[0]
    where = _flat_levels(parts, heights)
    ramp: set[int] = set()
    partial: dict[int, dict[Level, Split]] = {}
    chains = helix_chains(parts, links)
    span = _helix_spans(parts, chains, heights)
    from_staging = [n for n, (_t, b) in enumerate(span) if b == LEVELS[0]]
    layers = top_layers(parts, links, [chains[n] for n in from_staging])
    layer_of = {n: layers[k] for k, n in enumerate(from_staging)}
    for n, chain in enumerate(chains):
        top, bottom = span[n]
        layer = layer_of.get(n)
        if layer:
            cut = layer.cut
            cm = _cm(parts[cut.piece])
            partial[cut.piece] = {top: Split(cut.upper, cm * cut.share), bottom: Split(cut.lower, cm * (1 - cut.share))}
        for i in chain:
            where[i] = _helix_piece_level(parts[i], top, bottom, layer)
            ramp.add(i)
    if len(where) != len(parts):
        raise LevelsError("parts left without a level: %s" % sorted(set(range(len(parts))) - set(where)))
    return Assignment(where, ramp, links, partial)


def labels(level: Level) -> dict[str, str]:
    """{plan label: owner's switch number} for a level, from its section of plan_overrides.json."""
    return railroad_facts.read_plan_overrides(railroad_facts.Sources.under().plan_overrides, OVERRIDES[level]).relabel


def label_of(p: Part, names: Mapping[str, str]) -> str:
    t = "T%d" % p["index"]
    if p["kind"] == "threeway":
        if sum(1 for k in names if THREEWAY_KEY.fullmatch(k)) > 2:
            raise LevelsError("the relabel map names more than one three-way on a level; "
                              "label_of cannot tell them apart")
        halves = sorted(v for k, v in names.items() if THREEWAY_KEY.fullmatch(k))
        return "/".join(halves) if halves else t
    return names.get(t, t)


def _double_crossover_lines(p: Part, e: Sequence[Point]) -> list[Line]:
    """A double crossover's four rails and the X between them."""
    # a side is the two ends that lie closest together (a track spacing apart, against the crossover's length);
    # the end headings are not along the track in every file, so they are not used
    pairings = [([0, m], [i for i in range(1, 4) if i != m]) for m in (1, 2, 3)]
    spread = sorted((math.dist(e[a[0]], e[a[1]]) + math.dist(e[b[0]], e[b[1]]), a, b) for a, b in pairings)
    if spread[1][0] - spread[0][0] < 1e-6:
        raise LevelsError(f"T{p['index']}: cannot tell the two sides of the double crossover")
    _, s1, s2 = spread[0]
    out: list[Line] = []
    # the track runs from one side's middle to the other's; the end headings are not along it in every file
    c1 = [sum(e[i][k] for i in s1) / 2 for k in (0, 1)]
    c2 = [sum(e[i][k] for i in s2) / 2 for k in (0, 1)]
    run = math.dist(c1, c2)
    if run < 1e-6:
        raise LevelsError(f"T{p['index']}: the double crossover's two sides sit at the same place")
    ux, uy = (c2[0] - c1[0]) / run, (c2[1] - c1[1]) / run
    if abs(abs((e[s1[0]][0] - e[s1[1]][0]) * -uy + (e[s1[0]][1] - e[s1[1]][1]) * ux)) < 1e-6:
        raise LevelsError(f"T{p['index']}: the double crossover's two rails lie on one line")

    def mid(q: Point, r: Point, f: float) -> Point:
        return (q[0] + (r[0] - q[0]) * f, q[1] + (r[1] - q[1]) * f)
    for i in s1:        # a rail runs straight across to the end on the other side that lies closest abeam
        j = min(s2, key=lambda m: abs((e[m][0] - e[i][0]) * -uy + (e[m][1] - e[i][1]) * ux))
        out.append(e[i] + e[j])
        other = [m for m in s2 if m != j][0]
        out.append(mid(e[i], e[other], 0.3) + mid(e[i], e[other], 0.7))
    return out


def turnout_lines(p: Part) -> list[Line]:
    """[(x1, y1, x2, y2)] drawing a turnout: the toe to each leg and the legs to each other; a three-way's points
    to its three legs; a double crossover's four rails and the X between them."""
    e: list[Point] = [(a["x"], a["y"]) for a in p["ends"]]
    k = p["kind"]
    if k == "turnout":
        toe = e[p["points"]]
        legs = [e[i] for i in range(3) if i != p["points"]]
        return [toe + leg for leg in legs] + [legs[0] + legs[1]]
    if k == "threeway":
        toe = e[p["points"]]
        return [toe + e[i] for i in range(4) if i != p["points"]]
    if k == "double_crossover":
        return _double_crossover_lines(p, e)
    raise LevelsError(f"T{p['index']} is a {k}, which this drawing has no symbol for")


class _Sheet:
    """One level's drawing as draw() builds it: the SVG lines, every drawn point, and the lengths and labels."""

    def __init__(self) -> None:
        self.out: list[str] = []
        self.xs: list[float] = []
        self.ys: list[float] = []
        self.flex_cm, self.flex_n, self.ramp_cm = 0.0, 0, 0.0
        self.switches: list[str] = []

    def take(self, pts: Iterable[Sequence[float]]) -> None:
        for q in pts:
            self.xs.append(q[0])
            self.ys.append(q[1])

    def polyline(self, cls: str, pts: Sequence[Point]) -> None:
        self.take(pts)
        self.out.append('<polyline class="%s" points="%s"/>' % (cls, poly(pts)))

    def turnout(self, p: Part, label: str) -> None:
        for x1, y1, x2, y2 in turnout_lines(p):
            self.out.append('<line class="to" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (x1, y1, x2, y2))
        self.take([(a["x"], a["y"]) for a in p["ends"]])
        cx = sum(a["x"] for a in p["ends"]) / len(p["ends"])
        cy = sum(a["y"] for a in p["ends"]) / len(p["ends"])
        self.out.append('<text class="tl" x="%.1f" y="%.1f">%s</text>' % (cx + 3, cy - 3, label))
        self.switches.append(label)

    def bbox(self) -> list[float]:
        return [round(min(self.xs), 1), round(min(self.ys), 1), round(max(self.xs), 1), round(max(self.ys), 1)]


def _draw_part(sheet: _Sheet, p: Part, ramp: set[int], names: Mapping[str, str]) -> None:
    """Draw one part on its level: flex as a polyline (dotted for a ramp), a turnout as lines and its label."""
    if len(p["ends"]) == 2:
        if not p["curve"]:
            raise LevelsError(f"T{p['index']} has no curve in the plan")
        cm = _cm(p)
        if p["index"] in ramp:
            sheet.polyline("ramp", bezier(p["curve"]))
            sheet.ramp_cm += cm
        else:
            sheet.polyline("trk", bezier(p["curve"]))
            sheet.flex_cm += cm
            sheet.flex_n += 1
        return
    if len(p["ends"]) < 3:
        raise LevelsError(f"T{p['index']} has {len(p['ends'])} end; a buffer stop is not drawn")
    sheet.turnout(p, label_of(p, names))


def draw(parts: Sequence[Part], where: Mapping[int, Level], ramp: set[int], level: Level,
         partial: Mapping[int, Mapping[Level, Split]] | None = None) -> tuple[str, LevelCounts]:
    """(svg text, counts) of one level. partial: the helix pieces split between two levels, drawn on each from its own
    points and counted at its share of the piece's plan length."""
    partial = partial or {}
    names = labels(level)
    sheet = _Sheet()
    for by_level in partial.values():
        split = by_level.get(level)
        if split is not None and len(split.points) > 1:
            sheet.polyline("ramp", split.points)
            sheet.ramp_cm += split.cm
    for p in parts:
        if where[p["index"]] == level and p["index"] not in partial:
            _draw_part(sheet, p, ramp, names)
    on_level = [p for p in parts if where[p["index"]] == level]
    counts = LevelCounts(switches=len(sheet.switches),
                         crossovers=sum(1 for p in on_level if p["kind"] == "double_crossover"),
                         threeways=sum(1 for p in on_level if p["kind"] == "threeway"),
                         flex=sheet.flex_n, flex_m=round(sheet.flex_cm / 100, 2), ramp_m=round(sheet.ramp_cm / 100, 2),
                         bbox=sheet.bbox(), labels=sorted(sheet.switches, key=switch_key))
    return "\n".join(sheet.out) + "\n", counts


def _switch_name(p: Part, heights: Mapping[Level, float]) -> str:
    """The owner's number of a switch, from the relabel map of the level it sits at."""
    return label_of(p, labels(nearest_level(p["ends"][0]["z"], heights, f"T{p['index']}")))


def helix_tracks(parts: Sequence[Part], links: Sequence[Link], heights: Mapping[Level, float]) -> list[HelixTrack]:
    """Each helix track from the plugin's level_cuts, named by the owner's numbers of the switches at its ends."""
    out: list[HelixTrack] = []
    cuts: list[LevelCut] = anyplan().level_cuts(parts, links, HELIX_CUT_CM)
    for c in cuts:
        foot, top = (_switch_name(parts[part], heights) for part, _end in (c["low"], c["high"]))
        out.append(HelixTrack(foot=foot, top=top, cm=round(c["low_cm"] + c["high_cm"], 1),
                              below_cut_cm=round(c["low_cm"], 1)))
    return sorted(out, key=lambda t: t["foot"])


def ramps(parts: Sequence[Part], links: Sequence[Link], heights: Mapping[Level, float]) -> list[Ramp]:
    """Each helix or climb: the levels its ends sit at and the flex length of its pieces."""
    out: list[Ramp] = []
    for chain in helix_chains(parts, links):
        zs = [e["z"] for i in chain for e in parts[i]["ends"]]
        out.append(Ramp(foot=nearest_level(min(zs), heights, "a ramp"), top=nearest_level(max(zs), heights, "a ramp"),
                        flex_m=round(sum(_cm(parts[i]) for i in chain) / 100, 2)))
    return sorted(out, key=lambda r: (LEVELS.index(r["foot"]), LEVELS.index(r["top"]), r["flex_m"]))


def _max_grade_pct(parts: Sequence[Part], ramp: Iterable[int]) -> float:
    """The steepest ramp piece's grade, per cent."""
    return round(max(100 * abs(parts[i]["ends"][0]["z"] - parts[i]["ends"][1]["z"]) / _cm(parts[i])
                     for i in ramp), 2)


def build(plan_path: str | Path) -> dict[str, str]:
    """{file name: text} of every output."""
    parts: list[Part] = anyplan().read(plan_path)
    heights = level_heights(parts)
    where, ramp, links, partial = assign(parts, heights)
    files: dict[str, str] = {}
    counts: dict[Level, LevelCounts] = {}
    for level in LEVELS:
        files[level + ".svg"], counts[level] = draw(parts, where, ramp, level, partial)
    meta = dict(plan=plan_version(plan_path), parts=len(parts), cut_cm=HELIX_CUT_CM,
                levels={level: dict(height_cm=heights[level], **c) for level, c in counts.items()},
                helix=helix_tracks(parts, links, heights), ramps=ramps(parts, links, heights),
                max_grade_pct=_max_grade_pct(parts, ramp))
    drawn = sum(c["switches"] for c in counts.values())
    total = sum(1 for p in parts if len(p["ends"]) > 2)
    flat = sum(c["flex"] for c in counts.values())
    flex_all = sum(1 for p in parts if len(p["ends"]) == 2 and p["index"] not in ramp)
    if drawn != total or flat != flex_all:      # every part is drawn once
        raise LevelsError(f"drew {drawn} of {total} switches and {flat} of {flex_all} flex pieces")
    files["levels_meta.json"] = json.dumps(meta, indent=1, sort_keys=True) + "\n"
    return files


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("plan", nargs="?", default=str(DEFAULT_PLAN), help="the AnyRail .any file (default: %(default)s)")
    ap.add_argument("out", nargs="?", default=str(Path(__file__).resolve().parent / "levels"))
    ap.add_argument("--check", action="store_true", help="write nothing; fail if the committed files differ")
    a = ap.parse_args(argv)
    if a.check and not Path(a.plan).is_file():
        if Path(a.plan) != DEFAULT_PLAN:
            print(f"levels_svg: {a.plan} does not exist", file=sys.stderr)
            return 2
        print(f"levels_svg: SKIPPED, not checked: {a.plan} is not on this machine")
        return 0
    try:
        reader = anyplan()
    except le_common().BuildError as e:
        if a.check and os.environ.get("SCHEMATIC_REQUIRED") != "1":     # as the schematic checks in tools/check.sh
            print(f"levels_svg: SKIPPED, the schematic-maps plugin: {e}")
            return 0
        print(f"levels_svg: the schematic-maps plugin: {e}", file=sys.stderr)
        return 2
    try:
        files = build(a.plan)
    except (LevelsError, reader.PlanError, OSError) as e:
        print(f"levels_svg: {e}", file=sys.stderr)
        return 2
    except ValueError as e:  # an empty level or a plan with no ramps reaches max() or min()
        print(f"levels_svg: the plan has a level or ramp set with no parts ({e})", file=sys.stderr)
        return 2
    out = Path(a.out)
    if a.check:
        stale = [n for n, t in files.items() if not (out / n).is_file() or (out / n).read_text() != t]
        if stale:
            print(f"levels_svg: {', '.join(stale)} in {out} differ from the plan; rerun without --check",
                  file=sys.stderr)
            return 1
        print("levels_svg: the committed drawings match the plan")
        return 0
    out.mkdir(parents=True, exist_ok=True)
    for n, t in files.items():
        (out / n).write_text(t)
    print(f"wrote {len(files)} files to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
