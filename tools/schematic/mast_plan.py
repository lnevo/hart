"""One mast process for every level (owner, 2026-11-20; wiki/projects/level-unification-handoff.md, Masts).

plan() places every mast of the levels it is asked for, the same way on each, from the plan's tracks, the
interlockings (interlockings.csv, the signal rule's control points), the owner's block splits (block_splits.csv) and
the level's block layer:

1. Home masts by mast_rule.masts, with running track and exit dwarfs by rule (mast_rule.running_tracks,
   mast_rule.signalled_spurs, which replaced the hand lists), pruned by reaches_signal over the visible masts only
   (so 126L stays out); two heads when a route can still diverge inside the interlocking (facing_on_route), high
   from running track, a dwarf from a yard, lead or siding.
2. Intermediates (APB pairs): at each block boundary inside a running track (main, running by rule, or a long track
   inside one interlocking) with at least one end in an interlocking, where both blocks hold a train (over
   mast_rule.LONG_CM). Named from the milepost in tenths, odd westbound and even eastbound, after the level's line
   code (LINE_CODE: A main, B upper, none on staging, where a name stops at 98 so it never reads as a three-digit
   home mast). West is toward the lower milepost; on a balloon loop, which starts and ends at one switch, the
   eastbound mast faces Loop 1 (the half from leg B).
3. Virtual masts only as destinations: every route of each kept home mast is walked (mast_rule.route_ends) to the
   first visible mast; a route that reaches a buffer stop first gets a hidden bumper mast there, facing it. Nothing
   else gets one. A bumper mast is named as a home mast is, from the switch the track to the buffer stop leaves (its
   number + 1) and the letter a train heading for the buffer stop reads; masts of one number and letter take A, B ...
   by row on the drawing, after the letters the visible masts use (120RA and 120RB stand, so the bumper mast is
   120RC); a visible mast with the bare name stops the build.

The block layer is each level's own (not yet one process): staging's from its device map's block rows and
block_lengths.csv (build_staging_masts.py), main and upper's generated one block per track, loop and split halves
(build_device_map.track_layer). Each level's builder turns these masts into its rows: build_staging_masts.py into
staging_masts.csv, staging_signals.csv and its device rows; build_device_map.py into the main and upper device rows,
from which build_main_upper_masts.py writes main_upper_masts.csv.
"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

import le_names as ln
import mast_rule as mr
import publish_draft as pd
from hartlib import level_masts

RETIRED = pd.DATA / "retired_virtual_masts.csv"
RETIRED_COLUMNS = ["mast", "system_name", "dropped", "notes"]

LINE_CODE = {1: "", 2: "A", 3: "B"}   # milepost line codes, after Furnace A and B (owner, 2026-11-19); staging has none
CM_PER_SCALE_MILE = 63360 * 2.54 / 87.1
LOOP_FIRST = next(leg for leg, half in mr.LOOP_HALF.items() if half == 1)   # a loop's half 1 leaves from leg B
SWITCHES = ("switch", "dx")


def run_blocks(band, names: dict) -> list[tuple]:
    """[(start (node, port), [block, ...], end (node, port))]: each run of the band (le_names.runs: tracks joined
    through turnbacks, crossover insides left out) with its blocks from `names` in order from its start; a block
    that runs on through a turnback (Brick-Plane) counted once."""
    out = []
    for start, chain, end in ln.runs(band, ln.crossover_strands(band)):
        seq = []
        for sid, rev in chain:
            bl = names["blocks"][sid]
            for b in (bl[::-1] if rev else bl):
                if not seq or seq[-1] != b:
                    seq.append(b)
        out.append((tuple(start), seq, tuple(end)))
    return out


def node_mileposts(band) -> dict:
    """{node: milepost} of every node the band's milepost count reaches (band["mp"]: strand -> (start node, start
    milepost, length in miles, end node))."""
    out = {}
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
        raise mr.MapError(f"MP {mp:.2f} gives intermediate number {number}; names with no line code stop at 98")
    return number


def letter_at(band, node: str, leg: str) -> str:
    """The direction letter of a mast at switch `node`'s `leg` facing into the switch, as mast_rule.masts names it."""
    return "L" if mr.TAU[leg] * band["rail"][node] == 1 else "R"


def leg_row(band, node: str, leg: str) -> int:
    d = band["nodes"][node]
    return band["R"]["srow"].get(d["ins"].get(leg) or d["outs"].get(leg), 0)


def _label(band, node: str) -> str:
    d = band["nodes"][node]
    return mr.base(d.get("label") or "") if d["kind"] in SWITCHES else ""


