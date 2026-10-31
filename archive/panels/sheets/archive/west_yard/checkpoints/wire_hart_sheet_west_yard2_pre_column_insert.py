#!/usr/bin/env python3
"""Assign Digicon blocks onto West Yard SoR — edges only, no cell edits.

SoR: cats/panels/sheets/HART_sheet_West_Yard_SOR.xml
  (TRACKGROUP + SEC_NAME + Designer SWITCHPOINTS; any prior BLK edges ignored)

Rules (cats/docs/CATS_SOURCE_PAINT.md):
  - Blocks flow through SWITCHPOINTS (plain→SP). Do not cut the plant throat.
  - Each BLK↔BLK pair is a visible rail gap in CATS — keep cuts minimal.
  - Name OS on the approach cell (same region as the plant).

    python3 cats/scripts/wire_hart_sheet_west_yard2.py
"""

from __future__ import annotations

import csv
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_hart_digicon_ctc as ctc  # noqa: E402
import build_hart_digicon_from_le as le  # noqa: E402
import jmri_to_cats_digicon as gen  # noqa: E402

SOR = ROOT / "cats/panels/sheets/HART_sheet_West_Yard_SOR.xml"
SRC = ROOT / "cats/panels/sheets/HART_sheet_West_Yard2.xml"
ACTIVE = ROOT / "cats/panels/sheets/HART_sheet_West_Yard.xml"
SHOT = ROOT / "cats/screenshots/sheets/HART_sheet_West_Yard2.png"
TURNOUT_CSV = ROOT / "cats/data/turnout_bindings.csv"
HART_PANEL = ROOT / "jmri/layouts/hart/output/hart_prod.xml"

# SoR plant cells (tracks unchanged). 111b mate has tracks but no Designer SP.
# Second field = NORMAL route among non-points legs (not the SP edge).
# Digicon polarity: NORMAL leg = JMRI CLOSED (close); other = THROWN (throw).
# Dispatcher tip SoR (confirmed):
#   112 THROWN = BOTTOM Barn; CLOSED = LEFT through OS110 / S-1
#   114 THROWN = BOTTOM McKeesport (default); CLOSED = RIGHT K-2
#   115 THROWN = TOP Rocks; CLOSED = RIGHT K-1 (good — leave alone)
# SEL+CMD always share polarity. Wrong frog → flip that one PLANTS NORMAL only.
PLANTS: dict[tuple[int, int], tuple[str, str, str]] = {
    # Brick/WY on y=3; 100-102 = VERTICAL (6,4–6) into Plane tip (6,7).
    (4, 3): ("OS 101 (Brick)", "LEFT", "TOL38"),
    # 100: continuing=THROWN → BOTTOM (100–102); CLOSED → LEFT.
    (6, 3): ("OS 100 (Brick)", "LEFT", "TOL3"),
    # 102: CLOSED → East Main Ext (BOTTOM); THROWN → Yard T1 (RIGHT).
    (7, 7): ("OS 102 (Plane)", "BOTTOM", "TOL42"),
    (12, 7): ("OS 117 (West Yard)", "LEFT", "TO117"),
    (12, 8): ("OS 117b (West Yard)", "RIGHT", "TO117"),
    (14, 6): ("OS 119 (West Yard)", "LEFT", "TO10"),
    (16, 6): ("OS 118 (West Yard)", "TOP", "TO11"),
    (17, 7): ("OS 116 (West Yard)", "LEFT", "TO1"),
    # SY/EE ladder: 103 entry normal RIGHT into S-1; 104–106 / 107–110
    # ladder spine = BOTTOM (CLOSED). Diverge = RIGHT (SY) / LEFT (EE) into S-n.
    (20, 7): ("OS 103 (South Yard)", "RIGHT", "TOR14"),
    (21, 8): ("OS 104 (South Yard)", "BOTTOM", "TOL15"),
    (22, 9): ("OS 105 (South Yard)", "BOTTOM", "TOL17"),
    (23, 10): ("OS 106 (South Yard)", "BOTTOM", "TOL19"),
    (27, 10): ("OS 107 (East End)", "BOTTOM", "TOR11"),
    (28, 9): ("OS 108 (East End)", "BOTTOM", "TOR9"),
    (29, 8): ("OS 109 (East End)", "BOTTOM", "TOR7"),
    # 110: on Main East — LEFT = through to 112 (CLOSED); BOTTOM = EE ladder diverge.
    (30, 7): ("OS 110 (East End)", "LEFT", "TOL6"),
    # 112: THROWN = BOTTOM Barn; CLOSED = LEFT through OS110.
    (32, 7): ("OS 112 (East End)", "LEFT", "TOL23"),
    (28, 6): ("OS 111a (East End)", "RIGHT", "TO111"),
    (28, 7): ("OS 111b (East End)", "LEFT", "TO111"),
    (39, 6): ("OS 113b (Princess)", "LEFT", "TO113"),
    (39, 7): ("OS 113a (Princess)", "RIGHT", "TO113"),
    # 115: THROWN = TOP Rocks; CLOSED = RIGHT K-1 (confirmed good).
    (42, 6): ("OS 115 (Princess)", "RIGHT", "TOL29"),
    # 114: THROWN = BOTTOM McKeesport (default); CLOSED = RIGHT K-2.
    (42, 7): ("OS 114 (Princess)", "RIGHT", "TOR36"),
}

