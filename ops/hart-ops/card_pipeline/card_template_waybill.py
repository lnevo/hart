"""Spot waybill cards and CC/WB shipment labels on the HART card layout.

Call these through generate_card_template (build_waybill_card, build_cc_waybill_label):
it passes the logo and icon paths it holds, so patches of LOGO and ICON_* on that module
apply.
"""

import functools
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal, NamedTuple

from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from docx.table import _Cell, _Row

import car_paths  # noqa: F401  (puts publications/ on sys.path for crew_master)
import crew_master
from waybill_data import EMPTY
from card_template_docx import (
    _tighten_paragraph,
    add_round_frame,
    borders,
    bottom_rule,
    grid,
    hrule,
    minimize_cell_tail,
    pad,
    para,
    row_h,
    shade,
    split_on_commas,
    tbl_width_dxa,
    text,
    tighten_cell,
    tighten_revision_cell,
    width,
    write_label_lines,
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
    H_HEADER,
    H_IMAGE,
    IMAGE_BORDER,
    IMG_OUTER_PAD_BOTTOM,
    IMG_OUTER_PAD_TOP,
    INNER_BORDER,
    LABEL_CLR,
    PAGE2_SLOT_W,
    SIDE_PAD,
    SLOT_W,
    TARGET_FRAME_W,
    VALUE_CLR,
    WORK_FLOW_COMMODITY_GAP,
)


class CardImages(NamedTuple):
    """Logo and icon paths a builder draws; a missing file gets a text placeholder."""
    logo: Path
    road_name: Path
    road_num: Path
    desc: Path


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
    return long if len(text) > long_chars else normal


def _route_line(prefix: str, place: str) -> WorkLine:
    return WorkLine("line", f"{prefix}: {place}", _sized(place, ROUTE_SIZE, ROUTE_SIZE_LONG, ROUTE_LONG_CHARS),
                    False, VALUE_CLR)


def _via_line(route_chain: str) -> WorkLine:
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


