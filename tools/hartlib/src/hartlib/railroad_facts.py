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
from typing import Iterable

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
    switch_legs: Path
    devices: Path
    interlockings: Path
    local_switches: Path
    lcos_nodes: Path
    plan_overrides: Path
    block_lengths: Path
    staging_masts: Path
    hands: Path
    level_masts: Path
    tables: Path
    helix_tracks: Path

    @classmethod
    def under(cls, data: Path = paths.LAYOUT_DATA, tables_xml: Path | None = None) -> "Sources":
        """The files at their places under a data folder laid out as jmri/layouts/hart/data/ is."""
        s = data / "schematic"
        return cls(switches=data / "switches.csv", switch_legs=data / "switch_legs.csv",
                   devices=data / "devices.csv",
                   interlockings=s / "interlockings.csv",
                   local_switches=s / "local_switches_main_upper.csv", lcos_nodes=s / "lcos_nodes_main_upper.csv",
                   plan_overrides=s / "main_upper.plan_overrides.json", block_lengths=data / "block_lengths.csv",
                   staging_masts=s / "staging_masts.csv", hands=s / "hands.csv",
                   level_masts=s / level_masts.PATH.name,
                   tables=paths.TABLES_XML if tables_xml is None else tables_xml,
                   helix_tracks=s / "helix_tracks.csv")

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
    """A name-map row of devices.csv (its pnm_ columns). `current` == `proposed` is the live name; any other row is a
    historical alias (the master has none now)."""
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
    """The name-map rows of devices.csv (devices.name_map_lines), values stripped, unchecked beyond the master's own
    checks (read_name_map checks them)."""
    from . import devices
    return [(n, {c: r[c].strip() for c in NAME_COLUMNS + NAME_OPTIONAL}) for n, r in devices.name_map_lines(path)]


def read_name_map(path: Path, rows: list[tuple[int, dict[str, str]]] | None = None) -> NameMap:
    """The name map of devices.csv at `path` (or its `rows`, read_name_rows), every row checked. Stops on an unknown
    layer, an empty name, a DCC address that is not a number, or two rows for one (layer, current) name or one live
    (layer, name)."""
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
    the name map of devices.csv, its hardware, DCC address and control point."""
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
    """Switch number -> the live turnout row ("Switch <n>", current == proposed) of the name map, for the
    switches `numbers`. Only those rows are looked at for the answer; a name-map fault of another row (an unknown
    layer, a bad DCC address: read_name_map) is the railroad-facts check's to report. A bad row ANYWHERE in the master
    stops the load first (hartlib.devices.load checks the whole file, naming its line and row). Stops on a switch with
    two live rows."""
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

ALL_LEVELS = (1, 2, 3)                  # staging, main, upper: interlockings.csv holds every level


@dataclass(frozen=True)
class Interlocking:
    """An interlocking, the signal rule's control point (interlockings.csv, owner 2026-11-20): a group of switches
    whose home signals govern the routes between them. Staging's are named by place (Brick, Barn); main and upper's are
    "CP <lowest switch>" (owner, 2026-11-15), which are also their control points on the drawings and desks. `area`
    is the LCOS node area of a main or upper interlocking; staging leaves it blank, since staging's areas and desk
    groups are control_points_staging.csv's."""
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
            raise FactsError(f"{where} ({name}): a staging interlocking has no area (control_points_staging.csv "
                             "gives staging's)")
        if level != 1 and not r["area"]:
            raise FactsError(f"{where} ({name}): no area (the LCOS node area of a main or upper interlocking)")
        if level in levels:
            out.append(Interlocking(line, level, name, sw, r["area"], r["notes"]))
    return out


STATION_GROUP_COLUMNS = ("cp_id", "cp_name", "level", "switches", "notes", "code")


