"""South Yard (SM-03) drawer.

8×5 landscape, the inverse of the East End ladder geometry, at the same LED pitch (kit.DOT_R,
kit.STEP_1LED). The layout is centred on the Main East up-diagonal. Yard stubs and mains run to
the right edge, with the track labels past the rails, as on East End.
"""

from __future__ import annotations

from typing import NamedTuple

from PIL import Image, ImageDraw, ImageFont

from .kit import (
    ARIAL_BOLD,
    DOT_R,
    GEORGIA,
    INK,
    LADDER_DX_STEP,
    LADDER_TRACK_GAP,
    RAIL_W,
    SHEET_H,
    SHEET_PAD,
    SHEET_W,
    STEP_1LED,
    SWNUM,
    YARD_BLOCK_H,
    Hooks,
    Point,
    _arrow,
    _dot,
    _label,
    _ladder_x_at,
    _line,
    _sw_badge,
    _title,
    _yard_rows,
)

LABEL_W = 96  # track-label column right of the rails
LADDER_SLOPE = LADDER_DX_STEP / LADDER_TRACK_GAP  # dx/dy, down-right
TRACK_NAMES = ("Main West", "Track S-R", "Track S-1", "Track S-2", "Track S-3", "Track S-4", "Main East")
# Ladder switches (old 100-series ids, printed through SWNUM) and the rail each one sits on.
LADDER_SWITCHES = ((103, 1), (104, 2), (105, 3), (106, 4))


class _Fonts(NamedTuple):
    track: ImageFont.FreeTypeFont
    note: ImageFont.FreeTypeFont
    cp: ImageFont.FreeTypeFont
    sw: ImageFont.FreeTypeFont


class _Yard(NamedTuple):
    """Where the South Yard rails sit on the sheet."""

    ys: tuple[float, ...]  # Main West, S-R (West Lead), S-1 … S-4, Main East
    x_left: float
    x_right: float
    turn: Point  # top of the Main East up-diagonal
    me_foot: Point  # foot of the Main East up-diagonal
    top: Point  # ladder top (switch 103)
    bot: Point  # ladder foot on S-4
    barn_top: Point
    barn_bot: Point
    wl_label_x: float  # labels of the western mains, over West Lead
    me_east_label_x: float  # labels of the eastern mains, over Main East

    @property
    def lead_y(self) -> float:
        return self.ys[1]

    def track_label(self, draw: ImageDraw.ImageDraw, y: float, text: str, font: ImageFont.FreeTypeFont) -> None:
        """A track name in the column right of the rails."""
        _label(draw, (self.x_right + 8, y), text, font, anchor="lm")


def _yard() -> _Yard:
    """The rail geometry: rows, the Main East diagonal on the page centre line, the ladder east of it."""
    # Leave room at the bottom for the Main East label and the compass.
    ys = _yard_rows((SHEET_H - YARD_BLOCK_H) / 2 - 4)
    x_left = SHEET_PAD
    x_right = SHEET_W - SHEET_PAD - LABEL_W
    center_x = SHEET_W / 2
    me_dy = ys[6] - ys[2]
    turn = (center_x - me_dy * LADDER_SLOPE / 2, ys[2])
    me_foot = (center_x + me_dy * LADDER_SLOPE / 2, ys[6])
    # Switch 104 is one LED step east of the Main East turn, not connected to it.
    x_104 = turn[0] + STEP_1LED
    top = (x_104 - LADDER_DX_STEP, ys[1])
    bot = (x_104 + 3 * LADDER_DX_STEP, ys[5])
    barn_x = (x_left + turn[0]) / 2
    return _Yard(
        ys=ys,
        x_left=x_left,
        x_right=x_right,
        turn=turn,
        me_foot=me_foot,
        top=top,
        bot=bot,
        barn_top=(barn_x + LADDER_DX_STEP / 2, ys[1]),
        barn_bot=(barn_x - LADDER_DX_STEP / 2, ys[2]),
        wl_label_x=x_left + 200,  # clear of "to Brick", still west of Barn
        me_east_label_x=(me_foot[0] + x_right) / 2,
    )


def _draw_ladder(draw: ImageDraw.ImageDraw, g: _Yard, fonts: _Fonts) -> None:
    _line(draw, g.top, g.bot, w=RAIL_W)
    for num, row in LADDER_SWITCHES:
        y_t = g.ys[row]
        px = _ladder_x_at(g.top, g.bot, y_t)
        _sw_badge(draw, (px + 36, y_t - 28), str(SWNUM.get(num, num)), fonts.sw)
        if num != 103:
            _dot(draw, (px, y_t), r=DOT_R)
    _dot(draw, g.top, r=DOT_R)


def _draw_main_west(draw: ImageDraw.ImageDraw, g: _Yard, fonts: _Fonts) -> None:
    """Main West across the sheet, stopping before the track-label column, named at both ends."""
    y = g.ys[0]
    _line(draw, (g.x_left, y), (g.x_right, y), w=RAIL_W)
    _label(draw, (g.me_east_label_x, y - 18), "Main West", fonts.track, anchor="mm")
    _label(draw, (g.wl_label_x, y - 18), "Main West", fonts.track, anchor="mm")
    _arrow(draw, (g.x_left, y), direction="left", size=14)
    _label(draw, (g.x_left + 2, y - 26), "to Brick", fonts.note, anchor="lt", fill=INK)
    _arrow(draw, (g.x_right, y), direction="right", size=14)
    _label(draw, (g.x_right - 2, y - 26), "to East End", fonts.note, anchor="rt", fill=INK)


