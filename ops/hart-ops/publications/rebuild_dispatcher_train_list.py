#!/usr/bin/env python3
"""Rebuild Neville Island Dispatcher Train List (DS-01, Revision E).

Page 1: train lineup + priority + color key.
Page 2: subdivision diagram + narrow TT-23 timetable (no map chrome).
Publication identity lives in the footer.

Page-1 spacing (hand-tuned Jul 2026 — keep on rebuild):
  top/bottom margins 0.62 / 0.38; title rule_after=6;
  no soft pad before §1 since Rev E (room for ten rows); lineup before=6;
  priority before=8; destination colors before=8 (Rev E: ten lineup rows at 23pt).
  Do not reintroduce a large page1 bottom-bias spacer.

The text is read from the crew master, ops/hart-ops/data/crew.json (job "dispatcher").

Usage (from ops/hart-ops):
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

import crew_master  # noqa: E402

# The publication line, the lineup, the rules and the priority strip come from the crew master
# (ops/hart-ops/data/crew.json, job "dispatcher", ADR-039).
_MASTER = crew_master.load()
_JOB = crew_master.job(_MASTER, "dispatcher")
PUBLICATION = crew_master.publication(_JOB)

WHITE = RGBColor(0xFF, 0xFF, 0xFF)

# Order, Train, route (origin → points → destination, printed bold), dispatcher action.
LINEUP: list[tuple[str, str, str, str]] = crew_master.lineup(_MASTER)

# Dispatcher rules printed under the lineup (Session #4 punch list).
RULES = " ".join(_JOB["rules"])

PRIORITY = " → ".join(_JOB["priority"])


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
    for i, (num, train, route, action) in enumerate(LINEUP, start=1):
        row = table.rows[i]

        row.cells[0].text = ""
        p0 = row.cells[0].paragraphs[0]
        p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r0 = p0.add_run(num)
        _set_run_font(r0, size_pt=9, bold=True, color=BODY, name="Calibri")

        row.cells[1].text = ""
        r1 = row.cells[1].paragraphs[0].add_run(train)
        _set_run_font(r1, size_pt=8, bold=True, color=BODY, name="Calibri")

        row.cells[2].text = ""
        rr = row.cells[2].paragraphs[0].add_run(route + " ")
        _set_run_font(rr, size_pt=8, bold=True, color=BODY, name="Calibri")
        r2 = row.cells[2].paragraphs[0].add_run(action)
        _set_run_font(r2, size_pt=8, color=BODY, name="Calibri")

    style_table(table)

    for cell in table.rows[0].cells:
        for p in cell.paragraphs:
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            for run in p.runs:
                _set_run_font(run, size_pt=8.5, bold=True, color=WHITE, name="Calibri")

    for i, (num, train, route, action) in enumerate(LINEUP, start=1):
        row = table.rows[i]
        row.cells[0].text = ""
        p0 = row.cells[0].paragraphs[0]
        p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r0 = p0.add_run(num)
        _set_run_font(r0, size_pt=9, bold=True, color=BODY, name="Calibri")

        row.cells[1].text = ""
        r1 = row.cells[1].paragraphs[0].add_run(train)
        _set_run_font(r1, size_pt=8, bold=True, color=BODY, name="Calibri")

        row.cells[2].text = ""
        rr = row.cells[2].paragraphs[0].add_run(route + " ")
        _set_run_font(rr, size_pt=8, bold=True, color=BODY, name="Calibri")
        r2 = row.cells[2].paragraphs[0].add_run(action)
        _set_run_font(r2, size_pt=8, color=BODY, name="Calibri")

    for ri, row in enumerate(table.rows):
        _set_exact_row_height(row, 16 if ri == 0 else 23)
        for cell in row.cells:
            _set_cell_margins(cell, top=32, bottom=32)
            for p in cell.paragraphs:
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)

    _set_widths(table, [Inches(0.3), Inches(0.85), Inches(3.25)])


def _add_priority(doc: Document) -> None:
    _heading(doc, "2. Priority Order", space_before=8)
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run(PRIORITY)
    _set_run_font(r, size_pt=9, bold=True, color=BODY, name="Calibri")
    q = doc.add_paragraph()
    q.paragraph_format.space_before = Pt(2)
    q.paragraph_format.space_after = Pt(0)
    rq = q.add_run(RULES)
    _set_run_font(rq, size_pt=8.5, color=BODY, name="Calibri")


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

    _add_lineup(doc)
    _add_priority(doc)
    add_abridged_color_key(doc, heading="3. Destination Colors", space_before=8, compact=True)
    add_diagram_and_timetable_page(doc)

    doc.save(out)
    return out


def main() -> None:
    path = rebuild()
    print(f"Wrote {path} ({PUBLICATION['pub_id']} Rev {PUBLICATION['revision']})")


if __name__ == "__main__":
    main()
