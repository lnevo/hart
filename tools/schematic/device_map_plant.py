"""The main and upper plant rows of the device map: every switch's turnout, alias and feedback, every OS block, part
and track with its occupancy row, and the wiring each is planned on.

build_device_map.build() calls these stages in order over one MapBuild (device_map_records), which they fill in
place: switch_and_os_rows, part_rows, track_rows, then, once the masts are placed (device_map_level_masts),
check_frozen_cps and assign_ports. A device wiring.csv holds (frozen, or a pinned detector) keeps its own values;
every other one takes the next free place on a node of its level and area (device_map_nodes.Nodes).
"""
from __future__ import annotations

import re
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mast_rule  # noqa: E402  OVERRIDES_NAME, LOOP_HALF, MapError
from device_map_inputs import PINS, UID, loop_placeholder  # noqa: E402
from device_map_nodes import DetectorInput  # noqa: E402
from device_map_records import DeviceMapRow, Group, Layer, MapBuild, MasterCells, cells  # noqa: E402
from device_map_rows import Wired, device_row, switch_device_rows  # noqa: E402
from device_map_schematic import line_role  # noqa: E402
from device_map_staging import helix_ends, line_cp, part_row  # noqa: E402
from hartlib import device_ids, devices, level_devices, railroad  # noqa: E402
from mast_rule import MapError, Track  # noqa: E402

VIRTUAL_TURNOUT = level_devices.TURNOUT_PREFIX   # + switch number: the internal turnout the panels and desks use
occupancy_user = level_devices.occupancy_user
NOT_WIRED = "detector planned, not wired yet: no node or input (owner, 2026-11-16)"
NO_DETECTOR = "no detector planned: dark until decided"
CORNER = "xover_corner"         # a double crossover's corner block and its occupancy row
OFF_MAIN = "no detector: off the main line"
DETECTOR_OF_NOTE = {NOT_WIRED: "not_wired", NO_DETECTOR: "none"}    # an occupancy row with no input: its detector fact
PART_OF_OS = re.compile(r"OS Switch (\d+)[a-d]?")
PIN_RE = re.compile(r"^Node: (\d+) (Turnout|Signal|Sensor|Block): (\d+)$")


def block_sensor(block: str) -> str:
    """The virtual occupancy sensor of a main or upper block (hartlib.level_devices.block_sensor); MapError on a
    name that gives no clean key."""
    try:
        return level_devices.block_sensor(block)
    except ValueError as exc:
        raise MapError(str(exc)) from exc


def trial_of(st: MapBuild, name: str) -> str:
    """A block's trial name (level_keys); MapError when the block layer draws it on no strand."""
    if name not in st.trials:
        raise MapError(f"{name}: the block layer draws it on no strand, so it has no trial name")
    return st.trials[name]


def track_id(st: MapBuild, name: str) -> str:
    """A block's device ID, from the same plan ends as its trial name: no trial name, no ID (MapError)."""
    trial_of(st, name)
    return st.track_ids[name]


def add(st: MapBuild, level: int, cp: str, layer: Layer, user: str, *, role: str, ident: str, system: str = "",
        node: int | str = "", comment: str = "", trial: str = "", notes: str = "", jmri: str = "",
        **facts: str) -> None:
    """A device-map row with the role (hartlib.devices.ROLES) its caller says it has: no role is read off a name;
    and its device ID (`ident`, hartlib.device_ids), from the plan facts its caller holds. A block row's ID is kept
    in st.block_ids for its detector and the masts facing it. MapError on a fact column that is not one."""
    # device_row gives every column of DeviceMapRow (its own check stops on any other)
    st.rows.append(cast(DeviceMapRow, device_row(level, cp, layer, user, system, node, comment, trial, notes,
                                                 jmri=jmri, role=role, ident=ident, **facts)))
    if layer == "block":
        st.block_ids[(str(level), user)] = ident


def occupancy(st: MapBuild, level: int, cp: str, block: str, *, role: str, system: str = "", node: int | str = "",
              comment: str = "", notes: str = "") -> None:
    """The occupancy row of `block`, whose role (`role`) it shares: its virtual sensor (jmri_name), the block it
    serves and its detector: planned on an input (`system`, M2S), planned with no input yet (NOT_WIRED) or none
    planned (NO_DETECTOR). Its ID is its block's (det:<block id>): add the block row first."""
    detector = "planned" if system else DETECTOR_OF_NOTE.get(notes)
    if detector is None:
        raise MapError(f"occupancy of {block}: no detector and no reason why ({notes!r})")
    add(st, level, cp, "occupancy", occupancy_user(block), system=system, node=node, comment=comment, notes=notes,
        jmri=block_sensor(block), blocks=block, detector=detector, role=role,
        ident=device_ids.det_id(st.block_ids[(str(level), block)]))


