#!/usr/bin/env python3
"""Main-level framing drawings: the framing plan for the whole level, the typical shelf section, the riser block
on the existing back L-girder, the new front girders (1x2 web on the face over a flat 1x3 flange, joists butted to the web), the girder
junctions, and the build sequence. Needs reportlab and shapely (room outlines from main_level_geometry).

Section geometry is in real inches, elevation 0 = top of the 3/4 ply subroadbed (the 0" grade level),
staging deck top = -15. The framing plan is in room inches (x east, y south), the same as the cut plan.
"""
import sys

from reportlab.lib.colors import Color, black
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from main_level_geometry import (CLOSET, CLOSET_DECK, F_CL, F_NW, F_SW, NORTH, PEN, SW_TOP, WALL_GAP, WALLS, WEST)

OUT = sys.argv[1] if len(sys.argv) > 1 else "main_level_joist_construction.pdf"
PW, PH = landscape(letter)
PAGES = 7

# ---- stack (inches) ----
PLY = 0.72            # 3/4 ply as measured
J_TOP, J_BOT = -PLY, -PLY - 1.5             # 1x2 joist on edge
FLANGE_TOP = -3.25                          # existing back L-girder (as installed)
FLANGE_BOT = FLANGE_TOP - 0.75
WEB_BOT = FLANGE_BOT - 3.5
BLOCK_TOP, BLOCK_BOT = J_TOP, J_TOP - 2.5   # 1x3 riser block, tops flush with joist
# new front girder: 1x2 web on edge on the face, flush with the joist tops; 1x3 flange flat under it carries the joists
FG_TOP = J_TOP
FG_FL_TOP = J_BOT     # web bottom = flange top = joist bottom
FG_BOT = FG_FL_TOP - 0.75
SHIM = 0.25           # one shim where a front girder end seats on a -3.25 girder (0.28 gap, like the riser blocks)
STAGING_TOP = -15.0
STAGING_RAIL = STAGING_TOP + 0.236 + 0.160  # 6 mm cork + Atlas code 83
DEPTH = 24.0          # shelf depth used for the typical section (west wall)
EDGE = DEPTH          # deck edge, from the wall
FG_OUT = EDGE         # west girder: web outer face on the deck edge
FG_WEB_IN = FG_OUT - 0.75
FG_FL_IN = FG_OUT - 2.5
ROD_X = (FG_FL_IN + FG_WEB_IN) / 2   # rod through the flange's joist bearing, between joists
GIRDER_X0 = 0.0       # existing girder: web against the wall, flange on top
WEB_X1 = GIRDER_X0 + 0.75
FLANGE_X1 = GIRDER_X0 + 1.5
BLOCK_L = 5.0
JOIST_X0 = 0.125      # 1/8 off the wall
BLOCK_X0 = JOIST_X0  # wall end square, flush with the joist end
CLIP = BLOCK_TOP - BLOCK_BOT                # full-height 45 deg miter on the front end

# ---- framing plan (room inches) ----
Y_WALL_N, X_WALL_W = 47.5, 4.5
NG = (62.625, 65.125)              # north front girder flange, y; set back to the eased corner's front edge
NG_WEB = (63.5, 64.25)             # north web, centred on its flange: joists butt the back, lookouts the front
NG_X = (X_WALL_W + WALL_GAP, 158.5 - WALL_GAP)
WG = (26.0, 28.5)                  # west front girder flange, x; web on the deck edge
WG_WEB = (27.75, 28.5)
PG_N, PG_S = (218.5, 220.0), (247.0, 248.5)   # existing peninsula girders, 18 in in from each edge
PG_X1 = 100.0                      # drawn to here; verify the as-built end
WG_Y = (NG[1], PG_N[1])            # west flange: north flange edge to the far side of the peninsula girder
N_RODS = (X_WALL_W + 154 / 3, X_WALL_W + 2 * 154 / 3)
W_RODS = (WG_Y[0] + (PG_N[0] - WG_Y[0]) / 3, WG_Y[0] + 2 * (PG_N[0] - WG_Y[0]) / 3)
# joist stations (centres); every deck seam lands on a joist
N_JOISTS = [5.0, 21.0, 37.0, 53.0, 69.0, 85.0, 100.625, 116.625, 132.625, 148.625, 158.0]   # N1/N2 at 100.625
W_JOISTS = [71.0, 84.17, 97.33, 110.5, 125.44, 140.38, 155.31, 170.25, 185.19, 200.125]     # N/W 71, W1/W2 110.5
P_JOISTS = [5.375, 17.0, 28.875, 37.5, 46.5, 62.65, 78.8, 92.5, 104.5]   # beside the west web (W3/G4 28.5), F3/G1 46.5, G1/G2 78.8
Y_RIM = W_JOISTS[-1]               # last west joist runs on as the rim under F3
X_RIM_END = 46.5
X_NW_END = 38.5                    # the y 71 joist runs on under the NW fillet
SWT = unary_union([SW_TOP, box(X_WALL_W + WALL_GAP, 200.5, 28.4, 266.5)])
# closet: three 1x3 boxes on edge. The north and south boxes run the full depth from the wall openings to the
# east wall; a short box fills the east wall between them, its front rail under the inside edge of the helix track
CL_N, CL_S = (47.5, 65.0), (114.0, 131.5)          # north / south boxes (y), x 163 to the east wall
CL_BOX_X = [163.0, 181.0, 199.0, 217.0]           # their cross pieces (x), ends included, 18 in o.c.
X_CL_E = 204.0                                     # east box front edge, 13 in off the wall
CL_E_Y = [65.0, 77.25, 89.5, 101.75, 114.0]        # east box cross pieces (y), ends included; B2/B3 seam at 89.5
# B1 (the 0 in board from the helix to the south opening): on the helix at its post, a 1x3 joist on the wall stub,
# and a pair of 5/16 rods through its 10 in straight, halfway (as plywood_cut_plan.py)
X_B1_ROD, Y_B1, B1_ROD_OFF = 142.5, 121.45, 4.0

WOOD = Color(0.93, 0.85, 0.70)
WOOD_DK = Color(0.86, 0.74, 0.55)
NEW = Color(0.80, 0.35, 0.10)
PLYC = Color(0.96, 0.90, 0.76)
STEEL = Color(0.55, 0.57, 0.60)
CORK = Color(0.80, 0.62, 0.42)
ACCENT = Color(0.70, 0.12, 0.10)
DIMC = Color(0.10, 0.25, 0.55)
GREY = Color(0.45, 0.45, 0.45)
WALL = Color(0.82, 0.82, 0.82)
DECK = Color(0.97, 0.95, 0.90)
EXIST = Color(0.55, 0.55, 0.60)
CLOSETC = Color(0.20, 0.45, 0.30)


