"""cats/data/occupancy_bindings.csv: the occupancy sensor and CATS discipline of each block the CATS desks bind.

    occupancy_bindings.rows()      [{block_id, block_user_name, occupancy_sensor_user_name, cats_discipline}]

A row names its block by its block `id` (block_lengths.csv, as block:3B-end or os:23:A-1A; ADR-039 lane L4c), never
by its public name, which can change (ADR-005). rows() gives each row the block's name as well, from the name store
(hartlib.track_names.names_by_id: the owner's name in devices_field.csv, else the generated one), so the readers bind
by the name JMRI and CATS know. A block id is unique on its level only; an id two levels have stops the read, as does
an id that is no block. `tools/ops/check_data.py` holds the ids to block_lengths.csv (occupancy_bindings.columns.csv).

Readers: cats/scripts/digicon_lib.py (the CATS desk builders), jmri/layouts/hart/scripts/audit_panel_contracts.py,
tools/audit/check_layout_facts.py and tools/mqtt-mimic/lcos_mqtt_mimic.py.

Every failure is a railroad_facts.FactsError naming the file and line.
"""
from __future__ import annotations

import csv
from pathlib import Path

from . import paths, track_names
from .railroad_facts import FactsError

PATH = paths.CATS_DIR / "data" / "occupancy_bindings.csv"
COLUMNS = ("block_id", "occupancy_sensor_user_name", "cats_discipline")


def rows(path: Path = PATH, data: Path = track_names.SCHEMATIC) -> list[dict[str, str]]:
    """The rows of `path` in file order, cells stripped, each with `block_user_name` the name of its `block_id` (the
    name store beside the schematic folder `data`). FactsError on a header that is not COLUMNS, a row with no
    block_id, a block_id given twice, or an id the name store has no block for."""
    path = Path(path)
    try:
        fh = path.open(newline="", encoding="utf-8")
    except OSError as exc:
        raise FactsError(f"{path}: cannot read it ({exc.strerror})") from None
    with fh:
        reader = csv.DictReader(fh)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise FactsError(f"{path.name}: the header is {','.join(reader.fieldnames or [])}, not "
                             f"{','.join(COLUMNS)}")
        out, seen = [], {}
        for r in reader:
            line = reader.line_num
            row = {c: (r.get(c) or "").strip() for c in COLUMNS}
            bid = row["block_id"]
            if not bid:
                raise FactsError(f"{path.name} line {line}: no block_id")
            if bid in seen:
                raise FactsError(f"{path.name} line {line}: block_id {bid} is on line {seen[bid]} too")
            seen[bid] = line
            out.append(row)
    try:
        names = track_names.names_by_id([r["block_id"] for r in out], data, path.name)
    except track_names.TrackNameError as exc:
        raise FactsError(str(exc)) from None
    for r in out:
        r["block_user_name"] = names[r["block_id"]]
    return out
