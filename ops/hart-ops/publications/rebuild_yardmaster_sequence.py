#!/usr/bin/env python3
"""Rebuild Neville Island Yardmaster Sequence (YM-01, Revision D).

Page 1: sequence + color/blocking legend.
Page 2: subdivision diagram + narrow TT-23 timetable (no map chrome).
Publication identity lives in the footer.

Page-1 spacing (hand-tuned Jul 2026 — keep on rebuild):
  top/bottom margins 0.48 / 0.36; title rule_after=3;
  soft pad before §1; §1→§2 gap ~6pt before heading (not a large bias pad);
  sequence rows 17/30pt; legend rows 16/20pt.

Usage (from repo root):
  .venv/bin/python publications/rebuild_yardmaster_sequence.py

Writes:
  docs/Neville_Island_Yardmaster_Sequence.docx
"""

from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT.parents[1] / "docs/ops"
PUB = Path(__file__).resolve().parent
sys.path.insert(0, str(PUB))

from hart_pub_helpers import (  # noqa: E402
    ACCENT,
    BODY,
    _set_run_font,
    add_compact_title,
    add_diagram_and_timetable_page,
    add_publication_footer,
    fill_header_row,
    fill_swatch_cell,
    set_page_size,
    style_table,
)

CANONICAL = DOCS / "Neville_Island_Yardmaster_Sequence.docx"

PUBLICATION = {
    "title": "Yardmaster Sequence",
    "pub_id": "YM-01",
    "revision": "D",
    "effective": "21 July 2026",
}

BLOCK_LEGEND: list[tuple[str, str, str, str, str]] = [
    ("BLUE", "0000CD", "FFFFFF", "Demmler Yard; Mckeesport", "D749"),
    ("YELLOW", "FFFF00", "000000", "Aristech Plastics", "NVL"),
    ("GREEN", "008000", "FFFFFF", "A. Stucki Co.", "NVL"),
    ("PURPLE", "800080", "FFFFFF", "Calgon Carbon", "NVL"),
    ("RED", "FF0000", "FFFFFF", "Ferrellgas", "NVL"),
    ("PINK", "FFC0CB", "000000", "Kosmos Cement", "NVL"),
    ("BLACK", "000000", "FFFFFF", "Shenango Coke Works", "CK1"),
    ("ORANGE", "FFA500", "000000", "Scully Yard; McKees Rocks", "NVL return"),
]

SEQUENCE: list[tuple[str, str, str]] = [
    (
        "1",
        "D749",
        "Receive inbound Demmler / McKeesport block, build and hand-off outbounds to D749. (Blue)",
    ),
    (
        "2",
        "NVL",
        "Receive the Scully setout and give NVL the local cut for delivery. (Yellow, Green, Purple, Red, Pink)",
    ),
    (
        "3",
        "CK1",
        "Hand Shenango cars to CK1 for delivery; (Black) Calibrate the scale, weigh coke pull and sort.",
    ),
    (
        "4",
        "NVL return",
        "Receive NVL setouts and give the Scully / McKees Rocks block for the return. (Orange)",
    ),
]

WHITE = RGBColor(0xFF, 0xFF, 0xFF)


def _heading(doc: Document, text: str, *, space_before: float) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(text.upper())
    _set_run_font(r, size_pt=10.5, bold=True, color=ACCENT)


def _set_cell_margins(cell, *, top: int, bottom: int, left: int = 45, right: int = 45) -> None:
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


def _set_exact_row_height(row, height_pt: float) -> None:
    tr = row._tr
    trPr = tr.get_or_add_trPr()
    old = trPr.find(qn("w:trHeight"))
    if old is not None:
        trPr.remove(old)
    trHeight = OxmlElement("w:trHeight")
    trHeight.set(qn("w:val"), str(int(height_pt * 20)))
    trHeight.set(qn("w:hRule"), "exact")
    trPr.append(trHeight)


def _set_widths(table, widths: list) -> None:
    for row in table.rows:
        for cell, w in zip(row.cells, widths):
            cell.width = w


def _paint_header(row, size_pt: float = 9.5) -> None:
    for cell in row.cells:
        for p in cell.paragraphs:
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            for run in p.runs:
                _set_run_font(run, size_pt=size_pt, bold=True, color=WHITE, name="Calibri")


