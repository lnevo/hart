"""Shared pieces of the local station maps: switch numbers, palette, font paths, the sheet's
LED pitch and the drawing primitives (rails, dots, labels, arrows, switch pills, colour chips).

rebuild_local_station_maps re-exports the palette, font paths and primitives; the drawers in
this package read them from here. Fonts, the canvas and the compass reach the drawers through
Hooks, which the entry module fills at call time so a test can replace them there.

pub_fonts sits beside this package in publications/. Importing kit puts that folder on sys.path
and refuses a pub_fonts loaded from another checkout.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from PIL import Image, ImageDraw, ImageFont

PUB = Path(__file__).resolve().parents[1]
if str(PUB) not in sys.path:
    sys.path.insert(0, str(PUB))

import pub_fonts  # noqa: E402

if Path(pub_fonts.__file__).resolve().parent != PUB:
    raise ImportError(
        f"pub_fonts was loaded from {pub_fonts.__file__}, not from {PUB}; "
        "another checkout is earlier on sys.path"
    )

Point = tuple[float, float]
RGB = tuple[int, int, int]

# Switch pills use the CTC numbers (ADR-005), not the old 100-series.
SWNUM = {100: 1, 101: 3, 102: 5, 103: 15, 104: 17, 105: 19, 106: 21, 107: 25, 108: 27, 109: 29, 110: 31, 111: 23, 112: 33, 113: 35, 114: 37, 115: 39}

# TT-23 palette (match SM-01)
BG = (255, 255, 255)
INK = (0x16, 0x16, 0x16)
RULE = (0x16, 0x16, 0x16)
MUTED_INK = (0x4A, 0x4A, 0x4A)
SW_FILL = (0x0F, 0x47, 0x61)
ACCENT_RED = (0x5C, 0x16, 0x16)

ARIAL = pub_fonts.ARIAL
ARIAL_BOLD = pub_fonts.ARIAL_BOLD
GEORGIA = pub_fonts.GEORGIA
GEORGIA_BOLD = pub_fonts.GEORGIA_BOLD

# Desk sheets: 8×5 in on a 1600×1000 canvas, 200 px per inch. The LED pitch follows
# docs/benchwork/station_maps_3d/Toggle_Dimensions.png in true print inches.
SHEET_W, SHEET_H = 1600, 1000
SHEET_PAD = 56
RAIL_W = 3
PX_PER_IN = 200.0
DOT_R = (3 / 16) * PX_PER_IN / 2  # LED dot, Ø 3/16″
STEP_2LED = (3 / 8) * PX_PER_IN  # two-LED switch: mid point to either track
STEP_1LED = (3 / 4) * PX_PER_IN  # one-LED ladder: adjacent points
LADDER_DX_STEP = 35.0  # the ladder's mild slant: horizontal run per track
LADDER_TRACK_GAP = math.sqrt(STEP_1LED**2 - LADDER_DX_STEP**2)
# Main East sits closer to S-4 than the ladder pitch: it is not on the ladder.
YARD_ME_GAP = LADDER_TRACK_GAP * 0.72
YARD_BLOCK_H = 5 * LADDER_TRACK_GAP + YARD_ME_GAP


class Hooks(NamedTuple):
    """What a drawer gets from rebuild_local_station_maps at call time."""

    font: Callable[[str, int], ImageFont.FreeTypeFont]
    canvas: Callable[..., tuple[Image.Image, ImageDraw.ImageDraw]]
    paste_compass: Callable[..., None]


def _font(path: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """The font at ``path``; a missing font falls back to the PIL default with a warning naming it."""
    try:
        return ImageFont.truetype(path, size)
    except OSError as exc:
        print(f"local station maps: cannot load font {path} ({exc}); using the PIL default font",
              file=sys.stderr)
        return ImageFont.load_default()


def _line(draw: ImageDraw.ImageDraw, a: Point, b: Point, *, w: float = 4, fill: RGB = INK) -> None:
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


def _outset(a: Point, b: Point, dist: float) -> Point:
    """Point dist along a→b from a."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return a
    return (a[0] + dx / length * dist, a[1] + dy / length * dist)


def _dot(draw: ImageDraw.ImageDraw, p: Point, *, r: float = 7, fill: RGB = INK) -> None:
    x, y = p
    draw.ellipse([x - r, y - r, x + r, y + r], fill=fill, outline=fill)


def _label(draw: ImageDraw.ImageDraw, p: Point, text: str, font: ImageFont.FreeTypeFont, *,
           anchor: str = "mm", fill: RGB = INK) -> None:
    draw.text(p, text, font=font, fill=fill, anchor=anchor)


def _arrow(draw: ImageDraw.ImageDraw, tip: Point, *, direction: str, size: float = 14, fill: RGB = INK) -> None:
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


def _sw_badge(draw: ImageDraw.ImageDraw, p: Point, text: str, font: ImageFont.FreeTypeFont) -> None:
    """Small switch-number pill on the diagram."""
    x, y = p
    tw = draw.textlength(text, font=font)
    pad_x, pad_y = 7, 3
    w, h = tw + pad_x * 2, font.size + pad_y * 2
    box = [x - w / 2, y - h / 2, x + w / 2, y + h / 2]
    draw.rounded_rectangle(box, radius=8, fill=SW_FILL)
    draw.text((x, y), text, font=font, fill=(255, 255, 255), anchor="mm")


def _cp_box(draw: ImageDraw.ImageDraw, p: Point, text: str, font: ImageFont.FreeTypeFont) -> None:
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


def _color_chip(draw: ImageDraw.ImageDraw, p: Point, fill_hex: str, *, size: float = 14) -> None:
    x, y = p
    r = size / 2
    rgb = tuple(int(fill_hex[i : i + 2], 16) for i in (0, 2, 4))
    draw.rectangle([x - r, y - r, x + r, y + r], fill=rgb, outline=INK, width=1)


def _hollow(draw: ImageDraw.ImageDraw, p: Point, *, r: float = 6, w: int = 2, fill: RGB = INK) -> None:
    """Hollow circle highlight at a junction / control point."""
    x, y = p
    draw.ellipse([x - r, y - r, x + r, y + r], outline=fill, width=w)


def _title(draw: ImageDraw.ImageDraw, x: float, title: str, hooks: Hooks) -> None:
    """The sheet title in capitals, centred on x at the top edge."""
    draw.text((x, 16), title.upper(), font=hooks.font(ARIAL_BOLD, 56), fill=INK, anchor="mt")


def _yard_rows(y_top: float) -> tuple[float, ...]:
    """Rail heights of the seven-track yard sheets (East End, South Yard).

    Main West, S-R and S-1 … S-4 one ladder pitch apart from y_top, then Main East YARD_ME_GAP below S-4.
    """
    g = LADDER_TRACK_GAP
    return (y_top, y_top + g, y_top + 2 * g, y_top + 3 * g, y_top + 4 * g, y_top + 5 * g,
            y_top + 5 * g + YARD_ME_GAP)


def _ladder_x_at(top: Point, bot: Point, y: float) -> float:
    """x of the straight ladder top → bot at height y."""
    t = (y - top[1]) / max(1.0, (bot[1] - top[1]))
    return top[0] + (bot[0] - top[0]) * t
