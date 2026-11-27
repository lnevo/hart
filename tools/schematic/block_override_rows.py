"""block_overrides.csv for the schematic builders: its rows (hartlib.hand_lists.read_block_overrides, the file's one
reader, which has the kinds and row shapes), the OS block names it gives, the track each row names and the owner's
block splits.

A row names a track by its end switches (plan_tracks.track_key) and `parallel`, so a renumbered switch moves the row
with it; resolve_track finds that track among the named tracks. read_block_splits gives the tracks the split rows part
into two blocks at their turnback, which is the owner's choice, not a rule. hartlib's HandListError comes out as a
MapError.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from hartlib import hand_lists
from map_error import MapError
from plan_tracks import Track, plan_order, track_key

OVERRIDES_NAME = hand_lists.OVERRIDES_NAME     # in the schematic data folder, beside plan_overrides.json
OVERRIDE_COLUMNS = hand_lists.OVERRIDE_COLUMNS
OVERRIDE_KINDS = hand_lists.OVERRIDE_KINDS

OverrideRow = dict[str, Any]       # one checked row of block_overrides.csv, as hand_lists.read_block_overrides gives it


def read_block_overrides(path: Path, kinds: tuple[str, ...] = OVERRIDE_KINDS) -> list[OverrideRow]:
    """hartlib.hand_lists.read_block_overrides (its text has the kinds and rows), its HandListError a MapError."""
    try:
        return hand_lists.read_block_overrides(path, kinds)
    except hand_lists.HandListError as exc:
        raise MapError(str(exc)) from exc


def os_block_name(level: str, ident: str, halves: Mapping[tuple[str, str, str], str],
                  names: Mapping[tuple[str, str], str] | None = None) -> str:
    """hartlib.hand_lists.os_block_name, its HandListError a MapError."""
    try:
        return hand_lists.os_block_name(level, ident, halves, names)
    except hand_lists.HandListError as exc:
        raise MapError(str(exc)) from exc


def resolve_track(row: OverrideRow, found: Sequence[Track]) -> Track | None:
    """The one track entry of `found` the row's switches (and `parallel`) name, or None with the reason in
    row["problem"]: no track, or several with no `parallel` to choose (the candidates named, in plan_order)."""
    key = (row["switch_a"], row["switch_b"])
    same = [t for t in found if track_key(t) == key]
    if len(same) > 1:
        same.sort(key=plan_order)
    label = f"Switch {key[0]}" + (f" to Switch {key[1]}" if key[1] else " spur")
    if not same:
        near = sorted({t["name"] for t in found
                       if (tk := track_key(t)) and set(key[:1 + bool(key[1])]) & set(tk)})
        row["problem"] = f"no track runs {label} (tracks at those switches: {', '.join(near) or 'none'})"
        return None
    if row["parallel"]:
        k = int(row["parallel"])
        if len(same) < 2 or k > len(same):
            row["problem"] = (f"parallel {k} of {label}, but {len(same)} track{'s' * (len(same) != 1)} run there "
                              f"({', '.join(t['name'] for t in same)})")
            return None
        return same[k - 1]
    if len(same) > 1:
        row["problem"] = (f"{len(same)} tracks run {label} ({', '.join(t['name'] for t in same)}): "
                          "give parallel, 1 for the first by plan ends (plan_tracks.plan_order)")
        return None
    return same[0]


def read_block_splits(path: Path, found: Sequence[Track], levels: Mapping[str, int]) -> set[str]:
    """The names of the tracks block_overrides.csv's split rows (read_block_overrides) part into two blocks at their
    turnback, among `found` and the `levels` ({band key: level}) asked for, each row's end switches resolved at build
    time. Stops on a row naming no track or a track on another level, or a track two rows name. A row of a level not
    asked for is checked for shape only."""
    wanted = set(levels.values())
    rows = read_block_overrides(path, ("split",))
    out: set[str] = set()
    seen: dict[str, str] = {}
    bad: list[str] = []
    for r in rows:
        if int(r["level"]) not in wanted:
            continue
        t = resolve_track(r, [t for t in found if t["level"] == int(r["level"])])
        if t is None:
            bad.append(f"line {r['line']}: level {r['level']}: {r['problem']}")
        elif t["name"] in seen:
            bad.append(f"line {r['line']}: {t['name']} is already split on line {seen[t['name']]}")
        else:
            seen[t["name"]] = r["line"]
            out.add(t["name"])
    if bad:
        raise MapError(f"{path.name}: " + "; ".join(bad))
    return out
