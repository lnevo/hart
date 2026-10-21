#!/usr/bin/env python3
"""Main-level plywood cut plan: 3/4 in (0" level) and 1/2 in (+4.25 level).

Builds every piece as a shape in room coordinates (inches, from the AnyRail plan:
x east from the room's west corner, y south from the north wall line), nests the
pieces on 48 x 96 sheets, checks fit and overlap, and writes SVG fragments plus a
JSON summary for the review page. Needs shapely.
"""
import json
import math
import sys
from pathlib import Path

from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "plywood_out")
OUT.mkdir(parents=True, exist_ok=True)
SW, SH = 96.0, 48.0
KERF = 0.125


def catmull(pts, n=12):
    """Smooth curve through pts (open), for edges AnyRail stores as arcs."""
    out = []
    p = [pts[0]] + pts + [pts[-1]]
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in range(2)))
    out.append(pts[-1])
    return out


def disc(cx, cy, r):
    return Point(cx, cy).buffer(r, 256)


# ---------------------------------------------------------------- room geometry (AnyRail, inches)
BULB = disc(92.4, 132.75, 36.0)                      # helix peninsula bulb = D01 at +4.25
NORTH_EDGE = catmull([(127.9, 71.0), (137.5, 71.1), (144.0, 68.9), (158.5, 65.0)])
WALL_GAP = 0.125   # deck stops 1/8 off the wall, like the joists; two rips + kerf fit a 48 in sheet
NORTH = Polygon([(4.5 + WALL_GAP, 47.5 + WALL_GAP), (158.5, 47.5 + WALL_GAP)] + NORTH_EDGE[::-1] + [(4.5 + WALL_GAP, 71.0)])
WEST = box(4.5 + WALL_GAP, 71.0, 28.5, 266.5)
CLOSET = box(4.5, 266.5, 18.5, 302.5)
ALCOVE_N = box(163.0, 47.5, 187.0, 65.0)
ALCOVE_S = box(163.0, 114.0, 187.0, 131.5)
# Aisle end: half-ellipse on the alcove line, 17 in deep, b = 26.45 so it passes AnyRail's
# (193.4, 65), (201, 74.5), (204.2, 85.5) and the 13 in tip within about 1/8 in.
AISLE_C, AISLE_A, AISLE_B = (187.0, 89.5), 17.0, 26.45
AISLE_ELL = affinity.scale(Point(0, 0).buffer(1.0, 256), AISLE_A, AISLE_B, origin=(0, 0))
AISLE_ELL = affinity.translate(AISLE_ELL, *AISLE_C)
AISLE_BUMP = unary_union([AISLE_ELL.intersection(box(187.0, 65.0, 210.0, 114.0)), box(150.0, 65.0, 187.0, 114.0)])
TURNBACK = box(187.0, 47.5, 217.0, 131.5).difference(AISLE_BUMP)
NECK_OUTLINE = Polygon([(92.4, 96.7), (111.0, 101.6), (128.0, 110.7), (134.1, 114.0), (158.4, 114.0),
                        (158.4, 136.0), (143.0, 136.0), (138.6, 140.1), (108.2, 168.6), (92.4, 168.7)])
NECK = NECK_OUTLINE.difference(BULB)


def fillet(cx, cy, sx, sy, r):
    """Inside-corner fillet: square of side r at corner (cx,cy) growing toward (sx,sy), minus the arc."""
    sq = box(min(cx, cx + sx * r), min(cy, cy + sy * r), max(cx, cx + sx * r), max(cy, cy + sy * r))
    return sq.difference(disc(cx + sx * r, cy + sy * r, r))


F_NW = fillet(28.5, 71.0, 1, 1, 10.0)
F_CL = fillet(18.5, 266.5, 1, 1, 6.0)
F_SW = fillet(28.5, 200.5, 1, -1, 18.0)

