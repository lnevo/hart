"""East End (SM-04, map key "industries") drawer.

8×5 landscape printable schematic at the LED pitch of
docs/benchwork/station_maps_3d/Toggle_Dimensions.png in true print inches (kit.PX_PER_IN):
dots Ø 3/16″ (kit.DOT_R); switch 111 has two LEDs, its mid point 3/8″ from each track along the
diagonal (kit.STEP_2LED); the yard ladder has one LED, 3/4″ between adjacent points (kit.STEP_1LED).
"""

from __future__ import annotations

import math
from typing import NamedTuple

from PIL import Image, ImageDraw, ImageFont

import crew_master

from .kit import (
    ARIAL_BOLD,
    DOT_R,
    GEORGIA,
    GEORGIA_BOLD,
    INK,
    LADDER_DX_STEP,
    RAIL_W,
    SHEET_H,
    SHEET_PAD,
    SHEET_W,
    STEP_1LED,
    STEP_2LED,
    SWNUM,
    YARD_BLOCK_H,
    Hooks,
    Point,
    _arrow,
    _color_chip,
    _dot,
    _label,
    _ladder_x_at,
    _line,
    _sw_badge,
    _title,
    _yard_rows,
)

# The industry tracks of the East End ladder: crew-master colour ids and the loads printed
# under each rail.
TRACK_INDUSTRIES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("Track S-1", ("yellow",), "Pellets  ·  Chemicals  ·  Shipping"),
    ("Track S-2", ("red", "green"), "LPG  ·  Crane  ·  Team"),
    ("Track S-3", ("pink",), "Cement  ·  Aggregate"),
    ("Track S-4", ("purple",), "Coal  ·  Carbon  ·  Chemical"),
)
LABEL_W = 110  # track-label column west of the rails
CHIP_SIZE = 28
# Ladder switches (old 100-series ids, printed through SWNUM) and the rail each one sits on.
LADDER_SWITCHES = ((110, 1), (109, 2), (108, 3), (107, 4))


class _Fonts(NamedTuple):
    track: ImageFont.FreeTypeFont
    ind: ImageFont.FreeTypeFont
    spot: ImageFont.FreeTypeFont
    note: ImageFont.FreeTypeFont
    sw: ImageFont.FreeTypeFont


class IndustryRow(NamedTuple):
    """One industry track: its name, the industries on it, their colour chips, the loads line."""

    track: str
    industry: str
    colors: list[tuple[str, str]]  # (colour label, fill hex)
    loads: str


class _Yard(NamedTuple):
    """Where the East End rails sit on the sheet."""

    ys: tuple[float, ...]  # Main West, S-R, S-1 … S-4, Main East
    x_left: float
    x_right: float
    top: Point  # ladder top (switch 110)
    bot: Point  # ladder foot on S-4
    sw111_top: Point  # 111 on Main West
    sw111_bot: Point  # 111 on S-R
    x_east: float  # switch 33 (old 112) on the East Lead
    me_turn_x: float  # Main East turns up to the East Lead here
    yard_ends: list[float]  # where S-1 … S-4 meet the ladder

    @property
    def lead_y(self) -> float:
        return self.ys[1]

    def ladder_x_at(self, y: float) -> float:
        return _ladder_x_at(self.top, self.bot, y)

    def track_label(self, draw: ImageDraw.ImageDraw, y: float, text: str, font: ImageFont.FreeTypeFont) -> None:
        """A track name right-aligned against the shared west rail end."""
        _label(draw, (self.x_left - 8, y), text, font, anchor="rm")


def industry_rows() -> list[IndustryRow]:
    """TRACK_INDUSTRIES with the industry names and colour labels from the crew master."""
    swatch = crew_master.swatches(crew_master.load())
    return [
        IndustryRow(
            track,
            "  ·  ".join(swatch[c].dest for c in color_ids),
            [(swatch[c].label, swatch[c].fill) for c in color_ids],
            loads,
        )
        for track, color_ids, loads in TRACK_INDUSTRIES
    ]


def _yard() -> _Yard:
    x_left = SHEET_PAD + LABEL_W
    x_right = SHEET_W - SHEET_PAD
    ys = _yard_rows((SHEET_H - YARD_BLOCK_H) / 2 + 8)
    cx = (x_left + x_right) / 2
    # Ladder: four one-LED steps along the diagonal, S-R to S-4.
    top = (cx + 2 * LADDER_DX_STEP, ys[1])
    bot = (cx - 2 * LADDER_DX_STEP, ys[5])
    # 111 has the ladder's vertical gap, so the same horizontal run per track step.
    sw111_top = (top[0] - 220, ys[0])
    sw111_bot = (sw111_top[0] + LADDER_DX_STEP, ys[1])
    yard_ends = [_ladder_x_at(top, bot, ys[i]) for i in range(2, 6)]
    x_east, me_turn_x = _east_lead_switch(top, bot, ys, yard_ends)
    return _Yard(ys, x_left, x_right, top, bot, sw111_top, sw111_bot, x_east, me_turn_x, yard_ends)


