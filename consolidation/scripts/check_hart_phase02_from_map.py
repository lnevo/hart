#!/usr/bin/env python3
"""Draft phase02 checks using OS names from public_name_map (D2c prep).

Same invariants as jmri/scripts/check_hart_phase02.py except OS expectations
come from the map (layer=block, proposed.startswith("OS ")), not block_display.

Read-only — does not write live files. Safe to run before live promotion.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "consolidation" / "scripts"))

from names_from_map import DEFAULT_MAP, SECONDARY_OS_BLOCKS, os_public_names_from_map

JMRI_ROOT = ROOT / "jmri"
HART = JMRI_ROOT / "layouts" / "hart"
PANEL = HART / "output" / "hart_prod.xml"


def main() -> int:
    errors: list[str] = []
    if not PANEL.is_file():
        errors.append(f"missing panel {PANEL}")
        print("\n".join(errors))
        return 1

    root = ET.parse(PANEL).getroot()

    sys.path.insert(0, str(JMRI_ROOT.parent))
    from jmri.layout_paths import layout_paths

    paths = layout_paths("hart")
    if not paths["output"].endswith("hart_blocked.xml"):
        errors.append(f"layout_paths output unexpected: {paths['output']}")

    for s in root.iter("sensor"):
        sn = s.get("systemName") or s.findtext("systemName") or ""
        if sn.startswith("ISIS"):
            errors.append(f"ISIS sensor still present: {sn}")

    clock = [
        s
        for s in root.iter("sensor")
        if (s.get("systemName") or s.findtext("systemName")) == "ISCLOCKRUNNING"
    ]
    if not clock:
        errors.append("ISCLOCKRUNNING missing")

    le_names = [le.get("name") for le in root.iter("LayoutEditor")]
    if not any(name in {"HART Railroad", "HART"} for name in le_names):
        errors.append(f"LayoutEditor name not HART Railroad: {le_names}")

    counts = Counter(
        (b.findtext("userName") or "").strip()
        for b in root.iter("block")
        if (b.findtext("userName") or "").strip()
    )
    dups = [f"{n}×{c}" for n, c in counts.items() if c > 1]
    if dups:
        errors.append("duplicate block userNames: " + ", ".join(dups[:8]))

    if not DEFAULT_MAP.is_file():
        errors.append(f"missing map {DEFAULT_MAP}")
    else:
        expected_os = os_public_names_from_map(DEFAULT_MAP)
        found = {t.get("blockname") for t in root.iter("layoutturnout")}
        missing = sorted(expected_os - found - SECONDARY_OS_BLOCKS)
        if missing:
            errors.append("layoutturnout missing OS blocks: " + ", ".join(missing))
        for name in SECONDARY_OS_BLOCKS:
            if not any(
                (b.findtext("userName") or "") == name for b in root.iter("block")
            ):
                errors.append(f"secondary OS block missing from block table: {name}")

    if errors:
        print("FAIL (map-derived OS)")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("PASS hart phase 0–2 checks (map-derived OS)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
