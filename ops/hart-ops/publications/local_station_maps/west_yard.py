"""West Yard (SM-02) drawer.

8×5 landscape: Main West ↔ Brick, the W-1 and W-2 stubs, Plane. Brick and the west turnout are
3/4″ apart. W-1 is labelled above and W-2 below the stub ends. The Brick lead is one face of an
octagon: down-left (beside W-2), vertical, then down-right to Plane; Main East runs one more
down-right leg. Each leg is its own polygon stroke, so the first diagonal has no jog.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from PIL import Image, ImageDraw, ImageFont

from .kit import (
    ARIAL_BOLD,
    DOT_R,
    GEORGIA,
    INK,
    RAIL_W,
    SHEET_H,
    SHEET_PAD,
    SHEET_W,
    STEP_1LED,
    Hooks,
    Point,
    _arrow,
    _dot,
    _label,
    _line,
    _outset,
    _sw_badge,
    _title,
)

LEG = 150  # the equal 45° octagon legs
LEG_D = LEG / math.sqrt(2)  # x and y run of one leg
VERT = 110  # south face of the octagon
ABOVE_MW = 78  # switch badges and labels above Main West
BELOW_ME = 70  # labels below Main East
X_LEFT = 22  # rails run nearly to the page edges, room only for arrowheads
TIP_X = SHEET_W - 22 - 5  # east rail ends; arrows and notes sit a little inboard
BRICK_X = 920.0  # Brick and the west turnout sit near the page centre


class _Fonts(NamedTuple):
    track: ImageFont.FreeTypeFont
    note: ImageFont.FreeTypeFont
    cp: ImageFont.FreeTypeFont
    sw: ImageFont.FreeTypeFont


class _Yard(NamedTuple):
    """Where the West Yard rails sit on the sheet."""

    y_mw: float
    brick: Point
    turnout: Point  # west turnout, one LED step west of Brick
    w2_corner: Point  # W-2 leaves the turnout down-left
    p1: Point  # octagon: end of the down-left leg from Brick
    p2: Point  # octagon: foot of the vertical
    plane: Point  # end of the first down-right leg; West Lead turns east here
    me_turn: Point  # Main East turns east one leg further on


def _yard() -> _Yard:
    span = VERT + 3 * LEG_D  # Main West to Main East: down-left leg, vertical, two down-right legs
    y_mw = (SHEET_H - (ABOVE_MW + span + BELOW_ME)) / 2 + ABOVE_MW
    brick = (BRICK_X, float(y_mw))
    turnout = (brick[0] - STEP_1LED, brick[1])
    p1 = (brick[0] - LEG_D, brick[1] + LEG_D)
    p2 = (p1[0], p1[1] + VERT)
    plane = (p2[0] + LEG_D, p2[1] + LEG_D)
    return _Yard(
        y_mw=y_mw,
        brick=brick,
        turnout=turnout,
        w2_corner=(turnout[0] - LEG_D, turnout[1] + LEG_D),
        p1=p1,
        p2=p2,
        plane=plane,
        me_turn=(plane[0] + LEG_D, plane[1] + LEG_D),
    )


def _draw_main_west(draw: ImageDraw.ImageDraw, g: _Yard, fonts: _Fonts) -> None:
    """Main West from the east edge to Brick, with switch 1."""
    y = g.y_mw
    _line(draw, (g.brick[0], y), (TIP_X, y), w=RAIL_W)
    _dot(draw, g.brick, r=DOT_R)
    _sw_badge(draw, (g.brick[0] + 56, y - 44), "1", fonts.sw)
    _label(draw, (g.brick[0] + 28, y + 56), "Brick", fonts.cp, anchor="mm")
    _label(draw, ((g.brick[0] + TIP_X) / 2, y - 18), "Main West", fonts.track, anchor="mm")
    _arrow(draw, (TIP_X, y), direction="right", size=18)
    _label(draw, (TIP_X - 2, y + 34), "to East End", fonts.note, anchor="rt", fill=INK)


def _draw_stubs(draw: ImageDraw.ImageDraw, g: _Yard, fonts: _Fonts) -> None:
    """Brick → west turnout (switch 3), then the W-1 and W-2 stubs west of it."""
    y = g.y_mw
    _line(draw, g.brick, g.turnout, w=RAIL_W)
    _dot(draw, g.turnout, r=DOT_R)
    _sw_badge(draw, (g.turnout[0] - 56, y - 44), "3", fonts.sw)
    _line(draw, (X_LEFT, y), g.turnout, w=RAIL_W)
    _line(draw, g.turnout, g.w2_corner, w=RAIL_W)
    _line(draw, (X_LEFT, g.w2_corner[1]), g.w2_corner, w=RAIL_W)
    # One x for both labels, centred on the stub run.
    stub_label_x = (X_LEFT + min(g.turnout[0], g.w2_corner[0])) / 2
    _label(draw, (stub_label_x, y - 18), "W-1", fonts.track, anchor="mm")
    _label(draw, (stub_label_x, g.w2_corner[1] + 20), "W-2", fonts.track, anchor="mt")


def _draw_octagon_to_plane(draw: ImageDraw.ImageDraw, g: _Yard, fonts: _Fonts) -> None:
    """Brick down-left, vertical, down-right to Plane (switch 5)."""
    _line(draw, g.brick, g.p1, w=RAIL_W)
    _line(draw, g.p1, g.p2, w=RAIL_W)
    _line(draw, g.p2, g.plane, w=RAIL_W)
    _dot(draw, g.plane, r=DOT_R)
    _label(draw, (g.plane[0] - 60, g.plane[1]), "Plane", fonts.cp, anchor="rm")
    _sw_badge(draw, (g.plane[0] + 56, g.plane[1] - 44), "5", fonts.sw)


def _draw_lead_barn_main_east(draw: ImageDraw.ImageDraw, g: _Yard, fonts: _Fonts) -> None:
    """West Lead east from Plane to South Yard, Main East one leg further, and Barn between them."""
    y_wl, y_me = g.plane[1], g.me_turn[1]
    _line(draw, g.plane, (TIP_X, y_wl), w=RAIL_W)
    _arrow(draw, (TIP_X, y_wl), direction="right", size=18)
    _label(draw, (TIP_X - 2, y_wl - 36), "to South Yard", fonts.note, anchor="rt", fill=INK)
    # Barn runs down-left from West Lead, as on South Yard, kept 100 px clear of the east edge.
    track_label_x = (g.brick[0] + TIP_X) / 2
    barn_top = (min(track_label_x + 58 + LEG_D, TIP_X - 100), y_wl)
    barn_bot = (barn_top[0] - LEG_D, barn_top[1] + LEG_D)
    # West Lead and Main East are named between the Main East turn and the Barn foot.
    me_label_x = (g.me_turn[0] + barn_bot[0]) / 2
    _label(draw, (me_label_x, y_wl - 18), "West Lead", fonts.track, anchor="mm")

    # The diagonals start outset from their junctions so they do not pile onto the horizontal.
    _line(draw, _outset(g.plane, g.me_turn, DOT_R), g.me_turn, w=RAIL_W)
    _line(draw, g.me_turn, (TIP_X, y_me), w=RAIL_W)
    _line(draw, _outset(barn_top, barn_bot, RAIL_W), barn_bot, w=RAIL_W)
    _label(draw, ((barn_top[0] + barn_bot[0]) / 2, y_wl - 52), "Barn", fonts.cp, anchor="mm")

    _arrow(draw, (TIP_X, y_me), direction="right", size=18)
    _label(draw, (TIP_X - 2, y_me + 34), "to East End", fonts.note, anchor="rt", fill=INK)
    _label(draw, (me_label_x, y_me + 18), "Main East", fonts.track, anchor="mt")


def draw_west_yard(title: str, hooks: Hooks) -> Image.Image:
    """The West Yard sheet titled ``title``: Main West, the stubs, the octagon to Plane, West Lead, Barn, Main East."""
    img, draw = hooks.canvas(SHEET_W, SHEET_H)
    _title(draw, SHEET_W // 2, title, hooks)
    fonts = _Fonts(
        track=hooks.font(ARIAL_BOLD, 22),
        note=hooks.font(GEORGIA, 18),
        cp=hooks.font(ARIAL_BOLD, 36),
        sw=hooks.font(ARIAL_BOLD, 20),
    )
    g = _yard()
    _draw_main_west(draw, g, fonts)
    _draw_stubs(draw, g, fonts)
    _draw_octagon_to_plane(draw, g, fonts)
    _draw_lead_barn_main_east(draw, g, fonts)
    hooks.paste_compass(img, cx=SHEET_PAD + 115, cy=SHEET_H - 185, size=230, north="up")
    return img
