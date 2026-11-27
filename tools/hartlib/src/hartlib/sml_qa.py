"""The native SML QA's steps (jmri/layouts/hart/data/native_sml_qa.csv), read, and the staging devices they drive,
by device ID from the device master (hartlib.devices).

    from hartlib import sml_qa
    steps = sml_qa.read()             # tuple of Step, in run order
    drives = sml_qa.drives(steps)     # {device id: Drive}: its user name, LCOS MQTT address and feedback sensors

tools/mqtt-mimic/qa/run_native_sml_qa.py is the one reader. The file has one row per part of a step (`part`): the
step's `about` row holds its description (`text`); a `before` or `after` row drives one device (`device`, a device ID
of staging) to a `state`; an `expect` row names a mast and the aspect it must show (`want`: stop, nonstop or an
aspect name). `tag` (qaNN_words) and `n` key a row: the steps run in the order of their NN, and a step's rows in the
order of `n`. native_sml_qa.columns.csv beside it gives the column rules check_data.py checks.

A turnout state (CLOSED, THROWN) drives a turnout row (role turnout) and an occupancy state (ACTIVE, INACTIVE) an
occupancy row. A turnout drives its feedback sensors too when the master has both of its fb rows (fb:<n>:N and
fb:<n>:R), and none when it has neither. QAError names the file and line, or the device, on any other shape.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import NamedTuple

from . import devices, paths
from .device_rows import MasterRow
from .errors import HartlibError
from .levels import STAGING
from .railroad_facts import FactsError, read_rows

PATH = paths.LAYOUT_DATA / "native_sml_qa.csv"
COLUMNS = ("tag", "n", "part", "device", "state", "mast", "want", "text")
PARTS = ("about", "before", "expect", "after")
# the cells each part must fill; every other cell but text (a note for people) stays empty
PART_CELLS = {"about": ("text",), "before": ("device", "state"), "after": ("device", "state"),
              "expect": ("mast", "want")}
STATE_LAYER = {"CLOSED": "turnout", "THROWN": "turnout", "ACTIVE": "occupancy", "INACTIVE": "occupancy"}
# the LCOS MQTT system name prefix of each layer the QA drives: the address is what follows it
PREFIX = {"turnout": "M2T", "occupancy": "M2S", "fb": "M2S"}
TAG = re.compile(r"qa(\d\d)_[A-Za-z0-9_]+")
SWITCH = re.compile(r"switch:([1-9]\d*)")


class QAError(HartlibError, ValueError):
    """The steps file or a device it names is not in its shape; the message names the file and line or the device."""


class Change(NamedTuple):
    """One retained state a step drives: a device ID of staging and its state."""
    device: str
    state: str
    line: int


class Step(NamedTuple):
    """Drive `before`, wait, read the masts and check `expect` ((mast, want) in order), then drive `after`."""
    tag: str
    desc: str
    expect: tuple[tuple[str, str], ...]
    before: tuple[Change, ...]
    after: tuple[Change, ...]


class Drive(NamedTuple):
    """A device the steps drive: a turnout with its feedback sensors' addresses (normal, reverse) or None, or an
    occupancy sensor (feedback None)."""
    id: str
    user_name: str
    layer: str
    address: str
    feedback: tuple[str, str] | None


def _row_problem(row: Mapping[str, str]) -> str:
    part = row["part"]
    if part not in PARTS:
        return f"part {part!r} is not one of {', '.join(PARTS)}"
    need = PART_CELLS[part]
    missing = [c for c in need if not row[c]]
    if missing:
        return f"a {part} row needs {' and '.join(missing)}"
    extra = [c for c in COLUMNS[3:] if c != "text" and c not in need and row[c]]
    if extra:
        return f"a {part} row has no {' or '.join(extra)}"
    if row["state"] and row["state"] not in STATE_LAYER:
        return f"state {row['state']!r} is not one of {', '.join(STATE_LAYER)}"
    return ""


def read(path: Path = PATH) -> tuple[Step, ...]:
    """The steps of the file, in run order. QAError naming the file and line on a missing file or column, a bad tag,
    n, part or state, a cell its part does not take, a tag and n given twice, two steps with one number, a step with
    no about row or two, and a mast expected twice in one step."""
    try:
        rows = read_rows(path, COLUMNS)
    except FactsError as exc:
        raise QAError(str(exc)) from exc
    by_tag: dict[str, list[tuple[int, int, dict[str, str]]]] = {}
    numbers: dict[int, str] = {}
    for line, row in rows:
        where = f"{path}:{line}"
        m = TAG.fullmatch(row["tag"])
        if not m:
            raise QAError(f"{where}: tag {row['tag']!r} is not qaNN_words (qa00_rest)")
        if numbers.setdefault(int(m.group(1)), row["tag"]) != row["tag"]:
            raise QAError(f"{where}: {row['tag']} has the number of {numbers[int(m.group(1))]}")
        if not row["n"].isdigit() or int(row["n"]) < 1:
            raise QAError(f"{where}: n {row['n']!r} is not a whole number from 1")
        problem = _row_problem(row)
        if problem:
            raise QAError(f"{where}: {problem}")
        n = int(row["n"])
        held = by_tag.setdefault(row["tag"], [])
        if any(k == n for k, _, _ in held):
            raise QAError(f"{where}: {row['tag']} n {n} is given twice")
        held.append((n, line, row))
    steps = [_step(path, tag, sorted(held)) for tag, held in by_tag.items()]
    return tuple(sorted(steps, key=lambda s: s.tag))


def _step(path: Path, tag: str, rows: list[tuple[int, int, dict[str, str]]]) -> Step:
    about = [r["text"] for _, _, r in rows if r["part"] == "about"]
    if len(about) != 1:
        raise QAError(f"{path}: {tag} has {len(about)} about rows, not one")
    expect: dict[str, str] = {}
    for _, line, r in rows:
        if r["part"] == "expect":
            if r["mast"] in expect:
                raise QAError(f"{path}:{line}: {tag} expects {r['mast']} twice")
            expect[r["mast"]] = r["want"]

    def changes(part: str) -> tuple[Change, ...]:
        return tuple(Change(r["device"], r["state"], line) for _, line, r in rows if r["part"] == part)
    return Step(tag, about[0], tuple(expect.items()), changes("before"), changes("after"))


def _address(row: MasterRow, ident: str) -> str:
    prefix = PREFIX[row.layer]
    if not row.system_name.startswith(prefix) or not row.system_name[len(prefix):].isdigit():
        raise QAError(f"{row.user_name} ({ident}): system name {row.system_name!r} is not {prefix}<number>, an LCOS "
                      "MQTT device")
    return row.system_name[len(prefix):]


def drives(steps: Iterable[Step], rows: Iterable[MasterRow] | None = None, path: Path = PATH) -> dict[str, Drive]:
    """{device id: Drive} of every device the steps drive, in the order they first name it, from the staging rows of
    the device master (`rows`, default hartlib.devices.load()). QAError on an ID with no staging row, a state its
    row's layer or role does not take, a system name that is not an LCOS MQTT one, and a turnout with one of its two
    fb rows."""
    by_id = {r.id: r for r in (devices.load() if rows is None else rows) if r.level == STAGING and r.id}
    out: dict[str, Drive] = {}
    for step in steps:
        for change in (*step.before, *step.after):
            where = f"{path}:{change.line}"
            row = by_id.get(change.device)
            if row is None:
                raise QAError(f"{where}: {change.device} is no staging device ID of the device master")
            layer = STATE_LAYER[change.state]
            if row.layer != layer or (layer == "turnout" and row.role != "turnout"):
                raise QAError(f"{where}: {change.state} drives a {layer} row; {row.user_name} ({change.device}) is a "
                              f"{row.layer} row (role {row.role or 'none'})")
            if change.device not in out:
                out[change.device] = Drive(change.device, row.user_name, layer, _address(row, change.device),
                                           _feedback(row, change.device, by_id) if layer == "turnout" else None)
    return out


def _feedback(row: MasterRow, ident: str, by_id: Mapping[str, MasterRow]) -> tuple[str, str] | None:
    m = SWITCH.fullmatch(ident)
    if not m:
        raise QAError(f"{row.user_name} ({ident}): a turnout ID is switch:<n>")
    normal, reverse = by_id.get(f"fb:{m.group(1)}:N"), by_id.get(f"fb:{m.group(1)}:R")
    if normal is None and reverse is None:
        return None
    if normal is None or reverse is None:
        have = "N" if normal is not None else "R"
        raise QAError(f"{row.user_name} ({ident}): the device master has fb:{m.group(1)}:{have} but not the other "
                      "feedback sensor; a turnout has both or neither")
    return _address(normal, normal.id), _address(reverse, reverse.id)
