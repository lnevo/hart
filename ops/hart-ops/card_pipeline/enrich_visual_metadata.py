#!/usr/bin/env python3
"""Fill color and car_type in image_metadata.csv from card-fill images."""

from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

from car_visual import enrich_row_visuals
from crop_car_image import detect_car_bbox
from process_car_images import CSV_COLUMNS, METADATA_CSV, ROSTER_XML, _parse_markings

BASE = Path(__file__).resolve().parent.parent  # Car Cards project root (scripts live in card_pipeline/)
CARD_FILL_DIR = BASE / "CarImagesCardFill"


def load_roster_types() -> dict[str, str]:
    root = ET.parse(ROSTER_XML).getroot()
    out: dict[str, str] = {}
    for el in root.findall("./cars/car"):
        out[el.get("id", "")] = el.get("type", "")
    return out


def enrich_manifest() -> None:
    roster_types = load_roster_types()
    rows: list[dict] = []
    type_filled = 0
    color_filled = 0

    with METADATA_CSV.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stem = Path(row.get("source_image", "")).stem
            fill_path = CARD_FILL_DIR / f"{stem}.png"
            roster_type = roster_types.get(row.get("roster_id", ""), "")

            if fill_path.exists():
                fill_img = Image.open(fill_path).convert("RGB")
                fill_bbox = detect_car_bbox(fill_img)
                parsed = _parse_markings(row.get("ocr_text", ""))
                visuals = enrich_row_visuals(
                    row, fill_img, fill_bbox, roster_type, parsed=parsed
                )
                row["car_type"] = visuals["car_type"]
                row["color"] = visuals["color"]
            elif roster_type:
                row["car_type"] = roster_type

            if row.get("car_type"):
                type_filled += 1
            if row.get("color"):
                color_filled += 1
            rows.append(row)

    with METADATA_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({c: row.get(c, "") for c in CSV_COLUMNS})

    print(f"Wrote {METADATA_CSV}")
    print(f"  car_type filled: {type_filled}/{len(rows)}")
    print(f"  color filled:    {color_filled}/{len(rows)}")

    from clean_manifest import clean_manifest

    cleared_marks, cleared_nums = clean_manifest()
    print(f"  cleared garbage marks: {cleared_marks}")
    print(f"  cleared garbage numbers: {cleared_nums}")


def main() -> int:
    if not METADATA_CSV.exists():
        raise FileNotFoundError(METADATA_CSV)
    enrich_manifest()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
