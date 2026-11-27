"""CC/WB shipment labels on the HART card layout: one bill (empty or freight) per poker sticker.

Call build_cc_waybill_label through generate_card_template: it passes the logo and icon paths it holds, so patches
of LOGO and ICON_* on that module apply.
"""
from __future__ import annotations

import functools
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt
from docx.table import _Cell, _Row
from docx.text.paragraph import Paragraph

import car_paths  # noqa: F401  (puts publications/ on sys.path for crew_master)
import crew_master
from card_template_docx import (
    _tighten_paragraph,
    borders,
    grid,
    minimize_cell_tail,
    pad,
    para,
    row_h,
    shade,
    split_on_commas,
    tbl_width_dxa,
    text,
    tighten_cell,
    width,
    write_label_lines,
)
from card_template_layout import (
    CARD_W,
    DIVIDER_CLR,
    H_DATA_SECTION,
    H_HEADER,
    INNER_BORDER,
    LABEL_CLR,
    SIDE_PAD,
    VALUE_CLR,
)
from card_template_parts import (
    CONTENT_W,
    FRAME_H_PT,
    CardImages,
    card_frame,
    card_table,
    inset_box,
    ruled_title,
    section,
)
from card_template_records import CcLabelRecord


# STS location colour names → RRGGBB, as the STS shipment-label palette has them. The names the crew master
# (ops/hart-ops/data/crew.json) also has take its fill; STS's mediumblue is the master's blue. The rest are STS-only.
_STS_NAME_TO_MASTER_ID: dict[str, str] = {
    "pink": "pink", "red": "red", "orange": "orange", "yellow": "yellow", "green": "green",
    "mediumblue": "blue", "purple": "purple", "black": "black",
}
_STS_ONLY_HEX: dict[str, str] = {"lightblue": "ADD8E6", "lightgrey": "D3D3D3", "white": "FFFFFF"}


@functools.cache
def sts_color_hex() -> dict[str, str]:
    """STS location colour name → RRGGBB fill, the master's fills first."""
    swatch = crew_master.swatches(crew_master.load())
    return {**{name: swatch[cid].fill for name, cid in _STS_NAME_TO_MASTER_ID.items()}, **_STS_ONLY_HEX}


class CcField(NamedTuple):
    """One row of a CC/WB label's data table: its label and the value lines under it."""
    label: str
    lines: list[str]


# CC/WB label rows, top to bottom, in twips. The flex spacer (row 4) takes what the frame has left, so the
# shipment id and the form id sit at fixed distances from the bottom of the card.
CC_H_HEADER = H_HEADER - 40
CC_H_ACCENT = 90
CC_H_DEST = 1180
CC_H_DEST_WRAPPED = 1320  # a station that wraps after a comma (e.g. "…, Chemical Unload")
CC_H_BODY = H_DATA_SECTION + 80
CC_H_SHIP = 160
CC_H_SHIP_TO_FORM = 280
CC_H_FORM = 120
CC_H_SPACER_MIN = 40
# The frame's inner height, with a small clearance above the rounded frame stroke.
CC_FRAME_H_PT = FRAME_H_PT
CC_FRAME_CONTENT_TWIPS = int(round(CC_FRAME_H_PT * 20)) - 160
CC_LOGO_W = 820
CC_FIELD_LABEL_W = 1100
CC_FORM_ID = "Form HART-CCWB-001"


def _cc_track_spot(record: CcLabelRecord) -> str:
    """The TRACK / SPOT line: STAGING · IN/OUT for staging flows, else track · spot, else whichever is set, else —."""
    track = record.get("Track", "")
    spot = record.get("Spot", "")
    flow = (record.get("Flow") or "").strip().upper()
    if track.lower() == "staging" and flow in {"IN", "OUT"}:
        return f"STAGING  ·  {flow}"
    if track and spot:
        return f"{track}  ·  {spot}"
    return track or spot or "—"


def _cc_fields(record: CcLabelRecord, *, is_empty: bool) -> list[CcField]:
    """The data-table rows: an empty bill names what to load, a freight bill what it carries and from where."""
    if is_empty:
        return [
            CcField("ASSIGNMENT", ["Empty car to load"]),
            CcField("CAR TYPE", [record.get("CarCode", "") or "—"]),
            CcField("LOADS", [record.get("Consignment", "") or "—"]),
            CcField("SHIPMENT", split_on_commas(record.get("Description", "")) or ["—"]),
        ]
    return [
        CcField("CONTENTS", [record.get("Consignment", "") or "—"]),
        CcField("CAR TYPE", [record.get("CarCode", "") or "—"]),
        CcField("FROM", [record.get("FromLocation", "") or "—"]),
        CcField("FROM STA.", split_on_commas(record.get("FromStation", "")) or ["—"]),
    ]


