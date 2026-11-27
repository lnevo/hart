"""Shared page, footer, back-page and colour-key helpers for the HART letter publications (DS, YM, crew sheets).

The timetable and the destination colours come from the crew master (ops/hart-ops/data/crew.json, ADR-039), read once
on first use. The text and table styling lives in hart_pub_styles.py and the raw OOXML writers in hart_ooxml.py; both
are imported here so the rebuild scripts import from one module.
"""

from __future__ import annotations

import functools
import sys
from pathlib import Path

from docx.document import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from docx.table import Table, _Cell

PUB = Path(__file__).resolve().parent
ASSETS = PUB / "assets"
if str(PUB) not in sys.path:
    sys.path.insert(0, str(PUB))

import crew_master  # noqa: E402
from hart_ooxml import clear_table_borders, set_cell_margins, set_cell_width, set_row_height  # noqa: E402
from hart_pub_styles import (  # noqa: E402,F401
    ACCENT,
    BODY,
    MUTED,
    RULE,
    WHITE,
    _set_run_font,
    add_body,
    add_bullet_items,
    add_heading,
    add_horizontal_rule,
    add_masthead,
    add_numbered_items,
    fill_header_row,
    fill_row,
    fill_swatch_cell,
    set_cell_shading,
    style_table,
)

HEADER_FILL = "0F4761"


@functools.cache
def _master() -> dict:
    """The crew master, read on first use (importing this module reads no file)."""
    return crew_master.load()


def _set_col_width(cell: _Cell, width_in: float) -> None:
    """Width for python-docx layout (cell.width) and the one exact w:tcW Word reads."""
    cell.width = Inches(width_in)
    set_cell_width(cell, int(width_in * 1440))


def _float_to_page_y(table: Table, y_twips: int) -> None:
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
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    if compact:
        section.top_margin = Inches(0.5)
        section.bottom_margin = Inches(0.55)
        section.left_margin = Inches(0.6)
        section.right_margin = Inches(0.6)
    else:
        section.top_margin = Inches(0.7)
        section.bottom_margin = Inches(0.7)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)


