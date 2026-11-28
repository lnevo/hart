"""The name store of the tracks (ADR-033 decision 2): the owner's track names, keyed by device
ID, and how they reach the schematic plugin.

    track_names.owner_names()                      {(level, block id): name}: the owner's track names
    track_names.plugin_section(sheet, section)     a plan_overrides section with the plugin's `name` and `end` edits
    track_names.hand_problems(section)             why a hand section still holds a name (a check)
    track_names.piece_names(section, pieces)       {drawn piece ("37C-39C #2"): name}: what the readers by ID take
    track_names.end_key(node, port), edge_run(...) a plan graph end's and edge's run key (plan_runs, build_main_route)
    track_names.repo_inputs(data)                  a test's opt-in to the repo's plan graphs and device files
    track_names.names_by_id(ids)                   {block id: "Track S-1"}: preferences.json's and stations.csv's
    track_names.pref_section(sheet, section)       a preferences section with its track keys' IDs named
    track_names.pref_problems(section)             why a hand preferences section names a track (a check)

The owner names a track in devices_field.csv: a block row with an `id` (hartlib.device_ids.block_id, "block:17C-29C")
and its user name ("Track S-1"). That row is the only place the name is kept. plan_overrides.json holds no track
name: its `end` edit says what each track end is ([switch, leg, kind, to]: a bumper, or the helix and the level it
climbs to), `left_end` is the ID of the track drawn at the left end and main_upper's `helix` map gives each helix
top switch the ID of its staging helix track (block:39B-helix); the plugin's `name` edit, the names in its `end` edit,
its `left_end` and its `helix` names are made here from the store, when hartlib.layer_files.view writes the folder the
plugin reads. A renamed track is one edited user name; nothing in plan_overrides.json changes.

A block ID comes from the plan: each end of its track is the switch label (after the `relabel` edit) and leg it ends
at, or "end" (a bumper) or "helix" (staging_device_map.end_key, plan_tracks.end_leg), so a track is found in the AnyRail
plan graph (inputs/<graph>.json) with no drawing. The pieces of a run the drawing parts at a turnback ("#1", "#2",
from the lower end) are named in order: one name for every piece is one plan name, different names a list (the
owner's split, K-1 and K-2). The `main` flags of the `name` edit are build_main_route.py's (plan_generated.json
`name_main`, the runs of the staging main lines): a run on a main line gets an entry even when it has no name.

Generated names (the end-switch rule, "Track 17-19") are not drawn on the schematic, so they are not written here:
block_layer.name_tracks makes them from the plan's track ends (plan_tracks.plan_order for parallel tracks).

The readers by ID: block_layer (name_tracks, the halves), cats_panel.py, device_map_masts.py and
staging_device_map.check_helix take a drawn strand's track name from piece_names, by the strand's ID part
(staging_device_map.band_refs, strand_names), not from the drawing. The store reads only the folder it is given: a
missing devices_field.csv or plan graph stops (a test whose copy holds only the layer files calls repo_inputs).

preferences.json and stations.csv name tracks by block ID too: the preferences' track keys
(_map_pref_tracks) are named in the merged view (hartlib.layer_files.merged, so the plugin's folder holds names), and
stations.csv's `tracks` cell by hartlib.railroad_facts.station_tracks; both through names_by_id.

TrackNameError names the file and row: an owner ID no plan track has, a name on part of a piece (":1/2"), a run whose
pieces are not all named, a `name` edit or a five-item `end` entry left in plan_overrides.json.
"""
from __future__ import annotations

import csv
import json
import re
from collections.abc import Callable, Collection, Iterable, Mapping
from pathlib import Path
from typing import Any

from . import paths
from .errors import FactsError, HartlibError

# A plan override section and the plan graph are JSON read as is: Any is their values' type (json.loads).
End = tuple[str, str, str]                   # a plan run end: (junction, leg, end key)
TrackFn = Callable[[Any, str, str], Any]     # _map_pref_tracks' fn(value, form, where): the value to keep

SCHEMATIC = paths.LAYOUT_DATA / "schematic"
PLAN_GRAPHS = {"staging": "inputs/staging.json", "main_upper": "inputs/main.json"}   # sheet -> its plan graph
FIELD_FILE = "devices_field.csv"            # beside the schematic folder (hartlib.devices.FIELD_FILE)
NAME_MAIN = "name_main"                     # plan_generated.json: the runs of the staging main lines
TRACK_PREFIX = "Track "
_STRAND = re.compile(r"(?P<run>[^#:+]+)(?:#(?P<piece>\d+))?(?::(?P<k>\d+)/(?P<n>\d+))?")
_END = re.compile(r"(\d+)([A-Z]?)([A-D])")


