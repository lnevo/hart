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


def heading(parts, x, y, near=0.5):
    """Unit direction of the flex that ends at (x, y), pointing away from that end, or None."""
    for p in parts:
        for b in p["bez"] or []:
            for end, nxt in ((b[0], b[1]), (b[-1], b[-2])):
                if math.dist(end, (x, y)) < near:
                    d = math.dist(end, nxt) or 1.0
                    return [(nxt[0] - end[0]) / d, (nxt[1] - end[1]) / d]
    return None


def ease(x0, y0, x1, y1, d0=(1.0, 0.0), d1=(1.0, 0.0), n=20):
    """A smooth curve between two points that leaves along d0 and arrives along d1 (the tracks either side),
    so there is no kink where it meets them."""
    k = 0.4 * math.dist((x0, y0), (x1, y1))
    c = [(x0, y0), (x0 + k * d0[0], y0 + k * d0[1]), (x1 - k * d1[0], y1 - k * d1[1]), (x1, y1)]
    return [[(1 - t) ** 3 * c[0][j] + 3 * (1 - t) ** 2 * t * c[1][j] + 3 * (1 - t) * t * t * c[2][j] + t ** 3 * c[3][j]
             for j in range(2)] for t in (m / n for m in range(n + 1))]


def poly(pts):
    return " ".join("%.1f,%.1f" % (x, y) for x, y in pts)


PARTS = []


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
                if ci == 2 or min(zs) >= UPPER_Z or i in UPPER_RAILS:
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
# The two tracks out of the east end of crossover 23: the plan runs one down to T300 (height 0) and the
# other up to T237. The owner built both on the upper level, joined by T300 (plan_overrides: T300 moved).
UPPER_RAILS = {254, 287, 259, 303, 296, 293, 261, 298, 304, 302}
XOVER23 = (413.7, 320.0, 461.4, 325.1)      # west x, north y, east x, south y of the plan's double crossover
# T300 on the upper level: a stock turnout (23.4 cm long, legs 2.5 cm apart) on the north rail, its diverging
# leg eased into the south rail (which starts at B_RAIL) over the gap. The toe sits 20 cm west of the plan's old T300.
T300_NEW = (408.1, 127.4)
T300_LEN, T300_OFFSET = 23.4, 2.5
B_RAIL = (451.5, 134.1)
MOVED = {300}     # plan parts the overlay (plan_overrides) moves to another level: drawn as plain track here
NOTES = {         # words placed on a level: (x, y, anchor, text)
    "main": [(405, 130, "start", "H1 McKees Rocks (T175)"), (392, 130, "end", "H2 McKeesport (T251)")],
    "upper": [(402, 122, "end", "T300: where the two tracks out of crossover 23 meet")],
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
        if i in MOVED:       # keep one route only: toe to the helix leg
            def off(a):
                d = (a["a"] - toe["a"] - math.pi) % (2 * math.pi)
                return min(d, 2 * math.pi - d)
            leg = max(e[1:], key=off)          # T251 runs on into the inner helix track, T300's diverging leg
            d0 = heading(PARTS, toe["x"], toe["y"]) or (1.0, 0.0)
            d1 = heading(PARTS, leg["x"], leg["y"]) or (1.0, 0.0)
            out.append('<polyline class="trk" points="%s"/>' % poly(ease(toe["x"], toe["y"], leg["x"], leg["y"], d0, d1)))
            continue
        for a in e[1:]:
            out.append('<line class="to" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (toe["x"], toe["y"], a["x"], a["y"]))
        if len(e) == 3:
            out.append('<line class="to" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (e[1]["x"], e[1]["y"], e[2]["x"], e[2]["y"]))
        cx = sum(a["x"] for a in e) / len(e)
        cy = sum(a["y"] for a in e) / len(e)
        out.append('<text class="tl" x="%.1f" y="%.1f">%s</text>' % (cx + 3, cy - 3, NAMES.get(i, "T%d" % i)))
    if level == "upper":
        wx, ny, ex, sy = XOVER23
        for y in (ny, sy):
            out.append('<line class="to" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (wx, y, ex, y))
        mx0, mx1 = wx + (ex - wx) * 0.3, wx + (ex - wx) * 0.7
        out.append('<line class="to" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (mx0, ny, mx1, sy))
        out.append('<line class="to" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (mx0, sy, mx1, ny))
        out.append('<text class="tl" x="%.1f" y="%.1f">crossover 23</text>' % (wx + 6, sy + 9))
        tx, ty = T300_NEW
        ex, dy = tx + T300_LEN, ty + T300_OFFSET
        out.append('<line class="to" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (tx, ty, ex, ty))
        out.append('<line class="to" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (tx, ty, ex, dy))
        out.append('<line class="to" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % (ex, ty, ex, dy))
        d0 = [T300_LEN / math.hypot(T300_LEN, T300_OFFSET), T300_OFFSET / math.hypot(T300_LEN, T300_OFFSET)]
        d1 = heading(PARTS, B_RAIL[0], B_RAIL[1]) or (1.0, 0.0)
        out.append('<polyline class="trk" points="%s"/>' % poly(ease(ex, dy, B_RAIL[0], B_RAIL[1], d0, d1)))
        out.append('<text class="tl" x="%.1f" y="%.1f">T300</text>' % (tx, ty - 4))
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
    PARTS[:] = parts
    graph = json.load(open(graph_file))
    cls, to = build(parts, graph)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    meta = {}
    for level in ("main", "upper"):
        x0, y0, x1, y1 = bbox(cls, to, level)
        meta[level] = dict(bbox=[x0, y0, x1, y1], flex=len(cls[level]), turnouts=len(to[level]),
                           drawn=len(to[level]) - sum(1 for i, _ in to[level] if i in MOVED) + (2 if level == "upper" else 0),
                           flex_m=round(sum(flex_cm(pts) for _, pts, *_ in cls[level]) / 100, 1))
        (out / (level + ".svg")).write_text(svg_for(level, cls, to, []) + "\n")
    meta["ramp_flex"] = len(cls["ramp"])
    meta["ramp_m"] = round(sum(flex_cm(pts) for _, pts, *_ in cls["ramp"]) / 100, 1)
    (out / "levels_meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta))


if __name__ == "__main__":
    main(*sys.argv[1:4])
