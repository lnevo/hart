"""Shared page, footer, back-page and colour-key helpers for the HART letter publications (DS, YM, crew sheets).

The timetable and the destination colours come from the crew master (ops/hart-ops/data/crew.json, ADR-039), read once
on first use. The text and table styling lives in hart_pub_styles.py and the raw OOXML writers in hart_ooxml.py; both
are imported here so the rebuild scripts import from one module.
"""

from __future__ import annotations

import functools
import sys
from pathlib import Path
from typing import Any, NamedTuple

from docx.document import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from docx.table import Table, _Cell, _Row
from docx.text.paragraph import Paragraph

PUB = Path(__file__).resolve().parent
ASSETS = PUB / "assets"
if str(PUB) not in sys.path:
    sys.path.insert(0, str(PUB))

import crew_master  # noqa: E402
from hart_ooxml import clear_table_borders, set_cell_margins, set_cell_width, set_row_height  # noqa: E402
from hart_pub_styles import (  # noqa: E402,F401  (the rebuild scripts import these names from here)
    ACCENT, BODY, MUTED, RULE, WHITE, _set_run_font, add_body, add_bullet_items, add_heading, add_horizontal_rule,
    add_masthead, add_numbered_items, fill_header_row, fill_row, fill_swatch_cell, set_cell_shading, style_table,
)

HEADER_FILL = "0F4761"
STATION_MAP = ASSETS / "station_map_diagram_only.png"

CrewMaster = dict[str, Any]  # the parsed crew.json (crew_master.load)


class PublicationAssetError(FileNotFoundError):
    """An image that a publication page places is missing (not a file)."""


class ColorKeyError(ValueError):
    """The crew master's colour groups cannot be laid out as the two-column key."""


@functools.cache
def _master() -> CrewMaster:
    """The crew master, read on first use (importing this module reads no file)."""
    return crew_master.load()


def _set_col_width(cell: _Cell, width_in: float) -> None:
    """Width for python-docx layout (cell.width) and the one exact w:tcW Word reads."""
    cell.width = Inches(width_in)
    set_cell_width(cell, int(width_in * 1440))


def _spacing(paragraph: Paragraph, *, before: float = 0, after: float = 0) -> None:
    paragraph.paragraph_format.space_before = Pt(before)
    paragraph.paragraph_format.space_after = Pt(after)


def _picture_path(map_path: str | Path) -> Path:
    path = Path(map_path)
    if not path.is_file():
        raise PublicationAssetError(f"Station map not found: {path}")
    return path


def float_table_to_page_y(table: Table, y_twips: int) -> None:
    """Position the table absolutely, y_twips from the page top, centred in the margins, never overlapped."""
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        tbl.insert(0, tbl_pr)
    for tag in ("w:tblpPr", "w:tblOverlap"):
        old = tbl_pr.find(qn(tag))
        if old is not None:
            tbl_pr.remove(old)
    tblp = OxmlElement("w:tblpPr")
    tblp.set(qn("w:horzAnchor"), "margin")
    tblp.set(qn("w:vertAnchor"), "page")
    tblp.set(qn("w:tblpX"), "0")
    tblp.set(qn("w:tblpY"), str(max(y_twips, 0)))
    tblp.set(qn("w:tblpXSpec"), "center")
    tbl_pr.append(tblp)
    ov = OxmlElement("w:tblOverlap")
    ov.set(qn("w:val"), "never")
    tbl_pr.append(ov)


def set_letter_portrait(doc: Document, *, compact: bool = False) -> None:
    """US letter portrait; compact narrows the margins (top, bottom, sides)."""
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    top, bottom, side = (0.5, 0.55, 0.6) if compact else (0.7, 0.7, 0.75)
    section.top_margin = Inches(top)
    section.bottom_margin = Inches(bottom)
    section.left_margin = Inches(side)
    section.right_margin = Inches(side)


