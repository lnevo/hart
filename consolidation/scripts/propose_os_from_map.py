#!/usr/bin/env python3
"""Draft: OS block names for phase02 from public_name_map (D2 migration prep).

Read-only — prints CSV to stdout; does not write live files.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "jmri/layouts/hart/data/public_name_map.csv"
LEGACY = ROOT / "jmri/layouts/hart/data/block_display_names.csv"


def os_from_legacy() -> set[str]:
    if not LEGACY.is_file():
        return set()
    with LEGACY.open(newline="", encoding="utf-8") as f:
        return {
            (r.get("public_user_name") or "").strip()
            for r in csv.DictReader(f)
            if (r.get("role") or "").strip() == "os"
        }


def os_from_map() -> set[str]:
    names: set[str] = set()
    with MAP.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            layer = (row.get("layer") or "").strip()
            proposed = (row.get("proposed") or row.get("current") or "").strip()
            if not proposed:
                continue
            if layer == "block" and proposed.startswith("OS "):
                names.add(proposed)
            if layer == "turnout" and "OS" in proposed:
                names.add(proposed)
    return names


def main() -> int:
    legacy = os_from_legacy()
    derived = os_from_map()
    print(f"legacy block_display OS count: {len(legacy)}")
    print(f"derived from map OS count: {len(derived)}")
    only_legacy = sorted(legacy - derived)
    only_map = sorted(derived - legacy)
    if only_legacy:
        print("\nOS in block_display only:")
        for n in only_legacy:
            print(f"  {n}")
    if only_map:
        print("\nOS in map only:")
        for n in only_map[:20]:
            print(f"  {n}")
    if not only_legacy and legacy:
        print("\nOK: map-derived OS covers all legacy OS rows")
    return 0 if not only_legacy or not legacy else 1


if __name__ == "__main__":
    raise SystemExit(main())
