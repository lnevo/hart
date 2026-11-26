"""switches.csv's rows read and checked (hartlib.railroad_facts.read_switch_rows), one step per concern.
railroad_facts.read_switch_rows calls read here; this module reads railroad_facts' columns and records, so it is
imported when the read runs."""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

from .errors import FactsError
from .levels import ALL_LEVELS, Level, parse_level
from .railroad_facts import (HAND_SOURCES, HANDS, LEG_IDS, STAGING_ONLY, SWITCH_COLUMNS, SWITCH_WIDE, SwitchNames,
                             SwitchRow, _int, _no_label_columns, _where, read_rows, switch_groups, switch_names)


class _LegNames:
    """The name store read_switch_rows names an OS-keyed row's legs from: `given`, a callable that gives it, or
    switch_names of `path`, each loaded at the first row that needs it (main and upper rows need no master)."""

    def __init__(self, path: Path, given: SwitchNames | Callable[[], SwitchNames] | None) -> None:
        self.path, self.given = path, given
        self.names: SwitchNames | None = None

    def __call__(self) -> SwitchNames:
        if self.names is None:
            given = self.given
            self.names = switch_names(self.path) if given is None else given() if callable(given) else given
        return self.names


def _check_together(n: int, level: Level, line: int, later: bool, first_of: Mapping[int, tuple[int, int]],
                    path: Path, where: str) -> None:
    """A switch number is on one level, and its rows go together."""
    if n not in first_of:
        return
    lv, ln = first_of[n]
    if lv != level:
        raise FactsError(f"{path.name} lines {ln} (level {lv}) and {line} (level {level}) both use Switch {n}; "
                         "switch numbers are unique railroad-wide")
    if not later:
        raise FactsError(f"{where}: Switch {n} is also on line {ln}; a switch's rows go together")


def _leg_labels(r: Mapping[str, str], n: int, level: Level, by_os: bool, names: _LegNames,
                where: str) -> dict[str, str]:
    """An OS-keyed row's os_block, closed_leg and thrown_leg: the name store's names of its device IDs (the name is
    the owner's, a rename in devices_field.csv is allowed: only the ID carries the number). A half-keyed row has no
    OS block or legs, and no leg IDs."""
    labels = dict.fromkeys(LEG_IDS, "")
    if not by_os:
        if any(r[c] for c in LEG_IDS.values()):
            raise FactsError(f"{where}: closed_id and thrown_id go with an os_id (a row keyed by its OS block); a "
                             "row keyed by its half leaves them blank")
        return labels
    if not re.fullmatch(rf"os:{n}(:[A-Z0-9-]+)?", r["os_id"]) or not r["closed_id"] or not r["thrown_id"]:
        raise FactsError(f"{where}: a row keyed by its OS block gives the device IDs of it (os_id os:{n}, "
                         f"or os:{n}:<half>) and of its legs (closed_id, thrown_id), not {r['os_id']!r}, "
                         f"{r['closed_id']!r}, {r['thrown_id']!r}")
    store = names()
    for label, ident in LEG_IDS.items():
        name = store.get((str(level), r[ident]))
        if not name:
            raise FactsError(f"{where}: {ident} {r[ident]} is no level {level} device of the device master "
                             "(a new export dropped it, or the ID is mistyped: give the device's id)")
        labels[label] = name
    return labels


def _check_key_cells(r: Mapping[str, str], n: int, by_os: bool, where: str) -> None:
    """An OS-keyed row has no half and an owner's hand; a half-keyed row's half is its number (or with A or B) and
    it leaves the live bindings (STAGING_ONLY) blank."""
    if by_os:
        if r["half"]:
            raise FactsError(f"{where}: a row keyed by its OS block has no half (its os_block is its key), not "
                             f"{r['half']!r}")
        if r["hand_source"] == "plan":
            raise FactsError(f"{where}: hand_source plan is for rows keyed by their half (build_hands.py); the "
                             "hands of rows keyed by their OS block are the owner's")
        return
    if r["half"] not in (str(n), f"{n}A", f"{n}B"):
        raise FactsError(f"{where}: half is {n}, {n}A or {n}B, not {r['half']!r}")
    given = [c for c in STAGING_ONLY if r[c]]
    if given:
        raise FactsError(f"{where}: {', '.join(given)} bind a row keyed by its OS block (staging's) to the "
                         "live panels; a row keyed by its half leaves them blank")


