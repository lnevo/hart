#!/usr/bin/env python3
"""Assign Digicon blocks onto West Yard SoR — edges only, no cell edits.

SoR: cats/panels/sheets/HART_sheet_West_Yard_SOR.xml
  Geometry + SEC_NAME only (Designer-safe). Do not put Digicon BLOCK/SP/
  SECSIGNAL back into SoR — that crashes Designer. Designer working copy is
  HART_sheet_West_Yard2.xml; wire also publishes the active ops panel
  HART_sheet_West_Yard.xml plus HART_Master.xml / HART_Master_ABS.xml
  (launch_cats.sh default is HART_Master.xml).

Rules (cats/docs/CATS_SOURCE_PAINT.md):
  - Blocks flow through SWITCHPOINTS (plain→SP). Do not cut the plant throat.
  - Each BLK↔BLK pair is a visible rail gap in CATS — keep cuts minimal.
  - Name OS on the approach cell (same region as the plant).

    python3 cats/scripts/wire_hart_sheet_west_yard2.py
"""

from __future__ import annotations

import csv
import re
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
MASTER = ROOT / "cats/panels/sheets/HART_Master.xml"
MASTER_ABS = ROOT / "cats/panels/sheets/HART_Master_ABS.xml"
SHOT = ROOT / "cats/screenshots/sheets/HART_sheet_West_Yard2.png"
TURNOUT_CSV = ROOT / "cats/data/turnout_bindings.csv"
HART_PANEL = ROOT / "jmri/layouts/hart/output/hart_prod.xml"

# Control-point SEC_NAME titles → yellow FONT_CP (Java RGB -256 = #FFFF00).
# Values: display NAME + LOC_NAME (None = leave Designer placement).
CP_LABEL_STYLE: dict[str, tuple[str, str | None]] = {
    "brick": ("BRICK", None),  # Designer places LOWCENT
    "plane": ("PLANE", None),
    "barn": ("BARN", None),
    "princess": ("PRINCESS", None),
    "east end": ("EAST END", None),
}
CP_LABEL_NAMES = frozenset(CP_LABEL_STYLE)
# Area titles (not yellow CP font) forced to ALL CAPS / placement.
AREA_LABEL_STYLE: dict[str, tuple[str, str | None]] = {
    "west yard": ("WEST YARD", None),
    "south yard": ("SOUTH YARD", None),
}
FONT_CP_KEY = "FONT_CP"
FONT_CP_YELLOW = "-256"  # opaque yellow

# SoR plant cells (tracks unchanged). 111b mate has tracks but no Designer SP.
# Second field = NORMAL route among non-points legs (not the SP edge).
# Digicon polarity: NORMAL leg = JMRI CLOSED (close); other = THROWN (throw).
# Dispatcher tip SoR (confirmed):
#   112 THROWN = BOTTOM Barn; CLOSED = LEFT through OS110 / S-1
#   114 THROWN = BOTTOM McKeesport (default); CLOSED = RIGHT K-2
#   115 THROWN = TOP Rocks; CLOSED = RIGHT K-1 (good — leave alone)
# SEL+CMD always share polarity. Wrong frog → flip that one PLANTS NORMAL only.
# Coords match Designer SoR after user_0125 promote (≈ dx=-1,dy=-1; Brick tip compressed).
# NORMAL = continuing/CLOSED leg among non-points edges (must match SoR ROUTEINFO).
PLANTS: dict[tuple[int, int], tuple[str, str, str]] = {
    # Brick/WY on y=3; shaft (7,4–6) into Plane tip (8,7).
    (5, 3): ("OS 101 (Brick)", "LEFT", "TOL38"),
    (7, 3): ("OS 100 (Brick)", "LEFT", "TOL3"),
    (8, 7): ("OS 102 (Plane)", "BOTTOM", "TOL42"),
    (13, 7): ("OS 117 (West Yard)", "LEFT", "TO117"),
    (13, 8): ("OS 117b (West Yard)", "RIGHT", "TO117"),
    (15, 6): ("OS 119 (West Yard)", "LEFT", "TO10"),
    (17, 6): ("OS 118 (West Yard)", "LEFT", "TO11"),
    (18, 7): ("OS 116 (West Yard)", "LEFT", "TO1"),
    (21, 7): ("OS 103 (South Yard)", "RIGHT", "TOR14"),
    (22, 8): ("OS 104 (South Yard)", "BOTTOM", "TOL15"),
    (23, 9): ("OS 105 (South Yard)", "BOTTOM", "TOL17"),
    (24, 10): ("OS 106 (South Yard)", "BOTTOM", "TOL19"),
    (28, 10): ("OS 107 (East End)", "BOTTOM", "TOR11"),
    (29, 9): ("OS 108 (East End)", "BOTTOM", "TOR9"),
    (30, 8): ("OS 109 (East End)", "BOTTOM", "TOR7"),
    (31, 7): ("OS 110 (East End)", "LEFT", "TOL6"),
    (33, 7): ("OS 112 (East End)", "LEFT", "TOL23"),
    (29, 6): ("OS 111a (East End)", "RIGHT", "TO111"),
    (29, 7): ("OS 111b (East End)", "LEFT", "TO111"),
    (38, 6): ("OS 113b (Princess)", "LEFT", "TO113"),
    (38, 7): ("OS 113a (Princess)", "RIGHT", "TO113"),
    (42, 6): ("OS 115 (Princess)", "RIGHT", "TOL29"),
    (42, 7): ("OS 114 (Princess)", "RIGHT", "TOR36"),
}

