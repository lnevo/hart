#!/usr/bin/env python3
"""Placeholder control points and device names for the main and upper levels, and every level's block rows.

    python3 tools/schematic/build_device_map.py           # write both outputs
    python3 tools/schematic/build_device_map.py --check   # exit 1 if either output is stale

--check prints SKIPPED and exits 0 when the plugin submodule is not checked out (1 with SCHEMATIC_REQUIRED=1).

Inputs (jmri/layouts/hart/data/schematic/):
- interlockings.csv, its level 2 and 3 rows: the placeholder control points, "CP <lowest switch>", which
  are also the signal rule's interlockings (one file for every level). Hand
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
  markers (labels are placed before the page is scaled).
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
  its `stop` stays empty: the Dispatcher stations are parked with the stations topic
  (docs/parked/UNPARK.md has the helix stop rule for the day they return).
  A balloon loop is two blocks, "Track <n> Loop 1" from the switch's leg B and "Track <n> Loop 2" from leg C, parted
  at the turnback halfway round: JMRI keys a mast by its facing and protected blocks
  (LayoutBlockManager.getFacingBean returns one), so two masts facing one loop block into one OS block would leave
  one of them out of Signal Mast Logic discovery. Loop 1 keeps the loop's detector; Loop 2's is not on a node until it is
  wired (NOT_WIRED), so no node or input assignment moves.
  A link, a track under block_layer.LINK_CM (50 cm) between two switches, is a part (the device master's part_of) of an OS
  block: the lower-numbered switch's, or, where a home mast stands at a switch's
  points facing it, the OS block at its other end (the block boundary is at the mast). On main and upper a part is
  still a JMRI block and layout block of its own, drawn on the panel, whose occupancy sensor is its OS block's
  (hartlib.tables_build.master_beans): no occupancy row or detector of its own. A double crossover's link is part of the corner
  block of its leg; a part's row is on the level of its OS block's row (127-131 2, drawn on the upper band, in the
  main level's OS Switch 127).
- Detection on the main line only: main-route tracks and the OS blocks of control point
  switches get a planned detector; yard and industry tracks and the OS blocks of switches in no control point
  get none (their virtual sensor stays, NO_DETECTOR).
- Masts: the one mast process every level uses (mast_plan.plan; plan_masts): home masts,
  intermediates, and virtual masts (hidden, IF$vsm, ordinals from 2001 on main and 3001 on upper) only where a
  visible mast's route reaches a buffer stop first. What follows is the home mast rule as it stands here.
- Home signals: one mast where each track from outside a control point meets one of its switches; none on spurs
  or yard tracks that end at a bumper, and none where no route the mast would govern reaches another signal (every
  route ends at a bumper or in dark track: mast_rule.reaches_signal, which leaves out 125B's mast
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
- Hand lists keyed by end switches (block_overrides.csv, with a level column, and wiring.csv's main and upper detectors; running track and
  exit dwarfs are rules, mast_rule.running_tracks and signalled_spurs): columns switch_a,
  switch_b (the owner's switch numbers, lower first; switch_b blank for a spur, whose other end is a
  bumper), `parallel` (1, 2 in mast_rule.plan_order, only where two tracks run between the same switches) and, in the pins,
  `half` (1, 2: a balloon loop or split track, half 1 at the lower-numbered switch). Each row is resolved to the
  generated track at build time (mast_rule.resolve_track), so a renumber moves rows with their tracks; a pair that
  matches no track, or two tracks with no `parallel`, stops the build naming the file, line and candidates. A pin on a
  helix block gives the owner's block name instead (no switches).
- DCC addresses continue from staging's last (119): 120 up in switch-number order, main level first. Each
  turnout also gets its LCC alias "DCC Switch <n>" (MTT<dcc>, same node comment, as staging has).
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import NamedTuple, cast

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA, GRAPHS, INPUTS and the pinned plugin
from mast_rule import (  # noqa: E402,F401  the track and mast rule, re-exported for the builders
    LOOP_HALF, TAU, MapError, band_levels, end_label, end_ref, facing_on_route, helix_blocks, helix_tags, masts,
    TRACK_KEY_COLUMNS, key_problem, read_helix_tracks, resolve_track, track_names, tracks)
import block_layer  # noqa: E402  the one block process for every level
import device_map_masts  # noqa: E402  staging's mast and head rows
import mast_plan  # noqa: E402  the one mast process for every level
import mast_rule  # noqa: E402  read_block_splits, OVERRIDES_NAME
from mast_plan import Bands  # noqa: E402  the plugin's solved bands
from mast_rule import Joined, Track  # noqa: E402  the plugin's connector partners; a named track
from hartlib import block_numbering, devices, layer_files, level_masts, railroad, wiring  # noqa: E402,F401  facts, the master
from hartlib.errors import FactsError  # noqa: E402
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
from device_map_records import (  # noqa: E402,F401  build()'s records; re-exported: callers read them here
    Corners, DeviceMapRow, Drawing, MapBuild, MapInputs, MapOutput, MastEntry, MastKind, MasterCells, Runs,
    VirtualNames)
from device_map_plant import (  # noqa: E402,F401  main and upper's switch, block and track rows; re-exported
    CORNER, NO_DETECTOR, NOT_WIRED, PIN_RE, VIRTUAL_TURNOUT, assign_ports, block_sensor, check_frozen_cps,
    occupancy_user, part_rows, switch_and_os_rows, track_rows)
from device_map_level_masts import (  # noqa: E402,F401  main and upper's mast and head rows; re-exported
    HEAD_NOT_WIRED, head_name, head_rows, master_virtual_names, name_masts, owner_mast_names, virtual_mast_rows,
    virtual_memory)
from device_map_master import (  # noqa: E402,F401  the rows in the master's form; re-exported
    WRITER, block_beans, check_switch_ids, check_virtual, master_rows, owned_rows, startup_thrown)

SWITCHES = SOURCES.switches                     # switches.csv: its main and upper rows give the local switches' areas
OVERRIDES = SOURCES.plan_overrides               # plan_overrides.json, the owner's hand edits (read only)
GENERATED = layer_files.path(layer_files.GENERATED, OVERRIDES.parent)   # plan_generated.json: this writes its main_upper keys
SHEET = railroad.PlanOverrides.SHEET
OUT = SOURCES.devices                             # the device master, whose levels 2 and 3 this script writes
LEVELS = band_levels(layer_files.read("plan_overrides", SHEET, OVERRIDES.parent))     # {band title: level} of main and upper
COLUMNS = list(railroad.DEVICE_COLUMNS)
DCC_FIRST = 120                       # staging uses 100-119 (MTT100-MTT119); the owner continues from 120
LAYER_ORDER = {"turnout": 0, "fb": 1, "block": 2, "occupancy": 3, "mast": 4, "head": 5}   # build()'s row order
NAME = Path(__file__).name
# The switch number of a schematic label ("129A" -> "129", "223*" -> "223") and the natural sort key, defined once in
# hartlib.railroad; the names stay here because build_layout_le.py and build_cats_panel.py import them from this module.
base = railroad.switch_number
natural = railroad.natural


def device_files() -> devices.Files:
    """The master and its generated files as main() writes them: OUT, as it is when it runs (a test may patch it)."""
    return devices.Files.under(OUT.parent)


def sources() -> railroad.Sources:
    """The files main() reads and writes: the module's paths as they are when it runs (a test may patch them)."""
    return railroad.Sources.under().but(interlockings=CPS, lcos_nodes=NODES, switches=SWITCHES,
                                        plan_overrides=OVERRIDES, devices=OUT)


