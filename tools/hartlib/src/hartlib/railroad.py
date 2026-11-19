"""The railroad's facts, loaded once into typed objects and held to the rules that join the files.

    from hartlib import railroad
    rr = railroad.Railroad()                      # every layer, from this checkout's files
    rr = railroad.Railroad(upto="inputs")         # a builder of a later layer reads only what comes before it
    rr.switches[9].legs[0].closed                 # "Track EH-2"
    rr.device_map.sensors["BS Switch 101"]        # "IS:HART:C3:B:OS101"
    problems = rr.check()                         # [Problem(invariant, message)], [] when the files agree

    python3 -m hartlib.railroad check [--upto LAYER]    # tools/check.sh runs it

Some of these files are written by the panel builders (tools/schematic/build_panels.sh runs them in order), so the
facts come in layers, in the order the pipeline makes them. A Railroad built `upto` a layer refuses (LayerError) to
read a later one: build_device_map.py loads upto="inputs", because it writes the device map, and so never reads a
stale copy of its own output. Each file is read the first time it is asked for, once.

    inputs      hand-kept: switches.csv and switch_legs.csv (staging switches, ADR-021), public_name_map.csv,
                schematic/control_points_main_upper.csv, local_switches_main_upper.csv, lcos_nodes_main_upper.csv,
                main_upper.plan_overrides.json (its edits; build_device_map.py rewrites only its control_points and
                stations keys), block_lengths.csv and schematic/staging_masts.csv (the staging masts in the
                device map's form, kept by hand; tools/schematic/staging_device_map.py --check)
    hands       schematic/hands.csv                       build_hands.py
    device_map  schematic/device_map_main_upper.csv       build_device_map.py
    masts       schematic/main_upper_masts.csv            build_main_upper_masts.py (hartlib.level_masts)
    tables      jmri/layouts/hart/output/tables.xml       build_layout_le.py --as-live, and PanelPro's Store

Every reader checks its own file's shape and stops with FactsError naming the file and line. The rules between files
are INVARIANTS, each run by Railroad.check once every layer it reads is loaded; a problem names the files and rows
that disagree. KNOWN lists problems already reported to the owner, each by its exact message: `check` prints them
and passes, any other problem fails, and a KNOWN message that no longer happens fails so the list stays honest.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from functools import cached_property
from pathlib import Path
from typing import Callable, Iterable

from . import level_devices, level_masts, paths, tables

LAYERS = ("inputs", "hands", "device_map", "masts", "tables")
WRITERS = {
    "hands": "tools/schematic/build_hands.py",
    "device_map": "tools/schematic/build_device_map.py",
    "masts": "tools/schematic/build_main_upper_masts.py",
    "tables": "tools/schematic/build_layout_le.py --as-live (or a PanelPro Store)",
}
LEVEL_NUMBERS = (2, 3)                  # main and upper: the levels of the schematic's main_upper files
YES = {"yes": True, "no": False}
HANDS = {"", "L", "R"}
NAME_LAYERS = ("turnout", "fb", "block", "occupancy", "mast", "head")
DEVICE_COLUMNS = ("level", "cp", "layer", "user_name", "system_name", "jmri_name", "node", "dcc", "comment",
                  "trial_name", "notes")
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
    switch_legs: Path
    name_map: Path
    level_control_points: Path
    local_switches: Path
    lcos_nodes: Path
    plan_overrides: Path
    block_lengths: Path
    staging_masts: Path
    hands: Path
    device_map: Path
    level_masts: Path
    tables: Path

    @classmethod
    def under(cls, data: Path = paths.LAYOUT_DATA, tables_xml: Path | None = None) -> "Sources":
        """The files at their places under a data folder laid out as jmri/layouts/hart/data/ is."""
        s = data / "schematic"
        return cls(switches=data / "switches.csv", switch_legs=data / "switch_legs.csv",
                   name_map=data / "public_name_map.csv",
                   level_control_points=s / "control_points_main_upper.csv",
                   local_switches=s / "local_switches_main_upper.csv", lcos_nodes=s / "lcos_nodes_main_upper.csv",
                   plan_overrides=s / "main_upper.plan_overrides.json", block_lengths=data / "block_lengths.csv",
                   staging_masts=s / "staging_masts.csv", hands=s / "hands.csv",
                   device_map=s / "device_map_main_upper.csv",
                   level_masts=s / level_masts.PATH.name,
                   tables=paths.TABLES_XML if tables_xml is None else tables_xml)

    def but(self, **changes: Path) -> "Sources":
        """These sources with some files swapped (a builder's patched path, a test's copy)."""
        return replace(self, **changes)


# ---------------------------------------------------------------- reading a CSV strictly

def _where(path: Path, line: int) -> str:
    return f"{path.name} line {line}"


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


# ---------------------------------------------------------------- inputs: the name map

@dataclass(frozen=True)
class NameRow:
    """A public_name_map.csv row. `current` == `proposed` is the live name; any other row is a historical alias."""
    line: int
    layer: str
    current: str
    proposed: str
    cp: str = ""
    hardware: str = ""
    dcc: str = ""
    comment: str = ""
    notes: str = ""

    @property
    def identity(self) -> bool:
        return self.current == self.proposed


@dataclass(frozen=True)
class NameMap:
    path: Path
    rows: tuple[NameRow, ...]

    @cached_property
    def live(self) -> dict[tuple[str, str], NameRow]:
        """(layer, name) -> its identity row (current == proposed)."""
        return {(r.layer, r.proposed): r for r in self.rows if r.identity}

    @property
    def aliases(self) -> list[NameRow]:
        return [r for r in self.rows if not r.identity]

    def names(self, layer: str) -> set[str]:
        return {name for lay, name in self.live if lay == layer}


NAME_COLUMNS = ("layer", "current", "proposed")
NAME_OPTIONAL = ("cp", "hardware", "dcc", "comment", "notes")


def read_name_rows(path: Path) -> list[tuple[int, dict[str, str]]]:
    """public_name_map.csv's rows as read, unchecked beyond its columns (read_name_map checks them)."""
    return read_rows(path, NAME_COLUMNS, optional=NAME_OPTIONAL)


