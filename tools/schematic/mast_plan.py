"""One mast process for every level (archive/history/wiki/projects/level-unification-handoff.md, Masts).

plan() places every mast of the levels it is asked for, the same way on each, from the plan's tracks, the
interlockings (interlockings.csv, the signal rule's control points), the owner's block splits (block_overrides.csv) and
the level's block layer:

1. Home masts by mast_rule.masts, with running track and exit dwarfs by rule (mast_rule.running_tracks,
   mast_rule.signalled_spurs), pruned by reaches_signal over the visible masts only
   (so 126L stays out); two heads when a route can still diverge inside the interlocking (facing_on_route), high
   from running track, a dwarf from a yard, lead or siding.
2. Intermediates (APB pairs): at each block boundary inside a running track (main, running by rule, or a long track
   inside one interlocking) with at least one end in an interlocking, where both blocks hold a train (over
   mast_routes.LONG_CM). Named from the milepost in tenths, odd westbound and even eastbound, after the level's line
   code (LINE_CODE: A main, B upper, none on staging, where a name stops at 98 so it never reads as a three-digit
   home mast). A number another intermediate already holds moves on to the next free one of its parity
   (assign_numbers).
   West is toward the lower milepost; on a balloon loop, which starts and ends at one switch, the
   eastbound mast faces Loop 1 (the half from leg B).
3. Virtual masts only as destinations: every route of each kept home mast is walked (mast_routes.route_ends) to the
   first visible mast; a route that reaches a buffer stop first gets a hidden bumper mast there, facing it. Nothing
   else gets one. A bumper mast is named as a home mast is, from the switch the track to the buffer stop leaves (its
   number + 1) and the letter a train heading for the buffer stop reads; masts of one number and letter take A, B ...
   in the plan order of their tracks (the switch leg each leaves: hartlib.track_names.end_order, as home masts follow
   plan_tracks.letter_order), after the letters the visible masts use (120RA and 120RB stand,
   so the bumper mast is 120RC); a visible mast with the bare name stops the build.

The block layer is each level's own: staging's from its device map's block rows and
block_lengths.csv (device_map_masts.py), main and upper's generated one block per track, loop and split halves
(device_map_schematic.main_upper_layer). One writer turns these masts into every level's device rows,
build_device_map.py (staging's through device_map_masts.py, with their plan facts; main and upper's through
device_map_level_masts.plan_rows); build_masts.py writes masts.csv, every level, from those rows.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Literal, NamedTuple, NotRequired, TypedDict

import le_names as ln
import mast_routes
import mast_rule as mr
import plan_bands
import plan_tracks
from map_error import MapError
from plan_bands import Band, Bands
from plan_tracks import Leg
import publish_draft  # noqa: F401  imported for its side effect: it puts hartlib on the path before the hartlib import below
from hartlib import hand_lists, level_masts
from hartlib.track_names import end_order

RETIRED = hand_lists.RETIRED_MASTS             # the virtual masts dropped from a level (hartlib.hand_lists)
RETIRED_COLUMNS = hand_lists.RETIRED_MAST_COLUMNS

LINE_CODE = {1: "", 2: "A", 3: "B"}   # milepost line codes, after Furnace A and B; staging has none
CM_PER_SCALE_MILE = 63360 * 2.54 / 87.1
LOOP_FIRST = next(leg for leg, half in mr.LOOP_HALF.items() if half == 1)   # a loop's half 1 leaves from leg B
SWITCHES = ("switch", "dx")

Direction = Literal["west", "east"]


class Run(NamedTuple):
    """One run of a band (run_blocks): its start and end (node, port) and its blocks in order from the start."""
    start: Leg
    blocks: list[str]
    end: Leg


class Intermediate(TypedDict):
    """An intermediate mast (intermediates): its name (with the line code, no "Mast "), level, band, dir, the blocks it
    protects and faces, milepost, the run's start and end, `to` (the end it heads for), toward and other (their switch
    numbers), dist (cm from `to` to the boundary), total (the run's cm) and cp (the interlocking of `toward`, else of
    `other`). The device map's builders read it by key; `id` is filled by the device map's build."""
    name: str
    level: int
    band: int
    dir: Direction
    protects: str
    facing: str
    milepost: float
    start: Leg
    end: Leg
    to: Leg
    toward: str
    other: str
    dist: float
    total: float
    cp: str
    id: NotRequired[str]


class UnnamedIntermediate(TypedDict):
    """An Intermediate before assign_numbers gives it its name."""
    level: int
    band: int
    dir: Direction
    protects: str
    facing: str
    milepost: float
    start: Leg
    end: Leg
    to: Leg
    toward: str
    other: str
    dist: float
    total: float
    cp: str


class Pending(NamedTuple):
    """An intermediate waiting for its name: its line code, natural number (signal_number), milepost and fields."""
    code: str
    number: int
    mp: float
    mast: UnnamedIntermediate


class VirtualFields(TypedDict):
    """A virtual mast before it is lettered (virtual_masts)."""
    level: int
    band: int
    node: str
    leg: str
    switch: str
    bumper: str
    dir: Direction
    facing: str
    seq: list[str]
    total: float
    needed_by: list[str]


class VirtualMast(VirtualFields):
    """A virtual mast (virtual_masts): VirtualFields and its name (no "Mast "); `id` is filled by the device map's
    build."""
    name: str
    id: NotRequired[str]


class MastPlan(TypedDict):
    """plan's masts of the levels asked for: home masts (mast_rule.HomeMast), intermediates and virtual masts."""
    home: list[mr.HomeMast]
    intermediates: list[Intermediate]
    virtual: list[VirtualMast]


