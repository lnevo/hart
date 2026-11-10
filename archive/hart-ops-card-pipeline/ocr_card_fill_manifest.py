#!/usr/bin/env python3
"""Regenerate image_metadata.csv: OCR full Images/, card paths from CardFill.

Runs OCR on the original light-box photos (``Images/``) for best text quality,
matches ``OperationsCarRoster.xml``, and points ``cropped_image`` at
``CarImagesCardFill/`` for card generation. Does not modify image folders.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from PIL import Image

from car_visual import enrich_row_visuals
from crop_car_image import detect_car_bbox
from process_car_images import (
    CSV_COLUMNS,
    METADATA_CSV,
    OCR_DIR,
    ROSTER_XML,
    _analysis_notes,
    _find_road_mark,
    _identity_key,
    _match_roster,
    _ocr_band,
    _parse_markings,
    load_roster,
    write_csv,
)

from ocr_compare import _ocr_easyocr


BASE = Path(__file__).resolve().parent.parent  # Car Cards project root (scripts live in card_pipeline/)
IMAGES_DIR = BASE / "Images"
CARD_FILL_DIR = BASE / "CarImagesCardFill"
FINAL_DIR = BASE / "CarImagesFinal"


def _card_fill_images() -> list[Path]:
    if not CARD_FILL_DIR.is_dir():
        raise FileNotFoundError(CARD_FILL_DIR)
    return sorted(CARD_FILL_DIR.glob("IMG_*.png"))


def process_card_fill_manifest(engine: str = "tesseract") -> list[dict]:
    roster = load_roster()
    OCR_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    seen: dict[str, str] = {}
    easy_reader = None
    if engine in ("easyocr", "both"):
        import easyocr

        easy_reader = easyocr.Reader(["en"], gpu=False, verbose=False)

    for crop_path in _card_fill_images():
        stem = crop_path.stem
        src_path = IMAGES_DIR / f"{stem}.png"
        rel_source = src_path.name if src_path.exists() else f"{stem}.png"

        # OCR from full-resolution source; card layout uses the card-fill crop.
        ocr_img_path = src_path if src_path.exists() else crop_path
        img = Image.open(ocr_img_path).convert("RGB")
        bbox = detect_car_bbox(img)
        ocr_text, ocr_zoom = _ocr_band(img, bbox)
        if engine == "easyocr":
            ocr_text = _ocr_easyocr(img, bbox, easy_reader)
        elif engine == "both":
            ocr_text = f"{ocr_text} {_ocr_easyocr(img, bbox, easy_reader)}"
        parsed = _parse_markings(ocr_text)
        marks, number = _find_road_mark(ocr_text, roster)
        roster_row, confidence = _match_roster(ocr_text, roster, marks, number, parsed)

        ocr_name = f"OCR_{stem}.png"
        ocr_zoom.save(OCR_DIR / ocr_name)

        final_rel = (
            f"CarImagesFinal/{stem}.png"
            if (FINAL_DIR / f"{stem}.png").exists()
            else ""
        )

        row = {
            "source_image": rel_source,
            "cropped_image": f"CarImagesCardFill/{crop_path.name}",
            "ocr_zoom_image": f"OcrZoom/{ocr_name}",
            "crop_status": "ok",
            "duplicate_of": "",
            "reporting_marks": marks,
            "road_name": marks,
            "road_number": number,
            "full_name": "",
            "car_type": parsed.get("car_type", ""),
            "car_class": parsed.get("car_class", ""),
            "color": "",
            "capy_lbs": parsed.get("capy_lbs", ""),
            "ld_lmt_lbs": parsed.get("ld_lmt_lbs", ""),
            "lt_wt_lbs": parsed.get("lt_wt_lbs", ""),
            "built": parsed.get("built", ""),
            "roster_id": "",
            "roster_road": "",
            "roster_length_ft": "",
            "roster_weight_oz": "",
            "roster_weight_tons": "",
            "ocr_text": ocr_text[:400].replace("\n", " "),
            "match_confidence": confidence,
            "notes": _analysis_notes(ocr_text, marks, number),
        }
        if final_rel:
            row["notes"] = (
                f"{row['notes']}; final_ref={final_rel}".strip("; ")
                if row["notes"]
                else f"final_ref={final_rel}"
            )

        if roster_row:
            row.update(
                {
                    "road_number": roster_row["road_number"] or number,
                    "car_type": roster_row["car_type"] or row["car_type"],
                    "roster_id": roster_row["roster_id"],
                    "roster_road": roster_row["roster_road"],
                    "roster_length_ft": roster_row["roster_length_ft"],
                    "roster_weight_oz": roster_row["roster_weight_oz"],
                    "roster_weight_tons": roster_row["roster_weight_tons"],
                }
            )

        key = _identity_key(row)
        if key:
            if key in seen:
                row["duplicate_of"] = seen[key]
                extra = "duplicate photo of same car"
                row["notes"] = f"{row['notes']}; {extra}".strip("; ")
            else:
                seen[key] = rel_source

        fill_img = Image.open(crop_path).convert("RGB")
        fill_bbox = detect_car_bbox(fill_img)
        roster_type = row.get("car_type", "")
        visuals = enrich_row_visuals(
            row, fill_img, fill_bbox, roster_type, parsed=parsed
        )
        row["car_type"] = visuals["car_type"]
        row["color"] = visuals["color"]

        rows.append(row)
        dup = f" DUP->{row['duplicate_of']}" if row["duplicate_of"] else ""
        tag = row["roster_id"] or number or marks or "?"
        print(f"{crop_path.name}  [{confidence}] {tag}{dup}")

    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="OCR Images/ and write image_metadata.csv with CardFill paths",
    )
    parser.add_argument(
        "--engine",
        choices=("tesseract", "easyocr", "both"),
        default="tesseract",
        help="OCR engine (both merges Tesseract + EasyOCR text; slow)",
    )
    args = parser.parse_args()
    if not ROSTER_XML.exists():
        raise FileNotFoundError(ROSTER_XML)
    rows = process_card_fill_manifest(engine=args.engine)
    write_csv(rows)
    matched = sum(1 for r in rows if r.get("roster_id"))
    print(f"  OCR engine: {args.engine}")
    print(f"  Card-fill images: {CARD_FILL_DIR}/")
    print(f"  Roster matches: {matched}/{len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
