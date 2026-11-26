#!/usr/bin/env python3
"""The Layout Editor, the CATS desks and the USS CTC must agree with the switch facts.

    python3 tools/audit/check_layout_facts.py

The facts are the staging rows of jmri/layouts/hart/data/switches.csv (read by
layout_facts.py), with hardware, DCC address and control point from
staging's rows of the device master and the desk areas of stations.csv. For every switch this checks:

Layout Editor (tables.xml)
  - the turnout's hardware and DCC address, and the layout turnout's name and OS block;
  - which leg the continuing sense closes to (plain turnouts);
  - the stored block paths: the closed leg needs Closed or no setting, the thrown
    leg Thrown, and neither may be reached with the other setting. The generated tables.xml stores none (ADR-029:
    JMRI derives them from the panel on load), so this part runs only on a tables file that stores them (--tables,
    a PanelPro Store: tools/hosts/run_panelpro_roundtrip.sh runs it on its Store);
  - a crossover's legs against the panel's track: its OS block one half, its thrown leg the other half, its closed
    leg a block the track reaches from that half (check_crossover_legs; plain turnouts by continuing sense above).
CATS desks (HART_CTC.xml, HART_ABS.xml: the live desks, generated from the schematic since the CATS cut-over)
  - each bound plant's turnout, the leg each command (close/throw) leads to, and which
    leg is NORMAL (the closed one, unless the switch is CATS-inverted); the main and upper
    plants (internal turnouts) are checked below;
  - every block bound to a detector is a Layout Editor block (main and upper ones only where the tables hold those
    levels), and each main and upper desk block reports, occupied and unoccupied, the virtual sensor
    (IS:HART:C3:B:) its block has in tables.xml; only the desk-only middle of a double crossover's X reports none;
  - the desk's staging masts are mast_cells.csv's, each once, its lamp on the edge of the block it
    protects (schematic/masts.csv's staging rows, hartlib.railroad); each is a staging mast row of the device master and in tables.xml, with one head
    (the one named) for a d1 icon and two for h2;
  - main and upper (bound to their internal turnouts IT:HART:C3:<n>, their masts and their blocks' virtual
    sensors): each plant commands and reports one internal turnout of tables.xml, NORMAL on its close
    leg, and no plain turnout's close and throw legs are the Layout Editor's swapped; every internal
    turnout has a plant (a double crossover four points, one turnout); each mast of
    masts.csv's main and upper rows has one lamp, on the edge of the block it protects (a double crossover's
    corner is its one desk block), and is that mast in tables.xml.
Levels (stations.csv desk areas, switches.csv, staging's rows of the device master)
  - each control point's switches are on its level, and every cp of a staging row has a desk area;
  - every mast and block has one level: its switch's, its control point's, or, for a
    main between control points, the one level of the blocks it joins (its stored paths, else the panel's track).
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
import functools
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType
from typing import overload

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import devices, level_devices, level_masts, occupancy_bindings, parked, paths, railroad, tables_build  # noqa: E402,E501
from hartlib import tables as hart_tables  # noqa: E402
from hartlib.names import split_dcc  # noqa: E402

ROOT = paths.REPO_ROOT
HART = paths.LAYOUT_DIR
sys.path[:0] = [str(paths.LAYOUT_SCRIPTS), str(Path(__file__).resolve().parent)]     # layout_facts_xml beside this
sys.path.append(str(paths.CATS_DIR / "scripts"))

import layout_facts as facts  # noqa: E402
from layout_facts_xml import LayoutFactsError, desk_root, need, parse, parse_tables, trackplan  # noqa: E402,F401
import digicon_trace as trace  # noqa: E402

TABLES = paths.TABLES_XML
GUI = HART / "ctc/GUIObjects.xml"
DESKS = (ROOT / "cats/panels/HART_CTC.xml", ROOT / "cats/panels/HART_ABS.xml")
MASTS = railroad.Sources.under().masts     # masts.csv: each mast's level, facing and protected blocks
# the staging level (its field masts and turnouts), and the main and upper levels (on virtual heads and turnouts)
STAGING_LEVELS = (int(railroad.STAGING_LEVEL),)
ADDED_LEVELS = tuple(lv for lv in level_masts.LEVELS if lv not in STAGING_LEVELS)
DEVICE_MAP = railroad.Sources.under().devices     # the device master: the main and upper block names

CLOSED, THROWN = "2", "4"
PLAIN_TURNOUTS = {"RH_TURNOUT", "LH_TURNOUT", "WYE_TURNOUT"}

# Differences already reported to the owner and accepted, each by its exact message.
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


# ---------------------------------------------------------------- tables.xml

def part_map(master: Path) -> dict[str, str]:
    """{part: the block it is part of} of every level's parts (the device master's part_of) in the master at `master`: the
    master that goes with the tables being checked."""
    return {r["user_name"]: r["part_of"] for _n, r in devices.part_lines(("1", "2", "3"), master)}


def desk_leg(t: "Tables", cells: dict, xy: tuple[int, int], edge: str, own: str) -> str | None:
    """The block a desk plant's leg `edge` leads to, read as the Layout Editor's legs are (Tables.leg_block): past
    its own OS block `own` and the parts inside it, a part read as the block it is part of."""
    inside = frozenset(p for p, of in t.part_of.items() if of == own)
    return t.os_of(trace.trace_leg(cells, xy, edge, own=own, inside=inside))


class Tables:
    def __init__(self, path: Path, root: ET.Element | None = None, parts: dict[str, str] | None = None) -> None:
        """The tables at `path`, or `root` when the caller holds them parsed already (the USS CTC view). `parts`:
        {part: the block it is part of} from the master that goes with these tables (part_map); none when not
        given, never read from the repo behind the caller's back."""
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
                settings = [(need(to, "systemName"), need(bs, "setting"))
                            for bs in p.findall("beansetting") if (to := bs.find("turnout")) is not None]
                self.paths.setdefault(user, []).append((need(p, "block"), settings))
        self.turnouts: dict[str, tuple[str, str]] = {}
        for t in hart_tables.turnouts(self.root):
            user = (t.findtext("userName") or "").strip()
            if user:
                self.turnouts[user] = ((t.findtext("systemName") or "").strip(),
                                       (t.findtext("comment") or "").strip())
        # the full panel only: the band panels (tables.BAND_PANEL_NAMES, 2026-11-22) copy its elements under the same
        # idents, and a lookup over the whole file would take the copy
        panel = hart_tables.layout_editor(self.root)
        if panel is None:
            raise ValueError(f"{path}: no main Layout Editor panel ({', '.join(hart_tables.MAIN_PANEL_NAMES)})")
        self.layout_turnouts = {lt.get("ident"): lt for lt in panel.iter("layoutturnout")}
        self.segments = {s.get("ident"): s for s in panel.iter("tracksegment")}
        self.points = {p.get("ident"): p for p in panel.iter("positionablepoint")}
        self.paths_stored = bool(self.paths)
        # a part (the device master's part_of) is a JMRI block of its own inside another block; the
        # legs in switches.csv name the blocks a part is inside, as the masts read them (staging_device_map.os_layer)
        self.part_of: dict[str, str] = dict(parts or {})
        self.sensor_system = {
            (s.findtext("userName") or "").strip(): (s.findtext("systemName") or "").strip()
            for s in self.root.iter("sensor")
        }

    def joined_blocks(self, user: str) -> set[str]:
        """The block user names `user` joins: through its stored paths, or, in tables that store none (the generated
        tables.xml, ADR-029), through the panel's track: a segment of `user` ending at an anchor or a turnout whose
        other side is another block."""
        if self.paths_stored:
            return {self.block_user.get(dest, dest) for dest, _settings in self.paths.get(user, [])} - {None}
        out: set[str] = set()
        for seg in self.segments.values():
            if seg.get("blockname") != user:
                continue
            for i in ("1", "2"):
                name, kind = seg.get(f"connect{i}name"), seg.get(f"type{i}") or ""
                if kind == "POS_POINT" and name in self.points:
                    pp = self.points[name]
                    for other in (pp.get("connect1name"), pp.get("connect2name")):
                        o = self.segments.get(other or "")
                        if o is not None and (joined := o.get("blockname")):
                            out.add(joined)
                elif kind.startswith("TURNOUT_") and name in self.layout_turnouts:
                    # a turnout with no block joins none: the stored-paths branch above drops None the same way
                    if (joined_lt := self._turnout_block(self.layout_turnouts[name], kind[-1])) is not None:
                        out.add(joined_lt)
                elif kind.startswith(("SLIP_", "LEVEL_XING_")):
                    raise ValueError(f"{user}: track segment {seg.get('ident')} ends at {kind} {name}, a slip or level "
                                     "crossing the panel check does not read; give the block a cp")
                elif kind:
                    raise ValueError(f"{user}: track segment {seg.get('ident')} ends at {kind} {name!r}, which is "
                                     "not on the panel")
        return out - {user, None}

    @overload
    def track_name(self, user: str) -> str: ...
    @overload
    def track_name(self, user: None) -> None: ...
    @overload
    def track_name(self, user: str | None) -> str | None: ...

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

    def os_of(self, block: str | None) -> str | None:
        """The block `block` is part of (part_of), or `block` itself."""
        return self.part_of.get(block, block) if block else block

    def leg_block(self, ident: str | None, conn: str, own: str | None) -> str | None:
        """Block reached from connection B or C of a layout turnout, past its own OS block (and the parts inside
        it), a part read as the block it is part of (os_of)."""
        came: tuple[str | None, str | None] = (ident, f"TURNOUT_{conn}")
        seg = next((s for s in self.segments.values()
                    for i in ("1", "2")
                    if (s.get(f"connect{i}name"), s.get(f"type{i}")) == came), None)
        for _ in range(200):
            if seg is None:
                return None
            if seg.get("blockname") and self.os_of(seg.get("blockname")) != own:
                return self.os_of(seg.get("blockname"))
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
                block = self.os_of(self._turnout_block(self.layout_turnouts[name], kind[-1]))
                return block if block != own else None
            else:
                return None
        return None


