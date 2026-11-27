"""The block layer of every level: one process from the drawing, rules and the owner's hand data.

    from block_layer import layer, name_tracks

What it makes, for each level drawn on a band:
- an OS block per switch, "OS Switch <n>". A single crossover is one OS block, unless its halves have their own
  detectors: then each half is an OS block of its own, given in block_overrides.csv (kind crossover_half; staging 7,
  23 and 35) and named OS Switch <n><its letter> (the owner's name, by its ID, wins in the device master). A double
  crossover's corners are device_map_schematic.xover_corners' (main and upper), not this module's; its node keeps
  "OS Switch <n>" here, as mast_plan reads it.
- a block per track, named by name_tracks: the name store's name when it gives its strands one ("Track <name>";
  hartlib.track_names, looked up by each strand's ID, store_names, never read off the drawing; a helix track its
  "Track <plan name>" too, on every level, so each helix block is one block across levels), else
  plan_tracks.track_names' end-switch rule ("Track 107-109", "Track 3 Spur 1", "Track 107 Loop"). A balloon loop, or a
  track block_overrides.csv splits (kind split, the owner's choice: 227-241, Princess K-1 and K-2), is two blocks
  parted at its turnback, half 1 at the lower-numbered switch (loop_halves); a half is named by its strand's name
  when the two halves have different ones (Track K-2, Track K-1), else "<track> <half>" (half_block). A name given
  to two blocks of one level stops.
- parts: a piece of track inside another block (the device master's part_of). A link, a track between two
  switches shorter than LINK_CM, is part of the lower-numbered switch's OS block (the one at that end: a crossover
  half's, when the half has its own; a double crossover's corner block of the leg it leaves, `corners`), on every
  level (step 5 part 2). A link drawn to a connector, whose lower-numbered switch is on another
  band, takes the OS block of its end switch on its own band (link_block). block_overrides.csv (kind track) gives a
  track, or the piece of it at one end switch, to another OS block where the field wiring (or, on main and upper, the
  owner) says otherwise. A whole track's part is named as the track; a piece at one end "<track> at <switch>" ("Track
  1-3 at 1"). A track with pieces at both ends is all pieces, sharing its length evenly; with one, that piece's length
  is its row's cm and the rest of the track is its own block.

LINK_CM is 50 cm on every level: staging's wiring folds every track between two switches up to
42 cm (11-13) by the rule, and its next is Barn at 92 cm; on main and upper it folds 25 links, the longest 229-233
(48.2 cm).

block_overrides.csv (block_override_rows.OVERRIDE_COLUMNS, read and checked for shape by block_override_rows.read_block_overrides, the
one reader of the file), every row the owner's fact, keyed by switch numbers so a new export moves rows with their
tracks, a row of any level (1 staging, 2 main, 3 upper). Its kind split rows are split_edges' (mast_rule
.read_block_splits); this module resolves the other two:
- kind track: level, switch_a and switch_b (the track's end switches, lower first) and parallel (1, 2 in plan_tracks.plan_order
  where two tracks run between them, block_override_rows.resolve_track); `end` empty for the whole track or one of its end
  switches for the piece at that end; `block` the OS block it is part of, which must be the OS block at that end (at
  either end for a whole track); `cm` the piece's length, given only for a piece at one end whose track keeps the
  rest (and then needed, under the track's length); `inside` yes keeps the piece inside its OS block with no JMRI or
  layout block of its own (Layer.inside; the owner's: the halves of 35-39, for Mast 36RB's route to Mast 68),
  empty for the rule, a part that is a JMRI block of its own.
- kind crossover_half: switch_a the crossover's number, switch_b the switch its half's leg A track runs to, `block`
  the half's own OS block's ID (os:7:A-13C) and `parallel` its letter, 1 a or 2 b (hartlib.hand_lists). Both halves
  of a crossover have a row, or neither.
Stops (BlockError, naming the file, line and level) on a row in no such shape, a track or half it does not find, a row
that would apply twice, or a block that is not the OS block at its end; and on a layer that breaks its invariants
(check): every switch node in one OS block, every strand outside a crossover in at least one block, every part's
block an OS block of its level, no name for two things.
"""
from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple, TypedDict

import publish_draft as pd  # first: it puts hartlib on the path
import block_override_rows
import mast_rule
import plan_bands
import plan_tracks
from hartlib import layer_files, railroad
from map_error import MapError
from plan_bands import Band, Bands, Levels
from plan_tracks import Joined, Runs, Track, edge_key

LINK_CM = 50.0
OVERRIDES_NAME = block_override_rows.OVERRIDES_NAME     # in pd.DATA, looked up when read (a test may point pd.DATA elsewhere)
EXCEPTION_KINDS = ("track", "crossover_half")   # its rows this module resolves; its split rows are split_edges'
natural, base = railroad.natural, railroad.switch_number


class BlockError(MapError):
    pass


Drawings = Mapping[int, str]                    # {level: drawing} (drawings): the plan_overrides.json section
Ends = dict[str, "str | None"]                  # {end switch: the OS block at that end on the band} (end_blocks)


