#!/usr/bin/env python3
"""Generate filled HART car cards for every row in image_metadata.csv.

Reads cropped images from CarImagesCardFill/ (then CarImagesFinal/, then CarImages/), sticker-sheet layout
(9 cards per page), and writes a single review document.
"""

from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import operations  # noqa: E402

from docx import Document
from docx.table import Table

import car_paths
import card_template_layout
import card_template_sheet
import generate_card_template as g
from engine_lookup import (
    ROAD_DISPLAY,
    build_locomotive_description,
    is_locomotive_row,
    load_engine_roster,
    match_engine,
)
from card_description import build_freight_description, normalize_car_type, format_type_label as format_type

BASE = car_paths.ROOT
DATA = car_paths.DATA
OUTPUT_DIR = car_paths.OUTPUT_DIR
ASSETS = car_paths.ASSETS
METADATA_CSV = DATA / "image_metadata.csv"
ROSTER_XML = DATA / "OperationsCarRoster.xml"
OUTPUT = OUTPUT_DIR / "HART_All_Car_Cards.docx"
CARDS_PER_PAGE = len(card_template_layout.CARD_SLOTS)

# Omit from print sheet — unidentified / decorative cars kept in manifest for review only.
EXCLUDE_FROM_DOC: frozenset[str] = frozenset({"IMG_9152.png"})

# Known-good override for the manually verified flatcar photo.
IMG_9088_OVERRIDE = {
    "roster_id": "NW32800",
    "image": ASSETS / "NW32800.png",
    "record": {
        "Type": "Flat Car",
        "RoadName": "N&W",
        "RoadNumber": "32800",
        "Description": "Flatcar \u00b7 52'",
    },
}


def load_roster() -> dict[str, dict]:
    cars: dict[str, dict] = {}
    for el in operations.cars(ROSTER_XML):
        cars[el.get("id", "")] = {
            "roster_id": el.get("id", ""),
            "roster_road": el.get("roadName", ""),
            "road_number": el.get("roadNumber", ""),
            "car_type": el.get("type", ""),
            "roster_length_ft": el.get("length", ""),
        }
    return cars


def format_description(row: dict, car: dict | None, engine_by_key: dict | None = None) -> str:
    if is_locomotive_row(row):
        if engine_by_key is None:
            _, engine_by_key = load_engine_roster()
        engine = match_engine(row, engine_by_key)
        desc = build_locomotive_description(engine, row)
        if desc:
            return desc
    return build_freight_description(row, car)


def display_road(row: dict, engine_by_key: dict) -> str:
    roster_id = row.get("roster_id", "").strip()
    if roster_id:
        road = row.get("roster_road", "").strip()
        return ROAD_DISPLAY.get(road, road) or "?"

    marks = (row.get("reporting_marks") or row.get("road_name") or "").strip()
    if marks:
        return marks

    engine = match_engine(row, engine_by_key)
    if engine:
        road = engine.get("roster_road", "")
        return ROAD_DISPLAY.get(road, road) or marks or "?"

    return "?"


def display_road_number(row: dict, car: dict | None, engine_by_key: dict) -> str:
    if car and car.get("road_number"):
        return car["road_number"]

    engine = match_engine(row, engine_by_key)
    if engine and engine.get("road_number"):
        return engine["road_number"]

    if row.get("roster_id", "").strip():
        number = row.get("road_number", "").strip()
        return number if number else "?"

    number = row.get("road_number", "").strip()
    return number if number else "?"


FINAL_DIR = car_paths.FINAL_DIR  # the folder finalize_car_images.py writes
CARD_FILL_DIR = BASE / "CarImagesCardFill"
CARD_FILL_PRINT_DIR = BASE / "CarImagesCardFillPrint"


def resolve_image(row: dict) -> Path | None:
    if "IMG_9088" in row.get("source_image", ""):
        override = IMG_9088_OVERRIDE["image"]
        if override.exists():
            return override
    stem = Path(row.get("source_image", "")).stem
    if stem:
        for folder in (CARD_FILL_PRINT_DIR, CARD_FILL_DIR, FINAL_DIR):
            path = folder / f"{stem}.png"
            if path.exists():
                return path
    rel = row.get("cropped_image", "").strip()
    if rel:
        path = BASE / rel
        if path.exists():
            return path
    return None


def row_to_card(row: dict, roster: dict[str, dict], engine_by_key: dict) -> tuple[dict, Path | None]:
    if "IMG_9088" in row.get("source_image", ""):
        return IMG_9088_OVERRIDE["record"].copy(), IMG_9088_OVERRIDE["image"]

    car = roster.get(row.get("roster_id", ""))
    ctype = normalize_car_type(row.get("car_type") or (car or {}).get("car_type", ""))
    record = {
        "Type": format_type(ctype),
        "RoadName": display_road(row, engine_by_key),
        "RoadNumber": display_road_number(row, car, engine_by_key),
        "Description": format_description(row, car, engine_by_key),
    }
    return record, resolve_image(row)


def load_cards() -> list[tuple[dict, Path | None, dict]]:
    roster = load_roster()
    _, engine_by_key = load_engine_roster()
    cards: list[tuple[dict, Path | None, dict]] = []
    with METADATA_CSV.open(newline="") as f:
        for row in csv.DictReader(f):
            if row.get("source_image", "") in EXCLUDE_FROM_DOC:
                continue
            if not row.get("source_image", "").strip():
                continue  # No photo yet; cars.py queues these cards.
            record, image = row_to_card(row, roster, engine_by_key)
            cards.append((record, image, row))
    return cards


def _fill_page(sheet: Table, batch: list[tuple[dict, Path | None, dict]], page_idx: int) -> None:
    for i, (record, image, _row) in enumerate(batch):
        r, c = card_template_layout.CARD_SLOTS[i]
        g.build_card(
            sheet.rows[r].cells[c],
            advance_record=False,
            idx=page_idx * CARDS_PER_PAGE + i,
            record=record,
            image_path=image,
        )


def generate(cards: list[tuple[dict, Path | None, dict]]) -> None:
    car_paths.require_sticker_sheet()
    if not METADATA_CSV.exists():
        raise FileNotFoundError(METADATA_CSV)

    blank_grid = card_template_sheet.blank_sticker_grid(car_paths.STICKER_SHEET)
    shutil.copy2(car_paths.STICKER_SHEET, OUTPUT)
    doc = Document(OUTPUT)
    card_template_sheet.keep_sticker_grid(doc)

    pages = [
        cards[i : i + CARDS_PER_PAGE]
        for i in range(0, len(cards), CARDS_PER_PAGE)
    ]

    sheet = doc.tables[0]
    _fill_page(sheet, pages[0], 0)

    for page_idx, batch in enumerate(pages[1:], start=1):
        sheet = card_template_sheet.append_grid(doc, blank_grid)
        _fill_page(sheet, batch, page_idx)

    card_template_sheet.add_document_tail(doc.element.body)
    doc.save(OUTPUT)


def main() -> None:
    cards = load_cards()
    generate(cards)

    with_image = sum(1 for _, img, _ in cards if img)
    matched = sum(1 for _, _, row in cards if row.get("roster_id"))
    pages = (len(cards) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE

    print(f"Wrote {OUTPUT}")
    print(f"  {len(cards)} cards · {pages} pages · {with_image} with photos")
    print(f"  {matched} roster matches (review remaining in the doc)")


if __name__ == "__main__":
    try:
        main()
    except car_paths.CardPipelineError as exc:
        raise SystemExit(str(exc)) from exc
