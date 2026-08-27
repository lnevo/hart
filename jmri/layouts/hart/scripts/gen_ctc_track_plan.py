#!/usr/bin/env python3
"""Generate the USS CTC track diagram from CATS Master 4 (v73).

20 packed columns. Brick column 1 is N/R, 101 is L/N, 102 is L/N, 117 is
LNR. 120L is named L but faces east (into the McKees Rocks wrap) under 120R.

    python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py
    python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py --preview cats/screenshots/master4/uss_ctc_v73_preview.png
    python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py --tables jmri/layouts/hart/output/tables.xml
"""
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CATS_XML = ROOT / "cats/panels/HART_Master4_wired.xml"
CATS_DESIGNER = ROOT / "cats/panels/HART_Master4.xml"
if not CATS_XML.is_file():
    CATS_XML = CATS_DESIGNER
GUI_XML = ROOT / "jmri/layouts/hart/ctc/GUIObjects.xml"
OUTPUT_TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"
NEW_TABLES = ROOT / "tables/new_tables.xml"
SOURCE_TABLES = ROOT / "tables/tables.xml"
THIN_DIR = ROOT / "jmri/layouts/hart/ctc/icons"
JMRI_RES = Path("/Applications/JMRI/resources")

U = "program:resources/icons/USS/"
THIN = "preference:ctc/icons/"

# Square cells. 20 packed tiles: 12 + 20*65 + 12 = 1324.
# USS 7" plate: gold 0–31, silver 32–36, dark diagram 38–274, silver 275–280.
# Stack (station + tracks + OS numbers) is padded equally in that dark band.
OX, OY = 8, 73
CELL_W, CELL_H = 21, 21
OS_Y = 228
STATION_Y = 51
PANEL_W, PANEL_H = 1400, 800

N_SLOTS = 20
BLANK_SLOTS: set[int] = set()
# 119, 118, 116, 103, 104, 105, 106, 107, 108, 109 — switch-only (no signal lever).
SWITCH_ONLY_SLOTS = {4, 5, 6, 7, 8, 9, 10, 12, 13, 14}

CREAM = dict(red=220, green=220, blue=180)
WHITE = dict(red=255, green=255, blue=255)

# CATS frog cell → (JMRI turnout, invert vs JMRI). Rails come from CATS
# track pieces; the turnouticon is only a points dot.
PLANTS = {
    (4, 8): ("Switch 100", True),
    (5, 9): ("Switch 101", False),
    (9, 8): ("Switch 102", False),
    (15, 7): ("Switch 117", False),
    (24, 8): ("Switch 119", False),
    (26, 8): ("Switch 118", False),
    (27, 7): ("Switch 116", False),
    (30, 7): ("Switch 103", False),
    (31, 8): ("Switch 104", False),
    (32, 9): ("Switch 105", False),
    (33, 10): ("Switch 106", False),
    (39, 10): ("Switch 107", False),
    (40, 9): ("Switch 108", False),
    (41, 8): ("Switch 109", False),
    (40, 6): ("Switch 111", False),
    (42, 7): ("Switch 110", False),
    (44, 7): ("Switch 112", False),
    (52, 6): ("Switch 113", False),
    (55, 6): ("Switch 115", True),
    (55, 7): ("Switch 114", True),
}
# Stock USS tiles (transparent copies in ctc/icons/). Offsets center the
# native GIF on the CATS cell. Slashes stay half-cell custom tiles
# at stock bar weight so frogs still meet.
STOCK_H = ("stock-h.gif", -1, 6)       # line025 24×8 on 21×21
STOCK_V = ("stock-v.gif", 6, -1)       # rotated line025 8×24
STOCK_END = ("stock-end.gif", -2, 2)   # eotwht 26×16
CELL_GIF = {
    "UPPERSLASH": "cell-us.gif",
    "LOWERSLASH": "cell-ls.gif",
    "UPPERBACKSLASH": "cell-ub.gif",
    "LOWERBACKSLASH": "cell-lb.gif",
}
# Occupancy jewels centered on these named segments (CATS cell).
CENTER_OCC = {
    "Brick-Plane": (6, 8),
    "W-1": (8, 10),
    "W-2": (8, 9),
    "Main West": (33, 6),
    "S-1": (33, 7),
}

# 111 crossover (Y=6/7 around the frog) shifts 3 CATS cells west onto
# CTC column 12 (slot 11, plate 23).
SHIFT_WEST = 3
SHIFT_CELLS = {(x, y) for x in range(38, 41) for y in (6, 7)}

HIDE_TRACK_LABELS = {
    "E Main Ext", "East Main Ext", "West Main Ext", "East Lead",
    "Main West", "Main East",
}
LABEL_LEFT = {"EH-1", "EH-2", "EH-3", "Barn"}
LABEL_AT = {
    "K-1": (59, 5),
    "K-2": (59, 8),
    "Barn": (21, 7),
    "EH-1": (21, 8),
    "EH-2": (21, 9),
    "EH-3": (21, 10),
}

# Existing CTC UniqueIDs → 20-col slot (odd = switch, even = its signal).
UID_SLOT = {
    1: 1, 2: 1,       # 101
    3: 0, 4: 0,       # 100
    5: 2, 6: 2,       # 102
    7: 3, 8: 3,       # 117
    9: 6, 10: 6,      # 116 switch-only
    11: 7, 12: 7,     # 103 switch-only
    17: 11, 18: 11,   # 111
    13: 12, 14: 12,   # 107 (lock in tables.xml; levers added if present)
    15: 13, 16: 13,   # 108
    19: 14, 20: 14,   # 109
    21: 15, 22: 15,   # 110
    23: 16, 24: 16,   # 112
    25: 17, 26: 17,   # 113
    27: 18, 28: 18,   # 114
    29: 19, 30: 19,   # 115
}

# Even UniqueID that owns LOCKTOGGLE on each packed slot.
# 32/34/36/38/40 are GUI-only until CTC columns are created (119, 118, 104–106).
SLOT_LOCK_UID = {
    0: 4, 1: 2, 2: 6, 3: 8,
    4: 32, 5: 34, 6: 10, 7: 12,
    8: 36, 9: 38, 10: 40,
    11: 18, 12: 14, 13: 16, 14: 20,
    15: 22, 16: 24, 17: 26, 18: 28, 19: 30,
}

# CATS has no occupancy edge on Main East; JMRI sensor is Block 2-3.
FALLBACK_LABEL_SENSORS = {"Main East": ("Block 2-3", "Main East")}