def plan_name(t: Track, bi: int, sid: str) -> str:
    """The name store's name of strand `sid` of band `bi`, a strand of track entry `t` ("" when it has none): the
    names tracks() looked up by the strands' IDs (staging_device_map.strand_names), never the drawing's."""
    return t["names"].get((bi, sid), "")


# ---------------------------------------------------------------- track names

def sheet_of(bands: Bands, levels: Levels, data: Path | None = None) -> dict[int, str]:
    """{band index: its drawing} of the bands `levels` holds: the staging band is one drawing, the main and upper
    bands another (two plan inputs, whose edge ids repeat), told apart by the level a band's title has in `levels`
    and the plan-overrides section that holds that level (drawings of `data`)."""
    of = drawings(data)
    return {bi: drawing(levels[title], of, title) for bi, (title, _b, _o) in enumerate(bands) if title in levels}


def drawings(data: Path | None = None) -> dict[int, str]:
    """{level: drawing}: the section of plan_overrides.json in `data` (default publish_draft.DATA) whose bands
    (plan_bands.band_places) hold each level. A section is one plan input, whose edge ids are its own. BlockError for
    a file or section that cannot be read, and for a level two sections hold."""
    folder = Path(pd.DATA if data is None else data)
    try:
        whole = layer_files.read_file("plan_overrides", folder)
    except layer_files.LayerFileError as exc:
        raise BlockError(str(exc)) from exc
    out: dict[int, str] = {}
    for sheet in (k for k in whole if not k.startswith("_")):
        try:
            places = plan_bands.band_places(whole[sheet])
        except MapError as exc:
            raise BlockError(f"plan_overrides.json section {sheet}: {exc}") from exc
        for title, (level, _height) in places.items():
            if out.setdefault(level, sheet) != sheet:
                raise BlockError(f"plan_overrides.json: level {level} is in sections {out[level]} and {sheet} "
                                 f"(band {title!r}); a level's bands are one plan drawing")
    return out


def drawing(level: int, of: Drawings | None = None, title: str | None = None) -> str:
    """The drawing (drawings, or `of`) a band of `level` (titled `title`, for the message) is on. BlockError for a
    level no section holds."""
    of = drawings() if of is None else of
    if level not in of:
        band = f" (band {title!r})" if title else ""
        raise BlockError(f"plan_overrides.json gives no band level {level}{band} (it has levels {sorted(of)})")
    return of[level]


def tracks(bands: Bands, runs: Runs, joined: Joined, levels: Levels, data: Path | None = None,
           owner: dict | None = None) -> list[Track]:
    """plan_tracks.tracks of every band `levels` holds, one drawing at a time (sheet_of: a track's edges are keyed
    within its drawing; drawings of `data`), each level's helix ends tagged "H" (name_tracks names a helix track by
    its plan name). Each entry's `names` ({(band index, strand): name}) are the name store's for its strands on every
    band of its drawing (a track cut by a connector is one entry), looked up by their IDs
    (staging_device_map.strand_names over the drawing's hand plan_overrides section; `owner`: hartlib.track_names
    .owner_names in its shape, default the rows beside `data`). BlockError when a name cannot be looked up."""
    out: list[Track] = []
    of = drawings(data)
    titles: defaultdict[int, list[str]] = defaultdict(list)
    for t, lv in levels.items():
        titles[lv].append(t)
    for name in dict.fromkeys(drawing(lv, of, ", ".join(titles[lv])) for lv in sorted(titles)):
        mine = {t: lv for t, lv in levels.items() if drawing(lv, of) == name}
        if mine:
            out += plan_tracks.tracks(bands, runs, joined, {lv: "H" for lv in mine.values()}, mine)
    store_names(out, bands, joined, levels, data, owner)
    return out


def store_names(found: Sequence[Track], bands: Bands, joined: Joined, levels: Levels, data: Path | None = None,
                owner: dict | None = None) -> None:
    """Give each track entry of `found` (plan_tracks.tracks of the bands `levels` holds) its `names`, {(band index,
    strand): name}: the name store's for its strands on every band of its drawing (a track cut by a connector is one
    entry), looked up by their IDs (staging_device_map.strand_names over the drawing's hand plan_overrides section in
    `data`; `owner`: hartlib.track_names.owner_names in its shape, default the rows beside `data`). plan_name reads
    them. BlockError when a name cannot be looked up."""
    import staging_device_map as sdm        # band_refs, the strands' IDs (it does not import this module)
    folder = Path(pd.DATA if data is None else data)
    try:
        whole = layer_files.read_file("plan_overrides", folder)
    except layer_files.LayerFileError as exc:
        raise BlockError(str(exc)) from exc
    sheet = sheet_of(bands, levels, folder)
    named: dict[int, Mapping[str, str]] = {}
    for bi, name in sheet.items():
        try:
            named[bi] = sdm.strand_names(bands, joined, bi, whole[name], owner, folder)
        except sdm.StagingMapError as exc:
            raise BlockError(f"the track names of {bands[bi][0]!r}: {exc}") from exc
    for t in found:
        edges = {edge_key(bands[t["band"]][1]["strands"][sid]["edge"]) for sid in t["strands"]}
        t["names"] = {(bi, sid): nm for bi, got in named.items() if sheet[bi] == sheet[t["band"]]
                      for sid, nm in got.items() if edge_key(bands[bi][1]["strands"][sid]["edge"]) in edges}


