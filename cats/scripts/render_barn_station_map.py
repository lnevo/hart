#!/usr/bin/env python3
"""Barn station map — Switch 7 / 9 / 11 / 13 control-panel sheet.

Layout Editor plant (TO117 / TO10 / TO11 / TO1) drawn in the same sheet
language as West Yard / South Yard, spread so each turnout has a 3/4"
touch-toggle footprint (dual Ø3/16" pads, 3/8" apart).

Print the PNG 11 in wide (150 dpi). Rebuild:

    python3 cats/scripts/render_barn_station_map.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT_CATS = ROOT / "cats/docs/station_maps/Neville_Island_Station_Map_Barn_0.png"
OUT_PORTAL = ROOT / "consolidation/ops-portal/assets/maps/station_map_barn.png"

# 11 in × 7 in at 150 dpi — matches the other SM sheets' ~1.6 aspect.
DPI = 150
W = 11 * DPI
H = 7 * DPI
IN = float(DPI)

TRACK = (20, 20, 20)
INK = (16, 20, 24)
BADGE = (26, 90, 122)
BADGE_INK = (255, 255, 255)
TOGGLE = (120, 132, 142)
COMPASS_RING = (40, 70, 110)
COMPASS_GOLD = (201, 154, 40)
COMPASS_N = (70, 110, 160)

# LE topology, spread in sheet inches so 3/4" squares do not overlap.
Y_EH1 = 1.70 * IN
Y_EH2 = 2.30 * IN
Y_EH3 = 3.05 * IN
Y_BARN = 4.35 * IN
Y_MAIN = 5.85 * IN

X_WEST = 0.48 * IN
X_EH_END = 1.70 * IN
X_EAST = 10.50 * IN

# Frogs on the rails. Switch 7 toggle sits in the crossover opening, west
# of the thrown diagonal, so the 3/4" module does not cover the points.
SW7 = (2.85 * IN, Y_BARN)
SW7_TOGGLE = (2.05 * IN, (Y_BARN + Y_MAIN) / 2)
SW9 = (6.20 * IN, Y_EH3)
SW11 = (8.25 * IN, Y_EH3)
SW13 = (9.25 * IN, Y_BARN)


def _font(size: int, bold: bool = False, black: bool = False, narrow: bool = False):
    names = []
    if black:
        names.append("Arial Black.ttf")
    if narrow and bold:
        names.append("Arial Narrow Bold.ttf")
    if bold:
        names.append("Arial Bold.ttf")
    names.append("Arial.ttf")
    bases = [
        Path("/System/Library/Fonts/Supplemental"),
        Path("/Library/Fonts"),
        Path("/usr/share/fonts/truetype/macos"),
    ]
    for name in names:
        for base in bases:
            p = base / name
            if p.is_file():
                return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def _line(d: ImageDraw.ImageDraw, a, b, width=6):
    d.line([a, b], fill=TRACK, width=width)
    # round caps
    r = width / 2
    for x, y in (a, b):
        d.ellipse([x - r, y - r, x + r, y + r], fill=TRACK)


def _arrow(d: ImageDraw.ImageDraw, tip, direction: str, size=16):
    x, y = tip
    if direction == "left":
        pts = [(x, y), (x + size, y - size * 0.55), (x + size, y + size * 0.55)]
    else:
        pts = [(x, y), (x - size, y - size * 0.55), (x - size, y + size * 0.55)]
    d.polygon(pts, fill=TRACK)


def _label(d, xy, text, font, fill=INK, anchor="mm"):
    d.text(xy, text, font=font, fill=fill, anchor=anchor)


def _badge(d, cx, cy, text, font, dx=28, dy=-22):
    # teal pill, matching 103–106 on the South Yard sheet
    x, y = cx + dx, cy + dy
    pad_x = 11
    box = d.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    w, h = tw + pad_x * 2, max(22, th + 8)
    d.rounded_rectangle(
        [x, y, x + w, y + h],
        radius=6,
        fill=BADGE,
    )
    d.text((x + w / 2, y + h / 2 - 1), text, font=font, fill=BADGE_INK, anchor="mm")


def _dashed_rect(d, box, dash=8):
    x0, y0, x1, y1 = box
    d.rectangle(box, outline=TOGGLE, width=2)
    for x in range(int(x0), int(x1), dash * 2):
        d.line([(x, y0), (min(x + dash, x1), y0)], fill=(255, 255, 255), width=2)
        d.line([(x, y1), (min(x + dash, x1), y1)], fill=(255, 255, 255), width=2)
    for y in range(int(y0), int(y1), dash * 2):
        d.line([(x0, y), (x0, min(y + dash, y1))], fill=(255, 255, 255), width=2)
        d.line([(x1, y), (x1, min(y + dash, y1))], fill=(255, 255, 255), width=2)


def _toggle(d, cx, cy):
    """3/4 in module with dual Ø3/16 in pads, 3/8 in apart (drill guide)."""
    s = 0.75 * IN
    hole_r = (0.1875 * IN) / 2
    gap = 0.375 * IN
    half = s / 2
    _dashed_rect(d, [cx - half, cy - half, cx + half, cy + half])
    for hy in (cy - gap / 2, cy + gap / 2):
        d.ellipse(
            [cx - hole_r, hy - hole_r, cx + hole_r, hy + hole_r],
            outline=TOGGLE,
            width=2,
        )


def _compass(d, cx, cy, r=62):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=COMPASS_RING, width=3)
    d.ellipse(
        [cx - r + 8, cy - r + 8, cx + r - 8, cy + r - 8],
        outline=COMPASS_RING,
        width=2,
    )
    needle = r - 14
    d.polygon(
        [(cx, cy - needle), (cx + 9, cy + 4), (cx, cy + 8), (cx - 9, cy + 4)],
        fill=COMPASS_GOLD,
    )
    d.polygon(
        [(cx, cy + needle - 4), (cx + 8, cy - 2), (cx, cy + 6), (cx - 8, cy - 2)],
        fill=COMPASS_N,
    )
    f = _font(15, bold=True)
    d.text((cx, cy - r - 6), "N", font=f, fill=INK, anchor="ms")
    d.text((cx, cy + r + 6), "S", font=f, fill=INK, anchor="mt")
    d.text((cx - r - 8, cy), "W", font=f, fill=INK, anchor="rm")
    d.text((cx + r + 8, cy), "E", font=f, fill=INK, anchor="lm")


def render(out: Path) -> None:
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    f_title = _font(44, black=True)
    f_track = _font(18, bold=True)
    f_dest = _font(14)
    f_num = _font(16, bold=True)
    f_note = _font(13)

    d.text((W / 2, 42), "BARN", font=f_title, fill=INK, anchor="mm")

    # --- rails (LE plant, west → east) ---
    # Scale / West Lead / Track Barn / to South Yard (TO117 A–B, T6, TO1)
    _line(d, (X_WEST, Y_BARN), (X_EAST, Y_BARN), 6)
    # East Main Ext / Main East (TO117 D–C, T5)
    _line(d, (X_WEST, Y_MAIN), (X_EAST, Y_MAIN), 6)
    # Switch 7 thrown diagonal, West Lead down-right onto Main East
    # (same as the Barn mark on West Yard / South Yard).
    _line(d, SW7, (SW7[0] + 0.72 * IN, Y_MAIN), 6)

    # Engine House: EH-3 through 9–11; EH-2 into 9; EH-1 into 11 (LE T11/T10/T2)
    _line(d, (X_EH_END, Y_EH1), (SW11[0] - 0.55 * IN, Y_EH1), 5)
    _line(d, (SW11[0] - 0.55 * IN, Y_EH1), SW11, 5)
    _line(d, (X_EH_END, Y_EH2), (SW9[0] - 0.22 * IN, Y_EH2), 5)
    _line(d, (SW9[0] - 0.22 * IN, Y_EH2), SW9, 5)
    _line(d, (X_EH_END, Y_EH3), SW11, 5)

    # Switch 13 RH diverge up-west into Switch 11 (TO1 C → TO11 A)
    _line(d, SW13, SW11, 5)

    # destination arrows
    _arrow(d, (X_WEST, Y_BARN), "left")
    _arrow(d, (X_WEST, Y_MAIN), "left")
    _arrow(d, (X_EAST, Y_BARN), "right")
    _arrow(d, (X_EAST, Y_MAIN), "right")

    # 3/4 in toggle pads (drill / mount guides)
    _toggle(d, *SW7_TOGGLE)
    _toggle(d, *SW9)
    _toggle(d, *SW11)
    _toggle(d, *SW13)

    for cx, cy in (SW7, SW9, SW11, SW13):
        d.ellipse([cx - 11, cy - 11, cx + 11, cy + 11], fill=TRACK)

    _badge(d, SW7_TOGGLE[0], SW7_TOGGLE[1], "7", f_num, dx=48, dy=-18)
    _badge(d, SW9[0], SW9[1], "9", f_num, dx=22, dy=-52)
    _badge(d, SW11[0], SW11[1], "11", f_num, dx=26, dy=-52)
    _badge(d, SW13[0], SW13[1], "13", f_num, dx=-72, dy=-42)

    _label(d, (5.15 * IN, Y_BARN - 0.28 * IN), "West Lead / Track Barn", f_track)
    _label(d, (5.85 * IN, Y_MAIN + 0.32 * IN), "Main East", f_track)
    _label(d, (3.45 * IN, Y_EH1 - 0.18 * IN), "EH-1", f_track)
    _label(d, (3.45 * IN, Y_EH2 - 0.18 * IN), "EH-2", f_track)
    _label(d, (3.45 * IN, Y_EH3 - 0.18 * IN), "EH-3", f_track)

    _label(d, (X_WEST + 0.42 * IN, Y_BARN - 0.30 * IN), "to Scale", f_dest, anchor="lm")
    _label(d, (X_WEST + 0.42 * IN, Y_MAIN - 0.30 * IN), "to Plane", f_dest, anchor="lm")
    _label(d, (X_EAST - 0.12 * IN, Y_BARN - 0.55 * IN), "to South Yard", f_dest, anchor="rm")
    _label(d, (X_EAST - 0.12 * IN, Y_MAIN + 0.32 * IN), "to East End", f_dest, anchor="rm")

    _compass(d, 1.05 * IN, 6.38 * IN, r=52)

    _label(
        d,
        (W / 2, H - 16),
        "Print 11 in wide  ·  dashed squares are 3/4 in touch toggles  ·  3/16 in pads, 3/8 in apart",
        f_note,
        fill=(90, 96, 104),
        anchor="mm",
    )

    pads = [
        ("7", *SW7_TOGGLE),
        ("9", *SW9),
        ("11", *SW11),
        ("13", *SW13),
    ]
    min_sep = 0.75 * IN
    for i, (n1, x1, y1) in enumerate(pads):
        for n2, x2, y2 in pads[i + 1 :]:
            dx, dy = abs(x1 - x2), abs(y1 - y2)
            # axis-aligned squares overlap if both axes are closer than 3/4 in
            if dx < min_sep and dy < min_sep:
                raise SystemExit(
                    f"toggle {n1} overlaps {n2}: dx={dx / IN:.2f}in dy={dy / IN:.2f}in"
                )

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    print(f"wrote {out} ({W}x{H})")


def main() -> None:
    render(OUT_CATS)
    OUT_PORTAL.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUT_CATS, OUT_PORTAL)
    print(f"copied {OUT_PORTAL}")


if __name__ == "__main__":
    main()
