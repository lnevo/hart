#!/usr/bin/env python3
"""Staging's facts in the device map's form: the source the Layout Editor build, the signals and the CATS desks read.

The turnout and feedback rows of level 1 of the device master are kept by hand but for their wiring cells, which
build_device_map.py writes from wiring.csv (stations.csv's desk areas are staging's control points,
build_staging_sets.py). The block and occupancy rows are the one block builder's (build_device_map.py, block_layer),
which carries each row's field facts over, writes its detector's wiring from wiring.csv (level 1 rows) and owns which
blocks there are and what each holds; it writes the mast and head rows too (device_map_masts.py, from those block
rows), and build_masts.py writes masts.csv from them. Edit these files, not a panel. This module reads them (load,
load_masts, load_signal_masts, mast_facts) and stops on a file not in its shape; check_device_master.py --check
(`make panels`, tools/check.sh) holds them, and every device row, to tables.xml and the schematic.

Staging's objects are field devices: every system name, user name and binding here is the railroad's own.

Files (jmri/layouts/hart/data/, schematic/ for the rest):
- the level 1 rows of the device master (hartlib.devices.device_map_lines). Layers as main and upper: turnout (and its LCC alias
  "DCC Switch <n>"), fb, block, occupancy, mast, head. Staging is the field, so system_name is the live device;
  jmri_name is the name tables.xml and the panels bind it by: a turnout's is the Layout Editor's turnoutname (some
  bind "M2T408", some "Switch 23"), every other row's its system name. trial_name is the link to the drawing, as for
  main and upper (placeholders(), below). The facts are in columns (hartlib.railroad.DEVICE_FACTS, checked by
  device_facts; the comment and notes stay text for people): one occupancy row per detector, its `blocks` the blocks
  it serves (a detector that serves several blocks lists each) and its `detector` wired, all of staging's being in
  the field; a block's `stop` "yes" for a Dispatcher System station, as its tables.xml comment marks it ("; stop",
  checked); a mast's `switch`, `facing` and `protects` as masts.csv has them. The rules every level's rows
  keep are check_device_master.row_problems', which load() runs on these rows.
  A helix block (plan_overrides.json: Track Helix Outer, Track Helix Inner) is one JMRI block from its staging switch
  up the helix: its staging piece is a block row here, and its detector is the occupancy row of
  levels 2 and 3 of the device master, which name the same block for the piece on its level (check_device_master.check_rows).
- parts (the device master's part_of, role part): a short piece of track between two switches has a block
  row of its own that names the block it is part of (the lower-numbered switch's OS block by rule, or the one
  block_overrides.csv gives it), and its trial_name. A part is a JMRI block of its own on that block's occupancy
  sensor: load() draws its pieces as the part, and os_layer reads them inside its block, as the
  masts do. The device maps leave parts out (hartlib.devices.OUT_OF_MAPS), so load() reads them from the master.
- stations.csv (level, station, switches, tracks, desk_code, notes): the stations, and through their desk codes
  staging's control points, the desk areas (hartlib.railroad_facts.read_desk_areas, the one reader; desk_areas()
  here). build_staging_sets.py writes plan_generated.json's staging section (control_points, stations and
  station_tracks) and the `detail_sheets` preference from it and sheets.csv (other readers take the areas' rows
  through hartlib.railroad_facts.station_group_rows).
- masts.csv (hartlib.level_masts, every level's masts), its level 1 rows. A mast's kind of slot follows from its
  row (mast_kind): a switch number means a turnout mast, no protected block an end bumper (buffer stop) mast, else an
  anchor mast. Hidden is a virtual mast (IF$vsm), its icon size hartlib.tables.mast_icon_size. Each staging row
  carries its plan facts (its schematic run and lengths: level_masts.PLAN_FIELDS); build_signals.py writes
  signals.json's staging section from them (load_signal_masts, signal_rows).

Readers: build_layout_le.py (load), build_signals.py (load_signal_masts, staging_chains), build_cats_panel.py
(staging_chains), hartlib.railroad's masts and check_layout_facts.py (masts.csv),
test_le_mast_parity.py (mast_facts).

Trial names (placeholders()): the links from the rows to the drawing, by switch numbers and legs, so they survive a
new AnyRail export, whose edge and node ids change every time. Each is resolved to the drawing's
ids when the files are read, and one that matches nothing, or more than one thing, stops.
- turnout: "Switch <n>" (both halves of a single crossover: one turnout).
- OS block: "OS Switch <n>" of a plain switch; "OS <n> A-<end>" of a crossover half, by where the run from its leg A
  goes (staging's crossovers 7, 23 and 35 have an OS block per half: OS Switch 7 and 7b, 23a and 23b, 35a and 35b;
  the half's key is not written as a block name, so check_name_copies.py does not take it for one).
- track block: "Track <end>-<end>" for the run between two ends, each a switch label and the leg the run leaves
  it by ("17C"; a lettered crossover half on main and upper "121AB", Switch 121A's leg B; a double crossover's leg
  "225D"), "end" for a bumper or "helix" (end_key), the lower switch first; a run that ends at a connector is keyed
  by the switch and leg beyond it on the other band (band_refs); " #<i>" for the i-th of a run's pieces (a run
  folded at a turnback, a balloon loop) from that first end; " <k>/<n>" for the k-th of the piece's n blocks from
  that end (Scale was "Track 5C-7B 1/2", OS Switch 7 "2/2").
The track keys are one grammar for every level: main and upper's track and part rows take them
too (build_device_map.level_trials), where they used to name AnyRail plan edges ("Track e33"). A block that several
tracks or a switch share lists every placeholder, comma separated, in key order; a part's pieces are on its own row.
Every piece of the drawing is on exactly one row.

The panel's own icons and labels are not device facts and are not here: the status cluster, captions and backdrop
are in panel_items.json (panel_items.py); the occupancy lamps and station clusters are parked with the Dispatcher
System (jmri/layouts/hart/parked/staging_panel_lamps.json).
"""
from __future__ import annotations

