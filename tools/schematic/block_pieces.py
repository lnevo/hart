"""Which OS block a short track or a given piece of track belongs to, for the block layer (block_layer.layer): a link
(is_link: a track between two switches under LINK_CM) is part of the OS block at one of its ends (link_block,
masted_block), and a track block_overrides.csv gives to OS blocks is cut into pieces (exception_pieces). The rules
and the overrides file's rows are block_layer's module text.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NamedTuple

from hartlib import railroad
from plan_tracks import Track

LINK_CM = 50.0
Ends = dict[str, "str | None"]                  # {end switch: the OS block at that end on the band} (end_blocks)
OsGift = tuple[str, int, "float | None"]     # a track row given to an OS block: (block, line, cm or None)
natural = railroad.natural


def is_link(t: Track) -> bool:
    """Whether track `t` is a link: between two different switches and shorter than LINK_CM."""
    sws = [v for k, v in t["ends"] if k == "sw"]
    return len(sws) == 2 == len(t["ends"]) and sws[0] != sws[1] and t["cm"] < LINK_CM


def link_block(ends: Ends) -> str | None:
    """The OS block a link is part of, from `ends` ({end switch: the OS block at that end on the link's band, None
    when the switch is drawn on another band}): the lower-numbered switch's, or, for a link drawn to a connector whose
    lower-numbered switch is across it, the one end switch's on the band; None when neither is on the band."""
    for s in sorted(ends, key=natural):
        if ends[s] is not None:
            return ends[s]
    return None


def masted_block(t: Track, ends: Ends, masts: Mapping[str, str], level: int, where: str, bad: list[str]
                 ) -> tuple[str | None, str | None]:
    """(the OS block link `t` is part of, why) from `ends` (end_blocks) and `masts` ({end switch: the home mast that
    stands at its points facing the link}; the block boundary is at the mast): with a mast at one
    end, the OS block at the other end; with none, link_block's (the lower-numbered switch's). A mast at both ends is a
    problem in `bad` (why None): the link would be inside the OS block of one of them."""
    if len(masts) > 1:
        bad.append(f"level {level}: the link {t['name']} has a home mast facing it at both ends ("
                   + ", ".join(f"Mast {m} at Switch {s}" for s, m in sorted(masts.items(), key=lambda x: natural(x[0])))
                   + f"): one of them would stand inside its own OS block; give the link to one OS block in {where}")
        return None, None
    if masts:
        (s, mast), = masts.items()
        other = [v for v in ends if v != s]
        return (ends[other[0]] if other else None), (f"OS block at its other end: Mast {mast} stands at Switch {s}'s "
                                                    "points facing it, so the block boundary is at the mast")
    block = link_block(ends)
    low = min(ends, key=natural)
    return block, ("lower-numbered switch's OS block" if ends[low] == block else
                   "OS block of its end switch on its band (a connector)")


def end_blocks(t: Track, nodes: Mapping[str, Any], os_: Mapping[str, str], corners: Mapping[str, Mapping[str, str]],
               level: int, bad: list[str]) -> Ends:
    """{end switch: the OS block at that end of track `t` on this band (`os_`), None for a switch drawn on another
    band}: a double crossover's corner block of the leg the track leaves (`corners`, {switch number: {leg: block}}).
    A double crossover with no corners given is a problem in `bad` (and None)."""
    out: Ends = {}
    for (node, port), (k, end) in zip(t["legs"], t["ends"]):
        if k != "sw":
            continue
        v = str(end)                                # a switch end's number
        if node not in os_:
            out[v] = None
        elif nodes[node]["kind"] == "dx":
            got = corners.get(v, {}).get(port)
            if got is None:
                bad.append(f"level {level}: {t['name']} leaves double crossover {v} at leg {port}, which has no "
                           "corner block given")
            out[v] = got
        else:
            out[v] = os_[node]
    return out


class Piece(NamedTuple):
    """A piece of a track block_overrides.csv gives to OS blocks (exception_pieces): its row name, its block, the
    overrides line that gives it (0 for the rest of the track, its own block) and its length."""
    row: str
    block: str
    line: int
    cm: float


def exception_pieces(t: Track, ex: Mapping[str, OsGift], own: str, ends: Ends, where: str, bad: list[str]
                     ) -> list[Piece] | None:
    """The pieces (row name, block, overrides line or 0, cm) of a track block_overrides.csv gives to OS blocks (`ex`, {end:
    (block, line, cm)}), from its lower-numbered switch's end: the whole track as one part (its own name, its whole
    length), or a piece per end the file names ("<track> at <switch>"). Pieces at both ends share the track evenly;
    a piece at one end takes the cm its row gives, and the rest of the track, its own block
    `own`, the remaining length. None (with the problem in `bad`) when a block is not the OS block at its end, a
    parted track is drawn in several pieces, or a length is missing, out of range or given where none is taken."""
    sws = sorted(ends, key=natural)
    if "" in ex:
        block, line, cm = ex[""]
        if cm is not None:
            bad.append(f"{where} line {line}: cm {cm:g} for the whole of {t['name']}: only a piece at one end takes "
                       "its length")
            return None
        if block not in {ends[s] for s in sws}:
            bad.append(f"{where} line {line}: {t['name']} is given {block}, the OS block of neither of its end "
                       "switches")
            return None
        return [Piece(t["name"], block, line, t["cm"])]
    if len(t["strands"]) != 1:
        bad.append(f"{where} lines {', '.join(str(x[1]) for x in ex.values())}: {t['name']} is drawn as "
                   f"{len(t['strands'])} pieces; a track parted at an end is one")
        return None
    out: list[Piece] = []
    for s in sws:
        if s not in ex:
            continue
        block, line, cm = ex[s]
        name = f"{t['name']} at {s}"
        if block != ends[s]:
            bad.append(f"{where} line {line}: the piece of {t['name']} at Switch {s} is given {block}, not that "
                       f"switch's OS block {ends[s]}")
            return None
        if len(ex) == 2:
            if cm is not None:
                bad.append(f"{where} line {line}: cm {cm:g} for {name}: only a piece at one end takes its length "
                           "(pieces at both ends share the track evenly)")
                return None
            cm = round(t["cm"] / 2, 1)
        elif cm is None:
            bad.append(f"{where} line {line}: {name}: give its cm, the length of the piece inside {block}")
            return None
        elif cm >= t["cm"]:
            bad.append(f"{where} line {line}: {name}: cm {cm:g} is not under the track's {t['cm']:g}")
            return None
        out.append(Piece(name, block, line, cm))
    if len(ex) == 1:                                   # the rest of the track stays its own block
        rest = Piece(own, own, 0, round(t["cm"] - out[0].cm, 1))
        out = [out[0], rest] if next(iter(ex)) == sws[0] else [rest, out[0]]
    return out