def band_level(title: str) -> int | None:
    """The level (2 or 3) of a main or upper band by its title, from the plan overrides' `level`s; None for staging."""
    return mast_rule.band_level(title, LEVELS)


def load_cps(path: Path = CPS) -> list[railroad.Interlocking]:
    """The main and upper interlockings, their control points (hartlib.railroad.read_interlockings: every switch in at
    most one)."""
    try:
        return railroad.read_interlockings(path, railroad.LEVEL_NUMBERS)
    except FactsError as exc:
        raise MapError(str(exc)) from exc


# ---------------------------------------------------------------- the map


class Planned(NamedTuple):
    """plan_masts' result: mast_plan.plan's masts by kind (home, intermediates, virtual), the double crossovers'
    corner blocks, the split tracks' names and the block layer."""
    masts: mast_plan.MastPlan
    corner_blocks: dict[str, dict[str, str]]
    split_names: set[str]
    lay: block_layer.Layer


class Held(NamedTuple):
    """What wiring.csv holds as build() starts: the node allocator with the owner's pins and frozen devices on it,
    the level of each OS block pinned by its name, and the frozen control points with their devices and blocks."""
    nodes: Nodes
    os_pin_level: dict[str, int]
    cps: frozenset[str]
    devices: set[tuple[str, str]]
    blocks: set[str]


