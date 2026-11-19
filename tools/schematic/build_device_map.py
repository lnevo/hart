#!/usr/bin/env python3
"""Placeholder control points and device names for the main and upper levels.

    python3 tools/schematic/build_device_map.py           # write both outputs
    python3 tools/schematic/build_device_map.py --check   # exit 1 if either output is stale

--check prints SKIPPED and exits 0 when the plugin submodule is not checked out (1 with SCHEMATIC_REQUIRED=1).

Inputs (jmri/layouts/hart/data/schematic/):
- control_points_main_upper.csv: the placeholder control points, "CP <lowest switch>" (owner, 2026-11-15).
  Hand data, one row per control point: level (2 main, 3 upper), switch numbers, area. Only interlockings that
  affect the main route are control points, as in the bench plans (docs/wiring/bench/control_point_4 to 6):
  switches on the main route, grouped where they stand close together.
- local_switches_main_upper.csv: every other switch (yards and industry spurs), with its area. These get a
  turnout and feedback but no control point, no signals and no detection.
- lcos_nodes_main_upper.csv: the LCOS radio addresses each level and area may use, in order: the upper level's
  from LCOS_Layout_Inventory_v85.xlsx, the rest from the owner's node grid
  (media/hart-research/wiring-drafts/lcos-node-grid-2025-10-06c.xlsx, local), where an address 0XN is device X off
  node 0N.
- the solved schematic bands (the inputs publish_draft.py draws), for tracks, their ends and which way is east.

Outputs:
- main_upper.plan_overrides.json, keys `control_points` and `stations`: the detail sheets (the "Main level" and
  "Upper level" sheets of main_upper.preferences.json) draw each control point's interlocking limits and name,
  and the overall sheet a bar per control point (no car count). A control point may list only switches on one
  band, so a crossover whose halves sit on two bands (129, 135) lists the half on the control point's level. The
  bars make the page taller; at the smaller scale the plugin's label check counts 7 milepost labels against their
  markers (draft, 2026-11-15; labels are placed before the page is scaled).
- device_map_main_upper.csv: the one mapping from each main and upper JMRI device to its planned physical part. Per
  row: the user name under ADR-005; jmri_name, the virtual device tables.xml and the CATS desks use now; system_name,
  the planned physical device (LCOS, a DRAFT: the main and upper plant is not reviewed yet, owner 2026-11-17). Later
  a physical device is swapped in by this mapping alone, so no JMRI name ever comes from a draft address or from
  drawing order. Placeholder user names change when the owner names the levels.

Virtual names (owner, 2026-11-17), from each device's stable identity:
- Turnout "Switch <n>" (and its LCC alias "DCC Switch <n>"): IT:HART:C3:<n>.
- Every block has one occupancy row, its sensor IS:HART:C3:B:<block_key> (hartlib.level_devices: the block name with
  "Track "
  dropped, "OS Switch " shortened to "OS", spaces to "_": IS:HART:C3:B:107-109, IS:HART:C3:B:107_Loop_2,
  IS:HART:C3:B:OS225b). Its system_name is the planned detector (M2S), or empty: NOT_WIRED for a detector planned
  but not on a node yet, NO_DETECTOR for a block that has none planned (dark until decided).
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
- Track "Track <a>-<b>" from its end switches (numbers, H1 or H2 for a helix), "Track <n> Spur" to a bumper,
  "Track <n> Loop" back to the same switch; parallel tracks between the same ends take " 1", " 2" from the top row.
  A balloon loop is two blocks, "Track <n> Loop 1" from the switch's leg B and "Track <n> Loop 2" from leg C, parted
  at the turnback halfway round (owner, 2026-11-16): JMRI keys a mast by its facing and protected blocks
  (LayoutBlockManager.getFacingBean returns one), so two masts facing one loop block into one OS block would leave
  one of them out of Signal Mast Logic discovery. Loop 1 keeps the loop's detector; Loop 2's is not on a node until it is
  wired (NOT_WIRED), so no node or input assignment moves.
  A track under SHORT_CM between two switches gets a block but no detector (it would sit inside their OS blocks).
- Detection on the main line only (owner, 2026-11-15): main-route tracks and the OS blocks of control point
  switches get a planned detector; yard and industry tracks and the OS blocks of switches in no control point
  get none (their virtual sensor stays, NO_DETECTOR).
- Home signals: one mast where each track from outside a control point meets one of its switches; none on spurs
  or yard tracks that end at a bumper. "Mast <n+1><L|R>", L for a westbound train (ADR-005), A/B when one number
  and direction has two. Two heads (Top and Bottom) when a route the mast governs meets facing points inside its
  control point before the next signal (mast_rule.facing_on_route), else one; high (searchlight) facing from running
  track, a dwarf (low) from a yard, lead or siding (owner, 2026-11-19). East is the schematic's (ADR-022 amendment: away from the helix on these levels).
- LCOS packed IDs are node * 100 + UID (external/lcos-bridge): blocks UID 0-7 (BS, "Node: n Block: k+1"), turnouts
  8-15 (M2T, "Node: n Turnout: k"), signals 32-47 (IH, "Node: n Signal: k"), inputs from 67 (M2S, feedback N then R
  per turnout, "Node: n Sensor: k"). A control point's turnouts stay on one node; switches in no control point
  follow, area by area.
- DCC addresses continue from staging's last (119): 120 up in switch-number order, main level first (owner,
  2026-11-15). Each turnout also gets its LCC alias "DCC Switch <n>" (MTT<dcc>, same node comment, as staging has).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA, GRAPHS, INPUTS and the pinned plugin
from mast_rule import (  # noqa: E402,F401  the track and mast rule, re-exported for the builders
    LEVELS, LOOP_HALF, TAU, MapError, band_level, end_label, end_ref, facing_on_route, helix_tags, masts, track_names,
    tracks)
from hartlib import level_devices, railroad  # noqa: E402  the virtual names; the facts it reads and checks

SOURCES = railroad.Sources.under()
CPS = SOURCES.level_control_points
NODES = SOURCES.lcos_nodes
LOCAL = SOURCES.local_switches
OVERRIDES = SOURCES.plan_overrides
OUT = SOURCES.device_map
SPLIT = OVERRIDES.parent / "split_tracks_main_upper.csv"          # tracks parted into two blocks at their turnback
RUNNING = OVERRIDES.parent / "running_tracks_main_upper.csv"     # passing sidings counted as running track
SPURS = OVERRIDES.parent / "signalled_spurs_main_upper.csv"      # spurs that get an exit dwarf


def sources() -> railroad.Sources:
    """The files main() reads and writes: the module's paths as they are when it runs (a test may patch them)."""
    return railroad.Sources.under().but(level_control_points=CPS, lcos_nodes=NODES, local_switches=LOCAL,
                                        plan_overrides=OVERRIDES, device_map=OUT)

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


