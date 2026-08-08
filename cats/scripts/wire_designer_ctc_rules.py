#!/usr/bin/env python3
"""Build the HART Digicon panel from the user's CATS Designer drawing.

One command rebuild:

    python3 cats/scripts/wire_designer_ctc_rules.py --mqtt

Writes
    cats/panels/HART_magnet.xml         magnet board (no JMRI IO)
    cats/panels/HART_designer_wired.xml identical copy, kept for diffing
    cats/panels/HART.xml                + MQTT occupancy (with --mqtt)

TRACKPLAN geometry comes verbatim from cats/panels/HART_designer_raw.xml (the
user's Designer draw).  Only the Armstrong *header* (fonts, colours, signal
template, stores) is reused as a shell.

Wiring rules are taken from the CATS sources in tools/cats/src-repo and the
golden CTC-Tests panels (Chubb_CTC.xml is the reference for tight plants):

R1  Track geometry -> edges
      HORIZONTAL      LEFT  <-> RIGHT
      VERTICAL        TOP   <-> BOTTOM
      UPPERSLASH      LEFT  <-> TOP
      LOWERSLASH      RIGHT <-> BOTTOM
      UPPERBACKSLASH  RIGHT <-> TOP
      LOWERBACKSLASH  LEFT  <-> BOTTOM
    A cell holding two tracks is a turnout; the edge shared by both tracks is
    the points ("throat") edge and carries SWITCHPOINTS.  The other two edges
    are the routes, and ROUTEINFO/ROUTEID uses those edge names.

R2  BLOCK and SWITCHPOINTS must never share one SEC_EDGE (EdgeBuilder).

R3  A points edge's facing neighbour edge must stay plain.  BlkEdge.
    neighborOccupied() does an unchecked (BlkEdge) getNeighbor() cast, so a
    BLOCK opposite SWITCHPOINTS is a ClassCastException.

R4  Any SEC_EDGE carrying a BLOCK whose neighbour cell exists must be met by a
    neighbour edge that also carries a BLOCK (BlkEdge <-> BlkEdge).  Same cast.
    A BLOCK on an edge with no neighbour cell (panel rim / end of track) is
    fine - see CTC-Tests/XEdgeCTC.xml.

R5  PtsEdge.propagateBlock() forwards the block to its joint, so blocks flow
    *through* turnouts.  A "block region" is therefore any set of cells that is
    not separated by a BLOCK edge, and every region needs exactly one named
    VISIBLE block or TrackGroup.isVisible() returns false and the cell is not
    painted at all.

R6  BLOCK *is* legal on a turnout cell's non-points edges - Chubb_CTC.xml
    (29,4) carries an anonymous BLOCK on both frog legs and (29,5)/(27,5) carry
    named blocks on a frog leg.

R7  DISCIPLINE only accepts UNDEFINED/ABS/APB/CTC/DTC (Discipline.java), so the
    YARD rows in cats/data/occupancy_bindings.csv are written as CTC.

Because a plant's throat joint can never be a block boundary (R3), the block
holding an OS always reaches back through its approach cell - exactly what
Chubb does (Block 14 = approach (12,3) + OS (13,3)).  Where the Designer draw
leaves only one cell between two plants the two OS blocks unavoidably merge;
those cases are listed in MERGED_NOTES and in cats/docs/DESIGNER_DRAWING_REVIEW.md.

Do NOT invent South Yard / East End / Princess cells here. Draw them in Designer
(Gates 3–5), save into HART_designer_raw.xml, then extend anchors only.
"""

from __future__ import annotations

import argparse
import copy
import csv
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "cats/panels"
RAW = OUT_DIR / "HART_designer_raw.xml"
BINDINGS = ROOT / "cats/data/occupancy_bindings.csv"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cats_paths import armstrong_magnet  # noqa: E402

ARM = armstrong_magnet()

WIDTH, HEIGHT = "560", "380"

