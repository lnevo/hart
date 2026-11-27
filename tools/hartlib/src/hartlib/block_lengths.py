"""Block lengths: the plan length from the AnyRail plan, and the measured length speed matching found.

Two files, one row per block, keyed by the block's device ID (ADR-039 lane L8):

- jmri/layouts/hart/data/block_lengths.csv (PLAN_COLUMNS): each JMRI block's length in the AnyRail plan 5.3c, on
  every level. tools/schematic/plan_lengths.py writes it from the plan; nothing else does.
- jmri/layouts/hart/data/block_lengths_measured.csv (MEASURED_COLUMNS): the blocks speed matching timed, each with
  its measured length and the run and date it came from. jmri/layouts/hart/scripts/infer_block_lengths.py --apply
  writes it; nothing else does. It sits over the plan file the way devices_field.csv sits over devices_generated.csv.

A reader takes one of two lengths:

- the plan length (plan_lengths, plan_cm, plan_length, plan_blocks): the schematic, the Layout Editor drawing, mast
  and signal placement, the levels and layout pages and the track-length export;
- the operating length (operating_lengths, operating_length): the plan length, except on a detector speed matching
  timed, whose blocks add up to the measured length (the parts of an OS block keep their plan lengths, the OS block
  takes the rest). The Dispatcher's block lengths in tables.xml (tables_build) take it. The speed-match tools on the
  Pi read the same two files with the standard library (speedmatch/analyze.py load_lengths), by sensor: a timed
  detector's whole measured length.

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
from collections.abc import Container, Iterable, Mapping
from typing import TYPE_CHECKING

from . import level_devices, paths
from .railroad_facts import FactsError, MasterRow, device_list, read_rows

if TYPE_CHECKING:
    from . import devices as devices_mod

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
    except ValueError as exc:
        raise FactsError(f"{where}: {col} {value!r} is not a number") from exc
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
        m = _measured_row(r, _where(path, line), line, ids, out, Path(plan).name)
        out[m.id] = m
    return out


def _measured_row(r: Mapping[str, str], where: str, line: int, ids: Container[str], seen: Container[str],
                  plan_name: str) -> Measured:
    """A measured row (text cells) checked: its id a row of the plan file and not in `seen`, its length above
    zero, a run and a YYYY-MM-DD date. read_measured and write_measured hold rows to the same rules."""
    if r["id"] not in ids or r["id"] in seen:
        raise FactsError(f"{where}: id {r['id']!r} is no row of {plan_name}, or is given twice")
    if not r["run"] or not DATE.match(r["date"]):
        raise FactsError(f"{where}: run {r['run']!r} and date {r['date']!r}: the run it came from and its date "
                         "(YYYY-MM-DD)")
    return Measured(line, r["id"], _inches(r["measured_in"], where, "measured_in", False), r["run"], r["date"],
                    r["note"])


def _files_beside(path: Path) -> devices_mod.Files | None:
    """The device master beside a plan file (a test's copy), else the repo's."""
    from . import devices
    data = Path(path).parent
    return devices.Files.under(data) if (data / devices.GENERATED_FILE).is_file() else None


def occupancy_sensor(level: str, name: str, part_of: str, detectors: Mapping[tuple[str, str], MasterRow]) -> str:
    """A block's occupancy sensor as the documentation names it: on staging, its detector's node input ("Block 4-4",
    from the occupancy row's wiring text); on main and upper, the occupancy row's user name; with no occupancy row
    (the helix blocks' virtual sensors), level_devices.occupancy_user. A part (part_of) reports on its block's
    detector. `detectors`: {(level, block name): occupancy row}."""
    row = detectors.get((level, name))
    if row is None and part_of:
        row = detectors.get((level, part_of))
    if row is None:
        return level_devices.occupancy_user(name)
    m = DETECTOR_INPUT.search(row.wiring) if level == STAGING else None
    return f"Block {m.group(1)}-{m.group(2)}" if m else row.user_name


def plan_blocks(path: Path = PLAN, files: devices_mod.Files | Path | str | None = None) -> dict[str, Block]:
    """{user name: Block} of the plan file, in file order, each with its block's user name and occupancy sensor from
    the device master (`files`, default the one beside `path`, else the repo's). FactsError on a row whose (level,
    id) is no block of the device master (the owner moves its length to the new id, or plan_lengths.py drops it), or
    two rows whose blocks have the same user name."""
    from . import devices
    rows = read_plan(path)
    master = devices.load(_files_beside(path) if files is None else files)
    blocks = {(r.level_cell, r.id): r for r in master if r.level is not None and r.layer == "block"}
    detectors: dict[tuple[str, str], MasterRow] = {}
    for r in master:
        if r.level is not None and r.layer == "occupancy":
            for b in device_list(r.blocks):
                detectors.setdefault((r.level_cell, b), r)
    out: dict[str, Block] = {}
    bad: list[str] = []
    for p in rows.values():
        row = blocks.get((p.level, p.id))
        if row is None:
            bad.append(f"{_where(path, p.line)}: {p.id} is no level {p.level} block row of the device master")
            continue
        name = row.user_name
        if name in out:
            bad.append(f"{_where(path, p.line)}: {p.id} is named {name!r}, as {out[name].id} is (line {out[name].line})")
            continue
        out[name] = Block(p.line, p.level, p.id, name, occupancy_sensor(p.level, name, row.part_of, detectors),
                          p.plan_in, p.note)
    if bad:
        raise FactsError("; ".join(bad))
    return out


def plan_lengths(path: Path = PLAN, files: devices_mod.Files | Path | str | None = None) -> dict[str, float]:
    """{user name: plan inches} of every block: the length the drawings and the signal rules measure by."""
    return {name: b.plan_in for name, b in plan_blocks(path, files).items()}


def plan_cm(path: Path = PLAN, files: devices_mod.Files | Path | str | None = None) -> dict[str, float]:
    """{user name: plan length in cm} of every block."""
    return {name: inches * 2.54 for name, inches in plan_lengths(path, files).items()}


def plan_length(ident: str, path: Path = PLAN) -> float:
    """The plan length in inches of the block with device ID `ident`. FactsError when the plan file has no row."""
    try:
        return read_plan(path)[ident].plan_in
    except KeyError as exc:
        raise FactsError(f"{Path(path).name}: no row for {ident}") from exc


def measured_lengths(path: Path = PLAN, files: devices_mod.Files | Path | str | None = None) -> dict[str, Measured]:
    """{user name: Measured} of the measured blocks, in the measured file's order: for the pages that print a measured
    length beside the plan length. A plan-side reader never takes it as the block's length."""
    names = {b.id: name for name, b in plan_blocks(path, files).items()}
    return {names[m.id]: m for m in read_measured(plan=path).values()}


def detector_blocks(blocks: Mapping[str, Block]) -> dict[tuple[str, str], list[str]]:
    """{(level, occupancy sensor): block names} of `blocks` (plan_blocks): the JMRI blocks one detector reports, an OS
    block and its parts together."""
    out: dict[tuple[str, str], list[str]] = {}
    for name, b in blocks.items():
        out.setdefault((b.level, b.occupancy_sensor), []).append(name)
    return out


def operating_lengths(path: Path = PLAN, files: devices_mod.Files | Path | str | None = None) -> dict[str, float]:
    """{user name: inches} of every block: the plan length, except on a detector speed matching timed. A measured
    length is the timing of the whole detector, so the detector's blocks add up to it: each other block on it (a part
    of an OS block) keeps its plan length, and the measured block takes the measured length less theirs. The
    Dispatcher's block lengths (tables.xml) take it. FactsError on a detector with two measured blocks, or where the
    measured block's share would not be above zero."""
    blocks = plan_blocks(path, files)
    measured = read_measured(plan=path)
    out = {name: b.plan_in for name, b in blocks.items()}
    bad = []
    for names in detector_blocks(blocks).values():
        timed = [n for n in names if blocks[n].id in measured]
        if not timed:
            continue
        if len(timed) > 1:
            bad.append(f"detector {blocks[timed[0]].occupancy_sensor}: {', '.join(timed)} are all measured; one "
                       "measured length covers the whole detector")
            continue
        whole = measured[blocks[timed[0]].id].measured_in
        share = round(whole - sum(blocks[n].plan_in for n in names if n != timed[0]), 1)
        if share <= 0:
            bad.append(f"{timed[0]}: measured {whole} in for its detector {blocks[timed[0]].occupancy_sensor}, but "
                       f"its parts' plan lengths add up to {whole - share:.1f} in")
            continue
        out[timed[0]] = share
    if bad:
        raise FactsError("block lengths: " + "; ".join(bad))
    return out


def operating_length(ident: str, path: Path = PLAN) -> float:
    """The operating length in inches of the block with device ID `ident` (operating_lengths)."""
    for b, inches in zip(plan_blocks(path).values(), operating_lengths(path).values()):
        if b.id == ident:
            return inches
    raise FactsError(f"{Path(path).name}: no row for {ident}")


def measured_text(rows: Iterable[Measured]) -> str:
    """The measured file's text of `rows` (Measured, in the order given), measured_in to 0.1 in."""
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(MEASURED_COLUMNS)
    for m in rows:
        w.writerow([m.id, f"{m.measured_in:.1f}", m.run, m.date, m.note])
    return buf.getvalue()


def write_measured(rows: Iterable[Measured], plan: Path = PLAN) -> Path:
    """Write the measured file beside `plan` (speed matching's one writer: infer_block_lengths.py --apply). Each row
    is held to read_measured's rules first; FactsError on the first that breaks one, and nothing is written."""
    rows = list(rows)
    ids = read_plan(plan)
    out = measured_path(plan)
    seen: dict[str, Measured] = {}
    for n, m in enumerate(rows, 2):         # the line each row will have
        cells = {"id": m.id, "measured_in": f"{m.measured_in:.1f}", "run": m.run, "date": m.date, "note": m.note}
        seen[m.id] = _measured_row(cells, _where(out, n), n, ids, seen, Path(plan).name)
    out.write_text(measured_text(rows), encoding="utf-8")
    return out
