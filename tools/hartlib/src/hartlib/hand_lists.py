"""The owner's hand lists in jmri/layouts/hart/data/: each file's one reader, which checks its shape and stops with
HandListError naming the file and line (every read of layout data goes through hartlib).

    from hartlib import hand_lists
    hand_lists.read_block_overrides(path)          # block_overrides.csv: the owner's hand facts about blocks
    hand_lists.read_main_lines("staging")          # main_lines.csv: the main lines of a schematic sheet
    hand_lists.read_mast_cells()                   # mast_cells.csv: the masts on the parked USS CTC board
    hand_lists.read_uss_cells(), read_uss_plants() # uss_board_cells.csv, uss_board_plants.csv: that board's grid
    hand_lists.read_retired_masts()                # retired_virtual_masts.csv: the virtual masts dropped from a level
    hand_lists.read_sheet_rows()                   # sheets.csv: the station detail sheets, as rows
    hand_lists.read_panel_items()                  # panel_items.json: the Layout Editor panel's own items, as loaded

- block_overrides.csv (schematic/): read_block_overrides. Every level's rows, keyed by switch numbers, so a new
  export moves a row with its track; a track row's `block` is an OS block's device ID, named here from the plan and
  the name store (os_block_name). The panel builders (tools/schematic: block_override_rows, block_layer) read it here.
- main_lines.csv (schematic/): read_main_lines. Each stop's tracks are block IDs and come back by the name store's
  names (resolve_stop), so a rename in devices_field.csv changes no row. build_main_route.py reads it here.
- mast_cells.csv, uss_board_cells.csv, uss_board_plants.csv: the parked USS CTC machine's board (its grid frozen
  from the hand-wired CATS desk) and the hand-wired desks' lamp placements. Read by
  jmri/layouts/hart/scripts/layout_facts.py (for gen_ctc_track_plan.py) and tools/audit/check_layout_facts.py.
  mast_cells.csv keys masts by name: two of its masts no longer exist, and it is keyed by mast ID when the USS
  machine is unparked.
- retired_virtual_masts.csv (schematic/): read_retired_masts, {mast: system name} with each row checked, so a dropped
  mast's ordinal stays taken. tools/schematic/mast_plan.py (read_retired) reads it here.
- sheets.csv (schematic/): read_sheet_rows, the rows with their lines; tools/schematic/build_staging_sets.py
  (read_sheets) checks them against the stations.
- panel_items.json (schematic/): read_panel_items, the parsed file; tools/schematic/panel_items.py (load) checks its
  items, for build_layout_le.py.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping
from typing import Any

from . import level_masts, paths
from .railroad_facts import natural, read_rows
from .errors import HartlibError

DATA = paths.LAYOUT_DATA
SCHEMATIC = DATA / "schematic"


class HandListError(HartlibError, ValueError):
    """A hand list that cannot be read or is not in its shape; the message names the file and line."""


# ---------------------------------------------------------------- block_overrides.csv

OVERRIDES_NAME = "block_overrides.csv"     # in the schematic data folder, beside plan_overrides.json
TRACK_KEY_COLUMNS = ["switch_a", "switch_b", "parallel"]
# `parallel` has two uses: on a split or track row, the track's place among tracks with the same end switches (1 to
# 4, plan order); on a crossover_half row, the half's letter, 1 a or 2 b (HALF_LETTERS). Both say which of two or
# more things sharing switch_a and switch_b the row means.
OVERRIDE_COLUMNS = ["level", "kind"] + TRACK_KEY_COLUMNS + ["end", "block", "cm", "inside", "notes"]
OVERRIDE_KINDS = ("split", "track", "crossover_half")
SWITCH_NUMBER = re.compile(r"\d+")
HALF_LETTERS = "ab"           # a crossover_half row's parallel 1 or 2: the half's letter
OS_ID = re.compile(r"os:(?P<n>\d+)(?::A-(?P<to>\d+)[A-Z]?[A-D]|:(?P<corner>[A-D]))?")


def key_problem(row: dict) -> str:
    """Why a row's switch_a, switch_b and parallel are not a track key ("" when they are)."""
    a, b, par = row["switch_a"], row["switch_b"], row["parallel"]
    if not SWITCH_NUMBER.fullmatch(a) or (b and not SWITCH_NUMBER.fullmatch(b)):
        return f"switch_a {a!r} and switch_b {b!r} are switch numbers (switch_b blank for a spur)"
    if b and natural(a) > natural(b):
        return f"switch_a {a} and switch_b {b} are in number order, lower first"
    if par and par not in ("1", "2", "3", "4"):
        return f"parallel {par!r} is blank or the track's place in plan order (plan_order), 1 to 4"
    return ""