def run_blocks(band: Band, names: Mapping[str, Mapping[str, list[str]]]) -> list[Run]:
    """Each run of the band (le_names.runs: tracks joined through turnbacks, crossover insides left out) with its
    blocks from `names` ({"blocks": {strand: [block, ...]}}) in order from its start; a block that runs on through a
    turnback (Brick-Plane) counted once."""
    out = []
    for start, chain, end in ln.runs(band, ln.crossover_strands(band)):
        seq: list[str] = []
        for sid, rev in chain:
            bl = names["blocks"][sid]
            for b in (bl[::-1] if rev else bl):
                if not seq or seq[-1] != b:
                    seq.append(b)
        out.append(Run(tuple(start), seq, tuple(end)))
    return out


def node_mileposts(band: Band) -> dict[str, float]:
    """{node: milepost} of every node the band's milepost count reaches (band["mp"]: strand -> (start node, start
    milepost, length in miles, end node))."""
    out: dict[str, float] = {}
    for start, mp, length, end in band["mp"].values():
        out.setdefault(start, mp)
        out.setdefault(end, mp + length)
    return out


def signal_number(mp: float, west: bool, code: str = "") -> int:
    """An intermediate signal's number from its milepost in tenths: odd westbound, even eastbound (prototype). With no
    line code (staging) a number over 98 stops the build: 99 and up, and a three-digit name would read as a main or upper home mast
    (hartlib.level_devices.LEVEL_USER)."""
    n = int(mp * 10 + 1e-9)
    number = (n if n % 2 else n + 1) if west else (n if n % 2 == 0 else n + 1)
    if not code and number > 98:
        raise MapError(f"MP {mp:.2f} gives intermediate number {number}; names with no line code stop at 98")
    return number


def assign_numbers(pending: Sequence[Pending]) -> list[Intermediate]:
    """The intermediates of `pending` in its order, each named from its line code and natural number. Two pairs under
    a tenth of a mile apart share a westward number (6.6 and 6.7 both give 67: the odd and even numbers give one
    number per two tenths). Every natural number is reserved first; of the masts that share one, the lowest milepost
    keeps it and each other takes the next number of its parity that no intermediate holds or would hold, so no mast
    without a clash is renamed. Each shift is printed with both mileposts. With no line code a shifted number stops at
    98 like any other."""
    natural = {f"{p.code}{p.number}" for p in pending}
    holder: dict[str, Pending] = {}
    names: dict[int, str] = {}
    order = sorted(range(len(pending)), key=lambda i: (pending[i].code, pending[i].number, pending[i].mp,
                                                       pending[i].mast["dir"]))
    for i in order:
        p = pending[i]
        code, number = p.code, p.number
        name = f"{code}{number}"
        if name in holder:
            held = holder[name]
            while f"{code}{number}" in natural or f"{code}{number}" in holder:
                number += 2
            if not code and number > 98:
                raise MapError(f"MP {p.mp:.3f}: intermediate {p.number} is held by MP {held.mp:.3f} and the next "
                                  f"free number {number} is over 98; names with no line code stop at 98")
            name = f"{code}{number}"
            print(f"mast_plan: MP {p.mp:.3f} would be intermediate {code}{p.number}, which MP {held.mp:.3f} holds; "
                  f"named {name}", file=sys.stderr)
        holder[name] = p
        names[i] = name
    return [{"name": names[i], **p.mast} for i, p in enumerate(pending)]


