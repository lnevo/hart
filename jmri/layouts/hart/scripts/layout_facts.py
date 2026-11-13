#!/usr/bin/env python3
"""Railroad facts about each switch, read from jmri/layouts/hart/data/.

    switches.csv     one row per switch: level, number, Layout Editor turnout,
                     CATS inversion and its USS CTC lever
    switch_legs.csv  one row per OS block at the points: the block each leg
                     leads to when the switch is closed and when it is thrown

Hardware, DCC address and control point come from the canonical turnout row
of public_name_map.csv (current == proposed); control_points.csv lists which
switches each control point holds. Nothing here is copied from those files.

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
from dataclasses import dataclass
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
YES = {"yes": True, "no": False}


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
        nm = names.get(f"Switch {n}", {})
        dcc = re.search(r"DCC:\s*(\d+)", nm.get("comment", ""))
        out[n] = Switch(
            number=n,
            level=row["level"],
            le_ident=row["le_ident"],
            cats_inverted=_yes(row["cats_inverted"], where),
            ctc_is=ctc_is,
            ctc_signals=_yes(row["ctc_signals"], where),
            legs=tuple(legs.pop(n)),
            hardware=nm.get("hardware", ""),
            dcc=dcc.group(1) if dcc else "",
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
