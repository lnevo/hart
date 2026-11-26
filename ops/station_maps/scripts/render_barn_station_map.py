#!/usr/bin/env python3
"""Barn station map — Switch 7 / 9 / 11 / 13.

Layout Editor plant (TO117 xover, TO10, TO11, TO1) in the same sheet language
as West Yard / South Yard / East End. One slope for every non-horizontal:
Switch 7 is a three-dot crossover like East End 111; Switch 13's diverge is
a straight line to the EH-1 horizontal.

Print size matches the other local sheets: 8 in × 5 in (1600×1000 at 200 dpi).

    python3 ops/station_maps/scripts/render_barn_station_map.py
"""

from __future__ import annotations

import sys
from functools import partial
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sheet_kit  # noqa: E402  (sibling module)

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402
ROOT = paths.REPO_ROOT
OUT_CATS = ROOT / "ops/station_maps/maps/Neville_Island_Station_Map_Barn_0.png"
HOPS = ROOT / sheet_kit.HOPS_REL
DOCX_NAME = "Neville_Island_Station_Map_Barn.docx"
DOCX_TEMPLATE = ROOT / sheet_kit.SM_DOCX_TEMPLATE_REL

# 8 in × 5 in landscape, same as SM-02…SM-05.
DPI, W, H = sheet_kit.DPI, sheet_kit.W, sheet_kit.H
IN = float(DPI)

TRACK, INK, BADGE, BADGE_INK = sheet_kit.TRACK, sheet_kit.INK, sheet_kit.BADGE, sheet_kit.BADGE_INK
DOT_R = 16
# Clear air between the frog and the pill (103/111 sit off the circle, not on it).
BADGE_GAP = 18
COMPASS_RING = (40, 70, 110)
COMPASS_GOLD = sheet_kit.COMPASS_GOLD
COMPASS_N = (70, 110, 160)

# Shared slope: down-right (screen y grows down). Reverse is up-left.
# Matches East End 111 / 110–107.
RUN, RISE = 0.50, 1.00

Y_EH1 = 1.12 * IN
Y_EH2 = 1.68 * IN
Y_EH3 = 2.24 * IN
Y_BARN = 3.20 * IN
Y_MAIN = 4.04 * IN  # 0.84 in below Barn — 111-like crossover height

X_WEST = 0.32 * IN
X_EH = 0.95 * IN
X_EAST = 7.68 * IN

SW13 = (6.92 * IN, Y_BARN)
SW7_TOP = (2.05 * IN, Y_BARN)
SW9 = (4.55 * IN, Y_EH3)


_along = partial(sheet_kit.along, run=RUN, rise=RISE)


def _mid(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


SW7_BOT = _along(SW7_TOP, Y_MAIN - Y_BARN)
SW7_MID = _mid(SW7_TOP, SW7_BOT)
SW11 = _along(SW13, Y_EH3 - Y_BARN)
EH1_JOIN = _along(SW13, Y_EH1 - Y_BARN)
EH2_JOIN = _along(SW9, Y_EH2 - Y_EH3)


_font = sheet_kit.arial
_line = partial(sheet_kit.capped_line, fill=TRACK)


_arrow = partial(sheet_kit.arrow, fill=TRACK)


_dot = partial(sheet_kit.dot, r=DOT_R, fill=TRACK)
_badge_near = partial(sheet_kit.badge_near, dot_r=DOT_R, gap=BADGE_GAP, fill=BADGE, ink=BADGE_INK)


def _compass(d, cx, cy, r=58):
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
    f = _font(14, bold=True)
    d.text((cx, cy - r - 5), "N", font=f, fill=INK, anchor="ms")
    d.text((cx, cy + r + 5), "S", font=f, fill=INK, anchor="mt")
    d.text((cx - r - 7, cy), "W", font=f, fill=INK, anchor="rm")
    d.text((cx + r + 7, cy), "E", font=f, fill=INK, anchor="lm")


def render(out: Path) -> None:
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    f_title = _font(56, black=True)
    f_track = _font(22, bold=True)
    f_dest = _font(16)
    f_num = _font(20, bold=True)

    # Official SM titles sit at y≈16 with 42 px ink (Arial Black 56).
    d.text((W / 2, 37), "BARN", font=f_title, fill=INK, anchor="mm")

    # Horizontals
    _line(d, (X_WEST, Y_BARN), (X_EAST, Y_BARN), 6)
    _line(d, (X_WEST, Y_MAIN), (X_EAST, Y_MAIN), 6)
    _line(d, (X_EH, Y_EH1), EH1_JOIN, 5)
    _line(d, (X_EH, Y_EH2), EH2_JOIN, 5)
    _line(d, (X_EH, Y_EH3), SW11, 5)

    # One slope: 7 xover, 13→EH-1, EH-2→9
    _line(d, SW7_TOP, SW7_BOT, 6)
    _line(d, SW13, EH1_JOIN, 5)
    _line(d, EH2_JOIN, SW9, 5)

    _arrow(d, (X_WEST, Y_BARN), "left")
    _arrow(d, (X_WEST, Y_MAIN), "left")
    _arrow(d, (X_EAST, Y_BARN), "right")
    _arrow(d, (X_EAST, Y_MAIN), "right")

    for pt in (SW7_TOP, SW7_MID, SW7_BOT, SW9, SW11, SW13):
        _dot(d, pt)

    # 7 like East End 111 (west of the xover); 9/11 like 103 (NE); 13 like 110 (NW).
    _badge_near(d, SW7_MID, "7", f_num, "w")
    _badge_near(d, SW9, "9", f_num, "ne")
    _badge_near(d, SW11, "11", f_num, "ne")
    _badge_near(d, SW13, "13", f_num, "nw")

    gap = 10
    d.text((SW7_TOP[0] - 0.55 * IN, Y_BARN - gap), "Scale", font=f_track, fill=INK, anchor="ms")
    d.text((4.55 * IN, Y_BARN - gap), "Barn", font=f_track, fill=INK, anchor="ms")
    d.text((4.55 * IN, Y_MAIN - gap), "Main East", font=f_track, fill=INK, anchor="ms")
    d.text((2.35 * IN, Y_EH1 - gap), "EH-1", font=f_track, fill=INK, anchor="ms")
    d.text((2.35 * IN, Y_EH2 - gap), "EH-2", font=f_track, fill=INK, anchor="ms")
    d.text((2.35 * IN, Y_EH3 - gap), "EH-3", font=f_track, fill=INK, anchor="ms")

    d.text(
        ((X_WEST + SW7_TOP[0]) / 2, (Y_BARN + Y_MAIN) / 2),
        "to Plane",
        font=f_dest,
        fill=INK,
        anchor="mm",
    )
    d.text((X_EAST - 0.08 * IN, Y_BARN - 36), "to South Yard", font=f_dest, fill=INK, anchor="rm")
    d.text((X_EAST - 0.08 * IN, Y_MAIN - 36), "to East End", font=f_dest, fill=INK, anchor="rm")

    _compass(d, 0.82 * IN, 4.52 * IN, r=50)

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    print(f"wrote {out} ({W}x{H})")


def _write_docx(png: Path, dest: Path) -> None:
    """The SM-series landscape docx with the Barn map in it."""
    sheet_kit.write_sheet_docx(DOCX_TEMPLATE, png, dest,
                               media_names=("station_map_west_yard.png", "station_map_barn.png"),
                               title="Neville Island Station Map — Barn")


def main() -> None:
    render(OUT_CATS)
    if HOPS.is_dir():
        _write_docx(OUT_CATS, ROOT / "docs/ops" / DOCX_NAME)


if __name__ == "__main__":
    main()
