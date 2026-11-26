#!/usr/bin/env python3
"""Placeholder control points and device names for the main and upper levels, and every level's block rows.

    python3 tools/schematic/build_device_map.py           # write both outputs
    python3 tools/schematic/build_device_map.py --check   # exit 1 if either output is stale

--check prints SKIPPED and exits 0 when the plugin submodule is not checked out (1 with SCHEMATIC_REQUIRED=1).

Inputs (jmri/layouts/hart/data/schematic/):
- interlockings.csv, its level 2 and 3 rows: the placeholder control points, "CP <lowest switch>" (owner,
  2026-11-15), which are also the signal rule's interlockings (one file for every level). Hand
  data, one row per control point: level (2 main, 3 upper), switch numbers, area (the LCOS node area). Only
  interlockings that affect the main route are control points, as in the bench plans
  (docs/wiring/bench/control_point_4 to 6): switches on the main route, grouped where they stand close together.
- block_overrides.csv kind split: the owner's choice of tracks parted into two blocks at their turnback (not a rule).
- switches.csv, its main and upper rows: every other switch (yards and industry spurs) has its area there. These get a
  turnout and feedback but no control point, no signals and no detection.
- lcos_nodes.csv: every level's LCOS radio addresses. Staging's are the nodes in service (inventory v86), which this
  never hands out; main and upper's are the ones each level and area may use, in order (each row's source says
  where its address was first taken from: the upper level's from the old inventory v85, the rest from the owner's
  node grid
  media/hart-research/wiring-drafts/lcos-node-grid-2025-10-06c.xlsx, local), where an address 0XN is device X off
  node 0N.
- the solved schematic bands (the inputs publish_draft.py draws), for tracks, their ends and which way is east.

Outputs:
- plan_generated.json's main_upper section (hartlib.layer_files), keys `control_points` and `stations`: the detail
  sheets (the "Main level" and "Upper level" sheets of preferences.json's main_upper section) draw each control
  point's interlocking limits and name, and the overall sheet a bar per control point (no car count). A control
  point may list only switches on one band, so a crossover whose halves sit on two bands (127, 131) lists the half
  on the control point's level. The bars make the page taller; at the smaller scale the plugin's label check counts 7 milepost labels against their
  markers (draft, 2026-11-15; labels are placed before the page is scaled).
- The device master (hartlib.devices): the rows of levels 2 and 3 are this script's (written_by build_device_map.py), and
  so are staging's block and occupancy rows (staging_rows, below). The main and upper rows are the one mapping from
  each main and upper JMRI device to its planned physical part. Per
  row: the user name under ADR-005; jmri_name, the virtual device tables.xml and the CATS desks use now; system_name,
  the planned physical device (LCOS, a DRAFT: the main and upper plant is not reviewed yet). Later
  a physical device is swapped in by this mapping alone, so no JMRI name ever comes from a draft address or from
  drawing order. Placeholder user names change when the owner names the levels.

Blocks: one block process for every level (block_layer.py): OS
blocks, track blocks, halves (block_overrides.csv kind split, every level: 227-241 and staging's K-1 and K-2), helix blocks named
through plan_overrides.json, and parts (the device master's part_of: a piece of track inside another block, by the rule or
block_overrides.csv). Staging's rows, built on the owner's field rows: device_map_staging.py.

Virtual names, from each device's stable identity:
- Turnout "Switch <n>" (and its LCC alias "DCC Switch <n>"): IT:HART:C3:<n>.
- Every block has one occupancy row, its sensor IS:HART:C3:B:<block_key> (hartlib.level_devices: the block name with
  "Track "
  dropped, "OS Switch " shortened to "OS", spaces to "_": IS:HART:C3:B:107-109, IS:HART:C3:B:107_Loop_2,
  IS:HART:C3:B:OS225b). Its system_name is the planned detector (M2S), or empty: NOT_WIRED for a detector planned
  but not on a node yet, NO_DETECTOR for a block that has none planned (dark until decided). Those facts are columns
  of their own (hartlib.railroad.DEVICE_FACTS): an occupancy row's `blocks` (its block) and `detector` (planned,
  not_wired or none), a mast row's `switch`, `facing` and `protects`; the notes and comment are text for people.
- Head "Head <mast>[ Top|Bottom]": hartlib.level_masts.head_name, the level's prefix data (IH:HART:C3:108LA); mast
  IF$shsm:basic:<type>(<head>)(<head>) over those heads.
- Feedback rows have no JMRI device of their own (assignment none: a turnout's feedback is DIRECT until the plant is
  wired).
- Block "<name>" (parts too, not a helix block, whose beans are staging's): jmri_name IB:C3:<nnnn> and layout_block
  ILB<1000 + nnnn>, today's numbers copied from block_numbering.csv (hartlib.block_numbering; kept until the
  levels are wired for good); hartlib.tables_build.master_beans names the beans from the rows.
- What a main and upper bean takes from its row beyond its names (device_map_rows.bean_cells): `start`, inactive for a detector and closed or thrown for a turnout (startup_thrown:
  thrown where the main route runs through leg C), which the startup LogixNG sets, and `bean_comment`, the bean's
  JMRI comment in staging's form.

Naming rules (ADR-005 grammar, LCOS conventions):
- Turnout "Switch <n>" (a crossover is one turnout), feedback "FB Switch <n> N|R", OS block "OS Switch <n>" (one per
  number, as the Layout Editor trial has it), occupancy "BS <block without Track>". A double crossover is four OS
  blocks, one per corner, "OS Switch <n>a" to "<n>d" by its Layout Editor corner A to D (the
  plugin's double_corners maps the schematic's legs to the corners): with one block, or
  two, JMRI 5.16 records a through path between the two legs on one side (LayoutBlock.addThroughPath keeps a pair
  whose turnout lists match both ways) and Signal Mast Logic discovery pairs masts across it (226RA to 224LB). Corner
  a keeps the switch's detector; b to d have none on a node until wired (NOT_WIRED). A mast at a double crossover
  protects its own leg's corner block ("home signal from Track X into OS Switch <n><corner>").
- Track "Track <a>-<b>" from its end switches, "Track <n> Spur" to a bumper, "Track <n> Loop" back to the same
  switch; parallel tracks between the same ends take " 1", " 2" in plan order (mast_rule.plan_order: by their ends' plan legs). A track up the helix is its helix
  block (plan_overrides.json: Track Helix Outer from 131A, Track Helix Inner from 131B), one JMRI block with the staging
  track below it: the staging device map names its staging piece, and the Layout Editor build
  binds this map's occupancy row to the one staging block. Its level_switch must be the switch the drawing gives, and
  its `stop` stays empty: the Dispatcher stations are parked with the stations topic (owner, 2026-11-22;
  docs/parked/UNPARK.md has the helix stop rule for the day they return).
  A balloon loop is two blocks, "Track <n> Loop 1" from the switch's leg B and "Track <n> Loop 2" from leg C, parted
  at the turnback halfway round: JMRI keys a mast by its facing and protected blocks
  (LayoutBlockManager.getFacingBean returns one), so two masts facing one loop block into one OS block would leave
  one of them out of Signal Mast Logic discovery. Loop 1 keeps the loop's detector; Loop 2's is not on a node until it is
  wired (NOT_WIRED), so no node or input assignment moves.
  A link, a track under block_layer.LINK_CM (50 cm) between two switches, is a part (the device master's part_of) of an OS
  block (step 5 part 2): the lower-numbered switch's, or, where a home mast stands at a switch's
  points facing it, the OS block at its other end (the block boundary is at the mast). On main and upper a part is
  still a JMRI block and layout block of its own, drawn on the panel, whose occupancy sensor is its OS block's
  (hartlib.tables_build.master_beans): no occupancy row or detector of its own. A double crossover's link is part of the corner
  block of its leg; a part's row is on the level of its OS block's row (127-131 2, drawn on the upper band, in the
  main level's OS Switch 127).
- Detection on the main line only: main-route tracks and the OS blocks of control point
  switches get a planned detector; yard and industry tracks and the OS blocks of switches in no control point
  get none (their virtual sensor stays, NO_DETECTOR).
- Masts: the one mast process every level uses (mast_plan.plan, owner 2026-11-20; plan_masts): home masts,
  intermediates, and virtual masts (hidden, IF$vsm, ordinals from 2001 on main and 3001 on upper) only where a
  visible mast's route reaches a buffer stop first. What follows is the home mast rule as it stands here.
- Home signals: one mast where each track from outside a control point meets one of its switches; none on spurs
  or yard tracks that end at a bumper, and none where no route the mast would govern reaches another signal (every
  route ends at a bumper or in dark track: mast_rule.reaches_signal, owner 2026-11-19, which leaves out 125B's mast
  into Switch 129's spurs). "Mast <n+1><L|R>", L for a westbound train (ADR-005), A/B when one number and direction
  has two. Two heads (Top and Bottom) when a route the mast governs meets facing points inside its
  control point before the next signal (mast_rule.facing_on_route), else one; high (searchlight) facing from running
  track, a dwarf (low) from a yard, lead or siding. East is the schematic's (ADR-022 amendment: away from the helix on these levels).
- LCOS packed IDs are node * 100 + UID (external/lcos-bridge): blocks UID 0-7 (BS, "Node: n Block: k+1"), turnouts
  8-15 (M2T, "Node: n Turnout: k"), signals 32-47 (IH, "Node: n Signal: k"), inputs from 67 (M2S, feedback N then R
  per turnout, "Node: n Sensor: k"). A control point's turnouts stay on one node; switches in no control point
  follow, area by area. Heads come last: every two-head mast of every group before any one-head mast, each on the
  first 5V board with room, so a group's heads may land off its home node, on another node of its area, when the
  home node is full, and draft head outputs may reshuffle from one build to the next (nothing on
  the main and upper levels is wired yet).
- wiring.csv's turnout, fb and head rows of main and upper: a control point wired and frozen
  (tools/wiring/freeze_wiring.py). Each frozen device keeps its node, LCOS number and pins on every
  build (Nodes.freeze), and the rule hands them to nothing else; its detectors are pins (read_pins: an OS block by its
  name, a helix block by its name, a track by its end switches). The JMRI names stay virtual: freezing fixes the
  wiring only.
- Hand lists keyed by end switches (block_overrides.csv, with a level column, and wiring.csv's main and upper detectors; source-data row 5; running
  track and exit dwarfs are rules since 2026-11-20, mast_rule.running_tracks and signalled_spurs): columns switch_a,
  switch_b (the owner's switch numbers, lower first; switch_b blank for a spur, whose other end is a
  bumper), `parallel` (1, 2 in mast_rule.plan_order, only where two tracks run between the same switches) and, in the pins,
  `half` (1, 2: a balloon loop or split track, half 1 at the lower-numbered switch). Each row is resolved to the
  generated track at build time (mast_rule.resolve_track), so a renumber moves rows with their tracks; a pair that
  matches no track, or two tracks with no `parallel`, stops the build naming the file, line and candidates. A pin on a
  helix block gives the owner's block name instead (no switches).
- DCC addresses continue from staging's last (119): 120 up in switch-number order, main level first (owner,
  2026-11-15). Each turnout also gets its LCC alias "DCC Switch <n>" (MTT<dcc>, same node comment, as staging has).
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA, GRAPHS, INPUTS and the pinned plugin
from mast_rule import (  # noqa: E402,F401  the track and mast rule, re-exported for the builders
    LOOP_HALF, TAU, MapError, band_levels, end_label, end_ref, facing_on_route, helix_blocks, helix_tags, masts,
    TRACK_KEY_COLUMNS, key_problem, read_helix_tracks, resolve_track, track_names, tracks)
import block_layer  # noqa: E402  the one block process for every level
import device_map_masts  # noqa: E402  staging's mast and head rows
import mast_plan  # noqa: E402  the one mast process for every level
import mast_rule  # noqa: E402  read_block_splits, OVERRIDES_NAME
import le_common  # noqa: E402  bare: a switch label as the plan prints it
from hartlib import block_numbering, device_ids, devices, layer_files, level_devices, level_masts, railroad, wiring  # noqa: E402,E501  names, facts, the master
from device_map_inputs import (  # noqa: E402,F401  the readers; re-exported: callers read them from this module
    CPS, NODES, OS_BLOCK, PINS, SOURCES, STATIONS, UID, WIRING, Places, StagingPin, frozen_wires,
    helix_pins, loop_placeholder, read_places, read_staging_pins, staging_nodes, wiring_rows)
from device_map_staging import (  # noqa: E402,F401  staging's rows; re-exported: callers read them from this module
    BEAN_NAME, FIELD_LAYERS, PART_BLOCK_FIRST, STAGING_SHEET, WIRED_LAYERS, alias_note, field_row, helix_ends,
    level_keys, level_trials, line_cp, new_spare, part_bean_names, part_row, piece_trials, staging_field, staging_layer,
    staging_cps, staging_keys, staging_part_names, staging_rows, staging_switches, staging_trials, staging_wired_rows,
    taken_bean_names, wire_block, wire_occupancy)
from device_map_nodes import (  # noqa: E402,F401  the LCOS node allocator; re-exported for callers
    CAP, MAX_OU, STAGING_LEVEL, NoBoardRoom, Nodes)
from device_map_rows import (  # noqa: E402,F401  every level's rows
    Wired, bean_cells, device_row, follow_swaps, owner_over, switch_device_rows)
from device_map_schematic import (  # noqa: E402,F401  the drawing's tracks; re-exported: callers read them here
    block_overrides, check_helix_ends, corner_blocks_of, dx_corners, helix_tracks, home_and_posts,
    labels_by_level, line_role, loop_halves, main_upper_layer, named_tracks, overrides_keys, read_pins, split_edges,
    split_tracks, xover_corners)

SWITCHES = SOURCES.switches                     # switches.csv: its main and upper rows give the local switches' areas
OVERRIDES = SOURCES.plan_overrides               # plan_overrides.json, the owner's hand edits (read only)
GENERATED = layer_files.path(layer_files.GENERATED, OVERRIDES.parent)   # plan_generated.json: this writes its main_upper keys
SHEET = railroad.PlanOverrides.SHEET
OUT = SOURCES.devices                             # the device master, whose levels 2 and 3 this script writes
LEVELS = band_levels(layer_files.read("plan_overrides", SHEET, OVERRIDES.parent))     # {band title: level} of main and upper

def device_files() -> devices.Files:
    """The master and its generated files as main() writes them: OUT, as it is when it runs (a test may patch it)."""
    return devices.Files.under(OUT.parent)


def sources() -> railroad.Sources:
    """The files main() reads and writes: the module's paths as they are when it runs (a test may patch them)."""
    return railroad.Sources.under().but(interlockings=CPS, lcos_nodes=NODES, switches=SWITCHES,
                                        plan_overrides=OVERRIDES, devices=OUT)

