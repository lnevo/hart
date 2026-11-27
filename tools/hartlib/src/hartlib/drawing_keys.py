"""Which device each piece of the drawing is, keyed by device ID: the one reader of the device master's drawing keys
for every level.

A turnout or block row of the device master lists the pieces of the solved schematic it holds in `trial_name`, in the
switch-and-leg grammar every level shares (tools/schematic/staging_device_map.py: "Switch 101A", "OS Switch 7",
"OS 7 A-13C", "Track 1B-3A 1/2", "Track 107B-107C #1"). `read` turns those cells into {drawing key: (level, device
ID)}, the master's key (hartlib.devices.KEY: an ID is unique on its level), and the row a key names is the merged
view's (hartlib.devices.load: the generated file with the owner's cells over it), so a name read here is the name
store's answer for that ID (devices.user_names): the owner's if set, else the generated one. The Layout Editor build
(le_names.device_names, staging_device_map.load) and the CATS desks (cats_panel) look a piece up here, then name it
by its ID.

A part (role part: a piece of track inside another block, its `part_of` naming that block) is read too: each is a JMRI
block of its own. An LCC alias (role lcc_alias) holds no piece. `read` stops (DrawingKeyError,
listing every problem) on a turnout or block row with no key or no id, a key two rows give, an id given twice on one
level, an LCC alias with a key, a part whose `part_of` names no block row of its own level, or a staging key with
the plan's trailing "*" (staging's keys are written exactly; only a main or upper plan label carries one, 223).
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from collections.abc import Iterable, Mapping
from pathlib import Path

from . import devices
from .railroad_facts import STAGING_LEVEL
from .errors import HartlibError

LAYERS = ("turnout", "block")       # the rows that hold pieces of the drawing
LIST = ","                          # between the keys of a trial_name cell

Key = tuple[str, str]               # (level, device ID): hartlib.devices.KEY


class DrawingKeyError(HartlibError, ValueError):
    """The rows' drawing keys cannot be read as one device per piece."""


def raw_keys(row: Mapping[str, str]) -> list[str]:
    """A row's trial_name keys as written, in order."""
    return [k.strip() for k in (row.get("trial_name") or "").split(LIST) if k.strip()]


def keys_of(row: Mapping[str, str]) -> list[str]:
    """A row's drawing keys, in the order its trial_name gives them (a trailing "*", which a main or upper plan label
    may carry, is left off: the drawing's key is the bare one)."""
    return [k.rstrip("*") for k in raw_keys(row)]


@dataclass(frozen=True)
class Keys:
    """`ids`: {drawing key: (level, device ID)}; `rows`: {(level, device ID): its row} of the levels read (turnout
    and block rows, parts among them; no LCC alias)."""
    ids: Mapping[str, Key]
    rows: Mapping[Key, Mapping[str, str]]

    def id(self, key: str) -> str | None:
        """The device ID drawing key `key` is, or None."""
        k = self.ids.get(key)
        return None if k is None else k[1]

    def row(self, key: str) -> Mapping[str, str] | None:
        """The row of the device drawing key `key` is, or None."""
        k = self.ids.get(key)
        return None if k is None else self.rows[k]

    def name(self, key: str) -> str | None:
        """The name of the device `key` is (its ID's name in the merged view: the owner's, else the generated), or
        None."""
        r = self.row(key)
        return None if r is None else r["user_name"]

    def keys(self, device_id: str, level: str | None = None) -> frozenset[str]:
        """The drawing keys of device `device_id` (on `level` when given)."""
        return frozenset(k for k, (lv, i) in self.ids.items() if i == device_id and level in (None, lv))

    def of(self, layer: str, role: str | None = None, parts: bool | None = None) -> dict[str, str]:
        """{drawing key: name} of the `layer` rows (only `role`'s when given; parts alone when `parts` is True,
        none when False)."""
        out = {}
        for k, i in self.ids.items():
            r = self.rows[i]
            if r["layer"] != layer or (role is not None and r["role"] != role):
                continue
            if parts is not None and (r["role"] == "part") != parts:
                continue
            out[k] = r["user_name"]
        return out

    def parts(self) -> dict[str, str]:
        """{part name: the block it is part of} of the parts read."""
        return {r["user_name"]: r["part_of"] for r in self.rows.values() if r["role"] == "part"}


def read(levels: Iterable[str], source: devices.Files | Path | str | None = None,
         rows: Iterable[Mapping[str, str]] | None = None) -> Keys:
    """The Keys of the turnout and block rows of `levels` ("1", "2", "3") of the merged master (`source`: a master's
    path or Files, as devices.load takes it), or of `rows` (master rows a builder is writing). Either way the rows
    are read and kept as the master's text (MasterRow.cells for the merged view's). DrawingKeyError on the problems
    the module names; DevicesError when the master cannot be read."""
    levels = tuple(str(lv) for lv in levels)
    mine: list[Mapping[str, str]]
    if rows is None:
        mine = [r.cells() for r in devices.load(source) if r.level_cell in levels and r.layer in LAYERS]
    else:
        mine = [r for r in rows if r["level"] in levels and r["layer"] in LAYERS]
    ids: dict[str, Key] = {}
    by_id: dict[Key, Mapping[str, str]] = {}
    bad = []
    for r in mine:
        what = devices.row_text(r)
        if r["role"] == "lcc_alias":
            if raw_keys(r):
                bad.append(f"{what} is an LCC alias, which holds no piece, and has trial_name {r['trial_name']!r}")
            continue
        if not r.get("id"):
            bad.append(f"{what} has no id")
            continue
        key = (r["level"], r["id"])
        if key in by_id:
            bad.append(f"{what}: id {r['id']} is {devices.row_text(by_id[key])}'s as well")
            continue
        by_id[key] = r
        written = raw_keys(r)
        if not written:
            bad.append(f"{what} has no trial_name")
        if r["level"] == str(STAGING_LEVEL):
            starred = [k for k in written if k.endswith("*")]
            if starred:
                bad.append(f"{what}: staging keys are written exactly, with no plan '*': {starred}")
        for k in keys_of(r):
            if k in ids:
                bad.append(f"trial_name {k} is given to {devices.row_text(by_id[ids[k]])} and {what}")
                continue
            ids[k] = key
    blocks = {(r["level"], r["user_name"]) for r in by_id.values() if r["layer"] == "block" and r["role"] != "part"}
    for r in by_id.values():
        if r["role"] == "part" and (r["level"], r.get("part_of")) not in blocks:
            bad.append(f"part {devices.row_text(r)} is part of {r.get('part_of')!r}, no block row of level "
                       f"{r['level']}")
    if bad:
        raise DrawingKeyError("; ".join(bad))
    return Keys(ids=MappingProxyType(ids), rows=MappingProxyType(by_id))
