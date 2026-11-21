"""The block layer of every level: one process from the drawing, rules and the owner's hand data (level unification
step 5, owner 2026-11-20; wiki/projects/level-unification-handoff.md).

    from block_layer import layer, name_tracks

What it makes, for each level drawn on a band:
- an OS block per switch, "OS Switch <n>". A single crossover is one OS block, unless its halves have their own
  detectors: then each half is an OS block of its own, named in block_exceptions.csv (kind crossover_half; staging 7,
  23 and 35). A double crossover's corners are build_device_map.xover_corners' (main and upper), not this module's;
  its node keeps "OS Switch <n>" here, as mast_plan reads it.
- a block per track, named by name_tracks: the plan's name when its strands carry one ("Track <name>"; a helix track
  its helix block from helix_tracks.csv, on every level, so each helix block is one block across levels), else
  mast_rule.track_names' end-switch rule ("Track 107-109", "Track 3 Spur 1", "Track 107 Loop"). A balloon loop, or a
  track block_splits.csv names (the owner's choice, a level column: 227-241, Princess K-1 and K-2), is two blocks
  parted at its turnback, half 1 at the lower-numbered switch (loop_halves); a half is named by its strand's plan name
  when it has one (Track K-2, Track K-1), else "<track> <half>".
- parts: a piece of track inside another block (devices.csv part_of; owner, 2026-11-20). A link, a track between two
  switches shorter than LINK_CM, is part of the lower-numbered switch's OS block (the one at that end: a crossover
  half's, when the half has its own) on a level whose FOLD_LINKS is set; block_exceptions.csv (kind track) gives a
  track, or the piece of it at one end switch, to another OS block where the field wiring says otherwise. A whole
  track's part is named as the track; a piece at one end "<track> at <switch>" ("Track 1-3 at 1", "Track Scale at
  7"). A track with pieces at both ends is all pieces; with one, the rest is the track's own block.

LINK_CM is 50 cm: staging's wiring folds every track between two switches up to 42 cm (11-13) by the rule, and its
next is Barn at 92 cm. FOLD_LINKS is a per-level setting for step 5 part 1 only: main and upper keep their links as
blocks of their own until part 2 (a panel change: their 21 dark link blocks under build_device_map.SHORT_CM, and 4 more
between 30 and 50 cm, 231-237, 113-115, 239-245 and 229-233, for the owner to decide).

block_exceptions.csv (EXCEPTION_COLUMNS), every row the owner's wiring fact, keyed by switch numbers so a new export
moves rows with their tracks:
- kind track: level, switch_a and switch_b (the track's end switches, lower first) and parallel (1, 2 from the top row
  where two tracks run between them, mast_rule.resolve_track); `end` empty for the whole track or one of its end
  switches for the piece at that end; `block` the OS block it is part of, which must be the OS block at that end (at
  either end for a whole track).
- kind crossover_half: switch_a the crossover's number, switch_b the switch its half's leg A track runs to, `block`
  the half's own OS block. Both halves of a crossover have a row, or neither.
Stops (BlockError, naming the file, line and level) on a row in no such shape, a track or half it does not find, a row
that would apply twice, or a block that is not the OS block at its end; and on a layer that breaks its invariants
(check): every switch node in one OS block, every strand outside a crossover in at least one block, every part's
block an OS block of its level, no name for two things.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

import publish_draft as pd  # first: it puts hartlib on the path
import mast_rule as mr
from hartlib import railroad

LINK_CM = 50.0
FOLD_LINKS = {1: True, 2: False, 3: False}       # step 5 part 1: main and upper keep their links (part 2: all True)
EXCEPTIONS_NAME = "block_exceptions.csv"       # in pd.DATA, looked up when read (a test may point pd.DATA elsewhere)
EXCEPTION_COLUMNS = ["level", "kind", "switch_a", "switch_b", "parallel", "end", "block", "notes"]
KINDS = ("track", "crossover_half")
natural, base = railroad.natural, railroad.switch_number


class BlockError(mr.MapError):
    pass


def edge_key(edge: str) -> str:
    """A plan edge with its connector cut letter dropped: a track cut by a connector is one track."""
    return re.sub(r"(?<=\d)[xy]$", "", edge)


def plan_name(band, sid: str) -> str:
    return (band["strands"][sid].get("name") or "").strip()


# ---------------------------------------------------------------- track names

def sheet_of(bands, levels: dict) -> dict:
    """{band index: its drawing}: the staging band is one drawing, the main and upper bands another (two plan inputs,
    whose edge ids repeat), told apart by the level a band's title has in `levels` (1 staging, else main_upper)."""
    return {bi: drawing(levels[title]) for bi, (title, _b, _o) in enumerate(bands) if title in levels}