class TrackNameError(HartlibError, ValueError):
    """A plan graph, plan override section or name store that does not give a track its name."""


def end_order(key: str) -> tuple[int, int, str, str]:
    """The sort key of a track end key: a switch leg by its number, half letter and leg ("103AB" before "103BA"
    before "105B"), any other end ("end", "helix") after every switch leg, by its text."""
    m = _END.fullmatch(key)
    return (0, int(m.group(1)), m.group(2), m.group(3)) if m else (1, 0, "", key)


def relabel_map(section: Mapping[str, Any]) -> dict[str, str]:
    """{plan label: drawing label} of a plan override section's `relabel` edits, later edits over earlier ones."""
    out: dict[str, str] = {}
    for e in section.get("edits", ()):
        if e.get("op") == "relabel":
            out.update(e["map"])
    return out


def run_of(a: str, b: str) -> str:
    """The run key of a track between ends a and b ("37C", "39C", "end", "helix"): lower first, "37C-39C"."""
    lo, hi = sorted((a, b), key=end_order)
    return f"{lo}-{hi}"


def end_key(node: Mapping[str, Any], port: str, node_id: str = "", helix: bool | None = None) -> str:
    """A track end's key in a plan graph: at a junction (`node`, a graph node whose label is already relabelled) its
    label, else `node_id`, with a moved switch's star dropped, then the `port` the track leaves it by ("17C",
    "103AB"); at a track end "helix" (`helix`; default: the node's sub is helix) or "end". The one end key of
    plan_runs and build_main_route.staging_keys (staging_device_map.end_key gives the drawing's, the same keys)."""
    if node["kind"] != "end":
        return f"{(node.get('label') or node_id).rstrip('*')}{port}"
    if helix is None:
        helix = node.get("sub") == "helix"
    return "helix" if helix else "end"


def edge_run(nodes: Mapping[str, Any], edge: Mapping[str, Any], helix_ends: Collection[str] | None = None) -> str:
    """The run key (run_of) of plan graph edge `edge`, each end by end_key over `nodes` (the graph's, relabelled);
    `helix_ends`, the end nodes that are the helix (default: those whose sub is helix)."""
    def key(n: str, port: str) -> str:
        return end_key(nodes[n], port, n, None if helix_ends is None else n in helix_ends)
    return run_of(key(edge["u"], edge["up"]), key(edge["v"], edge["vp"]))


def _beside(data: Path, rel: str, what: str) -> Path:
    """`rel` under the folder `data`; TrackNameError when it is not there. The store reads only the folder it is
    given: a test whose copy of the schematic folder holds only the layer files opts in to the repo's plan graphs
    and devices_field.csv with repo_inputs."""
    p = Path(data) / rel
    if not p.exists():
        raise TrackNameError(f"{what} {p} is missing (the name store reads the plan graphs in the schematic folder it "
                             f"is given and {FIELD_FILE} beside it; a test's copy: hartlib.track_names.repo_inputs)")
    return p


def repo_inputs(data: Path) -> Path:
    """Copy the repo's plan graphs (inputs/<graph>.json) into the folder `data` and the repo's devices_field.csv and
    devices_generated.csv (the generated names of preferences.json's block IDs) beside it, each only where missing: the explicit opt-in of a test whose copy of the schematic folder holds only the
    layer files. Returns `data`."""
    import shutil
    data = Path(data)
    for rel in PLAN_GRAPHS.values():
        if not (data / rel).exists():
            (data / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SCHEMATIC / rel, data / rel)
    from . import devices
    for name in (FIELD_FILE, devices.GENERATED_FILE):   # the generated names of the IDs preferences.json gives
        if not (data.parent / name).exists():
            shutil.copyfile(SCHEMATIC.parent / name, data.parent / name)
    return data


