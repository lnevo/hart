#!/usr/bin/env python3
"""Build a Layout Editor panel of all three levels that looks like the schematic (C3, ADR-023).

    python3 tools/schematic/build_layout_le.py           # write the trial tables file
    python3 tools/schematic/build_layout_le.py --check   # fail if the trial file is stale
    python3 tools/schematic/build_layout_le.py --as-live                   # the cut-over candidate, all three levels
    python3 tools/schematic/build_layout_le.py --as-live --review          # the same, staging not yet approved
    python3 tools/schematic/build_layout_le.py --levels staging --as-live   # staging alone (the candidate's base)
    python3 tools/schematic/build_layout_le.py --freeze [--tables FILE]     # one-shot: re-read the frozen inputs

Frozen inputs (Phase 3b, owner requirement 2026-11-15). Everything the build used to read off the hand-drawn "HART
Railroad" panel (its turnouts, tracks and their blocks, the idents kept, the Entry/Exit sensors, the masts, the
overlay of icons and labels, the panel's attributes) was read once into
jmri/layouts/hart/data/schematic/staging_le/ (le_inputs.py, le_overlay.py). The build reads only those files, the
schematic and the tables' beans; it reads no panel. So the candidate is the same file whether the tables hold the
hand-drawn panel, the generated one (after the cut-over) or none. Edit the frozen files, not a panel. `--freeze`
re-reads them from a hand-drawn panel (it refuses a generated one) and checks they rebuild the same candidate;
it is not part of the normal build. "Live" below means the railroad's objects and the hand-drawn panel as frozen.

Three levels (owner, 2026-11-16). `--as-live` (levels all) writes the cut-over candidate
jmri/layouts/hart/output/trial/tables_cutover.xml: first the staging candidate below (--levels staging --as-live, drawn
at staging's own fit widened by the page's le_stretch factor, so the three-level panel has the window's shape; the
plugin's check_stretch), then
all three bands at that candidate's grid (no fitting: the panel is larger than the FIT window, which stays FIT;
zoom to fit), each band's labels placed in rounds of their own (the plugin's labels_by_band, so staging's do not
depend on the levels below), staging against the left edge (the plugin's band_align) and the main level below everything the
staging candidate holds (the plugin's le_title_clear, with the overlay's bottom under staging as band_bottoms), the
frame items and status
cluster tied to the staging band's track. check_staging_unchanged then stops unless the staging candidate is in it
unchanged: every bean, every other panel, every staging element, but the main and upper objects and the helix joins
(the staging helix tracks run on to the main level, so their end bumpers become anchors and Masts 38RA and 40RA stand
there, protecting Track 135-H2 and Track 135-H1). Main and upper take the device map's names (device_names; a
crossover's two halves are one turnout, drawn as one single crossover on one level, or as two Layout Editor
turnouts on one turnout for 129 and 135, whose halves stand on two levels), on internal system names, each block bound to its virtual occupancy sensor (the device map's jmri_name,
IS:HART:C3:B:<block key>; level_sensors), which a LogixNG sets clear when the tables load (add_level_clear); their track
names are the device map's block names without "Track ", one per block, left out where there is no room
(names_last); one block contents icon per block at 12 px (staging keeps 13; LEVEL_LE_LABELS). No sensor icons for them.

Parked features (owner, 2026-11-17; hartlib.parked, PARKED). After the staging guard the three-level candidate's
Entry/Exit, Dispatcher System and USS CTC elements are left out (parked.split), so the candidate holds none of them;
their live data is the snapshot in jmri/layouts/hart/parked/tables_parked.xml, split once from the deployed tables
(hartlib.parked.freeze), not written by this build. The released tables are that
candidate with its Signal Mast Logic from stock discovery in a sandbox (jmri/layouts/hart/parked/README.md).

Staging alone (owner approved 2026-11-15). `--levels staging` draws the staging band alone: its helix
tracks end at end bumpers as live, so every mast resolves exactly as live (no helix-entrance exception), its rows
STAGING_ROW px apart, and no main or upper object is added to the tables. With `--as-live` it writes
jmri/layouts/hart/output/trial/tables_cutover_staging.xml: the tables with the "HART Railroad" panel replaced, in its
place (or put before the first Layout Editor panel when there is none), by the generated one under the same name and
the frozen panel attributes (editable, scrollable, colours,
turnout sizes, autoblkgenerate), sized by FIT and opening at 0, 0 so the window fits the display; the "Dispatcher
System" panel and everything else unchanged. In it the staging turnouts, boundary anchors, end bumpers and the
track segment of each one-segment block keep their live idents (the plugin's `idents`), each turnout keeps its
live leg letters, type and continuing route (`leg_b`: a switch whose drawn diverging leg is live leg B is drawn
that way), the Entry/Exit sensors go back in their live slots (same ident and slot, checked to resolve to the same
blocks), and le_overlay.py carries the live icons and region captions across (Phase 2), around the switch
numbers, track names, station captions and block contents icons the plugin generates (owner, 2026-11-15). The
panel carries the hidden generated-panel label (hartlib.tables.GENERATED_PANEL_MARKER, Phase 3):
polish_hart_layout_editor.py, reconcile_dispatcher_stations.py, the audit and the other scripts that pin the
hand-drawn panel's pixels read it and take positions from the panel itself (wiki/projects/schematic-maps-handoff.md,
cut-over runbook).

Staging from the device map (`--staging devicemap`, owner review pending; the frozen path stays the default until
the owner approves it). Staging is drawn as main and upper are, from device_map_staging.csv, control_points_staging.csv
and staging_masts.csv (staging_device_map.load: turnouts, OS and track blocks by the drawing's keys, each switch's
normal leg from switch_legs.csv, its turnout ident from switches.csv), with no frozen file: no kept anchor, end bumper
or segment ident (generated, owner 2026-11-17; the boundary contract for them is staged in schematic/staged/), no
Entry/Exit sensor (parked), and panel_items.json (panel_items.py) in place of the overlay: the panel's attributes,
the status cluster panel_status.py drives, the frame captions, the helix destination labels and the backdrop, each
tied to the staging track. The occupancy lamps and station clusters are parked with the Dispatcher System
(jmri/layouts/hart/parked/staging_panel_lamps.json). check_device_masts stands in for check_slots and
check_live_turnouts. The grid, the stretch check, staging_lengths, staging_columns and the three-level build on the
staging candidate are as on the frozen path. Its trial files carry DEVICEMAP_SUFFIX (tables_cutover_devicemap.xml and
its _staging candidate), beside the frozen path's.

Writes jmri/layouts/hart/output/trial/tables_layout.xml: the live tables.xml unchanged, plus one new Layout
Editor panel, PANEL_NAME, and the internal turnouts, blocks and layout blocks the main and upper levels need. The
live tables.xml is only read. The panel is the schematic-maps plugin's `le` drawing of the solved schematic bands
(the inputs of publish_draft.py): straight rows, rounded bends, half-circle turnbacks, helix circles, names on the
drawing. Staging, main and upper are stacked as on the sheet.

Names:
- Staging binds to the live objects, so the panel can replace "HART Railroad" at the cut-over: each schematic
  switch is the live Layout Editor turnout that switches.csv names (its turnout name and OS blocks as the live panel
  has them; switches 7, 23 and 35 are one single crossover each), and each schematic track takes the blocks of the
  live track between the same two switches, in order (a turnback's two tracks split them by track name), drawn at
  their measured lengths (staging `track_lengths_in`), so each short throat block (S-1 West, S-1 East, East Lead
  East, K-1 West) sits at its own end of its track, by its ladder. The
  normal leg is switch_legs.csv's closed leg. No staging object is created; the build stops if a name is missing.
- Staging masts: every mast the live panel binds in a slot goes in the slot of the new panel that JMRI resolves to
  the same facing and protected blocks, and the same kind of slot (anchor, end bumper or turnout leg), so Signal
  Mast Logic discovery and the Dispatcher System read the same boundaries from either panel (the plugin's slots.py
  holds JMRI's rules). Its icon goes on the right-hand side of the train it governs, hidden as the live icon is.
  Staging's helix joins carry the next level's block ("joins": "other"), so the helix entrance anchor is a block
  boundary: a live buffer-stop mast whose track the new panel runs on through the helix (Mast 38RA, 40RA) stands
  there, facing the same block and protecting the helix run (the live buffer stop protects nothing). Any mast with
  no matching slot stops the build, and so does a mast that two slots of the new panel would fit (a turnout mast
  must also land on the live turnout).
- Main and upper: the drawing's placeholders (turnouts "Switch <number>", blocks "Track <plan edge id>" and "OS
  Switch <number>", the track between the A and B halves of one number being that number's OS block) mapped to
  the device map's user names by its trial_name column, on internal IT:HART:C3: and IB:C3: system names, so nothing
  commands field hardware; each block bound to its virtual occupancy sensor IS:HART:C3:B:<block key> and each
  control-point mast on virtual heads (the device map's jmri_name, owner 2026-11-17: the physical plant is a draft,
  swapped in later by the device map alone).

Size: the panel opens at 100% zoom in a FIT pixel window (the plugin's `fit` scales the grid; label fonts keep their
size).

The trial is for looking at only. Both panels bind the same staging masts in one tables file. JMRI's mast lookups
(LayoutBlockManager, DefaultSignalMastLogic) walk the Layout Editor panels in title order and take the first panel
that has the mast, so "HART Railroad" answers before "Layout (generated)"; but Layout Block routing merges the block
connections of every loaded panel, so the trial adds the helix joins (McKeesport and McKees Rocks to the next
levels' placeholder blocks) to the routing graph, and 38RA and 40RA resolve differently on the two panels. So with
the trial loaded do not run Signal Mast Logic discovery, Dispatcher System Stage 1 or Entry/Exit generation, and do
not Store. At the cut-over the live panel goes and the generated one alone carries the masts. This script never
writes the live tables.xml or anything in the JMRI profile (main() refuses such an --out).

The plugin is the pinned submodule, or SCHEMATIC_PLUGIN (as publish_draft.py).
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import importlib
import json
import os
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import le_inputs  # noqa: E402  the frozen staging facts (jmri/layouts/hart/data/schematic/staging_le/)
import panel_items  # noqa: E402  the panel's fixed items and attributes (panel_items.json; the device-map path)
import publish_draft as pd  # noqa: E402  DATA, GRAPHS, INPUTS, hartlib paths and the pinned plugin
import staging_device_map as sdm  # noqa: E402  the staging device map (the device-map path)
from hartlib import hand_drawn, parked, paths, tables  # noqa: E402
# The build's parts (split out of this file, no change in what they do) and the staging candidate's approval
# fingerprint (approval.py): their names are re-exported below, so callers and tests read them here as before. Patch
# a name in the module that calls it (le_names.placeholder_names, say).
from le_common import (  # noqa: E402,F401  re-exported: callers and tests read them here
    STAGING, SWITCHES, SWITCH_LEGS, DEVICE_MAP, TURNOUT_SYS, BLOCK_SYS, LAYOUT_BLOCK_FIRST, BuildError, plugin,
    schematic, overlay_mod, slots_module, band_key, bare, read_csv,
)
from approval import (  # noqa: E402,F401  re-exported: callers and tests read them here
    ApprovalError, STAGING_APPROVED as APPROVED, approved_fingerprint, check_approved, read_approved, write_approved,
)
from le_names import (  # noqa: E402,F401  re-exported: callers and tests read them here
    LEVEL_LE_LABELS, NUMBERS_BELOW, OPTIONAL_READOUTS, crossover_strands, runs, orient, share_blocks,
    staging_names, LEGS_SWAPPED, swapped_idents, swap_legs, live_leg_first, staging_lengths, plugin_masts,
    MAIN_UPPER_MASTS, read_level_masts, lcos_rule, lcos_named, level_masts, placeholder_names, device_names,
    level_names, shared_turnouts, NAME_COLUMNS, LAMP_COLUMNS, staging_columns, named_bands, NO_NAME, joined_ends,
)
from le_checks import (  # noqa: E402,F401  re-exported: callers and tests read them here
    BOUNDARIES, check_swapped_slots, check_slots, mast_band, check_level_slots, check_unplaced, turnout_facts,
    check_live_turnouts, check_device_masts,
)
from le_tables import (  # noqa: E402,F401  re-exported: callers and tests read them here
    BLOCK_NUMBERED_AS, APPENDED_BLOCKS, COMMENT, place, bean, r1, block_sort,
    RETIRED_TURNOUT_PREFIX, retire_yard_ladder, bind_sensors, replace, canon, is_level_bean, level_items,
    PANEL_SIZE_ATTRS, helix_join_changes, check_staging_unchanged, insert_first_panel, numbered_blocks,
    level_sensors, SENSOR_COMMENT, add_level_sensors, MALE_DEBUGGER, MALE_ACTION, male_socket, add_level_clear,
    add_level_objects, SIGNAL_NOTE, HEAD_CLASS, MAST_CLASS, add_level_signals,
)

# Whether the three-level panel joins staging's helix tracks to the main and upper levels by hidden segments. On
# (owner, 2026-11-17, the helix-join release): joined plainly, with no route-flow entries; staging's own pairs change
# as stock SML discovery finds them (10RA, 10RB, 12R and 14R pair to 16L; 36RB->40RB is lost), accepted. Masts 38RA
# and 40RA stand at the helix-entrance anchors, protecting Track 135-H2 and Track 135-H1. Off, every helix end stays
# an end bumper (the 2026-11-16 cut-over) and the staging guard accepts no difference.
JOIN_HELIX = True
TRIAL = paths.LAYOUT_OUTPUT / "trial" / "tables_layout.xml"
CUTOVER = paths.LAYOUT_OUTPUT / "trial" / "tables_cutover.xml"                    # all three levels (the candidate)
CUTOVER_STAGING = paths.LAYOUT_OUTPUT / "trial" / "tables_cutover_staging.xml"    # staging alone (the guard's base)
TRIAL_STAGING = paths.LAYOUT_OUTPUT / "trial" / "tables_layout_staging.xml"
LEVELS = ("all", "staging")
# Where staging's facts come from (module text, "Staging from the device map"): the frozen files until the owner
# approves the device-map panel, then the device map. Each source writes its own trial files (default_out).
STAGING_SOURCES = ("frozen", "devicemap")
PANEL_ITEMS = pd.DATA / "panel_items.json"
DEVICEMAP_SUFFIX = "_devicemap"     # tables_cutover.xml -> tables_cutover_devicemap.xml, and so on
PANEL_NAME = "Layout (generated)"
TEMPLATE_PANEL = le_inputs.PANEL     # the panel the cut-over candidate replaces (its inputs are frozen in le_inputs)
# The window the panel opens in at 100% zoom on the owner's 1900 x 1200 display (the plugin fits the panel inside
# it less Layout Editor's 18 x 60 px frame allowance). Width: the whole 1900, so the panel is at most 1882 (the
# live panel's window is 1882 wide). Height: 1200 less the macOS menu bar (37 px on a notched display, 25 else)
# and 23 px spare for the Dock's edge is 1140; the 60 px allowance covers the title bar (28 px) and the thin edit
# toolbar, leaving the panel at most 1080.
FIT = (1900, 1140)
# Staging alone fills the window's width long before its height, so its rows may be as far apart as the live
# panel's yard tracks (about 47 px), leaving room between them for the live panel's icons and labels.
STAGING_ROW = 48
# The cut-over candidates' grid (owner, 2026-11-16): staging's own fit to the window (the grid's scale across and down
# when the staging band alone is fitted into FIT at STAGING_ROW, found by the plugin's fit in each staging cut-over
# build and kept as P.staging_fit) widened by main_upper.preferences.json's le_stretch (the plugin's stretched and
# check_stretch). The geometry knobs of the Layout Editor drawing (le_shift, le_longer_straights, le_title_clear,
# le_stretch, le_labels extra_steps and extra_follow) are layer 3 preferences the plugin reads (schematic/le_prefs.py).
# The plugin's label layer (schematic/le_labels.py): switch numbers as the hand-drawn panel wrote them ("SW-13",
# 13 px bold), block contents icons on with the plugin's reserve; given to every band through the page options.
# The all-levels trial (viewing only) has no block contents icons (owner, 2026-11-16), and its switch numbers at the
# plugin's 9 px: three bands in one window leave no room for 13 px ones (SW-29 fits nowhere). Staging keeps both.
LE_LABELS = {"switch_prefix": "SW-", "switch_size": 13}
TRIAL_LE_LABELS = dict(LE_LABELS, switch_size=9, block_contents=False)
# The features parked out of the cut-over candidate into jmri/layouts/hart/parked/tables_parked.xml (owner,
# 2026-11-17; hartlib.parked): Entry/Exit, the stock Dispatcher System and the USS CTC machine. Unpark one by taking
# it out of hartlib.parked.PARKED and rebuilding.
PARKED = parked.PARKED


def template_tables() -> Path:
    """The tables a build or --freeze starts from when none is named: this checkout's, while its main panel is the
    hand-drawn one; after the cut-over (the main panel is generated) the last hand-drawn tables, read from git
    (hartlib.hand_drawn), since the build replaces that panel and adds the main and upper objects to its tables."""
    try:
        live = tables.layout_editor(tables.read(paths.TABLES_XML), TEMPLATE_PANEL)
        cut_over = live is not None and tables.generated_panel(live)
    except (OSError, ET.ParseError, ValueError) as exc:
        raise BuildError(f"cannot read {paths.rel(paths.TABLES_XML)}: {exc}") from None
    if not cut_over:
        return paths.TABLES_XML
    try:
        path = hand_drawn.tables_path()
    except ValueError as exc:
        raise BuildError(f"{paths.rel(paths.TABLES_XML)} holds the generated panel, and {exc}") from None
    print(f"note: {paths.rel(paths.TABLES_XML)} holds the generated panel (cut over); building on the last hand-drawn "
          f"tables, git {hand_drawn.COMMIT}")
    return path


def build(live_path: Path = paths.TABLES_XML, bands=None, levels: str = "all", as_live: bool = False, inputs=None,
          freeze_from: ET.Element | None = None, approved: Path | None = APPROVED, page: dict | None = None,
          staging_source: str = "frozen"):
    """(tables bytes, the plugin's Panel, {band key: names}, bands). `levels` "all" draws every band, main and upper
    under the device map's names (level_names) and their objects added to the tables; "staging" draws staging alone, its
    helix ends as end bumpers as live, and adds no table object. `as_live` writes a cut-over candidate: the "HART
    Railroad" panel of the tables (hand-drawn or generated) replaced by the new one, or the new one put before the
    first Layout Editor panel when the tables have none, under the frozen name and attributes; with "all", drawn at
    the staging candidate's grid and checked to hold it unchanged (check_staging_unchanged; module text). Without
    `as_live`, "all" is the viewing trial beside the live panel, fitted into the FIT window. The staging facts come
    from `inputs` (default: the frozen files, le_inputs.load()); nothing is read from a panel in the tables.
    `freeze_from` (--freeze only, with `as_live`): the hand-drawn panel whose overlay le_overlay.freeze reads into
    inputs.overlay before it is carried. `approved`: the fingerprint the staging candidate's panel must match
    (check_approved; None skips it, for --approve-staging and tests that change the inputs).
    `staging_source` (STAGING_SOURCES): "frozen", the default, draws staging from the frozen files as above;
    "devicemap" from the staging device map (staging_device_map.load, no frozen file) with panel_items.json in place
    of the overlay (module text, "Staging from the device map")."""
    if levels not in LEVELS:
        raise BuildError(f"levels must be one of {', '.join(LEVELS)}, not {levels!r}")
    if staging_source not in STAGING_SOURCES:
        raise BuildError(f"staging_source must be one of {', '.join(STAGING_SOURCES)}, not {staging_source!r}")
    devicemap = staging_source == "devicemap"
    if freeze_from is not None and not (as_live and levels == "staging"):
        raise BuildError("the overlay is frozen from the staging cut-over build (--levels staging --as-live)")
    if devicemap and (freeze_from is not None or inputs is not None):
        raise BuildError("the device-map staging path reads no frozen inputs: it takes neither inputs nor freeze_from")
    items = None
    if devicemap:
        try:
            items = panel_items.load(PANEL_ITEMS)
        except panel_items.ItemsError as exc:
            raise BuildError(f"panel items: {exc}") from None
    elif inputs is None:
        inputs = le_inputs.load()
    _sheet, le_mod, core = plugin()
    # the page options come from the solved sheet (schematic()), for the bands given too unless `page` is (the
    # three-level build passes its own on to the staging candidate it draws first)
    if bands is None:
        bands, solved_page = schematic()
    else:
        solved_page = schematic()[1]
    page = solved_page if page is None else page
    # as the Layout Editor draws them (the preferences' le_shift, le_longer_straights; once): so the names below are
    # read off the bands drawn, before named_bands relabels a crossover's halves
    try:
        bands = le_mod.drawn_bands(bands, page)
    except core.SchematicError as exc:
        raise BuildError(f"schematic le: {exc}") from None
    base = None             # the three-level candidate: the staging candidate it must hold unchanged, and its grid
    if as_live and levels == "all":
        base = build(live_path, bands, "staging", True, inputs, approved=approved, page=page,
                     staging_source=staging_source)
    keys = [band_key(t) for t, _, _ in bands]
    if STAGING not in keys:
        raise BuildError(f"no {STAGING} band in the schematic (bands: {', '.join(keys)})")
    if levels == "staging":
        bands = [bands[keys.index(STAGING)]]
        keys = [STAGING]
    if band_key(bands[0][0]) != STAGING:
        raise BuildError(f"the first band is {bands[0][0]!r}, not {STAGING}")
    doc = tables.load(live_path)
    root = doc.root
    # The build reads no panel (a staging candidate rebuilds from itself byte for byte), but it adds the main and
    # upper objects to the tables: tables that hold them already (the cut-over tables) are refused
    if any(is_level_bean(el) for sec in root for el in sec):
        raise BuildError(f"{live_path} already holds the main and upper objects (the cut-over is done): build on "
                         f"the last hand-drawn tables (the command does so by itself: hartlib.hand_drawn, git "
                         f"{hand_drawn.COMMIT})")
    panel_name = (items["panel"] if devicemap else inputs.panel_name) if as_live else PANEL_NAME
    if not as_live and any(le.get("name") == PANEL_NAME for le in tables.layout_editors(root)):
        raise BuildError(f"{live_path} already has a panel named {PANEL_NAME}")
    if not tables.layout_editors(root):
        raise BuildError(f"{live_path} has no Layout Editor panel to put the new one beside")

    names, lengths = level_names(bands, le_mod, page=page) if levels == "all" else ({}, {})
    level_rows = []
    if levels == "all":                 # the main and upper control-point masts (main_upper_masts.csv)
        level_rows = read_level_masts()
        level_masts(names, level_rows)
    shared_turnouts(names)
    if devicemap:
        try:
            names[STAGING] = sdm.load(bands[0][1])
        except sdm.StagingMapError as exc:
            raise BuildError(f"staging device map: {exc}") from None
    else:
        names[STAGING] = staging_names(bands[0][1], inputs, core.tidy)
    # a live segment ident JMRI cannot find as a segment by name (F46-W-0: LayoutEditorFindItems.findObjectByName
    # reads only T... and F<n>-S-<n>; such names load, but the Check menu and connection menus miss them) is not
    # carried over: that segment takes a generated ident (noted)
    segs = names[STAGING]["idents"]["segments"]
    unfindable = sorted(i for i in segs.values() if le_mod.jmri_kind(i) != "segment")
    names[STAGING]["idents"]["segments"] = {b: i for b, i in segs.items() if i not in unfindable}
    if not devicemap:               # the device map's reader gives them (staging_masts.csv)
        names[STAGING]["masts"] = plugin_masts(inputs.masts)
    system = tables.mast_system_names(root)
    absent = sorted(m["mast"] for m in names[STAGING]["masts"] if m["mast"] not in system)
    if absent:
        raise BuildError(f"{'staging_masts.csv' if devicemap else 'masts.csv'} names masts that are not in the "
                         f"signal mast table: {absent}")
    if levels == "all" and not JOIN_HELIX:
        names[STAGING]["joins"] = "none"        # the helix ends stay end bumpers on every level (JOIN_HELIX)
    elif levels == "all":
        names[STAGING]["joins"] = "other"
        # a staging track that runs on through a helix join has no end bumper here: its live bumper's ident goes
        names[STAGING]["idents"]["ends"] = {b: i for b, i in names[STAGING]["idents"]["ends"].items()
                                            if b not in joined_ends(bands, names[STAGING], le_mod)}
    names[STAGING]["lengths"] = staging_lengths(bands[0][2], names[STAGING])
    # the page-wide label options are HART's (LE_LABELS). The page is the last input's own options, so le_labels in
    # main_upper.preferences.json are main's and upper's: they reach those bands through their own options
    # (named_bands), not the page
    page = dict(page, le_labels=dict(TRIAL_LE_LABELS if levels == "all" and not as_live else LE_LABELS))  # a copy
    extras = {}
    # the station clusters, placed by the plugin's label layer (le_overlay.station_extras); the device-map path has
    # none (parked with the Dispatcher System, jmri/layouts/hart/parked/staging_panel_lamps.json)
    if as_live and not devicemap:
        ov = overlay_mod()
        try:
            clusters = ov.panel_station_clusters(freeze_from) if freeze_from is not None else \
                ov.station_clusters(inputs.overlay)
            extras = {"extras": ov.station_extras(clusters)}
        except ov.OverlayError as exc:
            raise BuildError(f"overlay: {exc}") from None
    try:
        if base is not None:        # staging's own grid, so staging is drawn as in its candidate; no fitting
            scale = base[1].scale
            if page.get("band_align"):
                raise BuildError("the schematic's page options hold band_align; HART sets it for the panel here")
            # staging against the left edge, where it stands drawn alone, however wide the other levels are; its
            # labels placed as when it is drawn alone (labels_by_band); and the gaps between the levels as small as
            # is clean (owner, 2026-11-16; the page's le_title_clear): for staging, below everything its candidate
            # holds (its status cluster stands in the gap: band_bottoms). Every crossover at its level's
            # le_crossover_angle, however each level is stretched; the station clusters where staging's candidate
            # has them (an extra given its x keeps it)
            S = base[1]
            stepped = {"extras": le_mod.with_x(extras.get("extras"), S.extra_x)}
            P = le_mod.panel(staging_columns(named_bands(bands, names)), names, cell=le_mod.CELL * scale[0],
                             row=STAGING_ROW * scale[1], page=dict(page, band_align={STAGING: "left"}),
                             labels_by_band=True, tight_crossovers=TIGHT_CROSSOVERS, split_crossovers=SPLIT_CROSSOVERS,
                             mast_room=MAST_ROOM, name_room=NAME_ROOM,
                             band_bottoms={STAGING: S.overlay["bottom"] - S.band_boxes[0][3]},
                             **stepped)
            P.scale, P.fit, P.stretch = scale, None, S.stretch
        elif as_live:               # the staging candidate: the cut-over grid, no fitting (it scrolls in FIT)
            # (the grid a fit settles on does not depend on the caller's items, so none are given)
            fitted = le_mod.panel(bands, names, page=page, fit=FIT, row=STAGING_ROW).scale
            scale, stretch = le_mod.stretched(fitted, page)
            # the station clusters that step (staging's le_labels extra_steps, extra_follow) are placed by the plugin
            P = le_mod.panel(staging_columns(bands), names, cell=le_mod.CELL * scale[0], row=STAGING_ROW * scale[1],
                             page=page, **extras)
            P.scale, P.fit, P.staging_fit, P.stretch = scale, None, fitted, stretch
        else:
            rows = {"row": STAGING_ROW} if levels == "staging" else {}
            drawn = named_bands(bands, names) if levels == "all" else bands
            P = le_mod.panel(drawn, names, page=page, fit=FIT, **rows, **extras)
    except core.SchematicError as exc:
        raise BuildError(f"schematic le: {exc}") from None
    P.mast_notes = check_unplaced(P)
    if unfindable:
        P.log.append(f"live segment idents JMRI does not find as segments, so not reused: {', '.join(unfindable)}")
    if devicemap:           # no frozen idents or slots to hold the panel to: each mast in one slot, on its switch
        check_device_masts(P, names[STAGING]["masts"], le_mod)
    else:
        check_slots(P, inputs.masts, le_mod)
        check_live_turnouts(le_mod.to_xml(P, "check"), inputs)
    check_level_slots(P, level_rows, le_mod)
    check_swapped_slots()

    # staging: every name must already be live
    staging_turnouts = set(names[STAGING]["turnouts"].values())
    staging_blocks = set(names[STAGING]["os"].values()) | {b for v in names[STAGING]["blocks"].values() for b in v}
    live_turnouts = tables.by_any_name(tables.turnouts(root))
    live_lb = {tables.user_name(b) for b in tables.layout_blocks(root)}
    missing = sorted(t for t in staging_turnouts if t not in live_turnouts) + \
        sorted(b for b in staging_blocks if b not in live_lb)
    if missing:
        raise BuildError(f"staging names not in the live tables: {missing}")
    if levels == "staging" and set(P.blocks) - staging_blocks:
        raise BuildError(f"the staging panel draws blocks that are not live: {sorted(set(P.blocks) - staging_blocks)}")
    if levels == "all":
        add_level_objects(root, P, names, lengths, staging_blocks)
        add_level_signals(root, level_rows)

    if as_live and devicemap:
        # the panel's own items by rule (panel_items.json), no overlay and no Entry/Exit sensors (parked)
        try:
            attrs, options = panel_items.panel_attributes(items)
            panel_el = le_mod.to_xml(P, panel_name, attrs, options)
            # tied to the staging track, so they stand where the staging candidate has them on three levels too
            placed = panel_items.place(panel_el, items, le_mod, slots_module(), FIT, le_mod.CHROME,
                                       frame_blocks=staging_blocks)
        except panel_items.ItemsError as exc:
            raise BuildError(f"panel items: {exc}") from None
        if placed["bottom"] is None:
            raise BuildError(f"{paths.rel(PANEL_ITEMS)} places no sized item, so the level below has no bottom to "
                             "keep clear of")
        P.items = placed
        P.overlay = dict(size=placed["size"], bottom=placed["bottom"])      # what the three-level build reads
    if as_live and not devicemap:
        panel_el = le_mod.to_xml(P, panel_name, dict(inputs.attrs), copy.deepcopy(inputs.drawing_options))
        P.sensors_bound = bind_sensors(panel_el, inputs.sensors)
        ov = overlay_mod()
        try:
            if freeze_from is not None:
                inputs.overlay = ov.freeze(freeze_from, panel_el, root, le_mod, slots_module(), inputs.note,
                                           LE_LABELS["switch_prefix"])
            # every crossover half shows its own OS occupancy (owner, 2026-11-16): the hand-drawn panel has one lamp
            # for 7 and 23, the generated one a lamp per half, each in the middle of its half (le_overlay.half_lamps)
            os_sensors = {b.findtext("userName"): b.findtext("occupancysensor").strip() for b in root.iter("block")
                          if b.findtext("userName") and b.find("occupancysensor") is not None}
            P.overlay = ov.carry(inputs.overlay, panel_el, P, le_mod, slots_module(), FIT,
                                 LE_LABELS["switch_prefix"], frame_blocks=staging_blocks, lamp_columns=LAMP_COLUMNS,
                                 os_sensors=os_sensors)
            ov.check_half_lamps(panel_el, os_sensors)
        except ov.OverlayError as exc:
            raise BuildError(f"overlay: {exc}") from None
    if as_live:
        # a panel larger than its window (the cut-over grid: staging alone is wider, three levels wider and taller)
        # scrolls both ways, so nothing on it is out of reach at 100% zoom; the frozen attribute says "none"
        w, h = P.overlay["size"]
        if w + le_mod.CHROME[0] > FIT[0] or h + le_mod.CHROME[1] > FIT[1]:
            panel_el.set("scrollable", "both")
        # the marker that tells polish_hart_layout_editor.py and the other hand-pixel scripts to leave positions alone
        opts = panel_el.find("layoutTrackDrawingOptions")
        panel_el.insert(list(panel_el).index(opts) + 1 if opts is not None else 0, tables.generated_marker_label())
        if levels == "staging" and approved is not None:
            try:
                check_approved(panel_el, approved)
            except ApprovalError as exc:
                raise BuildError(str(exc)) from None
        old = tables.layout_editor(root, panel_name)
        if old is not None:
            replace(root, old, panel_el, 1)
        else:
            insert_first_panel(root, panel_el, 1)
        if base is not None:
            P.staging_same = check_staging_unchanged(base, doc.tobytes(), P, panel_name, JOIN_HELIX)
            P.staging_data = base[0]
            try:
                le_mod.check_stretch(P.overlay["size"], FIT, page)
            except core.SchematicError as exc:
                raise BuildError(f"schematic le: {exc}") from None
            # the parked features (PARKED, owner 2026-11-17) leave the cut-over candidate for the parked file,
            # after the staging guard, which compares the two candidates whole
            try:
                P.parked_doc = parked.split(root, PARKED)
            except parked.ParkError as exc:
                raise BuildError(f"parking: {exc}") from None
            P.retired = retire_yard_ladder(root)
    else:
        attrs = dict(inputs.attrs)
        attrs.update(scrollable="both", editable="yes", autoblkgenerate="no")
        panel_el = le_mod.to_xml(P, panel_name, attrs, copy.deepcopy(inputs.drawing_options))
        place(root, [panel_el], 1, tables.layout_editors(root)[-1])
    return doc.tobytes(), P, names, bands


# Crossovers drawn as close together as JMRI's shapes allow on the track they share (the plugin's tight_crossovers):
# 101 and 103 are one physical three-way switch (owner, 2026-11-16). JMRI's crossover shape runs its pieces a run
# past the diagonal on each track, which kept their throats about 110 px apart, so the two are drawn as two plain
# turnouts each on their one turnout name (split_crossovers): their throats on the shared track stand two legs and
# the block's least length apart, each diagonal at 45 degrees.
TIGHT_CROSSOVERS = {"Main": [["101", "103"]]}
SPLIT_CROSSOVERS = {"Main": ["101", "103"]}
# Bands whose drawing lets in room for a mast icon (the plugin's mast_room): a mast whose straight track before its
# boundary is shorter than its icon, or whose icon still has no clean spot there, has its band let out along its rows
# at that track (Masts 108R and 110LA on track 107-109, 128RB and 130LA on 127-129, 228RA on 227-233 stood on 16 to
# 19 px of straight; 2026-11-17). Main and upper only: staging is drawn as the owner approved it.
MAST_ROOM = ["Main", "Upper"]
# Bands whose drawing, in the same pass, lets a named track's straight out to its name's width (the plugin's
# name_room), while the band stays no wider than the widest: main uses its spare width so Tracks 107-109 and 125-127
# get their names beside 109-111 and 127-129 (owner, 2026-11-17: "Use main's spare width"); upper is the widest, so
# its short tracks keep their length (noted).
NAME_ROOM = ["Main", "Upper"]


def live_target(out: Path) -> bool:
    """True when `out` is the live tables.xml or lies in the JMRI profile (by path or through a link)."""
    real = Path(os.path.realpath(out))
    # the checkout's own file, whatever HART_TABLES points TABLES_XML at
    if real in (Path(os.path.realpath(paths.REPO_TABLES_XML)), Path(os.path.realpath(paths.TABLES_XML))):
        return True
    profile = Path(os.path.realpath(paths.JMRI_USER_FILES))
    return real == profile or profile in real.parents


SIGNAL_GRAPH = "staging.json"      # the plan graph in inputs/ the signal reader matches staging's masts on


def freeze(tables_path: Path = paths.TABLES_XML, folder: Path = le_inputs.FOLDER, date: str | None = None) -> list:
    """Read every staging input off the hand-drawn panel in `tables_path` into the frozen files in `folder`, once
    (le_inputs.py): its turnouts, tracks, kept idents, Entry/Exit sensors, masts (with their schematic runs, by the
    plugin's signal reader, as build_signals.py read them before) and overlay (le_overlay.freeze), and its
    attributes. Refuses a generated panel. The files are written to a new folder beside `folder` first; the cut-over
    candidate is rebuilt from them there and must be byte for byte the one built from the panel, and the signals the
    reader's. Only then do they replace `folder` (each step a rename); on any failure `folder` is left as it was.
    Every failure is a BuildError (or le_inputs.InputsError). Returns the files written."""
    import datetime
    import shutil
    import tempfile

    try:
        root = tables.read(tables_path)
    except (OSError, ET.ParseError, ValueError) as exc:
        raise BuildError(f"cannot read {tables_path}: {exc}") from None
    live_le = tables.layout_editor(root, TEMPLATE_PANEL)
    if live_le is None:
        raise BuildError(f"{tables_path} has no {TEMPLATE_PANEL!r} panel to freeze")
    if tables.generated_panel(live_le):
        raise BuildError(f"the {TEMPLATE_PANEL!r} panel in {tables_path} is a generated one (it holds the "
                         "generated-panel marker): the inputs are frozen from the hand-drawn panel only")
    plugin()
    reader = importlib.import_module("schematic.signal_reader")
    layers = importlib.import_module("schematic.layers")
    panel_reader = importlib.import_module("schematic.panel_reader")
    try:
        overrides = layers.load("staging", str(pd.DATA), preferences=False)
        graph = json.loads((pd.GRAPHS / SIGNAL_GRAPH).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:        # a missing or unparsable layer file or plan graph
        raise BuildError(f"cannot read the staging plan overrides or {SIGNAL_GRAPH}: {exc}") from None
    try:
        signals = reader.read(str(tables_path), graph, overrides, panel_reader.load_numbers(str(SWITCHES)),
                              panel_reader.load_lengths(str(paths.LAYOUT_DATA / "block_lengths.csv")),
                              TEMPLATE_PANEL)
    except Exception as exc:        # the plugin's own errors (PlanError and others): named, not a traceback
        raise BuildError(f"signal reader on {tables_path}: {type(exc).__name__}: {exc}") from None
    try:
        source = paths.rel(Path(tables_path))
    except ValueError:
        source = Path(tables_path).name
    try:                            # the last hand-drawn tables, read from git (template_tables): named as such
        if Path(tables_path).resolve() == hand_drawn.tables_path().resolve():
            source = f"{hand_drawn.REL} at git {hand_drawn.COMMIT}"
    except ValueError:
        pass
    note = le_inputs.NOTE.format(panel=TEMPLATE_PANEL, source=source,
                                 date=date or datetime.date.today().isoformat())
    inputs = le_inputs.from_live(root, live_le, slots_module(), signals, overrides.get("mast_prefix", ""), note)
    # the freeze compares two builds with each other; whether the owner approved that panel is the cut-over's check
    data = build(tables_path, levels="staging", as_live=True, inputs=inputs, freeze_from=live_le, approved=None)[0]
    folder = Path(folder)
    try:
        folder.parent.mkdir(parents=True, exist_ok=True)
        fresh = Path(tempfile.mkdtemp(prefix=f".{folder.name}.new.", dir=folder.parent))
    except OSError as exc:
        raise BuildError(f"cannot make a folder beside {folder}: {exc}") from None
    try:
        written = le_inputs.write(inputs, fresh)
        again = le_inputs.load(fresh)
        if le_inputs.signal_rows(again.masts) != signals["signals"]:
            raise BuildError("the written masts.csv does not give back the signal reader's runs")
        if build(tables_path, levels="staging", as_live=True, inputs=again, approved=None)[0] != data:
            raise BuildError("the written files do not rebuild the panel built from the hand-drawn one")
        old = None
        if folder.exists():
            old = Path(tempfile.mkdtemp(prefix=f".{folder.name}.old.", dir=folder.parent)) / folder.name
            folder.rename(old)
        try:
            fresh.rename(folder)
        except OSError:
            if old is not None:
                old.rename(folder)          # put the committed files back
            raise
        if old is not None:
            shutil.rmtree(old.parent)
    except OSError as exc:
        raise BuildError(f"cannot put the frozen files in {folder}: {exc}") from None
    finally:
        if fresh.exists():
            shutil.rmtree(fresh)
    return [folder / p.name for p in written]


def main(argv=None) -> int:
    """The command. Once its arguments pass, the plugin's cache is on (publish_draft.cache_on) for the solve and the
    Layout Editor panels, so a run whose inputs and plugin code are unchanged draws nothing again."""
    with contextlib.ExitStack() as cached:
        return run(argv, cached)


def run(argv, cached) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="regenerate in memory and fail if the file differs")
    ap.add_argument("--levels", choices=LEVELS, default=None,
                    help="all: every band, main and upper under the device map's names (default); staging: staging "
                         "alone")
    ap.add_argument("--as-live", action="store_true",
                    help="write the cut-over candidate: the live panel replaced by the new one; with --levels all "
                         "(the default) all three levels at staging's grid (tables_cutover.xml), with --levels "
                         "staging staging alone (tables_cutover_staging.xml)")
    ap.add_argument("--out", type=Path, help="where to write (default: the trial file for these options: "
                    "tables_layout.xml, tables_layout_staging.xml, tables_cutover.xml or "
                    "tables_cutover_staging.xml)")
    ap.add_argument("--tables", type=Path, help="the tables file to build on (default: this checkout's); with "
                    "--freeze, the tables holding the hand-drawn panel")
    ap.add_argument("--freeze", action="store_true",
                    help="one-shot: read the staging inputs off the hand-drawn panel into the frozen files "
                         f"({paths.rel(le_inputs.FOLDER)}), then check they rebuild the same candidate")
    ap.add_argument("--freeze-to", type=Path,
                    help="with --freeze: the folder to write (default: the frozen files' own)")
    ap.add_argument("--review", action="store_true",
                    help="with --as-live: write the candidate for the owner to review although its staging panel is "
                         f"not the approved one ({paths.rel(APPROVED)} is not checked; the run says so)")
    ap.add_argument("--approve-staging", action="store_true",
                    help="after the owner approves the staging panel in PanelPro: record its fingerprint in "
                         f"{paths.rel(APPROVED)}, which both cut-over builds then check")
    ap.add_argument("--staging", choices=STAGING_SOURCES, default="frozen",
                    help="where staging's facts come from: frozen (default; staging_le/ and its overlay) or devicemap "
                         "(device_map_staging.csv, staging_masts.csv and panel_items.json), whose trial files are "
                         f"named with {DEVICEMAP_SUFFIX} (tables_cutover{DEVICEMAP_SUFFIX}.xml)")
    args = ap.parse_args(argv)
    if args.staging == "devicemap" and args.freeze:
        print("ERROR: --freeze reads the hand-drawn panel into the frozen files; it has no device-map form")
        return 1
    if not args.check:          # --freeze writes the committed frozen files: refused with HART_TABLES as any write
        message = paths.check_only_message(Path(__file__).name)
        if message:
            print(f"ERROR: {message}")
            return 1
    cached.enter_context(pd.cache_on())     # after the HART_TABLES refusal: a refused run touches nothing
    if args.approve_staging:
        if args.check or args.freeze or args.freeze_to or args.as_live or args.out or args.levels is not None \
                or args.review:
            print("ERROR: --approve-staging takes only --tables")
            return 1
        try:
            data = build(args.tables or template_tables(), levels="staging", as_live=True, approved=None,
                         staging_source=args.staging)[0]
            write_approved(tables.layout_editor(tables.loads(data).root, TEMPLATE_PANEL))
        except (le_inputs.InputsError, ApprovalError) as exc:
            print(f"ERROR: {exc}")
            return 1
        print(f"wrote {paths.rel(APPROVED)}: the staging panel as the owner approved it")
        return 0
    if args.freeze:
        if args.check or args.as_live or args.out or args.levels is not None or args.review:
            print("ERROR: --freeze takes only --tables and --freeze-to")
            return 1
        try:
            written = freeze(args.tables or template_tables(), args.freeze_to or le_inputs.FOLDER)
        except le_inputs.InputsError as exc:
            print(f"ERROR: {exc}")
            return 1
        for p in written:
            print(f"wrote {p}")
        print("ok: the written files rebuild the same cut-over candidate")
        return 0
    if args.freeze_to is not None:
        print("ERROR: --freeze-to goes with --freeze")
        return 1
    if args.review and not args.as_live:
        print("ERROR: --review goes with --as-live")
        return 1
    levels = args.levels or "all"
    out = args.out or default_out(levels, args.as_live, args.staging)
    if live_target(out):
        print(f"ERROR: {out} is the live tables or in the JMRI profile; the trial is for viewing only and is "
              "written beside them, never over them")
        return 1
    try:
        where = {"live_path": args.tables or template_tables()}
        if args.review:
            where["approved"] = None
        data, P, _names, _bands = build(levels=levels, as_live=args.as_live, staging_source=args.staging, **where)
    except le_inputs.InputsError as exc:
        print(f"ERROR: {exc}")
        return 1
    _, le_mod, _ = plugin()
    summary = f"panel {(TEMPLATE_PANEL if args.as_live else PANEL_NAME)!r}: {le_mod.summary(P)}"
    # the three-level candidate writes the staging candidate it holds beside it (tables_cutover_staging.xml)
    files = [(out, data)]
    if getattr(P, "staging_data", None) is not None:
        files.append((staging_out(out), P.staging_data))
    if args.check:
        stale = [f for f, d in files if not f.exists() or f.read_bytes() != d]
        if stale:
            print(f"STALE: {', '.join(paths.rel(f) for f in stale)}; run {paths.rel(Path(__file__))}")
            return 1
        print(f"ok: {', '.join(paths.rel(f) for f, _d in files)} current ({summary})")
        return 0
    for f, d in files:
        if live_target(f):
            print(f"ERROR: {f} is the live tables or in the JMRI profile")
            return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    for f, d in files:
        tables.loads(d, path=f).save(f)
    print(f"wrote {paths.rel(out)}: {summary}")
    if args.review:
        print(f"  REVIEW: the staging panel was not checked against the approved one ({paths.rel(APPROVED)}); it is "
              "UNAPPROVED until the owner approves it in PanelPro and --approve-staging records it")
    if len(files) > 1:
        print(f"wrote {paths.rel(files[1][0])}: the staging candidate it holds")
    if isinstance(getattr(P, "parked_doc", None), ET.Element):
        where = f"kept in {paths.rel(parked.PARKED_XML)} (the live snapshot)"
        print(f"parked ({', '.join(sorted(PARKED))}), left out, {where}; the template's: " + "; ".join(
            f"{f}: " + ", ".join(f"{v} {k}" for k, v in sorted(c.items()))
            for f, c in parked.counts(P.parked_doc).items()))
    if getattr(P, "retired", None) is not None:
        print(f"yard ladder retired: {P.retired} internal turnouts and routes left out ({RETIRED_TURNOUT_PREFIX}*)")
    moved = {f"{t}: mast {m}: {why}" for t, m, why in P.moved}       # the plugin's own log line for each
    for line in P.log:
        if line not in moved:
            print(f"  note: {line}")
    for line in P.mast_notes:
        print(f"  mast at a helix join: {line}")
    for line in overlay_lines(getattr(P, "overlay", None)):
        print(f"  overlay: {line}")
    if isinstance(getattr(P, "items", None), dict):         # the device-map path's panel items
        print(f"  panel items: {P.items['count']} elements from {paths.rel(PANEL_ITEMS)}; panel "
              f"{P.items['size'][0]}x{P.items['size'][1]} px (no overlay; lamps and stations parked)")
    if getattr(P, "gaps", None):
        print(f"  gaps between the levels: {', '.join(f'{g:g}' for g in P.gaps)} px; grid {P.scale[0]:.4f} x "
              f"{P.scale[1]:.4f} (le_stretch factor {P.stretch})")
    same = getattr(P, "staging_same", None)
    if same is not None:
        print(f"  staging guard: the {'(unapproved) ' if args.review else 'approved '}staging candidate is held "
              + ("unchanged but for the helix joins:" if same else "unchanged, byte for byte (JOIN_HELIX off)"))
        for line in same:
            print(f"    {line}")
    return 0


def staging_out(out: Path) -> Path:
    """Where the three-level candidate `out` writes the staging candidate it holds: tables_cutover.xml ->
    tables_cutover_staging.xml (CUTOVER_STAGING)."""
    return out.with_name(f"{out.stem}_staging{out.suffix}")


def default_out(levels: str, as_live: bool, staging_source: str = "frozen") -> Path:
    """The trial file for these options, so --check always compares like with like; the device-map path's beside the
    frozen path's, its name with DEVICEMAP_SUFFIX (tables_cutover_devicemap.xml)."""
    if as_live:
        out = CUTOVER_STAGING if levels == "staging" else CUTOVER
    else:
        out = TRIAL_STAGING if levels == "staging" else TRIAL
    if staging_source == "devicemap":
        stem = out.stem.removesuffix("_staging")
        out = out.with_name(f"{stem}{DEVICEMAP_SUFFIX}{'_staging' if stem != out.stem else ''}{out.suffix}")
    return out


def overlay_lines(report) -> list[str]:
    """The overlay report (le_overlay.carry) as printed lines; none without one (the device-map path's P.overlay
    holds only the size and bottom its panel items give, no carry report)."""
    if not report or "records" not in report:
        return []
    ov = overlay_mod()
    kinds = defaultdict(int)
    for r in report["records"]:
        kinds[r["anchor"].split(" ", 1)[0] if r["anchor"].startswith("group") else r["anchor"]] += 1
    out = [f"{len(report['records'])} live items carried ({', '.join(f'{v} {k}' for k, v in sorted(kinds.items()))})"
           f"; panel {report['size'][0]}x{report['size'][1]} px",
           "placed around the generated " + (", ".join(f"{v} {k if k.endswith('s') else k + 's'}"
                                                       for k, v in sorted(report["generated"].items())) or "nothing") +
           "; left to the generator: " + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in report["dropped"].items()
                                                   if k in ov.GIVEN) +
           "; not carried: " + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in report["dropped"].items()
                                         if k in ov.NOT_CARRIED)]
    out += report["notes"]
    if report["unchained"]:
        out.append("blocks whose track is not one run (an item's share read against its pieces in order): "
                   + ", ".join(report["unchained"]))
    far = sorted(report["records"], key=lambda r: -r["nudged"])[:5]
    out.append("nudged furthest: " + ", ".join(f"{r['item']} {r['nudged']:g} px" for r in far))
    return out


if __name__ == "__main__":
    sys.exit(main())