def build_waybill_card(cell, *, idx: int, record: dict, images: CardImages) -> None:
    """Place one spot waybill card into a sticker-sheet slot.

    Same rounded-frame layout as equipment cards, but the header carries the
    industry name (no HART logo) and the body holds spot/load details."""
    cell.text = ""
    side_gap = SLOT_W - PAGE2_SLOT_W - CENTER_OFFSET
    pad(cell, top=CARD_TOP_PAD, left=CENTER_OFFSET, right=side_gap)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP

    lead = cell.paragraphs[0]
    para(lead, after=2)
    lead.paragraph_format.line_spacing = Pt(1)
    for r in lead.runs:
        r.font.size = Pt(1)

    frame_w_pt = (TARGET_FRAME_W + 2 * FRAME_GROW_TWIPS) / 20.0
    frame_h_pt = 3.16 * 72.0 + FRAME_GROW_PT
    frame_left_pt = (FRAME_MARGIN - FRAME_GROW_TWIPS) / 20.0
    add_round_frame(
        lead,
        idx,
        width_pt=frame_w_pt,
        height_pt=frame_h_pt,
        left_pt=frame_left_pt,
        top_pt=1.0,
    )

    t = cell.add_table(rows=4, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_width_dxa(t, CARD_W, center=True)
    grid(t, [CARD_W])
    borders(t, outer=0)

    commodity = record.get("Commodity", "")
    route_from = record.get("RouteFrom", record.get("Route", "")).strip()
    route_to = record.get("RouteTo", "").strip()
    route_chain = record.get("RouteChain", record.get("RouteVia", "")).strip()
    flow = record.get("Flow", "")
    is_interchange = record.get("CardKind") == "interchange"
    is_empty = commodity == EMPTY
    is_outbound_empty = record.get("CardKind") == "outbound_empty" or (
        is_empty and not record.get("Spots") and flow == "OUT"
    )
    is_inbound_empty = record.get("CardKind") == "inbound_empty" or (
        is_empty and bool(record.get("Spots")) and flow == "IN"
    )

    # ── SECTION 0 · industry name across the top ─────────────────────────
    row_h(t.rows[0], H_HEADER)
    c_head = t.rows[0].cells[0]
    width(c_head, CARD_W)
    pad(c_head, top=24, left=SIDE_PAD, bottom=24, right=SIDE_PAD)
    c_head.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    inner_w = CARD_W - 2 * SIDE_PAD
    title_box = c_head.add_table(rows=1, cols=1)
    tbl_width_dxa(title_box, inner_w, center=False)
    grid(title_box, [inner_w])
    borders(title_box, outer=0)
    tc = title_box.rows[0].cells[0]
    width(tc, inner_w)
    pad(tc, top=36, bottom=36)
    hrule(tc, size=INNER_BORDER, color=DIVIDER_CLR)
    p = tc.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER)
    industry = record.get("Industry", "")
    title = EMPTY if is_outbound_empty else industry.upper()
    title_size = 9 if len(title) > 22 else 11
    text(p.add_run(), title, bold=True, size=title_size)
    tighten_cell(c_head)

    # ── SECTION 1 · flow + commodity work-order block ────────────────────
    row_h(t.rows[1], H_IMAGE)
    c_work = t.rows[1].cells[0]
    width(c_work, CARD_W)
    pad(c_work, top=IMG_OUTER_PAD_TOP, left=SIDE_PAD, bottom=IMG_OUTER_PAD_BOTTOM, right=SIDE_PAD)
    c_work.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    work_w = CARD_W - 2 * SIDE_PAD
    work = c_work.add_table(rows=1, cols=1)
    tbl_width_dxa(work, work_w, center=True)
    grid(work, [work_w])
    borders(work, outer=IMAGE_BORDER, color=DIVIDER_CLR)

    work_lines = _work_lines(
        commodity=commodity, route_from=route_from, route_to=route_to, route_chain=route_chain, flow=flow,
        is_interchange=is_interchange, is_outbound_empty=is_outbound_empty, is_inbound_empty=is_inbound_empty,
    )

    inner = work.rows[0].cells[0]
    width(inner, work_w)
    inner.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    pad(inner, top=4, bottom=4, left=8, right=8)
    inner_tbl = inner.add_table(rows=len(work_lines), cols=1)
    tbl_width_dxa(inner_tbl, work_w - 80, center=True)
    grid(inner_tbl, [work_w - 80])
    borders(inner_tbl, outer=0)

    for i, (kind, line, size, bold, color) in enumerate(work_lines):
        row_cell = inner_tbl.rows[i].cells[0]
        width(row_cell, work_w - 80)
        if kind == "load":
            top_pad, bottom_pad = 6, WORK_FLOW_COMMODITY_GAP if not is_empty else 8
        elif kind == "gap":
            top_pad, bottom_pad = 6, WORK_FLOW_COMMODITY_GAP
        else:
            top_pad, bottom_pad = 8, 8
        pad(row_cell, top=top_pad, bottom=bottom_pad, left=40, right=40)
        row_cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        if kind == "load" and not is_empty:
            bottom_rule(row_cell, size=4, color=DIVIDER_CLR)
        elif kind == "line" and i + 1 < len(work_lines):
            next_kind = work_lines[i + 1][0]
            if next_kind == "line":
                bottom_rule(row_cell, size=4, color=DIVIDER_CLR)
        p = row_cell.paragraphs[0]
        para(p, align=WD_ALIGN_PARAGRAPH.CENTER)
        if line:
            text(p.add_run(), line, bold=bold, size=size, color=color)

    tighten_cell(inner)
    tighten_cell(c_work)

    # ── SECTION 2 · spot / car type / load table ─────────────────────────
    row_h(t.rows[2], H_DATA_SECTION)
    c_data = t.rows[2].cells[0]
    width(c_data, CARD_W)
    pad(c_data, top=DATA_TABLE_TOP_PAD, left=SIDE_PAD, bottom=8, right=SIDE_PAD)
    c_data.vertical_alignment = WD_ALIGN_VERTICAL.TOP

    content_w = CARD_W - 2 * SIDE_PAD
    icon_w, label_w = 340, 1040
    value_w = content_w - icon_w - label_w

    if is_outbound_empty:
        fields = [("LOAD:", "Commodity", images.desc)]
    else:
        fields = [
            ("SPOT(S):", "Spots", images.road_num),
            ("CAR TYPE:", "CarType", images.road_name),
            ("LOAD:", "LoadSummary", images.desc),
        ]

    data = c_data.add_table(rows=len(fields), cols=3)
    tbl_width_dxa(data, content_w, center=True)
    grid(data, [icon_w, label_w, value_w])
    borders(data, outer=INNER_BORDER, inner_h=INNER_BORDER, inner_v=0, color=DIVIDER_CLR)

    for ri, (label, key, icon_path) in enumerate(fields):
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
        if key == "LoadSummary":
            val = record.get("LoadSummary") or record.get("Commodity", "")
        else:
            val = record.get(key, "")
        if key in ("Commodity", "LoadSummary"):
            val_size = 5.5 if len(val) > 22 else 6.5
        elif key == "Spots":
            val_size = 9
        else:
            val_size = 7 if len(val) > 16 else 8
        text(p.add_run(), val, bold=True, size=val_size, color=VALUE_CLR)

    tighten_cell(c_data)

    # ── SECTION 3 · footer ─────────────────────────────────────────────
    row_h(t.rows[3], H_FOOTER)
    c_ftr = t.rows[3].cells[0]
    width(c_ftr, CARD_W)
    c_ftr.vertical_alignment = WD_ALIGN_VERTICAL.TOP
    p = c_ftr.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=0)
    text(p.add_run(), "Form HART-WB-001    Rev A", size=5.5, color=(80, 80, 80))
    tighten_revision_cell(c_ftr)

    minimize_cell_tail(cell)


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
CC_FRAME_H_PT = 3.16 * 72.0 + FRAME_GROW_PT
CC_FRAME_CONTENT_TWIPS = int(round(CC_FRAME_H_PT * 20)) - 160
CC_LOGO_W = 820
CC_FIELD_LABEL_W = 1100
CC_FORM_ID = "Form HART-CCWB-001"