def _cc_value_size(value_lines: Sequence[str]) -> float:
    """Value font size: smaller for longer text, so a value fits its cell."""
    measure = " ".join(value_lines)
    return 5.5 if len(measure) > 28 else (6.5 if len(measure) > 18 else 7.5)


def _cc_header(row: _Row, record: CcLabelRecord, images: CardImages, *, is_empty: bool) -> None:
    """The logo (the party's own, else HART's, else the word HART) beside the EMPTY or FREIGHT title."""
    c_head = section(row, CC_H_HEADER, top=16, bottom=8, valign=WD_ALIGN_VERTICAL.CENTER)
    title_w = CONTENT_W - CC_LOGO_W
    head = c_head.add_table(rows=1, cols=2)
    tbl_width_dxa(head, CONTENT_W, center=False)
    grid(head, [CC_LOGO_W, title_w])
    borders(head, outer=0)
    h_logo, h_title = head.rows[0].cells
    width(h_logo, CC_LOGO_W)
    width(h_title, title_w)
    pad(h_logo, left=30, right=0, top=0, bottom=0)
    h_logo.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    p = h_logo.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.LEFT)
    party_logo = Path(record.get("LogoPath") or "")
    if party_logo.is_file():
        p.add_run().add_picture(str(party_logo), width=Inches(0.52))
    elif images.logo.exists():
        p.add_run().add_picture(str(images.logo), width=Inches(0.48))
    else:
        text(p.add_run(), "HART", bold=True, size=7)

    pad(h_title, left=80, right=0, top=0, bottom=0)
    h_title.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    p = ruled_title(h_title, title_w - 80, pad_tb=28)
    text(p.add_run(), "EMPTY" if is_empty else "FREIGHT", bold=True, size=11)
    tighten_cell(c_head)


def _cc_accent_bar(row: _Row, accent: str) -> None:
    """A bar in the STS location colour."""
    row_h(row, CC_H_ACCENT)
    c_bar = row.cells[0]
    width(c_bar, CARD_W)
    pad(c_bar, top=0, bottom=0, left=SIDE_PAD, right=SIDE_PAD)
    shade(c_bar, accent)
    c_bar.paragraphs[0].paragraph_format.space_after = Pt(0)


def _dest_line(p: Paragraph, label: str, lines: Sequence[str], *, bold: bool, size: float) -> None:
    """One centred line of the destination box: the grey label, then the value lines with breaks between them."""
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=1, after=1)
    text(p.add_run(), label, bold=True, size=6, color=LABEL_CLR)
    for i, line in enumerate(lines):
        if i:
            p.add_run().add_break()
        text(p.add_run(), line, bold=bold, size=size, color=VALUE_CLR)


def _cc_destination(row: _Row, record: CcLabelRecord) -> int:
    """The boxed TO / STATION / TRACK-SPOT block; returns the row height it took."""
    station_lines = split_on_commas(record.get("Station", ""))
    h_dest = CC_H_DEST_WRAPPED if len(station_lines) > 1 else CC_H_DEST
    row_h(row, h_dest)
    c_dest = row.cells[0]
    width(c_dest, CARD_W)
    pad(c_dest, top=40, left=SIDE_PAD, bottom=20, right=SIDE_PAD)
    dest_w = CARD_W - 2 * SIDE_PAD
    inner = inset_box(c_dest, dest_w)
    pad(inner, top=50, bottom=50, left=60, right=60)
    inner.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    _dest_line(inner.paragraphs[0], "TO: ", [record.get("ToLocation", "") or "—"], bold=True, size=9)
    _dest_line(inner.add_paragraph(), "STATION: ", station_lines or ["—"], bold=False, size=7)
    _dest_line(inner.add_paragraph(), "TRACK / SPOT: ", [_cc_track_spot(record)], bold=False, size=7)
    tighten_cell(c_dest)
    return h_dest


