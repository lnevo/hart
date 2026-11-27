"""The compass roses of the station maps.

``compass_rose`` is the rose of SM-01 to SM-05, in the linear5 panel style. One drawing serves
every orientation: ``north`` names where the gold needle points, and the cardinal letters
follow it while staying upright.

``draw_sheet_compass`` draws the two ring compasses of the sheets in ops/station_maps/scripts
straight onto their canvas: ``"kite"`` (Barn) and ``"split"`` (Shenango, which turns with the
plan).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Literal, NamedTuple

from PIL import Image, ImageDraw, ImageFont

from pub_fonts import ARIAL_BOLD, font

North = Literal["right", "up", "down"]

COMPASS_RING = (0x2A, 0x3A, 0x55)
COMPASS_FILL = (0xFF, 0xFF, 0xFF)
COMPASS_GOLD_L = (0xD4, 0xA8, 0x2E)
COMPASS_GOLD_D = (0x9A, 0x72, 0x18)
COMPASS_BLUE_L = (0x9A, 0xA8, 0xB8)
COMPASS_BLUE_D = (0x3A, 0x4E, 0x68)

Vec = tuple[int, int]


class Orientation(NamedTuple):
    """Unit vectors (screen axes, y down) of one rose orientation."""

    north: Vec  # where the gold needle points
    light_side: Vec  # the half of each needle drawn in the light shade
    letters: dict[str, Vec]  # where each cardinal letter sits, drawn in N, E, S, W order


ORIENTATIONS: dict[str, Orientation] = {
    "right": Orientation((1, 0), (0, -1), {"N": (1, 0), "E": (0, 1), "S": (-1, 0), "W": (0, -1)}),
    "up": Orientation((0, -1), (-1, 0), {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}),
    "down": Orientation((0, 1), (-1, 0), {"N": (0, 1), "E": (-1, 0), "S": (0, -1), "W": (1, 0)}),
}


def _orientation(north: str) -> Orientation:
    try:
        return ORIENTATIONS[north]
    except KeyError as exc:
        raise ValueError(f"compass north must be one of {sorted(ORIENTATIONS)}, not {north!r}") from exc


def _needle(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    tip: float,
    half: float,
    direction: Vec,
    light_side: Vec,
    shades: tuple[tuple[int, int, int], tuple[int, int, int]],
) -> None:
    """One needle as two triangles: the light half on ``light_side``, the dark half opposite."""
    t = (cx + direction[0] * tip, cy + direction[1] * tip)
    light = (cx + light_side[0] * half, cy + light_side[1] * half)
    dark = (cx - light_side[0] * half, cy - light_side[1] * half)
    draw.polygon([t, light, (cx, cy)], fill=shades[0])
    draw.polygon([t, dark, (cx, cy)], fill=shades[1])


FontLoader = Callable[[str, int], "ImageFont.FreeTypeFont | ImageFont.ImageFont"]


def compass_rose(size: int = 180, north: str = "right", load_font: FontLoader | None = None) -> Image.Image:
    """The rose on a transparent square ``size`` px wide, North (gold) pointing ``north``.

    ``load_font`` loads the letter font; without one, pub_fonts.font, which raises FontMissing
    when the font is absent.
    """
    o = _orientation(north)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = size / 2
    r = size * 0.32  # room for the letters outside the ring
    ring_w = max(2, int(size * 0.018))
    thin = max(1, ring_w // 2)
    letter_font = (load_font or font)(ARIAL_BOLD, max(11, int(size * 0.13)))

    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=COMPASS_FILL, outline=COMPASS_RING, width=ring_w)
    r_in = r * 0.82
    draw.ellipse([cx - r_in, cy - r_in, cx + r_in, cy + r_in], outline=COMPASS_RING, width=thin)
    for ang in (45, 135, 225, 315):
        rad = math.radians(ang)
        x0 = cx + math.cos(rad) * r_in
        y0 = cy + math.sin(rad) * r_in
        x1 = cx + math.cos(rad) * r * 0.95
        y1 = cy + math.sin(rad) * r * 0.95
        draw.line([(x0, y0), (x1, y1)], fill=COMPASS_RING, width=thin)
    draw.line([(cx, cy - r * 0.72), (cx, cy + r * 0.72)], fill=COMPASS_RING, width=thin)
    draw.line([(cx - r * 0.72), (cy), (cx + r * 0.72), (cy)], fill=COMPASS_RING, width=thin)

    tip = r * 0.78
    half = r * 0.16
    south = (-o.north[0], -o.north[1])
    _needle(draw, cx, cy, tip, half, o.north, o.light_side, (COMPASS_GOLD_L, COMPASS_GOLD_D))
    _needle(draw, cx, cy, tip, half, south, o.light_side, (COMPASS_BLUE_L, COMPASS_BLUE_D))
    pr = max(2, int(size * 0.025))
    draw.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], fill=COMPASS_RING)

    label_r = r + size * 0.12
    for letter, (dx, dy) in o.letters.items():
        draw.text((cx + dx * label_r, cy + dy * label_r), letter, font=letter_font, fill=COMPASS_RING, anchor="mm")
    return img


def paste_compass(
    base: Image.Image, *, cx: float, cy: float, size: int, north: str = "right", load_font: FontLoader | None = None
) -> None:
    """Paste the rose centred on (cx, cy), its letters in a font from ``load_font``."""
    rose = compass_rose(size, north, load_font)
    base.paste(rose, (int(cx - size / 2), int(cy - size / 2)), rose)


# The ring compasses of ops/station_maps/scripts (draw_sheet_compass).
SheetCompassStyle = Literal["kite", "split"]

SHEET_GOLD = (201, 154, 40)
KITE_RING = (40, 70, 110)
KITE_SOUTH = (70, 110, 160)
KITE_LETTERS = (16, 20, 24)
KITE_LETTER_PX = 14
SPLIT_RING = (40, 58, 88)
SPLIT_GOLD_D = (168, 126, 28)
SPLIT_SOUTH_D = (60, 82, 112)
SPLIT_SOUTH_L = (150, 165, 185)
SPLIT_LETTER_PX = 28
SPLIT_NEEDLE = 58  # needle length in px, whatever the ring radius


def _kite_compass(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, letter_font: ImageFont.ImageFont) -> None:
    """Two rings, a gold kite needle north (up) and a blue one south; letters outside the ring."""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=KITE_RING, width=3)
    draw.ellipse([cx - r + 8, cy - r + 8, cx + r - 8, cy + r - 8], outline=KITE_RING, width=2)
    needle = r - 14
    draw.polygon([(cx, cy - needle), (cx + 9, cy + 4), (cx, cy + 8), (cx - 9, cy + 4)], fill=SHEET_GOLD)
    draw.polygon([(cx, cy + needle - 4), (cx + 8, cy - 2), (cx, cy + 6), (cx - 8, cy - 2)], fill=KITE_SOUTH)
    draw.text((cx, cy - r - 5), "N", font=letter_font, fill=KITE_LETTERS, anchor="ms")
    draw.text((cx, cy + r + 5), "S", font=letter_font, fill=KITE_LETTERS, anchor="mt")
    draw.text((cx - r - 7, cy), "W", font=letter_font, fill=KITE_LETTERS, anchor="rm")
    draw.text((cx + r + 7, cy), "E", font=letter_font, fill=KITE_LETTERS, anchor="lm")


def _split_compass(
    draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, turned: bool, letter_font: ImageFont.ImageFont
) -> None:
    """Two rings with an east-west bar and diagonal ticks, two-tone needles and a pivot.

    ``turned`` points north down, with the letters kept upright (S on top).
    """
    k = -1 if turned else 1
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=SPLIT_RING, width=4)
    draw.ellipse([cx - r + 12, cy - r + 12, cx + r - 12, cy + r - 12], outline=SPLIT_RING, width=2)
    draw.line([(cx - r + 12, cy), (cx + r - 12, cy)], fill=SPLIT_RING, width=2)
    for sx in (-1, 1):
        for sy in (-1, 1):
            draw.line([(cx + sx * (r - 12) * 0.707, cy + sy * (r - 12) * 0.707),
                       (cx + sx * (r - 1) * 0.707, cy + sy * (r - 1) * 0.707)], fill=SPLIT_RING, width=2)
    n = SPLIT_NEEDLE
    draw.polygon([(cx, cy - k * n), (cx + 11, cy), (cx, cy + k * 2), (cx - 11, cy)], fill=SHEET_GOLD)
    draw.polygon([(cx, cy - k * n), (cx - 11, cy), (cx, cy + k * 2)], fill=SPLIT_GOLD_D)
    draw.polygon([(cx, cy + k * n), (cx + 11, cy), (cx, cy - k * 2), (cx - 11, cy)], fill=SPLIT_SOUTH_D)
    draw.polygon([(cx, cy + k * n), (cx - 11, cy), (cx, cy - k * 2)], fill=SPLIT_SOUTH_L)
    draw.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=SPLIT_RING)
    top, bot, left, right = ("S", "N", "E", "W") if turned else ("N", "S", "W", "E")
    off = r + 28
    draw.text((cx, cy - off), top, font=letter_font, fill=SPLIT_RING, anchor="mm")
    draw.text((cx, cy + off), bot, font=letter_font, fill=SPLIT_RING, anchor="mm")
    draw.text((cx - off, cy), left, font=letter_font, fill=SPLIT_RING, anchor="mm")
    draw.text((cx + off, cy), right, font=letter_font, fill=SPLIT_RING, anchor="mm")


def draw_sheet_compass(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    r: float,
    *,
    style: SheetCompassStyle,
    load_font: FontLoader,
    turned: bool = False,
) -> None:
    """Draw a ring compass of radius ``r`` centred on (cx, cy), its letters in Arial Bold from ``load_font``.

    ``turned`` (north down) exists for the ``"split"`` style only.
    """
    if style == "kite":
        if turned:
            raise ValueError("the kite compass has no turned form; north always points up")
        _kite_compass(draw, cx, cy, r, load_font(ARIAL_BOLD, KITE_LETTER_PX))
    elif style == "split":
        _split_compass(draw, cx, cy, r, turned, load_font(ARIAL_BOLD, SPLIT_LETTER_PX))
    else:
        raise ValueError(f"sheet compass style must be 'kite' or 'split', not {style!r}")