def plan_masts(bands: Bands, joined: Joined, runs: Runs, found: list[Track], cp_of: Mapping[str, str],
               corners: Corners | None) -> Planned:
    """The one mast process over this level's block layer (main_upper_layer) and the owner's block splits. Each
    home mast gains `facing`, the block of the track it faces (its track's: a part is a JMRI block of its own).
    MapError on a double crossover with no corners given."""
    corner_blocks = corner_blocks_of(bands, corners)
    split = split_edges(found=found)
    home, posts = home_and_posts(bands, joined, found, LEVELS, cp_of, corner_blocks, set(split.values()))
    lay = main_upper_layer(bands, runs, found, split, corner_blocks, posts)
    got = mast_plan.plan(bands, joined, found, levels=LEVELS, cp_of=cp_of, layer=lay.bands, cm=lay.cm,
                         corner_blocks=corner_blocks, split=set(split.values()), home=home)
    for m in got["home"]:
        m["facing"] = m["track"]
    return Planned(got, corner_blocks, set(split.values()), lay)


def build(bands: Bands, joined: Joined, runs: Runs, inputs: MapInputs, corners: Corners | None = None, *,
          helix: Mapping[str, Mapping[str, str]] | None = None, pins: dict[str, tuple[int, int]] | None = None,
          places: Places | None = None, virtual_names: VirtualNames | None = None,
          frozen: list[wiring.Wire] | None = None, owner: Mapping[str, str] | None = None) -> MapOutput:
    """MapOutput of the main and upper levels from the drawing (`bands`, `joined`, `runs`) and `inputs`.
    `corners`: dx_corners, needed when a band has a double crossover. `helix`:
    read_helix_tracks (None: plan_overrides.json; {}: no helix tracks); `pins`: read_pins (None: wiring.csv's
    detectors, resolved against the tracks found here); `virtual_names`: {mast id: (user name, system name)} of the
    virtual masts that have one already (None: master_virtual_names); `frozen`: frozen_wires (None: wiring.csv's);
    `places`: read_places (None: stations.csv's and interlockings.csv's), the cp of every line block (line_cp);
    `owner`: {mast id: the owner's name} (None: owner_mast_names), which a mast and its heads take."""
    helix = helix_tracks() if helix is None else helix
    places = read_places() if places is None else places
    by_level = labels_by_level(bands)
    cp_keys = overrides_keys(inputs.cps, by_level)
    switches, cp_of, loc = _switch_facts(inputs.cps, inputs.local, by_level)
    found = named_tracks(bands, joined, runs, inputs.overrides, helix)
    check_helix_ends(bands, joined, found, helix)
    planned = plan_masts(bands, joined, runs, found, cp_of, corners)
    if planned.lay.inside:      # the main and upper drawing gives each strand one block: a piece there is a part
        raise MapError(f"{mast_rule.OVERRIDES_NAME} keeps {', '.join(sorted(planned.lay.inside))} inside an OS block on "
                       "main or upper, whose drawing gives each strand one block; leave inside empty (a part)")
    trials, track_ids = level_keys(bands, joined, planned.lay)
    held = _held(inputs.node_rows, pins, frozen, found=found, split_names=planned.split_names, track_ids=track_ids)
    dcc = {s: DCC_FIRST + i for i, s in enumerate(sorted(set(cp_of) | set(loc), key=natural))}
    st = MapBuild(bands=bands, by_level=by_level, switches=switches, cp_of=cp_of, loc=loc, found=found,
                  corner_blocks=planned.corner_blocks, split_names=planned.split_names, lay=planned.lay,
                  trials=trials, track_ids=track_ids, places=places, helix=helix, nodes=held.nodes,
                  os_pin_level=held.os_pin_level, dcc=dcc, rows=[], block_ids={}, home={}, area_of={})
    parts = _fill_rows(st, inputs.cps, planned.masts, owner, virtual_names)
    _check_rows(st, held)
    assign_ports(st.rows)
    st.rows.sort(key=lambda r: (r["level"], LAYER_ORDER[r["layer"]], natural(r["user_name"])))
    return MapOutput(cp_keys, st.rows, parts)


