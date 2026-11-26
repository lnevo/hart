"""Block lengths: the plan length from the AnyRail plan, and the measured length speed matching found.

Two files, one row per block, keyed by the block's device ID (ADR-039 lane L8, owner 2026-11-25):

- jmri/layouts/hart/data/block_lengths.csv (PLAN_COLUMNS): each JMRI block's length in the AnyRail plan 5.3c, on
  every level. tools/schematic/plan_lengths.py writes it from the plan; nothing else does.
- jmri/layouts/hart/data/block_lengths_measured.csv (MEASURED_COLUMNS): the blocks speed matching timed, each with
  its measured length and the run and date it came from. jmri/layouts/hart/scripts/infer_block_lengths.py --apply
  writes it; nothing else does. It sits over the plan file the way devices_field.csv sits over devices_generated.csv.

A reader takes one of two lengths:

- the plan length (plan_lengths, plan_cm, plan_length, plan_blocks): the schematic, the Layout Editor drawing, mast
  and signal placement, the levels and layout pages and the track-length export;
- the operating length (operating_lengths, operating_length): the measured length where there is one, else the plan
  length. The Dispatcher's block lengths in tables.xml (tables_build) take it; the speed-match tools on the Pi read
  the same two files with the standard library (speedmatch/analyze.py load_lengths).

measured_lengths gives the measured rows themselves, for the pages that print them beside the plan length.
tools/hartlib/tests/test_block_lengths.py lists the readers on each side and fails one that calls the other side's
reader.

The files hold no names. A block's user name and occupancy sensor come from the device master (hartlib.devices):
the name store's name for its (level, id), and the sensor of the occupancy row whose blocks cell names it
(occupancy_sensor).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from . import level_devices, paths
from .railroad_facts import FactsError, read_rows

PLAN_NAME = "block_lengths.csv"
MEASURED_NAME = "block_lengths_measured.csv"
PLAN = paths.LAYOUT_DATA / PLAN_NAME
MEASURED = paths.LAYOUT_DATA / MEASURED_NAME
PLAN_COLUMNS = ("level", "id", "plan_in", "note")
MEASURED_COLUMNS = ("id", "measured_in", "run", "date", "note")
LEVELS = ("1", "2", "3")
STAGING = "1"
MM_PER_INCH = 25.4
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DETECTOR_INPUT = re.compile(r"Node: (\d+) Block: (\d+)")


def measured_path(plan: Path = PLAN) -> Path:
    """The measured file beside a plan file: block_lengths.csv -> block_lengths_measured.csv."""
    plan = Path(plan)
    return plan.with_name(plan.stem + "_measured.csv")


@dataclass(frozen=True)
class PlanRow:
    """A row of the plan file."""
    line: int
    level: str
    id: str
    plan_in: float      # the AnyRail plan 5.3c length; 0 for a block between two turnouts that touch in the plan
    note: str


@dataclass(frozen=True)
class Measured:
    """A row of the measured file."""
    line: int
    id: str
    measured_in: float
    run: str            # the run it came from: loop1 laps, loop2 passes
    date: str           # the run's date, YYYY-MM-DD
    note: str


@dataclass(frozen=True)
class Block:
    """A plan row with its block's names from the device master."""
    line: int
    level: str
    id: str
    user_name: str
    occupancy_sensor: str
    plan_in: float
    note: str


def _where(path: Path, line: int) -> str:
    return f"{Path(path).name} line {line}"


def _inches(value: str, where: str, col: str, zero_ok: bool) -> float:
    try:
        v = float(value)
    except ValueError:
        raise FactsError(f"{where}: {col} {value!r} is not a number") from None
    if v < 0 or (v == 0 and not zero_ok):
        raise FactsError(f"{where}: {col} {value} is " + ("below zero" if zero_ok else "not above zero"))
    return v


def read_plan(path: Path = PLAN) -> dict[str, PlanRow]:
    """{id: PlanRow} of the plan file, in file order. Stops on a level not 1 to 3, an id empty or given twice (on any
    level: the measured file and the Pi's readers find a row by its id alone), or a plan length that is missing, not a
    number or below zero."""
    out: dict[str, PlanRow] = {}
    for line, r in read_rows(Path(path), PLAN_COLUMNS):
        where = _where(path, line)
        if r["level"] not in LEVELS or not r["id"] or r["id"] in out:
            raise FactsError(f"{where}: level {r['level']!r} and id {r['id']!r}: a level 1 to 3 and a device ID, "
                             "each id once")
        if not r["plan_in"]:
            raise FactsError(f"{where}: no plan_in (run tools/schematic/plan_lengths.py)")
        out[r["id"]] = PlanRow(line, r["level"], r["id"], _inches(r["plan_in"], where, "plan_in", True), r["note"])
    return out


def read_measured(path: Path | None = None, plan: Path = PLAN) -> dict[str, Measured]:
    """{id: Measured} of the measured file (default: the one beside `plan`), in file order. Stops on an id that is
    given twice or is no row of the plan file, a measured length that is not a number above zero, no run, or a date
    that is not YYYY-MM-DD."""
    path = measured_path(plan) if path is None else Path(path)
    ids = read_plan(plan)
    out: dict[str, Measured] = {}
    for line, r in read_rows(path, MEASURED_COLUMNS):
        where = _where(path, line)
        if r["id"] not in ids or r["id"] in out:
            raise FactsError(f"{where}: id {r['id']!r} is no row of {Path(plan).name}, or is given twice")
        if not r["run"] or not DATE.match(r["date"]):
            raise FactsError(f"{where}: run {r['run']!r} and date {r['date']!r}: the run it came from and its date "
                             "(YYYY-MM-DD)")
        out[r["id"]] = Measured(line, r["id"], _inches(r["measured_in"], where, "measured_in", False), r["run"],
                                r["date"], r["note"])
    return out


