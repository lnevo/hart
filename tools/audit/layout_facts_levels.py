"""The data and levels part of tools/audit/check_layout_facts.py: switches.csv against stations.csv and the device
master (check_data), the staging masts against mast_cells.csv, the desks and tables.xml (check_mast_cells), and one
level for every control point, mast and block (check_levels)."""
from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from hartlib import devices, level_masts, parked, railroad
from hartlib import tables as hart_tables
from layout_facts_base import ADDED_LEVELS, MASTS, STAGING_LEVELS, Report, facts
from layout_facts_desks import desk_mast_blocks
from layout_facts_tables import Tables
from layout_facts_xml import LayoutFactsError

VIRTUAL_STAGING_MAST = "IF$vsm:"     # the system name prefix of a staging mast the desks do not draw


def listed_switches(data: Path) -> dict[int, str]:
    """{switch number: control point} of the switches stations.csv lists under each desk area."""
    listed: dict[int, str] = {}
    for cp in facts.load_control_points(data):
        for item in cp["switches"].split(","):
            num = re.match(r"\d+", item.strip())
            if num:
                listed[int(num.group(0))] = cp["cp_name"]
    return listed


def check_data(switches: dict[int, facts.Switch], data: Path, r: Report) -> None:
    """Each switch has a staging turnout row, and stations.csv puts it at the device master's control point."""
    listed = listed_switches(data)
    for sw in switches.values():
        n = f"Switch {sw.number}"
        if not sw.hardware:
            r.add(f"data:{n}", f"{n}: no staging turnout row with a system_name in the device master")
        if sw.number in listed and sw.cp != listed[sw.number]:
            r.add(f"data:{n}", f"{n}: stations.csv puts it at {listed[sw.number]}, "
                               f"the device master at {sw.cp or '-'}")
    for only in sorted(set(listed) - set(switches)):
        r.add(f"data:Switch {only}", f"Switch {only}: in stations.csv, not in switches.csv")


def protected_blocks(path: Path = MASTS) -> dict[str, str]:
    """Mast -> the block it protects (";" between several), from the staging masts (schematic/masts.csv's base level
    rows, hartlib.railroad.read_masts)."""
    return {m.mast: ";".join(m.protects) for m in railroad.read_masts(path, levels=STAGING_LEVELS) if m.protects}


def staging_mast_rows(path: Path = MASTS) -> list[dict]:
    """masts.csv's base level (staging) rows (hartlib.level_masts.read, which checks the file)."""
    return level_masts.read(path, levels=STAGING_LEVELS)


def _check_desk_masts(desks: Sequence[Path], r: Report) -> None:
    """Each desk draws each visible staging mast once, its lamp on the edge of the block it protects, and no mast
    masts.csv does not have (main and upper masts: check_level_desk)."""
    # the desks draw staging's visible masts, as the rule places them (masts.csv, ADR-024)
    want = {m["mast"] for m in staging_mast_rows() if not m["system_name"].startswith(VIRTUAL_STAGING_MAST)}
    protects = protected_blocks()
    level = level_masts.names(MASTS, levels=ADDED_LEVELS)
    for desk in desks:
        have = desk_mast_blocks(Path(desk))
        name = Path(desk).name
        for mast in sorted(want | (set(have) - level)):
            lamps = have.get(mast, [])
            if mast not in want:
                r.add(f"mast:{mast}", f"{mast}: {name} has a lamp for it, {MASTS.name} has no such visible mast")
            elif len(lamps) != 1:
                r.add(f"mast:{mast}", f"{mast}: {name} has {len(lamps)} lamps for it, not one")
            elif lamps[0] != protects.get(mast):
                r.add(f"mast:{mast}", f"{mast}: {name} has its lamp on the edge of {lamps[0]}, "
                                      f"but it protects {protects.get(mast)} ({MASTS.name})")


