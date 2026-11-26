#!/usr/bin/env python3
"""HART car workflow: one car repository feeding cards, STS and Operations Pro.

    cars.py import-legacy   Add roster cars with no photo to the repository (once)
    cars.py intake          Process new photos in ops/car-cards/incoming/
    cars.py add             Add a car with no photo by answering questions
    cars.py status          Show the queue of cars still working through the steps
    cars.py review          Stage 1: crop and read new photos, write a review sheet
    cars.py ai-notes BATCH FILE   Merge an AI reviewer's readings into the review sheet
    cars.py kind BATCH car|loco PHOTO...   Set whether photos are cars or locomotives
    cars.py fill BATCH [--set COL=VAL]   Set a column on every row, fill empty details from the best row
    cars.py sheet-import BATCH FILE   Load the review.csv downloaded from the review page
    cars.py crop BATCH [PHOTO X,Y,W,H[,ANGLE]]   Crop picker on the review page / re-cut a photo
    cars.py approve BATCH   Approve the unflagged rows of a review sheet
    cars.py records BATCH   Stage 2: write approved rows into the repository
    cars.py site            Stage 5: add new photographed cars and locos to the public gallery
    cars.py locos ...       Locomotive repository and stage 4 publish (add, set, status, publish)
    cars.py cards           Build a print .docx for every queued car without a card
    cars.py publish         Rebuild rosters, feed STS, merge into Operations Pro
    cars.py seed-copy       Rebuild the roster and refresh the STS seed copies only
    cars.py compare         Report differences between the repository and each tool
    cars.py sync            Send the repository's identity fields to the tools that differ (dry run; --apply writes)

``data/image_metadata.csv`` is the repository: one row per car, with a blank
``source_image`` until the car is photographed. ``data/car_queue.csv`` tracks
which new cars still need a card, STS or Operations Pro.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import importlib
import os
import shutil
import subprocess
import sys
import urllib.request
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent
HART_ROOT = PIPELINE.parents[2]
os.environ.setdefault("HART_CAR_CARDS_ROOT", str(HART_ROOT / "ops/car-cards"))

from car_paths import DATA, FINAL_DIR, IMAGES_DIR, ROOT, CardPipelineError  # noqa: E402
from car_records import (  # noqa: E402
    CarMerge, CarRow, FieldDiff, FieldTarget, IntakeContext, MergeOutcome, QueueItem,
)
from hartlib import operations  # noqa: E402  (car_paths put tools/hartlib/src on sys.path)

METADATA = DATA / "image_metadata.csv"
QUEUE = DATA / "car_queue.csv"
MERGED = DATA / "HART_MergedCarRoster.xml"
OPS = DATA / "OperationsCarRoster.xml"
# ADR-015: the repo copy is the master; the deploy installs it on the hosts.
OPS_MERGED = HART_ROOT / "jmri/layouts/hart/operations/OperationsCarRoster.xml"
STS_HELPERS = HART_ROOT / "external/sts-helpers"
# Publish copies these into the STS seed; compare reports when the copies drift.
SEED_COPIES = (METADATA, MERGED)

SEED_INPUTS = STS_HELPERS / "seed/inputs"
NO_SEED_DIR = (
    "{path} does not exist (is the external/sts-helpers submodule checked out? "
    "git submodule update --init external/sts-helpers)"
)
PRINT_DIR = ROOT / "print"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".heic", ".tif", ".tiff"}
DEPLOY_NOTE = "Commit it in the hart repo, then deploy with tools/hosts/sync_hart_package.sh."
QUEUE_COLUMNS = [
    "roster_id",
    "reason",
    "queued",
    "card_built",
    "card_printed",
    "sts",
    "ops",
]
QUESTIONS = [
    ("reporting_marks", "Reporting marks (e.g. N&W)"),
    ("road_number", "Road number"),
    ("car_type", "Car type (Boxcar, Hopper, Flatcar, Gondola, Tank, Coil, MOW...)"),
    ("car_class", "AAR class (e.g. F3)"),
    ("color", "Color"),
    ("roster_length_ft", "Length in feet"),
    ("capy_lbs", "Capacity lbs"),
    ("ld_lmt_lbs", "Load limit lbs"),
    ("lt_wt_lbs", "Light weight lbs"),
    ("built", "Built date"),
    ("full_name", "Card description override (blank for automatic)"),
]


def today() -> str:
    return date.today().isoformat()


def read_rows() -> tuple[list[CarRow], list[str]]:
    with METADATA.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader), list(reader.fieldnames or [])


def write_rows(rows: list[CarRow], columns: list[str]) -> None:
    tmp = METADATA.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(METADATA)


def read_queue() -> list[QueueItem]:
    if not QUEUE.is_file():
        return []
    with QUEUE.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_queue(queue: list[QueueItem]) -> None:
    with QUEUE.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=QUEUE_COLUMNS)
        writer.writeheader()
        writer.writerows(queue)


def enqueue(queue: list[QueueItem], roster_id: str, reason: str) -> None:
    """Queue a card. A new car also needs STS and Operations Pro; a photo does not."""
    for item in queue:
        if item["roster_id"] == roster_id and not item["card_printed"]:
            item["reason"] = reason
            item["card_built"] = ""
            return
    done = today() if reason == "photo added" else ""
    queue.append(
        {
            "roster_id": roster_id,
            "reason": reason,
            "queued": today(),
            "card_built": "",
            "card_printed": "",
            "sts": done,
            "ops": done,
        }
    )


def row_id(row: CarRow) -> str:
    from roster_id import manifest_car_id

    return manifest_car_id(row)


def find_car(rows: list[CarRow], roster_id: str) -> CarRow | None:
    return next((r for r in rows if row_id(r) == roster_id), None)


def parse_sets(pairs: list[str]) -> dict[str, str]:
    values = {}
    for pair in pairs:
        if "=" not in pair:
            raise CardPipelineError(f"--set needs field=value, got {pair!r}")
        key, value = pair.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def ask(row: CarRow, values: dict[str, str], assume_yes: bool) -> None:
    """Fill the row from --set values, then ask about anything left."""
    row.update(values)
    if assume_yes:
        return
    print("Press Enter to keep the value in brackets.")
    for field, label in QUESTIONS:
        if field in values:
            continue
        current = row.get(field, "")
        answer = input(f"  {label} [{current}]: ").strip()
        if answer:
            row[field] = answer


def finish_row(row: CarRow, columns: list[str]) -> str:
    """Fill the derived fields and return the roster id."""
    from build_merged_car_roster import default_weights
    from roster_id import assign_freight_roster_id

    row["road_name"] = row.get("road_name") or row.get("reporting_marks", "")
    row["roster_id"] = ""
    row["roster_road"] = ""
    assign_freight_roster_id(row)
    roster_id = row.get("roster_id", "")
    if not roster_id:
        raise CardPipelineError("A car needs reporting marks and a road number.")
    length = row.get("roster_length_ft", "")
    if length and not (row.get("roster_weight_oz") and row.get("roster_weight_tons")):
        row["roster_weight_oz"], row["roster_weight_tons"] = default_weights(length)
    for column in columns:
        row.setdefault(column, "")
    return roster_id


def cmd_import_legacy(_args: argparse.Namespace) -> int:
    """Bring roster-only cars into the repository so it holds the whole fleet."""
    rows, columns = read_rows()
    known = {row_id(r) for r in rows}
    added = 0
    for car in operations.cars(OPS):
        cid = car.get("id", "")
        if cid in known:
            continue
        rows.append(
            {
                **{c: "" for c in columns},
                "reporting_marks": car.get("roadName", ""),
                "road_name": car.get("roadName", ""),
                "road_number": car.get("roadNumber", ""),
                "car_type": car.get("type", ""),
                "color": car.get("color", ""),
                "roster_id": cid,
                "roster_road": car.get("roadName", ""),
                "roster_length_ft": car.get("length", ""),
                "roster_weight_oz": car.get("weight", ""),
                "roster_weight_tons": car.get("weightTons", ""),
                "match_confidence": "operations-pro",
                "notes": "No photo yet",
            }
        )
        added += 1
    write_rows(rows, columns)
    print(f"Added {added} cars without photos; repository has {len(rows)} rows.")
    return 0


def to_png(src: Path) -> Path:
    """Photos are processed as PNG. Any other format is converted beside the original."""
    if src.suffix.lower() == ".png":
        return src
    dst = src.with_suffix(".png")
    if src.suffix.lower() == ".heic":
        subprocess.run(["sips", "-s", "format", "png", str(src), "--out", str(dst)],
                       check=True, capture_output=True)
    else:
        from PIL import Image

        Image.open(src).convert("RGB").save(dst)
    return dst


def process_photo(png: Path) -> dict[str, str]:
    """Crop, OCR and finalize one photo. Returns the fields it could read."""
    import pytesseract  # noqa: F401
    from PIL import Image

    import finalize_car_images as final
    import process_car_images as proc
    from car_paths import CAR_IMAGES_DIR, CARD_FILL_PRINT_DIR, OCR_DIR
    from crop_car_image import detect_car_bbox, process_image
    from sharpen_card_fill_images import sharpen_for_print

    stem = png.stem
    meta = process_image(png, CAR_IMAGES_DIR / f"{stem}.png")
    image = Image.open(png)
    text, zoom = proc._ocr_band(image, detect_car_bbox(image))
    OCR_DIR.mkdir(parents=True, exist_ok=True)
    zoom.save(OCR_DIR / f"OCR_{stem}.png")
    parsed = proc._parse_markings(text)
    marks, number = proc._find_road_mark(text, proc.load_roster())
    if not final.finalize_one(stem):
        raise CardPipelineError(f"Could not finalize {png.name}")
    CARD_FILL_PRINT_DIR.mkdir(parents=True, exist_ok=True)
    sharpen_for_print(Image.open(FINAL_DIR / f"{stem}.png")).save(
        CARD_FILL_PRINT_DIR / f"{stem}.png"
    )
    read = proc.ocr_lettering(Image.open(FINAL_DIR / f"{stem}.png"))
    if read.get("reporting_marks"):  # the colour read of the finished crop beats the general OCR
        marks, number = read["reporting_marks"], read["road_number"]
        text = f"{read.get('ocr_text', '')} {text}"
    parsed.update({k: v for k, v in read.items() if k in ("ld_lmt_lbs", "lt_wt_lbs")})
    return {
        "source_image": png.name,
        "cropped_image": f"CarImages/{stem}.png",
        "ocr_zoom_image": f"OcrZoom/OCR_{stem}.png",
        "crop_status": meta.get("crop_status", "ok"),
        "reporting_marks": marks,
        "road_name": marks,
        "road_number": number,
        "car_type": parsed.get("car_type", ""),
        "car_class": parsed.get("car_class", ""),
        "capy_lbs": parsed.get("capy_lbs", ""),
        "ld_lmt_lbs": parsed.get("ld_lmt_lbs", ""),
        "lt_wt_lbs": parsed.get("lt_wt_lbs", ""),
        "built": parsed.get("built", ""),
        "ocr_text": text[:400].replace("\n", " "),
        "match_confidence": "intake",
        "notes": "CarImagesFinal",
    }


def new_photos(rows: list[CarRow]) -> list[Path]:
    seen = {Path(r["source_image"]).stem for r in rows if r.get("source_image")}
    return sorted(
        p
        for p in IMAGES_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES and p.stem not in seen
    )


def merge_car(row: CarRow, rows: list[CarRow], columns: list[str], queue: list[QueueItem],
              dry_run: bool) -> CarMerge:
    """Fill the derived fields of a new car row and merge it into the repository rows.

    A new roster id is appended and queued as a new car. A car already in the repository
    takes the row's non-blank values and is queued for its photo, unless it already has a
    photo, which is left alone. ``dry_run`` reports the outcome and changes nothing.
    """
    roster_id = finish_row(row, columns)
    existing = find_car(rows, roster_id)
    if existing is None:
        if not dry_run:
            rows.append(row)
            enqueue(queue, roster_id, MergeOutcome.NEW_CAR.value)
        return CarMerge(roster_id, MergeOutcome.NEW_CAR, "")
    if existing.get("source_image"):
        return CarMerge(roster_id, MergeOutcome.SKIPPED, existing["source_image"])
    if not dry_run:
        for key, value in row.items():
            if value:
                existing[key] = value
        enqueue(queue, roster_id, MergeOutcome.PHOTO_ADDED.value)
    return CarMerge(roster_id, MergeOutcome.PHOTO_ADDED, "")


def cmd_intake(args: argparse.Namespace) -> int:
    rows, columns = read_rows()
    queue = read_queue()
    photos = new_photos(rows)
    if not photos:
        print(f"No new photos in {IMAGES_DIR}")
        return 0
    values = parse_sets(args.set)
    for photo in photos:
        print(f"\n{photo.name}")
        fields = process_photo(to_png(photo))
        print(f"  Crop: {fields['crop_status']}. Check {FINAL_DIR / (photo.stem + '.png')}")
        row: CarRow = {c: "" for c in columns}  # type: ignore[misc]  # columns are the CSV header
        row.update(fields)
        ask(row, values, args.yes)
        merged = merge_car(row, rows, columns, queue, dry_run=False)
        if merged.outcome is MergeOutcome.NEW_CAR:
            print(f"  Added {merged.roster_id}")
        elif merged.outcome is MergeOutcome.SKIPPED:
            print(f"  {merged.roster_id} already has {merged.existing_image}; skipped.")
        else:
            print(f"  Added the photo to {merged.roster_id}")
        write_rows(rows, columns)
        write_queue(queue)
    return 0


def guess_roster_id(review_row: Mapping[str, str], kind: str) -> str:
    """The roster id a review row would get, or "" when marks or number are missing."""
    if kind == "loco":
        import locos

        marks, number = review_row.get("reporting_marks", ""), review_row.get("road_number", "")
        return locos.loco_roster_id(marks, number) if marks and number else ""
    row = {k: v for k, v in review_row.items() if k in ("reporting_marks", "road_number", "car_type")}
    row["road_name"] = row.get("reporting_marks", "")
    if not (row["road_name"] and row.get("road_number")):
        return ""
    from roster_id import assign_freight_roster_id

    assign_freight_roster_id(row)
    return row.get("roster_id", "")


def record_car(r: Mapping[str, str], rows: list[CarRow], columns: list[str], queue: list[QueueItem],
               dry_run: bool) -> str:
    """Stage 2 for one approved car row, the same writes as ``intake`` makes."""
    row: CarRow = {c: "" for c in columns}  # type: ignore[misc]  # columns are the CSV header
    photo = Path(r["photo"])
    row.update(
        {
            "source_image": r["photo"],
            "cropped_image": f"CarImages/{photo.stem}.png",
            "ocr_zoom_image": f"OcrZoom/OCR_{photo.stem}.png",
            "crop_status": r["crop_status"],
            "reporting_marks": r["reporting_marks"],
            "road_name": r["reporting_marks"],
            "match_confidence": "intake",
            "notes": "CarImagesFinal",
        }
    )
    for key in ("road_number", "car_type", "car_class", "color", "roster_length_ft",
                "capy_lbs", "ld_lmt_lbs", "lt_wt_lbs", "built", "full_name", "ocr_text"):
        row[key] = r.get(key, "")
    merged = merge_car(row, rows, columns, queue, dry_run)
    if merged.outcome is MergeOutcome.NEW_CAR:
        return f"new car {merged.roster_id}"
    if merged.outcome is MergeOutcome.SKIPPED:
        return f"skipped: {merged.roster_id} already has {merged.existing_image}"
    return f"photo added to {merged.roster_id}"


def record_loco(r: Mapping[str, str], dry_run: bool) -> str:
    """Stage 2 for one approved loco row. The details come later with ``locos set``."""
    import locos

    rows, queue = locos.read_locos(), locos.read_queue()
    fields = {"road_name": r["reporting_marks"], "road_number": r["road_number"],
              "source_image": r["photo"], "loco_type": "Diesel"}
    fields = {k: v for k, v in fields.items() if v}
    if dry_run:
        return f"loco {locos.loco_roster_id(fields.get('road_name', ''), fields.get('road_number', ''))}"
    outcome = locos.upsert(rows, queue, fields)
    locos.write_table(locos.LOCOS, locos.COLUMNS, rows)
    locos.write_table(locos.LOCO_QUEUE, locos.QUEUE_COLUMNS, queue)
    rid = locos.loco_roster_id(fields["road_name"], fields["road_number"])
    miss = locos.missing_fields(next(x for x in rows if x["roster_id"] == rid))
    return f"loco {outcome} {rid}; needs {' '.join(miss) or 'nothing'}"


def intake_context() -> IntakeContext:
    return IntakeContext(
        IMAGES_DIR=IMAGES_DIR, FINAL_DIR=FINAL_DIR, IMAGE_SUFFIXES=frozenset(IMAGE_SUFFIXES),
        read_rows=read_rows, write_rows=write_rows, read_queue=read_queue, write_queue=write_queue,
        find_car=find_car, guess_roster_id=guess_roster_id, to_png=to_png,
        process_photo=process_photo, record_car=record_car, record_loco=record_loco,
    )


def stage(module: str, name: str) -> Callable[[argparse.Namespace], int]:
    """A command that runs ``module.name(args, intake_context())``, importing the module on use."""

    def run(args: argparse.Namespace) -> int:
        return getattr(importlib.import_module(module), name)(args, intake_context())

    return run


def cmd_locos(args: argparse.Namespace) -> int:
    import locos

    run = {"add": locos.cmd_add, "set": locos.cmd_set, "status": locos.cmd_status}
    if args.action == "publish":
        return locos.cmd_publish(args, parse_sets, FINAL_DIR)
    return run[args.action](args, parse_sets)


def cmd_add(args: argparse.Namespace) -> int:
    rows, columns = read_rows()
    queue = read_queue()
    row = {c: "" for c in columns}
    row["match_confidence"] = "questionnaire"
    row["notes"] = "No photo yet"
    ask(row, parse_sets(args.set), args.yes)
    roster_id = finish_row(row, columns)
    if find_car(rows, roster_id):
        raise CardPipelineError(f"{roster_id} is already in the repository.")
    rows.append(row)
    enqueue(queue, roster_id, "new car")
    write_rows(rows, columns)
    write_queue(queue)
    print(f"Added {roster_id} with no photo.")
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    rows, _ = read_rows()
    queue = read_queue()
    no_photo = [r for r in rows if not r.get("source_image")]
    print(f"Cars: {len(rows)} ({len(no_photo)} without a photo)")
    print(f"New photos waiting: {len(new_photos(rows))}")
    open_items = [q for q in queue if not (q["card_printed"] and q["sts"] and q["ops"])]
    if not open_items:
        print("Queue is empty.")
        return 0
    print(f"{'Car':<16}{'Reason':<14}{'Card':<12}{'Printed':<12}{'STS':<12}{'Ops Pro':<12}")
    for q in open_items:
        print(
            f"{q['roster_id']:<16}{q['reason']:<14}{q['card_built'] or '-':<12}"
            f"{q['card_printed'] or '-':<12}{q['sts'] or '-':<12}{q['ops'] or '-':<12}"
        )
    return 0


def cmd_cards(args: argparse.Namespace) -> int:
    import locos

    queue = read_queue()
    loco_queue = locos.read_queue()
    if args.mark_printed:
        count = 0
        for item in queue + loco_queue:
            if item.get("card_built") and not item.get("card_printed"):
                item["card_printed"] = today()
                count += 1
        write_queue(queue)
        if loco_queue:
            locos.write_table(locos.LOCO_QUEUE, locos.QUEUE_COLUMNS, loco_queue)
        print(f"Marked {count} cards printed.")
        return 0
    pending = [q for q in queue if not q["card_printed"]]
    loco_pending = [q for q in loco_queue if not q.get("card_printed")]
    if not pending and not loco_pending and not args.trains:
        print("No cards queued.")
        return 0

    import generate_all_cards as gen

    rows, _ = read_rows()
    roster = gen.load_roster()
    _, engines = gen.load_engine_roster()
    cards = []
    for item in pending:
        row = find_car(rows, item["roster_id"])
        if row is None:
            raise CardPipelineError(f"Queued car {item['roster_id']} is not in the repository.")
        record, image = gen.row_to_card(row, roster, engines)
        cards.append((record, image, row))
        print(f"  {record['RoadName']} {record['RoadNumber']}: {'photo' if image else 'no photo'}")
    loco_rows = {r["roster_id"]: r for r in locos.read_locos()}
    for item in loco_pending:
        loco = loco_rows.get(item["roster_id"])
        if loco is None:
            raise CardPipelineError(f"Queued loco {item['roster_id']} is not in the locomotive repository.")
        card, engine = locos.card_row(loco)
        engines = {**engines, (loco["road_name"], loco["road_number"]): engine}
        record, image = gen.row_to_card(card, roster, engines)
        cards.append((record, image, card))
        print(f"  {record['RoadName']} {record['RoadNumber']} (loco): {'photo' if image else 'no photo'}")
    if args.trains:
        import train_cards

        cards.extend(train_cards.train_cards())
        print(f"  + {len(train_cards.TRAINS)} train cards")
    PRINT_DIR.mkdir(parents=True, exist_ok=True)
    gen.OUTPUT = PRINT_DIR / f"HART_New_Car_Cards_{today()}.docx"
    gen.generate(cards)
    for item in pending + loco_pending:
        item["card_built"] = today()
    write_queue(queue)
    if loco_queue:
        locos.write_table(locos.LOCO_QUEUE, locos.QUEUE_COLUMNS, loco_queue)
    print(f"Wrote {gen.OUTPUT}. After printing, run: cars.py cards --mark-printed")
    return 0


def add_to_sections(root: ET.Element, car: ET.Element) -> None:
    for section, tag, value in (
        ("roads", "road", car.get("roadName")),
        ("types", "type", car.get("type")),
        ("colors", "color", car.get("color")),
    ):
        parent = root.find(section)
        if parent is None or not value:
            continue
        if not any(e.get("name") == value for e in parent):
            ET.SubElement(parent, tag, {"name": value})


def write_ops(tree: ET.ElementTree, live_path: Path) -> None:
    """Write the merged roster, keeping the stylesheet and DOCTYPE lines ElementTree drops."""
    text = live_path.read_text(encoding="utf-8")
    header = text[: text.index("<operations-config")]
    body = ET.tostring(tree.getroot(), encoding="unicode")
    live_path.write_text(header + body + "\n", encoding="utf-8")


def out_of_service_ids(rows: list[CarRow]) -> set[str]:
    """The cars the repository holds out of service. STS and Operations Pro follow this."""
    return {row_id(r) for r in rows if r.get("out_of_service") == "yes"}


def ops_out_of_service(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    return {
        c.get("id", "") for c in operations.cars(path) if c.get("outOfService") == "true"
    }


def merge_ops(
    live_path: Path,
    wanted: list[str],
    out_of_service: set[str] | None = None,
) -> list[str]:
    """Add cars to the Operations Pro roster, leaving every other car alone.

    When out_of_service is given, every car's flag is set to match it.
    """
    tree = ET.parse(live_path)
    root = tree.getroot()
    cars_el = root.find("cars")
    have = {c.get("id") for c in cars_el.findall("car")}
    source = {c.get("id"): c for c in operations.cars(MERGED)}
    added = []
    for roster_id in wanted:
        if roster_id in have:
            continue
        if roster_id not in source:
            raise CardPipelineError(f"{roster_id} is missing from {MERGED.name}")
        car = source[roster_id]
        cars_el.append(car)
        added.append(roster_id)
        add_to_sections(root, car)
    if out_of_service is not None:
        for car in cars_el.findall("car"):
            if car.get("id") in out_of_service:
                car.set("outOfService", "true")
            else:
                car.attrib.pop("outOfService", None)
    write_ops(tree, live_path)
    return added


PI_HOST = os.environ.get("HART_PI_SSH", "pi")
PI_OPS_DIR = os.environ.get("HART_PI_USERFILES", "/home/pi/JMRI_UserFiles") + "/operations"


def publish_gate(args: argparse.Namespace) -> None:
    """Stop before anything is changed unless the stage 3 checks pass (ADR-018)."""
    import intake_stages
    import publish_gate as gate

    sys.path.insert(0, str(STS_HELPERS / "lib"))
    from sts_paths import backups_dir

    problems = gate.run_gate(
        batch_root=intake_stages.BATCH_ROOT,
        tracked=[METADATA, QUEUE],
        ops_local=OPS_MERGED.parent,
        pi_host=PI_HOST,
        pi_dir=PI_OPS_DIR,
        backups_dir=backups_dir(),
        only=bool(args.only),
        skip=args.skip_check,
    )
    if problems:
        raise CardPipelineError("\n".join(["Publish stopped:", *(f"  {line}" for line in problems)]))


def sync_seed_copies(inputs: Path, masters: tuple[Path, ...]) -> None:
    """Copy the master car files into the STS seed inputs and nothing else."""
    if not inputs.is_dir():
        raise CardPipelineError(NO_SEED_DIR.format(path=inputs))
    for source in masters:
        if not source.is_file():
            raise CardPipelineError(f"Master file is missing: {source}")
    for source in masters:
        shutil.copy2(source, inputs / source.name)
    print(f"Copied the repository and roster to {inputs}")


def cmd_seed_copy(args: argparse.Namespace) -> int:
    """Rebuild the merged roster as publish does, then refresh the STS seed copies only."""
    from build_car_roster_sor import main as build_roster

    build_roster()
    sync_seed_copies(SEED_INPUTS, SEED_COPIES)
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    from build_car_roster_sor import main as build_roster

    publish_gate(args)
    build_roster()
    queue = read_queue()
    if args.only:
        unknown = [i for i in args.only if i not in {q["roster_id"] for q in queue}]
        if unknown:
            raise CardPipelineError(f"Not in the queue: {' '.join(unknown)}")

    def chosen(item: dict) -> bool:
        """With --only, the rest of the queue is left exactly as it is."""
        return not args.only or item["roster_id"] in args.only

    sync_seed_copies(SEED_INPUTS, SEED_COPIES)

    for_sts = [q for q in queue if not q["sts"] and chosen(q)]
    if for_sts:
        result = subprocess.run(
            [sys.executable, str(STS_HELPERS / "tools/add_hart_cars.py"),
             *[q["roster_id"] for q in for_sts]],
            check=False,
        )
        if result.returncode:
            print("STS step failed; those cars stay queued.", file=sys.stderr)
        else:
            for item in for_sts:
                item["sts"] = today()
            write_queue(queue)

    result = subprocess.run(
        [sys.executable, str(STS_HELPERS / "tools/sync_hart_status.py")], check=False
    )
    if result.returncode:
        print("STS out-of-service sync failed.", file=sys.stderr)

    for_ops = [q["roster_id"] for q in queue if not q["ops"] and chosen(q)]
    live = Path(args.ops_live)
    rows, _ = read_rows()
    out = out_of_service_ids(rows)
    flags_differ = live.is_file() and ops_out_of_service(live) != out
    if for_ops or flags_differ:
        added = merge_ops(live, for_ops, out_of_service=out)
        for item in queue:
            if not item["ops"] and chosen(item):
                item["ops"] = today()
        write_queue(queue)
        print(f"Added {len(added)} cars to {OPS_MERGED}; {len(out)} out of service")
        print(DEPLOY_NOTE)
    return 0


def cmd_service(args: argparse.Namespace) -> int:
    """Record a car as out of or back in service. Publish carries it to STS and Operations Pro."""
    rows, columns = read_rows()
    if "out_of_service" not in columns:
        columns.append("out_of_service")
    for roster_id in args.roster_ids:
        matches = [r for r in rows if row_id(r) == roster_id]
        if not matches:
            raise CardPipelineError(f"{roster_id} is not in the repository.")
        for row in matches:
            row["out_of_service"] = "yes" if args.state == "out" else ""
    write_rows(rows, columns)
    print(f"Marked {args.state} of service: {' '.join(args.roster_ids)}. Run publish to send it.")
    return 0


def cmd_fix_ops(args: argparse.Namespace) -> int:
    """Bring the Operations Pro roster up to the repository. Leaves STS and the queue alone."""
    from build_car_roster_sor import main as build_roster

    build_roster()
    rows, _ = read_rows()
    live = Path(args.ops_live)
    wanted = sorted(
        row_id(r) for r in rows
        if row_id(r) and (r.get("car_type") or "") not in ("Locomotive", "Streetcar")
    )
    unknown = sorted(ops_ids(live) - {row_id(r) for r in rows})
    added = merge_ops(live, wanted, out_of_service_ids(rows))
    print(f"Added {len(added)}: {' '.join(added)}")
    if unknown:
        # fix-ops renames nothing: a car kept under a wrong id would now sit beside its added right id.
        print(f"Not in the repository, left as they are (check each by hand): {' '.join(unknown)}")
    print(DEPLOY_NOTE)
    return 0


def seed_marks() -> set[str]:
    import re

    backups = HART_ROOT / "external/sts-docker-data/backups"
    seed = next((p for p in (backups / "hart_seed0", backups / "hart_seed") if p.is_file()), None)
    if seed is None:
        return set()
    text = seed.read_text(encoding="utf-8", errors="replace")
    return set(re.findall(r'insert into `cars` values\("\d+","([^"]*)"', text))


def ops_ids(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    return set(operations.ids(operations.cars(path)))


def seed_copy_report(inputs: Path, masters: tuple[Path, ...]) -> list[str]:
    """Lines saying whether each master matches its copy in the STS seed inputs.

    The roster is compared as last built; publish and seed-copy rebuild it first.
    """
    if not inputs.is_dir():
        return ["  Cannot check: " + NO_SEED_DIR.format(path=inputs)]
    lines = []
    drift = False
    for master in masters:
        suffix = " (as last built)" if master == MERGED else ""
        if not master.is_file():
            lines.append(f"  {master.name}: master is missing")
            continue
        copy = inputs / master.name
        if not copy.is_file():
            state = "differs (copy is missing)"
            drift = True
        elif copy.read_bytes() == master.read_bytes():
            state = "same"
        else:
            state = "differs"
            drift = True
        lines.append(f"  {master.name}: {state}{suffix}")
    if drift:
        lines.append("  Bring them in step with: bin/cars seed-copy")
    return lines


# Field differences (compare): repository column -> the attribute the tool's writer sets.
# The expected value is what build_merged_car_roster.manifest_to_car makes from the row, so
# road code, number, type, length and colour are normalised exactly as the roster build does.
# A field is compared only when its repository column is filled in: manifest_to_car's defaults
# (40 or 90 ft, default weights) are not repository facts. Not compared: weight and weightTons,
# location, load, destination and position (STS owns them, ADR-016), the out-of-service flag
# (ADR-015, reported above) and the STS AAR code (derived from several rules, not one field).
# Operations Pro's car type is left out: it follows the STS car code, not car_type
# (docs/ops/OPSPRO_MAPPING.md, D14), and no writer code in the repository derives it.
ROSTER_FIELDS = {
    "roster_road": "roadName",
    "road_number": "roadNumber",
    "car_type": "type",
    "roster_length_ft": "length",
    "color": "color",
}
OPS_FIELDS = {c: a for c, a in ROSTER_FIELDS.items() if a != "type"}
# STS seed copy of image_metadata.csv: the columns generate_hart_seed.load_roster_metadata reads.
SEED_META_FIELDS = ("car_type", "car_class", "notes")
# sts_added_cars.csv: reporting_marks is road code + number; remarks is "{type} {length}ft"
# (generate_hart_seed.add_cars).
ADDED_FIELDS = {"reporting_marks": "marks", "remarks": "remarks"}
DIFF_LIMIT = 20
# The roster build skips only locomotives, so Operations Pro is compared for every other type.
# generate_hart_seed skips its PASSENGER_TYPES (passenger cars, cabooses, MOW) in add_cars.
OPS_SKIP_TYPES: frozenset[str] = frozenset()


def seed_helpers():
    """(generate_hart_seed, None), or (None, reason) when the sts-helpers submodule cannot load."""
    seed_dir = STS_HELPERS / "seed"
    if not (seed_dir / "generate_hart_seed.py").is_file():
        return None, NO_SEED_DIR.format(path=seed_dir)
    for path in (str(seed_dir), str(STS_HELPERS / "lib")):
        if path not in sys.path:
            sys.path.insert(0, path)
    try:
        import generate_hart_seed
    except (ImportError, AttributeError) as err:
        return None, f"{type(err).__name__}: {err}"
    return generate_hart_seed, None


def expected_cars(rows: list[CarRow], skip_types: frozenset[str]) -> dict[str, dict[str, str]]:
    """Roster attributes the build makes from each repository row, keyed by roster id.

    An attribute whose repository column is blank is dropped, not defaulted.
    """
    from build_merged_car_roster import manifest_to_car, normalize_roster_type
    from engine_lookup import is_locomotive_row

    out = {}
    for row in rows:
        ctype = (row.get("car_type") or "").strip()
        if is_locomotive_row(row) or ctype in ("Locomotive", "Streetcar"):
            continue
        if normalize_roster_type(ctype) in skip_types or ctype in skip_types:
            continue
        attrs = manifest_to_car(row)
        if not attrs:
            continue
        for column, attr in ROSTER_FIELDS.items():
            if attr != "roadName" and not (row.get(column) or "").strip():
                attrs.pop(attr, None)
        out[attrs["id"]] = attrs
    return out


def field_diffs(expected: dict[str, dict[str, str]], tool: dict[str, dict[str, str]], fields: dict[str, str]) -> list[FieldDiff]:
    """The differing fields of cars in both, over the mapped fields only.

    A field the repository leaves blank is skipped: the roster build keeps the tool's own value.
    """
    diffs: list[FieldDiff] = []
    for cid in sorted(expected.keys() & tool.keys()):
        for attr in fields.values():
            want = (expected[cid].get(attr) or "").strip()
            have = (tool[cid].get(attr) or "").strip()
            if want and want != have:
                diffs.append(FieldDiff(cid, attr, want, have))
    return diffs


def ops_car_attrs(path: Path) -> dict[str, dict[str, str]]:
    return {c.get("id", ""): dict(c.attrib) for c in operations.cars(path)}


def print_diffs(diffs: list[FieldDiff], show_all: bool) -> None:
    print(f"  Field differences: {len(diffs)}")
    shown = diffs if show_all else diffs[:DIFF_LIMIT]
    for cid, field, want, have in shown:
        print(f"    {cid} {field}: repo={want!r} tool={have!r}")
    if len(diffs) > len(shown):
        print(f"    +{len(diffs) - len(shown)} more (--all)")


def print_if_present(path: Path, show_all: bool, make_diffs) -> None:
    """Print make_diffs() for a tool file, or say the file is missing instead of reporting 0."""
    if not path.is_file():
        print(f"  Cannot check: {path} is missing")
        return
    print_diffs(make_diffs(), show_all)


def seed_meta_diffs(rows: list[CarRow], copy_path: Path, gen) -> list[FieldDiff]:
    """Differences between the repository and the STS seed copy of image_metadata.csv."""
    with copy_path.open(newline="", encoding="utf-8") as fh:
        copy_rows = {row_id(r): r for r in csv.DictReader(fh) if row_id(r)}
    reads = {
        "car_type": lambda r: gen.normalize_car_type(r.get("car_type") or ""),
        "car_class": gen.infer_car_class,
        "notes": lambda r: (r.get("notes") or "").strip(),
    }
    diffs: list[FieldDiff] = []
    for row in rows:
        cid = row_id(row)
        if cid not in copy_rows or "CarImagesFinal" not in (row.get("notes") or ""):
            continue
        if gen.normalize_car_type(row.get("car_type") or "") in gen.PASSENGER_TYPES:
            continue
        for field in SEED_META_FIELDS:
            want, have = reads[field](row), reads[field](copy_rows[cid])
            if want and want != have:
                diffs.append(FieldDiff(cid, field, want, have))
    return sorted(diffs)


def added_cars_diffs(rows: list[CarRow], added: dict[str, dict[str, str]], gen) -> list[FieldDiff]:
    """Differences between the repository and sts_added_cars.csv (marks and remarks)."""
    tool = {
        cid: {"marks": a.get("reporting_marks", ""), "remarks": a.get("remarks", "")}
        for cid, a in added.items()
    }
    want = {
        cid: {"marks": f"{a['roadName']}{a['roadNumber']}", "remarks": f"{a['type']} {a['length']}ft"}
        for cid, a in expected_cars(rows, frozenset(gen.PASSENGER_TYPES)).items()
        if a.get("type") and a.get("length")
    }
    return field_diffs(want, tool, ADDED_FIELDS)


def field_targets(rows: list[CarRow], ops_path: Path, gen) -> list[FieldTarget]:
    """Each tool file compared field by field, in print order.

    compare prints these and sync applies them, so both read the same differences. The STS
    entries are present only when the seed helpers loaded (gen) and the seed folder exists.
    """
    targets = [FieldTarget(
        "ops", "Operations Pro fields (OperationsCarRoster.xml, type left out)", ops_path,
        lambda: field_diffs(expected_cars(rows, OPS_SKIP_TYPES), ops_car_attrs(ops_path), OPS_FIELDS),
    )]
    if gen is None or not SEED_INPUTS.is_dir():
        return targets
    photos = {row_id(r) for r in rows if "CarImagesFinal" in (r.get("notes") or "")}
    sts_expected = expected_cars(
        [r for r in rows if row_id(r) in photos], frozenset(gen.PASSENGER_TYPES)
    )
    roster, meta = SEED_INPUTS / MERGED.name, SEED_INPUTS / METADATA.name
    added = SEED_INPUTS / "sts_added_cars.csv"
    return targets + [
        FieldTarget("seed_roster", "STS seed roster copy fields (HART_MergedCarRoster.xml; cars with a photo only)",
         roster, lambda: field_diffs(sts_expected, ops_car_attrs(roster), ROSTER_FIELDS)),
        FieldTarget("seed_meta", "STS seed metadata copy fields (image_metadata.csv)",
         meta, lambda: seed_meta_diffs(rows, meta, gen)),
        FieldTarget("added", "STS added cars fields (sts_added_cars.csv)",
         added, lambda: added_cars_diffs(rows, gen.load_added_cars(SEED_INPUTS), gen)),
    ]


def print_field_sections(rows: list[CarRow], ops_path: Path, show_all: bool) -> None:
    """Field differences for cars present in the repository and a tool (read only)."""
    gen, reason = seed_helpers()
    for _key, heading, path, make_diffs in field_targets(rows, ops_path, gen):
        print(f"\n{heading}:")
        print_if_present(path, show_all, make_diffs)
    if gen is None:
        print(f"\nCannot check STS sections: {reason}")
    elif not SEED_INPUTS.is_dir():
        print("\nCannot check STS sections: " + NO_SEED_DIR.format(path=SEED_INPUTS))


LIVE_STS_TIMEOUT = 20
OPERATING_SH = HART_ROOT / "tools/hosts/operating.sh"


class LiveStsError(RuntimeError):
    """The live section cannot run; the message says why. Never falls back to the seed."""


def operating_reason() -> str | None:
    """The operating flag's reason when it is set, else None (operating.sh status exits 0 when set)."""
    try:
        out = subprocess.run(
            [str(OPERATING_SH), "status"], capture_output=True, text=True, timeout=15, check=False
        )
    except (OSError, subprocess.SubprocessError) as err:
        raise LiveStsError(f"cannot read the operating flag ({err}); not touching the live STS") from err
    if out.returncode == 1:
        return None
    if out.returncode != 0:
        raise LiveStsError(f"cannot read the operating flag (exit {out.returncode}); not touching the STS")
    line = out.stdout.strip()
    return line.split("reason=", 1)[1] if "reason=" in line else (line or "set")