# Named rim / approach / tip edges — only cut faces (interior stays plain).
# Gap style: plain within a block; cut only at OS bounds (no same-name BLK↔BLK).
ANCHORS: list[tuple[int, int, str, str]] = [
    # Brick / WY — W-1/W-2 dead-end spurs (Joins unchecked on west faces).
    # Digicon gaps: spur tip | mid-spur cut | anon lamp mate | OS101 lamp | plant.
    # Same block name both sides of spur-end cut (like Yard T9 mid-spur).
    (2, 3, "LEFT", "West Yard 1"),
    (2, 3, "RIGHT", "West Yard 1"),
    (3, 3, "LEFT", "West Yard 1"),
    (4, 3, "LEFT", "OS 101 (Brick)"),
    (6, 3, "RIGHT", "OS 101 (Brick)"),
    (2, 4, "LEFT", "West Yard 2"),
    (2, 4, "RIGHT", "West Yard 2"),
    (3, 4, "LEFT", "West Yard 2"),
    (4, 4, "LEFT", "OS 101 (Brick)"),
    (7, 3, "LEFT", "OS 100 (Brick)"),
    (7, 3, "BOTTOM", "OS 100 (Brick)"),
    (8, 3, "RIGHT", "OS 100 (Brick)"),
    # Main West: Brick tip → SE stair → EE
    (9, 3, "LEFT", "Main West"),
    (27, 6, "RIGHT", "Main West"),
    # Main West Brick–Plane vertical into Plane
    (7, 4, "TOP", "Main West Brick–Plane"),
    (7, 6, "BOTTOM", "Main West Brick–Plane"),
    (7, 7, "TOP", "OS 102 (Plane)"),
    # Plane: name OS on shaft approach only — floods through plant SP. Do NOT
    # name (9,8) BOTTOM/(9,9) TOP (extra frog Digicon seam). East lamps on cuts.
    (9, 7, "RIGHT", "OS 102 (Plane)"),
    (10, 7, "LEFT", "Yard T1"),
    (11, 7, "RIGHT", "Yard T1"),
    (12, 7, "LEFT", "OS 117 (West Yard)"),
    (9, 8, "RIGHT", "OS 102 (Plane)"),
    (10, 8, "LEFT", "East Main Ext"),
    (11, 8, "RIGHT", "East Main Ext"),
    (12, 8, "LEFT", "OS 117b (West Yard)"),
    # Barn 117 / 117b (plants at 14,8 / 14,9)
    (13, 7, "BOTTOM", "OS 117 (West Yard)"),
    (14, 7, "RIGHT", "OS 117 (West Yard)"),
    (15, 7, "LEFT", "Yard T6"),
    (13, 8, "TOP", "OS 117b (West Yard)"),
    (14, 8, "RIGHT", "OS 117b (West Yard)"),
    (15, 8, "LEFT", "Main East"),
    # ET: Designer mid-spur cuts (not at plant throat — OS floods into 118/119)
    (12, 6, "LEFT", "Yard T9"),
    (13, 6, "RIGHT", "Yard T9"),
    (14, 6, "LEFT", "OS 119 (West Yard)"),
    # OS119 plant: approach names flood through SP — no plant-edge names (avoids
    # throat Digicon seams + R4 vs plain ET stubs).
    (16, 6, "RIGHT", "OS 119 (West Yard)"),
    (12, 5, "LEFT", "Yard T10"),
    (13, 5, "RIGHT", "Yard T10"),
    (14, 5, "LEFT", "OS 119 (West Yard)"),
    (12, 4, "LEFT", "Yard T11"),
    (14, 4, "RIGHT", "Yard T11"),
    (15, 4, "LEFT", "OS 118 (West Yard)"),
    (16, 6, "LEFT", "OS 118 (West Yard)"),
    (17, 6, "LEFT", "OS 118 (West Yard)"),
    (18, 6, "BOTTOM", "OS 118 (West Yard)"),
    (17, 7, "RIGHT", "Yard T6"),
    (18, 7, "TOP", "OS 116 (West Yard)"),
    (18, 7, "LEFT", "OS 116 (West Yard)"),
    (19, 7, "RIGHT", "OS 116 (West Yard)"),
    # South Yard (plants shifted +1)
    (20, 7, "LEFT", "OS 103 (South Yard)"),
    (21, 7, "RIGHT", "OS 103 (South Yard)"),
    (22, 7, "LEFT", "Yard Track 1"),
    (22, 8, "RIGHT", "OS 104 (South Yard)"),
    (23, 8, "LEFT", "Yard Track 2"),
    (23, 9, "RIGHT", "OS 105 (South Yard)"),
    (24, 9, "LEFT", "Yard Track 3"),
    (24, 10, "RIGHT", "OS 106 (South Yard)"),
    (25, 10, "LEFT", "Yard Track 4"),
    (24, 10, "BOTTOM", "OS 106 (South Yard)"),
    (24, 11, "TOP", "Yard Track 5"),
    # EE 111 / 110 / 112 (plants at 30,7/30,8 / 32,8 / 34,8)
    (28, 6, "LEFT", "OS 111a (East End)"),
    (29, 6, "BOTTOM", "OS 111a (East End)"),
    (30, 6, "RIGHT", "OS 111a (East End)"),
    (31, 6, "LEFT", "West Main Ext"),
    (27, 7, "RIGHT", "Yard Track 1"),
    (28, 7, "LEFT", "OS 111b (East End)"),
    (29, 7, "TOP", "OS 111b (East End)"),
    (30, 7, "RIGHT", "OS 111b (East End)"),
    (31, 7, "LEFT", "OS 110 (East End)"),
    (31, 7, "BOTTOM", "OS 110 (East End)"),
    (32, 7, "RIGHT", "OS 110 (East End)"),
    (30, 8, "LEFT", "OS 109 (East End)"),
    (29, 9, "LEFT", "OS 108 (East End)"),
    (28, 10, "LEFT", "OS 107 (East End)"),
    (33, 7, "LEFT", "OS 112 (East End)"),
    (34, 7, "RIGHT", "OS 112 (East End)"),
    # 112 south lamp on slash face (34,9) LEFT — continuous (33,9)↔(33,10) Main East
    (33, 8, "LEFT", "OS 112 (East End)"),
    (32, 8, "RIGHT", "Main East"),
    (35, 7, "LEFT", "East Lead"),
    (36, 7, "RIGHT", "East Lead"),
    (37, 7, "LEFT", "OS 113a (Princess)"),
    (37, 7, "RIGHT", "OS 113a (Princess)"),
    (29, 8, "RIGHT", "Yard Track 2"),
    (28, 9, "RIGHT", "Yard Track 3"),
    (27, 10, "RIGHT", "Yard Track 4"),
    # Princess
    (36, 6, "RIGHT", "West Main Ext"),
    (37, 6, "LEFT", "OS 113b (Princess)"),
    (38, 6, "BOTTOM", "OS 113b (Princess)"),
    (39, 6, "RIGHT", "OS 113b (Princess)"),
    (40, 6, "LEFT", "OS 115 (Princess)"),
    (38, 7, "LEFT", "OS 113a (Princess)"),
    (38, 7, "TOP", "OS 113a (Princess)"),
    (39, 7, "RIGHT", "OS 113a (Princess)"),
    (40, 7, "LEFT", "OS 114 (Princess)"),
    # K-2 continuous plant→(44,8); OS on approach floods through SP.
    # Cut only at McKeesport lamp — never mid-K-2.
    (43, 8, "RIGHT", "OS 114 (Princess)"),
    (44, 8, "LEFT", "McKeesport"),
    (45, 7, "TOP", "McKeesport"),
    # K-1 continuous plant→(44,7); cut only at Rocks lamp — never mid-K-1.
    (43, 5, "RIGHT", "OS 115 (Princess)"),
    (44, 5, "LEFT", "McKees Rocks"),
    (45, 6, "BOTTOM", "McKees Rocks"),
]

