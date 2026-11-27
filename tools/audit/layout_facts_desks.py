"""The CATS desk part of tools/audit/check_layout_facts.py: each desk's staging plants against switches.csv
(check_desk), its main and upper plants and masts against the internal turnouts, masts.csv and tables.xml
(check_level_desk), and its main and upper blocks' sensors (check_level_sensors)."""
from __future__ import annotations

import functools
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import NamedTuple

from hartlib import devices, level_devices, level_masts, paths, tables_build
from hartlib import tables as hart_tables
from layout_facts_base import ADDED_LEVELS, CLOSED, DEVICE_MAP, MASTS, PLAIN_TURNOUTS, Cells, Report, facts, trace
from layout_facts_tables import Tables, desk_leg
from layout_facts_xml import LayoutFactsError, desk_root, need, trackplan


class DeskPlants(NamedTuple):
    """A desk's cells and its staging plants: {OS block: plant cell}."""
    cells: Cells
    plants: dict[str, tuple[int, int]]


class BlockRow(NamedTuple):
    """A block row of the device master and its line number."""
    line: int
    row: dict[str, str]


def desk_plants(path: Path, r: Report) -> DeskPlants:
    """The desk's cells and staging plants; a desk whose plants cannot be read is reported and has none."""
    cells = trace.track_cells(trackplan(path))
    try:
        plants = trace.desk_plants(cells, bound=True, level_turnouts=level_turnouts())     # staging's plants
    except trace.PlantError as err:
        r.add(f"cats:{path.name}", f"{path.name}: {err}")
        plants = {}
    return DeskPlants(cells, plants)


@functools.cache
def level_turnouts() -> dict[str, str]:
    """{user name: bean name} of the main and upper turnouts, from the device master's rows
    (hartlib.tables_build.level_turnouts), so a swapped turnout is still one."""
    return tables_build.level_turnouts([r.cells() for r in devices.load(DEVICE_MAP)])


@functools.cache
def block_rows() -> dict[str, BlockRow]:
    """{block name: its row} of the block rows of levels 2 and 3 of the device master; LayoutFactsError when it has
    none."""
    rows = {row["user_name"]: BlockRow(n, row) for n, row in devices.device_map_lines(("2", "3"), DEVICE_MAP)
            if row["layer"] == "block"}
    if not rows:
        raise LayoutFactsError(f"{paths.rel(DEVICE_MAP)} has no block rows")
    return rows


@functools.cache
def device_map_rows() -> frozenset[str]:
    """The main and upper block names (the block rows of levels 2 and 3 of the device master)."""
    return frozenset(block_rows())


@functools.cache
def device_map_blocks() -> frozenset[str]:
    """The device map's main and upper block names, a double crossover's corners (role xover_corner) also without
    the corner letter (the middle of its X, a desk-only block)."""
    rows = block_rows()
    corners = {n for n, br in rows.items()
               if devices.row_role(br.row, f"{paths.rel(DEVICE_MAP)}: {devices.row_text(br.row)}") == "xover_corner"}
    return frozenset(set(rows) | {re.sub(r"(?<=\d)[a-d]$", "", n) for n in corners})


@functools.cache
def field_sensors() -> frozenset[str]:
    """The JMRI names of the main and upper detectors swapped to a field sensor by their row (assignment field,
    ADR-028): a column of the row, not its level, says a block's sensor is virtual."""
    return frozenset(r.jmri_name for r in devices.load(DEVICE_MAP) if r.level_cell in level_devices.LEVELS
                     and r.layer == "occupancy" and r.swapped)


def desk_block_names(path: Path) -> set[str]:
    """Every named BLOCK of a CATS desk."""
    return {desk_block for b in desk_root(path).iter("BLOCK") if (desk_block := b.get("NAME"))}


def desk_mast_blocks(path: Path) -> dict[str, list[str | None]]:
    """Mast -> the block on the edge of each lamp of that name on a CATS desk (the block the mast protects)."""
    out: dict[str, list[str | None]] = {}
    for se in desk_root(path).iter("SEC_EDGE"):
        sig = se.find("SECSIGNAL")
        mast = (sig.text or "").strip() if sig is not None else ""
        if not mast:
            continue
        blk = se.find("BLOCK")
        out.setdefault(mast, []).append(blk.get("NAME") if blk is not None else None)
    return out