def set_page_size(
    doc: Document,
    *,
    width_in: float,
    height_in: float,
    margin_in: float = 0.3,
    top_margin_in: float | None = None,
    bottom_margin_in: float | None = None,
) -> None:
    """Custom page size (e.g. 8×5 landscape desk sheet), oriented landscape when wider than tall for print dialogs.

    top_margin_in defaults to at least 0.55 in so clipboard clips don't eat the title.
    """
    section = doc.sections[0]
    # Assign orientation before size — python-docx may swap dims on orient change
    if width_in > height_in:
        section.orientation = WD_ORIENT.LANDSCAPE
    else:
        section.orientation = WD_ORIENT.PORTRAIT
    section.page_width = Inches(width_in)
    section.page_height = Inches(height_in)
    top = top_margin_in if top_margin_in is not None else max(margin_in, 0.55)
    bottom = bottom_margin_in if bottom_margin_in is not None else margin_in
    section.top_margin = Inches(top)
    section.bottom_margin = Inches(bottom)
    section.left_margin = Inches(margin_in)
    section.right_margin = Inches(margin_in)
    section.header_distance = Inches(0.15)
    section.footer_distance = Inches(0.18)
    # Avoid empty header eating vertical space
    header = section.header
    header.is_linked_to_previous = False
    if header.paragraphs:
        for run in list(header.paragraphs[0].runs):
            run.text = ""


def add_compact_title(
    doc: Document,
    title: str,
    *,
    revision: str = "D",
    size_pt: float = 13,
    rule_after: float = 6,
    space_before: float = 0,
) -> None:
    """Single-line title for one-page desk sheets."""
    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _spacing(t, before=space_before, after=1)
    r = t.add_run(f"HART Railroad  ·  {title}")
    _set_run_font(r, size_pt=size_pt, bold=True, color=ACCENT)
    rule = doc.add_paragraph()
    _spacing(rule, after=rule_after)
    add_horizontal_rule(rule)


def add_publication_footer(
    doc: Document,
    *,
    pub_id: str,
    revision: str = "D",
    effective: str = "21 July 2026",
    authority: str = "Office of the Superintendent · Neville Island Operations",
    compact: bool = False,
) -> None:
    """Put publication identity in the section footer (not the body)."""
    section = doc.sections[0]
    footer = section.footer
    footer.is_linked_to_previous = False
    p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    for run in list(p.runs):
        run.text = ""
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _spacing(p)
    if compact:
        line = f"{pub_id}  ·  Rev {revision}  ·  Eff. {effective}  ·  Neville Island Ops"
        size = 6.5
    else:
        line = (
            f"{authority}  ·  Publication {pub_id}  ·  "
            f"Effective {effective}  ·  Revision {revision}  ·  Official Publication"
        )
        size = 7.5
    r = p.add_run(line)
    _set_run_font(r, size_pt=size, color=MUTED, name="Calibri")


def add_station_map_page(
    doc: Document,
    *,
    map_path: str | Path | None = None,
    page_break: bool = True,
    plain_bg: bool = False,
) -> None:
    """Append the subdivision diagram only (no extra title) as a full page.

    With no map_path the chrome-free diagram is used when it exists, else the SM-01 export (plain or cream).
    """
    if map_path is None:
        fallback = ASSETS / ("station_map_subdivision_plain.png" if plain_bg else "station_map_subdivision.png")
        map_path = STATION_MAP if STATION_MAP.is_file() else fallback
    path = _picture_path(map_path)

    if page_break:
        p = doc.add_paragraph()
        _spacing(p)
        p.add_run().add_break(WD_BREAK.PAGE)

    pic = doc.add_paragraph()
    pic.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _spacing(pic)
    pic.add_run().add_picture(str(path), height=Inches(7.0))


# The back page: STATION MAP (left) and the ROUTE 23 timetable (right), about 50/50.

TIMETABLE_COLUMNS = ("AM", "STATION", "PM")
TIMETABLE_WIDTHS_IN = (0.52, 0.92, 0.58)
TIMETABLE_ALIGN = (WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER)