def detected(st: MapBuild, level: int, cp: str, block: str, on: DetectorInput, *, role: str) -> None:
    """The occupancy row of `block` with its detector planned on the input `on`."""
    node, k, packed = on
    occupancy(st, level, cp, block, system=f"M2S{packed}", node=node, comment=f"Node: {node} Block: {k + 1}",
              role=role)


def switch_and_os_rows(st: MapBuild, cps: Sequence[railroad.Interlocking]) -> None:
    """Every switch's turnout, alias and feedback rows, control points first and then the local switches, then
    every switch's OS block rows: turnouts first, as a node's 12V boards come before its 5V boards."""
    local = [(s, st.loc[s]) for s in sorted(st.loc, key=railroad.natural)]
    for cp in cps:
        loose = [s for s in cp.switches if ("turnout", f"Switch {s}") not in st.nodes.frozen]
        node = st.nodes.pick(cp.level, cp.area, "turnout", len(loose)) if loose else None
        for s in cp.switches:
            switch_rows(st, Group(cp.level, cp.area, cp.name), s, node)
    for s, r in local:      # no control point: turnout and feedback, no signals or detection
        node = st.nodes.pick(r.level, r.area, "turnout") if ("turnout", f"Switch {s}") not in st.nodes.frozen else None
        switch_rows(st, Group(r.level, r.area, ""), s, node, "no control point: " + r.notes)
    for cp in cps:
        for s in cp.switches:
            os_rows(st, Group(cp.level, cp.area, cp.name), s)
    for s, r in local:
        os_rows(st, Group(r.level, r.area, ""), s, detect=False)


def turnout_wiring(st: MapBuild, s: str, node: int | None) -> Wired:
    """Where the turnout of switch `s` is wired: a frozen turnout's own wiring.csv values, else the next free
    turnout of `node`. MapError when it is not frozen and no node was picked for it."""
    frozen = st.nodes.take_frozen("turnout", f"Switch {s}")
    if frozen:
        packed = frozen.node * 100 + UID["turnout"] + frozen.index
        return Wired(f"M2T{packed}", frozen.node, frozen.wiring_text)
    if node is None:            # switch_and_os_rows picks a node for every control point with a switch not frozen
        raise MapError(f"Switch {s}: not frozen in {PINS.name}, and no node was picked for its turnout")
    k, packed = st.nodes.take(node, "turnout")
    return Wired(f"M2T{packed}", node, f"Node: {node} Turnout: {k}")


def feedback_wiring(st: MapBuild, group: Group, s: str, nr: str, turnout_node: object) -> Wired:
    """Where the feedback `nr` (N or R) of switch `s` is wired: a frozen one's own wiring.csv values, else the next
    free sensor input, on the turnout's node first."""
    fb = st.nodes.take_frozen("fb", f"FB Switch {s} {nr}")
    if fb:
        return Wired(fb.address, fb.node, fb.wiring_text)
    node = st.nodes.pick(group.level, group.area, "sensor", prefer=[turnout_node])
    k, packed = st.nodes.take(node, "sensor")
    return Wired(f"M2S{packed}", node, f"Node: {node} Sensor: {k}")


def switch_rows(st: MapBuild, group: Group, s: str, node: int | None, note: str = "") -> None:
    """A switch's turnout, LCC alias and feedback rows (device_map_rows.switch_device_rows, the one maker, as
    staging's), wired by turnout_wiring and feedback_wiring. Main and upper bind the virtual turnout. Sets st.home
    and st.area_of for the switch."""
    turnout = turnout_wiring(st, s, node)
    st.home[s], st.area_of[s] = cast(int, turnout.node), (group.level, group.area)
    fbs = {nr: feedback_wiring(st, group, s, nr, turnout.node) for nr in "NR"}
    labels = [lb for labels in st.by_level.values() for lb in labels if railroad.switch_number(lb) == s]
    # switch_device_rows makes each row with device_row: every column of DeviceMapRow
    st.rows.extend(cast(list[DeviceMapRow], switch_device_rows(
        group.level, group.cp, s, labels, turnout, fbs, st.dcc[s], jmri=VIRTUAL_TURNOUT + s,
        alias_notes="LCC alias of the MQTT turnout (ADR-005)", notes=note)))


