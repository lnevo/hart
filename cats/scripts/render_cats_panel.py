#!/usr/bin/env python3
"""Render a CATS panel TRACKPLAN to a PNG for remote review.

This is a schematic render of the panel *data* (SECTION grid: track kinds,
switch plants, block names, labels), not a live CATS GUI capture. It lets a
Cloud Agent post a reviewable board image without a full JMRI/CATS install.

Usage:
    python3 cats/scripts/render_cats_panel.py cats/panels/HART_CTC.xml out.png
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import digicon_lib  # noqa: E402  (also puts hartlib on sys.path)

CELL = 60
PAD_X = 60
PAD_Y = 90
TRACK_W = 5

RGB: TypeAlias = tuple[int, int, int]
Point: TypeAlias = tuple[int, int]
Font: TypeAlias = ImageFont.FreeTypeFont | ImageFont.ImageFont

BG: RGB = (22, 24, 28)
TRACK: RGB = (210, 214, 220)
PLANT: RGB = (90, 200, 255)
POINTS: RGB = (255, 196, 60)
BLKTXT: RGB = (150, 230, 160)
LABELTXT: RGB = (255, 255, 255)
GRIDLINE: RGB = (44, 48, 54)


class PanelError(ValueError):
    """The panel file cannot be drawn; the message names the file and what is wrong."""


@dataclass(frozen=True)
class Grid:
    """The cell span of the TRACKPLAN and where it sits in the image."""

    minx: int
    miny: int
    cols: int
    rows: int

    @property
    def size(self) -> Point:
        return PAD_X * 2 + self.cols * CELL, PAD_Y + PAD_Y // 2 + self.rows * CELL

    def origin(self, x: int, y: int) -> Point:
        """The top left corner of cell (x, y) in the image."""
        return PAD_X + (x - self.minx) * CELL, PAD_Y + (y - self.miny) * CELL


@dataclass(frozen=True)
class Fonts:
    title: Font
    block: Font
    label: Font


def label_fonts() -> Fonts:
    """Pillow's built-in font for every label.

    No host carries a TrueType font this render could name, so every label has always been drawn in
    Pillow's built-in font; the image stays as it is.
    """
    font = ImageFont.load_default()
    return Fonts(title=font, block=font, label=font)


def edge_pt(x0: int, y0: int, edge: str) -> Point:
    """The midpoint of `edge` (LEFT, RIGHT, TOP or BOTTOM) of the cell whose corner is (x0, y0)."""
    h = CELL // 2
    return {
        "LEFT": (x0, y0 + h),
        "RIGHT": (x0 + CELL, y0 + h),
        "TOP": (x0 + h, y0),
        "BOTTOM": (x0 + h, y0 + CELL),
    }[edge]


def track_line(kind: str) -> tuple[str, str] | None:
    """The two cell edges a TRACK of `kind` joins (digicon_lib.TRACK_ENDS), or None for a kind it does not draw."""
    if kind not in digicon_lib.TRACK_ENDS:
        return None
    a, b = digicon_lib.cell_edges([kind])
    return a, b


def read_sections(src: Path) -> list[ET.Element]:
    """The SECTION elements of `src`'s TRACKPLAN; PanelError when the file, the plan or its sections are missing."""
    try:
        root = ET.parse(src).getroot()
    except (OSError, ET.ParseError) as exc:
        raise PanelError(f"{src}: cannot read the panel: {exc}") from exc
    tp = root.find("TRACKPLAN")
    if tp is None:
        raise PanelError(f"{src}: no TRACKPLAN element")
    sections = tp.findall("SECTION")
    if not sections:
        raise PanelError(f"{src}: TRACKPLAN has no SECTION")
    return sections


def cell_of(src: Path, s: ET.Element) -> Point:
    """A SECTION's X and Y; PanelError naming the section when either is missing or not a whole number."""
    x, y = s.get("X"), s.get("Y")
    try:
        return int(x or ""), int(y or "")
    except ValueError as exc:
        raise PanelError(f"{src}: SECTION X={x!r} Y={y!r} is not a grid cell") from exc


def grid_of(cells: Sequence[Point]) -> Grid:
    xs = [x for x, _ in cells]
    ys = [y for _, y in cells]
    return Grid(min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)


