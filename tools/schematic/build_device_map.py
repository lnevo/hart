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
- device_map_main_upper.csv: the names each switch, track and home signal would take under ADR-005, with LCOS
  system names. Placeholders: nothing in tables.xml uses them yet, and the names change when the owner names
  the levels.

Naming rules (ADR-005 grammar, LCOS conventions):
- Turnout "Switch <n>" (a crossover is one turnout), feedback "FB Switch <n> N|R", OS block "OS Switch <n>" (one per
  number, as the Layout Editor trial has it), occupancy "BS <block without Track>". A double crossover is four OS
  blocks, one per corner, "OS Switch <n>a" to "<n>d" by its Layout Editor corner A to D (owner, 2026-11-16; the
  plugin's double_corners maps the schematic's legs to the corners): with one block, or
  two, JMRI 5.16 records a through path between the two legs on one side (LayoutBlock.addThroughPath keeps a pair
  whose turnout lists match both ways) and Signal Mast Logic discovery pairs masts across it (226RA to 224LB). Corner
  a keeps the switch's detector; b to d are virtual (VIRTUAL_SENSOR) until wired. A mast at a double crossover
  protects its own leg's corner block ("home signal from Track X into OS Switch <n><corner>").
- Track "Track <a>-<b>" from its end switches (numbers, H1 or H2 for a helix), "Track <n> Spur" to a bumper,
  "Track <n> Loop" back to the same switch; parallel tracks between the same ends take " 1", " 2" from the top row.
  A balloon loop is two blocks, "Track <n> Loop 1" from the switch's leg B and "Track <n> Loop 2" from leg C, parted
  at the turnback halfway round (owner, 2026-11-16): JMRI keys a mast by its facing and protected blocks
  (LayoutBlockManager.getFacingBean returns one), so two masts facing one loop block into one OS block would leave
  one of them out of Signal Mast Logic discovery. Loop 1 keeps the loop's detector; Loop 2's is virtual (an internal
  VIRTUAL_SENSOR, numbered from 1) until it is wired, so no node or input assignment moves.
  A track under SHORT_CM between two switches gets a block but no detector (it would sit inside their OS blocks).
- Detection on the main line only (owner, 2026-11-15): main-route tracks and the OS blocks of control point
  switches get an occupancy sensor; yard and industry tracks and the OS blocks of switches in no control point
  get a block for the panels but no detector.
- Home signals: one mast where each track from outside a control point meets one of its switches; none on spurs
  or yard tracks that end at a bumper. "Mast <n+1><L|R>", L for a westbound train (ADR-005), A/B when one number
  and direction has two. A mast at the points has two heads (two-searchlight, Top and Bottom); one at a trailing
  leg has one (one-low). East is the schematic's (ADR-022 amendment: away from the helix on these levels).
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

CPS = pd.DATA / "control_points_main_upper.csv"
NODES = pd.DATA / "lcos_nodes_main_upper.csv"
LOCAL = pd.DATA / "local_switches_main_upper.csv"
OVERRIDES = pd.DATA / "main_upper.plan_overrides.json"
OUT = pd.DATA / "device_map_main_upper.csv"

LEVELS = {"Main": 2, "Upper": 3}      # band key (first word of the band title) -> level
SHORT_CM = 30.0
CAP = {"turnout": 8, "block": 8, "signal": 16, "sensor": 16}
MAX_OU = 4                            # DNOU8 boards per node: the most any node has in LCOS_Layout_Inventory_v85
UID = {"block": 0, "turnout": 8, "signal": 32, "sensor": 67}
COLUMNS = ["level", "cp", "layer", "user_name", "system_name", "node", "dcc", "comment", "trial_name", "notes"]
DCC_FIRST = 120                       # staging uses 100-119 (MTT100-MTT119); the owner continues from 120
TAU = {"A": -1, "B": 1, "C": 1, "D": -1}      # the plugin's leg sides (schematic.core.TAU)
LOOP_HALF = {"B": 1, "C": 2}          # a balloon loop's half by the switch leg it leaves from (owner, 2026-11-16)
VIRTUAL_SENSOR = "IS:HART:C3:"        # internal occupancy placeholders, numbered from 1: nothing reaches the field
VIRTUAL_NOTE = "virtual: no detector wired yet (owner, 2026-11-16)"