import re
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, TypeVar

sys.path.insert(0, str(Path(__file__).resolve().parent))
import le_common as lc  # noqa: E402  the band key, plugin, solved schematic and the files the build reads
import le_names as ln  # noqa: E402  runs and crossovers
import mast_rule as mr  # noqa: E402  the helix tracks (plan_overrides.json)
import publish_draft as pd  # noqa: E402  DATA and the plugin cache
from hartlib import device_ids, devices, drawing_keys, layer_files, level_masts, paths, railroad, tables, track_names  # noqa: E402
from mast_plan import Band, Bands, Leg  # noqa: E402  the plugin's solved band shapes
from staging_records import (  # noqa: E402,F401  the records; re-exported: callers read them from this module
    Beyond, Idents, Joined, MastFact, MastKind, Ref, Row, SignalMast, StagingMast, StagingNames, TrackRuns)

LEVEL = 1
DEVICE_MAP = devices.MASTER     # the master: its level 1 rows are staging's device map
STATIONS = pd.DATA / "stations.csv"          # the stations; their desk areas are staging's control points
INTERLOCKINGS = railroad.Sources.under().interlockings     # every level's (the control points a row's cp may name)
MASTS = level_masts.PATH         # masts.csv, every level's masts: staging's are its level 1 rows
SHEET = "staging"           # staging's section of the layer files (plan_overrides.json, signals.json)
LIST = level_masts.LIST       # between the items of a cell (a run, a plan edge's names)
# what signals.json's staging section names as its source: the file the masts were first read from (the hand-drawn panel's)
SIGNALS_SOURCE = "tables.xml"
LAYERS = ("turnout", "fb", "block", "occupancy", "mast", "head")
TRACK_RE = re.compile(r"Track (\S+?(?: #\d+)?)(?: (\d+)/(\d+))?")       # a track by its piece (piece_refs), k-th of n blocks


T = TypeVar("T")


class StagingMapError(RuntimeError):
    """Staging's device-map rows, masts.csv's staging rows or the staging drawing break a rule this module reads them
    by; the message names the file and row, or the switch or track."""


def overrides() -> dict[str, Any]:
    """Staging's section of plan_overrides.json (hartlib.layer_files; LayerFileError if it is missing)."""
    return layer_files.read("plan_overrides", SHEET, pd.DATA)


# ---------------------------------------------------------------- placeholders: the drawing's keys


def crossover_halves(band: Band) -> dict[str, str]:
    """{node: other half} for each switch that is half of a single crossover (two switches of one label joined C to C,
    build_layout_le.crossover_strands)."""
    out: dict[str, str] = {}
    for sid in ln.crossover_strands(band):
        u, v = band["strands"][sid]["src"][0], band["strands"][sid]["dst"][0]
        out[u], out[v] = v, u
    return out


def end_key(band: Band, end: Leg, beyond: Beyond | None = None) -> str:
    """A run's end (node, port) by what survives a new export: a switch's label and leg ("17C", "121AB", a double
    crossover's "225D"), "helix" for a helix end, the far side's key for a connector (`beyond`: a function of the end,
    band_refs), "end" for any other track end (a bumper). StagingMapError on a connector with no `beyond`."""
    d = band["nodes"][end[0]]
    if d["kind"] in ("switch", "dx"):
        return f"{lc.bare(d.get('label'))}{end[1]}"
    if d.get("sub") == "helix":
        return "helix"
    if d.get("sub") == "link":
        if beyond is None:
            raise StagingMapError(f"connector {end[0]}: a run ends at it, and nothing says what is beyond it")
        return beyond(end)
    return "end"


def band_refs(bands: Bands, joined: Joined, bi: int) -> dict[str, Ref]:
    """piece_refs of band `bi` of `bands` (the solved schematic), a run that ends at a connector keyed by the switch
    and leg where the run beyond it, on the band `joined` (the plugin's partners: {(band, node): (band, node)}) gives,
    ends: one track cut by a connector has one key on both bands. StagingMapError on a connector `joined` does not
    pair, or one whose run beyond ends at another connector."""
    def beyond(end: Leg) -> str:
        if (bi, end[0]) not in joined:
            raise StagingMapError(f"{bands[bi][0]}: connector {end[0]} is joined to no other band")
        bj, m = joined[(bi, end[0])]
        other = bands[bj][1]
        for start, _chain, stop in ln.runs(other):
            far = stop if start[0] == m else start if stop[0] == m else None
            if far is not None:
                if other["nodes"][far[0]].get("sub") == "link":
                    raise StagingMapError(f"{bands[bj][0]}: the run from connector {m} ends at another connector")
                return end_key(other, far)
        raise StagingMapError(f"{bands[bj][0]}: no run reaches connector {m}")
    return piece_refs(bands[bi][1], beyond)


def strand_names(bands: Bands, joined: Joined, bi: int, section: Mapping[str, Any],
                 owner: Mapping[tuple[str, str], str] | None = None, data: Path | None = None) -> dict[str, str]:
    """{strand id: its track's name, without "Track "} of every strand of band `bi` the name store names, looked up
    by the strand's ID part (band_refs) in hartlib.track_names (piece_names over `section`, the hand plan_overrides
    section of the band's drawing; `owner`, owner_names of `data`, default publish_draft.DATA), never read off the
    drawing. A strand of no named track has none."""
    return _names_by_ref(band_refs(bands, joined, bi), section, owner, data, bands[bi][0])


