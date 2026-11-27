"""The Layout Editor part of tools/audit/check_layout_facts.py: tables.xml read once (Tables), and each switch's
turnout, layout turnout, legs and stored block paths against switches.csv (check_tables)."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import NamedTuple, overload

from hartlib import devices
from hartlib import tables as hart_tables
from hartlib.names import split_dcc
from layout_facts_base import CLOSED, PLAIN_TURNOUTS, THROWN, Cells, Report, facts, trace
from layout_facts_xml import LayoutFactsError, need, parse_tables

XOVERS = frozenset({"RH_XOVER", "LH_XOVER", "DOUBLE_XOVER"})
XOVER_HALVES = (("A", "B"), ("C", "D"))     # a crossover's connections by half: A-B is one track, C-D the other
# The connections a crossover's diverging route joins (JMRI ConnectivityUtil: a right-hand crossover throws A to C,
# a left-hand one B to D). A train in a half reaches the half's closed leg at the other connection; a double
# crossover diverges at all four, so its closed leg is only held to the half's ends.
XOVER_DIVERGING = {"RH_XOVER": frozenset("AC"), "LH_XOVER": frozenset("BD"), "DOUBLE_XOVER": frozenset("ABCD")}
TRACK_WALK_LIMIT = 200      # segments a leg walk follows before the track counts as a loop
TURNOUT_BLOCK_ATTR = {"A": "blockname", "B": "blockbname", "C": "blockcname", "D": "blockdname"}


class Turnout(NamedTuple):
    """A turnout of tables.xml by its user name."""
    system: str
    comment: str


class Setting(NamedTuple):
    """One beansetting of a stored block path: the turnout's system name and its setting (CLOSED or THROWN)."""
    turnout: str
    setting: str


class BlockPath(NamedTuple):
    """A stored block path: the system name of the block it leads to, and the turnout settings it needs."""
    dest: str
    settings: list[Setting]


def part_map(master: Path) -> dict[str, str]:
    """{part: the block it is part of} of every level's parts (the device master's part_of) in the master at `master`: the
    master that goes with the tables being checked."""
    return {r["user_name"]: r["part_of"] for _n, r in devices.part_lines(("1", "2", "3"), master)}


class Tables:
    def __init__(self, path: Path, root: ET.Element | None = None, parts: dict[str, str] | None = None) -> None:
        """The tables at `path`, or `root` when the caller holds them parsed already (the USS CTC view). `parts`:
        {part: the block it is part of} from the master that goes with these tables (part_map); none when not
        given, never read from the repo behind the caller's back."""
        self.path = path
        self.root = parse_tables(path) if root is None else root
        self.block_user: dict[str, str] = {}
        self.block_sensor: dict[str, str] = {}
        self.paths: dict[str, list[BlockPath]] = {}
        for b in self.root.iter("block"):
            sn = b.get("systemName") or ""
            user = (b.findtext("userName") or "").strip()
            if user:
                self.block_user[sn] = user
            sensor = (b.findtext("occupancysensor") or "").strip()
            if sensor and user:
                self.block_sensor[user] = sensor
            for p in b.findall("path"):
                settings = [Setting(need(to, "systemName"), need(bs, "setting"))
                            for bs in p.findall("beansetting") if (to := bs.find("turnout")) is not None]
                self.paths.setdefault(user, []).append(BlockPath(need(p, "block"), settings))
        self.turnouts: dict[str, Turnout] = {}
        for t in hart_tables.turnouts(self.root):
            user = (t.findtext("userName") or "").strip()
            if user:
                self.turnouts[user] = Turnout((t.findtext("systemName") or "").strip(),
                                              (t.findtext("comment") or "").strip())
        # the full panel only: the band panels (tables.BAND_PANEL_NAMES) copy its elements under the same idents,
        # and a lookup over the whole file would take the copy
        panel = hart_tables.layout_editor(self.root)
        if panel is None:
            raise LayoutFactsError(f"{path}: no main Layout Editor panel ({', '.join(hart_tables.MAIN_PANEL_NAMES)})")
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
        other side is another block. LayoutFactsError when a segment ends at a slip, a level crossing or a name not
        on the panel."""
        if self.paths_stored:
            return {self.block_user.get(bp.dest, bp.dest) for bp in self.paths.get(user, [])}
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
                    # a turnout with no block joins none
                    if (joined_lt := self.turnout_block(self.layout_turnouts[name], kind[-1])) is not None:
                        out.add(joined_lt)
                elif kind.startswith(("SLIP_", "LEVEL_XING_")):
                    raise LayoutFactsError(f"{user}: track segment {seg.get('ident')} ends at {kind} {name}, a slip "
                                           "or level crossing the panel check does not read; give the block a cp")
                elif kind:
                    raise LayoutFactsError(f"{user}: track segment {seg.get('ident')} ends at {kind} {name!r}, "
                                           "which is not on the panel")
        return out - {user}

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

    @staticmethod
    def turnout_block(lt: ET.Element, conn: str) -> str | None:
        """The block at connection `conn` (A to D) of layout turnout `lt`: its own block for that connection, else
        the turnout's block."""
        return lt.get(TURNOUT_BLOCK_ATTR[conn]) or lt.get("blockname")

    def os_of(self, block: str | None) -> str | None:
        """The block `block` is part of (part_of), or `block` itself."""
        return self.part_of.get(block, block) if block else block

    def leg_block(self, ident: str | None, conn: str, own: str | None) -> str | None:
        """Block reached from connection B or C of a layout turnout, past its own OS block (and the parts inside
        it), a part read as the block it is part of (os_of). None when the track ends first; LayoutFactsError when
        the walk passes TRACK_WALK_LIMIT segments (a loop of track inside `own`)."""
        came: tuple[str | None, str | None] = (ident, f"TURNOUT_{conn}")
        seg = next((s for s in self.segments.values()
                    for i in ("1", "2")
                    if (s.get(f"connect{i}name"), s.get(f"type{i}")) == came), None)
        for _ in range(TRACK_WALK_LIMIT):
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
                block = self.os_of(self.turnout_block(self.layout_turnouts[name], kind[-1]))
                return block if block != own else None
            else:
                return None
        raise LayoutFactsError(f"{self.path}: the track from layout turnout {ident} {conn} runs past "
                               f"{TRACK_WALK_LIMIT} segments inside {own} without leaving it")


