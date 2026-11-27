"""Row and column runs of a grey car photo: flags to spans, tone levels and the deck band.

The one-dimensional pieces crop_span and crop_car_image build the car's box from. Every
threshold is in crop_settings.CROP.
"""

from __future__ import annotations

import numpy as np

from crop_settings import CROP  # a sibling module, on sys.path with this one


def _trim_foreground(region: np.ndarray) -> np.ndarray:
    """Cut off a near-black table/foreground strip below the track.

    Some photos frame the car high enough that the dark foreground falls inside
    the analysis band; it reads as a full-width "track" and drags the bbox down.
    Rails and trucks never fill more than about 60% of a row.
    """
    dark = (region < CROP.tone.track_thresh).mean(axis=1)
    rows = np.where(dark > CROP.rows.foreground_row_frac)[0]
    if rows.size and rows[0] > region.shape[0] * 0.3:
        # Walk up the smooth ramp where the backdrop edge fades into the table,
        # so it is not mistaken for rails. A ramp rises steadily; rails do not.
        smooth = np.convolve(dark, np.ones(9) / 9.0, mode="same")
        cut = int(rows[0])
        while cut > 0 and CROP.rows.track_row_frac / 2 < smooth[cut - 1] <= smooth[cut] + 0.005:
            cut -= 1
        return region[:cut]
    return region


def _span(flags: np.ndarray) -> tuple[int, int]:
    if not flags.any():
        return 0, 0
    lo = int(np.argmax(flags))
    hi = len(flags) - int(np.argmax(flags[::-1]))
    return lo, hi


def _body_top_row(band: np.ndarray) -> int:
    """First row with car body in the center band (stable vs handbrake headroom)."""
    Rh, W = band.shape
    center = band[:, int(0.22 * W) : int(0.78 * W)]
    rows = np.where((center < CROP.tone.body_thresh).mean(axis=1) > 0.02)[0]
    return int(rows[0]) if rows.size else max(0, int(Rh * 0.12))


def _runs_from_flags(flags: np.ndarray) -> list[tuple[int, int]]:
    """Contiguous True runs in a 1-D flag array."""
    runs: list[tuple[int, int]] = []
    start = None
    for c, flag in enumerate(flags):
        if flag and start is None:
            start = c
        elif not flag and start is not None:
            runs.append((start, c - 1))
            start = None
    if start is not None:
        runs.append((start, len(flags) - 1))
    return runs


def _merge_close_runs(
    runs: list[tuple[int, int]],
    max_gap: int,
) -> list[tuple[int, int]]:
    """Bridge short gaps between runs (e.g. light lettering on a dark car)."""
    if not runs:
        return []
    merged = [runs[0]]
    for lo, hi in runs[1:]:
        prev_lo, prev_hi = merged[-1]
        if lo - prev_hi <= max_gap:
            merged[-1] = (prev_lo, hi)
        else:
            merged.append((lo, hi))
    return merged


def _span_from_flags(flags: np.ndarray) -> tuple[int, int]:
    """Pick the car span: merge significant runs, else the run around frame center."""
    width = len(flags)
    if width < 2:
        return 0, max(0, width - 1)
    runs = _runs_from_flags(flags)
    if not runs:
        return 0, width - 1
    max_gap = max(12, int(width * CROP.span.run_merge_gap_frac))
    merged = _merge_close_runs(runs, max_gap)
    center = width // 2
    min_car = max(30, int(width * 0.06))
    significant = [span for span in merged if span[1] - span[0] >= min_car]
    if significant:
        lo = min(span[0] for span in significant)
        hi = max(span[1] for span in significant)
        if hi - lo <= width * CROP.span.body_span_max_frac:
            return lo, hi
    for lo, hi in merged:
        if lo <= center <= hi:
            return lo, hi
    lo, hi = max(merged, key=lambda span: span[1] - span[0])
    return lo, hi


def _sample_tone_levels(band: np.ndarray) -> tuple[float, float]:
    """Backdrop brightness vs car-body tone (body-anchored, not upper-band average)."""
    Rh, W = band.shape
    upper = band[: max(1, int(Rh * 0.42)), :]
    edge_med = float(np.median(upper[:, : max(5, int(W * 0.06))]))
    center = band[:, int(0.30 * W) : int(0.70 * W)]
    body_rows = np.where((center < CROP.tone.body_thresh).mean(axis=1) > 0.15)[0]
    if body_rows.size:
        car_med = float(
            np.median(
                band[
                    body_rows[0] : body_rows[-1] + 1,
                    int(0.30 * W) : int(0.70 * W),
                ]
            )
        )
    else:
        car_med = float(np.median(upper[:, int(0.35 * W) : int(0.65 * W)]))
    return edge_med, car_med


def _deck_fractions(band: np.ndarray) -> np.ndarray:
    """Deck lettering density per column, anchored on body top — not band fractions."""
    Rh, W = band.shape
    top = _body_top_row(band)
    car_h = max(24, Rh - top)
    y0 = top + int(car_h * 0.06)
    y1 = top + int(car_h * 0.34)
    y1 = max(y0 + 8, min(y1, Rh))
    deck = band[y0:y1, :]
    return (deck < CROP.tone.body_thresh).mean(axis=0)


def _deck_core_span(band: np.ndarray, deck_frac: np.ndarray) -> tuple[int, int]:
    """Horizontal extent of the car deck lettering band."""
    W = band.shape[1]
    sustain = max(12, int(W * CROP.span.deck_sustain_frac))
    lo = next(
        (
            c
            for c in range(W - sustain)
            if deck_frac[c : c + sustain].mean() > CROP.span.deck_core_thresh
            and deck_frac[c] > CROP.span.deck_edge_min
        ),
        0,
    )
    hi = next(
        (
            c
            for c in range(W - 1, sustain, -1)
            if deck_frac[c - sustain : c].mean() > CROP.span.deck_core_thresh
            and deck_frac[c] > CROP.span.deck_edge_min
        ),
        W - 1,
    )
    return lo, hi
