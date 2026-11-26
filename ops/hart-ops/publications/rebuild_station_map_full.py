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

import sys
from pathlib import Path
from typing import NamedTuple

from PIL import Image, ImageDraw, ImageFont

PUB = Path(__file__).resolve().parent
sys.path.insert(0, str(PUB))

import crew_master  # noqa: E402
from rebuild_local_station_maps import (  # noqa: E402
    ARIAL_BOLD,
    BG,
    GEORGIA,
    GEORGIA_BOLD,
    SWNUM,
    _color_chip,
    _dot,
    _font,
    _label,
    _line,
    _sw_badge,
)
from local_station_maps.east_end import TRACK_INDUSTRIES  # noqa: E402
from local_station_maps.kit import Point  # noqa: E402

OUT = PUB / "assets" / "station_map_full.png"

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


class Fonts(NamedTuple):
    track: ImageFont.FreeTypeFont  # track names
    cp: ImageFont.FreeTypeFont  # control points
    sw: ImageFont.FreeTypeFont  # switch pills
    et: ImageFont.FreeTypeFont  # engine house tracks
    ind: ImageFont.FreeTypeFont  # industries
    spot: ImageFont.FreeTypeFont  # spot numbers
    note: ImageFont.FreeTypeFont  # off-map destinations


def load_fonts() -> Fonts:
    """The map's fonts, loaded when the map is drawn rather than on import."""
    return Fonts(
        track=_font(ARIAL_BOLD, 24),
        cp=_font(ARIAL_BOLD, 38),
        sw=_font(ARIAL_BOLD, 20),
        et=_font(ARIAL_BOLD, 18),
        ind=_font(GEORGIA_BOLD, 28),
        spot=_font(GEORGIA, 17),
        note=_font(GEORGIA, 19),
    )


def barn_crossover(sw9_x: float, row_top: float, row_bot: float) -> tuple[Point, Point]:
    """Switch 7's crossover from the West Lead down to Main East: 45 degrees like switch 23,
    placed so its Main East end (the dot over the Barn label) sits under switch 9."""
    return (sw9_x - (row_bot - row_top), row_top), (sw9_x, row_bot)


EH_RUN = 132  # EH-3 between switches 9 and 11 (half its first length)


def engine_lead(sw9_x: float, lead_y: float, eh: dict[int, float]) -> tuple[Point, Point, Point, Point]:
    """The engine house ladder: switch 13 on the West Lead, its 45 degree line up through 11 to EH-1
    (parallel with switch 7), and switch 9's 45 degree line up to EH-2. Returns the points
    sw13, sw11, EH-1 join, EH-2 join."""

    def up_left(p: Point, y: float) -> Point:
        return (p[0] - (p[1] - y), y)

    sw13 = (sw9_x + EH_RUN + (lead_y - eh[3]), lead_y)
    return sw13, up_left(sw13, eh[3]), up_left(sw13, eh[1]), up_left((sw9_x, eh[3]), eh[2])


class Anchors(NamedTuple):
    """The x positions the map is built on, west to east."""

    x_stub: float  # west ends of W-1 and W-2
    x101: float
    xb: float  # Brick
    takeoff_x: float
    x103: float
    turn_x: float  # Main East leaves its high row
    x110: float
    x112: float
    xp: float  # Princess
    t115x: float
    x_end: float  # east end of K-1 and K-2
    x_vert: float  # Shenango octagon east side
    x_tr: float  # where its corner cuts start


S_LEG, VERT = 75, 60  # Brick lead: down-left, down, down-right to Plane
CORNER = 90  # Shenango octagon corner cut
CHIP = 28
ME_HI = W0 + G  # Main East's high row, west of the yard


def anchors() -> Anchors:
    x101 = 440
    xb = x101 + 150
    takeoff_x = xb + 740
    x103 = takeoff_x + 200
    x110 = x103 + 900
    x112 = x110 + 150
    xp = x112 + 200 + P_GAP
    x_vert = xp + 804
    return Anchors(
        x_stub=40,
        x101=x101,
        xb=xb,
        takeoff_x=takeoff_x,
        x103=x103,
        turn_x=x103 - 120,
        x110=x110,
        x112=x112,
        xp=xp,
        t115x=xp + 150,
        x_end=xp + 564,
        x_vert=x_vert,
        x_tr=x_vert - CORNER,
    )


