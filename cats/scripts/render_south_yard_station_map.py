#!/usr/bin/env python3
"""South Yard station map — Switch 7 / 15 / 17 / 19 / 21.

Starts from the published SM-03 sheet and restamps the frogs with the
live switch userNames (not Digicon CP / DCC 103–106). Adds the Switch 7
three-dot crossover at Barn, same language as East End 111.

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

TRACK = (20, 20, 20)
BADGE = (15, 71, 97)
BADGE_INK = (255, 255, 255)
DOT_R = 16
BADGE_GAP = 18

# Ladder frogs on the published sheet (was CP 103–106 → Switch 15/17/19/21).
SW15 = (850, 222)
SW17 = (883, 368)
SW19 = (917, 514)
SW21 = (953, 661)

# Switch 7 LH_XOVER: West Lead down-left onto Main East at Barn.
SW7_TOP = (411, 225)
SW7_BOT = (378, 370)
SW7_MID = ((SW7_TOP[0] + SW7_BOT[0]) / 2, (SW7_TOP[1] + SW7_BOT[1]) / 2)

OLD_BADGES = (
    (862, 184, 49, 27),
    (897, 330, 49, 27),
    (932, 475, 49, 27),
    (967, 621, 49, 27),
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
    else:
        raise ValueError(corner)
    d.rounded_rectangle([x, y, x + w, y + h], radius=8, fill=BADGE)
    d.text((x + w / 2, y + h / 2 - 1), text, font=font, fill=BADGE_INK, anchor="mm")


def _cover(d, box, pad=6):
    x, y, w, h = box
    d.rectangle([x - pad, y - pad, x + w + pad, y + h + pad], fill=(255, 255, 255))


def render(out: Path) -> None:
    if not SRC.is_file():
        raise SystemExit(f"missing source sheet {SRC}")
    img = Image.open(SRC).convert("RGB")
    d = ImageDraw.Draw(img)
    f_num = _font(20, bold=True)

    for box in OLD_BADGES:
        _cover(d, box, pad=8)

    for pt in (SW7_TOP, SW7_MID, SW7_BOT, SW15, SW17, SW19, SW21):
        _dot(d, pt)

    _badge_near(d, SW7_MID, "7", f_num, "w")
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