CUTS: list[tuple[tuple[int, int], str, tuple[int, int], str, str]] = [
    # W-1/W-2: Joins unchecked on spur left/west faces (Designer "Joins to adjacent").
    # Digicon encodes that as BLK↔BLK cuts — spur end | anon buffer | OS101 lamp.
    ((2, 3), "RIGHT", (3, 3), "LEFT", "W-1 spur end (no west join)"),
    ((2, 4), "RIGHT", (3, 4), "LEFT", "W-2 spur end (no west join)"),
    ((3, 3), "RIGHT", (4, 3), "LEFT", "W-1 west lamp"),
    ((3, 4), "RIGHT", (4, 4), "LEFT", "W-2 west lamp"),
    ((6, 3), "RIGHT", (7, 3), "LEFT", "OS101 tip | OS100"),
    ((7, 3), "BOTTOM", (7, 4), "TOP", "OS100 | Main West Brick–Plane"),
    ((7, 6), "BOTTOM", (7, 7), "TOP", "Main West Brick–Plane | OS102"),
    ((8, 3), "RIGHT", (9, 3), "LEFT", "OS100 tip | Main West"),
    ((9, 7), "RIGHT", (10, 7), "LEFT", "OS102 | Yard T1"),
    ((9, 8), "RIGHT", (10, 8), "LEFT", "OS102 south | East Main Ext"),
    ((11, 8), "RIGHT", (12, 8), "LEFT", "East Main Ext | OS117b"),
    ((11, 7), "RIGHT", (12, 7), "LEFT", "Yard T1 | OS117"),
    ((14, 7), "RIGHT", (15, 7), "LEFT", "OS117 tip | Yard T6"),
    ((13, 7), "BOTTOM", (13, 8), "TOP", "OS117 | OS117b diamond"),
    ((14, 8), "RIGHT", (15, 8), "LEFT", "OS117b | Main East"),
    # ET mid-spur (Designer) — continuous into OS118/119 throats
    ((13, 6), "RIGHT", (14, 6), "LEFT", "Yard T9 mid"),
    ((13, 5), "RIGHT", (14, 5), "LEFT", "Yard T10 mid"),
    ((14, 4), "RIGHT", (15, 4), "LEFT", "Yard T11 mid"),
    ((16, 6), "RIGHT", (17, 6), "LEFT", "OS119 tip | OS118"),
    ((18, 6), "BOTTOM", (18, 7), "TOP", "OS118 | OS116"),
    ((17, 7), "RIGHT", (18, 7), "LEFT", "Yard T6 | OS116"),
    ((19, 7), "RIGHT", (20, 7), "LEFT", "OS116 tip | OS103 tip"),
    ((21, 7), "RIGHT", (22, 7), "LEFT", "OS103 | Yard Track 1 / S-1"),
    ((21, 7), "BOTTOM", (21, 8), "TOP", "OS103 spine"),
    ((22, 8), "RIGHT", (23, 8), "LEFT", "OS104 | Yard Track 2"),
    ((22, 8), "BOTTOM", (22, 9), "TOP", "OS104 spine"),
    ((23, 9), "RIGHT", (24, 9), "LEFT", "OS105 | Yard Track 3"),
    ((23, 9), "BOTTOM", (23, 10), "TOP", "OS105 spine"),
    ((24, 10), "RIGHT", (25, 10), "LEFT", "OS106 | Yard Track 4"),
    ((24, 10), "BOTTOM", (24, 11), "TOP", "OS106 | Yard Track 5"),
    ((27, 6), "RIGHT", (28, 6), "LEFT", "Main West | OS111a tip"),
    ((30, 6), "RIGHT", (31, 6), "LEFT", "OS111a | West Main Ext"),
    ((29, 6), "BOTTOM", (29, 7), "TOP", "OS111a | OS111b diamond"),
    ((27, 7), "RIGHT", (28, 7), "LEFT", "YT1/S-1 | OS111b"),
    ((30, 7), "RIGHT", (31, 7), "LEFT", "OS111b tip | OS110"),
    ((31, 7), "BOTTOM", (31, 8), "TOP", "OS110 spine"),
    ((29, 8), "RIGHT", (30, 8), "LEFT", "OS109 approach"),
    ((30, 8), "BOTTOM", (30, 9), "TOP", "OS109 spine"),
    ((28, 9), "RIGHT", (29, 9), "LEFT", "OS108 approach"),
    ((29, 9), "BOTTOM", (29, 10), "TOP", "OS108 spine"),
    ((27, 10), "RIGHT", (28, 10), "LEFT", "OS107 approach"),
    ((28, 10), "BOTTOM", (28, 11), "TOP", "OS107 spine"),
    ((32, 7), "RIGHT", (33, 7), "LEFT", "OS110 tip | OS112"),
    ((34, 7), "RIGHT", (35, 7), "LEFT", "OS112 tip | East Lead"),
    ((36, 7), "RIGHT", (37, 7), "LEFT", "East Lead | OS113a tip"),
    ((32, 8), "RIGHT", (33, 8), "LEFT", "OS112 south lamp"),
    ((36, 6), "RIGHT", (37, 6), "LEFT", "WME | OS113b"),
    ((38, 6), "BOTTOM", (38, 7), "TOP", "OS113b | OS113a diamond"),
    ((39, 7), "RIGHT", (40, 7), "LEFT", "OS113a | OS114 approach"),
    ((39, 6), "RIGHT", (40, 6), "LEFT", "OS113b tip | OS115"),
    ((43, 5), "RIGHT", (44, 5), "LEFT", "OS115 | McKees Rocks"),
    ((43, 8), "RIGHT", (44, 8), "LEFT", "OS114 | McKeesport"),
    ((45, 6), "BOTTOM", (45, 7), "TOP", "McKees Rocks | McKeesport"),
]

