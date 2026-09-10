#!/usr/bin/env python3
"""Barn station map — Switch 7 / 9 / 11 / 13.

Layout Editor plant (TO117 xover, TO10, TO11, TO1) in the same sheet language
as West Yard / South Yard / East End. One slope for every non-horizontal:
Switch 7 is a three-dot crossover like East End 111; Switch 13's diverge is
a straight line to the EH-1 horizontal.

Print size matches the other local sheets: 8 in × 5 in (1600×1000 at 200 dpi).

    python3 cats/scripts/render_barn_station_map.py
"""

from __future__ import annotations

import shutil
import zipfile
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT_CATS = ROOT / "cats/docs/station_maps/Neville_Island_Station_Map_Barn_0.png"
OUT_PORTAL = ROOT / "consolidation/ops-portal/assets/maps/station_map_barn.png"
HOPS = ROOT / "consolidation/external/hart-ops"
DOCX_NAME = "Neville_Island_Station_Map_Barn.docx"
DOCX_TEMPLATE = HOPS / "docs/Neville_Island_Station_Map_West_Yard.docx"

# 8 in × 5 in landscape, same as SM-02…SM-05.
DPI = 200
W = 8 * DPI
H = 5 * DPI
IN = float(DPI)

TRACK = (20, 20, 20)
INK = (16, 20, 24)
BADGE = (15, 71, 97)  # same teal as SM-02…SM-05
BADGE_INK = (255, 255, 255)
DOT_R = 16
# Clear air between the frog and the pill (103/111 sit off the circle, not on it).
BADGE_GAP = 18
COMPASS_RING = (40, 70, 110)
COMPASS_GOLD = (201, 154, 40)
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


def _along(origin, dy):
    """Move `dy` screen-pixels (down positive) along the shared slope."""
    return (origin[0] + (RUN / RISE) * dy, origin[1] + dy)


def _mid(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


SW7_BOT = _along(SW7_TOP, Y_MAIN - Y_BARN)
SW7_MID = _mid(SW7_TOP, SW7_BOT)
SW11 = _along(SW13, Y_EH3 - Y_BARN)
EH1_JOIN = _along(SW13, Y_EH1 - Y_BARN)
EH2_JOIN = _along(SW9, Y_EH2 - Y_EH3)


def _font(size: int, bold: bool = False, black: bool = False):
    names = []
    if black:
        names.append("Arial Black.ttf")
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
    r = width / 2
    for x, y in (a, b):
        d.ellipse([x - r, y - r, x + r, y + r], fill=TRACK)


def _arrow(d: ImageDraw.ImageDraw, tip, direction: str, size=14):
    x, y = tip
    if direction == "left":
        pts = [(x, y), (x + size, y - size * 0.55), (x + size, y + size * 0.55)]
    else:
        pts = [(x, y), (x - size, y - size * 0.55), (x - size, y + size * 0.55)]
    d.polygon(pts, fill=TRACK)


def _dot(d, pt, r=DOT_R):
    x, y = pt
    d.ellipse([x - r, y - r, x + r, y + r], fill=TRACK)


def _badge_near(d, pt, text, font, corner: str = "ne"):
    """Teal switch pill off the frog, same language as 103 / 110 / 111."""
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
    """Clone an SM-series landscape docx and swap the embedded map PNG."""
    if not DOCX_TEMPLATE.is_file():
        raise SystemExit(f"missing template {DOCX_TEMPLATE}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    png_bytes = png.read_bytes()
    buf = BytesIO()
    with zipfile.ZipFile(DOCX_TEMPLATE, "r") as src, zipfile.ZipFile(
        buf, "w", compression=zipfile.ZIP_DEFLATED
    ) as out:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "word/media/image1.png":
                data = png_bytes
            elif item.filename == "word/document.xml":
                data = data.replace(
                    b"station_map_west_yard.png",
                    b"station_map_barn.png",
                )
            elif item.filename == "docProps/core.xml":
                data = _patch_core_title(data, "Neville Island Station Map — Barn")
            out.writestr(item, data)
    dest.write_bytes(buf.getvalue())
    print(f"wrote {dest}")


def _patch_core_title(xml_bytes: bytes, title: str) -> bytes:
    ns = {
        "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
        "dc": "http://purl.org/dc/elements/1.1/",
    }
    root = ET.fromstring(xml_bytes)
    el = root.find("dc:title", ns)
    if el is not None:
        el.text = title
    ET.register_namespace("cp", ns["cp"])
    ET.register_namespace("dc", ns["dc"])
    ET.register_namespace("dcterms", "http://purl.org/dc/terms/")
    ET.register_namespace("dcmitype", "http://purl.org/dc/dcmitype/")
    ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def main() -> None:
    render(OUT_CATS)
    OUT_PORTAL.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUT_CATS, OUT_PORTAL)
    print(f"copied {OUT_PORTAL}")
    if HOPS.is_dir():
        _write_docx(OUT_CATS, HOPS / "docs" / DOCX_NAME)
        _write_docx(OUT_CATS, HOPS / "docs/published" / DOCX_NAME)


if __name__ == "__main__":
    main()
