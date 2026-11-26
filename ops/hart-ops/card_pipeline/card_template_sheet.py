"""Sticker-sheet assembly for the HART card templates: the page-4 grid, extra grid pages and the body tail."""

from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches
from docx.table import Table

from card_template_docx import _tc_pr, borders
from card_template_layout import (
    PAGE_MAR_BOTTOM,
    PAGE_MAR_LEFT,
    PAGE_MAR_RIGHT,
    PAGE_MAR_TOP,
    SLOT_H,
)


# ── sticker-sheet assembly ────────────────────────────────────────────────────

def ensure_sect_pr_last(body) -> None:
    """sectPr must be the final body child; mid-document sectPr causes blank pages."""
    sect = body.find(qn("w:sectPr"))
    if sect is not None:
        body.remove(sect)
        body.append(sect)


def insert_before_sect(body, element) -> None:
    sect = body.find(qn("w:sectPr"))
    if sect is not None:
        sect.addprevious(element)
    else:
        body.append(element)


def _minimal_body_paragraph() -> OxmlElement:
    """Tiny paragraph (no page break) for Word's body tail requirement."""
    p = OxmlElement("w:p")
    pPr = OxmlElement("w:pPr")
    spacing = OxmlElement("w:spacing")
    spacing.set(qn("w:before"), "0")
    spacing.set(qn("w:after"), "0")
    spacing.set(qn("w:line"), "20")
    spacing.set(qn("w:lineRule"), "exact")
    pPr.append(spacing)
    rPr = OxmlElement("w:rPr")
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), "2")
    rPr.append(sz)
    pPr.append(rPr)
    p.append(pPr)
    return p


def add_document_tail(body) -> None:
    """One minimal paragraph before sectPr — no page break (avoids blank trailing page)."""
    ensure_sect_pr_last(body)
    sect = body.find(qn("w:sectPr"))
    if sect is None:
        return
    prev = sect.getprevious()
    if prev is not None and prev.tag == qn("w:p"):
        for br in prev.findall(".//" + qn("w:br")):
            if br.get(qn("w:type")) == "page":
                parent = br.getparent()
                if parent is not None:
                    parent.remove(br)
        return
    sect.addprevious(_minimal_body_paragraph())
    ensure_sect_pr_last(body)


def _page4_grid(body):
    """Return the page-4 sticker sheet table (3×3, no gutters)."""
    for tbl in body.findall(qn("w:tbl")):
        grid = tbl.find(qn("w:tblGrid"))
        if grid is not None and len(grid.findall(qn("w:gridCol"))) == 3:
            return tbl
    raise ValueError("page 4 sticker grid (3×3 table) not found in template")


def clear_cell_borders(cell) -> None:
    """Remove printable borders from a sticker-slot cell."""
    tc_pr = _tc_pr(cell)
    old = tc_pr.find(qn("w:tcBorders"))
    if old is not None:
        tc_pr.remove(old)
    b = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        b.append(el)
    tc_pr.append(b)
    shd = tc_pr.find(qn("w:shd"))
    if shd is not None:
        tc_pr.remove(shd)


def strip_grid_guides(table) -> None:
    """Hide the Apostrophe template's gray slot grid when printing."""
    borders(table, outer=0, inner_h=0, inner_v=0)
    pr = table._tbl.tblPr
    for tag in ("w:tblStyle",):
        el = pr.find(qn(tag))
        if el is not None:
            pr.remove(el)
    look = pr.find(qn("w:tblLook"))
    if look is None:
        look = OxmlElement("w:tblLook")
        pr.append(look)
    look.set(qn("w:val"), "0000")
    look.set(qn("w:firstRow"), "0")
    look.set(qn("w:lastRow"), "0")
    look.set(qn("w:firstColumn"), "0")
    look.set(qn("w:lastColumn"), "0")
    look.set(qn("w:noHBand"), "0")
    look.set(qn("w:noVBand"), "0")
    for row in table.rows:
        for cell in row.cells:
            clear_cell_borders(cell)


def keep_sticker_grid(doc: Document) -> None:
    """Keep only page 4's sticker grid (the 3×3 table) + section props.

    Uses the template's page margins and slot dimensions so the printed sheet
    aligns with Apostrophe's edge-to-edge poker sticker layout."""
    body = doc.element.body
    sheet = _page4_grid(body)
    sect = body.find(qn("w:sectPr"))
    for el in list(body):
        if el is not sheet and el is not sect:
            body.remove(el)

    # The template ships the grid as a floating (page-centered) table. Once the
    # cells are filled, the renderer can't center the taller table on one page
    # and splits it across two. Make it in-flow instead, with fixed row heights
    # and the template's page margins, so all 9 cards stay on one page.
    tblPr = sheet.find(qn("w:tblPr"))
    tp = tblPr.find(qn("w:tblpPr"))
    if tp is not None:
        tblPr.remove(tp)
    jc = tblPr.find(qn("w:jc"))
    if jc is None:
        jc = OxmlElement("w:jc")
        tblPr.append(jc)
    jc.set(qn("w:val"), "center")
    for tr in sheet.findall(qn("w:tr")):
        trPr = tr.find(qn("w:trPr"))
        h = trPr.find(qn("w:trHeight")) if trPr is not None else None
        if h is not None:
            h.set(qn("w:val"), str(SLOT_H))
            h.set(qn("w:hRule"), "exact")

    section = doc.sections[0]
    section.top_margin = Inches(PAGE_MAR_TOP / 1440)
    section.bottom_margin = Inches(PAGE_MAR_BOTTOM / 1440)
    section.left_margin = Inches(PAGE_MAR_LEFT / 1440)
    section.right_margin = Inches(PAGE_MAR_RIGHT / 1440)

    # Template slot gridlines must not print — strip table style + cell borders.
    strip_grid_guides(doc.tables[0])
    if body.find(qn("w:sectPr")) is None:
        body.append(OxmlElement("w:sectPr"))
    ensure_sect_pr_last(body)


def set_page_break_before_table(tbl: OxmlElement) -> None:
    """Start a sticker grid on a new page without a blank paragraph between pages."""
    first_row = tbl.findall(qn("w:tr"))[0]
    first_cell = first_row.findall(qn("w:tc"))[0]
    p = first_cell.find(qn("w:p"))
    if p is None:
        p = OxmlElement("w:p")
        first_cell.insert(0, p)
    pPr = p.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        p.insert(0, pPr)
    if pPr.find(qn("w:pageBreakBefore")) is None:
        pPr.insert(0, OxmlElement("w:pageBreakBefore"))


def blank_sticker_grid(sticker_sheet: Path) -> OxmlElement:
    """OOXML for an empty 3x3 sticker grid, taken from the sticker sheet template. The template file is only read."""
    scratch = Document(str(sticker_sheet))
    keep_sticker_grid(scratch)
    return deepcopy(scratch.tables[0]._tbl)


def append_grid(doc: Document, grid_xml: OxmlElement) -> Table:
    """Append a copy of grid_xml as a new page of doc and return it as a Table, with its guides stripped."""
    body = doc.element.body
    tbl = deepcopy(grid_xml)
    set_page_break_before_table(tbl)
    insert_before_sect(body, tbl)
    ensure_sect_pr_last(body)
    table = Table(body.findall(qn("w:tbl"))[-1], doc)
    strip_grid_guides(table)
    return table
