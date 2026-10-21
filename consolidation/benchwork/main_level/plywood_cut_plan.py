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


# ---------------------------------------------------------------- AnyRail outlines
def conic(p0, c, p2, n=24):
    """Rational quadratic from p0 to p2 with control c; weight cos(half the turn) = exact arc when tangents match."""
    a1 = math.atan2(c[1] - p0[1], c[0] - p0[0])
    a2 = math.atan2(p2[1] - c[1], p2[0] - c[0])
    turn = abs((a2 - a1 + math.pi) % (2 * math.pi) - math.pi)
    w = math.cos(turn / 2)
    out = []
    for k in range(1, n + 1):
        t = k / n
        b0, b1, b2 = (1 - t) ** 2, 2 * t * (1 - t) * w, t * t
        d = b0 + b1 + b2
        out.append(((b0 * p0[0] + b1 * c[0] + b2 * p2[0]) / d, (b0 * p0[1] + b1 * c[1] + b2 * p2[1]) / d))
    return out


def outline(pts):
    """AnyRail shape: (x, y, flag) with flag 1 = control point; consecutive controls imply an on-curve midpoint."""
    n = len(pts)
    start = next(i for i, p in enumerate(pts) if p[2] == 0)
    seq = pts[start:] + pts[:start] + [pts[start]]
    out = [seq[0][:2]]
    cur = seq[0][:2]
    ctrl = None
    for x, y, f in seq[1:]:
        if f == 1:
            if ctrl is not None:
                mid = ((ctrl[0] + x) / 2, (ctrl[1] + y) / 2)
                out += conic(cur, ctrl, mid)
                cur = mid
            ctrl = (x, y)
        else:
            if ctrl is not None:
                out += conic(cur, ctrl, (x, y))
                ctrl = None
            else:
                out.append((x, y))
            cur = (x, y)
    return Polygon(out).buffer(0)


PENINSULA = [(55.42, 96.73, 1), (92.56, 96.73, 0), (99.69, 96.73, 1), (110.97, 101.61, 0), (128.02, 110.75, 0),
             (134.11, 114.02, 1), (140.0, 114.02, 0), (158.44, 114.0, 0), (158.44, 136.0, 0), (147.64, 135.98, 0),
             (143.0, 135.98, 1), (138.59, 140.11, 0), (108.17, 168.61, 1), (92.36, 168.73, 0), (55.42, 168.8, 1),
             (56.05, 132.44, 0)]
NORTH_MOD = [(4.48, 47.48, 0), (158.48, 47.48, 0), (158.48, 64.98, 0), (144.0, 68.92, 0), (137.5, 71.06, 1),
             (127.89, 71.0, 0), (4.5, 71.0, 0)]
SW_MOD = [(28.28, 200.48, 0), (77.84, 200.48, 0), (112.3, 200.48, 1), (112.3, 233.75, 0), (112.3, 266.48, 1),
          (77.91, 266.48, 0), (28.28, 266.48, 0)]
TURNBACK_MOD = [(187.0, 47.48, 0), (217.0, 47.48, 0), (217.0, 131.48, 0), (187.0, 131.48, 0), (187.0, 114.0, 0),
                (195.66, 114.03, 1), (204.0, 98.11, 1), (204.02, 92.0, 0), (204.02, 90.86, 0), (204.16, 85.48, 1),
                (201.02, 74.5, 1), (193.36, 65.0, 1), (186.98, 64.98, 0)]


# ---------------------------------------------------------------- room geometry (AnyRail, inches)
BULB = disc(92.4, 132.75, 36.0)                      # helix bulb (centre and radius for the board and ledge)
PEN = outline(PENINSULA)                             # helix peninsula, the same footprint on all three levels
WALL_GAP = 0.125   # deck stops 1/8 off the wall, like the joists; two rips + kerf fit a 48 in sheet
NORTH = outline(NORTH_MOD).intersection(box(4.5 + WALL_GAP, 47.5 + WALL_GAP, 200, 200))
WEST = box(4.5 + WALL_GAP, 71.0, 28.5, 266.5)
CLOSET = box(4.5, 266.5, 18.5, 302.5)
ALCOVE_N = box(163.0, 47.5, 187.0, 65.0)
ALCOVE_S = box(163.0, 114.0, 187.0, 131.5)
TURNBACK = outline(TURNBACK_MOD)
CLOSET_DECK = unary_union([TURNBACK, ALCOVE_N, ALCOVE_S]).intersection(
    box(163.0, 47.5 + WALL_GAP, 217.0 - WALL_GAP, 131.5 - WALL_GAP))


