"""Cars into the repository: new photos (intake), the questionnaire (add), the roster import, and the stage dispatcher.

The intake stage modules (intake_stages, crop_picker, site_gallery) get the repository reads and the
per-photo steps through ``intake_context``, built at call time.
"""
from __future__ import annotations

import argparse
import importlib
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

from car_repo import (
    IMAGE_SUFFIXES, OPS, as_fields, ask, blank_row, enqueue, find_car, finish_row, merge_car, parse_sets,
    read_queue, read_rows, row_id, write_queue, write_rows,
)
from car_paths import FINAL_DIR, IMAGES_DIR, CardPipelineError
from car_records import CarRow, IntakeContext, MergeOutcome, QueueItem
from hartlib import operations

# Repository columns a stage 2 car row copies from the review sheet as they are.
RECORD_COLUMNS = ("road_number", "car_type", "car_class", "color", "roster_length_ft",
                  "capy_lbs", "ld_lmt_lbs", "lt_wt_lbs", "built", "full_name", "ocr_text")


def legacy_row(car: Mapping[str, str], columns: list[str]) -> CarRow:
    """A repository row for one Operations Pro roster car that has no photo."""
    row = blank_row(columns)
    as_fields(row).update({
        "reporting_marks": car.get("roadName", ""),
        "road_name": car.get("roadName", ""),
        "road_number": car.get("roadNumber", ""),
        "car_type": car.get("type", ""),
        "color": car.get("color", ""),
        "roster_id": car.get("id", ""),
        "roster_road": car.get("roadName", ""),
        "roster_length_ft": car.get("length", ""),
        "roster_weight_oz": car.get("weight", ""),
        "roster_weight_tons": car.get("weightTons", ""),
        "match_confidence": "operations-pro",
        "notes": "No photo yet",
    })
    return row


def cmd_import_legacy(_args: argparse.Namespace) -> int:
    """Bring roster-only cars into the repository so it holds the whole fleet."""
    rows, columns = read_rows()
    known = {row_id(r) for r in rows}
    added = 0
    for car in operations.cars(OPS):
        if car.get("id", "") in known:
            continue
        rows.append(legacy_row(car.attrib, columns))
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


def merge_message(roster_id: str, outcome: MergeOutcome, existing_image: str) -> str:
    """The intake line for one merged photo."""
    if outcome is MergeOutcome.NEW_CAR:
        return f"  Added {roster_id}"
    if outcome is MergeOutcome.SKIPPED:
        return f"  {roster_id} already has {existing_image}; skipped."
    return f"  Added the photo to {roster_id}"


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
        row = blank_row(columns)
        as_fields(row).update(fields)
        ask(row, values, args.yes)
        merged = merge_car(row, rows, columns, queue, dry_run=False)
        print(merge_message(*merged))
        write_rows(rows, columns)
        write_queue(queue)
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    rows, columns = read_rows()
    queue = read_queue()
    row = blank_row(columns)
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
    row = blank_row(columns)
    photo = Path(r["photo"])
    fields = as_fields(row)
    fields.update(
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
    for key in RECORD_COLUMNS:
        fields[key] = r.get(key, "")
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
        command: Callable[[argparse.Namespace, IntakeContext], int] = getattr(importlib.import_module(module), name)
        return command(args, intake_context())

    return run
