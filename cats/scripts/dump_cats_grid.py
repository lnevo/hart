#!/usr/bin/env python3
"""Compact dump of a CATS panel TRACKPLAN: cell -> tracks + edge kinds.

Usage: python3 cats/scripts/dump_cats_grid.py <panel.xml> [...]
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EDGES = ("LEFT", "RIGHT", "TOP", "BOTTOM")


def edge_kind(e: ET.Element) -> str:
    blk = e.find("BLOCK")
    if e.find("SWITCHPOINTS") is not None:
        return "SP"
    if e.find("CROSSINGEDGE") is not None:
        return "XING"
    if blk is not None:
        name = blk.get("NAME")
        vis = blk.get("VISIBLE")
        if name:
            return f"BLK[{name}{'' if vis == 'true' else ' !vis'}]"
        return "BLK[-]"
    return "plain"


def routes(e: ET.Element) -> str:
    sp = e.find("SWITCHPOINTS")
    if sp is None:
        return ""
    parts = []
    for r in sp.findall("ROUTEINFO"):
        parts.append(r.get("ROUTEID") + ("*" if r.get("NORMAL") == "true" else ""))
    return "{" + ",".join(parts) + "}"


def dump(path: Path) -> None:
    root = ET.parse(path).getroot()
    tp = root.find("TRACKPLAN")
    print("=" * 78)
    print(f"{path}  WIDTH={root.get('WIDTH')} HEIGHT={root.get('HEIGHT')} {tp.attrib}")
    cells = []
    for s in tp.findall("SECTION"):
        x, y = int(s.get("X")), int(s.get("Y"))
        tg = s.find("TRACKGROUP")
        if tg is None:
            nm = s.find("SEC_NAME")
            if nm is not None:
                cells.append((y, x, f"({x},{y}) LABEL {nm.get('NAME')!r}"))
            continue
        tracks = "+".join((t.text or "").strip() for t in tg.findall("TRACK"))
        eds = []
        for e in s.findall("SEC_EDGE"):
            eds.append(f"{e.get('EDGE')}={edge_kind(e)}{routes(e)}")
        cells.append((y, x, f"({x},{y}) {tracks:<28} " + "  ".join(eds)))
    for _y, _x, line in sorted(cells):
        print("  " + line)
    names = sorted({b.get("NAME") for b in root.iter("BLOCK") if b.get("NAME")})
    print(f"  -- track cells: {sum(1 for s in tp.findall('SECTION') if s.find('TRACKGROUP') is not None)}")
    print(f"  -- named blocks ({len(names)}): {', '.join(names)}")


if __name__ == "__main__":
    for a in sys.argv[1:]:
        dump(Path(a))
