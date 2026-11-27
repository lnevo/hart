#!/usr/bin/env python3
"""Rebuild Neville Island Dispatcher Train List (DS-01; the revision comes from the crew master).

Page 1: train lineup + priority + color key.
Page 2: subdivision diagram + narrow TT-23 timetable (no map chrome).
Publication identity lives in the footer.

Page-1 spacing is hand-tuned; keep it on rebuild:
  top/bottom margins 0.62 / 0.38; title rule_after=6;
  no soft pad before §1 (room for ten lineup rows at 23 pt); lineup before=6;
  priority before=8; destination colors before=8.
  A large page-1 bottom-bias spacer would push the lineup off the page.

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
from docx.document import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt
from docx.table import Table

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT.parents[1] / "docs/ops"
PUB = Path(__file__).resolve().parent
sys.path.insert(0, str(PUB))

from hart_pub_helpers import (  # noqa: E402
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
from hart_pub_styles import (  # noqa: E402
    add_section_heading,
    fix_table_rows,
    paint_header_row,
    set_column_widths,
)

CANONICAL = DOCS / "Neville_Island_Dispatcher_Train_List.docx"

import crew_master  # noqa: E402

# The publication line, the lineup, the rules and the priority strip come from the crew master
# (ops/hart-ops/data/crew.json, job "dispatcher", ADR-039).
_MASTER = crew_master.load()
_JOB = crew_master.job(_MASTER, "dispatcher")
PUBLICATION = crew_master.publication(_JOB)

# Order, Train, route (origin → points → destination, printed bold), dispatcher action.
LINEUP: list[tuple[str, str, str, str]] = crew_master.lineup(_MASTER)

# Dispatcher rules printed under the lineup.
RULES = " ".join(_JOB["rules"])

PRIORITY = " → ".join(_JOB["priority"])

HEADING_PT = 10


def _fill_lineup_rows(table: Table) -> None:
    """Number, train and route-plus-action in each body row, in Calibri."""
    for row, (num, train, route, action) in zip(table.rows[1:], LINEUP):
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


def _add_lineup(doc: DocxDocument) -> None:
    """Section 1: the train lineup, ten rows at 23 pt under a 16 pt header."""
    add_section_heading(doc, "1. Train Lineup", space_before=6, size_pt=HEADING_PT)
    table = doc.add_table(rows=1 + len(LINEUP), cols=3)
    fill_header_row(table.rows[0], ["#", "Train", "Dispatcher action"])
    _fill_lineup_rows(table)
    style_table(table)
    # style_table rewrites the run fonts; the header and the rows are written again after it.
    paint_header_row(table.rows[0], size_pt=8.5)
    _fill_lineup_rows(table)
    fix_table_rows(table, header_pt=16, body_pt=23, margin=32, side_margin=40)
    set_column_widths(table, [Inches(0.3), Inches(0.85), Inches(3.25)])


def _add_priority(doc: DocxDocument) -> None:
    """Section 2: the priority strip and the dispatcher rules."""
    add_section_heading(doc, "2. Priority Order", space_before=8, size_pt=HEADING_PT)
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
    """Write DS-01 to ``out`` and return it."""
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