# SW peninsula top: 84 x 66 with a 33 in round east end
SW_TOP = unary_union([box(28.3, 200.5, 79.3, 266.5), disc(79.3, 233.5, 33.0)])

# +4.25 ledge for the two outer main tracks (centres from AnyRail D.01 layer)
NW_C, TB_N, TB_S, SW_C = (39.0, 81.2), (183.6, 81.2), (183.6, 96.9), (52.7, 160.3)
R_IN = 26.5        # inner edge of ledge: inner track R28.5 less 2 in
L_W = 8.0          # straight ledge width
L1 = box(4.5 + WALL_GAP, 81.2, 4.5 + L_W, 160.3)
L2 = box(4.5 + WALL_GAP, 47.5 + WALL_GAP, NW_C[0], NW_C[1]).difference(disc(*NW_C, R_IN))
L3 = box(NW_C[0], 47.5 + WALL_GAP, 187.0, 47.5 + L_W)
STADIUM = unary_union([disc(*TB_N, R_IN), disc(*TB_S, R_IN), box(TB_N[0] - R_IN, TB_N[1], TB_N[0] + R_IN, TB_S[1])])
L4 = box(187.0, 47.5 + WALL_GAP, 217.0 - WALL_GAP, 131.5 - WALL_GAP).difference(STADIUM)
L5A = box(158.5, TB_S[1] + R_IN, 187.0, 131.5 - WALL_GAP)
L5B = box(118.0, 119.0, 158.5, 138.0).difference(BULB)
SW_R_IN, SW_R_OUT = 40.2, SW_C[0] - 4.5
L6 = disc(*SW_C, SW_R_OUT - WALL_GAP).difference(disc(*SW_C, SW_R_IN)).intersection(box(4.5, SW_C[1], SW_C[0], 200.5))


def split(geom, axis, at):
    lo = box(-1e3, -1e3, at, 1e3) if axis == "x" else box(-1e3, -1e3, 1e3, at)
    hi = box(at, -1e3, 1e3, 1e3) if axis == "x" else box(-1e3, at, 1e3, 1e3)
    return geom.intersection(lo), geom.intersection(hi)


def biggest(g):
    if g.geom_type == "MultiPolygon":
        return max(g.geoms, key=lambda q: q.area)
    return g


# ---------------------------------------------------------------- pieces
P = {}


def piece(pid, geom, level, name, note=""):
    P[pid] = dict(id=pid, geom=biggest(geom), level=level, name=name, note=note)


# 3/4
n_a, n_b = split(NORTH, "x", 4.5 + WALL_GAP + 96)
piece("N1", n_a, "34", "North wall", "Square cuts. Tracks run along it.")
piece("N2", n_b, "34", "North wall, east end", "Front edge eases from 23-1/2 to 17-1/2 deep: see offsets.")
w_c, rest = split(WEST, "y", 109.0)
w_a, w_b = split(rest, "y", 205.0 + 0.0)
piece("W1", w_c, "34", "West wall, north end", "Butts N1 at the corner.")
piece("W2", w_a, "34", "West wall, middle")
piece("W3", w_b, "34", "West wall, south end", "Ends at the SW peninsula / closet line.")
CORE = box(124.1, 113.0, 158.4, 136.0)
neck_core = NECK.intersection(CORE)
piece("K1", neck_core, "34", "Neck core", "Inner end follows the 36 in bulb radius.")
neck_rest = NECK.difference(CORE)
parts = sorted([g for g in getattr(neck_rest, "geoms", [neck_rest]) if g.area > 4], key=lambda g: -g.area)
piece("K2", parts[0], "34", "Neck, lower wedge", "Between the bulb and the angled south edge.")
if len(parts) > 1:
    piece("K3", parts[1], "34", "Neck, upper sliver", "Between the bulb and the north edge.")