COLUMNS = list(railroad.DEVICE_COLUMNS)
DCC_FIRST = 120                       # staging uses 100-119 (MTT100-MTT119); the owner continues from 120
VIRTUAL_TURNOUT = level_devices.TURNOUT_PREFIX   # + switch number: the internal turnout the panels and desks use
occupancy_user = level_devices.occupancy_user
NOT_WIRED = "detector planned, not wired yet: no node or input (owner, 2026-11-16)"
HEAD_NOT_WIRED = "head planned, no board room on the draft plant: placed when the wiring plan is reworked (owner, 2026-11-19)"
NO_DETECTOR = "no detector planned: dark until decided"


# The switch number of a schematic label ("129A" -> "129", "223*" -> "223") and the natural sort key, defined once in
# hartlib.railroad; the names stay here because build_layout_le.py and build_cats_panel.py import them from this module.
base = railroad.switch_number
natural = railroad.natural


def block_sensor(block: str) -> str:
    """The virtual occupancy sensor of a main or upper block (hartlib.level_devices.block_sensor); MapError on a
    name that gives no clean key."""
    try:
        return level_devices.block_sensor(block)
    except ValueError as exc:
        raise MapError(str(exc)) from exc


def head_name(user: str, level) -> str:
    """The internal system name of a head of `level` (hartlib.level_masts.head_name: the level's prefix is data,
    HEAD_PREFIXES; every level's builder names its heads so); MapError on a name out of the
    grammar."""
    try:
        return level_masts.head_name(user, int(level))
    except ValueError as exc:
        raise MapError(str(exc)) from exc


