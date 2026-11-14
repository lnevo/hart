#!/usr/bin/env python3
"""Draw the main and upper levels of AnyRail plan 5.3b to scale, as SVG fragments.

    python3 levels_svg.py parts.json graph.json OUT_DIR

parts.json and graph.json come from the prototype reader (README.md here). Writes
main.svg and upper.svg: track only (flex and turnouts), in plan centimetres, y down,
so a level lines up with the staging drawing. Custom objects and buildings in the plan
are never read. The helix ramps (flex whose ends differ in height) are drawn dotted on
the level they climb from; the peninsula (a separate group at 2.5 cm in the plan, built
at 4.25 in) is drawn on the upper level.
"""
import json
import math
import sys
from pathlib import Path

UPPER_Z = 10.0     # flex at or above this height is upper level
FLAT = 0.01        # flex within this of 0 is main level


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


def build(parts, graph):
    cls = {"main": [], "upper": [], "ramp": []}
    to = {"main": [], "upper": []}
    for ci in (0, 2):                       # 0: main level and helix, 2: peninsula
        for i in graph["comps"][ci]:
            p = parts[i]
            zs = [e["z"] for e in p["eps"]]
            if p["bez"]:
                pts = []
                for b in p["bez"]:
                    pts += bezier(b)
                if ci == 2 or min(zs) >= UPPER_Z:
                    k = "upper"
                elif max(zs) <= FLAT and min(zs) >= -FLAT:
                    k = "main"
                else:
                    k = "ramp"
                cls[k].append((i, pts, min(zs), max(zs)))
            else:
                k = "upper" if (ci == 2 or min(zs) >= UPPER_Z) else "main"
                to[k].append((i, p))
    return cls, to


NAMES = {161: "double crossover"}      # plan parts that read better by what they are
MOVED = {300}     # plan parts the overlay (plan_overrides) moves to another level: drawn as plain track here
NOTES = {         # words placed on a level: (x, y, anchor, text)
    "main": [(405, 123, "start", "H1 McKees Rocks (T175)"), (392, 123, "end", "H2 McKeesport (T251)")],
    "upper": [(45, 346, "start", "T300 is built in the run between the"),
              (45, 352, "start", "double crossover and T237, 292 cm"),
              (45, 358, "start", "from the crossover. The plan has no"),
              (45, 364, "start", "geometry for it.")],
}


def flex_cm(pts):
    return sum(math.dist(pts[k], pts[k + 1]) for k in range(len(pts) - 1))


def svg_for(level, cls, to, labels):
    out = []
    for i, pts, z0, z1 in cls[level]:
        out.append('<polyline class="trk" points="%s"/>' % poly(pts))
    if level == "main":
        for i, pts, z0, z1 in cls["ramp"]:
            out.append('<polyline class="ramp" points="%s"/>' % poly(pts))
    for i, p in to[level]:
        e = [a for a in p["eps"] if abs(a["x"]) > 1e-3 and abs(a["y"]) > 1e-3]   # the reader misses one leg of T0
        toe = e[0]
        if i in MOVED:       # keep the straight route only: the leg that points straight on from the toe
            def off(a):
                d = (a["a"] - toe["a"] - math.pi) % (2 * math.pi)
                return min(d, 2 * math.pi - d)
            leg = min(e[1:], key=off)
            out.append('<line class="trk" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (toe["x"], toe["y"], leg["x"], leg["y"]))
            continue
        for a in e[1:]:
            out.append('<line class="to" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (toe["x"], toe["y"], a["x"], a["y"]))
        if len(e) == 3:
            out.append('<line class="to" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (e[1]["x"], e[1]["y"], e[2]["x"], e[2]["y"]))
        cx = sum(a["x"] for a in e) / len(e)
        cy = sum(a["y"] for a in e) / len(e)
        out.append('<text class="tl" x="%.1f" y="%.1f">%s</text>' % (cx + 3, cy - 3, NAMES.get(i, "T%d" % i)))
    for x, y, anchor, text in NOTES.get(level, []):
        out.append('<text class="rl" x="%d" y="%d" text-anchor="%s">%s</text>' % (x, y, anchor, text))
    out.extend(labels)
    return "\n".join(out)


def bbox(cls, to, level):
    xs, ys = [], []
    for i, pts, *_ in cls[level]:
        xs += [p[0] for p in pts]
        ys += [p[1] for p in pts]
    if level == "main":
        for i, pts, *_ in cls["ramp"]:
            xs += [p[0] for p in pts]
            ys += [p[1] for p in pts]
    for i, p in to[level]:
        xs += [a["x"] for a in p["eps"] if abs(a["x"]) > 1e-3]
        ys += [a["y"] for a in p["eps"] if abs(a["y"]) > 1e-3]
    return min(xs), min(ys), max(xs), max(ys)


def main(parts_file, graph_file, out_dir):
    parts = json.load(open(parts_file))
    graph = json.load(open(graph_file))
    cls, to = build(parts, graph)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    meta = {}
    for level in ("main", "upper"):
        x0, y0, x1, y1 = bbox(cls, to, level)
        meta[level] = dict(bbox=[x0, y0, x1, y1], flex=len(cls[level]), turnouts=len(to[level]),
                           flex_m=round(sum(flex_cm(pts) for _, pts, *_ in cls[level]) / 100, 1))
        (out / (level + ".svg")).write_text(svg_for(level, cls, to, []) + "\n")
    meta["ramp_flex"] = len(cls["ramp"])
    meta["ramp_m"] = round(sum(flex_cm(pts) for _, pts, *_ in cls["ramp"]) / 100, 1)
    (out / "levels_meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta))


if __name__ == "__main__":
    main(*sys.argv[1:4])
