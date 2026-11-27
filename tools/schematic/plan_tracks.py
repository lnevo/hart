"""The tracks of the schematic's bands: each track between its ends, its name and the keys hand lists find it by.

tracks() lists each track of a band between its ends (switch, helix or bumper), following a connector to the band
beyond it so a track cut by one is counted once. track_names() names them ("Track <a>-<b>", "Track <n> Spur",
"Track <n> Loop", " 1"/" 2" for parallel tracks, in plan_order). track_key() gives a track's end switches, the key
block_overrides.csv and wiring.csv name a track by; plan_order() and letter_order() order parallel tracks and the A
and B masts facing them from the plan, never from the drawn rows.
"""
from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from typing import Any, NotRequired, TypedDict

from hartlib import railroad
from hartlib.track_names import end_order
from map_error import MapError
from plan_bands import Band, Bands, HelixTags, Levels, band_level

base = railroad.switch_number
natural = railroad.natural

Joined = dict[tuple[int, str], tuple[int, str]]      # the plugin's connector partners: (band, node) -> (band, node)
End = tuple[str, str | None]         # what a track ends at (end_ref): ("sw", number), ("helix", "H1"), ("bumper", None)
Leg = tuple[str, str]                # a switch leg on a band: (node, port)
TrackKey = tuple[int, str]           # a track entry's band and first strand (entry_key): one entry per track
BandRun = tuple[Leg, Sequence[tuple[str, bool]], Leg]   # le_names.runs: (start, [(strand, reversed)], end)
Runs = Callable[[Band], Sequence[BandRun]]              # le_names.runs over one band


class Track(TypedDict):
    """One track of the bands (tracks); `name` is filled by track_names (or block_layer.name_tracks), `names` by
    block_layer.store_names ({(band index, strand): the name store's name})."""
    level: int
    ends: tuple[End, End]
    legs: list[Leg]
    band: int
    plan_ends: tuple[str, ...]
    cm: float
    loop: bool
    main: bool
    row: int
    strands: list[str]
    trial: list[str]
    name: NotRequired[str]
    names: NotRequired[dict[tuple[int, str], str]]


TrackEnd = tuple[Track, End]        # a track at a switch leg and what its far end is
LegKey = tuple[int, str, str]       # a switch leg on the drawing: (band, node, leg)


def edge_key(edge: str) -> str:
    """A plan edge with its connector cut letter dropped: a track cut by a connector is one track."""
    return re.sub(r"(?<=\d)[xy]$", "", edge)


def beyond_connector(bands: Bands, joined: Joined, bi: int, node: str) -> tuple[int, Leg] | None:
    """The far end of the track beyond connector `node` of band `bi`: (its band, (node, port)) at the other end of
    the one strand at the partner connector `joined` gives; None when `node` is not a connector `joined` pairs. The
    walk goes on from that end, so a track cut by a connector reads as one track."""
    d = bands[bi][1]["nodes"][node]
    if d.get("sub") != "link" or (bi, node) not in joined:
        return None
    bj, m = joined[(bi, node)]
    other = bands[bj][1]
    sid = next(iter(list(other["nodes"][m]["ins"].values()) + list(other["nodes"][m]["outs"].values())))
    s = other["strands"][sid]
    src, dst = tuple(s["src"]), tuple(s["dst"])
    return bj, (dst if src[0] == m else src)


def end_ref(bands: Bands, joined: Joined, bi: int, node_id: str, helix_tag: HelixTags, levels: Levels) -> End:
    """What a track ends at: ("sw", number), ("helix", "H1"), ("bumper", None). A connector to the other band
    is followed to the switch beyond it."""
    d = bands[bi][1]["nodes"][node_id]
    if d["kind"] in ("switch", "dx"):
        return ("sw", base(d["label"]))
    if d.get("sub") == "helix":
        level = band_level(bands[bi][0], levels)
        if level not in helix_tag:
            raise MapError(f"a track reaches the helix end on band {bands[bi][0]!r}, which is not main or upper")
        return ("helix", helix_tag[level])
    if (far := beyond_connector(bands, joined, bi, node_id)) is not None:
        return end_ref(bands, joined, far[0], far[1][0], helix_tag, levels)
    return ("bumper", None)


def end_label(bands: Bands, joined: Joined, bi: int, node_id: str) -> str:
    """The switch label a track ends at, followed through a connector to the other band ("" at a bumper or
    helix): the halves of the helix-top crossovers 127 and 131 sit on two bands, joined by connectors."""
    d = bands[bi][1]["nodes"][node_id]
    if d["kind"] in ("switch", "dx"):
        return str(d.get("label") or "")
    if (far := beyond_connector(bands, joined, bi, node_id)) is not None:
        return end_label(bands, joined, far[0], far[1][0])
    return ""


def end_leg(bands: Bands, joined: Joined, bi: int, end: Leg) -> str:
    """A track end (node, port) by its plan switch label and leg ("103AB", "113C"; a moved switch's star dropped),
    followed through a connector to the switch beyond it as end_ref does; "helix" at a helix end, "end" at any other
    (a bumper). The same key staging_device_map.end_key gives a run's end, so it comes from the plan, not the drawing."""
    node, port = end
    d = bands[bi][1]["nodes"][node]
    if d["kind"] in ("switch", "dx"):
        return f"{(d.get('label') or '').rstrip('*')}{port}"
    if d.get("sub") == "helix":
        return "helix"
    if (far := beyond_connector(bands, joined, bi, node)) is not None:
        return end_leg(bands, joined, far[0], far[1])
    return "end"


def entry_key(t: Track) -> TrackKey:
    """The key of track entry `t` that stays the same however the entry is copied: its band and its first strand."""
    return t["band"], t["strands"][0]