def staging_names(band: Band, data: Path, section: Mapping[str, Any] | None = None,
                  owner: Mapping[tuple[str, str], str] | None = None) -> dict[str, str]:
    """strand_names of the staging band alone (`band`, no connector: piece_refs), from the schematic folder `data` the
    band was solved from: staging's hand section there (`section`, default) and the owner rows beside it (`owner`,
    default)."""
    if section is None:
        try:
            section = layer_files.read("plan_overrides", SHEET, data)
        except layer_files.LayerFileError as exc:
            raise StagingMapError(str(exc)) from exc
    return _names_by_ref(piece_refs(band), section, owner, data, "staging")


def _names_by_ref(refs: Mapping[str, Ref], section: Mapping[str, Any], owner: Mapping[tuple[str, str], str] | None,
                  data: Path | None, where: str) -> dict[str, str]:
    """{strand id: its track's name} of each strand of `refs` whose piece the name store names
    (track_names.piece_names); StagingMapError naming `where` when the names do not read."""
    try:
        got = track_names.piece_names(section, {piece for piece, _rev in refs.values()}, owner,
                                      pd.DATA if data is None else data)
    except track_names.TrackNameError as exc:
        raise StagingMapError(f"{where}: {exc}") from exc
    return {sid: got[piece] for sid, (piece, _rev) in refs.items() if piece in got}


def piece_refs(band: Band, beyond: Beyond | None = None) -> dict[str, Ref]:
    """{strand id: (its piece reference, whether the strand runs against it)} of every strand of `band` outside a
    staging-style single crossover (two switches of one label joined C to C; their insides carry no blocks):
    "<end>-<end>" of its run (end_key, the lower first; `beyond` keys a connector end, band_refs) and " #<i>" when the
    run has several pieces. Stops when two runs share ends, which could not be told apart."""
    out: dict[str, Ref] = {}
    seen: dict[str, str] = {}
    for start, chain, stop in ln.runs(band, ln.crossover_strands(band)):
        a, b = end_key(band, start, beyond), end_key(band, stop, beyond)
        flip = track_names.end_order(b) < track_names.end_order(a)
        run = f"{b}-{a}" if flip else f"{a}-{b}"
        if run in seen:
            raise StagingMapError(f"tracks {seen[run]} and {chain[0][0]} both run {run}: name them apart")
        seen[run] = chain[0][0]
        pieces = chain[::-1] if flip else chain
        for i, (sid, rev) in enumerate(pieces, 1):
            out[sid] = (run if len(pieces) == 1 else f"{run} #{i}", rev != flip)
    return out


def placeholders(band: Band) -> tuple[dict[str, str], dict[str, str], dict[str, Ref]]:
    """({switch node: turnout placeholder}, {switch node: OS placeholder}, {strand id: (piece reference, reversed)})
    of the staging band (piece_refs). Inner crossover strands carry none (the plugin draws them inside the
    crossover). A crossover half is told apart by where the run from its leg A goes."""
    refs = piece_refs(band)
    turnouts = {n: f"Switch {label}" for n, (label, _half) in _switch_halves(band).items()}
    os_ = {n: ph for n, (ph, _id) in os_keys(band).items()}
    return turnouts, os_, refs


def os_keys(band: Band) -> dict[str, tuple[str, str]]:
    """{switch node: (its OS placeholder, its OS block's device ID)} of the staging band: "OS Switch <n>" and
    os:<n> of a plain switch; "OS <n> A-<end>" and os:<n>:A-<end> of a crossover half, by where the run from its leg
    A goes (hartlib.device_ids: the plan has no corner letter for a staging half)."""
    out: dict[str, tuple[str, str]] = {}
    for n, (label, half) in _switch_halves(band).items():
        out[n] = ((f"OS {label} A-{half}", device_ids.os_id(label, f"A-{half}")) if half else
                  (f"OS Switch {label}", device_ids.os_id(label)))
    if len({ph for ph, _id in out.values()}) != len(out):
        raise StagingMapError(f"two crossover halves have one key: {sorted(ph for ph, _id in out.values())}")
    return out


def _switch_halves(band: Band) -> dict[str, tuple[str, str]]:
    """{switch node: (its label, the end its leg A runs to when it is a crossover half, else "")}."""
    halves = crossover_halves(band)
    leg_a: dict[tuple[str, str], str] = {}
    for start, _chain, stop in ln.runs(band, ln.crossover_strands(band)):
        leg_a[tuple(start)], leg_a[tuple(stop)] = end_key(band, stop), end_key(band, start)
    out: dict[str, tuple[str, str]] = {}
    for n, d in sorted(band["nodes"].items()):
        if d["kind"] == "dx":
            raise StagingMapError(f"staging switch {d.get('label')}: a double crossover, which staging has none of")
        if d["kind"] != "switch":
            continue
        label = lc.bare(d.get("label"))
        if not re.fullmatch(r"\d+", label or ""):
            raise StagingMapError(f"staging switch node {n}: label {d.get('label')!r} is no switch number")
        if n in halves and (n, "A") not in leg_a:
            raise StagingMapError(f"crossover half {label} at {n}: no run leaves its leg A to tell it apart by")
        out[n] = (label, leg_a[(n, "A")] if n in halves else "")
    return out


def track_placeholder(piece: str, k: int, count: int) -> str:
    """The trial key of the k-th of a piece's `count` blocks ("Track 5C-7B", or "Track 5C-7B 1/2" of two)."""
    return f"Track {piece}" if count == 1 else f"Track {piece} {k}/{count}"


