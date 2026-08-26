#!/usr/bin/env python3
"""Generate the USS CTC track diagram from CATS Master 4 (v56).

Reads `cats/panels/HART_Master4.xml` and places USS tiles on the same
west→east / north→south grid as the Digicon. Lever plates are unchanged.
Default write is `ctc/GUIObjects.xml` only (does not touch `tables.xml`).

    python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py
    python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py --preview cats/screenshots/master4/uss_ctc_v56_preview.png

`--tables tables/new_tables.xml` also rewrites the embedded paneleditor.
Never pass `tables/tables.xml`.
"""
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CATS_XML = ROOT / "cats/panels/HART_Master4.xml"
GUI_XML = ROOT / "jmri/layouts/hart/ctc/GUIObjects.xml"
THIN_DIR = ROOT / "jmri/layouts/hart/ctc/icons"
JMRI_RES = Path("/Applications/JMRI/resources")

U = "program:resources/icons/USS/"
THIN = "preference:ctc/icons/"

# CATS cell → USS pixels. 17-slot gold board is 12 + 17*65 + 12 = 1129.
OX, OY = 10, 52
CELL_W, CELL_H = 17, 22
OS_Y = 255
STATION_Y = 36

N_SLOTS = 17
BLANK_SLOTS = {0, 4, 8, 12, 16}
SWITCH_ONLY_SLOTS = {6, 7}

CREAM = dict(red=220, green=220, blue=180)
WHITE = dict(red=255, green=255, blue=255)

# CATS frog cell → (JMRI turnout, icon kind, dy from bar_y).
# Crossovers sit on the upper cell and span CELL_H into the lower.
# swap: = invert vs JMRI (100 / 114 / 115).
PLANTS = {
    (4, 8): ("Switch 100", "swap:track/turnout/right/east/os-r-e", -6),
    (5, 9): ("Switch 101", "track/turnout/right/east/os-r-e", -6),
    (9, 8): ("Switch 102", "track/turnout/left/east/os-l-e", -28),
    (15, 7): ("Switch 117", "track/crossover/right/os-r-sc", -6),
    (24, 8): ("Switch 119", "thin:os-r-e-thin", -6),
    (26, 8): ("Switch 118", "thin:os-r-e-thin", -6),
    (27, 7): ("Switch 116", "thin:os-r-e-thin", -6),
    (30, 7): ("Switch 103", "thin:os-r-e-thin", -6),
    (31, 8): ("Switch 104", "track/turnout/right/east/os-r-e", -6),
    (32, 9): ("Switch 105", "track/turnout/right/east/os-r-e", -6),
    (33, 10): ("Switch 106", "track/turnout/right/east/os-r-e", -6),
    (39, 10): ("Switch 107", "thin:os-l-w-thin", -6),
    (40, 9): ("Switch 108", "thin:os-l-w-thin", -6),
    (41, 8): ("Switch 109", "thin:os-l-w-thin", -6),
    (40, 6): ("Switch 111", "track/crossover/left/os-l-sc", -6),
    (42, 7): ("Switch 110", "thin:os-l-w-thin", -6),
    (44, 7): ("Switch 112", "track/turnout/left/west/os-l-w", -6),
    (52, 6): ("Switch 113", "track/crossover/right/os-r-sc", -6),
    (55, 6): ("Switch 115", "swap:track/turnout/left/east/os-l-e", -28),
    (55, 7): ("Switch 114", "swap:track/turnout/right/east/os-r-e", -6),
}
# Lower half of a crossover — rails come from the scissor icon.
SKIP_RAIL_CELLS = {(15, 8), (40, 7), (52, 7)}

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

# Lever-column OS lamps (slot, sensor, tooltip). Crossovers get two.
OS_ROW = [
    (1, "Block 4-1", "OS 101"),
    (2, "Block 4-2", "OS 100"),
    (3, "Block 4-5", "OS 102"),
    (5, "Block 13-3", "OS 117 (yard side)"),
    (5, "Block 13-4", "OS 117b (main side)", 24),
    (6, "Block 3-1", "OS 116"),
    (7, "Block 3-2", "OS 103"),
    (9, "Block 12-4", "OS 111a (Main West side)"),
    (9, "Block 12-6", "OS 111b (yard side)", 24),
    (10, "Block 12-7", "OS 110"),
    (11, "Block 12-8", "OS 112"),
    (13, "Block 1-5", "OS 113b (Main West side)"),
    (13, "Block 1-6", "OS 113a (East Lead side)", 24),
    (14, "Block 1-3", "OS 114"),
    (15, "Block 1-4", "OS 115"),
]

OS_NUMBERS = [
    (1, "101"), (2, "100"), (3, "102"),
    (5, "117"), (6, "116"), (7, "103"),
    (9, "111"), (10, "110"), (11, "112"),
    (13, "113"), (14, "114"), (15, "115"),
]

STATION_NAMES = {"BRICK", "PLANE", "BARN", "EAST END", "PRINCESS"}
SKIP_LABELS = {
    "HART RAILROAD", "NEVILLE ISLAND OPERATIONS", "P&CV DIVISION",
    "CTC DIGICON", "DS-CTC  Rev A  Eff 2026-08-11",
}

SLASH = {"UPPERSLASH", "LOWERSLASH"}
BACKSLASH = {"UPPERBACKSLASH", "LOWERBACKSLASH"}

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


