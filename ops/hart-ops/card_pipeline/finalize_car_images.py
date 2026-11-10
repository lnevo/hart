#!/usr/bin/env python3
"""Centered final crops in CarImagesFinal/ — re-pulled from Images/, no gray gaps."""

from __future__ import annotations

import sys
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from crop_car_image import (
    BODY_THRESH,
    MIN_ROTATION_DEG,
    TRACK_THRESH,
    _backdrop_color,
    _centered_crop_box,
    _crop_at_fixed_size,
    _level_image,
    detect_car_bbox,
    match_lightbox_white_balance,
)

from car_paths import CAR_IMAGES_DIR as CROPPED_DIR, FINAL_DIR, IMAGES_DIR

SAMPLE_STEMS = [
    "IMG_9131",
    "IMG_9110",
    "IMG_9135",
    "IMG_9106",
    "IMG_9160",
    "IMG_9185",
    "IMG_9137",
    "IMG_9139",
]

# Fine pan after auto-center (ties: + = crop window right, car shifts left in frame).
TIE_PAN_ADJUSTMENTS: dict[str, float] = {
    "IMG_9134": 1.5,
    "IMG_9137": 2.0,
    "IMG_9139": -0.5,
    "IMG_9149": 2.5,
    "IMG_9154": 2.5,
    "IMG_9160": -0.25,
    "IMG_9192": -0.25,
    "IMG_9193": 1.0,
    "IMG_9194": 1.0,
    "IMG_9195": 1.0,
}

# Extra width beyond CarImages size, in ties (left, right).
WIDTH_TIE_EXTRA: dict[str, tuple[float, float]] = {
    "IMG_9133": (1.5, 1.5),
    "IMG_9134": (1.5, 1.5),
    "IMG_9137": (5.0, 5.0),
    "IMG_9192": (7.5, 7.5),
    "IMG_9193": (1.5, 1.5),
    "IMG_9194": (1.5, 1.5),
    "IMG_9195": (1.5, 1.5),
}

# Output height overrides (e.g. short flatcars → box-car height).
HEIGHT_OVERRIDE: dict[str, int] = {
    "IMG_9149": 671,
    "IMG_9154": 671,
}

# These level badly from auto rotation — match the approved CarImages orientation.
ROTATION_OVERRIDES: dict[str, float] = {
    "IMG_9183": 0.0,
    "IMG_9187": 0.0,
    "IMG_9195": -0.75,
}

# Warm/cool cast vs fleet — normalize wall white balance before crop.
WHITE_BALANCE_STEMS: set[str] = {"IMG_9187"}

BOX_HEIGHT_MIN = 620
BOX_HEIGHT_MAX = 720
FLATCAR_MAX_HEIGHT = 620
FLATCAR_MIN_HEIGHT = 400
FLATCAR_MIN_RATIO = 3.0

# Card image box (matches expand_card_fill_images / generate_card_template).
CARD_EMBED_WIDTH_IN = 1.84
CARD_DISPLAY_HEIGHT_IN = 1.12

# Tall cars: widen in WIDTH_TIE_EXTRA, then center-crop height to the card-box aspect.
CARD_ASPECT_HEIGHT_STEMS: set[str] = {"IMG_9137"}


def _card_box_height(out_tw: int) -> int:
    return int(round(out_tw * CARD_DISPLAY_HEIGHT_IN / CARD_EMBED_WIDTH_IN))


def _box_car_target_height() -> int:
    heights = [
        Image.open(p).size[1]
        for p in CROPPED_DIR.glob("IMG_*.png")
        if BOX_HEIGHT_MIN <= Image.open(p).size[1] <= BOX_HEIGHT_MAX
    ]
    return int(round(sum(heights) / len(heights))) if heights else 671


def _is_flatcar_crop(tw: int, th: int) -> bool:
    return (
        FLATCAR_MIN_HEIGHT < th < FLATCAR_MAX_HEIGHT
        and tw / max(th, 1) >= FLATCAR_MIN_RATIO
    )