def band_level(title: str) -> int | None:
    """The level (2 or 3) of a main or upper band by its title, from the plan overrides' `level`s; None for staging."""
    return mast_rule.band_level(title, LEVELS)


def load_cps(path: Path = CPS) -> list[railroad.Interlocking]:
    """The main and upper interlockings, their control points (hartlib.railroad.read_interlockings: every switch in at
    most one)."""
    try:
        return railroad.read_interlockings(path, railroad.LEVEL_NUMBERS)
    except railroad.FactsError as exc:
        raise MapError(str(exc)) from exc


MastKind = Literal["home", "intermediate", "virtual"]    # mast_plan's three lists of masts


# ---------------------------------------------------------------- the map


def plan_masts(bands, joined, runs, found, cp_of: dict, corners: dict | None
               ) -> tuple[dict, dict, set, block_layer.Layer]:
    """(mast_plan.plan's masts of the main and upper levels, the double crossovers' corner blocks, the split track
    names, the block layer): the one mast process over this level's block layer (main_upper_layer) and the owner's
    block splits. Each home mast gains `facing`, the block of the track it faces (its track's: a part is a JMRI block
    of its own). MapError on a double crossover with no corners given."""
    corner_blocks = corner_blocks_of(bands, corners)
    split = split_edges(found=found)
    home, posts = home_and_posts(bands, joined, found, LEVELS, cp_of, corner_blocks, set(split.values()))
    lay = main_upper_layer(bands, runs, found, split, corner_blocks, posts)
    got = mast_plan.plan(bands, joined, found, levels=LEVELS, cp_of=cp_of, layer=lay.bands, cm=lay.cm,
                         corner_blocks=corner_blocks, split=set(split.values()), home=home)
    for m in got["home"]:
        m["facing"] = m["track"]
    return got, corner_blocks, set(split.values()), lay


def master_virtual_names(files: devices.Files | None = None) -> dict:
    """{mast id: (user name, system name)} of the main and upper virtual masts as this script last wrote them (each
    keeps its ordinal by its ID, so a mast whose letter changed keeps its system name): name memory, its one
    read-back of its own output (devices.allocated_names)."""
    return {r["id"]: (u, r["jmri_name"])
            for u, r in devices.allocated_names(("2", "3"), "mast", files=files or device_files()).items()
            if level_masts.virtual_ordinal(r["jmri_name"])}


def owner_mast_names(files: devices.Files | None = None) -> dict:
    """{mast id: the owner's user name} of the main and upper masts devices_field.csv names (by ID, hartlib.devices
    .KEY): the owner's name wins, and the mast's heads are named from it."""
    return {f["id"]: f["user_name"] for f in devices.field_index(files or device_files()).values()
            if f["level"] in ("2", "3") and f["layer"] == "mast" and f["user_name"]}


def virtual_memory(virtual: list[dict], old: dict) -> dict[int, dict]:
    """{level: {"Mast <name>": system name}} of the virtual masts' old system names (`old`: master_virtual_names,
    by ID), each under its mast's name now (`virtual`: the planned virtual masts, each with its `id` and final
    `name`), an old ID the rule no longer places under its old name (mast_plan.virtual_system_names asks for it in
    retired_virtual_masts.csv). MapError when that old name is now another mast's."""
    now = {m["id"]: f"Mast {m['name']}" for m in virtual}
    out, bad = {}, []
    for ident, (user, system) in old.items():
        key = now.get(ident, user)
        mine = out.setdefault(level_masts.virtual_level(system), {})
        if key in mine or (ident not in now and key in now.values()):
            bad.append(f"{key}: the virtual mast of id {ident} had that name, and another mast now has it: add "
                       f"{user} ({system}) to retired_virtual_masts.csv under another name, or give the mast its old "
                       "ID back")
        mine[key] = system
    if bad:
        raise MapError("; ".join(bad))
    return out


def check_frozen_cps(rows: list[dict], cps: frozenset, held_devices: set, held_blocks: set) -> None:
    """A control point wiring.csv holds (frozen) is read from it and proposed for no more: stop on a device the rule
    gave one of its rows (a turnout, feedback or head on a node, or a detector input) that wiring.csv does not
    hold. A switch added to a frozen control point is wired and frozen again (make wiring-freeze)."""
    bad = []
    for r in rows:
        if devices.place(r).split(devices.LIST)[0] not in cps or not r["node"] or r["role"] == "lcc_alias":
            continue
        if r["layer"] in ("turnout", "fb", "head") and (r["layer"], r["user_name"]) not in held_devices:
            bad.append(f"{r['layer']} {r['user_name']}")
        elif r["layer"] == "occupancy" and r["system_name"] and r["blocks"] not in held_blocks:
            bad.append(f"occupancy of {r['blocks']}")
    if bad:
        raise MapError(f"{PINS.name}: control point(s) {', '.join(sorted(cps))} are frozen, but the rule proposes "
                       f"{', '.join(sorted(bad))} for them: wire and freeze again (make wiring-freeze CP=...)")


DeviceMapRow = dict[str, Any]   # a device-map row (device_map_rows.device_row); csv_text writes it under COLUMNS
CORNER = "xover_corner"         # a double crossover's corner block and its occupancy row
LAYER_ORDER = {"turnout": 0, "fb": 1, "block": 2, "occupancy": 3, "mast": 4, "head": 5}   # build()'s row order


class MapBuild(NamedTuple):
    """What build()'s stages share: the plan facts read once at the start, the node allocator, and the rows made so
    far. `rows`, `block_ids`, `home` and `area_of` are filled in place, stage by stage, in build()'s order (a node's
    12V turnout boards come before its 5V head boards)."""
    bands: list[Any]                    # the plugin's bands
    by_level: dict[int, set[str]]       # labels_by_level: {level: the switch labels drawn on it}
    switches: dict[str, railroad.MainUpperSwitch]   # every main and upper switch, by number
    cp_of: dict[str, str]               # {switch: its control point}
    loc: dict[str, railroad.MainUpperSwitch]        # the switches in no control point (level, area, notes)
    found: list[dict[str, Any]]         # named_tracks: the main and upper tracks
    corner_blocks: dict[str, dict[str, str]]        # {double crossover: {schematic leg: corner block}}
    split_names: set[str]               # the split tracks' names
    lay: block_layer.Layer
    trials: dict[str, str]              # {block: trial_name} (level_keys)
    track_ids: dict[str, str]           # {block: device ID} (level_keys)
    places: Places
    helix: dict[str, Any]               # read_helix_tracks
    nodes: Nodes
    os_pin_level: dict[str, int]        # {OS block pinned by its name: the level its wiring.csv row gives}
    dcc: dict[str, int]                 # {switch: its DCC address}
    rows: list[DeviceMapRow]
    block_ids: dict[tuple[str, str], str]   # (level, block) -> its device ID, for its detector and the masts facing it
    home: dict[str, int]                # switch -> its turnout's node
    area_of: dict[str, tuple[int, str]]     # switch -> (level, area)


