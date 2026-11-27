#!/usr/bin/env python3
"""Generate one filled HART car card (static data + embedded photo) to test-fit on the poker sticker sheet.

    generate_single_card.py             the golden card, NW32800 (tests/golden/NW32800.docx)
    generate_single_card.py ROSTER_ID   that car's card as generate_all_cards.py prints it

The card fills the first sticker slot; the other slots stay blank. The sheet has no body tail paragraph after the
grid, as the golden file was made.
"""
from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from docx import Document

import car_paths
import card_template_layout
import card_template_sheet
import generate_all_cards
import generate_card_template as g
from card_errors import CardPipelineError
from card_template_records import CardRecord


class SingleCard(NamedTuple):
    """The car a sheet is made for: its roster id names the file, its record and picture fill the card."""

    roster_id: str
    record: CardRecord
    image: Path | None  # None prints the placeholder picture


# The golden car, matched from OperationsCarRoster.xml: NW 32800, Flatcar, 52 ft. Color read from the photo
# (black); feet abbreviated with an apostrophe.
GOLDEN_CARD = SingleCard(
    "NW32800",
    {"Type": "Flat Car", "RoadName": "N&W", "RoadNumber": "32800", "Description": "Black Flatcar · 52'"},
    car_paths.ASSETS / "NW32800.png",
)


def output_for(roster_id: str) -> Path:
    """Where the sheet for ``roster_id`` is written."""
    return car_paths.OUTPUT_DIR / f"HART_Card_{roster_id}.docx"


def repository_card(roster_id: str) -> SingleCard:
    """The card generate_all_cards.py prints for the one photographed repository row with this roster id."""
    found = [entry for entry in generate_all_cards.load_cards() if entry.row.get("roster_id", "").strip() == roster_id]
    if not found:
        raise CardPipelineError(f"no photographed car {roster_id} in {generate_all_cards.METADATA_CSV}")
    if len(found) > 1:
        photos = ", ".join(entry.row.get("source_image", "") for entry in found)
        raise CardPipelineError(f"{roster_id} is on {len(found)} photographed rows ({photos}); give it one")
    return SingleCard(roster_id, found[0].record, found[0].image)


def write_card(card: SingleCard, output: Path, sticker_sheet: Path) -> None:
    """The sticker sheet's grid with ``card`` in the first slot, written beside ``output`` and moved into place."""
    doc = Document(str(sticker_sheet))
    card_template_sheet.keep_sticker_grid(doc)
    r, c = card_template_layout.CARD_SLOTS[0]
    g.build_card(doc.tables[0].rows[r].cells[c], advance_record=False, idx=0, record=card.record,
                 image_path=card.image)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output.with_suffix(".tmp.docx")
    doc.save(str(temp_path))
    os.replace(temp_path, output)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("roster_id", nargs="?", help=f"a car of the repository (default: the golden card, "
                                                     f"{GOLDEN_CARD.roster_id})")
    args = parser.parse_args(argv)
    card = repository_card(args.roster_id) if args.roster_id else GOLDEN_CARD
    output = output_for(card.roster_id)
    write_card(card, output, car_paths.require_sticker_sheet())

    record = card.record
    print(f"Wrote {output}")
    print(f"  {record['RoadName']} {record['RoadNumber']} - {record['Description']}")
    print(f"  Image: {card.image.name if card.image else 'none (placeholder)'}")


if __name__ == "__main__":
    try:
        main()
    except CardPipelineError as exc:
        raise SystemExit(str(exc)) from exc
