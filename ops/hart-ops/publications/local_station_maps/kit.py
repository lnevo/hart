"""Shared pieces of the local station maps: switch numbers, palette, font paths and the
drawing primitives (rails, dots, labels, arrows, switch pills, colour chips).

rebuild_local_station_maps re-exports all of these; the drawers in this package read them
from here. Fonts, the canvas and the compass reach the drawers through Hooks, which the
entry module fills at call time so a test can replace them there.
"""

from __future__ import annotations

import math
import sys
from typing import Callable, NamedTuple

from PIL import Image, ImageDraw, ImageFont

# Switch pills use the CTC numbers (ADR-005), not the old 100-series.
SWNUM = {100: 1, 101: 3, 102: 5, 103: 15, 104: 17, 105: 19, 106: 21, 107: 25, 108: 27, 109: 29, 110: 31, 111: 23, 112: 33, 113: 35, 114: 37, 115: 39}

# TT-23 palette (match SM-01)
BG = (255, 255, 255)
INK = (0x16, 0x16, 0x16)
RULE = (0x16, 0x16, 0x16)
MUTED_INK = (0x4A, 0x4A, 0x4A)
SW_FILL = (0x0F, 0x47, 0x61)
ACCENT_RED = (0x5C, 0x16, 0x16)

from pub_fonts import ARIAL, ARIAL_BOLD, GEORGIA, GEORGIA_BOLD  # noqa: E402, F401  (re-exported)


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


def _color_chip(draw: ImageDraw.ImageDraw, p, fill_hex: str, *, size: int = 14) -> None:
    x, y = p
    r = size / 2
    rgb = tuple(int(fill_hex[i : i + 2], 16) for i in (0, 2, 4))
    draw.rectangle([x - r, y - r, x + r, y + r], fill=rgb, outline=INK, width=1)


def _hollow(draw: ImageDraw.ImageDraw, p, *, r: int = 6, w: int = 2, fill=INK) -> None:
    """Hollow circle highlight at a junction / control point."""
    x, y = p
    draw.ellipse([x - r, y - r, x + r, y + r], outline=fill, width=w)
