#!/usr/bin/env python3
"""The Layout Editor, the CATS desks and the USS CTC must agree with the switch facts.

    python3 tools/audit/check_layout_facts.py

The facts are jmri/layouts/hart/data/switches.csv and switch_legs.csv (read by
layout_facts.py), with hardware, DCC address and control point from
public_name_map.csv and control_points.csv. For every switch this checks:

Layout Editor (tables.xml)
  - the turnout's hardware and DCC address, and the layout turnout's name and OS block;
  - which leg the continuing sense closes to (plain turnouts);
  - the stored block paths: the closed leg needs Closed or no setting, the thrown
    leg Thrown, and neither may be reached with the other setting.
CATS desks (HART_CTC.xml, HART_ABS.xml: the live desks, generated from the schematic since the CATS cut-over)
  - each bound plant's turnout, the leg each command (close/throw) leads to, and which
    leg is NORMAL (the closed one, unless the switch is CATS-inverted); the main and upper
    plants (internal turnouts) are checked below;
  - every block bound to a detector is a Layout Editor block (main and upper ones only where the tables hold those
    levels), and each main and upper desk block reports the virtual sensor (IS:HART:C3:B:) its block has in
    tables.xml;
  - the desk's staging masts are mast_cells.csv's, each once, its lamp on the edge of the block it
    protects (staging_le/masts.csv); each is in the name map and tables.xml, with one head
    (the one named) for a d1 icon and two for h2;
  - main and upper (bound to their internal turnouts IT:HART:C3:<n>, their masts and their blocks' virtual
    sensors): each plant commands and reports one internal turnout of tables.xml, NORMAL on its close
    leg, and no plain turnout's close and throw legs are the Layout Editor's swapped; every internal
    turnout has a plant (a double crossover four points, one turnout); each mast of
    main_upper_masts.csv has one lamp, on the edge of the block it protects (a double crossover's
    corner is its one desk block), and is that mast in tables.xml.
Levels (control_points.csv, switches.csv, public_name_map.csv)
  - each control point's switches are on its level, and every cp in the name map has a row;
  - every mast and block has one level: its switch's, its control point's, or, for a
    main between control points, the one level of the blocks its tables.xml paths join.
USS CTC (CTC code buttons in tables.xml, ctc/GUIObjects.xml and the copy in tables.xml)
  - the code button's turnout, OS sensors, lever and signal levers;
  - the lever, the points dot and its polarity in the switch's column;
  - the track jewels and labels are the ones the board's grid gives (uss_board_cells.csv,
    frozen from the hand-wired CATS desk on 2026-11-15; gen_ctc_track_plan.py reads it too).

Track names are the CATS occupancy names; a Layout Editor throat block such as
Track S-R West (same occupancy sensor as Track S-R) counts as Track S-R.
A failure names the switch or track and the two sources that disagree.
KNOWN lists differences already reported to the owner, each by its exact message;
they print but do not fail, any other message fails, and a KNOWN message that no
longer happens fails so the list stays honest.
"""
from __future__ import annotations

import argparse
import csv
import functools
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import level_masts, parked, paths, tables as hart_tables  # noqa: E402
from hartlib.names import split_dcc  # noqa: E402

ROOT = paths.REPO_ROOT
HART = paths.LAYOUT_DIR
sys.path.insert(0, str(paths.LAYOUT_SCRIPTS))
sys.path.append(str(paths.CATS_DIR / "scripts"))

import layout_facts as facts  # noqa: E402
import digicon_trace as trace  # noqa: E402

TABLES = paths.TABLES_XML
GUI = HART / "ctc/GUIObjects.xml"
DESKS = (ROOT / "cats/panels/HART_CTC.xml", ROOT / "cats/panels/HART_ABS.xml")
MASTS = paths.LAYOUT_DATA / "schematic/staging_le/masts.csv"     # each staging mast's facing and protected blocks
OCCUPANCY = ROOT / "cats/data/occupancy_bindings.csv"
DEVICE_MAP = paths.LAYOUT_DATA / "schematic/device_map_main_upper.csv"   # the main and upper block names

CLOSED, THROWN = "2", "4"
PLAIN_TURNOUTS = {"RH_TURNOUT", "LH_TURNOUT", "WYE_TURNOUT"}

# Differences already reported to the owner and accepted, each by its exact message.
# Empty since the 2026-11-12 USS rebuild (EH-1/EH-3 swap, Switch 37/39 dots).
KNOWN: dict[str, str] = {}


