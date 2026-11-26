"""Staging's rows of the device master (build_device_map.py): its block layer, its block, occupancy and part rows
(staging_rows) and its wired turnout, LCC alias and feedback rows (staging_wired_rows). The trial keys every level's
line blocks carry (piece_trials, level_trials), the cp of a line block (line_cp) and a part's row (part_row) are here
too: the main and upper build uses them.

Staging is generated like main and upper: its devices are the plan's (its blocks from the
block layer, its switches from the plan graph, staging_switches), each row made by the same makers
(device_map_rows: device_row, switch_device_rows), then the owner's values put over it by the device's ID
(device_map_rows.owner_over; devices_field.csv is keyed by it: a user name there is the
owner's). A staging device with no field row keeps the generated values: a block is numbered as a part is
(part_bean_names), a turnout is bound to its address. This script owns which devices there are and what each holds
(trial_name in staging's switch-and-leg keys, part_of, blocks, description). A staging block change made in PanelPro
is carried by hand into this script's data (block_overrides.csv, plan_overrides.json). A staging detector's wiring
(node and input, so its sensor and wiring) is its level 1 row of wiring.csv (hartlib.wiring, the physical wiring
source), as are its turnouts' and feedback's (staging_wired_rows) and main and upper's pinned
detectors: staging's nodes are as built, so the builder proposes none and a staging device with no wiring row stops.
Any other field fact of a staging device (a block system name, its comment, a DCC address) is the owner's, in its row
of devices_field.csv (ADR-029 amendment), which this script reads and never writes: it writes
devices_generated.csv, and never reads its own last rows back but for the numbers it gave (devices.allocated_names).

The drawing's tracks come from device_map_schematic; the builder's paths (OVERRIDES, OUT through device_files) are read
from build_device_map when a function runs (device_map_schematic.builder), as they are then: that module imports this
one, so this one does not import it at load.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import block_layer  # noqa: E402  the one block process for every level
import mast_rule  # noqa: E402  read_block_splits, OVERRIDES_NAME
from mast_rule import MapError, band_levels  # noqa: E402
from device_map_inputs import (  # noqa: E402  the readers
    CPS, NODES, PINS, STAGING_NAMES, STATIONS, WIRING, Places, StagingPin, helix_pins, read_places, read_staging_pins,
    staging_nodes, wiring_rows)
from device_map_rows import Wired, device_row, owner_over, switch_device_rows  # noqa: E402  every level's row makers
from device_map_schematic import (  # noqa: E402
    block_overrides, builder, helix_tracks, home_and_posts, line_role, named_tracks)
from hartlib import device_ids, devices, layer_files, level_devices, railroad, track_names  # noqa: E402

natural = railroad.natural
occupancy_user = level_devices.occupancy_user


STAGING_SHEET = "staging"           # staging's section of plan_overrides.json
STAGING = int(railroad.STAGING_LEVEL)   # staging's level, as wiring.csv and interlockings.csv number it
STAGING_LEVEL = railroad.STAGING_LEVEL  # and as the device master does
WRITER = "build_device_map.py"
FIELD_LAYERS = ("block", "occupancy")
# One row of the device master, keyed by hartlib.devices.COLUMNS. A plain dict, not a TypedDict: hartlib's row
# functions (devices.master_row, describe, merge) take Mapping[str, str], which a TypedDict does not satisfy.
MasterRow = dict[str, str]


def part_row(level: str, name: str, part: dict, trial: str, device_id: str = "") -> dict:
    """The master row of a part (block_layer.Layer.parts): a piece of track inside another block, part_of naming it,
    with no occupancy row or detector of its own (hartlib.devices: role part). It is a JMRI block of its own on every
    level, its sensor its OS block's: main and upper's the Layout Editor build makes (assignment
    none here); staging_rows gives staging's their bean names (part_bean_names, assignment virtual). `device_id`: its
    block ID from the plan ends its trial name has (staging_keys, level_keys)."""
    t = part["track"]
    row = {c: "" for c in devices.COLUMNS}
    row.update(level=level, layer="block", role="part", id=device_id, user_name=name, assignment="none",
               trial_name=trial,
               notes=f"a piece of the {t['cm']} cm track from Switch "
                     f"{' to Switch '.join(sorted({v for k, v in t['ends'] if k == 'sw'}, key=natural))}, part of "
                     f"{part['part_of']} ({part['why']})",
               part_of=part["part_of"], written_by="build_device_map.py")
    row["description"] = devices.describe(row)
    return row


PART_BLOCK_FIRST = 52        # a new staging part's number: the first above staging's last JMRI block (IB:AUTO:0051)


def part_bean_names(parts: list[str], prior: dict, taken: set) -> dict[str, tuple[str, str]]:
    """{part: (jmri_name, layout_block)} of staging's parts, each a JMRI block of its own on its block's occupancy sensor:
    the names its row has (`prior`: {part: (jmri_name, layout_block)}), else, in name order, the next number n from
    PART_BLOCK_FIRST up with neither IB:AUTO:<nnnn> nor ILB<n> in `taken` (every other bean's names), so a name never
    shifts. MapError on a row with one of the two names only, or a name another bean has."""
    out, bad, used = {}, [], set(taken)
    for p in sorted(parts, key=natural):
        if p not in prior:
            continue
        jn, lb = prior[p]
        if bool(jn) != bool(lb):
            bad.append(f"{p}: its row has a jmri_name or a layout_block, not both")
        elif jn:
            clash = [x for x in (jn, lb) if x in used]
            if clash:
                bad.append(f"{p}: its row has {'jmri_name' if clash[0] == jn else 'layout_block'} {clash[0]}, which "
                           "another bean has")
            out[p] = (jn, lb)
            used |= {jn, lb}
    if bad:
        raise MapError("; ".join(bad))
    n = PART_BLOCK_FIRST
    for p in sorted(parts, key=natural):
        if p in out:
            continue
        while f"IB:AUTO:{n:04d}" in used or f"ILB{n}" in used:
            n += 1
        out[p] = (f"IB:AUTO:{n:04d}", f"ILB{n}")
        used |= set(out[p])
    return out


BEAN_NAME = re.compile(r"\bIB:AUTO:\d{4}\b|\bILB\d+\b")


def taken_bean_names(master: list[dict]) -> set:
    """Every name a bean has but the ones this script numbers (staging's generated block rows: its parts', and a
    block's with no field row): the master's other rows (system_name, jmri_name, layout_block; a field row's are the
    owner's), and the template's and the parked snapshot's block and layout block names
    (hartlib.tables_build.TEMPLATE, hartlib.parked.PARKED_XML), so a new number is free everywhere."""
    from hartlib import parked, tables_build
    out = {r[c] for r in master
           if not (r["level"] == STAGING_LEVEL and r["layer"] == "block" and r["written_by"] == WRITER)
           for c in ("system_name", "jmri_name", "layout_block") if r[c]}
    for path in (tables_build.TEMPLATE, parked.PARKED_XML):
        out |= set(BEAN_NAME.findall(path.read_text(encoding="utf-8")))
    return out


def staging_layer(bands, joined, runs, exceptions: Path | None = None) -> tuple[block_layer.Layer, int, list[dict]]:
    """(block_layer.layer of the staging band, its band index, its tracks): the one block process over staging's
    drawing and block_overrides.csv (`exceptions`, default block_overrides()), every kind of its rows from that one
    file."""
    bdm = builder()
    exceptions = exceptions or block_overrides()
    overrides = layer_files.read("plan_overrides", STAGING_SHEET, bdm.OVERRIDES.parent)
    levels = band_levels(overrides)
    found = named_tracks(bands, joined, runs, overrides)
    try:
        cp_of = {s: r.name for r in railroad.read_interlockings(CPS, (1,)) for s in r.switches}
    except railroad.FactsError as exc:
        raise MapError(str(exc)) from exc
    _home, posts = home_and_posts(bands, joined, found, levels, cp_of, None,
                                  mast_rule.read_block_splits(exceptions, found, levels))
    split = block_layer.split_edges(found, levels, exceptions, bdm.OVERRIDES.parent)
    lay = block_layer.layer(bands, runs, found, levels, split,
                            block_layer.read_exceptions(found, bands, levels, exceptions), posts=posts,
                            data=bdm.OVERRIDES.parent)
    if len(lay.bands) != 1:
        raise MapError(f"staging is drawn on {len(lay.bands)} bands; its trial names need one")
    return lay, next(iter(lay.bands)), found


def staging_trials(band, lay: block_layer.Layer, bi: int) -> dict[str, str]:
    """{row name: trial_name} of staging's block rows in its drawing's keys (staging_device_map.placeholders: switch
    numbers and legs, which survive a new export): a row's OS placeholders, then its track pieces in strand order,
    each "Track <piece>" or, for the k-th of a piece's n rows from the piece's first end, "Track <piece> k/n"."""
    return staging_keys(band, lay, bi)[0]


def staging_keys(band, lay: block_layer.Layer, bi: int) -> tuple[dict[str, str], dict[str, str]]:
    """({row name: trial_name} (staging_trials), {row name: device ID}) of staging's block rows, both from the same
    plan ends (hartlib.device_ids): an OS block's ID is its switch's (staging_device_map.os_keys: os:<n>, or
    os:<n>:A-<end> of a crossover half), even when a piece of track lies inside it; any other row's is block: and
    its pieces' keys, in key order. MapError on a row that two switches' OS blocks share."""
    import staging_device_map as sdm        # its placeholder grammar (it imports this module)
    _turnouts, _os_ph, refs = sdm.placeholders(band)
    got, ids, bad = defaultdict(list), {}, []
    for n, (ph, oid) in sdm.os_keys(band).items():
        row = lay.bands[bi]["os"][n]
        got[row].append(ph)
        if ids.setdefault(row, oid) != oid:
            bad.append(f"{row} is the OS block of {ids[row]} and {oid}")
    for row, keys in piece_keys({bi: lay.rows[bi]}, {bi: refs}, {bi: set()}).items():
        got[row] += [ph for ph, _k in keys]
        ids.setdefault(row, device_ids.block_id(k for _ph, k in keys))
    if bad:
        raise MapError("staging OS blocks: " + "; ".join(bad))
    return {row: ", ".join(phs) for row, phs in got.items()}, ids


def piece_trials(rows: dict, refs: dict, inside: dict) -> dict[str, list[str]]:
    """{row name: its track placeholders, in key order} of the layer rows of some bands (`rows`: {band index: {strand:
    [row, ...] from the strand's first end]}, block_layer.Layer.rows), each strand keyed by `refs` ({band index:
    staging_device_map.piece_refs or band_refs}): "Track <piece>", or "Track <piece> k/n" for the k-th of its n rows
    from the piece's first end (staging_device_map.strand_placeholders, the rule every reader keys by). A strand whose
    rows are all in `inside` ({band index: OS blocks}) is inside a crossover and keyed by its OS block's own
    placeholder, not here. One grammar for every level; a key drawn on two bands (a track cut by a
    connector) is listed once. MapError on a strand with rows but no key."""
    return {row: [ph for ph, _k in keys] for row, keys in piece_keys(rows, refs, inside).items()}


def piece_keys(rows: dict, refs: dict, inside: dict) -> dict[str, list[tuple[str, str]]]:
    """{row name: [(track placeholder, device-ID part)], in placeholder key order}: piece_trials' placeholders, each
    with the ID part of the same piece, k and n (staging_device_map.strand_ids, hartlib.device_ids.strand_key)."""
    import staging_device_map as sdm        # its placeholder grammar (it imports this module)
    got = defaultdict(dict)
    for bi, band_rows in rows.items():
        for sid, names in band_rows.items():
            if set(names) <= inside[bi]:
                continue
            if sid not in refs[bi]:
                raise MapError(f"strand {sid} of band {bi} has blocks {names} but no piece key "
                               "(staging_device_map.piece_refs)")
            ref = refs[bi][sid]
            for row, key, part in zip(names, sdm.strand_placeholders(ref, len(names)),
                                      sdm.strand_ids(ref, len(names))):
                got[row][key] = part
    return {row: sorted(phs.items(), key=lambda kv: natural(kv[0])) for row, phs in got.items()}


def level_trials(bands, joined, lay: block_layer.Layer) -> dict[str, str]:
    """{row name: trial_name} of the main and upper track, half and part rows of `lay` (main_upper_layer), in the
    switch-and-leg keys staging's rows have (piece_trials over staging_device_map.band_refs), which survive a new
    export. A strand inside a crossover is its OS block's ("OS Switch <n>", written by os_rows)."""
    return level_keys(bands, joined, lay)[0]


def level_keys(bands, joined, lay: block_layer.Layer) -> tuple[dict[str, str], dict[str, str]]:
    """({row name: trial_name} (level_trials), {row name: device ID}) of the main and upper track, half and part rows
    of `lay`, both from the same plan ends: the ID is block: and the row's pieces' keys (hartlib.device_ids)."""
    import staging_device_map as sdm        # its placeholder grammar (it imports this module)
    try:
        refs = {bi: sdm.band_refs(bands, joined, bi) for bi in lay.rows}
    except sdm.StagingMapError as exc:
        raise MapError(str(exc)) from exc
    inside = {bi: set(b["os"].values()) for bi, b in lay.bands.items()}
    keys = piece_keys(lay.rows, refs, inside)
    return ({row: ", ".join(ph for ph, _k in ks) for row, ks in keys.items()},
            {row: device_ids.block_id(k for _ph, k in ks) for row, ks in keys.items()})


def helix_ends(helix: dict) -> dict[str, set[str]]:
    """{helix block: its two end switches, staging's and the main or upper one's number} (`helix`:
    read_helix_tracks): a helix block is one block across the levels, so each level's row of it has both ends."""
    return {h["block"]: {h["staging_switch"], re.match(r"\d+", h["level_switch"]).group(0)} for h in helix.values()}


def line_cp(block: str, level, track: dict, places: Places, helix_ends: dict | None = None) -> str:
    """The cp of the level `level` row of a line block (devices.LINE_ROLES) on `track` (a mast_rule track: its
    `ends`; a helix block's ends from `helix_ends` too, which its drawing on one level does not reach): the places of
    the switches at its two ends and the stations whose `tracks` name it, each once, joined by railroad.DEVICE_LIST
    (a block in none: empty). The row's own level's places come first, then the nearer levels' (a helix block's main
    and upper rows read "CP 127;Princess", its staging row "Princess;CP 127"), each level's in Places.order: a reader
    that wants one place takes the first."""
    sws = {v for k, v in track["ends"] if k == "sw"} | (helix_ends or {}).get(block, set())
    got = {p for v in sws for p in places.of.get(v, ())} | set(places.tracks.get(block, ()))
    return railroad.DEVICE_LIST.join(sorted(got, key=lambda p: (abs(places.level[p] - int(level)), places.order[p])))


WIRED_LAYERS = {"turnout": "turnout", "fb": "fb"}      # master layer -> wiring.csv kind of staging's wired rows


def field_row(f: Mapping[str, str]) -> dict:
    """A full master row of a staging device from its field row (devices_field.csv): its key and the owner's cells,
    every other cell empty for this script to fill."""
    return {c: f[c] for c in devices.COLUMNS}


def staging_field(files: devices.Files | None = None, layers=FIELD_LAYERS) -> dict:
    """{(layer, device ID): full row} of the field file's staging rows of `layers` (field_row): the devices the owner
    says staging has, this script's input for them, keyed as the field file is (hartlib.devices.KEY), so a row keeps
    its owner's user name when the generated name changes. Read from devices_field.csv alone, never from this
    script's last output."""
    bdm = builder()
    return {(f["layer"], f["id"]): field_row(f) for f in devices.field_index(files or bdm.device_files()).values()
            if f["level"] == STAGING_LEVEL and f["layer"] in layers}


def alias_note(turnout: str, address: str) -> str:
    """The note of an LCC alias row: the turnout it stands for and that turnout's LCOS address. MapError when the
    turnout has no address (no wiring.csv row)."""
    if not address:
        raise MapError(f"LCC alias DCC {turnout}: {turnout} has no turnout row in {WIRING.name}")
    return f"LCC alias of {turnout} ({address})"


def staging_switches(data: Path | None = None) -> dict[str, list[str]]:
    """{switch number: its plan labels} of staging's switches, from the plan (hartlib.track_names.plan_switches over
    the staging plan graph in `data`, default the builder's schematic folder), not from the owner's rows: the
    switches staging_wired_rows makes rows for."""
    folder = data or builder().OVERRIDES.parent
    try:
        return track_names.plan_switches(STAGING_SHEET, layer_files.read("plan_overrides", STAGING_SHEET, folder),
                                         folder)
    except track_names.TrackNameError as exc:
        raise MapError(str(exc)) from exc


def staging_cps() -> dict[str, str]:
    """{switch number: its control point} of staging's interlockings (interlockings.csv level 1): a staging device's
    generated cp; the owner's cp (its field row) goes over it."""
    try:
        return {str(s): r.name for r in railroad.read_interlockings(CPS, (STAGING,)) for s in r.switches}
    except railroad.FactsError as exc:
        raise MapError(str(exc)) from exc


def staging_wired_rows(files: devices.Files | None = None, path: Path | None = None,
                       nodes: set | None = None, switches: dict[str, list[str]] | None = None) -> list[dict]:
    """Staging's turnout, LCC alias and feedback rows of the master, generated as main and upper's are
    (device_map_rows.switch_device_rows) for each switch of the plan (`switches`: {number: plan labels}, default
    staging_switches()), wired as wiring.csv has them (`path`, default the committed file: node, wiring text and
    address; staging's devices are bound to their address, an alias to MTT<dcc>), with the owner's values over them
    (device_map_rows.owner_over: the field row of the device's id in devices_field.csv, if it has one: its user name,
    role, assignment, cp, dcc and the rest). The alias takes the owner's DCC address (the turnout's or its own field
    row's); a switch with none has no alias row. An alias's note names its turnout as readers see it and its address
    (alias_note). `nodes`: staging's (default staging_nodes()). MapError on a switch with no turnout or feedback row
    in wiring.csv (staging's nodes are as built: the builder proposes none), a wiring or field row whose id names no
    switch of the plan, a node that is not staging's, or a turnout the panels bind by its old user name (Q13)."""
    bdm = builder()
    nodes = staging_nodes() if nodes is None else nodes
    field = bdm.device_files() if files is None else files
    switches = staging_switches() if switches is None else switches
    by = {(w.kind, w.id): w for w in wiring_rows(path, STAGING_NAMES, field)
          if w.level == STAGING and w.kind in ("turnout", "fb")}
    bad = [f"{WIRING.name} line {w.line}: {w.kind} {w.device} is on node {w.node}, no staging node of {NODES.name} "
           f"({', '.join(map(str, sorted(nodes)))})" for w in by.values() if w.node not in nodes]
    owner = staging_field(field, tuple(WIRED_LAYERS))
    cp_of = staging_cps()
    out, seen = [], set()
    for s, labels in switches.items():
        tid, aid = device_ids.switch_id(s), device_ids.dcc_id(s)
        f_turnout, f_alias = owner.pop(("turnout", tid), None), owner.pop(("turnout", aid), None)
        f_fb = {nr: owner.pop(("fb", device_ids.fb_id(s, nr)), None) for nr in "NR"}
        wires = {("turnout", tid): by.get(("turnout", tid))} | {
            ("fb", device_ids.fb_id(s, nr)): by.get(("fb", device_ids.fb_id(s, nr))) for nr in "NR"}
        lost = [(kind, did) for (kind, did), w in wires.items() if w is None]
        for kind, did in lost:
            f = f_turnout if kind == "turnout" else f_fb[did[-1]]
            name = (f or {}).get("user_name") or (f"Switch {s}" if kind == "turnout" else f"FB Switch {s} {did[-1]}")
            bad.append(f"staging {kind} {name}: no {kind} row for {did} in {WIRING.name}")
        if lost:
            continue
        seen |= set(wires)
        w = wires[("turnout", tid)]
        dcc = (f_turnout or {}).get("dcc") or (f_alias or {}).get("dcc") or ""
        if f_alias is not None and not dcc:
            bad.append(f"{devices.FIELD_FILE}: staging turnout {f_alias['user_name'] or 'DCC Switch ' + s} (id {aid}): "
                       f"an LCC alias needs a DCC address, and neither its row nor {tid}'s gives one: give dcc, or "
                       "remove the alias row")
            continue
        made = switch_device_rows(
            STAGING_LEVEL, cp_of.get(s, ""), s, labels, Wired(w.address, w.node, w.wiring_text),
            {nr: Wired(wires[("fb", device_ids.fb_id(s, nr))].address, wires[("fb", device_ids.fb_id(s, nr))].node,
                       wires[("fb", device_ids.fb_id(s, nr))].wiring_text) for nr in "NR"},
            dcc, jmri=w.address, alias_notes="", alias=bool(dcc) or f_alias is not None)
        # the master's form (devices.master_row); the DCC address is put back after, as a field turnout's wiring
        # text holds none (a JMRI comment's "DCC: n" group is the dcc column's)
        rows = {r["id"]: dict(devices.master_row(dict(r, dcc=""), WRITER), dcc=str(r["dcc"])) for r in made}
        turnout = owner_over(rows[tid], f_turnout)
        fbs = [owner_over(rows[device_ids.fb_id(s, nr)], f_fb[nr]) for nr in "NR"]
        unbound = [(r, wires[(r["layer"], r["id"])].address) for r in [turnout] + fbs
                   if r["jmri_name"] not in (wires[(r["layer"], r["id"])].address, r["user_name"])]
        for r, address in unbound:
            # a device the panels bind by its user name (Q13): a rename moves the binding, so the owner changes
            # both cells together; the build does not rewrite the binding
            bad.append(f"{devices.FIELD_FILE}: staging {r['layer']} {r['user_name']} (id {r['id']}): its jmri_name "
                       f"{r['jmri_name']!r} binds it by its old user name; change jmri_name and user_name "
                       f"together, or clear jmri_name to bind it by its address {address}")
        if unbound:
            continue
        got = [turnout]
        if aid in rows:
            alias = dict(rows[aid], notes=alias_note(turnout["user_name"], w.address))
            got.append(owner_over(alias, f_alias))
        got += fbs
        for r in got:
            r["description"] = devices.describe(r)
        out += got
    bad += [f"{WIRING.name} line {w.line}: staging {kind} {did} names no switch of the plan"
            for (kind, did), w in sorted(by.items()) if (kind, did) not in seen and
            did.split(":")[1] not in switches]
    bad += [f"{devices.FIELD_FILE}: staging {layer} {r['user_name'] or '(no name)'} (id {did}): the plan has no such "
            "device (move the row's cells to the device's id, or remove the row)"
            for (layer, did), r in sorted(owner.items())]
    if bad:
        raise MapError("; ".join(bad))
    return sorted(out, key=lambda r: (devices.LAYERS.index(r["layer"]), natural(r["user_name"])))


def wire_occupancy(row: dict, pin: StagingPin) -> dict:
    """`row` (a staging occupancy row) with its wiring cells from its pin: node, sensor and wiring."""
    return dict(row, node=str(pin.node), system_name=pin.sensor, jmri_name=pin.sensor, wiring=pin.wiring)


def new_spare(pin: StagingPin) -> dict:
    """The row of a spare input (a wiring.csv detector with no block, or one whose block is now a part): named by its
    input, detector none. wiring.csv makes it; it has no field row."""
    row = {c: "" for c in devices.COLUMNS}
    row.update(level=STAGING_LEVEL, layer="occupancy", role="spare", user_name=f"unused {pin.input}",
               assignment="spare", detector="none", written_by="build_device_map.py")
    row = wire_occupancy(row, pin)
    row["id"] = device_ids.spare_id(row["system_name"])
    row["description"] = devices.describe(row)
    return row


def wire_block(row: dict, node: int, k: int) -> dict:
    """`row` (a staging block row) with its detector's node, and its comment: the field file's words with the
    detector's "occupancy Block <n>-<k> / M2S<id>" put where devices.OCCUPANCY_MARK stands. MapError when the field
    comment has no mark to fill."""
    pin = StagingPin(0, row["user_name"], node, k)
    if devices.OCCUPANCY_MARK not in row["jmri_comment"]:
        raise MapError(f"{devices.FIELD_FILE}: staging block {row['user_name']}: its jmri_comment "
                       f"{row['jmri_comment']!r} has no {devices.OCCUPANCY_MARK} for its detector's "
                       f"\"occupancy {pin.input} / {pin.sensor}\" ({PINS.name})")
    return dict(row, node=str(node), jmri_comment=devices.fill_occupancy(row["jmri_comment"],
                                                                         f"occupancy {pin.input} / {pin.sensor}"))


def staging_part_names(files: devices.Files | None = None) -> tuple[dict, set]:
    """({block: (jmri_name, layout_block)} of staging's block rows as this script last numbered them (its parts, and
    a block with no field row), every other bean's names): the name memory part_bean_names keeps its numbers by
    (devices.allocated_names, the one read-back of this script's own output; a block the owner names has no number
    there), and every name taken (taken_bean_names) so a new number is free."""
    bdm = builder()
    f = files or bdm.device_files()
    mine = {r["id"]: (r["jmri_name"], r["layout_block"])
            for r in devices.allocated_names((STAGING_LEVEL,), "block", None, f).values()
            if r["jmri_name"] and r["layout_block"]}
    # both files as written, not their merge: a field row the owner just removed leaves a generated row that no
    # longer merges, and this build is what writes it again
    return mine, taken_bean_names(list(devices.generated_rows(f)) + list(devices.field_rows(f)))


class StagingBlocks(NamedTuple):
    """Staging's drawn blocks and what staging_rows' steps read of them. `prior` (the owner's field rows not yet
    used) and `bad` (the problems found) are filled in place by the steps, in order, so the error text keeps one
    order."""
    lay: block_layer.Layer
    bi: int                             # the staging band's index
    trials: dict[str, str]              # {row name: trial_name} (staging_keys)
    ids: dict[str, str]                 # {row name: device ID} (staging_keys)
    blocks: set[str]                    # the OS blocks and track blocks (not the parts)
    helix_rows: dict[str, Any]          # helix_tracks()
    helix: set[str]                     # the helix blocks
    prior: dict[tuple[str, str], MasterRow]     # staging_field: {(layer, device ID): field row}
    bad: list[str]


def staging_rows(bands: Any, joined: Any, runs: Any, files: devices.Files | None = None,
                 exceptions: Path | None = None, pins: Path | None = None,
                 places: Places | None = None, part_names: tuple[dict[str, tuple[str, str]], set[str]] | None = None,
                 drawn: dict[str, str] | None = None) -> list[MasterRow]:
    """Staging's block and occupancy rows of the master: the one block process's blocks and parts of the staging
    band (staging_layer), each block row and its occupancy row generated (device_map_rows.device_row: its role from
    its id or its track's ends, an OS block's cp its interlocking's, a comment marking its detector, a detector's
    notes and detector cells) with the owner's field row of its device ID over it (owner_over; devices_field.csv,
    staging_field: the system and layout-block names, comment, notes, detector, stop, dcc and an OS block's control
    point); a block with no field row is numbered as a part is (assignment virtual, part_bean_names). A line block's
    cp, and its sensor's, is line_cp's (the places it joins, `places`: read_places by default), never the owner's;
    this script owns the rest (trial_name, part_of, blocks, written_by, description). The wiring is wiring.csv's
    (level 1 detectors, read_staging_pins; a helix block's, its main or upper row): an occupancy row's node, sensor
    and wiring, a block row's node and the occupancy text in its comment (wire_block), and the spare inputs (no block,
    or a block that is now a part), each row "unused Block <n>-<k>" (new_spare); `pins` (default the committed file).
    A helix block's occupancy row is the level of its helix switch's (main or upper), not staging's: the block is one
    across levels. A part's beans keep the numbers this script gave them (`part_names`, default staging_part_names),
    and so does a block whose field row gives no bean names. `drawn`, when given, gets {block id: generated name}.
    MapError on a field row the drawing has no block for, a block that is now
    a part while its field rows stand (the owner's cells would be lost: remove them), a detector block with no pin, or
    a pin whose block staging does not
    have or is a helix block."""
    bdm = builder()
    f = files or bdm.device_files()
    s = _staging_blocks(bands, joined, runs, f, exceptions)
    # staging's parts, and a block the owner has no field row for, carry their block names here, where main and
    # upper's take theirs from block_numbering.csv (build_device_map.block_beans)
    beans = _bean_names(s, _unnamed_blocks(s), staging_part_names(f) if part_names is None else part_names)
    cp_of = staging_cps()
    staging_pins = read_staging_pins(pins, files=f)
    # a pin finds its block by the block's device ID (wiring.csv keys it so): the drawn name of
    # an OS block is the rule's, its row's name may be the owner's
    pin_of = {p.id: p for p in staging_pins if p.id}
    on_helix = helix_pins(pins, layer_files.read("plan_overrides", "main_upper", bdm.OVERRIDES.parent).get("helix", {}))
    _check_pins(s, staging_pins)
    named = _block_and_part_rows(s, beans, cp_of, pin_of, on_helix, drawn)
    out = list(named.values())
    _part_comments(s, named)
    _line_cps(s, named, read_places() if places is None else places)
    occupancy = _occupancy_rows(s, named, beans, pin_of)
    spares = _spare_rows(s, staging_pins)
    if s.prior:
        s.bad.append(f"staging rows of {devices.FIELD_FILE} the drawing has no block for: "
                     + ", ".join(f"{layer} {r['user_name'] or '(no name)'} (id {did})"
                                 for (layer, did), r in sorted(s.prior.items())))
    if s.bad:
        raise MapError("; ".join(s.bad))
    out += sorted(occupancy + spares, key=lambda r: natural(r["user_name"]))
    return out


def _staging_blocks(bands: Any, joined: Any, runs: Any, files: devices.Files,
                    exceptions: Path | None) -> StagingBlocks:
    """The staging band's block layer (staging_layer), its rows' trial names and device IDs, the helix blocks and the
    owner's staging field rows."""
    lay, bi, _found = staging_layer(bands, joined, runs, exceptions)
    trials, ids = staging_keys(bands[bi][1], lay, bi)
    helix_rows = helix_tracks()
    return StagingBlocks(lay, bi, trials, ids, set(lay.bands[bi]["os"].values()) | set(lay.tracks), helix_rows,
                         {h["block"] for h in helix_rows.values()}, staging_field(files), [])


def _unnamed_blocks(s: StagingBlocks) -> list[str]:
    """The blocks this script numbers because the owner gives them no bean names: no field row, or one with neither
    jmri_name nor layout_block. A row with one of the two is a problem (the other would not match it), put in
    s.bad."""
    unnamed = []
    for n in sorted(s.blocks, key=natural):
        fr = s.prior.get(("block", s.ids.get(n, "")))
        if n not in s.ids or (fr is not None and fr["jmri_name"] and fr["layout_block"]):
            continue
        if fr is not None and (fr["jmri_name"] or fr["layout_block"]):
            s.bad.append(f"{devices.FIELD_FILE}: staging block {fr['user_name'] or n} (id {s.ids[n]}): it gives "
                         f"{'jmri_name' if fr['jmri_name'] else 'layout_block'} but not "
                         f"{'layout_block' if fr['jmri_name'] else 'jmri_name'}; give both, or neither for the "
                         "builder's numbers")
            continue
        unnamed.append(n)
    return unnamed


def _bean_names(s: StagingBlocks, unnamed: list[str],
                part_names: tuple[dict[str, tuple[str, str]], set[str]]) -> dict[str, tuple[str, str]]:
    """{part or unnamed block: (jmri_name, layout_block)} (part_bean_names). The memory is by device ID
    (staging_part_names), so a block the owner renames keeps its numbers. MapError naming staging's parts."""
    mine, taken = part_names
    numbered = list(s.lay.parts) + unnamed
    try:
        return part_bean_names(numbered, {n: mine[s.ids[n]] for n in numbered if s.ids.get(n) in mine}, taken)
    except MapError as exc:
        raise MapError(f"staging parts: {exc}") from exc


def _check_pins(s: StagingBlocks, staging_pins: Iterable[StagingPin]) -> None:
    """A pin on a helix block (its detector is its main or upper row's), or on a block staging does not draw, is a
    problem, put in s.bad. Pins match by device ID: a pin's name may be the owner's."""
    helix_ids = {s.ids[n] for n in s.helix if n in s.ids}
    drawn_ids = {s.ids[n] for n in s.blocks | set(s.lay.parts) if n in s.ids}
    for p in staging_pins:
        if p.id in helix_ids:
            s.bad.append(f"{PINS.name} line {p.line}: {p.block} is a helix block; its detector is its main or upper "
                         "row's")
        elif p.id and p.id not in drawn_ids:
            s.bad.append(f"{PINS.name} line {p.line}: staging has no block {p.block} ({p.id})")


def _owned(s: StagingBlocks, beans: Mapping[str, tuple[str, str]], generated: Mapping[str, str]) -> MasterRow:
    """The master row of a staging device from its generated row (device_map_rows.device_row form), with the
    owner's values over it (device_map_rows.owner_over: the field row of its id, if any, hartlib.devices.KEY, taken
    out of s.prior). A block numbered here (`beans`) is virtual on those names, as a part is (part_bean_names)."""
    row = devices.master_row(generated, WRITER)
    field = s.prior.pop((row["layer"], row["id"]), None)
    if row["layer"] == "block" and row["user_name"] in beans:
        row.update(assignment="virtual", jmri_name=beans[row["user_name"]][0],
                   layout_block=beans[row["user_name"]][1])
    row = owner_over(row, field)
    row["description"] = devices.describe(row)
    return row


def _block_role(lay: block_layer.Layer, name: str, did: str) -> str:
    """A staging block's generated role: an OS block's by its id (a crossover half's corner), a line block's from
    its track's ends (device_map_schematic.line_role), "track" where the ends give none. The owner's role goes over
    it."""
    if did.startswith("os:"):
        return "xover_corner" if ":A-" in did else "os"
    track, half = lay.tracks[name]
    try:
        return line_role(track, half)
    except MapError:
        return "track"


def _drop(prior: dict[tuple[str, str], MasterRow], layer: str, name: str, did: str = "") -> list[str]:
    """Take the field rows of `layer` with the id `did` (when known) or named `name` out of `prior` (a field row's
    user name may be empty: the generated name stands); `name` once per row taken."""
    keys = [k for k, r in prior.items() if k[0] == layer and ((did and k[1] == did) or r["user_name"] == name)]
    for k in keys:
        prior.pop(k)
    return [name for _k in keys]


def _block_and_part_rows(s: StagingBlocks, beans: Mapping[str, tuple[str, str]], cp_of: Mapping[str, str],
                         pin_of: Mapping[str, StagingPin], on_helix: Mapping[str, tuple[int, int]],
                         drawn: dict[str, str] | None) -> dict[str, MasterRow]:
    """{drawn name: row} of staging's blocks and parts, in name order; a row may hold the owner's name. `drawn`, when
    given, gets {block id: generated name}."""
    named: dict[str, MasterRow] = {}
    for name in sorted(s.blocks | set(s.lay.parts), key=natural):
        if name in s.lay.parts:
            named[name] = _part_block_row(s, beans, name)
            continue
        if name not in s.ids:
            s.bad.append(f"staging block {name}: the plan gives it no ends, so no device ID")
            _drop(s.prior, "block", name)                       # one error for it, not a second "no block" one
            _drop(s.prior, "occupancy", occupancy_user(name))
            continue
        did = s.ids[name]
        named[name] = _block_row(s, beans, name, did, cp_of, pin_of, on_helix)
        if drawn is not None:
            drawn[did] = name           # its generated name: the caller follows the owner's rename on every level
    return named


def _part_block_row(s: StagingBlocks, beans: Mapping[str, tuple[str, str]], name: str) -> MasterRow:
    """The row of a part, on its numbered beans. A block that became a part while its field rows stand is a problem
    (its own cells would be lost, so the owner decides): put in s.bad and those rows taken out of s.prior. Its cp is
    line_cp's of its own track and its comment names its block's detector, both set later (_line_cps,
    _part_comments)."""
    part = s.lay.parts[name]
    was = [(layer, k, s.prior[layer, k]["user_name"]) for layer, k in
           (("block", s.ids[name]), ("occupancy", device_ids.det_id(s.ids[name]))) if (layer, k) in s.prior]
    if was:
        s.bad.append(f"staging block {name} is now part of {part['part_of']} ({mast_rule.OVERRIDES_NAME}), but "
                     f"{devices.FIELD_FILE} still has its "
                     + " and ".join(f"{layer} row {n}" for layer, _k, n in was)
                     + ": remove them (its detector's input becomes a spare)")
        for layer, k, _n in was:
            s.prior.pop((layer, k))
    row = part_row(STAGING_LEVEL, name, part, s.trials[name], s.ids[name])
    row.update(assignment="virtual", jmri_name=beans[name][0], layout_block=beans[name][1])
    row["description"] = devices.describe(row)
    return row


def _block_row(s: StagingBlocks, beans: Mapping[str, tuple[str, str]], name: str, did: str,
               cp_of: Mapping[str, str], pin_of: Mapping[str, StagingPin],
               on_helix: Mapping[str, tuple[int, int]]) -> MasterRow:
    """The row of a block, generated as main and upper's are (device_map_rows.device_row); its comment marks where
    its detector goes (wire_block fills it from its pin, or its helix pin), and the owner's words go over it. A
    comment that marks a detector no pin wires is a problem, put in s.bad."""
    pin = pin_of.get(did)
    at = (pin.node, pin.k) if pin else on_helix.get(did)
    row = _owned(s, beans, device_row(
        STAGING_LEVEL, cp_of.get(did.split(":")[1], "") if did.startswith("os:") else "", "block", name,
        comment=f"{name}; {devices.OCCUPANCY_MARK}" if at else name, trial=s.trials.get(name, ""),
        role=_block_role(s.lay, name, did), ident=did))
    if at is not None:
        try:
            row = wire_block(row, *at)
        except MapError as exc:
            s.bad.append(str(exc))
    elif devices.OCCUPANCY_MARK in row["jmri_comment"]:
        s.bad.append(f"{devices.FIELD_FILE}: staging block {name}: its jmri_comment marks "
                     f"{devices.OCCUPANCY_MARK}, but no {PINS.name} pin wires it")
    return row


def _part_comments(s: StagingBlocks, named: dict[str, MasterRow]) -> None:
    """Each part's JMRI comment: where it is, and its block's detector (its occupancy sensor, as rewired on this
    build). A part whose block has the owner's name names that. A part whose block has no row, or no occupancy in
    its comment, is a problem, put in s.bad."""
    block_rows = {n: r for n, r in named.items() if r["role"] != "part"}
    for name, r in named.items():
        if r["role"] != "part":
            continue
        of = block_rows.get(r["part_of"])
        if of is None:
            s.bad.append(f"staging part {r['user_name']}: its block {r['part_of']} has no row to take its detector "
                         "from")
            continue
        m = re.search(r"occupancy .*$", of["jmri_comment"])
        if not m:
            s.bad.append(f"staging part {r['user_name']}: its block {r['part_of']} has no occupancy in its comment")
            continue
        if of["user_name"] != r["part_of"]:
            r["notes"] = r["notes"].replace(f"part of {r['part_of']} (", f"part of {of['user_name']} (")
            r["part_of"] = of["user_name"]
            r["description"] = devices.describe(r)
        t = s.lay.parts[name]["track"]
        ends = " to ".join(f"Switch {sw}" for sw in sorted({v for k, v in t["ends"] if k == "sw"}, key=natural))
        r["jmri_comment"] = f"Part of {r['part_of']}, the track from {ends}; {m.group(0)}"


def _line_cps(s: StagingBlocks, named: dict[str, MasterRow], places: Places) -> None:
    """A line block's cp is the rule's and the owner's additions (line_cp), not the field's. A station that lists a
    track staging has no block for is a problem, put in s.bad."""
    staging_names = s.blocks | set(s.lay.parts)
    s.bad.extend(f"{STATIONS.name}: {', '.join(places.tracks[t])} lists {t.removeprefix('Track ')} in its tracks, "
                 "which is no staging block" for t in sorted(places.tracks) if t not in staging_names)
    for name, r in named.items():
        if r["role"] in devices.LINE_ROLES:
            track = s.lay.parts[name]["track"] if r["role"] == "part" else s.lay.tracks[name][0]
            r["cp"] = line_cp(name, STAGING_LEVEL, track, places, helix_ends(s.helix_rows))


def _occupancy_rows(s: StagingBlocks, named: Mapping[str, MasterRow], beans: Mapping[str, tuple[str, str]],
                    pin_of: Mapping[str, StagingPin]) -> list[MasterRow]:
    """The occupancy row of each block but a helix block's (its row is its main or upper level's), wired from its
    pin. A block with no pin is a problem, put in s.bad (a block with no device ID is already there)."""
    occupancy = []
    for b in sorted(s.blocks - s.helix, key=natural):
        if b not in s.ids:
            continue
        block = named.get(b)
        did = device_ids.det_id(s.ids[b])
        pin = pin_of.get(s.ids[b])
        if pin is None:
            f = s.prior.pop(("occupancy", did), None)
            s.bad.append(f"staging block {b}: its detector {(f or {}).get('user_name') or occupancy_user(b)} has no "
                         f"level 1 row in {PINS.name}")
            continue
        name = block["user_name"] if block else b
        row = _owned(s, beans, device_row(
            STAGING_LEVEL, block["cp"] if block else "", "occupancy", occupancy_user(name), pin.sensor, pin.node,
            pin.wiring, notes=f"blocks {name}", jmri=pin.sensor, role=block["role"] if block else "track",
            ident=did, blocks=name, detector="wired"))
        occupancy.append(wire_occupancy(dict(row, cp=block["cp"] if block else "", blocks=name), pin))
    return occupancy


def _spare_rows(s: StagingBlocks, staging_pins: Sequence[StagingPin]) -> list[MasterRow]:
    """The spare inputs: a pin with no block, and a pin whose block is now a part (its rails are still on that
    input). wiring.csv makes their rows, so a field row for one is a problem, put in s.bad."""
    part_ids = {s.ids[n] for n in s.lay.parts if n in s.ids}
    spares = [new_spare(p) for p in staging_pins if not p.id or p.id in part_ids]
    taken_spare = [n for p in staging_pins
                   for n in _drop(s.prior, "occupancy", f"unused {p.input}", device_ids.spare_id(p.sensor))]
    s.bad.extend(f"{devices.FIELD_FILE}: occupancy {n} is a spare input of {PINS.name}, which makes its row: "
                 "remove the field row" for n in taken_spare)
    return spares
