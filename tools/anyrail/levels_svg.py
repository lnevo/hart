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
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "schematic"))
import le_common  # noqa: E402  the pinned schematic-maps plugin, whose schematic.anyplan reads the plan

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import railroad_facts  # noqa: E402

LEVELS = ("staging", "main", "upper")          # lowest to highest


def anyplan():
    """The plugin's plan reader, schematic.anyplan (le_common.plugin_module: the pinned submodule, or SCHEMATIC_PLUGIN;
    le_common.BuildError when it is missing or off its pin)."""
    return le_common.plugin_module("anyplan")


def switch_key(label):
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
OVERRIDES = {"staging": "staging", "main": "main_upper", "upper": "main_upper"}   # level: plan_overrides.json section
VERSION = re.compile(r"Version (\d+(?:\.\d+)*[a-z]?)\b")
THREEWAY_KEY = re.compile(r"TO_3W\w+-\d+")       # the relabel keys of the three-way's halves: no T number


class LevelsError(ValueError):
    pass


def bezier(ctrl, n=14):
    out = []
    for s in range(0, len(ctrl) - 3, 3):
        q = ctrl[s:s + 4]
        for i in range(n + 1):
            t = i / n
            u = 1 - t
            out.append([u ** 3 * q[0][j] + 3 * u * u * t * q[1][j] + 3 * u * t * t * q[2][j] + t ** 3 * q[3][j]
                        for j in range(2)])
    return out


def poly(pts):
    return " ".join("%.1f,%.1f" % (x, y) for x, y in pts)


def plan_version(path) -> str:
    m = VERSION.search(Path(path).name)
    if not m:
        raise LevelsError(f"{Path(path).name}: no 'Version 5.3c' style plan version in the file name")
    return m.group(1)


def level_heights(parts) -> dict[str, float]:
    """{level: height cm} from the heights the plan's turnouts sit at: three, the middle one the main level at 0."""
    heights = sorted({round(p["ends"][0]["z"], 2) for p in parts if len(p["ends"]) > 2})
    if len(heights) != len(LEVELS) or abs(heights[1]) > SNAP_CM:
        raise LevelsError(f"the turnouts sit at {heights} cm; expected three heights with main at 0")
    for p in parts:
        if len(p["ends"]) > 2 and max(e["z"] for e in p["ends"]) - min(e["z"] for e in p["ends"]) > anyplan().LEVEL_CM:
            raise LevelsError(f"T{p['index']} is a turnout that is not level")
    return dict(zip(LEVELS, heights))


def nearest_level(z, heights, what) -> str:
    level = min(heights, key=lambda k: abs(heights[k] - z))
    if abs(heights[level] - z) > SNAP_CM:
        raise LevelsError(f"{what} lies at {z:.2f} cm, not at a level ({heights})")
    return level


def helix_chains(parts, links):
    """The sloped flex pieces joined end to end: a list of sets of part indices, one per helix track. A level piece
    partway up a helix is not part of a chain and stops the build in assign() ('not at a level'): plans 5.3b and 5.3c
    have none, and the drawing would need a rule for one."""
    sloped = {p["index"] for p in parts if len(p["ends"]) == 2
              and abs(p["ends"][0]["z"] - p["ends"][1]["z"]) > anyplan().LEVEL_CM}
    root = {i: i for i in sloped}

    def find(x):
        while root[x] != x:
            root[x] = root[root[x]]
            x = root[x]
        return x
    for a, _, b, _ in links:
        if a in sloped and b in sloped:
            root[find(a)] = find(b)
    groups = collections.defaultdict(set)
    for i in sloped:
        groups[find(i)].add(i)
    return sorted(groups.values(), key=min)


