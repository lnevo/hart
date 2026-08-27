#!/usr/bin/env python3
"""Generate the USS CTC track diagram from CATS Master 4 (v60).

20 packed columns (device-map plates 1…39), CATS geometry stretched to
the gold board. New plants are switch-only. Beans stay Switch 100–119.
Default write is GUIObjects.xml only — CTC logic / tables.xml later.

    python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py
    python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py --preview cats/screenshots/master4/uss_ctc_v60_preview.png
"""
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CATS_XML = ROOT / "cats/panels/HART_Master4.xml"
GUI_XML = ROOT / "jmri/layouts/hart/ctc/GUIObjects.xml"
THIN_DIR = ROOT / "jmri/layouts/hart/ctc/icons"
JMRI_RES = Path("/Applications/JMRI/resources")

U = "program:resources/icons/USS/"
THIN = "preference:ctc/icons/"

# Square cells. 20 packed tiles: 12 + 20*65 + 12 = 1324.
# USS background: gold 0–31, silver 32–36, dark diagram 38–275.
OX, OY = 8, 62
CELL_W, CELL_H = 21, 21
OS_Y = 240
STATION_Y = 42
PANEL_W, PANEL_H = 1400, 800

N_SLOTS = 20
BLANK_SLOTS: set[int] = set()
# 119, 118, 116, 103, 104, 105, 106, 107, 108, 109 — switch-only, local later.
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
# CATS has no occupancy edge on Main East; JMRI sensor is Block 2-3.
FALLBACK_LABEL_SENSORS = {"Main East": ("Block 2-3", "Main East")}

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
    ("120R", 61, 6, "E", "d1", "IH134"),
    ("114LA", 56, 7, "W", "d1", "IH143"),
    ("114LB", 56, 8, "W", "h2", None),
    ("120L", 60, 6, "W", "d1", "IH141"),
    ("115LA", 56, 6, "W", "d1", "IH142"),
    ("115LB", 56, 5, "W", "h2", None),
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


def ux(cx: int) -> int:
    return OX + (cx - 1) * CELL_W


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
    return ux(cx) + (CELL_W - 21) // 2, bar_y(cy) + (CELL_H - 21) // 2


def build_geometry(cells: dict) -> tuple[list, list, list, list]:
    turnouts = []
    tracks = []
    lamps = []
    texts = []

    for xy, (name, invert) in PLANTS.items():
        cx, cy = xy
        turnouts.append((name, ux(cx) + 5, bar_y(cy) + 5, invert))

    for (x, y), cell in cells.items():
        if y < 5 or y > 12:
            continue
        kinds = set(cell["tracks"])
        if "HORIZONTAL" in kinds:
            gif, dx, dy = STOCK_H
            tracks.append((ux(x) + dx, bar_y(y) + dy, gif, 0))
        if "VERTICAL" in kinds:
            gif, dx, dy = STOCK_V
            tracks.append((ux(x) + dx, bar_y(y) + dy, gif, 0))
        for kind in kinds:
            gif = CELL_GIF.get(kind)
            if gif:
                tracks.append((ux(x), bar_y(y), gif, 0))
        for edge, bname, _sensor in cell["blocks"]:
            if edge == "RIGHT" and (x + 1, y) not in cells and bname:
                gif, dx, dy = STOCK_END
                tracks.append((ux(x) + dx, bar_y(y) + dy, gif, 0))

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
        jx, jy = _jewel_xy(x, y)
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
        jx, jy = _jewel_xy(hx, hy)
        lamps.append((sensor, jx, jy, bname or sensor))
        placed.add(sensor)

    for slot, _plate, lamps_spec in COLUMNS:
        for i, (sensor, tip) in enumerate(lamps_spec):
            extra = 24 if i else 0
            lamps.append((sensor, slot * 65 + 34 + extra, OS_Y, tip))

    texts.append((480, 8, "HART RAILROAD - NEVILLE ISLAND", 16, dict(red=0, green=0, blue=0)))
    for (x, y), cell in cells.items():
        name = cell["name"]
        if not name or name in SKIP_LABELS:
            continue
        if name.endswith(", PA"):
            name = name[:-4]
        if name in STATION_NAMES:
            texts.append((ux(x), STATION_Y, name, 12, WHITE))
            continue
        texts.append((ux(x) + CELL_W + 1, bar_y(y) + 4, name, 8, CREAM))
    for slot, plate, _lamps in COLUMNS:
        texts.append((slot * 65 + 37, OS_Y + 23, plate, 8, WHITE))
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
        stem_x = ux(cx) + (8 if facing == "E" else 2)
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
    re.compile(r"\s*<positionablelabel\b[^>]*text=\"Unlocked\".*?</positionablelabel>", re.S),
    re.compile(r"\s*<signalmasticon\b[^>]*/>", re.S),
    re.compile(r"\s*<signalmasticon\b[^>]*>.*?</signalmasticon>", re.S),
    re.compile(r"\s*<signalheadicon\b[^>]*>.*?</signalheadicon>", re.S),
]


def apply(text: str, cells: dict, close_tag: str = "</paneleditor>") -> str:
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
        if y > H or "background/" in url:
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
                    help="Optional. Only tables/new_tables.xml — never tables.xml")
    ap.add_argument("--preview", type=Path, default=None)
    args = ap.parse_args()
    if args.tables and args.tables.name == "tables.xml":
        sys.exit("refusing to write tables/tables.xml")

    write_cell_icons()
    install_preference_icons()
    cells = parse_cats(args.cats)
    txt = args.gui.read_text()
    new = apply(txt, cells)
    args.gui.write_text(new)
    print("%s: Master 4 track plan regenerated" % args.gui)

    if args.tables:
        tables = args.tables.read_text()
        m = re.search(r"<paneleditor\b.*?</paneleditor>", tables, re.S)
        assert m, "no paneleditor in %s" % args.tables
        new_panel = apply(m.group(0), cells)
        args.tables.write_text(tables[: m.start()] + new_panel + tables[m.end():])
        print("%s: embedded paneleditor regenerated" % args.tables)

    if args.preview:
        render_preview(new, args.preview)


if __name__ == "__main__":
    main()
