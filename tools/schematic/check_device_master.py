#!/usr/bin/env python3
"""The device master's rules on every level, and its rows against tables.xml and the schematic.

    python3 tools/schematic/check_device_master.py --check   # exit 1 unless the device master holds its rules

`make panels` (its device-master step) and tools/check.sh run it. Every rule is one rule for every level of
the device master (staging, main, upper: hartlib.devices); where a rule reads a file only one level has, it is that file's
rule, named for the file, not a level test.

Every row (row_problems), each naming the file, line, level, layer and device:
- its fact columns hold (hartlib.railroad.device_facts);
- its cp is a control point of its own level: stations.csv's desk areas or interlockings.csv's rows of that
  level; or, for a block or occupancy row, the control point of a switch at its block's ends on another level (a
  row's level is the band its track is drawn on: Track 127-221 is drawn on the upper band from main level CP 127);
- (a field device names its user, system and jmri names: hartlib.devices.check_rows holds it on every load);
- only a turnout or block row has a trial_name, and no two rows of one level share one;
- an occupancy row is a field device exactly when its detector is wired.

The rows together (check_rows):
- every block has exactly one occupancy row naming it, on any level; a block named on more than one level is a
  helix block (plan_overrides.json: one JMRI block from its staging switch up the helix), and every
  helix block is so named;
- no two rows of one layer share a user name (but the helix blocks), a system name or a jmri_name (but a virtual LCC
  alias), and no two turnouts a DCC address, on any level;
- every turnout has exactly one LCC alias "DCC Switch <n>": MTT<dcc>, bound by its own system name when it is a
  field device and by its turnout's jmri_name when it is virtual (one internal turnout).
These are hartlib.railroad_invariants.device_row_problems, which `python3 -m hartlib.railroad check` also runs.

Every row against tables.xml (check_tables, hartlib.railroad's tables by user name): the bean its user name names
is the device the row binds (its system name when it is a field device, its jmri_name when it is virtual; a row
with assignment none gives no name and is not looked for, but a block, found by its user name); a block's system
name or jmri_name when the row has one and its layout block's its layout_block (a main or upper block's, which
build_device_map.py copies from block_numbering.csv), its stop as its comment marks a station, and its detector its
occupancy row's; a turnout's jmri_name that turnout, its feedback sensors fb rows', both of them for a field
turnout; a head's user name; a mast's heads its head rows, and its planned heads the head rows' planned devices.
A main or upper row's bean_comment is its bean's comment and its start what the startup LogixNG sets it to
(check_bean_cells).

Against the drawing: the end switches of the main and upper tracks (build_device_map.named_tracks), for the cp rule
above; staging's rows (the owner's, devices_field.csv) are read on their band (staging_device_map.load: staging's
trial names, short tracks, normal legs and masts), and the helix tracks drawn from their staging switches
(staging_device_map.check_helix). A builder's rows are its own --check's (build_device_map.py regenerates the main
and upper rows from the drawing). masts.csv's staging rows are read in their shape (load_signal_masts,
mast_facts). Each part runs on its own, so one that stops leaves the others running. Without
the plugin submodule the drawing part prints SKIPPED and the rest runs, a cp of another level unchecked (exit 1
with SCHEMATIC_REQUIRED=1), as build_device_map.py does.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import le_common as lc  # noqa: E402  the plugin
import mast_rule as mr  # noqa: E402  MapError of the helix tracks file
import publish_draft as pd  # noqa: E402  the plugin cache
import staging_device_map as sdm  # noqa: E402  staging's rows, band and mast files
from hartlib import devices, layer_files, level_devices, level_masts, paths, railroad, railroad_invariants, tables  # noqa: E402,E501

DEVICE_MAP = sdm.DEVICE_MAP
STATIONS = sdm.STATIONS                         # staging's control points: the desk areas of its stations
TRIAL_LAYERS = ("turnout", "block")             # the rows that link to the drawing


class DeviceMasterError(RuntimeError):
    pass


def master_lines(path: Path = DEVICE_MAP) -> list[tuple[int, dict[str, str]]]:
    """(line, row) of every row of the master at `path` that a device map holds (all levels, outside
    devices.OUT_OF_MAPS, and not a level-less device), each a dict of the master's columns. DeviceMasterError when it cannot be read or is empty."""
    try:
        out = [(r.line, dict(r)) for r in devices.load(path)
               if r.role not in devices.OUT_OF_MAPS and not devices.is_unplaced(r)]   # on no level's map yet
    except railroad.FactsError as exc:
        raise DeviceMasterError(str(exc)) from exc
    if not out:
        raise DeviceMasterError(f"{paths.rel(path)}: no device rows")
    return out


