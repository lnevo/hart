#!/usr/bin/env python3
"""masts.csv, every level's signal masts, the level a column (owner, 2026-11-18/19/20/21), from the device master's
mast and head rows.

    python3 tools/schematic/build_masts.py           # write masts.csv
    python3 tools/schematic/build_masts.py --check   # exit 1 if it is stale
    python3 tools/schematic/build_masts.py --show    # print staging's masts by the rule, write nothing

When the plugin submodule is not checked out or not at its pinned commit, --check prints SKIPPED and exits 0 (1 with
SCHEMATIC_REQUIRED=1, set in CI), as the other schematic checks do; a write or --show names the fault and exits 2.

Every level's mast and head rows are build_device_map.py's (one writer, naming-layers step 12, builder merge step 6):
staging's by the rule in device_map_masts.py (part 1 of this script until then), main and upper's in
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
from pathlib import Path

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


def file_rows(master: list[dict], plan: dict) -> list[dict]:
    """masts.csv's rows, every level alike, from the mast and head rows of the device master (`master`, its rows as
    they will be written) and `plan` ({(level, mast): its PLAN_FIELDS}, the plan facts of staging's masts; every
    other row's are empty): one row per mast, in level, number and name order. system_name and head_system_names are
    the JMRI names (the master's jmri_name), device_system_name the master's system_name (the same on staging, the
    planned physical mast on main and upper). A mast protects the OS block of its switch unless its row names one
    (an anchor mast, an intermediate, a double crossover's corner). RuleError, naming the level and mast, on a virtual
    mast out of its level's thousand or at a switch or protecting a block; a visible mast protecting more than one
    block, or none at no switch; a home mast at no switch (an anchor mast, by one rule on every level: owner,
    2026-11-23) that does not protect an OS block of its level (a home signal that lost its switch?); a name out of the grammar
    (level_masts.MAST_USER, virtual masts too), a system name that is not a SignalHeadSignalMast over its heads; a head
    with no head row of its level, or neither its level's internal name nor, on a head row whose assignment is field,
    a wired LCOS head (level_masts.head_problem); a planned physical mast whose heads are not the JMRI mast's; two
    masts on one block pair that are not an A and a B (level_masts.LEGS); a mast named twice; and a plan fact for a
    mast the master does not have. A row on no level (a device a Store added, not yet placed: hartlib.devices
    is_unplaced) is on no level's map, and left out."""
    levels = {str(lv) for lv in level_masts.LEVELS}
    master = [r for r in master if r["level"] in levels]
    heads = {(r["level"], r["jmri_name"]): r for r in master if r["layer"] == "head"}
    physical = {(r["level"], r["system_name"]): r for r in master if r["layer"] == "head" and r["system_name"]}
    blocks = {(r["level"], r["user_name"]): r for r in master if r["layer"] == "block"}   # a protected block's role
    os_of = {(r["level"], r["id"]): r["user_name"] for r in master if r["layer"] == "block" and r["id"].startswith("os:")}

    out, bad = [], []
    for r in (r for r in master if r["layer"] == "mast"):
        level, name, jmri, switch = r["level"], r["user_name"], r["jmri_name"], r["switch"]
        where = f"{DEVICE_MAP.name}: level {level} mast {name}"
        if not level_masts.MAST_USER.fullmatch(name):
            bad.append(f"{where}: the name is not Mast <number>[L|R][letter] or Mast <A|B><milepost number>")
            continue
        protects = railroad.device_list(r["protects"])
        row = dict(level=level, mast=name, cp=r["cp"], switch=switch, facing=r["facing"], dir=r["dir"], leg="",
                   system_name=jmri, device_system_name=r["system_name"],
                   **{**dict.fromkeys(level_masts.PLAN_FIELDS, ""), **plan.get((int(level), name), {})})
        if jmri.startswith("IF$vsm:"):          # a hidden destination mast at a buffer stop (mast_plan)
            if level_masts.virtual_level(jmri) != int(level) or r["system_name"] != jmri or switch or protects:
                bad.append(f"{where}: {jmri!r} is a VirtualSignalMast of its level's thousand (its system_name the "
                           "same) at a buffer stop: no switch, nothing protected")
            out.append(dict(row, protects="", head_system_names=""))
            continue
        if len(protects) > 1 or not (switch or protects):     # an intermediate: no switch, between two blocks
            bad.append(f"{where}: protects {protects or 'nothing'} and stands at "
                       f"{'Switch ' + switch if switch else 'no switch'}: a home signal is at a switch or protects "
                       "its OS block, an intermediate protects one block")
            continue
        if not switch and r["role"] == "home" and (level, protects[0]) not in blocks:
            bad.append(f"{where} is an anchor mast protecting {protects[0]}, which is no level {level} block row")
        elif not switch and r["role"] == "home" and not devices.is_os(blocks[(level, protects[0])], DEVICE_MAP.name):
            bad.append(f"{where} is a home mast at no switch, so an anchor mast, but protects {protects[0]}, no OS "
                       "block: a home signal lost its switch?")
        m = level_masts.SHSM.fullmatch(jmri)
        if not m:
            bad.append(f"{where}: jmri_name {jmri!r} is not a SignalHeadSignalMast over its heads")
            continue
        names = level_masts.mast_heads(jmri)
        missing = [h for h in names if (level, h) not in heads]
        if missing:
            bad.append(f"{where}: heads {missing} have no head row")
            continue
        bad += [f"{where}: {p}" for p in (level_masts.head_problem(h, heads[(level, h)]["user_name"], int(level),
                                                                   heads[(level, h)]["assignment"] == "field")
                                          for h in names) if p]
        if r["system_name"] and r["system_name"] != jmri:      # the planned physical mast: over the same heads
            planned = level_masts.SHSM.fullmatch(r["system_name"])
            got = [physical.get((level, h), {}).get("jmri_name") for h in level_masts.mast_heads(r["system_name"])]
            if not planned or planned.group(1, 2) != m.group(1, 2) or got != names:
                bad.append(f"{where}: system_name {r['system_name']!r} is not the planned physical mast of "
                           f"{jmri!r} (its heads' rows give {got})")
        # the OS block of its switch by its id (os:<n>), so an owner's name for it is the one written here
        own = protects[0] if protects else os_of.get((level, f"os:{switch}"), f"OS Switch {switch}")
        out.append(dict(row, protects=own,
                        head_system_names=level_masts.LIST.join(f"{h}={heads[(level, h)]['user_name']}"
                                                                for h in names)))
    pairs = {}
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
    taken = [r["mast"] for r in out]
    bad += [f"{DEVICE_MAP.name}: mast {x} is named twice" for x in sorted({x for x in taken if taken.count(x) > 1})]
    bad += [f"plan facts for level {lv} mast {x}, which the master has no mast row for"
            for lv, x in sorted(set(plan) - {(int(r["level"]), r["mast"]) for r in out})]
    if bad:
        raise RuleError("; ".join(bad))
    return sorted(out, key=lambda r: (int(r["level"]), int(re.search(r"\d+", r["mast"]).group()), r["mast"]))


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