# OS occupancy-cut sits at the frog; lamp goes left/right of the points.
OS_FROG = {
    "OS 100": (4, 8),
    "OS 101": (5, 9),
    "OS 102": (9, 8),
    "OS 117": (15, 7),
    "OS 117b": (15, 8),
    "OS 119": (24, 8),
    "OS 118": (26, 8),
    "OS 116": (27, 7),
    "OS 103": (30, 7),
    "OS 104": (31, 8),
    "OS 105": (32, 9),
    "OS 106": (33, 10),
    "OS 111a": (40, 6),
    "OS 111b": (40, 7),
    "OS 110": (42, 7),
    "OS 112": (44, 7),
    "OS 109": (41, 8),
    "OS 108": (40, 9),
    "OS 107": (39, 10),
    "OS 113b": (52, 6),
    "OS 113a": (52, 7),
    "OS 115": (55, 6),
    "OS 114": (55, 7),
}

# (mast, cats_x, cats_y, facing, kind, IH* or None)
SIGNALS = [
    ("101RA", 6, 10, "E", "d1", "IH436"),
    ("101RB", 6, 9, "E", "d1", "IH437"),
    ("100L", 3, 8, "W", "h2", None),
    ("102LA", 10, 7, "W", "d1", "IH434"),
    ("102LB", 10, 8, "W", "h2", None),
    ("117RA", 14, 7, "E", "d1", "IH1332"),
    ("117RB", 14, 8, "E", "h2", None),
    ("117LB", 16, 7, "W", "d1", "IH1334"),
    ("117LA", 16, 8, "W", "d1", "IH1337"),
    ("111RA", 39, 6, "E", "h2", None),
    ("111RB", 39, 7, "E", "d1", "IH1236"),
    ("111L", 45, 6, "W", "h2", None),
    ("110R", 42, 7, "E", "d1", "IH1239"),
    ("112R", 44, 8, "E", "h2", None),
    ("112L", 45, 7, "W", "h2", None),
    ("113RA", 51, 6, "E", "h2", None),
    ("113RB", 51, 7, "E", "h2", None),
    ("120R", 62, 6, "E", "d1", "IH134"),
    ("115LB", 56, 6, "W", "h2", None),
    ("115LA", 56, 5, "W", "d1", "IH142"),
    ("114LB", 56, 7, "W", "h2", None),
    ("114LA", 56, 8, "W", "d1", "IH143"),
    # 120L is named L but faces east into the McKees Rocks wrap (exception).
    ("120L", 62, 7, "E", "d1", "IH141"),
]

# Packed 20: device-map plate (odd) west→east. Beans remain Switch 100–119.
# (slot, plate, [(sensor, tip), ...])
COLUMNS = [
    (0, "1", [("Block 4-2", "OS 100")]),
    (1, "3", [("Block 4-1", "OS 101")]),
    (2, "5", [("Block 4-5", "OS 102")]),
    (3, "7", [("Block 13-3", "OS 117 (yard side)"),
              ("Block 13-4", "OS 117b (main side)")]),
    (4, "9", [("Block 13-8", "OS 119")]),
    (5, "11", [("Block 13-2", "OS 118")]),
    (6, "13", [("Block 3-1", "OS 116")]),
    (7, "15", [("Block 3-2", "OS 103")]),
    (8, "17", [("Block 3-3", "OS 104")]),
    (9, "19", [("Block 3-5", "OS 105")]),
    (10, "21", [("Block 3-7", "OS 106")]),
    (11, "23", [("Block 12-4", "OS 111a (Main West side)"),
                ("Block 12-6", "OS 111b (yard side)")]),
    (12, "25", [("Block 12-1", "OS 107")]),
    (13, "27", [("Block 12-3", "OS 108")]),
    (14, "29", [("Block 12-5", "OS 109")]),
    (15, "31", [("Block 12-7", "OS 110")]),
    (16, "33", [("Block 12-8", "OS 112")]),
    (17, "35", [("Block 1-5", "OS 113b (Main West side)"),
                ("Block 1-6", "OS 113a (East Lead side)")]),
    (18, "37", [("Block 1-3", "OS 114")]),
    (19, "39", [("Block 1-4", "OS 115")]),
]

STATION_NAMES = {"BRICK", "PLANE", "BARN", "EAST END", "PRINCESS"}
SKIP_LABELS = {
    "HART RAILROAD", "NEVILLE ISLAND OPERATIONS", "P&CV DIVISION",
    "CTC DIGICON", "DS-CTC  Rev A  Eff 2026-08-11",
}

SLASH = {"UPPERSLASH", "LOWERSLASH"}
BACKSLASH = {"UPPERBACKSLASH", "LOWERBACKSLASH"}

RAIL = (255, 255, 255, 255)
PTS_N = (255, 214, 80, 255)
PTS_R = (255, 170, 40, 255)


def _save_gif(im, path: Path) -> None:
    """1-bit transparency GIF (index 0 = empty)."""
    from PIL import Image

    w, h = im.size
    rgba = im.convert("RGBA")
    pal = Image.new("P", (w, h))
    pal.putpalette(
        [0, 0, 0, 255, 255, 255, 255, 214, 80, 255, 170, 40, 255, 40, 40]
        + [0, 0, 0] * 251
    )
    data = []
    for y in range(h):
        for x in range(w):
            r, g, b, a = rgba.getpixel((x, y))
            if a < 128:
                data.append(0)
            elif r > 200 and g > 200 and b > 200:
                data.append(1)
            elif r > 200 and g < 80:
                data.append(4)
            elif g > 180:
                data.append(2)
            else:
                data.append(3)
    pal.putdata(data)
    pal.save(path, transparency=0, disposal=2)