# Named rim / approach / tip edges — only cut faces (interior stays plain).
# Gap style: plain within a block; cut only at OS bounds (no same-name BLK↔BLK).
ANCHORS: list[tuple[int, int, str, str]] = [
    # Brick / WY on y=3
    (2, 3, "LEFT", "West Yard 1"),
    (3, 3, "RIGHT", "West Yard 1"),
    (4, 3, "LEFT", "OS 101 (Brick)"),
    (5, 3, "RIGHT", "OS 101 (Brick)"),
    (2, 4, "LEFT", "West Yard 2"),
    (4, 4, "TOP", "West Yard 2"),
    (4, 3, "BOTTOM", "OS 101 (Brick)"),
    (6, 3, "LEFT", "OS 100 (Brick)"),
    (6, 3, "BOTTOM", "OS 100 (Brick)"),
    (7, 3, "RIGHT", "OS 100 (Brick)"),
    # Main West: Brick tip → SE stair → EE
    (8, 3, "LEFT", "Main West"),
    (26, 6, "RIGHT", "Main West"),
    # Block 100-102 vertical (6,4)–(6,6) into Plane tip (6,7)
    (6, 4, "TOP", "Block 100-102"),
    (6, 6, "BOTTOM", "Block 100-102"),
    (6, 7, "TOP", "OS 102 (Plane)"),
    (7, 7, "BOTTOM", "OS 102 (Plane)"),
    (7, 7, "RIGHT", "OS 102 (Plane)"),
    (8, 7, "LEFT", "Yard T1"),
    (11, 7, "RIGHT", "Yard T1"),
    (7, 8, "TOP", "East Main Ext"),
    (10, 8, "RIGHT", "East Main Ext"),
    # Barn
    (12, 7, "LEFT", "OS 117 (West Yard)"),
    (13, 7, "RIGHT", "OS 117 (West Yard)"),
    (14, 7, "LEFT", "Yard T6"),
    (11, 8, "LEFT", "OS 117b (West Yard)"),
    (12, 8, "RIGHT", "OS 117b (West Yard)"),
    (13, 8, "LEFT", "Main East"),
    # ET
    (12, 6, "LEFT", "ET-3"),
    (13, 6, "RIGHT", "ET-3"),
    (14, 6, "LEFT", "OS 119 (West Yard)"),
    (14, 6, "TOP", "OS 119 (West Yard)"),
    (15, 6, "RIGHT", "OS 119 (West Yard)"),
    (12, 5, "LEFT", "ET-2"),
    (14, 5, "BOTTOM", "ET-2"),
    (12, 4, "LEFT", "ET-1"),
    (15, 5, "RIGHT", "ET-1"),
    (16, 5, "LEFT", "OS 118 (West Yard)"),
    (16, 6, "LEFT", "OS 118 (West Yard)"),
    (17, 7, "LEFT", "OS 116 (West Yard)"),
    (18, 7, "RIGHT", "OS 116 (West Yard)"),
    # South Yard
    (19, 7, "LEFT", "OS 103 (South Yard)"),
    (20, 7, "RIGHT", "OS 103 (South Yard)"),
    (21, 7, "LEFT", "Yard Track 1"),
    (21, 8, "RIGHT", "OS 104 (South Yard)"),
    (22, 8, "LEFT", "Yard Track 2"),
    (22, 9, "RIGHT", "OS 105 (South Yard)"),
    (23, 9, "LEFT", "Yard Track 3"),
    (23, 10, "RIGHT", "OS 106 (South Yard)"),
    (24, 10, "LEFT", "Yard Track 4"),
    (23, 10, "BOTTOM", "OS 106 (South Yard)"),
    (23, 11, "TOP", "Yard Track 5"),
    # 111 / EE
    (27, 6, "LEFT", "OS 111a (East End)"),
    (28, 6, "RIGHT", "OS 111a (East End)"),
    (29, 6, "LEFT", "West Main Ext"),
    (27, 7, "RIGHT", "Yard Track 1"),
    (28, 7, "LEFT", "OS 111b (East End)"),
    (29, 7, "RIGHT", "OS 111b (East End)"),
    (30, 7, "LEFT", "OS 110 (East End)"),
    (31, 7, "RIGHT", "OS 110 (East End)"),
    (29, 8, "LEFT", "OS 109 (East End)"),
    (28, 9, "LEFT", "OS 108 (East End)"),
    (27, 10, "LEFT", "OS 107 (East End)"),
    (32, 7, "LEFT", "OS 112 (East End)"),
    (32, 7, "BOTTOM", "OS 112 (East End)"),
    (33, 7, "RIGHT", "OS 112 (East End)"),
    (32, 8, "TOP", "Main East"),
    (34, 7, "LEFT", "East Lead"),
    (37, 7, "RIGHT", "East Lead"),
    (28, 8, "RIGHT", "Yard Track 2"),
    (27, 9, "RIGHT", "Yard Track 3"),
    (26, 10, "RIGHT", "Yard Track 4"),
    # Princess: K-1 = OS 115 body (Block 1-4); K-2 = OS 114 body (Block 1-3).
    # Rocks / Port loops are separate (McKees Rocks 1-1 / McKeesport 1-2).
    # Name BOTH faces of destination cuts (not plant-side anon) so OS occupancy
    # cannot flood across the Joint into the 100/101 loops.
    (38, 6, "RIGHT", "West Main Ext"),
    (39, 6, "LEFT", "OS 113b (Princess)"),
    (40, 6, "RIGHT", "OS 113b (Princess)"),
    (38, 7, "LEFT", "OS 113a (Princess)"),
    (39, 7, "RIGHT", "OS 113a (Princess)"),
    (40, 7, "LEFT", "OS 114 (Princess)"),
    (42, 7, "BOTTOM", "OS 114 (Princess)"),
    # K-2 stub east of 114: plain through plant tip (no BLK) so Digicon has
    # one continuous region with OS 114 — no rail gaps on the two-cell body.
    (42, 8, "TOP", "McKeesport"),
    (45, 7, "TOP", "McKeesport"),
    (41, 6, "LEFT", "OS 115 (Princess)"),
    (42, 6, "TOP", "OS 115 (Princess)"),
    # K-1 stub east of 115: same — plain tip into two-cell body.
    (42, 5, "BOTTOM", "McKees Rocks"),
    (45, 6, "BOTTOM", "McKees Rocks"),
]

