"""East End (SM-04, map key "industries") drawer."""

from __future__ import annotations

import math

from PIL import Image

import crew_master

from .kit import (
    ARIAL_BOLD,
    GEORGIA,
    GEORGIA_BOLD,
    INK,
    SWNUM,
    Hooks,
    _arrow,
    _color_chip,
    _dot,
    _label,
    _line,
    _sw_badge,
)


def draw_industries(meta: dict, hooks: Hooks) -> Image.Image:
    """c2 East End — 8×5 landscape printable schematic.

    Layout scale matches docs/benchwork/station_maps_3d/Toggle_Dimensions.png (true print inches):
      - LED / map dots: Ø 3/16″
      - 111 (2-LED): mid point 3/8″ from each track along the diagonal
      - Yard ladder (1-LED): 3/4″ (3/8″×2) between adjacent points
    Canvas 1600×1000 on an 8×5 sheet → 200 px/in.
    """
    width, height = 1600, 1000
    img, draw = hooks.canvas(width, height)
    pad = 56
    label_w = 110
    x_left = pad + label_w
    x_right = width - pad

    # --- hardware-driven geometry (see Toggle_Dimensions.png) ---
    PX_PER_IN = 200.0
    LED_D = (3 / 16) * PX_PER_IN  # 37.5
    DOT_R = LED_D / 2  # 18.75
    STEP_2LED = (3 / 8) * PX_PER_IN  # 75 — 111 mid ↔ either track
    STEP_1LED = (3 / 4) * PX_PER_IN  # 150 — ladder adjacent points
    # Keep a mild ladder slant; vertical track gap follows from 1-LED pitch.
    ladder_dx_step = 35.0
    track_gap = math.sqrt(STEP_1LED**2 - ladder_dx_step**2)

    track_font = hooks.font(ARIAL_BOLD, 22)
    ind_font = hooks.font(GEORGIA_BOLD, 28)
    spot_font = hooks.font(GEORGIA, 16)
    note_font = hooks.font(GEORGIA, 18)
    sw_font = hooks.font(ARIAL_BOLD, 20)
    lw = 3
    chip_size = 28

    # track name, industry, colors, spot line under the rail
    swatch = crew_master.swatches(crew_master.load())   # the industry colours, from the master
    rows = [
        ("Main West", None, [], None),
        ("Track S-R", None, [], None),
        (
            "Track S-1",
            "Aristech Plastics",
            [("YELLOW", swatch["yellow"].fill)],
            "Pellets  ·  Chemicals  ·  Shipping",
        ),
        (
            "Track S-2",
            "Ferrellgas  ·  A. Stucki Co.",
            [("RED", swatch["red"].fill), ("GREEN", swatch["green"].fill)],
            "LPG  ·  Crane  ·  Team",
        ),
        (
            "Track S-3",
            "Kosmos Cement",
            [("PINK", swatch["pink"].fill)],
            "Cement  ·  Aggregate",
        ),
        (
            "Track S-4",
            "Calgon Carbon",
            [("PURPLE", swatch["purple"].fill)],
            "Coal  ·  Carbon  ·  Chemical",
        ),
        ("Main East", None, [], None),
    ]
    # MW…T5 use full LED pitch; Main East sits a bit closer (not on ladder).
    me_gap = track_gap * 0.72
    block_h = 5 * track_gap + me_gap
    y_top = (height - block_h) / 2 + 8
    ys = [
        y_top,
        y_top + track_gap,
        y_top + 2 * track_gap,
        y_top + 3 * track_gap,
        y_top + 4 * track_gap,
        y_top + 5 * track_gap,
        y_top + 5 * track_gap + me_gap,
    ]

    cx = (x_left + x_right) / 2
    lead_y = ys[1]
    # Ladder: 4 × STEP_1LED along the diagonal (T1→T5)
    top = (cx + 2 * ladder_dx_step, ys[1])  # 110
    bot = (cx - 2 * ladder_dx_step, ys[5])

    # Title centered over switch 110
    draw.text(
        (top[0], 16),
        meta["title"].upper(),
        font=hooks.font(ARIAL_BOLD, 56),
        fill=INK,
        anchor="mt",
    )

    def _ladder_x_at(y: float) -> float:
        t = (y - top[1]) / max(1.0, (bot[1] - top[1]))
        return top[0] + (bot[0] - top[0]) * t

    _line(draw, top, bot, w=lw)
    ladder_sw = [
        (110, ys[1]),
        (109, ys[2]),
        (108, ys[3]),
        (107, ys[4]),
    ]
    for num, y_t in ladder_sw:
        px = _ladder_x_at(y_t)
        _sw_badge(draw, (px - 36, y_t - 28), str(SWNUM.get(num, num)), sw_font)

    _dot(draw, top, r=DOT_R)

    # 111 — 2-LED pitch: mid is STEP_2LED from each track along the diagonal
    # Same vertical gap as ladder → same horizontal run per track step.
    sw111_top = (top[0] - 220, ys[0])
    sw111_bot = (sw111_top[0] + ladder_dx_step, ys[1])
    _line(draw, sw111_top, sw111_bot, w=lw)
    # Unit vector along 111; mid sits exactly STEP_2LED from the Main West point.
    d111 = math.hypot(sw111_bot[0] - sw111_top[0], sw111_bot[1] - sw111_top[1])
    ux = (sw111_bot[0] - sw111_top[0]) / d111
    uy = (sw111_bot[1] - sw111_top[1]) / d111
    sw111_mid = (sw111_top[0] + ux * STEP_2LED, sw111_top[1] + uy * STEP_2LED)
    _dot(draw, sw111_mid, r=DOT_R)
    _sw_badge(
        draw,
        (sw111_mid[0] - 78, sw111_mid[1] - 4),
        "23",
        sw_font,
    )

    # MW / ME / yard stubs share the same west rail end (x_left).
    def _track_label(y: float, text: str) -> None:
        _label(draw, (x_left - 8, y), text, track_font, anchor="rm")

    _line(draw, (x_left, ys[0]), (x_right, ys[0]), w=lw)
    _dot(draw, sw111_top, r=DOT_R)
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

    _line(draw, (x_left, ys[1]), (top[0], ys[1]), w=lw)
    _dot(draw, sw111_bot, r=DOT_R)
    _track_label(ys[1], "Track S-R")

    for i in range(2, 6):
        y = ys[i]
        tname, industry, colors, spots = rows[i]
        xe = _ladder_x_at(y)
        _line(draw, (x_left, y), (xe, y), w=lw)
        if i != 5:
            _dot(draw, (xe, y), r=DOT_R)
        _track_label(y, tname)
        mid_x = (x_left + xe) / 2
        label_y = y - 20
        # Dual-industry: red on Ferrellgas, green on A. Stucki (team)
        if industry and " · " in industry and len(colors) == 2:
            left_name, right_name = industry.split(" · ", 1)
            gap = 14
            left_w = chip_size + 8 + draw.textlength(left_name, font=ind_font)
            mid_sep = draw.textlength(" · ", font=ind_font)
            right_w = chip_size + 8 + draw.textlength(right_name, font=ind_font)
            group_w = left_w + mid_sep + gap + right_w
            x = mid_x - group_w / 2
            _color_chip(draw, (x + chip_size / 2, label_y), colors[0][1], size=chip_size)
            x += chip_size + 8
            _label(draw, (x, label_y), left_name, ind_font, anchor="lm")
            x += draw.textlength(left_name, font=ind_font)
            _label(draw, (x, label_y), " · ", ind_font, anchor="lm")
            x += mid_sep + gap
            _color_chip(draw, (x + chip_size / 2, label_y), colors[1][1], size=chip_size)
            x += chip_size + 8
            _label(draw, (x, label_y), right_name, ind_font, anchor="lm")
        elif industry:
            n_chips = len(colors)
            chip_span = n_chips * (chip_size + 8) - 8 if n_chips else 0
            tw = draw.textlength(industry, font=ind_font)
            group_w = (chip_span + 12 if n_chips else 0) + tw
            group_left = mid_x - group_w / 2
            for ci, (_cname, hexfill) in enumerate(colors):
                _color_chip(
                    draw,
                    (group_left + chip_size / 2 + ci * (chip_size + 8), label_y),
                    hexfill,
                    size=chip_size,
                )
            _label(
                draw,
                (group_left + (chip_span + 12 if n_chips else 0), label_y),
                industry,
                ind_font,
                anchor="lm",
            )
        if spots:
            _label(
                draw,
                (mid_x, y + 14),
                spots,
                spot_font,
                anchor="mm",
                fill=INK,
            )

    ladder_dx = bot[0] - top[0]
    ladder_dy = bot[1] - top[1]
    yard_ends = [_ladder_x_at(ys[i]) for i in range(2, 6)]
    # 112 one 1-LED module east of 110 along Track 1 / East Lead
    x_east = top[0] + STEP_1LED
    me_turn_x = x_east - (lead_y - ys[6]) * ladder_dx / ladder_dy
    me_turn_x = max(me_turn_x, max(yard_ends) + 28)
    x_east = me_turn_x + (lead_y - ys[6]) * ladder_dx / ladder_dy
    # Prefer exact 1-LED pitch from 110 when Main East geometry allows
    if abs(x_east - (top[0] + STEP_1LED)) > 1:
        x_east = top[0] + STEP_1LED
        me_turn_x = x_east - (lead_y - ys[6]) * ladder_dx / ladder_dy

    # Main East through the yard — same west extent as Main West / S tracks
    _line(draw, (x_left, ys[6]), (me_turn_x, ys[6]), w=lw)
    _line(draw, (me_turn_x, ys[6]), (x_east, lead_y), w=lw)
    _arrow(draw, (x_left, ys[6]), direction="left", size=14)
    _label(
        draw,
        (x_left + 2, ys[6] - 22),
        "to Barn",
        note_font,
        anchor="lb",
        fill=INK,
    )
    # Main East above the rail (shared x with left Main West)
    industry_label_x = (x_left + max(yard_ends)) / 2
    _label(
        draw,
        (industry_label_x, ys[6] - 18),
        "Main East",
        track_font,
        anchor="mm",
    )
    # Main West left of 111, above the rail, aligned with industries / Main East
    _label(
        draw,
        (industry_label_x, ys[0] - 18),
        "Main West",
        track_font,
        anchor="mm",
    )

    _line(draw, (top[0], ys[1]), (x_east, lead_y), w=lw)
    # Same clearance as 110 — offset left of the junction, not on the rail
    _sw_badge(draw, (x_east - 36, lead_y - 28), "33", sw_font)
    _dot(draw, (x_east, lead_y), r=DOT_R)

    _line(draw, (x_east, lead_y), (x_right, lead_y), w=lw)
    lead_label_x = (x_east + x_right) / 2
    # Main East above the eastern lead
    _label(
        draw,
        (lead_label_x, lead_y - 18),
        "Main East",
        track_font,
        anchor="mm",
    )
    _label(
        draw,
        (lead_label_x, ys[0] - 18),
        "Main West",
        track_font,
        anchor="mm",
    )
    _arrow(draw, (x_right, lead_y), direction="right", size=14)
    # One destination note centered between Main West and Main East
    _label(
        draw,
        (x_right - 2, (ys[0] + lead_y) / 2),
        "to Princess",
        note_font,
        anchor="rm",
        fill=INK,
    )
    # Geographic north points right (same rose as SM-01 / linear5 panel)
    hooks.paste_compass(img, cx=width - pad - 115, cy=height - 185, size=230, north="up")
    return img
