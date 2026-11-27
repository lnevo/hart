"""The track and mast rule of the schematic levels, out of build_device_map.py so every level can use it.

tracks() lists each track of a band between its ends (switch, helix or bumper), track_names() names them ("Track
<a>-<b>", "Track <n> Spur", "Track <n> Loop", " 1"/" 2" for parallel tracks, in plan_order), and masts() places a home signal where a
track from outside a control point meets one of its switches, unless no route it governs reaches another signal
(reaches_signal; build_device_map.py's module text has the naming and head rules). band_level() maps a band title
to its level by the `level` of its entry in a plan-overrides file (band_levels).
The rules that replaced hand lists: running_tracks (passing sidings between interlockings), signalled_spurs (exit dwarfs off a main track); read_block_splits reads the owner's block
splits (block_overrides.csv kind split), which are a choice, not a rule; hartlib.hand_lists.read_block_overrides is that file's one reader. mast_plan.py runs them all as the one mast process of every level.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple, NotRequired, TypedDict

from hartlib import hand_lists, railroad
from hartlib.track_names import end_order

base = railroad.switch_number
natural = railroad.natural

TAU = {"A": -1, "B": 1, "C": 1, "D": -1}      # the plugin's leg sides (schematic.core.TAU)
LOOP_HALF = {"B": 1, "C": 2}          # a balloon loop's half by the switch leg it leaves from
LONG_CM = 150.0                       # a track inside a control point longer than this can hold a train


class MapError(RuntimeError):
    pass


class MastOrderError(MapError):
    """Two masts on one (band, node, leg): the key that orders a switch's A and B masts would be shared."""


def band_places(overrides: dict) -> dict[str, tuple[int, float | None]]:
    """{band title: (level, height)} of one plan-overrides file: each `levels.bands` entry's name with its `level`
    (main and upper: 2 and 3) and its height, `below` (the cm its track lies under: 5 and 99), or, for a one-band
    input, `level_title` with the file's own `level` (staging: 1) and no height. A band is found by its place, never
    by its title; the titles stay the drawn text. MapError for a band with no level, a level that
    is not 1, 2 or 3, a height that is not a number above 0, a title two bands share, two bands at one level and
    height, or a file that names no band."""
    entries = [(b.get("name"), b.get("level"), b.get("below"), f"levels.bands entry {b.get('name')!r}")
               for b in overrides.get("levels", {}).get("bands", ())]
    if not entries and overrides.get("level_title"):
        entries = [(overrides["level_title"], overrides.get("level"), None, "level_title")]
    if not entries:
        raise MapError("the plan overrides name no band (levels.bands, or level_title)")
    out: dict[str, tuple[int, float | None]] = {}
    at: dict[tuple[int, float | None], str] = {}
    for name, level, height, what in entries:
        if not name:
            raise MapError(f"{what}: no name")
        if type(level) is not int or level not in (1, 2, 3):
            raise MapError(f"{what} has level {level!r}, which is not 1, 2 or 3")
        if height is not None and (type(height) not in (int, float) or not height > 0):
            raise MapError(f"{what}: band {name!r} has height (below) {height!r}, which is not a number above 0")
        if name in out:
            raise MapError(f"two bands are titled {name!r}")
        if (level, height) in at:
            raise MapError(f"bands {at[(level, height)]!r} and {name!r} are both at level {level}, "
                           f"{'height ' + format(height, 'g') if height is not None else 'no height'}")
        at[(level, height)] = name
        out[name] = (level, height)
    return out


def band_levels(overrides: dict) -> dict[str, int]:
    """{band title: level} of one plan-overrides file (band_places, every check of it, without the height)."""
    return {name: level for name, (level, _height) in band_places(overrides).items()}


def band_level(title: str, levels: dict) -> int | None:
    """The level of a band by its title, in `levels` (band_levels); None for a band `levels` does not hold."""
    return levels.get(title) if title else None


Joined = dict[tuple[int, str], tuple[int, str]]      # the plugin's connector partners: (band, node) -> (band, node)


