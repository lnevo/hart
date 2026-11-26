#!/usr/bin/env python3
"""Crop a model-car photo tight to the rolling stock.

Detects the car against the light-box background (works for dark and light-gray
rolling stock) and crops to the couplers with minimal padding. Pixels are left
untouched — no color or backdrop adjustments.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from crop_settings import CROP  # noqa: E402  (a sibling module, on sys.path with this one)


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


def _trim_shadow_columns(band: np.ndarray) -> tuple[int, int]:
    """Drop backdrop corners: flat gray strips and dark vignette wedges."""
    H, W = band.shape
    if H < 4 or W < 4:
        return 0, W
    upper = band[: max(1, int(H * 0.45)), :]
    top = band[: max(1, H // 2), :]
    col_std = top.std(axis=0)
    col_range = top.max(axis=0) - top.min(axis=0)
    flat = (col_std < 15) & (col_range < 45)
    wedge = (upper < CROP.tone.body_thresh).mean(axis=0) > CROP.span.shadow_wedge_frac
    col_body = (band < CROP.tone.body_thresh).mean(axis=0) < 0.10

    lo = 0
    for c in range(W):
        if flat[c] or (wedge[c] and col_body[c]):
            lo = c + 1
        else:
            break
    hi = W
    for c in range(W - 1, -1, -1):
        if flat[c] or (wedge[c] and col_body[c]):
            hi = c
        else:
            break
    if hi - lo < W * 0.30:
        return 0, W
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


def _largest_run(flags: np.ndarray) -> tuple[int, int]:
    """Return the longest contiguous True run in a 1-D flag array."""
    best = (0, 0, 0)
    start = None
    for c, flag in enumerate(flags):
        if flag and start is None:
            start = c
        elif not flag and start is not None:
            if c - start > best[2]:
                best = (start, c - 1, c - start)
            start = None
    if start is not None and len(flags) - start > best[2]:
        best = (start, len(flags) - 1, len(flags) - start)
    return best[0], best[1]


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


def _strong_horizontal_span(band: np.ndarray) -> tuple[int, int]:
    """Find left/right edges at the couplers, ignoring side vignette shadows."""
    Rh, W = band.shape
    upper = band[: max(1, int(Rh * CROP.rows.upper_body_frac)), :]
    lower = band[int(Rh * CROP.rows.lower_track_frac) :, :]
    umean = upper.mean(axis=0)
    lfrac = (lower < CROP.tone.track_thresh).mean(axis=0)

    strong = (lfrac > CROP.span.strong_lfrac) | (umean < CROP.tone.dark_body_mean)
    sustain = CROP.span.h_sustain_cols
    need = sustain - 2

    lo = next(
        (c for c in range(30, W // 2) if strong[c : c + sustain].sum() >= need),
        30,
    )
    hi = next(
        (
            c
            for c in range(W - 30, W // 2, -1)
            if strong[c - sustain + 1 : c + 1].sum() >= need
        ),
        W - 30,
    )
    return _shrink_shadow_edges(band, lo, hi)


def _maybe_widen_span(
    lo: int,
    hi: int,
    span: int,
    nlo: int,
    nhi: int,
    width: int,
) -> tuple[int, int, int]:
    """Adopt a wider candidate span only if it beats the current span and is not too wide."""
    new_span = nhi - nlo
    if new_span > span and new_span < width * CROP.span.body_span_max_frac:
        if span >= width * 0.25 and new_span > span * CROP.span.widen_span_max_ratio:
            return lo, hi, span
        return nlo, nhi, new_span
    return lo, hi, span


def _bridge_outboard_runs(
    body_frac: np.ndarray,
    min_frac: float,
    width: int,
) -> tuple[int, int] | None:
    """Bridge separated body runs (hopper end caps, locomotive hoods)."""
    runs = _merge_close_runs(
        _runs_from_flags(body_frac > min_frac),
        max(12, int(width * CROP.span.run_merge_gap_frac)),
    )
    significant = [
        span
        for span in runs
        if span[1] - span[0] >= max(30, int(width * 0.025))
    ]
    if not significant:
        return None
    center = width // 2
    idx = next(
        (i for i, span in enumerate(significant) if span[0] <= center <= span[1]),
        None,
    )
    if idx is None:
        return None
    max_gap = max(12, int(width * CROP.span.hopper_bridge_gap_frac))
    base_lo, base_hi = significant[idx]

    def _valid(lo: int, hi: int) -> tuple[int, int] | None:
        span = hi - lo
        if width * CROP.span.body_span_min_frac <= span < width * CROP.span.body_span_max_frac:
            return lo, hi
        return None

    # Left-only before right-only: loco hoods vs hopper end caps.
    for bridge_left, bridge_right in ((True, False), (False, True), (True, True)):
        lo, hi = base_lo, base_hi
        if bridge_right:
            for j in range(idx + 1, len(significant)):
                nlo, nhi = significant[j]
                if nlo - hi <= max_gap:
                    hi = nhi
                else:
                    break
        if bridge_left:
            for j in range(idx - 1, -1, -1):
                nlo, nhi = significant[j]
                if lo - nhi <= max_gap:
                    lo = nlo
                else:
                    break
        hit = _valid(lo, hi)
        if hit:
            return hit
    return None


def _clamp_truck_edges(
    lo: int,
    hi: int,
    lfrac: np.ndarray,
    width: int,
) -> tuple[int, int]:
    """Drop dead track past the outer truck axles (coal hoppers)."""
    strong = np.where(lfrac > CROP.span.truck_edge_lfrac)[0]
    if not strong.size:
        return lo, hi
    reach_r = max(40, int(width * CROP.span.coupler_reach_frac))
    allow_hi = int(strong[-1]) + reach_r
    if hi > allow_hi:
        hi = allow_hi
    return lo, hi


def _coupler_tips_from_body(
    band: np.ndarray,
    body_lo: int,
    body_hi: int,
    lfrac: np.ndarray,
) -> tuple[int, int]:
    """Outer truck / coupler columns just outside the body silhouette."""
    W = band.shape[1]
    reach_l = max(50, int(W * CROP.span.coupler_reach_left_frac))
    reach_r = max(40, int(W * CROP.span.coupler_reach_frac))
    l_start = max(0, body_lo - reach_l)
    peak_thr = 0.22

    left_tip = body_lo
    for c in range(body_lo, l_start - 1, -1):
        if lfrac[c] >= peak_thr:
            left_tip = c
            break

    r_end = min(W, body_hi + reach_r + 1)
    right_tip = body_hi
    for c in range(body_hi, r_end):
        if lfrac[c] >= peak_thr:
            right_tip = c
            break

    return left_tip, right_tip


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


def _core_body_span(band: np.ndarray) -> tuple[int, int]:
    """Rolling-stock silhouette — works for dark, light-gray, and silver cars."""
    Rh, W = band.shape
    upper = band[: max(1, int(Rh * 0.42)), :]
    mid = band[int(Rh * 0.10) : int(Rh * 0.55), :]
    edge_med, car_med = _sample_tone_levels(band)
    umean = upper.mean(axis=0)

    if car_med > 100:
        thresh = min(car_med + 12, edge_med - 12)
        min_frac = CROP.span.light_body_min_frac
    else:
        thresh = CROP.tone.body_thresh
        min_frac = CROP.span.dark_body_min_frac

    body_frac = (mid < thresh).mean(axis=0)
    lo, hi = _span_from_flags(body_frac > min_frac)
    span = hi - lo
    used_umean = False

    if span > W * CROP.span.body_span_max_frac:
        for tighter_frac in (0.5, 0.55, 0.6):
            nlo, nhi = _span_from_flags(body_frac > tighter_frac)
            nspan = nhi - nlo
            if nspan < span and nspan >= W * CROP.span.body_span_min_frac:
                lo, hi = nlo, nhi
                span = nspan
                break
        if span > W * CROP.span.body_span_max_frac:
            deck_frac = _deck_fractions(band)
            for deck_thr in (0.45, 0.4, 0.35):
                dlo, dhi = _span_from_flags(deck_frac > deck_thr)
                dspan = dhi - dlo
                if W * CROP.span.body_span_min_frac <= dspan < W * CROP.span.body_span_max_frac:
                    lo, hi = dlo, dhi
                    span = dspan
                    break
        if span > W * CROP.span.body_span_max_frac:
            center_u = umean[int(0.25 * W) : int(0.75 * W)]
            t = float(np.percentile(center_u, 30)) + 8
            ulo, uhi = _span_from_flags(umean < t)
            uspan = uhi - ulo
            if W * CROP.span.body_span_min_frac <= uspan < W * CROP.span.body_span_max_frac:
                lo, hi = ulo, uhi
                span = uspan
                used_umean = True

    trust_silhouette = span >= W * CROP.span.silhouette_trust_frac

    if span < W * CROP.span.body_span_min_frac and not used_umean:
        deck_frac = _deck_fractions(band)
        lo2, hi2 = _deck_core_span(band, deck_frac)
        lo, hi, span = _maybe_widen_span(lo, hi, span, lo2, hi2, W)

    if (
        span < W * (CROP.span.body_span_min_frac - 0.03)
        and not used_umean
        and not trust_silhouette
    ):
        bridged = _bridge_outboard_runs(body_frac, min_frac, W)
        if bridged:
            lo, hi = bridged
            span = hi - lo

    if span < W * CROP.span.body_span_min_frac and not trust_silhouette:
        lo_e, hi_e = _span_from_flags(umean < edge_med - CROP.tone.edge_umean_delta)
        lo, hi, span = _maybe_widen_span(lo, hi, span, lo_e, hi_e, W)

    if span < W * CROP.span.body_span_min_frac and not trust_silhouette:
        dark_frac = (band < CROP.tone.body_thresh).mean(axis=0)
        lo_d, hi_d = _span_from_flags(dark_frac > CROP.span.full_dark_frac)
        lo, hi, span = _maybe_widen_span(lo, hi, span, lo_d, hi_d, W)

    if span < W * CROP.span.body_span_min_frac and car_med > 100 and not trust_silhouette:
        center_u = umean[int(0.25 * W) : int(0.75 * W)]
        t = float(np.percentile(center_u, CROP.tone.light_umean_pctile)) + CROP.tone.light_umean_pad
        lo_p, hi_p = _span_from_flags(umean < t)
        lo, hi, span = _maybe_widen_span(lo, hi, span, lo_p, hi_p, W)

    return lo, hi


def _extend_to_couplers(
    band: np.ndarray,
    lo: int,
    hi: int,
    lfrac: np.ndarray,
) -> tuple[int, int]:
    """Include couplers / truck ends just outside the body silhouette."""
    W = band.shape[1]
    reach_l = max(50, int(W * CROP.span.coupler_reach_left_frac))
    reach_r = max(40, int(W * CROP.span.coupler_reach_frac))
    for c in range(lo - 1, max(0, lo - reach_l), -1):
        if lfrac[c] > CROP.span.coupler_lfrac:
            lo = c
        else:
            break
    for c in range(hi + 1, min(W, hi + reach_r + 1)):
        if lfrac[c] > CROP.span.coupler_lfrac:
            hi = c
        else:
            break
    return max(0, lo), min(W - 1, hi)


def _peel_bare_track(
    band: np.ndarray,
    lo: int,
    hi: int,
    deck_frac: np.ndarray,
    lfrac: np.ndarray,
    ufrac: np.ndarray,
) -> tuple[int, int]:
    """Drop track-only columns outside the rolling stock (dead space past couplers)."""
    W = band.shape[1]
    max_peel = max(50, int(W * CROP.span.track_peel_max_frac))
    peeled = 0
    while lo < hi and peeled < max_peel:
        if (
            deck_frac[lo] < 0.12
            and ufrac[lo] < 0.04
            and 0.08 < lfrac[lo] < CROP.span.track_peel_lfrac_max
        ):
            lo += 1
            peeled += 1
        else:
            break
    peeled = 0
    while hi > lo and peeled < max_peel:
        if (
            deck_frac[hi] < 0.12
            and ufrac[hi] < 0.04
            and lfrac[hi] > 0.08
        ):
            hi -= 1
            peeled += 1
        else:
            break
    return lo, hi


def _extend_crane_arms(
    band: np.ndarray,
    lo: int,
    hi: int,
    body_frac: np.ndarray,
    anchor_lo: int | None = None,
    anchor_hi: int | None = None,
) -> tuple[int, int]:
    """Include crane booms / high outboard gear that sit above the deck line."""
    Rh, W = band.shape
    mid = band[int(Rh * 0.10) : int(Rh * 0.50), :]
    reach = max(50, int(W * CROP.span.crane_reach_frac))
    min_lo = max(0, (anchor_lo if anchor_lo is not None else lo) - reach)
    max_hi = min(W - 1, (anchor_hi if anchor_hi is not None else hi) + reach)
    for c in range(lo - 1, min_lo - 1, -1):
        if body_frac[c] < 0.10 and (mid[:, c] < CROP.tone.body_thresh).mean() > 0.05:
            lo = c
    for c in range(hi + 1, max_hi + 1):
        if body_frac[c] < 0.10 and (mid[:, c] < CROP.tone.body_thresh).mean() > 0.05:
            hi = c
    return lo, hi


def _horizontal_span(band: np.ndarray) -> tuple[int, int]:
    """Rolling stock only — couplers included, track stubs and corner shadows dropped."""
    Rh, W = band.shape
    mid = band[int(Rh * 0.10) : int(Rh * 0.55), :]
    lower = band[int(Rh * 0.62) :, :]
    upper = band[: max(1, int(Rh * 0.38)), :]
    lfrac = (lower < CROP.tone.track_thresh).mean(axis=0)
    ufrac = (upper < CROP.tone.body_thresh).mean(axis=0)
    body_frac = (mid < CROP.tone.body_thresh).mean(axis=0)

    body_lo, body_hi = _core_body_span(band)
    body_span = body_hi - body_lo
    if body_span < W * CROP.span.silhouette_trust_frac:
        lo, hi = _strong_horizontal_span(band)
        return _shrink_shadow_edges(band, lo, hi)

    lo, hi = _coupler_tips_from_body(band, body_lo, body_hi, lfrac)
    tip_lo, tip_hi = lo, hi

    if body_span < W * CROP.span.small_car_span_frac:
        lo_ext, _ = _extend_to_couplers(band, body_lo, body_hi, lfrac)
        lo = min(lo, lo_ext)
        lo, hi = _peel_bare_track(band, lo, hi, body_frac, lfrac, ufrac)

    lo, hi = _clamp_truck_edges(lo, hi, lfrac, W)
    lo, hi = _extend_crane_arms(
        band, lo, hi, body_frac, anchor_lo=tip_lo, anchor_hi=tip_hi
    )
    lo, hi = _peel_bare_track(band, lo, hi, body_frac, lfrac, ufrac)
    return _shrink_shadow_edges(band, lo, hi)


def _shrink_shadow_edges(band: np.ndarray, lo: int, hi: int) -> tuple[int, int]:
    """Drop side vignette columns that have no car above the track."""
    Rh, _W = band.shape
    upper = band[: max(1, int(Rh * CROP.rows.upper_body_frac)), :].mean(axis=0)
    lower = band[int(Rh * CROP.rows.lower_track_frac) :, :]
    lfrac = (lower < CROP.tone.track_thresh).mean(axis=0)
    weak_frac = 0.08

    while lo < hi and upper[lo] > CROP.tone.edge_shadow_mean and lfrac[lo] < weak_frac:
        lo += 1
    while hi > lo and upper[hi] > CROP.tone.edge_shadow_mean and lfrac[hi] < weak_frac:
        hi -= 1
    return lo, hi


def detect_car_bbox(img: Image.Image) -> tuple[int, int, int, int]:
    """Locate the car by anchoring on the track, then growing through the body."""
    g = np.asarray(ImageOps.grayscale(img), dtype=np.uint8)
    H, W = g.shape
    y0, y1 = int(CROP.frame.y0 * H), int(CROP.frame.y1 * H)
    region = _trim_foreground(g[y0:y1, :])
    y1 = y0 + region.shape[0]
    Rh, Rw = region.shape

    content = region < CROP.tone.content_thresh
    dark = region < CROP.tone.track_thresh
    row_dark = dark.mean(axis=1)

    if (row_dark > CROP.rows.track_row_frac).any():
        _, ry1 = _span(row_dark > CROP.rows.track_row_frac)
        # Top edge: center car body, extended upward only for a left-end handbrake
        # (skip the extreme-left 8% where studio-flag wedges live).
        center = region[:, int(0.25 * Rw) : int(0.75 * Rw)]
        left_skip = region[:, int(0.08 * Rw) : int(0.32 * Rw)]
        c_rows = np.where((center < CROP.tone.body_thresh).mean(axis=1) > 0.02)[0]
        l_rows = np.where((left_skip < CROP.tone.body_thresh).mean(axis=1) > 0.015)[0]
        if c_rows.any():
            ry0_c = int(c_rows[0])
            ry0 = ry0_c
            if l_rows.any():
                ry0_l = int(l_rows[0])
                if ry0_l < ry0_c:
                    extreme_at_l = (
                        region[ry0_l, : int(0.08 * Rw)] < CROP.tone.body_thresh
                    ).mean()
                    if extreme_at_l < 0.08:
                        ry0 = ry0_l
            # Walk up from the deck for a left-end handbrake staff / wheel.
            hband = region[:, int(0.10 * Rw) : int(0.20 * Rw)]
            for r in range(ry0_c - 1, -1, -1):
                extreme_frac = (
                    region[r, : int(0.08 * Rw)] < CROP.tone.body_thresh
                ).mean()
                hb_frac = (hband[r] < CROP.tone.body_thresh).mean()
                c_frac = (center[r] < CROP.tone.body_thresh).mean()
                if extreme_frac > 0.10:
                    break
                if (
                    0.04 < hb_frac < 0.12
                    and c_frac < 0.01
                    and extreme_frac < 0.08
                ):
                    ry0 = min(ry0, r)
                elif c_frac > 0.02 and hb_frac < 0.05:
                    break
            expand = int((ry1 - ry0) * CROP.frame.row_expand_up)
            ry0 = max(0, ry0 - expand)
            # Gondola covers, cab roofs, roofwalks above the deck line.
            roof_limit = max(0, ry0_c - int((ry1 - ry0_c) * 0.22))
            for r in range(ry0_c - 1, roof_limit - 1, -1):
                row = center[r]
                if (row < CROP.tone.body_thresh).mean() > 0.06 or float(row.std()) > 18:
                    ry0 = min(ry0, r)
                elif r < ry0_c - int((ry1 - ry0_c) * 0.06):
                    break
        else:
            ry0, _ = _span(row_dark > CROP.rows.track_row_frac)
    else:
        ry0, ry1 = _span(content.mean(axis=1) > CROP.rows.content_row_frac)

    if ry1 <= ry0:
        return 0, y0, W, y1

    row_band = region[ry0:ry1, :]
    # Horizontal span already peels corner shadows; pre-trim here can clip
    # outboard coupler ends on split flatcars (e.g. IMG_9149).
    cx0, cx1 = _horizontal_span(row_band)
    bx0, bx1 = cx0, cx1

    by0 = y0 + ry0
    by1 = y0 + ry1

    ch = by1 - by0
    by1 += int(ch * 0.02)
    by0 -= int(ch * 0.02)

    return (max(0, bx0), max(0, by0), min(W, bx1), min(H, by1))


def _backdrop_color(img: Image.Image) -> tuple[int, ...]:
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


def _visual_car_center_x(gray: np.ndarray) -> float:
    """Horizontal center of the car body silhouette (not the detection bbox)."""
    H, W = gray.shape
    mid = gray[int(H * 0.30) : int(H * 0.70), :]
    body = (mid < CROP.tone.body_thresh).mean(axis=0)
    cols = np.where(body > 0.12)[0]
    if not cols.size:
        return W / 2.0
    lo, hi = int(cols[0]), int(cols[-1])
    weights = body[lo : hi + 1]
    if weights.sum() > 0:
        return float(lo + np.average(np.arange(lo, hi + 1), weights=weights))
    return (lo + hi) / 2.0


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


def _visual_car_center_x_in_crop(gray: np.ndarray) -> float:
    """Horizontal body centroid for an already-cropped car photo."""
    return _visual_car_center_x(gray)


def recenter_crop_image(crop_img: Image.Image) -> Image.Image:
    """Shift a crop horizontally so the car body sits on the image center."""
    gray = np.asarray(ImageOps.grayscale(crop_img), dtype=np.uint8)
    W, H = gray.shape[1], gray.shape[0]
    car_cx = _visual_car_center_x_in_crop(gray)
    shift = int(round(W / 2.0 - car_cx))
    if shift == 0:
        return crop_img.copy()

    fill = _backdrop_color(crop_img)
    canvas = Image.new(crop_img.mode, (W, H), fill)
    canvas.paste(crop_img, (shift, 0))
    return canvas


def process_image_at_size(
    src: Path,
    target_size: tuple[int, int],
    dst: Path | None = None,
) -> dict:
    """Re-crop a source photo to exact dimensions, centered on the car body."""
    target_w, target_h = target_size
    img = Image.open(src)
    img, rotation = _level_image(img)
    gray = np.asarray(ImageOps.grayscale(img), dtype=np.uint8)

    bx0, by0, bx1, by1 = detect_car_bbox(img)
    center_x = _visual_car_center_x(gray)
    center_y = (by0 + by1) / 2.0
    canvas = _crop_at_fixed_size(img, center_x, center_y, target_w, target_h)

    if dst is not None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(dst)

    return {
        "source": src.name,
        "bbox": (bx0, by0, bx1, by1),
        "center_x": center_x,
        "center_y": center_y,
        "output_size": (target_w, target_h),
        "ratio": target_w / max(target_h, 1),
        "rotation_deg": rotation,
        "image": canvas,
    }


def assess_crop(bbox: tuple[int, int, int, int], img_size: tuple[int, int]) -> str:
    W, H = img_size
    x0, y0, x1, y1 = bbox
    cw, ch = x1 - x0, y1 - y0
    if cw < 0.20 * W or ch < 0.12 * H:
        return "review"
    return "ok"


def process_image(src: Path, dst: Path | None = None) -> dict:
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


def main():
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