def read_name_map(path: Path, rows: list[tuple[int, dict[str, str]]] | None = None) -> NameMap:
    """public_name_map.csv (or its `rows`, read_name_rows), every row checked. Stops on an unknown layer, an empty
    name, a DCC address that is not a number, or two rows for one (layer, current) name or one live (layer, name)."""
    rows_in, rows, seen = read_name_rows(path) if rows is None else rows, [], {}
    for line, r in rows_in:
        where = _where(path, line)
        if r["layer"] not in NAME_LAYERS:
            raise FactsError(f"{where}: layer is one of {', '.join(NAME_LAYERS)}, not {r['layer']!r}")
        if not r["current"] or not r["proposed"]:
            raise FactsError(f"{where}: current and proposed are both needed")
        if r["dcc"] and not r["dcc"].isdigit():
            raise FactsError(f"{where}: dcc is a number or blank, not {r['dcc']!r}")
        key = (r["layer"], r["current"])
        if key in seen:
            raise FactsError(f"{path.name} lines {seen[key]} and {line}: both are {r['layer']} {r['current']!r}")
        seen[key] = line
        rows.append(NameRow(line=line, **r))
    return NameMap(path, tuple(rows))


# ---------------------------------------------------------------- inputs: the staging switches (ADR-021)

@dataclass(frozen=True)
class Leg:
    os_block: str
    closed: str
    thrown: str


@dataclass(frozen=True)
class Switch:
    """A staging switch (switches.csv) with its legs (switch_legs.csv) and, from its live turnout row in
    public_name_map.csv, its hardware, DCC address and control point."""
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


def switch_turnouts(name_map: Path, rows: list[tuple[int, dict[str, str]]] | None = None,
                    numbers: Iterable[int] = ()) -> dict[int, dict[str, str]]:
    """Switch number -> the live turnout row ("Switch <n>", current == proposed) of public_name_map.csv, for the
    switches `numbers`. Only those rows are looked at: a bad row elsewhere in the map is the railroad-facts check's
    to report (read_name_map), not a reason to stop loading switches. Stops on a switch with two live rows."""
    want = {f"Switch {n}": n for n in numbers}
    out: dict[int, dict[str, str]] = {}
    lines: dict[int, int] = {}
    for line, r in read_name_rows(name_map) if rows is None else rows:
        n = want.get(r["current"])
        if n is None or r["layer"] != "turnout" or r["current"] != r["proposed"]:
            continue
        if n in out:
            raise FactsError(f"{name_map.name} lines {lines[n]} and {line}: both are the live turnout Switch {n}")
        out[n], lines[n] = r, line
    return out


def read_switches(switches: Path, switch_legs: Path, name_map: Path,
                  name_rows: list[tuple[int, dict[str, str]]] | None = None) -> dict[int, Switch]:
    """Switch number -> Switch, in switches.csv order; hardware, DCC address and control point from each switch's
    live turnout row of `name_map` (switch_turnouts; `name_rows` when the caller read it already). Line numbers in
    errors count the header as 1. Stops on a number, OS block or USS lever given twice, a switch with no legs or
    legs with no switch, or a bad hand."""
    legs: dict[int, list[Leg]] = {}
    os_line: dict[str, int] = {}
    for line, row in read_rows(switch_legs, ("switch", "os_block", "closed_leg", "thrown_leg")):
        os_name = row["os_block"]
        if os_name in os_line:
            raise FactsError(f"switch_legs.csv lines {os_line[os_name]} and {line}: "
                             f"both list {os_name}; an OS block belongs to one switch")
        os_line[os_name] = line
        legs.setdefault(_int(row["switch"], _where(switch_legs, line), "switch"), []).append(
            Leg(os_name, row["closed_leg"], row["thrown_leg"]))
    out: dict[int, Switch] = {}
    seen: dict[int, tuple[int, str]] = {}
    lever: dict[int, tuple[int, int]] = {}
    columns = ("level", "switch", "le_ident", "cats_inverted", "ctc_is", "ctc_signals")
    rows = read_rows(switches, columns, optional=("hand",))
    names = switch_turnouts(name_map, name_rows, [_int(r["switch"], _where(switches, line), "switch")
                                                   for line, r in rows])
    for line, row in rows:
        n = _int(row["switch"], _where(switches, line), "switch")
        where = f"switches.csv line {line} (Switch {n})"
        if n in seen:
            first, level = seen[n]
            raise FactsError(f"switches.csv lines {first} (level {level}) and {line} (level {row['level']}) "
                             f"both use Switch {n}; switch numbers are unique railroad-wide")
        seen[n] = (line, row["level"])
        if n not in legs:
            raise FactsError(f"{where}: no rows in switch_legs.csv")
        ctc_is = _int(row["ctc_is"], where, "ctc_is")
        if ctc_is in lever:
            first, other = lever[ctc_is]
            raise FactsError(f"switches.csv lines {first} (Switch {other}) and {line} (Switch {n}) "
                             f"both use USS lever IS{ctc_is}")
        lever[ctc_is] = (line, n)
        if row["hand"] not in HANDS:
            raise FactsError(f"{where}: hand is L, R or blank, got {row['hand']!r}")
        nm = names.get(n, {})
        out[n] = Switch(number=n, level=row["level"], le_ident=row["le_ident"],
                        cats_inverted=_yes(row["cats_inverted"], where), ctc_is=ctc_is,
                        ctc_signals=_yes(row["ctc_signals"], where), legs=tuple(legs.pop(n)), hand=row["hand"],
                        hardware=nm.get("hardware", ""), dcc=nm.get("dcc", ""), cp=nm.get("cp", ""))
    if legs:
        raise FactsError(f"switch_legs.csv: switches not in switches.csv: {sorted(legs)}")
    return out


# ---------------------------------------------------------------- inputs: main and upper control points and nodes