XOVERS = {"RH_XOVER", "LH_XOVER", "DOUBLE_XOVER"}
XOVER_HALVES = (("A", "B"), ("C", "D"))     # a crossover's connections by half: A-B is one track, C-D the other
# The connections a crossover's diverging route joins (JMRI ConnectivityUtil: a right-hand crossover throws A to C,
# a left-hand one B to D). A train in a half reaches the half's closed leg at the other connection; a double
# crossover diverges at all four, so its closed leg is only held to the half's ends.
XOVER_DIVERGING = {"RH_XOVER": frozenset("AC"), "LH_XOVER": frozenset("BD"), "DOUBLE_XOVER": frozenset("ABCD")}


def check_crossover_legs(sw: facts.Switch, lt: ET.Element, t: Tables, r: Report) -> None:
    """Each leg of a crossover's switch against the panel's track (the generated tables.xml stores no paths): its OS
    block is one half of the layout turnout, its thrown leg the other half, and its closed leg the block the track
    reaches from that half's straight-through end (XOVER_DIVERGING)."""
    n = f"Switch {sw.number}"
    pairs = [(t._turnout_block(lt, a), (a, b)) for a, b in XOVER_HALVES]
    blocks = [h for h, _c in pairs]
    if not all(blocks) or len(set(blocks)) != 2:
        r.add(f"le:{n}", f"{n}: Layout Editor {sw.le_ident}'s halves are blocks {blocks}: a crossover needs two "
                         "halves, each its own block (blockname for A-B, blockcname for C-D)")
        return
    halves = {h: c for h, c in pairs if h}     # every half is a block (checked above)
    for leg in sw.legs:
        conns = halves.get(leg.os_block)
        if conns is None:
            r.add(f"le:{n}", f"{n}: {leg.os_block} is no half of Layout Editor {sw.le_ident} "
                             f"({', '.join(sorted(halves))})")
            continue
        other = [h for h in halves if h != leg.os_block]
        if [t.track_name(leg.thrown)] != [t.track_name(h) for h in other]:
            r.add(f"le:{n}", f"{n}: switches.csv throws {leg.os_block} to {leg.thrown}, Layout Editor "
                             f"{sw.le_ident}'s other half is {', '.join(other) or 'none'}")
        ends = [c for c in conns if c not in XOVER_DIVERGING[need(lt, "type")]] or list(conns)
        reach = {reached for c in ends
                 if (reached := t.track_name(t.leg_block(sw.le_ident, c, leg.os_block))) is not None}
        if t.track_name(leg.closed) not in reach:
            r.add(f"le:{n}", f"{n}: switches.csv closes {leg.os_block} to {leg.closed}, the panel's track from "
                             f"that half's closed end reaches {sorted(reach) or 'nothing'}")


