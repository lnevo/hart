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
    cars.py compare         Report differences between the repository and each tool

``data/image_metadata.csv`` is the repository: one row per car, with a blank
``source_image`` until the car is photographed. ``data/car_queue.csv`` tracks
which new cars still need a card, STS or Operations Pro.
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent
HART_ROOT = PIPELINE.parents[2]
os.environ.setdefault("HART_CAR_CARDS_ROOT", str(HART_ROOT / "ops/car-cards"))

from car_paths import DATA, FINAL_DIR, IMAGES_DIR, OUTPUT_DIR, ROOT  # noqa: E402

METADATA = DATA / "image_metadata.csv"
QUEUE = DATA / "car_queue.csv"
MERGED = DATA / "HART_MergedCarRoster.xml"
OPS = DATA / "OperationsCarRoster.xml"
# ADR-015: the repo copy is the master; the deploy installs it on the hosts.
OPS_MERGED = HART_ROOT / "jmri/layouts/hart/operations/OperationsCarRoster.xml"
STS_HELPERS = HART_ROOT / "external/sts-helpers"
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


def read_rows() -> tuple[list[dict], list[str]]:
    with METADATA.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader), list(reader.fieldnames or [])


def write_rows(rows: list[dict], columns: list[str]) -> None:
    tmp = METADATA.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(METADATA)


def read_queue() -> list[dict]:
    if not QUEUE.is_file():
        return []
    with QUEUE.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_queue(queue: list[dict]) -> None:
    with QUEUE.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=QUEUE_COLUMNS)
        writer.writeheader()
        writer.writerows(queue)


def enqueue(queue: list[dict], roster_id: str, reason: str) -> None:
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


def row_id(row: dict) -> str:
    from roster_id import manifest_car_id

    return manifest_car_id(row)


def find_car(rows: list[dict], roster_id: str) -> dict | None:
    return next((r for r in rows if row_id(r) == roster_id), None)


def parse_sets(pairs: list[str]) -> dict[str, str]:
    values = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"--set needs field=value, got {pair!r}")
        key, value = pair.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def ask(row: dict, values: dict[str, str], assume_yes: bool) -> None:
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


def finish_row(row: dict, columns: list[str]) -> str:
    """Fill the derived fields and return the roster id."""
    from build_merged_car_roster import ROSTER_TYPO_IDS, default_weights
    from roster_id import assign_freight_roster_id

    row["road_name"] = row.get("road_name") or row.get("reporting_marks", "")
    row["roster_id"] = ""
    row["roster_road"] = ""
    assign_freight_roster_id(row)
    roster_id = row.get("roster_id", "")
    if not roster_id:
        raise SystemExit("A car needs reporting marks and a road number.")
    if roster_id in ROSTER_TYPO_IDS:
        raise SystemExit(f"{roster_id} is a recorded misread road number; check the car.")
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
    for car in ET.parse(OPS).getroot().findall("./cars/car"):
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


def process_photo(png: Path) -> dict:
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
        raise SystemExit(f"Could not finalize {png.name}")
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


def new_photos(rows: list[dict]) -> list[Path]:
    seen = {Path(r["source_image"]).stem for r in rows if r.get("source_image")}
    return sorted(
        p
        for p in IMAGES_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES and p.stem not in seen
    )


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
        row = {c: "" for c in columns}
        row.update(fields)
        ask(row, values, args.yes)
        roster_id = finish_row(row, columns)
        existing = find_car(rows, roster_id)
        if existing is None:
            rows.append(row)
            enqueue(queue, roster_id, "new car")
            print(f"  Added {roster_id}")
        elif existing.get("source_image"):
            print(f"  {roster_id} already has {existing['source_image']}; skipped.")
        else:
            for key, value in row.items():
                if value:
                    existing[key] = value
            enqueue(queue, roster_id, "photo added")
            print(f"  Added the photo to {roster_id}")
        write_rows(rows, columns)
        write_queue(queue)
    return 0


def guess_roster_id(review_row: dict, kind: str) -> str:
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


def record_car(r: dict, rows: list[dict], columns: list[str], queue: list[dict], dry_run: bool) -> str:
    """Stage 2 for one approved car row, the same writes as ``intake`` makes."""
    row = {c: "" for c in columns}
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
    roster_id = finish_row(row, columns)
    existing = find_car(rows, roster_id)
    if existing is None:
        if not dry_run:
            rows.append(row)
            enqueue(queue, roster_id, "new car")
        return f"new car {roster_id}"
    if existing.get("source_image"):
        return f"skipped: {roster_id} already has {existing['source_image']}"
    if not dry_run:
        for key, value in row.items():
            if value:
                existing[key] = value
        enqueue(queue, roster_id, "photo added")
    return f"photo added to {roster_id}"