def _desk_areas(stations_path: Path) -> list[railroad.DeskArea]:
    try:
        return sdm.desk_areas(stations_path)
    except sdm.StagingMapError as exc:
        raise DeviceMasterError(str(exc)) from exc


def control_points(interlockings: list[railroad.Interlocking], stations_path: Path = STATIONS) -> dict[str, set[str]]:
    """{level: control point names}: interlockings.csv's (every level) and the desk areas of stations.csv, each by its
    level."""
    out = defaultdict(set)
    for i in interlockings:
        out[str(i.level)].add(i.name)
    for a in _desk_areas(stations_path):
        out[str(a.level)].add(a.name)
    return dict(out)


def known_places(interlockings: list[railroad.Interlocking], stations_path: Path = STATIONS) -> set[str]:
    """Every station of stations.csv and control point of interlockings.csv, any level: the places a line block's
    cp may list (build_device_map.line_cp; a helix block joins two levels)."""
    try:
        stations = railroad.read_stations(stations_path)
    except railroad.FactsError as exc:
        raise DeviceMasterError(str(exc)) from exc
    return {i.name for i in interlockings} | {s.name for s in stations}


def _at(n: int, r: dict, where: str) -> str:
    """A master row as a message names it: its file and key, never a line (the master is two merged files)."""
    return f"{where}: {devices.row_text(r)}"


def switch_cps(interlockings: list[railroad.Interlocking], stations_path: Path = STATIONS) -> dict[str, set[str]]:
    """{switch number: the control points it is in, on any level} (interlockings.csv, stations.csv's desk areas)."""
    out = defaultdict(set)
    for i in interlockings:
        for s in i.switches:
            out[s].add(i.name)
    for a in _desk_areas(stations_path):
        for s in a.switches:
            out[s].add(a.name)
    return dict(out)


def block_end_switches(lines: list[tuple[int, dict]], drawing=None) -> dict[str, set[str]]:
    """{block: the switches at its track's ends} of every block row whose trial names are tracks of the drawing
    (`drawing`: (bands, joined, runs), default build_device_map.solve's; its tracks build_device_map.named_tracks,
    each strand keyed by staging_device_map.band_refs, the grammar of every level's trial names). A row's level is the
    band its track is drawn on, so a track drawn on the upper band from a main level switch (Track 127-221) has that
    switch among them."""
    import build_device_map as bdm      # the drawing's tracks and their end switches (needs the plugin)
    bands, joined, runs = bdm.solve()[:3] if drawing is None else drawing
    found = bdm.named_tracks(bands, joined, runs)
    refs = {}
    ends = {}
    try:
        for t in found:
            if t["band"] not in refs:
                refs[t["band"]] = sdm.band_refs(bands, joined, t["band"])
            for sid in t["strands"]:
                ends[refs[t["band"]][sid][0]] = {v for k, v in t["ends"] if k == "sw"}
    except sdm.StagingMapError as exc:
        raise DeviceMasterError(str(exc)) from exc
    out = defaultdict(set)
    for _n, r in lines:
        if r["layer"] != "block":
            continue
        for ph in sdm.split_names(r["trial_name"]):
            if not ph.startswith("Track "):
                continue                    # an OS block's placeholder: its switch, not a track's ends
            try:            # by its piece (staging_device_map.piece_of: a k/n key is the k-th block of its strand)
                got = ends.get(sdm.piece_of(ph)[0])
            except sdm.StagingMapError as exc:
                raise DeviceMasterError(f"block {r['user_name']}: {exc}") from exc
            out[r["user_name"]] |= set(got or ())
    # staging's blocks are named by the one block process over its band (build_device_map.staging_layer): their
    # tracks and parts by block name
    try:
        lay, _bi, _found = bdm.staging_layer(bands, joined, runs)
    except bdm.MapError as exc:
        raise DeviceMasterError(f"staging's blocks: {exc}") from exc
    staging = {r["user_name"] for _n, r in lines if r["level"] == str(sdm.LEVEL) and r["layer"] == "block"}
    tracks = {name: t for name, (t, _h) in lay.tracks.items()} | {name: p["track"] for name, p in lay.parts.items()}
    for name in staging & set(tracks):
        out[name] |= {v for k, v in tracks[name]["ends"] if k == "sw"}
    return dict(out)