def check_tables(sw: facts.Switch, t: Tables, r: Report) -> None:
    n = f"Switch {sw.number}"
    system, comment = t.turnouts.get(sw.turnout, ("", ""))
    if not system:
        r.add(f"le:{n}", f"{n}: no turnout {sw.turnout!r} in tables.xml")
        return
    if sw.hardware and system != sw.hardware:
        r.add(f"le:{n}", f"{n}: tables.xml turnout is {system}, the device master says {sw.hardware}")
    # a witness of tables.xml (an output) against the device master's dcc column: the address is read out of the built
    # comment only to hold the build to the master, never used as a fact
    try:
        dcc = split_dcc(comment)[1]
    except ValueError as err:
        dcc = "?"
        r.add(f"le:{n}", f"{n}: tables.xml {err}")
    if sw.dcc and dcc != sw.dcc:
        r.add(f"le:{n}", f"{n}: tables.xml comment DCC {dcc or '-'}, "
                         f"the device master says DCC {sw.dcc}")
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
                         f"switches.csv says {primary.os_block}")
    if lt.get("type") in PLAIN_TURNOUTS:
        cont = lt.get("continuing", CLOSED)
        b = t.track_name(t.leg_block(sw.le_ident, "B", primary.os_block))
        c = t.track_name(t.leg_block(sw.le_ident, "C", primary.os_block))
        closed, thrown = (b, c) if cont == CLOSED else (c, b)
        if (closed, thrown) != (primary.closed, primary.thrown):
            r.add(f"le:{n}", f"{n}: Layout Editor {sw.le_ident} (continuing={cont}) closes to {closed} "
                             f"and throws to {thrown}; switches.csv says closed {primary.closed}, "
                             f"thrown {primary.thrown}")
    if lt.get("type") in XOVERS:
        check_crossover_legs(sw, lt, t, r)
    if not t.paths_stored:          # the generated tables.xml (ADR-029): no stored paths to hold to the legs
        return
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
                                 f"switches.csv says it is the {label} leg")