def _switch_facts(cps: Sequence[railroad.Interlocking], local: Iterable[railroad.LocalSwitch], by_level: Mapping[int, set[str]]
                  ) -> tuple[dict[str, railroad.MainUpperSwitch], dict[str, str], dict[str, railroad.MainUpperSwitch]]:
    """(every main and upper switch, {switch: its control point}, the switches in no control point). MapError on a
    switch the bands draw that is in neither."""
    try:
        switches = railroad.join_main_upper(cps, local, SWITCHES.name)
    except FactsError as exc:
        raise MapError(str(exc)) from exc
    cp_of = {s: sw.cp for s, sw in switches.items() if sw.cp}
    loc = {s: sw for s, sw in switches.items() if not sw.cp}
    on_bands = {base(lb) for labels in by_level.values() for lb in labels}
    missing = sorted(on_bands - set(cp_of) - set(loc), key=natural)
    if missing:
        raise MapError(f"switch {', '.join(missing)} is in no control point and not a local switch (an area) "
                       f"in {SWITCHES.name}")
    return switches, cp_of, loc


def _held(node_rows: Sequence[railroad.LcosNode], pins: dict[str, tuple[int, int]] | None,
          frozen: list[wiring.Wire] | None, *, found: list[Track], split_names: set[str],
          track_ids: Mapping[str, str]) -> Held:
    """The node allocator over `node_rows` with the owner's detector pins and frozen devices on it. `pins` and
    `frozen`: build()'s (None: wiring.csv's, the pins resolved against the tracks `found`)."""
    os_pin_level: dict[str, int] = {}
    if pins is None:
        pins = read_pins(found=found, split=split_names, ids={v: k for k, v in track_ids.items()})
        os_pin_level = {w.device: w.level for w in wiring_rows() if w.kind == "detector" and w.device
                        and OS_BLOCK.fullmatch(w.device)}
    nodes = Nodes(node_rows)
    nodes.pin(pins)
    wires = frozen_wires() if frozen is None else frozen
    nodes.freeze(wires)
    return Held(nodes, os_pin_level, frozenset(cp for w in wires if (cp := wiring.frozen_cp(w))),
                {(w.kind, w.device) for w in wires}, set(pins))


def _fill_rows(st: MapBuild, cps: Sequence[railroad.Interlocking], planned: mast_plan.MastPlan,
               owner: Mapping[str, str] | None, virtual_names: VirtualNames | None) -> list[MasterCells]:
    """Every row of the map into st.rows, in the order the nodes' boards fill (turnouts' 12V boards before the
    heads' 5V ones); returns the parts' master rows. `owner` and `virtual_names`: build()'s."""
    # the stages read mast_plan's records by key and give each its device ID and final name
    placed = cast(Mapping[str, list[MastEntry]], planned)
    switch_and_os_rows(st, cps)
    parts = part_rows(st)
    track_rows(st)
    visible = placed["home"] + [dict(m, heads=1, kind="one-searchlight", switch="", intermediate=True)
                               for m in placed["intermediates"]]
    vnames = name_masts(st, visible, placed["virtual"], owner_mast_names(device_files()) if owner is None else owner,
                        master_virtual_names(device_files()) if virtual_names is None else virtual_names)
    head_rows(st, cps, visible)
    virtual_mast_rows(st, placed["virtual"], vnames)
    return parts


