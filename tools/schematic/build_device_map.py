#!/usr/bin/env python3
"""Placeholder control points and device names for the main and upper levels, and every level's block rows.

    python3 tools/schematic/build_device_map.py           # write both outputs
    python3 tools/schematic/build_device_map.py --check   # exit 1 if either output is stale

--check prints SKIPPED and exits 0 when the plugin submodule is not checked out (1 with SCHEMATIC_REQUIRED=1).

Inputs (jmri/layouts/hart/data/schematic/):
- interlockings.csv, its level 2 and 3 rows: the placeholder control points, "CP <lowest switch>" (owner,
  2026-11-15), which are also the signal rule's interlockings (one file for every level, owner 2026-11-20). Hand
  data, one row per control point: level (2 main, 3 upper), switch numbers, area (the LCOS node area). Only
  interlockings that affect the main route are control points, as in the bench plans
  (docs/wiring/bench/control_point_4 to 6): switches on the main route, grouped where they stand close together.
- block_splits.csv: the owner's choice of tracks parted into two blocks at their turnback (not a rule).
- local_switches_main_upper.csv: every other switch (yards and industry spurs), with its area. These get a
  turnout and feedback but no control point, no signals and no detection.
- lcos_nodes_main_upper.csv: the LCOS radio addresses each level and area may use, in order: the upper level's
  from LCOS_Layout_Inventory_v85.xlsx, the rest from the owner's node grid
  (media/hart-research/wiring-drafts/lcos-node-grid-2025-10-06c.xlsx, local), where an address 0XN is device X off
  node 0N.
- the solved schematic bands (the inputs publish_draft.py draws), for tracks, their ends and which way is east.

Outputs:
- plan_overrides.json's main_upper section (hartlib.layer_files), keys `control_points` and `stations`: the detail
  sheets (the "Main level" and "Upper level" sheets of preferences.json's main_upper section) draw each control
  point's interlocking limits and name, and the overall sheet a bar per control point (no car count). A control
  point may list only switches on one band, so a crossover whose halves sit on two bands (127, 131) lists the half
  on the control point's level. The bars make the page taller; at the smaller scale the plugin's label check counts 7 milepost labels against their
  markers (draft, 2026-11-15; labels are placed before the page is scaled).
- devices.csv (hartlib.devices): the rows of levels 2 and 3 are this script's (written_by build_device_map.py), and
  so are staging's block and occupancy rows (staging_rows, below). The main and upper rows are the one mapping from
  each main and upper JMRI device to its planned physical part. Per
  row: the user name under ADR-005; jmri_name, the virtual device tables.xml and the CATS desks use now; system_name,
  the planned physical device (LCOS, a DRAFT: the main and upper plant is not reviewed yet, owner 2026-11-17). Later
  a physical device is swapped in by this mapping alone, so no JMRI name ever comes from a draft address or from
  drawing order. Placeholder user names change when the owner names the levels.

Blocks: one block process for every level (block_layer.py, level unification step 5 part 1, owner 2026-11-20): OS
blocks, track blocks, halves (block_splits.csv, every level: 227-241 and staging's K-1 and K-2), helix blocks named
through helix_tracks.csv, and parts (devices.csv part_of: a piece of track inside another block, by the rule or
block_exceptions.csv). Staging's plant is the field, so its block and occupancy rows carry their field facts (system
and layout-block names, node, wiring, comment, notes, detector, stop, the station group in cp and the name-map columns)
over from the row of the same name; this script owns which blocks there are and what each holds (role, trial_name in
staging's switch-and-leg keys, part_of, blocks, description). A staging block change made in PanelPro is carried by
hand into this script's data (block_exceptions.csv, block_splits.csv, helix_tracks.csv), not into devices.csv; a field
fact of a staging block (a new system name or detector) is still edited in its devices.csv row, which this script keeps.
A new staging block needs a row with its field facts first (hand-kept, no written_by: this script adopts it). Main and
upper keep their links as blocks of their own until part 2 (block_layer.FOLD_LINKS).

Virtual names (owner, 2026-11-17), from each device's stable identity:
- Turnout "Switch <n>" (and its LCC alias "DCC Switch <n>"): IT:HART:C3:<n>.
- Every block has one occupancy row, its sensor IS:HART:C3:B:<block_key> (hartlib.level_devices: the block name with
  "Track "
  dropped, "OS Switch " shortened to "OS", spaces to "_": IS:HART:C3:B:107-109, IS:HART:C3:B:107_Loop_2,
  IS:HART:C3:B:OS225b). Its system_name is the planned detector (M2S), or empty: NOT_WIRED for a detector planned
  but not on a node yet, NO_DETECTOR for a block that has none planned (dark until decided). Those facts are columns
  of their own (hartlib.railroad.DEVICE_FACTS): an occupancy row's `blocks` (its block) and `detector` (planned,
  not_wired or none), a mast row's `switch`, `facing` and `protects`; the notes and comment are text for people.
- Head "Head <mast>[ Top|Bottom]": hartlib.level_devices.head_name (IH:HART:C3:108LA, IH:HART:C3:108R_Top); mast
  IF$shsm:basic:<type>(<head>)(<head>) over those heads.
- Feedback rows have no JMRI device of their own (a turnout's feedback is DIRECT until the plant is wired), and
  block rows none here: build_layout_le.py numbers their blocks.

Naming rules (ADR-005 grammar, LCOS conventions):
- Turnout "Switch <n>" (a crossover is one turnout), feedback "FB Switch <n> N|R", OS block "OS Switch <n>" (one per
  number, as the Layout Editor trial has it), occupancy "BS <block without Track>". A double crossover is four OS
  blocks, one per corner, "OS Switch <n>a" to "<n>d" by its Layout Editor corner A to D (owner, 2026-11-16; the
  plugin's double_corners maps the schematic's legs to the corners): with one block, or
  two, JMRI 5.16 records a through path between the two legs on one side (LayoutBlock.addThroughPath keeps a pair
  whose turnout lists match both ways) and Signal Mast Logic discovery pairs masts across it (226RA to 224LB). Corner
  a keeps the switch's detector; b to d have none on a node until wired (NOT_WIRED). A mast at a double crossover
  protects its own leg's corner block ("home signal from Track X into OS Switch <n><corner>").
- Track "Track <a>-<b>" from its end switches, "Track <n> Spur" to a bumper, "Track <n> Loop" back to the same
  switch; parallel tracks between the same ends take " 1", " 2" from the top row. A track up the helix is its helix
  block (helix_tracks.csv: Track Helix Outer from 131A, Track Helix Inner from 131B), one JMRI block with the staging
  track below it (owner, 2026-11-20): the staging device map names its staging piece, and the Layout Editor build
  binds this map's occupancy row to the one staging block. Its level_switch must be the switch the drawing gives.
  A balloon loop is two blocks, "Track <n> Loop 1" from the switch's leg B and "Track <n> Loop 2" from leg C, parted
  at the turnback halfway round (owner, 2026-11-16): JMRI keys a mast by its facing and protected blocks
  (LayoutBlockManager.getFacingBean returns one), so two masts facing one loop block into one OS block would leave
  one of them out of Signal Mast Logic discovery. Loop 1 keeps the loop's detector; Loop 2's is not on a node until it is
  wired (NOT_WIRED), so no node or input assignment moves.
  A track under SHORT_CM between two switches gets a block but no detector (it would sit inside their OS blocks;
  step 5 part 2 makes such links parts of an OS block, as staging's are).
- Detection on the main line only (owner, 2026-11-15): main-route tracks and the OS blocks of control point
  switches get a planned detector; yard and industry tracks and the OS blocks of switches in no control point
  get none (their virtual sensor stays, NO_DETECTOR).
- Masts: the one mast process every level uses (mast_plan.plan, owner 2026-11-20; plan_masts): home masts,
  intermediates, and virtual masts (hidden, IF$vsm, ordinals from 2001 on main and 3001 on upper) only where a
  visible mast's route reaches a buffer stop first. What follows is the home mast rule as it stands here.
- Home signals: one mast where each track from outside a control point meets one of its switches; none on spurs
  or yard tracks that end at a bumper, and none where no route the mast would govern reaches another signal (every
  route ends at a bumper or in dark track: mast_rule.reaches_signal, owner 2026-11-19, which leaves out 125B's mast
  into Switch 129's spurs). "Mast <n+1><L|R>", L for a westbound train (ADR-005), A/B when one number and direction
  has two. Two heads (Top and Bottom) when a route the mast governs meets facing points inside its
  control point before the next signal (mast_rule.facing_on_route), else one; high (searchlight) facing from running
  track, a dwarf (low) from a yard, lead or siding (owner, 2026-11-19). East is the schematic's (ADR-022 amendment: away from the helix on these levels).
- LCOS packed IDs are node * 100 + UID (external/lcos-bridge): blocks UID 0-7 (BS, "Node: n Block: k+1"), turnouts
  8-15 (M2T, "Node: n Turnout: k"), signals 32-47 (IH, "Node: n Signal: k"), inputs from 67 (M2S, feedback N then R
  per turnout, "Node: n Sensor: k"). A control point's turnouts stay on one node; switches in no control point
  follow, area by area. Heads come last: every two-head mast of every group before any one-head mast, each on the
  first 5V board with room, so a group's heads may land off its home node, on another node of its area, when the
  home node is full, and draft head outputs may reshuffle from one build to the next (owner, 2026-11-19: nothing on
  the main and upper levels is wired yet).
- Hand lists keyed by end switches (block_splits, with a level column, and detector_pins; source-data row 5; running
  track and exit dwarfs are rules since 2026-11-20, mast_rule.running_tracks and signalled_spurs): columns switch_a,
  switch_b (the owner's switch numbers, lower first; switch_b blank for a spur, whose other end is a
  bumper), `parallel` (1, 2 from the top row, only where two tracks run between the same switches) and, in the pins,
  `half` (1, 2: a balloon loop or split track, half 1 at the lower-numbered switch). Each row is resolved to the
  generated track at build time (mast_rule.resolve_track), so a renumber moves rows with their tracks; a pair that
  matches no track, or two tracks with no `parallel`, stops the build naming the file, line and candidates. A pin on a
  helix block gives the owner's block name instead (no switches).
- DCC addresses continue from staging's last (119): 120 up in switch-number order, main level first (owner,
  2026-11-15). Each turnout also gets its LCC alias "DCC Switch <n>" (MTT<dcc>, same node comment, as staging has).
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA, GRAPHS, INPUTS and the pinned plugin
from mast_rule import (  # noqa: E402,F401  the track and mast rule, re-exported for the builders
    LOOP_HALF, TAU, MapError, band_levels, end_label, end_ref, facing_on_route, helix_blocks, helix_tags, masts,
    TRACK_KEY_COLUMNS, key_problem, read_helix_tracks, resolve_track, track_names, tracks)
import block_layer  # noqa: E402  the one block process for every level
import mast_plan  # noqa: E402  the one mast process for every level
import mast_rule  # noqa: E402  read_block_splits
from hartlib import devices, layer_files, level_devices, level_masts, railroad  # noqa: E402  names, facts, the master

SOURCES = railroad.Sources.under()
CPS = SOURCES.interlockings
NODES = SOURCES.lcos_nodes
LOCAL = SOURCES.local_switches
OVERRIDES = SOURCES.plan_overrides               # plan_overrides.json; this writes its main_upper section
SHEET = railroad.PlanOverrides.SHEET
OUT = SOURCES.devices                             # devices.csv, whose levels 2 and 3 this script writes
LEVELS = band_levels(layer_files.read("plan_overrides", SHEET, OVERRIDES.parent))     # {band title: level} of main and upper
SPLIT = OVERRIDES.parent / "block_splits.csv"     # the owner's choice of tracks parted into two blocks (all levels)
PINS = OVERRIDES.parent / "detector_pins_main_upper.csv"         # detectors the owner placed on a given node input
# The hand lists name a track by the switches at its ends (switch_a, switch_b: lower number first; switch_b blank for a
# spur, whose other end is a bumper; mast_rule.track_key), so a renumbered switch moves its row with it. `parallel`
# (1, 2 from the top row) says which of two tracks between the same switches; `half` (1, 2) which half of a balloon
# loop or split track, half 1 at the lower-numbered switch. A pin on a helix block, which the owner named
# (helix_tracks.csv), has `block` and no switches.
PIN_COLUMNS = TRACK_KEY_COLUMNS + ["half", "block", "node", "block_input", "notes"]


def device_files() -> devices.Files:
    """The master and its generated files as main() writes them: OUT, as it is when it runs (a test may patch it)."""
    return devices.Files.under(OUT.parent)


def sources() -> railroad.Sources:
    """The files main() reads and writes: the module's paths as they are when it runs (a test may patch them)."""
    return railroad.Sources.under().but(interlockings=CPS, lcos_nodes=NODES, local_switches=LOCAL,
                                        plan_overrides=OVERRIDES, devices=OUT)

