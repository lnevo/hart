#!/usr/bin/env python3
"""Main-level shelf construction drawings: back L-girder riser block, 1x2 joist,
front 1x3 face + 1x2 ledger, 3/4 ply subroadbed. Needs reportlab.

All geometry is in real inches. Elevation 0 = top of the 3/4 ply subroadbed
(the 0" grade level). Staging deck top = -15.
"""
import sys
from reportlab.lib.pagesizes import letter, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color, black, white

OUT = sys.argv[1] if len(sys.argv) > 1 else "main_level_joist_construction.pdf"
PW, PH = landscape(letter)

# ---- stack (inches) ----
PLY = 0.72            # 3/4 ply as measured
J_TOP, J_BOT = -PLY, -PLY - 1.5             # 1x2 joist on edge
FACE_TOP, FACE_BOT = -PLY, -PLY - 2.5       # front 1x3 on edge
LEDGER_TOP, LEDGER_BOT = J_BOT, J_BOT - 0.75  # 1x2 flat, edge glued to the 1x3
FLANGE_TOP = -3.25                          # existing L-girder (as installed)
FLANGE_BOT = FLANGE_TOP - 0.75
WEB_BOT = FLANGE_BOT - 3.5
BLOCK_TOP, BLOCK_BOT = J_TOP, J_TOP - 2.5   # 1x3 riser block, tops flush with joist
STAGING_TOP = -15.0
STAGING_RAIL = STAGING_TOP + 0.236 + 0.160  # 6 mm cork + Atlas code 83
DEPTH = 24.0          # shelf depth used for the typical section (west wall)
FACE_OUT = DEPTH
FACE_IN = DEPTH - 0.75
LEDGER_IN = FACE_IN - 1.5
GIRDER_X0 = 0.0       # existing girder: web against the wall, flange on top
WEB_X1 = GIRDER_X0 + 0.75
FLANGE_X1 = GIRDER_X0 + 1.5
BLOCK_L = 5.0
JOIST_X0 = 0.125      # 1/8 off the wall
BLOCK_X0 = JOIST_X0  # wall end square, flush with the joist end
CLIP = BLOCK_TOP - BLOCK_BOT - 1.5          # 1.0: block hang-down below joist
ROD_X = (LEDGER_IN + FACE_IN) / 2

WOOD = Color(0.93, 0.85, 0.70)
WOOD_DK = Color(0.86, 0.74, 0.55)
PLYC = Color(0.96, 0.90, 0.76)
STEEL = Color(0.55, 0.57, 0.60)
CORK = Color(0.80, 0.62, 0.42)
ACCENT = Color(0.70, 0.12, 0.10)
DIMC = Color(0.10, 0.25, 0.55)
GREY = Color(0.45, 0.45, 0.45)
WALL = Color(0.82, 0.82, 0.82)


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


def header(c, title, sub, page, pages):
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(36, PH - 40, title)
    c.setFont("Helvetica", 8.5)
    c.setFillColor(GREY)
    c.drawString(36, PH - 54, sub)
    c.drawRightString(PW - 36, PH - 40, f"HART main level  |  sheet {page} of {pages}")
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