def _level_for_finalize(src_path: Path, stem: str) -> tuple[Image.Image, float]:
    img = Image.open(src_path)
    if stem in WHITE_BALANCE_STEMS:
        img = match_lightbox_white_balance(img)
    if stem in ROTATION_OVERRIDES:
        angle = ROTATION_OVERRIDES[stem]
        if abs(angle) < MIN_ROTATION_DEG:
            return img, angle
        leveled = img.rotate(
            angle,
            resample=Image.BICUBIC,
            expand=True,
            fillcolor=_backdrop_color(img),
        )
        return leveled, angle
    return _level_image(img)


def _rolling_stock_span(gray: np.ndarray) -> tuple[int, int]:
    """Coupler tips just outside the visible body silhouette."""
    h, w = gray.shape
    mid = gray[int(h * 0.30) : int(h * 0.70), :]
    body = (mid < BODY_THRESH).mean(axis=0)
    cols = np.where(body > 0.15)[0]
    if not cols.size:
        lower = gray[int(h * 0.70) :, :]
        lfrac = (lower < TRACK_THRESH).mean(axis=0)
        strong = np.where(lfrac > 0.22)[0]
        if strong.size:
            return int(strong[0]), int(strong[-1])
        return 0, w - 1

    blo, bhi = int(cols[0]), int(cols[-1])
    lower = gray[int(h * 0.72) :, :]
    lfrac = (lower < TRACK_THRESH).mean(axis=0)
    reach = max(30, int(w * 0.035))
    l0 = max(0, blo - reach)
    left_tip = l0 + int(np.argmax(lfrac[l0 : blo + 1]))
    r1 = min(w, bhi + reach + 1)
    right_tip = bhi + int(np.argmax(lfrac[bhi : r1]))
    return left_tip, right_tip


def _tie_pitch(gray: np.ndarray, lo: int, hi: int) -> float:
    h = gray.shape[0]
    band = gray[int(h * 0.75) :, max(0, lo) : hi]
    if band.size == 0 or hi <= lo:
        return 28.0
    col = (band < TRACK_THRESH).mean(axis=0)
    smooth = np.convolve(col, np.ones(5) / 5, mode="same")
    peaks = [
        i
        for i in range(2, len(smooth) - 2)
        if smooth[i] > smooth[i - 1] and smooth[i] > smooth[i + 1] and smooth[i] > 0.12
    ]
    if len(peaks) >= 3:
        return float(np.clip(np.median(np.diff(peaks)), 12, 45))
    return max(18.0, (hi - lo) / 50.0)


def _horizontal_shift(gray: np.ndarray) -> int:
    """Pixels to move content right for centering (same as paste shift on CarImages)."""
    w = gray.shape[1]
    lo, hi = _rolling_stock_span(gray)
    return int(round(w / 2.0 - (lo + hi) / 2.0))


def _find_src_left(
    leveled: Image.Image,
    crop_gray: np.ndarray,
    src_top: int,
) -> int:
    """Match CarImages horizontally on the leveled source at a known top edge."""
    src = np.asarray(ImageOps.grayscale(leveled), dtype=np.int16)
    crop = crop_gray.astype(np.int16)
    th, tw = crop.shape
    y0, y1 = int(th * 0.25), int(th * 0.90)
    ref = crop[y0:y1, :]
    sw = src.shape[1]

    best_diff, best_sl = 1e18, 0
    for sl in range(0, sw - tw + 1, 2):
        patch = src[src_top + y0 : src_top + y1, sl : sl + tw]
        diff = float(np.mean(np.abs(ref - patch)))
        if diff < best_diff:
            best_diff, best_sl = diff, sl

    for sl in range(max(0, best_sl - 8), min(sw - tw, best_sl + 8) + 1):
        patch = src[src_top + y0 : src_top + y1, sl : sl + tw]
        diff = float(np.mean(np.abs(ref - patch)))
        if diff < best_diff:
            best_diff, best_sl = diff, sl
    return best_sl


def _locate_on_source(
    leveled: Image.Image,
    crop_img: Image.Image,
) -> tuple[int, int]:
    """Find where CarImages sits on the leveled source photo."""
    tw, th = crop_img.size
    gray = np.asarray(ImageOps.grayscale(leveled), dtype=np.uint8)
    bx0, by0, bx1, by1 = detect_car_bbox(leveled)
    sl, st, sr, sb = _centered_crop_box(gray, bx0, by0, bx1, by1)

    if (sr - sl) == tw and (sb - st) == th:
        return sl, st

    if abs((sb - st) - th) <= 2:
        src_top = st
    else:
        src_top = int(round((by0 + by1) / 2.0 - th / 2.0))

    crop_gray = np.asarray(ImageOps.grayscale(crop_img), dtype=np.uint8)
    src_left = _find_src_left(leveled, crop_gray, src_top)
    return src_left, src_top


