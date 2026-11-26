"""The records and errors of analyze.py: a runner log's runs and steps, the profile rows, passes and block events.

The records are TypedDicts: parse_log fills a run while it reads the log, the rows are written to CSV by key, and
infer_block_lengths.py reads the passes by key. Positional tuples are NamedTuples. Standard library only: the Pi's
speed-match publisher imports analyze.py, and this file ships with it (tools/hosts/deploy/stage.sh).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple, TypedDict


class AnalyzeError(ValueError):
    """A log, routes.json or a lengths file this module cannot use as given; main() prints it and exits 1."""


class RoutesError(AnalyzeError):
    """routes.json is unreadable or does not match ROUTE_BLOCKS / ROUTE_MID_BLOCK (rebuild it)."""


class UnknownRouteError(AnalyzeError):
    """A route name that routes.json does not have."""


class LengthsError(AnalyzeError):
    """A block lengths file without the columns load_lengths reads."""


class LogError(AnalyzeError):
    """A runner log that cannot be replayed: old block names, a sensor off its route, or no RUN line."""


class Event(NamedTuple):
    """A sensor went ACTIVE at epoch t."""
    t: float
    sensor: str


class _Step(TypedDict):
    step: int
    occurrence: int  # 1 for the first time the step runs in its run, 2 for its repeat
    events: list[Event]


class StepRecord(_Step, total=False):
    """One STEP of a run. measuring (distance mode only): events count from MEASURE to FREEZE or STEPDONE."""
    measuring: bool
    done_reason: str


class RunRecord(TypedDict):
    """One RUN of a log (parse_log). cfg holds the CFG line's settings by their CFG_KEYS names; lengths is the
    LENGTHS line (sensor -> mm), None in logs without one; complete is the runner's "STOP all steps complete"."""
    loco: str
    direction: str
    steps: list[StepRecord]
    cfg: dict[str, int | float | str]
    lengths: dict[str, float | None] | None
    log: str
    complete: bool
    t0: float


class ProfileRow(TypedDict):
    """One step of a run, as profile.csv writes it: median and rel_sd are None without readings."""
    loco: str
    direction: str
    step: int
    occurrence: int
    travel: str
    n: int
    blocks: int
    run: int
    used: int
    reason: str
    median: float | None
    rel_sd: float | None
    settled: bool


class RunSummary(TypedDict):
    """One run of summarize_runs: its number (oldest first) and its rows."""
    run: int
    loco: str
    direction: str
    route: str
    log: str
    complete: bool
    rows: list[ProfileRow]


class PassRecord(TypedDict):
    """One PASS of a pass-job log (parse_pass_log)."""
    loco: str
    direction: str
    step: int
    frm: str
    to: str
    path: list[str]
    events: list[Event]
    reason: str
    log: str


class BlockReading(NamedTuple):
    """One whole block of a distance-mode step, as the BLOCK line has it."""
    sensor: str
    mm: float
    s: float


class DistanceReplay(NamedTuple):
    """replay_distance's answer: reason is 'settled', 'timed', 'max' or '' (the data ended first)."""
    blocks: list[BlockReading]
    reason: str
    relsd: float | None
    extra: object  # liverule.DistanceStep.extra, passed through unread


class EventRow(TypedDict):
    """One block transit (block_events); a length or speed the run does not have is ''."""
    loco: str
    log: str
    step: int
    lap_index: int
    block: str
    block_len_mm: float | str
    entry_epoch: str
    next_entry_epoch: str
    transit_s: float
    mm_per_s: float | str


Lengths = Mapping[str, "float | None"]  # sensor -> block length in mm, None where no trusted length