def load_cps(path: Path = CPS) -> list[railroad.LevelControlPoint]:
    """The control points (hartlib.railroad.read_level_control_points: every switch in at most one)."""
    try:
        return railroad.read_level_control_points(path)
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
    """control_points for main_upper.plan_overrides.json: each control point lists the labels of its
    switches on its own level's band (both halves of a crossover there, one half when the other is on the
    other band), as the band prints them: a moved switch keeps its star ("223*"), which station bars match on."""
    cp_out = {}
    for cp in cps:
        have = by_level[cp.level]
        refs = []
        for s in cp.switches:
            mine = sorted(lb for lb in have if base(lb) == s)
            if not mine:
                raise MapError(f"{cp.cp_name}: switch {s} is not on the level {cp.level} band")
            refs += mine
        cp_out[cp.cp_name] = {"switches": refs}
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
                turned = title.split()[0] in page.get("rotate_bands", ())
                out[base(d["label"])] = le_mod.double_corners(band, n, turned)
    return out


def split_edges(path: Path | None = None) -> dict:
    """{plan edge: track name} of the tracks split_tracks_main_upper.csv parts into two blocks at their turnback."""
    with open(path or SPLIT, newline="", encoding="utf-8") as fh:
        return {r["edge"]: r["track"] for r in csv.DictReader(fh)}