def build(bands: list[Any], joined: Any, runs: Any, overrides: Mapping[str, Any],
          cps: Sequence[railroad.Interlocking], node_rows: Iterable[Any], local: Iterable[Any] = (),
          corners: dict[str, Any] | None = None, helix: dict[str, Any] | None = None,
          pins: dict[str, tuple[int, int]] | None = None, places: Places | None = None,
          virtual_names: dict[str, tuple[str, str]] | None = None, frozen: list[Any] | None = None,
          owner: dict[str, str] | None = None) -> tuple[dict[str, Any], list[DeviceMapRow], list[DeviceMapRow]]:
    """(control_points, device map rows, the parts' master rows: links inside an OS block, part_row). `local`: the
    switches in no control point (the local switches of switches.csv rows). Every switch on the main and upper bands
    must be in exactly one of the two. `corners`: dx_corners, needed when a band has a double crossover. `helix`:
    read_helix_tracks (None: plan_overrides.json; {}: no helix tracks); `pins`: read_pins (None: wiring.csv's
    detectors, resolved against the tracks found here); `virtual_names`: {mast id: (user name, system name)} of the
    virtual masts that have one already (None: master_virtual_names); `frozen`: frozen_wires (None: wiring.csv's);
    `places`: read_places (None: stations.csv's and interlockings.csv's), the cp of every line block (line_cp);
    `owner`: {mast id: the owner's name} (None: owner_mast_names), which a mast and its heads take."""
    helix = helix_tracks() if helix is None else helix
    places = read_places() if places is None else places
    by_level = labels_by_level(bands)
    cp_keys = overrides_keys(cps, by_level)
    switches, cp_of, loc = _switch_facts(cps, local, by_level)
    found = named_tracks(bands, joined, runs, overrides, helix)
    check_helix_ends(bands, joined, found, helix)
    planned, corner_blocks, split_names, lay = plan_masts(bands, joined, runs, found, cp_of, corners)
    if lay.inside:          # the main and upper drawing gives each strand one block: a piece there is a part
        raise MapError(f"{mast_rule.OVERRIDES_NAME} keeps {', '.join(sorted(lay.inside))} inside an OS block on "
                       "main or upper, whose drawing gives each strand one block; leave inside empty (a part)")
    trials, track_ids = level_keys(bands, joined, lay)
    os_pin_level: dict[str, int] = {}
    if pins is None:
        pins = read_pins(found=found, split=split_names, ids={v: k for k, v in track_ids.items()})
        os_pin_level = {w.device: w.level for w in wiring_rows() if w.kind == "detector" and w.device
                        and OS_BLOCK.fullmatch(w.device)}
    nodes = Nodes(node_rows)
    nodes.pin(pins)
    held_wires = frozen_wires() if frozen is None else frozen
    nodes.freeze(held_wires)
    frozen_cps = frozenset(cp for w in held_wires if (cp := wiring.frozen_cp(w)))
    held_devices, held_blocks = {(w.kind, w.device) for w in held_wires}, set(pins)
    dcc = {s: DCC_FIRST + i for i, s in enumerate(sorted(set(cp_of) | set(loc), key=natural))}
    st = MapBuild(bands, by_level, switches, cp_of, loc, found, corner_blocks, split_names, lay, trials, track_ids,
                  places, helix, nodes, os_pin_level, dcc, [], {}, {}, {})
    _switch_and_os_rows(st, cps)
    part_rows = _part_rows(st)
    _track_rows(st)
    ms = planned["home"] + [dict(m, heads=1, kind="one-searchlight", switch="", intermediate=True)
                            for m in planned["intermediates"]]
    vnames = _name_masts(st, ms, planned["virtual"], owner_mast_names() if owner is None else owner,
                         virtual_names)
    _head_rows(st, cps, ms)
    _virtual_mast_rows(st, planned["virtual"], vnames)
    nodes.check_boards()
    nodes.check_pins()
    nodes.check_frozen()
    check_frozen_cps(st.rows, frozen_cps, held_devices, held_blocks)
    check_virtual(st.rows)
    assign_ports(st.rows)
    st.rows.sort(key=lambda r: (r["level"], LAYER_ORDER[r["layer"]], natural(r["user_name"])))
    return cp_keys, st.rows, part_rows


def _switch_facts(cps: Sequence[railroad.Interlocking], local: Iterable[Any], by_level: Mapping[int, set[str]]
                  ) -> tuple[dict[str, railroad.MainUpperSwitch], dict[str, str], dict[str, railroad.MainUpperSwitch]]:
    """(every main and upper switch, {switch: its control point}, the switches in no control point). MapError on a
    switch the bands draw that is in neither."""
    try:
        switches = railroad.join_main_upper(cps, local, SWITCHES.name)
    except railroad.FactsError as exc:
        raise MapError(str(exc)) from exc
    cp_of = {s: sw.cp for s, sw in switches.items() if sw.cp}
    loc = {s: sw for s, sw in switches.items() if not sw.cp}
    on_bands = {base(lb) for labels in by_level.values() for lb in labels}
    missing = sorted(on_bands - set(cp_of) - set(loc), key=natural)
    if missing:
        raise MapError(f"switch {', '.join(missing)} is in no control point and not a local switch (an area) "
                       f"in {SWITCHES.name}")
    return switches, cp_of, loc


def _trial_of(st: MapBuild, name: str) -> str:
    """A block's trial name (level_keys); MapError when the block layer draws it on no strand."""
    if name not in st.trials:
        raise MapError(f"{name}: the block layer draws it on no strand, so it has no trial name")
    return st.trials[name]


def _track_id(st: MapBuild, name: str) -> str:
    """A block's device ID, from the same plan ends as its trial name: no trial name, no ID (MapError)."""
    _trial_of(st, name)
    return st.track_ids[name]


def _add(st: MapBuild, level: Any, cp: str, layer: str, user: str, system: str = "", node: Any = "",
         comment: str = "", trial: str = "", notes: str = "", dcc: Any = "", jmri: str = "", *, role: str,
         ident: str, **facts: Any) -> None:
    """A device-map row with the role (hartlib.devices.ROLES) its caller says it has: no role is read off a name;
    and its device ID (`ident`, hartlib.device_ids), from the plan facts its caller holds. A block row's ID is kept
    in st.block_ids for its detector and the masts facing it."""
    st.rows.append(device_row(level, cp, layer, user, system, node, comment, trial, notes, dcc, jmri, role=role,
                              ident=ident, **facts))
    if layer == "block":
        st.block_ids[(str(level), user)] = ident