# ---------------------------------------------------------------- sheet 1
def sheet_section(c):
    header(c, "Typical shelf section - north & west walls",
           "Section through a joist, perpendicular to the wall.", 1, 5)
    v = View(c, ox=70, oy=528, scale=4, xref=-2.0, yref=5.6)

    # wall
    v.rect(-2.0, STAGING_TOP - 1.2, 0, 5.6, fill=WALL, lw=0.6)
    v.text(-1.0, -8, "WALL", size=7, anchor="c", color=GREY)

    # +4.25 ledge (reference)
    ph = (2, 2)
    v.rect(JOIST_X0, 0, JOIST_X0 + 1.5, 3.75, fill=None, dash=ph, lw=0.6)
    ply(v, 0.25, 8.25, 3.75 + 0.47, 0.47, dash=ph)
    track(v, 3.5, 4.22, dash=ph)
    track(v, 6.0, 4.22, dash=ph)
    v.leader(8.25, 4.0, 10.0, 4.6, "+4.25 ledge: 1/2 ply on 2x4 risers (reference only)", color=GREY)

    # subroadbed + 0" track
    ply(v, 0.25, FACE_OUT, 0, PLY)
    track(v, 13.5, 0)
    track(v, 16.0, 0)

    # joist (side view) and riser block with 45 deg clipped bottom corners
    v.rect(JOIST_X0, J_BOT, FACE_IN, J_TOP, fill=WOOD)
    v.poly(block_pts(), fill=WOOD_DK)
    v.rect(JOIST_X0, J_BOT, FACE_IN, J_TOP, fill=None)

    # L-girder (cut)
    v.rect(GIRDER_X0, FLANGE_BOT, FLANGE_X1, FLANGE_TOP, xcut=True)
    v.rect(GIRDER_X0, WEB_BOT, WEB_X1, FLANGE_BOT, xcut=True)

    # front 1x3 face + 1x2 ledger (cut)
    v.rect(FACE_IN, FACE_BOT, FACE_OUT, FACE_TOP, xcut=True)
    v.rect(LEDGER_IN, LEDGER_BOT, FACE_IN, LEDGER_TOP, xcut=True)

    # threaded rod (beyond the cut, between joists)
    v.line(ROD_X, LEDGER_TOP + 0.35, ROD_X, STAGING_TOP - PLY - 0.4, lw=1.4, color=STEEL, dash=(4, 2))
    for y in (LEDGER_TOP, LEDGER_BOT - 0.1, STAGING_TOP, STAGING_TOP - PLY - 0.1):
        v.rect(ROD_X - 0.4, y, ROD_X + 0.4, y + 0.1, fill=STEEL, lw=0.3)

    # staging level
    ply(v, 0.0, FACE_OUT + 0.5, STAGING_TOP, PLY)
    for xc in (5.0, 9.5, 14.0, 18.5):
        track(v, xc, STAGING_TOP)
    v.text(12, STAGING_TOP - PLY - 0.8, "STAGING LEVEL deck (existing)", size=7, anchor="c", color=GREY)

    # clearances
    v.dim_v(13.0, J_BOT, STAGING_RAIL, f"{J_BOT - STAGING_RAIL:.2f} clear")
    v.dim_v(FACE_OUT + 0.7, FACE_BOT, STAGING_RAIL, f"{FACE_BOT - STAGING_RAIL:.2f} clear")
    v.dim_v(GIRDER_X0 + 1.2, WEB_BOT, STAGING_RAIL, f"{WEB_BOT - STAGING_RAIL:.2f} clear")
    v.dim_h(-12.6, 0, FACE_OUT, f"{DEPTH:.0f} shelf depth (west wall; north wall 23-1/2 tapering to 17-1/2)")

    # leaders
    v.leader(BLOCK_X0 + BLOCK_L - 0.3, BLOCK_BOT + 0.4, 8.0, -5.0,
             "1x3 riser block, 5\" long, square at the wall,\n45 deg miter at the front, glued + screwed\nto the joist side (sheet 2)")
    v.leader(GIRDER_X0 + 0.4, -6.2, 5.0, -6.9, "Existing L-girder: 1x4 web + 1x2 flange,\n"
             "flange top -3.25 (as installed)")
    v.leader(17.5, (J_TOP + J_BOT) / 2, 15.0, -4.4, "1x2 joist on edge, 16\" o.c.")
    v.leader(FACE_OUT - 0.2, FACE_BOT + 0.2, 26.3, -4.4, "1x3 face on edge\n(fascia backer)")
    v.leader(LEDGER_IN + 0.3, LEDGER_BOT, 15.0, -6.6,
             "1x2 ledger, flat, edge glued + screwed\nto the 1x3 inside face (sheet 3)")
    v.leader(ROD_X, -10.0, 26.3, -10.0, "5/16-18 threaded rod,\nmax 36\" apart, between\njoists; nut + fender\n"
             "washer each side")
    v.leader(20.5, -PLY / 2, 26.3, 1.2, "3/4 ply subroadbed\n(0.72 measured), glued +\nscrewed to joists")
    v.leader(16.0, 0.4, 17.5, 2.6, "0\" grade track (typ.)")

    # elevation list (page coordinates)
    ex, ey = 560, 170
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(black)
    c.drawString(ex, ey, "ELEVATIONS")
    rows = [(0.0, "top of 3/4 ply subroadbed"), (J_TOP, "joist top, 1x3 top"),
            (J_BOT, "joist bottom = ledger top"), (LEDGER_BOT, "ledger bottom"),
            (FACE_BOT, "1x3 bottom, block bottom"), (FLANGE_TOP, "girder flange top"),
            (WEB_BOT, "girder web bottom"), (STAGING_RAIL, "staging railhead"),
            (STAGING_TOP, "staging deck top")]
    c.setFont("Helvetica", 7.5)
    for i, (y, s) in enumerate(rows):
        c.drawRightString(ex + 32, ey - 12 - i * 10, f"{y:.2f}")
        c.drawString(ex + 40, ey - 12 - i * 10, s)

    footer_note(c, [
        "Block bottom lands 0.03 above the flange (3.25 - 2.50 - 0.72); the deck top finishes 1/32 low - within "
        "tolerance, or shim the flange.",
        "Existing girder against the wall (web to the studs, flange on top). Track = 0.236 cork + 0.160 Atlas code 83 "
        "(caliper before clearance sign-off).",
        "Scale 1:4 on Letter landscape. Lumber cut in section shows an X; the joist and riser block are in side view.",
    ], y=22, size=7)


