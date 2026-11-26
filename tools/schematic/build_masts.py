#!/usr/bin/env python3
"""masts.csv, every level's signal masts, the level a column, from the device master's
mast and head rows.

    python3 tools/schematic/build_masts.py           # write masts.csv
    python3 tools/schematic/build_masts.py --check   # exit 1 if it is stale
    python3 tools/schematic/build_masts.py --show    # print staging's masts by the rule, write nothing

When the plugin submodule is not checked out or not at its pinned commit, --check prints SKIPPED and exits 0 (1 with
SCHEMATIC_REQUIRED=1, set in CI), as the other schematic checks do; a write or --show names the fault and exits 2.

Every level's mast and head rows are build_device_map.py's (one writer):
staging's by the rule in device_map_masts.py, main and upper's in
build_device_map.build, both through the one mast process (mast_plan.plan). This script writes masts.csv from those
rows (file_rows, one transform; the file's rules are hartlib.level_masts), with the plan facts
(level_masts.PLAN_FIELDS: where the drawing puts each mast) of staging's masts, which it reads from the same plan
(device_map_masts.staging_masts over the device master's rows). It stops when the master's staging masts are not
the ones the rule places now (run build_device_map.py first). On staging each mast and head row's system_name and
jmri_name are its JMRI name; on main and upper system_name is the planned physical part, so masts.csv's
device_system_name keeps it.

Writes: jmri/layouts/hart/data/schematic/masts.csv.
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_device_map as bdm  # noqa: E402
import device_map_masts as dmm  # noqa: E402  staging's masts by the rule
import mast_rule  # noqa: E402
import publish_draft as pd  # noqa: E402
import staging_device_map as sdm  # noqa: E402
from hartlib import devices, level_masts, places, railroad  # noqa: E402

DATA = pd.DATA
MASTS, DEVICE_MAP = level_masts.PATH, sdm.DEVICE_MAP     # masts.csv, every level; the device master
WRITER = Path(__file__).name
RuleError = dmm.RuleError


def device_files() -> devices.Files:
    """The master (the only device file) as build() uses it: DEVICE_MAP, as it is when it runs (a test may patch it)."""
    return devices.Files.under(DEVICE_MAP.parent)


def csv_text(rows: list[dict], columns, path: Path | None = None) -> str:
    """masts.csv's text of `rows`, the cp cells as place ids by the lists beside `path` (the file it goes to;
    places.lists_beside, the repo's lists when None or when it has none), the lists level_masts.read names them by."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(columns), lineterminator="\n")
    w.writeheader()
    w.writerows(places.with_ids(rows, places.lists_beside(path)))
    return buf.getvalue()


class _Master(NamedTuple):
    """The device master's rows on a level, indexed the ways file_rows looks them up."""
    masts: list[dict]                       # the mast rows, in master order
    heads: dict[tuple[str, str], dict]      # (level, jmri_name) -> head row
    physical: dict[tuple[str, str], dict]   # (level, system_name) -> head row that names a planned physical part
    blocks: dict[tuple[str, str], dict]     # (level, user_name) -> block row (a protected block's role)
    os_of: dict[tuple[str, str], str]       # (level, "os:<switch>") -> the OS block's user name


def _index_master(master: list[dict]) -> _Master:
    """The master's rows on a level (a row on no level, a device a Store added and not yet placed, is left out)."""
    levels = {str(lv) for lv in level_masts.LEVELS}
    rows = [r for r in master if r["level"] in levels]
    return _Master(
        masts=[r for r in rows if r["layer"] == "mast"],
        heads={(r["level"], r["jmri_name"]): r for r in rows if r["layer"] == "head"},
        physical={(r["level"], r["system_name"]): r for r in rows if r["layer"] == "head" and r["system_name"]},
        blocks={(r["level"], r["user_name"]): r for r in rows if r["layer"] == "block"},
        os_of={(r["level"], r["id"]): r["user_name"] for r in rows if r["layer"] == "block" and r["id"].startswith("os:")},
    )


