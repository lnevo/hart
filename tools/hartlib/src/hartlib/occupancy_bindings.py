"""The blocks the CATS desks bind: each block row of the device master with a cats_discipline, and its occupancy sensor.

    occupancy_bindings.rows()      [{level, block_id, block_user_name, occupancy_sensor_user_name, cats_discipline}]

The discipline is the owner's cell `cats_discipline` of the block's row in devices_field.csv (CTC or YARD,
devices.CATS_DISCIPLINES; ADR-039 lane L12, owner 2026-11-25). cats/data/occupancy_bindings.csv held it, with copies
of the block and sensor names, until then. rows() gives each block its user name from the merged master and its
occupancy sensor's user name: the occupancy row on its level whose `blocks` cell names it (or the block it is
part_of), else level_devices.occupancy_user (a helix block, whose sensor is the main and upper levels' virtual one).
`hartlib.devices` checks the cell (a block row, one of CTC or YARD); devices.columns.csv gives check_data.py the same
values.

Readers: cats/scripts/digicon_lib.py (the CATS desk builders), jmri/layouts/hart/scripts/audit_panel_contracts.py,
tools/audit/check_layout_facts.py and tools/mqtt-mimic/lcos_mqtt_mimic.py.

Every failure is a railroad_facts.FactsError (devices.DevicesError for the master).
"""
from __future__ import annotations

from typing import Mapping

from . import devices, level_devices
from .railroad_facts import device_list

COLUMNS = ("level", "block_id", "block_user_name", "occupancy_sensor_user_name", "cats_discipline")


def sensors(master: tuple[Mapping[str, str], ...]) -> dict[tuple[str, str], str]:
    """{(level, block user name): occupancy sensor user name} of the occupancy rows of `master` (the first occupancy
    row that names a block wins, as hartlib.block_lengths takes it)."""
    out: dict[tuple[str, str], str] = {}
    for r in master:
        if r["level"] and r["layer"] == "occupancy":
            for b in device_list(r["blocks"]):
                out.setdefault((r["level"], b), r["user_name"])
    return out


def rows(files=None) -> list[dict[str, str]]:
    """The block rows of the device master (`files`: a devices.Files or the generated file's path, as devices.load
    takes it; default the repo's) that have a cats_discipline, in master order, each as COLUMNS."""
    master = devices.load(files)
    by_sensor = sensors(master)
    out = []
    for r in master:
        if not (r["level"] and r["layer"] == "block" and r["cats_discipline"]):
            continue
        name = r["user_name"]
        sensor = (by_sensor.get((r["level"], name))
                  or (by_sensor.get((r["level"], r["part_of"])) if r["part_of"] else None)
                  or level_devices.occupancy_user(name))
        out.append({"level": r["level"], "block_id": r["id"], "block_user_name": name,
                    "occupancy_sensor_user_name": sensor, "cats_discipline": r["cats_discipline"]})
    return out
