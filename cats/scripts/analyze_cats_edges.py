#!/usr/bin/env python3
"""Report SEC_EDGE joint typing for a CATS panel.

Edge runtime class (cats/layout/items/EdgeBuilder):
  child BLOCK        -> BlkEdge   (AbstractTrackEdge)
  child SWITCHPOINTS -> OSEdge / PtsEdge (AbstractTrackEdge)
  neither            -> plain SecEdge (NOT AbstractTrackEdge)

Usage:
  python3 cats/scripts/analyze_cats_edges.py FILE...
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

OPP = {
    "LEFT": ("RIGHT", -1, 0),
    "RIGHT": ("LEFT", 1, 0),
    "TOP": ("BOTTOM", 0, -1),
    "BOTTOM": ("TOP", 0, 1),
}

# track type -> the two edges it terminates on
TRACK_ENDS = {
    "HORIZONTAL": ("LEFT", "RIGHT"),
    "VERTICAL": ("TOP", "BOTTOM"),
    "UPPERSLASH": ("TOP", "LEFT"),
    "LOWERSLASH": ("BOTTOM", "RIGHT"),
    "UPPERBACKSLASH": ("TOP", "RIGHT"),
    "LOWERBACKSLASH": ("BOTTOM", "LEFT"),
}


def edge_kind(e: ET.Element) -> str:
    if e.find("SWITCHPOINTS") is not None:
        return "PTS"
    if e.find("BLOCK") is not None:
        b = e.find("BLOCK")
        return "BLK*" if b.get("NAME") else "BLK"
    return "PLAIN"


def sections(root: ET.Element) -> dict[tuple[int, int], ET.Element]:
    tp = root.find("TRACKPLAN")
    out = {}
    for s in tp.findall("SECTION"):
        if s.find("TRACKGROUP") is None:
            continue
        out[(int(s.get("X")), int(s.get("Y")))] = s
    return out


def tracks_of(sec: ET.Element) -> list[str]:
    tg = sec.find("TRACKGROUP")
    return [] if tg is None else [(t.text or "").strip() for t in tg.findall("TRACK")]


def analyze(path: Path) -> Counter:
    root = ET.parse(path).getroot()
    secs = sections(root)
    pairs: Counter = Counter()
    problems: list[str] = []

    for (x, y), sec in sorted(secs.items()):
        kinds = {e.get("EDGE"): edge_kind(e) for e in sec.findall("SEC_EDGE")}
        used = set()
        for t in tracks_of(sec):
            used.update(TRACK_ENDS.get(t, ()))
        missing = used - set(kinds)
        if missing:
            problems.append(f"({x},{y}) tracks need edges {sorted(missing)}; has {sorted(kinds)}")
        extra = set(kinds) - used
        if extra:
            problems.append(f"({x},{y}) edge(s) {sorted(extra)} with no track end")
        for e in sec.findall("SEC_EDGE"):
            if e.find("BLOCK") is not None and e.find("SWITCHPOINTS") is not None:
                problems.append(f"({x},{y}) {e.get('EDGE')} has BLOCK+SWITCHPOINTS")

        for ed, k in kinds.items():
            ned, dx, dy = OPP[ed]
            n = secs.get((x + dx, y + dy))
            if n is None:
                pairs[f"{k} <-> (none)"] += 1
                continue
            nk = None
            for ee in n.findall("SEC_EDGE"):
                if ee.get("EDGE") == ned:
                    nk = edge_kind(ee)
            if nk is None:
                pairs[f"{k} <-> (no-edge)"] += 1
                continue
            pairs["  <->  ".join(sorted([k, nk]))] += 1

    print(f"--- {path.name}  sections={len(secs)}")
    for k, v in sorted(pairs.items()):
        print(f"    {v:4d}  {k}")
    for p in problems:
        print(f"    !! {p}")
    return pairs


def main() -> None:
    total: Counter = Counter()
    for a in sys.argv[1:]:
        total += analyze(Path(a))
    if len(sys.argv) > 2:
        print("=== TOTAL")
        for k, v in sorted(total.items()):
            print(f"    {v:4d}  {k}")


if __name__ == "__main__":
    main()