def owner_names(data: Path = SCHEMATIC) -> dict[tuple[str, str], str]:
    """{(level, block id): name without "Track "} of every block row of devices_field.csv (beside `data`) whose id is a
    track's (block:...) and that gives a user name. Every field row is keyed by its id, so
    an OS block's row (os:...) is there too and is no track. TrackNameError on a missing file or a track name not
    "Track <name>"."""
    path = _beside(Path(data).parent, FIELD_FILE, "the owner's rows")
    out, bad = {}, []
    with path.open(newline="", encoding="utf-8") as fh:
        for i, r in enumerate(csv.DictReader(fh), 2):
            rid = (r.get("id") or "").strip()
            name = r.get("user_name") or ""
            if not rid.startswith("block:") or r.get("layer") != "block" or not name:
                continue
            if not name.startswith(TRACK_PREFIX) or not name[len(TRACK_PREFIX):].strip():
                bad.append(f"line {i}: block {rid} is named {name!r}, not \"Track <name>\"")
            else:
                out[(r["level"], rid)] = name[len(TRACK_PREFIX):]
    if bad:
        raise TrackNameError(f"{path.name}: " + "; ".join(bad))
    return out


def section_levels(section: Mapping[str, Any]) -> set[str]:
    """The levels a plan_overrides section draws: its `level` (one band) or its levels.bands entries' levels."""
    bands = section.get("levels", {}).get("bands", ())
    got = {b.get("level") for b in bands} if bands else {section.get("level")}
    return {str(lv) for lv in got if lv is not None}


def plan_runs(sheet: str, section: Mapping[str, Any], data: Path = SCHEMATIC) -> dict[str, list[tuple[End, End]]]:
    """{run key: [((junction, leg, end key), (junction, leg, end key)), lower end first]} of every track of the
    sheet's plan graph, its switches labelled by the section's `relabel` edit and its ends by the section's `end`
    edit (a helix end: "helix") and `helix` map. A run two tracks share lists both."""
    graph = json.loads(_beside(data, PLAN_GRAPHS[sheet], "the plan graph").read_text(encoding="utf-8"))
    relabel = relabel_map(section)
    nodes = graph["nodes"]
    label = {n: relabel.get(d.get("label") or n, d.get("label") or n) for n, d in nodes.items() if d["kind"] != "end"}
    by_label: dict[str, list[str]] = {}
    for n, lb in label.items():
        by_label.setdefault(lb.rstrip("*"), []).append(n)
    helix_ends = set()
    for e in section.get("edits", ()):
        if e.get("op") == "end":
            for ref, port, *rest in e["ends"]:
                kind = rest[-2] if len(rest) >= 2 else ""
                if kind == "helix":
                    for n in by_label.get(str(ref), ()):
                        helix_ends |= {_far(graph, n, port)}
    for ref in section.get("helix", {}):
        for n in by_label.get(relabel.get(ref, ref), ()):
            ends = [(ed, ed["v"] if ed["u"] == n else ed["u"]) for ed in graph["edges"] if n in (ed["u"], ed["v"])]
            ends = [(ed, m) for ed, m in ends if nodes[m]["kind"] == "end"]
            if ends:
                helix_ends.add(max(ends, key=lambda t: t[0]["cm"])[1])

    def key(n: str, port: str) -> str:
        return end_key({**nodes[n], "label": label.get(n)}, port, n, helix=n in helix_ends)

    out: dict[str, list[tuple[tuple[str, str, str], tuple[str, str, str]]]] = {}
    for ed in graph["edges"]:
        a, b = (ed["u"], ed["up"], key(ed["u"], ed["up"])), (ed["v"], ed["vp"], key(ed["v"], ed["vp"]))
        lo, hi = sorted((a, b), key=lambda end: end_order(end[2]))
        out.setdefault(run_of(a[2], b[2]), []).append((lo, hi))
    return out


def plan_switches(sheet: str, section: Mapping[str, Any], data: Path = SCHEMATIC) -> dict[str, list[str]]:
    """{switch number: its labels, sorted} of the switches of the sheet's plan graph, each labelled by the section's
    `relabel` edit (a crossover's halves share a number: "7", "7"; a moved switch keeps its star, "223*", in its
    label, not its number): the switches the plan has, with no drawing (staging's turnouts from
    the plan, not from the owner's rows). TrackNameError on a switch the relabel edit gives no number."""
    graph = json.loads(_beside(data, PLAN_GRAPHS[sheet], "the plan graph").read_text(encoding="utf-8"))
    relabel = relabel_map(section)
    out: dict[str, list[str]] = {}
    for n, d in graph["nodes"].items():
        if d["kind"] == "end":
            continue
        label = relabel.get(d.get("label") or n, d.get("label") or n)
        m = re.match(r"\d+", label)
        if not m:
            raise TrackNameError(f"{PLAN_GRAPHS[sheet]}: switch {n} ({d.get('label')}) has label {label!r}, no switch "
                                 "number (the section's relabel edit gives each plan switch its number)")
        out.setdefault(m.group(0), []).append(label)
    return {k: sorted(v) for k, v in sorted(out.items(), key=lambda kv: int(kv[0]))}


