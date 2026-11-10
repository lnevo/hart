#!/usr/bin/env python3
"""Rebuild Neville Island Dispatcher Train List (DS-01, Revision D).

Page 1: train lineup + priority + color key.
Page 2: subdivision diagram + narrow TT-23 timetable (no map chrome).
Publication identity lives in the footer.

Page-1 spacing (hand-tuned Jul 2026 — keep on rebuild):
  top/bottom margins 0.62 / 0.38; title rule_after=6;
  soft pad before §1 (before=6/after=2); lineup before=6;
  priority before=18; destination colors before=18.
  Do not reintroduce a large page1 bottom-bias spacer.

Usage (from repo root):
  .venv/bin/python publications/rebuild_dispatcher_train_list.py

Writes:
  docs/Neville_Island_Dispatcher_Train_List.docx
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
    add_abridged_color_key,
    add_compact_title,
    add_diagram_and_timetable_page,
    add_publication_footer,
    fill_header_row,
    set_page_size,
    style_table,
)

CANONICAL = DOCS / "Neville_Island_Dispatcher_Train_List.docx"

PUBLICATION = {
    "title": "Dispatcher Train List",
    "pub_id": "DS-01",
    "revision": "D",
    "effective": "21 July 2026",
}

WHITE = RGBColor(0xFF, 0xFF, 0xFF)

# Order, Train, one-sentence dispatcher action (aligned with YM-01).
LINEUP: list[tuple[str, str, str]] = [
    ("1", "Route 23 AM", "Operate per timetable; hold conflicting work until the train clears."),
    (
        "2",
        "D749",
        "Demmler → South Yard to open; interchange; release outbounds to McKeesport.",
    ),
    ("3", "OCS-1", "When scheduled — highest priority; clear the route."),
    (
        "4",
        "NVL",
        "Scully → South Yard; interchange; service local industries; return with outbounds; return to McKees Rocks.",
    ),
    ("5", "CK1", "Shenango pickup and delivery; calibrate scale, weigh coke pull, and sort."),
    ("6", "D749 Return", "Authorize return; terminate in West Yard."),
    ("7", "Route 23 PM", "Operate per timetable; hold conflicting work until the train clears."),
]

PRIORITY = "OCS-1 → Route 23 → D749 → NVL → CK1 → Yard"


def _heading(doc: Document, text: str, *, space_before: float) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(text.upper())
    _set_run_font(r, size_pt=10, bold=True, color=ACCENT)


def _set_cell_margins(cell, *, top: int, bottom: int, left: int = 40, right: int = 40) -> None:
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


def _soft_pad(doc: Document, *, before: float = 6, after: float = 2) -> None:
    """One quiet blank used between page-1 blocks."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)


def _add_lineup(doc: Document) -> None:
    _heading(doc, "1. Train Lineup", space_before=6)

    table = doc.add_table(rows=1 + len(LINEUP), cols=3)
    fill_header_row(table.rows[0], ["#", "Train", "Dispatcher action"])
    for i, (num, train, action) in enumerate(LINEUP, start=1):
        row = table.rows[i]

        row.cells[0].text = ""
        p0 = row.cells[0].paragraphs[0]
        p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r0 = p0.add_run(num)
        _set_run_font(r0, size_pt=10, bold=True, color=BODY, name="Calibri")

        row.cells[1].text = ""
        r1 = row.cells[1].paragraphs[0].add_run(train)
        _set_run_font(r1, size_pt=8.5, bold=True, color=BODY, name="Calibri")

        row.cells[2].text = ""
        r2 = row.cells[2].paragraphs[0].add_run(action)
        _set_run_font(r2, size_pt=8.5, color=BODY, name="Calibri")

    style_table(table)

    for cell in table.rows[0].cells:
        for p in cell.paragraphs:
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            for run in p.runs:
                _set_run_font(run, size_pt=8.5, bold=True, color=WHITE, name="Calibri")

    for i, (num, train, action) in enumerate(LINEUP, start=1):
        row = table.rows[i]
        row.cells[0].text = ""
        p0 = row.cells[0].paragraphs[0]
        p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r0 = p0.add_run(num)
        _set_run_font(r0, size_pt=10, bold=True, color=BODY, name="Calibri")

        row.cells[1].text = ""
        r1 = row.cells[1].paragraphs[0].add_run(train)
        _set_run_font(r1, size_pt=8.5, bold=True, color=BODY, name="Calibri")

        row.cells[2].text = ""
        r2 = row.cells[2].paragraphs[0].add_run(action)
        _set_run_font(r2, size_pt=8.5, color=BODY, name="Calibri")

    for ri, row in enumerate(table.rows):
        _set_exact_row_height(row, 16 if ri == 0 else 26)
        for cell in row.cells:
            _set_cell_margins(cell, top=32, bottom=32)
            for p in cell.paragraphs:
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)

    _set_widths(table, [Inches(0.3), Inches(0.85), Inches(3.25)])


def _add_priority(doc: Document) -> None:
    _heading(doc, "2. Priority Order", space_before=18)
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run(PRIORITY)
    _set_run_font(r, size_pt=9, bold=True, color=BODY, name="Calibri")


def rebuild(out: Path = CANONICAL) -> Path:
    doc = Document()
    set_page_size(
        doc,
        width_in=5.0,
        height_in=8.0,
        margin_in=0.3,
        top_margin_in=0.62,
        bottom_margin_in=0.38,
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
        size_pt=12,
        rule_after=6,
    )
    _soft_pad(doc, before=6, after=2)

    _add_lineup(doc)
    _add_priority(doc)
    add_abridged_color_key(doc, heading="3. Destination Colors", space_before=18, compact=True)
    add_diagram_and_timetable_page(doc)

    doc.save(out)
    return out


def main() -> None:
    path = rebuild()
    print(f"Wrote {path} ({PUBLICATION['pub_id']} Rev {PUBLICATION['revision']})")


if __name__ == "__main__":
    main()
