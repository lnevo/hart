"""The rules that join the railroad's fact files: each an INVARIANT that Railroad.check runs (hartlib.railroad)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from . import level_devices, level_masts, tables
from .railroad_facts import (DeviceRow, NameRow, UNIQUE_HARDWARE, check_virtual_names, natural,
                             switch_number)

if TYPE_CHECKING:
    from .railroad import Railroad

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


@invariant("switch-numbers", "inputs")
def _switch_numbers(rr: Railroad) -> list[str]:
    """Switch plate numbers are unique railroad-wide: no main or upper switch (interlockings.csv,
    local_switches_main_upper.csv) reuses a staging number (switches.csv); every staging interlocking's switches are
    staging switches; each main and upper interlocking (control point) is named "CP <its lowest switch>"."""
    bad = []
    staging = {str(n) for n in rr.switches}
    for s, sw in sorted(rr.main_upper_switches.items(), key=lambda kv: natural(kv[0])):
        if s in staging:
            bad.append(f"Switch {s} is a staging switch (switches.csv) and a level {sw.level} switch")
    for i in rr.interlockings:
        if i.level == 1:
            bad += [f"{rr.sources.interlockings.name} line {i.line}: staging interlocking {i.name} lists Switch {s}, "
                    "which is no staging switch (switches.csv)" for s in i.switches if s not in staging]
    for cp in rr.level_control_points:
        want = f"CP {min(cp.switches, key=int)}"
        if cp.name != want:
            bad.append(f"{rr.sources.interlockings.name} line {cp.line}: {cp.name} is named {want} by "
                       "its lowest switch")
    return bad


@invariant("lcos-nodes", "inputs")
def _lcos_nodes(rr: Railroad) -> list[str]:
    """Every level and area a main or upper switch is in has an LCOS node to put it on, and no main or upper node
    number is a staging node (the node of a staging turnout's or sensor's packed address, the name map of devices.csv)."""
    pool = {(n.level, n.area) for n in rr.lcos_nodes}
    bad = [f"no node in {rr.sources.lcos_nodes.name} for level {lv} {area} (switches "
           f"{', '.join(sorted((s for s, sw in rr.main_upper_switches.items() if (sw.level, sw.area) == (lv, area)), key=natural))})"
           for lv, area in sorted({(sw.level, sw.area) for sw in rr.main_upper_switches.values()} - pool)]
    staging_nodes: dict[int, str] = {}
    for r in rr.name_map.live.values():
        m = re.fullmatch(r"(?:M2T|M2S|IH)(\d+)", r.hardware)
        if m and len(m.group(1)) >= 3:
            staging_nodes.setdefault(int(m.group(1)) // 100, f"{r.layer} {r.proposed} ({r.hardware})")
    for n in rr.lcos_nodes:
        if n.node in staging_nodes:
            bad.append(f"{rr.sources.lcos_nodes.name} line {n.line}: node {n.node} is staging's "
                       f"({staging_nodes[n.node]})")
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
    """Every block a staging switch leg (switch_legs.csv), a staging mast (staging_masts.csv) or a measured
    length (block_lengths.csv) names is a live block of the name map of devices.csv, and every staging mast a live mast."""
    blocks, masts = rr.name_map.names("block"), rr.name_map.names("mast")
    bad = []
    for sw in rr.switches.values():
        for leg in sw.legs:
            for what, b in (("OS block", leg.os_block), ("closed leg", leg.closed), ("thrown leg", leg.thrown)):
                if b not in blocks:
                    bad.append(f"Switch {sw.number} (switch_legs.csv): {what} {b} is no live block of the name map")
    for m in rr.staging_masts:
        where = f"{rr.sources.staging_masts.name}: {m.mast}"
        if m.mast not in masts:
            bad.append(f"{where}: no live mast {m.mast} in the name map")
        bad += [f"{where}: block {b} is no live block of the name map" for b in (m.facing, *m.protects)
                if b not in blocks]
    bad += [f"{rr.sources.block_lengths.name}: {name} is no live block of the name map"
            for name in rr.block_lengths if name not in blocks]
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
    """Each hands.csv label is a main or upper switch the plan's relabel names (a crossover half by its label)."""
    targets = set(rr.plan_overrides.relabel.values())
    return [f"{rr.sources.hands.name} line {h.line}: {label} is no label the plan's relabel gives"
            for label, h in rr.hands.items() if label not in targets and label + "*" not in targets] + \
           [f"{rr.sources.hands.name} line {h.line}: {label} is no main or upper switch"
            for label, h in rr.hands.items() if switch_number(label) not in rr.main_upper_switches]