def _needs_lengths(runs, cm: dict) -> None:
    missing = sorted({b for _s, seq, _e in runs for b in seq} - set(cm))
    if missing:
        raise mr.MapError(f"no length for block(s) {missing}: a mast's place and milepost need every block's length")


def home_masts(bands, joined, found, cp_of: dict, running: set, *, levels, corner_blocks=None,
               split=frozenset()) -> list[dict]:
    """Step 1 (module text): the home masts of `levels`, each with its heads and kind; `running`: the running tracks
    by rule (mast_rule.running_tracks)."""
    spurs = mr.signalled_spurs(found, cp_of)
    home = mr.masts(bands, None, found, cp_of, corner_blocks or {}, levels=levels, running_extra=running,
                    spurs=spurs, split=split, joined=joined)
    for m in home:
        if m["heads"] == 1 and mr.facing_on_route(bands[m["band"]][1], m["node"], m["leg"], cp_of):
            m["heads"] = 2
        m["kind"] = f"{'two' if m['heads'] == 2 else 'one'}-{'searchlight' if m['running'] else 'low'}"
    return home


def intermediates(bands, found, runs_by_band: dict, layer: dict, cm: dict, cp_of: dict, running: set,
                  levels) -> list[dict]:
    """Step 2 (module text). Each: name (with its line code, no "Mast "), level, band, dir, facing, protects,
    milepost, the run's `start` and `end` (node, port), `to` (the end the mast heads for), toward and other (their
    switch numbers), dist (cm from `to` to the boundary), total (the run's cm) and cp (the interlocking of `toward`,
    else of `other`)."""
    legs = mr.by_leg(found)
    out = []
    for bi, runs in sorted(runs_by_band.items()):
        band = bands[bi][1]
        level = mr.band_level(bands[bi][0], levels)
        code = LINE_CODE[level]
        nodes, os_ = band["nodes"], layer[bi]["os"]
        mp_at = node_mileposts(band)
        for start, seq, end in runs:
            if any(nodes[e[0]]["kind"] not in SWITCHES for e in (start, end)):
                continue
            sw = [_label(band, start[0]), _label(band, end[0])]
            if not any(s in cp_of for s in sw):
                continue
            t = legs.get((bi, start[0], start[1]))
            if t is None:
                continue                        # a crossover's inside: its OS block, no boundary
            inside = cp_of.get(sw[0]) is not None and cp_of.get(sw[0]) == cp_of.get(sw[1])
            if not (t["main"] or t["name"] in running or inside):
                continue
            if start[0] == end[0] and start[1] != LOOP_FIRST:      # a balloon loop is read from its half 1
                start, seq, end, sw = end, seq[::-1], start, sw[::-1]
            body = [b for b in seq if b not in (os_.get(start[0]), os_.get(end[0]))]
            _needs_lengths([(start, seq, end)], cm)
            total = sum(cm[x] for x in seq)
            for i in range(len(body) - 1):
                a, b = body[i], body[i + 1]
                if cm[a] <= mr.LONG_CM or cm[b] <= mr.LONG_CM:
                    continue
                if start[0] not in mp_at or end[0] not in mp_at:
                    raise mr.MapError(f"the boundary {a}|{b} cannot be numbered: switch "
                                      f"{sw[0] if start[0] not in mp_at else sw[1]} is not on the milepost count")
                from_start = sum(cm[x] for x in seq[:seq.index(b)])
                low_is_start = mp_at[start[0]] <= mp_at[end[0]]
                mp = (mp_at[start[0]] + from_start / CM_PER_SCALE_MILE if low_is_start
                      else mp_at[end[0]] + (total - from_start) / CM_PER_SCALE_MILE)
                west_to, east_to = (start, end) if low_is_start else (end, start)
                for west, to in ((True, west_to), (False, east_to)):
                    at_start = to is start
                    toward, other = (sw[0], sw[1]) if at_start else (sw[1], sw[0])
                    cp = cp_of.get(toward) or cp_of[other]
                    out.append(dict(name=f"{code}{signal_number(mp, west, code)}", level=level, band=bi,
                                    dir="west" if west else "east",
                                    protects=a if at_start else b, facing=b if at_start else a,
                                    milepost=round(mp, 3), start=start, end=end, to=to, toward=toward, other=other,
                                    dist=round(from_start if at_start else total - from_start, 1),
                                    total=round(total, 1), cp=cp))
    return out


