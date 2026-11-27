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
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import block_layer  # noqa: E402  the one block process for every level
import block_override_rows  # noqa: E402
import staging_device_map as sdm  # noqa: E402  the placeholder grammar every level's trial keys follow
from map_error import MapError  # noqa: E402
from plan_bands import Band, Bands, HelixEntry, band_levels  # noqa: E402
from plan_tracks import Joined, Runs, Track  # noqa: E402
from staging_records import Ref  # noqa: E402  a strand's (piece reference, whether it runs against the piece)
from device_map_inputs import (  # noqa: E402  the readers
    CPS, PINS, STATIONS, Places, StagingPin, helix_pins, read_places, read_staging_pins)
from device_map_rows import device_row, owner_over  # noqa: E402  every level's row makers
from device_map_schematic import (  # noqa: E402
    block_overrides, builder, helix_tracks, home_and_posts, line_role, named_tracks)
from device_map_staging_switches import (  # noqa: E402,F401  staging's switch rows and shared names; re-exported
    FIELD_LAYERS, STAGING, STAGING_LEVEL, STAGING_SHEET, WIRED_LAYERS, WRITER, FieldKey, MasterRow, alias_note,
    check_unique, field_row, staging_cps, staging_field, staging_switches, staging_wired_rows)
from hartlib import device_ids, devices, layer_files, level_devices, railroad  # noqa: E402

natural = railroad.natural
occupancy_user = level_devices.occupancy_user


class Beans(NamedTuple):
    """The two bean names of a block this script numbers (a part, or a block the owner names no beans for)."""
    jmri_name: str          # IB:AUTO:<nnnn>
    layout_block: str       # ILB<n>


class NameMemory(NamedTuple):
    """What part_bean_names keeps its numbers by (staging_part_names): {device ID: the beans this script last gave
    it}, and every bean name taken elsewhere."""
    mine: dict[str, Beans]
    taken: set[str]


def part_row(level: str, name: str, part: block_layer.Part, trial: str, device_id: str = "") -> MasterRow:
    """The master row of a part (block_layer.Layer.parts): a piece of track inside another block, part_of naming it,
    with no occupancy row or detector of its own (hartlib.devices: role part). It is a JMRI block of its own on every
    level, its sensor its OS block's: main and upper's the Layout Editor build makes (assignment
    none here); staging_rows gives staging's their bean names (part_bean_names, assignment virtual). `device_id`: its
    block ID from the plan ends its trial name has (staging_keys, level_keys)."""
    t = part["track"]
    row = {c: "" for c in devices.COLUMNS}
    row.update(level=level, layer="block", role="part", id=device_id, user_name=name, assignment="none",
               trial_name=trial,
               notes=f"a piece of the {t['cm']} cm track from Switch {' to Switch '.join(end_switches(t))}, part of "
                     f"{part['part_of']} ({part['why']})",
               part_of=part["part_of"], written_by=WRITER)
    row["description"] = devices.describe(row)
    return row


def end_switches(track: Track) -> list[str]:
    """The numbers of the switches at a track's ends, in number order (a track between two legs of one switch:
    once)."""
    sws = {v for k, v in track["ends"] if k == "sw"}
    if None in sws:
        raise MapError(f"a track with ends {track['ends']}: a switch end with no number")
    return sorted((v for v in sws if v is not None), key=natural)


PART_BLOCK_FIRST = 52        # a new staging part's number: the first above staging's last JMRI block (IB:AUTO:0051)


def part_bean_names(parts: Iterable[str], prior: Mapping[str, tuple[str, str]], taken: Iterable[str]
                    ) -> dict[str, Beans]:
    """{part: (jmri_name, layout_block)} of staging's parts, each a JMRI block of its own on its block's occupancy sensor:
    the names its row has (`prior`: {part: (jmri_name, layout_block)}), else, in name order, the next number n from
    PART_BLOCK_FIRST up with neither IB:AUTO:<nnnn> nor ILB<n> in `taken` (every other bean's names), so a name never
    shifts. MapError on a row with one of the two names only, or a name another bean has."""
    out: dict[str, Beans] = {}
    bad: list[str] = []
    used = set(taken)
    parts = sorted(parts, key=natural)
    for p in parts:
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
            out[p] = Beans(jn, lb)
            used |= {jn, lb}
    if bad:
        raise MapError("; ".join(bad))
    n = PART_BLOCK_FIRST
    for p in parts:
        if p in out:
            continue
        while f"IB:AUTO:{n:04d}" in used or f"ILB{n}" in used:
            n += 1
        out[p] = Beans(f"IB:AUTO:{n:04d}", f"ILB{n}")
        used |= set(out[p])
    return out


