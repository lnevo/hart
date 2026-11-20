"""West Yard (SM-02) drawer."""

from __future__ import annotations

import math

from PIL import Image

from .kit import (
    ARIAL_BOLD,
    GEORGIA,
    INK,
    Hooks,
    _arrow,
    _dot,
    _label,
    _line,
    _outset,
    _sw_badge,
)


def draw_west_yard(meta: dict, hooks: Hooks) -> Image.Image:
    """West Yard — 8×5 landscape: Main West ↔ Brick, W-1/W-2 stubs, Plane.

    Brick ↔ west turnout at 3/4″. W-1 above / W-2 below stub ends.
    Brick lead is an octagon face: down-left (∥ W-2) → vertical → down-right
    to Plane; Main East continues one more down-right leg. Polygon strokes
    keep the first diagonal clean (no mid-line jog).
    """
    width, height = 1600, 1000
    img, draw = hooks.canvas(width, height)
    pad = 56
    draw.text(
        (width // 2, 16),
        meta["title"].upper(),
        font=hooks.font(ARIAL_BOLD, 56),
        fill=INK,
        anchor="mt",
    )
    track_font = hooks.font(ARIAL_BOLD, 22)
    note_font = hooks.font(GEORGIA, 18)
    cp_font = hooks.font(ARIAL_BOLD, 36)
    sw_font = hooks.font(ARIAL_BOLD, 20)
    lw = 3
    DOT_R = (3 / 16) * 200.0 / 2
    STEP = 150  # 3/4″ Brick ↔ turnout
    LEG = 150  # equal 45° octagon legs
    s = LEG / math.sqrt(2)
    dl = (-s, s)  # down-left (∥ W-2)
    dr = (s, s)  # down-right
    vert = 110  # south face of the octagon

    # Rails run nearly to the page edges (room only for arrowheads)
    x_left = 22
    x_right = width - 22

    # MW → ME: SW leg + vertical + SE leg + SE leg to ME
    span = vert + 3 * s
    above = 78  # switch badges + larger labels above MW
    below = 70  # labels below ME
    block_h = above + span + below
    y_mw = (height - block_h) / 2 + above
    # Shift left so Brick + west turnout sit near page center
    brick = (920.0, float(y_mw))
    turnout = (brick[0] - STEP, brick[1])

    # Parallel down-left: W-2 from turnout, lead from Brick
    w2_corner = (turnout[0] + dl[0], turnout[1] + dl[1])
    p1 = (brick[0] + dl[0], brick[1] + dl[1])
    p2 = (p1[0], p1[1] + vert)  # bottom of vertical (octagon south face)
    # Plane at end of first SE leg — West Lead turns east; ME continues SE
    plane = (p2[0] + dr[0], p2[1] + dr[1])
    y_wl = plane[1]
    me_turn = (plane[0] + dr[0], plane[1] + dr[1])
    y_me = me_turn[1]

    # Rails to the edge; arrows/notes sit slightly inboard
    tip_x = x_right - 5

    # Main West from east to Brick
    _line(draw, (brick[0], y_mw), (tip_x, y_mw), w=lw)
    _dot(draw, brick, r=DOT_R)
    _sw_badge(draw, (brick[0] + 56, y_mw - 44), "1", sw_font)
    _label(draw, (brick[0] + 28, y_mw + 56), "Brick", cp_font, anchor="mm")
    _label(
        draw,
        ((brick[0] + tip_x) / 2, y_mw - 18),
        "Main West",
        track_font,
        anchor="mm",
    )
    _arrow(draw, (tip_x, y_mw), direction="right", size=18)
    _label(
        draw,
        (tip_x - 2, y_mw + 34),
        "to East End",
        note_font,
        anchor="rt",
        fill=INK,
    )

    # Brick → turnout (3/4″) with spot; W-1 / W-2 stubs
    _line(draw, brick, turnout, w=lw)
    _dot(draw, turnout, r=DOT_R)
    _sw_badge(draw, (turnout[0] - 56, y_mw - 44), "3", sw_font)

    _line(draw, (x_left, y_mw), turnout, w=lw)
    _line(draw, turnout, w2_corner, w=lw)
    _line(draw, (x_left, w2_corner[1]), w2_corner, w=lw)
    # Stub labels: same x (centered on stub run); W-1 above, W-2 below
    stub_label_x = (x_left + min(turnout[0], w2_corner[0])) / 2
    _label(draw, (stub_label_x, y_mw - 18), "W-1", track_font, anchor="mm")
    _label(draw, (stub_label_x, w2_corner[1] + 20), "W-2", track_font, anchor="mt")

    # Octagon face: down-left (∥ W-2) → vertical → down-right to Plane
    _line(draw, brick, p1, w=lw)
    _line(draw, p1, p2, w=lw)
    _line(draw, p2, plane, w=lw)
    _dot(draw, plane, r=DOT_R)
    _label(draw, (plane[0] - 60, plane[1]), "Plane", cp_font, anchor="rm")
    _sw_badge(draw, (plane[0] + 56, plane[1] - 44), "5", sw_font)

    # West Lead turns right at Plane → South Yard
    _line(draw, plane, (tip_x, y_wl), w=lw)
    _arrow(draw, (tip_x, y_wl), direction="right", size=18)
    _label(
        draw,
        (tip_x - 2, y_wl - 36),
        "to South Yard",
        note_font,
        anchor="rt",
        fill=INK,
    )
    # Barn on the right (same span as before), down-left like South Yard.
    track_label_x = (brick[0] + tip_x) / 2
    # Old down-right Barn spanned track_label_x+58 → +58+dr; flip in place.
    barn_top_x = track_label_x + 58 + dr[0]
    max_top_x = tip_x - 100
    if barn_top_x > max_top_x:
        barn_top_x = max_top_x
    barn_top = (barn_top_x, y_wl)
    barn_bot = (barn_top[0] - dr[0], barn_top[1] + dr[1])  # down-left (/)
    barn_mid_x = (barn_top[0] + barn_bot[0]) / 2
    # Trapezoid bottom: ME between Plane→ME turn and Barn foot
    me_label_x = (me_turn[0] + barn_bot[0]) / 2
    _label(
        draw,
        (me_label_x, y_wl - 18),
        "West Lead",
        track_font,
        anchor="mm",
    )

    # Main East continues past Plane on the same diagonal, then right → East End.
    # Outset diagonals past the junction so they don't pile onto the horizontal.
    me_diag_start = _outset(plane, me_turn, DOT_R)
    _line(draw, me_diag_start, me_turn, w=lw)
    _line(draw, me_turn, (tip_x, y_me), w=lw)
    barn_diag_start = _outset(barn_top, barn_bot, lw)
    _line(draw, barn_diag_start, barn_bot, w=lw)
    _label(
        draw,
        (barn_mid_x, y_wl - 52),
        "Barn",
        cp_font,
        anchor="mm",
    )

    _arrow(draw, (tip_x, y_me), direction="right", size=18)
    _label(
        draw,
        (tip_x - 2, y_me + 34),
        "to East End",
        note_font,
        anchor="rt",
        fill=INK,
    )
    _label(draw, (me_label_x, y_me + 18), "Main East", track_font, anchor="mt")

    hooks.paste_compass(img, cx=pad + 115, cy=height - 185, size=230, north="up")
    return img