@dataclass(frozen=True)
class LevelControlPoint:
    """A main or upper control point (control_points_main_upper.csv): "CP <lowest switch>" (owner, 2026-11-15)."""
    line: int
    cp_id: str
    cp_name: str
    level: int
    switches: tuple[str, ...]
    area: str
    notes: str = ""


def read_level_control_points(path: Path) -> list[LevelControlPoint]:
    """The control points in file order. Stops on a bad level, a control point with no switches, a name or id
    given twice, or a switch in two control points."""
    out, seen, names = [], {}, {}
    for line, r in read_rows(path, ("cp_id", "cp_name", "level", "switches", "area"), optional=("notes",)):
        where = _where(path, line)
        sw = tuple(s.strip() for s in r["switches"].split(",") if s.strip())
        if not sw or not all(s.isdigit() for s in sw):
            raise FactsError(f"{where} ({r['cp_name']}): switches is a list of switch numbers, not {r['switches']!r}")
        for key in (r["cp_id"], r["cp_name"]):
            if not key or key in names:
                raise FactsError(f"{where}: cp_id and cp_name are given and unique, {key!r} is not")
            names[key] = line
        for s in sw:
            if s in seen:
                raise FactsError(f"{where}: switch {s} is in {seen[s]} and {r['cp_name']}")
            seen[s] = r["cp_name"]
        if not r["area"]:
            raise FactsError(f"{where} ({r['cp_name']}): no area")
        out.append(LevelControlPoint(line, r["cp_id"], r["cp_name"], _level(r["level"], where), sw, r["area"],
                                     r["notes"]))
    return out


@dataclass(frozen=True)
class LocalSwitch:
    """A main or upper switch in no control point (local_switches_main_upper.csv): yards and spurs."""
    line: int
    switch: str
    level: int
    area: str
    notes: str = ""


def read_local_switches(path: Path) -> list[LocalSwitch]:
    out, seen = [], {}
    for line, r in read_rows(path, ("switch", "level", "area"), optional=("notes",)):
        where = _where(path, line)
        if not r["switch"].isdigit() or not r["area"]:
            raise FactsError(f"{where}: switch is a number and area is given, not {r['switch']!r}, {r['area']!r}")
        if r["switch"] in seen:
            raise FactsError(f"{path.name} lines {seen[r['switch']]} and {line}: both are switch {r['switch']}")
        seen[r["switch"]] = line
        out.append(LocalSwitch(line, r["switch"], _level(r["level"], where), r["area"], r["notes"]))
    return out


@dataclass(frozen=True)
class LcosNode:
    """An LCOS radio address a level and area may use (lcos_nodes_main_upper.csv), in the order they are used."""
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
        out.append(LcosNode(line, _level(r["level"], where), r["area"], node, r["source"]))
    return out


# ---------------------------------------------------------------- inputs: the main and upper plan's overrides

@dataclass(frozen=True)
class PlanOverrides:
    """main_upper.plan_overrides.json. `data` is the whole file (build_device_map.py writes it back with its
    control_points and stations keys); `relabel` maps a plan switch label to the owner's switch number."""
    path: Path
    data: dict
    edits: tuple[dict, ...]
    relabel: dict[str, str]

    @property
    def helix(self) -> list:
        return list(self.data.get("helix", []))


def read_plan_overrides(path: Path) -> PlanOverrides:
    """Stops on a file that is not JSON, edits that are not a list of {op: ...}, or not exactly one relabel edit."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FactsError(f"{path.name}: not a readable JSON file ({exc})") from None
    edits = data.get("edits") if isinstance(data, dict) else None
    if not isinstance(edits, list) or not all(isinstance(e, dict) and isinstance(e.get("op"), str) for e in edits):
        raise FactsError(f"{path.name}: `edits` is a list of objects with an `op`")
    relabels = [e for e in edits if e["op"] == "relabel"]
    if len(relabels) != 1 or not isinstance(relabels[0].get("map"), dict):
        raise FactsError(f"{path.name}: {len(relabels)} relabel edits; it needs exactly one, with a `map`")
    return PlanOverrides(path, data, tuple(edits), dict(relabels[0]["map"]))


# ---------------------------------------------------------------- inputs: block lengths and staging masts

@dataclass(frozen=True)
class BlockLength:
    line: int
    user_name: str
    occupancy_sensor: str
    inches: float | None        # None: not measured
    flag: str = ""


def read_block_lengths(path: Path) -> dict[str, BlockLength]:
    out: dict[str, BlockLength] = {}
    for line, r in read_rows(path, ("user_name", "inches"), optional=("occupancy_sensor", "flag")):
        where = _where(path, line)
        if not r["user_name"] or r["user_name"] in out:
            raise FactsError(f"{where}: user_name {r['user_name']!r} is empty or given twice")
        try:
            inches = float(r["inches"]) if r["inches"] else None
        except ValueError:
            raise FactsError(f"{where}: inches {r['inches']!r} is not a number") from None
        out[r["user_name"]] = BlockLength(line, r["user_name"], r["occupancy_sensor"], inches, r["flag"])
    return out


@dataclass(frozen=True)
class StagingMast:
    """A staging mast's name and blocks, from schematic/staging_masts.csv (protects ";" separated)."""
    line: int
    mast: str
    facing: str
    protects: tuple[str, ...]


def read_staging_masts(path: Path) -> list[StagingMast]:
    out, seen = [], {}
    for line, r in read_rows(path, ("mast", "facing", "protects")):
        if not r["mast"] or r["mast"] in seen or not r["facing"]:
            raise FactsError(f"{_where(path, line)}: mast {r['mast']!r} is empty or given twice, or has no facing "
                             "block")
        seen[r["mast"]] = line
        out.append(StagingMast(line, r["mast"], r["facing"], tuple(b for b in r["protects"].split(";") if b)))
    return out


# ---------------------------------------------------------------- hands (build_hands.py)

@dataclass(frozen=True)
class Hand:
    line: int
    switch: str          # the schematic label: "107", or a crossover half "101A"
    hand: str            # L or R
    source: str = ""


