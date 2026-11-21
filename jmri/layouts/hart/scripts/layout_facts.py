#!/usr/bin/env python3
"""Railroad facts about each switch, read from jmri/layouts/hart/data/.

    switches.csv     every level's switches, one row per OS block (staging)
                     or half (main and upper); a staging switch's rows give
                     the block each leg leads to when the switch is closed and
                     when it is thrown, and its first row its level, Layout
                     Editor turnout, CATS inversion, USS CTC lever and hand
                     (L or R, blank where nobody has recorded it). This module
                     reads staging's (switches.columns.csv has every column)
    mast_cells.csv   one row per mast on the USS CTC board: its cell on the
                     board's grid (x, y) and how the board draws it (uss_*),
                     read by gen_ctc_track_plan.py; and, for the hand-wired
                     CATS desks only, the SEC_EDGE of its lamp in that cell and
                     a lamp placement to set (edge, sig_location, sig_orient),
                     read by check_layout_facts.py. The
                     board's grid is the hand-wired desk's, frozen on
                     2026-11-15; the generated desks do not use this file
    uss_board_cells.csv / uss_board_plants.csv  the USS CTC board's grid:
                     each cell's track, label and block edges, and the cell
                     of each switch plant, frozen from the hand-wired desk
                     on 2026-11-15 (read by gen_ctc_track_plan.py and
                     check_layout_facts.py)

Hardware, DCC address (its own ``dcc`` column) and control point come from the
canonical turnout row of the name map of devices.csv (current == proposed); the desk areas of schematic/stations.csv list which
switches each control point holds and its level. Nothing here is copied from
those files.

Level is held once per switch (switches.csv) and once per control point
(a station's, in stations.csv). A mast, head, block or occupancy sensor has no level of
its own: it takes the level of its control point (the ``cp`` column of
the name map of devices.csv), and an OS block or a switch leg takes its switch's.
name_map_levels() resolves them. No grouping above the control point exists
yet, so there is no district column; when the new levels need one, it goes beside ``level`` on the control-point
files (stations.csv, interlockings.csv).

Switch numbers are the plate numbers and are unique across the whole railroad,
every level included: a number is never reused on another level. The loader
refuses a second row for a number, an OS block or a USS lever.

Track names are the occupancy names the CATS desks use (Track S-R, not the
Layout Editor's hidden Track S-R West throat). check_layout_facts.py proves
tables.xml, the CATS desks and the USS CTC agree with these files.
"""
from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths, railroad, railroad_facts  # noqa: E402
from hartlib.railroad import Leg, Switch  # noqa: E402,F401  one definition, in hartlib.railroad

DATA = paths.LAYOUT_DATA
_SWITCH_NAME = re.compile(r"(?:DCC |FB )?Switch (\d+)(?: [NR])?")


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


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]


def identity_rows(data: Path = DATA) -> list[dict[str, str]]:
    """The name-map rows of devices.csv whose current name is the live one (current == proposed): hartlib.railroad's
    read_name_rows, so the master is read by one loader."""
    return [row for _line, row in railroad.read_name_rows(railroad.Sources.under(data).devices)
            if row["current"] == row["proposed"]]


def load_switches(data: Path = DATA) -> dict[int, Switch]:
    """Switch number -> Switch, in switches.csv order (hartlib.railroad.read_switches). Line numbers in errors
    count the header as 1."""
    s = railroad.Sources.under(data)
    return railroad.read_switches(s.switches, s.devices)


EDGES = {"LEFT", "RIGHT", "TOP", "BOTTOM"}


