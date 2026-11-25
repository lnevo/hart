"""The main and upper blocks' JMRI numbers: block_numbering.csv's one reader and the rule that numbers them
(naming-layers step 8, builder merge step 2).

    from hartlib import block_numbering
    numbering = block_numbering.read(names=names)      # block_numbering.csv, its ids named by `names`
    block_numbering.bean_names(blocks, numbering)       # {block: (IB:C3:<nnnn>, ILB<1000 + n>)}

Each main and upper block is a JMRI block IB:C3:<nnnn> (level_devices.BLOCK_PREFIX) and a layout block
ILB<LAYOUT_BLOCK_FIRST - 1 + nnnn>, numbered once over both levels in block_sort order: OS blocks first, then the
rest, each by the number at the end of its name. Blocks added after the cut-over take the next numbers at the end
(owner, 2026-11-16: append), so no main or upper system name shifts. block_numbering.csv holds them: a renamed block
gets the sort place of the name it replaces (numbered_as), an appended one comes last in append_order, and a retired
one (a block gone from the levels, such as the main and upper helix pieces joined into one staging block per helix
track on 2026-11-20) keeps its number taken, unused, so no block after it is renumbered. A live block is given by its
device ID (naming-layers step 5), its name the name store's, so a rename changes no row; a retired block has no ID
any more, so its row gives the name it had (retired), and numbered_as is the name whose sort place a block takes (a
name no block has now).

The owner keeps today's numbers until those levels are wired for good (2026-11-23): build_device_map.py copies
them into the block rows' jmri_name and layout_block, and the Layout Editor build (le_tables) reads them there.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from . import level_devices, paths

PATH = paths.LAYOUT_DATA / "schematic" / "block_numbering.csv"
COLUMNS = ["id", "numbered_as", "append_order", "retired", "notes"]
LEVELS = ("2", "3")


class NumberingError(ValueError):
    """block_numbering.csv cannot be read, is not in its shape or does not fit the blocks; the message says where."""


@dataclass(frozen=True)
class Numbering:
    """block_numbering.csv by block name: {block: the name whose sort place it takes}, the appended blocks in
    append order and the retired blocks' old names."""
    numbered_as: Mapping[str, str]
    appended: tuple[str, ...]
    retired: tuple[str, ...]


def read(path: Path = PATH, names: Mapping[tuple[str, str], str] | None = None) -> Numbering:
    """block_numbering.csv, by block name. A row gives a main or upper block's id and exactly one of numbered_as or
    append_order, or no id and the retired block's name in retired; blocks are listed once, append_order counts 1, 2,
    3 ... without a gap, and a name a block is numbered as is not itself a listed block. Each id is named by `names`
    ({(level, id): user name}, default hartlib.devices.user_names(), the repo's), on level 2 or 3. NumberingError on
    any problem, an id neither level has included."""
    path = Path(path)
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    except OSError as exc:
        raise NumberingError(f"{path.name}: cannot read it ({exc.strerror})") from None
    if not rows or list(rows[0]) != COLUMNS:
        raise NumberingError(f"{path.name}: expected the columns {', '.join(COLUMNS)}")
    if names is None and any((r["id"] or "").strip() for r in rows):
        from . import devices           # the device master reads this module's callers' outputs: import on use
        names = devices.user_names()
    numbered, appended, retired, seen = {}, {}, [], set()
    for n, r in enumerate(rows, 2):
        ident, as_, order, gone = ((r[c] or "").strip() for c in ("id", "numbered_as", "append_order", "retired"))
        if bool(ident) == bool(gone):
            raise NumberingError(f"{path.name} line {n}: give a block's id, or a retired block's old name in retired")
        name = gone or next((names[(lv, ident)] for lv in LEVELS if (lv, ident) in names), "")
        if not name:
            raise NumberingError(f"{path.name} line {n}: {ident} is no main or upper device of the device master (a "
                                 "new export dropped it: give the block's new id)")
        if name in seen:
            raise NumberingError(f"{path.name} line {n}: block {name!r} is listed twice")
        seen.add(name)
        if gone and (as_ or order):
            raise NumberingError(f"{path.name} line {n} ({name}): a retired block holds its number; no numbered_as "
                                 "or append_order")
        if not gone and bool(as_) == bool(order):
            raise NumberingError(f"{path.name} line {n} ({name}): give exactly one of numbered_as, append_order")
        if gone:
            retired.append(name)
        elif as_:
            numbered[name] = as_
        elif not order.isdigit():
            raise NumberingError(f"{path.name} line {n} ({name}): append_order {order!r} is not a whole number")
        else:
            appended[int(order)] = name
    if sorted(appended) != list(range(1, len(appended) + 1)):
        raise NumberingError(f"{path.name}: append_order must count 1, 2, 3 ... without a gap or repeat, got "
                             f"{sorted(appended)}")
    clash = sorted(set(numbered.values()) & seen)
    if clash:
        raise NumberingError(f"{path.name}: {', '.join(clash)} is both a block and the name another is numbered as")
    return Numbering(numbered, tuple(appended[k] for k in sorted(appended)), tuple(retired))


def block_sort(name: str):
    """A main or upper block's sort key: OS blocks first, then by the number at the end of the name."""
    kind = 0 if name.startswith("OS ") else 1
    tail = name.split(" ")[-1].split("+")[0]
    digits = "".join(c for c in tail if c.isdigit())
    return (kind, int(digits or 0), name)


def order(blocks: Iterable[str], numbering: Numbering, require_listed: bool = False) -> list[str]:
    """The blocks in the order their system names are numbered: by block_sort (a block in numbered_as in the place of
    the name it replaces), then the appended ones. Give it the retired blocks too to keep their numbers taken. With
    require_listed (a build), a block block_numbering.csv names that is not among `blocks` stops it
    (NumberingError): the row is stale."""
    blocks = set(blocks)
    listed = set(numbering.numbered_as) | set(numbering.appended) | set(numbering.retired)
    missing = sorted(listed - blocks) if require_listed else []
    if missing:
        raise NumberingError(f"{PATH.name} names {', '.join(missing)}, which the main and upper levels no longer "
                             "have; take the row out or rename it")
    tail = [b for b in numbering.appended if b in blocks]
    return sorted(blocks - set(tail), key=lambda b: block_sort(numbering.numbered_as.get(b, b))) + tail


def block_name(n: int) -> str:
    """The JMRI block system name of the n-th main or upper block (from 1): IB:C3:0001."""
    return f"{level_devices.BLOCK_PREFIX}{n:04d}"


def layout_block_name(n: int) -> str:
    """The layout block system name of the n-th main or upper block (from 1): ILB1001."""
    return f"ILB{level_devices.LAYOUT_BLOCK_FIRST + n - 1}"


def bean_names(blocks: Iterable[str], numbering: Numbering) -> dict[str, tuple[str, str]]:
    """{block: (jmri_name, layout_block)} of every main and upper block in `blocks`, numbered in order() over them
    and the retired blocks (whose numbers stay taken). NumberingError on a retired block among `blocks` (drawn
    again: take its retired row out) or a row block_numbering.csv holds for a block not among them."""
    blocks = set(blocks)
    again = sorted(blocks & set(numbering.retired))
    if again:
        raise NumberingError(f"retired blocks drawn again: {', '.join(again)}; take them out of {PATH.name}'s "
                             "retired rows")
    return {b: (block_name(i), layout_block_name(i))
            for i, b in enumerate(order(blocks | set(numbering.retired), numbering, require_listed=True), 1)
            if b in blocks}
