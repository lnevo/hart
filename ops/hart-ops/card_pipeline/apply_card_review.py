#!/usr/bin/env python3
"""Apply card_review.html export JSON to image_metadata.csv."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from process_car_images import CSV_COLUMNS, METADATA_CSV

BASE = Path(__file__).resolve().parent.parent  # Car Cards project root (scripts live in card_pipeline/)

FIELD_MAP = {
    "reporting_marks": "reporting_marks",
    "road_name": "road_name",
    "road_number": "road_number",
    "car_type": "car_type",
    "color": "color",
    "roster_id": "roster_id",
    "description": "full_name",
}


def apply_changes(payload: dict) -> int:
    changes = {c["source_image"]: c for c in payload.get("changes", [])}
    if not changes:
        print("No changes in payload.")
        return 0

    rows: list[dict] = []
    updated = 0
    with METADATA_CSV.open(newline="") as f:
        for row in csv.DictReader(f):
            src = row.get("source_image", "")
            if src in changes:
                ch = changes[src]
                for src_key, csv_key in FIELD_MAP.items():
                    if src_key in ch:
                        row[csv_key] = ch[src_key]
                if ch.get("engine_roster_id"):
                    note = f"engine_roster_id={ch['engine_roster_id']}"
                    if note not in row.get("notes", ""):
                        row["notes"] = "; ".join(
                            p for p in [row.get("notes", "").strip(), note] if p
                        )
                updated += 1
            rows.append(row)

    with METADATA_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({c: row.get(c, "") for c in CSV_COLUMNS})

    print(f"Updated {updated} row(s) in {METADATA_CSV}")
    for src, ch in changes.items():
        if src not in {r["source_image"] for r in rows}:
            print(f"  WARNING: {src} not found in manifest")
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_file", nargs="?", help="Export JSON file (default: stdin)")
    args = parser.parse_args()

    if args.json_file:
        payload = json.loads(Path(args.json_file).read_text(encoding="utf-8"))
    else:
        payload = json.load(sys.stdin)

    apply_changes(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