class Report:
    def __init__(self) -> None:
        self.found: dict[str, list[str]] = {}

    def add(self, key: str, message: str) -> None:
        self.found.setdefault(key, []).append(message)

    def messages(self) -> list[str]:
        return [m for msgs in self.found.values() for m in msgs]

    def failures(self, known: dict[str, str]) -> list[str]:
        """Every message not in ``known`` (matched exactly), and every ``known`` message that did not happen."""
        seen = self.messages()
        out = [m for m in seen if m not in known]
        out += [f"KNOWN entry no longer happens; remove it from KNOWN: {m}" for m in known if m not in seen]
        return out

    def known(self, known: dict[str, str]) -> list[str]:
        """One line per KNOWN reason that happened, with its count."""
        hits = Counter(known[m] for m in self.messages() if m in known)
        return [f"{reason} ({count} difference(s))" for reason, count in hits.items()]


def _cached(load, path: Path):
    """``load(path)`` once per file version: a desk or tables.xml is read by several checks."""
    st = Path(path).stat()
    return _load_cached(load, str(Path(path).resolve()), (st.st_mtime_ns, st.st_size))


@functools.lru_cache(maxsize=None)
def _load_cached(load, path: str, _stamp: tuple[int, int]):
    return load(path)


def parse(path: Path) -> ET.ElementTree:
    """ET.parse, once per file version (a desk or GUIObjects.xml)."""
    return _cached(ET.parse, path)


def parse_tables(path: Path) -> ET.Element:
    """Root of tables.xml via hartlib, once per file version."""
    return _cached(hart_tables.read, path)


# ---------------------------------------------------------------- tables.xml

class Tables:
    def __init__(self, path: Path, root: ET.Element | None = None) -> None:
        """The tables at `path`, or `root` when the caller holds them parsed already (the USS CTC view)."""
        self.path = path
        self.root = parse_tables(path) if root is None else root
        self.block_user: dict[str, str] = {}
        self.block_sensor: dict[str, str] = {}
        self.paths: dict[str, list[tuple[str, list[tuple[str, str]]]]] = {}
        for b in self.root.iter("block"):
            sn = b.get("systemName") or ""
            user = (b.findtext("userName") or "").strip()
            if user:
                self.block_user[sn] = user
            sensor = (b.findtext("occupancysensor") or "").strip()
            if sensor and user:
                self.block_sensor[user] = sensor
            for p in b.findall("path"):
                settings = [(bs.find("turnout").get("systemName"), bs.get("setting"))
                            for bs in p.findall("beansetting") if bs.find("turnout") is not None]
                self.paths.setdefault(user, []).append((p.get("block"), settings))
        self.turnouts: dict[str, tuple[str, str]] = {}
        for t in hart_tables.turnouts(self.root):
            user = (t.findtext("userName") or "").strip()
            if user:
                self.turnouts[user] = ((t.findtext("systemName") or "").strip(),
                                       (t.findtext("comment") or "").strip())
        self.layout_turnouts = {lt.get("ident"): lt for lt in self.root.iter("layoutturnout")}
        self.segments = {s.get("ident"): s for s in self.root.iter("tracksegment")}
        self.points = {p.get("ident"): p for p in self.root.iter("positionablepoint")}
        self.sensor_system = {
            (s.findtext("userName") or "").strip(): (s.findtext("systemName") or "").strip()
            for s in self.root.iter("sensor")
        }

    def track_name(self, user: str | None) -> str | None:
        """Track S-R West -> Track S-R when both report on the same occupancy sensor."""
        if not user:
            return user
        m = re.match(r"^(.*) (?:East|West)$", user)
        if m and m.group(1) in self.block_sensor and \
                self.block_sensor.get(m.group(1)) == self.block_sensor.get(user):
            return m.group(1)
        return user

    def block_names(self) -> set[str]:
        return {self.track_name(u) for u in self.block_user.values()}

    def _turnout_block(self, lt: ET.Element, conn: str) -> str | None:
        attr = {"A": "blockname", "B": "blockbname", "C": "blockcname", "D": "blockdname"}[conn]
        return lt.get(attr) or lt.get("blockname")

    def leg_block(self, ident: str, conn: str, own: str) -> str | None:
        """Block reached from connection B or C of a layout turnout, past its own OS block."""
        came = (ident, f"TURNOUT_{conn}")
        seg = next((s for s in self.segments.values()
                    for i in ("1", "2")
                    if (s.get(f"connect{i}name"), s.get(f"type{i}")) == came), None)
        for _ in range(200):
            if seg is None:
                return None
            if seg.get("blockname") and seg.get("blockname") != own:
                return seg.get("blockname")
            ends = [(seg.get("connect1name"), seg.get("type1")), (seg.get("connect2name"), seg.get("type2"))]
            name, kind = ends[1] if ends[0] == came else ends[0]
            if kind == "POS_POINT":
                pp = self.points.get(name)
                if pp is None:
                    return None
                here = seg.get("ident")
                nxt = pp.get("connect2name") if pp.get("connect1name") == here else pp.get("connect1name")
                came = (name, "POS_POINT")
                seg = self.segments.get(nxt) if nxt else None
            elif kind and kind.startswith("TURNOUT_") and name in self.layout_turnouts:
                block = self._turnout_block(self.layout_turnouts[name], kind[-1])
                return block if block != own else None
            else:
                return None
        return None


