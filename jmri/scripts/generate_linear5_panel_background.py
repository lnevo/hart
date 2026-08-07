#!/usr/bin/env python3
"""
Generate linear5 panel background: light-blue JPEG with a simple compass rose (N up).

The image matches LayoutEditor RGB (186, 210, 235) with the rose composited on top.

Output: jmri/layouts/linear5/assets/linear5_panel_bg.jpg
Install for JMRI: preference:/linear5_panel_bg.jpg
"""
from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

JMRI_ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = JMRI_ROOT / "layouts/linear5/assets/linear5_panel_bg.jpg"
PANEL_BG_RGB = (186, 210, 235)
BLOCKED = JMRI_ROOT / "layouts/linear5/output/linear5_blocked.xml"
VIEWPORT_JSON = JMRI_ROOT / "layouts/linear5/data/viewport.json"

INK = (72, 98, 128, 255)
INK_LIGHT = (108, 132, 158, 200)
FACE = (248, 250, 252, 215)
NORTH = (150, 118, 48, 255)
SOUTH = (88, 108, 132, 255)

# Rose size and placement (prod pixels): inset from lower-right, then shift left/up.
COMPASS_RADIUS = 36
COMPASS_MARGIN = 48
COMPASS_SHIFT_LEFT = 200
COMPASS_SHIFT_UP = 15


def _viewport_offsets() -> tuple[int, int]:
    """Compass extra-left (prod px) and global panel shift (prod px)."""
    panel_shift = 20
    compass_extra = 30
    if VIEWPORT_JSON.is_file():
        data = json.loads(VIEWPORT_JSON.read_text(encoding="utf-8"))
        panel_shift = int(data.get("panel_x_shift_display", panel_shift))
        compass_extra = int(data.get("compass_extra_x_display", compass_extra))
    return compass_extra, panel_shift


def _panel_dimensions() -> tuple[int, int]:
    width, height = 1900, 600
    scale = 1.5
    if VIEWPORT_JSON.is_file():
        scale = float(
            json.loads(VIEWPORT_JSON.read_text(encoding="utf-8")).get("display_scale", scale)
        )
    if BLOCKED.is_file():
        layout = ET.parse(BLOCKED).getroot().find(".//LayoutEditor")
        if layout is not None:
            pw = layout.get("panelwidth")
            ph = layout.get("panelheight")
            if pw and ph:
                width = int(round(float(pw) * scale))
                height = int(round(float(ph) * scale))
    return width, height


def _compass_center(width: int, height: int) -> tuple[float, float]:
    compass_extra, panel_shift = _viewport_offsets()
    shift_left = COMPASS_SHIFT_LEFT + panel_shift + compass_extra
    cx = width - COMPASS_MARGIN - COMPASS_RADIUS - shift_left
    cy = height - COMPASS_MARGIN - COMPASS_RADIUS - COMPASS_SHIFT_UP
    return cx, cy


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    )
    for path in candidates:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _text_size(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> tuple[float, float]:
    if hasattr(font, "getbbox"):
        left, top, right, bottom = font.getbbox(text)
        return right - left, bottom - top
    return draw.textsize(text, font=font)


def _draw_compass(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    radius: float,
    *,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    """Moderate rose: soft face, rings, cardinals, modest N/S pointers, N/E/S/W labels."""
    r = radius
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=FACE, outline=INK, width=2)
    ri = r * 0.62
    draw.ellipse((cx - ri, cy - ri, cx + ri, cy + ri), outline=INK_LIGHT, width=1)

    # Cardinal spokes
    draw.line([(cx, cy - r * 0.82), (cx, cy + r * 0.82)], fill=INK, width=1)
    draw.line([(cx - r * 0.82, cy), (cx + r * 0.82, cy)], fill=INK, width=2)

    # Short intercardinal ticks on the ring
    for angle_deg in (45, 135, 225, 315):
        rad = math.radians(angle_deg)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        x0 = cx + cos_a * r * 0.9
        y0 = cy + sin_a * r * 0.9
        x1 = cx + cos_a * r * 0.72
        y1 = cy + sin_a * r * 0.72
        draw.line([(x0, y0), (x1, y1)], fill=INK_LIGHT, width=1)

    # North pointer (moderate gold triangle)
    draw.polygon(
        [
            (cx, cy - r * 0.88),
            (cx - r * 0.16, cy - r * 0.08),
            (cx + r * 0.16, cy - r * 0.08),
        ],
        fill=NORTH,
        outline=INK,
    )
    # South pointer (smaller, subdued)
    draw.polygon(
        [
            (cx, cy + r * 0.55),
            (cx - r * 0.1, cy + r * 0.04),
            (cx + r * 0.1, cy + r * 0.04),
        ],
        fill=SOUTH,
        outline=INK,
    )

    for text, lx, ly in (
        ("N", cx, cy - r * 1.32),
        ("E", cx + r * 1.26, cy),
        ("S", cx, cy + r * 1.32),
        ("W", cx - r * 1.26, cy),
    ):
        tw, th = _text_size(draw, text, font)
        draw.text((lx - tw / 2, ly - th / 2), text, fill=INK, font=font)


def generate(path: Path = OUT_PATH) -> Path:
    width, height = _panel_dimensions()
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = _compass_center(width, height)
    font = _load_font(13)
    _draw_compass(draw, cx, cy, COMPASS_RADIUS, font=font)

    path.parent.mkdir(parents=True, exist_ok=True)
    flat = Image.new("RGB", img.size, PANEL_BG_RGB)
    flat.paste(img, mask=img.split()[3])
    flat.save(path, format="JPEG", quality=95, optimize=True)
    return path


def main() -> None:
    out = generate()
    w, h = _panel_dimensions()
    cx, cy = _compass_center(w, h)
    print(f"Wrote {out} ({w}×{h}, RGB {PANEL_BG_RGB}; compass at {int(cx)}, {int(cy)})")


if __name__ == "__main__":
    main()
