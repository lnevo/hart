#!/usr/bin/env python3
"""Class-I station-map band under a frozen row-1 base (sidecar only).

Three streamlined Digicon panels sharing block names with row 1 (same MQTT):

  A  Main West → Brick → Plane → Barn
  B  West Lead → South Yard vertical ladder → East End
  C  Princess (113 / 115 / 114)

Reads the good row-1 ops panel; writes ONLY the Class-I sidecar.
Never overwrites HART_sheet_West_Yard.xml / West_Yard2.xml (ops / Designer).

Revert row-1: cats/panels/sheets/checkpoints/HART_sheet_West_Yard_good_row1.xml

    python3 cats/scripts/wire_hart_sheet_west_yard2.py
    python3 cats/scripts/compose_hart_sheet_west_yard2_classI_row2.py
    ./cats/scripts/launch_cats.sh cats/panels/sheets/HART_sheet_West_Yard2_classI.xml
"""

from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_hart_digicon_ctc as ctc  # noqa: E402
import build_hart_digicon_from_le as le  # noqa: E402
import jmri_to_cats_digicon as gen  # noqa: E402
import wire_hart_sheet_west_yard2 as wy  # noqa: E402

# Frozen good row-1 base (checkpoint). Fall back to live ops if missing.
BASE = ROOT / "cats/panels/sheets/checkpoints/HART_sheet_West_Yard_good_row1.xml"
BASE_FALLBACK = ROOT / "cats/panels/sheets/HART_sheet_West_Yard.xml"
OUT = ROOT / "cats/panels/sheets/HART_sheet_West_Yard2_classI.xml"
SHOT = ROOT / "cats/screenshots/sheets/HART_sheet_West_Yard2_classI.png"

# Below live sheet (Designer y=2..12). Gap row 13 for breathing room.
ROW2_Y0 = 14
Y_BANNER = 14
Y0 = 15  # first track row of Class-I band

# Panel X ranges (gap columns between)
AX0, AX1 = 2, 18  # room for Plane/Barn tip spacers + lamps
BX0, BX1 = 20, 40  # wider for EE vertical ladder + 110/112 throat
CX0, CX1 = 42, 54


def _H(x0: int, x1: int, y: int) -> None:
    for x in range(x0, x1 + 1):
        le.H((x, y))


ROW2_LABELS: list[tuple] = []
ROW2_SIGNALS: list[tuple[int, int, str, str, str, str, str]] = []


def _label(x: int, y: int, text: str, *, loc: str = "LOWCENT", font: str = "FONT_LABEL") -> None:
    ROW2_LABELS.append((x, y, text, loc, font))


def _sig(
    x: int,
    y: int,
    edge: str,
    name: str,
    pantype: str,
    loc: str,
    orient: str,
) -> None:
    """Queue a row-2 panel lamp (same names/heads as row-1 SIGNAL_DEFS)."""
    ROW2_SIGNALS.append((x, y, edge, name, pantype, loc, orient))


