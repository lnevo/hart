#!/usr/bin/env python3
"""HART Digicon — Neville station-map CPs + Fall River A/D yard body.

Starts from the verify-clean LE Digicon (Brick/Plane/Barn/112/111 plants),
then replaces the South Yard + East End stub peels with map geometry:

  plant on a row → S-track continues on that same row (Fall River A/D)
  next plant steps down-right (Neville South Yard / East End ladders)
  all S-1…S-5 share one east column (rectangle, not stairs)

Visual SoR:
  cats/docs/station_maps/Neville_Island_Station_Map_*.png
  cats/docs/vendor/fall_river_yard_crop.jpg
  cats/docs/STATION_MAP_CTC.md

    python3 cats/scripts/build_hart_digicon_ctc.py --mqtt
    CATS_LAUNCH_VIA=terminal ./cats/scripts/launch_cats.sh cats/panels/HART_ctc.xml
"""

from __future__ import annotations

import argparse
import copy
import csv
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_hart_digicon_from_le as le  # noqa: E402

OUT_MAGNET = ROOT / "cats/panels/HART_ctc_magnet.xml"
OUT_MQTT = ROOT / "cats/panels/HART_ctc.xml"
WIDTH, HEIGHT = "2600", "1000"

# Equal A/D east edge (0-based, before shift)
AD_EAST = 30

# On-track labels (STATION) — NAME stays JMRI/occupancy identity for MQTT.
# Language matches Neville station-map sheets.
STATION_LABEL = {
    "West Yard 1": "W-1",
    "West Yard 2": "W-2",
    "Main West": "Main West",
    "Main East": "Main East",
    "East Main Ext": "Main East",
    "West Main Ext": "Main West",
    "Yard T1": "West Lead",
    "Yard T6": "West Lead",
    "Yard Track 1": "S-1",
    "Yard Track 2": "S-2",
    "Yard Track 3": "S-3",
    "Yard Track 4": "S-4",
    "Yard Track 5": "S-5",
    "Yard T11": "ET-1",
    "Yard T10": "ET-2",
    "Yard T9": "ET-3",
    "East Lead": "East Lead",
    # K-1 / K-2 = OS 115 / OS 114 bodies (Block 1-4 / 1-3). Loops keep their names.
    "Block 100-102": "100–102",
    "OS 100 (Brick)": "100",
    "OS 101 (Brick)": "101",
    "OS 102 (Plane)": "102",
    "OS 103 (South Yard)": "103",
    "OS 104 (South Yard)": "104",
    "OS 105 (South Yard)": "105",
    "OS 106 (South Yard)": "106",
    "OS 107 (East End)": "107",
    "OS 108 (East End)": "108",
    "OS 109 (East End)": "109",
    "OS 110 (East End)": "110",
    "OS 111a (East End)": "111",
    "OS 111b (East End)": "111",
    "OS 112 (East End)": "112",
    "OS 113a (Princess)": "113",
    "OS 113b (Princess)": "113",
    "OS 114 (Princess)": "K-2",
    "OS 115 (Princess)": "K-1",
    "OS 116 (West Yard)": "116",
    "OS 117 (West Yard)": "117",
    "OS 117b (West Yard)": "117",
    "OS 118 (West Yard)": "118",
    "OS 119 (West Yard)": "119",
}


def _apply_station_labels(tp: ET.Element) -> None:
    """Paint station-map names on tracks; keep BLOCK NAME for occupancy."""
    for blk in tp.iter("BLOCK"):
        name = blk.get("NAME")
        if name and name in STATION_LABEL:
            blk.set("STATION", STATION_LABEL[name])


