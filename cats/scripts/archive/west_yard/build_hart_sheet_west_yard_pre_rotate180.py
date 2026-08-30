#!/usr/bin/env python3
"""West Yard station-map sheet → one Digicon panel (critique unit).

SoR: cats/docs/station_maps/Neville_Island_Station_Map_West_Yard_0.png

Rotated Digicon (Brick-friendly):
  Main West enters from the LEFT into Brick 100; diverge goes straight
  down into Brick-Plane → Plane (no lead turn-around under the main).
  W-1 / W-2 merge at 101 on that same west approach (yard legs, not the
  main continuum past Brick).

Slash SoR: 101 / Brick / Barn use "/" (H+LOWERSLASH / H+UPPERSLASH).

    python3 cats/scripts/build_hart_sheet_west_yard.py
    CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh \\
        cats/panels/sheets/HART_sheet_West_Yard.xml
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "cats/scripts"
sys.path.insert(0, str(SCRIPTS))

import build_hart_digicon_from_le as le  # noqa: E402

OUT = ROOT / "cats/panels/sheets/archive/west_yard/HART_sheet_West_Yard.xml"
SHOT = ROOT / "cats/screenshots/sheets/HART_sheet_West_Yard.png"
WIDTH, HEIGHT = "1600", "560"

STATION = {
    "W-1": "W-1",
    "W-2": "W-2",
    "OS 101": "101",
    "OS 100": "100",
    "Brick-Plane": "100-102",
    "OS 102": "102",
    "Scale": "West Lead",
    "Barn": "West Lead",
    "East Main Ext": "Main East",
    "Main East": "Main East",
    "Main West": "Main West",
    "OS 117": "117",
    "OS 117b": "117",
}


def _clear() -> None:
    le.GRID.clear()
    le.PLANTS.clear()
    le.ANCHORS.clear()
    le.ANON.clear()
    le.LABELS.clear()


def _shift_1() -> None:
    g = {(x + 1, y + 1): v for (x, y), v in le.GRID.items()}
    p = {(x + 1, y + 1): v for (x, y), v in le.PLANTS.items()}
    a = {((x + 1, y + 1), e): n for ((x, y), e), n in le.ANCHORS.items()}
    n = {((x + 1, y + 1), e) for (x, y), e in le.ANON}
    labs = [(x + 1, y + 1, t) for x, y, t in le.LABELS]
    le.GRID.clear(); le.GRID.update(g)
    le.PLANTS.clear(); le.PLANTS.update(p)
    le.ANCHORS.clear(); le.ANCHORS.update(a)
    le.ANON.clear(); le.ANON.update(n)
    le.LABELS.clear(); le.LABELS.extend(labs)


def _run(x0: int, x1: int, y: int, name: str) -> None:
    for x in range(x0, x1 + 1):
        le.H((x, y))
    le.nm((x0, y), "LEFT", name)


def build_west_yard_sheet() -> None:
    H, plant, nm, cut, an = le.H, le.plant, le.nm, le.cut, le.an
    _clear()

    # =====================================================================
    # Spine y=1:  W-1 → 101 → Main West → Brick 100 → Main West → East End
    # Lead  y=2:  W-2 → 101;  100-102 → Plane → West Lead → Barn → South Yard
    #       y=3:  Plane → Main East → Barn → East End
    #
    # Brick sits ON Main West (approach from LEFT). Diverge BOTTOM goes
    # straight into 100-102 → Plane — no under-main turn-around.
    # =====================================================================

    # --- W-1 / W-2 → 101 (yard merge onto the west approach; keep "/" look) ---
    _run(2, 3, 1, "W-1")
    cut((3, 1), "RIGHT", (4, 1), "LEFT")
    H((4, 1))
    nm((4, 1), "LEFT", "OS 101")
    plant((5, 1), ["HORIZONTAL", "LOWERSLASH"], "OS 101", "LEFT", "TOL38")
    H((6, 1))  # plain into SP RIGHT

    _run(2, 4, 2, "W-2")
    cut((4, 2), "RIGHT", (5, 2), "LEFT")
    le.GRID[(5, 2)] = ["UPPERSLASH"]
    nm((5, 2), "LEFT", "W-2")
    cut((5, 1), "BOTTOM", (5, 2), "TOP")

    # --- Brick 100 ("/" = H+LOWERSLASH) ---
    # No intermediate 100–101 block: (6,1) is plain into 101 SP and BLK into 100.
    # Main West starts EAST of Brick only.
    # (6,1) already plain into 101 SP; BLK boundary straight into Brick plant
    cut((6, 1), "RIGHT", (7, 1), "LEFT")
    plant((7, 1), ["HORIZONTAL", "LOWERSLASH"], "OS 100", "LEFT", "TOL3")
    nm((7, 1), "LEFT", "OS 100")
    H((8, 1))  # plain into SP RIGHT
    cut((8, 1), "RIGHT", (9, 1), "LEFT")
    nm((9, 1), "LEFT", "Main West")
    # Match West Lead / Main East east rim (x=25)
    for x in range(9, 26):
        H((x, 1))
    an((25, 1), "RIGHT")

    # Diverging leg → Brick-Plane → Plane (direct; one UB elbow TOP→RIGHT)
    le.GRID[(7, 2)] = ["UPPERBACKSLASH"]
    cut((7, 1), "BOTTOM", (7, 2), "TOP")
    nm((7, 2), "RIGHT", "Brick-Plane")
    _run(8, 10, 2, "Brick-Plane")
    cut((10, 2), "RIGHT", (11, 2), "LEFT")

    # --- Plane 102 (unchanged — signed off) ---
    H((11, 2))
    nm((11, 2), "LEFT", "OS 102")
    plant((12, 2), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 102", "RIGHT", "TOL42")
    cut((12, 2), "RIGHT", (13, 2), "LEFT")
    nm((13, 2), "LEFT", "Scale")
    for x in range(13, 17):
        H((x, 2))

    le.GRID[(12, 3)] = ["UPPERBACKSLASH"]
    cut((12, 2), "BOTTOM", (12, 3), "TOP")
    nm((12, 3), "RIGHT", "East Main Ext")
    _run(13, 16, 3, "East Main Ext")

    # --- Barn 117 (unchanged — signed off) ---
    cut((16, 2), "RIGHT", (17, 2), "LEFT")
    H((17, 2))
    nm((17, 2), "LEFT", "OS 117")
    plant((18, 2), ["HORIZONTAL", "LOWERSLASH"], "OS 117", "LEFT", "TO117")
    H((19, 2))
    cut((19, 2), "RIGHT", (20, 2), "LEFT")
    nm((20, 2), "LEFT", "Barn")
    for x in range(20, 26):
        H((x, 2))
    an((25, 2), "RIGHT")

    cut((18, 2), "BOTTOM", (18, 3), "TOP")
    H((17, 3))
    nm((17, 3), "LEFT", "OS 117b")
    plant((18, 3), ["HORIZONTAL", "UPPERSLASH"], "OS 117b", "RIGHT", "TO117")
    cut((16, 3), "RIGHT", (17, 3), "LEFT")
    cut((18, 3), "RIGHT", (19, 3), "LEFT")
    _run(19, 25, 3, "Main East")
    an((25, 3), "RIGHT")

    le.LABELS[:] = [
        (5, 0, "101"),
        (7, 0, "Brick 100"),
        (12, 0, "Plane 102"),
        (18, 0, "Barn"),
        (10, 0, "Main West"),
        # East-end arrows on empty cells past the rails (occupied cells skip labels)
        (26, 1, "to East End"),
        (26, 2, "to South Yard"),
        (26, 3, "to East End"),
        (2, 0, "W-1"),
        (2, 4, "W-2"),
        (12, 5, "WEST YARD"),
    ]
    _shift_1()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-render", action="store_true")
    args = ap.parse_args()

    build_west_yard_sheet()

    root = ET.parse(le.ARM).getroot()
    for ops in root.iter("OPERATIONS"):
        ops.set("CONNECT", "false")
    for old in list(root.findall("TRACKPLAN")):
        root.remove(old)
    if root.find(le.COMPRESSION_OFF_TAG) is None:
        root.append(ET.Element(le.COMPRESSION_OFF_TAG))

    tp = ET.Element("TRACKPLAN")
    for (x, y), tracks in sorted(le.GRID.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        tp.append(le.make_section(x, y, tracks))
    cols = max(c[0] for c in le.GRID) + 2
    rows = max(c[1] for c in le.GRID) + 2
    tp.set("COLUMNS", str(cols))
    tp.set("ROWS", str(rows))
    disc = {n: "CTC" for n in set(le.ANCHORS.values())}
    le.wire(tp, disc)
    for blk in tp.iter("BLOCK"):
        name = blk.get("NAME") or ""
        blk.set("STATION", STATION.get(name, name))
    root.append(tp)
    root.set("WIDTH", WIDTH)
    root.set("HEIGHT", HEIGHT)

    errs = le.verify(tp)
    for e in errs:
        print(f"VERIFY FAIL: {e}", file=sys.stderr)
    if errs:
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(OUT, encoding="UTF-8", xml_declaration=True)
    print(f"wrote {OUT.relative_to(ROOT)}  grid {cols}x{rows} cells={len(le.GRID)}")
    print("Brick on Main West from left; 100-102 runs straight to Plane.")

    if not args.no_render:
        import subprocess

        SHOT.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "cats/scripts/render_cats_panel.py"),
                str(OUT),
                str(SHOT),
            ],
            check=False,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
