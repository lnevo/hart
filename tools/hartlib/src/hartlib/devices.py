"""devices.csv: the one device master for all three levels.

jmri/layouts/hart/data/devices.csv holds one row per railroad device (ADR-029). Staging, main and upper are one
structure; a level differs only in column values. devices.columns.csv describes every column (column, description),
and a test holds the two files to each other both ways. Every reader gets its rows from the master (load,
device_map_lines below). The two device maps and the public name map that once sat beside it are gone (R9e,
ADR-029), and so are the six pnm_ columns that kept the name map's copy: their facts are in the master's own columns.

The master's values.
- level 1 staging, 2 main, 3 upper. layer: turnout, fb, block, occupancy, mast, head, sensor.
- assignment: field (the physical device is in JMRI: jmri_name is system_name), virtual (an internal stand-in; the
  system_name, if any, is the planned device), none (no JMRI name from this row), spare (a detector with no block).
- role: what the device is (ROLES). Readers test it, never a name prefix.
- written_by: the script that writes the row, one of WRITERS (the one place a later merge of builders changes);
  empty is hand-kept. A writer replaces only the rows that carry its name (replace_rows), and stops on a key
  another writer or the owner holds.

Row order is level, layer (LAYERS), then who holds the row (hand-kept first, then WRITERS order), then the order the
holder gave, so a rebuild changes only its own rows and `check` can hold the file to it. Block and mast numbers
that le_tables.block_sort and block_numbering.csv set are not touched here.

    python3 -m hartlib.devices check         # the master and its dictionary are valid

Every failure is a DevicesError (a FactsError) naming the file and row.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping

from . import names, paths
from .railroad_facts import DEVICE_COLUMNS, DEVICE_LIST, FactsError

LEVELS = ("1", "2", "3")
LAYERS = ("turnout", "fb", "block", "occupancy", "mast", "head", "sensor")   # also the order within a level
ASSIGNMENTS = ("field", "virtual", "none", "spare")
# the roles of a line block (and its occupancy sensor): a block between switches, whose cp is a list of the places it
# joins (build_device_map.line_cp); every other device sits in one control point at most
LINE_ROLES = ("track", "helix", "part", "loop_half", "spur")
# the roles of a block through a switch's points (and its occupancy sensor): an OS block, or a corner of a double
# crossover; readers test these (is_os, Index.is_os), never an "OS Switch " prefix
OS_ROLES = ("os", "xover_corner")
ROLES = ("turnout", "lcc_alias", "fb", "os", "xover_corner", "track", "spur", "loop_half", "helix",
         "home", "intermediate", "hidden", "head", "spare", "panel_status", "part")
# The scripts that write rows (the one list: a merge of builders changes only this). Order is the order of rows
# within a (level, layer) after the hand-kept ones.
WRITERS = ("build_staging_masts.py", "build_device_map.py", "build_main_upper_masts.py", "panel_items.json")
# roles the two device maps leave out: a spare detector, a panel status bean, and a part (a block row with part_of: a
# piece of track inside another block: a JMRI block on its block's occupancy sensor, built by its level's builder, with
# no occupancy row or detector of its own)
OUT_OF_MAPS = ("spare", "panel_status", "part")
SOURCE_PREFIXES = ("IT:HART:", "IS:HART:", "IH:HART:", "IB:HART:")

COLUMNS = ("level", "cp", "layer", "role", "user_name", "assignment", "system_name", "jmri_name", "node", "dcc",
           "wiring", "jmri_comment", "trial_name", "notes", "blocks", "detector", "stop", "layout_block",
           "part_of", "switch", "facing", "protects", "dir", "written_by", "description", "jmri_bean")
# staging: its plant is the field, so a rewrite of its field devices' rows carries their field facts over from the
# rows they replace, and a writer may not drop one without saying so (carries_field_facts, replace_rows' drops)
FIELD_LEVEL = "1"
LIST = DEVICE_LIST              # the separator of a list column (blocks, protects, a line block's cp)
# the columns an old-form device-map row shares with the master; its comment is built, the rest of the master is left out
_SHARED = tuple(c for c in DEVICE_COLUMNS if c not in ("comment",))

_NODE_TEXT = re.compile(r"Node: \d+")
_WIRED_HEAD = re.compile(r"\(IH\d+\)")


class DevicesError(FactsError):
    """The master or its dictionary cannot stand as it is, or a write would break it."""


@dataclass(frozen=True)
class Files:
    """The master and its dictionary; tests point them at a copy."""
    master: Path
    dictionary: Path

    @staticmethod
    def under(data: Path) -> "Files":
        """The files as they sit under a data folder (jmri/layouts/hart/data): one root, so a test or a script that
        points it elsewhere moves every file together and cannot write the repo's."""
        return Files(data / "devices.csv", data / "devices.columns.csv")

    @staticmethod
    def here() -> "Files":
        return Files.under(paths.LAYOUT_DATA)

    def but(self, **changes) -> "Files":
        return replace(self, **changes)