def load_mast_cells(data: Path = DATA) -> list[MastCell]:
    """mast_cells.csv in file order (the order the USS board draws the icons)."""
    out: list[MastCell] = []
    seen: dict[str, int] = {}
    cells: dict[tuple[int, int, str], int] = {}
    for line, row in enumerate(_rows(data / "mast_cells.csv"), start=2):
        where = f"mast_cells.csv line {line} ({row['mast']})"
        cell = MastCell(row["mast"], int(row["x"]), int(row["y"]), row["edge"], row["uss_facing"],
                        row["uss_kind"], row["uss_head"], row["sig_location"], row["sig_orient"])
        key = (cell.x, cell.y, cell.edge)
        for what, index, value in (("mast", seen, cell.mast), ("cell and edge", cells, key)):
            if value in index:
                raise ValueError(f"mast_cells.csv lines {index[value]} and {line}: same {what} {value}")
            index[value] = line
        if cell.edge not in EDGES or cell.uss_facing not in ("E", "W") or cell.uss_kind not in ("h2", "d1"):
            raise ValueError(f"{where}: edge {EDGES}, uss_facing E/W, uss_kind h2/d1")
        if (cell.uss_kind == "d1") != bool(cell.uss_head):
            raise ValueError(f"{where}: uss_head is the head for d1 and blank for h2")
        if bool(cell.sig_location) != bool(cell.sig_orient):
            raise ValueError(f"{where}: sig_location and sig_orient go together")
        out.append(cell)
    return out


USS_CELLS = "uss_board_cells.csv"
USS_PLANTS = "uss_board_plants.csv"
USS_TRACKS = {"HORIZONTAL", "VERTICAL", "UPPERSLASH", "LOWERSLASH", "UPPERBACKSLASH", "LOWERBACKSLASH"}


def _noted_rows(path: Path, columns: list[str]) -> list[tuple[int, dict[str, str]]]:
    """(line, row) of a CSV below its `# ` note line, values kept as written (a cell name may hold runs of
    spaces)."""
    with path.open(newline="", encoding="utf-8") as fh:
        if not fh.readline().startswith("# "):
            raise ValueError(f"{path.name} line 1: the note line (# ...) saying where the file came from")
        reader = csv.DictReader(fh)
        if reader.fieldnames != columns:
            raise ValueError(f"{path.name}: columns {','.join(columns)}, not {','.join(reader.fieldnames or [])}")
        out = []
        for row in reader:
            line = reader.line_num + 1              # + the note line, which the reader did not see
            if None in row or any(v is None for v in row.values()):
                have = sum(v is not None for k, v in row.items() if k is not None) + len(row.get(None) or [])
                raise ValueError(f"{path.name} line {line}: {len(columns)} fields ({','.join(columns)}), not {have}")
            out.append((line, row))
        return out


def load_uss_cells(data: Path = DATA) -> dict[tuple[int, int], dict]:
    """The USS CTC board's grid (uss_board_cells.csv), frozen from the hand-wired CATS desk on 2026-11-15, in file
    order: (x, y) -> {tracks: [CATS track kinds], name: the cell's label or None, blocks: [(edge, block or None,
    occupancy sensor or None)]}, the shape gen_ctc_track_plan.build_block reads."""
    out: dict[tuple[int, int], dict] = {}
    for line, row in _noted_rows(data / USS_CELLS, ["x", "y", "tracks", "name", "blocks"]):
        where = f"{USS_CELLS} line {line}"
        try:
            xy = (int(row["x"]), int(row["y"]))
        except (TypeError, ValueError):
            raise ValueError(f"{where}: x and y are whole numbers") from None
        if xy in out:
            raise ValueError(f"{where}: cell {xy} is listed twice")
        tracks = [t for t in row["tracks"].split(";") if t]
        if set(tracks) - USS_TRACKS:
            raise ValueError(f"{where}: tracks are {', '.join(sorted(USS_TRACKS))}, not {row['tracks']!r}")
        blocks = []
        for item in [b for b in row["blocks"].split(";") if b]:
            parts = item.split("|")
            if len(parts) != 3 or parts[0] not in EDGES or not (parts[1] or parts[2]):
                raise ValueError(f"{where}: a block is EDGE|block|sensor (block or sensor given), not {item!r}")
            blocks.append((parts[0], parts[1] or None, parts[2] or None))
        out[xy] = dict(tracks=tracks, name=row["name"] or None, blocks=blocks)
    return out


