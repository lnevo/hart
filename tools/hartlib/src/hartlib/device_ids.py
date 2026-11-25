"""A device's ID (ADR-033, decision 1 of the naming-layers hand-off, owner 2026-11-24): a key that is not its name.

The builders derive each ID from the plan (the AnyRail plan's switch numbers and legs, as the solved schematic gives
them), never from a user name, so an ID stays the same when the owner renames the device. Every row of the device
master with a level carries one in its `id` column, unique on its level (hartlib.devices.check_rows); a Store's
level-less row has none. Nothing keys on the ID yet (steps 4 and 5 of the hand-off).

The grammar, one function per kind below:
- switch:<n>          a turnout (a crossover drawn as halves 101A and 101B is one turnout, one ID)
- dcc:<n>             its LCC alias
- fb:<n>:N, fb:<n>:R  its feedback sensors
- block:<ends>        a track, spur, loop half, helix or part block, from the ends of its strands (the trial keys of
                      staging_device_map.strand_placeholders): "1B-3A:1/2" for the first of two blocks on the piece
                      1B-3A, "107B-107C#1" for the first piece of a run, several strands joined by "+"
- os:<n>              the OS block of switch n
- os:<n>:A-<end>      a staging single crossover's half (7, 23, 35), told apart by where its leg A runs, as
                      block_overrides.csv's crossover_half rows do: os:7:A-13C. The a and b in "OS Switch 23a" are the
                      owner's names, not the plan's (owner, 2026-11-24)
- os:<n>:<leg>        a double crossover's corner block by the schematic leg it serves (A to D, the letters the track
                      ends use: os:225:D is the corner at track 225D-229A), not the Layout Editor corner, which turns
                      with the drawing (owner, 2026-11-24)
- det:<block id>      a block's detector (occupancy row)
- spare:<system name> a spare detector (no block)
- mast:<switch>:<leg>:<dir>   a home mast, by the switch label it stands at (a crossover half's label: 101A), the leg
                      and the way it looks (east, west)
- mast:<block id>:<dir>       an intermediate or a hidden (buffer stop) mast, by the block it faces
- <mast id>:<top|bottom|single>   a head, by its place on its mast
- panel:<item key>:<system name>  a panel lamp of panel_items.json, by its item and the system name of the bean its
                      icon shows (owner, 2026-11-24)
"""
from __future__ import annotations

import re

HEAD_PLACES = ("top", "bottom", "single")
DIRS = ("east", "west")
_LABEL = re.compile(r"\d+[A-Z]?")          # a switch label as the plan prints it: 101, 101A
_NUMBER = re.compile(r"\d+")


def _need(ok: bool, what: str) -> None:
    if not ok:
        raise ValueError(f"no device ID for {what}")


def _number(n) -> str:
    n = str(n)
    _need(bool(_NUMBER.fullmatch(n)), f"switch number {n!r} (digits)")
    return n


def switch_id(n) -> str:
    return f"switch:{_number(n)}"


def dcc_id(n) -> str:
    return f"dcc:{_number(n)}"


def fb_id(n, position: str) -> str:
    _need(position in ("N", "R"), f"feedback position {position!r} (N or R)")
    return f"fb:{_number(n)}:{position}"


def strand_key(piece: str, k: int = 1, count: int = 1) -> str:
    """The ID part of the k-th of `count` blocks on a plan piece (staging_device_map.piece_refs: "1B-3A",
    "1C-5A #1"): the piece with its " #" closed up, and ":k/count" when the piece carries several blocks."""
    _need(bool(piece) and 1 <= k <= count, f"piece {piece!r} block {k} of {count}")
    key = piece.replace(" #", "#")
    return key if count == 1 else f"{key}:{k}/{count}"


def block_id(strands) -> str:
    """block:<strand keys (strand_key), joined by "+">, in the order given."""
    strands = list(strands)
    _need(bool(strands) and all(strands), f"a block with strands {strands}")
    return "block:" + "+".join(strands)


def os_id(n, half: str = "") -> str:
    """os:<n>, or os:<n>:<half> for a crossover half (A-<end>) or a double crossover's corner (its leg)."""
    return f"os:{_number(n)}:{half}" if half else f"os:{_number(n)}"


def det_id(block: str) -> str:
    _need(block.startswith(("block:", "os:")), f"the detector of {block!r} (no block ID)")
    return f"det:{block}"


def spare_id(system_name: str) -> str:
    _need(bool(system_name), "a spare detector with no system name")
    return f"spare:{system_name}"


def home_mast_id(label: str, leg: str, direction: str) -> str:
    _need(bool(_LABEL.fullmatch(label or "")) and leg in ("A", "B", "C", "D") and direction in DIRS,
          f"a home mast at {label!r} leg {leg!r} looking {direction!r}")
    return f"mast:{label}:{leg}:{direction}"


def block_mast_id(facing: str, direction: str) -> str:
    _need(facing.startswith(("block:", "os:")) and direction in DIRS,
          f"a mast facing {facing!r} looking {direction!r}")
    return f"mast:{facing}:{direction}"


def head_id(mast: str, place: str) -> str:
    _need(mast.startswith("mast:") and place in HEAD_PLACES, f"head {place!r} of {mast!r}")
    return f"{mast}:{place}"


def head_place(index: int, heads: int) -> str:
    """top, bottom or single: the place of the `index`-th head (from 0, top first) of a mast with `heads` heads."""
    _need(heads in (1, 2) and 0 <= index < heads, f"head {index} of a {heads}-head mast")
    return "single" if heads == 1 else HEAD_PLACES[index]


def panel_id(item: str, system_name: str) -> str:
    _need(bool(item) and bool(system_name), f"panel item {item!r} bean {system_name!r}")
    return f"panel:{item}:{system_name}"