# Panel-lamp NX targets: (x,y,edge) → (name, pantype, loc, orient).
# Must sit on a BLOCK edge (never SP / plain). LAMP1=yard · 2=main/CP · 3=Princess exits.


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


def wire_turnouts(
    tp: ET.Element,
    turnout_by_ident: dict[str, tuple[str, str]],
    plants: dict[tuple[int, int], tuple[str, str, str]] | None = None,
) -> int:
    """Bind SELECTEDREPORT + ROUTECOMMAND on each plant SWITCHPOINTS.

    NORMAL route ↔ JMRI CLOSED (close); other leg ↔ THROWN (throw).
    SELECTEDREPORT and ROUTECOMMAND must use the same polarity — remapping
    only the report (to chase a bad MQTT retain) reverses Digicon commands.

    ``plants`` defaults to module PLANTS (row 1). Pass Class-I / sidecar
    plant maps (same tip idents) so both bands share M2T and frogs sync.
    """
    plant_map = PLANTS if plants is None else plants
    secs = {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in tp.findall("SECTION")
        if s.find("TRACKGROUP") is not None
    }
    n = 0
    for xy, (_os, normal, ident) in plant_map.items():
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
# SoR is geometry-only (Designer). Lamps live on West_Yard2 named cut faces.
#
# SIGPANTYPE = panel head count (CATS AspectMap templates):
#   LAMP1 / single — yard / stub / one-head dwarf (Stop / Approach / Clear)
#   LAMP2 / double — main / CP (adds Medium/Slow / diverging speed aspects)
#   LAMP3 / triple — high-speed plant exits (full Clear/Approach/Restricting ladder)
SIGNAL_DEFS: dict[tuple[int, int, str], tuple] = {
    # Yard stubs — single head
    (4, 3, "LEFT"): ("Brick West Yard 1", "LAMP1", "LOWLEFT", "RIGHT"),
    (4, 4, "LEFT"): ("Brick West Yard 2", "LAMP1", "LOWLEFT", "RIGHT"),
    # Brick main — JMRI MQTT mast 464 (Brick East Main West); Digicon 2-lamp, lower off for now
    (8, 3, "RIGHT"): ("Brick East Main West", "LAMP2", "LOWLEFT", "LEFT", "aar-single"),
    (43, 5, "RIGHT"): ("Princess North McKees Rocks", "LAMP3", "LOWLEFT", "LEFT"),
    (28, 6, "LEFT"): ("East End West Main West", "LAMP2", "LOWLEFT", "RIGHT"),
    (30, 6, "RIGHT"): ("East End East OS 111a", "LAMP2", "LOWLEFT", "LEFT"),
    (37, 6, "LEFT"): ("Princess West OS 113b", "LAMP2", "LOWLEFT", "RIGHT"),
    (9, 7, "RIGHT"): ("Plane East OS 102", "LAMP2", "LOWLEFT", "LEFT"),
    (12, 7, "LEFT"): ("West Yard West OS 117", "LAMP2", "LOWLEFT", "RIGHT"),
    (14, 7, "RIGHT"): ("West Yard East Yard T6", "LAMP1", "LOWLEFT", "LEFT"),
    (28, 7, "LEFT"): ("East End West Yard Track 1", "LAMP1", "LOWLEFT", "RIGHT"),
    (34, 7, "RIGHT"): ("East End East Lead", "LAMP2", "LOWRIGHT", "LEFT"),
    (37, 7, "LEFT"): ("Princess West OS 113a", "LAMP2", "LOWLEFT", "RIGHT"),
    (31, 7, "BOTTOM"): ("East End South OS 110", "LAMP1", "UPLEFT", "RIGHT"),
    # Plane normal route (SW102 closed → East Main Ext): JMRI heads IH465/IH466 + cats-virtual-2
    (9, 8, "RIGHT"): ("Plane East East Main Ext", "LAMP2", "LOWLEFT", "LEFT"),
    (12, 8, "LEFT"): ("West Yard West East Main Ext", "LAMP2", "LOWLEFT", "RIGHT"),
    (14, 8, "RIGHT"): ("West Yard East OS 117b", "LAMP2", "LOWLEFT", "LEFT"),
    (33, 8, "LEFT"): ("East End South OS 112", "LAMP2", "RIGHTLOW", "RIGHT"),
    (43, 8, "RIGHT"): ("Princess South McKeesport", "LAMP3", "LOWLEFT", "LEFT"),
}

