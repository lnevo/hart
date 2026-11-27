#!/usr/bin/env python3
"""Generate an operator reference sheet for HART industries and yards.

Each industry page takes its colours from the STS seed's `spurs` file (external/sts-helpers/seed/inputs/spurs), read
when the sheet is built. The page text lives in operator_sheet_data.py.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import TypedDict

from docx import Document
from docx.document import Document as DocxDocument
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.section import Section
from docx.shared import Inches, Pt, RGBColor
from docx.table import Table, _Cell, _Row
from docx.text.paragraph import Paragraph

import generate_waybill_cards as gw
import hartlib_path  # noqa: E402

hartlib_path.ensure_on_path()
from hartlib import operations  # noqa: E402
import car_paths  # noqa: E402  (loaded by generate_waybill_cards)
import car_repo  # noqa: E402
import waybill_data as wdata  # noqa: E402
import waybill_deck as wdeck  # noqa: E402
import crew_master
from card_errors import CardPipelineError
from hart_ooxml import shade_cell
from operator_sheet_data import (
    INDUSTRY_LOGOS,
    INDUSTRY_SUMMARIES,
    SHEET_INDUSTRY_ORDER,
    SHENANGO_TRACK_ROWS,
    YARD_PAGES,
    TrackRow,
    YardPage,
)
from waybill_data import WaybillSpec

OUTPUT = car_repo.HART_ROOT / "docs/ops/HART_Operator_Sheet.docx"
LOGO_DIR = car_paths.HART_OPS_ROOT / "operator_logos"
SPUR_FILE = car_repo.SEED_INPUTS / "spurs"
EMPTY = wdata.EMPTY


class SpursFileMissingError(CardPipelineError, FileNotFoundError):
    """The STS seed's spurs file is not where SPUR_FILE says (the external/sts-helpers submodule is not checked out)."""


class SpursLineError(CardPipelineError, ValueError):
    """A spurs line is not ``Industry - count - Colour``."""


class IndustryColourMissingError(CardPipelineError, KeyError):
    """An industry on the sheet has no colour in the spurs file."""


class IndustryStyle(TypedDict):
    """A page banner's look: RRGGBB accent and text colours, and an optional logo in LOGO_DIR."""

    accent: str
    text: str
    logo: str | None
    logo_width: float


class SpotRow(TypedDict):
    """One row of an industry's spot table; sort is the first spot number."""

    spot: str
    usage: str
    cars: str
    inbound: str
    outbound: str
    sort: int

PAGE_W = Inches(5)
PAGE_H = Inches(8)
MARGIN = Inches(0.4)

FONT_BODY = Pt(8.5)
FONT_HEADING = Pt(13)
FONT_SECTION = Pt(7.5)
FONT_TABLE = Pt(7.5)
FONT_TABLE_HEAD = Pt(7)
FONT_BULLET = Pt(8)

COLOR_BODY = RGBColor(0x44, 0x44, 0x44)
COLOR_MUTED = RGBColor(0x66, 0x66, 0x66)
COLOR_INK = RGBColor(0x22, 0x22, 0x22)
COLOR_BORDER = "BBBBBB"
COLOR_PANEL = "FAFAFA"

TABLE_COLS_IN = (0.32, 0.88, 0.82, 0.95, 0.95)
TABLE_COLS_TRACK = (1.05, 0.55, 1.15, 1.15)  # Track, Cars, In, Out (no spots)

# The label the sheet prints for each spot usage: ops/hart-ops/data/spot_usages.csv (hartlib.operations).
USAGE_LABELS: dict[str, str] = operations.read_spot_usages()

# Spur colour names from layout `spurs` (STS location colour names) → the accent band and the text colour. The
# accent is the crew master's fill for the colours it has (mediumblue is its blue); lightblue and lightgrey are
# STS-only. Yellow prints FFD400, richer than the master's FFFF00, because pure yellow washes out as a thin rule.
_SPUR_MASTER_ID: dict[str, str] = {
    "green": "green", "blue": "blue", "red": "red", "orange": "orange", "purple": "purple", "pink": "pink",
    "mediumblue": "blue", "black": "black",
}
_SPUR_FIXED_ACCENT: dict[str, str] = {"yellow": "FFD400", "lightblue": "ADD8E6", "lightgrey": "D3D3D3"}
_SPUR_TEXT: dict[str, str] = {
    "yellow": "000000", "green": "008000", "blue": "0000CD", "red": "FF0000", "orange": "000000",
    "purple": "800080", "pink": "000000", "lightblue": "000000", "mediumblue": "0000CD", "lightgrey": "000000",
    "black": "000000",
}