def _cc_track_spot(record: Mapping[str, str]) -> str:
    """The TRACK / SPOT line: STAGING · IN/OUT for staging flows, else track · spot, else whichever is set, else —."""
    track = record.get("Track", "")
    spot = record.get("Spot", "")
    flow = (record.get("Flow") or "").strip().upper()
    if track.lower() == "staging" and flow in {"IN", "OUT"}:
        return f"STAGING  ·  {flow}"
    if track and spot:
        return f"{track}  ·  {spot}"
    return track or spot or "—"


def _cc_fields(record: Mapping[str, str], *, is_empty: bool) -> list[CcField]:
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


def _cc_frame(cell: _Cell, idx: int) -> None:
    """Clear the slot, pad it like the equipment cards and anchor the rounded frame on a 1 pt lead paragraph."""
    cell.text = ""
    side_gap = SLOT_W - PAGE2_SLOT_W - CENTER_OFFSET
    pad(cell, top=CARD_TOP_PAD, left=CENTER_OFFSET, right=side_gap)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP

    lead = cell.paragraphs[0]
    para(lead, after=2)
    lead.paragraph_format.line_spacing = Pt(1)
    for r in lead.runs:
        r.font.size = Pt(1)
    add_round_frame(
        lead,
        idx,
        width_pt=(TARGET_FRAME_W + 2 * FRAME_GROW_TWIPS) / 20.0,
        height_pt=CC_FRAME_H_PT,
        left_pt=(FRAME_MARGIN - FRAME_GROW_TWIPS) / 20.0,
        top_pt=1.0,
    )


def _cc_header(row: _Row, record: Mapping[str, str], images: CardImages, *, is_empty: bool) -> None:
    """The logo (the party's own, else HART's, else the word HART) beside the EMPTY or FREIGHT title."""
    row_h(row, CC_H_HEADER)
    c_head = row.cells[0]
    width(c_head, CARD_W)
    pad(c_head, top=16, left=SIDE_PAD, bottom=8, right=SIDE_PAD)
    c_head.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    content_w = CARD_W - 2 * SIDE_PAD
    title_w = content_w - CC_LOGO_W
    head = c_head.add_table(rows=1, cols=2)
    tbl_width_dxa(head, content_w, center=False)
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
    title_box = h_title.add_table(rows=1, cols=1)
    inner_title = title_w - 80
    tbl_width_dxa(title_box, inner_title, center=False)
    grid(title_box, [inner_title])
    borders(title_box, outer=0)
    tc = title_box.rows[0].cells[0]
    width(tc, inner_title)
    pad(tc, top=28, bottom=28)
    hrule(tc, size=INNER_BORDER, color=DIVIDER_CLR)
    p = tc.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER)
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