class View:
    def __init__(self, c, ox, oy, scale, xref=0.0, yref=0.0):
        """(xref, yref) in real inches lands on page point (ox, oy)."""
        self.c, self.ox, self.oy, self.k = c, ox, oy, 72.0 / scale
        self.xref, self.yref = xref, yref

    def p(self, x, y):
        return self.ox + (x - self.xref) * self.k, self.oy + (y - self.yref) * self.k

    def rect(self, x0, y0, x1, y1, fill=WOOD, stroke=black, lw=0.8, dash=None, xcut=False):
        c = self.c
        (a, b), (d, e) = self.p(min(x0, x1), min(y0, y1)), self.p(max(x0, x1), max(y0, y1))
        c.saveState()
        c.setLineWidth(lw)
        c.setStrokeColor(stroke)
        if dash:
            c.setDash(*dash)
        if fill is not None:
            c.setFillColor(fill)
        c.rect(a, b, d - a, e - b, stroke=1, fill=0 if fill is None else 1)
        if xcut:  # lumber cut in section (end grain)
            c.setLineWidth(0.4)
            c.line(a, b, d, e)
            c.line(a, e, d, b)
        c.restoreState()

    def poly(self, pts, fill=WOOD, lw=0.8, dash=None):
        c = self.c
        c.saveState()
        c.setLineWidth(lw)
        if dash:
            c.setDash(*dash)
        path = c.beginPath()
        path.moveTo(*self.p(*pts[0]))
        for q in pts[1:]:
            path.lineTo(*self.p(*q))
        path.close()
        if fill is not None:
            c.setFillColor(fill)
        c.drawPath(path, stroke=1, fill=0 if fill is None else 1)
        c.restoreState()

    def line(self, x0, y0, x1, y1, lw=0.6, color=black, dash=None):
        c = self.c
        c.saveState()
        c.setLineWidth(lw)
        c.setStrokeColor(color)
        if dash:
            c.setDash(*dash)
        c.line(*self.p(x0, y0), *self.p(x1, y1))
        c.restoreState()

    def text(self, x, y, s, size=7, color=black, anchor="l", bold=False, dx=0, dy=0):
        c = self.c
        c.saveState()
        c.setFillColor(color)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        a, b = self.p(x, y)
        a += dx
        b += dy
        if anchor == "c":
            c.drawCentredString(a, b, s)
        elif anchor == "r":
            c.drawRightString(a, b, s)
        else:
            c.drawString(a, b, s)
        c.restoreState()

    def leader(self, x, y, tx, ty, s, size=7, anchor="l", color=black):
        """Leader from point (x,y) to label at (tx,ty)."""
        self.line(x, y, tx, ty, lw=0.4, color=color)
        a, b = self.p(x, y)
        self.c.saveState()
        self.c.setFillColor(color)
        self.c.circle(a, b, 1.2, stroke=0, fill=1)
        self.c.restoreState()
        lines = s.split("\n")
        for i, ln in enumerate(lines):
            self.text(tx, ty, ln, size=size, anchor=anchor, color=color,
                      dx=(3 if anchor == "l" else -3), dy=-2 - i * (size + 1.5))

    def dim_v(self, x, y0, y1, label, side="r", size=7, color=DIMC):
        self.line(x, y0, x, y1, lw=0.5, color=color)
        for y in (y0, y1):
            self.line(x - 0.12 * 72 / self.k, y, x + 0.12 * 72 / self.k, y, lw=0.5, color=color)
        ym = (y0 + y1) / 2
        self.text(x, ym, label, size=size, color=color, anchor="l" if side == "r" else "r",
                  dx=4 if side == "r" else -4, dy=-2)

    def dim_h(self, y, x0, x1, label, size=7, color=DIMC, above=True):
        self.line(x0, y, x1, y, lw=0.5, color=color)
        for x in (x0, x1):
            self.line(x, y - 0.12 * 72 / self.k, x, y + 0.12 * 72 / self.k, lw=0.5, color=color)
        self.text((x0 + x1) / 2, y, label, size=size, color=color, anchor="c",
                  dy=3 if above else -9)

    def screw(self, x0, y0, x1, y1):
        self.line(x0, y0, x1, y1, lw=1.1, color=ACCENT)
        a, b = self.p(x0, y0)
        self.c.saveState()
        self.c.setFillColor(ACCENT)
        self.c.circle(a, b, 1.6, stroke=0, fill=1)
        self.c.restoreState()


def ply(v, x0, x1, y_top, thick, dash=None, fill=PLYC):
    v.rect(x0, y_top - thick, x1, y_top, fill=fill, dash=dash)
    if not dash:
        for f in (1 / 3, 2 / 3):  # veneer lines
            v.line(x0, y_top - thick * f, x1, y_top - thick * f, lw=0.25, color=GREY)


def track(v, xc, y_base, cork=True, dash=None):
    """HO track in section: cork, tie, two rails (rail gauge 0.65)."""
    y = y_base
    if cork:
        v.poly([(xc - 1.0, y), (xc + 1.0, y), (xc + 0.85, y + 0.236), (xc - 0.85, y + 0.236)],
               fill=CORK if not dash else None, lw=0.4, dash=dash)
        y += 0.236
    v.rect(xc - 0.53, y, xc + 0.53, y + 0.077, fill=Color(0.35, 0.25, 0.2) if not dash else None,
           lw=0.3, dash=dash)
    for r in (-0.325, 0.325):
        v.rect(xc + r - 0.03, y + 0.077, xc + r + 0.03, y + 0.160, fill=black if not dash else None,
               lw=0.3, dash=dash)


def header(c, title, sub, page, pages, level="main level"):
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(36, PH - 40, title)
    c.setFont("Helvetica", 8.5)
    c.setFillColor(GREY)
    c.drawString(36, PH - 54, sub)
    c.drawRightString(PW - 36, PH - 40, f"HART {level}  |  sheet {page} of {pages}")
    c.drawRightString(PW - 36, PH - 54, "Dimensions in inches. 0.00 = top of 3/4 ply subroadbed (0\" grade).")
    c.setStrokeColor(black)
    c.setLineWidth(0.8)
    c.line(36, PH - 60, PW - 36, PH - 60)


def footer_note(c, lines, y=40, x=36, size=7.5, lead=10, color=GREY):
    c.setFont("Helvetica", size)
    c.setFillColor(color)
    for i, s in enumerate(lines):
        c.drawString(x, y + (len(lines) - 1 - i) * lead, s)


def scale_label(v, x, y, s):
    v.text(x, y, s, size=8, bold=True)


def frac(v, den=8):
    """Inches to the nearest 1/den, e.g. 23-7/8."""
    n = round(v * den)
    whole, rem = divmod(n, den)
    if rem == 0:
        return f"{whole}"
    while rem % 2 == 0:
        rem, den = rem // 2, den // 2
    return f"{whole}-{rem}/{den}" if whole else f"{rem}/{den}"


# ---------------------------------------------------------------- framing members (room inches)
def front_edge_y(x):
    hit = LineString([(x, 40), (x, 90)]).intersection(NORTH)
    return hit.bounds[3]


def deck_span(geom, x=None, y=None):
    line = LineString([(x, 40), (x, 320)]) if x is not None else LineString([(0, y), (230, y)])
    hit = line.intersection(geom)
    return None if hit.is_empty else hit.bounds


def members():
    """Every new framing member as (kind, x0, y0, x1, y1, length, stock). Length is along the member."""
    m = []

    def add(kind, x0, y0, x1, y1, stock="1x2"):
        length = max(x1 - x0, y1 - y0)
        m.append((kind, x0, y0, x1, y1, length, stock))

    # front girders: both run onto the seats; the west web starts on the north flange and is cut where the NW joist
    # and the rim cross on its flange
    add("girder", NG_X[0], NG[0], NG_X[1], NG[1], "1x3")                           # north flange
    add("girder_web", NG_X[0], NG_WEB[0], NG_X[1], NG_WEB[1])                      # north web
    add("girder", WG[0], WG_Y[0], WG[1], WG_Y[1], "1x3")                           # west flange
    cuts = [NG_WEB[1], W_JOISTS[0] - 0.375, W_JOISTS[0] + 0.375, Y_RIM - 0.375, Y_RIM + 0.375, WG_Y[1]]
    for y0, y1 in zip(cuts[::2], cuts[1::2]):
        add("girder_web", WG_WEB[0], y0, WG_WEB[1], y1)                            # west web pieces
    for x in N_JOISTS:
        add("joist", x - 0.375, Y_WALL_N + WALL_GAP, x + 0.375, NG_WEB[0])
        y1 = Y_NW_STOP if x < X_NW_END + 0.5 else front_edge_y(x)
        add("lookout", x - 0.375, NG_WEB[1], x + 0.375, y1)
    for y in W_JOISTS:
        x1 = X_NW_END if y == W_JOISTS[0] else X_RIM_END if y == Y_RIM else WG_WEB[0]
        add("joist", X_WALL_W + WALL_GAP, y - 0.375, x1, y + 0.375)
    for x in P_JOISTS:
        y0, y1 = deck_span(SWT, x=x)[1], deck_span(SWT, x=x)[3]
        if x <= X_RIM_END:
            y0 = Y_RIM + 0.375
        add("pjoist", x - 0.375, y0, x + 0.375, y1)
    # seam blocking between joists
    add("block", WG[1], W_JOISTS[-2] + 0.375, WG[1] + 0.75, Y_RIM - 0.375)                   # F3 / W2 joint
    for xa, xb in ((P_JOISTS[0], P_JOISTS[1]), (P_JOISTS[1], P_JOISTS[2])):
        add("block", xa + 0.375, 206.5 - 0.375, xb - 0.375, 206.5 + 0.375)                    # W2 / W3 joint
    # closet: north and south boxes full depth, then the short east box between them
    for y0, y1 in (CL_N, CL_S):
        add("cl_ledger" if y0 == Y_WALL_N else "cl_rail", 163.0, y0, 217.0, y0 + 0.75, "1x3")
        add("cl_rail" if y0 == Y_WALL_N else "cl_ledger", 163.0, y1 - 0.75, 217.0, y1, "1x3")
        for i, x in enumerate(CL_BOX_X):
            x0 = x if i == 0 else x - 0.75 if i == len(CL_BOX_X) - 1 else x - 0.375
            add("cl_joist", x0, y0 + 0.75, x0 + 0.75, y1 - 0.75, "1x3")
    add("cl_ledger", 216.25, CL_N[1], 217.0, CL_S[0], "1x3")
    add("cl_rail", X_CL_E, CL_N[1], X_CL_E + 0.75, CL_S[0], "1x3")
    for i, y in enumerate(CL_E_Y):
        y0 = y if i == 0 else y - 0.75 if i == len(CL_E_Y) - 1 else y - 0.375
        add("cl_joist", X_CL_E + 0.75, y0, 216.25, y0 + 0.75, "1x3")
    # closet strip at the south end of the west wall: same 1x3 grid; the rail runs on to the peninsula girder
    add("cl_ledger", X_WALL_W, 301.75, 18.5, 302.5, "1x3")
    add("cl_rail", 17.75, PG_S[0], 18.5, 301.75, "1x3")
    for y in (267.0, 284.0):
        add("cl_joist", X_WALL_W + WALL_GAP, y - 0.375, 24.5 if y == 267.0 else 17.75, y + 0.375, "1x3")
    add("b1_joist", 157.75, Y_B1 - 7.0, 158.5, Y_B1 + 7.0, "1x3")
    return m


