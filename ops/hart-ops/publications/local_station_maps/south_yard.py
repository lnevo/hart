"""South Yard (SM-03) drawer."""

from __future__ import annotations

import math

from PIL import Image

from .kit import (
    ARIAL_BOLD,
    GEORGIA,
    INK,
    SWNUM,
    Hooks,
    _arrow,
    _dot,
    _label,
    _line,
    _sw_badge,
)


def draw_south_yard(meta: dict, hooks: Hooks) -> Image.Image:
    """c3 South Yard — 8×5 landscape (inverse of East End ladder geometry).

    Same LED pitch as East End / Toggle_Dimensions.png:
      - dots Ø 3/16″ · ladder 3/4″ between points
    Layout is centered on the Main East up-diagonal. Yard stubs and mains
    run to the right edge (with track labels past the rails), matching East End.
    """
    width, height = 1600, 1000
    img, draw = hooks.canvas(width, height)
    pad = 56
    label_w = 96
    draw.text(
        (width // 2, 16),
        meta["title"].upper(),
        font=hooks.font(ARIAL_BOLD, 56),
        fill=INK,
        anchor="mt",
    )
    PX_PER_IN = 200.0
    LED_D = (3 / 16) * PX_PER_IN
    DOT_R = LED_D / 2
    STEP_1LED = (3 / 4) * PX_PER_IN
    ladder_dx_step = 35.0
    track_gap = math.sqrt(STEP_1LED**2 - ladder_dx_step**2)
    ladder_slope = ladder_dx_step / track_gap  # dx/dy, down-right

    track_font = hooks.font(ARIAL_BOLD, 22)
    note_font = hooks.font(GEORGIA, 18)
    cp_font = hooks.font(ARIAL_BOLD, 36)
    sw_font = hooks.font(ARIAL_BOLD, 20)
    lw = 3

    names = [
        "Main West",
        "Track S-R",
        "Track S-1",
        "Track S-2",
        "Track S-3",
        "Track S-4",
        "Main East",
    ]
    me_gap = track_gap * 0.72
    block_h = 5 * track_gap + me_gap
    # Leave room at bottom for Main East label + compass
    y_top = (height - block_h) / 2 - 4
    ys = [
        y_top,
        y_top + track_gap,
        y_top + 2 * track_gap,
        y_top + 3 * track_gap,
        y_top + 4 * track_gap,
        y_top + 5 * track_gap,
        y_top + 5 * track_gap + me_gap,
    ]

    x_left = pad
    x_right = width - pad - label_w
    lead_y = ys[1]
    # Page centerline = midpoint of Main East up-diagonal
    center_x = width / 2
    me_dy = ys[6] - ys[2]
    turn = (center_x - me_dy * ladder_slope / 2, ys[2])
    me_foot = (center_x + me_dy * ladder_slope / 2, ys[6])

    # Ladder: 104 even with the ME turn (east of it), not connected
    x_104 = turn[0] + STEP_1LED
    top = (x_104 - ladder_dx_step, ys[1])  # 103
    bot = (x_104 + 3 * ladder_dx_step, ys[5])

    def _ladder_x_at(y: float) -> float:
        t = (y - top[1]) / max(1.0, (bot[1] - top[1]))
        return top[0] + (bot[0] - top[0]) * t

    _line(draw, top, bot, w=lw)
    ladder_sw = [
        (103, ys[1]),
        (104, ys[2]),
        (105, ys[3]),
        (106, ys[4]),
    ]
    for num, y_t in ladder_sw:
        px = _ladder_x_at(y_t)
        _sw_badge(draw, (px + 36, y_t - 28), str(SWNUM.get(num, num)), sw_font)
        if num != 103:
            _dot(draw, (px, y_t), r=DOT_R)
    _dot(draw, top, r=DOT_R)

    def _track_label(y: float, text: str) -> None:
        _label(draw, (x_right + 8, y), text, track_font, anchor="lm")

    # Barn first — west-side labels align left of it with West Lead
    barn_x = (x_left + turn[0]) / 2
    barn_top = (barn_x + ladder_dx_step / 2, lead_y)
    barn_bot = (barn_x - ladder_dx_step / 2, ys[2])
    wl_label_x = x_left + 200  # clear of "to Brick"; still left of Barn

    # Main West — rails stop before the track-label column
    _line(draw, (x_left, ys[0]), (x_right, ys[0]), w=lw)
    me_east_label_x = (me_foot[0] + x_right) / 2
    # Eastern Main West above the rail, aligned over Main East
    _label(
        draw,
        (me_east_label_x, ys[0] - 18),
        "Main West",
        track_font,
        anchor="mm",
    )
    # Western Main West above West Lead
    _label(
        draw,
        (wl_label_x, ys[0] - 18),
        "Main West",
        track_font,
        anchor="mm",
    )
    _arrow(draw, (x_left, ys[0]), direction="left", size=14)
    _label(
        draw,
        (x_left + 2, ys[0] - 26),
        "to Brick",
        note_font,
        anchor="lt",
        fill=INK,
    )
    _arrow(draw, (x_right, ys[0]), direction="right", size=14)
    _label(
        draw,
        (x_right - 2, ys[0] - 26),
        "to East End",
        note_font,
        anchor="rt",
        fill=INK,
    )

    # Track 1 / West Lead — full run
    _line(draw, (x_left, lead_y), (x_right, ys[1]), w=lw)
    _track_label(ys[1], names[1])

    for i in range(2, 6):
        y = ys[i]
        xe = _ladder_x_at(y)
        _line(draw, (xe, y), (x_right, y), w=lw)
        _track_label(y, names[i])

    # Main East: east to the edge, up-diagonal (centerline), then west ∥ West Lead
    _line(draw, me_foot, (x_right, ys[6]), w=lw)
    _line(draw, me_foot, turn, w=lw)
    _line(draw, (x_left, ys[2]), turn, w=lw)
    # Eastern Main East above the horizontal through the yard body
    _label(
        draw,
        (me_east_label_x, ys[6] - 18),
        "Main East",
        track_font,
        anchor="mm",
    )
    # Western Main East above the approach, aligned with West Lead, left of Barn
    _label(
        draw,
        (wl_label_x, ys[2] - 18),
        "Main East",
        track_font,
        anchor="mm",
    )
    _arrow(draw, (x_right, ys[6]), direction="right", size=14)
    _label(
        draw,
        (x_right - 2, ys[6] - 26),
        "to East End",
        note_font,
        anchor="rb",
        fill=INK,
    )
    _arrow(draw, (x_left, ys[2]), direction="left", size=14)
    # Between West Lead and the elevated Main East approach
    _label(
        draw,
        (x_left + 2, (lead_y + ys[2]) / 2),
        "to Plane",
        note_font,
        anchor="lm",
        fill=INK,
    )

    # Barn: West Lead ↔ elevated Main East (not motorized — no LED spots)
    _line(draw, barn_top, barn_bot, w=lw)
    _label(
        draw,
        ((barn_top[0] + barn_bot[0]) / 2, barn_bot[1] + 36),
        "Barn",
        cp_font,
        anchor="mm",
    )

    # Engine terminal: ET-1 / ET-2 off West Lead ladder; ET-3 spur off ET-2
    takeoff = ((barn_top[0] + top[0]) / 2, lead_y)
    stub_gap = track_gap / 6
    et3_y = lead_y - stub_gap
    et2_y = lead_y - 2 * stub_gap
    et1_y = lead_y - 3 * stub_gap

    def _stub_ladder_x(y: float) -> float:
        return takeoff[0] - (lead_y - y) * ladder_slope

    # Ladder only climbs to ET-2 / ET-1
    stub_ladder_top = (_stub_ladder_x(et1_y), et1_y)
    _line(draw, takeoff, stub_ladder_top, w=lw)
    stub_end = min(barn_top[0] - 24, takeoff[0] - 90)
    stub_end = max(stub_end, x_left + 28)
    et_font = hooks.font(ARIAL_BOLD, 16)
    for et_num, sy in ((1, et1_y), (2, et2_y)):
        sx = _stub_ladder_x(sy)
        _line(draw, (sx, sy), (stub_end, sy), w=lw)
        _label(
            draw,
            (stub_end - 4, sy),
            f"ET-{et_num}",
            et_font,
            anchor="rm",
            fill=INK,
        )

    # ET-3 spur: split just west of the ladder on ET-2, down-left (~45°)
    et2_sx = _stub_ladder_x(et2_y)
    spur_on_et2 = (et2_sx - 12, et2_y)
    drop = et3_y - et2_y
    et3_sx = spur_on_et2[0] - drop  # 45° down-left
    _line(draw, spur_on_et2, (et3_sx, et3_y), w=lw)
    _line(draw, (et3_sx, et3_y), (stub_end, et3_y), w=lw)
    _label(
        draw,
        (stub_end - 4, et3_y),
        "ET-3",
        et_font,
        anchor="rm",
        fill=INK,
    )

    _label(
        draw,
        (wl_label_x, lead_y - 18),
        "West Lead",
        track_font,
        anchor="mm",
    )
    _arrow(draw, (x_left, lead_y), direction="left", size=14)
    # Geographic north points right (same rose as SM-01 / linear5 panel)
    hooks.paste_compass(img, cx=pad + 115, cy=height - 185, size=230, north="up")
    return img
