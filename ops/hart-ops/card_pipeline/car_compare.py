"""bin/cars compare: report how each tool differs from the car repository. Reads only.

The sections are roster ids per tool, the STS seed copies, the STS seed's cars, the out-of-service
flags, the field differences (car_fields) and, with --live-sts, the live STS (car_live_sts).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from car_fields import NOT_CARS, field_targets, print_diffs, seed_helpers
from car_live_sts import print_live_sts
from car_ops_roster import ops_ids, ops_out_of_service
from car_records import CarRow, FieldDiff
from car_repo import (
    HART_ROOT, MERGED, NO_SEED_DIR, OPS, SEED_COPIES, SEED_INPUTS, STS_HELPERS, out_of_service_ids, read_rows,
    row_id,
)

URL_NEEDS_LIVE = "--sts-url only applies together with --live-sts"


def seed_marks() -> set[str]:
    backups = HART_ROOT / "external/sts-docker-data/backups"
    seed = next((p for p in (backups / "hart_seed0", backups / "hart_seed") if p.is_file()), None)
    if seed is None:
        return set()
    text = seed.read_text(encoding="utf-8", errors="replace")
    return set(re.findall(r'insert into `cars` values\("\d+","([^"]*)"', text))


def seed_copy_report(inputs: Path, masters: tuple[Path, ...]) -> list[str]:
    """Lines saying whether each master matches its copy in the STS seed inputs.

    The roster is compared as last built; publish and seed-copy rebuild it first.
    """
    if not inputs.is_dir():
        return ["  Cannot check: " + NO_SEED_DIR.format(path=inputs)]
    lines = []
    drift = False
    for master in masters:
        suffix = " (as last built)" if master == MERGED else ""
        if not master.is_file():
            lines.append(f"  {master.name}: master is missing")
            continue
        copy = inputs / master.name
        if not copy.is_file():
            state = "differs (copy is missing)"
            drift = True
        elif copy.read_bytes() == master.read_bytes():
            state = "same"
        else:
            state = "differs"
            drift = True
        lines.append(f"  {master.name}: {state}{suffix}")
    if drift:
        lines.append("  Bring them in step with: bin/cars seed-copy")
    return lines


def print_if_present(path: Path, show_all: bool, make_diffs: Callable[[], list[FieldDiff]]) -> None:
    """Print make_diffs() for a tool file, or say the file is missing instead of reporting 0."""
    if not path.is_file():
        print(f"  Cannot check: {path} is missing")
        return
    print_diffs(make_diffs(), show_all)


def print_field_sections(rows: list[CarRow], ops_path: Path, show_all: bool) -> None:
    """Field differences for cars present in the repository and a tool (read only)."""
    gen, reason = seed_helpers()
    for _key, heading, path, make_diffs in field_targets(rows, ops_path, gen, SEED_INPUTS):
        print(f"\n{heading}:")
        print_if_present(path, show_all, make_diffs)
    if gen is None:
        print(f"\nCannot check STS sections: {reason}")
    elif not SEED_INPUTS.is_dir():
        print("\nCannot check STS sections: " + NO_SEED_DIR.format(path=SEED_INPUTS))


def print_id_sections(master: set[str], locos: set[str], ops_live: Path) -> None:
    """Roster ids missing from, or extra in, the roster export and Operations Pro."""
    targets = {
        "Roster export": ops_ids(OPS),
        "Operations Pro": ops_ids(ops_live),
    }
    for name, ids in targets.items():
        missing = sorted(master - locos - ids)
        extra = sorted(ids - master)
        print(f"\n{name}: {len(ids)} cars")
        print(f"  Missing there: {len(missing)} {' '.join(missing)}")
        print(f"  Not in repository: {len(extra)} {' '.join(extra)}")


def print_seed_and_service(rows: list[CarRow], master: set[str], locos: set[str], ops_live: Path) -> None:
    """The STS seed copies, the seed's cars, and the out-of-service flags in each tool."""
    print("\nSTS seed copies:")
    print("\n".join(seed_copy_report(SEED_INPUTS, SEED_COPIES)))
    marks = seed_marks()
    print(f"\nSTS seed: {len(marks)} cars")
    print(f"  Not in repository: {' '.join(sorted(marks - master)) or 'none'}")
    out = out_of_service_ids(rows)
    print(f"\nOut of service in the repository: {len(out)} {' '.join(sorted(out))}")
    live_flags = ops_out_of_service(ops_live)
    print(f"  Operations Pro should add: {' '.join(sorted(out - live_flags)) or 'none'}")
    print(f"  Operations Pro should clear: {' '.join(sorted(live_flags - out)) or 'none'}")
    subprocess.run(
        [sys.executable, str(STS_HELPERS / "tools/sync_hart_status.py"), "--check"], check=False
    )
    photo_ids = {row_id(r) for r in rows if r.get("source_image")} - locos
    print(f"  Photographed cars not in STS: {' '.join(sorted(photo_ids - marks)) or 'none'}")


def cmd_compare(args: argparse.Namespace) -> int:
    rows, _ = read_rows()
    ops_live = Path(args.ops_live)
    master = {row_id(r) for r in rows if row_id(r)}
    locos = {row_id(r) for r in rows if (r.get("car_type") or "") in NOT_CARS}
    print_id_sections(master, locos, ops_live)
    print_seed_and_service(rows, master, locos, ops_live)
    show_all = getattr(args, "all", False)
    if getattr(args, "sts_url", None) and not getattr(args, "live_sts", False):
        print(URL_NEEDS_LIVE, file=sys.stderr)
        return 2
    print_field_sections(rows, ops_live, show_all)
    if getattr(args, "live_sts", False):
        if getattr(args, "sts_url", None):
            os.environ["STS_API_URL"] = args.sts_url  # this run only
        return print_live_sts(rows, show_all)
    return 0