def spur_palette() -> dict[str, dict[str, str]]:
    """Spur colour name → {"accent", "text"} RRGGBB."""
    swatch = crew_master.swatches(crew_master.load())
    accent = {**{name: swatch[cid].fill for name, cid in _SPUR_MASTER_ID.items()}, **_SPUR_FIXED_ACCENT}
    return {name: {"accent": accent[name], "text": text} for name, text in _SPUR_TEXT.items()}


def load_industry_styles(spur_file: Path = SPUR_FILE) -> dict[str, IndustryStyle]:
    """Each industry's colours from `spurs` (``Industry - count - Colour`` lines), with its logo if it has one.

    Blank lines, lines with no ``-`` and colours the palette does not know are skipped.
    """
    if not spur_file.is_file():
        raise SpursFileMissingError(
            f"Missing the spurs file {spur_file} (git submodule update --init external/sts-helpers)"
        )
    styles: dict[str, IndustryStyle] = {}
    palettes = spur_palette()
    for raw in spur_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or "-" not in line:
            continue
        parts = [part.strip() for part in line.split("-", 2)]
        if len(parts) != 3:
            raise SpursLineError(f"{spur_file}: {line!r} is not 'Industry - count - Colour'")
        industry, _, color_name = parts
        palette = palettes.get(color_name.lower())
        if not palette:
            continue
        logo, logo_width = INDUSTRY_LOGOS.get(industry, (None, 0.0))
        styles[industry] = {"accent": palette["accent"], "text": palette["text"], "logo": logo,
                            "logo_width": logo_width}
    return styles


def _configure_page(section: Section) -> None:
    section.page_width = PAGE_W
    section.page_height = PAGE_H
    section.left_margin = MARGIN
    section.right_margin = MARGIN
    section.top_margin = MARGIN
    section.bottom_margin = MARGIN
    section.header_distance = Inches(0)
    section.footer_distance = Inches(0)


def _configure_document(doc: DocxDocument) -> None:
    _configure_page(doc.sections[0])
    normal = doc.styles["Normal"]
    normal.font.size = FONT_BODY
    normal.font.name = "Georgia"
    normal.font.color.rgb = RGBColor(0x33, 0x33, 0x33)


def _set_cell_margins(cell: _Cell, top: int = 40, bottom: int = 40, left: int = 60, right: int = 60) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    mar = OxmlElement("w:tcMar")
    for tag, val in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
        node = OxmlElement(f"w:{tag}")
        node.set(qn("w:w"), str(val))
        node.set(qn("w:type"), "dxa")
        mar.append(node)
    tc_pr.append(mar)


def _set_table_borders(
    table: Table,
    *,
    color: str = COLOR_BORDER,
    outer_size: int = 6,
    inner_size: int = 4,
) -> None:
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), str(outer_size))
        element.set(qn("w:color"), color)
        borders.append(element)
    for edge in ("insideH", "insideV"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), str(inner_size))
        element.set(qn("w:color"), color)
        borders.append(element)
    tbl_pr.append(borders)


def _set_cell_border(cell: _Cell, *, bottom_size: int = 0, bottom_color: str = COLOR_BORDER) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "right"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "nil")
        borders.append(element)
    bottom = OxmlElement("w:bottom")
    if bottom_size:
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), str(bottom_size))
        bottom.set(qn("w:color"), bottom_color)
    else:
        bottom.set(qn("w:val"), "nil")
    borders.append(bottom)
    tc_pr.append(borders)


def _accent_rule(doc: DocxDocument, accent: str) -> None:
    rule = doc.add_table(rows=1, cols=1)
    rule.autofit = False
    cell = rule.rows[0].cells[0]
    cell.width = PAGE_W - 2 * MARGIN
    shade_cell(cell, accent, auto_color=True)
    _set_cell_margins(cell, top=0, bottom=0, left=0, right=0)
    cell.paragraphs[0].paragraph_format.space_after = Pt(0)
    rule.rows[0].height = Pt(4)
    _set_table_borders(rule, color=accent, outer_size=0, inner_size=0)


