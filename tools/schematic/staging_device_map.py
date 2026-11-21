#!/usr/bin/env python3
"""Staging's facts in the device map's form: the source the Layout Editor build, the signals and the CATS desks read.

The source since the device-map switch-over (owner, 2026-11-17), when the frozen hand-drawn files (staging_le/) and the
conversion from them retired. The turnout and feedback rows of level 1 of devices.csv are kept by hand but for their wiring cells,
which build_device_map.py writes from wiring.csv (stations.csv's desk areas are staging's control points, build_staging_sets.py); the block and occupancy
rows are the one block builder's (build_device_map.py, block_layer: step 5 part 1, 2026-11-20), which carries each
row's field facts over, writes its detector's wiring from wiring.csv (level 1 rows; step 6) and owns which
blocks there are and what each holds; build_masts.py writes
staging_masts.csv, staging_signals.csv and the mast and head rows. Edit these files, not a panel. This module reads
them (load, load_masts, load_signal_masts, mast_facts) and stops on a file not in its shape; check_device_master.py --check
(`make panels`, tools/check.sh) holds them, and every device row, to tables.xml and the schematic.

Staging's objects are field devices: every system name, user name and binding here is the railroad's own.

Files (jmri/layouts/hart/data/, schematic/ for the rest):
- the level 1 rows of devices.csv (hartlib.devices.device_map_lines). Layers as main and upper: turnout (and its LCC alias
  "DCC Switch <n>"), fb, block, occupancy, mast, head. Staging is the field, so system_name is the live device;
  jmri_name is the name tables.xml and the panels bind it by: a turnout's is the Layout Editor's turnoutname (some
  bind "M2T408", some "Switch 23"), every other row's its system name. trial_name is the link to the drawing, as for
  main and upper (placeholders(), below). The facts are in columns (hartlib.railroad.DEVICE_FACTS, checked by
  device_facts; the comment and notes stay text for people): one occupancy row per detector, its `blocks` the blocks
  it serves (a detector that serves several blocks lists each) and its `detector` wired, all of staging's being in
  the field; a block's `stop` "yes" for a Dispatcher System station, as its tables.xml comment marks it ("; stop",
  checked); a mast's `switch`, `facing` and `protects` as staging_masts.csv has them. The rules every level's rows
  keep are check_device_master.row_problems', which load() runs on these rows.
  A helix block (plan_overrides.json: Track Helix Outer, Track Helix Inner) is one JMRI block from its staging switch
  up the helix (owner, 2026-11-20): its staging piece is a block row here, and its detector is the occupancy row of
  levels 2 and 3 of devices.csv, which name the same block for the piece on its level (check_device_master.check_rows).
- parts (devices.csv part_of, role part; owner, 2026-11-20): a short piece of track between two switches has a block
  row of its own that names the block it is part of (the lower-numbered switch's OS block by rule, or the one
  block_overrides.csv gives it), and its trial_name. A part is a JMRI block of its own on that block's occupancy
  sensor (owner, 2026-11-20): load() draws its pieces as the part, and os_layer reads them inside its block, as the
  masts do. The device maps leave parts out (hartlib.devices.OUT_OF_MAPS), so load() reads them from the master.
- stations.csv (level, station, switches, tracks, desk_code, notes): the stations, and through their desk codes
  staging's control points, the desk areas (hartlib.railroad_facts.read_desk_areas, the one reader; desk_areas()
  here). build_staging_sets.py writes plan_overrides.json's staging section (control_points, stations and
  station_tracks) and the `detail_sheets` preference from it and sheets.csv (other readers take the areas' rows
  through hartlib.railroad_facts.station_group_rows).
- staging_masts.csv, hartlib.level_masts.FIELDS. A mast's kind of slot follows from its row (mast_kind): a switch
  number means a turnout mast, no protected block an end bumper (buffer stop) mast, else an anchor mast. Hidden is a
  virtual mast (IF$vsm), its icon size hartlib.tables.mast_icon_size.
- staging_signals.csv (SIGNAL_COLUMNS): each mast's signal-plan facts (its schematic run, lengths, direction, kind
  and heads). build_signals.py writes signals.json's staging section from it and staging_masts.csv (load_signal_masts,
  signal_rows).

Readers: build_layout_le.py (load), build_signals.py (load_signal_masts, staging_chains), build_cats_panel.py
(staging_chains), hartlib.railroad's staging masts and check_layout_facts.py (staging_masts.csv),
test_le_mast_parity.py (mast_facts).

Trial names (placeholders()): the links from the rows to the drawing, by switch numbers and legs, so they survive a
new AnyRail export, whose edge and node ids change every time (owner, 2026-11-20). Each is resolved to the drawing's
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
The track keys are one grammar for every level (owner, 2026-11-20): main and upper's track and part rows take them
too (build_device_map.level_trials), where they used to name AnyRail plan edges ("Track e33"). A block that several
tracks or a switch share lists every placeholder, comma separated, in key order; a part's pieces are on its own row.
Every piece of the drawing is on exactly one row.

The panel's own icons and labels are not device facts and are not here: the status cluster, captions and backdrop
are in panel_items.json (panel_items.py); the occupancy lamps and station clusters are parked with the Dispatcher
System (jmri/layouts/hart/parked/staging_panel_lamps.json).
"""
from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import le_common as lc  # noqa: E402  the band key, plugin, solved schematic and the files the build reads
import le_names as ln  # noqa: E402  runs and crossovers
import mast_rule as mr  # noqa: E402  the helix tracks (plan_overrides.json)
import publish_draft as pd  # noqa: E402  DATA and the plugin cache
from hartlib import devices, layer_files, level_masts, paths, railroad, tables  # noqa: E402

