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
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NamedTuple, get_args

from docx import Document
from docx.document import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt
from docx.text.paragraph import Paragraph
from PIL import Image

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
# kit, so rebinding a constant here (INK, SWNUM, the font paths ...) does not change the
# maps. _font, _canvas and _paste_compass are the exception: _hooks() reads
# them from this module on every draw, so replacing them here reaches every drawer.

DrawerKey = Literal["west_yard", "south_yard", "industries", "shenango"]
SheetKind = Literal["8x5", "letter"]


class Revision(NamedTuple):
    """A publication revision letter and the date it takes effect."""

    letter: str
    effective: str


REV_A = Revision("A", "23 July 2026")
SM05_REV_B = Revision("B", "7 November 2026")


class StationMapError(ValueError):
    """A station map record that cannot be drawn or written."""


@dataclass(frozen=True)
class StationMap:
    """One local station map: its drawer, its publication line and the two files it writes.

    ``sheet`` "8x5" is the landscape desk sheet, the PNG full bleed on the page; "letter" is a
    portrait page with a title block over the PNG. ``drawn_elsewhere`` maps are drawn by
    ops/station_maps/scripts and skipped here.
    """

    key: DrawerKey
    title: str
    pub_id: str
    revision: Revision
    docx: Path
    png: Path
    subtitle: str = ""
    sheet: SheetKind = "8x5"
    minimal_chrome: bool | None = None  # unset: True on the 8x5 desk sheet, False (with the footer) on letter
    rotate180: bool = False
    drawn_elsewhere: bool = False

    def __post_init__(self) -> None:
        if self.minimal_chrome is None:
            object.__setattr__(self, "minimal_chrome", self.sheet == "8x5")
        if self.key not in get_args(DrawerKey):
            raise StationMapError(f"{self.pub_id} {self.title}: no drawer {self.key!r}; one of {get_args(DrawerKey)}")
        if self.sheet not in get_args(SheetKind):
            raise StationMapError(f"{self.pub_id} {self.title}: sheet {self.sheet!r} is not one of {get_args(SheetKind)}")
        if not self.pub_id.startswith("SM-"):
            raise StationMapError(f"{self.title}: publication id {self.pub_id!r} does not start with SM-")
        if self.png.suffix != ".png" or self.docx.suffix != ".docx":
            raise StationMapError(f"{self.pub_id} {self.title}: expected a .png and a .docx, got {self.png}, {self.docx}")


MAPS: list[StationMap] = [
    StationMap("west_yard", "West Yard", "SM-02", REV_A,
               DOCS / "Neville_Island_Station_Map_West_Yard.docx", ASSETS / "station_map_west_yard.png"),
    StationMap("south_yard", "South Yard", "SM-03", REV_A,
               DOCS / "Neville_Island_Station_Map_South_Yard.docx", ASSETS / "station_map_south_yard.png"),
    StationMap("industries", "East End", "SM-04", REV_A,
               DOCS / "Neville_Island_Station_Map_East_End.docx", ASSETS / "station_map_east_end.png"),
    # SM-05 is drawn by ops/station_maps/scripts/render_shenango_station_map.py.
    StationMap("shenango", "Shenango", "SM-05", SM05_REV_B,
               DOCS / "Neville_Island_Station_Map_Shenango.docx", ASSETS / "station_map_shenango.png",
               drawn_elsewhere=True),
    StationMap("shenango", "Shenango", "SM-05", SM05_REV_B,
               DOCS / "Neville_Island_Station_Map_Shenango_Rotated.docx", ASSETS / "station_map_shenango_rotated.png",
               rotate180=True, drawn_elsewhere=True),
]


def _paste_compass(base: Image.Image, *, cx: float, cy: float, size: int, north: str = "right") -> None:
    """The station compass, its letters in this module's fallback font loader (_font, read at call time)."""
    station_compass.paste_compass(base, cx=cx, cy=cy, size=size, north=north, load_font=_font)


def _hooks() -> Hooks:
    """Fonts, canvas and compass as this module holds them now (read at call time)."""
    return Hooks(font=_font, canvas=_canvas, paste_compass=_paste_compass)


