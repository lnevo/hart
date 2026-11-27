"""Field differences between the car repository and each tool file, shared by compare and sync.

The expected value is what build_merged_car_roster.manifest_to_car makes from the row, so road code,
number, type, length and colour are normalised exactly as the roster build does. A field is compared
only when its repository column is filled in: manifest_to_car's defaults (40 or 90 ft, default
weights) are not repository facts. Not compared: weight and weightTons, location, load, destination
and position (STS owns them, ADR-016), the out-of-service flag (ADR-015, reported on its own) and the
STS AAR code (derived from several rules, not one field). Operations Pro's car type is left out: it
follows the STS car code, not car_type (docs/ops/OPSPRO_MAPPING.md, D14), and no writer code in the
repository derives it.
"""
from __future__ import annotations

import csv
import sys
from collections.abc import Callable, Mapping
from collections.abc import Set as AbstractSet
from pathlib import Path
from typing import Protocol

from car_ops_roster import ops_car_attrs
from car_records import CarRow, FieldDiff, FieldTarget
from car_repo import MERGED, METADATA, NO_SEED_DIR, STS_HELPERS, as_fields, row_id

# Repository column -> the attribute the tool's writer sets.
ROSTER_FIELDS = {
    "roster_road": "roadName",
    "road_number": "roadNumber",
    "car_type": "type",
    "roster_length_ft": "length",
    "color": "color",
}
OPS_FIELDS = {c: a for c, a in ROSTER_FIELDS.items() if a != "type"}
# STS seed copy of image_metadata.csv: the columns generate_hart_seed.load_roster_metadata reads.
SEED_META_FIELDS = ("car_type", "car_class", "notes")
# sts_added_cars.csv: reporting_marks is road code + number; remarks is "{type} {length}ft"
# (generate_hart_seed.add_cars).
ADDED_FIELDS = {"reporting_marks": "marks", "remarks": "remarks"}
DIFF_LIMIT = 20
# The roster build skips only locomotives, so Operations Pro is compared for every other type.
# generate_hart_seed skips its PASSENGER_TYPES (passenger cars, cabooses, MOW) in add_cars.
OPS_SKIP_TYPES: frozenset[str] = frozenset()
NOT_CARS = ("Locomotive", "Streetcar")


class SeedHelpers(Protocol):
    """The parts of the sts-helpers generate_hart_seed module compare and sync read."""

    PASSENGER_TYPES: AbstractSet[str]

    def normalize_car_type(self, car_type: str) -> str: ...

    def infer_car_class(self, row: dict[str, str]) -> str: ...

    def load_added_cars(self, hart_dir: Path) -> dict[str, dict[str, str]]: ...


def seed_helpers() -> tuple[SeedHelpers, None] | tuple[None, str]:
    """(generate_hart_seed, None), or (None, reason) when the sts-helpers submodule cannot load."""
    seed_dir = STS_HELPERS / "seed"
    if not (seed_dir / "generate_hart_seed.py").is_file():
        return None, NO_SEED_DIR.format(path=seed_dir)
    for path in (str(seed_dir), str(STS_HELPERS / "lib")):
        if path not in sys.path:
            sys.path.insert(0, path)
    try:
        import generate_hart_seed
    except (ImportError, AttributeError) as err:
        return None, f"{type(err).__name__}: {err}"
    return generate_hart_seed, None


def expected_cars(rows: list[CarRow], skip_types: AbstractSet[str]) -> dict[str, dict[str, str]]:
    """Roster attributes the build makes from each repository row, keyed by roster id.

    An attribute whose repository column is blank is dropped, not defaulted.
    """
    from build_merged_car_roster import manifest_to_car, normalize_roster_type
    from engine_lookup import is_locomotive_row

    out = {}
    for row in rows:
        fields = as_fields(row)
        ctype = (row.get("car_type") or "").strip()
        if is_locomotive_row(fields) or ctype in NOT_CARS:
            continue
        if normalize_roster_type(ctype) in skip_types or ctype in skip_types:
            continue
        attrs = manifest_to_car(fields)
        if not attrs:
            continue
        for column, attr in ROSTER_FIELDS.items():
            if attr != "roadName" and not (fields.get(column) or "").strip():
                attrs.pop(attr, None)
        out[attrs["id"]] = attrs
    return out


