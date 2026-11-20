#!/usr/bin/env python3
"""Build a Layout Editor panel of all three levels that looks like the schematic (C3, ADR-023).

    python3 tools/schematic/build_layout_le.py --as-live                   # the cut-over candidate, all three levels
    python3 tools/schematic/build_layout_le.py --as-live --check           # fail if it is stale
    python3 tools/schematic/build_layout_le.py --as-live --review          # the same, staging not yet approved
    python3 tools/schematic/build_layout_le.py --levels staging --as-live   # staging alone (the candidate's base)
    python3 tools/schematic/build_layout_le.py --approve-staging           # record the owner-approved staging panel

Every run is --as-live and writes a cut-over candidate. The viewing trials, a "Layout (generated)" panel beside the
live one fitted into the le_window (tables_layout.xml of three levels with its own smaller labels, and
tables_layout_staging.xml of staging alone), are retired (owner, 2026-11-17): the candidates show every level. A run
without --as-live stops and says so.

One input path (owner, 2026-11-17, the device-map switch-over). Every level is drawn from its device map: staging
from the level 1 rows of devices.csv, control_points_staging.csv and staging_masts.csv (staging_device_map.load: each switch's
turnout and OS block, each track's blocks in order by the drawing's keys, each switch's normal leg from
switch_legs.csv, its turnout ident from switches.csv), main and upper from the rest of devices.csv and
main_upper_masts.csv (level_names, level_masts). The panel's own icons and labels, and its attributes, are
panel_items.json (panel_items.py): the status cluster panel_status.py drives, the frame captions, the helix
destination labels and the backdrop, each tied to the staging track. The occupancy lamps and station clusters are
parked with the Dispatcher System (jmri/layouts/hart/parked/staging_panel_lamps.json); Entry/Exit sensors are not
bound (parked). The frozen hand-drawn inputs (staging_le/, le_inputs.py) and the carried overlay (le_overlay.py) are
retired. The build reads no panel in the tables: only the schematic, those files and the tables' beans.

Three levels (owner, 2026-11-16). `--as-live` (levels all) writes the cut-over candidate
jmri/layouts/hart/output/trial/tables_cutover.xml: first the staging candidate below (--levels staging --as-live, drawn
at staging's own fit widened by the page's le_stretch factor, so the three-level panel has the window's shape; the
plugin's check_stretch), then all three bands at that candidate's grid (no fitting: the panel is larger than the window,
the page's le_window, which stays as it is; zoom to fit), each band's labels placed in rounds of their own (the plugin's
labels_by_band), staging against the left edge (the plugin's band_align) and the main level below everything the staging
candidate holds (the plugin's le_title_clear, with the panel items' bottom under staging as band_bottoms).
check_staging_unchanged then stops unless the staging candidate is in it unchanged: every bean, every other panel, every
staging element, but the main and upper objects and the helix joins (the staging helix tracks run on to the main level,
so their end bumpers become anchors, inside one block: each helix track is one block from staging up the helix,
Track Helix Outer and Track Helix Inner, owner 2026-11-20; the build binds the staging block to the device map's
sensor, which the guard accepts, without_level_detector). Main
and upper take the device map's names (device_names; a crossover's two halves are one turnout, drawn as one single
crossover on one level, or as two Layout Editor turnouts on one turnout for 127 and 131, whose halves stand on two
levels, and for 121 and 125, whose halves the plan joins leg C to leg B; each half is closed on the leg away from its
other half), on internal system names, each block bound to its virtual occupancy sensor (IS:HART:C3:B:<block key>;
level_sensors), which a LogixNG sets clear when the tables load (add_level_clear); their track names are the device
map's block names without "Track ", left out where there is no room (names_last); one block contents icon per block at
12 px (staging keeps 13; preferences.json[main_upper]'s le_band_labels).

Parked features (owner, 2026-11-17; hartlib.parked, PARKED). After the staging guard the three-level candidate's
Entry/Exit, Dispatcher System and USS CTC elements are left out (parked.split); their live data is the snapshot in
jmri/layouts/hart/parked/tables_parked.xml. The released tables are that candidate with its Signal Mast Logic from
stock discovery in a sandbox (jmri/layouts/hart/parked/README.md).

The tables it builds on (ADR-029, R9c): the generator's base (hartlib.tables_build.base), the template
(data/tables_template.xml) with the staging beans of devices.csv, never the live tables.xml, which is an output
(tools/schematic/build_tables.py writes it from this build, the discovered Signal Mast Logic and the template). The
base holds no panel and no Signal Mast Logic; the build adds the main and upper objects and the panel after the
template's sections.

Staging alone. `--levels staging` draws the staging band alone: its helix tracks end at end bumpers, its rows le_row px
apart (the page preference), and no main or upper object is added to the tables. It writes
jmri/layouts/hart/output/trial/tables_cutover_staging.xml: the tables with the "HART Railroad" panel replaced, in its
place, by the generated one under that name and panel_items.json's attributes, sized by the le_window and opening at
0, 0; everything else unchanged. Staging's turnouts
keep their switches.csv idents; anchors, end bumpers and segments take generated idents (owner, 2026-11-17), which
staging_masts.csv names them by block, not by ident. Every staging mast goes in the one slot whose facing and protected blocks and kind of
slot are its own (staging_masts.csv; the plugin's slots.py holds JMRI's rules), its icon on the right-hand side of the
train it governs, hidden for a virtual mast; check_device_masts stops on a mast two slots would fit or one on another
turnout than its switch's. Staging's helix joins carry the next level's block ("joins": "other"), the same helix block,
so the join is no block boundary and no mast stands there. The panel carries the
hidden generated-panel label (hartlib.tables.GENERATED_PANEL_MARKER): the build starts only from tables that hold
it, and the Stage 1 repairs of the parked Dispatcher System run only on a panel that holds it. The staging
candidate's panel must match the owner-approved fingerprint (approval.py, approved_staging.sha256; --review skips it, --approve-staging records it).

The candidates are for looking at only until the owner's cut-over. This script never writes the live tables.xml or
anything in the JMRI profile (main() refuses such an --out). The plugin is the pinned submodule, or SCHEMATIC_PLUGIN
(as publish_draft.py).
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel_items  # noqa: E402  the panel's fixed items and attributes (panel_items.json)
import publish_draft as pd  # noqa: E402  DATA, GRAPHS, INPUTS, hartlib paths and the pinned plugin
import staging_device_map as sdm  # noqa: E402  the staging device map
from hartlib import parked, paths, tables, tables_build  # noqa: E402
# The build's parts and the staging candidate's approval fingerprint (approval.py): their names are re-exported
# below, so callers and tests read them here. Patch a name in the module that calls it (le_names.placeholder_names).
from le_common import (  # noqa: E402,F401  re-exported: callers and tests read them here
    STAGING, staging_switches, DEVICE_MAP, TURNOUT_SYS, BLOCK_SYS, LAYOUT_BLOCK_FIRST, BuildError, plugin,
    schematic, slots_module, band_key, bare, read_csv,
)
from approval import (  # noqa: E402,F401  re-exported: callers and tests read them here
    ApprovalError, STAGING_APPROVED as APPROVED, approved_fingerprint, check_approved, read_approved, write_approved,
)
from le_names import (  # noqa: E402,F401  re-exported: callers and tests read them here
    crossover_strands, runs,
    staging_lengths, MAIN_UPPER_MASTS, read_level_masts, lcos_rule, lcos_named, level_masts, placeholder_names,
    device_names, level_names, shared_turnouts, named_bands,
)
from le_checks import (  # noqa: E402,F401  re-exported: callers and tests read them here
    mast_band, check_level_slots, check_unplaced, turnout_facts, check_device_masts,
)
from le_tables import (  # noqa: E402,F401  re-exported: callers and tests read them here
    BLOCK_NUMBERED_AS, APPENDED_BLOCKS, RETIRED_BLOCKS, NUMBERING, load_numbering, COMMENT, bean, r1, block_sort,
    RETIRED_TURNOUT_PREFIX, retire_yard_ladder, replace, place, canon, is_level_bean, level_items,
    PANEL_SIZE_ATTRS, helix_join_changes, check_staging_unchanged, numbered_blocks, STRIPPED, strip_build_owned,
    level_sensors, SENSOR_COMMENT, add_level_sensors, MALE_DEBUGGER, MALE_ACTION, male_socket, add_level_clear,
    add_level_objects, SIGNAL_NOTE, HEAD_CLASS, MAST_CLASS, add_level_signals,
)

CUTOVER = paths.LAYOUT_OUTPUT / "trial" / "tables_cutover.xml"                    # all three levels (the candidate)
CUTOVER_STAGING = paths.LAYOUT_OUTPUT / "trial" / "tables_cutover_staging.xml"    # staging alone (the guard's base)
LEVELS = ("all", "staging")
PANEL_ITEMS = pd.DATA / "panel_items.json"
TEMPLATE_PANEL = "HART Railroad"     # the panel the cut-over candidate replaces, and its name
RETIRED_TRIAL = ("the viewing trials (tables_layout.xml, tables_layout_staging.xml) are retired (owner, 2026-11-17): "
                 "add --as-live for the three-level cut-over candidate (tables_cutover.xml), or --levels staging "
                 "--as-live for the staging candidate (tables_cutover_staging.xml)")

# The window the panel opens in at 100% zoom (the page's le_window) and the rows staging is drawn at (le_row) are
# preferences.json[main_upper]'s, read through the plugin (le.window, le.row); their notes there say why.
# The cut-over candidates' grid (owner, 2026-11-16): staging's own fit to the window (the grid's scale across and down
# when the staging band alone is fitted into the le_window at le_row, found by the plugin's fit in each staging
# cut-over build and kept as P.staging_fit) widened by preferences.json[main_upper]'s le_stretch (the plugin's
# stretched and check_stretch). The geometry knobs of the Layout Editor drawing (le_shift, le_longer_straights,
# le_crossover_angle, le_mast_room, le_name_room, le_title_clear,
# le_stretch, le_window, le_row, and the label options: staging's le_labels extra_steps, extra_follow, name_columns
# and lamp_columns, preferences.json[main_upper]'s page-wide le_labels and each level's le_band_labels) are layer 3
# preferences the plugin reads (schematic/le_prefs.py, schematic/le_labels.py). Crossovers 101 and 103, one
# three-way part in the plan, are drawn tight and split by the plugin's rule (schematic-maps 0.1.48), not a
# preference.
# The features parked out of the cut-over candidate into jmri/layouts/hart/parked/tables_parked.xml (owner,
# 2026-11-17; hartlib.parked): Entry/Exit, the stock Dispatcher System and the USS CTC machine. Unpark one by taking
# it out of hartlib.parked.PARKED and rebuilding.
PARKED = parked.PARKED


BASE_NAME = "the generated base (data/tables_template.xml and devices.csv)"


def base_tables() -> bytes:
    """The tables a build draws on: hartlib.tables_build.base, the template with the staging beans of devices.csv.
    BuildError on anything that stops it, naming the file."""
    try:
        return tables_build.base().tobytes()
    except (tables_build.TablesBuildError, tables_build.devices.DevicesError) as exc:
        raise BuildError(f"tables base: {exc}") from None


def build(bands=None, levels: str = "all", as_live: bool = False,
          approved: Path | None = APPROVED, page: dict | None = None, base_data: bytes | None = None):
    """(tables bytes, the plugin's Panel, {band key: names}, bands). `levels` "all" draws every band, main and upper
    under the device map's names (level_names) and their objects added to the tables; "staging" draws staging alone,
    its helix ends as end bumpers, and adds no table object. `as_live` writes a cut-over candidate: the base
    (base_tables; module text) with the panel added, under panel_items.json's name and attributes; with "all",
    drawn at the staging candidate's grid and checked to hold it
    unchanged (check_staging_unchanged; module text). `as_live` must be given: without it
    (the viewing trials, retired, owner 2026-11-17) the build stops. Staging's facts come from the staging device map
    (staging_device_map.load); nothing is read from a panel in the tables. `approved`: the fingerprint the staging
    candidate's panel must match (check_approved; None skips it, for --approve-staging and --review).
    `base_data`: base_tables() already built (the three-level build passes it to the staging candidate it draws
    first, so the base is built once)."""
    if levels not in LEVELS:
        raise BuildError(f"levels must be one of {', '.join(LEVELS)}, not {levels!r}")
    if not as_live:
        raise BuildError(RETIRED_TRIAL)
    try:
        items = panel_items.load(PANEL_ITEMS)
    except panel_items.ItemsError as exc:
        raise BuildError(f"panel items: {exc}") from None
    _sheet, le_mod, core = plugin()
    # the page options come from the solved sheet (schematic()), for the bands given too unless `page` is (the
    # three-level build passes its own on to the staging candidate it draws first)
    if bands is None:
        bands, solved_page = schematic()
    else:
        solved_page = schematic()[1]
    page = solved_page if page is None else page
    if "le_row" not in page:        # le.row falls back to the plugin's rows: HART's staging rows are a preference
        raise BuildError("the page's preferences (preferences.json[main_upper]) hold no le_row")
    if "le_labels" not in page:     # the plugin's defaults would draw every switch number unprefixed, staging's too
        raise BuildError("the page's preferences (preferences.json[main_upper]) hold no le_labels")
    try:
        fit, staging_row = le_mod.window(page), le_mod.row(page)
    except core.SchematicError as exc:
        raise BuildError(f"schematic le: {exc}") from None
    # as the Layout Editor draws them (the preferences' le_shift, le_longer_straights; once): so the names below are
    # read off the bands drawn, before named_bands relabels a crossover's halves
    try:
        bands = le_mod.drawn_bands(bands, page)
    except core.SchematicError as exc:
        raise BuildError(f"schematic le: {exc}") from None
    # The build reads no panel and no live tables: it draws on the generator's base (module text)
    if base_data is None:
        base_data = base_tables()
    base = None             # the three-level candidate: the staging candidate it must hold unchanged, and its grid
    if levels == "all":
        base = build(bands, "staging", True, approved=approved, page=page, base_data=base_data)
    keys = [band_key(t) for t, _, _ in bands]
    if STAGING not in keys:
        raise BuildError(f"no {STAGING} band in the schematic (bands: {', '.join(keys)})")
    if levels == "staging":
        bands = [bands[keys.index(STAGING)]]
        keys = [STAGING]
    if band_key(bands[0][0]) != STAGING:
        raise BuildError(f"the first band is {bands[0][0]!r}, not {STAGING}")
    doc = tables.loads(base_data)
    root = doc.root
    if root.find("LayoutEditor") is not None:
        raise BuildError(f"{BASE_NAME} holds a Layout Editor panel; the build adds the one panel")
    panel_name = TEMPLATE_PANEL

    names, lengths = level_names(bands, le_mod, page=page) if levels == "all" else ({}, {})
    level_rows = []
    if levels == "all":                 # the main and upper control-point masts (main_upper_masts.csv)
        level_rows = read_level_masts()
    shared_turnouts(names)
    if base is not None:        # the staging candidate above read the staging device map from the same band: reuse it
        names[STAGING] = copy.deepcopy(base[2][STAGING])
    else:
        try:
            names[STAGING] = sdm.load(bands[0][1])
        except sdm.StagingMapError as exc:
            raise BuildError(f"staging device map: {exc}") from None
    system = tables.mast_system_names(root)
    absent = sorted(m["mast"] for m in names[STAGING]["masts"] if m["mast"] not in system)
    if absent:
        raise BuildError(f"staging_masts.csv names masts that are not in the signal mast table: {absent}")
    if levels == "all":                 # after staging's names: a helix intermediate protects a staging track
        level_masts(names, level_rows)
        names[STAGING]["joins"] = "other"   # staging's helix ends join the next level (helix-join release, 2026-11-17)
    names[STAGING]["lengths"] = staging_lengths(names[STAGING])
    try:
        if base is not None:        # staging's own grid, so staging is drawn as in its candidate; no fitting
            scale = base[1].scale
            if page.get("band_align"):
                raise BuildError("the schematic's page options hold band_align; HART sets it for the panel here")
            # staging against the left edge, where it stands drawn alone, however wide the other levels are; its
            # labels placed as when it is drawn alone (labels_by_band); and the gaps between the levels as small as
            # is clean (owner, 2026-11-16; the page's le_title_clear): for staging, below everything its candidate
            # holds (its status cluster stands in the gap: band_bottoms). Every crossover at its level's
            # le_crossover_angle, however each level is stretched
            S = base[1]
            P = le_mod.panel(named_bands(bands, names), names, cell=le_mod.CELL * scale[0],
                             row=staging_row * scale[1], page=dict(page, band_align={STAGING: "left"}),
                             labels_by_band=True, band_bottoms={STAGING: S.items["bottom"] - S.band_boxes[0][3]})
            P.scale, P.fit, P.stretch = scale, None, S.stretch
        else:                       # the staging candidate: the cut-over grid, no fitting (it scrolls in the le_window)
            # staging's own fit to the le_window, which the cut-over grid is stretched from
            fitted = le_mod.panel(bands, names, page=page, fit=fit, row=staging_row).scale
            scale, stretch = le_mod.stretched(fitted, page)
            P = le_mod.panel(bands, names, cell=le_mod.CELL * scale[0], row=staging_row * scale[1],
                             page=page)
            P.scale, P.fit, P.staging_fit, P.stretch = scale, None, fitted, stretch
    except core.SchematicError as exc:
        raise BuildError(f"schematic le: {exc}") from None
    P.mast_notes = check_unplaced(P)
    check_device_masts(P, names[STAGING]["masts"], le_mod)      # each mast in one slot, on its switch's turnout
    check_level_slots(P, level_rows, le_mod)

    # staging: every name must already be in the base (devices.csv)
    staging_turnouts = set(names[STAGING]["turnouts"].values())
    staging_blocks = set(names[STAGING]["os"].values()) | {b for v in names[STAGING]["blocks"].values() for b in v}
    live_turnouts = tables.by_any_name(tables.turnouts(root))
    live_lb = {tables.user_name(b) for b in tables.layout_blocks(root)}
    missing = sorted(t for t in staging_turnouts if t not in live_turnouts) + \
        sorted(b for b in staging_blocks if b not in live_lb)
    if missing:
        raise BuildError(f"staging names not in {BASE_NAME}: {missing}")
    if levels == "staging" and set(P.blocks) - staging_blocks:
        raise BuildError(f"the staging panel draws blocks that are not live: {sorted(set(P.blocks) - staging_blocks)}")
    if levels == "all":
        add_level_objects(root, P, names, lengths, staging_blocks, startup_thrown(bands))
        add_level_signals(root, level_rows)

    try:
        attrs, options = panel_items.panel_attributes(items)
    except panel_items.ItemsError as exc:
        raise BuildError(f"panel items: {exc}") from None
    # the panel's own items by rule (panel_items.json), tied to the staging track, so they stand where the staging
    # candidate has them on three levels too (by the staging band's own track: a helix block runs on up a level)
    panel_el = le_mod.to_xml(P, panel_name, attrs, options)
    frame = {P.name(o["ident"]) for o in P.segments + P.turnouts if o["band"] == 0}
    try:
        P.items = panel_items.place(panel_el, items, le_mod, slots_module(), fit, le_mod.CHROME,
                                    frame_idents=frame)
    except panel_items.ItemsError as exc:
        raise BuildError(f"panel items: {exc}") from None
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
    if levels == "staging" and approved is not None:
        try:
            check_approved(panel_el, approved)
        except ApprovalError as exc:
            raise BuildError(str(exc)) from None
    place(root, [panel_el], 1)          # after the template's last section
    if base is not None:
        P.staging_same = check_staging_unchanged(base, doc.tobytes(), P, panel_name)
        P.staging_data = base[0]
        try:
            le_mod.check_stretch(P.items["size"], fit, page)
        except core.SchematicError as exc:
            raise BuildError(f"schematic le: {exc}") from None
        # the parked features (PARKED, owner 2026-11-17) leave the cut-over candidate for the parked file,
        # after the staging guard, which compares the two candidates whole
        try:
            P.parked_doc = parked.split(root, PARKED)
        except parked.ParkError as exc:
            raise BuildError(f"parking: {exc}") from None
        P.retired = retire_yard_ladder(root)
    return doc.tobytes(), P, names, bands


def live_target(out: Path) -> bool:
    """True when `out` is the live tables.xml or lies in the JMRI profile (by path or through a link)."""
    real = Path(os.path.realpath(out))
    # the checkout's own file, whatever HART_TABLES points TABLES_XML at
    if real in (Path(os.path.realpath(paths.REPO_TABLES_XML)), Path(os.path.realpath(paths.TABLES_XML))):
        return True
    profile = Path(os.path.realpath(paths.JMRI_USER_FILES))
    return real == profile or profile in real.parents


def startup_thrown(bands) -> frozenset:
    """The main and upper turnouts ("Switch <n>") that start Thrown: those whose main route runs through leg C and
    not leg B, so every virtual turnout lines the main line when the tables load (owner, 2026-11-19: 227 and 229
    at the peninsula loop). A double crossover or a crossover half stays Closed (straight through)."""
    import build_device_map as bdm      # imports this module's plugin path: here, not at load
    out = set()
    for title, band, _opts in bands:
        if not bdm.band_level(title):
            continue
        for d in band["nodes"].values():
            if d["kind"] != "switch":
                continue
            main = {p: bool(sid and band["strands"][sid]["main"])
                    for p in "BC" for sid in [d["ins"].get(p) or d["outs"].get(p)]}
            if main["C"] and not main["B"]:
                out.add(f"Switch {bdm.base(d['label'])}")
    return frozenset(out)


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
                    help="required (the viewing trials are retired): write the cut-over candidate, the live panel "
                         "replaced by the new one; with --levels all (the default) all three levels at staging's grid (tables_cutover.xml), with --levels "
                         "staging staging alone (tables_cutover_staging.xml)")
    ap.add_argument("--out", type=Path, help="where to write (default: the candidate for these levels: "
                    "tables_cutover.xml or tables_cutover_staging.xml)")
    ap.add_argument("--review", action="store_true",
                    help="with --as-live: write the candidate for the owner to review although its staging panel is "
                         f"not the approved one ({paths.rel(APPROVED)} is not checked; the run says so)")
    ap.add_argument("--approve-staging", action="store_true",
                    help="after the owner approves the staging panel in PanelPro: record its fingerprint in "
                         f"{paths.rel(APPROVED)}, which both cut-over builds then check")
    args = ap.parse_args(argv)
    if not args.check:
        message = paths.check_only_message(Path(__file__).name)
        if message:
            print(f"ERROR: {message}")
            return 1
    cached.enter_context(pd.cache_on())     # after the HART_TABLES refusal: a refused run touches nothing
    if args.approve_staging:
        if args.check or args.as_live or args.out or args.levels is not None or args.review:
            print("ERROR: --approve-staging takes no other option")
            return 1
        try:
            data = build(levels="staging", as_live=True, approved=None)[0]
            write_approved(tables.layout_editor(tables.loads(data).root, TEMPLATE_PANEL))
        except (BuildError, ApprovalError) as exc:
            print(f"ERROR: {exc}")
            return 1
        print(f"wrote {paths.rel(APPROVED)}: the staging panel as the owner approved it")
        return 0
    if args.review and not args.as_live:
        print("ERROR: --review goes with --as-live")
        return 1
    levels = args.levels or "all"
    if not args.as_live:
        print(f"ERROR: {RETIRED_TRIAL}")
        return 1
    out = args.out or default_out(levels)
    if live_target(out):
        print(f"ERROR: {out} is the live tables or in the JMRI profile; the candidates are written beside them, "
              "never over them")
        return 1
    try:
        where = {}
        if args.review:
            where["approved"] = None
        data, P, _names, _bands = build(levels=levels, as_live=args.as_live, **where)
    except BuildError as exc:
        print(f"ERROR: {exc}")
        return 1
    _, le_mod, _ = plugin()
    summary = f"panel {TEMPLATE_PANEL!r}: {le_mod.summary(P)}"
    base = BASE_NAME
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
    print(f"  built on {base}")
    if args.review:
        print(f"  REVIEW: the staging panel was not checked against the approved one ({paths.rel(APPROVED)}); it is "
              "UNAPPROVED until the owner approves it in PanelPro and --approve-staging records it")
    if len(files) > 1:
        print(f"wrote {paths.rel(files[1][0])}: the staging candidate it holds")
    if isinstance(getattr(P, "parked_doc", None), ET.Element):
        where = f"kept in {paths.rel(parked.PARKED_XML)} (the live snapshot)"
        print(f"parked ({', '.join(sorted(PARKED))}), left out, {where}; taken out of {base}: " + "; ".join(
            f"{f}: " + (", ".join(f"{v} {k}" for k, v in sorted(c.items())) or "none")
            for f, c in parked.counts(P.parked_doc).items()))
    if getattr(P, "retired", None) is not None:
        print(f"yard ladder retired: {P.retired} internal turnouts and routes taken out of {base} "
              f"({RETIRED_TURNOUT_PREFIX}*)")
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
    same = getattr(P, "staging_same", None)     # never empty: the guard raises when no helix join is found
    if same is not None:
        print(f"  staging guard: the {'(unapproved) ' if args.review else 'approved '}staging candidate is held "
              + "unchanged but for the helix joins:")
        for line in same:
            print(f"    {line}")
    return 0


def staging_out(out: Path) -> Path:
    """Where the three-level candidate `out` writes the staging candidate it holds: tables_cutover.xml ->
    tables_cutover_staging.xml (CUTOVER_STAGING)."""
    return out.with_name(f"{out.stem}_staging{out.suffix}")


def default_out(levels: str) -> Path:
    """The candidate file for these levels, so --check always compares like with like."""
    return CUTOVER_STAGING if levels == "staging" else CUTOVER


if __name__ == "__main__":
    sys.exit(main())
