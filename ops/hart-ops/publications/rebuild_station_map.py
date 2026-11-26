#!/usr/bin/env python3
"""Rebuild Neville Island Station Map (SM-01).

Draws a TT-23-styled subdivision schematic with two East End control points:
  Upper: East End → Brick → Plane → Barn
  Lower: Barn → East End (industry spurs) → Princess → McKeesport / McKees Rocks
Plane–Barn runaround; Scale on the South Yard lead (inside); vertical South Yard stub.

The station names, their spacing down the spine, the industry names and the publication
lines come from data/station_map_sm01.json; this module holds the geometry.

Usage (from ops/hart-ops):
  .venv/bin/python publications/rebuild_station_map.py

Writes:
  publications/assets/station_map_subdivision.png (and the _plain, _diagram_only and compass PNGs)
  docs/ops/Neville_Island_Station_Map.docx
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Literal, NamedTuple, TypedDict

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT.parents[1] / "docs/ops"
PUB = Path(__file__).resolve().parent
ASSETS = PUB / "assets"
DATA = PUB / "data" / "station_map_sm01.json"
sys.path.insert(0, str(PUB))

from hart_pub_helpers import (  # noqa: E402
    ACCENT,
    MUTED,
    _set_run_font,
    add_publication_footer,
    set_page_size,
)
from pub_fonts import ARIAL, ARIAL_BOLD, GEORGIA, GEORGIA_BOLD, font  # noqa: E402, F401
from station_compass import compass_rose, paste_compass  # noqa: E402

CANONICAL = DOCS / "Neville_Island_Station_Map.docx"
PNG_OUT = ASSETS / "station_map_subdivision.png"
PNG_PLAIN = ASSETS / "station_map_subdivision_plain.png"
PNG_DIAGRAM = ASSETS / "station_map_diagram_only.png"
PNG_COMPASS = ASSETS / "compass_rose_n_right.png"

RGB = tuple[int, int, int]
Point = tuple[float, float]

# TT-23 palette
BG: RGB = (255, 255, 255)
INK: RGB = (0x16, 0x16, 0x16)
RULE: RGB = (0x16, 0x16, 0x16)
ACCENT_RED: RGB = (0x5C, 0x16, 0x16)

SPINE_KEYS = ("east_upper", "brick", "plane", "barn", "east_lower", "princess", "interchange")
LABEL_KEYS = ("to_princess", "brick", "west_yard", "plane", "barn", "scale", "south_yard",
              "east_end", "princess", "shenango", "interchange")


class Publication(TypedDict):
    title: str
    pub_id: str
    revision: str
    effective: str


class MapText(TypedDict):
    """data/station_map_sm01.json."""

    publication: Publication
    masthead: dict[str, str]
    diagram_title: str
    footer_official: str
    spine_y: dict[str, float]
    labels: dict[str, str]
    industries: list[str]


class StationMapDataError(ValueError):
    """data/station_map_sm01.json is missing a key the drawing needs."""


def load_map_text(path: Path = DATA) -> MapText:
    """Read and check the SM-01 text and spine spacing."""
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("publication", "masthead", "diagram_title", "footer_official", "spine_y", "labels", "industries"):
        if key not in data:
            raise StationMapDataError(f"{path}: missing {key!r}")
    for group, keys in (("spine_y", SPINE_KEYS), ("labels", LABEL_KEYS), ("masthead", ("railroad", "division")),
                        ("publication", ("title", "pub_id", "revision", "effective"))):
        missing = [k for k in keys if k not in data[group]]
        if missing:
            raise StationMapDataError(f"{path}: {group} is missing {', '.join(missing)}")
    if not data["industries"]:
        raise StationMapDataError(f"{path}: industries is empty")
    return data


TEXT: MapText = load_map_text()
PUBLICATION: Publication = TEXT["publication"]


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return font(path, size)


def _compass_rose_n_right(size: int = 180) -> Image.Image:
    return compass_rose(size, "right")


def _paste_compass(base: Image.Image, *, cx: float, cy: float, size: int, north: str = "right") -> None:
    paste_compass(base, cx=cx, cy=cy, size=size, north=north)


def _line(draw: ImageDraw.ImageDraw, a: Point, b: Point, *, w: int = 3) -> None:
    draw.line([a, b], fill=INK, width=w)


def _dot(draw: ImageDraw.ImageDraw, xy: Point, *, r: int = 9) -> None:
    x, y = xy
    draw.ellipse([x - r, y - r, x + r, y + r], fill=INK, outline=INK)


def _label(
    draw: ImageDraw.ImageDraw,
    xy: Point,
    text: str,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    *,
    anchor: str = "lm",
) -> None:
    draw.text(xy, text, font=font, fill=INK, anchor=anchor)


def _arrow(
    draw: ImageDraw.ImageDraw,
    tip: Point,
    *,
    direction: Literal["up", "down", "left", "right"],
    size: int = 16,
) -> None:
    """Draw a filled arrowhead at tip."""
    x, y = tip
    if direction == "up":
        pts = [(x, y), (x - size * 0.55, y + size), (x + size * 0.55, y + size)]
    elif direction == "down":
        pts = [(x, y), (x - size * 0.55, y - size), (x + size * 0.55, y - size)]
    elif direction == "left":
        pts = [(x, y), (x + size, y - size * 0.55), (x + size, y + size * 0.55)]
    else:
        pts = [(x, y), (x - size, y - size * 0.55), (x - size, y + size * 0.55)]
    draw.polygon(pts, fill=INK)


class Frame(NamedTuple):
    """Page bands and the scale from design units (1400 x 2450) to pixels."""

    width: int
    margin_x: int
    header_bottom: int
    foot_y: int
    footer_top: int
    avail_h: int
    s: float  # x scale (and font scale)
    s_y: float  # y scale; the fill layout stretches the spine to the panel height
    fill: bool

    def u(self, v: float) -> float:
        return v * self.s

    def uy(self, v: float) -> float:
        return v * self.s_y


def _frame(width: int, height: int, *, include_title: bool, include_footer: bool, fill: bool) -> Frame:
    base_w, base_h = 1400, 2450
    margin_x = 36 if fill else 90
    header_bottom = 72 if (include_title and fill) else (110 if include_title else 28)
    foot_band = 160 if include_footer else 24
    foot_y = height - foot_band
    footer_top = foot_y - 8
    avail_w = width - 2 * margin_x
    avail_h = footer_top - header_bottom
    if fill:
        # Content footprint in design units, tight pads, from the interchange label to the To Princess arrow.
        base_geo_w = 120 + 170 + 240 + 130
        base_content_h = (1710 + 70) - (0 - 110)
        s = avail_w / base_geo_w
        s_y = avail_h / base_content_h
    else:
        s = min(width / base_w, height / base_h)
        s_y = s
    return Frame(width, margin_x, header_bottom, foot_y, footer_top, avail_h, s, s_y, fill)


class Fonts(NamedTuple):
    title: ImageFont.FreeTypeFont
    station: ImageFont.FreeTypeFont
    industry: ImageFont.FreeTypeFont
    footer: ImageFont.FreeTypeFont
    footer_bold: ImageFont.FreeTypeFont


def _fonts(f: Frame) -> Fonts:
    s = f.s
    return Fonts(
        title=_font(ARIAL_BOLD, 38 if f.fill else max(28, int(42 * s))),
        station=_font(GEORGIA, max(22, int(30 * s))),
        industry=_font(GEORGIA, max(18, int(24 * s))),
        footer=_font(GEORGIA, max(16, int(20 * s))),
        footer_bold=_font(GEORGIA_BOLD, max(16, int(20 * s))),
    )


class Spine(NamedTuple):
    """Pixel positions of the spine and the lines off it."""

    mx: float  # spine x
    run_dx: float
    slope_dy: float
    sy_x: float  # South Yard lead x
    lead_dy: float
    ind_x: float  # industry lead x
    y: dict[str, float]  # spine stations by SPINE_KEYS, page y


def _spine(f: Frame, spine_y: dict[str, float]) -> Spine:
    """Centre the spine across the page and its content down the drawable band."""
    run_dx = f.u(170)
    slope_dy = f.uy(95)
    ind_span = f.u(240)
    west_label_pad = f.u(120 if f.fill else 140)
    right_pad = f.u(130 if f.fill else 160)
    geo_w = run_dx + ind_span
    total_w = west_label_pad + geo_w + right_pad
    origin = (f.width - total_w) / 2
    mx = origin + west_label_pad + run_dx
    ind_x = mx + ind_span
    sy_x = (mx + ind_x) / 2
    lead_dy = (sy_x - mx) * slope_dy / run_dx

    y = {k: f.uy(spine_y[k]) for k in SPINE_KEYS}
    content_top = y["east_upper"] - f.uy(110)
    content_bottom = y["interchange"] + f.uy(70)
    y_shift = f.header_bottom + (f.avail_h - (content_bottom - content_top)) / 2 - content_top
    return Spine(mx, run_dx, slope_dy, sy_x, lead_dy, ind_x, {k: v + y_shift for k, v in y.items()})


def _draw_title(draw: ImageDraw.ImageDraw, f: Frame, fonts: Fonts) -> None:
    title_y = 12 if f.fill else int(f.header_bottom * 0.45)
    rule_y = (title_y + 44) if f.fill else (f.header_bottom - 15)
    draw.text((f.width // 2, title_y), TEXT["diagram_title"], font=fonts.title, fill=INK, anchor="mt")
    draw.line([(f.margin_x, rule_y), (f.width - f.margin_x, rule_y)], fill=RULE, width=max(4, int(5 * f.s)))


class Pen(NamedTuple):
    """The drawing context every step shares."""

    draw: ImageDraw.ImageDraw
    f: Frame
    fonts: Fonts
    lw: int
    dot_r: int
    label_dx: float

    def line(self, a: Point, b: Point) -> None:
        _line(self.draw, a, b, w=self.lw)

    def dot(self, p: Point) -> None:
        _dot(self.draw, p, r=self.dot_r)

    def label(self, p: Point, key: str, anchor: str) -> None:
        _label(self.draw, p, TEXT["labels"][key], self.fonts.station, anchor=anchor)


def _draw_spine(pen: Pen, sp: Spine) -> dict[str, Point]:
    """The spine top to bottom, its arrows and To Princess. Returns the spine points."""
    f, mx = pen.f, sp.mx
    pts = {k: (mx, sp.y[k]) for k in SPINE_KEYS}
    for a, b in zip(SPINE_KEYS, SPINE_KEYS[1:]):
        pen.line(pts[a], pts[b])
    _arrow(pen.draw, pts["interchange"], direction="down", size=max(14, int(18 * f.s)))

    # Upper East End junction: no label or dot, only the industry lead and To Princess.
    east_u = pts["east_upper"]
    princess_arrow = (mx, sp.y["east_upper"] - f.uy(110))
    pen.line(east_u, princess_arrow)
    _arrow(pen.draw, princess_arrow, direction="up", size=max(12, int(16 * f.s)))
    pen.label((princess_arrow[0] + f.u(18), (east_u[1] + princess_arrow[1]) / 2), "to_princess", "lm")

    brick = pts["brick"]
    west = (mx - sp.run_dx, sp.y["brick"] + sp.slope_dy)
    pen.line(brick, west)
    pen.dot(brick)
    pen.dot(west)
    pen.label((brick[0] + pen.label_dx, brick[1]), "brick", "lm")
    pen.label((west[0], brick[1]), "west_yard", "mm")
    return pts


def _draw_yard_and_industry_lead(pen: Pen, sp: Spine, pts: dict[str, Point]) -> Point:
    """Plane–Barn runaround with Scale and South Yard, and the industry lead. Returns the spur tip."""
    f = pen.f
    plane, barn, east_u = pts["plane"], pts["barn"], pts["east_upper"]
    plane_e = (sp.sy_x, sp.y["plane"] + sp.lead_dy)
    barn_e = (sp.sy_x, sp.y["barn"] + sp.lead_dy)
    scale_pt = (sp.sy_x, (plane_e[1] + barn_e[1]) / 2)
    south = (sp.sy_x, barn_e[1] + f.uy(150))

    ind_dy = (sp.ind_x - sp.mx) * sp.slope_dy / sp.run_dx
    ind_top = (sp.ind_x, sp.y["east_upper"] + ind_dy)
    spur_tip = (sp.ind_x, sp.y["east_lower"] - ind_dy)

    for a, b in ((plane, plane_e), (plane_e, barn_e), (barn, barn_e), (barn_e, south), (east_u, ind_top),
                 (ind_top, spur_tip)):
        pen.line(a, b)
    for p in (ind_top, spur_tip, plane, barn, plane_e, barn_e, scale_pt, south):
        pen.dot(p)
    pen.label((plane[0] - pen.label_dx, plane[1]), "plane", "rm")
    pen.label((barn[0] - pen.label_dx, barn[1]), "barn", "rm")
    pen.label((sp.mx - pen.label_dx, (sp.y["plane"] + sp.y["barn"]) / 2), "scale", "rm")
    pen.label((south[0], south[1] + f.u(28)), "south_yard", "mt")
    return spur_tip


def _draw_industries(pen: Pen, pts: dict[str, Point], spur_tip: Point) -> None:
    """East End and the industry spur: one dot per industry, the last at the spur tip."""
    f = pen.f
    east_l = pts["east_lower"]
    pen.dot(east_l)
    pen.label((east_l[0] - pen.label_dx, east_l[1]), "east_end", "rm")
    pen.line(east_l, spur_tip)

    names = TEXT["industries"]
    dots: list[Point] = []
    for i in range(1, len(names)):
        t = i / float(len(names))
        p = (east_l[0] + (spur_tip[0] - east_l[0]) * t, east_l[1] + (spur_tip[1] - east_l[1]) * t)
        dots.append(p)
        pen.dot(p)
    dots.append(spur_tip)

    ind_cx = sum(p[0] for p in dots) / len(dots)
    names_top = east_l[1] + f.uy(20)
    name_gap = f.uy(28)
    for i, name in enumerate(names):
        _label(pen.draw, (ind_cx, names_top + i * name_gap), name, pen.fonts.industry, anchor="mt")


def _draw_south_end(pen: Pen, sp: Spine, pts: dict[str, Point]) -> None:
    """Princess, the Shenango branch and the interchange label."""
    f = pen.f
    princess, ix = pts["princess"], pts["interchange"]
    pen.dot(princess)
    pen.label((princess[0] - pen.label_dx, princess[1]), "princess", "rm")
    shenango = (sp.mx + sp.run_dx, sp.y["princess"] + sp.slope_dy)
    pen.line(princess, shenango)
    pen.dot(shenango)
    pen.label((shenango[0], shenango[1] + f.u(28)), "shenango", "mt")
    pen.label((ix[0], ix[1] + f.uy(36)), "interchange", "mt")


def _draw_compass(img: Image.Image, f: Frame, sp: Spine) -> None:
    """The rose (North right) left of the spine between Barn and East End, kept inside the bands."""
    rose_size = max(110, int(round(f.u(155))))
    compass_cx = sp.mx - f.u(200)
    compass_cy = (sp.y["barn"] + sp.y["east_lower"]) * 0.5
    compass_cx = max(f.margin_x + rose_size * 0.52, min(compass_cx, sp.mx - rose_size * 0.55))
    compass_cy = max(f.header_bottom + rose_size * 0.55, min(compass_cy, f.footer_top - rose_size * 0.55))
    _paste_compass(img, cx=compass_cx, cy=compass_cy, size=rose_size)


def _draw_footer(draw: ImageDraw.ImageDraw, f: Frame, fonts: Fonts) -> None:
    draw.line([(f.margin_x, f.foot_y), (f.width - f.margin_x, f.foot_y)], fill=RULE, width=max(4, int(5 * f.s)))
    cy = f.foot_y + 28
    draw.text(
        (f.width // 2, cy),
        f"Publication {PUBLICATION['pub_id']}  ·  Revision {PUBLICATION['revision']}",
        font=fonts.footer,
        fill=INK,
        anchor="mt",
    )
    draw.text((f.width // 2, cy + 32), TEXT["footer_official"], font=fonts.footer_bold, fill=INK, anchor="mt")


def draw_subdivision_map(
    *,
    width: int = 1400,
    height: int = 2450,
    include_title: bool = True,
    include_footer: bool = True,
    fill: bool = False,
    bg: RGB = BG,
) -> Image.Image:
    """Portrait subdivision schematic in TT-23 visual language.

    When fill=True, geometry and fonts scale to use the drawable area (for the TT-23 panel).
    """
    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)
    f = _frame(width, height, include_title=include_title, include_footer=include_footer, fill=fill)
    fonts = _fonts(f)
    pen = Pen(draw, f, fonts, lw=max(3, int(round(3 * f.s))), dot_r=max(7, int(round(9 * f.s))), label_dx=f.u(28))

    if include_title:
        _draw_title(draw, f, fonts)
    sp = _spine(f, TEXT["spine_y"])
    pts = _draw_spine(pen, sp)
    spur_tip = _draw_yard_and_industry_lead(pen, sp, pts)
    _draw_industries(pen, pts, spur_tip)
    _draw_south_end(pen, sp, pts)
    _draw_compass(img, f, sp)
    if include_footer:
        _draw_footer(draw, f, fonts)
    return img


def rebuild_png(out: Path = PNG_OUT) -> Path:
    """Write the SM-01 PNG, its white-ground and diagram-only variants and the compass asset."""
    out.parent.mkdir(parents=True, exist_ok=True)
    draw_subdivision_map().save(out, "PNG")
    draw_subdivision_map(bg=(255, 255, 255)).save(PNG_PLAIN, "PNG")
    # Diagram only, without the title and footer, for desk embeds.
    draw_subdivision_map(
        width=1000, height=2400, include_title=False, include_footer=False, fill=True, bg=(255, 255, 255)
    ).save(PNG_DIAGRAM, "PNG")
    rose = _compass_rose_n_right(220)
    rose_rgb = Image.new("RGB", rose.size, BG)
    rose_rgb.paste(rose, (0, 0), rose)
    rose_rgb.save(PNG_COMPASS)
    return out


def _centered(doc: Document, text: str, *, before: float, after: float, size_pt: float, color: RGBColor,
              name: str, bold: bool = False) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    _set_run_font(p.add_run(text), size_pt=size_pt, bold=bold, color=color, name=name)


def rebuild_docx(png: Path = PNG_OUT, out: Path = CANONICAL) -> Path:
    """Write the letter-size SM-01 sheet: masthead, title and the map."""
    doc = Document()
    set_page_size(doc, width_in=8.5, height_in=11.0, margin_in=0.55, bottom_margin_in=0.65)
    add_publication_footer(
        doc,
        pub_id=PUBLICATION["pub_id"],
        revision=PUBLICATION["revision"],
        effective=PUBLICATION["effective"],
        compact=False,
    )
    _centered(doc, TEXT["masthead"]["railroad"], before=0, after=2, size_pt=14, bold=True, color=ACCENT, name="Arial")
    _centered(doc, TEXT["masthead"]["division"], before=0, after=2, size_pt=10, color=MUTED, name="Georgia")
    _centered(doc, PUBLICATION["title"], before=6, after=10, size_pt=18, bold=True, color=ACCENT, name="Georgia")

    pic = doc.add_paragraph()
    pic.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pic.paragraph_format.space_before = Pt(0)
    pic.paragraph_format.space_after = Pt(0)
    pic.add_run().add_picture(str(png), height=Inches(8.6))  # fits the letter page under masthead and footer

    doc.save(out)
    return out


def main() -> None:
    png = rebuild_png()
    docx = rebuild_docx(png)
    print(f"Wrote {png}")
    print(f"Wrote {docx} ({PUBLICATION['pub_id']} Rev {PUBLICATION['revision']})")


if __name__ == "__main__":
    main()