def _far(graph: Mapping[str, Any], n: str, port: str) -> str | None:
    for ed in graph["edges"]:
        if (ed["u"], ed["up"]) == (n, port):
            return str(ed["v"])
        if (ed["v"], ed["vp"]) == (n, port):
            return str(ed["u"])
    return None


def hand_problems(section: Mapping[str, Any]) -> list[str]:
    """Why a hand plan_overrides section holds a track name (the name store holds them all): a `name` edit, an `end`
    entry with a name ([switch, leg, kind, to] has four items), or a `left_end` that is not a block ID."""
    bad = []
    for e in section.get("edits", ()):
        if e.get("op") == "name":
            bad.append("a `name` edit (track names are the owner's block rows in devices_field.csv, by id)")
        if e.get("op") == "end":
            long = [x for x in e.get("ends", ()) if len(x) != 4]
            if long:
                bad.append(f"`end` entries {long} are not [switch, leg, kind, to] (a track end's name is its block "
                           "row's in devices_field.csv)")
    left = section.get("left_end")
    if left is not None and not str(left).startswith("block:"):
        bad.append(f"left_end {left!r} is not a block ID (block:...)")
    named = {k: v for k, v in section.get("helix", {}).items() if not str(v).startswith("block:")}
    if named:
        bad.append(f"helix {named} gives names, not the block IDs of the staging helix tracks (block:39B-helix)")
    return bad


def _names_of_runs(owner: Mapping[tuple[str, str], str], levels: set[str]) -> dict[str, str | list[str]]:
    """{run: name, or names by piece from the lower end} of the owner's names on `levels`: one name when the run is
    named whole or every piece from #1 has that name, else the list. TrackNameError on a run named whole and by
    piece, or whose named pieces do not run from #1 with no gap."""
    out = {}
    for run, by in _pieces_of_runs(owner, levels).items():
        names = [by[p] for p in sorted(by)]
        out[run] = names[0] if 0 in by or len(set(names)) == 1 else names
    return out


def _pieces_of_runs(owner: Mapping[tuple[str, str], str], levels: set[str]) -> dict[str, dict[int, str]]:
    """{run: {piece: name}} of the owner's names on `levels` (piece 0: the run named whole), checked: no run named
    whole and by piece, and named pieces from #1 with no gap (TrackNameError)."""
    pieces: dict[str, dict[int, str]] = {}
    bad = []
    for (level, bid), name in sorted(owner.items()):
        if level not in levels:
            continue
        for strand in bid.removeprefix("block:").split("+"):
            m = _STRAND.fullmatch(strand)
            if not m or m.group("k"):
                bad.append(f"block {bid} ({name}): a name on part of a piece ({strand}) is not drawn; name the "
                           "whole track")
                continue
            got = pieces.setdefault(m.group("run"), {})
            p = int(m.group("piece") or 0)
            if got.setdefault(p, name) != name:
                bad.append(f"run {m.group('run')} piece {p} is named {got[p]!r} and {name!r}")
    for run, by in pieces.items():
        if 0 in by and len(by) > 1:
            bad.append(f"run {run} is named whole and by piece")
        elif 0 not in by and sorted(by) != list(range(1, len(by) + 1)):
            bad.append(f"run {run}: pieces {sorted(by)} are named, not every piece from #1")
    if bad:
        raise TrackNameError(f"{FIELD_FILE}: " + "; ".join(bad))
    return pieces


HELIX_END = "-helix"


