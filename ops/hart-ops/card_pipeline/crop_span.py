"""The car's horizontal span in its row band: body silhouette, couplers, crane arms, shadows.

``_horizontal_span`` is the entry point crop_car_image.detect_car_bbox calls; the rest are its
steps. Every threshold is in crop_settings.CROP.
"""

from __future__ import annotations

from typing import NamedTuple

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

Span = tuple[int, int]  # first and last column


class BodyRead(NamedTuple):
    """What the body-span steps read from one row band."""

    body_frac: np.ndarray  # per column, the share of mid-band pixels darker than the body threshold
    min_frac: float  # the share that marks a body column (light or dark car)
    umean: np.ndarray  # per column, the mean grey of the upper band
    edge_med: float  # backdrop grey at the band's left edge
    light_car: bool  # the car body is light grey or silver


def _rows(band: np.ndarray, rows: tuple[float, float]) -> np.ndarray:
    """The rows of ``band`` between two fractions of its height."""
    height = band.shape[0]
    return band[int(height * rows[0]) : int(height * rows[1]), :]


def _center_columns(values: np.ndarray, width: int) -> np.ndarray:
    """The car-body columns (CROP.top.center_band) of a per-column array."""
    a, b = CROP.top.center_band
    return values[int(a * width) : int(b * width)]


def _in_body_range(span: int, width: int) -> bool:
    """True when ``span`` is neither too narrow nor too wide to be the car body."""
    return width * CROP.span.body_span_min_frac <= span < width * CROP.span.body_span_max_frac


