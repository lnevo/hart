#!/usr/bin/env python3
"""Draw the whole railroad as ONE continuous station map (west to east).

The five area sheets (West Yard, South Yard, East End, Shenango; the Barn is
the crossover inside the yard) join end to end: Main West and Main East run
unbroken, the S-R and S-1 to S-4 yard tracks run from the South Yard ladder straight
into the East End ladder. No "to ..." notes, no compass.

Usage (from this folder):
  python3 rebuild_station_map_full.py
Writes assets/station_map_full.png
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

PUB = Path(__file__).resolve().parent
sys.path.insert(0, str(PUB))

from rebuild_local_station_maps import (  # noqa: E402
    ARIAL_BOLD,
    BG,
    GEORGIA,
    GEORGIA_BOLD,
    INK,
    _color_chip,
    _dot,
    _font,
    _label,
    _line,
    _sw_badge,
)

OUT = PUB / "assets" / "station_map_full.png"

SWNUM = {100: 1, 101: 3, 102: 5, 103: 15, 104: 17, 105: 19, 106: 21, 107: 25, 108: 27,
         109: 29, 110: 31, 111: 23, 112: 33, 113: 35, 114: 37, 115: 39}  # ADR-005
LW = 4
DOT_R = 15
K = 0.24  # ladder slope, dx per dy (same as the sheets)

Y0 = 160  # Main West
P_GAP = 120  # Main West to the S-R / Main East row, from the jog to Princess
R1 = 210  # Main West to the West Lead at Plane
W0 = Y0 + R1  # West Lead row, west of the jog before 103
G = 120  # row pitch in the yard
S = [Y0 + P_GAP + i * G for i in range(5)]  # S-R, S-1 .. S-4 (yard, east of the jog)
ME_LOW = S[4] + 85  # Main East under the yard

track_font = _font(ARIAL_BOLD, 24)
cp_font = _font(ARIAL_BOLD, 38)
sw_font = _font(ARIAL_BOLD, 20)
et_font = _font(ARIAL_BOLD, 18)
ind_font = _font(GEORGIA_BOLD, 28)
spot_font = _font(GEORGIA, 17)
note_font = _font(GEORGIA, 19)


def barn_crossover(sw9_x: float, row_top: float, row_bot: float):
    """Switch 7's crossover from the West Lead down to Main East: 45 degrees like switch 23,
    placed so its Main East end (the dot over the Barn label) sits under switch 9."""
    return (sw9_x - (row_bot - row_top), row_top), (sw9_x, row_bot)


def main() -> None:
    # ── x anchors ────────────────────────────────────────────────────────
    x_stub = 40
    x101 = 440
    xb = x101 + 150  # Brick
    s_leg, vert = 75, 60  # Brick lead: down-left, down, down-right to Plane
    takeoff_x = xb + 740
    x103 = takeoff_x + 200
    turn_x = x103 - 120  # Main East leaves its high row
    x110 = x103 + 900
    x112 = x110 + 150
    t113x = x112 + 200
    xp = t113x + P_GAP  # Princess
    t115x = xp + 150
    x_end = xp + 564
    x_vert = xp + 804
    corner = 90
    x_tr = x_vert - corner

    width = int(x_vert + 70)
    height = int(ME_LOW + 110)
    img = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(img)

    def line(a, b):
        _line(d, a, b, w=LW)

    def dot(p):
        _dot(d, p, r=DOT_R)

    def lab(p, text, font, anchor="mm"):
        _label(d, p, text, font, anchor=anchor)

    def badge(p, text):
        _sw_badge(d, p, text, sw_font)

    # ── West Yard ────────────────────────────────────────────────────────
    plane = (xb, Y0 + 2 * s_leg + vert)
    assert plane[1] == W0, (plane, W0)
    p1 = (xb - s_leg, Y0 + s_leg)
    p2 = (p1[0], p1[1] + vert)
    t101 = (x101, Y0)
    w2c = (x101 - s_leg, Y0 + s_leg)

    # Main West: W-1 → 101 → Brick → east, all the way to the Princess loop
    line((x_stub, Y0), (x_end, Y0))
    line(t101, w2c)
    line((x_stub, w2c[1]), w2c)
    stub_mid = (x_stub + w2c[0]) / 2
    lab((stub_mid, Y0 - 18), "W-1", track_font)
    lab((stub_mid, w2c[1] + 20), "W-2", track_font, "mt")
    dot(t101)
    badge((x101 - 56, Y0 - 44), "{}".format(SWNUM[101]))
    dot((xb, Y0))
    badge((xb + 56, Y0 - 44), "{}".format(SWNUM[100]))
    lab((xb + 28, Y0 + 56), "Brick", cp_font)

    # Brick lead to Plane
    line((xb, Y0), p1)
    line(p1, p2)
    line(p2, plane)
    dot(plane)
    lab((plane[0] - 60, plane[1]), "Plane", cp_font, "rm")
    badge((plane[0] + 56, plane[1] - 44), "{}".format(SWNUM[102]))

    # West Lead (S-R) runs east from Plane; Main East drops one row and runs east
    me_hi = W0 + G
    me_corner = (xb + (me_hi - W0), me_hi)
    # West Lead jogs up 45 degrees between 13 and 103, so the yard sits close
    # under Main West and nothing downstream is stretched
    xj0 = takeoff_x + 40
    xj1 = xj0 + (W0 - S[0])
    line(plane, (xj0, W0))
    line((xj0, W0), (xj1, S[0]))
    line((xj1, S[0]), (x110, S[0]))  # S-R to 110
    line((x110, S[0]), (x112, S[0]))  # S-R links 110 to 112
    line(plane, me_corner)
    line(me_corner, (turn_x, me_hi))
    lab((xb + 150, W0 - 18), "West Lead", track_font)
    lab((xb + 205, me_hi - 18), "Main East", track_font)

    # ── Barn (SM-06): switch 7 crossover, 13 / 11 / 9, EH-1 to EH-3 ─────
    sw9_x = takeoff_x - 300
    sw7_top, sw7_bot = barn_crossover(sw9_x, W0, me_hi)
    sw7_mid = ((sw7_top[0] + sw7_bot[0]) / 2, (sw7_top[1] + sw7_bot[1]) / 2)
    line(sw7_top, sw7_bot)
    for p in (sw7_top, sw7_mid, sw7_bot):
        dot(p)
    badge((sw7_mid[0] - 50, sw7_mid[1]), "7")
    lab((sw7_bot[0], me_hi + 52), "Barn", cp_font)

    eh = {3: W0 - 70, 2: W0 - 112, 1: W0 - 154}
    x_eh = xb + 140

    def up_left(p, y):
        return (p[0] + 0.5 * (y - p[1]), y)

    sw13 = (takeoff_x, W0)
    sw11 = up_left(sw13, eh[3])
    eh1_join = up_left(sw13, eh[1])
    sw9 = (sw9_x, eh[3])
    eh2_join = up_left(sw9, eh[2])
    line((x_eh, eh[1]), eh1_join)
    line((x_eh, eh[2]), eh2_join)
    line((x_eh, eh[3]), sw11)
    line(sw13, eh1_join)
    line(eh2_join, sw9)
    for p in (sw13, sw11, sw9):
        dot(p)
    badge((sw13[0] - 56, W0 - 34), "13")
    badge((sw11[0] + 56, sw11[1] - 30), "11")
    badge((sw9[0] + 56, sw9[1] - 30), "9")
    for n in (1, 2, 3):
        lab((x_eh + 70, eh[n] - 14), f"EH-{n}", et_font, "lm")

    # Yard ladder 103-106 (down-right)
    top = (x103, S[0])
    bot = (x103 + 4 * G * K, S[4])

    def lad_w(y):
        return top[0] + (bot[0] - top[0]) * (y - top[1]) / (bot[1] - top[1])

    line(top, bot)
    for num, y in ((103, S[0]), (104, S[1]), (105, S[2]), (106, S[3])):
        dot((lad_w(y), y))
        badge((lad_w(y) + 36, y - 28), str(SWNUM[num]))

    # Main East: high row → down the west side of the ladder → under the yard
    me_foot = (turn_x + (ME_LOW - me_hi) * K, ME_LOW)
    line((turn_x, me_hi), me_foot)

    # ── East End ─────────────────────────────────────────────────────────
    etop = (x110, S[0])
    ebot = (x110 - 4 * G * K, S[4])

    def lad_e(y):
        return etop[0] + (ebot[0] - etop[0]) * (y - etop[1]) / (ebot[1] - etop[1])

    line(etop, ebot)
    for num, y in ((110, S[0]), (109, S[1]), (108, S[2]), (107, S[3])):
        dot((lad_e(y), y))
        badge((lad_e(y) - 36, y - 28), str(SWNUM[num]))

    # 23 (111): Main West ↔ S-R at 45 degrees, the mirror of 35
    x111 = x110 - 260
    sw111_top = (x111, Y0)
    sw111_bot = (x111 + (S[0] - Y0), S[0])
    line(sw111_top, sw111_bot)
    dot(sw111_top)
    dot(sw111_bot)
    mid111 = (x111 + (S[0] - Y0) * 0.5, (Y0 + S[0]) / 2)
    dot(mid111)
    badge((mid111[0] - 60, mid111[1]), "{}".format(SWNUM[111]))

    # S-R label, then yard tracks with industries
    lab((x103 + 100, S[0] - 18), "Track S-R", track_font, "lm")
    rows = [
        ("Track S-1", [("FFFF00", "Aristech Plastics")], "Pellets  ·  Chemicals  ·  Shipping"),
        ("Track S-2", [("FF0000", "Ferrellgas"), ("008000", "A. Stucki Co.")], "LPG  ·  Crane  ·  Team"),
        ("Track S-3", [("FFC0CB", "Kosmos Cement")], "Cement  ·  Aggregate"),
        ("Track S-4", [("800080", "Calgon Carbon")], "Coal  ·  Carbon  ·  Chemical"),
    ]
    chip = 28
    for i, (name, parts, spots) in enumerate(rows, start=1):
        y = S[i]
        xs, xe = lad_w(y), lad_e(y)
        line((xs, y), (xe, y))
        lab((xs + 84, y - 18), name, track_font, "lm")
        # industry label: chip + name, joined by " · " when there are two
        sep = " · "
        gap = 8
        widths = [d.textlength(n, font=ind_font) + gap + chip for _, n in parts]
        sep_w = d.textlength(sep, font=ind_font) + 14
        total = sum(widths) + sep_w * (len(parts) - 1)
        right = xe - 70  # right-justified, clear of the switch pill
        x = right - total
        ly = y - 20
        for j, (hexfill, nm) in enumerate(parts):
            lab((x, ly), nm, ind_font, "lm")
            x += d.textlength(nm, font=ind_font) + gap
            _color_chip(d, (x + chip / 2, ly), hexfill, size=chip)
            x += chip
            if j < len(parts) - 1:
                lab((x, ly), sep, ind_font, "lm")
                x += sep_w
        lab((right, y + 16), spots, spot_font, "rm")

    # Main East under the yard, rising at 112
    me_turn_x = x112 - (ME_LOW - S[0]) * K
    line(me_foot, (me_turn_x, ME_LOW))
    line((me_turn_x, ME_LOW), (x112, S[0]))
    dot((x112, S[0]))
    badge((x112 - 36, S[0] - 28), "{}".format(SWNUM[112]))
    lab(((me_foot[0] + me_turn_x) / 2, ME_LOW - 18), "Main East", track_font)

    # ── Princess / Shenango ──────────────────────────────────────────────
    y2 = Y0 + P_GAP
    line((x112, y2), (x_end, y2))
    lab((x112 + 120, S[0] - 18), "Main East", track_font)

    # Main West label stations along the top
    lab((xb + 470, Y0 - 18), "Main West", track_font)
    lab(((x103 + x110) / 2, Y0 - 18), "Main West", track_font)
    lab((xp - 330, Y0 - 18), "Main West", track_font)

    princess = (xp, Y0)
    t113 = (xp - P_GAP, y2)
    mid113 = ((princess[0] + t113[0]) / 2, (princess[1] + t113[1]) / 2)
    line(princess, t113)
    dot(princess)
    dot(mid113)
    dot(t113)
    lab((mid113[0], Y0 - 48), "Princess", cp_font)
    badge((mid113[0] + 46, mid113[1] + 4), "{}".format(SWNUM[113]))

    y_top = Y0 - 100
    y_bot = y2 + 100
    up115 = (t115x + 110, y_top)
    dn114 = (t115x + 110, y_bot)
    line((t115x, Y0), up115)
    line(up115, (x_tr, y_top))
    top_r = (x_vert, y_top + corner)
    bot_r = (x_vert, y_bot - corner)
    line((x_tr, y_top), top_r)
    line((t115x, y2), dn114)
    line(dn114, (x_tr, y_bot))
    line((x_tr, y_bot), bot_r)
    line(top_r, bot_r)
    dot((t115x, Y0))
    dot((t115x, y2))
    badge((t115x - 48, Y0 - 28), "{}".format(SWNUM[115]))
    badge((t115x - 48, y2 + 28), "{}".format(SWNUM[114]))

    k_x = (t115x + x_end) / 2
    lab((k_x, Y0 - 18), "Track K-1", track_font)
    lab((k_x, y2 + 18), "Track K-2", track_font)
    ind_y = (Y0 + y2) / 2
    tl = k_x - d.textlength("Track K-1", font=track_font) / 2
    _color_chip(d, (tl - chip / 2 - 10, ind_y), "000000", size=chip)
    lab((tl, ind_y), "Shenango Coke Works", ind_font, "lm")
    lab(((up115[0] + x_tr) / 2, y_top - 22), "McKee's Rocks / Scully Yard", note_font)
    lab(((dn114[0] + x_tr) / 2, y_bot + 22), "McKeesport / Demmler Yard", note_font)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)
    print(f"{OUT} {img.size}")


if __name__ == "__main__":
    main()