SHORT_CM = 30.0
CAP = {"turnout": 8, "block": 8, "signal": 16, "sensor": 16}
MAX_OU = 4                            # DNOU8 boards per node: the most any node has in LCOS_Layout_Inventory_v85
UID = {"block": 0, "turnout": 8, "signal": 32, "sensor": 67}
COLUMNS = list(railroad.DEVICE_COLUMNS)
DCC_FIRST = 120                       # staging uses 100-119 (MTT100-MTT119); the owner continues from 120
VIRTUAL_TURNOUT = level_devices.TURNOUT_PREFIX   # + switch number: the internal turnout the panels and desks use
VIRTUAL_SENSOR = level_devices.SENSOR_PREFIX     # + block_key: the internal occupancy sensor of every block
occupancy_user = level_devices.occupancy_user
NOT_WIRED = "detector planned, not wired yet: no node or input (owner, 2026-11-16)"
HEAD_NOT_WIRED = "head planned, no board room on the draft plant: placed when the wiring plan is reworked (owner, 2026-11-19)"
NO_DETECTOR = "no detector planned: dark until decided"


# The switch number of a schematic label ("129A" -> "129", "223*" -> "223") and the natural sort key, defined once in
# hartlib.railroad; the names stay here because build_layout_le.py and build_cats_panel.py import them from this module.
base = railroad.switch_number
natural = railroad.natural