def _keep_with_next(paragraph: Paragraph) -> None:
    paragraph.paragraph_format.keep_with_next = True


def _set_row_cant_split(row: _Row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    if tr_pr.find(qn("w:cantSplit")) is None:
        tr_pr.append(OxmlElement("w:cantSplit"))


def _set_table_column_widths(table: Table, widths_in: tuple[float, ...]) -> None:
    table.autofit = False
    for row in table.rows:
        for idx, cell in enumerate(row.cells):
            if idx < len(widths_in):
                cell.width = Inches(widths_in[idx])


def _add_banner(doc: DocxDocument, title: str, style: IndustryStyle) -> None:
    logo_name = style["logo"]
    logo_path = LOGO_DIR / logo_name if logo_name else None
    has_logo = bool(logo_path and logo_path.exists())
    banner = doc.add_table(rows=1, cols=1)
    banner.autofit = False
    cell = banner.rows[0].cells[0]
    cell.width = PAGE_W - 2 * MARGIN
    shade_cell(cell, COLOR_PANEL, auto_color=True)
    _set_cell_margins(cell, top=90, bottom=90, left=100, right=100)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    _set_cell_border(cell, bottom_size=8, bottom_color=style["accent"])
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if has_logo:
        run = p.add_run()
        run.add_picture(str(logo_path), width=Inches(style["logo_width"]))
    else:
        run = p.add_run(title)
        run.bold = True
        run.font.size = FONT_HEADING
        run.font.name = "Georgia"
        run.font.color.rgb = RGBColor.from_string(style["text"])
    _keep_with_next(p)
    banner.rows[0].height = Inches(0.72 if has_logo else 0.52)
    _set_table_borders(banner, color=COLOR_BORDER, outer_size=4, inner_size=0)


def _add_title_heading(doc: DocxDocument, title: str, accent: str, *, subtitle: str = "") -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2 if subtitle else 6)
    run = p.add_run(title)
    run.bold = True
    run.font.size = FONT_HEADING
    run.font.name = "Georgia"
    run.font.color.rgb = RGBColor.from_string(accent if accent != "D3D3D3" else "222222")
    _keep_with_next(p)
    if subtitle:
        s = doc.add_paragraph()
        s.paragraph_format.space_before = Pt(0)
        s.paragraph_format.space_after = Pt(6)
        r = s.add_run(subtitle)
        r.font.size = FONT_SECTION
        r.font.name = "Georgia"
        r.font.color.rgb = COLOR_MUTED
        _keep_with_next(s)


def _add_section_label(doc: DocxDocument, text: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(text.upper())
    run.bold = True
    run.font.size = FONT_SECTION
    run.font.name = "Georgia"
    run.font.color.rgb = COLOR_MUTED
    _keep_with_next(p)


def _add_body_paragraph(doc: DocxDocument, text: str, *, keep: bool = True) -> None:
    p = doc.add_paragraph(text)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.15
    for run in p.runs:
        run.font.size = FONT_BODY
        run.font.name = "Georgia"
        run.font.color.rgb = COLOR_BODY
    if keep:
        _keep_with_next(p)


def _add_bullet(doc: DocxDocument, text: str, *, keep: bool = True) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.15)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.space_before = Pt(0)
    run = p.add_run(f"• {text}")
    run.font.size = FONT_BULLET
    run.font.name = "Georgia"
    run.font.color.rgb = COLOR_BODY
    if keep:
        _keep_with_next(p)


def _style_data_table(table: Table, accent: str, *, center_first: bool = True) -> None:
    header = table.rows[0]
    for idx, cell in enumerate(header.cells):
        _set_cell_margins(cell, top=35, bottom=35, left=45, right=45)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        _set_cell_border(cell, bottom_size=8, bottom_color=accent)
        for p in cell.paragraphs:
            p.alignment = (
                WD_ALIGN_PARAGRAPH.CENTER if center_first and idx == 0 else WD_ALIGN_PARAGRAPH.LEFT
            )
            for run in p.runs:
                run.bold = True
                run.font.size = FONT_TABLE_HEAD
                run.font.name = "Georgia"
                run.font.color.rgb = COLOR_INK

    for row in table.rows[1:]:
        for idx, cell in enumerate(row.cells):
            _set_cell_margins(cell, top=28, bottom=28, left=45, right=45)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
            for p in cell.paragraphs:
                p.alignment = (
                    WD_ALIGN_PARAGRAPH.CENTER
                    if center_first and idx == 0
                    else WD_ALIGN_PARAGRAPH.LEFT
                )
                for run in p.runs:
                    run.font.size = FONT_TABLE
                    run.font.name = "Georgia"
                    run.font.color.rgb = COLOR_BODY
        _set_row_cant_split(row)


