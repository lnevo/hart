#!/usr/bin/env python3
"""Staging's facts in the device map's form: the source the Layout Editor build, the signals and the CATS desks read.

    python3 tools/schematic/staging_device_map.py --check   # exit 1 unless the four files hold their rules

The source since the device-map switch-over (owner, 2026-11-17), when the frozen hand-drawn files (staging_le/) and the
conversion from them retired. control_points_staging.csv and the non-signal rows of device_map_staging.csv are kept by
hand; build_staging_masts.py writes staging_masts.csv, staging_signals.csv and the mast and head rows. Edit these files,
not a panel. `make panels` (its staging-map step) and tools/check.sh
run --check: every file in its shape (load, load_signal_masts, mast_facts, check_rows), every device the same bean in
tables.xml (check_tables: system and user names, a turnout's feedback sensors, a block's detector, a mast's heads),
and the control points the schematic's (staging.plan_overrides.json). It prints SKIPPED and exits 0 when the plugin
submodule is not checked out (1 with SCHEMATIC_REQUIRED=1), as build_device_map.py does.

Staging's objects are field devices: every system name, user name and binding here is the railroad's own.

Files (jmri/layouts/hart/data/schematic/):
- device_map_staging.csv, build_device_map.COLUMNS. Layers as main and upper: turnout (and its LCC alias
  "DCC Switch <n>"), fb, block, occupancy, mast, head. Staging is the field, so system_name is the live device;
  jmri_name is the name tables.xml and the panels bind it by: a turnout's is the Layout Editor's turnoutname (some
  bind "M2T408", some "Switch 23"), every other row's its system name. trial_name is the link to the drawing, as for
  main and upper (placeholders(), below). The facts are in columns (hartlib.railroad.DEVICE_FACTS, checked by
  device_facts; the comment and notes stay text for people): one occupancy row per detector, its `blocks` the blocks
  it serves (a throat block and its yard track, or a stub and its switch, share one) and its `detector` wired, all
  of staging's being in the field; a block's `stop` "yes" for a Dispatcher System station, as its tables.xml comment
  marks it ("; stop", checked); a mast's `switch`, `facing` and `protects` as staging_masts.csv has them.
  A helix block (helix_tracks.csv: Track Helix Outer, Track Helix Inner) is one JMRI block from its staging switch
  up the helix (owner, 2026-11-20): its staging piece is a block row here, and its detector is the occupancy row of
  device_map_main_upper.csv, which names the same block for the piece on its level (shared_blocks).
- short_tracks_staging.csv (SHORT_COLUMNS): a short track between two switches with no block row of its own takes
  the OS block whose gap it sits inside (one of its two switches'), keyed by the two switch numbers, never by an
  edge id (read_short_tracks, short_track_blocks: a track with no row, a row with no such track or with a track that
  has its own block, or two tracks between the same switches, stops). Today the track from Switch 35 to Switch 37,
  in OS Switch 35a.
- control_points_staging.csv, the columns of control_points_main_upper.csv: the staging stations of
  staging.plan_overrides.json's control_points (the schematic's source), held equal by --check.
- staging_masts.csv, hartlib.level_masts.FIELDS. A mast's kind of slot follows from its row (mast_kind): a switch
  number means a turnout mast, no protected block an end bumper (buffer stop) mast, else an anchor mast. Hidden is a
  virtual mast (IF$vsm), its icon size hartlib.tables.mast_icon_size.
- staging_signals.csv (SIGNAL_COLUMNS): each mast's signal-plan facts (its schematic run, lengths, direction, kind
  and heads). build_signals.py writes staging.signals.json from it and staging_masts.csv (load_signal_masts,
  signal_rows).

Readers: build_layout_le.py (load), build_signals.py (load_signal_masts, staging_chains), build_cats_panel.py
(staging_chains), hartlib.railroad's staging masts and check_layout_facts.py (staging_masts.csv),
test_le_mast_parity.py (mast_facts).

Trial names (placeholders()): the drawing's own keys for staging, as placeholder_names gives main and upper theirs.
- turnout: "Switch <n>" (both halves of a single crossover: one turnout).
- OS block: "OS Switch <n>" of a plain switch; "OS <n> at <node>" of a crossover half (staging's crossovers 7, 23
  and 35 have an OS block per half: OS Switch 7 and 7b, 23a and 23b, 35a and 35b; the half's key is not written as
  a block name, so check_name_copies.py does not take it for one).
- track block: "Track <strand>" for a track of one block, "Track <strand> <k>/<n>" for the k-th of its n blocks from
  the strand's first end (S-1 is "Track e23 1/3" West, "2/3" the body, "3/3" East). Strand and node ids are the
  plan's (as main and upper's "Track <edge>"); --check stops when the plan renames one.
A block that several tracks or a switch share lists every placeholder, comma separated.

The panel's own icons and labels are not device facts and are not here: the status cluster, captions and backdrop
are in panel_items.json (panel_items.py); the occupancy lamps and station clusters are parked with the Dispatcher
System (jmri/layouts/hart/parked/staging_panel_lamps.json).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_device_map as bdm  # noqa: E402  COLUMNS
import le_common as lc  # noqa: E402  the band key, plugin, solved schematic and the files the build reads
import le_names as ln  # noqa: E402  runs and crossovers
import build_main_upper_masts as bmm  # noqa: E402  LEGS: two masts on one block pair, by letter
import mast_rule as mr  # noqa: E402  the helix tracks (helix_tracks.csv)
import publish_draft as pd  # noqa: E402  DATA and the plugin cache
from hartlib import level_devices, level_masts, paths, railroad, tables  # noqa: E402

LEVEL = 1
DEVICE_MAP = pd.DATA / "device_map_staging.csv"
CPS = pd.DATA / "control_points_staging.csv"
MASTS = pd.DATA / "staging_masts.csv"
SIGNALS = pd.DATA / "staging_signals.csv"
OVERRIDES = pd.DATA / "staging.plan_overrides.json"
# staging_signals.csv: the signal-plan facts build_signals.py writes staging.signals.json from; lists inside a cell
# are LIST separated
SIGNAL_COLUMNS = ["mast", "signal", "toward", "run", "names", "edge_cm", "cm_from_toward", "dir", "signal_kind",
                  "heads", "schematic_edge", "schematic_toward_node"]
LIST = ";"
# what staging.signals.json names as its source: the file the masts were first read from (the hand-drawn panel's)
SIGNALS_SOURCE = "tables.xml"
CP_COLUMNS = ["cp_id", "cp_name", "level", "switches", "area", "notes"]
# short_tracks_staging.csv: a short track between two switches with no block of its own, and the OS block whose gap it
# sits inside (owner, 2026-11-20), keyed by the two switches, never by the drawing's edge ids
SHORT_TRACKS = pd.DATA / "short_tracks_staging.csv"
SHORT_COLUMNS = ["switch_a", "switch_b", "block", "notes"]
LAYERS = ("turnout", "fb", "block", "occupancy", "mast", "head")
TRACK_RE = re.compile(r"Track (\S+?)(?: (\d+)/(\d+))?")


class StagingMapError(RuntimeError):
    pass


# ---------------------------------------------------------------- placeholders: the drawing's keys


def crossover_halves(band) -> dict:
    """{node: other half} for each switch that is half of a single crossover (two switches of one label joined C to C,
    build_layout_le.crossover_strands)."""
    out = {}
    for sid in ln.crossover_strands(band):
        u, v = band["strands"][sid]["src"][0], band["strands"][sid]["dst"][0]
        out[u], out[v] = v, u
    return out


def placeholders(band) -> tuple[dict, dict, list]:
    """({switch node: turnout placeholder}, {switch node: OS placeholder}, [strand ids that carry blocks]) of the
    staging band. Inner crossover strands carry none (the plugin draws them inside the crossover)."""
    halves = crossover_halves(band)
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
        os_[n] = f"OS {label} at {n}" if n in halves else f"OS Switch {label}"
    inner = ln.crossover_strands(band)
    return turnouts, os_, sorted(s for s in band["strands"] if s not in inner)


def track_placeholder(sid: str, k: int, count: int) -> str:
    return f"Track {sid}" if count == 1 else f"Track {sid} {k}/{count}"


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
    keys = [lc.band_key(t) for t, _b, _o in bands]
    if lc.STAGING not in keys:
        raise StagingMapError(f"no {lc.STAGING} band in the schematic (bands: {', '.join(keys)})")
    _t, band, opts = bands[keys.index(lc.STAGING)]
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


def read_short_tracks(path: Path | None = None) -> dict:
    """{(switch, switch) in number order: (OS block, line)} of short_tracks_staging.csv. Stops on a file not in its
    shape, a row naming one switch twice or a block that is no OS block, or a pair given twice (a short track takes
    one block)."""
    path = path or SHORT_TRACKS
    out, bad = {}, []
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)                     # none is right: a staging with no short track
    except OSError as exc:
        raise StagingMapError(f"cannot read {paths.rel(path)}: {exc}") from None
    if reader.fieldnames != SHORT_COLUMNS:
        raise StagingMapError(f"{paths.rel(path)}: columns {reader.fieldnames}, not {SHORT_COLUMNS}")
    for i, r in enumerate(rows, 2):
        a, b = r["switch_a"].strip(), r["switch_b"].strip()
        if not (a.isdigit() and b.isdigit()) or a == b or not r["block"].startswith("OS Switch "):
            bad.append(f"line {i}: switches {a!r} and {b!r} are two switch numbers and {r['block']!r} an OS block")
            continue
        key = tuple(sorted((a, b), key=int))
        if key in out:
            bad.append(f"line {i}: the track from Switch {key[0]} to Switch {key[1]} is given a block twice "
                       f"(line {out[key][1]})")
            continue
        out[key] = (r["block"], i)
    if bad:
        raise StagingMapError(f"{paths.rel(path)}: " + "; ".join(bad))
    return out


def short_track_blocks(band, names: dict, strands: list, short: dict) -> tuple[dict, list]:
    """({strand id: [OS block]}, problems) for the staging tracks the device map gives no block (no trial name):
    each must run from one switch to another, be the only such track between them, and have its row in `short`
    (read_short_tracks), naming the OS block of one of its two switches, the one whose gap it sits inside. Every
    row of `short` must be used (a stale row stops)."""
    nodes, out, bad, used = band["nodes"], {}, [], set()
    pairs = defaultdict(list)
    for sid in strands:
        s = band["strands"][sid]
        ends = [s["src"][0], s["dst"][0]]
        if all(nodes[n]["kind"] == "switch" for n in ends):
            pairs[tuple(sorted((lc.bare(nodes[n].get("label")) for n in ends), key=int))].append((sid, ends))
    for sid in strands:
        s = band["strands"][sid]
        ends = [s["src"][0], s["dst"][0]]
        if sid in names["blocks"]:
            continue
        if not all(nodes[n]["kind"] == "switch" for n in ends):
            bad.append(f"track {sid}: no block in the device map, and it does not run between two switches")
            continue
        key = tuple(sorted((lc.bare(nodes[n].get("label")) for n in ends), key=int))
        what = f"the short track from Switch {key[0]} to Switch {key[1]} ({sid})"
        if key not in short:
            bad.append(f"{what} has no block: give it the OS block whose gap it sits inside in {SHORT_TRACKS.name}")
            continue
        if len(pairs[key]) != 1:
            bad.append(f"{what}: {len(pairs[key])} tracks join those switches, so {SHORT_TRACKS.name} cannot tell "
                       "which it means")
            continue
        block = short[key][0]
        own = {names["os"].get(n) for n in ends}
        if block not in own:
            bad.append(f"{what}: {SHORT_TRACKS.name} gives it {block}, which is the OS block of neither of its "
                       f"switches ({', '.join(sorted(b for b in own if b))})")
            continue
        out[sid] = [block]
        used.add(key)
    for key in sorted(set(short) - used, key=lambda k: (int(k[0]), int(k[1]))):
        ids = [sid for sid, _e in pairs.get(key, [])]
        why = "the device map gives it a block of its own" if any(i in names["blocks"] for i in ids) else \
            "the staging drawing has no such track"
        bad.append(f"{SHORT_TRACKS.name} line {short[key][1]}: Switch {key[0]} to Switch {key[1]}: {why}")
    return out, bad


def stop_token(comment: str) -> bool:
    """Whether a JMRI block comment marks a Dispatcher System station: "stop", or ending "; stop" (the stock
    Dispatcher System's station mark)."""
    c = (comment or "").strip()
    return c == "stop" or c.endswith("; stop")


def shared_blocks(rows: list[dict], level_map: railroad.DeviceMap, helix: dict | None = None) -> dict:
    """{block: its main or upper occupancy row} of the staging blocks device_map_main_upper.csv also names: the helix
    blocks, one JMRI block from staging up the helix, whose detector is that map's. Stops unless they are exactly
    helix_tracks.csv's blocks, each with one occupancy row there."""
    helix = mr.read_helix_tracks() if helix is None else helix
    staging = {r["user_name"] for r in rows if r["layer"] == "block"}
    shared = staging & set(level_map.blocks)
    want = {v["block"] for v in helix.values()}
    if shared != want:
        raise StagingMapError(f"staging and main or upper blocks of one name: {sorted(shared)}; only the helix blocks "
                              f"of {mr.HELIX_TRACKS.name} ({sorted(want)}) may be both")
    occ = level_map.by_user("occupancy")
    out = {}
    for b in sorted(shared):
        o = occ.get(level_devices.occupancy_user(b))
        if o is None:
            raise StagingMapError(f"{b}: no occupancy row in {level_map.path.name if level_map.path else 'the main and upper device map'}")
        out[b] = o
    return out


def check_helix(band, names: dict, helix: dict | None = None) -> list[str]:
    """Each helix track of helix_tracks.csv is drawn on the staging band from its staging_switch, and its staging
    piece is that file's block (load()'s names)."""
    helix = mr.read_helix_tracks() if helix is None else helix
    bad = []
    for plan, h in sorted(helix.items()):
        sids = [sid for sid, s in band["strands"].items() if s.get("name") == plan]
        if len(sids) != 1:
            bad.append(f"helix track {plan}: drawn {len(sids)} times on the staging band")
            continue
        s = band["strands"][sids[0]]
        labels = [band["nodes"][e[0]].get("label") for e in (s["src"], s["dst"])
                  if band["nodes"][e[0]]["kind"] == "switch"]
        if labels != [h["staging_switch"]] or names["blocks"].get(sids[0]) != [h["block"]]:
            bad.append(f"helix track {plan}: from switch {', '.join(map(str, labels)) or 'none'} in block(s) "
                       f"{names['blocks'].get(sids[0])}, {mr.HELIX_TRACKS.name} says Switch {h['staging_switch']}, "
                       f"{h['block']}")
    return bad


# ---------------------------------------------------------------- reading the files


def check_rows(rows: list[dict], shared=frozenset()) -> None:
    """Every block has exactly one occupancy row naming it, but a helix block (`shared`: shared_blocks), whose
    detector is the main and upper device map's; no two rows of one layer share a system name, a jmri_name
    or a user name (a turnout's LCC alias "DCC Switch <n>" is a turnout of its own, MTT<dcc>, with its own names);
    every row is a whole field device."""
    bad = []
    blocks = [r["user_name"] for r in rows if r["layer"] == "block" and r["user_name"] not in shared]
    served = [b for r in rows if r["layer"] == "occupancy" for b in occupancy_blocks(r)]
    if sorted(blocks) != sorted(served):
        bad.append(f"blocks and occupancy rows differ: {sorted(set(blocks) ^ set(served))} "
                   f"(or one is served twice)")
    for layer in LAYERS:
        mine = [r for r in rows if r["layer"] == layer]
        for col in ("system_name", "jmri_name", "user_name"):
            vals = [r[col] for r in mine]
            if not all(vals) or len(set(vals)) != len(vals):
                bad.append(f"{layer} rows: a {col} is empty or given twice")
    if bad:
        raise StagingMapError("staging device map: " + "; ".join(bad))


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
    """`read()` (a le_common reader of the staging switches, hartlib.railroad: switches.csv and switch_legs.csv,
    ADR-021, read once per run), with its BuildError as a StagingMapError naming the file and row."""
    try:
        return read()
    except lc.BuildError as exc:
        raise StagingMapError(str(exc)) from None


def closed_legs() -> dict:
    """{OS block: closed leg block} of every staging switch (switch_legs.csv, ADR-021)."""
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
    """{plain switch node: "B" or "C"}: the drawn leg whose first block is the switch's closed leg in switch_legs.csv
    ("Track S-4 West" counts as S-4: a throat block is part of its yard track)."""
    closed = closed_legs()
    first = leg_first_blocks(band, names)
    halves = crossover_halves(band)
    track = lambda b: re.sub(r" (East|West)$", "", b or "")      # noqa: E731
    out, bad = {}, []
    for n, d in sorted(band["nodes"].items()):
        if d["kind"] != "switch" or n in halves:
            continue
        want = closed.get(names["os"][n])
        if want is None:
            bad.append(f"switch {d['label']}: {names['os'][n]} is not in switch_legs.csv")
            continue
        legs = [p for p in "BC" if first.get((n, p)) == want or track(first.get((n, p))) == want]
        if len(legs) != 1:
            bad.append(f"switch {d['label']}: closed leg {want} is first past {len(legs)} of its legs "
                       f"(B: {first.get((n, 'B'))}, C: {first.get((n, 'C'))})")
            continue
        out[n] = legs[0]
    if bad:
        raise StagingMapError("staging normal legs: " + "; ".join(bad))
    return out


def load(band, device_map: Path = DEVICE_MAP, masts_path: Path = MASTS, cps_path: Path = CPS,
         turnout_idents: bool = True, with_masts: bool = True, short_path: Path | None = None) -> dict:
    """The plugin's names for the staging band from the three files alone: turnouts, os, blocks, normal (from
    switch_legs.csv), masts, and with `turnout_idents` each turnout's Layout Editor ident from switches.csv
    (le_ident, ADR-021); with_masts False leaves the masts out. Stops on any placeholder no row names, any row the drawing does not use, a broken k/n run,
    or a mast row that is not well formed."""
    rows = read_rows(device_map, bdm.COLUMNS)
    cp_names = {r["cp_name"] for r in read_rows(cps_path, CP_COLUMNS)}
    turnout_ph, os_ph, strands = placeholders(band)
    by_ph, bad = {}, []
    for i, r in enumerate(rows, 2):
        if r["layer"] not in LAYERS:
            bad.append(f"line {i}: layer {r['layer']!r}")
            continue
        bad += [f"line {i}: {r['user_name']}: {p}" for p in railroad.device_facts(r)]
        if r["layer"] == "occupancy" and r["detector"] != "wired":
            bad.append(f"line {i}: {r['user_name']}: staging's detectors are in the field (wired), not "
                       f"{r['detector']!r}")
        if r["level"] != str(LEVEL):
            bad.append(f"line {i}: level {r['level']!r}, staging is {LEVEL}")
        if r["cp"] and r["cp"] not in cp_names:
            bad.append(f"line {i}: cp {r['cp']!r} is no staging control point")
        if not (r["user_name"] and r["system_name"] and r["jmri_name"]):
            bad.append(f"line {i}: user_name, system_name and jmri_name are needed for a field device")
        phs = split_names(r["trial_name"])
        if phs and r["layer"] not in ("turnout", "block"):
            bad.append(f"line {i}: a {r['layer']} row has a trial_name")
        for ph in phs:
            if ph in by_ph:
                bad.append(f"line {i}: trial_name {ph} is given to {by_ph[ph][1]} and {r['user_name']}")
            by_ph[ph] = (r["layer"], r["user_name"], r["jmri_name"])
    if bad:
        raise StagingMapError(f"{paths.rel(device_map)}: " + "; ".join(bad))
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
    for sid in strands:
        got = runs.pop(sid, {})
        if not got:
            continue                    # no block row: a short track, given its OS block below
        counts = {c for c, _ph in got.values()}
        if len(counts) != 1 or sorted(got) != list(range(1, next(iter(counts)) + 1)):
            bad.append(f"track {sid}: blocks {sorted(ph for _c, ph in got.values()) or 'none'} are not 1/n to n/n")
            continue
        names["blocks"][sid] = [get(got[k][1], "block") for k in sorted(got)]
    if not bad:
        got_short, problems = short_track_blocks(band, names, strands, read_short_tracks(short_path))
        names["blocks"].update(got_short)
        bad += problems
    for sid, got in runs.items():
        bad.append(f"trial names for track {sid}, which the staging drawing does not have: "
                   f"{sorted(ph for _c, ph in got.values())}")
    unused = sorted(set(by_ph) - used - {ph for got in runs.values() for _c, ph in got.values()})
    if unused:
        bad.append(f"trial names the staging drawing does not have: {unused}")
    if bad:
        raise StagingMapError(f"{paths.rel(device_map)}: " + "; ".join(bad))
    names["normal"] = normal_legs(band, names)
    if turnout_idents:
        ident_of = switch_facts(lc.switch_idents)
        idents = {}
        for n, ph in turnout_ph.items():
            ident = ident_of.get(ph.removeprefix("Switch "))
            if not ident:
                bad.append(f"{ph} has no le_ident in switches.csv")
            idents[n] = ident
        names["idents"] = dict(turnouts=idents, boundaries=[], ends={}, segments={})
    if with_masts:              # build_staging_masts.py reads the rest to write the masts
        names["masts"] = load_masts(masts_path, cp_names, rows)
    if bad:
        raise StagingMapError("; ".join(bad))
    return names


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
        if r["leg"] not in ("", *bmm.LEGS.values()):
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
                  for r in read_rows(device_map, bdm.COLUMNS) if r["layer"] == "turnout" and r["trial_name"]}
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
    """staging.signals.json's signals from the staging masts (load_signal_masts), in the plugin's order (by number,
    then name)."""
    rows = [dict(mast=m["signal"], toward=m["toward"], run=list(m["run"]), names=list(m["names"]),
                 edge_cm=m["edge_cm"], cm_from_toward=m["cm_from_toward"], dir=m["dir"], kind=m["signal_kind"],
                 heads=m["heads"], source="le_panel", _edge=m["schematic_edge"],
                 _toward_node=m["schematic_toward_node"]) for m in masts]

    def key(r):
        n = re.match(r"\d+", r["mast"])
        return (int(n.group()) if n else 10 ** 9, r["mast"])
    return sorted(rows, key=key)