def check_tables(sw: facts.Switch, t: Tables, r: Report) -> None:
    n = f"Switch {sw.number}"
    system, comment = t.turnouts.get(sw.turnout, ("", ""))
    if not system:
        r.add(f"le:{n}", f"{n}: no turnout {sw.turnout!r} in tables.xml")
        return
    if sw.hardware and system != sw.hardware:
        r.add(f"le:{n}", f"{n}: tables.xml turnout is {system}, public_name_map.csv says {sw.hardware}")
    try:
        dcc = split_dcc(comment)[1]
    except ValueError as err:
        dcc = "?"
        r.add(f"le:{n}", f"{n}: tables.xml {err}")
    if sw.dcc and dcc != sw.dcc:
        r.add(f"le:{n}", f"{n}: tables.xml comment DCC {dcc or '-'}, "
                         f"public_name_map.csv says DCC {sw.dcc}")
    lt = t.layout_turnouts.get(sw.le_ident)
    if lt is None:
        r.add(f"le:{n}", f"{n}: switches.csv names layout turnout {sw.le_ident}, not in tables.xml")
        return
    if lt.get("turnoutname") not in (sw.turnout, system):
        r.add(f"le:{n}", f"{n}: Layout Editor {sw.le_ident} drives {lt.get('turnoutname')}, "
                         f"switches.csv says {sw.turnout}")
    primary = sw.legs[0]
    if lt.get("blockname") != primary.os_block:
        r.add(f"le:{n}", f"{n}: Layout Editor {sw.le_ident} is in {lt.get('blockname')}, "
                         f"switch_legs.csv says {primary.os_block}")
    if lt.get("type") in PLAIN_TURNOUTS:
        cont = lt.get("continuing", CLOSED)
        b = t.track_name(t.leg_block(sw.le_ident, "B", primary.os_block))
        c = t.track_name(t.leg_block(sw.le_ident, "C", primary.os_block))
        closed, thrown = (b, c) if cont == CLOSED else (c, b)
        if (closed, thrown) != (primary.closed, primary.thrown):
            r.add(f"le:{n}", f"{n}: Layout Editor {sw.le_ident} (continuing={cont}) closes to {closed} "
                             f"and throws to {thrown}; switch_legs.csv says closed {primary.closed}, "
                             f"thrown {primary.thrown}")
    for leg in sw.legs:
        leg_paths = t.paths.get(leg.os_block)
        if not leg_paths:
            r.add(f"le:{n}", f"{n}: {leg.os_block} has no block paths in tables.xml")
            continue
        seen: dict[str, set[str]] = {}
        for dest_sys, settings in leg_paths:
            dest = t.track_name(t.block_user.get(dest_sys, dest_sys))
            mine = {s for tn, s in settings if tn in (sw.turnout, system)}
            seen.setdefault(dest, set()).update(mine or {"none"})
        for want, ok, bad, label in ((leg.closed, {CLOSED, "none"}, THROWN, "closed"),
                                     (leg.thrown, {THROWN}, CLOSED, "thrown")):
            got = seen.get(want)
            if got is None or not (got & ok) or bad in got:
                r.add(f"le:{n}", f"{n}: {leg.os_block} block paths reach {want} with "
                                 f"{sorted(got) if got else 'no path'} for {sw.turnout}; "
                                 f"switch_legs.csv says it is the {label} leg")


# ---------------------------------------------------------------- CATS desks

def desk_plants(path: Path, r: Report) -> tuple[dict, dict[str, tuple[int, int]]]:
    cells = trace.track_cells(parse(path).getroot().find("TRACKPLAN"))
    try:
        plants = trace.desk_plants(cells, bound=True)      # the dark main and upper plants bind nothing
    except trace.PlantError as err:
        r.add(f"cats:{path.name}", f"{path.name}: {err}")
        plants = {}
    return cells, plants


@functools.cache
def device_map_blocks() -> frozenset[str]:
    """The device map's main and upper block names, a double crossover's corners also without the corner letter."""
    with DEVICE_MAP.open(newline="", encoding="utf-8") as f:
        names = {row["user_name"] for row in csv.DictReader(f) if row["layer"] == "block"}
    if not names:
        raise SystemExit(f"{paths.rel(DEVICE_MAP)} has no block rows")
    return frozenset(names | {re.sub(r"(?<=\d)[a-d]$", "", n) for n in names if n.startswith("OS Switch ")})


LEVEL_SENSOR = "IS:HART:C3:B:"      # a main or upper block's virtual occupancy sensor (build_device_map.block_sensor)