def _add_back_page_lead(doc: Document, *, page_break: bool) -> None:
    """The lead-in paragraph above the back page; it carries the page break (no empty blank page)."""
    lead = doc.add_paragraph()
    lead.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _spacing(lead, before=12, after=4)  # a small pad under the clipboard zone
    if page_break:
        p_pr = lead._p.get_or_add_pPr()
        for child in list(p_pr):
            if child.tag == qn("w:pageBreakBefore"):
                p_pr.remove(child)
        p_pr.append(OxmlElement("w:pageBreakBefore"))


def _add_column_title(cell: _Cell, text: str, *, after: float) -> None:
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _spacing(p, after=after)
    _set_run_font(p.add_run(text), size_pt=8, bold=True, color=ACCENT, name="Arial")


def _add_map_column(cell: _Cell, map_path: Path) -> None:
    _add_column_title(cell, "STATION MAP", after=2)
    pic = cell.add_paragraph()
    pic.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _spacing(pic)
    # Slightly shorter so the whole back page stays on one sheet
    pic.add_run().add_picture(str(map_path), width=Inches(2.05), height=Inches(5.6))


def _fill_timetable_cell(cell: _Cell, width_in: float) -> Paragraph:
    """Empty the cell, give it its width and return its paragraph."""
    cell.text = ""
    _set_col_width(cell, width_in)
    return cell.paragraphs[0]


def _timetable_table(doc: Document, rows: list[tuple[str, str, str]]) -> Table:
    """The AM | STATION | PM table, added at the end of the body (the caller moves it into its cell)."""
    sched = doc.add_table(rows=1 + len(rows), cols=3)
    sched.autofit = False
    style_table(sched)
    for cell, text, w in zip(sched.rows[0].cells, TIMETABLE_COLUMNS, TIMETABLE_WIDTHS_IN, strict=True):
        p = _fill_timetable_cell(cell, w)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _spacing(p)
        _set_run_font(p.add_run(text), size_pt=6, bold=True, color=WHITE, name="Arial")
        set_cell_shading(cell, HEADER_FILL)
    for row, values in zip(sched.rows[1:], rows, strict=True):
        for cell, text, align, w in zip(row.cells, values, TIMETABLE_ALIGN, TIMETABLE_WIDTHS_IN, strict=True):
            p = _fill_timetable_cell(cell, w)
            p.alignment = align
            _spacing(p, before=2, after=2)
            _set_run_font(p.add_run(text), size_pt=6.5, color=BODY, name="Georgia")
    return sched


def _add_timetable_column(doc: Document, cell: _Cell, master: CrewMaster) -> None:
    back_page = crew_master.tt23_back_page(master)
    _add_column_title(cell, "ROUTE 23 TIMETABLE", after=0)
    sub = cell.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _spacing(sub, after=4)
    _set_run_font(sub.add_run(back_page["subtitle"]), size_pt=6.5, color=MUTED, name="Georgia")

    tbl_el = _timetable_table(doc, crew_master.tt23_rows(master))._tbl
    tbl_el.getparent().remove(tbl_el)
    cell._tc.append(tbl_el)

    note = cell.add_paragraph()
    note.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _spacing(note, before=6)
    _set_run_font(note.add_run(back_page["note"]), size_pt=5.5, color=MUTED, name="Calibri")


def add_diagram_and_timetable_page(
    doc: Document,
    *,
    map_path: str | Path | None = None,
    page_break: bool = True,
) -> None:
    """Back page: STATION MAP (left) + ROUTE 23 timetable (right), ~50/50.

    The timetable is the master's TT-23 rows (AM | STATION | PM): each trip runs Barn to McKees Rocks, waits 10
    minutes and returns, so AM reads down and PM reads up.
    """
    master = _master()
    path = _picture_path(STATION_MAP if map_path is None else map_path)
    _add_back_page_lead(doc, page_break=page_break)

    outer = doc.add_table(rows=1, cols=2)
    outer.alignment = WD_TABLE_ALIGNMENT.CENTER
    outer.autofit = False
    clear_table_borders(outer)
    left, right = outer.rows[0].cells
    _set_col_width(left, 2.15)
    _set_col_width(right, 2.15)
    _add_map_column(left, path)
    _add_timetable_column(doc, right, master)