CUTS: list[tuple[tuple[int, int], str, tuple[int, int], str, str]] = [
    ((3, 3), "RIGHT", (4, 3), "LEFT", "W-1 | OS101"),
    ((4, 4), "TOP", (4, 3), "BOTTOM", "W-2 | OS101"),
    ((5, 3), "RIGHT", (6, 3), "LEFT", "OS101 tip | OS100"),
    ((6, 3), "BOTTOM", (6, 4), "TOP", "OS100 | Block 100-102"),
    ((6, 6), "BOTTOM", (6, 7), "TOP", "Block 100-102 | OS102"),
    ((7, 3), "RIGHT", (8, 3), "LEFT", "OS100 tip | Main West"),
    ((7, 7), "RIGHT", (8, 7), "LEFT", "OS102 | Yard T1"),
    ((7, 7), "BOTTOM", (7, 8), "TOP", "OS102 | East Main Ext (406)"),
    ((10, 8), "RIGHT", (11, 8), "LEFT", "East Main Ext (406) | OS117b"),
    ((11, 7), "RIGHT", (12, 7), "LEFT", "Yard T1 | OS117"),
    ((13, 7), "RIGHT", (14, 7), "LEFT", "OS117 tip | Yard T6"),
    ((12, 7), "BOTTOM", (12, 8), "TOP", "OS117 | OS117b diamond"),
    ((12, 8), "RIGHT", (13, 8), "LEFT", "OS117b | Main East"),
    ((13, 6), "RIGHT", (14, 6), "LEFT", "ET-3 | OS119"),
    ((14, 5), "BOTTOM", (14, 6), "TOP", "ET-2 | OS119"),
    ((15, 6), "RIGHT", (16, 6), "LEFT", "OS119 tip | OS118"),
    ((15, 5), "RIGHT", (16, 5), "LEFT", "ET-1 | OS118"),
    ((17, 6), "BOTTOM", (17, 7), "TOP", "OS118 diagonal | OS116"),
    ((16, 7), "RIGHT", (17, 7), "LEFT", "Yard T6 | OS116"),
    ((18, 7), "RIGHT", (19, 7), "LEFT", "OS116 tip | OS103 tip"),
    ((20, 7), "RIGHT", (21, 7), "LEFT", "OS103 | Yard Track 1 / S-1"),
    ((20, 7), "BOTTOM", (20, 8), "TOP", "OS103 spine"),
    ((21, 8), "RIGHT", (22, 8), "LEFT", "OS104 | Yard Track 2"),
    ((21, 8), "BOTTOM", (21, 9), "TOP", "OS104 spine"),
    ((22, 9), "RIGHT", (23, 9), "LEFT", "OS105 | Yard Track 3"),
    ((22, 9), "BOTTOM", (22, 10), "TOP", "OS105 spine"),
    ((23, 10), "RIGHT", (24, 10), "LEFT", "OS106 | Yard Track 4"),
    ((23, 10), "BOTTOM", (23, 11), "TOP", "OS106 | Yard Track 5"),
    ((26, 6), "RIGHT", (27, 6), "LEFT", "Main West | OS111a tip"),
    ((28, 6), "RIGHT", (29, 6), "LEFT", "OS111a | West Main Ext"),
    ((28, 6), "BOTTOM", (28, 7), "TOP", "OS111a | OS111b diamond"),
    ((27, 7), "RIGHT", (28, 7), "LEFT", "YT1/S-1 | OS111b"),
    ((29, 7), "RIGHT", (30, 7), "LEFT", "OS111b tip | OS110"),
    ((30, 7), "BOTTOM", (30, 8), "TOP", "OS110 spine"),
    ((28, 8), "RIGHT", (29, 8), "LEFT", "OS109 approach"),
    ((29, 8), "BOTTOM", (29, 9), "TOP", "OS109 spine"),
    ((27, 9), "RIGHT", (28, 9), "LEFT", "OS108 approach"),
    ((28, 9), "BOTTOM", (28, 10), "TOP", "OS108 spine"),
    ((26, 10), "RIGHT", (27, 10), "LEFT", "OS107 approach"),
    ((27, 10), "BOTTOM", (27, 11), "TOP", "OS107 spine"),
    ((31, 7), "RIGHT", (32, 7), "LEFT", "OS110 tip | OS112"),
    ((33, 7), "RIGHT", (34, 7), "LEFT", "OS112 tip | East Lead"),
    ((37, 7), "RIGHT", (38, 7), "LEFT", "East Lead | OS113a tip"),
    ((32, 7), "BOTTOM", (32, 8), "TOP", "OS112 spine"),
    ((38, 6), "RIGHT", (39, 6), "LEFT", "WME | OS113b"),
    ((39, 6), "BOTTOM", (39, 7), "TOP", "OS113b | OS113a diamond"),
    ((39, 7), "RIGHT", (40, 7), "LEFT", "OS113a | OS114 approach"),
    ((40, 6), "RIGHT", (41, 6), "LEFT", "OS113b tip | OS115 tip"),
    # OS115/114 stop at plant; destination loops are Blocks 1-1 / 1-2.
    ((42, 6), "TOP", (42, 5), "BOTTOM", "OS115 | McKees Rocks"),
    ((42, 7), "BOTTOM", (42, 8), "TOP", "OS114 | McKeesport"),
    ((45, 6), "BOTTOM", (45, 7), "TOP", "McKees Rocks | McKeesport"),
]

