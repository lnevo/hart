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

from main_level_geometry import *  # noqa: E402,F403 - room outlines, decks, ledges, fillets


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
# B1 rests on the helix at its post and on a 1x3 joist on the wall stub (x 158.5). Once it turns out of the helix
# it widens to 10 in along the straight, up to the wall, so a pair of 3/8 rods 4 in either side of the centre
# line clears both roadbeds wherever they go (a temporary post first); 6 in again through the wall opening
X_STRAIGHT, X_ROD, ROD_OFF = 140.3, 142.5, 4.0
B1_WIDE = box(X_STRAIGHT, Y_SOUTH - 5.0, 158.5, Y_SOUTH + 5.0)
b1 = unary_union([BOARD.intersection(box(0, 95, J_SOUTH, 300)), B1_WIDE])
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
      "6 in round the curve, 10 in along the straight to the wall (rods), 6 in through the opening. Square start 1-1/2 in outside the helix edge; field-fit to "
      "the end of the helix exit roadbed.")
piece("B2", b2, "34", "Closet deck, south half", "South alcove + turnback, full over the closet boxes. Inside edge: offsets.")
piece("B3", b3, "34", "Closet deck, north half", "North alcove + turnback. Seam at the middle of the aisle end.")
piece("F3", F_SW, "34", "SW inside corner + balloon loop start", "Square corners; 18 in fillet on the aisle side.")

# Balloon loop at 0 on the SW peninsula (AnyRail branchline): 4 in subroadbed on the open grid,
# only where there's no 3/4 deck under it. Centre line: R28.6 off the west wall, straight, R31 round the
# tip, straight back, R29 up to the west wall.
LOOP = (arc((45.1, 173.8), 28.6, 180, 90) + arc((78.8, 233.4), 31.0, -90, 90) + arc((44.5, 235.4), 29.0, 90, 180))
LOOP_W = 4.0
LOOP_BAND = LineString(LOOP).buffer(LOOP_W / 2, cap_style=2, join_style=1).difference(
    unary_union([WEST.buffer(0.0), F_SW, box(0, 0, 4.5 + WALL_GAP, 400)]))
X_ARC = 78.8   # where the loop turns round the tip: G2 / G3 are pure quarter circles
LOOP_C = (X_ARC, 233.4)
_g4 = LOOP_BAND.intersection(box(28.5, 218.0, X_ARC, 400))
G_W = round((_g4.bounds[3] - _g4.bounds[1]) * 8) / 8   # G4 is the box round the 29 in curve; G1-G3 match its width
G_RO = 31.0 + LOOP_W / 2              # outer edge stays on the 4 in band; the extra width goes inside the loop
_ring = disc(*LOOP_C, G_RO).difference(disc(*LOOP_C, G_RO - G_W))
for i, (gid, part, note) in enumerate([
        ("G1", box(46.5, LOOP_C[1] - G_RO, X_ARC, LOOP_C[1] - G_RO + G_W),
         "Plain rectangle on the straight; square cuts at F3 and G2."),
        ("G2", _ring.intersection(box(X_ARC, 0, 300, LOOP_C[1])),
         f"Quarter circle, {G_RO - G_W:g} / {G_RO:g} in edges, centre (78.8, 233.4)."),
        ("G3", _ring.intersection(box(X_ARC, LOOP_C[1], 300, 400)), "Quarter circle, same as G2; joint at the tip."),
        ("G4", box(*_g4.bounds), "Plain rectangle from W3 to G3; wide enough for the 29 in curve.")]):
    piece(gid, part, "34", "Balloon loop subroadbed", f"{G_W:g} in wide, outer edge on the 4 in roadbed edge. " + note)