# ---------------------------------------------------------------- CATS desks

def desk_plants(path: Path, r: Report) -> tuple[dict, dict[str, tuple[int, int]]]:
    cells = trace.track_cells(trackplan(path))
    try:
        plants = trace.desk_plants(cells, bound=True, level_turnouts=level_turnouts())     # staging's plants
    except trace.PlantError as err:
        r.add(f"cats:{path.name}", f"{path.name}: {err}")
        plants = {}
    return cells, plants


@functools.cache
def level_turnouts() -> dict[str, str]:
    """{user name: bean name} of the main and upper turnouts, from the device master's rows
    (hartlib.tables_build.level_turnouts), so a swapped turnout is still one."""
    return tables_build.level_turnouts(devices.load(DEVICE_MAP))


@functools.cache
def device_map_rows() -> frozenset[str]:
    """The main and upper block names (the block rows of levels 2 and 3 of the device master)."""
    return frozenset(block_rows())


def block_rows() -> dict[str, tuple[int, dict[str, str]]]:
    """{block name: (line, row)} of the block rows of levels 2 and 3 of the device master."""
    rows = {row["user_name"]: (n, row) for n, row in devices.device_map_lines(("2", "3"), DEVICE_MAP)
            if row["layer"] == "block"}
    if not rows:
        raise SystemExit(f"{paths.rel(DEVICE_MAP)} has no block rows")
    return rows