# The abridged colour key: interchange swatches left, local industries right.


class KeyMetrics(NamedTuple):
    """Row heights (pt) and cell paddings (twips) of the colour key, by compact or not."""

    header_pt: float
    body_pt: float
    swatch_pad: int
    dest_pad: int
    header_font_pt: float
    dest_font_pt: float


KEY_METRICS = {
    True: KeyMetrics(header_pt=12, body_pt=13, swatch_pad=14, dest_pad=20, header_font_pt=7.5, dest_font_pt=7),
    False: KeyMetrics(header_pt=14, body_pt=16, swatch_pad=20, dest_pad=28, header_font_pt=8, dest_font_pt=7.5),
}
KEY_TITLE_PT = 16
KEY_TITLE_PAD = 25
KEY_SIDE_PAD = 30
KEY_WIDTHS_IN = (0.26, 1.85, 0.26, 1.85)

Swatch = tuple[str, str]  # (RRGGBB fill, destination label), as crew_master.color_key gives them


def _color_key_groups(master: CrewMaster) -> tuple[list[Swatch], list[Swatch]]:
    """(interchange, island) swatches; the key has one row per island swatch, so interchange may not be longer."""
    offline, island = crew_master.color_key(master)
    if len(offline) > len(island):
        raise ColorKeyError(
            f"the crew master has {len(offline)} interchange colours and {len(island)} island colours; "
            "the key prints one row per island colour, so interchange colours would be dropped"
        )
    return offline, island


def abridged_color_key_height_in(*, compact: bool = False, pin_title: bool = True) -> float:
    """Approximate height of the abridged color-key table (inches)."""
    n = len(crew_master.color_key(_master())[1])
    title_h = KEY_TITLE_PT if pin_title else 0
    m = KEY_METRICS[compact]
    return (title_h + m.header_pt + n * m.body_pt) / 72.0 + 0.05


def _key_swatch(cell: _Cell, fill_hex: str) -> None:
    fill_swatch_cell(cell, "", fill_hex=fill_hex, text_hex="000000")
    for p in cell.paragraphs:
        _spacing(p)


def _key_dest(cell: _Cell, text: str, m: KeyMetrics) -> None:
    cell.text = ""
    p = cell.paragraphs[0]
    _spacing(p)
    _set_run_font(p.add_run(text), size_pt=m.dest_font_pt, color=BODY, name="Calibri")


def _add_key_heading(doc: Document, heading: str, *, space_before: float, compact: bool) -> None:
    h = doc.add_paragraph()
    _spacing(h, before=space_before, after=1 if compact else 2)
    _set_run_font(h.add_run(heading.upper()), size_pt=9 if compact else 10, bold=True, color=ACCENT)
    if not compact:
        add_body(doc, "Interchange (left). Local industries (right).", space_after=2, size_pt=8, line_spacing=1.05)


def _fill_key_title_row(row: _Row, heading: str) -> None:
    """The heading as a merged first row (the pinned key carries its own title)."""
    row.cells[0].merge(row.cells[3])
    title = row.cells[0]
    title.text = ""
    set_cell_shading(title, HEADER_FILL)
    tp = title.paragraphs[0]
    tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_run_font(tp.add_run(heading.upper()), size_pt=8.5, bold=True, color=WHITE, name="Calibri")


def _paint_key_header(row: _Row, m: KeyMetrics) -> None:
    for cell in row.cells:
        set_cell_shading(cell, HEADER_FILL)
        for p in cell.paragraphs:
            _spacing(p)
            for run in p.runs:
                _set_run_font(run, size_pt=m.header_font_pt, bold=True, color=WHITE, name="Calibri")