def set_page_size(
    doc: Document,
    *,
    width_in: float,
    height_in: float,
    margin_in: float = 0.3,
    top_margin_in: float | None = None,
    bottom_margin_in: float | None = None,
) -> None:
    """Custom page size (e.g. 8×5 landscape desk sheet).

    Sets WD_ORIENT from the width/height ratio so print dialogs match the
    sheet (width > height → landscape).

    top_margin_in defaults higher than side margins when unset so clipboard
    clips don't eat the title (pass explicitly to override).
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
    t.paragraph_format.space_before = Pt(space_before)
    t.paragraph_format.space_after = Pt(1)
    r = t.add_run(f"HART Railroad  ·  {title}")
    _set_run_font(r, size_pt=size_pt, bold=True, color=ACCENT)
    rule = doc.add_paragraph()
    rule.paragraph_format.space_before = Pt(0)
    rule.paragraph_format.space_after = Pt(rule_after)
    add_horizontal_rule(rule)


def add_page1_bottom_bias(
    doc: Document,
    *,
    space_before_pt: float = 36,
) -> None:
    """Empty pad under the title so page-1 body sits lower (clipboard clearance)."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(space_before_pt)
    r = p.add_run("")
    r.font.size = Pt(1)


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
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
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
    """Append the subdivision diagram only (no extra title) as a full page."""
    if map_path is None:
        # Prefer chrome-free diagram; fall back to plain/cream SM-01 export
        preferred = ASSETS / "station_map_diagram_only.png"
        fallback = ASSETS / ("station_map_subdivision_plain.png" if plain_bg else "station_map_subdivision.png")
        map_path = preferred if preferred.is_file() else fallback
    map_path = Path(map_path)
    if not map_path.is_file():
        raise FileNotFoundError(f"Station map not found: {map_path}")

    if page_break:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.add_run().add_break(WD_BREAK.PAGE)

    pic = doc.add_paragraph()
    pic.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pic.paragraph_format.space_before = Pt(0)
    pic.paragraph_format.space_after = Pt(0)
    pic.add_run().add_picture(str(map_path), height=Inches(7.0))


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
    schedule = crew_master.tt23_rows(_master())
    back_page = crew_master.tt23_back_page(_master())
    if map_path is None:
        map_path = ASSETS / "station_map_diagram_only.png"
    map_path = Path(map_path)
    if not map_path.is_file():
        raise FileNotFoundError(f"Station map not found: {map_path}")

    # Lead-in paragraph carries the page break (avoids an empty blank page)
    lead = doc.add_paragraph()
    lead.alignment = WD_ALIGN_PARAGRAPH.LEFT
    lead.paragraph_format.space_before = Pt(12)   # a small pad under the clipboard zone
    lead.paragraph_format.space_after = Pt(4)
    if page_break:
        pPr = lead._p.get_or_add_pPr()
        # Remove existing pageBreakBefore if any, then set
        for child in list(pPr):
            if child.tag == qn("w:pageBreakBefore"):
                pPr.remove(child)
        pPr.append(OxmlElement("w:pageBreakBefore"))

    outer = doc.add_table(rows=1, cols=2)
    outer.alignment = WD_TABLE_ALIGNMENT.CENTER
    outer.autofit = False
    clear_table_borders(outer)

    left, right = outer.rows[0].cells
    _set_col_width(left, 2.15)
    _set_col_width(right, 2.15)

    # —— Left: Station Map ——
    lp = left.paragraphs[0]
    lp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    lp.paragraph_format.space_before = Pt(0)
    lp.paragraph_format.space_after = Pt(2)
    r = lp.add_run("STATION MAP")
    _set_run_font(r, size_pt=8, bold=True, color=ACCENT, name="Arial")

    pic = left.add_paragraph()
    pic.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pic.paragraph_format.space_before = Pt(0)
    pic.paragraph_format.space_after = Pt(0)
    # Slightly shorter so the whole back page stays on one sheet
    pic.add_run().add_picture(str(map_path), width=Inches(2.05), height=Inches(5.6))

    # —— Right: Route 23 timetable ——
    rp = right.paragraphs[0]
    rp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rp.paragraph_format.space_before = Pt(0)
    rp.paragraph_format.space_after = Pt(0)
    r = rp.add_run("ROUTE 23 TIMETABLE")
    _set_run_font(r, size_pt=8, bold=True, color=ACCENT, name="Arial")

    sub = right.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.paragraph_format.space_before = Pt(0)
    sub.paragraph_format.space_after = Pt(4)
    r = sub.add_run(back_page["subtitle"])
    _set_run_font(r, size_pt=6.5, color=MUTED, name="Georgia")

    sched = doc.add_table(rows=1 + len(schedule), cols=3)
    sched.autofit = False
    style_table(sched)
    col_w = (0.52, 0.92, 0.58)
    for cell, text, w in zip(sched.rows[0].cells, ("AM", "STATION", "PM"), col_w):
        cell.text = ""
        _set_col_width(cell, w)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(text)
        _set_run_font(run, size_pt=6, bold=True, color=WHITE, name="Arial")
        set_cell_shading(cell, HEADER_FILL)

    for i, (am, station, pm) in enumerate(schedule, start=1):
        row = sched.rows[i]
        for cell, text, align, w in zip(
            row.cells,
            (am, station, pm),
            (WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER),
            col_w,
        ):
            cell.text = ""
            _set_col_width(cell, w)
            p = cell.paragraphs[0]
            p.alignment = align
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            run = p.add_run(text)
            _set_run_font(run, size_pt=6.5, color=BODY, name="Georgia")

    tbl_el = sched._tbl
    tbl_el.getparent().remove(tbl_el)
    right._tc.append(tbl_el)

    note = right.add_paragraph()
    note.alignment = WD_ALIGN_PARAGRAPH.LEFT
    note.paragraph_format.space_before = Pt(6)
    note.paragraph_format.space_after = Pt(0)
    r = note.add_run(back_page["note"])
    _set_run_font(r, size_pt=5.5, color=MUTED, name="Calibri")