@functools.cache
def device_map_blocks() -> frozenset[str]:
    """The device map's main and upper block names, a double crossover's corners (role xover_corner) also without
    the corner letter (the middle of its X, a desk-only block)."""
    rows = block_rows()
    corners = {n for n, (line, r) in rows.items()
               if devices.row_role(r, f"{paths.rel(DEVICE_MAP)}: {devices.row_text(r)}") == "xover_corner"}
    return frozenset(set(rows) | {re.sub(r"(?<=\d)[a-d]$", "", n) for n in corners})


@functools.cache
def field_sensors() -> frozenset[str]:
    """The JMRI names of the main and upper detectors swapped to a field sensor by their row (assignment field,
    ADR-028): a column of the row, not its level, says a block's sensor is virtual."""
    return frozenset(r["jmri_name"] for r in devices.load(DEVICE_MAP) if r["level"] in level_devices.LEVELS
                     and r["layer"] == "occupancy" and r["assignment"] == "field")


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


def check_desk(path: Path, switches: dict[int, facts.Switch], t: Tables, r: Report) -> None:
    desk = path.name
    cells, plants = desk_plants(path, r)
    by_os = facts.legs_by_os(switches)
    for os_name, at in plants.items():
        if os_name not in by_os:
            r.add(f"cats:{os_name}", f"{desk}: plant at {at} is in {os_name}, which switches.csv does not list")
    jmri_blocks = t.block_names()
    names = {desk_block for b in desk_root(path).iter("BLOCK") if (desk_block := b.get("NAME"))}
    # the main and upper blocks are drawn from the device map, before the tables may hold them: a staging-only
    # candidate has none, so all of them may be missing; tables with main and upper must hold every one but the
    # middle of a double crossover's X (named without the corner letter, a desk-only block with no sensor), and each
    # must report its virtual sensor (check_level_sensors)
    root = desk_root(path)
    level_here = bool(jmri_blocks & device_map_blocks())
    dark = (device_map_blocks() - device_map_rows() if level_here else device_map_blocks()) & names
    for name in sorted(names - dark - jmri_blocks):
        r.add(f"cats-track:{name}", f"{desk}: block {name} is not a Layout Editor block in tables.xml")
    if level_here:
        check_level_sensors(desk, root, t, r)
    for sw in switches.values():
        n = f"Switch {sw.number}"
        for leg in sw.legs:
            for want in (leg.closed, leg.thrown):
                if want not in names:
                    r.add(f"cats:{n}", f"{n}: switches.csv leg {want} is not a block on {desk}")
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
                dest = desk_leg(t, cells, xy, edge, leg.os_block)
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
    tables.xml, its masts against masts.csv's main and upper rows and tables.xml."""
    desk = path.name
    cells = trace.track_cells(trackplan(path))
    try:
        plants = trace.level_plants(cells, level_turnouts())
    except trace.PlantError as err:
        r.add(f"cats:{desk}", f"{desk}: {err}")
        return
    level = {user: t.turnouts[user][0] for user in level_turnouts() if user in t.turnouts}
    if not level:
        if t.block_names() & device_map_blocks():
            r.add(f"cats:{desk}", f"{desk}: tables.xml holds main/upper blocks but none of the device master's main "
                                  "and upper turnouts for the desk's main and upper plants to command")
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
                                      f"has {level.get(user) or 'no such main or upper turnout'}")
            if report is None or (report.text or "").strip() != cmd or report.get("USER_NAME") != user:
                r.add(f"cats:{user}", f"{desk}: plant at {xy} in {os_name} leg {edge} does not report the {cmd} "
                                      f"of {user} it commands")
            if (ri.get("NORMAL") == "true") != (cmd == "close"):
                r.add(f"cats:{user}", f"{desk}: plant at {xy} in {os_name}: NORMAL is not its close leg")
            cmds[cmd] = desk_leg(t, cells, xy, edge, os_name)          # as leg_block reads the Layout Editor
        if len(users) != 1 or set(cmds) != {"close", "throw"}:
            r.add(f"cats:{os_name}", f"{desk}: plant at {xy} in {os_name} commands {sorted(map(str, users))} with "
                                     f"{sorted(cmds)}; one turnout, close and throw")
            continue
        user = users.pop()
        commanded.add(user)
        lts = [lt for lt in t.layout_turnouts.values() if lt.get("turnoutname") in (user, level.get(user))]
        if len(lts) == 1 and lts[0].get("type") in PLAIN_TURNOUTS:
            lt = lts[0]
            b = t.leg_block(lt.get("ident"), "B", lt.get("blockname"))     # a turnout with no block still reports
            c = t.leg_block(lt.get("ident"), "C", lt.get("blockname"))
            closed, thrown = (b, c) if lt.get("continuing", CLOSED) == CLOSED else (c, b)
            if closed != thrown and (same_place(cmds["close"], thrown) or same_place(cmds["throw"], closed)):
                r.add(f"cats:{user}", f"{desk}: {user} closes to {cmds['close']} and throws to {cmds['throw']}; the "
                                      f"Layout Editor ({lt.get('ident')}) closes to {closed} and throws to {thrown}")
    for user in sorted(set(level) - commanded):
        r.add(f"cats:{user}", f"{desk}: no plant commands main or upper turnout {user}")
    have = desk_mast_blocks(path)
    blocks = {desk_block for b in desk_root(path).iter("BLOCK") if (desk_block := b.get("NAME"))}
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