def block_pts():
    # square at the wall end (full bearing on the flange), one 45 deg miter on the visible front end
    return [(BLOCK_X0, BLOCK_TOP), (BLOCK_X0 + BLOCK_L, BLOCK_TOP), (BLOCK_X0 + BLOCK_L, BLOCK_BOT + CLIP),
            (BLOCK_X0 + BLOCK_L - CLIP, BLOCK_BOT), (BLOCK_X0, BLOCK_BOT)]


# ---------------------------------------------------------------- sheet 2
def sheet_details(c):
    header(c, "Details - riser block at the back girder",
           "A: side view along the joist.  B: looking along the joist (joist and block cut, girder in elevation).",
           2, 5)
    mid = (J_TOP + J_BOT) / 2

    # Detail A (1:2)
    a = View(c, ox=60, oy=500, scale=2, xref=-0.5, yref=1.4)
    a.text(-0.5, 1.4, "A   SIDE VIEW ALONG THE JOIST   1:2", size=9, bold=True, dy=4)
    a.rect(-0.5, WEB_BOT - 0.3, 0, 0.6, fill=WALL, lw=0.5)
    ply(a, JOIST_X0, 8.5, 0, PLY)
    a.poly(block_pts(), fill=WOOD_DK)
    a.rect(JOIST_X0, J_BOT, 8.5, J_TOP, fill=None)
    a.text(8.3, mid, "1x2 joist", size=7, anchor="r", dy=-2)
    a.rect(GIRDER_X0, FLANGE_BOT, FLANGE_X1, FLANGE_TOP, xcut=True)
    a.rect(GIRDER_X0, WEB_BOT, WEB_X1, FLANGE_BOT, xcut=True)
    for x in (BLOCK_X0 + 1.2, BLOCK_X0 + BLOCK_L - 1.2):
        a.screw(x, mid, x, mid)
    fx = (GIRDER_X0 + FLANGE_X1) / 2
    a.screw(fx, FLANGE_BOT, fx, FLANGE_BOT + 1.5)
    a.dim_h(0.45, BLOCK_X0, BLOCK_X0 + BLOCK_L, "5")
    a.dim_v(BLOCK_X0 + BLOCK_L + 1.3, BLOCK_TOP, BLOCK_BOT, "2-1/2")
    a.dim_v(BLOCK_X0 + BLOCK_L + 0.4, J_BOT, BLOCK_BOT, "1")
    a.text(BLOCK_X0 + BLOCK_L - CLIP / 2, BLOCK_BOT + CLIP / 2, "45 deg", size=7, color=ACCENT, dx=4, dy=-14)
    a.text(-0.25, -5.5, "WALL", size=6.5, anchor="c", color=GREY)
    a.leader(fx, FLANGE_BOT - 0.05, 5.4, -5.0, "#6 x 1-1/2 up through the\nflange into the block, pilot",
             color=ACCENT)
    a.leader(BLOCK_X0 + BLOCK_L - 1.2, mid, 6.4, -3.3, "glue + 2x #6 x 1-1/4 through\nthe block into the joist",
             color=ACCENT)
    a.leader(GIRDER_X0 + 0.4, -6.5, 5.4, -6.6, "existing L-girder\n1x4 web, 1x2 flange")

    # Detail B (1:2)
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
        "the flange. The wall end stays square so the block bears on the full 1-1/2 flange;",
        "the single 45 deg miter trims only the 1\" hang-down on the front end. Joist and block ends sit 1/8 off the "
        "wall. Keep every block on the same side of its joist. "
        "Full-size pattern on sheet 4.",
    ], y=30)


