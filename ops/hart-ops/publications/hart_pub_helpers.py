"""Shared helpers for HART Railroad letter publications (DS / YM / etc.)."""

from __future__ import annotations

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor, Twips

# Theme accent used by Heading styles in EQ-01 / standards
ACCENT = RGBColor(0x0F, 0x47, 0x61)
RULE = RGBColor(0x2A, 0x2A, 0x2A)
BODY = RGBColor(0x1A, 0x1A, 0x1A)
MUTED = RGBColor(0x4A, 0x4A, 0x4A)


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
    from docx.enum.section import WD_ORIENT

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
    from pathlib import Path as _Path
    from docx.enum.text import WD_BREAK

    assets = _Path(__file__).resolve().parent / "assets"
    if map_path is None:
        # Prefer chrome-free diagram; fall back to plain/cream SM-01 export
        preferred = assets / "station_map_diagram_only.png"
        fallback = (
            assets / "station_map_subdivision_plain.png"
            if plain_bg
            else assets / "station_map_subdivision.png"
        )
        map_path = preferred if preferred.is_file() else fallback
    map_path = _Path(map_path)
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


# TT-23 page 2 schedule (AM | STATION | PM) for YM/DS companion column.
# Each trip is a round trip: Barn to McKees Rocks, 10-minute wait, back to Barn.
TT23_SCHEDULE_ROWS: list[tuple[str, str, str]] = [
    ("9:00", "Barn", "4:00"),
    ("9:06", "Scale", "4:06"),
    ("9:12", "Brick", "4:12"),
    ("9:18", "East End", "4:18"),
    ("9:25", "McKees Rocks (arr.)", "4:25"),
    ("9:35", "McKees Rocks (dep.)", "4:35"),
    ("9:42", "East End", "4:42"),
    ("9:48", "Brick", "4:48"),
    ("9:54", "Scale", "4:54"),
    ("10:00", "Barn", "5:00"),
]


def add_diagram_and_timetable_page(
    doc: Document,
    *,
    map_path: str | Path | None = None,
    page_break: bool = True,
) -> None:
    """Back page: STATION MAP (left) + ROUTE 23 timetable (right), ~50/50."""
    from pathlib import Path as _Path
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    assets = _Path(__file__).resolve().parent / "assets"
    if map_path is None:
        map_path = assets / "station_map_diagram_only.png"
    map_path = _Path(map_path)
    if not map_path.is_file():
        raise FileNotFoundError(f"Station map not found: {map_path}")

    def _set_col_width(cell, width_in: float) -> None:
        cell.width = Inches(width_in)
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        tcW = OxmlElement("w:tcW")
        tcW.set(qn("w:w"), str(int(width_in * 1440)))
        tcW.set(qn("w:type"), "dxa")
        tcPr.append(tcW)

    def _clear_borders(table) -> None:
        tbl = table._tbl
        tblPr = tbl.tblPr if tbl.tblPr is not None else OxmlElement("w:tblPr")
        borders = OxmlElement("w:tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            el = OxmlElement(f"w:{edge}")
            el.set(qn("w:val"), "nil")
            el.set(qn("w:sz"), "0")
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "auto")
            borders.append(el)
        tblPr.append(borders)

    # Lead-in paragraph carries the page break (avoids an empty blank page)
    lead = doc.add_paragraph()
    lead.alignment = WD_ALIGN_PARAGRAPH.LEFT
    lead.paragraph_format.space_before = Pt(0)
    lead.paragraph_format.space_after = Pt(4)
    if page_break:
        pPr = lead._p.get_or_add_pPr()
        # Remove existing pageBreakBefore if any, then set
        for child in list(pPr):
            if child.tag == qn("w:pageBreakBefore"):
                pPr.remove(child)
        pPr.append(OxmlElement("w:pageBreakBefore"))
    # Small top pad under clipboard zone (not a huge spacer that orphans the table)
    lead.paragraph_format.space_before = Pt(12)

    outer = doc.add_table(rows=1, cols=2)
    outer.alignment = WD_TABLE_ALIGNMENT.CENTER
    outer.autofit = False
    _clear_borders(outer)

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
    r = sub.add_run("Neville Queen  ·  Emp. TT No. 23")
    _set_run_font(r, size_pt=6.5, color=MUTED, name="Georgia")

    sched = doc.add_table(rows=1 + len(TT23_SCHEDULE_ROWS), cols=3)
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
        _set_run_font(run, size_pt=6, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF), name="Arial")
        set_cell_shading(cell, "0F4761")

    for i, (am, station, pm) in enumerate(TT23_SCHEDULE_ROWS, start=1):
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
    r = note.add_run(
        "Barn→McKees Rocks, 10 min wait, return to Barn. Station time."
    )
    _set_run_font(r, size_pt=5.5, color=MUTED, name="Calibri")


