"""The sections every HART sticker card shares: the rounded frame, the one-column body table, a section row, the
ruled title box, the bordered inset box, the icon field table and the form footer.

The equipment card (generate_card_template.build_card), the spot waybill and the CC/WB label
(card_template_waybill, card_template_cc_label) are built from these, so a change here reaches all three. Each helper writes its cell
properties in one fixed order, as Word stores them in that order.
"""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt
from docx.table import Table, _Cell, _Row
from docx.text.paragraph import Paragraph

from card_template_docx import (
    add_round_frame,
    borders,
    grid,
    hrule,
    merge_field,
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
    IMAGE_BORDER,
    INNER_BORDER,
    LABEL_CLR,
    PAGE2_SLOT_W,
    SIDE_PAD,
    SLOT_W,
    TARGET_FRAME_W,
    VALUE_CLR,
)

# The rounded frame stays inside the 3.35" sticker slot, so the bottom row (with no card below to mask an overhang)
# fits, while still clearing the footer line; it is 1/32" taller at the bottom than the 3.16" card.
FRAME_W_PT = (TARGET_FRAME_W + 2 * FRAME_GROW_TWIPS) / 20.0
FRAME_H_PT = 3.16 * 72.0 + FRAME_GROW_PT
FRAME_LEFT_PT = (FRAME_MARGIN - FRAME_GROW_TWIPS) / 20.0
FRAME_TOP_PT = 1.0

CONTENT_W = CARD_W - 2 * SIDE_PAD
# The icon column fits the 0.15" picture (216 twips) and its cell padding.
ICON_W, LABEL_W = 340, 1040
FOOTER_CLR = (80, 80, 80)


class CardImages(NamedTuple):
    """Logo and icon paths a builder draws; a missing file gets a text placeholder."""
    logo: Path
    road_name: Path
    road_num: Path
    desc: Path


class IconField(NamedTuple):
    """One row of a card's icon / label / value table. With ``merge`` the value is a MERGEFIELD name."""

    label: str
    icon: Path
    value: str
    size: float
    merge: bool = False


def card_frame(cell: _Cell, idx: int, *, advance_record: bool = False) -> None:
    """Clear the slot, shift the card into the wider page-4 slot and anchor the rounded frame on a 1 pt lead paragraph.

    The internal margins (content vs frame) stay as on the page-2 grid. With ``advance_record`` the lead paragraph
    also holds the mail merge's NEXT field. ``idx`` gives the frame shape its id.
    """
    cell.text = ""
    side_gap = SLOT_W - PAGE2_SLOT_W - CENTER_OFFSET
    pad(cell, top=CARD_TOP_PAD, left=CENTER_OFFSET, right=side_gap)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP

    lead = cell.paragraphs[0]
    para(lead, after=2)
    lead.paragraph_format.line_spacing = Pt(1)
    if advance_record:
        next_record(lead)
    for r in lead.runs:
        r.font.size = Pt(1)
    add_round_frame(lead, idx, width_pt=FRAME_W_PT, height_pt=FRAME_H_PT, left_pt=FRAME_LEFT_PT, top_pt=FRAME_TOP_PT)


def card_table(cell: _Cell, rows: int) -> Table:
    """The card's borderless one-column body table; the rounded frame is the only outline."""
    t = cell.add_table(rows=rows, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_width_dxa(t, CARD_W, center=True)
    grid(t, [CARD_W])
    borders(t, outer=0)
    return t


def section(row: _Row, height: int, *, top: int, bottom: int, valign: WD_ALIGN_VERTICAL,
            left: int = SIDE_PAD, right: int = SIDE_PAD) -> _Cell:
    """Size one body row and return its cell, padded and aligned."""
    row_h(row, height)
    cell = row.cells[0]
    width(cell, CARD_W)
    pad(cell, top=top, left=left, bottom=bottom, right=right)
    cell.vertical_alignment = valign
    return cell


def ruled_title(cell: _Cell, inner_w: int, *, pad_tb: int) -> Paragraph:
    """A one-cell box with a rule above and below, centred; returns its paragraph for the title text."""
    box = cell.add_table(rows=1, cols=1)
    tbl_width_dxa(box, inner_w, center=False)
    grid(box, [inner_w])
    borders(box, outer=0)
    tc = box.rows[0].cells[0]
    width(tc, inner_w)
    pad(tc, top=pad_tb, bottom=pad_tb)
    hrule(tc, size=INNER_BORDER, color=DIVIDER_CLR)
    p = tc.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER)
    return p


def inset_box(cell: _Cell, box_w: int) -> _Cell:
    """A centred one-cell table with the card's image border; returns its cell, sized but not yet padded."""
    box = cell.add_table(rows=1, cols=1)
    tbl_width_dxa(box, box_w, center=True)
    grid(box, [box_w])
    borders(box, outer=IMAGE_BORDER, color=DIVIDER_CLR)
    inner = box.rows[0].cells[0]
    width(inner, box_w)
    return inner


def _icon(p: Paragraph, icon: Path) -> None:
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER, after=1.5)
    if icon.exists():
        p.add_run().add_picture(str(icon), width=Inches(0.15))
    else:
        text(p.add_run(), "☰", size=8, color=(120, 120, 120))


def icon_field_section(row: _Row, fields: Sequence[IconField]) -> None:
    """The data section: a soft-ruled table of icon, label and value, one row per field."""
    c_data = section(row, H_DATA_SECTION, top=DATA_TABLE_TOP_PAD, bottom=8, valign=WD_ALIGN_VERTICAL.TOP)
    value_w = CONTENT_W - ICON_W - LABEL_W
    data = c_data.add_table(rows=len(fields), cols=3)
    tbl_width_dxa(data, CONTENT_W, center=True)
    grid(data, [ICON_W, LABEL_W, value_w])
    # A complete soft box: top and bottom match the sides and the row dividers.
    borders(data, outer=INNER_BORDER, inner_h=INNER_BORDER, inner_v=0, color=DIVIDER_CLR)

    for ri, field in enumerate(fields):
        c_icon, c_lbl, c_val = data.rows[ri].cells
        width(c_icon, ICON_W)
        pad(c_icon, top=16, left=30, bottom=10, right=30)
        c_icon.vertical_alignment = WD_ALIGN_VERTICAL.TOP
        width(c_lbl, LABEL_W)
        pad(c_lbl, top=30, left=30, bottom=30, right=30)
        c_lbl.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        width(c_val, value_w)
        pad(c_val, top=30, left=30, bottom=30, right=30)
        c_val.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

        _icon(c_icon.paragraphs[0], field.icon)

        p = c_lbl.paragraphs[0]
        para(p, align=WD_ALIGN_PARAGRAPH.LEFT)
        text(p.add_run(), field.label, bold=False, size=6, color=LABEL_CLR)

        p = c_val.paragraphs[0]
        para(p, align=WD_ALIGN_PARAGRAPH.LEFT)
        if field.merge:
            merge_field(p, field.value, bold=True, size=field.size, color=VALUE_CLR)
        else:
            text(p.add_run(), field.value, bold=True, size=field.size, color=VALUE_CLR)

    tighten_cell(c_data)


def form_footer(row: _Row, form_id: str) -> None:
    """The footer row with the card's form number."""
    row_h(row, H_FOOTER)
    c_ftr = row.cells[0]
    width(c_ftr, CARD_W)
    c_ftr.vertical_alignment = WD_ALIGN_VERTICAL.TOP
    p = c_ftr.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=0)
    text(p.add_run(), form_id, size=5.5, color=FOOTER_CLR)
    tighten_revision_cell(c_ftr)
