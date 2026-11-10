#!/usr/bin/env python3
"""Rebuild Neville Island Crew Instructions (one 5×8 sheet per job + station map).

Jobs: D749 (CI-D749), NVL (CI-NVL), CK1 (CI-CK1).
Page 2 is the station map + Route 23 timetable (same back page as YM/DS).
Publication identity lives in the footer.

Usage (from repo root):
  .venv/bin/python publications/rebuild_crew_instructions.py

Writes:
  docs/Neville_Island_Crew_D749.docx
  docs/Neville_Island_Crew_NVL.docx
  docs/Neville_Island_Crew_CK1.docx
"""

from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT.parents[1] / "docs/ops"
PUB = Path(__file__).resolve().parent
ASSETS = PUB / "assets"
ROSTER_PHOTOS = ROOT.parents[1] / "jmri/resources/roster"  # the loco photos the roster uses
sys.path.insert(0, str(PUB))

from hart_pub_helpers import (  # noqa: E402
    ACCENT,
    BODY,
    MUTED,
    _set_run_font,
    add_abridged_color_key,
    abridged_color_key_height_in,
    add_body,
    add_compact_title,
    add_diagram_and_timetable_page,
    add_publication_footer,
    set_page_size,
)

PUBLICATION = {
    "title": "Crew Instructions",
    "revision": "D",
    "effective": "21 July 2026",
}

CREWS: list[dict] = [
    {
        "train": "D749",
        "pub_id": "CI-D749",
        "out": DOCS / "Neville_Island_Crew_D749.docx",
        "subtitle": "CSX Neville Island Switcher",
        "engine": "CR 1993  ·  GE B23-7",
        "photo": ROSTER_PHOTOS / "1993.jpg",
        "intro": (
            "CSX turn between Demmler / McKeesport and Neville Island. The train starts "
            "tied down in West Yard. Deliver the Demmler inbound to South Yard, hostle "
            "the engine to the engine terminal, then return for the Demmler / McKeesport "
            "outbound block, depart westbound, and terminate again in West Yard."
        ),
        "steps": [
            "Find the train tied down in West Yard with the inbound Demmler block.",
            "Obtain dispatcher clearance and run the inbound to South Yard.",
            "Set out the Demmler / McKeesport inbound at South Yard.",
            "Take the engine light to the engine terminal. Top off fuel and sand if needed.",
            "When called for the outbound, interchange with the Yardmaster. Build and lift "
            "the Demmler / McKeesport outbound block.",
            "With clearance, depart toward McKeesport with the outbound block.",
            "On return, follow Yardmaster instructions and tie down in West Yard. Secure the engine.",
        ],
    },
    {
        "train": "NVL",
        "pub_id": "CI-NVL",
        "out": DOCS / "Neville_Island_Crew_NVL.docx",
        "subtitle": "Neville Island Turn",
        "engine": "POHC 2091  ·  EMD GP20",
        "photo": ROSTER_PHOTOS / "2091.jpg",
        "intro": (
            "Neville Island turn from Scully Yard. Interchange at South Yard, "
            "work Neville Island industries, then return to McKees Rocks / Scully with the "
            "outbound block."
        ),
        "steps": [
            "Assign on the train at Scully Yard with the inbound Scully block.",
            "Obtain dispatcher clearance and run to South Yard.",
            "Interchange with the Yardmaster. Lift the local industry cut.",
            "Work Neville Island industries: Aristech, A. Stucki, Calgon Carbon, Ferrellgas, Kosmos Cement, and Shenango Coke Works.",
            "Return to South Yard for final interchange. Lift the Scully / McKees Rocks outbound block.",
            "With dispatcher clearance, depart for McKees Rocks / Scully Yard and secure.",
        ],
    },
    {
        "train": "CK1",
        "pub_id": "CI-CK1",
        "out": DOCS / "Neville_Island_Crew_CK1.docx",
        "subtitle": "Coke Transfer",
        "engine": "Unassigned",
        "photo": None,
        "intro": (
            "Shenango Coke Works pickup and delivery, scale calibration, weigh, and sort. "
            "Power is assigned by the Yardmaster."
        ),
        "steps": [
            "Report to the Yardmaster for the assigned engine before going to work.",
            "Calibrate the track scale with the scale test car (see EQ-01 Scale Operating Instructions).",
            "Handle Shenango Coke Works pickup and delivery as directed by the Yardmaster.",
            "Weigh the coke pull on the South Yard west-lead scale at a steady stretch; do not apply brakes under weigh.",
            "Sort and set out weighed cars in South Yard for classification.",
        ],
    },
]


