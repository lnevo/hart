"""Text and table styling for the HART letter publications: theme colors, runs, rules, masthead, headings, body
text, lists, table rows and color swatches.

hart_pub_helpers.py imports every name here, and the rebuild scripts import them from hart_pub_helpers. Cell shading
is hart_ooxml.shade_cell, shared with the card pipeline.
"""

from __future__ import annotations

from collections.abc import Sequence

from docx import Document
from docx.document import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Length, Pt, RGBColor
from docx.table import Table, _Row

from hart_ooxml import set_cell_margins, set_row_height
from hart_ooxml import shade_cell as set_cell_shading

# Theme accent used by Heading styles in EQ-01 / standards
ACCENT = RGBColor(0x0F, 0x47, 0x61)
RULE = RGBColor(0x2A, 0x2A, 0x2A)
BODY = RGBColor(0x1A, 0x1A, 0x1A)
MUTED = RGBColor(0x4A, 0x4A, 0x4A)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)


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
                        color=WHITE if ri == 0 else BODY,
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
        _set_run_font(r, size_pt=9, bold=True, color=WHITE, name="Calibri")


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


# Pieces of the compact crew sheets (DS-01, YM-01): section headings, quiet spacers and tables with
# exact row heights.


def add_section_heading(doc: DocxDocument, text: str, *, space_before: float, size_pt: float) -> None:
    """A numbered section heading in upper case, accent colour, 2 pt after."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(text.upper())
    _set_run_font(r, size_pt=size_pt, bold=True, color=ACCENT)


def add_soft_pad(doc: DocxDocument, *, before: float, after: float) -> None:
    """One empty paragraph used as a small gap between page-1 blocks."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)


def paint_header_row(row: _Row, *, size_pt: float) -> None:
    """White bold Calibri on every run of a header row, with no paragraph spacing.

    style_table rewrites the run fonts, so the crew sheets paint their header again after it.
    """
    for cell in row.cells:
        for p in cell.paragraphs:
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            for run in p.runs:
                _set_run_font(run, size_pt=size_pt, bold=True, color=WHITE, name="Calibri")


def fix_table_rows(table: Table, *, header_pt: float, body_pt: float, margin: int, side_margin: int) -> None:
    """Exact row heights (header, then body), cell margins in twips and no paragraph spacing."""
    for ri, row in enumerate(table.rows):
        set_row_height(row, header_pt if ri == 0 else body_pt)
        for cell in row.cells:
            set_cell_margins(cell, top=margin, left=side_margin, bottom=margin, right=side_margin)
            for p in cell.paragraphs:
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)


def set_column_widths(table: Table, widths: Sequence[Length]) -> None:
    """Give each cell of every row the width of its column."""
    for row in table.rows:
        for cell, w in zip(row.cells, widths):
            cell.width = w
