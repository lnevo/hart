"""Shared name derivation from public_name_map.csv (D2 consolidation).

Read-only helpers — no live file writes.
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAP = ROOT / "jmri/layouts/hart/data/public_name_map.csv"

# Crossover legs: layoutturnout may name primary only; block table must still hold these.
SECONDARY_OS_BLOCKS = frozenset(
    {
        "OS Switch 23b",
        "OS Switch 35a",
        "OS Switch 7b",
    }
)


def os_public_names_from_map(map_path: Path = DEFAULT_MAP) -> set[str]:
    """OS block names for phase02 — same filter as legacy block_display role=os."""
    names: set[str] = set()
    with map_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            layer = (row.get("layer") or "").strip()
            proposed = (row.get("proposed") or row.get("current") or "").strip()
            if not proposed:
                continue
            if layer == "block" and proposed.startswith("OS "):
                names.add(proposed)
    return names