def _draw_yard_tracks(draw: ImageDraw.ImageDraw, g: _Yard, fonts: _Fonts) -> None:
    """West Lead (S-R) the full width; S-1 … S-4 from the ladder east."""
    _line(draw, (g.x_left, g.lead_y), (g.x_right, g.ys[1]), w=RAIL_W)
    g.track_label(draw, g.ys[1], TRACK_NAMES[1], fonts.track)
    for i in range(2, 6):
        y = g.ys[i]
        _line(draw, (_ladder_x_at(g.top, g.bot, y), y), (g.x_right, y), w=RAIL_W)
        g.track_label(draw, y, TRACK_NAMES[i], fonts.track)


def _draw_main_east(draw: ImageDraw.ImageDraw, g: _Yard, fonts: _Fonts) -> None:
    """Main East: east to the edge, up the centre-line diagonal, then west beside West Lead."""
    y_me, y_west = g.ys[6], g.ys[2]
    _line(draw, g.me_foot, (g.x_right, y_me), w=RAIL_W)
    _line(draw, g.me_foot, g.turn, w=RAIL_W)
    _line(draw, (g.x_left, y_west), g.turn, w=RAIL_W)
    _label(draw, (g.me_east_label_x, y_me - 18), "Main East", fonts.track, anchor="mm")
    _label(draw, (g.wl_label_x, y_west - 18), "Main East", fonts.track, anchor="mm")
    _arrow(draw, (g.x_right, y_me), direction="right", size=14)
    _label(draw, (g.x_right - 2, y_me - 26), "to East End", fonts.note, anchor="rb", fill=INK)
    _arrow(draw, (g.x_left, y_west), direction="left", size=14)
    # Between West Lead and the raised Main East approach.
    _label(draw, (g.x_left + 2, (g.lead_y + y_west) / 2), "to Plane", fonts.note, anchor="lm", fill=INK)


def _draw_barn(draw: ImageDraw.ImageDraw, g: _Yard, fonts: _Fonts) -> None:
    """Barn crossover, West Lead ↔ the raised Main East. It is not motorised, so it has no LED spots."""
    _line(draw, g.barn_top, g.barn_bot, w=RAIL_W)
    mid_x = (g.barn_top[0] + g.barn_bot[0]) / 2
    _label(draw, (mid_x, g.barn_bot[1] + 36), "Barn", fonts.cp, anchor="mm")


def _draw_engine_terminal(draw: ImageDraw.ImageDraw, g: _Yard, et_font: ImageFont.FreeTypeFont) -> None:
    """ET-1 and ET-2 off a short ladder from West Lead; ET-3 a spur off ET-2."""
    lead_y = g.lead_y
    takeoff = ((g.barn_top[0] + g.top[0]) / 2, lead_y)
    stub_gap = LADDER_TRACK_GAP / 6
    et3_y = lead_y - stub_gap
    et2_y = lead_y - 2 * stub_gap
    et1_y = lead_y - 3 * stub_gap

    def stub_ladder_x(y: float) -> float:
        return takeoff[0] - (lead_y - y) * LADDER_SLOPE

    # The ladder climbs only to ET-2 and ET-1.
    _line(draw, takeoff, (stub_ladder_x(et1_y), et1_y), w=RAIL_W)
    stub_end = max(min(g.barn_top[0] - 24, takeoff[0] - 90), g.x_left + 28)
    for et_num, sy in ((1, et1_y), (2, et2_y)):
        _line(draw, (stub_ladder_x(sy), sy), (stub_end, sy), w=RAIL_W)
        _label(draw, (stub_end - 4, sy), f"ET-{et_num}", et_font, anchor="rm", fill=INK)

    # ET-3 splits off ET-2 just west of the ladder and drops down-left at 45°.
    spur_on_et2 = (stub_ladder_x(et2_y) - 12, et2_y)
    et3_sx = spur_on_et2[0] - (et3_y - et2_y)
    _line(draw, spur_on_et2, (et3_sx, et3_y), w=RAIL_W)
    _line(draw, (et3_sx, et3_y), (stub_end, et3_y), w=RAIL_W)
    _label(draw, (stub_end - 4, et3_y), "ET-3", et_font, anchor="rm", fill=INK)


def draw_south_yard(title: str, hooks: Hooks) -> Image.Image:
    """The South Yard sheet titled ``title``: ladder, Main West, yard tracks, Main East, Barn, engine terminal, compass."""
    img, draw = hooks.canvas(SHEET_W, SHEET_H)
    _title(draw, SHEET_W // 2, title, hooks)
    fonts = _Fonts(
        track=hooks.font(ARIAL_BOLD, 22),
        note=hooks.font(GEORGIA, 18),
        cp=hooks.font(ARIAL_BOLD, 36),
        sw=hooks.font(ARIAL_BOLD, 20),
    )
    g = _yard()
    _draw_ladder(draw, g, fonts)
    _draw_main_west(draw, g, fonts)
    _draw_yard_tracks(draw, g, fonts)
    _draw_main_east(draw, g, fonts)
    _draw_barn(draw, g, fonts)
    _draw_engine_terminal(draw, g, hooks.font(ARIAL_BOLD, 16))
    _label(draw, (g.wl_label_x, g.lead_y - 18), "West Lead", fonts.track, anchor="mm")
    _arrow(draw, (g.x_left, g.lead_y), direction="left", size=14)
    # Geographic north points right (the rose of SM-01 and the linear5 panel).
    hooks.paste_compass(img, cx=SHEET_PAD + 115, cy=SHEET_H - 185, size=230, north="up")
    return img