BEAN_NAME = re.compile(r"\bIB:AUTO:\d{4}\b|\bILB\d+\b")


def taken_bean_names(master: Iterable[Mapping[str, str]]) -> set[str]:
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


def staging_layer(bands: Bands, joined: Joined, runs: Runs, exceptions: Path | None = None
                  ) -> tuple[block_layer.Layer, int, list[Track]]:
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
                                  block_override_rows.read_block_splits(exceptions, found, levels))
    split = block_layer.split_edges(found, levels, exceptions, bdm.OVERRIDES.parent)
    lay = block_layer.layer(bands, runs, found, levels, split,
                            block_layer.read_exceptions(found, bands, levels, exceptions), posts=posts,
                            data=bdm.OVERRIDES.parent)
    if len(lay.bands) != 1:
        raise MapError(f"staging is drawn on {len(lay.bands)} bands; its trial names need one")
    return lay, next(iter(lay.bands)), found


def staging_trials(band: Band, lay: block_layer.Layer, bi: int) -> dict[str, str]:
    """{row name: trial_name} of staging's block rows in its drawing's keys (staging_device_map.placeholders: switch
    numbers and legs, which survive a new export): a row's OS placeholders, then its track pieces in strand order,
    each "Track <piece>" or, for the k-th of a piece's n rows from the piece's first end, "Track <piece> k/n"."""
    return staging_keys(band, lay, bi)[0]


def staging_keys(band: Band, lay: block_layer.Layer, bi: int) -> tuple[dict[str, str], dict[str, str]]:
    """({row name: trial_name} (staging_trials), {row name: device ID}) of staging's block rows, both from the same
    plan ends (hartlib.device_ids): an OS block's ID is its switch's (staging_device_map.os_keys: os:<n>, or
    os:<n>:A-<end> of a crossover half), even when a piece of track lies inside it; any other row's is block: and
    its pieces' keys, in key order. MapError on a row that two switches' OS blocks share."""
    _turnouts, _os_ph, refs = sdm.placeholders(band)
    got: defaultdict[str, list[str]] = defaultdict(list)
    ids: dict[str, str] = {}
    bad: list[str] = []
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


BandRows = Mapping[int, Mapping[str, list[str]]]     # {band index: {strand: [row, ...] from its first end]}
BandRefs = Mapping[int, Mapping[str, Ref]]           # {band index: {strand: (piece reference, against)}}


def piece_trials(rows: BandRows, refs: BandRefs, inside: Mapping[int, set[str]]) -> dict[str, list[str]]:
    """{row name: its track placeholders, in key order} of the layer rows of some bands (`rows`: {band index: {strand:
    [row, ...] from the strand's first end]}, block_layer.Layer.rows), each strand keyed by `refs` ({band index:
    staging_device_map.piece_refs or band_refs}): "Track <piece>", or "Track <piece> k/n" for the k-th of its n rows
    from the piece's first end (staging_device_map.strand_placeholders, the rule every reader keys by). A strand whose
    rows are all in `inside` ({band index: OS blocks}) is inside a crossover and keyed by its OS block's own
    placeholder, not here. One grammar for every level; a key drawn on two bands (a track cut by a
    connector) is listed once. MapError on a strand with rows but no key."""
    return {row: [ph for ph, _k in keys] for row, keys in piece_keys(rows, refs, inside).items()}


def piece_keys(rows: BandRows, refs: BandRefs, inside: Mapping[int, set[str]]) -> dict[str, list[tuple[str, str]]]:
    """{row name: [(track placeholder, device-ID part)], in placeholder key order}: piece_trials' placeholders, each
    with the ID part of the same piece, k and n (staging_device_map.strand_ids, hartlib.device_ids.strand_key)."""
    got: defaultdict[str, dict[str, str]] = defaultdict(dict)
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


