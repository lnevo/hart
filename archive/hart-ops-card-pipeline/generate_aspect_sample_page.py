#!/usr/bin/env python3
"""One sticker page sampling CarImagesFinal crops across aspect ratios and car types."""

import csv
import shutil
from pathlib import Path

from docx import Document

import generate_all_cards as ga
import generate_card_template as g

OUTPUT = g.OUTPUT_DIR / "HART_Aspect_Ratio_Sample.docx"
FINAL_DIR = g.BASE / "CarImagesFinal"

# Curated for visual spread — one flatcar, mixed heights and car types.
SAMPLE: list[tuple[str, str]] = [
    ("IMG_9137", "Square outlier"),
    ("IMG_9115", "Tall narrow box"),
    ("IMG_9138", "Extra-tall crop"),
    ("IMG_9136", "Short height"),
    ("IMG_9161", "Hopper"),
    ("IMG_9153", "Tank car"),
    ("IMG_9162", "Typical box car"),
    ("IMG_9127", "Long gondola"),
    ("IMG_9131", "Flatcar (widest)"),
]


def load_row(stem: str) -> dict:
    with ga.METADATA_CSV.open(newline="") as f:
        for row in csv.DictReader(f):
            if Path(row["source_image"]).stem == stem:
                return row
    return {}


def aspect_label(path: Path) -> str:
    from PIL import Image

    w, h = Image.open(path).size
    return f"ratio {w / h:.2f} · {w}×{h}"


def main() -> int:
    roster = ga.load_roster()
    cards: list[tuple[dict, Path, dict]] = []

    for stem, label in SAMPLE:
        img = FINAL_DIR / f"{stem}.png"
        if not img.exists():
            raise FileNotFoundError(img)
        row = load_row(stem)
        if row:
            record, _ = ga.row_to_card(row, roster)
            car = roster.get(row.get("roster_id", ""))
            desc = ga.format_description(row, car)
            if desc and desc != "—":
                record["Description"] = desc
        else:
            record = {
                "Type": "Equipment",
                "RoadName": "",
                "RoadNumber": "",
                "Description": stem,
            }
        road = f"{record.get('RoadName', '')} {record.get('RoadNumber', '')}".strip()
        record["Description"] = f"{label} · {road} · {aspect_label(img)}"
        cards.append((record, img, row))

    shutil.copy2(g.require_sticker_sheet(), OUTPUT)
    doc = Document(OUTPUT)
    g.keep_sticker_grid(doc)
    ga._fill_page(doc.tables[0], cards, 0)
    doc.save(OUTPUT)

    print(f"Wrote {OUTPUT}")
    for i, (rec, img, _) in enumerate(cards):
        r, c = g.CARD_SLOTS[i]
        print(f"  [{r},{c}] {img.stem}: {rec.get('Type', '')} — {rec['Description']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