piece("T1", TURNBACK, "34", "East turnback", "Inside edge follows the aisle end: see offsets.")
piece("A1", ALCOVE_N, "34", "Alcove, north")
piece("A2", ALCOVE_S, "34", "Alcove, south")
piece("C1", CLOSET, "34", "Closet strip")
piece("F1", F_NW, "34", "Fillet, NW inside corner", "10 in radius.")
piece("F2", F_CL, "34", "Fillet, closet corner", "6 in radius.")
piece("F3", F_SW, "34", "Fillet, SW peninsula corner", "18 in radius.")
band = TURNBACK.intersection(AISLE_BUMP.buffer(3.0)).difference(AISLE_BUMP)
r_up, r_lo = split(band, "y", 89.5)
piece("R1", r_up, "34", "Turnback rim, north half", "3 in band screwed under T1 along the curve.")
piece("R2", r_lo, "34", "Turnback rim, south half")

# 1/2
d_n, d_s = split(BULB, "y", 132.75)
piece("D1", d_n, "12", "Helix top (D01), north half", "72 in circle, 36 in radius on the bulb centre.")
piece("D2", d_s, "12", "Helix top (D01), south half")
s_a, s_b = split(SW_TOP, "y", 248.5)
piece("S1", s_a, "12", "SW peninsula top, north", "Round end 33 in radius.")
piece("S2", s_b, "12", "SW peninsula top, south")
piece("L1", L1, "12", "Ledge, west wall", "8 in wide.")
piece("L2", L2, "12", "Ledge, NW corner", "Inside edge 26-1/2 in radius.")
l3a, l3b = split(L3, "x", 135.0)
piece("L3", l3a, "12", "Ledge, north wall", "8 in wide.")
piece("L4", l3b, "12", "Ledge, north wall east + alcove", "Passes the wall stub at x 158-1/2 to 163.")
l4n, l4s = split(L4, "y", (TB_N[1] + TB_S[1]) / 2)
piece("L5", l4n, "12", "Ledge, turnback north", "Inside edge 26-1/2 in radius.")
piece("L6", l4s, "12", "Ledge, turnback south", "Inside edge 26-1/2 in radius.")
piece("L7", L5A, "12", "Ledge, south alcove", "Passes the wall stub.")
piece("L8", L5B, "12", "Ledge, neck to helix top", "TO CONFIRM: assumes the main crosses the neck at +4.25.")
l9a, l9b = split(L6, "y", 181.0)
piece("L9", l9a, "12", "Ledge, west wall curve (north)", "Band 40.2 to 48.1 in radius.")
piece("L10", l9b, "12", "Ledge, west wall curve (south)", "Same band; meets the SW peninsula top.")


# ---------------------------------------------------------------- nesting
SHEETS = []


def sheet(sid, level, title, places, reserve=None):
    placed = []
    for pid, x, y, rot in places:
        g = P[pid]["geom"]
        if isinstance(rot, str):  # 'h' / 'v': long side of the minimum rectangle horizontal / vertical
            cs = list(g.minimum_rotated_rectangle.exterior.coords)
            e = max([(cs[0], cs[1]), (cs[1], cs[2])], key=lambda q: math.dist(*q))
            ang = math.degrees(math.atan2(e[1][1] - e[0][1], e[1][0] - e[0][0]))
            rot = -ang + (90 if rot == "v" else 0)
        g = affinity.rotate(g, rot, origin="centroid")
        minx, miny, _, _ = g.bounds
        g = affinity.translate(g, x - minx, y - miny)
        placed.append((pid, g, rot))
    s = box(0, 0, SW, SH)
    for pid, g, _ in placed:
        if not s.buffer(1e-6).contains(g):
            raise SystemExit(f"{sid}: {pid} off the sheet {g.bounds}")
    for i in range(len(placed)):
        for j in range(i + 1, len(placed)):
            if placed[i][1].intersection(placed[j][1]).area > 1e-3:
                raise SystemExit(f"{sid}: {placed[i][0]} overlaps {placed[j][0]}")
    label = None
    if reserve is not None:
        label = (max(reserve.geoms, key=lambda q: q.area) if hasattr(reserve, "geoms") else reserve).centroid
    SHEETS.append(dict(id=sid, level=level, title=title, placed=placed, reserve=reserve, reserve_label=label))


