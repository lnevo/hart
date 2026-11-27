"""The car's horizontal span in its row band: body silhouette, couplers, crane arms, shadows.

``_horizontal_span`` is the entry point crop_car_image.detect_car_bbox calls; the rest are its
steps. Every threshold is in crop_settings.CROP.
"""

from __future__ import annotations

import numpy as np

from crop_runs import (  # sibling modules, on sys.path with this one
    _deck_core_span,
    _deck_fractions,
    _merge_close_runs,
    _runs_from_flags,
    _sample_tone_levels,
    _span_from_flags,
)
from crop_settings import CROP


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
