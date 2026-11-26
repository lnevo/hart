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

Layout constants (card_template_layout), OOXML helpers (card_template_docx), the waybill
builders (card_template_waybill) and the sheet assembly (card_template_sheet) live beside this
file; import them from those modules. This module holds the equipment card, its image paths and
the wrappers that pass those paths to the waybill builders.
"""

import shutil
from pathlib import Path

import car_paths  # noqa: F401  (first: puts hartlib and publications/ on sys.path)

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt

from car_paths import ASSETS, OUTPUT_DIR, STICKER_SHEET, require_sticker_sheet
import card_template_waybill
from card_template_docx import (
    add_round_frame,
    borders,
    grid,
    hrule,
    linebreak,
    merge_field,
    minimize_cell_tail,
    next_record,
    pad,
    para,
    row_h,
    tbl_width_dxa,
    text,
    tighten_cell,
    tighten_revision_cell,
    width,
)
from card_template_layout import (
    CARD_SLOTS,
    CARD_TOP_PAD,
    CARD_W,
    CENTER_OFFSET,
    DATA_TABLE_TOP_PAD,
    DIVIDER_CLR,
    FRAME_GROW_PT,
    FRAME_GROW_TWIPS,
    FRAME_MARGIN,
    H_DATA_SECTION,
    H_FOOTER,
    H_HEADER,
    H_IMAGE,
    IMAGE_BORDER,
    IMG_INNER_PAD,
    IMG_OUTER_PAD_BOTTOM,
    IMG_OUTER_PAD_TOP,
    INNER_BORDER,
    LABEL_CLR,
    PAGE2_SLOT_W,
    SIDE_PAD,
    SLOT_W,
    TARGET_FRAME_W,
    VALUE_CLR,
)
from card_template_sheet import add_document_tail, keep_sticker_grid
from card_template_waybill import CardImages

LOGO = ASSETS / "Logo.png"
ICON_ROAD_NAME = ASSETS / "icon_railroad.png"   # tracks-in-a-circle line icon
ICON_ROAD_NUM  = ASSETS / "icon_number.png"     # circled # line icon
ICON_DESC      = ASSETS / "icon_pencil.png"     # circled pencil line icon
OUTPUT = OUTPUT_DIR / "HART_Equipment_Card_Template.docx"


# ── card builder ────────────────────────────────────────────────────────────

def build_card(cell, *, advance_record: bool, idx: int,
               record: dict | None = None, image_path=None) -> None:
    """Place one prompt-styled card into a sticker-sheet slot.

    When ``record`` / ``image_path`` are given the card is filled with static
    values and an embedded photo (single-card output); otherwise it carries
    MERGEFIELD placeholders for a mail merge."""
    cell.text = ""
    # Shift the whole card block into the wider page-4 slot; internal 110/140
    # margins (content vs frame) stay as on the page-2 grid.
    side_gap = SLOT_W - PAGE2_SLOT_W - CENTER_OFFSET
    pad(cell, top=CARD_TOP_PAD, left=CENTER_OFFSET, right=side_gap)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP   # raise content to top

    # Leading anchor paragraph hosts the NEXT-record field and the rounded
    # frame shape. Keep it tiny so it doesn't shift the card down.
    lead = cell.paragraphs[0]
    para(lead, after=2)
    lead.paragraph_format.line_spacing = Pt(1)
    if advance_record:
        next_record(lead)
    for r in lead.runs:
        r.font.size = Pt(1)

    # Heavier rounded outer frame. Height must stay inside the 3.35" sticker
    # slot so the bottom row (with no card below to mask any overhang) doesn't
    # exceed the available space, while still clearing the footer line.
    frame_w_pt = (TARGET_FRAME_W + 2 * FRAME_GROW_TWIPS) / 20.0
    frame_h_pt = 3.16 * 72.0 + FRAME_GROW_PT          # 1/32" taller at bottom
    frame_left_pt = (FRAME_MARGIN - FRAME_GROW_TWIPS) / 20.0
    frame_top_pt = 1.0
    add_round_frame(
        lead,
        idx,
        width_pt=frame_w_pt,
        height_pt=frame_h_pt,
        left_pt=frame_left_pt,
        top_pt=frame_top_pt,
    )

    # ── main card container: single column, 4 stacked sections (borderless) ─
    t = cell.add_table(rows=4, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_width_dxa(t, CARD_W, center=True)
    grid(t, [CARD_W])
    borders(t, outer=0)   # no border; rounded frame is the only card outline

    # ── SECTION 0 · header · logo left, name upper-right (no fill) ────────
    row_h(t.rows[0], H_HEADER)
    c_head = t.rows[0].cells[0]
    width(c_head, CARD_W)
    pad(c_head, top=20, left=SIDE_PAD, bottom=20, right=SIDE_PAD)
    c_head.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    content_w = CARD_W - 2 * SIDE_PAD
    logo_w = 900
    title_w = content_w - logo_w
    head = c_head.add_table(rows=1, cols=2)
    tbl_width_dxa(head, content_w, center=False)
    grid(head, [logo_w, title_w])
    borders(head, outer=0)           # no border around the logo/title cells
    h_logo, h_title = head.rows[0].cells
    width(h_logo, logo_w)
    width(h_title, title_w)
    for c in (h_logo, h_title):
        c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    # Logo (the rounded frame is baked into Logo.png, so no cell border needed).
    # Zero the default cell margins so the 0.56"-wide image isn't clipped on the
    # right; a small left margin keeps it off the card frame.
    pad(h_logo, left=40, right=0, top=0, bottom=0)
    p = h_logo.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.LEFT)
    if LOGO.exists():
        p.add_run().add_picture(str(LOGO), width=Inches(0.56))
    else:
        text(p.add_run(), "LOGO", bold=True, size=6, color=(100, 100, 100))

    # Right field: car type — centered, all-caps, inside a top+bottom rule that
    # hugs the text. A left cell margin keeps the rule off the logo frame.
    pad(h_title, left=150, right=0, top=0, bottom=0)
    inner_title = title_w - 150
    type_box = h_title.add_table(rows=1, cols=1)
    tbl_width_dxa(type_box, inner_title, center=False)
    grid(type_box, [inner_title])
    borders(type_box, outer=0)
    tc = type_box.rows[0].cells[0]
    width(tc, inner_title)
    pad(tc, top=36, bottom=36)
    hrule(tc, size=INNER_BORDER, color=DIVIDER_CLR)
    p = tc.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER)
    if record is not None:
        text(p.add_run(), record.get("Type", "").upper(), bold=True, size=12)
    else:
        merge_field(p, "Type", bold=True, size=12)
    tighten_cell(h_title)

    tighten_cell(c_head)

    # ── SECTION 1 · image area (~half the card) · own inset box ───────────
    row_h(t.rows[1], H_IMAGE)
    c_img = t.rows[1].cells[0]
    width(c_img, CARD_W)
    pad(c_img, top=IMG_OUTER_PAD_TOP, left=SIDE_PAD, bottom=IMG_OUTER_PAD_BOTTOM, right=SIDE_PAD)
    c_img.vertical_alignment = WD_ALIGN_VERTICAL.TOP

    img_w = CARD_W - 2 * SIDE_PAD
    img = c_img.add_table(rows=1, cols=1)
    tbl_width_dxa(img, img_w, center=True)
    grid(img, [img_w])
    borders(img, outer=IMAGE_BORDER, color=DIVIDER_CLR)
    ic = img.rows[0].cells[0]
    width(ic, img_w)
    ic.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    pad(ic, top=IMG_INNER_PAD, bottom=IMG_INNER_PAD, left=40, right=40)
    p = ic.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER)
    if image_path is not None and Path(image_path).exists():
        p.add_run().add_picture(str(image_path), width=Inches(1.84))
    elif record is not None and record.get("Blank"):
        text(p.add_run(), "WORK ORDERS", bold=True, size=6, color=LABEL_CLR)
        orders = record.get("Orders") or []
        for line in orders:
            q = ic.add_paragraph()
            para(q, align=WD_ALIGN_PARAGRAPH.LEFT, before=3, after=0)
            text(q.add_run(), line, size=5.5, color=VALUE_CLR)
        for _ in range(max(1, 7 - len(orders))):
            q = ic.add_paragraph()
            para(q, align=WD_ALIGN_PARAGRAPH.LEFT, before=5, after=0)
            text(q.add_run(), "_" * 46, size=5.5, color=(170, 170, 170))
    else:
        text(p.add_run(), "EQUIPMENT IMAGE", size=7, color=(140, 140, 140))
        linebreak(p)
        merge_field(p, "ImagePath", size=6, color=VALUE_CLR)

    tighten_cell(c_img)

    # ── SECTION 2 · data fields · own inset box with soft dividers ────────
    row_h(t.rows[2], H_DATA_SECTION)
    c_data = t.rows[2].cells[0]
    width(c_data, CARD_W)
    pad(c_data, top=DATA_TABLE_TOP_PAD, left=SIDE_PAD, bottom=8, right=SIDE_PAD)
    c_data.vertical_alignment = WD_ALIGN_VERTICAL.TOP

    # Icon column must fit 0.15" picture (216 twips) + horizontal cell padding.
    icon_w, label_w = 340, 1040
    data_w = content_w
    value_w = data_w - icon_w - label_w

    data = c_data.add_table(rows=3, cols=3)
    tbl_width_dxa(data, data_w, center=True)
    grid(data, [icon_w, label_w, value_w])
    # Complete soft box: top + bottom match the sides and the row dividers,
    # so the whole table is framed with one consistent light line.
    borders(data, outer=INNER_BORDER, inner_h=INNER_BORDER, inner_v=0, color=DIVIDER_CLR)

    # Matching circled line-art icons (image) for each field.
    fields = [
        ("ROAD NAME:",   "RoadName",   ICON_ROAD_NAME),
        ("ROAD NUMBER:", "RoadNumber", ICON_ROAD_NUM),
        ("DESCRIPTION:", "Description", ICON_DESC),
    ]
    for ri, (label, fname, icon_path) in enumerate(fields):
        row = data.rows[ri]
        c_icon, c_lbl, c_val = row.cells
        width(c_icon, icon_w)
        pad(c_icon, top=16, left=30, bottom=10, right=30)
        c_icon.vertical_alignment = WD_ALIGN_VERTICAL.TOP
        width(c_lbl, label_w)
        pad(c_lbl, top=30, left=30, bottom=30, right=30)
        c_lbl.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        width(c_val, value_w)
        pad(c_val, top=30, left=30, bottom=30, right=30)
        c_val.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

        p = c_icon.paragraphs[0]
        para(p, align=WD_ALIGN_PARAGRAPH.CENTER, after=1.5)
        if icon_path.exists():
            p.add_run().add_picture(str(icon_path), width=Inches(0.15))
        else:
            text(p.add_run(), "\u2630", size=8, color=(120, 120, 120))

        p = c_lbl.paragraphs[0]
        para(p, align=WD_ALIGN_PARAGRAPH.LEFT)
        text(p.add_run(), label, bold=False, size=6, color=LABEL_CLR)

        p = c_val.paragraphs[0]
        para(p, align=WD_ALIGN_PARAGRAPH.LEFT)
        if record is not None:
            val = record.get(fname, "")
            if fname == "Description":
                val_size = 5.5 if len(val) > 18 else 6.5
            else:
                val_size = 9
            text(p.add_run(), val, bold=True, size=val_size, color=VALUE_CLR)
        else:
            field_size = 9 if fname in ("RoadName", "RoadNumber") else 6.5
            merge_field(p, fname, bold=True, size=field_size, color=VALUE_CLR)

    tighten_cell(c_data)

    # ── SECTION 3 · footer (no fill) ──────────────────────────────────────
    row_h(t.rows[3], H_FOOTER)
    c_ftr = t.rows[3].cells[0]
    width(c_ftr, CARD_W)
    c_ftr.vertical_alignment = WD_ALIGN_VERTICAL.TOP
    p = c_ftr.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=0)
    text(p.add_run(), "Form HART-CC-001    Rev A", size=5.5, color=(80, 80, 80))
    tighten_revision_cell(c_ftr)

    minimize_cell_tail(cell)   # keep all 9 cards on one page



def _card_images() -> CardImages:
    """The logo and icon paths as this module holds them now (tests patch them here)."""
    return CardImages(logo=LOGO, road_name=ICON_ROAD_NAME, road_num=ICON_ROAD_NUM, desc=ICON_DESC)


def build_waybill_card(cell, *, idx: int, record: dict) -> None:
    """Place one spot waybill card into a sticker-sheet slot (card_template_waybill)."""
    card_template_waybill.build_waybill_card(cell, idx=idx, record=record, images=_card_images())


def build_cc_waybill_label(cell, *, idx: int, record: dict) -> None:
    """One slim CC/WB shipment label in a poker sticker slot (card_template_waybill)."""
    card_template_waybill.build_cc_waybill_label(cell, idx=idx, record=record, images=_card_images())


def main() -> None:
    require_sticker_sheet()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(STICKER_SHEET, OUTPUT)
    doc = Document(OUTPUT)
    keep_sticker_grid(doc)

    sheet = doc.tables[0]
    for i, (r, c) in enumerate(CARD_SLOTS):
        build_card(sheet.rows[r].cells[c], advance_record=(i > 0), idx=i)

    add_document_tail(doc.element.body)
    doc.save(OUTPUT)
    print(f"Wrote {OUTPUT}")
    print("  9 cards · 3×3 sticker grid · mail-merge ready")
    if LOGO.exists():
        print(f"  Logo: {LOGO.name}")


if __name__ == "__main__":
    try:
        main()
    except car_paths.CardPipelineError as exc:
        raise SystemExit(str(exc)) from exc