def strand_placeholders(ref: Ref, count: int = 1) -> list[str]:
    """The trial keys of a strand's `count` blocks, from the strand's first end as drawn: `ref` is its (piece, whether
    it runs against the piece) from piece_refs or band_refs, and the k-th of n blocks is counted from the piece's
    first end (track_placeholder). The one rule the writer (build_device_map.piece_trials) and every reader key a
    strand by. ValueError on a count under 1."""
    if count < 1:
        raise ValueError(f"a strand carries at least one block, not {count}")
    piece, against = ref
    keys = [track_placeholder(piece, k, count) for k in range(1, count + 1)]
    return keys[::-1] if against else keys


def strand_ids(ref: Ref, count: int = 1) -> list[str]:
    """The device-ID parts (hartlib.device_ids.strand_key) of a strand's `count` blocks, in the order
    strand_placeholders gives their keys: the same piece, k and n."""
    if count < 1:
        raise ValueError(f"a strand carries at least one block, not {count}")
    piece, against = ref
    keys = [device_ids.strand_key(piece, k, count) for k in range(1, count + 1)]
    return keys[::-1] if against else keys


def piece_of(key: str) -> tuple[str, int, int]:
    """(piece, k, n) of a track trial key ("Track 37C-39C #2 1/2" -> ("37C-39C #2", 1, 2); one block: k = n = 1).
    StagingMapError on a key that is no track key."""
    m = TRACK_RE.fullmatch(key)
    if not m:
        raise StagingMapError(f"{key!r} is no track trial key (Track <end>-<end>[ #i][ k/n])")
    return (m.group(1), int(m.group(2)), int(m.group(3))) if m.group(2) else (m.group(1), 1, 1)


def split_names(cell: str) -> list[str]:
    """The names of a comma-separated cell, each stripped, empty ones left out."""
    return [t.strip() for t in (cell or "").split(",") if t.strip()]


def staging_band() -> tuple[Band, dict[str, Any], Any]:
    """The staging band as build_layout_le.py draws it (the plugin's drawn_bands: the preferences' le_shift and
    le_longer_straights): (band, its options, the plugin's core)."""
    _sheet, le_mod, core = lc.plugin()
    bands, page = lc.schematic()
    try:
        bands = le_mod.drawn_bands(bands, page)
    except core.SchematicError as exc:
        raise StagingMapError(f"schematic le: {exc}") from exc
    try:
        _t, band, opts = bands[lc.base_band(bands)]     # the band of the level the base holds, by its level
    except lc.BuildError as exc:
        raise StagingMapError(f"the staging band: {exc}") from exc
    return band, opts, core


def mast_kind(r: Mapping[str, Any]) -> MastKind:
    """The kind of slot a masts.csv row stands in: a switch number means a turnout leg, no protected block an
    end bumper, else an anchor."""
    if r["switch"]:
        return "turnout"
    return "end bumper" if not r["protects"] else "anchor"


def occupancy_blocks(r: Mapping[str, str]) -> list[str]:
    """The blocks an occupancy row's detector serves, its `blocks` column ("Track S-1;Track S-1 West")."""
    return railroad.device_list(r["blocks"])


def check_helix(band: Band, names: StagingNames, stored: Mapping[str, str],
                helix: Mapping[str, Mapping[str, str]] | None = None) -> list[str]:
    """Each helix track of plan_overrides.json is drawn on the staging band from its staging_switch, and its staging
    piece is that file's block (load()'s names). A strand is the helix track the name store names it by its ID
    (`stored`: staging_names of the band, from the caller's data folder). The problems, one per track."""
    helix = mr.read_helix_tracks() if helix is None else helix
    bad: list[str] = []
    for plan, h in sorted(helix.items()):
        sids = [sid for sid in band["strands"] if stored.get(sid) == plan]
        if len(sids) != 1:
            bad.append(f"helix track {plan}: drawn {len(sids)} times on the staging band")
            continue
        s = band["strands"][sids[0]]
        labels = [lc.bare(band["nodes"][e[0]].get("label")) for e in (s["src"], s["dst"])
                  if band["nodes"][e[0]]["kind"] == "switch"]
        if labels != [h["staging_switch"]] or names["blocks"].get(sids[0]) != [h["block"]]:
            bad.append(f"helix track {plan}: from switch {', '.join(map(str, labels)) or 'none'} in block(s) "
                       f"{names['blocks'].get(sids[0])}, {mr.HELIX_SOURCE.name} says Switch {h['staging_switch']}, "
                       f"{h['block']}")
    return bad


# ---------------------------------------------------------------- reading the files


def read_device_rows(path: Path = DEVICE_MAP) -> list[Row]:
    """Staging's device-map rows: the level 1 rows of the master at `path` (hartlib.devices.device_map_lines), each a
    dict of the device-map columns and `role`. StagingMapError when the master cannot be read or has none."""
    try:
        rows = [r for _, r in devices.device_map_lines((str(LEVEL),), path)]
    except railroad.FactsError as exc:
        raise StagingMapError(str(exc)) from exc
    if not rows:
        raise StagingMapError(f"{paths.rel(path)}: no staging rows")
    return rows


def desk_areas(path: Path = STATIONS) -> list[railroad.DeskArea]:
    """Every level's desk areas of stations.csv (hartlib.railroad_facts.read_desk_areas); StagingMapError, naming the
    file, line and station, on a row that breaks its rules."""
    try:
        return railroad.read_desk_areas(path)
    except railroad.FactsError as exc:
        raise StagingMapError(str(exc)) from exc


def switch_areas(path: Path = STATIONS, level: int = LEVEL) -> dict[str, str]:
    """{switch number: the name of the desk area it is in} for `level` (staging unless given)."""
    return {s: a.name for a in desk_areas(path) if a.level == level for s in a.switches}


