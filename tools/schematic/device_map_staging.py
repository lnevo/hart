"""Staging's rows of the device master (build_device_map.py): its block layer, its block, occupancy and part rows
(staging_rows) and its wired turnout, LCC alias and feedback rows (staging_wired_rows). The trial keys every level's
line blocks carry (piece_trials, level_trials), the cp of a line block (line_cp) and a part's row (part_row) are here
too: the main and upper build uses them.

Staging's plant is the field, so its block and occupancy rows carry their field facts (system
and layout-block names, node, wiring, comment, notes, detector, stop and the station group in cp) over from the row
of the same device ID (devices_field.csv is keyed by it, naming-layers step 4: its user name is the owner's); this
script owns which blocks there are and what each holds (role, trial_name in staging's switch-and-leg keys, part_of,
blocks, description). A staging block change made in PanelPro is carried by
hand into this script's data (block_overrides.csv, plan_overrides.json). A
staging detector's wiring (node and input, so its sensor and wiring) is its level 1 row of
wiring.csv (hartlib.wiring, the physical wiring source; owner 2026-11-20), as are its turnouts' and feedback's
(staging_wired_rows) and main and upper's pinned detectors; any other field
fact of a staging device (a new block system name, its comment, a DCC address) is the owner's, in its row of
devices_field.csv (ADR-029 amendment, 2026-11-21), which this script reads and never writes: it writes
devices_generated.csv, and never reads its own last rows back but for the numbers it gave (devices.allocated_names).
A new staging block needs its field row first.

The drawing's tracks come from device_map_schematic; the builder's paths (OVERRIDES, OUT through device_files) are read
from build_device_map when a function runs (device_map_schematic.builder), as they are then: that module imports this
one, so this one does not import it at load.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))
import block_layer  # noqa: E402  the one block process for every level
import mast_rule  # noqa: E402  read_block_splits, OVERRIDES_NAME
from mast_rule import MapError, band_levels  # noqa: E402
from device_map_inputs import (  # noqa: E402  the readers
    CPS, FIELD_LEVEL, NODES, PINS, STATIONS, WIRING, Places, StagingPin, helix_pins, read_places, read_staging_pins,
    staging_nodes, wiring_rows)
from device_map_schematic import block_overrides, builder, helix_tracks, home_and_posts, named_tracks  # noqa: E402
from hartlib import device_ids, devices, layer_files, level_devices, railroad  # noqa: E402

natural = railroad.natural
occupancy_user = level_devices.occupancy_user


STAGING_SHEET = "staging"           # staging's section of plan_overrides.json
FIELD_LAYERS = ("block", "occupancy")


def part_row(level: str, name: str, part: dict, trial: str, device_id: str = "") -> dict:
    """The master row of a part (block_layer.Layer.parts): a piece of track inside another block, part_of naming it,
    with no occupancy row or detector of its own (hartlib.devices: role part). It is a JMRI block of its own on every
    level, its sensor its OS block's (owner, 2026-11-20): main and upper's the Layout Editor build makes (assignment
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
    """{part: (jmri_name, layout_block)} of the parts of a level whose beans the generator writes (staging,
    tables_build.GENERATED_LEVELS), each a JMRI block of its own on its block's occupancy sensor (owner, 2026-11-20):
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
    """Every name a bean has but staging's parts': the master's other rows (system_name, jmri_name, layout_block),
    and the template's and the parked snapshot's block and layout block names (hartlib.tables_build.TEMPLATE,
    hartlib.parked.PARKED_XML), so a new part's numbers are free everywhere."""
    from hartlib import parked, tables_build
    out = {r[c] for r in master if not (r["level"] == FIELD_LEVEL and r["role"] == "part")
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
        raise MapError(str(exc)) from None
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
    placeholder, not here. One grammar for every level (owner, 2026-11-20); a key drawn on two bands (a track cut by a
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
    export (owner, 2026-11-20). A strand inside a crossover is its OS block's ("OS Switch <n>", written by os_rows)."""
    return level_keys(bands, joined, lay)[0]


def level_keys(bands, joined, lay: block_layer.Layer) -> tuple[dict[str, str], dict[str, str]]:
    """({row name: trial_name} (level_trials), {row name: device ID}) of the main and upper track, half and part rows
    of `lay`, both from the same plan ends: the ID is block: and the row's pieces' keys (hartlib.device_ids)."""
    import staging_device_map as sdm        # its placeholder grammar (it imports this module)
    try:
        refs = {bi: sdm.band_refs(bands, joined, bi) for bi in lay.rows}
    except sdm.StagingMapError as exc:
        raise MapError(str(exc)) from None
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
            if f["level"] == FIELD_LEVEL and f["layer"] in layers}


def alias_note(turnout: str, address: str) -> str:
    """The note of an LCC alias row: the turnout it stands for and that turnout's LCOS address. MapError when the
    turnout has no address (no wiring.csv row)."""
    if not address:
        raise MapError(f"LCC alias DCC {turnout}: {turnout} has no turnout row in {WIRING.name}")
    return f"LCC alias of {turnout} ({address})"


def staging_wired_rows(files: devices.Files | None = None, path: Path | None = None,
                       nodes: set | None = None) -> list[dict]:
    """Staging's turnout, LCC alias and feedback rows of the master: each the owner's field row (devices_field.csv:
    its id, user name, role, assignment, cp, dcc and the rest of the owner's cells) with its wiring cells from
    wiring.csv (`path`, default the committed file): node, the wiring text, the address (system name, and the JMRI
    name unless the field row gives another: a turnout the panels bind by its user name). wiring.csv knows the device
    by its generated name, which comes from the row's id (wired_name), so the owner may rename it; a field row with
    no user name takes the generated one. An LCC alias ("DCC Switch <n>") takes its turnout's node and wiring and
    keeps its MTT<dcc> names (the field row's); its note names the turnout and its address (alias_note). The
    description is written from the row (devices.describe), as it names the node. `nodes`: staging's (default
    staging_nodes()). MapError on a field row whose id is no turnout, alias or feedback ID, a field row with no wiring
    row, a wiring row with no field row or on a node that is not staging's."""
    bdm = builder()
    nodes = staging_nodes() if nodes is None else nodes
    by = {(w.kind, w.device): w for w in wiring_rows(path) if w.level == int(FIELD_LEVEL) and w.kind in ("turnout", "fb")}
    bad = [f"{WIRING.name} line {w.line}: {w.kind} {w.device} is on node {w.node}, no staging node of {NODES.name} "
           f"({', '.join(map(str, sorted(nodes)))})" for w in by.values() if w.node not in nodes]
    field = bdm.device_files() if files is None else files
    rows = staging_field(field, tuple(WIRED_LAYERS)).values()
    out, seen = [], set()
    turnout_address = {w.device: w.address for (kind, _d), w in by.items() if kind == "turnout"}
    # a turnout's name as readers see it (the owner's, else the generated one), by its switch number: its alias's note
    turnout_name = {r["id"].split(":", 1)[1]: r["user_name"] for r in rows
                    if r["role"] == "turnout" and r["id"].startswith("switch:") and r["user_name"]}
    for r in rows:
        alias = r["role"] == "lcc_alias"
        try:
            generated = wired_name(r)
        except ValueError as exc:
            bad.append(f"staging {r['layer']} {r['user_name']}: {exc}")
            continue
        name = generated.removeprefix("DCC ") if alias else generated
        w = by.get((WIRED_LAYERS[r["layer"]], name))
        if w is None:
            bad.append(f"staging {r['layer']} {r['user_name'] or generated}: no {WIRED_LAYERS[r['layer']]} row for "
                       f"{name} in {WIRING.name}")
            continue
        seen.add((w.kind, w.device))
        row = dict(r, user_name=r["user_name"] or generated, node=str(w.node), wiring=w.wiring_text,
                   written_by="build_device_map.py")
        if not alias:
            row["system_name"] = w.address
            row["jmri_name"] = r["jmri_name"] or w.address
            if row["jmri_name"] not in (w.address, row["user_name"]):
                # a turnout the panels bind by its user name (Q13): a rename moves the binding, so the owner changes
                # both cells together; the build does not rewrite the binding
                bad.append(f"{devices.FIELD_FILE}: staging {r['layer']} {row['user_name']} (id {r['id']}): its "
                           f"jmri_name {row['jmri_name']!r} binds it by its old user name; change jmri_name and "
                           f"user_name together, or clear jmri_name to bind it by its address {w.address}")
                continue
        else:
            number = r["id"].split(":", 1)[1]
            row["notes"] = alias_note(turnout_name.get(number, name), turnout_address.get(name, ""))
        row["description"] = devices.describe(row)
        out.append(row)
    for kind, device in sorted(set(by) - seen):
        bad.append(f"{WIRING.name} line {by[kind, device].line}: staging {kind} {device} has no row in "
                   f"{devices.FIELD_FILE}")
    if bad:
        raise MapError("; ".join(bad))
    return out


# a staging turnout's, LCC alias's or feedback's device ID (hartlib.device_ids) and the generated name it gives
WIRED_ID = {"turnout": (re.compile(r"switch:(\d+)"), "Switch {}"),
            "lcc_alias": (re.compile(r"dcc:(\d+)"), "DCC Switch {}"),
            "fb": (re.compile(r"fb:(\d+):([NR])"), "FB Switch {} {}")}


def wired_name(row: Mapping[str, str]) -> str:
    """The generated name of a staging turnout, LCC alias or feedback row, from its device ID (hartlib.device_ids:
    switch:<n> "Switch <n>", dcc:<n> "DCC Switch <n>", fb:<n>:N|R "FB Switch <n> N|R"): the name wiring.csv knows it
    by. The id is the field row's key (hartlib.devices.KEY); nothing ties these rows to the plan until staging is
    generated (hand-off step 7), so build_device_map.check_switch_ids holds every number to a staging OS block of the
    plan. ValueError on an id out of that grammar for the row's kind."""
    kind = row["role"] if row["role"] in WIRED_ID else row["layer"]
    pattern, name = WIRED_ID.get(kind, (None, ""))
    m = pattern.fullmatch(row["id"]) if pattern else None
    if not m:
        raise ValueError(f"id {row['id']!r} is not a {kind} ID with a switch number "
                         f"({', '.join(p.pattern for p, _n in WIRED_ID.values())})")
    return name.format(*m.groups())


def wire_occupancy(row: dict, pin: StagingPin) -> dict:
    """`row` (a staging occupancy row) with its wiring cells from its pin: node, sensor and wiring."""
    return dict(row, node=str(pin.node), system_name=pin.sensor, jmri_name=pin.sensor, wiring=pin.wiring)


def new_spare(pin: StagingPin) -> dict:
    """The row of a spare input (a wiring.csv detector with no block, or one whose block is now a part): named by its
    input. wiring.csv makes it; it has no field row."""
    row = {c: "" for c in devices.COLUMNS}
    row.update(level=FIELD_LEVEL, layer="occupancy", role="spare", user_name=f"unused {pin.input}",
               assignment="spare", written_by="build_device_map.py")
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
    """({part: (jmri_name, layout_block)} of staging's parts as this script last numbered them, every other bean's
    names): the name memory part_bean_names keeps its numbers by (devices.allocated_names, the one read-back of this
    script's own output), and every name taken (taken_bean_names) so a new number is free."""
    bdm = builder()
    f = files or bdm.device_files()
    mine = {u: (r["jmri_name"], r["layout_block"])
            for u, r in devices.allocated_names((FIELD_LEVEL,), "block", ("part",), f).items()}
    # both files as written, not their merge: a field row the owner just removed leaves a generated row that no
    # longer merges, and this build is what writes it again
    return mine, taken_bean_names(list(devices.generated_rows(f)) + list(devices.field_rows(f)))


def staging_rows(bands, joined, runs, files: devices.Files | None = None,
                 exceptions: Path | None = None, pins: Path | None = None,
                 places: Places | None = None, part_names: tuple[dict, set] | None = None) -> list[dict]:
    """Staging's block and occupancy rows of the master: the one block process's blocks and parts of the staging
    band (staging_layer), each block row and its occupancy row built on the owner's field row of its device ID
    (devices_field.csv, staging_field: the system and layout-block names, comment, notes, detector, stop, dcc and an
    OS block's control point); a line block's cp, and its sensor's, is line_cp's (the places it joins, `places`:
    read_places by default), never the owner's; this script owns the rest (role but on a field row, trial_name,
    part_of, blocks, written_by, description). The wiring is wiring.csv's (level 1 detectors, read_staging_pins; a
    helix block's, its main or upper row): an occupancy row's node, sensor and wiring, a block row's node and the
    occupancy text in its comment (wire_block), and the spare inputs (no block, or a block that is now a part), each
    row "unused Block <n>-<k>" (new_spare); `pins` (default the committed file). A helix block's occupancy row is the
    level of its helix switch's (main or upper), not staging's: the block is one across levels. A part's beans keep
    the numbers this script gave them (`part_names`, default staging_part_names). MapError on a drawn block with no
    field row, a field row the drawing has no block for, a block that is now a part while its field rows stand (the
    owner's cells would be lost: remove them), a detector block with no pin, or a pin whose block staging does not
    have or is a helix block."""
    bdm = builder()
    lay, bi, _found = staging_layer(bands, joined, runs, exceptions)
    trials, ids = staging_keys(bands[bi][1], lay, bi)
    helix_rows = helix_tracks()
    helix = {h["block"] for h in helix_rows.values()}
    f = files or bdm.device_files()
    prior = staging_field(f)
    blocks = set(lay.bands[bi]["os"].values()) | set(lay.tracks)
    out, bad = [], []
    # staging's beans are the generator's (tables_build.GENERATED_LEVELS), so its parts carry their block names here,
    # where main and upper's take theirs from the Layout Editor build (le_tables numbering)
    mine, taken = staging_part_names(f) if part_names is None else part_names
    try:
        beans = part_bean_names(list(lay.parts), mine, taken)
    except MapError as exc:
        raise MapError(f"staging parts: {exc}") from None
    staging_pins = read_staging_pins(pins)
    pin_of = {p.block: p for p in staging_pins if p.block}
    on_helix = helix_pins(pins)
    for p in staging_pins:
        if p.block in helix:
            bad.append(f"{PINS.name} line {p.line}: {p.block} is a helix block; its detector is its main or upper "
                       "row's")
        elif p.block and p.block not in blocks and p.block not in lay.parts:
            bad.append(f"{PINS.name} line {p.line}: staging has no block {p.block}")

    def owned(layer: str, did: str, name: str, **made) -> dict | None:
        """The row of the staging device `did` (its generated name `name`) built on its field row, found by its id
        (hartlib.devices.KEY): the field row's user name is the owner's, else `name`."""
        old = prior.pop((layer, did), None)
        if old is None:
            bad.append(f"staging {layer} {name} (id {did}): no row in {devices.FIELD_FILE} (add its field row with its "
                       "id, system name, layout block and comment; this script builds the rest)")
            return None
        row = dict(old, written_by="build_device_map.py", **made)     # its role is the owner's
        row["user_name"] = old["user_name"] or name
        row["description"] = devices.describe(row)
        return row

    def drop(layer: str, name: str, did: str = "") -> list[str]:
        """Take the field rows of `layer` with the id `did` (when known) or named `name` out of `prior` (a field row's
        user name may be empty: the generated name stands); `name` once per row taken."""
        keys = [k for k, r in prior.items() if k[0] == layer and ((did and k[1] == did) or r["user_name"] == name)]
        for k in keys:
            prior.pop(k)
        return [name for _k in keys]

    named: dict[str, dict] = {}             # {drawn name: row} of the blocks and parts; a row may hold the owner's name
    for name in sorted(blocks | set(lay.parts), key=natural):
        if name in lay.parts:
            part = lay.parts[name]
            was = [(layer, k, prior[layer, k]["user_name"]) for layer, k in
                   (("block", ids[name]), ("occupancy", device_ids.det_id(ids[name]))) if (layer, k) in prior]
            if was:                 # a block that became a part: its own cells would be lost, so the owner decides
                bad.append(f"staging block {name} is now part of {part['part_of']} ({mast_rule.OVERRIDES_NAME}), but "
                           f"{devices.FIELD_FILE} still has its "
                           + " and ".join(f"{layer} row {n}" for layer, _k, n in was)
                           + ": remove them (its detector's input becomes a spare)")
                for layer, k, _n in was:
                    prior.pop((layer, k))
            row = part_row(FIELD_LEVEL, name, part, trials[name], ids[name])
            row.update(assignment="virtual", jmri_name=beans[name][0], layout_block=beans[name][1])
            # its cp is line_cp's of its own track and its comment names its block's detector, both set below (the
            # comment from the block's rewired row)
            row["description"] = devices.describe(row)
            out.append(row)
            named[name] = row
        else:
            if name not in ids:
                bad.append(f"staging block {name}: the plan gives it no ends, so no device ID")
                drop("block", name)                         # one error for it, not a second "no block" one
                drop("occupancy", occupancy_user(name))
                continue
            row = owned("block", ids[name], name, trial_name=trials.get(name, ""), id=ids[name])
            at = (pin_of[name].node, pin_of[name].k) if name in pin_of else on_helix.get(name)
            if row is not None and at is not None:
                try:
                    row = wire_block(row, *at)
                except MapError as exc:
                    bad.append(str(exc))
            elif row is not None and devices.OCCUPANCY_MARK in row["jmri_comment"]:
                bad.append(f"{devices.FIELD_FILE}: staging block {name}: its jmri_comment marks "
                           f"{devices.OCCUPANCY_MARK}, but no {PINS.name} pin wires it")
            out.append(row)
            if row is not None:
                named[name] = row
    block_rows = {n: r for n, r in named.items() if r["role"] != "part"}
    for name, r in named.items():   # a part's JMRI comment: where it is, and its block's detector (its occupancy sensor)
        if r["role"] == "part":
            of = block_rows.get(r["part_of"])       # as rewired on this build (wiring.csv)
            if of is None:
                bad.append(f"staging part {r['user_name']}: its block {r['part_of']} has no row to take its detector "
                           "from")
                continue
            m = re.search(r"occupancy .*$", of["jmri_comment"])
            if not m:
                bad.append(f"staging part {r['user_name']}: its block {r['part_of']} has no occupancy in its comment")
                continue
            if of["user_name"] != r["part_of"]:     # its block has the owner's name: the part names that
                r["notes"] = r["notes"].replace(f"part of {r['part_of']} (", f"part of {of['user_name']} (")
                r["part_of"] = of["user_name"]
                r["description"] = devices.describe(r)
            t = lay.parts[name]["track"]
            ends = " to ".join(f"Switch {s}" for s in sorted({v for k, v in t["ends"] if k == "sw"}, key=natural))
            r["jmri_comment"] = f"Part of {r['part_of']}, the track from {ends}; {m.group(0)}"
    places = read_places() if places is None else places
    staging_names = blocks | set(lay.parts)
    bad += [f"{STATIONS.name}: {', '.join(places.tracks[t])} lists {t.removeprefix('Track ')} in its tracks, which "
            "is no staging block" for t in sorted(places.tracks) if t not in staging_names]
    for name, r in named.items():   # a line block's cp is the rule's and the owner's additions (line_cp), not the field's
        if r["role"] in devices.LINE_ROLES:
            track = lay.parts[name]["track"] if r["role"] == "part" else lay.tracks[name][0]
            r["cp"] = line_cp(name, FIELD_LEVEL, track, places, helix_ends(helix_rows))
    occupancy = []
    for b in sorted(blocks - helix, key=natural):
        if b not in ids:
            continue                        # named in bad above
        block = named.get(b)
        did = device_ids.det_id(ids[b])
        row = owned("occupancy", did, occupancy_user(block["user_name"] if block else b),
                    blocks=block["user_name"] if block else b, cp=block["cp"] if block else "", id=did)
        if row is None:
            continue
        if b not in pin_of:
            bad.append(f"staging block {b}: its detector {row['user_name']} has no level 1 row in {PINS.name}")
            continue
        occupancy.append(wire_occupancy(row, pin_of[b]))
    # spare inputs: a pin with no block, and a pin whose block is now a part (its rails are still on that input)
    spares = [new_spare(p) for p in staging_pins if not p.block or p.block in lay.parts]
    taken_spare = [n for p in staging_pins
                   for n in drop("occupancy", f"unused {p.input}", device_ids.spare_id(p.sensor))]
    bad += [f"{devices.FIELD_FILE}: occupancy {n} is a spare input of {PINS.name}, which makes its row: remove the "
            "field row" for n in taken_spare]
    if prior:
        bad.append(f"staging rows of {devices.FIELD_FILE} the drawing has no block for: "
                   + ", ".join(f"{layer} {r['user_name'] or '(no name)'} (id {did})"
                               for (layer, did), r in sorted(prior.items())))
    if bad:
        raise MapError("; ".join(bad))
    out += sorted(occupancy + spares, key=lambda r: natural(r["user_name"]))
    return out
