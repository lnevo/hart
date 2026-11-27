"""The home mast rule of every schematic level, and the rules that say which tracks count as running track.

masts() places a home signal where a track from outside a control point meets one of its switches, unless no route
it governs reaches another signal (mast_routes.reaches_signal; build_device_map.py's module text has the naming and
head rules), and letters the A and B masts of one number and direction in plan order (plan_tracks.letter_order).
running_tracks (passing sidings between interlockings) and signalled_spurs (exit dwarfs off a main track) are the
rules that replaced hand lists. mast_plan.py runs them, over plan_tracks' named tracks and block_override_rows' splits,
as the one mast process of every level.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple, NotRequired, TypedDict

from hartlib import railroad
from map_error import MapError
from mast_routes import LONG_CM, reaches_signal
from plan_bands import Band, Bands, Levels, band_level
from plan_tracks import Joined, Leg, LegKey, Track, TrackEnd, by_leg, leg_ends, letter_order

base = railroad.switch_number
natural = railroad.natural

TAU = {"A": -1, "B": 1, "C": 1, "D": -1}      # the plugin's leg sides (schematic.core.TAU)
LOOP_HALF = {"B": 1, "C": 2}          # a balloon loop's half by the switch leg it leaves from
LetterOrder = tuple[Any, ...]         # letter_order of a mast's track: sorts a switch's A and B masts


class MastOrderError(MapError):
    """Two masts on one (band, node, leg): the key that orders a switch's A and B masts would be shared."""


class HomeMast(TypedDict):
    """A home mast (masts); `name` is filled once its letters are known, the rest by the device map's build."""
    level: int
    cp: str
    switch: str
    number: int
    letter: str
    dir: str
    protects: str
    heads: int
    row: int
    track: str
    band: int
    half: int
    node: str
    leg: str
    strand: str
    running: bool
    kind: str
    name: NotRequired[str]
    facing: NotRequired[str]
    id: NotRequired[str]


# ---------------------------------------------------------------- rules that replace hand lists

def through_leg(band: Band, node: str, leg: str) -> str | None:
    """The leg a train leaves a single crossover's half `node` by when it enters at `leg` and keeps to the half's
    through route (the points, A, and the leg that does not join the other half), or None: `node` is no crossover
    half (no leg joins a switch of the same number), or `leg` is the leg into the other half."""
    nodes, strands = band["nodes"], band["strands"]
    d = nodes[node]
    legs = d["ins"] | d["outs"]
    cross = []
    for p, sid in legs.items():
        s = strands[sid]
        other = s["dst"][0] if s["src"][0] == node else s["src"][0]
        o = nodes[other]
        if other != node and o["kind"] == "switch" and base(o.get("label") or "") == base(d.get("label") or ""):
            cross.append(p)
    if len(cross) != 1 or leg == cross[0] or len(legs) != 3:
        return None
    rest = [p for p in legs if p not in (cross[0], leg)]
    return str(rest[0]) if leg == "A" or rest == ["A"] else None


def running_tracks(bands: Bands, found: Sequence[Track], cp_of: Mapping[str, str]) -> set[str]:
    """The names of the tracks that count as running track besides the main route (it replaced
    the hand list running_tracks_main_upper.csv): a chain of non-main tracks joining two different interlockings
    (`cp_of`, {switch: interlocking}), where the chain may run on through the through route of a crossover half in no
    interlocking (through_leg: local crossover 121 on the long siding). A passing siding between two control points is
    running track; a spur, a loop, a track up the helix or one ending in a yard is not. On staging it makes Scale
    (5-7) running track."""
    legs = by_leg(found)

    def walk(t: Track, n: str, p: str, chain: dict[int, Track]) -> str | None:
        """The interlocking a chain reaches leaving track `t` at its end (n, p), or None; `chain` collects it."""
        while True:
            d = bands[t["band"]][1]["nodes"][n]
            if d["kind"] not in ("switch", "dx"):
                return None
            num = base(d["label"])
            if num in cp_of:
                return cp_of[num]
            out_leg = through_leg(bands[t["band"]][1], n, p)
            nxt = legs.get((t["band"], n, out_leg)) if out_leg else None
            if nxt is None or nxt["main"] or nxt["loop"] or id(nxt) in chain:
                return None
            chain[id(nxt)] = nxt
            a, b = nxt["legs"]
            n, p = b if tuple(a) == (n, out_leg) else a
            t = nxt

    out: set[str] = set()
    for t in found:
        if t["main"] or t["loop"] or any(k != "sw" for k, _v in t["ends"]):
            continue
        chain = {id(t): t}
        ends = [walk(t, n, p, chain) for (n, p) in t["legs"]]
        if ends[0] and ends[1] and ends[0] != ends[1]:
            out |= {u["name"] for u in chain.values()}
    return out


