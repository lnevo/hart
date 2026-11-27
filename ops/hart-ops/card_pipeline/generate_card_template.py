#!/usr/bin/env python3
"""
Build HART equipment card mail-merge template on the Apostrophe poker sticker sheet.

Design source: train_card.prompt
  - Letterhead logo upper-left
  - Railroad name + division subtitle
  - Boxed title upper-right
  - Heavy outer card border
  - Large image area (~half the card)
  - Footer form number
  - Sans-serif, monochrome, subtle gray fills on header/footer only

Sticker sheet: Poker Size Sticker Sheet Template.docx (9 cards per 8.5x11 page)

Layout constants (card_template_layout), OOXML helpers (card_template_docx), the sections every card shares
(card_template_parts), the waybill builders (card_template_waybill, card_template_cc_label) and the sheet assembly (card_template_sheet) live
beside this file. This module holds the equipment card, its image paths and the wrappers that pass those paths to the
waybill builders.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import car_paths  # noqa: F401  (first: puts hartlib and publications/ on sys.path)

from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches
from docx.table import _Cell, _Row
from docx.text.paragraph import Paragraph

from car_paths import ASSETS, OUTPUT_DIR, require_sticker_sheet
import card_template_cc_label
import card_template_waybill
from card_template_docx import (
    borders,
    grid,
    linebreak,
    merge_field,
    minimize_cell_tail,
    pad,
    para,
    tbl_width_dxa,
    text,
    tighten_cell,
    width,
)
from card_template_layout import (
    H_HEADER,
    H_IMAGE,
    IMG_INNER_PAD,
    IMG_OUTER_PAD_BOTTOM,
    IMG_OUTER_PAD_TOP,
    LABEL_CLR,
    VALUE_CLR,
)
from card_template_parts import (
    CONTENT_W,
    CardImages,
    IconField,
    card_frame,
    card_table,
    form_footer,
    icon_field_section,
    inset_box,
    ruled_title,
    section,
)
from card_template_records import CardRecord, CcLabelRecord, WaybillSource
from card_template_sheet import CARDS_PER_PAGE, write_sticker_deck

LOGO = ASSETS / "Logo.png"
ICON_ROAD_NAME = ASSETS / "icon_railroad.png"   # tracks-in-a-circle line icon
ICON_ROAD_NUM  = ASSETS / "icon_number.png"     # circled # line icon
ICON_DESC      = ASSETS / "icon_pencil.png"     # circled pencil line icon
OUTPUT = OUTPUT_DIR / "HART_Equipment_Card_Template.docx"
FORM_ID = "Form HART-CC-001    Rev A"

LOGO_W = 900  # the logo cell; the title takes the rest of the header
TITLE_LEFT_PAD = 150  # keeps the title's rules off the logo frame
WORK_ORDER_LINES = 7  # a blank train card's ruled lines, counting the orders it lists
PLACEHOLDER_CLR = (140, 140, 140)
RULED_LINE_CLR = (170, 170, 170)
FIELD_ROWS = (("ROAD NAME:", "RoadName"), ("ROAD NUMBER:", "RoadNumber"), ("DESCRIPTION:", "Description"))


# ── card builder ────────────────────────────────────────────────────────────

def build_card(cell: _Cell, *, advance_record: bool, idx: int,
               record: CardRecord | None = None, image_path: Path | None = None) -> None:
    """Place one prompt-styled card into a sticker-sheet slot.

    When ``record`` / ``image_path`` are given the card is filled with static values and an embedded photo; a record
    with ``Blank`` set is a train card whose picture area lists its work orders. With no record the card carries
    MERGEFIELD placeholders for a mail merge, and ``advance_record`` adds the NEXT field that moves to the next
    record."""
    card_frame(cell, idx, advance_record=advance_record)
    t = card_table(cell, 4)
    _header(t.rows[0], record)
    _picture(t.rows[1], record, image_path)
    icon_field_section(t.rows[2], _fields(record, _card_images()))
    form_footer(t.rows[3], FORM_ID)
    minimize_cell_tail(cell)   # keep all 9 cards on one page


def _header(row: _Row, record: CardRecord | None) -> None:
    """The logo on the left; the car type, upper case between two rules, on the right."""
    c_head = section(row, H_HEADER, top=20, bottom=20, valign=WD_ALIGN_VERTICAL.CENTER)
    title_w = CONTENT_W - LOGO_W
    head = c_head.add_table(rows=1, cols=2)
    tbl_width_dxa(head, CONTENT_W, center=False)
    grid(head, [LOGO_W, title_w])
    borders(head, outer=0)
    h_logo, h_title = head.rows[0].cells
    width(h_logo, LOGO_W)
    width(h_title, title_w)
    for c in (h_logo, h_title):
        c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    # The rounded frame is part of Logo.png. Zero cell margins keep the 0.56"-wide image from being clipped on the
    # right; a small left margin keeps it off the card frame.
    pad(h_logo, left=40, right=0, top=0, bottom=0)
    p = h_logo.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.LEFT)
    if LOGO.exists():
        p.add_run().add_picture(str(LOGO), width=Inches(0.56))
    else:
        text(p.add_run(), "LOGO", bold=True, size=6, color=(100, 100, 100))

    pad(h_title, left=TITLE_LEFT_PAD, right=0, top=0, bottom=0)
    p = ruled_title(h_title, title_w - TITLE_LEFT_PAD, pad_tb=36)
    if record is not None:
        text(p.add_run(), record.get("Type", "").upper(), bold=True, size=12)
    else:
        merge_field(p, "Type", bold=True, size=12)
    tighten_cell(h_title)
    tighten_cell(c_head)


def _picture(row: _Row, record: CardRecord | None, image_path: Path | None) -> None:
    """The picture area (about half the card): the photo, a train card's work orders, or the merge placeholder."""
    c_img = section(row, H_IMAGE, top=IMG_OUTER_PAD_TOP, bottom=IMG_OUTER_PAD_BOTTOM, valign=WD_ALIGN_VERTICAL.TOP)
    ic = inset_box(c_img, CONTENT_W)
    ic.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    pad(ic, top=IMG_INNER_PAD, bottom=IMG_INNER_PAD, left=40, right=40)
    p = ic.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER)
    if image_path is not None and Path(image_path).exists():
        p.add_run().add_picture(str(image_path), width=Inches(1.84))
    elif record is not None and record.get("Blank"):
        _work_orders(ic, p, record.get("Orders") or [])
    else:
        text(p.add_run(), "EQUIPMENT IMAGE", size=7, color=PLACEHOLDER_CLR)
        linebreak(p)
        merge_field(p, "ImagePath", size=6, color=VALUE_CLR)
    tighten_cell(c_img)


