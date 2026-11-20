"""The track and mast rule of the schematic levels, out of build_device_map.py so every level can use it.

tracks() lists each track of a band between its ends (switch, helix or bumper), track_names() names them ("Track
<a>-<b>", "Track <n> Spur", "Track <n> Loop", " 1"/" 2" for parallel tracks), and masts() places a home signal where a
track from outside a control point meets one of its switches, unless no route it governs reaches another signal
(reaches_signal; build_device_map.py's module text has the naming and head rules). band_level() maps a band title
to its level by the `level` of its entry in a plan-overrides file (band_levels). The rules that replaced hand lists
(owner, 2026-11-20): running_tracks (passing sidings between interlockings), signalled_spurs (exit dwarfs off a main track); read_block_splits reads the owner's block
splits, which are a choice, not a rule. mast_plan.py runs them all as the one mast process of every level.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from hartlib import railroad

base = railroad.switch_number
natural = railroad.natural

TAU = {"A": -1, "B": 1, "C": 1, "D": -1}      # the plugin's leg sides (schematic.core.TAU)
LOOP_HALF = {"B": 1, "C": 2}          # a balloon loop's half by the switch leg it leaves from (owner, 2026-11-16)
LONG_CM = 150.0                       # a track inside a control point longer than this can hold a train (owner, 2026-11-19)


class MapError(RuntimeError):
    pass


def band_levels(overrides: dict) -> dict[str, int]:
    """{band title: level} of one plan-overrides file: each `levels.bands` entry's name with its `level` (main and
    upper: 2 and 3), or, for a one-band input, `level_title` with the file's own `level` (staging: 1). The titles stay
    the drawn text; the level is the owner's number, not the title's first word. MapError for a band with no level, a
    level that is not 1, 2 or 3, a title two bands share, or a file that names no band."""
    entries = [(b.get("name"), b.get("level"), f"levels.bands entry {b.get('name')!r}")
               for b in overrides.get("levels", {}).get("bands", ())]
    if not entries and overrides.get("level_title"):
        entries = [(overrides["level_title"], overrides.get("level"), "level_title")]
    if not entries:
        raise MapError("the plan overrides name no band (levels.bands, or level_title)")
    out = {}
    for name, level, what in entries:
        if not name:
            raise MapError(f"{what}: no name")
        if level not in (1, 2, 3) or isinstance(level, bool):
            raise MapError(f"{what} has level {level!r}, which is not 1, 2 or 3")
        if name in out:
            raise MapError(f"two bands are titled {name!r}")
        out[name] = level
    return out


def band_level(title: str, levels: dict) -> int | None:
    """The level of a band by its title, in `levels` (band_levels); None for a band `levels` does not hold."""
    return levels.get(title) if title else None


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
    if d.get("sub") == "link" and (bi, node_id) in joined:
        bj, m = joined[(bi, node_id)]
        other = bands[bj][1]
        sid = next(iter(list(other["nodes"][m]["ins"].values()) + list(other["nodes"][m]["outs"].values())))
        s = other["strands"][sid]
        far = s["dst"][0] if s["src"][0] == m else s["src"][0]
        return end_ref(bands, joined, bj, far, helix_tag, levels)
    return ("bumper", None)


def end_label(bands, joined, bi, node_id) -> str:
    """The switch label a track ends at, followed through a connector to the other band ("" at a bumper or
    helix): the halves of the helix-top crossovers 127 and 131 sit on two bands, joined by connectors."""
    d = bands[bi][1]["nodes"][node_id]
    if d["kind"] in ("switch", "dx"):
        return d.get("label") or ""
    if d.get("sub") == "link" and (bi, node_id) in joined:
        bj, m = joined[(bi, node_id)]
        other = bands[bj][1]
        sid = next(iter(list(other["nodes"][m]["ins"].values()) + list(other["nodes"][m]["outs"].values())))
        s = other["strands"][sid]
        return end_label(bands, joined, bj, s["dst"][0] if s["src"][0] == m else s["src"][0])
    return ""


def helix_tags(bands, overrides) -> dict[int, str]:
    """{level: "H1"|"H2"}: the helix tracks in the overrides' order, each on the band holding its switch."""
    relabel = next(e["map"] for e in overrides["edits"] if e["op"] == "relabel")
    levels, out = band_levels(overrides), {}
    for i, sw in enumerate(overrides.get("helix", {})):
        label = relabel.get(sw, sw)
        for title, band, _ in bands:
            if any(d.get("label", "").rstrip("*") == label for d in band["nodes"].values()):
                out[band_level(title, levels)] = f"H{i + 1}"
    return out


