#!/usr/bin/env python3
"""Replace the TT-23 trifold left-panel station map with the SM-01 schematic.

Draws a panel-sized filled schematic (title + diagram) and embeds it so the map
uses nearly the full left column. Publication lines stay in a compact bottom band.

Archives (written once if missing):
  publications/assets/station_map_subdivision_tt23_original.png
  publications/assets/TT-23_Route23_NevilleQueen_RevisionA_v6_pre_map_replace.pptx

Usage (from ops/hart-ops):
  .venv/bin/python publications/update_tt23_station_map.py

Updates docs/ops/TT-23_Route23_NevilleQueen_RevisionB.pptx in place and writes
publications/assets/station_map_subdivision_tt23_panel.png. Exit 1 with the file named when the deck
or the original-map archive is missing.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.presentation import Presentation as PresentationT
from pptx.shapes.base import BaseShape
from pptx.slide import Slide
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
PUB = Path(__file__).resolve().parent
ASSETS = PUB / "assets"
sys.path.insert(0, str(PUB))

from rebuild_station_map import draw_subdivision_map  # noqa: E402

PPTX = ROOT.parents[1] / "docs/ops" / "TT-23_Route23_NevilleQueen_RevisionB.pptx"
ORIG_MAP = ASSETS / "station_map_subdivision_tt23_original.png"
BACKUP_PPTX = ASSETS / "TT-23_Route23_NevilleQueen_RevisionA_v6_pre_map_replace.pptx"
BODY_PNG = ASSETS / "station_map_subdivision_tt23_panel.png"

EMU = 914400  # per inch
PANEL_R = 3.55  # the left panel's right edge, in
LEFT_PANEL_MAX_X = 3.5  # shapes whose left edge is west of this belong to the left panel
FOOTER_LEFT, FOOTER_W, FOOTER_H = 0.30, 2.95, 0.18
PUB_LINE = "Publication TT-23"
PUB_REV_LINE = "Publication TT-23  ·  Revision A"
REV_LINE = "Revision A"
OFFICIAL_LINE = "Official Publication"

FOOTER_BAND_TOP = 7.90
SLOT_L = 0.08
SLOT_T = 0.10
SLOT_W = PANEL_R - SLOT_L - 0.05
SLOT_H = FOOTER_BAND_TOP - SLOT_T - 0.06
DPI = 300


class TT23Missing(FileNotFoundError):
    """The TT-23 deck or the archived original map is not where the update reads it."""


def _shape_text(sh: BaseShape) -> str:
    if not sh.has_text_frame:
        return ""
    return "\n".join(p.text for p in sh.text_frame.paragraphs).strip()


def _set_textbox_style(sh: BaseShape, *, size_pt: float, bold: bool = False) -> None:
    for p in sh.text_frame.paragraphs:
        for run in p.runs:
            run.font.size = Pt(size_pt)
            run.font.bold = bold
            run.font.color.rgb = RGBColor(0x16, 0x16, 0x16)


def _set_shape_text(sh: BaseShape, text: str) -> None:
    """Put text in the first run of the first paragraph and blank every other run."""
    tf = sh.text_frame
    p0 = tf.paragraphs[0]
    if p0.runs:
        p0.runs[0].text = text
        for run in p0.runs[1:]:
            run.text = ""
    else:
        p0.text = text
    # Blank any extra paragraphs
    for p in list(tf.paragraphs)[1:]:
        for run in p.runs:
            run.text = ""


def _left_panel_shapes(slide: Slide) -> list[BaseShape]:
    """The slide's shapes in the left panel, as a list so they can be removed while walking it."""
    return [sh for sh in slide.shapes if sh.left / EMU < LEFT_PANEL_MAX_X]


def _place_footer_line(sh: BaseShape, top_in: float) -> None:
    sh.left = Inches(FOOTER_LEFT)
    sh.top = Inches(top_in)
    sh.width = Inches(FOOTER_W)
    sh.height = Inches(FOOTER_H)