Y_NW_STOP = W_JOISTS[0] - 0.375


def riser_blocks():
    """(x0, y0, x1, y1) for each 1x3 riser block on a -3.25 girder, on the same side of every joist."""
    b = []
    for x in N_JOISTS:
        b.append((x + 0.375, Y_WALL_N + WALL_GAP, x + 1.125, Y_WALL_N + WALL_GAP + BLOCK_L))
    for y in W_JOISTS:
        b.append((X_WALL_W + WALL_GAP, y + 0.375, X_WALL_W + WALL_GAP + BLOCK_L, y + 1.125))
    for x in P_JOISTS:
        for g in (PG_N, PG_S):
            yc = (g[0] + g[1]) / 2
            b.append((x + 0.375, yc - BLOCK_L / 2, x + 1.125, yc + BLOCK_L / 2))
    return b


class PlanView:
    """Room inches (x east, y south) onto the page; y runs down the page."""

    def __init__(self, c, ox, oy, k, x0, y0):
        self.c, self.ox, self.oy, self.k, self.x0, self.y0 = c, ox, oy, k, x0, y0

    def p(self, x, y):
        return self.ox + (x - self.x0) * self.k, self.oy - (y - self.y0) * self.k

    def geom(self, g, fill=None, stroke=black, lw=0.5, dash=None):
        polys = g.geoms if hasattr(g, "geoms") else [g]
        c = self.c
        for poly in polys:
            if poly.is_empty or poly.geom_type != "Polygon":
                continue
            c.saveState()
            c.setLineWidth(lw)
            if stroke is not None:
                c.setStrokeColor(stroke)
            if dash:
                c.setDash(*dash)
            path = c.beginPath()
            for ring in [poly.exterior] + list(poly.interiors):
                pts = list(ring.coords)
                path.moveTo(*self.p(*pts[0]))
                for q in pts[1:]:
                    path.lineTo(*self.p(*q))
                path.close()
            if fill is not None:
                c.setFillColor(fill)
            c.drawPath(path, stroke=1 if stroke is not None else 0, fill=0 if fill is None else 1)
            c.restoreState()

    def rect(self, x0, y0, x1, y1, fill=None, stroke=black, lw=0.4, dash=None):
        self.geom(box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)), fill=fill, stroke=stroke, lw=lw, dash=dash)

    def text(self, x, y, s, size=6, color=black, anchor="l", bold=False, dx=0, dy=0):
        c = self.c
        c.saveState()
        c.setFillColor(color)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        a, b = self.p(x, y)
        {"c": c.drawCentredString, "r": c.drawRightString, "l": c.drawString}[anchor](a + dx, b + dy, s)
        c.restoreState()

    def dot(self, x, y, r=2.2, fill=STEEL):
        a, b = self.p(x, y)
        self.c.saveState()
        self.c.setFillColor(fill)
        self.c.circle(a, b, r, stroke=1, fill=1)
        self.c.restoreState()

    def tag(self, x, y, s, size=7):
        """Detail callout: letter in a circle."""
        a, b = self.p(x, y)
        c = self.c
        c.saveState()
        c.setFillColor(Color(1, 1, 1))
        c.setStrokeColor(ACCENT)
        c.setLineWidth(0.8)
        c.circle(a, b, 6.5, stroke=1, fill=1)
        c.setFillColor(ACCENT)
        c.setFont("Helvetica-Bold", size)
        c.drawCentredString(a, b - 2.5, s)
        c.restoreState()


STYLE = {"girder": (NEW, 0.5), "girder_web": (Color(0.55, 0.20, 0.05), 0.5), "lookout": (WOOD_DK, 0.3), "joist": (WOOD_DK, 0.3), "pjoist": (WOOD_DK, 0.3),
         "block": (NEW, 0.3), "cl_ledger": (CLOSETC, 0.3), "cl_rail": (CLOSETC, 0.3), "cl_joist": (CLOSETC, 0.3), "b1_joist": (NEW, 0.3)}


