"""Drawing and docx pieces shared by the station map renderers in this folder.

render_barn_station_map, render_south_yard_station_map and render_shenango_station_map draw
in one sheet language: capped track lines, frog dots, teal switch pills and Arial or Georgia
text, on an SM-series landscape docx whose embedded PNG is swapped for the new map.
"""

from __future__ import annotations

import sys
import zipfile
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree as ET

from PIL import ImageDraw, ImageFont

Point = tuple[float, float]
RGB = tuple[int, int, int]
Corner = Literal["ne", "nw", "w", "e"]

# The sheet: 8 in x 5 in at 200 dpi, and its colours.
DPI = 200
W = 8 * DPI
H = 5 * DPI
WHITE: RGB = (255, 255, 255)
TRACK: RGB = (20, 20, 20)
INK: RGB = (16, 20, 24)
BADGE: RGB = (15, 71, 97)  # the switch-pill teal of SM-02 to SM-05
BADGE_INK: RGB = (255, 255, 255)
COMPASS_GOLD: RGB = (201, 154, 40)

# Repo-relative: the hart-ops folder (present when the docx are written) and the SM-series
# landscape docx whose embedded map the renderers swap.
HOPS_REL = "ops/hart-ops"
SM_DOCX_TEMPLATE_REL = "docs/ops/Neville_Island_Station_Map_West_Yard.docx"

SANS_DIRS = (
    Path("/System/Library/Fonts/Supplemental"),
    Path("/Library/Fonts"),
    Path("/usr/share/fonts/truetype/macos"),
)
SERIF_DIRS = (
    Path("/System/Library/Fonts/Supplemental"),
    Path("/Library/Fonts"),
    Path("/usr/share/fonts/truetype/msttcorefonts"),
)


def find_font(names: Sequence[str], size: int, dirs: Sequence[Path]) -> ImageFont.FreeTypeFont | None:
    """The first of ``names`` found in ``dirs`` (names first, then folders), or None."""
    for name in names:
        for base in dirs:
            path = base / name
            if path.is_file():
                return ImageFont.truetype(str(path), size)
    return None


def _default_font(names: Sequence[str]) -> ImageFont.ImageFont:
    print(f"station map: none of {', '.join(names)} found; using the PIL default font", file=sys.stderr)
    return ImageFont.load_default()


def arial(size: int, bold: bool = False, black: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Arial at ``size``: Black, then Bold, when asked, then Regular; warns when none is installed."""
    names = (["Arial Black.ttf"] if black else []) + (["Arial Bold.ttf"] if bold else []) + ["Arial.ttf"]
    return find_font(names, size, SANS_DIRS) or _default_font(names)


def georgia(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Georgia at ``size``, else Arial of the same weight."""
    name = "Georgia Bold.ttf" if bold else "Georgia.ttf"
    return find_font([name], size, SERIF_DIRS) or arial(size, bold=bold)


def along(origin: Point, dy: float, run: float, rise: float) -> Point:
    """Move ``dy`` screen pixels (down positive) along the slope ``run / rise``."""
    return (origin[0] + (run / rise) * dy, origin[1] + dy)


def capped_line(d: ImageDraw.ImageDraw, a: Point, b: Point, width: int, fill: RGB) -> None:
    """A track line with round caps, so joins meet without gaps."""
    d.line([a, b], fill=fill, width=width)
    r = width / 2
    for x, y in (a, b):
        d.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def dot(d: ImageDraw.ImageDraw, pt: Point, r: float, fill: RGB) -> None:
    x, y = pt
    d.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def arrow(d: ImageDraw.ImageDraw, tip: Point, direction: Literal["left", "right"], size: float = 14,
          fill: RGB = TRACK) -> None:
    """A filled arrowhead with its point at ``tip``."""
    x, y = tip
    if direction == "left":
        pts = [(x, y), (x + size, y - size * 0.55), (x + size, y + size * 0.55)]
    else:
        pts = [(x, y), (x - size, y - size * 0.55), (x - size, y + size * 0.55)]
    d.polygon(pts, fill=fill)


def badge_near(
    d: ImageDraw.ImageDraw, pt: Point, text: str, font: ImageFont.ImageFont, corner: Corner = "ne", *,
    dot_r: float, gap: float, fill: RGB, ink: RGB,
) -> None:
    """A teal switch pill beside the frog dot at ``pt``, on the named corner."""
    box = d.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    w = tw + 22
    h = th + 16
    cx, cy = pt
    if corner == "ne":
        x = cx + dot_r + gap
        y = cy - dot_r - h - 2
    elif corner == "nw":
        x = cx - dot_r - w - gap
        y = cy - dot_r - h - 2
    elif corner == "w":
        x = cx - dot_r - w - gap
        y = cy - h / 2
    elif corner == "e":
        x = cx + dot_r + gap
        y = cy - h / 2
    else:
        raise ValueError(f"badge corner {corner!r}: expected ne, nw, w or e")
    d.rounded_rectangle([x, y, x + w, y + h], radius=8, fill=fill)
    d.text((x + w / 2, y + h / 2 - 1), text, font=font, fill=ink, anchor="mm")


CORE_NS = {
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
}


def patch_core_title(xml_bytes: bytes, title: str) -> bytes:
    """docProps/core.xml with its dc:title set to ``title``."""
    root = ET.fromstring(xml_bytes)
    el = root.find("dc:title", CORE_NS)
    if el is not None:
        el.text = title
    ET.register_namespace("cp", CORE_NS["cp"])
    ET.register_namespace("dc", CORE_NS["dc"])
    ET.register_namespace("dcterms", "http://purl.org/dc/terms/")
    ET.register_namespace("dcmitype", "http://purl.org/dc/dcmitype/")
    ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def write_sheet_docx(
    template: Path, png: Path, dest: Path, *,
    media_names: tuple[str, str] | None = None, title: str | None = None,
) -> None:
    """Copy an SM-series docx to ``dest`` with ``png`` as its map image.

    ``media_names`` (old, new) renames the image in word/document.xml; ``title`` sets the
    document title. Every other part is copied unchanged.
    """
    if not template.is_file():
        raise SystemExit(f"missing template {template}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    png_bytes = png.read_bytes()
    buf = BytesIO()
    with zipfile.ZipFile(template, "r") as src, zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "word/media/image1.png":
                data = png_bytes
            elif item.filename == "word/document.xml" and media_names:
                data = data.replace(media_names[0].encode(), media_names[1].encode())
            elif item.filename == "docProps/core.xml" and title is not None:
                data = patch_core_title(data, title)
            out.writestr(item, data)
    dest.write_bytes(buf.getvalue())
    print(f"wrote {dest}")
