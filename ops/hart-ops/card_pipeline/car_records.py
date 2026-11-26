"""Records of the car workflow (cars.py): repository rows, queue items, field differences.

``CarRow`` and ``QueueItem`` are the CSV rows of ``data/image_metadata.csv`` and
``data/car_queue.csv``. ``IntakeContext`` is what the intake stage modules
(intake_stages, crop_picker, site_gallery) read from cars.py.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import NamedTuple, TypedDict


class CarRow(TypedDict, total=False):
    """One row of image_metadata.csv. Every value is the CSV text; blank means unset."""

    source_image: str
    cropped_image: str
    ocr_zoom_image: str
    crop_status: str
    duplicate_of: str
    reporting_marks: str
    road_name: str
    road_number: str
    full_name: str
    car_type: str
    car_class: str
    color: str
    capy_lbs: str
    ld_lmt_lbs: str
    lt_wt_lbs: str
    built: str
    roster_id: str
    roster_road: str
    roster_length_ft: str
    roster_weight_oz: str
    roster_weight_tons: str
    ocr_text: str
    match_confidence: str
    notes: str
    out_of_service: str


class QueueItem(TypedDict):
    """One row of car_queue.csv: the date each step was done, blank while it is pending."""

    roster_id: str
    reason: str
    queued: str
    card_built: str
    card_printed: str
    sts: str
    ops: str


class FieldDiff(NamedTuple):
    """One field that differs between the repository and a tool, for one car."""

    car_id: str
    field: str
    repo: str
    tool: str


class FieldTarget(NamedTuple):
    """A tool file compare prints and sync applies, with the function that lists its differences."""

    key: str
    heading: str
    path: Path
    make_diffs: Callable[[], list[FieldDiff]]


class MergeOutcome(Enum):
    """What merging one new car row into the repository did."""

    NEW_CAR = "new car"
    PHOTO_ADDED = "photo added"
    SKIPPED = "skipped"


class CarMerge(NamedTuple):
    roster_id: str
    outcome: MergeOutcome
    existing_image: str  # the photo already on the car when outcome is SKIPPED, else ""


@dataclass(frozen=True)
class IntakeContext:
    """What the intake stage modules (intake_stages, crop_picker, site_gallery) read from here.

    Built at call time, so a test that patches a path on this module reaches the stages.
    """

    IMAGES_DIR: Path
    FINAL_DIR: Path
    IMAGE_SUFFIXES: frozenset[str]
    read_rows: Callable[[], tuple[list[CarRow], list[str]]]
    write_rows: Callable[[list[CarRow], list[str]], None]
    read_queue: Callable[[], list[QueueItem]]
    write_queue: Callable[[list[QueueItem]], None]
    find_car: Callable[[list[CarRow], str], CarRow | None]
    guess_roster_id: Callable[[Mapping[str, str], str], str]
    to_png: Callable[[Path], Path]
    process_photo: Callable[[Path], dict[str, str]]
    record_car: Callable[..., str]
    record_loco: Callable[[Mapping[str, str], bool], str]