# +4.25: helix top covers the whole peninsula footprint (bulb + neck), same as the 0 in and staging decks.
# Like the lower level: one full 48 x 96 sheet across the north side from the bulb to the neck, then the
# south span and the neck end at the wall.
# Split west / east into two 48 in wide pieces, 72 in long; the neck end goes with the L7 ledge.
HTOP = PEN
X_H1 = HTOP.bounds[0] + 48.0
X_H2 = X_H1 + 48.0
piece("H1", HTOP.intersection(box(0, 0, X_H1, 300)), "12", "Helix top, west", "48 x 72: the west half of the bulb.")
Y_L7 = L5A.bounds[1]          # top of the south-alcove ledge, carried straight west to H1
piece("H2", HTOP.intersection(box(X_H1, 0, 300, Y_L7)), "12", "Helix top, north-east",
      "East bulb and the neck's north side, out to the wall stubs.")
NECK_SOUTH = HTOP.intersection(box(X_H1, Y_L7, 300, 300))

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
piece("L1", L1, "12", "Ledge, west wall", "8 in wide. North end to y 139 (57-3/4 in): rip 4-5/8 in from the wall edge (dashed); the aisle side is the inner main's ramp strip.")
X_L3 = NW_C[0] + 96.0
piece("L2", L2, "12", "Ledge, NW corner", "26-1/2 in inside radius. Cut on the dashed arc (29-3/4 in) for the ramp; trim the strip to the dotted arc (27-1/4 in).")
piece("L3", L3.intersection(box(0, 0, X_L3, 300)), "12", "Ledge, north wall", "96 in. Rip 3-15/16 in from the wall edge (dashed). West of x 125.7 the aisle side is the ramp strip: trim it to 6-7/16 from the wall edge (dotted).")
piece("L4", L3.intersection(box(X_L3, 0, 300, 300)), "12", "Ledge, north wall east + alcove",
      "Through the north opening. Rip 3-15/16 in from the wall edge (dashed); the aisle side is scrap, the inner main is at 0 under it.")
PLY12 = 0.47          # 12 mm Baltic birch
GRADE = 4.25 / RAMP_LEN
piece("L5", L4, "12", "Ledge, turnback", "One piece, 30 x 84; 26-1/2 in inside radius at both ends.")
piece("L7", unary_union([NECK_SOUTH, box(NECK_SOUTH.bounds[2] - 0.2, L5A.bounds[1], L5A.bounds[2], L5A.bounds[3])]), "12",
      "Helix top south-east + south alcove ledge",
      "Straight top edge from H1 to the alcove wall; curved south edge; through the south opening.")
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


XF = {}   # pinned pid -> (mirrored, rot, x, y) as lay_out placed it, so marks drawn in room inches follow the piece


def place_mark(pid, h):
    """Move a room-inch geometry h (a mark on piece pid) the same way lay_out moved the piece onto its sheet."""
    mirror, rot, x, y = XF[pid]
    g = P[pid]["geom"]
    if mirror:
        c = g.centroid
        g, h = affinity.scale(g, -1, 1, origin=c), affinity.scale(h, -1, 1, origin=c)
    if isinstance(rot, str):   # as orient(): the minimum rectangle's long side
        cs = list(g.minimum_rotated_rectangle.exterior.coords)
        e = max([(cs[0], cs[1]), (cs[1], cs[2])], key=lambda q: math.dist(*q))
        rot = -math.degrees(math.atan2(e[1][1] - e[0][1], e[1][0] - e[0][0])) + (90 if rot == "v" else 0)
    c = g.centroid
    minx, miny, _, _ = affinity.rotate(g, rot, origin=c).bounds
    return affinity.translate(affinity.rotate(h, rot, origin=c), x - minx, y - miny)


def marks(pid):
    """(kind, line) marks on a piece in room inches: the ramp cut and the trim beside the branchline."""
    g = P[pid]["geom"].buffer(1e-3)
    out = []
    for kind, lines in (("cut", RAMP_CUT), ("trim", RAMP_TRIM)):
        for ln in lines:
            m = ln.intersection(g)
            if not m.is_empty and m.length > 0.5:
                out.append((kind, m))
    return out