HAND_LABEL = re.compile(r"\d+[AB]?")


def switch_number(label: str) -> str:
    """The switch number of a schematic label: "129A" -> "129", "223*" -> "223"."""
    return re.sub(r"[AB]$", "", (label or "").rstrip("*"))


def read_hands(path: Path) -> dict[str, Hand]:
    out: dict[str, Hand] = {}
    for line, r in read_rows(path, ("switch", "hand"), optional=("source",)):
        where = _where(path, line)
        if not HAND_LABEL.fullmatch(r["switch"]) or r["switch"] in out or r["hand"] not in ("L", "R"):
            raise FactsError(f"{where}: switch {r['switch']!r} is not a label given once (107, 101A), or hand "
                             f"{r['hand']!r} is not L or R")
        out[r["switch"]] = Hand(line, r["switch"], r["hand"], r["source"])
    return out


# ---------------------------------------------------------------- the device map (build_device_map.py)

@dataclass(frozen=True)
class DeviceRow:
    """A device_map_main_upper.csv row: a main or upper JMRI device (jmri_name, virtual) and its planned physical
    part (system_name, a draft)."""
    level: int
    layer: str
    user_name: str
    cp: str = ""
    system_name: str = ""
    jmri_name: str = ""
    node: str = ""
    dcc: str = ""
    comment: str = ""
    trial_name: str = ""
    notes: str = ""
    line: int = 0

    @property
    def trial(self) -> frozenset[str]:
        """The schematic tracks a block row holds ("Track e34", "Track e35")."""
        return frozenset(t.strip() for t in self.trial_name.split(",") if t.strip())

    @classmethod
    def from_dict(cls, row: dict, line: int = 0) -> "DeviceRow":
        """A row as build_device_map.py makes it (str or int level)."""
        return cls(line=line, **{k: (int(v) if k == "level" else str(v)) for k, v in row.items() if k != "line"})


DEVICE_LAYERS = NAME_LAYERS             # the device map's layers are the name map's


@dataclass
class DeviceMap:
    """The main and upper device map. `blocks`: block user name -> row; `sensors`: occupancy user name -> virtual
    sensor (jmri_name); `planned`: occupancy user name -> planned detector (M2S...), when the map has one."""
    rows: list[DeviceRow] = field(default_factory=list)
    blocks: dict[str, DeviceRow] = field(default_factory=dict)
    sensors: dict[str, str] = field(default_factory=dict)
    planned: dict[str, str] = field(default_factory=dict)
    path: Path | None = None

    def of(self, layer: str) -> list[DeviceRow]:
        return [r for r in self.rows if r.layer == layer]

    def by_user(self, layer: str) -> dict[str, DeviceRow]:
        return {r.user_name: r for r in self.of(layer)}

    @property
    def turnouts(self) -> dict[str, DeviceRow]:
        """Switch number -> its turnout row ("Switch <n>", not the LCC alias "DCC Switch <n>")."""
        return {r.user_name.removeprefix("Switch "): r for r in self.of("turnout")
                if r.user_name.startswith("Switch ")}

    @property
    def heads_by_system(self) -> dict[str, DeviceRow]:
        """Planned physical head (IH<packed>) -> its head row."""
        return {r.system_name: r for r in self.of("head")}


def read_device_map(path: Path) -> DeviceMap:
    """Stops on an unknown layer, a bad level, a (layer, user name) given twice (a turnout's LCC alias is its own
    row), an occupancy row whose jmri_name is not a virtual block sensor or whose planned detector is not M2S."""
    out = DeviceMap(path=path)
    seen: dict[tuple[str, str], int] = {}
    for line, r in read_rows(path, DEVICE_COLUMNS[:8], optional=DEVICE_COLUMNS[8:]):
        where = _where(path, line)
        if r["layer"] not in DEVICE_LAYERS or not r["user_name"]:
            raise FactsError(f"{where}: layer is one of {', '.join(DEVICE_LAYERS)} and user_name is given")
        key = (r["layer"], r["user_name"])
        if key in seen:
            raise FactsError(f"{path.name} lines {seen[key]} and {line}: both are {r['layer']} {r['user_name']}")
        seen[key] = line
        row = DeviceRow(line=line, **{**r, "level": _level(r["level"], where)})
        out.rows.append(row)
        if row.layer == "block":
            out.blocks[row.user_name] = row
        elif row.layer == "occupancy":
            if not level_devices.is_block_sensor(row.jmri_name) or \
                    not (row.system_name == "" or row.system_name.startswith("M2S")):
                raise FactsError(f"{where}: occupancy {row.user_name} has no virtual {level_devices.SENSOR_PREFIX} "
                                 "jmri_name, or plans a detector that is not an M2S sensor")
            out.sensors[row.user_name] = row.jmri_name
            if row.system_name:
                out.planned[row.user_name] = row.system_name
    return out