def _soft_pad(doc: Document, *, before: float = 4, after: float = 2) -> None:
    """One quiet blank used between page-1 blocks (avoid large bottom-bias pads)."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)


def _add_sequence(doc: Document) -> None:
    _heading(doc, "1. Sequence", space_before=4)

    table = doc.add_table(rows=1 + len(SEQUENCE), cols=3)
    fill_header_row(table.rows[0], ["#", "Train", "Yardmaster action"])
    for i, (num, move, action) in enumerate(SEQUENCE, start=1):
        row = table.rows[i]

        row.cells[0].text = ""
        p0 = row.cells[0].paragraphs[0]
        p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r0 = p0.add_run(num)
        _set_run_font(r0, size_pt=12, bold=True, color=BODY, name="Calibri")

        row.cells[1].text = ""
        r1 = row.cells[1].paragraphs[0].add_run(move)
        _set_run_font(r1, size_pt=9.5, bold=True, color=BODY, name="Calibri")

        row.cells[2].text = ""
        r2 = row.cells[2].paragraphs[0].add_run(action)
        _set_run_font(r2, size_pt=9.5, color=BODY, name="Calibri")

    style_table(table)

    # Re-apply after style_table (it rewrites run fonts)
    _paint_header(table.rows[0])
    for i, (num, move, action) in enumerate(SEQUENCE, start=1):
        row = table.rows[i]
        row.cells[0].text = ""
        p0 = row.cells[0].paragraphs[0]
        p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r0 = p0.add_run(num)
        _set_run_font(r0, size_pt=12, bold=True, color=BODY, name="Calibri")

        row.cells[1].text = ""
        r1 = row.cells[1].paragraphs[0].add_run(move)
        _set_run_font(r1, size_pt=9.5, bold=True, color=BODY, name="Calibri")

        row.cells[2].text = ""
        r2 = row.cells[2].paragraphs[0].add_run(action)
        _set_run_font(r2, size_pt=9.5, color=BODY, name="Calibri")

    for ri, row in enumerate(table.rows):
        _set_exact_row_height(row, 17 if ri == 0 else 30)
        for cell in row.cells:
            _set_cell_margins(cell, top=36, bottom=36)
            for p in cell.paragraphs:
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)

    _set_widths(table, [Inches(0.35), Inches(1.15), Inches(2.8)])


def _add_block_legend(doc: Document) -> None:
    _soft_pad(doc, before=6, after=2)
    _heading(doc, "2. Destination Colors", space_before=6)

    legend = doc.add_table(rows=1 + len(BLOCK_LEGEND), cols=3)
    fill_header_row(legend.rows[0], ["Color", "Destination", "Blocking"])
    for i, (label, fill, text_hex, dests, remarks) in enumerate(BLOCK_LEGEND, start=1):
        fill_swatch_cell(legend.rows[i].cells[0], label, fill_hex=fill, text_hex=text_hex)

        legend.rows[i].cells[1].text = ""
        r1 = legend.rows[i].cells[1].paragraphs[0].add_run(dests)
        _set_run_font(r1, size_pt=9.5, color=BODY, name="Calibri")

        legend.rows[i].cells[2].text = ""
        r2 = legend.rows[i].cells[2].paragraphs[0].add_run(remarks)
        _set_run_font(r2, size_pt=9.5, color=BODY, name="Calibri")

    style_table(legend)
    _paint_header(legend.rows[0])

    for i, (label, fill, text_hex, dests, remarks) in enumerate(BLOCK_LEGEND, start=1):
        fill_swatch_cell(legend.rows[i].cells[0], label, fill_hex=fill, text_hex=text_hex)
        for run in legend.rows[i].cells[0].paragraphs[0].runs:
            run.font.size = Pt(9)

        legend.rows[i].cells[1].text = ""
        r1 = legend.rows[i].cells[1].paragraphs[0].add_run(dests)
        _set_run_font(r1, size_pt=9.5, color=BODY, name="Calibri")

        legend.rows[i].cells[2].text = ""
        r2 = legend.rows[i].cells[2].paragraphs[0].add_run(remarks)
        _set_run_font(r2, size_pt=9.5, color=BODY, name="Calibri")

    for ri, row in enumerate(legend.rows):
        _set_exact_row_height(row, 16 if ri == 0 else 20)
        for cell in row.cells:
            _set_cell_margins(cell, top=28, bottom=28)
            for p in cell.paragraphs:
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)

    # Swatches last so fill/label survive margin pass
    for i, (label, fill, text_hex, _d, _r) in enumerate(BLOCK_LEGEND, start=1):
        fill_swatch_cell(legend.rows[i].cells[0], label, fill_hex=fill, text_hex=text_hex)
        for p in legend.rows[i].cells[0].paragraphs:
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            for run in p.runs:
                run.font.size = Pt(9)
        _set_cell_margins(legend.rows[i].cells[0], top=28, bottom=28)

    _set_widths(legend, [Inches(0.9), Inches(2.15), Inches(1.25)])


def rebuild(out: Path = CANONICAL) -> Path:
    doc = Document()
    set_page_size(
        doc,
        width_in=5.0,
        height_in=8.0,
        margin_in=0.3,
        top_margin_in=0.48,
        bottom_margin_in=0.36,
    )
    add_publication_footer(
        doc,
        pub_id=PUBLICATION["pub_id"],
        revision=PUBLICATION["revision"],
        effective=PUBLICATION["effective"],
        compact=True,
    )
    add_compact_title(
        doc,
        PUBLICATION["title"],
        revision=PUBLICATION["revision"],
        size_pt=13,
        rule_after=3,
    )
    _soft_pad(doc, before=4, after=2)

    _add_sequence(doc)
    _add_block_legend(doc)
    add_diagram_and_timetable_page(doc)

    doc.save(out)
    return out


def main() -> None:
    path = rebuild()
    print(f"Wrote {path} ({PUBLICATION['pub_id']} Rev {PUBLICATION['revision']})")


if __name__ == "__main__":
    main()