def drawing(level: int) -> str:
    return "staging" if level == 1 else "main_upper"


def tracks(bands, runs, joined, levels: dict) -> list[dict]:
    """mast_rule.tracks of every band `levels` holds, one drawing at a time (sheet_of: a track's edges are keyed
    within its drawing), each level's helix ends tagged "H" (name_tracks names a helix track by its plan name)."""
    out = []
    for name in ("staging", "main_upper"):
        mine = {t: lv for t, lv in levels.items() if drawing(lv) == name}
        if mine:
            out += mr.tracks(bands, runs, joined, {lv: "H" for lv in mine.values()}, mine)
    return out


def name_tracks(found: list[dict], bands, helix: dict) -> None:
    """Fill `name` in each track entry of mast_rule.tracks: the plan's name of its strands when they carry one (a
    helix track's: its block in `helix`, read_helix_tracks), else the end-switch rule (mast_rule.track_names). A
    track whose strands carry two names keeps the end-switch name: it must be split into halves (layer checks it),
    each named by its own. BlockError on a helix track whose plan name helix_tracks.csv does not give."""
    rest, bad = [], []
    for t in found:
        band = bands[t["band"]][1]
        names = sorted({plan_name(band, sid) for sid in t["strands"]} - {""})
        if any(k == "helix" for k, _v in t["ends"]):
            if len(names) != 1 or names[0] not in helix:
                bad.append(f"level {t['level']}: the track up the helix from Switch "
                           f"{', '.join(v for k, v in t['ends'] if k == 'sw')} has plan name(s) {names or 'none'}, "
                           f"which {mr.HELIX_TRACKS.name} does not name ({', '.join(sorted(helix))})")
                continue
            t["name"] = helix[names[0]]["block"]
        elif len(names) == 1:
            t["name"] = f"Track {names[0]}"
        else:
            rest.append(t)
    if bad:
        raise BlockError("; ".join(bad))
    mr.track_names(rest)


# ---------------------------------------------------------------- the owner's exceptions

@dataclass
class Exceptions:
    """block_exceptions.csv resolved against the drawing: track rows by track entry id, {end: (block, line)}
    ("" the whole track), and crossover halves by (band, node): (block, line)."""
    tracks: dict = field(default_factory=dict)
    halves: dict = field(default_factory=dict)


def crossover_pairs(band) -> dict:
    """{switch node: its other half} of each single crossover drawn on one band: two switch nodes of one number
    joined leg C to leg C."""
    out = {}
    nodes = band["nodes"]
    for s in band["strands"].values():
        (u, pu), (v, pv) = s["src"], s["dst"]
        if u != v and pu == pv == "C" and nodes[u]["kind"] == nodes[v]["kind"] == "switch" and \
                base(nodes[u].get("label") or "") == base(nodes[v].get("label") or "") != "":
            out[u], out[v] = v, u
    return out


def exceptions_path() -> Path:
    """block_exceptions.csv in the schematic data folder as it is now (publish_draft.DATA)."""
    return pd.DATA / EXCEPTIONS_NAME


