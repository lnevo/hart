#!/usr/bin/env python3
"""Generate filled HART car cards for every row in image_metadata.csv.

Reads cropped images from CarImagesCardFillPrint/, CarImagesCardFill/ and CarImagesFinal/ (then the row's
cropped_image), sticker-sheet layout (9 cards per page), and writes a single review document.
"""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NamedTuple, TypedDict

import car_paths  # first: puts hartlib and publications/ on sys.path
from hartlib import operations

from docx.table import _Cell

import card_template_sheet
import generate_card_template as g
from card_description import build_freight_description, normalize_car_type, format_type_label as format_type
from card_errors import CardPipelineError
from card_template_records import CardRecord
from engine_lookup import (
    ROAD_DISPLAY,
    EngineKey,
    EngineRecord,
    build_locomotive_description,
    is_locomotive_row,
    load_engine_roster,
    match_engine,
)

BASE = car_paths.ROOT
DATA = car_paths.DATA
OUTPUT_DIR = car_paths.OUTPUT_DIR
METADATA_CSV = DATA / "image_metadata.csv"
ROSTER_XML = DATA / "OperationsCarRoster.xml"
OUTPUT = OUTPUT_DIR / "HART_All_Car_Cards.docx"
CARDS_PER_PAGE = card_template_sheet.CARDS_PER_PAGE

FINAL_DIR = car_paths.FINAL_DIR  # the folder finalize_car_images.py writes
CARD_FILL_DIR = BASE / "CarImagesCardFill"
CARD_FILL_PRINT_DIR = BASE / "CarImagesCardFillPrint"

# Omit from print sheet — unidentified / decorative cars kept in manifest for review only.
EXCLUDE_FROM_DOC: frozenset[str] = frozenset({"IMG_9152.png"})

class RosterCar(TypedDict):
    """One car of OperationsCarRoster.xml, as the card reads it."""

    roster_id: str
    roster_road: str
    road_number: str
    car_type: str
    roster_length_ft: str


class CardEntry(NamedTuple):
    """One card of the sheet: its fields, its picture (None prints the placeholder) and the row it came from."""

    record: CardRecord
    image: Path | None
    row: Mapping[str, str]


def load_roster() -> dict[str, RosterCar]:
    """The car roster by JMRI id."""
    cars: dict[str, RosterCar] = {}
    for el in operations.cars(ROSTER_XML):
        cars[el.get("id", "")] = {
            "roster_id": el.get("id", ""),
            "roster_road": el.get("roadName", ""),
            "road_number": el.get("roadNumber", ""),
            "car_type": el.get("type", ""),
            "roster_length_ft": el.get("length", ""),
        }
    return cars


def format_description(row: Mapping[str, str], car: RosterCar | None,
                       engine_by_key: Mapping[EngineKey, EngineRecord]) -> str:
    """A locomotive's maker · model · length when the row is one and it can be read, else the freight description."""
    if is_locomotive_row(row):
        desc = build_locomotive_description(match_engine(row, engine_by_key), row)
        if desc:
            return desc
    return build_freight_description(dict(row), dict(car) if car else None)


def display_road(row: Mapping[str, str], engine_by_key: Mapping[EngineKey, EngineRecord]) -> str:
    """The road the card prints: a rostered car's display mark, else the row's marks, else its engine's road."""
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
        return ROAD_DISPLAY.get(road, road) or "?"

    return "?"


def display_road_number(row: Mapping[str, str], car: RosterCar | None,
                        engine_by_key: Mapping[EngineKey, EngineRecord]) -> str:
    """The number the card prints: the roster car's, else the matched engine's, else the row's, else ?."""
    if car and car.get("road_number"):
        return car["road_number"]

    engine = match_engine(row, engine_by_key)
    if engine and engine.get("road_number"):
        return engine["road_number"]

    return row.get("road_number", "").strip() or "?"


def resolve_image(row: Mapping[str, str]) -> Path | None:
    """The first card picture found for the row's photo: print fill, card fill, final, then its cropped_image."""
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


def row_to_card(row: Mapping[str, str], roster: Mapping[str, RosterCar],
                engine_by_key: Mapping[EngineKey, EngineRecord]) -> tuple[CardRecord, Path | None]:
    """The card fields and picture for one repository row (or a loco row in its shape)."""
    car = roster.get(row.get("roster_id", ""))
    ctype = normalize_car_type(row.get("car_type") or (car["car_type"] if car else ""))
    record: CardRecord = {
        "Type": format_type(ctype),
        "RoadName": display_road(row, engine_by_key),
        "RoadNumber": display_road_number(row, car, engine_by_key),
        "Description": format_description(row, car, engine_by_key),
    }
    return record, resolve_image(row)


def load_cards() -> list[CardEntry]:
    """A card for every photographed row of image_metadata.csv, less EXCLUDE_FROM_DOC."""
    if not METADATA_CSV.is_file():
        raise CardPipelineError(f"Missing the car repository {METADATA_CSV}")
    roster = load_roster()
    _, engine_by_key = load_engine_roster()
    cards: list[CardEntry] = []
    with METADATA_CSV.open(newline="") as f:
        for row in csv.DictReader(f):
            if row.get("source_image", "") in EXCLUDE_FROM_DOC:
                continue
            if not row.get("source_image", "").strip():
                continue  # No photo yet; cars.py queues these cards.
            record, image = row_to_card(row, roster, engine_by_key)
            cards.append(CardEntry(record, image, row))
    return cards


def _fill_slot(cell: _Cell, idx: int, card: CardEntry) -> None:
    record, image, _row = card
    g.build_card(cell, advance_record=False, idx=idx, record=record, image_path=image)


def generate(cards: Sequence[CardEntry]) -> None:
    """Write the cards to OUTPUT, nine to a sticker page."""
    sticker_sheet = car_paths.require_sticker_sheet()
    card_template_sheet.write_sticker_deck(cards, _fill_slot, sticker_sheet=sticker_sheet, output=OUTPUT)


def main() -> None:
    cards = load_cards()
    generate(cards)

    with_image = sum(1 for _, img, _ in cards if img)
    matched = sum(1 for _, _, row in cards if row.get("roster_id"))

    print(f"Wrote {OUTPUT}")
    print(f"  {len(cards)} cards · {card_template_sheet.page_count(len(cards))} pages · {with_image} with photos")
    print(f"  {matched} roster matches (review remaining in the doc)")


if __name__ == "__main__":
    try:
        main()
    except CardPipelineError as exc:
        raise SystemExit(str(exc)) from exc