# ---------------------------------------------------------------- sheet 3
def sheet_front(c):
    header(c, "Details - front 1x3 face + 1x2 ledger",
           "C: side view along a joist at the front edge.  D: the same edge between joists, at a rod.", 3, 5)
    mid = (J_TOP + J_BOT) / 2
    x0 = LEDGER_IN - 2.5

    f = View(c, ox=50, oy=490, scale=1.5, xref=x0, yref=0.9)
    f.text(x0, 0.9, "C   AT A JOIST   1:1.5", size=9, bold=True, dy=4)
    ply(f, x0, FACE_OUT, 0, PLY)
    f.rect(x0, J_BOT, FACE_IN, J_TOP, fill=WOOD)
    f.rect(FACE_IN, FACE_BOT, FACE_OUT, FACE_TOP, xcut=True)
    f.rect(LEDGER_IN, LEDGER_BOT, FACE_IN, LEDGER_TOP, xcut=True)
    f.screw(FACE_OUT + 0.25, mid, FACE_IN - 1.25, mid)
    f.screw(LEDGER_IN + 0.75, LEDGER_BOT - 0.2, LEDGER_IN + 0.75, LEDGER_TOP + 0.5)
    f.dim_v(FACE_OUT + 0.45, FACE_TOP, FACE_BOT, "2-1/2")
    f.dim_v(FACE_OUT + 1.3, FACE_TOP, LEDGER_TOP, "1-1/2 = joist")
    f.dim_v(x0 + 0.4, J_TOP, J_BOT, "1-1/2", side="r")
    f.dim_h(FACE_BOT - 0.45, LEDGER_IN, FACE_IN, "1-1/2", above=False)
    f.dim_h(FACE_BOT - 0.45, FACE_IN, FACE_OUT, "3/4", above=False)
    f.text(FACE_IN - 0.08, (LEDGER_BOT + FACE_BOT) / 2, "1/4", size=6.5, color=DIMC, anchor="r", dy=-3)
    f.leader(FACE_IN - 1.0, mid + 0.15, x0 + 0.1, -4.5, "2x #6 x 2 through the 1x3 into the joist end, pilot",
             color=ACCENT)
    f.leader(LEDGER_IN + 0.75, LEDGER_BOT - 0.2, x0 + 0.1, -5.1, "#6 x 1-1/4 up through the ledger into the joist",
             color=ACCENT)
    f.leader(FACE_IN - 0.4, (LEDGER_TOP + LEDGER_BOT) / 2, x0 + 0.1, -5.7,
             "1x2 ledger: glued + screwed to the 1x3 (see D)")

    g = View(c, ox=440, oy=490, scale=1.5, xref=LEDGER_IN - 1.0, yref=0.9)
    g.text(LEDGER_IN - 1.0, 0.9, "D   BETWEEN JOISTS, AT A ROD   1:1.5", size=9, bold=True, dy=4)
    ply(g, LEDGER_IN - 1.0, FACE_OUT, 0, PLY)
    g.rect(FACE_IN, FACE_BOT, FACE_OUT, FACE_TOP, xcut=True)
    g.rect(LEDGER_IN, LEDGER_BOT, FACE_IN, LEDGER_TOP, xcut=True)
    g.screw(FACE_OUT + 0.25, (LEDGER_TOP + LEDGER_BOT) / 2, FACE_IN - 0.9, (LEDGER_TOP + LEDGER_BOT) / 2)
    g.line(ROD_X, LEDGER_TOP + 0.55, ROD_X, FACE_BOT - 1.4, lw=3, color=STEEL)
    g.line(ROD_X, FACE_BOT - 1.4, ROD_X, FACE_BOT - 1.9, lw=3, color=STEEL, dash=(2, 2))
    for y in (LEDGER_TOP, LEDGER_BOT - 0.1):
        g.rect(ROD_X - 0.55, y, ROD_X + 0.55, y + 0.1, fill=STEEL, lw=0.3)
    g.rect(ROD_X - 0.28, LEDGER_TOP + 0.1, ROD_X + 0.28, LEDGER_TOP + 0.38, fill=STEEL, lw=0.3)
    g.rect(ROD_X - 0.28, LEDGER_BOT - 0.38, ROD_X + 0.28, LEDGER_BOT - 0.1, fill=STEEL, lw=0.3)
    g.leader(FACE_OUT + 0.25, (LEDGER_TOP + LEDGER_BOT) / 2, FACE_OUT + 0.6, -3.6,
             "glue + #6 x 1-5/8\nevery 8\" through the\n1x3 into the ledger\nedge, pilot", color=ACCENT)
    g.leader(ROD_X + 0.28, LEDGER_TOP + 0.25, FACE_OUT + 0.6, -0.9,
             "5/16-18 rod, 3/8 hole\ncentred in the ledger;\nnut + fender washer\nabove and below")
    g.text(ROD_X, FACE_BOT - 2.2, "to staging deck (nut + washer each side)", size=7, anchor="c", color=GREY)

    footer_note(c, [
        "Build the face + ledger on the bench first. Set the ledger height with a 1x2 offcut resting on it, its top "
        "flush with the 1x3 top: ledger top 1-1/2 below the 1x3 top, 1/4 up from its bottom.",
        "Ledger-to-face is a long-grain glue joint (edge to face); the glue is the structure and the screws clamp it "
        "while it cures. Stagger the face and ledger splices.",
    ], y=40)