_PANTYPE_PHYS = {"LAMP1": "single", "LAMP2": "double", "LAMP3": "triple"}

# Digicon AppearanceKey → AAR Clear/Approach/Stop for MQTT mast 464 (Brick East Main West).
# Must stay in every wired sheet — missing template + PHYSIGNAL=aar-single NPEs CATS panel load.
_AAR_SINGLE_ATTRS = {
    "TEMPLATEKIND": "Lamp",
    "TEMPLATEHEADS": "2",
    "TEMPLATENAME": "aar-single",
    "R281": "Clear",
    "R281B": "Clear",
    "R282": "Clear",
    "R284": "Clear",
    "RES_NORM": "Approach",
    "ADV_NORM": "Clear",
    "R285": "Approach",
    "R281C": "Clear",
    "C412": "Clear",
    "C413": "Clear",
    "C414": "Clear",
    "RES_LIM": "Approach",
    "ADV_LIM": "Clear",
    "R281D": "Approach",
    "R283": "Clear",
    "C417": "Clear",
    "R283A": "Clear",
    "R283B": "Clear",
    "RES_MED": "Approach",
    "ADV_MED": "Clear",
    "R286": "Approach",
    "R287": "Clear",
    "C422": "Clear",
    "C423": "Clear",
    "C424": "Clear",
    "RES_SLO": "Approach",
    "ADV_SLO": "Clear",
    "R288": "Approach",
    "R291": "Stop",
    "R292": "Stop",
}
_AAR_SINGLE_ASPECTMAP = (
    'R281="green|off" R281B="green|off" R282="green|off" R284="green|off" '
    'RES_NORM="yellow|off" ADV_NORM="green|off" R285="yellow|off" R281C="green|off" '
    'C412="green|off" C413="green|off" C414="green|off" RES_LIM="yellow|off" '
    'ADV_LIM="green|off" R281D="yellow|off" R283="green|off" C417="green|off" '
    'R283A="green|off" R283B="green|off" RES_MED="yellow|off" ADV_MED="green|off" '
    'R286="yellow|off" R287="green|off" C422="green|off" C423="green|off" '
    'C424="green|off" RES_SLO="yellow|off" ADV_SLO="green|off" R288="yellow|off" '
    'R292="red|off" R291="red|off"'
)