def read_block_overrides(path: Path = SCHEMATIC / OVERRIDES_NAME, kinds: tuple[str, ...] = OVERRIDE_KINDS,
                         names: Mapping[tuple[str, str], str] | None = None) -> list[dict]:
    """The rows of `kinds` of block_overrides.csv (OVERRIDE_COLUMNS), the owner's hand facts about blocks, each with
    its `line` and its `cm` a number (None when blank); a short row's missing trailing fields are empty. Every row of
    every kind is checked for its shape, whichever kinds are asked for, so a bad row stops every reader of the file;
    resolving a row against the drawing is the reader's (block_override_rows.read_block_splits,
    block_layer.read_exceptions). A row of any level (1 staging, 2 main, 3 upper), keyed by switch numbers so a new
    export moves it with its track:
    - split: the track switch_a to switch_b (lower first; parallel where two tracks run between them,
      block_override_rows.resolve_track) is two blocks parted at its turnback. The OWNER'S CHOICE, not a rule (a rule
      would catch every intermediate loop). No end, block, cm or inside.
    - track: the track switch_a to switch_b (as for split), or with `end` one of them the piece of it at that end, is
      part of `block`, an OS block by its device ID (os:15, a crossover half's os:35:A-39A),
      where the field wiring (or, on main and upper, the owner) says so; `cm` the piece's length, for a piece at one
      end whose track keeps the rest; `inside` yes keeps it inside its OS block with no JMRI or layout block of its
      own. block_layer's module text has the rules. The row comes back with `block` the OS block's generated name
      (os_block_name; `names` as there) and `id` the ID, so an owner's rename of the OS block (devices_field.csv)
      changes no row here.
    - crossover_half: `block` the half's own OS block by its device ID, os:<n>:A-<end> (the half whose leg A runs to
      that end: os:7:A-13C), switch_a its crossover's number n and switch_b the end's switch, as the ID has them;
      `parallel` 1 or 2, the half's letter a or b (HALF_LETTERS). The letter is the owner's: the desks label the half
      by it (7A, 7B) and the generator names the half OS Switch <n><letter>, so the owner's name for it
      (devices_field.csv, by its ID) is free and nothing reads a letter off a name. The row comes back with `id` the
      ID, `half` the letter and `block` the generated name, as a track row does. No end, cm or inside; each letter
      once per crossover.
    HandListError naming the file and line on columns not OVERRIDE_COLUMNS, a level not 1 to 3, a kind not
    OVERRIDE_KINDS, or a row not in its kind's shape."""
    unknown = sorted(set(kinds) - set(OVERRIDE_KINDS))
    if unknown:
        raise HandListError(f"{path.name}: no kind {', '.join(unknown)} (kinds: {', '.join(OVERRIDE_KINDS)})")
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
    except OSError as exc:
        raise HandListError(f"cannot read {path.name}: {exc}") from exc
    if reader.fieldnames != OVERRIDE_COLUMNS:
        raise HandListError(f"{path.name}: columns {reader.fieldnames}, not {OVERRIDE_COLUMNS}")
    out: list[dict[str, Any]] = []
    bad: list[str] = []
    halves: dict[tuple[str, str, str], str] = {}      # (level, switch, switch_b) -> the half's OS block
    letters: dict[tuple[str, str, str], int] = {}     # (level, switch, half letter) -> its line
    for i, r in enumerate(rows, 2):
        if None in r:                       # a short row's missing trailing fields are empty, as csv reads them
            bad.append(f"line {i}: more fields than the header's {len(OVERRIDE_COLUMNS)}")
            continue
        r = {k: (v or "").strip() for k, v in r.items()}
        r["line"] = i
        problem = override_problem(r)
        if problem:
            bad.append(f"line {i} (level {r['level']}, kind {r['kind']}): {problem}")
            continue
        r["cm"] = float(r["cm"]) if r["cm"] else None
        if r["kind"] == "crossover_half":         # every half, whichever kinds are asked for: a track row's OS block
            r["id"], r["half"] = r["block"], HALF_LETTERS[int(r["parallel"]) - 1]
            r["block"] = f"OS Switch {r['switch_a']}{r['half']}"
            other = letters.setdefault((r["level"], r["switch_a"], r["half"]), i)
            if other != i:
                bad.append(f"line {i}: Switch {r['switch_a']}'s half {r['half']} is given on line {other} too")
            halves[(r["level"], r["switch_a"], r["switch_b"])] = r["block"]
        if r["kind"] in kinds:
            out.append(r)
    for r in out if not bad else ():
        if r["kind"] == "track":
            r["id"] = r["block"]
            try:
                r["block"] = os_block_name(r["level"], r["id"], halves, names)
            except HandListError as exc:
                bad.append(f"line {r['line']}: {exc}")
    if bad:
        raise HandListError(f"{path.name}: " + "; ".join(bad))
    return out