def letter_at(band: Band, node: str, leg: str) -> str:
    """The direction letter of a mast at switch `node`'s `leg` facing into the switch, as mast_rule.masts names it."""
    return "L" if mr.TAU[leg] * band["rail"][node] == 1 else "R"


def _label(band: Band, node: str) -> str:
    """The switch number of `node`, "" when it is not a switch."""
    d = band["nodes"][node]
    return mr.base(d.get("label") or "") if d["kind"] in SWITCHES else ""


def _needs_lengths(blocks: Iterable[str], cm: Mapping[str, float]) -> None:
    """MapError naming each of `blocks` that `cm` gives no length."""
    missing = sorted(set(blocks) - set(cm))
    if missing:
        raise MapError(f"no length for block(s) {missing}: a mast's place and milepost need every block's length")


def home_masts(bands: Bands, joined: plan_tracks.Joined, found: list[plan_tracks.Track], cp_of: Mapping[str, str], running: set[str],
               *, levels: Mapping[str, int], corner_blocks: dict | None = None,
               split: frozenset[str] | set[str] = frozenset()) -> list[mr.HomeMast]:
    """Step 1 (module text): the home masts of `levels`, each with its heads and kind; `running`: the running tracks
    by rule (mast_rule.running_tracks)."""
    spurs = mr.signalled_spurs(found, cp_of)
    home = mr.masts(bands, found, cp_of, corner_blocks or {}, levels=levels, running_extra=running,
                    spurs=spurs, split=split, joined=joined)
    for m in home:
        if m["heads"] == 1 and mast_routes.facing_on_route(bands[m["band"]][1], m["node"], m["leg"], cp_of):
            m["heads"] = 2
        m["kind"] = f"{'two' if m['heads'] == 2 else 'one'}-{'searchlight' if m['running'] else 'low'}"
    return home


def _signalled_run(band: Band, bi: int, run: Run, legs: Mapping, cp_of: Mapping[str, str],
                   running: set[str]) -> tuple[Run, list[str]] | None:
    """(the run, read from a balloon loop's half 1, and its two end switches' numbers) when the run takes
    intermediates: switch to switch, one end in an interlocking, and main, running by rule or inside one
    interlocking; None for any other run, and for a crossover's inside (its OS block, no boundary)."""
    nodes = band["nodes"]
    start, seq, end = run
    if any(nodes[e[0]]["kind"] not in SWITCHES for e in (start, end)):
        return None
    sw = [_label(band, start[0]), _label(band, end[0])]
    if not any(s in cp_of for s in sw):
        return None
    t = legs.get((bi, start[0], start[1]))
    if t is None:
        return None
    inside = cp_of.get(sw[0]) is not None and cp_of.get(sw[0]) == cp_of.get(sw[1])
    if not (t["main"] or t["name"] in running or inside):
        return None
    if start[0] == end[0] and start[1] != LOOP_FIRST:      # a balloon loop is read from its half 1
        return Run(end, seq[::-1], start), sw[::-1]
    return run, sw


def _boundary_pair(run: Run, sw: list[str], a: str, b: str, *, level: int, bi: int, code: str,
                   mp_at: Mapping[str, float], cm: Mapping[str, float],
                   cp_of: Mapping[str, str]) -> list[Pending]:
    """The westbound and eastbound intermediates at the boundary of blocks `a` and `b` on `run` (end switches `sw`)."""
    start, seq, end = run
    if start[0] not in mp_at or end[0] not in mp_at:
        raise MapError(f"the boundary {a}|{b} cannot be numbered: switch "
                          f"{sw[0] if start[0] not in mp_at else sw[1]} is not on the milepost count")
    total = sum(cm[x] for x in seq)
    from_start = sum(cm[x] for x in seq[:seq.index(b)])
    low_is_start = mp_at[start[0]] <= mp_at[end[0]]
    mp = (mp_at[start[0]] + from_start / CM_PER_SCALE_MILE if low_is_start
          else mp_at[end[0]] + (total - from_start) / CM_PER_SCALE_MILE)
    west_to, east_to = (start, end) if low_is_start else (end, start)
    out = []
    for west, to in ((True, west_to), (False, east_to)):
        at_start = to is start
        toward, other = (sw[0], sw[1]) if at_start else (sw[1], sw[0])
        cp = cp_of.get(toward) or cp_of[other]
        out.append(Pending(code, signal_number(mp, west, code), mp, UnnamedIntermediate(
            level=level, band=bi, dir="west" if west else "east",
            protects=a if at_start else b, facing=b if at_start else a,
            milepost=round(mp, 3), start=start, end=end, to=to, toward=toward, other=other,
            dist=round(from_start if at_start else total - from_start, 1),
            total=round(total, 1), cp=cp)))
    return out