def _base_row(r: dict, plan: Mapping[tuple[int, str], dict]) -> dict:
    """A mast's masts.csv row before protects and head_system_names are known, its leg empty."""
    return dict(level=r["level"], mast=r["user_name"], cp=r["cp"], switch=r["switch"], facing=r["facing"],
                dir=r["dir"], leg="", system_name=r["jmri_name"], device_system_name=r["system_name"],
                **{**dict.fromkeys(level_masts.PLAN_FIELDS, ""), **plan.get((int(r["level"]), r["user_name"]), {})})


def _virtual_problem(r: dict, protects: list[str], where: str) -> str | None:
    """A hidden destination mast at a buffer stop (mast_plan) is its level's VirtualSignalMast, at no switch,
    protecting nothing."""
    jmri = r["jmri_name"]
    if level_masts.virtual_level(jmri) != int(r["level"]) or r["system_name"] != jmri or r["switch"] or protects:
        return (f"{where}: {jmri!r} is a VirtualSignalMast of its level's thousand (its system_name the "
                "same) at a buffer stop: no switch, nothing protected")
    return None


def _anchor_problem(r: dict, protects: list[str], where: str, idx: _Master) -> str | None:
    """A home mast at no switch is an anchor mast (one rule on every level): it protects an OS block of its level,
    else a home signal lost its switch."""
    if r["switch"] or r["role"] != "home":
        return None
    level = r["level"]
    if (level, protects[0]) not in idx.blocks:
        return f"{where} is an anchor mast protecting {protects[0]}, which is no level {level} block row"
    if not devices.is_os(idx.blocks[(level, protects[0])], DEVICE_MAP.name):
        return (f"{where} is a home mast at no switch, so an anchor mast, but protects {protects[0]}, no OS "
                "block: a home signal lost its switch?")
    return None


def _head_names(r: dict, where: str, idx: _Master, bad: list[str]) -> list[str] | None:
    """The heads a SignalHeadSignalMast jmri_name names, each checked against its head row (problems go to `bad`);
    None, with the reason in `bad`, when the name is no such mast or a head has no row."""
    level, jmri = r["level"], r["jmri_name"]
    if not level_masts.SHSM.fullmatch(jmri):
        bad.append(f"{where}: jmri_name {jmri!r} is not a SignalHeadSignalMast over its heads")
        return None
    names = level_masts.mast_heads(jmri)
    missing = [h for h in names if (level, h) not in idx.heads]
    if missing:
        bad.append(f"{where}: heads {missing} have no head row")
        return None
    bad += [f"{where}: {p}" for p in (level_masts.head_problem(h, idx.heads[(level, h)]["user_name"], int(level),
                                                               idx.heads[(level, h)]["assignment"] == "field")
                                      for h in names) if p]
    return names


def _physical_problem(r: dict, names: list[str], where: str, idx: _Master) -> str | None:
    """A planned physical mast (a system_name other than the JMRI name) is the same signal over the same heads."""
    jmri, system = r["jmri_name"], r["system_name"]
    if not system or system == jmri:
        return None
    planned, m = level_masts.SHSM.fullmatch(system), level_masts.SHSM.fullmatch(jmri)
    got = [idx.physical.get((r["level"], h), {}).get("jmri_name") for h in level_masts.mast_heads(system)]
    if not planned or not m or planned.group(1, 2) != m.group(1, 2) or got != names:
        return (f"{where}: system_name {system!r} is not the planned physical mast of "
                f"{jmri!r} (its heads' rows give {got})")
    return None