def line_d(m, sx, ox, oy):
    parts = m.geoms if hasattr(m, "geoms") else [m]
    return " ".join("M" + " L".join(f"{ox + x * sx:.2f},{oy + y * sx:.2f}" for x, y in p.coords) for p in parts)


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


def clearance(q, others, area=None):
    """Smallest gap from q to any other piece or to the edge of its area (default the sheet), so a centred piece
    sits mid-way in its space."""
    gaps = [q.distance(o) for o in others]
    ax0, ay0, ax1, ay1 = area.bounds if area is not None else (0, 0, SW, SH)
    x0, y0, x1, y1 = q.bounds
    gaps += [x0 - ax0, y0 - ay0, ax1 - x1, ay1 - y1]
    return min(gaps) if gaps else 0.0


PIVOT = {}   # arc pid -> trammel pivot on its sheet


def arc_nest(pids, x0=0.0, gap=0.0, centre=(78.8, 233.4)):
    """Nest identical arcs like the helix roadbed: chord across the 48 in width, all facing the same way,
    stepped along the sheet by the smallest advance that keeps a kerf plus `gap` between them. The arcs bulge toward the left edge so
    each arc centre falls on the sheet itself and can be marked with a trammel pivoting on the plywood."""
    out = []
    for pid in pids:
        g, c = P[pid]["geom"], Point(centre)
        pts = list(g.convex_hull.exterior.coords)
        a, b = max(((p, q) for p in pts for q in pts), key=lambda pq: math.dist(*pq))   # chord = the two end cuts
        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        o = g.centroid
        q, c = affinity.rotate(g, 90 - ang, origin=o), affinity.rotate(c, 90 - ang, origin=o)
        if q.centroid.x > (q.bounds[0] + q.bounds[2]) / 2:   # bulge to the left: the arc centre lands on the sheet
            o = q.centroid
            q, c = affinity.rotate(q, 180, origin=o), affinity.rotate(c, 180, origin=o)
        dx, dy = -q.bounds[0] + (x0 if not out else 0), (SH - (q.bounds[3] - q.bounds[1])) / 2 - q.bounds[1]
        q, c = affinity.translate(q, dx, dy), affinity.translate(c, dx, dy)
        while out and min(q.distance(o) for _, o in out) < KERF + gap - 1e-6:
            q, c = affinity.translate(q, 0.125, 0), affinity.translate(c, 0.125, 0)
        out.append((pid, q))
        PIVOT[pid] = (c.x, c.y)
    return out