def beyond_connector(bands, joined: Joined, bi: int, node: str) -> tuple[int, tuple[str, str]] | None:
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
    return bj, tuple(s["dst"] if s["src"][0] == m else s["src"])


def end_ref(bands, joined, bi, node_id, helix_tag, levels):
    """What a track ends at: ("sw", number), ("helix", "H1"), ("bumper", None). A connector to the other band
    is followed to the switch beyond it."""
    band = bands[bi][1]
    d = band["nodes"][node_id]
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


def end_label(bands, joined, bi, node_id) -> str:
    """The switch label a track ends at, followed through a connector to the other band ("" at a bumper or
    helix): the halves of the helix-top crossovers 127 and 131 sit on two bands, joined by connectors."""
    d = bands[bi][1]["nodes"][node_id]
    if d["kind"] in ("switch", "dx"):
        return d.get("label") or ""
    if (far := beyond_connector(bands, joined, bi, node_id)) is not None:
        return end_label(bands, joined, far[0], far[1][0])
    return ""


def end_leg(bands, joined, bi, end) -> str:
    """A track end (node, port) by its plan switch label and leg ("103AB", "113C"; a moved switch's star dropped),
    followed through a connector to the switch beyond it as end_ref does; "helix" at a helix end, "end" at any other
    (a bumper). The same key staging_device_map.end_key gives a run's end, so it comes from the plan, not the drawing."""
    band = bands[bi][1]
    node, port = end
    d = band["nodes"][node]
    if d["kind"] in ("switch", "dx"):
        return f"{(d.get('label') or '').rstrip('*')}{port}"
    if d.get("sub") == "helix":
        return "helix"
    if (far := beyond_connector(bands, joined, bi, node)) is not None:
        return end_leg(bands, joined, far[0], far[1])
    return "end"



End = tuple[str, str | None]         # what a track ends at (end_ref): ("sw", number), ("helix", "H1"), ("bumper", None)
Leg = tuple[str, str]                # a switch leg on a band: (node, port)


class Track(TypedDict):
    """One track of the main and upper bands (tracks); `name` is filled by track_names."""
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


TrackKey = tuple[int, str]           # a track entry's band and first strand (entry_key): one entry per track


def entry_key(t: Track) -> TrackKey:
    """The key of track entry `t` that stays the same however the entry is copied: its band and its first strand."""
    return t["band"], t["strands"][0]


def plan_order(t: Track) -> tuple:
    """The order of tracks that share their end switches (parallel tracks): by their ends' plan labels and legs, lower
    end first (the order of their device IDs, block:103AB-105B before block:103BA-105C), so the numbers in "Track
    103-105 1" and "2", and block_overrides.csv's `parallel`, come from the plan and not from the drawn rows."""
    return tuple(sorted((end_order(k) for k in t["plan_ends"]))) + (t["trial"],)


def letter_order(t: Track, half: int, leg: str) -> tuple:
    """The order of two home masts of one number and direction (their A and B): by the plan order of the tracks they
    face (plan_order, so the A mast faces a Spur 1 and the B mast its Spur 2, as the track numbers run), then a
    balloon loop's half (the A mast faces Loop 1, from leg B), then the leg they stand at. From the plan, not the
    drawn rows."""
    return plan_order(t) + (half, leg)


def helix_tags(bands, overrides) -> dict[int, str]:
    """{level: "H1"|"H2"}: the helix tracks in the overrides' order, each on the band holding its switch."""
    relabel = next(e["map"] for e in overrides["edits"] if e["op"] == "relabel")
    levels, out = band_levels(overrides), {}
    for i, sw in enumerate(overrides.get("helix", {})):
        label = relabel.get(sw, sw)
        for title, band, _ in bands:
            if any(d.get("label", "").rstrip("*") == label for d in band["nodes"].values()):
                lv = band_level(title, levels)
                if lv is not None:         # a band with no level (none today) draws no helix track
                    out[lv] = f"H{i + 1}"
    return out


HELIX_SOURCE = railroad.Sources.under().plan_overrides     # plan_overrides.json: the helix ends and map


