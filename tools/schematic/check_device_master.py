#!/usr/bin/env python3
"""The device master's rules on every level, and its rows against tables.xml and the schematic.

    python3 tools/schematic/check_device_master.py --check   # exit 1 unless devices.csv holds its rules

`make panels` (its device-master step) and tools/check.sh run it. Every rule is one rule for every level of
devices.csv (staging, main, upper: hartlib.devices); where a rule reads a file only one level has, it is that file's
rule, named for the file, not a level test.

Every row (row_problems), each naming the file, line, level, layer and device:
- its fact columns hold (hartlib.railroad.device_facts);
- its cp is a control point of its own level: control_points_staging.csv's or interlockings.csv's rows of that
  level (KNOWN_CP lists the exceptions already reported to the owner);
- only a turnout or block row has a trial_name, and no two rows of one level share one;
- a row kept by hand (no written_by) is a field device: the railroad's own, in JMRI as it is;
- an occupancy row is a field device exactly when its detector is wired.

The rows together (check_rows):
- every block has exactly one occupancy row naming it, on any level; a block named on more than one level is a
  helix block (helix_tracks.csv: one JMRI block from its staging switch up the helix, owner 2026-11-20), and every
  helix block is so named;
- no two rows of one layer share a system name (on any level), nor a user name (but the helix blocks);
- an LCC alias "DCC Switch <n>" is MTT<dcc> of the turnout of its level with that DCC address, bound by its own
  system name when it is a field device and by its turnout's jmri_name when it is virtual (one internal turnout).

Every row against tables.xml (check_tables, hartlib.railroad's tables by user name): the bean its user name names
is the device the row binds (its system name when it is a field device, its jmri_name when it is virtual; a row
with assignment none gives no name and is not looked for, but a block, whose bean the Layout Editor build
numbers); a block's system name when the row has one, its stop as its comment marks a station, and its detector its
occupancy row's; a turnout's jmri_name that turnout, its feedback sensors fb rows', both of them for a field
turnout; a head's user name; a mast's heads its head rows, and its planned heads the head rows' planned devices.

Against the drawing: the rows kept by hand are read on their level's band (staging_device_map.load: staging's
trial names, short tracks, normal legs and masts), and the helix tracks drawn from their staging switches
(staging_device_map.check_helix). A builder's rows are its own --check's (build_device_map.py regenerates the main
and upper rows from the drawing). staging_masts.csv and staging_signals.csv are read in their shape
(load_signal_masts, mast_facts). Without the plugin submodule the drawing part prints SKIPPED and the rest runs
(exit 1 with SCHEMATIC_REQUIRED=1), as build_device_map.py does.
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
from hartlib import devices, level_masts, paths, railroad, tables  # noqa: E402

DEVICE_MAP = sdm.DEVICE_MAP
CPS = sdm.CPS                                   # staging's control points (their level column)
TRIAL_LAYERS = ("turnout", "block")             # the rows that link to the drawing
# Rows that name a control point of another level: (row level, cp) -> why it is left. Each was reported to the owner;
# an entry no row uses any more fails, so the list stays honest (as hartlib.railroad.KNOWN).
KNOWN_CP: dict[tuple[str, str], str] = {
    ("3", "CP 127"): "the upper blocks at the helix top (Track 127-131 2, Track 127-221, Track Helix Inner and their "
                     "detectors) are in CP 127, a main level interlocking (build_device_map.py; reported 2026-11-20)",
}
# Blocks whose rows disagree on stop -> why it is left (reported to the owner; a stale entry fails, as KNOWN_CP).
KNOWN_STOP: dict[str, str] = {
    b: "the staging row marks the helix block a Dispatcher System station, as its tables.xml comment does; the main or "
       "upper row (build_device_map.py, which writes no stop) leaves it empty (reported 2026-11-20)"
    for b in ("Track Helix Inner", "Track Helix Outer")
}


class DeviceMasterError(RuntimeError):
    pass


def master_lines(path: Path = DEVICE_MAP) -> list[tuple[int, dict[str, str]]]:
    """(line, row) of every row of the master at `path` that a device map holds (all levels, outside
    devices.OUT_OF_MAPS), each a dict of the master's columns. DeviceMasterError when it cannot be read or is empty."""
    try:
        out = [(n, dict(r)) for n, r in enumerate(devices.load(path), 2) if r["role"] not in devices.OUT_OF_MAPS]
    except railroad.FactsError as exc:
        raise DeviceMasterError(str(exc)) from None
    if not out:
        raise DeviceMasterError(f"{paths.rel(path)}: no device rows")
    return out


