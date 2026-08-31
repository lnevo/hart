#!/usr/bin/env python3
"""Rewrite HART Layout Editor DCC switch labels (100–119) to SW-<plant#>.

Plant numbers come from ``public_name_map.csv`` (proposed ``Switch N`` + ``DCC:``).
Canonical writable target: ``tables/new_tables.xml``.
"""

from __future__ import annotations

import argparse
import csv
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HART = ROOT / "jmri/layouts/hart"
MAP = HART / "data/public_name_map.csv"
SRC = ROOT / "tables/new_tables.xml"
OUTPUTS = [HART / "output/tables.xml", HART / "output/hart_prod.xml"]

# Absolute x for specific plant labels (after rename).
# Engine-house row (y=213): even 50px centers over EH stubs→SW-13.
LABEL_X = {
    "9": "548",
    "11": "598",
    "13": "648",
}


def dcc_to_sw_label(map_path: Path = MAP) -> dict[str, str]:
    """DCC address string → ``SW-N`` from non-historical public_name_map rows."""
    out: dict[str, str] = {}
    with map_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("layer") != "turnout":
                continue
            if "historical" in (row.get("notes") or ""):
                continue
            m = re.search(r"DCC:\s*(\d+)", row.get("comment") or "")
            pm = re.fullmatch(r"Switch\s+(\d+)", (row.get("proposed") or "").strip())
            if m and pm:
                out[m.group(1)] = f"SW-{pm.group(1)}"
    return out


def _hart_le(root: ET.Element) -> ET.Element:
    editors = [
        le
        for le in root.findall("LayoutEditor")
        if len(le.findall("tracksegment")) >= 90
    ]
    if len(editors) != 1:
        raise SystemExit(f"expected one HART geometry panel, found {len(editors)}")
    return editors[0]


def _is_plant_label(el: ET.Element) -> bool:
    if el.get("blue") == "128" and el.get("red") == "0":
        return True
    return el.get("level") == "4"


def apply(path: Path, mapping: dict[str, str]) -> int:
    tree = ET.parse(path)
    le = _hart_le(tree.getroot())
    n = 0
    for el in le.findall("positionablelabel"):
        if not _is_plant_label(el):
            continue
        text = el.get("text") or ""
        plant = None
        if text in mapping:
            new = mapping[text]
            plant = new.split("-", 1)[1]
            el.set("text", new)
            n += 1
        else:
            m = re.fullmatch(r"(?:Sw\s+|SW-)(\d+)", text)
            if not m:
                continue
            plant = m.group(1)
            want = f"SW-{plant}"
            if text != want:
                el.set("text", want)
                n += 1
        if plant in LABEL_X:
            el.set("x", LABEL_X[plant])
    tree.write(path, encoding="UTF-8", xml_declaration=True)
    print(f"Updated {n} switch labels → {path}")
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", type=Path, default=SRC)
    ap.add_argument("--sync-output", action="store_true")
    args = ap.parse_args()
    mapping = dcc_to_sw_label()
    if len(mapping) != 20:
        raise SystemExit(f"expected 20 DCC→SW mappings, got {len(mapping)}")
    apply(args.panel, mapping)
    if args.sync_output and args.panel.resolve() == SRC.resolve():
        for output in OUTPUTS:
            apply(output, mapping)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
