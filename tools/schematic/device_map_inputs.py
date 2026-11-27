"""The device map's readers (build_device_map.py): the wiring, nodes and places it is built from.

- wiring.csv (hartlib.wiring, the physical wiring source): main and upper's pinned detectors (read_pins), staging's
  detectors as wired (read_staging_pins), the helix blocks' detectors (helix_pins) and the frozen control points'
  devices (frozen_wires).
- lcos_nodes.csv level 1: staging's nodes (staging_nodes).
- stations.csv and interlockings.csv: the places a line block joins (read_places).

Each stops with a MapError naming the file and line. read_pins resolves a pin against the tracks it is given
(build_device_map.read_pins gives the solved schematic's): nothing here solves the schematic or imports the builder.
The default paths (WIRING, PINS, NODES, CPS, STATIONS) are this module's: build_device_map re-exports the same
objects, so a test that wants another default file patches them here, not on the builder.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence, Set
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA, and the hartlib path
from mast_rule import MapError, Track, key_problem, resolve_track  # noqa: E402
from hartlib import devices, layer_files, railroad, wiring  # noqa: E402

SOURCES = railroad.Sources.under()
CPS = SOURCES.interlockings
NODES = SOURCES.lcos_nodes
WIRING = wiring.PATH                              # wiring.csv: the physical wiring source (hartlib.wiring)
PINS = WIRING
STATIONS = pd.DATA / "stations.csv"
STAGING = int(railroad.STAGING_LEVEL)   # staging's level, as wiring.csv and lcos_nodes.csv number it
UID = {"block": 0, "turnout": 8, "signal": 32, "sensor": 67}     # LCOS packed ID = node * 100 + UID + index
Pin = tuple[int, int]               # a detector's (node, block input index from 0)


# The hand lists name a track by the switches at its ends (switch_a, switch_b: lower number first; switch_b blank for a
# spur, whose other end is a bumper; mast_rule.track_key), so a renumbered switch moves its row with it. `parallel`
# (1, 2 in mast_rule.plan_order) says which of two tracks between the same switches; `half` (1, 2) which half of a balloon
# loop or split track, half 1 at the lower-numbered switch. A pin on a helix or OS block has its id (det:<block id>) and
# no switches (wiring.csv's detector rows); its name is the name store's.

OS_BLOCK = re.compile(r"OS Switch \d+[a-d]?")        # a main or upper OS block, named by its switch


STAGING_NAMES = (STAGING,)    # a staging reader names staging's rows only, from the field file (ADR-029)


def wiring_rows(path: Path | None = None, levels: Iterable[int | str] | None = None,
                files: devices.Files | None = None) -> list[wiring.Wire]:
    """The rows of wiring.csv (hartlib.wiring.read, `path` default the committed file; `levels` the levels whose rows
    get their names; `files` the device master they are named from), its FactsError a MapError."""
    try:
        return wiring.read(path or WIRING, levels=levels, files=files)
    except railroad.FactsError as exc:
        raise MapError(str(exc)) from exc


def read_pins(path: Path | None, found: Sequence[Track], split: Set[str],
              ids: Mapping[str, str] | None = None) -> dict[str, Pin]:
    """The low-level reader: callers that want the solved schematic's tracks by default use build_device_map.read_pins
    (device_map_schematic.read_pins). {block name: (node, input index from 0)} of wiring.csv's main and upper
    detector rows: detectors the owner put on a given input ("Block <k>" of a node, 1 to 8), which the rule then hands
    to no other block (the helix node 41). A row's level (2 or 3; staging's rows, level 1, are read_staging_pins') is
    the level its track is looked for on. A track's block is named by its end switches (switch_a, switch_b,
    parallel), plus `half` for a balloon loop or a track in `split` (names, split_tracks): resolved in `found`
    (tracks with names, build_device_map.named_tracks) to the generated block name. A helix or OS block is named by its
    id (det:<block id>): `ids` ({block id: block name} of this build's tracks) names a track by it, so a helix track
    the owner renamed is found under its new name before the device master is written again; without `ids`, the name
    store's (Wire.device). Stops on a track that does not resolve, a half missing from or given to a track that has
    none, a helix block on another level, or a block given twice (wiring.read stops on the rest)."""
    path = path or WIRING
    helix_level: dict[str, int] = {}
    for t in found:
        if any(k == "helix" for k, _v in t["ends"]):
            if helix_level.setdefault(t["name"], t["level"]) != t["level"]:
                raise MapError(f"{path.name}: helix block {t['name']} is found on levels {helix_level[t['name']]} "
                               f"and {t['level']}")
    out: dict[str, Pin] = {}
    bad: list[str] = []
    for w in wiring_rows(path):
        if w.kind != "detector" or w.level == STAGING:
            continue
        i, node, k = w.line, w.node, w.lcos_index - 1
        device = (ids or {}).get(w.id[len("det:"):], w.device) if w.id else w.device
        if device and OS_BLOCK.fullmatch(device):       # a switch's OS block (or a double crossover's corner)
            name = device                                # by its own name: a switch number is stable
        elif device:                                    # a helix block, by its id
            if device not in helix_level:
                bad.append(f"line {i}: block {device!r} ({w.id}) is no helix block "
                           f"({', '.join(sorted(helix_level))}); name any other track by switch_a and switch_b")
                continue
            if helix_level[device] != w.level:
                bad.append(f"line {i}: {device} is a level {helix_level[device]} block, not level {w.level}")
                continue
            name = device
        else:
            r = dict(switch_a=w.switch_a, switch_b=w.switch_b, parallel=w.parallel, half=w.half)
            problem = key_problem(r)
            t = None if problem else resolve_track(r, [t for t in found if t["level"] == w.level])
            if t is None:
                bad.append(f"line {i}: {problem or r['problem']}")
                continue
            looped = t["loop"] or t["name"] in split
            if w.half not in ("", "1", "2") or looped != bool(w.half):
                bad.append(f"line {i}: {t['name']} is " +
                           ("in two halves: give half 1 or 2" if looped else "one block: no half"))
                continue
            name = loop_placeholder(t["name"], int(w.half) if w.half else None)
        if name in out:
            bad.append(f"line {i}: block {name} pinned twice")
        else:
            out[name] = (node, k)
    if bad:
        raise MapError(f"{path.name}: " + "; ".join(bad))
    return out


class StagingPin(NamedTuple):
    """A staging detector as wired (a level 1 detector row of wiring.csv): its block's name (the name store's) and
    device ID (both empty for a spare input, one with a sensor in JMRI but no block), node and input index from 0."""
    line: int
    block: str
    node: int
    k: int
    id: str = ""            # the block's device ID (wiring.csv's det:<block id>), which the builder finds it by

    @property
    def sensor(self) -> str:
        return f"M2S{self.node * 100 + UID['block'] + self.k}"

    @property
    def wiring(self) -> str:
        return f"Node: {self.node} Block: {self.k + 1}"

    @property
    def input(self) -> str:
        return f"Block {self.node}-{self.k + 1}"


def staging_nodes() -> set[int]:
    """Staging's LCOS nodes: the level 1 rows of lcos_nodes.csv (as built)."""
    try:
        return {n.node for n in railroad.read_lcos_nodes(NODES) if n.level == STAGING}
    except railroad.FactsError as exc:
        raise MapError(str(exc)) from exc