class MapError(RuntimeError):
    pass


def base(label: str) -> str:
    """Switch number of a schematic label: "129A" -> "129", "223*" -> "223"."""
    return re.sub(r"[AB]$", "", (label or "").rstrip("*"))


def natural(name: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", name)]


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_cps(path: Path = CPS) -> list[dict]:
    """Control point rows, switches as a list; every switch in at most one control point."""
    rows, seen = [], {}
    for row in read_csv(path):
        sw = [s.strip() for s in row["switches"].split(",") if s.strip()]
        for s in sw:
            if s in seen:
                raise MapError(f"switch {s} is in {seen[s]} and {row['cp_name']}")
            seen[s] = row["cp_name"]
        rows.append(dict(row, switches=sw, level=int(row["level"])))
    return rows


# ---------------------------------------------------------------- the schematic

def band_level(title: str) -> int | None:
    return LEVELS.get((title or "").split()[0]) if title else None


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
        have = by_level[cp["level"]]
        refs = []
        for s in cp["switches"]:
            mine = sorted(lb for lb in have if base(lb) == s)
            if not mine:
                raise MapError(f"{cp['cp_name']}: switch {s} is not on the level {cp['level']} band")
            refs += mine
        cp_out[cp["cp_name"]] = {"switches": refs}
    return cp_out


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


def loop_halves(band, runs) -> dict:
    """{strand id: 1 or 2} for each balloon loop of `band` (a run that leaves a switch and comes back to it), by the
    leg its strand leaves the switch from (LOOP_HALF). Stops on a loop not drawn as two tracks joined by one
    turnback, or one not on legs B and C, since the halves would then be ambiguous."""
    out = {}
    for start, chain, end in runs(band):
        if start[0] != end[0] or band["nodes"][start[0]]["kind"] not in ("switch", "dx"):
            continue
        if len(chain) != 2 or {start[1], end[1]} != set(LOOP_HALF):
            raise MapError(f"the balloon loop at switch {band['nodes'][start[0]].get('label')} is drawn as "
                           f"{len(chain)} track(s) on legs {start[1]} and {end[1]}; its halves need two tracks "
                           "joined by one turnback, on legs B and C")
        for (sid, _), (_, port) in zip((chain[0], chain[-1]), (start, end)):
            out[sid] = LOOP_HALF[port]
    return out


def loop_placeholder(placeholder: str, half: int | None) -> str:
    """The drawing's placeholder for one half of a balloon loop ("Track e33" -> "Track e33 1"), as
    build_layout_le.placeholder_names and build_cats_panel name it; any other track's is unchanged."""
    return placeholder if half is None else f"{placeholder} {half}"


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


# ---------------------------------------------------------------- LCOS nodes

class Nodes:
    """Hands out LCOS UIDs per node, in each level and area's node order."""

    def __init__(self, rows):
        self.pool = defaultdict(list)
        for r in rows:
            self.pool[(int(r["level"]), r["area"])].append(int(r["node"]))
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
        """(board index among the node's 5V boards, first pin) where `pins` consecutive pins fit, or None."""
        boards = self.boards.setdefault(node, [])
        if boards and boards[-1] + pins <= self._cap(node, len(boards) - 1):
            return len(boards) - 1, boards[-1] + 1
        if self.n12(node) + len(boards) + 1 <= MAX_OU and pins <= self._cap(node, len(boards)):
            return len(boards), 1
        return None

    def pick_mast(self, level, area, heads, prefer=()):
        for node in list(prefer) + self.pool[(level, area)]:
            if self.room(node, "signal", heads) and self._fit(node, 3 * heads):
                return node
        raise MapError(f"level {level} {area}: no LCOS node left with board room for a {heads}-head mast; "
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


def build(bands, joined, runs, overrides, cps, node_rows, local=(), corners=None) -> tuple[dict, list[dict]]:
    """(control_points, device map rows). `local`: the switches in no control point (local_switches_main_upper.csv
    rows). Every switch on the main and upper bands must be in exactly one of the two. `corners`: dx_corners, needed
    when a band has a double crossover."""
    by_level = labels_by_level(bands)
    cp_keys = overrides_keys(cps, by_level)
    cp_of = {s: cp["cp_name"] for cp in cps for s in cp["switches"]}
    loc = {r["switch"]: dict(r, level=int(r["level"])) for r in local}
    both = sorted(set(cp_of) & set(loc), key=natural)
    if both:
        raise MapError(f"switch {', '.join(both)} is in a control point and in {LOCAL.name}")
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
    ms = masts(bands, cps, found, cp_of, corner_blocks)
    nodes = Nodes(node_rows)
    rows = []

    def add(level, cp, layer, user, system="", node="", comment="", trial="", notes="", dcc=""):
        rows.append(dict(level=level, cp=cp, layer=layer, user_name=user, system_name=system,
                         node=node, dcc=dcc, comment=comment, trial_name=trial, notes=notes))

    virtual = 0                             # virtual detectors, numbered in the order they are added
    dcc = {s: DCC_FIRST + i for i, s in enumerate(sorted(set(cp_of) | set(loc), key=natural))}
    home, area_of = {}, {}                  # switch -> its turnout's node, its area

    def switch_rows(lv, area, name, s, node, note=""):
        k, packed = nodes.take(node, "turnout")
        home[s], area_of[s] = node, (lv, area)
        halves = sorted({lb for labels in by_level.values() for lb in labels if base(lb) == s}, key=natural)
        add(lv, name, "turnout", f"Switch {s}", f"M2T{packed}", node, f"Node: {node} Turnout: {k}",
            ", ".join(f"Switch {lb}" for lb in halves), note, dcc[s])
        add(lv, name, "turnout", f"DCC Switch {s}", f"MTT{dcc[s]}", node, f"Node: {node} Turnout: {k}",
            notes="LCC alias of the MQTT turnout (ADR-005)", dcc=dcc[s])
        for nr in "NR":
            fnode = nodes.pick(lv, area, "sensor", prefer=[node])
            kk, pp = nodes.take(fnode, "sensor")
            add(lv, name, "fb", f"FB Switch {s} {nr}", f"M2S{pp}", fnode, f"Node: {fnode} Sensor: {kk}")

    def os_rows(lv, area, name, s, comment, detect=True):
        if s in dxs:                            # a double crossover: a block per corner, corner a detected
            nonlocal virtual
            for block in sorted(corner_blocks[s].values()):
                note = f"corner {block[-1].upper()} of the double crossover"
                user = "BS " + block.removeprefix("OS ")
                if not detect:
                    add(lv, name, "block", block, "", "", comment, block, note + ", no detector: off the main line")
                elif not block.endswith("a"):             # wired later: a virtual sensor, no node or input
                    virtual += 1
                    add(lv, name, "block", block, "", "", comment, block, note)
                    add(lv, name, "occupancy", user, f"{VIRTUAL_SENSOR}{virtual}", "", VIRTUAL_NOTE)
                else:                                     # corner a keeps the switch's detector
                    bnode = nodes.pick(lv, area, "block", prefer=[home[s]])
                    k, packed = nodes.take(bnode, "block")
                    add(lv, name, "block", block, "", bnode, comment, block, note)
                    add(lv, name, "occupancy", user, f"M2S{packed}", bnode, f"Node: {bnode} Block: {k + 1}")
            return
        if not detect:
            add(lv, name, "block", f"OS Switch {s}", "", "", comment, f"OS Switch {s}",
                "no detector: off the main line")
            return
        bnode = nodes.pick(lv, area, "block", prefer=[home[s]])
        k, packed = nodes.take(bnode, "block")
        add(lv, name, "block", f"OS Switch {s}", "", bnode, comment, f"OS Switch {s}")
        add(lv, name, "occupancy", f"BS Switch {s}", f"M2S{packed}", bnode, f"Node: {bnode} Block: {k + 1}")

    for cp in cps:                               # turnouts first: a node's 12V boards come before its 5V boards
        node = nodes.pick(cp["level"], cp["area"], "turnout", len(cp["switches"]))
        for s in cp["switches"]:
            switch_rows(cp["level"], cp["area"], cp["cp_name"], s, node)
    for s in sorted(loc, key=natural):           # no control point: turnout and feedback, no signals or detection
        r = loc[s]
        node = nodes.pick(r["level"], r["area"], "turnout")
        switch_rows(r["level"], r["area"], "", s, node, "no control point: " + r["notes"])
    for cp in cps:
        for s in cp["switches"]:
            os_rows(cp["level"], cp["area"], cp["cp_name"], s, cp["cp_name"])
    for s in sorted(loc, key=natural):
        os_rows(loc[s]["level"], loc[s]["area"], "", s, loc[s]["area"], detect=False)

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
        halves = sorted(LOOP_HALF.values()) if t["loop"] else [None]
        for half in halves:
            name = loop_placeholder(t["name"], half)
            cm = round(t["cm"] / 2, 1) if half else t["cm"]
            note = f"{cm} cm" + (" short link: inside the OS blocks of its switches, no detector" if short else
                                 "" if t["main"] else " no detector: off the main line")
            if half:
                note += f", half of the balloon loop from leg {'BC'[half - 1]}"
            add(t["level"], cp, "block", name, "", "", " / ".join(ends_cp),
                ", ".join(loop_placeholder(x, half) for x in t["trial"]), note)
            if not detect:
                continue
            user = "BS " + name.removeprefix("Track ")
            if half and half > 1:                                 # wired later: a virtual sensor, no node or input
                virtual += 1
                add(t["level"], cp, "occupancy", user, f"{VIRTUAL_SENSOR}{virtual}", "", VIRTUAL_NOTE)
                continue
            sws.sort(key=lambda s: area_of[s][0] != t["level"])      # a node on the track's own level first
            lv, area = t["level"], area_of[sws[0]][1]                 # the track's level, its switch's area
            bnode = nodes.pick(lv, area, "block", prefer=[home[s] for s in sws if area_of[s][0] == lv])
            k, packed = nodes.take(bnode, "block")
            add(t["level"], cp, "occupancy", user, f"M2S{packed}", bnode, f"Node: {bnode} Block: {k + 1}")

    for cp in cps:                               # heads last, once every node's boards are known
        lv, area, name = cp["level"], cp["area"], cp["cp_name"]
        for m in sorted((m for m in ms if m["cp"] == name), key=lambda m: natural(m["name"])):
            hnode = nodes.pick_mast(lv, area, m["heads"], prefer=[home[cp["switches"][0]]])
            parts = ["Top", "Bottom"] if m["heads"] == 2 else [""]
            heads = [(f"Head {m['name']}" + (f" {part}" if part else ""), f"IH{packed}", k, board, pin)
                     for part, (k, packed, board, pin) in zip(parts, nodes.place_mast(hnode, m["heads"]))]
            kind = "two-searchlight" if m["heads"] == 2 else "one-low"
            sysname = f"IF$shsm:basic:{kind}(" + ")(".join(h[1] for h in heads) + ")"
            add(lv, name, "mast", f"Mast {m['name']}", sysname, hnode, f"{name} | Switch {m['switch']}",
                notes=f"home signal from {m['track']}" + (f" into {m['protects']}" if m["protects"] else ""))
            for user, sysn, k, board, pin in heads:
                add(lv, name, "head", user, sysn, hnode,
                    f"Node: {hnode} Signal: {k} | OU: {board} Ports: {pin},{pin + 1},{pin + 2}")
    nodes.check_boards()
    order = {"turnout": 0, "fb": 1, "block": 2, "occupancy": 3, "mast": 4, "head": 5}
    assign_ports(rows)
    rows.sort(key=lambda r: (r["level"], order[r["layer"]], natural(r["user_name"])))
    return cp_keys, rows


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


def csv_text(rows) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
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
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    import build_layout_le as bl
    try:
        bands, joined, runs, corners = solve()
    except bl.BuildError as exc:
        if not args.check:
            raise
        print(f"SKIPPED device map check: {exc}")
        return 1 if os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0
    try:
        cp_keys, rows = build(bands, joined, runs, overrides, load_cps(), read_csv(NODES), read_csv(LOCAL), corners)
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