def os_rows(st: MapBuild, group: Group, s: str, detect: bool = True) -> None:
    """A switch's OS block row and its occupancy row; a double crossover's one per corner, corner a detected.
    `detect` False: no detector (off the main line)."""
    if s in st.corner_blocks:
        corner_rows(st, group, s, detect)
        return
    lv, cp, block = group.level, group.cp, f"OS Switch {s}"
    if not detect:
        add(st, lv, cp, "block", block, comment=group.place, trial=block, notes=OFF_MAIN, role="os",
            ident=device_ids.os_id(s))
        occupancy(st, lv, cp, block, notes=NO_DETECTOR, role="os")
        return
    on = st.nodes.detector(block, lv, group.area, st.home[s], st.os_pin_level)
    add(st, lv, cp, "block", block, node=on[0], comment=group.place, trial=block, role="os",
        ident=device_ids.os_id(s))
    detected(st, lv, cp, block, on, role="os")


def corner_rows(st: MapBuild, group: Group, s: str, detect: bool) -> None:
    """A double crossover's block per corner, each corner's ID by the schematic leg it serves (xover_corners: {leg:
    block}), in block name order: corner a keeps the switch's detector, the others are wired later (NOT_WIRED)."""
    lv, cp = group.level, group.cp
    for leg, block in sorted(st.corner_blocks[s].items(), key=lambda kv: kv[1]):
        ident = device_ids.os_id(s, leg)
        note = f"corner {block[-1].upper()} of the double crossover"
        if not detect:
            add(st, lv, cp, "block", block, comment=group.place, trial=block, notes=f"{note}, {OFF_MAIN}",
                role=CORNER, ident=ident)
            occupancy(st, lv, cp, block, notes=NO_DETECTOR, role=CORNER)
        elif not block.endswith("a"):
            add(st, lv, cp, "block", block, comment=group.place, trial=block, notes=note, role=CORNER, ident=ident)
            occupancy(st, lv, cp, block, notes=NOT_WIRED, role=CORNER)
        else:
            on = st.nodes.detector(block, lv, group.area, st.home[s], st.os_pin_level)
            add(st, lv, cp, "block", block, node=on[0], comment=group.place, trial=block, notes=note, role=CORNER,
                ident=ident)
            detected(st, lv, cp, block, on, role=CORNER)


def part_rows(st: MapBuild) -> list[MasterCells]:
    """The master rows of the parts (links inside an OS block), each on the level of its OS block's row, its
    switch's (a link between the halves of the crossovers 127 and 131 drawn on the upper band is in a main level OS
    block). MapError on a piece at one end of a track, or a part of no main or upper switch's OS block."""
    out = []
    for name, part in sorted(st.lay.parts.items(), key=lambda kv: railroad.natural(kv[0])):
        if name != part["track"]["name"]:
            raise MapError(f"{name}: a piece at one end of a main or upper track ({part['why']}); the main and upper "
                           "drawing gives each strand one block, so give the whole track to an OS block")
        m = PART_OF_OS.fullmatch(part["part_of"])
        if not m or m.group(1) not in st.switches:
            raise MapError(f"{name} (level {part['level']}) is part of {part['part_of']}, the OS block of no main or "
                           "upper switch")
        lv = str(st.switches[m.group(1)].level)
        ident = track_id(st, name)
        out.append(dict(part_row(lv, name, part, trial_of(st, name), ident),
                        cp=line_cp(name, lv, part["track"], st.places)))
        st.block_ids[(lv, name)] = ident
    return out


def track_rows(st: MapBuild) -> None:
    """Each main and upper track's block row and occupancy row (a balloon loop's or a split track's, one per half),
    but a part's. MapError on a track ending at a switch of neither level."""
    for t in sorted(st.found, key=lambda t: railroad.natural(t["name"])):
        sws = [v for k, v in t["ends"] if k == "sw" and v is not None]
        stray = [s for s in sws if s not in st.area_of]
        if stray:
            raise MapError(f"{t['name']} ends at switch {', '.join(stray)}, which is on neither the main nor the "
                           "upper level")
        if t["name"] in st.lay.parts:               # a link inside an OS block: its part row, no block or detector
            continue
        split = t["name"] in st.split_names
        for half in sorted(mast_rule.LOOP_HALF.values()) if (t["loop"] or split) else [None]:
            track_half_rows(st, t, sws, half, split)


def track_note(t: Track, half: int | None, split: bool) -> str:
    """The notes of the block row of track `t` (or of its `half`): its length, no detector off the main line, and
    which half it is."""
    cm = round(t["cm"] / 2, 1) if half else t["cm"]
    note = f"{cm} cm" + ("" if t["main"] else f" {OFF_MAIN}")
    if half and split:
        return note + f", half {half} of the split track ({mast_rule.OVERRIDES_NAME})"
    if half:
        return note + f", half of the balloon loop from leg {'BC'[half - 1]}"
    return note