def draw_gridlines(d: ImageDraw.ImageDraw, g: Grid) -> None:
    for c in range(g.cols + 1):
        gx = PAD_X + c * CELL
        d.line([(gx, PAD_Y), (gx, PAD_Y + g.rows * CELL)], fill=GRIDLINE, width=1)
    for r in range(g.rows + 1):
        gy = PAD_Y + r * CELL
        d.line([(PAD_X, gy), (PAD_X + g.cols * CELL, gy)], fill=GRIDLINE, width=1)


def draw_section(d: ImageDraw.ImageDraw, s: ET.Element, x0: int, y0: int, fonts: Fonts, seen: set[str]) -> None:
    """One cell: a label cell's name, or its tracks, switch points and first sight of each block name.

    `seen` holds the block names already drawn; a name drawn here is added to it.
    """
    tg = s.find("TRACKGROUP")
    if tg is None:
        nm = s.find("SEC_NAME")
        name = nm.get("NAME") if nm is not None else None
        if name:
            d.text((x0 + 4, y0 + CELL // 2 - 8), name, font=fonts.label, fill=LABELTXT)
        return
    edges = s.findall("SEC_EDGE")
    is_plant = any(e.find("SWITCHPOINTS") is not None for e in edges)
    col = PLANT if is_plant else TRACK
    for t in tg.findall("TRACK"):
        ends = track_line((t.text or "").strip())
        if ends:
            d.line([edge_pt(x0, y0, ends[0]), edge_pt(x0, y0, ends[1])], fill=col, width=TRACK_W)
    for e in edges:
        if e.find("SWITCHPOINTS") is not None:
            px, py = edge_pt(x0, y0, e.get("EDGE") or "")
            d.ellipse([px - 5, py - 5, px + 5, py + 5], fill=POINTS)
    for e in edges:
        b = e.find("BLOCK")
        block = b.get("NAME") if b is not None else None
        if block and block not in seen:
            seen.add(block)
            d.text((x0 + 2, y0 + 2), block, font=fonts.block, fill=BLKTXT)


def draw_legend(d: ImageDraw.ImageDraw, height: int, font: Font) -> None:
    ly = height - PAD_Y // 2 + 6
    d.line([(PAD_X, ly + 8), (PAD_X + 30, ly + 8)], fill=TRACK, width=TRACK_W)
    d.text((PAD_X + 38, ly), "track", font=font, fill=LABELTXT)
    d.line([(PAD_X + 110, ly + 8), (PAD_X + 140, ly + 8)], fill=PLANT, width=TRACK_W)
    d.text((PAD_X + 148, ly), "turnout plant", font=font, fill=LABELTXT)
    d.ellipse([PAD_X + 270, ly + 3, PAD_X + 280, ly + 13], fill=POINTS)
    d.text((PAD_X + 288, ly), "switch points", font=font, fill=LABELTXT)
    d.text((PAD_X + 410, ly), "block / OS names in green", font=font, fill=BLKTXT)


def draw(src: Path, sections: Sequence[ET.Element]) -> Image.Image:
    """The image of `sections`, the TRACKPLAN of `src`; PanelError when a section has no grid cell."""
    cells = [cell_of(src, s) for s in sections]
    g = grid_of(cells)
    img = Image.new("RGB", g.size, BG)
    d = ImageDraw.Draw(img)
    fonts = label_fonts()
    draw_gridlines(d, g)
    d.text((PAD_X, 26), f"{src.name}   grid {g.cols}×{g.rows}  (min col={g.minx}, "
           f"row={g.miny})", font=fonts.title, fill=LABELTXT)
    seen: set[str] = set()
    for s, (x, y) in zip(sections, cells):
        draw_section(d, s, *g.origin(x, y), fonts, seen)
    draw_legend(d, g.size[1], fonts.block)
    return img


def render(src: Path, out: Path) -> None:
    """Draw `src` and save the PNG at `out`, creating its folder."""
    sections = read_sections(src)
    img = draw(src, sections)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    w, h = img.size
    print(f"wrote {out}  ({w}x{h})  sections={len(sections)}")


def main(argv: Sequence[str]) -> int:
    if len(argv) != 2:
        print("usage: render_cats_panel.py <panel.xml> <out.png>", file=sys.stderr)
        return 2
    try:
        render(Path(argv[0]), Path(argv[1]))
    except PanelError as exc:
        print(f"render_cats_panel: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