def half_letters(path: Path = SCHEMATIC / OVERRIDES_NAME) -> dict[tuple[str, str], str]:
    """{(level, a crossover half's OS block ID): its letter a or b}, from block_overrides.csv's crossover_half rows
    (the owner's letters: a desk labels the half 7A, 7B by them, never by its name). HandListError as
    read_block_overrides."""
    return {(r["level"], r["id"]): r["half"] for r in read_block_overrides(path, ("crossover_half",))}


def os_block_name(level: str, ident: str, halves: Mapping[tuple[str, str, str], str],
                  names: Mapping[tuple[str, str], str] | None = None) -> str:
    """The generated name of the OS block with device ID `ident`: os:<n> is OS Switch <n>; a crossover half,
    os:<n>:A-<end>, is the half whose leg A runs to the end's switch, named by its crossover_half row (`halves`:
    {(level, crossover, switch): name}); a double crossover's corner, os:<n>:<leg> (os:225:D), is named by the device
    master (`names`, hartlib.devices.user_names, default the repo's: its letter is not its leg, OS Switch 225a is
    os:225:C). HandListError on an ID of no OS block, a half with no crossover_half row, or a corner the master
    lacks."""
    m = OS_ID.fullmatch(ident)
    if not m:
        raise HandListError(f"block {ident!r} is no OS block ID (os:<switch>, a crossover half's os:<switch>:A-<end>, "
                            "or a double crossover corner's os:<switch>:<leg>)")
    if m.group("corner"):
        if names is None:
            from . import devices
            names = devices.user_names()
        name = names.get((level, ident))
        if name is None:
            raise HandListError(f"block {ident}: no level {level} OS block of the device master has this id")
        return name
    if not m.group("to"):
        return f"OS Switch {m.group('n')}"
    name = halves.get((level, m.group("n"), m.group("to")))
    if name is None:
        raise HandListError(f"block {ident}: no crossover_half row of Switch {m.group('n')} whose leg A runs to "
                            f"Switch {m.group('to')}")
    return name


def override_problem(r: dict) -> str:
    """Why a block_overrides.csv row (its fields stripped) is not in its kind's shape ("" when it is)."""
    if r["level"] not in ("1", "2", "3") or r["kind"] not in OVERRIDE_KINDS:
        return f"level is 1, 2 or 3 and kind one of {', '.join(OVERRIDE_KINDS)}"
    kind = r["kind"]
    if kind == "split":
        if r["end"] or r["block"] or r["cm"] or r["inside"]:
            return "a split is a track's switch_a, switch_b and parallel, with no end, block, cm or inside"
        return key_problem(r)
    if kind == "track" and not OS_ID.fullmatch(r["block"]):
        return (f"block {r['block']!r} is no OS block ID (a piece of track is part of a switch's OS block: os:<switch>, "
                "a crossover half's os:<switch>:A-<end>, or a double crossover corner's os:<switch>:<leg>)")
    if kind == "crossover_half":
        m = OS_ID.fullmatch(r["block"])
        if not (m and m.group("to")):
            return (f"block {r['block']!r} is no crossover half's OS block ID (os:<switch>:A-<end>, the half whose "
                    "leg A runs to that end)")
        if (m.group("n"), m.group("to")) != (r["switch_a"], r["switch_b"]) or \
                r["parallel"] not in ("1", "2") or r["end"] or r["cm"] or r["inside"]:
            return ("a crossover half is switch_a (the crossover) and switch_b (where its leg A track runs), as its "
                    "block ID has them, and parallel 1 or 2 (its letter a or b), with no end, cm or inside")
        return ""
    try:
        cm = float(r["cm"]) if r["cm"] else None
    except ValueError:
        cm = -1.0
    if cm is not None and not cm > 0:
        return f"cm {r['cm']!r} is a length in cm, more than 0"
    if r["inside"] not in ("", "yes"):
        return f"inside is yes or empty, not {r['inside']!r}"
    problem = key_problem(r)
    if problem or not r["switch_b"] or (r["end"] and r["end"] not in (r["switch_a"], r["switch_b"])):
        return problem or "a track between two switches, its end empty or one of them"
    return ""