def fillet(cx, cy, sx, sy, r):
    """Inside-corner fillet: square of side r at corner (cx,cy) growing toward (sx,sy), minus the arc."""
    sq = box(min(cx, cx + sx * r), min(cy, cy + sy * r), max(cx, cx + sx * r), max(cy, cy + sy * r))
    return sq.difference(disc(cx + sx * r, cy + sy * r, r))


F_NW = fillet(28.5, 71.0, 1, 1, 10.0)
F_CL = fillet(18.5, 266.5, 1, 1, 6.0)
F_SW = fillet(28.5, 200.5, 1, -1, 18.0)

# SW peninsula top: 84 x 66 with a 33 in round east end
SW_TOP = outline(SW_MOD)

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
SW_R_IN, SW_R_OUT = 40.2, SW_C[0] - 4.5
# SW corner: everything outside the inner band radius, from the end of L1 down to the peninsula edge (y 200.5).
L_SW = box(4.5 + WALL_GAP, SW_C[1], SW_C[0], 200.5).difference(disc(*SW_C, SW_R_IN))


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


# 0 in level: 6 in board for the double track from the helix, through both wall openings, into N2.
# Centre line = midway between the two "Helix Top Turn 1" tracks in AnyRail (2-1/2 in apart).
HELIX_C, HELIX_R = (92.4, 132.75), 32.0               # helix roadbed outer edge (as built 31-3/4 to 32)
S_CURVE_C, S_CURVE_R = (177.7, 91.7), 29.75           # turnback south curve (tracks R28.5 / R31)
N_CURVE_C, N_CURVE_R = (183.25, 80.35), 24.2          # turnback north curve (tracks R23.2 / R25.2)
Y_SOUTH, Y_NORTH = 121.45, 56.15


def arc(c, r, a0, a1, n=48):
    return [(c[0] + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)),
             c[1] + r * math.sin(math.radians(a0 + (a1 - a0) * k / n))) for k in range(n + 1)]


exit_s = catmull([(107.3, 107.0), (125.45, 117.5), (140.3, Y_SOUTH), (S_CURVE_C[0], Y_SOUTH)], 16)
centre = (exit_s[:-1] + arc(S_CURVE_C, S_CURVE_R, 90, 0)
          + [(S_CURVE_C[0] + S_CURVE_R, N_CURVE_C[1])][:0]
          + arc(N_CURVE_C, N_CURVE_R, 0, -90) + [(140.0, Y_NORTH)])
_cl = LineString(centre)
_s0 = next(d / 4 for d in range(0, int(_cl.length * 4)) if _cl.interpolate(d / 4).distance(Point(HELIX_C)) >= HELIX_R + 1.5)
_p0, _p1 = _cl.interpolate(_s0), _cl.interpolate(_s0 + 0.5)
_tx, _ty = (_p1.x - _p0.x) / 0.5, (_p1.y - _p0.y) / 0.5
AHEAD = Polygon([(_p0.x - _ty * 300, _p0.y + _tx * 300), (_p0.x + _ty * 300, _p0.y - _tx * 300),
                 (_p0.x + _ty * 300 + _tx * 400, _p0.y - _tx * 300 + _ty * 400),
                 (_p0.x - _ty * 300 + _tx * 400, _p0.y + _tx * 300 + _ty * 400)])
BOARD = _cl.buffer(3.0, cap_style=2, join_style=1).intersection(AHEAD)   # square start 1-1/2 in past the helix edge
# Joints: the board meets the closet deck at the alcove face of each wall opening (x 163); the closet deck
# (alcoves + turnback, full over the 1x3 grid) splits at the middle of the aisle so the halves mirror.
J_SOUTH, J_NORTH, J_EAST, J_N2 = 163.0, 163.0, 89.5, 150.0
b1 = BOARD.intersection(box(0, 95, J_SOUTH, 300))
b2 = CLOSET_DECK.intersection(box(0, J_EAST, 300, 300))
b3 = CLOSET_DECK.intersection(box(0, 0, 300, J_EAST))
n_a, n_rest = split(NORTH, "x", 4.5 + WALL_GAP + 96)
n2 = unary_union([n_rest, BOARD.intersection(box(150.0, 0, J_NORTH, 75))])
piece("N1", n_a, "34", "North wall", "Square cuts.")
piece("N2", n2, "34", "North wall east + board through the north opening",
      "One piece: the eased front edge (offsets) and the board across the opening into the alcove.")
