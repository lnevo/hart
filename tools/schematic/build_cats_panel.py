"""build_cats_panel.py [--check]

Generate the live CATS Designer desks for all three levels (staging, main, upper) from the schematic grid, with the
schematic-maps plugin's cats module (the code behind `schematic cats --bindings`): cats/panels/HART_CTC.xml (CTC)
and its ABS twin HART_ABS.xml, the desks the deploy installs (sync_hart_package.sh LIVE_PANELS) and the launchers
open (CATS cut-over; ADR-023). This script is their only writer; the hand-wired Designer panel HART_Digicon.xml is not
read. tools/check.sh compares the desks byte for byte with --check, holds them to their approval fingerprints
(check_approved.py) and checks them against the layout facts (tools/audit/check_layout_facts.py).

Bands stack in the sheet's order (staging on top). Staging is bound to the live JMRI objects through the bindings
file cats/panels/HART_CTC.bindings.json, which this script writes from the railroad's facts, never by
hand:
  switches.csv (level 1 rows)      which OS block each switch's points are in (and a crossover half's label, 23A
                                  or 23B, from its OS block's letter), which leg is closed and which thrown,
                                  and whether CATS normal is JMRI thrown (cats_inverted); Switch 9 and 13 follow them
  The device master + tables.xml          each switch's M2T turnout (cats_turnout_io.load_turnouts)
  cats_discipline blocks + tables.xml   each block's M2S sensor and discipline (digicon_lib.load_occupancy: the
                                  layout block table and the sensors, not a Layout Editor panel)
  signals.json[staging] + signal_head_plan.csv the masts drawn on staging (field and planned) and their templates
  The device master (level 1)   the block of a short unnamed track between two switches that has no JMRI block of its own:
                         the one block the staging device map's track between them holds
                         (staging_device_map.staging_chains)
Main and upper blocks are CTC on the CTC desk, as staging's are (CATS holds their signals and
releases them, so a route set from staging up the helix stops at the first main or upper signal); the ABS twin
turns them ABS with the rest. They take their names from the block rows of
the main and upper rows of the device master (by the schematic tracks each holds). Their switches
command and report the turnouts their device-master rows give (internal today, IT:HART:C3:<n>; cats_panel's
split_system_name), closed on the drawn leg B, which is
NORMAL; double crossover 225 too, its one turnout moving all four points, and a desk block per corner as in the
Layout Editor, OS Switch 225a to d on their corners' detectors, with the middle of its X a block of its own and no
detector: the plugin's `corners` binding, which opens a row between its tracks on the upper level), and their
control-point masts (masts.csv, on virtual heads) are drawn and bound as staging's are: each on the track
it faces at the switch it protects (level_signals), its CATS template the one staging's masts of its appearance type
take. Every main and upper desk block is bound to its virtual occupancy sensor (the device map's jmri_name,
IS:HART:C3:B:<block key>, hartlib.level_devices), as OCCUPIEDSPEC / UNOCCUPIEDSPEC (the physical plant is a draft,
swapped in later by the device map alone); the planned detector, when the
map has one, is kept in the bindings as _planned_occupied / _planned_unoccupied for the record and is not on the
panel. The middle of 225's X, a desk-only block, has no sensor. Each helix track is one desk
block over both bands it is drawn on (cats_helix_blocks "one": one JMRI block from its staging switch to its main
or upper switch), named and bound as the main and upper device map gives it (Track Helix Outer,
Track Helix Inner: its virtual sensor), the staging device map naming the same block for the staging piece.
Anything else without a JMRI block, an ambiguous track, or a fact that disagrees with the drawing stops the run.
The sheet is built once and tables.xml read once; bindings and panels come from the same plugin code.
The IOSPEC, STATION and SECSIGNAL conventions are the hand-wired desks' (cats_turnout_io.py, digicon_lib.py,
hartlib.cats). The header (fonts, counters, signal templates, train, job and crew stores, colours,
OPERATIONS, JMRI names) and the publication plate come from cats/data/generated_desk_header.xml, frozen from the
live desk; the ABS twin turns every CTC block ABS and says DS-ABS / ABS DIGICON on its plate, as the
hand-wired ABS desk did. Inputs and plugin are the same as tools/schematic/publish_draft.py (SCHEMATIC_PLUGIN for
other plugin code).

--check regenerates the files into a temporary folder and compares (exit 1 if any is stale). When SCHEMATIC_PLUGIN
is not set and the plugin submodule is not checked out or not at its pinned commit, --check prints SKIPPED and
exits 0 (a failure with SCHEMATIC_REQUIRED=1).
"""
import difflib
import importlib
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple, TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA, GRAPHS, INPUTS, hartlib paths and the pinned plugin
import build_device_map as bdm  # noqa: E402  the device map's naming helpers (base, band_level, natural)
import staging_device_map as sdm  # noqa: E402  the staging tracks and their blocks (the level 1 rows of the device master)
from hartlib import level_devices, level_masts, paths, railroad  # noqa: E402,F401  the tests read B.level_masts, B.railroad

