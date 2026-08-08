#!/usr/bin/env python3
"""Build HART Digicon CTC from JMRI Layout Editor geometry + connectivity.

Source of truth: jmri/layouts/hart/output/hart_prod.xml
  - every layoutturnout (xcen/ycen, type, A/B/C/D tip blocks via segments)
  - occupancy sensors on layoutblocks / cats/data/occupancy_bindings.csv

Digicon is schematic (CATS cannot import LE pixels), but plant order, crossover
parallels, yard ladders, and block names come from LE tip connectivity.

Writes Gate 2–5 WIP panels (does NOT overwrite Designer Gate 1 primary):

    python3 cats/scripts/build_hart_digicon_from_le.py --mqtt
    # -> cats/panels/HART_le_magnet.xml
    # -> cats/panels/HART_le.xml  (with --mqtt)

Primary Designer Gate 1 remains:

    python3 cats/scripts/wire_designer_ctc_rules.py --mqtt
    # -> cats/panels/HART.xml

Mac launch (WIP LE board):

    CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh cats/panels/HART_le.xml
"""

from __future__ import annotations

import argparse
import copy
import csv
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HART = ROOT / "jmri/layouts/hart/output/hart_prod.xml"
OUT_DIR = ROOT / "cats/panels"
OCC_CSV = ROOT / "cats/data/occupancy_bindings.csv"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cats_paths import armstrong_magnet  # noqa: E402

ARM = armstrong_magnet()

WIDTH, HEIGHT = "1400", "520"
COMPRESSION_OFF_TAG = "COMPRESSIONTAG"

TRACK_ENDS = {
    "HORIZONTAL": frozenset({"LEFT", "RIGHT"}),
    "VERTICAL": frozenset({"TOP", "BOTTOM"}),
    "UPPERSLASH": frozenset({"LEFT", "TOP"}),
    "LOWERSLASH": frozenset({"RIGHT", "BOTTOM"}),
    "UPPERBACKSLASH": frozenset({"RIGHT", "TOP"}),
    "LOWERBACKSLASH": frozenset({"LEFT", "BOTTOM"}),
}
OPPOSITE = {"LEFT": "RIGHT", "RIGHT": "LEFT", "TOP": "BOTTOM", "BOTTOM": "TOP"}
STEP = {"LEFT": (-1, 0), "RIGHT": (1, 0), "TOP": (0, -1), "BOTTOM": (0, 1)}
Cell = tuple[int, int]

GRID: dict[Cell, list[str]] = {}
PLANTS: dict[Cell, tuple[str, str, str]] = {}  # os, normal_edge, layout_ident
ANCHORS: dict[tuple[Cell, str], str] = {}
ANON: set[tuple[Cell, str]] = set()
LABELS: list[tuple[int, int, str]] = []


def H(xy: Cell) -> None:
    GRID[xy] = ["HORIZONTAL"]


def plant(xy: Cell, tracks: list[str], os_name: str, normal: str, ident: str) -> None:
    GRID[xy] = list(tracks)
    PLANTS[xy] = (os_name, normal, ident)


def nm(xy: Cell, edge: str, block: str) -> None:
    ANCHORS[(xy, edge)] = block


def an(xy: Cell, edge: str) -> None:
    ANON.add((xy, edge))


def cut(a: Cell, ae: str, b: Cell, be: str) -> None:
    """BLK boundary between two cells (both edges)."""
    an(a, ae)
    an(b, be)