LEVEL = 1
DEVICE_MAP = paths.LAYOUT_DATA / "devices.csv"     # the master: its level 1 rows are staging's device map
STATIONS = pd.DATA / "stations.csv"          # the stations; their desk areas are staging's control points
INTERLOCKINGS = railroad.Sources.under().interlockings     # every level's (the control points a row's cp may name)
MASTS = pd.DATA / "staging_masts.csv"
SIGNALS = pd.DATA / "staging_signals.csv"
SHEET = "staging"           # staging's section of the layer files (plan_overrides.json, signals.json)
# staging_signals.csv: the signal-plan facts build_signals.py writes signals.json's staging section from; lists inside a cell
# are LIST separated
SIGNAL_COLUMNS = ["mast", "signal", "toward", "run", "names", "edge_cm", "cm_from_toward", "dir", "signal_kind",
                  "heads", "schematic_edge", "schematic_toward_node"]
LIST = ";"
# what signals.json's staging section names as its source: the file the masts were first read from (the hand-drawn panel's)
SIGNALS_SOURCE = "tables.xml"
LAYERS = ("turnout", "fb", "block", "occupancy", "mast", "head")
TRACK_RE = re.compile(r"Track (\S+?(?: #\d+)?)(?: (\d+)/(\d+))?")       # a track by its piece (piece_refs), k-th of n blocks


class StagingMapError(RuntimeError):
    pass


def overrides() -> dict:
    """Staging's section of plan_overrides.json (hartlib.layer_files; LayerFileError if it is missing)."""
    return layer_files.read("plan_overrides", SHEET, pd.DATA)


# ---------------------------------------------------------------- placeholders: the drawing's keys


def crossover_halves(band) -> dict:
    """{node: other half} for each switch that is half of a single crossover (two switches of one label joined C to C,
    build_layout_le.crossover_strands)."""
    out = {}
    for sid in ln.crossover_strands(band):
        u, v = band["strands"][sid]["src"][0], band["strands"][sid]["dst"][0]
        out[u], out[v] = v, u
    return out


def end_key(band, end, beyond=None) -> str:
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


def _end_order(key: str):
    m = re.fullmatch(r"(\d+)([AB]?)([A-D])", key)
    return (0, int(m.group(1)), m.group(2), m.group(3)) if m else (1, 0, "", key)


def band_refs(bands, joined: dict, bi: int) -> dict[str, tuple[str, bool]]:
    """piece_refs of band `bi` of `bands` (the solved schematic), a run that ends at a connector keyed by the switch
    and leg where the run beyond it, on the band `joined` (the plugin's partners: {(band, node): (band, node)}) gives,
    ends: one track cut by a connector has one key on both bands. StagingMapError on a connector `joined` does not
    pair, or one whose run beyond ends at another connector."""
    def beyond(end):
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


