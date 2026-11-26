"""Shenango (SM-05, upright and rotated) drawer.

8×5: Princess, Main West and Main East, K-1 and K-2, switches 113–115. The LED pitch is East
End's (kit.DOT_R): the mid point of 113 is 3/8″ from each rail and Princess ↔ 115 is 3/4″.
K-1 and K-2 end at an open octagon, missing the side between 114 and 115.

meta['rotate180'] turns the track plan 180° about its centre; labels stay upright and the
compass is flipped.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from PIL import Image, ImageDraw, ImageFont

from .kit import (
    ARIAL_BOLD,
    DOT_R,
    GEORGIA,
    GEORGIA_BOLD,
    INK,
    RAIL_W,
    SHEET_H,
    SHEET_PAD,
    SHEET_W,
    STEP_1LED,
    STEP_2LED,
    Hooks,
    Point,
    RGB,
    _arrow,
    _color_chip,
    _dot,
    _label,
    _line,
    _sw_badge,
    _title,
)

TRACK_GAP = STEP_1LED / math.sqrt(2)  # 113 is a 45° diagonal one LED step long
OCT_UP = 100.0  # K-1 up to the octagon's top side
OCT_DN = 100.0  # K-2 down to the octagon's bottom side
CORNER = 90.0  # the octagon's corner cut on the east side
LABEL_PAD = 28.0
CONTENT_W = 1164.0
CONTENT_H = LABEL_PAD + OCT_UP + TRACK_GAP + OCT_DN + LABEL_PAD
CHIP_SIZE = 28


class _Fonts(NamedTuple):
    track: ImageFont.FreeTypeFont
    note: ImageFont.FreeTypeFont
    cp: ImageFont.FreeTypeFont
    ind: ImageFont.FreeTypeFont
    sw: ImageFont.FreeTypeFont


class _Layout(NamedTuple):
    """Where the Shenango rails sit, in upright plan coordinates."""

    x_left: float
    y_top: float  # octagon top side
    y1: float  # Main West, K-1
    y2: float  # Main East, K-2
    y_bot: float  # octagon bottom side
    x_end: float  # east end of the straight rails
    x_vert: float  # octagon east side
    x_tr: float  # where the octagon's corner cuts start
    centre: Point  # turning point of rotate180
    princess: Point
    t113: Point  # 113 on Main East
    mid113: Point  # 113 mid point, one 2-LED step from Princess
    t115: Point
    t114: Point
    up115: Point  # 115 leg meets the octagon top
    dn114: Point  # 114 leg meets the octagon bottom


def _layout() -> _Layout:
    x_left = (SHEET_W - CONTENT_W) / 2
    y_block = 58 + ((SHEET_H - 140 - 58) - CONTENT_H) / 2
    y_top = y_block + LABEL_PAD
    y1 = y_top + OCT_UP
    y2 = y1 + TRACK_GAP
    y_bot = y2 + OCT_DN
    x_p = x_left + 360.0
    x_vert = x_left + CONTENT_W
    princess = (x_p, y1)
    t113 = (x_p - TRACK_GAP, y2)
    ux = (t113[0] - princess[0]) / STEP_1LED
    uy = (t113[1] - princess[1]) / STEP_1LED
    t115 = (x_p + STEP_1LED, y1)
    t114 = (t115[0], y2)
    return _Layout(
        x_left=x_left,
        y_top=y_top,
        y1=y1,
        y2=y2,
        y_bot=y_bot,
        x_end=x_left + 924.0,
        x_vert=x_vert,
        x_tr=x_vert - CORNER,
        centre=(x_left + CONTENT_W / 2, y_block + CONTENT_H / 2),
        princess=princess,
        t113=t113,
        mid113=(princess[0] + ux * STEP_2LED, princess[1] + uy * STEP_2LED),
        t115=t115,
        t114=t114,
        up115=(t115[0] + 110, y_top),
        dn114=(t114[0] + 110, y_bot),
    )


class _Plan:
    """Draws in plan coordinates; with rot it turns each point 180° about centre."""

    def __init__(self, draw: ImageDraw.ImageDraw, *, rot: bool, centre: Point) -> None:
        self.draw = draw
        self.rot = rot
        self.centre = centre

    def T(self, p: Point) -> Point:
        if not self.rot:
            return p
        return (2 * self.centre[0] - p[0], 2 * self.centre[1] - p[1])

    def line(self, a: Point, b: Point) -> None:
        _line(self.draw, self.T(a), self.T(b), w=RAIL_W)

    def dot(self, p: Point) -> None:
        _dot(self.draw, self.T(p), r=DOT_R)

    def lab(self, p: Point, text: str, font: ImageFont.FreeTypeFont, *, anchor: str = "mm", fill: RGB = INK) -> None:
        # Turned 180°, the left and right anchors swap so the text stays on its side of the point.
        if self.rot:
            anchor = anchor.replace("l", "\x00").replace("r", "l").replace("\x00", "r")
        _label(self.draw, self.T(p), text, font, anchor=anchor, fill=fill)

    def badge(self, p: Point, text: str, font: ImageFont.FreeTypeFont) -> None:
        _sw_badge(self.draw, self.T(p), text, font)

    def chip(self, p: Point, hexfill: str, *, size: float = 14) -> None:
        _color_chip(self.draw, self.T(p), hexfill, size=size)


def _draw_mains(plan: _Plan, g: _Layout, fonts: _Fonts) -> None:
    """Main West and Main East, west arrows, their names, and K-1 / K-2 east of the switches."""
    plan.line((g.x_left, g.y1), (g.x_end, g.y1))
    plan.line((g.x_left, g.y2), (g.x_end, g.y2))
    # The arrows point geographic west.
    west = "right" if plan.rot else "left"
    _arrow(plan.draw, plan.T((g.x_left, g.y1)), direction=west, size=14)
    _arrow(plan.draw, plan.T((g.x_left, g.y2)), direction=west, size=14)
    main_label_x = g.x_left + 110
    plan.lab((main_label_x, g.y1 - 18), "Main West", fonts.track, anchor="mm")
    plan.lab((main_label_x, g.y2 + 18), "Main East", fonts.track, anchor="mm")
    plan.lab((g.x_left + 56, (g.y1 + g.y2) / 2), "to East End", fonts.note, anchor="lm", fill=INK)
    k_label_x = _k_label_x(g)
    plan.lab((k_label_x, g.y1 - 18), "Track K-1", fonts.track, anchor="mm")
    plan.lab((k_label_x, g.y2 + 18), "Track K-2", fonts.track, anchor="mm")


def _k_label_x(g: _Layout) -> float:
    return (g.t114[0] + g.x_end) / 2


def _draw_coke_works(plan: _Plan, g: _Layout, fonts: _Fonts) -> None:
    """Industry name between K-1 and K-2; its first letter lines up with the T of the track names."""
    ind_y = (g.y1 + g.y2) / 2
    half_track = plan.draw.textlength("Track K-1", font=fonts.track) / 2
    if plan.rot:
        # Upright text on the turned plan: placed on the page, not through plan.T.
        k_mid = plan.T((_k_label_x(g), ind_y))
        left = k_mid[0] - half_track
        _color_chip(plan.draw, (left - CHIP_SIZE / 2 - 10, k_mid[1]), "000000", size=CHIP_SIZE)
        _label(plan.draw, (left, k_mid[1]), "Shenango Coke Works", fonts.ind, anchor="lm")
    else:
        left = _k_label_x(g) - half_track
        plan.chip((left - CHIP_SIZE / 2 - 10, ind_y), "000000", size=CHIP_SIZE)
        plan.lab((left, ind_y), "Shenango Coke Works", fonts.ind, anchor="lm")


def _draw_switches_and_octagon(plan: _Plan, g: _Layout, fonts: _Fonts) -> None:
    """Destinations at the octagon, 113 at Princess, the 115 and 114 legs and the octagon sides."""
    plan.lab(((g.up115[0] + g.x_tr) / 2, g.y_top - 22), "McKee's Rocks / Scully Yard", fonts.note,
             anchor="mm", fill=INK)
    plan.lab(((g.dn114[0] + g.x_tr) / 2, g.y_bot + 22), "McKeesport / Demmler Yard", fonts.note,
             anchor="mm", fill=INK)

    plan.dot(g.princess)
    plan.line(g.princess, g.t113)
    plan.dot(g.mid113)
    plan.dot(g.t113)
    plan.lab((g.mid113[0], g.y1 - 48), "Princess", fonts.cp, anchor="mm")
    plan.badge((g.mid113[0] + 44, g.mid113[1] + 4), "35", fonts.sw)

    top_r = (g.x_vert, g.y_top + CORNER)
    plan.line(g.t115, g.up115)
    plan.line(g.up115, (g.x_tr, g.y_top))
    plan.line((g.x_tr, g.y_top), top_r)
    plan.dot(g.t115)

    bot_r = (g.x_vert, g.y_bot - CORNER)
    plan.line(g.t114, g.dn114)
    plan.line(g.dn114, (g.x_tr, g.y_bot))
    plan.line((g.x_tr, g.y_bot), bot_r)
    plan.dot(g.t114)

    plan.line(top_r, bot_r)

    # 115 and 114 badges sit outside the octagon angles, on the Princess side of each switch:
    # 115 level with K-1 (above), 114 level with K-2 (below).
    plan.badge((g.t115[0] - 48, g.y1 - 28), "39", fonts.sw)
    plan.badge((g.t114[0] - 48, g.y2 + 28), "37", fonts.sw)


def draw_shenango(meta: dict, hooks: Hooks) -> Image.Image:
    """The Shenango sheet, upright or turned 180° (meta['rotate180'])."""
    img, draw = hooks.canvas(SHEET_W, SHEET_H)
    rot = bool(meta.get("rotate180"))
    _title(draw, SHEET_W // 2, meta["title"], hooks)
    fonts = _Fonts(
        track=hooks.font(ARIAL_BOLD, 22),
        note=hooks.font(GEORGIA, 18),
        cp=hooks.font(ARIAL_BOLD, 36),
        ind=hooks.font(GEORGIA_BOLD, 28),
        sw=hooks.font(ARIAL_BOLD, 20),
    )
    g = _layout()
    plan = _Plan(draw, rot=rot, centre=g.centre)
    _draw_mains(plan, g, fonts)
    _draw_coke_works(plan, g, fonts)
    _draw_switches_and_octagon(plan, g, fonts)
    # The compass cardinals flip with the plan.
    if rot:
        hooks.paste_compass(img, cx=SHEET_W - SHEET_PAD - 115, cy=SHEET_H - 185, size=230, north="down")
    else:
        hooks.paste_compass(img, cx=SHEET_PAD + 115, cy=SHEET_H - 185, size=230, north="up")
    return img