def lay_out(level, pins, autos=(), fixed=()):
    """One sheet laid out for the saw. pins: (pid, rot, x, y), rot 'F' / 'F180' = flipped (then turned), x 'R' = flush right, y 'B' = flush bottom,
    x 'S' = slide right until it fits, ('A', gap) = as far right as fits less gap, 'M' = middle of the room it fits in. fixed: pieces already placed (arc_nest). autos: small pieces placed in the
    leftover space; (pid, "C"[, area]) centres the piece where it has the most clearance, square to the sheet;
    "CA" also tries 5 degree steps, face up or flipped, so a curved piece can follow a curved offcut."""
    placed = list(fixed)
    for pid, rot, x, y in pins:
        g = P[pid]["geom"]
        mirror = isinstance(rot, str) and rot.startswith("F")
        if mirror:   # 'F' / 'F180': flipped end for end, then turned
            g, rot = affinity.scale(g, -1, 1, origin="centroid"), int(rot[1:] or 0)
        q0 = orient(g, rot)
        w, h = q0.bounds[2], q0.bounds[3]
        yy = SH - h if y == "B" else y
        if isinstance(x, tuple) and x[0] == "with":   # ("with", pid): left end in line with a placed piece's
            x = dict(placed)[x[1]].bounds[0]
        if isinstance(y, tuple) and y[0] == "under":   # ("under", pid): one kerf below a placed piece
            yy = dict(placed)[y[1]].bounds[3] + KERF
        if isinstance(x, tuple):   # ("A", gap): as far right as it fits, then back off to leave `gap` to its neighbour
            free = [k / 8 for k in range(int((SW - w) * 8), -1, -1)
                    if all(affinity.translate(q0, k / 8, yy).distance(o) >= KERF - 1e-6 for _, o in placed)]
            x = free[0] - (x[1] - min(affinity.translate(q0, free[0], yy).distance(o) for _, o in placed))
        xs = [SW - w] if x == "R" else ([k / 4 for k in range(0, int((SW - w) * 4) + 1)] if x in ("S", "M") else [x])
        if x == "M":   # the most room to its neighbours, keeping clear of any trammel pivot marked on the sheet
            piv = [Point(v) for k, v in PIVOT.items() if any(k == pid2 for pid2, _ in placed)]
            room = lambda q: min([q.distance(o) for _, o in placed] + [q.distance(c) for c in piv])
            ok = [xx for xx in xs if all(affinity.translate(q0, xx, yy).distance(o) >= KERF - 1e-6 for _, o in placed)]
            xs = [max(ok, key=lambda xx: room(affinity.translate(q0, xx, yy)))] if ok else []
        for xx in xs:
            q = affinity.translate(q0, xx, yy)
            if all(q.distance(o) >= KERF - 1e-6 for _, o in placed):
                break
        else:
            raise SystemExit(f"{pid}: no room")
        placed.append((pid, q))
        XF[pid] = (mirror, rot, xx, yy)
    for item in autos:
        pid, mode, area = (item, "", None) if isinstance(item, str) else (tuple(item) + (None,))[:3]
        best = None
        rots = [(r, False) for r in (0, 90, "h", "v", 180, 270)]
        if mode == "CA":   # any 5 degree step, either face up (a flipped piece is just cut upside down)
            rots += [(r, m) for m in (False, True) for r in range(0, 360, 5)]
        for rot, mirror in rots:
            g = affinity.scale(P[pid]["geom"], -1, 1, origin="centroid") if mirror else P[pid]["geom"]
            q0 = orient(g, rot)
            w, h = q0.bounds[2], q0.bounds[3]
            if w > SW or h > SH:
                continue
            for yi in range(0, int((SH - h) * 2) + 1):
                for xi in range(0, int((SW - w) * 2) + 1):
                    q = affinity.translate(q0, xi / 2, yi / 2)
                    others = [o for _, o in placed]
                    if area is not None and not area.buffer(1e-6).contains(q):
                        continue
                    if not all(q.distance(o) >= KERF - 1e-6 for o in others):
                        continue
                    key = (-clearance(q, others, area),) if mode in ("C", "CA") else (xi / 2 + yi / 2 * 0.5, yi)
                    if best is None or key < best[0]:
                        best = (key, q)
                    if mode not in ("C", "CA"):
                        break
        if best is None:
            raise SystemExit(f"{pid}: no room on this sheet")
        placed.append((pid, best[1]))
    for pid, q in placed:
        if not box(0, 0, SW, SH).buffer(1e-6).contains(q):
            raise SystemExit(f"{pid}: off the sheet")
    for i in range(len(placed)):
        for j in range(i + 1, len(placed)):
            if placed[i][1].distance(placed[j][1]) < KERF - 1e-6:
                raise SystemExit(f"{placed[i][0]} and {placed[j][0]} closer than the kerf")
    return placed