def turnout_urls(kind: str) -> dict[str, str]:
    swap = kind.startswith("swap:")
    if swap:
        kind = kind[5:]
    if kind.startswith("thin:"):
        base = THIN + kind[5:]
    else:
        base = U + kind
    urls = dict(
        closed=base + "-closed.gif",
        thrown=base + "-thrown.gif",
        unknown=base + "-unknown.gif",
        inconsistent=base + "-inconsistent.gif",
    )
    if swap:
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


def _cover_run(x0: int, x1: int, y: int, tracks: list) -> None:
    px0, px1 = ux(x0), ux(x1) + CELL_W
    x = px0
    by = bar_y(y) - 1
    while x < px1 - 4:
        remain = px1 - x
        if remain >= 78:
            tracks.append((x, by - 1, "line1.gif", 0))
            x += 78
        elif remain >= 38:
            tracks.append((x, by, "line050.gif", 0))
            x += 40
        else:
            tracks.append((x, by + 1, "line025.gif", 0))
            x += 22


def build_geometry(cells: dict) -> tuple[list, list, list, list]:
    turnouts = []
    tracks = []
    lamps = []
    texts = []

    plant_cells = set(PLANTS) | SKIP_RAIL_CELLS
    for xy, (name, kind, dy) in PLANTS.items():
        cx, cy = xy
        turnouts.append((name, ux(cx) - 4, bar_y(cy) + dy, kind))

    by_row: dict[int, list[int]] = {}
    for (x, y), cell in cells.items():
        if y < 5 or y > 12:
            continue
        kinds = set(cell["tracks"])
        if (x, y) not in plant_cells:
            if "HORIZONTAL" in kinds:
                by_row.setdefault(y, []).append(x)
        slash = kinds & SLASH
        back = kinds & BACKSLASH
        if slash and (x, y) not in PLANTS:
            tracks.append((ux(x) + 1, bar_y(y) - 6, "thin-45.gif", 1))
        if back and (x, y) not in PLANTS:
            tracks.append((ux(x) + 1, bar_y(y) - 6, "thin-45.gif", 0))

        # East bumper: named block on RIGHT and no neighbor.
        for edge, bname, _sensor in cell["blocks"]:
            if edge == "RIGHT" and (x + 1, y) not in cells and bname:
                tracks.append((ux(x) + CELL_W - 2, bar_y(y) - 4, "thin-end.gif", 0))

    for y, xs in by_row.items():
        xs = sorted(set(xs))
        start = prev = xs[0]
        for x in xs[1:]:
            if x != prev + 1:
                _cover_run(start, prev, y, tracks)
                start = x
            prev = x
        _cover_run(start, prev, y, tracks)

    seen_sensors = set()
    for (x, y), cell in cells.items():
        if y < 5 or y > 12:
            continue
        for _edge, bname, sensor in cell["blocks"]:
            if not sensor or sensor in seen_sensors:
                continue
            if bname and str(bname).startswith("OS "):
                continue
            seen_sensors.add(sensor)
            tip = bname or sensor
            lamps.append((sensor, ux(x) + 2, bar_y(y) - 8, tip))

    for row in OS_ROW:
        slot, sensor, tip = row[0], row[1], row[2]
        extra = row[3] if len(row) > 3 else 0
        lamps.append((sensor, slot * 65 + 34 + extra, OS_Y, tip))

    texts.append((415, 8, "HART RAILROAD - NEVILLE ISLAND", 16, dict(red=0, green=0, blue=0)))
    for (x, y), cell in cells.items():
        name = cell["name"]
        if not name or name in SKIP_LABELS:
            continue
        if name.endswith(", PA"):
            name = name[: -4]
        if name in STATION_NAMES:
            texts.append((ux(x), STATION_Y, name, 12, WHITE))
            continue
        texts.append((ux(x), bar_y(y) - 12, name, 8, CREAM))
    for slot, num in OS_NUMBERS:
        texts.append((slot * 65 + 37, OS_Y + 23, num, 8, WHITE))
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
    for name, x, y, kind in turnouts:
        parts.append(TURNOUT.format(name=name, x=x, y=y, **turnout_urls(kind)))
    for sensor, x, y, tip in lamps:
        parts.append(LAMP.format(sensor=sensor, x=x, y=y, tip=tip, u=U))
    for x, y, gif, rot in tracks:
        url = THIN if gif.startswith(("thin", "thick")) else U + "track/block/"
        parts.append(TRACK.format(x=x, y=y, gif=gif, rot=rot, url=url))
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
        r"\s*<positionablelabel\b[^>]*text=\"(?:BRICK|PLANE|BARN|EAST END|PRINCESS|1[01][0-9]|HART RAILROAD[^\"]*)\".*?</positionablelabel>",
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
        r'\1 x="40" y="40" height="780" width="1190"',
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

    W, H = 1190, 340
    img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 11)
        font_sm = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 8)
    except OSError:
        font = font_sm = ImageFont.load_default()

    def paste(path: Path, x: int, y: int, rot: int = 0) -> None:
        if not path.exists():
            return
        tile = Image.open(path).convert("RGBA")
        if rot:
            tile = tile.rotate(-90 * rot, expand=True)
        img.alpha_composite(tile, (x, y))

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
        draw.text((x, y), text, fill=rgb + (255,), font=font if size >= 12 else font_sm)

    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out)
    print("preview %s (%dx%d)" % (out, W, H))


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