def draw_west_yard(meta: StationMap) -> Image.Image:
    return west_yard.draw_west_yard(meta.title, _hooks())


def draw_south_yard(meta: StationMap) -> Image.Image:
    return south_yard.draw_south_yard(meta.title, _hooks())


def draw_industries(meta: StationMap) -> Image.Image:
    return east_end.draw_industries(meta.title, _hooks())


def draw_shenango(meta: StationMap) -> Image.Image:
    return shenango.draw_shenango(meta.title, _hooks(), rotate180=meta.rotate180)


DRAWERS: dict[DrawerKey, Callable[[StationMap], Image.Image]] = {
    "west_yard": draw_west_yard,
    "south_yard": draw_south_yard,
    "industries": draw_industries,
    "shenango": draw_shenango,
}


def _centred_paragraph(doc: DocxDocument, *, before: float, after: float) -> Paragraph:
    """A new centred paragraph with this spacing, in points."""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    return p


def _add_desk_sheet(doc: DocxDocument, png: Path) -> None:
    """8×5 landscape desk sheet: the PNG full bleed, its margins drawn in the PNG."""
    set_page_size(doc, width_in=8.0, height_in=5.0, margin_in=0.0, top_margin_in=0.0, bottom_margin_in=0.0)
    section = doc.sections[0]
    section.header_distance = Inches(0)
    section.footer_distance = Inches(0)
    _centred_paragraph(doc, before=0, after=0).add_run().add_picture(str(png), width=Inches(8.0))


def _add_letter_title_block(doc: DocxDocument, meta: StationMap) -> None:
    """Railroad name, division line, the map title and its subtitle, centred."""
    r = _centred_paragraph(doc, before=0, after=2).add_run("HART RAILROAD")
    _set_run_font(r, size_pt=13, bold=True, color=ACCENT, name="Arial")
    r = _centred_paragraph(doc, before=0, after=2).add_run(
        "Pittsburgh & Chartiers Valley Division  ·  Neville Island Operations")
    _set_run_font(r, size_pt=9.5, color=MUTED, name="Georgia")
    r = _centred_paragraph(doc, before=4, after=2 if meta.subtitle else 8).add_run(f"Station Map  ·  {meta.title}")
    _set_run_font(r, size_pt=16, bold=True, color=ACCENT, name="Georgia")
    if meta.subtitle:
        r = _centred_paragraph(doc, before=0, after=8).add_run(meta.subtitle)
        _set_run_font(r, size_pt=10, color=MUTED, name="Georgia")


def _add_letter_page(doc: DocxDocument, meta: StationMap, png: Path) -> None:
    """Letter portrait: the publication footer unless minimal, the title block, the PNG 7.4 in wide."""
    set_letter_portrait(doc)
    section = doc.sections[0]
    section.top_margin = Inches(0.55)
    section.bottom_margin = Inches(0.55)
    section.left_margin = Inches(0.55)
    section.right_margin = Inches(0.55)
    if not meta.minimal_chrome:
        add_publication_footer(
            doc,
            pub_id=meta.pub_id,
            revision=meta.revision.letter,
            effective=meta.revision.effective,
            compact=False,
        )
    _add_letter_title_block(doc, meta)
    _centred_paragraph(doc, before=0, after=0).add_run().add_picture(str(png), width=Inches(7.4))


def rebuild_docx(meta: StationMap, png: Path) -> Path:
    """Write ``meta``'s .docx around ``png`` and return its path."""
    doc = Document()
    if meta.sheet == "8x5":
        _add_desk_sheet(doc, png)
    else:
        _add_letter_page(doc, meta, png)
    doc.save(str(meta.docx))
    return meta.docx


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    for meta in MAPS:
        if meta.drawn_elsewhere:
            print(f"Skipped {meta.pub_id} ({meta.png.name}): drawn in the hart repo")
            continue
        drawer = DRAWERS[meta.key]
        img = drawer(meta)
        img.save(meta.png, "PNG")
        docx = rebuild_docx(meta, meta.png)
        print(f"Wrote {meta.png}")
        print(f"Wrote {docx} ({meta.pub_id} Rev {meta.revision.letter})")


if __name__ == "__main__":
    main()