# West wall + closet strip: three pieces, the south one running on through the closet strip.
Y_W1, Y_W2 = 302.5 - 96.0 - 96.0, 302.5 - 96.0
w_1, w_rest = split(WEST, "y", Y_W1)
w_2, w_3 = split(w_rest, "y", Y_W2)
piece("W1", unary_union([w_1, F_NW]), "34", "West wall, north end", "Includes the 10 in fillet at the NW inside corner.")
piece("W2", w_2, "34", "West wall, middle", "96 in.")
piece("W3", unary_union([w_3, CLOSET, F_CL]), "34", "West wall south end + closet strip",
      "96 in, one piece; cut the 6 in fillet curve where the closet strip steps in.")
piece("B1", b1, "34", "Board: helix exit, neck, south opening",
      "6 in. Square start 1-1/2 in outside the helix edge; field-fit to the end of the helix exit roadbed.")
piece("B2", b2, "34", "Closet deck, south half", "South alcove + turnback, full over the grid. Inside edge: offsets.")
piece("B3", b3, "34", "Closet deck, north half", "North alcove + turnback. Seam at the middle of the aisle end.")
piece("F3", F_SW, "34", "Fillet, SW peninsula corner", "18 in radius.")

# Balloon loop at 0 on the SW peninsula (AnyRail branchline): 4 in subroadbed on the open grid,
# only where there's no 3/4 deck under it. Centre line: R28.6 off the west wall, straight, R31 round the
# tip, straight back, R29 up to the west wall.
LOOP = (arc((45.1, 173.8), 28.6, 180, 90) + arc((78.8, 233.4), 31.0, -90, 90) + arc((44.5, 235.4), 29.0, 90, 180))
LOOP_W = 4.0
LOOP_BAND = LineString(LOOP).buffer(LOOP_W / 2, cap_style=2, join_style=1).difference(
    unary_union([WEST.buffer(0.0), F_SW, box(0, 0, 4.5 + WALL_GAP, 400)]))
for i, (gid, part, note) in enumerate([
        ("G1", LOOP_BAND.intersection(box(0, 0, 72.0, 218.0)), "Leaves the west wall deck on 28.6 in radius."),
        ("G2", LOOP_BAND.intersection(box(72.0, 0, 300, 233.4)), "31 in radius round the tip, centre (78.8, 233.4)."),
        ("G3", LOOP_BAND.intersection(box(72.0, 233.4, 300, 400)), "31 in radius; joint at the tip."),
        ("G4", LOOP_BAND.intersection(box(0, 218.0, 72.0, 400)), "29 in radius back to the west wall deck.")]):
    piece(gid, part, "34", "Balloon loop subroadbed", "4 in wide. " + note)

# +4.25: helix top covers the whole peninsula footprint (bulb + neck), same as the 0 in and staging decks.
# Like the lower level: one full 48 x 96 sheet across the north side from the bulb to the neck, then the
# south span and the neck end at the wall.
# Split west / east into two 48 in wide pieces, 72 in long; the neck end goes with the L7 ledge.
HTOP = PEN
X_H1 = HTOP.bounds[0] + 48.0
X_H2 = X_H1 + 48.0
piece("H1", HTOP.intersection(box(0, 0, X_H1, 300)), "12", "Helix top, west", "48 x 72: the west half of the bulb.")
piece("H2", HTOP.intersection(box(X_H1, 0, X_H2, 300)), "12", "Helix top, east", "48 wide: east bulb and the neck; curved south edge.")
NECK_END = HTOP.intersection(box(X_H2, 0, 300, 300))