def piece_refs(band, beyond=None) -> dict[str, tuple[str, bool]]:
    """{strand id: (its piece reference, whether the strand runs against it)} of every strand of `band` outside a
    staging-style single crossover (two switches of one label joined C to C; their insides carry no blocks):
    "<end>-<end>" of its run (end_key, the lower first; `beyond` keys a connector end, band_refs) and " #<i>" when the
    run has several pieces. Stops when two runs share ends, which could not be told apart."""
    out, seen = {}, {}
    for start, chain, stop in ln.runs(band, ln.crossover_strands(band)):
        a, b = end_key(band, start, beyond), end_key(band, stop, beyond)
        flip = _end_order(b) < _end_order(a)
        run = f"{b}-{a}" if flip else f"{a}-{b}"
        if run in seen:
            raise StagingMapError(f"tracks {seen[run]} and {chain[0][0]} both run {run}: name them apart")
        seen[run] = chain[0][0]
        pieces = chain[::-1] if flip else chain
        for i, (sid, rev) in enumerate(pieces, 1):
            out[sid] = (run if len(pieces) == 1 else f"{run} #{i}", rev != flip)
    return out


def placeholders(band) -> tuple[dict, dict, dict]:
    """({switch node: turnout placeholder}, {switch node: OS placeholder}, {strand id: (piece reference, reversed)})
    of the staging band (piece_refs). Inner crossover strands carry none (the plugin draws them inside the
    crossover). A crossover half is told apart by where the run from its leg A goes."""
    halves = crossover_halves(band)
    refs = piece_refs(band)
    leg_a = {}
    for start, _chain, stop in ln.runs(band, ln.crossover_strands(band)):
        leg_a[tuple(start)], leg_a[tuple(stop)] = end_key(band, stop), end_key(band, start)
    turnouts, os_ = {}, {}
    for n, d in sorted(band["nodes"].items()):
        if d["kind"] == "dx":
            raise StagingMapError(f"staging switch {d.get('label')}: a double crossover, which staging has none of")
        if d["kind"] != "switch":
            continue
        label = lc.bare(d.get("label"))
        if not re.fullmatch(r"\d+", label or ""):
            raise StagingMapError(f"staging switch node {n}: label {d.get('label')!r} is no switch number")
        turnouts[n] = f"Switch {label}"
        if n in halves and (n, "A") not in leg_a:
            raise StagingMapError(f"crossover half {label} at {n}: no run leaves its leg A to tell it apart by")
        os_[n] = f"OS {label} A-{leg_a[(n, 'A')]}" if n in halves else f"OS Switch {label}"
    if len(set(os_.values())) != len(os_):
        raise StagingMapError(f"two crossover halves have one key: {sorted(os_.values())}")
    return turnouts, os_, refs


def track_placeholder(piece: str, k: int, count: int) -> str:
    return f"Track {piece}" if count == 1 else f"Track {piece} {k}/{count}"


def strand_placeholders(ref: tuple[str, bool], count: int = 1) -> list[str]:
    """The trial keys of a strand's `count` blocks, from the strand's first end as drawn: `ref` is its (piece, whether
    it runs against the piece) from piece_refs or band_refs, and the k-th of n blocks is counted from the piece's
    first end (track_placeholder). The one rule the writer (build_device_map.piece_trials) and every reader key a
    strand by. ValueError on a count under 1."""
    if count < 1:
        raise ValueError(f"a strand carries at least one block, not {count}")
    piece, against = ref
    keys = [track_placeholder(piece, k, count) for k in range(1, count + 1)]
    return keys[::-1] if against else keys


def piece_of(key: str) -> tuple[str, int, int]:
    """(piece, k, n) of a track trial key ("Track 37C-39C #2 1/2" -> ("37C-39C #2", 1, 2); one block: k = n = 1).
    StagingMapError on a key that is no track key."""
    m = TRACK_RE.fullmatch(key)
    if not m:
        raise StagingMapError(f"{key!r} is no track trial key (Track <end>-<end>[ #i][ k/n])")
    return (m.group(1), int(m.group(2)), int(m.group(3))) if m.group(2) else (m.group(1), 1, 1)


def split_names(cell: str) -> list[str]:
    return [t.strip() for t in (cell or "").split(",") if t.strip()]


def staging_band():
    """The staging band as build_layout_le.py draws it (the plugin's drawn_bands: the preferences' le_shift and
    le_longer_straights): (band, its options, the plugin's core)."""
    _sheet, le_mod, core = lc.plugin()
    bands, page = lc.schematic()
    try:
        bands = le_mod.drawn_bands(bands, page)
    except core.SchematicError as exc:
        raise StagingMapError(f"schematic le: {exc}") from None
    try:
        _t, band, opts = bands[lc.base_band(bands)]     # the band of the level the base holds, by its level
    except lc.BuildError as exc:
        raise StagingMapError(f"the staging band: {exc}") from None
    return band, opts, core