class _Pen:
    """The map's drawing calls at its rail width, dot size and fonts."""

    def __init__(self, d: ImageDraw.ImageDraw, fonts: Fonts) -> None:
        self.d = d
        self.fonts = fonts

    def line(self, a: Point, b: Point) -> None:
        _line(self.d, a, b, w=LW)

    def dot(self, p: Point) -> None:
        _dot(self.d, p, r=DOT_R)

    def lab(self, p: Point, text: str, font: ImageFont.FreeTypeFont, anchor: str = "mm") -> None:
        _label(self.d, p, text, font, anchor=anchor)

    def badge(self, p: Point, text: str) -> None:
        _sw_badge(self.d, p, text, self.fonts.sw)


def _draw_west_yard(pen: _Pen, a: Anchors) -> None:
    """Main West the full width with W-1 / W-2, Brick, the lead to Plane; West Lead and the high Main East."""
    f = pen.fonts
    plane = (a.xb, Y0 + 2 * S_LEG + VERT)
    if plane[1] != W0:
        raise ValueError(f"the Brick lead ends at y {plane[1]}, not on the West Lead row {W0}")
    p1 = (a.xb - S_LEG, Y0 + S_LEG)
    p2 = (p1[0], p1[1] + VERT)
    t101 = (a.x101, Y0)
    w2c = (a.x101 - S_LEG, Y0 + S_LEG)

    pen.line((a.x_stub, Y0), (a.x_end, Y0))
    pen.line(t101, w2c)
    pen.line((a.x_stub, w2c[1]), w2c)
    stub_mid = (a.x_stub + w2c[0]) / 2
    pen.lab((stub_mid, Y0 - 18), "W-1", f.track)
    pen.lab((stub_mid, w2c[1] + 20), "W-2", f.track, "mt")
    pen.dot(t101)
    pen.badge((a.x101 - 56, Y0 - 44), str(SWNUM[101]))
    pen.dot((a.xb, Y0))
    pen.badge((a.xb + 56, Y0 - 44), str(SWNUM[100]))
    pen.lab((a.xb + 28, Y0 + 56), "Brick", f.cp)

    pen.line((a.xb, Y0), p1)
    pen.line(p1, p2)
    pen.line(p2, plane)
    pen.dot(plane)
    pen.lab((plane[0] - 60, plane[1]), "Plane", f.cp, "rm")
    pen.badge((plane[0] + 56, plane[1] - 44), str(SWNUM[102]))

    # West Lead (S-R) runs east from Plane and jogs up 45 degrees between 13 and 103, so the
    # yard sits close under Main West; Main East drops one row and runs east.
    me_corner = (a.xb + (ME_HI - W0), ME_HI)
    xj0 = a.takeoff_x + 40
    xj1 = xj0 + (W0 - S[0])
    pen.line(plane, (xj0, W0))
    pen.line((xj0, W0), (xj1, S[0]))
    pen.line((xj1, S[0]), (a.x110, S[0]))  # S-R to 110
    pen.line((a.x110, S[0]), (a.x112, S[0]))  # S-R links 110 to 112
    pen.line(plane, me_corner)
    pen.line(me_corner, (a.turn_x, ME_HI))
    pen.lab((a.xb + 150, W0 - 18), "West Lead", f.track)
    pen.lab((a.xb + 205, ME_HI - 18), "Main East", f.track)


def _draw_barn(pen: _Pen, a: Anchors) -> None:
    """Switch 7's crossover, the engine house ladder 13 / 11 / 9 and EH-1 to EH-3."""
    sw9_x = a.takeoff_x - 300
    sw7_top, sw7_bot = barn_crossover(sw9_x, W0, ME_HI)
    sw7_mid = ((sw7_top[0] + sw7_bot[0]) / 2, (sw7_top[1] + sw7_bot[1]) / 2)
    pen.line(sw7_top, sw7_bot)
    for p in (sw7_top, sw7_mid, sw7_bot):
        pen.dot(p)
    pen.badge((sw7_mid[0] - 50, sw7_mid[1]), "7")
    pen.lab((sw7_bot[0], ME_HI + 52), "Barn", pen.fonts.cp)

    eh = {3: W0 - 70, 2: W0 - 112, 1: W0 - 154}
    x_eh = a.xb + 140
    sw9 = (sw9_x, eh[3])
    sw13, sw11, eh1_join, eh2_join = engine_lead(sw9_x, W0, eh)
    pen.line((x_eh, eh[1]), eh1_join)
    pen.line((x_eh, eh[2]), eh2_join)
    pen.line((x_eh, eh[3]), sw11)
    pen.line(sw13, eh1_join)
    pen.line(eh2_join, sw9)
    for p in (sw13, sw11, sw9):
        pen.dot(p)
    pen.badge((sw13[0] + 50, W0 - 34), "13")  # east of the dot, clear of the 45 degree line
    pen.badge((sw11[0] + 56, sw11[1] - 30), "11")
    pen.badge((sw9[0] + 56, sw9[1] - 30), "9")
    for n in (1, 2, 3):
        pen.lab((x_eh + 70, eh[n] - 14), f"EH-{n}", pen.fonts.et, "lm")


