#!/usr/bin/env python3
"""Wire HART_Master4.xml geometry → HART_Master4_wired.xml.

Designer save is HART_Master4.xml. Live desks:

    python3 cats/scripts/wire_hart_master4.py --live

That copies the wired panel to HART_Master.xml / HART_Master_ABS.xml and
rebuilds the CATS CTC / CATS ABS HOLD copies.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_hart_digicon_from_le as le  # noqa: E402
import jmri_to_cats_digicon as gen  # noqa: E402
import wire_hart_sheet_west_yard2 as sheet  # noqa: E402

SRC = ROOT / "cats/panels/HART_Master4.xml"
DST = ROOT / "cats/panels/HART_Master4_wired.xml"
LIVE_CTC = ROOT / "cats/panels/HART_Master.xml"
LIVE_ABS = ROOT / "cats/panels/HART_Master_ABS.xml"
LIVE_CTC_HOLD = ROOT / "cats/panels/HART_Master_CTC_hold.xml"
LIVE_ABS_HOLD = ROOT / "cats/panels/HART_Master_ABS_hold.xml"

# (x, y) → (OS name, NORMAL route among non-points legs, layout_ident)
# NORMAL is the drawn through / main. invert_vs_jmri plants put throw on
# that NORMAL route (JMRI Thrown = mainline): 100, 112, 114, 115.
#
# Left → right on the focused main (BRICK @ x=5, PLANE @ x=9):
#   100 Brick (5,6) → 101 West Yard (6,5, above) → 102 Plane (9,6) → 117…
# 110 frog is (36,7). Thrown BOTTOM is geographic into (36,8) UPPERSLASH
# (longer diverge + 110R). That LEFT SHARED-jumps to 109 (35,9) TOP.
# (35,8) has no rail. OS 111a SHARED-skips (34,8) RIGHT ↔ (37,8) LEFT.
# Wrap to Brick is SHARED (1,8) LEFT ↔ (1,6) LEFT.
# 116 Thrown does not SHARED-jump over MW (that landed on 118).
# 103 Thrown SHARED-jumps over MW to (25,9) TOP.
# 119 at (17,9); 118 at (19,9); 118 throat is (20,9).
PLANTS: dict[tuple[int, int], tuple[str, str, str]] = {
    (5, 6): ("OS 100", "RIGHT", "TOL3"),  # Brick. Thrown = through; Closed = W yard
    (6, 5): ("OS 101", "TOP", "TOL38"),  # West Yard. Closed = W-1 (TOP); Thrown = W-2 (RIGHT)
    (10, 6): ("OS 102", "RIGHT", "TOL42"),  # Plane. Closed = through to 117b; Thrown = Scale
    (16, 6): ("OS 117b", "RIGHT", "TO117"),
    (39, 6): ("OS 112", "LEFT", "TOL23"),  # Thrown = Y=6 East Lead; Closed = OS 110
    (47, 6): ("OS 113a", "RIGHT", "TO113"),
    (55, 6): ("OS 114", "RIGHT", "TOR36"),  # Thrown = McKeesport; Closed = K-2
    (16, 7): ("OS 117", "LEFT", "TO117"),
    (21, 7): ("OS 116", "LEFT", "TO1"),
    (24, 7): ("OS 103", "RIGHT", "TOR14"),
    (34, 7): ("OS 111b", "LEFT", "TO111"),
    (36, 7): ("OS 110", "LEFT", "TOL6"),  # Closed = S-1/111; Thrown = (36,8) then SHARED to 109
    (34, 8): ("OS 111a", "RIGHT", "TO111"),
    (48, 8): ("OS 113b", "LEFT", "TO113"),
    (51, 8): ("OS 115", "RIGHT", "TOL29"),  # Thrown = McKees Rocks; Closed = K-1
    (17, 9): ("OS 119", "LEFT", "TO10"),  # EH-1 LEFT; Thrown BOTTOM = EH-2
    (19, 9): ("OS 118", "LEFT", "TO11"),  # Closed LEFT = from 119; Thrown BOTTOM = EH-3
    # Staggered H+slash ladders (Designer). Spine BOTTOM faces a plain slash
    # cell, not the next SWITCHPOINTS — no spacer insert.
    (26, 9): ("OS 104", "BOTTOM", "TOL15"),
    (34, 9): ("OS 109", "BOTTOM", "TOR7"),
    (27, 10): ("OS 105", "BOTTOM", "TOL17"),
    (33, 10): ("OS 108", "BOTTOM", "TOR9"),
    (28, 11): ("OS 106", "BOTTOM", "TOL19"),
    (32, 11): ("OS 107", "BOTTOM", "TOR11"),
}

# CATS NORMAL = drawn through. These four are JMRI Thrown when lined
# for that through route (Designer “differs from JMRI settings”).
INVERT_VS_JMRI = {"TOL3", "TOL23", "TOR36", "TOL29"}  # 100, 112, 114, 115

# Do not add rails. Designer already drew 100/101/117/ladder frogs.
EXTRA_TRACKS: dict[tuple[int, int], str] = {}

# Named BLOCK only at occupancy cuts (different names facing) and the mate
# of a mid-block lamp. CATS paints a rail gap at every BlkEdge. Occupancy
# flows through turnouts (PtsEdge.propagateBlock) — frog interiors stay plain.
ANCHORS: list[tuple[int, int, str, str]] = [
    # W-1 is 101 NORMAL (TOP / Closed). W-2 is Thrown RIGHT. 101RA/RB follow.
    (7, 4, "RIGHT", "OS 101"),  # 101RA
    (8, 4, "LEFT", "W-1"),
    (10, 4, "RIGHT", "W-1"),
    (7, 5, "RIGHT", "OS 101"),  # 101RB
    (8, 5, "LEFT", "W-2"),
    (10, 5, "RIGHT", "W-2"),
    # OS 100 | OS 101 on the yard lead. 101 points face LEFT — (5,5) RIGHT stays plain.
    (5, 6, "TOP", "OS 100"),
    (5, 5, "BOTTOM", "OS 101"),
    # Spur west of 100 is Main West (wrap merges with Y=8). Gap at 100:
    # (4,6) RIGHT stays plain (100 points face LEFT).
    (3, 6, "RIGHT", "Main West"),
    (4, 6, "LEFT", "OS 100"),
    # OS 100 | Brick-Plane (3 cells) | OS 102. Gap at 100 and at 102.
    (5, 6, "RIGHT", "OS 100"),
    (6, 6, "LEFT", "Brick-Plane"),
    (8, 6, "RIGHT", "Brick-Plane"),
    (9, 6, "LEFT", "OS 102"),
    # OS 102 includes 102LB / 102LA (plant is (10,6); lamps sit east of the frog)
    (11, 6, "RIGHT", "OS 102"),  # 102LB
    (12, 6, "LEFT", "East Main Ext"),
    (14, 6, "RIGHT", "East Main Ext"),
    (15, 6, "LEFT", "OS 117b"),  # 117RB
    # (17,6) is OS 117b (no LEFT gap at the frog). Cut is east of 117LA.
    (17, 6, "RIGHT", "OS 117b"),  # 117LA
    (18, 6, "LEFT", "Main East"),
    # Main East | OS 112 (112R). Lamp stacked with 111 at x=33.
    # 112 points face RIGHT so (40,6) LEFT stays plain.
    (32, 6, "RIGHT", "Main East"),
    (33, 6, "LEFT", "OS 112"),  # 112R
    # OS 112 | East Lead (112L). (40,6) LEFT faces 112 SP — leave plain.
    (40, 6, "RIGHT", "OS 112"),  # 112L
    (41, 6, "LEFT", "East Lead"),
    (45, 6, "RIGHT", "East Lead"),
    (46, 6, "LEFT", "OS 113a"),  # 113RB
    # 113 crossover: Designer gap is mid-slash (47,7)|(48,7), not at 113a frog.
    (47, 7, "RIGHT", "OS 113a"),
    (48, 7, "LEFT", "OS 113b"),
    # OS 113a | OS 114 (114 points face LEFT at (55,6) — (54,6) RIGHT stays plain)
    (53, 6, "RIGHT", "OS 113a"),
    (54, 6, "LEFT", "OS 114"),
    # (56,6) is OS 114 (no LEFT gap at the frog). Cut is east of 114LA.
    (56, 6, "RIGHT", "OS 114"),  # 114LA
    (57, 6, "LEFT", "McKeesport"),
    # Balloon wrap: same McKeesport name on both SHARED bumpers so occupancy
    # continues Y=6 → wrap → Y=8 east of 115R.
    (64, 6, "RIGHT", "McKeesport"),
    (64, 8, "RIGHT", "McKeesport"),
    (11, 7, "RIGHT", "OS 102"),  # 102LA
    (12, 7, "LEFT", "Scale"),
    (14, 7, "RIGHT", "Scale"),
    (15, 7, "LEFT", "OS 117"),  # 117RA
    (16, 6, "BOTTOM", "OS 117b"),
    (16, 7, "TOP", "OS 117"),
    (17, 7, "RIGHT", "OS 117"),  # 117LB
    (18, 7, "LEFT", "Barn"),
    (20, 7, "RIGHT", "Barn"),
    (21, 7, "LEFT", "OS 116"),
    # 116 Thrown BOTTOM is a dangling OS 116 edge — do NOT SHARED-jump onto 118.
    (21, 7, "BOTTOM", "OS 116"),
    # OS 116 | OS 103 (116 SP is RIGHT so (22,7) LEFT stays plain)
    (22, 7, "RIGHT", "OS 116"),
    (23, 7, "LEFT", "OS 103"),
    # OS 103 | S-1 (103 SP is LEFT so (23,7) RIGHT stays plain)
    (24, 7, "RIGHT", "OS 103"),
    (25, 7, "LEFT", "S-1"),
    (32, 7, "RIGHT", "S-1"),
    (33, 7, "LEFT", "OS 111b"),  # 111RB — (33,7) is OS, no RIGHT gap
    # OS 111b | OS 111a
    (34, 7, "BOTTOM", "OS 111b"),
    (34, 8, "TOP", "OS 111a"),
    # OS 111b | OS 110 (111b SP is RIGHT so (35,7) LEFT stays plain)
    (35, 7, "RIGHT", "OS 111b"),
    (36, 7, "LEFT", "OS 110"),
    # OS 110 | OS 112 Closed (110 SP is RIGHT so (37,7) LEFT stays plain)
    (37, 7, "RIGHT", "OS 110"),
    (38, 7, "LEFT", "OS 112"),
    (39, 6, "BOTTOM", "OS 112"),
    (39, 7, "TOP", "OS 112"),
    # 110 Thrown: frog BOTTOM stays plain (geographic into (36,8) TOP).
    # 110R on the longer diverge SHARED-jumps to 109. Occupancy cut.
    (36, 8, "LEFT", "OS 110"),  # 110R
    (35, 9, "TOP", "OS 109"),
    # 111a east leg is gapped at x=35. Same OS 111a name on both SHARED
    # ends so occupancy continues; paint stays gapped. SP is LEFT so RIGHT
    # is the through leg (not R2).
    (34, 8, "RIGHT", "OS 111a"),
    (37, 8, "LEFT", "OS 111a"),
    # 103 Thrown SHARED-jumps over Main West to (25,9) (104 approach).
    (24, 7, "BOTTOM", "OS 103"),
    (25, 9, "TOP", "OS 104"),
    # (39,8) is OS 111a (no gap). Cut is east of 111L.
    (40, 8, "RIGHT", "OS 111a"),  # 111L
    (41, 8, "LEFT", "West Main Ext"),
    (45, 8, "RIGHT", "West Main Ext"),
    (46, 8, "LEFT", "OS 113b"),  # 113RA (same occupancy as 113b, like 113RB)
    (49, 8, "RIGHT", "OS 113b"),
    (50, 8, "LEFT", "OS 115"),
    # (52,8) is OS 115 (no LEFT gap at the frog). Cut is east of 115LA.
    (52, 8, "RIGHT", "OS 115"),  # 115LA
    (53, 8, "LEFT", "McKees Rocks"),
    # Intermediates on Y=8, west of the wrap: 114R westbound into McKees Rocks,
    # 115R eastbound into the McKeesport wrap. Occupancy cut between them.
    (61, 8, "RIGHT", "McKees Rocks"),  # 114R
    (62, 8, "LEFT", "McKeesport"),  # 115R
    (55, 6, "BOTTOM", "OS 114"),
    (55, 7, "TOP", "K-2"),
    (56, 7, "RIGHT", "K-2"),  # 114LB
    (59, 7, "RIGHT", "K-2"),
    (51, 8, "BOTTOM", "OS 115"),
    (51, 9, "TOP", "K-1"),
    (52, 9, "RIGHT", "K-1"),  # 115LB
    (55, 9, "RIGHT", "K-1"),
    # EH: 119 at (17,9) SP RIGHT; 118 at (19,9) SP RIGHT.
    # (16,9) LEFT faces 119 west leg (ok to name). (18,9) LEFT faces 119 SP — plain.
    # (20,9) LEFT faces 118 SP — plain. (20,9) TOP is the 118 throat boundary.
    (14, 9, "LEFT", "EH-1"),
    (15, 9, "RIGHT", "EH-1"),
    (16, 9, "LEFT", "OS 119"),
    (16, 9, "RIGHT", "OS 119"),
    (18, 9, "RIGHT", "OS 119"),
    (19, 9, "LEFT", "OS 118"),
    (20, 9, "TOP", "OS 118"),  # 118 throat — not OS 116
    (14, 10, "LEFT", "EH-2"),
    (17, 9, "BOTTOM", "OS 119"),
    (17, 10, "TOP", "EH-2"),
    (14, 11, "LEFT", "EH-3"),
    (19, 9, "BOTTOM", "OS 118"),
    (19, 10, "TOP", "EH-3"),
    # Main West | OS 111a (111a SP is LEFT so (33,8) RIGHT stays plain)
    (32, 8, "RIGHT", "Main West"),
    # West-edge wrap: Main West (1,8) LEFT SHARED-joins Brick (1,6) LEFT.
    # Both ends are Main West so occupancy merges — the spur west of 100
    # is the same detector as the Y=8 spine. Gap at 100 is (3,6)|(4,6).
    (1, 8, "LEFT", "Main West"),
    (1, 6, "LEFT", "Main West"),
    (33, 8, "LEFT", "OS 111a"),  # 111RA
    # Staggered ladders — body and spine cuts, never facing SWITCHPOINTS.
    (26, 9, "RIGHT", "OS 104"),
    (27, 9, "LEFT", "S-2"),
    (33, 9, "RIGHT", "S-2"),
    (34, 9, "LEFT", "OS 109"),
    (26, 9, "BOTTOM", "OS 104"),
    (26, 10, "TOP", "OS 105"),
    (34, 9, "BOTTOM", "OS 109"),
    (34, 10, "TOP", "OS 108"),
    (27, 10, "RIGHT", "OS 105"),
    (28, 10, "LEFT", "S-3"),
    (32, 10, "RIGHT", "S-3"),
    (33, 10, "LEFT", "OS 108"),
    (27, 10, "BOTTOM", "OS 105"),
    (27, 11, "TOP", "OS 106"),
    (33, 10, "BOTTOM", "OS 108"),
    (33, 11, "TOP", "OS 107"),
    (28, 11, "RIGHT", "OS 106"),
    (29, 11, "LEFT", "S-4"),
    (31, 11, "RIGHT", "S-4"),
    (32, 11, "LEFT", "OS 107"),
    (28, 11, "BOTTOM", "OS 106"),
    (28, 12, "TOP", "S-5"),
    (32, 11, "BOTTOM", "OS 107"),
    (32, 12, "TOP", "S-5"),
    # S-5 body is continuous (no LEFT gap at 29,12 / no RIGHT gap at 31,12).
]
# Name existing lamps only (keep Designer PANELSIGNAL).
SIGNAL_NAMES: dict[tuple[int, int, str], str] = {
    (7, 4, "RIGHT"): "101RA",
    (7, 5, "RIGHT"): "101RB",
    (11, 6, "RIGHT"): "102LB",
    (15, 6, "LEFT"): "117RB",
    (17, 6, "RIGHT"): "117LA",
    (33, 6, "LEFT"): "112R",
    (40, 6, "RIGHT"): "112L",
    (46, 6, "LEFT"): "113RB",
    (56, 6, "RIGHT"): "114LA",
    (61, 8, "RIGHT"): "114R",
    (11, 7, "RIGHT"): "102LA",
    (15, 7, "LEFT"): "117RA",
    (17, 7, "RIGHT"): "117LB",
    (33, 7, "LEFT"): "111RB",
    (56, 7, "RIGHT"): "114LB",
    (33, 8, "LEFT"): "111RA",
    (40, 8, "RIGHT"): "111L",
    (46, 8, "LEFT"): "113RA",
    (52, 8, "RIGHT"): "115LA",
    (62, 8, "LEFT"): "115R",
    (36, 8, "LEFT"): "110R",  # longer 110 diverge — must not sit on OS 109
    (52, 9, "RIGHT"): "115LB",
}

# Designer captions are in the right cells; do not relocate them.
LABEL_FIXES: dict[tuple[int, int], str] = {
    (9, 4): "W-1",
    (9, 5): "W-2",
}

LABEL_ALIGN: dict[tuple[int, int], str] = {
    (9, 4): "LOWCENT",
    (9, 5): "LOWCENT",
    (28, 6): "LOWCENT",
    (41, 6): "LOWCENT",
    (58, 6): "LOWCENT",
    (56, 7): "LOWCENT",
    (56, 8): "LOWCENT",
    (28, 7): "LOWCENT",
    (14, 8): "LOWCENT",
    (28, 8): "LOWCENT",
    (41, 8): "LOWCENT",
    (13, 9): "LOWCENT",
    (28, 9): "LOWCENT",
    (52, 9): "LOWCENT",
    (13, 10): "LOWCENT",
    (28, 10): "LOWCENT",
    (13, 11): "LOWCENT",
    (28, 11): "LOWCENT",
    (28, 12): "LOWCENT",
}

# 110R stays where Designer put it: (36,8) LEFT on the longer diverge.
# A CP on OS 109 would stop 109→110 search at the approach.
# 114R/115R stay where Designer put them: opposing intermediates on Y=8
# at the McKees Rocks | McKeesport cut, not on the wrap bumpers.
SIGNAL_MOVES: list[tuple[tuple[int, int, str], tuple[int, int, str]]] = []
SIGNAL_PANEL: dict[tuple[int, int, str], tuple[str, str]] = {
    (36, 8, "LEFT"): ("LOWRIGHT", "TOP"),  # 110R
}

# Non-adjacent joints. CATS SecEdge.bind() uses SHARED instead of the
# geographic neighbor (SecEdge.java: if DescribeEdge != null, locate that
# Section/edge). Paint stays gapped; N/X routes through. Occupancy only
# merges when both SHARED ends share a BLOCK name. Princess wrap bumpers
# are both McKeesport so occupancy continues around the balloon.
# Both ends must point at each other (HART_Brick.xml, Chubb_APB.xml).
SHARED_LINKS: list[tuple[tuple[int, int, str], tuple[int, int, str]]] = [
    # Main West west bumper → Brick west of 100 (panel-edge wrap)
    ((1, 8, "LEFT"), (1, 6, "LEFT")),
    # 110 longer diverge → 109 across the schematic gap
    ((36, 8, "LEFT"), (35, 9, "TOP")),
    # OS 111a skips the empty (35,8) and the 110 slash at (36,8)
    ((34, 8, "RIGHT"), (37, 8, "LEFT")),
    # 103 Thrown → 104 approach across Main West
    ((24, 7, "BOTTOM"), (25, 9, "TOP")),
    # Princess balloon: east McKeesport wraps to east McKees Rocks (RIGHT↔RIGHT).
    # Same BLOCK name (McKeesport) so occupancy merges. 114R/115R sit west of this.
    ((64, 6, "RIGHT"), (64, 8, "RIGHT")),
    # 116 Thrown does not jump onto 118. (20,9) is the 118 throat (OS 118).
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
        have = sheet._tracks(sec)
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

    Both ends must point at each other. Occupancy-cut jumps keep ANCHORS
    names so the two detectors stay separate: 110→109 and 103→104.
    Same-name jumps merge occupancy: west-edge Main West wrap, Princess
    McKeesport wrap, and the OS 111a skip (34,8) RIGHT ↔ (37,8) LEFT. 116 Thrown does
    not jump onto 118.
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
        tracks = sheet._tracks(sec)
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
        tracks = sheet._tracks(sec)
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
    """(36,8) is the 110 diverge UPPERSLASH — do not strip it. (35,8) has no rail."""
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
    for kind in sheet._tracks(sec):
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
    for kind in sheet._tracks(sec):
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
        for kind in sheet._tracks(sec):
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
    for kind in sheet._tracks(sec):
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
        for kind in sheet._tracks(sec):
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
            "--no-polish",
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
            "--no-polish",
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

    to_map = sheet.load_turnouts()
    n_to = sheet.wire_turnouts(
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
        f"signals={n_sig} new_sp={n_new_sp} empty_spurs={n_spur} foreign_sp_stripped={n_sp_strip} r3_cleared={n_r3} "
        f"r4_healed={n_heal} dual={n_dual} anon={n_anon} "
        f"sig_seams={n_sig_seams} blk_plain={n_plain} shared={n_share} turnout_io={n_to}"
    )
    audit_coverage(tp)
    if args.live:
        promote_to_live()


if __name__ == "__main__":
    main()