def mast_kind(r: dict) -> str:
    """The kind of slot a staging_masts.csv row stands in: a switch number means a turnout leg, no protected block an
    end bumper, else an anchor."""
    if r["switch"]:
        return "turnout"
    return "end bumper" if not r["protects"] else "anchor"


def occupancy_blocks(r: dict) -> list[str]:
    """The blocks an occupancy row's detector serves, its `blocks` column ("Track S-1;Track S-1 West")."""
    return railroad.device_list(r["blocks"])


def check_helix(band, names: dict, helix: dict | None = None) -> list[str]:
    """Each helix track of plan_overrides.json is drawn on the staging band from its staging_switch, and its staging
    piece is that file's block (load()'s names)."""
    helix = mr.read_helix_tracks() if helix is None else helix
    bad = []
    for plan, h in sorted(helix.items()):
        sids = [sid for sid, s in band["strands"].items() if s.get("name") == plan]
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


def read_device_rows(path: Path = DEVICE_MAP) -> list[dict]:
    """Staging's device-map rows: the level 1 rows of the master at `path` (hartlib.devices.device_map_lines), each a
    dict of the device-map columns and `role`. StagingMapError when the master cannot be read or has none."""
    try:
        rows = [r for _, r in devices.device_map_lines((str(LEVEL),), path)]
    except railroad.FactsError as exc:
        raise StagingMapError(str(exc)) from None
    if not rows:
        raise StagingMapError(f"{paths.rel(path)}: no staging rows")
    return rows


def desk_areas(path: Path = STATIONS) -> list[railroad.DeskArea]:
    """Every level's desk areas of stations.csv (hartlib.railroad_facts.read_desk_areas); StagingMapError, naming the
    file, line and station, on a row that breaks its rules."""
    try:
        return railroad.read_desk_areas(path)
    except railroad.FactsError as exc:
        raise StagingMapError(str(exc)) from None


def switch_areas(path: Path = STATIONS, level: int = LEVEL) -> dict[str, str]:
    """{switch number: the name of the desk area it is in} for `level` (staging unless given)."""
    return {s: a.name for a in desk_areas(path) if a.level == level for s in a.switches}


def read_rows(path: Path, columns) -> list[dict]:
    try:
        rows = lc.read_csv(path)
    except OSError as exc:
        raise StagingMapError(f"cannot read {paths.rel(path)}: {exc}") from None
    if not rows:
        raise StagingMapError(f"{paths.rel(path)}: no rows")
    if list(rows[0]) != list(columns):
        raise StagingMapError(f"{paths.rel(path)}: columns {list(rows[0])}, not {list(columns)}")
    return rows


def switch_facts(read):
    """`read()` (a le_common reader of the staging switches, hartlib.railroad: switches.csv,
    ADR-021, read once per run), with its BuildError as a StagingMapError naming the file and row."""
    try:
        return read()
    except lc.BuildError as exc:
        raise StagingMapError(str(exc)) from None


def closed_legs() -> dict:
    """{OS block: closed leg block} of every staging switch (switches.csv, ADR-021)."""
    return {leg.os_block: leg.closed for sw in switch_facts(lc.staging_switches).values() for leg in sw.legs}


def run_blocks(band, names: dict) -> list[tuple]:
    """[(start (node, port), [block, ...], end (node, port))]: each run of the band (le_names.runs: tracks joined
    through turnbacks, crossover insides left out) with its blocks from `names` in order from its start; a block
    that runs on through a turnback (Brick-Plane) counted once."""
    out = []
    for start, chain, end in ln.runs(band, ln.crossover_strands(band)):
        seq = []
        for sid, rev in chain:
            bl = names["blocks"][sid]
            for b in (bl[::-1] if rev else bl):
                if not seq or seq[-1] != b:
                    seq.append(b)
        out.append((start, seq, end))
    return out


def leg_first_blocks(band, names: dict) -> dict:
    """{(switch node, leg): first block past the switch's own OS block along that leg}: along the run of tracks from
    that leg (through turnbacks), else the OS block of the switch at the run's far end; None at a bumper."""
    nodes = band["nodes"]
    out = {}
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


