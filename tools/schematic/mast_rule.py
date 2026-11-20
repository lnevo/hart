"""The track and mast rule of the schematic levels, out of build_device_map.py so every level can use it.

tracks() lists each track of a band between its ends (switch, helix or bumper), track_names() names them ("Track
<a>-<b>", "Track <n> Spur", "Track <n> Loop", " 1"/" 2" for parallel tracks), and masts() places a home signal where a
track from outside a control point meets one of its switches, unless no route it governs reaches another signal
(reaches_signal; build_device_map.py's module text has the naming and head rules). band_level() maps a band title
to its level by LEVELS.
"""
from __future__ import annotations

import re
from collections import defaultdict

from hartlib import railroad

base = railroad.switch_number
natural = railroad.natural

LEVELS = {"Main": 2, "Upper": 3}      # band key (first word of the band title) -> level
TAU = {"A": -1, "B": 1, "C": 1, "D": -1}      # the plugin's leg sides (schematic.core.TAU)
LOOP_HALF = {"B": 1, "C": 2}          # a balloon loop's half by the switch leg it leaves from (owner, 2026-11-16)
LONG_CM = 150.0                       # a track inside a control point longer than this can hold a train (owner, 2026-11-19)


class MapError(RuntimeError):
    pass


def band_level(title: str, levels: dict | None = None) -> int | None:
    """The level of a band by the first word of its title, in `levels` (default LEVELS: main and upper)."""
    return (LEVELS if levels is None else levels).get((title or "").split()[0]) if title else None


def end_ref(bands, joined, bi, node_id, helix_tag, levels=None):
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
    helix): the halves of the helix-top crossovers 129 and 135 sit on two bands, joined by connectors."""
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
    out = {}
    for i, sw in enumerate(overrides.get("helix", {})):
        label = relabel.get(sw, sw)
        for title, band, _ in bands:
            if any(d.get("label", "").rstrip("*") == label for d in band["nodes"].values()):
                out[band_level(title)] = f"H{i + 1}"
    return out


def tracks(bands, runs, joined, helix_tag, levels=None) -> list[dict]:
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
            la, lb = end_label(bands, joined, bi, start[0]), end_label(bands, joined, bi, end[0])
            halves = la[-1:] in ("A", "B") and lb[-1:] in ("A", "B")
            # between a crossover's halves, its OS block: halves lettered A/B (main, upper), or two nodes with one
            # number (staging's single crossovers 7, 23 and 35); a balloon loop starts and ends on the same node
            if a[0] == b[0] == "sw" and a[1] == b[1] and ((la != lb and halves) or start[0] != end[0]):
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


def track_names(found) -> None:
    """Fill `name` in each track entry (see the module text)."""
    groups = defaultdict(list)
    for t in found:
        (ka, va), (kb, vb) = t["ends"]
        sw = sorted([v for k, v in t["ends"] if k == "sw"], key=natural)
        hx = [v for k, v in t["ends"] if k == "helix"]
        if not sw:
            raise MapError(f"a track ({', '.join(t['trial'])}) has no switch at either end, so it has no name")
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


def masts(bands, cps, found, cp_of, corner_blocks=None, levels=None, running_extra=frozenset(),
          spurs=frozenset(), split=frozenset(), *, joined) -> list[dict]:
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
    run on to another band)."""
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
                                    letter="L" if TAU[p] * rail[n] == 1 else "R", protects="", heads=1,
                                    row=srow.get(sid, 0), track=t["name"], band=bi, half=0, node=n, leg=p,
                                    strand=sid, running=False, kind="one-low"))
                    continue
                loop = kind == "sw" and far == num and t["name"].endswith(" Loop")   # comes back to this switch
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
    todo, seen = [start], {start}
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
                    return True                             # runs on: another level, or off the drawing
                continue                                    # a bumper or an unjoined connector: this route ends dark
            if here != start and (m, q) in posts.get(fb, ()):
                return True
            if here not in seen:
                seen.add(here)
                todo.append(here)
    return False


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
