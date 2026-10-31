"""Main-level room geometry from the AnyRail plan, shared by the plywood cut plan and the framing drawings.

Room inches: x east from the room's west corner, y south from the north wall line. Needs shapely.
"""
import math

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union


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
CLOSET = box(4.5 + WALL_GAP, 266.5, 18.5, 302.5)   # stops 1/8 off the wall like WEST, so W2 and W3 are one straight rip
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
# SW inside corner: the 18 in fillet, squared off down to the balloon loop's outer edge so the loop's first
# curve sits on it and G1 starts with a square cut.
# down to the inside edge of the 9-1/4 in balloon-loop pieces (233.4 - 33 + 9.25), so F3 meets G1 full width
F_SW = box(28.5, 182.5, 46.5, 209.65).difference(disc(46.5, 182.5, 18.0))

# SW peninsula top: 84 x 66 with a 33 in round east end
SW_TOP = outline(SW_MOD)

# +4.25 ledge for the two outer main tracks (centres from AnyRail D.01 layer)
NW_C, TB_N, TB_S, SW_C = (39.0, 81.2), (183.6, 81.2), (183.6, 96.9), (52.7, 160.3)
R_IN = 26.5        # inner edge of ledge: inner track R28.5 less 2 in
L_W = 8.0          # straight ledge width
L1 = box(4.5 + WALL_GAP, 81.2, 4.5 + L_W, 160.3)
L2 = box(4.5 + WALL_GAP, 47.5 + WALL_GAP, NW_C[0], NW_C[1]).difference(disc(*NW_C, R_IN))
L3 = box(NW_C[0], 47.5 + WALL_GAP, 187.0, 47.5 + L_W)
# Inner main: 0 on N2 to x 125.7, then climbs about 2.25% round the NW corner to 4.25 at y 139 (AnyRail D.01 heights),
# while the outer main stays at 4.25. The ledge boards stay full width; RAMP_CUT marks where to rip each one so the
# wall side carries the outer main at 4.25 and the aisle side is the inner main's ramp strip (scrap east of x 125.7,
# where the inner main is at 0 underneath). RAMP_TRIM marks the ramp strip's aisle edge beside the 0 in branchline.
OUT_N, IN_N, OUT_W, IN_W = 50.3, 52.8, 8.0, 10.5          # track centres: north wall y, west wall x
OUT_R, IN_R = NW_C[0] - OUT_W, NW_C[0] - IN_W             # NW curve radii, 31 and 28.5
EDGE = 1.25                                                # cut line past the track centre
RAMP_X0, RAMP_Y1 = 125.7, 139.0                           # inner main at 0 (north wall) and at 4.25 (west wall)


def _arc_line(r, n=48):   # NW corner quarter, north wall end to west wall end
    return LineString([(NW_C[0] + r * math.cos(math.radians(270 - 90 * k / n)),
                        NW_C[1] + r * math.sin(math.radians(270 - 90 * k / n))) for k in range(n + 1)])


RAMP_CUT = [LineString([(NW_C[0], OUT_N + EDGE), (187.0, OUT_N + EDGE)]), _arc_line(OUT_R - EDGE),
            LineString([(OUT_W + EDGE, NW_C[1]), (OUT_W + EDGE, RAMP_Y1)])]
RAMP_TRIM = [LineString([(NW_C[0], IN_N + EDGE), (RAMP_X0, IN_N + EDGE)]), _arc_line(IN_R - EDGE)]
RAMP_LEN = (RAMP_X0 - NW_C[0]) + math.pi / 2 * IN_R + (RAMP_Y1 - NW_C[1])
STADIUM = unary_union([disc(*TB_N, R_IN), disc(*TB_S, R_IN), box(TB_N[0] - R_IN, TB_N[1], TB_N[0] + R_IN, TB_S[1])])
L4 = box(187.0, 47.5 + WALL_GAP, 217.0 - WALL_GAP, 131.5 - WALL_GAP).difference(STADIUM)
L5A = box(158.5, TB_S[1] + R_IN, 187.0, 131.5 - WALL_GAP)
SW_R_IN, SW_R_OUT = 40.2, SW_C[0] - 4.5
# SW corner: everything outside the inner band radius, from the end of L1 down to the peninsula edge (y 200.5).
L_SW = box(4.5 + WALL_GAP, SW_C[1], SW_C[0], 200.5).difference(disc(*SW_C, SW_R_IN))


# room walls and wall stubs (for drawings)
WALLS = unary_union([box(0, 43, 221.5, 47.5), box(0, 43, 4.5, 307), box(4.5, 302.5, 177, 307),
                     box(217, 47.5, 221.5, 131.5), box(158.5, 131.5, 221.8, 136), box(158.5, 114, 163, 131.5),
                     box(158.5, 47.5, 163, 65)])