def virtual_masts(bands, joined, home: list[dict], runs_by_band: dict, cm: dict, taken: set, levels) -> list[dict]:
    """Step 3 (module text). Each: name (no "Mast "), level, band, node and leg (the switch leg the track to the
    buffer stop leaves), switch (its number), bumper (the buffer stop's node), dir, facing (the block next to the
    buffer stop), seq (the blocks from the switch to the buffer stop), total (their cm) and needed_by (the visible
    masts whose routes end there). `taken`: the visible masts' names. MapError on a buffer stop no track from a
    switch reaches, a name a visible mast has bare, or more than four masts of one number and letter."""
    posts = defaultdict(set)
    for m in home:
        posts[m["band"]].add((m["node"], m["leg"]))
    need = defaultdict(set)
    for m in home:
        _signal, bumpers = mr.route_ends(bands, m["band"], m["node"], m["leg"], posts, joined)
        for e in bumpers:
            need[e].add(m["name"])
    reach = {}
    for bi, runs in runs_by_band.items():
        nodes = bands[bi][1]["nodes"]
        for start, seq, end in runs:
            for here, there, s in ((start, end, seq), (end, start, seq[::-1])):
                if nodes[there[0]].get("sub") == "bumper" and nodes[here[0]]["kind"] in SWITCHES:
                    reach[(bi, there[0])] = (here, s)
    groups = defaultdict(list)
    for e, who in sorted(need.items()):
        if e not in reach:
            raise mr.MapError(f"the routes of {', '.join(sorted(who, key=mr.natural))} end at buffer stop {e[1]} on "
                              f"{bands[e[0]][0]!r}, which no track from a switch reaches: no virtual mast can stand "
                              "there")
        bi, (n, p), seq = e[0], *reach[e]
        band = bands[bi][1]
        letter = "R" if letter_at(band, n, p) == "L" else "L"      # the letter a train heading for the stop reads
        sw = _label(band, n)
        _needs_lengths([((n, p), seq, None)], cm)
        groups[(int(sw) + 1, letter)].append((leg_row(band, n, p), dict(
            level=mr.band_level(bands[bi][0], levels), band=bi, node=n, leg=p, switch=sw,
            bumper=e[1], dir="west" if letter == "L" else "east", facing=seq[-1], seq=seq,
            total=round(sum(cm[b] for b in seq), 1), needed_by=sorted(who, key=mr.natural))))
    out = []
    for (number, letter), ms in sorted(groups.items()):
        stem = f"{number}{letter}"
        used = sorted(t.removeprefix(stem) for t in taken if t == stem or re.fullmatch(re.escape(stem) + "[A-Z]", t))
        if "" in used:
            raise mr.MapError(f"Mast {stem} stands already; the virtual mast(s) at its buffer stop(s) cannot be "
                              "lettered")
        ms.sort(key=lambda x: x[0])
        letters = [c for c in "ABCD" if c not in used] if used or len(ms) > 1 else [""]
        if len(ms) > len(letters):
            raise mr.MapError(f"Mast {stem}: {len(used) + len(ms)} masts of one number and letter, more than A to D")
        for (_row, fields), suffix in zip(ms, letters):
            out.append(dict(fields, name=stem + suffix))
    return sorted(out, key=lambda m: (int(re.match(r"\d+", m["name"]).group()), m["name"]))


def read_retired(path: Path = RETIRED) -> dict:
    """{mast: system name} of the virtual masts dropped from any level (retired_virtual_masts.csv), so their ordinals
    stay taken; checked: the columns, one row per mast, each a VirtualSignalMast system name, no ordinal twice."""
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
    except OSError as exc:
        raise mr.MapError(f"cannot read {path.name}: {exc}") from None
    if reader.fieldnames != RETIRED_COLUMNS:
        raise mr.MapError(f"{path.name}: columns {reader.fieldnames}, not {RETIRED_COLUMNS}")
    out, seen = {}, set()
    for n, r in enumerate(rows, 2):
        m, sysname = (r["mast"] or "").strip(), (r["system_name"] or "").strip()
        k = level_masts.virtual_ordinal(sysname)
        if not m or m in out or k is None or k in seen:
            raise mr.MapError(f"{path.name} line {n}: {m!r} {sysname!r} is empty, listed twice, not a virtual mast's "
                              "system name, or reuses an ordinal")
        out[m] = sysname
        seen.add(k)
    return out


