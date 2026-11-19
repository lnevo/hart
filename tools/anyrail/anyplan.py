#!/usr/bin/env python3
"""Read an AnyRail plan (.any) straight from the file: its track parts, their end points with heights, the flex
track curves, how the parts join, and what kind of part each is.

AnyRail's file is a binary archive with no published format. What this reads was worked out on HART's plans 5.3b
and 5.3c (2026-11-19) and is checked against AnyRail's own JMRI export (tests/test_anyplan.py):

- A part's name record is two length-prefixed strings: the catalog name and its library ("SL-8362" "PSL83",
  "83051" "WAL83F19"). Scenery, vehicles and buildings have name records too.
- An end point record is four doubles (x, y, z in cm, and the end's heading in radians) followed by a
  length-prefixed track system string ("PSL83", "WAL83"). The bytes before the doubles differ for the first record
  of its kind in a file (the archive writes the record's class there), so records are found by what follows the
  doubles, never by a tag in front of them.
- A track part is a name record whose library starts with a system that end points use, so the reader keeps
  every maker's track and no scenery, without a list of makers. Its end points are the end point records between
  its name record and the next part's.
- A flex track's curve is a list of Bezier points: a count, then per point a two-byte class tag, an id and x and
  y. The tag is numbered per file (it was "4" in 5.3b and "6" in 5.3c), so a list counts only when every point
  carries the same tag and the curve starts and ends on the part's end points.

The type of a part comes from its end points, not its catalog name: two ends are track, three a turnout (straight or
curved, left or right), four a three-way, a double crossover or a crossing (a diamond or slip, which the ends alone
cannot tell apart).

Coordinates are AnyRail's: centimetres, y growing down the screen. A part's index (its place in the file) is its
"T" number in the schematic inputs.

    python3 tools/anyrail/anyplan.py PLAN.any --report            # levels, track ends, grades, faults
    python3 tools/anyrail/anyplan.py PLAN.any --parts parts.json  # the parts list the schematic-maps plugin reads
"""
from __future__ import annotations

import argparse
import bisect
import collections
import json
import math
import re
import struct
import sys
from pathlib import Path

JOIN_CM = 0.15          # two ends this close (in plan) are joined, as AnyRail snaps them
JOIN_DZ_CM = 0.5        # ... and this close in height
NEAR_MISS_CM = 5.0      # a free end this close to another end is reported: it probably should join
MAX_XY_CM = 5000.0      # a plan coordinate beyond this is not a coordinate
PARALLEL_DEG = 2.0      # two ends this close in heading run the same way
LEVEL_CM = 0.05         # a part's ends within this much height are level

NAME_RE = re.compile(rb"([\x03-\x30])\x00{7}([\x20-\x7e]{3,48})([\x03-\x10])\x00{7}([A-Za-z0-9_-]{2,16})")
END_RE = re.compile(rb"(.{32})([\x01-\x20])\x00{7}([A-Za-z0-9_-]{1,32})(?![\x20-\x7e])", re.S)
POINT_BYTES = 22        # tag (2), id (4), x (8), y (8)


class PlanError(ValueError):
    pass


def _finite(*v):
    return all(math.isfinite(x) for x in v)


def _names(d: bytes):
    """[(offset, name, library)] of every name record."""
    out = []
    for m in NAME_RE.finditer(d):
        if len(m.group(2)) == m.group(1)[0] and len(m.group(4)) == m.group(3)[0]:
            out.append((m.start(), m.group(2).decode(), m.group(4).decode()))
    return out


def _end_records(d: bytes):
    """[(offset, x, y, z, a, system)] of every record shaped like an end point."""
    out = []
    for m in END_RE.finditer(d):
        if len(m.group(3)) != m.group(2)[0]:
            continue
        x, y, z, a = struct.unpack("<4d", m.group(1))
        # (0, 0) is not a place on a plan, and a subnormal double (8e-320) is not a measure: headers have that shape
        real = not any(0.0 < abs(v) < sys.float_info.min for v in (x, y, z, a))
        if (real and _finite(x, y, z, a) and abs(x) < MAX_XY_CM and abs(y) < MAX_XY_CM and abs(z) < 1000
                and abs(a) < 10 and max(abs(x), abs(y)) > 1e-6):
            out.append((m.start(), x, y, z, a, m.group(3).decode()))
    return out