class HelixEntry(TypedDict):
    """One helix track as read_helix_tracks gives it: its JMRI block, the switches at its two ends and its shown name."""
    block: str
    staging_switch: str
    level_switch: str
    shown: str


def read_helix_tracks(path: Path | None = None) -> dict[str, HelixEntry]:
    """{plan helix track name: {block, staging_switch, level_switch, shown}} from the plan overrides (hartlib.railroad
    .read_helix_tracks, which checks them): each helix track is one JMRI block, "Track <plan name>" by the ordinary
    rule, from its staging switch to its main or upper switch; `shown` is the name a reader
    sees (preferences.json track_labels). Its FactsError as a MapError."""
    try:
        got = railroad.read_helix_tracks(path or HELIX_SOURCE)
    except railroad.FactsError as exc:
        raise MapError(str(exc)) from exc
    return {h.helix: HelixEntry(block=h.block, staging_switch=h.staging_switch, level_switch=h.level_switch,
                                shown=h.shown) for h in got.values()}


def helix_blocks(overrides, helix: Mapping[str, HelixEntry] | None = None) -> dict[str, str]:
    """{helix tag ("H1", "H2", as helix_tags gives them): block} for the main and upper levels: the overrides' helix
    tracks in order, each "Track <plan name>" (read_helix_tracks). Stops on a helix track of `overrides` that
    `helix` does not hold, or one it holds that the overrides do not have."""
    helix = read_helix_tracks() if helix is None else helix
    plan = list(overrides.get("helix", {}).values())
    if sorted(plan) != sorted(helix):
        raise MapError(f"the helix tracks are {sorted(helix)}, the plan overrides' helix map {sorted(plan)}")
    return {f"H{i + 1}": helix[name]["block"] for i, name in enumerate(plan)}


def tracks(bands, runs, joined: Joined, helix_tag, levels) -> list[Track]:
    """One entry per track of the main and upper bands (a track cut by a connector counted once)."""
    found, seen = [], set()
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
            edges = {}
            for sid, _ in chain:
                edges[re.sub(r"(?<=\d)[xy]$", "", strands[sid]["edge"])] = strands[sid]["cm"]
            key = tuple(sorted(edges))
            if key in seen:
                continue
            seen.add(key)
            ends = [(start[0], start[1]), (end[0], end[1])]
            found.append(Track(level=lv, ends=(a, b), legs=ends, band=bi,
                               plan_ends=tuple(end_leg(bands, joined, bi, e) for e in ends),
                               cm=round(sum(edges.values()), 1), loop=start[0] == end[0] and a[0] == "sw",
                               main=any(strands[sid]["main"] for sid, _ in chain),
                               row=min(srow.get(sid, 0) for sid, _ in chain),
                               strands=[sid for sid, _ in chain],
                               trial=sorted({"Track " + re.sub(r"(?<=\d)[xy]$", "", strands[sid]["edge"])
                                             for sid, _ in chain})))
    return found


def track_names(found, helix=None) -> None:
    """Fill `name` in each track entry (see the module text). `helix` ({helix tag: block}, helix_blocks) names each
    track that reaches the helix by its helix block (main and upper: one block from staging up the helix, owner
    2026-11-20); without it (staging's own mast rule) such a track is "Track <switch>-<tag>". A track reaching a helix
    tag that `helix` does not name stops."""
    groups = defaultdict(list)
    for t in found:
        sw = sorted([v for k, v in t["ends"] if k == "sw"], key=natural)
        hx = [v for k, v in t["ends"] if k == "helix"]
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
        elif sw and not hx and len(sw) == 1:
            stem = f"Track {sw[0]} Spur"
        else:
            stem = "Track " + "-".join(sw + hx)
        groups[stem].append(t)
    for stem, ts in groups.items():
        if len(ts) > 1:
            ts.sort(key=plan_order)
        for i, t in enumerate(ts, 1):
            t["name"] = stem if len(ts) == 1 else f"{stem} {i}"


# ---------------------------------------------------------------- hand lists keyed by end switches