# ---------------------------------------------------------------- main_lines.csv

MAIN_LINES_NAME = "main_lines.csv"
MAIN_LINES = SCHEMATIC / MAIN_LINES_NAME
MAIN_LINE_COLUMNS = ["sheet", "line", "from", "via", "to", "loop", "double", "count", "notes"]
SHEETS = ("staging", "main_upper")
STOP_CELLS = ("from", "via", "to", "loop")
TRACK_PREFIX = "Track "


def split(cell: str) -> list[str]:
    """The items of a `;` list cell, each stripped, empty ones left out."""
    return [p.strip() for p in cell.split(";") if p.strip()]


def resolve_stop(token: str, names: Mapping[tuple[str, str], str] | None, where: str) -> str:
    """A stop as main_lines.csv gives it, with each track in it by its block id, as the plan
    graph names it: the track's name in the name store (`names`, hartlib.devices.user_names) less "Track ", so
    "35@block:33A-35A" is "35@East Lead" and "block:39B-helix" "Helix Outer". A switch number is itself. The ids are
    looked up on every level (a helix track's is staging's: its main or upper end carries the same name), so a rename
    in devices_field.csv reaches the route with no row here changed. HandListError on a track given by name, or an id
    the device master does not have."""
    label, at, track = token.rpartition("@") if "@" in token else ("", "", token)
    if not track.startswith("block:"):
        if at or " " in token:
            raise HandListError(f"{where}: stop {token!r} names a track by its name; give its block id "
                                "(devices_generated.csv's id column, as 35@block:33A-35A or block:39B-helix)")
        return token
    if names is None:
        from . import devices
        names = devices.user_names()
    hit = next((names[(lv, track)] for lv in ("1", "2", "3") if (lv, track) in names), None)
    if hit is None:
        raise HandListError(f"{where}: stop {token!r}: {track} is no block of the device master (a new export "
                            "dropped it: give the track's new id)")
    return f"{label}{at}{hit.removeprefix(TRACK_PREFIX)}"