sys.path[:0] = [str(paths.CATS_DIR / "scripts"), str(paths.LAYOUT_SCRIPTS)]

from cats_panel_facts import (DEVICE_MAP, CatsPanelError, DeviceMap, Facts, StagingTracks, load_device_map, load_facts,  # noqa: E402,F401
                              mast_type, staging_tracks, template_by_type)
from cats_panel import (split_system_name, MAIN_UPPER_DISCIPLINE, block_bindings,  # noqa: E402,F401
                        dark_bindings, dest, device_name, half_label, helix_block, inside_os, intermediate_signal,
                        legs_of, level_bands, level_mast_bindings, level_signals, level_switch_bindings,
                        loop_half_edge, mast_bindings, name_loop_halves, os_blocks, os_plates, plan_edge, placeholder,
                        planned_sensor, spec, staging_names, switch_bindings, switch_of, track_block, virtual_sensor,
                        xover_corners)
from cats_panel import Bands, BlockBinding, MastBinding, SwitchBinding, Unbound  # noqa: E402
from cats_panel_dress import (ABS_PLATE, HEADER, ORDER, PLATE_PX, dress, frozen_header, label_clashes,  # noqa: E402,F401
                              plate_box, right_edge, station_plates)

# The live desks (CATS cut-over, ADR-023): the names the hosts, launchers and shortcuts use. Nothing else writes them.
OUT = pd.REPO / "cats/panels/HART_CTC.xml"
OUT_ABS = OUT.with_name("HART_ABS.xml")
BINDINGS = OUT.with_name("HART_CTC.bindings.json")
BOUND_LEVEL = 1        # the level bound to JMRI: staging's band (its `level` in plan_overrides.json's staging section)
# The desks' window, cells per grid unit, helix blocks and row gaps are page preferences (preferences.json[main_upper]:
# cats_window, cats_cells_per_unit, cats_helix_blocks, cats_band_gap, cats_title_gap) the plugin reads (schematic/cats_prefs.py, cats.options),
# which also gives the cells the desk must fit in that window. cats_window is not set there: publish_draft.solved_sheet
# derives it from the page's host_screen (host_screen.py), the layout hosts' screen, as the Layout Editor's le_window.

Cells = tuple[int, int]         # (columns, rows), or a window's (width, height) in pixels


class DeskOptions(TypedDict):
    """The page's CATS preferences as the plugin's cats.options gives them, checked by desk_options: the desks'
    window in pixels and the cells they must fit in it are set, and each helix track is one block."""
    scale: Any                  # cats_cells_per_unit as the plugin's check_scale returns it (the plugin is untyped)
    helix_blocks: str
    band_gap: int | None        # None: cats.panel's default
    title_gap: int | None
    window: Cells
    fit: Cells


class DeskBindings(TypedDict):
    """The bindings file (HART_CTC.bindings.json) as bindings() writes it."""
    _note: str
    _main_upper_not_on_desk: dict[str, Unbound]
    switches: dict[str, SwitchBinding]
    blocks: dict[str, BlockBinding]
    masts: dict[str, MastBinding]


NOTE = ("Written by tools/schematic/build_cats_panel.py from the railroad's facts; do not edit. Main and upper switches "
        "command their internal turnouts, their masts are bound and their blocks report their virtual occupancy "
        "sensors (IS:HART:C3:B:); a block's planned detector, a draft, is kept as _planned_occupied / "
        "_planned_unoccupied.")


