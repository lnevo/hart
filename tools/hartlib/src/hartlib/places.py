"""The railroad's places by id (ADR-039 lane L4c): the stations of schematic/stations.csv, keyed by `station_id`
(st:<name>), and the control points of schematic/interlockings.csv, keyed by `cp_id` (cp:<name>).

    places.table(schematic)      the Table of a folder's two files, default the repo's (read again when either
                                 file changes); its names, ids, with_names and with_ids are the ones below
    places.names(cell)           "st:barn;st:engine-house" -> "Barn;Engine House"
    places.ids(cell)             "Barn;Engine House" -> "st:barn;st:engine-house"
    places.with_names(row)       the row with its `cp` cell named (a dict, changed in place and returned)
    places.with_ids(rows)        copies of the rows with their `cp` cells as ids
    places.switch_place(level, n)  the place id of switch n on a level ("" when it is in none)
    places.switch_places()       {(level, switch number): place id} of every switch the two files list
    places.of(row)               a device row's place by name: its cp cell, a turnout's switch_place (devices.place)

A `cp` cell of the device pair (devices_field.csv, devices_generated.csv) and of schematic/masts.csv holds ids, ';'
between them. hartlib.devices and hartlib.level_masts name them when they read a file and write ids when they write
one, so every reader sees the names and a renamed station or control point changes one row of its file and no cp
cell. `tools/ops/check_data.py` holds each id of those files to a `station_id` or `cp_id` (devices.columns.csv refs).

An id is its prefix, a colon and lower-case words joined by '-' (st:west-yard, cp:107). It is given once and stays
when the name changes. A main or upper control point "CP 107" is cp:107.

Four staging interlockings (Brick, Barn, East End and Princess) have the name of a station. A staging `cp` cell names
the desk area, which is a station, so such a name is written as the station's id (st:brick). No cp cell names one of
those four interlockings today; tests/test_places.py fails when a file's cells stop reading back as they are.

A turnout row of the device pair has no `cp` cell: the switch lists of the two files are the one
place for the switch-to-place link, and `switch_place` gives a switch's place from them. On staging (level 1) it is
the desk area that holds the switch (railroad_facts.read_desk_areas), written as the id of the station that names the
area: Switches 1 and 3 are st:brick (Switch 3 also lies in West Yard, a station of the Brick desk area), 5 is
st:plane, 9 is st:engine-house (nested in Barn, a desk area of its own). Staging's interlockings, which group 1, 3
and 5 as Brick, are the signal rule's and give no turnout's place. On main and upper it is the interlocking that holds
the switch (cp:107); a local switch of a yard or spur is in none and has no place.

Each function takes the folder of the lists to read (`schematic`, default the repo's); lists_beside gives a copied
file's own lists, so hartlib.devices and hartlib.level_masts read a copy's cp cells by the copy's stations.csv and
interlockings.csv.

An item that is no id (a test's own place name) is left as it is either way. FactsError names the file and line on an
id that is malformed, given twice or under the wrong prefix, on an id of a cell that no row has, and on a station or
control point name given twice (on any level, as ids() has no level to choose by; a staging interlocking named as
a station of its own level is the one exception), naming both rows.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from collections.abc import Callable, Iterable, Mapping
from typing import TYPE_CHECKING

from . import paths
from .device_rows import MasterRow, row_cells

if TYPE_CHECKING:
    from . import devices as devices_mod

SCHEMATIC = paths.LAYOUT_DATA / "schematic"
STATIONS = SCHEMATIC / "stations.csv"
INTERLOCKINGS = SCHEMATIC / "interlockings.csv"
STATION_PREFIX, CP_PREFIX = "st:", "cp:"
ID = re.compile(r"(st|cp):[a-z0-9]+(?:-[a-z0-9]+)*")
LIST = ";"                      # between the items of a cp cell (hartlib.devices.LIST)
COLUMN = "cp"                   # the column of the device pair and masts.csv that holds place ids


def _error(message: str) -> Exception:
    """A railroad_facts.FactsError (imported here: railroad_facts imports level_masts, which imports this module)."""
    from .railroad_facts import FactsError
    return FactsError(message)


@dataclass(frozen=True, eq=False)
class Table:
    """The places of one stations.csv and interlockings.csv (table, _table). Compared and hashed by identity: _table
    gives one object per pair of file contents, so a cache keyed on a Table (hartlib.devices._read) reads again when
    either file changes."""
    by_id: Mapping[str, str]        # id -> name
    by_name: Mapping[str, str]      # name -> id (a station's before a staging interlocking's of the same name)

    def names(self, cell: str, where: str = "") -> str:
        """The names of a cp cell's ids, ';' between them; an item that is no id is kept. FactsError on an id that
        no row of the two files has."""
        def one(item: str) -> str:
            if not ID.fullmatch(item):
                return item
            if item not in self.by_id:
                raise _error(f"{where + ': ' if where else ''}{item} is no station_id of {STATIONS.name} or cp_id "
                             f"of {INTERLOCKINGS.name}")
            return self.by_id[item]
        return _map(cell, one)

    def ids(self, cell: str) -> str:
        """The ids of a cp cell's names (a station's first), ';' between them; an id, or a name no row has, is
        kept."""
        return _map(cell, lambda item: self.by_name.get(item, item))

    def with_names(self, row: dict, where: str = "") -> dict:
        """`row` with its cp cell named (in place); a row with no cp column is returned as it is."""
        if row.get(COLUMN):
            row[COLUMN] = self.names(row[COLUMN], where)
        return row

    def with_ids(self, rows: Iterable[Mapping[str, str]]) -> list[dict]:
        """Copies of `rows` with their cp cells as ids (a row with no cp column copied as it is)."""
        return [dict(r, **{COLUMN: self.ids(r[COLUMN])}) if r.get(COLUMN) else dict(r) for r in rows]


def _rows(name: str, data: bytes, id_col: str, name_col: str) -> list[tuple[int, str, str, str]]:
    """(line, id, level, name) of each row of one file's bytes, cells stripped."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _error(f"{name}: not UTF-8 text ({exc.reason} at byte {exc.start})") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    missing = [c for c in (id_col, "level", name_col) if c not in (reader.fieldnames or [])]
    if missing:
        raise _error(f"{name}: no column {', '.join(missing)}")
    return [(line, (r[id_col] or "").strip(), (r["level"] or "").strip(), (r[name_col] or "").strip())
            for line, r in enumerate(reader, 2)]


