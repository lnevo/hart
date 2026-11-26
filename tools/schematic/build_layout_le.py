#!/usr/bin/env python3
"""Build the Layout Editor panel of all three levels that looks like the schematic (C3, ADR-023).

    python3 tools/schematic/build_layout_le.py                    # build in memory and print what the panel holds
    python3 tools/schematic/build_layout_le.py --levels staging   # the same for staging drawn alone

The build is a library: tools/schematic/build_tables.py calls build(levels="all", as_live=True) and writes
jmri/layouts/hart/output/tables.xml from it. This command writes no file. The trial copies beside the tables
(output/trial/tables_cutover.xml and tables_cutover_staging.xml), their fingerprints and the staging guard are
retired: the live panel is approved, and approval.py's `le-panel` fingerprint of the
"HART Railroad" panel in tables.xml is the one approval check. The viewing trials (tables_layout.xml,
tables_layout_staging.xml) are retired; build() without as_live stops and says so.

One input path. Every level is drawn from its device map: staging
from the level 1 rows of the device master, stations.csv (its desk areas) and masts.csv (staging_device_map.load: each switch's
turnout and OS block, each track's blocks in order by the drawing's keys, each switch's normal leg from
switches.csv, its turnout ident from the same file), main and upper from the rest of the device master and
masts.csv's other rows (level_names, level_masts). The panel's own icons and labels, and its attributes, are
panel_items.json (panel_items.py): the status cluster panel_status.py drives, the frame captions, the helix
destination labels and the backdrop, each tied to the staging track. The occupancy lamps and station clusters are
parked with the Dispatcher System (jmri/layouts/hart/parked/staging_panel_lamps.json); Entry/Exit sensors are not
bound (parked). The build reads no panel in the tables: only the schematic, those files and the tables' beans.

Three levels. levels "all" first draws staging alone (levels "staging", below), at staging's own
fit widened by the page's le_stretch factor, so the three-level panel has the window's shape (the plugin's
check_stretch), then all three bands at that grid (no fitting: the panel is larger than the window, the page's
le_window, which stays as it is; zoom to fit), each band's labels placed in rounds of their own (the plugin's
labels_by_band), staging against the left edge (the plugin's band_align) and the main level below everything the
staging drawing holds (the plugin's le_title_clear, with the panel items' bottom under staging as band_bottoms). The
staging helix tracks run on to the main level, so their end bumpers become anchors, inside one block: each helix
track is one block from staging up the helix, Track Helix Outer and Track Helix Inner, bound to
the device map's sensor of that helix track (the base: hartlib.tables_build.master_beans). Main
and upper take the device map's names (device_names; a crossover's two halves are one turnout, drawn as one single
crossover on one level, or as two Layout Editor turnouts on one turnout for 127 and 131, whose halves stand on two
levels, and for 121 and 125, whose halves the plan joins leg C to leg B; each half is closed on the leg away from its
other half), on the beans the device master's rows give them (each row's jmri_name: today internal, each block bound
to its virtual occupancy sensor, which the startup LogixNG sets clear when the tables load); their track names are the device
map's block names without "Track ", left out where there is no room (names_last); one block contents icon per block at
12 px (staging keeps 13; preferences.json[main_upper]'s le_band_labels).

Parked features (hartlib.parked, PARKED). The three-level build's Entry/Exit, Dispatcher System
and USS CTC elements are left out (parked.split); their live data is the snapshot in
jmri/layouts/hart/parked/tables_parked.xml. The released tables are this build with its Signal Mast Logic from
stock discovery in a sandbox (jmri/layouts/hart/parked/README.md).

The tables it builds on (ADR-029, R9c): the generator's base (hartlib.tables_build.base), the template
(data/tables_template.xml) with every level's beans of the device master, never the live
tables.xml, which is an output (tools/schematic/build_tables.py writes it from this build, the discovered Signal Mast
Logic and the template). The base holds no panel and no Signal Mast Logic; the build adds no bean, only the panel after
the template's sections, once it has checked that every name the panel binds is a bean of the base (check_bound) and
that the main and upper blocks drawn are numbered as block_numbering.csv says (check_level_blocks).

Staging alone. levels "staging" draws the staging band alone: its helix tracks end at end bumpers, its rows le_row px
apart (the page preference); the panel is the "HART Railroad"
panel under panel_items.json's attributes, sized by the le_window and opening at 0, 0. The three-level build takes
its grid from it. Staging's turnouts
keep their switches.csv idents; anchors, end bumpers and segments take generated idents, which
masts.csv names them by block, not by ident. Every staging mast goes in the one slot whose facing and protected blocks and kind of
slot are its own (masts.csv; the plugin's slots.py holds JMRI's rules), its icon on the right-hand side of the
train it governs, hidden for a virtual mast; check_masts (one check for every level's masts) stops on a mast two slots
would fit, one JMRI does not resolve to its blocks, or one on another turnout than its switch's. Staging's helix joins carry the next level's block ("joins": "other"), the same helix block,
so the join is no block boundary and no mast stands there. The panel carries the
hidden generated-panel label (hartlib.tables.GENERATED_PANEL_MARKER): the build starts only from tables that hold
it, and the Stage 1 repairs of the parked Dispatcher System run only on a panel that holds it.

The plugin is the pinned submodule, or SCHEMATIC_PLUGIN (as publish_draft.py).
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import sys
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel_items  # noqa: E402  the panel's fixed items and attributes (panel_items.json)
import publish_draft as pd  # noqa: E402  DATA, GRAPHS, INPUTS, hartlib paths and the pinned plugin
import staging_device_map as sdm  # noqa: E402  the staging device map
from hartlib import parked, paths, tables, tables_build  # noqa: E402
# The build's parts: their names are re-exported below, so callers and tests read them here. Patch a name in the module that calls it (le_names.placeholder_names).
from le_common import (  # noqa: E402,F401  re-exported: callers and tests read them here
    staging_switches, DEVICE_MAP, BLOCK_SYS, LAYOUT_BLOCK_FIRST, BuildError, plugin,
    schematic, slots_module, band_key, bare, read_csv, STAGING_LEVELS, band_levels, base_bands, base_band, base_keys,
    find_band, le_band_align, le_station_labels,
)
from le_names import (  # noqa: E402,F401  re-exported: callers and tests read them here
    crossover_strands, runs,
    staging_lengths, MASTS, read_level_masts, lcos_rule, lcos_named, level_masts, placeholder_names,
    device_names, level_names, shared_turnouts, named_bands,
)
from le_checks import (  # noqa: E402,F401  re-exported: callers and tests read them here
    check_masts, mast_turnouts, check_unplaced, turnout_facts,
)
import le_tables  # noqa: E402  its numbering, read on first use (__getattr__)
from le_tables import (  # noqa: E402,F401  re-exported: callers and tests read them here
    NUMBERING, NUMBERING_NAMES, load_numbering, numbering, block_sort,
    RETIRED_TURNOUT_PREFIX, retire_yard_ladder, place, canon, level_bean_names, is_level_bean,
    numbered_blocks, level_block_beans, band_blocks, check_level_blocks, check_bound, bean_names, drawn_blocks,
)

LEVELS = ("all", "staging")
PANEL_ITEMS = panel_items.ITEMS     # the panel's own items (hartlib.hand_lists.PANEL_ITEMS)
TEMPLATE_PANEL = "HART Railroad"     # the panel's name
RETIRED_TRIAL = ("the viewing trials (tables_layout.xml, tables_layout_staging.xml) are retired: "
                 "build with as_live=True")

# The window the panel opens in at 100% zoom (the page's le_window, derived from preferences.json[main_upper]'s
# host_screen by host_screen.py, as the CATS desks' window is) and the rows staging is drawn at (le_row, set there)
# are read through the plugin (le.window, le.row); their notes there say why.
# The three-level panel's grid: staging's own fit to the window (the grid's scale across and down
# when the staging band alone is fitted into the le_window at le_row, found by the plugin's fit in each staging
# cut-over build and kept as P.staging_fit) widened by preferences.json[main_upper]'s le_stretch (the plugin's
# stretched and check_stretch). The geometry knobs of the Layout Editor drawing (le_shift, le_longer_straights,
# le_crossover_angle, le_mast_room, le_name_room, le_title_clear,
# le_stretch, le_window, le_row, and the label options: staging's le_labels extra_steps, extra_follow and name_columns,
# preferences.json[main_upper]'s page-wide le_labels and each level's le_band_labels) are layer 3
# preferences the plugin reads (schematic/le_prefs.py, schematic/le_labels.py). Crossovers 101 and 103, one
# three-way part in the plan, are drawn tight and split by the plugin's rule (schematic-maps 0.1.48), not a
# preference.
# The features parked out of the three-level panel into jmri/layouts/hart/parked/tables_parked.xml
# (hartlib.parked): Entry/Exit, the stock Dispatcher System and the USS CTC machine. Unpark one by taking
# it out of hartlib.parked.PARKED and rebuilding.
PARKED = parked.PARKED


BASE_NAME = "the generated base (data/tables_template.xml and the device master)"


def base_tables() -> bytes:
    """The tables a build draws on: hartlib.tables_build.base, the template with every level's beans of the device
    master. BuildError on anything that stops it, naming the file."""
    try:
        return tables_build.base().tobytes()
    except (tables_build.TablesBuildError, tables_build.devices.DevicesError) as exc:
        raise BuildError(f"tables base: {exc}") from exc


class LeBuild(NamedTuple):
    """What build() returns. Callers unpack it as (data, P, names, bands) or read it by field."""
    data: bytes                     # the base tables with the panel added
    panel: Any                      # the plugin's Panel (schematic/le.py, loaded from the plugin's path: untyped here)
    names: dict[str, dict[str, Any]]    # {band key: the names the plugin draws that band under}
    bands: list[Any]                # the plugin's bands as drawn, each (title, band, options)


def build(bands: list[Any] | None = None, levels: str = "all", as_live: bool = False,
          page: dict[str, Any] | None = None, base_data: bytes | None = None) -> LeBuild:
    """The panel added to the base tables. `levels` "all" draws every band, main and upper under the device map's
    names (level_names) and their objects added to the tables; "staging" draws staging alone, its helix ends as end
    bumpers, and adds no table object. `as_live`: the base (base_tables; module text) with the panel added, under
    panel_items.json's name and attributes; with "all", drawn at the grid of staging drawn alone (module text).
    `as_live` must be given: without it (the viewing trials, retired) the build stops. Staging's facts come from the
    staging device map (staging_device_map.load); nothing is read from a panel in the tables. `base_data`:
    base_tables() already built (the three-level build passes it to the staging drawing it makes first, so the base
    is built once)."""
    if levels not in LEVELS:
        raise BuildError(f"levels must be one of {', '.join(LEVELS)}, not {levels!r}")
    if not as_live:
        raise BuildError(RETIRED_TRIAL)
    items = _load_items()
    _sheet, le_mod, core = plugin()
    bands, page = _sheet_inputs(bands, page)
    fit, staging_row = _window(page, le_mod, core)
    bands = _drawn(bands, page, le_mod, core)
    # The build reads no panel and no live tables: it draws on the generator's base (module text)
    if base_data is None:
        base_data = base_tables()
    # the three-level panel is drawn at the grid of staging drawn alone, from the same drawn bands
    alone = build(bands, "staging", True, page=page, base_data=base_data) if levels == "all" else None
    staging, levels_of = _staging_band(bands)
    if levels == "staging":
        bands, levels_of = bands[:1], levels_of[:1]
    # whether the drawing holds a level other than staging, whose names and masts come from the device master
    adds = any(lv not in STAGING_LEVELS for lv in levels_of)
    doc = tables.loads(base_data)
    root = doc.root
    if root.find("LayoutEditor") is not None:
        raise BuildError(f"{BASE_NAME} holds a Layout Editor panel; the build adds the one panel")
    names, level_rows, skip = _names(bands, staging, adds, alone, page, le_mod)
    P = _draw(bands, names, staging, alone, page, fit, staging_row, le_mod, core)
    base_ix = {i for i, lv in enumerate(levels_of) if lv in STAGING_LEVELS}    # a hidden join has band None: in none
    _check_drawn(root, P, names, level_rows, skip, base_ix, adds, le_mod)
    _add_panel(root, P, items, base_ix, fit, le_mod)
    if alone is not None:
        _finish_three_levels(root, P, fit, page, le_mod, core)
    return LeBuild(doc.tobytes(), P, names, bands)


def _load_items() -> Any:
    """panel_items.json read (panel_items.load; its own record type); BuildError naming it on a bad file."""
    try:
        return panel_items.load(PANEL_ITEMS)
    except panel_items.ItemsError as exc:
        raise BuildError(f"panel items: {exc}") from exc


def _sheet_inputs(bands: list[Any] | None, page: dict[str, Any] | None) -> tuple[list[Any], dict[str, Any]]:
    """(bands, page options): the solved sheet's (schematic()) for whichever is not given. The three-level build
    passes its own page on to the staging drawing it makes first."""
    if bands is None:
        bands, solved_page = schematic()
    else:
        solved_page = schematic()[1]
    return bands, solved_page if page is None else page


def _window(page: Mapping[str, Any], le_mod: Any, core: Any) -> tuple[Any, Any]:
    """(the le_window, staging's le_row) from the page's preferences, read through the plugin (le.window, le.row).
    BuildError when the page holds no le_row or le_labels, or the plugin rejects them."""
    if "le_row" not in page:        # le.row falls back to the plugin's rows: HART's staging rows are a preference
        raise BuildError("the page's preferences (preferences.json[main_upper]) hold no le_row")
    if "le_labels" not in page:     # the plugin's defaults would draw every switch number unprefixed, staging's too
        raise BuildError("the page's preferences (preferences.json[main_upper]) hold no le_labels")
    try:
        return le_mod.window(page), le_mod.row(page)
    except core.SchematicError as exc:
        raise BuildError(f"schematic le: {exc}") from exc


def _drawn(bands: list[Any], page: Mapping[str, Any], le_mod: Any, core: Any) -> list[Any]:
    """The bands as the Layout Editor draws them (the preferences' le_shift, le_longer_straights), so the names are
    read off the bands drawn, before named_bands relabels a crossover's halves; then the station names the labeller
    prints: each sheet's le_nested_station_labels (preferences.json[staging]: false, so Engine House, a desk area
    nested in Barn, is named on the drawings but not on the panel)."""
    try:
        drawn = le_mod.drawn_bands(bands, page)
    except core.SchematicError as exc:
        raise BuildError(f"schematic le: {exc}") from exc
    return le_station_labels(drawn)


def _staging_band(bands: list[Any]) -> tuple[str, list[Any]]:
    """(the staging band's key, each band's level). One band of the staging level (STAGING_LEVELS), drawn first: the
    staging band, which the staging device map names (staging_device_map.load reads that band, found by its level)
    and every other level is drawn under; its key is the plugin's key for the names and options given for it."""
    levels_of = band_levels(bands)
    if base_bands(bands) != [0]:
        raise BuildError(f"the schematic must draw one band of level {', '.join(map(str, sorted(STAGING_LEVELS)))} "
                         f"(staging), first; its bands are "
                         + ", ".join(f"{t!r} (level {lv})" for (t, _b, _o), lv in zip(bands, levels_of)))
    return band_key(bands[base_band(bands)][0]), levels_of


def _names(bands: list[Any], staging: str, adds: bool, alone: LeBuild | None, page: dict[str, Any],
           le_mod: Any) -> tuple[dict[str, dict[str, Any]], list[Any], Any]:
    """(names by band key, masts.csv's main and upper rows, the staging band's keys). Main and upper from the device
    master and masts.csv; staging from the staging device map, reused from `alone` when staging was drawn alone from
    the same band."""
    names, _lengths = level_names(bands, le_mod, page=page) if adds else ({}, {})
    level_rows = read_level_masts() if adds else []
    skip = base_keys(bands)             # the staging band's: its names are the staging device map's
    shared_turnouts(names, skip)
    if alone is not None:
        names[staging] = copy.deepcopy(alone.names[staging])
    else:
        try:
            names[staging] = sdm.load(bands[0][1])
        except sdm.StagingMapError as exc:
            raise BuildError(f"staging device map: {exc}") from exc
    if adds:                            # after staging's names: a helix intermediate protects a staging track
        level_masts(names, level_rows, skip)
        names[staging]["joins"] = "other"   # staging's helix ends join the next level: no block boundary there
    names[staging]["lengths"] = staging_lengths(names[staging])
    return names, level_rows, skip


def _draw(bands: list[Any], names: dict[str, dict[str, Any]], staging: str, alone: LeBuild | None,
          page: dict[str, Any], fit: Any, staging_row: Any, le_mod: Any, core: Any) -> Any:
    """The plugin's Panel: on three levels at the grid of staging drawn alone (`alone`), with no fitting; staging
    alone at its own fit to the le_window, widened by le_stretch."""
    try:
        if alone is not None:
            return _draw_three_levels(bands, names, staging, alone.panel, page, staging_row, le_mod)
        # staging alone: the three-level grid, no fitting (it scrolls in the le_window); staging's own fit to the
        # le_window, which the cut-over grid is stretched from
        fitted = le_mod.panel(bands, names, page=page, fit=fit, row=staging_row).scale
        scale, stretch = le_mod.stretched(fitted, page)
        P = le_mod.panel(bands, names, cell=le_mod.CELL * scale[0], row=staging_row * scale[1], page=page)
        P.scale, P.fit, P.staging_fit, P.stretch = scale, None, fitted, stretch
        return P
    except core.SchematicError as exc:
        raise BuildError(f"schematic le: {exc}") from exc


def _draw_three_levels(bands: list[Any], names: dict[str, dict[str, Any]], staging: str, S: Any,
                       page: dict[str, Any], staging_row: Any, le_mod: Any) -> Any:
    """Every band at staging's own grid (S, staging drawn alone), so staging is drawn as when drawn alone. Each band
    against the edge its sheet's le_band_align gives (preferences.json[staging]: staging against the left edge, where
    it stands drawn alone, however wide the other levels are); its labels placed as when it is drawn alone
    (labels_by_band); and the gaps between the levels as small as is clean (the page's le_title_clear): for staging,
    below everything its drawing holds (its status cluster stands in the gap: band_bottoms). Every crossover at its
    level's le_crossover_angle, however each level is stretched."""
    scale = S.scale
    if page.get("band_align"):
        raise BuildError("the schematic's page options hold band_align, which the published sheet would "
                         "read too; set the Layout Editor panel's in a sheet's preferences section as "
                         "le_band_align ({level: side})")
    P = le_mod.panel(named_bands(bands, names), names, cell=le_mod.CELL * scale[0],
                     row=staging_row * scale[1], page=dict(page, band_align=le_band_align(bands)),
                     labels_by_band=True, band_bottoms={staging: S.items["bottom"] - S.band_boxes[0][3]})
    P.scale, P.fit, P.stretch = scale, None, S.stretch
    return P


def _check_drawn(root: ET.Element, P: Any, names: dict[str, dict[str, Any]], level_rows: list[Any], skip: Any,
                 base_ix: set[int], adds: bool, le_mod: Any) -> None:
    """Every level's masts, each in the one slot its blocks fit, on its switch's turnout (one check for all levels);
    the main and upper blocks drawn checked against block_numbering.csv; then each name the panel binds is a bean of
    the base (hartlib.tables_build.base, from the device master). Sets P.mast_notes."""
    P.mast_notes = check_unplaced(P)
    check_masts(P, {k: v.get("masts", []) for k, v in names.items()}, le_mod, mast_turnouts(level_rows))
    if adds:
        check_level_blocks(root, P, skip, names)
    check_bound(root, P, names, skip, base_ix, BASE_NAME)


def _add_panel(root: ET.Element, P: Any, items: Any, base_ix: set[int], fit: Any, le_mod: Any) -> None:
    """The panel element, with the panel's own items by rule (panel_items.json) tied to the staging track (by the
    staging band's own track: a helix block runs on up a level), so they stand where the staging drawing has them on
    three levels too, and the generated-panel marker, placed after the template's last section. Sets P.items."""
    try:
        attrs, options = panel_items.panel_attributes(items)
    except panel_items.ItemsError as exc:
        raise BuildError(f"panel items: {exc}") from exc
    panel_el = le_mod.to_xml(P, TEMPLATE_PANEL, attrs, options)
    frame = {P.name(o["ident"]) for o in P.segments + P.turnouts if o["band"] in base_ix}
    try:
        P.items = panel_items.place(panel_el, items, le_mod, slots_module(), fit, le_mod.CHROME,
                                    frame_idents=frame)
    except panel_items.ItemsError as exc:
        raise BuildError(f"panel items: {exc}") from exc
    if P.items["bottom"] is None:
        raise BuildError(f"{paths.rel(PANEL_ITEMS)} places no sized item, so the level below has no bottom to "
                         "keep clear of")
    # a panel larger than its window (the cut-over grid: staging alone is wider, three levels wider and taller)
    # scrolls both ways, so nothing on it is out of reach at 100% zoom
    w, h = P.items["size"]
    if w + le_mod.CHROME[0] > fit[0] or h + le_mod.CHROME[1] > fit[1]:
        panel_el.set("scrollable", "both")
    # the marker that tells the build and the Stage 1 repairs the panel is a generated one
    opts = panel_el.find("layoutTrackDrawingOptions")
    panel_el.insert(list(panel_el).index(opts) + 1 if opts is not None else 0, tables.generated_marker_label())
    place(root, [panel_el], 1)          # after the template's last section


def _finish_three_levels(root: ET.Element, P: Any, fit: Any, page: dict[str, Any], le_mod: Any, core: Any) -> None:
    """The three-level panel's last steps: its size against the window (the plugin's check_stretch), the parked
    features (PARKED) moved out to the parked file (P.parked_doc) and the yard ladder retired (P.retired)."""
    try:
        le_mod.check_stretch(P.items["size"], fit, page)
    except core.SchematicError as exc:
        raise BuildError(f"schematic le: {exc}") from exc
    try:
        P.parked_doc = parked.split(root, PARKED)
    except parked.ParkError as exc:
        raise BuildError(f"parking: {exc}") from exc
    P.retired = retire_yard_ladder(root)


def __getattr__(name: str) -> Any:
    """le_tables' numbering (BLOCK_NUMBERED_AS, APPENDED_BLOCKS, RETIRED_BLOCKS), re-exported as read on first use."""
    if name in NUMBERING_NAMES:
        return getattr(le_tables, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main(argv: Sequence[str] | None = None) -> int:
    """The command. Once its arguments pass, the plugin's cache is on (publish_draft.cache_on) for the solve and the
    Layout Editor panels, so a run whose inputs and plugin code are unchanged draws nothing again."""
    with contextlib.ExitStack() as cached:
        return run(argv, cached)


def run(argv: Sequence[str] | None, cached: contextlib.ExitStack) -> int:
    """Build in memory and print what the panel holds; write nothing (build_tables.py writes tables.xml)."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--levels", choices=LEVELS, default="all",
                    help="all: every band, main and upper under the device map's names (default); staging: staging "
                         "alone")
    args = ap.parse_args(argv)
    cached.enter_context(pd.cache_on())
    try:
        _data, P, _names, _bands = build(levels=args.levels, as_live=True)
    except BuildError as exc:
        print(f"ERROR: {exc}")
        return 1
    _, le_mod, _ = plugin()
    print(f"panel {TEMPLATE_PANEL!r}: {le_mod.summary(P)}")
    print(f"  built on {BASE_NAME}; nothing written (tools/schematic/build_tables.py writes "
          f"{paths.rel(paths.REPO_TABLES_XML)})")
    if isinstance(getattr(P, "parked_doc", None), ET.Element):
        print(f"parked ({', '.join(sorted(PARKED))}), left out, kept in {paths.rel(parked.PARKED_XML)} (the live "
              "snapshot): " + "; ".join(
                  f"{f}: " + (", ".join(f"{v} {k}" for k, v in sorted(c.items())) or "none")
                  for f, c in parked.counts(P.parked_doc).items()))
    if getattr(P, "retired", None) is not None:
        print(f"yard ladder retired: {P.retired} internal turnouts and routes taken out ({RETIRED_TURNOUT_PREFIX}*)")
    moved = {f"{t}: mast {m}: {why}" for t, m, why in P.moved}       # the plugin's own log line for each
    for line in P.log:
        if line not in moved:
            print(f"  note: {line}")
    for line in P.mast_notes:
        print(f"  mast at a helix join: {line}")
    if isinstance(getattr(P, "items", None), dict):
        print(f"  panel items: {P.items['count']} elements from {paths.rel(PANEL_ITEMS)}; panel "
              f"{P.items['size'][0]}x{P.items['size'][1]} px")
    if getattr(P, "gaps", None):
        print(f"  gaps between the levels: {', '.join(f'{g:g}' for g in P.gaps)} px; grid {P.scale[0]:.4f} x "
              f"{P.scale[1]:.4f} (le_stretch factor {P.stretch})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
