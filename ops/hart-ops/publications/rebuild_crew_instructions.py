#!/usr/bin/env python3
"""Rebuild Neville Island Crew Instructions (one 5×8 sheet per job + station map).

Jobs: D749 (CI-D749), NVL (CI-NVL), CK1 (CI-CK1).
Page 2 is the station map + Route 23 timetable (same back page as YM/DS).
Publication identity lives in the footer.

The jobs and their text are read from the crew master, ops/hart-ops/data/crew.json (crew_master.crews), when the
sheets are built; importing this module reads no file.

Usage (from ops/hart-ops):
  .venv/bin/python publications/rebuild_crew_instructions.py

Writes:
  docs/Neville_Island_Crew_D749.docx
  docs/Neville_Island_Crew_NVL.docx
  docs/Neville_Island_Crew_CK1.docx
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, NamedTuple, TypedDict

from docx import Document
from docx.document import Document as DocxDocument
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from docx.table import _Cell
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT.parents[1] / "docs/ops"
PUB = Path(__file__).resolve().parent
ASSETS = PUB / "assets"
ROSTER_PHOTOS = ROOT.parents[1] / "jmri/resources/roster"  # the loco photos the roster uses
sys.path.insert(0, str(PUB))

from hart_ooxml import clear_table_borders, set_cell_margins  # noqa: E402
from hart_pub_helpers import (  # noqa: E402
    ACCENT,
    BODY,
    MUTED,
    _set_run_font,
    abridged_color_key_height_in,
    add_abridged_color_key,
    add_body,
    add_compact_title,
    add_diagram_and_timetable_page,
    add_publication_footer,
    float_table_to_page_y,
    set_page_size,
)

import crew_master  # noqa: E402


class CrewSheetError(ValueError):
    """The crew master cannot be printed as crew sheets: a missing photo or disagreeing publication lines."""


class Publication(TypedDict):
    title: str
    revision: str
    effective: str


class CrewSheet(TypedDict):
    """One crew job as its sheet prints it (crew_master.crews), with the output and photo resolved to paths."""

    train: str
    pub_id: str
    subtitle: str
    engine: str
    photo: Path | None
    intro: str
    steps: list[str]
    publication: dict[str, str]
    out: Path


class CrewSheets(NamedTuple):
    crews: list[CrewSheet]
    publication: Publication


# The 5×8 sheet (inches).
PAGE_W = 5.0
PAGE_H = 8.0
MARGIN = 0.28
TOP_MARGIN = 0.58
BOTTOM_MARGIN = 0.36
BOTTOM_CLEARANCE = 0.42  # the pinned colour key's distance from the page bottom
TITLE_BLOCK = 0.36       # title + rule
CONTENT_W = 4.44

PHOTO_W = 1.85
ENGINE_BLOCK_NO_PHOTO_IN = 0.70  # height of the engine block with the placeholder text instead of a photo
ENGINE_BLOCK_PAD_IN = 0.14


def load_crews(master: dict[str, Any]) -> list[CrewSheet]:
    """The crew jobs with their output path and photo path; a photo the master names must exist."""
    crews: list[CrewSheet] = []
    for c in crew_master.crews(master):
        photo = ROSTER_PHOTOS / c["photo"] if c["photo"] else None
        if photo is not None and not photo.is_file():
            raise CrewSheetError(f"crew {c['pub_id']}: photo {photo} is not a file")
        crews.append({
            "train": c["train"], "pub_id": c["pub_id"], "subtitle": c["subtitle"], "engine": c["engine"],
            "photo": photo, "intro": c["intro"], "steps": c["steps"], "publication": c["publication"],
            "out": DOCS / c["file"],
        })
    if not crews:
        raise CrewSheetError("the crew master has no crew jobs")
    return crews


def shared_publication(crews: list[CrewSheet]) -> Publication:
    """The one publication line (title, revision, effective) the crew sheets share."""
    first = crews[0]["publication"]
    pub: Publication = {"title": first["title"], "revision": first["revision"], "effective": first["effective"]}
    for c in crews:
        line = {k: c["publication"][k] for k in pub}
        if line != pub:
            raise CrewSheetError(
                f"crew {c['pub_id']} prints {line}, the first crew prints {dict(pub)}; "
                "the crew master's jobs must share title, revision and effective"
            )
    return pub


def load_sheets(master: dict[str, Any] | None = None) -> CrewSheets:
    """The crew sheets and their shared publication line, from the given master or the repo's crew.json."""
    crews = load_crews(crew_master.load() if master is None else master)
    return CrewSheets(crews, shared_publication(crews))


