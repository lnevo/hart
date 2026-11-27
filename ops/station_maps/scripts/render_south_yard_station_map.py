#!/usr/bin/env python3
"""South Yard station map — Switch 7 / 13 / 15 / 17 / 19 / 21.

Starts from the published SM-03 sheet, whose ladder frogs carry the Digicon
CP / DCC 103–106 numbers, and restamps them with the live switch userNames.
Switch 7 is the three-dot Barn xover. The sheet's compact ET stub is covered
by a shrunken Barn engine-house plant (EH-1 / EH-2 / EH-3). Switch 13 sits on
Scale at that throat; the Barn block is the rail between 7 and 13.

    python3 ops/station_maps/scripts/render_south_yard_station_map.py
"""

from __future__ import annotations

import sys
from functools import partial
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sheet_kit  # noqa: E402  (sibling module)
from sheet_kit import Corner, Point  # noqa: E402

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402
ROOT = paths.REPO_ROOT
SRC = ROOT / "ops/station_maps/maps/src/south_yard_sheet.png"
OUT_CATS = ROOT / "ops/station_maps/maps/Neville_Island_Station_Map_South_Yard_0.png"
HOPS = ROOT / sheet_kit.HOPS_REL
DOCX_NAME = "Neville_Island_Station_Map_South_Yard.docx"
DOCX_TEMPLATE = ROOT / "docs/ops/Neville_Island_Station_Map_South_Yard.docx"

WHITE, TRACK, INK = sheet_kit.WHITE, sheet_kit.TRACK, sheet_kit.INK
BADGE, BADGE_INK = sheet_kit.BADGE, sheet_kit.BADGE_INK
DOT_R = 16
BADGE_GAP = 18
# Same slope as the Barn sheet (and East End 111 / 110–107).
RUN, RISE = 0.50, 1.00

# Ladder frogs on the published sheet (CP 103–106 there), stamped Switch 15/17/19/21.
SW15 = (850, 222)
SW17 = (883, 368)
SW19 = (917, 514)
SW21 = (953, 661)

# Switch 7 LH_XOVER: West Lead down-left onto Main East at Barn.
SW7_TOP = (411, 225)
SW7_BOT = (378, 370)
SW7_MID = ((SW7_TOP[0] + SW7_BOT[0]) / 2, (SW7_TOP[1] + SW7_BOT[1]) / 2)

# Shrunken Barn EH plant above Scale (replaces the compact ET stub).
# Switch 13 is the Scale frog at the published throat (~x=630).
Y_WL = 225.0
Y_EH1 = 108.0
Y_EH2 = 140.0
Y_EH3 = 172.0
X_EH = 340.0
SW13 = (632.0, Y_WL)


_along = partial(sheet_kit.along, run=RUN, rise=RISE)


SW11 = _along(SW13, Y_EH3 - Y_WL)
EH1_JOIN = _along(SW13, Y_EH1 - Y_WL)
SW9 = (X_EH + 0.50 * (SW11[0] - X_EH), Y_EH3)
EH2_JOIN = _along(SW9, Y_EH2 - Y_EH3)

OLD_BADGES = (
    (862, 184, 49, 27),
    (897, 330, 49, 27),
    (932, 475, 49, 27),
    (967, 621, 49, 27),
)
# Compact ET-1/2/3 stub + its join onto Scale (stop above the rail).
OLD_EH_STUB = (
    (318, 120, 340, 92),
    (618, 200, 24, 16),
)
# The published sheet names its five yard tracks at the right edge; each name is covered
# and written again with the track's current name.
TRACK_NAME_COVER_X = (1452, 1598)  # left and right of the white box over each old name
TRACK_NAME_HALF_H = 16
TRACK_NAME_X = 1456
TRACK_NAMES = (
    (225, "Track S-R"),
    (371, "Track S-1"),
    (516, "Track S-2"),
    (662, "Track S-3"),
    (808, "Track S-4"),
)
OLD_LABELS = (
    (201, 199, 108, 16),  # West Lead
    (350, 392, 88, 32),  # Barn (under Main East)
)
# Cover padding around each kind of old mark.
PAD_BADGE, PAD_EH_STUB, PAD_LABEL = 8, 2, 3

FROGS = (SW7_TOP, SW7_MID, SW7_BOT, SW13, SW15, SW17, SW19, SW21)
BADGES: tuple[tuple[Point, str, Corner], ...] = (
    (SW7_MID, "7", "w"),
    (SW13, "13", "e"),
    (SW15, "15", "ne"),
    (SW17, "17", "ne"),
    (SW19, "19", "ne"),
    (SW21, "21", "ne"),
)
EH_LABEL_DX = 72  # EH-1..3 names sit this far east of the EH west ends
EH_LABEL_GAP = 6
X_SCALE_LABEL = 254
TRACK_LABEL_GAP = 12