def check_level_sensors(desk: str, root: ET.Element, t: Tables, r: Report) -> None:
    """Each main and upper desk block reports the occupancy sensor its Layout Editor block has in tables.xml, a
    virtual IS:HART:C3:B: sensor of that name and system name."""
    seen = set()
    for b in root.iter("BLOCK"):               # a desk block is listed once per edge it has: checked once
        name, occ = b.get("NAME"), b.find("OCCUPIEDSPEC/IOSPEC")
        if not name or occ is None or name not in device_map_blocks() or name in seen:
            continue
        seen.add(name)
        user, system = occ.get("USER_NAME"), (occ.get("JMRIPREFIX") or "") + (occ.get("DECADDR") or "")
        if not system.startswith(LEVEL_SENSOR) or t.block_sensor.get(name) != user or \
                t.sensor_system.get(user or "") != system:
            r.add(f"cats-track:{name}", f"{desk}: block {name} reports {user} ({system}); tables.xml binds it to "
                                        f"{t.block_sensor.get(name) or 'no sensor'} "
                                        f"({t.sensor_system.get(t.block_sensor.get(name) or '', 'none')})")


def check_desk(path: Path, switches: dict[int, facts.Switch], t: Tables, r: Report) -> None:
    desk = path.name
    cells, plants = desk_plants(path, r)
    by_os = facts.legs_by_os(switches)
    for os_name, xy in plants.items():
        if os_name not in by_os:
            r.add(f"cats:{os_name}", f"{desk}: plant at {xy} is in {os_name}, which switch_legs.csv does not list")
    jmri_blocks = t.block_names()
    names = {b.get("NAME") for b in parse(path).getroot().iter("BLOCK") if b.get("NAME")}
    # the main and upper blocks are drawn from the device map, before the tables may hold them: a staging-only
    # candidate has none, so all of them may be missing; tables with main and upper must hold every one but the
    # middle of a double crossover's X (named without the corner letter, a desk block with no sensor)
    root = parse(path).getroot()
    level_here = bool(jmri_blocks & device_map_blocks())
    unbound = names - {b.get("NAME") for b in root.iter("BLOCK") if b.find("OCCUPIEDSPEC") is not None}
    dark = (unbound if level_here else names) & device_map_blocks()
    for name in sorted(names - dark - jmri_blocks):
        r.add(f"cats-track:{name}", f"{desk}: block {name} is not a Layout Editor block in tables.xml")
    if level_here:
        check_level_sensors(desk, root, t, r)
    for sw in switches.values():
        n = f"Switch {sw.number}"
        for leg in sw.legs:
            for want in (leg.closed, leg.thrown):
                if want not in names:
                    r.add(f"cats:{n}", f"{n}: switch_legs.csv leg {want} is not a block on {desk}")
            xy = plants.get(leg.os_block)
            if xy is None:
                r.add(f"cats:{n}", f"{n}: {desk} has no plant in {leg.os_block}")
                continue
            for ri in cells[xy].iter("ROUTEINFO"):
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
                dest = trace.trace_leg(cells, xy, edge, own=leg.os_block)
                want = {"close": leg.closed, "throw": leg.thrown}.get(cmd)
                if dest != want:
                    r.add(f"cats:{n}", f"{n}: {desk} {leg.os_block} leg {edge} ({cmd}) leads to {dest}; "
                                       f"switch_legs.csv says {cmd} leads to {want}")
                normal = ri.get("NORMAL") == "true"
                want_normal = (cmd == "throw") if sw.cats_inverted else (cmd == "close")
                if normal != want_normal:
                    r.add(f"cats:{n}", f"{n}: {desk} {leg.os_block} NORMAL is the {cmd} leg {edge} = {normal}; "
                                       f"switches.csv cats_inverted={'yes' if sw.cats_inverted else 'no'} "
                                       f"puts NORMAL on the {'thrown' if sw.cats_inverted else 'closed'} leg")


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