# ---------------------------------------------------------------- USS CTC

def occupancy_sensors(device_map: Path) -> dict[str, str]:
    """{block name: occupancy sensor} of the CATS desks' blocks in the master at `device_map` (occupancy_bindings)."""
    return {row["block_user_name"]: row["occupancy_sensor_user_name"]
            for row in occupancy_bindings.rows(device_map)}


def _button_text(cb: ET.Element, tag: str) -> str:
    """The stripped text of a code button's child `tag` ("" when it has none)."""
    return (cb.findtext(tag) or "").strip()


def check_ctc_buttons(switches: dict[int, facts.Switch], t: Tables, occ: dict[str, str], r: Report) -> None:
    buttons: dict[str, Callable[[str], str]] = {}
    for cb in t.root.iter("ctcCodeButtonData"):
        text_of = functools.partial(_button_text, cb)
        buttons[text_of("SWDI_ExternalTurnout")] = text_of
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
            r.add(f"uss:{n}", f"{n}: CTC code button OS sensors {os_sensors}; switches.csv "
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


def check_uss_panel(label: str, pe: str, switches: dict[int, facts.Switch], gen: ModuleType,
                    cells: dict, r: Report) -> None:
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
            r.add(f"data:{n}", f"{n}: no staging turnout row with a system_name in the device master")
        if sw.number in listed and sw.cp != listed[sw.number]:
            r.add(f"data:{n}", f"{n}: stations.csv puts it at {listed[sw.number]}, "
                               f"the device master at {sw.cp or '-'}")
    for only in sorted(set(listed) - set(switches)):
        r.add(f"data:Switch {only}", f"Switch {only}: in stations.csv, not in switches.csv")


def desk_signals(path: Path) -> dict[tuple[int, int, str], str]:
    """(x, y, edge) -> mast for every named SECSIGNAL on a CATS desk."""
    out: dict[tuple[int, int, str], str] = {}
    for sec in trackplan(path).findall("SECTION"):
        for edge in sec.findall("SEC_EDGE"):
            sig = edge.find("SECSIGNAL")
            mast = (sig.text or "").strip() if sig is not None else ""
            if mast:
                out[(int(need(sec, "X")), int(need(sec, "Y")), need(edge, "EDGE"))] = mast
    return out


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


def protected_blocks(path: Path = MASTS) -> dict[str, str]:
    """Mast -> the block it protects (";" between several), from the staging masts (schematic/masts.csv's base level
    rows, hartlib.railroad.read_masts)."""
    return {m.mast: ";".join(m.protects) for m in railroad.read_masts(path, levels=STAGING_LEVELS) if m.protects}


def staging_mast_rows(path: Path = MASTS) -> list[dict]:
    """masts.csv's base level (staging) rows (hartlib.level_masts.read, which checks the file)."""
    return level_masts.read(path, levels=STAGING_LEVELS)


def check_mast_cells(data: Path, rows: list[dict[str, str]], desks: Sequence[Path], t: Tables, r: Report) -> None:
    """mast_cells.csv against the USS board's grid, the CATS desks (each of its masts once, its lamp on the edge of
    the block it protects, and no other mast), staging's mast rows of the device master and the masts' heads in tables.xml."""
    # the desks draw staging's visible masts, as the rule places them (masts.csv, ADR-024); mast_cells.csv
    # is the USS board's, checked only while the board is in the tables (it is parked with it)
    want = {m["mast"] for m in staging_mast_rows() if not m["system_name"].startswith("IF$vsm:")}
    uss_parked = "uss" in parked.parked_in(t.root)
    cells = [] if uss_parked else facts.load_mast_cells(data)
    grid = {} if uss_parked else facts.load_uss_cells(data)
    for c in cells:
        if not grid.get((c.x, c.y), {}).get("tracks"):
            r.add(f"mast:{c.mast}", f"{c.mast}: mast_cells.csv puts it at ({c.x}, {c.y}), a cell with no track on "
                                    f"the USS board's grid ({facts.USS_CELLS})")
    protects = protected_blocks()
    level = level_masts.names(MASTS, levels=ADDED_LEVELS)      # main and upper: check_level_desk
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
    named = {row["user_name"] for row in rows if row["layer"] == "mast"}
    heads = {}
    for m in hart_tables.masts(t.root):
        heads[hart_tables.user_name(m)] = re.findall(r"\((IH\d+)\)", hart_tables.system_name(m))
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
    # A block's level from its switches (throat blocks through their track) against its control point's.
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
    levels = facts.staging_levels(data, switches, rows, t.track_name)
    for row in rows:
        key = (row["layer"], row["user_name"])
        if row["layer"] not in ("mast", "block") or key in levels:
            continue
        name = row["user_name"]
        try:
            near = {levels.get(("block", t.track_name(b))) for b in t.joined_blocks(name)} - {None}
        except ValueError as exc:
            r.add(f"level:{name}", str(exc))
            continue
        if len(near) != 1:
            r.add(f"level:{name}", f"{name}: no control point and no switch in the device master or "
                                   f"switches.csv, and the blocks it joins in tables.xml are on levels "
                                   f"{sorted(near) or 'none'}; give it a cp")


def run(data: Path = facts.DATA, tables: Path = TABLES, desks: Sequence[Path] = DESKS, gui: Path = GUI,
        device_map: Path = DEVICE_MAP) -> Report:
    """`device_map`: the master that goes with `tables` (its parts, part_map)."""
    import gen_ctc_track_plan as gen

    r = Report()
    switches = facts.load_switches(data)
    parts = part_map(device_map)
    t = Tables(tables, parts=parts)
    check_data(switches, data, r)
    rows = facts.staging_rows(data)  # staging's rows of the device master, read once for the checks below
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
        uss = Tables(tables, root=uss_root, parts=parts)
        pe = next(iter(uss_root.iter("paneleditor")), None)       # only the USS panel is read from the text
        uss_text = ET.tostring(pe, encoding="unicode") if pe is not None else ""
    check_ctc_buttons(switches, uss, occupancy_sensors(device_map), r)
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
    ap.add_argument("--devices", type=Path, default=DEVICE_MAP,
                    help="the master that goes with --tables (its parts: a part is read as the block it is in)")
    args = ap.parse_args(argv)
    r = run(args.data, args.tables, tuple(args.desk) if args.desk else DESKS, args.gui, device_map=args.devices)
    for line in r.known(KNOWN):
        print(f"KNOWN {line}")
    failures = r.failures(KNOWN)
    for line in failures:
        print(f"FAIL {line}", file=sys.stderr)
    n = len(facts.load_switches(args.data))
    if not Tables(args.tables).paths_stored:
        print(f"note: {paths.rel(args.tables)} stores no block paths (ADR-029: JMRI derives them from the panel); the "
              "stored-path leg check runs on a tables file that stores them (--tables, a PanelPro Store)")
    print(f"layout facts: {n} switches, {len(failures)} failure(s), {len(r.known(KNOWN))} known")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