def record_loco(r: dict, dry_run: bool) -> str:
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


def cmd_review(args: argparse.Namespace) -> int:
    import intake_stages

    return intake_stages.cmd_review(args, sys.modules[__name__])


def cmd_approve(args: argparse.Namespace) -> int:
    import intake_stages

    return intake_stages.cmd_approve(args, sys.modules[__name__])


def cmd_ai_notes(args: argparse.Namespace) -> int:
    import intake_stages

    return intake_stages.cmd_ai_notes(args, sys.modules[__name__])


def cmd_kind(args: argparse.Namespace) -> int:
    import intake_stages

    return intake_stages.cmd_kind(args, sys.modules[__name__])


def cmd_fill(args: argparse.Namespace) -> int:
    import intake_stages

    return intake_stages.cmd_fill(args, sys.modules[__name__])


def cmd_sheet_import(args: argparse.Namespace) -> int:
    import intake_stages

    return intake_stages.cmd_sheet_import(args, sys.modules[__name__])


def cmd_crop(args: argparse.Namespace) -> int:
    import crop_picker

    return crop_picker.cmd_crop(args, sys.modules[__name__])


def cmd_records(args: argparse.Namespace) -> int:
    import intake_stages

    return intake_stages.cmd_records(args, sys.modules[__name__])


def cmd_site(args: argparse.Namespace) -> int:
    import site_gallery

    return site_gallery.cmd_site(args, sys.modules[__name__])


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
        raise SystemExit(f"{roster_id} is already in the repository.")
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
            raise SystemExit(f"Queued car {item['roster_id']} is not in the repository.")
        record, image = gen.row_to_card(row, roster, engines)
        cards.append((record, image, row))
        print(f"  {record['RoadName']} {record['RoadNumber']}: {'photo' if image else 'no photo'}")
    loco_rows = {r["roster_id"]: r for r in locos.read_locos()}
    for item in loco_pending:
        loco = loco_rows.get(item["roster_id"])
        if loco is None:
            raise SystemExit(f"Queued loco {item['roster_id']} is not in the locomotive repository.")
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


def out_of_service_ids(rows: list[dict]) -> set[str]:
    """The cars the repository holds out of service. STS and Operations Pro follow this."""
    return {row_id(r) for r in rows if r.get("out_of_service") == "yes"}


