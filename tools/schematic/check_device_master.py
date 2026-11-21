#!/usr/bin/env python3
"""The device master's rules against tables.xml and the schematic.

    python3 tools/schematic/check_device_master.py --check   # exit 1 unless the files hold their rules

`make panels` (its device-master step) and tools/check.sh run it: the level 1 rows of devices.csv, the staging
masts and the control points in their shape (staging_device_map.load, load_signal_masts, mast_facts, check_rows),
and every device the same bean in tables.xml (check_tables: system and user names, a turnout's feedback sensors, a
block's detector, a mast's heads). It prints SKIPPED and exits 0 when the plugin submodule is not checked out (1 with
SCHEMATIC_REQUIRED=1), as build_device_map.py does.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import le_common as lc  # noqa: E402  the plugin
import mast_rule as mr  # noqa: E402  the helix tracks (helix_tracks.csv)
import publish_draft as pd  # noqa: E402  the plugin cache
import staging_device_map as sdm  # noqa: E402  staging's rows, band and mast files
from hartlib import level_devices, level_masts, railroad, tables  # noqa: E402

StagingMapError = sdm.StagingMapError


def stop_token(comment: str) -> bool:
    """Whether a JMRI block comment marks a Dispatcher System station: "stop", or ending "; stop" (the stock
    Dispatcher System's station mark)."""
    c = (comment or "").strip()
    return c == "stop" or c.endswith("; stop")


def shared_blocks(rows: list[dict], level_map: railroad.DeviceMap, helix: dict | None = None) -> dict:
    """{block: its main or upper occupancy row} of the staging blocks the main and upper rows also name: the helix
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


def check_rows(rows: list[dict], shared=frozenset()) -> None:
    """Every block has exactly one occupancy row naming it, but a helix block (`shared`: shared_blocks), whose
    detector is the main and upper device map's; no two rows of one layer share a system name, a jmri_name
    or a user name (a turnout's LCC alias "DCC Switch <n>" is a turnout of its own, MTT<dcc>, with its own names);
    every row is a whole field device."""
    bad = []
    blocks = [r["user_name"] for r in rows if r["layer"] == "block" and r["user_name"] not in shared]
    served = [b for r in rows if r["layer"] == "occupancy" for b in sdm.occupancy_blocks(r)]
    if sorted(blocks) != sorted(served):
        bad.append(f"blocks and occupancy rows differ: {sorted(set(blocks) ^ set(served))} "
                   f"(or one is served twice)")
    for layer in sdm.LAYERS:
        mine = [r for r in rows if r["layer"] == layer]
        for col in ("system_name", "jmri_name", "user_name"):
            vals = [r[col] for r in mine]
            if not all(vals) or len(set(vals)) != len(vals):
                bad.append(f"{layer} rows: a {col} is empty or given twice")
    if bad:
        raise StagingMapError("staging device map: " + "; ".join(bad))


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
    serves = {b: r for r in rows if r["layer"] == "occupancy" for b in sdm.occupancy_blocks(r)}
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
        if r["role"] == "turnout":
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
        rows = sdm.read_device_rows()
        rr = railroad.Railroad()
        shared = shared_blocks(rows, rr.device_map)
        check_rows(rows, set(shared))
        bad += sdm.check_helix(band, sdm.load(band))
        sdm.load_signal_masts()
        sdm.mast_facts()
        bad += check_tables(rows, rr, shared)
    except (StagingMapError, railroad.FactsError, mr.MapError) as exc:
        bad.append(str(exc))
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 unless the files hold their rules")
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
            band, _opts, _core = sdm.staging_band()
    except (StagingMapError, lc.BuildError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    bad = check(band)
    for b in bad:
        print(f"staging device map: {b}", file=sys.stderr)
    if not bad:
        print("ok: " + ", ".join(p.name for p in (sdm.DEVICE_MAP, sdm.CPS, sdm.MASTS, sdm.SIGNALS)) +
              " hold their rules")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
