#!/usr/bin/env python3
"""Read-only wiring crosswalk: signal_wiring vs deploy IH beans.

Uses consolidation/sor/wiring/packed_id_crosswalk.csv for mast-aware remap
(node×100 packed IDs and stale helix rows → live IH). Falls back to naive
packed↔IH compare only if crosswalk is missing.
"""
from __future__ import annotations

import csv
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WIRING = ROOT / "cats/data/signal_wiring.csv"
TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"
CROSSWALK = ROOT / "consolidation/sor/wiring/packed_id_crosswalk.csv"


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
        for row in csv.DictReader(f):
            packed = (row.get("packed") or "").strip()
            if packed.isdigit():
                ids.add(packed)
    return ids


def ih_packed_from_tables(tree: ET.ElementTree) -> set[str]:
    ids: set[str] = set()
    for head in tree.getroot().iter("signalhead"):
        sn = text(head, "systemName") or (head.get("systemName") or "")
        m = re.match(r"IH(\d+)", sn)
        if m:
            ids.add(m.group(1))
    return ids


def load_crosswalk() -> list[dict[str, str]]:
    if not CROSSWALK.is_file():
        return []
    with CROSSWALK.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def validate_mast_aware(wiring_ids: set[str], bean_ids: set[str], rows: list[dict[str, str]]) -> int:
    by_packed = {(r.get("wiring_packed") or "").strip(): r for r in rows}
    missing_crosswalk = sorted(wiring_ids - set(by_packed))
    if missing_crosswalk:
        print(f"FAIL: {len(missing_crosswalk)} wiring packed IDs not in crosswalk")
        for pid in missing_crosswalk[:8]:
            print(f"  - {pid}")
        return 1

    unmapped = [r for r in rows if not (r.get("live_ih") or "").strip()]
    if unmapped:
        print(f"FAIL: {len(unmapped)} crosswalk rows without live_ih")
        return 1

    missing_beans: list[str] = []
    resolved: set[str] = set()
    for r in rows:
        live = (r.get("live_ih") or "").strip()
        packed = (r.get("wiring_packed") or "").strip()
        status = (r.get("status") or "").strip()
        resolved.add(live)
        if live not in bean_ids:
            missing_beans.append(f"{packed}→{live} ({status}, {r.get('wiring_mast')})")

    collisions = [r for r in rows if (r.get("status") or "") == "collision"]
    remaps = [r for r in rows if (r.get("status") or "") == "remap"]

    print(f"Crosswalk rows: {len(rows)} (remap={len(remaps)}, collision={len(collisions)})")
    print(f"Resolved live IH from wiring: {len(resolved)}")
    print(f"Deploy IH beans: {len(bean_ids)}")

    if missing_beans:
        print(f"FAIL: {len(missing_beans)} resolved IH not in deploy tables:")
        for item in missing_beans[:8]:
            print(f"  - {item}")
        return 1

    extra_beans = sorted(bean_ids - resolved)
    if extra_beans:
        print(f"INFO: {len(extra_beans)} deploy IH not referenced by wiring crosswalk (OK if virtual/extra heads)")

    covered = len(resolved & bean_ids)
    ratio = covered / len(resolved) if resolved else 1.0
    print(f"Mast-aware overlap: {covered}/{len(resolved)} ({ratio:.0%})")
    if ratio < 0.95:
        print("FAIL: mast-aware overlap below 95%")
        return 1

    print("OK: wiring crosswalk (mast-aware)")
    return 0


def validate_naive(wiring_ids: set[str], bean_ids: set[str]) -> int:
    missing_beans = sorted(wiring_ids - bean_ids)
    extra_beans = sorted(bean_ids - wiring_ids)
    if missing_beans:
        print(f"INFO: {len(missing_beans)} wiring IDs without IH (first 5): {missing_beans[:5]}")
    if extra_beans:
        print(f"INFO: {len(extra_beans)} IH not in wiring CSV (first 5): {extra_beans[:5]}")
    overlap = wiring_ids & bean_ids
    ratio = len(overlap) / len(wiring_ids) if wiring_ids else 1.0
    print(f"Naive overlap: {len(overlap)}/{len(wiring_ids)} ({ratio:.0%})")
    if ratio < 0.5:
        print("FAIL: naive crosswalk overlap below 50%")
        return 1
    print("OK: wiring crosswalk (naive — regenerate crosswalk CSV)")
    return 0


def main() -> int:
    if not TABLES.is_file():
        print(f"MISSING: {TABLES}", file=sys.stderr)
        return 2

    tree = ET.parse(TABLES)
    wiring_ids = packed_ids_from_wiring()
    bean_ids = ih_packed_from_tables(tree)

    print(f"Packed IDs from signal_wiring.csv: {len(wiring_ids)}")
    print(f"IH IDs from deploy tables: {len(bean_ids)}")
    print()

    crosswalk = load_crosswalk()
    if crosswalk:
        return validate_mast_aware(wiring_ids, bean_ids, crosswalk)

    print(f"WARN: missing {CROSSWALK.relative_to(ROOT)} — run build_wiring_crosswalk.py")
    return validate_naive(wiring_ids, bean_ids)


if __name__ == "__main__":
    raise SystemExit(main())
