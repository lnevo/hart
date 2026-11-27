#!/usr/bin/env python3
"""Crop a model-car photo tight to the rolling stock.

Detects the car against the light-box background (works for dark and light-gray
rolling stock) and crops to the couplers with minimal padding. Pixels are left
untouched — no color or backdrop adjustments.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal, TypedDict

import numpy as np
from PIL import Image, ImageOps

# Sibling modules, on sys.path with this one. CROP, _backdrop_color, _level_image and
# match_lightbox_white_balance are also imported from here by finalize_car_images and crop_picker.
from crop_level import _backdrop_color, _level_image, match_lightbox_white_balance  # noqa: F401
from crop_runs import _span, _trim_foreground
from crop_settings import CROP
from crop_span import _horizontal_span

Box = tuple[int, int, int, int]  # left, top, right, bottom
CropStatus = Literal["ok", "review"]


class Crop(TypedDict):
    """process_image: the levelled photo cropped to the car with tie margins."""

    source: str
    bbox: Box
    bbox_size: tuple[int, int]
    output_size: tuple[int, int]
    ratio: float
    rotation_deg: float
    crop_status: CropStatus
    image: Image.Image


def _estimate_tie_pitch(
    gray: np.ndarray,
    x0: int,
    x1: int,
    y0: int,
    y1: int,
) -> float:
    """Estimate tie spacing (px) from the track band under the car."""
    H, W = gray.shape
    x0 = max(0, min(x0, W - 1))
    x1 = max(x0 + 1, min(x1, W))
    y0 = max(0, min(y0, H - 1))
    y1 = max(y0 + 1, min(y1, H))
    strip = gray[y0:y1, x0:x1]
    if strip.size == 0:
        return 28.0
    col = (strip < CROP.tone.track_thresh).mean(axis=0)
    sm = np.convolve(col, np.ones(5) / 5, mode="same")
    peaks: list[int] = []
    for i in range(2, len(sm) - 2):
        if sm[i] > sm[i - 1] and sm[i] > sm[i + 1] and sm[i] > 0.12:
            peaks.append(i)
    if len(peaks) >= 4:
        peak_pitch = float(np.median(np.diff(peaks)))
        cw = x1 - x0
        cw_pitch = float(np.clip(cw / 52.0, 18.0, 40.0))
        blended = (peak_pitch + cw_pitch) / 2.0
        pitch = max(blended, cw_pitch * 0.82)
        return float(np.clip(pitch, CROP.frame.tie_pitch_min, CROP.frame.tie_pitch_max))
    cw = x1 - x0
    cw_pitch = float(np.clip(cw / 52.0, 18.0, 40.0))
    return cw_pitch


def _columns(region: np.ndarray, band: tuple[float, float]) -> np.ndarray:
    """The columns of ``region`` between two fractions of its width."""
    width = region.shape[1]
    return region[:, int(band[0] * width) : int(band[1] * width)]


def _dark_share(pixels: np.ndarray) -> float:
    """Share of ``pixels`` darker than the car-body grey."""
    return float((pixels < CROP.tone.body_thresh).mean())


def _left_end_top(region: np.ndarray, ry0_c: int) -> int:
    """The body top, raised to the left band's first body row when the extreme-left strip is clear there."""
    top = CROP.top
    l_rows = np.where((_columns(region, top.left_band) < CROP.tone.body_thresh).mean(axis=1) > top.left_body_min)[0]
    ry0 = ry0_c
    if l_rows.any():
        ry0_l = int(l_rows[0])
        if ry0_l < ry0_c:
            extreme_at_l = _dark_share(region[ry0_l, : int(top.extreme_left * region.shape[1])])
            if extreme_at_l < top.extreme_left_max:
                ry0 = ry0_l
    return ry0