def _is_footer_rule(sh: BaseShape) -> bool:
    """The thin rule over the footer lines: an auto shape about 2.73 in wide, under 0.05 in tall, low on the panel."""
    return bool(
        sh.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
        and abs(sh.width / EMU - 2.73) < 0.25
        and sh.height / EMU < 0.05
        and sh.top / EMU > 6.0
    )


def _compact_left_footer(slide: Slide) -> None:
    """One line for publication and revision, Official Publication below it; the spare Revision box goes."""
    sp_tree = slide.shapes._spTree
    for sh in _left_panel_shapes(slide):
        text = _shape_text(sh)
        if text == REV_LINE:
            sp_tree.remove(sh._element)
        elif text in (PUB_LINE, PUB_REV_LINE):
            _set_shape_text(sh, PUB_REV_LINE)
            _place_footer_line(sh, 8.00)
            _set_textbox_style(sh, size_pt=7.5, bold=False)
        elif text == OFFICIAL_LINE:
            _place_footer_line(sh, 8.18)
            _set_textbox_style(sh, size_pt=8.5, bold=True)
        elif _is_footer_rule(sh):
            sh.left = Inches(FOOTER_LEFT)
            sh.top = Inches(FOOTER_BAND_TOP)
            sh.width = Inches(FOOTER_W)


def _clear_left_chrome_and_map(slide: Slide) -> None:
    """Remove every left-panel shape except the footer lines and the footer rule."""
    keep_text = {PUB_LINE, PUB_REV_LINE, OFFICIAL_LINE}
    sp_tree = slide.shapes._spTree
    for sh in _left_panel_shapes(slide):
        text = _shape_text(sh)
        if text in keep_text:
            continue
        if (
            sh.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
            and sh.height / EMU < 0.05
            and sh.top / EMU >= FOOTER_BAND_TOP - 0.05
        ):
            continue
        sp_tree.remove(sh._element)


def _render_panel_png(out: Path = BODY_PNG) -> Path:
    """The SM-01 schematic drawn to fill the map slot at DPI, with its title and no footer."""
    px_w = max(800, int(SLOT_W * DPI))
    px_h = max(1200, int(SLOT_H * DPI))
    img = draw_subdivision_map(
        width=px_w,
        height=px_h,
        include_title=True,
        include_footer=False,
        fill=True,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def update_pptx(pptx_path: Path = PPTX, *, archive_original: bool = True) -> Path:
    """Swap the left-panel map of the deck at pptx_path for the panel PNG, in place.

    With archive_original, the deck is copied to BACKUP_PPTX once, and ORIG_MAP must exist.
    """
    if not pptx_path.exists():
        raise TT23Missing(f"{pptx_path}: the TT-23 deck is missing")

    ASSETS.mkdir(parents=True, exist_ok=True)
    if archive_original and not BACKUP_PPTX.exists():
        shutil.copy2(pptx_path, BACKUP_PPTX)
    if archive_original and not ORIG_MAP.exists():
        raise TT23Missing(f"{ORIG_MAP} missing: export the left panel from the pre-replace pptx once")

    body = _render_panel_png()
    prs: PresentationT = Presentation(str(pptx_path))
    slide = prs.slides[0]
    _compact_left_footer(slide)
    _clear_left_chrome_and_map(slide)
    slide.shapes.add_picture(
        str(body), Inches(SLOT_L), Inches(SLOT_T), Inches(SLOT_W), Inches(SLOT_H)
    )
    print(f'map box {SLOT_W:.2f}" × {SLOT_H:.2f}"  panel png {body.name}')
    prs.save(str(pptx_path))
    return pptx_path


def main() -> None:
    out = update_pptx()
    print(f"Updated {out}")
    print(f"Original map archive: {ORIG_MAP}")
    if BACKUP_PPTX.exists():
        print(f"Pre-replace pptx:   {BACKUP_PPTX}")


def run() -> None:
    """main(), with a missing deck or archive printed to stderr and exit 1."""
    try:
        main()
    except TT23Missing as e:
        print(e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run()