# ---------------------------------------------------------------- reading

@lru_cache(maxsize=8)
def _read(name: str, data: bytes) -> tuple[Mapping[str, str], ...]:
    """The rows of a master's bytes. Cached on the bytes themselves, so a write of the same size in the same clock
    tick can never return stale rows."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DevicesError(f"{name}: not UTF-8 text ({exc.reason} at byte {exc.start})") from None
    reader = csv.reader(io.StringIO(text, newline=""))
    header = next(reader, None)
    if header is None or tuple(header) != COLUMNS:
        raise DevicesError(f"{name}: the header is not the master's columns ({', '.join(COLUMNS)}); got {header}")
    rows = []
    for line, fields in enumerate(reader, 2):
        if len(fields) != len(COLUMNS):
            raise DevicesError(f"{name} line {line}: {len(fields)} fields, expected {len(COLUMNS)}")
        rows.append(MappingProxyType(dict(zip(COLUMNS, fields))))
    return tuple(rows)


def _master_path(source: "Files | Path | str | None") -> Path:
    if source is None:
        return Files.here().master
    return source.master if isinstance(source, Files) else Path(source)


def load(files: "Files | Path | str | None" = None) -> tuple[Mapping[str, str], ...]:
    """The master's rows (read-only mappings), checked (check_rows). Read once per file state: the parse is cached on
    the file's bytes, so every reader of one run shares it and a changed file is always read again. `files` is the
    Files of a copy, or the master's own path. A bad row ANYWHERE stops the load (check_rows names its line and row),
    since the master is one validated file; there is no way round it. DevicesError on any problem."""
    path = _master_path(files)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise DevicesError(f"{path}: cannot read it ({exc.strerror})") from None
    rows = _read(path.name, data)
    check_rows(rows, path.name)
    return rows


def device_map_lines(levels: tuple[str, ...], source: "Files | Path | str | None" = None
                     ) -> list[tuple[int, dict[str, str]]]:
    """(line of the master, device-map row) of each row of `levels` outside OUT_OF_MAPS, in master order: the rows the
    old device map of those levels held, in its form plus `role`. The one way a reader gets them."""
    return [(n, {**device_map_row(r), "role": r["role"]}) for n, r in enumerate(load(source), 2)
            if r["level"] in levels and r["role"] not in OUT_OF_MAPS]


def part_lines(levels: tuple[str, ...], source: "Files | Path | str | None" = None
               ) -> list[tuple[int, dict[str, str]]]:
    """(line of the master, row) of each part of `levels` (role part: a piece of track inside another block, part_of
    naming it), which the device maps leave out (OUT_OF_MAPS), in master order."""
    return [(n, dict(r)) for n, r in enumerate(load(source), 2) if r["level"] in levels and r["role"] == "part"]


# ---------------------------------------------------------------- a device's kind, from its row

def row_role(row: Mapping[str, str], where: str = "devices.csv") -> str:
    """The role column of `row` (ROLES). DevicesError naming `where` (the file and line) and the row when the row has
    no role column or an empty one: a reader asks the row what a device is, never its name (hand-off row 8)."""
    role = row.get("role", "")
    if not role:
        raise DevicesError(f"{where}: {row.get('layer', '?')} {row.get('user_name', '?')!r} has no role "
                           f"(one of {', '.join(ROLES)})")
    return role


def is_os(row: Mapping[str, str], where: str = "devices.csv") -> bool:
    """Whether a block or occupancy row is the block through a switch's points (OS_ROLES), by its role."""
    return row_role(row, where) in OS_ROLES