def plugin_modules(plugin: Path) -> tuple[ModuleType, ModuleType]:
    """The plugin's cats and sheet modules, imported from `plugin` (the same code the command would run)."""
    sys.path.insert(0, str(plugin))
    for name in [m for m in sys.modules if m == "schematic" or m.startswith("schematic.")]:
        if not str(getattr(sys.modules[name], "__file__", "")).startswith(str(plugin)):
            del sys.modules[name]                  # another copy of the plugin was imported first
    from schematic import cats, sheet
    return cats, sheet


def cats_le(cats: ModuleType) -> ModuleType:
    """The plugin's le module, beside its cats module."""
    return importlib.import_module(cats.__name__.rpartition(".")[0] + ".le")


def block_names(blocks: Mapping[str, BlockBinding]) -> set[str]:
    """The block name each desk block of `blocks` takes: its binding's name, else its panel name."""
    return {e.get("name", k) for k, e in blocks.items()}


def check_apart(staging: Mapping[str, BlockBinding], dark: Mapping[str, BlockBinding]) -> None:
    """Stop when a staging and a main or upper block binding share a panel name or the block name they take (which
    would make them one CATS block)."""
    clash = sorted(set(staging) & set(dark))
    if clash:
        raise CatsPanelError(f"staging and main/upper blocks share panel names {', '.join(clash)}")
    clash = sorted(block_names(staging) & block_names(dark))
    if clash:
        raise CatsPanelError(f"staging and main/upper desk blocks would both be {', '.join(clash)}")


def check_keys_apart(what: str, staging: Mapping[str, object], level: Mapping[str, object]) -> None:
    """Stop when staging's and main/upper's `what` bindings share a key (one would hide the other in the file)."""
    shared = sorted(set(staging) & set(level))
    if shared:
        raise CatsPanelError(f"staging and main/upper share {what} keys {', '.join(shared)}")


def bound_index(bands: Bands) -> int:
    """The index of the staging band, the one bound to the field: the band of level BOUND_LEVEL, found by its level
    (le_common.find_band), never by its title. Stops when no band, or several, are at that level."""
    try:
        found: int = sdm.lc.find_band(bands, BOUND_LEVEL)
    except sdm.lc.BuildError as exc:
        raise CatsPanelError(f"the band bound to the field: {exc}") from exc
    return found


def bindings(bands: Bands, cats: ModuleType, F: Facts, o: DeskOptions, page: Mapping[str, Any]) -> DeskBindings:
    """The bindings for every band, from the facts (see the module docstring); `o` the page's CATS preferences
    (desk_options), `page` the schematic's page preferences (the solved sheet's opts: the plugin's JSON)."""
    bi = bound_index(bands)
    _, band, opts = bands[bi]
    stored = staging_names(band, pd.DATA)       # the staging names, from the store of the folder solved from
    os_of = os_blocks(band, F, stored)
    out_sw = switch_bindings(band, F, os_of, stored)
    le_mod = cats_le(cats)
    level_sw = level_switch_bindings(bands, F, bi, bdm.dx_corners(bands, le_mod, page))
    # the panel's block names once the switches name their OS blocks (and a double crossover its corners)
    named: dict[str, dict[str, Any]] = {k: {"block": v["block"]} for k, v in out_sw.items()}
    named.update({k: {"corners": v["corners"]} for k, v in level_sw.items() if "corners" in v})
    P = cats.panel(bands, scale=o["scale"], helix_blocks=o["helix_blocks"],   # names only: no column trimming
                   band_gap=o["band_gap"], title_gap=o["title_gap"],
                   bindings={"switches": named})
    dark, log, missing, joined = dark_bindings(bands, cats, P, F, bi, stored)
    names = {k: v for k, v in P.names.items() if k[1].startswith(f"b{bi}:") and k not in joined}
    blocks = block_bindings(band, F, names, stored)
    print("\n".join(log))
    check_apart(blocks, dark)
    masts, level = mast_bindings(opts, F), level_mast_bindings(bands, F, bi)
    check_keys_apart("switch", out_sw, level_sw)
    check_keys_apart("mast", masts, level)
    return DeskBindings(_note=NOTE, _main_upper_not_on_desk=missing, switches={**out_sw, **level_sw},
                        blocks={**blocks, **dark}, masts={**masts, **level})