def read_exceptions(found: list[dict], bands, levels: dict, path: Path | None = None) -> Exceptions:
    """block_exceptions.csv for the `levels` ({band title: level}) drawn, resolved in `found` (named tracks). A row of
    a level not drawn is checked for shape only. See the module text for the rows and the stops."""
    path = path or exceptions_path()
    where = path.name
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = [{k: (v or "").strip() for k, v in r.items()} for r in reader]
    except OSError as exc:
        raise BlockError(f"cannot read {where}: {exc}") from None
    if reader.fieldnames != EXCEPTION_COLUMNS:
        raise BlockError(f"{where}: columns {reader.fieldnames}, not {EXCEPTION_COLUMNS}")
    wanted = set(levels.values())
    out, bad = Exceptions(), []
    for i, r in enumerate(rows, 2):
        at = f"line {i} (level {r['level']})"
        if r["level"] not in ("1", "2", "3") or r["kind"] not in KINDS:
            bad.append(f"{at}: level is 1, 2 or 3 and kind one of {', '.join(KINDS)}")
            continue
        if not r["block"].startswith("OS Switch "):
            bad.append(f"{at}: block {r['block']!r} is no OS block (a piece of track is part of a switch's OS block)")
            continue
        level = int(r["level"])
        if r["kind"] == "crossover_half":
            if not (mr.SWITCH_NUMBER.fullmatch(r["switch_a"]) and mr.SWITCH_NUMBER.fullmatch(r["switch_b"])) or \
                    r["parallel"] or r["end"]:
                bad.append(f"{at}: a crossover half is switch_a (the crossover) and switch_b (where its leg A track "
                           "runs), with no parallel or end")
                continue
            if level not in wanted:
                continue
            hits = []
            for t in found:
                if t["level"] != level:
                    continue
                for j, (node, port) in enumerate(t["legs"]):
                    other = t["ends"][1 - j]
                    pairs = crossover_pairs(bands[t["band"]][1])
                    if port == "A" and node in pairs and t["ends"][j] == ("sw", r["switch_a"]) and \
                            other == ("sw", r["switch_b"]):
                        hits.append((t["band"], node))
            if len(hits) != 1:
                bad.append(f"{at}: {len(hits) or 'no'} crossover half of Switch {r['switch_a']} has its leg A track "
                           f"running to Switch {r['switch_b']}")
                continue
            if hits[0] in out.halves:
                bad.append(f"{at}: that half is given its block on line {out.halves[hits[0]][1]} too")
                continue
            out.halves[hits[0]] = (r["block"], i)
            continue
        problem = mr.key_problem(r)
        if problem or not r["switch_b"] or (r["end"] and r["end"] not in (r["switch_a"], r["switch_b"])):
            bad.append(f"{at}: {problem or 'a track between two switches, its end empty or one of them'}")
            continue
        if level not in wanted:
            continue
        t = mr.resolve_track(r, [t for t in found if t["level"] == level])
        if t is None:
            bad.append(f"{at}: {r['problem']}")
            continue
        got = out.tracks.setdefault(id(t), {})
        if r["end"] in got or ("" in got and r["end"]) or (got and not r["end"]):
            bad.append(f"{at}: {t['name']} is given a block on line {next(iter(got.values()))[1]} already")
            continue
        got[r["end"]] = (r["block"], i)
    if bad:
        raise BlockError(f"{where}: " + "; ".join(bad))
    return out


# ---------------------------------------------------------------- the layer