# Panel-lamp NX targets: (x,y,edge) → (name, pantype, loc, orient).
# Must sit on a BLOCK edge (never SP / plain). LAMP1=yard · 2=main · 3=Princess.


def _tracks(sec: ET.Element) -> list[str]:
    tg = sec.find("TRACKGROUP")
    return [(t.text or "").strip() for t in tg.findall("TRACK")] if tg is not None else []


def _clear_edges(sec: ET.Element) -> None:
    for e in list(sec.findall("SEC_EDGE")):
        sec.remove(e)


def load_turnouts() -> dict[str, tuple[str, str]]:
    """layout_ident → (DECADDR, USER_NAME) for M2T."""
    by_user: dict[str, str] = {}
    root = ET.parse(HART_PANEL).getroot()
    for t in root.iter("turnout"):
        sn = (t.findtext("systemName") or t.get("systemName") or "").strip()
        un = (t.findtext("userName") or "").strip()
        if sn.startswith("M2T") and un:
            by_user[un] = sn[3:]
            by_user[sn] = sn[3:]
    out: dict[str, tuple[str, str]] = {}
    with TURNOUT_CSV.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ident = row["layout_ident"].strip()
            key = row["turnout_user_or_system"].strip()
            addr = by_user.get(key)
            if not addr and key.startswith("M2T"):
                addr = key[3:]
            if not addr:
                print(f"TURNOUT SKIP: {ident} unresolved {key}", file=sys.stderr)
                continue
            # Prefer JMRI userName (Switch N) when known.
            uname = key
            for u, a in by_user.items():
                if a == addr and u.startswith("Switch"):
                    uname = u
                    break
            out[ident] = (addr, uname)
    return out


def wire_turnouts(tp: ET.Element, turnout_by_ident: dict[str, tuple[str, str]]) -> int:
    """Bind SELECTEDREPORT + ROUTECOMMAND on each plant SWITCHPOINTS.

    NORMAL route ↔ JMRI CLOSED (close); other leg ↔ THROWN (throw).
    SELECTEDREPORT and ROUTECOMMAND must use the same polarity — remapping
    only the report (to chase a bad MQTT retain) reverses Digicon commands.
    """
    secs = {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in tp.findall("SECTION")
        if s.find("TRACKGROUP") is not None
    }
    n = 0
    for xy, (_os, normal, ident) in PLANTS.items():
        binding = turnout_by_ident.get(ident)
        if not binding:
            print(f"TURNOUT SKIP: plant {xy} {ident} not in CSV", file=sys.stderr)
            continue
        addr, uname = binding
        sec = secs.get(xy)
        if sec is None:
            continue
        tracks = _tracks(sec)
        pts = le.points_edge(tracks)
        if pts is None:
            continue
        legs = [e for e in le.cell_edges(tracks) if e != pts]
        sp_edge = _edge(sec, pts)
        if sp_edge is None:
            continue
        sp = sp_edge.find("SWITCHPOINTS")
        if sp is None:
            sp = ET.SubElement(sp_edge, "SWITCHPOINTS")
        existing = {r.get("ROUTEID"): r for r in sp.findall("ROUTEINFO")}
        for leg in legs:
            ri = existing.get(leg)
            if ri is None:
                attrs = {"ROUTEID": leg}
                if leg == normal:
                    attrs["NORMAL"] = "true"
                ri = ET.SubElement(sp, "ROUTEINFO", attrs)
                existing[leg] = ri
            elif leg == normal:
                ri.set("NORMAL", "true")
            else:
                # Drop stale NORMAL when flipping polarity for one plant.
                if "NORMAL" in ri.attrib:
                    del ri.attrib["NORMAL"]
            for child in list(ri):
                ri.remove(child)
            pol = "close" if leg == normal else "throw"
            for tag in ("SELECTEDREPORT", "ROUTECOMMAND"):
                el = ET.SubElement(ri, tag)
                ios = ET.SubElement(
                    el,
                    "IOSPEC",
                    {"DECADDR": addr, "JMRIPREFIX": "M2T", "USER_NAME": uname},
                )
                ios.text = pol
        n += 1
    return n