def finalize_box(stem: str, verbose: bool = False) -> dict | None:
    """Where the finished image sits on the leveled source photo, or None if a file is missing.

    Returns ``leveled`` (the image), ``center`` (x, y) and ``size`` (w, h) of the window.
    """
    crop_path = CROPPED_DIR / f"{stem}.png"
    src_path = IMAGES_DIR / f"{stem}.png"
    if not crop_path.exists():
        if verbose:
            print(f"missing {crop_path}")
        return None
    if not src_path.exists():
        if verbose:
            print(f"missing source {src_path}")
        return None

    crop_img = Image.open(crop_path)
    tw, th = crop_img.size
    crop_gray = np.asarray(ImageOps.grayscale(crop_img), dtype=np.uint8)

    lo, hi = _rolling_stock_span(crop_gray)
    pitch = _tie_pitch(crop_gray, lo, hi)
    ties_l, ties_r = lo / pitch, (tw - hi) / pitch
    shift = _horizontal_shift(crop_gray)

    leveled, _ = _level_for_finalize(src_path, stem)
    src_left, src_top = _locate_on_source(leveled, crop_img)
    new_left = src_left - shift
    pan_ties = TIE_PAN_ADJUSTMENTS.get(stem, 0.0)
    extra_l, extra_r = WIDTH_TIE_EXTRA.get(stem, (0.0, 0.0))
    out_tw = tw + int(round((extra_l + extra_r) * pitch))
    center_x = new_left + tw / 2.0 + pan_ties * pitch

    out_th = HEIGHT_OVERRIDE.get(stem, th)
    if stem in CARD_ASPECT_HEIGHT_STEMS:
        out_th = _card_box_height(out_tw)
    elif out_th == th and _is_flatcar_crop(tw, th):
        out_th = _box_car_target_height()

    center_y = src_top + th / 2.0
    if verbose:
        pan_note = f" pan={pan_ties:+.2f} ties" if pan_ties else ""
        extra_note = ""
        if extra_l or extra_r:
            extra_note = f" extra_L/R={extra_l:.1f}/{extra_r:.1f} ties"
        h_note = f" h={out_th}" if out_th != th else ""
        w_note = f" w={out_tw}" if out_tw != tw else ""
        print(
            f"{stem}: {tw}x{th}{w_note}{h_note}  origin=({src_left},{src_top})  "
            f"shift={shift}px ({shift/pitch:.1f} ties){pan_note}{extra_note}  "
            f"before L/R={ties_l:.1f}/{ties_r:.1f} ties"
        )
    return {"leveled": leveled, "center": (center_x, center_y), "size": (out_tw, out_th)}


def finalize_one(stem: str, verbose: bool = False) -> bool:
    box = finalize_box(stem, verbose)
    if box is None:
        return False
    out = _crop_at_fixed_size(box["leveled"], *box["center"], *box["size"])
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    out.save(FINAL_DIR / f"{stem}.png")
    return True


def finalize_all(verbose: bool = False) -> int:
    crops = sorted(CROPPED_DIR.glob("IMG_*.png"))
    if not crops:
        print(f"No images in {CROPPED_DIR}")
        return 1
    ok = sum(1 for p in crops if finalize_one(p.stem, verbose=verbose))
    print(f"Wrote {ok} images to {FINAL_DIR}/")
    return 0


def finalize_sample(verbose: bool = True) -> int:
    ok = sum(1 for stem in SAMPLE_STEMS if finalize_one(stem, verbose=verbose))
    print(f"Wrote {ok} review images to {FINAL_DIR}/")
    return 0


def main() -> int:
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--sample":
            return finalize_sample()
        if arg == "--all":
            return finalize_all(verbose=True)
        stem = Path(arg).stem
        return 0 if finalize_one(stem, verbose=True) else 1
    return finalize_sample()


if __name__ == "__main__":
    raise SystemExit(main())