def _check_rows(st: MapBuild, held: Held) -> None:
    """Every board, pin and frozen device is used as wiring.csv has it, and the virtual names follow their grammar.
    MapError naming what does not."""
    st.nodes.check_boards()
    st.nodes.check_pins()
    st.nodes.check_frozen()
    check_frozen_cps(st.rows, held.cps, held.devices, held.blocks)
    check_virtual(st.rows)


# ---------------------------------------------------------------- the outputs


def master_outputs(bands: Bands, joined: Joined, runs: Runs, rows: Iterable[DeviceMapRow],
                   parts: Iterable[Mapping[str, str]], files: devices.Files | None = None,
                   warn: Callable[[str], None] | None = None, check: bool = False,
                   held: list[str] | None = None) -> dict[Path, str]:
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
    generated = [*made, *(dict(r, user_name=drawn[r["id"]]) if r["layer"] == "block" and r["id"] in drawn else r
                          for r in staging)]
    every: list[Mapping[str, str]] = [dict(r) for r in devices.follow_renames([*main, *staging, *wired], generated)]
    # staging's masts and heads, from the block rows above (device_map_masts: one writer of every level's mast and
    # head rows)
    try:
        every += [devices.master_row(o, WRITER) for o in
                  device_map_masts.staging_masts(bands, joined, runs, every, f)["rows"]]
    except device_map_masts.MissingLengths as exc:
        # a new staging block has no plan length yet: write the rows (plan_lengths.py needs them) with staging's
        # last mast and head rows, and stop after the write (main)
        every += last_staging_masts(f)
        held.append(str(exc))
    # what a main or upper bean takes from its row: its start and bean comment
    return devices.outputs_after(WRITER, [], f, master_rows=bean_cells(every, startup_thrown(bands)), warn=warn,
                                 check=check)


def last_staging_masts(files: devices.Files) -> list[MasterCells]:
    """Staging's mast and head rows as this script last wrote them into the master of `files`."""
    return [dict(r) for r in devices.load(files) if r.level == STAGING_LEVEL
            and r.layer in device_map_masts.LAYERS and r.written_by == WRITER]


def staging_map_error() -> type[Exception]:
    """staging_device_map's StagingMapError, imported at call time (that module imports this one)."""
    import staging_device_map as sdm
    error: type[Exception] = sdm.StagingMapError
    return error


def csv_text(rows: Iterable[Mapping[str, object]], columns: Sequence[str] = COLUMNS) -> str:
    """The CSV text of `rows` under `columns` (default: the device map's), as the schematic data files are written;
    a row with a column not in `columns` stops (ValueError)."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def generated_text(cp_keys: Mapping[str, Mapping[str, object]]) -> str:
    """plan_generated.json's whole text with its main_upper section given these control points and stations (the
    hand file is not read or written; nothing here comes from the section's own earlier keys)."""
    over: dict[str, object] = {}
    over["control_points"] = cp_keys
    over["stations"] = {name: {"switches": cp["switches"], "tracks": []} for name, cp in cp_keys.items()}
    over["_control_points"] = ("Placeholder control points 'CP <lowest switch>' (owner, 2026-11-15), written by "
                               "tools/schematic/build_device_map.py from interlockings.csv; edit that "
                               "file, not this key.")
    return layer_files.generated_texts({SHEET: over}, OVERRIDES.parent)[GENERATED]