LAYOUT34 = [
    ([("N1", 0, 0, 0), ("N2", 0, 0, "B"), ("F3", 270, "R", "B")], [], []),
    ([("W2", 90, 0, 0), ("W3", 90, 0, "B")], [], []),
    # B1 flipped: square end on the left edge, straight run on the bottom edge (both square corners in the corner)
    ([("W1", "F270", 0, 0), ("B3", 0, "R", 0), ("B1", "F", 0, "B")], [], []),   # W1 flipped: its long side on the left edge
    # G4 on the top edge, G1 under it with their left ends in line: the long cut and the end cut are shared
    ([("B2", 0, "R", "B"), ("G4", 0, "M", 0), ("G1", 0, ("with", "G4"), ("under", "G4"))], [],
     arc_nest(["G2", "G3"], x0=0.25, gap=1.5)),
]
LAYOUT12 = [
    ([("H1", 90, 0, 0), ("L9", 180, "R", 0)], [], []),
    ([("S4", 0, 0, 0), ("L3", 0, 0, "B")], [], []),
    ([("S2", 0, 0, 0), ("L1", 90, 0, "B")], [], []),
    ([("L7", 0, 0, 0), ("L2", 90, "R", "B"), ("H2", 0, "M", "B")], [], []),   # H2 on the bottom edge, centred
    ([("L5", 90, 0, 0), ("S1", 90, 0, "B"), ("L4", "h", "M", 0)], [], []),   # L4 on the top edge inside L5
]
# Which 3/4 stock each sheet is cut from: 2 furniture birch on hand, 2 Baltic birch bought. The Baltic (void-free core)
# takes the narrow, curved and rod-hung pieces; the furniture birch the wide wall shelves, which sit on joists 16 in o.c.
STOCK34 = {"A": "3/4 furniture birch", "B": "3/4 furniture birch", "C": "3/4 Baltic birch", "D": "3/4 Baltic birch"}
A34 = [lay_out("34", pins, autos, fixed) for pins, autos, fixed in LAYOUT34]
A12 = [lay_out("12", pins, autos, fixed) for pins, autos, fixed in LAYOUT12]
for lvl, sheets in (("34", A34), ("12", A12)):
    ids = sorted(p for sh in sheets for p, _ in sh)
    want = sorted(k for k, v in P.items() if v["level"] == lvl)
    assert ids == want, (lvl, set(want) ^ set(ids))
add_sheets("34", "A", A34, "")
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


def frac(v, den=8):
    """inches to nearest 1/den as text"""
    e = round(v * den) / den
    whole = int(e)
    f = e - whole
    if abs(f) < 1e-9:
        return f"{whole}"
    n, dd = int(round(f * den)), den
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
                 f'{"balloon loop roadbed arcs" if s["level"] == "34" else "spare"}</text>')
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
    for pid, g, _ in s["placed"]:
        for kind, m in (marks(pid) if pid in XF else []):
            o.append(f'<path class="{kind}" d="{line_d(place_mark(pid, m), scale, ox, oy)}"/>')
    pivots = []
    for pid, g, _ in s["placed"]:
        if pid in PIVOT:   # trammel pivot: a cross; the distance in from the left and top edges goes under the sheet
            px, py = ox + PIVOT[pid][0] * scale, oy + PIVOT[pid][1] * scale
            o.append(f'<path class="pivot" d="M{px - 6:.1f} {py:.1f}H{px + 6:.1f}M{px:.1f} {py - 6:.1f}V{py + 6:.1f}"/>')
            o.append(f'<text class="rlbl" x="{px:.1f}" y="{py + 20:.1f}" text-anchor="middle">{pid}</text>')
            pivots.append(f"{pid} {frac(PIVOT[pid][0])}, {frac(PIVOT[pid][1])}")
    if pivots:
        o.append(f'<text class="axis" x="{ox + SW * scale / 2:.1f}" y="{H - 6}" text-anchor="middle">'
                 f'trammel pivots, in from left, top: {" · ".join(pivots)}</text>')
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
    walls = WALLS
    bench = unary_union([NORTH, WEST, CLOSET, ALCOVE_N, ALCOVE_S, TURNBACK, PEN, SW_TOP])
    o.append(f'<path class="bench" d="{t(bench)}"/>')
    o.append(f'<path class="wall" d="{t(walls)}"/>')
    for p in P.values():
        if p["level"] != level:
            continue
        o.append(f'<path class="pc l{level}" d="{t(p["geom"])}"/>')
        c = p["geom"].representative_point()
        o.append(f'<text class="mlbl" x="{(c.x - x0 + pad) * scale:.1f}" y="{(c.y - y0 + pad) * scale + 4:.1f}" '
                 f'text-anchor="middle">{p["id"]}</text>')
    if level == "12":
        for kind, lines in (("cut", RAMP_CUT), ("trim", RAMP_TRIM)):
            for ln in lines:
                o.append(f'<path class="{kind}" d="{line_d(ln, scale, (pad - x0) * scale, (pad - y0) * scale)}"/>')
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


