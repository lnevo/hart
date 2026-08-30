#!/usr/bin/env python3
"""Apply the HART dispatcher label hierarchy without replacing config files.

The canonical writable target is tables/new_tables.xml.  Output files are
patched independently when ``--sync-output`` is requested so their CTC/SML
content cannot be lost through a whole-file copy.
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HART = ROOT / "jmri/layouts/hart"
SRC = ROOT / "tables/new_tables.xml"
OUTPUTS = [HART / "output/tables.xml", HART / "output/hart_prod.xml"]

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


def apply(path: Path) -> int:
    tree = ET.parse(path)
    root = tree.getroot()
    editors = [
        le for le in root.findall("LayoutEditor")
        if len(le.findall("tracksegment")) >= 90
    ]
    if len(editors) != 1:
        raise SystemExit(f"expected one HART geometry panel in {path}, found {len(editors)}")
    le = editors[0]
    n = 0
    for el in le.iter("positionablelabel"):
        text = el.get("text") or ""
        if text not in HIERARCHY:
            continue
        size, style = HIERARCHY[text]
        el.set("size", size)
        el.set("style", style)
        n += 1

    tree.write(path, encoding="UTF-8", xml_declaration=True)
    print(f"Updated {n} labels → {path}")
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", type=Path, default=SRC)
    ap.add_argument("--sync-output", action="store_true")
    args = ap.parse_args()

    apply(args.panel)
    if args.sync_output and args.panel.resolve() == SRC.resolve():
        for output in OUTPUTS:
            apply(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
