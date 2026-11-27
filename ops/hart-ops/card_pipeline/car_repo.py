"""The car repository and its queue: file locations, reads, writes and the rules for adding a car.

``data/image_metadata.csv`` is the repository (one row per car) and ``data/car_queue.csv`` the
queue of cars that still need a card, STS or Operations Pro. The ``bin/cars`` commands
(cars.py and the car_* modules) read and write them only through this module.
"""
from __future__ import annotations

import csv
import os
import shutil
from datetime import date
from pathlib import Path
from typing import cast

PIPELINE = Path(__file__).resolve().parent
HART_ROOT = PIPELINE.parents[2]
# The image trees live in the hart checkout's ops/car-cards unless the caller points elsewhere.
# Set before car_paths is imported, because car_paths reads it at import.
os.environ.setdefault("HART_CAR_CARDS_ROOT", str(HART_ROOT / "ops/car-cards"))

from car_paths import DATA, ROOT, CardPipelineError  # noqa: E402
from car_records import CarMerge, CarRow, MergeOutcome, QueueItem  # noqa: E402

METADATA = DATA / "image_metadata.csv"
QUEUE = DATA / "car_queue.csv"
MERGED = DATA / "HART_MergedCarRoster.xml"
OPS = DATA / "OperationsCarRoster.xml"
# ADR-015: the repo copy is the master; the deploy installs it on the hosts.
OPS_MERGED = HART_ROOT / "jmri/layouts/hart/operations/OperationsCarRoster.xml"
STS_HELPERS = HART_ROOT / "external/sts-helpers"
# Publish copies these into the STS seed; compare reports when the copies drift.
SEED_COPIES = (METADATA, MERGED)
SEED_INPUTS = STS_HELPERS / "seed/inputs"
NO_SEED_DIR = (
    "{path} does not exist (is the external/sts-helpers submodule checked out? "
    "git submodule update --init external/sts-helpers)"
)
PRINT_DIR = ROOT / "print"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".heic", ".tif", ".tiff"}
DEPLOY_NOTE = "Commit it in the hart repo, then deploy with tools/hosts/sync_hart_package.sh."
PI_HOST = os.environ.get("HART_PI_SSH", "pi")
PI_OPS_DIR = os.environ.get("HART_PI_USERFILES", "/home/pi/JMRI_UserFiles") + "/operations"
QUEUE_COLUMNS = [
    "roster_id",
    "reason",
    "queued",
    "card_built",
    "card_printed",
    "sts",
    "ops",
]
QUESTIONS = [
    ("reporting_marks", "Reporting marks (e.g. N&W)"),
    ("road_number", "Road number"),
    ("car_type", "Car type (Boxcar, Hopper, Flatcar, Gondola, Tank, Coil, MOW...)"),
    ("car_class", "AAR class (e.g. F3)"),
    ("color", "Color"),
    ("roster_length_ft", "Length in feet"),
    ("capy_lbs", "Capacity lbs"),
    ("ld_lmt_lbs", "Load limit lbs"),
    ("lt_wt_lbs", "Light weight lbs"),
    ("built", "Built date"),
    ("full_name", "Card description override (blank for automatic)"),
]


def today() -> str:
    return date.today().isoformat()


def read_rows() -> tuple[list[CarRow], list[str]]:
    with METADATA.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return cast("list[CarRow]", list(reader)), list(reader.fieldnames or [])


def write_rows(rows: list[CarRow], columns: list[str]) -> None:
    tmp = METADATA.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(METADATA)


def read_queue() -> list[QueueItem]:
    if not QUEUE.is_file():
        return []
    with QUEUE.open(newline="", encoding="utf-8") as fh:
        return cast("list[QueueItem]", list(csv.DictReader(fh)))


def write_queue(queue: list[QueueItem]) -> None:
    with QUEUE.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=QUEUE_COLUMNS)
        writer.writeheader()
        writer.writerows(queue)


def enqueue(queue: list[QueueItem], roster_id: str, reason: str) -> None:
    """Queue a card. A new car also needs STS and Operations Pro; a photo does not."""
    for item in queue:
        if item["roster_id"] == roster_id and not item["card_printed"]:
            item["reason"] = reason
            item["card_built"] = ""
            return
    done = today() if reason == "photo added" else ""
    queue.append(
        {
            "roster_id": roster_id,
            "reason": reason,
            "queued": today(),
            "card_built": "",
            "card_printed": "",
            "sts": done,
            "ops": done,
        }
    )


