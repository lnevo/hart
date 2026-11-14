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
CATS desks (HART_CTC.xml, HART_ABS.xml) and cats/data/turnout_bindings.csv
  - each plant's turnout, the leg each command (close/throw) leads to, and which
    leg is NORMAL (the closed one, unless the switch is CATS-inverted);
  - every block name on the desk is a Layout Editor block.
Levels (control_points.csv, switches.csv, public_name_map.csv)
  - each control point's switches are on its level, and every cp in the name map has a row;
  - every mast and block has one level: its switch's, its control point's, or, for a
    main between control points, the one level of the blocks its tables.xml paths join.
USS CTC (CTC code buttons in tables.xml, ctc/GUIObjects.xml and the copy in tables.xml)
  - the code button's turnout, OS sensors, lever and signal levers;
  - the lever, the points dot and its polarity in the switch's column;
  - the track jewels and labels are the ones the CATS desk gives today.

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
from hartlib import paths, tables as hart_tables  # noqa: E402

ROOT = paths.REPO_ROOT
HART = paths.LAYOUT_DIR
sys.path.insert(0, str(paths.LAYOUT_SCRIPTS))
sys.path.append(str(paths.CATS_DIR / "scripts"))

import layout_facts as facts  # noqa: E402
import digicon_trace as trace  # noqa: E402

TABLES = paths.TABLES_XML
GUI = HART / "ctc/GUIObjects.xml"
DESKS = (ROOT / "cats/panels/HART_CTC.xml", ROOT / "cats/panels/HART_ABS.xml")
TURNOUT_BINDINGS = ROOT / "cats/data/turnout_bindings.csv"
OCCUPANCY = ROOT / "cats/data/occupancy_bindings.csv"

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
    def __init__(self, path: Path) -> None:
        self.path = path
        self.root = parse_tables(path)
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
    dcc = re.search(r"DCC:\s*(\d+)", comment)
    if sw.dcc and (dcc.group(1) if dcc else "") != sw.dcc:
        r.add(f"le:{n}", f"{n}: tables.xml comment DCC {dcc.group(1) if dcc else '-'}, "
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
        plants = trace.desk_plants(cells)
    except trace.PlantError as err:
        r.add(f"cats:{path.name}", f"{path.name}: {err}")
        plants = {}
    return cells, plants


def check_desk(path: Path, switches: dict[int, facts.Switch], t: Tables, r: Report) -> None:
    desk = path.name
    cells, plants = desk_plants(path, r)
    by_os = facts.legs_by_os(switches)
    for os_name, xy in plants.items():
        if os_name not in by_os:
            r.add(f"cats:{os_name}", f"{desk}: plant at {xy} is in {os_name}, which switch_legs.csv does not list")
    jmri_blocks = t.block_names()
    names = {b.get("NAME") for b in parse(path).getroot().iter("BLOCK") if b.get("NAME")}
    for name in sorted(names - jmri_blocks):
        r.add(f"cats-track:{name}", f"{desk}: block {name} is not a Layout Editor block in tables.xml")
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


def check_turnout_bindings(path: Path, switches: dict[int, facts.Switch], r: Report) -> None:
    by_ident = {sw.le_ident: sw for sw in switches.values()}
    seen = set()
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ident = row["layout_ident"].strip()
            sw = by_ident.get(ident)
            if sw is None:
                r.add(f"bindings:{ident}", f"{path.name}: {ident} is not a le_ident in switches.csv")
                continue
            seen.add(sw.number)
            n = f"Switch {sw.number}"
            if row["os_block"].strip() != sw.legs[0].os_block:
                r.add(f"bindings:{n}", f"{n}: {path.name} puts {ident} in {row['os_block']}, "
                                       f"switch_legs.csv in {sw.legs[0].os_block}")
            if row["turnout_user_or_system"].strip() not in (sw.turnout, sw.hardware):
                r.add(f"bindings:{n}", f"{n}: {path.name} binds {ident} to {row['turnout_user_or_system']}, "
                                       f"switches.csv to {sw.turnout} ({sw.hardware})")
    for n in sorted(set(switches) - seen):
        r.add(f"bindings:Switch {n}", f"Switch {n}: not in {path.name}")


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
    # Track jewels and labels against a fresh build from the CATS desk.
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


def check_levels(switches: dict[int, facts.Switch], data: Path, t: Tables, r: Report) -> None:
    """Each control point, mast and block has one level, and it agrees with its switches."""
    by_cp = facts.cp_levels(data)
    for cp in facts.load_control_points(data):
        for item in cp["switches"].split(","):
            num = re.match(r"\d+", item.strip())
            sw = switches.get(int(num.group(0))) if num else None
            if sw and sw.level != cp["level"]:
                r.add(f"level:Switch {sw.number}", f"Switch {sw.number}: switches.csv level {sw.level}, "
                                                   f"control_points.csv puts {cp['cp_name']} on level {cp['level']}")
    rows = facts.identity_rows(data)
    for cp in sorted({row["cp"] for row in rows if row["cp"]} - set(by_cp)):
        r.add(f"level:{cp}", f"{cp}: a cp in public_name_map.csv with no row (and no level) in control_points.csv")
    for sw in switches.values():
        for leg in sw.legs:
            cp = next((row["cp"] for row in rows if row["layer"] == "block" and row["proposed"] == leg.os_block), "")
            if cp in by_cp and by_cp[cp] != sw.level:
                r.add(f"level:Switch {sw.number}", f"Switch {sw.number}: {leg.os_block} is in {cp} "
                                                   f"(level {by_cp[cp]}), switches.csv says level {sw.level}")
    levels = facts.name_map_levels(data, switches)
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
        bindings: Path = TURNOUT_BINDINGS, occupancy: Path = OCCUPANCY) -> Report:
    import gen_ctc_track_plan as gen

    r = Report()
    switches = facts.load_switches(data)
    t = Tables(tables)
    check_data(switches, data, r)
    check_levels(switches, data, t, r)
    for sw in switches.values():
        check_tables(sw, t, r)
    for desk in desks:
        check_desk(Path(desk), switches, t, r)
    check_turnout_bindings(bindings, switches, r)
    check_ctc_buttons(switches, t, occupancy_sensors(occupancy), r)
    cells = gen.parse_cats(Path(desks[0]))
    for label, path in (("GUIObjects.xml", gui), ("tables.xml USS panel", tables)):
        check_uss_panel(label, uss_panel(Path(path).read_text(encoding="utf-8")), switches, gen, cells, r)
    return r


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", type=Path, default=facts.DATA)
    ap.add_argument("--tables", type=Path, default=TABLES)
    ap.add_argument("--desk", type=Path, action="append", help="CATS desk (repeat); default CTC and ABS")
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