def _cell_vertical_center(cell: _Cell) -> None:
    """Centre the cell's content vertically: one w:vAlign, written last in its w:tcPr."""
    tc_pr = cell._tc.get_or_add_tcPr()
    old = tc_pr.find(qn("w:vAlign"))
    if old is not None:
        tc_pr.remove(old)
    v_align = OxmlElement("w:vAlign")
    v_align.set(qn("w:val"), "center")
    tc_pr.append(v_align)


def _tight(paragraph: Paragraph, *, after: float = 0) -> None:
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(after)


def _add_photo_cell(cell: _Cell, photo: Path | None) -> None:
    """The engine photo, or two placeholder lines when the job has none."""
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _tight(p)
    if photo is not None:
        p.paragraph_format.line_spacing = 1.0
        p.add_run().add_picture(str(photo), width=Inches(PHOTO_W))
        return
    _set_run_font(p.add_run("No assigned"), size_pt=9, color=MUTED, name="Calibri")
    p1 = cell.add_paragraph()
    p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_run_font(p1.add_run("engine photo"), size_pt=9, color=MUTED, name="Calibri")


def _add_train_cell(cell: _Cell, crew: CrewSheet) -> None:
    """Train, subtitle and engine; the summary stays outside the table."""
    cell.text = ""
    p_train = cell.paragraphs[0]
    _tight(p_train, after=2)
    _set_run_font(p_train.add_run(crew["train"]), size_pt=15, bold=True, color=ACCENT)

    p_sub = cell.add_paragraph()
    _tight(p_sub, after=5)
    _set_run_font(p_sub.add_run(crew["subtitle"]), size_pt=9.5, color=MUTED, name="Calibri")

    p_eng = cell.add_paragraph()
    _tight(p_eng)
    _set_run_font(p_eng.add_run(f"Engine:  {crew['engine']}"), size_pt=10.5, bold=True, color=BODY, name="Calibri")


def _add_engine_block(doc: DocxDocument, crew: CrewSheet) -> None:
    """Photo left, train/engine details right — borderless 2-col table."""
    table = doc.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    clear_table_borders(table)

    left = table.rows[0].cells[0]
    right = table.rows[0].cells[1]
    left.width = Inches(1.95)
    right.width = Inches(2.45)
    # Content before cell properties: cell.text = "" wipes the w:tcPr.
    _add_photo_cell(left, crew["photo"])
    _add_train_cell(right, crew)
    set_cell_margins(left, top=20, bottom=60, left=20, right=60)
    set_cell_margins(right, top=20, bottom=60, left=40, right=20)
    _cell_vertical_center(left)
    _cell_vertical_center(right)


def _chars_per_line(size_pt: float, content_width_in: float) -> int:
    """Rough characters per line at size_pt across content_width_in."""
    avg_char_in = (size_pt * 0.48) / 72.0
    return max(20, int(content_width_in / avg_char_in))