def _files_beside(path: Path):
    """The device master beside a plan file (a test's copy), else the repo's."""
    from . import devices
    data = Path(path).parent
    return devices.Files.under(data) if (data / devices.GENERATED_FILE).is_file() else None


def occupancy_sensor(level: str, name: str, part_of: str, detectors: Mapping[tuple[str, str], Mapping[str, str]]
                     ) -> str:
    """A block's occupancy sensor as the documentation names it: on staging, its detector's node input ("Block 4-4",
    from the occupancy row's wiring text); on main and upper, the occupancy row's user name; with no occupancy row
    (the helix blocks' virtual sensors), level_devices.occupancy_user. A part (part_of) reports on its block's
    detector. `detectors`: {(level, block name): occupancy row}."""
    row = detectors.get((level, name)) or (detectors.get((level, part_of)) if part_of else None)
    if row is None:
        return level_devices.occupancy_user(name)
    m = DETECTOR_INPUT.search(row["wiring"]) if level == STAGING else None
    return f"Block {m.group(1)}-{m.group(2)}" if m else row["user_name"]


def plan_blocks(path: Path = PLAN, files=None) -> dict[str, Block]:
    """{user name: Block} of the plan file, in file order, each with its block's user name and occupancy sensor from
    the device master (`files`, default the one beside `path`, else the repo's). FactsError on a row whose (level,
    id) is no block of the device master (the owner moves its length to the new id, or plan_lengths.py drops it)."""
    from . import devices
    rows = read_plan(path)
    master = devices.load(_files_beside(path) if files is None else files)
    blocks = {(r["level"], r["id"]): r for r in master if r["level"] and r["layer"] == "block"}
    detectors: dict[tuple[str, str], Mapping[str, str]] = {}
    for r in master:
        if r["level"] and r["layer"] == "occupancy":
            for b in filter(None, (x.strip() for x in r["blocks"].split(";"))):
                detectors.setdefault((r["level"], b), r)
    out: dict[str, Block] = {}
    bad = []
    for p in rows.values():
        b = blocks.get((p.level, p.id))
        if b is None:
            bad.append(f"{_where(path, p.line)}: {p.id} is no level {p.level} block row of the device master")
            continue
        out[b["user_name"]] = Block(p.line, p.level, p.id, b["user_name"],
                                    occupancy_sensor(p.level, b["user_name"], b["part_of"], detectors), p.plan_in,
                                    p.note)
    if bad:
        raise FactsError("; ".join(bad))
    return out


def plan_lengths(path: Path = PLAN, files=None) -> dict[str, float]:
    """{user name: plan inches} of every block: the length the drawings and the signal rules measure by."""
    return {name: b.plan_in for name, b in plan_blocks(path, files).items()}


def plan_cm(path: Path = PLAN, files=None) -> dict[str, float]:
    """{user name: plan length in cm} of every block."""
    return {name: inches * 2.54 for name, inches in plan_lengths(path, files).items()}


def plan_length(ident: str, path: Path = PLAN) -> float:
    """The plan length in inches of the block with device ID `ident`. FactsError when the plan file has no row."""
    try:
        return read_plan(path)[ident].plan_in
    except KeyError:
        raise FactsError(f"{Path(path).name}: no row for {ident}") from None


def measured_lengths(path: Path = PLAN, files=None) -> dict[str, Measured]:
    """{user name: Measured} of the measured blocks, in the measured file's order: for the pages that print a measured
    length beside the plan length. A plan-side reader never takes it as the block's length."""
    names = {b.id: name for name, b in plan_blocks(path, files).items()}
    return {names[m.id]: m for m in read_measured(plan=path).values()}


def operating_lengths(path: Path = PLAN, files=None) -> dict[str, float]:
    """{user name: inches} of every block: its measured length where the measured file has one, else its plan
    length. The Dispatcher's block lengths (tables.xml) and speed matching take it."""
    measured = read_measured(plan=path)
    return {name: measured[b.id].measured_in if b.id in measured else b.plan_in
            for name, b in plan_blocks(path, files).items()}


def operating_length(ident: str, path: Path = PLAN) -> float:
    """The operating length in inches of the block with device ID `ident` (operating_lengths)."""
    measured = read_measured(plan=path)
    return measured[ident].measured_in if ident in measured else plan_length(ident, path)


def measured_text(rows) -> str:
    """The measured file's text of `rows` (Measured, in the order given), measured_in to 0.1 in."""
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(MEASURED_COLUMNS)
    for m in rows:
        w.writerow([m.id, f"{m.measured_in:.1f}", m.run, m.date, m.note])
    return buf.getvalue()


def write_measured(rows, plan: Path = PLAN) -> Path:
    """Write the measured file beside `plan` (speed matching's one writer: infer_block_lengths.py --apply). Each
    row's id must be a row of the plan file; FactsError otherwise, and nothing is written."""
    rows = list(rows)
    ids = read_plan(plan)
    bad = sorted({m.id for m in rows if m.id not in ids})
    if bad:
        raise FactsError(f"{measured_path(plan).name}: {', '.join(bad)} is no row of {Path(plan).name}")
    out = measured_path(plan)
    out.write_text(measured_text(rows), encoding="utf-8")
    return out