# ---------------------------------------------------------------- the check (--check)

def check_control_points(path: Path = CPS, overrides: Path = OVERRIDES) -> list[str]:
    """control_points_staging.csv against staging.plan_overrides.json's control_points (the schematic's source):
    the same stations, codes and switches, in order."""
    want = json.loads(overrides.read_text(encoding="utf-8")).get("control_points")
    if not isinstance(want, dict) or not want:
        return [f"{overrides.name}: no control_points object"]
    rows = read_rows(path, CP_COLUMNS)
    got = [(r["cp_name"], r["cp_id"], [x.strip() for x in r["switches"].split(",") if x.strip()], r["level"])
           for r in rows]
    exp = [(name, f"cp_{(cp or {}).get('code', '').lower()}", list((cp or {}).get("switches") or []), str(LEVEL))
           for name, cp in want.items()]
    return [] if got == exp else [f"{path.name} is not {overrides.name}'s control points: {got} != {exp}"]


def check_tables(rows: list[dict], rr: railroad.Railroad, shared: dict | None = None) -> list[str]:
    """Every device-map row the same bean in tables.xml (hartlib.railroad's tables, by user name): its system name;
    a turnout's jmri_name a turnout name the tables hold and its feedback sensors the fb rows'; a block's detector an
    occupancy row naming that block (a helix block's, `shared`: shared_blocks, the main and upper map's virtual
    sensor, which the Layout Editor build binds); a mast's heads its head rows."""
    shared = shared or {}
    t = rr.tables
    heads = {tables.system_name(h): tables.user_name(h) for h in tables.signal_heads(t.root)}
    blocks = {tables.user_name(b): b for b in tables.blocks(t.root)}
    turnout_els = tables.by_any_name(tables.turnouts(t.root))
    by_layer = {"turnout": t.turnouts, "fb": t.sensors, "occupancy": t.sensors, "mast": t.masts}
    serves = {b: r for r in rows if r["layer"] == "occupancy" for b in occupancy_blocks(r)}
    fb = {r["user_name"] for r in rows if r["layer"] == "fb"}
    bad = []
    for r in rows:
        user, system, layer = r["user_name"], r["system_name"], r["layer"]
        if layer == "head":
            if heads.get(system) != user:
                bad.append(f"head {system}: tables.xml names it {heads.get(system)!r}, not {user!r}")
            continue
        if layer == "block":
            b = blocks.get(user)
            if b is None or tables.system_name(b) != system:
                bad.append(f"block {user}: tables.xml has {tables.system_name(b) if b is not None else 'none'}, "
                           f"not {system}")
                continue
            if stop_token(b.findtext("comment")) != (r["stop"] == "yes"):
                bad.append(f"block {user}: stop is {r['stop'] or 'empty'}, but its comment in tables.xml "
                           f"{'marks' if stop_token(b.findtext('comment')) else 'does not mark'} a station")
            occ = (b.findtext("occupancysensor") or "").strip()
            row = serves.get(user)
            if user in shared:
                if occ not in (shared[user].user_name, shared[user].jmri_name):
                    bad.append(f"helix block {user}: its detector in tables.xml is {occ!r}, the main and upper "
                               f"device map's {shared[user].user_name}")
            elif row is None or occ not in (row["user_name"], row["system_name"]):
                bad.append(f"block {user}: its detector in tables.xml is {occ!r}, the device map's "
                           f"{row['user_name'] if row else 'none'}")
            continue
        if by_layer[layer].get(user) != system:
            bad.append(f"{layer} {user}: tables.xml has {by_layer[layer].get(user)!r}, not {system}")
            continue
        if layer == "turnout" and not user.startswith("DCC "):
            el = turnout_els.get(r["jmri_name"])
            if el is None or tables.system_name(el) != system:
                bad.append(f"turnout {user}: jmri_name {r['jmri_name']} is not that turnout in tables.xml")
            elif {el.get("sensor1"), el.get("sensor2")} - fb:
                bad.append(f"turnout {user}: feedback {el.get('sensor1')}, {el.get('sensor2')} have no fb rows")
        if layer == "mast":
            mine = {h for h in level_masts.mast_heads(system)}
            listed = {x["system_name"] for x in rows if x["layer"] == "head"}
            if mine - listed:
                bad.append(f"mast {user}: heads {sorted(mine - listed)} have no head rows")
    return bad