def read_staging_pins(path: Path | None = None, nodes: Set[int] | None = None,
                      files: devices.Files | None = None) -> list[StagingPin]:
    """Staging's detectors as wired: the level 1 detector rows of wiring.csv, each a block by its name (staging's
    names are the field's) or a spare input (no block), its node and input. `nodes`: staging's nodes (lcos_nodes.csv
    level 1; default the committed file's). Stops on a node that is not staging's (wiring.read stops on the rest)."""
    nodes = staging_nodes() if nodes is None else nodes
    path = path or WIRING
    out: list[StagingPin] = []
    bad: list[str] = []
    for w in wiring_rows(path, STAGING_NAMES, files):
        if w.kind != "detector" or w.level != STAGING:
            continue
        if w.node not in nodes:
            bad.append(f"line {w.line}: node {w.node} is no staging node of {NODES.name} "
                       f"({', '.join(map(str, sorted(nodes)))})")
            continue
        out.append(StagingPin(w.line, w.device, w.node, w.lcos_index - 1, w.id.removeprefix("det:")))
    if bad:
        raise MapError(f"{path.name}: " + "; ".join(bad))
    return out


HELIX_ID = re.compile(r"det:block:(?P<label>\d+[A-Z]?)[A-D]-helix")     # a main or upper helix track's detector