def read_rows(path: Path, columns: Sequence[str]) -> list[Row]:
    """The rows of the CSV file at `path`, whose columns must be `columns` in that order. StagingMapError when it
    cannot be read, has no rows or other columns."""
    try:
        rows = lc.read_csv(path)
    except OSError as exc:
        raise StagingMapError(f"cannot read {paths.rel(path)}: {exc}") from exc
    if not rows:
        raise StagingMapError(f"{paths.rel(path)}: no rows")
    if list(rows[0]) != list(columns):
        raise StagingMapError(f"{paths.rel(path)}: columns {list(rows[0])}, not {list(columns)}")
    return rows


def switch_facts(read: Callable[[], T]) -> T:
    """`read()` (a le_common reader of the staging switches, hartlib.railroad: switches.csv,
    ADR-021, read once per run), with its BuildError as a StagingMapError naming the file and row."""
    try:
        return read()
    except lc.BuildError as exc:
        raise StagingMapError(str(exc)) from exc


def closed_legs() -> dict[str, str]:
    """{OS block: closed leg block} of every staging switch (switches.csv, ADR-021)."""
    return {leg.os_block: leg.closed for sw in switch_facts(lc.staging_switches).values() for leg in sw.legs}


def run_blocks(band: Band, names: StagingNames) -> list[tuple[Leg, list[str], Leg]]:
    """[(start (node, port), [block, ...], end (node, port))]: each run of the band (le_names.runs: tracks joined
    through turnbacks, crossover insides left out) with its blocks from `names` in order from its start; a block
    that runs on through a turnback (Brick-Plane) counted once."""
    out: list[tuple[Leg, list[str], Leg]] = []
    for start, chain, end in ln.runs(band, ln.crossover_strands(band)):
        seq: list[str] = []
        for sid, rev in chain:
            bl = names["blocks"][sid]
            for b in (bl[::-1] if rev else bl):
                if not seq or seq[-1] != b:
                    seq.append(b)
        out.append((start, seq, end))
    return out


def leg_first_blocks(band: Band, names: StagingNames) -> dict[Leg, str | None]:
    """{(switch node, leg): first block past the switch's own OS block along that leg}: along the run of tracks from
    that leg (through turnbacks), else the OS block of the switch at the run's far end; None at a bumper."""
    nodes = band["nodes"]
    out: dict[Leg, str | None] = {}
    for start, seq, end in run_blocks(band, names):
        for here, there, blocks_ in ((start, end, seq), (end, start, seq[::-1])):
            if nodes[here[0]]["kind"] != "switch":
                continue
            own = names["os"][here[0]]
            got = next((b for b in blocks_ if b != own), None)
            if got is None and nodes[there[0]]["kind"] == "switch":
                got = names["os"][there[0]]
            out[tuple(here)] = got
    return out


def normal_legs(band: Band, names: StagingNames) -> dict[str, str]:
    """{plain switch node: "B" or "C"}: the drawn leg whose first block is the switch's closed leg in switches.csv."""
    closed = closed_legs()
    first = leg_first_blocks(band, names)
    halves = crossover_halves(band)
    out: dict[str, str] = {}
    bad: list[str] = []
    for n, d in sorted(band["nodes"].items()):
        if d["kind"] != "switch" or n in halves:
            continue
        want = closed.get(names["os"][n])
        if want is None:
            bad.append(f"switch {d['label']}: {names['os'][n]} is not in switches.csv")
            continue
        legs = [p for p in "BC" if first.get((n, p)) == want]
        if len(legs) != 1:
            bad.append(f"switch {d['label']}: closed leg {want} is first past {len(legs)} of its legs "
                       f"(B: {first.get((n, 'B'))}, C: {first.get((n, 'C'))})")
            continue
        out[n] = legs[0]
    if bad:
        raise StagingMapError("staging normal legs: " + "; ".join(bad))
    return out


def part_lines(device_map: Path = DEVICE_MAP, rows: Sequence[Mapping[str, str]] | None = None) -> list[tuple[int, Row]]:
    """(line, row) of staging's parts (role part: a piece of track inside another block, part_of naming it), which
    the device maps leave out (hartlib.devices.OUT_OF_MAPS): of the master at `device_map`, or of `rows` (master rows
    a builder is writing, numbered from 2 as a file's lines)."""
    if rows is not None:
        return [(n, dict(r)) for n, r in enumerate(rows, 2) if r["level"] == str(LEVEL) and r["role"] == "part"]
    try:
        return devices.part_lines((str(LEVEL),), device_map)
    except railroad.FactsError as exc:
        raise StagingMapError(str(exc)) from exc


class _Trials:
    """load()'s reader of the drawing keys (hartlib.drawing_keys.read): the name a trial key's row is bound by, the
    keys read so far (`used`) and the problems found (`bad`, the caller's list)."""

    def __init__(self, keys: drawing_keys.Keys, bad: list[str]) -> None:
        self.keys, self.bad = keys, bad
        self.used: set[str] = set()

    def name(self, ph: str, layer: str) -> str:
        """The name the panels bind the `layer` row of trial key `ph` by: a turnout's jmri_name, any other row's user
        name. "" with a problem in `bad` when no `layer` row has that key."""
        row = self.keys.row(ph)
        if row is None or row["layer"] != layer:
            self.bad.append(f"no {layer} row has trial_name {ph}")
            return ""
        self.used.add(ph)
        return row["jmri_name"] if layer == "turnout" else row["user_name"]