def block_end_cps(lines: list[tuple[int, dict]], interlockings: list[railroad.Interlocking], drawing=None,
                  stations_path: Path = STATIONS, ends: dict[str, set[str]] | None = None) -> dict[str, set[str]]:
    """{block: the control points of the switches at its track's ends} (block_end_switches, or `ends` when the caller
    read them already; switch_cps)."""
    ends = block_end_switches(lines, drawing) if ends is None else ends
    cp_of = switch_cps(interlockings, stations_path)
    return {b: {c for s in sws for c in cp_of.get(s, set())} for b, sws in ends.items()}


def line_block_places(ends: dict[str, set[str]]) -> dict[str, set[str]]:
    """{block: the places its cp may list}: the rule's own inputs (build_device_map.line_cp), the places of the
    switches at its ends (`ends`: block_end_switches), of a helix block's two end switches (read_helix_tracks: plan_overrides.json), and
    the stations whose tracks cell names it."""
    import build_device_map as bdm      # read_places, helix_ends: the rule's inputs
    try:
        places = bdm.read_places()
        helix = bdm.helix_ends(bdm.read_helix_tracks())
    except (bdm.MapError, railroad.FactsError) as exc:
        raise DeviceMasterError(str(exc)) from exc
    out = defaultdict(set)
    for b in set(ends) | set(helix) | set(places.tracks):
        for s in ends.get(b, set()) | helix.get(b, set()):
            out[b] |= set(places.of.get(s, ()))
        out[b] |= set(places.tracks.get(b, ()))
    return dict(out)


def row_problems(lines: list[tuple[int, dict]], cps: dict[str, set[str]], where: str = DEVICE_MAP.name,
                 ends_cps: dict[str, set[str]] | None = None, places: set[str] | None = None,
                 line_places: dict[str, set[str]] | None = None) -> list[str]:
    """Each row's own rules (the module text), as problems naming its line, level, layer and user name. `ends_cps`
    (block_end_cps) lets a block or occupancy row name the control point of an end switch of its block on another
    level; None (no drawing read) leaves such a row unchecked, {} refuses it. A line block's cp (devices.LINE_ROLES,
    and its sensor's) is a list each of whose places is in `places` (known_places; None: every level's `cps`) and,
    when `line_places` is given (line_block_places; None: the drawing is not read), one the rule can give it: at an
    end switch of its block, or a station whose tracks name it."""
    bad, trial = [], {}
    places = set().union(*cps.values()) if places is None else places
    for n, r in lines:
        at, level, layer = _at(n, r, where), r["level"], r["layer"]
        if layer not in sdm.LAYERS:
            bad.append(f"{at}: a device map holds no {layer} rows (layers {', '.join(sdm.LAYERS)})")
            continue
        bad += [f"{at}: {p}" for p in railroad.device_facts(r)]
        if r["role"] in devices.LINE_ROLES:
            unknown = [p for p in devices.cp_list(r) if p not in places]
            if unknown:
                bad.append(f"{at}: cp names {', '.join(unknown)}, no station of {STATIONS.name} or control point of "
                           "interlockings.csv")
            elif line_places is not None:
                blocks = [r["user_name"]] if layer == "block" else sdm.occupancy_blocks(r)
                allowed = set().union(*(line_places.get(b, set()) for b in blocks))
                off = [p for p in devices.cp_list(r) if p not in allowed]
                if off:
                    bad.append(f"{at}: cp names {', '.join(off)}, at no end switch of {', '.join(blocks)} and named "
                               f"by no station's tracks in {STATIONS.name}")
        elif r["cp"] and r["cp"] not in cps.get(level, ()):
            blocks = [r["user_name"]] if layer == "block" else sdm.occupancy_blocks(r) if layer == "occupancy" else []
            if ends_cps is None and blocks:
                pass                        # the drawing is not read: check_device_master main says SKIPPED
            elif not any(r["cp"] in (ends_cps or {}).get(b, ()) for b in blocks):
                bad.append(f"{at}: cp {r['cp']!r} is no level {level} control point ({STATIONS.name} desk areas, interlockings.csv)"
                           + (" and no control point of an end switch of its blocks" if blocks else ""))
        phs = sdm.split_names(r["trial_name"])
        if phs and layer not in TRIAL_LAYERS:
            bad.append(f"{at}: a {layer} row has a trial_name")
        for ph in phs:
            if (level, ph) in trial:
                bad.append(f"{at}: trial_name {ph} is {trial[(level, ph)]}'s as well")
            trial.setdefault((level, ph), devices.row_text(r))
        if layer == "occupancy" and (r["assignment"] == "field") != (r["detector"] == "wired"):
            bad.append(f"{at}: assignment {r['assignment']} with detector {r['detector']!r}: a detector is wired "
                       "exactly when the row is a field device")
    return bad


