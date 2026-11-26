#!/usr/bin/env python3
"""
Generate linear4 JMRI panel background (1280×320): light blue field + river band along bottom.

Output: jmri/layouts/linear4/assets/linear4_panel_bg.png
Install for JMRI: preference:/linear4_panel_bg.png (see assets/README.md)
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

JMRI_ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = JMRI_ROOT / "layouts/linear4/assets/linear4_panel_bg.png"
WIDTH = 1280
HEIGHT = 320

# Light sky-blue panel field
SKY = (186, 210, 235)
SKY_MID = (200, 222, 244)
RIVER_DEEP = (150, 188, 220)
RIVER_MID = (130, 175, 215)
RIVER_SHIMMER = (170, 205, 232)
ACCENT_GOLD = (140, 118, 58)
ACCENT_STEEL = (72, 98, 128)


def _lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def _lerp_rgb(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (_lerp(c1[0], c2[0], t), _lerp(c1[1], c2[1], t), _lerp(c1[2], c2[2], t))


def generate(path: Path = OUT_PATH) -> Path:
    img = Image.new("RGB", (WIDTH, HEIGHT), SKY)
    draw = ImageDraw.Draw(img)

    # Soft vertical gradient (slightly richer blue toward bottom)
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        row = _lerp_rgb(SKY, SKY_MID, t * 0.35)
        draw.line([(0, y), (WIDTH, y)], fill=row)

    # River / industrial waterfront band (bottom ~22% of panel)
    band_top = HEIGHT - 70
    for y in range(band_top, HEIGHT):
        t = (y - band_top) / (HEIGHT - band_top)
        row = _lerp_rgb(RIVER_DEEP, RIVER_MID, t**0.7)
        draw.line([(0, y), (WIDTH, y)], fill=row)

    # Gentle wave crests (schematic, not photo-real)
    for x0 in range(-40, WIDTH + 40, 95):
        y0 = HEIGHT - 52
        draw.arc(
            [x0, y0, x0 + 110, y0 + 28],
            start=200,
            end=340,
            fill=RIVER_SHIMMER,
            width=1,
        )
    for x0 in range(30, WIDTH + 40, 120):
        y0 = HEIGHT - 38
        draw.arc(
            [x0, y0, x0 + 90, y0 + 22],
            start=190,
            end=350,
            fill=(_lerp(RIVER_SHIMMER[0], 255, 0.15), _lerp(RIVER_SHIMMER[1], 255, 0.15), _lerp(RIVER_SHIMMER[2], 255, 0.15)),
            width=1,
        )

    # Horizon rule + tie ticks (suggests track/industrial edge without clutter)
    y_rule = HEIGHT - 24
    draw.line([(0, y_rule), (WIDTH, y_rule)], fill=ACCENT_GOLD, width=1)
    draw.line([(0, y_rule + 1), (WIDTH, y_rule + 1)], fill=ACCENT_STEEL, width=1)
    for x in range(24, WIDTH, 48):
        draw.line([(x, y_rule + 2), (x, y_rule + 7)], fill=ACCENT_STEEL, width=1)

    # Subtle vignette on sides (keeps focus on track)
    for x in range(40):
        t = (40 - x) / 40
        for y in range(HEIGHT):
            base = img.getpixel((x, y))
            img.putpixel((x, y), _lerp_rgb(base, SKY, t * 0.35))
            base = img.getpixel((WIDTH - 1 - x, y))
            img.putpixel((WIDTH - 1 - x, y), _lerp_rgb(base, SKY, t * 0.35))

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG", optimize=True)
    return path


def main() -> None:
    out = generate()
    print(f"Wrote {out} ({WIDTH}×{HEIGHT})")


if __name__ == "__main__":
    main()
