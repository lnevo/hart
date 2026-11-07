#!/usr/bin/env python3
"""Shenango station map (SM-05), normal and rotated.

Princess 113-115, Track McKees Rocks / Track McKeesport (mainline toward the
helix), and the K-1 / K-2 loop that serves Shenango Coke Works. Same sheet
language as the Barn / South Yard maps: 8 in x 5 in (1600x1000 at 200 dpi).

The rotated sheet is the same plan turned 180 degrees about the diagram, with
text kept upright (as the original rotated sheet was).

    python3 ops/station_maps/scripts/render_shenango_station_map.py
"""

from __future__ import annotations

import sys
import zipfile
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_barn_station_map as barn  # noqa: E402  (reuse docx writer, compass, fonts)

ROOT = Path(__file__).resolve().parents[3]
MAPS = ROOT / "ops/station_maps/maps"
OUT = MAPS / "Neville_Island_Station_Map_Shenango_0.png"
OUT_ROT = MAPS / "Neville_Island_Station_Map_Shenango_Rotated_0.png"
DOCS = ROOT / "docs/ops"

W, H = barn.W, barn.H
TRACK, INK, BADGE, BADGE_INK = barn.TRACK, barn.INK, barn.BADGE, barn.BADGE_INK
DOT_R = 19

# Plan geometry (pixels, normal orientation).
Y_W, Y_E = 405, 512          # Main West (upper), Main East (lower)
X_ARROW = 222                # west end of the mains
X_SW115 = 728                # switches 115 / 114
X_END = 1142                 # east end of the two straight tracks
X_113 = [(578, Y_W), (525, 459), (472, Y_E)]
LOOP_TOP, LOOP_BOT = 305, 611
LOOP = [(838, 305), (1293, 305), (1382, 396), (1382, 522), (1293, 611), (838, 611)]
# 180-degree turn: x -> 1600 - x, y -> 917 - y (centre of the plan).
CY = Y_W + Y_E  # y' = CY - y


def _serif(size, bold=False):
    name = "Georgia Bold.ttf" if bold else "Georgia.ttf"
    for base in (Path("/System/Library/Fonts/Supplemental"), Path("/Library/Fonts"),
                 Path("/usr/share/fonts/truetype/msttcorefonts")):
        p = base / name
        if p.is_file():
            return ImageFont.truetype(str(p), size)
    return barn._font(size, bold=bold)


def _compass(d, cx, cy, r, flip):
    k = -1 if flip else 1
    ring = (40, 58, 88)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ring, width=4)
    d.ellipse([cx - r + 12, cy - r + 12, cx + r - 12, cy + r - 12], outline=ring, width=2)
    d.line([(cx - r + 12, cy), (cx + r - 12, cy)], fill=ring, width=2)
    for sx in (-1, 1):
        for sy in (-1, 1):
            d.line([(cx + sx * (r - 12) * 0.707, cy + sy * (r - 12) * 0.707),
                    (cx + sx * (r - 1) * 0.707, cy + sy * (r - 1) * 0.707)], fill=ring, width=2)
    n = 58
    d.polygon([(cx, cy - k * n), (cx + 11, cy), (cx, cy + k * 2), (cx - 11, cy)],
              fill=barn.COMPASS_GOLD)
    d.polygon([(cx, cy - k * n), (cx - 11, cy), (cx, cy + k * 2)], fill=(168, 126, 28))
    d.polygon([(cx, cy + k * n), (cx + 11, cy), (cx, cy - k * 2), (cx - 11, cy)],
              fill=(60, 82, 112))
    d.polygon([(cx, cy + k * n), (cx - 11, cy), (cx, cy - k * 2)], fill=(150, 165, 185))
    d.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=(40, 58, 88))
    f = barn._font(28, bold=True)
    top, bot, left, right = ("S", "N", "E", "W") if flip else ("N", "S", "W", "E")
    off = r + 28
    d.text((cx, cy - off), top, font=f, fill=ring, anchor="mm")
    d.text((cx, cy + off), bot, font=f, fill=ring, anchor="mm")
    d.text((cx - off, cy), left, font=f, fill=ring, anchor="mm")
    d.text((cx + off, cy), right, font=f, fill=ring, anchor="mm")