HELIX_TRACKS = railroad.Sources.under().helix_tracks


def read_helix_tracks(path: Path | None = None) -> dict[str, dict]:
    """{plan helix track name: {block, staging_switch, level_switch}} from helix_tracks.csv (hartlib.railroad
    .read_helix_tracks, which checks it): each helix track is one JMRI block from its staging switch to its main or
    upper switch (owner, 2026-11-20). Its FactsError as a MapError."""
    try:
        got = railroad.read_helix_tracks(path or HELIX_TRACKS)
    except railroad.FactsError as exc:
        raise MapError(str(exc)) from None
    return {h.helix: {"block": h.block, "staging_switch": h.staging_switch, "level_switch": h.level_switch}
            for h in got.values()}


def helix_blocks(overrides, helix=None) -> dict[str, str]:
    """{helix tag ("H1", "H2", as helix_tags gives them): block} for the main and upper levels: the overrides' helix
    tracks in order, each named in helix_tracks.csv. Stops on a helix track the file does not name, or one it names
    that the overrides do not have."""
    helix = read_helix_tracks() if helix is None else helix
    plan = list(overrides.get("helix", {}).values())
    if sorted(plan) != sorted(helix):
        raise MapError(f"{HELIX_TRACKS.name} names helix tracks {sorted(helix)}, the plan overrides {sorted(plan)}")
    return {f"H{i + 1}": helix[name]["block"] for i, name in enumerate(plan)}


