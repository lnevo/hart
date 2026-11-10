#!/usr/bin/env python3
"""Taller card crops in CarImagesCardFill/ — width unchanged, height from source above/below.

Reads approved CarImagesFinal/ as reference (position + width). Where the on-card
display height is short, expands up to 1\" taller (capped by the image box), re-pulling
extra pixels from the leveled source equally above and below so the car stays centered.
Images that already fill the box are copied unchanged.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from crop_car_image import _crop_at_fixed_size
from finalize_car_images import (
    IMAGES_DIR,
    _level_for_finalize,
    _locate_on_source,
)

BASE = Path(__file__).resolve().parent.parent  # Car Cards project root (scripts live in card_pipeline/)
REF_DIR = BASE / "CarImagesFinal"
OUT_DIR = BASE / "CarImagesCardFill"

# Matches generate_card_template.py embed width (inches).
EMBED_WIDTH_IN = 1.84
# Max increase in on-card display height (inches).
MAX_DISPLAY_BOOST_IN = 1.0
# Target cap — roughly the bordered image box usable height.
TARGET_MAX_DISPLAY_IN = 1.12
# Skip tiny tweaks that won't matter on the printed card.
MIN_BOOST_IN = 0.08


def _display_height_in(width_px: int, height_px: int) -> float:
    return EMBED_WIDTH_IN * height_px / max(width_px, 1)


def _target_height_px(width_px: int, current_display_in: float) -> int | None:
    boost = min(
        MAX_DISPLAY_BOOST_IN,
        max(0.0, TARGET_MAX_DISPLAY_IN - current_display_in),
    )
    if boost < MIN_BOOST_IN:
        return None
    target_display = current_display_in + boost
    return int(round(width_px * target_display / EMBED_WIDTH_IN))


def expand_one(stem: str, verbose: bool = False) -> str:
    ref_path = REF_DIR / f"{stem}.png"
    src_path = IMAGES_DIR / f"{stem}.png"
    if not ref_path.exists():
        return "missing_ref"
    if not src_path.exists():
        return "missing_src"

    ref_img = Image.open(ref_path)
    tw, th = ref_img.size
    current_display = _display_height_in(tw, th)
    new_th = _target_height_px(tw, current_display)

    out_path = OUT_DIR / ref_path.name
    if new_th is None or new_th <= th:
        shutil.copy2(ref_path, out_path)
        if verbose:
            print(f"{stem}: copy {tw}x{th} display={current_display:.2f}\"")
        return "copy"

    leveled, _ = _level_for_finalize(src_path, stem)
    src_left, src_top = _locate_on_source(leveled, ref_img)
    center_x = src_left + tw / 2.0
    center_y = src_top + th / 2.0
    out = _crop_at_fixed_size(leveled, center_x, center_y, tw, new_th)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.save(out_path)

    new_display = _display_height_in(tw, new_th)
    if verbose:
        print(
            f"{stem}: {tw}x{th} -> {tw}x{new_th}  "
            f"display {current_display:.2f}\" -> {new_display:.2f}\""
        )
    return "expand"


def expand_all(verbose: bool = False) -> int:
    refs = sorted(REF_DIR.glob("IMG_*.png"))
    if not refs:
        print(f"No images in {REF_DIR}")
        return 1
    counts = {"expand": 0, "copy": 0, "missing_ref": 0, "missing_src": 0}
    for p in refs:
        status = expand_one(p.stem, verbose=verbose)
        counts[status] = counts.get(status, 0) + 1
    print(f"Wrote {len(refs)} images to {OUT_DIR}/")
    print(f"  expanded={counts['expand']}  unchanged={counts['copy']}")
    if counts["missing_src"] or counts["missing_ref"]:
        print(f"  missing_src={counts['missing_src']}  missing_ref={counts['missing_ref']}")
    return 0


def main() -> int:
    verbose = "--quiet" not in sys.argv
    if len(sys.argv) == 2 and sys.argv[1] not in ("--all", "--quiet"):
        stem = Path(sys.argv[1]).stem
        expand_one(stem, verbose=True)
        return 0
    return expand_all(verbose=verbose)


if __name__ == "__main__":
    raise SystemExit(main())