def signalled_spurs(found: Sequence[Track], cp_of: Mapping[str, str]) -> set[str]:
    """The names of the spurs that get an exit dwarf (it replaced the hand list signalled_spurs_main_upper.csv): a
    spur (one switch, a buffer stop at the other end) off a main track at a switch in no interlocking (`cp_of`):
    Track 241 Spur."""
    out = set()
    for t in found:
        sw = [v for k, v in t["ends"] if k == "sw"]
        if len(sw) != 1 or not any(k == "bumper" for k, _v in t["ends"]) or sw[0] in cp_of:
            continue
        if any(u["main"] for u in found if u is not t and u["level"] == t["level"]
               and sw[0] in [v for k, v in u["ends"] if k == "sw"]):
            out.add(t["name"])
    return out


# ---------------------------------------------------------------- home masts

class LegSpot(NamedTuple):
    """Where a home mast stands: leg `leg` of switch node `node` on band `band` (level `level`), at strand `strand`
    (drawn on row `row`), reading eastward or not by the leg's side and the node's rail."""
    level: int
    band: int
    node: str
    leg: str
    strand: str
    row: int
    eastward: bool


class MastInputs(NamedTuple):
    """What masts() places by besides the drawing: `cp_of` {switch: control point}, `corner_blocks` {double crossover
    switch: {leg: corner block}}, `running_extra` the passing sidings, `spurs` the spurs with an exit dwarf and
    `split` the tracks parted into two blocks at their turnback."""
    cp_of: Mapping[str, str]
    corner_blocks: Mapping[str, Mapping[str, str]]
    running_extra: frozenset[str] | set[str]
    spurs: frozenset[str] | set[str]
    split: frozenset[str] | set[str]


def masts(bands: Bands, found: Sequence[Track], cp_of: Mapping[str, str],
          corner_blocks: Mapping[str, Mapping[str, str]] | None = None,
          running_extra: frozenset[str] | set[str] = frozenset(), spurs: frozenset[str] | set[str] = frozenset(),
          split: frozenset[str] | set[str] = frozenset(), *, joined: Joined, levels: Levels) -> list[HomeMast]:
    """Home masts where a track from outside a control point meets one of its switches, or where a track inside one
    is long enough to hold a train (over LONG_CM: running track inside an interlocking, staging's K-1/K-2), or where a
    track ending at a bumper that can hold a train leaves one (staging's W-1 and W-2). `running_extra`: track names
    that count as running track besides the main route (passing sidings); `spurs`: spur names that get an exit dwarf
    at their switch even when it is in no control point (cp "" then). Each mast
    gives its switch `node` and `leg`, and `kind`, its JMRI basic appearance: two-searchlight facing the points (two
    heads), one-searchlight on a trailing leg of running track (the main route, or a long track inside an
    interlocking), one-low (a dwarf) on a trailing leg off it (the stock basic system shows Diverging aspects only
    on two heads). A mast none of whose routes reaches another signal is left out (reaches_signal; `joined`, the
    plugin's partners, says which connector ends run on to another band). `levels`: {band title: level}
    (band_levels). Each leg's mast is leg_mast's, the dark ones left out by signalled, the A and B letters given by
    letter_masts."""
    rule = MastInputs(cp_of, corner_blocks or {}, running_extra, spurs, split)
    ends = leg_ends(found)
    out: list[HomeMast] = []
    order: dict[LegKey, LetterOrder] = {}      # (band, node, leg) of a mast: letter_order of its track
    for bi, (title, band, _) in enumerate(bands):
        lv = band_level(title, levels)
        if not lv:
            continue
        rail, srow = band["rail"], band["R"]["srow"]
        for n, d in band["nodes"].items():
            if d["kind"] not in ("switch", "dx") or n not in rail:
                continue
            for p in sorted(set(d["ins"]) | set(d["outs"])):
                hit = ends.get((bi, n, p))
                if hit is None:
                    continue
                sid = d["ins"].get(p) or d["outs"].get(p)
                spot = LegSpot(lv, bi, n, p, sid, srow.get(sid, 0), TAU[p] * rail[n] == 1)
                got = leg_mast(spot, d, hit, rule)
                if got is not None:
                    out.append(got[0])
                    put_order(order, (bi, n, p), got[1])
    out = signalled(bands, out, joined)
    letter_masts(out, order)
    return out