def w(pid):
    a, b, c, d = P[pid]["geom"].bounds
    return c - a, d - b


K = KERF
# 3/4 in
sheet("A", "34", "North wall + west wall north end",
      [("N1", 0, 0, 0), ("N2", 0, 24 + K, 0), ("W1", 96 - 38.0, 24 + K, 90)])
sheet("B", "34", "West wall + neck core",
      [("W2", 0, 0, 90), ("W3", 0, 24 + K, 90), ("K1", 96 - 34.3, 24 + K, 0)])
sheet("C", "34", "East turnback, alcoves, closet strip, fillets",
      [("T1", 0, 0, 90), ("A1", 0, 30 + K, 0), ("A2", 24 + K, 30 + K, 0), ("C1", 48 + 2 * K, 30 + K, 90),
       ("F1", 84 + 3 * K, 0, 0), ("F2", 84 + 3 * K, 10 + K, 0), ("K3", 84 + 3 * K, 17, "v")])
sheet("D", "34", "Neck wedge, SW fillet, turnback rim + balloon loop roadbed",
      [("K2", 0, 0, "h"), ("R1", 0, 10.5, "h"), ("R2", 0, 20.0, "h"), ("F3", 36.0, 10.5, 0)],
      reserve=MultiPolygon([box(0, 31, 96, 48), box(58.5, 0, 96, 31)]))

# 1/2 in
sheet("E", "12", "SW peninsula top, north + south alcove ledge",
      [("S1", 0, 0, 0), ("L7", 84 + K, 0, 90)])
sheet("F", "12", "Helix top north half + north wall ledge",
      [("D1", 0, 0, 0), ("L3", 0, 36 + K, 0), ("L8", 72 + K, 0, 90)])
sheet("G", "12", "Helix top south half + west wall ledge",
      [("D2", 0, 0, 0), ("L1", 0, 36 + K, 90)],
      reserve=box(72.5, 0, 96, 36))
sheet("H", "12", "SW peninsula top, south + turnback ledge",
      [("S2", 0, 0, 0), ("L5", 0, 18 + K, 90), ("L6", 42.0, 18 + K, 90)])
sheet("J", "12", "NW / SW ledge curves + north ledge east + room for the ramp",
      [("L2", 0, 0, 0), ("L9", 35.0, 0, "h"), ("L10", 35.0, 15.0, "h"), ("L4", 0, 40.0 - K, 0)],
      reserve=box(60, 30, 96, 48))


# ---------------------------------------------------------------- SVG
def path_d(g, sx=1.0, sy=1.0, ox=0.0, oy=0.0):
    polys = g.geoms if hasattr(g, "geoms") else [g]
    d = []
    for poly in polys:
        for ring in [poly.exterior] + list(poly.interiors):
            cs = list(ring.coords)
            d.append("M" + " L".join(f"{ox + x * sx:.2f},{oy + y * sy:.2f}" for x, y in cs) + "Z")
    return " ".join(d)


def frac(v):
    """inches to nearest 1/8 as text"""
    e = round(v * 8) / 8
    whole = int(e)
    f = e - whole
    if abs(f) < 1e-9:
        return f"{whole}"
    n, dd = int(round(f * 8)), 8
    while n % 2 == 0:
        n //= 2
        dd //= 2
    return f"{whole}-{n}/{dd}" if whole else f"{n}/{dd}"


