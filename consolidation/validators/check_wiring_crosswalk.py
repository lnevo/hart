#!/usr/bin/env python3
"""Read-only wiring crosswalk: signal_wiring packed IDs vs IH beans in deploy tables."""
from __future__ import annotations

import csv
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WIRING = ROOT / "cats/data/signal_wiring.csv"
TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"


def text(el: ET.Element | None, child: str) -> str:
    if el is None:
        return ""
    v = el.findtext(child)
    return v.strip() if v else ""


def packed_ids_from_wiring() -> set[str]:
    ids: set[str] = set()
    if not WIRING.is_file():
        return ids
    with WIRING.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            packed = (row.get("packed") or "").strip()
            if packed.isdigit():
                ids.add(packed)
                continue
            node = (row.get("mqtt_node") or row.get("node") or "").strip()
            uid = (row.get("uid") or row.get("UID") or "").strip()
            if node.isdigit() and uid.isdigit():
                ids.add(str(int(node) * 100 + int(uid)))
    return ids


def ih_packed_from_tables(tree: ET.ElementTree) -> set[str]:
    ids: set[str] = set()
    for head in tree.getroot().iter("signalhead"):
        sn = text(head, "systemName") or (head.get("systemName") or "")
        m = re.match(r"IH(\d+)", sn)
        if m:
            ids.add(m.group(1))
    return ids


def main() -> int:
    if not TABLES.is_file():
        print(f"MISSING: {TABLES}", file=sys.stderr)
        return 2

    tree = ET.parse(TABLES)
    wiring_ids = packed_ids_from_wiring()
    bean_ids = ih_packed_from_tables(tree)

    print(f"Packed IDs from signal_wiring.csv: {len(wiring_ids)}")
    print(f"IH packed IDs from deploy tables: {len(bean_ids)}")

    if not wiring_ids:
        print("WARN: no wiring packed IDs parsed")
        return 0

    missing_beans = sorted(wiring_ids - bean_ids)
    extra_beans = sorted(bean_ids - wiring_ids)

    if missing_beans:
        print(f"INFO: {len(missing_beans)} wiring IDs without IH (first 5): {missing_beans[:5]}")
    if extra_beans:
        print(f"INFO: {len(extra_beans)} IH not in wiring CSV (first 5): {extra_beans[:5]}")

    overlap = wiring_ids & bean_ids
    ratio = len(overlap) / len(wiring_ids) if wiring_ids else 1.0
    print(f"Crosswalk overlap: {len(overlap)}/{len(wiring_ids)} ({ratio:.0%})")
    if ratio < 0.5:
        print("FAIL: crosswalk overlap below 50%")
        return 1
    print("OK: wiring crosswalk")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
