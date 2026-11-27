"""The device master's row as a record: MasterRow (any row of the merged view) and DeviceRow (a row with a level).

hartlib.devices.load() returns these rows, and hartlib.railroad_facts.DeviceMap holds DeviceRow records of main and
upper. A reader takes a row's fields; a writer or a check that works on the master's text takes MasterRow.cells(),
the row as the file holds it. railroad_facts re-exports every name here.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import cast

from .errors import FactsError
from .levels import Level, level_text, parse_level

DEVICE_LIST = ";"           # the separator of a list column (blocks, protects, a line block's cp)


def device_list(cell: str) -> list[str]:
    """A DEVICE_LIST cell's items, in order."""
    return [x.strip() for x in (cell or "").split(DEVICE_LIST) if x.strip()]


# The device master's columns in file order (hartlib.devices.COLUMNS, which the file headers are held to).
MASTER_COLUMNS = ("level", "cp", "layer", "role", "id", "user_name", "assignment", "system_name", "jmri_name", "node",
                  "dcc", "wiring", "jmri_comment", "trial_name", "notes", "blocks", "detector", "stop", "layout_block",
                  "cats_discipline", "part_of", "switch", "facing", "protects", "dir", "start", "bean_comment",
                  "written_by", "description", "jmri_bean")


@dataclass(frozen=True, eq=False)
class MasterRow:
    """A row of the device master: a JMRI device (jmri_name, virtual) and its planned physical part (system_name, a
    draft). `role` is what the device is (devices.ROLES), given by the row or its writer; readers test it, not the
    name. `level` is None only on a Store's level-less row (devices.is_unplaced), which has no role either; every
    row with a level is a DeviceRow, whose level is a Level.

    A reader takes the fields. A writer or a check that works on the master's text takes cells(): the row as the
    file holds it, {column: text} in MASTER_COLUMNS order, the level as "1", "2", "3" or "" (level_cell). `comment`
    (the device-map form's built comment) and `line` are not columns of the master and are not among the cells."""
    level: Level | None
    layer: str
    user_name: str
    role: str
    cp: str = ""
    system_name: str = ""
    jmri_name: str = ""
    node: str = ""
    dcc: str = ""
    comment: str = ""
    trial_name: str = ""
    notes: str = ""
    blocks: str = ""
    detector: str = ""
    stop: str = ""
    switch: str = ""
    facing: str = ""
    protects: str = ""
    dir: str = ""
    id: str = ""        # its device ID (hartlib.device_ids); empty on a row made without one (a test's)
    assignment: str = ""    # the master's assignment (devices.ASSIGNMENTS): field for a device swapped in (ADR-028);
                            # empty on a row made without one (a test's), read as virtual
    wiring: str = ""
    jmri_comment: str = ""
    layout_block: str = ""
    cats_discipline: str = ""
    part_of: str = ""
    start: str = ""
    bean_comment: str = ""
    written_by: str = ""
    description: str = ""
    jmri_bean: str = ""
    line: int = 0

    @property
    def swapped(self) -> bool:
        """Whether the row is a field device (assignment field: swapped in by its row, ADR-028): its jmri_name is
        the device's, held to no virtual-name rule (a column test, not a level test)."""
        return self.assignment == "field"

    def __post_init__(self) -> None:
        from . import devices
        if self.level is None and not self.role:     # a Store's level-less row: no role until it has a level
            return
        if self.role not in devices.ROLES:      # no role is read off a name (hand-off row 8)
            raise FactsError(f"level {self.level} {self.layer} {self.user_name!r} has role {self.role!r}, not one of "
                             f"{', '.join(devices.ROLES)}")

    @property
    def level_cell(self) -> str:
        """The level as the master's level column holds it: "1", "2", "3", or "" for a Store's level-less row."""
        return "" if self.level is None else level_text(self.level)

    def cells(self) -> dict[str, str]:
        """The row as the master's text: {column: cell} of every MASTER_COLUMNS column, in file order, the level as
        level_cell. A new dict each call, so a writer may change it; the text a file of this row holds."""
        out: dict[str, str] = {c: getattr(self, c) for c in MASTER_COLUMNS}
        out["level"] = self.level_cell
        return out

    def _values(self) -> tuple[object, ...]:
        return tuple(getattr(self, f) for f in _DEVICE_ROW_FIELDS)

    def __eq__(self, other: object) -> bool:
        """Equal to a row with the same fields (line and comment too)."""
        if isinstance(other, MasterRow):
            return self._values() == other._values()
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._values())

    @staticmethod
    def from_master(row: Mapping[str, str], line: int, where: str) -> "MasterRow":
        """A row of the device master's text (every MASTER_COLUMNS cell) at place `line` of the merged view: a
        DeviceRow, its level parsed (parse_level, naming `where`), or a MasterRow with no level for a Store's
        level-less row."""
        missing = [c for c in MASTER_COLUMNS if c not in row]
        if missing:
            raise FactsError(f"{where}: a device master row has no {', '.join(missing)}")
        cells = {c: row[c] for c in MASTER_COLUMNS if c != "level"}
        if not row["level"]:
            return MasterRow(level=None, line=line, **cells)
        return DeviceRow(level=parse_level(row["level"], where), line=line, **cells)


@dataclass(frozen=True, eq=False)
class DeviceRow(MasterRow):
    """A row of the device master with a level (every row of the device map, and every row devices.load() gives but
    a Store's level-less one)."""
    level: Level

    @property
    def served(self) -> list[str]:
        """An occupancy row's blocks, in order."""
        return device_list(self.blocks)

    @property
    def protected(self) -> list[str]:
        """A mast row's protected blocks, in order."""
        return device_list(self.protects)

    @property
    def trial(self) -> frozenset[str]:
        """The schematic tracks a block row holds, by switch and leg ("Track 127AB-131AB", "Track 107B-107C #1")."""
        return frozenset(t.strip() for t in self.trial_name.split(",") if t.strip())

    @classmethod
    def from_dict(cls, row: dict, line: int = 0) -> "DeviceRow":
        """A row as build_device_map.py makes it (str or int level); its role is the row's own (a row with none stops)."""
        row = {"role": "", **row}           # a row with no role stops in __post_init__, naming it
        cells = {k: str(v) for k, v in row.items() if k not in ("line", "level")}
        return cls(line=line, level=cast(Level, int(row["level"])), **cells)


_DEVICE_ROW_FIELDS = tuple(f.name for f in fields(MasterRow))


def row_cells(row: MasterRow | Mapping[str, str]) -> Mapping[str, str]:
    """A row as the master's text, for a helper that takes either form (a message's name, a row's place): a
    MasterRow's cells(), any other row (a writer's dict, a file's row) as it is."""
    return row.cells() if isinstance(row, MasterRow) else row