def check_rows(lines: list[tuple[int, dict]], helix_blocks: set[str], where: str = DEVICE_MAP.name) -> list[str]:
    """The rules between rows (hartlib.railroad_invariants.device_row_problems, which the device-map invariant of
    `python3 -m hartlib.railroad check` also runs before tables.xml is built)."""
    return railroad_invariants.device_row_problems(lines, helix_blocks, where, mr.HELIX_SOURCE.name)


def bound_name(r: dict) -> str:
    """The name the tables.xml bean of a row is: its system name for a field device, its jmri_name for a virtual one."""
    return r["system_name"] if r["assignment"] == "field" else r["jmri_name"]


def check_tables(rows: list[dict], rr: railroad.Railroad) -> list[str]:
    """Every row the bean tables.xml holds (the module text), as problems naming the device. The rows of one block
    (a helix block's, one per level) agree on its stop, and a block's comment marks a station exactly when its stop
    is yes. While the Dispatcher stations are parked the master's stop is empty, so a comment that
    marks one is reported."""
    t = rr.tables
    heads = {tables.system_name(h): tables.user_name(h) for h in tables.signal_heads(t.root)}
    blocks = {tables.user_name(b): b for b in tables.blocks(t.root)}
    layout_blocks = {tables.user_name(b): b for b in tables.layout_blocks(t.root)}
    turnout_els = tables.by_any_name(tables.turnouts(t.root))
    by_layer = {"turnout": t.turnouts, "fb": t.sensors, "occupancy": t.sensors, "mast": t.masts}
    serves = {b: r for r in rows if r["layer"] == "occupancy" for b in sdm.occupancy_blocks(r)}
    fb = {r["user_name"] for r in rows if r["layer"] == "fb" and r["assignment"] != "none"}
    head_names = {r["jmri_name"] for r in rows if r["layer"] == "head"}
    head_planned = {r["system_name"] for r in rows if r["layer"] == "head" and r["system_name"]}
    stops = defaultdict(set)
    for r in rows:
        if r["layer"] == "block":
            stops[r["user_name"]].add(r["stop"])
    bad = [f"block {b}: its rows disagree on stop ({', '.join(sorted(s or 'empty' for s in v))})"
           for b, v in sorted(stops.items()) if len(v) > 1]
    for r in rows:
        user, layer, bound = r["user_name"], r["layer"], bound_name(r)
        if layer == "block":
            # the block bean its row names: a field block's system name, a virtual one's jmri_name (a main or upper
            # block's, which build_device_map.py copies from block_numbering.csv)
            b, want = blocks.get(user), bound or r["system_name"]
            if b is None or (want and tables.system_name(b) != want):
                bad.append(f"block {user}: tables.xml has {tables.system_name(b) if b is not None else 'none'}, "
                           f"not {want or 'a block of that name'}")
                continue
            lb = layout_blocks.get(user)
            if r["layout_block"] and (lb is None or tables.system_name(lb) != r["layout_block"]):
                bad.append(f"block {user}: tables.xml's layout block is "
                           f"{tables.system_name(lb) if lb is not None else 'none'}, not {r['layout_block']}")
            stop = "yes" if "yes" in stops[user] else ""       # a block's rows that disagree: reported above
            if stop_token(b.findtext("comment")) != (stop == "yes"):
                bad.append(f"block {user}: stop is {stop or 'empty'}, but its comment in tables.xml "
                           f"{'does not mark' if stop == 'yes' else 'marks'} a station")
            occ = (b.findtext("occupancysensor") or "").strip()
            row = serves.get(user)
            if row is None or occ not in (row["user_name"], row["jmri_name"]):
                bad.append(f"block {user}: its detector in tables.xml is {occ!r}, the device map's "
                           f"{row['user_name'] if row else 'none'}")
            continue
        if layer not in by_layer and layer != "head":
            bad.append(f"{layer} {user}: a device map holds no {layer} rows")
            continue
        if r["assignment"] == "none" or (r["role"] == "lcc_alias" and r["assignment"] == "virtual"):
            continue            # no JMRI name of its own: none gives none, a virtual alias stands on its turnout
        if layer == "head":
            if heads.get(bound) != user:
                bad.append(f"head {bound}: tables.xml names it {heads.get(bound)!r}, not {user!r}")
            continue
        if by_layer[layer].get(user) != bound:
            bad.append(f"{layer} {user}: tables.xml has {by_layer[layer].get(user)!r}, not {bound}")
            continue
        if r["role"] == "turnout":
            el = turnout_els.get(r["jmri_name"])
            if el is None or tables.system_name(el) != bound:
                bad.append(f"turnout {user}: jmri_name {r['jmri_name']} is not that turnout in tables.xml")
                continue
            sensors = {el.get("sensor1"), el.get("sensor2")}
            if sensors - {None} - fb or (r["assignment"] == "field" and None in sensors):
                bad.append(f"turnout {user}: feedback {el.get('sensor1')}, {el.get('sensor2')} have no fb rows")
        if layer == "mast":
            missing = set(level_masts.mast_heads(r["jmri_name"])) - head_names
            if missing:
                bad.append(f"mast {user}: heads {sorted(missing)} have no head rows")
            if r["system_name"] and r["system_name"] != r["jmri_name"]:
                planned = set(level_masts.mast_heads(r["system_name"])) - head_planned
                if planned:
                    bad.append(f"mast {user}: planned heads {sorted(planned)} are no head row's system name")
    return bad