# ---------------------------------------------------------------- sheet 1
def sheet_framing_plan(c):
    header(c, "Framing plan - main level, deck removed",
           "Looking down. Orange = new front girders; grey = existing girders.", 1, PAGES)
    v = PlanView(c, ox=40, oy=PH - 74, k=1.86, x0=0.0, y0=43.0)
    v.geom(WALLS, fill=WALL, stroke=GREY, lw=0.4)
    deck = unary_union([NORTH, WEST, F_NW, F_SW, SWT, CLOSET, F_CL, CLOSET_DECK])
    v.geom(deck, fill=DECK, stroke=GREY, lw=0.4, dash=(2, 1.5))
    v.geom(PEN, fill=Color(0.90, 0.90, 0.90), stroke=GREY, lw=0.4)
    v.text(107, 136, "HELIX PENINSULA", size=6.5, color=GREY, anchor="c", bold=True)
    v.text(107, 142, "existing 2x4 structure", size=6, color=GREY, anchor="c")

    # existing L-girders (flanges)
    v.rect(X_WALL_W, Y_WALL_N, 158.5, Y_WALL_N + 1.5, fill=EXIST, stroke=None)
    v.rect(X_WALL_W, Y_WALL_N, X_WALL_W + 1.5, 266.5, fill=EXIST, stroke=None)
    for g in (PG_N, PG_S):
        v.rect(X_WALL_W + 1.5, g[0], PG_X1, g[1], fill=EXIST, stroke=None)
        v.rect(PG_X1, g[0], PG_X1 + 8, g[1], fill=None, stroke=EXIST, lw=0.5, dash=(1.5, 1.5))

    v.rect(140.3, Y_B1 - 5.0, 158.5, Y_B1 + 5.0, fill=DECK, stroke=GREY, lw=0.4, dash=(2, 1.5))
    mem = members()
    for kind, x0, y0, x1, y1, _, _ in mem:
        fill, lw = STYLE[kind]
        if fill is not None:
            v.rect(x0, y0, x1, y1, fill=fill, stroke=None if kind.startswith("girder") else black, lw=lw)
    for b in riser_blocks():
        v.rect(*b, fill=WOOD, stroke=black, lw=0.25)
    for x in N_RODS:
        v.dot(x, (NG[0] + NG_WEB[0]) / 2)
    for y in W_RODS:
        v.dot((WG[0] + WG_WEB[0]) / 2, y)
    for dy in (-B1_ROD_OFF, B1_ROD_OFF):
        v.dot(X_B1_ROD, Y_B1 + dy)

    # labels
    v.text(81, NG[1] + 3.5, f"NORTH FRONT GIRDER  {frac(NG_X[1] - NG_X[0])} wall to wall", size=6, color=NEW,
           anchor="c", bold=True)
    c.saveState()
    a, b = v.p(WG[1] + 3.0, 150)
    c.translate(a, b)
    c.rotate(-90)
    c.setFillColor(NEW)
    c.setFont("Helvetica-Bold", 6)
    c.drawCentredString(0, 0, f"WEST FRONT GIRDER  {frac(WG_Y[1] - WG_Y[0])}")
    c.restoreState()
    v.text(64, PG_N[0] - 2.0, "existing peninsula girder", size=5.5, color=GREY, anchor="c")
    v.text(64, PG_S[1] + 4.5, "existing peninsula girder", size=5.5, color=GREY, anchor="c")
    v.text(PG_X1 + 9, PG_N[1] + 2, "end: verify", size=5, color=GREY)
    v.text(149.4, Y_B1 + 9.0, "B1, 10 in", size=5.5, color=GREY, anchor="c")
    v.text(183, 90, "CLOSET 1x3 BOXES", size=6, color=CLOSETC, anchor="c", bold=True)
    v.text(N_RODS[0], NG[0] - 3.0, "rod", size=5.5, color=GREY, anchor="c")
    v.text(N_RODS[1], NG[0] - 3.0, "rod", size=5.5, color=GREY, anchor="c")
    for y in W_RODS:
        v.text(WG[0] - 1.5, y + 1.2, "rod", size=5.5, color=GREY, anchor="r")
    v.tag(X_WALL_W + 4, NG[1] + 4, "E")
    v.tag(WG[1] + 4, PG_N[0] - 7, "E")
    v.tag(WG[1] + 4.5, NG[1] + 5, "F")
    v.tag(158.5 - 4, NG[1] + 5, "G")
    v.tag(40, 192, "H")

    # legend + notes (page coordinates)
    lx, ly = 498, PH - 86
    rows = [(NEW, "New front girder: 1x2 web (dark) on a 1x3 flange"), (WOOD_DK, "New 1x2 joist or lookout"),
            (WOOD, "1x3 riser block on a -3.25 girder"), (NEW, "1x2 blocking under a deck seam"),
            (CLOSETC, "Closet 1x3 boxes / grid (wall side, rail, cross piece)"), (EXIST, "Existing L-girder flange"),
            (STEEL, "5/16 rod, 2 per run, over a staging leg")]
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(black)
    c.drawString(lx, ly, "LEGEND")
    for i, (col, s) in enumerate(rows):
        y = ly - 14 - i * 12
        c.setFillColor(col)
        if col is STEEL:
            c.circle(lx + 5, y + 3, 2.4, stroke=1, fill=1)
        else:
            c.rect(lx, y, 10, 6, stroke=1, fill=1)
        c.setFillColor(black)
        c.setFont("Helvetica", 7.5)
        c.drawString(lx + 16, y, s)
    notes = [
        "Joists run north-south on the north shelf, east-west on the west shelf and north-south on the SW "
        "peninsula, about 16 in o.c. Every deck seam lands on a joist or on blocking.",
        "North girder set back to the wall-stub end, web centred on its flange: joists butt its back, 1x2 lookouts "
        "in line carry the deck to the front edge (up to 7 in). West girder web on the deck edge.",
        f"Rods: nominal at the third points (north x {N_RODS[0]:.0f}, {N_RODS[1]:.0f}; west y {W_RODS[0]:.0f}, "
        f"{W_RODS[1]:.0f}). Move each one over a staging leg; keep every gap under 60 in.",
        "E: front girder seats on an existing girder (sheet 4). F: west girder into the north girder. "
        "G: north girder at the wall stub. H: rim and blocking under F3.",
        "Peninsula girders and joist ends at the tip: drawn to x 100; check the as-built girders before cutting "
        "the last two joists.",
        "Closet past the helix: three 1x3 boxes on edge. North and south run full depth to the east wall; a short "
        "13 in box fills the east wall between them, its front rail under the inside edge of the helix track and a "
        "cross piece under the B2/B3 seam (y 89.5). Cross pieces 18 in o.c. in the side boxes, 12-1/4 in the east box.",
        "B1 (0 in board, helix to the south opening): on the helix at its post and on a 1x3 joist on the wall stub. "
        "Past the curve it is 10 in wide to the wall: two 5/16 rods 4 in off the centre line, halfway; a temporary post "
        "under it until then.",
    ]
    y = ly - 14 - len(rows) * 12 - 16
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(lx, y, "NOTES")
    c.setFont("Helvetica", 7.2)
    y -= 12
    for s in notes:
        for ln in simpleSplit(s, "Helvetica", 7.2, 256):
            c.drawString(lx, y, ln)
            y -= 9
        y -= 4

    y -= 6
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(lx, y, "JOIST STATIONS (centres, room inches)")
    c.setFont("Helvetica", 7.2)
    for lbl, xs in (("North, x", N_JOISTS), ("West, y", W_JOISTS), ("Peninsula, x", P_JOISTS)):
        y -= 11
        for ln in simpleSplit(f"{lbl}: " + ", ".join(frac(s) for s in xs), "Helvetica", 7.2, 256):
            c.drawString(lx, y, ln)
            y -= 9
        y += 9
    footer_note(c, ["Room inches: x east from the west wall corner, y south from the north wall line (same as the "
                    "cut plan). Plan about 1:39 - work from the stations, not the drawing."], y=22, size=7)


# ---------------------------------------------------------------- sheet 2
def sheet_section(c):
    header(c, "Typical shelf section - west wall (north wall the same, girder set back)",
           "Section through a joist, perpendicular to the wall.", 2, PAGES)
    v = View(c, ox=70, oy=528, scale=4, xref=-2.0, yref=5.6)

    v.rect(-2.0, STAGING_TOP - 1.2, 0, 5.6, fill=WALL, lw=0.6)
    v.text(-1.0, -8, "WALL", size=7, anchor="c", color=GREY)

    # +4.25 ledge (reference)
    ph = (2, 2)
    v.rect(JOIST_X0, 0, JOIST_X0 + 1.5, 3.75, fill=None, dash=ph, lw=0.6)
    ply(v, 0.25, 8.25, 3.75 + 0.47, 0.47, dash=ph)
    track(v, 3.5, 4.22, dash=ph)
    track(v, 6.0, 4.22, dash=ph)
    v.leader(8.25, 4.0, 10.0, 4.6, "+4.25 ledge: 1/2 ply on risers (reference only)", color=GREY)

    ply(v, 0.25, EDGE, 0, PLY)
    track(v, 13.5, 0)
    track(v, 16.0, 0)

    v.rect(JOIST_X0, J_BOT, FG_WEB_IN, J_TOP, fill=WOOD)
    v.poly(block_pts(), fill=WOOD_DK)
    v.rect(JOIST_X0, J_BOT, FG_WEB_IN, J_TOP, fill=None)

    v.rect(GIRDER_X0, FLANGE_BOT, FLANGE_X1, FLANGE_TOP, xcut=True)
    v.rect(GIRDER_X0, WEB_BOT, WEB_X1, FLANGE_BOT, xcut=True)

    # new front girder (cut)
    v.rect(FG_WEB_IN, FG_FL_TOP, FG_OUT, FG_TOP, xcut=True)
    v.rect(FG_FL_IN, FG_BOT, FG_OUT, FG_FL_TOP, xcut=True)
    # fascia, later
    v.rect(EDGE, FG_BOT - 0.25, EDGE + 0.25, 0.0, fill=None, dash=(2, 2), lw=0.5)

    # rod (beyond the cut, between joists)
    v.line(ROD_X, FG_FL_TOP + 0.35, ROD_X, STAGING_TOP - PLY - 0.4, lw=1.4, color=STEEL, dash=(4, 2))
    for y in (FG_FL_TOP, FG_BOT - 0.1, STAGING_TOP, STAGING_TOP - PLY - 0.1):
        v.rect(ROD_X - 0.4, y, ROD_X + 0.4, y + 0.1, fill=STEEL, lw=0.3)

    ply(v, 0.0, EDGE + 0.5, STAGING_TOP, PLY)
    for xc in (5.0, 9.5, 14.0, 18.5):
        track(v, xc, STAGING_TOP)
    v.text(12, STAGING_TOP - PLY - 0.8, "STAGING LEVEL deck (existing)", size=7, anchor="c", color=GREY)

    v.dim_v(13.0, J_BOT, STAGING_RAIL, f"{J_BOT - STAGING_RAIL:.2f} clear")
    v.dim_v(EDGE + 0.9, FG_BOT, STAGING_RAIL, f"{FG_BOT - STAGING_RAIL:.2f} clear")
    v.dim_v(GIRDER_X0 + 1.2, WEB_BOT, STAGING_RAIL, f"{WEB_BOT - STAGING_RAIL:.2f} clear")
    v.dim_h(-12.6, 0, EDGE, f"{DEPTH:.0f} shelf depth (west wall; north wall 23-1/2 tapering to 17-1/2)")

    v.leader(BLOCK_X0 + BLOCK_L - 0.3, BLOCK_BOT + 0.4, 8.0, -5.0,
             "1x3 riser block, 5\" long, square at the wall,\n45 deg miter at the front, glued + screwed\nto the joist side (sheet 5)")
    v.leader(GIRDER_X0 + 0.4, -6.2, 5.0, -6.9, "Existing L-girder: 1x4 web + 1x2 flange,\n"
             "flange top -3.25 (as installed)")
    v.leader(17.5, (J_TOP + J_BOT) / 2, 10.0, 2.3, "1x2 joist on edge, about 16\" o.c., butts\nthe front web, sits on the flange")
    v.leader(FG_FL_IN + 0.3, FG_BOT + 0.3, 26.3, -3.0,
             "New front girder: 1x2 web on edge\non the face, flush with the joists;\n1x3 flange flat under it (sheet 3)")
    v.leader(EDGE + 0.2, -1.0, 26.3, 1.2, "fascia on the front web,\nlater")
    v.leader(ROD_X, -10.0, 26.3, -10.0, "5/16-18 threaded rod, 2 per run,\nover a staging leg, through the\n"
             "flange between joists (sheet 3)")
    v.leader(20.5, -PLY / 2, 18.5, 3.4, "3/4 ply subroadbed (0.72 measured),\nglued + screwed to joists")

    ex, ey = 560, 170
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(black)
    c.drawString(ex, ey, "ELEVATIONS")
    rows = [(0.0, "top of 3/4 ply subroadbed"), (J_TOP, "joist top = front web top"),
            (J_BOT, "joist bottom = front flange top"),
            (FG_BOT, "front flange bottom"), (BLOCK_BOT, "riser block bottom"), (FLANGE_TOP, "back girder flange top"),
            (WEB_BOT, "back girder web bottom"), (STAGING_RAIL, "staging railhead"),
            (STAGING_TOP, "staging deck top")]
    c.setFont("Helvetica", 7.5)
    for i, (y, s) in enumerate(rows):
        c.drawRightString(ex + 32, ey - 12 - i * 10, f"{y:.2f}")
        c.drawString(ex + 40, ey - 12 - i * 10, s)

    footer_note(c, [
        "Block bottom lands 0.03 above the back flange (3.25 - 2.50 - 0.72); the deck top finishes 1/32 low - within "
        "tolerance, or shim the flange. The joists butt the front web and sit on its flange - no blocks at the front.",
        "North wall: the girder is set back to the wall-stub end with its web centred; 1x2 lookouts in line with the "
        "joists carry the deck to the front edge (sheet 3, N). Track = 0.236 cork + 0.160 Atlas code 83.",
        "Scale 1:4 on Letter landscape. Lumber cut in section shows an X; the joist and riser block are in side view.",
    ], y=22, size=7)