def check_level_desk(path: Path, t: Tables, r: Report) -> None:
    """The main and upper part of a generated desk: its plants against the internal turnouts and the Layout Editor in
    tables.xml, its masts against main_upper_masts.csv and tables.xml."""
    desk = path.name
    cells = trace.track_cells(parse(path).getroot().find("TRACKPLAN"))
    try:
        plants = trace.level_plants(cells)
    except trace.PlantError as err:
        r.add(f"cats:{desk}", f"{desk}: {err}")
        return
    level = {user: system for user, (system, _c) in t.turnouts.items() if system.startswith("IT:HART:C3:")}
    if not level:
        if t.block_names() & device_map_blocks():
            r.add(f"cats:{desk}", f"{desk}: tables.xml holds main/upper blocks but no IT:HART:C3: turnout for the "
                                  "desk's main and upper plants to command")
        return              # a staging-only candidate (test_le_cutover): tables with no main or upper level to check
    commanded: set[str] = set()
    for os_name, xy, points in plants:
        cmds: dict[str, str | None] = {}
        users = set()
        for ri in cells[xy].findall(f"SEC_EDGE[@EDGE='{points}']/SWITCHPOINTS/ROUTEINFO"):
            edge = ri.get("ROUTEID")
            ios, report = ri.find("ROUTECOMMAND/IOSPEC"), ri.find("SELECTEDREPORT/IOSPEC")
            if ios is None:
                r.add(f"cats:{os_name}", f"{desk}: plant at {xy} in {os_name} leg {edge} has no ROUTECOMMAND")
                continue
            cmd = (ios.text or "").strip()
            user, system = ios.get("USER_NAME"), (ios.get("JMRIPREFIX") or "") + (ios.get("DECADDR") or "")
            users.add(user)
            if level.get(user) != system:
                r.add(f"cats:{user}", f"{desk}: plant at {xy} in {os_name} commands {user} ({system}); tables.xml "
                                      f"has {level.get(user) or 'no such internal turnout'}")
            if report is None or (report.text or "").strip() != cmd or report.get("USER_NAME") != user:
                r.add(f"cats:{user}", f"{desk}: plant at {xy} in {os_name} leg {edge} does not report the {cmd} "
                                      f"of {user} it commands")
            if (ri.get("NORMAL") == "true") != (cmd == "close"):
                r.add(f"cats:{user}", f"{desk}: plant at {xy} in {os_name}: NORMAL is not its close leg")
            cmds[cmd] = trace.trace_leg(cells, xy, edge, own=os_name)
        if len(users) != 1 or set(cmds) != {"close", "throw"}:
            r.add(f"cats:{os_name}", f"{desk}: plant at {xy} in {os_name} commands {sorted(map(str, users))} with "
                                     f"{sorted(cmds)}; one turnout, close and throw")
            continue
        user = users.pop()
        commanded.add(user)
        lts = [lt for lt in t.layout_turnouts.values() if lt.get("turnoutname") in (user, level.get(user))]
        if len(lts) == 1 and lts[0].get("type") in PLAIN_TURNOUTS:
            lt = lts[0]
            b = t.leg_block(lt.get("ident"), "B", lt.get("blockname"))
            c = t.leg_block(lt.get("ident"), "C", lt.get("blockname"))
            closed, thrown = (b, c) if lt.get("continuing", CLOSED) == CLOSED else (c, b)
            if closed != thrown and (same_place(cmds["close"], thrown) or same_place(cmds["throw"], closed)):
                r.add(f"cats:{user}", f"{desk}: {user} closes to {cmds['close']} and throws to {cmds['throw']}; the "
                                      f"Layout Editor ({lt.get('ident')}) closes to {closed} and throws to {thrown}")
    for user in sorted(set(level) - commanded):
        r.add(f"cats:{user}", f"{desk}: no plant commands internal turnout {user}")
    have = desk_mast_blocks(path)
    blocks = {b.get("NAME") for b in parse(path).getroot().iter("BLOCK") if b.get("NAME")}
    masts = {hart_tables.user_name(m): hart_tables.system_name(m) for m in hart_tables.masts(t.root)}
    for row in level_masts.read():
        mast, lamps = row["mast"], have.get(row["mast"], [])
        if len(lamps) != 1:
            r.add(f"mast:{mast}", f"{mast}: {desk} has {len(lamps)} lamps for it, not one")
        elif lamps[0] != desk_block_of(row["protects"], blocks):
            r.add(f"mast:{mast}", f"{mast}: {desk} has its lamp on the edge of {lamps[0]}, but it protects "
                                  f"{row['protects']} ({level_masts.PATH.name})")
        if masts.get(mast) != row["system_name"]:
            r.add(f"mast:{mast}", f"{mast}: tables.xml has {masts.get(mast) or 'no such mast'}, "
                                  f"{level_masts.PATH.name} says {row['system_name']}")


# ---------------------------------------------------------------- USS CTC