def name_tracks(found: Sequence[Track], helix: Mapping[str, Any]) -> None:
    """Fill `name` in each track entry of tracks(): "Track <plan name>" when the name store gives its strands one
    name (plan_name; a helix track too: its pieces on two drawings get one name, so they are one block across the
    level split), else the end-switch rule (plan_tracks.track_names). A track whose strands get two names keeps the
    end-switch name: it must be split into halves (layer checks it), each named by its own.
    BlockError on a track up the helix whose one plan name is not a helix track of `helix` (read_helix_tracks)."""
    rest: list[Track] = []
    bad: list[str] = []
    for t in found:
        names = sorted({plan_name(t, t["band"], sid) for sid in t["strands"]} - {""})
        if any(k == "helix" for k, _v in t["ends"]):
            if len(names) != 1 or names[0] not in helix:
                bad.append(f"level {t['level']}: the track up the helix from Switch "
                           f"{', '.join(v for k, v in t['ends'] if k == 'sw')} has plan name(s) {names or 'none'}, "
                           f"which is not a helix track of {plan_bands.HELIX_SOURCE.name} ({', '.join(sorted(helix))})")
                continue
        if len(names) == 1:
            t["name"] = f"Track {names[0]}"
        else:
            rest.append(t)
    if bad:
        raise BlockError("; ".join(bad))
    plan_tracks.track_names(rest)


# ---------------------------------------------------------------- the owner's exceptions

OsGift = tuple[str, int, "float | None"]     # a track row given to an OS block: (block, line, cm or None)


@dataclass
class Exceptions:
    """block_overrides.csv's track and crossover_half rows resolved against the drawing: track rows by track entry
    (plan_tracks.track_key), {end: (block, line, cm or None)} ("" the whole track), crossover halves by (band, node):
    (block, line), and the lines of the track rows marked `inside` (the piece stays inside its OS block, with no JMRI
    block of its own)."""
    tracks: dict[plan_tracks.TrackKey, dict[str, OsGift]] = field(default_factory=dict)
    halves: dict[tuple[int, str], tuple[str, int]] = field(default_factory=dict)
    inside: set[int] = field(default_factory=set)


def crossover_pairs(band: Band) -> dict[str, str]:
    """{switch node: its other half} of each single crossover drawn on one band: two switch nodes of one number
    joined leg C to leg C."""
    out: dict[str, str] = {}
    nodes = band["nodes"]
    for s in band["strands"].values():
        (u, pu), (v, pv) = s["src"], s["dst"]
        if u != v and pu == pv == "C" and nodes[u]["kind"] == nodes[v]["kind"] == "switch" and \
                base(nodes[u].get("label") or "") == base(nodes[v].get("label") or "") != "":
            out[u], out[v] = v, u
    return out


def overrides_path(data: Path | None = None) -> Path:
    """block_overrides.csv in the schematic data folder `data` (default publish_draft.DATA as it is now): the one place
    its path is made, for every kind of its rows (build_device_map.block_overrides passes its OVERRIDES folder)."""
    return Path(pd.DATA if data is None else data) / OVERRIDES_NAME


def read_exceptions(found: Sequence[Track], bands: Bands, levels: Levels, path: Path | None = None) -> Exceptions:
    """block_overrides.csv's track and crossover_half rows for the `levels` ({band title: level}) drawn, resolved in
    `found` (named tracks). A row of a level not drawn is checked for shape only (block_override_rows
    .read_block_overrides, which checks every row of the file). See the module text for the rows and the stops."""
    path = path or overrides_path()
    try:
        rows = block_override_rows.read_block_overrides(path, EXCEPTION_KINDS)
    except MapError as exc:
        raise BlockError(str(exc)) from exc
    wanted = set(levels.values())
    out, bad = Exceptions(), []
    for r in rows:
        if int(r["level"]) not in wanted:
            continue
        if r["kind"] == "crossover_half":
            problem = _crossover_half_row(r, found, bands, out)
        else:
            problem = _track_row(r, found, out)
        if problem:
            bad.append(f"line {r['line']} (level {r['level']}): {problem}")
    if bad:
        raise BlockError(f"{path.name}: " + "; ".join(bad))
    return out


def _crossover_half_row(r: block_override_rows.OverrideRow, found: Sequence[Track], bands: Bands,
                        out: Exceptions) -> str:
    """Put a crossover_half row's block in out.halves under the half (band, node) whose leg A track runs from
    switch_a to switch_b; the problem ("" when none) when no one half matches or the half is given twice."""
    level = int(r["level"])
    hits = []
    for t in found:
        if t["level"] != level:
            continue
        pairs = crossover_pairs(bands[t["band"]][1])
        for j, (node, port) in enumerate(t["legs"]):
            if port == "A" and node in pairs and t["ends"][j] == ("sw", r["switch_a"]) and \
                    t["ends"][1 - j] == ("sw", r["switch_b"]):
                hits.append((t["band"], node))
    if len(hits) != 1:
        return (f"{len(hits) or 'no'} crossover half of Switch {r['switch_a']} has its leg A track running to "
                f"Switch {r['switch_b']}")
    if hits[0] in out.halves:
        return f"that half is given its block on line {out.halves[hits[0]][1]} too"
    out.halves[hits[0]] = (r["block"], r["line"])
    return ""


