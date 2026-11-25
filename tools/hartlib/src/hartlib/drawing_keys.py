"""Which device each piece of the drawing is, keyed by device ID: the one reader of the device master's drawing keys
for every level (naming-layers step 13, builder merge step 7).

A turnout or block row of the device master lists the pieces of the solved schematic it holds in `trial_name`, in the
switch-and-leg grammar every level shares (tools/schematic/staging_device_map.py: "Switch 101A", "OS Switch 7",
"OS 7 A-13C", "Track 1B-3A 1/2", "Track 107B-107C #1"). `read` turns those cells into {drawing key: device ID}, and
the row an ID names is the merged view's (hartlib.devices.load: the generated file with the owner's cells over it),
so a name read here is the name store's answer for that ID (devices.user_names): the owner's if set, else the
generated one. The Layout Editor build (le_names.device_names, staging_device_map.load), the CATS desks
(cats_panel) and the staging device map look a piece up here, then name it by its ID.

A part (role part: a piece of track inside another block, its `part_of` naming that block) is read too: each is a JMRI
block of its own (owner, 2026-11-20). An LCC alias (role lcc_alias) holds no piece. `read` stops (DrawingKeyError,
listing every problem) on a turnout or block row with no key, a key two rows give, or a part whose `part_of` names no
block row of its levels.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping

from . import devices

LAYERS = ("turnout", "block")       # the rows that hold pieces of the drawing
LIST = ","                          # between the keys of a trial_name cell


class DrawingKeyError(ValueError):
    """The rows' drawing keys cannot be read as one device per piece."""


def keys_of(row: Mapping[str, str]) -> list[str]:
    """A row's drawing keys, in the order its trial_name gives them (a trailing "*", which a plan label may carry, is
    left off: the drawing's key is the bare one)."""
    return [k.strip().rstrip("*") for k in (row.get("trial_name") or "").split(LIST) if k.strip()]


@dataclass(frozen=True)
class Keys:
    """`ids`: {drawing key: device ID}; `rows`: {device ID: its row} of the levels read (turnout and block rows,
    parts among them; no LCC alias)."""
    ids: Mapping[str, str]
    rows: Mapping[str, Mapping[str, str]]

    def row(self, key: str) -> Mapping[str, str] | None:
        """The row of the device drawing key `key` is, or None."""
        i = self.ids.get(key)
        return None if i is None else self.rows[i]

    def name(self, key: str) -> str | None:
        """The name of the device `key` is (its ID's name in the merged view: the owner's, else the generated), or
        None."""
        r = self.row(key)
        return None if r is None else r["user_name"]

    def keys(self, device_id: str) -> frozenset[str]:
        """The drawing keys of device `device_id`."""
        return frozenset(k for k, i in self.ids.items() if i == device_id)

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


def read(levels: Iterable[str], source=None, rows: Iterable[Mapping[str, str]] | None = None) -> Keys:
    """The Keys of the turnout and block rows of `levels` ("1", "2", "3") of the merged master (`source`: a master's
    path or Files, as devices.load takes it), or of `rows` (master rows a builder is writing). DrawingKeyError on a
    row with no key, a key given twice or a part of no block row; DevicesError when the master cannot be read."""
    levels = tuple(str(lv) for lv in levels)
    every = list(devices.load(source) if rows is None else rows)
    mine = [r for r in every if r["level"] in levels and r["layer"] in LAYERS and r["role"] != "lcc_alias"]
    ids: dict[str, str] = {}
    by_id: dict[str, Mapping[str, str]] = {}
    bad = []
    for r in mine:
        what = devices.row_text(r)
        if not r.get("id"):
            bad.append(f"{what} has no id")
            continue
        if r["id"] in by_id:
            bad.append(f"{what}: id {r['id']} is {devices.row_text(by_id[r['id']])}'s as well")
            continue
        by_id[r["id"]] = r
        keys = keys_of(r)
        if not keys:
            bad.append(f"{what} has no trial_name")
        for k in keys:
            if k in ids:
                bad.append(f"trial_name {k} is given to {devices.row_text(by_id[ids[k]])} and {what}")
                continue
            ids[k] = r["id"]
    blocks = {r["user_name"] for r in mine if r["layer"] == "block" and r["role"] != "part"}
    for r in mine:
        if r["role"] == "part" and r.get("part_of") not in blocks:
            bad.append(f"part {devices.row_text(r)} is part of {r.get('part_of')!r}, no block row of level "
                       f"{'/'.join(levels)}")
    if bad:
        raise DrawingKeyError("; ".join(bad))
    return Keys(ids=MappingProxyType(ids), rows=MappingProxyType(by_id))