# block_overrides.csv's reader and its row rules are hartlib.hand_lists'; the names stay here
TRACK_KEY_COLUMNS = hand_lists.TRACK_KEY_COLUMNS
SWITCH_NUMBER = hand_lists.SWITCH_NUMBER


def track_key(t: Mapping[str, Any]) -> tuple[str, str] | None:
    """The end switches of a track entry, lower number first: (a, b) between two switches, (n, n) for a balloon loop
    and (n, "") for a spur (one switch, a bumper at the other end). None for a track up the helix, which its helix
    block names ("Track <plan name>"). Hand lists name a track by this key, so a renumbered switch moves the row with
    it, where a generated name ("Track 119-121") would have to be retyped."""
    if any(k == "helix" for k, _v in t["ends"]):
        return None
    sw = sorted((v for k, v in t["ends"] if k == "sw"), key=natural)
    return (sw[0], sw[1] if len(sw) == 2 else "") if sw else None


key_problem = hand_lists.key_problem
override_problem = hand_lists.override_problem
OVERRIDES_NAME = hand_lists.OVERRIDES_NAME     # in the schematic data folder, beside plan_overrides.json
OVERRIDE_COLUMNS = hand_lists.OVERRIDE_COLUMNS
OVERRIDE_KINDS = hand_lists.OVERRIDE_KINDS
OS_ID = hand_lists.OS_ID


def read_block_overrides(path: Path, kinds: tuple[str, ...] = OVERRIDE_KINDS) -> list[dict]:
    """hartlib.hand_lists.read_block_overrides (its text has the kinds and rows), its HandListError a MapError."""
    try:
        return hand_lists.read_block_overrides(path, kinds)
    except hand_lists.HandListError as exc:
        raise MapError(str(exc)) from exc


def os_block_name(level: str, ident: str, halves: dict, names=None) -> str:
    """hartlib.hand_lists.os_block_name, its HandListError a MapError."""
    try:
        return hand_lists.os_block_name(level, ident, halves, names)
    except hand_lists.HandListError as exc:
        raise MapError(str(exc)) from exc


def resolve_track(row: dict, found: list[Track]) -> Track | None:
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
                          "give parallel, 1 for the first by plan ends (mast_rule.plan_order)")
        return None
    return same[0]


# ---------------------------------------------------------------- rules that replace hand lists

def through_leg(band, node: str, leg: str) -> str | None:
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
    return rest[0] if leg == "A" or rest == ["A"] else None


def by_leg(found) -> dict:
    """{(band, switch node, leg): track entry} of every track end at a switch leg."""
    out = {}
    for t in found:
        for (n, p) in t["legs"]:
            out[(t["band"], n, p)] = t
    return out


def running_tracks(bands, found, cp_of: dict) -> set[str]:
    """The names of the tracks that count as running track besides the main route (it replaced
    the hand list running_tracks_main_upper.csv): a chain of non-main tracks joining two different interlockings
    (`cp_of`, {switch: interlocking}), where the chain may run on through the through route of a crossover half in no interlocking
    (through_leg: local crossover 121 on the long siding). A passing siding between two control points is running
    track; a spur, a loop, a track up the helix or one ending in a yard is not. On staging it makes Scale (5-7) running
    track."""
    legs = by_leg(found)

    def walk(t, n, p, chain):
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

    out = set()
    for t in found:
        if t["main"] or t["loop"] or any(k != "sw" for k, _v in t["ends"]):
            continue
        chain = {id(t): t}
        ends = [walk(t, n, p, chain) for (n, p) in t["legs"]]
        if ends[0] and ends[1] and ends[0] != ends[1]:
            out |= {u["name"] for u in chain.values()}
    return out


def signalled_spurs(found, cp_of: dict) -> set[str]:
    """The names of the spurs that get an exit dwarf (it replaced the hand list
    signalled_spurs_main_upper.csv): a spur (one switch, a buffer stop at the other end) off a main track at a switch in no interlocking (`cp_of`): Track
    241 Spur."""
    out = set()
    for t in found:
        sw = [v for k, v in t["ends"] if k == "sw"]
        if len(sw) != 1 or not any(k == "bumper" for k, _v in t["ends"]) or sw[0] in cp_of:
            continue
        if any(u["main"] for u in found if u is not t and u["level"] == t["level"]
               and sw[0] in [v for k, v in u["ends"] if k == "sw"]):
            out.add(t["name"])
    return out


