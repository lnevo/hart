"""The routes a train can take from a switch leg on the schematic: where they end and which points they meet facing.

route_ends() walks every route from a switch leg to the next mast or the end of track, reaches_signal() says whether
one of them reaches another signal (the rule that leaves dark masts out, mast_rule.signalled), and facing_on_route()
lists the switches whose points a route meets facing inside one interlocking.
"""
from __future__ import annotations

from collections.abc import Mapping

from hartlib import railroad
from map_error import MapError
from plan_bands import Band, Bands
from plan_tracks import Joined, Leg

base = railroad.switch_number
natural = railroad.natural

LONG_CM = 150.0                       # a track inside a control point longer than this can hold a train

Posts = Mapping[int, set[Leg]]        # {band index: {(node, leg)}} of the masts
LegOnBand = tuple[int, str, str]      # (band, node, port)

# where a train leaves a switch by, entering it at a leg: a plain switch's points (A) choose B or C and B or C trail to
# A; a double crossover joins A to B and C, D to C and B (its through tracks A-B and D-C, both diagonals)
EXITS: dict[str, dict[str, tuple[str, ...]]] = {"switch": {"A": ("B", "C"), "B": ("A",), "C": ("A",)},
         "dx": {"A": ("B", "C"), "B": ("A", "D"), "C": ("D", "A"), "D": ("C", "B")}}


def reaches_signal(bands: Bands, bi: int, node: str, leg: str, posts: Posts, joined: Joined) -> bool:
    """True when some route of a train entering switch `node` of band `bi` at `leg` reaches another signal: a switch
    leg in `posts` ({band index: {(node, leg)}} of the masts) that it enters by, other than the one it starts at, or
    an end where the track runs on: a helix end (its signals are the other level's) or an open end (track running on
    off the drawing), so the rule never leaves out a mast whose route runs on beyond what is drawn. A connector end is
    followed to the other band when `joined` (the plugin's partners, {(band, node): (band, node)}) joins it, as
    plan_tracks.end_ref does, and is a bumper when it does not. Every route is walked through switches and turnbacks
    to the next mast or the end of track; a route ending at a bumper, or in track with no mast facing on (a dark spur
    or yard), reaches none. A route that comes back to a leg already walked, its own start among them, adds nothing."""
    return route_ends(bands, bi, node, leg, posts, joined)[0]


def _legs(bands: Bands, b: int, n: str) -> dict[str, str]:
    """{port: strand} of node `n` of band `b`."""
    d = bands[b][1]["nodes"][n]
    return dict(d["ins"] | d["outs"])


def _far_end(bands: Bands, joined: Joined, b: int, n: str, x: str) -> LegOnBand:
    """(band, node, port) a train reaches leaving node `n` of band `b` by its port `x`, on through any turnback and
    joined connector. MapError at a turnback that does not join exactly two tracks."""
    while True:
        nodes, strands = bands[b][1]["nodes"], bands[b][1]["strands"]
        s = strands[_legs(bands, b, n)[x]]
        m, q = s["dst"] if tuple(s["src"]) == (n, x) else s["src"]
        kind, sub = nodes[m]["kind"], nodes[m].get("sub")
        if kind.startswith("turn"):
            onward = [k for k in _legs(bands, b, m) if k != q]
            if len(onward) != 1:
                raise MapError(f"reaches_signal: turnback {m} has {len(onward) + 1} tracks, not two")
            n, x = m, onward[0]
        elif kind == "end" and sub == "link" and (b, m) in joined:
            b, n = joined[(b, m)]
            x = next(iter(_legs(bands, b, n)))
        else:
            return b, m, q


def route_ends(bands: Bands, bi: int, node: str, leg: str, posts: Posts, joined: Joined
               ) -> tuple[bool, set[tuple[int, str]]]:
    """(reaches a signal, {(band, buffer stop node)} reached before any mast) over every route of a train entering
    switch `node` of band `bi` at `leg`, walked as reaches_signal says (the whole walk: a route that reaches a signal
    stops there, the others run on). The buffer stops are where a mast in `posts` needs a destination
    (mast_plan.virtual_masts). MapError when a route enters a node that is no switch."""
    start: LegOnBand = (bi, node, leg)
    todo, seen, signal = [start], {start}, False
    bumpers: set[tuple[int, str]] = set()
    while todo:
        b, n, p = todo.pop()
        d = bands[b][1]["nodes"][n]
        if d["kind"] not in EXITS:
            raise MapError(f"reaches_signal: a route enters {d['kind']} node {n}, which is no switch")
        for x in EXITS[d["kind"]][p]:
            if _legs(bands, b, n).get(x) is None:
                continue
            here = _far_end(bands, joined, b, n, x)
            fb, m, q = here
            end = bands[fb][1]["nodes"][m]
            if end["kind"] not in EXITS:                    # a track end
                if end.get("sub") in ("helix", "open"):
                    signal = True                           # runs on: another level, or off the drawing
                elif end.get("sub") == "bumper":
                    bumpers.add((fb, m))                    # this route ends dark at a buffer stop
                continue                                    # an unjoined connector: this route ends dark
            if here != start and (m, q) in posts.get(fb, ()):
                signal = True
                continue
            if here not in seen:
                seen.add(here)
                todo.append(here)
    return signal, bumpers


def facing_on_route(band: Band, node: str, leg: str, cp_of: Mapping[str, str], long_cm: float = LONG_CM) -> list[str]:
    """The switch numbers whose points a train meets facing, on any route from entering switch `node` at `leg`,
    inside the control point (interlocking) that switch is in, before it leaves it or reaches the next signal: a track
    longer than `long_cm` inside the interlocking holds signals of its own, so the walk stops there. Entering a switch
    at A meets its points facing (a choice of B or C); entering at B or C trails through to A. Turnbacks are followed.
    Used to give a home mast two heads when a route it governs can still diverge."""
    nodes, strands = band["nodes"], band["strands"]
    first = nodes[node]
    cp = cp_of.get(base(first.get("label") or ""))

    def leg_strand(n: str, p: str) -> str | None:
        d = nodes[n]
        got: str | None = d["ins"].get(p) or d["outs"].get(p)
        return got

    def at_other_end(sid: str, n: str) -> Leg:
        s = strands[sid]
        other = s["dst"] if s["src"][0] == n else s["src"]
        return other[0], other[1]

    out: list[str] = []
    seen: set[str] = set()
    todo: list[Leg] = [(node, leg)]
    while todo:
        n, p = todo.pop()
        d = nodes[n]
        if d["kind"] not in ("switch", "dx"):
            if not d["kind"].startswith("turn"):
                continue                                    # a bumper, a helix end or a connector: off the route
            for sid, s in strands.items():
                if n in (s["src"][0], s["dst"][0]) and sid not in seen:
                    seen.add(sid)
                    if s["cm"] <= long_cm:
                        todo.append(at_other_end(sid, n))
            continue
        if cp_of.get(base(d.get("label") or "")) != cp:
            continue                                        # left the interlocking
        if d["kind"] == "dx":                               # a double crossover offers a choice from every leg
            out.append(base(d["label"]))
            continue
        exits = ["B", "C"] if p == "A" else ["A"]
        if p == "A" and all(leg_strand(n, x) for x in ("B", "C")):
            out.append(base(d["label"]))
        for x in exits:
            sid = leg_strand(n, x)
            if not sid or sid in seen:
                continue
            seen.add(sid)
            if strands[sid]["cm"] > long_cm:
                continue                                    # running track inside: its own signals govern it
            todo.append(at_other_end(sid, n))
    return sorted(set(out), key=natural)