def station_group_rows(cps: Path, switch_legs: Path) -> list[dict[str, str]]:
    """Staging's control points (the station groups of control_points_staging.csv: the drawings' brackets and the
    CATS desk names) in the shape the older data/control_points.csv had, which this replaces (level-unification step
    8): cp_id the name in lower case with underscores, level, code and notes as given, and switches the OS block of
    each switch (a crossover by its halves, 7 as 7,7b and 23 as 23a,23b, from switch_legs.csv), "," between. Stops
    with FactsError, naming the file and line, on a row with no level or a switch with no OS block."""
    halves: dict[str, list[str]] = {}
    for line, r in read_rows(switch_legs, ("switch", "os_block")):
        m = re.fullmatch(r"OS Switch (\d+[a-z]?)", r["os_block"])
        if not m:
            raise FactsError(f"{_where(switch_legs, line)}: {r['os_block']!r} is not an OS Switch block")
        halves.setdefault(r["switch"], []).append(m.group(1))
    out = []
    for line, r in read_rows(cps, ("cp_name", "level", "switches", "code"), optional=("notes",)):
        where = _where(cps, line)
        if not r["level"]:
            raise FactsError(f"{where} ({r['cp_name']}): no level")
        sw = []
        for s in (x.strip() for x in re.split(r"[;,]", r["switches"]) if x.strip()):
            if s not in halves:
                raise FactsError(f"{where} ({r['cp_name']}): switch {s} has no OS block in {switch_legs.name}")
            sw += sorted(halves[s])
        out.append(dict(cp_id=re.sub(r"\W+", "_", r["cp_name"].lower()), cp_name=r["cp_name"], level=r["level"],
                        switches=",".join(sw), notes=r["notes"], code=r["code"]))
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
class HelixTrack:
    """A helix track (helix_tracks.csv): one JMRI block, `block`, from its staging switch up the helix to its main or
    upper switch (`level_switch`, the label the drawing prints: 131A), under the plan's name `helix` (owner,
    2026-11-20)."""
    line: int
    helix: str
    block: str
    staging_switch: str
    level_switch: str
    notes: str = ""


def read_helix_tracks(path: Path) -> dict[str, HelixTrack]:
    """{plan helix track name: HelixTrack}. Stops on an empty field, a block not named "Track ...", or a name or
    block given twice."""
    out: dict[str, HelixTrack] = {}
    blocks: dict[str, int] = {}
    for line, r in read_rows(path, ("helix", "block", "staging_switch", "level_switch"), optional=("notes",)):
        where = _where(path, line)
        if not all(r[k] for k in ("helix", "block", "staging_switch", "level_switch")) or \
                not r["block"].startswith("Track "):
            raise FactsError(f"{where}: helix, block (Track ...), staging_switch and level_switch are all needed")
        if r["helix"] in out or r["block"] in blocks:
            raise FactsError(f"{where}: helix {r['helix']!r} or block {r['block']!r} given twice")
        blocks[r["block"]] = line
        out[r["helix"]] = HelixTrack(line, r["helix"], r["block"], r["staging_switch"], r["level_switch"], r["notes"])
    if not out:
        raise FactsError(f"{path.name}: no helix tracks")
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

# block_lengths.csv: each staging block's 5.3c plan length (plan_in, written by tools/schematic/plan_lengths.py) and,
# for a timed block, its measured length (measured_in). `source` says which one JMRI's block length is: `timed`
# (measured_in) or `plan` (plan_in). The drawings and the signal rules use plan_in alone; the measured lengths serve
# speed profiling and JMRI's block lengths only (owner, 2026-11-20).
BLOCK_LENGTH_COLUMNS = ("user_name", "occupancy_sensor", "plan_in", "measured_in", "source", "note")
LENGTH_SOURCES = ("timed", "plan")


@dataclass(frozen=True)
class BlockLength:
    line: int
    user_name: str
    occupancy_sensor: str
    plan_in: float              # the AnyRail plan 5.3c length
    measured_in: float | None   # the timed length; None unless source is "timed"
    source: str                 # LENGTH_SOURCES: which length JMRI's block holds

    @property
    def jmri_in(self) -> float:
        """The block length JMRI holds: the measured length of a timed block, else the plan length."""
        return self.measured_in if self.source == "timed" else self.plan_in