def read_block_splits(path: Path, found: list[Track], levels) -> set[str]:
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


TrackEnd = tuple[Track, End]        # a track at a switch leg and what its far end is


def leg_ends(found: Sequence[Track]) -> dict[tuple[int, str, str], TrackEnd]:
    """{(band, node, leg): (track, its far end)} of every track end at a switch leg."""
    out: dict[tuple[int, str, str], TrackEnd] = {}
    for t in found:
        for (n, p), far in zip(t["legs"], reversed(t["ends"])):
            out[(t["band"], n, p)] = (t, far)
    return out


def masts(bands, cps, found, cp_of, corner_blocks=None, running_extra=frozenset(),
          spurs=frozenset(), split=frozenset(), *, joined, levels) -> list[HomeMast]:
    """Home masts where a track from outside a control point meets one of its switches, or where a track inside one
    is long enough to hold a train (over LONG_CM: running track inside an interlocking, staging's K-1/K-2), or where a
    track ending at a bumper that can hold a train leaves one (staging's W-1 and W-2). `running_extra`: track names
    that count as running track besides the main route (passing sidings); `spurs`: spur names that get an exit dwarf
    at their switch even when it is in no control point (cp "" then). Each mast
    gives its switch `node` and `leg`, and `kind`, its JMRI basic appearance: two-searchlight facing the points (two
    heads), one-searchlight on a trailing leg of running track (the main route, or a long track inside an
    interlocking), one-low (a dwarf) on a trailing leg off it (owner,
    2026-11-19: the stock basic system shows Diverging aspects only on two heads). A mast none of whose routes
    reaches another signal is left out (reaches_signal; `joined`, the plugin's partners, says which connector ends
    run on to another band). `levels`: {band title: level} (band_levels). Each leg's mast is leg_mast's, the dark ones
    left out by signalled, the A and B letters given by letter_masts."""
    rule = MastInputs(cp_of, corner_blocks or {}, running_extra, spurs, split)
    ends = leg_ends(found)
    out: list[HomeMast] = []
    order: dict[tuple[int, str, str], tuple] = {}      # (band, node, leg) of a mast: letter_order of its track
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


def leg_mast(spot: LegSpot, d: Mapping[str, Any], hit: TrackEnd, rule: MastInputs) -> tuple[HomeMast, tuple] | None:
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
    # a split track's half at this end: half 1 at its lower-numbered switch (build_device_map.loop_halves)
    sw_ends = sorted((v for k, v in t["ends"] if k == "sw" and v is not None), key=natural)
    split_half = (1 if num == sw_ends[0] else 2) if t["name"] in rule.split else 0
    half = LOOP_HALF[p] if t["loop"] else 0
    track = f"{t['name']} {half}" if half else f"{t['name']} {split_half}" if split_half else t["name"]
    protects = rule.corner_blocks[num][p] if d["kind"] == "dx" else ""
    return (home_mast(spot, cp=cp, switch=num, protects=protects, heads=heads, track=track, half=half,
                      running=running), letter_order(t, half, p))


def signalled(bands, out: list[HomeMast], joined: Joined) -> list[HomeMast]:
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


def letter_masts(out: list[HomeMast], order: Mapping[tuple[int, str, str], tuple]) -> None:
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


def put_order(order: dict[tuple[int, str, str], tuple], key: tuple[int, str, str], value: tuple) -> None:
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


# where a train leaves a switch by, entering it at a leg: a plain switch's points (A) choose B or C and B or C trail to
# A; a double crossover joins A to B and C, D to C and B (its through tracks A-B and D-C, both diagonals)
EXITS: dict[str, dict[str, tuple[str, ...]]] = {"switch": {"A": ("B", "C"), "B": ("A",), "C": ("A",)},
         "dx": {"A": ("B", "C"), "B": ("A", "D"), "C": ("D", "A"), "D": ("C", "B")}}


