"""masts.csv's staging rows (hartlib.level_masts, its level 1 rows) as staging_device_map's readers take them: the
plugin's drawn masts (load_masts, which staging_device_map.load runs), build_signals.py's masts and signals.json rows
(load_signal_masts, signal_rows) and test_le_mast_parity.py's facts (mast_facts). A mast's kind of slot follows from
its row (mast_kind). staging_device_map re-exports every name here; callers read them from that module.
"""
from __future__ import annotations

import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hartlib import devices, level_masts, paths, railroad, tables  # noqa: E402
from staging_records import MastFact, MastKind, Row, SignalMast, StagingMapError, StagingMast  # noqa: E402

LEVEL = int(railroad.STAGING_LEVEL)     # staging's level, as masts.csv and the device master number it
DEVICE_MAP = devices.MASTER             # the master: its level 1 rows are staging's device map
MASTS = level_masts.PATH                # masts.csv, every level's masts: staging's are its level 1 rows
LIST = level_masts.LIST                 # between the items of a cell (a run, a plan edge's names)
VIRTUAL = "IF$vsm:"                     # a virtual (hidden) mast's system name starts so


def items(cell: str) -> list[str]:
    """The items of a masts.csv list cell (LIST between them), empty ones left out."""
    return [x for x in cell.split(LIST) if x]


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


def mast_kind(r: Mapping[str, Any]) -> MastKind:
    """The kind of slot a masts.csv row stands in: a switch number means a turnout leg, no protected block an
    end bumper, else an anchor."""
    if r["switch"]:
        return "turnout"
    return "end bumper" if not r["protects"] else "anchor"


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
        size, known = tables.mast_icon_size(r["system_name"])
        problems = _mast_problems(r, d, cp_names, heads) + ([] if known else [f": no icon size for {r['system_name']}"])
        bad += [f"line {i}: {name}{p}" for p in problems]
        out.append(_staging_mast(r, size))
    if bad:
        raise StagingMapError(f"{paths.rel(path)}: " + "; ".join(bad))
    return sorted(out, key=lambda m: m["mast"])


def _mast_problems(r: Mapping[str, Any], d: Mapping[str, str], cp_names: set[str],
                   heads: Mapping[str, str]) -> list[str]:
    """What a staging masts.csv row `r` breaks against its device map row `d`, each text to follow the mast's name:
    its system name, its facing block and control point, its heads (`heads`: the device map's {head system name: user
    name}) and its leg."""
    bad: list[str] = []
    if r["system_name"] != d["system_name"] or r["device_system_name"] != d["system_name"]:
        bad.append(f" system name {r['system_name']!r}, the device map's {d['system_name']!r}")
    if (r["cp"] and r["cp"] not in cp_names) or not r["facing"]:
        bad.append(" needs a facing block, and its cp (if any) a staging control point")
    if not r["cp"] and not r["system_name"].startswith(VIRTUAL):
        bad.append(" is a visible mast in no control point")
    pairs = [tuple(h.split("=", 1)) for h in r["head_system_names"].split(LIST) if h]
    if [h for h, *_ in pairs] != level_masts.mast_heads(r["system_name"]) or \
            any(len(p) != 2 or heads.get(p[0]) != p[1] for p in pairs):
        bad.append(f" heads {r['head_system_names']!r} are not its system name's heads as the device map names them")
    if r["leg"] not in ("", *level_masts.LEGS.values()):
        bad.append(f" leg {r['leg']!r}")
    return bad


def _staging_mast(r: Mapping[str, Any], icon: Sequence[int]) -> StagingMast:
    """The plugin's mast of a staging masts.csv row: its blocks, slot kind, hidden and icon size (`icon`); a turnout
    mast's leg when the row gives one, and an end bumper mast may stand at a helix join instead (the three-level
    panel)."""
    entry = StagingMast(mast=r["mast"], facing=r["facing"], protects=items(r["protects"]), kind=mast_kind(r),
                        hidden=r["system_name"].startswith(VIRTUAL),
                        icon=list(icon))
    if r["leg"]:
        entry["leg"] = r["leg"]
    if entry["kind"] == "end bumper":
        entry["or_join"] = True
    return entry


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
        out.append(SignalMast(mast=r["mast"], kind=mast_kind(r), facing=r["facing"], protects=items(r["protects"]),
                              signal=level_masts.signal_name(r["mast"]), toward=r["toward"], run=r["run"].split(LIST),
                              names=items(r["names"]), edge_cm=float(r["edge_cm"]),
                              cm_from_toward=float(r["cm_from_toward"]), dir=r["dir"],
                              signal_kind=level_masts.signal_kind(r), heads=level_masts.head_count(r),
                              schematic_edge=r["schematic_edge"], schematic_toward_node=r["schematic_toward_node"]))
    if bad:
        raise StagingMapError(f"{paths.rel(masts_path)}: " + "; ".join(bad))
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
        fact = MastFact(kind=kind, facing=r["facing"], protects=items(r["protects"]),
                        hidden=r["system_name"].startswith(VIRTUAL))
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
    return sorted(rows, key=_signal_order)


def _signal_order(r: Mapping[str, Any]) -> tuple[int, str]:
    """A signal's place in the plugin's order: its leading number (none last), then its name."""
    n = re.match(r"\d+", r["mast"])
    return (int(n.group()) if n else 10 ** 9, r["mast"])