@dataclass(frozen=True)
class Index:
    """The master's rows by (layer, user name), each with its line: the one lookup for a reader that holds a device's
    name and needs its row's facts (role, level, layer). Built by index()."""
    path: Path
    by_key: Mapping[tuple[str, str], tuple[tuple[int, Mapping[str, str]], ...]]
    lines: tuple[tuple[int, Mapping[str, str]], ...]

    def rows(self, layer: str, name: str) -> tuple[tuple[int, Mapping[str, str]], ...]:
        """(line, row) of every row of `layer` named `name`: one per level the device is on (a helix block is a row
        on staging and one on its main or upper level). DevicesError when there is none."""
        got = self.by_key.get((layer, name))
        if not got:
            raise DevicesError(f"{self.path.name}: no {layer} row {name!r}")
        return got

    def role(self, layer: str, name: str) -> str:
        """The role of the `layer` device `name`. DevicesError when it has no row, a row with no role, or rows on two
        levels that give it different roles (naming their lines)."""
        got = self.rows(layer, name)
        roles = {row_role(r, f"{self.path.name} line {n}") for n, r in got}
        if len(roles) != 1:
            raise DevicesError(f"{self.path.name} lines {', '.join(str(n) for n, _ in got)}: {layer} {name!r} has "
                               f"roles {', '.join(sorted(roles))}; its rows give it one")
        return roles.pop()

    def is_os(self, block: str) -> bool:
        """Whether block `block` runs through a switch's points (OS_ROLES), by its role."""
        return self.role("block", block) in OS_ROLES

    def has(self, layer: str, name: str) -> bool:
        """Whether the master holds a `layer` row named `name` (placed or not)."""
        return (layer, name) in self.by_key

    def is_unplaced(self, layer: str, name: str) -> bool:
        """Whether every `layer` row named `name` is a device not on the layout yet (is_unplaced: no level, no role,
        kept by its jmri_bean). DevicesError when there is no such row."""
        return all(is_unplaced(r) for _n, r in self.rows(layer, name))

    def where(self, row: Mapping[str, str]) -> str:
        """"devices.csv line N" for the master's row with `row`'s level, layer and user name, for a message; the file's
        name alone when the master has no such row (a caller's own row, as in a test)."""
        for n, r in self.by_key.get((row.get("layer", ""), row.get("user_name", "")), ()):
            if r["level"] == row.get("level"):
                return f"{self.path.name} line {n}"
        return self.path.name

    def names(self, layer: str, roles: Iterable[str] | None = None, levels: Iterable[str] | None = None
              ) -> list[str]:
        """The user names of the `layer` rows (of `roles` and `levels` when given), in master order, each once. With
        `roles`, a device not on the layout yet (is_unplaced: it has no role) is left out."""
        roles = None if roles is None else frozenset(roles)
        levels = None if levels is None else frozenset(levels)
        out: dict[str, None] = {}
        for n, r in self.lines:
            if r["layer"] != layer or (levels is not None and r["level"] not in levels):
                continue
            if roles is not None and (is_unplaced(r) or row_role(r, f"{self.path.name} line {n}") not in roles):
                continue
            out.setdefault(r["user_name"], None)
        return list(out)


_INDEXES: dict[int, tuple[tuple[Mapping[str, str], ...], Index]] = {}


def index(files: "Files | Path | str | None" = None) -> Index:
    """The Index of the master (or of `files`, a copy), built once per file state: load() returns the same rows for
    the same bytes, and the index is kept with them."""
    path = _master_path(files)
    rows = load(files)
    kept = _INDEXES.get(id(rows))
    if kept is not None and kept[0] is rows and kept[1].path == path:
        return kept[1]
    lines = tuple(enumerate(rows, 2))
    by_key: dict[tuple[str, str], list[tuple[int, Mapping[str, str]]]] = {}
    for n, r in lines:
        by_key.setdefault((r["layer"], r["user_name"]), []).append((n, r))
    out = Index(path, MappingProxyType({k: tuple(v) for k, v in by_key.items()}), lines)
    _INDEXES[id(rows)] = (rows, out)
    while len(_INDEXES) > 8:                    # as many file states as _read keeps
        del _INDEXES[next(iter(_INDEXES))]
    return out


def read_dictionary(path: Path) -> dict[str, str]:
    """{column: description} of devices.columns.csv; DevicesError unless it is exactly the columns `column,description`
    with every master column once, and each described."""
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
    except OSError as exc:
        raise DevicesError(f"{path}: cannot read it ({exc.strerror})") from None
    if not rows or rows[0] != ["column", "description"]:
        raise DevicesError(f"{path.name}: the header is column,description")
    out, bad = {}, []
    for line, r in enumerate(rows[1:], 2):
        if len(r) != 2:
            bad.append(f"line {line}: {len(r)} fields, expected 2")
        elif r[0] in out:
            bad.append(f"line {line}: {r[0]} is described twice")
        elif not r[1].strip():
            bad.append(f"line {line}: {r[0]} has no description")
        else:
            out[r[0]] = r[1]
    bad += [f"{c} is a master column with no description" for c in COLUMNS if c not in out]
    bad += [f"{c} is described but is no master column" for c in out if c not in COLUMNS]
    if bad:
        raise DevicesError(f"{path.name}: " + "; ".join(bad))
    return out


