#!/usr/bin/env python3
"""Square-ish variant of station_map_full.png: two tiers joined by a hairpin.

The five area sheets (West Yard, South Yard, East End, Shenango; the Barn is
the crossover inside the yard) join end to end: Main West and Main East run
unbroken, the S-R and S-1 to S-4 yard tracks run from the South Yard ladder straight
into the East End ladder. No "to ..." notes, no compass.

Usage (from this folder):
  python3 rebuild_station_map_full_square.py
Writes assets/station_map_full_square.png
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

OUT = PUB / "assets" / "station_map_full_square.png"

LW = 4
DOT_R = 15
K = 0.24  # ladder slope, dx per dy (same as the sheets)

Y0 = 160  # Main West
R1 = 210  # Main West to S-R / West Lead
G = 100  # row pitch in the yard
S = [Y0 + R1 + i * G for i in range(5)]  # S-R, S-1 .. S-4
ME_LOW = S[4] + 70  # Main East under the yard
P_GAP = 120  # Main West to Main East at Princess

track_font = _font(ARIAL_BOLD, 24)
cp_font = _font(ARIAL_BOLD, 38)
sw_font = _font(ARIAL_BOLD, 20)
et_font = _font(ARIAL_BOLD, 18)
ind_font = _font(GEORGIA_BOLD, 28)
spot_font = _font(GEORGIA, 17)
note_font = _font(GEORGIA, 19)


def main() -> None:
    x_stub = 40
    x101 = 330
    xb = x101 + 150  # Brick
    s_leg, vert = 75, 60
    takeoff_x = xb + 640
    x103 = takeoff_x + 170
    turn_x = x103 - 120
    x110 = x103 + 760
    x112 = x110 + 150
    ts = x112 + 200
    y2 = Y0 + P_GAP
    te = ts + (S[0] - y2)
    d_ = P_GAP
    t_out, t_in = 120, 50
    xv_in = te + 160
    xv_out = xv_in + d_
    y_me2 = ME_LOW + 150  # tier 2, Main East (upper) / Main West (lower)
    y_mw2 = y_me2 + d_

    width = int(xv_out + 70)
    height = int(y_mw2 + 122 + 40)
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

    # Main West: W-1 → 101 → Brick → east, then round the hairpin
    line((x_stub, Y0), (xv_out - t_out, Y0))
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

    line((xb, Y0), p1)
    line(p1, p2)
    line(p2, plane)
    dot(plane)
    lab((plane[0] - 60, plane[1]), "Plane", cp_font, "rm")
    badge((plane[0] + 56, plane[1] - 44), "102")

    me_hi = S[1]
    me_corner = (xb + (me_hi - S[0]), me_hi)
    line(plane, (x110, S[0]))
    line((x110, S[0]), (x112, S[0]))  # S-R links 110 to 112
    line(plane, me_corner)
    line(me_corner, (turn_x, me_hi))
    lab((xb + 150, S[0] - 18), "West Lead", track_font)
    lab((xb + 205, me_hi - 18), "Main East", track_font)

    # ── Barn (SM-06): switch 7 crossover, 13 / 11 / 9, EH-1 to EH-3 ─────
    x7 = xb + 260
    sw7_top = (x7, S[0])
    sw7_bot = (x7 + (me_hi - S[0]) * 0.5, me_hi)
    sw7_mid = ((sw7_top[0] + sw7_bot[0]) / 2, (sw7_top[1] + sw7_bot[1]) / 2)
    line(sw7_top, sw7_bot)
    for p in (sw7_top, sw7_mid, sw7_bot):
        dot(p)
    badge((sw7_mid[0] - 50, sw7_mid[1]), "7")
    lab((sw7_mid[0] + 10, me_hi + 52), "Barn", cp_font)

    eh = {3: S[0] - 70, 2: S[0] - 112, 1: S[0] - 154}
    x_eh = xb + 140

    def up_left(p, y):
        return (p[0] + 0.5 * (y - p[1]), y)

    sw13 = (takeoff_x, S[0])
    sw11 = up_left(sw13, eh[3])
    eh1_join = up_left(sw13, eh[1])
    sw9 = (takeoff_x - 300, eh[3])
    eh2_join = up_left(sw9, eh[2])
    line((x_eh, eh[1]), eh1_join)
    line((x_eh, eh[2]), eh2_join)
    line((x_eh, eh[3]), sw11)
    line(sw13, eh1_join)
    line(eh2_join, sw9)
    for p in (sw13, sw11, sw9):
        dot(p)
    badge((sw13[0] - 56, S[0] - 34), "13")
    badge((sw11[0] + 56, sw11[1] - 30), "11")
    badge((sw9[0] + 56, sw9[1] - 30), "9")
    for n in (1, 2, 3):
        lab((x_eh + 70, eh[n] - 14), f"EH-{n}", et_font, "lm")

    top = (x103, S[0])
    bot = (x103 + 4 * G * K, S[4])

    def lad_w(y):
        return top[0] + (bot[0] - top[0]) * (y - top[1]) / (bot[1] - top[1])

    line(top, bot)
    for num, y in ((103, S[0]), (104, S[1]), (105, S[2]), (106, S[3])):
        dot((lad_w(y), y))
        badge((lad_w(y) + 36, y - 28), str(num))

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

    x111 = x110 - 240
    sw111_top = (x111, Y0)
    sw111_bot = (x111 + (S[0] - Y0) * K, S[0])
    line(sw111_top, sw111_bot)
    dot(sw111_top)
    dot(sw111_bot)
    mid111 = (x111 + (S[0] - Y0) * K * 0.5, (Y0 + S[0]) / 2)
    dot(mid111)
    badge((mid111[0] - 60, mid111[1]), "111")

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
        lab((xs + 56, y + 22), name, track_font, "lm")
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

    me_turn_x = x112 - (ME_LOW - S[0]) * K
    line(me_foot, (me_turn_x, ME_LOW))
    line((me_turn_x, ME_LOW), (x112, S[0]))
    dot((x112, S[0]))
    badge((x112 - 36, S[0] - 28), "112")
    lab(((me_foot[0] + me_turn_x) / 2, ME_LOW - 18), "Main East", track_font)
    lab((x112 + 110, S[0] - 18), "Main East", track_font)

    lab((xb + 470, Y0 - 18), "Main West", track_font)
    lab(((x103 + x110) / 2, Y0 - 18), "Main West", track_font)
    lab((x112 + 330, Y0 - 18), "Main West", track_font)

    # ── Hairpin: Main East (inner) and Main West (outer) turn back west ─
    line((x112, S[0]), (ts, S[0]))
    line((ts, S[0]), (te, y2))
    # Main East
    line((te, y2), (xv_in - t_in, y2))
    line((xv_in - t_in, y2), (xv_in, y2 + t_in))
    line((xv_in, y2 + t_in), (xv_in, y_me2 - t_in))
    line((xv_in, y_me2 - t_in), (xv_in - t_in, y_me2))
    # Main West
    line((xv_out - t_out, Y0), (xv_out, Y0 + t_out))
    line((xv_out, Y0 + t_out), (xv_out, y_mw2 - t_out))
    line((xv_out, y_mw2 - t_out), (xv_out - t_out, y_mw2))

    # ── Princess / Shenango on tier 2, drawn turned 180° so the labels
    #    stay upright and the loop ends up at the west end ───────────────
    c_y = y_mw2 + Y0  # page_y = c_y - local_y

    def T(p):
        return (xv_out - 120 - 300 - p[0], c_y - p[1])

    def tline(a, b):
        line(T(a), T(b))

    def tdot(p):
        dot(T(p))

    def tlab(p, text, font, anchor="mm"):
        if "l" in anchor or "r" in anchor:
            anchor = anchor.replace("l", "\x00").replace("r", "l").replace("\x00", "r")
        lab(T(p), text, font, anchor)

    def tbadge(p, text):
        badge(T(p), text)

    xp = 0.0
    t113 = (xp - P_GAP, y2)
    t115x = xp + 150
    x_end = xp + 564
    x_vert = xp + 804
    corner = 90
    x_tr = x_vert - corner
    y_top = Y0 - 100
    y_bot = y2 + 100

    tline((-300, Y0), (x_end, Y0))  # Main West → K-1
    tline((-250, y2), (x_end, y2))  # Main East → K-2

    princess = (xp, Y0)
    mid113 = ((princess[0] + t113[0]) / 2, (princess[1] + t113[1]) / 2)
    tline(princess, t113)
    tdot(princess)
    tdot(mid113)
    tdot(t113)
    tlab((mid113[0], Y0 - 48), "Princess", cp_font)
    tbadge((mid113[0] + 46, mid113[1] + 4), "113")

    up115 = (t115x + 110, y_top)
    dn114 = (t115x + 110, y_bot)
    tline((t115x, Y0), up115)
    tline(up115, (x_tr, y_top))
    top_r = (x_vert, y_top + corner)
    bot_r = (x_vert, y_bot - corner)
    tline((x_tr, y_top), top_r)
    tline((t115x, y2), dn114)
    tline(dn114, (x_tr, y_bot))
    tline((x_tr, y_bot), bot_r)
    tline(top_r, bot_r)
    tdot((t115x, Y0))
    tdot((t115x, y2))
    tbadge((t115x - 48, Y0 - 28), "115")
    tbadge((t115x - 48, y2 + 28), "114")

    k_x = (t115x + x_end) / 2
    tlab((k_x, Y0 - 18), "Track K-1", track_font)
    tlab((k_x, y2 + 18), "Track K-2", track_font)
    ind_y = (Y0 + y2) / 2
    mx, my = T((k_x, ind_y))
    tl = mx - d.textlength("Track K-1", font=track_font) / 2
    _color_chip(d, (tl - chip / 2 - 10, my), "000000", size=chip)
    lab((tl, my), "Shenango Coke Works", ind_font, "lm")
    tlab(((up115[0] + x_tr) / 2, y_top - 22), "McKee's Rocks / Scully Yard", note_font)
    tlab(((dn114[0] + x_tr) / 2, y_bot + 22), "McKeesport / Demmler Yard", note_font)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)
    print(f"{OUT} {img.size}")


if __name__ == "__main__":
    main()