@invariant("device-map", "device_map")
def _device_map(rr: Railroad) -> list[str]:
    """The device map's turnouts are exactly the main and upper switches, each with its LCC alias "DCC Switch <n>",
    on its own level and control point; its virtual names follow hartlib.level_devices (check_virtual_names); its
    nodes are the level's LCOS nodes; its DCC addresses and planned hardware are no staging device's."""
    dm, mu, name = rr.device_map, rr.main_upper_switches, rr.sources.devices.name
    bad = list(check_virtual_names(dm.rows))
    turnouts = dm.turnouts
    aliases = {r.user_name.removeprefix("DCC Switch "): r for r in dm.of("turnout") if r.role == "lcc_alias"}
    for s in sorted(set(mu) | set(turnouts), key=natural):
        r, sw = turnouts.get(s), mu.get(s)
        if r is None:
            bad.append(f"Switch {s} ({sw.cp or 'local'}, level {sw.level}): no turnout row in {name}")
            continue
        if sw is None:
            bad.append(f"{name} line {r.line}: Switch {s} is in no control point and not in "
                       f"{rr.sources.local_switches.name}")
            continue
        if (r.level, r.cp) != (sw.level, sw.cp):
            bad.append(f"{name} line {r.line}: Switch {s} is level {r.level} {r.cp or 'local'}, the control points "
                       f"say level {sw.level} {sw.cp or 'local'}")
        a = aliases.get(s)
        if a is None or (a.jmri_name, a.dcc, a.system_name) != (r.jmri_name, r.dcc, f"MTT{r.dcc}"):
            bad.append(f"{name} line {r.line}: Switch {s} has no LCC alias DCC Switch {s} on its turnout and DCC "
                       "address")
    nodes = {n.node: n for n in rr.lcos_nodes}
    # a helix block runs from staging up to main or upper: its detector may be on either level's node (owner,
    # 2026-11-20: both helix tracks on helix node 41)
    helix = {b for h in rr.helix_tracks.values() for b in (h.block, level_devices.occupancy_user(h.block))}
    for r in dm.rows:
        if r.node and (not r.node.isdigit() or int(r.node) not in nodes or
                       (nodes[int(r.node)].level != r.level and r.user_name not in helix)):
            bad.append(f"{name} line {r.line}: {r.layer} {r.user_name} is on node {r.node}, no level {r.level} node "
                       f"of {rr.sources.lcos_nodes.name}")
    staging_dcc = {r.dcc: r for r in rr.name_map.live.values() if r.layer == "turnout" and r.dcc}
    staging_hw = {r.hardware: r for r in rr.name_map.live.values() if r.layer in UNIQUE_HARDWARE and r.hardware}
    seen_hw: dict[str, DeviceRow] = {}
    for r in dm.rows:
        if r.role == "turnout" and r.dcc in staging_dcc:
            bad.append(f"{name} line {r.line}: {r.user_name} has DCC {r.dcc}, staging's {staging_dcc[r.dcc].proposed}")
        if r.layer in UNIQUE_HARDWARE and r.system_name:
            if r.system_name in staging_hw:
                bad.append(f"{name} line {r.line}: {r.user_name} plans {r.system_name}, staging's "
                           f"{staging_hw[r.system_name].proposed}")
            if r.system_name in seen_hw:
                bad.append(f"{name} lines {seen_hw[r.system_name].line} and {r.line}: "
                           f"{seen_hw[r.system_name].user_name} and {r.user_name} both plan {r.system_name}")
            seen_hw.setdefault(r.system_name, r)
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
    switch, protects nothing, and its control point is its track's switch's, if any."""
    dm, name = rr.device_map, rr.sources.level_masts.name
    masts = dm.by_user("mast")
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
            if r["facing"] not in dm.blocks:
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
                for what, b in (("faces", r["facing"]), ("protects", r["protects"])) if b not in dm.blocks]
    bad += [f"{name}: device map mast {m} has no row" for m in sorted(set(masts) - seen, key=natural)]
    return bad


@invariant("tables", "tables")
def _tables(rr: Railroad) -> list[str]:
    """tables.xml holds the facts' devices: every staging switch's turnout and block of its legs, every staging
    mast; every main and upper turnout, occupancy sensor and control-point mast on its virtual name."""
    t, bad = rr.tables, []
    for sw in rr.switches.values():
        if sw.turnout not in t.turnouts:
            bad.append(f"Switch {sw.number} (switches.csv): no turnout {sw.turnout} in tables.xml")
        bad += [f"Switch {sw.number} (switch_legs.csv): no block {b} in tables.xml"
                for leg in sw.legs for b in (leg.os_block, leg.closed, leg.thrown) if b not in t.blocks]
    bad += [f"{rr.sources.staging_masts.name}: no mast {m.mast} in tables.xml"
            for m in rr.staging_masts if m.mast not in t.masts]
    dm = rr.device_map
    for s, r in sorted(dm.turnouts.items(), key=lambda kv: natural(kv[0])):
        if t.turnouts.get(r.user_name) != r.jmri_name:
            bad.append(f"{r.user_name}: tables.xml has {t.turnouts.get(r.user_name) or 'no such turnout'}, the "
                       f"device map says {r.jmri_name}")
    for user, sensor in sorted(dm.sensors.items(), key=lambda kv: natural(kv[0])):
        if t.sensors.get(user) != sensor:
            bad.append(f"{user}: tables.xml has {t.sensors.get(user) or 'no such sensor'}, the device map says "
                       f"{sensor}")
    for r in rr.level_masts:
        if t.masts.get(r["mast"]) != r["system_name"]:
            bad.append(f"{r['mast']}: tables.xml has {t.masts.get(r['mast']) or 'no such mast'}, "
                       f"{rr.sources.level_masts.name} says {r['system_name']}")
    return bad