def helix_walk(parts, links, chain):
    """A helix track's pieces from its highest end down: [(piece, points)], each piece's points (x, y, z) in walking
    order."""
    nxt = collections.defaultdict(set)
    for a, _ea, b, _eb in links:
        if a in chain and b in chain:
            nxt[a].add(b)
            nxt[b].add(a)
    ends = list(chain) if len(chain) == 1 else [i for i in chain if len(nxt[i]) < 2]
    if len(ends) not in (1, 2):
        raise LevelsError(f"the helix track of T{min(chain)} does not form one run (its ends are "
                          f"{', '.join('T%d' % i for i in sorted(ends))})")
    here = max(ends, key=lambda i: max(e["z"] for e in parts[i]["ends"]))
    top_end = max(parts[here]["ends"], key=lambda e: e["z"])
    last, seen, out = (top_end["x"], top_end["y"]), set(), []
    while here is not None:
        if not parts[here]["curve"]:
            raise LevelsError(f"T{here} has no curve in the plan")
        pts = bezier(parts[here]["curve"])
        if math.dist(pts[-1], last) < math.dist(pts[0], last):
            pts = pts[::-1]
        e0, e1 = sorted(parts[here]["ends"], key=lambda e: math.dist((e["x"], e["y"]), pts[0]))
        n = max(len(pts) - 1, 1)        # the height runs evenly along the piece from the end the walk enters at
        out.append((here, [(q[0], q[1], e0["z"] + (e1["z"] - e0["z"]) * k / n) for k, q in enumerate(pts)]))
        seen.add(here)
        last = pts[-1]
        here = next(iter(nxt[here] - seen), None)
    return out


def _crossing(p1, p2, q1, q2):
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


def _crosses(p1, p2, q1, q2):
    """True when segment p1-p2 crosses segment q1-q2."""
    return _crossing(p1, p2, q1, q2) is not None


