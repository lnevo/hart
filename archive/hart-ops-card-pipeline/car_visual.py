"""Infer car paint color and car type from crop images and OCR text."""

from __future__ import annotations

import colorsys
import re
from typing import Any

import numpy as np
from PIL import Image

# AAR-style stencil codes -> equipment type (when roster is unknown).
CLASS_TO_TYPE: dict[str, str] = {
    "XM": "Boxcar",
    "GB": "Gondola",
    "LO": "Hopper",
    "HT": "Hopper",
    "HTS": "Hopper",
}

OCR_TYPE_PATTERNS: list[tuple[str, str]] = [
    (r"SCALE\s*TEST", "MOW"),
    (r"MAINTENANCE\s+OF\s+WAY|WEED\s*SPRAY", "MOW"),
    (r"FLAT\s*CAR|FLATCAR", "Flatcar"),
    (r"GONDOLA", "Gondola"),
    (r"BOX\s*CAR|BOXCAR", "Boxcar"),
    (r"REEFER|REFRIGERATOR", "Reefer"),
    (r"TANK\s*CAR|TANKCAR", "Tank"),
    (r"CABOOSE", "Caboose"),
    (r"OBSERVATION", "Observation"),
    (r"DINING", "Dining"),
    (r"COMBINE", "Combine"),
    (r"BAGGAGE", "Baggage"),
    (r"COACH", "Coach"),
    (r"CEMENT|KOSMOS|KSMX", "Hopper"),
    (r"\bCOAL\b", "Coal"),
    (r"HOPPER", "Hopper"),
    (r"COIL", "Coil"),
    (r"CHESAPEAKE", "Coal"),
    (r"\bC\s*&\s*O\b", "Coal"),
    (r"PENNSYLVANIA|PEN\s*NSY", "Gondola"),
]


def infer_car_type(
    ocr_text: str,
    parsed: dict[str, str],
    *,
    roster_type: str = "",
    bbox: tuple[int, int, int, int] | None = None,
    image_size: tuple[int, int] | None = None,
) -> str:
    """Best-effort car type from roster, OCR keywords, class codes, or silhouette."""
    if roster_type and roster_type.strip():
        return roster_type.strip()

    text = ocr_text.upper()
    for pat, ctype in OCR_TYPE_PATTERNS:
        if re.search(pat, text, re.I):
            return ctype

    if parsed.get("car_type"):
        return parsed["car_type"]

    car_class = parsed.get("car_class", "").strip().upper()
    if car_class in CLASS_TO_TYPE:
        return CLASS_TO_TYPE[car_class]

    if bbox and image_size:
        x0, y0, x1, y1 = bbox
        _, img_h = image_size
        if img_h > 0:
            height_frac = (y1 - y0) / img_h
            if height_frac < 0.19:
                return "Flatcar"
            if height_frac > 0.48:
                return "Hopper"
            car_class = parsed.get("car_class", "").strip().upper()
            if car_class == "GB":
                return "Gondola"
            if car_class in CLASS_TO_TYPE:
                return CLASS_TO_TYPE[car_class]
            if re.search(r"CAPY", text) and re.search(r"LD\s*LMT", text):
                return "Boxcar"
            if 0.19 <= height_frac <= 0.48:
                return "Boxcar"

    return ""


def _sample_body_pixels(img: Image.Image, bbox: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    if w < 8 or h < 8:
        return np.empty((0, 3), dtype=np.uint8)

    cx0 = x0 + int(0.12 * w)
    cx1 = x1 - int(0.12 * w)
    cy0 = y0 + int(0.06 * h)
    cy1 = y0 + int(0.72 * h)
    region = np.asarray(img.crop((cx0, cy0, cx1, cy1)), dtype=np.uint8)
    if region.ndim != 3:
        return np.empty((0, 3), dtype=np.uint8)

    gray = region.mean(axis=2)
    # Light-box wall and glare
    mask = gray < 188
    pixels = region[mask]
    if pixels.shape[0] < 80:
        mask = gray < 210
        pixels = region[mask]
    if pixels.shape[0] > 4000:
        idx = np.linspace(0, pixels.shape[0] - 1, 4000, dtype=int)
        pixels = pixels[idx]
    return pixels


def _classify_rgb(r: float, g: float, b: float) -> str:
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)

    if v < 0.20:
        return "Black"
    if s < 0.14:
        if v > 0.62:
            return "Gray"
        if v > 0.34:
            return "Gray"
        return "Black"

    if h < 0.04 or h > 0.96:
        if v > 0.55 and s > 0.42:
            return "Orange"
        if r > 125 and g < 95 and b < 95:
            return "Boxcar Red"
        return "Freight Car Brown"

    if 0.04 <= h < 0.12:
        if v > 0.50:
            return "Yellow"
        return "Freight Car Brown"

    if 0.12 <= h < 0.38:
        return "Green"

    if 0.38 <= h < 0.58:
        return "Blue"

    if 0.58 <= h < 0.78:
        return "Blue"

    return "Gray"


def infer_car_color(img: Image.Image, bbox: tuple[int, int, int, int]) -> str:
    """Dominant paint color on the car body (excludes track and light-box wall)."""
    pixels = _sample_body_pixels(img, bbox)
    if pixels.shape[0] < 40:
        return ""

    brightness = pixels.mean(axis=1)
    body = pixels[brightness < 168]
    if body.shape[0] < 30:
        body = pixels[brightness < 195]
    if body.shape[0] < 20:
        return ""

    r, g, b = np.median(body, axis=0)
    return _classify_rgb(float(r), float(g), float(b))


def enrich_row_visuals(
    row: dict[str, Any],
    fill_img: Image.Image,
    fill_bbox: tuple[int, int, int, int],
    roster_type: str = "",
    parsed: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return updated car_type and color fields for a metadata row."""
    ocr_text = row.get("ocr_text", "")
    if parsed is None:
        parsed = {}
    merged: dict[str, str] = {
        "car_class": row.get("car_class", "") or parsed.get("car_class", ""),
    }
    if parsed.get("car_type"):
        merged["car_type"] = parsed["car_type"]
    car_type = infer_car_type(
        ocr_text,
        merged,
        roster_type=roster_type,
        bbox=fill_bbox,
        image_size=fill_img.size,
    )
    color = infer_car_color(fill_img, fill_bbox)
    return {"car_type": car_type, "color": color}