def leg_mast(spot: LegSpot, d: Mapping[str, Any], hit: TrackEnd, rule: MastInputs
             ) -> tuple[HomeMast, LetterOrder] | None:
    """The home mast at switch leg `spot` (switch node `d`, the track `hit` leaving it) with its letter order, or None
    where the rule (masts) puts none. MapError on a balloon loop leaving from a leg that is no loop half's."""
    t, (kind, far) = hit
    num = base(d["label"])
    cp = rule.cp_of.get(num)
    p = spot.leg
    if cp is None or t["name"] in rule.spurs:
        if t["name"] not in rule.spurs:
            return None
        return (home_mast(spot, cp=cp or "", switch=num, protects="", heads=1, track=t["name"], half=0,
                          running=False), letter_order(t, 0, p))
    loop = kind == "sw" and far == num and t["loop"]   # comes back to this switch
    inside = kind == "sw" and far is not None and rule.cp_of.get(far) == cp and not loop
    # a track ending at a bumper gets a mast only when it can hold a train (a staging track trains leave from, W-1
    # and W-2), and then a dwarf, unless it is main route
    if (kind == "bumper" and t["cm"] <= LONG_CM) or (inside and t["cm"] <= LONG_CM):
        return None
    running = t["main"] or inside or t["name"] in rule.running_extra   # long inside track, passing siding
    if t["loop"] and p not in LOOP_HALF:
        raise MapError(f"Switch {num}: balloon loop {t['name']} leaves from leg {p}; a loop's halves "
                       f"leave from legs {' and '.join(LOOP_HALF)}")
    heads = 2 if (p == "A" or d["kind"] == "dx") else 1
    # a split track's half at this end: half 1 at its lower-numbered switch (block_layer.loop_halves)
    sw_ends = sorted((v for k, v in t["ends"] if k == "sw" and v is not None), key=natural)
    split_half = (1 if num == sw_ends[0] else 2) if t["name"] in rule.split else 0
    half = LOOP_HALF[p] if t["loop"] else 0
    track = f"{t['name']} {half}" if half else f"{t['name']} {split_half}" if split_half else t["name"]
    protects = rule.corner_blocks[num][p] if d["kind"] == "dx" else ""
    return (home_mast(spot, cp=cp, switch=num, protects=protects, heads=heads, track=track, half=half,
                      running=running), letter_order(t, half, p))


def signalled(bands: Bands, out: list[HomeMast], joined: Joined) -> list[HomeMast]:
    """The masts of `out` that govern something: a route they would clear reaches another signal (no hand-made
    exceptions). One whose every route ends at a bumper or in dark track is left out, and again until none is: a
    mast kept only by a mast the rule leaves out reaches no signal either."""
    while True:
        posts: defaultdict[int, set[Leg]] = defaultdict(set)
        for m in out:
            posts[m["band"]].add((m["node"], m["leg"]))
        kept = [m for m in out if reaches_signal(bands, m["band"], m["node"], m["leg"], posts, joined)]
        if len(kept) == len(out):
            return out
        out = kept


def letter_masts(out: list[HomeMast], order: Mapping[LegKey, LetterOrder]) -> None:
    """Name each mast of `out`, in place: its switch number plus one, its direction letter, and A or B when two masts
    share both, in the plan order of the tracks they face (letter_order, `order` by (band, node, leg)): a balloon
    loop's A mast faces Loop 1 (leg B, the normal leg) and its B mast Loop 2. MapError on three or more."""
    groups: defaultdict[tuple[int, str], list[HomeMast]] = defaultdict(list)
    for m in out:
        groups[(m["number"], m["letter"])].append(m)
    for (number, letter), ms in groups.items():
        if len(ms) > 2:
            raise MapError(f"switch {number - 1}: {len(ms)} masts for direction {letter}; ADR-005 names two (A and B)")
        ms.sort(key=lambda m: order[(m["band"], m["node"], m["leg"])])
        for i, m in enumerate(ms):
            m["name"] = f"{number}{letter}" + ("AB"[i] if len(ms) == 2 else "")


def put_order(order: dict[LegKey, LetterOrder], key: LegKey, value: LetterOrder) -> None:
    """Record a mast's letter order under its (band, node, leg); MastOrderError when that leg already has a mast, so
    two masts on one leg cannot share the key that sorts them into A and B."""
    if key in order:
        raise MastOrderError(f"two masts on band {key[0]}, node {key[1]}, leg {key[2]}: (band, node, leg) {key} "
                             f"already has a letter order")
    order[key] = value


def home_mast(spot: LegSpot, *, cp: str, switch: str, protects: str, heads: int, track: str, half: int,
              running: bool) -> HomeMast:
    """A home mast at `spot` (a leg of switch `switch`), facing `track`: numbered one above its switch, lettered L
    when it reads eastward (it faces west) and R otherwise, its kind from its heads and whether it stands on running
    track."""
    return HomeMast(level=spot.level, cp=cp, switch=switch, number=int(switch) + 1,
                    letter="L" if spot.eastward else "R", dir="west" if spot.eastward else "east", protects=protects,
                    heads=heads, row=spot.row, track=track, band=spot.band, half=half, node=spot.node, leg=spot.leg,
                    strand=spot.strand, running=running,
                    kind="two-searchlight" if heads == 2 else "one-searchlight" if running else "one-low")