def _shift_1() -> None:
    g = {(x + 1, y + 1): v for (x, y), v in le.GRID.items()}
    p = {(x + 1, y + 1): v for (x, y), v in le.PLANTS.items()}
    a = {((x + 1, y + 1), e): n for ((x, y), e), n in le.ANCHORS.items()}
    n = {((x + 1, y + 1), e) for (x, y), e in le.ANON}
    labs = [(x + 1, y + 1, t) for x, y, t in le.LABELS]
    le.GRID.clear()
    le.GRID.update(g)
    le.PLANTS.clear()
    le.PLANTS.update(p)
    le.ANCHORS.clear()
    le.ANCHORS.update(a)
    le.ANON.clear()
    le.ANON.update(n)
    le.LABELS.clear()
    le.LABELS.extend(labs)


def _clear_cell(xy: tuple[int, int]) -> None:
    le.GRID.pop(xy, None)
    le.PLANTS.pop(xy, None)
    for e in ("LEFT", "RIGHT", "TOP", "BOTTOM"):
        le.ANCHORS.pop((xy, e), None)
        le.ANON.discard((xy, e))


def _body(x0: int, y: int, name: str) -> None:
    """Fill H from x0…AD_EAST, name on west, stub-end on east."""
    for x in range(x0, AD_EAST + 1):
        le.H((x, y))
    le.nm((x0, y), "LEFT", name)
    le.an((AD_EAST, y), "RIGHT")


