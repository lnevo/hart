"""Dispatcher virtual stub masts (D2f Option A — map-only, no beans)."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAP = ROOT / "jmri/layouts/hart/data/public_name_map.csv"


def virtual_mast_names_from_map(map_path: Path = DEFAULT_MAP) -> frozenset[str]:
    """Canonical Mast* names whose map hardware column marks virtual Dispatcher stubs."""
    names: set[str] = set()
    if not map_path.is_file():
        return frozenset()
    with map_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (row.get("layer") or "").strip() != "mast":
                continue
            current = (row.get("current") or "").strip()
            proposed = (row.get("proposed") or "").strip()
            if current != proposed:
                continue
            hardware = (row.get("hardware") or "").lower()
            if "virtual" not in hardware:
                continue
            if proposed.startswith("Mast "):
                names.add(proposed)
    return frozenset(names)