def as_fields(row: CarRow) -> dict[str, str]:
    """The same row object, typed as the plain column dict that roster_id and the roster build take and change."""
    return cast("dict[str, str]", row)


def blank_row(columns: list[str]) -> CarRow:
    """A row with every repository column blank."""
    return cast(CarRow, {c: "" for c in columns})


def row_id(row: CarRow | dict[str, str]) -> str:
    """The roster id of a repository row, or of a plain CSV row with the same columns."""
    from roster_id import manifest_car_id

    return manifest_car_id(cast("dict[str, str]", row))


def find_car(rows: list[CarRow], roster_id: str) -> CarRow | None:
    return next((r for r in rows if row_id(r) == roster_id), None)


def out_of_service_ids(rows: list[CarRow]) -> set[str]:
    """The cars the repository holds out of service. STS and Operations Pro follow this."""
    return {row_id(r) for r in rows if r.get("out_of_service") == "yes"}


def parse_sets(pairs: list[str]) -> dict[str, str]:
    values = {}
    for pair in pairs:
        if "=" not in pair:
            raise CardPipelineError(f"--set needs field=value, got {pair!r}")
        key, value = pair.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def ask(row: CarRow, values: dict[str, str], assume_yes: bool) -> None:
    """Fill the row from --set values, then ask about anything left."""
    as_fields(row).update(values)
    if assume_yes:
        return
    print("Press Enter to keep the value in brackets.")
    for field, label in QUESTIONS:
        if field in values:
            continue
        current = row.get(field, "")
        answer = input(f"  {label} [{current}]: ").strip()
        if answer:
            as_fields(row)[field] = answer


def finish_row(row: CarRow, columns: list[str]) -> str:
    """Fill the derived fields and return the roster id."""
    from build_merged_car_roster import default_weights
    from roster_id import assign_freight_roster_id

    row["road_name"] = row.get("road_name") or row.get("reporting_marks", "")
    row["roster_id"] = ""
    row["roster_road"] = ""
    assign_freight_roster_id(as_fields(row))
    roster_id = row.get("roster_id", "")
    if not roster_id:
        raise CardPipelineError("A car needs reporting marks and a road number.")
    length = row.get("roster_length_ft", "")
    if length and not (row.get("roster_weight_oz") and row.get("roster_weight_tons")):
        row["roster_weight_oz"], row["roster_weight_tons"] = default_weights(length)
    for column in columns:
        as_fields(row).setdefault(column, "")
    return roster_id


def merge_car(row: CarRow, rows: list[CarRow], columns: list[str], queue: list[QueueItem],
              dry_run: bool) -> CarMerge:
    """Fill the derived fields of a new car row and merge it into the repository rows.

    A new roster id is appended and queued as a new car. A car already in the repository
    takes the row's non-blank values and is queued for its photo, unless it already has a
    photo, which is left alone. ``dry_run`` reports the outcome and changes nothing.
    """
    roster_id = finish_row(row, columns)
    existing = find_car(rows, roster_id)
    if existing is None:
        if not dry_run:
            rows.append(row)
            enqueue(queue, roster_id, MergeOutcome.NEW_CAR.value)
        return CarMerge(roster_id, MergeOutcome.NEW_CAR, "")
    if existing.get("source_image"):
        return CarMerge(roster_id, MergeOutcome.SKIPPED, existing["source_image"])
    if not dry_run:
        for key, value in as_fields(row).items():
            if value:
                as_fields(existing)[key] = value
        enqueue(queue, roster_id, MergeOutcome.PHOTO_ADDED.value)
    return CarMerge(roster_id, MergeOutcome.PHOTO_ADDED, "")


def sync_seed_copies(inputs: Path, masters: tuple[Path, ...]) -> None:
    """Copy the master car files into the STS seed inputs and nothing else."""
    if not inputs.is_dir():
        raise CardPipelineError(NO_SEED_DIR.format(path=inputs))
    for source in masters:
        if not source.is_file():
            raise CardPipelineError(f"Master file is missing: {source}")
    for source in masters:
        shutil.copy2(source, inputs / source.name)
    print(f"Copied the repository and roster to {inputs}")
