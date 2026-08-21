#!/usr/bin/env python3
"""Wire row-2 South Yard + East End under West_Yard2.

South Yard left ladder = horizontal flip of Designer East End ladder:
  EE 110→109→108→107 : H+LOWERSLASH stepping (-1,+1), spine east, normal=BOTTOM
  SY 103→104→105→106 : H+LOWERBACKSLASH stepping (+1,+1), spine west, normal=BOTTOM
  (103 keeps normal=RIGHT into S-1 — entry plant.)

Row-2 left/right edges match West Yard (x=8..27).

    python3 cats/scripts/wire_hart_sheet_west_yard2.py --with-row2
    python3 cats/scripts/compose_hart_sheet_west_yard2_row2.py
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

SRC = ROOT / "cats/panels/sheets/HART_sheet_West_Yard2.xml"
ACTIVE = ROOT / "cats/panels/sheets/HART_sheet_West_Yard.xml"
SHOT = ROOT / "cats/screenshots/sheets/HART_sheet_West_Yard2.png"
DESIGNER_ROW2 = ROOT / "cats/panels/sheets/HART_sheet_West_Yard2_row2_designer.xml"

ROW2_Y0 = 10
# Match West Yard track bbox (xmin=8, xmax=27). Shift in Designer; preserve via sidecar.
X0 = 8
X1 = 27
FORCE_REBUILD = False  # Designer owns row2 offsets; set True only to rebuild SoR

# Absolute plants — compressed S-body so band fits X0..X1
P103 = (11, 13)
P104 = (12, 14)
P105 = (13, 15)
P106 = (14, 16)
P107 = (20, 16)
P108 = (21, 15)
P109 = (22, 14)
P110 = (23, 13)
P111 = (P108[0], 12)  # (21,12) — even with 108
P112 = (25, 13)

PLANTS: dict[tuple[int, int], tuple[list[str], str, str, str]] = {
    # SY — 103 entry normal RIGHT; 104-106 ladder normal BOTTOM (mirror of EE)
    P103: (["HORIZONTAL", "LOWERBACKSLASH"], "OS 103 (South Yard)", "RIGHT", "TOR14"),
    P104: (["HORIZONTAL", "LOWERBACKSLASH"], "OS 104 (South Yard)", "BOTTOM", "TOL15"),
    P105: (["HORIZONTAL", "LOWERBACKSLASH"], "OS 105 (South Yard)", "BOTTOM", "TOL17"),
    P106: (["HORIZONTAL", "LOWERBACKSLASH"], "OS 106 (South Yard)", "BOTTOM", "TOL19"),
    # EE — Designer geometry; ladder via normal BOTTOM
    # 110 sits on Main East: LEFT = through to 112 (CLOSED); BOTTOM = ladder.
    P110: (["HORIZONTAL", "LOWERSLASH"], "OS 110 (East End)", "LEFT", "TOL6"),
    P109: (["HORIZONTAL", "LOWERSLASH"], "OS 109 (East End)", "BOTTOM", "TOR7"),
    P108: (["HORIZONTAL", "LOWERSLASH"], "OS 108 (East End)", "BOTTOM", "TOR9"),
    P107: (["HORIZONTAL", "LOWERSLASH"], "OS 107 (East End)", "BOTTOM", "TOR11"),
    P111: (["HORIZONTAL", "LOWERBACKSLASH"], "OS 111a (East End)", "RIGHT", "TO111"),
    # Normal BOTTOM = Barn spine (CLOSED); throw LEFT = Main East → South Yard East
    # (Brick 100 pattern: throw = continuing main).
    P112: (["HORIZONTAL", "LOWERSLASH"], "OS 112 (East End)", "BOTTOM", "TOL23"),
}


def _sy_spine_cells(px: int, py: int) -> dict[tuple[int, int], list[str]]:
    """West spine for one H+LB plant — mirror of EE east US/LS spine."""
    return {
        (px, py + 1): ["UPPERBACKSLASH"],
        (px - 1, py + 1): ["LOWERBACKSLASH"],
        (px - 1, py + 2): ["UPPERBACKSLASH"],
    }


def _ee_spine_cells(px: int, py: int) -> dict[tuple[int, int], list[str]]:
    """East spine for one H+LS plant (Designer)."""
    return {
        (px, py + 1): ["UPPERSLASH"],
        (px + 1, py + 1): ["LOWERSLASH"],
        (px + 1, py + 2): ["UPPERSLASH"],
    }


def _build_row2_grid() -> dict[tuple[int, int], list[str]]:
    """Absolute TRACKGROUPs for South Yard + East End band."""
    g: dict[tuple[int, int], list[str]] = {}
    y_mw = P111[1]  # Main West / 111 row
    y_s1 = P103[1]  # West Lead / S-1
    y_s2 = P104[1]
    y_s3 = P105[1]
    y_s4 = P106[1]
    y_s5 = y_s4 + 1
    y_me_chord = y_s4 + 2  # bottom Main East chord

    def put(xy: tuple[int, int], tracks: list[str]) -> None:
        g[xy] = list(tracks)

    # --- Main West + 111 ---
    for x in range(X0, X1 + 1):
        put((x, y_mw), ["HORIZONTAL"])
    put(P111, ["HORIZONTAL", "LOWERBACKSLASH"])
    put((P111[0], y_s1), ["HORIZONTAL", "UPPERBACKSLASH"])

    # --- West Lead / S-1 / South Yard East ---
    for x in range(X0, X1 + 1):
        put((x, y_s1), ["HORIZONTAL"])
    put(P103, ["HORIZONTAL", "LOWERBACKSLASH"])
    put(P110, ["HORIZONTAL", "LOWERSLASH"])
    put(P112, ["HORIZONTAL", "LOWERSLASH"])

    # --- SY plants 104-106 + S-row bodies ---
    put(P104, ["HORIZONTAL", "LOWERBACKSLASH"])
    put(P105, ["HORIZONTAL", "LOWERBACKSLASH"])
    put(P106, ["HORIZONTAL", "LOWERBACKSLASH"])

    for x in range(P104[0] + 1, P109[0]):
        put((x, y_s2), ["HORIZONTAL"])
    for x in range(P105[0] + 1, P108[0]):
        put((x, y_s3), ["HORIZONTAL"])
    for x in range(P106[0] + 1, P107[0]):
        put((x, y_s4), ["HORIZONTAL"])

    put(P103, ["HORIZONTAL", "LOWERBACKSLASH"])
    put(P110, ["HORIZONTAL", "LOWERSLASH"])
    put(P112, ["HORIZONTAL", "LOWERSLASH"])
    put((P111[0], y_s1), ["HORIZONTAL", "UPPERBACKSLASH"])

    put(P109, ["HORIZONTAL", "LOWERSLASH"])
    put(P108, ["HORIZONTAL", "LOWERSLASH"])
    put(P107, ["HORIZONTAL", "LOWERSLASH"])

    # Main East tip west of SY spine + bottom chord
    put((X0, y_s2), ["HORIZONTAL"])
    put((X0 + 1, y_s2), ["HORIZONTAL"])
    for x in range(P106[0], P107[0] + 1):
        put((x, y_me_chord), ["HORIZONTAL"])

    for x in range(P106[0] + 1, P107[0]):
        put((x, y_s5), ["HORIZONTAL"])

    for plant in (P103, P104, P105, P106):
        for xy, tr in _sy_spine_cells(*plant).items():
            put(xy, tr)
    for plant in (P110, P109, P108, P107):
        for xy, tr in _ee_spine_cells(*plant).items():
            put(xy, tr)
    put((P112[0], P112[1] + 1), ["UPPERSLASH"])

    for xy, (tracks, *_rest) in PLANTS.items():
        put(xy, tracks)
    put((P111[0], y_s1), ["HORIZONTAL", "UPPERBACKSLASH"])

    return g


# Named block tips (absolute) — derived from plant rows
_Y_MW, _Y_S1 = P111[1], P103[1]
_Y_S2, _Y_S3, _Y_S4 = P104[1], P105[1], P106[1]
_Y_S5 = _Y_S4 + 1

ANCHORS: list[tuple[int, int, str, str]] = [
    (X0, _Y_MW, "LEFT", "Main West"),
    (P111[0] - 1, _Y_MW, "LEFT", "OS 111a (East End)"),
    (P111[0], _Y_S1, "LEFT", "OS 111a (East End)"),
    (P111[0] + 1, _Y_S1, "LEFT", "South Yard 1"),
    (X0, _Y_S1, "LEFT", "West Lead"),
    (P103[0] - 1, _Y_S1, "LEFT", "OS 103 (South Yard)"),
    (P103[0] + 1, _Y_S1, "LEFT", "South Yard 1"),
    (P104[0], _Y_S2, "RIGHT", "OS 104 (South Yard)"),
    (P104[0] + 1, _Y_S2, "LEFT", "South Yard 2"),
    (P105[0], _Y_S3, "RIGHT", "OS 105 (South Yard)"),
    (P105[0] + 1, _Y_S3, "LEFT", "South Yard 3"),
    (P106[0], _Y_S4, "RIGHT", "OS 106 (South Yard)"),
    (P106[0] + 1, _Y_S4, "LEFT", "South Yard 4"),
    (P106[0], _Y_S5, "RIGHT", "South Yard 5"),
    (P106[0] + 1, _Y_S5, "LEFT", "South Yard 5"),
    (P110[0], _Y_S1, "LEFT", "OS 110 (East End)"),
    (P109[0], _Y_S2, "LEFT", "OS 109 (East End)"),
    (P108[0], _Y_S3, "LEFT", "OS 108 (East End)"),
    (P107[0], _Y_S4, "LEFT", "OS 107 (East End)"),
    (P112[0], _Y_S1, "LEFT", "OS 112 (East End)"),
    (X1, _Y_S1, "LEFT", "South Yard East"),
    (X0, _Y_S2, "LEFT", "Main East"),
]

CUTS: list[tuple[tuple[int, int], str, tuple[int, int], str]] = [
    ((P111[0] - 2, _Y_MW), "RIGHT", (P111[0] - 1, _Y_MW), "LEFT"),
    ((P111[0], _Y_MW), "BOTTOM", (P111[0], _Y_S1), "TOP"),
    ((P111[0], _Y_S1), "LEFT", (P111[0] - 1, _Y_S1), "RIGHT"),
    ((P111[0], _Y_S1), "RIGHT", (P111[0] + 1, _Y_S1), "LEFT"),
    ((P103[0] - 2, _Y_S1), "RIGHT", (P103[0] - 1, _Y_S1), "LEFT"),
    ((P103[0], _Y_S1), "RIGHT", (P103[0] + 1, _Y_S1), "LEFT"),
    ((P103[0], _Y_S1), "BOTTOM", (P103[0], _Y_S2), "TOP"),
    ((P104[0], _Y_S2), "RIGHT", (P104[0] + 1, _Y_S2), "LEFT"),
    ((P104[0], _Y_S2), "BOTTOM", (P104[0], _Y_S3), "TOP"),
    ((P105[0], _Y_S3), "RIGHT", (P105[0] + 1, _Y_S3), "LEFT"),
    ((P105[0], _Y_S3), "BOTTOM", (P105[0], _Y_S4), "TOP"),
    ((P106[0], _Y_S4), "RIGHT", (P106[0] + 1, _Y_S4), "LEFT"),
    ((P106[0], _Y_S4), "BOTTOM", (P106[0], _Y_S5), "TOP"),
    ((P106[0], _Y_S5), "RIGHT", (P106[0] + 1, _Y_S5), "LEFT"),
    ((P110[0] - 1, _Y_S1), "RIGHT", P110, "LEFT"),
    ((P109[0] - 1, _Y_S2), "RIGHT", P109, "LEFT"),
    ((P108[0] - 1, _Y_S3), "RIGHT", P108, "LEFT"),
    ((P107[0] - 1, _Y_S4), "RIGHT", P107, "LEFT"),
    (P110, "BOTTOM", (P110[0], _Y_S2), "TOP"),
    (P109, "BOTTOM", (P109[0], _Y_S3), "TOP"),
    (P108, "BOTTOM", (P108[0], _Y_S4), "TOP"),
    (P107, "BOTTOM", (P107[0], _Y_S5), "TOP"),
    ((P110[0] + 1, _Y_S1), "RIGHT", P112, "LEFT"),
    ((P112[0] + 1, _Y_S1), "RIGHT", (X1, _Y_S1), "LEFT"),
    (P112, "BOTTOM", (P112[0], _Y_S2), "TOP"),
]

# (x, y, text) or (x, y, text, loc_name). Default loc = CENT.
# S-1..S-5: mid-body cells, LOWCENT (under the rail).
_S_MID = (P106[0] + P107[0]) // 2
_Y_LAB = _Y_S5 + 2  # turnout number row under bowl
LABELS: list[tuple] = [
    # Row 2 only (west labels come from wire script)
    (X0 + 1, _Y_MW - 1, "West Lead"),
    (_S_MID, _Y_MW - 1, "SOUTH YARD"),
    (_S_MID, _Y_S1, "S-1", "LOWCENT"),
    (_S_MID, _Y_S2, "S-2", "LOWCENT"),
    (_S_MID, _Y_S3, "S-3", "LOWCENT"),
    (_S_MID, _Y_S4, "S-4", "LOWCENT"),
    (_S_MID, _Y_S5, "S-5", "LOWCENT"),
    (X1, _Y_MW - 1, "to Princess"),
    (X1, _Y_S2, "South Yard East"),
    (P112[0], _Y_S4, "EAST END"),
    (X0, _Y_S3, "To Barn"),
    (_S_MID, _Y_LAB, "Main East"),
    (P103[0], _Y_LAB, "103"),
    (P104[0], _Y_LAB, "104"),
    (P105[0], _Y_LAB, "105"),
    (P106[0], _Y_LAB, "106"),
    (P107[0], _Y_LAB, "107"),
    (P108[0], _Y_LAB, "108"),
    (P109[0], _Y_LAB, "109"),
    (P110[0], _Y_LAB, "110"),
    (P111[0], _Y_MW + 1, "111"),
    (P112[0], _Y_LAB, "112"),
]


def _tracks(sec: ET.Element) -> list[str]:
    tg = sec.find("TRACKGROUP")
    return [(t.text or "").strip() for t in tg.findall("TRACK")] if tg is not None else []


def _clear_edges(sec: ET.Element) -> None:
    for e in list(sec.findall("SEC_EDGE")):
        sec.remove(e)


def _set_tracks(sec: ET.Element, tracks: list[str]) -> None:
    tg = sec.find("TRACKGROUP")
    if tg is None:
        tg = ET.SubElement(sec, "TRACKGROUP")
    for old in list(tg.findall("TRACK")):
        tg.remove(old)
    for t in tracks:
        ET.SubElement(tg, "TRACK").text = t


def _label_sec(x: int, y: int, text: str, loc: str = "CENT") -> ET.Element:
    sec = ET.Element("SECTION", {"X": str(x), "Y": str(y)})
    ET.SubElement(
        sec,
        "SEC_NAME",
        {"LOC_NAME": loc, "NAME": text, "FONT_NAME": "FONT_LABEL"},
    )
    return sec


def _snapshot_row2_geometry(tp: ET.Element) -> None:
    """Save pre-compose row-2 TRACKGROUPs as sidecar (Designer SoR archive)."""
    root = ET.Element("DOCUMENT", {"VERSION": "3.1", "WIDTH": "1900", "HEIGHT": "900"})
    out_tp = ET.SubElement(root, "TRACKPLAN")
    n = 0
    for s in tp.findall("SECTION"):
        if s.find("TRACKGROUP") is None:
            continue
        if int(s.get("Y")) < ROW2_Y0:
            continue
        sec = ET.SubElement(out_tp, "SECTION", {"X": s.get("X"), "Y": s.get("Y")})
        tg = ET.SubElement(sec, "TRACKGROUP")
        for t in _tracks(s):
            ET.SubElement(tg, "TRACK").text = t
        n += 1
    out_tp.set("COLUMNS", tp.get("COLUMNS") or "40")
    out_tp.set("ROWS", tp.get("ROWS") or "22")
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(DESIGNER_ROW2, encoding="UTF-8", xml_declaration=True)
    print(f"wrote {DESIGNER_ROW2.relative_to(ROOT)}  ({n} track sections)")


def _replace_row2_tracks(tp: ET.Element, grid: dict[tuple[int, int], list[str]]) -> dict[tuple[int, int], ET.Element]:
    """Drop old row-2 track sections; install rebuilt grid."""
    for s in list(tp.findall("SECTION")):
        y = int(s.get("Y"))
        if y < ROW2_Y0:
            continue
        if s.find("TRACKGROUP") is not None or s.find("SEC_NAME") is not None:
            tp.remove(s)

    secs: dict[tuple[int, int], ET.Element] = {}
    for (x, y), tracks in sorted(grid.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        sec = ET.Element("SECTION", {"X": str(x), "Y": str(y)})
        tg = ET.SubElement(sec, "TRACKGROUP")
        for t in tracks:
            ET.SubElement(tg, "TRACK").text = t
        tp.append(sec)
        secs[(x, y)] = sec
    return secs


def _grid_from_tp(tp: ET.Element) -> dict[tuple[int, int], list[str]]:
    """Designer-preserved row-2 TRACKGROUPs (SoR when present)."""
    grid: dict[tuple[int, int], list[str]] = {}
    for s in tp.findall("SECTION"):
        if int(s.get("Y")) < ROW2_Y0 or s.find("TRACKGROUP") is None:
            continue
        grid[(int(s.get("X")), int(s.get("Y")))] = _tracks(s)
    return grid


def _wire_row2(tp: ET.Element) -> list[str]:
    # Rebuild when width SoR changes; else prefer live Designer geometry.
    grid = _grid_from_tp(tp)
    xs = [x for x, _y in grid] or [0]
    width_ok = min(xs) == X0 and max(xs) == X1
    if FORCE_REBUILD or len(grid) < 40 or not width_ok:
        grid = _build_row2_grid()
        secs = _replace_row2_tracks(tp, grid)
    else:
        # Drop row2 label-only cells (re-applied later); keep tracks.
        for s in list(tp.findall("SECTION")):
            if int(s.get("Y")) >= ROW2_Y0 and s.find("TRACKGROUP") is None:
                tp.remove(s)
        secs = {
            (int(s.get("X")), int(s.get("Y"))): s
            for s in tp.findall("SECTION")
            if s.find("TRACKGROUP") is not None and int(s.get("Y")) >= ROW2_Y0
        }
        for xy, (tracks, _os, _n, _tip) in PLANTS.items():
            if xy not in secs:
                sec = ET.Element("SECTION", {"X": str(xy[0]), "Y": str(xy[1])})
                tg = ET.SubElement(sec, "TRACKGROUP")
                for t in tracks:
                    ET.SubElement(tg, "TRACK").text = t
                tp.append(sec)
                secs[xy] = sec
            else:
                _set_tracks(secs[xy], tracks)
            grid[xy] = list(tracks)

    le.GRID.clear()
    le.PLANTS.clear()
    le.ANCHORS.clear()
    le.ANON.clear()
    le.LABELS.clear()

    for xy, tracks in grid.items():
        le.GRID[xy] = list(tracks)
        if xy in secs:
            _clear_edges(secs[xy])

    for xy, (tracks, os_name, normal, tip) in PLANTS.items():
        le.GRID[xy] = list(tracks)
        le.PLANTS[xy] = (os_name, normal, tip)

    for x, y, edge, name in ANCHORS:
        if (x, y) in le.GRID:
            le.nm((x, y), edge, name)

    for a, ae, b, be in CUTS:
        if a in le.GRID and b in le.GRID:
            le.cut(a, ae, b, be)

    for xy, tracks in le.GRID.items():
        if xy[0] >= X1 and "HORIZONTAL" in tracks:
            le.an(xy, "RIGHT")
        if xy[0] <= X0 and "HORIZONTAL" in tracks:
            le.an(xy, "LEFT")

    mini = ET.Element("TRACKPLAN")
    for (x, y), tracks in sorted(le.GRID.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        mini.append(le.make_section(x, y, tracks))
    disc = {n: "CTC" for n in set(le.ANCHORS.values())}
    le.wire(mini, disc)
    ctc._apply_station_labels(mini)
    for blk in mini.iter("BLOCK"):
        if blk.get("NAME"):
            blk.set("VISIBLE", "true")
            if not blk.get("DISCIPLINE"):
                blk.set("DISCIPLINE", "CTC")

    def _demote_non_plant_sp(tp_el: ET.Element, *, row2_only: bool = True) -> None:
        """H+UB drop under 111 etc. must not keep SWITCHPOINTS (SP→BLK on cuts).

        Only touch row-2 cells — never strip West Yard plants (101/100/119/…).
        """
        for s in tp_el.findall("SECTION"):
            if s.find("TRACKGROUP") is None:
                continue
            xy = (int(s.get("X")), int(s.get("Y")))
            if row2_only and xy[1] < ROW2_Y0:
                continue
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

    _demote_non_plant_sp(mini)
    errs = le.verify(mini)

    wired = {(int(s.get("X")), int(s.get("Y"))): s for s in mini.findall("SECTION")}
    for xy, wsec in wired.items():
        live = secs[xy]
        _clear_edges(live)
        for e in wsec.findall("SEC_EDGE"):
            live.append(e)
        _set_tracks(live, grid[xy])

    # Row-2 only — west plants keep SWITCHPOINTS from wire_hart_sheet_west_yard2.
    _demote_non_plant_sp(tp, row2_only=True)
    return errs


def _apply_labels(tp: ET.Element) -> None:
    """Apply SEC_NAME labels. S-1..S-5 colocate on mid-body cells (LOWCENT)."""
    by_xy = {(int(s.get("X")), int(s.get("Y"))): s for s in tp.findall("SECTION")}
    for s in list(tp.findall("SECTION")):
        y = int(s.get("Y"))
        if y < ROW2_Y0:
            continue
        sn = s.find("SEC_NAME")
        if sn is None:
            continue
        if s.find("TRACKGROUP") is None:
            tp.remove(s)
            by_xy.pop((int(s.get("X")), int(s.get("Y"))), None)
        else:
            s.remove(sn)

    by_xy = {(int(s.get("X")), int(s.get("Y"))): s for s in tp.findall("SECTION")}
    colocate_ok = {(_S_MID, y) for y in (_Y_S1, _Y_S2, _Y_S3, _Y_S4, _Y_S5)}
    for item in LABELS:
        x, y, text = item[0], item[1], item[2]
        loc = item[3] if len(item) > 3 else "CENT"
        if y < ROW2_Y0:
            continue
        xy = (x, y)
        if xy in by_xy and by_xy[xy].find("TRACKGROUP") is not None:
            if xy not in colocate_ok:
                print(f"skip label {xy} {text}")
                continue
            ET.SubElement(
                by_xy[xy],
                "SEC_NAME",
                {"LOC_NAME": loc, "NAME": text, "FONT_NAME": "FONT_LABEL"},
            )
            continue
        if xy in by_xy and by_xy[xy].find("TRACKGROUP") is None:
            tp.remove(by_xy[xy])
        lab = _label_sec(x, y, text, loc)
        tp.append(lab)
        by_xy[xy] = lab


def compose(west_path: Path = SRC) -> int:
    if not west_path.exists():
        print(f"missing {west_path}", file=sys.stderr)
        return 1

    root = ET.parse(west_path).getroot()
    tp = root.find("TRACKPLAN")
    assert tp is not None

    _snapshot_row2_geometry(tp)

    errs = _wire_row2(tp)
    if errs:
        print(f"ROW2 VERIFY FAIL ({len(errs)}):", file=sys.stderr)
        for e in errs[:25]:
            print(f"  {e}", file=sys.stderr)
        ok = False
    else:
        ok = True

    _apply_labels(tp)

    for blk in tp.iter("BLOCK"):
        if blk.get("NAME"):
            blk.set("VISIBLE", "true")
            if not blk.get("DISCIPLINE"):
                blk.set("DISCIPLINE", "CTC")

    if root.find(le.COMPRESSION_OFF_TAG) is None:
        root.append(ET.Element(le.COMPRESSION_OFF_TAG))

    max_x = max(int(s.get("X")) for s in tp.findall("SECTION"))
    max_y = max(int(s.get("Y")) for s in tp.findall("SECTION"))
    tp.set("COLUMNS", str(max(max_x + 2, 40)))
    tp.set("ROWS", str(max_y + 2))
    root.set("WIDTH", str(max(1900, (max_x + 2) * 52)))
    root.set("HEIGHT", str(max(700, (max_y + 2) * 52)))

    ET.indent(root, space="  ")
    for dest in (SRC, ACTIVE):
        ET.ElementTree(root).write(dest, encoding="UTF-8", xml_declaration=True)
        print(f"wrote {dest.relative_to(ROOT)}")

    subprocess.run(
        [sys.executable, str(ROOT / "cats/scripts/render_cats_panel.py"), str(SRC), str(SHOT)],
        check=False,
    )

    # ASCII preview of row2
    cells = {
        (int(s.get("X")), int(s.get("Y"))): _tracks(s)
        for s in tp.findall("SECTION")
        if s.find("TRACKGROUP") is not None and int(s.get("Y")) >= ROW2_Y0
    }
    print(f"row2 x={min(c[0] for c in cells)}..{max(c[0] for c in cells)} (match West Yard {X0}..{X1})")
    names = sorted(
        {
            b.get("NAME")
            for b in tp.iter("BLOCK")
            if b.get("NAME")
            and any(k in b.get("NAME") for k in ("103", "104", "105", "106", "107", "108", "109", "110", "111", "112"))
        }
    )
    print("row2 OS:", ", ".join(names))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(compose())