def loop_halves(band, runs, split: dict | None = None) -> dict:
    """{strand id: 1 or 2} for each balloon loop of `band` (a run that leaves a switch and comes back to it), by the
    leg its strand leaves the switch from (LOOP_HALF), and for each track `split` names (split_edges: a run between
    two switches folded at one turnback, owner 2026-11-19): half 1 the strand at its lower-numbered switch. Stops on a
    loop not drawn as two tracks joined by one turnback, or one not on legs B and C, since the halves would then be
    ambiguous."""
    split = split_edges() if split is None else split
    out = {}
    for start, chain, end in runs(band):
        edges = {re.sub(r"\.\d+$", "", band["strands"][sid]["edge"]) for sid, _ in chain}
        if start[0] != end[0] and len(edges) == 1 and next(iter(edges)) in split:
            if len(chain) != 2:
                raise MapError(f"{split[next(iter(edges))]} is drawn as {len(chain)} track(s); a split track needs "
                               "two joined by one turnback")
            labels = [natural(base(band["nodes"][x[0]].get("label") or "")) for x in (start, end)]
            first = 0 if labels[0] <= labels[1] else 1
            out[chain[0][0]], out[chain[-1][0]] = (1, 2) if first == 0 else (2, 1)
            continue
        if start[0] != end[0] or band["nodes"][start[0]]["kind"] not in ("switch", "dx"):
            continue
        if len(chain) != 2 or {start[1], end[1]} != set(LOOP_HALF):
            raise MapError(f"the balloon loop at switch {band['nodes'][start[0]].get('label')} is drawn as "
                           f"{len(chain)} track(s) on legs {start[1]} and {end[1]}; its halves need two tracks "
                           "joined by one turnback, on legs B and C")
        for (sid, _), (_, port) in zip((chain[0], chain[-1]), (start, end)):
            out[sid] = LOOP_HALF[port]
    return out


LINE_CODE = {2: "A", 3: "B"}            # milepost line codes, after Furnace A and B (owner, 2026-11-19)


def signal_number(mp: float, west: bool) -> int:
    """An intermediate signal's number from its milepost in tenths: odd westbound, even eastbound (prototype)."""
    n = int(mp * 10 + 1e-9)
    if west:
        return n if n % 2 else n + 1
    return n if n % 2 == 0 else n + 1


def intermediates(bands, found, cp_of, running, split) -> list[dict]:
    """APB intermediate masts on the main and upper levels (owner, 2026-11-19), named from the milepost with the
    level's line code: a pair at the turnback of each running balloon loop or split track, one each way (eastbound
    even, westbound odd). The milepost is the plugin's count along the main route (the band's `mp`, the numbers the
    sheets print), at the middle of the folded track; east is the way it rises, so on a split track the eastbound mast
    faces the half the count starts on. A balloon loop starts and ends at one switch, so its eastbound mast faces
    Loop 1. None into the helix: the home signals at 129 and 135 govern it (owner, 2026-11-19)."""
    out = []
    for bi, (title, band, _) in enumerate(bands):
        lv = band_level(title)
        if not lv:
            continue
        code = LINE_CODE[lv]
        for t in found:
            if t["band"] != bi:
                continue
            ends = [v for k, v in t["ends"] if k == "sw"]
            cp = next((cp_of[e] for e in ends if e in cp_of), "")
            if not cp:
                continue                    # a track with no control point at either end gets no intermediates
            if any(k == "helix" for k, _v in t["ends"]):
                continue                    # no signal into the helix: 129/135 govern it (owner, 2026-11-19)
            if not (t["loop"] or t["name"] in split) or not (t["main"] or t["name"] in running):
                continue
            edge = re.sub(r"(\.\d+|(?<=\d)[xy])$", "", band["strands"][t["strands"][0]]["edge"])
            if edge not in band["mp"]:
                raise MapError(f"{t['name']}: the milepost count (main route) does not run over plan edge {edge}")
            west_node, mp0, length, _end = band["mp"][edge]
            mp = mp0 + length / 2           # the turnback parts a folded track in the middle
            half = [f"{t['name']} 1", f"{t['name']} 2"]
            if not t["loop"]:               # east is the way the count rises: from the end it starts at
                west_label = base(band["nodes"][west_node].get("label") or "")
                first_switch = sorted(ends, key=natural)[0]       # half 1 is at the lower-numbered switch
                if west_label != first_switch:
                    half.reverse()
            for west, facing, protects in ((True, half[1], half[0]), (False, half[0], half[1])):
                out.append(dict(level=lv, cp=cp, name=f"{code}{signal_number(mp, west)}", facing=facing,
                                protects=protects, heads=1, kind="one-searchlight", switch="", intermediate=True,
                                band=bi, milepost=round(mp, 3)))
    return out


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
        self.boards = {}                     # node -> pins used on each of its 5V boards

    def room(self, node, what, n=1):
        return self.used[node][what] + n <= CAP[what]

    def pick(self, level, area, what, n=1, prefer=()):
        for node in list(prefer) + self.pool[(level, area)]:
            if self.room(node, what, n):
                return node
        raise MapError(f"level {level} {area}: no LCOS node left with room for {n} {what}(s); "
                       f"add one to {NODES.name}")

    def take(self, node, what):
        k = self.used[node][what]
        self.used[node][what] += 1
        return k, node * 100 + UID[what] + k

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