def reaches_signal(bands, bi: int, node: str, leg: str, posts: Mapping[int, set[Leg]], joined: Joined) -> bool:
    """True when some route of a train entering switch `node` of band `bi` at `leg` reaches another signal: a switch
    leg in `posts` ({band index: {(node, leg)}} of the masts) that it enters by, other than the one it starts at, or
    an end where the track runs on: a helix end (its signals are the other level's) or an open end (track running on
    off the drawing), so the rule never leaves out a mast whose route runs on beyond what is drawn. A connector end is
    followed to the other band when `joined` (the plugin's partners, {(band, node): (band, node)}) joins it, as
    end_ref does, and is a bumper when it does not. Every route is walked through switches and turnbacks to the next
    mast or the end of track; a route ending at a bumper, or in track with no mast facing on (a dark spur or yard),
    reaches none. A route that comes back to a leg already walked, its own start among them, adds nothing."""
    return route_ends(bands, bi, node, leg, posts, joined)[0]


def route_ends(bands, bi: int, node: str, leg: str, posts: Mapping[int, set[Leg]], joined: Joined
               ) -> tuple[bool, set[tuple[int, str]]]:
    """(reaches a signal, {(band, buffer stop node)} reached before any mast) over every route of a train entering
    switch `node` of band `bi` at `leg`, walked as reaches_signal says (the whole walk: a route that reaches a signal
    stops there, the others run on). The buffer stops are where a mast in `posts` needs a destination
    (mast_plan.virtual_masts)."""
    def legs(b, n):
        d = bands[b][1]["nodes"][n]
        return d["ins"] | d["outs"]

    def far_end(b, n, x):
        """(band, node, port) a train reaches leaving node `n` of band `b` by its port `x`, on through any turnback
        and joined connector."""
        while True:
            nodes, strands = bands[b][1]["nodes"], bands[b][1]["strands"]
            s = strands[legs(b, n)[x]]
            m, q = s["dst"] if tuple(s["src"]) == (n, x) else s["src"]
            kind, sub = nodes[m]["kind"], nodes[m].get("sub")
            if kind.startswith("turn"):
                onward = [k for k in legs(b, m) if k != q]
                if len(onward) != 1:
                    raise MapError(f"reaches_signal: turnback {m} has {len(onward) + 1} tracks, not two")
                n, x = m, onward[0]
            elif kind == "end" and sub == "link" and (b, m) in joined:
                b, n = joined[(b, m)]
                x = next(iter(legs(b, n)))
            else:
                return b, m, q

    start = (bi, node, leg)
    todo, seen, signal = [start], {start}, False
    bumpers: set[tuple[int, str]] = set()
    while todo:
        b, n, p = todo.pop()
        d = bands[b][1]["nodes"][n]
        if d["kind"] not in EXITS:
            raise MapError(f"reaches_signal: a route enters {d['kind']} node {n}, which is no switch")
        for x in EXITS[d["kind"]][p]:
            if legs(b, n).get(x) is None:
                continue
            here = far_end(b, n, x)
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


def facing_on_route(band, node: str, leg: str, cp_of: dict, long_cm: float = LONG_CM) -> list[str]:
    """The switch numbers whose points a train meets facing, on any route from entering switch `node` at `leg`,
    inside the control point (interlocking) that switch is in, before it leaves it or reaches the next signal: a track
    longer than `long_cm` inside the interlocking holds signals of its own, so the walk stops there. Entering a switch
    at A meets its points facing (a choice of B or C); entering at B or C trails through to A. Turnbacks are followed.
    Used to give a home mast two heads when a route it governs can still diverge."""
    nodes, strands = band["nodes"], band["strands"]
    first = nodes[node]
    cp = cp_of.get(base(first.get("label") or ""))

    def leg_strand(n, p):
        d = nodes[n]
        return d["ins"].get(p) or d["outs"].get(p)

    def at_other_end(sid, n):
        s = strands[sid]
        return tuple(s["dst"]) if s["src"][0] == n else tuple(s["src"])

    out, seen = [], set()
    todo = [(node, leg)]
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
