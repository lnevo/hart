"""The railroad's fact files read strictly into typed objects (hartlib.railroad has the layers and the rules)."""
from __future__ import annotations

import csv
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field, replace
from functools import cached_property
from pathlib import Path
from typing import Collection, Iterable

from . import layer_files, level_devices, level_masts, paths, tables, track_names

LAYERS = ("inputs", "hands", "device_map", "masts", "tables")
WRITERS = {
    "hands": "tools/schematic/build_hands.py",
    "device_map": "tools/schematic/build_device_map.py",
    "masts": "tools/schematic/build_masts.py",
    "tables": "tools/schematic/build_tables.py (or a PanelPro Store)",
}
LEVEL_NUMBERS = (2, 3)                  # main and upper: the levels of the schematic's main_upper files
STAGING_LEVEL = "1"                     # staging: the level of the staging rows (read_staging_rows) and their device views
YES = {"yes": True, "no": False}
HANDS = {"", "L", "R"}
NAME_LAYERS = ("turnout", "fb", "block", "occupancy", "mast", "head")
DEVICE_COLUMNS = ("level", "cp", "layer", "user_name", "system_name", "jmri_name", "node", "dcc", "comment",
                  "trial_name", "notes", "blocks", "detector", "stop", "switch", "facing", "protects", "dir")
# The device maps' facts in columns of their own (owner, 2026-11-20), so no code reads them out of the comment or
# notes, which stay as text for people (device_facts checks them):
#   blocks     occupancy rows: the blocks its detector serves, LIST separated (a throat and its yard track share one)
#   detector   occupancy rows: DETECTORS, whether the detector is in the field, planned on a node input, planned with
#              no input yet, or not planned at all
#   stop       block rows: "yes" for a Dispatcher System station (the "; stop" its JMRI comment carries)
#   switch, facing, protects   mast rows: the switch whose leg it stands at (none for an intermediate or a buffer stop
#              or anchor mast), the block it faces and the blocks it protects (LIST separated)
#   dir        mast rows: the way the mast looks, "east" or "west", set where the direction is known (mast_rule for a
#              home mast, build_device_map.intermediates for an APB one); the name's L/R or odd/even only labels it
DEVICE_FACTS = DEVICE_COLUMNS[11:]
DEVICE_LIST = ";"
MAST_DIRS = ("east", "west")
DETECTORS = ("wired", "planned", "not_wired", "none")
UNIQUE_HARDWARE = ("turnout", "fb", "occupancy", "head")   # layers whose hardware is one device's alone


class FactsError(ValueError):
    """A fact file that cannot be read as it stands: the message names the file and the row."""


class LayerError(RuntimeError):
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


def master_at(path: Path, user_name: str, level, layer: str) -> str:
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
        raise FactsError(f"{path}: cannot read it ({exc.strerror})") from None
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
    except ValueError:
        raise FactsError(f"{where}: {what} is a whole number, not {value!r}") from None


def _level(value: str, where: str) -> int:
    level = _int(value, where, "level")
    if level not in LEVEL_NUMBERS:
        raise FactsError(f"{where}: level is {' or '.join(map(str, LEVEL_NUMBERS))} (main, upper), not {level}")
    return level


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
    unchecked beyond the master's own checks (read_staging_devices checks them)."""
    from . import devices
    return [(n, {c: r[c].strip() for c in STAGING_COLUMNS}) for n, r in enumerate(devices.load(path), 2)
            if r["level"] == STAGING_LEVEL and r["layer"] in NAME_LAYERS]


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

SWITCH_COLUMNS = ("level", "switch", "half", "os_block", "closed_leg", "thrown_leg", "os_id", "closed_id", "thrown_id",
                  "hand", "hand_source", "area", "le_ident", "cats_inverted", "ctc_is", "ctc_signals", "notes")