def _east_lead_switch(top: Point, bot: Point, ys: tuple[float, ...], yard_ends: list[float]) -> tuple[float, float]:
    """x of switch 33 on the East Lead and of the Main East turn below it.

    Main East climbs to the lead parallel to the ladder. The turn is first pushed 28 px clear
    of the yard ends; when that moves switch 33 more than 1 px from one LED step east of 110,
    the exact step wins and the turn follows it.
    """
    ladder_dx = bot[0] - top[0]
    ladder_dy = bot[1] - top[1]
    lead_y = ys[1]
    x_east = top[0] + STEP_1LED
    me_turn_x = x_east - (lead_y - ys[6]) * ladder_dx / ladder_dy
    me_turn_x = max(me_turn_x, max(yard_ends) + 28)
    x_east = me_turn_x + (lead_y - ys[6]) * ladder_dx / ladder_dy
    if abs(x_east - (top[0] + STEP_1LED)) > 1:
        x_east = top[0] + STEP_1LED
        me_turn_x = x_east - (lead_y - ys[6]) * ladder_dx / ladder_dy
    return x_east, me_turn_x


def _draw_ladder_and_111(draw: ImageDraw.ImageDraw, g: _Yard, fonts: _Fonts) -> None:
    _line(draw, g.top, g.bot, w=RAIL_W)
    for num, row in LADDER_SWITCHES:
        y_t = g.ys[row]
        _sw_badge(draw, (g.ladder_x_at(y_t) - 36, y_t - 28), str(SWNUM.get(num, num)), fonts.sw)
    _dot(draw, g.top, r=DOT_R)

    _line(draw, g.sw111_top, g.sw111_bot, w=RAIL_W)
    # The mid point sits exactly one 2-LED step from the Main West point along 111.
    d111 = math.hypot(g.sw111_bot[0] - g.sw111_top[0], g.sw111_bot[1] - g.sw111_top[1])
    ux = (g.sw111_bot[0] - g.sw111_top[0]) / d111
    uy = (g.sw111_bot[1] - g.sw111_top[1]) / d111
    mid = (g.sw111_top[0] + ux * STEP_2LED, g.sw111_top[1] + uy * STEP_2LED)
    _dot(draw, mid, r=DOT_R)
    _sw_badge(draw, (mid[0] - 78, mid[1] - 4), "23", fonts.sw)


def _draw_main_west_and_sr(draw: ImageDraw.ImageDraw, g: _Yard, fonts: _Fonts) -> None:
    y_mw = g.ys[0]
    _line(draw, (g.x_left, y_mw), (g.x_right, y_mw), w=RAIL_W)
    _dot(draw, g.sw111_top, r=DOT_R)
    _arrow(draw, (g.x_left, y_mw), direction="left", size=14)
    _label(draw, (g.x_left + 2, y_mw - 26), "to Brick", fonts.note, anchor="lt", fill=INK)
    _arrow(draw, (g.x_right, y_mw), direction="right", size=14)

    _line(draw, (g.x_left, g.ys[1]), (g.top[0], g.ys[1]), w=RAIL_W)
    _dot(draw, g.sw111_bot, r=DOT_R)
    g.track_label(draw, g.ys[1], "Track S-R", fonts.track)


def _draw_dual_industry(draw: ImageDraw.ImageDraw, mid_x: float, label_y: float, row: IndustryRow,
                        font: ImageFont.FreeTypeFont) -> None:
    """Two industries on one track, each name after its own chip (S-2: red, then green)."""
    left_name, right_name = row.industry.split(" · ", 1)
    gap = 14
    left_w = CHIP_SIZE + 8 + draw.textlength(left_name, font=font)
    mid_sep = draw.textlength(" · ", font=font)
    right_w = CHIP_SIZE + 8 + draw.textlength(right_name, font=font)
    x = mid_x - (left_w + mid_sep + gap + right_w) / 2
    _color_chip(draw, (x + CHIP_SIZE / 2, label_y), row.colors[0][1], size=CHIP_SIZE)
    x += CHIP_SIZE + 8
    _label(draw, (x, label_y), left_name, font, anchor="lm")
    x += draw.textlength(left_name, font=font)
    _label(draw, (x, label_y), " · ", font, anchor="lm")
    x += mid_sep + gap
    _color_chip(draw, (x + CHIP_SIZE / 2, label_y), row.colors[1][1], size=CHIP_SIZE)
    x += CHIP_SIZE + 8
    _label(draw, (x, label_y), right_name, font, anchor="lm")