def check_virtual_names(rows: Iterable[DeviceRow]) -> list[str]:
    """Problems with a device map's virtual names: every block has exactly one occupancy row, named and numbered by
    the block (hartlib.level_devices), every head's jmri_name comes from its user name, every turnout's from its
    number, and no two rows of a layer share a virtual name (but a turnout and its LCC alias, one JMRI turnout)."""
    rows = list(rows)
    bad = []
    for layer in ("block", "occupancy"):            # the dicts and sets below would fold a second row away
        twice = sorted(n for n, k in Counter(r.user_name for r in rows if r.layer == layer).items() if k > 1)
        if twice:
            bad.append(f"{layer} rows given twice: {', '.join(twice)}")
    blocks = {r.user_name for r in rows if r.layer == "block"}
    occ = {r.user_name: r for r in rows if r.layer == "occupancy"}
    want = {level_devices.occupancy_user(b): b for b in blocks}
    if set(want) != set(occ):
        bad.append(f"blocks and occupancy rows differ: {sorted(set(want) ^ set(occ))}")
    for user, b in sorted(want.items()):
        r = occ.get(user)
        if r is None:
            continue
        try:
            sensor = level_devices.block_sensor(b)
        except ValueError as exc:
            bad.append(f"block {b}: {exc}")
            continue
        if r.jmri_name != sensor:
            bad.append(f"occupancy {user}: jmri_name {r.jmri_name!r}, not {sensor} (from block {b})")
    for r in rows:
        if r.layer == "head":
            try:
                if r.jmri_name != level_devices.head_name(r.user_name):
                    bad.append(f"head {r.user_name}: jmri_name {r.jmri_name!r}, not "
                               f"{level_devices.head_name(r.user_name)}")
            except ValueError as exc:
                bad.append(str(exc))
        elif r.layer == "turnout":
            m = re.fullmatch(r"(?:DCC )?Switch (\d+)", r.user_name)
            if not m or r.jmri_name != level_devices.TURNOUT_PREFIX + m.group(1):
                bad.append(f"turnout {r.user_name}: jmri_name {r.jmri_name!r}, not "
                           f"{level_devices.TURNOUT_PREFIX}<switch number>")
    for layer in ("occupancy", "head", "mast", "turnout"):
        names = [r.jmri_name for r in rows if r.layer == layer and not r.user_name.startswith("DCC ")]
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
    """The tables file's beans by user name; FactsError naming the file when it cannot be read or parsed."""
    try:
        root = tables.read(path)
    except (OSError, ET.ParseError) as exc:
        raise FactsError(f"{path}: cannot read it as a tables file ({exc})") from None

    def by_user(beans):
        return {tables.user_name(b): tables.system_name(b) for b in beans if tables.user_name(b)}
    return TablesNames(root, by_user(tables.turnouts(root)), by_user(tables.sensors(root)),
                       by_user(tables.masts(root)),
                       {tables.user_name(b) or tables.system_name(b) for b in tables.blocks(root)})


# ---------------------------------------------------------------- the railroad

@dataclass(frozen=True)
class MainUpperSwitch:
    """A main or upper switch: in a control point (cp) or in none (local_switches_main_upper.csv)."""
    number: str
    level: int
    area: str
    cp: str = ""
    notes: str = ""


def join_main_upper(cps: Iterable[LevelControlPoint], local: Iterable[LocalSwitch],
                    local_name: str = "local_switches_main_upper.csv") -> dict[str, MainUpperSwitch]:
    """Switch number -> MainUpperSwitch, from the control points and the local switches. Stops on a switch in
    both."""
    out = {s: MainUpperSwitch(s, cp.level, cp.area, cp.cp_name) for cp in cps for s in cp.switches}
    for r in local:
        if r.switch in out:
            raise FactsError(f"switch {r.switch} is in a control point and in {local_name} (line {r.line}, "
                             f"{out[r.switch].cp})")
        out[r.switch] = MainUpperSwitch(r.switch, r.level, r.area, notes=r.notes)
    return out


class Railroad:
    """The facts, each file read on first use, up to the layer `upto` (see the module text)."""

    def __init__(self, sources: Sources | None = None, upto: str = LAYERS[-1]):
        if upto not in LAYERS:
            raise ValueError(f"upto is one of {', '.join(LAYERS)}, not {upto!r}")
        self.sources = sources or Sources.under()
        self.upto = upto

    def _need(self, layer: str, what: str) -> None:
        if LAYERS.index(layer) > LAYERS.index(self.upto):
            raise LayerError(f"{what} is the {layer} layer, written by {WRITERS[layer]}; this Railroad reads up to "
                             f"the {self.upto} layer, so it may not read it (it would be a stale copy of a later step)")

    def has(self, layer: str) -> bool:
        return LAYERS.index(layer) <= LAYERS.index(self.upto)

    # inputs
    @cached_property
    def name_rows(self) -> list[tuple[int, dict[str, str]]]:
        """public_name_map.csv as read, once: name_map checks every row, switches look only at theirs."""
        return read_name_rows(self.sources.name_map)

    @cached_property
    def name_map(self) -> NameMap:
        return read_name_map(self.sources.name_map, self.name_rows)

    @cached_property
    def switches(self) -> dict[int, Switch]:
        return read_switches(self.sources.switches, self.sources.switch_legs, self.sources.name_map, self.name_rows)

    @cached_property
    def level_control_points(self) -> list[LevelControlPoint]:
        return read_level_control_points(self.sources.level_control_points)

    @cached_property
    def local_switches(self) -> list[LocalSwitch]:
        return read_local_switches(self.sources.local_switches)

    @cached_property
    def lcos_nodes(self) -> list[LcosNode]:
        return read_lcos_nodes(self.sources.lcos_nodes)

    @cached_property
    def plan_overrides(self) -> PlanOverrides:
        return read_plan_overrides(self.sources.plan_overrides)

    @cached_property
    def block_lengths(self) -> dict[str, BlockLength]:
        return read_block_lengths(self.sources.block_lengths)

    @cached_property
    def staging_masts(self) -> list[StagingMast]:
        return read_staging_masts(self.sources.staging_masts)

    @cached_property
    def main_upper_switches(self) -> dict[str, MainUpperSwitch]:
        """Switch number -> its control point or local row (join_main_upper)."""
        return join_main_upper(self.level_control_points, self.local_switches, self.sources.local_switches.name)

    # later layers
    @cached_property
    def hands(self) -> dict[str, Hand]:
        self._need("hands", self.sources.hands.name)
        return read_hands(self.sources.hands)

    @cached_property
    def device_map(self) -> DeviceMap:
        self._need("device_map", self.sources.device_map.name)
        return read_device_map(self.sources.device_map)

    @cached_property
    def level_masts(self) -> list[dict]:
        """main_upper_masts.csv rows (hartlib.level_masts.read: dicts with `heads` as (system, user) pairs)."""
        self._need("masts", self.sources.level_masts.name)
        try:
            return level_masts.read(self.sources.level_masts)
        except (OSError, ValueError) as exc:
            raise FactsError(str(exc)) from None

    @cached_property
    def tables(self) -> TablesNames:
        self._need("tables", self.sources.tables.name)
        return read_tables(self.sources.tables)

    def check(self) -> list["Problem"]:
        """Every invariant whose layers this Railroad reads, in INVARIANTS order."""
        out = []
        for inv in INVARIANTS:
            if self.has(inv.layer):
                out += [Problem(inv.name, m) for m in inv.run(self)]
        return out


