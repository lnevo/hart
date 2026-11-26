"""The compass rose of the station maps (SM-01 to SM-05), in the linear5 panel style.

One drawing serves every orientation: ``north`` names where the gold needle points, and the
cardinal letters follow it while staying upright.
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
    except KeyError:
        raise ValueError(f"compass north must be one of {sorted(ORIENTATIONS)}, not {north!r}") from None


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