class _Ladder(NamedTuple):
    top: Point
    bot: Point

    def x_at(self, y: float) -> float:
        return self.top[0] + (self.bot[0] - self.top[0]) * (y - self.top[1]) / (self.bot[1] - self.top[1])


def _draw_ladder(pen: _Pen, ladder: _Ladder, switches: tuple[int, ...], badge_dx: float) -> None:
    """A yard ladder with a dot and a switch pill on S-R and S-1 … S-3."""
    pen.line(ladder.top, ladder.bot)
    for num, y in zip(switches, S[:4], strict=True):
        pen.dot((ladder.x_at(y), y))
        pen.badge((ladder.x_at(y) + badge_dx, y - 28), str(SWNUM[num]))


def _draw_sw111(pen: _Pen, a: Anchors) -> None:
    """23 (111): Main West ↔ S-R at 45 degrees, the mirror of 35."""
    x111 = a.x110 - 260
    sw111_top = (x111, Y0)
    sw111_bot = (x111 + (S[0] - Y0), S[0])
    pen.line(sw111_top, sw111_bot)
    pen.dot(sw111_top)
    pen.dot(sw111_bot)
    mid111 = (x111 + (S[0] - Y0) * 0.5, (Y0 + S[0]) / 2)
    pen.dot(mid111)
    pen.badge((mid111[0] - 60, mid111[1]), str(SWNUM[111]))


def _industry_parts() -> list[tuple[str, list[tuple[str, str]], str]]:
    """(track, [(fill, industry)], loads) per East End industry track, names and fills from the crew master."""
    swatch = crew_master.swatches(crew_master.load())
    return [(track, [(swatch[c].fill, swatch[c].dest) for c in ids], loads) for track, ids, loads in TRACK_INDUSTRIES]


def _draw_yard_tracks(pen: _Pen, a: Anchors, west: _Ladder, east: _Ladder) -> None:
    """S-R's name, then S-1 … S-4 between the ladders, each with its industries right-justified and loads."""
    d, f = pen.d, pen.fonts
    pen.lab((a.x103 + 100, S[0] - 18), "Track S-R", f.track, "lm")
    sep, gap = " · ", 8
    for i, (name, parts, spots) in enumerate(_industry_parts(), start=1):
        y = S[i]
        xs, xe = west.x_at(y), east.x_at(y)
        pen.line((xs, y), (xe, y))
        pen.lab((xs + 84, y - 18), name, f.track, "lm")
        # Industry label: name then chip, joined by " · " when there are two.
        widths = [d.textlength(n, font=f.ind) + gap + CHIP for _, n in parts]
        sep_w = d.textlength(sep, font=f.ind) + 14
        total = sum(widths) + sep_w * (len(parts) - 1)
        right = xe - 70  # right-justified, clear of the switch pill
        x = right - total
        ly = y - 20
        for j, (hexfill, nm) in enumerate(parts):
            pen.lab((x, ly), nm, f.ind, "lm")
            x += d.textlength(nm, font=f.ind) + gap
            _color_chip(d, (x + CHIP / 2, ly), hexfill, size=CHIP)
            x += CHIP
            if j < len(parts) - 1:
                pen.lab((x, ly), sep, f.ind, "lm")
                x += sep_w
        pen.lab((right, y + 16), spots, f.spot, "rm")