def solve() -> Drawing:
    """The Drawing from the solved sheet (publish_draft.solved_sheet) and the plugin's le module. build_layout_le's
    BuildError when the plugin or the drawing stops."""
    import build_layout_le as bl
    sheet, le_mod, _core = bl.plugin()
    built = pd.solved_sheet(sheet)
    return Drawing(built.bands, le_mod.partners(built.bands), bl.runs, dx_corners(built.bands, le_mod, built.opts))


# ---------------------------------------------------------------- the run


class Wanted(NamedTuple):
    """What a run would write: each output's text, the layers' row counts, and why staging's masts were held."""
    texts: dict[Path, str]
    counts: Counter[str]
    held: list[str]


def wanted(drawing: Drawing, inputs: MapInputs, check: bool = False) -> Wanted:
    """The outputs of `drawing` and `inputs`: plan_generated.json and the device master's files (`check`:
    master_outputs'). MapError, a FactsError (a DevicesError is one), a StagingMapError (staging's placeholder
    grammar) or a LayerFileError as build() and master_outputs stop."""
    bands, joined, runs, corners = drawing
    out = build(bands, joined, runs, inputs, corners)
    held: list[str] = []
    texts = {GENERATED: generated_text(out.control_points),
             **master_outputs(bands, joined, runs, out.rows, out.parts, check=check, held=held)}
    return Wanted(texts, Counter(r["layer"] for r in out.rows), held)


def _stopped(exc: Exception) -> int:
    """Say the fact that stops the build on stderr; exit status 2."""
    print(f"{NAME}: {exc}", file=sys.stderr)
    return 2


def _report_stale(stale: Sequence[Path], held: Sequence[str]) -> int:
    """--check: say which outputs are stale and why staging's masts were held; 1 when there is either, else 0."""
    for p in stale:
        print(devices.stale_message(p, device_files(), f"tools/schematic/{NAME}"), file=sys.stderr)
    if held:
        print(f"{NAME}: staging's masts not placed again: {'; '.join(held)}", file=sys.stderr)
    return 1 if stale or held else 0


def _write(want: Wanted, stale: Sequence[Path]) -> int:
    """Write the stale outputs and print each (from the repo root when it is under it); 2 when staging's masts were
    held (the rows are written), else 0 after the layers' row counts."""
    for p in stale:
        p.write_text(want.texts[p], encoding="utf-8")
        print(f"wrote {p.relative_to(pd.REPO) if p.is_relative_to(pd.REPO) else p}")
    if want.held:
        print(f"{NAME}: rows written, staging's masts kept as they were: {'; '.join(want.held)}", file=sys.stderr)
        return 2
    print(", ".join(f"{v} {k}" for k, v in want.counts.items()))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Exit status: 0 current or written, 1 stale under --check (or SKIPPED with SCHEMATIC_REQUIRED=1), 2 a fact
    that stops the build (its message on stderr), or rows written with staging's masts held."""
    ap = argparse.ArgumentParser(description=(__doc__ or NAME).split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if an output is stale")
    args = ap.parse_args(argv)
    try:
        # the device map is its own layer: it reads the inputs only (railroad.LAYERS), never a copy of itself
        inputs = MapInputs.of(railroad.Railroad(sources(), upto="inputs"))
    except FactsError as exc:
        return _stopped(exc)
    import build_layout_le as bl
    try:
        drawing = solve()
    except bl.BuildError as exc:
        if not args.check:
            raise
        print(f"SKIPPED device map check: {exc}")
        return 1 if os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0
    try:
        want = wanted(drawing, inputs, args.check)
    except (MapError, staging_map_error(), FactsError, layer_files.LayerFileError) as exc:
        return _stopped(exc)
    stale = [p for p, text in want.texts.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
    return _report_stale(stale, want.held) if args.check else _write(want, stale)


if __name__ == "__main__":
    # the modules that read this one at call time (device_map_schematic.builder) get this run, not a second copy
    sys.modules.setdefault("build_device_map", sys.modules[__name__])
    sys.exit(main())
