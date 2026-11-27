"""Level a car photo and match its light-box wall: roll angle, backdrop colour, white balance."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageOps

from crop_runs import _trim_foreground  # sibling modules, on sys.path with this one
from crop_settings import CROP


def _backdrop_color(img: Image.Image) -> int | tuple[int, ...]:
    """Sample the light-box wall for rotation fill color."""
    g = np.asarray(ImageOps.grayscale(img), dtype=np.uint8)
    H, W = g.shape
    strip = g[: max(1, H // 18), W // 5 : 4 * W // 5]
    level = int(np.median(strip))
    if img.mode in ("RGB", "RGBA"):
        rgb = (level, level, level)
        return rgb + (255,) if img.mode == "RGBA" else rgb
    if img.mode == "L":
        return level
    return (level, level, level)


def match_lightbox_white_balance(
    img: Image.Image,
    target: tuple[float, float, float] | None = None,
) -> Image.Image:
    """Scale RGB so the light-box wall matches the fleet reference."""
    target_rgb = target or CROP.tone.fleet_lightbox_wall
    rgb = img.convert("RGB")
    arr = np.asarray(rgb, dtype=np.float32)
    h, w = arr.shape[:2]
    strip = arr[: max(1, h // 10), w // 4 : 3 * w // 4]
    gray = strip.mean(axis=2)
    wall_px = strip[gray > 200]
    if wall_px.shape[0] < 50:
        wall_px = strip.reshape(-1, 3)
    src = np.median(wall_px, axis=0)
    gains = np.array(target_rgb, dtype=np.float32) / np.maximum(src, 1.0)
    gains = np.clip(gains, 0.80, 1.20)
    corrected = np.clip(arr * gains.reshape(1, 1, 3), 0, 255).astype(np.uint8)
    return Image.fromarray(corrected)


def _track_roll_angle(region: np.ndarray) -> float | None:
    """Roll (degrees for PIL rotate) from the lower-band track line."""
    Rh, Rw = region.shape
    lower = region[int(Rh * 0.55) :, :]
    xs, ys = [], []
    for c in range(int(0.15 * Rw), int(0.85 * Rw), 8):
        col = lower[:, c]
        rows = np.where(col < CROP.tone.track_thresh)[0]
        if rows.size >= 3:
            xs.append(float(c))
            ys.append(float(rows.max()))
    if len(xs) < 10:
        return None
    slope = np.polyfit(np.array(xs), np.array(ys), 1)[0]
    return float(np.degrees(np.arctan(slope)))


def _body_roll_angle(region: np.ndarray) -> float | None:
    """Roll from the car-body roof line when visible (hoppers / boxcars)."""
    Rh, Rw = region.shape
    upper = region[: max(1, int(Rh * 0.35)), int(0.20 * Rw) : int(0.80 * Rw)]
    if upper.size == 0:
        return None
    xs, ys = [], []
    for c in range(0, upper.shape[1], 16):
        col = upper[:, c]
        rows = np.where(col < CROP.tone.body_thresh)[0]
        if rows.size:
            xs.append(float(c))
            ys.append(float(rows.min()))
    if len(xs) < 8:
        return None
    slope = np.polyfit(np.array(xs), np.array(ys), 1)[0]
    # Counter the measured body slope to level the roof line.
    return float(np.degrees(np.arctan(slope)))


def estimate_rotation(img: Image.Image) -> float:
    """Estimate roll angle (degrees) to level the car; 0 = perfectly level."""
    g = np.asarray(ImageOps.grayscale(img), dtype=np.uint8)
    H, W = g.shape
    y0, y1 = int(CROP.frame.y0 * H), int(CROP.frame.y1 * H)
    region = _trim_foreground(g[y0:y1, :])

    track = _track_roll_angle(region)
    body = _body_roll_angle(region)

    if body is not None and abs(body) >= 0.15:
        if track is None:
            return body
        if abs(body - track) > 0.45 and abs(body) < 1.2:
            return body
    if track is not None:
        return track
    return 0.0


def _level_image(img: Image.Image) -> tuple[Image.Image, float]:
    angle = estimate_rotation(img)
    if abs(angle) < CROP.frame.min_rotation_deg:
        return img, angle
    leveled = img.rotate(
        angle,
        resample=Image.BICUBIC,
        expand=True,
        fillcolor=_backdrop_color(img),
    )
    return leveled, angle