def block_sensor(block: str) -> str:
    """The virtual occupancy sensor of a main or upper block (hartlib.level_devices.block_sensor); MapError on a
    name that gives no clean key."""
    try:
        return level_devices.block_sensor(block)
    except ValueError as exc:
        raise MapError(str(exc)) from None


def band_level(title: str) -> int | None:
    """The level (2 or 3) of a main or upper band by its title, from the plan overrides' `level`s; None for staging."""
    return mast_rule.band_level(title, LEVELS)


def load_cps(path: Path = CPS) -> list[railroad.Interlocking]:
    """The main and upper interlockings, their control points (hartlib.railroad.read_interlockings: every switch in at
    most one)."""
    try:
        return railroad.read_interlockings(path, railroad.LEVEL_NUMBERS)
    except railroad.FactsError as exc:
        raise MapError(str(exc)) from None


# ---------------------------------------------------------------- the schematic


def labels_by_level(bands) -> dict[int, set[str]]:
    out = defaultdict(set)
    for title, band, _ in bands:
        lv = band_level(title)
        if lv:
            out[lv] |= {d["label"] for d in band["nodes"].values() if d["kind"] in ("switch", "dx")}
    return out


def overrides_keys(cps, by_level) -> dict:
    """control_points for plan_overrides.json's main_upper section: each control point lists the labels of its
    switches on its own level's band (both halves of a crossover there, one half when the other is on the
    other band), as the band prints them: a moved switch keeps its star ("223*"), which station bars match on."""
    cp_out = {}
    for cp in cps:
        have = by_level[cp.level]
        refs = []
        for s in cp.switches:
            mine = sorted(lb for lb in have if base(lb) == s)
            if not mine:
                raise MapError(f"{cp.name}: switch {s} is not on the level {cp.level} band")
            refs += mine
        cp_out[cp.name] = {"switches": refs}
    return cp_out


def xover_corners(number: str, corners: dict) -> dict:
    """{schematic leg: OS block} of a double crossover's four corner blocks, named by the Layout Editor corner each
    leg reaches (`corners`, {leg: corner}: dx_corners); see the module text."""
    if sorted(corners) != list("ABCD") or sorted(corners.values()) != list("ABCD"):
        raise MapError(f"double crossover {number}: legs to corners {corners} is not one corner per leg")
    return {leg: f"OS Switch {number}{corner.lower()}" for leg, corner in sorted(corners.items())}


def dx_corners(bands, le_mod, page) -> dict:
    """{switch number: {schematic leg: Layout Editor corner}} of each double crossover on the main and upper bands,
    as the plugin draws it (le.double_corners; a band in the page's rotate_bands is turned)."""
    out = {}
    for title, band, _ in bands:
        if not band_level(title):
            continue
        for n, d in band["nodes"].items():
            if d["kind"] == "dx":
                # rotate_bands lists the plugin's band keys (its draw.band_key: a title's first word), not levels
                turned = title.split()[0] in page.get("rotate_bands", ())
                out[base(d["label"])] = le_mod.double_corners(band, n, turned)
    return out


def split_tracks(path: Path | None = None, found: list | None = None) -> set[str]:
    """The main and upper track names block_splits.csv parts into two blocks at their turnback (the owner's choice,
    not a rule: mast_rule.read_block_splits): each row's end switches resolved to the generated name in `found` (tracks
    with names; default: the solved schematic's) at build time, so a renumbered switch moves its row with it."""
    return mast_rule.read_block_splits(path or SPLIT, named_tracks() if found is None else found, LEVELS)


def named_tracks(bands=None, joined=None, runs=None, overrides=None, helix=None) -> list[dict]:
    """The track entries of the bands `overrides` names (default: the main and upper bands) with their names
    (block_layer.tracks and name_tracks: the plan's name, a helix track's helix block from helix_tracks.csv, else the
    end-switch rule); the solved schematic's bands when none are given. `helix`: read_helix_tracks (default)."""
    if bands is None:
        bands, joined, runs, _corners = solve()
    if overrides is None:
        overrides = layer_files.read("plan_overrides", SHEET, OVERRIDES.parent)
    found = block_layer.tracks(bands, runs, joined, band_levels(overrides))
    block_layer.name_tracks(found, bands, read_helix_tracks() if helix is None else helix)
    return found


def split_edges(path: Path | None = None, found: list | None = None) -> dict:
    """{plan edge: track name} of the main and upper split tracks (block_layer.split_edges over block_splits.csv):
    each name resolved to the one plan edge its track is drawn on, in `found` (tracks with names; default: the solved
    schematic's), at build time. Stops on a name no track has, or a track drawn on more than one plan edge (a split
    needs one track folded at one turnback)."""
    found = named_tracks() if found is None else found
    return block_layer.split_edges(found, LEVELS, path or SPLIT).get("main_upper", {})


def read_pins(path: Path | None = None, found: list | None = None, split: set | None = None) -> dict:
    """{block name: (node, input index from 0)} of detector_pins_main_upper.csv: detectors the owner put on a given
    input ("Block <k>" of a node, 1 to 8), which the rule then hands to no other block (owner, 2026-11-20: the helix
    node 41). A track's block is named by its end switches (switch_a, switch_b, parallel), plus `half` for a balloon
    loop or a track in `split` (names, split_tracks): resolved in `found` (named_tracks) to the generated block name. A
    helix block is named in `block` with no switches. Stops on a file not in that shape, a track that does not
    resolve, a half missing from or given to a track that has none, a block or an input given twice, or an input out
    of range."""
    path = path or PINS
    found = named_tracks() if found is None else found
    split = split_tracks(found=found) if split is None else split
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows, header = list(reader), reader.fieldnames or []
    except OSError as exc:
        raise MapError(f"cannot read {path.name}: {exc}") from None
    if list(header) != PIN_COLUMNS:
        raise MapError(f"{path.name}: columns {list(header)}, not {PIN_COLUMNS}")
    helix_names = {t["name"] for t in found if any(k == "helix" for k, _v in t["ends"])}
    out, slots, bad = {}, set(), []
    for i, r in enumerate(rows, 2):
        r = {k: (v or "").strip() for k, v in r.items()}
        try:
            node, k = int(r["node"]), int(r["block_input"]) - 1
        except ValueError:
            bad.append(f"line {i}: node and block_input are numbers")
            continue
        if not 0 <= k < CAP["block"]:
            bad.append(f"line {i}: input {k + 1} is not 1 to {CAP['block']}")
            continue
        if r["block"]:                                  # a helix block, named by the owner
            if r["block"] not in helix_names:
                bad.append(f"line {i}: block {r['block']!r} is no helix block ({', '.join(sorted(helix_names))}); "
                           "name any other track by switch_a and switch_b")
                continue
            if r["switch_a"] or r["switch_b"] or r["parallel"] or r["half"]:
                bad.append(f"line {i}: helix block {r['block']!r} is named by its block alone: leave switch_a, "
                           "switch_b, parallel and half empty")
                continue
            name = r["block"]
        else:
            problem = key_problem(r)
            t = None if problem else resolve_track(r, found)
            if t is None:
                bad.append(f"line {i}: {problem or r['problem']}")
                continue
            looped = t["loop"] or t["name"] in split
            if r["half"] not in ("", "1", "2") or looped != bool(r["half"]):
                bad.append(f"line {i}: {t['name']} is " +
                           ("in two halves: give half 1 or 2" if looped else "one block: no half"))
                continue
            name = loop_placeholder(t["name"], int(r["half"]) if r["half"] else None)
        if name in out or (node, k) in slots:
            bad.append(f"line {i}: block {name} or Block {node}-{k + 1} pinned twice")
        else:
            out[name] = (node, k)
            slots.add((node, k))
    if bad:
        raise MapError(f"{path.name}: " + "; ".join(bad))
    return out


