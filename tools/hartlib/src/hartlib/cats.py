"""CATS desk conventions of the generated desks (tools/schematic/build_cats_panel.py): a block's station plate and
each mast's signal template."""
from __future__ import annotations

import csv
from pathlib import Path

from . import paths


def station_plate(name: str) -> str:
    """Desk plate for a block: `OS Switch 39` -> 39, `Track West Ext` -> West."""
    return name.removeprefix("OS Switch ").removeprefix("Track ").split()[0]


def mast_templates(path: Path | None = None, systems: dict[str, str] | None = None) -> dict[str, str]:
    """CATS signal template (PHYSIGNAL) per mast user name, from signal_head_plan.csv. With `systems` ({mast user
    name: system name}, the tables' masts), only the rows whose mast_system_name is that mast's: a plan row for a mast
    the tables now hold with other heads or another type (staging's rule-built masts) gives no template."""
    with (path or paths.SIGNAL_HEAD_PLAN).open(newline="") as f:
        rows = list(csv.DictReader(f))
    return {row["mast_user_name"].strip(): row["physignal"].strip() for row in rows
            if systems is None or systems.get(row["mast_user_name"].strip()) == row["mast_system_name"].strip()}


def appearance_templates(path: Path | None = None) -> dict[str, str]:
    """{appearance type: CATS template} from signal_head_plan.csv's appearance and physignal columns. Raises
    ValueError on a type the file gives two templates."""
    out: dict[str, str] = {}
    with (path or paths.SIGNAL_HEAD_PLAN).open(newline="") as f:
        for row in csv.DictReader(f):
            kind, template = row["appearance"].strip(), row["physignal"].strip()
            if out.setdefault(kind, template) != template:
                raise ValueError(f"signal_head_plan.csv gives {kind} masts two templates, {out[kind]} and {template}")
    return out