def target_is_local(url: str) -> bool:
    """The Mac's own STS (UAT or sandbox) is Mac-only work and stays open while operating."""
    return (urlsplit(url).hostname or "") in ("localhost", "127.0.0.1", "::1")


def target_url() -> str:
    return os.environ.get("STS_API_URL", "").strip() or "http://localhost:8980/sts/api/v1"


@contextlib.contextmanager
def capped_timeout(seconds: int):
    """sts_api waits up to an hour per request (for long tasks); a read here must not."""
    real = urllib.request.urlopen
    urllib.request.urlopen = lambda url, data=None, timeout=None, *a, **kw: real(
        url, data, seconds, *a, **kw
    )
    try:
        yield
    finally:
        urllib.request.urlopen = real


def load_sts_api():
    """The sts-helpers client, the one place cars.py imports it (and sts_paths beside it)."""
    helpers_lib = str(STS_HELPERS / "lib")
    if not (STS_HELPERS / "lib/sts_api.py").is_file():
        raise LiveStsError(NO_SEED_DIR.format(path=STS_HELPERS / "lib"))
    if helpers_lib not in sys.path:
        sys.path.insert(0, helpers_lib)
    import sts_api

    return sts_api


def fetch_live_cars() -> tuple[str, str, list[dict]]:
    """(url, stack, cars) from GET /health and GET /cars through the sts-helpers client.

    The URL is STS_API_URL (the caller sets it for this job only); GET requests only.
    """
    sts_api = load_sts_api()
    url = sts_api.base_url()
    try:
        with capped_timeout(LIVE_STS_TIMEOUT):
            health = sts_api.get("/health")
            cars = sts_api.get_all("/cars")
    except sts_api.ApiError as err:
        if err.code == "unreachable":
            raise LiveStsError(f"cannot reach STS at {url}: {err.message.split(': ', 1)[-1]}") from err
        raise LiveStsError(f"STS at {url} refused the read: {err}") from err
    except (OSError, ValueError, TypeError) as err:  # timeouts and bad bodies
        raise LiveStsError(f"cannot read STS at {url}: {type(err).__name__}: {err}") from err
    if not isinstance(health, dict):
        raise LiveStsError(f"STS at {url} gave an unexpected /health answer: {health!r}")
    return url, str(health.get("stack", "unknown")), cars


