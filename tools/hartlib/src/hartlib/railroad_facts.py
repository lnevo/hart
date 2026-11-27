"""The railroad's fact files read strictly into typed objects (hartlib.railroad has the layers and the rules)."""
from __future__ import annotations

import csv
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field, replace
from functools import cached_property
from pathlib import Path
from collections.abc import Callable, Collection, Iterable, Mapping
from typing import Any

from . import layer_files, level_devices, level_masts, paths, tables, track_names
from .errors import FactsError, HartlibError
from .device_rows import DEVICE_LIST, MASTER_COLUMNS, DeviceRow, MasterRow, device_list, row_cells  # noqa: F401
from .levels import ALL_LEVELS, MAIN_UPPER, Level, parse_level

LAYERS = ("inputs", "hands", "device_map", "masts", "tables")
WRITERS = {
    "hands": "tools/schematic/build_hands.py",
    "device_map": "tools/schematic/build_device_map.py",
    "masts": "tools/schematic/build_masts.py",
    "tables": "tools/schematic/build_tables.py (or a PanelPro Store)",
}
LEVEL_NUMBERS = MAIN_UPPER              # main and upper: the levels of the schematic's main_upper files
STAGING_LEVEL = "1"                     # staging: the level of the staging rows (read_staging_rows) and their device views
YES = {"yes": True, "no": False}
HANDS = {"", "L", "R"}
NAME_LAYERS = ("turnout", "fb", "block", "occupancy", "mast", "head")
DEVICE_COLUMNS = ("level", "cp", "layer", "user_name", "system_name", "jmri_name", "node", "dcc", "comment",
                  "trial_name", "notes", "blocks", "detector", "stop", "switch", "facing", "protects", "dir")
# The device maps' facts in columns of their own, so no code reads them out of the comment or
# notes, which stay as text for people (device_facts checks them):
#   blocks     occupancy rows: the blocks its detector serves, LIST separated (a throat and its yard track share one)
#   detector   occupancy rows: DETECTORS, whether the detector is in the field, planned on a node input, planned with
#              no input yet, or not planned at all
#   stop       block rows: "yes" for a Dispatcher System station (the "; stop" its JMRI comment carries)
#   switch, facing, protects   mast rows: the switch whose leg it stands at (none for an intermediate or a buffer stop
#              or anchor mast), the block it faces and the blocks it protects (LIST separated)
#   dir        mast rows: the way the mast looks, "east" or "west", set where the direction is known (mast_rule for a
#              home mast, mast_plan.intermediates for an APB one); the name's L/R or odd/even only labels it
DEVICE_FACTS = DEVICE_COLUMNS[11:]
MAST_DIRS = ("east", "west")
DETECTORS = ("wired", "planned", "not_wired", "none")
UNIQUE_HARDWARE = ("turnout", "fb", "occupancy", "head")   # layers whose hardware is one device's alone


class LayerError(HartlibError, RuntimeError):
    """A builder asked for a layer the pipeline writes after it (see the module text)."""


# ---------------------------------------------------------------- where the files are

@dataclass(frozen=True)
class Sources:
    """The files the facts are read from. Railroad() uses this checkout's; tests point `under` a copy."""
    switches: Path
    devices: Path
    interlockings: Path
    lcos_nodes: Path
    plan_overrides: Path
    block_lengths: Path
    masts: Path
    tables: Path
    stations: Path

    @classmethod
    def under(cls, data: Path = paths.LAYOUT_DATA, tables_xml: Path | None = None) -> "Sources":
        """The files at their places under a data folder laid out as jmri/layouts/hart/data/ is."""
        from . import devices       # devices imports this module, so the import waits for the call
        s = data / "schematic"
        return cls(switches=data / "switches.csv",
                   devices=devices.master_path(data),
                   interlockings=s / "interlockings.csv",
                   lcos_nodes=s / "lcos_nodes.csv",
                   plan_overrides=layer_files.path("plan_overrides", s), block_lengths=data / BLOCK_LENGTHS_NAME,
                   masts=s / level_masts.PATH.name,
                   tables=paths.TABLES_XML if tables_xml is None else tables_xml,
                   stations=s / "stations.csv")

    def but(self, **changes: Path) -> "Sources":
        """These sources with some files swapped (a builder's patched path, a test's copy)."""
        return replace(self, **changes)


# ---------------------------------------------------------------- reading a CSV strictly

def _where(path: Path, line: int) -> str:
    return f"{path.name} line {line}"


def master_at(path: Path, user_name: str, level: int | str, layer: str) -> str:
    """A device master row as a message names it: the file that holds it and its key, "devices_field.csv: Switch 1
    (level 1, turnout)" for a row with the owner's cells, else the generated file (hartlib.devices.Index.where; the
    master is two merged files, so a row has no line). A row the master at `path` does not hold (a caller's own) is
    named with `path`'s file."""
    from . import devices
    row = {"level": str(level), "layer": layer, "user_name": user_name}
    where = devices.index(path).where(row)
    return where if ": " in where else f"{where}: {devices.row_text(row)}"


def read_rows(path: Path, required: Iterable[str], *, optional: Iterable[str] = (),
              note: bool = False) -> list[tuple[int, dict[str, str]]]:
    """(line, row) for each row of a CSV: the `required` and `optional` columns only, values stripped. The header
    must hold every required column; other columns are allowed and left out. An optional column missing from the
    header, or from the end of a short row, reads as "". `note`: the first line is a `# ` note saying where the file
    came from. A row with more fields than the header, or without a required field, stops."""
    required, optional = list(required), [c for c in optional if c not in required]
    try:
        fh = path.open(newline="", encoding="utf-8")
    except OSError as exc:
        raise FactsError(f"{path}: cannot read it ({exc.strerror})") from exc
    with fh:
        if note and not fh.readline().startswith("# "):
            raise FactsError(f"{_where(path, 1)}: the note line (# ...) saying where the file came from")
        reader = csv.DictReader(fh)
        header = list(reader.fieldnames or [])
        missing = [c for c in required if c not in header]
        if missing:
            raise FactsError(f"{path.name}: no column {', '.join(missing)} (the header is {','.join(header)})")
        out = []
        for row in reader:
            line = reader.line_num + (1 if note else 0)
            short = [c for c in required if row.get(c) is None]
            if None in row or short:
                raise FactsError(f"{_where(path, line)}: {len(header)} fields ({','.join(header)}), not "
                                 f"{sum(v is not None for k, v in row.items() if k is not None) + len(row.get(None) or [])}")
            out.append((line, {c: (row.get(c) or "").strip() for c in required + optional}))
        return out