def _fill_key_rows(rows: list[_Row], offline: list[Swatch], island: list[Swatch], m: KeyMetrics) -> None:
    for i, (row, (island_fill, island_dest)) in enumerate(zip(rows, island, strict=True)):
        if i < len(offline):
            _key_swatch(row.cells[0], offline[i][0])
            _key_dest(row.cells[1], offline[i][1], m)
        else:
            row.cells[0].text = ""
            row.cells[1].text = ""
            set_cell_shading(row.cells[0], "FFFFFF")
        _key_swatch(row.cells[2], island_fill)
        _key_dest(row.cells[3], island_dest, m)


def _size_key_rows(table: Table, *, header_index: int, pinned: bool, m: KeyMetrics) -> None:
    """Exact row heights and cell paddings for every row; paragraphs lose their spacing."""
    for ri, row in enumerate(table.rows):
        title_row = pinned and ri == 0
        if title_row:
            set_row_height(row, KEY_TITLE_PT)
        elif ri == header_index:
            set_row_height(row, m.header_pt)
        else:
            set_row_height(row, m.body_pt)
        for ci, cell in enumerate(row.cells):
            pad = m.swatch_pad if ci in (0, 2) else m.dest_pad
            if title_row:
                pad = KEY_TITLE_PAD
            set_cell_margins(cell, top=pad, left=KEY_SIDE_PAD, bottom=pad, right=KEY_SIDE_PAD)
            for p in cell.paragraphs:
                _spacing(p)


def _repaint_key_swatches(rows: list[_Row], offline: list[Swatch], island: list[Swatch], m: KeyMetrics) -> None:
    """Swatch cells again after sizing, with the swatch padding (the sizing pass gives every cell its padding)."""
    for i, (row, (island_fill, _dest)) in enumerate(zip(rows, island, strict=True)):
        cells = [(row.cells[0], offline[i][0])] if i < len(offline) else []
        for cell, fill in [*cells, (row.cells[2], island_fill)]:
            _key_swatch(cell, fill)
            set_cell_margins(cell, top=m.swatch_pad, left=KEY_SIDE_PAD, bottom=m.swatch_pad, right=KEY_SIDE_PAD)


def add_abridged_color_key(
    doc: Document,
    *,
    heading: str = "Destination Colors",
    space_before: float = 6,
    compact: bool = False,
    pin_to_bottom: bool = False,
    page_height_in: float = 8.0,
    bottom_clearance_in: float = 0.42,
) -> None:
    """Two-column swatch chart: interchange left, local industries right.

    The swatches are the master's colour groups, (fill, label), in its order. When pin_to_bottom=True, the chart is
    absolutely positioned near the bottom of the page (for 5×8 crew sheets).
    """
    offline, island = _color_key_groups(_master())
    m = KEY_METRICS[compact]
    if not pin_to_bottom:
        _add_key_heading(doc, heading, space_before=space_before, compact=compact)

    header_index = 1 if pin_to_bottom else 0
    table = doc.add_table(rows=header_index + 1 + len(island), cols=4)
    fill_header_row(table.rows[header_index], ["", "Interchange", "", "Local Industries"])
    style_table(table)
    if pin_to_bottom:
        _fill_key_title_row(table.rows[0], heading)
    _paint_key_header(table.rows[header_index], m)

    body = list(table.rows)[header_index + 1:]
    _fill_key_rows(body, offline, island, m)
    _size_key_rows(table, header_index=header_index, pinned=pin_to_bottom, m=m)
    _repaint_key_swatches(body, offline, island, m)
    for row in table.rows:
        for cell, w in zip(row.cells, KEY_WIDTHS_IN, strict=True):
            cell.width = Inches(w)

    if pin_to_bottom:
        block_in = abridged_color_key_height_in(compact=compact, pin_title=True)
        float_table_to_page_y(table, int((page_height_in - bottom_clearance_in - block_in) * 1440))