@lru_cache(maxsize=4)
def _table(stations: bytes, interlockings: bytes) -> Table:
    """The Table of the two files' bytes. A name is one place on the railroad, on every level: ids() turns a name
    into an id with no level to choose by. The one exception is a staging interlocking named as a station of its own
    level (Brick, Barn, East End, Princess: the module text), whose name stays the station's. FactsError naming the
    file and line on a malformed id, an id or name given twice (both rows), or an empty name."""
    by_id: dict[str, str] = {}
    by_name: dict[str, str] = {}
    first: dict[str, tuple[str, str, str]] = {}     # name -> (id, level, where) of the row that holds it
    shadow: dict[str, str] = {}                     # name -> where of the interlocking that carries a station's name
    for fname, data, id_col, name_col, prefix in (
            (STATIONS.name, stations, "station_id", "station", STATION_PREFIX),
            (INTERLOCKINGS.name, interlockings, "cp_id", "interlocking", CP_PREFIX)):
        for line, ident, level, name in _rows(fname, data, id_col, name_col):
            where = f"{fname} line {line} ({name or 'no name'}, level {level or 'empty'})"
            if not name:
                raise _error(f"{where}: {name_col} is empty")
            if not ID.fullmatch(ident) or not ident.startswith(prefix):
                raise _error(f"{where}: {id_col} {ident!r} is not {prefix}<lower-case words joined by ->")
            if ident in by_id:
                raise _error(f"{where}: {id_col} {ident} is given twice")
            by_id[ident] = name
            if name not in first:
                first[name] = (ident, level, where)
                by_name[name] = ident
                continue
            held, held_level, held_where = first[name]
            if prefix == CP_PREFIX and held.startswith(STATION_PREFIX) and held_level == level and name not in shadow:
                shadow[name] = where                # a staging interlocking named as its station
                continue
            raise _error(f"{where}: {name_col} {name!r} is the name of {shadow.get(name, held_where)} as well (a "
                         "station or control point name is given once; only an interlocking may carry the name of a "
                         "station on its own level)")
    return Table(by_id, by_name)


def _bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise _error(f"{path}: cannot read it ({exc.strerror})") from exc


def table(schematic: Path | None = None) -> Table:
    """The places of stations.csv and interlockings.csv in `schematic` (a folder holding both; default the repo's,
    lists_beside finds a copy's), cached on the bytes of both files."""
    st, il = _files(schematic)
    return _table(_bytes(st), _bytes(il))


def _map(cell: str, fn: Callable[[str], str]) -> str:
    return LIST.join(fn(p) if p else p for p in cell.split(LIST)) if cell else cell


def names(cell: str, where: str = "", schematic: Path | None = None) -> str:
    """The names of a cp cell's ids (Table.names) by the lists in `schematic` (default the repo's)."""
    return table(schematic).names(cell, where)


def ids(cell: str, schematic: Path | None = None) -> str:
    """The ids of a cp cell's names (Table.ids) by the lists in `schematic` (default the repo's)."""
    return table(schematic).ids(cell)


def _files(schematic: Path | None) -> tuple[Path, Path]:
    folder = SCHEMATIC if schematic is None else Path(schematic)
    return folder / STATIONS.name, folder / INTERLOCKINGS.name


def _stamp(path: Path) -> tuple[str, int, int]:
    try:
        st = path.stat()
    except OSError as exc:
        raise _error(f"{path}: cannot read it ({exc.strerror})") from exc
    return str(path), st.st_mtime_ns, st.st_size