def block_pts():
    # square at the wall end (full bearing on the flange), one 45 deg miter on the visible front end
    return [(BLOCK_X0, BLOCK_TOP), (BLOCK_X0 + BLOCK_L, BLOCK_TOP), (BLOCK_X0 + BLOCK_L, BLOCK_BOT + CLIP),
            (BLOCK_X0 + BLOCK_L - CLIP, BLOCK_BOT), (BLOCK_X0, BLOCK_BOT)]


# ---------------------------------------------------------------- sheet 3
def sheet_front(c):
    header(c, "Details - front girder: 1x2 web on the face, 1x3 flange under it",
           "C: west, at a joist.  D: between joists, at a rod.  N: north girder, joist and lookout.  "
           "All cut across the girder.", 3, PAGES)
    mid = (J_TOP + J_BOT) / 2
    jx = (FG_FL_IN + FG_WEB_IN) / 2
    wx = (FG_WEB_IN + FG_OUT) / 2

    x0 = FG_FL_IN - 2.5
    f = View(c, ox=40, oy=470, scale=2, xref=x0, yref=0.9)
    f.text(x0, 0.9, "C   WEST, AT A JOIST   1:2", size=9, bold=True, dy=4)
    ply(f, x0, EDGE, 0, PLY)
    f.rect(x0, J_BOT, FG_WEB_IN, J_TOP, fill=WOOD)
    f.rect(FG_WEB_IN, FG_FL_TOP, FG_OUT, FG_TOP, xcut=True)
    f.rect(FG_FL_IN, FG_BOT, FG_OUT, FG_FL_TOP, xcut=True)
    f.screw(jx, FG_BOT - 0.15, jx, FG_FL_TOP + 0.6)
    f.screw(wx, FG_BOT - 0.15, wx, FG_FL_TOP + 0.6)
    f.dim_v(FG_OUT + 0.4, FG_TOP, FG_FL_TOP, "1-1/2")
    f.dim_v(FG_OUT + 0.4, FG_FL_TOP, FG_BOT, "3/4")
    f.dim_h(FG_BOT - 0.4, FG_FL_IN, FG_OUT, "2-1/2", above=False)
    f.text(x0 + 0.2, mid, "1x2 joist", size=7, dy=-2)
    f.leader(jx, FG_BOT - 0.1, x0, -4.4, "#6 x 1-1/4 up through the flange\ninto each joist, pilot", color=ACCENT)
    f.leader(wx, FG_BOT - 0.1, x0, -5.4, "girder: glue + #6 x 1-1/4 up through\nthe flange into the web every 8\"",
             color=ACCENT)

    x1 = FG_FL_IN - 1.0
    g = View(c, ox=265, oy=470, scale=2, xref=x1, yref=0.9)
    g.text(x1, 0.9, "D   BETWEEN JOISTS, AT A ROD   1:2", size=9, bold=True, dy=4)
    ply(g, x1, EDGE, 0, PLY)
    g.rect(FG_WEB_IN, FG_FL_TOP, FG_OUT, FG_TOP, xcut=True)
    g.rect(FG_FL_IN, FG_BOT, FG_OUT, FG_FL_TOP, xcut=True)
    g.line(ROD_X, FG_FL_TOP + 0.6, ROD_X, FG_BOT - 1.4, lw=3, color=STEEL)
    g.line(ROD_X, FG_BOT - 1.4, ROD_X, FG_BOT - 1.9, lw=3, color=STEEL, dash=(2, 2))
    for y in (FG_FL_TOP, FG_BOT - 0.1):
        g.rect(ROD_X - 0.55, y, ROD_X + 0.55, y + 0.1, fill=STEEL, lw=0.3)
    g.rect(ROD_X - 0.28, FG_FL_TOP + 0.1, ROD_X + 0.28, FG_FL_TOP + 0.38, fill=STEEL, lw=0.3)
    g.rect(ROD_X - 0.28, FG_BOT - 0.38, ROD_X + 0.28, FG_BOT - 0.1, fill=STEEL, lw=0.3)
    g.leader(ROD_X - 0.3, FG_FL_TOP + 0.25, x1, -5.6,
             "5/16-18 rod, 3/8 hole through the\nflange's joist bearing; nut + fender\nwasher on top and underneath")
    g.text(ROD_X + 0.3, FG_BOT - 1.7, "to the staging deck,", size=7, color=GREY)
    g.text(ROD_X + 0.3, FG_BOT - 2.05, "over a leg", size=7, color=GREY)

    # N: north girder, web centred on its flange (local inches: web back face at 0)
    hb = (2.5 - 0.75) / 2
    n = View(c, ox=455, oy=470, scale=2, xref=-2.0, yref=0.9)
    n.text(-2.0, 0.9, "N   NORTH, JOIST AND LOOKOUT   1:2", size=9, bold=True, dy=4)
    ply(n, -2.0, 6.75, 0, PLY)
    n.rect(-2.0, J_BOT, 0, J_TOP, fill=WOOD)
    n.rect(0.75, J_BOT, 6.75, J_TOP, fill=WOOD_DK)
    n.rect(0, FG_FL_TOP, 0.75, FG_TOP, xcut=True)
    n.rect(-hb, FG_BOT, 0.75 + hb, FG_FL_TOP, xcut=True)
    for x in (-hb / 2, 0.75 + hb / 2):
        n.screw(x, FG_BOT - 0.15, x, FG_FL_TOP + 0.6)
    n.dim_h(FG_BOT - 0.4, -hb, 0.75 + hb, "2-1/2", above=False)
    n.dim_h(0.45, 0.75, 6.75, "lookout, up to 7")
    n.text(-1.9, mid, "joist", size=7, dy=-2)
    n.text(3.6, mid, "1x2 lookout", size=7, anchor="c", dy=-2)
    n.leader(0.75 + hb / 2, FG_BOT - 0.1, -2.0, -4.4, "#6 x 1-1/4 up through the flange into\n"
             "the joist and the lookout, pilot", color=ACCENT)
    n.leader(0.4, -0.3, -2.0, -5.4, "web centred, 7/8 of bearing each side;\nthe ply runs over the web and ties\n"
             "the lookout to the joist behind it")

    footer_note(c, [
        "Build each girder on the bench: lay the 1x3 flange flat, glue the 1x2 web on edge on top - on the outer edge "
        "for the west girder, centred for the north - and screw up through the flange every 8\". One 16 ft piece of "
        "each per run.",
        "The web top is the joist top (-0.72), so the ply lies flush across both. Joists butt the web and sit on the "
        "flange. Lookouts on the north run sit in line with each joist. Drill the rod holes between joists, over a "
        "staging leg, two per run.",
    ], y=40)