# ---------------------------------------------------------------- sheet 4
def sheet_plan(c):
    header(c, "Plan - typical 8 ft bay, deck removed  +  riser block pattern",
           "Looking down. Joists at 16\" o.c. land on the existing girder via the riser blocks; rods carry the "
           "front ledger between joists.", 4, 5)
    v = View(c, ox=50, oy=372, scale=12, xref=-2.0, yref=-2.0)
    L = 96.0
    v.rect(-2, -2, L + 2, 0, fill=WALL, lw=0.5)
    v.text(L / 2, -1.6, "WALL", size=7, anchor="c", color=GREY, dy=2)
    v.rect(0, GIRDER_X0, L, FLANGE_X1, fill=WOOD, lw=0.6)
    v.text(L + 0.6, (GIRDER_X0 + FLANGE_X1) / 2, "existing girder flange", size=6.5, dy=-2)
    v.rect(0, LEDGER_IN, L, FACE_IN, fill=WOOD_DK, lw=0.6)
    v.rect(0, FACE_IN, L, FACE_OUT, fill=WOOD, lw=0.6)
    v.text(L + 0.6, FACE_OUT + 0.2, "1x3 face", size=6.5, dy=-2)
    v.text(L + 0.6, LEDGER_IN - 0.4, "1x2 ledger", size=6.5, dy=-2)
    xs = [0.375 + 16 * i for i in range(7)]
    xs[-1] = L - 0.375
    for x in xs:
        v.rect(x - 0.375, JOIST_X0, x + 0.375, FACE_IN, fill=WOOD, lw=0.6)
        v.rect(x + 0.375, BLOCK_X0, x + 1.125, BLOCK_X0 + BLOCK_L, fill=WOOD_DK, lw=0.5)
    for x in (24.375, 56.375, 88.375):
        a, b = v.p(x, ROD_X)
        c.setFillColor(STEEL)
        c.circle(a, b, 3, stroke=1, fill=1)
    v.dim_h(-4.0, xs[0], xs[1], "16 o.c.", above=False)
    v.dim_h(FACE_OUT + 2.0, 24.375, 56.375, "rods max 36 apart, mid-bay")
    v.dim_v(-3.5, 0, FACE_OUT, "24", side="l")
    v.text(xs[1] + 1.4, BLOCK_X0 + BLOCK_L + 0.4, "riser block", size=6.5, dy=-2)
    v.text(xs[2] + 1.0, 14, "1x2 joist", size=6.5)

    p = View(c, ox=80, oy=100, scale=1)
    p.text(0, 3.2, "RISER BLOCK - FULL SIZE PATTERN (1:1)", size=9, bold=True)
    p.poly([(0, 2.5), (5, 2.5), (5, 1.0), (4.0, 0), (0, 0)], fill=WOOD_DK)
    p.line(0, 1.0, 5, 1.0, lw=0.4, color=GREY, dash=(3, 2))
    p.text(2.5, 1.05, "joist bottom line", size=6.5, color=GREY, anchor="c", dy=2)
    p.dim_h(2.8, 0, 5, "5")
    p.dim_h(-0.3, 0, 4, "4", above=False)
    p.text(0, -0.75, "square end goes to the wall", size=6.5, color=GREY)
    p.dim_v(-0.3, 0, 2.5, "2-1/2", side="l")
    p.dim_v(5.3, 0, 1.0, "1")
    p.text(2.5, 1.75, "grain  ->", size=7, anchor="c", color=GREY)

    tx = 500
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(tx, 280, "CUT LIST PER 8 FT BAY (24\" deep)")
    rows = [
        ("1x2 joists", "7 @ 23-1/8", "24 - 3/4 face - 1/8 wall gap"),
        ("1x3 riser blocks", "7 @ 5", "square at wall, 45 deg front"),
        ("1x3 face", "96", "on edge"),
        ("1x2 ledger", "96", "flat, edge to the 1x3"),
        ("5/16-18 rod", "3 @ ~13", "fit to the staging deck"),
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
        "Splice the 1x3 face and the ledger at different joists; butt joints in the 3/4 ply land on a joist. "
        "North wall: 23-1/2 deep tapering to 17-1/2 - cut each joist to depth - 3/4 - 1/8.",
        "Scales: plan 1:12, pattern 1:1 - print at 100% and check the 5\" dimension with a rule before tracing.",
    ], y=22, size=7)