def control_points(interlockings: list[railroad.Interlocking], cps_path: Path = CPS) -> dict[str, set[str]]:
    """{level: control point names}: interlockings.csv's (every level) and control_points_staging.csv's, each by its
    level column."""
    out = defaultdict(set)
    for i in interlockings:
        out[str(i.level)].add(i.name)
    try:
        rows = sdm.read_rows(cps_path, sdm.CP_COLUMNS)
    except sdm.StagingMapError as exc:
        raise DeviceMasterError(str(exc)) from None
    for i, r in enumerate(rows, 2):
        if r["level"] not in devices.LEVELS or not r["cp_name"]:
            raise DeviceMasterError(f"{paths.rel(cps_path)} line {i}: level {r['level']!r} is one of "
                                    f"{', '.join(devices.LEVELS)} and cp_name {r['cp_name']!r} is given")
        out[r["level"]].add(r["cp_name"])
    return dict(out)


def _at(n: int, r: dict, where: str) -> str:
    return f"{where} line {n} (level {r['level']} {r['layer']} {r['user_name']})"


def row_problems(lines: list[tuple[int, dict]], cps: dict[str, set[str]], where: str = DEVICE_MAP.name,
                 known_cp: dict | None = None) -> list[str]:
    """Each row's own rules (the module text), as problems naming its line, level, layer and user name. `known_cp`
    (default KNOWN_CP) lists the (level, cp) pairs let through; one that no row uses is a problem too."""
    known_cp = KNOWN_CP if known_cp is None else known_cp
    bad, trial, used = [], {}, set()
    for n, r in lines:
        at, level, layer = _at(n, r, where), r["level"], r["layer"]
        if layer not in sdm.LAYERS:
            bad.append(f"{at}: a device map holds no {layer} rows (layers {', '.join(sdm.LAYERS)})")
            continue
        bad += [f"{at}: {p}" for p in railroad.device_facts(r)]
        if r["cp"] and r["cp"] not in cps.get(level, ()):
            if (level, r["cp"]) in known_cp:
                used.add((level, r["cp"]))
            else:
                bad.append(f"{at}: cp {r['cp']!r} is no level {level} control point ({CPS.name}, interlockings.csv)")
        phs = sdm.split_names(r["trial_name"])
        if phs and layer not in TRIAL_LAYERS:
            bad.append(f"{at}: a {layer} row has a trial_name")
        for ph in phs:
            if (level, ph) in trial:
                bad.append(f"{at}: trial_name {ph} is line {trial[(level, ph)]}'s as well")
            trial.setdefault((level, ph), n)
        if not r["written_by"] and r["assignment"] != "field":
            bad.append(f"{at}: kept by hand, so a field device, not assignment {r['assignment']}")
        if layer == "occupancy" and (r["assignment"] == "field") != (r["detector"] == "wired"):
            bad.append(f"{at}: assignment {r['assignment']} with detector {r['detector']!r}: a detector is wired "
                       "exactly when the row is a field device")
    levels = {r["level"] for _n, r in lines}
    bad += [f"KNOWN_CP entry no longer happens; remove it: level {lv} {cp}" for lv, cp in sorted(set(known_cp) - used)
            if lv in levels]                # a reader of some levels' rows (staging_device_map.load) leaves the rest
    return bad


def check_rows(lines: list[tuple[int, dict]], helix_blocks: set[str], where: str = DEVICE_MAP.name) -> list[str]:
    """The rules between rows (the module text), as problems naming the rows."""
    bad = []
    block_levels = defaultdict(list)
    for n, r in lines:
        if r["layer"] == "block":
            block_levels[r["user_name"]].append((n, r))
    shared = {b for b, rs in block_levels.items() if len({r["level"] for _n, r in rs}) > 1}
    if shared != helix_blocks:
        bad.append(f"{where}: blocks named on more than one level: {sorted(shared) or 'none'}; exactly the helix "
                   f"blocks of {mr.HELIX_TRACKS.name} ({sorted(helix_blocks)}) are")
    served = defaultdict(list)
    for n, r in lines:
        if r["layer"] == "occupancy":
            for b in sdm.occupancy_blocks(r):
                served[b].append(n)
    for b in sorted(set(block_levels) | set(served)):
        if b not in block_levels:
            bad.append(f"{where} line(s) {', '.join(map(str, served[b]))}: occupancy of {b}, which is no block row")
        elif len(served[b]) != 1:
            lines_ = ", ".join(str(n) for n, _r in block_levels[b])
            bad.append(f"{where} line {lines_}: block {b} has {len(served[b])} occupancy rows naming it "
                       f"({', '.join(map(str, served[b])) or 'none'}), not one")
    for col in ("system_name", "user_name", "dcc"):
        seen: dict[tuple[str, str], int] = {}
        for n, r in lines:
            v = r[col]
            if not v or (col == "user_name" and r["layer"] == "block" and v in shared) or \
                    (col == "dcc" and r["role"] != "turnout"):      # an LCC alias carries its turnout's address
                continue
            # one physical device is one row: a turnout, sensor or head's system name is no other such row's
            kind = "hardware" if col == "system_name" and r["layer"] in railroad.UNIQUE_HARDWARE else r["layer"]
            key = (kind, v)
            if key in seen:
                bad.append(f"{_at(n, r, where)}: {col} {v!r} is line {seen[key]}'s as well")
            seen.setdefault(key, n)
    turnouts = {(r["level"], r["dcc"]): r for _n, r in lines if r["role"] == "turnout" and r["dcc"]}
    for n, r in lines:
        if r["role"] != "lcc_alias":
            continue
        t = turnouts.get((r["level"], r["dcc"]))
        if t is None:
            bad.append(f"{_at(n, r, where)}: no level {r['level']} turnout has its DCC address {r['dcc'] or 'none'}")
            continue
        field = r["assignment"] == "field"
        want = (f"DCC {t['user_name']}", f"MTT{r['dcc']}", f"MTT{r['dcc']}" if field else t["jmri_name"])
        if (r["user_name"], r["system_name"], r["jmri_name"]) != want:
            bad.append(f"{_at(n, r, where)}: the LCC alias of {t['user_name']} (DCC {r['dcc']}) is user, system and "
                       f"jmri name {', '.join(want)} ({'a field device' if field else 'on its turnout'}), not "
                       f"{r['user_name']}, {r['system_name']}, {r['jmri_name']}")
    return bad