def load_uss_plants(data: Path = DATA) -> dict[tuple[int, int], str]:
    """(x, y) -> OS block of each switch plant on the USS CTC board grid (uss_board_plants.csv), in its drawing
    order. Each cell holds track in uss_board_cells.csv; the hand-wired CATS desks put their plants there too."""
    cells = load_uss_cells(data)
    out: dict[tuple[int, int], str] = {}
    seen: dict[str, int] = {}
    for line, row in _noted_rows(data / USS_PLANTS, ["os_block", "x", "y", "notes"]):
        where = f"{USS_PLANTS} line {line} ({row['os_block']})"
        try:
            xy = (int(row["x"]), int(row["y"]))
        except (TypeError, ValueError):
            raise ValueError(f"{where}: x and y are whole numbers") from None
        if not row["os_block"] or row["os_block"] in seen or xy in out:
            raise ValueError(f"{where}: an OS block or cell that is empty or given twice")
        if not cells.get(xy, {}).get("tracks"):
            raise ValueError(f"{where}: {USS_CELLS} has no track in cell {xy}")
        seen[row["os_block"]] = line
        out[xy] = row["os_block"]
    return out


def legs_by_os(switches: dict[int, Switch]) -> dict[str, tuple[Switch, Leg]]:
    return {leg.os_block: (sw, leg) for sw in switches.values() for leg in sw.legs}


def load_control_points(data: Path = DATA) -> list[dict[str, str]]:
    """The control points of every level that has desk areas in schematic/stations.csv (staging's only so far; each
    row carries its ``level``), with switches.csv, in the older control_points.csv shape
    (hartlib.railroad_facts.station_group_rows); ``switches`` is the OS-block list, e.g. "23a,23b,33"."""
    return railroad_facts.station_group_rows(data / "schematic" / "stations.csv",
                                             data / "switches.csv")


def station_names(data: Path = DATA) -> set[str]:
    """Control point names as the desks print them, e.g. EAST END (every level's desk areas: staging's so far)."""
    return {row["cp_name"].upper() for row in load_control_points(data)}


def cp_levels(data: Path = DATA) -> dict[str, str]:
    """Control point name -> level, from stations.csv's desk areas (a station's level; station_group_rows stops on a
    row without one)."""
    out: dict[str, str] = {}
    for row in load_control_points(data):
        out[row["cp_name"]] = row["level"]
    return out


def switch_block_levels(switches: dict[int, Switch]) -> dict[str, set[str]]:
    """Block name -> levels of the switches whose OS block it is or whose legs lead to it."""
    out: dict[str, set[str]] = {}
    for sw in switches.values():
        for leg in sw.legs:
            for name in (leg.os_block, leg.closed, leg.thrown):
                out.setdefault(name, set()).add(sw.level)
    return out


def name_map_levels(data: Path = DATA, switches: dict[int, Switch] | None = None,
                    rows: list[dict[str, str]] | None = None,
                    track_name: Callable[[str], str] | None = None) -> dict[tuple[str, str], str]:
    """(layer, public name) -> level for the identity rows of the name map of devices.csv.

    A turnout or feedback sensor of Switch N (``Switch N``, ``DCC Switch N``,
    ``FB Switch N R``) takes switches.csv; an OS block or a block a switch leg
    leads to takes its switch's level; any other row takes its control point's.
    ``track_name`` maps a Layout Editor throat block to its track (Track S-R West
    -> Track S-R, through their shared occupancy sensor in tables.xml); without it
    a throat block is matched by its own name only. A row with none of these (a
    main between control points, Track Main West) is left out: check_layout_facts.py
    gives it the level of the blocks it joins, and reports any block whose switch
    and control point give different levels (here the switch wins).
    """
    switches = load_switches(data) if switches is None else switches
    rows = identity_rows(data) if rows is None else rows
    by_cp = cp_levels(data)
    by_block = switch_block_levels(switches)
    out: dict[tuple[str, str], str] = {}
    for row in rows:
        layer, name = row["layer"], row["proposed"]
        level = ""
        m = _SWITCH_NAME.fullmatch(name) if layer in ("turnout", "fb") else None
        from_switch = by_block.get(track_name(name) if track_name else name, set()) if layer == "block" else set()
        if m and int(m.group(1)) in switches:
            level = switches[int(m.group(1))].level
        elif len(from_switch) == 1:
            level = next(iter(from_switch))
        elif row["cp"] in by_cp:
            level = by_cp[row["cp"]]
        if level:
            out[(layer, name)] = level
    return out