def virtual_system_names(masts: list[str], level: int, old: dict, retired: dict | None = None) -> dict:
    """{mast: system name} of a level's virtual masts (names without "Mast "): each keeps the name `old` ({"Mast
    <name>": system name}, the device master's) gives it, and a new one takes the next ordinal in its level's thousand
    (hartlib.level_masts.VIRTUAL_BASE) after every one `old` and `retired` (read_retired) use there, so no system name
    shifts and a dropped mast's ordinal is never given again. A mast being dropped may still be in `old` (the rebuild
    takes it out), with the system name `retired` gives it. MapError on a mast in `old` the rule no longer places
    and `retired` does not list, on a mast placed again that `retired` lists (take
    its row out, and its old ordinal back, to restore it), a dropped mast whose retired name is not its old one, an
    old name outside the level's thousand, or a thousand used up."""
    retired = read_retired() if retired is None else retired
    back = sorted(f"Mast {m}" for m in masts if f"Mast {m}" in retired)
    if back:
        raise mr.MapError(f"{RETIRED.name} lists {', '.join(back)}, which the rule places again; take the row out "
                          "and give the mast its retired ordinal back")
    moved = sorted(m for m in set(old) & set(retired) if old[m] != retired[m])
    if moved:
        raise mr.MapError(f"{RETIRED.name} gives {', '.join(moved)} another system name than the device master")
    gone = sorted((m for m in old if m.removeprefix("Mast ") not in masts and m not in retired), key=mr.natural)
    if gone:
        raise mr.MapError(f"the rule no longer places {', '.join(gone)}: add each to {RETIRED.name} with its system "
                          "name, so its ordinal is never given to another mast")
    low = level_masts.VIRTUAL_BASE[level]
    wrong = sorted(m for m, x in old.items() if level_masts.virtual_level(x) != level)
    if wrong:
        raise mr.MapError(f"virtual mast(s) {', '.join(wrong)} of level {level} have ordinals outside {low + 1} to "
                          f"{low + 999}")
    used = [k for x in [*old.values(), *retired.values()] if low < (k := level_masts.virtual_ordinal(x)) < low + 1000]
    nxt = max(used, default=low) + 1
    out = {}
    for m in masts:
        system = old.get(f"Mast {m}")
        if system is None:
            if nxt >= low + 1000:
                raise mr.MapError(f"level {level} has no virtual mast ordinal left after {low + 999}")
            system, nxt = f"IF$vsm:basic:one-low(${nxt})", nxt + 1
        out[m] = system
    return out


def home_posts(home: list[dict]) -> dict:
    """{(band index, switch node, leg): mast name} of home masts (home_masts): where each stands, at its switch's
    points on the leg toward the track it faces. The block layer reads it (block_layer.layer's `posts`): a short piece
    a mast faces from its own switch joins the OS block at its other end, so the block boundary is at the mast."""
    out = {}
    for m in home:
        key = (m["band"], m["node"], m["leg"])
        if key in out:
            raise mr.MapError(f"Masts {out[key]} and {m['name']} stand at one switch leg")
        out[key] = m["name"]
    return out


def plan(bands, joined, found, *, levels: dict, cp_of: dict, layer: dict, cm: dict, corner_blocks=None,
         split=frozenset(), home: list | None = None) -> dict:
    """Every mast of `levels` ({band key: level}) by the one process (module text): {"home": [...], "intermediates":
    [...], "virtual": [...]}. `found`: the named tracks (mast_rule.tracks, track_names); `cp_of`: {switch:
    interlocking} of those levels; `layer`: {band index: {"os": {switch node: OS block}, "blocks": {strand: [block]}}},
    the level's block layer, for every band of `levels`; `cm`: {block: cm}; `corner_blocks`: a double crossover's
    corner blocks (build_device_map.xover_corners); `split`: the owner's block splits (mast_rule.read_block_splits).
    `home`: home_masts' masts when the caller has them already (the block layer reads where they stand: home_posts).
    MapError when a band of `levels` has no block layer or the masts' names are not all different."""
    wanted = {bi for bi, (title, _b, _o) in enumerate(bands) if mr.band_level(title, levels)}
    if wanted - set(layer):
        raise mr.MapError(f"no block layer for band(s) {[bands[bi][0] for bi in sorted(wanted - set(layer))]}")
    runs_by_band = {bi: run_blocks(bands[bi][1], layer[bi]) for bi in sorted(wanted)}
    running = mr.running_tracks(bands, found, cp_of)
    if home is None:
        home = home_masts(bands, joined, found, cp_of, running, levels=levels, corner_blocks=corner_blocks,
                          split=split)
    inter = intermediates(bands, found, runs_by_band, layer, cm, cp_of, running, levels)
    visible = [m["name"] for m in home + inter]
    virtual = virtual_masts(bands, joined, home, runs_by_band, cm, set(visible), levels)
    names = visible + [m["name"] for m in virtual]
    twice = sorted({n for n in names if names.count(n) > 1}, key=mr.natural)
    if twice:
        raise mr.MapError(f"mast names given twice: {', '.join(twice)}")
    return {"home": home, "intermediates": inter, "virtual": virtual}