def bound_name(r: dict) -> str:
    """The name the tables.xml bean of a row is: its system name for a field device, its jmri_name for a virtual one."""
    return r["system_name"] if r["assignment"] == "field" else r["jmri_name"]


def check_tables(rows: list[dict], rr: railroad.Railroad, known_stop: dict | None = None) -> list[str]:
    """Every row the bean tables.xml holds (the module text), as problems naming the device. The rows of one block
    (a helix block's, one per level) agree on its stop, but those `known_stop` (default KNOWN_STOP) lists, which are
    a station when any of them says so; an entry whose rows agree is a problem too."""
    known_stop = KNOWN_STOP if known_stop is None else known_stop
    t = rr.tables
    heads = {tables.system_name(h): tables.user_name(h) for h in tables.signal_heads(t.root)}
    blocks = {tables.user_name(b): b for b in tables.blocks(t.root)}
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
           for b, v in sorted(stops.items()) if len(v) > 1 and b not in known_stop]
    bad += [f"KNOWN_STOP entry no longer happens; remove it: {b}" for b in sorted(known_stop)
            if len(stops.get(b, ())) < 2]
    for r in rows:
        user, layer, bound = r["user_name"], r["layer"], bound_name(r)
        if layer == "block":
            b = blocks.get(user)
            if b is None or (r["system_name"] and tables.system_name(b) != r["system_name"]):
                bad.append(f"block {user}: tables.xml has {tables.system_name(b) if b is not None else 'none'}, "
                           f"not {r['system_name'] or 'a block of that name'}")
                continue
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


def stop_token(comment: str | None) -> bool:
    """Whether a JMRI block comment marks a Dispatcher System station: "stop", or ending "; stop" (the stock
    Dispatcher System's station mark)."""
    c = (comment or "").strip()
    return c == "stop" or c.endswith("; stop")


def check_drawing(band, lines: list[tuple[int, dict]]) -> list[str]:
    """The hand-kept rows against the drawing (the module text): only staging_device_map.load reads hand-kept rows,
    so a hand-kept row of another level is a problem, not a row left unread."""
    other = [(n, r) for n, r in lines if not r["written_by"] and r["level"] != str(sdm.LEVEL)]
    bad = [f"{_at(n, r, DEVICE_MAP.name)}: kept by hand, but only staging's hand-kept rows (level {sdm.LEVEL}) are "
           "read against the drawing; give it a writer, whose --check reads it" for n, r in other]
    bad += sdm.check_helix(band, sdm.load(band))
    return bad


def check(band=None) -> list[str]:
    """Every rule (the module text), as problems; [] when they hold. With `band` None the drawing part is left out."""
    bad = []
    try:
        lines = master_lines()
        rr = railroad.Railroad()
        bad += row_problems(lines, control_points(rr.interlockings))
        bad += check_rows(lines, {h.block for h in rr.helix_tracks.values()})
        if band is not None:
            bad += check_drawing(band, lines)
        sdm.load_signal_masts()
        sdm.mast_facts()
        bad += check_tables([r for _n, r in lines], rr)
    except (DeviceMasterError, sdm.StagingMapError, railroad.FactsError, mr.MapError) as exc:
        bad.append(str(exc))
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 unless devices.csv holds its rules")
    args = ap.parse_args(argv)
    if not args.check:
        ap.error("devices.csv is checked here, never written; --check is the only mode")
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
    bad = check(band)
    for b in bad:
        print(f"device master: {b}", file=sys.stderr)
    if not bad:
        print("ok: " + ", ".join(p.name for p in (DEVICE_MAP, CPS, sdm.MASTS, sdm.SIGNALS)) + " hold their rules"
              + (" (but the drawing)" if skipped else ""))
    if bad:
        return 1
    return 1 if skipped and os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0


if __name__ == "__main__":
    sys.exit(main())
