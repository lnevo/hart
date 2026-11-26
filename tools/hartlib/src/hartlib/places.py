"""The railroad's places by id (ADR-039 lane L4c): the stations of schematic/stations.csv, keyed by `station_id`
(st:<name>), and the control points of schematic/interlockings.csv, keyed by `cp_id` (cp:<name>).

    places.table()               the Table of the repo's two files (read again when either file changes)
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

A turnout row of the device pair has no `cp` cell (owner, 2026-11-25): the switch lists of the two files are the one
place for the switch-to-place link, and `switch_place` gives a switch's place from them. On staging (level 1) it is
the desk area that holds the switch (railroad_facts.read_desk_areas), written as the id of the station that names the
area: Switches 1 and 3 are st:brick (Switch 3 also lies in West Yard, a station of the Brick desk area), 5 is
st:plane, 9 is st:engine-house (nested in Barn, a desk area of its own). Staging's interlockings, which group 1, 3
and 5 as Brick, are the signal rule's and give no turnout's place. On main and upper it is the interlocking that holds
the switch (cp:107); a local switch of a yard or spur is in none and has no place.

An item that is no id (a test's own place name) is left as it is either way. FactsError names the file and line on an
id that is malformed, given twice or under the wrong prefix, and on an id of a cell that no row has.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping

from . import paths

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


@dataclass(frozen=True)
class Table:
    by_id: Mapping[str, str]        # id -> name
    by_name: Mapping[str, str]      # name -> id (a station's before an interlocking's of the same name)


def _rows(name: str, data: bytes, id_col: str, name_col: str) -> list[tuple[int, str, str]]:
    reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""))
    missing = [c for c in (id_col, name_col) if c not in (reader.fieldnames or [])]
    if missing:
        raise _error(f"{name}: no column {', '.join(missing)}")
    return [(line, (r[id_col] or "").strip(), (r[name_col] or "").strip()) for line, r in enumerate(reader, 2)]


@lru_cache(maxsize=4)
def _table(stations: bytes, interlockings: bytes) -> Table:
    by_id: dict[str, str] = {}
    by_name: dict[str, str] = {}
    shadowed: dict[str, list[str]] = {}
    for fname, data, id_col, name_col, prefix in (
            (STATIONS.name, stations, "station_id", "station", STATION_PREFIX),
            (INTERLOCKINGS.name, interlockings, "cp_id", "interlocking", CP_PREFIX)):
        for line, ident, name in _rows(fname, data, id_col, name_col):
            where = f"{fname} line {line} ({name or 'no name'})"
            if not ID.fullmatch(ident) or not ident.startswith(prefix):
                raise _error(f"{where}: {id_col} {ident!r} is not {prefix}<lower-case words joined by ->")
            if ident in by_id:
                raise _error(f"{where}: {id_col} {ident} is given twice")
            by_id[ident] = name
            if name in by_name and prefix == CP_PREFIX:
                shadowed.setdefault(name, []).append(ident)   # a staging interlocking named as its station
                continue
            by_name[name] = ident
    clash = [n for n, ids in shadowed.items() if not by_name[n].startswith(STATION_PREFIX) or len(ids) > 1]
    if clash:
        raise _error(f"{INTERLOCKINGS.name}: control point name(s) {', '.join(clash)} are given twice")
    return Table(by_id, by_name)


def _bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise _error(f"{path}: cannot read it ({exc.strerror})") from None


def table() -> Table:
    """The places of the repo's stations.csv and interlockings.csv, cached on the bytes of both files."""
    return _table(_bytes(STATIONS), _bytes(INTERLOCKINGS))


def _map(cell: str, fn) -> str:
    return LIST.join(fn(p) if p else p for p in cell.split(LIST)) if cell else cell


def names(cell: str, where: str = "") -> str:
    """The names of a cp cell's ids, ';' between them; an item that is no id is kept. FactsError on an id that no row
    of the two files has."""
    by_id = table().by_id

    def one(item: str) -> str:
        if not ID.fullmatch(item):
            return item
        if item not in by_id:
            raise _error(f"{where + ': ' if where else ''}{item} is no station_id of {STATIONS.name} or cp_id "
                             f"of {INTERLOCKINGS.name}")
        return by_id[item]
    return _map(cell, one)


def ids(cell: str) -> str:
    """The ids of a cp cell's names (a station's first), ';' between them; an id, or a name no row has, is kept."""
    by_name = table().by_name
    return _map(cell, lambda item: by_name.get(item, item))


def _files(schematic: Path | None) -> tuple[Path, Path]:
    folder = SCHEMATIC if schematic is None else Path(schematic)
    return folder / STATIONS.name, folder / INTERLOCKINGS.name


def _stamp(path: Path) -> tuple[str, int, int]:
    try:
        st = path.stat()
    except OSError as exc:
        raise _error(f"{path}: cannot read it ({exc.strerror})") from None
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


def lists_beside(source) -> Path | None:
    """The schematic folder beside a device master `source` (a devices.Files, the master's path, or a data folder)
    when it holds its own stations.csv, so a copy's turnouts take the copy's lists; None (the repo's) otherwise."""
    if source is None:
        return None
    path = Path(getattr(source, "master", source))
    data = path if path.is_dir() else path.parent
    folder = data / SCHEMATIC.name
    if (folder / STATIONS.name).is_file() and folder.resolve() != SCHEMATIC.resolve():
        return folder
    return None


SWITCH_ID = re.compile(r"(?:switch|dcc):(\d+)")     # a turnout row's id: Switch <n> or DCC Switch <n>


def of(row: Mapping[str, str], schematic: Path | None = None) -> str:
    """The place a device row sits in, by name. A turnout row has no cp cell (owner, 2026-11-25): its place is its
    switch's (switch_place, from the lists in `schematic`, default the repo's; lists_beside finds a copy's), "" for a
    local switch or a level-less row. Any other row's place is its cp cell."""
    if row["layer"] != "turnout":
        return row["cp"]
    m = SWITCH_ID.fullmatch(row["id"])
    if not (m and row["level"]):
        return ""
    ident = switch_place(row["level"], m.group(1), schematic)
    if not ident:
        return ""
    st, il = _files(schematic)
    return _switch_places(_stamp(st), _stamp(il))[1].by_id.get(ident, ident)


def with_names(row: dict, where: str = "") -> dict:
    """`row` with its cp cell named (in place); a row with no cp column is returned as it is."""
    if row.get(COLUMN):
        row[COLUMN] = names(row[COLUMN], where)
    return row


def with_ids(rows: Iterable[Mapping[str, str]]) -> list[dict]:
    """Copies of `rows` with their cp cells as ids (a row with no cp column copied as it is)."""
    return [dict(r, **{COLUMN: ids(r[COLUMN])}) if r.get(COLUMN) else dict(r) for r in rows]