def _staging_lines(device_map: Path, master_rows: Sequence[Mapping[str, str]] | None) -> list[tuple[int, Row]]:
    """(line, row) of the master's level 1 rows that a device map holds: of the file at `device_map`, or of
    `master_rows` (rows a builder is writing, numbered from 2 as a file's lines). StagingMapError when there is none."""
    import check_device_master as cdm       # the rules of every level's rows (it imports this module)
    try:
        if master_rows is None:
            lines = [(n, r) for n, r in cdm.master_lines(device_map) if r["level"] == str(LEVEL)]
        else:                               # as master_lines reads a file: a device map's rows, placed ones
            lines = [(n, dict(r)) for n, r in enumerate(master_rows, 2) if r["level"] == str(LEVEL)
                     and r["role"] not in devices.OUT_OF_MAPS]
    except cdm.DeviceMasterError as exc:
        raise StagingMapError(str(exc)) from exc
    if not lines:
        raise StagingMapError(f"{paths.rel(device_map)}: no staging rows")
    return lines


def _row_problems(lines: list[tuple[int, Row]], device_map: Path, stations_path: Path,
                  interlockings_path: Path) -> tuple[list[str], set[str]]:
    """(the problems of `lines` under the rules every level's rows keep (check_device_master.row_problems), staging's
    control point names). StagingMapError when interlockings.csv or stations.csv does not read."""
    import check_device_master as cdm
    try:
        interlockings = railroad.read_interlockings(interlockings_path)
        cps = cdm.control_points(interlockings, stations_path)
        places = cdm.known_places(interlockings, stations_path)
    except (cdm.DeviceMasterError, railroad.FactsError) as exc:
        raise StagingMapError(str(exc)) from exc
    # staging's rows cross no level but a helix block's, whose cp lists the places it joins
    return cdm.row_problems(lines, cps, paths.rel(device_map), ends_cps={}, places=places), cps.get(str(LEVEL), set())


def track_runs(keys: drawing_keys.Keys) -> TrackRuns:
    """{piece: {k: (n, trial key)}} of the block rows whose trial key is a track key (piece_of)."""
    runs: TrackRuns = {}
    for ph, device_id in keys.ids.items():
        if keys.rows[device_id]["layer"] == "block" and TRACK_RE.fullmatch(ph):
            piece, k, count = piece_of(ph)
            runs.setdefault(piece, {})[k] = (count, ph)
    return runs


def strand_blocks(strands: Mapping[str, Ref], runs: TrackRuns, trials: _Trials) -> dict[str, list[str]]:
    """{strand id: its blocks from the strand's first end, as drawn} of each strand of `strands` (placeholders) whose
    piece's block rows (`runs`, track_runs) are 1/n to n/n; a problem in trials.bad for a strand with none, or with a
    broken k/n run."""
    out: dict[str, list[str]] = {}
    for sid, (piece, against) in sorted(strands.items()):
        got = runs.get(piece, {})
        if not got:
            trials.bad.append(f"track {piece} ({sid}) is on no block row: give it a block, or a part row naming the "
                              "block it is part of (build_device_map.py writes them)")
            continue
        counts = {c for c, _ph in got.values()}
        if len(counts) != 1 or sorted(got) != list(range(1, next(iter(counts)) + 1)):
            trials.bad.append(f"track {piece}: blocks {sorted(ph for _c, ph in got.values()) or 'none'} are not 1/n "
                              "to n/n")
            continue
        blocks = [trials.name(got[k][1], "block") for k in sorted(got)]     # from the run's first end
        out[sid] = blocks[::-1] if against else blocks                       # from the strand's first end, as drawn
    return out


def le_idents(turnout_ph: Mapping[str, str], bad: list[str]) -> dict[str, str]:
    """{switch node: its Layout Editor ident} from switches.csv's le_ident (le_common.switch_idents), by the turnout
    placeholders `turnout_ph`; a problem in `bad` for a switch with none."""
    ident_of = switch_facts(lc.switch_idents)
    idents: dict[str, str] = {}
    for n, ph in turnout_ph.items():
        ident = ident_of.get(ph.removeprefix("Switch "), "")
        if not ident:
            bad.append(f"{ph} has no le_ident in switches.csv")
        idents[n] = ident
    return idents


def load(band: Band, device_map: Path = DEVICE_MAP, masts_path: Path = MASTS, stations_path: Path = STATIONS,
         turnout_idents: bool = True, with_masts: bool = True,
         interlockings_path: Path = INTERLOCKINGS, master_rows: Sequence[Mapping[str, str]] | None = None,
         with_normal: bool = True) -> StagingNames:
    """The plugin's names for the staging band from the three files alone: turnouts, os, blocks, normal (from
    switches.csv), masts, and with `turnout_idents` each turnout's Layout Editor ident from switches.csv
    (le_ident, ADR-021); with_masts False leaves the masts out. Stops on a row that breaks the rules every row of
    the device master keeps (check_device_master.row_problems), any placeholder no row names, any row the drawing
    does not use, a piece of the drawing on no row or on two, a broken k/n run, or a mast row that is not well formed.
    A part (part_lines) is a JMRI block of its own on every level: its pieces are its own block, and
    staging_parts gives {part: the block it is part of} (os_layer reads the blocks as the masts do). `master_rows`: the
    master's rows as a builder writes them (build_device_map.py's staging masts, from the block rows it makes in the
    same run), read in place of the file at `device_map` (which then only names it in messages). with_normal False
    leaves out `normal` (switches.csv's closed legs, by block name: the masts do not read it, and in a build the
    hands step writes those names only after the device map)."""
    lines = _staging_lines(device_map, master_rows)
    bad, cp_names = _row_problems(lines, device_map, stations_path, interlockings_path)
    if bad:
        raise StagingMapError("; ".join(bad))
    rows = [r for _n, r in lines]
    turnout_ph, os_ph, strands = placeholders(band)
    try:        # the one reader of every level's drawing keys, keyed by device ID
        keys = drawing_keys.read((str(LEVEL),), None if master_rows is not None else device_map, rows=master_rows)
    except (drawing_keys.DrawingKeyError, railroad.FactsError) as exc:
        raise StagingMapError(f"{paths.rel(device_map)}: {exc}") from exc
    trials = _Trials(keys, bad)
    turnouts = {n: trials.name(ph, "turnout") for n, ph in turnout_ph.items()}
    os_blocks = {n: trials.name(ph, "block") for n, ph in os_ph.items()}
    runs = track_runs(keys)
    names = StagingNames(turnouts=turnouts, os=os_blocks, blocks=strand_blocks(strands, runs, trials))
    drawn = {piece for piece, _against in strands.values()}
    left = {piece: got for piece, got in runs.items() if piece not in drawn}
    for piece, got in left.items():
        bad.append(f"trial names for track {piece}, which the staging drawing does not have: "
                   f"{sorted(ph for _c, ph in got.values())}")
    unused = sorted(set(keys.ids) - trials.used - {ph for got in left.values() for _c, ph in got.values()})
    if unused:
        bad.append(f"trial names the staging drawing does not have: {unused}")
    if bad:
        raise StagingMapError(f"{paths.rel(device_map)}: " + "; ".join(bad))
    if with_normal:             # switches.csv names a leg by its first OS block
        names["normal"] = normal_legs(band, os_layer(names, keys.parts()))   # a part's pieces are its own JMRI block
    if turnout_idents:
        names["idents"] = Idents(turnouts=le_idents(turnout_ph, bad), boundaries=[], ends={}, segments={})
    if with_masts:              # masts.csv's staging rows, for the readers of the drawn masts
        names["masts"] = load_masts(masts_path, cp_names, rows, device_map)
    if bad:
        raise StagingMapError("; ".join(bad))
    return names