def _usage_label(usage: str) -> str:
    return USAGE_LABELS.get(usage.lower(), usage).lstrip()


def _format_inbound(spec: WaybillSpec) -> str:
    return wdeck.inbound_commodity_label(spec)


def _format_outbound(spec: WaybillSpec) -> str:
    load = spec["outbound_load"]
    return "Empty cars" if load == EMPTY else load


def _add_spot_table(doc: DocxDocument, rows: list[SpotRow], accent: str) -> None:
    table = doc.add_table(rows=1, cols=5)
    for i, text in enumerate(("Spot", "Track", "Cars", "In", "Out")):
        table.rows[0].cells[i].text = text
    for row in rows:
        cells = table.add_row().cells
        cells[0].text = row["spot"]
        cells[1].text = row["usage"]
        cells[2].text = row["cars"]
        cells[3].text = row["inbound"]
        cells[4].text = row["outbound"]
    _set_table_column_widths(table, TABLE_COLS_IN)
    _set_table_borders(table)
    _style_data_table(table, accent)


def _add_track_table(doc: DocxDocument, rows: list[TrackRow], accent: str) -> None:
    table = doc.add_table(rows=1, cols=4)
    for i, text in enumerate(("Track", "Cars", "In", "Out")):
        table.rows[0].cells[i].text = text
    for row in rows:
        cells = table.add_row().cells
        cells[0].text = row["track"]
        cells[1].text = row["cars"]
        cells[2].text = row["inbound"]
        cells[3].text = row["outbound"]
    _set_table_column_widths(table, TABLE_COLS_TRACK)
    _set_table_borders(table)
    _style_data_table(table, accent, center_first=False)


def _add_industry_section(
    doc: DocxDocument, industry: str, rows: list[SpotRow], style: IndustryStyle, *, page_break: bool
) -> None:
    if page_break:
        doc.add_page_break()

    logo = style["logo"]
    logo_path = LOGO_DIR / logo if logo else None
    has_logo = bool(logo_path and logo_path.exists())

    _add_banner(doc, industry, style)
    _accent_rule(doc, style["accent"])
    if not has_logo:
        _add_title_heading(doc, industry, style["accent"])

    summary_lines = INDUSTRY_SUMMARIES.get(industry, [])
    for i, line in enumerate(summary_lines):
        _add_body_paragraph(doc, line, keep=i < len(summary_lines) - 1)

    if industry == "Shenango Coke Works":
        _add_section_label(doc, "Tracks")
        _add_track_table(doc, SHENANGO_TRACK_ROWS, style["accent"])
        note = doc.add_paragraph()
        note.paragraph_format.space_before = Pt(6)
        note.paragraph_format.space_after = Pt(0)
        r = note.add_run("No numbered spots. Weigh all outgoing coke at South Yard scale.")
        r.font.size = FONT_BULLET
        r.font.name = "Georgia"
        r.font.color.rgb = COLOR_MUTED
        return

    _add_section_label(doc, "Tracks & spots")
    _add_spot_table(doc, rows, style["accent"])


def _add_yard_section(doc: DocxDocument, page: YardPage, *, page_break: bool) -> None:
    if page_break:
        doc.add_page_break()

    style: IndustryStyle = {
        "accent": page["accent"],
        "text": page["text"],
        "logo": page.get("logo"),
        "logo_width": float(page.get("logo_width") or 0.0),
    }
    _add_banner(doc, page["title"], style)
    _accent_rule(doc, page["accent"])
    # Always show the desk/yard name — logos are railroad marks, not page titles.
    _add_title_heading(doc, page["title"], page["accent"], subtitle=page.get("subtitle", ""))

    for line in page.get("role", []):
        _add_body_paragraph(doc, line)

    for label, items in page.get("sections", []):
        _add_section_label(doc, label)
        for item in items:
            _add_bullet(doc, item)

    if page.get("trains"):
        _add_section_label(doc, "Trains this session")
        for job in page["trains"]:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(2)
            run = p.add_run(job["name"])
            run.bold = True
            run.font.size = FONT_BULLET
            run.font.name = "Georgia"
            run.font.color.rgb = COLOR_INK
            _keep_with_next(p)
            for line in job["lines"]:
                _add_bullet(doc, line)

    if page.get("blocking"):
        _add_section_label(doc, "Blocking priority")
        for item in page["blocking"]:
            _add_bullet(doc, item)

    if page.get("jobs"):
        _add_section_label(doc, "Jobs")
        for item in page["jobs"]:
            _add_bullet(doc, item)