def _wrapped_lines(text: str, cpl: int) -> int:
    return max(1, (len(text) + cpl - 1) // cpl)


def _estimate_intro_height_in(text: str, *, size_pt: float = 9.5, line_spacing: float = 1.08,
                              space_before: float = 10, space_after: float = 4,
                              content_width_in: float = CONTENT_W) -> float:
    """Rough wrapped-paragraph height for gap layout."""
    lines = _wrapped_lines(text, _chars_per_line(size_pt, content_width_in))
    return (space_before + lines * size_pt * line_spacing + space_after) / 72.0


def _engine_block_height_in(crew: CrewSheet) -> float:
    """Height of the engine block: the photo at 1.85 in wide plus its padding, or the placeholder."""
    photo = crew["photo"]
    if photo is None:
        return ENGINE_BLOCK_NO_PHOTO_IN
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(photo) as img:
            w, h = img.size
    except (OSError, UnidentifiedImageError) as exc:
        raise CrewSheetError(f"crew {crew['pub_id']}: cannot read photo {photo}: {exc}") from exc
    return PHOTO_W * h / w + ENGINE_BLOCK_PAD_IN


def _estimate_steps_height_in(steps: list[str], *, size_pt: float = 9.5,
                              content_width_in: float = 4.3) -> float:
    """Rough height of heading + numbered steps."""
    cpl = _chars_per_line(size_pt, content_width_in)
    total_pt = 11.0 + 4  # heading + its space after
    for step in steps:
        total_pt += _wrapped_lines(f"1.  {step}", cpl) * size_pt * 1.05 + 3
    return total_pt / 72.0


def _add_steps_centered(
    doc: DocxDocument,
    steps: list[str],
    *,
    gap_top_in: float,
    gap_bottom_in: float,
) -> None:
    """Float Crew Steps at the vertical center of the summary→color-key gap."""
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    clear_table_borders(table)
    cell = table.rows[0].cells[0]
    cell.text = ""

    p_h = cell.paragraphs[0]
    _tight(p_h, after=4)
    _set_run_font(p_h.add_run("CREW STEPS"), size_pt=11, bold=True, color=ACCENT)

    for i, step in enumerate(steps, start=1):
        p = cell.add_paragraph()
        _tight(p, after=3)
        p.paragraph_format.left_indent = Inches(0.05)
        _set_run_font(p.add_run(f"{i}.  {step}"), size_pt=9.5, color=BODY, name="Calibri")

    set_cell_margins(cell, top=0, bottom=0, left=20, right=20)
    steps_h = _estimate_steps_height_in(steps)
    gap_h = max(gap_bottom_in - gap_top_in, steps_h)
    y_in = gap_top_in + max((gap_h - steps_h) / 2.0, 0.0)
    float_table_to_page_y(table, int(y_in * 1440))
    for c in table.rows[0].cells:
        c.width = Inches(CONTENT_W)


def _steps_gap_in(crew: CrewSheet) -> tuple[float, float]:
    """Top and bottom (inches from the page top) of the gap between the summary and the pinned colour key.

    The top uses the summary's position before its 20 pt drop, so only the summary moves down.
    """
    chart_top = PAGE_H - BOTTOM_CLEARANCE - abridged_color_key_height_in(compact=True, pin_title=True)
    top = (
        TOP_MARGIN
        + TITLE_BLOCK
        + _engine_block_height_in(crew)
        + _estimate_intro_height_in(crew["intro"], space_before=10, space_after=4)
    )
    return top, chart_top - 0.08


def _add_front_page(doc: DocxDocument, crew: CrewSheet, pub: Publication) -> None:
    set_page_size(doc, width_in=PAGE_W, height_in=PAGE_H, margin_in=MARGIN,
                  top_margin_in=TOP_MARGIN, bottom_margin_in=BOTTOM_MARGIN)
    add_publication_footer(doc, pub_id=crew["pub_id"], revision=pub["revision"], effective=pub["effective"],
                           compact=True)
    add_compact_title(doc, pub["title"], revision=pub["revision"], size_pt=12, rule_after=3)
    _add_engine_block(doc, crew)
    add_body(doc, crew["intro"], space_before=20, space_after=4, size_pt=9.5, line_spacing=1.08)
    gap_top, gap_bottom = _steps_gap_in(crew)
    _add_steps_centered(doc, crew["steps"], gap_top_in=gap_top, gap_bottom_in=gap_bottom)
    add_abridged_color_key(doc, heading="Destination Colors", compact=True, pin_to_bottom=True,
                           page_height_in=PAGE_H, bottom_clearance_in=BOTTOM_CLEARANCE)


def rebuild_crew(crew: CrewSheet, pub: Publication) -> Path:
    """Write one crew sheet (front page and the station map back page) to its output path."""
    doc = Document()
    _add_front_page(doc, crew, pub)
    add_diagram_and_timetable_page(doc)
    out = crew["out"]
    doc.save(str(out))
    return out


def rebuild_all(sheets: CrewSheets | None = None) -> list[Path]:
    sheets = load_sheets() if sheets is None else sheets
    return [rebuild_crew(crew, sheets.publication) for crew in sheets.crews]


def main() -> None:
    sheets = load_sheets()
    paths = rebuild_all(sheets)
    legacy = DOCS / "Neville_Island_Crew_Instructions.docx"
    if legacy.exists():
        legacy.unlink()
        print(f"Removed legacy {legacy}")
    for path, crew in zip(paths, sheets.crews, strict=True):
        print(f"Wrote {path} ({crew['pub_id']} Rev {sheets.publication['revision']})")


if __name__ == "__main__":
    main()
