"""Locomotive repository and stage 4 publish.

    cars.py locos add        Add a locomotive by answering questions (or --set)
    cars.py locos set ID F=V Change fields of a locomotive
    cars.py locos status     Show locomotives and the steps still open
    cars.py locos publish    Engine roster, roster photo and the JMRI import list

``data/locos.csv`` is the repository for locomotives, ``data/loco_queue.csv`` the open
steps. ``publish`` writes only files in the hart repo. The DecoderPro roster entry is
created on the Pi by ``jmri/layouts/hart/scripts/loco_roster_import.py`` from
``jmri/layouts/hart/data/new_locos.json``; it then needs roster_rename_road_ids.py, the
CS-105 sync. Dispatcher traininfo needs nothing per loco (wiki/pipelines/intake-stages.md, stage 4).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypedDict

from card_errors import CardPipelineError

if TYPE_CHECKING:
    from engine_lookup import EngineRecord

HART_OPS = Path(__file__).resolve().parents[1]
HART_ROOT = HART_OPS.parents[1]
LOCOS = HART_OPS / "data/locos.csv"
LOCO_QUEUE = HART_OPS / "data/loco_queue.csv"
ENGINE_ROSTER = HART_ROOT / "jmri/layouts/hart/operations/OperationsEngineRoster.xml"
ROSTER_PHOTOS = HART_ROOT / "jmri/resources/roster"
IMPORT_LIST = HART_ROOT / "jmri/layouts/hart/data/new_locos.json"

COLUMNS = [
    "roster_id",
    "road_name",
    "road_number",
    "dcc_address",
    "long_address",
    "mfg",
    "model",
    "loco_type",
    "length_ft",
    "weight_tons",
    "hp",
    "decoder",
    "sound",
    "source_image",
    "notes",
]
QUEUE_COLUMNS = ["roster_id", "queued", "published", "card_built", "card_printed",
                 "jmri_roster", "cs105", "traininfo"]
REQUIRED = ["road_name", "road_number", "dcc_address", "model", "loco_type", "length_ft"]
QUESTIONS = [
    ("road_name", "Road name (e.g. NW, BO, CSX)"),
    ("road_number", "Road number"),
    ("dcc_address", "DCC address"),
    ("long_address", "Long address (yes/no)"),
    ("mfg", "Manufacturer"),
    ("model", "Model (e.g. GP20)"),
    ("loco_type", "Type (Diesel, Steam, Electric)"),
    ("length_ft", "Length in feet"),
    ("weight_tons", "Weight in tons"),
    ("hp", "Horsepower"),
    ("decoder", "Decoder"),
    ("sound", "Sound (yes/no)"),
]

# One row of locos.csv or loco_queue.csv: column -> the CSV text, blank while unset.
LocoRow = dict[str, str]
ParseSets = Callable[[list[str]], dict[str, str]]
Upserted = Literal["added", "updated"]


class RosterEntry(TypedDict):
    """One entry of new_locos.json, what the Pi-side import needs to create the DecoderPro entry."""

    id: str
    road_name: str
    road_number: str
    mfg: str
    model: str
    dcc_address: str
    long_address: bool
    image: str
    comment: str


def read_locos() -> list[LocoRow]:
    if not LOCOS.is_file():
        return []
    with LOCOS.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_table(path: Path, columns: list[str], rows: list[LocoRow]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_queue() -> list[LocoRow]:
    if not LOCO_QUEUE.is_file():
        return []
    with LOCO_QUEUE.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def loco_roster_id(road: str, number: str) -> str:
    """The DecoderPro ID is the road name and number: "NWR 06", "BO 572"."""
    return f"{road.strip()} {number.strip()}".strip()


def ops_id(road: str, number: str) -> str:
    """The Operations Pro engine id has no space: CR1993, BO9602."""
    return re.sub(r"[^A-Za-z0-9]", "", road) + re.sub(r"[^A-Za-z0-9]", "", number)


def missing_fields(row: Mapping[str, str]) -> list[str]:
    return [f for f in REQUIRED if not row.get(f, "").strip()]


def upsert(rows: list[LocoRow], queue: list[LocoRow], fields: Mapping[str, str]) -> Upserted:
    """Add or update a locomotive. Returns "added" or "updated"."""
    rid = loco_roster_id(fields.get("road_name", ""), fields.get("road_number", ""))
    if not fields.get("road_name") or not fields.get("road_number"):
        raise CardPipelineError("A locomotive needs a road name and a road number.")
    fields = {**fields, "roster_id": rid}
    for row in rows:
        if row["roster_id"] == rid:
            row.update({k: v for k, v in fields.items() if v})
            return "updated"
    rows.append({c: fields.get(c, "") for c in COLUMNS})
    queue.append({c: "" for c in QUEUE_COLUMNS} | {"roster_id": rid, "queued": date.today().isoformat()})
    return "added"


def cmd_add(args: argparse.Namespace, parse_sets: ParseSets) -> int:
    rows, queue = read_locos(), read_queue()
    values = parse_sets(args.set)
    if not args.yes:
        print("Press Enter to skip a value.")
        for field, label in QUESTIONS:
            if field not in values:
                answer = input(f"  {label}: ").strip()
                if answer:
                    values[field] = answer
    print(f"{upsert(rows, queue, values)} {loco_roster_id(values.get('road_name', ''), values.get('road_number', ''))}")
    write_table(LOCOS, COLUMNS, rows)
    write_table(LOCO_QUEUE, QUEUE_COLUMNS, queue)
    return 0


def cmd_set(args: argparse.Namespace, parse_sets: ParseSets) -> int:
    rows = read_locos()
    row = next((r for r in rows if r["roster_id"] == args.roster_id), None)
    if row is None:
        raise CardPipelineError(f"{args.roster_id} is not in the locomotive repository.")
    row.update(parse_sets(args.fields))
    write_table(LOCOS, COLUMNS, rows)
    print(f"Updated {args.roster_id}; still missing: {' '.join(missing_fields(row)) or 'nothing'}")
    return 0


def cmd_status(_args: argparse.Namespace, _parse_sets: ParseSets) -> int:
    rows, queue = read_locos(), {q["roster_id"]: q for q in read_queue()}
    print(f"Locomotives: {len(rows)}")
    for r in rows:
        q = queue.get(r["roster_id"])
        if q is None:
            continue
        miss = missing_fields(r)
        steps = " ".join(f"{k}={q.get(k) or '-'}" for k in QUEUE_COLUMNS[2:])
        print(f"  {r['roster_id']:<12} {steps}" + (f"  needs: {' '.join(miss)}" if miss else ""))
    return 0


def engine_element(row: Mapping[str, str]) -> dict[str, str]:
    """The attributes of the <engine> element merge_engines adds for one locomotive."""
    attrs = {
        "id": ops_id(row["road_name"], row["road_number"]),
        "roadName": row["road_name"],
        "roadNumber": row["road_number"],
        "type": row["loco_type"],
        "length": row["length_ft"],
        "moves": "0",
        "date": "",
        "selected": "false",
        "model": row["model"],
        "hp": row.get("hp", ""),
        "bUnit": "false",
    }
    if row.get("weight_tons"):
        attrs["weightTons"] = row["weight_tons"]
    return attrs


def merge_engines(path: Path, rows: list[LocoRow]) -> list[str]:
    """Add engines the roster lacks. Existing engines keep their session state."""
    text = path.read_text(encoding="utf-8")
    header = text[: text.index("<operations-config")]
    root = ET.fromstring(text[len(header):])
    engines = root.find("engines")
    if engines is None:
        raise CardPipelineError(f"{path} has no <engines> section")
    models = root.find("models")
    have = {e.get("id") for e in engines}
    added = []
    for row in rows:
        attrs = engine_element(row)
        if attrs["id"] in have:
            continue
        ET.SubElement(engines, "engine", attrs)
        added.append(attrs["id"])
        if models is not None and not any(m.get("name") == row["model"] for m in models):
            ET.SubElement(models, "model", {"name": row["model"]})
    path.write_text(header + ET.tostring(root, encoding="unicode") + "\n", encoding="utf-8")
    return added


def roster_entry(row: Mapping[str, str]) -> RosterEntry:
    """What the Pi-side import needs to create the DecoderPro entry."""
    if not row["dcc_address"].strip().isdigit():
        raise CardPipelineError(f"{row['roster_id']}: DCC address {row['dcc_address']!r} is not a number")
    return {
        "id": row["roster_id"],
        "road_name": row["road_name"],
        "road_number": row["road_number"],
        "mfg": row.get("mfg", ""),
        "model": row["model"],
        "dcc_address": row["dcc_address"],
        "long_address": row.get("long_address", "").lower() in ("yes", "true", "1")
        or int(row["dcc_address"]) > 127,
        "image": f"preference:resources/roster/{row['road_number']}.jpg",
        "comment": row.get("notes", ""),
    }


def card_row(row: Mapping[str, str]) -> tuple[dict[str, str], EngineRecord]:
    """A repository row and engine record in the shape generate_all_cards.row_to_card reads.

    The engine record comes from locos.csv itself, so a card can be built before publish
    has put the loco in the engine roster.
    """
    from engine_lookup import ROAD_DISPLAY, manufacturer_for_model

    card = {
        "roster_id": row["roster_id"],
        "reporting_marks": row["road_name"],
        "road_name": row["road_name"],
        "roster_road": ROAD_DISPLAY.get(row["road_name"], row["road_name"]),
        "road_number": row["road_number"],
        "car_type": "Locomotive",
        "source_image": row.get("source_image", ""),
        "roster_length_ft": row.get("length_ft", ""),
        "notes": row.get("model", ""),
    }
    engine: EngineRecord = {
        "engine_roster_id": ops_id(row["road_name"], row["road_number"]),
        "roster_road": row["road_name"],
        "road_number": row["road_number"],
        "engine_type": row.get("loco_type", ""),
        "model": row.get("model", ""),
        "length_ft": row.get("length_ft", ""),
        "manufacturer": row.get("mfg") or manufacturer_for_model(row.get("model", "")),
    }
    return card, engine


def photo_to_jpg(src: Path, dst: Path) -> None:
    from PIL import Image

    dst.parent.mkdir(parents=True, exist_ok=True)
    Image.open(src).convert("RGB").save(dst, quality=90)


def cmd_publish(args: argparse.Namespace, _parse_sets: ParseSets, final_dir: Path | None = None) -> int:
    rows, queue = read_locos(), read_queue()
    open_ids = {q["roster_id"] for q in queue if not q["published"]}
    todo = [r for r in rows if r["roster_id"] in open_ids]
    if not todo:
        print("No locomotives waiting to be published.")
        return 0
    bad = {r["roster_id"]: missing_fields(r) for r in todo if missing_fields(r)}
    for rid, miss in bad.items():
        print(f"  {rid}: missing {' '.join(miss)}")
    if bad:
        raise CardPipelineError("Fill the missing fields with: cars.py locos set ID FIELD=VALUE")
    added = merge_engines(ENGINE_ROSTER, todo)
    entries: list[RosterEntry] = []
    if IMPORT_LIST.is_file():
        entries = json.loads(IMPORT_LIST.read_text(encoding="utf-8"))
    known = {e["id"] for e in entries}
    for r in todo:
        if r["roster_id"] not in known:
            entries.append(roster_entry(r))
        src = (final_dir or Path()) / f"{Path(r['source_image']).stem}.png" if r.get("source_image") else None
        if src and src.is_file():
            photo_to_jpg(src, ROSTER_PHOTOS / f"{r['road_number']}.jpg")
        else:
            print(f"  {r['roster_id']}: no photo found; the roster entry will have none.")
    IMPORT_LIST.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    for q in queue:
        if q["roster_id"] in open_ids:
            q["published"] = date.today().isoformat()
    write_table(LOCO_QUEUE, QUEUE_COLUMNS, queue)
    print(f"Engine roster: added {' '.join(added) or 'none'}. Import list: {IMPORT_LIST}")
    print("Commit and deploy (sync_hart_package.sh --all), then run loco_roster_import.py on the Pi.")
    return 0