def _work_orders(cell: _Cell, heading: Paragraph, orders: Sequence[str]) -> None:
    """A train card's WORK ORDERS heading, its orders, then ruled lines to write more on (at least one)."""
    text(heading.add_run(), "WORK ORDERS", bold=True, size=6, color=LABEL_CLR)
    for line in orders:
        q = cell.add_paragraph()
        para(q, align=WD_ALIGN_PARAGRAPH.LEFT, before=3, after=0)
        text(q.add_run(), line, size=5.5, color=VALUE_CLR)
    for _ in range(max(1, WORK_ORDER_LINES - len(orders))):
        q = cell.add_paragraph()
        para(q, align=WD_ALIGN_PARAGRAPH.LEFT, before=5, after=0)
        text(q.add_run(), "_" * 46, size=5.5, color=RULED_LINE_CLR)


def _fields(record: CardRecord | None, images: CardImages) -> list[IconField]:
    """Road name, road number and description: the record's values, else their merge fields."""
    icons = {"RoadName": images.road_name, "RoadNumber": images.road_num, "Description": images.desc}
    fields = []
    for label, name in FIELD_ROWS:
        if record is None:
            fields.append(IconField(label, icons[name], name, 6.5 if name == "Description" else 9, merge=True))
            continue
        value = _record_value(record, name)
        size = (5.5 if len(value) > 18 else 6.5) if name == "Description" else 9
        fields.append(IconField(label, icons[name], value, size))
    return fields


def _record_value(record: Mapping[str, object], name: str) -> str:
    """One text field of the record; a train card's record may leave one out, which prints blank."""
    value = record.get(name, "")
    if not isinstance(value, str):
        raise TypeError(f"card field {name} is {value!r}, expected text")
    return value


def _card_images() -> CardImages:
    """The logo and icon paths as this module holds them now (tests patch them here)."""
    return CardImages(logo=LOGO, road_name=ICON_ROAD_NAME, road_num=ICON_ROAD_NUM, desc=ICON_DESC)


def build_waybill_card(cell: _Cell, *, idx: int, record: WaybillSource) -> None:
    """Place one spot waybill card into a sticker-sheet slot (card_template_waybill)."""
    card_template_waybill.build_waybill_card(cell, idx=idx, record=record, images=_card_images())


def build_cc_waybill_label(cell: _Cell, *, idx: int, record: CcLabelRecord) -> None:
    """One slim CC/WB shipment label in a poker sticker slot (card_template_cc_label)."""
    card_template_cc_label.build_cc_waybill_label(cell, idx=idx, record=record, images=_card_images())


def _merge_slot(cell: _Cell, idx: int, _record: None) -> None:
    build_card(cell, advance_record=idx > 0, idx=idx)


def main() -> None:
    sticker_sheet = require_sticker_sheet()
    write_sticker_deck([None] * CARDS_PER_PAGE, _merge_slot, sticker_sheet=sticker_sheet, output=OUTPUT)
    print(f"Wrote {OUTPUT}")
    print("  9 cards · 3×3 sticker grid · mail-merge ready")
    if LOGO.exists():
        print(f"  Logo: {LOGO.name}")


if __name__ == "__main__":
    try:
        main()
    except car_paths.CardPipelineError as exc:
        raise SystemExit(str(exc)) from exc