def sheet_svg(s):
    pad, scale = 2.0, 8.0
    W, H = (SW + 2 * pad) * scale, (SH + 2 * pad + 3) * scale
    o = [f'<svg viewBox="0 0 {W:.0f} {H:.0f}" role="img" aria-label="Sheet {s["id"]} cutting layout" '
         f'xmlns="http://www.w3.org/2000/svg">']
    ox = oy = pad * scale
    o.append(f'<rect class="sheet" x="{ox}" y="{oy}" width="{SW * scale}" height="{SH * scale}"/>')
    for gx in range(12, 96, 12):
        o.append(f'<line class="grid" x1="{ox + gx * scale}" y1="{oy}" x2="{ox + gx * scale}" y2="{oy + SH * scale}"/>')
    for gy in range(12, 48, 12):
        o.append(f'<line class="grid" x1="{ox}" y1="{oy + gy * scale}" x2="{ox + SW * scale}" y2="{oy + gy * scale}"/>')
    if s["reserve"] is not None:
        o.append(f'<path class="reserve" d="{path_d(s["reserve"], scale, scale, ox, oy)}"/>')
        c = s["reserve_label"]
        o.append(f'<text class="rlbl" x="{ox + c.x * scale:.1f}" y="{oy + c.y * scale:.1f}" text-anchor="middle">'
                 f'{"balloon loop roadbed arcs" if s["level"] == "34" else "spare: 0 to 4.25 ramp, mistakes"}</text>')
    for pid, g, _ in s["placed"]:
        o.append(f'<path class="pc l{s["level"]}" d="{path_d(g, scale, scale, ox, oy)}"/>')
        c = g.representative_point()
        a, b, cc, dd = g.bounds
        dims = f'{frac(cc - a)} x {frac(dd - b)}'
        small = (cc - a) < 14 or (dd - b) < 9
        o.append(f'<text class="plbl{" sm" if small else ""}" x="{ox + c.x * scale:.1f}" y="{oy + c.y * scale:.1f}" '
                 f'text-anchor="middle">{pid}</text>')
        if not small:
            o.append(f'<text class="pdim" x="{ox + c.x * scale:.1f}" y="{oy + c.y * scale + 15:.1f}" '
                     f'text-anchor="middle">{dims}</text>')
    o.append(f'<text class="axis" x="{ox}" y="{H - 6}">96 in</text>')
    o.append(f'<text class="axis" x="{ox + SW * scale}" y="{H - 6}" text-anchor="end">48 x 96 sheet, grid 12 in</text>')
    o.append("</svg>")
    return "\n".join(o)


def room_svg(level):
    scale, pad = 3.0, 6.0
    x0, y0, x1, y1 = 0.0, 43.0, 222.0, 307.0
    W, H = (x1 - x0 + 2 * pad) * scale, (y1 - y0 + 2 * pad) * scale
    t = lambda g: path_d(g, scale, scale, (pad - x0) * scale, (pad - y0) * scale)
    o = [f'<svg viewBox="0 0 {W:.0f} {H:.0f}" role="img" aria-label="Room plan, {level} pieces" '
         f'xmlns="http://www.w3.org/2000/svg">']
    walls = unary_union([box(0, 43, 221.5, 47.5), box(0, 43, 4.5, 307), box(4.5, 302.5, 177, 307),
                         box(217, 47.5, 221.5, 131.5), box(158.5, 131.5, 221.8, 136), box(158.5, 114, 163, 131.5),
                         box(158.5, 47.5, 163, 65)])
    bench = unary_union([NORTH, WEST, CLOSET, ALCOVE_N, ALCOVE_S, TURNBACK, NECK, BULB, SW_TOP])
    o.append(f'<path class="bench" d="{t(bench)}"/>')
    o.append(f'<path class="wall" d="{t(walls)}"/>')
    for p in P.values():
        if p["level"] != level or p["id"].startswith("R"):
            continue
        o.append(f'<path class="pc l{level}" d="{t(p["geom"])}"/>')
        c = p["geom"].representative_point()
        o.append(f'<text class="mlbl" x="{(c.x - x0 + pad) * scale:.1f}" y="{(c.y - y0 + pad) * scale + 4:.1f}" '
                 f'text-anchor="middle">{p["id"]}</text>')
    if level == "12":
        for (cx, cy) in (NW_C, TB_N, TB_S, SW_C):
            o.append(f'<circle class="ctr" cx="{(cx - x0 + pad) * scale:.1f}" cy="{(cy - y0 + pad) * scale:.1f}" r="2.5"/>')
    o.append(f'<text class="axis" x="{(140 - x0 + pad) * scale}" y="{(290 - y0 + pad) * scale}">N up · 1 grid = 12 in</text>')
    o.append("</svg>")
    return "\n".join(o)