# A staging row's OS block and legs are keyed by their device IDs (os_id, closed_id, thrown_id; naming-layers step 5);
# os_block, closed_leg and thrown_leg are their labels, the name store's, which build_hands.py (the hands step of make
# panels) writes, so a rename in devices_field.csv relabels the row and every reader by name follows it.
LEG_IDS = {"os_block": "os_id", "closed_leg": "closed_id", "thrown_leg": "thrown_id"}
HAND_SOURCES = ("plan", "owner")        # plan: build_hands.py writes it from the plan graph; owner: hand-kept
# Columns that hold a fact of the whole switch: given on its first row only (a crossover's later rows leave them blank)
SWITCH_WIDE = ("area", "le_ident", "cats_inverted", "ctc_is", "ctc_signals", "notes")
# Staging's bindings to its live Layout Editor, CATS desks and USS CTC board; main and upper leave them blank
STAGING_ONLY = ("le_ident", "cats_inverted", "ctc_is", "ctc_signals")
OS_BLOCK = re.compile(r"OS Switch (\d+)([a-z]?)")


@dataclass(frozen=True)
class SwitchRow:
    """A row of switches.csv: one OS block of a staging switch (keyed by os_block), or one half of a main or upper
    switch (keyed by half, the label the drawings print: 107, or a crossover half 101A). switches.columns.csv says
    what each column holds."""
    line: int
    level: int
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
    def key(self) -> str:
        return self.os_block if self.level == 1 else self.half


def read_switch_rows(path: Path) -> list[SwitchRow]:
    """switches.csv's rows in file order, each held to its level's shape. Stops with FactsError naming the file and
    line on: a missing column, a level that is not 1, 2 or 3, a switch number on two levels or on rows that are not
    together, a key (staging's os_block, main and upper's half) given twice, an os_block that is not an OS Switch block
    of the row's number, one leg without the other or legs without an os_block, a staging row without its os_block
    and legs or with a half, a main or upper row with a staging-only column (STAGING_ONLY) or a half that is not its
    number (107) or its number and A or B (101A), a main or upper switch whose rows are not either one half {n} or
    both {n}A and {n}B, a hand that is not L, R or blank, a hand with no hand_source (plan or owner) or an owner
    hand_source with no hand (a plan row's blank hand is build_hands.py's to fill), and a whole-switch column
    (SWITCH_WIDE; on staging the hand too) on a switch's later row. A main
    or upper row's os_block and legs are optional: none is given yet; station_group_rows reads an os_block on any
    level, and only staging's legs are read so far (staging_switches)."""
    out: list[SwitchRow] = []
    keys: dict[str, int] = {}
    first_of: dict[int, tuple[int, int]] = {}          # switch -> (level, line of its first row)
    for line, r in read_rows(path, SWITCH_COLUMNS):
        n = _int(r["switch"], _where(path, line), "switch")
        where = f"{_where(path, line)} (Switch {n})"
        level = _int(r["level"], where, "level")
        if level not in ALL_LEVELS:
            raise FactsError(f"{where}: level is 1, 2 or 3 (staging, main, upper), not {level}")
        later = bool(out) and out[-1].switch == n
        if n in first_of:
            lv, ln = first_of[n]
            if lv != level:
                raise FactsError(f"{path.name} lines {ln} (level {lv}) and {line} (level {level}) both use Switch {n}; "
                                 "switch numbers are unique railroad-wide")
            if not later:
                raise FactsError(f"{where}: Switch {n} is also on line {ln}; a switch's rows go together")
        first_of.setdefault(n, (level, line))
        if level == 1:
            if not re.fullmatch(rf"os:{n}(:[A-Z0-9-]+)?", r["os_id"]) or not r["closed_id"] or not r["thrown_id"]:
                raise FactsError(f"{where}: a staging row gives the device IDs of its OS block (os_id os:{n}, or "
                                 f"os:{n}:<half>) and of its legs (closed_id, thrown_id), not {r['os_id']!r}, "
                                 f"{r['closed_id']!r}, {r['thrown_id']!r}")
            if not r["os_block"]:
                raise FactsError(f"{where}: os_block is empty; build_hands.py writes the label of {r['os_id']}")
        elif r["os_block"]:
            m = OS_BLOCK.fullmatch(r["os_block"])
            if not m or int(m.group(1)) != n:
                raise FactsError(f"{where}: os_block is OS Switch {n} or a half of it (OS Switch {n}b), "
                                 f"not {r['os_block']!r}")
        if level != 1 and any(r[c] for c in LEG_IDS.values()):
            raise FactsError(f"{where}: os_id, closed_id and thrown_id are staging's; main and upper leave them blank")
        if (bool(r["closed_leg"]) != bool(r["thrown_leg"]) or (r["closed_leg"] and not r["os_block"])
                or (level == 1 and not r["closed_leg"])):
            raise FactsError(f"{where}: a row gives both legs (closed_leg, thrown_leg) with its os_block, or neither; "
                             "a staging row gives them")
        if level == 1:
            if r["half"]:
                raise FactsError(f"{where}: a staging row has no half (its os_block is its key), not {r['half']!r}")
            if r["hand_source"] == "plan":
                raise FactsError(f"{where}: hand_source plan is for main and upper (build_hands.py); staging's hands "
                                 "are the owner's")
        else:
            if r["half"] not in (str(n), f"{n}A", f"{n}B"):
                raise FactsError(f"{where}: half is {n}, {n}A or {n}B, not {r['half']!r}")
            given = [c for c in STAGING_ONLY if r[c]]
            if given:
                raise FactsError(f"{where}: {', '.join(given)} are staging columns; main and upper leave them blank")
        if r["hand"] not in HANDS:
            raise FactsError(f"{where}: hand is L, R or blank, got {r['hand']!r}")
        # a plan row may wait for build_hands.py to fill its hand; an owner row gives one
        if ((r["hand"] and not r["hand_source"]) or (r["hand_source"] and r["hand_source"] not in HAND_SOURCES)
                or (r["hand_source"] == "owner" and not r["hand"])):
            raise FactsError(f"{where}: a hand needs a hand_source ({' or '.join(HAND_SOURCES)}), and an owner "
                             f"hand_source a hand; got hand {r['hand']!r}, hand_source {r['hand_source']!r}")
        # staging's hand is a fact of the whole switch (Switch.hand); main and upper give one per half
        wide = SWITCH_WIDE + (("hand", "hand_source") if level == 1 else ())
        repeated = [c for c in wide if later and r[c]]
        if repeated:
            raise FactsError(f"{where}: {', '.join(repeated)} hold a fact of the whole switch: give them on its first "
                             f"row (line {first_of[n][1]}) only")
        row = SwitchRow(line, level, n, **{c: r[c] for c in SWITCH_COLUMNS[2:]})
        if row.key in keys:
            raise FactsError(f"{path.name} lines {keys[row.key]} and {line}: both are {row.key}")
        keys[row.key] = line
        out.append(row)
    for n, rs in switch_groups(out, LEVEL_NUMBERS).items():
        halves = sorted(r.half for r in rs)
        if halves not in ([str(n)], [f"{n}A", f"{n}B"]):
            raise FactsError(f"{_where(path, rs[0].line)} (Switch {n}): a main or upper switch has one row, half {n}, "
                             f"or two, halves {n}A and {n}B; not {', '.join(halves)}")
    return out


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


