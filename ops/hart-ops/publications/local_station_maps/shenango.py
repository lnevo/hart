"""Shenango (SM-05, upright and rotated) drawer."""

from __future__ import annotations

import math

from PIL import Image

from .kit import (
    ARIAL_BOLD,
    GEORGIA,
    GEORGIA_BOLD,
    INK,
    Hooks,
    _arrow,
    _color_chip,
    _dot,
    _label,
    _line,
    _sw_badge,
)


def draw_shenango(meta: dict, hooks: Hooks) -> Image.Image:
    """Shenango — 8×5: Princess, Main West/East, K-1/K-2, SW 113–115.

    LED pitch matches East End / Toggle_Dimensions.png:
      - dots Ø 3/16″ · 113 mid 3/8″ from each rail · Princess↔115 = 3/4″
    K-1/K-2 end at an open octagon (missing the left side between 114/115).

    meta['rotate180']: track plan rotated 180°; upright labels; compass N/S/E/W flipped.
    """
    width, height = 1600, 1000
    img, draw = hooks.canvas(width, height)
    pad = 56
    rot = bool(meta.get("rotate180"))
    # Rotation pivot — set to content center after layout is known
    rot_c = [width / 2.0, height / 2.0]

    def T(p):
        if not rot:
            return p
        return (2 * rot_c[0] - p[0], 2 * rot_c[1] - p[1])

    def line(a, b, **kw):
        _line(draw, T(a), T(b), **kw)

    def dot(p, **kw):
        _dot(draw, T(p), **kw)

    def lab(p, text, font, *, anchor="mm", fill=INK):
        # Under 180° rot, flip left/right anchors so text stays on the correct side
        if rot:
            anchor = (
                anchor.replace("l", "\x00").replace("r", "l").replace("\x00", "r")
            )
        _label(draw, T(p), text, font, anchor=anchor, fill=fill)

    def badge(p, text, font):
        _sw_badge(draw, T(p), text, font)

    def chip(p, hexfill, *, size=14):
        _color_chip(draw, T(p), hexfill, size=size)

    draw.text(
        (width // 2, 16),
        meta["title"].upper(),
        font=hooks.font(ARIAL_BOLD, 56),
        fill=INK,
        anchor="mt",
    )
    PX_PER_IN = 200.0
    DOT_R = ((3 / 16) * PX_PER_IN) / 2
    STEP_2LED = (3 / 8) * PX_PER_IN  # 75 — adjacent spots on 113
    STEP_1LED = (3 / 4) * PX_PER_IN  # 150 — Princess ↔ 115; full 113 diagonal
    track_font = hooks.font(ARIAL_BOLD, 22)
    note_font = hooks.font(GEORGIA, 18)
    cp_font = hooks.font(ARIAL_BOLD, 36)
    ind_font = hooks.font(GEORGIA_BOLD, 28)
    sw_font = hooks.font(ARIAL_BOLD, 20)
    lw = 3
    chip_size = 28

    # 113 is 45° with length STEP_1LED → track gap = STEP_1LED/√2
    track_gap = STEP_1LED / math.sqrt(2)
    oct_up = 100.0
    oct_dn = 100.0
    corner = 90.0
    label_pad = 28.0
    content_w = 1164.0
    content_h = label_pad + oct_up + track_gap + oct_dn + label_pad
    x_left = (width - content_w) / 2
    y_block = 58 + ((height - 140 - 58) - content_h) / 2
    if rot:
        rot_c[0] = x_left + content_w / 2
        rot_c[1] = y_block + content_h / 2
    y_top = y_block + label_pad
    y1 = y_top + oct_up
    y2 = y1 + track_gap
    y_bot = y2 + oct_dn
    x_p = x_left + 360.0
    x_end = x_left + 924.0
    x_vert = x_left + content_w
    x_tr = x_vert - corner

    princess = (x_p, y1)
    t113 = (x_p - track_gap, y2)
    ux113 = (t113[0] - princess[0]) / STEP_1LED
    uy113 = (t113[1] - princess[1]) / STEP_1LED
    mid113 = (princess[0] + ux113 * STEP_2LED, princess[1] + uy113 * STEP_2LED)
    t115 = (x_p + STEP_1LED, y1)
    t114 = (t115[0], y2)
    up115 = (t115[0] + 110, y_top)
    dn114 = (t114[0] + 110, y_bot)

    line((x_left, y1), (x_end, y1), w=lw)
    line((x_left, y2), (x_end, y2), w=lw)
    # Arrows point geographic west
    _arrow(draw, T((x_left, y1)), direction=("right" if rot else "left"), size=14)
    _arrow(draw, T((x_left, y2)), direction=("right" if rot else "left"), size=14)

    main_label_x = x_left + 110
    lab((main_label_x, y1 - 18), "Main West", track_font, anchor="mm")
    lab((main_label_x, y2 + 18), "Main East", track_font, anchor="mm")
    # Destination between the two mains (west → East End)
    lab(
        (x_left + 56, (y1 + y2) / 2),
        "to East End",
        note_font,
        anchor="lm",
        fill=INK,
    )

    k_label_x = (t114[0] + x_end) / 2
    lab((k_label_x, y1 - 18), "Track K-1", track_font, anchor="mm")
    lab((k_label_x, y2 + 18), "Track K-2", track_font, anchor="mm")

    # Coke Works: "S" lines up with the "T" in Track K-1 / K-2 (page-left upright)
    ind_y = (y1 + y2) / 2
    if rot:
        k_mid = T((k_label_x, ind_y))
        track_left_page = k_mid[0] - draw.textlength("Track K-1", font=track_font) / 2
        _color_chip(
            draw,
            (track_left_page - chip_size / 2 - 10, k_mid[1]),
            "000000",
            size=chip_size,
        )
        _label(
            draw,
            (track_left_page, k_mid[1]),
            "Shenango Coke Works",
            ind_font,
            anchor="lm",
        )
    else:
        track_left = k_label_x - draw.textlength("Track K-1", font=track_font) / 2
        chip((track_left - chip_size / 2 - 10, ind_y), "000000", size=chip_size)
        lab((track_left, ind_y), "Shenango Coke Works", ind_font, anchor="lm")

    lab(
        ((up115[0] + x_tr) / 2, y_top - 22),
        "McKee's Rocks / Scully Yard",
        note_font,
        anchor="mm",
        fill=INK,
    )
    lab(
        ((dn114[0] + x_tr) / 2, y_bot + 22),
        "McKeesport / Demmler Yard",
        note_font,
        anchor="mm",
        fill=INK,
    )

    dot(princess, r=DOT_R)
    line(princess, t113, w=lw)
    dot(mid113, r=DOT_R)
    dot(t113, r=DOT_R)
    lab((mid113[0], y1 - 48), "Princess", cp_font, anchor="mm")
    badge((mid113[0] + 44, mid113[1] + 4), "35", sw_font)

    line(t115, up115, w=lw)
    line(up115, (x_tr, y_top), w=lw)
    top_r = (x_vert, y_top + corner)
    line((x_tr, y_top), top_r, w=lw)
    dot(t115, r=DOT_R)

    line(t114, dn114, w=lw)
    line(dn114, (x_tr, y_bot), w=lw)
    bot_r = (x_vert, y_bot - corner)
    line((x_tr, y_bot), bot_r, w=lw)
    dot(t114, r=DOT_R)

    line(top_r, bot_r, w=lw)

    # 114 / 115 outside the octagon angles, Princess side of each switch
    # 115 even with K-1 (above); 114 even with K-2 (below)
    badge((t115[0] - 48, y1 - 28), "39", sw_font)
    badge((t114[0] - 48, y2 + 28), "37", sw_font)

    # Compass: flipped cardinals when plan is rotated 180°
    if rot:
        hooks.paste_compass(img, cx=width - pad - 115, cy=height - 185, size=230, north="down")
    else:
        hooks.paste_compass(img, cx=pad + 115, cy=height - 185, size=230, north="up")
    return img