def _occupancy(st: MapBuild, level: Any, cp: str, block: str, system: str = "", node: Any = "", comment: str = "",
               notes: str = "", *, role: str) -> None:
    """The occupancy row of `block`, whose role (`role`) it shares: its virtual sensor (jmri_name), the block it
    serves and its detector: planned on an input (`system`, M2S), planned with no input yet (NOT_WIRED) or none
    planned (NO_DETECTOR). Its ID is its block's (det:<block id>): add the block row first."""
    detector = "planned" if system else {NOT_WIRED: "not_wired", NO_DETECTOR: "none"}.get(notes)
    if detector is None:
        raise MapError(f"occupancy of {block}: no detector and no reason why ({notes!r})")
    _add(st, level, cp, "occupancy", occupancy_user(block), system, node, comment, notes=notes,
         jmri=block_sensor(block), blocks=block, detector=detector, role=role,
         ident=device_ids.det_id(st.block_ids[(str(level), block)]))


def _switch_and_os_rows(st: MapBuild, cps: Sequence[railroad.Interlocking]) -> None:
    """Every switch's turnout, alias and feedback rows, control points first and then the local switches, then
    every switch's OS block rows: turnouts first, as a node's 12V boards come before its 5V boards."""
    for cp in cps:
        loose = [s for s in cp.switches if ("turnout", f"Switch {s}") not in st.nodes.frozen]
        node = st.nodes.pick(cp.level, cp.area, "turnout", len(loose)) if loose else None
        for s in cp.switches:
            _switch_rows(st, cp.level, cp.area, cp.name, s, node)
    for s in sorted(st.loc, key=natural):       # no control point: turnout and feedback, no signals or detection
        r = st.loc[s]
        node = st.nodes.pick(r.level, r.area, "turnout") if ("turnout", f"Switch {s}") not in st.nodes.frozen else None
        _switch_rows(st, r.level, r.area, "", s, node, "no control point: " + r.notes)
    for cp in cps:
        for s in cp.switches:
            _os_rows(st, cp.level, cp.area, cp.name, s, cp.name)
    for s in sorted(st.loc, key=natural):
        _os_rows(st, st.loc[s].level, st.loc[s].area, "", s, st.loc[s].area, detect=False)


def _switch_rows(st: MapBuild, lv: int, area: str, name: str, s: str, node: int | None, note: str = "") -> None:
    """A switch's turnout, LCC alias and feedback rows (device_map_rows.switch_device_rows, the one maker, as
    staging's): a frozen device's own wiring.csv values, else the node's next free turnout and sensor inputs. Main
    and upper bind the virtual turnout. Sets st.home and st.area_of for the switch."""
    frozen = st.nodes.take_frozen("turnout", f"Switch {s}")    # wired and frozen (wiring.csv): its own values
    if frozen:
        node, k, packed = frozen.node, frozen.index, frozen.node * 100 + UID["turnout"] + frozen.index
        where = frozen.wiring_text
    else:
        if node is None:            # build() picks a node for every control point with a switch not frozen
            raise MapError(f"Switch {s}: not frozen in {PINS.name}, and no node was picked for its turnout")
        k, packed = st.nodes.take(node, "turnout")
        where = f"Node: {node} Turnout: {k}"
    st.home[s], st.area_of[s] = node, (lv, area)
    fbs = {}
    for nr in "NR":
        fb = st.nodes.take_frozen("fb", f"FB Switch {s} {nr}")
        if fb:
            fbs[nr] = Wired(fb.address, fb.node, fb.wiring_text)
            continue
        fnode = st.nodes.pick(lv, area, "sensor", prefer=[node])
        kk, pp = st.nodes.take(fnode, "sensor")
        fbs[nr] = Wired(f"M2S{pp}", fnode, f"Node: {fnode} Sensor: {kk}")
    st.rows.extend(switch_device_rows(
        lv, name, s, [lb for labels in st.by_level.values() for lb in labels if base(lb) == s],
        Wired(f"M2T{packed}", node, where), fbs, st.dcc[s], jmri=VIRTUAL_TURNOUT + s,
        alias_notes="LCC alias of the MQTT turnout (ADR-005)", notes=note))


def _os_rows(st: MapBuild, lv: int, area: str, name: str, s: str, comment: str, detect: bool = True) -> None:
    """A switch's OS block row and its occupancy row; a double crossover's one per corner, corner a detected.
    `detect` False: no detector (off the main line)."""
    if s in st.corner_blocks:
        _corner_rows(st, lv, area, name, s, comment, detect)
        return
    block = f"OS Switch {s}"
    if not detect:
        _add(st, lv, name, "block", block, "", "", comment, block, "no detector: off the main line", role="os",
             ident=device_ids.os_id(s))
        _occupancy(st, lv, name, block, notes=NO_DETECTOR, role="os")
        return
    bnode, k, packed = st.nodes.detector(block, lv, area, st.home[s], st.os_pin_level)
    _add(st, lv, name, "block", block, "", bnode, comment, block, role="os", ident=device_ids.os_id(s))
    _occupancy(st, lv, name, block, f"M2S{packed}", bnode, f"Node: {bnode} Block: {k + 1}", role="os")


def _corner_rows(st: MapBuild, lv: int, area: str, name: str, s: str, comment: str, detect: bool) -> None:
    """A double crossover's block per corner, each corner's ID by the schematic leg it serves (xover_corners: {leg:
    block}), in block name order: corner a keeps the switch's detector, the others are wired later (NOT_WIRED)."""
    for leg, block in sorted(st.corner_blocks[s].items(), key=lambda kv: kv[1]):
        ident = device_ids.os_id(s, leg)
        note = f"corner {block[-1].upper()} of the double crossover"
        if not detect:
            _add(st, lv, name, "block", block, "", "", comment, block, note + ", no detector: off the main line",
                 role=CORNER, ident=ident)
            _occupancy(st, lv, name, block, notes=NO_DETECTOR, role=CORNER)
        elif not block.endswith("a"):
            _add(st, lv, name, "block", block, "", "", comment, block, note, role=CORNER, ident=ident)
            _occupancy(st, lv, name, block, notes=NOT_WIRED, role=CORNER)
        else:
            bnode, k, packed = st.nodes.detector(block, lv, area, st.home[s], st.os_pin_level)
            _add(st, lv, name, "block", block, "", bnode, comment, block, note, role=CORNER, ident=ident)
            _occupancy(st, lv, name, block, f"M2S{packed}", bnode, f"Node: {bnode} Block: {k + 1}", role=CORNER)


def _part_rows(st: MapBuild) -> list[DeviceMapRow]:
    """The master rows of the parts (links inside an OS block), each on the level of its OS block's row, its
    switch's (a link between the halves of the crossovers 127 and 131 drawn on the upper band is in a main level OS
    block). MapError on a piece at one end of a track, or a part of no main or upper switch's OS block."""
    out = []
    for name, part in sorted(st.lay.parts.items(), key=lambda kv: natural(kv[0])):
        if name != part["track"]["name"]:
            raise MapError(f"{name}: a piece at one end of a main or upper track ({part['why']}); the main and upper "
                           "drawing gives each strand one block, so give the whole track to an OS block")
        m = re.fullmatch(r"OS Switch (\d+)[a-d]?", part["part_of"])
        if not m or m.group(1) not in st.switches:
            raise MapError(f"{name} (level {part['level']}) is part of {part['part_of']}, the OS block of no main or "
                           "upper switch")
        lv = str(st.switches[m.group(1)].level)
        out.append(dict(part_row(lv, name, part, _trial_of(st, name), _track_id(st, name)),
                        cp=line_cp(name, lv, part["track"], st.places)))
        st.block_ids[(lv, name)] = _track_id(st, name)
    return out