@dataclass(frozen=True)
class Switch:
    """A staging switch (its level 1 rows of switches.csv: the first row's whole-switch columns and hand, and every
    row's legs) with, from its turnout row in the device master (staging's "Switch <n>"), its hardware (system_name), DCC
    address and control point."""
    number: int
    level: str
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
    """Switch number -> Switch of the level 1 rows (read_switch_rows of `path`), in file order; hardware
    (system_name), DCC address and control point from each switch's turnout row of `devices_csv` (switch_turnouts;
    `staging_rows` when the caller read them already). Stops on a switch whose first row lacks a whole-switch column, or a USS lever given twice."""
    groups = switch_groups(rows, (1,))
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
        out[n] = Switch(number=n, level=str(first.level), le_ident=first.le_ident,
                        cats_inverted=_yes(first.cats_inverted, where), ctc_is=ctc_is,
                        ctc_signals=_yes(first.ctc_signals, where),
                        legs=tuple(Leg(r.os_block, r.closed_leg, r.thrown_leg) for r in rs), hand=first.hand,
                        hardware=nm.get("system_name", ""), dcc=nm.get("dcc", ""), cp=nm.get("cp", ""))
    return out


def read_switches(path: Path, devices_csv: Path,
                  staging_rows: list[tuple[int, dict[str, str]]] | None = None) -> dict[int, Switch]:
    """The staging switches of switches.csv (staging_switches of read_switch_rows). Line numbers in errors count the
    header as 1."""
    return staging_switches(read_switch_rows(path), path, devices_csv, staging_rows)


