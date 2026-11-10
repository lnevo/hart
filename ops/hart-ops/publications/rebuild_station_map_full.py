#!/usr/bin/env python3
"""Draw the whole railroad as ONE continuous station map (west to east).

The five area sheets (West Yard, South Yard, East End, Shenango; the Barn is
the crossover inside the yard) join end to end: Main West and Main East run
unbroken, the S-1 to S-5 yard tracks run from the South Yard ladder straight
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

LW = 4
DOT_R = 15
K = 0.24  # ladder slope, dx per dy (same as the sheets)

Y0 = 160  # Main West
R1 = 210  # Main West to S-1 / West Lead
G = 120  # row pitch in the yard
S = [Y0 + R1 + i * G for i in range(5)]  # S-1 .. S-5
ME_LOW = S[4] + 85  # Main East under the yard
P_GAP = 120  # Main West to Main East at Princess

track_font = _font(ARIAL_BOLD, 24)
cp_font = _font(ARIAL_BOLD, 38)
sw_font = _font(ARIAL_BOLD, 20)
et_font = _font(ARIAL_BOLD, 18)
ind_font = _font(GEORGIA_BOLD, 28)
spot_font = _font(GEORGIA, 17)
note_font = _font(GEORGIA, 19)


def main() -> None:
    # ── x anchors ────────────────────────────────────────────────────────
    x_stub = 40
    x101 = 440
    xb = x101 + 150  # Brick
    s_leg, vert = 75, 60  # Brick lead: down-left, down, down-right to Plane
    barn_bot_x = xb + 400
    barn_top_x = barn_bot_x + 120
    takeoff_x = xb + 740
    x103 = takeoff_x + 200
    turn_x = x103 - 120  # Main East leaves its high row
    x110 = x103 + 900
    x112 = x110 + 150
    ts = x112 + 220  # taper start (Main East rises to sit beside Main West)
    te = ts + (S[0] - (Y0 + P_GAP))
    t113x = te + 100
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
    assert plane[1] == S[0], (plane, S[0])
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
    badge((x101 - 56, Y0 - 44), "101")
    dot((xb, Y0))
    badge((xb + 56, Y0 - 44), "100")
    lab((xb + 28, Y0 + 56), "Brick", cp_font)

    # Brick lead to Plane
    line((xb, Y0), p1)
    line(p1, p2)
    line(p2, plane)
    dot(plane)
    lab((plane[0] - 60, plane[1]), "Plane", cp_font, "rm")
    badge((plane[0] + 56, plane[1] - 44), "102")

    # West Lead (S-1) runs east from Plane; Main East drops one row and runs east
    me_hi = S[1]
    me_corner = (xb + (me_hi - S[0]), me_hi)
    line(plane, (x110, S[0]))  # West Lead / S-1 to 110
    line((x110, S[0]), (x112, S[0]))  # S-1 links 110 to 112
    line(plane, me_corner)
    line(me_corner, (turn_x, me_hi))
    lab((xb + 250, S[0] - 18), "West Lead", track_font)
    lab((xb + 250, me_hi - 18), "Main East", track_font)

    # Barn crossover
    line((barn_top_x, S[0]), (barn_bot_x, me_hi))
    lab((barn_bot_x + 20, me_hi + 40), "Barn", cp_font)

    # ── South Yard ───────────────────────────────────────────────────────
    # Engine terminal ladder off the West Lead
    gap = 26
    et = {3: S[0] - gap, 2: S[0] - 2 * gap, 1: S[0] - 3 * gap}

    def et_x(y):
        return takeoff_x - (S[0] - y) * K

    line((takeoff_x, S[0]), (et_x(et[1]), et[1]))
    stub_end = takeoff_x - 170
    for n in (1, 2):
        line((et_x(et[n]), et[n]), (stub_end, et[n]))
        lab((stub_end - 4, et[n]), f"ET-{n}", et_font, "rm")
    spur = (et_x(et[2]) - 12, et[2])
    et3x = spur[0] - gap
    line(spur, (et3x, et[3]))
    line((et3x, et[3]), (stub_end, et[3]))
    lab((stub_end - 4, et[3]), "ET-3", et_font, "rm")

    # Yard ladder 103-106 (down-right)
    top = (x103, S[0])
    bot = (x103 + 4 * G * K, S[4])

    def lad_w(y):
        return top[0] + (bot[0] - top[0]) * (y - top[1]) / (bot[1] - top[1])

    line(top, bot)
    for num, y in ((103, S[0]), (104, S[1]), (105, S[2]), (106, S[3])):
        dot((lad_w(y), y))
        badge((lad_w(y) + 36, y - 28), str(num))

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
        badge((lad_e(y) - 36, y - 28), str(num))

    # 111: Main West ↔ S-1
    x111 = x110 - 260
    sw111_top = (x111, Y0)
    sw111_bot = (x111 + (S[0] - Y0) * K, S[0])
    line(sw111_top, sw111_bot)
    dot(sw111_top)
    dot(sw111_bot)
    mid111 = (x111 + (S[0] - Y0) * K * 0.5, (Y0 + S[0]) / 2)
    dot(mid111)
    badge((mid111[0] - 60, mid111[1]), "111")

    # S-1 label, then yard tracks with industries
    lab((x103 + 100, S[0] - 18), "Track S-1", track_font, "lm")
    rows = [
        ("Track S-2", [("FFFF00", "Aristech Plastics")], "Pellets  ·  Chemicals  ·  Shipping"),
        ("Track S-3", [("FF0000", "Ferrellgas"), ("008000", "A. Stucki Co.")], "LPG  ·  Crane  ·  Team"),
        ("Track S-4", [("FFC0CB", "Kosmos Cement")], "Cement  ·  Aggregate"),
        ("Track S-5", [("800080", "Calgon Carbon")], "Coal  ·  Carbon  ·  Chemical"),
    ]
    chip = 28
    for i, (name, parts, spots) in enumerate(rows, start=1):
        y = S[i]
        xs, xe = lad_w(y), lad_e(y)
        line((xs, y), (xe, y))
        lab((xs + 84, y - 18), name, track_font, "lm")
        # industry label: chip + name, joined by " · " when there are two
        sep = " · "
        widths = [chip + 8 + d.textlength(n, font=ind_font) for _, n in parts]
        sep_w = d.textlength(sep, font=ind_font) + 14
        total = sum(widths) + sep_w * (len(parts) - 1)
        cx = (xs + xe) / 2 + 60
        x = cx - total / 2
        ly = y - 20
        for j, (hexfill, nm) in enumerate(parts):
            _color_chip(d, (x + chip / 2, ly), hexfill, size=chip)
            x += chip + 8
            lab((x, ly), nm, ind_font, "lm")
            x += d.textlength(nm, font=ind_font)
            if j < len(parts) - 1:
                lab((x, ly), sep, ind_font, "lm")
                x += sep_w
        lab((cx, y + 16), spots, spot_font)

    # Main East under the yard, rising at 112
    me_turn_x = x112 - (ME_LOW - S[0]) * K
    line(me_foot, (me_turn_x, ME_LOW))
    line((me_turn_x, ME_LOW), (x112, S[0]))
    dot((x112, S[0]))
    badge((x112 - 36, S[0] - 28), "112")
    lab(((me_foot[0] + me_turn_x) / 2, ME_LOW - 18), "Main East", track_font)

    # ── Princess / Shenango ──────────────────────────────────────────────
    y2 = Y0 + P_GAP
    line((x112, S[0]), (ts, S[0]))
    line((ts, S[0]), (te, y2))
    line((te, y2), (x_end, y2))
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
    badge((mid113[0] + 46, mid113[1] + 4), "113")

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
    badge((t115x - 48, Y0 - 28), "115")
    badge((t115x - 48, y2 + 28), "114")

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