BEAN_TAGS = {"turnout": ("turnout",), "occupancy": ("sensor",), "block": ("block",), "head": ("signalhead",),
             "mast": ("signalmast", "virtualsignalmast")}


def check_bean_cells(rows: list[dict], root) -> list[str]:
    """Each row's bean_comment is its bean's comment in tables `root` (a block's full pass), and the startup LogixNG
    sets each row's start and nothing else (hartlib.level_devices.turnout_states, clear_sensors): the cells
    build_device_map.py writes on the main and upper rows, which the Layout Editor build reads.
    Problems naming the row and what differs."""
    comments: dict[tuple[str, str], str | None] = {}
    for sec in tables.elements(root):
        for el in tables.elements(sec):
            if el.find("comment") is not None:
                comments[(el.tag, tables.user_name(el))] = el.findtext("comment")
    bad = []
    for r in rows:
        if not r["bean_comment"]:
            continue
        got = [comments[(t, r["user_name"])] for t in BEAN_TAGS.get(r["layer"], ()) if (t, r["user_name"]) in comments]
        if not got:
            bad.append(f"{r['layer']} {r['user_name']}: tables.xml has no bean of that name with a comment, for its "
                       f"bean_comment {r['bean_comment']!r}")
        elif len(got) > 1:
            bad.append(f"{r['layer']} {r['user_name']}: tables.xml has {len(got)} beans of that name with a comment "
                       f"({', '.join(BEAN_TAGS[r['layer']])}), not one")
        elif got[0] != r["bean_comment"]:
            bad.append(f"{r['layer']} {r['user_name']}: tables.xml's comment is {got[0]!r}, not its bean_comment "
                       f"{r['bean_comment']!r}")
    try:
        states = {**level_devices.turnout_states(root),
                  **{s: "Inactive" for s in level_devices.clear_sensors(root)}}
    except ValueError as exc:
        return bad + [f"tables.xml's startup LogixNG: {exc}"]
    want = {r["jmri_name"]: level_devices.START_ENUM[r["start"]] for r in rows if r["start"]}
    bad += [f"{n}: tables.xml starts it {states.get(n, 'unset')}, its row {want.get(n, 'unset')}"
            for n in sorted(set(want) | set(states)) if want.get(n) != states.get(n)]
    return bad


