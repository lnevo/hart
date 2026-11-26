#!/usr/bin/env python3
"""Rebuild Neville Island local station maps (SM-02 … SM-05).

Detail schematics for West Yard, South Yard, Industries, and Shenango —
track numbers / spur names derived from:
  - publications/assets/dispatcher_panel_neville_island.png
  - SM-01 subdivision diagram + seed industry spot names

Usage (from repo root):
  .venv/bin/python publications/rebuild_local_station_maps.py

Writes PNGs under publications/assets/ and letter docs under docs/.

The drawers live in the local_station_maps package next to this file (one module per
station, shared primitives in local_station_maps/kit.py); this module keeps the map table,
the .docx writer and the command line.
"""

from __future__ import annotations

import sys
from typing import Any
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT.parents[1] / "docs/ops"
PUB = Path(__file__).resolve().parent
ASSETS = PUB / "assets"
sys.path.insert(0, str(PUB))

from hart_pub_helpers import (  # noqa: E402
    ACCENT,
    MUTED,
    _set_run_font,
    add_publication_footer,
    set_letter_portrait,
    set_page_size,
)
import station_compass  # noqa: E402

import local_station_maps  # noqa: E402

if Path(local_station_maps.__file__).resolve().parent != PUB / "local_station_maps":
    raise ImportError(
        f"local_station_maps was loaded from {local_station_maps.__file__}, not from {PUB}; "
        "another checkout is earlier on sys.path"
    )

from local_station_maps import east_end, shenango, south_yard, west_yard  # noqa: E402
from local_station_maps.kit import (  # noqa: E402, F401  (re-exported for importers and tests)
    ACCENT_RED,
    ARIAL,
    ARIAL_BOLD,
    BG,
    GEORGIA,
    GEORGIA_BOLD,
    INK,
    MUTED_INK,
    RULE,
    SW_FILL,
    SWNUM,
    Hooks,
    _arrow,
    _canvas,
    _color_chip,
    _cp_box,
    _dot,
    _font,
    _hollow,
    _label,
    _line,
    _outset,
    _sw_badge,
)

# The constants and primitives above are re-exported from local_station_maps.kit for
# rebuild_station_map_full and the tests. The drawers and the primitives read them from
# kit, so rebinding a constant here (INK, SWNUM, the font paths ...) changes only _chrome
# below, not the maps. _font, _canvas and _paste_compass are the exception: _hooks() reads
# them from this module on every draw, so replacing them here reaches every drawer.

MAPS = [
    {
        "key": "west_yard",
        "title": "West Yard",
        "pub_id": "SM-02",
        "revision": "A",
        "effective": "23 July 2026",
        "subtitle": "",
        "docx": DOCS / "Neville_Island_Station_Map_West_Yard.docx",
        "png": ASSETS / "station_map_west_yard.png",
        "minimal_chrome": True,
        "sheet": "8x5",
        "png_only": True,
    },
    {
        "key": "south_yard",
        "title": "South Yard",
        "pub_id": "SM-03",
        "revision": "A",
        "effective": "23 July 2026",
        "subtitle": "",
        "docx": DOCS / "Neville_Island_Station_Map_South_Yard.docx",
        "png": ASSETS / "station_map_south_yard.png",
        "minimal_chrome": True,
        "sheet": "8x5",
        "png_only": True,
    },
    {
        "key": "industries",
        "title": "East End",
        "pub_id": "SM-04",
        "revision": "A",
        "effective": "23 July 2026",
        "subtitle": "",
        "docx": DOCS / "Neville_Island_Station_Map_East_End.docx",
        "png": ASSETS / "station_map_east_end.png",
        "minimal_chrome": True,
        "sheet": "8x5",
        "png_only": True,
    },
    {
        "key": "shenango",
        "title": "Shenango",
        "pub_id": "SM-05",
        "revision": "B",
        "effective": "7 November 2026",
        "subtitle": "",
        "docx": DOCS / "Neville_Island_Station_Map_Shenango.docx",
        "png": ASSETS / "station_map_shenango.png",
        "minimal_chrome": True,
        "sheet": "8x5",
        "png_only": True,
        "skip": True,  # drawn by hart/ops/station_maps/scripts/render_shenango_station_map.py
    },
    {
        "key": "shenango",
        "title": "Shenango",
        "pub_id": "SM-05",
        "revision": "B",
        "effective": "7 November 2026",
        "subtitle": "",
        "docx": DOCS / "Neville_Island_Station_Map_Shenango_Rotated.docx",
        "png": ASSETS / "station_map_shenango_rotated.png",
        "minimal_chrome": True,
        "sheet": "8x5",
        "png_only": True,
        "rotate180": True,
        "skip": True,
    },
]