def _strong_horizontal_span(band: np.ndarray) -> Span:
    """Find left/right edges at the couplers, ignoring side vignette shadows."""
    Rh, W = band.shape
    upper = band[: max(1, int(Rh * CROP.rows.upper_body_frac)), :]
    lower = band[int(Rh * CROP.rows.lower_track_frac) :, :]
    umean = upper.mean(axis=0)
    lfrac = (lower < CROP.tone.track_thresh).mean(axis=0)

    strong = (lfrac > CROP.span.strong_lfrac) | (umean < CROP.tone.dark_body_mean)
    sustain = CROP.span.h_sustain_cols
    need = sustain - CROP.span.h_sustain_slack
    skip = CROP.span.strong_edge_skip

    lo = next(
        (c for c in range(skip, W // 2) if strong[c : c + sustain].sum() >= need),
        skip,
    )
    hi = next(
        (
            c
            for c in range(W - skip, W // 2, -1)
            if strong[c - sustain + 1 : c + 1].sum() >= need
        ),
        W - skip,
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
        if span >= width * CROP.span.widen_cap_min_frac and new_span > span * CROP.span.widen_span_max_ratio:
            return lo, hi, span
        return nlo, nhi, new_span
    return lo, hi, span


def _bridge_outboard_runs(
    body_frac: np.ndarray,
    min_frac: float,
    width: int,
) -> Span | None:
    """Bridge separated body runs (hopper end caps, locomotive hoods)."""
    gap_min = CROP.span.run_gap_min_px
    runs = _merge_close_runs(
        _runs_from_flags(body_frac > min_frac),
        max(gap_min, int(width * CROP.span.run_merge_gap_frac)),
    )
    significant = [
        span
        for span in runs
        if span[1] - span[0] >= max(CROP.span.run_min_px, int(width * CROP.span.run_min_frac))
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
    max_gap = max(gap_min, int(width * CROP.span.hopper_bridge_gap_frac))
    base_lo, base_hi = significant[idx]

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
        if _in_body_range(hi - lo, width):
            return lo, hi
    return None


def _clamp_truck_edges(
    lo: int,
    hi: int,
    lfrac: np.ndarray,
    width: int,
) -> Span:
    """Drop dead track past the outer truck axles (coal hoppers)."""
    strong = np.where(lfrac > CROP.span.truck_edge_lfrac)[0]
    if not strong.size:
        return lo, hi
    allow_hi = int(strong[-1]) + _coupler_reach(width)[1]
    if hi > allow_hi:
        hi = allow_hi
    return lo, hi


def _coupler_reach(width: int) -> Span:
    """(left, right) columns a coupler may sit past the body edge."""
    span = CROP.span
    return (
        max(span.coupler_reach_left_min_px, int(width * span.coupler_reach_left_frac)),
        max(span.coupler_reach_min_px, int(width * span.coupler_reach_frac)),
    )


def _coupler_tips_from_body(
    band: np.ndarray,
    body_lo: int,
    body_hi: int,
    lfrac: np.ndarray,
) -> Span:
    """Outer truck / coupler columns just outside the body silhouette."""
    W = band.shape[1]
    reach_l, reach_r = _coupler_reach(W)
    l_start = max(0, body_lo - reach_l)
    peak_thr = CROP.span.coupler_tip_lfrac

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


def _read_body(band: np.ndarray) -> BodyRead:
    """Body density per column, with the threshold chosen for a light or a dark car."""
    Rh = band.shape[0]
    upper = band[: max(1, int(Rh * CROP.rows.core_upper_frac)), :]
    mid = _rows(band, CROP.rows.mid_band)
    edge_med, car_med = _sample_tone_levels(band)
    light_car = car_med > CROP.tone.light_car_min
    if light_car:
        margin = CROP.tone.light_body_margin
        thresh = min(car_med + margin, edge_med - margin)
        min_frac = CROP.span.light_body_min_frac
    else:
        thresh = CROP.tone.body_thresh
        min_frac = CROP.span.dark_body_min_frac
    return BodyRead(
        body_frac=(mid < thresh).mean(axis=0),
        min_frac=min_frac,
        umean=upper.mean(axis=0),
        edge_med=edge_med,
        light_car=light_car,
    )


def _umean_cut_span(umean: np.ndarray, width: int, pctile: int, pad: int) -> Span:
    """Columns whose upper-band mean is darker than a percentile of the centre columns plus ``pad``."""
    t = float(np.percentile(_center_columns(umean, width), pctile)) + pad
    return _span_from_flags(umean < t)


def _tighter_body_span(body_frac: np.ndarray, span: int, width: int) -> Span | None:
    """Too wide: the first denser body rule whose span is narrower and still wide enough."""
    for frac in CROP.span.tighter_body_fracs:
        nlo, nhi = _span_from_flags(body_frac > frac)
        nspan = nhi - nlo
        if nspan < span and nspan >= width * CROP.span.body_span_min_frac:
            return nlo, nhi
    return None


def _deck_lettering_span(band: np.ndarray, width: int) -> Span | None:
    """Too wide: the first deck-lettering density whose span is in the body range."""
    deck_frac = _deck_fractions(band)
    for deck_thr in CROP.span.deck_fallback_fracs:
        dlo, dhi = _span_from_flags(deck_frac > deck_thr)
        if _in_body_range(dhi - dlo, width):
            return dlo, dhi
    return None


def _narrow_wide_span(band: np.ndarray, read: BodyRead, lo: int, hi: int) -> tuple[int, int, bool]:
    """Narrow a span wider than body_span_max_frac: denser body, deck lettering, then upper-band mean.

    The bool is True when the upper-band mean set the span; the narrow-span steps then leave it.
    """
    W = band.shape[1]
    too_wide = W * CROP.span.body_span_max_frac
    if hi - lo > too_wide:
        hit = _tighter_body_span(read.body_frac, hi - lo, W)
        if hit:
            lo, hi = hit
    if hi - lo > too_wide:
        hit = _deck_lettering_span(band, W)
        if hit:
            lo, hi = hit
    if hi - lo > too_wide:
        ulo, uhi = _umean_cut_span(read.umean, W, CROP.tone.wide_umean_pctile, CROP.tone.wide_umean_pad)
        if _in_body_range(uhi - ulo, W):
            return ulo, uhi, True
    return lo, hi, False


def _widen_narrow_span(band: np.ndarray, read: BodyRead, lo: int, hi: int, used_umean: bool) -> Span:
    """Widen a span narrower than body_span_min_frac, step by step, unless the silhouette is trusted.

    Steps in order: deck-lettering core, bridged body runs, edge-relative upper-band mean,
    full-height dark columns, and for light cars a high upper-band percentile.
    """
    W = band.shape[1]
    span = hi - lo
    too_narrow = W * CROP.span.body_span_min_frac
    trust_silhouette = span >= W * CROP.span.silhouette_trust_frac

    if span < too_narrow and not used_umean:
        lo2, hi2 = _deck_core_span(band, _deck_fractions(band))
        lo, hi, span = _maybe_widen_span(lo, hi, span, lo2, hi2, W)

    bridge_below = W * (CROP.span.body_span_min_frac - CROP.span.bridge_span_slack)
    if span < bridge_below and not used_umean and not trust_silhouette:
        bridged = _bridge_outboard_runs(read.body_frac, read.min_frac, W)
        if bridged:
            lo, hi = bridged
            span = hi - lo

    if trust_silhouette:
        return lo, hi

    if span < too_narrow:
        lo_e, hi_e = _span_from_flags(read.umean < read.edge_med - CROP.tone.edge_umean_delta)
        lo, hi, span = _maybe_widen_span(lo, hi, span, lo_e, hi_e, W)

    if span < too_narrow:
        dark_frac = (band < CROP.tone.body_thresh).mean(axis=0)
        lo_d, hi_d = _span_from_flags(dark_frac > CROP.span.full_dark_frac)
        lo, hi, span = _maybe_widen_span(lo, hi, span, lo_d, hi_d, W)

    if span < too_narrow and read.light_car:
        lo_p, hi_p = _umean_cut_span(read.umean, W, CROP.tone.light_umean_pctile, CROP.tone.light_umean_pad)
        lo, hi, span = _maybe_widen_span(lo, hi, span, lo_p, hi_p, W)

    return lo, hi


def _core_body_span(band: np.ndarray) -> Span:
    """Rolling-stock silhouette — works for dark, light-gray, and silver cars."""
    read = _read_body(band)
    lo, hi = _span_from_flags(read.body_frac > read.min_frac)
    lo, hi, used_umean = _narrow_wide_span(band, read, lo, hi)
    return _widen_narrow_span(band, read, lo, hi, used_umean)


def _extend_to_couplers(
    band: np.ndarray,
    lo: int,
    hi: int,
    lfrac: np.ndarray,
) -> Span:
    """Include couplers / truck ends just outside the body silhouette."""
    W = band.shape[1]
    reach_l, reach_r = _coupler_reach(W)
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
) -> Span:
    """Drop track-only columns outside the rolling stock (dead space past couplers)."""
    W = band.shape[1]
    span = CROP.span
    max_peel = max(span.track_peel_min_px, int(W * span.track_peel_max_frac))

    def bare(c: int) -> bool:
        return deck_frac[c] < span.peel_deck_max and ufrac[c] < span.peel_upper_max and lfrac[c] > span.peel_lfrac_min

    peeled = 0
    # Left end only: trucks and couplers read darker than bare rail stubs.
    while lo < hi and peeled < max_peel and bare(lo) and lfrac[lo] < span.track_peel_lfrac_max:
        lo += 1
        peeled += 1
    peeled = 0
    while hi > lo and peeled < max_peel and bare(hi):
        hi -= 1
        peeled += 1
    return lo, hi


def _extend_crane_arms(
    band: np.ndarray,
    lo: int,
    hi: int,
    body_frac: np.ndarray,
    anchor_lo: int | None = None,
    anchor_hi: int | None = None,
) -> Span:
    """Include crane booms / high outboard gear that sit above the deck line."""
    W = band.shape[1]
    span = CROP.span
    crane = _rows(band, CROP.rows.crane_band)
    reach = max(span.crane_reach_min_px, int(W * span.crane_reach_frac))
    min_lo = max(0, (anchor_lo if anchor_lo is not None else lo) - reach)
    max_hi = min(W - 1, (anchor_hi if anchor_hi is not None else hi) + reach)

    def boom(c: int) -> bool:
        return bool(body_frac[c] < span.crane_body_max and (crane[:, c] < CROP.tone.body_thresh).mean() > span.crane_dark_min)

    for c in range(lo - 1, min_lo - 1, -1):
        if boom(c):
            lo = c
    for c in range(hi + 1, max_hi + 1):
        if boom(c):
            hi = c
    return lo, hi


def _horizontal_span(band: np.ndarray) -> Span:
    """Rolling stock only — couplers included, track stubs and corner shadows dropped."""
    Rh, W = band.shape
    mid = _rows(band, CROP.rows.mid_band)
    lower = band[int(Rh * CROP.rows.coupler_track_frac) :, :]
    upper = band[: max(1, int(Rh * CROP.rows.upper_body_frac)), :]
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


def _shrink_shadow_edges(band: np.ndarray, lo: int, hi: int) -> Span:
    """Drop side vignette columns that have no car above the track."""
    Rh = band.shape[0]
    upper = band[: max(1, int(Rh * CROP.rows.upper_body_frac)), :].mean(axis=0)
    lower = band[int(Rh * CROP.rows.lower_track_frac) :, :]
    lfrac = (lower < CROP.tone.track_thresh).mean(axis=0)
    weak_frac = CROP.span.shadow_track_min

    while lo < hi and upper[lo] > CROP.tone.edge_shadow_mean and lfrac[lo] < weak_frac:
        lo += 1
    while hi > lo and upper[hi] > CROP.tone.edge_shadow_mean and lfrac[hi] < weak_frac:
        hi -= 1
    return lo, hi