def level_trials(bands: Bands, joined: Joined, lay: block_layer.Layer) -> dict[str, str]:
    """{row name: trial_name} of the main and upper track, half and part rows of `lay` (main_upper_layer), in the
    switch-and-leg keys staging's rows have (piece_trials over staging_device_map.band_refs), which survive a new
    export. A strand inside a crossover is its OS block's ("OS Switch <n>", written by os_rows)."""
    return level_keys(bands, joined, lay)[0]


def level_keys(bands: Bands, joined: Joined, lay: block_layer.Layer) -> tuple[dict[str, str], dict[str, str]]:
    """({row name: trial_name} (level_trials), {row name: device ID}) of the main and upper track, half and part rows
    of `lay`, both from the same plan ends: the ID is block: and the row's pieces' keys (hartlib.device_ids)."""
    try:
        refs = {bi: sdm.band_refs(bands, joined, bi) for bi in lay.rows}
    except sdm.StagingMapError as exc:
        raise MapError(str(exc)) from exc
    inside = {bi: set(b["os"].values()) for bi, b in lay.bands.items()}
    keys = piece_keys(lay.rows, refs, inside)
    return ({row: ", ".join(ph for ph, _k in ks) for row, ks in keys.items()},
            {row: device_ids.block_id(k for _ph, k in ks) for row, ks in keys.items()})


def helix_ends(helix: Mapping[str, HelixEntry]) -> dict[str, set[str]]:
    """{helix block: its two end switches, staging's and the main or upper one's number} (`helix`:
    read_helix_tracks): a helix block is one block across the levels, so each level's row of it has both ends.
    MapError on a level switch that does not start with its number."""
    out: dict[str, set[str]] = {}
    for plan, h in helix.items():
        m = re.match(r"\d+", h["level_switch"])
        if m is None:
            raise MapError(f"helix track {plan}: level_switch {h['level_switch']!r} is no switch number")
        out[h["block"]] = {h["staging_switch"], m.group(0)}
    return out


def line_cp(block: str, level: str | int, track: Track, places: Places,
            helix_ends: Mapping[str, set[str]] | None = None) -> str:
    """The cp of the level `level` row of a line block (devices.LINE_ROLES) on `track` (a mast_rule track: its
    `ends`; a helix block's ends from `helix_ends` too, which its drawing on one level does not reach): the places of
    the switches at its two ends and the stations whose `tracks` name it, each once, joined by railroad.DEVICE_LIST
    (a block in none: empty). The row's own level's places come first, then the nearer levels' (a helix block's main
    and upper rows read "CP 127;Princess", its staging row "Princess;CP 127"), each level's in Places.order: a reader
    that wants one place takes the first."""
    sws = set(end_switches(track)) | (helix_ends or {}).get(block, set())
    got = {p for v in sws for p in places.of.get(v, ())} | set(places.tracks.get(block, ()))
    return railroad.DEVICE_LIST.join(sorted(got, key=lambda p: (abs(places.level[p] - int(level)), places.order[p])))


def wire_occupancy(row: Mapping[str, str], pin: StagingPin) -> MasterRow:
    """`row` (a staging occupancy row) with its wiring cells from its pin: node, sensor and wiring."""
    return dict(row, node=str(pin.node), system_name=pin.sensor, jmri_name=pin.sensor, wiring=pin.wiring)


def new_spare(pin: StagingPin) -> MasterRow:
    """The row of a spare input (a wiring.csv detector with no block, or one whose block is now a part): named by its
    input, detector none. wiring.csv makes it; it has no field row."""
    row = {c: "" for c in devices.COLUMNS}
    row.update(level=STAGING_LEVEL, layer="occupancy", role="spare", user_name=f"unused {pin.input}",
               assignment="spare", detector="none", written_by=WRITER)
    row = wire_occupancy(row, pin)
    row["id"] = device_ids.spare_id(row["system_name"])
    row["description"] = devices.describe(row)
    return row


def wire_block(row: Mapping[str, str], node: int, k: int) -> MasterRow:
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