def _edge(sec: ET.Element, edge: str) -> ET.Element | None:
    for e in sec.findall("SEC_EDGE"):
        if e.get("EDGE") == edge:
            return e
    return None


# ADR-002: CP + direction + track. Value = (name, pantype, loc, orient).
# Facing: tip INTO the BLOCK on that edge —
#   LEFT→SIGORIENT RIGHT, RIGHT→LEFT, TOP→BOTTOM, BOTTOM→TOP.
# Place on the OS-named face of each plant cut (not the approach/yard side).
SIGNAL_DEFS: dict[tuple[int, int, str], tuple[str, str, str, str]] = {
    # Brick 101 / 100 — OS edges only
    (4, 3, "LEFT"): ("Brick West West Yard 1", "LAMP2", "LOWLEFT", "RIGHT"),
    (4, 3, "BOTTOM"): ("Brick South West Yard 2", "LAMP1", "LOWLEFT", "TOP"),
    (5, 3, "RIGHT"): ("Brick East OS 101", "LAMP2", "LOWRIGHT", "LEFT"),
    (6, 3, "LEFT"): ("Brick West OS 100", "LAMP2", "LOWLEFT", "RIGHT"),
    (6, 3, "BOTTOM"): ("Brick South OS 100", "LAMP2", "LOWLEFT", "TOP"),
    (7, 3, "RIGHT"): ("Brick East Main West", "LAMP2", "LOWRIGHT", "LEFT"),
    # Plane 102
    (6, 7, "TOP"): ("Plane West OS 102", "LAMP2", "LOWLEFT", "BOTTOM"),
    (7, 7, "RIGHT"): ("Plane East Yard T1", "LAMP1", "LOWRIGHT", "LEFT"),
    (7, 7, "BOTTOM"): ("Plane East East Main Ext", "LAMP2", "LOWLEFT", "TOP"),
    # Barn 117 / 117b
    (12, 7, "LEFT"): ("West Yard West Yard T1", "LAMP1", "LOWLEFT", "RIGHT"),
    (13, 7, "RIGHT"): ("West Yard East Yard T6", "LAMP1", "LOWRIGHT", "LEFT"),
    (11, 8, "LEFT"): ("West Yard West East Main Ext", "LAMP2", "LOWLEFT", "RIGHT"),
    (12, 8, "RIGHT"): ("West Yard East Main East", "LAMP2", "LOWRIGHT", "LEFT"),
    # South Yard ladder 103–106 (into yard tracks)
    (20, 7, "RIGHT"): ("South Yard East Yard Track 1", "LAMP1", "LOWRIGHT", "LEFT"),
    (21, 8, "RIGHT"): ("South Yard East Yard Track 2", "LAMP1", "LOWRIGHT", "LEFT"),
    (22, 9, "RIGHT"): ("South Yard East Yard Track 3", "LAMP1", "LOWRIGHT", "LEFT"),
    (23, 10, "RIGHT"): ("South Yard East Yard Track 4", "LAMP1", "LOWRIGHT", "LEFT"),
    (23, 10, "BOTTOM"): ("South Yard East Yard Track 5", "LAMP1", "LOWLEFT", "TOP"),
    # East End 111 / 110 / 112 + ladder
    (27, 6, "LEFT"): ("East End West Main West", "LAMP2", "LOWLEFT", "RIGHT"),
    (28, 6, "RIGHT"): ("East End East West Main Ext", "LAMP2", "LOWRIGHT", "LEFT"),
    (28, 7, "LEFT"): ("East End West Yard Track 1", "LAMP1", "LOWLEFT", "RIGHT"),
    (29, 7, "RIGHT"): ("East End East OS 111b", "LAMP1", "LOWRIGHT", "LEFT"),
    (30, 7, "LEFT"): ("East End West OS 110", "LAMP2", "LOWLEFT", "RIGHT"),
    (31, 7, "RIGHT"): ("East End East OS 110", "LAMP2", "LOWRIGHT", "LEFT"),
    (32, 7, "LEFT"): ("East End West OS 112", "LAMP2", "LOWLEFT", "RIGHT"),
    (32, 7, "BOTTOM"): ("East End West Main East", "LAMP2", "LOWLEFT", "TOP"),
    (33, 7, "RIGHT"): ("East End East East Lead", "LAMP2", "LOWRIGHT", "LEFT"),
    (29, 8, "LEFT"): ("East End West Yard Track 2", "LAMP1", "LOWLEFT", "RIGHT"),
    (28, 9, "LEFT"): ("East End West Yard Track 3", "LAMP1", "LOWLEFT", "RIGHT"),
    (27, 10, "LEFT"): ("East End West Yard Track 4", "LAMP1", "LOWLEFT", "RIGHT"),
    # Princess 113 / 114 / 115
    (38, 7, "LEFT"): ("Princess West East Lead", "LAMP3", "LOWLEFT", "RIGHT"),
    (39, 6, "LEFT"): ("Princess West West Main Ext", "LAMP3", "LOWLEFT", "RIGHT"),
    (39, 7, "RIGHT"): ("Princess East OS 113a", "LAMP3", "LOWRIGHT", "LEFT"),
    (41, 6, "LEFT"): ("Princess West OS 115", "LAMP3", "LOWLEFT", "RIGHT"),
    (42, 6, "TOP"): ("Princess North OS 115", "LAMP3", "UPRIGHT", "BOTTOM"),
    (40, 7, "LEFT"): ("Princess West OS 114", "LAMP3", "LOWLEFT", "RIGHT"),
    (42, 7, "BOTTOM"): ("Princess South OS 114", "LAMP3", "LOWLEFT", "TOP"),
}
_PANTYPE_PHYS = {"LAMP1": "single", "LAMP2": "double", "LAMP3": "triple"}


