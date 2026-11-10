#!/usr/bin/env python3
"""Rebuild Neville Island local station maps (SM-02 … SM-05).

Detail schematics for West Yard, South Yard, Industries, and Shenango —
track numbers / spur names derived from:
  - publications/assets/dispatcher_panel_neville_island.png
  - SM-01 subdivision diagram + seed industry spot names

Usage (from repo root):
  .venv/bin/python publications/rebuild_local_station_maps.py

Writes PNGs under publications/assets/ and letter docs under docs/.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT.parents[1] / "docs/ops"
PUB = Path(__file__).resolve().parent
ASSETS = PUB / "assets"
sys.path.insert(0, str(PUB))

from hart_pub_helpers import (  # noqa: E402
    ACCENT,
    MUTED,
    _set_run_font,
    add_publication_footer,
    set_letter_portrait,
    set_page_size,
)
from rebuild_station_map import _paste_compass  # noqa: E402

# Switch pills use the CTC numbers (ADR-005), not the old 100-series.
SWNUM = {100: 1, 101: 3, 102: 5, 103: 15, 104: 17, 105: 19, 106: 21, 107: 25, 108: 27, 109: 29, 110: 31, 111: 23, 112: 33, 113: 35, 114: 37, 115: 39}

# TT-23 palette (match SM-01)
BG = (255, 255, 255)
INK = (0x16, 0x16, 0x16)
RULE = (0x16, 0x16, 0x16)
MUTED_INK = (0x4A, 0x4A, 0x4A)
SW_FILL = (0x0F, 0x47, 0x61)
ACCENT_RED = (0x5C, 0x16, 0x16)

GEORGIA = "/System/Library/Fonts/Supplemental/Georgia.ttf"
GEORGIA_BOLD = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"
ARIAL_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
ARIAL = "/System/Library/Fonts/Supplemental/Arial.ttf"

MAPS = [
    {
        "key": "west_yard",
        "title": "West Yard",
        "pub_id": "SM-02",
        "revision": "A",
        "effective": "23 July 2026",
        "subtitle": "",
        "docx": DOCS / "Neville_Island_Station_Map_West_Yard.docx",
        "png": ASSETS / "station_map_west_yard.png",
        "minimal_chrome": True,
        "sheet": "8x5",
        "png_only": True,
    },
    {
        "key": "south_yard",
        "title": "South Yard",
        "pub_id": "SM-03",
        "revision": "A",
        "effective": "23 July 2026",
        "subtitle": "",
        "docx": DOCS / "Neville_Island_Station_Map_South_Yard.docx",
        "png": ASSETS / "station_map_south_yard.png",
        "minimal_chrome": True,
        "sheet": "8x5",
        "png_only": True,
    },
    {
        "key": "industries",
        "title": "East End",
        "pub_id": "SM-04",
        "revision": "A",
        "effective": "23 July 2026",
        "subtitle": "",
        "docx": DOCS / "Neville_Island_Station_Map_East_End.docx",
        "png": ASSETS / "station_map_east_end.png",
        "minimal_chrome": True,
        "sheet": "8x5",
        "png_only": True,
    },
    {
        "key": "shenango",
        "title": "Shenango",
        "pub_id": "SM-05",
        "revision": "B",
        "effective": "7 November 2026",
        "subtitle": "",
        "docx": DOCS / "Neville_Island_Station_Map_Shenango.docx",
        "png": ASSETS / "station_map_shenango.png",
        "minimal_chrome": True,
        "sheet": "8x5",
        "png_only": True,
        "skip": True,  # drawn by hart/ops/station_maps/scripts/render_shenango_station_map.py
    },
    {
        "key": "shenango",
        "title": "Shenango",
        "pub_id": "SM-05",
        "revision": "B",
        "effective": "7 November 2026",
        "subtitle": "",
        "docx": DOCS / "Neville_Island_Station_Map_Shenango_Rotated.docx",
        "png": ASSETS / "station_map_shenango_rotated.png",
        "minimal_chrome": True,
        "sheet": "8x5",
        "png_only": True,
        "rotate180": True,
        "skip": True,
    },
]


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _line(draw: ImageDraw.ImageDraw, a, b, *, w: int = 4, fill=INK) -> None:
    """Thick rail as a constant-width polygon (no end caps — junctions use dots)."""
    x0, y0 = float(a[0]), float(a[1])
    x1, y1 = float(b[0]), float(b[1])
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return
    px = -dy / length * (w / 2)
    py = dx / length * (w / 2)
    draw.polygon(
        [
            (x0 + px, y0 + py),
            (x1 + px, y1 + py),
            (x1 - px, y1 - py),
            (x0 - px, y0 - py),
        ],
        fill=fill,
    )


def _outset(a, b, dist: float):
    """Point dist along a→b from a."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return a
    return (a[0] + dx / length * dist, a[1] + dy / length * dist)