def _mast_row(r: dict, idx: _Master, plan: Mapping[tuple[int, str], dict], bad: list[str]) -> dict | None:
    """One mast's masts.csv row, its problems added to `bad`; None when a problem leaves no row to write."""
    level, name, switch = r["level"], r["user_name"], r["switch"]
    where = f"{DEVICE_MAP.name}: level {level} mast {name}"
    if not level_masts.MAST_USER.fullmatch(name):
        bad.append(f"{where}: the name is not Mast <number>[L|R][letter] or Mast <A|B><milepost number>")
        return None
    protects = railroad.device_list(r["protects"])
    row = _base_row(r, plan)
    if r["jmri_name"].startswith("IF$vsm:"):
        if problem := _virtual_problem(r, protects, where):
            bad.append(problem)
        return dict(row, protects="", head_system_names="")
    if len(protects) > 1 or not (switch or protects):     # an intermediate: no switch, between two blocks
        bad.append(f"{where}: protects {protects or 'nothing'} and stands at "
                   f"{'Switch ' + switch if switch else 'no switch'}: a home signal is at a switch or protects "
                   "its OS block, an intermediate protects one block")
        return None
    if problem := _anchor_problem(r, protects, where, idx):
        bad.append(problem)
    names = _head_names(r, where, idx, bad)
    if names is None:
        return None
    if problem := _physical_problem(r, names, where, idx):
        bad.append(problem)
    # the OS block of its switch by its id (os:<n>), so an owner's name for it is the one written here
    own = protects[0] if protects else idx.os_of.get((level, f"os:{switch}"), f"OS Switch {switch}")
    return dict(row, protects=own,
                head_system_names=level_masts.LIST.join(f"{h}={idx.heads[(level, h)]['user_name']}" for h in names))


def _assign_legs(out: list[dict], bad: list[str]) -> None:
    """Two masts facing into one block are an A and a B, on the switch's normal and diverging legs: set their leg."""
    pairs: dict[tuple[str, str], list[dict]] = {}
    for r in out:
        if r["protects"]:
            pairs.setdefault((r["facing"], r["protects"]), []).append(r)
    for (facing, protects), group in pairs.items():
        if len(group) == 1:
            continue
        letters = {r["mast"][-1]: r for r in group}
        if len(group) != 2 or set(letters) != set(level_masts.LEGS):
            bad.append(f"masts {[r['mast'] for r in group]} share {facing} into {protects}: only an A and a B mast "
                       "can, on the switch's normal and diverging legs")
            continue
        for letter, r in letters.items():
            r["leg"] = level_masts.LEGS[letter]


def _naming_problems(out: list[dict], plan: Mapping[tuple[int, str], dict]) -> list[str]:
    """A mast named twice, and plan facts for a mast the master has no row for."""
    taken = [r["mast"] for r in out]
    bad = [f"{DEVICE_MAP.name}: mast {x} is named twice" for x in sorted({x for x in taken if taken.count(x) > 1})]
    bad += [f"plan facts for level {lv} mast {x}, which the master has no mast row for"
            for lv, x in sorted(set(plan) - {(int(r["level"]), r["mast"]) for r in out})]
    return bad


def _mast_number(name: str) -> int:
    """The first number in a mast name; MAST_USER, checked before, gives every name one."""
    m = re.search(r"\d+", name)
    if m is None:
        raise RuleError(f"mast {name!r} has no number")
    return int(m.group())


def file_rows(master: list[dict], plan: Mapping[tuple[int, str], dict]) -> list[dict]:
    """masts.csv's rows, every level alike, from the mast and head rows of the device master (`master`, its rows as
    they will be written) and `plan` ({(level, mast): its PLAN_FIELDS}, the plan facts of staging's masts; every
    other row's are empty): one row per mast, in level, number and name order. system_name and head_system_names are
    the JMRI names (the master's jmri_name), device_system_name the master's system_name (the same on staging, the
    planned physical mast on main and upper). A mast protects the OS block of its switch unless its row names one
    (an anchor mast, an intermediate, a double crossover's corner). RuleError, naming the level and mast, on a virtual
    mast out of its level's thousand or at a switch or protecting a block; a visible mast protecting more than one
    block, or none at no switch; a home mast at no switch (an anchor mast, by one rule on every level) that does not
    protect an OS block of its level (a home signal that lost its switch?); a name out of the grammar
    (level_masts.MAST_USER, virtual masts too), a system name that is not a SignalHeadSignalMast over its heads; a head
    with no head row of its level, or neither its level's internal name nor, on a head row whose assignment is field,
    a wired LCOS head (level_masts.head_problem); a planned physical mast whose heads are not the JMRI mast's; two
    masts on one block pair that are not an A and a B (level_masts.LEGS); a mast named twice; and a plan fact for a
    mast the master does not have. A row on no level (a device a Store added, not yet placed: hartlib.devices
    is_unplaced) is on no level's map, and left out."""
    idx = _index_master(master)
    out: list[dict] = []
    bad: list[str] = []
    for r in idx.masts:
        row = _mast_row(r, idx, plan, bad)
        if row is not None:
            out.append(row)
    _assign_legs(out, bad)
    bad += _naming_problems(out, plan)
    if bad:
        raise RuleError("; ".join(bad))
    return sorted(out, key=lambda r: (int(r["level"]), _mast_number(r["mast"]), r["mast"]))