def _curve(d: bytes, start: int, ends):
    """The Bezier points of the flex curve stored after `start`, or None: a count then that many points with one tag,
    starting and ending on the part's ends."""
    for o in range(start, min(start + 400, len(d) - 10)):
        n = d[o]
        if not (4 <= n <= 64 and (n - 1) % 3 == 0 and d[o + 1:o + 8] == b"\x00" * 7):
            continue
        tag, base = d[o + 8:o + 10], o + 8
        if base + n * POINT_BYTES > len(d) or tag[1] != 0 or not 0x20 <= tag[0] <= 0x7e:
            continue
        pts = []
        for k in range(n):
            p = base + k * POINT_BYTES
            if d[p:p + 2] != tag:
                break
            x, y = struct.unpack("<2d", d[p + 6:p + 22])
            if not _finite(x, y) or abs(x) > MAX_XY_CM or abs(y) > MAX_XY_CM:
                break
            pts.append((x, y))
        if len(pts) != n:
            continue
        tips = (pts[0], pts[-1])
        if all(min(math.dist(t, (e["x"], e["y"])) for t in tips) < 0.5 for e in ends):
            return pts
    return None


def bezier_length(pts, steps=200):
    total = 0.0
    for s in range(0, len(pts) - 3, 3):
        p0, p1, p2, p3 = pts[s:s + 4]
        prev = p0
        for i in range(1, steps + 1):
            t = i / steps
            u = 1 - t
            q = tuple(u ** 3 * p0[j] + 3 * u * u * t * p1[j] + 3 * u * t * t * p2[j] + t ** 3 * p3[j] for j in (0, 1))
            total += math.dist(prev, q)
            prev = q
    return total


def read(path) -> list[dict]:
    """The plan's track parts in file order: {index, name, library, system, ends [{x, y, z, a}], curve, cm, kind,
    ...}; `cm` is a flex track's length along its curve, None for a fixed part."""
    d = Path(path).read_bytes()
    names = _names(d)
    records = _end_records(d)
    libraries = {lib for _, _, lib in names}
    systems = {s for *_, s in records if any(lib.startswith(s) for lib in libraries)}
    if not systems:
        raise PlanError(f"{path}: no track end points found; is it an AnyRail plan?")
    kept = [n for n in names if any(n[2].startswith(s) for s in systems)]
    starts = [o for o, _, _ in kept]
    parts = [dict(index=i, name=n, library=lib, offset=o, ends=[]) for i, (o, n, lib) in enumerate(kept)]
    for o, x, y, z, a, s in records:
        if s not in systems:
            continue
        i = bisect.bisect_right(starts, o) - 1
        if i < 0:
            raise PlanError(f"{path}: a track end point at byte {o} comes before any track part")
        parts[i]["ends"].append(dict(x=x, y=y, z=z, a=a, system=s, offset=o))
    # a library none of whose parts has two ends is placed objects (benchwork, scenery), not track
    track_libs = {p["library"] for p in parts if len(p["ends"]) >= 2}
    parts = [p for p in parts if p["library"] in track_libs]
    for i, p in enumerate(parts):
        p["index"] = i
    bad = [(p["index"], p["name"], len(p["ends"])) for p in parts if not 2 <= len(p["ends"]) <= 4]
    if bad:
        raise PlanError(f"{path}: parts with an unsupported number of ends (index, name, ends): {bad}")
    for p in parts:
        p["system"] = p["ends"][0]["system"]
        p["curve"] = _curve(d, p["ends"][-1]["offset"] + 32, p["ends"]) if len(p["ends"]) == 2 else None
        p["cm"] = bezier_length(p["curve"]) if p["curve"] else None
        p.update(classify(p["ends"]))
    return parts


def _wrap(deg):
    return (deg + 180) % 360 - 180


