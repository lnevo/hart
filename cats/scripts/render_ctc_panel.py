#!/usr/bin/env python3
"""Render a single east->west Class I style CTC dispatcher panel for HART.

Collapses the layout into one linear schematic: a straight main line (west =
Brick, left) with control points drawn as numbered OS plates, passing/second
main above, and the West Yard/engine terminal, South Yard, and East End
ladders stacked below as parallel tracks. Signals sit at each control point.

This is a schematic (CTC-machine) representation, not geographic geometry.

Usage:
    python3 cats/scripts/render_ctc_panel.py <out.png>
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ------- styling -------
UNIT = 30          # px per schematic column
LANE = 70          # px per lane row
HEADER = 140
PAD = 60
BG = (12, 14, 18)
BAND = (22, 26, 32)
MAIN_C = (236, 238, 242)
SEC_C = (200, 204, 210)
YARD_C = (150, 156, 166)
DIAG_C = (120, 205, 255)
OSBOX = (30, 36, 44)
OSBORD = (120, 130, 142)
OSTXT = (255, 255, 255)
AREATXT = (150, 230, 160)
BLKTXT = (150, 158, 170)
STATION = (255, 214, 120)
SIG_G = (60, 220, 110)
SIG_R = (240, 80, 80)
ARROW = (150, 158, 170)

# lane row indices (top -> bottom)
UP2, UP, MAIN, YU, YL = 0, 1, 3, 5, 6

# ------- curated linear model (west -> east) -------
# horizontal track runs: (lane, col_start, col_end, color, width, label, label_col)
RUNS = [
    (UP, 3, 12, SEC_C, 3, "Main West", 6),
    (MAIN, 1, 74, MAIN_C, 5, None, 0),
    (UP, 44, 71, SEC_C, 3, "West Main Ext", 49),
    (UP2, 66, 73, SEC_C, 3, "McKees Rocks", 70),
    # West Yard + engine terminal
    (YU, 14, 27, YARD_C, 3, "West Yard lead", 16),
    (YL, 14, 20, YARD_C, 3, "Eng T11", 15),
    (YL, 20, 27, YARD_C, 3, "Eng T9 / T10", 23),
    # South Yard tracks
    (YU, 28, 42, YARD_C, 3, "South Yard lead", 30),
    (YL, 29, 45, YARD_C, 3, "Yard Tracks 1-5", 37),
    # East End ladder tracks
    (YU, 43, 55, YARD_C, 3, "East End sidings", 48),
    # Princess loop return
    (YL, 63, 73, YARD_C, 3, "McKeesport", 69),
]

# control points: (col, lane, os, area, diverge_dir, signals)
CPS = [
    (4, MAIN, "101", "Brick", "up"),
    (7, MAIN, "100", "Brick", "down"),
    (12, MAIN, "102", "Plane", "down"),
    (18, YU, "119", "West Yard", "down"),
    (20, MAIN, "117", "West Yard", "down"),
    (22, YU, "118", "West Yard", "down"),
    (24, YU, "116", "West Yard", "down"),
    (30, MAIN, "103", "South Yard", "down"),
    (33, YU, "104", "South Yard", "down"),
    (36, YU, "105", "South Yard", "down"),
    (39, YU, "106", "South Yard", "down"),
    (44, YU, "107", "East End", "down"),
    (47, YU, "108", "East End", "down"),
    (46, MAIN, "111", "East End", "up"),
    (50, YU, "109", "East End", "down"),
    (53, YU, "110", "East End", "down"),
    (56, MAIN, "112", "East End", "up"),
    (62, MAIN, "113", "Princess", "up"),
    (65, MAIN, "114", "Princess", "down"),
    (67, UP, "115", "Princess", "up"),
]

# station header bands: (label, col_center)
STATIONS = [
    ("BRICK", 6), ("PLANE", 12), ("WEST YARD / ENGINE TERMINAL", 21),
    ("SOUTH YARD", 35), ("EAST END", 49), ("PRINCESS", 65),
]

# main-line block name labels: (col, text)
MAIN_BLK = [
    (9, "100-102"), (16, "East Main Ext"), (27, "Main East"),
    (42, "East Lead"), (59, "OS 113"),
]


def _font(size, bold=False):
    for p in (("/usr/share/fonts/truetype/macos/Inter-Bold.ttf" if bold
               else "/usr/share/fonts/truetype/macos/Inter-Regular.ttf"),
              "/usr/share/fonts/truetype/macos/JetBrainsMono-Regular.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render(out: Path) -> None:
    max_col = 76
    max_lane = 7
    W = PAD * 2 + max_col * UNIT
    H = HEADER + PAD + max_lane * LANE

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    def px(col):
        return PAD + col * UNIT

    def py(lane):
        return HEADER + int(lane * LANE)

    f_title = _font(30, bold=True)
    f_st = _font(15, bold=True)
    f_os = _font(15, bold=True)
    f_area = _font(11)
    f_blk = _font(12)

    # header band
    d.rectangle([0, 0, W, HEADER - 34], fill=BAND)
    d.text((PAD, 18), "HART  \u2014  CTC Dispatcher Panel", font=f_title, fill=OSTXT)
    d.text((W - 330, 24), "WEST \u2190  main track  \u2192 EAST",
           font=f_st, fill=ARROW)
    d.line([(0, HEADER - 34), (W, HEADER - 34)], fill=OSBORD, width=1)
    for label, c in STATIONS:
        d.text((px(c), HEADER - 56), label, font=f_st, fill=STATION, anchor="mm")
        d.line([(px(c), HEADER - 46), (px(c), HEADER - 36)], fill=OSBORD, width=1)

    # horizontal runs
    for lane, c0, c1, color, w, label, lc in RUNS:
        d.line([(px(c0), py(lane)), (px(c1), py(lane))], fill=color, width=w)
        if label:
            d.text((px(lc), py(lane) - 12), label, font=f_blk, fill=BLKTXT)

    # main-line block labels (below the main line so they clear the OS plates)
    for c, text in MAIN_BLK:
        d.text((px(c), py(MAIN) + 12), text, font=f_blk, fill=BLKTXT, anchor="mm")

    # crossovers / diverging legs (drawn as ~45deg turnout leads that reach the
    # target lane, so a branch reads as a real route rather than a stub)
    def diagonal(col, lane, direction):
        x = px(col)
        y = py(lane)
        if direction == "up":
            tgt = UP if lane == MAIN else UP2
        else:
            tgt = YU if lane == MAIN else YL
        ty = py(tgt)
        dx = abs(ty - y)  # 45 degrees
        d.line([(x, y), (x + dx, ty)], fill=DIAG_C, width=4)

    # west end / east end arrows
    d.polygon([(px(1) - 14, py(MAIN)), (px(1), py(MAIN) - 7),
               (px(1), py(MAIN) + 7)], fill=ARROW)
    d.polygon([(px(74) + 14, py(MAIN)), (px(74), py(MAIN) - 7),
               (px(74), py(MAIN) + 7)], fill=ARROW)

    # control points
    placed = []
    for col, lane, os, area, direction in CPS:
        x, y = px(col), py(lane)
        diagonal(col, lane, direction)
        # signal bullets both directions
        d.ellipse([x - 16, y - 3, x - 10, y + 3], fill=SIG_G)
        d.ellipse([x + 10, y - 3, x + 16, y + 3], fill=SIG_R)
        # OS plate (always above the track; stack higher to avoid collisions)
        bx0, by0 = x - 17, y - 52
        while any(abs(bx0 - qx) < 40 and abs(by0 - qy) < 36 for qx, qy in placed):
            by0 -= 38
        placed.append((bx0, by0))
        # leader from plate down to the point
        d.line([(bx0 + 17, by0 + 20), (x, y - 5)], fill=OSBORD, width=1)
        d.rectangle([bx0, by0, bx0 + 34, by0 + 20], fill=OSBOX, outline=OSBORD, width=1)
        d.text((bx0 + 17, by0 + 10), os, font=f_os, fill=OSTXT, anchor="mm")
        d.text((bx0 + 17, by0 + 27), area, font=f_area, fill=AREATXT, anchor="mm")
        # point marker
        d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=STATION)

    # legend
    ly = H - 20
    d.line([(PAD, ly), (PAD + 26, ly)], fill=MAIN_C, width=5)
    d.text((PAD + 32, ly - 7), "main", font=f_blk, fill=BLKTXT)
    d.line([(PAD + 90, ly), (PAD + 116, ly)], fill=YARD_C, width=3)
    d.text((PAD + 122, ly - 7), "yard/siding", font=f_blk, fill=BLKTXT)
    d.line([(PAD + 210, ly), (PAD + 236, ly)], fill=DIAG_C, width=4)
    d.text((PAD + 242, ly - 7), "turnout route", font=f_blk, fill=BLKTXT)
    d.ellipse([PAD + 350, ly - 3, PAD + 356, ly + 3], fill=SIG_G)
    d.ellipse([PAD + 360, ly - 3, PAD + 366, ly + 3], fill=SIG_R)
    d.text((PAD + 372, ly - 7), "signals (W/E)", font=f_blk, fill=BLKTXT)
    d.rectangle([PAD + 470, ly - 8, PAD + 500, ly + 6], fill=OSBOX, outline=OSBORD)
    d.text((PAD + 506, ly - 7), "OS control point", font=f_blk, fill=BLKTXT)

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"wrote {out}  ({W}x{H})  control_points={len(CPS)}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: render_ctc_panel.py <out.png>", file=sys.stderr)
        raise SystemExit(2)
    render(Path(sys.argv[1]))