def desk_options(cats: ModuleType, page: Mapping[str, Any], bands: Bands) -> DeskOptions:
    """The page's CATS preferences (cats.options), which must hold the desks' window (they fit the dispatcher's) and
    each helix track one block over both bands (dark_bindings binds it as the main and upper device map gives it).
    CatsPanelError when they do not."""
    try:
        o = cats.options(page, bands)
    except cats.SchematicError as e:
        raise CatsPanelError(f"error: {e}") from e
    if o["fit"] is None or o["window"] is None:
        raise CatsPanelError("error: the page's preferences hold no cats_window; the desks must fit the dispatcher's "
                             "window")
    if o["helix_blocks"] != "one":
        raise CatsPanelError(f"error: cats_helix_blocks is {o['helix_blocks']!r}; the desks need \"one\" (a helix "
                             "track one block over both bands, as JMRI holds it)")
    return DeskOptions(scale=o["scale"], helix_blocks=o["helix_blocks"], band_gap=o["band_gap"],
                       title_gap=o["title_gap"], window=o["window"], fit=o["fit"])


def check_desk_faults(cats: ModuleType, P: object, fit: Cells) -> None:
    """Print the plugin's desk faults for panel P (cats.faults: two blocks landing in one cell, a desk wider than its
    `fit` window), the count first, and stop when there is one. They are what preferences.json[main_upper]'s
    level_leg pins on 115, 235 and 239 keep away (its _level_leg note). CatsPanelError on a fault."""
    found = cats.faults(P, fit)
    print(f"CATS desk faults: {len(found)}" + "".join(f"\n  {x}" for x in found))
    if found:
        raise CatsPanelError(f"error: the desk has {len(found)} fault(s), listed above")


def desk_plates() -> list[tuple[str, tuple[str, ...]]]:
    """[(station, its switches)] of stations.csv's desk_plate rows (hartlib.railroad_facts.read_stations): the control
    point plates both desks carry (Brick, Plane, Barn, East End, Princess, as the hand-built desk)."""
    from hartlib import errors, railroad_facts
    try:
        rows = railroad_facts.read_stations(pd.DATA / "stations.csv")
    except errors.FactsError as exc:
        raise CatsPanelError(f"error: {exc}") from exc
    return [(st.name, st.switches) for st in rows if st.desk_plate]


class Solved(NamedTuple):
    """The solved sheet the desks are drawn from: its bands, each loop half named, and its page preferences (the
    plugin's JSON)."""
    bands: Bands
    page: Mapping[str, Any]


def solved(sheet: ModuleType, F: Facts) -> Solved:
    """The sheet solved once (publish_draft.solved_sheet). CatsPanelError when the page's host_screen, which gives
    the desks' window, does not read."""
    try:
        s = pd.solved_sheet(sheet)
    except pd.host_screen.HostScreenError as exc:
        raise CatsPanelError(f"error: {exc}") from exc
    return Solved(name_loop_halves(s.bands, F.device), s.opts)


def desk_panel(cats: ModuleType, bands: Bands, o: DeskOptions, bound: Mapping[str, Any]) -> Any:
    """The plugin's panel of `bands` under the bindings `bound` (the bindings file's JSON), held to its window:
    check_desk_faults stops on a fault, and cats.check_fit is the backstop behind it. Returns the plugin's panel
    object (untyped). cats.SchematicError as the plugin stops; CatsPanelError on a fault."""
    fit = o["fit"]
    P = cats.panel(bands, scale=o["scale"], bindings=bound, max_cols=fit[0], helix_blocks=o["helix_blocks"],
                   band_gap=o["band_gap"], title_gap=o["title_gap"])
    check_desk_faults(cats, P, fit)
    cats.check_fit(P, *fit)
    return P


def write_desks(cats: ModuleType, P: Any, o: DeskOptions, frozen: tuple[list[ET.Element], list[ET.Element]],
                desks: Mapping[str, Path | None]) -> None:
    """Write panel P (the plugin's) as each desk of `desks` ({"CTC" or "ABS": its path, None to leave it out}),
    dressed with the frozen header and plate (`frozen`: frozen_header) and the station plates."""
    header, plate = frozen
    for desk, path in desks.items():
        if path is not None:
            xml = cats.to_xml(P, "CTC", header, o["window"])
            path.write_text(dress(cats, xml, header, plate, desk, o["fit"], desk_plates()), encoding="utf-8")