def _dot(draw: ImageDraw.ImageDraw, p, *, r: int = 7, fill=INK) -> None:
    x, y = p
    draw.ellipse([x - r, y - r, x + r, y + r], fill=fill, outline=fill)


def _label(draw, p, text, font, *, anchor="mm", fill=INK) -> None:
    draw.text(p, text, font=font, fill=fill, anchor=anchor)


def _arrow(draw, tip, *, direction: str, size: int = 14, fill=INK) -> None:
    x, y = tip
    if direction == "right":
        pts = [(x, y), (x - size, y - size * 0.55), (x - size, y + size * 0.55)]
    elif direction == "left":
        pts = [(x, y), (x + size, y - size * 0.55), (x + size, y + size * 0.55)]
    elif direction == "up":
        pts = [(x, y), (x - size * 0.55, y + size), (x + size * 0.55, y + size)]
    else:
        pts = [(x, y), (x - size * 0.55, y - size), (x + size * 0.55, y - size)]
    draw.polygon(pts, fill=fill)


def _sw_badge(draw, p, text: str, font) -> None:
    """Small switch-number pill on the diagram."""
    x, y = p
    tw = draw.textlength(text, font=font)
    pad_x, pad_y = 7, 3
    w, h = tw + pad_x * 2, font.size + pad_y * 2
    box = [x - w / 2, y - h / 2, x + w / 2, y + h / 2]
    draw.rounded_rectangle(box, radius=8, fill=SW_FILL)
    draw.text((x, y), text, font=font, fill=(255, 255, 255), anchor="mm")


def _cp_box(draw, p, text: str, font) -> None:
    """Control-point label in a light box (panel style)."""
    x, y = p
    tw = draw.textlength(text, font=font)
    pad_x, pad_y = 8, 4
    w, h = tw + pad_x * 2, font.size + pad_y * 2
    box = [x - w / 2, y - h / 2, x + w / 2, y + h / 2]
    draw.rectangle(box, fill=(255, 255, 255), outline=INK, width=2)
    draw.text((x, y), text, font=font, fill=INK, anchor="mm")


def _canvas(width: int = 1600, height: int = 1100) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (width, height), BG)
    return img, ImageDraw.Draw(img)