def normal_legs(band, names: dict) -> dict:
    """{plain switch node: "B" or "C"}: the drawn leg whose first block is the switch's closed leg in switches.csv."""
    closed = closed_legs()
    first = leg_first_blocks(band, names)
    halves = crossover_halves(band)
    out, bad = {}, []
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


def part_lines(device_map: Path = DEVICE_MAP) -> list[tuple[int, dict]]:
    """(line, row) of staging's parts (role part: a piece of track inside another block, part_of naming it), which
    the device maps leave out (hartlib.devices.OUT_OF_MAPS)."""
    try:
        return devices.part_lines((str(LEVEL),), device_map)
    except railroad.FactsError as exc:
        raise StagingMapError(str(exc)) from None


def load(band, device_map: Path = DEVICE_MAP, masts_path: Path = MASTS, stations_path: Path = STATIONS,
         turnout_idents: bool = True, with_masts: bool = True,
         interlockings_path: Path = INTERLOCKINGS) -> dict:
    """The plugin's names for the staging band from the three files alone: turnouts, os, blocks, normal (from
    switches.csv), masts, and with `turnout_idents` each turnout's Layout Editor ident from switches.csv
    (le_ident, ADR-021); with_masts False leaves the masts out. Stops on a row that breaks the rules every row of
    devices.csv keeps (check_device_master.row_problems), any placeholder no row names, any row the drawing does not
    use, a piece of the drawing on no row or on two, a broken k/n run, or a mast row that is not well formed. A
    part (part_lines) is a JMRI block of its own on every level (owner, 2026-11-20): its pieces are its own block, and
    staging_parts gives {part: the block it is part of} (os_layer reads the blocks as the masts do)."""
    import check_device_master as cdm       # the rules of every level's rows (it imports this module)
    try:
        lines = [(n, r) for n, r in cdm.master_lines(device_map) if r["level"] == str(LEVEL)]
        interlockings = railroad.read_interlockings(interlockings_path)
        cps = cdm.control_points(interlockings, stations_path)
        places = cdm.known_places(interlockings, stations_path)
    except (cdm.DeviceMasterError, railroad.FactsError) as exc:
        raise StagingMapError(str(exc)) from None
    if not lines:
        raise StagingMapError(f"{paths.rel(device_map)}: no staging rows")
    # staging's rows cross no level but a helix block's, whose cp lists the places it joins
    bad = cdm.row_problems(lines, cps, paths.rel(device_map), ends_cps={}, places=places)
    if bad:
        raise StagingMapError("; ".join(bad))
    rows = [r for _n, r in lines]
    cp_names = cps.get(str(LEVEL), set())
    turnout_ph, os_ph, strands = placeholders(band)
    by_ph = {ph: (r["layer"], r["user_name"], r["jmri_name"]) for r in rows for ph in split_names(r["trial_name"])}
    parts = {}
    for n, r in part_lines(device_map):          # a part's pieces are its own JMRI block
        parts[r["user_name"]] = r["part_of"]
        for ph in split_names(r["trial_name"]):
            if ph in by_ph:
                bad.append(f"line {n}: part {r['user_name']}'s trial_name {ph} is another row's as well")
            by_ph[ph] = ("block", r["user_name"], "")
    used = set()

    def get(ph, layer):
        got = by_ph.get(ph)
        if got is None or got[0] != layer:
            bad.append(f"no {layer} row has trial_name {ph}")
            return None
        used.add(ph)
        return got[2] if layer == "turnout" else got[1]

    names = dict(turnouts={n: get(ph, "turnout") for n, ph in turnout_ph.items()},
                 os={n: get(ph, "block") for n, ph in os_ph.items()}, blocks={})
    runs = defaultdict(dict)
    for ph, (layer, _u, _j) in by_ph.items():
        m = TRACK_RE.fullmatch(ph)
        if layer == "block" and m:
            k, count = (int(m.group(2)), int(m.group(3))) if m.group(2) else (1, 1)
            runs[m.group(1)][k] = (count, ph)
    for sid, (piece, against) in sorted(strands.items()):
        got = runs.pop(piece, {})
        if not got:
            bad.append(f"track {piece} ({sid}) is on no block row: give it a block, or a part row naming the block "
                       "it is part of (build_device_map.py writes them)")
            continue
        counts = {c for c, _ph in got.values()}
        if len(counts) != 1 or sorted(got) != list(range(1, next(iter(counts)) + 1)):
            bad.append(f"track {piece}: blocks {sorted(ph for _c, ph in got.values()) or 'none'} are not 1/n to n/n")
            continue
        blocks = [get(got[k][1], "block") for k in sorted(got)]       # from the run's first end
        names["blocks"][sid] = blocks[::-1] if against else blocks    # from the strand's first end, as drawn
    for sid, got in runs.items():
        bad.append(f"trial names for track {sid}, which the staging drawing does not have: "
                   f"{sorted(ph for _c, ph in got.values())}")
    unused = sorted(set(by_ph) - used - {ph for got in runs.values() for _c, ph in got.values()})
    if unused:
        bad.append(f"trial names the staging drawing does not have: {unused}")
    if bad:
        raise StagingMapError(f"{paths.rel(device_map)}: " + "; ".join(bad))
    names["normal"] = normal_legs(band, os_layer(names, parts))  # switches.csv names a leg by its first OS block
    if turnout_idents:
        ident_of = switch_facts(lc.switch_idents)
        idents = {}
        for n, ph in turnout_ph.items():
            ident = ident_of.get(ph.removeprefix("Switch "))
            if not ident:
                bad.append(f"{ph} has no le_ident in switches.csv")
            idents[n] = ident
        names["idents"] = dict(turnouts=idents, boundaries=[], ends={}, segments={})
    if with_masts:              # build_masts.py reads the rest to write the masts
        names["masts"] = load_masts(masts_path, cp_names, rows)
    if bad:
        raise StagingMapError("; ".join(bad))
    return names


