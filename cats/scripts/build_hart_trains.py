#!/usr/bin/env python3
"""Write the CATS train list cats/data/hart_trains.csv from the train master ops/hart-ops/data/trains.csv (ADR-039).

    python3 cats/scripts/build_hart_trains.py           write cats/data/hart_trains.csv
    python3 cats/scripts/build_hart_trains.py --check   write nothing; exit 1 when the file differs from a fresh build

The CATS file keeps its own columns and order (train_name, train_symbol, engine, font, runs_job, notes), one row per
train on the desks (on_desks yes) in the master's order, UTF-8 with LF line ends. The master's other columns
(on_desks, opspro_name) and its Operations Pro only trains (on_desks no, the staging trains) stay out of it. Edit the
master, never the CATS file.
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402
ROOT = paths.REPO_ROOT
MASTER = ROOT / "ops/hart-ops/data/trains.csv"
OUT = ROOT / "cats/data/hart_trains.csv"
COLUMNS = ("train_name", "train_symbol", "engine", "font", "runs_job", "notes")


class TrainsError(ValueError):
    """The train master lacks a column the CATS list needs, or a row's on_desks is not yes or no."""


def build(master: Path = MASTER) -> str:
    """The text of the CATS train list built from the master. TrainsError on a missing column or a bad on_desks."""
    with master.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in (*COLUMNS, "on_desks") if c not in (reader.fieldnames or ())]
        if missing:
            raise TrainsError(f"build_hart_trains: {master} has no column {', '.join(missing)}")
        rows = list(reader)
    bad = [row["train_symbol"] for row in rows if row["on_desks"] not in ("yes", "no")]
    if bad:
        raise TrainsError(f"build_hart_trains: on_desks must be yes or no: {', '.join(bad)}")
    rows = [row for row in rows if row["on_desks"] == "yes"]
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow([row[c] for c in COLUMNS])
    return buf.getvalue()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 when the CATS file is stale")
    args = ap.parse_args(argv)
    try:
        text = build(MASTER)
    except TrainsError as exc:
        print(exc, file=sys.stderr)
        return 1
    rel = OUT.relative_to(ROOT) if OUT.is_relative_to(ROOT) else OUT
    if args.check:
        current = OUT.read_bytes() if OUT.exists() else b""
        if current != text.encode("utf-8"):
            print(f"build_hart_trains: {rel} differs from a build of the train master; "
                  "run python3 cats/scripts/build_hart_trains.py")
            return 1
        print(f"build_hart_trains: {rel} is current")
        return 0
    OUT.write_bytes(text.encode("utf-8"))
    print(f"build_hart_trains: wrote {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
