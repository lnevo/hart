"""The track and mast rule of the schematic levels, out of build_device_map.py so every level can use it.

tracks() lists each track of a band between its ends (switch, helix or bumper), track_names() names them ("Track
<a>-<b>", "Track <n> Spur", "Track <n> Loop", " 1"/" 2" for parallel tracks), and masts() places a home signal where a
track from outside a control point meets one of its switches (build_device_map.py's module text has the naming and
head rules). band_level() maps a band title to its level by LEVELS.
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


class MapError(RuntimeError):
    pass


def band_level(title: str) -> int | None:
    return LEVELS.get((title or "").split()[0]) if title else None


def end_ref(bands, joined, bi, node_id, helix_tag):
    """What a track ends at: ("sw", number), ("helix", "H1"), ("bumper", None). A connector to the other band
    is followed to the switch beyond it."""
    band = bands[bi][1]
    d = band["nodes"][node_id]
    if d["kind"] in ("switch", "dx"):
        return ("sw", base(d["label"]))
    if d.get("sub") == "helix":
        level = band_level(bands[bi][0])
        if level not in helix_tag:
            raise MapError(f"a track reaches the helix end on band {bands[bi][0]!r}, which is not main or upper")
        return ("helix", helix_tag[level])
    if d.get("sub") == "link" and (bi, node_id) in joined:
        bj, m = joined[(bi, node_id)]
        other = bands[bj][1]
        sid = next(iter(list(other["nodes"][m]["ins"].values()) + list(other["nodes"][m]["outs"].values())))
        s = other["strands"][sid]
        far = s["dst"][0] if s["src"][0] == m else s["src"][0]
        return end_ref(bands, joined, bj, far, helix_tag)
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


def tracks(bands, runs, joined, helix_tag) -> list[dict]:
    """One entry per track of the main and upper bands (a track cut by a connector counted once)."""
    found, seen = [], set()
    for bi, (title, band, _) in enumerate(bands):
        lv = band_level(title)
        if not lv:
            continue
        nodes, strands, srow = band["nodes"], band["strands"], band["R"]["srow"]
        for start, chain, end in runs(band):
            a = end_ref(bands, joined, bi, start[0], helix_tag)
            b = end_ref(bands, joined, bi, end[0], helix_tag)
            la, lb = end_label(bands, joined, bi, start[0]), end_label(bands, joined, bi, end[0])
            halves = la[-1:] in ("A", "B") and lb[-1:] in ("A", "B")
            if a[0] == b[0] == "sw" and a[1] == b[1] and la != lb and halves:
                continue                                    # between a crossover's halves: its OS block
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


def masts(bands, cps, found, cp_of, corner_blocks=None) -> list[dict]:
    """Home masts where a track from outside a control point meets one of its switches."""
    by_leg = {}
    for t in found:
        for (n, p), far in zip(t["legs"], reversed(t["ends"])):
            by_leg[(t["band"], n, p)] = (t, far)
    out = []
    for bi, (title, band, _) in enumerate(bands):
        lv = band_level(title)
        if not lv:
            continue
        rail, srow = band["rail"], band["R"]["srow"]
        for n, d in band["nodes"].items():
            if d["kind"] not in ("switch", "dx") or n not in rail:
                continue
            num = base(d["label"])
            cp = cp_of.get(num)
            if cp is None:
                continue
            for p in sorted(set(d["ins"]) | set(d["outs"])):
                hit = by_leg.get((bi, n, p))
                if hit is None:
                    continue
                t, (kind, far) = hit
                loop = kind == "sw" and far == num and t["name"].endswith(" Loop")   # comes back to this switch
                if kind == "bumper" or (kind == "sw" and cp_of.get(far) == cp and not loop):
                    continue
                if t["loop"] and p not in LOOP_HALF:
                    raise MapError(f"Switch {num}: balloon loop {t['name']} leaves from leg {p}; a loop's halves "
                                   f"leave from legs {' and '.join(LOOP_HALF)}")
                eastward = TAU[p] * rail[n] == 1
                sid = d["ins"].get(p) or d["outs"].get(p)
                out.append(dict(level=lv, cp=cp, switch=num, number=int(num) + 1, letter="L" if eastward else "R",
                                protects=corner_blocks[num][p] if d["kind"] == "dx" else "",
                                heads=2 if (p == "A" or d["kind"] == "dx") else 1, row=srow.get(sid, 0),
                                track=f"{t['name']} {LOOP_HALF[p]}" if t["loop"] else t["name"], band=bi,
                                half=LOOP_HALF[p] if t["loop"] else 0))
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