def _draw_main_east_low(pen: _Pen, a: Anchors, me_foot: Point) -> None:
    """Main East under the yard, rising to S-R at 112, then east to Princess beside Main West."""
    f = pen.fonts
    me_turn_x = a.x112 - (ME_LOW - S[0]) * K
    pen.line(me_foot, (me_turn_x, ME_LOW))
    pen.line((me_turn_x, ME_LOW), (a.x112, S[0]))
    pen.dot((a.x112, S[0]))
    pen.badge((a.x112 - 36, S[0] - 28), str(SWNUM[112]))
    pen.lab(((me_foot[0] + me_turn_x) / 2, ME_LOW - 18), "Main East", f.track)

    pen.line((a.x112, Y0 + P_GAP), (a.x_end, Y0 + P_GAP))
    pen.lab((a.x112 + 120, S[0] - 18), "Main East", f.track)
    # Main West names along the top.
    pen.lab((a.xb + 470, Y0 - 18), "Main West", f.track)
    pen.lab(((a.x103 + a.x110) / 2, Y0 - 18), "Main West", f.track)
    pen.lab((a.xp - 330, Y0 - 18), "Main West", f.track)


def _draw_shenango(pen: _Pen, a: Anchors) -> None:
    """Princess (113), the 115 / 114 legs to the open octagon, K-1 / K-2, the coke works and the two yards."""
    d, f = pen.d, pen.fonts
    y2 = Y0 + P_GAP
    princess = (a.xp, Y0)
    t113 = (a.xp - P_GAP, y2)
    mid113 = ((princess[0] + t113[0]) / 2, (princess[1] + t113[1]) / 2)
    pen.line(princess, t113)
    pen.dot(princess)
    pen.dot(mid113)
    pen.dot(t113)
    pen.lab((mid113[0], Y0 - 48), "Princess", f.cp)
    pen.badge((mid113[0] + 46, mid113[1] + 4), str(SWNUM[113]))

    y_top = Y0 - 100
    y_bot = y2 + 100
    up115 = (a.t115x + 110, y_top)
    dn114 = (a.t115x + 110, y_bot)
    pen.line((a.t115x, Y0), up115)
    pen.line(up115, (a.x_tr, y_top))
    top_r = (a.x_vert, y_top + CORNER)
    bot_r = (a.x_vert, y_bot - CORNER)
    pen.line((a.x_tr, y_top), top_r)
    pen.line((a.t115x, y2), dn114)
    pen.line(dn114, (a.x_tr, y_bot))
    pen.line((a.x_tr, y_bot), bot_r)
    pen.line(top_r, bot_r)
    pen.dot((a.t115x, Y0))
    pen.dot((a.t115x, y2))
    pen.badge((a.t115x - 48, Y0 - 28), str(SWNUM[115]))
    pen.badge((a.t115x - 48, y2 + 28), str(SWNUM[114]))

    k_x = (a.t115x + a.x_end) / 2
    pen.lab((k_x, Y0 - 18), "Track K-1", f.track)
    pen.lab((k_x, y2 + 18), "Track K-2", f.track)
    ind_y = (Y0 + y2) / 2
    tl = k_x - d.textlength("Track K-1", font=f.track) / 2
    _color_chip(d, (tl - CHIP / 2 - 10, ind_y), "000000", size=CHIP)
    pen.lab((tl, ind_y), "Shenango Coke Works", f.ind, "lm")
    pen.lab(((up115[0] + a.x_tr) / 2, y_top - 22), "McKee's Rocks / Scully Yard", f.note)
    pen.lab(((dn114[0] + a.x_tr) / 2, y_bot + 22), "McKeesport / Demmler Yard", f.note)


def draw() -> Image.Image:
    """The whole map, west to east: West Yard, Barn, the two ladders and the yard, Main East, Shenango."""
    a = anchors()
    img = Image.new("RGB", (int(a.x_vert + 70), int(ME_LOW + 110)), BG)
    pen = _Pen(ImageDraw.Draw(img), load_fonts())
    _draw_west_yard(pen, a)
    _draw_barn(pen, a)
    # South Yard ladder 103-106 runs down-right; Main East goes down its west side.
    west = _Ladder((a.x103, S[0]), (a.x103 + 4 * G * K, S[4]))
    _draw_ladder(pen, west, (103, 104, 105, 106), 36)
    me_foot = (a.turn_x + (ME_LOW - ME_HI) * K, ME_LOW)
    pen.line((a.turn_x, ME_HI), me_foot)
    # East End ladder 110-107 runs down-left.
    east = _Ladder((a.x110, S[0]), (a.x110 - 4 * G * K, S[4]))
    _draw_ladder(pen, east, (110, 109, 108, 107), -36)
    _draw_sw111(pen, a)
    _draw_yard_tracks(pen, a, west, east)
    _draw_main_east_low(pen, a, me_foot)
    _draw_shenango(pen, a)
    return img


def main() -> None:
    img = draw()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)
    print(f"{OUT} {img.size}")


if __name__ == "__main__":
    main()