def _check_hand(r: Mapping[str, str], by_os: bool, later: bool, first_line: int, where: str) -> None:
    """hand is L, R or blank with its hand_source (a plan row may wait for build_hands.py to fill its hand; an owner
    row gives one); a whole-switch column, and an OS-keyed switch's hand (Switch.hand), only on its first row."""
    if r["hand"] not in HANDS:
        raise FactsError(f"{where}: hand is L, R or blank, got {r['hand']!r}")
    if ((r["hand"] and not r["hand_source"]) or (r["hand_source"] and r["hand_source"] not in HAND_SOURCES)
            or (r["hand_source"] == "owner" and not r["hand"])):
        raise FactsError(f"{where}: a hand needs a hand_source ({' or '.join(HAND_SOURCES)}), and an owner "
                         f"hand_source a hand; got hand {r['hand']!r}, hand_source {r['hand_source']!r}")
    wide = SWITCH_WIDE + (("hand", "hand_source") if by_os else ())
    repeated = [c for c in wide if later and r[c]]
    if repeated:
        raise FactsError(f"{where}: {', '.join(repeated)} hold a fact of the whole switch: give them on its first "
                         f"row (line {first_line}) only")


def _check_groups(out: Iterable[SwitchRow], path: Path) -> None:
    """A switch's rows are all keyed by their OS block or all by their half; a half-keyed switch has half {n}, or
    halves {n}A and {n}B."""
    for n, rs in switch_groups(out, ALL_LEVELS).items():
        if any(r.by_os for r in rs):
            if not all(r.by_os for r in rs):
                raise FactsError(f"{_where(path, rs[0].line)} (Switch {n}): a switch's rows are all keyed by their OS "
                                 "block (os_id) or all by their half")
            continue
        halves = sorted(r.half for r in rs)
        if halves not in ([str(n)], [f"{n}A", f"{n}B"]):
            raise FactsError(f"{_where(path, rs[0].line)} (Switch {n}): a switch keyed by its halves has one row, "
                             f"half {n}, or two, halves {n}A and {n}B; not {', '.join(halves)}")


def read(path: Path, names: SwitchNames | Callable[[], SwitchNames] | None = None) -> list[SwitchRow]:
    """hartlib.railroad_facts.read_switch_rows, in named steps."""
    _no_label_columns(path)
    leg_names = _LegNames(path, names)
    out: list[SwitchRow] = []
    keys: dict[str, int] = {}
    first_of: dict[int, tuple[int, int]] = {}          # switch -> (level, line of its first row)
    for line, r in read_rows(path, SWITCH_COLUMNS):
        n = _int(r["switch"], _where(path, line), "switch")
        where = f"{_where(path, line)} (Switch {n})"
        level = parse_level(r["level"], where)
        later = bool(out) and out[-1].switch == n
        _check_together(n, level, line, later, first_of, path, where)
        first_of.setdefault(n, (level, line))
        by_os = bool(r["os_id"])                        # the row's key, not its level, gives its shape
        if by_os != (level == 1):
            # only staging's switches are bound to the live panels (staging_switches, switch_turnouts) so far: a main
            # or upper row is keyed by its half until its switches are bound
            raise FactsError(f"{where}: a staging row is keyed by its OS block and gives the device IDs of it (os_id "
                             f"os:{n}, or os:{n}:<half>) and of its legs (closed_id, thrown_id); a main or upper row "
                             f"is keyed by its half until its switches are bound; not os_id {r['os_id']!r}")
        labels = _leg_labels(r, n, level, by_os, leg_names, where)
        _check_key_cells(r, n, by_os, where)
        _check_hand(r, by_os, later, first_of[n][1], where)
        row = SwitchRow(line, level, n, **labels, **{c: r[c] for c in SWITCH_COLUMNS[2:]})
        if row.key in keys:
            raise FactsError(f"{path.name} lines {keys[row.key]} and {line}: both are {row.key}")
        keys[row.key] = line
        out.append(row)
    _check_groups(out, path)
    return out