def read_main_lines(sheet: str, path: Path = MAIN_LINES,
                    names: Mapping[tuple[str, str], str] | None = None) -> list[dict]:
    """The main lines of one sheet of main_lines.csv (MAIN_LINE_COLUMNS; build_main_route.py's module text says what
    each column holds). The whole file is checked first: its columns, a known sheet on every row, a line name used
    once per sheet, from and to given, count yes or blank and only on staging (the main and upper mileposts follow
    main_route), loop and double only on main_upper (staging_text reads neither); the sheet asked for must have a
    line. Each stop's tracks are given by block id and come back by name (resolve_stop; `names` the name store's,
    default hartlib.devices.user_names of the repo). HandListError naming the file and line otherwise."""
    if sheet not in SHEETS:
        raise HandListError(f"unknown sheet {sheet!r}: the sheets are {', '.join(SHEETS)}")
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
    except OSError as exc:
        raise HandListError(f"cannot read {path.name}: {exc}") from exc
    if reader.fieldnames != MAIN_LINE_COLUMNS:
        raise HandListError(f"{path.name}: expected the columns {', '.join(MAIN_LINE_COLUMNS)}, got {reader.fieldnames}")
    seen = set()
    for n, r in enumerate(rows, 2):
        if None in r.values() or None in r:
            raise HandListError(f"{path.name} line {n}: expected {len(MAIN_LINE_COLUMNS)} cells "
                                f"({', '.join(MAIN_LINE_COLUMNS)})")
        r["sheet"] = r["sheet"].strip()
        if r["sheet"] not in SHEETS:
            raise HandListError(f"{path.name} line {n}: sheet {r['sheet']!r} is not one of {', '.join(SHEETS)}")
        if not r["line"].strip() or (r["sheet"], r["line"]) in seen:
            raise HandListError(f"{path.name} line {n}: line name {r['line']!r} is empty or repeated on sheet "
                                f"{r['sheet']}")
        seen.add((r["sheet"], r["line"]))
        if not r["from"].strip() or not r["to"].strip():
            raise HandListError(f"{path.name} line {n} ({r['line']}): from and to are both needed")
        if r["count"].strip() not in ("", "yes"):
            raise HandListError(f"{path.name} line {n} ({r['line']}): count is yes or blank, not {r['count']!r}")
        if r["count"].strip() and r["sheet"] != "staging":
            raise HandListError(f"{path.name} line {n} ({r['line']}): count is only read on the staging sheet; the "
                                f"{r['sheet']} mileposts follow main_route")
        if r["sheet"] == "staging" and (r["loop"].strip() or r["double"].strip()):
            raise HandListError(f"{path.name} line {n} ({r['line']}): loop and double are only read on the "
                                "main_upper sheet; a staging line names its junctions in via")
    mine = [r for r in rows if r["sheet"] == sheet]
    if not mine:
        raise HandListError(f"{path.name} has no main line on sheet {sheet}")
    if any("block:" in r[c] for r in mine for c in STOP_CELLS):
        if names is None:
            from . import devices
            names = devices.user_names()
    for n, r in enumerate(rows, 2):
        if r["sheet"] != sheet:
            continue
        for c in STOP_CELLS:
            where = f"{path.name} line {n} ({r['line']}), {c}"
            r[c] = (";".join(resolve_stop(t, names, where) for t in split(r[c])) if c in ("via", "loop")
                    else resolve_stop(r[c].strip(), names, where))
    return mine


# ---------------------------------------------------------------- retired_virtual_masts.csv

RETIRED_MASTS = SCHEMATIC / "retired_virtual_masts.csv"
RETIRED_MAST_COLUMNS = ["mast", "system_name", "dropped", "notes"]


def read_retired_masts(path: Path = RETIRED_MASTS) -> dict[str, str]:
    """{mast: system name} of the virtual masts dropped from any level (RETIRED_MAST_COLUMNS), so their ordinals stay
    taken. Stops on other columns, or a row whose mast is empty or listed twice, whose system name is no
    VirtualSignalMast's (level_masts.virtual_ordinal), or whose ordinal another row has."""
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
    except OSError as exc:
        raise HandListError(f"cannot read {path.name}: {exc}") from exc
    if reader.fieldnames != RETIRED_MAST_COLUMNS:
        raise HandListError(f"{path.name}: columns {reader.fieldnames}, not {RETIRED_MAST_COLUMNS}")
    out, seen = {}, set()
    for n, r in enumerate(rows, 2):
        m, sysname = (r["mast"] or "").strip(), (r["system_name"] or "").strip()
        k = level_masts.virtual_ordinal(sysname)
        if not m or m in out or k is None or k in seen:
            raise HandListError(f"{path.name} line {n}: {m!r} {sysname!r} is empty, listed twice, not a virtual "
                                "mast's system name, or reuses an ordinal")
        out[m] = sysname
        seen.add(k)
    return out


# ---------------------------------------------------------------- sheets.csv

SHEETS_FILE = SCHEMATIC / "sheets.csv"
SHEET_COLUMNS = ("level", "sheet", "stations")      # and notes, optional


def read_sheet_rows(path: Path = SHEETS_FILE) -> list[tuple[int, dict[str, str]]]:
    """(line, row) of each station detail sheet (SHEET_COLUMNS and notes, values stripped; railroad_facts.read_rows).
    Stops (FactsError) on a missing column or a row of the wrong length; what the cells may hold is the reader's
    (build_staging_sets.read_sheets)."""
    return read_rows(path, SHEET_COLUMNS, optional=("notes",))