def piece_names(section: Mapping[str, Any], pieces: Iterable[str], owner: Mapping[tuple[str, str], str] | None = None,
                data: Path = SCHEMATIC) -> dict[str, str]:
    """{piece: name without "Track "} of each drawn piece of `pieces` (staging_device_map.band_refs' piece
    references: "17C-29C", "37C-39C #2", the ID parts of a block ID) that the store names, for a hand plan_overrides
    section (its `helix` map holding block IDs): a run the owner names whole gives each of its pieces that name, a
    run named by piece its i-th piece the i-th name (owner_names on the section's levels; `owner` in its shape); a
    track up the helix from a switch of the section's `helix` map ("131AA-helix") the name of the staging helix block
    the map gives it. The readers by ID (block_layer, cats_panel, device_map_masts, staging_device_map) take a strand's
    name from here, not from the drawing. TrackNameError on a helix entry with no named block row or with more than
    one drawn track up the helix from its switch, or a drawn piece of a run named by piece that has no name of its
    own (a name is never spread to a piece the owner did not name)."""
    owner = owner_names(data) if owner is None else owner
    named = _pieces_of_runs(owner, section_levels(section))
    any_level = {bid: name for (_level, bid), name in owner.items()}     # a helix track is staging's block
    relabel = relabel_map(section)
    helix, bad = {}, []
    for ref, bid in section.get("helix", {}).items():
        if bid not in any_level:
            bad.append(f"helix {ref}: {bid} has no named block row in {FIELD_FILE}")
        else:
            helix[str(relabel.get(ref, ref)).rstrip("*")] = any_level[bid]
    out: dict[str, str] = {}
    up: dict[str, set[str]] = {}
    for piece in sorted(set(pieces)):
        run, _sep, i = piece.partition(" #")
        by = named.get(run)
        if by:
            got = by[0] if 0 in by else by.get(int(i)) if i else None
            if got is None:
                given = ", ".join(f"#{p} {n}" for p, n in sorted(by.items()))
                bad.append(f"piece {piece}: its run is named by piece ({given}), and this piece has no name of its own")
                continue
            out[piece] = got
        elif run.endswith(HELIX_END):
            label = run.removesuffix(HELIX_END)[:-1]                   # the end key less its leg: the switch label
            if label in helix:
                up.setdefault(label, set()).add(run)
                out[piece] = helix[label]
    for label, runs in sorted(up.items()):
        if len(runs) > 1:
            bad.append(f"helix track from switch {label}: {len(runs)} drawn tracks run up the helix from it "
                       f"({', '.join(sorted(runs))}); the `helix` map names one")
    if bad:
        raise TrackNameError("; ".join(bad))
    return out


def plugin_section(sheet: str, section: Mapping[str, Any], main_runs: Iterable[str] = (),
                   owner: Mapping[tuple[str, str], str] | None = None, data: Path = SCHEMATIC) -> Mapping[str, Any]:
    """`section` (a merged plan_overrides section) as the plugin reads it: a `name` edit after `relabel` naming every
    run the owner names (owner_names on the section's levels) and every run of `main_runs` (flagged main), each by
    its plan junction ids and the leg it leaves the lower end by; each `end` entry's name (its block row's: a bumper's
    block:<switch><leg>-end, a helix end's block:<switch><leg>-helix) put in third place; `left_end` the name of the
    block it gives. A section with no owner names and no main runs is returned as it is; one that draws no level
    and has nothing to fill is returned without reading the store."""
    bad = hand_problems(section)
    if bad:
        raise TrackNameError(f"plan_overrides.json[{sheet}]: " + "; ".join(bad))
    main_runs = list(main_runs)
    if not all(isinstance(r, str) for r in main_runs):
        raise TrackNameError(f"plan_generated.json[{sheet}] {NAME_MAIN} holds {main_runs[:3]}..., not runs "
                             "(\"1A-23A\"): run python3 tools/schematic/build_main_route.py")
    levels = section_levels(section)
    has_end = any(e.get("op") == "end" for e in section.get("edits", ()))
    fills = main_runs or has_end or "left_end" in section or section.get("helix")
    if not levels and not fills:
        return section
    owner = owner_names(data) if owner is None else owner
    names = _names_of_runs(owner, levels)
    by_id = {bid: name for (level, bid), name in owner.items() if level in levels}
    any_level = {bid: name for (_level, bid), name in owner.items()}     # a helix track is staging's block
    if not names and not fills:
        return section
    runs = plan_runs(sheet, section, data)
    out: dict[str, Any] = json.loads(json.dumps(section))
    tracks, bad = [], []
    for run in list(dict.fromkeys([*names, *main_runs])):
        if run.endswith(("-end", "-helix")):
            if run in main_runs and run.endswith("-end"):
                bad.append(f"run {run}: a main line ends at a bumper, which no `name` entry can flag")
            continue                    # its name goes on its `end` entry; the plugin marks a helix track main
        hits = runs.get(run, [])
        if len(hits) != 1:
            bad.append(f"run {run}: {len(hits) or 'no'} plan tracks run there")
            continue
        (first, leg, _k), (second, _leg, _k2) = hits[0]
        entry = [first, second, names.get(run, ""), leg]
        if run in main_runs:
            entry.append("main")
        tracks.append(entry)
    ends_done = set()
    for e in out.get("edits", ()):
        if e.get("op") != "end":
            continue
        filled = []
        for ref, port, kind, to in e["ends"]:
            bid = f"block:{ref}{port}-{'helix' if kind == 'helix' else 'end'}"
            if bid not in by_id:
                bad.append(f"the {kind} at Switch {ref} leg {port} has no named block row {bid} in {FIELD_FILE}")
                continue
            ends_done.add(bid)
            filled.append([ref, port, by_id[bid], kind, to])
        e["ends"] = filled
    for ref, bid in out.get("helix", {}).items():
        if bid not in any_level:
            bad.append(f"helix {ref}: {bid} has no named block row in {FIELD_FILE}")
        else:
            out["helix"][ref] = any_level[bid]
    if "left_end" in out:
        bid = out["left_end"]
        if bid not in by_id:
            bad.append(f"left_end {bid} has no named block row in {FIELD_FILE}")
        else:
            out["left_end"] = by_id[bid]
    # a named track end the `end` edit does not list would not be drawn: checked where the section has an `end` edit
    lost = sorted(bid for bid in by_id if has_end and bid.endswith(("-end", "-helix")) and bid not in ends_done)
    if lost:
        bad.append(f"track ends {lost} are named in {FIELD_FILE} but have no `end` entry in plan_overrides.json")
    if bad:
        raise TrackNameError(f"{sheet}: " + "; ".join(bad))
    if tracks:
        edits = out.setdefault("edits", [])
        at = next((i + 1 for i, e in enumerate(edits) if e.get("op") == "relabel"), 0)
        edits.insert(at, {"op": "name", "tracks": tracks})
    return out