def offsets():
    """Shop offsets for the two free-form curves."""
    rows = {"N2": [], "T1": []}
    for x in (124, 128, 132, 136, 140, 144, 148, 152, 156, 158.4):
        hit = LineString([(x, 40), (x, 80)]).intersection(NORTH)
        rows["N2"].append((x - 4.5, hit.bounds[3] - 47.5))
    for y in (65.1, 70, 75, 80, 85, 89.5, 95, 100, 105, 110, 113.9):
        hit = LineString([(186, y), (220, y)]).intersection(TURNBACK)
        rows["T1"].append((y - 47.5, 217 - hit.bounds[0]))
    return rows


summary = dict(
    pieces=[dict(id=p["id"], level=p["level"], name=p["name"], note=p["note"],
                 w=frac(p["geom"].bounds[2] - p["geom"].bounds[0]), h=frac(p["geom"].bounds[3] - p["geom"].bounds[1]),
                 area=round(p["geom"].area / 144, 1)) for p in P.values()],
    sheets=[dict(id=s["id"], level=s["level"], title=s["title"], pieces=[q[0] for q in s["placed"]],
                 used=round(sum(q[1].area for q in s["placed"]) / (SW * SH) * 100)) for s in SHEETS],
    area34=round(sum(p["geom"].area for p in P.values() if p["level"] == "34") / 144, 1),
    area12=round(sum(p["geom"].area for p in P.values() if p["level"] == "12") / 144, 1),
    offsets=offsets(),
)
# Presentation-attribute fallbacks (page CSS overrides them for light/dark themes).
FALLBACK = {
    "sheet": 'fill="#fbfaf6" stroke="#1f2326"', "grid": 'stroke="#e7e3d8"', "reserve": 'fill="#ece8dc" stroke="#5f666b"',
    "rlbl": 'fill="#5f666b" font-size="13"', "pc l34": 'fill="#e3c48f" stroke="#9a7434"',
    "pc l12": 'fill="#a9c6c0" stroke="#3f7268"', "plbl": 'fill="#1f2326" font-size="17" font-weight="700"',
    "plbl sm": 'fill="#1f2326" font-size="12" font-weight="700"', "pdim": 'fill="#1f2326" font-size="13"',
    "axis": 'fill="#5f666b" font-size="12"', "bench": 'fill="#efece3" stroke="#d9d6cc"', "wall": 'fill="#b9b4a8"',
    "mlbl": 'fill="#1f2326" font-size="11" font-weight="600"', "ctr": 'fill="#b4532a"',
}


def with_fallbacks(t):
    for k, v in FALLBACK.items():
        t = t.replace(f'class="{k}"', f'class="{k}" {v}')
    return t


(OUT / "summary.json").write_text(json.dumps(summary, indent=1))
for s in SHEETS:
    (OUT / f"sheet_{s['id']}.svg").write_text(with_fallbacks(sheet_svg(s)))
(OUT / "room_34.svg").write_text(with_fallbacks(room_svg("34")))
(OUT / "room_12.svg").write_text(with_fallbacks(room_svg("12")))
for s in summary["sheets"]:
    print(s)
print("3/4 sq ft", summary["area34"], " 1/2 sq ft", summary["area12"])
for p in summary["pieces"]:
    print(p["id"], p["w"], "x", p["h"], p["area"])
