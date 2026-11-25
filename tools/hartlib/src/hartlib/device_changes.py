"""What a write of the device master changes, by device ID (ADR-033, naming-layers step 4).

A builder's write (hartlib.devices.outputs_after_rows) is held to the last generated file, row by row on its key
(level, id; hartlib.devices.KEY):

- new and gone IDs are listed, one line per level and layer;
- a gone ID that devices_field.csv holds owner's cells for stops the write (decision 3 of the naming-layers
  hand-off, owner 2026-11-24): the owner moves the cells to the device's new ID or drops them. The stop lists the new
  IDs of the same level and layer, as the likely new home;
- a rename (one ID, another user name) lists the copies of the old name in the repo's Operations Pro files
  (decision 5: Operations Pro keeps its own names and nothing rewrites them; STS is not checked);
- a mast rename warns that JMRI keys Signal Mast Logic by mast user name, so it needs a new SML discovery and the
  owner's panel approval (decision 6).

The lines go to a `warn` callable (default: stderr), so a build prints them and a test collects them.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping

from . import devices, paths

# the repo's Operations Pro files (ADR-015: the repo is the master), the copies decision 5 lists
OPERATIONS = paths.LAYOUT_DIR / "operations"
SML_DISCOVERY = "jmri/layouts/hart/scripts/run_sml_discover.sh"


@dataclass(frozen=True)
class Changes:
    """The difference of two generated files' rows by KEY: rows whose key only the new one has, only the old one
    has, and (old row, new row) pairs of one key with different user names."""
    new: tuple[Mapping[str, str], ...]
    gone: tuple[Mapping[str, str], ...]
    renamed: tuple[tuple[Mapping[str, str], Mapping[str, str]], ...]

    def __bool__(self) -> bool:
        return bool(self.new or self.gone or self.renamed)


def compare(old: Iterable[Mapping[str, str]], new: Iterable[Mapping[str, str]]) -> Changes:
    """The Changes from rows `old` (the last generated file) to rows `new` (the one a write gives), each by KEY; rows
    with no level (a Store's, which no builder writes) are left out."""
    was = {devices.key_of(r): r for r in old if r["level"]}
    now = {devices.key_of(r): r for r in new if r["level"]}
    return Changes(tuple(r for k, r in now.items() if k not in was),
                   tuple(r for k, r in was.items() if k not in now),
                   tuple((was[k], r) for k, r in now.items() if k in was and was[k]["user_name"] != r["user_name"]))


def held_gone(changes: Changes, field: Iterable[Mapping[str, str]]) -> list[str]:
    """Decision 3: one problem per gone ID that a field row holds owner's cells for, naming the cells and the new IDs
    of its level and layer (where they may belong)."""
    keyed = {devices.key_of(r): r for r in field if r["level"]}
    out = []
    for g in changes.gone:
        f = keyed.get(devices.key_of(g))
        if f is None:
            continue
        cells = [f"{c} {f[c]!r}" for c in devices.FIELD_COLUMNS if f[c]]
        near = [r["id"] for r in changes.new if r["level"] == g["level"] and r["layer"] == g["layer"]]
        out.append(f"{devices.FIELD_FILE}: id {g['id']!r} ({devices.row_text(g)}) is gone from the plan, and its "
                   f"field row holds {', '.join(cells) or 'no cells'}: move them to the device's new id"
                   + (f" (new on level {g['level']}, {g['layer']}: {', '.join(near)})" if near else "")
                   + ", or remove the row")
    return out


def _quoted(name: str) -> re.Pattern[str]:
    """The name as a whole name, as tools/audit/check_name_copies.py matches it: not inside a longer word, and not the
    tail of a longer name ("Switch 3" in "DCC Switch 3": a word and a space before it)."""
    return re.compile(r"(?<![\w-])(?<!\w )" + re.escape(name) + r"(?![\w-])")


def ops_copies(name: str, folder: Path = OPERATIONS) -> list[str]:
    """"<file>:<line>" of each line of the Operations Pro files in `folder` that holds `name` as a whole name
    (_quoted), or, for a track ("Track X"), its bare name X as the name attribute of a track or location element
    (<track ... name="X">), as Operations Pro names a track on a location. [] when the folder is not there."""
    if not folder.is_dir():
        return []
    pats = [_quoted(name)]
    if name.startswith("Track "):
        bare = re.escape(name.removeprefix("Track "))
        pats.append(re.compile(r'<(?:track|location)\b[^>]*?\sname="' + bare + '"'))
    out = []
    for path in sorted(folder.glob("*.xml")):
        for no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if any(p.search(line) for p in pats):
                out.append(f"{path.name}:{no}")
    return out


CHECK_ONLY = "check only, nothing written: "     # the mark of a line said by a --check run


def lines(writer: str, changes: Changes, ops: Path = OPERATIONS) -> list[str]:
    """What a build prints of `changes`: the new and gone IDs (one line per level and layer), each rename with the
    Operations Pro copies of its old name, and a warning on each mast rename."""
    out = []
    for what, rows in (("new", changes.new), ("gone", changes.gone)):
        groups: dict[tuple[str, str], list[str]] = {}
        for r in rows:
            groups.setdefault((r["level"], r["layer"]), []).append(r["id"])
        out += [f"{writer}: {len(ids)} {what} ID(s) on level {level}, {layer}: {', '.join(ids)}"
                for (level, layer), ids in sorted(groups.items())]
    for old, new in changes.renamed:
        copies = ops_copies(old["user_name"], ops)
        out.append(f"{writer}: id {new['id']!r} (level {new['level']}, {new['layer']}) is renamed "
                   f"{old['user_name']!r} -> {new['user_name']!r}; "
                   + (f"the Operations Pro files hold the old name at {', '.join(copies)} (nothing rewrites them)"
                      if copies else "no Operations Pro file holds the old name"))
        if new["layer"] == "mast":
            out.append(f"warning: {writer}: mast {old['user_name']!r} is now {new['user_name']!r}: JMRI keys Signal "
                       f"Mast Logic by mast user name, so this needs a new SML discovery ({SML_DISCOVERY}) and the "
                       "owner's panel approval")
    return out


def _stderr(line: str) -> None:
    print(line, file=sys.stderr)


def stop(old: Iterable[Mapping[str, str]], new: Iterable[Mapping[str, str]],
         field: Iterable[Mapping[str, str]]) -> Changes:
    """The Changes from the last generated file (`old`) to a write's generated rows (`new`); DevicesError listing
    each gone ID the field file holds owner's cells for (held_gone, decision 3). Says nothing (say does, once the
    write has merged back)."""
    changes = compare(old, new)
    bad = held_gone(changes, list(field))
    if bad:
        raise devices.DevicesError("; ".join(bad))
    return changes


def say(writer: str, changes: Changes, warn: Callable[[str], None] | None = None, check: bool = False,
        ops: Path = OPERATIONS) -> None:
    """Each line of `lines` to `warn` (default: stderr), marked CHECK_ONLY when `check` (a --check run)."""
    for line in lines(writer, changes, ops):
        (warn or _stderr)((CHECK_ONLY if check else "") + line)


def report(writer: str, old: Iterable[Mapping[str, str]], new: Iterable[Mapping[str, str]],
           field: Iterable[Mapping[str, str]], warn: Callable[[str], None] | None = None,
           ops: Path = OPERATIONS, check: bool = False) -> Changes:
    """stop, then say: a write held to the last generated file and what it changes said. The Changes."""
    changes = stop(old, new, field)
    say(writer, changes, warn, check, ops)
    return changes