"""The rules that join the railroad's fact files: each an INVARIANT that Railroad.check runs (hartlib.railroad)."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from . import level_devices, level_masts, tables
from .railroad_facts import (NameRow, UNIQUE_HARDWARE, check_virtual_names, device_list, natural,
                             switch_number)

if TYPE_CHECKING:
    from .railroad import Railroad

# ---------------------------------------------------------------- the rows of devices.csv, every level

def _at(n: int, r, where: str) -> str:
    return f"{where} line {n} (level {r['level']} {r['layer']} {r['user_name']})"


def device_row_problems(lines, helix_blocks: set[str], where: str = "devices.csv",
                        helix_file: str = "helix_tracks.csv") -> list[str]:
    """The rules between the rows of devices.csv, one for every level, as problems naming the rows. `lines` are
    (line, master row) of every level (outside devices.OUT_OF_MAPS); `helix_blocks` the blocks of helix_tracks.csv.
    - every block has exactly one occupancy row naming it, on any level; a block named on more than one level is a
      helix block (one JMRI block from its staging switch up the helix, owner 2026-11-20), and every helix block is;
    - no two rows of one layer share a user name (but a helix block's rows), a system name (a turnout, sensor or head's
      is no other such row's, of any of those layers) or a jmri_name (but a virtual LCC alias, which stands on its
      turnout's); no two turnouts share a DCC address;
    - every turnout has exactly one LCC alias "DCC <its user name>" on its DCC address, MTT<dcc>, bound by its own
      system name when it is a field device and by its turnout's jmri_name when it is virtual (one internal turnout)."""
    lines = list(lines)
    bad = []
    block_levels = defaultdict(list)
    for n, r in lines:
        if r["layer"] == "block":
            block_levels[r["user_name"]].append((n, r))
    shared = {b for b, rs in block_levels.items() if len({r["level"] for _n, r in rs}) > 1}
    if shared != helix_blocks:
        bad.append(f"{where}: blocks named on more than one level: {sorted(shared) or 'none'}; exactly the helix "
                   f"blocks of {helix_file} ({sorted(helix_blocks)}) are")
    served = defaultdict(list)
    for n, r in lines:
        if r["layer"] == "occupancy":
            for b in device_list(r["blocks"]):
                served[b].append(n)
    for b in sorted(set(block_levels) | set(served)):
        if b not in block_levels:
            bad.append(f"{where} line(s) {', '.join(map(str, served[b]))}: occupancy of {b}, which is no block row")
        elif len(served[b]) != 1:
            lines_ = ", ".join(str(n) for n, _r in block_levels[b])
            bad.append(f"{where} line {lines_}: block {b} has {len(served[b])} occupancy rows naming it "
                       f"({', '.join(map(str, served[b])) or 'none'}), not one")
    for col in ("system_name", "user_name", "jmri_name", "dcc"):
        seen: dict[tuple[str, str], int] = {}
        for n, r in lines:
            v = r[col]
            if not v or (col == "user_name" and r["layer"] == "block" and v in shared) or \
                    (col == "dcc" and r["role"] != "turnout") or \
                    (col == "jmri_name" and r["role"] == "lcc_alias" and r["assignment"] == "virtual"):
                continue                    # an LCC alias carries its turnout's address; a virtual one its name
            # one physical device is one row: a turnout, sensor or head's system name is no other such row's
            kind = "hardware" if col == "system_name" and r["layer"] in UNIQUE_HARDWARE else r["layer"]
            key = (kind, v)
            if key in seen:
                bad.append(f"{_at(n, r, where)}: {col} {v!r} is line {seen[key]}'s as well")
            seen.setdefault(key, n)
    turnouts = {(r["level"], r["dcc"]): r for _n, r in lines if r["role"] == "turnout" and r["dcc"]}
    aliases = defaultdict(int)
    for n, r in lines:
        if r["role"] != "lcc_alias":
            continue
        aliases[(r["level"], r["dcc"])] += 1
        t = turnouts.get((r["level"], r["dcc"]))
        if t is None:
            bad.append(f"{_at(n, r, where)}: no level {r['level']} turnout has its DCC address {r['dcc'] or 'none'}")
            continue
        field = r["assignment"] == "field"
        want = (f"DCC {t['user_name']}", f"MTT{r['dcc']}", f"MTT{r['dcc']}" if field else t["jmri_name"])
        if (r["user_name"], r["system_name"], r["jmri_name"]) != want:
            bad.append(f"{_at(n, r, where)}: the LCC alias of {t['user_name']} (DCC {r['dcc']}) is user, system and "
                       f"jmri name {', '.join(want)} ({'a field device' if field else 'on its turnout'}), not "
                       f"{r['user_name']}, {r['system_name']}, {r['jmri_name']}")
    for n, r in lines:
        if r["role"] == "turnout" and aliases[(r["level"], r["dcc"])] != 1:
            bad.append(f"{_at(n, r, where)}: {aliases[(r['level'], r['dcc'])]} LCC aliases carry its DCC address "
                       f"{r['dcc'] or 'none'}, not one")
    return bad


def master_rows(rr: Railroad) -> list[tuple[int, dict]]:
    """(line, row) of every level's rows of devices.csv that a device map holds (hartlib.devices): not a level-less
    device, which is on no level's map yet."""
    from . import devices
    return [(n, r) for n, r in enumerate(devices.load(rr.sources.devices), 2)
            if r["role"] not in devices.OUT_OF_MAPS and not devices.is_unplaced(r)]


# ---------------------------------------------------------------- invariants

@dataclass(frozen=True)
class Problem:
    invariant: str
    message: str

    def __str__(self) -> str:
        return f"{self.invariant}: {self.message}"


@dataclass(frozen=True)
class Invariant:
    name: str
    layer: str                                  # the latest layer it reads
    run: Callable[[Railroad], list[str]]
    doc: str


INVARIANTS: list[Invariant] = []


def invariant(name: str, layer: str):
    def wrap(fn):
        INVARIANTS.append(Invariant(name, layer, fn, (fn.__doc__ or "").strip()))
        return fn
    return wrap


def switch_levels(rr: Railroad) -> dict[str, dict[int, str]]:
    """{switch number: {level: the file that puts it there}} of every level's switches: staging's in switches.csv,
    main and upper's in their interlockings and switches.csv (a local switch's area)."""
    out: dict[str, dict[int, str]] = {}
    for n, sw in rr.switches.items():
        out.setdefault(str(n), {})[int(sw.level)] = rr.sources.switches.name
    for s, sw in rr.main_upper_switches.items():
        src = rr.sources.interlockings.name if sw.cp else rr.sources.switches.name
        out.setdefault(s, {})[sw.level] = src
    return out


@invariant("switch-numbers", "inputs")
def _switch_numbers(rr: Railroad) -> list[str]:
    """Switch plate numbers are unique railroad-wide: no number is a switch of two levels (switch_levels); every
    interlocking's switches are switches of its own level; each main and upper interlocking (control point) is named
    "CP <its lowest switch>"."""
    bad = []
    levels = switch_levels(rr)
    for s, on in sorted(levels.items(), key=lambda kv: natural(kv[0])):
        if len(on) > 1:
            bad.append(f"Switch {s} is a switch of levels " +
                       " and ".join(f"{lv} ({src})" for lv, src in sorted(on.items())))
    for i in rr.interlockings:
        bad += [f"{rr.sources.interlockings.name} line {i.line}: level {i.level} interlocking {i.name} lists Switch "
                f"{s}, which is no level {i.level} switch" for s in i.switches if i.level not in levels.get(s, {})]
    for cp in rr.level_control_points:
        want = f"CP {min(cp.switches, key=int)}"
        if cp.name != want:
            bad.append(f"{rr.sources.interlockings.name} line {cp.line}: {cp.name} is named {want} by "
                       "its lowest switch")
    return bad


@invariant("lcos-nodes", "inputs")
def _lcos_nodes(rr: Railroad) -> list[str]:
    """Every level and area a main or upper switch is in has an LCOS node to put it on, every staging node (the node
    of a staging turnout's or sensor's packed address, the name map of devices.csv) is a staging row of the node
    file, and no main or upper row is a staging node."""
    pool = {(n.level, n.area) for n in rr.lcos_nodes}
    bad = [f"no node in {rr.sources.lcos_nodes.name} for level {lv} {area} (switches "
           f"{', '.join(sorted((s for s, sw in rr.main_upper_switches.items() if (sw.level, sw.area) == (lv, area)), key=natural))})"
           for lv, area in sorted({(sw.level, sw.area) for sw in rr.main_upper_switches.values()} - pool)]
    staging_nodes: dict[int, str] = {}
    for r in rr.name_map.live.values():
        m = re.fullmatch(r"(?:M2T|M2S|IH)(\d+)", r.hardware)
        if m and len(m.group(1)) >= 3:
            staging_nodes.setdefault(int(m.group(1)) // 100, f"{r.layer} {r.proposed} ({r.hardware})")
    wired = {int(m.group(1)) // 100 for r in rr.name_map.live.values()
             if (m := re.fullmatch(r"M2[TS](\d{3,})", r.hardware))}     # LCOS turnouts and sensors; an IH number may
    level_of = {n.node: n for n in rr.lcos_nodes}                            # be a panel lamp's (IH9990), on no node
    for node, what in sorted(staging_nodes.items()):
        n = level_of.get(node)
        if n is None:
            if node in wired:
                bad.append(f"staging node {node} ({what}) is not in {rr.sources.lcos_nodes.name}")
        elif n.level != 1:
            bad.append(f"{rr.sources.lcos_nodes.name} line {n.line}: node {node} is level {n.level}, but it is "
                       f"staging's ({what})")
    return bad


@invariant("name-map", "inputs")
def _name_map(rr: Railroad) -> list[str]:
    """The name map of devices.csv resolves: every historical alias names a live row of its layer; every staging switch has
    a live turnout row with hardware and a DCC address; no two live turnouts share a DCC address; and no two live
    turnouts, feedback sensors, occupancy sensors or heads share hardware."""
    nm = rr.name_map
    bad = [f"{nm.path.name}: {r.layer} {r.current!r} is an alias of {r.proposed!r}, which has no "
           f"live row (current == proposed)" for r in nm.aliases if (r.layer, r.proposed) not in nm.live]
    for n, sw in rr.switches.items():
        if not sw.hardware or not sw.dcc:
            bad.append(f"Switch {n} (switches.csv): {nm.path.name} has no live turnout row with hardware and dcc")
    dcc: dict[str, NameRow] = {}
    hardware: dict[tuple[str, str], NameRow] = {}
    for r in nm.live.values():
        if r.layer == "turnout" and r.dcc:
            if r.dcc in dcc:
                bad.append(f"{nm.path.name} lines {dcc[r.dcc].line} and {r.line}: DCC {r.dcc} is "
                           f"{dcc[r.dcc].proposed} and {r.proposed}")
            dcc.setdefault(r.dcc, r)
        if r.layer in UNIQUE_HARDWARE and r.hardware:
            key = (r.layer, r.hardware)
            if key in hardware:
                bad.append(f"{nm.path.name} lines {hardware[key].line} and {r.line}: {r.layer}s "
                           f"{hardware[key].proposed} and {r.proposed} are both {r.hardware}")
            hardware.setdefault(key, r)
    return bad


@invariant("staging-blocks", "inputs")
def _staging_blocks(rr: Railroad) -> list[str]:
    """Every block a staging switch leg (switches.csv), a staging mast (staging_masts.csv) or a measured
    length (block_lengths.csv) names is a live block of the name map of devices.csv, and every staging mast a live mast."""
    blocks, masts = rr.name_map.names("block"), rr.name_map.names("mast")
    bad = []
    for sw in rr.switches.values():
        for leg in sw.legs:
            for what, b in (("OS block", leg.os_block), ("closed leg", leg.closed), ("thrown leg", leg.thrown)):
                if b not in blocks:
                    bad.append(f"Switch {sw.number} (switches.csv): {what} {b} is no live block of the name map")
    for m in rr.staging_masts:
        where = f"{rr.sources.staging_masts.name}: {m.mast}"
        if m.mast not in masts:
            bad.append(f"{where}: no live mast {m.mast} in the name map")
        bad += [f"{where}: block {b} is no live block of the name map" for b in (m.facing, *m.protects)
                if b not in blocks]
    # block_lengths.csv holds every level's JMRI blocks (step 5 part 2): staging's live blocks and main and upper's
    # block rows of devices.csv, their parts among them (a main or upper part is a JMRI block of its own on its OS
    # block's sensor, owner 2026-11-20)
    from hartlib import devices
    level_blocks = {r["user_name"] for r in devices.load(rr.sources.devices)
                    if r["level"] in ("2", "3") and r["layer"] == "block"}
    bad += [f"{rr.sources.block_lengths.name}: {name} is no live block of the name map or main and upper block row "
            "of devices.csv" for name in rr.block_lengths if name not in blocks | level_blocks]
    return bad


@invariant("plan-overrides", "inputs")
def _plan_overrides(rr: Railroad) -> list[str]:
    """plan_overrides.json's main_upper section renames plan switches to main and upper switches only, every main and
    upper switch is named by it, and each `move` edit names a plan switch the relabel renames."""
    po, mu = rr.plan_overrides, rr.main_upper_switches
    targets = {switch_number(v): k for k, v in po.relabel.items()}
    bad = [f"{po.name}: relabel {old!r} -> {new!r}: {switch_number(new)} is no main or upper switch"
           for old, new in po.relabel.items() if switch_number(new) not in mu]
    bad += [f"Switch {s} ({mu[s].cp or 'local'}): no plan switch is relabelled to it in {po.name}"
            for s in sorted(set(mu) - set(targets), key=natural)]
    bad += [f"{po.name}: move edit names {e.get('switch')!r}, which the relabel does not rename"
            for e in po.edits if e["op"] == "move" and e.get("switch") not in po.relabel]
    return bad


@invariant("hands", "hands")
def _hands(rr: Railroad) -> list[str]:
    """Each hand label of switches.csv is a main or upper switch the plan's relabel names (a crossover half by its label)."""
    targets = set(rr.plan_overrides.relabel.values())
    return [f"{rr.sources.switches.name} line {h.line}: {label} is no label the plan's relabel gives"
            for label, h in rr.hands.items() if label not in targets and label + "*" not in targets] + \
           [f"{rr.sources.switches.name} line {h.line}: {label} is no main or upper switch"
            for label, h in rr.hands.items() if switch_number(label) not in rr.main_upper_switches]


@invariant("device-map", "device_map")
def _device_map(rr: Railroad) -> list[str]:
    """The device map's turnouts are exactly the main and upper switches, on their own level and control point; its
    virtual names follow hartlib.level_devices (check_virtual_names); its nodes are the level's LCOS nodes; and the
    rows of every level hold to each other (device_row_problems: one occupancy row per block, names, DCC addresses
    and system names given once, every turnout's one LCC alias), before tables.xml is built."""
    dm, mu, name = rr.device_map, rr.main_upper_switches, rr.sources.devices.name
    bad = list(check_virtual_names(dm.rows))
    bad += device_row_problems(master_rows(rr), {h.block for h in rr.helix_tracks.values()}, name,
                               rr.sources.helix_tracks.name)
    turnouts = dm.turnouts
    for s in sorted(set(mu) | set(turnouts), key=natural):
        r, sw = turnouts.get(s), mu.get(s)
        if r is None:
            bad.append(f"Switch {s} ({sw.cp or 'local'}, level {sw.level}): no turnout row in {name}")
            continue
        if sw is None:
            bad.append(f"{name} line {r.line}: Switch {s} is in no control point and not a local switch (an area) in "
                       f"{rr.sources.switches.name}")
            continue
        if (r.level, r.cp) != (sw.level, sw.cp):
            bad.append(f"{name} line {r.line}: Switch {s} is level {r.level} {r.cp or 'local'}, the control points "
                       f"say level {sw.level} {sw.cp or 'local'}")
    nodes = {n.node: n for n in rr.lcos_nodes if n.level != 1}     # staging's nodes are as built: none is the map's
    # a helix block runs from staging up to main or upper: its detector may be on either main or upper level's node
    # (owner, 2026-11-20: both helix tracks on helix node 41)
    helix = {b for h in rr.helix_tracks.values() for b in (h.block, level_devices.occupancy_user(h.block))}
    for r in dm.rows:
        if r.node and (not r.node.isdigit() or int(r.node) not in nodes or
                       (nodes[int(r.node)].level != r.level and r.user_name not in helix)):
            bad.append(f"{name} line {r.line}: {r.layer} {r.user_name} is on node {r.node}, no level {r.level} node "
                       f"of {rr.sources.lcos_nodes.name}")
    return bad


@invariant("name-clash", "device_map")
def _name_clash(rr: Railroad) -> list[str]:
    """No name-map row of devices.csv, live or historical alias, uses a name the device map gives a main or upper
    device of the same layer: a rename pass that maps the alias would rename the main or upper device. A helix block
    (helix_tracks.csv) is one block from staging up the helix, so its live row names the device map's block too."""
    dm = {(r.layer, r.user_name): r for r in rr.device_map.rows}
    helix = {h.block for h in rr.helix_tracks.values()}
    out = []
    for r in rr.name_map.rows:
        hit = dm.get((r.layer, r.current))
        if hit is not None and not (r.layer == "block" and r.identity and r.current in helix):
            what = "live" if r.identity else f"an alias of {r.proposed}"
            out.append(f"{rr.name_map.path.name}: {r.layer} {r.current} is {what} there and level "
                       f"{hit.level} {r.layer} {hit.user_name} in {rr.sources.devices.name}")
    return out


@invariant("level-masts", "masts")
def _level_masts(rr: Railroad) -> list[str]:
    """Each main_upper_masts.csv mast is a device map mast of the same control point, on its virtual and planned
    names; its switch is in that control point (an APB intermediate has no switch; a spur's exit dwarf at a local
    switch has no control point, ADR-024); its facing and protected blocks are device map blocks; and every device
    map mast has a row. A virtual mast (a destination at a buffer stop, level_masts.is_level_virtual) stands at no
    switch, protects nothing, and its control point is its track's switch's, if any. A main or upper part (a link
    inside an OS block, devices.csv part_of) is a JMRI block of its own (owner, 2026-11-20), so a mast may face or
    protect it, as Signal Mast Logic discovery does."""
    from hartlib import devices
    dm, name = rr.device_map, rr.sources.level_masts.name
    masts = dm.by_user("mast")
    blocks = set(dm.blocks) | {r["user_name"] for _line, r in devices.part_lines(("2", "3"), rr.sources.devices)}
    cps = {cp.name: cp for cp in rr.level_control_points}
    bad, seen = [], set()
    for r in rr.level_masts:
        seen.add(r["mast"])
        m = masts.get(r["mast"])
        if m is None:
            bad.append(f"{name}: {r['mast']} is no mast of the device map")
            continue
        if (r["cp"], r["system_name"], r["device_system_name"]) != (m.cp, m.jmri_name, m.system_name):
            bad.append(f"{name}: {r['mast']} is {r['cp']} {r['system_name']} on {r['device_system_name']}; the "
                       f"device map says {m.cp} {m.jmri_name} on {m.system_name}")
        if level_masts.is_level_virtual(r["system_name"]):
            if r["switch"] or r["protects"]:
                bad.append(f"{name}: virtual {r['mast']} stands at a switch or protects a block; it stands at a "
                           "buffer stop")
            if r["cp"] and r["cp"] not in cps:
                bad.append(f"{name}: virtual {r['mast']} names control point {r['cp']!r}, which is none")
            if r["facing"] not in blocks:
                bad.append(f"{name}: virtual {r['mast']} faces {r['facing']}, which is no device map block")
            continue
        if not r["switch"]:
            if r["cp"] not in cps:          # an APB intermediate: between two track blocks, in its track's CP
                bad.append(f"{name}: {r['mast']} (an intermediate) names control point {r['cp']!r}, which is none")
        elif not r["cp"]:
            if r["switch"] not in rr.main_upper_switches:
                bad.append(f"{name}: {r['mast']} names Switch {r['switch']}, which is on neither level")
            elif rr.main_upper_switches[r["switch"]].cp:
                bad.append(f"{name}: {r['mast']} has no control point, but Switch {r['switch']} is in "
                           f"{rr.main_upper_switches[r['switch']].cp}")
        elif r["switch"] not in (cps[r["cp"]].switches if r["cp"] in cps else ()):
            bad.append(f"{name}: {r['mast']} protects Switch {r['switch']}, which is not in {r['cp']}")
        bad += [f"{name}: {r['mast']} {what} {b}, which is no device map block"
                for what, b in (("faces", r["facing"]), ("protects", r["protects"])) if b not in blocks]
    bad += [f"{name}: device map mast {m} has no row" for m in sorted(set(masts) - seen, key=natural)]
    return bad


@invariant("tables", "tables")
def _tables(rr: Railroad) -> list[str]:
    """tables.xml holds the fact files' devices: every staging switch's turnout and the blocks of its legs
    (switches.csv), and every mast of both mast files (staging_masts.csv, main_upper_masts.csv) on
    the system name its file gives it. The rows of devices.csv, every level's, are held to their beans by
    tools/schematic/check_device_master.py (check_tables)."""
    t, bad = rr.tables, []
    for sw in rr.switches.values():
        if sw.turnout not in t.turnouts:
            bad.append(f"Switch {sw.number} (switches.csv): no turnout {sw.turnout} in tables.xml")
        bad += [f"Switch {sw.number} (switches.csv): no block {b} in tables.xml"
                for leg in sw.legs for b in (leg.os_block, leg.closed, leg.thrown) if b not in t.blocks]
    masts = [(rr.sources.staging_masts.name, m.mast, m.system_name) for m in rr.staging_masts]
    masts += [(rr.sources.level_masts.name, r["mast"], r["system_name"]) for r in rr.level_masts]
    for name, mast, system in masts:
        if not system:
            bad.append(f"{name}: {mast} has no system name")
        elif t.masts.get(mast) != system:
            bad.append(f"{name}: {mast}: tables.xml has {t.masts.get(mast) or 'no such mast'}, the file says "
                       f"{system}")
    return bad


