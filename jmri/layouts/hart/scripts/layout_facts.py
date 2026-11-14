#!/usr/bin/env python3
"""Railroad facts about each switch, read from jmri/layouts/hart/data/.

    switches.csv     one row per switch: level, number, Layout Editor turnout,
                     CATS inversion, its USS CTC lever and its hand (L or R,
                     blank where nobody has recorded it)
    switch_legs.csv  one row per OS block at the points: the block each leg
                     leads to when the switch is closed and when it is thrown

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


def name_map_levels(data: Path = DATA, switches: dict[int, Switch] | None = None) -> dict[tuple[str, str], str]:
    """(layer, public name) -> level for the identity rows of public_name_map.csv.

    A turnout or feedback sensor of Switch N (``Switch N``, ``DCC Switch N``,
    ``FB Switch N R``) takes switches.csv; an OS block or a block a switch leg
    leads to takes its switch's level; any other row takes its control point's.
    A row with none of these (a main between control points, Track Main West) is
    left out: check_layout_facts.py gives it the level of the blocks it joins.
    Where an OS block's switch and its control point disagree, the switch wins
    here and the check reports it.
    """
    switches = load_switches(data) if switches is None else switches
    by_cp = cp_levels(data)
    by_block: dict[str, set[str]] = {}
    for sw in switches.values():
        for leg in sw.legs:
            for name in (leg.os_block, leg.closed, leg.thrown):
                by_block.setdefault(name, set()).add(sw.level)
    out: dict[tuple[str, str], str] = {}
    for row in identity_rows(data):
        layer, name = row["layer"], row["proposed"]
        level = ""
        m = _SWITCH_NAME.fullmatch(name) if layer in ("turnout", "fb") else None
        if m and int(m.group(1)) in switches:
            level = switches[int(m.group(1))].level
        elif layer == "block" and len(by_block.get(name, ())) == 1:
            level = next(iter(by_block[name]))
        elif row["cp"] in by_cp:
            level = by_cp[row["cp"]]
        if level:
            out[(layer, name)] = level
    return out
