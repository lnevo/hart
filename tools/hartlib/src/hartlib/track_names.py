"""The name store of the tracks (ADR-033 decision 2, naming-layers step 3): the owner's track names, keyed by device
ID, and how they reach the schematic plugin.

    track_names.owner_names()                      {(level, block id): name}: the owner's track names
    track_names.plugin_section(sheet, section)     a plan_overrides section with the plugin's `name` and `end` edits
    track_names.hand_problems(section)             why a hand section still holds a name (a check)
    track_names.piece_names(section, pieces)       {drawn piece ("37C-39C #2"): name}: what the readers by ID take
    track_names.end_key(node, port), edge_run(...) a plan graph end's and edge's run key (plan_runs, build_main_route)
    track_names.repo_inputs(data)                  a test's opt-in to the repo's plan graphs and field file

The owner names a track in devices_field.csv: a block row with an `id` (hartlib.device_ids.block_id, "block:17C-29C")
and its user name ("Track S-1"). That row is the only place the name is kept. plan_overrides.json holds no track
name: its `end` edit says what each track end is ([switch, leg, kind, to]: a bumper, or the helix and the level it
climbs to), `left_end` is the ID of the track drawn at the left end and main_upper's `helix` map gives each helix
top switch the ID of its staging helix track (block:39B-helix); the plugin's `name` edit, the names in its `end` edit,
its `left_end` and its `helix` names are made here from the store, when hartlib.layer_files.view writes the folder the
plugin reads. A renamed track is one edited user name; nothing in plan_overrides.json changes.

A block ID comes from the plan: each end of its track is the switch label (after the `relabel` edit) and leg it ends
at, or "end" (a bumper) or "helix" (staging_device_map.end_key, mast_rule.end_leg), so a track is found in the AnyRail
plan graph (inputs/<graph>.json) with no drawing. The pieces of a run the drawing parts at a turnback ("#1", "#2",
from the lower end) are named in order: one name for every piece is one plan name, different names a list (the
owner's split, K-1 and K-2). The `main` flags of the `name` edit are build_main_route.py's (plan_generated.json
`name_main`, the runs of the staging main lines): a run on a main line gets an entry even when it has no name.

Generated names (the end-switch rule, "Track 17-19") are not drawn on the schematic, so they are not written here:
block_layer.name_tracks makes them from the plan's track ends (mast_rule.plan_order for parallel tracks).

The readers by ID (naming-layers step 3b): block_layer (name_tracks, the halves), cats_panel.py, build_masts.py and
staging_device_map.check_helix take a drawn strand's track name from piece_names, by the strand's ID part
(staging_device_map.band_refs, strand_names), not from the drawing. The store reads only the folder it is given: a
missing devices_field.csv or plan graph stops (a test whose copy holds only the layer files calls repo_inputs).

TrackNameError names the file and row: an owner ID no plan track has, a name on part of a piece (":1/2"), a run whose
pieces are not all named, a `name` edit or a five-item `end` entry left in plan_overrides.json.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from . import paths

SCHEMATIC = paths.LAYOUT_DATA / "schematic"
PLAN_GRAPHS = {"staging": "inputs/staging.json", "main_upper": "inputs/main.json"}   # sheet -> its plan graph
FIELD_FILE = "devices_field.csv"            # beside the schematic folder (hartlib.devices.FIELD_FILE)
NAME_MAIN = "name_main"                     # plan_generated.json: the runs of the staging main lines
TRACK_PREFIX = "Track "
_STRAND = re.compile(r"(?P<run>[^#:+]+)(?:#(?P<piece>\d+))?(?::(?P<k>\d+)/(?P<n>\d+))?")
_END = re.compile(r"(\d+)([A-Z]?)([A-D])")


class TrackNameError(ValueError):
    pass


def _end_order(key: str):
    m = _END.fullmatch(key)
    return (0, int(m.group(1)), m.group(2), m.group(3)) if m else (1, 0, "", key)


def run_of(a: str, b: str) -> str:
    """The run key of a track between ends a and b ("37C", "39C", "end", "helix"): lower first, "37C-39C"."""
    lo, hi = sorted((a, b), key=_end_order)
    return f"{lo}-{hi}"


def end_key(node: dict, port: str, node_id: str = "", helix: bool | None = None) -> str:
    """A track end's key in a plan graph: at a junction (`node`, a graph node whose label is already relabelled) its
    label, else `node_id`, with a moved switch's star dropped, then the `port` the track leaves it by ("17C",
    "103AB"); at a track end "helix" (`helix`; default: the node's sub is helix) or "end". The one end key of
    plan_runs and build_main_route.staging_keys (staging_device_map.end_key gives the drawing's, the same keys)."""
    if node["kind"] != "end":
        return f"{(node.get('label') or node_id).rstrip('*')}{port}"
    if helix is None:
        helix = node.get("sub") == "helix"
    return "helix" if helix else "end"


def edge_run(nodes: dict, edge: dict, helix_ends=None) -> str:
    """The run key (run_of) of plan graph edge `edge`, each end by end_key over `nodes` (the graph's, relabelled);
    `helix_ends`, the end nodes that are the helix (default: those whose sub is helix)."""
    def key(n, port):
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
    """Copy the repo's plan graphs (inputs/<graph>.json) into the folder `data` and the repo's devices_field.csv beside
    it, each only where it is missing: the explicit opt-in of a test whose copy of the schematic folder holds only the
    layer files. Returns `data`."""
    import shutil
    data = Path(data)
    for rel in PLAN_GRAPHS.values():
        if not (data / rel).exists():
            (data / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SCHEMATIC / rel, data / rel)
    if not (data.parent / FIELD_FILE).exists():
        shutil.copyfile(SCHEMATIC.parent / FIELD_FILE, data.parent / FIELD_FILE)
    return data


def owner_names(data: Path = SCHEMATIC) -> dict[tuple[str, str], str]:
    """{(level, block id): name without "Track "} of every block row of devices_field.csv (beside `data`) that has an
    id. TrackNameError on a missing file, a row with an id that is not a block ID or a name not "Track <name>"."""
    path = _beside(Path(data).parent, FIELD_FILE, "the owner's rows")
    out, bad = {}, []
    with path.open(newline="", encoding="utf-8") as fh:
        for i, r in enumerate(csv.DictReader(fh), 2):
            rid = (r.get("id") or "").strip()
            if not rid or r.get("layer") != "block":
                continue
            name = r.get("user_name") or ""
            if not rid.startswith("block:"):
                bad.append(f"line {i}: id {rid!r} of block {name!r} is no track ID (block:...)")
            elif not name.startswith(TRACK_PREFIX) or not name[len(TRACK_PREFIX):].strip():
                bad.append(f"line {i}: block {rid} is named {name!r}, not \"Track <name>\"")
            else:
                out[(r["level"], rid)] = name[len(TRACK_PREFIX):]
    if bad:
        raise TrackNameError(f"{path.name}: " + "; ".join(bad))
    return out


def section_levels(section: dict) -> set[str]:
    """The levels a plan_overrides section draws: its `level` (one band) or its levels.bands entries' levels."""
    bands = section.get("levels", {}).get("bands", ())
    got = {b.get("level") for b in bands} if bands else {section.get("level")}
    return {str(lv) for lv in got if lv is not None}


def plan_runs(sheet: str, section: dict, data: Path = SCHEMATIC) -> dict[str, list[tuple[tuple, tuple]]]:
    """{run key: [((junction, leg, end key), (junction, leg, end key)), lower end first]} of every track of the
    sheet's plan graph, its switches labelled by the section's `relabel` edit and its ends by the section's `end`
    edit (a helix end: "helix") and `helix` map. A run two tracks share lists both."""
    graph = json.loads(_beside(data, PLAN_GRAPHS[sheet], "the plan graph").read_text(encoding="utf-8"))
    relabel = {}
    for e in section.get("edits", ()):
        if e.get("op") == "relabel":
            relabel.update(e["map"])
    nodes = graph["nodes"]
    label = {n: relabel.get(d.get("label") or n, d.get("label") or n) for n, d in nodes.items() if d["kind"] != "end"}
    by_label = {}
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

    def key(n, port):
        return end_key({**nodes[n], "label": label.get(n)}, port, n, helix=n in helix_ends)

    out = {}
    for ed in graph["edges"]:
        a, b = (ed["u"], ed["up"], key(ed["u"], ed["up"])), (ed["v"], ed["vp"], key(ed["v"], ed["vp"]))
        lo, hi = sorted((a, b), key=lambda end: _end_order(end[2]))
        out.setdefault(run_of(a[2], b[2]), []).append((lo, hi))
    return out


def _far(graph, n, port):
    for ed in graph["edges"]:
        if (ed["u"], ed["up"]) == (n, port):
            return ed["v"]
        if (ed["v"], ed["vp"]) == (n, port):
            return ed["u"]
    return None


def hand_problems(section: dict) -> list[str]:
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


def _names_of_runs(owner: dict, levels: set[str]) -> dict[str, str | list[str]]:
    """{run: name, or names by piece from the lower end} of the owner's names on `levels`: one name when the run is
    named whole or every piece from #1 has that name, else the list. TrackNameError on a run named whole and by
    piece, or whose named pieces do not run from #1 with no gap."""
    out = {}
    for run, by in _pieces_of_runs(owner, levels).items():
        names = [by[p] for p in sorted(by)]
        out[run] = names[0] if 0 in by or len(set(names)) == 1 else names
    return out


def _pieces_of_runs(owner: dict, levels: set[str]) -> dict[str, dict[int, str]]:
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


def piece_names(section: dict, pieces, owner: dict | None = None, data: Path = SCHEMATIC) -> dict[str, str]:
    """{piece: name without "Track "} of each drawn piece of `pieces` (staging_device_map.band_refs' piece
    references: "17C-29C", "37C-39C #2", the ID parts of a block ID) that the store names, for a hand plan_overrides
    section (its `helix` map holding block IDs): a run the owner names whole gives each of its pieces that name, a
    run named by piece its i-th piece the i-th name (owner_names on the section's levels; `owner` in its shape); a
    track up the helix from a switch of the section's `helix` map ("131AA-helix") the name of the staging helix block
    the map gives it. The readers by ID (block_layer, cats_panel, build_masts, staging_device_map) take a strand's
    name from here, not from the drawing. TrackNameError on a helix entry with no named block row or with more than
    one drawn track up the helix from its switch, or a drawn piece of a run named by piece that has no name of its
    own (a name is never spread to a piece the owner did not name)."""
    owner = owner_names(data) if owner is None else owner
    named = _pieces_of_runs(owner, section_levels(section))
    any_level = {bid: name for (_level, bid), name in owner.items()}     # a helix track is staging's block
    relabel = {}
    for e in section.get("edits", ()):
        if e.get("op") == "relabel":
            relabel.update(e["map"])
    helix, bad = {}, []
    for ref, bid in section.get("helix", {}).items():
        if bid not in any_level:
            bad.append(f"helix {ref}: {bid} has no named block row in {FIELD_FILE}")
        else:
            helix[str(relabel.get(ref, ref)).rstrip("*")] = any_level[bid]
    out, up = {}, {}
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


def plugin_section(sheet: str, section: dict, main_runs=(), owner: dict | None = None,
                   data: Path = SCHEMATIC) -> dict:
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
    out = json.loads(json.dumps(section))
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