def loop_halves(band, runs, split: dict, split_file: str = "block_splits.csv") -> dict:
    """{strand id: 1 or 2} for each balloon loop of `band` (a run that leaves a switch and comes back to it), by the
    leg its strand leaves the switch from (mast_rule.LOOP_HALF), and for each track `split` names ({plan edge: track
    name}, build_device_map.split_edges: a run between two switches folded at one turnback, owner 2026-11-19): half
    1 the strand at its lower-numbered switch. Stops on a loop not drawn as two tracks joined by one turnback, or one
    not on legs B and C, since the halves would then be ambiguous."""
    out, parted = {}, set()
    for start, chain, end in runs(band):
        edges = {re.sub(r"\.\d+$", "", band["strands"][sid]["edge"]) for sid, _ in chain}
        if start[0] != end[0] and len(edges) == 1 and next(iter(edges)) in split:
            parted |= edges
            if len(chain) != 2:
                raise mr.MapError(f"{split[next(iter(edges))]} is drawn as {len(chain)} track(s); a split track needs "
                                  "two joined by one turnback")
            labels = [natural(base(band["nodes"][x[0]].get("label") or "")) for x in (start, end)]
            first = 0 if labels[0] <= labels[1] else 1
            out[chain[0][0]], out[chain[-1][0]] = (1, 2) if first == 0 else (2, 1)
            continue
        if start[0] != end[0] or band["nodes"][start[0]]["kind"] not in ("switch", "dx"):
            continue
        if len(chain) != 2 or {start[1], end[1]} != set(mr.LOOP_HALF):
            raise mr.MapError(f"the balloon loop at switch {band['nodes'][start[0]].get('label')} is drawn as "
                              f"{len(chain)} track(s) on legs {start[1]} and {end[1]}; its halves need two tracks "
                              "joined by one turnback, on legs B and C")
        for (sid, _), (_, port) in zip((chain[0], chain[-1]), (start, end)):
            out[sid] = mr.LOOP_HALF[port]
    drawn = {re.sub(r"\.\d+$", "", st["edge"]) for st in band["strands"].values()}
    stale = sorted(e for e in set(split) & drawn - parted)
    if stale:           # the edge is on this band but not a track between two switches: its id moved
        raise mr.MapError(f"{split_file}: {', '.join(f'{e} ({split[e]})' for e in stale)} is not a track folded at "
                          "its turnback on this band; give the plan edge the track is drawn on")
    return out


def split_edges(found: list[dict], levels: dict, path: Path) -> dict:
    """{drawing (sheet_of): {plan edge: track name}} of the tracks block_splits.csv parts into two blocks at their
    turnback (the owner's choice, not a rule: mast_rule.read_block_splits), among the `levels` drawn: each row's end
    switches resolved to the named track in `found`, and that track to the one plan edge it is drawn on. Stops on a
    track drawn on more than one plan edge (a split needs one track folded at one turnback)."""
    names = mr.read_block_splits(path, found, levels)
    out, bad = {}, []
    for t in sorted((t for t in found if t["name"] in names), key=lambda t: natural(t["name"])):
        if len(t["trial"]) != 1:
            bad.append(f"{t['name']}: drawn on {', '.join(t['trial'])}")
            continue
        out.setdefault(drawing(t["level"]), {})[t["trial"][0].removeprefix("Track ")] = t["name"]
    if bad:
        raise BlockError(f"{path.name}: " + "; ".join(bad))
    return out


def half_name(track: str, half: int | None) -> str:
    """One half of a balloon loop or split track ("Track e33" -> "Track e33 1"); any other track's name unchanged."""
    return track if half is None else f"{track} {half}"


@dataclass
class Layer:
    """The block layer of the bands of some levels. `bands`: {band index: {"os": {switch node: OS block}, "blocks":
    {strand: [block, ...] from the strand's first end]}}, as mast_plan.plan reads it (a part counts as the block it is
    part of); `rows`: {band index: {strand: [row name, ...]}}, the same with a part's own name; `cm`: {block: cm} (an
    OS block 0: its boundary is at the switch's leg); `parts`: {part name: {part_of, level, track, why}}; `tracks`:
    {block: (track entry, half)} of the tracks' own blocks."""
    bands: dict = field(default_factory=dict)
    rows: dict = field(default_factory=dict)
    cm: dict = field(default_factory=dict)
    parts: dict = field(default_factory=dict)
    tracks: dict = field(default_factory=dict)


def is_link(t: dict) -> bool:
    sws = [v for k, v in t["ends"] if k == "sw"]
    return len(sws) == 2 == len(t["ends"]) and sws[0] != sws[1] and t["cm"] < LINK_CM