def field_diffs(expected: Mapping[str, Mapping[str, str]], tool: Mapping[str, Mapping[str, str]],
                fields: Mapping[str, str]) -> list[FieldDiff]:
    """The differing fields of cars in both, over the mapped fields only.

    A field the repository leaves blank is skipped: the roster build keeps the tool's own value.
    """
    diffs: list[FieldDiff] = []
    for cid in sorted(expected.keys() & tool.keys()):
        for attr in fields.values():
            want = (expected[cid].get(attr) or "").strip()
            have = (tool[cid].get(attr) or "").strip()
            if want and want != have:
                diffs.append(FieldDiff(cid, attr, want, have))
    return diffs


def print_diffs(diffs: list[FieldDiff], show_all: bool) -> None:
    print(f"  Field differences: {len(diffs)}")
    shown = diffs if show_all else diffs[:DIFF_LIMIT]
    for cid, field, want, have in shown:
        print(f"    {cid} {field}: repo={want!r} tool={have!r}")
    if len(diffs) > len(shown):
        print(f"    +{len(diffs) - len(shown)} more (--all)")


def seed_meta_diffs(rows: list[CarRow], copy_path: Path, gen: SeedHelpers) -> list[FieldDiff]:
    """Differences between the repository and the STS seed copy of image_metadata.csv."""
    with copy_path.open(newline="", encoding="utf-8") as fh:
        copy_rows = {row_id(r): r for r in csv.DictReader(fh) if row_id(r)}
    reads: dict[str, Callable[[dict[str, str]], str]] = {
        "car_type": lambda r: gen.normalize_car_type(r.get("car_type") or ""),
        "car_class": gen.infer_car_class,
        "notes": lambda r: (r.get("notes") or "").strip(),
    }
    diffs: list[FieldDiff] = []
    for row in rows:
        cid = row_id(row)
        if cid not in copy_rows or "CarImagesFinal" not in (row.get("notes") or ""):
            continue
        if gen.normalize_car_type(row.get("car_type") or "") in gen.PASSENGER_TYPES:
            continue
        for field in SEED_META_FIELDS:
            want, have = reads[field](as_fields(row)), reads[field](copy_rows[cid])
            if want and want != have:
                diffs.append(FieldDiff(cid, field, want, have))
    return sorted(diffs)


def added_cars_diffs(rows: list[CarRow], added: Mapping[str, Mapping[str, str]], gen: SeedHelpers) -> list[FieldDiff]:
    """Differences between the repository and sts_added_cars.csv (marks and remarks)."""
    tool = {
        cid: {"marks": a.get("reporting_marks", ""), "remarks": a.get("remarks", "")}
        for cid, a in added.items()
    }
    want = {
        cid: {"marks": f"{a['roadName']}{a['roadNumber']}", "remarks": f"{a['type']} {a['length']}ft"}
        for cid, a in expected_cars(rows, frozenset(gen.PASSENGER_TYPES)).items()
        if a.get("type") and a.get("length")
    }
    return field_diffs(want, tool, ADDED_FIELDS)


def field_targets(rows: list[CarRow], ops_path: Path, gen: SeedHelpers | None, seed_inputs: Path) -> list[FieldTarget]:
    """Each tool file compared field by field, in print order.

    compare prints these and sync applies them, so both read the same differences. The STS
    entries are present only when the seed helpers loaded (gen) and the seed folder exists.
    """
    targets = [FieldTarget(
        "ops", "Operations Pro fields (OperationsCarRoster.xml, type left out)", ops_path,
        lambda: field_diffs(expected_cars(rows, OPS_SKIP_TYPES), ops_car_attrs(ops_path), OPS_FIELDS),
    )]
    if gen is None or not seed_inputs.is_dir():
        return targets
    seed = gen
    photos = {row_id(r) for r in rows if "CarImagesFinal" in (r.get("notes") or "")}
    sts_expected = expected_cars(
        [r for r in rows if row_id(r) in photos], frozenset(seed.PASSENGER_TYPES)
    )
    roster, meta = seed_inputs / MERGED.name, seed_inputs / METADATA.name
    added = seed_inputs / "sts_added_cars.csv"
    return targets + [
        FieldTarget("seed_roster", "STS seed roster copy fields (HART_MergedCarRoster.xml; cars with a photo only)",
                    roster, lambda: field_diffs(sts_expected, ops_car_attrs(roster), ROSTER_FIELDS)),
        FieldTarget("seed_meta", "STS seed metadata copy fields (image_metadata.csv)",
                    meta, lambda: seed_meta_diffs(rows, meta, seed)),
        FieldTarget("added", "STS added cars fields (sts_added_cars.csv)",
                    added, lambda: added_cars_diffs(rows, seed.load_added_cars(seed_inputs), seed)),
    ]