def _build_panel_a() -> None:
    """Main West → Brick (101/100) → Plane (102) → Barn (117)."""
    H, plant, nm, cut, an = le.H, le.plant, le.nm, le.cut, le.an
    y_mw, y_wl, y_me = Y0, Y0 + 1, Y0 + 2

    # --- Main West: W-1 → 101 → 100 → east ---
    # Match row-1 Brick: H+LOWERSLASH (points RIGHT, NORMAL LEFT).
    _H(AX0, AX0 + 1, y_mw)
    nm((AX0, y_mw), "LEFT", "West Yard 1")
    cut((AX0 + 1, y_mw), "RIGHT", (AX0 + 2, y_mw), "LEFT")
    H((AX0 + 2, y_mw))
    nm((AX0 + 2, y_mw), "LEFT", "OS 101 (Brick)")
    plant((AX0 + 3, y_mw), ["HORIZONTAL", "LOWERSLASH"], "OS 101 (Brick)", "LEFT", "TOL38")
    H((AX0 + 4, y_mw))
    nm((AX0 + 4, y_mw), "RIGHT", "OS 101 (Brick)")
    cut((AX0 + 4, y_mw), "RIGHT", (AX0 + 5, y_mw), "LEFT")
    H((AX0 + 5, y_mw))
    nm((AX0 + 5, y_mw), "LEFT", "OS 100 (Brick)")
    plant((AX0 + 6, y_mw), ["HORIZONTAL", "LOWERSLASH"], "OS 100 (Brick)", "LEFT", "TOL3")
    H((AX0 + 7, y_mw))
    nm((AX0 + 7, y_mw), "RIGHT", "OS 100 (Brick)")
    cut((AX0 + 7, y_mw), "RIGHT", (AX0 + 8, y_mw), "LEFT")
    _H(AX0 + 8, AX1, y_mw)
    nm((AX0 + 8, y_mw), "LEFT", "Main West")
    an((AX1, y_mw), "RIGHT")
    _sig(AX0 + 2, y_mw, "LEFT", "Brick West West Yard 1", "LAMP1", "LOWLEFT", "RIGHT")
    _sig(AX0 + 7, y_mw, "RIGHT", "100L", "LAMP2", "LOWLEFT", "LEFT")

    # W-2 merges into 101 BOTTOM (LS frog) via UPPERSLASH stub.
    _H(AX0, AX0 + 2, y_wl)
    nm((AX0, y_wl), "LEFT", "West Yard 2")
    cut((AX0 + 2, y_wl), "RIGHT", (AX0 + 3, y_wl), "LEFT")
    le.GRID[(AX0 + 3, y_wl)] = ["UPPERSLASH"]
    nm((AX0 + 3, y_wl), "LEFT", "OS 101 (Brick)")
    _sig(AX0 + 3, y_wl, "LEFT", "Brick West West Yard 2", "LAMP1", "LOWLEFT", "RIGHT")

    # Brick diverge → Plane: 100 BOTTOM → UB elbow → Plane tip (H+LB, NORMAL BOTTOM).
    le.GRID[(AX0 + 6, y_wl)] = ["UPPERBACKSLASH"]
    nm((AX0 + 6, y_wl), "RIGHT", "Main West Brick–Plane")
    cut((AX0 + 6, y_wl), "RIGHT", (AX0 + 7, y_wl), "LEFT")
    H((AX0 + 7, y_wl))
    nm((AX0 + 7, y_wl), "LEFT", "OS 102 (Plane)")
    plant((AX0 + 8, y_wl), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 102 (Plane)", "BOTTOM", "TOL42")
    H((AX0 + 9, y_wl))
    nm((AX0 + 9, y_wl), "RIGHT", "OS 102 (Plane)")
    cut((AX0 + 9, y_wl), "RIGHT", (AX0 + 10, y_wl), "LEFT")
    _H(AX0 + 10, AX0 + 12, y_wl)
    nm((AX0 + 10, y_wl), "LEFT", "South Yard Scale")
    _sig(AX0 + 9, y_wl, "RIGHT", "102LA", "LAMP2", "LOWLEFT", "LEFT")
    # Main East peel under Plane — UB stub so Plane BOTTOM meets a TOP edge.
    le.GRID[(AX0 + 8, y_me)] = ["UPPERBACKSLASH"]
    nm((AX0 + 8, y_me), "RIGHT", "East Main Ext")
    cut((AX0 + 8, y_me), "RIGHT", (AX0 + 9, y_me), "LEFT")
    _H(AX0 + 9, AX0 + 12, y_me)
    nm((AX0 + 9, y_me), "LEFT", "East Main Ext")
    _sig(AX0 + 9, y_me, "LEFT", "102LB", "LAMP2", "LOWLEFT", "LEFT")

    # Barn 117/117b — row-1 `\` XO only (H+LOWERSLASH over H+UPPERSLASH).
    # Never cut on SWITCHPOINTS (plain→SP only).
    bx = AX0 + 14
    # South Yard Scale → 117 approach → plant (SP=RIGHT) → tip → South Yard West
    cut((AX0 + 12, y_wl), "RIGHT", (bx - 1, y_wl), "LEFT")
    H((bx - 1, y_wl))
    nm((bx - 1, y_wl), "LEFT", "OS 117 (Barn)")
    plant((bx, y_wl), ["HORIZONTAL", "LOWERSLASH"], "OS 117 (Barn)", "LEFT", "TO117")
    H((bx + 1, y_wl))
    nm((bx + 1, y_wl), "RIGHT", "OS 117 (Barn)")
    cut((bx + 1, y_wl), "RIGHT", (bx + 2, y_wl), "LEFT")
    _H(bx + 2, AX1, y_wl)
    nm((bx + 2, y_wl), "LEFT", "South Yard West")
    an((AX1, y_wl), "RIGHT")
    # EME → 117b approach → plant (SP=LEFT) → tip → Main East
    cut((AX0 + 12, y_me), "RIGHT", (bx - 1, y_me), "LEFT")
    H((bx - 1, y_me))
    nm((bx - 1, y_me), "LEFT", "OS 117b (Barn)")
    plant((bx, y_me), ["HORIZONTAL", "UPPERSLASH"], "OS 117b (Barn)", "RIGHT", "TO117")
    # Diamond between XO halves (BOTTOM/TOP are non-SP frog legs)
    cut((bx, y_wl), "BOTTOM", (bx, y_me), "TOP")
    H((bx + 1, y_me))
    nm((bx + 1, y_me), "RIGHT", "OS 117b (Barn)")
    cut((bx + 1, y_me), "RIGHT", (bx + 2, y_me), "LEFT")
    _H(bx + 2, AX1, y_me)
    nm((bx + 2, y_me), "LEFT", "Main East")
    an((AX1, y_me), "RIGHT")
    _sig(bx - 1, y_wl, "LEFT", "117RA", "LAMP2", "LOWLEFT", "RIGHT")
    _sig(bx + 1, y_wl, "RIGHT", "117LB", "LAMP1", "LOWLEFT", "LEFT")
    _sig(bx - 1, y_me, "LEFT", "117RB", "LAMP2", "LOWLEFT", "RIGHT")
    _sig(bx + 1, y_me, "RIGHT", "117LA", "LAMP2", "LOWLEFT", "LEFT")

    _label(AX0 + 3, Y_BANNER, "BRICK", loc="LOWCENT", font="FONT_CP")
    _label(AX0 + 8, Y_BANNER, "PLANE", loc="LOWCENT", font="FONT_CP")
    _label(bx, Y_BANNER, "BARN", loc="LOWCENT", font="FONT_CP")
    _label(AX0, y_mw, "MW", loc="UPLEFT")
    _label(AX0, y_wl, "W-2", loc="LOWLEFT")


def _build_panel_b() -> None:
    """South Yard vertical ladder + East End vertical ladder (Class-I).

    SY west spine and EE east spine are both vertical stacks (not the
    row-1 diagonal stair) — easier to read as station-map sketches.
    Digicon: never cut on SWITCHPOINTS; name OS on approach / non-SP leg.
    """
    H, plant, nm, cut, an = le.H, le.plant, le.nm, le.cut, le.an
    y_mw = Y0
    y_s1 = Y0 + 1
    y_s2 = Y0 + 2
    y_s3 = Y0 + 3
    y_s4 = Y0 + 4
    y_s5 = Y0 + 5

    lx = BX0 + 1  # SY plant column
    sx = lx + 1  # S-body start
    s_end = BX0 + 8  # S-body east (gap before EE)
    ee_app = s_end + 2  # EE west approach
    ee = ee_app + 1  # EE plant column (vertical ladder)
    ee_tip = ee + 1  # tip / South Yard East start

    # --- Main West → 111a → West Main Ext ---
    _H(BX0, ee_app - 1, y_mw)
    nm((BX0, y_mw), "LEFT", "Main West")
    cut((ee_app - 1, y_mw), "RIGHT", (ee_app, y_mw), "LEFT")
    H((ee_app, y_mw))
    nm((ee_app, y_mw), "LEFT", "OS 111a (East End)")
    plant((ee, y_mw), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 111a (East End)", "RIGHT", "TO111")
    H((ee_tip, y_mw))
    nm((ee_tip, y_mw), "RIGHT", "OS 111a (East End)")
    cut((ee_tip, y_mw), "RIGHT", (ee_tip + 1, y_mw), "LEFT")
    _H(ee_tip + 1, BX1, y_mw)
    nm((ee_tip + 1, y_mw), "LEFT", "West Main Ext")
    an((BX1, y_mw), "RIGHT")
    _sig(ee_app, y_mw, "LEFT", "111RA", "LAMP2", "LOWLEFT", "RIGHT")
    _sig(ee_tip, y_mw, "RIGHT", "111L", "LAMP2", "LOWLEFT", "LEFT")

    # --- South Yard West → 103 → S-1 ---
    _H(BX0, lx - 2, y_s1)
    nm((BX0, y_s1), "LEFT", "South Yard West")
    cut((lx - 2, y_s1), "RIGHT", (lx - 1, y_s1), "LEFT")
    H((lx - 1, y_s1))
    nm((lx - 1, y_s1), "LEFT", "OS 103 (South Yard)")
    plant((lx, y_s1), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 103 (South Yard)", "RIGHT", "TOR14")
    cut((lx, y_s1), "RIGHT", (sx, y_s1), "LEFT")
    # S-1 continuous into 111b approach (no dead-end gap at s_end).
    _H(sx, ee_app - 1, y_s1)
    nm((sx, y_s1), "LEFT", "South Yard 1")
    cut((ee_app - 1, y_s1), "RIGHT", (ee_app, y_s1), "LEFT")

    # --- 111b under 111a (same column) + S-1 into EE ---
    cut((ee, y_mw), "BOTTOM", (ee, y_s1), "TOP")
    H((ee_app, y_s1))
    nm((ee_app, y_s1), "LEFT", "OS 111b (East End)")
    plant((ee, y_s1), ["HORIZONTAL", "UPPERBACKSLASH"], "OS 111b (East End)", "LEFT", "TO111")
    H((ee_tip, y_s1))
    nm((ee_tip, y_s1), "RIGHT", "OS 111b (East End)")
    cut((ee_tip, y_s1), "RIGHT", (ee_tip + 1, y_s1), "LEFT")
    # 110 / 112 sit on S-1 row east of 111b tip — keep horizontal throat
    H((ee_tip + 1, y_s1))
    nm((ee_tip + 1, y_s1), "LEFT", "OS 110 (East End)")
    plant((ee_tip + 2, y_s1), ["HORIZONTAL", "LOWERSLASH"], "OS 110 (East End)", "LEFT", "TOL6")
    H((ee_tip + 3, y_s1))
    nm((ee_tip + 3, y_s1), "RIGHT", "OS 110 (East End)")
    cut((ee_tip + 3, y_s1), "RIGHT", (ee_tip + 4, y_s1), "LEFT")
    H((ee_tip + 4, y_s1))
    nm((ee_tip + 4, y_s1), "LEFT", "OS 112 (East End)")
    plant((ee_tip + 5, y_s1), ["HORIZONTAL", "LOWERSLASH"], "OS 112 (East End)", "LEFT", "TOL23")
    H((ee_tip + 6, y_s1))
    nm((ee_tip + 6, y_s1), "RIGHT", "OS 112 (East End)")
    cut((ee_tip + 6, y_s1), "RIGHT", (ee_tip + 7, y_s1), "LEFT")
    _H(ee_tip + 7, BX1, y_s1)
    nm((ee_tip + 7, y_s1), "LEFT", "South Yard East")
    an((BX1, y_s1), "RIGHT")
    _sig(ee_app, y_s1, "LEFT", "111RB", "LAMP1", "LOWLEFT", "RIGHT")
    _sig(ee_tip + 3, y_s1, "RIGHT", "110R", "LAMP1", "UPLEFT", "RIGHT")
    _sig(ee_tip + 6, y_s1, "RIGHT", "East End East South Yard East", "LAMP2", "LOWRIGHT", "LEFT")
    # 112 south lamp on slash face below plant
    le.GRID[(ee_tip + 5, y_s2)] = ["UPPERSLASH"]
    nm((ee_tip + 5, y_s2), "LEFT", "OS 112 (East End)")
    _sig(ee_tip + 5, y_s2, "LEFT", "112R", "LAMP2", "RIGHTLOW", "RIGHT")

    # --- SY + EE ladders ---
    # Vertical frog chain needs TOP↔BOTTOM: use V+LS (body east) / V+LB (body west).
    # Plain H+LB/H+LS stacks have no TOP and break Digicon routes between rows.
    ee_lad = ee_tip + 2  # under 110 column

    for yb, sy_os, sy_tip, body, ee_os, ee_tip_id in (
        (y_s2, "OS 104 (South Yard)", "TOL15", "South Yard 2", "OS 109 (East End)", "TOR7"),
        (y_s3, "OS 105 (South Yard)", "TOL17", "South Yard 3", "OS 108 (East End)", "TOR9"),
        (y_s4, "OS 106 (South Yard)", "TOL19", "South Yard 4", "OS 107 (East End)", "TOR11"),
    ):
        # SY: V+LS — SP BOTTOM, NORMAL RIGHT into yard body; TOP from plant above.
        plant((lx, yb), ["VERTICAL", "LOWERSLASH"], sy_os, "RIGHT", sy_tip)
        nm((lx, yb), "RIGHT", sy_os)
        cut((lx, yb), "RIGHT", (sx, yb), "LEFT")
        _H(sx, ee_lad - 1, yb)
        nm((sx, yb), "LEFT", body)
        # EE: V+LB — SP BOTTOM, NORMAL LEFT into S-body; TOP from plant above.
        plant((ee_lad, yb), ["VERTICAL", "LOWERBACKSLASH"], ee_os, "LEFT", ee_tip_id)
        nm((ee_lad, yb), "LEFT", ee_os)
        cut((ee_lad - 1, yb), "RIGHT", (ee_lad, yb), "LEFT")

    # S-5 into 106 BOTTOM and across into 107 BOTTOM.
    le.GRID[(lx, y_s5)] = ["UPPERBACKSLASH"]  # TOP↔RIGHT into body
    nm((lx, y_s5), "RIGHT", "South Yard 5")
    cut((lx, y_s5), "RIGHT", (sx, y_s5), "LEFT")
    _H(sx, ee_lad - 1, y_s5)
    nm((sx, y_s5), "LEFT", "South Yard 5")
    le.GRID[(ee_lad, y_s5)] = ["UPPERSLASH"]  # TOP↔LEFT under 107
    nm((ee_lad, y_s5), "LEFT", "South Yard 5")
    cut((ee_lad - 1, y_s5), "RIGHT", (ee_lad, y_s5), "LEFT")

    _label((sx + ee_lad) // 2, Y_BANNER, "SOUTH YARD", loc="LOWCENT", font="FONT_CP")
    _label(ee_lad, Y_BANNER, "EAST END", loc="LOWCENT", font="FONT_CP")
    for yb, lab in (
        (y_s1, "S-1"),
        (y_s2, "S-2"),
        (y_s3, "S-3"),
        (y_s4, "S-4"),
        (y_s5, "S-5"),
    ):
        _label(sx + 2, yb, lab, loc="LOWCENT")


def _build_panel_c() -> None:
    """Princess 113 XO (vertically aligned) + 115/114 to K-1/K-2.

    Match row-1 plant tracks: 113b H+LS over 113a H+US at the same X;
    115 H+US over 114 H+LB at the same X.
    """
    H, plant, nm, cut, an = le.H, le.plant, le.nm, le.cut, le.an
    y_mw, y_me = Y0, Y0 + 1
    xo = CX0 + 3  # 113 crossover column (aligned)
    kx = CX0 + 7  # 115/114 column (aligned)

    # North: WME → 113b → 115 → K-1 / McKees Rocks
    _H(CX0, xo - 1, y_mw)
    nm((CX0, y_mw), "LEFT", "West Main Ext")
    cut((xo - 1, y_mw), "RIGHT", (xo, y_mw), "LEFT")
    # approach cell west of plant kept short — name on plant LEFT via ensure
    plant((xo, y_mw), ["HORIZONTAL", "LOWERSLASH"], "OS 113b (Princess)", "LEFT", "TO113")
    nm((xo, y_mw), "LEFT", "OS 113b (Princess)")
    H((xo + 1, y_mw))
    nm((xo + 1, y_mw), "RIGHT", "OS 113b (Princess)")
    cut((xo + 1, y_mw), "RIGHT", (xo + 2, y_mw), "LEFT")
    _H(xo + 2, kx - 1, y_mw)
    nm((xo + 2, y_mw), "LEFT", "OS 115 (Princess)")
    plant((kx, y_mw), ["HORIZONTAL", "UPPERSLASH"], "OS 115 (Princess)", "RIGHT", "TOL29")
    H((kx + 1, y_mw))
    nm((kx + 1, y_mw), "RIGHT", "OS 115 (Princess)")
    cut((kx + 1, y_mw), "RIGHT", (kx + 2, y_mw), "LEFT")
    _H(kx + 2, CX1, y_mw)
    nm((kx + 2, y_mw), "LEFT", "McKees Rocks")
    an((CX1, y_mw), "RIGHT")
    _sig(xo, y_mw, "LEFT", "113RA", "LAMP2", "LOWLEFT", "RIGHT")
    _sig(kx + 1, y_mw, "RIGHT", "115LB", "LAMP3", "LOWLEFT", "LEFT")

    # South: South Yard East → 113a → 114 → K-2 / McKeesport
    _H(CX0, xo - 2, y_me)
    nm((CX0, y_me), "LEFT", "South Yard East")
    cut((xo - 2, y_me), "RIGHT", (xo - 1, y_me), "LEFT")
    H((xo - 1, y_me))
    nm((xo - 1, y_me), "LEFT", "OS 113a (Princess)")
    plant((xo, y_me), ["HORIZONTAL", "UPPERSLASH"], "OS 113a (Princess)", "RIGHT", "TO113")
    cut((xo, y_mw), "BOTTOM", (xo, y_me), "TOP")
    H((xo + 1, y_me))
    nm((xo + 1, y_me), "RIGHT", "OS 113a (Princess)")
    cut((xo + 1, y_me), "RIGHT", (xo + 2, y_me), "LEFT")
    _H(xo + 2, kx - 1, y_me)
    nm((xo + 2, y_me), "LEFT", "OS 114 (Princess)")
    plant((kx, y_me), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 114 (Princess)", "RIGHT", "TOR36")
    H((kx + 1, y_me))
    nm((kx + 1, y_me), "RIGHT", "OS 114 (Princess)")
    cut((kx + 1, y_me), "RIGHT", (kx + 2, y_me), "LEFT")
    _H(kx + 2, CX1, y_me)
    nm((kx + 2, y_me), "LEFT", "McKeesport")
    an((CX1, y_me), "RIGHT")
    _sig(xo - 1, y_me, "LEFT", "113RB", "LAMP2", "LOWLEFT", "RIGHT")
    _sig(kx + 1, y_me, "RIGHT", "114LB", "LAMP3", "LOWLEFT", "LEFT")

    _label(xo, Y_BANNER, "PRINCESS", loc="LOWCENT", font="FONT_CP")
    _label(kx + 3, y_mw, "K-1", loc="LOWCENT")
    _label(kx + 3, y_me, "K-2", loc="LOWCENT")
    _label(CX1, y_mw - 1 if y_mw > Y_BANNER else Y_BANNER, "McKees Rocks, PA", loc="RIGHTCENT")
    _label(CX1, y_me + 1, "McKeesport, PA", loc="RIGHTCENT")


def _apply_labels(tp: ET.Element) -> None:
    for s in list(tp.findall("SECTION")):
        if int(s.get("Y")) < ROW2_Y0:
            continue
        sn = s.find("SEC_NAME")
        if sn is None:
            continue
        if s.find("TRACKGROUP") is None:
            tp.remove(s)
        else:
            s.remove(sn)

    by_xy = {(int(s.get("X")), int(s.get("Y"))): s for s in tp.findall("SECTION")}
    for item in ROW2_LABELS:
        x, y, text = item[0], item[1], item[2]
        loc = item[3] if len(item) > 3 else "LOWCENT"
        font = item[4] if len(item) > 4 else "FONT_LABEL"
        if y < ROW2_Y0:
            continue
        xy = (x, y)
        if xy in by_xy and by_xy[xy].find("TRACKGROUP") is not None:
            # colocate only short S-* labels on track cells
            if not text.startswith("S-"):
                continue
            ET.SubElement(
                by_xy[xy],
                "SEC_NAME",
                {"LOC_NAME": loc, "NAME": text, "FONT_NAME": font},
            )
            continue
        if xy in by_xy and by_xy[xy].find("TRACKGROUP") is None:
            tp.remove(by_xy[xy])
        sec = ET.Element("SECTION", {"X": str(x), "Y": str(y)})
        ET.SubElement(
            sec,
            "SEC_NAME",
            {"LOC_NAME": loc, "NAME": text, "FONT_NAME": font},
        )
        tp.append(sec)
        by_xy[xy] = sec


def _demote_non_plant_sp(tp: ET.Element, plants: set[tuple[int, int]]) -> None:
    for s in tp.findall("SECTION"):
        if s.find("TRACKGROUP") is None:
            continue
        xy = (int(s.get("X")), int(s.get("Y")))
        if xy[1] < ROW2_Y0 or xy in plants:
            continue
        tracks = [
            (t.text or "").strip() for t in s.find("TRACKGROUP").findall("TRACK")
        ]
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
                ET.SubElement(
                    se,
                    "BLOCK",
                    {
                        "NAME": le.ANCHORS[key],
                        "STATION": le.ANCHORS[key],
                        "DISCIPLINE": "CTC",
                        "VISIBLE": "true",
                    },
                )
            elif key in le.ANON:
                ET.SubElement(se, "BLOCK")
            s.append(se)


def _ensure_plant_myblock(tp: ET.Element, plants: dict[tuple[int, int], tuple[str, str, str]]) -> None:
    """Every plant needs a named non-SP BLOCK edge (PtsEdge.MyBlock)."""
    secs = {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in tp.findall("SECTION")
        if s.find("TRACKGROUP") is not None
    }
    for xy, (os_name, normal, _tip) in plants.items():
        sec = secs.get(xy)
        if sec is None:
            continue
        named = False
        sp_edge = None
        for e in sec.findall("SEC_EDGE"):
            if e.find("SWITCHPOINTS") is not None:
                sp_edge = e.get("EDGE")
                continue
            b = e.find("BLOCK")
            if b is not None and b.get("NAME"):
                named = True
        if named:
            continue
        # Prefer NORMAL frog leg; else first non-SP edge.
        target = None
        for e in sec.findall("SEC_EDGE"):
            if e.get("EDGE") == sp_edge:
                continue
            if e.get("EDGE") == normal:
                target = e
                break
            if target is None:
                target = e
        if target is None:
            continue
        for old in list(target):
            target.remove(old)
        ET.SubElement(
            target,
            "BLOCK",
            {
                "NAME": os_name,
                "STATION": os_name,
                "DISCIPLINE": "CTC",
                "VISIBLE": "true",
            },
        )


def _heal_blk_plain_seams(tp: ET.Element) -> int:
    """Promote plain mates that face a BLOCK edge to anonymous BLOCK.

    CATS ClassCasts when BlkEdge.discoverAdvanceVitalLogic hits a bare
    SecEdge across a BLK→plain seam. Anon BLK on the mate is safe.
    Only touches Class-I rows (y >= ROW2_Y0).
    """
    secs = {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in tp.findall("SECTION")
        if s.find("TRACKGROUP") is not None and int(s.get("Y")) >= ROW2_Y0
    }
    opp = {"LEFT": "RIGHT", "RIGHT": "LEFT", "TOP": "BOTTOM", "BOTTOM": "TOP"}
    step = {"LEFT": (-1, 0), "RIGHT": (1, 0), "TOP": (0, -1), "BOTTOM": (0, 1)}

    def _edge(sec: ET.Element, edge: str) -> ET.Element | None:
        for e in sec.findall("SEC_EDGE"):
            if e.get("EDGE") == edge:
                return e
        return None

    n = 0
    for xy, sec in list(secs.items()):
        for e in list(sec.findall("SEC_EDGE")):
            if e.find("BLOCK") is None or e.find("SWITCHPOINTS") is not None:
                continue
            ed = e.get("EDGE") or ""
            dx, dy = step[ed]
            nb = (xy[0] + dx, xy[1] + dy)
            other = secs.get(nb)
            if other is None:
                continue
            back = opp[ed]
            oe = _edge(other, back)
            if oe is None:
                oe = ET.SubElement(other, "SEC_EDGE", {"EDGE": back})
            if oe.find("SWITCHPOINTS") is not None:
                continue
            if oe.find("BLOCK") is not None:
                continue
            ET.SubElement(oe, "BLOCK")
            n += 1
    return n


def _clear_sp_throats(tp: ET.Element) -> None:
    """Remove BLOCK on the edge facing into SWITCHPOINTS (plain→SP only)."""
    secs = {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in tp.findall("SECTION")
        if s.find("TRACKGROUP") is not None and int(s.get("Y")) >= ROW2_Y0
    }
    opp = {"LEFT": "RIGHT", "RIGHT": "LEFT", "TOP": "BOTTOM", "BOTTOM": "TOP"}
    step = {"LEFT": (-1, 0), "RIGHT": (1, 0), "TOP": (0, -1), "BOTTOM": (0, 1)}
    for xy, s in secs.items():
        for e in s.findall("SEC_EDGE"):
            if e.find("SWITCHPOINTS") is None:
                continue
            ed = e.get("EDGE")
            dx, dy = step[ed]
            nb = (xy[0] + dx, xy[1] + dy)
            other = secs.get(nb)
            if other is None:
                continue
            back = opp[ed]
            for oe in list(other.findall("SEC_EDGE")):
                if oe.get("EDGE") != back or oe.find("BLOCK") is None:
                    continue
                other.remove(oe)
                other.append(ET.Element("SEC_EDGE", {"EDGE": back}))


def _apply_row2_signals(tp: ET.Element) -> list[str]:
    """Place ROW2_SIGNALS without clearing row-1 lamps."""
    secs = {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in tp.findall("SECTION")
        if s.find("TRACKGROUP") is not None and int(s.get("Y")) >= ROW2_Y0
    }
    # Clear only row-2 signals
    for sec in secs.values():
        for se in sec.findall("SEC_EDGE"):
            for old in list(se.findall("SECSIGNAL")):
                se.remove(old)

    pantype_phys = {"LAMP1": "single", "LAMP2": "double", "LAMP3": "triple"}
    placed: list[str] = []
    for x, y, edge, name, pantype, loc, orient in ROW2_SIGNALS:
        sec = secs.get((x, y))
        if sec is None:
            print(f"ROW2 SIGNAL SKIP: {name} @({x},{y}) missing", file=sys.stderr)
            continue
        se = None
        for e in sec.findall("SEC_EDGE"):
            if e.get("EDGE") == edge:
                se = e
                break
        if se is None or se.find("BLOCK") is None:
            print(
                f"ROW2 SIGNAL SKIP: {name} @({x},{y}) {edge} needs BLOCK",
                file=sys.stderr,
            )
            continue
        if se.find("SWITCHPOINTS") is not None:
            print(f"ROW2 SIGNAL SKIP: {name} @({x},{y}) on SP", file=sys.stderr)
            continue
        sig = ET.Element("SECSIGNAL")
        sig.text = f"\n          {name}\n          "
        ps = ET.SubElement(
            sig,
            "PANELSIGNAL",
            {"SIGLOCATION": loc, "SIGORIENT": orient, "SIGPANTYPE": pantype},
        )
        ps.tail = "\n          "
        phys = ET.SubElement(sig, "PHYSIGNAL")
        phys.text = pantype_phys.get(pantype, "single")
        phys.tail = "\n        "
        se.append(sig)
        placed.append(f"{name} @({x},{y}) {edge} {pantype}")
    return placed


def compose() -> int:
    src = BASE if BASE.exists() else BASE_FALLBACK
    if not src.exists():
        print(f"missing base {BASE} and {BASE_FALLBACK}", file=sys.stderr)
        return 1
    print(f"Class-I base: {src.relative_to(ROOT)}")

    root = ET.parse(src).getroot()
    tp = root.find("TRACKPLAN")
    assert tp is not None

    # Drop prior Class-I / old row2 band
    for s in list(tp.findall("SECTION")):
        if int(s.get("Y")) >= ROW2_Y0:
            tp.remove(s)

    le.GRID.clear()
    le.PLANTS.clear()
    le.ANCHORS.clear()
    le.ANON.clear()
    le.LABELS.clear()
    ROW2_LABELS.clear()
    ROW2_SIGNALS.clear()

    _build_panel_a()
    _build_panel_b()
    _build_panel_c()

    plants = set(le.PLANTS)
    grid = {xy: list(tr) for xy, tr in le.GRID.items()}

    # Install track sections
    secs: dict[tuple[int, int], ET.Element] = {}
    for (x, y), tracks in sorted(grid.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        sec = ET.Element("SECTION", {"X": str(x), "Y": str(y)})
        tg = ET.SubElement(sec, "TRACKGROUP")
        for t in tracks:
            ET.SubElement(tg, "TRACK").text = t
        tp.append(sec)
        secs[(x, y)] = sec

    mini = ET.Element("TRACKPLAN")
    for (x, y), tracks in sorted(grid.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        mini.append(le.make_section(x, y, tracks))
    disc = {n: "CTC" for n in set(le.ANCHORS.values())}
    le.wire(mini, disc)
    ctc._apply_station_labels(mini)
    for blk in mini.iter("BLOCK"):
        if blk.get("NAME"):
            blk.set("VISIBLE", "true")
            blk.set("DISCIPLINE", "CTC")
    _demote_non_plant_sp(mini, plants)
    _clear_sp_throats(mini)
    _ensure_plant_myblock(mini, {xy: le.PLANTS[xy] for xy in plants})
    _heal_blk_plain_seams(mini)

    errs = le.verify(mini)
    wired = {(int(s.get("X")), int(s.get("Y"))): s for s in mini.findall("SECTION")}
    for xy, wsec in wired.items():
        live = secs[xy]
        for e in list(live.findall("SEC_EDGE")):
            live.remove(e)
        for e in wsec.findall("SEC_EDGE"):
            live.append(e)

    _demote_non_plant_sp(tp, plants)
    _clear_sp_throats(tp)
    _ensure_plant_myblock(tp, {xy: le.PLANTS[xy] for xy in plants})
    healed = _heal_blk_plain_seams(tp)
    _apply_labels(tp)
    placed = _apply_row2_signals(tp)

    # Ensure yellow CP font def exists
    wy._ensure_cp_yellow_labels(root)

    max_x = max(int(s.get("X")) for s in tp.findall("SECTION"))
    max_y = max(int(s.get("Y")) for s in tp.findall("SECTION"))
    tp.set("COLUMNS", str(max_x + 2))
    tp.set("ROWS", str(max_y + 2))
    root.set("WIDTH", str(max(2800, max_x * 48)))
    root.set("HEIGHT", str(max(1200, max_y * 55)))

    # Occupancy + turnouts + trains for whole panel.
    # Row-1 plants use wy.PLANTS; Class-I band uses le.PLANTS — same tip
    # idents so SELECTEDREPORT/ROUTECOMMAND share M2T and frogs stay in sync.
    gen.ensure_mqtt(root)
    gen.wire_occupancy(root, le.load_occupancy())
    to_map = wy.load_turnouts()
    n_to_r1 = wy.wire_turnouts(tp, to_map)
    n_to_r2 = wy.wire_turnouts(tp, to_map, plants=dict(le.PLANTS))
    for ops in root.iter("OPERATIONS"):
        ops.set("CONNECT", "true")
    for blk in tp.iter("BLOCK"):
        if blk.get("NAME"):
            blk.set("STATION", blk.get("STATION") or blk.get("NAME"))
            blk.set("VISIBLE", "true")
    ctc._apply_station_labels(tp)
    gen.ensure_hart_trains(root)

    ET.indent(root, space="  ")
    # Sidecar only — never clobber ops / Designer working copy.
    ET.ElementTree(root).write(OUT, encoding="UTF-8", xml_declaration=True)
    print(f"wrote {OUT.relative_to(ROOT)}")

    print(
        f"Class-I row2: plants={len(plants)} cells={len(grid)} "
        f"COLS={tp.get('COLUMNS')} ROWS={tp.get('ROWS')} verify={len(errs)} "
        f"healed_seams={healed} signals={len(placed)}/{len(ROW2_SIGNALS)} "
        f"turnouts_r1={n_to_r1} turnouts_r2={n_to_r2}"
    )
    for p in placed:
        print(f"  signal {p}")
    if errs:
        for e in errs[:20]:
            print(f"  VERIFY: {e}", file=sys.stderr)
        # Soft: R3/R4/R5 on Class-I sketches are iterative; still launchable.
        print("NOTE: Class-I verify warnings kept — review Digicon paint", file=sys.stderr)

    try:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "cats/scripts/render_cats_panel.py"),
                str(OUT),
                str(SHOT),
            ],
            check=False,
            cwd=ROOT,
        )
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(compose())
