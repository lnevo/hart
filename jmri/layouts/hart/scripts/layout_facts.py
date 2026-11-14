#!/usr/bin/env python3
"""Railroad facts about each switch, read from jmri/layouts/hart/data/.

    switches.csv     one row per switch: level, number, Layout Editor turnout,
                     CATS inversion, its USS CTC lever and its hand (L or R,
                     blank where nobody has recorded it)
    switch_legs.csv  one row per OS block at the points: the block each leg
                     leads to when the switch is closed and when it is thrown
    mast_cells.csv   one row per mast on the CATS desk: its cell and edge, and
                     how the USS CTC board draws it (read by wire_digicon.py
                     and gen_ctc_track_plan.py)

Hardware, DCC address (its own ``dcc`` column) and control point come from the
canonical turnout row of public_name_map.csv (current == proposed); control_points.csv lists which
switches each control point holds and its level. Nothing here is copied from
those files.

Level is held once per switch (switches.csv) and once per control point
(control_points.csv). A mast, head, block or occupancy sensor has no level of
its own: it takes the level of its control point (the ``cp`` column of
public_name_map.csv), and an OS block or a switch leg takes its switch's.
name_map_levels() resolves them. No grouping above the control point exists
yet, so there is no district column; when the new levels need one, it goes on
control_points.csv beside ``level``.

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
from hartlib import paths  # noqa: E402

DATA = paths.LAYOUT_DATA
YES = {"yes": True, "no": False}
HANDS = {"", "L", "R"}
_SWITCH_NAME = re.compile(r"(?:DCC |FB )?Switch (\d+)(?: [NR])?")


@dataclass(frozen=True)
class Leg:
    os_block: str
    closed: str
    thrown: str


@dataclass(frozen=True)
class MastCell:
    """A mast's lamp on the CATS desk and its icon on the USS CTC board."""
    mast: str
    x: int
    y: int
    edge: str          # SEC_EDGE of the desk cell that holds the SECSIGNAL
    uss_facing: str    # E or W on the USS board
    uss_kind: str      # h2: mast icon (two heads); d1: head icon on the only head
    uss_head: str      # that head for d1, blank for h2
    sig_location: str = ""  # PANELSIGNAL SIGLOCATION / SIGORIENT to set, blank to keep the Designer's
    sig_orient: str = ""


@dataclass(frozen=True)
class Switch:
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


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]


def _yes(value: str, where: str) -> bool:
    if value not in YES:
        raise ValueError(f"{where}: expected yes or no, got {value!r}")
    return YES[value]


def _name_map_turnouts(data: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for row in _rows(data / "public_name_map.csv"):
        if row["layer"] == "turnout" and row["current"] == row["proposed"]:
            out[row["current"]] = row
    return out


def identity_rows(data: Path = DATA) -> list[dict[str, str]]:
    """public_name_map.csv rows whose current name is the live one (current == proposed)."""
    return [row for row in _rows(data / "public_name_map.csv") if row["current"] == row["proposed"]]


def load_switches(data: Path = DATA) -> dict[int, Switch]:
    """Switch number -> Switch, in switches.csv order. Line numbers in errors count the header as 1."""
    legs: dict[int, list[Leg]] = {}
    os_line: dict[str, int] = {}
    for line, row in enumerate(_rows(data / "switch_legs.csv"), start=2):
        os_name = row["os_block"]
        if os_name in os_line:
            raise ValueError(f"switch_legs.csv lines {os_line[os_name]} and {line}: "
                             f"both list {os_name}; an OS block belongs to one switch")
        os_line[os_name] = line
        legs.setdefault(int(row["switch"]), []).append(
            Leg(os_name, row["closed_leg"], row["thrown_leg"])
        )
    names = _name_map_turnouts(data)
    out: dict[int, Switch] = {}
    seen: dict[int, tuple[int, str]] = {}
    lever: dict[int, tuple[int, int]] = {}
    for line, row in enumerate(_rows(data / "switches.csv"), start=2):
        n = int(row["switch"])
        where = f"switches.csv line {line} (Switch {n})"
        if n in seen:
            first, level = seen[n]
            raise ValueError(f"switches.csv lines {first} (level {level}) and {line} (level {row['level']}) "
                             f"both use Switch {n}; switch numbers are unique railroad-wide")
        seen[n] = (line, row["level"])
        if n not in legs:
            raise ValueError(f"{where}: no rows in switch_legs.csv")
        ctc_is = int(row["ctc_is"])
        if ctc_is in lever:
            first, other = lever[ctc_is]
            raise ValueError(f"switches.csv lines {first} (Switch {other}) and {line} (Switch {n}) "
                             f"both use USS lever IS{ctc_is}")
        lever[ctc_is] = (line, n)
        hand = row.get("hand", "")
        if hand not in HANDS:
            raise ValueError(f"{where}: hand is L, R or blank, got {hand!r}")
        nm = names.get(f"Switch {n}", {})
        out[n] = Switch(
            number=n,
            level=row["level"],
            le_ident=row["le_ident"],
            cats_inverted=_yes(row["cats_inverted"], where),
            ctc_is=ctc_is,
            ctc_signals=_yes(row["ctc_signals"], where),
            legs=tuple(legs.pop(n)),
            hand=hand,
            hardware=nm.get("hardware", ""),
            dcc=nm.get("dcc", ""),
            cp=nm.get("cp", ""),
        )
    if legs:
        raise ValueError(f"switch_legs.csv: switches not in switches.csv: {sorted(legs)}")
    return out


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


def legs_by_os(switches: dict[int, Switch]) -> dict[str, tuple[Switch, Leg]]:
    return {leg.os_block: (sw, leg) for sw in switches.values() for leg in sw.legs}


def load_control_points(data: Path = DATA) -> list[dict[str, str]]:
    """control_points.csv rows; ``switches`` stays the quoted list, e.g. "23a,23b,33"."""
    return _rows(data / "control_points.csv")


def station_names(data: Path = DATA) -> set[str]:
    """Control point names as the desks print them, e.g. EAST END."""
    return {row["cp_name"].upper() for row in load_control_points(data)}


def cp_levels(data: Path = DATA) -> dict[str, str]:
    """Control point name -> level, from control_points.csv. Every row needs a level."""
    out: dict[str, str] = {}
    for line, row in enumerate(load_control_points(data), start=2):
        if not row.get("level"):
            raise ValueError(f"control_points.csv line {line} ({row['cp_name']}): no level")
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
    """(layer, public name) -> level for the identity rows of public_name_map.csv.

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
