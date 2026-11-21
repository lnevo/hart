#!/usr/bin/env python3
"""Acceptance checks for hart phases 0–2 (fail = nonzero exit)."""

from __future__ import annotations

import csv
import os
import xml.etree.ElementTree as ET
from pathlib import Path

JMRI_ROOT = Path(__file__).resolve().parents[1]
HART = JMRI_ROOT / "layouts" / "hart"
# HART_TABLES names another tables file for the checks (tools/check.sh, hartlib.paths); this
# script stays free of hartlib.
PANEL = Path(os.environ["HART_TABLES"]) if os.environ.get("HART_TABLES") else HART / "output" / "tables.xml"
DEVICES = HART / "data" / "devices.csv"
SWITCHES = HART / "data" / "switches.csv"
STAGING_COLUMNS = ("level", "switch", "os_block", "le_ident")


def staging_rows(path: Path = SWITCHES) -> list[dict[str, str]]:
    """The staging (level 1) rows of switches.csv, one per OS block, in file order. Stops on a
    file without the columns this reads (hartlib.railroad_facts.read_switch_rows checks the rest)."""
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in STAGING_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"{path}: no column {', '.join(missing)}")
        return [row for row in reader if row["level"] == "1"]


def secondary_os_blocks(path: Path = SWITCHES) -> set[str]:
    """A crossover's OS blocks after its first (main) row in switches.csv (7b, 23b, 35a)."""
    seen: set[str] = set()
    out: set[str] = set()
    for row in staging_rows(path):
        if row["switch"] in seen:
            out.add(row["os_block"])
        seen.add(row["switch"])
    return out


def crossover_row_errors(root: ET.Element, switches: Path = SWITCHES) -> list[str]:
    """A switch whose Layout Editor turnout is a crossover needs two switches.csv rows
    (its main and its second OS block); with one, its second OS block would go unchecked.
    The turnout is the le_ident of the switch's first row."""
    xover = {t.get("ident") for t in root.iter("layoutturnout") if (t.get("type") or "").endswith("_XOVER")}
    rows: dict[str, int] = {}
    ident: dict[str, str] = {}
    for row in staging_rows(switches):
        rows[row["switch"]] = rows.get(row["switch"], 0) + 1
        ident.setdefault(row["switch"], row["le_ident"])
    return [f"Switch {n} is a crossover ({ident[n]}) but {switches.name} has {count} row(s) for it, not 2"
            for n, count in rows.items() if ident[n] in xover and count < 2]


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
    # the staging (level 1) OS blocks of the device master: role os, or xover_corner for a crossover's
    with DEVICES.open(newline="", encoding="utf-8-sig") as f:
        expected_os = {
            row["user_name"]
            for row in csv.DictReader(f)
            if row["level"] == "1" and row["layer"] == "block" and row["role"] in ("os", "xover_corner")
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