def _clear_table_borders(table) -> None:
    tbl = table._tbl
    tblPr = tbl.tblPr if tbl.tblPr is not None else OxmlElement("w:tblPr")
    if tbl.tblPr is None:
        tbl.insert(0, tblPr)
    old = tblPr.find(qn("w:tblBorders"))
    if old is not None:
        tblPr.remove(old)
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        el.set(qn("w:sz"), "0")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "auto")
        borders.append(el)
    tblPr.append(borders)


def _cell_margins(cell, *, top: int = 40, bottom: int = 40, left: int = 40, right: int = 40) -> None:
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


def _cell_vertical_center(cell) -> None:
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    old = tcPr.find(qn("w:vAlign"))
    if old is not None:
        tcPr.remove(old)
    vAlign = OxmlElement("w:vAlign")
    vAlign.set(qn("w:val"), "center")
    tcPr.append(vAlign)


def _add_engine_block(doc: Document, crew: dict) -> None:
    """Photo left, train/engine details right — borderless 2-col table."""
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT

    table = doc.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _clear_table_borders(table)

    left = table.rows[0].cells[0]
    right = table.rows[0].cells[1]
    left.width = Inches(1.95)
    right.width = Inches(2.45)

    # Left: photo or placeholder (set content before cell props — text="" wipes tcPr)
    left.text = ""
    photo = crew.get("photo")
    if photo is not None and Path(photo).is_file():
        p = left.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        p.add_run().add_picture(str(photo), width=Inches(1.85))
    else:
        p0 = left.paragraphs[0]
        p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p0.paragraph_format.space_before = Pt(0)
        p0.paragraph_format.space_after = Pt(0)
        r0 = p0.add_run("No assigned")
        _set_run_font(r0, size_pt=9, color=MUTED, name="Calibri")
        p1 = left.add_paragraph()
        p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r1 = p1.add_run("engine photo")
        _set_run_font(r1, size_pt=9, color=MUTED, name="Calibri")

    # Right: train, subtitle, engine only (summary stays outside the table)
    right.text = ""
    p_train = right.paragraphs[0]
    p_train.paragraph_format.space_before = Pt(0)
    p_train.paragraph_format.space_after = Pt(2)
    r_train = p_train.add_run(crew["train"])
    _set_run_font(r_train, size_pt=15, bold=True, color=ACCENT)

    p_sub = right.add_paragraph()
    p_sub.paragraph_format.space_before = Pt(0)
    p_sub.paragraph_format.space_after = Pt(5)
    r_sub = p_sub.add_run(crew["subtitle"])
    _set_run_font(r_sub, size_pt=9.5, color=MUTED, name="Calibri")

    p_eng = right.add_paragraph()
    p_eng.paragraph_format.space_before = Pt(0)
    p_eng.paragraph_format.space_after = Pt(0)
    r_eng = p_eng.add_run(f"Engine:  {crew['engine']}")
    _set_run_font(r_eng, size_pt=10.5, bold=True, color=BODY, name="Calibri")

    # Cell props after content so they aren't wiped by cell.text =
    _cell_margins(left, top=20, bottom=60, left=20, right=60)
    _cell_margins(right, top=20, bottom=60, left=40, right=20)
    left.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    right.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    _cell_vertical_center(left)
    _cell_vertical_center(right)