def intermediates(bands: Bands, found: list[plan_tracks.Track], runs_by_band: Mapping[int, list[Run]],
                  layer: Mapping[int, Mapping[str, dict]], cm: Mapping[str, float], cp_of: Mapping[str, str],
                  running: set[str], levels: Mapping[str, int]) -> list[Intermediate]:
    """Step 2 (module text): a pair at each boundary of two long blocks (over mast_routes.LONG_CM) inside a run that
    takes intermediates (_signalled_run), named by assign_numbers. MapError on a band of runs with no level."""
    legs = plan_tracks.by_leg(found)
    pending: list[Pending] = []
    for bi, runs in sorted(runs_by_band.items()):
        band = bands[bi][1]
        level = plan_bands.band_level(bands[bi][0], levels)
        if level is None:
            raise MapError(f"band {bands[bi][0]!r} has runs but no level")
        code = LINE_CODE[level]
        os_ = layer[bi]["os"]
        mp_at = node_mileposts(band)
        for raw in runs:
            got = _signalled_run(band, bi, Run(*raw), legs, cp_of, running)
            if got is None:
                continue
            run, sw = got
            body = [b for b in run.blocks if b not in (os_.get(run.start[0]), os_.get(run.end[0]))]
            _needs_lengths(run.blocks, cm)
            for a, b in zip(body, body[1:]):
                if cm[a] > mast_routes.LONG_CM and cm[b] > mast_routes.LONG_CM:
                    pending += _boundary_pair(run, sw, a, b, level=level, bi=bi, code=code, mp_at=mp_at, cm=cm,
                                              cp_of=cp_of)
    return assign_numbers(pending)


def _buffer_stop_needs(bands: Bands, joined: plan_tracks.Joined,
                       home: Sequence[mr.HomeMast]) -> dict[tuple[int, str], set[str]]:
    """{(band, buffer stop node): the home masts whose routes end there} (mast_routes.route_ends)."""
    posts: defaultdict[int, set[tuple[str, str]]] = defaultdict(set)
    for m in home:
        posts[m["band"]].add((m["node"], m["leg"]))
    need: defaultdict[tuple[int, str], set[str]] = defaultdict(set)
    for m in home:
        _signal, bumpers = mast_routes.route_ends(bands, m["band"], m["node"], m["leg"], posts, joined)
        for e in bumpers:
            need[e].add(m["name"])
    return need


def _buffer_stop_tracks(bands: Bands,
                        runs_by_band: Mapping[int, list[Run]]) -> dict[tuple[int, str], tuple[Leg, list[str]]]:
    """{(band, buffer stop node): (the switch leg the track to it leaves, its blocks from that switch)}."""
    reach = {}
    for bi, runs in runs_by_band.items():
        nodes = bands[bi][1]["nodes"]
        for start, seq, end in runs:
            for here, there, s in ((start, end, seq), (end, start, seq[::-1])):
                if nodes[there[0]].get("sub") == "bumper" and nodes[here[0]]["kind"] in SWITCHES:
                    reach[(bi, there[0])] = (here, s)
    return reach