def staging_part_names(files: devices.Files | None = None) -> NameMemory:
    """({block ID: Beans} of staging's block rows as this script last numbered them (its parts, and
    a block with no field row), every other bean's names): the name memory part_bean_names keeps its numbers by
    (devices.allocated_names, the one read-back of this script's own output; a block the owner names has no number
    there), and every name taken (taken_bean_names) so a new number is free."""
    bdm = builder()
    f = files or bdm.device_files()
    mine = {r["id"]: Beans(r["jmri_name"], r["layout_block"])
            for r in devices.allocated_names((STAGING_LEVEL,), "block", None, f).values()
            if r["jmri_name"] and r["layout_block"]}
    # both files as written, not their merge: a field row the owner just removed leaves a generated row that no
    # longer merges, and this build is what writes it again
    return NameMemory(mine, taken_bean_names(list(devices.generated_rows(f)) + list(devices.field_rows(f))))


class StagingBlocks(NamedTuple):
    """Staging's drawn blocks and what staging_rows' steps read of them. `prior` (the owner's field rows not yet
    used) and `bad` (the problems found) are filled in place by the steps, in order, so the error text keeps one
    order."""
    lay: block_layer.Layer
    bi: int                             # the staging band's index
    trials: dict[str, str]              # {row name: trial_name} (staging_keys)
    ids: dict[str, str]                 # {row name: device ID} (staging_keys)
    blocks: set[str]                    # the OS blocks and track blocks (not the parts)
    helix_rows: dict[str, HelixEntry]   # helix_tracks()
    helix: set[str]                     # the helix blocks
    prior: dict[FieldKey, MasterRow]    # staging_field: {(layer, device ID): field row}
    bad: list[str]


class StagingWiring(NamedTuple):
    """Staging's detectors as wiring.csv has them (read_staging_pins), each block's pin by its device ID (a pin finds
    its block so: the drawn name of an OS block is the rule's, its row's name may be the owner's), and the helix
    blocks' pins on their main or upper rows (helix_pins)."""
    pins: list[StagingPin]
    pin_of: dict[str, StagingPin]
    on_helix: dict[str, tuple[int, int]]


