"""The device master for all three levels: devices_generated.csv and devices_field.csv, merged into one view.

The master holds one row per railroad device (ADR-029). Since the amendment of 2026-11-21 it is two files under
jmri/layouts/hart/data: devices_generated.csv, every row the builders make (written by them alone, through
outputs_after), and devices_field.csv, the owner's cells, each row keyed by (level, layer, user_name) and holding
only FIELD_COLUMNS, plus the level-less devices a Store split takes in (full rows). load() and index() merge them
(merge: a non-empty field cell wins; a keyed field row with no generated row is an error), so readers see one
master. A builder reads the owner's cells from field_index(), never back from its own last output; the one
read-back it makes is its name memory (allocated_names). Before the split the master was one file, devices.csv. Staging, main and upper are one
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
  every row with a level has one, and only a Store's level-less device (the field file's) has none. A writer
  replaces only the rows that carry its name (outputs_after_rows), stops on a key another writer or a Store's device
  holds, and cannot drop a key the field file names (merge: rename or remove the field row).

Row order is level, layer (LAYERS), then the writer (WRITERS order; a Store's level-less rows after every level),
then the order the writer gave, so a rebuild changes only its own rows and `check` can hold each file to it. Block
and mast numbers that le_tables.block_sort and block_numbering.csv set are not touched here.

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
from .railroad_facts import DEVICE_COLUMNS, DEVICE_LIST, NAME_LAYERS, FactsError

# The one place the master's file names and paths are written (T6a): every other module asks for them here, and
# tools/hartlib/tests/test_devices_one_path.py fails on any tracked .py outside hartlib that names a file itself.
# MASTER is the generated file, a reader's handle on the pair: load(MASTER) merges the field file beside it.
GENERATED_FILE = "devices_generated.csv"     # every row the builders make (WRITERS), written by them alone
FIELD_FILE = "devices_field.csv"             # the owner's cells, keyed by KEY, and the Store's level-less devices
MASTER_FILE = GENERATED_FILE
ONE_FILE = "devices.csv"                     # the one-file master before the split (2026-11-21), for its history
MASTER = paths.LAYOUT_DATA / MASTER_FILE
FIELD = paths.LAYOUT_DATA / FIELD_FILE

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
WRITERS = ("build_masts.py", "build_device_map.py", "panel_items.json")
# roles the two device maps leave out: a spare detector, a panel status bean, and a part (a block row with part_of: a
# piece of track inside another block: a JMRI block on its block's occupancy sensor, built by its level's builder, with
# no occupancy row or detector of its own)
OUT_OF_MAPS = ("spare", "panel_status", "part")
SOURCE_PREFIXES = ("IT:HART:", "IS:HART:", "IH:HART:", "IB:HART:")

COLUMNS = ("level", "cp", "layer", "role", "user_name", "assignment", "system_name", "jmri_name", "node", "dcc",
           "wiring", "jmri_comment", "trial_name", "notes", "blocks", "detector", "stop", "layout_block",
           "part_of", "switch", "facing", "protects", "dir", "written_by", "description", "jmri_bean")
KEY = ("level", "layer", "user_name")      # a row's key in both files
# The columns of a keyed field row (the owner's cells, ADR-029 amendment 2026-11-21): the cells a builder took from
# the master's previous rows before the split, so the owner's value lives in one place. A field row also gives a
# staging device's identity (role, assignment): staging's devices are the owner's, so its rows come from here.
FIELD_COLUMNS = ("role", "assignment", "cp", "system_name", "jmri_name", "node", "dcc", "jmri_comment", "trial_name",
                 "notes", "detector", "stop", "layout_block")
# In a field jmri_comment, where the builder puts the detector's wiring.csv text ("occupancy Block 4-2 / M2S401"): the
# owner keeps the words around it, wiring.csv the pin, so a moved pin changes no hand file. The merged cell is the
# generated one, which must be the field text with the mark filled in (merge checks it).
OCCUPANCY_MARK = "{occupancy}"
OCCUPANCY_TEXT = r"occupancy Block \d+-\d+ / M2S\d+"
# staging: its plant is the field, so its devices are the owner's (each a field row in devices_field.csv)
FIELD_LEVEL = "1"
LIST = DEVICE_LIST              # the separator of a list column (blocks, protects, a line block's cp)
# the columns an old-form device-map row shares with the master; its comment is built, the rest of the master is left out
_SHARED = tuple(c for c in DEVICE_COLUMNS if c not in ("comment",))

_NODE_TEXT = re.compile(r"Node: \d+")
_WIRED_HEAD = re.compile(r"\(IH\d+\)")


class DevicesError(FactsError):
    """The master or its dictionary cannot stand as it is, or a write would break it."""


def master_path(data: Path | None = None) -> Path:
    """The master's path (the generated file, a reader's handle on the pair): MASTER, or the one under a data folder
    `data` (Sources.under(root), a test's temp dir)."""
    return MASTER if data is None else Path(data) / MASTER_FILE


def field_path(data: Path | None = None) -> Path:
    """The field file's path: FIELD, or the one under a data folder `data`."""
    return FIELD if data is None else Path(data) / FIELD_FILE


@dataclass(frozen=True)
class Files:
    """The master (the generated file), its dictionary and the field file; tests point them at a copy. `field` None
    is a copy with no field file: its master holds every cell (a test's one-file master)."""
    master: Path
    dictionary: Path
    field: Path | None = None

    @staticmethod
    def under(data: Path) -> "Files":
        """The files as they sit under a data folder (jmri/layouts/hart/data): one root, so a test or a script that
        points it elsewhere moves every file together and cannot write the repo's."""
        return Files(master_path(data), Path(data) / "devices.columns.csv", field_path(data))

    @staticmethod
    def here() -> "Files":
        return Files.under(paths.LAYOUT_DATA)

    @staticmethod
    def of(source: "Files | Path | str | None") -> "Files":
        """The Files a reader's `source` names: None the repo's, a Files itself, or a master's path, with the field
        file beside it when there is one there (a test's one-file copy has none)."""
        if source is None:
            return Files.here()
        if isinstance(source, Files):
            return source
        path = Path(source)
        beside = path.parent / FIELD_FILE
        return Files(path, path.parent / "devices.columns.csv", beside if beside.is_file() else None)

    def but(self, **changes) -> "Files":
        return replace(self, **changes)


# ---------------------------------------------------------------- reading

@lru_cache(maxsize=16)
def _read(name: str, data: bytes) -> tuple[Mapping[str, str], ...]:
    """The rows of one file's bytes (the generated or the field file: one header). Cached on the bytes themselves, so
    a write of the same size in the same clock tick can never return stale rows."""
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


def key_of(row: Mapping[str, str]) -> tuple[str, str, str]:
    """A row's key (KEY): level, layer, user name."""
    return (row["level"], row["layer"], row["user_name"])


def key_text(key: tuple[str, str, str]) -> str:
    """A key as a message names it: "Track 12 (level 1, block)", or "X (no level, turnout)" for a Store's device."""
    level, layer, name = key
    return f"{name} ({'level ' + level if level else 'no level'}, {layer})"


def check_field(rows: Iterable[Mapping[str, str]], name: str = FIELD_FILE) -> None:
    """The field file's own rules: no writer; a keyed row (one with a level) holds its key and FIELD_COLUMNS cells
    only; a key once; rows in level and layer order. A level-less row (a Store's device) is a full row, which
    check_rows holds on the merged view. DevicesError listing every problem."""
    bad, seen, ranks = [], set(), []
    for r in rows:
        k = key_of(r)
        at = f"{name}: {key_text(k)}"
        if r["written_by"]:
            bad.append(f"{at}: written_by {r['written_by']!r}; a field row has no writer (the builders write "
                       f"{GENERATED_FILE})")
        if r["level"]:
            extra = [c for c in COLUMNS if c not in KEY and c not in FIELD_COLUMNS and r[c]]
            if extra:
                bad.append(f"{at}: {', '.join(extra)} set; a field row holds only "
                           f"{', '.join(FIELD_COLUMNS)} (the builders make the rest)")
        if k in seen:
            bad.append(f"{at}: the key is twice in the file")
        seen.add(k)
        if r["layer"] in LAYERS and (not r["level"] or r["level"] in LEVELS):
            ranks.append((_rank(r), k))
    for (a, ka), (b, kb) in zip(ranks, ranks[1:]):
        if b < a:
            bad.append(f"{name}: {key_text(kb)} is out of order (level, then layer); it follows {key_text(ka)}")
            break
    if bad:
        raise DevicesError("; ".join(bad))


def check_generated(rows: Iterable[Mapping[str, str]], name: str = GENERATED_FILE) -> None:
    """The generated file's own rules: every row has a level and a writer of WRITERS (a Store's level-less device is
    the field file's). DevicesError listing every problem."""
    bad = []
    for r in rows:
        at = f"{name}: {key_text(key_of(r))}"
        if not r["level"]:
            bad.append(f"{at}: a level-less device (a Store's) is kept in {FIELD_FILE}")
        elif r["written_by"] not in WRITERS:
            bad.append(f"{at}: written_by {r['written_by']!r} is not one of {', '.join(WRITERS)} (the owner's "
                       f"cells go in {FIELD_FILE})")
    if bad:
        raise DevicesError("; ".join(bad))


def _templated(field_cell: str, generated_cell: str) -> bool:
    """Whether `generated_cell` is the field text `field_cell` with its OCCUPANCY_MARK filled in."""
    head, _, tail = field_cell.partition(OCCUPANCY_MARK)
    return bool(re.fullmatch(re.escape(head) + OCCUPANCY_TEXT + re.escape(tail), generated_cell))


def fill_occupancy(text: str, occupancy: str) -> str:
    """A field jmri_comment with its OCCUPANCY_MARK filled with `occupancy` (the detector's wiring.csv text)."""
    return text.replace(OCCUPANCY_MARK, occupancy, 1)


def merge(generated: Iterable[Mapping[str, str]], field: Iterable[Mapping[str, str]],
          names: tuple[str, str] = (GENERATED_FILE, FIELD_FILE)) -> tuple[Mapping[str, str], ...]:
    """The one view every reader gets: each generated row with its field row's cells over it (a non-empty field cell
    replaces the generated one; an empty one means no override), then the field file's level-less rows (a Store's
    devices), in the master's order (_rank), checked (check_rows). A field jmri_comment with OCCUPANCY_MARK is the
    builder's to fill: the generated cell stands, and must be the field text with the mark filled in. DevicesError on
    a field cell outside FIELD_COLUMNS, a keyed field row with no generated row (a builder no longer makes it), a
    templated comment the generated cell does not follow, or a merged row that breaks check_rows."""
    gname, fname = names
    field = list(field)
    check_field(field, fname)
    keyed = {key_of(r): r for r in field if r["level"]}
    out, bad, used = [], [], set()
    for g in generated:
        k = key_of(g)
        f = keyed.get(k)
        if f is None:
            out.append(g)
            continue
        used.add(k)
        row = dict(g)
        for c in FIELD_COLUMNS:
            v = f[c]
            if not v:
                continue
            if c == "jmri_comment" and OCCUPANCY_MARK in v:
                if not _templated(v, g[c]):
                    bad.append(f"{fname}: {key_text(k)}: jmri_comment {v!r} needs its {OCCUPANCY_MARK} filled from "
                               f"wiring.csv, but {gname} has {g[c]!r} (run make panels)")
                continue
            row[c] = v
        out.append(MappingProxyType(row))
    bad += [f"{fname}: {key_text(k)} has no row in {gname} (no builder makes it now): rename the field row to the "
            "device's new name, or remove it" for k in keyed if k not in used]
    if bad:
        raise DevicesError("; ".join(bad))
    out += [r for r in field if not r["level"]]
    out.sort(key=_rank)
    rows = tuple(out)
    check_rows(rows, f"{gname} with {fname}")
    return rows


def redundant(generated: Iterable[Mapping[str, str]], field: Iterable[Mapping[str, str]]) -> list[str]:
    """Warnings: each field cell equal to the generated cell it overrides (the value would be in two places)."""
    keyed = {key_of(r): r for r in field if r["level"]}
    out = []
    for g in generated:
        f = keyed.get(key_of(g))
        if f is not None:
            out += [f"{FIELD_FILE}: {key_text(key_of(g))}: {c} {f[c]!r} is the generated value too (redundant)"
                    for c in FIELD_COLUMNS if f[c] and f[c] == g[c]]
    return out


def unmerge(rows: Iterable[Mapping[str, str]], field: Iterable[Mapping[str, str]],
            writer: str = "the builder") -> list[dict[str, str]]:
    """The generated form of merged rows `rows` (a builder's rows, as readers will see them): each row's cells the
    field file gives are left empty, so the owner's value lives in one place; a templated comment (OCCUPANCY_MARK)
    stays, as the builder fills it. Level-less rows (the field file's own) are left out. DevicesError when a row
    gives a field cell a value other than the field file's (the builder would override the owner)."""
    keyed = {key_of(r): r for r in field if r["level"]}
    out, bad = [], []
    for r in rows:
        if not r["level"]:
            continue
        row = dict(r)
        f = keyed.get(key_of(r))
        if f is not None:
            for c in FIELD_COLUMNS:
                v = f[c]
                if not v:
                    continue
                if c == "jmri_comment" and OCCUPANCY_MARK in v:
                    if not _templated(v, row[c]):
                        bad.append(f"{writer} gives {key_text(key_of(r))} jmri_comment {row[c]!r}, which is not "
                                   f"{FIELD_FILE}'s {v!r} with its {OCCUPANCY_MARK} filled")
                elif row[c] != v:
                    bad.append(f"{writer} gives {key_text(key_of(r))} {c} {row[c]!r}, but {FIELD_FILE} holds {v!r}")
                else:
                    row[c] = ""
        out.append(row)
    if bad:
        raise DevicesError("; ".join(bad))
    return out


def _read_file(path: Path) -> tuple[Mapping[str, str], ...]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise DevicesError(f"{path}: cannot read it ({exc.strerror})") from None
    return _read(path.name, data)


def generated_rows(files: "Files | Path | str | None" = None) -> tuple[Mapping[str, str], ...]:
    """The generated file's rows as written (field cells empty), unmerged. Two uses only: a writer keeps the other
    writers' rows (outputs_after), and a builder's name memory (allocated_names): the numbers it gave before, so a
    generated name never shifts. A builder never takes an owner's cell from here."""
    f = Files.of(files)
    rows = _read_file(f.master)
    if f.field is not None:
        check_generated(rows, f.master.name)
    return rows


def allocated_names(levels: Iterable[str], layer: str, roles: Iterable[str] | None = None,
                    files: "Files | Path | str | None" = None) -> dict[str, Mapping[str, str]]:
    """{user name: generated row} of the `layer` rows of `levels` (and `roles`) as the builders last wrote them: the
    one read-back a builder makes of its own output (ADR-029 amendment), for the names it numbered itself (a virtual
    mast's ordinal, a part's block and layout block numbers), so a rebuild gives every one the number it had. Never
    an owner's cell: those are field_index's."""
    levels, roles = frozenset(levels), None if roles is None else frozenset(roles)
    return {r["user_name"]: r for r in generated_rows(files)
            if r["level"] in levels and r["layer"] == layer and (roles is None or r["role"] in roles)}


def field_rows(files: "Files | Path | str | None" = None) -> tuple[Mapping[str, str], ...]:
    """The field file's rows, checked (check_field); () for a copy with no field file."""
    f = Files.of(files)
    if f.field is None:
        return ()
    rows = _read_file(f.field)
    check_field(rows, f.field.name)
    return rows


def field_index(files: "Files | Path | str | None" = None) -> Mapping[tuple[str, str, str], Mapping[str, str]]:
    """{key: field row} of the field file's keyed rows (those with a level): the owner's cells, the one place a
    builder reads them from (it never reads them back from its own last output)."""
    return MappingProxyType({key_of(r): r for r in field_rows(files) if r["level"]})


@lru_cache(maxsize=8)
def _merged(gname: str, gdata: bytes, fname: str | None, fdata: bytes | None) -> tuple[Mapping[str, str], ...]:
    generated = _read(gname, gdata)
    if fname is None:                       # a one-file copy: it holds every cell
        check_rows(generated, gname)
        return generated
    check_generated(generated, gname)
    return merge(generated, _read(fname, fdata), (gname, fname))


def _field_bytes(f: "Files") -> bytes:
    try:
        return f.field.read_bytes()
    except OSError as exc:
        raise DevicesError(f"{f.field}: cannot read it ({exc.strerror})") from None


def parse(text: str, name: str = MASTER_FILE, files: "Files | None" = None) -> tuple[Mapping[str, str], ...]:
    """The merged rows of a generated file's text (one outputs_after gives, before it is written) with `files`'
    field file (none, or a Files with no field file: the text holds every cell), checked as load checks the files.
    DevicesError naming the file on any problem."""
    if files is None or files.field is None:
        return _merged(name, text.encode("utf-8"), None, None)
    return _merged(name, text.encode("utf-8"), files.field.name, _field_bytes(files))


def load(files: "Files | Path | str | None" = None) -> tuple[Mapping[str, str], ...]:
    """The master's rows (read-only mappings): the generated file merged with the field file (merge), checked
    (check_rows). Read once per state of the two files: the merge is cached on both files' bytes, so every reader of
    one run shares it and a changed file is always read again. `files` is the Files of a copy, or a master's path
    (Files.of). A bad row ANYWHERE stops the load (check_rows names its key and file); there is no way round it.
    DevicesError on any problem."""
    f = Files.of(files)
    try:
        gdata = f.master.read_bytes()
    except OSError as exc:
        raise DevicesError(f"{f.master}: cannot read it ({exc.strerror})") from None
    if f.field is None:
        return _merged(f.master.name, gdata, None, None)
    return _merged(f.master.name, gdata, f.field.name, _field_bytes(f))


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
    path = Files.of(files).master
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


def column_file(column: str) -> str:
    """Which file may hold `column` on a row with a level: "field" for the key and FIELD_COLUMNS (the owner's cell
    in devices_field.csv when the row has a field row, else the builder's), "generated" for the rest (the builders'
    alone). A Store's level-less row holds every column in the field file."""
    return "field" if column in KEY or column in FIELD_COLUMNS else "generated"


def read_dictionary(path: Path) -> dict[str, str]:
    """{column: description} of devices.columns.csv; DevicesError unless it is exactly the columns
    `column,file,description` with every master column once, each described, and its file column_file's."""
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
    except OSError as exc:
        raise DevicesError(f"{path}: cannot read it ({exc.strerror})") from None
    if not rows or rows[0] != ["column", "file", "description"]:
        raise DevicesError(f"{path.name}: the header is column,file,description")
    out, bad = {}, []
    for line, r in enumerate(rows[1:], 2):
        if len(r) != 3:
            bad.append(f"line {line}: {len(r)} fields, expected 3")
        elif r[0] in out:
            bad.append(f"line {line}: {r[0]} is described twice")
        elif not r[2].strip():
            bad.append(f"line {line}: {r[0]} has no description")
        elif r[0] in COLUMNS and r[1] != column_file(r[0]):
            bad.append(f"line {line}: {r[0]} is in file {column_file(r[0])!r}, not {r[1]!r}")
        else:
            out[r[0]] = r[2]
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
        more = f"; and {len(bad) - 20} more" if len(bad) > 20 else ""
        raise DevicesError(f"{where}: " + "; ".join(bad[:20]) + more)


# ---------------------------------------------------------------- roles, assignments, descriptions

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
    """The master row of an old-form device-map row with its `role` (the writer states what each row is: no role is
    read off a name, hand-off row 8). `prior` is the row it replaces, whose description a hand-kept row keeps.
    DevicesError on a layer a device map does not hold, a row with no role or one not in ROLES, or a comment that
    cannot be split back by device_map_row."""
    if not set(DEVICE_COLUMNS) <= set(old):
        raise DevicesError(f"device-map row {old.get('user_name')!r} misses columns "
                           f"{sorted(set(DEVICE_COLUMNS) - set(old))}")
    if old["layer"] not in NAME_LAYERS:
        raise DevicesError(f"layer {old['layer']!r}: a device map has no {old['layer']} rows")
    role = str(old.get("role") or "")
    if role not in ROLES:
        raise DevicesError(f"{old['level']} {old['layer']} {old['user_name']!r}: {writer or 'a hand-kept row'} gives "
                           f"it role {role!r}, not one of {', '.join(ROLES)}")
    r = {c: "" for c in COLUMNS}
    r.update({c: str(old[c]) for c in _SHARED})
    r["role"] = role
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

def replace_rows(rows: Iterable[Mapping[str, str]], writer: str,
                 new: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    """`rows` with the rows `writer` holds replaced by `new` (master rows with written_by == writer), sorted into the
    master's order (stable). DevicesError when the writer is not in WRITERS, a new row names another writer or
    would take a key (level, layer, user_name) a row held by someone else has (another writer's, or a Store's
    level-less device), or the result breaks check_rows. A row the field file names may not go: merge refuses the
    pair (rename or remove the field row), so the owner's cells are never dropped silently."""
    rows, new = [dict(r) for r in rows], [dict(r) for r in new]
    _writes_only_its_own(writer, new, [r for r in rows if r["written_by"] != writer])
    out = [r for r in rows if r["written_by"] != writer] + new
    out.sort(key=_rank)
    check_rows(out, f"the master after {writer}'s write")
    return out


def _writes_only_its_own(writer: str, new: list[Mapping[str, str]], others: Iterable[Mapping[str, str]]) -> None:
    """DevicesError when `writer` is not in WRITERS, a row of `new` names another writer, or takes the key of a row of
    `others` (another writer's, or a Store's level-less device)."""
    if writer not in WRITERS:
        raise DevicesError(f"writer {writer!r} is not one of {', '.join(WRITERS)}")
    foreign = [r for r in new if r["written_by"] != writer]
    if foreign:
        raise DevicesError(f"{writer} would write {len(foreign)} row(s) held by someone else, first "
                           f"{foreign[0]['level']} {foreign[0]['layer']} {foreign[0]['user_name']!r} "
                           f"(written_by {foreign[0]['written_by']!r})")
    held = {key_of(r): r["written_by"] for r in others}
    clash = [k for k in (key_of(r) for r in new) if k in held]
    if clash:
        raise DevicesError(f"{writer} would rewrite row(s) it does not hold: "
                           + ", ".join(f"{k[2]!r} ({k[1]}, level {k[0]}; held by {held[k] or FIELD_FILE})"
                                       for k in clash[:5]))


def _text(columns: Iterable[str], rows: Iterable[Mapping[str, str]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(columns), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def master_text(rows: Iterable[Mapping[str, str]]) -> str:
    return _text(COLUMNS, rows)


def write_one_file(rows: Iterable[Mapping[str, str]], files: "Files | Path | str | None" = None) -> Path:
    """Write `rows` as a one-file master: a test's or a check's copy with no field file beside it, which holds every
    cell; the path written. The repo's pair is written by write_generated and write_field alone."""
    f = Files.of(files)
    if f.field is not None:
        raise DevicesError(f"{f.master.name} has a field file beside it; write the pair (write_generated, write_field)")
    path = f.master
    path.write_text(master_text(rows), encoding="utf-8")
    return path


def write_generated(rows: Iterable[Mapping[str, str]], files: "Files | Path | str | None" = None) -> Path:
    """Write `rows` (generated rows: field cells empty) as the generated file, once it checks on its own and merged
    with the field file; the path written. With write_field, the one writer of the pair's text."""
    f = Files.of(files)
    rows = [dict(r) for r in rows]
    check_generated(rows, f.master.name)
    merge(rows, field_rows(f), (f.master.name, f.field.name if f.field else FIELD_FILE))
    f.master.write_text(master_text(rows), encoding="utf-8")
    return f.master


def write_field(rows: Iterable[Mapping[str, str]], files: "Files | Path | str | None" = None) -> Path:
    """Write `rows` as the field file, once it checks on its own and merged with the generated file; the path
    written. DevicesError (nothing written) otherwise."""
    f = Files.of(files)
    if f.field is None:
        raise DevicesError(f"{f.master.name} has no field file beside it to write")
    rows = [dict(r) for r in rows]
    check_field(rows, f.field.name)
    merge(generated_rows(f), rows, (f.master.name, f.field.name))
    f.field.write_text(master_text(rows), encoding="utf-8")
    return f.field


def device_map_rows(rows: Iterable[Mapping[str, str]], levels: tuple[str, ...]) -> list[dict[str, str]]:
    """The old-form rows of a device map: those of `levels` outside OUT_OF_MAPS, in master order."""
    return [device_map_row(r) for r in rows if r["level"] in levels and r["role"] not in OUT_OF_MAPS]


def texts(rows: list[Mapping[str, str]], files: Files | None = None) -> dict[Path, str]:
    """{path: text} of the generated file from merged rows `rows` (unmerge: the field file's cells left out)."""
    f = files or Files.here()
    return {f.master: master_text(unmerge(rows, field_rows(f)) if f.field is not None else rows)}


def outputs_after_rows(writer: str, new: Iterable[Mapping[str, str]], files: Files | None = None) -> dict[Path, str]:
    """{path: text} of the generated file once `writer` has written `new`, its rows as readers will see them (merged
    form, written_by set to it), in place of the rows it holds (replace_rows on the merged view). The writer's rows
    go in with the field file's cells left empty (unmerge); every other writer's generated row is kept as written.
    The caller writes the texts (or compares them for --check); nothing is written here. DevicesError when the
    writer would touch a row it does not hold, override a field cell, or the result does not merge back to what the
    writer gave."""
    f = files or Files.here()
    if f.field is None:                     # a one-file copy: it holds every cell
        return texts(replace_rows(load(f), writer, new), f)
    # The old merged view is not read: after an owner's edit (a field row removed or renamed) it may not merge any
    # more, and this write is what makes the pair whole again.
    new = [dict(r) for r in new]
    field = field_rows(f)
    keep = [dict(g) for g in generated_rows(f) if g["written_by"] != writer]
    _writes_only_its_own(writer, new, keep + [r for r in field if not r["level"]])
    out = keep + unmerge(new, field, writer)
    out.sort(key=_rank)
    back = merge(out, field, (f.master.name, f.field.name))
    mine = {key_of(r): dict(r) for r in back if r["written_by"] == writer}
    if mine != {key_of(r): r for r in new}:
        raise DevicesError(f"{writer}: the rows written do not merge back to what it gave")
    return {f.master: master_text(out)}
def outputs_after(writer: str, old_rows: Iterable[Mapping[str, str]], files: Files | None = None,
                  master_rows: Iterable[Mapping[str, str]] = ()) -> dict[Path, str]:
    """outputs_after_rows for `old_rows`, old-form device-map rows each with the role its writer gives it (master_row
    gives each its master form), and
    `master_rows`, rows already in the master's form (a builder's staging rows, built on the owner's field rows, or
    rows the device maps leave out). What a reader of the master sees for these rows is what the writer gave; DevicesError
    when it is not."""
    f = files or Files.here()
    old_rows = list(old_rows)
    master_rows = [dict(r) for r in master_rows]
    new = [master_row(o, writer) for o in old_rows]
    out = outputs_after_rows(writer, new + master_rows, f)
    want = {(str(o["level"]), o["layer"], o["user_name"]): {c: str(o[c]) for c in DEVICE_COLUMNS} for o in old_rows}
    whole = {(r["level"], r["layer"], r["user_name"]): r for r in master_rows}
    back = {key_of(r): dict(r) for r in parse(out[f.master], f.master.name, f) if r["written_by"] == writer}
    held = {k: device_map_row(r) for k, r in back.items() if k not in whole}
    if held != want or any(back.get(k) != r for k, r in whole.items()):
        raise DevicesError(f"{writer}: the rows written do not read back as given")
    return out


def one_file_copy(path: Path, files: "Files | Path | str | None" = None) -> Path:
    """Write the merged view of the master (or of `files`) to `path` as a one-file master (no field file beside it:
    it holds every cell), for a test or a check that edits a copy row by row; the path written."""
    path = Path(path)
    if (path.parent / FIELD_FILE).exists():
        raise DevicesError(f"{path.parent}: a field file is there already, so {path.name} would merge with it")
    path.write_text(master_text(load(files)), encoding="utf-8")
    return path


def pair_copy(data: Path, files: "Files | Path | str | None" = None) -> Files:
    """Copy the master's two files and its dictionary (or `files`') into the folder `data` as they are; their
    Files there."""
    src, data = Files.of(files), Path(data)
    data.mkdir(parents=True, exist_ok=True)
    out = Files.under(data)
    for a, b in ((src.master, out.master), (src.field, out.field), (src.dictionary, out.dictionary)):
        if a is not None:
            b.write_bytes(a.read_bytes())
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
    converts to that form and back (a DevicesError otherwise, naming the row). A device not on the layout yet
    (is_unplaced: a Store's, with no level and no role) is on no device map, so it is left out as OUT_OF_MAPS is."""
    f = files or Files.here()
    rows = load(f)
    read_dictionary(f.dictionary)
    out = []
    for r in rows:
        if r["role"] in OUT_OF_MAPS or is_unplaced(r):
            continue
        try:
            master_row(dict(device_map_row(r), role=r["role"]), r["written_by"], r)
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
            for w in redundant(generated_rows(f), field_rows(f)):
                print(f"warning: {w}", file=sys.stderr)
            print(f"{f.master.name} with {f.field.name}: {len(load(f))} rows; its dictionary agrees")
        return 1 if problems else 0
    except DevicesError as exc:
        print(f"devices.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