def _cc_destination(row: _Row, record: Mapping[str, str]) -> int:
    """The boxed TO / STATION / TRACK-SPOT block; returns the row height it took."""
    station_lines = split_on_commas(record.get("Station", ""))
    h_dest = CC_H_DEST_WRAPPED if len(station_lines) > 1 else CC_H_DEST
    row_h(row, h_dest)
    c_dest = row.cells[0]
    width(c_dest, CARD_W)
    pad(c_dest, top=40, left=SIDE_PAD, bottom=20, right=SIDE_PAD)
    dest_w = CARD_W - 2 * SIDE_PAD
    dest = c_dest.add_table(rows=1, cols=1)
    tbl_width_dxa(dest, dest_w, center=True)
    grid(dest, [dest_w])
    borders(dest, outer=IMAGE_BORDER, color=DIVIDER_CLR)
    inner = dest.rows[0].cells[0]
    width(inner, dest_w)
    pad(inner, top=50, bottom=50, left=60, right=60)
    inner.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    p = inner.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=1, after=1)
    text(p.add_run(), "TO: ", bold=True, size=6, color=LABEL_CLR)
    text(p.add_run(), record.get("ToLocation", "") or "—", bold=True, size=9, color=VALUE_CLR)

    p = inner.add_paragraph()
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=1, after=1)
    text(p.add_run(), "STATION: ", bold=True, size=6, color=LABEL_CLR)
    if station_lines:
        text(p.add_run(), station_lines[0], bold=False, size=7, color=VALUE_CLR)
        for cont in station_lines[1:]:
            p.add_run().add_break()
            text(p.add_run(), cont, bold=False, size=7, color=VALUE_CLR)
    else:
        text(p.add_run(), "—", bold=False, size=7, color=VALUE_CLR)

    p = inner.add_paragraph()
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=1, after=1)
    text(p.add_run(), "TRACK / SPOT: ", bold=True, size=6, color=LABEL_CLR)
    text(p.add_run(), _cc_track_spot(record), bold=False, size=7, color=VALUE_CLR)
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


def _cc_shipment(row: _Row, record: Mapping[str, str]) -> None:
    """The shipment code, or a grey dash when the record has none."""
    row_h(row, CC_H_SHIP)
    c_ship = row.cells[0]
    width(c_ship, CARD_W)
    pad(c_ship, top=0, bottom=0, left=SIDE_PAD, right=SIDE_PAD)
    c_ship.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    code = (record.get("ShipmentCode") or "").strip()
    p = c_ship.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=0)
    if code:
        text(p.add_run(), code, bold=True, size=7.5, color=VALUE_CLR)
    else:
        text(p.add_run(), "—", bold=True, size=7.5, color=(120, 120, 120))


def _cc_form_footer(row: _Row) -> None:
    row_h(row, CC_H_FORM)
    c_form = row.cells[0]
    width(c_form, CARD_W)
    pad(c_form, top=0, bottom=6, left=SIDE_PAD, right=SIDE_PAD)
    c_form.vertical_alignment = WD_ALIGN_VERTICAL.BOTTOM
    p = c_form.paragraphs[0]
    para(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=0)
    text(p.add_run(), CC_FORM_ID, size=5, color=(100, 100, 100))


def build_cc_waybill_label(cell: _Cell, *, idx: int, record: Mapping[str, str], images: CardImages) -> None:
    """One slim CC/WB shipment label (empty or freight) in a poker sticker slot.

    Mirrors STS ``printable_ccwaybill.php`` / ``build_cc_*.php`` fields, but
    sized for the same Apostrophe card template as equipment cards — one bill
    per label (empty and freight are separate cards). Rows: header, accent bar,
    destination, data table, flex spacer, shipment id, fixed gap, form id.
    """
    _cc_frame(cell, idx)
    is_empty = (record.get("BillKind") or "freight").lower() == "empty"
    accent = sts_color_hex().get((record.get("Color") or "").strip().lower(), DIVIDER_CLR)

    t = cell.add_table(rows=8, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_width_dxa(t, CARD_W, center=True)
    grid(t, [CARD_W])
    borders(t, outer=0)

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