# SW top: the peninsula plus the west wall south of the L9/L10 curve, out to the wall. The backdrop
# (AnyRail view block, y 231.8 to 233.3, wall to x 68.7) splits it into north and south halves; each half is
# one 96 in piece back from the tip plus a narrow strip at the wall.
SWT = unary_union([SW_TOP, box(4.5 + WALL_GAP, 200.5, 28.4, 266.5)])
BACKDROP = box(0, 231.8, 68.7, 233.3)
TIP_X = SW_TOP.bounds[2]
X_SW = TIP_X - 96.0
north = SWT.difference(BACKDROP).intersection(box(0, 0, 300, 231.8)).union(
    SWT.intersection(box(68.7, 231.8, 300, 233.3)))
south = SWT.difference(BACKDROP).intersection(box(0, 233.3, 300, 400))
s2 = north.intersection(box(X_SW, 0, 300, 400))
s4 = south.intersection(box(X_SW, 0, 300, 400))
piece("S1", SWT.intersection(box(0, 0, X_SW, 400)), "12", "SW top, strip at the wall",
      "One piece the full 66 in; the backdrop stands on it. Straight joints to L9, S2 and S4.")
piece("S2", s2, "12", "SW top, north half", "96 in back from the tip; 33 in round end. Stops at the backdrop.")
piece("S4", s4, "12", "SW top, south half", "96 in back from the tip; 33 in round end. Stops at the backdrop.")
piece("L1", L1, "12", "Ledge, west wall", "8 in wide.")
X_L3 = NW_C[0] + 96.0
piece("L2", L2, "12", "Ledge, NW corner", "26-1/2 in inside radius. Kept separate: merging it costs a sixth sheet.")
piece("L3", L3.intersection(box(0, 0, X_L3, 300)), "12", "Ledge, north wall", "96 in.")
piece("L4", L3.intersection(box(X_L3, 0, 300, 300)), "12", "Ledge, north wall east + alcove", "Through the north opening.")
piece("L5", L4, "12", "Ledge, turnback", "One piece, 30 x 84; 26-1/2 in inside radius at both ends.")
piece("L7", unary_union([NECK_END, box(NECK_END.bounds[2] - 0.2, L5A.bounds[1], L5A.bounds[2], L5A.bounds[3])]), "12",
      "Ledge, south alcove + helix neck end", "Covers the neck at the wall stubs and runs through the south opening.")
piece("L9", L_SW, "12", "Ledge, SW corner", "One piece: 40.2 in inside radius, out to the wall; straight edge on the SW top.")


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


def orient(g, rot):
    if isinstance(rot, str):  # long side of the minimum rectangle horizontal ('h') or vertical ('v')
        cs = list(g.minimum_rotated_rectangle.exterior.coords)
        e = max([(cs[0], cs[1]), (cs[1], cs[2])], key=lambda q: math.dist(*q))
        rot = -math.degrees(math.atan2(e[1][1] - e[0][1], e[1][0] - e[0][0])) + (90 if rot == "v" else 0)
    g = affinity.rotate(g, rot, origin="centroid")
    minx, miny, _, _ = g.bounds
    return affinity.translate(g, -minx, -miny)


def pack(level, order, pinned=()):
    """First fit, decreasing: pinned sheets first, then each piece goes on the first sheet where it fits,
    tried at several rotations against candidate corners (sheet edges and edges of placed pieces)."""
    sheets = [[(pid, affinity.translate(orient(P[pid]["geom"], rot), x, y)) for pid, x, y, rot in sh] for sh in pinned]
    for pid in order:
        done = False
        for sh in sheets + [[]]:
            best = None
            for rot in (0, 90, "h", "v", 180, 270):
                g0 = orient(P[pid]["geom"], rot)
                gw, gh = g0.bounds[2], g0.bounds[3]
                if gw > SW + 1e-6 or gh > SH + 1e-6:
                    continue
                xs = sorted({float(v) for v in range(0, int(SW - gw) + 1)} | {round(q.bounds[2] + KERF, 3) for _, q in sh})
                ys = sorted({float(v) for v in range(0, int(SH - gh) + 1)} | {round(q.bounds[3] + KERF, 3) for _, q in sh}
                            | {round(SH - gh, 3)})
                for x in xs:
                    for y in ys:
                        if x + gw > SW + 1e-6 or y + gh > SH + 1e-6:
                            continue
                        bx = (x - KERF, y - KERF, x + gw + KERF, y + gh + KERF)
                        near = [q for _, q in sh if not (q.bounds[0] > bx[2] or q.bounds[2] < bx[0]
                                                         or q.bounds[1] > bx[3] or q.bounds[3] < bx[1])]
                        if best and (x + y * 0.5, y) >= best[0]:
                            continue
                        g = affinity.translate(g0, x, y)
                        if all(g.distance(q) >= KERF - 1e-6 for q in near):
                            key = (x + y * 0.5, y)
                            if best is None or key < best[0]:
                                best = (key, g)
                        if best and best[0][0] <= x:
                            break
            if best:
                if not sh:
                    sheets.append(sh)
                sh.append((pid, best[1]))
                done = True
                break
        if not done:
            raise SystemExit(f"{pid} fits no sheet")
    return sheets