@lru_cache(maxsize=8)
def _switch_places(stations: tuple[str, int, int], interlockings: tuple[str, int, int]
                   ) -> tuple[Mapping[tuple[str, str], str], Table]:
    from . import railroad_facts                # it imports level_masts, which imports this module
    st_path, il_path = Path(stations[0]), Path(interlockings[0])
    places = _table(_bytes(st_path), _bytes(il_path))
    by_name = places.by_name

    def ident_of(name: str, fname: str) -> str:
        if name not in by_name:
            raise _error(f"{fname}: {name!r} is no station or interlocking of {st_path.name} or {il_path.name}")
        return by_name[name]
    out: dict[tuple[str, str], str] = {}

    def put(key: tuple[str, str], ident: str, fname: str) -> None:
        if key in out and out[key] != ident:
            raise _error(f"{fname}: switch {key[1]} (level {key[0]}) is in {out[key]} and in {ident}: a switch has "
                         "one place")
        out[key] = ident
    for a in railroad_facts.read_desk_areas(st_path):
        if a.level == 1:
            ident = ident_of(a.name, st_path.name)
            for s in a.switches:
                put((str(a.level), s), ident, st_path.name)
    for x in railroad_facts.read_interlockings(il_path, levels=(2, 3)):
        ident = ident_of(x.name, il_path.name)
        if not ident.startswith(CP_PREFIX):
            raise _error(f"{il_path.name}: interlocking {x.name} (level {x.level}) has a station's name")
        for s in x.switches:
            put((str(x.level), s), ident, il_path.name)
    return out, places


def switch_places(schematic: Path | None = None) -> Mapping[tuple[str, str], str]:
    """{(level, switch number): place id}: staging's switches by desk area (as the naming station's id), main and
    upper's by interlocking (the module text), from the lists in `schematic` (a folder holding stations.csv and
    interlockings.csv; default the repo's). Cached on both files' path, mtime and size; a switch given two places
    stops."""
    st, il = _files(schematic)
    return _switch_places(_stamp(st), _stamp(il))[0]


def switch_place(level: str | int, switch: str | int, schematic: Path | None = None) -> str:
    """The place id of switch `switch` on `level` (switch_places), "" when the lists hold it in no place."""
    return switch_places(schematic).get((str(level), str(switch)), "")


def lists_beside(source: devices_mod.Files | Path | str | None) -> Path | None:
    """The schematic folder a file `source` goes with, when it holds its own stations.csv and is not the repo's: the
    file's own folder when that is a schematic folder (masts.csv), else the schematic folder of its data folder (a
    device master: a devices.Files, the master's path, or a data folder). None (the repo's lists) otherwise, so a
    copy with no lists of its own reads the repo's."""
    if source is None:
        return None
    path = Path(source) if isinstance(source, (str, Path)) else Path(source.master)
    data = path if path.is_dir() else path.parent
    folder = data if data.name == SCHEMATIC.name else data / SCHEMATIC.name
    if (folder / STATIONS.name).is_file() and folder.resolve() != SCHEMATIC.resolve():
        return folder
    return None


SWITCH_ID = re.compile(r"(?:switch|dcc):([1-9]\d*)")   # a turnout row's id: Switch <n> or DCC Switch <n>


def of(device: MasterRow | Mapping[str, str], schematic: Path | None = None) -> str:
    """The place a device row (a MasterRow, or a row of the master's text) sits in, by name. A turnout row has no cp
    cell: its place is its switch's (switch_place, from the lists in `schematic`, default the repo's; lists_beside
    finds a copy's), "" for a local switch or a level-less row. Any other row's place is its cp cell. FactsError on a
    turnout row with a level whose id is not switch:<n> or dcc:<n> (devices.check_rows refuses one too)."""
    row = row_cells(device)
    if row["layer"] != "turnout":
        return row["cp"]
    if not row["level"]:
        return ""
    m = SWITCH_ID.fullmatch(row["id"])
    if not m:
        raise _error(f"turnout {row.get('user_name', '?')!r} (level {row['level']}): id {row['id']!r} is not "
                     "switch:<n> or dcc:<n>, so it names no switch")
    ident = switch_place(row["level"], m.group(1), schematic)
    if not ident:
        return ""
    st, il = _files(schematic)
    by_id = _switch_places(_stamp(st), _stamp(il))[1].by_id
    if ident not in by_id:          # switch_places gives only ids of the lists; this guards a stand-in for it
        raise _error(f"turnout {row.get('user_name', '?')!r} (level {row['level']}): its switch's place {ident!r} "
                     "is no id of the lists")
    return by_id[ident]


def with_names(row: dict, where: str = "", schematic: Path | None = None) -> dict:
    """`row` with its cp cell named (Table.with_names) by the lists in `schematic` (default the repo's)."""
    return table(schematic).with_names(row, where)


def with_ids(rows: Iterable[Mapping[str, str]], schematic: Path | None = None) -> list[dict]:
    """Copies of `rows` with their cp cells as ids (Table.with_ids) by the lists in `schematic` (default the
    repo's)."""
    return table(schematic).with_ids(rows)