# ---------------------------------------------------------------- invariants

@dataclass(frozen=True)
class Problem:
    invariant: str
    message: str

    def __str__(self) -> str:
        return f"{self.invariant}: {self.message}"


@dataclass(frozen=True)
class Invariant:
    name: str
    layer: str                                  # the latest layer it reads
    run: Callable[[Railroad], list[str]]
    doc: str


INVARIANTS: list[Invariant] = []


def invariant(name: str, layer: str):
    def wrap(fn):
        INVARIANTS.append(Invariant(name, layer, fn, (fn.__doc__ or "").strip()))
        return fn
    return wrap


@invariant("switch-numbers", "inputs")
def _switch_numbers(rr: Railroad) -> list[str]:
    """Switch plate numbers are unique railroad-wide: no main or upper switch (control_points_main_upper.csv,
    local_switches_main_upper.csv) reuses a staging number (switches.csv); each control point is named "CP <its
    lowest switch>"."""
    bad = []
    staging = {str(n) for n in rr.switches}
    for s, sw in sorted(rr.main_upper_switches.items(), key=lambda kv: natural(kv[0])):
        if s in staging:
            bad.append(f"Switch {s} is a staging switch (switches.csv) and a level {sw.level} switch")
    for cp in rr.level_control_points:
        want = f"CP {min(cp.switches, key=int)}"
        if cp.cp_name != want:
            bad.append(f"{rr.sources.level_control_points.name} line {cp.line}: {cp.cp_name} is named {want} by "
                       "its lowest switch")
    return bad