# ---------------------------------------------------------------- tracks named by ID in the other hand files

BLOCK_PREFIX = "block:"
WHOLE, BARE = "whole", "bare"      # how a plugin key names a track: "Track S-1" (whole) or "S-1" (bare)
LABEL_KEYS = SCHEMATIC / "label_track_keys.csv"
LABEL_KEY_COLUMNS = ["key", "depth", "form", "notes"]


def label_track_keys(path: Path = LABEL_KEYS) -> dict[str, tuple[int, str]]:
    """{option: (depth, form)} of label_track_keys.csv: the label options (le_labels, and each band's in
    le_band_labels) that list tracks, depth 1 a list of tracks and 2 a list of lists, form WHOLE or BARE.
    TrackNameError naming the file and line on a missing column or cell, a key given twice, or a depth or form not
    one of those."""
    from .railroad_facts import read_rows     # railroad_facts imports this module, so not at the top
    try:
        rows = read_rows(path, LABEL_KEY_COLUMNS)
    except FactsError as exc:
        raise TrackNameError(str(exc)) from exc
    out: dict[str, tuple[int, str]] = {}
    for n, r in rows:
        key, depth, form = r["key"], r["depth"], r["form"]
        if not key or key in out:
            raise TrackNameError(f"{path.name} line {n}: key {key!r} is empty or given twice")
        if depth not in ("1", "2") or form not in (WHOLE, BARE):
            raise TrackNameError(f"{path.name} line {n}: {key}: depth must be 1 or 2 and form {WHOLE} or {BARE}, "
                                 f"not {depth!r} and {form!r}")
        out[key] = (int(depth), form)
    return out

STOP, KEEP = "stop", "keep"        # names_by_id: what an ID with no name does