def _signal_list() -> list[tuple[int, int, str, str, str, str, str]]:
    """(x, y, edge, name, loc, orient, pantype) from SIGNAL_DEFS."""
    out: list[tuple[int, int, str, str, str, str, str]] = []
    for (x, y, edge), (name, pantype, loc, orient) in sorted(
        SIGNAL_DEFS.items(), key=lambda kv: (kv[0][1], kv[0][0], kv[0][2])
    ):
        out.append((x, y, edge, name, loc, orient, pantype))
    return out


def _apply_signals(
    tp: ET.Element,
    signals: list[tuple[int, int, str, str, str, str, str]],
) -> list[str]:
    """Attach panel-lamp SECSIGNAL on existing BLOCK edges only."""
    secs = {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in tp.findall("SECTION")
        if s.find("TRACKGROUP") is not None
    }
    for sec in secs.values():
        for se in sec.findall("SEC_EDGE"):
            for old in list(se.findall("SECSIGNAL")):
                se.remove(old)

    placed: list[str] = []
    for x, y, edge, name, loc, orient, pantype in signals:
        sec = secs.get((x, y))
        if sec is None:
            print(f"SIGNAL SKIP: {name} @({x},{y}) missing cell", file=sys.stderr)
            continue
        se = _edge(sec, edge)
        if se is None or se.find("BLOCK") is None:
            print(
                f"SIGNAL SKIP: {name} @({x},{y}) {edge} needs BLOCK edge",
                file=sys.stderr,
            )
            continue
        if se.find("SWITCHPOINTS") is not None:
            print(f"SIGNAL SKIP: {name} @({x},{y}) {edge} is SP", file=sys.stderr)
            continue
        phys_name = _PANTYPE_PHYS.get(pantype, "single")
        sig = ET.Element("SECSIGNAL")
        sig.text = f"\n          {name}\n          "
        ps = ET.SubElement(
            sig,
            "PANELSIGNAL",
            {"SIGLOCATION": loc, "SIGORIENT": orient, "SIGPANTYPE": pantype},
        )
        ps.tail = "\n          "
        phys = ET.SubElement(sig, "PHYSIGNAL")
        phys.text = phys_name
        phys.tail = "\n        "
        se.append(sig)
        blk = se.find("BLOCK")
        bname = blk.get("NAME") if blk is not None else None
        placed.append(
            f"{name} @({x},{y}) {edge} {pantype}/{phys_name} "
            f"loc={loc} ori={orient} blk={bname}"
        )
    return placed


def _sync_sor_signals(sor_path: Path) -> None:
    """Write SIGNAL_DEFS into SoR so Designer matches the wired panel."""
    root = ET.parse(sor_path).getroot()
    secs = {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in root.findall(".//SECTION")
        if s.find("TRACKGROUP") is not None
    }
    for sec in secs.values():
        for se in sec.findall("SEC_EDGE"):
            for old in list(se.findall("SECSIGNAL")):
                se.remove(old)
    for x, y, edge, name, loc, orient, pantype in _signal_list():
        sec = secs.get((x, y))
        if sec is None:
            continue
        se = _edge(sec, edge)
        if se is None:
            # ensure edge exists for Designer Track Ends
            se = ET.SubElement(sec, "SEC_EDGE", {"EDGE": edge})
        for old in list(se.findall("SECSIGNAL")):
            se.remove(old)
        sig = ET.Element("SECSIGNAL")
        sig.text = f"\n          {name}\n          "
        ps = ET.SubElement(
            sig,
            "PANELSIGNAL",
            {"SIGLOCATION": loc, "SIGORIENT": orient, "SIGPANTYPE": pantype},
        )
        ps.tail = "\n          "
        phys = ET.SubElement(sig, "PHYSIGNAL")
        phys.text = _PANTYPE_PHYS.get(pantype, "single")
        phys.tail = "\n        "
        se.append(sig)
    ET.ElementTree(root).write(sor_path, encoding="UTF-8", xml_declaration=True)


