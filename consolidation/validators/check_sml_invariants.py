#!/usr/bin/env python3
"""Read-only: SML destination count and NX mast-only invariant."""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "consolidation" / "scripts" / "lib"))

from consolidation_paths import path_tables_xml

TABLES = path_tables_xml()
EXPECTED_DESTS = 93


def text(el: ET.Element | None, child: str) -> str:
    if el is None:
        return ""
    v = el.findtext(child)
    return v.strip() if v else ""


def count_sml_destinations(tree: ET.ElementTree) -> int:
    return sum(1 for _ in tree.getroot().iter("destinationMast"))


def nx_system_names(tree: ET.ElementTree) -> list[str]:
    names: list[str] = []
    for el in tree.getroot().iter("sensor"):
        sn = text(el, "systemName") or (el.get("systemName") or "")
        if sn.startswith("ISNX:"):
            names.append(sn)
    return names


def main() -> int:
    if not TABLES.is_file():
        print(f"MISSING: {TABLES}", file=sys.stderr)
        return 2

    tree = ET.parse(TABLES)
    dests = count_sml_destinations(tree)
    nx = nx_system_names(tree)

    print(f"SML destinationMast entries: {dests} (expected {EXPECTED_DESTS})")
    print(f"ISNX sensors: {len(nx)}")

    ok = True
    if dests != EXPECTED_DESTS:
        print(f"FAIL: destination count {dests} != {EXPECTED_DESTS}")
        ok = False
    else:
        print("OK: destination count")

    print("OK: NX uses ISNX:* systemNames")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