def virtual_masts(bands: Bands, joined: plan_tracks.Joined, home: Sequence[mr.HomeMast],
                  runs_by_band: Mapping[int, list[Run]], cm: Mapping[str, float], taken: set[str],
                  levels: Mapping[str, int]) -> list[VirtualMast]:
    """Step 3 (module text): each VirtualMast; node and leg are the switch leg the track to the buffer stop leaves,
    switch its number, bumper the buffer stop's node, facing the block next to the buffer stop, seq the blocks from
    the switch to the buffer stop, total their cm and needed_by the visible masts whose routes end there. `taken`: the
    visible masts' names. MapError on a buffer stop no track from a switch reaches, a name a visible mast has bare, or
    more than four masts of one number and letter."""
    need = _buffer_stop_needs(bands, joined, home)
    reach = _buffer_stop_tracks(bands, runs_by_band)
    groups: defaultdict[tuple[int, str], list[tuple[tuple, VirtualFields]]] = defaultdict(list)
    for e, who in sorted(need.items()):
        if e not in reach:
            raise MapError(f"the routes of {', '.join(sorted(who, key=mr.natural))} end at buffer stop {e[1]} on "
                              f"{bands[e[0]][0]!r}, which no track from a switch reaches: no virtual mast can stand "
                              "there")
        bi, ((n, p), seq) = e[0], reach[e]
        band = bands[bi][1]
        letter = "R" if letter_at(band, n, p) == "L" else "L"      # the letter a train heading for the stop reads
        sw = _label(band, n)
        level = plan_bands.band_level(bands[bi][0], levels)
        if level is None:
            raise MapError(f"band {bands[bi][0]!r} has a buffer stop mast but no level")
        _needs_lengths(seq, cm)
        # lettered in the plan order of the track to the buffer stop, by the switch leg it leaves (end_order of its
        # end_leg: Track 209 Spur 1 from 209B before Spur 2 from 209C), as the home masts are
        groups[(int(sw) + 1, letter)].append((end_order(plan_tracks.end_leg(bands, joined, bi, (n, p))), VirtualFields(
            level=level, band=bi, node=n, leg=p, switch=sw,
            bumper=e[1], dir="west" if letter == "L" else "east", facing=seq[-1], seq=seq,
            total=round(sum(cm[b] for b in seq), 1), needed_by=sorted(who, key=mr.natural))))
    out: list[tuple[int, VirtualMast]] = []
    for (number, letter), ms in sorted(groups.items()):
        stem = f"{number}{letter}"
        used = sorted(t.removeprefix(stem) for t in taken if t == stem or re.fullmatch(re.escape(stem) + "[A-Z]", t))
        if "" in used:
            raise MapError(f"Mast {stem} stands already; the virtual mast(s) at its buffer stop(s) cannot be "
                              "lettered")
        ms.sort(key=lambda x: x[0])
        letters = [c for c in "ABCD" if c not in used] if used or len(ms) > 1 else [""]
        if len(ms) > len(letters):
            raise MapError(f"Mast {stem}: {len(used) + len(ms)} masts of one number and letter, more than A to D")
        for (_row, fields), suffix in zip(ms, letters):
            out.append((number, {**fields, "name": stem + suffix}))
    return [m for _n, m in sorted(out, key=lambda x: (x[0], x[1]["name"]))]


def read_retired(path: Path = RETIRED) -> dict[str, str]:
    """{mast: system name} of the virtual masts dropped from any level (retired_virtual_masts.csv), so their ordinals
    stay taken; checked: the columns, one row per mast, each a VirtualSignalMast system name, no ordinal twice
    (hartlib.hand_lists.read_retired_masts, its HandListError a MapError here)."""
    try:
        return hand_lists.read_retired_masts(path)
    except hand_lists.HandListError as exc:
        raise MapError(str(exc)) from exc


def _ordinal(system: str) -> int:
    """The ordinal of a virtual mast's system name; MapError on any other name."""
    k = level_masts.virtual_ordinal(system)
    if k is None:
        raise MapError(f"{system!r} is not a virtual mast system name")
    return k