def _ensure_aar_single_template(root: ET.Element) -> None:
    """Insert/refresh aar-single SIGNALTEMPLATE (SoR copies lack it)."""
    existing = [
        t
        for t in root.findall("SIGNALTEMPLATE")
        if t.get("TEMPLATENAME") == "aar-single"
    ]
    for t in existing:
        root.remove(t)
    el = ET.Element("SIGNALTEMPLATE", _AAR_SINGLE_ATTRS)
    am = ET.SubElement(el, "ASPECTMAP")
    for k, v in re.findall(r'(\w+)="([^"]*)"', _AAR_SINGLE_ASPECTMAP):
        am.set(k, v)
    # Place after "single" template if present, else before first SIGNALTEMPLATE
    singles = [
        t for t in root.findall("SIGNALTEMPLATE") if t.get("TEMPLATENAME") == "single"
    ]
    if singles:
        idx = list(root).index(singles[0]) + 1
        root.insert(idx, el)
    else:
        # before first TRACKPLAN / after counters
        for i, child in enumerate(list(root)):
            if child.tag in ("SIGNALTEMPLATE", "TRACKPLAN", "TRAINSTORE"):
                root.insert(i, el)
                break
        else:
            root.append(el)



def _signal_list() -> list[tuple[int, int, str, str, str, str, str]]:
    """(x, y, edge, name, loc, orient, pantype) from SIGNAL_DEFS."""
    out: list[tuple[int, int, str, str, str, str, str]] = []
    for (x, y, edge), defn in sorted(
        SIGNAL_DEFS.items(), key=lambda kv: (kv[0][1], kv[0][0], kv[0][2])
    ):
        name, pantype, loc, orient = defn[0], defn[1], defn[2], defn[3]
        out.append((x, y, edge, name, loc, orient, pantype))
    return out