# ---------------------------------------------------------------- panel_items.json

PANEL_ITEMS = SCHEMATIC / "panel_items.json"


def read_panel_items(path: Path = PANEL_ITEMS) -> Any:     # the JSON as json.loads gives it
    """The Layout Editor panel's own items file, parsed; HandListError when it cannot be read or parsed. Its shape is
    checked by tools/schematic/panel_items.py (load)."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HandListError(f"cannot read {Path(path).name}: {exc}") from exc


# ---------------------------------------------------------------- the USS CTC board (parked)

MAST_CELLS = "mast_cells.csv"
MAST_CELL_COLUMNS = ["mast", "x", "y", "edge", "uss_facing", "uss_kind", "uss_head", "sig_location", "sig_orient",
                     "notes"]
USS_CELLS = "uss_board_cells.csv"
USS_PLANTS = "uss_board_plants.csv"
EDGES = {"LEFT", "RIGHT", "TOP", "BOTTOM"}
USS_TRACKS = {"HORIZONTAL", "VERTICAL", "UPPERSLASH", "LOWERSLASH", "UPPERBACKSLASH", "LOWERBACKSLASH"}


@dataclass(frozen=True)
class MastCell:
    """A mast's icon on the USS CTC board, and its lamp on the hand-wired CATS desks (whose grid the board keeps)."""
    mast: str
    x: int             # the cell on the USS board's grid (uss_board_cells.csv)
    y: int
    edge: str          # hand-wired desks only: SEC_EDGE of the cell that holds the SECSIGNAL
    uss_facing: str    # E or W on the USS board
    uss_kind: str      # h2: mast icon (two heads); d1: head icon on the only head
    uss_head: str      # that head for d1, blank for h2
    sig_location: str = ""  # hand-wired desks only: PANELSIGNAL SIGLOCATION / SIGORIENT to set, blank to keep
    sig_orient: str = ""


def read_mast_cells(data: Path = DATA) -> list[MastCell]:
    """mast_cells.csv in `data`, in file order (the order the USS board draws the icons). HandListError on a mast or
    a cell and edge given twice, an edge not EDGES, uss_facing not E or W, uss_kind not h2 or d1, a d1 icon without
    its head or an h2 with one, sig_location without sig_orient, columns not MAST_CELL_COLUMNS, a row of another
    number of fields, or an x or y that is not a whole number."""
    out: list[MastCell] = []
    seen: dict[str, int] = {}
    cells: dict[tuple[int, int, str], int] = {}
    with (data / MAST_CELLS).open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != MAST_CELL_COLUMNS:
            raise HandListError(f"{MAST_CELLS}: columns {','.join(MAST_CELL_COLUMNS)}, not "
                                f"{','.join(reader.fieldnames or [])}")
        rows = []
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                have = sum(v is not None for k, v in row.items() if k is not None) + len(row.get(None) or [])
                raise HandListError(f"{MAST_CELLS} line {reader.line_num}: {len(MAST_CELL_COLUMNS)} fields, not {have}")
            rows.append({k: v.strip() for k, v in row.items()})
    for line, row in enumerate(rows, start=2):
        where = f"{MAST_CELLS} line {line} ({row['mast']})"
        try:
            x, y = int(row["x"]), int(row["y"])
        except ValueError as exc:
            raise HandListError(f"{where}: x and y are whole numbers, not {row['x']!r} and {row['y']!r}") from exc
        cell = MastCell(row["mast"], x, y, row["edge"], row["uss_facing"],
                        row["uss_kind"], row["uss_head"], row["sig_location"], row["sig_orient"])
        key = (cell.x, cell.y, cell.edge)
        if cell.mast in seen:
            raise HandListError(f"{MAST_CELLS} lines {seen[cell.mast]} and {line}: same mast {cell.mast}")
        seen[cell.mast] = line
        if key in cells:
            raise HandListError(f"{MAST_CELLS} lines {cells[key]} and {line}: same cell and edge {key}")
        cells[key] = line
        if cell.edge not in EDGES or cell.uss_facing not in ("E", "W") or cell.uss_kind not in ("h2", "d1"):
            raise HandListError(f"{where}: edge {EDGES}, uss_facing E/W, uss_kind h2/d1")
        if (cell.uss_kind == "d1") != bool(cell.uss_head):
            raise HandListError(f"{where}: uss_head is the head for d1 and blank for h2")
        if bool(cell.sig_location) != bool(cell.sig_orient):
            raise HandListError(f"{where}: sig_location and sig_orient go together")
        out.append(cell)
    return out