# ---------------------------------------------------------------- the checks

def _rank(row: Mapping[str, str]) -> tuple[int, int, int]:
    """A row's place: by level (a level-less row after every level), layer, then hand-kept rows before each writer's."""
    writer = row["written_by"]
    level = LEVELS.index(row["level"]) if row["level"] else len(LEVELS)
    return (level, LAYERS.index(row["layer"]), 0 if not writer else 1 + WRITERS.index(writer))


def cp_list(row: Mapping[str, str]) -> list[str]:
    """The places a row's cp names: one control point, or, for a line block (LINE_ROLES) and its sensor, the stations
    or control points it joins (LIST separated); [] when it has none."""
    return [p for p in row["cp"].split(LIST) if p]


def carries_field_facts(row: Mapping[str, str]) -> bool:
    """A staging row of a physical device (assignment field or spare) that a rewrite carries its field facts over from
    (system name, node, wiring, notes, cp): a writer may not drop it without naming it (replace_rows). A row the rule
    makes (a virtual mast or head, a part) or a panel status bean (panel_items.json) carries none, so it may go."""
    return (row["level"] == FIELD_LEVEL and row["assignment"] in ("field", "spare")
            and row["role"] != "panel_status")


def is_unplaced(row: Mapping[str, str]) -> bool:
    """A device not on the layout yet: added in PanelPro, kept as its Store beans in jmri_bean, with no level until the
    owner gives its details (owner, 2026-11-20)."""
    return not row["level"]


def _unplaced_problems(r: Mapping[str, str]) -> list[str]:
    """What a level-less row breaks: it carries its beans (jmri_bean), is a field device by its own system name, and
    has no cp, role, writer or other level's facts."""
    from . import tables, tables_build          # tables_build reads this module
    bad = []
    if not r["jmri_bean"]:
        return ["level is one of " + ", ".join(LEVELS) + ", or empty for a device kept by its jmri_bean"]
    if r["assignment"] != "field" or not r["jmri_name"] or r["system_name"] != r["jmri_name"]:
        bad.append("a level-less device is assignment field with system_name equal to jmri_name")
    set_cols = [c for c in ("cp", "role", "written_by", "wiring", "part_of", "blocks", "detector", "stop", "switch",
                            "facing", "protects", "dir") if r[c]]
    if set_cols:
        bad.append(f"a level-less device has no {', '.join(set_cols)} (they come with its level)")
    try:
        beans = tables_build.row_beans(r)
    except tables_build.TablesBuildError as exc:
        return bad + [str(exc).split(": ", 2)[-1]]
    names = {tables.system_name(el) for _, el in beans}
    own = {r["jmri_name"], r["layout_block"]} - {""}
    if r["jmri_name"] not in names:
        bad.append(f"jmri_bean holds no bean named {r['jmri_name']!r}")
    if names - own:
        bad.append(f"jmri_bean holds beans of other names ({', '.join(sorted(names - own))})")
    return bad