@invariant("lcos-nodes", "inputs")
def _lcos_nodes(rr: Railroad) -> list[str]:
    """Every level and area a main or upper switch is in has an LCOS node to put it on, and no main or upper node
    number is a staging node (the node of a staging turnout's or sensor's packed address, public_name_map.csv)."""
    pool = {(n.level, n.area) for n in rr.lcos_nodes}
    bad = [f"no node in {rr.sources.lcos_nodes.name} for level {lv} {area} (switches "
           f"{', '.join(sorted((s for s, sw in rr.main_upper_switches.items() if (sw.level, sw.area) == (lv, area)), key=natural))})"
           for lv, area in sorted({(sw.level, sw.area) for sw in rr.main_upper_switches.values()} - pool)]
    staging_nodes: dict[int, str] = {}
    for r in rr.name_map.live.values():
        m = re.fullmatch(r"(?:M2T|M2S|IH)(\d+)", r.hardware)
        if m and len(m.group(1)) >= 3:
            staging_nodes.setdefault(int(m.group(1)) // 100, f"{r.layer} {r.proposed} ({r.hardware})")
    for n in rr.lcos_nodes:
        if n.node in staging_nodes:
            bad.append(f"{rr.sources.lcos_nodes.name} line {n.line}: node {n.node} is staging's "
                       f"({staging_nodes[n.node]})")
    return bad


@invariant("name-map", "inputs")
def _name_map(rr: Railroad) -> list[str]:
    """public_name_map.csv resolves: every historical alias names a live row of its layer; every staging switch has
    a live turnout row with hardware and a DCC address; no two live turnouts share a DCC address; and no two live
    turnouts, feedback sensors, occupancy sensors or heads share hardware."""
    nm = rr.name_map
    bad = [f"{nm.path.name}: {r.layer} {r.current!r} is an alias of {r.proposed!r}, which has no "
           f"live row (current == proposed)" for r in nm.aliases if (r.layer, r.proposed) not in nm.live]
    for n, sw in rr.switches.items():
        if not sw.hardware or not sw.dcc:
            bad.append(f"Switch {n} (switches.csv): {nm.path.name} has no live turnout row with hardware and dcc")
    dcc: dict[str, NameRow] = {}
    hardware: dict[tuple[str, str], NameRow] = {}
    for r in nm.live.values():
        if r.layer == "turnout" and r.dcc:
            if r.dcc in dcc:
                bad.append(f"{nm.path.name} lines {dcc[r.dcc].line} and {r.line}: DCC {r.dcc} is "
                           f"{dcc[r.dcc].proposed} and {r.proposed}")
            dcc.setdefault(r.dcc, r)
        if r.layer in UNIQUE_HARDWARE and r.hardware:
            key = (r.layer, r.hardware)
            if key in hardware:
                bad.append(f"{nm.path.name} lines {hardware[key].line} and {r.line}: {r.layer}s "
                           f"{hardware[key].proposed} and {r.proposed} are both {r.hardware}")
            hardware.setdefault(key, r)
    return bad


@invariant("staging-blocks", "inputs")
def _staging_blocks(rr: Railroad) -> list[str]:
    """Every block a staging switch leg (switch_legs.csv), a staging mast (staging_masts.csv) or a measured
    length (block_lengths.csv) names is a live block of public_name_map.csv, and every staging mast a live mast."""
    blocks, masts = rr.name_map.names("block"), rr.name_map.names("mast")
    bad = []
    for sw in rr.switches.values():
        for leg in sw.legs:
            for what, b in (("OS block", leg.os_block), ("closed leg", leg.closed), ("thrown leg", leg.thrown)):
                if b not in blocks:
                    bad.append(f"Switch {sw.number} (switch_legs.csv): {what} {b} is no live block of the name map")
    for m in rr.staging_masts:
        where = f"{rr.sources.staging_masts.name}: {m.mast}"
        if m.mast not in masts:
            bad.append(f"{where}: no live mast {m.mast} in the name map")
        bad += [f"{where}: block {b} is no live block of the name map" for b in (m.facing, *m.protects)
                if b not in blocks]
    bad += [f"{rr.sources.block_lengths.name}: {name} is no live block of the name map"
            for name in rr.block_lengths if name not in blocks]
    return bad


@invariant("plan-overrides", "inputs")
def _plan_overrides(rr: Railroad) -> list[str]:
    """main_upper.plan_overrides.json renames plan switches to main and upper switches only, every main and upper
    switch is named by it, and each `move` edit names a plan switch the relabel renames."""
    po, mu = rr.plan_overrides, rr.main_upper_switches
    targets = {switch_number(v): k for k, v in po.relabel.items()}
    bad = [f"{po.path.name}: relabel {old!r} -> {new!r}: {switch_number(new)} is no main or upper switch"
           for old, new in po.relabel.items() if switch_number(new) not in mu]
    bad += [f"Switch {s} ({mu[s].cp or 'local'}): no plan switch is relabelled to it in {po.path.name}"
            for s in sorted(set(mu) - set(targets), key=natural)]
    bad += [f"{po.path.name}: move edit names {e.get('switch')!r}, which the relabel does not rename"
            for e in po.edits if e["op"] == "move" and e.get("switch") not in po.relabel]
    return bad


@invariant("hands", "hands")
def _hands(rr: Railroad) -> list[str]:
    """Each hands.csv label is a main or upper switch the plan's relabel names (a crossover half by its label)."""
    targets = set(rr.plan_overrides.relabel.values())
    return [f"{rr.sources.hands.name} line {h.line}: {label} is no label the plan's relabel gives"
            for label, h in rr.hands.items() if label not in targets and label + "*" not in targets] + \
           [f"{rr.sources.hands.name} line {h.line}: {label} is no main or upper switch"
            for label, h in rr.hands.items() if switch_number(label) not in rr.main_upper_switches]


@invariant("device-map", "device_map")
def _device_map(rr: Railroad) -> list[str]:
    """The device map's turnouts are exactly the main and upper switches, each with its LCC alias "DCC Switch <n>",
    on its own level and control point; its virtual names follow hartlib.level_devices (check_virtual_names); its
    nodes are the level's LCOS nodes; its DCC addresses and planned hardware are no staging device's."""
    dm, mu, name = rr.device_map, rr.main_upper_switches, rr.sources.device_map.name
    bad = list(check_virtual_names(dm.rows))
    turnouts = dm.turnouts
    aliases = {r.user_name.removeprefix("DCC Switch "): r for r in dm.of("turnout")
               if r.user_name.startswith("DCC Switch ")}
    for s in sorted(set(mu) | set(turnouts), key=natural):
        r, sw = turnouts.get(s), mu.get(s)
        if r is None:
            bad.append(f"Switch {s} ({sw.cp or 'local'}, level {sw.level}): no turnout row in {name}")
            continue
        if sw is None:
            bad.append(f"{name} line {r.line}: Switch {s} is in no control point and not in "
                       f"{rr.sources.local_switches.name}")
            continue
        if (r.level, r.cp) != (sw.level, sw.cp):
            bad.append(f"{name} line {r.line}: Switch {s} is level {r.level} {r.cp or 'local'}, the control points "
                       f"say level {sw.level} {sw.cp or 'local'}")
        a = aliases.get(s)
        if a is None or (a.jmri_name, a.dcc, a.system_name) != (r.jmri_name, r.dcc, f"MTT{r.dcc}"):
            bad.append(f"{name} line {r.line}: Switch {s} has no LCC alias DCC Switch {s} on its turnout and DCC "
                       "address")
    nodes = {n.node: n for n in rr.lcos_nodes}
    for r in dm.rows:
        if r.node and (not r.node.isdigit() or int(r.node) not in nodes or nodes[int(r.node)].level != r.level):
            bad.append(f"{name} line {r.line}: {r.layer} {r.user_name} is on node {r.node}, no level {r.level} node "
                       f"of {rr.sources.lcos_nodes.name}")
    staging_dcc = {r.dcc: r for r in rr.name_map.live.values() if r.layer == "turnout" and r.dcc}
    staging_hw = {r.hardware: r for r in rr.name_map.live.values() if r.layer in UNIQUE_HARDWARE and r.hardware}
    seen_hw: dict[str, DeviceRow] = {}
    for r in dm.rows:
        if r.layer == "turnout" and not r.user_name.startswith("DCC ") and r.dcc in staging_dcc:
            bad.append(f"{name} line {r.line}: {r.user_name} has DCC {r.dcc}, staging's {staging_dcc[r.dcc].proposed}")
        if r.layer in UNIQUE_HARDWARE and r.system_name:
            if r.system_name in staging_hw:
                bad.append(f"{name} line {r.line}: {r.user_name} plans {r.system_name}, staging's "
                           f"{staging_hw[r.system_name].proposed}")
            if r.system_name in seen_hw:
                bad.append(f"{name} lines {seen_hw[r.system_name].line} and {r.line}: "
                           f"{seen_hw[r.system_name].user_name} and {r.user_name} both plan {r.system_name}")
            seen_hw.setdefault(r.system_name, r)
    return bad


@invariant("name-clash", "device_map")
def _name_clash(rr: Railroad) -> list[str]:
    """No public_name_map.csv row, live or historical alias, uses a name the device map gives a main or upper
    device of the same layer: a rename pass that maps the alias would rename the main or upper device."""
    dm = {(r.layer, r.user_name): r for r in rr.device_map.rows}
    out = []
    for r in rr.name_map.rows:
        hit = dm.get((r.layer, r.current))
        if hit is not None:
            what = "live" if r.identity else f"an alias of {r.proposed}"
            out.append(f"{rr.name_map.path.name}: {r.layer} {r.current} is {what} there and level "
                       f"{hit.level} {r.layer} {hit.user_name} in {rr.sources.device_map.name}")
    return out


@invariant("level-masts", "masts")
def _level_masts(rr: Railroad) -> list[str]:
    """Each main_upper_masts.csv mast is a device map mast of the same control point, on its virtual and planned
    names; its switch is in that control point (an APB intermediate has no switch; a spur's exit dwarf at a local
    switch has no control point, ADR-024); its facing and protected blocks are device map blocks; and every device
    map mast has a row."""
    dm, name = rr.device_map, rr.sources.level_masts.name
    masts = dm.by_user("mast")
    cps = {cp.cp_name: cp for cp in rr.level_control_points}
    bad, seen = [], set()
    for r in rr.level_masts:
        seen.add(r["mast"])
        m = masts.get(r["mast"])
        if m is None:
            bad.append(f"{name}: {r['mast']} is no mast of the device map")
            continue
        if (r["cp"], r["system_name"], r["device_system_name"]) != (m.cp, m.jmri_name, m.system_name):
            bad.append(f"{name}: {r['mast']} is {r['cp']} {r['system_name']} on {r['device_system_name']}; the "
                       f"device map says {m.cp} {m.jmri_name} on {m.system_name}")
        if not r["switch"]:
            if r["cp"] not in cps:          # an APB intermediate: between two track blocks, in its track's CP
                bad.append(f"{name}: {r['mast']} (an intermediate) names control point {r['cp']!r}, which is none")
        elif not r["cp"]:
            if r["switch"] not in rr.main_upper_switches:
                bad.append(f"{name}: {r['mast']} names Switch {r['switch']}, which is on neither level")
            elif rr.main_upper_switches[r["switch"]].cp:
                bad.append(f"{name}: {r['mast']} has no control point, but Switch {r['switch']} is in "
                           f"{rr.main_upper_switches[r['switch']].cp}")
        elif r["switch"] not in (cps[r["cp"]].switches if r["cp"] in cps else ()):
            bad.append(f"{name}: {r['mast']} protects Switch {r['switch']}, which is not in {r['cp']}")
        bad += [f"{name}: {r['mast']} {what} {b}, which is no device map block"
                for what, b in (("faces", r["facing"]), ("protects", r["protects"])) if b not in dm.blocks]
    bad += [f"{name}: device map mast {m} has no row" for m in sorted(set(masts) - seen, key=natural)]
    return bad


@invariant("tables", "tables")
def _tables(rr: Railroad) -> list[str]:
    """tables.xml holds the facts' devices: every staging switch's turnout and block of its legs, every staging
    mast; every main and upper turnout, occupancy sensor and control-point mast on its virtual name."""
    t, bad = rr.tables, []
    for sw in rr.switches.values():
        if sw.turnout not in t.turnouts:
            bad.append(f"Switch {sw.number} (switches.csv): no turnout {sw.turnout} in tables.xml")
        bad += [f"Switch {sw.number} (switch_legs.csv): no block {b} in tables.xml"
                for leg in sw.legs for b in (leg.os_block, leg.closed, leg.thrown) if b not in t.blocks]
    bad += [f"{rr.sources.staging_masts.name}: no mast {m.mast} in tables.xml"
            for m in rr.staging_masts if m.mast not in t.masts]
    dm = rr.device_map
    for s, r in sorted(dm.turnouts.items(), key=lambda kv: natural(kv[0])):
        if t.turnouts.get(r.user_name) != r.jmri_name:
            bad.append(f"{r.user_name}: tables.xml has {t.turnouts.get(r.user_name) or 'no such turnout'}, the "
                       f"device map says {r.jmri_name}")
    for user, sensor in sorted(dm.sensors.items(), key=lambda kv: natural(kv[0])):
        if t.sensors.get(user) != sensor:
            bad.append(f"{user}: tables.xml has {t.sensors.get(user) or 'no such sensor'}, the device map says "
                       f"{sensor}")
    for r in rr.level_masts:
        if t.masts.get(r["mast"]) != r["system_name"]:
            bad.append(f"{r['mast']}: tables.xml has {t.masts.get(r['mast']) or 'no such mast'}, "
                       f"{rr.sources.level_masts.name} says {r['system_name']}")
    return bad


# ---------------------------------------------------------------- the check command

# Problems already reported to the owner, each by its exact message (str(Problem)) -> why it is left. Empty since
# 2026-11-17: the owner decided the throat blocks (live rows added) and the BS unused aliases (they point at the
# free detectors' live names). Add an entry only for a problem the owner has been told about and chose to leave.
KNOWN: dict[str, str] = {}


def run_check(rr: Railroad, known: dict[str, str] = KNOWN) -> tuple[list[str], list[str]]:
    """(failures, known lines): every problem not in `known`, and every `known` message of an invariant that ran
    which no longer happens."""
    seen = [str(p) for p in rr.check()]
    ran = {inv.name for inv in INVARIANTS if rr.has(inv.layer)}
    fails = [m for m in seen if m not in known]
    fails += [f"KNOWN entry no longer happens; remove it from KNOWN: {m}" for m in known
              if m not in seen and m.split(":", 1)[0] in ran]
    hits = Counter(known[m] for m in seen if m in known)
    return fails, [f"{reason} ({n} problem(s))" for reason, n in hits.items()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m hartlib.railroad", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="hold the fact files to every invariant (tools/check.sh)")
    c.add_argument("--upto", choices=LAYERS, default=LAYERS[-1], help="the last layer to read (default: all)")
    sub.add_parser("invariants", help="list the invariants and the layer each reads")
    args = ap.parse_args(argv)
    if args.cmd == "invariants":
        for inv in INVARIANTS:
            print(f"{inv.name} ({inv.layer}): {' '.join(inv.doc.split())}")
        return 0
    rr = Railroad(upto=args.upto)
    try:
        fails, known = run_check(rr)
    except FactsError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    for line in known:
        print(f"KNOWN {line}")
    for line in fails:
        print(f"FAIL {line}", file=sys.stderr)
    counts = defaultdict(int)
    for inv in INVARIANTS:
        counts["run" if rr.has(inv.layer) else "skipped"] += 1
    print(f"railroad facts: {counts['run']} invariants up to {args.upto}, {len(fails)} failure(s), "
          f"{len(known)} known")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
