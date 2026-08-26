#!/usr/bin/env python3
"""Wire HART_Master4.xml geometry → HART_Master4_wired.xml.

Designer save is HART_Master4.xml. Live desks:

    python3 cats/scripts/wire_hart_master4.py --live

That copies the wired panel to HART_Master.xml / HART_Master_ABS.xml and
rebuilds the CATS CTC / CATS ABS HOLD copies.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_hart_digicon_from_le as le  # noqa: E402
import cats_turnout_io as tio  # noqa: E402
import jmri_to_cats_digicon as gen  # noqa: E402

SRC = ROOT / "cats/panels/HART_Master4.xml"
DST = ROOT / "cats/panels/HART_Master4_wired.xml"
LIVE_CTC = ROOT / "cats/panels/HART_Master.xml"
LIVE_ABS = ROOT / "cats/panels/HART_Master_ABS.xml"
LIVE_CTC_HOLD = ROOT / "cats/panels/HART_Master_CTC_hold.xml"
LIVE_ABS_HOLD = ROOT / "cats/panels/HART_Master_ABS_hold.xml"

# (x, y) → (OS name, NORMAL route among non-points legs, layout_ident)
# NORMAL is the drawn through / main. invert_vs_jmri plants put throw on
# that NORMAL route (JMRI Thrown = mainline): 100, 114, 115.
#
# Untwisted 63×16 board (Designer 2026-08-26).
# Y=6 Main West → West Main Ext → McKees Rocks (K-1 above).
# Y=7 Scale / Barn / S-1 / East Lead / McKeesport (K-2 below).
# Y=8 Brick 100 / Plane 102 / E Main Ext / EH / S-2.
# Y=12 Main East under the south-yard ladders.
# SHARED: (1,6) LEFT ↔ (1,8) LEFT Main West; (63,6) RIGHT ↔ (63,7) RIGHT McKeesport.
PLANTS: dict[tuple[int, int], tuple[str, str, str]] = {
    (4, 8): ("OS 100", "RIGHT", "TOL3"),  # Brick. Thrown = through E Main Ext; Closed BOTTOM = yard
    (5, 9): ("OS 101", "BOTTOM", "TOL38"),  # Closed = W-1 (BOTTOM); Thrown RIGHT = W-2
    (9, 8): ("OS 102", "RIGHT", "TOL42"),  # Closed = through E Main Ext; Thrown TOP = Scale
    (15, 8): ("OS 117b", "RIGHT", "TO117"),
    (15, 7): ("OS 117", "LEFT", "TO117"),
    (24, 8): ("OS 119", "LEFT", "TO10"),  # Closed LEFT = EH-1; Thrown BOTTOM = EH-2
    (26, 8): ("OS 118", "LEFT", "TO11"),  # Closed LEFT = from 119; Thrown BOTTOM = EH-3
    (27, 7): ("OS 116", "LEFT", "TO1"),  # Thrown BOTTOM is a stub; does not join 118
    (30, 7): ("OS 103", "RIGHT", "TOR14"),  # Thrown BOTTOM geographic into 104 approach
    (31, 8): ("OS 104", "BOTTOM", "TOL15"),
    (32, 9): ("OS 105", "BOTTOM", "TOL17"),
    (33, 10): ("OS 106", "BOTTOM", "TOL19"),
    (40, 6): ("OS 111a", "RIGHT", "TO111"),  # Main West
    (40, 7): ("OS 111b", "LEFT", "TO111"),  # S-1
    (42, 7): ("OS 110", "LEFT", "TOL6"),  # Closed LEFT = S-1/111; Thrown BOTTOM = 109
    (44, 7): ("OS 112", "LEFT", "TOL23"),  # Closed LEFT = 110; Thrown BOTTOM = Main East
    (41, 8): ("OS 109", "BOTTOM", "TOR7"),
    (40, 9): ("OS 108", "BOTTOM", "TOR9"),
    (39, 10): ("OS 107", "BOTTOM", "TOR11"),
    (52, 6): ("OS 113b", "LEFT", "TO113"),  # West Main Ext
    (52, 7): ("OS 113a", "RIGHT", "TO113"),  # East Lead
    (55, 6): ("OS 115", "RIGHT", "TOL29"),  # Thrown = McKees Rocks; Closed TOP = K-1
    (55, 7): ("OS 114", "RIGHT", "TOR36"),  # Thrown = McKeesport; Closed BOTTOM = K-2
}

# CATS NORMAL = drawn through. These three are JMRI Thrown when lined
# for that through route (Designer “differs from JMRI settings”).
# 112 is no longer inverted: LEFT is the 110/S-1 closed leg, BOTTOM is Main East.
INVERT_VS_JMRI = {"TOL3", "TOR36", "TOL29"}  # 100, 114, 115

# Do not add rails. Designer already drew every frog.
EXTRA_TRACKS: dict[tuple[int, int], str] = {}

# Named BLOCK only on Designer occupancy cuts (do not add/remove gaps).
ANCHORS: list[tuple[int, int, str, str]] = [
    # K-1 | OS 115
    (56, 5, "RIGHT", "OS 115"),  # 115LB
    (57, 5, "LEFT", "K-1"),
    # Main West west rim (Y=6) SHARED-joins west-of-Brick (Y=8) for N/X.
    (1, 6, "LEFT", "Main West"),
    (1, 8, "LEFT", "Main West"),
    (2, 8, "RIGHT", "Main West"),
    (3, 8, "LEFT", "OS 100"),  # 100L
    # Main West | OS 111a
    (38, 6, "RIGHT", "Main West"),
    (39, 6, "LEFT", "OS 111a"),  # 111RA
    (40, 6, "RIGHT", "OS 111a"),
    (41, 6, "LEFT", "West Main Ext"),
    (40, 6, "BOTTOM", "OS 111a"),
    (40, 7, "TOP", "OS 111b"),
    # 111L sits mid West Main Ext (same name both faces — lamp gap only).
    (45, 6, "RIGHT", "West Main Ext"),  # 111L
    (46, 6, "LEFT", "West Main Ext"),
    (50, 6, "RIGHT", "West Main Ext"),
    (51, 6, "LEFT", "OS 113b"),  # 113RA
    (52, 6, "BOTTOM", "OS 113b"),
    (52, 7, "TOP", "OS 113a"),
    (53, 6, "RIGHT", "OS 113b"),
    (54, 6, "LEFT", "OS 115"),
    (56, 6, "RIGHT", "OS 115"),  # 115LA
    (57, 6, "LEFT", "McKees Rocks"),
    (60, 6, "RIGHT", "McKees Rocks"),  # 120L
    (61, 6, "LEFT", "McKeesport"),  # 120R
    (63, 6, "RIGHT", "McKeesport"),  # SHARED wrap to (63,7)
    # Scale / 117 / Barn / 116 / 103 / S-1
    (10, 7, "RIGHT", "OS 102"),  # 102LA
    (11, 7, "LEFT", "Scale"),
    (13, 7, "RIGHT", "Scale"),
    (14, 7, "LEFT", "OS 117"),  # 117RA
    (15, 7, "BOTTOM", "OS 117"),
    (15, 8, "TOP", "OS 117b"),
    (16, 7, "RIGHT", "OS 117"),  # 117LB
    (17, 7, "LEFT", "Barn"),
    (26, 7, "RIGHT", "Barn"),
    (27, 7, "LEFT", "OS 116"),
    (27, 7, "BOTTOM", "OS 116"),
    (27, 8, "TOP", "OS 118"),  # 116 Thrown stub | 118 (no jump)
    (28, 7, "RIGHT", "OS 116"),
    (29, 7, "LEFT", "OS 103"),
    (30, 7, "RIGHT", "OS 103"),
    (31, 7, "LEFT", "S-1"),
    (30, 7, "BOTTOM", "OS 103"),
    (30, 8, "TOP", "OS 104"),
    (38, 7, "RIGHT", "S-1"),
    (39, 7, "LEFT", "OS 111b"),  # 111RB
    (41, 7, "RIGHT", "OS 111b"),
    (42, 7, "LEFT", "OS 110"),  # OS 110 | OS 111b
    (42, 7, "BOTTOM", "OS 110"),  # 110R — OS 110 | OS 109
    (42, 8, "TOP", "OS 109"),
    (43, 7, "RIGHT", "OS 110"),
    (44, 7, "LEFT", "OS 112"),
    (45, 7, "RIGHT", "OS 112"),  # 112L
    (43, 8, "RIGHT", "Main East"),
    (44, 8, "LEFT", "OS 112"),  # 112R (CATS name only; no field mast yet)
    (46, 7, "LEFT", "East Lead"),
    (50, 7, "RIGHT", "East Lead"),
    (51, 7, "LEFT", "OS 113a"),  # 113RB
    (53, 7, "RIGHT", "OS 113a"),
    (54, 7, "LEFT", "OS 114"),
    (56, 7, "RIGHT", "OS 114"),  # 114LA
    (57, 7, "LEFT", "McKeesport"),
    (63, 7, "RIGHT", "McKeesport"),
    # Brick / Plane / E Main Ext / 117b
    (4, 8, "RIGHT", "OS 100"),
    (5, 8, "LEFT", "Brick-Plane"),
    (4, 8, "BOTTOM", "OS 100"),
    (4, 9, "TOP", "OS 101"),
    (7, 8, "RIGHT", "Brick-Plane"),
    (8, 8, "LEFT", "OS 102"),
    (10, 8, "RIGHT", "OS 102"),  # 102LB
    (11, 8, "LEFT", "East Main Ext"),
    (13, 8, "RIGHT", "East Main Ext"),
    (14, 8, "LEFT", "OS 117b"),  # 117RB
    (16, 8, "RIGHT", "OS 117b"),  # 117LA
    (17, 8, "LEFT", "Main East"),
    # Engine House
    (21, 8, "LEFT", "EH-1"),
    (23, 8, "RIGHT", "EH-1"),
    (24, 8, "LEFT", "OS 119"),
    (24, 8, "BOTTOM", "OS 119"),
    (24, 9, "TOP", "EH-2"),
    (25, 8, "RIGHT", "OS 119"),
    (26, 8, "LEFT", "OS 118"),
    (26, 8, "BOTTOM", "OS 118"),
    (26, 9, "TOP", "EH-3"),
    (21, 9, "LEFT", "EH-2"),
    (21, 10, "LEFT", "EH-3"),
    # South yard ladders
    (31, 8, "RIGHT", "OS 104"),
    (32, 8, "LEFT", "S-2"),
    (31, 8, "BOTTOM", "OS 104"),
    (31, 9, "TOP", "OS 105"),
    (40, 8, "RIGHT", "S-2"),
    (41, 8, "LEFT", "OS 109"),
    (41, 8, "BOTTOM", "OS 109"),
    (41, 9, "TOP", "OS 108"),
    (32, 9, "RIGHT", "OS 105"),
    (33, 9, "LEFT", "S-3"),
    (32, 9, "BOTTOM", "OS 105"),
    (32, 10, "TOP", "OS 106"),
    (39, 9, "RIGHT", "S-3"),
    (40, 9, "LEFT", "OS 108"),
    (40, 9, "BOTTOM", "OS 108"),
    (40, 10, "TOP", "OS 107"),
    (33, 10, "RIGHT", "OS 106"),
    (34, 10, "LEFT", "S-4"),
    (33, 10, "BOTTOM", "OS 106"),
    (33, 11, "TOP", "S-5"),
    (38, 10, "RIGHT", "S-4"),
    (39, 10, "LEFT", "OS 107"),
    (39, 10, "BOTTOM", "OS 107"),
    (39, 11, "TOP", "S-5"),
    # W-1 / W-2
    (6, 9, "RIGHT", "OS 101"),  # 101RB
    (7, 9, "LEFT", "W-2"),
    (9, 9, "RIGHT", "W-2"),
    (6, 10, "RIGHT", "OS 101"),  # 101RA
    (7, 10, "LEFT", "W-1"),
    (9, 10, "RIGHT", "W-1"),
    # K-2
    (56, 8, "RIGHT", "OS 114"),  # 114LB
    (57, 8, "LEFT", "K-2"),
]
# Name existing lamps only (keep Designer PANELSIGNAL).
SIGNAL_NAMES: dict[tuple[int, int, str], str] = {
    (6, 10, "RIGHT"): "101RA",  # W-1
    (6, 9, "RIGHT"): "101RB",  # W-2
    (3, 8, "LEFT"): "100L",
    (10, 8, "RIGHT"): "102LB",
    (10, 7, "RIGHT"): "102LA",
    (14, 8, "LEFT"): "117RB",
    (16, 8, "RIGHT"): "117LA",
    (14, 7, "LEFT"): "117RA",
    (16, 7, "RIGHT"): "117LB",
    (39, 6, "LEFT"): "111RA",
    (45, 6, "RIGHT"): "111L",
    (51, 6, "LEFT"): "113RA",
    (51, 7, "LEFT"): "113RB",
    (56, 6, "RIGHT"): "115LA",
    (56, 5, "RIGHT"): "115LB",
    (60, 6, "RIGHT"): "120L",
    (61, 6, "LEFT"): "120R",
    (39, 7, "LEFT"): "111RB",
    (42, 7, "BOTTOM"): "110R",
    (45, 7, "RIGHT"): "112L",
    (44, 8, "LEFT"): "112R",  # panel CP name; no JMRI mast yet
    (56, 7, "RIGHT"): "114LA",
    (56, 8, "RIGHT"): "114LB",
}

# Designer captions are in the right cells; do not relocate them.
LABEL_FIXES: dict[tuple[int, int], str] = {}
LABEL_ALIGN: dict[tuple[int, int], str] = {}

# 110R is on OS 110 BOTTOM (110|109). A CP on OS 109 would stop 109→110 N/X.
SIGNAL_MOVES: list[tuple[tuple[int, int, str], tuple[int, int, str]]] = []
SIGNAL_PANEL: dict[tuple[int, int, str], tuple[str, str]] = {}

# Panel-edge wraps. Paint stays gapped; N/X routes through. Same BLOCK
# name so occupancy merges: Main West west stubs; Princess McKeesport.
SHARED_LINKS: list[tuple[tuple[int, int, str], tuple[int, int, str]]] = [
    ((1, 6, "LEFT"), (1, 8, "LEFT")),
    ((63, 6, "RIGHT"), (63, 7, "RIGHT")),
]

STATIONS = {
    "W-1": "W-1",
    "W-2": "W-2",
    "EH-1": "EH-1",
    "EH-2": "EH-2",
    "EH-3": "EH-3",
    "Scale": "West Lead",
    "Barn": "West Lead",
    "S-1": "S-1",
    "S-2": "S-2",
    "S-3": "S-3",
    "S-4": "S-4",
    "S-5": "S-5",
    "K-1": "K-1",
    "K-2": "K-2",
    "McKees Rocks": "McKees Rocks",
    "McKeesport": "McKeesport",
    "East Lead": "East Lead",
    "Main West": "Main West",
    "West Main Ext": "Main West",
    "Main East": "Main East",
    "East Main Ext": "Main East",
    "Brick-Plane": "Brick-Plane",
}


TRACK_ENDS = {
    "HORIZONTAL": frozenset({"LEFT", "RIGHT"}),
    "VERTICAL": frozenset({"TOP", "BOTTOM"}),
    "UPPERSLASH": frozenset({"LEFT", "TOP"}),
    "LOWERSLASH": frozenset({"RIGHT", "BOTTOM"}),
    "UPPERBACKSLASH": frozenset({"RIGHT", "TOP"}),
    "LOWERBACKSLASH": frozenset({"LEFT", "BOTTOM"}),
}


def _edge(sec: ET.Element, edge: str) -> ET.Element | None:
    for e in sec.findall("SEC_EDGE"):
        if e.get("EDGE") == edge:
            return e
    return None


def _ensure_edge(sec: ET.Element, edge: str) -> ET.Element:
    found = _edge(sec, edge)
    if found is not None:
        return found
    el = ET.SubElement(sec, "SEC_EDGE", {"EDGE": edge})
    return el


def add_extra_tracks(tp: ET.Element) -> int:
    """Add the omitted 100 / ladder frogs so SWITCHPOINTS have three legs."""
    secs = {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in tp.findall("SECTION")
        if s.find("TRACKGROUP") is not None
    }
    n = 0
    for xy, kind in EXTRA_TRACKS.items():
        sec = secs.get(xy)
        if sec is None:
            print(f"EXTRA TRACK SKIP missing cell {xy}", file=sys.stderr)
            continue
        tg = sec.find("TRACKGROUP")
        if tg is None:
            continue
        have = tio.section_tracks(sec)
        if kind not in have:
            ET.SubElement(tg, "TRACK").text = kind
            n += 1
        for edge in TRACK_ENDS[kind]:
            _ensure_edge(sec, edge)
    return n


def _shift_ladder_band(tp: ET.Element, y_from: int, dy: int = 1) -> None:
    """Move track (and labels sitting on those cells) in columns 23–33 down.

    High Y first so a cell never lands on one that has not moved yet.
    """
    x0, x1 = 23, 33
    secs = [
        s
        for s in tp.findall("SECTION")
        if x0 <= int(s.get("X", "-1")) <= x1 and int(s.get("Y", "-1")) >= y_from
    ]
    for s in sorted(secs, key=lambda el: int(el.get("Y", "0")), reverse=True):
        s.set("Y", str(int(s.get("Y")) + dy))


def _add_vertical(tp: ET.Element, x: int, y: int) -> None:
    occupied = {(int(s.get("X")), int(s.get("Y"))) for s in tp.findall("SECTION")}
    if (x, y) in occupied:
        print(f"LADDER SPACER SKIP occupied ({x},{y})", file=sys.stderr)
        return
    sec = ET.SubElement(tp, "SECTION", {"X": str(x), "Y": str(y)})
    tg = ET.SubElement(sec, "TRACKGROUP")
    t = ET.SubElement(tg, "TRACK")
    t.text = "VERTICAL"
    ET.SubElement(sec, "SEC_EDGE", {"EDGE": "TOP"})
    ET.SubElement(sec, "SEC_EDGE", {"EDGE": "BOTTOM"})


def insert_ladder_os_gaps(root: ET.Element, tp: ET.Element) -> int:
    """No-op: Designer now staggers the H+slash ladders.

    Spine BOTTOM of each frog faces a plain slash cell, not the next
    SWITCHPOINTS, so OS 104–109 already separate without inserted VERTICALs.
    """
    return 0


def strip_designer_blocks(tp: ET.Element) -> int:
    """Drop every BLOCK. ANCHORS are the occupancy SoR (re-applied next).

    Source may be a previously wired save (leftover names would stick).
    Nameless <BLOCK /> NPEs; stale names would keep extra rail gaps.
    """
    n = 0
    for sec in tp.findall("SECTION"):
        for e in sec.findall("SEC_EDGE"):
            blk = e.find("BLOCK")
            if blk is None:
                continue
            e.remove(blk)
            n += 1
    return n


def name_blocks(tp: ET.Element) -> int:
    disc = le.load_disciplines()
    secs = {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in tp.findall("SECTION")
        if s.find("TRACKGROUP") is not None
    }
    n = 0
    for x, y, edge, name in ANCHORS:
        sec = secs.get((x, y))
        if sec is None:
            print(f"ANCHOR SKIP: ({x},{y}) {edge} {name}", file=sys.stderr)
            continue
        if edge not in _track_ends(sec):
            print(f"ANCHOR SKIP not a track end: ({x},{y}) {edge} {name}", file=sys.stderr)
            continue
        se = _ensure_edge(sec, edge)
        blk = se.find("BLOCK")
        if blk is None:
            blk = ET.SubElement(se, "BLOCK")
        blk.set("NAME", name)
        blk.set("STATION", STATIONS.get(name, name.split()[0] if name.startswith("OS") else name))
        if name.startswith("OS"):
            blk.set("STATION", name.replace("OS ", "").split()[0])
        blk.set("DISCIPLINE", disc.get(name, "CTC"))
        blk.set("VISIBLE", "true")
        n += 1
    return n


def add_shared_jumps(tp: ET.Element) -> int:
    """Joint non-adjacent edges. CATS SecEdge.bind() uses SHARED instead of
    the geographic neighbor (paint stays gapped; N/X routes).

    Both ends must point at each other. Same-name jumps merge occupancy:
    west-edge Main West wrap and Princess McKeesport wrap.
    """
    keep_blk = {(x, y, e) for x, y, e, _ in ANCHORS}
    secs = {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in tp.findall("SECTION")
        if s.find("TRACKGROUP") is not None
    }
    for sec in secs.values():
        for e in sec.findall("SEC_EDGE"):
            for old in list(e.findall("SHARED")):
                e.remove(old)
    n = 0
    pairs = list(SHARED_LINKS) + [(b, a) for a, b in SHARED_LINKS]
    for (x, y, edge), (ox, oy, oedge) in pairs:
        sec = secs.get((x, y))
        if sec is None:
            print(f"SHARED SKIP missing ({x},{y})", file=sys.stderr)
            continue
        if edge not in _track_ends(sec):
            print(f"SHARED SKIP not a track end ({x},{y}) {edge}", file=sys.stderr)
            continue
        se = _ensure_edge(sec, edge)
        if se.find("SWITCHPOINTS") is not None:
            print(f"SHARED SKIP points ({x},{y}) {edge}", file=sys.stderr)
            continue
        if se.find("CROSSINGEDGE") is not None:
            print(f"SHARED SKIP crossing ({x},{y}) {edge}", file=sys.stderr)
            continue
        blk = se.find("BLOCK")
        if blk is not None and (x, y, edge) not in keep_blk:
            se.remove(blk)
        for old in list(se.findall("SHARED")):
            se.remove(old)
        sh = ET.SubElement(se, "SHARED", {"X": str(ox), "Y": str(oy)})
        sh.text = oedge
        n += 1
    return n


def name_signals(tp: ET.Element) -> int:
    secs = {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in tp.findall("SECTION")
        if s.find("TRACKGROUP") is not None
    }
    n = 0
    for (x, y, edge), name in SIGNAL_NAMES.items():
        sec = secs.get((x, y))
        if sec is None:
            print(f"SIGNAL SKIP: {name} @({x},{y})", file=sys.stderr)
            continue
        se = _edge(sec, edge)
        if se is None:
            print(f"SIGNAL SKIP edge: {name} @({x},{y}) {edge}", file=sys.stderr)
            continue
        sig = se.find("SECSIGNAL")
        if sig is None:
            print(f"SIGNAL SKIP missing SECSIGNAL: {name} @({x},{y}) {edge}", file=sys.stderr)
            continue
        # Text node is the JMRI mast userName.
        sig.text = "\n          " + name + "\n          "
        pan = sig.find("PANELSIGNAL")
        loc = SIGNAL_PANEL.get((x, y, edge))
        if pan is not None and loc is not None:
            pan.set("SIGLOCATION", loc[0])
            pan.set("SIGORIENT", loc[1])
        n += 1
    return n


def mast_head_counts() -> dict[str, int]:
    """Packed-head count per mast userName from signal_wiring.csv."""
    path = ROOT / "cats/data/signal_wiring.csv"
    counts: dict[str, int] = {}
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            mast = (row.get("mast_user_name") or "").strip()
            if mast:
                counts[mast] = counts.get(mast, 0) + 1
    return counts


_PHYS_BY_HEADS = {1: "single", 2: "double", 3: "triple"}


def align_physignal_to_heads(tp: ET.Element) -> int:
    """PHYSIGNAL must match JMRI heads. CATS setAspect uses the template name
    even when HOLD_ONLY; double→Clear on an SL-1-low dwarf aborts Screen.init.
    SIGPANTYPE (LAMP1 vs LAMP2) is left for Designer cosmetics (117RA/117LA).
    """
    heads = mast_head_counts()
    n = 0
    for sig in tp.iter("SECSIGNAL"):
        name = (sig.text or "").strip()
        want = _PHYS_BY_HEADS.get(heads.get(name, 0))
        if not want:
            continue
        phys = sig.find("PHYSIGNAL")
        if phys is None:
            phys = ET.SubElement(sig, "PHYSIGNAL")
        if (phys.text or "").strip() != want:
            phys.text = want
            n += 1
    return n


def add_missing_plants(tp: ET.Element) -> int:
    secs = {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in tp.findall("SECTION")
        if s.find("TRACKGROUP") is not None
    }
    n = 0
    for xy, (_os, _normal, _ident) in PLANTS.items():
        sec = secs.get(xy)
        if sec is None:
            print(f"PLANT SKIP missing cell {xy}", file=sys.stderr)
            continue
        tracks = tio.section_tracks(sec)
        pts = le.points_edge(tracks)
        if pts is None:
            print(f"PLANT SKIP no points edge {xy} {tracks}", file=sys.stderr)
            continue
        se = _ensure_edge(sec, pts)
        # R2: BLOCK and SWITCHPOINTS must not share an edge (existing SP too).
        blk = se.find("BLOCK")
        if blk is not None:
            se.remove(blk)
        if se.find("SWITCHPOINTS") is not None:
            continue
        ET.SubElement(se, "SWITCHPOINTS")
        n += 1
    return n


def strip_foreign_points(tp: ET.Element) -> int:
    """Designer SWITCHPOINTS stay. Empty SPUR is completed in finish_empty_spurs."""
    return 0


def finish_empty_spurs(tp: ET.Element) -> int:
    """CATS 3.1 PtsVitalLogic.setPoints AIOOBs if SPUR has getNormal()==-1.

    Empty SWITCHPOINTS SPUR (not in PLANTS) gets a through NORMAL so CATS
    3.1 PtsVitalLogic.setPoints does not AIOOB.
    """
    plant_cells = set(PLANTS)
    prefer = ("RIGHT", "LEFT", "BOTTOM", "TOP")
    n = 0
    for sec in tp.findall("SECTION"):
        if sec.find("TRACKGROUP") is None:
            continue
        xy = (int(sec.get("X")), int(sec.get("Y")))
        if xy in plant_cells:
            continue
        tracks = tio.section_tracks(sec)
        pts = le.points_edge(tracks)
        if pts is None:
            continue
        se = _edge(sec, pts)
        if se is None:
            continue
        sp = se.find("SWITCHPOINTS")
        if sp is None or sp.findall("ROUTEINFO"):
            continue
        legs = [e for e in le.cell_edges(tracks) if e != pts]
        if not legs:
            continue
        normal = next((e for e in prefer if e in legs), legs[0])
        for leg in legs:
            attrs = {"ROUTEID": leg}
            if leg == normal:
                attrs["NORMAL"] = "true"
            ET.SubElement(sp, "ROUTEINFO", attrs)
        n += 1
    return n


def drop_110_crossing(tp: ET.Element) -> None:
    """No-op: 110 Thrown is geographic into (42,8) toward 109."""
    drop: dict[tuple[int, int], str] = {}
    secs = {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in tp.findall("SECTION")
        if s.find("TRACKGROUP") is not None
    }
    for xy, kind in drop.items():
        sec = secs.get(xy)
        if sec is None:
            continue
        tg = sec.find("TRACKGROUP")
        if tg is not None:
            for tr in list(tg.findall("TRACK")):
                if (tr.text or "").strip() == kind:
                    tg.remove(tr)
        used = _track_ends(sec)
        for se in list(sec.findall("SEC_EDGE")):
            xing = se.find("CROSSINGEDGE")
            if xing is not None:
                se.remove(xing)
            ed = se.get("EDGE") or ""
            if ed and ed not in used:
                sec.remove(se)


def clear_points_facing_blocks(tp: ET.Element) -> int:
    """R3: the cell facing SWITCHPOINTS must be a plain SecEdge, not BlkEdge."""
    opp = {"LEFT": "RIGHT", "RIGHT": "LEFT", "TOP": "BOTTOM", "BOTTOM": "TOP"}
    step = {"LEFT": (-1, 0), "RIGHT": (1, 0), "TOP": (0, -1), "BOTTOM": (0, 1)}
    secs = {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in tp.findall("SECTION")
        if s.find("TRACKGROUP") is not None
    }
    n = 0
    for (x, y), sec in secs.items():
        for e in sec.findall("SEC_EDGE"):
            if e.find("SWITCHPOINTS") is None:
                continue
            ed = e.get("EDGE") or ""
            dx, dy = step[ed]
            other = secs.get((x + dx, y + dy))
            if other is None:
                continue
            back = opp[ed]
            oe = _edge(other, back)
            if oe is None or oe.find("BLOCK") is None:
                continue
            if oe.find("SWITCHPOINTS") is not None:
                continue
            blk = oe.find("BLOCK")
            oe.remove(blk)
            n += 1
    return n


def _track_ends(sec: ET.Element) -> set[str]:
    used: set[str] = set()
    for kind in tio.section_tracks(sec):
        used |= TRACK_ENDS.get(kind, set())
    return used


def heal_blk_plain_seams(tp: ET.Element) -> int:
    """Copy a named BLOCK onto a real track-end mate that is still PLAIN.

    BlkEdge.discoverAdvanceVitalLogic casts the neighbor to AbstractTrackEdge
    (ClassCast on a bare SecEdge) then calls MyBlock.getDiscipline()
    (NPE on anonymous <BLOCK />). Same occupancy name on both sides of the
    joint is a BlkEdge with MyBlock set. Skip SWITCHPOINTS throats (R3) and
    do not invent edges that are not track ends.
    """
    opp = {"LEFT": "RIGHT", "RIGHT": "LEFT", "TOP": "BOTTOM", "BOTTOM": "TOP"}
    step = {"LEFT": (-1, 0), "RIGHT": (1, 0), "TOP": (0, -1), "BOTTOM": (0, 1)}
    secs = {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in tp.findall("SECTION")
        if s.find("TRACKGROUP") is not None
    }
    n = 0
    for (x, y), sec in list(secs.items()):
        for e in list(sec.findall("SEC_EDGE")):
            src = e.find("BLOCK")
            if src is None or e.find("SWITCHPOINTS") is not None:
                continue
            ed = e.get("EDGE") or ""
            dx, dy = step[ed]
            other = secs.get((x + dx, y + dy))
            if other is None:
                continue
            back = opp[ed]
            if back not in _track_ends(other):
                continue
            oe = _edge(other, back)
            if oe is None:
                oe = ET.SubElement(other, "SEC_EDGE", {"EDGE": back})
            if oe.find("SWITCHPOINTS") is not None:
                continue
            if oe.find("CROSSINGEDGE") is not None:
                continue
            if e.find("SHARED") is not None or oe.find("SHARED") is not None:
                continue
            # Only close ClassCast at a lamp joint. Copying an OS name through
            # a frog paints a gap in the middle of the plant.
            if e.find("SECSIGNAL") is None and oe.find("SECSIGNAL") is None:
                continue
            # Do not put two occupancy names on one Track (CATS Track.warn).
            # If the mate track already has a different name on its other end,
            # skip the copy and keep this name — the joint stays a named cut.
            far = _other_end(other, back)
            far_e = _edge(other, far) if far else None
            far_b = far_e.find("BLOCK") if far_e is not None else None
            far_name = far_b.get("NAME") if far_b is not None else None
            src_name = src.get("NAME")
            if far_name and src_name and far_name != src_name:
                continue
            dst = oe.find("BLOCK")
            if dst is None:
                dst = ET.SubElement(oe, "BLOCK")
            if dst.get("NAME"):
                continue
            for key in ("NAME", "STATION", "DISCIPLINE", "VISIBLE"):
                if src.get(key) and not dst.get(key):
                    dst.set(key, src.get(key))
            n += 1
    return n


def _other_end(sec: ET.Element, edge: str) -> str | None:
    for kind in tio.section_tracks(sec):
        ends = TRACK_ENDS.get(kind)
        if ends and edge in ends:
            for e in ends:
                if e != edge:
                    return e
    return None


def break_dual_named_tracks(tp: ET.Element) -> int:
    """One CATS Track may carry only one Block. Drop the extra name."""
    secs = {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in tp.findall("SECTION")
        if s.find("TRACKGROUP") is not None
    }
    n = 0
    for sec in secs.values():
        for kind in tio.section_tracks(sec):
            ends = TRACK_ENDS.get(kind)
            if not ends or len(ends) != 2:
                continue
            a, b = tuple(ends)
            ea, eb = _edge(sec, a), _edge(sec, b)
            ba = ea.find("BLOCK") if ea is not None else None
            bb = eb.find("BLOCK") if eb is not None else None
            na = ba.get("NAME") if ba is not None else None
            nb = bb.get("NAME") if bb is not None else None
            if not na or not nb or na == nb:
                continue
            # Keep OS occupancy; drop the body-track name on the same frog.
            drop_e, drop_b = (ea, ba)
            if str(na).startswith("OS ") and not str(nb).startswith("OS "):
                drop_e, drop_b = eb, bb
            elif str(nb).startswith("OS ") and not str(na).startswith("OS "):
                drop_e, drop_b = ea, ba
            drop_e.remove(drop_b)
            n += 1
    return n


def fill_anonymous_blocks(tp: ET.Element) -> int:
    """Nameless BLOCK NPEs (MyBlock is null). Drop them unless a lamp needs it."""
    n = 0
    for sec in tp.findall("SECTION"):
        if sec.find("TRACKGROUP") is None:
            continue
        for e in list(sec.findall("SEC_EDGE")):
            blk = e.find("BLOCK")
            if blk is None or blk.get("NAME"):
                continue
            if e.find("SWITCHPOINTS") is not None:
                e.remove(blk)
                n += 1
                continue
            if e.find("SECSIGNAL") is not None:
                continue
            e.remove(blk)
            n += 1
    return n


def _copy_block_name(dst_edge: ET.Element, src_block: ET.Element) -> None:
    blk = dst_edge.find("BLOCK")
    if blk is None:
        blk = ET.SubElement(dst_edge, "BLOCK")
    for key in ("NAME", "STATION", "DISCIPLINE", "VISIBLE"):
        if src_block.get(key) and not blk.get(key):
            blk.set(key, src_block.get(key))


def _faces_points(secs: dict, x: int, y: int, ed: str) -> bool:
    opp = {"LEFT": "RIGHT", "RIGHT": "LEFT", "TOP": "BOTTOM", "BOTTOM": "TOP"}
    step = {"LEFT": (-1, 0), "RIGHT": (1, 0), "TOP": (0, -1), "BOTTOM": (0, 1)}
    dx, dy = step[ed]
    other = secs.get((x + dx, y + dy))
    if other is None:
        return False
    oe = _edge(other, opp[ed])
    return oe is not None and oe.find("SWITCHPOINTS") is not None


def _shared_edge(sec: ET.Element, edge: str) -> bool:
    n = 0
    for kind in tio.section_tracks(sec):
        ends = TRACK_ENDS.get(kind)
        if ends and edge in ends:
            n += 1
    return n > 1


def fill_same_track_names(tp: ET.Element) -> int:
    """If one end of a Track is named, name the other (unless it faces SWITCHPOINTS)."""
    secs = {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in tp.findall("SECTION")
        if s.find("TRACKGROUP") is not None
    }
    n = 0
    for (x, y), sec in secs.items():
        for kind in tio.section_tracks(sec):
            ends = TRACK_ENDS.get(kind)
            if not ends or len(ends) != 2:
                continue
            a, b = tuple(ends)
            if _shared_edge(sec, a) or _shared_edge(sec, b):
                continue
            ea, eb = _edge(sec, a), _edge(sec, b)
            if ea is None or eb is None:
                continue
            if ea.find("SWITCHPOINTS") is not None or eb.find("SWITCHPOINTS") is not None:
                continue
            ba = ea.find("BLOCK")
            bb = eb.find("BLOCK")
            na = ba.get("NAME") if ba is not None else None
            nb = bb.get("NAME") if bb is not None else None
            if na and not nb and not _faces_points(secs, x, y, b):
                _copy_block_name(eb, ba)
                n += 1
            elif nb and not na and not _faces_points(secs, x, y, a):
                _copy_block_name(ea, bb)
                n += 1
    return n


def name_signal_seams(tp: ET.Element) -> int:
    """SECSIGNAL on a bare SecEdge ClassCasts; both sides of the joint need a Block."""
    opp = {"LEFT": "RIGHT", "RIGHT": "LEFT", "TOP": "BOTTOM", "BOTTOM": "TOP"}
    step = {"LEFT": (-1, 0), "RIGHT": (1, 0), "TOP": (0, -1), "BOTTOM": (0, 1)}
    secs = {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in tp.findall("SECTION")
        if s.find("TRACKGROUP") is not None
    }
    n = 0
    for (x, y), sec in secs.items():
        for e in list(sec.findall("SEC_EDGE")):
            if e.find("SECSIGNAL") is None or e.find("SWITCHPOINTS") is not None:
                continue
            ed = e.get("EDGE") or ""
            blk = e.find("BLOCK")
            name = blk.get("NAME") if blk is not None else None
            if not name:
                far = _other_end(sec, ed)
                far_e = _edge(sec, far) if far else None
                far_b = far_e.find("BLOCK") if far_e is not None else None
                if far_b is not None and far_b.get("NAME"):
                    _copy_block_name(e, far_b)
                    name = far_b.get("NAME")
                    n += 1
            if not name or _faces_points(secs, x, y, ed):
                continue
            dx, dy = step[ed]
            other = secs.get((x + dx, y + dy))
            if other is None:
                continue
            back = opp[ed]
            if back not in _track_ends(other):
                continue
            oe = _ensure_edge(other, back)
            if oe.find("SWITCHPOINTS") is not None:
                continue
            if oe.find("CROSSINGEDGE") is not None:
                continue
            if e.find("SHARED") is not None or oe.find("SHARED") is not None:
                continue
            ob = oe.find("BLOCK")
            if ob is not None and ob.get("NAME"):
                continue
            src = e.find("BLOCK")
            if src is not None and src.get("NAME"):
                _copy_block_name(oe, src)
                n += 1
    return n


def strip_blk_facing_plain(tp: ET.Element) -> int:
    """A named BLOCK facing a bare SecEdge ClassCasts. Drop the name."""
    opp = {"LEFT": "RIGHT", "RIGHT": "LEFT", "TOP": "BOTTOM", "BOTTOM": "TOP"}
    step = {"LEFT": (-1, 0), "RIGHT": (1, 0), "TOP": (0, -1), "BOTTOM": (0, 1)}
    secs = {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in tp.findall("SECTION")
        if s.find("TRACKGROUP") is not None
    }
    n = 0
    for (x, y), sec in list(secs.items()):
        for e in list(sec.findall("SEC_EDGE")):
            blk = e.find("BLOCK")
            if blk is None or e.find("SWITCHPOINTS") is not None:
                continue
            ed = e.get("EDGE") or ""
            dx, dy = step[ed]
            other = secs.get((x + dx, y + dy))
            if other is None:
                continue
            back = opp[ed]
            oe = _edge(other, back)
            if oe is None:
                continue
            if oe.find("SWITCHPOINTS") is not None:
                continue
            if oe.find("CROSSINGEDGE") is not None:
                continue
            if e.find("SHARED") is not None or oe.find("SHARED") is not None:
                continue
            if oe.find("BLOCK") is not None:
                continue
            e.remove(blk)
            n += 1
    return n


def fix_labels(tp: ET.Element) -> int:
    n = 0
    by_xy = {(int(s.get("X")), int(s.get("Y"))): s for s in tp.findall("SECTION")}
    for xy, text in LABEL_FIXES.items():
        s = by_xy.get(xy)
        if text == "":
            if s is None:
                continue
            nm = s.find("SEC_NAME")
            if nm is not None:
                s.remove(nm)
                n += 1
            continue
        if s is None:
            s = ET.Element("SECTION", {"X": str(xy[0]), "Y": str(xy[1])})
            tp.append(s)
            by_xy[xy] = s
        loc = LABEL_ALIGN.get(xy, "LOWCENT")
        nm = s.find("SEC_NAME")
        if nm is None:
            ET.SubElement(
                s, "SEC_NAME",
                {"LOC_NAME": loc, "NAME": text, "FONT_NAME": "FONT_LABEL"},
            )
            n += 1
            continue
        if nm.get("NAME") != text:
            nm.set("NAME", text)
            n += 1
        if nm.get("LOC_NAME") != loc:
            nm.set("LOC_NAME", loc)
            n += 1
    for xy, loc in LABEL_ALIGN.items():
        if xy in LABEL_FIXES:
            continue
        s = by_xy.get(xy)
        if s is None:
            continue
        nm = s.find("SEC_NAME")
        if nm is None:
            continue
        if nm.get("LOC_NAME") != loc:
            nm.set("LOC_NAME", loc)
            n += 1
    return n


def move_signals(tp: ET.Element) -> int:
    """Relocate a Designer SECSIGNAL onto the occupancy-cut cell/edge."""
    secs = {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in tp.findall("SECTION")
        if s.find("TRACKGROUP") is not None
    }
    n = 0
    for (fx, fy, fedge), (tx, ty, tedge) in SIGNAL_MOVES:
        src_sec = secs.get((fx, fy))
        dst_sec = secs.get((tx, ty))
        if src_sec is None or dst_sec is None:
            print(f"SIGNAL MOVE SKIP missing cell ({fx},{fy})→({tx},{ty})", file=sys.stderr)
            continue
        src_e = _edge(src_sec, fedge)
        if src_e is None:
            print(f"SIGNAL MOVE SKIP no source edge ({fx},{fy}) {fedge}", file=sys.stderr)
            continue
        sig = src_e.find("SECSIGNAL")
        if sig is None:
            print(f"SIGNAL MOVE SKIP no SECSIGNAL ({fx},{fy}) {fedge}", file=sys.stderr)
            continue
        dst_e = _ensure_edge(dst_sec, tedge)
        if dst_e.find("SECSIGNAL") is not None:
            src_e.remove(sig)
            n += 1
            continue
        src_e.remove(sig)
        dst_e.append(sig)
        pan = sig.find("PANELSIGNAL")
        loc = SIGNAL_PANEL.get((tx, ty, tedge))
        if pan is not None and loc is not None:
            pan.set("SIGLOCATION", loc[0])
            pan.set("SIGORIENT", loc[1])
        elif pan is not None:
            if tedge == "LEFT":
                pan.set("SIGLOCATION", "UPLEFT")
                pan.set("SIGORIENT", "LEFT")
            elif tedge == "BOTTOM" and pan.get("SIGORIENT") == "TOP":
                pan.set("SIGLOCATION", "UPCENT")
                pan.set("SIGORIENT", "TOP")
        n += 1
    return n


def _expected_blocks() -> set[str]:
    names: set[str] = set()
    with (ROOT / "cats/data/occupancy_bindings.csv").open(encoding="utf-8") as fh:
        next(fh)
        for line in fh:
            name = line.split(",", 1)[0].strip()
            if name:
                names.add(name)
    return names


def _expected_idents() -> set[str]:
    idents: set[str] = set()
    with (ROOT / "cats/data/turnout_bindings.csv").open(encoding="utf-8") as fh:
        next(fh)
        for line in fh:
            ident = line.split(",", 1)[0].strip()
            if ident:
                idents.add(ident)
    return idents


OMITTED_BLOCKS: set[str] = set()
OMITTED_IDENTS: set[str] = set()


def audit_coverage(tp: ET.Element) -> None:
    named = {b.get("NAME") for b in tp.iter("BLOCK") if b.get("NAME")}
    expected = _expected_blocks() - OMITTED_BLOCKS
    missing_blk = sorted(expected - named)
    extra_blk = sorted(named - _expected_blocks())
    have_ident = {ident for _os, _n, ident in PLANTS.values()}
    missing_to = sorted((_expected_idents() - OMITTED_IDENTS) - have_ident)
    extra_to = sorted(have_ident - _expected_idents())
    print(
        f"coverage blocks={len(named)} missing={missing_blk or '-'} "
        f"extra={extra_blk or '-'} omitted={sorted(OMITTED_BLOCKS)}  "
        f"plants={len(PLANTS)} "
        f"idents_missing={missing_to or '-'} extra={extra_to or '-'}"
    )


def promote_to_live() -> None:
    """Copy wired Master 4 onto the live CTC/ABS Masters and rebuild HOLD copies.

    Skips header polish so the Designer 1920×540 window and title row stay.
    """
    shutil.copy2(DST, LIVE_CTC)
    print(f"live CTC {LIVE_CTC}")

    abs_xml = LIVE_CTC.read_text(encoding="utf-8").replace(
        'DISCIPLINE="CTC"', 'DISCIPLINE="ABS"'
    )
    LIVE_ABS.write_text(abs_xml, encoding="utf-8")
    abs_tree = ET.parse(LIVE_ABS)
    abs_tp = abs_tree.getroot().find("TRACKPLAN")
    assert abs_tp is not None
    today = date.today().isoformat()
    for s in abs_tp.findall("SECTION"):
        if int(s.get("Y", "-1")) != 1:
            continue
        nm = s.find("SEC_NAME")
        if nm is None:
            continue
        name = nm.get("NAME") or ""
        if name == "CTC DIGICON":
            nm.set("NAME", "ABS DIGICON")
        elif name.startswith("DS-CTC"):
            nm.set("NAME", f"DS-ABS  Rev A  Eff {today}")
    abs_tree.write(LIVE_ABS, encoding="UTF-8", xml_declaration=True)
    subprocess.check_call(
        [sys.executable, str(ROOT / "cats/scripts/unbind_abs_from_jmri_masts.py"), str(LIVE_ABS)]
    )
    print(f"live ABS {LIVE_ABS}")

    hold = ROOT / "cats/scripts"
    subprocess.check_call(
        [
            sys.executable,
            str(hold / "build_hart_master_ctc_hold.py"),
            "--src",
            str(LIVE_CTC),
            "--dst",
            str(LIVE_CTC_HOLD),
        ]
    )
    subprocess.check_call(
        [
            sys.executable,
            str(hold / "build_hart_master_abs_hold.py"),
            "--src",
            str(LIVE_ABS),
            "--dst",
            str(LIVE_ABS_HOLD),
        ]
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--live",
        action="store_true",
        help="Promote wired Master 4 to live CATS CTC / CATS ABS Masters.",
    )
    args = ap.parse_args()
    if not SRC.is_file():
        raise SystemExit(f"missing {SRC}")
    shutil.copy2(SRC, DST)
    tree = ET.parse(DST)
    root = tree.getroot()
    tp = root.find("TRACKPLAN")
    assert tp is not None

    n_tr = add_extra_tracks(tp)
    n_lab = fix_labels(tp)
    n_mv = move_signals(tp)
    n_gap = insert_ladder_os_gaps(root, tp)
    n_strip = strip_designer_blocks(tp)
    n_blk = name_blocks(tp)
    n_sig = name_signals(tp)
    n_phys = align_physignal_to_heads(tp)
    n_new_sp = add_missing_plants(tp)
    n_sp_strip = strip_foreign_points(tp)
    n_spur = finish_empty_spurs(tp)
    drop_110_crossing(tp)
    n_r3 = clear_points_facing_blocks(tp)
    n_heal = heal_blk_plain_seams(tp)
    n_dual = break_dual_named_tracks(tp)
    n_anon = fill_anonymous_blocks(tp)
    n_sig_seams = name_signal_seams(tp)
    n_heal += heal_blk_plain_seams(tp)
    n_plain = strip_blk_facing_plain(tp)
    n_r3 += clear_points_facing_blocks(tp)
    drop_110_crossing(tp)
    n_share = add_shared_jumps(tp)

    to_map = tio.load_turnouts()
    n_to = tio.wire_turnouts(
        tp, to_map, plants=PLANTS, invert_vs_jmri=INVERT_VS_JMRI
    )

    for ops in root.iter("OPERATIONS"):
        ops.set("CONNECT", "false")

    gen.ensure_mqtt(root)
    occ = le.load_occupancy()
    gen.wire_occupancy(root, occ)

    # Keep the CATS window at the Designer frame (WIDTH/HEIGHT/COLUMNS/ROWS).
    src_root = ET.parse(SRC).getroot()
    for attr in ("WIDTH", "HEIGHT", "X", "Y"):
        if src_root.get(attr) is not None:
            root.set(attr, src_root.get(attr))
    src_tp = src_root.find("TRACKPLAN")
    if src_tp is not None:
        for attr in ("COLUMNS", "ROWS"):
            if src_tp.get(attr) is not None:
                tp.set(attr, src_tp.get(attr))

    tree.write(DST, encoding="UTF-8", xml_declaration=True)
    print(
        f"wrote {DST}  extra_tracks={n_tr} labels={n_lab} moved_sig={n_mv} "
        f"ladder_spacers={n_gap} stripped={n_strip} "
        f"blocks={n_blk} "
        f"signals={n_sig} physignal={n_phys} new_sp={n_new_sp} empty_spurs={n_spur} foreign_sp_stripped={n_sp_strip} r3_cleared={n_r3} "
        f"r4_healed={n_heal} dual={n_dual} anon={n_anon} "
        f"sig_seams={n_sig_seams} blk_plain={n_plain} shared={n_share} turnout_io={n_to}"
    )
    audit_coverage(tp)
    if args.live:
        promote_to_live()


if __name__ == "__main__":
    main()
