"""CATS desk conventions shared by the desk builders: a block's station plate and each mast's signal template.

Both the hand-wired desks (cats/scripts/wire_digicon.py) and the generated one (tools/schematic/build_cats_panel.py)
use them, so they live here, not in either script (CATS cut-over, 2026-11-15).
"""
from __future__ import annotations

import csv
from pathlib import Path

from . import paths


def station_plate(name: str) -> str:
    """Desk plate for a block: `OS Switch 39` -> 39, `Track West Ext` -> West."""
    return name.removeprefix("OS Switch ").removeprefix("Track ").split()[0]


def mast_templates(path: Path | None = None) -> dict[str, str]:
    """CATS signal template (PHYSIGNAL) per mast user name, from signal_head_plan.csv."""
    with (path or paths.SIGNAL_HEAD_PLAN).open(newline="") as f:
        return {row["mast_user_name"].strip(): row["physignal"].strip() for row in csv.DictReader(f)}