# ---------------------------------------------------------------- sheet 5
def sheet_steps(c):
    header(c, "Assembly sequence and fastener schedule", "", 5, 5)
    steps = [
        "1.  Rip the front members: 1x3 face and 1x2 ledger to length. Stagger splices so they never fall at the "
        "same joist.",
        "2.  On the bench, glue the ledger flat to the inside face of the 1x3, its edge against the face. Set the "
        "height with a 1x2 offcut on the ledger, flush with the 1x3 top (ledger top 1-1/2 below the 1x3 top, "
        "1/4 up from its bottom). Screw from outside every 8\". Let it cure.",
        "3.  Cut the riser blocks: 5\" of 1x3, square at the wall end; trim the front bottom corner at 45 deg, 1\" each way. Trace the "
        "full-size pattern on sheet 4 or make a stop block on the miter saw.",
        "4.  Glue + screw a block to the side of each joist: top flush, square end flush with the joist's wall end. "
        "Same side on every joist.",
        "5.  Prop the front assembly at height (ledger top at -2.22). Drill 3/8 holes in the ledger mid-bay for the "
        "rods, max 36\" apart, between joists.",
        "6.  Set the joists at 16\" o.c.: blocks on the flange, front ends on the ledger, butted to the 1x3. "
        "Screw up through the flange into each block, through the 1x3 into the joist end, and up through the "
        "ledger into the joist.",
        "7.  Run the rods from the staging deck to the ledger. Level the front edge with the nuts, then lock "
        "with the opposing nuts.",
        "8.  Dry-lay the 3/4 ply; butt joints on joists. Glue + screw every 8\" along each joist, keeping screws "
        "out from under the track centrelines (feeders).",
        "9.  Check the deck top against the helix exit and the +4.25 ledge risers before the glue sets.",
    ]
    c.setFont("Helvetica", 9)
    c.setFillColor(black)
    y = PH - 90
    from reportlab.lib.utils import simpleSplit
    for s in steps:
        for ln in simpleSplit(s, "Helvetica", 9, 430):
            c.drawString(36, y, ln)
            y -= 12
        y -= 5

    tx = 500
    c.setFont("Helvetica-Bold", 10)
    c.drawString(tx, PH - 90, "FASTENERS")
    rows = [
        ("Block to joist", "glue + 2x #6 x 1-1/4"),
        ("Flange up into block", "#6 x 1-1/2, pilot"),
        ("Ledger to 1x3 face", "glue + #6 x 1-5/8 @ 8\""),
        ("1x3 into joist end", "2x #6 x 2, pilot"),
        ("Ledger up into joist", "#6 x 1-1/4"),
        ("Ply to joists", "glue + #6 x 1-1/4 @ 8\""),
        ("Rod at ledger / deck", "5/16 nut + fender washer\neach side, 3/8 hole"),
    ]
    c.setFont("Helvetica", 8.5)
    yy = PH - 108
    for a_, b_ in rows:
        c.setFillColor(black)
        c.drawString(tx, yy, a_)
        for j, ln in enumerate(b_.split("\n")):
            c.setFillColor(GREY)
            c.drawString(tx + 115, yy - j * 11, ln)
        yy -= 14 + 11 * (b_.count("\n"))

    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(tx, yy - 14, "CLEARANCE OVER STAGING")
    c.setFont("Helvetica", 8.5)
    for i, (a_, b_) in enumerate([
        ("Under joists", f"{J_BOT - STAGING_RAIL:.2f}"),
        ("Under front 1x3", f"{FACE_BOT - STAGING_RAIL:.2f}"),
        ("Under girder web", f"{WEB_BOT - STAGING_RAIL:.2f}"),
    ]):
        c.drawString(tx, yy - 30 - i * 12, a_)
        c.drawString(tx + 115, yy - 30 - i * 12, b_ + " in")
    c.setFillColor(GREY)
    c.setFont("Helvetica", 7.5)
    c.drawString(tx, yy - 72, "Railhead = staging deck + 0.236 cork + 0.160 track.")


def main():
    c = canvas.Canvas(OUT, pagesize=(PW, PH))
    c.setTitle("HART main level - joist construction")
    for f in (sheet_section, sheet_details, sheet_front, sheet_plan, sheet_steps):
        f(c)
        c.showPage()
    c.save()
    print(OUT)


if __name__ == "__main__":
    main()
