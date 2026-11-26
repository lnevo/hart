#!/usr/bin/env python3
"""Compare Tesseract vs EasyOCR on car-side bands from full Images/."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from crop_car_image import detect_car_bbox
from process_car_images import (
    _find_road_mark,
    _match_roster,
    _ocr_band,
    _parse_markings,
    load_roster,
)

BASE = Path(__file__).resolve().parent.parent  # Car Cards project root (scripts live in card_pipeline/)
IMAGES_DIR = BASE / "Images"

# B&O-heavy samples that failed roster match on card-fill OCR.
DEFAULT_SAMPLES = [
    "IMG_9107",
    "IMG_9109",
    "IMG_9110",
    "IMG_9112",
    "IMG_9122",
    "IMG_9129",
    "IMG_9130",
    "IMG_9135",
    "IMG_9140",
    "IMG_9145",
]


def _crop_band(img: Image.Image, bbox: tuple[int, int, int, int]) -> Image.Image:
    x0, y0, x1, y1 = bbox
    w, h = img.size
    pad_x = int(0.06 * (x1 - x0))
    pad_y = int(0.10 * (y1 - y0))
    rx0 = max(0, x0 - pad_x)
    ry0 = max(0, y0 - pad_y)
    rx1 = min(w, x1 + pad_x)
    ry1 = min(h, y1 + pad_y)
    return img.crop((rx0, ry0, rx1, ry1))


def _ocr_easyocr(
    img: Image.Image,
    bbox: tuple[int, int, int, int],
    reader: object | None = None,
) -> str:
    import easyocr

    band = _crop_band(img, bbox)
    band = ImageOps.grayscale(band)
    band = band.point(lambda p: 255 if p > 175 else (0 if p < 110 else p))
    zoom = band.resize((band.width * 3, band.height * 3), Image.LANCZOS)
    if reader is None:
        reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    lines = reader.readtext(np.array(zoom), detail=0, paragraph=True)
    return " ".join(lines).upper()


def _summarize(engine: str, text: str, roster: list[dict]) -> str:
    parsed = _parse_markings(text)
    marks, number = _find_road_mark(text, roster)
    car, conf = _match_roster(text, roster, marks, number, parsed)
    rid = car["roster_id"] if car else "—"
    return f"{engine:10} roster={rid} conf={conf} marks={marks!r} num={number!r}"


def compare(stems: list[str]) -> None:
    import easyocr

    roster = load_roster()
    reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    tess_hits = 0
    easy_hits = 0

    for stem in stems:
        path = IMAGES_DIR / f"{stem}.png"
        if not path.exists():
            print(f"{stem}: missing")
            continue
        img = Image.open(path).convert("RGB")
        bbox = detect_car_bbox(img)

        tess_text, _ = _ocr_band(img, bbox)
        easy_text = _ocr_easyocr(img, bbox, reader)

        if _match_roster(tess_text, roster, *_find_road_mark(tess_text, roster), _parse_markings(tess_text))[0]:
            tess_hits += 1
        if _match_roster(easy_text, roster, *_find_road_mark(easy_text, roster), _parse_markings(easy_text))[0]:
            easy_hits += 1

        print(f"\n=== {stem} ===")
        print(_summarize("Tesseract", tess_text, roster))
        print(_summarize("EasyOCR", easy_text, roster))
        print(f"  tess[:100]: {tess_text[:100]!r}")
        print(f"  easy[:100]: {easy_text[:100]!r}")

    print(f"\n--- Summary ({len(stems)} samples) ---")
    print(f"  Tesseract matches: {tess_hits}/{len(stems)}")
    print(f"  EasyOCR matches:   {easy_hits}/{len(stems)}")


def main() -> int:
    p = argparse.ArgumentParser(description="Compare OCR engines on car photos")
    p.add_argument(
        "stems",
        nargs="*",
        default=DEFAULT_SAMPLES,
        help="Image stems (default: 10 hard B&O samples)",
    )
    args = p.parse_args()
    compare(args.stems)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
