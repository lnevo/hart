"""bin/cars sync: send the repository's identity fields to the tools that differ, for cars both hold.

A dry run by default. Position, load and destination are STS's (ADR-016) and are never sent. The
live STS takes only ``remarks`` ("{type} {length}ft"): PATCH /cars/{id} is the API's one per-car
update, and remarks is the only identity column compare reads there. A changed road or number would
be a new reporting mark, which sync leaves to a person. Every refusal comes before the first write.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from car_fields import SeedHelpers, field_targets, seed_helpers
from car_live_sts import (
    LiveCar, LiveStsError, StsApi, fetch_live_cars, live_sts_diffs, load_sts_api, operating_reason,
    refuse_while_operating, take_sts_backup, target_is_local, target_url, write_live_cars,
)
from car_ops_roster import update_ops_fields
from car_records import CarRow, FieldDiff
from car_repo import (
    DEPLOY_NOTE, METADATA, NO_SEED_DIR, OPS_MERGED, PI_HOST, PI_OPS_DIR, SEED_COPIES, SEED_INPUTS, read_rows,
    row_id, sync_seed_copies,
)
from hartlib import operations

OPS_TARGET = "Operations Pro"
SEED_ROSTER_TARGET = "STS seed roster copy"
SEED_META_TARGET = "STS seed metadata copy"
LIVE_TARGET = "Live STS"
SYNC_TARGETS = {
    "ops": OPS_TARGET,
    "seed_roster": SEED_ROSTER_TARGET,
    "seed_meta": SEED_META_TARGET,
}
SEED_WHOLESALE = (
    "  --apply replaces both STS seed copies wholesale, as seed-copy does "
    "(the roster is rebuilt first), not just the fields listed."
)


@dataclass(frozen=True)
class SyncRequest:
    """The sync flags, checked: --sts-url needs --live-sts, and --apply --live-sts needs --sts-url."""

    ops_path: Path
    apply: bool
    use_live: bool
    url: str | None

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> SyncRequest:
        request = cls(Path(args.ops_live), getattr(args, "apply", False), getattr(args, "live_sts", False),
                      getattr(args, "sts_url", None))
        if request.url and not request.use_live:
            raise SyncRefused("--sts-url only applies together with --live-sts")
        if request.apply and request.use_live and not request.url:
            raise SyncRefused("--apply with --live-sts needs --sts-url URL (the live STS is never a default)")
        return request


class SyncRefused(ValueError):
    """The sync flags do not go together; the message says which."""


@dataclass(frozen=True)
class SyncPlan:
    """The field differences per target, in print order, and the parts --apply writes."""

    diffs: dict[str, list[FieldDiff]]

    @property
    def ops(self) -> list[FieldDiff]:
        return self.diffs.get(OPS_TARGET, [])

    @property
    def seed(self) -> list[FieldDiff]:
        return self.diffs.get(SEED_ROSTER_TARGET, []) + self.diffs.get(SEED_META_TARGET, [])

    @property
    def live(self) -> list[FieldDiff]:
        return self.diffs.get(LIVE_TARGET, [])

    def total(self) -> int:
        return sum(len(d) for d in self.diffs.values())


def sync_plan(rows: list[CarRow], ops_path: Path, live: list[LiveCar] | None, gen: SeedHelpers | None
              ) -> dict[str, list[FieldDiff]]:
    """Field differences per target, from the same field_targets compare prints."""
    plan: dict[str, list[FieldDiff]] = {}
    for key, _heading, path, make_diffs in field_targets(rows, ops_path, gen, SEED_INPUTS):
        if key in SYNC_TARGETS and path.is_file():
            plan[SYNC_TARGETS[key]] = make_diffs()
    if live is not None and gen is not None:
        plan[LIVE_TARGET] = live_sts_diffs(rows, live, set(gen.PASSENGER_TYPES))
    return plan


def out_of_service_flags(path: Path) -> dict[str, str]:
    """Roster id -> out-of-service value, from a repository CSV or a roster XML."""
    if path.suffix == ".csv":
        with path.open(newline="", encoding="utf-8") as fh:
            return {row_id(r): r.get("out_of_service") or "" for r in csv.DictReader(fh) if row_id(r)}
    return {c.get("id", ""): c.get("outOfService") or "" for c in operations.cars(path)}


def seed_extra_changes() -> list[str]:
    """What replacing the seed copies would change beyond the listed fields: cars added or
    removed, and out-of-service flags (the roster as last built; seed-copy rebuilds it first)."""
    lines = []
    for master in SEED_COPIES:
        copy = SEED_INPUTS / master.name
        if not master.is_file():
            continue
        if not copy.is_file():
            lines.append(f"{master.name}: the copy is missing and would be created")
            continue
        want, have = out_of_service_flags(master), out_of_service_flags(copy)
        for label, ids in (("added", sorted(want.keys() - have.keys())),
                           ("removed", sorted(have.keys() - want.keys())),
                           ("out_of_service changed", sorted(i for i in want.keys() & have.keys() if want[i] != have[i]))):
            if ids:
                lines.append(f"{master.name}: cars {label}: {' '.join(ids)}")
    return lines


def seed_preflight() -> None:
    """Everything the seed refresh needs, checked before the first write of a sync."""
    if not SEED_INPUTS.is_dir():
        raise LiveStsError(NO_SEED_DIR.format(path=SEED_INPUTS))
    if not METADATA.is_file():
        raise LiveStsError(f"Master file is missing: {METADATA}")
    try:
        import build_car_roster_sor  # noqa: F401
    except ImportError as err:
        raise LiveStsError(f"the roster build cannot run ({err})") from err


def read_live(request: SyncRequest) -> list[LiveCar] | None:
    """The live STS cars when --live-sts is given, else None."""
    if not request.use_live:
        return None
    refuse_while_operating(operating_reason, "touched")
    return fetch_live_cars().cars


def print_plan(plan: SyncPlan, request: SyncRequest) -> None:
    for target, diffs in plan.diffs.items():
        print(f"{target}: {len(diffs)} change(s)")
        for cid, field, want, have in diffs:
            print(f"    {cid} {field}: {have!r} -> {want!r}")
    if plan.seed:
        print(SEED_WHOLESALE)
        for line in seed_extra_changes():
            print(f"    also changes: {line}")
    if not request.use_live:
        print("Live STS: not checked (add --live-sts --sts-url URL)")


def preflight(plan: SyncPlan, request: SyncRequest) -> StsApi | None:
    """Every check --apply needs, before the first write. Returns the STS client when the live STS is written."""
    if plan.ops:
        import publish_gate as gate

        if request.ops_path.resolve() != OPS_MERGED.resolve():
            raise LiveStsError(f"--apply only edits the repo roster {OPS_MERGED}, not {request.ops_path}")
        problems = gate.pi_out_of_step(OPS_MERGED.parent, PI_HOST, PI_OPS_DIR)
        if problems:
            raise LiveStsError("; ".join(problems))
    if plan.seed:
        seed_preflight()
    if not plan.live:
        return None
    sts_api = load_sts_api()
    refuse_while_operating(operating_reason, "touched")
    print("  " + take_sts_backup(sts_api, target_is_local(target_url())))
    return sts_api


def apply_plan(plan: SyncPlan, request: SyncRequest, live: list[LiveCar] | None, sts_api: StsApi | None) -> int:
    if plan.seed:
        from build_car_roster_sor import main as build_roster

        build_roster()
        sync_seed_copies(SEED_INPUTS, SEED_COPIES)
    if plan.ops:
        update_ops_fields(request.ops_path, plan.ops)
        print(f"Updated {len(plan.ops)} attribute(s) in {request.ops_path}. {DEPLOY_NOTE}")
    if plan.live:
        if sts_api is None or live is None:
            raise LiveStsError("the live STS plan has no client or car list")
        try:
            done = write_live_cars(sts_api, live, plan.live)
        except LiveStsError as err:
            print(err, file=sys.stderr)
            return 2
        print(f"Updated {len(done)} live STS car(s), each read back: {' '.join(done)}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    """Dry run by default. --apply writes Operations Pro, replaces the STS seed copies and,
    with --live-sts --sts-url, patches the STS."""
    try:
        request = SyncRequest.from_args(args)
    except SyncRefused as err:
        print(err, file=sys.stderr)
        return 2
    if request.url:
        os.environ["STS_API_URL"] = request.url  # this run only
    rows, _ = read_rows()
    gen, why = seed_helpers()
    if gen is None:
        print(f"Cannot check the STS targets: {why}")
    try:
        live = read_live(request)
    except LiveStsError as err:
        print(f"Cannot use the live STS: {err}", file=sys.stderr)
        return 2
    plan = SyncPlan(sync_plan(rows, request.ops_path, live, gen))
    print_plan(plan, request)
    if not plan.total():
        print("Nothing to do: the repository and the tools agree.")
        return 0
    if not request.apply:
        print("Dry run: nothing was written. Add --apply to write.")
        return 0
    try:
        sts_api = preflight(plan, request)
    except LiveStsError as err:
        print(f"Sync stopped, nothing written: {err}", file=sys.stderr)
        return 2
    return apply_plan(plan, request, live, sts_api)