def report(cats: ModuleType, P: Any, bands: Bands, o: DeskOptions) -> None:
    """Print the desk's summary, size and the plugin's log. CatsPanelError when the log has a lost or clashing
    label: the desks keep few spare rows (cats_band_gap, cats_title_gap)."""
    cols, rows = cats.shown(P)
    g = cats.GRID_PX
    fit, window = o["fit"], o["window"]
    print(", ".join(t for t, _, _ in bands) + ": " + cats.summary(P) +
          f"; shows {cols} x {rows} cells ({cols * g} x {rows * g} pixels at the {g} pixel grid), "
          f"fit {fit[0]} x {fit[1]} in a {window[0]} x {window[1]} window")
    print("\n".join(P.log))
    clashes = label_clashes(P.log)
    if clashes:
        raise CatsPanelError("error: the desk's labels clash; give them room (cats_band_gap, cats_title_gap) or move "
                             "them:\n  " + "\n  ".join(clashes))


def generate(plugin: Path, out: Path, bindings_out: Path, out_abs: Path | None = None) -> None:
    """Build the sheet once and write the bindings and the desks with the same plugin code. CatsPanelError when a
    fact, the window or the labels do not fit."""
    cats, sheet = plugin_modules(plugin)
    F = load_facts()
    bands, page = solved(sheet, F)
    o = desk_options(cats, page, bands)
    level_signals(bands, F, bound_index(bands))
    text = json.dumps(bindings(bands, cats, F, o, page), indent=1, sort_keys=True) + "\n"
    bindings_out.write_text(text, encoding="utf-8")
    frozen = frozen_header()
    try:
        P = desk_panel(cats, bands, o, json.loads(text))
        write_desks(cats, P, o, frozen, {"CTC": out, "ABS": out_abs})
    except cats.SchematicError as e:
        raise CatsPanelError(f"error: {e}") from e
    report(cats, P, bands, o)


def compare(fresh: Mapping[Path, Path], check: bool) -> int:
    """Hold each live file to its fresh build (`fresh`: {live path: fresh path}): print current or stale, with a
    diff, under `check`; else write each stale one. The number of stale files under `check`, else 0."""
    stale = 0
    for target, new_file in fresh.items():
        new = new_file.read_text(encoding="utf-8")
        old = target.read_text(encoding="utf-8") if target.exists() else ""
        rel = target.relative_to(pd.REPO)
        if new == old:
            print(f"{rel} is current")
        elif check:
            stale += 1
            print(f"{rel} is stale; run python3 tools/schematic/build_cats_panel.py")
            sys.stdout.writelines(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                                       target.name, "fresh", n=1))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(new, encoding="utf-8")
            print(f"wrote {rel}")
    return stale


def main(argv: Sequence[str]) -> int:
    """Exit status: 0 current or written, 1 a stale file under --check or a named error (its message on stderr),
    2 a bad argument. --help prints the docstring."""
    if {"-h", "--help"} & set(argv):     # help wins over --check and over a typo beside it: it only prints
        print(__doc__ or "build_cats_panel.py [--check]")       # python -OO strips the docstring
        return 0
    unknown = [a for a in argv if a != "--check"]
    if unknown:         # a typo must not fall through to a rebuild
        print(f"build_cats_panel.py: unknown argument {unknown[0]!r}; usage: build_cats_panel.py [--check] (--help for more)",
              file=sys.stderr)
        return 2
    check = "--check" in argv
    if not check:
        pd.paths.exit_if_overridden(Path(__file__).name)
    try:
        plugin = pd.plugin()
    except pd.PluginMissing as e:
        if not check:
            print(e, file=sys.stderr)
            return 1
        print(f"SKIPPED CATS panel check: {e}")
        return 1 if os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0
    with tempfile.TemporaryDirectory() as tmp:
        fresh = {OUT: Path(tmp) / OUT.name, OUT_ABS: Path(tmp) / OUT_ABS.name, BINDINGS: Path(tmp) / BINDINGS.name}
        try:
            generate(plugin, fresh[OUT], fresh[BINDINGS], fresh[OUT_ABS])
        except CatsPanelError as exc:       # a fact the desks need is wrong: the message names it
            print(exc, file=sys.stderr)
            return 1
        return 1 if compare(fresh, check) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