def _strip_sp_side_anchors() -> None:
    for xy in PLANTS:
        tracks = le.GRID.get(xy)
        if not tracks:
            continue
        sp = le.points_edge(tracks)
        if sp is None:
            continue
        le.ANCHORS.pop((xy, sp), None)
        le.ANON.discard((xy, sp))
        dx, dy = le.STEP[sp]
        tip = (xy[0] + dx, xy[1] + dy)
        back = le.OPPOSITE[sp]
        le.ANCHORS.pop((tip, back), None)
        le.ANON.discard((tip, back))


def _demote_non_plant_sp(tp: ET.Element) -> None:
    for s in tp.findall("SECTION"):
        if s.find("TRACKGROUP") is None:
            continue
        xy = (int(s.get("X")), int(s.get("Y")))
        if xy in PLANTS:
            continue
        tracks = _tracks(s)
        pts = le.points_edge(tracks)
        if pts is None:
            continue
        for e in list(s.findall("SEC_EDGE")):
            if e.get("EDGE") != pts or e.find("SWITCHPOINTS") is None:
                continue
            s.remove(e)
            se = ET.Element("SEC_EDGE", {"EDGE": pts})
            key = (xy, pts)
            if key in le.ANCHORS:
                bname = le.ANCHORS[key]
                ET.SubElement(
                    se,
                    "BLOCK",
                    {
                        "NAME": bname,
                        "STATION": bname,
                        "DISCIPLINE": "CTC",
                        "VISIBLE": "true",
                    },
                )
            elif key in le.ANON:
                ET.SubElement(se, "BLOCK")
            s.append(se)


def _report_gaps(tp: ET.Element) -> None:
    """Print Digicon BLK boundaries and Designer empty-cell gaps."""
    kind: dict[tuple[tuple[int, int], str], tuple[str, str | None]] = {}
    cells: dict[tuple[int, int], list[str]] = {}
    for s in tp.findall("SECTION"):
        if s.find("TRACKGROUP") is None:
            continue
        xy = (int(s.get("X")), int(s.get("Y")))
        cells[xy] = _tracks(s)
        for e in s.findall("SEC_EDGE"):
            ed = e.get("EDGE") or ""
            if e.find("SWITCHPOINTS") is not None:
                kind[(xy, ed)] = ("SP", None)
            elif e.find("BLOCK") is not None:
                kind[(xy, ed)] = ("BLK", e.find("BLOCK").get("NAME"))
            else:
                kind[(xy, ed)] = ("plain", None)

    print("\n=== Digicon BLK gaps (wiring) ===")
    seen: set[tuple] = set()
    n = 0
    for (xy, ed), (k, name) in sorted(kind.items()):
        if k != "BLK":
            continue
        dx, dy = le.STEP[ed]
        nb = (xy[0] + dx, xy[1] + dy)
        back = le.OPPOSITE[ed]
        other = kind.get((nb, back))
        if other is None or other[0] != "BLK":
            continue
        key = tuple(sorted([(xy, ed), (nb, back)]))
        if key in seen:
            continue
        seen.add(key)
        n += 1
        a = name or "<anon>"
        b = other[1] or "<anon>"
        print(f"  {xy} {ed} [{a}]  <->  {nb} {back} [{b}]")
    print(f"total Digicon gap pairs: {n}")

    print("\n=== Designer empty cells (SoR geometry, not wiring) ===")
    for y in range(min(c[1] for c in cells), max(c[1] for c in cells) + 1):
        xs = sorted(x for x, yy in cells if yy == y)
        if not xs:
            continue
        missing = [x for x in range(xs[0], xs[-1] + 1) if (x, y) not in cells]
        if missing:
            print(f"  y={y} empty x={missing}")