def _to_segment(q, a, b):
    """Distance in plan from point q to segment a-b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    d2 = dx * dx + dy * dy
    t = 0.0 if d2 == 0 else max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / d2))
    return math.dist(q[:2], (a[0] + t * dx, a[1] + t * dy))


def top_layer(walk, others=()):
    """The top layer of one helix track, as the level it reaches draws it: its walk down to the first point where it
    passes under track: its own track more than SELF_GAP_CM back along it (within OVERLAP_CM in plan of that track,
    or crossing it), or a segment of another helix track in `others` that is more than CLEAR_CM higher where they
    cross. Returns (whole, cut), or None when the track never passes under anything (less than one turn): the pieces
    drawn whole, and (piece, upper points, lower points, upper share) for the piece the layer ends in, split there,
    as (x, y) points, with the share of the piece's length above the split.
    """
    segs, whole, s = [], set(), 0.0                 # segs: [(a, b, distance along the track at b)]
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
                flat = [p[:2] for p in pts]
                return whole, (piece, flat[:k], flat[k - 1:], done / run)
            segs.append((a, q, s))
            done += step
        whole.add(piece)
    return None


def _higher(a, q, other):
    """True when segment `other` ((x, y, z), (x, y, z)) crosses a-q and lies more than CLEAR_CM above it there."""
    hit = _crossing(a, q, other[0], other[1])
    if hit is None:
        return False
    t, u = hit
    return other[0][2] + u * (other[1][2] - other[0][2]) > a[2] + t * (q[2] - a[2]) + CLEAR_CM


def top_layers(parts, links, chains):
    """{chain index: (whole, cut) or None} for the helix tracks from staging: each cut where it first passes under
    itself or under a higher part of another track. Every other track is taken whole, so the result does not depend
    on the order the tracks are taken in."""
    walks = {n: helix_walk(parts, links, c) for n, c in enumerate(chains)}
    segs = {n: [(a, b) for _piece, pts in w for a, b in zip(pts, pts[1:])] for n, w in walks.items()}
    return {n: top_layer(w, [o for m in walks if m != n for o in segs[m]]) for n, w in walks.items()}


def assign(parts, heights):
    """{part index: level} for every flat part and every helix piece (the dotted ones are `ramp` below)."""
    links, _ = anyplan().joins(parts)
    where, ramp, partial = {}, set(), {}
    for p in parts:
        zs = [e["z"] for e in p["ends"]]
        if max(zs) - min(zs) <= anyplan().LEVEL_CM:
            where[p["index"]] = nearest_level(zs[0], heights, f"T{p['index']}")
    chains = helix_chains(parts, links)
    span = []
    for chain in chains:
        top = nearest_level(max(e["z"] for i in chain for e in parts[i]["ends"]), heights, "the top of a helix track")
        bottom = nearest_level(min(e["z"] for i in chain for e in parts[i]["ends"]), heights,
                               "the foot of a helix track")
        if LEVELS.index(top) <= LEVELS.index(bottom):
            raise LevelsError(f"a helix track runs from {bottom} to {top}; it must climb")
        span.append((top, bottom))
    from_staging = [n for n, (_t, b) in enumerate(span) if b == LEVELS[0]]
    layers = top_layers(parts, links, [chains[n] for n in from_staging])
    layer_of = {n: layers[k] for k, n in enumerate(from_staging)}
    for n, chain in enumerate(chains):
        top, bottom = span[n]
        layer = layer_of.get(n)
        if layer:
            whole, (piece, upper, lower, share) = layer
            cm = parts[piece]["cm"]
            partial[piece] = {top: (upper, cm * share), bottom: (lower, cm * (1 - share))}
        for i in chain:
            # a helix track from staging is drawn on the level it reaches for its top layer and on staging below it
            # (the piece the layer ends in is split, see `partial`); a staging climb of less than one turn is split at
            # HELIX_CUT_CM; any other climb is drawn on the level it climbs from
            if layer:
                where[i] = top if i in whole else bottom
            elif bottom == LEVELS[0]:
                where[i] = bottom if sum(e["z"] for e in parts[i]["ends"]) / 2 < HELIX_CUT_CM else top
            else:
                where[i] = bottom
            ramp.add(i)
    if len(where) != len(parts):
        raise LevelsError("parts left without a level: %s" % sorted(set(range(len(parts))) - set(where)))
    return where, ramp, links, partial


def labels(level) -> dict[str, str]:
    """{plan label: owner's switch number} for a level, from its section of plan_overrides.json."""
    return railroad_facts.read_plan_overrides(railroad_facts.Sources.under().plan_overrides, OVERRIDES[level]).relabel


def label_of(p, names):
    t = "T%d" % p["index"]
    if p["kind"] == "threeway":
        if sum(1 for k in names if THREEWAY_KEY.fullmatch(k)) > 2:
            raise LevelsError("the relabel map names more than one three-way on a level; "
                              "label_of cannot tell them apart")
        halves = sorted(v for k, v in names.items() if THREEWAY_KEY.fullmatch(k))
        return "/".join(halves) if halves else t
    return names.get(t, t)


def turnout_lines(p):
    """[(x1, y1, x2, y2)] drawing a turnout: the toe to each leg and the legs to each other; a three-way's points
    to its three legs; a double crossover's four rails and the X between them."""
    e = [(a["x"], a["y"]) for a in p["ends"]]
    k = p["kind"]
    if k == "turnout":
        toe = e[p["points"]]
        legs = [e[i] for i in range(3) if i != p["points"]]
        return [toe + leg for leg in legs] + [legs[0] + legs[1]]
    if k == "threeway":
        toe = e[p["points"]]
        return [toe + e[i] for i in range(4) if i != p["points"]]
    if k == "double_crossover":
        # a side is the two ends that lie closest together (a track spacing apart, against the crossover's length);
        # the end headings are not along the track in every file, so they are not used
        pairings = [([0, m], [i for i in range(1, 4) if i != m]) for m in (1, 2, 3)]
        spread = sorted((math.dist(e[a[0]], e[a[1]]) + math.dist(e[b[0]], e[b[1]]), a, b) for a, b in pairings)
        if spread[1][0] - spread[0][0] < 1e-6:
            raise LevelsError(f"T{p['index']}: cannot tell the two sides of the double crossover")
        _, s1, s2 = spread[0]
        out = []
        # the track runs from one side's middle to the other's; the end headings are not along it in every file
        c1 = [sum(e[i][k] for i in s1) / 2 for k in (0, 1)]
        c2 = [sum(e[i][k] for i in s2) / 2 for k in (0, 1)]
        run = math.dist(c1, c2)
        if run < 1e-6:
            raise LevelsError(f"T{p['index']}: the double crossover's two sides sit at the same place")
        ux, uy = (c2[0] - c1[0]) / run, (c2[1] - c1[1]) / run
        if abs(abs((e[s1[0]][0] - e[s1[1]][0]) * -uy + (e[s1[0]][1] - e[s1[1]][1]) * ux)) < 1e-6:
            raise LevelsError(f"T{p['index']}: the double crossover's two rails lie on one line")
        for i in s1:        # a rail runs straight across to the end on the other side that lies closest abeam
            j = min(s2, key=lambda m: abs((e[m][0] - e[i][0]) * -uy + (e[m][1] - e[i][1]) * ux))
            out.append(e[i] + e[j])
            other = [m for m in s2 if m != j][0]
            mid = lambda q, r, f: (q[0] + (r[0] - q[0]) * f, q[1] + (r[1] - q[1]) * f)    # noqa: E731
            out.append(mid(e[i], e[other], 0.3) + mid(e[i], e[other], 0.7))
        return out
    raise LevelsError(f"T{p['index']} is a {k}, which this drawing has no symbol for")


def draw(parts, where, ramp, level, partial=None):
    """(svg text, bbox, counts) of one level. partial: {piece: {level: (points, cm)}} for a helix piece split between
    two levels, drawn on each from its own points and counted at its share of the piece's plan length."""
    partial = partial or {}
    names = labels(level)
    out, xs, ys = [], [], []
    flex_cm, flex_n, ramp_cm, switches = 0.0, 0, 0.0, []

    def take(pts):
        xs.extend(q[0] for q in pts)
        ys.extend(q[1] for q in pts)
    for i, by_level in partial.items():
        pts, cm = by_level.get(level, ((), 0.0))
        if len(pts) > 1:
            take(pts)
            out.append('<polyline class="ramp" points="%s"/>' % poly(pts))
            ramp_cm += cm
    for p in parts:
        if where[p["index"]] != level or p["index"] in partial:
            continue
        if len(p["ends"]) == 2:
            if not p["curve"]:
                raise LevelsError(f"T{p['index']} has no curve in the plan")
            pts = bezier(p["curve"])
            take(pts)
            if p["index"] in ramp:
                out.append('<polyline class="ramp" points="%s"/>' % poly(pts))
                ramp_cm += p["cm"]
            else:
                out.append('<polyline class="trk" points="%s"/>' % poly(pts))
                flex_cm += p["cm"]
                flex_n += 1
            continue
        if len(p["ends"]) < 3:
            raise LevelsError(f"T{p['index']} has {len(p['ends'])} end; a buffer stop is not drawn")
        for x1, y1, x2, y2 in turnout_lines(p):
            out.append('<line class="to" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (x1, y1, x2, y2))
        take([(a["x"], a["y"]) for a in p["ends"]])
        cx = sum(a["x"] for a in p["ends"]) / len(p["ends"])
        cy = sum(a["y"] for a in p["ends"]) / len(p["ends"])
        label = label_of(p, names)
        out.append('<text class="tl" x="%.1f" y="%.1f">%s</text>' % (cx + 3, cy - 3, label))
        switches.append(label)
    bbox = [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)]
    counts = dict(switches=len(switches), crossovers=sum(1 for p in parts if where[p["index"]] == level
                                                        and p["kind"] == "double_crossover"),
                  threeways=sum(1 for p in parts if where[p["index"]] == level and p["kind"] == "threeway"),
                  flex=flex_n, flex_m=round(flex_cm / 100, 2), ramp_m=round(ramp_cm / 100, 2), bbox=bbox,
                  labels=sorted(switches, key=switch_key))
    return "\n".join(out) + "\n", counts


def helix_tracks(parts, links, heights):
    """Each helix track as {from, to, cm, below_cut_cm}: the owner's numbers of the switch at its foot and at its top,
    its length along the flex, and the part of it below the schematic's cut."""
    out = []
    for c in anyplan().level_cuts(parts, links, HELIX_CUT_CM):
        names = {}
        for side in ("low", "high"):
            p = parts[c[side][0]]
            level = nearest_level(p["ends"][0]["z"], heights, f"T{p['index']}")
            names[side] = label_of(p, labels(level))
        out.append(dict(foot=names["low"], top=names["high"], cm=round(c["low_cm"] + c["high_cm"], 1),
                        below_cut_cm=round(c["low_cm"], 1)))
    return sorted(out, key=lambda t: t["foot"])


def ramps(parts, links, heights):
    """Each helix or climb as {foot, top, flex_m}: the levels its ends sit at and the flex length of its pieces."""
    out = []
    for chain in helix_chains(parts, links):
        zs = [e["z"] for i in chain for e in parts[i]["ends"]]
        out.append(dict(foot=nearest_level(min(zs), heights, "a ramp"), top=nearest_level(max(zs), heights, "a ramp"),
                        flex_m=round(sum(parts[i]["cm"] for i in chain) / 100, 2)))
    return sorted(out, key=lambda r: (LEVELS.index(r["foot"]), LEVELS.index(r["top"]), r["flex_m"]))


def build(plan_path) -> dict[str, str]:
    """{file name: text} of every output."""
    parts = anyplan().read(plan_path)
    heights = level_heights(parts)
    where, ramp, links, partial = assign(parts, heights)
    files, meta = {}, dict(plan=plan_version(plan_path), parts=len(parts), cut_cm=HELIX_CUT_CM, levels={})
    for level in LEVELS:
        svg, counts = draw(parts, where, ramp, level, partial)
        files[level + ".svg"] = svg
        meta["levels"][level] = dict(height_cm=heights[level], **counts)
    meta["helix"] = helix_tracks(parts, links, heights)
    meta["ramps"] = ramps(parts, links, heights)
    meta["max_grade_pct"] = round(max(100 * abs(parts[i]["ends"][0]["z"] - parts[i]["ends"][1]["z"]) / parts[i]["cm"]
                                      for i in ramp), 2)
    drawn = sum(c["switches"] for c in meta["levels"].values())
    total = sum(1 for p in parts if len(p["ends"]) > 2)
    flat = sum(c["flex"] for c in meta["levels"].values())
    flex_all = sum(1 for p in parts if len(p["ends"]) == 2 and p["index"] not in ramp)
    if drawn != total or flat != flex_all:      # every part is drawn once
        raise LevelsError(f"drew {drawn} of {total} switches and {flat} of {flex_all} flex pieces")
    files["levels_meta.json"] = json.dumps(meta, indent=1, sort_keys=True) + "\n"
    return files


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("plan", nargs="?", default=str(DEFAULT_PLAN), help="the AnyRail .any file (default: %(default)s)")
    ap.add_argument("out", nargs="?", default=str(Path(__file__).resolve().parent / "levels"))
    ap.add_argument("--check", action="store_true", help="write nothing; fail if the committed files differ")
    a = ap.parse_args(argv)
    if a.check and not Path(a.plan).is_file():
        if Path(a.plan) != DEFAULT_PLAN:
            print(f"levels_svg: {a.plan} does not exist", file=sys.stderr)
            return 2
        print(f"levels_svg: SKIPPED, {a.plan} is not on this machine")
        return 0
    try:
        reader = anyplan()
    except le_common.BuildError as e:
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