def check(band) -> list[str]:
    """Every rule of the four files (the module text), as problems; [] when they hold."""
    bad = []
    try:
        rows = read_rows(DEVICE_MAP, bdm.COLUMNS)
        rr = railroad.Railroad()
        shared = shared_blocks(rows, rr.device_map)
        check_rows(rows, set(shared))
        bad += check_helix(band, load(band))
        load_signal_masts()
        mast_facts()
        bad += check_control_points()
        bad += check_tables(rows, rr, shared)
    except (StagingMapError, railroad.FactsError, mr.MapError) as exc:
        bad.append(str(exc))
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 unless the four files hold their rules")
    args = ap.parse_args(argv)
    if not args.check:
        ap.error("the staging device map is kept by hand; --check is the only mode")
    try:
        lc.plugin()
    except lc.BuildError as exc:
        print(f"SKIPPED staging device map check: {exc}")
        return 1 if os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0
    try:
        with pd.cache_on():
            band, _opts, _core = staging_band()
    except (StagingMapError, lc.BuildError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    bad = check(band)
    for b in bad:
        print(f"staging device map: {b}", file=sys.stderr)
    if not bad:
        print("ok: " + ", ".join(p.name for p in (DEVICE_MAP, CPS, MASTS, SIGNALS)) + " hold their rules")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
