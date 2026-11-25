#!/usr/bin/env python3
"""Check that every loco the rosters and the train list name is in the loco master (ADR-039, lane L4d).

``ops/hart-ops/data/locos.csv`` is the loco master. Its copies are the two Operations Pro engine rosters
(the live one under ``jmri/layouts/hart/operations/`` and the snapshot in ``ops/hart-ops/data/``) and the
``engine`` column of ``cats/data/hart_trains.csv``. This check reads them and fails when one names a loco
the master lacks:

- each roster ``id`` must be a master row's Operations Pro id (``locos.ops_id``: road name and number with
  no space);
- each train ``engine``, a road number, must be the road number of exactly one master row;
- each master ``roster_id`` must be its key, road name and road number, formatted by ``locos.loco_roster_id``
  (one space); the sidecar keys the master on the pair.

A gap the owner has yet to decide is in ``REPORTED``: it is printed on every run and does not fail. An entry
there that is no longer a gap fails, so the list cannot go stale. It writes nothing; the rosters are the
Pi's, and phase 2 of ADR-039 reconciles them.

    python3 tools/ops/check_locos.py
"""
from __future__ import annotations

import csv
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ops/hart-ops/card_pipeline"))
import locos  # noqa: E402  (loco_roster_id, ops_id: the one definition of the two id forms)

MASTER = ROOT / "ops/hart-ops/data/locos.csv"
ROSTERS = (
    ROOT / "jmri/layouts/hart/operations/OperationsEngineRoster.xml",
    ROOT / "ops/hart-ops/data/OperationsEngineRoster.xml",
)
TRAINS = ROOT / "cats/data/hart_trains.csv"

# (file, value) -> why it is a known gap. Owner questions of lane L4d; remove an entry when it is settled.
REPORTED: dict[tuple[str, str], str] = {
    ("ops/hart-ops/data/OperationsEngineRoster.xml", "CWRY2091"):
        "the owner chose POHC 2091 (2026-11-25); the snapshot roster keeps CWRY until phase 2 reconciles it",
}


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_master(path: Path = MASTER) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def roster_ids(path: Path) -> list[str]:
    return [e.get("id", "") for e in ET.parse(path).getroot().iter("engine")]


def train_engines(path: Path = TRAINS) -> list[str]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [r["engine"].strip() for r in csv.DictReader(fh) if r.get("engine", "").strip()]


def gaps(rows: list[dict], rosters: dict[str, list[str]], trains: dict[str, list[str]]) -> list[tuple[str, str, str]]:
    """Every (file, value, problem) where a copy names a loco the master lacks, or a master id is malformed."""
    found = []
    for r in rows:
        want = locos.loco_roster_id(r["road_name"], r["road_number"])
        if r["roster_id"] != want:
            found.append((rel(MASTER), r["roster_id"], f"roster_id should be {want!r}"))
    ops_ids: dict[str, str] = {}
    for r in rows:
        oid = locos.ops_id(r["road_name"], r["road_number"])
        if oid in ops_ids:
            found.append((rel(MASTER), r["roster_id"], f"the same Operations Pro id {oid!r} as {ops_ids[oid]}"))
        ops_ids.setdefault(oid, r["roster_id"])
    for name, ids in rosters.items():
        for eid in ids:
            if eid not in ops_ids:
                found.append((name, eid, "no locos.csv row has this Operations Pro id"))
    by_number: dict[str, list[str]] = {}
    for r in rows:
        by_number.setdefault(r["road_number"], []).append(r["roster_id"])
    for name, engines in trains.items():
        for eng in dict.fromkeys(engines):
            hits = by_number.get(eng, [])
            if len(hits) != 1:
                why = "no locos.csv row has this road number" if not hits else f"road number of {', '.join(hits)}"
                found.append((name, eng, why))
    return found


def main() -> int:
    try:
        rows = read_master()
        found = gaps(rows, {rel(p): roster_ids(p) for p in ROSTERS}, {rel(TRAINS): train_engines()})
    except (OSError, ET.ParseError, KeyError) as exc:
        print(f"FAIL     check_locos: a file it reads is missing or unreadable: {exc}")
        return 1
    failed = reported = 0
    for file, value, problem in found:
        if (file, value) in REPORTED:
            print(f"REPORTED {file}: {value}: {problem} ({REPORTED[(file, value)]})")
            reported += 1
        else:
            print(f"FAIL     {file}: {value}: {problem}")
            failed += 1
    for file, value in sorted(set(REPORTED) - {(f, v) for f, v, _ in found}):
        print(f"FAIL     {file}: {value} is in REPORTED but is no longer a gap; remove it from check_locos.py")
        failed += 1
    print(f"check_locos: {len(rows)} locos; {failed} problem(s), {reported} reported")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