def layer(bands, runs, found: list[dict], levels: dict, split: dict, exceptions: Exceptions,
          exceptions_file: str = EXCEPTIONS_NAME) -> Layer:
    """The block layer of every band whose level `levels` ({band title: level}) holds, from `found` (name_tracks),
    `split` ({drawing: {plan edge: track name}}, split_edges: the owner's block splits) and `exceptions`
    (read_exceptions). BlockError on a track the layer cannot place or a layer that breaks its invariants (check)."""
    sheet = sheet_of(bands, levels)
    by_edge = {}
    for t in found:
        for sid in t["strands"]:
            by_edge[(sheet[t["band"]], edge_key(bands[t["band"]][1]["strands"][sid]["edge"]))] = t
    out, bad, used = Layer(), [], set()
    for bi, (title, band, _o) in enumerate(bands):
        level = mr.band_level(title, levels)
        if not level:
            continue
        nodes = band["nodes"]
        pairs = crossover_pairs(band)
        os_ = {}
        for n, d in nodes.items():
            if d["kind"] in ("switch", "dx"):
                own = exceptions.halves.get((bi, n))
                os_[n] = own[0] if own else f"OS Switch {base(d['label'])}"
                if own:
                    used.add((bi, n))
                out.cm[os_[n]] = 0.0
        for n, m in sorted(pairs.items()):
            if ((bi, n) in exceptions.halves) != ((bi, m) in exceptions.halves) or \
                    ((bi, n) in exceptions.halves and os_[n] == os_[m]):
                bad.append(f"level {level}: crossover {base(nodes[n]['label'])}: give both halves an OS block of "
                           f"their own in {exceptions_file}, or neither")
        halves = loop_halves(band, runs, split.get(sheet[bi], {}))
        blocks, rows = {}, {}
        for sid, st in band["strands"].items():
            t = by_edge.get((sheet[bi], edge_key(st["edge"])))
            ends = [x for x in (st["src"][0], st["dst"][0]) if nodes[x]["kind"] in ("switch", "dx")]
            if t is None:           # inside a crossover (its halves lettered A and B, or staging's 7, 23 and 35)
                links = [x for x in (st["src"][0], st["dst"][0]) if nodes[x].get("sub") == "link"]
                if not ends or len(ends) + len(links) != 2 or len({base(nodes[x]["label"]) for x in ends}) != 1:
                    bad.append(f"level {level}: strand {sid} ({st['edge']}) on {title!r} is on no track and inside "
                               "no crossover")
                    continue
                if len(ends) == 2 and os_[ends[0]] != os_[ends[1]]:
                    continue        # between two halves with blocks of their own: drawn inside the crossover
                blocks[sid] = rows[sid] = [os_[ends[0]]]
                continue
            h = halves.get(sid)
            name = f"Track {plan_name(band, sid)}" if h and plan_name(band, sid) else half_name(t["name"], h)
            out.tracks[name] = (t, h)
            out.cm[name] = round(t["cm"] / 2, 1) if h else t["cm"]
            ex = exceptions.tracks.get(id(t))
            sws = [v for _k, v in t["ends"]]
            at_end = {v: node for (node, _p), (k, v) in zip(t["legs"], t["ends"]) if k == "sw"}
            if ex:
                if h:
                    lines = ", ".join(str(x[1]) for x in ex.values())
                    bad.append(f"level {level}: {t['name']} is split in halves and given to OS blocks in "
                               f"{exceptions_file} (lines {lines}): one or the other")
                    continue
                pieces = exception_pieces(t, ex, name, os_, at_end, exceptions_file, bad)   # from switch_a's end
                if pieces is None:
                    continue
                if st["src"][0] != at_end[min(at_end, key=natural)]:                # from the strand's first end
                    pieces = pieces[::-1]
                for row, block, line in pieces:
                    if line:
                        out.parts[row] = dict(part_of=block, level=level, track=t,
                                              why=f"{exceptions_file} line {line}")
                if all(line for _r, _b, line in pieces):        # no piece left to the track's own block
                    out.tracks.pop(name, None)
                    out.cm.pop(name, None)
                blocks[sid], rows[sid] = [b for _r, b, _l in pieces], [r for r, _b, _l in pieces]
                used.add(id(t))
                continue
            if FOLD_LINKS[level] and is_link(t):
                low = min(sws, key=natural)
                block = os_.get(at_end[low])
                if block is None:
                    bad.append(f"level {level}: the link {t['name']} ends at Switch {low} on another band; part 2 "
                               "places such links")
                    continue
                out.parts[t["name"]] = dict(part_of=block, level=level, track=t,
                                            why=f"the rule: under {LINK_CM:g} cm between two switches, so in the "
                                                "lower-numbered switch's OS block")
                out.tracks.pop(name, None)
                out.cm.pop(name, None)
                blocks[sid], rows[sid] = [block], [t["name"]]
                continue
            blocks[sid] = rows[sid] = [name]
        out.bands[bi] = {"os": os_, "blocks": blocks}
        out.rows[bi] = rows
    unused = sorted(line for key, (block, line) in exceptions.halves.items() if key not in used)
    unused += sorted(line for key, got in exceptions.tracks.items() if key not in used for _b, line in got.values())
    if unused:
        bad.append(f"{exceptions_file} line(s) {', '.join(map(str, sorted(unused)))} match nothing drawn")
    bad += check(bands, out, levels, found)
    if bad:
        raise BlockError("; ".join(bad))
    return out