def _handbrake_top(region: np.ndarray, center: np.ndarray, ry0_c: int, ry0: int) -> int:
    """Walk up from the body top for a left-end handbrake staff or wheel; return the raised top."""
    top = CROP.top
    hband = _columns(region, top.handbrake_band)
    extreme_w = int(top.extreme_left * region.shape[1])
    hb_lo, hb_hi = top.handbrake_frac
    for r in range(ry0_c - 1, -1, -1):
        extreme_frac = _dark_share(region[r, :extreme_w])
        hb_frac = _dark_share(hband[r])
        c_frac = _dark_share(center[r])
        if extreme_frac > top.wedge_stop:
            break
        if hb_lo < hb_frac < hb_hi and c_frac < top.handbrake_center_max and extreme_frac < top.extreme_left_max:
            ry0 = min(ry0, r)
        elif c_frac > top.body_resume and hb_frac < top.body_resume_handbrake_max:
            break
    return ry0


def _roof_top(center: np.ndarray, ry0_c: int, ry1: int, ry0: int) -> int:
    """Raise the top over gondola covers, cab roofs and roofwalks above the deck line."""
    top = CROP.top
    roof_limit = max(0, ry0_c - int((ry1 - ry0_c) * top.roof_reach))
    for r in range(ry0_c - 1, roof_limit - 1, -1):
        row = center[r]
        if _dark_share(row) > top.roof_dark_min or float(row.std()) > top.roof_std_min:
            ry0 = min(ry0, r)
        elif r < ry0_c - int((ry1 - ry0_c) * top.roof_gap):
            break
    return ry0


def _row_band(region: np.ndarray) -> tuple[int, int]:
    """(top, bottom) rows of the car in the analysis region: track rows anchor the bottom, the body the top."""
    track_rows = (region < CROP.tone.track_thresh).mean(axis=1) > CROP.rows.track_row_frac
    if not track_rows.any():
        return _span((region < CROP.tone.content_thresh).mean(axis=1) > CROP.rows.content_row_frac)
    _, ry1 = _span(track_rows)
    center = _columns(region, CROP.top.center_band)
    c_rows = np.where((center < CROP.tone.body_thresh).mean(axis=1) > CROP.top.center_body_min)[0]
    if not c_rows.any():
        ry0, _ = _span(track_rows)
        return ry0, ry1
    ry0_c = int(c_rows[0])
    ry0 = _handbrake_top(region, center, ry0_c, _left_end_top(region, ry0_c))
    ry0 = max(0, ry0 - int((ry1 - ry0) * CROP.frame.row_expand_up))
    return _roof_top(center, ry0_c, ry1, ry0), ry1


def detect_car_bbox(img: Image.Image) -> tuple[int, int, int, int]:
    """Locate the car by anchoring on the track, then growing through the body: (left, top, right, bottom)."""
    g = np.asarray(ImageOps.grayscale(img), dtype=np.uint8)
    H, W = g.shape
    y0, y1 = int(CROP.frame.y0 * H), int(CROP.frame.y1 * H)
    region = _trim_foreground(g[y0:y1, :])
    y1 = y0 + region.shape[0]
    ry0, ry1 = _row_band(region)
    if ry1 <= ry0:
        return 0, y0, W, y1

    # Horizontal span already peels corner shadows; pre-trim here can clip
    # outboard coupler ends on split flatcars (e.g. IMG_9149).
    bx0, bx1 = _horizontal_span(region[ry0:ry1, :])
    by0, by1 = y0 + ry0, y0 + ry1
    pad = int((by1 - by0) * CROP.top.band_pad)
    return (max(0, bx0), max(0, by0 - pad), min(W, bx1), min(H, by1 + pad))