def _noted_rows(path: Path, columns: list[str]) -> list[tuple[int, dict[str, str]]]:
    """(line, row) of a CSV below its `# ` note line, values kept as written (a cell name may hold runs of
    spaces)."""
    with path.open(newline="", encoding="utf-8") as fh:
        if not fh.readline().startswith("# "):
            raise HandListError(f"{path.name} line 1: the note line (# ...) saying where the file came from")
        reader = csv.DictReader(fh)
        if reader.fieldnames != columns:
            raise HandListError(f"{path.name}: columns {','.join(columns)}, not {','.join(reader.fieldnames or [])}")
        out = []
        for row in reader:
            line = reader.line_num + 1              # + the note line, which the reader did not see
            if None in row or any(v is None for v in row.values()):
                have = sum(v is not None for k, v in row.items() if k is not None) + len(row.get(None) or [])
                raise HandListError(f"{path.name} line {line}: {len(columns)} fields ({','.join(columns)}), "
                                    f"not {have}")
            out.append((line, row))
        return out


def read_uss_cells(data: Path = DATA) -> dict[tuple[int, int], dict]:
    """The USS CTC board's grid (uss_board_cells.csv in `data`), frozen from the hand-wired CATS desk,
    in file order: (x, y) -> {tracks: [CATS track kinds], name: the cell's label or None, blocks: [(edge, block or
    None, occupancy sensor or None)]}, the shape gen_ctc_track_plan.build_block reads."""
    out: dict[tuple[int, int], dict] = {}
    for line, row in _noted_rows(data / USS_CELLS, ["x", "y", "tracks", "name", "blocks"]):
        where = f"{USS_CELLS} line {line}"
        try:
            xy = (int(row["x"]), int(row["y"]))
        except (TypeError, ValueError) as exc:
            raise HandListError(f"{where}: x and y are whole numbers") from exc
        if xy in out:
            raise HandListError(f"{where}: cell {xy} is listed twice")
        tracks = [t for t in row["tracks"].split(";") if t]
        if set(tracks) - USS_TRACKS:
            raise HandListError(f"{where}: tracks are {', '.join(sorted(USS_TRACKS))}, not {row['tracks']!r}")
        blocks = []
        for item in [b for b in row["blocks"].split(";") if b]:
            parts = item.split("|")
            if len(parts) != 3 or parts[0] not in EDGES or not (parts[1] or parts[2]):
                raise HandListError(f"{where}: a block is EDGE|block|sensor (block or sensor given), not {item!r}")
            blocks.append((parts[0], parts[1] or None, parts[2] or None))
        out[xy] = dict(tracks=tracks, name=row["name"] or None, blocks=blocks)
    return out


def read_uss_plants(data: Path = DATA) -> dict[tuple[int, int], str]:
    """(x, y) -> OS block of each switch plant on the USS CTC board grid (uss_board_plants.csv in `data`), in its
    drawing order. Each cell holds track in uss_board_cells.csv; the hand-wired CATS desks put their plants there
    too."""
    cells = read_uss_cells(data)
    out: dict[tuple[int, int], str] = {}
    seen: dict[str, int] = {}
    for line, row in _noted_rows(data / USS_PLANTS, ["os_block", "x", "y", "notes"]):
        where = f"{USS_PLANTS} line {line} ({row['os_block']})"
        try:
            xy = (int(row["x"]), int(row["y"]))
        except (TypeError, ValueError) as exc:
            raise HandListError(f"{where}: x and y are whole numbers") from exc
        if not row["os_block"] or row["os_block"] in seen or xy in out:
            raise HandListError(f"{where}: an OS block or cell that is empty or given twice")
        if not cells.get(xy, {}).get("tracks"):
            raise HandListError(f"{where}: {USS_CELLS} has no track in cell {xy}")
        seen[row["os_block"]] = line
        out[xy] = row["os_block"]
    return out