# ---------------------------------------------------------------- inputs: main and upper control points and nodes

ALL_LEVELS = (1, 2, 3)                  # staging, main, upper: interlockings.csv holds every level


@dataclass(frozen=True)
class Interlocking:
    """An interlocking, the signal rule's control point (interlockings.csv, owner 2026-11-20): a group of switches
    whose home signals govern the routes between them. Staging's are named by place (Brick, Barn); main and upper's are
    "CP <lowest switch>" (owner, 2026-11-15), which are also their control points on the drawings and desks. `area`
    is the LCOS node area of a main or upper interlocking; staging leaves it blank, since staging's areas and desk
    groups are the desk areas of stations.csv (read_desk_areas)."""
    line: int
    level: int
    name: str
    switches: tuple[str, ...]
    area: str
    notes: str = ""


def read_interlockings(path: Path, levels: Iterable[int] = ALL_LEVELS) -> list[Interlocking]:
    """The interlockings of `levels` in file order (the whole file is checked whatever `levels` asks for). Stops on a
    level that is not 1, 2 or 3, an interlocking with no switches, a name given twice on one level, a switch in two
    interlockings of one level, a main or upper interlocking with no area or a staging one with an area."""
    out, seen, names = [], {}, set()
    for line, r in read_rows(path, ("level", "interlocking", "switches", "area"), optional=("notes",)):
        where = _where(path, line)
        level = _int(r["level"], where, "level")
        if level not in ALL_LEVELS:
            raise FactsError(f"{where}: level is 1, 2 or 3 (staging, main, upper), not {level}")
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
    block:3C-end; naming-layers step 5b), whose names station_tracks gives from the name store; `desk_code` names its
    desk area; `desk_plate` (yes) puts a control point plate with its name on the CATS desks
    (cats_panel_dress.station_plates)."""
    line: int
    level: int
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
            raise FactsError(str(exc)) from None
        out[st.name] = tuple(names[i] for i in ids)
    return out


@dataclass(frozen=True)
class DeskArea:
    """A desk area (owner, 2026-11-20): the stations of one level that share a desk code, named by the first of them in
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
    out, names = [], {}
    for line, r in read_rows(path, STATION_COLUMNS, optional=STATION_OPTIONAL):
        where = _where(path, line)
        name = r["station"]
        if not name:
            raise FactsError(f"{where}: the station has no name")
        at = f"{where} ({name})"
        if name in names:
            raise FactsError(f"{where}: station {name!r} is also on line {names[name]}")
        names[name] = line
        level = _int(r["level"], at, "level")
        if level not in ALL_LEVELS:
            raise FactsError(f"{at}: level is 1, 2 or 3 (staging, main, upper), not {level}")
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
        held = {s for a in out if a.level == 1 for s in a.switches}
        lost = sorted(known - held, key=lambda s: (len(s), s))
        if lost:
            raise FactsError(f"{path.name}: staging switch(es) {', '.join(lost)} are in no desk area")
    return out


def read_desk_areas(path: Path, switches: Iterable[str] | None = None) -> list[DeskArea]:
    """desk_areas of the stations in `path` (stations.csv)."""
    return desk_areas(read_stations(path), path, switches)


STATION_GROUP_COLUMNS = ("cp_id", "cp_name", "level", "switches", "notes", "code")


def os_label(r: SwitchRow, where: Path) -> str:
    """The label a desk area gives a switch row's OS block: "19", or a crossover half's "7b", "23a". It is the OS
    block's name less "OS Switch " while the name keeps that form; a renamed OS block of a switch with one (os_id
    os:<n>) is its number. FactsError on a renamed crossover half: which half letter it is, the name said, and nothing
    else holds it yet (naming-layers step 5, open)."""
    m = OS_BLOCK.fullmatch(r.os_block)
    if m and int(m.group(1)) == r.switch:
        return r.os_block.removeprefix("OS Switch ")
    if r.os_id == f"os:{r.switch}":
        return str(r.switch)
    raise FactsError(f"{_where(where, r.line)} (Switch {r.switch}): {r.os_id} is named {r.os_block!r}; a crossover "
                     "half's name gives its half letter (OS Switch 7b), so it keeps that form for now")