def _heading(e):
    return math.degrees(e["a"])


def classify(ends) -> dict:
    """{kind, ...} from a part's ends. kind: track; turnout (points, straight, diverging end indices, hand L/R,
    curved); threeway (points); double_crossover; crossing (diamond or slip)."""
    xy = [(e["x"], e["y"]) for e in ends]
    if len(ends) == 2:
        return dict(kind="track")
    if len(ends) == 3:
        far = [sum(math.dist(xy[i], xy[j]) for j in range(3)) for i in range(3)]
        p = max(range(3), key=far.__getitem__)
        legs = [i for i in range(3) if i != p]
        back = _heading(ends[p]) + 180
        s, dv = sorted(legs, key=lambda i: abs(_wrap(_heading(ends[i]) - back)))
        (sx, sy), (dx, dy) = [(xy[i][0] - xy[p][0], xy[i][1] - xy[p][1]) for i in (s, dv)]
        hand = "R" if sx * dy - sy * dx > 0 else "L"       # y grows down: clockwise on screen is to the right
        curved = abs(_wrap(_heading(ends[s]) - back)) > PARALLEL_DEG
        return dict(kind="turnout", points=p, straight=s, diverging=dv, hand=hand, curved=curved)
    groups = collections.defaultdict(list)
    first = _heading(ends[0])
    for i, e in enumerate(ends):
        groups[abs(_wrap(_heading(e) - first)) < 90].append(i)
    sizes = sorted(len(g) for g in groups.values())
    if sizes == [1, 3]:
        p = next(g[0] for g in groups.values() if len(g) == 1)
        return dict(kind="threeway", points=p)
    if sizes == [2, 2]:
        same = all(abs(_wrap(_heading(ends[a]) - _heading(ends[b]))) < PARALLEL_DEG for a, b in groups.values())
        return dict(kind="double_crossover" if same else "crossing")
    raise PlanError(f"a four-ended part whose ends face {sizes} ways is neither a three-way nor a crossover")


def joins(parts):
    """(links [(part, end, part, end)], free [(part, end)]). Ends join when they meet in plan and height."""
    ends = [(p["index"], k, e) for p in parts for k, e in enumerate(p["ends"])]
    cell = lambda e: (math.floor(e["x"] / 1), math.floor(e["y"] / 1))          # noqa: E731
    grid = collections.defaultdict(list)
    for t in ends:
        grid[cell(t[2])].append(t)
    links, degree = [], collections.Counter()
    for i, k, e in ends:
        cx, cy = cell(e)
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                for j, m, f in grid[(gx, gy)]:
                    if (j, m) <= (i, k):
                        continue
                    if math.hypot(e["x"] - f["x"], e["y"] - f["y"]) < JOIN_CM and abs(e["z"] - f["z"]) < JOIN_DZ_CM:
                        links.append((i, k, j, m))
                        degree[(i, k)] += 1
                        degree[(j, m)] += 1
    crowded = [t for t, n in degree.items() if n > 1]
    if crowded:
        raise PlanError(f"more than two track ends meet at one spot: {crowded}")
    free = [(i, k) for i, k, _ in ends if not degree[(i, k)]]
    return links, free


def components(parts, links):
    root = list(range(len(parts)))

    def find(x):
        while root[x] != x:
            root[x] = root[root[x]]
            x = root[x]
        return x
    for a, _, b, _ in links:
        root[find(a)] = find(b)
    groups = collections.defaultdict(list)
    for p in parts:
        groups[find(p["index"])].append(p["index"])
    return sorted(groups.values(), key=len, reverse=True)