def render(out: Path, rotated: bool) -> None:
    def T(p):
        return (W - p[0], CY - p[1]) if rotated else p

    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    f_title = barn._font(56, bold=True)
    f_track = barn._font(22, bold=True)
    f_princess = barn._font(38, bold=True)
    f_num = barn._font(20, bold=True)
    f_dest = _serif(20)
    f_ind = _serif(27, bold=True)

    def line(a, b, w=4):
        barn._line(d, T(a), T(b), w)

    def text(x, y, s, font, anchor="mm", fill=INK):
        """Place text by its ink box in plan coordinates; keep it upright."""
        bx = d.textbbox((x, y), s, font=font, anchor=anchor)
        c = T(((bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2))
        ob = d.textbbox((0, 0), s, font=font, anchor="mm")
        d.text((c[0] - (ob[0] + ob[2]) / 2, c[1] - (ob[1] + ob[3]) / 2), s,
               font=font, fill=fill, anchor="mm")

    def badge(cx, cy, s):
        box = d.textbbox((0, 0), s, font=f_num)
        w, h = box[2] - box[0] + 22, box[3] - box[1] + 16
        x, y = T((cx, cy))
        d.rounded_rectangle([x - w / 2, y - h / 2, x + w / 2, y + h / 2], radius=8, fill=BADGE)
        d.text((x, y - 1), s, font=f_num, fill=BADGE_INK, anchor="mm")

    d.text((W / 2, 37), "SHENANGO", font=f_title, fill=INK, anchor="mm")

    # Mains, Princess crossover, straight tracks, loop.
    line((X_ARROW, Y_W), (X_END, Y_W))
    line((X_ARROW, Y_E), (X_END, Y_E))
    line(X_113[0], X_113[2])
    pts = [(X_SW115, Y_W)] + LOOP + [(X_SW115, Y_E)]
    for a, b in zip(pts, pts[1:]):
        line(a, b)
    for y in (Y_W, Y_E):
        tip = T((X_ARROW, y))
        barn._arrow(d, tip, "right" if rotated else "left", size=17)
    for p in X_113 + [(X_SW115, Y_W), (X_SW115, Y_E)]:
        barn._dot(d, T(p), DOT_R)

    badge(680, 378, "115")
    badge(570, 463, "113")
    badge(680, 540, "114")

    # Labels.
    text(525, 358, "Princess", f_princess)
    text(274, 388, "Main West", f_track, "lm")
    text(274, 530, "Main East", f_track, "lm")
    text(274, 459, "to East End", f_dest, "lm")

    text(885, 388, "Track McKees Rocks", f_track, "lm")
    text(885, 530, "Track McKeesport", f_track, "lm")
    text(X_END - 6, 430, "to Scully Yard (helix)", f_dest, "rm")
    text(X_END - 6, 487, "to Demmler Yard (helix)", f_dest, "rm")

    text(1065, LOOP_TOP - 20, "Track K-1", f_track)
    text(1065, LOOP_BOT + 22, "Track K-2", f_track)

    # Coke Works sits inside the loop's east end, served from K-1 and K-2.
    # Square + two lines are one unit; turned 180 degrees the square swaps sides.
    l1, l2 = "Shenango", "Coke Works"
    tw = max(d.textlength(l1, font=f_ind), d.textlength(l2, font=f_ind))
    sqs, gap = 22, 12
    unit_w = sqs + gap + tw
    ux = (X_END + 1382) / 2 - unit_w / 2          # plan-space left edge of the unit
    uy = 459
    mx, my = T((ux + unit_w / 2, uy))
    left = mx - unit_w / 2                         # upright left edge
    if rotated:
        sq_x, tx, anchor = left + unit_w - sqs, left + tw, "rm"
    else:
        sq_x, tx, anchor = left, left + sqs + gap, "lm"
    d.rectangle([sq_x, my - sqs / 2, sq_x + sqs, my + sqs / 2], fill=(0, 0, 0))
    d.text((tx, my - 17), l1, font=f_ind, fill=INK, anchor=anchor)
    d.text((tx, my + 17), l2, font=f_ind, fill=INK, anchor=anchor)

    # Compass, turned with the plan (letters stay upright, so S is on top).
    _compass(d, 1429 if rotated else 172, 815, 74, rotated)

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    print(f"wrote {out} ({W}x{H})")


def _write_docx(png: Path, dest: Path, media_name: str) -> None:
    """Clone the SM-series landscape docx and swap the embedded map PNG."""
    tpl = barn.DOCX_TEMPLATE
    if not tpl.is_file():
        raise SystemExit(f"missing template {tpl}")
    png_bytes = png.read_bytes()
    buf = BytesIO()
    with zipfile.ZipFile(tpl) as src, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "word/media/image1.png":
                data = png_bytes
            elif item.filename == "word/document.xml":
                data = data.replace(b"station_map_west_yard.png", media_name.encode())
            elif item.filename == "docProps/core.xml":
                title = "Neville Island Station Map \u2014 Shenango"
                if "Rotated" in dest.name:
                    title += " (rotated)"
                data = barn._patch_core_title(data, title)
            out.writestr(item, data)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(buf.getvalue())
    print(f"wrote {dest}")


def main() -> None:
    render(OUT, False)
    render(OUT_ROT, True)
    if barn.HOPS.is_dir():
        _write_docx(OUT, DOCS / "Neville_Island_Station_Map_Shenango.docx",
                    "station_map_shenango.png")
        _write_docx(OUT_ROT, DOCS / "Neville_Island_Station_Map_Shenango_Rotated.docx",
                    "station_map_shenango_rotated.png")


if __name__ == "__main__":
    main()