def _track_row(r: block_override_rows.OverrideRow, found: Sequence[Track], out: Exceptions) -> str:
    """Put a track row's block in out.tracks under its track (block_override_rows.resolve_track) and end, and its
    line in out.inside when the row keeps the piece inside its OS block; the problem ("" when none) when no one
    track matches or the track already has a block for that end."""
    level = int(r["level"])
    t = block_override_rows.resolve_track(r, [t for t in found if t["level"] == level])
    if t is None:
        return str(r["problem"])
    got = out.tracks.setdefault(plan_tracks.entry_key(t), {})
    if r["end"] in got or ("" in got and r["end"]) or (got and not r["end"]):
        return f"{t['name']} is given a block on line {next(iter(got.values()))[1]} already"
    got[r["end"]] = (r["block"], r["line"], r["cm"])
    if r["inside"]:
        out.inside.add(r["line"])
    return ""


# ---------------------------------------------------------------- the layer

def loop_halves(band: Band, runs: Runs, split: Mapping[str, str], split_file: str = OVERRIDES_NAME) -> dict[str, int]:
    """{strand id: 1 or 2} for each balloon loop of `band` (a run that leaves a switch and comes back to it), by the
    leg its strand leaves the switch from (mast_rule.LOOP_HALF), and for each track `split` names ({plan edge: track
    name}, build_device_map.split_edges: a run between two switches folded at one turnback): half
    1 the strand at its lower-numbered switch. Stops on a loop not drawn as two tracks joined by one turnback, or one
    not on legs B and C, since the halves would then be ambiguous."""
    out: dict[str, int] = {}
    parted: set[str] = set()
    for start, chain, end in runs(band):
        edges = {re.sub(r"\.\d+$", "", band["strands"][sid]["edge"]) for sid, _ in chain}
        if start[0] != end[0] and len(edges) == 1 and next(iter(edges)) in split:
            parted |= edges
            if len(chain) != 2:
                raise MapError(f"{split[next(iter(edges))]} is drawn as {len(chain)} track(s); a split track needs "
                                  "two joined by one turnback")
            labels = [natural(base(band["nodes"][x[0]].get("label") or "")) for x in (start, end)]
            first = 0 if labels[0] <= labels[1] else 1
            out[chain[0][0]], out[chain[-1][0]] = (1, 2) if first == 0 else (2, 1)
            continue
        if start[0] != end[0] or band["nodes"][start[0]]["kind"] not in ("switch", "dx"):
            continue
        if len(chain) != 2 or {start[1], end[1]} != set(mast_rule.LOOP_HALF):
            raise MapError(f"the balloon loop at switch {band['nodes'][start[0]].get('label')} is drawn as "
                              f"{len(chain)} track(s) on legs {start[1]} and {end[1]}; its halves need two tracks "
                              "joined by one turnback, on legs B and C")
        for (sid, _), (_, port) in zip((chain[0], chain[-1]), (start, end)):
            out[sid] = mast_rule.LOOP_HALF[port]
    drawn = {re.sub(r"\.\d+$", "", st["edge"]) for st in band["strands"].values()}
    stale = sorted(e for e in set(split) & drawn - parted)
    if stale:           # the edge is on this band but not a track between two switches: its id moved
        raise MapError(f"{split_file}: {', '.join(f'{e} ({split[e]})' for e in stale)} is not a track folded at "
                          "its turnback on this band; give the plan edge the track is drawn on")
    return out


def split_edges(found: Sequence[Track], levels: Levels, path: Path, data: Path | None = None
                ) -> dict[str, dict[str, str]]:
    """{drawing (sheet_of): {plan edge: track name}} of the tracks block_overrides.csv splits into two blocks at their
    turnback (the owner's choice, not a rule: block_override_rows.read_block_splits), among the `levels` drawn: each row's end
    switches resolved to the named track in `found`, and that track to the one plan edge it is drawn on. Stops on a
    track drawn on more than one plan edge (a split needs one track folded at one turnback)."""
    names = block_override_rows.read_block_splits(path, found, levels)
    out: dict[str, dict[str, str]] = {}
    bad: list[str] = []
    of = drawings(data)
    for t in sorted((t for t in found if t["name"] in names), key=lambda t: natural(t["name"])):
        if len(t["trial"]) != 1:
            bad.append(f"{t['name']}: drawn on {', '.join(t['trial'])}")
            continue
        out.setdefault(drawing(t["level"], of), {})[t["trial"][0].removeprefix("Track ")] = t["name"]
    if bad:
        raise BlockError(f"{path.name}: " + "; ".join(bad))
    return out


def half_name(track: str, half: int | None) -> str:
    """One half of a balloon loop or split track ("Track 107 Loop" -> "Track 107 Loop 1"); any other track's name
    unchanged."""
    return track if half is None else f"{track} {half}"