def _load_off_spot_rows() -> dict[str, list[SpotRow]]:
    spots: dict[tuple[str, str], list[int]] = defaultdict(list)
    cars: dict[tuple[str, str], str] = {}

    with gw.SPOT_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            industry = wdata.norm(row.get("Industry"))
            usage = wdata.norm(row.get("Usage"))
            if not industry or usage.lower() not in wdata.SKIP_USAGES:
                continue
            spot = wdeck.parse_spot_num(row.get("Spot #", ""))
            if spot:
                key = (industry, usage)
                spots[key].append(spot)
                cars[key] = row.get("Cars Applicable", "").replace(";", ", ")

    by_industry: dict[str, list[SpotRow]] = defaultdict(list)
    for (industry, usage), nums in spots.items():
        by_industry[industry].append(
            {
                "spot": wdeck.format_spots(nums),
                "usage": _usage_label(usage),
                "cars": cars[(industry, usage)],
                "inbound": "—",
                "outbound": "—",
                "sort": min(nums),
            }
        )
    for industry in by_industry:
        by_industry[industry].sort(key=lambda r: r["sort"])
    return dict(by_industry)


def _load_all_spot_rows() -> dict[str, list[SpotRow]]:
    combined: dict[str, list[SpotRow]] = {name: [] for name in wdata.INDUSTRY_ORDER}

    for group in gw.load_spot_groups():
        industry = group["Industry"]
        spec = wdeck.waybill_spec(industry, group["Usage"])
        combined[industry].append(
            {
                "spot": group["Spots"],
                "usage": _usage_label(group["Usage"]),
                "cars": ", ".join(group["CarTypes"]),
                "inbound": _format_inbound(spec),
                "outbound": _format_outbound(spec),
                "sort": int(group["Spots"].split("-")[0].split(",")[0]),
            }
        )

    off_spot = _load_off_spot_rows()
    for industry in wdata.INDUSTRY_ORDER:
        combined[industry].extend(off_spot.get(industry, []))
        combined[industry].sort(key=lambda r: r["sort"])

    return combined


def _style_for(styles: dict[str, IndustryStyle], industry: str, spur_file: Path) -> IndustryStyle:
    if industry not in styles:
        raise IndustryColourMissingError(f"{industry} has no colour the sheet knows in {spur_file}")
    return styles[industry]


def generate(output: Path = OUTPUT, spur_file: Path = SPUR_FILE) -> int:
    """Write the operator sheet to output and return its page count."""
    styles = load_industry_styles(spur_file)
    doc = Document()
    _configure_document(doc)

    by_industry = _load_all_spot_rows()
    ordered = sorted(SHEET_INDUSTRY_ORDER, key=lambda n: SHEET_INDUSTRY_ORDER[n])
    page_count = 0

    for industry in ordered:
        rows = [] if industry == "Shenango Coke Works" else by_industry.get(industry, [])
        if rows or industry == "Shenango Coke Works":
            style = _style_for(styles, industry, spur_file)
            _add_industry_section(doc, industry, rows, style, page_break=page_count > 0)
            page_count += 1

    for yard in YARD_PAGES:
        _add_yard_section(doc, yard, page_break=page_count > 0)
        page_count += 1

    doc.save(output)
    return page_count


def main() -> None:
    pages = generate()
    print(f"Wrote {OUTPUT} ({PAGE_W.inches:.0f}×{PAGE_H.inches:.0f} in, {pages} pages)")


if __name__ == "__main__":
    try:
        main()
    except CardPipelineError as exc:
        raise SystemExit(str(exc)) from exc
