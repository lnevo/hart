#!/usr/bin/env python3
"""Rebuild Neville Island Yardmaster Sequence (YM-01; the revision comes from the crew master).

Page 1: sequence + color/blocking legend.
Page 2: subdivision diagram + narrow TT-23 timetable (no map chrome).
Publication identity lives in the footer.

Page-1 spacing is hand-tuned; keep it on rebuild:
  top/bottom margins 0.48 / 0.36; title rule_after=3;
  soft pad before §1; §1→§2 gap ~6pt before heading (not a large bias pad);
  sequence rows 17/28pt; legend rows 16/18pt (room for nine legend rows plus the yard rules).

The text is read from the crew master, ops/hart-ops/data/crew.json (job "yardmaster").

Usage (from ops/hart-ops):
  .venv/bin/python publications/rebuild_yardmaster_sequence.py

Writes:
  docs/Neville_Island_Yardmaster_Sequence.docx
"""

from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from docx.document import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt
from docx.table import Table, _Row

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT.parents[1] / "docs/ops"
PUB = Path(__file__).resolve().parent
sys.path.insert(0, str(PUB))

from hart_ooxml import set_cell_margins  # noqa: E402
from hart_pub_helpers import (  # noqa: E402
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
from hart_pub_styles import (  # noqa: E402
    add_section_heading,
    add_soft_pad,
    fix_table_rows,
    paint_header_row,
    set_column_widths,
)

CANONICAL = DOCS / "Neville_Island_Yardmaster_Sequence.docx"

import crew_master  # noqa: E402

# The publication line, the blocking list, the yard rules and the sequence come from the crew master
# (ops/hart-ops/data/crew.json, job "yardmaster", ADR-039).
_MASTER = crew_master.load()
_JOB = crew_master.job(_MASTER, "yardmaster")
PUBLICATION = crew_master.publication(_JOB)

# Color, fill, text, destination, block, in the job's color order (the site shows the same), then the
# uncolored storage row (legend_extra, which the site shows too).
LegendEntry = tuple[str, str, str, str, str]
BLOCK_LEGEND: list[LegendEntry] = crew_master.block_legend(_MASTER)

# Yard rules printed under the blocking list.
YARD_RULES: list[str] = _JOB["rules"]

SEQUENCE: list[tuple[str, str, str]] = crew_master.yard_sequence(_MASTER)

HEADING_PT = 10.5
HEADER_PT = 9.5  # header row text after style_table
SIDE_MARGIN = 45  # cell margins left and right, twips
LEGEND_MARGIN = 28  # blocking list cell margins top and bottom, twips


def _fill_sequence_rows(table: Table) -> None:
    """Step number, train and yardmaster action in each body row, in Calibri."""
    for row, (num, move, action) in zip(table.rows[1:], SEQUENCE):
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


def _add_sequence(doc: DocxDocument) -> None:
    """Section 1: the yard sequence, rows at 28 pt under a 17 pt header."""
    add_section_heading(doc, "1. Sequence", space_before=4, size_pt=HEADING_PT)
    table = doc.add_table(rows=1 + len(SEQUENCE), cols=3)
    fill_header_row(table.rows[0], ["#", "Train", "Yardmaster action"])
    _fill_sequence_rows(table)
    style_table(table)
    # style_table rewrites the run fonts; the header and the rows are written again after it.
    paint_header_row(table.rows[0], size_pt=HEADER_PT)
    _fill_sequence_rows(table)
    fix_table_rows(table, header_pt=17, body_pt=28, margin=36, side_margin=SIDE_MARGIN)
    set_column_widths(table, [Inches(0.35), Inches(1.15), Inches(2.8)])


def _swatch(row: _Row, entry: LegendEntry) -> None:
    """The colour swatch of one legend row, from the job's color list."""
    label, fill, text_hex, _dests, _block = entry
    fill_swatch_cell(row.cells[0], label, fill_hex=fill, text_hex=text_hex)


def _fill_legend_rows(legend: Table, *, swatch_pt: float | None) -> None:
    """Swatch, destinations and block in each body row; ``swatch_pt`` resizes the swatch label."""
    for row, entry in zip(legend.rows[1:], BLOCK_LEGEND):
        _swatch(row, entry)
        if swatch_pt is not None:
            for run in row.cells[0].paragraphs[0].runs:
                run.font.size = Pt(swatch_pt)
        _label, _fill, _text_hex, dests, block = entry

        row.cells[1].text = ""
        r1 = row.cells[1].paragraphs[0].add_run(dests)
        _set_run_font(r1, size_pt=9.5, color=BODY, name="Calibri")

        row.cells[2].text = ""
        r2 = row.cells[2].paragraphs[0].add_run(block)
        _set_run_font(r2, size_pt=9.5, color=BODY, name="Calibri")


def _restamp_swatches(legend: Table) -> None:
    """Write the swatches last, so their fill and label survive the row and margin pass."""
    for row, entry in zip(legend.rows[1:], BLOCK_LEGEND):
        _swatch(row, entry)
        for p in row.cells[0].paragraphs:
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            for run in p.runs:
                run.font.size = Pt(9)
        set_cell_margins(row.cells[0], top=LEGEND_MARGIN, left=SIDE_MARGIN, bottom=LEGEND_MARGIN, right=SIDE_MARGIN)


def _add_block_legend(doc: DocxDocument) -> None:
    """Section 2: the blocking list, colour swatches at 18 pt rows under a 16 pt header."""
    add_soft_pad(doc, before=6, after=2)
    add_section_heading(doc, "2. Blocking List", space_before=6, size_pt=HEADING_PT)
    legend = doc.add_table(rows=1 + len(BLOCK_LEGEND), cols=3)
    fill_header_row(legend.rows[0], ["Color", "Destination", "Block"])
    _fill_legend_rows(legend, swatch_pt=None)
    style_table(legend)
    paint_header_row(legend.rows[0], size_pt=HEADER_PT)
    _fill_legend_rows(legend, swatch_pt=9)
    fix_table_rows(legend, header_pt=16, body_pt=18, margin=LEGEND_MARGIN, side_margin=SIDE_MARGIN)
    _restamp_swatches(legend)
    set_column_widths(legend, [Inches(0.8), Inches(2.0), Inches(1.5)])


def _add_yard_rules(doc: DocxDocument) -> None:
    """Section 3: the yard rules as bullets."""
    add_section_heading(doc, "3. Yard Rules", space_before=6, size_pt=HEADING_PT)
    for rule in YARD_RULES:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(1)
        r = p.add_run("• " + rule)
        _set_run_font(r, size_pt=9, color=BODY, name="Calibri")


def rebuild(out: Path = CANONICAL) -> Path:
    """Write YM-01 to ``out`` and return it."""
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
    add_soft_pad(doc, before=4, after=2)

    _add_sequence(doc)
    _add_block_legend(doc)
    _add_yard_rules(doc)
    add_diagram_and_timetable_page(doc)

    doc.save(out)
    return out


def main() -> None:
    path = rebuild()
    print(f"Wrote {path} ({PUBLICATION['pub_id']} Rev {PUBLICATION['revision']})")


if __name__ == "__main__":
    main()