def stop_token(comment: str | None) -> bool:
    """Whether a JMRI block comment marks a Dispatcher System station: "stop", or ending "; stop" (the stock
    Dispatcher System's station mark)."""
    c = (comment or "").strip()
    return c == "stop" or c.endswith("; stop")


def check_drawing(band, lines: list[tuple[int, dict]], data: Path) -> list[str]:
    """Staging's rows against the drawing (the module text): the helix tracks drawn from their staging switches,
    each found by the name store's names in the schematic folder `data`. Every row with a level has a writer
    (hartlib.devices.check_generated), whose --check reads it."""
    return sdm.check_helix(band, sdm.load(band), sdm.staging_names(band, data))


ERRORS = (DeviceMasterError, sdm.StagingMapError, railroad.FactsError, mr.MapError, lc.BuildError)


def _part(bad: list[str], fn) -> None:
    """Run one part of the check, its problems (or the error that stopped it) added to `bad`, so a part that stops
    leaves the others running."""
    try:
        bad += fn() or []
    except ERRORS as exc:
        bad.append(str(exc))


def read_mast_files() -> list[str]:
    """masts.csv's staging rows read in their shape (StagingMapError on one that is not)."""
    sdm.load_signal_masts()
    sdm.mast_facts()
    return []


def check(band=None) -> list[str]:
    """Every rule (the module text), as problems; [] when they hold. With `band` None the drawing part is left out,
    and a cp of another level goes unchecked. The drawing part reads the hand-kept staging rows again
    (staging_device_map.load), so it runs only when those rows hold their own rules: a broken row is reported once."""
    try:
        lines = master_lines()
        rr = railroad.Railroad()
        cps = control_points(rr.interlockings)
        places = known_places(rr.interlockings)
    except ERRORS as exc:
        return [str(exc)]
    bad: list[str] = []
    ends = line_places = None
    if band is not None:
        try:
            switches = block_end_switches(lines)
            ends = block_end_cps(lines, rr.interlockings, ends=switches)
            line_places = line_block_places(switches)
        except ERRORS as exc:
            bad.append(f"the main and upper drawing's tracks: {exc}")
            ends, line_places = {}, None
    by_level = defaultdict(list)
    for n, r in lines:
        by_level[r["level"]].append((n, r))
    staging_bad = False
    for level, mine in sorted(by_level.items()):
        got = row_problems(mine, cps, ends_cps=ends, places=places, line_places=line_places)
        staging_bad = staging_bad or (level == str(sdm.LEVEL) and bool(got))
        bad += got
    _part(bad, lambda: check_rows(lines, {h.block for h in rr.helix_tracks.values()}))
    if band is not None and not staging_bad:
        _part(bad, lambda: check_drawing(band, lines, rr.sources.plan_overrides.parent))
    _part(bad, read_mast_files)
    _part(bad, lambda: check_tables([r for _n, r in lines], rr))
    # every row, parts too (master_lines leaves them out): a part's block bean has its comment as well
    _part(bad, lambda: check_bean_cells([dict(r) for r in devices.load(DEVICE_MAP)], rr.tables.root))
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 unless the device master holds its rules")
    args = ap.parse_args(argv)
    if not args.check:
        ap.error("the device master is checked here, never written; --check is the only mode")
    band, skipped = None, None
    try:
        lc.plugin()
    except lc.BuildError as exc:
        skipped = exc
        print(f"SKIPPED the device master's drawing check: {exc}")
    if skipped is None:
        try:
            with pd.cache_on():
                band, _opts, _core = sdm.staging_band()
        except (sdm.StagingMapError, lc.BuildError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    with pd.cache_on():
        bad = check(band)
    # preferences.json's block IDs, each named now that device-map has written the generated names (naming-layers
    # step 5b: the view keeps an ID with no name as it is until then)
    bad += [f"preferences: {m}" for m in layer_files.unnamed_preferences(pd.DATA)]
    for b in bad:
        print(f"device master: {b}", file=sys.stderr)
    if not bad:
        print("ok: " + ", ".join(p.name for p in (DEVICE_MAP, STATIONS, sdm.MASTS)) + " hold their rules"
              + (" (but the drawing)" if skipped else ""))
    if bad:
        return 1
    return 1 if skipped and os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0


if __name__ == "__main__":
    sys.exit(main())