def build(bands, joined, runs, overrides, cps, node_rows, local=(), corners=None, running=frozenset(),
          spurs=frozenset()) -> tuple[dict, list[dict]]:
    """(control_points, device map rows). `local`: the switches in no control point (local_switches_main_upper.csv
    rows). Every switch on the main and upper bands must be in exactly one of the two. `corners`: dx_corners, needed
    when a band has a double crossover."""
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
    found = tracks(bands, runs, joined, helix_tags(bands, overrides))
    track_names(found)
    corners = corners or {}
    dxs = {base(d["label"]) for title, band, _ in bands if band_level(title)
           for d in band["nodes"].values() if d["kind"] == "dx"}
    if dxs - set(corners):
        raise MapError(f"double crossover {', '.join(sorted(dxs - set(corners), key=natural))}: no corners given")
    corner_blocks = {s: xover_corners(s, corners[s]) for s in dxs}
    split_names = set(split_edges().values())       # read once per build
    ms = masts(bands, cps, found, cp_of, corner_blocks, running_extra=running, spurs=spurs, split=split_names)
    known = {t["name"] for t in found}
    if (set(running) | set(spurs)) - known:
        raise MapError(f"{RUNNING.name} or {SPURS.name} names a track the plan does not have: "
                       f"{sorted((set(running) | set(spurs)) - known)}")
    for m in ms:
        # two heads when a route the mast governs meets facing points inside its interlocking; high from running
        # track, a dwarf from a yard, lead or siding (owner, 2026-11-19, as staging: build_staging_masts.py)
        if m["heads"] == 1 and facing_on_route(bands[m["band"]][1], m["node"], m["leg"], cp_of):
            m["heads"] = 2
        m["kind"] = f"{'two' if m['heads'] == 2 else 'one'}-{'searchlight' if m['running'] else 'low'}"
    ms += intermediates(bands, found, cp_of, set(running), split_names)
    names = [m["name"] for m in ms]
    twice = sorted({n for n in names if names.count(n) > 1}, key=natural)
    if twice:       # an intermediate named from a milepost can meet another's number (a home mast never can)
        raise MapError(f"mast names given twice: {', '.join(twice)}")
    nodes = Nodes(node_rows)
    rows = []

    def add(level, cp, layer, user, system="", node="", comment="", trial="", notes="", dcc="", jmri=""):
        rows.append(dict(level=level, cp=cp, layer=layer, user_name=user, system_name=system, jmri_name=jmri,
                         node=node, dcc=dcc, comment=comment, trial_name=trial, notes=notes))

    def occupancy(level, cp, block, system="", node="", comment="", notes=""):
        """The occupancy row of `block`: its virtual sensor (jmri_name) and the planned detector, if any."""
        add(level, cp, "occupancy", occupancy_user(block), system, node, comment, notes=notes,
            jmri=block_sensor(block))

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
            switch_rows(cp.level, cp.area, cp.cp_name, s, node)
    for s in sorted(loc, key=natural):           # no control point: turnout and feedback, no signals or detection
        r = loc[s]
        node = nodes.pick(r.level, r.area, "turnout")
        switch_rows(r.level, r.area, "", s, node, "no control point: " + r.notes)
    for cp in cps:
        for s in cp.switches:
            os_rows(cp.level, cp.area, cp.cp_name, s, cp.cp_name)
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
                note += f", half {half} of the split track (split_tracks_main_upper.csv)"
            elif half:
                note += f", half of the balloon loop from leg {'BC'[half - 1]}"
            add(t["level"], cp, "block", name, "", "", " / ".join(ends_cp),
                ", ".join(loop_placeholder(x, half) for x in t["trial"]), note)
            if not detect:
                occupancy(t["level"], cp, name, notes=NO_DETECTOR)
                continue
            if half and half > 1:                                 # wired later: no node or input yet
                occupancy(t["level"], cp, name, notes=NOT_WIRED)
                continue
            sws.sort(key=lambda s: area_of[s][0] != t["level"])      # a node on the track's own level first
            lv, area = t["level"], area_of[sws[0]][1]                 # the track's level, its switch's area
            bnode = nodes.pick(lv, area, "block", prefer=[home[s] for s in sws if area_of[s][0] == lv])
            k, packed = nodes.take(bnode, "block")
            occupancy(t["level"], cp, name, f"M2S{packed}", bnode, f"Node: {bnode} Block: {k + 1}")

    groups = [(cp.level, cp.area, cp.cp_name, cp.switches[0]) for cp in cps]
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
                      f"{m['milepost']:.2f}", jmri=virtual)
        else:
            add(lv, name, "mast", f"Mast {m['name']}", sysname, hnode, f"{name or area} | Switch {m['switch']}",
                notes=f"home signal from {m['track']}" + (f" into {m['protects']}" if m["protects"] else ""),
                jmri=virtual)
        for user, sysn, k, board, pin in heads:
            if not sysn:                    # no node yet: the mast's comment says where it stands
                where = f"{name or area} | " + (f"Switch {m['switch']}" if m["switch"] else "intermediate")
                add(lv, name, "head", user, "", "", where, notes=HEAD_NOT_WIRED, jmri=level_devices.head_name(user))
                continue
            add(lv, name, "head", user, sysn, hnode,
                f"Node: {hnode} Signal: {k} | OU: {board} Ports: {pin},{pin + 1},{pin + 2}",
                jmri=level_devices.head_name(user))
    nodes.check_boards()
    check_virtual(rows)
    order = {"turnout": 0, "fb": 1, "block": 2, "occupancy": 3, "mast": 4, "head": 5}
    assign_ports(rows)
    rows.sort(key=lambda r: (r["level"], order[r["layer"]], natural(r["user_name"])))
    return cp_keys, rows


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
    over = dict(overrides)
    over["control_points"] = cp_keys
    over["stations"] = {name: {"switches": cp["switches"], "tracks": []} for name, cp in cp_keys.items()}
    over["_control_points"] = ("Placeholder control points 'CP <lowest switch>' (owner, 2026-11-15), written by "
                               "tools/schematic/build_device_map.py from control_points_main_upper.csv; edit that "
                               "file, not this key.")
    return json.dumps(over, indent=1, ensure_ascii=False) + "\n"


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
        lists = [{r["track"] for r in csv.DictReader(io.StringIO(p.read_text(encoding="utf-8")))} for p in (RUNNING, SPURS)]
        cp_keys, rows = build(bands, joined, runs, overrides, *inputs, corners, *lists)
    except MapError as exc:
        print(f"build_device_map.py: {exc}", file=sys.stderr)
        return 2
    want = {OVERRIDES: overrides_text(overrides, cp_keys), OUT: csv_text(rows)}
    stale = [p for p, text in want.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
    if args.check:
        for p in stale:
            print(f"{p.name} is stale: run python3 tools/schematic/build_device_map.py", file=sys.stderr)
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
