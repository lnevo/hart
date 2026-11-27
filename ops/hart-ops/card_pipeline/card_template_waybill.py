"""Spot waybill cards on the HART card layout.

Call build_waybill_card through generate_card_template: it passes the logo and icon paths it holds, so patches of
LOGO and ICON_* on that module apply. The CC/WB shipment label is in card_template_cc_label.
"""
from __future__ import annotations

from typing import Literal, NamedTuple

from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import RGBColor
from docx.table import _Cell, _Row

from waybill_data import EMPTY
from card_template_docx import (
    borders,
    bottom_rule,
    grid,
    minimize_cell_tail,
    pad,
    para,
    tbl_width_dxa,
    text,
    tighten_cell,
    width,
)
from card_template_layout import (
    DIVIDER_CLR,
    H_HEADER,
    H_IMAGE,
    IMG_OUTER_PAD_BOTTOM,
    IMG_OUTER_PAD_TOP,
    LABEL_CLR,
    VALUE_CLR,
    WORK_FLOW_COMMODITY_GAP,
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
from card_template_records import WaybillSource


def _via_interchange_label(rail: str | None) -> str:
    """Format a RouteChain token as ``Via CSX Interchange`` / ``Via POHC Interchange``."""
    rail = (rail or "").strip()
    if not rail:
        return ""
    if rail.lower().startswith("via "):
        return rail
    if rail.endswith("Interchange"):
        return f"Via {rail}"
    return f"Via {rail} Interchange"


# Work-order font sizes (points): a long line takes the smaller size so it fits the card on one line.
LOAD_SIZE_EMPTY = 10
LOAD_SIZE, LOAD_SIZE_LONG, LOAD_LONG_CHARS = 9.5, 8, 28
RETURN_SIZE, RETURN_SIZE_LONG, RETURN_LONG_CHARS = 7, 6, 28
ROUTE_SIZE, ROUTE_SIZE_LONG, ROUTE_LONG_CHARS = 6.5, 5.5, 36
VIA_SIZE, VIA_SIZE_LONG, VIA_LONG_CHARS = 6.5, 5.5, 24


class WorkLine(NamedTuple):
    """One row of a waybill's work-order block: a load line, a blank gap or a text line."""
    kind: Literal["load", "gap", "line"]
    text: str
    size: float
    bold: bool
    color: RGBColor


GAP = WorkLine("gap", "", 0, False, VALUE_CLR)


def _sized(text: str, normal: float, long: float, long_chars: int) -> float:
    """The long size for text over long_chars characters, else the normal size."""
    return long if len(text) > long_chars else normal


def _route_line(prefix: str, place: str) -> WorkLine:
    """A From: or To: line."""
    return WorkLine("line", f"{prefix}: {place}", _sized(place, ROUTE_SIZE, ROUTE_SIZE_LONG, ROUTE_LONG_CHARS),
                    False, VALUE_CLR)


def _via_line(route_chain: str) -> WorkLine:
    """The Via ... Interchange line, bold in the label colour."""
    label = _via_interchange_label(route_chain)
    return WorkLine("line", label, _sized(label, VIA_SIZE, VIA_SIZE_LONG, VIA_LONG_CHARS), True, LABEL_CLR)


def _work_lines(*, commodity: str, route_from: str, route_to: str, route_chain: str, flow: str,
                is_interchange: bool, is_outbound_empty: bool, is_inbound_empty: bool) -> list[WorkLine]:
    """The work-order block of a spot waybill, top to bottom."""
    lines: list[WorkLine] = []
    if is_outbound_empty:
        return_line = f"Return to {route_to or 'Interchange'}"
        lines.append(WorkLine("line", return_line,
                              _sized(return_line, RETURN_SIZE, RETURN_SIZE_LONG, RETURN_LONG_CHARS), False, VALUE_CLR))
        if route_chain:
            lines += [GAP, _via_line(route_chain)]
        return lines
    if is_inbound_empty:
        lines.append(WorkLine("load", EMPTY, LOAD_SIZE_EMPTY, True, VALUE_CLR))
        if route_chain:
            lines += [GAP, _via_line(route_chain)]
        return lines
    lines += [WorkLine("load", commodity, _sized(commodity, LOAD_SIZE, LOAD_SIZE_LONG, LOAD_LONG_CHARS), True,
                       VALUE_CLR), GAP]
    if is_interchange:
        if route_from:
            lines.append(_route_line("From", route_from))
        if route_to:
            lines.append(_route_line("To", route_to))
        if route_from or route_to:
            lines.append(GAP)
        if route_chain:
            lines.append(_via_line(route_chain))
    elif flow == "IN" and route_from:
        lines.append(_route_line("From", route_from))
        if route_chain:
            lines += [GAP, _via_line(route_chain)]
    elif flow == "OUT" and route_to:
        lines.append(_route_line("To", route_to))
        if route_chain:
            lines += [GAP, _via_line(route_chain)]
    return lines


class WaybillView(NamedTuple):
    """What a spot waybill card prints, read once from its record: the load, the route and which kind of card it is."""

    industry: str
    commodity: str
    route_from: str
    route_to: str
    route_chain: str
    flow: str
    is_interchange: bool
    is_empty: bool
    is_outbound_empty: bool
    is_inbound_empty: bool


def read_waybill(record: WaybillSource) -> WaybillView:
    """The card's view of a waybill record. A record with no CardKind takes its kind from the load, spots and flow."""
    commodity = record.get("Commodity", "")
    flow = record.get("Flow", "")
    kind = record.get("CardKind")
    is_empty = commodity == EMPTY
    return WaybillView(
        industry=record.get("Industry", ""),
        commodity=commodity,
        route_from=record.get("RouteFrom", record.get("Route", "")).strip(),
        route_to=record.get("RouteTo", "").strip(),
        route_chain=record.get("RouteChain", record.get("RouteVia", "")).strip(),
        flow=flow,
        is_interchange=kind == "interchange",
        is_empty=is_empty,
        is_outbound_empty=kind == "outbound_empty" or (is_empty and not record.get("Spots") and flow == "OUT"),
        is_inbound_empty=kind == "inbound_empty" or (is_empty and bool(record.get("Spots")) and flow == "IN"),
    )


WB_FORM_ID = "Form HART-WB-001    Rev A"
WORK_INNER_INSET = 80  # the work-order rows sit this much narrower than their box


def build_waybill_card(cell: _Cell, *, idx: int, record: WaybillSource, images: CardImages) -> None:
    """Place one spot waybill card into a sticker-sheet slot.

    Same rounded-frame layout as equipment cards, but the header carries the
    industry name (no HART logo) and the body holds spot/load details."""
    bill = read_waybill(record)
    card_frame(cell, idx)
    t = card_table(cell, 4)
    _waybill_title(t.rows[0], bill)
    _waybill_work_block(t.rows[1], bill)
    icon_field_section(t.rows[2], _waybill_fields(record, bill, images))
    form_footer(t.rows[3], WB_FORM_ID)
    minimize_cell_tail(cell)


def _waybill_title(row: _Row, bill: WaybillView) -> None:
    """The industry name across the top, or EMPTY on an outbound empty."""
    c_head = section(row, H_HEADER, top=24, bottom=24, valign=WD_ALIGN_VERTICAL.CENTER)
    p = ruled_title(c_head, CONTENT_W, pad_tb=36)
    title = EMPTY if bill.is_outbound_empty else bill.industry.upper()
    text(p.add_run(), title, bold=True, size=9 if len(title) > 22 else 11)
    tighten_cell(c_head)


def _work_row_pads(kind: str, *, is_empty: bool) -> tuple[int, int]:
    """Top and bottom padding of one work-order row."""
    if kind == "load":
        return 6, WORK_FLOW_COMMODITY_GAP if not is_empty else 8
    if kind == "gap":
        return 6, WORK_FLOW_COMMODITY_GAP
    return 8, 8


def _waybill_work_block(row: _Row, bill: WaybillView) -> None:
    """The boxed work-order block: the load, then the route lines (see _work_lines)."""
    c_work = section(row, H_IMAGE, top=IMG_OUTER_PAD_TOP, bottom=IMG_OUTER_PAD_BOTTOM,
                     valign=WD_ALIGN_VERTICAL.CENTER)
    work_lines = _work_lines(
        commodity=bill.commodity, route_from=bill.route_from, route_to=bill.route_to, route_chain=bill.route_chain,
        flow=bill.flow, is_interchange=bill.is_interchange, is_outbound_empty=bill.is_outbound_empty,
        is_inbound_empty=bill.is_inbound_empty,
    )
    inner = inset_box(c_work, CONTENT_W)
    inner.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    pad(inner, top=4, bottom=4, left=8, right=8)
    rows_w = CONTENT_W - WORK_INNER_INSET
    inner_tbl = inner.add_table(rows=len(work_lines), cols=1)
    tbl_width_dxa(inner_tbl, rows_w, center=True)
    grid(inner_tbl, [rows_w])
    borders(inner_tbl, outer=0)

    for i, line in enumerate(work_lines):
        row_cell = inner_tbl.rows[i].cells[0]
        width(row_cell, rows_w)
        top_pad, bottom_pad = _work_row_pads(line.kind, is_empty=bill.is_empty)
        pad(row_cell, top=top_pad, bottom=bottom_pad, left=40, right=40)
        row_cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        next_is_line = i + 1 < len(work_lines) and work_lines[i + 1].kind == "line"
        if (line.kind == "load" and not bill.is_empty) or (line.kind == "line" and next_is_line):
            bottom_rule(row_cell, size=4, color=DIVIDER_CLR)
        p = row_cell.paragraphs[0]
        para(p, align=WD_ALIGN_PARAGRAPH.CENTER)
        if line.text:
            text(p.add_run(), line.text, bold=line.bold, size=line.size, color=line.color)

    tighten_cell(inner)
    tighten_cell(c_work)


def _waybill_value_size(key: str, value: str) -> float:
    """Value font size by field, smaller for a long value."""
    if key in ("Commodity", "LoadSummary"):
        return 5.5 if len(value) > 22 else 6.5
    if key == "Spots":
        return 9
    return 7 if len(value) > 16 else 8


def _waybill_fields(record: WaybillSource, bill: WaybillView, images: CardImages) -> list[IconField]:
    """An outbound empty shows only its load; every other card its spots, car type and load."""
    if bill.is_outbound_empty:
        rows = [("LOAD:", "Commodity", record.get("Commodity", ""), images.desc)]
    else:
        rows = [
            ("SPOT(S):", "Spots", record.get("Spots", ""), images.road_num),
            ("CAR TYPE:", "CarType", record.get("CarType", ""), images.road_name),
            ("LOAD:", "LoadSummary", record.get("LoadSummary") or record.get("Commodity", ""), images.desc),
        ]
    return [IconField(label, icon, value, _waybill_value_size(key, value)) for label, key, value, icon in rows]
