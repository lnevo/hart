#!/usr/bin/env python3
"""Railroad facts about each switch, read from jmri/layouts/hart/data/ through hartlib (hartlib.railroad for
switches.csv, the device master, stations.csv and interlockings.csv; hartlib.hand_lists for mast_cells.csv and the
USS board's grid): this module opens no data file itself (tools/audit/check_data_readers.py).

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

Hardware (``system_name``), DCC address (its own ``dcc`` column) and control point come from
staging's turnout row of the device master; the desk areas of schematic/stations.csv list which
switches each control point holds and its level. Nothing here is copied from
those files.

Level is held once per switch (switches.csv) and once per control point
(a station's, in stations.csv). A mast, head, block or occupancy sensor has no level of
its own: it takes the level of its control point (the ``cp`` column of
the device master), and an OS block or a switch leg takes its switch's.
staging_levels() resolves them. No grouping above the control point exists
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

import re
import sys
from pathlib import Path
from typing import Callable

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import devices, hand_lists, levels, paths, railroad, railroad_facts  # noqa: E402
from hartlib.railroad import Leg, Switch  # noqa: E402,F401  one definition, in hartlib.railroad

DATA = paths.LAYOUT_DATA
_SWITCH_NAME = re.compile(r"(?:DCC |FB )?Switch (\d+)(?: [NR])?")


MastCell = hand_lists.MastCell          # one definition, in hartlib.hand_lists


def staging_rows(data: Path = DATA) -> list[dict[str, str]]:
    """Staging's rows of the device master (hartlib.railroad's read_staging_rows, so the master is read by one loader)."""
    return [row for _line, row in railroad.read_staging_rows(railroad.Sources.under(data).devices)]


def load_switches(data: Path = DATA) -> dict[int, Switch]:
    """Switch number -> Switch, in switches.csv order (hartlib.railroad.read_switches). Line numbers in errors
    count the header as 1."""
    s = railroad.Sources.under(data)
    return railroad.read_switches(s.switches, s.devices)


EDGES = hand_lists.EDGES
USS_CELLS = hand_lists.USS_CELLS
USS_PLANTS = hand_lists.USS_PLANTS
USS_TRACKS = hand_lists.USS_TRACKS


def load_mast_cells(data: Path = DATA) -> list[MastCell]:
    """mast_cells.csv in file order (the order the USS board draws the icons): hartlib.hand_lists.read_mast_cells,
    which stops (HandListError, a ValueError) on a row out of shape."""
    return hand_lists.read_mast_cells(data)


def load_uss_cells(data: Path = DATA) -> dict[tuple[int, int], dict]:
    """The USS CTC board's grid (uss_board_cells.csv), frozen from the hand-wired CATS desk on 2026-11-15:
    hartlib.hand_lists.read_uss_cells, (x, y) -> {tracks, name, blocks}, the shape gen_ctc_track_plan.build_block
    reads."""
    return hand_lists.read_uss_cells(data)


def load_uss_plants(data: Path = DATA) -> dict[tuple[int, int], str]:
    """(x, y) -> OS block of each switch plant on the USS CTC board grid (uss_board_plants.csv):
    hartlib.hand_lists.read_uss_plants."""
    return hand_lists.read_uss_plants(data)


def legs_by_os(switches: dict[int, Switch]) -> dict[str, tuple[Switch, Leg]]:
    return {leg.os_block: (sw, leg) for sw in switches.values() for leg in sw.legs}


def load_control_points(data: Path = DATA) -> list[dict[str, str]]:
    """The control points of every level that has desk areas in schematic/stations.csv (staging's only so far; each
    row carries its ``level``), with switches.csv, in the older control_points.csv shape
    (hartlib.railroad_facts.station_group_rows); ``switches`` is the OS-block list, e.g. "23a,23b,33"."""
    s = railroad.Sources.under(data)
    return railroad_facts.station_group_rows(s.stations, s.switches)


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


def place_levels(data: Path = DATA) -> dict[str, str]:
    """Place name -> level of every station of stations.csv and control point of interlockings.csv: the places a
    line block's cp lists (build_device_map.line_cp)."""
    src = railroad.Sources.under(data)
    out = {s.name: str(s.level) for s in railroad.read_stations(src.stations)}
    out.update({i.name: str(i.level) for i in railroad.read_interlockings(src.interlockings)})
    return out


def switch_block_levels(switches: dict[int, Switch]) -> dict[str, set[str]]:
    """Block name -> levels of the switches whose OS block it is or whose legs lead to it."""
    out: dict[str, set[str]] = {}
    for sw in switches.values():
        for leg in sw.legs:
            for name in (leg.os_block, leg.closed, leg.thrown):
                out.setdefault(name, set()).add(levels.level_text(sw.level))
    return out


def staging_levels(data: Path = DATA, switches: dict[int, Switch] | None = None,
                   rows: list[dict[str, str]] | None = None,
                   track_name: Callable[[str], str] | None = None) -> dict[tuple[str, str], str]:
    """(layer, user name) -> level for staging's rows of the device master (staging_rows).

    A turnout or feedback sensor of Switch N (``Switch N``, ``DCC Switch N``,
    ``FB Switch N R``) takes switches.csv; an OS block or a block a switch leg
    leads to takes its switch's level; any other row takes its control point's. A line block's cp lists the
    places it joins (stations of stations.csv, control points of interlockings.csv): it takes their level only
    when every place has one and they agree (place_levels), so a helix block, whose places are on two levels, takes
    its switch's.
    ``track_name`` maps a Layout Editor throat block to its track (Track S-R West
    -> Track S-R, through their shared occupancy sensor in tables.xml); without it
    a throat block is matched by its own name only. A row with none of these (a
    block in no place) is left out: check_layout_facts.py
    gives it the level of the blocks it joins, and reports any block whose switch
    and control point give different levels (here the switch wins).
    """
    switches = load_switches(data) if switches is None else switches
    rows = staging_rows(data) if rows is None else rows
    by_cp = cp_levels(data)
    places = place_levels(data)
    by_block = switch_block_levels(switches)
    out: dict[tuple[str, str], str] = {}
    for row in rows:
        layer, name = row["layer"], row["user_name"]
        level = ""
        m = _SWITCH_NAME.fullmatch(name) if layer in ("turnout", "fb") else None
        from_switch = by_block.get(track_name(name) if track_name else name, set()) if layer == "block" else set()
        if m and int(m.group(1)) in switches:
            level = levels.level_text(switches[int(m.group(1))].level)
        elif len(from_switch) == 1:
            level = next(iter(from_switch))
        elif row["role"] in devices.LINE_ROLES:     # its places: every one with a level, all the same
            got = [places.get(p) for p in row["cp"].split(";") if p]
            level = got[0] if None not in got and len(set(got)) == 1 else ""
        elif row["cp"] in by_cp:
            level = by_cp[row["cp"]]
        if level:
            out[(layer, name)] = level
    return out