def abridged_color_key_height_in(*, compact: bool = False, pin_title: bool = True) -> float:
    """Approximate height of the abridged color-key table (inches)."""
    n = len(crew_master.color_key(_master())[1])
    title_h = 16 if pin_title else 0
    hdr_h, body_h = (12, 13) if compact else (14, 16)
    return (title_h + hdr_h + n * body_h) / 72.0 + 0.05


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
    offline_dests, island_dests = crew_master.color_key(_master())

    if not pin_to_bottom:
        h = doc.add_paragraph()
        h.paragraph_format.space_before = Pt(space_before)
        h.paragraph_format.space_after = Pt(1 if compact else 2)
        hr = h.add_run(heading.upper())
        _set_run_font(hr, size_pt=9 if compact else 10, bold=True, color=ACCENT)

        if not compact:
            add_body(
                doc,
                "Interchange (left). Local industries (right).",
                space_after=2,
                size_pt=8,
                line_spacing=1.05,
            )

    n = len(island_dests)
    # Title row (optional) + header + data rows
    title_rows = 1 if pin_to_bottom else 0
    table = doc.add_table(rows=title_rows + 1 + n, cols=4)
    data_start = title_rows
    fill_header_row(table.rows[data_start], ["", "Interchange", "", "Local Industries"])
    style_table(table)

    if pin_to_bottom:
        # Title as first row, merged
        title_row = table.rows[0]
        title_row.cells[0].merge(title_row.cells[3])
        title_row.cells[0].text = ""
        set_cell_shading(title_row.cells[0], HEADER_FILL)
        tp = title_row.cells[0].paragraphs[0]
        tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        trun = tp.add_run(heading.upper())
        _set_run_font(trun, size_pt=8.5, bold=True, color=WHITE, name="Calibri")

    for cell in table.rows[data_start].cells:
        set_cell_shading(cell, HEADER_FILL)
        for p in cell.paragraphs:
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            for run in p.runs:
                _set_run_font(run, size_pt=7.5 if compact else 8, bold=True, color=WHITE, name="Calibri")

    def _swatch(cell, fill_hex: str) -> None:
        fill_swatch_cell(cell, "", fill_hex=fill_hex, text_hex="000000")
        for p in cell.paragraphs:
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)

    def _dest(cell, text: str) -> None:
        cell.text = ""
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(text)
        _set_run_font(r, size_pt=7 if compact else 7.5, color=BODY, name="Calibri")

    for i in range(n):
        row = table.rows[data_start + 1 + i]
        offline = offline_dests[i] if i < len(offline_dests) else None
        if offline is None:
            row.cells[0].text = ""
            row.cells[1].text = ""
            set_cell_shading(row.cells[0], "FFFFFF")
        else:
            _swatch(row.cells[0], offline[0])
            _dest(row.cells[1], offline[1])
        _swatch(row.cells[2], island_dests[i][0])
        _dest(row.cells[3], island_dests[i][1])

    hdr_h, body_h = (12, 13) if compact else (14, 16)
    pad_s, pad_d = (14, 20) if compact else (20, 28)
    for ri, row in enumerate(table.rows):
        if pin_to_bottom and ri == 0:
            set_row_height(row, 16)
        elif ri == data_start:
            set_row_height(row, hdr_h)
        else:
            set_row_height(row, body_h)
        for ci, cell in enumerate(row.cells):
            pad = pad_s if ci in (0, 2) else pad_d
            if pin_to_bottom and ri == 0:
                pad = 25
            set_cell_margins(cell, top=pad, left=30, bottom=pad, right=30)
            for p in cell.paragraphs:
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)

    for i in range(n):
        row = table.rows[data_start + 1 + i]
        offline = offline_dests[i] if i < len(offline_dests) else None
        if offline is not None:
            _swatch(row.cells[0], offline[0])
            set_cell_margins(row.cells[0], top=pad_s, left=30, bottom=pad_s, right=30)
        _swatch(row.cells[2], island_dests[i][0])
        set_cell_margins(row.cells[2], top=pad_s, left=30, bottom=pad_s, right=30)

    for row in table.rows:
        for cell, w in zip(
            row.cells,
            [Inches(0.26), Inches(1.85), Inches(0.26), Inches(1.85)],
        ):
            cell.width = w

    if pin_to_bottom:
        # Float the chart to the bottom of the page.
        block_in = abridged_color_key_height_in(compact=compact, pin_title=True)
        _float_to_page_y(table, int((page_height_in - bottom_clearance_in - block_in) * 1440))
