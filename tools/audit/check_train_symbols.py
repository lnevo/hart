#!/usr/bin/env python3
"""Every train named outside the train master is one of its trains (ADR-039, key train_symbol).

    python3 tools/audit/check_train_symbols.py     tools/check.sh runs it (job train-symbols)

It reads ops/hart-ops/data/trains.csv and checks three copies against it:

- ops/hart-ops/data/crew.json, the crew master (www/data/crew.json is built from it): the code of each crew job
  (kind "crew") is a train_symbol. The yardmaster and dispatcher jobs are not trains; their codes are publication
  numbers (YM-01, DS-01), so they are left out.
- jmri/layouts/hart/operations/OperationsTrainRoster.xml: each Operations Pro train name is a train_symbol, or the
  opspro_name of one train. Each opspro_name must still be in the roster, so a stale mapping fails too. The Pi writes
  that roster (ADR-015); a mismatch is fixed in the master or by a decision about the Operations Pro train, never by
  editing the XML here. NOT_TRAINS lists the Operations Pro trains that are open owner questions. The staging trains
  (STG-DEMMLER, STG-SCULLY) are master rows with on_desks no.
- cats/data/generated_desk_header.xml: the CATS desks' train list (TRAINDATA, frozen into both desks) holds the
  master's trains on the desks (on_desks yes) in its order, with the same name, engine and font.

It prints each problem and exits 1 when there is one.
"""
from __future__ import annotations

import csv
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import operations, paths  # noqa: E402

ROOT = paths.REPO_ROOT
MASTER = ROOT / "ops/hart-ops/data/trains.csv"
CREW = ROOT / "ops/hart-ops/data/crew.json"  # the crew master (ADR-039, lane L5)
ROSTER = operations.ROSTERS["trains"]
HEADER = ROOT / "cats/data/generated_desk_header.xml"

# Operations Pro trains that are not in the master yet, with the reason. Each is an open owner question: a name here
# that the roster no longer has, or that the master now holds, fails.
NOT_TRAINS: dict[str, str] = {}
# desk header attribute -> master column
HEADER_FIELDS = {"TRAIN_SYMBOL": "train_symbol", "TRAIN_NAME": "train_name", "ENGINE": "engine", "FONT": "font"}


def read_master(path: Path = MASTER) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def crew_problems(trains: list[dict[str, str]], crew: dict) -> list[str]:
    symbols = {t["train_symbol"] for t in trains}
    return [f"{CREW.relative_to(ROOT)}: crew job {job.get('id')!r} has code {job.get('code')!r}, which is no "
            f"train_symbol of {MASTER.relative_to(ROOT)}"
            for job in crew.get("jobs", []) if job.get("kind") == "crew" and job.get("code") not in symbols]


def roster_problems(trains: list[dict[str, str]], names: list[str]) -> list[str]:
    rel = ROSTER.relative_to(ROOT)
    symbols = {t["train_symbol"] for t in trains}
    mapped = {t["opspro_name"]: t["train_symbol"] for t in trains if t.get("opspro_name")}
    problems = []
    seen: dict[str, str] = {}
    for t in trains:
        name = t.get("opspro_name")
        if name and name in seen:
            problems.append(f"{MASTER.relative_to(ROOT)}: {seen[name]} and {t['train_symbol']} share the opspro_name "
                            f"{name!r}")
        elif name:
            seen[name] = t["train_symbol"]
    for name in names:
        if name in symbols or name in mapped or name in NOT_TRAINS:
            continue
        problems.append(f"{rel}: Operations Pro train {name!r} is no train_symbol and no opspro_name of "
                        f"{MASTER.relative_to(ROOT)}")
    for name, symbol in mapped.items():
        if name not in names:
            problems.append(f"{MASTER.relative_to(ROOT)}: {symbol}'s opspro_name {name!r} is no train in {rel}")
        if name in symbols:
            problems.append(f"{MASTER.relative_to(ROOT)}: {symbol}'s opspro_name {name!r} is another train's symbol")
    for name, why in NOT_TRAINS.items():
        if name not in names:
            problems.append(f"check_train_symbols.NOT_TRAINS: {name!r} ({why}) is no longer in {rel}; drop it from "
                            "NOT_TRAINS, or give the renamed train a row in trains.csv")
        elif name in symbols or name in mapped:
            problems.append(f"check_train_symbols.NOT_TRAINS: {name!r} is in {MASTER.relative_to(ROOT)} now; drop it from "
                            "NOT_TRAINS")
    return problems


def header_problems(trains: list[dict[str, str]], root: ET.Element) -> list[str]:
    rel = HEADER.relative_to(ROOT)
    data = root.find(".//TRAINSTORE/TRAINDATA")
    if data is None:
        return [f"{rel}: no TRAINSTORE/TRAINDATA"]
    records = [{col: rec.get(attr, "") for attr, col in HEADER_FIELDS.items()} for rec in data.findall("DATARECORD")]
    want = [{col: t[col] for col in HEADER_FIELDS.values()} for t in trains if t.get("on_desks") == "yes"]
    if records == want:
        return []
    problems = [f"{rel}: the CATS train list differs from {MASTER.relative_to(ROOT)}"]
    problems += [f"  master row {i + 1}: {w}" for i, w in enumerate(want) if i >= len(records) or records[i] != w]
    problems += [f"  desk record {i + 1}: {r}" for i, r in enumerate(records) if i >= len(want) or want[i] != r]
    return problems


def main() -> int:
    trains = read_master()
    problems = crew_problems(trains, json.loads(CREW.read_text(encoding="utf-8")))
    problems += roster_problems(trains, [t.get("name", "") for t in operations.trains(ROSTER)])
    problems += header_problems(trains, ET.parse(HEADER).getroot())
    for p in problems:
        print(p)
    if problems:
        return 1
    print(f"check_train_symbols: {len(trains)} trains; crew jobs, Operations Pro trains and the CATS train list agree"
          f" ({len(NOT_TRAINS)} Operations Pro trains are open questions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