# ---------------------------------------------------------------- sheet 4
def sheet_junctions(c):
    header(c, "Details - girder junctions",
           "E: seat on an existing girder.  F: west girder into the north girder.  G: wall stub.  H: under F3.",
           4, PAGES)

    def notes(v, x, y, lines, step, size=7):
        for i, s in enumerate(lines):
            v.text(x, y, s, size=size, color=ACCENT if i == 0 else black, dy=-i * (size + 2.5))

    # E: side view along the carried girder, the supporting girder cut (top left)
    e = View(c, ox=50, oy=505, scale=3, xref=-3.0, yref=0.6)
    e.text(-3.0, 0.6, "E   SEAT ON AN EXISTING GIRDER   1:3", size=9, bold=True, dy=4)
    sx0, sx1 = 0.0, 1.5        # supporting flange (cut), its web under the near half
    e.rect(sx0, FLANGE_BOT, sx1, FLANGE_TOP, xcut=True)
    e.rect(sx0, WEB_BOT, sx0 + 0.75, FLANGE_BOT, xcut=True)
    e.rect(sx0, FLANGE_TOP, sx1, FLANGE_TOP + SHIM, fill=Color(0.75, 0.70, 0.62))
    e.rect(sx0 + 0.125, FG_FL_TOP, 9.0, FG_TOP, fill=WOOD)         # carried web
    e.rect(sx0 + 0.125, FG_BOT, 9.0, FG_FL_TOP, fill=WOOD)         # carried flange, both run onto the seat
    e.screw(0.75, FG_TOP, 0.75, FLANGE_TOP - 0.6)
    e.dim_h(FG_TOP + 0.4, sx0 + 0.125, sx1, "1-3/8 seat")
    e.text(5.0, (FG_TOP + FG_FL_TOP) / 2, "front girder web", size=6.5, anchor="c", dy=-2)
    e.text(5.0, (FG_FL_TOP + FG_BOT) / 2, "1x3 flange", size=6.5, anchor="c", dy=-2)
    e.leader(sx1 + 0.3, FLANGE_TOP + SHIM / 2, 3.5, -4.7, "1/4 hardboard shim, glued: the -2.97 flange\n"
             "bottom sits 0.28 above the -3.25 flange")
    e.leader(0.75, FLANGE_TOP - 0.4, 3.5, -5.8, "glue + 2x #8 x 3 down through the web,\nflange and shim, pilot",
             color=ACCENT)
    e.text(-2.9, -5.0, "existing girder", size=6.5, color=GREY)
    e.text(-2.9, -5.5, "flange top -3.25", size=6.5, color=GREY)
    e.text(-3.0, -8.4, "At the west wall: the north girder on the west wall girder, end 1/8 off the wall.",
           size=6.5, color=GREY)
    e.text(-3.0, -8.85, "At the peninsula: the west girder across the peninsula's north girder flange.", size=6.5,
           color=GREY)

    # F: NW corner, plan from below (top right)
    f = PlanView(c, ox=450, oy=525, k=8.5, x0=WG[0] - 7.0, y0=NG[0] - 2.0)
    f.text(WG[0] - 7.0, NG[0] - 2.0, "F   WEST GIRDER INTO THE NORTH GIRDER, FROM BELOW   1:8", size=9, bold=True,
           dy=4)
    f.rect(WG[0] - 7.0, NG[0], WG[1] + 9.0, NG[1], fill=WOOD, lw=0.5)                 # north flange
    f.rect(WG[0] - 7.0, NG_WEB[0], WG[1] + 9.0, NG_WEB[1], fill=None, lw=0.4, dash=(2, 2))   # north web, above
    f.rect(WG[0], NG[1], WG[1], NG[1] + 10.0, fill=WOOD, lw=0.5)                      # west flange
    f.rect(WG_WEB[0], NG_WEB[1], WG_WEB[1], NG[1] + 10.0, fill=None, lw=0.4, dash=(2, 2))   # west web, above
    tri = Polygon([(WG[1] - 7.5, NG[0]), (WG[1], NG[0]), (WG[1], NG[0] + 7.5)])
    f.geom(tri, fill=Color(0.95, 0.88, 0.70, alpha=0.75), stroke=ACCENT, lw=0.7, dash=(3, 2))
    f.text(WG[1] - 1.8, NG[1] + 0.9, "gusset", size=7, color=ACCENT, anchor="r")
    f.text(WG[1] + 9.0, NG[0] - 0.7, "north girder, web centred", size=6.5, color=GREY, anchor="r")
    f.text(WG[1] + 0.8, NG[1] + 7.4, "west girder, web on", size=6.5, color=GREY)
    f.text(WG[1] + 0.8, NG[1] + 8.6, "the x 28.5 face", size=6.5, color=GREY)
    notes(f, WG[0] - 7.0, NG[1] + 12.5, [
        "1/2 ply gusset, 7-1/2 x 7-1/2 triangle, under both flanges: glue + 3x",
        "#6 x 1-1/4 up into each flange, pilot. The west flange butts the north",
        "flange's front edge; the west web runs on over the north flange to the",
        "north web: glue, 2x #6 x 2 through the north web into its end. Webs dashed."], 1)

    # G: north girder at the wall stub, plan (bottom left)
    g = PlanView(c, ox=60, oy=245, k=9.0, x0=148.0, y0=58.0)
    g.text(148.0, 58.0, "G   NORTH GIRDER AT THE WALL STUB, PLAN   1:8", size=9, bold=True, dy=4)
    g.rect(158.5, 58.0, 163.0, 65.0, fill=WALL, stroke=GREY)
    g.rect(158.5, 63.5, 163.0, 65.0, fill=None, stroke=GREY, dash=(2, 2))
    g.text(160.75, 61.0, "stub", size=6.5, color=GREY, anchor="c")
    g.rect(148.0, NG[0], 158.375, NG[1], fill=WOOD, lw=0.5)
    g.rect(148.0, NG_WEB[0], 158.375, NG_WEB[1], fill=WOOD_DK, lw=0.5)
    g.rect(157.75, NG[1] - 2.5, 158.5, NG[1], fill=Color(0.95, 0.88, 0.70), stroke=ACCENT, lw=0.7)
    g.text(148.2, NG[0] - 0.6, "north girder (web centred on the flange)", size=6.5, color=GREY)
    g.text(163.4, 64.0, "end stud", size=6.5, color=GREY)
    g.text(157.5, NG[1] + 1.4, "seat block", size=6.5, color=ACCENT, anchor="r")
    notes(g, 148.0, 68.5, [
        "Seat block: 1x3 x 4 long, flat on the wall at the end stud, top at -2.97 under",
        "the flange end. 2x #8 x 2-1/2 through the block into the end stud; #8 x 3 down",
        "through the web and flange into the block. Girder end 1/8 off the wall. If",
        "there's no stud at the end of the stub, add blocking in the wall first."], 1)

    # H: F3 rim and blocking, plan (bottom right)
    h = PlanView(c, ox=450, oy=262, k=5.0, x0=4.0, y0=178.0)
    h.text(4.0, 178.0, "H   RIM AND BLOCKING UNDER F3, PLAN   1:14", size=9, bold=True, dy=4)
    h.geom(unary_union([WEST, F_SW, SWT]).intersection(box(4.0, 178.0, 50.0, 214.0)), fill=DECK, stroke=GREY,
           lw=0.4, dash=(2, 1.5))
    h.geom(F_SW, fill=None, stroke=ACCENT, lw=0.6, dash=(3, 2))
    h.text(41.0, 194.0, "F3", size=8, color=ACCENT, bold=True, anchor="c")
    h.rect(X_WALL_W, 178.0, X_WALL_W + 1.5, 214.0, fill=EXIST, stroke=None)
    h.rect(WG[0], 178.0, WG[1], 214.0, fill=NEW, stroke=None)
    for kind, x0, y0, x1, y1, _, _ in members():
        if kind in ("joist", "pjoist", "block", "girder_web") and x0 < 50 and y1 > 178 and y0 < 214:
            fill, lw = STYLE[kind]
            h.rect(max(x0, 4.0), max(y0, 178.0), min(x1, 50.0), min(y1, 214.0), fill=fill, lw=lw)
    h.text(30.0, Y_RIM - 1.0, "rim: last west joist, on to x 46-1/2", size=6.5)
    h.text(30.4, 191.5, "blocking", size=6.5, color=NEW)
    h.text(6.0, 205.3, "blocking (W2/W3 seam)", size=6.5, color=NEW)
    h.text(30.0, 213.0, "peninsula joists", size=6.5, color=GREY)
    notes(h, 4.0, 217.5, [
        "The rim crosses the west girder on its flange; the web is cut either side,",
        "2x #6 x 2 through the rim into each web end. Peninsula joists butt the rim:",
        "2x #6 x 2 each. The NW joist (y 71) crosses the same way. Blocking: 1x2 on",
        "edge between joists, ends screwed 2x #6 x 2."], 1)