def _centered_crop_box(
    gray: np.ndarray,
    bx0: int,
    by0: int,
    bx1: int,
    by1: int,
) -> tuple[int, int, int, int]:
    """Symmetric tie margins past coupler tips, centered on the car."""
    H, W = gray.shape
    cw, ch = bx1 - bx0, by1 - by0
    track_y0 = by0 + int(ch * 0.62)
    track_y1 = min(H, by1 + int(ch * 0.08))
    pitch = _estimate_tie_pitch(gray, bx0, bx1, track_y0, track_y1)
    pad_x = max(8, int(CROP.frame.tie_margin_count * pitch))
    if cw >= W * CROP.frame.long_car_min_frac:
        pad_x = min(pad_x, max(8, int(cw * CROP.frame.long_car_pad_x)))
    pad_top = int(ch * CROP.frame.pad_top)
    pad_bottom = int(ch * CROP.frame.pad_bottom)

    cx = (bx0 + bx1) / 2.0
    half_w = cw / 2.0 + pad_x
    src_left = int(round(cx - half_w))
    src_right = int(round(cx + half_w))
    want_w = src_right - src_left

    if src_left < 0:
        src_right = min(W, src_right - src_left)
        src_left = 0
    if src_right > W:
        src_left = max(0, src_left - (src_right - W))
        src_right = W

    crop_cx = (src_left + src_right) / 2.0
    shift = int(round(cx - crop_cx))
    if shift:
        nleft = max(0, src_left + shift)
        nright = min(W, src_right + shift)
        if nright - nleft >= want_w - 2:
            src_left, src_right = nleft, nright

    src_top = max(0, by0 - pad_top)
    src_bottom = min(H, by1 + pad_bottom)
    return src_left, src_top, src_right, src_bottom


def _crop_at_fixed_size(
    img: Image.Image,
    center_x: float,
    center_y: float,
    target_w: int,
    target_h: int,
) -> Image.Image:
    """Extract a fixed-size window centered on (center_x, center_y)."""
    W, H = img.size
    src_left = int(round(center_x - target_w / 2.0))
    src_top = int(round(center_y - target_h / 2.0))
    src_right = src_left + target_w
    src_bottom = src_top + target_h

    fill = _backdrop_color(img)
    canvas = Image.new(img.mode, (target_w, target_h), fill)

    dest_x = max(0, -src_left)
    dest_y = max(0, -src_top)
    clip_left = max(0, src_left)
    clip_top = max(0, src_top)
    clip_right = min(W, src_right)
    clip_bottom = min(H, src_bottom)

    if clip_right > clip_left and clip_bottom > clip_top:
        canvas.paste(
            img.crop((clip_left, clip_top, clip_right, clip_bottom)),
            (dest_x, dest_y),
        )
    return canvas


def assess_crop(bbox: Box, img_size: tuple[int, int]) -> CropStatus:
    """"review" when the box is narrower or lower than CROP.frame's review minimums, else "ok"."""
    W, H = img_size
    x0, y0, x1, y1 = bbox
    cw, ch = x1 - x0, y1 - y0
    if cw < CROP.frame.review_min_w * W or ch < CROP.frame.review_min_h * H:
        return "review"
    return "ok"


def process_image(src: Path, dst: Path | None = None) -> Crop:
    """Level ``src``, crop it to the car with tie margins past the couplers; write it to ``dst`` when given."""
    img = Image.open(src)
    img, rotation = _level_image(img)
    W, H = img.size
    gray = np.asarray(ImageOps.grayscale(img), dtype=np.uint8)

    bx0, by0, bx1, by1 = detect_car_bbox(img)
    src_left, src_top, src_right, src_bottom = _centered_crop_box(
        gray, bx0, by0, bx1, by1
    )
    canvas = img.crop((src_left, src_top, src_right, src_bottom))

    if dst is not None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(dst)

    out_w, out_h = canvas.size
    return {
        "source": src.name,
        "bbox": (bx0, by0, bx1, by1),
        "bbox_size": (out_w, out_h),
        "output_size": (out_w, out_h),
        "ratio": out_w / max(out_h, 1),
        "rotation_deg": rotation,
        "crop_status": assess_crop((bx0, by0, bx1, by1), (W, H)),
        "image": canvas,
    }


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: python crop_car_image.py INPUT OUTPUT")
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    meta = process_image(src, dst)
    bx0, by0, bx1, by1 = meta["bbox"]
    ow, oh = meta["output_size"]
    print(
        f"car bbox: x[{bx0}-{bx1}] y[{by0}-{by1}]  "
        f"status={meta['crop_status']}  "
        f"wrote {dst}  ({ow}x{oh}, ratio {meta['ratio']:.2f})"
    )

if __name__ == "__main__":
    main()