def add_sheets(level, first_id, sheets, reserve_note):
    for i, sh in enumerate(sheets):
        sid = chr(ord(first_id) + i)
        used = unary_union([q for _, q in sh])
        SHEETS.append(dict(id=sid, level=level, title=" · ".join(p for p, _ in sh),
                           placed=[(p, q, 0) for p, q in sh], reserve=None, reserve_label=None))


def pack_best(level, ids, pinned=(), tries=14):
    """Run the first-fit packer over several piece orders; keep the fewest sheets, then the emptiest last sheet."""
    import random
    rnd = random.Random(7)
    base = sorted(ids, key=lambda k: -P[k]["geom"].area)
    best = None
    for t in range(tries):
        order = base[:] if t == 0 else sorted(base, key=lambda k: -P[k]["geom"].area * rnd.uniform(0.6, 1.4))
        try:
            sh = pack(level, order, pinned)
        except SystemExit:
            continue
        key = (len(sh), sum(q.area for _, q in sh[-1]))
        if best is None or key < best[0]:
            best = (key, sh)
    return best[1]


A34 = pack_best("34", ["B2", "B3", "B1", "W1", "G2", "G3", "G1", "G4", "F3"], pinned=[
    [("N1", 0, 0, 0), ("N2", 0, 24 + KERF, 0)],
    [("W2", 0, 0, 90), ("W3", 0, 24 + KERF, 90)],
])
add_sheets("34", "A", A34, "")
order12 = sorted([k for k, v in P.items() if v["level"] == "12"], key=lambda k: -P[k]["geom"].area)
A12 = pack_best("12", order12)
add_sheets("12", chr(ord("A") + len(A34)), A12, "")


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
    bench = unary_union([NORTH, WEST, CLOSET, ALCOVE_N, ALCOVE_S, TURNBACK, PEN, SW_TOP])
    o.append(f'<path class="bench" d="{t(bench)}"/>')
    o.append(f'<path class="wall" d="{t(walls)}"/>')
    for p in P.values():
        if p["level"] != level or p["id"].startswith("R"):
            continue
        o.append(f'<path class="pc l{level}" d="{t(p["geom"])}"/>')
        c = p["geom"].representative_point()
        o.append(f'<text class="mlbl" x="{(c.x - x0 + pad) * scale:.1f}" y="{(c.y - y0 + pad) * scale + 4:.1f}" '
                 f'text-anchor="middle">{p["id"]}</text>')
    for (cx, cy) in ((NW_C, TB_N, TB_S, SW_C) if level == "12" else (S_CURVE_C, N_CURVE_C)):
        if True:
            o.append(f'<circle class="ctr" cx="{(cx - x0 + pad) * scale:.1f}" cy="{(cy - y0 + pad) * scale:.1f}" r="2.5"/>')
    o.append(f'<text class="axis" x="{(140 - x0 + pad) * scale}" y="{(290 - y0 + pad) * scale}">N up · 1 grid = 12 in</text>')
    o.append("</svg>")
    return "\n".join(o)


def offsets():
    """Shop offsets for the two free-form curves."""
    rows = {"N2": [], "T1": [], "H2": []}
    # helix top south edge: depth south of the neck's north edge (y 114, in line with the wall stubs),
    # measured west from the wall stubs
    xe = PEN.bounds[2]
    for k in range(0, int(xe - PEN.bounds[0]) + 1, 6):
        hit = LineString([(xe - k - 0.01, 90), (xe - k - 0.01, 200)]).intersection(PEN)
        if not hit.is_empty:
            rows["H2"].append((k, hit.bounds[3] - 114.0))
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