def tracks(bands, runs, joined, helix_tag, levels) -> list[dict]:
    """One entry per track of the main and upper bands (a track cut by a connector counted once)."""
    found, seen = [], set()
    for bi, (title, band, _) in enumerate(bands):
        lv = band_level(title, levels)
        if not lv:
            continue
        nodes, strands, srow = band["nodes"], band["strands"], band["R"]["srow"]
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
            found.append(dict(level=lv, ends=(a, b), legs=ends, band=bi, cm=round(sum(edges.values()), 1),
                              loop=start[0] == end[0] and a[0] == "sw",
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
                               f"{HELIX_TRACKS.name} names no block for")
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
        ts.sort(key=lambda t: (t["row"], t["trial"]))
        for i, t in enumerate(ts, 1):
            t["name"] = stem if len(ts) == 1 else f"{stem} {i}"


# ---------------------------------------------------------------- hand lists keyed by end switches

TRACK_KEY_COLUMNS = ["switch_a", "switch_b", "parallel"]
SWITCH_NUMBER = re.compile(r"\d+")


def track_key(t: dict) -> tuple[str, str] | None:
    """The end switches of a track entry, lower number first: (a, b) between two switches, (n, n) for a balloon loop
    and (n, "") for a spur (one switch, a bumper at the other end). None for a track up the helix, which its helix
    block names (helix_tracks.csv). Hand lists name a track by this key, so a renumbered switch moves the row with
    it, where a generated name ("Track 119-121") would have to be retyped."""
    if any(k == "helix" for k, _v in t["ends"]):
        return None
    sw = sorted((v for k, v in t["ends"] if k == "sw"), key=natural)
    return (sw[0], sw[1] if len(sw) == 2 else "") if sw else None


def key_problem(row: dict) -> str:
    """Why a row's switch_a, switch_b and parallel are not a track key ("" when they are)."""
    a, b, par = row["switch_a"], row["switch_b"], row["parallel"]
    if not SWITCH_NUMBER.fullmatch(a) or (b and not SWITCH_NUMBER.fullmatch(b)):
        return f"switch_a {a!r} and switch_b {b!r} are switch numbers (switch_b blank for a spur)"
    if b and natural(a) > natural(b):
        return f"switch_a {a} and switch_b {b} are in number order, lower first"
    if par and par not in ("1", "2", "3", "4"):
        return f"parallel {par!r} is blank or the track's place from the top, 1 to 4"
    return ""


def read_track_rows(path: Path, columns: list[str]) -> list[dict]:
    """The rows of a hand list keyed by end switches (`columns` holds TRACK_KEY_COLUMNS), each with its `line`.
    switch_a and switch_b are switch numbers, lower first; switch_b is blank for a spur (a bumper at the other end);
    `parallel` (1, 2, from the top row, as the generated names count) is needed only where two tracks run between
    the same switches. Stops on columns not in that shape or a malformed row, naming the line."""
    import csv
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
    except OSError as exc:
        raise MapError(f"cannot read {path.name}: {exc}") from None
    if reader.fieldnames != columns:
        raise MapError(f"{path.name}: columns {reader.fieldnames}, not {columns}")
    out, bad = [], []
    for i, r in enumerate(rows, 2):
        r = {k: (v or "").strip() for k, v in r.items()}
        r["line"] = i
        problem = key_problem(r)
        if problem:
            bad.append(f"line {i}: {problem}")
        else:
            out.append(r)
    if bad:
        raise MapError(f"{path.name}: " + "; ".join(bad))
    return out


def resolve_track(row: dict, found: list[dict]) -> dict | None:
    """The one track entry of `found` the row's switches (and `parallel`) name, or None with the reason in
    row["problem"]: no track, or several with no `parallel` to choose (the candidates named, in top-row order)."""
    key = (row["switch_a"], row["switch_b"])
    same = sorted((t for t in found if track_key(t) == key), key=lambda t: (t["row"], t["trial"]))
    label = f"Switch {key[0]}" + (f" to Switch {key[1]}" if key[1] else " spur")
    if not same:
        near = sorted({t["name"] for t in found if track_key(t) and set(key[:1 + bool(key[1])]) & set(track_key(t))})
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
                          "give parallel, 1 from the top row")
        return None
    return same[0]