def desk_leg(t: Tables, cells: Cells, xy: tuple[int, int], edge: str, own: str) -> str | None:
    """The block a desk plant's leg `edge` leads to, read as the Layout Editor's legs are (Tables.leg_block): past
    its own OS block `own` and the parts inside it, a part read as the block it is part of."""
    inside = frozenset(p for p, of in t.part_of.items() if of == own)
    return t.os_of(trace.trace_leg(cells, xy, edge, own=own, inside=inside))


def check_crossover_legs(sw: facts.Switch, lt: ET.Element, t: Tables, r: Report) -> None:
    """Each leg of a crossover's switch against the panel's track (the generated tables.xml stores no paths): its OS
    block is one half of the layout turnout, its thrown leg the other half, and its closed leg the block the track
    reaches from that half's straight-through end (XOVER_DIVERGING)."""
    n = f"Switch {sw.number}"
    pairs = [(t.turnout_block(lt, a), (a, b)) for a, b in XOVER_HALVES]
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


def _check_turnout_bean(sw: facts.Switch, t: Tables, r: Report) -> str | None:
    """The switch's turnout in tables.xml against the device master's hardware and DCC address; its system name, or
    None (reported) when tables.xml has no such turnout."""
    n = f"Switch {sw.number}"
    bean = t.turnouts.get(sw.turnout)
    if bean is None or not bean.system:
        r.add(f"le:{n}", f"{n}: no turnout {sw.turnout!r} in tables.xml")
        return None
    if sw.hardware and bean.system != sw.hardware:
        r.add(f"le:{n}", f"{n}: tables.xml turnout is {bean.system}, the device master says {sw.hardware}")
    # a witness of tables.xml (an output) against the device master's dcc column: the address is read out of the built
    # comment only to hold the build to the master, never used as a fact
    try:
        dcc = split_dcc(bean.comment)[1]
    except ValueError as err:
        dcc = "?"
        r.add(f"le:{n}", f"{n}: tables.xml {err}")
    if sw.dcc and dcc != sw.dcc:
        r.add(f"le:{n}", f"{n}: tables.xml comment DCC {dcc or '-'}, "
                         f"the device master says DCC {sw.dcc}")
    return bean.system


def _check_stored_paths(sw: facts.Switch, system: str, t: Tables, r: Report) -> None:
    """Each leg's OS block's stored block paths: the closed leg reached with the switch Closed or unset, the thrown
    leg Thrown, and neither with the other setting."""
    n = f"Switch {sw.number}"
    for leg in sw.legs:
        leg_paths = t.paths.get(leg.os_block)
        if not leg_paths:
            r.add(f"le:{n}", f"{n}: {leg.os_block} has no block paths in tables.xml")
            continue
        seen: dict[str, set[str]] = {}
        for bp in leg_paths:
            dest = t.track_name(t.block_user.get(bp.dest, bp.dest))
            mine = {s.setting for s in bp.settings if s.turnout in (sw.turnout, system)}
            seen.setdefault(dest, set()).update(mine or {"none"})
        for want, ok, bad, label in ((leg.closed, {CLOSED, "none"}, THROWN, "closed"),
                                     (leg.thrown, {THROWN}, CLOSED, "thrown")):
            got = seen.get(want)
            if got is None or not (got & ok) or bad in got:
                r.add(f"le:{n}", f"{n}: {leg.os_block} block paths reach {want} with "
                                 f"{sorted(got) if got else 'no path'} for {sw.turnout}; "
                                 f"switches.csv says it is the {label} leg")


def check_tables(sw: facts.Switch, t: Tables, r: Report) -> None:
    """One switch of switches.csv against tables.xml: its turnout, its layout turnout's turnout, block and legs, and
    the stored block paths when the tables store them."""
    n = f"Switch {sw.number}"
    system = _check_turnout_bean(sw, t, r)
    if system is None:
        return
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
    if t.paths_stored:          # the generated tables.xml (ADR-029) stores no paths to hold to the legs
        _check_stored_paths(sw, system, t, r)