def _phys_for(defn: tuple, pantype: str) -> str:
    """Optional 5th SIGNAL_DEFS field overrides PHYSIGNAL template name."""
    if len(defn) >= 5 and defn[4]:
        return str(defn[4])
    return _PANTYPE_PHYS.get(pantype, "single")


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

    by_key = {k: v for k, v in SIGNAL_DEFS.items()}
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
        phys_name = _phys_for(by_key[(x, y, edge)], pantype)
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
    """Deprecated: do not write Digicon edges/signals into SoR.

    Designer crashes on Digicon BLOCK/SP/SECSIGNAL payloads. SoR stays
    geometry + SEC_NAME only; West_Yard2.xml is Designer; West_Yard.xml is ops.
    """
    return


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


def _sync_designer_labels_into_sor(designer: Path, sor: Path) -> int:
    """Copy SEC_NAME placements from Designer save into SoR (tracks untouched).

    Row-2 Class-I labels (y >= 14) are compose-owned — do not fold into SoR.
    """
    d_root = ET.parse(designer).getroot()
    s_root = ET.parse(sor).getroot()
    d_tp = d_root.find("TRACKPLAN")
    s_tp = s_root.find("TRACKPLAN")
    assert d_tp is not None and s_tp is not None

    labels: dict[tuple[int, int], dict[str, str]] = {}
    for sec in d_tp.findall("SECTION"):
        y = int(sec.get("Y"))
        if y >= 14:
            continue
        sn = sec.find("SEC_NAME")
        if sn is None or not (sn.get("NAME") or "").strip():
            continue
        labels[(int(sec.get("X")), y)] = dict(sn.attrib)

    s_secs = {
        (int(s.get("X")), int(s.get("Y"))): s for s in s_tp.findall("SECTION")
    }
    for sec in list(s_tp.findall("SECTION")):
        xy = (int(sec.get("X")), int(sec.get("Y")))
        # Class-I row2 is compose-owned — strip from SoR entirely.
        if xy[1] >= 14:
            s_tp.remove(sec)
            s_secs.pop(xy, None)
            continue
        for old in list(sec.findall("SEC_NAME")):
            sec.remove(old)
        if sec.find("TRACKGROUP") is None and not list(sec):
            s_tp.remove(sec)
            s_secs.pop(xy, None)

    for (x, y), attrs in sorted(labels.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        sec = s_secs.get((x, y))
        if sec is None:
            sec = ET.SubElement(s_tp, "SECTION", {"X": str(x), "Y": str(y)})
            s_secs[(x, y)] = sec
        ET.SubElement(sec, "SEC_NAME", attrs)

    ET.indent(s_root, space="  ")
    ET.ElementTree(s_root).write(sor, encoding="UTF-8", xml_declaration=True)
    return len(labels)


def _ensure_cp_yellow_labels(root: ET.Element) -> list[str]:
    """Yellow FONT_CP for CP titles; enforce ALL-CAPS / LOW|UP placements."""
    defs = list(root.findall("FONTDEFINITION"))
    existing = {d.get("FONTKEY") for d in defs}
    if FONT_CP_KEY not in existing:
        # Insert after FONT_LABEL if present, else first among font defs.
        fd = ET.Element(
            "FONTDEFINITION",
            {
                "FONTKEY": FONT_CP_KEY,
                "FONTNAME": "Control Points",
                "FONTCOLOR": FONT_CP_YELLOW,
                "FONTSIZE": "11",
                "FONTSTYLE": "PLAIN",
            },
        )
        anchor = None
        for i, child in enumerate(list(root)):
            if child.tag == "FONTDEFINITION" and child.get("FONTKEY") == "FONT_LABEL":
                anchor = i
                break
        if anchor is not None:
            root.insert(anchor + 1, fd)
        else:
            root.insert(0, fd)

    painted: list[str] = []
    for sn in root.iter("SEC_NAME"):
        name = (sn.get("NAME") or "").strip()
        key = name.casefold()
        if key == "to princess":
            key = "princess"

        if key in AREA_LABEL_STYLE:
            new_name, loc = AREA_LABEL_STYLE[key]
            sn.set("NAME", new_name)
            if loc:
                sn.set("LOC_NAME", loc)
            painted.append(f"{new_name}@{sn.get('LOC_NAME')}")
            continue

        if key not in CP_LABEL_STYLE:
            continue
        new_name, loc = CP_LABEL_STYLE[key]
        sn.set("NAME", new_name)
        if loc:
            sn.set("LOC_NAME", loc)
        sn.set("FONT_NAME", FONT_CP_KEY)
        painted.append(f"{new_name}@{sn.get('LOC_NAME')}/{FONT_CP_KEY}")
    return painted


def wire() -> int:
    if not SOR.exists():
        print(f"MISSING SoR: {SOR}", file=sys.stderr)
        return 2

    # Designer SEC_NAME edits live on West_Yard2 — fold into SoR before copy.
    if SRC.exists():
        n_lab = _sync_designer_labels_into_sor(SRC, SOR)
        print(f"synced {n_lab} SEC_NAME labels Designer → SoR")

    # Fresh copy of SoR; we rebuild every SEC_EDGE (ignore any BLK already in SoR).
    shutil.copy2(SOR, SRC)
    root = ET.parse(SRC).getroot()
    _ensure_aar_single_template(root)
    painted = _ensure_cp_yellow_labels(root)
    if painted:
        print(f"CP yellow labels: {', '.join(painted)}")
    # Persist yellow font + CP FONT_NAME back into SoR (Designer-safe).
    sor_root = ET.parse(SOR).getroot()
    _ensure_cp_yellow_labels(sor_root)
    ET.indent(sor_root, space="  ")
    ET.ElementTree(sor_root).write(SOR, encoding="UTF-8", xml_declaration=True)

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

    # No west-rim BLK stubs — anonymous BLK with no neighbor crashes Digicon
    # SecEdge→AbstractTrackEdge during findBounds. WY1/WY2 are named at cuts.
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
    # Stock CATS + cats-pts-nullguard overlay. Launch does not touch MQTT retain.
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

    n_trains = gen.ensure_hart_trains(root)
    print(f"trains={n_trains} from {gen.HART_TRAINS_CSV.name}")

    print(f"explicit cuts: {len(cut_reasons)}")
    for (a, ae, b, be), reason in cut_reasons.items():
        print(f"  {a} {ae} | {b} {be}  — {reason}")

    _report_gaps(tp)

    ET.indent(root, space="  ")
    for dest in (SRC, ACTIVE, MASTER):
        ET.ElementTree(root).write(dest, encoding="UTF-8", xml_declaration=True)
        print(f"wrote {dest.relative_to(ROOT)}")

    # Open-house ABS copy: same geometry/wiring, DISCIPLINE=ABS on every block.
    abs_xml = dest.read_text(encoding="utf-8").replace(
        'DISCIPLINE="CTC"', 'DISCIPLINE="ABS"'
    )
    MASTER_ABS.write_text(abs_xml, encoding="utf-8")
    print(f"wrote {MASTER_ABS.relative_to(ROOT)} (ABS)")

    # Keep SoR train/job tables in sync (Designer-safe; no Digicon edges).
    sor_root = ET.parse(SOR).getroot()
    gen.ensure_hart_trains(sor_root)
    ET.indent(sor_root, space="  ")
    ET.ElementTree(sor_root).write(SOR, encoding="UTF-8", xml_declaration=True)

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
