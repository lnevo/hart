#!/usr/bin/env python3
"""Staging level (-15) as built: framing plan, sections and plywood piece map, drawn the same way as the main
level. Reuses the main level's room outlines, joist stations and drawing helpers. Needs reportlab
and shapely.

Section geometry is in real inches, elevation 0 = top of the main-level 3/4 ply; the staging deck top is -15.
The plan is in room inches (x east, y south), the same as the main level.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "main_level"))

from reportlab.lib.colors import Color, black  # noqa: E402
from reportlab.lib.utils import simpleSplit  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402
from shapely.geometry import LineString, box  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import make_joist_construction_pdf as ml  # noqa: E402
from main_level_geometry import (F_NW, fillet, F_SW, NORTH, PEN, WALL_GAP, WALLS,  # noqa: E402
                                 WEST, disc)
from make_joist_construction_pdf import (ACCENT, CLOSETC, DECK, GREY, NEW, WALL,  # noqa: E402
                                         WOOD, WOOD_DK, PlanView, View, footer_note, frac, header, ply, track)

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "staging_level_framing.pdf")
PW, PH = ml.PW, ml.PH
PAGES = 3

# ---- stack (inches) ----
TOP = -15.0
PLY = 0.72
J_TOP, J_BOT = TOP - PLY, TOP - PLY - 2.5        # 1x3 joist on edge, straight on the girder flanges
G_FL_TOP, G_FL_BOT = J_BOT, J_BOT - 0.75          # 1x4 web + 1x2 flange L-girders
G_WEB_BOT = G_FL_BOT - 3.5
FLOOR = -40.0                                     # drawn only; field-measure
MAIN_FL_TOP = -3.25                               # main level: existing upper girders

# ---- plan (room inches) ----
Y_WALL_N, X_WALL_W = 47.5, 4.5
NG = (63.5, 65.0)
X_W_EDGE = 28.5                                   # west run deck edge
WG = (21.0, 22.5)                                 # west front girder flange, inset ~6 in, web west like the wall girder
SW_N_OUT, SW_N_IN = (208.5, 210.0), (218.5, 220.0)   # SW box lower girders: inner pair 18 in from each edge,
SW_S_IN, SW_S_OUT = (247.0, 248.5), (257.0, 258.5)   # outer pair about 10 in further out
SW_X = (X_WALL_W + 1.5, 100.0)                    # wall girder to about x 100; verify the tip ends
WG_Y = (NG[1], SW_S_OUT[0])                       # west front girder runs to the southernmost SW girder
WG_S = (SW_S_OUT[1], 302.5)                       # L-girder off that girder, south under the 18 x 36 strip to the wall
WG_S_X = (WG[0] - 6.0, WG[1] - 6.0)              # inset from the strip edge, not in line with the west girder; verify
STRIP = box(X_WALL_W + 0.125, 266.5, WG[1], 302.5)  # SW strip at the wall, 18 x 36 (wider than the main level's)
F_STRIP = fillet(WG[1], 266.5, 1, 1, 6.0)            # 6 in curve where it steps in, as the main-level W3
SW_FRAMES = (30.0, 76.0)                          # leg frames under the west and east straights (x); verify
SW_LEGS = [(x, y) for x in SW_FRAMES for y in (209.25, 257.75)]    # 2x4 legs under the outer girders
# wall runs: two leg frames each, a 1x4 from the wall girder to the front girder on a 2x4 leg; verify positions
N_FRAMES = (55.0, 115.0)                          # x
W_FRAMES = (110.0, 165.0)                         # y
# SW deck: two 18 in rectangles on the straights (FG keeps the F3 fillet curve, no notch) and the bullnose
# (G2 + G3, the 15 / 33 in ring round the tip) as one solid piece
LOOP_C, G_RO, G_W = (78.8, 233.4), 33.0, 18.0
_ring = disc(*LOOP_C, G_RO).difference(disc(*LOOP_C, G_RO - G_W))
G1 = box(28.5, LOOP_C[1] - G_RO, LOOP_C[0], LOOP_C[1] - G_RO + G_W)
G4 = box(28.5, LOOP_C[1] + G_RO - G_W, LOOP_C[0], LOOP_C[1] + G_RO)
FG = unary_union([F_SW.intersection(box(0, 0, 300, G1.bounds[3])), G1])
GG = G4
BN = _ring.intersection(box(LOOP_C[0], 0, 300, 400))
SW_DECK = unary_union([FG, GG, BN])
# helix peninsula: two long girders off the closet wall on the neck edges, the south one cut out at the hatch;
# a free girder halfway between it and the south edge; a 2x4 + 1x4 leg frame under all three at each end
HC = (92.4, 132.75)
HATCH = box(HC[0] - 18.0, HC[1] - 12.0, HC[0] + 18.0, HC[1] + 12.0)    # 36 E-W x 24 N-S placeholder
HATCH_FR = HATCH.buffer(1.5, join_style=2)
H_A, H_B = (114.0, 115.5), (134.5, 136.0)
H_C = (151.6, 153.1)
H_FRAMES = (66.0, 121.0)                          # leg frames (x); verify
X_PEN_WALL = 158.5
X_N2_END = 158.48 - 2.5                           # N2 ends about 2-1/2 in short of the closet wall; verify
TONGUE_N, TONGUE_S = (53.15, 59.15), (118.45, 124.45)   # 6 in tongues through the wall openings, as the main level
J_EAST = 89.5                                     # closet alcove pieces split here, as the main level
# closet as built: a long 8 in shelf down the east wall and a separate rectangle in each alcove, each a 1x3 box
# on edge; straight deck edges, no turnback curve (the desk sits under the shelf)
X_SHELF = 209.0                                   # shelf front edge, 8 in off the east wall
CL_N, CL_S = (Y_WALL_N, 65.0), (114.0, 131.5)     # alcove rectangles (y), from the openings (x 163) to the shelf
CL_SHELF_X = [Y_WALL_N, 61.5, 75.5, 89.5, 103.5, 117.5, 131.5]   # shelf cross pieces (y), ends included
CL_BOX_X = [163.0, 178.0, 193.5, X_SHELF]                        # alcove box cross pieces (x), ends included
STG_CLOSET = unary_union([box(163.0, CL_N[0] + WALL_GAP, X_SHELF, CL_N[1]),
                          box(163.0, CL_S[0], X_SHELF, CL_S[1] - WALL_GAP),
                          box(X_SHELF, Y_WALL_N + WALL_GAP, 217.0 - WALL_GAP, 131.5 - WALL_GAP)])


def pen_span(y):
    hit = LineString([(0, y), (200, y)]).intersection(PEN)
    return hit.bounds[0], hit.bounds[2]


def deck_runs(geom, x):
    """Intervals (y0, y1) where the vertical line at x crosses geom."""
    hit = LineString([(x, 0), (x, 400)]).intersection(geom)
    parts = hit.geoms if hasattr(hit, "geoms") else [hit]
    return sorted((p.bounds[1], p.bounds[3]) for p in parts if not p.is_empty and p.length > 1.0)


def members():
    m = []

    def add(kind, x0, y0, x1, y1, stock="1x3"):
        m.append((kind, x0, y0, x1, y1, max(x1 - x0, y1 - y0), stock))

    # wall runs: front girders like the main level, 1x3 joists at the same stations (same ply seams)
    add("girder", ml.NG_X[0], NG[0], ml.NG_X[1], NG[1], "L")
    add("girder", WG[0], WG_Y[0], WG[1], WG_Y[1], "L")
    for x in ml.N_JOISTS:
        y1 = ml.Y_NW_STOP if x < ml.X_NW_END + 0.5 else ml.front_edge_y(x)
        add("joist", x - 0.375, Y_WALL_N + WALL_GAP, x + 0.375, y1)
    for y in ml.W_JOISTS:
        x1 = ml.X_NW_END if y == ml.W_JOISTS[0] else ml.X_RIM_END if y == ml.Y_RIM else X_W_EDGE
        add("joist", X_WALL_W + WALL_GAP, y - 0.375, x1, y + 0.375)
    add("block", X_W_EDGE, ml.W_JOISTS[-2] + 0.375, X_W_EDGE + 0.75, ml.Y_RIM - 0.375, "1x2")
    for x in N_FRAMES:
        add("frame", x - 0.375, Y_WALL_N, x + 0.375, NG[1] + 1.0, "1x4")
    for y in W_FRAMES:
        add("frame", X_WALL_W, y - 0.375, WG[1] + 1.0, y + 0.375, "1x4")
    # SW box
    for g in (SW_N_OUT, SW_N_IN, SW_S_IN, SW_S_OUT):
        x0 = SW_X[0] if g == SW_S_OUT else WG[1]   # the other three butt the west front girder
        add("girder", x0, g[0], SW_X[1], g[1], "L")
    add("girder", WG_S_X[0], WG_S[0], WG_S_X[1], WG_S[1], "L")
    for x in SW_FRAMES:
        add("frame", x - 0.375, SW_N_OUT[0] - 1.0, x + 0.375, SW_S_OUT[1] + 1.0, "1x4")
    sw = unary_union([SW_DECK, WEST.intersection(box(0, ml.Y_RIM + 0.375, 300, 400))])
    for x in (5.375, 17.0, 28.875, 45.0, 61.5, 77.5, 92.5, 104.5):
        for y0, y1 in deck_runs(sw, x):
            y0 = max(y0, ml.Y_RIM + 0.375)
            if y1 < LOOP_C[1]:
                y1 = max(y1, SW_N_IN[1])
            if y0 > LOOP_C[1]:
                y0 = min(y0, SW_S_IN[0])
            add("joist", x - 0.375, y0, x + 0.375, y1)
    # helix peninsula
    xa0 = pen_span(sum(H_A) / 2)[0] + 1.0
    xb0 = pen_span(sum(H_B) / 2)[0] + 1.0
    xc0, xc1 = pen_span(sum(H_C) / 2)
    add("girder", xa0, H_A[0], X_PEN_WALL, H_A[1], "L")
    add("girder", xb0, H_B[0], HATCH_FR.bounds[0], H_B[1], "L")
    add("girder", HATCH_FR.bounds[2], H_B[0], X_PEN_WALL, H_B[1], "L")
    add("girder", xc0 + 1.0, H_C[0], xc1 - 1.0, H_C[1], "L")
    for x in H_FRAMES:
        add("frame", x - 0.375, H_A[0] - 1.0, x + 0.375, H_C[1] + 1.0, "1x4")
    hx0, hy0, hx1, hy1 = HATCH_FR.bounds
    add("hatch", hx0, hy0, hx1, hy0 + 1.5, "2x4")
    add("hatch", hx0, hy1 - 1.5, hx1, hy1, "2x4")
    add("hatch", hx0, hy0 + 1.5, hx0 + 1.5, hy1 - 1.5, "2x4")
    add("hatch", hx1 - 1.5, hy0 + 1.5, hx1, hy1 - 1.5, "2x4")
    xs = [PEN.bounds[0] + 2.0 + 16.0 * i for i in range(7)] + [X_PEN_WALL - 0.5]
    for x in xs:
        for y0, y1 in deck_runs(PEN.difference(HATCH_FR), x):
            if hx0 < x < hx1:            # ends on the hatch frame
                y1 = hy0 + 1.5 if y1 <= hy0 + 0.01 else y1
                y0 = hy1 - 1.5 if y0 >= hy1 - 0.01 else y0
            add("joist", x - 0.375, y0, x + 0.375, y1)
    # closet: the east shelf box (full length on the wall) and the two alcove boxes stopping against it
    add("cl_ledger", 216.25, Y_WALL_N, 217.0, 131.5)
    add("cl_rail", X_SHELF, Y_WALL_N, X_SHELF + 0.75, 131.5)
    for i, y in enumerate(CL_SHELF_X):
        y0 = y if i == 0 else y - 0.75 if i == len(CL_SHELF_X) - 1 else y - 0.375
        add("cl_joist", X_SHELF + 0.75, y0, 216.25, y0 + 0.75)
    for (y0, y1) in (CL_N, CL_S):
        add("cl_ledger" if y0 == Y_WALL_N else "cl_rail", 163.0, y0, X_SHELF, y0 + 0.75)
        add("cl_rail" if y0 == Y_WALL_N else "cl_ledger", 163.0, y1 - 0.75, X_SHELF, y1)
        for i, x in enumerate(CL_BOX_X):
            x0 = x if i == 0 else x - 0.75 if i == len(CL_BOX_X) - 1 else x - 0.375
            add("cl_joist", x0, y0 + 0.75, x0 + 0.75, y1 - 0.75)
    for y in (267.0, 284.0, 301.5):              # SW strip: 1x3 joists from the wall girder over the strip girder
        add("joist", X_WALL_W + 1.5, y - 0.375, WG[1], y + 0.375)
    return m


# ---------------------------------------------------------------- plywood (mirrors the 0 in pieces)
def pieces():
    n_a = NORTH.intersection(box(0, 0, X_WALL_W + WALL_GAP + 96, 300))
    n_b = NORTH.difference(n_a)
    y_w1, y_w2 = 302.5 - 192.0, 302.5 - 96.0
    w_1 = WEST.intersection(box(0, 0, 300, y_w1))
    w_2 = WEST.intersection(box(0, y_w1, 300, y_w2))
    w_3 = WEST.intersection(box(0, y_w2, 300, 400))
    px0, py0 = PEN.bounds[0], PEN.bounds[1]
    pen = PEN.difference(HATCH)
    hs1 = pen.intersection(box(px0, py0, px0 + 96, py0 + 48))
    hs3 = pen.intersection(box(px0 + 96, 0, 300, 300))
    hs2 = pen.difference(hs1).difference(hs3)
    # closet deck: each alcove piece runs through its wall opening on a notched tongue (as the main-level N2),
    # the south one across the neck to HS1, the north one to N2; the east shelf is one piece. The neck beside the
    # south tongue is left open, to be filled with scrap or foam.
    alcoves = STG_CLOSET.intersection(box(0, 0, X_SHELF, 300))
    tongue_s = box(hs1.bounds[2], TONGUE_S[0], STG_CLOSET.bounds[0] + 0.1, TONGUE_S[1])
    b2a = unary_union([alcoves.intersection(box(0, J_EAST, 300, 300)), tongue_s])
    n_end = n_b.intersection(box(X_N2_END, 0, 300, 300))     # N2 stops short; the north tongue runs into the gap
    n_b = n_b.difference(n_end)
    tongue_n = box(X_N2_END, TONGUE_N[0], STG_CLOSET.bounds[0] + 0.1, TONGUE_N[1])
    b3a = unary_union([alcoves.intersection(box(0, 0, 300, J_EAST)), tongue_n])
    pieces.fill = unary_union([hs3.difference(tongue_s), n_end.difference(tongue_n)])
    return [
        ("N1", n_a, "North wall", "square cuts"),
        ("N2", n_b, "North wall east", "eased front edge"),
        ("W1", unary_union([w_1, F_NW]), "West wall, north end", "with the 10 in NW fillet"),
        ("W2", w_2, "West wall, middle", "96 in"),
        ("W3", unary_union([w_3, STRIP, F_STRIP]), "West wall south end + SW strip",
         "96 in; strip 18 x 36, 6 in curve where it steps in"),
        ("FG", FG, "SW box, north straight", "18 in rectangle + the F3 fillet curve"),
        ("GG", GG, "SW box, south straight", "18 in rectangle"),
        ("BN", BN, "SW box, bullnose (G2 + G3)", "one solid piece round the tip"),
        ("HS1", hs1, "Helix peninsula, north", "full 48 x 96 sheet, bulb to neck"),
        ("HS2", hs2, "Helix peninsula, south span", "around the hatch"),
        ("B2a", b2a, "Closet south alcove", "notched tongue through the wall and across the neck to HS1"),
        ("B3a", b3a, "Closet north alcove", "tongue through the wall, about 2-1/2 in into N2's end"),
        ("B4", STG_CLOSET.difference(alcoves), "Closet east shelf", "8 x 84, one piece on the shelf box"),
    ]


STYLE = {"girder": (NEW, 0.4), "joist": (WOOD_DK, 0.3), "block": (NEW, 0.3), "frame": (Color(0.35, 0.35, 0.40), 0.4),
         "hatch": (Color(0.55, 0.40, 0.25), 0.4), "cl_ledger": (CLOSETC, 0.3), "cl_rail": (CLOSETC, 0.3),
         "cl_joist": (CLOSETC, 0.3)}


# ---------------------------------------------------------------- sheet 1
def sheet_plan(c):
    header(c, "Staging level framing plan (-15), as built, deck removed",
           "Looking down. Orange = L-girders (1x4 web + 1x2 flange); tan = 1x3 joists.", 1, PAGES, level="staging level")
    v = PlanView(c, ox=40, oy=PH - 74, k=1.86, x0=0.0, y0=43.0)
    v.geom(WALLS, fill=WALL, stroke=GREY, lw=0.4)
    deck = unary_union([NORTH, WEST, F_NW, SW_DECK, STRIP, F_STRIP, STG_CLOSET, PEN])
    v.geom(deck, fill=DECK, stroke=GREY, lw=0.4, dash=(2, 1.5))
    v.geom(HATCH, fill=Color(1, 1, 1), stroke=ACCENT, lw=0.6, dash=(3, 2))
    # wall girders
    v.rect(X_WALL_W, Y_WALL_N, 158.5, Y_WALL_N + 1.5, fill=NEW, stroke=None)
    v.rect(X_WALL_W, Y_WALL_N, X_WALL_W + 1.5, 302.5, fill=NEW, stroke=None)    # one spliced girder, full length
    for kind, x0, y0, x1, y1, _, _ in members():
        fill, lw = STYLE[kind]
        v.rect(x0, y0, x1, y1, fill=fill, stroke=None if kind in ("girder", "frame") else black, lw=lw)
    for x, y in SW_LEGS:
        v.rect(x - 1.75, y - 0.75, x + 1.75, y + 0.75, fill=Color(0.35, 0.35, 0.40), stroke=black, lw=0.3)
    for x in N_FRAMES:
        v.rect(x - 0.75, NG[1] - 0.75, x + 0.75, NG[1] + 2.75, fill=Color(0.35, 0.35, 0.40), stroke=black, lw=0.3)
    for y in W_FRAMES:
        v.rect(WG[0] - 0.75, y - 0.75, WG[1] + 1.25, y + 0.75, fill=Color(0.35, 0.35, 0.40), stroke=black, lw=0.3)
    for x in H_FRAMES:
        for y in (H_A[0] - 1.0, H_C[1] + 1.0):
            v.rect(x - 0.75, y - 1.75, x + 0.75, y + 1.75, fill=Color(0.35, 0.35, 0.40), stroke=black, lw=0.3)
    v.text(83, NG[1] + 3.5, "NORTH FRONT GIRDER (set back)", size=6, color=NEW, anchor="c", bold=True)
    c.saveState()
    a, b = v.p(X_W_EDGE + 3.0, 140)
    c.translate(a, b)
    c.rotate(-90)
    c.setFillColor(NEW)
    c.setFont("Helvetica-Bold", 6)
    c.drawCentredString(0, 0, "WEST FRONT GIRDER")
    c.restoreState()
    v.text(HC[0], HC[1] + 1.0, "HATCH 36 x 24", size=6, color=ACCENT, anchor="c", bold=True)
    v.text(HC[0], H_A[0] - 2.0, "girder A", size=5.5, color=GREY, anchor="c")
    v.text(66, H_B[1] + 3.0, "girder B", size=5.5, color=GREY, anchor="c")
    v.text(HC[0], H_C[1] + 3.5, "girder C (free)", size=5.5, color=GREY, anchor="c")
    v.text(186, 90, "CLOSET: 8 in EAST SHELF", size=6, color=CLOSETC, anchor="c", bold=True)
    v.text(186, 94.5, "+ 2 alcove boxes", size=5.5, color=CLOSETC, anchor="c")
    v.text(64, 233.4, "SW BOX: open middle", size=6, color=GREY, anchor="c", bold=True)
    v.text(64, 238.0, "4 lower girders on 2 leg frames", size=5.5, color=GREY, anchor="c")

    lx, ly = 498, PH - 86
    rows = [(NEW, "L-girder, 1x4 web + 1x2 flange (wall, front, SW, helix)"), (WOOD_DK, "1x3 joist, ~16 in o.c."),
            (Color(0.35, 0.35, 0.40), "2x4 leg / 1x4 leg-frame joist"), (Color(0.55, 0.40, 0.25),
            "2x4 hatch frame"), (CLOSETC, "Closet 1x3 boxes (shelf + alcoves)")]
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(black)
    c.drawString(lx, ly, "LEGEND")
    for i, (col, s) in enumerate(rows):
        y = ly - 14 - i * 12
        c.setFillColor(col)
        c.rect(lx, y, 10, 6, stroke=1, fill=1)
        c.setFillColor(black)
        c.setFont("Helvetica", 7.5)
        c.drawString(lx + 16, y, s)
    notes = [
        "Deck top -15, 3/4 ply on 1x3 joists sitting straight on the girder flanges (flange top -18.22). Same "
        "outlines and seams as the 0 in level, so the joist stations on the wall runs are the main level's.",
        "Legs: 2x4 legs under a 1x4 joist that carries the girders, 1x2 diagonals on every leg. Two frames on "
        "the north run and two on the west run (wall girder to front girder); two on the SW box, under the west "
        "and east straights, each carrying all four lower girders.",
        "SW box: upper girders (y 218-1/2, 248-1/2) carry the main "
        "level; the lower inner pair sits under them, the outer pair 10 in further out. Deck: two 18 in "
        "straights and a solid bullnose round the tip; the middle is open.",
        "Helix peninsula: girders A and B come off the closet wall on the neck edges and run to the bulb's west "
        "edge; B is cut out at the hatch. C is free, halfway to the south edge. A 2x4 + 1x4 leg frame carries all "
        "three at each end.",
        "Closet: a long, narrow 8 in shelf on the east wall, full length, and a separate rectangle in each "
        "alcove from the wall opening to the shelf. Each is a 1x3 box on edge, cross pieces about 14 in o.c. "
        "Straight deck edges; the desk sits under the shelf.",
    ]
    verify = [
        "North front girder line (drawn set back to y 65, like the main level).",
        "SW strip girder inset (drawn 6 in in from the strip edge, x 15 to 16-1/2).",
        "Leg frame positions: north run x 55, 115; west run y 110, 165; SW box x 30, 76; helix x 66, 121.",
        "Hatch size and position (placeholder 36 x 24 on the helix centre); girder y positions A, B, C.",
        "SW girder ends (drawn to x 100) and how the west front girder meets the SW box girders.",
        "FG / GG / bullnose seam lines (drawn at the loop centre, x 78.8); the 6 in tongues through the wall "
        "openings (drawn where the main level's are).",
        "Closet: shelf depth (drawn 8 in) and alcove rectangles (drawn 17-1/2 in deep, opening to the shelf).",
    ]
    y = ly - 14 - len(rows) * 12 - 16
    for title, items, bullet in (("NOTES", notes, ""), ("TO VERIFY ON SITE", verify, "- ")):
        c.setFillColor(black if title == "NOTES" else ACCENT)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(lx, y, title)
        c.setFont("Helvetica", 7.2)
        y -= 12
        for s in items:
            for ln in simpleSplit(bullet + s, "Helvetica", 7.2, 256):
                c.drawString(lx, y, ln)
                y -= 9
            y -= 3
        y -= 8
    footer_note(c, ["Room inches: x east from the west wall corner, y south from the north wall line (same as the "
                    "main level). Plan about 1:39."], y=22, size=7)


# ---------------------------------------------------------------- sheet 2
def girder_cut(v, x0, web_side="l", dash=None, fill=WOOD):
    """1x4 + 1x2 L-girder cut across, flange x0..x0+1.5, web under the given half."""
    v.rect(x0, G_FL_BOT, x0 + 1.5, G_FL_TOP, xcut=dash is None, fill=fill, dash=dash)
    wx = x0 if web_side == "l" else x0 + 0.75
    v.rect(wx, G_WEB_BOT, wx + 0.75, G_FL_BOT, xcut=dash is None, fill=fill, dash=dash)


def sheet_sections(c):
    header(c, "Staging level sections", "A: wall run (west).  B: SW box, north-south at x 60.  "
           "C: helix peninsula, north-south through the hatch.", 2, PAGES, level="staging level")

    # A: wall run, 1:8
    a = View(c, ox=50, oy=500, scale=10, xref=-2.0, yref=-12.0)
    a.text(-2.0, -12.0, "A   WALL RUN (WEST)   1:10", size=9, bold=True, dy=4)
    a.rect(-2.0, -32.0, 0, -12.5, fill=WALL, lw=0.5)
    ply(a, 0.125, 24.0, TOP, PLY)
    a.rect(0.125, J_BOT, 24.0, J_TOP, fill=WOOD)
    girder_cut(a, 0.0, "l")
    girder_cut(a, 16.5, "l")
    a.rect(0.0, G_WEB_BOT - 3.5, 19.5, G_WEB_BOT, fill=Color(0.85, 0.85, 0.88), dash=(2, 2), lw=0.5)
    a.rect(16.0, -32.0, 19.5, G_WEB_BOT - 3.5, fill=Color(0.85, 0.85, 0.88), dash=(2, 2), lw=0.5)
    a.line(16.0, -31.0, 6.0, G_WEB_BOT - 3.5, lw=0.8, color=GREY, dash=(3, 2))
    for xc in (5.0, 10.0, 15.0, 20.0):
        track(a, xc, TOP)
    a.leader(12, (J_TOP + J_BOT) / 2, 6, -34.5, "1x3 joist on edge, ~16 in o.c.,\nstraight on both flanges")
    a.leader(0.4, -20.5, 3.0, -38.0, "wall L-girder, 1x4 web + 1x2 flange", color=GREY)
    a.leader(17.6, -19.5, 25.0, -24.0, "front L-girder, inset\n6 in, web on the wall\nside like the wall girder")
    a.dim_h(TOP + 1.6, 18.0, 24.0, "6")
    a.leader(18.0, -29.0, 25.0, -29.5, "leg frame (beyond): 1x4 joist\nunder both girders, 2x4 leg,\n1x2 diagonal")
    a.dim_v(-1.0, TOP, J_BOT, f"{TOP - J_BOT:.2f}", side="l")

    # B: SW box, y across the page (north on the left), 1:8
    b = View(c, ox=320, oy=520, scale=12, xref=199.0, yref=1.0)
    b.text(199.0, 1.0, "B   SW BOX, NORTH-SOUTH AT x 60   1:12", size=9, bold=True, dy=4)
    for y0, y1 in deck_runs(SW_DECK, 60.0):
        ply(b, y0, y1, TOP, PLY)
    for y0, y1 in deck_runs(SW_DECK, 60.0):
        jy0 = max(y0, ml.Y_RIM + 0.375)
        jy1 = max(y1, SW_N_IN[1]) if y1 < LOOP_C[1] else y1
        jy0 = min(jy0, SW_S_IN[0]) if jy0 > LOOP_C[1] else jy0
        b.rect(jy0, J_BOT, jy1, J_TOP, fill=WOOD)
    for g, side in ((SW_N_OUT, "l"), (SW_N_IN, "l"), (SW_S_IN, "r"), (SW_S_OUT, "r")):
        girder_cut(b, g[0], side)
    for g in (ml.PG_N, ml.PG_S):              # main-level upper girders (reference)
        b.rect(g[0], MAIN_FL_TOP - 0.75, g[1], MAIN_FL_TOP, fill=Color(0.9, 0.9, 0.9), dash=(2, 2), lw=0.5)
        b.rect(g[0], MAIN_FL_TOP - 4.25, g[0] + 0.75, MAIN_FL_TOP - 0.75, fill=Color(0.9, 0.9, 0.9), dash=(2, 2),
               lw=0.5)
    b.text(233.5, -2.4, "main level (reference)", size=6, color=GREY, anchor="c")
    for g in (SW_N_OUT, SW_S_OUT):
        yc = sum(g) / 2
        b.rect(yc - 1.75, -32.0, yc + 1.75, G_WEB_BOT - 3.5, fill=Color(0.85, 0.85, 0.88), dash=(2, 2), lw=0.5)
    b.line(SW_N_OUT[0] - 1.5, -30.0, SW_N_IN[1] + 6.0, G_WEB_BOT - 3.5, lw=0.6, color=GREY, dash=(3, 2))
    b.dim_h(TOP + 1.6, 200.5, 218.4, "18")
    b.dim_h(TOP + 1.6, 248.4, 266.5, "18")
    b.text(233.4, TOP - 1.2, "open", size=7, color=GREY, anchor="c")
    b.leader(sum(SW_N_OUT) / 2, -21.0, 205.0, -27.0, "outer lower girder", color=black)
    b.leader(sum(SW_N_IN) / 2, -21.0, 222.0, -24.0, "inner lower girder, under\nthe upper girder", color=black)
    b.leader(sum(ml.PG_N) / 2, -5.0, 223.0, -8.0, "upper girder (main level, -3.25)", color=GREY)
    b.rect(SW_N_OUT[0] - 1.0, G_WEB_BOT - 3.5, SW_S_OUT[1] + 1.0, G_WEB_BOT, fill=Color(0.85, 0.85, 0.88),
           dash=(2, 2), lw=0.5)
    b.text(SW_S_OUT[1] + 2.5, -33.8, "leg frame (beyond): 1x4 joist under all four girders,", size=6.5, color=GREY,
           anchor="r")
    b.text(SW_S_OUT[1] + 2.5, -35.1, "2x4 legs, 1x2 diagonals", size=6.5, color=GREY, anchor="r")

    # C: helix peninsula through the hatch, 1:10
    k = View(c, ox=60, oy=250, scale=10, xref=95.0, yref=-12.0)
    k.text(95.0, -12.0, "C   HELIX PENINSULA, NORTH-SOUTH AT x 92 (THROUGH THE HATCH)   1:10", size=9, bold=True,
           dy=4)
    hx0, hy0, hx1, hy1 = HATCH_FR.bounds
    for y0, y1 in deck_runs(PEN.difference(HATCH), HC[0]):
        ply(k, y0, y1, TOP, PLY)
        k.rect(y0, J_BOT, y1, J_TOP, fill=WOOD)
    for y0 in (hy0, hy1 - 1.5):
        k.rect(y0, J_TOP - 3.5, y0 + 1.5, J_TOP, fill=Color(0.80, 0.66, 0.45), xcut=True)
    girder_cut(k, H_A[0], "l")
    girder_cut(k, H_B[0], "r", dash=(2, 2), fill=Color(0.95, 0.95, 0.95))
    girder_cut(k, H_C[0], "r")
    k.rect(H_A[0] - 1.0, G_WEB_BOT - 3.5, H_C[1] + 1.0, G_WEB_BOT, fill=Color(0.85, 0.85, 0.88), dash=(2, 2), lw=0.5)
    k.text(HC[1], TOP - 1.0, "hatch 24", size=7, color=ACCENT, anchor="c")
    k.leader(H_B[0] + 0.7, -20.0, 140.0, -18.0, "girder B, cut out at the hatch (beyond)", color=GREY)
    k.leader(hy1 - 0.75, J_TOP - 2.0, 150.0, -13.0, "2x4 hatch frame", color=black)
    k.leader(130.0, G_WEB_BOT - 1.8, 150.0, -27.5, "leg frame at each end (beyond):\n1x4 under all three "
             "girders, 2x4 legs, 1x2 diagonals", color=GREY)
    k.leader(H_A[0] + 0.4, -21.0, 100.0, -27.5, "girder A", color=black)
    k.leader(H_C[0] + 1.0, -21.0, 159.0, -21.0, "girder C (free)", color=black)

    footer_note(c, ["Elevations: deck top -15.00; joist top -15.72, bottom -18.22 = girder flange top; web bottom "
                    "-22.47. Floor not measured. Dashed grey = main level, legs and parts beyond the cut."],
                y=22, size=7)


# ---------------------------------------------------------------- sheet 3
def sheet_ply(c):
    header(c, "Staging level plywood pieces (3/4)", "As the 0 in level except the SW box, the closet "
           "pieces (B2a/B3a through the wall, the 8 in shelf B4).", 3, PAGES, level="staging level")
    v = PlanView(c, ox=40, oy=PH - 74, k=1.86, x0=0.0, y0=43.0)
    v.geom(WALLS, fill=WALL, stroke=GREY, lw=0.4)
    cols = [Color(0.96, 0.90, 0.76), Color(0.90, 0.94, 0.82), Color(0.86, 0.91, 0.96), Color(0.97, 0.86, 0.82)]
    rows = []
    for i, (pid, g, name, note) in enumerate(pieces()):
        v.geom(g, fill=cols[i % len(cols)], stroke=black, lw=0.6)
        pt = g.representative_point()
        v.text(pt.x, pt.y, pid, size=7, bold=True, anchor="c", dy=-2)
        x0, y0, x1, y1 = g.bounds
        rows.append((pid, name, f"{frac(x1 - x0)} x {frac(y1 - y0)}", note))
    v.geom(pieces.fill, fill=Color(0.88, 0.88, 0.88), stroke=GREY, lw=0.4, dash=(2, 1.5))
    v.text(152.0, 141.0, "grey: fill with scrap / foam", size=5.5, color=GREY)
    v.geom(HATCH, fill=Color(1, 1, 1), stroke=ACCENT, lw=0.6, dash=(3, 2))
    tx, ty = 500, PH - 90
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(tx, ty, "PIECE  /  WHERE  /  BOUNDING (E-W x N-S)")
    c.setFont("Helvetica", 7.2)
    for i, (pid, name, size, note) in enumerate(rows):
        y = ty - 16 - i * 21
        c.setFillColor(black)
        c.drawString(tx, y, pid)
        c.drawString(tx + 30, y, name)
        c.drawRightString(PW - 40, y, size)
        c.setFillColor(GREY)
        c.drawString(tx + 30, y - 9, note)
    footer_note(c, ["Pieces mirror the main-level cut plan; edges are the AnyRail outlines. Dashed red = hatch. "
                    "Sizes are bounding boxes, not cut dimensions."], y=22, size=7)


def main():
    c = canvas.Canvas(OUT, pagesize=(PW, PH))
    c.setTitle("HART staging level - framing")
    for f in (sheet_plan, sheet_sections, sheet_ply):
        f(c)
        c.showPage()
    c.save()
    print(OUT)


if __name__ == "__main__":
    main()