def _draw_single_industry(draw: ImageDraw.ImageDraw, mid_x: float, label_y: float, row: IndustryRow,
                          font: ImageFont.FreeTypeFont) -> None:
    """The chips in a row, then the industry name, centred together on mid_x."""
    n_chips = len(row.colors)
    chip_span = n_chips * (CHIP_SIZE + 8) - 8 if n_chips else 0
    text_x = chip_span + 12 if n_chips else 0
    group_left = mid_x - (text_x + draw.textlength(row.industry, font=font)) / 2
    for ci, (_cname, hexfill) in enumerate(row.colors):
        _color_chip(draw, (group_left + CHIP_SIZE / 2 + ci * (CHIP_SIZE + 8), label_y), hexfill, size=CHIP_SIZE)
    _label(draw, (group_left + text_x, label_y), row.industry, font, anchor="lm")


def _draw_industry_tracks(draw: ImageDraw.ImageDraw, g: _Yard, fonts: _Fonts, rows: list[IndustryRow]) -> None:
    """S-1 … S-4 from the west rail end to the ladder, each with its industries above and loads below."""
    for i, row in zip(range(2, 6), rows, strict=True):
        y = g.ys[i]
        xe = g.ladder_x_at(y)
        _line(draw, (g.x_left, y), (xe, y), w=RAIL_W)
        if i != 5:
            _dot(draw, (xe, y), r=DOT_R)
        g.track_label(draw, y, row.track, fonts.track)
        mid_x = (g.x_left + xe) / 2
        label_y = y - 20
        if row.industry and " · " in row.industry and len(row.colors) == 2:
            _draw_dual_industry(draw, mid_x, label_y, row, fonts.ind)
        elif row.industry:
            _draw_single_industry(draw, mid_x, label_y, row, fonts.ind)
        if row.loads:
            _label(draw, (mid_x, y + 14), row.loads, fonts.spot, anchor="mm", fill=INK)


def _draw_main_east(draw: ImageDraw.ImageDraw, g: _Yard, fonts: _Fonts) -> None:
    """Main East through the yard, from the shared west rail end up to the East Lead."""
    y_me = g.ys[6]
    _line(draw, (g.x_left, y_me), (g.me_turn_x, y_me), w=RAIL_W)
    _line(draw, (g.me_turn_x, y_me), (g.x_east, g.lead_y), w=RAIL_W)
    _arrow(draw, (g.x_left, y_me), direction="left", size=14)
    _label(draw, (g.x_left + 2, y_me - 22), "to Barn", fonts.note, anchor="lb", fill=INK)
    # Main East and the western Main West share one x, over the industry labels.
    industry_label_x = (g.x_left + max(g.yard_ends)) / 2
    _label(draw, (industry_label_x, y_me - 18), "Main East", fonts.track, anchor="mm")
    _label(draw, (industry_label_x, g.ys[0] - 18), "Main West", fonts.track, anchor="mm")


def _draw_east_lead(draw: ImageDraw.ImageDraw, g: _Yard, fonts: _Fonts) -> None:
    """S-R east from 110 to switch 33, then the East Lead to the edge, toward Princess."""
    lead_y = g.lead_y
    _line(draw, (g.top[0], g.ys[1]), (g.x_east, lead_y), w=RAIL_W)
    # Badge clearance as at 110: offset west of the junction, off the rail.
    _sw_badge(draw, (g.x_east - 36, lead_y - 28), "33", fonts.sw)
    _dot(draw, (g.x_east, lead_y), r=DOT_R)
    _line(draw, (g.x_east, lead_y), (g.x_right, lead_y), w=RAIL_W)
    lead_label_x = (g.x_east + g.x_right) / 2
    _label(draw, (lead_label_x, lead_y - 18), "Main East", fonts.track, anchor="mm")
    _label(draw, (lead_label_x, g.ys[0] - 18), "Main West", fonts.track, anchor="mm")
    _arrow(draw, (g.x_right, lead_y), direction="right", size=14)
    # One destination note, centred between Main West and Main East.
    _label(draw, (g.x_right - 2, (g.ys[0] + lead_y) / 2), "to Princess", fonts.note, anchor="rm", fill=INK)


def draw_industries(title: str, hooks: Hooks) -> Image.Image:
    """The East End sheet titled ``title``: ladder and 111, Main West, the industry tracks, Main East, the East Lead."""
    img, draw = hooks.canvas(SHEET_W, SHEET_H)
    fonts = _Fonts(
        track=hooks.font(ARIAL_BOLD, 22),
        ind=hooks.font(GEORGIA_BOLD, 28),
        spot=hooks.font(GEORGIA, 16),
        note=hooks.font(GEORGIA, 18),
        sw=hooks.font(ARIAL_BOLD, 20),
    )
    rows = industry_rows()
    g = _yard()
    _title(draw, g.top[0], title, hooks)  # centred over switch 110
    _draw_ladder_and_111(draw, g, fonts)
    _draw_main_west_and_sr(draw, g, fonts)
    _draw_industry_tracks(draw, g, fonts, rows)
    _draw_main_east(draw, g, fonts)
    _draw_east_lead(draw, g, fonts)
    # Geographic north points right (the rose of SM-01 and the linear5 panel).
    hooks.paste_compass(img, cx=SHEET_W - SHEET_PAD - 115, cy=SHEET_H - 185, size=230, north="up")
    return img
