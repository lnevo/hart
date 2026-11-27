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
from typing import Literal, NamedTuple

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sheet_kit  # noqa: E402  (sibling module)
from sheet_kit import Corner, Point  # noqa: E402

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402
ROOT = paths.REPO_ROOT
sys.path.insert(0, str(ROOT / sheet_kit.PUBLICATIONS_REL))
import station_compass  # noqa: E402

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


def _mid(a: Point, b: Point) -> Point:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


SW7_BOT = _along(SW7_TOP, Y_MAIN - Y_BARN)
SW7_MID = _mid(SW7_TOP, SW7_BOT)
SW11 = _along(SW13, Y_EH3 - Y_BARN)
EH1_JOIN = _along(SW13, Y_EH1 - Y_BARN)
EH2_JOIN = _along(SW9, Y_EH2 - Y_EH3)


class Track(NamedTuple):
    """One straight piece of track, drawn with round caps."""

    a: Point
    b: Point
    width: int


class Badge(NamedTuple):
    """A switch number pill beside its frog dot."""

    frog: Point
    number: str
    corner: Corner


class Label(NamedTuple):
    """Text at (x, y) on the sheet, in the font named by ``size``."""

    text: str
    x: float
    y: float
    size: Literal["track", "dest"]
    anchor: str


# Drawn in this order: the horizontals, then the one slope (7 xover, 13→EH-1, EH-2→9).
TRACKS = (
    Track((X_WEST, Y_BARN), (X_EAST, Y_BARN), 6),
    Track((X_WEST, Y_MAIN), (X_EAST, Y_MAIN), 6),
    Track((X_EH, Y_EH1), EH1_JOIN, 5),
    Track((X_EH, Y_EH2), EH2_JOIN, 5),
    Track((X_EH, Y_EH3), SW11, 5),
    Track(SW7_TOP, SW7_BOT, 6),
    Track(SW13, EH1_JOIN, 5),
    Track(EH2_JOIN, SW9, 5),
)
ARROWS: tuple[tuple[Point, Literal["left", "right"]], ...] = (
    ((X_WEST, Y_BARN), "left"),
    ((X_WEST, Y_MAIN), "left"),
    ((X_EAST, Y_BARN), "right"),
    ((X_EAST, Y_MAIN), "right"),
)
FROGS = (SW7_TOP, SW7_MID, SW7_BOT, SW9, SW11, SW13)
# 7 like East End 111 (west of the xover); 9/11 like 103 (NE); 13 like 110 (NW).
BADGES = (
    Badge(SW7_MID, "7", "w"),
    Badge(SW9, "9", "ne"),
    Badge(SW11, "11", "ne"),
    Badge(SW13, "13", "nw"),
)
LABEL_GAP = 10  # track names sit this far above their rail
DEST_RISE = 36  # "to ..." names sit this far above their rail
X_LABEL_MID = 4.55 * IN
X_LABEL_EH = 2.35 * IN
X_DEST_EAST = X_EAST - 0.08 * IN
LABELS = (
    Label("Scale", SW7_TOP[0] - 0.55 * IN, Y_BARN - LABEL_GAP, "track", "ms"),
    Label("Barn", X_LABEL_MID, Y_BARN - LABEL_GAP, "track", "ms"),
    Label("Main East", X_LABEL_MID, Y_MAIN - LABEL_GAP, "track", "ms"),
    Label("EH-1", X_LABEL_EH, Y_EH1 - LABEL_GAP, "track", "ms"),
    Label("EH-2", X_LABEL_EH, Y_EH2 - LABEL_GAP, "track", "ms"),
    Label("EH-3", X_LABEL_EH, Y_EH3 - LABEL_GAP, "track", "ms"),
    Label("to Plane", (X_WEST + SW7_TOP[0]) / 2, (Y_BARN + Y_MAIN) / 2, "dest", "mm"),
    Label("to South Yard", X_DEST_EAST, Y_BARN - DEST_RISE, "dest", "rm"),
    Label("to East End", X_DEST_EAST, Y_MAIN - DEST_RISE, "dest", "rm"),
)
TITLE = "BARN"
TITLE_Y = 37  # SM titles sit at y≈16 with 42 px ink (Arial Black 56)
COMPASS = (0.82 * IN, 4.52 * IN, 50)  # centre x, centre y, ring radius


_font = sheet_kit.arial
_line = partial(sheet_kit.capped_line, fill=TRACK)
_arrow = partial(sheet_kit.arrow, fill=TRACK)
_dot = partial(sheet_kit.dot, r=DOT_R, fill=TRACK)
_badge_near = partial(sheet_kit.badge_near, dot_r=DOT_R, gap=BADGE_GAP, fill=BADGE, ink=BADGE_INK)


def draw_plan(d: ImageDraw.ImageDraw) -> None:
    """Title, track, frogs, switch pills, labels and compass onto ``d``."""
    f_title = _font(56, black=True)
    fonts = {"track": _font(22, bold=True), "dest": _font(16)}
    f_num = _font(20, bold=True)

    d.text((W / 2, TITLE_Y), TITLE, font=f_title, fill=INK, anchor="mm")
    for track in TRACKS:
        _line(d, track.a, track.b, track.width)
    for tip, direction in ARROWS:
        _arrow(d, tip, direction)
    for pt in FROGS:
        _dot(d, pt)
    for badge in BADGES:
        _badge_near(d, badge.frog, badge.number, f_num, badge.corner)
    for label in LABELS:
        d.text((label.x, label.y), label.text, font=fonts[label.size], fill=INK, anchor=label.anchor)
    cx, cy, r = COMPASS
    station_compass.draw_sheet_compass(d, cx, cy, r, style="kite", load_font=sheet_kit.load_font)


def render(out: Path) -> None:
    """Draw the Barn sheet and write it to ``out`` as PNG."""
    img = Image.new("RGB", (W, H), (255, 255, 255))
    draw_plan(ImageDraw.Draw(img))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    print(f"wrote {out} ({W}x{H})")


def _write_docx(png: Path, dest: Path) -> None:
    """The SM-series landscape docx with the Barn map in it."""
    sheet_kit.write_sheet_docx(DOCX_TEMPLATE, png, dest,
                               media_names=("station_map_west_yard.png", "station_map_barn.png"),
                               title="Neville Island Station Map — Barn")
    print(f"wrote {dest}")


def main() -> None:
    render(OUT_CATS)
    if HOPS.is_dir():
        try:
            _write_docx(OUT_CATS, ROOT / "docs/ops" / DOCX_NAME)
        except sheet_kit.SheetTemplateMissing as exc:
            raise SystemExit(f"render_barn_station_map: {exc}") from exc


if __name__ == "__main__":
    main()
