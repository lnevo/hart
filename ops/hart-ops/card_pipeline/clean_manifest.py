#!/usr/bin/env python3
"""Remove OCR garbage from image_metadata.csv identity fields."""

from __future__ import annotations

import csv
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from process_car_images import (
    CSV_COLUMNS,
    METADATA_CSV,
    ROSTER_XML,
    _is_weight_context,
    _norm,
    _valid_marks,
)

BASE = Path(__file__).resolve().parent.parent  # Car Cards project root (scripts live in card_pipeline/)

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

KNOWN_MARKS = set(ROAD_DISPLAY.values()) | {
    "UNION",
    "CONRAIL",
    "N&W",
    "B&O",
    "C&O",
    "CB&Q",
}


def load_roster() -> dict[str, dict]:
    root = ET.parse(ROSTER_XML).getroot()
    cars: dict[str, dict] = {}
    for el in root.findall("./cars/car"):
        rid = el.get("id", "")
        cars[rid] = {
            "roster_id": rid,
            "roster_road": el.get("roadName", ""),
            "road_number": el.get("roadNumber", ""),
            "car_type": el.get("type", ""),
            "roster_length_ft": el.get("length", ""),
        }
    return cars


def _trusted_marks(marks: str) -> bool:
    if not marks or not _valid_marks(marks):
        return False
    if marks in KNOWN_MARKS:
        return True
    mk = _norm(marks)
    return mk in { _norm(m) for m in KNOWN_MARKS }


def _trusted_number(row: dict, number: str) -> bool:
    if not number or not re.fullmatch(r"\d{4,6}", number):
        return False
    ocr = row.get("ocr_text", "")
    if _is_weight_context(ocr, number):
        return False
    excluded = {
        row.get("capy_lbs", ""),
        row.get("ld_lmt_lbs", ""),
        row.get("lt_wt_lbs", ""),
    }
    if number in excluded:
        return False
    conf = row.get("match_confidence", "").strip()
    return conf != "none"


def clean_row(row: dict, roster: dict[str, dict]) -> dict:
    roster_id = row.get("roster_id", "").strip()
    car = roster.get(roster_id) if roster_id else None

    if car:
        road = car["roster_road"]
        marks = ROAD_DISPLAY.get(road, road)
        row["reporting_marks"] = marks
        row["road_name"] = marks
        row["road_number"] = car["road_number"]
        row["roster_road"] = road
        row["roster_length_ft"] = car["roster_length_ft"]
        if not row.get("car_type"):
            row["car_type"] = car["car_type"]
    else:
        marks = row.get("reporting_marks", "").strip()
        if not _trusted_marks(marks):
            row["reporting_marks"] = ""
            row["road_name"] = ""

        number = row.get("road_number", "").strip()
        if not _trusted_number(row, number):
            row["road_number"] = ""

    row["full_name"] = ""

    # Notes: keep human hints, drop empty duplicates.
    notes = row.get("notes", "").strip()
    parts = [p.strip() for p in notes.split(";") if p.strip()]
    row["notes"] = "; ".join(parts)

    return row


def clean_manifest() -> tuple[int, int]:
    roster = load_roster()
    rows: list[dict] = []
    cleared_marks = 0
    cleared_nums = 0

    with METADATA_CSV.open(newline="") as f:
        for row in csv.DictReader(f):
            before_m = row.get("reporting_marks", "")
            before_n = row.get("road_number", "")
            row = clean_row(row, roster)
            if before_m and not row.get("reporting_marks"):
                cleared_marks += 1
            if before_n and not row.get("road_number"):
                cleared_nums += 1
            rows.append(row)

    with METADATA_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({c: row.get(c, "") for c in CSV_COLUMNS})

    return cleared_marks, cleared_nums


def main() -> int:
    cleared_marks, cleared_nums = clean_manifest()
    print(f"Wrote {METADATA_CSV}")
    print(f"  cleared garbage marks: {cleared_marks}")
    print(f"  cleared garbage numbers: {cleared_nums}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