def _estimate_intro_height_in(text: str, *, size_pt: float = 9.5, line_spacing: float = 1.08,
                              space_before: float = 10, space_after: float = 4,
                              content_width_in: float = 4.44) -> float:
    """Rough wrapped-paragraph height for gap layout."""
    avg_char_in = (size_pt * 0.48) / 72.0
    cpl = max(20, int(content_width_in / avg_char_in))
    lines = max(1, (len(text) + cpl - 1) // cpl)
    return (space_before + lines * size_pt * line_spacing + space_after) / 72.0


def _engine_block_height_in(crew: dict) -> float:
    photo = crew.get("photo")
    if photo is not None and Path(photo).is_file():
        try:
            from PIL import Image
            w, h = Image.open(photo).size
            return 1.85 * h / w + 0.14
        except Exception:
            return 0.70
    return 0.70


def _float_table(table, *, y_in: float, width_in: float = 4.44) -> None:
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
    tblpPr.set(qn("w:tblpY"), str(max(int(y_in * 1440), 0)))
    tblpPr.set(qn("w:tblpXSpec"), "center")
    tblPr.append(tblpPr)
    old_ov = tblPr.find(qn("w:tblOverlap"))
    if old_ov is not None:
        tblPr.remove(old_ov)
    ov = OxmlElement("w:tblOverlap")
    ov.set(qn("w:val"), "never")
    tblPr.append(ov)
    for cell in table.rows[0].cells:
        cell.width = Inches(width_in)


def _estimate_steps_height_in(steps: list[str], *, size_pt: float = 9.5,
                              content_width_in: float = 4.3) -> float:
    """Rough height of heading + numbered steps."""
    avg_char_in = (size_pt * 0.48) / 72.0
    cpl = max(20, int(content_width_in / avg_char_in))
    # heading + after
    total_pt = 11 + 4
    for step in steps:
        lines = max(1, (len(f"1.  {step}") + cpl - 1) // cpl)
        total_pt += lines * size_pt * 1.05 + 3
    return total_pt / 72.0


def _add_steps_centered(
    doc: Document,
    steps: list[str],
    *,
    gap_top_in: float,
    gap_bottom_in: float,
) -> None:
    """Float Crew Steps at the vertical center of the summary→color-key gap."""
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _clear_table_borders(table)
    cell = table.rows[0].cells[0]
    cell.text = ""

    p_h = cell.paragraphs[0]
    p_h.paragraph_format.space_before = Pt(0)
    p_h.paragraph_format.space_after = Pt(4)
    r_h = p_h.add_run("CREW STEPS")
    _set_run_font(r_h, size_pt=11, bold=True, color=ACCENT)

    for i, step in enumerate(steps, start=1):
        p = cell.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.left_indent = Inches(0.05)
        r = p.add_run(f"{i}.  {step}")
        _set_run_font(r, size_pt=9.5, color=BODY, name="Calibri")

    _cell_margins(cell, top=0, bottom=0, left=20, right=20)
    steps_h = _estimate_steps_height_in(steps)
    gap_h = max(gap_bottom_in - gap_top_in, steps_h)
    y_in = gap_top_in + max((gap_h - steps_h) / 2.0, 0.0)
    _float_table(table, y_in=y_in)


def rebuild_crew(crew: dict) -> Path:
    page_h = 8.0
    margin = 0.28
    top_margin = 0.58
    bottom_clearance = 0.42

    doc = Document()
    set_page_size(
        doc,
        width_in=5.0,
        height_in=page_h,
        margin_in=margin,
        top_margin_in=top_margin,
        bottom_margin_in=0.36,
    )
    add_publication_footer(
        doc,
        pub_id=crew["pub_id"],
        revision=PUBLICATION["revision"],
        effective=PUBLICATION["effective"],
        compact=True,
    )
    add_compact_title(
        doc,
        PUBLICATION["title"],
        revision=PUBLICATION["revision"],
        size_pt=12,
        rule_after=3,
    )
    _add_engine_block(doc, crew)
    add_body(
        doc,
        crew["intro"],
        space_before=20,
        space_after=4,
        size_pt=9.5,
        line_spacing=1.08,
    )

    chart_h = abridged_color_key_height_in(compact=True, pin_title=True)
    chart_top = page_h - bottom_clearance - chart_h
    title_block = 0.36  # title + rule
    # Keep steps Y based on pre-drop summary position so only the summary moves down.
    gap_top = (
        top_margin
        + title_block
        + _engine_block_height_in(crew)
        + _estimate_intro_height_in(crew["intro"], space_before=10, space_after=4)
    )
    gap_bottom = chart_top - 0.08
    _add_steps_centered(doc, crew["steps"], gap_top_in=gap_top, gap_bottom_in=gap_bottom)

    add_abridged_color_key(
        doc,
        heading="Destination Colors",
        compact=True,
        pin_to_bottom=True,
        page_height_in=page_h,
        bottom_clearance_in=bottom_clearance,
    )

    add_diagram_and_timetable_page(doc)

    out = Path(crew["out"])
    doc.save(out)
    return out


def rebuild_all() -> list[Path]:
    return [rebuild_crew(crew) for crew in CREWS]


def main() -> None:
    paths = rebuild_all()
    legacy = DOCS / "Neville_Island_Crew_Instructions.docx"
    if legacy.exists():
        legacy.unlink()
        print(f"Removed legacy {legacy}")
    for path, crew in zip(paths, CREWS):
        print(f"Wrote {path} ({crew['pub_id']} Rev {PUBLICATION['revision']})")


if __name__ == "__main__":
    main()