def check_rows(rows: Iterable[Mapping[str, str]], where: str = "devices.csv") -> None:
    """The master's invariants; DevicesError listing every problem (a row is named by its line, level, layer and
    name). Run on every load and after every write."""
    bad, keys, jmri, field_systems = [], {}, {}, {}
    ranks = []
    parts, part_names, whole = [], set(), set()      # parts (row, level, part_of); (level, name)s
    for n, r in enumerate(rows, 2):
        at = f"line {n} ({r['level']} {r['layer']} {r['user_name']!r})"
        if r["level"] and r["level"] not in LEVELS:
            bad.append(f"{at}: level is one of {', '.join(LEVELS)}, or empty for a device kept by its jmri_bean")
            continue
        if not r["level"]:
            bad += [f"{at}: {b}" for b in _unplaced_problems(r)]
        elif r["jmri_bean"]:
            bad.append(f"{at}: jmri_bean is for a level-less device; a row with a level is made by the build")
        if r["layer"] not in LAYERS:
            bad.append(f"{at}: layer is one of {', '.join(LAYERS)}")
            continue
        broken = [c for c in COLUMNS if "\n" in r[c] or "\r" in r[c]]
        if broken:
            bad.append(f"{at}: {', '.join(broken)} hold a line break (a record would no longer be one file line)")
        unknown = False
        for col, allowed in (("role", ROLES), ("assignment", ASSIGNMENTS), ("written_by", ("",) + WRITERS)):
            if col == "role" and not r["level"] and not r[col]:
                continue                            # a level-less device has no role yet
            if r[col] not in allowed:
                bad.append(f"{at}: {col} {r[col]!r} is not one of {', '.join(a or 'empty' for a in allowed)}")
                unknown = unknown or col == "written_by"
        for col in ("user_name", "description"):
            if not r[col].strip():
                bad.append(f"{at}: {col} is empty")
        key = (r["level"], r["layer"], r["user_name"])
        if key in keys:
            bad.append(f"{at}: the same level, layer and user_name as line {keys[key]}")
        keys[key] = n
        jn = r["jmri_name"]
        if jn:
            # a virtual turnout and its LCC alias both stand on one internal turnout, so the role is part of the key
            jk = (r["layer"], r["role"] == "lcc_alias", jn)
            if jk in jmri:
                bad.append(f"{at}: jmri_name {jn!r} is line {jmri[jk]}'s as well")
            jmri[jk] = n
        a = r["assignment"]
        if a == "field":
            if not r["system_name"] or not jn:
                bad.append(f"{at}: a field device needs a system_name and a jmri_name")
            elif r["system_name"] != jn and not (r["role"] == "turnout" and jn == r["user_name"]):
                # a staging turnout the tables and panels bind by its user name (staging_device_map.py): the one exception
                bad.append(f"{at}: field, but system_name {r['system_name']!r} is not jmri_name {jn!r}")
            if r["system_name"]:
                if r["system_name"] in field_systems.get(r["layer"], {}):
                    bad.append(f"{at}: field system_name {r['system_name']!r} is line "
                               f"{field_systems[r['layer']][r['system_name']]}'s as well")
                field_systems.setdefault(r["layer"], {})[r["system_name"]] = n
        elif a == "virtual" and not jn:
            bad.append(f"{at}: a virtual device needs a jmri_name")
        elif a == "none" and jn:
            bad.append(f"{at}: assignment none, but jmri_name is {jn!r}")
        if (a == "spare") != (r["role"] == "spare"):
            bad.append(f"{at}: assignment spare and role spare go together")
        if a == "spare" and not (r["system_name"] and r["system_name"] == jn):
            bad.append(f"{at}: a spare detector has its M2S name as system_name and jmri_name")
        if (r["role"] == "panel_status") != (r["written_by"] == "panel_items.json"):
            bad.append(f"{at}: role panel_status and written_by panel_items.json go together")
        if r["layout_block"] and (r["layer"] != "block" or not r["layout_block"].startswith("ILB")):
            bad.append(f"{at}: layout_block {r['layout_block']!r} is for a block row, an ILB name")
        if LIST in r["cp"] and r["role"] not in LINE_ROLES:
            bad.append(f"{at}: cp {r['cp']!r} is a list, but a {r['role'] or r['layer']} sits in one control point "
                       f"(only a line block, roles {', '.join(LINE_ROLES)}, lists the places it joins)")
        if r["wiring"] and r["jmri_comment"]:
            bad.append(f"{at}: wiring and jmri_comment are both set; a row has one comment")
        if (r["role"] == "part") != bool(r["part_of"]):
            bad.append(f"{at}: role part and part_of go together")
        if r["part_of"]:
            if r["layer"] != "block":
                bad.append(f"{at}: part_of is for a block row (a piece of track inside another block)")
            # a part is a JMRI block and layout block of its own on every level (owner, 2026-11-20) whose occupancy
            # sensor is its block's: no detector, wiring, node or DCC address of its own
            made = [c for c in ("node", "detector", "wiring", "dcc") if r[c]]
            if made or a not in ("none", "virtual"):
                bad.append(f"{at}: a part has no detector of its own (its sensor is its block's), so assignment "
                           "none or virtual and no " + ", ".join(made or ["field facts"]))
            parts.append((at, r["level"], r["part_of"]))
            part_names.add((r["level"], r["user_name"]))
        elif r["layer"] == "block":
            whole.add((r["level"], r["user_name"]))
        if not unknown:
            ranks.append((_rank(r), n))
    for at, level, target in parts:            # the block a part names is on the part's own level
        if (level, target) in part_names:
            bad.append(f"{at}: part_of {target!r} is itself a part (a part names a whole block: no chain or cycle)")
        elif (level, target) not in whole:
            bad.append(f"{at}: part_of {target!r} is no block row")
    for (a, na), (b, nb) in zip(ranks, ranks[1:]):
        if b < a:
            bad.append(f"line {nb}: out of order (level, layer, then hand-kept rows before each writer's, "
                       f"in WRITERS order); it follows line {na}")
            break
    if bad:
        raise DevicesError(f"{where}: " + "; ".join(bad))


# ---------------------------------------------------------------- roles, assignments, descriptions