def check_level_sensors(desk: str, root: ET.Element, t: Tables, r: Report) -> None:
    """Each main and upper desk block (a device map block row) reports, occupied (close) and unoccupied (throw), the
    occupancy sensor its Layout Editor block has in tables.xml: a virtual IS:HART:C3:B: sensor (hartlib.level_devices),
    or the field sensor of a detector swapped in by its row (field_sensors), of that name and system name. A desk-only
    block (the middle of a double crossover's X) reports none."""
    seen = set()
    for b in root.iter("BLOCK"):               # a desk block is listed once per edge it has: checked once
        name = b.get("NAME")
        if not name or name not in device_map_blocks() or name in seen:
            continue
        seen.add(name)
        specs = {tag: [((i.get("JMRIPREFIX") or "") + (i.get("DECADDR") or ""), (i.text or "").strip())
                       for i in b.findall(f"{tag}/IOSPEC")] for tag in ("OCCUPIEDSPEC", "UNOCCUPIEDSPEC")}
        if name not in device_map_rows():
            if any(specs.values()):
                r.add(f"cats-track:{name}", f"{desk}: desk-only block {name} reports a sensor; it has none")
            continue
        user = t.block_sensor.get(name)
        system = t.sensor_system.get(user or "")
        occ = b.find("OCCUPIEDSPEC/IOSPEC")
        occ_user = occ.get("USER_NAME") if occ is not None else None
        want = {"OCCUPIEDSPEC": [(system, "close")], "UNOCCUPIEDSPEC": [(system, "throw")]}
        if not (level_devices.is_block_sensor(system or "") or system in field_sensors()) or specs != want \
                or occ_user != user:
            got = "; ".join(f"{tag} " + (" ".join(f"{sn} {cmd}" for sn, cmd in v) or "none")
                            for tag, v in specs.items())
            r.add(f"cats-track:{name}", f"{desk}: block {name} reports {got} (user name {occ_user}); tables.xml "
                                        f"binds it to {user or 'no sensor'} ({system or 'none'})")


def _check_plant_routes(desk: str, sw: facts.Switch, leg: facts.Leg, dp: DeskPlants, t: Tables, r: Report) -> None:
    """The routes of the staging plant in `leg`'s OS block: each commands and reports the switch's turnout, leads to
    the leg switches.csv gives its command, and NORMAL is on the closed leg (thrown when CATS-inverted)."""
    n = f"Switch {sw.number}"
    xy = dp.plants.get(leg.os_block)
    if xy is None:
        r.add(f"cats:{n}", f"{n}: {desk} has no plant in {leg.os_block}")
        return
    for ri in dp.cells[xy].iter("ROUTEINFO"):
        edge = ri.get("ROUTEID")
        ios = ri.find("ROUTECOMMAND/IOSPEC")
        rep = ri.find("SELECTEDREPORT/IOSPEC")
        if ios is None:
            r.add(f"cats:{n}", f"{n}: {desk} {leg.os_block} leg {edge} has no ROUTECOMMAND")
            continue
        cmd = (ios.text or "").strip()
        if ios.get("USER_NAME") != sw.turnout:
            r.add(f"cats:{n}", f"{n}: {desk} {leg.os_block} leg {edge} commands "
                               f"{ios.get('USER_NAME')}, switches.csv says {sw.turnout}")
        if rep is None or (rep.text or "").strip() != cmd:
            r.add(f"cats:{n}", f"{n}: {desk} {leg.os_block} leg {edge} reports "
                               f"{(rep.text or '').strip() if rep is not None else '-'} but commands {cmd}")
        dest = desk_leg(t, dp.cells, xy, need(ri, "ROUTEID"), leg.os_block)
        want = {"close": leg.closed, "throw": leg.thrown}.get(cmd)
        if dest != want:
            r.add(f"cats:{n}", f"{n}: {desk} {leg.os_block} leg {edge} ({cmd}) leads to {dest}; "
                               f"switches.csv says {cmd} leads to {want}")
        normal = ri.get("NORMAL") == "true"
        want_normal = (cmd == "throw") if sw.cats_inverted else (cmd == "close")
        if normal != want_normal:
            r.add(f"cats:{n}", f"{n}: {desk} {leg.os_block} NORMAL is the {cmd} leg {edge} = {normal}; "
                               f"switches.csv cats_inverted={'yes' if sw.cats_inverted else 'no'} "
                               f"puts NORMAL on the {'thrown' if sw.cats_inverted else 'closed'} leg")