def _bresenham(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    pts = []
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        pts.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy
    return pts


def _punch_black(im):
    im = im.convert("RGBA")
    pix = im.load()
    for y in range(im.size[1]):
        for x in range(im.size[0]):
            r, g, b, a = pix[x, y]
            if r < 40 and g < 40 and b < 40:
                pix[x, y] = (0, 0, 0, 0)
    return im


def write_cell_icons() -> None:
    from PIL import Image, ImageDraw

    THIN_DIR.mkdir(parents=True, exist_ok=True)
    n = CELL_W
    mid = n // 2
    last = n - 1
    bar = 6

    def blank():
        return Image.new("RGBA", (n, n), (0, 0, 0, 0))

    def stroke(im, x0, y0, x1, y1, color=RAIL, width=bar):
        pix = im.load()
        w, h = im.size
        dx, dy = x1 - x0, y1 - y0
        if abs(dx) >= abs(dy):
            half = width // 2
            offsets = [(0, oy) for oy in range(-half, half + 1)]
        else:
            half = width // 2
            offsets = [(ox, 0) for ox in range(-half, half + 1)]
        for x, y in _bresenham(x0, y0, x1, y1):
            for ox, oy in offsets:
                xx, yy = x + ox, y + oy
                if 0 <= xx < w and 0 <= yy < h:
                    pix[xx, yy] = color

    us = blank()
    stroke(us, 0, mid, mid, 0)
    _save_gif(us, THIN_DIR / "cell-us.gif")
    ls = blank()
    stroke(ls, mid, last, last, mid)
    _save_gif(ls, THIN_DIR / "cell-ls.gif")
    ub = blank()
    stroke(ub, mid, 0, last, mid)
    _save_gif(ub, THIN_DIR / "cell-ub.gif")
    lb = blank()
    stroke(lb, 0, mid, mid, last)
    _save_gif(lb, THIN_DIR / "cell-lb.gif")

    block = JMRI_RES / "icons/USS/track/block"
    if (block / "line025.gif").is_file():
        h = _punch_black(Image.open(block / "line025.gif"))
        _save_gif(h, THIN_DIR / "stock-h.gif")
        _save_gif(h.rotate(90, expand=True), THIN_DIR / "stock-v.gif")
    if (block / "eotwht.gif").is_file():
        _save_gif(_punch_black(Image.open(block / "eotwht.gif")),
                  THIN_DIR / "stock-end.gif")
    if not (THIN_DIR / "stock-h.gif").is_file():
        h = Image.new("RGBA", (24, 8), (0, 0, 0, 0))
        ImageDraw.Draw(h).rectangle((0, 1, 23, 6), fill=RAIL)
        _save_gif(h, THIN_DIR / "stock-h.gif")
        _save_gif(h.rotate(90, expand=True), THIN_DIR / "stock-v.gif")
    if not (THIN_DIR / "stock-end.gif").is_file():
        end = Image.new("RGBA", (26, 16), (0, 0, 0, 0))
        ImageDraw.Draw(end).rectangle((0, 4, 19, 11), fill=RAIL)
        ImageDraw.Draw(end).rectangle((19, 0, 25, 15), fill=RAIL)
        _save_gif(end, THIN_DIR / "stock-end.gif")

    def dot(color):
        im = Image.new("RGBA", (9, 9), (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse((1, 1, 7, 7), fill=color)
        return im

    _save_gif(dot(PTS_N), THIN_DIR / "pts-closed.gif")
    _save_gif(dot(PTS_R), THIN_DIR / "pts-thrown.gif")
    _save_gif(dot(PTS_N), THIN_DIR / "pts-unknown.gif")
    _save_gif(dot((180, 180, 180, 255)), THIN_DIR / "pts-inconsistent.gif")


BG = """<positionablelabel x="{x}" y="0" level="1" forcecontroloff="false" hidden="no" positionable="false" showtooltip="false" editable="true" icon="yes" class="jmri.jmrit.display.configurexml.PositionableLabelXml">
      <icon url="{u}background/{gif}" scale="1.0">
        <rotation>0</rotation>
      </icon>
    </positionablelabel>"""

TURNOUT = """<turnouticon turnout="{name}" x="{x}" y="{y}" level="7" forcecontroloff="true" hidden="no" positionable="true" showtooltip="false" editable="true" tristate="false" momentary="false" directControl="false" class="jmri.jmrit.display.configurexml.TurnoutIconXml">
      <icons>
        <closed url="{closed}" scale="1.0">
          <rotation>0</rotation>
        </closed>
        <thrown url="{thrown}" scale="1.0">
          <rotation>0</rotation>
        </thrown>
        <unknown url="{unknown}" scale="1.0">
          <rotation>0</rotation>
        </unknown>
        <inconsistent url="{inconsistent}" scale="1.0">
          <rotation>0</rotation>
        </inconsistent>
      </icons>
      <iconmaps />
    </turnouticon>"""

LAMP = """<sensoricon sensor="{sensor}" x="{x}" y="{y}" level="10" forcecontroloff="false" hidden="no" positionable="true" showtooltip="true" editable="true" momentary="false" icon="yes" class="jmri.jmrit.display.configurexml.SensorIconXml">
      <tooltip>{tip}</tooltip>
      <active url="{u}sensor/red-on.gif" scale="1.0">
        <rotation>0</rotation>
      </active>
      <inactive url="{u}sensor/red-off.gif" scale="1.0">
        <rotation>0</rotation>
      </inactive>
      <unknown url="{u}sensor/s-unknown.gif" scale="1.0">
        <rotation>0</rotation>
      </unknown>
      <inconsistent url="{u}sensor/s-inconsistent.gif" scale="1.0">
        <rotation>0</rotation>
      </inconsistent>
      <iconmaps />
    </sensoricon>"""

TRACK = """<positionablelabel x="{x}" y="{y}" level="3" forcecontroloff="false" hidden="no" positionable="true" showtooltip="false" editable="true" icon="yes" class="jmri.jmrit.display.configurexml.PositionableLabelXml">
      <icon url="{url}{gif}" degrees="0" scale="1.0">
        <rotation>{rot}</rotation>
      </icon>
    </positionablelabel>"""

TEXT = """<positionablelabel x="{x}" y="{y}" level="4" forcecontroloff="false" hidden="no" positionable="true" showtooltip="false" editable="true" text="{text}" fontname="Dialog.plain" size="{size}" style="1" red="{red}" green="{green}" blue="{blue}" hasBackground="no" justification="left" class="jmri.jmrit.display.configurexml.PositionableLabelXml">
      <tooltip>Text Label</tooltip>
    </positionablelabel>"""

LOCK_TOGGLE = """<sensoricon sensor="IS{uid}:LOCKTOGGLE" x="{x}" y="541" level="10" forcecontroloff="false" hidden="no" positionable="true" showtooltip="true" editable="true" momentary="false" icon="yes" class="jmri.jmrit.display.configurexml.SensorIconXml">
      <tooltip>IS{uid}:LOCKTOGGLE</tooltip>
      <active url="{u}plate/levers/switch-on.gif" scale="1.0">
        <rotation>0</rotation>
      </active>
      <inactive url="{u}plate/levers/switch-off.gif" scale="1.0">
        <rotation>0</rotation>
      </inactive>
      <unknown url="{u}plate/levers/switch-unknown.gif" scale="1.0">
        <rotation>0</rotation>
      </unknown>
      <inconsistent url="{u}plate/levers/switch-inconsistent.gif" scale="1.0">
        <rotation>0</rotation>
      </inconsistent>
      <iconmaps />
    </sensoricon>"""

LOCK_CAP = """<positionablelabel x="{x}" y="{y}" level="4" forcecontroloff="false" hidden="no" positionable="true" showtooltip="true" editable="true" text="{text}" fontname="Dialog.plain" size="11" style="0" red="255" green="255" blue="255" hasBackground="no" justification="centre" class="jmri.jmrit.display.configurexml.PositionableLabelXml">
      <tooltip>Text Label</tooltip>
    </positionablelabel>"""

SIG_LEVER = """<multisensoricon x="{x}" y="492" level="10" forcecontroloff="false" hidden="no" positionable="true" showtooltip="true" editable="true" updown="false" class="jmri.jmrit.display.configurexml.MultiSensorIconXml">
      <tooltip>IS{uid}:LDGL,IS{uid}:NGL,IS{uid}:RDGL</tooltip>
      <active url="{u}plate/levers/lever-left-wide.gif" scale="1.0" sensor="IS{uid}:LDGL">
        <rotation>0</rotation>
      </active>
      <active url="{u}plate/levers/lever-vertical-wide.gif" scale="1.0" sensor="IS{uid}:NGL">
        <rotation>0</rotation>
      </active>
      <active url="{u}plate/levers/lever-right-wide.gif" scale="1.0" sensor="IS{uid}:RDGL">
        <rotation>0</rotation>
      </active>
      <inactive url="{u}plate/levers/lever-inactive-wide.gif" scale="1.0">
        <rotation>0</rotation>
      </inactive>
      <unknown url="{u}plate/levers/lever-unknown-wide.gif" scale="1.0">
        <rotation>0</rotation>
      </unknown>
      <inconsistent url="{u}plate/levers/lever-inconsistent-wide.gif" scale="1.0">
        <rotation>0</rotation>
      </inconsistent>
    </multisensoricon>"""

SIG_LEVER_LN = """<multisensoricon x="{x}" y="492" level="10" forcecontroloff="false" hidden="no" positionable="true" showtooltip="true" editable="true" updown="false" class="jmri.jmrit.display.configurexml.MultiSensorIconXml">
      <tooltip>IS{uid}:LDGL,IS{uid}:NGL,</tooltip>
      <active url="{u}plate/levers/lever-left-wide.gif" scale="1.0" sensor="IS{uid}:LDGL">
        <rotation>0</rotation>
      </active>
      <active url="{u}plate/levers/lever-vertical-wide.gif" scale="1.0" sensor="IS{uid}:NGL">
        <rotation>0</rotation>
      </active>
      <inactive url="{u}plate/levers/lever-inactive-wide.gif" scale="1.0">
        <rotation>0</rotation>
      </inactive>
      <unknown url="{u}plate/levers/lever-unknown-wide.gif" scale="1.0">
        <rotation>0</rotation>
      </unknown>
      <inconsistent url="{u}plate/levers/lever-inconsistent-wide.gif" scale="1.0">
        <rotation>0</rotation>
      </inconsistent>
    </multisensoricon>"""

SIG_LEVER_NR = """<multisensoricon x="{x}" y="492" level="10" forcecontroloff="false" hidden="no" positionable="true" showtooltip="true" editable="true" updown="false" class="jmri.jmrit.display.configurexml.MultiSensorIconXml">
      <tooltip>,IS{uid}:NGL,IS{uid}:RDGL</tooltip>
      <active url="{u}plate/levers/lever-vertical-wide.gif" scale="1.0" sensor="IS{uid}:NGL">
        <rotation>0</rotation>
      </active>
      <active url="{u}plate/levers/lever-right-wide.gif" scale="1.0" sensor="IS{uid}:RDGL">
        <rotation>0</rotation>
      </active>
      <inactive url="{u}plate/levers/lever-inactive-wide.gif" scale="1.0">
        <rotation>0</rotation>
      </inactive>
      <unknown url="{u}plate/levers/lever-unknown-wide.gif" scale="1.0">
        <rotation>0</rotation>
      </unknown>
      <inconsistent url="{u}plate/levers/lever-inconsistent-wide.gif" scale="1.0">
        <rotation>0</rotation>
      </inconsistent>
    </multisensoricon>"""

KNOCKOUT = """<positionablelabel x="{x}" y="454" level="3" forcecontroloff="false" hidden="no" positionable="true" showtooltip="true" editable="true" icon="yes" class="jmri.jmrit.display.configurexml.PositionableLabelXml">
      <icon url="program:resources/icons/USSpanels/Panels/knockout.gif" degrees="0" scale="1.0">
        <rotation>0</rotation>
      </icon>
    </positionablelabel>"""

GREEN_JEWEL = """<sensoricon sensor="IS{uid}:{kind}" x="{x}" y="454" level="10" forcecontroloff="false" hidden="no" positionable="true" showtooltip="true" editable="true" momentary="false" icon="yes" class="jmri.jmrit.display.configurexml.SensorIconXml">
      <tooltip>IS{uid}:{kind}</tooltip>
      <active url="program:resources/icons/USS/sensor/green-on.gif" scale="1.0">
        <rotation>0</rotation>
      </active>
      <inactive url="program:resources/icons/USS/sensor/green-off.gif" scale="1.0">
        <rotation>0</rotation>
      </inactive>
      <unknown url="program:resources/icons/USS/sensor/s-unknown.gif" scale="1.0">
        <rotation>0</rotation>
      </unknown>
      <inconsistent url="program:resources/icons/USS/sensor/s-inconsistent.gif" scale="1.0">
        <rotation>0</rotation>
      </inconsistent>
      <iconmaps />
    </sensoricon>"""

MAST = """<signalmasticon signalmast="{name}" x="{x}" y="{y}" level="9" forcecontroloff="false" hidden="no" positionable="true" showtooltip="true" editable="true" degrees="0" clickmode="0" litmode="false" scale="1.0" imageset="{imageset}" class="jmri.jmrit.display.configurexml.SignalMastIconXml">
      <tooltip>{name}</tooltip>
    </signalmasticon>"""

HEAD = """<signalheadicon signalhead="{head}" x="{x}" y="{y}" level="9" forcecontroloff="false" hidden="no" positionable="true" showtooltip="true" editable="true" clickmode="0" litmode="false" degrees="0" class="jmri.jmrit.display.configurexml.SignalHeadIconXml">
      <tooltip>{name}</tooltip>
      <icons>
        <held url="{stop}" scale="1.0">
          <rotation>0</rotation>
        </held>
        <dark url="{unk}" scale="1.0">
          <rotation>0</rotation>
        </dark>
        <red url="{stop}" scale="1.0">
          <rotation>0</rotation>
        </red>
        <yellow url="{rest}" scale="1.0">
          <rotation>0</rotation>
        </yellow>
        <green url="{clr}" scale="1.0">
          <rotation>0</rotation>
        </green>
        <lunar url="{rest}" scale="1.0">
          <rotation>0</rotation>
        </lunar>
        <flashred url="{stop}" scale="1.0">
          <rotation>0</rotation>
        </flashred>
        <flashyellow url="{rest}" scale="1.0">
          <rotation>0</rotation>
        </flashyellow>
        <flashgreen url="{clr}" scale="1.0">
          <rotation>0</rotation>
        </flashgreen>
        <flashlunar url="{rest}" scale="1.0">
          <rotation>0</rotation>
        </flashlunar>
      </icons>
      <iconmaps />
    </signalheadicon>"""


def ux(cx: int, cy: int | None = None) -> int:
    dx = -SHIFT_WEST if cy is not None and (cx, cy) in SHIFT_CELLS else 0
    return OX + (cx - 1 + dx) * CELL_W


def bar_y(cy: int) -> int:
    return OY + (cy - 5) * CELL_H


def turnout_urls(invert: bool) -> dict[str, str]:
    base = THIN + "pts"
    urls = dict(
        closed=base + "-closed.gif",
        thrown=base + "-thrown.gif",
        unknown=base + "-unknown.gif",
        inconsistent=base + "-inconsistent.gif",
    )
    if invert:
        urls["closed"], urls["thrown"] = urls["thrown"], urls["closed"]
    return urls


def sig_url(kind: str, aspect: str, facing: str) -> str:
    suf = "-w" if facing == "W" else ""
    return "preference:ctc/icons/sig-%s-%s%s.gif" % (kind, aspect, suf)


def signal_xy(stem_x: int, bar_c: int, facing: str, kind: str) -> tuple[int, int]:
    width = 21 if kind == "h2" else 12
    x = stem_x if facing == "E" else stem_x - width + 1
    return x, bar_c - 3


def parse_cats(path: Path) -> dict:
    root = ET.parse(path).getroot()
    tp = root.find("TRACKPLAN")
    cells: dict[tuple[int, int], dict] = {}
    for sec in tp.findall("SECTION"):
        x, y = int(sec.get("X")), int(sec.get("Y"))
        tracks = [(t.text or "").strip() for t in sec.findall("TRACKGROUP/TRACK")]
        tracks = [t for t in tracks if t]
        sn = sec.find("SEC_NAME")
        name = sn.get("NAME") if sn is not None else None
        blocks = []
        for se in sec.findall("SEC_EDGE"):
            edge = se.get("EDGE")
            for blk in se.findall("BLOCK"):
                bname = blk.get("NAME")
                ios = blk.find("OCCUPIEDSPEC/IOSPEC")
                sensor = ios.get("USER_NAME") if ios is not None else None
                if bname or sensor:
                    blocks.append((edge, bname, sensor))
        cells[(x, y)] = dict(tracks=tracks, name=name, blocks=blocks)
    return cells


def _norm_name(name: str | None) -> str:
    s = name or ""
    if s.endswith(", PA"):
        s = s[:-4]
    return {"E Main Ext": "East Main Ext"}.get(s, s)


def _jewel_xy(cx: int, cy: int) -> tuple[int, int]:
    return ux(cx, cy) + (CELL_W - 21) // 2, bar_y(cy) + (CELL_H - 21) // 2


def _throat_cell(os_cells: set[tuple[int, int]], frog: tuple[int, int]) -> tuple[int, int]:
    """Cell beside the points, not the frog and not a far signal cell."""
    fx, fy = frog
    adj = [p for p in os_cells if abs(p[0] - fx) + abs(p[1] - fy) == 1]
    left = [p for p in adj if p[0] < fx and p[1] == fy]
    if left:
        return left[0]
    vert = [p for p in adj if p[0] == fx]
    if vert:
        return vert[0]
    if frog in os_cells:
        return frog
    right = [p for p in adj if p[0] > fx and p[1] == fy]
    if right:
        return right[0]
    if os_cells:
        return min(os_cells, key=lambda p: abs(p[0] - fx) + abs(p[1] - fy))
    return frog


def _os_jewel_xy(pick: tuple[int, int], frog: tuple[int, int]) -> tuple[int, int]:
    jx, jy = _jewel_xy(*pick)
    fx, fy = frog
    if pick[0] < fx:
        jx -= 6
    elif pick[0] > fx:
        jx += 6
    elif pick[1] < fy:
        jy -= 6
    elif pick[1] > fy:
        jy += 6
    else:
        jx -= CELL_W
    return jx, jy


def build_geometry(cells: dict) -> tuple[list, list, list, list]:
    turnouts = []
    tracks = []
    lamps = []
    texts = []

    for xy, (name, invert) in PLANTS.items():
        cx, cy = xy
        turnouts.append((name, ux(cx, cy) + 5, bar_y(cy) + 5, invert))

    for (x, y), cell in cells.items():
        if y < 5 or y > 12:
            continue
        kinds = set(cell["tracks"])
        if "HORIZONTAL" in kinds:
            gif, dx, dy = STOCK_H
            tracks.append((ux(x, y) + dx, bar_y(y) + dy, gif, 0))
        if "VERTICAL" in kinds:
            gif, dx, dy = STOCK_V
            tracks.append((ux(x, y) + dx, bar_y(y) + dy, gif, 0))
        for kind in kinds:
            gif = CELL_GIF.get(kind)
            if gif:
                tracks.append((ux(x, y), bar_y(y), gif, 0))
        for edge, bname, _sensor in cell["blocks"]:
            if edge == "RIGHT" and (x + 1, y) not in cells and bname:
                gif, dx, dy = STOCK_END
                tracks.append((ux(x, y) + dx, bar_y(y) + dy, gif, 0))

    # 111 shift leaves a 3-cell hole at the original frog; fill with mains.
    gif, dx, dy = STOCK_H
    for x, y in SHIFT_CELLS:
        tracks.append((OX + (x - 1) * CELL_W + dx, bar_y(y) + dy, gif, 0))

    occ: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    name_sensor: dict[str, str] = {}
    for (x, y), cell in cells.items():
        if y < 5 or y > 12:
            continue
        for _edge, bname, sensor in cell["blocks"]:
            if not sensor:
                continue
            occ[sensor].append((x, y, bname or ""))
            n = _norm_name(bname)
            if n and not n.startswith("OS "):
                name_sensor[n] = sensor

    placed: set[str] = set()
    for sensor, hits in occ.items():
        os_hits = [(x, y, n) for x, y, n in hits if n.startswith("OS ")]
        if not os_hits:
            continue
        os_name = os_hits[0][2]
        frog = OS_FROG.get(os_name)
        os_cells = {(x, y) for x, y, _n in os_hits}
        if frog is None:
            frog = min(os_cells)
        pick = _throat_cell(os_cells, frog)
        jx, jy = _os_jewel_xy(pick, frog)
        lamps.append((sensor, jx, jy, os_name))
        placed.add(sensor)

    for (x, y), cell in cells.items():
        raw = cell["name"]
        if not raw or raw in SKIP_LABELS or raw in STATION_NAMES:
            continue
        name = _norm_name(raw)
        sensor = name_sensor.get(name)
        tip = name
        if not sensor and raw in FALLBACK_LABEL_SENSORS:
            sensor, tip = FALLBACK_LABEL_SENSORS[raw]
        if not sensor or sensor in placed:
            continue
        cx, cy = CENTER_OCC.get(name, (x, y))
        jx, jy = _jewel_xy(cx, cy)
        lamps.append((sensor, jx, jy, tip))
        placed.add(sensor)

    for sensor, hits in occ.items():
        if sensor in placed:
            continue
        non_os = [(x, y, n) for x, y, n in hits if not n.startswith("OS ")]
        if not non_os:
            continue
        ys = sorted(h[1] for h in non_os)
        my = ys[len(ys) // 2]
        on_row = sorted((h for h in non_os if h[1] == my), key=lambda h: h[0])
        hx, hy, bname = on_row[len(on_row) // 2]
        name = _norm_name(bname)
        cx, cy = CENTER_OCC.get(name, (hx, hy))
        jx, jy = _jewel_xy(cx, cy)
        lamps.append((sensor, jx, jy, bname or sensor))
        placed.add(sensor)

    jewel_cells: set[tuple[int, int]] = set()
    for _sensor, jx, jy, _tip in lamps:
        if jy >= OS_Y - 5:
            continue
        jewel_cells.add(((jx - OX) // CELL_W + 1, (jy - OY) // CELL_H + 5))

    texts.append((480, 8, "HART RAILROAD - NEVILLE ISLAND", 16, dict(red=0, green=0, blue=0)))
    for (x, y), cell in cells.items():
        name = cell["name"]
        if not name or name in SKIP_LABELS:
            continue
        if name.endswith(", PA"):
            name = name[:-4]
        if name in STATION_NAMES:
            texts.append((ux(x, y), STATION_Y, name, 12, WHITE))
            continue
        if name in HIDE_TRACK_LABELS or _norm_name(name) in HIDE_TRACK_LABELS:
            continue
        lx, ly = LABEL_AT.get(name, (x, y))
        if name in LABEL_LEFT or (lx, ly) in jewel_cells:
            prefer = -1 if name in LABEL_LEFT else 1
            if (lx, ly) in jewel_cells:
                if (lx + prefer, ly) not in jewel_cells:
                    lx += prefer
                elif (lx - prefer, ly) not in jewel_cells:
                    lx -= prefer
        texts.append((ux(lx, ly) + 1, bar_y(ly) - 6, name, 8, CREAM))
    main_x = 12 + 65 * 8 + 65  # packed columns 9–10
    texts.append((main_x, bar_y(6) - 6, "Main", 8, CREAM))
    texts.append((main_x, bar_y(12) - 6, "Main", 8, CREAM))
    return turnouts, tracks, lamps, texts


def build_block(cells: dict) -> str:
    turnouts, tracks, lamps, texts = build_geometry(cells)
    parts = []
    parts.append(BG.format(x=0, u=U, gif="Panel-left-7.gif"))
    for slot in range(N_SLOTS):
        if slot in BLANK_SLOTS:
            gif = "Panel-blank-7.gif"
        elif slot in SWITCH_ONLY_SLOTS:
            gif = "Panel-switch-7.gif"
        else:
            gif = "Panel-sw-sig-7.gif"
        parts.append(BG.format(x=12 + 65 * slot, u=U, gif=gif))
    parts.append(BG.format(x=12 + 65 * N_SLOTS, u=U, gif="Panel-right-7.gif"))
    for name, x, y, invert in turnouts:
        parts.append(TURNOUT.format(name=name, x=x, y=y, **turnout_urls(invert)))
    for item in lamps:
        sensor, x, y, tip = item
        parts.append(LAMP.format(sensor=sensor, x=x, y=y, tip=tip, u=U))
    for x, y, gif, rot in tracks:
        parts.append(TRACK.format(x=x, y=y, gif=gif, rot=rot, url=THIN))
    for x, y, text, size, col in texts:
        parts.append(TEXT.format(x=x, y=y, text=text, size=size, **col))
    for name, cx, cy, facing, kind, head in SIGNALS:
        stem_x = ux(cx, cy) + (8 if facing == "E" else 2)
        x, y = signal_xy(stem_x, bar_y(cy) + 2, facing, kind)
        if kind == "h2":
            parts.append(MAST.format(
                name=name, x=x, y=y,
                imageset="ctc-w" if facing == "W" else "ctc"))
        else:
            parts.append(HEAD.format(
                name=name, head=head, x=x, y=y,
                stop=sig_url("d1", "stop", facing),
                rest=sig_url("d1", "restricting", facing),
                clr=sig_url("d1", "slow-clear", facing),
                unk=sig_url("d1", "unknown", facing)))
    for slot in range(N_SLOTS):
        origin = 12 + 65 * slot
        parts.append(LOCK_TOGGLE.format(
            uid=SLOT_LOCK_UID[slot], x=origin + 21, u=U))
        parts.append(LOCK_CAP.format(x=origin + 48, y=536, text="Local"))
        parts.append(LOCK_CAP.format(x=origin + 48, y=560, text="Locked"))
    return "    " + "\n    ".join(parts) + "\n"


STRIP = [
    re.compile(r"\s*<turnouticon\b[^>]*>.*?</turnouticon>", re.S),
    re.compile(r"\s*<sensoricon\b[^>]*sensor=\"Block [^\"]*\".*?</sensoricon>", re.S),
    re.compile(
        r"\s*<positionablelabel\b[^>]*>\s*<icon url=\"(?:[^\"]*USS/(?:track/block|background)/|preference:ctc/icons/)[^\"]*\".*?</positionablelabel>",
        re.S,
    ),
    re.compile(
        r"\s*<positionablelabel\b[^>]*red=\"220\" green=\"220\" blue=\"180\".*?</positionablelabel>",
        re.S,
    ),
    re.compile(
        r"\s*<positionablelabel\b[^>]*text=\"(?:BRICK|PLANE|BARN|EAST END|PRINCESS|\d+|HART RAILROAD[^\"]*)\".*?</positionablelabel>",
        re.S,
    ),
    re.compile(r"\s*<sensoricon\b[^>]*sensor=\"IS\d+:UNLOCKEDINDICATOR\".*?</sensoricon>", re.S),
    re.compile(r"\s*<sensoricon\b[^>]*sensor=\"IS\d+:LOCKTOGGLE\".*?</sensoricon>", re.S),
    re.compile(r"\s*<positionablelabel\b[^>]*text=\"Unlocked\".*?</positionablelabel>", re.S),
    re.compile(r"\s*<positionablelabel\b[^>]*text=\"(?:Local|Locked)\".*?</positionablelabel>", re.S),
    re.compile(r"\s*<signalmasticon\b[^>]*/>", re.S),
    re.compile(r"\s*<signalmasticon\b[^>]*>.*?</signalmasticon>", re.S),
    re.compile(r"\s*<signalheadicon\b[^>]*>.*?</signalheadicon>", re.S),
]


def reposition_levers(text: str) -> str:
    """Slide existing UniqueID lever groups onto the 20-column slots."""
    xs: dict[int, list[int]] = defaultdict(list)
    for m in re.finditer(r'sensor="IS(\d+):[^"]+" x="(\d+)"', text):
        xs[int(m.group(1))].append(int(m.group(2)))
    for uid, slot in UID_SLOT.items():
        if uid not in xs:
            continue
        cur = int(round((min(xs[uid]) - 12) / 65.0))
        delta = (12 + 65 * slot) - (12 + 65 * cur)
        if delta == 0:
            continue
        text = re.sub(
            r'(sensor="IS%d:[^"]+" x=")(\d+)(")' % uid,
            lambda m, d=delta: "%s%d%s" % (m.group(1), int(m.group(2)) + d, m.group(3)),
            text,
        )

    def _ms(m: re.Match) -> str:
        block = m.group(0)
        uid_m = re.search(r"IS(\d+):", block)
        if not uid_m:
            return block
        uid = int(uid_m.group(1))
        if uid not in UID_SLOT:
            return block
        xm = re.search(r'<multisensoricon x="(\d+)"', block)
        if not xm:
            return block
        x = int(xm.group(1))
        cur = int(round((x - 12) / 65.0))
        d = (12 + 65 * UID_SLOT[uid]) - (12 + 65 * cur)
        if d == 0:
            return block
        return re.sub(
            r'(<multisensoricon x=")(\d+)(")',
            lambda mm, delta=d: "%s%d%s" % (mm.group(1), int(mm.group(2)) + delta, mm.group(3)),
            block,
            count=1,
        )

    return re.sub(r"<multisensoricon\b.*?</multisensoricon>", _ms, text, flags=re.S)


def _replace_signal_lever(text: str, uid: int, xml: str) -> str:
    return re.sub(
        r'<multisensoricon x="\d+" y="492"[^>]*>.*?</multisensoricon>',
        lambda m, uid=uid, xml=xml: xml if ("IS%d:" % uid) in m.group(0) else m.group(0),
        text,
        flags=re.S,
    )


def _replace_sensoricon(text: str, sensor: str, xml: str) -> str:
    return re.sub(
        r'<sensoricon sensor="%s"[^>]*>.*?</sensoricon>' % re.escape(sensor),
        xml,
        text,
        count=1,
        flags=re.S,
    )


def _replace_knockout_at(text: str, x: int, xml: str) -> str:
    return re.sub(
        r'<positionablelabel x="%d" y="454"[^>]*>\s*<icon url="[^"]*knockout\.gif"[^>]*>.*?</positionablelabel>'
        % x,
        xml,
        text,
        count=1,
        flags=re.S,
    )


def _has_knockout_at(text: str, x: int) -> bool:
    return bool(
        re.search(
            r'x="%d" y="454"[^>]*>\s*<icon url="[^"]*knockout\.gif"' % x,
            text,
        )
    )


def fix_brick_signal_levers(text: str) -> str:
    """Column 1 = N/R, 101 = L/N. 102 stays L/N, 117 stays LNR."""
    text = _replace_signal_lever(text, 4, SIG_LEVER_NR.format(uid=4, x=20, u=U))
    text = _replace_signal_lever(text, 2, SIG_LEVER_LN.format(uid=2, x=85, u=U))

    if re.search(r'sensor="IS4:LDGK"', text):
        text = _replace_sensoricon(text, "IS4:LDGK", KNOCKOUT.format(x=16))
    if _has_knockout_at(text, 50) and not re.search(r'sensor="IS4:RDGK"', text):
        text = _replace_knockout_at(text, 50, GREEN_JEWEL.format(uid=4, kind="RDGK", x=50))

    if _has_knockout_at(text, 81) and not re.search(r'sensor="IS2:LDGK"', text):
        text = _replace_knockout_at(text, 81, GREEN_JEWEL.format(uid=2, kind="LDGK", x=81))
    if re.search(r'sensor="IS2:RDGK"', text):
        text = _replace_sensoricon(text, "IS2:RDGK", KNOCKOUT.format(x=115))

    if not _has_knockout_at(text, 180):
        text = re.sub(
            r'(<sensoricon sensor="IS6:NGK"[^>]*>.*?</sensoricon>)',
            r"\1\n    " + KNOCKOUT.format(x=180),
            text,
            count=1,
            flags=re.S,
        )
    return text


def _ctc_uid_block(text: str, uid: int) -> re.Match | None:
    return re.search(
        r"<ctcCodeButtonData>\s*<UniqueID>%d</UniqueID>.*?</ctcCodeButtonData>" % uid,
        text,
        re.S,
    )


def _sidi_signal_list(tag: str, names: list[str]) -> str:
    if not names:
        return "      <%s />" % tag
    inner = "\n".join("        <signal>%s</signal>" % n for n in names)
    return "      <%s>\n%s\n      </%s>" % (tag, inner, tag)


def _set_sidi_lists(block: str, direction: str, ltr: list[str], rtl: list[str], swap_trl: bool) -> str:
    block = re.sub(
        r"<SIDI_TrafficDirection>[A-Z]+</SIDI_TrafficDirection>",
        "<SIDI_TrafficDirection>%s</SIDI_TrafficDirection>" % direction,
        block,
        count=1,
    )
    block = re.sub(
        r"      <SIDI_LeftRightTrafficSignals(?: />|>.*?</SIDI_LeftRightTrafficSignals>)",
        _sidi_signal_list("SIDI_LeftRightTrafficSignals", ltr),
        block,
        count=1,
        flags=re.S,
    )
    block = re.sub(
        r"      <SIDI_RightLeftTrafficSignals(?: />|>.*?</SIDI_RightLeftTrafficSignals>)",
        _sidi_signal_list("SIDI_RightLeftTrafficSignals", rtl),
        block,
        count=1,
        flags=re.S,
    )
    if not swap_trl:
        return block
    left_m = re.search(r"<TRL_LeftRules(?: />|>(.*?)</TRL_LeftRules>)", block, re.S)
    right_m = re.search(r"<TRL_RightRules(?: />|>(.*?)</TRL_RightRules>)", block, re.S)
    if not left_m or not right_m:
        return block
    left_inner = left_m.group(1) if left_m.lastindex else ""
    right_inner = right_m.group(1) if right_m.lastindex else ""

    def rules(tag: str, inner: str | None) -> str:
        if not inner or not inner.strip():
            return "      <%s />" % tag
        return "      <%s>%s</%s>" % (tag, inner, tag)

    block = re.sub(
        r"      <TRL_LeftRules(?: />|>.*?</TRL_LeftRules>)",
        rules("TRL_LeftRules", right_inner),
        block,
        count=1,
        flags=re.S,
    )
    block = re.sub(
        r"      <TRL_RightRules(?: />|>.*?</TRL_RightRules>)",
        rules("TRL_RightRules", left_inner),
        block,
        count=1,
        flags=re.S,
    )
    return block


def patch_brick_sidi(text: str) -> str:
    """Column 1 (100) codes from R; 101 codes from L — match the 2-position levers."""
    specs = (
        (13, "LEFT", [], ["101RA", "101RB"]),
        (14, "RIGHT", ["100L"], []),
    )
    for uid, direction, ltr, rtl in specs:
        m = _ctc_uid_block(text, uid)
        if not m:
            continue
        block = m.group(0)
        already = "<SIDI_TrafficDirection>%s</SIDI_TrafficDirection>" % direction in block
        block = _set_sidi_lists(block, direction, ltr, rtl, swap_trl=not already)
        text = text[: m.start()] + block + text[m.end() :]
    return text


def apply(text: str, cells: dict, close_tag: str = "</paneleditor>") -> str:
    text = reposition_levers(text)
    text = fix_brick_signal_levers(text)
    for pat in STRIP:
        text = pat.sub("", text)
    text = re.sub(
        r'(<paneleditor\b[^>]*?) x="-?\d+" y="-?\d+" height="\d+" width="\d+"',
        r'\1 x="40" y="40" height="%d" width="%d"' % (PANEL_H, PANEL_W),
        text,
        count=1,
    )
    idx = text.rindex(close_tag)
    return text[:idx] + build_block(cells) + "  " + text[idx:]


def resolve_icon(url: str) -> Path | None:
    if url.startswith("program:resources/"):
        return JMRI_RES / url[len("program:resources/"):]
    if url.startswith("preference:ctc/icons/"):
        return THIN_DIR / url.split("/")[-1]
    return None


def render_preview(gui_text: str, out: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    W, H = PANEL_W, 300
    S = 2
    img = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 22)
        font_sm = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 14)
    except OSError:
        font = font_sm = ImageFont.load_default()

    def paste(path: Path, x: int, y: int, rot: int = 0) -> None:
        if not path.exists():
            return
        tile = Image.open(path).convert("RGBA")
        if rot:
            tile = tile.rotate(-90 * rot, expand=True)
        tile = tile.resize((tile.size[0] * S, tile.size[1] * S), Image.Resampling.NEAREST)
        img.alpha_composite(tile, (x * S, y * S))

    for m in re.finditer(
        r'<positionablelabel x="(\d+)" y="(\d+)"[^>]*>\s*<icon url="([^"]+)"[^>]*>(?:\s*<rotation>(\d+)</rotation>)?',
        gui_text,
    ):
        x, y, url, rot = int(m.group(1)), int(m.group(2)), m.group(3), int(m.group(4) or 0)
        if y > H:
            continue
        p = resolve_icon(url)
        if p:
            paste(p, x, y, rot)

    for m in re.finditer(
        r'<turnouticon turnout="([^"]+)" x="(\d+)" y="(\d+)"[^>]*>.*?<closed url="([^"]+)"',
        gui_text,
        re.S,
    ):
        x, y, url = int(m.group(2)), int(m.group(3)), m.group(4)
        if y > H:
            continue
        p = resolve_icon(url)
        if p:
            paste(p, x, y)

    for m in re.finditer(
        r'<sensoricon sensor="([^"]+)" x="(\d+)" y="(\d+)"',
        gui_text,
    ):
        x, y = int(m.group(2)), int(m.group(3))
        if y > H:
            continue
        p = resolve_icon(U + "sensor/red-off.gif")
        if p:
            paste(p, x, y)

    for m in re.finditer(
        r'<positionablelabel x="(\d+)" y="(\d+)"[^>]*text="([^"]+)"[^>]*size="(\d+)"[^>]*red="(\d+)" green="(\d+)" blue="(\d+)"',
        gui_text,
    ):
        x, y, text, size = int(m.group(1)), int(m.group(2)), m.group(3), int(m.group(4))
        rgb = (int(m.group(5)), int(m.group(6)), int(m.group(7)))
        if y > H:
            continue
        draw.text((x * S, y * S), text, fill=rgb + (255,),
                  font=font if size >= 12 else font_sm)

    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out)
    print("preview %s (%dx%d)" % (out, W * S, H * S))


def install_preference_icons() -> list[Path]:
    """Copy preference:ctc/icons GIFs (and GUIObjects.xml) into local profiles."""
    dests: list[Path] = []
    candidates = [
        Path.home() / "JMRI_UserFiles",
        Path.home() / "Library/Preferences/JMRI",
        Path.home() / ".jmri",
        Path.home() / "JMRI",
    ]
    for base in candidates:
        if not base.is_dir():
            continue
        if base.name == "JMRI_UserFiles":
            dests.append(base / "ctc")
        dests.extend(p / "ctc" for p in base.glob("*.jmri") if p.is_dir())
    written: list[Path] = []
    gifs = sorted(THIN_DIR.glob("*.gif"))
    if not gifs:
        return written
    for dest in dests:
        icons = dest / "icons"
        icons.mkdir(parents=True, exist_ok=True)
        for gif in gifs:
            target = icons / gif.name
            target.write_bytes(gif.read_bytes())
            written.append(target)
        if GUI_XML.is_file():
            panel = dest / "GUIObjects.xml"
            panel.write_bytes(GUI_XML.read_bytes())
            written.append(panel)
        print("CTC icons -> %s" % dest)
    return written


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cats", type=Path, default=CATS_XML)
    ap.add_argument("--gui", type=Path, default=GUI_XML)
    ap.add_argument("--tables", type=Path, default=None,
                    help="Optional. output/tables.xml or tables/new_tables.xml — never tables/tables.xml")
    ap.add_argument("--preview", type=Path, default=None)
    args = ap.parse_args()
    if args.tables and args.tables.resolve() == SOURCE_TABLES.resolve():
        sys.exit("refusing to write tables/tables.xml")

    write_cell_icons()
    cells = parse_cats(args.cats)
    txt = args.gui.read_text()
    new = apply(txt, cells)
    args.gui.write_text(new)
    print("%s: Master 4 track plan regenerated" % args.gui)
    install_preference_icons()

    pe = re.search(r"<paneleditor\b.*?</paneleditor>", new, re.S)
    assert pe, "no paneleditor in regenerated GUI"

    def embed(path: Path, replace_panel: bool) -> None:
        tables = path.read_text()
        if replace_panel:
            m = re.search(r"<paneleditor\b.*?</paneleditor>", tables, re.S)
            assert m, "no paneleditor in %s" % path
            tables = tables[: m.start()] + pe.group(0) + tables[m.end() :]
        patched = patch_brick_sidi(tables)
        if patched != tables or replace_panel:
            path.write_text(patched)
            print("%s: %s" % (
                path,
                "paneleditor replaced, Brick SIDI updated" if replace_panel
                else "Brick SIDI updated",
            ))

    if args.tables:
        embed(args.tables, replace_panel=True)
    if NEW_TABLES.is_file() and (
        not args.tables or args.tables.resolve() != NEW_TABLES.resolve()
    ):
        embed(NEW_TABLES, replace_panel=False)

    if args.preview:
        render_preview(new, args.preview)


if __name__ == "__main__":
    main()