def loop_halves(band, runs, split: dict | None = None) -> dict:
    """{strand id: 1 or 2} of each balloon loop and split track of a main or upper `band` (block_layer.loop_halves);
    `split`: split_edges (default: block_splits.csv's)."""
    return block_layer.loop_halves(band, runs, split_edges() if split is None else split, SPLIT.name)


def track_layer(bands, runs, found, split_map: dict) -> tuple[dict, dict]:
    """The main and upper block layer as mast_plan.plan reads it: ({band index: {"os": {switch node: OS block},
    "blocks": {strand: [block]}}}, {block: cm}), block_layer.layer's for the main and upper levels with
    `split_map` (split_edges) and block_exceptions.csv. One block per track, a balloon loop or split track in two
    halves (half 1 at the lower-numbered switch; each half's length is half the track's), a crossover's inside its
    switch's OS block; an OS block counts 0 cm (the boundary is at the switch's leg)."""
    lay = main_upper_layer(bands, runs, found, split_map)
    return lay.bands, lay.cm


def main_upper_layer(bands, runs, found, split_map: dict) -> block_layer.Layer:
    """block_layer.layer of the main and upper levels."""
    return block_layer.layer(bands, runs, found, LEVELS, {"main_upper": split_map},
                             block_layer.read_exceptions(found, bands, LEVELS))


def check_helix_ends(bands, joined, found, helix) -> None:
    """Stop unless each track up the helix ends at the switch helix_tracks.csv gives it (level_switch, the label the
    drawing prints: 131A, 131B), so the file cannot give a helix track the other one's block."""
    if not helix:
        return
    want = {v["block"]: v["level_switch"] for v in helix.values()}
    bad = []
    for t in found:
        if not any(k == "helix" for k, _v in t["ends"]):
            continue
        labels = [end_label(bands, joined, t["band"], n) for (n, _p), (k, _v) in zip(t["legs"], t["ends"]) if k == "sw"]
        if t["name"] not in want or labels != [want[t["name"]]]:
            bad.append(f"{t['name']} runs from switch {', '.join(labels) or 'none'}, helix_tracks.csv says "
                       f"{want.get(t['name'], 'nothing')}")
    drawn = {t["name"] for t in found}
    bad += [f"{b} is drawn on neither the main nor the upper band" for b in want if b not in drawn]
    if bad:
        raise MapError("helix tracks: " + "; ".join(bad))


def loop_placeholder(placeholder: str, half: int | None) -> str:
    """The drawing's placeholder for one half of a balloon loop ("Track e33" -> "Track e33 1"), as
    build_layout_le.placeholder_names and build_cats_panel name it; any other track's is unchanged."""
    return placeholder if half is None else f"{placeholder} {half}"


# ---------------------------------------------------------------- LCOS nodes

class NoBoardRoom(MapError):
    """The draft plant has no 5V board room left in an area for a mast's heads: the heads wait for the wiring plan
    (HEAD_NOT_WIRED). Any other MapError still stops the build."""