def read_block_lengths(path: Path) -> dict[str, BlockLength]:
    """{user name: BlockLength} from block_lengths.csv (BLOCK_LENGTH_COLUMNS). Stops on a name empty or given twice, a
    plan length that is not a number above zero, a source not in LENGTH_SOURCES, or a measured length given on a row
    whose source is not "timed" (or missing on one that is)."""
    out: dict[str, BlockLength] = {}
    for line, r in read_rows(path, BLOCK_LENGTH_COLUMNS):
        where = _where(path, line)
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
            if not lengths[col] > 0:
                raise FactsError(f"{where}: {col} {r[col]} is not above zero")
        if lengths["plan_in"] is None:
            raise FactsError(f"{where}: no plan_in (run tools/schematic/plan_lengths.py)")
        if (r["source"] == "timed") != (lengths["measured_in"] is not None):
            raise FactsError(f"{where}: source {r['source']} with measured_in {r['measured_in']!r}: a timed row "
                             "gives its measured length, any other none")
        out[r["user_name"]] = BlockLength(line, r["user_name"], r["occupancy_sensor"], lengths["plan_in"],
                                          lengths["measured_in"], r["source"])
    return out


def plan_cm(lengths: dict[str, BlockLength]) -> dict[str, float]:
    """{block: plan length in cm}: the lengths the drawings and the signal rules measure by."""
    return {name: b.plan_in * 2.54 for name, b in lengths.items()}


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
    """A main or upper row of devices.csv: a JMRI device (jmri_name, virtual) and its planned physical part
    (system_name, a draft). `role` is what the device is (devices.ROLES); readers test it, not the name."""
    level: int
    layer: str
    user_name: str
    role: str = ""
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
    line: int = 0

    def __post_init__(self) -> None:
        if not self.role:           # a row built by hand is never roleless: the role its layer and names give
            from . import devices
            object.__setattr__(self, "role", devices.role_of(self.layer, self.user_name, self.system_name,
                                                             self.jmri_name))

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
        """The schematic tracks a block row holds ("Track e34", "Track e35")."""
        return frozenset(t.strip() for t in self.trial_name.split(",") if t.strip())

    @classmethod
    def from_dict(cls, row: dict, line: int = 0) -> "DeviceRow":
        """A row as build_device_map.py makes it (str or int level); __post_init__ gives it the role devices.role_of says."""
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
        return {r.user_name.removeprefix("Switch "): r for r in self.of("turnout") if r.role == "turnout"}

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
    """The main and upper rows of devices.csv at `path` (devices.device_map_lines). Stops on an unknown layer, a bad level, a (layer, user name) given twice (a turnout's LCC alias is its own
    row), a row whose fact columns do not hold (device_facts), an occupancy row whose jmri_name is not a virtual block
    sensor, whose planned detector is not M2S, or whose blocks are not the one block it is named for."""
    out = DeviceMap(path=path)
    seen: dict[tuple[str, str], int] = {}
    from . import devices
    for line, r in ((n, {c: v.strip() for c, v in row.items()}) for n, row in devices.device_map_lines(("2", "3"), path)):
        where = _where(path, line)
        if r["layer"] not in DEVICE_LAYERS or not r["user_name"]:
            raise FactsError(f"{where}: layer is one of {', '.join(DEVICE_LAYERS)} and user_name is given")
        bad = device_facts(r)
        if bad:
            raise FactsError(f"{where}: {r['layer']} {r['user_name']}: " + "; ".join(bad))
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
                    not (row.system_name == "" or row.system_name.startswith("M2S")) or row.detector == "wired":
                raise FactsError(f"{where}: occupancy {row.user_name} has no virtual {level_devices.SENSOR_PREFIX} "
                                 "jmri_name, or plans a detector that is not an M2S sensor, or calls it wired")
            if len(row.served) != 1 or level_devices.occupancy_user(row.served[0]) != row.user_name:
                raise FactsError(f"{where}: occupancy {row.user_name} serves {row.served}, not the one block it is "
                                 "named for")
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
    """A main or upper switch: in a control point (cp) or in none (local_switches_main_upper.csv)."""
    number: str
    level: int
    area: str
    cp: str = ""
    notes: str = ""


def join_main_upper(cps: Iterable[Interlocking], local: Iterable[LocalSwitch],
                    local_name: str = "local_switches_main_upper.csv") -> dict[str, MainUpperSwitch]:
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