def build_board() -> None:
    """LE-derived Digicon schematic.

    Tip blocks from hart_prod (segment TURNOUT_A/B/C/D):
      TOL3  A=Main West  B=OS100     C=Block 100-102
      TOL38 A=OS101      B=West Yard 1 C=West Yard 2
      TOL42 A=100-102    B=East Main Ext C=Yard T1
      TO117 A=Yard T1    B=Yard T6   C=Main East  D=East Main Ext
      TO111 A=Main West  B=West Main Ext C=OS110  D=Yard Track 1
      TO113 A=West Main Ext B=OS113b C=OS113a D=East Lead
      TOL23 A=East Lead  B=OS110     C=Main East
      … South Yard 103–106 / East End 107–110 / Princess 114–115
    """
    GRID.clear()
    PLANTS.clear()
    ANCHORS.clear()
    ANON.clear()
    LABELS.clear()

    # =====================================================================
    # Y=1 UPPER PARALLEL (LE y≈252): Main West — 111 — WME — 113b — 115 — Rocks
    # =====================================================================
    # Main West — cut — OS111a approach+plant — cut — West Main Ext
    for x in range(0, 7):
        H((x, 1))
    nm((0, 1), "LEFT", "Main West")
    cut((6, 1), "RIGHT", (7, 1), "LEFT")
    H((7, 1))
    nm((7, 1), "LEFT", "OS 111a (East End)")
    plant((8, 1), ["HORIZONTAL", "UPPERSLASH"], "OS 111a (East End)", "RIGHT", "TO111")
    # (7,1) plain into SP; cut frog to WME; TOP = 111b (LE CD / skip_switches mate)
    nm((8, 1), "RIGHT", "OS 111a (East End)")
    H((8, 0))
    nm((8, 0), "LEFT", "OS 111b (East End)")
    cut((8, 1), "TOP", (8, 0), "BOTTOM")
    for x in range(9, 13):
        H((x, 1))
    nm((9, 1), "LEFT", "West Main Ext")
    cut((12, 1), "RIGHT", (13, 1), "LEFT")
    for x in range(13, 16):
        H((x, 1))
    nm((13, 1), "LEFT", "OS 113b (Princess)")
    # drop into lower 113 plants at (16,2) via LB
    GRID[(16, 1)] = ["LOWERBACKSLASH"]
    cut((15, 1), "RIGHT", (16, 1), "LEFT")
    # OS 115 (LE C=McKees Rocks)
    H((17, 1))
    plant((18, 1), ["HORIZONTAL", "UPPERSLASH"], "OS 115 (Princess)", "RIGHT", "TOL29")
    # (17,1) plain into SP; 115 owns through plant; cut to Rocks
    an((18, 1), "RIGHT")
    # McKees Rocks / loop corner placed later at (24,1) next to McKeesport

    # =====================================================================
    # Y=2 MAIN SPINE: Brick — 100-102 — Plane — EME — 117b — ME — 112 — EL — 113 — 114 — MKP
    # =====================================================================
    # OS 101 (TOL38): A=OS101 B=WY1 C=WY2 — Digicon plant, normal east to OS100
    H((0, 2))
    plant((1, 2), ["HORIZONTAL", "UPPERSLASH"], "OS 101 (Brick)", "RIGHT", "TOL38")
    nm((0, 2), "LEFT", "OS 101 (Brick)")  # owns (0,2)+(1,2) through SP
    an((1, 2), "RIGHT")
    # WY1 / WY2 stubs under/over
    H((0, 3))
    nm((0, 3), "LEFT", "West Yard 2")
    an((0, 3), "RIGHT")
    H((1, 3))
    nm((1, 3), "LEFT", "West Yard 1")
    cut((1, 2), "TOP", (1, 3), "BOTTOM")  # diverge visual (US has TOP)

    # OS 100 (TOL3): continuing Digicon = C = 100-102
    H((2, 2))
    nm((2, 2), "LEFT", "OS 100 (Brick)")
    plant((3, 2), ["HORIZONTAL", "UPPERSLASH"], "OS 100 (Brick)", "RIGHT", "TOL3")
    # (2,2) through SP; cut to 100-102; TOP into Main West at (3,1)
    an((3, 2), "RIGHT")
    cut((3, 2), "TOP", (3, 1), "BOTTOM")

    for x in range(4, 6):
        H((x, 2))
    nm((4, 2), "LEFT", "Block 100-102")
    cut((5, 2), "RIGHT", (6, 2), "LEFT")

    # OS 102 Plane: approach + plant; B=EME C=Yard T1
    H((6, 2))
    nm((6, 2), "LEFT", "OS 102 (Plane)")
    plant((7, 2), ["HORIZONTAL", "UPPERSLASH"], "OS 102 (Plane)", "RIGHT", "TOL42")
    nm((7, 2), "RIGHT", "OS 102 (Plane)")
    H((7, 3))
    nm((7, 3), "LEFT", "Yard T1")
    cut((7, 2), "TOP", (7, 3), "BOTTOM")

    for x in range(8, 10):
        H((x, 2))
    nm((8, 2), "LEFT", "East Main Ext")

    # TO117: spine uses D=EME / C=Main East as 117b; AB = T1/T6 as 117
    plant((10, 2), ["HORIZONTAL", "UPPERBACKSLASH"], "OS 117b (West Yard)", "LEFT", "TO117")
    # SP RIGHT; cut west on LEFT
    cut((9, 2), "RIGHT", (10, 2), "LEFT")
    nm((10, 2), "LEFT", "OS 117b (West Yard)")
    H((10, 3))
    nm((10, 3), "LEFT", "OS 117 (West Yard)")
    cut((10, 2), "TOP", (10, 3), "BOTTOM")
    H((9, 3))
    nm((9, 3), "LEFT", "Yard T6")
    cut((9, 3), "RIGHT", (10, 3), "LEFT")

    H((11, 2))
    H((12, 2))
    # through SP into (11,2); cut to Main East
    cut((11, 2), "RIGHT", (12, 2), "LEFT")
    nm((12, 2), "LEFT", "Main East")
    cut((12, 2), "RIGHT", (13, 2), "LEFT")

    # OS 112: approach + plant; A=East Lead C=Main East
    H((13, 2))
    nm((13, 2), "LEFT", "OS 112 (East End)")
    plant((14, 2), ["HORIZONTAL", "UPPERSLASH"], "OS 112 (East End)", "RIGHT", "TOL23")
    nm((14, 2), "RIGHT", "OS 112 (East End)")

    H((15, 2))
    nm((15, 2), "LEFT", "East Lead")
    # gap x=16 so EL does not face 113 SP LEFT

    # TO113 lower plants at x=17+
    plant((17, 2), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 113a (Princess)", "RIGHT", "TO113")
    plant((18, 2), ["HORIZONTAL", "UPPERBACKSLASH"], "OS 113a (Princess)", "LEFT", "TO113")
    plant((19, 2), ["HORIZONTAL", "LOWERSLASH"], "OS 113a (Princess)", "LEFT", "TO113")
    # one region through all three plants; name on BOTTOM rim (non-neighbor)
    nm((19, 2), "BOTTOM", "OS 113a (Princess)")
    cut((16, 1), "BOTTOM", (18, 2), "TOP")

    # OS 114 — gap after 113 SP RIGHT (x=19 plant)
    H((21, 2))
    nm((21, 2), "LEFT", "OS 114 (Princess)")
    plant((22, 2), ["HORIZONTAL", "UPPERSLASH"], "OS 114 (Princess)", "RIGHT", "TOR36")
    nm((22, 2), "RIGHT", "OS 114 (Princess)")
    H((23, 2))
    H((24, 2))
    nm((23, 2), "LEFT", "McKeesport")
    GRID[(24, 1)] = ["LOWERBACKSLASH"]
    ANON.discard(((21, 1), "RIGHT"))
    nm((24, 1), "LEFT", "McKees Rocks")
    cut((24, 1), "BOTTOM", (24, 2), "TOP")
    cut((23, 2), "RIGHT", (24, 2), "LEFT")
    nm((24, 2), "LEFT", "McKeesport")

    # =====================================================================
    # Y=3/4 West Yard 116–119 + South Yard 103–106 + East End 107–110 + YT
    # =====================================================================
    # West Yard ladder: T11/T10/T9 stubs + OS119/118/116 (column gaps at throats)
    H((2, 3))
    nm((2, 3), "LEFT", "Yard T11")
    cut((2, 3), "RIGHT", (3, 3), "LEFT")
    H((3, 3))
    nm((3, 3), "LEFT", "Yard T10")
    cut((3, 3), "RIGHT", (4, 3), "LEFT")
    H((4, 3))
    nm((4, 3), "LEFT", "Yard T9")
    cut((4, 3), "RIGHT", (5, 3), "LEFT")
    H((5, 3))
    nm((5, 3), "LEFT", "OS 119 (West Yard)")
    plant((6, 3), ["HORIZONTAL", "UPPERSLASH"], "OS 119 (West Yard)", "RIGHT", "TO10")
    nm((6, 3), "RIGHT", "OS 119 (West Yard)")
    # gap x=7 then OS118
    H((8, 3))
    nm((8, 3), "LEFT", "OS 118 (West Yard)")
    plant((9, 3), ["HORIZONTAL", "UPPERSLASH"], "OS 118 (West Yard)", "RIGHT", "TO11")
    nm((9, 3), "RIGHT", "OS 118 (West Yard)")
    # gap then OS116; Yard T1 under Plane; T6/117 shift east if needed
    H((7, 4))
    nm((7, 4), "LEFT", "Yard T1")
    cut((7, 2), "TOP", (7, 4), "BOTTOM")
    H((11, 3))
    nm((11, 3), "LEFT", "OS 116 (West Yard)")
    plant((12, 3), ["HORIZONTAL", "UPPERSLASH"], "OS 116 (West Yard)", "RIGHT", "TO1")
    nm((12, 3), "RIGHT", "OS 116 (West Yard)")
    # T6 + OS117 under 117b plant
    H((10, 4))
    nm((10, 4), "LEFT", "Yard T6")
    H((11, 4))
    nm((11, 4), "LEFT", "OS 117 (West Yard)")
    cut((10, 2), "TOP", (10, 4), "BOTTOM")
    cut((10, 4), "RIGHT", (11, 4), "LEFT")
    # clear earlier (9,3)/(10,3) T6/117 if left from main-spine block
    for xy in ((9, 3), (10, 3)):
        if xy in GRID and xy not in PLANTS:
            GRID.pop(xy, None)
            for e in ("LEFT", "RIGHT", "TOP", "BOTTOM"):
                ANCHORS.pop((xy, e), None)
                ANON.discard((xy, e))
    ANON.discard(((10, 2), "TOP"))
    cut((10, 2), "TOP", (10, 4), "BOTTOM")

    # South Yard ladder 103–106 east of OS116 (gap at x=13)
    H((14, 3))
    nm((14, 3), "LEFT", "OS 103 (South Yard)")
    plant((15, 3), ["HORIZONTAL", "LOWERSLASH"], "OS 103 (South Yard)", "LEFT", "TOR14")

    H((17, 3))
    nm((17, 3), "LEFT", "OS 104 (South Yard)")
    plant((18, 3), ["HORIZONTAL", "LOWERSLASH"], "OS 104 (South Yard)", "LEFT", "TOL15")

    H((20, 3))
    nm((20, 3), "LEFT", "OS 105 (South Yard)")
    plant((21, 3), ["HORIZONTAL", "LOWERSLASH"], "OS 105 (South Yard)", "LEFT", "TOL17")

    H((23, 3))
    nm((23, 3), "LEFT", "OS 106 (South Yard)")
    plant((24, 3), ["HORIZONTAL", "LOWERSLASH"], "OS 106 (South Yard)", "LEFT", "TOL19")

    # East End ladder 107–110 (gaps between OS)
    H((26, 3))
    nm((26, 3), "LEFT", "OS 107 (East End)")
    plant((27, 3), ["HORIZONTAL", "LOWERSLASH"], "OS 107 (East End)", "LEFT", "TOR11")

    H((29, 3))
    nm((29, 3), "LEFT", "OS 108 (East End)")
    plant((30, 3), ["HORIZONTAL", "LOWERSLASH"], "OS 108 (East End)", "LEFT", "TOR9")

    H((32, 3))
    nm((32, 3), "LEFT", "OS 109 (East End)")
    plant((33, 3), ["HORIZONTAL", "LOWERSLASH"], "OS 109 (East End)", "LEFT", "TOR7")

    H((35, 3))
    nm((35, 3), "LEFT", "OS 110 (East End)")
    plant((36, 3), ["HORIZONTAL", "LOWERSLASH"], "OS 110 (East End)", "LEFT", "TOL6")

    # Yard Tracks 1–5 under South Yard
    for i, blk in enumerate(
        ["Yard Track 1", "Yard Track 2", "Yard Track 3", "Yard Track 4", "Yard Track 5"]
    ):
        x = 15 + i * 2
        H((x, 4))
        nm((x, 4), "LEFT", blk)
    for p, yx in [((15, 3), (15, 4)), ((18, 3), (17, 4)), ((21, 3), (19, 4)), ((24, 3), (21, 4))]:
        if p in GRID and yx in GRID:
            cut(p, "BOTTOM", yx, "TOP")
    # align YT under plants
    for p, yx in [((15, 3), (15, 4)), ((18, 3), (18, 4)), ((21, 3), (21, 4)), ((24, 3), (23, 4))]:
        if yx not in GRID:
            H(yx)
            # keep name if already set on alternate
        if p in GRID and yx in GRID:
            cut(p, "BOTTOM", yx, "TOP")

    # OS 111b / 113a already represented; 117b/117 done.
    # West Yard 1 cut from 101 already.

    # --- rim / join fixes ---
    an((1, 3), "RIGHT")
    if (7, 3) in GRID and (7, 3) not in PLANTS:
        GRID.pop((7, 3), None)
        for e in ("LEFT", "RIGHT", "TOP", "BOTTOM"):
            ANCHORS.pop(((7, 3), e), None)
            ANON.discard(((7, 3), e))
    ANON.discard(((15, 1), "RIGHT"))
    ANON.discard(((16, 1), "LEFT"))
    nm((17, 1), "LEFT", "OS 115 (Princess)")
    # Remove stale upper-loop cells from earlier Rocks corridor (19-22,1)
    for x in range(19, 23):
        xy = (x, 1)
        if xy in GRID and (xy, "LEFT") not in ANCHORS and xy not in PLANTS:
            # keep if part of 115/Rocks named region
            pass
    # Drop unnamed Y=4 orphans
    for xy in list(GRID):
        if xy[1] != 4:
            continue
        if (xy, "LEFT") in ANCHORS or xy in PLANTS:
            continue
        # allow cells that only have TOP anon into a plant
        GRID.pop(xy, None)
        for e in ("LEFT", "RIGHT", "TOP", "BOTTOM"):
            ANON.discard((xy, e))


    # Labels use pre-shift coords; shift everything to Armstrong-style Y>=1 last.
    LABELS[:] = [
        (2, 0, "Brick / Main West"),
        (6, 0, "Plane / EME"),
        (10, 0, "117"),
        (12, 0, "Main East"),
        (8, 0, "111 / WME"),
        (15, 0, "113 / Princess"),
        (20, 0, "Loops"),
        (14, 5, "South Yard"),
        (23, 5, "East End 107-110"),
        (4, 4, "West Yard ladder"),
    ]

    # CATS grids are 1-based (Armstrong min X=1, Y=1). Column/row 0 → col<=0 NPE
    # on load. Shift BOTH axes by +1 so the whole plant starts at (1,1).
    # SHIFT_XY_TO_1
    _g = {(x + 1, y + 1): v for (x, y), v in GRID.items()}
    _p = {(x + 1, y + 1): v for (x, y), v in PLANTS.items()}
    _a = {((x + 1, y + 1), e): n for ((x, y), e), n in ANCHORS.items()}
    _n = {((x + 1, y + 1), e) for (x, y), e in ANON}
    _l = [(x + 1, y + 1, t) for x, y, t in LABELS]
    GRID.clear(); GRID.update(_g)
    PLANTS.clear(); PLANTS.update(_p)
    ANCHORS.clear(); ANCHORS.update(_a)
    ANON.clear(); ANON.update(_n)
    LABELS.clear(); LABELS.extend(_l)


def points_edge(tracks: list[str]) -> str | None:
    if len(tracks) != 2:
        return None
    shared = TRACK_ENDS[tracks[0]] & TRACK_ENDS[tracks[1]]
    return next(iter(shared)) if len(shared) == 1 else None


def cell_edges(tracks: list[str]) -> list[str]:
    used: set[str] = set()
    for t in tracks:
        used |= TRACK_ENDS[t]
    return [e for e in ("LEFT", "RIGHT", "TOP", "BOTTOM") if e in used]


def make_section(x: int, y: int, tracks: list[str]) -> ET.Element:
    sec = ET.Element("SECTION", {"X": str(x), "Y": str(y)})
    tg = ET.SubElement(sec, "TRACKGROUP")
    for t in tracks:
        ET.SubElement(tg, "TRACK").text = t
    return sec


def load_disciplines() -> dict[str, str]:
    out: dict[str, str] = {}
    with OCC_CSV.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            disc = (row.get("cats_discipline") or "CTC").strip().upper()
            if disc not in {"UNDEFINED", "ABS", "APB", "CTC", "DTC"}:
                disc = "CTC"
            out[row["block_user_name"].strip()] = disc
    return out


def load_occupancy() -> dict[str, tuple[str, str]]:
    root = ET.parse(HART).getroot()
    sensor_addr: dict[str, str] = {}
    for s in root.iter("sensor"):
        sn = s.get("systemName") or s.findtext("systemName") or ""
        un = (s.findtext("userName") or "").strip()
        if sn.startswith("M2S") and un:
            sensor_addr[un] = sn[3:]
    out: dict[str, tuple[str, str]] = {}
    for lb in root.iter("layoutblock"):
        un = (lb.findtext("userName") or "").strip()
        occ = (lb.get("occupancysensor") or "").strip()
        if un and occ and occ in sensor_addr:
            out[un] = (sensor_addr[occ], occ)
    with OCC_CSV.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            name = row["block_user_name"].strip()
            sens = row["occupancy_sensor_user_name"].strip()
            if name not in out and sens in sensor_addr:
                out[name] = (sensor_addr[sens], sens)
    return out


def wire(tp: ET.Element, disc: dict[str, str]) -> None:
    secs = {(int(s.get("X")), int(s.get("Y"))): s for s in tp.findall("SECTION")}
    for xy, sec in secs.items():
        tracks = GRID[xy]
        pts = points_edge(tracks)
        for edge in cell_edges(tracks):
            se = ET.SubElement(sec, "SEC_EDGE", {"EDGE": edge})
            if edge == pts:
                _os, normal, _id = PLANTS.get(xy, ("", "", ""))
                legs = [e for e in cell_edges(tracks) if e != pts]
                if normal not in legs:
                    normal = legs[0]
                sp = ET.SubElement(se, "SWITCHPOINTS")
                for leg in legs:
                    attrs = {"ROUTEID": leg}
                    if leg == normal:
                        attrs["NORMAL"] = "true"
                    ET.SubElement(sp, "ROUTEINFO", attrs)
                continue
            key = (xy, edge)
            if key in ANCHORS:
                bname = ANCHORS[key]
                ET.SubElement(
                    se,
                    "BLOCK",
                    {
                        "NAME": bname,
                        "STATION": bname,
                        "DISCIPLINE": disc.get(bname, "CTC"),
                        "VISIBLE": "true",
                    },
                )
            elif key in ANON:
                ET.SubElement(se, "BLOCK")
    occupied = set(secs)
    for x, y, text in LABELS:
        if (x, y) in occupied:
            continue
        lab = ET.Element("SECTION", {"X": str(x), "Y": str(y)})
        ET.SubElement(
            lab,
            "SEC_NAME",
            {"LOC_NAME": "CENT", "NAME": text, "FONT_NAME": "FONT_LABEL"},
        )
        tp.append(lab)
        occupied.add((x, y))


def regions_of(tp: ET.Element) -> list[set[Cell]]:
    blocked: set[tuple[Cell, str]] = set()
    for s in tp.findall("SECTION"):
        if s.find("TRACKGROUP") is None:
            continue
        xy = (int(s.get("X")), int(s.get("Y")))
        for e in s.findall("SEC_EDGE"):
            if e.find("BLOCK") is not None:
                blocked.add((xy, e.get("EDGE")))
    seen: set[Cell] = set()
    out: list[set[Cell]] = []
    for start in GRID:
        if start in seen:
            continue
        comp = {start}
        stack = [start]
        seen.add(start)
        while stack:
            cur = stack.pop()
            for edge in cell_edges(GRID[cur]):
                if (cur, edge) in blocked:
                    continue
                dx, dy = STEP[edge]
                nb = (cur[0] + dx, cur[1] + dy)
                if nb not in GRID or nb in seen:
                    continue
                back = OPPOSITE[edge]
                if back not in cell_edges(GRID[nb]) or (nb, back) in blocked:
                    continue
                seen.add(nb)
                comp.add(nb)
                stack.append(nb)
        out.append(comp)
    return out


def verify(tp: ET.Element) -> list[str]:
    errs: list[str] = []
    secs = {(int(s.get("X")), int(s.get("Y"))): s for s in tp.findall("SECTION")}
    kind: dict[tuple[Cell, str], str] = {}
    for xy, s in secs.items():
        if s.find("TRACKGROUP") is None:
            continue
        for e in s.findall("SEC_EDGE"):
            ed = e.get("EDGE")
            has_b = e.find("BLOCK") is not None
            has_s = e.find("SWITCHPOINTS") is not None
            if has_b and has_s:
                errs.append(f"R2 {xy} {ed}")
            kind[(xy, ed)] = "SP" if has_s else ("BLK" if has_b else "plain")
    for (xy, ed), k in kind.items():
        dx, dy = STEP[ed]
        nb = (xy[0] + dx, xy[1] + dy)
        other = kind.get((nb, OPPOSITE[ed]))
        if other is None:
            continue
        if k == "SP" and other == "BLK":
            errs.append(f"R3 {xy} {ed} SP→BLK {nb}")
        if k == "BLK" and other != "BLK":
            errs.append(f"R4 {xy} {ed} BLK→{other} {nb}")
    named: dict[Cell, str] = {}
    for xy, s in secs.items():
        for e in s.findall("SEC_EDGE"):
            b = e.find("BLOCK")
            if b is not None and b.get("NAME"):
                named.setdefault(xy, b.get("NAME"))
    for comp in regions_of(tp):
        names = sorted({named[c] for c in comp if c in named})
        if not names:
            errs.append(f"R5 {sorted(comp)} unnamed")
        elif len(names) > 1:
            errs.append(f"R5 {sorted(comp)} {names}")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mqtt", action="store_true")
    args = ap.parse_args()

    build_board()

    # drop empty/orphan fixes: remove cells not in GRID that lost tracks
    root = ET.parse(ARM).getroot()
    for ops in root.iter("OPERATIONS"):
        ops.set("CONNECT", "false")
    for old in list(root.findall("TRACKPLAN")):
        root.remove(old)
    if root.find(COMPRESSION_OFF_TAG) is None:
        root.append(ET.Element(COMPRESSION_OFF_TAG))

    tp = ET.Element("TRACKPLAN")
    for (x, y), tracks in sorted(GRID.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        tp.append(make_section(x, y, tracks))
    cols = max(c[0] for c in GRID) + 2
    rows = max(c[1] for c in GRID) + 2
    tp.set("COLUMNS", str(cols))
    tp.set("ROWS", str(rows))
    wire(tp, load_disciplines())
    root.append(tp)
    root.set("WIDTH", WIDTH)
    root.set("HEIGHT", HEIGHT)

    errs = verify(tp)
    for e in errs:
        print(f"VERIFY FAIL: {e}", file=sys.stderr)
    if errs:
        return 1

    ET.indent(root, space="  ")
    magnet = OUT_DIR / "HART_le_magnet.xml"
    ET.ElementTree(root).write(magnet, encoding="UTF-8", xml_declaration=True)
    print(f"wrote {magnet.relative_to(ROOT)}")
    names = sorted({b.get("NAME") for b in root.iter("BLOCK") if b.get("NAME")})
    plants = sorted({f"{v[2]}:{v[0]}" for v in PLANTS.values()})
    print(f"grid {cols}x{rows} cells={len(GRID)} plants={len(PLANTS)}")
    print(f"named ({len(names)}): {', '.join(names)}")
    print(f"LE plants: {', '.join(plants)}")
    print(f"regions: {len(regions_of(tp))}")
    print("note: Designer Gate 1 primary remains cats/panels/HART.xml")

    want = {r["block_user_name"].strip() for r in csv.DictReader(OCC_CSV.open())}
    missing = sorted(want - set(names))
    if missing:
        print(f"NOT YET ON BOARD ({len(missing)}): {', '.join(missing)}")

    if args.mqtt:
        import jmri_to_cats_digicon as gen

        mqtt_root = copy.deepcopy(root)
        gen.ensure_mqtt(mqtt_root)
        gen.wire_occupancy(mqtt_root, load_occupancy())
        for ops in mqtt_root.iter("OPERATIONS"):
            ops.set("CONNECT", "true")
        gen.ensure_hart_trains(mqtt_root)
        ET.indent(mqtt_root, space="  ")
        out = OUT_DIR / "HART_le.xml"
        ET.ElementTree(mqtt_root).write(out, encoding="UTF-8", xml_declaration=True)
        n_occ = sum(
            1
            for b in mqtt_root.iter("BLOCK")
            if b.get("NAME") and b.find("OCCUPIEDSPEC") is not None
        )
        print(f"wrote {out.relative_to(ROOT)} MQTT {n_occ}/{len(names)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