# ---------------------------------------------------------------- sheet 5
def sheet_details(c):
    header(c, "Details - riser block at a -3.25 girder (back wall and peninsula)",
           "A: side view along the joist.  B: looking along the joist (joist and block cut, girder in elevation).",
           5, PAGES)
    mid = (J_TOP + J_BOT) / 2

    a = View(c, ox=60, oy=500, scale=2, xref=-0.5, yref=1.4)
    a.text(-0.5, 1.4, "A   SIDE VIEW ALONG THE JOIST   1:2", size=9, bold=True, dy=4)
    a.rect(-0.5, WEB_BOT - 0.3, 0, 0.6, fill=WALL, lw=0.5)
    ply(a, JOIST_X0, 8.5, 0, PLY)
    a.poly(block_pts(), fill=WOOD_DK)
    a.rect(JOIST_X0, J_BOT, 8.5, J_TOP, fill=None)
    a.text(8.3, mid, "1x2 joist", size=7, anchor="r", dy=-2)
    a.rect(GIRDER_X0, FLANGE_BOT, FLANGE_X1, FLANGE_TOP, xcut=True)
    a.rect(GIRDER_X0, WEB_BOT, WEB_X1, FLANGE_BOT, xcut=True)
    for x in (BLOCK_X0 + 0.9, BLOCK_X0 + 3.0):
        a.screw(x, mid, x, mid)
    fx = (GIRDER_X0 + FLANGE_X1) / 2
    a.screw(fx, FLANGE_BOT, fx, FLANGE_BOT + 1.5)
    a.dim_h(0.45, BLOCK_X0, BLOCK_X0 + BLOCK_L, "5")
    a.dim_v(BLOCK_X0 + BLOCK_L + 1.3, BLOCK_TOP, BLOCK_BOT, "2-1/2")
    a.text(BLOCK_X0 + BLOCK_L - CLIP / 2, BLOCK_BOT + CLIP / 2, "45 deg", size=7, color=ACCENT, dx=8, dy=-4)
    a.text(-0.25, -5.5, "WALL", size=6.5, anchor="c", color=GREY)
    a.leader(fx, FLANGE_BOT - 0.05, 5.4, -5.0, "#6 x 1-1/2 up through the\nflange into the block, pilot",
             color=ACCENT)
    a.leader(BLOCK_X0 + 3.0, mid, 6.4, -3.3, "glue + 2x #6 x 1-1/4 through\nthe block into the joist",
             color=ACCENT)
    a.leader(GIRDER_X0 + 0.4, -6.5, 5.4, -6.6, "existing L-girder\n1x4 web, 1x2 flange")

    b = View(c, ox=470, oy=500, scale=2, xref=-2.5, yref=1.4)
    b.text(-2.5, 1.4, "B   LOOKING ALONG THE JOIST   1:2", size=9, bold=True, dy=4)
    ply(b, -2.5, 2.5, 0, PLY)
    b.rect(-0.75, J_BOT, 0, J_TOP, xcut=True)
    b.rect(0, BLOCK_BOT, 0.75, BLOCK_TOP, fill=WOOD_DK, xcut=True)
    b.rect(-2.5, FLANGE_BOT, 2.5, FLANGE_TOP, fill=WOOD)
    b.rect(-2.5, WEB_BOT, 2.5, FLANGE_BOT, fill=WOOD)
    b.text(2.4, (FLANGE_TOP + FLANGE_BOT) / 2, "flange", size=6.5, anchor="r", dy=-2)
    b.text(2.4, (FLANGE_BOT + WEB_BOT) / 2, "web", size=6.5, anchor="r", dy=-2)
    b.screw(0.375, FLANGE_BOT, 0.375, FLANGE_BOT + 1.5)
    b.screw(1.1, mid, -0.45, mid)
    b.dim_v(-1.3, J_TOP, J_BOT, "1-1/2", side="l")
    b.dim_v(1.5, BLOCK_TOP, BLOCK_BOT, "2-1/2")
    b.leader(-0.4, J_BOT + 0.25, -2.5, -2.6, "1x2 joist", anchor="r")
    b.leader(0.6, BLOCK_BOT + 0.25, 2.7, -2.9, "1x3 block,\nface-glued")

    footer_note(c, [
        "Riser block: cut from 1x3, grain running with the joist. Top flush with the joist top; the bottom sits on "
        "the flange. The wall end stays square; one full-height 45 deg miter on the front end leaves 2-1/2 of bottom,",
        "so the block still bears on the whole 1-1/2 flange. Joist and block ends sit 1/8 off the wall. On the "
        "peninsula girders the block is centred on the flange, miter toward the aisle. Same side on every joist. "
        "Pattern on sheet 6.",
    ], y=30)


# ---------------------------------------------------------------- sheet 6
def sheet_plan(c):
    header(c, "Plan - typical 8 ft bay, west wall, deck removed  +  riser block pattern",
           "Looking down. Joists about 16\" o.c.: riser blocks at the wall, butted to the front web.", 6, PAGES)
    v = View(c, ox=50, oy=372, scale=12, xref=-2.0, yref=-2.0)
    L = 96.0
    v.rect(-2, -2, L + 2, 0, fill=WALL, lw=0.5)
    v.text(L / 2, -1.6, "WALL", size=7, anchor="c", color=GREY, dy=2)
    v.rect(0, GIRDER_X0, L, FLANGE_X1, fill=WOOD, lw=0.6)
    v.text(L + 0.6, (GIRDER_X0 + FLANGE_X1) / 2, "existing girder flange", size=6.5, dy=-2)
    v.rect(0, FG_FL_IN, L, FG_OUT, fill=WOOD, lw=0.6)
    v.rect(0, FG_WEB_IN, L, FG_OUT, fill=WOOD_DK, lw=0.6)
    v.text(L + 0.6, FG_FL_IN + 0.6, "1x3 flange under the joist", size=6.5, dy=-2)
    v.text(L + 0.6, FG_FL_IN - 0.6, "ends; 1x2 web on the face", size=6.5, dy=-2)
    xs = [0.375 + 16 * i for i in range(7)]
    xs[-1] = L - 0.375
    for x in xs:
        v.rect(x - 0.375, JOIST_X0, x + 0.375, FG_WEB_IN, fill=WOOD, lw=0.6)
        v.rect(x + 0.375, BLOCK_X0, x + 1.125, BLOCK_X0 + BLOCK_L, fill=WOOD_DK, lw=0.5)
    a, b = v.p(40.375, ROD_X)
    c.setFillColor(STEEL)
    c.circle(a, b, 3, stroke=1, fill=1)
    v.text(41.5, FG_FL_IN - 0.8, "rod, only where a staging leg is", size=6.5, dy=-2)
    v.dim_h(-4.0, xs[0], xs[1], "16 o.c.", above=False)
    v.dim_v(-3.5, 0, EDGE, "24", side="l")
    v.text(xs[1] + 1.4, BLOCK_X0 + BLOCK_L + 0.4, "riser block", size=6.5, dy=-2)
    v.text(xs[2] + 1.0, 14, "1x2 joist", size=6.5)

    p = View(c, ox=80, oy=100, scale=1)
    p.text(0, 3.2, "RISER BLOCK - FULL SIZE PATTERN (1:1)", size=9, bold=True)
    p.poly([(0, 2.5), (5, 2.5), (2.5, 0), (0, 0)], fill=WOOD_DK)
    p.line(0, 1.0, 3.5, 1.0, lw=0.4, color=GREY, dash=(3, 2))
    p.text(1.75, 1.05, "joist bottom line", size=6.5, color=GREY, anchor="c", dy=2)
    p.dim_h(2.8, 0, 5, "5")
    p.dim_h(-0.3, 0, 2.5, "2-1/2", above=False)
    p.text(0, -0.75, "square end goes to the wall", size=6.5, color=GREY)
    p.dim_v(-0.3, 0, 2.5, "2-1/2", side="l")
    p.text(1.9, 1.75, "grain  ->", size=7, anchor="c", color=GREY)
    p.text(3.9, 1.1, "45 deg", size=7, color=ACCENT, dy=-2)

    tx = 500
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(tx, 280, "PER 8 FT BAY (24\" deep, west wall)")
    rows = [
        ("1x2 joists", f"7 @ {frac(FG_WEB_IN - JOIST_X0)}", "wall gap 1/8 to the front web"),
        ("1x3 riser blocks", "7 @ 5", "square at wall, full 45 deg front"),
        ("1x2 front web", "96", "on edge, on the face"),
        ("1x3 front flange", "96", "flat, under web + joists"),
        ("3/4 ply", "24 x 96", "one rip per bay"),
    ]
    c.setFont("Helvetica", 8)
    for i, (a_, b_, n_) in enumerate(rows):
        y = 264 - i * 13
        c.setFillColor(black)
        c.drawString(tx, y, a_)
        c.drawString(tx + 85, y, b_)
        c.setFillColor(GREY)
        c.drawString(tx + 140, y, n_)
    footer_note(c, [
        "The front girders go in as one 16 ft piece per run, no splice. Butt joints in the 3/4 ply land on a joist; "
        "the joist stations on sheet 1 already sit under every seam.",
        "Scales: plan 1:12, pattern 1:1 - print at 100% and check the 5\" dimension with a rule before tracing.",
    ], y=22, size=7)


