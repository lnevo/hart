#!/usr/bin/env python3
"""South Yard station map — Switch 7 / 13 / 15 / 17 / 19 / 21.

Starts from the published SM-03 sheet and restamps the frogs with the
live switch userNames (not Digicon CP / DCC 103–106). Switch 7 is the
three-dot Barn xover. The compact ET stub is replaced with a shrunken
Barn engine-house plant (EH-1 / EH-2 / EH-3). Switch 13 sits on Scale
at that throat; the Barn block is the rail between 7 and 13.

    python3 ops/station_maps/scripts/render_south_yard_station_map.py
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

# Ladder frogs on the published sheet (was CP 103–106 → Switch 15/17/19/21).
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
# "Track S-1" .. "Track S-5" baked into the published sheet (right edge). The
# tracks are now S-R, S-1 .. S-4 (S-1 became S-R, the rest renumbered).
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


_font = sheet_kit.arial
_line = partial(sheet_kit.capped_line, width=4, fill=TRACK)
_dot = partial(sheet_kit.dot, r=DOT_R, fill=TRACK)
_badge_near = partial(sheet_kit.badge_near, dot_r=DOT_R, gap=BADGE_GAP, fill=BADGE, ink=BADGE_INK)


def _cover(d, box, pad=6):
    x, y, w, h = box
    d.rectangle([x - pad, y - pad, x + w + pad, y + h + pad], fill=WHITE)


def render(out: Path) -> None:
    if not SRC.is_file():
        raise SystemExit(f"missing source sheet {SRC}")
    img = Image.open(SRC).convert("RGB")
    d = ImageDraw.Draw(img)
    f_num = _font(20, bold=True)

    for box in OLD_BADGES:
        _cover(d, box, pad=8)
    for box in OLD_EH_STUB:
        _cover(d, box, pad=2)
    for box in OLD_LABELS:
        _cover(d, box, pad=3)
    f_name = _font(22, bold=True)
    for y, _name in TRACK_NAMES:
        d.rectangle([1452, y - 16, 1598, y + 16], fill=WHITE)
    for y, name in TRACK_NAMES:
        d.text((1456, y), name, font=f_name, fill=INK, anchor="lm")

    _line(d, (X_EH, Y_EH1), EH1_JOIN)
    _line(d, (X_EH, Y_EH2), EH2_JOIN)
    _line(d, (X_EH, Y_EH3), SW11)
    _line(d, SW13, EH1_JOIN)
    _line(d, EH2_JOIN, SW9)

    f_eh = _font(13, bold=True)
    f_track = _font(18, bold=True)
    gap = 6
    d.text((X_EH + 72, Y_EH1 - gap), "EH-1", font=f_eh, fill=INK, anchor="ms")
    d.text((X_EH + 72, Y_EH2 - gap), "EH-2", font=f_eh, fill=INK, anchor="ms")
    d.text((X_EH + 72, Y_EH3 - gap), "EH-3", font=f_eh, fill=INK, anchor="ms")
    d.text((254, Y_WL - 12), "Scale", font=f_track, fill=INK, anchor="ms")
    d.text(((SW7_TOP[0] + SW13[0]) / 2, Y_WL - 12), "Barn", font=f_track, fill=INK, anchor="ms")

    for pt in (SW7_TOP, SW7_MID, SW7_BOT, SW13, SW15, SW17, SW19, SW21):
        _dot(d, pt)

    _badge_near(d, SW7_MID, "7", f_num, "w")
    _badge_near(d, SW13, "13", f_num, "e")
    _badge_near(d, SW15, "15", f_num, "ne")
    _badge_near(d, SW17, "17", f_num, "ne")
    _badge_near(d, SW19, "19", f_num, "ne")
    _badge_near(d, SW21, "21", f_num, "ne")

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    print(f"wrote {out} ({img.size[0]}x{img.size[1]})")


def _write_docx(png: Path, dest: Path) -> None:
    """The published SM-03 docx with the new South Yard map in it."""
    sheet_kit.write_sheet_docx(DOCX_TEMPLATE, png, dest)


def main() -> None:
    render(OUT_CATS)
    if HOPS.is_dir() and DOCX_TEMPLATE.is_file():
        _write_docx(OUT_CATS, ROOT / "docs/ops" / DOCX_NAME)


if __name__ == "__main__":
    main()