def block_role(name: str) -> str:
    """The role of a block or its occupancy row from its name ("OS Switch 7", "BS Switch 225b", "Track 101 Spur 1",
    "Track Helix Inner", "BS 107 Loop 2")."""
    if re.fullmatch(r"(?:OS|BS) Switch \d+[a-d]", name):
        return "xover_corner"
    if re.fullmatch(r"(?:OS|BS) Switch \d+", name):
        return "os"
    if "Helix" in name:
        return "helix"
    if re.search(r" Spur(?: \d+)?$", name):
        return "spur"
    if re.search(r" Loop(?: \d+)?$", name):
        return "loop_half"
    return "track"


def role_of(layer: str, user_name: str, system_name: str, jmri_name: str) -> str:
    """The role a device-map row gets: DevicesError on a layer a device map does not hold."""
    if layer == "turnout":
        return "lcc_alias" if user_name.startswith("DCC Switch ") else "turnout"
    if layer == "fb":
        return "fb"
    if layer in ("block", "occupancy"):
        return block_role(user_name)
    if layer == "head":
        return "head"
    if layer == "mast":
        if (jmri_name or system_name).startswith("IF$vsm"):
            return "hidden"
        return "intermediate" if re.fullmatch(r"Mast [AB]?\d+", user_name) else "home"
    raise DevicesError(f"layer {layer!r}: a device map has no {layer} rows")


def assignment_of(jmri_name: str) -> str:
    """How a device-map row is in JMRI: none without a jmri_name, virtual for an internal name (IT/IS/IH/IB:HART:, a
    hidden mast, a mast over internal heads), else field."""
    if not jmri_name:
        return "none"
    if jmri_name.startswith(SOURCE_PREFIXES) or jmri_name.startswith("IF$vsm"):
        return "virtual"
    if jmri_name.startswith("IF$shsm") and not _WIRED_HEAD.search(jmri_name):
        return "virtual"
    return "field"


def describe(r: Mapping[str, str]) -> str:
    """One plain sentence for a row from its columns; DevicesError on a role it has no sentence for. Writers call this
    for the rows they write; a hand-kept row's sentence is kept as given."""
    u, role, node = r["user_name"], r["role"], r["node"]
    on = f" on LCOS node {node}" if node else ""
    at = f" at {r['cp']}" if r["cp"] else ""
    live = "wired in JMRI" if r["assignment"] == "field" else "a virtual stand-in until the plant is wired"
    if role == "turnout":
        return f"Turnout {u}{at}, {live}{on}."
    if role == "lcc_alias":
        return f"LCC alias {u} of the turnout with the same number, DCC address {r['dcc'] or 'not set'}."
    if role == "fb":
        return f"Feedback sensor {u}: reports one position of its turnout{on}."
    if role == "os":
        return f"Block {u}: the track through the points of its switch."
    if role == "xover_corner":
        return f"Block {u}: one corner of a double crossover."
    if role == "track":
        return f"Track block {u}."
    if role == "spur":
        return f"Block {u}: a spur that ends at a buffer stop."
    if role == "loop_half":
        return f"Block {u}: one half of a balloon loop."
    if role == "helix":
        return f"Block {u}: a helix track, one block for its whole length."
    if role == "home":
        return f"Signal mast {u} at a switch, facing {r['facing'] or 'its track'}."
    if role == "intermediate":
        return f"Intermediate signal mast {u} between two blocks, facing {r['facing'] or 'its track'}."
    if role == "hidden":
        return f"Hidden routing mast {u}, facing {r['facing'] or 'its track'}; it shows no signal on the panel."
    if role == "head":
        return f"Signal head {u} of {'Mast ' + u.removeprefix('Head ').split(' ')[0]}, {live}."
    if role == "spare":
        return f"Spare detector {u}: a field detector with no block assigned."
    if role == "part":
        return f"Piece {u} of block {r['part_of']}: a JMRI block of its own on {r['part_of']}'s occupancy sensor."
    raise DevicesError(f"no description rule for role {role!r} ({u})")


# ---------------------------------------------------------------- device-map rows and master rows

def _carries_dcc(r: Mapping[str, str]) -> bool:
    return r["role"] == "turnout" and r["assignment"] == "field"


def comment_of(r: Mapping[str, str]) -> str:
    """The JMRI comment of a master row: jmri_comment, else wiring, with the DCC group put in as the JMRI comment has
    it for a field turnout (hartlib.names.jmri_comment). The one place a reader gets a row's comment."""
    return r["jmri_comment"] or (names.jmri_comment(r["wiring"], r["dcc"]) if _carries_dcc(r) else r["wiring"])