class Nodes:
    """Hands out LCOS UIDs per node, in each level and area's node order."""

    def __init__(self, rows):
        self.pool = defaultdict(list)
        for r in rows:
            self.pool[(r.level, r.area)].append(r.node)
        self.used = defaultdict(lambda: defaultdict(int))
        self.taken = defaultdict(set)         # (node, what) -> the indices given out or pinned
        self.pins = {}                        # block -> (node, index): detector_pins_main_upper.csv
        self.boards = {}                     # node -> pins used on each of its 5V boards

    def pin(self, pins):
        """Hold each pinned detector's input (read_pins: {block: (node, input index)}) before any other is given out,
        so the rule never hands it to another block."""
        known = {n for nodes in self.pool.values() for n in nodes}
        for block, (node, k) in sorted(pins.items()):
            if node not in known:
                raise MapError(f"{PINS.name}: {block} is pinned to node {node}, which {NODES.name} does not list")
            self.taken[(node, "block")].add(k)
            self.used[node]["block"] += 1
        self.pins = dict(pins)

    def room(self, node, what, n=1):
        return self.used[node][what] + n <= CAP[what]

    def pick(self, level, area, what, n=1, prefer=()):
        for node in list(prefer) + self.pool[(level, area)]:
            if self.room(node, what, n):
                return node
        raise MapError(f"level {level} {area}: no LCOS node left with room for {n} {what}(s); "
                       f"add one to {NODES.name}")

    def take(self, node, what):
        """The node's lowest free index of `what` (one a pin holds is not free), and its packed id."""
        k = next(i for i in range(CAP[what]) if i not in self.taken[(node, what)])
        self.taken[(node, what)].add(k)
        self.used[node][what] += 1
        return k, node * 100 + UID[what] + k

    def take_pinned(self, block):
        """(node, index, packed id) of `block`'s pinned detector, once; None when it has no pin."""
        if block not in self.pins:
            return None
        node, k = self.pins.pop(block)
        return node, k, node * 100 + UID["block"] + k

    def check_pins(self):
        """Stop when a pin names a block the map has no detector row for (a stale or misspelt pin)."""
        if self.pins:
            raise MapError(f"{PINS.name}: pins for blocks the device map gives no detector: {sorted(self.pins)}")

    # 5V boards for heads, after the node's 12V turnout boards (call once every turnout and detector is placed)
    def n12(self, node):
        return -(-self.used[node]["turnout"] // 4)

    def _cap(self, node, i):
        return 7 if i == 0 and self.used[node]["block"] else 8     # pin 8 of the first 5V board: calibration

    def _fit(self, node, pins):
        """(board index among the node's 5V boards, first pin) where `pins` consecutive pins fit, or None: the first
        board with room (any of them, not only the last), else a new board while the node has OU room."""
        boards = self.boards.setdefault(node, [])
        for i, used in enumerate(boards):
            if used + pins <= self._cap(node, i):
                return i, used + 1
        if self.n12(node) + len(boards) + 1 <= MAX_OU and pins <= self._cap(node, len(boards)):
            return len(boards), 1
        return None

    def pick_mast(self, level, area, heads, prefer=()):
        for node in list(prefer) + self.pool[(level, area)]:
            if self.room(node, "signal", heads) and self._fit(node, 3 * heads):
                return node
        raise NoBoardRoom(f"level {level} {area}: no LCOS node left with board room for a {heads}-head mast; "
                       f"add one to {NODES.name}")

    def place_mast(self, node, heads):
        """[(signal index, packed id, OU board, first pin)] for the mast's heads, on one 5V board."""
        i, first = self._fit(node, 3 * heads)
        boards = self.boards[node]
        if i == len(boards):
            boards.append(0)
        out = []
        for h in range(heads):
            k, packed = self.take(node, "signal")
            out.append((k, packed, self.n12(node) + 1 + i, first + 3 * h))
        boards[i] = first - 1 + 3 * heads
        return out

    def check_boards(self):
        """A node with detectors needs a 5V board for the calibration pin; no node may need more than MAX_OU."""
        for node, used in self.used.items():
            five = max(len(self.boards.get(node, [])), 1 if used["block"] else 0)
            if self.n12(node) + five > MAX_OU:
                raise MapError(f"node {node} needs {self.n12(node) + five} DNOU8 boards; the limit is {MAX_OU}")


# ---------------------------------------------------------------- the map


def plan_masts(bands, joined, runs, found, cp_of: dict, corners: dict | None) -> tuple[dict, dict, set]:
    """(mast_plan.plan's masts of the main and upper levels, the double crossovers' corner blocks, the split track
    names): the one mast process over this level's block layer (track_layer) and the owner's block splits. MapError
    on a double crossover with no corners given."""
    corners = corners or {}
    dxs = {base(d["label"]) for title, band, _ in bands if band_level(title)
           for d in band["nodes"].values() if d["kind"] == "dx"}
    if dxs - set(corners):
        raise MapError(f"double crossover {', '.join(sorted(dxs - set(corners), key=natural))}: no corners given")
    corner_blocks = {s: xover_corners(s, corners[s]) for s in dxs}
    split = split_edges(found=found)
    layer, cm = track_layer(bands, runs, found, split)
    got = mast_plan.plan(bands, joined, found, levels=LEVELS, cp_of=cp_of, layer=layer, cm=cm,
                         corner_blocks=corner_blocks, split=set(split.values()))
    return got, corner_blocks, set(split.values())


def master_virtual_names(files: devices.Files | None = None) -> dict:
    """{mast: system name} of the main and upper virtual masts the device master holds now (each keeps its ordinal)."""
    return {r["user_name"]: r["jmri_name"] for r in devices.load(files or device_files())
            if r["level"] in ("2", "3") and r["layer"] == "mast" and level_masts.virtual_ordinal(r["jmri_name"])}


def build(bands, joined, runs, overrides, cps, node_rows, local=(), corners=None, helix=None, pins=None,
          virtual_names=None) -> tuple[dict, list[dict]]:
    """(control_points, device map rows). `local`: the switches in no control point (local_switches_main_upper.csv
    rows). Every switch on the main and upper bands must be in exactly one of the two. `corners`: dx_corners, needed
    when a band has a double crossover. `helix`: read_helix_tracks (None: helix_tracks.csv; {}: no helix tracks);
    `pins`: read_pins (None: detector_pins_main_upper.csv, resolved against the tracks found here); `virtual_names`:
    {mast: system name} of the virtual masts that have one already (None: master_virtual_names)."""
    helix = read_helix_tracks() if helix is None else helix
    by_level = labels_by_level(bands)
    cp_keys = overrides_keys(cps, by_level)
    try:
        switches = railroad.join_main_upper(cps, local, LOCAL.name)
    except railroad.FactsError as exc:
        raise MapError(str(exc)) from None
    cp_of = {s: sw.cp for s, sw in switches.items() if sw.cp}
    loc = {s: sw for s, sw in switches.items() if not sw.cp}          # in no control point: level, area, notes
    on_bands = {base(lb) for labels in by_level.values() for lb in labels}
    missing = sorted(on_bands - set(cp_of) - set(loc), key=natural)
    if missing:
        raise MapError(f"switch {', '.join(missing)} is in no control point and not in {LOCAL.name}")
    found = named_tracks(bands, joined, runs, overrides, helix)
    check_helix_ends(bands, joined, found, helix)
    planned, corner_blocks, split_names = plan_masts(bands, joined, runs, found, cp_of, corners)
    dxs = set(corner_blocks)
    pins = read_pins(found=found, split=split_names) if pins is None else pins
    ms = planned["home"] + [dict(m, heads=1, kind="one-searchlight", switch="", intermediate=True)
                            for m in planned["intermediates"]]
    old_virtual = master_virtual_names() if virtual_names is None else virtual_names
    vnames = {}
    for lv in (2, 3):                       # each level's ordinals from its own thousand (hartlib.level_masts)
        vnames |= mast_plan.virtual_system_names([m["name"] for m in planned["virtual"] if m["level"] == lv], lv,
                                                 {k: v for k, v in old_virtual.items()
                                                  if level_masts.virtual_level(v) == lv})
    nodes = Nodes(node_rows)
    nodes.pin(pins)
    rows = []

    def add(level, cp, layer, user, system="", node="", comment="", trial="", notes="", dcc="", jmri="", **facts):
        rows.append(dict(level=level, cp=cp, layer=layer, user_name=user, system_name=system, jmri_name=jmri,
                         node=node, dcc=dcc, comment=comment, trial_name=trial, notes=notes,
                         **{c: facts.pop(c, "") for c in railroad.DEVICE_FACTS}))
        if facts:
            raise MapError(f"{layer} {user}: unknown fact columns {sorted(facts)}")

    def occupancy(level, cp, block, system="", node="", comment="", notes=""):
        """The occupancy row of `block`: its virtual sensor (jmri_name), the block it serves and its detector: planned
        on an input (`system`, M2S), planned with no input yet (NOT_WIRED) or none planned (NO_DETECTOR)."""
        detector = "planned" if system else {NOT_WIRED: "not_wired", NO_DETECTOR: "none"}.get(notes)
        if detector is None:
            raise MapError(f"occupancy of {block}: no detector and no reason why ({notes!r})")
        add(level, cp, "occupancy", occupancy_user(block), system, node, comment, notes=notes,
            jmri=block_sensor(block), blocks=block, detector=detector)

    dcc = {s: DCC_FIRST + i for i, s in enumerate(sorted(set(cp_of) | set(loc), key=natural))}
    home, area_of = {}, {}                  # switch -> its turnout's node, its area

    def switch_rows(lv, area, name, s, node, note=""):
        k, packed = nodes.take(node, "turnout")
        home[s], area_of[s] = node, (lv, area)
        halves = sorted({lb for labels in by_level.values() for lb in labels if base(lb) == s}, key=natural)
        add(lv, name, "turnout", f"Switch {s}", f"M2T{packed}", node, f"Node: {node} Turnout: {k}",
            ", ".join(f"Switch {lb}" for lb in halves), note, dcc[s], jmri=VIRTUAL_TURNOUT + s)
        add(lv, name, "turnout", f"DCC Switch {s}", f"MTT{dcc[s]}", node, f"Node: {node} Turnout: {k}",
            notes="LCC alias of the MQTT turnout (ADR-005)", dcc=dcc[s], jmri=VIRTUAL_TURNOUT + s)
        for nr in "NR":
            fnode = nodes.pick(lv, area, "sensor", prefer=[node])
            kk, pp = nodes.take(fnode, "sensor")
            add(lv, name, "fb", f"FB Switch {s} {nr}", f"M2S{pp}", fnode, f"Node: {fnode} Sensor: {kk}")

    def os_rows(lv, area, name, s, comment, detect=True):
        if s in dxs:                            # a double crossover: a block per corner, corner a detected
            for block in sorted(corner_blocks[s].values()):
                note = f"corner {block[-1].upper()} of the double crossover"
                if not detect:
                    add(lv, name, "block", block, "", "", comment, block, note + ", no detector: off the main line")
                    occupancy(lv, name, block, notes=NO_DETECTOR)
                elif not block.endswith("a"):             # wired later: no node or input yet
                    add(lv, name, "block", block, "", "", comment, block, note)
                    occupancy(lv, name, block, notes=NOT_WIRED)
                else:                                     # corner a keeps the switch's detector
                    bnode = nodes.pick(lv, area, "block", prefer=[home[s]])
                    k, packed = nodes.take(bnode, "block")
                    add(lv, name, "block", block, "", bnode, comment, block, note)
                    occupancy(lv, name, block, f"M2S{packed}", bnode, f"Node: {bnode} Block: {k + 1}")
            return
        block = f"OS Switch {s}"
        if not detect:
            add(lv, name, "block", block, "", "", comment, block, "no detector: off the main line")
            occupancy(lv, name, block, notes=NO_DETECTOR)
            return
        bnode = nodes.pick(lv, area, "block", prefer=[home[s]])
        k, packed = nodes.take(bnode, "block")
        add(lv, name, "block", block, "", bnode, comment, block)
        occupancy(lv, name, block, f"M2S{packed}", bnode, f"Node: {bnode} Block: {k + 1}")

    for cp in cps:                               # turnouts first: a node's 12V boards come before its 5V boards
        node = nodes.pick(cp.level, cp.area, "turnout", len(cp.switches))
        for s in cp.switches:
            switch_rows(cp.level, cp.area, cp.name, s, node)
    for s in sorted(loc, key=natural):           # no control point: turnout and feedback, no signals or detection
        r = loc[s]
        node = nodes.pick(r.level, r.area, "turnout")
        switch_rows(r.level, r.area, "", s, node, "no control point: " + r.notes)
    for cp in cps:
        for s in cp.switches:
            os_rows(cp.level, cp.area, cp.name, s, cp.name)
    for s in sorted(loc, key=natural):
        os_rows(loc[s].level, loc[s].area, "", s, loc[s].area, detect=False)

    for t in sorted(found, key=lambda t: natural(t["name"])):
        sws = [v for k, v in t["ends"] if k == "sw"]
        stray = [s for s in sws if s not in area_of]
        if stray:
            raise MapError(f"{t['name']} ends at switch {', '.join(stray)}, which is on neither the main nor the "
                           "upper level")
        ends_cp = sorted({cp_of[v] for v in sws if v in cp_of}, key=natural)
        cp = ends_cp[0] if ends_cp else ""
        short = t["cm"] < SHORT_CM and all(k == "sw" for k, _ in t["ends"])
        detect = not short and t["main"] and sws
        split = t["name"] in split_names
        halves = sorted(LOOP_HALF.values()) if (t["loop"] or split) else [None]
        for half in halves:
            name = loop_placeholder(t["name"], half)
            cm = round(t["cm"] / 2, 1) if half else t["cm"]
            note = f"{cm} cm" + (" short link: inside the OS blocks of its switches, no detector" if short else
                                 "" if t["main"] else " no detector: off the main line")
            if half and split:
                note += f", half {half} of the split track (block_splits.csv)"
            elif half:
                note += f", half of the balloon loop from leg {'BC'[half - 1]}"
            add(t["level"], cp, "block", name, "", "", " / ".join(ends_cp),
                ", ".join(loop_placeholder(x, half) for x in t["trial"]), note)
            pinned = nodes.take_pinned(name)
            if not detect:
                if pinned:
                    raise MapError(f"{PINS.name} pins a detector for {name}, which the rule gives none "
                                   "(off the main line or a short link)")
                occupancy(t["level"], cp, name, notes=NO_DETECTOR)
                continue
            if pinned:                                            # the owner's input (detector_pins_main_upper.csv)
                bnode, k, packed = pinned
            elif half and half > 1:                               # wired later: no node or input yet
                occupancy(t["level"], cp, name, notes=NOT_WIRED)
                continue
            else:
                sws.sort(key=lambda s: area_of[s][0] != t["level"])      # a node on the track's own level first
                lv, area = t["level"], area_of[sws[0]][1]                 # the track's level, its switch's area
                bnode = nodes.pick(lv, area, "block", prefer=[home[s] for s in sws if area_of[s][0] == lv])
                k, packed = nodes.take(bnode, "block")
            occupancy(t["level"], cp, name, f"M2S{packed}", bnode, f"Node: {bnode} Block: {k + 1}")

    groups = [(cp.level, cp.area, cp.name, cp.switches[0]) for cp in cps]
    groups += [(loc[s].level, loc[s].area, "", s)
               for s in sorted({m["switch"] for m in ms if not m["cp"] and m["switch"]}, key=natural)]
    # heads last, once every node's boards are known: each group's masts in name order, but every two-head mast of
    # every group before any one-head mast (a stable sort), since a two-head mast takes six of a board's eight pins and
    # a one-head mast placed first would take a board of its own that a two-head mast of the area needs (owner,
    # 2026-11-19: as many heads placed as the boards hold; the rest wait as HEAD_NOT_WIRED)
    placing = [(lv, area, name, first, m) for lv, area, name, first in groups
               for m in sorted((m for m in ms if m["cp"] == name and (name or m["switch"] == first)),
                               key=lambda m: natural(m["name"]))]
    for lv, area, name, first, m in sorted(placing, key=lambda g: -g[4]["heads"]):
        parts = ["Top", "Bottom"] if m["heads"] == 2 else [""]
        kind = m["kind"]
        try:
            hnode = nodes.pick_mast(lv, area, m["heads"], prefer=[home[first]])
            heads = [(f"Head {m['name']}" + (f" {part}" if part else ""), f"IH{packed}", k, board, pin)
                     for part, (k, packed, board, pin) in zip(parts, nodes.place_mast(hnode, m["heads"]))]
            sysname = f"IF$shsm:basic:{kind}(" + ")(".join(h[1] for h in heads) + ")"
        except NoBoardRoom:
            # the draft plant has no board room left in this area: the heads wait for the wiring plan, which
            # the owner reworks once the masts are approved (2026-11-19); their virtual names do not change
            hnode, sysname = "", ""
            heads = [(f"Head {m['name']}" + (f" {part}" if part else ""), "", None, None, None) for part in parts]
        virtual = f"IF$shsm:basic:{kind}(" + ")(".join(level_devices.head_name(h[0]) for h in heads) + ")"
        if m.get("intermediate"):
            add(lv, name, "mast", f"Mast {m['name']}", sysname, hnode, f"{name or area} | intermediate",
                notes=f"intermediate signal from {m['facing']} into {m['protects']} at MP {m['name'][0]} "
                      f"{m['milepost']:.2f}", jmri=virtual, facing=m["facing"], protects=m["protects"], dir=m["dir"])
        else:
            add(lv, name, "mast", f"Mast {m['name']}", sysname, hnode, f"{name or area} | Switch {m['switch']}",
                notes=f"home signal from {m['track']}" + (f" into {m['protects']}" if m["protects"] else ""),
                jmri=virtual, switch=m["switch"], facing=m["track"], protects=m["protects"], dir=m["dir"])
        for user, sysn, k, board, pin in heads:
            if not sysn:                    # no node yet: the mast's comment says where it stands
                where = f"{name or area} | " + (f"Switch {m['switch']}" if m["switch"] else "intermediate")
                add(lv, name, "head", user, "", "", where, notes=HEAD_NOT_WIRED, jmri=level_devices.head_name(user))
                continue
            add(lv, name, "head", user, sysn, hnode,
                f"Node: {hnode} Signal: {k} | OU: {board} Ports: {pin},{pin + 1},{pin + 2}",
                jmri=level_devices.head_name(user))
    for m in planned["virtual"]:            # a destination for the visible masts' routes: hidden, no heads, no node
        sw = switches[m["switch"]]
        system = vnames[m["name"]]
        add(m["level"], sw.cp, "mast", f"Mast {m['name']}", system, "", f"{sw.cp or sw.area} | buffer stop",
            notes=f"virtual bumper mast facing {m['facing']} at its buffer stop: the destination of "
                  f"{', '.join('Mast ' + x for x in m['needed_by'])}",
            jmri=system, facing=m["facing"], dir=m["dir"])
    nodes.check_boards()
    nodes.check_pins()
    check_virtual(rows)
    order = {"turnout": 0, "fb": 1, "block": 2, "occupancy": 3, "mast": 4, "head": 5}
    assign_ports(rows)
    rows.sort(key=lambda r: (r["level"], order[r["layer"]], natural(r["user_name"])))
    return cp_keys, rows


# ---------------------------------------------------------------- staging's block layer (step 5 part 1)

STAGING_SHEET = "staging"           # staging's section of plan_overrides.json
FIELD_LEVEL = "1"                   # staging: its plant is the field, so its block rows carry their field facts
FIELD_LAYERS = ("block", "occupancy")


def part_row(level: str, name: str, part: dict, trial: str) -> dict:
    """The master row of a part (block_layer.Layer.parts): a piece of track inside another block, part_of naming it;
    no JMRI block, layout block or occupancy row of its own (hartlib.devices: role part, assignment none)."""
    t = part["track"]
    row = {c: "" for c in devices.COLUMNS}
    row.update(level=level, layer="block", role="part", user_name=name, assignment="none", trial_name=trial,
               notes=f"a piece of the {t['cm']} cm track from Switch "
                     f"{' to Switch '.join(sorted({v for k, v in t['ends'] if k == 'sw'}, key=natural))}, part of "
                     f"{part['part_of']} ({part['why']})",
               part_of=part["part_of"], written_by="build_device_map.py")
    row["description"] = devices.describe(row)
    return row


def staging_layer(bands, joined, runs, exceptions: Path | None = None) -> tuple[block_layer.Layer, int, list[dict]]:
    """(block_layer.layer of the staging band, its band index, its tracks): the one block process over staging's
    drawing, block_splits.csv and block_exceptions.csv (`exceptions`, default the committed file)."""
    overrides = layer_files.read("plan_overrides", STAGING_SHEET, OVERRIDES.parent)
    levels = band_levels(overrides)
    found = named_tracks(bands, joined, runs, overrides)
    lay = block_layer.layer(bands, runs, found, levels, block_layer.split_edges(found, levels, SPLIT),
                            block_layer.read_exceptions(found, bands, levels, exceptions))
    if len(lay.bands) != 1:
        raise MapError(f"staging is drawn on {len(lay.bands)} bands; its trial names need one")
    return lay, next(iter(lay.bands)), found


def staging_trials(band, lay: block_layer.Layer, bi: int) -> dict[str, str]:
    """{row name: trial_name} of staging's block rows in its drawing's keys (staging_device_map.placeholders: switch
    numbers and legs, which survive a new export): a row's OS placeholders, then its track pieces in strand order,
    each "Track <piece>" or, for the k-th of a piece's n rows from the piece's first end, "Track <piece> k/n"."""
    import staging_device_map as sdm        # its placeholder grammar (it imports this module)
    _turnouts, os_ph, refs = sdm.placeholders(band)
    got = defaultdict(list)
    for n, ph in os_ph.items():
        got[lay.bands[bi]["os"][n]].append(((0, ()), ph))
    for sid, names in lay.rows[bi].items():
        if sid not in refs:
            raise MapError(f"staging strand {sid} has blocks {names} but no piece key (staging_device_map.piece_refs)")
        piece, against = refs[sid]
        run = names[::-1] if against else names
        for k, row in enumerate(run, 1):
            got[row].append(((1, tuple(natural(sid))), sdm.track_placeholder(piece, k, len(run))))
    return {row: ", ".join(ph for _k, ph in sorted(phs, key=lambda x: x[0])) for row, phs in got.items()}


SPARE_RE = re.compile(r"^Node: (\d+) Block: (\d+)$")


def freed_spare(occ: dict, block: str, part_of: str) -> dict:
    """The spare row of the field detector `occ` (an occupancy row) whose block became part of `part_of`: named by its
    node input ("unused Block 1-7"), as the other spares are, with its sensor, node and wiring kept and no name-map
    columns. MapError when its wiring names no node input."""
    m = SPARE_RE.match(occ["wiring"])
    if not m or occ["assignment"] != "field":
        raise MapError(f"{occ['user_name']}: {block} is now part of {part_of}, but its detector's wiring "
                       f"{occ['wiring']!r} names no node input to keep it as a spare by; reassign the detector")
    row = dict(occ, user_name=f"unused Block {m.group(1)}-{m.group(2)}", role="spare", assignment="spare", cp="",
               blocks="", detector="", jmri_comment="", trial_name="",
               notes=f"freed when {block} became part of {part_of} (block_exceptions.csv)",
               written_by="build_device_map.py", **{c: "" for c in devices.COLUMNS if c.startswith("pnm_")})
    row["description"] = devices.describe(row)
    return row


def staging_rows(bands, joined, runs, files: devices.Files | None = None,
                 exceptions: Path | None = None) -> tuple[list[dict], set, set]:
    """(staging's block and occupancy rows of the master, the keys they take over, the keys they drop): the one block
    process's blocks
    and parts of the staging band (staging_layer), each block row and its occupancy row carrying its field facts
    (system and layout-block names, node, wiring, comment, notes, detector, stop, control point and name-map columns)
    over from the row of its name in devices.csv; this script owns the rest (role, trial_name, part_of, blocks,
    written_by, description). The spare detectors' rows are carried as they are. A helix block's occupancy row is the
    level of its helix switch's (main or upper), not staging's: the block is one across levels. A block that becomes a
    part (block_exceptions.csv gives it to an OS block) loses its JMRI block: its part row has no name-map columns, its
    detector becomes a spare row named by its node input (freed_spare), and both old keys are dropped from the name
    map on purpose (the keys returned, for hartlib.devices' drops). MapError on a block with no row to carry its field
    facts from, or a staging block or occupancy row the drawing has no block for."""
    lay, bi, _found = staging_layer(bands, joined, runs, exceptions)
    trials = staging_trials(bands[bi][1], lay, bi)
    helix = {h["block"] for h in read_helix_tracks().values()}
    prior = {(r["layer"], r["user_name"]): r for r in devices.load(files or device_files())
             if r["level"] == FIELD_LEVEL and r["layer"] in FIELD_LAYERS}
    blocks = set(lay.bands[bi]["os"].values()) | set(lay.tracks)
    out, bad, drops, freed = [], [], set(), []

    def carried(layer: str, name: str, **owned) -> dict | None:
        old = prior.pop((layer, name), None)
        if old is None or old["role"] == "part":
            bad.append(f"staging {layer} {name}: no row in {OUT.name} to carry its field facts from (add it with its "
                       "system name, node and wiring; this script then keeps it)")
            return None
        row = dict(old, written_by="build_device_map.py", part_of="", **owned)
        row["role"] = devices.role_of(layer, row["user_name"], row["system_name"], row["jmri_name"])
        row["description"] = devices.describe(row)
        return row

    for name in sorted(blocks | set(lay.parts), key=natural):
        if name in lay.parts:
            part = lay.parts[name]
            old = prior.pop(("block", name), None)      # a part's row is this script's alone
            if old is not None and old["role"] != "part":           # a block that became a part
                drops.add((FIELD_LEVEL, "block", name))
                occ = prior.pop(("occupancy", occupancy_user(name)), None)
                if occ is not None:
                    drops.add((FIELD_LEVEL, "occupancy", occ["user_name"]))
                    try:
                        freed.append(freed_spare(occ, name, part["part_of"]))
                    except MapError as exc:
                        bad.append(str(exc))
            out.append(part_row(FIELD_LEVEL, name, part, trials[name]))
        else:
            out.append(carried("block", name, trial_name=trials.get(name, "")))
    occupancy = [carried("occupancy", occupancy_user(b), blocks=b) for b in sorted(blocks - helix, key=natural)]
    spares = [dict(r, written_by="build_device_map.py") for k, r in sorted(prior.items()) if r["role"] == "spare"]
    for r in spares:
        prior.pop((r["layer"], r["user_name"]))
    taken = {r["user_name"] for r in spares}
    for r in freed:
        if r["user_name"] in taken:
            bad.append(f"{r['user_name']}: a spare of that name is in {OUT.name} already")
    spares += freed
    if prior:
        bad.append(f"staging rows of {OUT.name} the drawing has no block for: "
                   + ", ".join(f"{layer} {name}" for layer, name in sorted(prior)))
    if bad:
        raise MapError("; ".join(bad))
    out += sorted(occupancy + spares, key=lambda r: natural(r["user_name"]))
    return out, {(FIELD_LEVEL, r["layer"], r["user_name"]) for r in out}, drops


def staging_map_error() -> type:
    import staging_device_map as sdm        # it imports this module
    return sdm.StagingMapError


def check_virtual(rows) -> None:
    """The rows' virtual names follow hartlib.level_devices (hartlib.railroad.check_virtual_names, which
    `python3 -m hartlib.railroad check` also holds the written file to); MapError naming each problem."""
    bad = railroad.check_virtual_names(railroad.DeviceRow.from_dict(r) for r in rows)
    if bad:
        raise MapError("; ".join(bad))


PIN_RE = re.compile(r"^Node: (\d+) (Turnout|Signal|Sensor|Block): (\d+)$")


def assign_ports(rows) -> None:
    """Board and pins for turnout and feedback rows, as docs/wiring/README.md lays boards out: turnouts two pins
    each on 12V DNOU8 boards from OU1; feedback N then R on DNIN8 boards from IN1. Heads get theirs when placed
    (Nodes.place_mast: 5V boards after the 12V ones, R Y G on three consecutive pins, a mast's heads on one board,
    pin 8 of the first 5V board kept for detector calibration). Comments become ADR-005's
    "Node: n Turnout: k | OU: b Ports: p,q" (LCC aliases the same); occupancy keeps "Node: n Block: k"."""
    for r in rows:
        m = PIN_RE.match(r["comment"])
        if not m:
            continue
        kind, k = m.group(2), int(m.group(3))
        if kind == "Turnout":
            r["comment"] += f" | OU: {k // 4 + 1} Ports: {2 * (k % 4) + 1},{2 * (k % 4) + 2}"
        elif kind == "Sensor":
            r["comment"] += f" | IN: {k // 8 + 1} Ports: {k % 8 + 1}"


def csv_text(rows, columns=COLUMNS) -> str:
    """The CSV text of `rows` under `columns` (default: the device map's), as the schematic data files are written;
    a row with a column not in `columns` stops (ValueError)."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def overrides_text(overrides, cp_keys) -> str:
    """plan_overrides.json's whole text with its main_upper section given these control points and stations."""
    over = dict(overrides)
    over["control_points"] = cp_keys
    over["stations"] = {name: {"switches": cp["switches"], "tracks": []} for name, cp in cp_keys.items()}
    over["_control_points"] = ("Placeholder control points 'CP <lowest switch>' (owner, 2026-11-15), written by "
                               "tools/schematic/build_device_map.py from interlockings.csv; edit that "
                               "file, not this key.")
    return layer_files.texts({("plan_overrides", SHEET): over}, OVERRIDES.parent)[OVERRIDES]


def solve():
    import build_layout_le as bl
    sheet, le_mod, _core = bl.plugin()
    built = pd.solved_sheet(sheet)
    return built.bands, le_mod.partners(built.bands), bl.runs, dx_corners(built.bands, le_mod, built.opts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if an output is stale")
    args = ap.parse_args(argv)
    # the device map is its own layer: it reads the inputs only (railroad.LAYERS), never a copy of itself
    rr = railroad.Railroad(sources(), upto="inputs")
    try:
        overrides = rr.plan_overrides.data
        inputs = rr.level_control_points, rr.lcos_nodes, rr.local_switches
    except railroad.FactsError as exc:
        print(f"build_device_map.py: {exc}", file=sys.stderr)
        return 2
    import build_layout_le as bl
    try:
        bands, joined, runs, corners = solve()
    except bl.BuildError as exc:
        if not args.check:
            raise
        print(f"SKIPPED device map check: {exc}")
        return 1 if os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0
    try:
        cp_keys, rows = build(bands, joined, runs, overrides, *inputs, corners)
    except (MapError, railroad.FactsError) as exc:        # a DevicesError (reading the master) is a FactsError
        print(f"build_device_map.py: {exc}", file=sys.stderr)
        return 2
    try:
        staging, adopts, drops = staging_rows(bands, joined, runs)
        want = {OVERRIDES: overrides_text(overrides, cp_keys),
                **devices.outputs_after("build_device_map.py", rows, device_files(), master_rows=staging,
                                        adopts=adopts, drops=drops)}
    except (MapError, staging_map_error(), railroad.FactsError, layer_files.LayerFileError) as exc:
        # a DevicesError is a FactsError; a StagingMapError comes from staging's placeholder grammar
        print(f"build_device_map.py: {exc}", file=sys.stderr)
        return 2
    stale = [p for p, text in want.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
    if args.check:
        for p in stale:
            print(devices.stale_message(p, device_files(), "tools/schematic/build_device_map.py"), file=sys.stderr)
        return 1 if stale else 0
    for p in stale:
        p.write_text(want[p], encoding="utf-8")
        print(f"wrote {p.relative_to(pd.DATA.parents[4]) if len(pd.DATA.parents) > 4 else p}")
    counts = defaultdict(int)
    for r in rows:
        counts[r["layer"]] += 1
    print(", ".join(f"{v} {k}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