def names_by_id(ids: Iterable[str], data: Path = SCHEMATIC, where: str = "", levels: Collection[str] | None = None,
                missing: str = STOP) -> dict[str, str]:
    """{block id: its track name, "Track S-1"} of each of `ids` on `levels` (a set of level numbers as text; None:
    any level): the owner's (owner_names), else the generated name of its row in devices_generated.csv beside
    `data`, which is read only when an ID has no owner's name. A block ID is unique on its level only, so an ID that
    two of `levels` have is a clash. TrackNameError naming `where` on a clash, or on an ID that is no block of
    either file (a new export dropped it, or it is mistyped: decision 3) when `missing` is STOP; with KEEP such an
    ID is left out of the answer (the caller keeps it as it is: the device-map step has not written its row yet).

    The generated names are the device-map step's output: a step before it reads the last build's, which can only
    differ for a block whose generated name changed, and none of those steps reads the keys that hold such names
    (the Layout Editor's label options); hartlib.layer_files.unnamed_preferences, which the device-master check
    runs after device-map, stops on an ID still unnamed."""
    from . import devices                  # devices imports railroad_facts, which imports layer_files and so this
    want = set(ids)
    if not want:
        return {}
    levels = None if levels is None else {str(lv) for lv in levels}
    got: dict[str, dict[str, str]] = {}            # id -> {level: name}
    for (level, bid), name in owner_names(data).items():
        if bid in want and (levels is None or level in levels):
            got.setdefault(bid, {})[level] = TRACK_PREFIX + name
    rest = want - set(got)
    if rest:
        gen = _beside(Path(data).parent, devices.GENERATED_FILE, "the generated device rows")
        with gen.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                lv = r.get("level") or ""
                if (r.get("id") in rest and lv and (levels is None or lv in levels) and r.get("layer") == "block"
                        and r.get("user_name")):
                    got.setdefault(r["id"], {}).setdefault(lv, r["user_name"])
    on = f" on level {'/'.join(sorted(levels))}" if levels else ""
    bad = []
    if missing == STOP:
        bad += [f"{bid} is no block{on} of {FIELD_FILE} or {devices.GENERATED_FILE} (a new export dropped it, or it "
                "is mistyped: give the block's id)" for bid in sorted(want - set(got))]
    bad += [f"{bid} is a block of levels {' and '.join(sorted(by))} ({', '.join(by[lv] for lv in sorted(by))}): "
            "name one level's" for bid, by in sorted(got.items()) if len(by) > 1]
    if bad:
        raise TrackNameError((f"{where}: " if where else "") + "; ".join(bad))
    return {bid: next(iter(by.values())) for bid, by in got.items()}


def _map_pref_tracks(section: Mapping[str, Any], fn: TrackFn, shapes: list[str] | None = None) -> dict[str, Any]:
    """A copy of the preferences section `section` with each track it names put through fn(value, form, where):
    min_cells' track names (an entry's items after [from, to, cells]), turnbacks, track_labels' keys, and the
    label_track_keys() of le_labels and of each band of le_band_labels. A track key of the wrong shape (a list where a
    list of lists goes, a string where a list goes) is left as it is and named in `shapes` when given. TrackNameError
    on two track_labels keys that come out as one."""
    out: dict[str, Any] = json.loads(json.dumps(section))
    shapes = [] if shapes is None else shapes

    def bad_shape(text: str, value: Any) -> Any:
        shapes.append(text)
        return value

    def each(values: Any, form: str, where: str) -> Any:
        if not isinstance(values, list):
            shapes.append(f"{where} is {values!r}, not a list of tracks")
            return values
        return [fn(v, form, f"{where}[{i}]") for i, v in enumerate(values)]

    cells = out.get("min_cells")
    for i, entry in enumerate(cells if isinstance(cells, list) else ()):
        if isinstance(entry, list) and len(entry) > 3:
            entry[3:] = [fn(v, BARE, f"min_cells[{i}][{3 + j}]") for j, v in enumerate(entry[3:])]
    if "turnbacks" in out:
        out["turnbacks"] = each(out["turnbacks"], BARE, "turnbacks")
    labels = out.get("track_labels")
    if isinstance(labels, dict):
        mapped: dict = {}
        for k, v in labels.items():
            key = fn(k, BARE, f"track_labels key {k!r}")
            if key in mapped:
                raise TrackNameError(f"track_labels keys {mapped[key][0]!r} and {k!r} are both {key!r}: give each "
                                     "track one label")
            mapped[key] = (k, v)
        out["track_labels"] = {key: v for key, (_k, v) in mapped.items()}
    elif labels is not None:
        shapes.append(f"track_labels is {labels!r}, not an object of track to label")
    holders = [("le_labels", out.get("le_labels"))]
    if isinstance(out.get("le_band_labels"), dict):
        holders += [(f"le_band_labels.{band}", d) for band, d in out["le_band_labels"].items()]
    for where, d in holders:
        if not isinstance(d, dict):
            continue
        for key, (depth, form) in label_track_keys().items():
            if key not in d:
                continue
            if depth == 1:
                d[key] = each(d[key], form, f"{where}.{key}")
            elif not isinstance(d[key], list):
                shapes.append(f"{where}.{key} is {d[key]!r}, not a list of lists of tracks")
            else:
                d[key] = [each(g, form, f"{where}.{key}[{i}]") if isinstance(g, list)
                          else bad_shape(f"{where}.{key}[{i}] is {g!r}, not a list of tracks", g)
                          for i, g in enumerate(d[key])]
    return out