# ---------------------------------------------------------------- rules that replace hand lists (owner, 2026-11-20)

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
    """The names of the tracks that count as running track besides the main route (owner, 2026-11-20; it replaced
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
    """The names of the spurs that get an exit dwarf (owner, 2026-11-20; it replaced the hand list
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


SPLIT_COLUMNS = ["level"] + TRACK_KEY_COLUMNS + ["notes"]


def read_block_splits(path: Path, found: list[dict], levels) -> set[str]:
    """The names of the tracks block_splits.csv parts into two blocks at their turnback, among `found` and the
    `levels` ({band key: level}) asked for. Each row is the OWNER'S CHOICE, not a rule (owner, 2026-11-20: a rule would
    catch every intermediate loop): `level` and the track's end switches (read_track_rows' key), resolved at build
    time. Stops on a file not in that shape, a level that is not 1 to 3, a row naming no track or a track on another
    level, or a track two rows name. A row of a level not asked for is checked for shape only."""
    wanted = set(levels.values())
    rows = read_track_rows(path, SPLIT_COLUMNS)
    bad = [f"line {r['line']}: level {r['level']!r} is 1, 2 or 3" for r in rows if r["level"] not in ("1", "2", "3")]
    out, seen = set(), {}
    for r in rows:
        if bad or int(r["level"]) not in wanted:
            continue
        t = resolve_track(r, [t for t in found if t["level"] == int(r["level"])])
        if t is None:
            bad.append(f"line {r['line']}: level {r['level']}: {r['problem']}")
        elif t["name"] in seen:
            bad.append(f"line {r['line']}: {t['name']} is already named on line {seen[t['name']]}")
        else:
            seen[t["name"]] = r["line"]
            out.add(t["name"])
    if bad:
        raise MapError(f"{path.name}: " + "; ".join(bad))
    return out


def masts(bands, cps, found, cp_of, corner_blocks=None, running_extra=frozenset(),
          spurs=frozenset(), split=frozenset(), *, joined, levels) -> list[dict]:
    """Home masts where a track from outside a control point meets one of its switches, or where a track inside one
    is long enough to hold a train (over LONG_CM: running track inside an interlocking, staging's K-1/K-2), or where a
    track ending at a bumper that can hold a train leaves one (staging's W-1 and W-2). `running_extra`: track names
    that count as running track besides the main route (passing sidings); `spurs`: spur names that get an exit dwarf
    at their switch even when it is in no control point (cp "" then; owner, 2026-11-19). Each mast
    gives its switch `node` and `leg`, and `kind`, its JMRI basic appearance: two-searchlight facing the points (two
    heads), one-searchlight on a trailing leg of running track (the main route, or a long track inside an
    interlocking), one-low (a dwarf) on a trailing leg off it (owner,
    2026-11-19: the stock basic system shows Diverging aspects only on two heads). A mast none of whose routes
    reaches another signal is left out (reaches_signal; `joined`, the plugin's partners, says which connector ends
    run on to another band). `levels`: {band title: level} (band_levels)."""
    by_leg = {}
    for t in found:
        for (n, p), far in zip(t["legs"], reversed(t["ends"])):
            by_leg[(t["band"], n, p)] = (t, far)
    out = []
    for bi, (title, band, _) in enumerate(bands):
        lv = band_level(title, levels)
        if not lv:
            continue
        rail, srow = band["rail"], band["R"]["srow"]
        for n, d in band["nodes"].items():
            if d["kind"] not in ("switch", "dx") or n not in rail:
                continue
            num = base(d["label"])
            cp = cp_of.get(num)
            for p in sorted(set(d["ins"]) | set(d["outs"])):
                hit = by_leg.get((bi, n, p))
                if hit is None:
                    continue
                t, (kind, far) = hit
                if cp is None or t["name"] in spurs:
                    if t["name"] not in spurs:
                        continue
                    sid = d["ins"].get(p) or d["outs"].get(p)
                    out.append(dict(level=lv, cp=cp or "", switch=num, number=int(num) + 1,
                                    letter="L" if TAU[p] * rail[n] == 1 else "R",
                                    dir="west" if TAU[p] * rail[n] == 1 else "east", protects="", heads=1,
                                    row=srow.get(sid, 0), track=t["name"], band=bi, half=0, node=n, leg=p,
                                    strand=sid, running=False, kind="one-low"))
                    continue
                loop = kind == "sw" and far == num and t["loop"]   # comes back to this switch
                inside = kind == "sw" and cp_of.get(far) == cp and not loop
                # a track ending at a bumper gets a mast only when it can hold a train (a staging track trains leave
                # from, W-1 and W-2; owner, 2026-11-19), and then a dwarf, unless it is main route
                if (kind == "bumper" and t["cm"] <= LONG_CM) or (inside and t["cm"] <= LONG_CM):
                    continue
                running = t["main"] or inside or t["name"] in running_extra   # long inside track, passing siding
                if t["loop"] and p not in LOOP_HALF:
                    raise MapError(f"Switch {num}: balloon loop {t['name']} leaves from leg {p}; a loop's halves "
                                   f"leave from legs {' and '.join(LOOP_HALF)}")
                eastward = TAU[p] * rail[n] == 1
                sid = d["ins"].get(p) or d["outs"].get(p)
                heads = 2 if (p == "A" or d["kind"] == "dx") else 1
                # a split track's half at this end: half 1 at its lower-numbered switch (build_device_map.loop_halves)
                ends = sorted((v for k, v in t["ends"] if k == "sw"), key=natural)
                split_half = (1 if num == ends[0] else 2) if t["name"] in split else 0
                out.append(dict(level=lv, cp=cp, switch=num, number=int(num) + 1, letter="L" if eastward else "R",
                                dir="west" if eastward else "east",
                                protects=corner_blocks[num][p] if d["kind"] == "dx" else "",
                                heads=heads, row=srow.get(sid, 0),
                                track=(f"{t['name']} {LOOP_HALF[p]}" if t["loop"] else
                                       f"{t['name']} {split_half}" if split_half else t["name"]), band=bi,
                                half=LOOP_HALF[p] if t["loop"] else 0, node=n, leg=p, strand=sid, running=running,
                                kind=("two-searchlight" if heads == 2 else
                                      "one-searchlight" if running else "one-low")))
    # a home mast governs something only when a route it would clear reaches another signal (owner, 2026-11-19: no
    # hand-made exceptions); one whose every route ends at a bumper or in dark track is left out, and again until none
    # is: a mast kept only by a mast the rule leaves out reaches no signal either
    while True:
        posts = defaultdict(set)
        for m in out:
            posts[m["band"]].add((m["node"], m["leg"]))
        kept = [m for m in out if reaches_signal(bands, m["band"], m["node"], m["leg"], posts, joined)]
        if len(kept) == len(out):
            break
        out = kept
    groups = defaultdict(list)
    for m in out:
        groups[(m["number"], m["letter"])].append(m)
    for (num, letter), ms in groups.items():
        if len(ms) > 2:
            raise MapError(f"switch {num - 1}: {len(ms)} masts for direction {letter}; ADR-005 names two (A and B)")
        # a balloon loop's A mast faces Loop 1 (leg B, the normal leg) and its B mast Loop 2 (owner, 2026-11-16)
        ms.sort(key=lambda m: (m["band"], m["half"], m["row"]))
        for i, m in enumerate(ms):
            m["name"] = f"{num}{letter}" + ("AB"[i] if len(ms) == 2 else "")
    return out


# where a train leaves a switch by, entering it at a leg: a plain switch's points (A) choose B or C and B or C trail to
# A; a double crossover joins A to B and C, D to C and B (its through tracks A-B and D-C, both diagonals)
EXITS = {"switch": {"A": ("B", "C"), "B": ("A",), "C": ("A",)},
         "dx": {"A": ("B", "C"), "B": ("A", "D"), "C": ("D", "A"), "D": ("C", "B")}}


def reaches_signal(bands, bi: int, node: str, leg: str, posts: dict, joined: dict) -> bool:
    """True when some route of a train entering switch `node` of band `bi` at `leg` reaches another signal: a switch
    leg in `posts` ({band index: {(node, leg)}} of the masts) that it enters by, other than the one it starts at, or
    an end where the track runs on: a helix end (its signals are the other level's) or an open end (track running on
    off the drawing), so the rule never leaves out a mast whose route runs on beyond what is drawn. A connector end is
    followed to the other band when `joined` (the plugin's partners, {(band, node): (band, node)}) joins it, as
    end_ref does, and is a bumper when it does not. Every route is walked through switches and turnbacks to the next
    mast or the end of track; a route ending at a bumper, or in track with no mast facing on (a dark spur or yard),
    reaches none. A route that comes back to a leg already walked, its own start among them, adds nothing."""
    return route_ends(bands, bi, node, leg, posts, joined)[0]


def route_ends(bands, bi: int, node: str, leg: str, posts: dict, joined: dict) -> tuple[bool, set]:
    """(reaches a signal, {(band, buffer stop node)} reached before any mast) over every route of a train entering
    switch `node` of band `bi` at `leg`, walked as reaches_signal says (the whole walk: a route that reaches a signal
    stops there, the others run on). The buffer stops are where a mast in `posts` needs a destination
    (mast_plan.virtual_masts, owner 2026-11-20)."""
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
    todo, seen, signal, bumpers = [start], {start}, False, set()
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
    Used to give a home mast two heads when a route it governs can still diverge (owner, 2026-11-19)."""
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