def runs(parts, links):
    """Switch-to-switch runs: [(part, end, part or None, end or None, cm)] from every end of every part with three or
    more ends, through two-ended parts, to the next such part or a free end; each run once from each side. cm counts
    flex curves only (fixed parts add nothing), as AnyRail's export measures between turnout ends."""
    nbr = {}
    for a, ka, b, kb in links:
        nbr[(a, ka)], nbr[(b, kb)] = (b, kb), (a, ka)
    out = []
    for p in parts:
        if len(p["ends"]) < 3:
            continue
        for k in range(len(p["ends"])):
            here, cm, seen = (p["index"], k), 0.0, 0
            while here in nbr:
                j, m = nbr[here]
                q = parts[j]
                if len(q["ends"]) != 2:
                    out.append((p["index"], k, j, m, cm))
                    break
                cm += q["cm"] or 0.0
                here, seen = (j, 1 - m), seen + 1
                if seen > len(parts):
                    raise PlanError(f"a run from part {p['index']} loops without reaching a switch")
            else:
                out.append((p["index"], k, None, None, cm))
    return out


def parts_list(parts) -> list[dict]:
    """The parts list the schematic-maps plugin reads (`plan --parts`): name and end points' x, y, z, in file order."""
    return [{"name": p["name"], "eps": [{k: e[k] for k in "xyz"} for e in p["ends"]]} for p in parts]


def report(parts) -> list[str]:
    links, free = joins(parts)
    comp = components(parts, links)
    lines = [f"{len(parts)} track parts, {sum(len(p['ends']) for p in parts)} ends, {len(links)} joins, "
             f"{len(free)} free ends, {len(comp)} connected piece(s): {[len(c) for c in comp[:6]]}"]
    kinds = collections.Counter((p["kind"], p.get("hand"), p.get("curved")) for p in parts if p["kind"] != "track")
    lines.append("switches: " + ", ".join(f"{k[0]}{' ' + k[1] if k[1] else ''}{' curved' if k[2] else ''} x{n}"
                                          for k, n in sorted(kinds.items(), key=str)))
    z = collections.Counter(round(e["z"], 2) for p in parts for e in p["ends"])
    lines.append("ends by height (cm): " + ", ".join(f"{h} x{n}" for h, n in z.most_common(8)))
    sw = collections.Counter(round(p["ends"][0]["z"], 2) for p in parts if len(p["ends"]) > 2)
    lines.append("switches by height (cm): " + ", ".join(f"{h} x{n}" for h, n in sorted(sw.items())))
    tilted = [p["index"] for p in parts if len(p["ends"]) > 2
              and max(e["z"] for e in p["ends"]) - min(e["z"] for e in p["ends"]) > LEVEL_CM]
    lines.append(f"switches not level: {tilted or 'none'}")
    grades = sorted(((100 * abs(p["ends"][0]["z"] - p["ends"][1]["z"]) / p["cm"], p["index"]) for p in parts
                     if p["cm"] and abs(p["ends"][0]["z"] - p["ends"][1]["z"]) > LEVEL_CM), reverse=True)
    lines.append(f"sloped flex pieces: {len(grades)}, steepest " +
                 ", ".join(f"T{i} {g:.2f}%" for g, i in grades[:5]) if grades else "sloped flex pieces: none")
    flat_in_free = set(free)
    near = []
    for i, k in free:
        e = parts[i]["ends"][k]
        for q in parts:
            if q["index"] == i:
                continue
            for m, f in enumerate(q["ends"]):
                dist = math.hypot(e["x"] - f["x"], e["y"] - f["y"])
                if dist < NEAR_MISS_CM and ((q["index"], m) in flat_in_free or abs(e["z"] - f["z"]) < JOIN_DZ_CM):
                    near.append((i, q["index"], round(dist, 2), round(f["z"] - e["z"], 2)))
    lines.append(f"free ends within {NEAR_MISS_CM} cm of another end at the same height or free: {near or 'none'}")
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("plan", help="the AnyRail .any file")
    ap.add_argument("--parts", help="write the plugin's parts list (JSON) here")
    ap.add_argument("--report", action="store_true", help="print levels, track ends, grades and likely faults")
    a = ap.parse_args(argv)
    parts = read(a.plan)
    if a.parts:
        Path(a.parts).write_text(json.dumps(parts_list(parts), separators=(",", ":")))
        print(f"wrote {a.parts}: {len(parts)} parts")
    if a.report or not a.parts:
        print("\n".join(report(parts)))


if __name__ == "__main__":
    sys.exit(main())