# ---------------------------------------------------------------- materials
def stick_count(lengths, stock_len=96.0, kerf=0.125):
    """First-fit decreasing into stock lengths; returns the number of sticks."""
    bins = []
    for ln in sorted(lengths, reverse=True):
        for i, used in enumerate(bins):
            if used + ln + kerf <= stock_len:
                bins[i] = used + ln + kerf
                break
        else:
            bins.append(ln + kerf)
    return len(bins)


def materials():
    mem = members()
    out = dict(joists=sum(1 for m in mem if m[0] in ("joist", "pjoist")), blocks=len(riser_blocks()),
               lookouts=sum(1 for m in mem if m[0] == "lookout"), cl_members=sum(1 for m in mem if m[0].startswith("cl_")))
    for stock, extra in (("1x2", []), ("1x3", [BLOCK_L] * len(riser_blocks()) + [4.0])):   # + seat block
        lengths = [m[5] for m in mem if m[6] == stock] + extra
        long_ = [ln for ln in lengths if ln > 95.0]
        short = [ln for ln in lengths if ln <= 95.0]
        out[f"n16_{stock}"] = len(long_)
        out[f"n8_{stock}"] = stick_count(short)
        out[f"lf_{stock}"] = sum(lengths)
    out["girders"] = [m[5] for m in mem if m[0] in ("girder", "girder_web")]
    return out

# ---------------------------------------------------------------- sheet 7
def sheet_steps(c):
    header(c, "Assembly sequence, fasteners and lumber", "", 7, PAGES)
    steps = [
        "1.  Build both front girders on the bench: 1x3 flange flat, 1x2 web on edge on top - outer edge for the "
        "west girder, centred for the north - glue + screw up every 8\". One 16 ft piece of each per run. Leave the "
        "west web out where the NW joist and the rim cross (H), and run it 7/8 past the flange's north end (F).",
        "2.  Mark the staging legs under each front edge. Pick two per run, keeping every gap under 60\". Drill "
        "3/8 holes through the flange there, between joist stations (detail D).",
        "3.  North girder: seat the west end on the west wall girder (E), the east end on the seat block at the "
        "wall-stub end stud (G). Prop at mid-span with the web top at -0.72.",
        "4.  West girder: seat the south end across the peninsula's north girder (E), butt the north end into the "
        "north girder and fit the gusset (F). Prop with the web top at -0.72.",
        "5.  Run the rods to the staging deck. Level both girders with the nuts, then lock with the opposing nuts.",
        "6.  Cut the riser blocks (pattern, sheet 6) and glue + screw one to each joist that lands on a -3.25 "
        "girder: the back wall end of every north and west joist, and both peninsula girders.",
        "7.  Set the joists at the sheet 1 stations, butted to the front web; screw up through the front flange "
        "into each joist and up through the back flange into each block. North: a 1x2 lookout in line with each joist. The rim and the NW joist run on past the west girder (H).",
        "8.  Fit the seam blocking (H). Build the closet boxes (north, south, then the short east box) and screw their wall sides into studs; then the SW closet strip: ledger, rail, joists.",
        "9.  Dry-lay the 3/4 ply; seams on joists or blocking. Glue + screw every 8\" along each joist, keeping "
        "screws out from under the track centrelines (feeders). Fascia last.",
    ]
    c.setFont("Helvetica", 8.6)
    c.setFillColor(black)
    y = PH - 86
    for s in steps:
        for ln in simpleSplit(s, "Helvetica", 8.6, 430):
            c.drawString(36, y, ln)
            y -= 11
        y -= 4

    tx = 495
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(tx, PH - 86, "FASTENERS")
    rows = [
        ("Girder flange to web", "glue + #6 x 1-1/4 @ 8\""),
        ("Flange up into joist", "#6 x 1-1/4, pilot"),
        ("Block to joist", "glue + 2x #6 x 1-1/4"),
        ("Back flange up into block", "#6 x 1-1/2, pilot"),
                ("Seat (E), through shim", "glue + 2x #8 x 3"),
        ("Gusset (F)", "glue + 3x #6 x 1-1/4 per flange"),
        ("Seat block (G)", "2x #8 x 2-1/2, 1x #8 x 3"),
        ("Rim, blocking ends", "2x #6 x 2"),
        ("Ply to joists", "glue + #6 x 1-1/4 @ 8\""),
        ("Rods", "5/16 nut + fender washer\neach side, 3/8 hole"),
    ]
    c.setFont("Helvetica", 8)
    yy = PH - 102
    for a_, b_ in rows:
        c.setFillColor(black)
        c.drawString(tx, yy, a_)
        for j, ln in enumerate(b_.split("\n")):
            c.setFillColor(GREY)
            c.drawString(tx + 118, yy - j * 10, ln)
        yy -= 12 + 10 * (b_.count("\n"))

    mt = materials()
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(tx, yy - 12, "LUMBER (from the framing plan)")
    c.setFont("Helvetica", 8)
    lines = [
        ("1x2, 16 ft", f"{mt['n16_1x2']}", "front girder webs"),
        ("1x3, 16 ft", f"{mt['n16_1x3']}", "front girder flanges"),
        ("1x2, 8 ft", f"{mt['n8_1x2']}", f"{mt['joists']} joists, {mt['lookouts']} lookouts, rim, blocking"),
        ("1x3, 8 ft", f"{mt['n8_1x3']}", f"{mt['blocks']} riser blocks, closet boxes, SW strip"),
        ("1x2 / 1x3 net", f"{mt['lf_1x2'] / 12:.0f} / {mt['lf_1x3'] / 12:.0f} ft", "before offcuts"),
        ("5/16-18 rod", "2 x 72\"", "4 pieces ~15\" + 2 under B1"),
        ("Nuts / fender washers", "24 / 24", ""),
        ("1/2 ply scrap", "7-1/2 sq", "gusset (F)"),
        ("1/4 hardboard scrap", "2 @ 2-1/2 sq", "shims (E)"),
    ]
    for i, (a_, b_, n_) in enumerate(lines):
        y = yy - 26 - i * 11
        c.setFillColor(black)
        c.drawString(tx, y, a_)
        c.drawString(tx + 88, y, b_)
        c.setFillColor(GREY)
        c.drawString(tx + 140, y, n_)

    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 9.5)
    y0 = yy - 26 - len(lines) * 11 - 10
    c.drawString(tx, y0, "CLEARANCE OVER STAGING")
    c.setFont("Helvetica", 8)
    for i, (a_, b_) in enumerate([
        ("Under joists", f"{J_BOT - STAGING_RAIL:.2f}"),
        ("Under front girder", f"{FG_BOT - STAGING_RAIL:.2f}"),
        ("Under back girder web", f"{WEB_BOT - STAGING_RAIL:.2f}"),
    ]):
        c.drawString(tx, y0 - 13 - i * 11, a_)
        c.drawString(tx + 118, y0 - 13 - i * 11, b_ + " in")
    c.setFillColor(GREY)
    c.setFont("Helvetica", 7)
    c.drawString(tx, y0 - 50, "Railhead = staging deck + 0.236 cork + 0.160 track.")


def main():
    c = canvas.Canvas(OUT, pagesize=(PW, PH))
    c.setTitle("HART main level - framing")
    for f in (sheet_framing_plan, sheet_section, sheet_front, sheet_junctions, sheet_details, sheet_plan, sheet_steps):
        f(c)
        c.showPage()
    c.save()
    print(OUT)
    mt = materials()
    print({k: (round(v, 1) if isinstance(v, float) else v) for k, v in mt.items() if k != "girders"},
          [round(g, 2) for g in mt["girders"]])


if __name__ == "__main__":
    main()
