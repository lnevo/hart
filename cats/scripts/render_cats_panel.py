#!/usr/bin/env python3
"""Render a CATS panel TRACKPLAN to a PNG for remote review.

This is a schematic render of the panel *data* (SECTION grid: track kinds,
switch plants, block names, labels) — not a live CATS GUI capture. It lets a
Cloud Agent post a reviewable board image without a full JMRI/CATS install.

Usage:
    python3 cats/scripts/render_cats_panel.py cats/panels/HART_le.xml out.png
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CELL = 60
PAD_X = 60
PAD_Y = 90
TRACK_W = 5

# track kind -> (endpoint A, endpoint B) using cell edge midpoints
ENDS = {
    "HORIZONTAL": ("LEFT", "RIGHT"),
    "VERTICAL": ("TOP", "BOTTOM"),
    "UPPERSLASH": ("LEFT", "TOP"),
    "LOWERSLASH": ("RIGHT", "BOTTOM"),
    "UPPERBACKSLASH": ("RIGHT", "TOP"),
    "LOWERBACKSLASH": ("LEFT", "BOTTOM"),
}

BG = (22, 24, 28)
TRACK = (210, 214, 220)
PLANT = (90, 200, 255)
POINTS = (255, 196, 60)
BLKTXT = (150, 230, 160)
LABELTXT = (255, 255, 255)
GRIDLINE = (44, 48, 54)


def _font(size: int, bold: bool = False):
    for p in (
        "/usr/share/fonts/truetype/macos/Inter-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/macos/Inter-Regular.ttf",
        "/usr/share/fonts/truetype/macos/JetBrainsMono-Regular.ttf",
    ):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def edge_pt(x0: int, y0: int, edge: str) -> tuple[int, int]:
    h = CELL // 2
    return {
        "LEFT": (x0, y0 + h),
        "RIGHT": (x0 + CELL, y0 + h),
        "TOP": (x0 + h, y0),
        "BOTTOM": (x0 + h, y0 + CELL),
    }[edge]


def render(src: Path, out: Path) -> None:
    root = ET.parse(src).getroot()
    tp = root.find("TRACKPLAN")
    sections = tp.findall("SECTION")

    xs, ys = [], []
    for s in sections:
        xs.append(int(s.get("X")))
        ys.append(int(s.get("Y")))
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    cols = maxx - minx + 1
    rows = maxy - miny + 1

    W = PAD_X * 2 + cols * CELL
    H = PAD_Y + PAD_Y // 2 + rows * CELL
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    def cell_origin(x: int, y: int) -> tuple[int, int]:
        return PAD_X + (x - minx) * CELL, PAD_Y + (y - miny) * CELL

    # faint grid
    for c in range(cols + 1):
        gx = PAD_X + c * CELL
        d.line([(gx, PAD_Y), (gx, PAD_Y + rows * CELL)], fill=GRIDLINE, width=1)
    for r in range(rows + 1):
        gy = PAD_Y + r * CELL
        d.line([(PAD_X, gy), (PAD_X + cols * CELL, gy)], fill=GRIDLINE, width=1)

    f_title = _font(30, bold=True)
    f_blk = _font(12)
    f_lab = _font(15, bold=True)

    d.text((PAD_X, 26), f"{src.name}   grid {cols}\u00d7{rows}  (min col={minx}, "
           f"row={miny})", font=f_title, fill=LABELTXT)

    seen_names: set[str] = set()
    for s in sections:
        x, y = int(s.get("X")), int(s.get("Y"))
        x0, y0 = cell_origin(x, y)
        tg = s.find("TRACKGROUP")
        if tg is None:
            nm = s.find("SEC_NAME")
            if nm is not None and nm.get("NAME"):
                d.text((x0 + 4, y0 + CELL // 2 - 8), nm.get("NAME"),
                       font=f_lab, fill=LABELTXT)
            continue
        tracks = [(t.text or "").strip() for t in tg.findall("TRACK")]
        is_plant = any(e.find("SWITCHPOINTS") is not None for e in s.findall("SEC_EDGE"))
        col = PLANT if is_plant else TRACK
        for t in tracks:
            if t not in ENDS:
                continue
            a, b = ENDS[t]
            d.line([edge_pt(x0, y0, a), edge_pt(x0, y0, b)], fill=col, width=TRACK_W)
        # points marker
        for e in s.findall("SEC_EDGE"):
            if e.find("SWITCHPOINTS") is not None:
                px, py = edge_pt(x0, y0, e.get("EDGE"))
                d.ellipse([px - 5, py - 5, px + 5, py + 5], fill=POINTS)
        # block name (first occurrence, drawn once)
        for e in s.findall("SEC_EDGE"):
            b = e.find("BLOCK")
            if b is not None and b.get("NAME") and b.get("NAME") not in seen_names:
                seen_names.add(b.get("NAME"))
                d.text((x0 + 2, y0 + 2), b.get("NAME"), font=f_blk, fill=BLKTXT)

    # legend
    ly = H - PAD_Y // 2 + 6
    d.line([(PAD_X, ly + 8), (PAD_X + 30, ly + 8)], fill=TRACK, width=TRACK_W)
    d.text((PAD_X + 38, ly), "track", font=f_blk, fill=LABELTXT)
    d.line([(PAD_X + 110, ly + 8), (PAD_X + 140, ly + 8)], fill=PLANT, width=TRACK_W)
    d.text((PAD_X + 148, ly), "turnout plant", font=f_blk, fill=LABELTXT)
    d.ellipse([PAD_X + 270, ly + 3, PAD_X + 280, ly + 13], fill=POINTS)
    d.text((PAD_X + 288, ly), "switch points", font=f_blk, fill=LABELTXT)
    d.text((PAD_X + 410, ly), "block / OS names in green", font=f_blk, fill=BLKTXT)

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"wrote {out}  ({W}x{H})  sections={len(sections)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: render_cats_panel.py <panel.xml> <out.png>", file=sys.stderr)
        raise SystemExit(2)
    render(Path(sys.argv[1]), Path(sys.argv[2]))
