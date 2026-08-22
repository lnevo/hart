#!/usr/bin/env python3
"""Build HART Digicon CTC from JMRI Layout Editor geometry + connectivity.

Source of truth: jmri/layouts/hart/output/hart_prod.xml
  - every layoutturnout (xcen/ycen, type, A/B/C/D tip blocks via segments)
  - occupancy sensors on layoutblocks / cats/data/occupancy_bindings.csv

Digicon is schematic (CATS cannot import LE pixels), but plant order, crossover
parallels, yard ladders, and block names come from LE tip connectivity.

Writes the **operational Digicon** (full railroad). Does not overwrite Designer XML:

    python3 cats/scripts/build_hart_digicon_from_le.py --mqtt
    # -> cats/panels/HART_le_magnet.xml
    # -> cats/panels/HART_le.xml  (with --mqtt)

Gate 1 spine SoR (must stay honest):

    Main West ═══[ OS 100 ]═══ Brick-Plane (HORIZONTAL) ═══[ OS 102 ]═══ East Main Ext
                      ╲
                       OS 101

Optional Designer experiment (not ops SoR):

    python3 cats/scripts/wire_designer_ctc_rules.py --mqtt  # -> cats/panels/HART.xml

Mac launch:

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

WIDTH, HEIGHT = "1600", "620"
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


def build_board(*, shift: bool = True) -> None:
    """LE-derived Digicon schematic.

    shift=False leaves 0-based coords so callers (e.g. CTC builder) can extend
    the grid before the mandatory CATS 1-based shift.

    Tip blocks from hart_prod (segment TURNOUT_A/B/C/D):
      TOL3  A=Main West  B=OS100     C=Brick-Plane
      TOL38 A=OS101      B=W-1 C=W-2
      TOL42 A=100-102    B=East Main Ext C=Scale
      TO117 A=Scale    B=Barn   C=Main East  D=East Main Ext
      TO111 A=Main West  B=West Main Ext C=OS110  D=S-1
      TO113 A=West Main Ext B=OS113b C=OS113a D=East Lead
      TOL23 A=East Lead  B=OS110     C=Main East
      … S-103–106 / East End 107–110 / Princess 114–115
    """
    GRID.clear()
    PLANTS.clear()
    ANCHORS.clear()
    ANON.clear()
    LABELS.clear()

    # =====================================================================
    # Y=1 UPPER PARALLEL: 111 — WME — 113b — 115 — Rocks
    # (Main West lives on the Gate‑1 spine below — not duplicated here.)
    # =====================================================================
    H((7, 1))
    nm((7, 1), "LEFT", "OS 111a")
    plant((8, 1), ["HORIZONTAL", "UPPERSLASH"], "OS 111a", "RIGHT", "TO111")
    nm((8, 1), "RIGHT", "OS 111a")
    H((8, 0))
    nm((8, 0), "LEFT", "OS 111b")
    cut((8, 1), "TOP", (8, 0), "BOTTOM")
    for x in range(9, 13):
        H((x, 1))
    nm((9, 1), "LEFT", "West Main Ext")
    cut((12, 1), "RIGHT", (13, 1), "LEFT")
    for x in range(13, 16):
        H((x, 1))
    nm((13, 1), "LEFT", "OS 113b")
    GRID[(16, 1)] = ["LOWERBACKSLASH"]
    cut((15, 1), "RIGHT", (16, 1), "LEFT")
    H((17, 1))
    plant((18, 1), ["HORIZONTAL", "UPPERSLASH"], "OS 115", "RIGHT", "TOL29")
    an((18, 1), "RIGHT")

    # =====================================================================
    # Y=2 MAIN SPINE (Gate 1 SoR):
    #   Main West ═══[ OS 100 ]═══ Brick-Plane ═══[ OS 102 ]═══ East Main Ext
    #                     ╲
    #                      OS 101 (yard diverge)
    # =====================================================================
    # Throat: Main West into Brick (continuing = east HORIZONTAL into 100-102)
    H((0, 2))
    H((1, 2))
    nm((0, 2), "LEFT", "Main West")
    cut((1, 2), "RIGHT", (2, 2), "LEFT")

    # OS 100 — H+LOWERBACKSLASH: points LEFT, normal RIGHT (100-102), diverge BOTTOM (OS 101)
    H((2, 2))
    nm((2, 2), "LEFT", "OS 100")
    plant((3, 2), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 100", "RIGHT", "TOL3")
    cut((3, 2), "RIGHT", (4, 2), "LEFT")

    # Long continuing mid-spine (must stay HORIZONTAL — not a plant approach slash)
    for x in range(4, 7):
        H((x, 2))
    nm((4, 2), "LEFT", "Brick-Plane")
    cut((6, 2), "RIGHT", (7, 2), "LEFT")

    # OS 102 Plane — continuing east to EME; diverge down to Scale
    H((7, 2))
    nm((7, 2), "LEFT", "OS 102")
    plant((8, 2), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 102", "RIGHT", "TOL42")
    cut((8, 2), "RIGHT", (9, 2), "LEFT")
    H((8, 3))
    nm((8, 3), "LEFT", "Scale")
    cut((8, 2), "BOTTOM", (8, 3), "TOP")

    for x in range(9, 11):
        H((x, 2))
    nm((9, 2), "LEFT", "East Main Ext")

    # OS 101 diverge under Brick + W-1/2 bodies (TOL38)
    H((3, 3))
    nm((3, 3), "LEFT", "OS 101")
    cut((3, 2), "BOTTOM", (3, 3), "TOP")
    H((2, 3))
    nm((2, 3), "LEFT", "W-2")
    cut((2, 3), "RIGHT", (3, 3), "LEFT")
    H((4, 3))
    nm((4, 3), "LEFT", "W-1")
    cut((3, 3), "RIGHT", (4, 3), "LEFT")

    # TO117: spine uses D=EME / C=Main East as 117b; AB = T1/T6 as 117
    plant((11, 2), ["HORIZONTAL", "UPPERBACKSLASH"], "OS 117b", "LEFT", "TO117")
    cut((10, 2), "RIGHT", (11, 2), "LEFT")
    nm((11, 2), "LEFT", "OS 117b")
    H((11, 3))
    nm((11, 3), "LEFT", "OS 117")
    cut((11, 2), "TOP", (11, 3), "BOTTOM")
    H((10, 3))
    nm((10, 3), "LEFT", "Barn")
    cut((10, 3), "RIGHT", (11, 3), "LEFT")
    # Gap between Scale (8,3) and T6 (10,3) — separate named regions

    H((12, 2))
    H((13, 2))
    cut((12, 2), "RIGHT", (13, 2), "LEFT")
    nm((13, 2), "LEFT", "Main East")
    cut((13, 2), "RIGHT", (14, 2), "LEFT")

    # OS 112
    H((14, 2))
    nm((14, 2), "LEFT", "OS 112")
    plant((15, 2), ["HORIZONTAL", "UPPERSLASH"], "OS 112", "RIGHT", "TOL23")
    nm((15, 2), "RIGHT", "OS 112")

    H((16, 2))
    nm((16, 2), "LEFT", "East Lead")

    # TO113 lower plants
    plant((18, 2), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 113a", "RIGHT", "TO113")
    plant((19, 2), ["HORIZONTAL", "UPPERBACKSLASH"], "OS 113a", "LEFT", "TO113")
    plant((20, 2), ["HORIZONTAL", "LOWERSLASH"], "OS 113a", "LEFT", "TO113")
    nm((20, 2), "BOTTOM", "OS 113a")
    cut((16, 1), "BOTTOM", (19, 2), "TOP")

    # OS 114 + loops
    H((22, 2))
    nm((22, 2), "LEFT", "OS 114")
    plant((23, 2), ["HORIZONTAL", "UPPERSLASH"], "OS 114", "RIGHT", "TOR36")
    nm((23, 2), "RIGHT", "OS 114")
    H((24, 2))
    H((25, 2))
    nm((24, 2), "LEFT", "McKeesport")
    GRID[(25, 1)] = ["LOWERBACKSLASH"]
    nm((25, 1), "LEFT", "McKees Rocks")
    cut((25, 1), "BOTTOM", (25, 2), "TOP")
    cut((24, 2), "RIGHT", (25, 2), "LEFT")
    nm((25, 2), "LEFT", "McKeesport")

    # =====================================================================
    # Y=4 West Yard ladder — contiguous approach+plant pairs (SP never faces BLK)
    # =====================================================================
    H((5, 4))
    nm((5, 4), "LEFT", "OS 119")
    plant((6, 4), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 119", "RIGHT", "TO10")
    cut((6, 4), "RIGHT", (7, 4), "LEFT")
    H((6, 5))
    nm((6, 5), "LEFT", "EH-3")
    cut((6, 4), "BOTTOM", (6, 5), "TOP")

    H((7, 4))
    nm((7, 4), "LEFT", "OS 118")
    plant((8, 4), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 118", "RIGHT", "TO11")
    cut((8, 4), "RIGHT", (9, 4), "LEFT")
    H((8, 5))
    nm((8, 5), "LEFT", "EH-2")
    cut((8, 4), "BOTTOM", (8, 5), "TOP")

    H((9, 4))
    nm((9, 4), "LEFT", "OS 116")
    plant((10, 4), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 116", "RIGHT", "TO1")
    an((10, 4), "RIGHT")
    H((10, 5))
    nm((10, 5), "LEFT", "EH-1")
    cut((10, 4), "BOTTOM", (10, 5), "TOP")

    # =====================================================================
    # South Yard ladder 103–106 — contiguous approach+plant
    # =====================================================================
    H((14, 3))
    nm((14, 3), "LEFT", "OS 103")
    plant((15, 3), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 103", "RIGHT", "TOR14")
    cut((15, 3), "RIGHT", (16, 3), "LEFT")
    H((15, 4))
    nm((15, 4), "LEFT", "S-1")
    cut((15, 3), "BOTTOM", (15, 4), "TOP")

    H((16, 3))
    nm((16, 3), "LEFT", "OS 104")
    plant((17, 3), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 104", "RIGHT", "TOL15")
    cut((17, 3), "RIGHT", (18, 3), "LEFT")
    H((17, 4))
    nm((17, 4), "LEFT", "S-2")
    cut((17, 3), "BOTTOM", (17, 4), "TOP")

    H((18, 3))
    nm((18, 3), "LEFT", "OS 105")
    plant((19, 3), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 105", "RIGHT", "TOL17")
    cut((19, 3), "RIGHT", (20, 3), "LEFT")
    H((19, 4))
    nm((19, 4), "LEFT", "S-3")
    cut((19, 3), "BOTTOM", (19, 4), "TOP")

    H((20, 3))
    nm((20, 3), "LEFT", "OS 106")
    plant((21, 3), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 106", "RIGHT", "TOL19")
    an((21, 3), "RIGHT")
    H((21, 4))
    nm((21, 4), "LEFT", "S-4")
    cut((21, 3), "BOTTOM", (21, 4), "TOP")
    H((22, 4))
    nm((22, 4), "LEFT", "S-5")
    cut((21, 4), "RIGHT", (22, 4), "LEFT")

    # =====================================================================
    # East End ladder 107–110 — contiguous approach+plant
    # =====================================================================
    H((24, 3))
    nm((24, 3), "LEFT", "OS 107")
    plant((25, 3), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 107", "RIGHT", "TOR11")
    cut((25, 3), "RIGHT", (26, 3), "LEFT")

    H((26, 3))
    nm((26, 3), "LEFT", "OS 108")
    plant((27, 3), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 108", "RIGHT", "TOR9")
    cut((27, 3), "RIGHT", (28, 3), "LEFT")

    H((28, 3))
    nm((28, 3), "LEFT", "OS 109")
    plant((29, 3), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 109", "RIGHT", "TOR7")
    cut((29, 3), "RIGHT", (30, 3), "LEFT")

    H((30, 3))
    nm((30, 3), "LEFT", "OS 110")
    plant((31, 3), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 110", "RIGHT", "TOL6")
    an((31, 3), "RIGHT")

    # --- rim / join fixes ---
    ANON.discard(((15, 1), "RIGHT"))
    ANON.discard(((16, 1), "LEFT"))
    nm((17, 1), "LEFT", "OS 115")
    for xy in list(GRID):
        if xy[1] not in (3, 4, 5):
            continue
        if (xy, "LEFT") in ANCHORS or xy in PLANTS:
            continue
        if any((xy, e) in ANON for e in ("LEFT", "RIGHT", "TOP", "BOTTOM")):
            continue
        GRID.pop(xy, None)
        for e in ("LEFT", "RIGHT", "TOP", "BOTTOM"):
            ANON.discard((xy, e))

    LABELS[:] = [
        (1, 0, "Main West → Brick"),
        (4, 0, "100-102"),
        (7, 0, "Plane / EME"),
        (8, 0, "111 / WME"),
        (11, 0, "117"),
        (13, 0, "Main East"),
        (18, 0, "Princess / Loops"),
        (6, 6, "West Yard"),
        (15, 5, "South Yard"),
        (26, 5, "East End"),
    ]

    # CATS grids are 1-based (Armstrong min X=1, Y=1). Column/row 0 → col<=0 NPE
    # on load. Shift BOTH axes by +1 so the whole plant starts at (1,1).
    # SHIFT_XY_TO_1
    if shift:
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