class BandBlocks(TypedDict):
    """One band's blocks, as mast_plan.plan reads them: `os` {switch node: OS block}, `blocks` {strand: [block, ...]
    from the strand's first end} (a part counts as the block it is part of)."""
    os: dict[str, str]
    blocks: dict[str, list[str]]


class Part(TypedDict):
    """A piece of track inside another block: the block it is part of, its level, its track entry, length and why."""
    part_of: str
    level: int
    track: Track
    cm: float
    why: str


@dataclass
class Layer:
    """The block layer of the bands of some levels. `bands`: {band index: BandBlocks}; `rows`: {band index: {strand:
    [row name, ...]}}, the blocks with a part's own name; `cm`: {block: cm} (an OS block 0: its boundary is at the
    switch's leg); `parts`: {part name: Part}; `tracks`: {block: (track entry, half)} of the tracks' own blocks;
    `inside`: {piece name: its OS block} of the pieces block_overrides.csv keeps inside their OS block (`inside` yes:
    no part, no JMRI block of their own)."""
    bands: dict[int, BandBlocks] = field(default_factory=dict)
    rows: dict[int, dict[str, list[str]]] = field(default_factory=dict)
    cm: dict[str, float] = field(default_factory=dict)
    parts: dict[str, Part] = field(default_factory=dict)
    tracks: dict[str, tuple[Track, int | None]] = field(default_factory=dict)
    inside: dict[str, str] = field(default_factory=dict)


def is_link(t: Track) -> bool:
    """Whether track `t` is a link: between two different switches and shorter than LINK_CM."""
    sws = [v for k, v in t["ends"] if k == "sw"]
    return len(sws) == 2 == len(t["ends"]) and sws[0] != sws[1] and t["cm"] < LINK_CM


def link_block(ends: Ends) -> str | None:
    """The OS block a link is part of, from `ends` ({end switch: the OS block at that end on the link's band, None
    when the switch is drawn on another band}): the lower-numbered switch's, or, for a link drawn to a connector whose
    lower-numbered switch is across it, the one end switch's on the band; None when neither is on the band."""
    for s in sorted(ends, key=natural):
        if ends[s] is not None:
            return ends[s]
    return None


def masted_block(t: Track, ends: Ends, masts: Mapping[str, str], level: int, where: str, bad: list[str]
                 ) -> tuple[str | None, str | None]:
    """(the OS block link `t` is part of, why) from `ends` (end_blocks) and `masts` ({end switch: the home mast that
    stands at its points facing the link}; the block boundary is at the mast): with a mast at one
    end, the OS block at the other end; with none, link_block's (the lower-numbered switch's). A mast at both ends is a
    problem in `bad` (why None): the link would be inside the OS block of one of them."""
    if len(masts) > 1:
        bad.append(f"level {level}: the link {t['name']} has a home mast facing it at both ends ("
                   + ", ".join(f"Mast {m} at Switch {s}" for s, m in sorted(masts.items(), key=lambda x: natural(x[0])))
                   + f"): one of them would stand inside its own OS block; give the link to one OS block in {where}")
        return None, None
    if masts:
        (s, mast), = masts.items()
        other = [v for v in ends if v != s]
        return (ends[other[0]] if other else None), (f"OS block at its other end: Mast {mast} stands at Switch {s}'s "
                                                    "points facing it, so the block boundary is at the mast")
    block = link_block(ends)
    low = min(ends, key=natural)
    return block, ("lower-numbered switch's OS block" if ends[low] == block else
                   "OS block of its end switch on its band (a connector)")


def end_blocks(t: Track, nodes: Mapping[str, Any], os_: Mapping[str, str], corners: Mapping[str, Mapping[str, str]],
               level: int, bad: list[str]) -> Ends:
    """{end switch: the OS block at that end of track `t` on this band (`os_`), None for a switch drawn on another
    band}: a double crossover's corner block of the leg the track leaves (`corners`, {switch number: {leg: block}}).
    A double crossover with no corners given is a problem in `bad` (and None)."""
    out: Ends = {}
    for (node, port), (k, end) in zip(t["legs"], t["ends"]):
        if k != "sw":
            continue
        v = str(end)                                # a switch end's number
        if node not in os_:
            out[v] = None
        elif nodes[node]["kind"] == "dx":
            got = corners.get(v, {}).get(port)
            if got is None:
                bad.append(f"level {level}: {t['name']} leaves double crossover {v} at leg {port}, which has no "
                           "corner block given")
            out[v] = got
        else:
            out[v] = os_[node]
    return out


@dataclass
class _Build:
    """What layer() fills and checks as it walks the bands: the layer, the problems found and the hand rows used."""
    exceptions: Exceptions
    overrides_file: str
    corners: dict[str, dict[str, str]]
    posts: dict[tuple[int, str, str], str]
    out: Layer = field(default_factory=Layer)
    bad: list[str] = field(default_factory=list)
    used: set[object] = field(default_factory=set)       # crossover halves' (band, node) and tracks' entry_key