def staging_parts(device_map: Path = DEVICE_MAP) -> dict[str, str]:
    """{part: the block it is part of} of staging's parts (part_lines): each a JMRI block of its own (owner,
    2026-11-20) that the masts read inside its block (os_layer)."""
    return {r["user_name"]: r["part_of"] for _n, r in part_lines(device_map)}


def os_layer(names: dict, parts: dict) -> dict:
    """A copy of load()'s names with each part's pieces given to the block it is part of (`parts`, staging_parts),
    as the one mast process reads a level's block layer on every level (main and upper: block_layer.Layer.bands): a
    mast's place and the blocks it protects follow the OS blocks, a part being inside its OS block (mast_plan,
    build_masts). StagingMapError on a part whose block is itself a part."""
    bad = sorted(p for p, of in parts.items() if of in parts)
    if bad:
        raise StagingMapError(f"parts {bad} are part of another part")
    return dict(names, blocks={sid: [parts.get(b, b) for b in v] for sid, v in names["blocks"].items()})


def load_masts(path: Path, cp_names: set, device_rows: list[dict]) -> list[dict]:
    """The plugin's staging masts from staging_masts.csv: each with its facing and protected blocks, its kind of slot
    (mast_kind), hidden for a virtual mast and its icon size (hartlib.tables.mast_icon_size). Stops on a row whose
    mast, heads or system name the device map does not hold as the same mast, or whose switch no turnout row is."""
    rows = read_rows(path, level_masts.FIELDS)
    dev = {(r["layer"], r["user_name"]): r for r in device_rows}
    heads = {r["system_name"]: r["user_name"] for r in device_rows if r["layer"] == "head"}
    switches = {r["trial_name"].removeprefix("Switch ") for r in device_rows
                if r["layer"] == "turnout" and r["trial_name"].startswith("Switch ")}
    out, bad, seen = [], [], set()
    for i, r in enumerate(rows, 2):
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
        entry = dict(mast=name, facing=r["facing"], protects=protects, kind=mast_kind(r),
                     hidden=r["system_name"].startswith("IF$vsm:"), icon=list(size))
        if r["leg"]:
            entry["leg"] = r["leg"]
        if entry["kind"] == "end bumper":       # may stand at a helix join instead (the three-level panel)
            entry["or_join"] = True
        out.append(entry)
    if bad:
        raise StagingMapError(f"{paths.rel(path)}: " + "; ".join(bad))
    return sorted(out, key=lambda m: m["mast"])


