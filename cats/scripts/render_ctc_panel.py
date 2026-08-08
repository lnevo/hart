#!/usr/bin/env python3
"""Render a single east->west Class I style CTC dispatcher panel for HART.

Collapses the layout into one linear schematic: a straight main line (west =
Brick, left) with control points drawn as numbered OS plates. Yards are drawn
as proper ladders: the entry turnout's diverging lead lands exactly on the
first ladder rung, and each subsequent rung peels one track off the lead, so
103->104->105->106 connect in sequence (not into the gap between rungs).

This is a schematic (CTC-machine) representation, not geographic geometry.

Usage:
    python3 cats/scripts/render_ctc_panel.py <out.png>
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ------- styling -------
UNIT = 30
LANE = 70
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

# lane rows (top -> bottom)
UP2, UP, MAIN, YU, YL = 0, 1, 3, 5, 6

# horizontal track runs: (lane, c0, c1, color, width, label, label_col)
RUNS = [
    (UP, 3, 13, SEC_C, 3, "Main West", 6),
    (MAIN, 1, 80, MAIN_C, 5, None, 0),
    (UP, 54, 79, SEC_C, 3, "West Main Ext", 60),
    (UP2, 74, 82, SEC_C, 3, "McKees Rocks", 77),
    (YL, 70, 82, YARD_C, 3, "McKeesport", 75),
]

# standalone control points on main/up: (col, lane, os, area, dir, stub_label)
STANDALONE = [
    (4, MAIN, "101", "Brick", "up", "Main West"),
    (7, MAIN, "100", "Brick", "down", "West Yard interchange"),
    (11, MAIN, "102", "Plane", "down", "Plane spur"),
    (56, MAIN, "111", "East End", "up", None),      # crossover to passing main
    (66, MAIN, "112", "East End", "up", None),
    (70, MAIN, "113", "Princess", "up", None),       # crossover to passing main
    (72, MAIN, "114", "Princess", "down", "East Lead"),
    (74, UP, "115", "Princess", "up", "McKees Rocks"),
]

# East End ladder rungs sit on the yard lead (kept as the reviewer liked it):
# (col, os, area, track_label)
EAST_END = [
    (50, "107", "East End", "EE 1"),
    (54, "108", "East End", "EE 2"),
    (58, "109", "East End", "EE 3"),
    (62, "110", "East End", "EE 4"),
]

# ladders: entry turnout on MAIN, rungs on the lead lane, tracks below.
# (entry_col, entry_os, area, [(os, track_label), ...], rung_spacing)
LADDERS = [
    (15, "117", "West Yard",
     [("119", "Eng T11"), ("118", "Eng T10"), ("116", "Eng T9")], 4),
    (34, "103", "South Yard",
     [("104", "Yard Trk 1"), ("105", "Yard Trk 2"), ("106", "Yard Trk 3")], 4),
]

STATIONS = [
    ("BRICK", 6), ("PLANE", 11), ("WEST YARD / ENGINE TERMINAL", 22),
    ("SOUTH YARD", 42), ("EAST END", 58), ("PRINCESS", 73),
]

MAIN_BLK = [(9, "100-102"), (26, "Main East"), (46, "East Lead")]


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
    max_col = 86
    max_lane = 7
    W = PAD * 2 + max_col * UNIT
    H = HEADER + PAD + max_lane * LANE
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    def px(col):
        return int(PAD + col * UNIT)

    def py(lane):
        return int(HEADER + lane * LANE)

    # lanes-per-column for a 45deg diagonal
    lane_cols = LANE / UNIT

    f_title = _font(30, bold=True)
    f_st = _font(15, bold=True)
    f_os = _font(15, bold=True)
    f_area = _font(11)
    f_blk = _font(12)

    placed = []

    def diag(col, lane, tgt_lane):
        x, y, ty = px(col), py(lane), py(tgt_lane)
        dx = abs(ty - y)  # 45deg
        sign = 1
        d.line([(x, y), (x + sign * dx, ty)], fill=DIAG_C, width=4)
        return col + sign * (tgt_lane - lane) * lane_cols  # landing col (signed)

    def signals(x, y):
        d.ellipse([x - 16, y - 3, x - 10, y + 3], fill=SIG_G)
        d.ellipse([x + 10, y - 3, x + 16, y + 3], fill=SIG_R)

    def os_plate(col, lane, os, area):
        x, y = px(col), py(lane)
        bx0, by0 = x - 17, y - 52
        while any(abs(bx0 - qx) < 40 and abs(by0 - qy) < 36 for qx, qy in placed):
            by0 -= 38
        placed.append((bx0, by0))
        d.line([(bx0 + 17, by0 + 20), (x, y - 5)], fill=OSBORD, width=1)
        d.rectangle([bx0, by0, bx0 + 34, by0 + 20], fill=OSBOX, outline=OSBORD, width=1)
        d.text((bx0 + 17, by0 + 10), os, font=f_os, fill=OSTXT, anchor="mm")
        d.text((bx0 + 17, by0 + 30), area, font=f_area, fill=AREATXT, anchor="mm")
        d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=STATION)
        signals(x, y)

    # header
    d.rectangle([0, 0, W, HEADER - 34], fill=BAND)
    d.text((PAD, 18), "HART  \u2014  CTC Dispatcher Panel", font=f_title, fill=OSTXT)
    d.text((W - 330, 24), "WEST \u2190  main track  \u2192 EAST", font=f_st, fill=ARROW)
    d.line([(0, HEADER - 34), (W, HEADER - 34)], fill=OSBORD, width=1)
    for label, c in STATIONS:
        d.text((px(c), HEADER - 56), label, font=f_st, fill=STATION, anchor="mm")
        d.line([(px(c), HEADER - 46), (px(c), HEADER - 36)], fill=OSBORD, width=1)

    # horizontal runs
    for lane, c0, c1, color, w, label, lc in RUNS:
        d.line([(px(c0), py(lane)), (px(c1), py(lane))], fill=color, width=w)
        if label:
            d.text((px(lc), py(lane) - 12), label, font=f_blk, fill=BLKTXT)
    for c, text in MAIN_BLK:
        d.text((px(c), py(MAIN) + 12), text, font=f_blk, fill=BLKTXT, anchor="mm")

    # end arrows
    d.polygon([(px(1) - 14, py(MAIN)), (px(1), py(MAIN) - 7), (px(1), py(MAIN) + 7)],
              fill=ARROW)
    d.polygon([(px(80) + 14, py(MAIN)), (px(80), py(MAIN) - 7), (px(80), py(MAIN) + 7)],
              fill=ARROW)

    # ladders (entry on main -> lead lands on first rung -> rungs peel tracks)
    for entry_col, entry_os, area, rungs, spacing in LADDERS:
        land = diag(entry_col, MAIN, YU)          # entry lead lands on YU
        os_plate(entry_col, MAIN, entry_os, area)
        rung_cols = [land + i * spacing for i in range(len(rungs))]
        # lead along YU through all rungs
        d.line([(px(land), py(YU)), (px(rung_cols[-1] + 1.5), py(YU))],
               fill=YARD_C, width=3)
        for (os, tl), rc in zip(rungs, rung_cols):
            tland = diag(rc, YU, YL)              # rung peels a track down to YL
            d.line([(px(tland), py(YL)), (px(tland + 3), py(YL))],
                   fill=YARD_C, width=3)
            d.text((px(tland + 0.2), py(YL) + 10), tl, font=f_blk, fill=BLKTXT)
            os_plate(rc, YU, os, area)

    # East End lead + rungs (yard lead below the main)
    ee_cols = [c for c, *_ in EAST_END]
    d.line([(px(ee_cols[0] - 1), py(YU)), (px(ee_cols[-1] + 1), py(YU))],
           fill=YARD_C, width=3)
    for col, os, area, tl in EAST_END:
        tland = diag(col, YU, YL)
        d.line([(px(tland), py(YL)), (px(tland + 3), py(YL))], fill=YARD_C, width=3)
        d.text((px(tland + 0.2), py(YL) + 10), tl, font=f_blk, fill=BLKTXT)
        os_plate(col, YU, os, area)

    # standalone control points
    for col, lane, os, area, direction, stub in STANDALONE:
        if direction == "up":
            tgt = UP if lane == MAIN else UP2
        else:
            tgt = YU if lane == MAIN else YL
        land = diag(col, lane, tgt)
        if stub and tgt in (YU, YL, UP2) and not (lane == MAIN and direction == "up"):
            d.line([(px(land), py(tgt)), (px(land + 3), py(tgt))], fill=YARD_C, width=3)
            d.text((px(land + 0.2), py(tgt) + 10), stub, font=f_blk, fill=BLKTXT)
        elif stub:
            d.text((px(land), py(tgt) - 12), stub, font=f_blk, fill=BLKTXT)
        os_plate(col, lane, os, area)

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
    n = len(STANDALONE) + len(EAST_END) + sum(1 + len(r[3]) for r in LADDERS)
    print(f"wrote {out}  ({W}x{H})  control_points={n}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: render_ctc_panel.py <out.png>", file=sys.stderr)
        raise SystemExit(2)
    render(Path(sys.argv[1]))
