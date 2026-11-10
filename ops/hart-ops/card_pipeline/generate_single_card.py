#!/usr/bin/env python3
"""Generate one filled HART car card (static data + embedded photo).

Reuses the layout from generate_card_template.py but fills a single sticker
slot with real values and an embedded image, so a single card can be printed
and test-fit on the poker sticker sheet.
"""

import shutil

from docx import Document

import generate_card_template as g

OUTPUT = g.OUTPUT_DIR / "HART_Card_NW32800.docx"
IMAGE = g.ASSETS / "NW32800.png"

# Matched from OperationsCarRoster.xml: NW 32800, Flatcar, 52 ft.
# Color read from the photo (black); feet abbreviated with an apostrophe.
RECORD = {
    "Type": "Flat Car",
    "RoadName": "N&W",
    "RoadNumber": "32800",
    "Description": "Black Flatcar \u00b7 52'",
}


def main() -> None:
    shutil.copy2(g.require_sticker_sheet(), OUTPUT)
    doc = Document(OUTPUT)
    g.keep_sticker_grid(doc)

    sheet = doc.tables[0]
    r, c = g.CARD_SLOTS[0]
    g.build_card(
        sheet.rows[r].cells[c],
        advance_record=False,
        idx=0,
        record=RECORD,
        image_path=IMAGE,
    )

    doc.save(OUTPUT)
    print(f"Wrote {OUTPUT}")
    print(f"  {RECORD['RoadName']} {RECORD['RoadNumber']} - {RECORD['Description']}")
    print(f"  Image: {IMAGE.name}")


if __name__ == "__main__":
    main()
