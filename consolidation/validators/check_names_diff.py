#!/usr/bin/env python3
"""Read-only: diff public_name_map identity rows vs bean userName in deploy tables."""
from __future__ import annotations

import csv
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "consolidation" / "scripts"))

from virtual_stub_masts import virtual_mast_names_from_map

MAP_CSV = ROOT / "jmri/layouts/hart/data/public_name_map.csv"
TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"


def text(el: ET.Element | None, child: str) -> str:
    if el is None:
        return ""
    v = el.findtext(child)
    return v.strip() if v else ""


def attr_or_child(el: ET.Element, name: str) -> str:
    return (el.get(name) or text(el, name)).strip()


def identity_names_from_map() -> set[str]:
    names: set[str] = set()
    with MAP_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            current = (row.get("current") or "").strip()
            proposed = (row.get("proposed") or "").strip()
            name = current if current == proposed or not proposed else proposed
            if name and not name.startswith("DCC Switch"):
                names.add(name)
    return names


def bean_usernames(xml_path: Path) -> set[str]:
    tree = ET.parse(xml_path)
    names: set[str] = set()
    for el in tree.getroot().iter():
        if el.tag in ("turnout", "sensor", "block", "signalhead", "signalmast", "section"):
            un = attr_or_child(el, "userName")
            if un:
                names.add(un)
    return names


def main() -> int:
    if not MAP_CSV.is_file() or not TABLES.is_file():
        print("MISSING inputs", file=sys.stderr)
        return 2

    virtual_masts = virtual_mast_names_from_map(MAP_CSV)
    map_names = identity_names_from_map()
    bean_names = bean_usernames(TABLES)

    missing = sorted(n for n in map_names if n not in bean_names)
    critical = [
        n
        for n in missing
        if n.startswith(("Mast ", "Head ", "Switch ", "OS ", "Track ", "Block "))
        and n not in virtual_masts
    ]
    virtual_missing = sorted(n for n in missing if n in virtual_masts)

    print(f"Map names (excl DCC comment rows): {len(map_names)}")
    print(f"Bean userNames in deploy tables: {len(bean_names)}")
    print(f"Map names not on beans: {len(missing)}")
    if virtual_missing:
        print(f"INFO: {len(virtual_missing)} virtual stub masts excluded (D2f map-only):")
        for n in virtual_missing:
            print(f"  - {n}")
    if critical:
        print(f"FAIL: {len(critical)} equipment-like map rows not on beans:")
        for n in critical[:20]:
            print(f"  - {n}")
        return 1
    print("OK: names diff within consolidation tolerance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
