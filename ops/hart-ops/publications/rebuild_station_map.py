#!/usr/bin/env python3
"""Rebuild Neville Island Station Map (SM-01).

Draws a TT-23-styled subdivision schematic with two East End control points:
  Upper: East End → Brick → Plane → Barn
  Lower: Barn → East End (industry spurs) → Princess → McKeesport / McKees Rocks
Plane–Barn runaround; Scale on the South Yard lead (inside); vertical South Yard stub.

Usage (from repo root):
  .venv/bin/python publications/rebuild_station_map.py

Writes:
  publications/assets/station_map_subdivision.png
  docs/Neville_Island_Station_Map.docx
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont

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
    set_page_size,
)

CANONICAL = DOCS / "Neville_Island_Station_Map.docx"
PNG_OUT = ASSETS / "station_map_subdivision.png"
PNG_PLAIN = ASSETS / "station_map_subdivision_plain.png"
PNG_DIAGRAM = ASSETS / "station_map_diagram_only.png"

PUBLICATION = {
    "title": "Station Map",
    "pub_id": "SM-01",
    "revision": "A",
    "effective": "21 July 2026",
}

# TT-23 palette
BG = (255, 255, 255)
INK = (0x16, 0x16, 0x16)
RULE = (0x16, 0x16, 0x16)
ACCENT_RED = (0x5C, 0x16, 0x16)

# Compass (linear5_panel_bg style)
COMPASS_RING = (0x2A, 0x3A, 0x55)
COMPASS_FILL = (0xFF, 0xFF, 0xFF)
COMPASS_GOLD_L = (0xD4, 0xA8, 0x2E)
COMPASS_GOLD_D = (0x9A, 0x72, 0x18)
COMPASS_BLUE_L = (0x9A, 0xA8, 0xB8)
COMPASS_BLUE_D = (0x3A, 0x4E, 0x68)

GEORGIA = "/System/Library/Fonts/Supplemental/Georgia.ttf"
GEORGIA_BOLD = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"
ARIAL_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
ARIAL = "/System/Library/Fonts/Supplemental/Arial.ttf"


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _compass_rose_n_right(size: int = 180) -> Image.Image:
    """Compass rose in the linear5 panel style with North (gold) pointing right."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = size / 2
    # Room for N/E/S/W labels outside the ring
    r = size * 0.32
    ring_w = max(2, int(size * 0.018))
    font = _font(ARIAL_BOLD, max(11, int(size * 0.13)))

    # Face
    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        fill=COMPASS_FILL,
        outline=COMPASS_RING,
        width=ring_w,
    )
    # Inner guide ring
    r_in = r * 0.82
    draw.ellipse(
        [cx - r_in, cy - r_in, cx + r_in, cy + r_in],
        outline=COMPASS_RING,
        width=max(1, ring_w // 2),
    )
    # 45° tick marks
    for ang in (45, 135, 225, 315):
        rad = math.radians(ang)
        x0 = cx + math.cos(rad) * r_in
        y0 = cy + math.sin(rad) * r_in
        x1 = cx + math.cos(rad) * r * 0.95
        y1 = cy + math.sin(rad) * r * 0.95
        draw.line([(x0, y0), (x1, y1)], fill=COMPASS_RING, width=max(1, ring_w // 2))

    # Crosshair (E–W is vertical when N is right)
    draw.line([(cx, cy - r * 0.72), (cx, cy + r * 0.72)], fill=COMPASS_RING, width=max(1, ring_w // 2))
    draw.line([(cx - r * 0.72), (cy), (cx + r * 0.72), (cy)], fill=COMPASS_RING, width=max(1, ring_w // 2))

    tip = r * 0.78
    half = r * 0.16

    # North needle → right (gold, split top/bottom like linear5's left/right split)
    n_tip = (cx + tip, cy)
    draw.polygon(
        [(n_tip[0], n_tip[1]), (cx, cy - half), (cx, cy)],
        fill=COMPASS_GOLD_L,
    )
    draw.polygon(
        [(n_tip[0], n_tip[1]), (cx, cy + half), (cx, cy)],
        fill=COMPASS_GOLD_D,
    )
    # South needle → left (blue-gray)
    s_tip = (cx - tip, cy)
    draw.polygon(
        [(s_tip[0], s_tip[1]), (cx, cy - half), (cx, cy)],
        fill=COMPASS_BLUE_L,
    )
    draw.polygon(
        [(s_tip[0], s_tip[1]), (cx, cy + half), (cx, cy)],
        fill=COMPASS_BLUE_D,
    )
    # Center pivot
    pr = max(2, int(size * 0.025))
    draw.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], fill=COMPASS_RING)

    # Cardinal labels (N right, E down, S left, W up) — upright for this orientation
    label_r = r + size * 0.12
    draw.text((cx + label_r, cy), "N", font=font, fill=COMPASS_RING, anchor="mm")
    draw.text((cx, cy + label_r), "E", font=font, fill=COMPASS_RING, anchor="mm")
    draw.text((cx - label_r, cy), "S", font=font, fill=COMPASS_RING, anchor="mm")
    draw.text((cx, cy - label_r), "W", font=font, fill=COMPASS_RING, anchor="mm")
    return img


def _compass_rose_n_up(size: int = 180) -> Image.Image:
    """Same linear5 rose style with North (gold) pointing up; letters upright."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = size / 2
    r = size * 0.32
    ring_w = max(2, int(size * 0.018))
    font = _font(ARIAL_BOLD, max(11, int(size * 0.13)))

    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        fill=COMPASS_FILL,
        outline=COMPASS_RING,
        width=ring_w,
    )
    r_in = r * 0.82
    draw.ellipse(
        [cx - r_in, cy - r_in, cx + r_in, cy + r_in],
        outline=COMPASS_RING,
        width=max(1, ring_w // 2),
    )
    for ang in (45, 135, 225, 315):
        rad = math.radians(ang)
        x0 = cx + math.cos(rad) * r_in
        y0 = cy + math.sin(rad) * r_in
        x1 = cx + math.cos(rad) * r * 0.95
        y1 = cy + math.sin(rad) * r * 0.95
        draw.line([(x0, y0), (x1, y1)], fill=COMPASS_RING, width=max(1, ring_w // 2))

    draw.line([(cx, cy - r * 0.72), (cx, cy + r * 0.72)], fill=COMPASS_RING, width=max(1, ring_w // 2))
    draw.line([(cx - r * 0.72), (cy), (cx + r * 0.72), (cy)], fill=COMPASS_RING, width=max(1, ring_w // 2))

    tip = r * 0.78
    half = r * 0.16

    # North needle → up (gold, split left/right)
    n_tip = (cx, cy - tip)
    draw.polygon(
        [(n_tip[0], n_tip[1]), (cx - half, cy), (cx, cy)],
        fill=COMPASS_GOLD_L,
    )
    draw.polygon(
        [(n_tip[0], n_tip[1]), (cx + half, cy), (cx, cy)],
        fill=COMPASS_GOLD_D,
    )
    # South needle → down (blue-gray)
    s_tip = (cx, cy + tip)
    draw.polygon(
        [(s_tip[0], s_tip[1]), (cx - half, cy), (cx, cy)],
        fill=COMPASS_BLUE_L,
    )
    draw.polygon(
        [(s_tip[0], s_tip[1]), (cx + half, cy), (cx, cy)],
        fill=COMPASS_BLUE_D,
    )
    pr = max(2, int(size * 0.025))
    draw.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], fill=COMPASS_RING)

    label_r = r + size * 0.12
    draw.text((cx, cy - label_r), "N", font=font, fill=COMPASS_RING, anchor="mm")
    draw.text((cx + label_r, cy), "E", font=font, fill=COMPASS_RING, anchor="mm")
    draw.text((cx, cy + label_r), "S", font=font, fill=COMPASS_RING, anchor="mm")
    draw.text((cx - label_r, cy), "W", font=font, fill=COMPASS_RING, anchor="mm")
    return img


def _compass_rose_n_down(size: int = 180) -> Image.Image:
    """N-up rose with cardinals flipped (for a 180°-rotated track plan)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = size / 2
    r = size * 0.32
    ring_w = max(2, int(size * 0.018))
    font = _font(ARIAL_BOLD, max(11, int(size * 0.13)))

    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        fill=COMPASS_FILL,
        outline=COMPASS_RING,
        width=ring_w,
    )
    r_in = r * 0.82
    draw.ellipse(
        [cx - r_in, cy - r_in, cx + r_in, cy + r_in],
        outline=COMPASS_RING,
        width=max(1, ring_w // 2),
    )
    for ang in (45, 135, 225, 315):
        rad = math.radians(ang)
        x0 = cx + math.cos(rad) * r_in
        y0 = cy + math.sin(rad) * r_in
        x1 = cx + math.cos(rad) * r * 0.95
        y1 = cy + math.sin(rad) * r * 0.95
        draw.line([(x0, y0), (x1, y1)], fill=COMPASS_RING, width=max(1, ring_w // 2))

    draw.line([(cx, cy - r * 0.72), (cx, cy + r * 0.72)], fill=COMPASS_RING, width=max(1, ring_w // 2))
    draw.line([(cx - r * 0.72), (cy), (cx + r * 0.72), (cy)], fill=COMPASS_RING, width=max(1, ring_w // 2))

    tip = r * 0.78
    half = r * 0.16

    # North needle → down (gold); South → up (blue)
    n_tip = (cx, cy + tip)
    draw.polygon(
        [(n_tip[0], n_tip[1]), (cx - half, cy), (cx, cy)],
        fill=COMPASS_GOLD_L,
    )
    draw.polygon(
        [(n_tip[0], n_tip[1]), (cx + half, cy), (cx, cy)],
        fill=COMPASS_GOLD_D,
    )
    s_tip = (cx, cy - tip)
    draw.polygon(
        [(s_tip[0], s_tip[1]), (cx - half, cy), (cx, cy)],
        fill=COMPASS_BLUE_L,
    )
    draw.polygon(
        [(s_tip[0], s_tip[1]), (cx + half, cy), (cx, cy)],
        fill=COMPASS_BLUE_D,
    )
    pr = max(2, int(size * 0.025))
    draw.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], fill=COMPASS_RING)

    label_r = r + size * 0.12
    draw.text((cx, cy + label_r), "N", font=font, fill=COMPASS_RING, anchor="mm")
    draw.text((cx - label_r, cy), "E", font=font, fill=COMPASS_RING, anchor="mm")
    draw.text((cx, cy - label_r), "S", font=font, fill=COMPASS_RING, anchor="mm")
    draw.text((cx + label_r, cy), "W", font=font, fill=COMPASS_RING, anchor="mm")
    return img


def _paste_compass(
    base: Image.Image,
    *,
    cx: float,
    cy: float,
    size: int,
    north: str = "right",
) -> None:
    """Paste the linear5-style rose. north='right'|'up'|'down'."""
    if north == "up":
        rose = _compass_rose_n_up(size)
    elif north == "down":
        rose = _compass_rose_n_down(size)
    else:
        rose = _compass_rose_n_right(size)
    x = int(cx - size / 2)
    y = int(cy - size / 2)
    base.paste(rose, (x, y), rose)


def _line(draw: ImageDraw.ImageDraw, a: tuple[float, float], b: tuple[float, float], *, w: int = 3) -> None:
    draw.line([a, b], fill=INK, width=w)


def _dot(draw: ImageDraw.ImageDraw, xy: tuple[float, float], *, r: int = 9) -> None:
    x, y = xy
    draw.ellipse([x - r, y - r, x + r, y + r], fill=INK, outline=INK)


def _label(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.ImageFont,
    *,
    anchor: str = "lm",
) -> None:
    draw.text(xy, text, font=font, fill=INK, anchor=anchor)


def _arrow(
    draw: ImageDraw.ImageDraw,
    tip: tuple[float, float],
    *,
    direction: str,
    size: int = 16,
) -> None:
    """Draw a filled arrowhead at tip. direction: up|down|left|right."""
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


def draw_subdivision_map(
    *,
    width: int = 1400,
    height: int = 2450,
    include_title: bool = True,
    include_footer: bool = True,
    fill: bool = False,
    bg: tuple[int, int, int] = BG,
) -> Image.Image:
    """Portrait subdivision schematic in TT-23 visual language.

    When fill=True, geometry/fonts scale to use the drawable area (for TT-23 panel).
    Pass bg=(255,255,255) for desk-sheet embeds without the cream timetable ground.
    """
    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)

    # Base design units (at 1400×2450). Scale up when filling a tall/narrow panel.
    base_w, base_h = 1400, 2450
    margin_x = 36 if fill else 90
    header_bottom = 72 if (include_title and fill) else (110 if include_title else 28)
    foot_band = 160 if include_footer else 24
    foot_y = height - foot_band
    footer_top = foot_y - 8
    avail_w = width - 2 * margin_x
    avail_h = footer_top - header_bottom

    if fill:
        # Design content footprint in base units (tighter pads → larger drawing)
        base_geo_w = 120 + 170 + 240 + 130
        base_content_h = (1710 + 70) - (0 - 110)  # ix label → To Princess arrow
        sx = avail_w / base_geo_w
        sy = avail_h / base_content_h
        s = sx
        s_y = sy  # stretch spine to use full panel height
    else:
        s = min(width / base_w, height / base_h)
        s_y = s

    def u(v: float) -> float:
        return v * s

    def uy(v: float) -> float:
        return v * s_y

    title_font = _font(ARIAL_BOLD, 38 if fill else max(28, int(42 * s)))
    station_font = _font(GEORGIA, max(22, int(30 * s)))
    industry_font = _font(GEORGIA, max(18, int(24 * s)))
    footer_font = _font(GEORGIA, max(16, int(20 * s)))
    footer_bold = _font(GEORGIA_BOLD, max(16, int(20 * s)))
    lw = max(3, int(round(3 * s)))
    dot_r = max(7, int(round(9 * s)))
    label_dx = u(28)

    if include_title:
        title_y = 12 if fill else int(header_bottom * 0.45)
        # Rule sits just under the title (fill: tight; SM-01: standard gap)
        rule_y = (title_y + 44) if fill else (header_bottom - 15)
        draw.text(
            (width // 2, title_y),
            "SUBDIVISION DIAGRAM",
            font=title_font,
            fill=INK,
            anchor="mt",
        )
        draw.line(
            [(margin_x, rule_y), (width - margin_x, rule_y)],
            fill=RULE,
            width=max(4, int(5 * s)),
        )

    # Spine geometry — horizontally centered, scaled
    run_dx = u(170)
    slope_dy = uy(95)
    ind_span = u(240)
    west_label_pad = u(120 if fill else 140)
    right_pad = u(130 if fill else 160)
    geo_w = run_dx + ind_span
    total_w = west_label_pad + geo_w + right_pad
    origin = (width - total_w) / 2
    mx = origin + west_label_pad + run_dx
    ind_x = mx + ind_span
    sy_x = (mx + ind_x) / 2
    lead_dx = sy_x - mx
    lead_dy = lead_dx * slope_dy / run_dx

    y_east_u = 0.0
    y_brick = uy(200)
    y_plane = uy(380)
    y_barn = uy(720)
    y_east_l = uy(1240)
    y_princess = uy(1510)
    y_ix = uy(1710)
    content_top = y_east_u - uy(110)
    content_bottom = y_ix + uy(70)
    content_h = content_bottom - content_top
    y_shift = header_bottom + (avail_h - content_h) / 2 - content_top

    y_east_u += y_shift
    y_brick += y_shift
    y_plane += y_shift
    y_barn += y_shift
    y_east_l += y_shift
    y_princess += y_shift
    y_ix += y_shift

    east_u = (mx, y_east_u)
    brick = (mx, y_brick)
    plane = (mx, y_plane)
    barn = (mx, y_barn)
    east_l = (mx, y_east_l)
    princess = (mx, y_princess)
    ix = (mx, y_ix)

    _line(draw, east_u, brick, w=lw)
    _line(draw, brick, plane, w=lw)
    _line(draw, plane, barn, w=lw)
    _line(draw, barn, east_l, w=lw)
    _line(draw, east_l, princess, w=lw)
    _line(draw, princess, ix, w=lw)
    _arrow(draw, ix, direction="down", size=max(14, int(18 * s)))

    # Upper East End junction (no label/spot — industry lead + To Princess only)
    princess_arrow = (mx, y_east_u - uy(110))
    _line(draw, east_u, princess_arrow, w=lw)
    _arrow(draw, princess_arrow, direction="up", size=max(12, int(16 * s)))
    _label(
        draw,
        (princess_arrow[0] + u(18), (east_u[1] + princess_arrow[1]) / 2),
        "To Princess",
        station_font,
        anchor="lm",
    )

    west = (mx - run_dx, y_brick + slope_dy)
    _line(draw, brick, west, w=lw)
    _dot(draw, brick, r=dot_r)
    _dot(draw, west, r=dot_r)
    _label(draw, (brick[0] + label_dx, brick[1]), "Brick", station_font, anchor="lm")
    _label(draw, (west[0], brick[1]), "West Yard", station_font, anchor="mm")

    plane_e = (sy_x, y_plane + lead_dy)
    barn_e = (sy_x, y_barn + lead_dy)
    y_scale = (plane_e[1] + barn_e[1]) / 2
    scale_pt = (sy_x, y_scale)
    south = (sy_x, barn_e[1] + uy(150))

    ind_dx = ind_x - mx
    ind_dy = ind_dx * slope_dy / run_dx
    ind_top = (ind_x, y_east_u + ind_dy)
    spur_tip = (ind_x, y_east_l - ind_dy)

    _line(draw, plane, plane_e, w=lw)
    _line(draw, plane_e, barn_e, w=lw)
    _line(draw, barn, barn_e, w=lw)
    _line(draw, barn_e, south, w=lw)
    _line(draw, east_u, ind_top, w=lw)
    _line(draw, ind_top, spur_tip, w=lw)
    _dot(draw, ind_top, r=dot_r)
    _dot(draw, spur_tip, r=dot_r)

    _dot(draw, plane, r=dot_r)
    _dot(draw, barn, r=dot_r)
    _dot(draw, plane_e, r=dot_r)
    _dot(draw, barn_e, r=dot_r)
    _dot(draw, scale_pt, r=dot_r)
    _dot(draw, south, r=dot_r)
    _label(draw, (plane[0] - label_dx, plane[1]), "Plane", station_font, anchor="rm")
    _label(draw, (barn[0] - label_dx, barn[1]), "Barn", station_font, anchor="rm")
    _label(draw, (mx - label_dx, (y_plane + y_barn) / 2), "Scale", station_font, anchor="rm")
    _label(draw, (south[0], south[1] + u(28)), "South Yard", station_font, anchor="mt")

    _dot(draw, east_l, r=dot_r)
    _label(draw, (east_l[0] - label_dx, east_l[1]), "East End", station_font, anchor="rm")
    _line(draw, east_l, spur_tip, w=lw)

    industry_names = [
        "Aristech",
        "A. Stucki Co. / Ferrellgas",
        "Kosmos Cement",
        "Calgon Carbon",
    ]
    industry_dots = []
    for i in range(1, 4):
        t = i / 4.0
        p = (
            east_l[0] + (spur_tip[0] - east_l[0]) * t,
            east_l[1] + (spur_tip[1] - east_l[1]) * t,
        )
        industry_dots.append(p)
        _dot(draw, p, r=dot_r)
    industry_dots.append(spur_tip)

    ind_cx = sum(p[0] for p in industry_dots) / len(industry_dots)
    names_top = east_l[1] + uy(20)
    name_gap = uy(28)
    for i, name in enumerate(industry_names):
        _label(draw, (ind_cx, names_top + i * name_gap), name, industry_font, anchor="mt")

    _dot(draw, princess, r=dot_r)
    _label(draw, (princess[0] - label_dx, princess[1]), "Princess", station_font, anchor="rm")

    shenango = (mx + run_dx, y_princess + slope_dy)
    _line(draw, princess, shenango, w=lw)
    _dot(draw, shenango, r=dot_r)
    _label(draw, (shenango[0], shenango[1] + u(28)), "Shenango", station_font, anchor="mt")

    _label(draw, (ix[0], ix[1] + uy(36)), "McKeesport / McKees Rocks", station_font, anchor="mt")

    # Compass rose (linear5 style; North / gold needle points right)
    rose_size = max(110, int(round(u(155))))
    compass_cx = mx - u(200)
    compass_cy = (y_barn + y_east_l) * 0.5
    compass_cx = max(margin_x + rose_size * 0.52, min(compass_cx, mx - rose_size * 0.55))
    compass_cy = max(
        header_bottom + rose_size * 0.55,
        min(compass_cy, footer_top - rose_size * 0.55),
    )
    _paste_compass(img, cx=compass_cx, cy=compass_cy, size=rose_size)

    if include_footer:
        draw.line([(margin_x, foot_y), (width - margin_x, foot_y)], fill=RULE, width=max(4, int(5 * s)))
        cy = foot_y + 28
        draw.text(
            (width // 2, cy),
            f"Publication {PUBLICATION['pub_id']}  ·  Revision {PUBLICATION['revision']}",
            font=footer_font,
            fill=INK,
            anchor="mt",
        )
        draw.text(
            (width // 2, cy + 32),
            "Official Publication",
            font=footer_bold,
            fill=INK,
            anchor="mt",
        )

    return img


def rebuild_png(out: Path = PNG_OUT) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    img = draw_subdivision_map()
    img.save(out, "PNG")
    # White ground for crew / desk sheets (no cream TT-23 field)
    plain = draw_subdivision_map(bg=(255, 255, 255))
    plain.save(PNG_PLAIN, "PNG")
    # Diagram only — no SUBDIVISION DIAGRAM chrome / pub footer (desk embeds)
    diagram = draw_subdivision_map(
        width=1000,
        height=2400,
        include_title=False,
        include_footer=False,
        fill=True,
        bg=(255, 255, 255),
    )
    diagram.save(PNG_DIAGRAM, "PNG")
    # Standalone rose asset (N → right) matching linear5 style
    rose = _compass_rose_n_right(220)
    rose_rgb = Image.new("RGB", rose.size, BG)
    rose_rgb.paste(rose, (0, 0), rose)
    rose_rgb.save(ASSETS / "compass_rose_n_right.png")
    return out


def rebuild_docx(png: Path = PNG_OUT, out: Path = CANONICAL) -> Path:
    doc = Document()
    set_page_size(doc, width_in=8.5, height_in=11.0, margin_in=0.55, bottom_margin_in=0.65)
    add_publication_footer(
        doc,
        pub_id=PUBLICATION["pub_id"],
        revision=PUBLICATION["revision"],
        effective=PUBLICATION["effective"],
        compact=False,
    )

    # Masthead in TT-23 / HART spirit
    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    t.paragraph_format.space_before = Pt(0)
    t.paragraph_format.space_after = Pt(2)
    r = t.add_run("HART RAILROAD")
    _set_run_font(r, size_pt=14, bold=True, color=ACCENT, name="Arial")

    s = doc.add_paragraph()
    s.alignment = WD_ALIGN_PARAGRAPH.CENTER
    s.paragraph_format.space_before = Pt(0)
    s.paragraph_format.space_after = Pt(2)
    r = s.add_run("Pittsburgh & Chartiers Valley Division  ·  Neville Island Operations")
    _set_run_font(r, size_pt=10, color=MUTED, name="Georgia")

    h = doc.add_paragraph()
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    h.paragraph_format.space_before = Pt(6)
    h.paragraph_format.space_after = Pt(10)
    r = h.add_run(PUBLICATION["title"])
    _set_run_font(r, size_pt=18, bold=True, color=ACCENT, name="Georgia")

    pic = doc.add_paragraph()
    pic.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pic.paragraph_format.space_before = Pt(0)
    pic.paragraph_format.space_after = Pt(0)
    # Fit on letter page under masthead/footer
    pic.add_run().add_picture(str(png), height=Inches(8.6))

    doc.save(out)
    return out


def main() -> None:
    png = rebuild_png()
    docx = rebuild_docx(png)
    print(f"Wrote {png}")
    print(f"Wrote {docx} ({PUBLICATION['pub_id']} Rev {PUBLICATION['revision']})")


if __name__ == "__main__":
    main()