def current(master: list, made: list[dict]) -> None:
    """RuleError when the master's staging mast and head rows are not the rule's (`made`: device_map_masts
    .staging_masts' rows): build_device_map.py writes them, and masts.csv must follow the rows it reads."""
    def key(r):
        return (r["layer"], r["id"], r["user_name"], r["system_name"])
    have = sorted(key(r) for r in master if r["level"] == str(dmm.LEVEL) and r["layer"] in dmm.LAYERS
                  and r["written_by"] == dmm.WRITER)
    want = sorted(key(r) for r in made)
    if have != want:
        diff = sorted(set(have) ^ set(want))[:4]
        raise RuleError(f"{DEVICE_MAP.name}'s staging masts are not the ones the rule places now ({diff}): run "
                        "tools/schematic/build_device_map.py first")


def build(check: bool = False):
    """({masts.csv: text}, the visible masts, the virtual masts by rule). `check`: a run that writes nothing."""
    with pd.cache_on():
        bands, joined, runs, _corners = bdm.solve()
    files = device_files()
    problems = devices.stale(files)       # the master is read below: stop if it or the files generated from it are off
    if problems:
        raise RuleError("; ".join(problems))
    master = list(devices.load(files))
    got = dmm.staging_masts(bands, joined, runs, master, files)
    current(master, got["rows"])
    rows = file_rows(master, got["facts"])
    placed = got["placed"]
    kinds = {m["mast"]: level_masts.signal_kind(m) for m in rows if m["mast"] in {g["mast"] for g in placed}}
    drift = sorted(m["mast"] for m in placed if kinds[m["mast"]] != m["signal_kind"])
    if drift:       # the file holds no kind: it must follow from the row as the rule gives it
        raise RuleError(f"the rule's signal kind of {drift} is not the one their heads give")
    gen = [m for m in placed if m["role"] != "hidden"]
    vgen = [m for m in placed if m["role"] == "hidden"]
    return {MASTS: csv_text(rows, level_masts.FIELDS, MASTS)}, gen, vgen


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="exit 1 if a file is stale")
    g.add_argument("--show", action="store_true", help="print the masts and write nothing")
    args = ap.parse_args(argv)
    try:
        sdm.lc.plugin()
    except sdm.lc.BuildError as exc:
        if args.check:
            print(f"SKIPPED masts check: {exc}")
            return 1 if os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0
        print(f"{WRITER}: {exc}", file=sys.stderr)
        return 2
    try:
        want, gen, vgen = build(check=args.check or args.show)
    except (sdm.StagingMapError, sdm.lc.BuildError, mast_rule.MapError, railroad.FactsError) as exc:
        # a RuleError is a MapError, a DevicesError a FactsError
        print(f"{WRITER}: {exc}", file=sys.stderr)
        return 2
    if args.show:
        for m in gen + vgen:
            print(f"{m['mast']:10} {m['kind']:16} {m['heads']}h  {m['facing']:22} -> {m['protects']:16} "
                  f"{'switch ' + m['switch'] if m['switch'] else 'anchor':10} {m['dir']}"
                  + (f"  MP {m['milepost']}" if "milepost" in m else ""))
        return 0
    stale = [p for p, text in want.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
    if args.check:
        for p in stale:
            print(devices.stale_message(p, device_files(), f"tools/schematic/{WRITER}"), file=sys.stderr)
        return 1 if stale else 0
    for p in stale:
        p.write_text(want[p], encoding="utf-8")
        print(f"wrote {p.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
