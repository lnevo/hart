#!/usr/bin/env python3
"""Apply dispatcher label hierarchy on hart panel CP / area labels (in-place XML)."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

HART = Path(__file__).resolve().parents[1] / "layouts" / "hart"
SRC = HART / "output" / "hart_prod.xml"

# text -> (size, style)  style 1=bold
HIERARCHY = {
    "Neville Island": ("28", "1"),
    "Brick": ("18", "1"),
    "Plane": ("18", "1"),
    "East End": ("18", "1"),
    "Princess": ("18", "1"),
    "West Yard": ("16", "0"),
    "South Yard": ("16", "0"),
    "Industries": ("16", "0"),
}


def main() -> int:
    tree = ET.parse(SRC)
    root = tree.getroot()
    n = 0
    for el in root.iter("positionablelabel"):
        text = el.get("text") or ""
        if text not in HIERARCHY:
            continue
        size, style = HIERARCHY[text]
        el.set("size", size)
        el.set("style", style)
        n += 1

    out = HART / "output" / "hart_blocked.xml"
    tree.write(out, encoding="UTF-8", xml_declaration=True)
    shutil.copy2(out, HART / "output" / "hart_prod.xml")
    shutil.copy2(out, HART / "authoritative" / "hart.xml")
    print(f"Updated {n} labels → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
