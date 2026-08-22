#!/usr/bin/env python3
"""Acceptance checks for hart phases 0–2 (fail = nonzero exit)."""

from __future__ import annotations

import csv
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

JMRI_ROOT = Path(__file__).resolve().parents[1]
HART = JMRI_ROOT / "layouts" / "hart"
PANEL = HART / "output" / "hart_prod.xml"
CSV = HART / "data" / "block_display_names.csv"


def main() -> int:
    errors: list[str] = []
    if not PANEL.is_file():
        errors.append(f"missing panel {PANEL}")
        print("\n".join(errors))
        return 1

    root = ET.parse(PANEL).getroot()

    # layout_paths registration
    sys.path.insert(0, str(JMRI_ROOT.parent))
    from jmri.layout_paths import layout_paths

    paths = layout_paths("hart")
    if not paths["output"].endswith("hart_blocked.xml"):
        errors.append(f"layout_paths output unexpected: {paths['output']}")

    # No leftover ISIS sensors
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

    # Panel title
    le_names = [le.get("name") for le in root.iter("LayoutEditor")]
    if not any(name in {"HART Railroad", "HART"} for name in le_names):
        errors.append(f"LayoutEditor name not HART Railroad: {le_names}")

    # No duplicate block userNames
    from collections import Counter

    counts = Counter(
        (b.findtext("userName") or "").strip()
        for b in root.iter("block")
        if (b.findtext("userName") or "").strip()
    )
    dups = [f"{n}×{c}" for n, c in counts.items() if c > 1]
    if dups:
        errors.append("duplicate block userNames: " + ", ".join(dups[:8]))

    # Expected OS public names present on layout turnouts
    with CSV.open(newline="", encoding="utf-8") as f:
        expected_os = {
            row["public_user_name"]
            for row in csv.DictReader(f)
            if row.get("role") == "os"
        }
    found = {t.get("blockname") for t in root.iter("layoutturnout")}
    missing = sorted(expected_os - found)
    # Crossover / paired legs: occupancy exists in block table; layoutturnout
    # may only name the primary leg (linear6 connectivity).
    secondary_ok = {
        "OS 111b",
        "OS 113a",
        "OS 117b",
    }
    missing = [m for m in missing if m not in secondary_ok]
    if missing:
        errors.append("layoutturnout missing OS blocks: " + ", ".join(missing))
    for name in secondary_ok:
        if not any(
            (b.findtext("userName") or "") == name for b in root.iter("block")
        ):
            errors.append(f"secondary OS block missing from block table: {name}")

    if errors:
        print("FAIL")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("PASS hart phase 0–2 checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
