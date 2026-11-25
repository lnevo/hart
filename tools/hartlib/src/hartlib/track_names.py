"""The name store of the tracks (ADR-033 decision 2, naming-layers step 3): the owner's track names, keyed by device
ID, and how they reach the schematic plugin.

    track_names.owner_names()                      {(level, block id): name}: the owner's track names
    track_names.plugin_section(sheet, section)     a plan_overrides section with the plugin's `name` and `end` edits
    track_names.hand_problems(section)             why a hand section still holds a name (a check)

The owner names a track in devices_field.csv: a block row with an `id` (hartlib.device_ids.block_id, "block:17C-29C")
and its user name ("Track S-1"). That row is the only place the name is kept. plan_overrides.json holds no track
name: its `end` edit says what each track end is ([switch, leg, kind, to]: a bumper, or the helix and the level it
climbs to) and `left_end` is the ID of the track drawn at the left end; the plugin's `name` edit, the names in its
`end` edit and its `left_end` are made here from the store, when hartlib.layer_files.view writes the folder the
plugin reads. A renamed track is one edited user name; nothing in plan_overrides.json changes.

A block ID comes from the plan: each end of its track is the switch label (after the `relabel` edit) and leg it ends
at, or "end" (a bumper) or "helix" (staging_device_map.end_key, mast_rule.end_leg), so a track is found in the AnyRail
plan graph (inputs/<graph>.json) with no drawing. The pieces of a run the drawing parts at a turnback ("#1", "#2",
from the lower end) are named in order: one name for every piece is one plan name, different names a list (the
owner's split, K-1 and K-2). The `main` flags of the `name` edit are build_main_route.py's (plan_generated.json
`name_main`, the runs of the staging main lines): a run on a main line gets an entry even when it has no name.

Generated names (the end-switch rule, "Track 17-19") are not drawn on the schematic, so they are not written here:
block_layer.name_tracks makes them from the plan's track ends (mast_rule.plan_order for parallel tracks).

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


def _beside(data: Path, rel: str, repo: Path) -> Path:
    """`rel` under the folder `data`, or the repo's (`repo`) when `data` lacks it: a test's copy of the schematic
    folder that holds only the layer files reads the repo's plan graph and field file."""
    p = Path(data) / rel
    return p if p.exists() else repo


def owner_names(data: Path = SCHEMATIC) -> dict[tuple[str, str], str]:
    """{(level, block id): name without "Track "} of every block row of devices_field.csv (beside `data`, else the
    repo's) that has an id. TrackNameError on a row with an id that is not a block ID or a name not "Track <name>"."""
    path = _beside(Path(data).parent, FIELD_FILE, SCHEMATIC.parent / FIELD_FILE)
    if not path.exists():
        return {}
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
    graph = json.loads(_beside(data, PLAN_GRAPHS[sheet], SCHEMATIC / PLAN_GRAPHS[sheet]).read_text(encoding="utf-8"))
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
        if nodes[n]["kind"] != "end":
            return f"{label[n].rstrip('*')}{port}"
        return "helix" if n in helix_ends else "end"

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
    return bad


def _names_of_runs(owner: dict, levels: set[str]) -> dict[str, str | list[str]]:
    """{run: name, or names by piece from the lower end} of the owner's names on `levels`."""
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
    out = {}
    for run, by in pieces.items():
        names = [by[p] for p in sorted(by)]
        if 0 in by and len(by) > 1:
            bad.append(f"run {run} is named whole and by piece")
        elif len(set(names)) == 1:
            out[run] = names[0]
        elif sorted(by) != list(range(1, len(by) + 1)):
            bad.append(f"run {run}: pieces {sorted(by)} are named, not every piece from #1")
        else:
            out[run] = names
    if bad:
        raise TrackNameError(f"{FIELD_FILE}: " + "; ".join(bad))
    return out


def plugin_section(sheet: str, section: dict, main_runs=(), owner: dict | None = None,
                   data: Path = SCHEMATIC) -> dict:
    """`section` (a merged plan_overrides section) as the plugin reads it: a `name` edit after `relabel` naming every
    run the owner names (owner_names on the section's levels) and every run of `main_runs` (flagged main), each by
    its plan junction ids and the leg it leaves the lower end by; each `end` entry's name (its block row's: a bumper's
    block:<switch><leg>-end, a helix end's block:<switch><leg>-helix) put in third place; `left_end` the name of the
    block it gives. A section with no owner names and no main runs is returned as it is."""
    bad = hand_problems(section)
    if bad:
        raise TrackNameError(f"plan_overrides.json[{sheet}]: " + "; ".join(bad))
    owner = owner_names(data) if owner is None else owner
    levels = section_levels(section)
    names = _names_of_runs(owner, levels)
    by_id = {bid: name for (level, bid), name in owner.items() if level in levels}
    main_runs = list(main_runs)
    if not all(isinstance(r, str) for r in main_runs):
        raise TrackNameError(f"plan_generated.json[{sheet}] {NAME_MAIN} holds {main_runs[:3]}..., not runs "
                             "(\"1A-23A\"): run python3 tools/schematic/build_main_route.py")
    if not names and not main_runs and "left_end" not in section:
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
    if "left_end" in out:
        bid = out["left_end"]
        if bid not in by_id:
            bad.append(f"left_end {bid} has no named block row in {FIELD_FILE}")
        else:
            out["left_end"] = by_id[bid]
    lost = sorted(bid for bid in by_id if bid.endswith(("-end", "-helix")) and bid not in ends_done)
    if lost:
        bad.append(f"track ends {lost} are named in {FIELD_FILE} but have no `end` entry in plan_overrides.json")
    if bad:
        raise TrackNameError(f"{sheet}: " + "; ".join(bad))
    if tracks:
        edits = out.setdefault("edits", [])
        at = next((i + 1 for i, e in enumerate(edits) if e.get("op") == "relabel"), 0)
        edits.insert(at, {"op": "name", "tracks": tracks})
    return out