def layer(bands: Bands, runs: Runs, found: Sequence[Track], levels: Levels, split: Mapping[str, Mapping[str, str]],
          exceptions: Exceptions, overrides_file: str = OVERRIDES_NAME,
          corners: dict[str, dict[str, str]] | None = None, posts: dict[tuple[int, str, str], str] | None = None,
          data: Path | None = None) -> Layer:
    """The block layer of every band whose level `levels` ({band title: level}) holds, from `found` (name_tracks),
    `split` ({drawing: {plan edge: track name}}, split_edges: the owner's block splits), `exceptions`
    (read_exceptions) and `corners` ({switch number: {schematic leg: corner block}} of each double crossover,
    device_map_schematic.corner_blocks_of) and `posts` ({(band index, switch node, leg): mast name} of the home masts,
    mast_plan.home_posts: a link a mast faces from its own switch joins the OS block at its other end, masted_block).
    BlockError on a track the layer cannot place or a layer that breaks its invariants (check)."""
    b = _Build(exceptions, overrides_file, corners or {}, posts or {})
    sheet = sheet_of(bands, levels, data)
    by_edge: dict[tuple[str, str], Track] = {}
    for t in found:
        for sid in t["strands"]:
            by_edge[(sheet[t["band"]], edge_key(bands[t["band"]][1]["strands"][sid]["edge"]))] = t
    for bi, (title, band, _o) in enumerate(bands):
        level = plan_bands.band_level(title, levels)
        if not level:
            continue
        os_ = _os_blocks(b, bi, band, level)
        halves = loop_halves(band, runs, split.get(sheet[bi], {}))
        blocks: dict[str, list[str]] = {}
        rows: dict[str, list[str]] = {}
        for sid, st in band["strands"].items():
            t = by_edge.get((sheet[bi], edge_key(st["edge"])))
            if t is None:
                _crossover_inside(b, sid, st, band["nodes"], os_, level, title, blocks, rows)
                continue
            got = _track_strand(b, bi, sid, st, t, halves.get(sid), halves, band["nodes"], os_, level, title)
            if got is not None:
                blocks[sid], rows[sid] = got
        b.out.bands[bi] = {"os": os_, "blocks": blocks}
        b.out.rows[bi] = rows
    unused = sorted(line for key, (block, line) in exceptions.halves.items() if key not in b.used)
    unused += sorted(line for key, given in exceptions.tracks.items() if key not in b.used
                     for _b, line, _cm in given.values())
    if unused:
        b.bad.append(f"{overrides_file} line(s) {', '.join(map(str, sorted(unused)))} match nothing drawn")
    b.bad += check(bands, b.out, levels, found, corners)
    if b.bad:
        raise BlockError("; ".join(b.bad))
    return b.out


def _os_blocks(b: _Build, bi: int, band: Band, level: int) -> dict[str, str]:
    """{switch node: OS block} of band `bi`: "OS Switch <n>", or a crossover half's own block (crossover_half rows),
    each at 0 cm, a double crossover's corner blocks too; a single crossover with only one half given is a problem."""
    nodes = band["nodes"]
    os_: dict[str, str] = {}
    for n, d in nodes.items():
        if d["kind"] in ("switch", "dx"):
            own = b.exceptions.halves.get((bi, n))
            os_[n] = own[0] if own else f"OS Switch {base(d['label'])}"
            if own:
                b.used.add((bi, n))
            b.out.cm[os_[n]] = 0.0
            if d["kind"] == "dx":           # its corner blocks, which a link may be part of: 0 cm as well
                b.out.cm.update({c: 0.0 for c in b.corners.get(base(d["label"]), {}).values()})
    halves = b.exceptions.halves
    for n, m in sorted(crossover_pairs(band).items()):
        if ((bi, n) in halves) != ((bi, m) in halves) or ((bi, n) in halves and os_[n] == os_[m]):
            b.bad.append(f"level {level}: crossover {base(nodes[n]['label'])}: give both halves an OS block of "
                         f"their own in {b.overrides_file}, or neither")
    return os_


def _crossover_inside(b: _Build, sid: str, st: Mapping[str, Any], nodes: Mapping[str, Any], os_: dict[str, str],
                      level: int, title: str,
                      blocks: dict[str, list[str]], rows: dict[str, list[str]]) -> None:
    """A strand on no track: inside a crossover (its halves lettered A and B, or staging's 7, 23 and 35), in its
    OS block, or drawn between two halves with blocks of their own (then in none); anything else is a problem."""
    ends = [x for x in (st["src"][0], st["dst"][0]) if nodes[x]["kind"] in ("switch", "dx")]
    links = [x for x in (st["src"][0], st["dst"][0]) if nodes[x].get("sub") == "link"]
    if not ends or len(ends) + len(links) != 2 or len({base(nodes[x]["label"]) for x in ends}) != 1:
        b.bad.append(f"level {level}: strand {sid} ({st['edge']}) on {title!r} is on no track and inside "
                     "no crossover")
        return
    if len(ends) == 2 and os_[ends[0]] != os_[ends[1]]:
        return              # between two halves with blocks of their own: drawn inside the crossover
    blocks[sid] = rows[sid] = [os_[ends[0]]]