def occupancy_sensors(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as fh:
        return {row["block_user_name"].strip(): row["occupancy_sensor_user_name"].strip()
                for row in csv.DictReader(fh)}


def check_ctc_buttons(switches: dict[int, facts.Switch], t: Tables, occ: dict[str, str], r: Report) -> None:
    buttons = {}
    for cb in t.root.iter("ctcCodeButtonData"):
        get = lambda tag, cb=cb: (cb.findtext(tag) or "").strip()  # noqa: E731
        buttons[get("SWDI_ExternalTurnout")] = get
    for sw in switches.values():
        n = f"Switch {sw.number}"
        get = buttons.pop(sw.turnout, None)
        if get is None:
            r.add(f"uss:{n}", f"{n}: no USS CTC code button works {sw.turnout} in tables.xml")
            continue
        os_sensors = tuple(s for s in (get("OSSectionOccupiedExternalSensor"),
                                       get("OSSectionOccupiedExternalSensor2")) if s)
        want = tuple(occ.get(os_name, "?") for os_name in sw.os_blocks)
        if os_sensors != want:
            r.add(f"uss:{n}", f"{n}: CTC code button OS sensors {os_sensors}; switch_legs.csv "
                              f"OS blocks {sw.os_blocks} report on {want}")
        lever = t.sensor_system.get(get("SWDL_InternalSensor"), "")
        if lever != f"IS{sw.ctc_is}:LEVER":
            r.add(f"uss:{n}", f"{n}: CTC lever is {get('SWDL_InternalSensor')} ({lever}), "
                              f"switches.csv says IS{sw.ctc_is}:LEVER")
        if (get("SIDL_Enabled") == "true") != sw.ctc_signals:
            r.add(f"uss:{n}", f"{n}: CTC signal levers SIDL_Enabled={get('SIDL_Enabled')}, "
                              f"switches.csv ctc_signals={'yes' if sw.ctc_signals else 'no'}")
    for turnout in buttons:
        r.add(f"uss:{turnout}", f"tables.xml has a USS CTC code button for {turnout}, not in switches.csv")


def uss_panel(text: str) -> str:
    m = re.search(r"<paneleditor\b.*?</paneleditor>", text, re.S)
    return m.group(0) if m else ""


def check_uss_panel(label: str, pe: str, switches: dict[int, facts.Switch], gen, cells: dict, r: Report) -> None:
    levers = {int(k): int(x) for k, x in re.findall(r'<sensoricon sensor="IS(\d+):LEVER" x="(\d+)"', pe)}
    dots = Counter(re.findall(r'<turnouticon turnout="([^"]+)"', pe))
    closed_url = dict(re.findall(r'<turnouticon turnout="([^"]+)"[^>]*>\s*<icons>\s*<closed url="([^"]+)"', pe))
    for sw in switches.values():
        n = f"Switch {sw.number}"
        x = levers.get(sw.ctc_is)
        want_x = 12 + 65 * sw.uss_slot + 8
        if x != want_x:
            r.add(f"uss:{n}", f"{n}: {label} lever IS{sw.ctc_is}:LEVER at x={x}, "
                              f"column {sw.uss_slot} for plate {sw.number} is x={want_x}")
        if dots[sw.turnout] != 1:
            r.add(f"uss:{n}", f"{n}: {label} draws {dots[sw.turnout]} points dots for {sw.turnout}, expected 1")
            continue
        swapped = closed_url.get(sw.turnout, "").endswith("pts-thrown.gif")
        if swapped != sw.cats_inverted:
            key = f"uss-dot:{n}"
            r.add(key, f"{n}: {label} points dot shows Normal when {'thrown' if swapped else 'closed'}; "
                       f"switches.csv cats_inverted={'yes' if sw.cats_inverted else 'no'} (Normal is the "
                       f"{'thrown' if sw.cats_inverted else 'closed'} leg)")
    # Track jewels and labels against a fresh build from the board grid (uss_board_cells.csv).
    _t, _tracks, lamps, texts = gen.build_geometry(cells)
    want_lamps = Counter((s, x, y, tip) for s, x, y, tip in lamps)
    have_lamps = Counter((s, int(x), int(y), tip) for s, x, y, tip in re.findall(
        r'<sensoricon sensor="(BS [^"]+)" x="(-?\d+)" y="(-?\d+)"[^>]*>\s*<tooltip>([^<]*)</tooltip>', pe))
    cream = 'red="220" green="220" blue="180"'
    want_text = Counter((txt, x, y) for x, y, txt, _size, col in texts
                        if col == gen.CREAM)
    have_text = Counter((txt, int(x), int(y)) for x, y, txt in re.findall(
        r'<positionablelabel x="(-?\d+)" y="(-?\d+)"[^>]*text="([^"]*)"[^>]*' + cream, pe))

    def track(name: str) -> str:
        return name.removeprefix("Track ")

    for (s, x, y, tip), k in (want_lamps - have_lamps).items():
        r.add(f"uss-diagram:{track(tip)}", f"{track(tip)}: the CATS desk puts jewel {s} ({tip}) at "
                                           f"({x},{y}); {label} does not")
    for (s, x, y, tip), k in (have_lamps - want_lamps).items():
        r.add(f"uss-diagram:{track(tip)}", f"{track(tip)}: {label} draws jewel {s} ({tip}) at ({x},{y}); "
                                           f"the CATS desk does not")
    for (txt, x, y), k in (want_text - have_text).items():
        r.add(f"uss-diagram:{track(txt)}", f"{track(txt)}: the CATS desk labels ({x},{y}) {txt!r}; {label} does not")
    for (txt, x, y), k in (have_text - want_text).items():
        r.add(f"uss-diagram:{track(txt)}", f"{track(txt)}: {label} labels ({x},{y}) {txt!r}; the CATS desk does not")


# ---------------------------------------------------------------- data

def check_data(switches: dict[int, facts.Switch], data: Path, r: Report) -> None:
    listed: dict[int, str] = {}
    for cp in facts.load_control_points(data):
        for item in cp["switches"].split(","):
            num = re.match(r"\d+", item.strip())
            if num:
                listed[int(num.group(0))] = cp["cp_name"]
    for sw in switches.values():
        n = f"Switch {sw.number}"
        if not sw.hardware:
            r.add(f"data:{n}", f"{n}: no canonical turnout row (current == proposed) in public_name_map.csv")
        if sw.number in listed and sw.cp != listed[sw.number]:
            r.add(f"data:{n}", f"{n}: control_points.csv puts it at {listed[sw.number]}, "
                               f"public_name_map.csv at {sw.cp or '-'}")
    for num in sorted(set(listed) - set(switches)):
        r.add(f"data:Switch {num}", f"Switch {num}: in control_points.csv, not in switches.csv")


def desk_signals(path: Path) -> dict[tuple[int, int, str], str]:
    """(x, y, edge) -> mast for every named SECSIGNAL on a CATS desk."""
    out = {}
    for sec in parse(path).getroot().find("TRACKPLAN").findall("SECTION"):
        for edge in sec.findall("SEC_EDGE"):
            sig = edge.find("SECSIGNAL")
            if sig is not None and (sig.text or "").strip():
                out[(int(sec.get("X")), int(sec.get("Y")), edge.get("EDGE"))] = sig.text.strip()
    return out


def desk_mast_blocks(path: Path) -> dict[str, list[str | None]]:
    """Mast -> the block on the edge of each lamp of that name on a CATS desk (the block the mast protects)."""
    out: dict[str, list[str | None]] = {}
    for se in parse(path).getroot().iter("SEC_EDGE"):
        sig = se.find("SECSIGNAL")
        if sig is None or not (sig.text or "").strip():
            continue
        blk = se.find("BLOCK")
        out.setdefault(sig.text.strip(), []).append(blk.get("NAME") if blk is not None else None)
    return out


def protected_blocks(path: Path = MASTS) -> dict[str, str]:
    """Mast -> the block it protects, from the frozen staging Layout Editor masts (staging_le/masts.csv)."""
    with path.open(newline="", encoding="utf-8") as fh:
        rows = csv.DictReader(line for line in fh if not line.startswith("#"))
        return {row["mast"]: row["protects"] for row in rows if row.get("protects")}


def check_mast_cells(data: Path, rows: list[dict[str, str]], desks, t: Tables, r: Report) -> None:
    """mast_cells.csv against the USS board's grid, the CATS desks (each of its masts once, its lamp on the edge of
    the block it protects, and no other mast), the name map and the masts' heads in tables.xml."""
    cells = facts.load_mast_cells(data)
    grid = facts.load_uss_cells(data)
    for c in cells:
        if not grid.get((c.x, c.y), {}).get("tracks"):
            r.add(f"mast:{c.mast}", f"{c.mast}: mast_cells.csv puts it at ({c.x}, {c.y}), a cell with no track on "
                                    f"the USS board's grid ({facts.USS_CELLS})")
    want = {c.mast for c in cells}
    protects = protected_blocks()
    level = level_masts.names()               # main and upper: check_level_desk
    for desk in desks:
        have = desk_mast_blocks(Path(desk))
        name = Path(desk).name
        for mast in sorted(want | (set(have) - level)):
            lamps = have.get(mast, [])
            if mast not in want:
                r.add(f"mast:{mast}", f"{mast}: {name} has a lamp for it, mast_cells.csv has no such mast")
            elif len(lamps) != 1:
                r.add(f"mast:{mast}", f"{mast}: {name} has {len(lamps)} lamps for it, not one")
            elif lamps[0] != protects.get(mast):
                r.add(f"mast:{mast}", f"{mast}: {name} has its lamp on the edge of {lamps[0]}, "
                                      f"but it protects {protects.get(mast)} (staging_le/masts.csv)")
    named = {row["proposed"] for row in rows if row["layer"] == "mast"}
    heads = {}
    for m in hart_tables.masts(t.root):
        heads[hart_tables.user_name(m)] = re.findall(r"\((IH\d+)\)", hart_tables.system_name(m))
    for c in cells:
        if c.mast not in named:
            r.add(f"mast:{c.mast}", f"{c.mast}: in mast_cells.csv, not a mast row in public_name_map.csv")
        if c.mast not in heads:
            r.add(f"mast:{c.mast}", f"{c.mast}: in mast_cells.csv, not a mast in tables.xml")
            continue
        got = heads[c.mast]
        if (c.uss_kind == "d1" and got != [c.uss_head]) or (c.uss_kind == "h2" and len(got) != 2):
            r.add(f"mast:{c.mast}", f"{c.mast}: mast_cells.csv draws it {c.uss_kind} "
                                    f"{c.uss_head or ''}".rstrip() + f", tables.xml gives it heads {got}")


def check_levels(switches: dict[int, facts.Switch], data: Path, rows: list[dict[str, str]], t: Tables,
                 r: Report) -> None:
    """Each control point, mast and block has one level, and every source for it agrees."""
    by_cp = facts.cp_levels(data)
    for cp in facts.load_control_points(data):
        for item in cp["switches"].split(","):
            num = re.match(r"\d+", item.strip())
            sw = switches.get(int(num.group(0))) if num else None
            if sw and sw.level != cp["level"]:
                r.add(f"level:Switch {sw.number}", f"Switch {sw.number}: switches.csv level {sw.level}, "
                                                   f"control_points.csv puts {cp['cp_name']} on level {cp['level']}")
    for cp in sorted({row["cp"] for row in rows if row["cp"]} - set(by_cp)):
        r.add(f"level:{cp}", f"{cp}: a cp in public_name_map.csv with no row (and no level) in control_points.csv")
    # A block's level from its switches (throat blocks through their track) against its control point's.
    by_block = facts.switch_block_levels(switches)
    block_cp = {row["proposed"]: row["cp"] for row in rows if row["layer"] == "block"}
    for name, cp in block_cp.items():
        from_switch = by_block.get(t.track_name(name), set())
        if len(from_switch) > 1:
            r.add(f"level:{name}", f"{name}: its switches in switch_legs.csv are on levels {sorted(from_switch)}")
        elif from_switch and cp in by_cp and by_cp[cp] not in from_switch:
            r.add(f"level:{name}", f"{name}: is in {cp} (level {by_cp[cp]}), its switches in switch_legs.csv "
                                   f"say level {next(iter(from_switch))}")
    levels = facts.name_map_levels(data, switches, rows, t.track_name)
    for row in rows:
        key = (row["layer"], row["proposed"])
        if row["layer"] not in ("mast", "block") or key in levels:
            continue
        name = row["proposed"]
        near = {levels.get(("block", t.track_name(t.block_user.get(dest, dest))))
                for dest, _settings in t.paths.get(name, [])} - {None}
        if len(near) != 1:
            r.add(f"level:{name}", f"{name}: no control point and no switch in public_name_map.csv or "
                                   f"switch_legs.csv, and its tables.xml paths join levels {sorted(near) or 'none'}; "
                                   f"give it a cp")


def run(data: Path = facts.DATA, tables: Path = TABLES, desks=DESKS, gui: Path = GUI,
        occupancy: Path = OCCUPANCY) -> Report:
    import gen_ctc_track_plan as gen

    r = Report()
    switches = facts.load_switches(data)
    t = Tables(tables)
    check_data(switches, data, r)
    rows = facts.identity_rows(data)  # public_name_map.csv, read once for the checks below
    check_levels(switches, data, rows, t, r)
    check_mast_cells(data, rows, desks, t, r)
    for sw in switches.values():
        check_tables(sw, t, r)
    for desk in desks:
        check_desk(Path(desk), switches, t, r)
        check_level_desk(Path(desk), t, r)
    # the USS CTC machine parked (hartlib.parked): its code buttons and panel are checked in the parked file, put
    # back into a copy of the tables, against the same switches (the tables parsed once above; the copy stays in
    # memory, with no temporary file to write and parse again)
    uss_root = parked.with_parked({"uss"}, tables, root=t.root)
    if uss_root is t.root:
        uss, uss_text = t, Path(tables).read_text(encoding="utf-8")
    else:
        uss = Tables(tables, root=uss_root)
        pe = next(iter(uss_root.iter("paneleditor")), None)       # only the USS panel is read from the text
        uss_text = ET.tostring(pe, encoding="unicode") if pe is not None else ""
    check_ctc_buttons(switches, uss, occupancy_sensors(occupancy), r)
    cells = facts.load_uss_cells(data)  # the board's grid, frozen from the hand-wired desk (uss_board_cells.csv)
    gui_text = Path(gui).read_text(encoding="utf-8")
    for label, text in (("GUIObjects.xml", gui_text), ("tables.xml USS panel", uss_text)):
        check_uss_panel(label, uss_panel(text), switches, gen, cells, r)
    return r


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", type=Path, default=facts.DATA)
    ap.add_argument("--tables", type=Path, default=TABLES)
    ap.add_argument("--desk", type=Path, action="append",
                    help="CATS desk (repeat); default the last hand-wired CTC and ABS (git)")
    ap.add_argument("--gui", type=Path, default=GUI)
    args = ap.parse_args(argv)
    r = run(args.data, args.tables, tuple(args.desk) if args.desk else DESKS, args.gui)
    for line in r.known(KNOWN):
        print(f"KNOWN {line}")
    failures = r.failures(KNOWN)
    for line in failures:
        print(f"FAIL {line}", file=sys.stderr)
    n = len(facts.load_switches(args.data))
    print(f"layout facts: {n} switches, {len(failures)} failure(s), {len(r.known(KNOWN))} known")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