def pref_problems(section: Mapping[str, Any]) -> list[str]:
    """Why a hand preferences section names a track (the name store holds every name): a track key (min_cells,
    turnbacks, track_labels, the label options' track lists: _map_pref_tracks) holding anything but a block ID or of
    the wrong shape, two track_labels keys for one track, or a "Track ..." string anywhere else outside a note (a key
    starting with _)."""
    bad: list[str] = []
    slots: set[str] = set()

    def check(v: Any, _form: str, where: str) -> Any:
        slots.add(where)
        if not (isinstance(v, str) and v.startswith(BLOCK_PREFIX)):
            bad.append(f"{where} is {v!r}, not a block ID (block:...; the track's name is its row's in {FIELD_FILE})")
        return v

    def scan(v: Any, where: str) -> None:
        if where in slots:
            return
        if isinstance(v, str) and v.startswith(TRACK_PREFIX):
            bad.append(f"{where} names {v!r} (a track is named by its block ID, its name kept in {FIELD_FILE})")
        elif isinstance(v, dict):
            for k, x in v.items():
                if not str(k).startswith("_"):
                    scan(k, f"{where} key {k!r}" if where else f"key {k!r}")
                    scan(x, f"{where}.{k}" if where else str(k))
        elif isinstance(v, list):
            for i, x in enumerate(v):
                scan(x, f"{where}[{i}]")

    shapes: list[str] = []
    try:
        _map_pref_tracks(section, check, shapes)
    except TrackNameError as exc:
        bad.append(str(exc))
    bad += shapes
    scan(section, "")
    return bad


def pref_ids(section: Mapping[str, Any]) -> set[str]:
    """The block IDs a preferences section names in its track keys (_map_pref_tracks)."""
    got: set[str] = set()

    def note(v: Any, _form: str, _where: str) -> Any:
        if isinstance(v, str) and v.startswith(BLOCK_PREFIX):
            got.add(v)
        return v
    _map_pref_tracks(section, note)
    return got


def pref_levels(sheet: str, data: Path = SCHEMATIC) -> set[str]:
    """The levels whose blocks a preferences section `sheet` names: the levels its plan_overrides section draws
    (section_levels; plan_overrides.json in `data`)."""
    from . import layer_files              # layer_files imports this module
    return section_levels(layer_files.read("plan_overrides", sheet, data))


def pref_section(sheet: str, section: Mapping[str, Any], names: Mapping[str, str] | None = None,
                 data: Path = SCHEMATIC, levels: Collection[str] | None = None,
                 missing: str = STOP) -> Mapping[str, Any]:
    """`section` (a merged preferences section) as the plugin reads it: each block ID of its track keys
    (_map_pref_tracks) put back as the track's name in the form the key takes ("Track S-1" or "S-1"), from `names`
    ({id: "Track <name>"}; else names_by_id of the folder `data` on `levels`, default the sheet's (pref_levels), but
    track_labels on every level: the plugin reads it sheet-wide, and its keys are staging's helix blocks). With
    `missing` KEEP an ID with no name is left as it is (names_by_id). A section that names no ID is returned as it is,
    without reading the store. TrackNameError naming preferences.json[sheet] and the key."""
    ids = pref_ids(section)
    if not ids:
        return section
    where = f"preferences.json[{sheet}]"
    if names is None:
        levels = pref_levels(sheet, data) if levels is None else levels
        labels = set(pref_ids({"track_labels": section.get("track_labels", {})}))
        names = {**names_by_id(ids - labels, data, where, levels, missing),
                 **names_by_id(labels, data, f"{where} track_labels", None, missing)}
    bad: list[str] = []

    def put(v: Any, form: str, at: str) -> Any:
        if not (isinstance(v, str) and v.startswith(BLOCK_PREFIX)):
            return v
        name = names.get(v)
        if name is None:
            if missing != KEEP:
                bad.append(f"{at}: {v} has no name")
            return v
        if form == WHOLE:
            return name
        if not name.startswith(TRACK_PREFIX):
            bad.append(f"{at}: {v} is named {name!r}, not \"Track <name>\"")
            return v
        return name[len(TRACK_PREFIX):]

    try:
        out = _map_pref_tracks(section, put)
    except TrackNameError as exc:
        raise TrackNameError(f"{where}: {exc}") from exc
    if bad:
        raise TrackNameError(f"{where}: " + "; ".join(bad))
    return out