def ops_out_of_service(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    return {
        c.get("id", "") for c in ET.parse(path).getroot().findall("./cars/car")
        if c.get("outOfService") == "true"
    }


def merge_ops(
    live_path: Path,
    wanted: list[str],
    renames: dict[str, str] | None = None,
    out_of_service: set[str] | None = None,
) -> list[str]:
    """Add cars to the Operations Pro roster, leaving every other car alone.

    Renames correct a car's identity in place, so its location and moves survive.
    When out_of_service is given, every car's flag is set to match it.
    """
    tree = ET.parse(live_path)
    root = tree.getroot()
    cars_el = root.find("cars")
    have = {c.get("id") for c in cars_el.findall("car")}
    source = {c.get("id"): c for c in ET.parse(MERGED).getroot().findall("./cars/car")}
    for car in cars_el.findall("car"):
        new_id = (renames or {}).get(car.get("id"))
        if not new_id:
            continue
        if new_id in have:
            raise SystemExit(f"{car.get('id')} and {new_id} are both in the roster; check by hand.")
        if new_id not in source:
            raise SystemExit(f"{new_id} is missing from {MERGED.name}")
        for attr in ("id", "roadName", "roadNumber", "color"):
            if source[new_id].get(attr):
                car.set(attr, source[new_id].get(attr))
        add_to_sections(root, car)
        have.discard(car.get("id"))
        have.add(new_id)
    added = []
    for roster_id in wanted:
        if roster_id in have:
            continue
        if roster_id not in source:
            raise SystemExit(f"{roster_id} is missing from {MERGED.name}")
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
        print("Publish stopped:", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        raise SystemExit(1)


def cmd_publish(args: argparse.Namespace) -> int:
    from build_car_roster_sor import main as build_roster

    publish_gate(args)
    build_roster()
    queue = read_queue()
    if args.only:
        unknown = [i for i in args.only if i not in {q["roster_id"] for q in queue}]
        if unknown:
            raise SystemExit(f"Not in the queue: {' '.join(unknown)}")

    def chosen(item: dict) -> bool:
        """With --only, the rest of the queue is left exactly as it is."""
        return not args.only or item["roster_id"] in args.only

    inputs = STS_HELPERS / "seed/inputs"
    shutil.copy2(METADATA, inputs / METADATA.name)
    shutil.copy2(MERGED, inputs / MERGED.name)
    print(f"Copied the repository and roster to {inputs}")

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
            raise SystemExit(f"{roster_id} is not in the repository.")
        for row in matches:
            row["out_of_service"] = "yes" if args.state == "out" else ""
    write_rows(rows, columns)
    print(f"Marked {args.state} of service: {' '.join(args.roster_ids)}. Run publish to send it.")
    return 0


def cmd_fix_ops(args: argparse.Namespace) -> int:
    """Bring the Operations Pro roster up to the repository. Leaves STS and the queue alone."""
    from build_car_roster_sor import main as build_roster
    from build_merged_car_roster import ROSTER_TYPO_IDS

    build_roster()
    rows, _ = read_rows()
    live = Path(args.ops_live)
    current = ops_ids(live)
    renames = {old: new for old, new in ROSTER_TYPO_IDS.items() if old in current}
    wanted = sorted(
        row_id(r) for r in rows
        if row_id(r) and (r.get("car_type") or "") not in ("Locomotive", "Streetcar")
    )
    added = merge_ops(live, wanted, renames, out_of_service_ids(rows))
    print(f"Renamed {len(renames)}: {' '.join(f'{o}>{n}' for o, n in renames.items())}")
    print(f"Added {len(added)}: {' '.join(added)}")
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
    return {c.get("id", "") for c in ET.parse(path).getroot().findall("./cars/car")}


def cmd_compare(args: argparse.Namespace) -> int:
    from build_merged_car_roster import ROSTER_TYPO_IDS

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
        typos = [i for i in extra if i in ROSTER_TYPO_IDS]
        print(f"\n{name}: {len(ids)} cars")
        print(f"  Missing there: {len(missing)} {' '.join(missing)}")
        print(f"  Not in repository: {len(extra)} {' '.join(extra)}")
        if typos:
            print(f"  Recorded misreads: {' '.join(typos)}")
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
    p.set_defaults(run=cmd_review)
    p = sub.add_parser("ai-notes")
    p.add_argument("batch")
    p.add_argument("file", help="JSON: {photo: {marks, number, type, note}}")
    p.set_defaults(run=cmd_ai_notes)
    p = sub.add_parser("kind")
    p.add_argument("batch")
    p.add_argument("kind", choices=["car", "loco"])
    p.add_argument("photos", nargs="+")
    p.set_defaults(run=cmd_kind)
    p = sub.add_parser("approve")
    p.add_argument("batch")
    p.add_argument("--no-ai", action="store_true", help="Approve without the AI review step")
    p.set_defaults(run=cmd_approve)
    p = sub.add_parser("fill")
    p.add_argument("batch")
    p.add_argument("--set", action="append", metavar="COLUMN=VALUE", help="Set a column on every row")
    p.set_defaults(run=cmd_fill)
    p = sub.add_parser("sheet-import")
    p.add_argument("batch")
    p.add_argument("file", help="review.csv downloaded from the review page")
    p.set_defaults(run=cmd_sheet_import)
    p = sub.add_parser("crop", help="Crop picker on the review page, or re-cut one photo")
    p.add_argument("batch")
    p.add_argument("photo", nargs="?")
    p.add_argument("box", nargs="?", metavar="X,Y,W,H[,ANGLE]")
    p.add_argument("--refresh", action="store_true", help="Rebuild the picker views")
    p.set_defaults(run=cmd_crop)
    p = sub.add_parser("records")
    p.add_argument("batch")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--allow-pending", action="store_true", help="Record approved rows while others wait")
    p.set_defaults(run=cmd_records)
    p = sub.add_parser("site")
    p.add_argument("--apply", action="store_true", help="Write the entries (default: show them)")
    p.set_defaults(run=cmd_site)
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
    p = sub.add_parser("compare")
    p.add_argument("--ops-live", default=str(OPS_MERGED))
    p.set_defaults(run=cmd_compare)
    args = parser.parse_args()
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