def staging_parts(device_map: Path = DEVICE_MAP, rows: Sequence[Mapping[str, str]] | None = None) -> dict[str, str]:
    """{part: the block it is part of} of staging's parts (part_lines, of the file or of `rows`): each a JMRI block of
    its own that the masts read inside its block (os_layer)."""
    return {r["user_name"]: r["part_of"] for _n, r in part_lines(device_map, rows)}


def os_layer(names: StagingNames, parts: Mapping[str, str]) -> StagingNames:
    """A copy of load()'s names with each part's pieces given to the block it is part of (`parts`, staging_parts),
    as the one mast process reads a level's block layer on every level (main and upper: block_layer.Layer.bands): a
    mast's place and the blocks it protects follow the OS blocks, a part being inside its OS block (mast_plan,
    device_map_masts). StagingMapError on a part whose block is itself a part."""
    bad = sorted(p for p, of in parts.items() if of in parts)
    if bad:
        raise StagingMapError(f"parts {bad} are part of another part")
    out = names.copy()
    out["blocks"] = {sid: [parts.get(b, b) for b in v] for sid, v in names["blocks"].items()}
    return out


def staging_masts(path: Path = MASTS) -> list[tuple[int, dict[str, Any]]]:
    """(line, row) of masts.csv's staging rows (hartlib.level_masts.read checks the whole file); StagingMapError on a
    file that breaks its rules or has no staging row."""
    try:
        rows = level_masts.read(path, levels=(LEVEL,))
    except railroad.FactsError as exc:
        raise StagingMapError(str(exc)) from exc
    if not rows:
        raise StagingMapError(f"{paths.rel(path)}: no level {LEVEL} rows")
    return [(r["line"], r) for r in rows]


def load_masts(path: Path, cp_names: set[str], device_rows: Sequence[Mapping[str, str]],
               device_map: Path = DEVICE_MAP) -> list[StagingMast]:
    """The plugin's staging masts from masts.csv's staging rows: each with its facing and protected blocks, its kind
    of slot (mast_kind), hidden for a virtual mast and its icon size (hartlib.tables.mast_icon_size). Stops on a row
    whose mast, heads or system name the device map does not hold as the same mast, or whose switch no turnout row
    is."""
    lines = staging_masts(path)
    dev = {(r["layer"], r["user_name"]): r for r in device_rows}
    where = devices.index(device_map).where     # a row's line in the master, for a message
    heads = {r["system_name"]: r["user_name"] for r in device_rows if r["layer"] == "head"}
    switches = {r["trial_name"].removeprefix("Switch ") for r in device_rows     # a turnout, not its LCC alias
                if r["layer"] == "turnout" and devices.row_role(r, where(r)) == "turnout"}
    out: list[StagingMast] = []
    bad: list[str] = []
    seen: set[str] = set()
    for i, r in lines:
        name = r["mast"]
        if r["switch"] and r["switch"] not in switches:
            bad.append(f"line {i}: {name} is on switch {r['switch']!r}, which no turnout row of the device map is")
        d = dev.get(("mast", name))
        if name in seen or d is None:
            bad.append(f"line {i}: mast {name!r} given twice or not in the device map")
            continue
        seen.add(name)
        if r["system_name"] != d["system_name"] or r["device_system_name"] != d["system_name"]:
            bad.append(f"line {i}: {name} system name {r['system_name']!r}, the device map's {d['system_name']!r}")
        if (r["cp"] and r["cp"] not in cp_names) or not r["facing"]:
            bad.append(f"line {i}: {name} needs a facing block, and its cp (if any) a staging control point")
        if not r["cp"] and not r["system_name"].startswith("IF$vsm:"):
            bad.append(f"line {i}: {name} is a visible mast in no control point")
        pairs = [tuple(h.split("=", 1)) for h in r["head_system_names"].split(";") if h]
        if [h for h, *_ in pairs] != level_masts.mast_heads(r["system_name"]) or \
                any(len(p) != 2 or heads.get(p[0]) != p[1] for p in pairs):
            bad.append(f"line {i}: {name} heads {r['head_system_names']!r} are not its system name's heads as the "
                       "device map names them")
        if r["leg"] not in ("", *level_masts.LEGS.values()):
            bad.append(f"line {i}: {name} leg {r['leg']!r}")
        size, known = tables.mast_icon_size(r["system_name"])
        if not known:
            bad.append(f"line {i}: {name}: no icon size for {r['system_name']}")
        protects = [b for b in r["protects"].split(";") if b]
        entry = StagingMast(mast=name, facing=r["facing"], protects=protects, kind=mast_kind(r),
                            hidden=r["system_name"].startswith("IF$vsm:"), icon=list(size))
        if r["leg"]:
            entry["leg"] = r["leg"]
        if entry["kind"] == "end bumper":       # may stand at a helix join instead (the three-level panel)
            entry["or_join"] = True
        out.append(entry)
    if bad:
        raise StagingMapError(f"{paths.rel(path)}: " + "; ".join(bad))
    return sorted(out, key=lambda m: m["mast"])