def _cc_body(row: _Row, fields: Sequence[CcField]) -> None:
    """The label / value table of the bill's contents and routing."""
    row_h(row, CC_H_BODY)
    c_body = row.cells[0]
    width(c_body, CARD_W)
    pad(c_body, top=30, left=SIDE_PAD, bottom=10, right=SIDE_PAD)

    body_w = CARD_W - 2 * SIDE_PAD
    value_w = body_w - CC_FIELD_LABEL_W
    data = c_body.add_table(rows=len(fields), cols=2)
    tbl_width_dxa(data, body_w, center=True)
    grid(data, [CC_FIELD_LABEL_W, value_w])
    borders(data, outer=INNER_BORDER, inner_h=INNER_BORDER, inner_v=0, color=DIVIDER_CLR)

    for ri, field in enumerate(fields):
        c_lbl, c_val = data.rows[ri].cells
        width(c_lbl, CC_FIELD_LABEL_W)
        width(c_val, value_w)
        pad(c_lbl, top=24, bottom=24, left=40, right=20)
        pad(c_val, top=24, bottom=24, left=30, right=30)
        c_lbl.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        c_val.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        p = c_lbl.paragraphs[0]
        para(p, align=WD_ALIGN_PARAGRAPH.LEFT)
        text(p.add_run(), field.label, bold=False, size=6, color=LABEL_CLR)
        p = c_val.paragraphs[0]
        para(p, align=WD_ALIGN_PARAGRAPH.LEFT)
        write_label_lines(p, field.lines, bold=True, size=_cc_value_size(field.lines), color=VALUE_CLR)
    tighten_cell(c_body)


def _cc_blank_row(row: _Row, height: int) -> None:
    """An empty row of exactly height twips."""
    row_h(row, height)
    c_gap = row.cells[0]
    width(c_gap, CARD_W)
    pad(c_gap, top=0, bottom=0, left=0, right=0)
    _tighten_paragraph(c_gap.paragraphs[0], 20)


def _cc_shipment(row: _Row, record: CcLabelRecord) -> None:
    """The shipment code, or a grey dash when the record has none."""
    c_ship = section(row, CC_H_SHIP, top=0, bottom=0, valign=WD_ALIGN_VERTICAL.CENTER)
    code = (record.get("ShipmentCode") or "").strip()
    p = c_ship.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=0)
    if code:
        text(p.add_run(), code, bold=True, size=7.5, color=VALUE_CLR)
    else:
        text(p.add_run(), "—", bold=True, size=7.5, color=(120, 120, 120))


def _cc_form_footer(row: _Row) -> None:
    """The form id at the foot of the label."""
    c_form = section(row, CC_H_FORM, top=0, bottom=6, valign=WD_ALIGN_VERTICAL.BOTTOM)
    p = c_form.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=0)
    text(p.add_run(), CC_FORM_ID, size=5, color=(100, 100, 100))


def build_cc_waybill_label(cell: _Cell, *, idx: int, record: CcLabelRecord, images: CardImages) -> None:
    """One slim CC/WB shipment label (empty or freight) in a poker sticker slot.

    Mirrors STS ``printable_ccwaybill.php`` / ``build_cc_*.php`` fields, but
    sized for the same Apostrophe card template as equipment cards — one bill
    per label (empty and freight are separate cards). Rows: header, accent bar,
    destination, data table, flex spacer, shipment id, fixed gap, form id.
    """
    card_frame(cell, idx)
    is_empty = (record.get("BillKind") or "freight").lower() == "empty"
    accent = sts_color_hex().get((record.get("Color") or "").strip().lower(), DIVIDER_CLR)

    t = card_table(cell, 8)

    _cc_header(t.rows[0], record, images, is_empty=is_empty)
    _cc_accent_bar(t.rows[1], accent)
    h_dest = _cc_destination(t.rows[2], record)
    _cc_body(t.rows[3], _cc_fields(record, is_empty=is_empty))
    used = CC_H_HEADER + CC_H_ACCENT + h_dest + CC_H_BODY + CC_H_SHIP + CC_H_SHIP_TO_FORM + CC_H_FORM
    _cc_blank_row(t.rows[4], max(CC_H_SPACER_MIN, CC_FRAME_CONTENT_TWIPS - used))
    _cc_shipment(t.rows[5], record)
    _cc_blank_row(t.rows[6], CC_H_SHIP_TO_FORM)
    _cc_form_footer(t.rows[7])
    minimize_cell_tail(cell)