def live_sts_diffs(rows: list[CarRow], live: list[dict], passenger_types) -> list[FieldDiff]:
    """Differences between the repository and the live STS car list, keyed by reporting marks.

    Compared: remarks ("{type} {length}ft"), as the seed builds it. Reporting marks are the key.
    Not compared: position, load, status, job or destination (ADR-016).
    """
    tool = {c["reporting_marks"]: {"remarks": c.get("remarks") or ""} for c in live if c.get("reporting_marks")}
    want = {
        f"{a['roadName']}{a['roadNumber']}": {"remarks": f"{a['type']} {a['length']}ft"}
        for a in expected_cars(rows, frozenset(passenger_types)).values()
        if a.get("type") and a.get("length")
    }
    return field_diffs(want, tool, {"remarks": "remarks"})


def print_live_sts(rows: list[CarRow], show_all: bool, fetch=fetch_live_cars, operating=operating_reason) -> int:
    """The opt-in live STS section. Returns 0, or 2 when it could not run (nothing else is read instead)."""
    print("\nSTS API fields (GET /cars, read only):")
    try:
        if not target_is_local(target_url()):
            reason = operating()
            if reason:
                raise LiveStsError(f"the operating flag is set ({reason}); {target_url()} is not read")
        gen, why = seed_helpers()
        if gen is None:
            raise LiveStsError(f"cannot check: {why}")
        url, stack, live = fetch()
    except LiveStsError as err:
        print(f"  Cannot check the STS API: {err}")
        return 2
    print(f"  Target: {stack} ({url}), {len(live)} cars")
    marks = [c.get("reporting_marks") for c in live]
    seen = {m for m in marks if m}
    dups = sorted({m for m in seen if marks.count(m) > 1})
    if dups:
        print(f"  Duplicate reporting marks in the STS: {' '.join(dups)}")
    print_diffs(live_sts_diffs(rows, live, gen.PASSENGER_TYPES), show_all)
    repo_marks = {f"{a['roadName']}{a['roadNumber']}" for a in expected_cars(rows, frozenset()).values()}
    extra = sorted(seen - repo_marks)
    print(f"  In the live STS, not in the repository: {' '.join(extra) or 'none'}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    rows, _ = read_rows()
    master = {row_id(r) for r in rows if row_id(r)}
    locos = {
        row_id(r) for r in rows
        if (r.get("car_type") or "") in ("Locomotive", "Streetcar")
    }
    targets = {
        "Roster export": ops_ids(OPS),
        "Operations Pro": ops_ids(Path(args.ops_live)),
    }
    for name, ids in targets.items():
        missing = sorted(master - locos - ids)
        extra = sorted(ids - master)
        print(f"\n{name}: {len(ids)} cars")
        print(f"  Missing there: {len(missing)} {' '.join(missing)}")
        print(f"  Not in repository: {len(extra)} {' '.join(extra)}")
    print("\nSTS seed copies:")
    print("\n".join(seed_copy_report(SEED_INPUTS, SEED_COPIES)))
    marks = seed_marks()
    print(f"\nSTS seed: {len(marks)} cars")
    print(f"  Not in repository: {' '.join(sorted(marks - master)) or 'none'}")
    out = out_of_service_ids(rows)
    print(f"\nOut of service in the repository: {len(out)} {' '.join(sorted(out))}")
    live_flags = ops_out_of_service(Path(args.ops_live))
    print(f"  Operations Pro should add: {' '.join(sorted(out - live_flags)) or 'none'}")
    print(f"  Operations Pro should clear: {' '.join(sorted(live_flags - out)) or 'none'}")
    subprocess.run(
        [sys.executable, str(STS_HELPERS / "tools/sync_hart_status.py"), "--check"], check=False
    )
    photo_ids = {row_id(r) for r in rows if r.get("source_image")} - locos
    print(f"  Photographed cars not in STS: {' '.join(sorted(photo_ids - marks)) or 'none'}")
    show_all = getattr(args, "all", False)
    if getattr(args, "sts_url", None) and not getattr(args, "live_sts", False):
        print("--sts-url only applies together with --live-sts", file=sys.stderr)
        return 2
    print_field_sections(rows, Path(args.ops_live), show_all)
    if getattr(args, "live_sts", False):
        if getattr(args, "sts_url", None):
            os.environ["STS_API_URL"] = args.sts_url  # this run only
        return print_live_sts(rows, show_all)
    return 0


# sync (T10c): the repository's identity fields go to the tools that differ, for cars both hold.
# Position, load and destination are STS's (ADR-016) and are never sent. The live STS takes only
# `remarks` ("{type} {length}ft"): PATCH /cars/{id} is the API's one per-car update, and remarks is
# the only identity column compare reads there. A changed road or number would be a new reporting
# mark, which sync leaves to a person.
SYNC_BACKUP_PREFIX = "cars_sync_"


def update_ops_fields(path: Path, diffs: list[FieldDiff]) -> int:
    """Set only the differing attributes on existing cars, through the writer merge_ops uses."""
    tree = ET.parse(path)
    by_id = {c.get("id"): c for c in tree.getroot().findall("./cars/car")}
    for cid, attr, want, _have in diffs:
        by_id[cid].set(attr, want)
    write_ops(tree, path)
    return len(diffs)


SYNC_TARGETS = {
    "ops": "Operations Pro",
    "seed_roster": "STS seed roster copy",
    "seed_meta": "STS seed metadata copy",
}
SEED_WHOLESALE = (
    "  --apply replaces both STS seed copies wholesale, as seed-copy does "
    "(the roster is rebuilt first), not just the fields listed."
)
BACKUP_TIMEOUT = 120  # a database backup takes longer than a read


def sync_plan(rows: list[CarRow], ops_path: Path, live: list[dict] | None, gen) -> dict[str, list[FieldDiff]]:
    """Field differences per target, from the same field_targets compare prints."""
    plan: dict[str, list[FieldDiff]] = {}
    for key, _heading, path, make_diffs in field_targets(rows, ops_path, gen):
        if key in SYNC_TARGETS and path.is_file():
            plan[SYNC_TARGETS[key]] = make_diffs()
    if live is not None and gen is not None:
        plan["Live STS"] = live_sts_diffs(rows, live, gen.PASSENGER_TYPES)
    return plan


def seed_extra_changes() -> list[str]:
    """What replacing the seed copies would change beyond the listed fields: cars added or
    removed, and out-of-service flags (the roster as last built; seed-copy rebuilds it first)."""
    lines = []
    for master in SEED_COPIES:
        copy = SEED_INPUTS / master.name
        if not master.is_file():
            continue
        if not copy.is_file():
            lines.append(f"{master.name}: the copy is missing and would be created")
            continue

        def flags(path: Path) -> dict[str, str]:
            if path.suffix == ".csv":
                with path.open(newline="", encoding="utf-8") as fh:
                    return {row_id(r): r.get("out_of_service") or "" for r in csv.DictReader(fh) if row_id(r)}
            return {c.get("id", ""): c.get("outOfService") or ""
                    for c in operations.cars(path)}

        want, have = flags(master), flags(copy)
        for label, ids in (("added", sorted(want.keys() - have.keys())),
                           ("removed", sorted(have.keys() - want.keys())),
                           ("out_of_service changed", sorted(i for i in want.keys() & have.keys() if want[i] != have[i]))):
            if ids:
                lines.append(f"{master.name}: cars {label}: {' '.join(ids)}")
    return lines


def take_sts_backup(api, local: bool, now: float | None = None) -> str:
    """ADR-018: a backup under 12 hours old, else make one with POST /admin/backups.

    A folder on this Mac says nothing about the Pi, so a non-local STS always gets a new backup.
    """
    import publish_gate as gate
    import time

    backups = api.backups_dir()
    if local and not gate.backup_missing(backups, now):
        return f"a backup under {gate.BACKUP_MAX_AGE_HOURS} hours old is in {backups}"
    name = f"{SYNC_BACKUP_PREFIX}{int(time.time() if now is None else now)}"
    try:
        with capped_timeout(BACKUP_TIMEOUT):
            api.post("/admin/backups", {"name": name})
    except api.ApiError as err:
        raise LiveStsError(f"could not take an STS backup first ({err})") from err
    except (OSError, ValueError, TypeError) as err:
        raise LiveStsError(f"could not take an STS backup first ({type(err).__name__}: {err})") from err
    return f"took STS backup {name}"


def write_live_cars(api, live: list[dict], diffs: list[FieldDiff]) -> list[str]:
    """PATCH one car at a time and read it back; stops at the first problem."""
    by_marks: dict[str, list[dict]] = {}
    for car in live:
        by_marks.setdefault(car.get("reporting_marks") or "", []).append(car)
    done: list[str] = []

    def stop(marks: str, why: str) -> LiveStsError:
        return LiveStsError(f"sync stopped at car {marks}: {why}; written so far: {' '.join(done) or 'none'}")

    for marks, field, want, _have in diffs:
        found = by_marks.get(marks, [])
        if len(found) != 1:
            raise stop(marks, f"{len(found)} STS cars have these reporting marks")
        car_id = found[0]["id"]
        try:
            with capped_timeout(LIVE_STS_TIMEOUT):
                api.patch(f"/cars/{car_id}", {field: want})
                back = api.get(f"/cars/{car_id}")
        except api.ApiError as err:
            raise stop(marks, str(err)) from err
        except (OSError, ValueError, TypeError) as err:
            raise stop(marks, f"{type(err).__name__}: {err}") from err
        if isinstance(back, dict) and isinstance(back.get("data"), dict):
            back = back["data"]  # an envelope, if the client ever hands one back
        got = back.get(field) if isinstance(back, dict) else back
        if (got or "") != want:
            raise stop(marks, f"read back {field}={got!r}, wanted {want!r}")
        done.append(marks)
    return done


def seed_preflight() -> None:
    """Everything the seed refresh needs, checked before the first write of a sync."""
    if not SEED_INPUTS.is_dir():
        raise LiveStsError(NO_SEED_DIR.format(path=SEED_INPUTS))
    if not METADATA.is_file():
        raise LiveStsError(f"Master file is missing: {METADATA}")
    try:
        import build_car_roster_sor  # noqa: F401
    except ImportError as err:
        raise LiveStsError(f"the roster build cannot run ({err})") from err


def cmd_sync(args: argparse.Namespace) -> int:
    """Dry run by default. --apply writes Operations Pro, replaces the STS seed copies and,
    with --live-sts --sts-url, patches the STS."""
    apply = getattr(args, "apply", False)
    use_live = getattr(args, "live_sts", False)
    url = getattr(args, "sts_url", None)
    if url and not use_live:
        print("--sts-url only applies together with --live-sts", file=sys.stderr)
        return 2
    if apply and use_live and not url:
        print("--apply with --live-sts needs --sts-url URL (the live STS is never a default)", file=sys.stderr)
        return 2
    if url:
        os.environ["STS_API_URL"] = url  # this run only
    rows, _ = read_rows()
    gen, why = seed_helpers()
    if gen is None:
        print(f"Cannot check the STS targets: {why}")
    live = None
    local = True
    if use_live:
        local = target_is_local(target_url())
        try:
            if not local:
                reason = operating_reason()
                if reason:
                    raise LiveStsError(f"the operating flag is set ({reason}); {target_url()} is not touched")
            _url, _stack, live = fetch_live_cars()
        except LiveStsError as err:
            print(f"Cannot use the live STS: {err}", file=sys.stderr)
            return 2
    ops_path = Path(args.ops_live)
    plan = sync_plan(rows, ops_path, live, gen)
    total = 0
    for target, diffs in plan.items():
        print(f"{target}: {len(diffs)} change(s)")
        for cid, field, want, have in diffs:
            print(f"    {cid} {field}: {have!r} -> {want!r}")
        total += len(diffs)
    ops_diffs = plan.get("Operations Pro", [])
    seed_diffs = plan.get("STS seed roster copy", []) + plan.get("STS seed metadata copy", [])
    live_diffs = plan.get("Live STS", [])
    if seed_diffs:
        print(SEED_WHOLESALE)
        for line in seed_extra_changes():
            print(f"    also changes: {line}")
    if not use_live:
        print("Live STS: not checked (add --live-sts --sts-url URL)")
    if not total:
        print("Nothing to do: the repository and the tools agree.")
        return 0
    if not apply:
        print("Dry run: nothing was written. Add --apply to write.")
        return 0

    sts_api = None
    try:  # every refusal comes before the first write
        if ops_diffs:
            import publish_gate as gate

            if ops_path.resolve() != OPS_MERGED.resolve():
                raise LiveStsError(f"--apply only edits the repo roster {OPS_MERGED}, not {ops_path}")
            problems = gate.pi_out_of_step(OPS_MERGED.parent, PI_HOST, PI_OPS_DIR)
            if problems:
                raise LiveStsError("; ".join(problems))
        if seed_diffs:
            seed_preflight()
        if live_diffs:
            sts_api = load_sts_api()
            if not local:
                reason = operating_reason()
                if reason:
                    raise LiveStsError(f"the operating flag is set ({reason}); {target_url()} is not touched")
            print("  " + take_sts_backup(sts_api, local))
    except LiveStsError as err:
        print(f"Sync stopped, nothing written: {err}", file=sys.stderr)
        return 2
    if seed_diffs:
        from build_car_roster_sor import main as build_roster

        build_roster()
        sync_seed_copies(SEED_INPUTS, SEED_COPIES)
    if ops_diffs:
        update_ops_fields(ops_path, ops_diffs)
        print(f"Updated {len(ops_diffs)} attribute(s) in {ops_path}. {DEPLOY_NOTE}")
    if live_diffs:
        try:
            done = write_live_cars(sts_api, live, live_diffs)
        except LiveStsError as err:
            print(err, file=sys.stderr)
            return 2
        print(f"Updated {len(done)} live STS car(s), each read back: {' '.join(done)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("import-legacy").set_defaults(run=cmd_import_legacy)
    for name, run in (("intake", cmd_intake), ("add", cmd_add)):
        p = sub.add_parser(name)
        p.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE")
        p.add_argument("--yes", action="store_true", help="Do not ask questions")
        p.set_defaults(run=run)
    p = sub.add_parser("review")
    p.add_argument("--batch", help="Batch name (default: today's date)")
    p.set_defaults(run=stage("intake_stages", "cmd_review"))
    p = sub.add_parser("ai-notes")
    p.add_argument("batch")
    p.add_argument("file", help="JSON: {photo: {marks, number, type, note}}")
    p.set_defaults(run=stage("intake_stages", "cmd_ai_notes"))
    p = sub.add_parser("kind")
    p.add_argument("batch")
    p.add_argument("kind", choices=["car", "loco"])
    p.add_argument("photos", nargs="+")
    p.set_defaults(run=stage("intake_stages", "cmd_kind"))
    p = sub.add_parser("approve")
    p.add_argument("batch")
    p.add_argument("--no-ai", action="store_true", help="Approve without the AI review step")
    p.set_defaults(run=stage("intake_stages", "cmd_approve"))
    p = sub.add_parser("fill")
    p.add_argument("batch")
    p.add_argument("--set", action="append", metavar="COLUMN=VALUE", help="Set a column on every row")
    p.set_defaults(run=stage("intake_stages", "cmd_fill"))
    p = sub.add_parser("sheet-import")
    p.add_argument("batch")
    p.add_argument("file", help="review.csv downloaded from the review page")
    p.set_defaults(run=stage("intake_stages", "cmd_sheet_import"))
    p = sub.add_parser("crop", help="Crop picker on the review page, or re-cut one photo")
    p.add_argument("batch")
    p.add_argument("photo", nargs="?")
    p.add_argument("box", nargs="?", metavar="X,Y,W,H[,ANGLE]")
    p.add_argument("--refresh", action="store_true", help="Rebuild the picker views")
    p.set_defaults(run=stage("crop_picker", "cmd_crop"))
    p = sub.add_parser("records")
    p.add_argument("batch")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--allow-pending", action="store_true", help="Record approved rows while others wait")
    p.set_defaults(run=stage("intake_stages", "cmd_records"))
    p = sub.add_parser("site")
    p.add_argument("--apply", action="store_true", help="Write the entries (default: show them)")
    p.set_defaults(run=stage("site_gallery", "cmd_site"))
    p = sub.add_parser("locos")
    p.add_argument("action", choices=["add", "set", "status", "publish"])
    p.add_argument("roster_id", nargs="?")
    p.add_argument("fields", nargs="*", metavar="FIELD=VALUE")
    p.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(run=cmd_locos)
    sub.add_parser("status").set_defaults(run=cmd_status)
    p = sub.add_parser("cards")
    p.add_argument("--mark-printed", action="store_true")
    p.add_argument("--trains", action="store_true",
                   help="append the train cards (D749, NVL, CK1, Route 23, OCS-1, EXTRA)")
    p.set_defaults(run=cmd_cards)
    p = sub.add_parser("service")
    p.add_argument("state", choices=["out", "in"])
    p.add_argument("roster_ids", nargs="+")
    p.set_defaults(run=cmd_service)
    p = sub.add_parser("publish")
    p.add_argument("--ops-live", default=str(OPS_MERGED))
    p.add_argument("--only", nargs="+", metavar="ROSTER_ID",
                   help="Publish just these queued cars (testing one at a time)")
    p.add_argument("--skip-check", action="append", default=[], metavar="NAME",
                   help="Skip a gate check: batches, committed, pi or backup")
    p.set_defaults(run=cmd_publish)
    p = sub.add_parser("fix-ops")
    p.add_argument("--ops-live", default=str(OPS_MERGED))
    p.set_defaults(run=cmd_fix_ops)
    sub.add_parser("seed-copy").set_defaults(run=cmd_seed_copy)
    p = sub.add_parser("compare")
    p.add_argument("--ops-live", default=str(OPS_MERGED))
    p.add_argument("--all", action="store_true", help="List every field difference, not the first 20")
    p.add_argument("--live-sts", action="store_true",
                   help="Also read the live STS cars over its API (GET only; refused while the operating flag is set)")
    p.add_argument("--sts-url", metavar="URL",
                   help="STS API base URL for this run, e.g. http://RPi-JMRI.local:8980/sts/api/v1 "
                        "(else STS_API_URL, else the Mac UAT)")
    p.set_defaults(run=cmd_compare)
    p = sub.add_parser("sync", help="Send the repository's identity fields to the tools that differ")
    p.add_argument("--ops-live", default=str(OPS_MERGED))
    p.add_argument("--apply", action="store_true", help="Write the changes (default: show them); the STS seed copies are replaced wholesale, as seed-copy does")
    p.add_argument("--live-sts", action="store_true", help="Include the live STS (with --apply, also needs --sts-url)")
    p.add_argument("--sts-url", metavar="URL", help="STS API base URL for this run")
    p.set_defaults(run=cmd_sync)
    args = parser.parse_args()
    try:
        return args.run(args)
    except CardPipelineError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