# cats/gui/Compression.java: "Compress Screen" defaults to true, which shrinks
# every horizontal-only column to a sliver so a 27 cell board renders postage
# stamp sized.  BooleanGui.newElement() sets the flag to !default purely from
# the element being present, so a bare <COMPRESSIONTAG /> turns compression off
# so every column is a full cell wide.
#
# Screen.FixSize is hardcoded true, so CATS never scales cells to the window:
# GridTile.Size is a runtime-only 30x30 default that is not stored in the panel
# file.  WIDTH/HEIGHT below therefore just size the frame to the drawn board;
# to enlarge the cells use the CTC Panel menu Appearance -> Grid Size.
COMPRESSION_OFF_TAG = "COMPRESSIONTAG"

# --- R1 -----------------------------------------------------------------
TRACK_ENDS: dict[str, frozenset[str]] = {
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

# ONLY rim cells the Designer draw omitted. No invented South Yard / East End /
# Princess geometry — that produced junk. Gates 3–5 must be drawn in Designer.
EXTRA_CELLS: dict[Cell, list[str]] = {
    (1, 5): ["HORIZONTAL"],  # Main West rim
    (11, 2): ["HORIZONTAL"],  # Main East rim
}

# cell -> (block name, normal route edge) — Designer Gate 1 only
PLANTS: dict[Cell, tuple[str, str]] = {
    (3, 5): ("OS 100 (Brick)", "TOP"),
    (5, 5): ("OS 101 (Brick)", "RIGHT"),
    (5, 3): ("OS 102 (Plane)", "RIGHT"),
    (8, 3): ("OS 116 (West Yard)", "RIGHT"),
    (8, 2): ("OS 117 (West Yard)", "LEFT"),
    (9, 2): ("OS 117b (West Yard)", "LEFT"),
}

BLOCK_ANCHORS: dict[tuple[Cell, str], str] = {
    ((1, 5), "LEFT"): "Main West",
    ((2, 5), "LEFT"): "OS 100 (Brick)",
    ((4, 5), "LEFT"): "OS 101 (Brick)",
    ((6, 5), "LEFT"): "West Yard 2",
    ((5, 4), "BOTTOM"): "West Yard 1",
    ((3, 4), "BOTTOM"): "Block 100-102",
    ((4, 3), "BOTTOM"): "OS 102 (Plane)",
    ((6, 3), "LEFT"): "East Main Ext",
    ((7, 3), "LEFT"): "OS 116 (West Yard)",
    ((9, 3), "LEFT"): "Yard T1",
    ((5, 2), "BOTTOM"): "Yard T6",
    ((8, 2), "LEFT"): "OS 117 (West Yard)",
    ((9, 1), "BOTTOM"): "Yard T9",
    ((11, 2), "LEFT"): "Main East",
}

ANON_BLOCKS: set[tuple[Cell, str]] = {
    ((1, 5), "RIGHT"),
    ((3, 5), "RIGHT"),
    ((3, 5), "TOP"),
    ((5, 5), "RIGHT"),
    ((5, 5), "TOP"),
    ((7, 5), "RIGHT"),
    ((7, 4), "RIGHT"),
    ((4, 4), "TOP"),
    ((5, 3), "RIGHT"),
    ((5, 3), "TOP"),
    ((6, 3), "RIGHT"),
    ((8, 3), "RIGHT"),
    ((8, 3), "TOP"),
    ((9, 3), "RIGHT"),
    ((7, 2), "RIGHT"),
    ((8, 2), "BOTTOM"),
    ((9, 2), "TOP"),
    ((10, 2), "RIGHT"),
    ((11, 2), "RIGHT"),
    ((8, 1), "LEFT"),
}

MERGED_NOTES = {
    "cell (4,5)": (
        "is inside OS 101 (Brick) — only one cell between SW100 and SW101."
    ),
    "OS 117b at (9,2)": (
        "is inside OS 117 (West Yard) — crossover throats are adjacent."
    ),
}

LABELS: list[tuple[int, int, str]] = [
    (2, 4, "Main West"),
    (3, 6, "Brick 100"),
    (5, 6, "OS 101"),
    (7, 6, "W Yard 2"),
    (2, 3, "100-102"),
    (3, 2, "Plane 102"),
    (6, 1, "East Main Ext"),
    (10, 5, "117 / 116"),
    (11, 3, "Main East"),
]


# --------------------------------------------------------------------------
def load_disciplines() -> dict[str, str]:
    """JMRI block user name -> CATS discipline (R7: YARD is not a CATS value)."""
    out: dict[str, str] = {}
    with BINDINGS.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            disc = (row.get("cats_discipline") or "CTC").strip().upper()
            if disc not in {"UNDEFINED", "ABS", "APB", "CTC", "DTC"}:
                disc = "CTC"
            out[row["block_user_name"].strip()] = disc
    return out


def tracks_of(sec: ET.Element) -> list[str]:
    tg = sec.find("TRACKGROUP")
    if tg is None:
        return []
    return [(t.text or "").strip() for t in tg.findall("TRACK")]


def points_edge(tracks: list[str]) -> str | None:
    """R1: the edge shared by both tracks of a two-track (turnout) cell."""
    if len(tracks) != 2:
        return None
    shared = TRACK_ENDS[tracks[0]] & TRACK_ENDS[tracks[1]]
    if len(shared) != 1:
        return None
    return next(iter(shared))


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


def build_trackplan(raw: Path) -> tuple[ET.Element, dict[Cell, list[str]]]:
    user = ET.parse(raw).getroot()
    src = user.find("TRACKPLAN")
    if src is None:
        raise SystemExit(f"no TRACKPLAN in {raw}")

    grid: dict[Cell, list[str]] = {}
    for s in src.findall("SECTION"):
        if s.find("TRACKGROUP") is None:
            continue
        grid[(int(s.get("X")), int(s.get("Y")))] = tracks_of(s)
    for xy, kind in EXTRA_CELLS.items():
        grid.setdefault(xy, list(kind))

    tp = ET.Element("TRACKPLAN")
    for (x, y), tracks in sorted(grid.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        tp.append(make_section(x, y, tracks))
    cols = max(x for x, _ in grid) + 1
    rows = max(y for _, y in grid) + 2  # +1 label row under the board
    tp.set("COLUMNS", str(cols))
    tp.set("ROWS", str(rows))
    return tp, grid


def wire(tp: ET.Element, grid: dict[Cell, list[str]], disc: dict[str, str]) -> None:
    secs = {(int(s.get("X")), int(s.get("Y"))): s for s in tp.findall("SECTION")}

    for xy, sec in secs.items():
        tracks = grid[xy]
        pts = points_edge(tracks)
        for edge in cell_edges(tracks):
            se = ET.SubElement(sec, "SEC_EDGE", {"EDGE": edge})
            if edge == pts:
                # R1/R2: points on the shared edge, routes named for the legs.
                name, normal = PLANTS.get(xy, ("", ""))
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
            if key in BLOCK_ANCHORS:
                bname = BLOCK_ANCHORS[key]
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
            elif key in ANON_BLOCKS:
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


# --------------------------------------------------------------------------
def regions(grid: dict[Cell, list[str]], tp: ET.Element) -> list[set[Cell]]:
    """R5: connected cells not separated by a BLOCK edge."""
    blocked: set[tuple[Cell, str]] = set()
    for s in tp.findall("SECTION"):
        xy = (int(s.get("X")), int(s.get("Y")))
        for e in s.findall("SEC_EDGE"):
            if e.find("BLOCK") is not None:
                blocked.add((xy, e.get("EDGE")))

    seen: set[Cell] = set()
    out: list[set[Cell]] = []
    for start in grid:
        if start in seen:
            continue
        comp: set[Cell] = {start}
        stack = [start]
        seen.add(start)
        while stack:
            cur = stack.pop()
            for edge in cell_edges(grid[cur]):
                if (cur, edge) in blocked:
                    continue
                dx, dy = STEP[edge]
                nb = (cur[0] + dx, cur[1] + dy)
                if nb not in grid or nb in seen:
                    continue
                back = OPPOSITE[edge]
                if back not in cell_edges(grid[nb]) or (nb, back) in blocked:
                    continue
                seen.add(nb)
                comp.add(nb)
                stack.append(nb)
        out.append(comp)
    return out


def verify(tp: ET.Element, grid: dict[Cell, list[str]]) -> list[str]:
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
                errs.append(f"R2 {xy} {ed}: BLOCK and SWITCHPOINTS share an edge")
            kind[(xy, ed)] = "SP" if has_s else ("BLK" if has_b else "plain")

    for (xy, ed), k in kind.items():
        dx, dy = STEP[ed]
        nb = (xy[0] + dx, xy[1] + dy)
        other = kind.get((nb, OPPOSITE[ed]))
        if other is None:
            continue
        if k == "SP" and other == "BLK":
            errs.append(f"R3 {xy} {ed}: SWITCHPOINTS faces BLOCK at {nb}")
        if k == "BLK" and other != "BLK":
            errs.append(f"R4 {xy} {ed}: BLOCK faces {other} at {nb}")

    named: dict[Cell, str] = {}
    for xy, s in secs.items():
        for e in s.findall("SEC_EDGE"):
            b = e.find("BLOCK")
            if b is not None and b.get("NAME"):
                named.setdefault(xy, b.get("NAME"))

    for comp in regions(grid, tp):
        names = sorted({named[c] for c in comp if c in named})
        if not names:
            errs.append(f"R5 region {sorted(comp)} has no named block - will not paint")
        elif len(names) > 1:
            errs.append(f"R5 region {sorted(comp)} has {len(names)} names: {names}")
    return errs


# --------------------------------------------------------------------------
def build() -> tuple[ET.Element, dict[Cell, list[str]], ET.Element]:
    root = ET.parse(ARM).getroot()
    for ops in root.iter("OPERATIONS"):
        ops.set("CONNECT", "false")
    for old in list(root.findall("TRACKPLAN")):
        root.remove(old)
    tp, grid = build_trackplan(RAW)
    wire(tp, grid, load_disciplines())
    if root.find(COMPRESSION_OFF_TAG) is None:
        root.append(ET.Element(COMPRESSION_OFF_TAG))
    root.append(tp)
    root.set("WIDTH", WIDTH)
    root.set("HEIGHT", HEIGHT)
    return root, grid, tp


def main() -> int:
    ap = argparse.ArgumentParser(description="Build HART Digicon from Designer draw")
    ap.add_argument("--mqtt", action="store_true", help="also write HART.xml with MQTT occupancy")
    args = ap.parse_args()

    root, grid, tp = build()
    errs = verify(tp, grid)
    for e in errs:
        print(f"VERIFY FAIL: {e}", file=sys.stderr)
    if errs:
        return 1

    ET.indent(root, space="  ")
    magnet = OUT_DIR / "HART_magnet.xml"
    wired = OUT_DIR / "HART_designer_wired.xml"
    for out in (magnet, wired):
        ET.ElementTree(root).write(out, encoding="UTF-8", xml_declaration=True)
        print(f"wrote {out.relative_to(ROOT)}")

    names = sorted({b.get("NAME") for b in root.iter("BLOCK") if b.get("NAME")})
    print(f"grid {tp.get('COLUMNS')}x{tp.get('ROWS')}  track cells {len(grid)}  window {WIDTH}x{HEIGHT}")
    print(f"named blocks ({len(names)}): {', '.join(names)}")
    print(f"regions: {len(regions(grid, tp))} (each has exactly one named block)")

    if args.mqtt:
        sys.path.insert(0, str(ROOT / "cats/scripts"))
        import jmri_to_cats_digicon as gen

        mqtt_root = copy.deepcopy(root)
        gen.ensure_mqtt(mqtt_root)
        gen.wire_occupancy(mqtt_root, gen.load_occupancy())
        for ops in mqtt_root.iter("OPERATIONS"):
            ops.set("CONNECT", "true")
        gen.ensure_hart_trains(mqtt_root)
        ET.indent(mqtt_root, space="  ")
        out = OUT_DIR / "HART.xml"
        ET.ElementTree(mqtt_root).write(out, encoding="UTF-8", xml_declaration=True)
        wired_occ = sorted(
            b.get("NAME")
            for b in mqtt_root.iter("BLOCK")
            if b.get("NAME") and b.find("OCCUPIEDSPEC") is not None
        )
        print(f"wrote {out.relative_to(ROOT)}")
        print(f"MQTT occupancy on {len(wired_occ)}/{len(names)}: {', '.join(wired_occ)}")
        missing = [n for n in names if n not in wired_occ]
        if missing:
            print(f"no JMRI occupancy sensor: {', '.join(missing)}")

    for k, v in MERGED_NOTES.items():
        print(f"note: {k} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
