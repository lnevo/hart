#!/usr/bin/env python3
"""South Yard station map — Switch 7 / 13 / 15 / 17 / 19 / 21.

Starts from the published SM-03 sheet and restamps the frogs with the
live switch userNames (not Digicon CP / DCC 103–106). Switch 7 is the
three-dot Barn xover. The compact ET stub is replaced with a shrunken
Barn engine-house plant (EH-1 / EH-2 / EH-3); Switch 13 sits on West Lead
at that throat.

    python3 cats/scripts/render_south_yard_station_map.py
"""

from __future__ import annotations

import shutil
import zipfile
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "cats/docs/station_maps/src/south_yard_sheet.png"
OUT_CATS = ROOT / "cats/docs/station_maps/Neville_Island_Station_Map_South_Yard_0.png"
OUT_PORTAL = ROOT / "consolidation/ops-portal/assets/maps/station_map_south_yard.png"
HOPS = ROOT / "consolidation/external/hart-ops"
DOCX_NAME = "Neville_Island_Station_Map_South_Yard.docx"
DOCX_TEMPLATE = HOPS / "docs/Neville_Island_Station_Map_South_Yard.docx"

WHITE = (255, 255, 255)
TRACK = (20, 20, 20)
INK = (16, 20, 24)
BADGE = (15, 71, 97)
BADGE_INK = (255, 255, 255)
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

# Shrunken Barn EH plant above West Lead (replaces the compact ET stub).
# Switch 13 is the West Lead frog at the published throat (~x=630).
Y_WL = 225.0
Y_EH1 = 108.0
Y_EH2 = 140.0
Y_EH3 = 172.0
X_EH = 340.0
SW13 = (632.0, Y_WL)


def _along(origin, dy):
    """Move `dy` screen-pixels (down positive) along the shared slope."""
    return (origin[0] + (RUN / RISE) * dy, origin[1] + dy)


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
# Compact ET-1/2/3 stub + its join onto West Lead (stop above the rail).
OLD_EH_STUB = (
    (318, 120, 340, 92),
    (618, 200, 24, 16),
)


def _font(size: int, bold: bool = False):
    names = ["Arial Bold.ttf"] if bold else ["Arial.ttf"]
    if bold:
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


def _line(d: ImageDraw.ImageDraw, a, b, width=5):
    d.line([a, b], fill=TRACK, width=width)
    r = width / 2
    for x, y in (a, b):
        d.ellipse([x - r, y - r, x + r, y + r], fill=TRACK)


def _dot(d, pt, r=DOT_R):
    x, y = pt
    d.ellipse([x - r, y - r, x + r, y + r], fill=TRACK)


def _badge_near(d, pt, text, font, corner: str = "ne"):
    box = d.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    w = tw + 22
    h = th + 16
    cx, cy = pt
    gap = BADGE_GAP
    if corner == "ne":
        x = cx + DOT_R + gap
        y = cy - DOT_R - h - 2
    elif corner == "nw":
        x = cx - DOT_R - w - gap
        y = cy - DOT_R - h - 2
    elif corner == "w":
        x = cx - DOT_R - w - gap
        y = cy - h / 2
    elif corner == "e":
        x = cx + DOT_R + gap
        y = cy - h / 2
    else:
        raise ValueError(corner)
    d.rounded_rectangle([x, y, x + w, y + h], radius=8, fill=BADGE)
    d.text((x + w / 2, y + h / 2 - 1), text, font=font, fill=BADGE_INK, anchor="mm")


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

    # Restore West Lead through the wiped pocket.
    _line(d, (200, Y_WL), (SW15[0], Y_WL), 6)

    _line(d, (X_EH, Y_EH1), EH1_JOIN)
    _line(d, (X_EH, Y_EH2), EH2_JOIN)
    _line(d, (X_EH, Y_EH3), SW11)
    _line(d, SW13, EH1_JOIN)
    _line(d, EH2_JOIN, SW9)

    f_eh = _font(13, bold=True)
    gap = 6
    d.text((X_EH + 72, Y_EH1 - gap), "EH-1", font=f_eh, fill=INK, anchor="ms")
    d.text((X_EH + 72, Y_EH2 - gap), "EH-2", font=f_eh, fill=INK, anchor="ms")
    d.text((X_EH + 72, Y_EH3 - gap), "EH-3", font=f_eh, fill=INK, anchor="ms")

    for pt in (SW7_TOP, SW7_MID, SW7_BOT, SW9, SW11, SW13, SW15, SW17, SW19, SW21):
        _dot(d, pt)

    _badge_near(d, SW7_MID, "7", f_num, "w")
    _badge_near(d, SW9, "9", f_num, "e")
    _badge_near(d, SW11, "11", f_num, "ne")
    _badge_near(d, SW13, "13", f_num, "e")
    _badge_near(d, SW15, "15", f_num, "ne")
    _badge_near(d, SW17, "17", f_num, "ne")
    _badge_near(d, SW19, "19", f_num, "ne")
    _badge_near(d, SW21, "21", f_num, "ne")

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    print(f"wrote {out} ({img.size[0]}x{img.size[1]})")


def _write_docx(png: Path, dest: Path) -> None:
    if not DOCX_TEMPLATE.is_file():
        raise SystemExit(f"missing template {DOCX_TEMPLATE}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    png_bytes = png.read_bytes()
    buf = BytesIO()
    with zipfile.ZipFile(DOCX_TEMPLATE, "r") as src, zipfile.ZipFile(
        buf, "w", compression=zipfile.ZIP_DEFLATED
    ) as outz:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "word/media/image1.png":
                data = png_bytes
            elif item.filename == "word/document.xml":
                data = data.replace(
                    b"station_map_south_yard.png",
                    b"station_map_south_yard.png",
                )
            outz.writestr(item, data)
    dest.write_bytes(buf.getvalue())
    print(f"wrote {dest}")


def main() -> None:
    render(OUT_CATS)
    OUT_PORTAL.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUT_CATS, OUT_PORTAL)
    print(f"copied {OUT_PORTAL}")
    if HOPS.is_dir() and DOCX_TEMPLATE.is_file():
        _write_docx(OUT_CATS, HOPS / "docs" / DOCX_NAME)
        _write_docx(OUT_CATS, HOPS / "docs/published" / DOCX_NAME)


if __name__ == "__main__":
    main()