def _track_rows(st: MapBuild) -> None:
    """Each main and upper track's block row and occupancy row (a balloon loop's or a split track's, one per half),
    but a part's. MapError on a track ending at a switch of neither level."""
    for t in sorted(st.found, key=lambda t: natural(t["name"])):
        sws = [v for k, v in t["ends"] if k == "sw"]
        stray = [s for s in sws if s not in st.area_of]
        if stray:
            raise MapError(f"{t['name']} ends at switch {', '.join(stray)}, which is on neither the main nor the "
                           "upper level")
        if t["name"] in st.lay.parts:               # a link inside an OS block: its part row, no block or detector
            continue
        split = t["name"] in st.split_names
        for half in sorted(LOOP_HALF.values()) if (t["loop"] or split) else [None]:
            _track_half_rows(st, t, sws, half, split)


def _track_half_rows(st: MapBuild, t: dict[str, Any], sws: list[str], half: int | None, split: bool) -> None:
    """The block row and occupancy row of track `t` (or of its `half`): its detector the owner's pin, none off the
    main line, not wired yet for a second half, else the next free block input of a node on the track's own level
    first. MapError on a pin the rule gives no detector."""
    ends_cp = sorted({st.cp_of[v] for v in sws if v in st.cp_of}, key=natural)
    detect = t["main"] and sws
    name, role = loop_placeholder(t["name"], half), line_role(t, half)
    cp = line_cp(name, t["level"], t, st.places, helix_ends(st.helix))
    cm = round(t["cm"] / 2, 1) if half else t["cm"]
    note = f"{cm} cm" + ("" if t["main"] else " no detector: off the main line")
    if half and split:
        note += f", half {half} of the split track ({mast_rule.OVERRIDES_NAME})"
    elif half:
        note += f", half of the balloon loop from leg {'BC'[half - 1]}"
    _add(st, t["level"], cp, "block", name, "", "", " / ".join(ends_cp), _trial_of(st, name), note, role=role,
         ident=_track_id(st, name))
    pinned = st.nodes.take_pinned(name)
    if not detect:
        if pinned:
            raise MapError(f"{PINS.name} pins a detector for {name}, which the rule gives none (off the main line)")
        _occupancy(st, t["level"], cp, name, notes=NO_DETECTOR, role=role)
        return
    if pinned:                                            # the owner's input (wiring.csv)
        bnode, k, packed = pinned
    elif half and half > 1:                               # wired later: no node or input yet
        _occupancy(st, t["level"], cp, name, notes=NOT_WIRED, role=role)
        return
    else:
        sws.sort(key=lambda s: st.area_of[s][0] != t["level"])      # a node on the track's own level first
        lv, area = t["level"], st.area_of[sws[0]][1]                 # the track's level, its switch's area
        bnode = st.nodes.pick(lv, area, "block", prefer=[st.home[s] for s in sws if st.area_of[s][0] == lv])
        k, packed = st.nodes.take(bnode, "block")
    _occupancy(st, t["level"], cp, name, f"M2S{packed}", bnode, f"Node: {bnode} Block: {k + 1}", role=role)


def _facing_id(st: MapBuild, level: Any, block: str) -> str:
    """The device ID of the block `block` a mast faces: its row on the mast's level, else its one row on another
    level (a helix block, a link drawn on the other band). MapError when it has none or several there."""
    got = st.block_ids.get((str(level), block))
    if got is None:
        other = [v for (_lv, b), v in st.block_ids.items() if b == block]
        if len(other) != 1:
            raise MapError(f"a mast faces {block}, which has {len(other)} block rows: no device ID to name it by")
        got = other[0]
    return got


def _mast_id(st: MapBuild, m: Mapping[str, Any], kind: MastKind) -> str:
    """A mast's device ID (hartlib.device_ids): a home mast's by its switch label, leg and way, others' by block."""
    if kind != "home":
        return device_ids.block_mast_id(_facing_id(st, m["level"], m["facing"]), m["dir"])
    label = le_common.bare(st.bands[m["band"]][1]["nodes"][m["node"]].get("label"))
    return device_ids.home_mast_id(label, m["leg"], m["dir"])


def _name_masts(st: MapBuild, ms: list[dict[str, Any]], virtual: list[dict[str, Any]], owner: Mapping[str, str],
                old_names: dict[str, tuple[str, str]] | None) -> dict[str, str]:
    """Every mast's ID, then the owner's name by it (devices_field.csv): a mast and its heads take it, as on staging
    (device_map_masts.owner_names); a virtual mast's needed_by follows the renames. Returns {virtual mast name: its
    system name}, each level's ordinals from its own thousand (hartlib.level_masts); `old_names`: build()'s
    virtual_names (None: master_virtual_names). MapError on an owner's name out
    of the grammar or two masts with one name."""
    renamed = {}
    kinds: list[tuple[dict[str, Any], MastKind]] = [(m, "intermediate" if m.get("intermediate") else "home")
                                                    for m in ms]
    kinds += [(m, "virtual") for m in virtual]
    for mast, kind in kinds:
        mast["id"] = _mast_id(st, mast, kind)
        name = owner.get(mast["id"], "")
        if name and name != f"Mast {mast['name']}":
            if not level_masts.MAST_USER.fullmatch(name):
                raise MapError(f"{devices.FIELD_FILE}: mast {mast['id']} named {name!r}, not Mast <number>[L|R][letter]")
            renamed[mast["name"]] = mast["name"] = name.removeprefix("Mast ")
    taken = [m["name"] for m in ms + virtual]
    twice = sorted({x for x in taken if taken.count(x) > 1}, key=natural)
    if twice:
        raise MapError(f"two masts are named {', '.join('Mast ' + x for x in twice)} (an owner's name in "
                       f"{devices.FIELD_FILE} takes a generated one?)")
    for m in virtual:
        m["needed_by"] = [renamed.get(x, x) for x in m["needed_by"]]
    old_virtual = virtual_memory(virtual, master_virtual_names() if old_names is None else old_names)
    vnames: dict[str, str] = {}
    for lv in (2, 3):
        vnames |= mast_plan.virtual_system_names([m["name"] for m in virtual if m["level"] == lv], lv,
                                                 old_virtual.get(lv, {}))
    return vnames


def _head_rows(st: MapBuild, cps: Sequence[railroad.Interlocking], ms: list[dict[str, Any]]) -> None:
    """The home and intermediate masts' rows and their heads', last, once every node's boards are known: each
    group's masts in name order, but every two-head mast of every group before any one-head mast (a stable sort),
    since a two-head mast takes six of a board's eight pins and a one-head mast placed first would take a board of
    its own that a two-head mast of the area needs. As many heads are placed as the boards hold; the rest wait as
    HEAD_NOT_WIRED."""
    groups: list[tuple[int, str, str, str]] = [(cp.level, cp.area, cp.name, cp.switches[0]) for cp in cps]
    groups += [(st.loc[s].level, st.loc[s].area, "", s)
               for s in sorted({m["switch"] for m in ms if not m["cp"] and m["switch"]}, key=natural)]
    placing = [(lv, area, name, first, m) for lv, area, name, first in groups
               for m in sorted((m for m in ms if m["cp"] == name and (name or m["switch"] == first)),
                               key=lambda m: natural(m["name"]))]
    for lv, area, name, first, m in sorted(placing, key=lambda g: -g[4]["heads"]):
        _mast_rows(st, lv, area, name, first, m)