def _int(value: str, where: str, what: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise FactsError(f"{where}: {what} is a whole number, not {value!r}") from exc


def _level(value: str, where: str) -> Level:
    """A main or upper level (parse_level with MAIN_UPPER)."""
    return parse_level(value, where, MAIN_UPPER)


def natural(name: str) -> list:
    """Sort key that orders the numbers in a name as numbers ("Switch 9" before "Switch 101")."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", name)]


# ---------------------------------------------------------------- inputs: staging's rows of the device master

@dataclass(frozen=True)
class StagingDevice:
    """A staging (level 1) row of the device master in one of NAME_LAYERS, in the master's own columns."""
    line: int
    layer: str
    user_name: str
    role: str = ""
    assignment: str = ""
    system_name: str = ""
    jmri_name: str = ""
    node: str = ""
    cp: str = ""
    dcc: str = ""
    notes: str = ""


@dataclass(frozen=True)
class StagingDevices:
    path: Path
    rows: tuple[StagingDevice, ...]

    @cached_property
    def by_name(self) -> dict[tuple[str, str], StagingDevice]:
        """(layer, user name) -> its row."""
        return {(r.layer, r.user_name): r for r in self.rows}

    def names(self, layer: str) -> set[str]:
        return {name for lay, name in self.by_name if lay == layer}


STAGING_COLUMNS = ("layer", "user_name", "role", "assignment", "system_name", "jmri_name", "node", "cp", "dcc", "notes")


def read_staging_rows(path: Path) -> list[tuple[int, dict[str, str]]]:
    """(line, row) of staging's rows of the device master in NAME_LAYERS (STAGING_COLUMNS, values stripped), in master order,
    unchecked beyond the master's own checks (read_staging_devices checks them); a turnout's cp is places.of's."""
    from . import devices, places
    lists = places.lists_beside(path)          # a copy's turnouts take the copy's switch lists
    rows = [(n, r.cells() | {"cp": devices.place(r, lists)}) for n, r in enumerate(devices.load(path), 2)
            if r.level_cell == STAGING_LEVEL and r.layer in NAME_LAYERS]
    return [(n, {c: cells[c].strip() for c in STAGING_COLUMNS}) for n, cells in rows]


def read_staging_devices(path: Path, rows: list[tuple[int, dict[str, str]]] | None = None) -> StagingDevices:
    """Staging's rows of the device master at `path` (or its `rows`, read_staging_rows, which keeps NAME_LAYERS only), every
    row checked. Stops on an empty user name or a DCC address that is not a number (the master's own check holds the
    keys unique)."""
    out = []
    for line, r in read_staging_rows(path) if rows is None else rows:
        where = master_at(path, r["user_name"], STAGING_LEVEL, r["layer"])
        if not r["user_name"]:
            raise FactsError(f"{where}: user_name is empty")
        if r["dcc"] and not r["dcc"].isdigit():
            raise FactsError(f"{where}: dcc is a number or blank, not {r['dcc']!r}")
        out.append(StagingDevice(line=line, **r))
    return StagingDevices(path, tuple(out))


# ---------------------------------------------------------------- inputs: switches.csv, every level's switches (ADR-021)

SWITCH_COLUMNS = ("level", "switch", "half", "os_id", "closed_id", "thrown_id",
                  "hand", "hand_source", "area", "le_ident", "cats_inverted", "ctc_is", "ctc_signals", "notes")
# A staging row's OS block and legs are given by their device IDs only (os_id, closed_id, thrown_id). SwitchRow's
# os_block, closed_leg and thrown_leg are the name store's names of those IDs (devices.user_names), so a rename in
# devices_field.csv reaches every reader; a LABEL_COLUMNS column (a copy of a name) in the header stops the read.
LEG_IDS = {"os_block": "os_id", "closed_leg": "closed_id", "thrown_leg": "thrown_id"}
LABEL_COLUMNS = tuple(LEG_IDS)
HAND_SOURCES = ("plan", "owner")        # plan: build_hands.py writes it from the plan graph; owner: hand-kept
# Columns that hold a fact of the whole switch: given on its first row only (a crossover's later rows leave them blank)
SWITCH_WIDE = ("area", "le_ident", "cats_inverted", "ctc_is", "ctc_signals", "notes")
# Staging's bindings to its live Layout Editor, CATS desks and USS CTC board; main and upper leave them blank
STAGING_ONLY = ("le_ident", "cats_inverted", "ctc_is", "ctc_signals")
OS_BLOCK = re.compile(r"OS Switch (\d+)([a-z]?)")
HALF_OS_ID = re.compile(r"os:\d+:A-\w+")      # a staging crossover half's OS block ID (hartlib.device_ids)


@dataclass(frozen=True)
class SwitchRow:
    """A row of switches.csv: one OS block of a staging switch (keyed by os_block), or one half of a main or upper
    switch (keyed by half, the label the drawings print: 107, or a crossover half 101A). switches.columns.csv says
    what each column holds. os_block, closed_leg and thrown_leg are no columns: on a row keyed by its OS block they
    are the name store's names of os_id, closed_id and thrown_id (read_switch_rows); a row keyed by its half has
    none."""
    line: int
    level: Level
    switch: int
    half: str
    os_block: str
    closed_leg: str
    thrown_leg: str
    hand: str
    hand_source: str
    area: str
    le_ident: str
    cats_inverted: str
    ctc_is: str
    ctc_signals: str
    notes: str
    os_id: str = ""             # the device IDs of the OS block and legs (LEG_IDS): staging's key
    closed_id: str = ""
    thrown_id: str = ""

    @property
    def by_os(self) -> bool:
        """Whether the row is keyed by its OS block's device ID (os_id: staging's rows today), not by its half: its
        shape follows this column, not its level."""
        return bool(self.os_id)

    @property
    def key(self) -> str:
        return self.os_block if self.by_os else self.half


def switch_names(path: Path) -> Mapping[tuple[str, str], str]:
    """The name store's {(level, id): user name} for switches.csv at `path`: the device master beside it (a pair's
    devices_generated.csv, else a one-file copy's devices.csv: a test's copy), else the repo's
    (hartlib.devices.user_names). FactsError (a DevicesError) on a master that does not load."""
    from . import devices          # devices imports this module, so the import waits for the call
    data = Path(path).parent
    for source in (devices.master_path(data), data / devices.ONE_FILE):
        if source.is_file():
            return devices.user_names(source)
    return devices.user_names()            # a copy of switches.csv alone (a test's) names by this repo's master


def _no_label_columns(path: Path) -> None:
    """FactsError when switches.csv's header has a name column (LABEL_COLUMNS): the name store holds the names."""
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            header = next(csv.reader(fh), [])
    except OSError:
        return                                  # read_rows says why it cannot be read
    given = [c.strip() for c in header if c.strip() in LABEL_COLUMNS]
    if given:
        raise FactsError(f"{path.name}: {', '.join(given)} are no columns: a row gives the device IDs (os_id, "
                         "closed_id, thrown_id) and the name store gives their names")


SwitchNames = Mapping[tuple[str, str], str]


def read_switch_rows(path: Path, names: SwitchNames | Callable[[], SwitchNames] | None = None) -> list[SwitchRow]:
    """switches.csv's rows in file order, each held to the shape of its key, not its level:
    a row keyed by its OS block (an os_id: staging's rows today, SwitchRow.by_os) or by its half (main and upper's).
    An OS-keyed row's os_block, closed_leg and thrown_leg are the names of its os_id, closed_id and thrown_id in
    `names` ({(level, id): user name}; switch_names of `path` by default, read when the first such row is met).
    Stops with FactsError naming the file and line on: a missing column, a name column (LABEL_COLUMNS: the file
    holds IDs, not copies of names), a level that is not 1, 2 or 3, a switch number on two levels or on rows that are
    not together, a key (an os_block, or a half) given twice, an os_id that is not os:<n> or os:<n>:<half>, an
    OS-keyed row without its legs' IDs, an ID the name store has no device for, an OS-keyed row with a half or a plan
    hand_source, a half-keyed row with a leg ID, a column of the live bindings (STAGING_ONLY) or a half that is not
    its number (107) or its number and A or B (101A), a half-keyed switch whose rows are not either one half {n} or
    both {n}A and {n}B, a hand that is not L, R or blank, a hand with no hand_source (plan or owner) or an owner
    hand_source with no hand (a plan row's blank hand is build_hands.py's to fill), and a whole-switch column
    (SWITCH_WIDE; on an OS-keyed switch the hand too) on a switch's later row. A half-keyed row has no OS block or
    legs."""
    from . import switch_rows                  # it reads this module
    return switch_rows.read(path, names)


def switch_groups(rows: Iterable[SwitchRow], levels: Iterable[int]) -> dict[int, list[SwitchRow]]:
    """Switch number -> its rows (first row first) of the given levels, in file order."""
    levels = set(levels)
    out: dict[int, list[SwitchRow]] = {}
    for r in rows:
        if r.level in levels:
            out.setdefault(r.switch, []).append(r)
    return out


@dataclass(frozen=True)
class Leg:
    os_block: str
    closed: str
    thrown: str
    os_id: str = ""             # its OS block's device ID (switches.csv os_id): a crossover half's letter is keyed by it


@dataclass(frozen=True)
class Switch:
    """A staging switch (its level 1 rows of switches.csv: the first row's whole-switch columns and hand, and every
    row's legs) with, from its turnout row in the device master (staging's "Switch <n>"), its hardware (system_name), DCC
    address and control point."""
    number: int
    level: Level
    le_ident: str
    cats_inverted: bool
    ctc_is: int
    ctc_signals: bool
    legs: tuple[Leg, ...] = ()
    hand: str = ""
    hardware: str = ""
    dcc: str = ""
    cp: str = ""

    @property
    def turnout(self) -> str:
        """JMRI turnout user name, also the public name."""
        return f"Switch {self.number}"

    @property
    def os_blocks(self) -> tuple[str, ...]:
        """The first is the primary OS: Layout Editor blockname and first CTC OS sensor."""
        return tuple(leg.os_block for leg in self.legs)

    @property
    def uss_slot(self) -> int:
        """USS CTC lever column: plate N sits in column (N - 1) / 2."""
        return (self.number - 1) // 2


def _yes(value: str, where: str) -> bool:
    if value not in YES:
        raise FactsError(f"{where}: expected yes or no, got {value!r}")
    return YES[value]


def switch_turnouts(devices_csv: Path, rows: list[tuple[int, dict[str, str]]] | None = None,
                    numbers: Iterable[int] = ()) -> dict[int, dict[str, str]]:
    """Switch number -> staging's turnout row "Switch <n>" of the device master (read_staging_rows), for the switches
    `numbers`. Only those rows are looked at; a fault of another row (an unknown layer, a bad DCC address:
    read_staging_devices) is the railroad-facts check's to report. A bad row ANYWHERE in the master stops the load
    first (hartlib.devices.load checks the whole file, naming its line and row). Stops on a switch with two rows."""
    want = {f"Switch {n}": n for n in numbers}
    out: dict[int, dict[str, str]] = {}
    for _line, r in read_staging_rows(devices_csv) if rows is None else rows:
        n = want.get(r["user_name"])
        if n is None or r["layer"] != "turnout":
            continue
        if n in out:
            raise FactsError(f"{master_at(devices_csv, r['user_name'], STAGING_LEVEL, 'turnout')}: two rows "
                             f"are both the turnout Switch {n}")
        out[n] = r
    return out


def staging_switches(rows: list[SwitchRow], path: Path, devices_csv: Path,
                     staging_rows: list[tuple[int, dict[str, str]]] | None = None) -> dict[int, Switch]:
    """Switch number -> Switch of the rows keyed by their OS block (SwitchRow.by_os, read_switch_rows of `path`;
    staging's today: the switches bound to the live panels, desks and USS board), in file order; hardware
    (system_name), DCC address and control point from each switch's turnout row of `devices_csv` (switch_turnouts;
    `staging_rows` when the caller read them already). Stops on a switch whose first row lacks a whole-switch column, or a USS lever given twice."""
    groups = {n: rs for n, rs in switch_groups(rows, ALL_LEVELS).items() if rs[0].by_os}
    names = switch_turnouts(devices_csv, staging_rows, groups)
    out: dict[int, Switch] = {}
    lever: dict[int, tuple[int, int]] = {}
    for n, rs in groups.items():
        first = rs[0]
        where = f"{_where(path, first.line)} (Switch {n})"
        missing = [c for c in ("le_ident", "cats_inverted", "ctc_is", "ctc_signals") if not getattr(first, c)]
        if missing:
            raise FactsError(f"{where}: a staging switch's first row gives {', '.join(missing)}")
        ctc_is = _int(first.ctc_is, where, "ctc_is")
        if ctc_is in lever:
            line, other = lever[ctc_is]
            raise FactsError(f"{path.name} lines {line} (Switch {other}) and {first.line} (Switch {n}) "
                             f"both use USS lever IS{ctc_is}")
        lever[ctc_is] = (first.line, n)
        nm = names.get(n, {})
        out[n] = Switch(number=n, level=first.level, le_ident=first.le_ident,
                        cats_inverted=_yes(first.cats_inverted, where), ctc_is=ctc_is,
                        ctc_signals=_yes(first.ctc_signals, where),
                        legs=tuple(Leg(r.os_block, r.closed_leg, r.thrown_leg, r.os_id) for r in rs), hand=first.hand,
                        hardware=nm.get("system_name", ""), dcc=nm.get("dcc", ""), cp=nm.get("cp", ""))
    return out


def read_switches(path: Path, devices_csv: Path,
                  staging_rows: list[tuple[int, dict[str, str]]] | None = None) -> dict[int, Switch]:
    """The staging switches of switches.csv (staging_switches of read_switch_rows). Line numbers in errors count the
    header as 1."""
    return staging_switches(read_switch_rows(path), path, devices_csv, staging_rows)


# ---------------------------------------------------------------- inputs: main and upper control points and nodes

@dataclass(frozen=True)
class Interlocking:
    """An interlocking, the signal rule's control point (interlockings.csv): a group of switches
    whose home signals govern the routes between them. Staging's are named by place (Brick, Barn); main and upper's are
    "CP <lowest switch>", which are also their control points on the drawings and desks. `area`
    is the LCOS node area of a main or upper interlocking; staging leaves it blank, since staging's areas and desk
    groups are the desk areas of stations.csv (read_desk_areas)."""
    line: int
    level: Level
    name: str
    switches: tuple[str, ...]
    area: str
    notes: str = ""


def read_interlockings(path: Path, levels: Iterable[int] = ALL_LEVELS) -> list[Interlocking]:
    """The interlockings of `levels` in file order (the whole file is checked whatever `levels` asks for). Stops on a
    level that is not 1, 2 or 3, an interlocking with no switches, a name given twice on one level, a switch in two
    interlockings of one level, a main or upper interlocking with no area or a staging one with an area."""
    out: list[Interlocking] = []
    seen: dict[tuple[int, str], str] = {}          # (level, switch) -> its interlocking
    names: set[tuple[int, str]] = set()
    for line, r in read_rows(path, ("level", "interlocking", "switches", "area"), optional=("notes",)):
        where = _where(path, line)
        level = parse_level(r["level"], where)
        name = r["interlocking"]
        sw = tuple(s.strip() for s in r["switches"].split(",") if s.strip())
        if not sw or not all(s.isdigit() for s in sw):
            raise FactsError(f"{where} ({name}): switches is a list of switch numbers, not {r['switches']!r}")
        if not name or (level, name) in names:
            raise FactsError(f"{where}: an interlocking is named, once per level; {name!r} is not")
        names.add((level, name))
        for s in sw:
            if (level, s) in seen:
                raise FactsError(f"{where}: switch {s} is in {seen[(level, s)]} and {name}")
            seen[(level, s)] = name
        if level == 1 and r["area"]:
            raise FactsError(f"{where} ({name}): a staging interlocking has no area (stations.csv's "
                             "desk codes give staging's)")
        if level != 1 and not r["area"]:
            raise FactsError(f"{where} ({name}): no area (the LCOS node area of a main or upper interlocking)")
        if level in levels:
            out.append(Interlocking(line, level, name, sw, r["area"], r["notes"]))
    return out


# ---------------------------------------------------------------- inputs: stations and desk areas (stations.csv)

STATION_COLUMNS = ("level", "station", "switches", "tracks", "desk_code")
STATION_OPTIONAL = ("desk_plate", "notes")      # an absent desk_plate column puts no plate on the desks
DESK_CODE = re.compile(r"[A-Z]+")


@dataclass(frozen=True)
class Station:
    """A station of stations.csv (every level; one row each). `tracks` is the cell as written: blank counts the
    tracks from the switches, `none` none, else the block IDs of its tracks, `;` between them (block:3B-end;
    block:3C-end), whose names station_tracks gives from the name store; `desk_code` names its
    desk area; `desk_plate` (yes) puts a control point plate with its name on the CATS desks
    (cats_panel_dress.station_plates)."""
    line: int
    level: Level
    name: str
    switches: tuple[str, ...]
    tracks: str
    desk_code: str
    notes: str = ""
    desk_plate: bool = False

    @property
    def track_ids(self) -> tuple[str, ...] | None:
        """The block IDs of its `tracks` cell: None when blank (its tracks are counted from its switches), () for
        `none`."""
        if not self.tracks:
            return None
        if self.tracks == STATION_NO_TRACKS:
            return ()
        return tuple(t.strip() for t in self.tracks.split(";"))    # read_stations refuses an empty entry


STATION_NO_TRACKS = "none"      # the `tracks` cell of a station that counts no track


def station_tracks(stations: list[Station], path: Path) -> dict[str, tuple[str, ...]]:
    """{station: the names of the tracks its `tracks` cell gives ("Track W-1", in cell order)} of each station of
    `stations` (read_stations of `path`) whose cell lists block IDs, each named by the name store
    (hartlib.track_names.names_by_id: the owner's name in devices_field.csv, else the generated one, beside the
    schematic folder `path` sits in), so a renamed track changes no row of stations.csv. FactsError naming the file
    and line on an ID the store has no block for."""
    out = {}
    for st in stations:
        ids = st.track_ids
        if not ids:
            continue
        try:
            names = track_names.names_by_id(ids, Path(path).parent, f"{_where(path, st.line)} ({st.name}) tracks",
                                            levels={str(st.level)})
        except track_names.TrackNameError as exc:
            raise FactsError(str(exc)) from exc
        out[st.name] = tuple(names[i] for i in ids)
    return out


@dataclass(frozen=True)
class DeskArea:
    """A desk area: the stations of one level that share a desk code, named by the first of them in
    the file. Its switches are its stations' own: a station's switches less those of the stations nested in it (a
    station whose switches all lie in another's, as Engine House in Barn), in file order. These are the control
    points the drawings bracket and the CATS desks name (plan_generated.json's control_points, build_staging_sets)."""
    line: int                       # the naming station's line
    level: int
    name: str
    code: str
    switches: tuple[str, ...]
    stations: tuple[str, ...]
    notes: str = ""                 # the naming station's notes


def read_stations(path: Path) -> list[Station]:
    """The stations in file order. Stops, naming the file, line and station, on a level that is not 1, 2 or 3, a name
    that is empty or given twice, no switches, a switch that is not a number or is listed twice, and a desk code that
    is missing, not capital letters, or more than one, and a desk_plate that is not yes or empty."""
    out: list[Station] = []
    names: dict[str, int] = {}                     # station -> its line
    for line, r in read_rows(path, STATION_COLUMNS, optional=STATION_OPTIONAL):
        where = _where(path, line)
        name = r["station"]
        if not name:
            raise FactsError(f"{where}: the station has no name")
        at = f"{where} ({name})"
        if name in names:
            raise FactsError(f"{where}: station {name!r} is also on line {names[name]}")
        names[name] = line
        level = parse_level(r["level"], at)
        sw = tuple(s.strip() for s in re.split(r"[;,]", r["switches"]) if s.strip())
        if not sw:
            raise FactsError(f"{at}: no switches")
        for s in sw:
            if not s.isdigit():
                raise FactsError(f"{at}: switches is a list of switch numbers, not {r['switches']!r}")
            if sw.count(s) > 1:
                raise FactsError(f"{at}: lists switch {s} twice")
        code = r["desk_code"]
        if not code:
            raise FactsError(f"{at}: no desk code (every station is in one desk area)")
        if re.search(r"[\s,;/]", code):
            raise FactsError(f"{at}: two desk codes in {code!r}; a station is in one desk area")
        if not DESK_CODE.fullmatch(code):
            raise FactsError(f"{at}: desk code {code!r} is not capital letters")
        if r["desk_plate"] not in ("", "yes"):
            raise FactsError(f"{at}: desk_plate is yes or empty, not {r['desk_plate']!r}")
        if r["tracks"] and r["tracks"] != STATION_NO_TRACKS:
            ids = [t.strip() for t in r["tracks"].split(";")]
            if "" in ids:
                raise FactsError(f"{at}: tracks {r['tracks']!r} has an empty entry (a ; with no block ID beside it)")
            bad = [t for t in ids if not t.startswith(track_names.BLOCK_PREFIX)]
            if bad:
                raise FactsError(f"{at}: tracks is blank, none, or the block IDs of its tracks with ; between them "
                                 f"(block:3B-end; the names are the name store's), not {', '.join(map(repr, bad))}")
            if len(set(ids)) != len(ids):
                raise FactsError(f"{at}: tracks lists a block twice ({r['tracks']!r})")
        out.append(Station(line, level, name, sw, r["tracks"], code, r["notes"], r["desk_plate"] == "yes"))
    return out


def nested_own_areas(stations: list[Station]) -> set[str]:
    """The names of the stations nested in a station of another desk area (Engine House, EH, in Barn, BN): the
    stations that make a desk area of their own inside another station. A station nested in one of its own desk area
    (West Yard in Brick, both BK) is not one: it is part of that area. The Layout Editor build may leave these out of
    its station names (preferences.json le_nested_station_labels)."""
    out = set()
    for a in stations:
        sa = set(a.switches)
        if any(b.level == a.level and b.desk_code != a.desk_code and sa < set(b.switches) for b in stations):
            out.add(a.name)
    return out


def _innermost(stations: list[Station], path: Path) -> dict[tuple[int, str], Station]:
    """{(level, switch): the innermost station holding it}. Two stations of a level that share a switch must nest
    (one's switches all inside the other's), so the stations holding a switch run from the largest in to the smallest;
    of them, one at most may be a desk area nested in another area's station (nested_own_areas)."""
    for i, a in enumerate(stations):
        for b in stations[i + 1:]:
            shared = set(a.switches) & set(b.switches)
            if a.level != b.level or not shared:
                continue
            pair = f"{path.name} lines {a.line} and {b.line}: {a.name} and {b.name}"
            if set(a.switches) == set(b.switches):
                raise FactsError(f"{pair} have the same switches; one station must hold switches the other does not")
            if not (shared == set(a.switches) or shared == set(b.switches)):
                first = sorted(shared, key=int)[0]
                raise FactsError(f"{pair} share switch {first} but neither is inside the other; stations overlap "
                                 "only when one is nested in the other")
    own = nested_own_areas(stations)
    holders: dict[tuple[int, str], list[Station]] = {}
    for st in stations:
        for s in st.switches:
            holders.setdefault((st.level, s), []).append(st)
    out = {}
    for (level, s), held in holders.items():
        areas = [st for st in held if st.name in own]
        if len(areas) > 1:
            x, y = areas[:2]
            raise FactsError(f"{path.name} lines {x.line} and {y.line}: {x.name} and {y.name} are both desk areas "
                             f"nested in another area's station, with switch {s}; a switch is in one such area only")
        out[(level, s)] = min(held, key=lambda st: len(st.switches))
    return out


def desk_areas(stations: list[Station], path: Path, switches: Iterable[str] | None = None) -> list[DeskArea]:
    """The desk areas of `stations` (read from `path`, named in errors), each named by its first station: first the
    areas nested in no other area's station, then those that are (nested_own_areas: Engine House), each in the order
    its code first appears.
    `switches`, when given, are staging's switch numbers (level 1 of switches.csv): each must be in one staging desk
    area and every staging station switch one of them. Stops on a code used on two levels, an area left with no
    switches of its own, an area whose first station lies inside another station of the same area (it would name
    the area), and what _innermost stops on."""
    inner = _innermost(stations, path)
    own = nested_own_areas(stations)
    first: dict[str, Station] = {}
    members: dict[str, list[Station]] = {}
    for st in stations:
        lead = first.setdefault(st.desk_code, st)
        if lead.level != st.level:
            raise FactsError(f"{_where(path, st.line)} ({st.name}): desk code {st.desk_code} is level {lead.level}'s "
                             f"({lead.name}, line {lead.line}); a desk area is on one level")
        members.setdefault(st.desk_code, []).append(st)
    for code, lead in first.items():
        outer = next((st for st in members[code] if set(lead.switches) < set(st.switches)), None)
        if outer is not None:
            raise FactsError(f"{_where(path, lead.line)} ({lead.name}): the first station of desk area {code} lies "
                             f"inside {outer.name} (line {outer.line}) of the same area; list {outer.name} first, as "
                             "the area takes its name from its first station")
    out = []
    for code, lead in sorted(first.items(), key=lambda kv: kv[1].name in own):
        held = tuple(s for st in members[code] for s in st.switches if inner[(st.level, s)] is st)
        if not held:
            raise FactsError(f"desk area {code} ({lead.name}, {_where(path, lead.line)}) has no switches of its own: "
                             "the stations nested in its stations hold them all")
        out.append(DeskArea(lead.line, lead.level, lead.name, code, held, tuple(st.name for st in members[code]),
                            lead.notes))
    if switches is not None:
        known = set(switches)
        for st in stations:
            for s in st.switches:
                if st.level == 1 and s not in known:
                    raise FactsError(f"{_where(path, st.line)} ({st.name}): switch {s} is no staging switch "
                                     "(level 1 of switches.csv)")
        held_all = {s for a in out if a.level == 1 for s in a.switches}
        lost = sorted(known - held_all, key=lambda s: (len(s), s))
        if lost:
            raise FactsError(f"{path.name}: staging switch(es) {', '.join(lost)} are in no desk area")
    return out


def read_desk_areas(path: Path, switches: Iterable[str] | None = None) -> list[DeskArea]:
    """desk_areas of the stations in `path` (stations.csv)."""
    return desk_areas(read_stations(path), path, switches)


STATION_GROUP_COLUMNS = ("cp_key", "cp_name", "level", "switches", "notes", "code")


def half_text(number: int | str, name: str, letter: str) -> str:
    """The lower-case label of a crossover half with `letter` (a or b, by its ID): its number and letter ("23a"), or
    the bare number while the owner's name is "OS Switch <n>" and the half is a (staging's OS Switch 7, which has
    always been labelled 7). The letter is never read off the name: a half named like the other one still gets its
    own."""
    return str(number) if letter == "a" and name == f"OS Switch {number}" else f"{number}{letter}"


HalfLetters = Mapping[tuple[str, str], str]     # {(level, OS block id): letter}: hand_lists.half_letters


def os_label(r: SwitchRow, where: Path,
             letters: HalfLetters | Callable[[], HalfLetters] | None = None) -> str:
    """The label a desk area gives a switch row's OS block: "19", or a crossover half's "7", "7b", "23a". A switch's
    one OS block (os_id os:<n>) is its name less "OS Switch " while the name keeps that form for its number, else the
    number; a crossover half (os_id os:<n>:A-<end>) is half_text of its letter by its ID from `letters` ({(level, id):
    letter}, hartlib.hand_lists.half_letters, or a callable that gives them, read when a half is met). FactsError on a
    half with no letter there."""
    if not HALF_OS_ID.fullmatch(r.os_id):
        m = OS_BLOCK.fullmatch(r.os_block)
        if m and int(m.group(1)) == r.switch:
            return r.os_block.removeprefix("OS Switch ")
        if r.os_id == f"os:{r.switch}":
            return str(r.switch)
        raise FactsError(f"{_where(where, r.line)} (Switch {r.switch}): {r.os_id or 'no os_id'} is named "
                         f"{r.os_block!r}, which gives no label")
    letter = (letters() if callable(letters) else letters or {}).get((str(r.level), r.os_id))
    if letter is None:
        raise FactsError(f"{_where(where, r.line)} (Switch {r.switch}): {r.os_id} ({r.os_block}) is a crossover half "
                         "with no crossover_half row of block_overrides.csv to give its letter")
    return half_text(r.switch, r.os_block, letter)


def station_group_rows(stations: Path, switches: Path) -> list[dict[str, str]]:
    """The desk areas of every level (staging's only so far: the drawings' brackets and the CATS desk names; each
    row carries its level, so a caller that wants one level filters on it) in the shape the older
    data/control_points.csv had: cp_key the name in lower case with
    underscores (a key, not a place id: cp_id is interlockings.csv's cp:<name>, hartlib.places), level, code and
    notes the area's, and switches the OS block of each switch (a crossover by its halves, 7 as 7,7b and 23 as 23a,23b, from the os_block of its switches.csv rows, os_label: a renamed half by
    its number and its letter in block_overrides.csv beside `stations`), "," between. Stops with
    FactsError, naming the file, line and station, on what read_desk_areas or read_switch_rows stops on or a switch
    with no OS block."""
    from . import hand_lists          # it imports this module
    letters: dict[tuple[str, str], str] = {}
    loaded = False

    def half_letters() -> dict[tuple[str, str], str]:
        nonlocal loaded
        if not loaded:           # the crossover halves' letters, by ID (os_label), from beside stations.csv
            try:
                letters.update(hand_lists.half_letters(Path(stations).parent / hand_lists.OVERRIDES_NAME))
            except hand_lists.HandListError as exc:
                raise FactsError(str(exc)) from exc
            loaded = True
        return letters

    halves: dict[str, list[str]] = {}
    for r in read_switch_rows(switches):
        if r.os_block:
            halves.setdefault(str(r.switch), []).append(os_label(r, switches, half_letters))
    rows = read_stations(stations)
    inner = _innermost(rows, stations)
    out = []
    for a in desk_areas(rows, stations):
        sw = []
        for s in a.switches:
            if s not in halves:
                st = inner[(a.level, s)]        # the station that holds it for its area, not the one it lies in
                raise FactsError(f"{_where(stations, st.line)} ({st.name}): switch {s} has no OS block in "
                                 f"{switches.name}")
            sw += sorted(halves[s])
        out.append(dict(cp_key=re.sub(r"\W+", "_", a.name.lower()), cp_name=a.name, level=str(a.level),
                        switches=",".join(sw), notes=a.notes, code=a.code))
    return out


@dataclass(frozen=True)
class LocalSwitch:
    """A main or upper switch in no control point (a switches.csv switch whose first row gives its area): yards and
    spurs."""
    line: int
    switch: str
    level: int
    area: str
    notes: str = ""


def local_switches(rows: list[SwitchRow]) -> list[LocalSwitch]:
    """The main and upper switches whose first row of switches.csv (read_switch_rows) gives an area, in file order."""
    return [LocalSwitch(rs[0].line, str(n), rs[0].level, rs[0].area, rs[0].notes)
            for n, rs in switch_groups(rows, LEVEL_NUMBERS).items() if rs[0].area]


def read_local_switches(path: Path) -> list[LocalSwitch]:
    return local_switches(read_switch_rows(path))


@dataclass(frozen=True)
class HelixTrack:
    """A helix track: one JMRI block, `block` ("Track <plan name>", the ordinary rule), from its staging switch up the
    helix to its main or upper switch (`level_switch`, the label the drawing prints: 131A), under the plan's name
    `helix`, and `shown`, the name drawn for it (track_labels)."""
    helix: str
    block: str
    staging_switch: str
    level_switch: str
    shown: str


TRACK_LABELS = "track_labels"   # preferences.json[main_upper]: {plan name: label drawn}, the schematic-maps preference
#                                 (the hand file keys it by the staging helix block's ID; layer_files.merged names it)


def read_helix_tracks(path: Path) -> dict[str, HelixTrack]:
    """{plan helix track name: HelixTrack}, in the order of the main_upper `helix` map, from the plan overrides
    `path` (plan_overrides.json, as merged with its track names: layer_files.merged) and the preferences beside it. A
    helix track is a staging `end` edit of kind helix (its staging switch, and its name from the name store) and an entry of main_upper's `helix` map (its main or upper switch, the same
    plan name); its block is "Track <plan name>", as every named track's is; its `shown` name is its label in
    preferences.json[main_upper] track_labels (the schematic-maps plugin's sheet-wide preference, which every output
    honours), else the plan name. Stops (FactsError, naming the file and section) on a helix end edit not of five
    fields, an empty name, a name given twice in a section, the two sections naming different helix tracks, none at
    all, or track_labels not an object of non-empty strings."""
    folder = path.parent
    try:
        whole = layer_files.merged(folder)     # the names of the staging helix ends are the name store's
        staging = layer_files.section_of(whole, "staging", path.name)
        upper = layer_files.section_of(whole, "main_upper", path.name)
        # track_labels keyed by block ID in the hand file, named by the name store as the merged view names them;
        # only that key, so the helix tracks' owner names are all that is read (no generated name is needed)
        hand = layer_files.read("preferences", "main_upper", folder)
        own = {TRACK_LABELS: hand.get(TRACK_LABELS, {})}
        bad = track_names.pref_problems(own)            # a plan name put back is refused here too
        if bad:
            raise FactsError("helix tracks: preferences.json[main_upper]: " + "; ".join(bad))
        prefs = track_names.pref_section("main_upper", own, data=folder)
    except track_names.TrackNameError as exc:
        raise FactsError(f"helix tracks: {exc}") from exc
    except layer_files.LayerFileError as exc:
        raise FactsError(f"helix tracks: {exc}") from exc
    feet: dict[str, str] = {}
    for e in staging.get("edits", []):
        if e.get("op") != "end":
            continue
        for end in e.get("ends", []):
            if not (isinstance(end, list) and len(end) > 3 and end[3] == "helix"):
                continue                    # not a helix end: the plugin checks the other kinds
            if len(end) != 5:
                raise FactsError(f"{path.name}[staging]: helix end edit {end!r} is not [switch, leg, name, helix, to]")
            ref, _leg, name, _sub, _to = end
            if not name or name in feet:
                raise FactsError(f"{path.name}[staging]: helix end at Switch {ref} is named {name!r}: give each "
                                 "helix track one name, once")
            feet[name] = str(ref)
    tops: dict[str, str] = {}
    helix = upper.get("helix")
    if not isinstance(helix, dict):
        raise FactsError(f"{path.name}[main_upper]: `helix` is a map of switch to helix track name, not {helix!r}")
    for ref, name in helix.items():
        if not name or name in tops:
            raise FactsError(f"{path.name}[main_upper]: helix entry {ref} is named {name!r}: give each helix track "
                             "one name, once")
        tops[name] = str(ref)
    if not tops or set(feet) != set(tops):
        raise FactsError(f"{path.name}: the staging helix ends name {sorted(feet)}, main_upper's helix map "
                         f"{sorted(tops)}; each helix track is one track with one name on both")
    labels = track_labels(prefs)
    return {name: HelixTrack(name, f"Track {name}", feet[name], tops[name], labels.get(name, name)) for name in tops}


def track_labels(prefs: Mapping[str, Any]) -> dict[str, str]:
    """{plan name: label drawn} of a preferences section's track_labels ({} when unset). FactsError on a value that is
    not an object of non-empty strings; the plugin checks each key against the sheet's tracks."""
    labels = prefs.get(TRACK_LABELS, {})
    if not isinstance(labels, dict) or not all(isinstance(k, str) and k.strip() and isinstance(v, str) and v.strip()
                                               for k, v in labels.items()):
        raise FactsError(f"preferences.json[main_upper] {TRACK_LABELS}: {labels!r} is not an object of plan name to "
                         "label, both non-empty")
    return dict(labels)


@dataclass(frozen=True)
class LcosNode:
    """An LCOS radio address of a level and area (lcos_nodes.csv, every level): staging's are the nodes in service, as
    built (inventory v86); main and upper's the ones build_device_map.py may hand out, in the order it uses them."""
    line: int
    level: Level
    area: str
    node: int
    source: str = ""


def read_lcos_nodes(path: Path) -> list[LcosNode]:
    out: list[LcosNode] = []
    seen: dict[int, int] = {}                      # node -> its line
    for line, r in read_rows(path, ("level", "area", "node"), optional=("source",)):
        where = _where(path, line)
        node = _int(r["node"], where, "node")
        if node in seen:
            raise FactsError(f"{path.name} lines {seen[node]} and {line}: both list node {node}")
        seen[node] = line
        if not r["area"]:
            raise FactsError(f"{where}: no area")
        level = parse_level(r["level"], where)
        out.append(LcosNode(line, level, r["area"], node, r["source"]))
    return out


# ---------------------------------------------------------------- inputs: the main and upper plan's overrides

@dataclass(frozen=True)
class PlanOverrides:
    """A sheet's section of plan_overrides.json (main_upper unless read_plan_overrides is given another) (hartlib.layer_files). `data` is the whole section
    (build_device_map.py writes it back with its control_points and stations keys); `relabel` maps a plan switch label
    to the owner's switch number."""
    path: Path
    data: dict
    edits: tuple[dict, ...]
    relabel: dict[str, str]
    sheet: str = "main_upper"

    SHEET = "main_upper"

    @property
    def name(self) -> str:
        """How messages name it: plan_overrides.json[<the sheet read>]."""
        return f"{self.path.name}[{self.sheet}]"

    @property
    def helix(self) -> list:
        return list(self.data.get("helix", []))


def read_plan_overrides(path: Path, sheet: str = PlanOverrides.SHEET) -> PlanOverrides:
    """The `sheet` section of the plan overrides file `path` (a plan_overrides.json). Stops on a file or section
    hartlib.layer_files refuses, edits that are not a list of {op: ...}, or not exactly one relabel edit."""
    where = f"{path.name}[{sheet}]"
    if path.name != layer_files.path("plan_overrides", path.parent).name:
        raise FactsError(f"{path}: the plan overrides are plan_overrides.json, a section per sheet")
    try:
        data = layer_files.read("plan_overrides", sheet, path.parent)
    except layer_files.LayerFileError as exc:
        raise FactsError(f"{where}: not a readable layer section ({exc})") from exc
    edits = data.get("edits")
    if not isinstance(edits, list) or not all(isinstance(e, dict) and isinstance(e.get("op"), str) for e in edits):
        raise FactsError(f"{where}: `edits` is a list of objects with an `op`")
    relabels = [e for e in edits if e["op"] == "relabel"]
    if len(relabels) != 1 or not isinstance(relabels[0].get("map"), dict):
        raise FactsError(f"{where}: {len(relabels)} relabel edits; it needs exactly one, with a `map`")
    return PlanOverrides(path, data, tuple(edits), dict(relabels[0]["map"]), sheet)


# ---------------------------------------------------------------- inputs: block lengths and staging masts

# block_lengths.csv: each block's plan length, with block_lengths_measured.csv beside it (hartlib.block_lengths
# reads both: the plan length and the operating length).
BLOCK_LENGTHS_NAME = "block_lengths.csv"


@dataclass(frozen=True)
class Mast:
    """A mast's level, name and blocks, from schematic/masts.csv (hartlib.level_masts; protects ";" separated)."""
    line: int
    level: Level
    mast: str
    facing: str
    protects: tuple[str, ...]
    system_name: str = ""     # "IF$vsm:..." for a hidden virtual mast


def read_masts(path: Path, *, levels: tuple[int, ...] | None = None) -> list[Mast]:
    """masts.csv's rows of `levels` (every level when None) as Mast (hartlib.level_masts.read checks the file)."""
    return [Mast(r["line"], r["level"], r["mast"], r["facing"], tuple(b for b in r["protects"].split(";") if b),
                 r["system_name"]) for r in level_masts.read(path, levels=levels)]


# ---------------------------------------------------------------- hands (build_hands.py)

@dataclass(frozen=True)
class Hand:
    line: int
    switch: str          # the schematic label: "107", or a crossover half "101A"
    hand: str            # L or R
    source: str = ""     # the row's hand_source: plan (build_hands.py) or owner


def switch_number(label: str) -> str:
    """The switch number of a schematic label: "129A" -> "129", "223*" -> "223"."""
    return re.sub(r"[AB]$", "", (label or "").rstrip("*"))


def hands(rows: list[SwitchRow]) -> dict[str, Hand]:
    """{label: Hand} of the rows of switches.csv keyed by their half (main and upper's; read_switch_rows) that give a
    hand; `source` is the row's hand_source (plan or owner)."""
    return {r.half: Hand(r.line, r.half, r.hand, r.hand_source) for r in rows
            if not r.by_os and r.hand}


def read_hands(path: Path) -> dict[str, Hand]:
    return hands(read_switch_rows(path))


# ---------------------------------------------------------------- the device map (build_device_map.py)

DEVICE_LAYERS = NAME_LAYERS             # the device map's layers are staging's


@dataclass
class DeviceMap:
    """The main and upper device map. `blocks`: block user name -> row; `occupancy`: block user name -> the
    occupancy row that serves it (its virtual sensor is the row's jmri_name, its planned detector the system_name)."""
    rows: list[DeviceRow] = field(default_factory=list)
    blocks: dict[str, DeviceRow] = field(default_factory=dict)
    path: Path | None = None

    def of(self, layer: str) -> list[DeviceRow]:
        return [r for r in self.rows if r.layer == layer]

    def by_user(self, layer: str) -> dict[str, DeviceRow]:
        return {r.user_name: r for r in self.of(layer)}

    @cached_property
    def occupancy(self) -> dict[str, DeviceRow]:
        """Block user name -> the occupancy row that serves it, by the row's own blocks column (read_device_map holds
        each occupancy row to the one block it is named for), so a reader finds a block's sensor row without
        building its name. Built once, from `rows` as they are then. FactsError on a block two occupancy rows
        serve, naming their lines."""
        out: dict[str, DeviceRow] = {}
        for r in self.of("occupancy"):
            for block in r.served:
                if block in out:
                    raise FactsError(f"{self.path.name if self.path else 'the device map'}: occupancy "
                                     f"{out[block].user_name} and {r.user_name} both serve block {block}")
                out[block] = r
        return out

    @property
    def turnouts(self) -> dict[str, DeviceRow]:
        """Switch number -> its turnout row (not the LCC alias), the number from its ID (turnout_switch), so an
        owner's name for the turnout does not move it."""
        return {turnout_switch(r) or r.user_name.removeprefix("Switch "): r for r in self.of("turnout")
                if r.role == "turnout"}

    @property
    def heads_by_system(self) -> dict[str, DeviceRow]:
        """Planned physical head (IH<packed>) -> its head row."""
        return {r.system_name: r for r in self.of("head")}


def device_facts(r: dict) -> list[str]:
    """Problems with a device map row's fact columns (DEVICE_FACTS): each only on its own layer; an occupancy row's
    blocks given and its detector one of DETECTORS, with a system name (the field or planned detector) exactly when it
    is wired or planned; stop "yes" or empty; a mast's facing block given, its switch a number or empty and its dir
    east or west."""
    bad, layer = [], r["layer"]
    own = {"occupancy": ("blocks", "detector"), "block": ("stop",), "mast": ("switch", "facing", "protects", "dir")}
    stray = [c for c in DEVICE_FACTS if r.get(c) and c not in own.get(layer, ())]
    if stray:
        bad.append(f"a {layer} row has {', '.join(stray)}")
    if layer == "occupancy":
        if not device_list(r.get("blocks", "")):
            bad.append("an occupancy row names no blocks")
        if r.get("detector") not in DETECTORS:
            bad.append(f"detector {r.get('detector')!r} is not one of {', '.join(DETECTORS)}")
        elif (r["detector"] in ("wired", "planned")) != bool(r["system_name"]):
            bad.append(f"a {r['detector']} detector {'needs' if r['detector'] in ('wired', 'planned') else 'has no'} "
                       f"system name (it has {r['system_name']!r})")
    if layer == "block" and r.get("stop") not in ("", "yes"):
        bad.append(f"stop {r.get('stop')!r} is not yes or empty")
    if layer == "mast":
        if not r.get("facing"):
            bad.append("a mast row names no facing block")
        if r.get("switch") and not r["switch"].isdigit():
            bad.append(f"switch {r['switch']!r} is not a switch number")
        if r.get("dir") not in MAST_DIRS:
            bad.append(f"dir {r.get('dir')!r} is not one of {', '.join(MAST_DIRS)}")
    return bad


def read_device_map(path: Path) -> DeviceMap:
    """The main and upper rows of the device master at `path` (devices.device_map_lines). Stops on an unknown layer, a bad level, a (layer, user name) given twice (a turnout's LCC alias is its own
    row), a row whose fact columns do not hold (device_facts), an occupancy row whose jmri_name is not a virtual block
    sensor, whose planned detector is not M2S, or whose blocks are not the one block it is the detector of (by
    ID: det:<the block's id>, so a block the owner renamed keeps its detector); a field
    occupancy row (swapped in, ADR-028) is held instead to its wired M2S sensor. Each row carries its `id` and
    `assignment`."""
    out = DeviceMap(path=path)
    seen: dict[tuple[str, str], int] = {}
    from . import devices
    master = devices.load(path)         # device_map_lines numbers its rows by their place here, from 2
    block_ids: dict[tuple[str, str], str] = {}
    for line, r in ((n, {c: v.strip() for c, v in row.items()}) for n, row in devices.device_map_lines(("2", "3"), path)):
        r["id"], r["assignment"] = master[line - 2].id, master[line - 2].assignment
        where = master_at(path, r["user_name"], r["level"], r["layer"])
        if r["layer"] not in DEVICE_LAYERS or not r["user_name"]:
            raise FactsError(f"{where}: layer is one of {', '.join(DEVICE_LAYERS)} and user_name is given")
        bad = device_facts(r)
        if bad:
            raise FactsError(f"{where}: {r['layer']} {r['user_name']}: " + "; ".join(bad))
        key = (r["layer"], r["user_name"])
        if key in seen:
            raise FactsError(f"{where}: two rows are both {r['layer']} {r['user_name']}")
        seen[key] = line
        cells = {k: v for k, v in r.items() if k != "level"}
        row = DeviceRow(line=line, level=_level(r["level"], where), **cells)  # str columns
        out.rows.append(row)
        if row.layer == "block":
            out.blocks[row.user_name] = row
            block_ids[(r["level"], row.user_name)] = row.id
        elif row.layer == "occupancy":
            # by the row's assignment, not its level: a field detector (swapped in by its
            # row, ADR-028) is its wired M2S sensor; any other is a virtual stand-in with a planned M2S one or none
            if row.swapped:
                if not (row.jmri_name.startswith("M2S") and row.jmri_name == row.system_name) or \
                        row.detector != "wired":
                    raise FactsError(f"{where}: occupancy {row.user_name} is a field detector: its jmri_name is its "
                                     "system_name, an M2S sensor, and its detector is wired")
            elif not level_devices.is_block_sensor(row.jmri_name) or \
                    not (row.system_name == "" or row.system_name.startswith("M2S")) or row.detector == "wired":
                raise FactsError(f"{where}: occupancy {row.user_name} has no virtual {level_devices.SENSOR_PREFIX} "
                                 "jmri_name, or plans a detector that is not an M2S sensor, or calls it wired")
            if len(row.served) != 1 or not _detects(row, block_ids.get((r["level"], row.served[0]))):
                raise FactsError(f"{where}: occupancy {row.user_name} serves {row.served}, not the one block it is "
                                 "the detector of")
    out.occupancy                   # noqa: B018  built here, so a block two rows serve stops the read
    return out


def _detects(occupancy: DeviceRow, block_id: str | None) -> bool:
    """Whether `occupancy` is the detector of the one block it serves, whose ID is `block_id`: by ID (det:<block id>,
    hartlib.device_ids) when both rows carry one, else by the name rule (level_devices.occupancy_user) for rows made
    without IDs."""
    if occupancy.id and block_id:
        return occupancy.id == f"det:{block_id}"
    return level_devices.occupancy_user(occupancy.served[0]) == occupancy.user_name


def turnout_switch(row: DeviceRow) -> str | None:
    """The switch number of a turnout row: from its ID (switch:<n>, or dcc:<n> for its LCC alias), so an owner's
    name does not move it; a row made without an ID by its user name ("Switch <n>",
    "DCC Switch <n>"). None when neither gives one."""
    m = re.fullmatch(r"(?:switch|dcc):(\d+)", row.id or "")
    if row.id:
        return m.group(1) if m else None
    m = re.fullmatch(r"(?:DCC )?Switch (\d+)", row.user_name)
    return m.group(1) if m else None


def check_virtual_names(rows: Iterable[DeviceRow], owner_named: Collection[tuple[int, str]] = (),
                        swapped: Collection[tuple[int, str]] = ()) -> list[str]:
    """Problems with a device map's virtual names: every block has exactly one occupancy row, paired row by row (its
    detector by ID, det:<block id>; by the name rule between rows made without IDs, a test's; rows with and without
    IDs mixed are named), numbered by the block (hartlib.level_devices), every head's jmri_name comes from its user
    name, every turnout's from its switch number (turnout_switch: its ID's), and no two rows of a layer share a
    virtual name (but a turnout and its LCC alias, one JMRI turnout). By the (level, id) of the owner's rows in
    devices_field.csv: `owner_named`, the rows the owner names, whose virtual names stay the
    generated ones, so such a block, its detector, a mast's heads and a head are held to their virtual name's
    form only. A row whose assignment is field (DeviceRow.swapped: a field device swapped in by its row, ADR-028),
    or one of `swapped`'s (level, id), is held to no virtual-name rule."""
    rows = list(rows)
    owner_named, swapped = set(owner_named), set(swapped)

    def mine(r: DeviceRow, keys: set) -> bool:  # the row, or the mast of a head, is one of `keys`
        return bool(r.id) and ((r.level, r.id) in keys or
                               (r.layer == "head" and (r.level, r.id.rsplit(":", 1)[0]) in keys))

    def owned(r: DeviceRow) -> bool:
        return mine(r, owner_named)

    bad = []
    for layer in ("block", "occupancy"):            # the dicts and sets below would fold a second row away
        twice = sorted(n for n, k in Counter(r.user_name for r in rows if r.layer == layer).items() if k > 1)
        if twice:
            bad.append(f"{layer} rows given twice: {', '.join(twice)}")
    blocks = [r for r in rows if r.layer == "block"]
    occ = [r for r in rows if r.layer == "occupancy"]
    if any(r.id for r in blocks + occ):
        no_id = sorted(f"{r.layer} {r.user_name}" for r in blocks + occ if not r.id)
        if no_id:
            bad.append(f"rows with no id among rows with ids: {', '.join(no_id)}")
    # each block's detector row, row by row: by its ID, else by the name rule
    want = {(f"det:{b.id}" if b.id else "name:" + level_devices.occupancy_user(b.user_name)): b for b in blocks}
    have = {(r.id if r.id else "name:" + r.user_name): r for r in occ}
    if set(want) != set(have):
        bad.append("blocks and occupancy rows differ: "
                   f"{sorted(k.removeprefix('name:') for k in set(want) ^ set(have))}")
    for key, b in sorted(want.items()):
        r = have.get(key)
        if r is None or r.swapped or mine(r, swapped):
            continue
        if owned(b) or owned(r):
            if not level_devices.is_block_sensor(r.jmri_name):
                bad.append(f"occupancy {r.user_name}: jmri_name {r.jmri_name!r} is no virtual block sensor")
            continue
        try:
            sensor = level_devices.block_sensor(b.user_name)
        except ValueError as exc:
            bad.append(f"block {b.user_name}: {exc}")
            continue
        if r.jmri_name != sensor:
            bad.append(f"occupancy {r.user_name}: jmri_name {r.jmri_name!r}, not {sensor} (from block {b.user_name})")
    for r in rows:
        if r.swapped or mine(r, swapped):
            continue                            # a field device the owner swapped in: no virtual name
        if r.layer == "head" and owned(r):
            if not level_devices.HEAD.fullmatch(r.jmri_name):
                bad.append(f"head {r.user_name}: jmri_name {r.jmri_name!r} is no virtual head name")
        elif r.layer == "head":
            try:
                if r.jmri_name != level_devices.head_name(r.user_name):
                    bad.append(f"head {r.user_name}: jmri_name {r.jmri_name!r}, not "
                               f"{level_devices.head_name(r.user_name)}")
            except ValueError as exc:
                bad.append(str(exc))
        elif r.layer == "turnout":
            n = turnout_switch(r)
            if n is None or r.jmri_name != level_devices.TURNOUT_PREFIX + n:
                bad.append(f"turnout {r.user_name}: jmri_name {r.jmri_name!r}, not "
                           f"{level_devices.TURNOUT_PREFIX}<switch number>")
    for layer in ("occupancy", "head", "mast", "turnout"):
        names = [r.jmri_name for r in rows if r.layer == layer and r.role != "lcc_alias"]
        if len(set(names)) != len(names) or not all(names):
            bad.append(f"{layer} rows: a virtual name is empty or given twice")
    return bad


# ---------------------------------------------------------------- tables.xml

@dataclass
class TablesNames:
    """The beans of a tables file by user name: turnouts, sensors and masts (user -> system), and block names."""
    root: ET.Element
    turnouts: dict[str, str]
    sensors: dict[str, str]
    masts: dict[str, str]
    blocks: set[str]


def read_tables(path: Path) -> TablesNames:
    """The tables file's beans by user name; FactsError naming the file when it cannot be read or parsed, or when
    two beans of one type share a user name (a name check would pass on either of them)."""
    try:
        root = tables.read(path)
    except (OSError, ET.ParseError) as exc:
        raise FactsError(f"{path}: cannot read it as a tables file ({exc})") from exc

    def by_user(kind: str, beans: Iterable[ET.Element]) -> dict[str, str]:
        # A bean with no system name cannot be told apart from another, so it neither counts as a twin nor hides one.
        out: dict[str, str] = {}
        for b in beans:
            user, system = tables.user_name(b), tables.system_name(b)
            if not user:
                continue
            if not system:
                out.setdefault(user, "")
                continue
            if out.get(user) not in (None, "", system):
                raise FactsError(f"{path}: two {kind}s have the user name {user!r}: {out[user]} and {system}")
            out[user] = system
        return out
    # Every <block> form: JMRI writes each block twice (names only, then in full), and a block may exist only bare.
    by_user("block", tables.section(root, "blocks", "block"))
    return TablesNames(root, by_user("turnout", tables.turnouts(root)), by_user("sensor", tables.sensors(root)),
                       by_user("mast", tables.masts(root)),
                       {tables.user_name(b) or tables.system_name(b) for b in tables.blocks(root)})


# ---------------------------------------------------------------- the railroad

@dataclass(frozen=True)
class MainUpperSwitch:
    """A main or upper switch: in a control point (cp) or in none (a local switch of switches.csv)."""
    number: str
    level: int
    area: str
    cp: str = ""
    notes: str = ""


def join_main_upper(cps: Iterable[Interlocking], local: Iterable[LocalSwitch],
                    local_name: str = "switches.csv") -> dict[str, MainUpperSwitch]:
    """Switch number -> MainUpperSwitch, from the main and upper interlockings (their control points) and the local
    switches. Stops on a staging interlocking among `cps` or a switch in both."""
    cps = list(cps)
    staging = [cp.name for cp in cps if cp.level not in LEVEL_NUMBERS]
    if staging:
        raise FactsError(f"join_main_upper: {', '.join(staging)} are not main or upper interlockings")
    out = {s: MainUpperSwitch(s, cp.level, cp.area, cp.name) for cp in cps for s in cp.switches}
    for r in local:
        if r.switch in out:
            raise FactsError(f"switch {r.switch} is in a control point and in {local_name} (line {r.line}, "
                             f"{out[r.switch].cp})")
        out[r.switch] = MainUpperSwitch(r.switch, r.level, r.area, notes=r.notes)
    return out