def _chrome(
    draw: ImageDraw.ImageDraw,
    *,
    width: int,
    height: int,
    title: str,
    subtitle: str = "",
    pub_id: str = "",
    revision: str = "",
    minimal: bool = False,
) -> tuple[int, int, int, int]:
    """Title / footer chrome. Returns content box (left, top, right, bottom).

    minimal=True: title + WEST/EAST only (no subtitle, rules, or publication footer).
    """
    margin = 48
    title_font = _font(ARIAL_BOLD, 36)
    sub_font = _font(GEORGIA, 20)
    foot_font = _font(GEORGIA, 16)
    foot_bold = _font(GEORGIA_BOLD, 16)
    dir_font = _font(ARIAL, 14)

    draw.text((width // 2, 28), title.upper(), font=title_font, fill=INK, anchor="mt")

    if minimal:
        draw.text((margin, height - 36), "← WEST", font=dir_font, fill=MUTED_INK, anchor="lm")
        draw.text((width - margin, height - 36), "EAST →", font=dir_font, fill=MUTED_INK, anchor="rm")
        return margin + 20, 90, width - margin - 20, height - 56

    if subtitle:
        draw.text((width // 2, 72), subtitle, font=sub_font, fill=MUTED_INK, anchor="mt")
    draw.line([(margin, 98), (width - margin, 98)], fill=RULE, width=4)

    foot_y = height - 56
    draw.line([(margin, foot_y), (width - margin, foot_y)], fill=RULE, width=3)
    draw.text(
        (width // 2, foot_y + 10),
        f"Publication {pub_id}  ·  Revision {revision}",
        font=foot_font,
        fill=INK,
        anchor="mt",
    )
    draw.text(
        (width // 2, foot_y + 30),
        "Official Publication  ·  Neville Island Operations",
        font=foot_bold,
        fill=INK,
        anchor="mt",
    )

    draw.text((margin, height - 78), "← WEST", font=dir_font, fill=MUTED_INK, anchor="lm")
    draw.text((width - margin, height - 78), "EAST →", font=dir_font, fill=MUTED_INK, anchor="rm")

    return margin + 20, 120, width - margin - 20, foot_y - 36


# ─── Individual maps ─────────────────────────────────────────────────────────


def draw_west_yard(meta: dict) -> Image.Image:
    """West Yard — 8×5 landscape: Main West ↔ Brick, W-1/W-2 stubs, Plane.

    Brick ↔ west turnout at 3/4″. W-1 above / W-2 below stub ends.
    Brick lead is an octagon face: down-left (∥ W-2) → vertical → down-right
    to Plane; Main East continues one more down-right leg. Polygon strokes
    keep the first diagonal clean (no mid-line jog).
    """
    width, height = 1600, 1000
    img, draw = _canvas(width, height)
    pad = 56
    draw.text(
        (width // 2, 16),
        meta["title"].upper(),
        font=_font(ARIAL_BOLD, 56),
        fill=INK,
        anchor="mt",
    )
    track_font = _font(ARIAL_BOLD, 22)
    note_font = _font(GEORGIA, 18)
    cp_font = _font(ARIAL_BOLD, 36)
    sw_font = _font(ARIAL_BOLD, 20)
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

    _paste_compass(img, cx=pad + 115, cy=height - 185, size=230, north="up")
    return img


def draw_south_yard(meta: dict) -> Image.Image:
    """c3 South Yard — 8×5 landscape (inverse of East End ladder geometry).

    Same LED pitch as East End / Toggle_Dimensions.png:
      - dots Ø 3/16″ · ladder 3/4″ between points
    Layout is centered on the Main East up-diagonal. Yard stubs and mains
    run to the right edge (with track labels past the rails), matching East End.
    """
    width, height = 1600, 1000
    img, draw = _canvas(width, height)
    pad = 56
    label_w = 96
    draw.text(
        (width // 2, 16),
        meta["title"].upper(),
        font=_font(ARIAL_BOLD, 56),
        fill=INK,
        anchor="mt",
    )
    PX_PER_IN = 200.0
    LED_D = (3 / 16) * PX_PER_IN
    DOT_R = LED_D / 2
    STEP_2LED = (3 / 8) * PX_PER_IN
    STEP_1LED = (3 / 4) * PX_PER_IN
    ladder_dx_step = 35.0
    track_gap = math.sqrt(STEP_1LED**2 - ladder_dx_step**2)
    ladder_slope = ladder_dx_step / track_gap  # dx/dy, down-right

    track_font = _font(ARIAL_BOLD, 22)
    note_font = _font(GEORGIA, 18)
    cp_font = _font(ARIAL_BOLD, 36)
    sw_font = _font(ARIAL_BOLD, 20)
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
    et_font = _font(ARIAL_BOLD, 16)
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
    _paste_compass(img, cx=pad + 115, cy=height - 185, size=230, north="up")
    return img


def _color_chip(draw: ImageDraw.ImageDraw, p, fill_hex: str, *, size: int = 14) -> None:
    x, y = p
    r = size / 2
    rgb = tuple(int(fill_hex[i : i + 2], 16) for i in (0, 2, 4))
    draw.rectangle([x - r, y - r, x + r, y + r], fill=rgb, outline=INK, width=1)


def _hollow(draw: ImageDraw.ImageDraw, p, *, r: int = 6, w: int = 2, fill=INK) -> None:
    """Hollow circle highlight at a junction / control point."""
    x, y = p
    draw.ellipse([x - r, y - r, x + r, y + r], outline=fill, width=w)


def draw_industries(meta: dict) -> Image.Image:
    """c2 East End — 8×5 landscape printable schematic.

    Layout scale matches docs/Toggle_Dimensions.png (true print inches):
      - LED / map dots: Ø 3/16″
      - 111 (2-LED): mid point 3/8″ from each track along the diagonal
      - Yard ladder (1-LED): 3/4″ (3/8″×2) between adjacent points
    Canvas 1600×1000 on an 8×5 sheet → 200 px/in.
    """
    width, height = 1600, 1000
    img, draw = _canvas(width, height)
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

    track_font = _font(ARIAL_BOLD, 22)
    ind_font = _font(GEORGIA_BOLD, 28)
    spot_font = _font(GEORGIA, 16)
    note_font = _font(GEORGIA, 18)
    sw_font = _font(ARIAL_BOLD, 20)
    lw = 3
    chip_size = 28

    # track name, industry, colors, spot line under the rail
    rows = [
        ("Main West", None, [], None),
        ("Track S-R", None, [], None),
        (
            "Track S-1",
            "Aristech Plastics",
            [("YELLOW", "FFFF00")],
            "Pellets  ·  Chemicals  ·  Shipping",
        ),
        (
            "Track S-2",
            "Ferrellgas  ·  A. Stucki Co.",
            [("RED", "FF0000"), ("GREEN", "008000")],
            "LPG  ·  Crane  ·  Team",
        ),
        (
            "Track S-3",
            "Kosmos Cement",
            [("PINK", "FFC0CB")],
            "Cement  ·  Aggregate",
        ),
        (
            "Track S-4",
            "Calgon Carbon",
            [("PURPLE", "800080")],
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
        font=_font(ARIAL_BOLD, 56),
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
    _paste_compass(img, cx=width - pad - 115, cy=height - 185, size=230, north="up")
    return img


def draw_shenango(meta: dict) -> Image.Image:
    """Shenango — 8×5: Princess, Main West/East, K-1/K-2, SW 113–115.

    LED pitch matches East End / Toggle_Dimensions.png:
      - dots Ø 3/16″ · 113 mid 3/8″ from each rail · Princess↔115 = 3/4″
    K-1/K-2 end at an open octagon (missing the left side between 114/115).

    meta['rotate180']: track plan rotated 180°; upright labels; compass N/S/E/W flipped.
    """
    width, height = 1600, 1000
    img, draw = _canvas(width, height)
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
        font=_font(ARIAL_BOLD, 56),
        fill=INK,
        anchor="mt",
    )
    PX_PER_IN = 200.0
    DOT_R = ((3 / 16) * PX_PER_IN) / 2
    STEP_2LED = (3 / 8) * PX_PER_IN  # 75 — adjacent spots on 113
    STEP_1LED = (3 / 4) * PX_PER_IN  # 150 — Princess ↔ 115; full 113 diagonal
    track_font = _font(ARIAL_BOLD, 22)
    note_font = _font(GEORGIA, 18)
    cp_font = _font(ARIAL_BOLD, 36)
    ind_font = _font(GEORGIA_BOLD, 28)
    sw_font = _font(ARIAL_BOLD, 20)
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
        _paste_compass(img, cx=width - pad - 115, cy=height - 185, size=230, north="down")
    else:
        _paste_compass(img, cx=pad + 115, cy=height - 185, size=230, north="up")
    return img


DRAWERS = {
    "west_yard": draw_west_yard,
    "south_yard": draw_south_yard,
    "industries": draw_industries,
    "shenango": draw_shenango,
}


def rebuild_docx(meta: dict, png: Path) -> Path:
    doc = Document()

    # 8×5 landscape desk sheet — PNG only, full-bleed (margins in the PNG)
    if meta.get("sheet") == "8x5" or meta.get("png_only"):
        set_page_size(
            doc,
            width_in=8.0,
            height_in=5.0,
            margin_in=0.0,
            top_margin_in=0.0,
            bottom_margin_in=0.0,
        )
        section = doc.sections[0]
        section.header_distance = Inches(0)
        section.footer_distance = Inches(0)
        pic = doc.add_paragraph()
        pic.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pic.paragraph_format.space_before = Pt(0)
        pic.paragraph_format.space_after = Pt(0)
        pic.add_run().add_picture(str(png), width=Inches(8.0))
        doc.save(meta["docx"])
        return meta["docx"]

    set_letter_portrait(doc)
    section = doc.sections[0]
    section.top_margin = Inches(0.55)
    section.bottom_margin = Inches(0.55)
    section.left_margin = Inches(0.55)
    section.right_margin = Inches(0.55)

    minimal = bool(meta.get("minimal_chrome"))
    if not minimal:
        add_publication_footer(
            doc,
            pub_id=meta["pub_id"],
            revision=meta["revision"],
            effective=meta["effective"],
            compact=False,
        )

    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    t.paragraph_format.space_before = Pt(0)
    t.paragraph_format.space_after = Pt(2)
    r = t.add_run("HART RAILROAD")
    _set_run_font(r, size_pt=13, bold=True, color=ACCENT, name="Arial")

    s = doc.add_paragraph()
    s.alignment = WD_ALIGN_PARAGRAPH.CENTER
    s.paragraph_format.space_before = Pt(0)
    s.paragraph_format.space_after = Pt(2)
    r = s.add_run("Pittsburgh & Chartiers Valley Division  ·  Neville Island Operations")
    _set_run_font(r, size_pt=9.5, color=MUTED, name="Georgia")

    h = doc.add_paragraph()
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    h.paragraph_format.space_before = Pt(4)
    h.paragraph_format.space_after = Pt(2 if meta.get("subtitle") else 8)
    r = h.add_run(f"Station Map  ·  {meta['title']}")
    _set_run_font(r, size_pt=16, bold=True, color=ACCENT, name="Georgia")

    if meta.get("subtitle"):
        sub = doc.add_paragraph()
        sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sub.paragraph_format.space_before = Pt(0)
        sub.paragraph_format.space_after = Pt(8)
        r = sub.add_run(meta["subtitle"])
        _set_run_font(r, size_pt=10, color=MUTED, name="Georgia")

    pic = doc.add_paragraph()
    pic.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pic.paragraph_format.space_before = Pt(0)
    pic.paragraph_format.space_after = Pt(0)
    pic.add_run().add_picture(str(png), width=Inches(7.4))

    doc.save(meta["docx"])
    return meta["docx"]


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    for meta in MAPS:
        if meta.get("skip"):
            print(f"Skipped {meta['pub_id']} ({meta['png'].name}): drawn in the hart repo")
            continue
        drawer = DRAWERS[meta["key"]]
        img = drawer(meta)
        img.save(meta["png"], "PNG")
        docx = rebuild_docx(meta, meta["png"])
        print(f"Wrote {meta['png']}")
        print(f"Wrote {docx} ({meta['pub_id']} Rev {meta['revision']})")


if __name__ == "__main__":
    main()
