#!/usr/bin/env python3
"""Replace the TT-23 trifold left-panel station map with the SM-01 schematic.

Draws a panel-sized filled schematic (title + diagram) and embeds it so the map
uses nearly the full left column. Publication lines stay in a compact bottom band.

Archives (written once if missing):
  publications/assets/station_map_subdivision_tt23_original.png
  publications/assets/TT-23_Route23_NevilleQueen_RevisionA_v6_pre_map_replace.pptx

Usage (from repo root):
  .venv/bin/python publications/update_tt23_station_map.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE_TYPE
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

EMU = 914400
PANEL_R = 3.55

FOOTER_BAND_TOP = 7.90
SLOT_L = 0.08
SLOT_T = 0.10
SLOT_W = PANEL_R - SLOT_L - 0.05
SLOT_H = FOOTER_BAND_TOP - SLOT_T - 0.06
DPI = 300


def _shape_text(sh) -> str:
    if not sh.has_text_frame:
        return ""
    return "\n".join(p.text for p in sh.text_frame.paragraphs).strip()


def _set_textbox_style(sh, *, size_pt: float, bold: bool = False) -> None:
    for p in sh.text_frame.paragraphs:
        for run in p.runs:
            run.font.size = Pt(size_pt)
            run.font.bold = bold
            run.font.color.rgb = RGBColor(0x16, 0x16, 0x16)


def _set_shape_text(sh, text: str) -> None:
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


def _compact_left_footer(slide) -> None:
    """One line for pub+rev; Official Publication below; drop spare Revision box."""
    combined = "Publication TT-23  ·  Revision A"
    sp_tree = slide.shapes._spTree
    for sh in list(slide.shapes):
        if sh.left / EMU >= 3.5:
            continue
        text = _shape_text(sh)
        if text == "Revision A":
            sp_tree.remove(sh._element)
            continue
        if text in ("Publication TT-23", combined):
            _set_shape_text(sh, combined)
            sh.left = Inches(0.30)
            sh.top = Inches(8.00)
            sh.width = Inches(2.95)
            sh.height = Inches(0.18)
            _set_textbox_style(sh, size_pt=7.5, bold=False)
            continue
        if text == "Official Publication":
            sh.left = Inches(0.30)
            sh.top = Inches(8.18)
            sh.width = Inches(2.95)
            sh.height = Inches(0.18)
            _set_textbox_style(sh, size_pt=8.5, bold=True)
            continue
        if (
            sh.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
            and abs(sh.width / EMU - 2.73) < 0.25
            and sh.height / EMU < 0.05
            and sh.top / EMU > 6.0
        ):
            sh.left = Inches(0.30)
            sh.top = Inches(FOOTER_BAND_TOP)
            sh.width = Inches(2.95)


def _clear_left_chrome_and_map(slide) -> None:
    keep_text = {
        "Publication TT-23",
        "Publication TT-23  ·  Revision A",
        "Official Publication",
    }
    sp_tree = slide.shapes._spTree
    for sh in list(slide.shapes):
        if sh.left / EMU >= 3.5:
            continue
        text = _shape_text(sh)
        if text in keep_text:
            continue
        if text == "Revision A":
            sp_tree.remove(sh._element)
            continue
        if (
            sh.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
            and sh.height / EMU < 0.05
            and sh.top / EMU >= FOOTER_BAND_TOP - 0.05
        ):
            continue
        if abs(sh.left / EMU - 3.67) < 0.05 and sh.height / EMU > 8.0:
            continue
        sp_tree.remove(sh._element)


def _render_panel_png(out: Path = BODY_PNG) -> Path:
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
    if not pptx_path.exists():
        raise FileNotFoundError(pptx_path)

    ASSETS.mkdir(parents=True, exist_ok=True)
    if archive_original and not BACKUP_PPTX.exists():
        shutil.copy2(pptx_path, BACKUP_PPTX)
    if archive_original and not ORIG_MAP.exists():
        raise FileNotFoundError(
            f"{ORIG_MAP} missing — export the left panel from the pre-replace pptx once"
        )

    body = _render_panel_png()
    prs = Presentation(str(pptx_path))
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


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