def _reshape_south_yard_ad() -> None:
    """Replace LE YT stub peels with Fall River / South Yard map ladder."""
    H, plant, nm, cut, an = le.H, le.plant, le.nm, le.cut, le.an

    # Remove LE South Yard + East End ladder cells (keep eng terminal x<14 on y=4,5)
    for xy in list(le.GRID):
        x, y = xy
        if y >= 3 and x >= 14:
            _clear_cell(xy)

    # West Lead continues from Yard T6 @ (10,3) / OS117 @ (11,3) into SY
    # (LE leaves a gap; fill as Yard T6 into TO1-on-lead then 103)
    cut((11, 3), "RIGHT", (12, 3), "LEFT")
    H((12, 3))
    nm((12, 3), "LEFT", "Yard T6")
    cut((12, 3), "RIGHT", (13, 3), "LEFT")
    H((13, 3))
    nm((13, 3), "LEFT", "OS 103 (South Yard)")
    plant((14, 3), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 103 (South Yard)", "RIGHT", "TOR14")
    cut((14, 3), "RIGHT", (15, 3), "LEFT")
    _body(15, 3, "Yard Track 1")

    # 104 / S-2 — step down-right (same-row body)
    le.GRID[(14, 4)] = ["UPPERBACKSLASH"]
    cut((14, 3), "BOTTOM", (14, 4), "TOP")
    nm((14, 4), "RIGHT", "OS 104 (South Yard)")
    H((15, 4))
    nm((15, 4), "LEFT", "OS 104 (South Yard)")
    plant((16, 4), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 104 (South Yard)", "RIGHT", "TOL15")
    cut((16, 4), "RIGHT", (17, 4), "LEFT")
    _body(17, 4, "Yard Track 2")

    # 105 / S-3
    le.GRID[(16, 5)] = ["UPPERBACKSLASH"]
    cut((16, 4), "BOTTOM", (16, 5), "TOP")
    nm((16, 5), "RIGHT", "OS 105 (South Yard)")
    H((17, 5))
    nm((17, 5), "LEFT", "OS 105 (South Yard)")
    plant((18, 5), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 105 (South Yard)", "RIGHT", "TOL17")
    cut((18, 5), "RIGHT", (19, 5), "LEFT")
    _body(19, 5, "Yard Track 3")

    # 106 / S-4
    le.GRID[(18, 6)] = ["UPPERBACKSLASH"]
    cut((18, 5), "BOTTOM", (18, 6), "TOP")
    nm((18, 6), "RIGHT", "OS 106 (South Yard)")
    H((19, 6))
    nm((19, 6), "LEFT", "OS 106 (South Yard)")
    plant((20, 6), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 106 (South Yard)", "RIGHT", "TOL19")
    cut((20, 6), "RIGHT", (21, 6), "LEFT")
    _body(21, 6, "Yard Track 4")

    # S-5 continues off 106 diverge (South Yard map)
    le.GRID[(20, 7)] = ["UPPERBACKSLASH"]
    cut((20, 6), "BOTTOM", (20, 7), "TOP")
    nm((20, 7), "RIGHT", "Yard Track 5")
    # plain-join slash into body (no BLK on (21,7) LEFT — would R4 vs slash RIGHT)
    for x in range(21, AD_EAST + 1):
        H((x, 7))
    nm((21, 7), "LEFT", "Yard Track 5")
    an((AD_EAST, 7), "RIGHT")


def _reshape_east_end() -> None:
    """East End: 107–110 spine east of A/D, drops onto equal S-rows; 110 → East Lead."""
    H, plant, nm, cut, an = le.H, le.plant, le.nm, le.cut, le.an

    for y in (3, 4, 5, 6, 7):
        le.ANON.discard(((AD_EAST, y), "RIGHT"))

    # Contiguous approach+plant pairs on y=3 (LE recipe — SP never faces BLK)
    ee0 = AD_EAST + 1  # 31
    specs = [
        (ee0, "OS 107 (East End)", "TOR11", 7, "Yard Track 5"),
        (ee0 + 2, "OS 108 (East End)", "TOR9", 6, "Yard Track 4"),
        (ee0 + 4, "OS 109 (East End)", "TOR7", 5, "Yard Track 3"),
        (ee0 + 6, "OS 110 (East End)", "TOL6", 4, "Yard Track 2"),
    ]
    for i, (px, os_name, ident, drop_y, ytrk) in enumerate(specs):
        H((px, 3))
        nm((px, 3), "LEFT", os_name)
        plant((px + 1, 3), ["HORIZONTAL", "LOWERBACKSLASH"], os_name, "RIGHT", ident)
        if i < len(specs) - 1:
            cut((px + 1, 3), "RIGHT", (specs[i + 1][0], 3), "LEFT")
        else:
            an((px + 1, 3), "RIGHT")
        # drop onto matching A/D row; plain-join bridge (one name tip only)
        for x in range(AD_EAST + 1, px + 2):
            if (x, drop_y) not in le.GRID:
                H((x, drop_y))
        nm((AD_EAST + 1, drop_y), "LEFT", ytrk)
        cut((px + 1, 3), "BOTTOM", (px + 1, drop_y), "TOP")
        cut((AD_EAST, drop_y), "RIGHT", (AD_EAST + 1, drop_y), "LEFT")

    # S-1 also reaches EE (drop from 110 band / extend row 3 body already OS — use 110 col)
    for x in range(AD_EAST + 1, ee0 + 7):
        if (x, 3) in le.PLANTS or (x, 3) in le.GRID:
            continue
    # Yard Track 1: extend to under 110 approach and cut from a free cell
    # Use column ee0+6 approach BOTTOM? approach is OS110. Drop YT2 already on y=4.
    # Attach YT1 via 110 plant — extra drop on y=3 is the OS spine itself.
    # Extend YT1 east under the spine with its own cells on… it's on y=3 west.
    # Bridge YT1 on a side path: from AD_EAST y=3 into first EE approach with cut
    cut((AD_EAST, 3), "RIGHT", (ee0, 3), "LEFT")

    # 110 → East Lead on y=3, and lander on main spine y=2 for Princess
    le.ANON.discard(((ee0 + 7, 3), "RIGHT"))
    H((ee0 + 8, 3))
    nm((ee0 + 8, 3), "LEFT", "East Lead")
    cut((ee0 + 7, 3), "RIGHT", (ee0 + 8, 3), "LEFT")
    # 45° up to main spine for Princess
    le.GRID[(ee0 + 9, 3)] = ["UPPERSLASH"]
    cut((ee0 + 8, 3), "RIGHT", (ee0 + 9, 3), "LEFT")
    nm((ee0 + 9, 3), "LEFT", "East Lead")
    le.GRID[(ee0 + 9, 2)] = ["LOWERBACKSLASH"]
    cut((ee0 + 9, 3), "TOP", (ee0 + 9, 2), "BOTTOM")
    nm((ee0 + 9, 2), "LEFT", "East Lead")


def _princess_east_of_ee() -> None:
    """Shenango map: Princess east of East End; 113 crossover; 114/115 → yards."""
    H, plant, nm, cut = le.H, le.plant, le.nm, le.cut

    # East Lead lander from EE reshape is at (AD_EAST+10, 2) = ee0+9
    land_x = AD_EAST + 10
    for xy in list(le.GRID):
        if xy[1] in (1, 2) and 18 <= xy[0] < land_x:
            _clear_cell(xy)

    for x in range(16, land_x + 1):
        if (x, 2) not in le.GRID:
            H((x, 2))
    nm((16, 2), "LEFT", "East Lead")
    # lander (land_x,2) may already be named East Lead from EE — BLK its west join
    if (land_x - 1, 2) in le.GRID and (land_x, 2) in le.GRID:
        cut((land_x - 1, 2), "RIGHT", (land_x, 2), "LEFT")

    for x in range(9, land_x + 1):
        if (x, 1) not in le.GRID:
            H((x, 1))

    px = land_x + 1
    cut((land_x, 2), "RIGHT", (px, 2), "LEFT")
    H((px, 2))
    nm((px, 2), "LEFT", "OS 113a (Princess)")
    plant((px + 1, 2), ["HORIZONTAL", "LOWERBACKSLASH"], "OS 113a (Princess)", "RIGHT", "TO113")
    cut((px + 1, 2), "RIGHT", (px + 2, 2), "LEFT")
    H((px + 2, 2))
    nm((px + 2, 2), "LEFT", "OS 114 (Princess)")
    plant((px + 3, 2), ["HORIZONTAL", "UPPERSLASH"], "OS 114 (Princess)", "RIGHT", "TOR36")
    nm((px + 3, 2), "RIGHT", "OS 114 (Princess)")
    H((px + 4, 2))
    H((px + 5, 2))
    nm((px + 4, 2), "LEFT", "McKeesport")

    cut((land_x, 1), "RIGHT", (px, 1), "LEFT")
    H((px, 1))
    nm((px, 1), "LEFT", "OS 113b (Princess)")
    plant((px + 1, 1), ["HORIZONTAL", "UPPERSLASH"], "OS 113b (Princess)", "RIGHT", "TO113")
    cut((px + 1, 2), "TOP", (px + 1, 1), "BOTTOM")
    cut((px + 1, 1), "RIGHT", (px + 2, 1), "LEFT")
    H((px + 2, 1))
    nm((px + 2, 1), "LEFT", "OS 115 (Princess)")
    plant((px + 3, 1), ["HORIZONTAL", "UPPERSLASH"], "OS 115 (Princess)", "RIGHT", "TOL29")
    cut((px + 3, 1), "RIGHT", (px + 4, 1), "LEFT")
    H((px + 4, 1))
    H((px + 5, 1))
    nm((px + 4, 1), "LEFT", "McKees Rocks")


def build_ctc_board() -> None:
    le.build_board(shift=False)
    _reshape_south_yard_ad()
    _reshape_east_end()
    _princess_east_of_ee()

    # Station-map connection labels. Only empty cells accept SEC_NAME
    # (see free-cell scan: header y=0 and footer y=8 are open after shift).
    le.LABELS[:] = [
        # --- Header: sheet / CP / which track the plant feeds ---
        (1, 0, "WEST YARD"),
        (3, 0, "Brick"),
        (4, 0, "100"),
        (5, 0, "101"),
        (7, 0, "Plane"),
        (8, 0, "102"),
        (9, 0, "111"),
        (11, 0, "Barn 117"),
        (13, 0, "112"),
        (14, 0, "SOUTH YARD"),
        (16, 0, "103→S-1"),
        (18, 0, "104→S-2"),
        (20, 0, "105→S-3"),
        (22, 0, "106→S-4"),
        (24, 0, "→S-5"),
        (26, 0, "S-1…S-5"),
        (29, 0, "EAST END"),
        (31, 0, "107→S-5"),
        (33, 0, "108→S-4"),
        (35, 0, "109→S-3"),
        (37, 0, "110→S-2"),
        (39, 0, "110→East Lead"),
        (41, 0, "PRINCESS"),
        (42, 0, "113"),
        (44, 0, "SHENANGO"),
        (45, 0, "115→K-1"),
        (47, 0, "114→K-2"),
        # --- Side callouts (known free pockets) ---
        (0, 1, "W-1"),
        (0, 4, "W-2"),
        (6, 6, "ET-1"),
        (8, 6, "ET-2"),
        (10, 6, "ET-3"),
        (12, 5, "West Lead"),
        (6, 3, "100↓Plane"),
        (9, 5, "102→Lead"),
        (11, 4, "117 XO"),
        # --- Footer: destination / connectivity (station-map arrows) ---
        (1, 8, "W-1/W-2 → 101 → Brick"),
        (5, 8, "Main West → East End → Princess"),
        (10, 8, "West Lead: Plane → Barn → 103 → S-1"),
        (16, 8, "Main East: Plane/Barn → East End → Princess"),
        (22, 8, "S-1"),
        (23, 8, "S-2"),
        (24, 8, "S-3"),
        (25, 8, "S-4"),
        (26, 8, "S-5"),
        (28, 8, "EE 110…107 feed S-tracks"),
        (33, 8, "112 → East Lead → Princess"),
        (38, 8, "113 XO · K-1 Rocks · K-2 McKeesport"),
        (44, 8, "← East End"),
    ]
    _shift_1()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mqtt", action="store_true")
    args = ap.parse_args()

    build_ctc_board()

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
    le.wire(tp, le.load_disciplines())
    _apply_station_labels(tp)
    root.append(tp)
    root.set("WIDTH", WIDTH)
    root.set("HEIGHT", HEIGHT)

    errs = le.verify(tp)
    for e in errs:
        print(f"VERIFY FAIL: {e}", file=sys.stderr)
    if errs:
        return 1

    ET.indent(root, space="  ")
    ET.ElementTree(root).write(OUT_MAGNET, encoding="UTF-8", xml_declaration=True)
    print(f"wrote {OUT_MAGNET.relative_to(ROOT)}")
    names = sorted({b.get("NAME") for b in root.iter("BLOCK") if b.get("NAME")})
    print(f"grid {cols}x{rows} cells={len(le.GRID)} plants={len(le.PLANTS)}")
    print(f"named ({len(names)}): {', '.join(names)}")
    print(f"regions: {len(le.regions_of(tp))}")
    print("Station-map Digicon: Fall River A/D + Neville CP order.")

    want = {r["block_user_name"].strip() for r in csv.DictReader(le.OCC_CSV.open())}
    missing = sorted(want - set(names))
    if missing:
        print(f"NOT YET ON BOARD ({len(missing)}): {', '.join(missing)}")

    if args.mqtt:
        import jmri_to_cats_digicon as gen

        mqtt_root = copy.deepcopy(root)
        gen.ensure_mqtt(mqtt_root)
        gen.wire_occupancy(mqtt_root, le.load_occupancy())
        for ops in mqtt_root.iter("OPERATIONS"):
            ops.set("CONNECT", "true")
        gen.ensure_hart_trains(mqtt_root)
        ET.indent(mqtt_root, space="  ")
        ET.ElementTree(mqtt_root).write(OUT_MQTT, encoding="UTF-8", xml_declaration=True)
        n_occ = sum(
            1
            for b in mqtt_root.iter("BLOCK")
            if b.get("NAME") and b.find("OCCUPIEDSPEC") is not None
        )
        print(f"wrote {OUT_MQTT.relative_to(ROOT)} MQTT {n_occ}/{len(names)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