def _track_strand(b: _Build, bi: int, sid: str, st: Mapping[str, Any], t: Track, h: int | None,
                  halves: Mapping[str, int], nodes: Mapping[str, Any], os_: dict[str, str], level: int, title: str
                  ) -> tuple[list[str], list[str]] | None:
    """(blocks, row names) of strand `sid` of track `t` (half `h` of a loop or split track, or None): the track's
    own block, the OS blocks block_overrides.csv gives its pieces, or the OS block a link is part of. None, with the
    problem in b.bad, when the strand cannot be placed."""
    out = b.out
    name = half_block(bi, t, sid, h, halves)
    held = out.tracks.get(name)
    if held is not None and held != (t, h) and held[0]["level"] == t["level"]:
        b.bad.append(f"level {level}: {name} names two blocks ({', '.join(held[0]['trial'])} and "
                     f"{', '.join(t['trial'])})")
        return None
    out.tracks[name] = (t, h)
    out.cm[name] = round(t["cm"] / 2, 1) if h else t["cm"]
    ex = b.exceptions.tracks.get(plan_tracks.entry_key(t))
    ends = end_blocks(t, nodes, os_, b.corners, level, b.bad)
    if ex:
        return _given_pieces(b, st, t, h, ex, name, ends, level)
    if is_link(t):
        return _link_part(b, bi, t, name, ends, level, title)
    return [name], [name]


def _given_pieces(b: _Build, st: Mapping[str, Any], t: Track, h: int | None, ex: Mapping[str, OsGift], name: str,
                  ends: Ends, level: int) -> tuple[list[str], list[str]] | None:
    """The blocks and row names of a track block_overrides.csv gives to OS blocks (exception_pieces), its parts and
    `inside` pieces recorded in the layer; None, with the problem in b.bad, for a split track given to OS blocks."""
    out = b.out
    if h:
        lines = ", ".join(str(x[1]) for x in ex.values())
        b.bad.append(f"level {level}: {t['name']} is split in halves and given to OS blocks in "
                     f"{b.overrides_file} (lines {lines}): one or the other")
        return None
    pieces = exception_pieces(t, ex, name, ends, b.overrides_file, b.bad)   # from switch_a's end
    if pieces is None:
        return None
    at_end = {v: node for (node, _p), (k, v) in zip(t["legs"], t["ends"]) if k == "sw"}
    if st["src"][0] != at_end[min(at_end, key=natural)]:                # from the strand's first end
        pieces = pieces[::-1]
    for row, block, line, cm in pieces:
        if line in b.exceptions.inside:             # inside its OS block: no part, no JMRI block
            out.inside[row] = block
        elif line:
            out.parts[row] = Part(part_of=block, level=level, track=t, cm=cm, why=f"{b.overrides_file} line {line}")
        else:                                       # the rest of the track, its own block
            out.cm[name] = cm
    if all(piece.line for piece in pieces):         # no piece left to the track's own block
        out.tracks.pop(name, None)
        out.cm.pop(name, None)
    b.used.add(plan_tracks.entry_key(t))
    return ([piece.block for piece in pieces],
            [piece.block if piece.line in b.exceptions.inside else piece.row for piece in pieces])


def _link_part(b: _Build, bi: int, t: Track, name: str, ends: Ends, level: int, title: str
               ) -> tuple[list[str], list[str]] | None:
    """The OS block link `t` is part of (masted_block), recorded as a part; None, with the problem in b.bad, when
    neither end has an OS block on the band or the link is given two blocks across a connector."""
    out = b.out
    masts = {v: b.posts[(bi, node, port)] for (node, port), (k, v) in zip(t["legs"], t["ends"])
             if k == "sw" and (bi, node, port) in b.posts}
    block, why = masted_block(t, ends, masts, level, b.overrides_file, b.bad)
    if why is None:
        return None
    if block is None:
        b.bad.append(f"level {level}: the link {t['name']} has neither end switch "
                     f"({', '.join(sorted(ends, key=natural))}) with an OS block on {title!r}")
        return None
    held = out.parts.get(t["name"])
    if held is not None and held["part_of"] != block:     # drawn on two bands, across a connector
        b.bad.append(f"level {level}: the link {t['name']} is given {held['part_of']} on one band and "
                     f"{block} on {title!r}; give it one in {b.overrides_file}")
        return None
    out.parts[t["name"]] = Part(part_of=block, level=level, track=t, cm=t["cm"],
                                why=f"the rule: under {LINK_CM:g} cm between two switches, so in the " + why)
    out.tracks.pop(name, None)
    out.cm.pop(name, None)
    return [block], [t["name"]]


class Piece(NamedTuple):
    """A piece of a track block_overrides.csv gives to OS blocks (exception_pieces): its row name, its block, the
    overrides line that gives it (0 for the rest of the track, its own block) and its length."""
    row: str
    block: str
    line: int
    cm: float