def check_desk(path: Path, switches: dict[int, facts.Switch], t: Tables, r: Report) -> None:
    """A desk's staging plants and blocks against switches.csv and tables.xml."""
    desk = path.name
    dp = desk_plants(path, r)
    by_os = facts.legs_by_os(switches)
    for os_name, at in dp.plants.items():
        if os_name not in by_os:
            r.add(f"cats:{os_name}", f"{desk}: plant at {at} is in {os_name}, which switches.csv does not list")
    jmri_blocks = t.block_names()
    names = desk_block_names(path)
    # the main and upper blocks are drawn from the device map, before the tables may hold them: a staging-only
    # candidate has none, so all of them may be missing; tables with main and upper must hold every one but the
    # middle of a double crossover's X (named without the corner letter, a desk-only block with no sensor), and each
    # must report its virtual sensor (check_level_sensors)
    level_here = bool(jmri_blocks & device_map_blocks())
    dark = (device_map_blocks() - device_map_rows() if level_here else device_map_blocks()) & names
    for name in sorted(names - dark - jmri_blocks):
        r.add(f"cats-track:{name}", f"{desk}: block {name} is not a Layout Editor block in tables.xml")
    if level_here:
        check_level_sensors(desk, desk_root(path), t, r)
    for sw in switches.values():
        n = f"Switch {sw.number}"
        for leg in sw.legs:
            for want in (leg.closed, leg.thrown):
                if want not in names:
                    r.add(f"cats:{n}", f"{n}: switches.csv leg {want} is not a block on {desk}")
            _check_plant_routes(desk, sw, leg, dp, t, r)


def desk_block_of(name: str, blocks: set[str]) -> str:
    """The desk block a main or upper block is drawn as: itself, or for a double crossover's corner block (its OS
    block's name and a letter a to d) the crossover's one desk block."""
    if name in blocks:
        return name
    m = re.fullmatch(r"(OS Switch \d+)[a-d]", name)
    return m.group(1) if m and m.group(1) in blocks else name


def same_place(desk: str | None, le: str | None) -> bool:
    """A main or upper leg's desk block names the Layout Editor's: the same block, or the OS block of a switch at one
    end of a track the desk draws inside its switches' OS blocks (OS Switch 107 for Track 107-109)."""
    if desk is None or le is None:
        return False
    if desk == le:
        return True
    m, t = re.fullmatch(r"OS Switch (\d+)", desk), re.fullmatch(r"Track (\d+)-(\d+)(?: \d)?", le)
    return bool(m and t and m.group(1) in t.groups())


def _check_level_plant(desk: str, cells: Cells, os_name: str, xy: tuple[int, int], points: str,
                       level: dict[str, str], t: Tables, r: Report) -> str | None:
    """One main or upper plant: one internal turnout of tables.xml commanded and reported, close and throw, NORMAL on
    close, and the legs not the Layout Editor's swapped. The turnout's user name, or None (reported) when the plant
    does not command one turnout both ways."""
    cmds: dict[str, str | None] = {}
    users: set[str | None] = set()
    for ri in cells[xy].findall(f"SEC_EDGE[@EDGE='{points}']/SWITCHPOINTS/ROUTEINFO"):
        edge = ri.get("ROUTEID")
        ios, report = ri.find("ROUTECOMMAND/IOSPEC"), ri.find("SELECTEDREPORT/IOSPEC")
        if ios is None:
            r.add(f"cats:{os_name}", f"{desk}: plant at {xy} in {os_name} leg {edge} has no ROUTECOMMAND")
            continue
        cmd = (ios.text or "").strip()
        user, system = ios.get("USER_NAME"), (ios.get("JMRIPREFIX") or "") + (ios.get("DECADDR") or "")
        users.add(user)
        if level.get(user or "") != system:
            r.add(f"cats:{user}", f"{desk}: plant at {xy} in {os_name} commands {user} ({system}); tables.xml "
                                  f"has {level.get(user or '') or 'no such main or upper turnout'}")
        if report is None or (report.text or "").strip() != cmd or report.get("USER_NAME") != user:
            r.add(f"cats:{user}", f"{desk}: plant at {xy} in {os_name} leg {edge} does not report the {cmd} "
                                  f"of {user} it commands")
        if (ri.get("NORMAL") == "true") != (cmd == "close"):
            r.add(f"cats:{user}", f"{desk}: plant at {xy} in {os_name}: NORMAL is not its close leg")
        cmds[cmd] = desk_leg(t, cells, xy, need(ri, "ROUTEID"), os_name)          # as leg_block reads the Layout Editor
    if len(users) != 1 or set(cmds) != {"close", "throw"}:
        r.add(f"cats:{os_name}", f"{desk}: plant at {xy} in {os_name} commands {sorted(map(str, users))} with "
                                 f"{sorted(cmds)}; one turnout, close and throw")
        return None
    user = users.pop()
    lts = [lt for lt in t.layout_turnouts.values() if lt.get("turnoutname") in (user, level.get(user or ""))]
    if len(lts) == 1 and lts[0].get("type") in PLAIN_TURNOUTS:
        lt = lts[0]
        b = t.leg_block(lt.get("ident"), "B", lt.get("blockname"))     # a turnout with no block still reports
        c = t.leg_block(lt.get("ident"), "C", lt.get("blockname"))
        closed, thrown = (b, c) if lt.get("continuing", CLOSED) == CLOSED else (c, b)
        if closed != thrown and (same_place(cmds["close"], thrown) or same_place(cmds["throw"], closed)):
            r.add(f"cats:{user}", f"{desk}: {user} closes to {cmds['close']} and throws to {cmds['throw']}; the "
                                  f"Layout Editor ({lt.get('ident')}) closes to {closed} and throws to {thrown}")
    return user


