#!/usr/bin/env python3
"""Remove empty duplicate <block> rows that share a userName with a populated row.

linear6/hart inherited pairs: one block with occupancy sensor, one without.
Keeps the row that has occupancysensor set (or the last if neither).
Rewrites hart output/prod/authoritative.
"""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

HART = Path(__file__).resolve().parents[1] / "layouts" / "hart"
SRC = HART / "output" / "hart_prod.xml"


def main() -> int:
    tree = ET.parse(SRC)
    root = tree.getroot()
    blocks_parent = root.find("blocks")
    if blocks_parent is None:
        raise SystemExit("no <blocks>")

    by_name: dict[str, list[ET.Element]] = defaultdict(list)
    for b in list(blocks_parent.findall("block")):
        un = (b.findtext("userName") or "").strip()
        if un:
            by_name[un].append(b)

    removed = 0
    for un, els in by_name.items():
        if len(els) < 2:
            continue
        # Prefer element with non-empty occupancysensor
        ranked = sorted(
            els,
            key=lambda e: (
                0 if (e.findtext("occupancysensor") or "").strip() else 1,
                e.get("systemName") or "",
            ),
        )
        keep = ranked[0]
        for e in els:
            if e is keep:
                continue
            blocks_parent.remove(e)
            removed += 1

    out = HART / "output" / "hart_blocked.xml"
    tree.write(out, encoding="UTF-8", xml_declaration=True)
    shutil.copy2(out, HART / "output" / "hart_prod.xml")
    shutil.copy2(out, HART / "authoritative" / "hart.xml")
    print(f"Removed {removed} empty duplicate block rows → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