Box = tuple[int, int, int, int]  # x, y, width, height


class SourceSheetMissing(FileNotFoundError):
    """The published SM-03 sheet this map is drawn over is not in the checkout."""


_font = sheet_kit.arial
_line = partial(sheet_kit.capped_line, width=4, fill=TRACK)
_dot = partial(sheet_kit.dot, r=DOT_R, fill=TRACK)
_badge_near = partial(sheet_kit.badge_near, dot_r=DOT_R, gap=BADGE_GAP, fill=BADGE, ink=BADGE_INK)


def _cover(d: ImageDraw.ImageDraw, box: Box, pad: int) -> None:
    """Paint white over ``box`` and ``pad`` px around it."""
    x, y, w, h = box
    d.rectangle([x - pad, y - pad, x + w + pad, y + h + pad], fill=WHITE)


def cover_old_marks(d: ImageDraw.ImageDraw) -> None:
    """White out the published sheet's switch numbers, ET stub, labels and track names, and rename the tracks."""
    for box in OLD_BADGES:
        _cover(d, box, pad=PAD_BADGE)
    for box in OLD_EH_STUB:
        _cover(d, box, pad=PAD_EH_STUB)
    for box in OLD_LABELS:
        _cover(d, box, pad=PAD_LABEL)
    f_name = _font(22, bold=True)
    x0, x1 = TRACK_NAME_COVER_X
    for y, _name in TRACK_NAMES:
        d.rectangle([x0, y - TRACK_NAME_HALF_H, x1, y + TRACK_NAME_HALF_H], fill=WHITE)
    for y, name in TRACK_NAMES:
        d.text((TRACK_NAME_X, y), name, font=f_name, fill=INK, anchor="lm")


def draw_engine_house(d: ImageDraw.ImageDraw) -> None:
    """The shrunken Barn EH plant above Scale and the Scale / Barn names on the West Lead rail."""
    _line(d, (X_EH, Y_EH1), EH1_JOIN)
    _line(d, (X_EH, Y_EH2), EH2_JOIN)
    _line(d, (X_EH, Y_EH3), SW11)
    _line(d, SW13, EH1_JOIN)
    _line(d, EH2_JOIN, SW9)

    f_eh = _font(13, bold=True)
    f_track = _font(18, bold=True)
    for name, y in (("EH-1", Y_EH1), ("EH-2", Y_EH2), ("EH-3", Y_EH3)):
        d.text((X_EH + EH_LABEL_DX, y - EH_LABEL_GAP), name, font=f_eh, fill=INK, anchor="ms")
    d.text((X_SCALE_LABEL, Y_WL - TRACK_LABEL_GAP), "Scale", font=f_track, fill=INK, anchor="ms")
    d.text(((SW7_TOP[0] + SW13[0]) / 2, Y_WL - TRACK_LABEL_GAP), "Barn", font=f_track, fill=INK, anchor="ms")


def stamp_switches(d: ImageDraw.ImageDraw) -> None:
    """Frog dots and switch pills with the live switch numbers."""
    f_num = _font(20, bold=True)
    for pt in FROGS:
        _dot(d, pt)
    for frog, number, corner in BADGES:
        _badge_near(d, frog, number, f_num, corner)


def render(out: Path, src: Path = SRC) -> None:
    """Draw the new South Yard map over the published sheet ``src`` and write it to ``out`` as PNG.

    Raises SourceSheetMissing when ``src`` is not a file.
    """
    if not src.is_file():
        raise SourceSheetMissing(f"missing source sheet {src}")
    img = Image.open(src).convert("RGB")
    d = ImageDraw.Draw(img)
    cover_old_marks(d)
    draw_engine_house(d)
    stamp_switches(d)

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    print(f"wrote {out} ({img.size[0]}x{img.size[1]})")


def _write_docx(png: Path, dest: Path) -> None:
    """The published SM-03 docx with the new South Yard map in it."""
    sheet_kit.write_sheet_docx(DOCX_TEMPLATE, png, dest)
    print(f"wrote {dest}")


def main() -> None:
    render(OUT_CATS)
    if HOPS.is_dir() and DOCX_TEMPLATE.is_file():
        _write_docx(OUT_CATS, ROOT / "docs/ops" / DOCX_NAME)


if __name__ == "__main__":
    main()