def virtual_system_names(masts: Sequence[str], level: int, old: Mapping[str, str],
                         retired: Mapping[str, str] | None = None) -> dict[str, str]:
    """{mast: system name} of a level's virtual masts (names without "Mast "): each keeps the name `old` ({"Mast
    <name>": system name}, the device master's) gives it, and a new one takes the next ordinal in its level's thousand
    (hartlib.level_masts.VIRTUAL_BASE) after every one `old` and `retired` (read_retired) use there, so no system name
    shifts and a dropped mast's ordinal is never given again. A mast being dropped may still be in `old` (the rebuild
    takes it out), with the system name `retired` gives it. MapError on a mast in `old` the rule no longer places
    and `retired` does not list, on a mast placed again that `retired` lists (take
    its row out, and its old ordinal back, to restore it), a dropped mast whose retired name is not its old one, an
    old name outside the level's thousand, a name that is not a virtual mast's, or a thousand used up."""
    retired = read_retired() if retired is None else retired
    back = sorted(f"Mast {m}" for m in masts if f"Mast {m}" in retired)
    if back:
        raise MapError(f"{RETIRED.name} lists {', '.join(back)}, which the rule places again; take the row out "
                          "and give the mast its retired ordinal back")
    moved = sorted(m for m in set(old) & set(retired) if old[m] != retired[m])
    if moved:
        raise MapError(f"{RETIRED.name} gives {', '.join(moved)} another system name than the device master")
    gone = sorted((m for m in old if m.removeprefix("Mast ") not in masts and m not in retired), key=mr.natural)
    if gone:
        raise MapError(f"the rule no longer places {', '.join(gone)}: add each to {RETIRED.name} with its system "
                          "name, so its ordinal is never given to another mast")
    low = level_masts.VIRTUAL_BASE[level]
    wrong = sorted(m for m, x in old.items() if level_masts.virtual_level(x) != level)
    if wrong:
        raise MapError(f"virtual mast(s) {', '.join(wrong)} of level {level} have ordinals outside {low + 1} to "
                          f"{low + 999}")
    used = [k for x in [*old.values(), *retired.values()] if low < (k := _ordinal(x)) < low + 1000]
    nxt = max(used, default=low) + 1
    out = {}
    for m in masts:
        system = old.get(f"Mast {m}")
        if system is None:
            if nxt >= low + 1000:
                raise MapError(f"level {level} has no virtual mast ordinal left after {low + 999}")
            system, nxt = f"IF$vsm:basic:one-low(${nxt})", nxt + 1
        out[m] = system
    return out


def home_posts(home: Iterable[mr.HomeMast]) -> dict[tuple[int, str, str], str]:
    """{(band index, switch node, leg): mast name} of home masts (home_masts): where each stands, at its switch's
    points on the leg toward the track it faces. The block layer reads it (block_layer.layer's `posts`): a short piece
    a mast faces from its own switch joins the OS block at its other end, so the block boundary is at the mast."""
    out: dict[tuple[int, str, str], str] = {}
    for m in home:
        key = (m["band"], m["node"], m["leg"])
        if key in out:
            raise MapError(f"Masts {out[key]} and {m['name']} stand at one switch leg")
        out[key] = m["name"]
    return out


def plan(bands: Bands, joined: plan_tracks.Joined, found: list[plan_tracks.Track], *, levels: Mapping[str, int],
         cp_of: Mapping[str, str], layer: Mapping[int, Mapping[str, dict]], cm: Mapping[str, float],
         corner_blocks: dict | None = None, split: frozenset[str] | set[str] = frozenset(),
         home: list[mr.HomeMast] | None = None) -> MastPlan:
    """Every mast of `levels` ({band key: level}) by the one process (module text). `found`: the named tracks
    (plan_tracks.tracks, track_names); `cp_of`: {switch: interlocking} of those levels; `layer`: {band index: {"os":
    {switch node: OS block}, "blocks": {strand: [block]}}}, the level's block layer, for every band of `levels`; `cm`:
    {block: cm}; `corner_blocks`: a double crossover's corner blocks (device_map_schematic.corner_blocks_of); `split`:
    the owner's block splits (block_override_rows.read_block_splits). `home`: home_masts' masts when the caller has them already
    (the block layer reads where they stand: home_posts). MapError when a band of `levels` has no block layer or the
    masts' names are not all different."""
    wanted = {bi for bi, (title, _b, _o) in enumerate(bands) if plan_bands.band_level(title, levels)}
    if wanted - set(layer):
        raise MapError(f"no block layer for band(s) {[bands[bi][0] for bi in sorted(wanted - set(layer))]}")
    runs_by_band = {bi: run_blocks(bands[bi][1], layer[bi]) for bi in sorted(wanted)}
    running = mr.running_tracks(bands, found, cp_of)
    if home is None:
        home = home_masts(bands, joined, found, cp_of, running, levels=levels, corner_blocks=corner_blocks,
                          split=split)
    inter = intermediates(bands, found, runs_by_band, layer, cm, cp_of, running, levels)
    visible = [m["name"] for m in home] + [m["name"] for m in inter]
    virtual = virtual_masts(bands, joined, home, runs_by_band, cm, set(visible), levels)
    names = visible + [m["name"] for m in virtual]
    twice = sorted({n for n in names if names.count(n) > 1}, key=mr.natural)
    if twice:
        raise MapError(f"mast names given twice: {', '.join(twice)}")
    return {"home": home, "intermediates": inter, "virtual": virtual}