def _mast_rows(st: MapBuild, lv: int, area: str, name: str, first: str, m: dict[str, Any]) -> None:
    """One home or intermediate mast's row and its heads' rows: a frozen mast's heads on their wiring.csv node, else
    a node with board room (Nodes.pick_mast, its first switch's node first). With no board room left in the area
    (NoBoardRoom) its heads wait for the wiring plan: no node, their virtual names unchanged. MapError on a mast
    frozen in part, or on two nodes."""
    parts = ["Top", "Bottom"] if m["heads"] == 2 else [""]
    mid = m["id"]
    users = [f"Head {m['name']}" + (f" {part}" if part else "") for part in parts]
    head_ids = {u: device_ids.head_id(mid, device_ids.head_place(i, len(parts))) for i, u in enumerate(users)}
    kind = m["kind"]
    frozen = [st.nodes.take_frozen("head", u) for u in users]
    heads: list[tuple[str, str, Any, Any]]
    try:
        if any(frozen):                          # wired and frozen (wiring.csv): every head of the mast, one node
            if not all(frozen) or len({w.node for w in frozen}) != 1:
                raise MapError(f"Mast {m['name']}: wiring.csv freezes {sum(map(bool, frozen))} of its "
                               f"{len(users)} head(s), or puts them on two nodes; freeze the mast whole")
            hnode = frozen[0].node
            heads = [(u, w.address, w.index, w.port_text) for u, w in zip(users, frozen)]
        else:
            hnode = st.nodes.pick_mast(lv, area, m["heads"], prefer=[st.home[first]])
            heads = [(u, f"IH{packed}", k, f"OU: {board} Ports: {pin},{pin + 1},{pin + 2}")
                     for u, (k, packed, board, pin) in zip(users, st.nodes.place_mast(hnode, m["heads"]))]
        sysname = f"IF$shsm:basic:{kind}(" + ")(".join(h[1] for h in heads) + ")"
    except NoBoardRoom:
        hnode, sysname = "", ""
        heads = [(u, "", None, None) for u in users]
    virtual = f"IF$shsm:basic:{kind}(" + ")(".join(head_name(h[0], lv) for h in heads) + ")"
    if m.get("intermediate"):
        _add(st, lv, name, "mast", f"Mast {m['name']}", sysname, hnode, f"{name or area} | intermediate",
             notes=f"intermediate signal from {m['facing']} into {m['protects']} at MP {m['name'][0]} "
                   f"{m['milepost']:.2f}", jmri=virtual, facing=m["facing"], protects=m["protects"], dir=m["dir"],
             role="intermediate", ident=mid)
    else:
        _add(st, lv, name, "mast", f"Mast {m['name']}", sysname, hnode, f"{name or area} | Switch {m['switch']}",
             notes=f"home signal from {m['track']}" + (f" into {m['protects']}" if m["protects"] else ""),
             jmri=virtual, switch=m["switch"], facing=m["facing"], protects=m["protects"], dir=m["dir"],
             role="home", ident=mid)
    for user, sysn, k, ports in heads:
        if not sysn:                    # no node yet: the mast's comment says where it stands
            where = f"{name or area} | " + (f"Switch {m['switch']}" if m["switch"] else "intermediate")
            _add(st, lv, name, "head", user, "", "", where, notes=HEAD_NOT_WIRED, jmri=head_name(user, lv),
                 role="head", ident=head_ids[user])
            continue
        _add(st, lv, name, "head", user, sysn, hnode, f"Node: {hnode} Signal: {k} | {ports}",
             jmri=head_name(user, lv), role="head", ident=head_ids[user])


def _virtual_mast_rows(st: MapBuild, virtual: list[dict[str, Any]], vnames: Mapping[str, str]) -> None:
    """Each virtual mast's row: a destination for the visible masts' routes, hidden, with no heads and no node."""
    for m in virtual:
        sw = st.switches[m["switch"]]
        system = vnames[m["name"]]
        _add(st, m["level"], sw.cp, "mast", f"Mast {m['name']}", system, "", f"{sw.cp or sw.area} | buffer stop",
             notes=f"virtual bumper mast facing {m['facing']} at its buffer stop: the destination of "
                   f"{', '.join('Mast ' + x for x in m['needed_by'])}",
             jmri=system, facing=m["facing"], dir=m["dir"], role="hidden", ident=m["id"])


WRITER = "build_device_map.py"


def owned_rows(rows, parts, files: devices.Files | None = None) -> tuple[list[dict], list[dict]]:
    """(the main and upper rows with the owner's values over them, the same rows as generated): build()'s `rows`
    (the device-map form) and `parts` (already master rows) in the master's form, each with the field row of its id
    in devices_field.csv over it (device_map_rows.owner_over, hartlib.devices.KEY), as staging's are: on every level
    the owner's name and values go over the generated ones the same way. A virtual JMRI name
    stays the generated one (hartlib.level_devices) unless the owner's row gives a jmri_name (its assignment then
    the name's unless the row gives one: a device swapped in by
    its row, ADR-028). A row with no field row is as build() gave it. master_outputs follows renames over both.
    Every block row but a helix block's gets its bean names (block_beans)."""
    field = devices.field_index(files or device_files())
    made = block_beans([devices.master_row(o, WRITER) for o in rows] + [dict(p) for p in parts])
    out = []
    for r in made:
        f = field.get(devices.key_of(r))
        out.append(owner_over(r, f) if f is not None else r)
    return follow_swaps(out, field), made


def block_beans(rows: list[dict], numbering_path: Path | None = None) -> list[dict]:
    """`rows` (main and upper master rows, as generated) with each block row's jmri_name and layout_block, a helix
    block's left out (its beans are staging's): the numbers block_numbering.csv gives (hartlib.block_numbering.read
    and bean_names: today's numbers until the levels are wired for good). They are numbered over the generated
    names, not the owner's, so an owner's rename in devices_field.csv keeps a block's numbers (sorting the owner's
    names would shift every block after a rename with no numbered_as row). Its assignment becomes virtual (an internal name) and its description is
    written again. `numbering_path`: block_numbering.csv (default the repo's). MapError on a numbering problem."""
    def numbered(r) -> bool:
        return r["layer"] == "block" and r["level"] in block_numbering.LEVELS and r["role"] != "helix"

    names = {(r["level"], r["id"]): r["user_name"] for r in rows if numbered(r)}
    try:
        numbering = block_numbering.read(numbering_path or block_numbering.PATH, names)
        beans = block_numbering.bean_names(names.values(), numbering)
    except block_numbering.NumberingError as exc:
        raise MapError(str(exc)) from exc
    out = []
    for r in rows:
        if numbered(r):
            r = dict(r)
            r["jmri_name"], r["layout_block"] = beans[r["user_name"]]
            r["assignment"] = devices.assignment_of(r["jmri_name"])
            r["description"] = devices.describe(r)
        out.append(r)
    return out