def check_mast_cells(data: Path, rows: list[dict[str, str]], desks: Sequence[Path], t: Tables, r: Report) -> None:
    """mast_cells.csv against the USS board's grid, the CATS desks (each of its masts once, its lamp on the edge of
    the block it protects, and no other mast), staging's mast rows of the device master and the masts' heads in
    tables.xml."""
    # mast_cells.csv is the USS board's, checked only while the board is in the tables (it is parked with it)
    uss_parked = "uss" in parked.parked_in(t.root)
    cells = [] if uss_parked else facts.load_mast_cells(data)
    grid = {} if uss_parked else facts.load_uss_cells(data)
    for c in cells:
        if not grid.get((c.x, c.y), {}).get("tracks"):
            r.add(f"mast:{c.mast}", f"{c.mast}: mast_cells.csv puts it at ({c.x}, {c.y}), a cell with no track on "
                                    f"the USS board's grid ({facts.USS_CELLS})")
    _check_desk_masts(desks, r)
    named = {row["user_name"] for row in rows if row["layer"] == "mast"}
    heads = {hart_tables.user_name(m): re.findall(r"\((IH\d+)\)", hart_tables.system_name(m))
             for m in hart_tables.masts(t.root)}
    for c in cells:
        if c.mast not in named:
            r.add(f"mast:{c.mast}", f"{c.mast}: in mast_cells.csv, not a staging mast row of the device master")
        if c.mast not in heads:
            r.add(f"mast:{c.mast}", f"{c.mast}: in mast_cells.csv, not a mast in tables.xml")
            continue
        got = heads[c.mast]
        if (c.uss_kind == "d1" and got != [c.uss_head]) or (c.uss_kind == "h2" and len(got) != 2):
            r.add(f"mast:{c.mast}", f"{c.mast}: mast_cells.csv draws it {c.uss_kind} "
                                    f"{c.uss_head or ''}".rstrip() + f", tables.xml gives it heads {got}")


def _check_block_levels(switches: dict[int, facts.Switch], by_cp: dict[str, str], rows: list[dict[str, str]],
                        t: Tables, r: Report) -> None:
    """A block's level from its switches (throat blocks through their track) against its control point's."""
    by_block = facts.switch_block_levels(switches)
    block_cp = {row["user_name"]: row["cp"] for row in rows if row["layer"] == "block"}
    for name, cps in block_cp.items():
        from_switch = by_block.get(t.track_name(name), set())
        if len(from_switch) > 1:
            r.add(f"level:{name}", f"{name}: its switches in switches.csv are on levels {sorted(from_switch)}")
            continue
        for cp in (p for p in cps.split(";") if p in by_cp):
            if from_switch and by_cp[cp] not in from_switch:
                r.add(f"level:{name}", f"{name}: is in {cp} (level {by_cp[cp]}), its switches in switches.csv "
                                       f"say level {next(iter(from_switch))}")


def check_levels(switches: dict[int, facts.Switch], data: Path, rows: list[dict[str, str]], t: Tables,
                 r: Report) -> None:
    """Each control point, mast and block has one level, and every source for it agrees."""
    by_cp = facts.cp_levels(data)
    for cp in facts.load_control_points(data):
        for item in cp["switches"].split(","):
            num = re.match(r"\d+", item.strip())
            sw = switches.get(int(num.group(0))) if num else None
            if sw and str(sw.level) != cp["level"]:
                r.add(f"level:Switch {sw.number}", f"Switch {sw.number}: switches.csv level {sw.level}, "
                                                   f"stations.csv puts {cp['cp_name']} on level {cp['level']}")
    # a line block's cp lists stations and control points of any level (check_device_master holds it); one row's is
    # a desk area of stations.csv
    for cp in sorted({row["cp"] for row in rows if row["cp"] and row["role"] not in devices.LINE_ROLES} - set(by_cp)):
        r.add(f"level:{cp}", f"{cp}: a cp of a staging row of the device master with no desk area (and no level) in stations.csv")
    _check_block_levels(switches, by_cp, rows, t, r)
    levels = facts.staging_levels(data, switches, rows, t.track_name)
    for row in rows:
        key = (row["layer"], row["user_name"])
        if row["layer"] not in ("mast", "block") or key in levels:
            continue
        name = row["user_name"]
        try:
            near = {levels.get(("block", t.track_name(b))) for b in t.joined_blocks(name)} - {None}
        except LayoutFactsError as exc:
            r.add(f"level:{name}", str(exc))
            continue
        if len(near) != 1:
            r.add(f"level:{name}", f"{name}: no control point and no switch in the device master or "
                                   f"switches.csv, and the blocks it joins in tables.xml are on levels "
                                   f"{sorted(near) or 'none'}; give it a cp")