def load_signal_masts(masts_path: Path | None = None) -> list[SignalMast]:
    """The staging masts as build_signals.py reads them: masts.csv's staging rows with their plan facts
    (level_masts.PLAN_FIELDS, which hartlib.level_masts.read checks), blocks and slot kind (mast_kind), with the fields
    signal_rows and build_signals.check_lengths read; the signal's name, kind and heads follow from the row
    (level_masts.signal_name, signal_kind, head_count). Stops on a staging row without plan facts: the drawing places
    staging's masts from them."""
    masts_path = masts_path or MASTS
    out: list[SignalMast] = []
    bad: list[str] = []
    for i, r in staging_masts(masts_path):
        if not level_masts.placed(r):
            bad.append(f"line {i} ({r['mast']}): no plan facts ({', '.join(level_masts.PLAN_FIELDS)})")
            continue
        out.append(SignalMast(mast=r["mast"], kind=mast_kind(r), facing=r["facing"],
                              protects=[x for x in r["protects"].split(LIST) if x],
                              signal=level_masts.signal_name(r["mast"]), toward=r["toward"], run=r["run"].split(LIST),
                              names=[x for x in r["names"].split(LIST) if x], edge_cm=float(r["edge_cm"]),
                              cm_from_toward=float(r["cm_from_toward"]), dir=r["dir"],
                              signal_kind=level_masts.signal_kind(r), heads=level_masts.head_count(r),
                              schematic_edge=r["schematic_edge"], schematic_toward_node=r["schematic_toward_node"]))
    if bad:
        raise StagingMapError(f"{paths.rel(masts_path)}: " + "; ".join(bad))
    return out


def staging_chains(band: Band, names: StagingNames) -> list[dict[str, Any]]:
    """The staging tracks between switches and ends, as the hand-drawn panel's tracks were read once:
    [{ends: [(Layout Editor ident or "END", band port), ...], blocks: [...]}], each a run of the band (through
    turnbacks) with its blocks from the device map (load()) in order. A switch's ident is switches.csv's le_ident
    (names["idents"]); the port is the band's, not a Layout Editor leg letter."""
    nodes = band["nodes"]
    idents = names["idents"]["turnouts"]
    out: list[dict[str, Any]] = []
    for start, seq, end in run_blocks(band, names):
        ends = [("END", str(e[1])) if nodes[e[0]]["kind"] != "switch" else (idents[e[0]], str(e[1]))
                for e in (start, end)]
        out.append(dict(ends=ends, blocks=seq))
    return out


def mast_facts(device_map: Path = DEVICE_MAP, masts_path: Path = MASTS) -> dict[str, MastFact]:
    """{mast: {kind, facing, protects, hidden, turnout}} of every staging mast from masts.csv: its slot kind
    (mast_kind), blocks, hidden (a virtual mast) and, for a turnout mast, the turnout name the panels bind its switch
    by (the device map's jmri_name)."""
    turnout_of = {r["trial_name"].removeprefix("Switch "): r["jmri_name"]
                  for r in read_device_rows(device_map) if r["layer"] == "turnout" and r["trial_name"]}
    out: dict[str, MastFact] = {}
    for _line, r in staging_masts(masts_path):
        kind = mast_kind(r)
        if kind == "turnout" and r["switch"] not in turnout_of:
            raise StagingMapError(f"{paths.rel(masts_path)}: {r['mast']} is on switch {r['switch']}, which the "
                                  "device map has no turnout for")
        fact = MastFact(kind=kind, facing=r["facing"], protects=[b for b in r["protects"].split(";") if b],
                        hidden=r["system_name"].startswith("IF$vsm:"))
        if kind == "turnout":
            fact["turnout"] = turnout_of[r["switch"]]
        out[r["mast"]] = fact
    return out


def signal_rows(masts: Sequence[SignalMast]) -> list[dict[str, Any]]:
    """signals.json[staging]'s signals from the staging masts (load_signal_masts), in the plugin's order (by number,
    then name)."""
    rows = [dict(mast=m["signal"], toward=m["toward"], run=list(m["run"]), names=list(m["names"]),
                 edge_cm=m["edge_cm"], cm_from_toward=m["cm_from_toward"], dir=m["dir"], kind=m["signal_kind"],
                 heads=m["heads"], source="le_panel", _edge=m["schematic_edge"],
                 _toward_node=m["schematic_toward_node"]) for m in masts]

    def key(r: Mapping[str, Any]) -> tuple[int, str]:
        n = re.match(r"\d+", r["mast"])
        return (int(n.group()) if n else 10 ** 9, r["mast"])
    return sorted(rows, key=key)