def staging_rows(bands: Bands, joined: Joined, runs: Runs, files: devices.Files | None = None,
                 exceptions: Path | None = None, pins: Path | None = None,
                 places: Places | None = None, part_names: NameMemory | None = None,
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
    f = files or builder().device_files()
    s = _staging_blocks(bands, joined, runs, f, exceptions)
    # staging's parts, and a block the owner has no field row for, carry their block names here, where main and
    # upper's take theirs from block_numbering.csv (build_device_map.block_beans)
    beans = _bean_names(s, _unnamed_blocks(s), staging_part_names(f) if part_names is None else part_names)
    wired = _staging_wiring(pins, f)
    _check_pins(s, wired.pins)
    named = _block_and_part_rows(s, beans, staging_cps(), wired, drawn)
    _part_comments(s, named)
    _line_cps(s, named, read_places() if places is None else places)
    occupancy = _occupancy_rows(s, named, beans, wired.pin_of)
    spares = _spare_rows(s, wired.pins)
    if s.prior:
        s.bad.append(f"staging rows of {devices.FIELD_FILE} the drawing has no block for: "
                     + ", ".join(f"{layer} {r['user_name'] or '(no name)'} (id {did})"
                                 for (layer, did), r in sorted(s.prior.items())))
    if s.bad:
        raise MapError("; ".join(s.bad))
    out = list(named.values()) + sorted(occupancy + spares, key=lambda r: natural(r["user_name"]))
    check_unique(out, "staging's block and occupancy rows")
    return out


def _staging_wiring(pins: Path | None, files: devices.Files) -> StagingWiring:
    """Staging's detectors from wiring.csv (`pins`, default the committed file), named from the master `files`."""
    staging_pins = read_staging_pins(pins, files=files)
    helix = layer_files.read("plan_overrides", "main_upper", builder().OVERRIDES.parent).get("helix", {})
    return StagingWiring(staging_pins, {p.id: p for p in staging_pins if p.id}, helix_pins(pins, helix))


def _staging_blocks(bands: Bands, joined: Joined, runs: Runs, files: devices.Files,
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


def _bean_names(s: StagingBlocks, unnamed: list[str], part_names: NameMemory) -> dict[str, Beans]:
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


def _owned(s: StagingBlocks, beans: Mapping[str, Beans], generated: Mapping[str, str]) -> MasterRow:
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


def _drop(prior: dict[FieldKey, MasterRow], layer: str, name: str, did: str = "") -> list[str]:
    """Take the field rows of `layer` with the id `did` (when known) or named `name` out of `prior` (a field row's
    user name may be empty: the generated name stands); `name` once per row taken."""
    keys = [k for k, r in prior.items() if k[0] == layer and ((did and k[1] == did) or r["user_name"] == name)]
    for k in keys:
        prior.pop(k)
    return [name for _k in keys]


def _block_and_part_rows(s: StagingBlocks, beans: Mapping[str, Beans], cp_of: Mapping[str, str],
                         wired: StagingWiring, drawn: dict[str, str] | None) -> dict[str, MasterRow]:
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
        named[name] = _block_row(s, beans, name, did, cp_of, wired)
        if drawn is not None:
            drawn[did] = name           # its generated name: the caller follows the owner's rename on every level
    return named


def _part_block_row(s: StagingBlocks, beans: Mapping[str, Beans], name: str) -> MasterRow:
    """The row of a part, on its numbered beans. A block that became a part while its field rows stand is a problem
    (its own cells would be lost, so the owner decides): put in s.bad and those rows taken out of s.prior. Its cp is
    line_cp's of its own track and its comment names its block's detector, both set later (_line_cps,
    _part_comments)."""
    part = s.lay.parts[name]
    was = [(layer, k, s.prior[layer, k]["user_name"]) for layer, k in
           (("block", s.ids[name]), ("occupancy", device_ids.det_id(s.ids[name]))) if (layer, k) in s.prior]
    if was:
        s.bad.append(f"staging block {name} is now part of {part['part_of']} ({block_override_rows.OVERRIDES_NAME}), but "
                     f"{devices.FIELD_FILE} still has its "
                     + " and ".join(f"{layer} row {n}" for layer, _k, n in was)
                     + ": remove them (its detector's input becomes a spare)")
        for layer, k, _n in was:
            s.prior.pop((layer, k))
    row = part_row(STAGING_LEVEL, name, part, s.trials[name], s.ids[name])
    row.update(assignment="virtual", jmri_name=beans[name][0], layout_block=beans[name][1])
    row["description"] = devices.describe(row)
    return row


def _block_row(s: StagingBlocks, beans: Mapping[str, Beans], name: str, did: str, cp_of: Mapping[str, str],
               wired: StagingWiring) -> MasterRow:
    """The row of a block, generated as main and upper's are (device_map_rows.device_row); its comment marks where
    its detector goes (wire_block fills it from its pin, or its helix pin), and the owner's words go over it. A
    comment that marks a detector no pin wires is a problem, put in s.bad."""
    pin = wired.pin_of.get(did)
    at = (pin.node, pin.k) if pin else wired.on_helix.get(did)
    row = _owned(s, beans, device_row(
        STAGING_LEVEL, cp_of.get(did.split(":")[1], "") if did.startswith("os:") else "", "block", name,
        comment=f"{name}; {devices.OCCUPANCY_MARK}" if at else name, trial=s.trials[name],
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
        ends = " to ".join(f"Switch {sw}" for sw in end_switches(s.lay.parts[name]["track"]))
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


def _occupancy_rows(s: StagingBlocks, named: Mapping[str, MasterRow], beans: Mapping[str, Beans],
                    pin_of: Mapping[str, StagingPin]) -> list[MasterRow]:
    """The occupancy row of each block but a helix block's (its row is its main or upper level's), wired from its
    pin. A block with no pin is a problem, put in s.bad (a block with no device ID is already there). `named`:
    _block_and_part_rows, which has a row for every block with a device ID."""
    occupancy = []
    for b in sorted(s.blocks - s.helix, key=natural):
        if b not in s.ids:
            continue
        block = named[b]
        did = device_ids.det_id(s.ids[b])
        pin = pin_of.get(s.ids[b])
        if pin is None:
            f = s.prior.pop(("occupancy", did), None)
            s.bad.append(f"staging block {b}: its detector {(f or {}).get('user_name') or occupancy_user(b)} has no "
                         f"level 1 row in {PINS.name}")
            continue
        name = block["user_name"]
        row = _owned(s, beans, device_row(
            STAGING_LEVEL, block["cp"], "occupancy", occupancy_user(name), pin.sensor, pin.node, pin.wiring,
            notes=f"blocks {name}", jmri=pin.sensor, role=block["role"], ident=did, blocks=name, detector="wired"))
        occupancy.append(wire_occupancy(dict(row, cp=block["cp"], blocks=name), pin))
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