def track_half_rows(st: MapBuild, t: Track, sws: list[str], half: int | None, split: bool) -> None:
    """The block row and occupancy row of track `t` (or of its `half`): its detector the owner's pin, none off the
    main line, not wired yet for a second half, else the next free block input (track_detector). MapError on a pin
    the rule gives no detector."""
    ends_cp = sorted({st.cp_of[v] for v in sws if v in st.cp_of}, key=railroad.natural)
    name, role, level = loop_placeholder(t["name"], half), line_role(t, half), t["level"]
    cp = line_cp(name, level, t, st.places, helix_ends(st.helix))
    add(st, level, cp, "block", name, comment=" / ".join(ends_cp), trial=trial_of(st, name),
        notes=track_note(t, half, split), role=role, ident=track_id(st, name))
    pinned = st.nodes.take_pinned(name)
    if not (t["main"] and sws):
        if pinned:
            raise MapError(f"{PINS.name} pins a detector for {name}, which the rule gives none (off the main line)")
        occupancy(st, level, cp, name, notes=NO_DETECTOR, role=role)
    elif pinned:                                          # the owner's input (wiring.csv)
        detected(st, level, cp, name, pinned, role=role)
    elif half and half > 1:                               # wired later: no node or input yet
        occupancy(st, level, cp, name, notes=NOT_WIRED, role=role)
    else:
        detected(st, level, cp, name, track_detector(st, level, sws), role=role)


def track_detector(st: MapBuild, level: int, sws: list[str]) -> DetectorInput:
    """The next free block input for a track of `level` between the switches `sws` (sorted in place, those of the
    track's own level first): on a node of its first switch's area, its own level's turnout nodes first."""
    sws.sort(key=lambda s: st.area_of[s][0] != level)
    area = st.area_of[sws[0]][1]
    node = st.nodes.pick(level, area, "block", prefer=[st.home[s] for s in sws if st.area_of[s][0] == level])
    k, packed = st.nodes.take(node, "block")
    return DetectorInput(node, k, packed)


def check_frozen_cps(rows: Iterable[DeviceMapRow], cps: frozenset[str], held_devices: set[tuple[str, str]],
                     held_blocks: set[str]) -> None:
    """A control point wiring.csv holds (frozen) is read from it and proposed for no more: stop on a device the rule
    gave one of its rows (a turnout, feedback or head on a node, or a detector input) that wiring.csv does not
    hold. A switch added to a frozen control point is wired and frozen again (make wiring-freeze)."""
    bad = []
    for r in rows:
        if devices.place(cells(r)).split(devices.LIST)[0] not in cps or not r["node"] or r["role"] == "lcc_alias":
            continue
        if r["layer"] in ("turnout", "fb", "head") and (r["layer"], r["user_name"]) not in held_devices:
            bad.append(f"{r['layer']} {r['user_name']}")
        elif r["layer"] == "occupancy" and r["system_name"] and r["blocks"] not in held_blocks:
            bad.append(f"occupancy of {r['blocks']}")
    if bad:
        raise MapError(f"{PINS.name}: control point(s) {', '.join(sorted(cps))} are frozen, but the rule proposes "
                       f"{', '.join(sorted(bad))} for them: wire and freeze again (make wiring-freeze CP=...)")


def assign_ports(rows: Iterable[DeviceMapRow]) -> None:
    """Board and pins for turnout and feedback rows, as docs/wiring/README.md lays boards out: turnouts two pins
    each on 12V DNOU8 boards from OU1; feedback N then R on DNIN8 boards from IN1. Heads get theirs when placed
    (Nodes.place_mast: 5V boards after the 12V ones, R Y G on three consecutive pins, a mast's heads on one board,
    pin 8 of the first 5V board kept for detector calibration). Comments become ADR-005's
    "Node: n Turnout: k | OU: b Ports: p,q" (LCC aliases the same); occupancy keeps "Node: n Block: k"."""
    for r in rows:
        m = PIN_RE.match(r["comment"])
        if not m:
            continue
        kind, k = m.group(2), int(m.group(3))
        if kind == "Turnout":
            r["comment"] += f" | OU: {k // 4 + 1} Ports: {2 * (k % 4) + 1},{2 * (k % 4) + 2}"
        elif kind == "Sensor":
            r["comment"] += f" | IN: {k // 8 + 1} Ports: {k % 8 + 1}"
