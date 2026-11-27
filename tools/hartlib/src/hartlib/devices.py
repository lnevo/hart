"""The device master for all three levels: devices_generated.csv and devices_field.csv, merged into one view.

The master holds one row per railroad device (ADR-029 and its amendment). It is two files under
jmri/layouts/hart/data: devices_generated.csv, every row the builders make (written by them alone, through
outputs_after), and devices_field.csv, the owner's cells, each row keyed by its device ID on its level (KEY: level,
id; ADR-033) and holding its layer and FIELD_COLUMNS only (the user name is an owner's cell like the rest), plus
the level-less devices a Store split takes in (full rows, keyed by layer and user name). load() and index() merge them
(merge: a non-empty field cell wins; a field row whose ID no generated row has is an error), so readers see one
master. A builder reads the owner's cells from field_index(), never back from its own last output; the one
read-back it makes is its name memory (allocated_names). Before the split the master was one file, devices.csv.
Staging, main and upper are one structure; a level differs only in column values. devices.columns.csv describes every
column, and a test holds the two files to each other both ways. Every reader gets its rows from the master (load,
device_map_lines below); a cp cell holds place ids, which readers see as names (hartlib.places). The two device maps,
the public name map and its six pnm_ columns are gone (R9e, ADR-029): their facts are in the master's own columns.

The master's values.
- level 1 staging, 2 main, 3 upper. layer: turnout, fb, block, occupancy, mast, head, sensor.
- assignment: field (the physical device is in JMRI: jmri_name is system_name), virtual (an internal stand-in; the
  system_name, if any, is the planned device), none (no JMRI name from this row), spare (a detector with no block).
- role: what the device is (ROLES). Readers test it, never a name prefix.
- cats_discipline: a field cell of the block rows the CATS desks bind, one of CATS_DISCIPLINES (CTC, YARD); empty
  elsewhere. hartlib.occupancy_bindings reads it.
- id: the device's key from the plan, not its name (hartlib.device_ids, ADR-033): a generated column, set on every
  row with a level and unique on its level; empty on a Store's level-less row. Every field row with a level is keyed
  by it (KEY), so a rename touches no key; the name store (hartlib.track_names) reads a field block row's name by it.
- user_name: the generated file names every row; a field row's user_name is the owner's name, which the merged view
  shows. A builder gives it as the row's name (staging's builders take it from the field row), and a write that
  renames a device lists the Operations Pro copies of the old name and warns on a mast (hartlib.device_changes).
- written_by: the script that writes the row, one of WRITERS (the one place a later merge of builders changes);
  every row with a level has one, and only a Store's level-less device (the field file's) has none. A writer
  replaces only the rows that carry its name (outputs_after_rows), stops on a key another writer or a Store's device
  holds, and cannot drop a key the field file names (merge: rename or remove the field row).

Row order is level, layer (LAYERS), then the writer (WRITERS order; a Store's level-less rows after every level),
then the order the writer gave, so a rebuild changes only its own rows and `check` can hold each file to it. The
main and upper block numbers (hartlib.block_numbering, written into the rows by build_device_map.py) and the mast
numbers are set by their writers, not here.

    python3 -m hartlib.devices check         # the master and its dictionary are valid

Every failure is a FactsError naming the file and row (DevicesError is the same class, the name its callers catch).
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
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Literal, get_args

from . import level_devices, names, paths, places
from .levels import LevelText

if TYPE_CHECKING:
    from . import device_changes as device_changes_mod
from .device_rows import row_cells
from .railroad_facts import DEVICE_COLUMNS, DEVICE_LIST, MASTER_COLUMNS, NAME_LAYERS, MasterRow, FactsError

# The one place the master's file names and paths are written (T6a): every other module asks for them here, and
# tools/hartlib/tests/test_devices_one_path.py fails on any tracked .py outside hartlib that names a file itself.
# MASTER is the generated file, a reader's handle on the pair: load(MASTER) merges the field file beside it.
GENERATED_FILE = "devices_generated.csv"     # every row the builders make (WRITERS), written by them alone
FIELD_FILE = "devices_field.csv"             # the owner's cells, keyed by KEY, and the Store's level-less devices
MASTER_FILE = GENERATED_FILE
ONE_FILE = "devices.csv"                     # the one-file master's name: a test's or a check's copy (one_file_copy)
MASTER = paths.LAYOUT_DATA / MASTER_FILE
FIELD = paths.LAYOUT_DATA / FIELD_FILE

LEVELS: tuple[LevelText, ...] = ("1", "2", "3")   # the master's level column: text (hartlib.levels)
Layer = Literal["turnout", "fb", "block", "occupancy", "mast", "head", "sensor"]
LAYERS: tuple[Layer, ...] = get_args(Layer)       # also the order within a level
Assignment = Literal["field", "virtual", "none", "spare"]
ASSIGNMENTS: tuple[Assignment, ...] = get_args(Assignment)
# the roles of a line block (and its occupancy sensor): a block between switches, whose cp is a list of the places it
# joins (build_device_map.line_cp); every other device sits in one control point at most
LINE_ROLES = ("track", "helix", "part", "loop_half", "spur")
# the roles of a block through a switch's points (and its occupancy sensor): an OS block, or a corner of a double
# crossover; readers test these (is_os, Index.is_os), never an "OS Switch " prefix
OS_ROLES = ("os", "xover_corner")
Role = Literal["turnout", "lcc_alias", "fb", "os", "xover_corner", "track", "spur", "loop_half", "helix",
               "home", "intermediate", "hidden", "head", "spare", "panel_status", "part"]
ROLES: tuple[Role, ...] = get_args(Role)
# The scripts that write rows (the one list: a merge of builders changes only this; build_device_map.py writes
# every level's mast and head rows). Order is the order of rows
# within a (level, layer) after the hand-kept ones.
WRITERS = ("build_device_map.py", "panel_items.json")
# roles the two device maps leave out: a spare detector, a panel status bean, and a part (a block row with part_of: a
# piece of track inside another block: a JMRI block on its block's occupancy sensor, built by its level's builder, with
# no occupancy row or detector of its own)
OUT_OF_MAPS = ("spare", "panel_status", "part")
# internal names: a virtual device. level_devices.BLOCK_PREFIX: a main or upper block (hartlib.block_numbering)
SOURCE_PREFIXES = ("IT:HART:", "IS:HART:", "IH:HART:", "IB:HART:", level_devices.BLOCK_PREFIX)

COLUMNS = MASTER_COLUMNS        # the file's header, in order (railroad_facts.MasterRow holds a row of them)
# The CATS disciplines a block row's cats_discipline may hold (owner's cell; hartlib.occupancy_bindings gives the
# CATS desk builders the blocks that have one)
CATS_DISCIPLINES = ("CTC", "YARD")
# A row's start: its bean's state when the tables load, by layer (hartlib.level_devices.START_ENUM gives the JMRI
# word); empty where JMRI's default stands
START = {"occupancy": ("inactive",), "turnout": ("closed", "thrown")}
# A field row's key (ADR-033): its device ID on its level, so a rename changes no key. A Store's level-less row
# has no ID and is keyed by ("", layer, user_name) instead (key_of). NAME_KEY is unique in the merged view too, and is
# how a message names a row (row_text).
KEY = ("level", "id")
RowKey = tuple[str, str] | tuple[str, str, str]    # key_of: (level, id), or ("", layer, user name) when level-less
NAME_KEY = ("level", "layer", "user_name")
# The columns of a keyed field row (the owner's cells, ADR-029's amendment): the cells a builder took from
# the master's previous rows before the split, so the owner's value lives in one place. On every level the builder
# makes each device's row from the plan and puts its field row's cells over it: a device with no
# field row keeps the generated values.
FIELD_COLUMNS = ("user_name", "role", "assignment", "cp", "system_name", "jmri_name", "node", "dcc", "jmri_comment",
                 "trial_name", "notes", "detector", "stop", "layout_block", "cats_discipline")
# A field row with a level also holds its layer, which must be its generated row's (merge checks it): it orders the
# file and tells a reader what the row is.
FIELD_HELD = ("layer",)
# In a field jmri_comment, where the builder puts the detector's wiring.csv text ("occupancy Block 4-2 / M2S401"): the
# owner keeps the words around it, wiring.csv the pin, so a moved pin changes no hand file. The merged cell is the
# generated one, which must be the field text with the mark filled in (merge checks it).
OCCUPANCY_MARK = "{occupancy}"
OCCUPANCY_TEXT = r"occupancy Block \d+-\d+ / M2S\d+"
LIST = DEVICE_LIST              # the separator of a list column (blocks, protects, a line block's cp)
place = places.of               # a row's place by name: its cp, a turnout's from the switch lists (it has no cp)
# the columns an old-form device-map row shares with the master; its comment is built, the rest of the master is left out
_SHARED = tuple(c for c in DEVICE_COLUMNS if c not in ("comment",))

# A turnout row's id by its role (hartlib.device_ids.switch_id, dcc_id): the switch number it names, with no leading
# zero, so places.of finds its switch in the lists (places.SWITCH_ID matches both forms)
TURNOUT_IDS = {"turnout": re.compile(r"switch:[1-9]\d*"), "lcc_alias": re.compile(r"dcc:[1-9]\d*")}

_NODE_TEXT = re.compile(r"Node: \d+")
_WIRED_HEAD = re.compile(r"\(IH\d+\)")


# The master or its dictionary cannot stand as it is, or a write would break it: a facts problem like any other, so
# the one error type of the facts readers (railroad_facts.FactsError). The name stays for the callers that catch it;
# `except DevicesError` and `except FactsError` catch the same faults, those of hartlib.places among them.
DevicesError = FactsError


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
        """The Files a reader's `source` names: None the repo's, a Files itself, or a master's path. A path named
        devices_generated.csv is one of a pair: DevicesError when devices_field.csv is not beside it. A path of any
        other name is a one-file copy (a test's or a check's, one_file_copy), which holds every cell."""
        if source is None:
            return Files.here()
        if isinstance(source, Files):
            return source
        path = Path(source)
        beside = path.parent / FIELD_FILE
        if path.name == GENERATED_FILE:
            if not beside.is_file():
                raise DevicesError(f"{path}: {FIELD_FILE} is missing beside it (the master is the pair; a one-file "
                                   f"copy has another name, such as {ONE_FILE})")
            return Files(path, path.parent / "devices.columns.csv", beside)
        return Files(path, path.parent / "devices.columns.csv", None)

    def but(self, **changes: Any) -> "Files":     # dataclasses.replace's keyword arguments: field names
        return replace(self, **changes)


# ---------------------------------------------------------------- reading

def places_of(source: "Files | Path | str | None" = None) -> places.Table:
    """The places a master's cp cells are read and written by: those of the stations.csv and interlockings.csv beside
    `source` (places.lists_beside: a copy's own lists), else the repo's."""
    return places.table(places.lists_beside(source))


@lru_cache(maxsize=16)
def _read(name: str, data: bytes, table: places.Table) -> tuple[Mapping[str, str], ...]:
    """The rows of one file's bytes (the generated or the field file: one header), cp cells named by `table`
    (places_of). Cached on the bytes themselves and the Table (one per content of the two lists), so a write of the
    same size in the same clock tick, or a changed list, can never return stale rows."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DevicesError(f"{name}: not UTF-8 text ({exc.reason} at byte {exc.start})") from exc
    reader = csv.reader(io.StringIO(text, newline=""))
    header = next(reader, None)
    if header is None or tuple(header) != COLUMNS:
        raise DevicesError(f"{name}: the header is not the master's columns ({', '.join(COLUMNS)}); got {header}")
    rows = []
    for line, fields in enumerate(reader, 2):
        if len(fields) != len(COLUMNS):
            raise DevicesError(f"{name} line {line}: {len(fields)} fields, expected {len(COLUMNS)}")
        rows.append(MappingProxyType(table.with_names(dict(zip(COLUMNS, fields)), f"{name} line {line}")))
    return tuple(rows)


def key_of(row: MasterRow | Mapping[str, str]) -> RowKey:
    """A row's (a MasterRow's, or a row of the master's text) key in both files: (level, id) (KEY) for a row with a
    level, ("", layer, user name) for a Store's level-less row, which has no id."""
    r = row_cells(row)
    return (r["level"], r["id"]) if r["level"] else ("", r["layer"], r["user_name"])


def name_key(row: MasterRow | Mapping[str, str]) -> tuple[str, str, str]:
    """A row's name key (NAME_KEY): level, layer, user name; unique in the merged view."""
    r = row_cells(row)
    return (r["level"], r["layer"], r["user_name"])


def key_text(key: tuple[str, ...]) -> str:
    """A key as a message names it: a name key "Track 12 (level 1, block)", or "X (no level, turnout)" for a Store's
    device; an ID key (KEY) "id 'os:19' (level 1)"."""
    if len(key) == 2:
        return f"id {key[1]!r} (level {key[0]})"
    level, layer, name = key
    return f"{name} ({'level ' + level if level else 'no level'}, {layer})"


def row_text(row: MasterRow | Mapping[str, str]) -> str:
    """A row as a message names it: its name key's text (key_text), "Track 12 (level 1, block)"."""
    return key_text(name_key(row))


def check_field(rows: Iterable[Mapping[str, str]], name: str = FIELD_FILE) -> None:
    """The field file's own rules: no writer; a keyed row (one with a level) holds its key (level, id), its layer
    and FIELD_COLUMNS cells only; a key once; rows in level and layer order. A level-less row (a Store's device) is a
    full row, which check_rows holds on the merged view. DevicesError listing every problem."""
    bad, seen, ranks = [], set(), []
    for r in rows:
        k = key_of(r)
        at = f"{name}: {row_text(r)}"
        if r["written_by"]:
            bad.append(f"{at}: written_by {r['written_by']!r}; a field row has no writer (the builders write "
                       f"{GENERATED_FILE})")
        if r["level"]:
            extra = [c for c in COLUMNS if c not in KEY + FIELD_HELD + FIELD_COLUMNS and r[c]]
            if extra:
                bad.append(f"{at}: {', '.join(extra)} set; a field row holds only its key ({', '.join(KEY)}), "
                           f"layer and {', '.join(FIELD_COLUMNS)} (the builders make the rest)")
            if not r["id"].strip():
                bad.append(f"{at}: id is empty; a field row is keyed by its device's id on its level (the id of its "
                           f"row in {GENERATED_FILE}, hartlib.device_ids)")
        if k in seen:
            bad.append(f"{at}: the key is twice in the file ({key_text(k)})")
        seen.add(k)
        if r["layer"] not in LAYERS or (r["level"] and r["level"] not in LEVELS):
            bad.append(f"{at}: level is one of {', '.join(LEVELS)} or empty, layer one of {', '.join(LAYERS)}")
        elif not r["written_by"]:               # a writer's row is refused above, and has no place here
            ranks.append((row_rank(r), row_text(r)))
    for (a, ka), (b, kb) in zip(ranks, ranks[1:]):
        if b < a:
            bad.append(f"{name}: {kb} is out of order (level, then layer); it follows {ka}")
            break
    if bad:
        raise DevicesError("; ".join(bad))


def check_generated(rows: Iterable[Mapping[str, str]], name: str = GENERATED_FILE) -> None:
    """The generated file's own rules: every row has a level and a writer of WRITERS (a Store's level-less device is
    the field file's). DevicesError listing every problem."""
    bad = []
    for r in rows:
        at = f"{name}: {row_text(r)}"
        if not r["level"]:
            bad.append(f"{at}: a level-less device (a Store's) is kept in {FIELD_FILE}")
        elif r["written_by"] not in WRITERS:
            bad.append(f"{at}: written_by {r['written_by']!r} is not one of {', '.join(WRITERS)} (the owner's "
                       f"cells go in {FIELD_FILE})")
    if bad:
        raise DevicesError("; ".join(bad))


def is_templated(field_cell: str, generated_cell: str) -> bool:
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
    devices), in the master's order (row_rank), checked (check_rows). Rows are matched by KEY (level, id), so a field
    user_name is the owner's name over the generated one. A field jmri_comment with OCCUPANCY_MARK is the builder's to
    fill: the generated cell stands, and must be the field text with the mark filled in. DevicesError on a field cell
    outside FIELD_COLUMNS, a field row whose id no generated row has (the plan no longer has that device: the owner
    moves its cells to the device's new id or drops them, decision 3 of the naming-layers hand-off), a field row of
    another layer than its id's row, a templated comment the generated cell does not follow, or a merged row that
    breaks check_rows."""
    gname, fname = names
    field, generated = list(field), list(generated)
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
        if f["layer"] != g["layer"]:
            bad.append(f"{fname}: {row_text(f)}: id {k[1]!r} is a {g['layer']} row in {gname}, not {f['layer']}")
            continue
        row = dict(g)
        for c in FIELD_COLUMNS:
            v = f[c]
            if not v:
                continue
            if c == "jmri_comment" and OCCUPANCY_MARK in v:
                if not is_templated(v, g[c]):
                    bad.append(f"{fname}: {row_text(f)}: jmri_comment {v!r} needs its {OCCUPANCY_MARK} filled from "
                               f"wiring.csv, but {gname} has {g[c]!r} (run make panels)")
                continue
            row[c] = v
        out.append(MappingProxyType(row))
    bad += [gone_text(f, gname, fname) for k, f in keyed.items() if k not in used]
    if bad:
        raise DevicesError("; ".join(bad))
    out = follow_renames(out, generated)
    out += [r for r in field if not r["level"]]
    out.sort(key=row_rank)
    rows = tuple(out)
    check_rows(rows, f"{gname} with {fname}")
    return rows


# The generated columns that name another row's block by its user name: a rename in the field file reaches them in
# the merged view at once, before a builder writes them again.
BLOCK_REFS = ("part_of", "blocks", "facing", "protects")


def follow_renames(rows: list[Mapping[str, str]], generated: Iterable[Mapping[str, str]]) -> list[Mapping[str, str]]:
    """`rows` (merged) with each block named in BLOCK_REFS by the name the merged view gives it: where the owner's
    name (a field user_name) replaced a block's generated name, a part's part_of, a detector's blocks and a mast's
    facing and protects that name the block follow it. A reference names a block on its own level first; one that
    names no block of its level (a main or upper mast facing a helix block of another level) follows the block's
    rename on the one other level whose block had that name, by the block's id, unless another level still has a
    block of that name. So a rename leaves the view consistent (no part of a block that is no row) and a reader takes
    the new name everywhere. Rows with no rename to follow are returned as they are."""
    renamed: dict[str, dict[str, str]] = {}
    new = {(r["level"], r["id"]): r["user_name"] for r in rows if r["level"] and r["layer"] == "block"}
    for g in generated:
        if g["level"] and g["layer"] == "block":
            now = new.get((g["level"], g["id"]))
            if now is not None and now != g["user_name"]:
                renamed.setdefault(g["level"], {})[g["user_name"]] = now
    if not renamed:
        return rows
    on_level: dict[str, set[str]] = {}
    for (level, _id), name in new.items():
        on_level.setdefault(level, set()).add(name)
    kept = {n for names in on_level.values() for n in names}          # names some block still has after the merge
    elsewhere: dict[str, list[str]] = {}
    for level, mine in renamed.items():
        for old, now in mine.items():
            elsewhere.setdefault(old, []).append(now)

    def follow(level: str, b: str) -> str:
        mine = renamed.get(level, {})
        if b in mine:
            return mine[b]
        if b in on_level.get(level, ()) or b in kept:
            return b
        hits = elsewhere.get(b, [])
        return hits[0] if len(hits) == 1 else b

    out = []
    for r in rows:
        cells = {c: LIST.join(follow(r["level"], b) for b in r[c].split(LIST)) for c in BLOCK_REFS if r[c]}
        changed = {c: v for c, v in cells.items() if v != r[c]}
        out.append(MappingProxyType({**r, **changed}) if changed else r)
    return out


def gone_text(f: Mapping[str, str], gname: str = GENERATED_FILE, fname: str = FIELD_FILE) -> str:
    """What merge says of field row `f` whose id no generated row has (decision 3: stop and list it)."""
    return (f"{fname}: {row_text(f)}: id {f['id']!r} has no row in {gname} (the plan no longer has it): move the "
            "row's cells to the device's new id, or remove the row")


def redundant(generated: Iterable[Mapping[str, str]], field: Iterable[Mapping[str, str]]) -> list[str]:
    """Warnings: each field cell equal to the generated cell it overrides (the value would be in two places). A
    user_name is left out: the generated file names every row, so the owner's name is in both on purpose."""
    keyed = {key_of(r): r for r in field if r["level"]}
    out = []
    for g in generated:
        f = keyed.get(key_of(g))
        if f is not None:
            out += [f"{FIELD_FILE}: {row_text(g)}: {c} {f[c]!r} is the generated value too (redundant)"
                    for c in FIELD_COLUMNS if c != "user_name" and f[c] and f[c] == g[c]]
    return out


def unmerge(rows: Iterable[Mapping[str, str]], field: Iterable[Mapping[str, str]],
            writer: str = "the builder") -> list[dict[str, str]]:
    """The generated form of merged rows `rows` (a builder's rows, as readers will see them), matched to the field
    file by KEY (level, id): each row's cells the field file gives are left empty, so the owner's value lives in one
    place; a templated comment (OCCUPANCY_MARK) stays, as the builder fills it, and so does the user_name (the
    generated file names every row). Level-less rows (the field file's own) are left out. DevicesError when a row
    gives a field cell a value other than the field file's (the builder would override the owner; for a user_name,
    the builder does not take the owner's name for that device)."""
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
                if c == "user_name":        # kept: the builder gives the owner's name, as readers see it
                    if row[c] != v:
                        bad.append(f"{writer} names id {row['id']!r} (level {row['level']}, {row['layer']}) "
                                   f"{row[c]!r}, but {FIELD_FILE} names it {v!r}: {writer} does not take the owner's "
                                   "name for this device; remove the field row's user_name to keep the generated one")
                    continue
                if c == "jmri_comment" and OCCUPANCY_MARK in v:
                    if not is_templated(v, row[c]):
                        bad.append(f"{writer} gives {row_text(r)} jmri_comment {row[c]!r}, which is not "
                                   f"{FIELD_FILE}'s {v!r} with its {OCCUPANCY_MARK} filled")
                elif row[c] != v:
                    bad.append(f"{writer} gives {row_text(r)} {c} {row[c]!r}, but {FIELD_FILE} holds {v!r}")
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
        raise DevicesError(f"{path}: cannot read it ({exc.strerror})") from exc
    return _read(path.name, data, places_of(path))


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


def field_index(files: "Files | Path | str | None" = None) -> Mapping[tuple[str, ...], Mapping[str, str]]:
    """{(level, id): field row} of the field file's keyed rows (those with a level, KEY): the owner's cells, the one
    place a builder reads them from (it never reads them back from its own last output)."""
    return MappingProxyType({key_of(r): r for r in field_rows(files) if r["level"]})


@lru_cache(maxsize=8)
def _merged(gname: str, gdata: bytes, fname: str | None, fdata: bytes | None, table: places.Table
            ) -> tuple[MasterRow, ...]:
    generated = _read(gname, gdata, table)
    (check_rows if fname is None else check_generated)(generated, gname)    # a one-file copy holds every cell
    return as_device_rows(generated if fname is None else merge(generated, _read(fname, fdata, table), (gname, fname)),
                          gname)


def as_device_rows(rows: Iterable[Mapping[str, str]], name: str = MASTER_FILE) -> tuple[MasterRow, ...]:
    """Checked rows of the merged view as DeviceRow (MasterRow for a Store's level-less row), at their place in it."""
    return tuple(MasterRow.from_master(r, n, f"{name} row {n} ({row_text(r)})") for n, r in enumerate(rows, 2))


def _field_bytes(f: "Files") -> bytes:
    if f.field is None:
        raise DevicesError(f"{f.master}: a one-file copy has no field file")
    try:
        return f.field.read_bytes()
    except OSError as exc:
        raise DevicesError(f"{f.field}: cannot read it ({exc.strerror})") from exc


def parse(text: str, name: str = MASTER_FILE, files: "Files | None" = None) -> tuple[MasterRow, ...]:
    """The merged rows of a generated file's text (one outputs_after gives, before it is written) with `files`'
    field file (none, or a Files with no field file: the text holds every cell), checked as load checks the files.
    DevicesError naming the file on any problem."""
    table = places_of(files)
    if files is None or files.field is None:
        return _merged(name, text.encode("utf-8"), None, None, table)
    return _merged(name, text.encode("utf-8"), files.field.name, _field_bytes(files), table)


def load(files: "Files | Path | str | None" = None) -> tuple[MasterRow, ...]:
    """The master's rows (DeviceRow; MasterRow for a Store's level-less one): the generated file merged with the field
    file (merge), checked (check_rows). Read once per state of the two files: the merge is cached on both files' bytes, so every reader of
    one run shares it and a changed file is always read again. `files` is the Files of a copy, or a master's path
    (Files.of). A bad row ANYWHERE stops the load (check_rows names its key and file); there is no way round it.
    DevicesError on any problem."""
    f = Files.of(files)
    try:
        gdata = f.master.read_bytes()
    except OSError as exc:
        raise DevicesError(f"{f.master}: cannot read it ({exc.strerror})") from exc
    table = places_of(f)
    if f.field is None:
        return _merged(f.master.name, gdata, None, None, table)
    return _merged(f.master.name, gdata, f.field.name, _field_bytes(f), table)


def device_map_lines(levels: tuple[str, ...], source: "Files | Path | str | None" = None
                     ) -> list[tuple[int, dict[str, str]]]:
    """(place in the merged view, device-map row; a message names it by at(), never the number) of each row of `levels` outside OUT_OF_MAPS, in master order: the rows the
    old device map of those levels held, in its form plus `role`, a turnout's cp its place. The one way a reader gets them."""
    lists = places.lists_beside(source)        # a copy's turnouts take the copy's switch lists
    return [(r.line, {**device_map_row(r), "cp": place(r, lists), "role": r.role}) for r in load(source)
            if r.level_cell in levels and r.role not in OUT_OF_MAPS]


def user_names(source: "Files | Path | str | None" = None) -> Mapping[tuple[str, str], str]:
    """{(level, id): user name} of every row with a level, from the merged view (the owner's name wins): the name
    store's answer for a device ID. The data files keyed by ID (wiring.csv, block_lengths.csv, block_numbering.csv,
    block_overrides.csv, mast_cells.csv) read their names here, so a rename in the field file
    reaches them with no row of theirs changed."""
    return MappingProxyType({(r.level_cell, r.id): r.user_name for r in load(source) if r.level and r.id})


def name_of(names: Mapping[tuple[str, str], str], level: str, ident: str, where: str) -> str:
    """The user name of device `ident` on `level` in `names` (user_names). DevicesError naming `where` (a file and
    line) when the device master has no such device: an ID the plan no longer has (decision 3: the owner moves the
    row to the new ID or drops it)."""
    try:
        return names[(str(level), ident)]
    except KeyError as exc:
        raise DevicesError(f"{where}: {ident} is no level {level} device of the device master (a new export dropped "
                           "it, or the ID is mistyped: give the device's id column)") from exc


def part_lines(levels: tuple[str, ...], source: "Files | Path | str | None" = None
               ) -> list[tuple[int, dict[str, str]]]:
    """(line of the master, row) of each part of `levels` (role part: a piece of track inside another block, part_of
    naming it), which the device maps leave out (OUT_OF_MAPS), in master order."""
    return [(r.line, r.cells()) for r in load(source) if r.level_cell in levels and r.role == "part"]


# ---------------------------------------------------------------- a device's kind, from its row

def row_role(row: MasterRow | Mapping[str, str], where: str = "the device master") -> str:
    """The role column of `row` (ROLES). DevicesError naming `where` (a file and line, else "the device master") and
    the row when its role is missing or empty: a reader asks the row what a device is, not its name (hand-off row 8)."""
    role = (cells := row_cells(row)).get("role", "")
    if not role:
        raise DevicesError(f"{where}: {cells.get('layer', '?')} {cells.get('user_name', '?')!r} has no role "
                           f"(one of {', '.join(ROLES)})")
    return role


def is_os(row: MasterRow | Mapping[str, str], where: str = "the device master") -> bool:
    """Whether a block or occupancy row is the block through a switch's points (OS_ROLES), by its role."""
    return row_role(row, where) in OS_ROLES


@dataclass(frozen=True)
class Index:
    """The master's rows by (layer, user name), each with its place in the merged view (an id, never a file line: the
    view is two files): the one lookup for a reader that holds a device's name and needs its row's facts (role,
    level, layer). Messages name a row by where(): its key and the file that holds the owner's cells or the
    builder's. Built by index()."""
    path: Path
    by_key: Mapping[tuple[str, str], tuple[tuple[int, MasterRow], ...]]
    lines: tuple[tuple[int, MasterRow], ...]
    field_keys: frozenset = frozenset()          # the keys devices_field.csv has a row of

    def rows(self, layer: str, name: str) -> tuple[tuple[int, MasterRow], ...]:
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
        roles = {row_role(r, self.where(r)) for _n, r in got}
        if len(roles) != 1:
            raise DevicesError(f"{'; '.join(self.where(r) for _n, r in got)}: {layer} {name!r} has "
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

    def where(self, row: MasterRow | Mapping[str, str]) -> str:
        """"devices_field.csv: Track 12 (level 1, block)" for the master's row with `row`'s name key, for a message:
        the field file when it has a row of that row's key (the owner's cells), else the generated file; the generated
        file's name alone when the master has no such row (a caller's own row, as in a test)."""
        k = tuple(row_cells(row).get(c, "") for c in NAME_KEY)
        got = [r for _n, r in self.by_key.get((k[1], k[2]), ()) if r.level_cell == k[0]]   # k is text
        if not got:
            return self.path.name
        return f"{FIELD_FILE if key_of(got[0]) in self.field_keys else self.path.name}: {key_text(k)}"

    def names(self, layer: str, roles: Iterable[str] | None = None, levels: Iterable[str] | None = None
              ) -> list[str]:
        """The user names of the `layer` rows (of `roles` and `levels` when given), in master order, each once. With
        `roles`, a device not on the layout yet (is_unplaced: it has no role) is left out."""
        roles = None if roles is None else frozenset(roles)
        levels = None if levels is None else frozenset(levels)
        out: dict[str, None] = {}
        for n, r in self.lines:
            if r.layer != layer or (levels is not None and r.level_cell not in levels):
                continue
            if roles is not None and (r.level is None or r.role not in roles):    # a row with a level has its role
                continue
            out.setdefault(r.user_name, None)
        return list(out)


_INDEXES: dict[int, tuple[tuple[MasterRow, ...], Index]] = {}


def index(files: "Files | Path | str | None" = None) -> Index:
    """The Index of the master (or of `files`, a copy), built once per file state: load() returns the same rows for
    the same bytes, and the index is kept with them."""
    path = Files.of(files).master
    rows = load(files)
    kept = _INDEXES.get(id(rows))
    if kept is not None and kept[0] is rows and kept[1].path == path:
        return kept[1]
    lines = tuple((r.line, r) for r in rows)
    by_key: dict[tuple[str, str], list[tuple[int, MasterRow]]] = {}
    for n, r in lines:
        by_key.setdefault((r.layer, r.user_name), []).append((n, r))
    out = Index(path, MappingProxyType({k: tuple(v) for k, v in by_key.items()}), lines,
                frozenset(key_of(r) for r in field_rows(files)))
    _INDEXES[id(rows)] = (rows, out)
    while len(_INDEXES) > 8:                    # as many file states as _read keeps
        del _INDEXES[next(iter(_INDEXES))]
    return out


def column_file(column: str) -> str:
    """Which file may hold `column` on a row with a level: "field" for the key and FIELD_COLUMNS (the owner's cell
    in devices_field.csv when the row has a field row, else the builder's), "generated" for the rest (the builders'
    alone). A Store's level-less row holds every column in the field file."""
    return "field" if column in KEY + FIELD_HELD + FIELD_COLUMNS else "generated"


def at(row: MasterRow | Mapping[str, str], files: "Files | Path | str | None" = None) -> str:
    """Where a master row is, for a message: "devices_field.csv: Track 12 (level 1, block)" (Index.where)."""
    return index(files).where(row)


def read_dictionary(path: Path) -> dict[str, str]:
    """{column: description} of devices.columns.csv; DevicesError unless the header is column,file,description (with or
    without check_data.py's rule columns), every master column once, each described, and its file column_file's."""
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
    except OSError as exc:
        raise DevicesError(f"{path}: cannot read it ({exc.strerror})") from exc
    if ",".join(next(iter(rows), [])) not in ((head := "column,file,description"), head + ",type,required,key,refs,values"):
        raise DevicesError(f"{path.name}: the header is {head}, alone or with type,required,key,refs,values")
    out, bad = {}, []
    for line, r in enumerate(rows[1:], 2):
        if len(r) != len(rows[0]):
            bad.append(f"line {line}: {len(r)} fields, expected {len(rows[0])}")
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

def row_rank(row: Mapping[str, str]) -> tuple[int, int, int]:
    """A row's place: by level (a level-less row after every level), layer, then hand-kept rows before each writer's."""
    writer = row["written_by"]
    level = LEVELS.index(row["level"]) if row["level"] else len(LEVELS)
    return (level, LAYERS.index(row["layer"]), 0 if not writer else 1 + WRITERS.index(writer))


def cp_list(row: Mapping[str, str]) -> list[str]:
    """The places a row's cp names: one control point, or, for a line block (LINE_ROLES) and its sensor, the stations
    or control points it joins (LIST separated); [] when it has none."""
    return [p for p in row["cp"].split(LIST) if p]


def is_unplaced(row: MasterRow | Mapping[str, str]) -> bool:
    """A device not on the layout yet: added in PanelPro, kept as its Store beans in jmri_bean, with no level until the
    owner gives its details."""
    return row.level is None if isinstance(row, MasterRow) else not row["level"]


def _unplaced_problems(r: Mapping[str, str]) -> list[str]:
    """What a level-less row breaks: it carries its beans (jmri_bean), is a field device by its own system name, and
    has no cp, role, writer or other level's facts."""
    from . import jmri_bean, tables, tables_sections          # jmri_bean reads this module's rows
    bad = []
    if not r["jmri_bean"]:
        return ["level is one of " + ", ".join(LEVELS) + ", or empty for a device kept by its jmri_bean"]
    if r["assignment"] != "field" or not r["jmri_name"] or r["system_name"] != r["jmri_name"]:
        bad.append("a level-less device is assignment field with system_name equal to jmri_name")
    set_cols = [c for c in ("cp", "role", "id", "written_by", "wiring", "part_of", "blocks", "detector", "stop", "switch",
                            "facing", "protects", "dir", "cats_discipline") if r[c]]
    if set_cols:
        bad.append(f"a level-less device has no {', '.join(set_cols)} (they come with its level)")
    try:
        beans = jmri_bean.row_beans(r)
    except tables_sections.TablesBuildError as exc:
        return bad + [str(exc).split(": ", 2)[-1]]
    names = {tables.system_name(el) for _, el in beans}
    own = {r["jmri_name"], r["layout_block"]} - {""}
    if r["jmri_name"] not in names:
        bad.append(f"jmri_bean holds no bean named {r['jmri_name']!r}")
    if names - own:
        bad.append(f"jmri_bean holds beans of other names ({', '.join(sorted(names - own))})")
    return bad


def check_rows(rows: Iterable[Mapping[str, str]], where: str = "the device master") -> None:
    """The master's invariants; DevicesError listing every problem (a row is named by its key: name, level and
    layer, never a line, as the merged view is two files). Run on every load and after every write. The steps are in
    hartlib.device_row_checks."""
    from . import device_row_checks             # it reads this module
    device_row_checks.check_rows(rows, where)


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
    at = f" at {place(r)}" if place(r) else ""
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


def comment_of(row: MasterRow | Mapping[str, str]) -> str:
    """The JMRI comment of a master row: jmri_comment, else wiring, with the DCC group put in as the JMRI comment has
    it for a field turnout (hartlib.names.jmri_comment). The one place a reader gets a row's comment."""
    r = row_cells(row)
    return r["jmri_comment"] or (names.jmri_comment(r["wiring"], r["dcc"]) if _carries_dcc(r) else r["wiring"])


def device_map_row(row: MasterRow | Mapping[str, str]) -> dict[str, str]:
    """The old-form device-map row of a master row: its comment is comment_of's."""
    r = row_cells(row)
    return {c: (comment_of(r) if c == "comment" else r[c]) for c in DEVICE_COLUMNS}


def master_row(old: Mapping[str, str], writer: str, prior: Mapping[str, str] | None = None,
               description: str | None = None) -> dict[str, str]:
    """The master row of an old-form device-map row with its `role` (the writer states what each row is: no role is
    read off a name, hand-off row 8) and its `id` (hartlib.device_ids), which the old form does not hold. `prior` is the row it replaces, whose description a hand-kept row keeps.
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
    r["id"] = str(old.get("id") or "")        # the writer's (hartlib.device_ids); a device map has no id column
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
    would take an id or a name (key_of, name_key) a row held by someone else has (another writer's, or a Store's
    level-less device), or the result breaks check_rows. A row the field file names may not go: merge refuses the
    pair (move the field row to the new id or remove it), so the owner's cells are never dropped silently."""
    old_rows, new_rows = [dict(r) for r in rows], [dict(r) for r in new]
    _writes_only_its_own(writer, new_rows, [r for r in old_rows if r["written_by"] != writer])
    out = [r for r in old_rows if r["written_by"] != writer] + new_rows
    out.sort(key=row_rank)
    check_rows(out, f"the master after {writer}'s write")
    return out


def _writes_only_its_own(writer: str, new: Sequence[Mapping[str, str]], others: Iterable[Mapping[str, str]]) -> None:
    """DevicesError when `writer` is not in WRITERS, a row of `new` names another writer, or takes the key of a row of
    `others` (another writer's, or a Store's level-less device)."""
    if writer not in WRITERS:
        raise DevicesError(f"writer {writer!r} is not one of {', '.join(WRITERS)}")
    foreign = [r for r in new if r["written_by"] != writer]
    if foreign:
        raise DevicesError(f"{writer} would write {len(foreign)} row(s) held by someone else, first "
                           f"{foreign[0]['level']} {foreign[0]['layer']} {foreign[0]['user_name']!r} "
                           f"(written_by {foreign[0]['written_by']!r})")
    held = {k(r): r["written_by"] for r in others for k in (key_of, name_key)}     # by id and by name
    clash = [(r, held.get(name_key(r), held.get(key_of(r)))) for r in new if name_key(r) in held or key_of(r) in held]
    if clash:
        raise DevicesError(f"{writer} would rewrite row(s) it does not hold: "
                           + ", ".join(f"{r['user_name']!r} ({r['layer']}, level {r['level']}, id {r['id']!r}; held by "
                                       f"{by or FIELD_FILE})" for r, by in clash[:5]))


def _text(columns: Iterable[str], rows: Iterable[Mapping[str, str]], table: places.Table) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(columns), lineterminator="\n")
    w.writeheader()
    w.writerows(table.with_ids(rows))           # cp cells as place ids (hartlib.places)
    return buf.getvalue()


def master_text(rows: Iterable[Mapping[str, str]], files: "Files | Path | str | None" = None) -> str:
    """A master file's text of `rows`, cp cells as the ids of the lists beside `files` (places_of; the repo's when
    None), the lists it is read back by."""
    return _text(COLUMNS, rows, places_of(files))


def write_one_file(rows: Iterable[Mapping[str, str]], files: "Files | Path | str | None" = None) -> Path:
    """Write `rows` as a one-file master: a test's or a check's copy with no field file beside it, which holds every
    cell; the path written. The repo's pair is written by write_generated and write_field alone."""
    f = Files.of(files)
    if f.field is not None:
        raise DevicesError(f"{f.master.name} has a field file beside it; write the pair (write_generated, write_field)")
    path = f.master
    path.write_text(master_text(rows, f), encoding="utf-8")
    return path


def write_generated(rows: Iterable[Mapping[str, str]], files: "Files | Path | str | None" = None) -> Path:
    """Write `rows` (generated rows: field cells empty) as the generated file, once it checks on its own and merged
    with the field file; the path written. With write_field, the one writer of the pair's text."""
    f = Files.of(files)
    rows = [dict(r) for r in rows]
    check_generated(rows, f.master.name)
    merge(rows, field_rows(f), (f.master.name, f.field.name if f.field else FIELD_FILE))
    f.master.write_text(master_text(rows, f), encoding="utf-8")
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
    f.field.write_text(master_text(rows, f), encoding="utf-8")
    return f.field


def device_map_rows(rows: Iterable[Mapping[str, str]], levels: tuple[str, ...]) -> list[dict[str, str]]:
    """The old-form rows of a device map: those of `levels` outside OUT_OF_MAPS, in master order."""
    return [device_map_row(r) for r in rows if r["level"] in levels and r["role"] not in OUT_OF_MAPS]


def texts(rows: Sequence[Mapping[str, str]], files: Files | None = None) -> dict[Path, str]:
    """{path: text} of the generated file from merged rows `rows` (unmerge: the field file's cells left out)."""
    f = files or Files.here()
    return {f.master: master_text(unmerge(rows, field_rows(f)) if f.field is not None else rows, f)}


def outputs_after_rows(writer: str, new: Iterable[Mapping[str, str]], files: Files | None = None,
                       warn: "Callable[[str], None] | None" = None, check: bool = False) -> dict[Path, str]:
    """{path: text} of the generated file once `writer` has written `new`, its rows as readers will see them (merged
    form, written_by set to it), in place of the rows it holds (replace_rows on the merged view). The writer's rows
    go in with the field file's cells left empty (unmerge); every other writer's generated row is kept as written.
    Once the result has merged back, the write's new and gone IDs and its renames against the last generated file go
    to `warn` (default: stderr; hartlib.device_changes, decisions 3, 5 and 6 of the naming-layers hand-off), each line
    marked check-only when `check` (a --check run, which writes nothing). The caller writes the texts (or compares
    them for --check); nothing is written here. DevicesError when the writer would touch a row it does not hold,
    override a field cell, drop an ID the field file holds owner's cells for (device_changes.stop lists it and the new
    IDs that may be its device's), or the result does not merge back to what the writer gave."""
    from . import device_changes                # it reads this module
    out, changes = _after_rows(writer, new, files)
    if changes is not None:
        device_changes.say(writer, changes, warn, check)
    return out


def _after_rows(writer: str, new: Iterable[Mapping[str, str]],
                files: Files | None) -> tuple[dict[Path, str], device_changes_mod.Changes | None]:
    """(outputs_after_rows' texts, the write's device_changes.Changes, None for a one-file copy), nothing said."""
    from . import device_changes                # it reads this module
    f = files or Files.here()
    if f.field is None:                     # a one-file copy: it holds every cell
        return texts(replace_rows([r.cells() for r in load(f)], writer, new), f), None
    # The old merged view is not read: after an owner's edit (a field row removed or renamed) it may not merge any
    # more, and this write is what makes the pair whole again.
    new = [dict(r) for r in new]
    field = field_rows(f)
    last = generated_rows(f)
    keep = [dict(g) for g in last if g["written_by"] != writer]
    _writes_only_its_own(writer, new, keep + [r for r in field if not r["level"]])
    out = keep + unmerge(new, field, writer)
    out.sort(key=row_rank)
    changes = device_changes.stop(last, out, field)
    back = merge(out, field, (f.master.name, f.field.name))
    mine = {key_of(r): dict(r) for r in back if r["written_by"] == writer}
    if mine != {key_of(r): r for r in new}:
        raise DevicesError(f"{writer}: the rows written do not merge back to what it gave")
    return {f.master: master_text(out, f)}, changes


def outputs_after(writer: str, old_rows: Iterable[Mapping[str, str]], files: Files | None = None,
                  master_rows: Iterable[Mapping[str, str]] = (),
                  warn: "Callable[[str], None] | None" = None, check: bool = False) -> dict[Path, str]:
    """outputs_after_rows for `old_rows`, old-form device-map rows each with the role its writer gives it (master_row
    gives each its master form), and
    `master_rows`, rows already in the master's form (a builder's staging rows, built on the owner's field rows, or
    rows the device maps leave out). What a reader of the master sees for these rows is what the writer gave; DevicesError
    when it is not. `warn` and `check`: where the write's ID changes and renames go, once it has read back
    (outputs_after_rows)."""
    from . import device_changes                # it reads this module
    f = files or Files.here()
    old_rows = list(old_rows)
    master_rows = [dict(r) for r in master_rows]
    new = [master_row(o, writer) for o in old_rows]
    out, changes = _after_rows(writer, new + master_rows, f)
    want = {(str(o["level"]), o["layer"], o["user_name"]): {c: str(o[c]) for c in DEVICE_COLUMNS} for o in old_rows}
    whole = {(r["level"], r["layer"], r["user_name"]): r for r in master_rows}
    back = {name_key(r): r.cells() for r in parse(out[f.master], f.master.name, f) if r.written_by == writer}
    held = {k: device_map_row(r) for k, r in back.items() if k not in whole}
    if held != want or any(back.get(k) != r for k, r in whole.items()):
        raise DevicesError(f"{writer}: the rows written do not read back as given")
    if changes is not None:
        device_changes.say(writer, changes, warn, check)
    return out


def one_file_copy(path: Path, files: "Files | Path | str | None" = None) -> Path:
    """Write the merged view of the master (or of `files`) to `path` as a one-file master (no field file beside it:
    it holds every cell), for a test or a check that edits a copy row by row; the path written."""
    path = Path(path)
    if path.name == GENERATED_FILE:
        raise DevicesError(f"{path}: a one-file copy takes another name ({ONE_FILE}); {GENERATED_FILE} is half a "
                           "pair")
    path.write_text(master_text([r.cells() for r in load(files)], path), encoding="utf-8")
    return path


def pair_copy(data: Path, files: "Files | Path | str | None" = None) -> Files:
    """Copy the master's two files and its dictionary (or `files`') into the folder `data` as they are; their
    Files there."""
    src, data = Files.of(files), Path(data)
    data.mkdir(parents=True, exist_ok=True)
    out = Files.under(data)
    for a, b in ((src.master, out.master), (src.field, out.field), (src.dictionary, out.dictionary)):
        if a is not None and b is not None:
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
        if r.role in OUT_OF_MAPS or r.level is None:
            continue
        try:
            master_row(device_map_row(r) | {"role": r.role, "id": r.id}, r.written_by, r.cells())
        except DevicesError as exc:
            out.append(str(exc))
        except (KeyError, ValueError) as exc:
            out.append(f"level {r.level_cell} {r.layer} {r.user_name}: cannot be read in the device-map form ({exc!r})")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m hartlib.devices", description=__doc__.split("\n")[0])
    ap.add_argument("action", choices=("check",))
    ap.parse_args(argv)
    f = Files.here()
    try:
        problems = stale(f)
        for p in problems:
            print(p, file=sys.stderr)
        if not problems:
            for w in redundant(generated_rows(f), field_rows(f)):
                print(f"warning: {w}", file=sys.stderr)
            field = f.field.name if f.field is not None else "no field file"
            print(f"{f.master.name} with {field}: {len(load(f))} rows; its dictionary agrees")
        return 1 if problems else 0
    except DevicesError as exc:
        print(f"devices.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