def device_map_row(r: Mapping[str, str]) -> dict[str, str]:
    """The old-form device-map row of a master row: its comment is comment_of's."""
    comment = comment_of(r)
    return {c: (comment if c == "comment" else r[c]) for c in DEVICE_COLUMNS}


def master_row(old: Mapping[str, str], writer: str, prior: Mapping[str, str] | None = None,
               description: str | None = None) -> dict[str, str]:
    """The master row of an old-form device-map row. `prior` is the row it replaces, whose description a hand-kept
    row keeps. DevicesError when the comment cannot be split back by device_map_row."""
    if not set(DEVICE_COLUMNS) <= set(old):
        raise DevicesError(f"device-map row {old.get('user_name')!r} misses columns "
                           f"{sorted(set(DEVICE_COLUMNS) - set(old))}")
    r = {c: "" for c in COLUMNS}
    r.update({c: str(old[c]) for c in _SHARED})
    r["role"] = role_of(old["layer"], old["user_name"], old["system_name"], old["jmri_name"])
    r["assignment"] = assignment_of(old["jmri_name"])
    r["written_by"] = writer
    comment = old["comment"]
    if _NODE_TEXT.match(comment):
        r["wiring"] = names.split_dcc(comment)[0] if _carries_dcc(r) else comment
    else:
        r["jmri_comment"] = comment
    r["description"] = description or (prior["description"] if prior and not writer else "") or describe(r)
    if device_map_row(r) != {c: str(old[c]) for c in DEVICE_COLUMNS}:
        raise DevicesError(f"{r['level']} {r['layer']} {r['user_name']}: the comment {comment!r} does not survive "
                           f"the split into wiring, dcc and jmri_comment")
    return r


# ---------------------------------------------------------------- writing

def replace_rows(rows: Iterable[Mapping[str, str]], writer: str, new: Iterable[Mapping[str, str]],
                 drops: Iterable[tuple[str, str, str]] = (),
                 adopts: Iterable[tuple[str, str, str]] = ()) -> list[dict[str, str]]:
    """`rows` with the rows `writer` holds replaced by `new` (master rows with written_by == writer), sorted into the
    master's order (stable). DevicesError when the writer is not in WRITERS, a new row names another writer or
    would take a key (level, layer, user_name) a row held by someone else has, a row of the writer that carries
    field facts (carries_field_facts) would go with no new row of its key (a rename would lose them silently: name it
    in `drops` when the row is meant to go), or the result breaks check_rows. `adopts` names the
    keys of hand-kept rows the writer takes over (a hand-kept row of that key is replaced by its new row, as its own
    would be): how a level's rows move from the owner's hand to a builder, which carries their hand facts over."""
    if writer not in WRITERS:
        raise DevicesError(f"writer {writer!r} is not one of {', '.join(WRITERS)}")
    rows, new = [dict(r) for r in rows], [dict(r) for r in new]
    foreign = [r for r in new if r["written_by"] != writer]
    if foreign:
        raise DevicesError(f"{writer} would write {len(foreign)} row(s) held by someone else, first "
                           f"{foreign[0]['level']} {foreign[0]['layer']} {foreign[0]['user_name']!r} "
                           f"(written_by {foreign[0]['written_by']!r})")
    adopts = set(adopts)
    mine = lambda r: r["written_by"] == writer or (not r["written_by"] and  # noqa: E731
                                                   (r["level"], r["layer"], r["user_name"]) in adopts)
    others = {(r["level"], r["layer"], r["user_name"]): r["written_by"] for r in rows if not mine(r)}
    clash = [k for k in ((r["level"], r["layer"], r["user_name"]) for r in new) if k in others]
    if clash:
        raise DevicesError(f"{writer} would rewrite row(s) it does not hold: "
                           + ", ".join(f"{k[2]!r} ({k[1]}, level {k[0]}; held by {others[k] or 'hand'})" for k in clash[:5]))
    kept = {(r["level"], r["layer"], r["user_name"]) for r in new} | set(drops)
    lost = [r for r in rows if mine(r) and carries_field_facts(r)
            and (r["level"], r["layer"], r["user_name"]) not in kept]
    if lost:
        raise DevicesError(f"{writer} would drop {len(lost)} staging field device row(s), first "
                           + ", ".join(f"{r['user_name']!r} ({r['layer']}, level {r['level']})" for r in lost[:5])
                           + "; a renamed row loses the field facts it carries over: pass it in drops if it is to go")
    out = [r for r in rows if not mine(r)] + new
    out.sort(key=_rank)
    check_rows(out, "devices.csv after the write")
    return out