def master_outputs(bands, joined, runs, rows, parts, files: devices.Files | None = None, warn=None,
                   check: bool = False, held: list | None = None) -> dict[Path, str]:
    """{path: text} of the device master once this script has written every level's rows: main and upper's
    (build()'s `rows` and `parts`, owned_rows) and staging's (staging_rows, staging_wired_rows, and its masts and
    heads from those rows, device_map_masts.staging_masts), all generated from the plan with the owner's values over
    them, in `files` (default device_files()). The cells that name a block the
    owner renamed (a part's part_of, a detector's blocks, a mast's facing and protects) follow the new name on every
    level at once (hartlib.devices.follow_renames: a main mast facing a renamed staging helix block too). `warn` and
    `check`: hartlib.devices.outputs_after's. `held` gets why staging's masts were not placed again (a block with
    no plan length: its last mast rows are kept, and main stops after the write). MapError, DevicesError (a
    FactsError) as those stop."""
    held = [] if held is None else held
    f = files or device_files()
    drawn: dict[str, str] = {}
    staging = staging_rows(bands, joined, runs, f, drawn=drawn)
    wired = staging_wired_rows(f)
    check_switch_ids(staging + wired)
    main, made = owned_rows(rows, parts, f)
    # every block as generated (its drawn name), for follow_renames to see which ones the owner renamed
    generated = made + [dict(r, user_name=drawn[r["id"]]) if r["layer"] == "block" and r["id"] in drawn else r
                        for r in staging]
    every = [dict(r) for r in devices.follow_renames(main + staging + wired, generated)]
    # staging's masts and heads, from the block rows above (device_map_masts: one writer of every level's mast and
    # head rows)
    try:
        every += [devices.master_row(o, WRITER) for o in
                  device_map_masts.staging_masts(bands, joined, runs, every, f)["rows"]]
    except device_map_masts.MissingLengths as exc:
        # a new staging block has no plan length yet: write the rows (plan_lengths.py needs them) with staging's
        # last mast and head rows, and stop after the write (main)
        every += [dict(r) for r in devices.load(f) if r["level"] == str(STAGING_LEVEL)
                  and r["layer"] in device_map_masts.LAYERS and r["written_by"] == WRITER]
        held.append(str(exc))
    # what a main or upper bean takes from its row: its start and bean comment
    every = bean_cells(every, startup_thrown(bands))
    return devices.outputs_after(WRITER, [], f, master_rows=every, warn=warn, check=check)


def startup_thrown(bands) -> frozenset:
    """The switch numbers of the main and upper levels (not le_common.STAGING_LEVELS: staging's turnouts are the
    field's) whose virtual turnout starts Thrown: those whose main route runs through leg C and not leg B, so every
    virtual turnout lines the main line when the tables load (227 and 229 at the peninsula loop).
    A double crossover or a crossover half stays Closed (straight through). bean_cells writes it as the turnout
    row's start, which hartlib.tables_build's startup LogixNG sets."""
    out = set()
    for (_title, band, _opts), level in zip(bands, le_common.band_levels(bands)):
        if level in le_common.STAGING_LEVELS:
            continue
        for d in band["nodes"].values():
            if d["kind"] != "switch":
                continue
            main = {p: bool(sid and band["strands"][sid]["main"])
                    for p in "BC" for sid in [d["ins"].get(p) or d["outs"].get(p)]}
            if main["C"] and not main["B"]:
                out.add(base(d["label"]))
    return frozenset(out)


def check_switch_ids(rows) -> None:
    """Every switch number in a staging turnout, LCC alias or feedback ID is a switch the drawing has: it has an OS
    block ID (os:<n>, or a crossover half's os:<n>:...) among `rows`. staging_wired_rows makes those rows for the
    switches of the plan graph (staging_switches), the drawing's blocks come from the solved plan: this holds the two
    to each other. MapError naming each that is not."""
    drawn = {r["id"].split(":")[1] for r in rows if r["layer"] == "block" and r["id"].startswith("os:")}
    stray = sorted({r["id"] for r in rows if r["layer"] in ("turnout", "fb") and r["id"].split(":")[1] not in drawn},
                   key=natural)
    if stray:
        raise MapError(f"staging device IDs {', '.join(stray)} name a switch the plan does not draw")


def staging_map_error() -> type:
    import staging_device_map as sdm        # it imports this module
    return sdm.StagingMapError


def check_virtual(rows) -> None:
    """The rows' virtual names follow hartlib.level_devices (hartlib.railroad.check_virtual_names, which
    `python3 -m hartlib.railroad check` also holds the written file to); MapError naming each problem."""
    # the rows as generated, each with its id: a turnout's switch number and a block's detector are read by ID
    bad = railroad.check_virtual_names(railroad.DeviceRow.from_dict(r) for r in rows)
    if bad:
        raise MapError("; ".join(bad))


PIN_RE = re.compile(r"^Node: (\d+) (Turnout|Signal|Sensor|Block): (\d+)$")


def assign_ports(rows) -> None:
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


def csv_text(rows, columns=COLUMNS) -> str:
    """The CSV text of `rows` under `columns` (default: the device map's), as the schematic data files are written;
    a row with a column not in `columns` stops (ValueError)."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def generated_text(cp_keys) -> str:
    """plan_generated.json's whole text with its main_upper section given these control points and stations (the
    hand file is not read or written; nothing here comes from the section's own earlier keys)."""
    over = {}
    over["control_points"] = cp_keys
    over["stations"] = {name: {"switches": cp["switches"], "tracks": []} for name, cp in cp_keys.items()}
    over["_control_points"] = ("Placeholder control points 'CP <lowest switch>' (owner, 2026-11-15), written by "
                               "tools/schematic/build_device_map.py from interlockings.csv; edit that "
                               "file, not this key.")
    return layer_files.generated_texts({SHEET: over}, OVERRIDES.parent)[GENERATED]


def solve():
    import build_layout_le as bl
    sheet, le_mod, _core = bl.plugin()
    built = pd.solved_sheet(sheet)
    return built.bands, le_mod.partners(built.bands), bl.runs, dx_corners(built.bands, le_mod, built.opts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if an output is stale")
    args = ap.parse_args(argv)
    # the device map is its own layer: it reads the inputs only (railroad.LAYERS), never a copy of itself
    rr = railroad.Railroad(sources(), upto="inputs")
    try:
        overrides = rr.plan_overrides.data
        inputs = rr.level_control_points, rr.lcos_nodes, rr.local_switches
    except railroad.FactsError as exc:
        print(f"build_device_map.py: {exc}", file=sys.stderr)
        return 2
    import build_layout_le as bl
    try:
        bands, joined, runs, corners = solve()
    except bl.BuildError as exc:
        if not args.check:
            raise
        print(f"SKIPPED device map check: {exc}")
        return 1 if os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0
    try:
        cp_keys, rows, parts = build(bands, joined, runs, overrides, *inputs, corners)
    except (MapError, railroad.FactsError) as exc:        # a DevicesError (reading the master) is a FactsError
        print(f"build_device_map.py: {exc}", file=sys.stderr)
        return 2
    try:
        held: list[str] = []
        want = {GENERATED: generated_text(cp_keys),
                **master_outputs(bands, joined, runs, rows, parts, check=args.check, held=held)}
    except (MapError, staging_map_error(), railroad.FactsError, layer_files.LayerFileError) as exc:
        # a DevicesError is a FactsError; a StagingMapError comes from staging's placeholder grammar
        print(f"build_device_map.py: {exc}", file=sys.stderr)
        return 2
    stale = [p for p, text in want.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
    if args.check:
        for p in stale:
            print(devices.stale_message(p, device_files(), "tools/schematic/build_device_map.py"), file=sys.stderr)
        if held:
            print(f"build_device_map.py: staging's masts not placed again: {'; '.join(held)}", file=sys.stderr)
        return 1 if stale or held else 0
    for p in stale:
        p.write_text(want[p], encoding="utf-8")
        print(f"wrote {p.relative_to(pd.DATA.parents[4]) if len(pd.DATA.parents) > 4 else p}")
    if held:
        print(f"build_device_map.py: rows written, staging's masts kept as they were: {'; '.join(held)}",
              file=sys.stderr)
        return 2
    counts = defaultdict(int)
    for r in rows:
        counts[r["layer"]] += 1
    print(", ".join(f"{v} {k}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    # the modules that read this one at call time (device_map_schematic.builder) get this run, not a second copy
    sys.modules.setdefault("build_device_map", sys.modules[__name__])
    sys.exit(main())