def load_signal_masts(path: Path | None = None, masts_path: Path | None = None) -> list[dict]:
    """The staging masts as build_signals.py reads them: staging_signals.csv's plan facts joined with
    staging_masts.csv's blocks and slot kind (mast_kind), with the fields signal_rows and build_signals.check_lengths
    read). Stops on a mast in one file and not the other, or a value
    that is not as the frozen file held it."""
    path, masts_path = path or SIGNALS, masts_path or MASTS
    plan = read_rows(path, SIGNAL_COLUMNS)
    blocks = {r["mast"]: r for r in read_rows(masts_path, level_masts.FIELDS)}
    if {r["mast"] for r in plan} != set(blocks):
        raise StagingMapError(f"{paths.rel(path)} and {paths.rel(masts_path)} name different masts: "
                              f"{sorted({r['mast'] for r in plan} ^ set(blocks))}")
    out, bad = [], []
    for i, r in enumerate(plan, 2):
        try:
            run = r["run"].split(LIST)
            if len(run) != 2 or not run[0] or r["dir"] not in ("east", "west") or \
                    r["signal_kind"] not in ("field", "virtual", "planned"):
                raise ValueError("run, dir or signal_kind")
            b = blocks[r["mast"]]
            out.append(dict(mast=r["mast"], kind=mast_kind(b), facing=b["facing"],
                            protects=[x for x in b["protects"].split(";") if x], signal=r["signal"],
                            toward=r["toward"], run=run, names=[x for x in r["names"].split(LIST) if x],
                            edge_cm=float(r["edge_cm"]), cm_from_toward=float(r["cm_from_toward"]), dir=r["dir"],
                            signal_kind=r["signal_kind"], heads=int(r["heads"]), schematic_edge=r["schematic_edge"],
                            schematic_toward_node=r["schematic_toward_node"]))
        except (ValueError, KeyError) as exc:
            bad.append(f"line {i} ({r['mast']}): {exc}")
    if bad:
        raise StagingMapError(f"{paths.rel(path)}: " + "; ".join(bad))
    return out


def staging_chains(band, names: dict) -> list[dict]:
    """The staging tracks between switches and ends, as the hand-drawn panel's tracks were read once:
    [{ends: [(Layout Editor ident or "END", band port), ...], blocks: [...]}], each a run of the band (through
    turnbacks) with its blocks from the device map (load()) in order. A switch's ident is switches.csv's le_ident
    (names["idents"]); the port is the band's, not a Layout Editor leg letter."""
    nodes = band["nodes"]
    idents = names["idents"]["turnouts"]
    out = []
    for start, seq, end in run_blocks(band, names):
        ends = [("END", str(e[1])) if nodes[e[0]]["kind"] != "switch" else (idents[e[0]], str(e[1]))
                for e in (start, end)]
        out.append(dict(ends=ends, blocks=seq))
    return out


def mast_facts(device_map: Path = DEVICE_MAP, masts_path: Path = MASTS) -> dict:
    """{mast: {kind, facing, protects, hidden, turnout}} of every staging mast from staging_masts.csv: its slot kind
    (mast_kind), blocks, hidden (a virtual mast) and, for a turnout mast, the turnout name the panels bind its switch
    by (the device map's jmri_name)."""
    turnout_of = {r["trial_name"].removeprefix("Switch "): r["jmri_name"]
                  for r in read_device_rows(device_map) if r["layer"] == "turnout" and r["trial_name"]}
    out = {}
    for r in read_rows(masts_path, level_masts.FIELDS):
        kind = mast_kind(r)
        if kind == "turnout" and r["switch"] not in turnout_of:
            raise StagingMapError(f"{paths.rel(masts_path)}: {r['mast']} is on switch {r['switch']}, which the "
                                  "device map has no turnout for")
        out[r["mast"]] = dict(kind=kind, facing=r["facing"], protects=[b for b in r["protects"].split(";") if b],
                              hidden=r["system_name"].startswith("IF$vsm:"),
                              **({"turnout": turnout_of[r["switch"]]} if kind == "turnout" else {}))
    return out


def signal_rows(masts: list[dict]) -> list[dict]:
    """signals.json[staging]'s signals from the staging masts (load_signal_masts), in the plugin's order (by number,
    then name)."""
    rows = [dict(mast=m["signal"], toward=m["toward"], run=list(m["run"]), names=list(m["names"]),
                 edge_cm=m["edge_cm"], cm_from_toward=m["cm_from_toward"], dir=m["dir"], kind=m["signal_kind"],
                 heads=m["heads"], source="le_panel", _edge=m["schematic_edge"],
                 _toward_node=m["schematic_toward_node"]) for m in masts]

    def key(r):
        n = re.match(r"\d+", r["mast"])
        return (int(n.group()) if n else 10 ** 9, r["mast"])
    return sorted(rows, key=key)
