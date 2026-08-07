#!/usr/bin/env python3
"""Export JMRI device catalog from hart panel for CATS Designer binding.

CATS Designer does not import Layout Editor geometry. Bind by userName.
"""

from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from pathlib import Path

JMRI_ROOT = Path(__file__).resolve().parents[1]
PANEL = JMRI_ROOT / "layouts" / "hart" / "output" / "hart_prod.xml"
OUT = JMRI_ROOT.parent / "cats" / "data" / "jmri_devices.csv"
CP_CSV = JMRI_ROOT / "layouts" / "hart" / "data" / "control_points.csv"


def text(el: ET.Element | None, tag: str) -> str:
    if el is None:
        return ""
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else ""


def main() -> int:
    root = ET.parse(PANEL).getroot()
    rows: list[dict[str, str]] = []

    for s in root.iter("sensor"):
        sn = s.get("systemName") or text(s, "systemName")
        un = text(s, "userName")
        if not sn:
            continue
        rows.append(
            {
                "kind": "sensor",
                "system_name": sn,
                "user_name": un,
                "cats_use": "occupancy_or_feedback",
                "notes": "",
            }
        )

    for t in root.iter("turnout"):
        sn = t.get("systemName") or text(t, "systemName")
        un = text(t, "userName")
        if not sn:
            continue
        rows.append(
            {
                "kind": "turnout",
                "system_name": sn,
                "user_name": un,
                "cats_use": "points_command",
                "notes": "",
            }
        )

    # Layout turnouts → OS block mapping for Designer plants
    for lt in root.iter("layoutturnout"):
        rows.append(
            {
                "kind": "layout_os",
                "system_name": lt.get("ident") or "",
                "user_name": lt.get("blockname") or "",
                "cats_use": "os_block",
                "notes": f"turnoutname={lt.get('turnoutname') or ''}",
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["kind", "system_name", "user_name", "cats_use", "notes"]
        )
        w.writeheader()
        w.writerows(rows)

    # Also write CP plant checklist
    plants = JMRI_ROOT.parent / "cats" / "data" / "plants_from_hart.csv"
    if CP_CSV.is_file():
        plants.write_text(CP_CSV.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"Wrote {len(rows)} rows → {OUT}")
    print(f"Plants → {plants}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
