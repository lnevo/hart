#!/usr/bin/env python3
"""Draw the staging, main and upper levels of an AnyRail plan to scale, as SVG fragments.

    python3 tools/anyrail/levels_svg.py [PLAN.any] [OUT_DIR] [--check]

Reads the plan with anyplan.py and writes staging.svg, main.svg, upper.svg and levels_meta.json into OUT_DIR
(`tools/anyrail/levels/`, committed, so the track plan page builds without the plan). `--check` writes nothing and
stops when the committed files differ from what the plan gives, and prints SKIPPED, passing, when the plan is not on this machine
(never in CI). PLAN.any is DEFAULT_PLAN unless given. The plan is the owner's, private, and never committed;
only track is read, so custom objects, scenery and buildings (third-party copyright) never reach a drawing.

Coordinates are plan centimetres, y down, so the three drawings line up. What a drawing holds:

- A level is a height. The turnouts of the plan sit at three heights (staging, main, upper); a flat flex piece goes to
  the level it lies at.
- A flex piece whose ends differ in height is a ramp (the helix and the climb to the upper level), drawn dotted. A
  track that starts on staging is drawn there below HELIX_CUT_CM, the cut the schematic parts the levels at, and on
  the level it reaches above it; a climb that starts higher is drawn on the level it climbs from.
- A turnout is labelled with the owner's switch number from the relabel map of staging.plan_overrides.json or
  main_upper.plan_overrides.json (the plan's T number is the part's place in the file); one the maps do not name
  carries its T number.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import anyplan  # noqa: E402

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths, railroad_facts  # noqa: E402

LEVELS = ("staging", "main", "upper")          # lowest to highest
HELIX_CUT_CM = -5.0     # the height that parts staging's graph from the main and upper graph (anyplan.py --cut -5)
SNAP_CM = 0.5           # a flat part this close to a level's height is on that level
CM_PER_IN = 2.54
DEFAULT_PLAN = Path.home() / "Documents/Layout/Lee Nevo Design Version 5.3c.any"
OVERRIDES = {"staging": "staging.plan_overrides.json", "main": "main_upper.plan_overrides.json",
             "upper": "main_upper.plan_overrides.json"}
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
        if len(p["ends"]) > 2 and max(e["z"] for e in p["ends"]) - min(e["z"] for e in p["ends"]) > anyplan.LEVEL_CM:
            raise LevelsError(f"T{p['index']} is a turnout that is not level")
    return dict(zip(LEVELS, heights))


def nearest_level(z, heights, what) -> str:
    level = min(heights, key=lambda k: abs(heights[k] - z))
    if abs(heights[level] - z) > SNAP_CM:
        raise LevelsError(f"{what} lies at {z:.2f} cm, not at a level ({heights})")
    return level


def helix_chains(parts, links):
    """The sloped flex pieces joined end to end: a list of sets of part indices, one per helix track."""
    sloped = {p["index"] for p in parts if len(p["ends"]) == 2
              and abs(p["ends"][0]["z"] - p["ends"][1]["z"]) > anyplan.LEVEL_CM}
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


def assign(parts, heights):
    """{part index: level} for every flat part and every helix piece (the dotted ones are `ramp` below)."""
    links, _ = anyplan.joins(parts)
    where, ramp = {}, set()
    for p in parts:
        zs = [e["z"] for e in p["ends"]]
        if max(zs) - min(zs) <= anyplan.LEVEL_CM:
            where[p["index"]] = nearest_level(zs[0], heights, f"T{p['index']}")
    for chain in helix_chains(parts, links):
        top = nearest_level(max(e["z"] for i in chain for e in parts[i]["ends"]), heights, "the top of a helix track")
        bottom = nearest_level(min(e["z"] for i in chain for e in parts[i]["ends"]), heights, "the foot of a helix track")
        if LEVELS.index(top) <= LEVELS.index(bottom):
            raise LevelsError(f"a helix track runs from {bottom} to {top}; it must climb")
        for i in chain:
            mid = sum(e["z"] for e in parts[i]["ends"]) / 2
            # a track that starts on staging is drawn there up to the cut and on the level it reaches above it; any
            # other climb is drawn on the level it climbs from
            where[i] = bottom if bottom != LEVELS[0] else (bottom if mid < HELIX_CUT_CM else top)
            ramp.add(i)
    if len(where) != len(parts):
        raise LevelsError("parts left without a level: %s" % sorted(set(range(len(parts))) - set(where)))
    return where, ramp, links


def labels(level) -> dict[str, str]:
    """{plan label: owner's switch number} for a level, from its plan overrides file."""
    return railroad_facts.read_plan_overrides(paths.LAYOUT_DATA / "schematic" / OVERRIDES[level]).relabel


def label_of(p, names):
    t = "T%d" % p["index"]
    if p["kind"] == "threeway":
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
        # ends 0 and one more face the same way (one side); the other two the opposite side
        h = [p["ends"][i]["a"] for i in range(4)]
        side = [i for i in range(1, 4) if abs(anyplan._wrap(math.degrees(h[i] - h[0]))) < anyplan.PARALLEL_DEG]
        if len(side) != 1:
            raise LevelsError(f"T{p['index']}: cannot tell the two sides of the double crossover")
        s1 = [0, side[0]]
        s2 = [i for i in range(4) if i not in s1]
        out = []
        for i in s1:        # a rail runs straight across to the end on the other side that lies closest abeam
            ux, uy = math.cos(h[i]), math.sin(h[i])
            j = min(s2, key=lambda m: abs((e[m][0] - e[i][0]) * -uy + (e[m][1] - e[i][1]) * ux))
            out.append(e[i] + e[j])
            other = [m for m in s2 if m != j][0]
            mid = lambda q, r, f: (q[0] + (r[0] - q[0]) * f, q[1] + (r[1] - q[1]) * f)    # noqa: E731
            out.append(mid(e[i], e[other], 0.3) + mid(e[i], e[other], 0.7))
        return out
    raise LevelsError(f"T{p['index']} is a {k}, which this drawing has no symbol for")


def draw(parts, where, ramp, level):
    """(svg text, bbox, counts) of one level."""
    names = labels(level)
    out, xs, ys = [], [], []
    flex_cm, flex_n, ramp_cm, switches = 0.0, 0, 0.0, []

    def take(pts):
        xs.extend(q[0] for q in pts)
        ys.extend(q[1] for q in pts)
    for p in parts:
        if where[p["index"]] != level:
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
                  labels=sorted(switches, key=lambda s: (int(re.match(r"\d+", s).group()) if re.match(r"\d+", s)
                                                         else 10 ** 6, s)))
    return "\n".join(out) + "\n", counts


def helix_tracks(parts, links, heights):
    """Each helix track as {from, to, cm, below_cut_cm}: the owner's numbers of the switch at its foot and at its top,
    its length along the flex, and the part of it below the schematic's cut."""
    out = []
    for c in anyplan.level_cuts(parts, links, HELIX_CUT_CM):
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
    parts = anyplan.read(plan_path)
    heights = level_heights(parts)
    where, ramp, links = assign(parts, heights)
    files, meta = {}, dict(plan=plan_version(plan_path), parts=len(parts), cut_cm=HELIX_CUT_CM, levels={})
    for level in LEVELS:
        svg, counts = draw(parts, where, ramp, level)
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
        print(f"levels_svg: SKIPPED, {a.plan} is not on this machine")
        return 0
    try:
        files = build(a.plan)
    except (LevelsError, anyplan.PlanError, OSError) as e:
        print(f"levels_svg: {e}", file=sys.stderr)
        return 2
    out = Path(a.out)
    if a.check:
        stale = [n for n, t in files.items() if not (out / n).is_file() or (out / n).read_text() != t]
        if stale:
            print(f"levels_svg: {', '.join(stale)} in {out} differ from the plan; rerun without --check", file=sys.stderr)
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