def _chrome(
    draw: ImageDraw.ImageDraw,
    *,
    width: int,
    height: int,
    title: str,
    subtitle: str = "",
    pub_id: str = "",
    revision: str = "",
    minimal: bool = False,
) -> tuple[int, int, int, int]:
    """Title / footer chrome. Returns content box (left, top, right, bottom).

    minimal=True: title + WEST/EAST only (no subtitle, rules, or publication footer).
    """
    margin = 48
    title_font = _font(ARIAL_BOLD, 36)
    sub_font = _font(GEORGIA, 20)
    foot_font = _font(GEORGIA, 16)
    foot_bold = _font(GEORGIA_BOLD, 16)
    dir_font = _font(ARIAL, 14)

    draw.text((width // 2, 28), title.upper(), font=title_font, fill=INK, anchor="mt")

    if minimal:
        draw.text((margin, height - 36), "← WEST", font=dir_font, fill=MUTED_INK, anchor="lm")
        draw.text((width - margin, height - 36), "EAST →", font=dir_font, fill=MUTED_INK, anchor="rm")
        return margin + 20, 90, width - margin - 20, height - 56

    if subtitle:
        draw.text((width // 2, 72), subtitle, font=sub_font, fill=MUTED_INK, anchor="mt")
    draw.line([(margin, 98), (width - margin, 98)], fill=RULE, width=4)

    foot_y = height - 56
    draw.line([(margin, foot_y), (width - margin, foot_y)], fill=RULE, width=3)
    draw.text(
        (width // 2, foot_y + 10),
        f"Publication {pub_id}  ·  Revision {revision}",
        font=foot_font,
        fill=INK,
        anchor="mt",
    )
    draw.text(
        (width // 2, foot_y + 30),
        "Official Publication  ·  Neville Island Operations",
        font=foot_bold,
        fill=INK,
        anchor="mt",
    )

    draw.text((margin, height - 78), "← WEST", font=dir_font, fill=MUTED_INK, anchor="lm")
    draw.text((width - margin, height - 78), "EAST →", font=dir_font, fill=MUTED_INK, anchor="rm")

    return margin + 20, 120, width - margin - 20, foot_y - 36


def _paste_compass(base: Image.Image, **place: Any) -> None:
    """The station compass, its letters in this module's fallback font loader (_font, read at call time)."""
    station_compass.paste_compass(base, load_font=_font, **place)


def _hooks() -> Hooks:
    """Fonts, canvas and compass as this module holds them now (read at call time)."""
    return Hooks(font=_font, canvas=_canvas, paste_compass=_paste_compass)


def draw_west_yard(meta: dict) -> Image.Image:
    return west_yard.draw_west_yard(meta, _hooks())


def draw_south_yard(meta: dict) -> Image.Image:
    return south_yard.draw_south_yard(meta, _hooks())


def draw_industries(meta: dict) -> Image.Image:
    return east_end.draw_industries(meta, _hooks())


def draw_shenango(meta: dict) -> Image.Image:
    return shenango.draw_shenango(meta, _hooks())


DRAWERS = {
    "west_yard": draw_west_yard,
    "south_yard": draw_south_yard,
    "industries": draw_industries,
    "shenango": draw_shenango,
}


def rebuild_docx(meta: dict, png: Path) -> Path:
    doc = Document()

    # 8×5 landscape desk sheet — PNG only, full-bleed (margins in the PNG)
    if meta.get("sheet") == "8x5" or meta.get("png_only"):
        set_page_size(
            doc,
            width_in=8.0,
            height_in=5.0,
            margin_in=0.0,
            top_margin_in=0.0,
            bottom_margin_in=0.0,
        )
        section = doc.sections[0]
        section.header_distance = Inches(0)
        section.footer_distance = Inches(0)
        pic = doc.add_paragraph()
        pic.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pic.paragraph_format.space_before = Pt(0)
        pic.paragraph_format.space_after = Pt(0)
        pic.add_run().add_picture(str(png), width=Inches(8.0))
        doc.save(meta["docx"])
        return meta["docx"]

    set_letter_portrait(doc)
    section = doc.sections[0]
    section.top_margin = Inches(0.55)
    section.bottom_margin = Inches(0.55)
    section.left_margin = Inches(0.55)
    section.right_margin = Inches(0.55)

    minimal = bool(meta.get("minimal_chrome"))
    if not minimal:
        add_publication_footer(
            doc,
            pub_id=meta["pub_id"],
            revision=meta["revision"],
            effective=meta["effective"],
            compact=False,
        )

    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    t.paragraph_format.space_before = Pt(0)
    t.paragraph_format.space_after = Pt(2)
    r = t.add_run("HART RAILROAD")
    _set_run_font(r, size_pt=13, bold=True, color=ACCENT, name="Arial")

    s = doc.add_paragraph()
    s.alignment = WD_ALIGN_PARAGRAPH.CENTER
    s.paragraph_format.space_before = Pt(0)
    s.paragraph_format.space_after = Pt(2)
    r = s.add_run("Pittsburgh & Chartiers Valley Division  ·  Neville Island Operations")
    _set_run_font(r, size_pt=9.5, color=MUTED, name="Georgia")

    h = doc.add_paragraph()
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    h.paragraph_format.space_before = Pt(4)
    h.paragraph_format.space_after = Pt(2 if meta.get("subtitle") else 8)
    r = h.add_run(f"Station Map  ·  {meta['title']}")
    _set_run_font(r, size_pt=16, bold=True, color=ACCENT, name="Georgia")

    if meta.get("subtitle"):
        sub = doc.add_paragraph()
        sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sub.paragraph_format.space_before = Pt(0)
        sub.paragraph_format.space_after = Pt(8)
        r = sub.add_run(meta["subtitle"])
        _set_run_font(r, size_pt=10, color=MUTED, name="Georgia")

    pic = doc.add_paragraph()
    pic.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pic.paragraph_format.space_before = Pt(0)
    pic.paragraph_format.space_after = Pt(0)
    pic.add_run().add_picture(str(png), width=Inches(7.4))

    doc.save(meta["docx"])
    return meta["docx"]


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    for meta in MAPS:
        if meta.get("skip"):
            print(f"Skipped {meta['pub_id']} ({meta['png'].name}): drawn in the hart repo")
            continue
        drawer = DRAWERS[meta["key"]]
        img = drawer(meta)
        img.save(meta["png"], "PNG")
        docx = rebuild_docx(meta, meta["png"])
        print(f"Wrote {meta['png']}")
        print(f"Wrote {docx} ({meta['pub_id']} Rev {meta['revision']})")


if __name__ == "__main__":
    main()