def exception_pieces(t: Track, ex: Mapping[str, OsGift], own: str, ends: Ends, where: str, bad: list[str]
                     ) -> list[Piece] | None:
    """The pieces (row name, block, overrides line or 0, cm) of a track block_overrides.csv gives to OS blocks (`ex`, {end:
    (block, line, cm)}), from its lower-numbered switch's end: the whole track as one part (its own name, its whole
    length), or a piece per end the file names ("<track> at <switch>"). Pieces at both ends share the track evenly;
    a piece at one end takes the cm its row gives, and the rest of the track, its own block
    `own`, the remaining length. None (with the problem in `bad`) when a block is not the OS block at its end, a
    parted track is drawn in several pieces, or a length is missing, out of range or given where none is taken."""
    sws = sorted(ends, key=natural)
    if "" in ex:
        block, line, cm = ex[""]
        if cm is not None:
            bad.append(f"{where} line {line}: cm {cm:g} for the whole of {t['name']}: only a piece at one end takes "
                       "its length")
            return None
        if block not in {ends[s] for s in sws}:
            bad.append(f"{where} line {line}: {t['name']} is given {block}, the OS block of neither of its end "
                       "switches")
            return None
        return [Piece(t["name"], block, line, t["cm"])]
    if len(t["strands"]) != 1:
        bad.append(f"{where} lines {', '.join(str(x[1]) for x in ex.values())}: {t['name']} is drawn as "
                   f"{len(t['strands'])} pieces; a track parted at an end is one")
        return None
    out: list[Piece] = []
    for s in sws:
        if s not in ex:
            continue
        block, line, cm = ex[s]
        name = f"{t['name']} at {s}"
        if block != ends[s]:
            bad.append(f"{where} line {line}: the piece of {t['name']} at Switch {s} is given {block}, not that "
                       f"switch's OS block {ends[s]}")
            return None
        if len(ex) == 2:
            if cm is not None:
                bad.append(f"{where} line {line}: cm {cm:g} for {name}: only a piece at one end takes its length "
                           "(pieces at both ends share the track evenly)")
                return None
            cm = round(t["cm"] / 2, 1)
        elif cm is None:
            bad.append(f"{where} line {line}: {name}: give its cm, the length of the piece inside {block}")
            return None
        elif cm >= t["cm"]:
            bad.append(f"{where} line {line}: {name}: cm {cm:g} is not under the track's {t['cm']:g}")
            return None
        out.append(Piece(name, block, line, cm))
    if len(ex) == 1:                                   # the rest of the track stays its own block
        rest = Piece(own, own, 0, round(t["cm"] - out[0].cm, 1))
        out = [out[0], rest] if next(iter(ex)) == sws[0] else [rest, out[0]]
    return out


def half_block(bi: int, t: Track, sid: str, h: int | None, halves: Mapping[str, int]) -> str:
    """The block name of strand `sid` (on band `bi`) of track `t`: the track's name, or for a half (`h`) of a balloon
    loop or split track its strand's plan name ("Track K-2") when the two halves have different ones, else
    "<track> <half>"."""
    if h is None:
        return t["name"]
    names = {halves[x]: plan_name(t, bi, x) for x in t["strands"] if x in halves}
    mine = plan_name(t, bi, sid)
    if mine and len(set(names.values())) == len(names) == 2:
        return f"Track {mine}"
    return half_name(t["name"], h)


def check(bands: Bands, lay: Layer, levels: Levels, found: Sequence[Track],
          corners: Mapping[str, Mapping[str, str]] | None = None) -> list[str]:
    """The layer's invariants: every switch node in one OS block; every strand of a track in a block; a track whose
    strands carry two plan names split into halves; every part's block an OS block of its level (a double crossover's
    corner blocks, `corners`, among them); no name both a part
    and a block, and no block of one level the name of two things (a helix block is one block across levels)."""
    bad: list[str] = []
    os_of_level: dict[int | None, set[str]] = {}
    owners: dict[tuple[int, str], plan_tracks.TrackKey] = {}
    for bi, got in lay.bands.items():
        level = plan_bands.band_level(bands[bi][0], levels)
        os_of_level.setdefault(level, set()).update(got["os"].values())
        for n, d in bands[bi][1]["nodes"].items():         # a double crossover's corner blocks are its OS blocks
            if d["kind"] == "dx" and n in got["os"]:
                os_of_level[level].update((corners or {}).get(base(d["label"]), {}).values())
        for sid in bands[bi][1]["strands"]:
            if sid not in got["blocks"] and any(sid in t["strands"] for t in found if t["band"] == bi):
                bad.append(f"level {level}: strand {sid} of a track is in no block")
    for name, (t, h) in lay.tracks.items():
        key = (t["level"], name)
        if owners.setdefault(key, plan_tracks.entry_key(t)) != plan_tracks.entry_key(t):
            bad.append(f"level {t['level']}: {name} names two tracks")
        names = {plan_name(t, t["band"], sid) for sid in t["strands"]} - {""}
        if len(names) > 1 and h is None:
            bad.append(f"level {t['level']}: {t['name']} carries plan names {sorted(names)} but is one block: name "
                       f"one of them, or split it in {OVERRIDES_NAME} (kind split)")
    for name, p in lay.parts.items():
        if p["part_of"] not in os_of_level.get(p["level"], ()):
            bad.append(f"level {p['level']}: part {name} names {p['part_of']}, no OS block of its level")
        if name in lay.tracks or name in os_of_level.get(p["level"], ()):
            bad.append(f"level {p['level']}: {name} is a part and a block")
    return bad
