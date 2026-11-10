#!/usr/bin/env python3
"""Generate filled HART car cards for every row in image_metadata.csv.

Reads cropped images from CarImagesCardFill/ (then CarImagesFinal/, then CarImages/), sticker-sheet layout
(9 cards per page), and writes a single review document.
"""

from __future__ import annotations

import csv
import shutil
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.table import Table

import generate_card_template as g
from engine_lookup import (
    build_locomotive_description,
    is_locomotive_row,
    load_engine_roster,
    match_engine,
)
from card_description import build_freight_description, normalize_car_type, format_type_label as format_type

BASE = g.BASE
DATA = g.DATA
OUTPUT_DIR = g.OUTPUT_DIR
ASSETS = g.ASSETS
METADATA_CSV = DATA / "image_metadata.csv"
ROSTER_XML = DATA / "OperationsCarRoster.xml"
OUTPUT = OUTPUT_DIR / "HART_All_Car_Cards.docx"
CARDS_PER_PAGE = len(g.CARD_SLOTS)

# Omit from print sheet — unidentified / decorative cars kept in manifest for review only.
EXCLUDE_FROM_DOC: frozenset[str] = frozenset({"IMG_9152.png"})

# JMRI roster road codes -> display reporting marks.
ROAD_DISPLAY = {
    "NW": "N&W",
    "BO": "B&O",
    "PRR": "PRR",
    "NYC": "NYC",
    "ATSF": "ATSF",
    "CBQ": "CB&Q",
    "GN": "GN",
    "MILW": "MILW",
    "WP": "WP",
    "WM": "WM",
    "RDG": "RDG",
    "EL": "EL",
    "CO": "C&O",
    "KSMX": "KSMX",
    "GATX": "GATX",
    "UTLX": "UTLX",
    "URTX": "URTX",
    "SHPX": "SHPX",
    "REX": "REX",
    "URR": "URR",
    "WLE": "WLE",
    "MSTL": "MSTL",
    "MOW": "MOW",
}

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
    root = ET.parse(ROSTER_XML).getroot()
    cars: dict[str, dict] = {}
    for el in root.findall("./cars/car"):
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


FINAL_DIR = BASE / "CarImagesFinal"
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


def _set_page_break_before_table(tbl) -> None:
    """Start a sticker grid on a new page without a blank paragraph between pages."""
    first_row = tbl.findall(qn("w:tr"))[0]
    first_cell = first_row.findall(qn("w:tc"))[0]
    p = first_cell.find(qn("w:p"))
    if p is None:
        p = OxmlElement("w:p")
        first_cell.insert(0, p)
    pPr = p.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        p.insert(0, pPr)
    if pPr.find(qn("w:pageBreakBefore")) is None:
        pPr.insert(0, OxmlElement("w:pageBreakBefore"))


def _append_grid(doc: Document, grid_xml) -> Table:
    body = doc.element.body
    tbl = deepcopy(grid_xml)
    _set_page_break_before_table(tbl)
    g._insert_before_sect(body, tbl)
    g._ensure_sect_pr_last(body)
    table = Table(body.findall(qn("w:tbl"))[-1], doc)
    g.strip_grid_guides(table)
    return table


def _blank_sticker_grid():
    """Return OOXML for an empty 3×3 sticker grid cloned from the template."""
    scratch_path = BASE / ".scratch_sticker.docx"
    shutil.copy2(g.STICKER_SHEET, scratch_path)
    scratch = Document(scratch_path)
    g.keep_sticker_grid(scratch)
    grid = deepcopy(scratch.tables[0]._tbl)
    scratch_path.unlink(missing_ok=True)
    return grid


def _fill_page(sheet: Table, batch: list[tuple[dict, Path | None, dict]], page_idx: int) -> None:
    for i, (record, image, _row) in enumerate(batch):
        r, c = g.CARD_SLOTS[i]
        g.build_card(
            sheet.rows[r].cells[c],
            advance_record=False,
            idx=page_idx * CARDS_PER_PAGE + i,
            record=record,
            image_path=image,
        )


def generate(cards: list[tuple[dict, Path | None, dict]]) -> None:
    g.require_sticker_sheet()
    if not METADATA_CSV.exists():
        raise FileNotFoundError(METADATA_CSV)

    blank_grid = _blank_sticker_grid()
    shutil.copy2(g.STICKER_SHEET, OUTPUT)
    doc = Document(OUTPUT)
    g.keep_sticker_grid(doc)

    pages = [
        cards[i : i + CARDS_PER_PAGE]
        for i in range(0, len(cards), CARDS_PER_PAGE)
    ]

    sheet = doc.tables[0]
    _fill_page(sheet, pages[0], 0)

    for page_idx, batch in enumerate(pages[1:], start=1):
        sheet = _append_grid(doc, blank_grid)
        _fill_page(sheet, batch, page_idx)

    g._add_document_tail(doc.element.body)
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
    main()