# Abridged destination color key (swatches only — no color names).
OFFLINE_DESTS: list[tuple[str, str]] = [
    ("0000CD", "Demmler / McKeesport"),
    ("FFA500", "Scully / McKees Rocks"),
]
ISLAND_DESTS: list[tuple[str, str]] = [
    ("FFFF00", "Aristech Plastics"),
    ("008000", "A. Stucki Co."),
    ("800080", "Calgon Carbon"),
    ("FF0000", "Ferrellgas"),
    ("FFC0CB", "Kosmos Cement"),
    ("000000", "Shenango Coke Works"),
]


def abridged_color_key_height_in(*, compact: bool = False, pin_title: bool = True) -> float:
    """Approximate height of the abridged color-key table (inches)."""
    n = len(ISLAND_DESTS)
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

    When pin_to_bottom=True, the chart is absolutely positioned near the
    bottom of the page (for 5×8 crew sheets).
    """
    WHITE = RGBColor(0xFF, 0xFF, 0xFF)

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

    n = len(ISLAND_DESTS)
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
        set_cell_shading(title_row.cells[0], "0F4761")
        tp = title_row.cells[0].paragraphs[0]
        tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        trun = tp.add_run(heading.upper())
        _set_run_font(trun, size_pt=8.5, bold=True, color=WHITE, name="Calibri")

    for cell in table.rows[data_start].cells:
        set_cell_shading(cell, "0F4761")
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

    def _margins(cell, *, top: int, bottom: int, left: int = 30, right: int = 30) -> None:
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        old = tcPr.find(qn("w:tcMar"))
        if old is not None:
            tcPr.remove(old)
        tcMar = OxmlElement("w:tcMar")
        for edge, val in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
            el = OxmlElement(f"w:{edge}")
            el.set(qn("w:w"), str(val))
            el.set(qn("w:type"), "dxa")
            tcMar.append(el)
        tcPr.append(tcMar)

    def _row_h(row, height_pt: float) -> None:
        tr = row._tr
        trPr = tr.get_or_add_trPr()
        old = trPr.find(qn("w:trHeight"))
        if old is not None:
            trPr.remove(old)
        trHeight = OxmlElement("w:trHeight")
        trHeight.set(qn("w:val"), str(int(height_pt * 20)))
        trHeight.set(qn("w:hRule"), "exact")
        trPr.append(trHeight)

    for i in range(n):
        row = table.rows[data_start + 1 + i]
        offline = OFFLINE_DESTS[i] if i < len(OFFLINE_DESTS) else None
        if offline is None:
            row.cells[0].text = ""
            row.cells[1].text = ""
            set_cell_shading(row.cells[0], "FFFFFF")
        else:
            _swatch(row.cells[0], offline[0])
            _dest(row.cells[1], offline[1])
        _swatch(row.cells[2], ISLAND_DESTS[i][0])
        _dest(row.cells[3], ISLAND_DESTS[i][1])

    hdr_h, body_h = (12, 13) if compact else (14, 16)
    pad_s, pad_d = (14, 20) if compact else (20, 28)
    for ri, row in enumerate(table.rows):
        if pin_to_bottom and ri == 0:
            _row_h(row, 16)
        elif ri == data_start:
            _row_h(row, hdr_h)
        else:
            _row_h(row, body_h)
        for ci, cell in enumerate(row.cells):
            pad = pad_s if ci in (0, 2) else pad_d
            if pin_to_bottom and ri == 0:
                pad = 25
            _margins(cell, top=pad, bottom=pad)
            for p in cell.paragraphs:
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)

    for i in range(n):
        row = table.rows[data_start + 1 + i]
        offline = OFFLINE_DESTS[i] if i < len(OFFLINE_DESTS) else None
        if offline is not None:
            _swatch(row.cells[0], offline[0])
            _margins(row.cells[0], top=pad_s, bottom=pad_s)
        _swatch(row.cells[2], ISLAND_DESTS[i][0])
        _margins(row.cells[2], top=pad_s, bottom=pad_s)

    for row in table.rows:
        for cell, w in zip(
            row.cells,
            [Inches(0.26), Inches(1.85), Inches(0.26), Inches(1.85)],
        ):
            cell.width = w

    if pin_to_bottom:
        # Float the chart to the bottom of the page.
        block_in = abridged_color_key_height_in(compact=compact, pin_title=True)
        y_twips = int((page_height_in - bottom_clearance_in - block_in) * 1440)
        tbl = table._tbl
        tblPr = tbl.tblPr
        if tblPr is None:
            tblPr = OxmlElement("w:tblPr")
            tbl.insert(0, tblPr)
        old = tblPr.find(qn("w:tblpPr"))
        if old is not None:
            tblPr.remove(old)
        tblpPr = OxmlElement("w:tblpPr")
        tblpPr.set(qn("w:horzAnchor"), "margin")
        tblpPr.set(qn("w:vertAnchor"), "page")
        tblpPr.set(qn("w:tblpX"), "0")
        tblpPr.set(qn("w:tblpY"), str(max(y_twips, 0)))
        tblpPr.set(qn("w:tblpXSpec"), "center")
        tblPr.append(tblpPr)
        # Keep following content from overlapping awkwardly
        old_ov = tblPr.find(qn("w:tblOverlap"))
        if old_ov is not None:
            tblPr.remove(old_ov)
        ov = OxmlElement("w:tblOverlap")
        ov.set(qn("w:val"), "never")
        tblPr.append(ov)


def _set_run_font(run, *, size_pt: float, bold: bool = False, color: RGBColor | None = None, name: str = "Georgia") -> None:
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:ascii"), name)
    run._element.rPr.rFonts.set(qn("w:hAnsi"), name)
    run.font.size = Pt(size_pt)
    run.bold = bold
    if color is not None:
        run.font.color.rgb = color


def add_horizontal_rule(paragraph, color: RGBColor = RULE) -> None:
    """Bottom border on the paragraph as a heavy rule."""
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "18")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), f"{color[0]:02X}{color[1]:02X}{color[2]:02X}")
    pBdr.append(bottom)
    pPr.append(pBdr)


def add_masthead(
    doc: Document,
    *,
    title: str,
    subtitle: str,
    pub_id: str,
    revision: str = "D",
    effective: str = "21 July 2026",
) -> None:
    """Typography-led HART publication block (no decorative drawings)."""
    brand = doc.add_paragraph()
    brand.alignment = WD_ALIGN_PARAGRAPH.CENTER
    brand.paragraph_format.space_before = Pt(0)
    brand.paragraph_format.space_after = Pt(2)
    r = brand.add_run("HART Railroad")
    _set_run_font(r, size_pt=22, bold=True, color=ACCENT)

    div = doc.add_paragraph()
    div.alignment = WD_ALIGN_PARAGRAPH.CENTER
    div.paragraph_format.space_before = Pt(0)
    div.paragraph_format.space_after = Pt(8)
    r = div.add_run("Pittsburgh & Chartiers Valley Division")
    _set_run_font(r, size_pt=11, color=MUTED)

    rule = doc.add_paragraph()
    rule.paragraph_format.space_before = Pt(0)
    rule.paragraph_format.space_after = Pt(8)
    add_horizontal_rule(rule)

    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    t.paragraph_format.space_before = Pt(0)
    t.paragraph_format.space_after = Pt(2)
    r = t.add_run(f"{title}  ·  Revision {revision}")
    _set_run_font(r, size_pt=14, bold=True, color=BODY)

    ops = doc.add_paragraph()
    ops.alignment = WD_ALIGN_PARAGRAPH.CENTER
    ops.paragraph_format.space_before = Pt(0)
    ops.paragraph_format.space_after = Pt(10)
    r = ops.add_run(subtitle)
    _set_run_font(r, size_pt=10, color=MUTED)

    # Publication block — left-aligned compact lines
    block_lines = [
        "Issuing Authority: Office of the Superintendent",
        f"Publication {pub_id}",
        f"Effective {effective}",
        f"Revision {revision}",
        "Official Publication",
    ]
    for i, line in enumerate(block_lines):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0 if i < len(block_lines) - 1 else 4)
        p.paragraph_format.line_spacing = 1.05
        r = p.add_run(line)
        _set_run_font(r, size_pt=9, color=MUTED, name="Calibri")

    rule2 = doc.add_paragraph()
    rule2.paragraph_format.space_before = Pt(2)
    rule2.paragraph_format.space_after = Pt(10)
    add_horizontal_rule(rule2)


def add_heading(doc: Document, text: str, *, level: int = 1) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12 if level == 1 else 8)
    p.paragraph_format.space_after = Pt(4)
    size = 12 if level == 1 else 10.5
    r = p.add_run(text.upper() if level == 1 else text)
    _set_run_font(r, size_pt=size, bold=True, color=ACCENT)
    if level == 1:
        add_horizontal_rule(p, ACCENT)


def add_body(
    doc: Document,
    text: str,
    *,
    space_before: float = 0,
    space_after: float = 6,
    size_pt: float = 10,
    line_spacing: float = 1.15,
) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = line_spacing
    r = p.add_run(text)
    _set_run_font(r, size_pt=size_pt, color=BODY, name="Calibri")


def add_numbered_items(doc: Document, items: list[str]) -> None:
    for i, item in enumerate(items, start=1):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.left_indent = Inches(0.15)
        r = p.add_run(f"{i}.  {item}")
        _set_run_font(r, size_pt=10, color=BODY, name="Calibri")


def add_bullet_items(doc: Document, items: list[str]) -> None:
    for item in items:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.left_indent = Inches(0.15)
        r = p.add_run(f"•  {item}")
        _set_run_font(r, size_pt=10, color=BODY, name="Calibri")


def set_cell_shading(cell, hex_color: str) -> None:
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), hex_color)
    shd.set(qn("w:val"), "clear")
    tcPr.append(shd)


def style_table(table) -> None:
    """Compact operational table: header bar, hairline borders, no spreadsheet look."""
    tbl = table._tbl
    tblPr = tbl.tblPr if tbl.tblPr is not None else OxmlElement("w:tblPr")
    if tbl.tblPr is None:
        tbl.insert(0, tblPr)

    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "A0A0A0")
        borders.append(el)
    # replace existing borders if present
    old = tblPr.find(qn("w:tblBorders"))
    if old is not None:
        tblPr.remove(old)
    tblPr.append(borders)

    for ri, row in enumerate(table.rows):
        for cell in row.cells:
            for p in cell.paragraphs:
                p.paragraph_format.space_before = Pt(2)
                p.paragraph_format.space_after = Pt(2)
                for run in p.runs:
                    _set_run_font(
                        run,
                        size_pt=8.5 if ri > 0 else 9,
                        bold=(ri == 0),
                        color=RGBColor(0xFF, 0xFF, 0xFF) if ri == 0 else BODY,
                        name="Calibri",
                    )
            if ri == 0:
                set_cell_shading(cell, "0F4761")


def fill_header_row(row, texts: list[str]) -> None:
    for i, text in enumerate(texts):
        cell = row.cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        r = p.add_run(text)
        _set_run_font(r, size_pt=9, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF), name="Calibri")


def fill_row(row, texts: list[str]) -> None:
    for i, text in enumerate(texts):
        cell = row.cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        r = p.add_run(text)
        _set_run_font(r, size_pt=8.5, color=BODY, name="Calibri")


def fill_swatch_cell(
    cell,
    label: str,
    *,
    fill_hex: str,
    text_hex: str = "000000",
) -> None:
    """Colored legend swatch cell (STS destination color)."""
    cell.text = ""
    set_cell_shading(cell, fill_hex)
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(label)
    rgb = RGBColor(
        int(text_hex[0:2], 16),
        int(text_hex[2:4], 16),
        int(text_hex[4:6], 16),
    )
    _set_run_font(r, size_pt=9, bold=True, color=rgb, name="Calibri")