def _check_level_masts(path: Path, t: Tables, r: Report) -> None:
    """Each mast of masts.csv's main and upper rows: one lamp on the desk (none for a virtual mast), on the edge of
    the block it protects, and that mast in tables.xml."""
    desk = path.name
    have = desk_mast_blocks(path)
    blocks = desk_block_names(path)
    masts = {hart_tables.user_name(m): hart_tables.system_name(m) for m in hart_tables.masts(t.root)}
    for row in level_masts.read(MASTS, levels=ADDED_LEVELS):
        mast, lamps = row["mast"], have.get(row["mast"], [])
        if level_masts.is_level_virtual(row["system_name"]):
            if lamps:                   # a hidden destination mast at a buffer stop: no lamp on the desk
                r.add(f"mast:{mast}", f"{mast}: {desk} has a lamp for it, but it is a virtual mast")
        elif len(lamps) != 1:
            r.add(f"mast:{mast}", f"{mast}: {desk} has {len(lamps)} lamps for it, not one")
        elif lamps[0] != desk_block_of(row["protects"], blocks):
            r.add(f"mast:{mast}", f"{mast}: {desk} has its lamp on the edge of {lamps[0]}, but it protects "
                                  f"{row['protects']} ({level_masts.PATH.name})")
        if masts.get(mast) != row["system_name"]:
            r.add(f"mast:{mast}", f"{mast}: tables.xml has {masts.get(mast) or 'no such mast'}, "
                                  f"{level_masts.PATH.name} says {row['system_name']}")


def check_level_desk(path: Path, t: Tables, r: Report) -> None:
    """The main and upper part of a generated desk: its plants against the internal turnouts and the Layout Editor in
    tables.xml, its masts against masts.csv's main and upper rows and tables.xml."""
    desk = path.name
    cells = trace.track_cells(trackplan(path))
    try:
        plants = trace.level_plants(cells, level_turnouts())
    except trace.PlantError as err:
        r.add(f"cats:{desk}", f"{desk}: {err}")
        return
    level = {user: t.turnouts[user].system for user in level_turnouts() if user in t.turnouts}
    if not level:
        if t.block_names() & device_map_blocks():
            r.add(f"cats:{desk}", f"{desk}: tables.xml holds main/upper blocks but none of the device master's main "
                                  "and upper turnouts for the desk's main and upper plants to command")
        return              # a staging-only candidate (test_le_cutover): tables with no main or upper level to check
    commanded = {user for os_name, xy, points in plants
                 if (user := _check_level_plant(desk, cells, os_name, xy, points, level, t, r)) is not None}
    for user in sorted(set(level) - commanded):
        r.add(f"cats:{user}", f"{desk}: no plant commands main or upper turnout {user}")
    _check_level_masts(path, t, r)