def wire() -> int:
    if not SOR.exists():
        print(f"MISSING SoR: {SOR}", file=sys.stderr)
        return 2

    # Fresh copy of SoR; we rebuild every SEC_EDGE (ignore any BLK already in SoR).
    shutil.copy2(SOR, SRC)
    root = ET.parse(SRC).getroot()
    tp = root.find("TRACKPLAN")
    assert tp is not None

    secs = {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in tp.findall("SECTION")
        if s.find("TRACKGROUP") is not None
    }
    before = {xy: tuple(_tracks(s)) for xy, s in secs.items()}

    le.GRID.clear()
    le.PLANTS.clear()
    le.ANCHORS.clear()
    le.ANON.clear()
    le.LABELS.clear()

    for xy, s in secs.items():
        le.GRID[xy] = _tracks(s)
        _clear_edges(s)

    for xy, (os_name, normal, ident) in PLANTS.items():
        if xy not in le.GRID:
            print(f"NOTE: plant {xy} {os_name} missing from SoR", file=sys.stderr)
            continue
        le.PLANTS[xy] = (os_name, normal, ident)

    for x, y, edge, name in ANCHORS:
        if (x, y) in le.GRID:
            le.nm((x, y), edge, name)

    cut_reasons: dict[tuple, str] = {}
    for a, ae, b, be, reason in CUTS:
        if a in le.GRID and b in le.GRID:
            le.cut(a, ae, b, be)
            cut_reasons[(a, ae, b, be)] = reason

    _strip_sp_side_anchors()

    # Rim stubs only — do NOT auto-pair every named edge (that doubles gaps).
    for xy in ((2, 3), (2, 4)):
        if xy in le.GRID:
            le.an(xy, "LEFT")
    xs = [x for x, _ in le.GRID]
    for xy, tracks in le.GRID.items():
        if xy[0] >= max(xs) and "RIGHT" in le.cell_edges(tracks):
            le.an(xy, "RIGHT")

    mini = ET.Element("TRACKPLAN")
    for (x, y), tracks in sorted(le.GRID.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        mini.append(le.make_section(x, y, tracks))
    disc = le.load_disciplines()
    disc = {k: ("CTC" if v == "YARD" else v) for k, v in disc.items()}
    le.wire(mini, disc)
    for blk in mini.iter("BLOCK"):
        if blk.get("NAME"):
            blk.set("VISIBLE", "true")
            blk.set("DISCIPLINE", disc.get(blk.get("NAME") or "", "CTC"))

    _demote_non_plant_sp(mini)
    # After demote recreates BLOCKs — apply K-1/K-2 (etc.) station paint last.
    ctc._apply_station_labels(mini)
    wired = {(int(s.get("X")), int(s.get("Y"))): s for s in mini.findall("SECTION")}
    for xy, wsec in wired.items():
        live = secs[xy]
        _clear_edges(live)
        for e in wsec.findall("SEC_EDGE"):
            live.append(e)
    _demote_non_plant_sp(tp)

    after = {xy: tuple(_tracks(s)) for xy, s in secs.items()}
    if before != after:
        raise SystemExit("REFUSING TO WRITE: tracks diverged from SoR")

    errs = le.verify(tp)
    for e in errs:
        print(f"VERIFY FAIL: {e}", file=sys.stderr)

    # Live occupancy: same CATS block name on disjoint spans shares one sensor
    # (e.g. Main West @ Brick 100 and @ 111 → M2S200 / Block 2-1).
    gen.ensure_mqtt(root)
    gen.wire_occupancy(root, le.load_occupancy())
    # Turnout feedback: SELECTEDREPORT + ROUTECOMMAND read/write MQTT M2T.
    # Stock CATS only. launch_cats.sh gates turnout retain across load so
    # RREventManager is not killed by the PtsVitalLogic race.
    to_map = load_turnouts()
    n_to = wire_turnouts(tp, to_map)
    n_sel = sum(1 for _ in root.iter("SELECTEDREPORT"))
    for ops in root.iter("OPERATIONS"):
        ops.set("CONNECT", "true")

    sigs = _signal_list()
    print(f"signal defs: {len(sigs)}")
    placed_sigs = _apply_signals(tp, sigs)
    _sync_sor_signals(SOR)

    # STATION paint last (occupancy/signals may recreate BLOCKs). Default
    # STATION=NAME, then overlay K-1/K-2 etc. from STATION_LABEL.
    for blk in tp.iter("BLOCK"):
        if blk.get("NAME"):
            blk.set("STATION", blk.get("NAME"))
            blk.set("VISIBLE", "true")
    ctc._apply_station_labels(tp)

    print(f"explicit cuts: {len(cut_reasons)}")
    for (a, ae, b, be), reason in cut_reasons.items():
        print(f"  {a} {ae} | {b} {be}  — {reason}")

    _report_gaps(tp)

    ET.indent(root, space="  ")
    for dest in (SRC, ACTIVE):
        ET.ElementTree(root).write(dest, encoding="UTF-8", xml_declaration=True)
        print(f"wrote {dest.relative_to(ROOT)}")

    named = sorted({b.get("NAME") for b in tp.iter("BLOCK") if b.get("NAME")})
    n_occ = sum(
        1
        for b in root.iter("BLOCK")
        if b.get("NAME") and b.find("OCCUPIEDSPEC") is not None
    )
    mw = [
        b
        for b in root.iter("BLOCK")
        if b.get("NAME") == "Main West" and b.find("OCCUPIEDSPEC") is not None
    ]
    print(
        f"plants={len(le.PLANTS)} named={len(named)} verify={len(errs)} "
        f"tracks=SoR MQTT {n_occ}/{len(named)} MainWest×{len(mw)}→M2S200 "
        f"turnouts={n_to} SELECTEDREPORT={n_sel} signals={len(placed_sigs)}"
    )
    for s in placed_sigs:
        print(f"  signal {s}")

    subprocess.run(
        [sys.executable, str(ROOT / "cats/scripts/render_cats_panel.py"), str(SRC), str(SHOT)],
        check=False,
    )
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(wire())
