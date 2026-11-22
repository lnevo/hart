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
- block_overrides.csv kind split: the owner's choice of tracks parted into two blocks at their turnback (not a rule).
- switches.csv, its main and upper rows: every other switch (yards and industry spurs) has its area there. These get a
  turnout and feedback but no control point, no signals and no detection.
- lcos_nodes.csv: every level's LCOS radio addresses. Staging's are the nodes in service (inventory v86), which this
  never hands out; main and upper's are the ones each level and area may use, in order (each row's source says
  where its address was first taken from: the upper level's from the old inventory v85, the rest from the owner's
  node grid
  media/hart-research/wiring-drafts/lcos-node-grid-2025-10-06c.xlsx, local), where an address 0XN is device X off
  node 0N.
- the solved schematic bands (the inputs publish_draft.py draws), for tracks, their ends and which way is east.

Outputs:
- plan_generated.json's main_upper section (hartlib.layer_files), keys `control_points` and `stations`: the detail
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
blocks, track blocks, halves (block_overrides.csv kind split, every level: 227-241 and staging's K-1 and K-2), helix blocks named
through plan_overrides.json, and parts (devices.csv part_of: a piece of track inside another block, by the rule or
block_overrides.csv). Staging's rows, built on the owner's field rows: device_map_staging.py.

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
  block (plan_overrides.json: Track Helix Outer from 131A, Track Helix Inner from 131B), one JMRI block with the staging
  track below it (owner, 2026-11-20): the staging device map names its staging piece, and the Layout Editor build
  binds this map's occupancy row to the one staging block. Its level_switch must be the switch the drawing gives, and
  its row marks a stop there (stop yes, the parked Dispatcher's station mark, as its staging row does; helix_stops:
  the helix stop on main and upper is at Switch 131A and 131B, owner 2026-11-20).
  A balloon loop is two blocks, "Track <n> Loop 1" from the switch's leg B and "Track <n> Loop 2" from leg C, parted
  at the turnback halfway round (owner, 2026-11-16): JMRI keys a mast by its facing and protected blocks
  (LayoutBlockManager.getFacingBean returns one), so two masts facing one loop block into one OS block would leave
  one of them out of Signal Mast Logic discovery. Loop 1 keeps the loop's detector; Loop 2's is not on a node until it is
  wired (NOT_WIRED), so no node or input assignment moves.
  A link, a track under block_layer.LINK_CM (50 cm) between two switches, is a part (devices.csv part_of) of an OS
  block (step 5 part 2, owner 2026-11-20): the lower-numbered switch's, or, where a home mast stands at a switch's
  points facing it, the OS block at its other end (the block boundary is at the mast). On main and upper a part is
  still a JMRI block and layout block of its own, drawn on the panel, whose occupancy sensor is its OS block's
  (le_tables.level_sensors): no occupancy row or detector of its own. A double crossover's link is part of the corner
  block of its leg; a part's row is on the level of its OS block's row (127-131 2, drawn on the upper band, in the
  main level's OS Switch 127).
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
- wiring.csv's turnout, fb and head rows of main and upper: a control point wired and frozen
  (tools/wiring/freeze_wiring.py, owner 2026-11-20). Each frozen device keeps its node, LCOS number and pins on every
  build (Nodes.freeze), and the rule hands them to nothing else; its detectors are pins (read_pins: an OS block by its
  name, a helix block by its name, a track by its end switches). The JMRI names stay virtual: freezing fixes the
  wiring only.
- Hand lists keyed by end switches (block_overrides.csv, with a level column, and wiring.csv's main and upper detectors; source-data row 5; running
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
import mast_rule  # noqa: E402  read_block_splits, OVERRIDES_NAME
from hartlib import devices, layer_files, level_devices, level_masts, railroad, wiring  # noqa: E402  names, facts, the master
import device_map_inputs as inputs  # noqa: E402  the readers: wiring.csv, lcos_nodes.csv, the places
from device_map_inputs import (  # noqa: E402,F401  re-exported: callers read them from this module
    CPS, FIELD_LEVEL, NODES, OS_BLOCK, PINS, STATIONS, UID, WIRING, Places, StagingPin, frozen_wires, helix_pins,
    loop_placeholder, read_places, read_staging_pins, staging_nodes, wiring_rows)
from device_map_staging import (  # noqa: E402,F401  staging's rows; re-exported: callers read them from this module
    BEAN_NAME, FIELD_LAYERS, PART_BLOCK_FIRST, STAGING_SHEET, WIRED_LAYERS, alias_note, field_row, helix_ends,
    level_trials, line_cp, new_spare, part_bean_names, part_row, piece_trials, staging_field, staging_layer,
    staging_part_names, staging_rows, staging_trials, staging_wired_rows, taken_bean_names, wire_block, wire_occupancy)
from device_map_schematic import (  # noqa: E402,F401  the drawing's tracks; re-exported: callers read them here
    block_overrides, check_helix_ends, corner_blocks_of, dx_corners, helix_stops, helix_tracks, home_and_posts,
    labels_by_level, line_role, loop_halves, main_upper_layer, named_tracks, overrides_keys, read_pins, split_edges,
    split_tracks, xover_corners)

SOURCES = inputs.SOURCES
SWITCHES = SOURCES.switches                     # switches.csv: its main and upper rows give the local switches' areas
OVERRIDES = SOURCES.plan_overrides               # plan_overrides.json, the owner's hand edits (read only)
GENERATED = layer_files.path(layer_files.GENERATED, OVERRIDES.parent)   # plan_generated.json: this writes its main_upper keys
SHEET = railroad.PlanOverrides.SHEET
OUT = SOURCES.devices                             # devices.csv, whose levels 2 and 3 this script writes
LEVELS = band_levels(layer_files.read("plan_overrides", SHEET, OVERRIDES.parent))     # {band title: level} of main and upper
STAGING_LEVEL = 1                                 # staging: its nodes are as built (lcos_nodes.csv)

def device_files() -> devices.Files:
    """The master and its generated files as main() writes them: OUT, as it is when it runs (a test may patch it)."""
    return devices.Files.under(OUT.parent)


def sources() -> railroad.Sources:
    """The files main() reads and writes: the module's paths as they are when it runs (a test may patch them)."""
    return railroad.Sources.under().but(interlockings=CPS, lcos_nodes=NODES, switches=SWITCHES,
                                        plan_overrides=OVERRIDES, devices=OUT)

CAP = {"turnout": 8, "block": 8, "signal": 16, "sensor": 16}
MAX_OU = 4                            # DNOU8 boards per node: the most any node has in LCOS_Layout_Inventory_v85
COLUMNS = list(railroad.DEVICE_COLUMNS)
DCC_FIRST = 120                       # staging uses 100-119 (MTT100-MTT119); the owner continues from 120
VIRTUAL_TURNOUT = level_devices.TURNOUT_PREFIX   # + switch number: the internal turnout the panels and desks use
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


# ---------------------------------------------------------------- LCOS nodes

class NoBoardRoom(MapError):
    """The draft plant has no 5V board room left in an area for a mast's heads: the heads wait for the wiring plan
    (HEAD_NOT_WIRED). Any other MapError still stops the build."""


class Nodes:
    """Hands out LCOS UIDs per node, in each level and area's node order. Staging's rows of lcos_nodes.csv are the
    nodes as built, never handed out or pinned here."""

    def __init__(self, rows):
        self.pool = defaultdict(list)
        for r in rows:
            if r.level != STAGING_LEVEL:
                self.pool[(r.level, r.area)].append(r.node)
        self.used = defaultdict(lambda: defaultdict(int))
        self.taken = defaultdict(set)         # (node, what) -> the indices given out or pinned
        self.pins = {}                        # block -> (node, index): wiring.csv's main and upper detectors
        self.boards = defaultdict(lambda: defaultdict(set))   # node -> {OU board: the pins its heads use}
        self.frozen = {}                      # (kind, device) -> wiring.csv's Wire of a frozen main or upper device
        self.turnout_boards = defaultdict(set)  # node -> the OU boards its frozen turnouts are on (12V)
        self.frozen_turnouts = defaultdict(set)  # node -> its frozen turnouts' LCOS numbers

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

    def freeze(self, wires):
        """Hold the node, LCOS number and pins of each frozen main or upper device (wiring.csv's turnout, fb and head
        rows of levels 2 and 3: a control point wired and frozen, freeze_wiring.py) before any other is given out,
        so the rule hands them to nothing else and gives the device the same values again (take_frozen)."""
        known = {n for nodes in self.pool.values() for n in nodes}
        what = {"turnout": "turnout", "fb": "sensor", "head": "signal"}
        for w in wires:
            if w.node not in known:
                raise MapError(f"{PINS.name} line {w.line}: {w.device} is on node {w.node}, which {NODES.name} does "
                               "not list for main or upper")
            self.taken[(w.node, what[w.kind])].add(w.index)
            self.used[w.node][what[w.kind]] += 1
            if w.kind == "head":                     # its pins, on one board or two
                for board, port in w.pins:
                    self.boards[w.node][int(board[2:])].add(port)
            elif w.kind == "turnout":
                self.turnout_boards[w.node].add(int(w.board[2:]))
                self.frozen_turnouts[w.node].add(w.index)
            self.frozen[(w.kind, w.device)] = w

    def take_frozen(self, kind, device):
        """wiring.csv's Wire of a frozen device, once; None when it is not frozen."""
        return self.frozen.pop((kind, device), None)

    def check_frozen(self):
        """Stop when a frozen row names a device the map does not give (a stale or misspelt row)."""
        if self.frozen:
            raise MapError(f"{PINS.name}: frozen rows for devices the device map does not give: "
                           f"{sorted(f'{k} {d}' for k, d in self.frozen)}")

    def room(self, node, what, n=1):
        return self.used[node][what] + n <= CAP[what]

    def staging(self, level):
        if level == STAGING_LEVEL:
            raise MapError(f"level {level} is staging: its nodes in {NODES.name} are as built, and the rule hands "
                           "none out")

    def pick(self, level, area, what, n=1, prefer=()):
        self.staging(level)
        for node in list(prefer) + self.pool[(level, area)]:
            if self.room(node, what, n):
                return node
        raise MapError(f"level {level} {area}: no LCOS node left with room for {n} {what}(s); "
                       f"add one to {NODES.name}")

    def take(self, node, what):
        """The node's lowest free index of `what` (one a pin holds is not free), and its packed id. A turnout's index
        is its board (index // 4 + 1, assign_ports): one on a board a frozen head is on is not free."""
        heads = {b for b, used in self.boards[node].items() if used}
        k = next((i for i in range(CAP[what]) if i not in self.taken[(node, what)]
                  and not (what == "turnout" and i // 4 + 1 in heads)), None)
        if k is None:
            raise MapError(f"node {node}: no {what} left (frozen heads in wiring.csv hold boards {sorted(heads)})")
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
    def twelve(self, node):
        """The node's turnout boards (12V): the rule's turnouts' (index // 4 + 1, assign_ports) and the frozen
        turnouts' own boards."""
        rule = {k // 4 + 1 for k in self.taken[(node, "turnout")] if k not in self.frozen_turnouts[node]}
        return rule | self.turnout_boards[node]

    def n12(self, node):
        """The node's last 12V board, the highest a turnout is on (0 with none): the rule's heads go after it."""
        return max(self.twelve(node), default=0)

    def _free(self, node, board):
        """The pins of one 5V OU board a head may use: all eight but those taken, and pin 8 of the first 5V board on a
        node with detectors (its calibration relay)."""
        cal = board == self.n12(node) + 1 and self.used[node]["block"]
        return [p for p in range(1, 9) if p not in self.boards[node][board] and not (cal and p == 8)]

    def five_volt(self, node):
        """The node's 5V boards with a head on them, in board order."""
        return sorted(b for b, used in self.boards[node].items() if used and b > self.n12(node))

    def _fit(self, node, pins):
        """(OU board, first pin) where `pins` consecutive pins fit, or None: the lowest run on the first 5V board with
        room (any of them, not only the last), else the next new board while the node has OU room."""
        last = max([self.n12(node)] + self.five_volt(node))
        for board in range(self.n12(node) + 1, last + 2):
            if board > MAX_OU:
                break
            free = set(self._free(node, board))
            for first in range(1, 10 - pins):
                if all(p in free for p in range(first, first + pins)):
                    return board, first
        return None

    def pick_mast(self, level, area, heads, prefer=()):
        self.staging(level)
        for node in list(prefer) + self.pool[(level, area)]:
            if self.room(node, "signal", heads) and self._fit(node, 3 * heads):
                return node
        raise NoBoardRoom(f"level {level} {area}: no LCOS node left with board room for a {heads}-head mast; "
                       f"add one to {NODES.name}")

    def place_mast(self, node, heads):
        """[(signal index, packed id, OU board, first pin)] for the mast's heads, on one 5V board."""
        board, first = self._fit(node, 3 * heads)
        out = []
        for h in range(heads):
            k, packed = self.take(node, "signal")
            out.append((k, packed, board, first + 3 * h))
        self.boards[node][board].update(range(first, first + 3 * heads))
        return out

    def check_boards(self):
        """A node with detectors needs a 5V board for the calibration pin; no node may need more than MAX_OU; no head
        is on a 12V board, or on a detector node's calibration relay pin (pin 8 of its first 5V board)."""
        for node, boards in self.boards.items():
            n12 = self.n12(node)
            on12 = sorted(b for b, used in boards.items() if used and b in self.twelve(node))
            if on12:
                raise MapError(f"node {node}: heads on OU{', OU'.join(map(str, on12))}, a 12V board a turnout is on; "
                               "move the frozen head or turnout in wiring.csv")
            if self.used[node]["block"] and 8 in boards.get(n12 + 1, set()):
                raise MapError(f"node {node}: a head is on OU{n12 + 1}-8, the calibration relay's pin of a node with "
                               "detectors; move it in wiring.csv")
        for node, used in self.used.items():
            five = max(len(self.five_volt(node)), 1 if used["block"] else 0)
            if self.n12(node) + five > MAX_OU:
                raise MapError(f"node {node} needs {self.n12(node) + five} DNOU8 boards; the limit is {MAX_OU}")


# ---------------------------------------------------------------- the map


def plan_masts(bands, joined, runs, found, cp_of: dict, corners: dict | None
               ) -> tuple[dict, dict, set, block_layer.Layer]:
    """(mast_plan.plan's masts of the main and upper levels, the double crossovers' corner blocks, the split track
    names, the block layer): the one mast process over this level's block layer (main_upper_layer) and the owner's
    block splits. Each home mast gains `facing`, the block of the track it faces (its track's: a part is a JMRI block
    of its own). MapError on a double crossover with no corners given."""
    corner_blocks = corner_blocks_of(bands, corners)
    split = split_edges(found=found)
    home, posts = home_and_posts(bands, joined, found, LEVELS, cp_of, corner_blocks, set(split.values()))
    lay = main_upper_layer(bands, runs, found, split, corner_blocks, posts)
    got = mast_plan.plan(bands, joined, found, levels=LEVELS, cp_of=cp_of, layer=lay.bands, cm=lay.cm,
                         corner_blocks=corner_blocks, split=set(split.values()), home=home)
    for m in got["home"]:
        m["facing"] = m["track"]
    return got, corner_blocks, set(split.values()), lay


def master_virtual_names(files: devices.Files | None = None) -> dict:
    """{mast: system name} of the main and upper virtual masts as this script last wrote them (each keeps its
    ordinal): name memory, its one read-back of its own output (devices.allocated_names)."""
    return {u: r["jmri_name"] for u, r in devices.allocated_names(("2", "3"), "mast", files=files or device_files()).items()
            if level_masts.virtual_ordinal(r["jmri_name"])}


def check_frozen_cps(rows: list[dict], cps: frozenset, held_devices: set, held_blocks: set) -> None:
    """A control point wiring.csv holds (frozen) is read from it and proposed for no more: stop on a device the rule
    gave one of its rows (a turnout, feedback or head on a node, or a detector input) that wiring.csv does not
    hold. A switch added to a frozen control point is wired and frozen again (make wiring-freeze)."""
    bad = []
    for r in rows:
        if r["cp"].split(devices.LIST)[0] not in cps or not r["node"] or r["role"] == "lcc_alias":
            continue
        if r["layer"] in ("turnout", "fb", "head") and (r["layer"], r["user_name"]) not in held_devices:
            bad.append(f"{r['layer']} {r['user_name']}")
        elif r["layer"] == "occupancy" and r["system_name"] and r["blocks"] not in held_blocks:
            bad.append(f"occupancy of {r['blocks']}")
    if bad:
        raise MapError(f"{PINS.name}: control point(s) {', '.join(sorted(cps))} are frozen, but the rule proposes "
                       f"{', '.join(sorted(bad))} for them: wire and freeze again (make wiring-freeze CP=...)")


def build(bands, joined, runs, overrides, cps, node_rows, local=(), corners=None, helix=None, pins=None, places=None,
          virtual_names=None, frozen=None) -> tuple[dict, list[dict], list[dict]]:
    """(control_points, device map rows, the parts' master rows: links inside an OS block, part_row). `local`: the switches in no control point (the local switches of switches.csv
    rows). Every switch on the main and upper bands must be in exactly one of the two. `corners`: dx_corners, needed
    when a band has a double crossover. `helix`: read_helix_tracks (None: plan_overrides.json; {}: no helix tracks);
    `pins`: read_pins (None: wiring.csv's detectors, resolved against the tracks found here); `virtual_names`:
    {mast: system name} of the virtual masts that have one already (None: master_virtual_names); `frozen`:
    frozen_wires (None: wiring.csv's); `places`: read_places (None: stations.csv's and interlockings.csv's), the cp of
    every line block (line_cp)."""
    helix = helix_tracks() if helix is None else helix
    places = read_places() if places is None else places
    by_level = labels_by_level(bands)
    cp_keys = overrides_keys(cps, by_level)
    try:
        switches = railroad.join_main_upper(cps, local, SWITCHES.name)
    except railroad.FactsError as exc:
        raise MapError(str(exc)) from None
    cp_of = {s: sw.cp for s, sw in switches.items() if sw.cp}
    loc = {s: sw for s, sw in switches.items() if not sw.cp}          # in no control point: level, area, notes
    on_bands = {base(lb) for labels in by_level.values() for lb in labels}
    missing = sorted(on_bands - set(cp_of) - set(loc), key=natural)
    if missing:
        raise MapError(f"switch {', '.join(missing)} is in no control point and not a local switch (an area) "
                       f"in {SWITCHES.name}")
    found = named_tracks(bands, joined, runs, overrides, helix)
    check_helix_ends(bands, joined, found, helix)
    stops = helix_stops(helix)              # check_helix_ends: each helix track ends at its level_switch
    planned, corner_blocks, split_names, lay = plan_masts(bands, joined, runs, found, cp_of, corners)
    if lay.inside:          # the main and upper drawing gives each strand one block: a piece there is a part
        raise MapError(f"{mast_rule.OVERRIDES_NAME} keeps {', '.join(sorted(lay.inside))} inside an OS block on "
                       "main or upper, whose drawing gives each strand one block; leave inside empty (a part)")
    trials = level_trials(bands, joined, lay)

    def trial_of(name: str) -> str:
        if name not in trials:
            raise MapError(f"{name}: the block layer draws it on no strand, so it has no trial name")
        return trials[name]

    dxs = set(corner_blocks)
    os_pin_level = {}                       # an OS block pinned by its name: the level its row gives (checked below)
    if pins is None:
        pins = read_pins(found=found, split=split_names)
        os_pin_level = {w.device: w.level for w in wiring_rows() if w.kind == "detector" and w.device
                        and OS_BLOCK.fullmatch(w.device)}
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
    held_wires = frozen_wires() if frozen is None else frozen
    nodes.freeze(held_wires)
    frozen_cps = frozenset(cp for w in held_wires if (cp := wiring.frozen_cp(w)))
    held_devices, held_blocks = {(w.kind, w.device) for w in held_wires}, set(pins)
    rows = []

    def add(level, cp, layer, user, system="", node="", comment="", trial="", notes="", dcc="", jmri="", *, role,
            **facts):
        """A device-map row with the role (hartlib.devices.ROLES) its caller says it has: no role is read off a name."""
        rows.append(dict(level=level, cp=cp, layer=layer, user_name=user, system_name=system, jmri_name=jmri,
                         node=node, dcc=dcc, comment=comment, trial_name=trial, notes=notes, role=role,
                         **{c: facts.pop(c, "") for c in railroad.DEVICE_FACTS}))
        if facts:
            raise MapError(f"{layer} {user}: unknown fact columns {sorted(facts)}")

    def occupancy(level, cp, block, system="", node="", comment="", notes="", *, role):
        """The occupancy row of `block`, whose role (`role`) it shares: its virtual sensor (jmri_name), the block it
        serves and its detector: planned on an input (`system`, M2S), planned with no input yet (NOT_WIRED) or none
        planned (NO_DETECTOR)."""
        detector = "planned" if system else {NOT_WIRED: "not_wired", NO_DETECTOR: "none"}.get(notes)
        if detector is None:
            raise MapError(f"occupancy of {block}: no detector and no reason why ({notes!r})")
        add(level, cp, "occupancy", occupancy_user(block), system, node, comment, notes=notes,
            jmri=block_sensor(block), blocks=block, detector=detector, role=role)

    dcc = {s: DCC_FIRST + i for i, s in enumerate(sorted(set(cp_of) | set(loc), key=natural))}
    home, area_of = {}, {}                  # switch -> its turnout's node, its area

    def switch_rows(lv, area, name, s, node, note=""):
        frozen = nodes.take_frozen("turnout", f"Switch {s}")    # wired and frozen (wiring.csv): its own values
        if frozen:
            node, k, packed = frozen.node, frozen.index, frozen.node * 100 + UID["turnout"] + frozen.index
            where = frozen.wiring_text
        else:
            k, packed = nodes.take(node, "turnout")
            where = f"Node: {node} Turnout: {k}"
        home[s], area_of[s] = node, (lv, area)
        halves = sorted({lb for labels in by_level.values() for lb in labels if base(lb) == s}, key=natural)
        add(lv, name, "turnout", f"Switch {s}", f"M2T{packed}", node, where,
            ", ".join(f"Switch {lb}" for lb in halves), note, dcc[s], jmri=VIRTUAL_TURNOUT + s, role="turnout")
        add(lv, name, "turnout", f"DCC Switch {s}", f"MTT{dcc[s]}", node, where,
            notes="LCC alias of the MQTT turnout (ADR-005)", dcc=dcc[s], jmri=VIRTUAL_TURNOUT + s, role="lcc_alias")
        for nr in "NR":
            fb = nodes.take_frozen("fb", f"FB Switch {s} {nr}")
            if fb:
                add(lv, name, "fb", f"FB Switch {s} {nr}", fb.address, fb.node, fb.wiring_text, role="fb")
                continue
            fnode = nodes.pick(lv, area, "sensor", prefer=[node])
            kk, pp = nodes.take(fnode, "sensor")
            add(lv, name, "fb", f"FB Switch {s} {nr}", f"M2S{pp}", fnode, f"Node: {fnode} Sensor: {kk}", role="fb")

    CORNER = "xover_corner"                     # a double crossover's corner block and its occupancy row

    def os_rows(lv, area, name, s, comment, detect=True):
        if s in dxs:                            # a double crossover: a block per corner, corner a detected
            for block in sorted(corner_blocks[s].values()):
                note = f"corner {block[-1].upper()} of the double crossover"
                if not detect:
                    add(lv, name, "block", block, "", "", comment, block, note + ", no detector: off the main line",
                        role=CORNER)
                    occupancy(lv, name, block, notes=NO_DETECTOR, role=CORNER)
                elif not block.endswith("a"):             # wired later: no node or input yet
                    add(lv, name, "block", block, "", "", comment, block, note, role=CORNER)
                    occupancy(lv, name, block, notes=NOT_WIRED, role=CORNER)
                else:                                     # corner a keeps the switch's detector
                    pinned = nodes.take_pinned(block)
                    if pinned and os_pin_level.get(block, lv) != lv:
                        raise MapError(f"{PINS.name}: {block} is a level {lv} block, not level {os_pin_level[block]}")
                    if pinned:
                        bnode, k, packed = pinned
                    else:
                        bnode = nodes.pick(lv, area, "block", prefer=[home[s]])
                        k, packed = nodes.take(bnode, "block")
                    add(lv, name, "block", block, "", bnode, comment, block, note, role=CORNER)
                    occupancy(lv, name, block, f"M2S{packed}", bnode, f"Node: {bnode} Block: {k + 1}", role=CORNER)
            return
        block = f"OS Switch {s}"
        if not detect:
            add(lv, name, "block", block, "", "", comment, block, "no detector: off the main line", role="os")
            occupancy(lv, name, block, notes=NO_DETECTOR, role="os")
            return
        pinned = nodes.take_pinned(block)
        if pinned and os_pin_level.get(block, lv) != lv:
            raise MapError(f"{PINS.name}: {block} is a level {lv} block, not level {os_pin_level[block]}")
        if pinned:
            bnode, k, packed = pinned
        else:
            bnode = nodes.pick(lv, area, "block", prefer=[home[s]])
            k, packed = nodes.take(bnode, "block")
        add(lv, name, "block", block, "", bnode, comment, block, role="os")
        occupancy(lv, name, block, f"M2S{packed}", bnode, f"Node: {bnode} Block: {k + 1}", role="os")

    for cp in cps:                               # turnouts first: a node's 12V boards come before its 5V boards
        loose = [s for s in cp.switches if ("turnout", f"Switch {s}") not in nodes.frozen]
        node = nodes.pick(cp.level, cp.area, "turnout", len(loose)) if loose else None
        for s in cp.switches:
            switch_rows(cp.level, cp.area, cp.name, s, node)
    for s in sorted(loc, key=natural):           # no control point: turnout and feedback, no signals or detection
        r = loc[s]
        node = nodes.pick(r.level, r.area, "turnout") if ("turnout", f"Switch {s}") not in nodes.frozen else None
        switch_rows(r.level, r.area, "", s, node, "no control point: " + r.notes)
    for cp in cps:
        for s in cp.switches:
            os_rows(cp.level, cp.area, cp.name, s, cp.name)
    for s in sorted(loc, key=natural):
        os_rows(loc[s].level, loc[s].area, "", s, loc[s].area, detect=False)

    part_rows = []
    for name, part in sorted(lay.parts.items(), key=lambda kv: natural(kv[0])):
        if name != part["track"]["name"]:
            raise MapError(f"{name}: a piece at one end of a main or upper track ({part['why']}); the main and upper "
                           "drawing gives each strand one block, so give the whole track to an OS block")
        # the part's row is on the level of the OS block's row, its switch's (a link between the halves of the
        # crossovers 127 and 131 drawn on the upper band is in a main level OS block)
        m = re.fullmatch(r"OS Switch (\d+)[a-d]?", part["part_of"])
        if not m or m.group(1) not in switches:
            raise MapError(f"{name} (level {part['level']}) is part of {part['part_of']}, the OS block of no main or "
                           "upper switch")
        lv = str(switches[m.group(1)].level)
        part_rows.append(dict(part_row(lv, name, part, trial_of(name)), cp=line_cp(name, lv, part["track"], places)))
    for t in sorted(found, key=lambda t: natural(t["name"])):
        sws = [v for k, v in t["ends"] if k == "sw"]
        stray = [s for s in sws if s not in area_of]
        if stray:
            raise MapError(f"{t['name']} ends at switch {', '.join(stray)}, which is on neither the main nor the "
                           "upper level")
        if t["name"] in lay.parts:                  # a link inside an OS block: its part row, no block or detector
            continue
        ends_cp = sorted({cp_of[v] for v in sws if v in cp_of}, key=natural)
        detect = t["main"] and sws
        split = t["name"] in split_names
        halves = sorted(LOOP_HALF.values()) if (t["loop"] or split) else [None]
        for half in halves:
            name, role = loop_placeholder(t["name"], half), line_role(t, half)
            cp = line_cp(name, t["level"], t, places, helix_ends(helix))
            cm = round(t["cm"] / 2, 1) if half else t["cm"]
            note = f"{cm} cm" + ("" if t["main"] else " no detector: off the main line")
            if half and split:
                note += f", half {half} of the split track ({mast_rule.OVERRIDES_NAME})"
            elif half:
                note += f", half of the balloon loop from leg {'BC'[half - 1]}"
            add(t["level"], cp, "block", name, "", "", " / ".join(ends_cp),
                trial_of(name), note, stop="yes" if name in stops else "", role=role)
            pinned = nodes.take_pinned(name)
            if not detect:
                if pinned:
                    raise MapError(f"{PINS.name} pins a detector for {name}, which the rule gives none "
                                   "(off the main line)")
                occupancy(t["level"], cp, name, notes=NO_DETECTOR, role=role)
                continue
            if pinned:                                            # the owner's input (wiring.csv)
                bnode, k, packed = pinned
            elif half and half > 1:                               # wired later: no node or input yet
                occupancy(t["level"], cp, name, notes=NOT_WIRED, role=role)
                continue
            else:
                sws.sort(key=lambda s: area_of[s][0] != t["level"])      # a node on the track's own level first
                lv, area = t["level"], area_of[sws[0]][1]                 # the track's level, its switch's area
                bnode = nodes.pick(lv, area, "block", prefer=[home[s] for s in sws if area_of[s][0] == lv])
                k, packed = nodes.take(bnode, "block")
            occupancy(t["level"], cp, name, f"M2S{packed}", bnode, f"Node: {bnode} Block: {k + 1}", role=role)

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
        users = [f"Head {m['name']}" + (f" {part}" if part else "") for part in parts]
        frozen = [nodes.take_frozen("head", u) for u in users]
        try:
            if any(frozen):                          # wired and frozen (wiring.csv): every head of the mast, one node
                if not all(frozen) or len({w.node for w in frozen}) != 1:
                    raise MapError(f"Mast {m['name']}: wiring.csv freezes {sum(map(bool, frozen))} of its "
                                   f"{len(users)} head(s), or puts them on two nodes; freeze the mast whole")
                hnode = frozen[0].node
                heads = [(u, w.address, w.index, w.port_text) for u, w in zip(users, frozen)]
            else:
                hnode = nodes.pick_mast(lv, area, m["heads"], prefer=[home[first]])
                heads = [(u, f"IH{packed}", k, f"OU: {board} Ports: {pin},{pin + 1},{pin + 2}")
                         for u, (k, packed, board, pin) in zip(users, nodes.place_mast(hnode, m["heads"]))]
            sysname = f"IF$shsm:basic:{kind}(" + ")(".join(h[1] for h in heads) + ")"
        except NoBoardRoom:
            # the draft plant has no board room left in this area: the heads wait for the wiring plan, which
            # the owner reworks once the masts are approved (2026-11-19); their virtual names do not change
            hnode, sysname = "", ""
            heads = [(f"Head {m['name']}" + (f" {part}" if part else ""), "", None, None) for part in parts]
        virtual = f"IF$shsm:basic:{kind}(" + ")(".join(level_devices.head_name(h[0]) for h in heads) + ")"
        if m.get("intermediate"):
            add(lv, name, "mast", f"Mast {m['name']}", sysname, hnode, f"{name or area} | intermediate",
                notes=f"intermediate signal from {m['facing']} into {m['protects']} at MP {m['name'][0]} "
                      f"{m['milepost']:.2f}", jmri=virtual, facing=m["facing"], protects=m["protects"], dir=m["dir"],
                role="intermediate")
        else:
            add(lv, name, "mast", f"Mast {m['name']}", sysname, hnode, f"{name or area} | Switch {m['switch']}",
                notes=f"home signal from {m['track']}" + (f" into {m['protects']}" if m["protects"] else ""),
                jmri=virtual, switch=m["switch"], facing=m["facing"], protects=m["protects"], dir=m["dir"],
                role="home")
        for user, sysn, k, ports in heads:
            if not sysn:                    # no node yet: the mast's comment says where it stands
                where = f"{name or area} | " + (f"Switch {m['switch']}" if m["switch"] else "intermediate")
                add(lv, name, "head", user, "", "", where, notes=HEAD_NOT_WIRED, jmri=level_devices.head_name(user),
                    role="head")
                continue
            add(lv, name, "head", user, sysn, hnode,
                f"Node: {hnode} Signal: {k} | {ports}",
                jmri=level_devices.head_name(user), role="head")
    for m in planned["virtual"]:            # a destination for the visible masts' routes: hidden, no heads, no node
        sw = switches[m["switch"]]
        system = vnames[m["name"]]
        add(m["level"], sw.cp, "mast", f"Mast {m['name']}", system, "", f"{sw.cp or sw.area} | buffer stop",
            notes=f"virtual bumper mast facing {m['facing']} at its buffer stop: the destination of "
                  f"{', '.join('Mast ' + x for x in m['needed_by'])}",
            jmri=system, facing=m["facing"], dir=m["dir"], role="hidden")
    nodes.check_boards()
    nodes.check_pins()
    nodes.check_frozen()
    check_frozen_cps(rows, frozen_cps, held_devices, held_blocks)
    check_virtual(rows)
    order = {"turnout": 0, "fb": 1, "block": 2, "occupancy": 3, "mast": 4, "head": 5}
    assign_ports(rows)
    rows.sort(key=lambda r: (r["level"], order[r["layer"]], natural(r["user_name"])))
    return cp_keys, rows, part_rows


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


def generated_text(cp_keys) -> str:
    """plan_generated.json's whole text with its main_upper section given these control points and stations (the
    hand file is not read or written; nothing here comes from the section's own earlier keys)."""
    over = {}
    over["control_points"] = cp_keys
    over["stations"] = {name: {"switches": cp["switches"], "tracks": []} for name, cp in cp_keys.items()}
    over["_control_points"] = ("Placeholder control points 'CP <lowest switch>' (owner, 2026-11-15), written by "
                               "tools/schematic/build_device_map.py from interlockings.csv; edit that "
                               "file, not this key.")
    return layer_files.generated_texts({SHEET: over}, OVERRIDES.parent)[GENERATED]


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
        cp_keys, rows, parts = build(bands, joined, runs, overrides, *inputs, corners)
    except (MapError, railroad.FactsError) as exc:        # a DevicesError (reading the master) is a FactsError
        print(f"build_device_map.py: {exc}", file=sys.stderr)
        return 2
    try:
        staging = staging_rows(bands, joined, runs)
        wired = staging_wired_rows()
        want = {GENERATED: generated_text(cp_keys),
                **devices.outputs_after("build_device_map.py", rows, device_files(),
                                        master_rows=staging + wired + parts)}
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