def plan_order(t: Track) -> tuple[Any, ...]:
    """The order of tracks that share their end switches (parallel tracks): by their ends' plan labels and legs, lower
    end first (the order of their device IDs, block:103AB-105B before block:103BA-105C), so the numbers in "Track
    103-105 1" and "2", and block_overrides.csv's `parallel`, come from the plan and not from the drawn rows."""
    return tuple(sorted((end_order(k) for k in t["plan_ends"]))) + (t["trial"],)


def letter_order(t: Track, half: int, leg: str) -> tuple[Any, ...]:
    """The order of two home masts of one number and direction (their A and B): by the plan order of the tracks they
    face (plan_order, so the A mast faces a Spur 1 and the B mast its Spur 2, as the track numbers run), then a
    balloon loop's half (the A mast faces Loop 1, from leg B), then the leg they stand at. From the plan, not the
    drawn rows."""
    return plan_order(t) + (half, leg)


def tracks(bands: Bands, runs: Runs, joined: Joined, helix_tag: HelixTags, levels: Levels) -> list[Track]:
    """One entry per track of the bands `levels` holds (a track cut by a connector counted once)."""
    found: list[Track] = []
    seen: set[tuple[str, ...]] = set()
    for bi, (title, band, _) in enumerate(bands):
        lv = band_level(title, levels)
        if not lv:
            continue
        strands, srow = band["strands"], band["R"]["srow"]
        for start, chain, end in runs(band):
            a = end_ref(bands, joined, bi, start[0], helix_tag, levels)
            b = end_ref(bands, joined, bi, end[0], helix_tag, levels)
            # between a crossover's halves, its OS block: two nodes of one switch number (the A and B halves of a
            # crossover, or staging's single crossovers 7, 23 and 35), however the plan labels them; a balloon loop
            # starts and ends on the same node
            if a[0] == b[0] == "sw" and a[1] == b[1] and start[0] != end[0]:
                continue
            edges = {edge_key(strands[sid]["edge"]): strands[sid]["cm"] for sid, _ in chain}
            key = tuple(sorted(edges))
            if key in seen:
                continue
            seen.add(key)
            ends: list[Leg] = [(start[0], start[1]), (end[0], end[1])]
            found.append(Track(level=lv, ends=(a, b), legs=ends, band=bi,
                               plan_ends=tuple(end_leg(bands, joined, bi, e) for e in ends),
                               cm=round(sum(edges.values()), 1), loop=start[0] == end[0] and a[0] == "sw",
                               main=any(strands[sid]["main"] for sid, _ in chain),
                               row=min(srow.get(sid, 0) for sid, _ in chain),
                               strands=[sid for sid, _ in chain],
                               trial=sorted({"Track " + edge_key(strands[sid]["edge"]) for sid, _ in chain})))
    return found


def track_names(found: Sequence[Track], helix: Mapping[str, str] | None = None) -> None:
    """Fill `name` in each track entry (see the module text). `helix` ({helix tag: block}, plan_bands.helix_blocks)
    names each track that reaches the helix by its helix block (main and upper: one block from staging up the
    helix); without it (staging's own mast rule) such a track is "Track <switch>-<tag>". A track reaching a helix
    tag that `helix` does not name stops."""
    groups: defaultdict[str, list[Track]] = defaultdict(list)
    for t in found:
        sw = sorted([str(v) for k, v in t["ends"] if k == "sw"], key=natural)
        hx = [str(v) for k, v in t["ends"] if k == "helix"]
        if not sw:
            raise MapError(f"a track ({', '.join(t['trial'])}) has no switch at either end, so it has no name")
        if hx and helix is not None:
            if len(hx) != 1 or hx[0] not in helix:
                raise MapError(f"track {', '.join(t['trial'])} reaches helix {', '.join(hx)}, which "
                               "is no helix track of the plan overrides")
            groups[helix[hx[0]]].append(t)
            continue
        if len(sw) == 2 and sw[0] == sw[1]:
            stem = f"Track {sw[0]} Loop"
        elif not hx and len(sw) == 1:
            stem = f"Track {sw[0]} Spur"
        else:
            stem = "Track " + "-".join(sw + hx)
        groups[stem].append(t)
    for stem, ts in groups.items():
        if len(ts) > 1:
            ts.sort(key=plan_order)
        for i, t in enumerate(ts, 1):
            t["name"] = stem if len(ts) == 1 else f"{stem} {i}"


def track_key(t: Track) -> tuple[str, str] | None:
    """The end switches of a track entry, lower number first: (a, b) between two switches, (n, n) for a balloon loop
    and (n, "") for a spur (one switch, a bumper at the other end). None for a track up the helix, which its helix
    block names ("Track <plan name>"). Hand lists name a track by this key, so a renumbered switch moves the row with
    it, where a generated name ("Track 119-121") would have to be retyped."""
    if any(k == "helix" for k, _v in t["ends"]):
        return None
    sw = sorted((str(v) for k, v in t["ends"] if k == "sw"), key=natural)
    return (sw[0], sw[1] if len(sw) == 2 else "") if sw else None


def by_leg(found: Sequence[Track]) -> dict[LegKey, Track]:
    """{(band, switch node, leg): track entry} of every track end at a switch leg."""
    return {(t["band"], n, p): t for t in found for (n, p) in t["legs"]}


def leg_ends(found: Sequence[Track]) -> dict[LegKey, TrackEnd]:
    """{(band, node, leg): (track, its far end)} of every track end at a switch leg."""
    out: dict[LegKey, TrackEnd] = {}
    for t in found:
        for (n, p), far in zip(t["legs"], reversed(t["ends"])):
            out[(t["band"], n, p)] = (t, far)
    return out