def helix_pins(path: Path | None = None, helix_map: Mapping[str, str] | None = None) -> dict[str, Pin]:
    """{staging helix block id: (node, input index from 0)} of wiring.csv's main and upper detector rows on a helix
    track (det:block:<switch label><leg>-helix): a helix block's staging row names the detector its main or upper row
    has. The main or upper switch label finds the staging block in `helix_map` (plan_overrides.json main_upper's
    `helix`: {"131A": "block:39B-helix"}; default the one beside `path`'s data folder, else the committed one), by
    ID, so a renamed helix track keeps its
    detector. Stops on a helix row whose switch the map does not have."""
    if helix_map is None:
        beside = Path(path).parent / "schematic" if path else pd.DATA      # a copy's own plan overrides
        folder = beside if layer_files.path("plan_overrides", beside).is_file() else pd.DATA
        helix_map = layer_files.read("plan_overrides", "main_upper", folder).get("helix", {})
    out: dict[str, Pin] = {}
    bad: list[str] = []
    for w in wiring_rows(path, STAGING_NAMES):
        if w.kind != "detector" or w.level == STAGING or not w.id.startswith("det:block:"):
            continue
        m = HELIX_ID.fullmatch(w.id)
        if not m:
            continue
        if m.group("label") not in helix_map:
            bad.append(f"line {w.line}: {w.id} is on helix switch {m.group('label')}, which the helix map "
                       f"({', '.join(sorted(helix_map))}) does not have")
            continue
        out[helix_map[m.group("label")]] = (w.node, w.lcos_index - 1)
    if bad:
        raise MapError(f"{(path or WIRING).name}: " + "; ".join(bad))
    return out


def loop_placeholder(placeholder: str, half: int | None) -> str:
    """The block name of one half of a balloon loop or split track ("Track 107 Loop" -> "Track 107 Loop 1", as
    block_layer.half_name); any other track's is unchanged."""
    return placeholder if half is None else f"{placeholder} {half}"


def frozen_wires(path: Path | None = None) -> list[wiring.Wire]:
    """wiring.csv's turnout, fb and head rows of main and upper: the devices of a control point wired and frozen
    (freeze_wiring.py), which the rule gives the same values again (Nodes.freeze). One helper tells what wiring.csv
    holds: hartlib.wiring.held."""
    return wiring.held(wires=wiring_rows(path)).devices


class Places(NamedTuple):
    """Where a line block sits: `of` {switch: its places}, a switch's places the stations of
    stations.csv that list it, or, for a switch in no station, the control points of interlockings.csv that list it;
    `order` {place: rank}, stations.csv's order then interlockings.csv's; `level` {place: its level}; `tracks`
    {block name: the stations whose `tracks` cell gives its block ID} (the owner's additions; the name the store's,
    railroad.station_tracks)."""
    of: dict[str, tuple[str, ...]]
    order: dict[str, int]
    level: dict[str, int]
    tracks: dict[str, list[str]]


def read_places(stations: Path | None = None, interlockings: Path | None = None) -> Places:
    """Places of stations.csv (`stations`, default the committed file) and interlockings.csv (`interlockings`,
    default CPS). MapError when either cannot be read."""
    try:
        st = railroad.read_stations(stations or STATIONS)
        ils = railroad.read_interlockings(interlockings or CPS)
    except railroad.FactsError as exc:
        raise MapError(str(exc)) from exc
    order: dict[str, int] = {}
    level: dict[str, int] = {}
    for name, lv in [(s.name, s.level) for s in st] + [(i.name, i.level) for i in ils]:
        order.setdefault(name, len(order))
        if level.setdefault(name, lv) != lv:
            raise MapError(f"{name} is a station or control point of levels {level[name]} and {lv}; a place is on "
                           "one level")
    in_station: defaultdict[str, list[str]] = defaultdict(list)
    in_cp: defaultdict[str, list[str]] = defaultdict(list)
    tracks: defaultdict[str, list[str]] = defaultdict(list)
    try:
        named = railroad.station_tracks(st, stations or STATIONS)   # the `tracks` IDs' names, from the name store
    except railroad.FactsError as exc:
        raise MapError(str(exc)) from exc
    for s in st:
        for sw in s.switches:
            in_station[sw].append(s.name)
        for t in named.get(s.name, ()):
            tracks[t].append(s.name)
    for i in ils:
        for sw in i.switches:
            in_cp[sw].append(i.name)
    return Places({sw: tuple(in_station[sw] or in_cp[sw]) for sw in set(in_station) | set(in_cp)}, order, level,
                  dict(tracks))