def station_group_rows(stations: Path, switches: Path) -> list[dict[str, str]]:
    """The desk areas of every level (staging's only so far: the drawings' brackets and the CATS desk names; each
    row carries its level, so a caller that wants one level filters on it) in the shape the older
    data/control_points.csv had, which this replaces (level-unification step 8): cp_id the name in lower case with
    underscores, level, code and notes the area's, and switches the OS block of each switch (a crossover by its
    halves, 7 as 7,7b and 23 as 23a,23b, from the os_block of its switches.csv rows), "," between. Stops with
    FactsError, naming the file, line and station, on what read_desk_areas or read_switch_rows stops on or a switch
    with no OS block."""
    halves: dict[str, list[str]] = {}
    for r in read_switch_rows(switches):
        if r.os_block:
            halves.setdefault(str(r.switch), []).append(os_label(r, switches))
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
        out.append(dict(cp_id=re.sub(r"\W+", "_", a.name.lower()), cp_name=a.name, level=str(a.level),
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
    `helix` (owner, 2026-11-20/21), and `shown`, the name drawn for it (track_labels)."""
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
            raise FactsError(f"helix tracks: preferences.json[main_upper]: " + "; ".join(bad))
        prefs = track_names.pref_section("main_upper", own, data=folder)
    except track_names.TrackNameError as exc:
        raise FactsError(f"helix tracks: {exc}") from None
    except layer_files.LayerFileError as exc:
        raise FactsError(f"helix tracks: {exc}") from None
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


def track_labels(prefs: dict) -> dict[str, str]:
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
    level: int
    area: str
    node: int
    source: str = ""


def read_lcos_nodes(path: Path) -> list[LcosNode]:
    out, seen = [], {}
    for line, r in read_rows(path, ("level", "area", "node"), optional=("source",)):
        where = _where(path, line)
        node = _int(r["node"], where, "node")
        if node in seen:
            raise FactsError(f"{path.name} lines {seen[node]} and {line}: both list node {node}")
        seen[node] = line
        if not r["area"]:
            raise FactsError(f"{where}: no area")
        level = _int(r["level"], where, "level")
        if level not in (1, *LEVEL_NUMBERS):
            raise FactsError(f"{where}: level is 1, 2 or 3 (staging, main, upper), not {level}")
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
        raise FactsError(f"{where}: not a readable layer section ({exc})") from None
    edits = data.get("edits")
    if not isinstance(edits, list) or not all(isinstance(e, dict) and isinstance(e.get("op"), str) for e in edits):
        raise FactsError(f"{where}: `edits` is a list of objects with an `op`")
    relabels = [e for e in edits if e["op"] == "relabel"]
    if len(relabels) != 1 or not isinstance(relabels[0].get("map"), dict):
        raise FactsError(f"{where}: {len(relabels)} relabel edits; it needs exactly one, with a `map`")
    return PlanOverrides(path, data, tuple(edits), dict(relabels[0]["map"]), sheet)


# ---------------------------------------------------------------- inputs: block lengths and staging masts

# block_lengths.csv: each block's 5.3c plan length on every level (plan_in, written by tools/schematic/plan_lengths.py)
# and, for a timed staging block, its measured length (measured_in; `source` timed, else plan). JMRI's block length,
# the drawings and the signal rules use plan_in alone; the measured lengths serve speed profiling only (owner,
# 2026-11-20, level unification step 5 part 2). A row is keyed by its block's level and device ID (naming-layers step
# 5), so a rename keeps its measured length; user_name is a label the build writes from the name store
# (plan_lengths.py --labels, the length-labels step of make panels) for the readers that go by name (the speed-match
# tools on the Pi, the documentation pages).
BLOCK_LENGTH_COLUMNS = ("level", "id", "user_name", "occupancy_sensor", "plan_in", "measured_in", "source", "note")
BLOCK_LENGTHS_NAME = "block_lengths.csv"
BLOCK_LENGTHS = paths.LAYOUT_DATA / BLOCK_LENGTHS_NAME      # this checkout's file, read_block_lengths' default
LENGTH_SOURCES = ("timed", "plan")


@dataclass(frozen=True)
class BlockLength:
    line: int
    user_name: str
    occupancy_sensor: str
    plan_in: float              # the AnyRail plan 5.3c length
    measured_in: float | None   # the timed length; None unless source is "timed"
    source: str                 # LENGTH_SOURCES: timed when the block has a measured length (speed profiling)
    level: str = ""             # the block's level and device ID: the row's key
    id: str = ""
    note: str = ""              # the row's note (a timed loop block's spread and laps, a piece's OS block)


def read_block_lengths(path: Path = BLOCK_LENGTHS) -> dict[str, BlockLength]:
    """{user name: BlockLength} from block_lengths.csv (BLOCK_LENGTH_COLUMNS). Stops on a level and id empty or given
    twice, a name empty or given twice, a plan length that is not a number above zero, a source not in
    LENGTH_SOURCES, or a measured length given on a row whose source is not "timed" (or missing on one that is). The
    name is the row's label (user_name), which the build keeps the name store's (railroad_invariants checks it)."""
    out: dict[str, BlockLength] = {}
    keys: set[tuple[str, str]] = set()
    for line, r in read_rows(path, BLOCK_LENGTH_COLUMNS):
        where = _where(path, line)
        if r["level"] not in ("1", "2", "3") or not r["id"] or (r["level"], r["id"]) in keys:
            raise FactsError(f"{where}: level {r['level']!r} and id {r['id']!r}: a level 1 to 3 and a device ID, "
                             "once each")
        keys.add((r["level"], r["id"]))
        if not r["user_name"] or r["user_name"] in out:
            raise FactsError(f"{where}: user_name {r['user_name']!r} is empty or given twice")
        if r["source"] not in LENGTH_SOURCES:
            raise FactsError(f"{where}: source {r['source']!r} is not one of {', '.join(LENGTH_SOURCES)}")
        lengths = {}
        for col in ("plan_in", "measured_in"):
            if not r[col]:
                lengths[col] = None
                continue
            try:
                lengths[col] = float(r[col])
            except ValueError:
                raise FactsError(f"{where}: {col} {r[col]!r} is not a number") from None
            # a plan length may be 0 (a block between two turnouts that touch in the plan); a measured one may not
            if not (lengths[col] >= 0 if col == "plan_in" else lengths[col] > 0):
                raise FactsError(f"{where}: {col} {r[col]} is " + ("below zero" if col == "plan_in" else
                                                                   "not above zero"))
        if lengths["plan_in"] is None:
            raise FactsError(f"{where}: no plan_in (run tools/schematic/plan_lengths.py)")
        if (r["source"] == "timed") != (lengths["measured_in"] is not None):
            raise FactsError(f"{where}: source {r['source']} with measured_in {r['measured_in']!r}: a timed row "
                             "gives its measured length, any other none")
        out[r["user_name"]] = BlockLength(line, r["user_name"], r["occupancy_sensor"], lengths["plan_in"],
                                          lengths["measured_in"], r["source"], r["level"], r["id"], r["note"])
    return out


def plan_cm(lengths: dict[str, BlockLength]) -> dict[str, float]:
    """{block: plan length in cm}: the lengths the drawings and the signal rules measure by."""
    return {name: b.plan_in * 2.54 for name, b in lengths.items()}


@dataclass(frozen=True)
class Mast:
    """A mast's level, name and blocks, from schematic/masts.csv (hartlib.level_masts; protects ";" separated)."""
    line: int
    level: int
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
    """{label: Hand} of the main and upper rows of switches.csv (read_switch_rows) that give a hand; `source` is the
    row's hand_source (plan or owner)."""
    return {r.half: Hand(r.line, r.half, r.hand, r.hand_source) for r in rows
            if r.level in LEVEL_NUMBERS and r.hand}


def read_hands(path: Path) -> dict[str, Hand]:
    return hands(read_switch_rows(path))


# ---------------------------------------------------------------- the device map (build_device_map.py)

@dataclass(frozen=True)
class DeviceRow:
    """A main or upper row of the device master: a JMRI device (jmri_name, virtual) and its planned physical part
    (system_name, a draft). `role` is what the device is (devices.ROLES), given by the row or its writer; readers test
    it, not the name."""
    level: int
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
    line: int = 0

    def __post_init__(self) -> None:
        from . import devices
        if self.role not in devices.ROLES:      # no role is read off a name (hand-off row 8)
            raise FactsError(f"level {self.level} {self.layer} {self.user_name!r} has role {self.role!r}, not one of "
                             f"{', '.join(devices.ROLES)}")

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
        return cls(line=line, **{k: (int(v) if k == "level" else str(v)) for k, v in row.items() if k != "line"})


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


def device_list(cell: str) -> list[str]:
    """A DEVICE_LIST cell's items, in order."""
    return [x.strip() for x in (cell or "").split(DEVICE_LIST) if x.strip()]


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
    ID: det:<the block's id>, so a block the owner renamed keeps its detector; naming-layers step 13). Each row
    carries its `id`."""
    out = DeviceMap(path=path)
    seen: dict[tuple[str, str], int] = {}
    from . import devices
    master = devices.load(path)         # device_map_lines numbers its rows by their place here, from 2
    block_ids: dict[tuple[str, str], str] = {}
    for line, r in ((n, {c: v.strip() for c, v in row.items()}) for n, row in devices.device_map_lines(("2", "3"), path)):
        r["id"] = master[line - 2]["id"]
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
        row = DeviceRow(line=line, **{**r, "level": _level(r["level"], where)})
        out.rows.append(row)
        if row.layer == "block":
            out.blocks[row.user_name] = row
            block_ids[(r["level"], row.user_name)] = row.id
        elif row.layer == "occupancy":
            if not level_devices.is_block_sensor(row.jmri_name) or \
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
    name does not move it (naming-layers step 13); a row made without an ID by its user name ("Switch <n>",
    "DCC Switch <n>"). None when neither gives one."""
    m = re.fullmatch(r"(?:switch|dcc):(\d+)", row.id or "")
    if row.id:
        return m.group(1) if m else None
    m = re.fullmatch(r"(?:DCC )?Switch (\d+)", row.user_name)
    return m.group(1) if m else None


def check_virtual_names(rows: Iterable[DeviceRow], owner_named: Collection[tuple[int, str]] = ()) -> list[str]:
    """Problems with a device map's virtual names: every block has exactly one occupancy row (its detector by ID:
    det:<block id>; by the name rule on rows made without IDs), numbered by the block (hartlib.level_devices), every
    head's jmri_name comes from its user name, every turnout's from its switch number (turnout_switch: its ID's),
    and no two rows of a layer share a virtual name (but a turnout and its LCC alias, one JMRI turnout).
    `owner_named`: the (level, id) of the rows the owner names in devices_field.csv. A virtual name stays the
    generated one when the owner renames a device (naming-layers step 7), so such a block, its detector, a mast's
    heads and a head are held to their virtual name's form only (naming-layers step 13)."""
    rows = list(rows)
    owner_named = set(owner_named)

    def owned(r: DeviceRow) -> bool:            # the row, or the mast of a head, carries an owner's name
        return bool(r.id) and ((r.level, r.id) in owner_named or
                               (r.layer == "head" and (r.level, r.id.rsplit(":", 1)[0]) in owner_named))

    bad = []
    for layer in ("block", "occupancy"):            # the dicts and sets below would fold a second row away
        twice = sorted(n for n, k in Counter(r.user_name for r in rows if r.layer == layer).items() if k > 1)
        if twice:
            bad.append(f"{layer} rows given twice: {', '.join(twice)}")
    blocks = [r for r in rows if r.layer == "block"]
    occ = [r for r in rows if r.layer == "occupancy"]
    by_id = all(r.id for r in blocks + occ)
    # each block's detector row, keyed as the block is: by its ID, else by the name rule
    want = {(f"det:{b.id}" if by_id else level_devices.occupancy_user(b.user_name)): b for b in blocks}
    have = {(r.id if by_id else r.user_name): r for r in occ}
    if set(want) != set(have):
        bad.append(f"blocks and occupancy rows differ: {sorted(set(want) ^ set(have))}")
    for key, b in sorted(want.items()):
        r = have.get(key)
        if r is None:
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
        raise FactsError(f"{path}: cannot read it as a tables file ({exc})") from None

    def by_user(kind, beans):
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