def ramp_stations(step=12.0):
    """Inner main ramp: every `step` in along the track from x 125.7, the height of the strip top and the riser under it."""
    a, b = RAMP_X0 - NW_C[0], math.pi / 2 * IN_R
    out, s = [], 0.0
    while s < RAMP_LEN + 1e-6:
        if s <= a:
            where = f"north wall, x {RAMP_X0 - s:.1f}"
        elif s <= a + b:
            where = f"NW curve, {math.degrees((s - a) / IN_R):.0f} deg round"
        else:
            where = f"west wall, y {NW_C[1] + s - a - b:.1f}"
        z = s * GRADE
        out.append(dict(s=round(s, 1), where=where, z=frac(z, 16), riser=frac(z - PLY12, 16) if z >= PLY12 else "taper"))
        s = s + step if s + step < RAMP_LEN or s >= RAMP_LEN - 1e-6 else RAMP_LEN
    return out


summary = dict(
    pieces=[dict(id=p["id"], level=p["level"], name=p["name"], note=p["note"],
                 w=frac(p["geom"].bounds[2] - p["geom"].bounds[0]), h=frac(p["geom"].bounds[3] - p["geom"].bounds[1]),
                 area=round(p["geom"].area / 144, 1)) for p in P.values()],
    sheets=[dict(id=s["id"], level=s["level"], title=s["title"], pieces=[q[0] for q in s["placed"]],
                 stock=STOCK34.get(s["id"]) if s["level"] == "34" else "1/2 Baltic birch",
                 used=round(sum(q[1].area for q in s["placed"]) / (SW * SH) * 100)) for s in SHEETS],
    area34=round(sum(p["geom"].area for p in P.values() if p["level"] == "34") / 144, 1),
    area12=round(sum(p["geom"].area for p in P.values() if p["level"] == "12") / 144, 1),
    offsets=offsets(),
    ramp=ramp_stations(),
    grade=round(GRADE * 100, 2), ramp_len=round(RAMP_LEN, 1),
)
# Presentation-attribute fallbacks (page CSS overrides them for light/dark themes).
FALLBACK = {
    "sheet": 'fill="#fbfaf6" stroke="#1f2326"', "grid": 'stroke="#e7e3d8"', "reserve": 'fill="#ece8dc" stroke="#5f666b"',
    "rlbl": 'fill="#5f666b" font-size="13"', "pc l34": 'fill="#e3c48f" stroke="#9a7434"',
    "pc l12": 'fill="#a9c6c0" stroke="#3f7268"', "plbl": 'fill="#1f2326" font-size="17" font-weight="700"',
    "plbl sm": 'fill="#1f2326" font-size="12" font-weight="700"', "pdim": 'fill="#1f2326" font-size="13"',
    "axis": 'fill="#5f666b" font-size="12"', "bench": 'fill="#efece3" stroke="#d9d6cc"', "wall": 'fill="#b9b4a8"',
    "mlbl": 'fill="#1f2326" font-size="11" font-weight="600"', "ctr": 'fill="#b4532a"', "pivot": 'stroke="#b4532a" stroke-width="2"',
    "cut": 'fill="none" stroke="#b4532a" stroke-width="2" stroke-dasharray="8 5"',
    "trim": 'fill="none" stroke="#b4532a" stroke-width="1.5" stroke-dasharray="2 4"',
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