def exception_pieces(t, ex: dict, own: str, os_: dict, at_end: dict, where: str, bad: list) -> list | None:
    """[(row name, block, exceptions line or 0)] of a track block_exceptions.csv gives to OS blocks (`ex`, {end:
    (block, line)}), from its lower-numbered switch's end: the whole track as one part (its own name), or a piece per
    end the file names ("<track> at <switch>") and, with one end named, the rest as the track's own block `own`.
    None (with the problem in `bad`) when a block is not the OS block at its end or a parted track is drawn in
    several pieces."""
    sws = sorted(at_end, key=natural)
    if "" in ex:
        block, line = ex[""]
        if block not in {os_.get(at_end[s]) for s in sws}:
            bad.append(f"{where} line {line}: {t['name']} is given {block}, the OS block of neither of its end "
                       "switches")
            return None
        return [(t["name"], block, line)]
    if len(t["strands"]) != 1:
        bad.append(f"{where} lines {', '.join(str(x[1]) for x in ex.values())}: {t['name']} is drawn as "
                   f"{len(t['strands'])} pieces; a track parted at an end is one")
        return None
    out = []
    for s in sws:
        if s in ex:
            block, line = ex[s]
            if block != os_.get(at_end[s]):
                bad.append(f"{where} line {line}: the piece of {t['name']} at Switch {s} is given {block}, not that "
                           f"switch's OS block {os_.get(at_end[s])}")
                return None
            out.append((f"{t['name']} at {s}", block, line))
        elif len(ex) == 1:
            out.append((own, own, 0))
    return out


def check(bands, lay: Layer, levels: dict, found: list[dict]) -> list[str]:
    """The layer's invariants: every switch node in one OS block; every strand of a track in a block; a track whose
    strands carry two plan names split into halves; every part's block an OS block of its level; no name both a part
    and a block, and no block of one level the name of two things (a helix block is one block across levels)."""
    bad = []
    os_of_level, owners = {}, {}
    for bi, got in lay.bands.items():
        level = mr.band_level(bands[bi][0], levels)
        os_of_level.setdefault(level, set()).update(got["os"].values())
        for sid in bands[bi][1]["strands"]:
            if sid not in got["blocks"] and any(sid in t["strands"] for t in found if t["band"] == bi):
                bad.append(f"level {level}: strand {sid} of a track is in no block")
    for name, (t, h) in lay.tracks.items():
        key = (t["level"], name)
        if owners.setdefault(key, id(t)) != id(t):
            bad.append(f"level {t['level']}: {name} names two tracks")
        names = {plan_name(bands[t["band"]][1], sid) for sid in t["strands"]} - {""}
        if len(names) > 1 and h is None:
            bad.append(f"level {t['level']}: {t['name']} carries plan names {sorted(names)} but is one block: name "
                       "one of them, or split it in block_splits.csv")
    for name, p in lay.parts.items():
        if p["part_of"] not in os_of_level.get(p["level"], ()):
            bad.append(f"level {p['level']}: part {name} names {p['part_of']}, no OS block of its level")
        if name in lay.tracks or name in os_of_level.get(p["level"], ()):
            bad.append(f"level {p['level']}: {name} is a part and a block")
    return bad
