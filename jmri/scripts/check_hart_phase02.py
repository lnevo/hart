#!/usr/bin/env python3
"""Acceptance checks for hart phases 0–2 (fail = nonzero exit)."""

from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from pathlib import Path

JMRI_ROOT = Path(__file__).resolve().parents[1]
HART = JMRI_ROOT / "layouts" / "hart"
PANEL = HART / "output" / "tables.xml"
NAME_MAP = HART / "data" / "public_name_map.csv"
SWITCH_LEGS = HART / "data" / "switch_legs.csv"
SWITCHES = HART / "data" / "switches.csv"


def secondary_os_blocks(path: Path = SWITCH_LEGS) -> set[str]:
    """A crossover's OS blocks after its first (main) row in switch_legs.csv (7b, 23b, 35a)."""
    seen: set[str] = set()
    out: set[str] = set()
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["switch"] in seen:
                out.add(row["os_block"])
            seen.add(row["switch"])
    return out


def crossover_row_errors(root: ET.Element, switches: Path = SWITCHES, legs: Path = SWITCH_LEGS) -> list[str]:
    """A switch whose Layout Editor turnout is a crossover needs two switch_legs.csv rows
    (its main and its second OS block); with one, its second OS block would go unchecked."""
    xover = {t.get("ident") for t in root.iter("layoutturnout") if (t.get("type") or "").endswith("_XOVER")}
    rows: dict[str, int] = {}
    with legs.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows[row["switch"]] = rows.get(row["switch"], 0) + 1
    errors = []
    with switches.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["le_ident"] in xover and rows.get(row["switch"], 0) < 2:
                errors.append(f"Switch {row['switch']} is a crossover ({row['le_ident']}) but "
                              f"{legs.name} has {rows.get(row['switch'], 0)} row(s) for it, not 2")
    return errors


def main() -> int:
    errors: list[str] = []
    if not PANEL.is_file():
        errors.append(f"missing panel {PANEL}")
        print("\n".join(errors))
        return 1

    root = ET.parse(PANEL).getroot()

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

    # tables.xml stores each block twice (stub + full), so count distinct system names.
    counts = Counter(
        user
        for user, _system in {
            (
                (b.findtext("userName") or "").strip(),
                b.get("systemName") or b.findtext("systemName") or "",
            )
            for b in root.iter("block")
            if (b.findtext("userName") or "").strip()
        }
    )
    dups = [f"{n}×{c}" for n, c in counts.items() if c > 1]
    if dups:
        errors.append("duplicate block userNames: " + ", ".join(dups[:8]))

    # Expected OS public names present on layout turnouts
    with NAME_MAP.open(newline="", encoding="utf-8-sig") as f:
        expected_os = {
            row["proposed"]
            for row in csv.DictReader(f)
            if row.get("layer") == "block" and row["proposed"].startswith("OS ")
        }
    found = {t.get("blockname") for t in root.iter("layoutturnout")}
    missing = sorted(expected_os - found)
    # Crossover / paired legs: occupancy exists in block table; layoutturnout
    # may only name the primary leg (linear6 connectivity).
    errors.extend(crossover_row_errors(root))
    secondary_ok = secondary_os_blocks()
    missing = [m for m in missing if m not in secondary_ok]
    if missing:
        errors.append("layoutturnout missing OS blocks: " + ", ".join(missing))
    for name in sorted(secondary_ok):
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