def _text(columns: Iterable[str], rows: Iterable[Mapping[str, str]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(columns), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def master_text(rows: Iterable[Mapping[str, str]]) -> str:
    return _text(COLUMNS, rows)


def device_map_rows(rows: Iterable[Mapping[str, str]], levels: tuple[str, ...]) -> list[dict[str, str]]:
    """The old-form rows of a device map: those of `levels` outside OUT_OF_MAPS, in master order."""
    return [device_map_row(r) for r in rows if r["level"] in levels and r["role"] not in OUT_OF_MAPS]


def texts(rows: list[Mapping[str, str]], files: Files | None = None) -> dict[Path, str]:
    """{path: text} of the master from `rows`."""
    f = files or Files.here()
    return {f.master: master_text(rows)}


def outputs_after_rows(writer: str, new: Iterable[Mapping[str, str]], files: Files | None = None,
                       drops: Iterable[tuple[str, str, str]] = (),
                       adopts: Iterable[tuple[str, str, str]] = ()) -> dict[Path, str]:
    """{path: text} of the master once `writer` has written `new`, master rows with written_by set to it, in place of
    the rows it holds (replace_rows). The caller writes the texts (or compares them for --check); nothing is written
    here. DevicesError when the writer would touch a row it does not hold."""
    f = files or Files.here()
    return texts(replace_rows(load(f), writer, new, drops, adopts), f)


def outputs_after(writer: str, old_rows: Iterable[Mapping[str, str]], files: Files | None = None,
                  drops: Iterable[tuple[str, str, str]] = (), master_rows: Iterable[Mapping[str, str]] = (),
                  adopts: Iterable[tuple[str, str, str]] = ()) -> dict[Path, str]:
    """outputs_after_rows for `old_rows`, old-form device-map rows (master_row gives each its master form), and
    `master_rows`, rows already in the master's form (a builder that carries a level's hand facts over, or rows the
    device maps leave out). What a reader of the master sees for these rows is what the writer gave; DevicesError
    when it is not."""
    f = files or Files.here()
    old_rows = list(old_rows)
    prior = {(r["level"], r["layer"], r["user_name"]): r for r in load(f)}
    master_rows = [dict(r) for r in master_rows]
    new = [master_row(o, writer, prior.get((str(o["level"]), o["layer"], o["user_name"]))) for o in old_rows]
    out = outputs_after_rows(writer, new + master_rows, f, drops, adopts)
    want = {(str(o["level"]), o["layer"], o["user_name"]): {c: str(o[c]) for c in DEVICE_COLUMNS} for o in old_rows}
    whole = {(r["level"], r["layer"], r["user_name"]): r for r in master_rows}
    back = {(r["level"], r["layer"], r["user_name"]): r for r in csv.DictReader(io.StringIO(out[f.master]))
            if r["written_by"] == writer}
    held = {k: device_map_row(r) for k, r in back.items() if k not in whole}
    if held != want or any(back.get(k) != r for k, r in whole.items()):
        raise DevicesError(f"{writer}: the rows written do not read back as given")
    return out


def stale_message(path: Path, files: Files, script: str) -> str:
    """What a --check says of a stale `path`: the writer to run."""
    return f"{path.name} is stale: run python3 {script}"


def write_all(files: Files, content: Mapping[Path, str]) -> list[Path]:
    """Write the changed ones of `content`; the paths written."""
    done = []
    for p, text in content.items():
        if not p.exists() or p.read_text(encoding="utf-8") != text:
            p.write_text(text, encoding="utf-8")
            done.append(p)
    return done


# ---------------------------------------------------------------- the check

def stale(files: Files | None = None) -> list[str]:
    """What is wrong with the master: [] when it and its dictionary check and every row the old-form readers take
    converts to that form and back (a DevicesError otherwise, naming the row)."""
    f = files or Files.here()
    rows = load(f)
    read_dictionary(f.dictionary)
    out = []
    for r in rows:
        if r["role"] in OUT_OF_MAPS:
            continue
        try:
            master_row(device_map_row(r), r["written_by"], r)
        except DevicesError as exc:
            out.append(str(exc))
        except (KeyError, ValueError) as exc:
            out.append(f"level {r['level']} {r['layer']} {r['user_name']}: cannot be read in the device-map form ({exc!r})")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m hartlib.devices", description=__doc__.split("\n")[0])
    ap.add_argument("action", choices=("check",))
    args = ap.parse_args(argv)
    f = Files.here()
    try:
        problems = stale(f)
        for p in problems:
            print(p, file=sys.stderr)
        if not problems:
            print(f"devices.csv: {len(load(f))} rows; its dictionary agrees")
        return 1 if problems else 0
    except DevicesError as exc:
        print(f"devices.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
