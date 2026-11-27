"""Tuned values for crop_car_image: framing, grey levels, row bands and span rules.

Each value was tuned on the fleet's light-box photos; ``CROP`` is the one instance the
detection reads. Fractions are of the image (or analysis band) width or height.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FrameSettings:
    """Framing: the search window, side and top/bottom padding, and levelling."""

    y0: float = 0.36  # top of the vertical search window, as a fraction of the height
    y1: float = 0.90  # bottom of the vertical search window
    tie_margin_count: float = 4.25  # railroad ties visible past each coupler tip
    tie_pitch_min: int = 12
    tie_pitch_max: int = 55
    long_car_min_frac: float = 0.60  # locomotives / long flats — tighter side margin
    long_car_pad_x: float = 0.027  # matches IMG_9185_cropped.jpg (~60 px each side)
    pad_top: float = 0.03  # headroom for roofwalk / gondola covers / cab roofs
    pad_bottom: float = 0.02  # slight margin below trucks
    row_expand_up: float = 0.03  # small extra headroom after body-top detection
    min_rotation_deg: float = 0.05
    tie_pitch_smooth: int = 5  # columns in the moving average over the track strip
    tie_peak_min: float = 0.12  # a tie column is at least this dark
    tie_peaks_min_count: int = 4  # fewer tie peaks than this: the pitch comes from the car width alone
    ties_per_car_width: float = 52.0  # car width / this is the width-based pitch
    tie_pitch_width_range: tuple[float, float] = (18.0, 40.0)  # clip of the width-based pitch
    tie_pitch_floor_share: float = 0.82  # the peak/width blend is at least this share of the width pitch
    tie_strip_top: float = 0.62  # the tie strip starts this far down the car box
    tie_strip_below: float = 0.08  # and ends this far below it (shares of the box height)
    pad_x_min_px: int = 8  # side padding floor
    recentre_slack_px: int = 2  # a re-centred crop may lose this much width
    review_min_w: float = 0.20  # a car box narrower than this share of the width is flagged for review
    review_min_h: float = 0.12  # or lower than this share of the height


@dataclass(frozen=True)
class ToneSettings:
    """Grey levels that separate the light-box wall, light cars, dark bodies and track."""

    content_thresh: int = 238  # not blown-out white; the wall reads about 180-210, light-grey cars 220 and up
    track_thresh: int = 95  # rails / trucks / dark car bodies
    body_thresh: int = 120  # car body / handbrake — ignores gray studio-flag wedges
    dark_body_mean: int = 130
    edge_shadow_mean: int = 145
    fleet_lightbox_wall: tuple[float, float, float] = (212.8, 208.8, 203.8)  # mean light-box wall RGB from a representative fleet sample (neutral grey)
    edge_umean_delta: int = 3  # edge-relative umean fallback
    light_umean_pctile: int = 45  # high-percentile umean for near-backdrop cars
    light_umean_pad: int = 5
    light_car_min: int = 100  # car-sample median above this is a light car
    light_body_margin: int = 12  # light-car body threshold: car median + this, at most edge median - this
    wide_umean_pctile: int = 30  # too-wide fallback: upper-band mean percentile in the centre columns ...
    wide_umean_pad: int = 8  # ... plus this


@dataclass(frozen=True)
class RowSettings:
    """Row bands and the share of a row that counts as track, table or content."""

    track_row_frac: float = 0.04
    foreground_row_frac: float = 0.85  # row this dark across is table, not track
    content_row_frac: float = 0.06
    upper_body_frac: float = 0.38
    lower_track_frac: float = 0.52
    core_upper_frac: float = 0.42  # body span: the upper band whose column mean feeds the umean fallbacks
    mid_band: tuple[float, float] = (0.10, 0.55)  # body span: rows where the body silhouette is read
    crane_band: tuple[float, float] = (0.10, 0.50)  # rows where crane booms are looked for
    coupler_track_frac: float = 0.62  # coupler and peel steps: track rows start here


@dataclass(frozen=True)
class SpanSettings:
    """Horizontal span: body runs, deck lettering, couplers and the fallbacks between them."""

    strong_lfrac: float = 0.12
    h_sustain_cols: int = 12
    h_sustain_slack: int = 2  # columns of a sustained run that may be weak
    strong_edge_skip: int = 30  # columns at each side the strong-span search skips (vignette)
    deck_sustain_frac: float = 0.006
    deck_core_thresh: float = 0.40  # sustained deck-lettering density
    deck_edge_min: float = 0.20  # per-column floor at span edges
    coupler_lfrac: float = 0.15  # truck / coupler signal in lower band
    coupler_reach_frac: float = 0.05  # max outward reach past deck for couplers (right)
    coupler_reach_left_frac: float = 0.055  # left end — body edge to coupler tip
    coupler_reach_min_px: int = 40  # floor of the right reach
    coupler_reach_left_min_px: int = 50  # floor of the left reach
    coupler_tip_lfrac: float = 0.22  # a coupler-tip column is at least this dark in the lower band
    run_merge_gap_frac: float = 0.04  # merge body runs separated by lettering gaps
    run_gap_min_px: int = 12  # floor of the merge gap and of the bridge gap
    run_min_px: int = 30  # a body run shorter than this (or run_min_frac) is noise
    run_min_frac: float = 0.025
    hopper_bridge_gap_frac: float = 0.25  # hopper slopes / loco hood gaps in the mid-band
    widen_span_max_ratio: float = 1.35  # cap full-height dark fallback vs body silhouette
    widen_cap_min_frac: float = 0.25  # the ratio cap applies once the current span is this wide
    truck_edge_lfrac: float = 0.35  # truck axle darkness for right-edge clamp
    track_peel_max_frac: float = 0.08  # max peel of bare track past couplers
    track_peel_lfrac_max: float = 0.35  # trucks/couplers read darker than bare rail stubs
    track_peel_min_px: int = 50  # floor of the peel
    peel_deck_max: float = 0.12  # a bare-track column has less body than this in the mid band ...
    peel_upper_max: float = 0.04  # ... less than this in the upper band ...
    peel_lfrac_min: float = 0.08  # ... and at least this much rail in the lower band
    crane_reach_frac: float = 0.045  # extend for crane booms past the deck
    crane_reach_min_px: int = 50  # floor of the crane reach
    crane_body_max: float = 0.10  # a boom column has less mid-band body than this ...
    crane_dark_min: float = 0.05  # ... and more dark crane-band pixels than this
    body_span_min_frac: float = 0.35  # deck fallback when silhouette span is too narrow
    bridge_span_slack: float = 0.03  # runs are bridged only below body_span_min_frac minus this
    tighter_body_fracs: tuple[float, ...] = (0.5, 0.55, 0.6)  # too-wide fallback: denser body rules, in order
    deck_fallback_fracs: tuple[float, ...] = (0.45, 0.4, 0.35)  # then deck-lettering densities, in order
    silhouette_trust_frac: float = 0.08  # trust body silhouette without dark_frac widen
    small_car_span_frac: float = 0.22  # small cars — peel left track stubs past couplers
    body_span_max_frac: float = 0.75  # umean fallback when silhouette span is too wide
    light_body_min_frac: float = 0.50  # min mid-band body density for light-gray cars
    dark_body_min_frac: float = 0.35  # min mid-band body density for dark cars
    full_dark_frac: float = 0.25  # full-height dark fallback for bicolor cars
    shadow_track_min: float = 0.08  # a side-shadow column has less lower-band track than this


@dataclass(frozen=True)
class TopEdgeSettings:
    """The top of the car's row band: body rows, a left-end handbrake, roof gear, and the band's padding.

    Column bands are fractions of the analysis band width; row reaches are fractions of the
    height from the body top down to the track.
    """

    center_band: tuple[float, float] = (0.25, 0.75)  # car body columns
    left_band: tuple[float, float] = (0.08, 0.32)  # left end, past the studio-flag wedges
    extreme_left: float = 0.08  # the extreme-left strip where studio-flag wedges live
    handbrake_band: tuple[float, float] = (0.10, 0.20)  # handbrake staff / wheel columns
    center_body_min: float = 0.02  # share of the centre band that marks a body row
    left_body_min: float = 0.015  # share of the left band that marks a body row
    extreme_left_max: float = 0.08  # a left-band top with more wedge than this is not the car
    wedge_stop: float = 0.10  # stop the handbrake walk at a row this dark in the wedge strip
    handbrake_frac: tuple[float, float] = (0.04, 0.12)  # open range of a handbrake row's share
    handbrake_center_max: float = 0.01  # a handbrake row has almost no body in the centre
    body_resume: float = 0.02  # centre share that ends the handbrake walk ...
    body_resume_handbrake_max: float = 0.05  # ... when the handbrake band is this clear
    roof_reach: float = 0.22  # how far above the body top roof gear is looked for
    roof_dark_min: float = 0.06  # centre share of a roof-gear row
    roof_std_min: float = 18.0  # or the grey spread of a roof-gear row
    roof_gap: float = 0.06  # stop at the first plain row this far above the body top
    band_pad: float = 0.02  # padding above and below the row band


@dataclass(frozen=True)
class CropSettings:
    """The tuned values detection and cropping read, tuned on the fleet's light-box photos."""

    frame: FrameSettings = field(default_factory=FrameSettings)
    tone: ToneSettings = field(default_factory=ToneSettings)
    rows: RowSettings = field(default_factory=RowSettings)
    span: SpanSettings = field(default_factory=SpanSettings)
    top: TopEdgeSettings = field(default_factory=TopEdgeSettings)


CROP = CropSettings()
