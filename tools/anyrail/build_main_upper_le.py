#!/usr/bin/env python3
"""Build a Layout Editor panel of the main and upper levels from the AnyRail plan data (C3, ADR-023).

    python3 tools/anyrail/build_main_upper_le.py           # write the trial tables file
    python3 tools/anyrail/build_main_upper_le.py --check   # fail if the trial file is stale

Writes jmri/layouts/hart/output/trial/tables_main_upper.xml: the live tables.xml unchanged, plus one
new Layout Editor panel, PANEL_NAME, and the internal turnouts, blocks and layout blocks it uses. The live
tables.xml is only read. Names are placeholders: turnouts "Switch <owner number>" (internal IT:HART:C3:
system names, so nothing commands field hardware), blocks "Track <plan edge id>" and "OS Switch <number>".
No sensors and no masts.

Inputs (all committed, track only):
- data/schematic/inputs/main.json: the plan's track graph (switches, ends, runs between them), in the
  AnyRail export's pixels (120 px per inch). The panel uses these pixels 1:1.
- data/schematic/inputs/parts.json: the plan's parts with their end points in cm. Runs are traced through
  the flex track parts between switches, so each run is drawn through every flex joint; joints become
  anchors and the track between them is a Bezier whose ends follow the track either side.
- data/schematic/main_upper.plan_overrides.json: the owner's switch numbers (relabel), T300 moved to the
  upper level (move), and the level cut (`levels`). Switch lookups, the levels and a check of the edited
  graph come from the schematic-maps plugin (the pinned submodule, or SCHEMATIC_PLUGIN); overrides the
  panel does not draw stop the build.
- data/schematic/hands.csv: the owner's hands. The build stops if a part's geometry, the plan's hand and
  hands.csv disagree.

The main level and the upper level overlap in plan, so the upper level is drawn to the right of the main
level (shifted, never scaled). A run that climbs from one level to the other is cut at its first joint on
the other level (the plugin's `treat` and bands) and joined across the gap by a hidden track segment, so
the blocks stay connected.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import importlib
import math
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths, tables  # noqa: E402

SCHEMATIC = paths.LAYOUT_DATA / "schematic"
GRAPH = SCHEMATIC / "inputs" / "main.json"
PARTS = SCHEMATIC / "inputs" / "parts.json"
OVERRIDES = SCHEMATIC / "main_upper.plan_overrides.json"
HANDS = SCHEMATIC / "hands.csv"
TRIAL = paths.LAYOUT_OUTPUT / "trial" / "tables_main_upper.xml"

PANEL_NAME = "Main and Upper (generated)"
TEMPLATE_PANEL = "HART Railroad"     # attributes and drawing options are copied from the live panel
PX_PER_CM = 120 / 25.4               # AnyRail's JMRI export, as in the schematic plugin's plan reader
Z_RANGE = (-5.0, 100.0)              # the parts of the main and upper levels (staging is below -5)
JOIN_CM = 0.3                        # part end points closer than this are one joint
Z_TOL_CM = 1.0                       # a switch or track end and its part: heights this close
UNMATCHED_LEG_CM = 3.0               # leg length for a switch with no part of its own (the three-way halves)
LEVEL_GAP_PX = 300.0
MARGIN_PX = 60.0

TURNOUT_SYS = "IT:HART:C3:"          # internal turnouts: nothing reaches the field
BLOCK_SYS = "IB:C3:"
LAYOUT_BLOCK_FIRST = 1001            # ILB1001 up; the live file stops well below
TAG = "C3"                           # in every panel ident: TOC3-, TC3-, AC3-, EBC3-

COMMENT = "Placeholder from AnyRail plan 5.3b (C3 trial, build_main_upper_le.py)"
LE = "jmri.jmrit.display.layoutEditor.configurexml."
CLASS = {
    "RH_TURNOUT": LE + "LayoutRHTurnoutXml",
    "LH_TURNOUT": LE + "LayoutLHTurnoutXml",
    "DOUBLE_XOVER": LE + "LayoutDoubleXOverXml",
    "segment": LE + "TrackSegmentXml",
    "point": LE + "PositionablePointXml",
}


class BuildError(RuntimeError):
    pass


# The overrides this build understands. Anything else stops it, so an edit the geometry ignores is never
# drawn silently (the schematic plugin may handle more ops than the panel does).
OVERRIDE_KEYS = {"_layer", "_note", "edits", "levels",
                 # the schematic sheet's own: names, main route, helix side, mast names (no track geometry)
                 "helix", "_helix_side", "helix_side", "helix_to", "main_route", "mast_prefix", "mast_dir_pattern"}
LEVEL_KEYS = {"treat", "bands", "assign"}
EDIT_KEYS = {"relabel": {"op", "map", "source", "_note"},
             "move": {"op", "switch", "through", "onto", "cm_from_first", "z", "hand", "source", "_note"}}


def plugin_edits():
    """The schematic plugin's edits module: SCHEMATIC_PLUGIN, else the pinned submodule (as publish_draft.py)."""
    env = os.environ.get("SCHEMATIC_PLUGIN")
    if env:
        folder = Path(env)
    else:
        sub_dir = paths.REPO_ROOT / "external/model-railroad-skills"
        folder = sub_dir / "plugins/schematic-maps"
        if not (folder / "schematic/edits.py").exists():
            raise BuildError("schematic-maps plugin not found: run git submodule update --init "
                             "external/model-railroad-skills")
        git = lambda *a: subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()  # noqa: E731
        have = git("-C", str(sub_dir), "rev-parse", "HEAD")
        pinned = (git("-C", str(paths.REPO_ROOT), "ls-files", "-s", "external/model-railroad-skills").split()
                  or ["", ""])[1]
        if pinned and have != pinned:
            raise BuildError(f"submodule is at {have[:8]}, pinned {pinned[:8]}: run git submodule update, "
                             "or set SCHEMATIC_PLUGIN on purpose")
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    return importlib.import_module("schematic.edits"), importlib.import_module("schematic.core")


def check_override_keys(overrides: dict) -> None:
    bad = sorted(set(overrides) - OVERRIDE_KEYS)
    bad += [f"levels.{k}" for k in sorted(set(overrides.get("levels", {})) - LEVEL_KEYS)]
    for ed in overrides.get("edits", []):
        allowed = EDIT_KEYS.get(ed.get("op"))
        if allowed is None:
            bad.append(f"edit op {ed.get('op')!r}")
        else:
            bad += [f"{ed['op']}.{k}" for k in sorted(set(ed) - allowed)]
    if bad:
        raise BuildError("plan overrides the panel build does not handle: " + ", ".join(bad))


def z_level(z, spec) -> int:
    """A height's level, as the plugin's split_levels reads it: `treat` first, then the first band below."""
    for lo, hi, to in spec.get("treat", []):
        if lo <= z < hi:
            z = to
            break
    return next(i for i, b in enumerate(spec["bands"]) if z < b["below"])


# ---------------------------------------------------------------- small geometry

def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def unit(v):
    n = math.hypot(*v) or 1.0
    return (v[0] / n, v[1] / n)


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def angle_to(a, b) -> float:
    """Angle between two directions, radians."""
    return abs(math.atan2(cross(a, b), a[0] * b[0] + a[1] * b[1]))


def r1(v: float) -> str:
    return f"{round(v, 1):.1f}"


def polyline_length(pts):
    return sum(math.dist(p[:2], q[:2]) for p, q in zip(pts, pts[1:]))


def point_at(pts, s):
    """The point at arc length s along pts, and the index of the vertex after it."""
    run = 0.0
    for i in range(1, len(pts)):
        d = math.dist(pts[i - 1][:2], pts[i][:2])
        if run + d >= s and d > 0:
            t = (s - run) / d
            return (pts[i - 1][0] + t * (pts[i][0] - pts[i - 1][0]),
                    pts[i - 1][1] + t * (pts[i][1] - pts[i - 1][1])), i
        run += d
    return tuple(pts[-1][:2]), len(pts) - 1


# ---------------------------------------------------------------- the plan

class Plan:
    """The plan graph with geometry: every switch's leg points and every run's polyline, in export px."""

    def __init__(self, graph: dict, parts: list, overrides: dict):
        check_override_keys(overrides)
        self.edits_mod, core = plugin_edits()
        self.plugin_error = core.SchematicError
        self.original = copy.deepcopy(graph)
        self.nodes = copy.deepcopy(graph["nodes"])
        self.edges = copy.deepcopy(graph["edges"])
        self.parts = parts
        self.overrides = overrides
        self.notes: list[str] = []
        self._fit()
        self._joints()
        self._own_parts()
        self._ports()
        self._trace()
        self._apply_edits()
        self._levels()

    def node_z(self, nid):
        """A switch's height, or the nearest switch's along the track when the plan reader left it out."""
        dist, todo = {nid: 0.0}, [(0.0, nid)]
        while todo:
            todo.sort()
            d, n = todo.pop(0)
            if self.nodes[n].get("z") is not None:
                return self.nodes[n]["z"]
            for e in self.edges:
                for a, b in ((e["u"], e["v"]), (e["v"], e["u"])):
                    if a == n and d + e["cm"] < dist.get(b, math.inf):
                        dist[b] = d + e["cm"]
                        todo.append((dist[b], b))
        return None

    # parts (cm) to export px: least squares over the switches the plan reader matched (T<part index>)
    def _fit(self):
        pairs = []
        for n in self.nodes.values():
            label = n.get("label", "")
            if n["kind"] == "switch" and label.startswith("T") and label[1:].isdigit():
                eps = self.parts[int(label[1:])]["eps"]
                cx = sum(q["x"] for q in eps) / len(eps)
                cy = sum(q["y"] for q in eps) / len(eps)
                pairs.append((n["xy"][0] / PX_PER_CM, n["xy"][1] / PX_PER_CM, cx, cy))

        def fit(a, b):
            ma, mb = sum(a) / len(a), sum(b) / len(b)
            s = sum((p - ma) * (q - mb) for p, q in zip(a, b)) / sum((p - ma) ** 2 for p in a)
            return s, mb - s * ma

        self.sx, self.ox = fit([p[2] for p in pairs], [p[0] for p in pairs])
        self.sy, self.oy = fit([p[3] for p in pairs], [p[1] for p in pairs])

    def px(self, q):
        return ((self.sx * q["x"] + self.ox) * PX_PER_CM, (self.sy * q["y"] + self.oy) * PX_PER_CM)

    def _joints(self):
        """Group part end points into joints (3D, so stacked levels never join)."""
        self.live = [i for i, p in enumerate(self.parts)
                     if p["eps"] and Z_RANGE[0] <= max(q["z"] for q in p["eps"]) <= Z_RANGE[1]]
        eps = [(i, k) for i in self.live for k in range(len(self.parts[i]["eps"]))]
        parent = {e: e for e in eps}

        def find(e):
            while parent[e] != e:
                parent[e] = parent[parent[e]]
                e = parent[e]
            return e

        def q(e):
            return self.parts[e[0]]["eps"][e[1]]

        def cell(e):
            return tuple(math.floor(q(e)[c] / JOIN_CM) for c in "xyz")

        grid: dict = {}
        for e in eps:
            grid.setdefault(cell(e), []).append(e)
        for a in eps:           # same or next cell in each direction: every pair closer than JOIN_CM
            qa, (cx, cy, cz) = q(a), cell(a)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for b in grid.get((cx + dx, cy + dy, cz + dz), ()):
                            qb = q(b)
                            if b > a and all(abs(qa[c] - qb[c]) < JOIN_CM for c in "xyz"):
                                ra, rb = find(a), find(b)
                                if ra != rb:
                                    parent[max(ra, rb)] = min(ra, rb)
        self.joint = {e: find(e) for e in eps}
        self.members: dict = {}
        for e in eps:
            self.members.setdefault(self.joint[e], []).append(e)

    def joint_point(self, j):
        q = self.parts[j[0]]["eps"][j[1]]
        return (*self.px(q), q["z"])

    def _own_parts(self):
        """Which part each switch is: T<i> from the plan reader, else the nearest unclaimed turnout part."""
        self.part_of: dict[str, int] = {}
        for nid, n in self.nodes.items():
            label = n.get("label", "")
            if n["kind"] == "switch" and label.startswith("T") and label[1:].isdigit():
                self.part_of[nid] = int(label[1:])
        claimed = set(self.part_of.values())
        for nid in sorted(self.nodes):
            n = self.nodes[nid]
            if n["kind"] == "end" or nid in self.part_of:
                continue
            best = None
            nz = self.node_z(nid)
            for i in self.live:
                if i in claimed and len(self.parts[i]["eps"]) < 4:
                    continue
                e = self.parts[i]["eps"]
                if nz is None or abs(max(q["z"] for q in e) - nz) > Z_TOL_CM:
                    continue        # main and upper overlap in plan: a part on another level is not this one
                c = (sum(self.px(q)[0] for q in e) / len(e), sum(self.px(q)[1] for q in e) / len(e))
                d = math.dist(c, n["xy"]) / PX_PER_CM
                # a turnout part (3 ends) within 20 cm, a three-way (4 ends, shared by the export's two
                # halves) within 30 cm, or a misread turnout (2 ends) right on the switch
                if (len(e) == 3 and d < 20) or (len(e) >= 4 and d < 30) or d < 2:
                    if best is None or d < best[0]:
                        best = (d, i)
            if best is not None:
                self.part_of[nid] = best[1]
                claimed.add(best[1])
        self.switch_parts = set(self.part_of.values())
        shared = [i for i in self.switch_parts if list(self.part_of.values()).count(i) > 1]
        self.shared_parts = set(shared)

    def _ports(self):
        """Leg points (export px) of every switch whose part is its own."""
        self.port_pt: dict[tuple[str, str], tuple] = {}
        self.port_joint: dict[tuple[str, str], tuple] = {}
        for nid, i in sorted(self.part_of.items()):
            if i in self.shared_parts:
                continue
            n = self.nodes[nid]
            e = [(i, k) for k in range(len(self.parts[i]["eps"]))]
            pts = {x: self.px(self.parts[i]["eps"][x[1]]) for x in e}
            if len(e) == 3:
                toe = max(e, key=lambda x: sum(math.dist(pts[x], pts[y]) for y in e))
                p, q = [x for x in e if x != toe]
                # B is the leg whose direction from the points is nearer the plan's B direction
                if angle_to(sub(pts[q], pts[toe]), n["dirs"]["B"]) < angle_to(sub(pts[p], pts[toe]), n["dirs"]["B"]):
                    p, q = q, p
                hand = 1 if cross(sub(pts[p], pts[toe]), sub(pts[q], pts[toe])) > 0 else -1
                if hand != n["hand"]:
                    raise BuildError(f"{n['label']}: part {i} is {'RL'[hand < 0]}-hand, the plan says "
                                     f"{'RL'[n['hand'] < 0]}")
                assign = {"A": toe, "B": p, "C": q}
            else:           # a part with a misread end: match the ends it has by direction
                if len(e) >= len(n["dirs"]):
                    raise BuildError(f"{n['label']}: part {i} has {len(e)} ends, the switch {len(n['dirs'])} legs")
                assign = {}
                for x in e:
                    d = unit(sub(pts[x], n["xy"]))
                    port = max((pp for pp in n["dirs"] if pp not in assign),
                               key=lambda pp: d[0] * n["dirs"][pp][0] + d[1] * n["dirs"][pp][1])
                    assign[port] = x
            for port, x in assign.items():
                self.port_pt[(nid, port)] = pts[x]
                self.port_joint[(nid, port)] = self.joint[x]
            have = [math.dist(self.port_pt[(nid, p)], n["xy"]) for p in assign]
            for port in n["dirs"]:
                if port not in assign:
                    L = sum(have) / len(have)
                    self.port_pt[(nid, port)] = (n["xy"][0] + n["dirs"][port][0] * L,
                                                 n["xy"][1] + n["dirs"][port][1] * L)
                    self.notes.append(f"{n['label']}: leg {port} not in parts.json, drawn from the plan's direction")

        for i in sorted(self.shared_parts):     # a three-way: the export's two halves share its part
            e = [(i, k) for k in range(len(self.parts[i]["eps"]))]
            pts = {x: self.px(self.parts[i]["eps"][x[1]]) for x in e}
            toe = max(e, key=lambda x: sum(math.dist(pts[x], pts[y]) for y in e))
            halves = sorted(n for n, j in self.part_of.items() if j == i)
            L = UNMATCHED_LEG_CM * PX_PER_CM

            def a_of(n):
                d = self.nodes[n]["dirs"]["A"]
                return (self.nodes[n]["xy"][0] + d[0] * L, self.nodes[n]["xy"][1] + d[1] * L)

            first = min(halves, key=lambda n: math.dist(a_of(n), pts[toe]))
            delta = sub(pts[toe], a_of(first))       # the plan's points and the parts differ by the fit
            for n in halves:
                self.nodes[n]["xy"] = [self.nodes[n]["xy"][0] + delta[0], self.nodes[n]["xy"][1] + delta[1]]
            self.port_pt[(first, "A")] = pts[toe]
            self.port_joint[(first, "A")] = self.joint[toe]

    def _walk(self, start, came):
        """Follow flex track from joint `start` (leaving part `came`) to the next switch part or a dead end."""
        pts = [self.joint_point(start)]
        cur, seen = start, set()
        while True:
            att = [e for e in self.members[cur] if e[0] != came]
            sw = [e for e in att if e[0] in self.switch_parts]
            if sw:
                return pts, cur, sw
            if not att:
                return pts, cur, []
            if len(att) > 1:
                raise BuildError(f"track branches at a joint with no switch near {self.joint_point(cur)}")
            p, k = att[0]
            if len(self.parts[p]["eps"]) != 2:
                raise BuildError(f"part {p} ({self.parts[p]['name']}) has {len(self.parts[p]['eps'])} ends but "
                                 "is no switch of this graph: a crossing or an unmatched turnout")
            if p in seen:
                raise BuildError(f"track loops back on part {p}")
            seen.add(p)
            other = self.joint[(p, 1 - k)]
            pts.append(self.joint_point(other))
            came, cur = p, other

    def _end_start(self, nid):
        """The dead-end joint at a track end."""
        xy = self.nodes[nid]["xy"]
        nz = self.node_z(nid)
        best = None
        for j, mem in self.members.items():
            if len(mem) == 1 and mem[0][0] not in self.switch_parts:
                if nz is None or abs(self.joint_point(j)[2] - nz) > Z_TOL_CM:
                    continue        # a dead end on another level
                d = math.dist(self.joint_point(j)[:2], xy)
                if best is None or d < best[0]:
                    best = (d, j)
        if best is None or best[0] > 3 * PX_PER_CM:
            raise BuildError(f"no track end in parts.json near {nid}")
        return best[1]

    def _trace(self):
        """A polyline for every run, from u's leg to v's leg; fills in leg points no part gives."""
        loose = {}       # (node, port) -> point found at the end of a walk (switches with no part)
        for e in self.edges:
            ends = [(e["u"], e["up"]), (e["v"], e["vp"])]
            start = None
            for k, (n, p) in enumerate(ends):
                if (n, p) in self.port_joint:
                    start = (k, self.port_joint[(n, p)], self.part_of[n])
                    break
            if start is None:
                for k, (n, p) in enumerate(ends):
                    if self.nodes[n]["kind"] == "end":
                        start = (k, self._end_start(n), None)
                        break
            if start is None:
                e["pts"] = None      # both ends inside one part (the three-way's halves): straight
                continue
            k, j0, came = start
            pts, j1, hit = self._walk(j0, came)
            tn, tp = ends[1 - k]
            want = self.port_joint.get((tn, tp))
            if want is not None and want != j1:
                raise BuildError(f"run {e['id']} reaches {self.joint_point(j1)[:2]}, not {tn} leg {tp}")
            if self.nodes[tn]["kind"] == "end":
                if hit:
                    raise BuildError(f"run {e['id']} meets a switch before its end {tn}")
                self.nodes[tn]["xy"] = list(pts[-1][:2])
            elif want is None and not hit:
                loose[(tn, tp)] = pts[-1][:2]          # a switch with no part: its leg is where the track stops
            elif want is None and hit and self.part_of.get(tn) not in self.shared_parts:
                raise BuildError(f"run {e['id']} meets part {hit[0][0]}, not {tn}")
            e["pts"] = pts if k == 0 else pts[::-1]
        self.port_pt.update(loose)
        for nid, n in sorted(self.nodes.items()):
            if n["kind"] == "end":
                continue
            for port, d in n["dirs"].items():
                if (nid, port) not in self.port_pt:
                    L = UNMATCHED_LEG_CM * PX_PER_CM
                    self.port_pt[(nid, port)] = (n["xy"][0] + d[0] * L, n["xy"][1] + d[1] * L)
        for nid, n in self.nodes.items():
            if n["kind"] == "dx":
                pts = [self.port_pt[(nid, p)] for p in "ABCD"]
                n["xy"] = [sum(p[0] for p in pts) / 4, sum(p[1] for p in pts) / 4]
        for e in self.edges:          # whole polylines, leg point to leg point
            a, b = self.leg(e["u"], e["up"]), self.leg(e["v"], e["vp"])
            mid = list(e["pts"] or [])
            out = [a]
            for p in mid + [b]:
                if math.dist(p[:2], out[-1][:2]) > 1.0:
                    out.append(p)
            if len(out) == 1:
                out.append(b)
            out[-1] = b
            e["pts"] = out

    def leg(self, nid, port):
        n = self.nodes[nid]
        if n["kind"] == "end":
            return (n["xy"][0], n["xy"][1], None)
        p = self.port_pt[(nid, port)]
        return (p[0], p[1], None)

    # ---- the owner's overrides
    def by_label(self, ref):
        try:
            return self.edits_mod.by_label({"nodes": self.nodes, "edges": self.edges}, ref)
        except self.plugin_error as exc:
            raise BuildError(str(exc)) from None

    def edge_at(self, n, port):
        return next(e for e in self.edges if (e["u"], e["up"]) == (n, port) or (e["v"], e["vp"]) == (n, port))

    @staticmethod
    def oriented(e, n, port):
        """e's polyline starting at (n, port)."""
        return e["pts"] if (e["u"], e["up"]) == (n, port) else e["pts"][::-1]

    def _apply_edits(self):
        for ed in self.overrides.get("edits", []):
            if ed["op"] == "relabel":
                for old, new in ed["map"].items():
                    n = self.by_label(old)
                    self.nodes[n]["alias"], self.nodes[n]["label"] = old, new
            elif ed["op"] == "move":
                self._move(ed)
            else:
                raise BuildError(f"plan override {ed['op']!r} is not handled here; add it")
        # the plugin's own edits on the bare graph must give the same switches and runs
        topo = copy.deepcopy(self.original)
        try:
            self.edits_mod.apply_edits(topo, copy.deepcopy(self.overrides.get("edits", [])))
        except self.plugin_error as exc:
            raise BuildError(f"plan overrides: {exc}") from None

        def runs(g):
            return sorted(tuple(sorted([(g["nodes"][e["u"]].get("label", e["u"]).rstrip("*"), e["up"]),
                                        (g["nodes"][e["v"]].get("label", e["v"]).rstrip("*"), e["vp"])]))
                          for e in g["edges"])

        def junctions(g):
            return sorted((d["label"].rstrip("*"), d["hand"]) for d in g["nodes"].values() if d["kind"] != "end")

        mine = {"nodes": self.nodes, "edges": self.edges}
        if runs(topo) != runs(mine) or junctions(topo) != junctions(mine):
            raise BuildError("the panel's edits and the schematic plugin's differ; update _move to match")
        self.topology = topo

    def _move(self, ed):
        """As the schematic plugin's `move`: lift the switch out of one run and set it into another."""
        x = self.by_label(ed["switch"])
        p1, p2 = ed["through"]
        leg = next(p for p in "ABC" if p not in (p1, p2))
        old = {p: self.port_pt[(x, p)] for p in "ABC"}
        e1, e2, e3 = self.edge_at(x, p1), self.edge_at(x, p2), self.edge_at(x, leg)
        a = (e1["v"], e1["vp"]) if (e1["u"], e1["up"]) == (x, p1) else (e1["u"], e1["up"])
        b = (e2["v"], e2["vp"]) if (e2["u"], e2["up"]) == (x, p2) else (e2["u"], e2["up"])
        n0, n1 = self.by_label(ed["onto"][0]), self.by_label(ed["onto"][1])
        onto = [e for e in self.edges if {e["u"], e["v"]} == {n0, n1}]
        if len(onto) != 1:
            raise BuildError(f"move {ed['switch']}: {len(onto)} runs join {ed['onto']}")
        t = onto[0]
        # lift: the run through p1 and p2 stays as plain track
        joined = self.oriented(e1, *a)[:-1] + self.oriented(e2, x, p2)[1:]
        self.edges = [e for e in self.edges if e is not e1 and e is not e2]
        self.edges.append(dict(e1, id=e1["id"] + "+" + e2["id"], u=a[0], up=a[1], v=b[0], vp=b[1],
                               cm=round(e1["cm"] + e2["cm"], 1), pts=joined, hidden=e1["hidden"] or e2["hidden"]))
        if (e3["u"], e3["up"]) == (x, leg):
            e3["up"] = "C"
        else:
            e3["vp"] = "C"
        # set in: B toward the first switch named, A toward the other (the plugin's points_toward_first=False)
        end0 = (t["u"], t["up"]) if t["u"] == n0 else (t["v"], t["vp"])
        end1 = (t["v"], t["vp"]) if t["u"] == n0 else (t["u"], t["up"])
        run = self.oriented(t, *end0)
        at = max(5.0, min(ed["cm_from_first"], t["cm"] - 5))
        total = polyline_length(run)
        lab = math.dist(old["A"], old["B"])
        if total <= lab:
            raise BuildError(f"move {ed['switch']}: the run {ed['onto']} is shorter than the switch")
        s = min(max(at / t["cm"] * total, lab / 2), total - lab / 2)     # the whole switch on the run
        along = (sub(old["C"], old["A"])[0] * unit(sub(old["B"], old["A"]))[0]
                 + sub(old["C"], old["A"])[1] * unit(sub(old["B"], old["A"]))[1])
        lat = abs(cross(unit(sub(old["B"], old["A"])), sub(old["C"], old["A"])))
        B, ib = point_at(run, s - lab / 2)
        A, ia = point_at(run, s + lab / 2)
        u = unit(sub(B, A))
        hand = {"R": 1, "L": -1}[ed["hand"]]
        nrm = (-u[1] * hand, u[0] * hand)
        C = (A[0] + along * u[0] + lat * nrm[0], A[1] + along * u[1] + lat * nrm[1])
        self.port_pt.update({(x, "A"): A, (x, "B"): B, (x, "C"): C})
        self.nodes[x].update(hand=hand, z=ed.get("z", self.nodes[x].get("z")),
                             xy=[(A[0] + B[0]) / 2, (A[1] + B[1]) / 2])
        self.edges.remove(t)
        self.edges.append(dict(t, id=t["id"] + "a", u=end0[0], up=end0[1], v=x, vp="B", cm=round(at, 1),
                               pts=run[:ib] + [(*B, None)]))
        self.edges.append(dict(t, id=t["id"] + "b", u=x, up="A", v=end1[0], vp=end1[1], cm=round(t["cm"] - at, 1),
                               pts=[(*A, None)] + run[ia:]))
        # the run on the moved switch's third leg now ends at the new leg C: drop what lies past it
        c_run = self.oriented(e3, x, "C")[::-1]           # from its far end toward the switch
        keep = min(range(len(c_run)), key=lambda i: math.dist(c_run[i][:2], C))
        c_run = c_run[:keep] + [(*C, None)]
        e3["pts"] = c_run if (e3["v"], e3["vp"]) == (x, "C") else c_run[::-1]
        e3["free"] = (x, "C")      # the plan never ran this track to here: no direction forced at the leg
        self.notes.append(f"{self.nodes[x]['label']}: moved onto the run {ed['onto'][0]}-{ed['onto'][1]} "
                          f"at {at} cm, hand {ed['hand']} (plan overrides)")

    def _levels(self):
        """Each switch's and end's level, from the plugin's own cut (split_levels) of the edited graph."""
        spec = self.overrides["levels"]
        names = [b["name"] for b in spec["bands"]]
        if len(names) != 2:
            raise BuildError(f"the panel draws two levels; the plan overrides give {len(names)} bands")
        try:
            bands = self.edits_mod.split_levels(copy.deepcopy(self.topology), copy.deepcopy(spec))
        except self.plugin_error as exc:
            raise BuildError(f"levels: {exc}") from None
        self.level = {}
        for name, sub_graph in bands:
            for nid in sub_graph["nodes"]:
                if nid in self.nodes:
                    self.level[nid] = names.index(name)
        missing = sorted(n for n in self.nodes if n not in self.level)
        if missing:
            raise BuildError(f"no level for {missing}")

    def point_level(self, z, fallback):
        return fallback if z is None else z_level(z, self.overrides["levels"])


# ---------------------------------------------------------------- the panel

def os_name(label: str) -> str:
    return "OS Switch " + label.rstrip("AB")


def tangent_out(plan, nid, port):
    """Direction the track leaves a switch leg (away from the switch)."""
    n = plan.nodes[nid]
    P = plan.port_pt
    if n["kind"] == "dx":
        opp = {"A": "B", "B": "A", "C": "D", "D": "C"}[port]
        return unit(sub(P[(nid, port)], P[(nid, opp)]))
    if port == "A":
        return unit(sub(P[(nid, "A")], P[(nid, "B")]))
    return unit(sub(P[(nid, port)], P[(nid, "A")]))


class Panel:
    def __init__(self, plan: Plan):
        self.plan = plan
        self.turnouts: list[ET.Element] = []
        self.segments: list[ET.Element] = []
        self.points: list[ET.Element] = []
        self.blocks: dict[str, float] = {}         # block user name -> length mm
        self.n_anchor = 0
        self.cuts: dict[str, int | None] = {}      # run id -> vertex where it changes level
        self.n_seg = 0
        self._offsets()
        self.ident = {}
        for nid, n in plan.nodes.items():
            self.ident[nid] = (f"EB{TAG}-{nid[4:]}" if n["kind"] == "end" else f"TO{TAG}-{n['label']}")
        self.conn: dict[tuple[str, str], str] = {}
        for e in sorted(plan.edges, key=lambda e: edge_sort(e["id"])):
            self._run(e)
        for nid in sorted(plan.nodes, key=lambda n: (plan.nodes[n]["kind"] == "end", plan.nodes[n]["label"], n)):
            n = plan.nodes[nid]
            if n["kind"] == "end":
                self._bumper(nid)
            else:
                self._turnout(nid)

    def _offsets(self):
        p = self.plan
        box = {0: [], 1: []}
        for e in p.edges:
            lu, lv = p.level[e["u"]], p.level[e["v"]]
            for i, q in enumerate(e["pts"]):
                box[lu if lu == lv or i < len(e["pts"]) / 2 else lv].append(q[:2])
        bounds = {k: (min(q[0] for q in v), min(q[1] for q in v), max(q[0] for q in v), max(q[1] for q in v))
                  for k, v in box.items()}
        m = bounds[0]
        u = bounds[1]
        top = min(m[1], u[1])
        self.offset = {0: (MARGIN_PX - m[0], MARGIN_PX - top),
                       1: (MARGIN_PX + (m[2] - m[0]) + LEVEL_GAP_PX - u[0], MARGIN_PX - top)}
        right = self.offset[1][0] + u[2]
        bottom = max(m[3], u[3]) + self.offset[0][1]
        self.size = (math.ceil(right + MARGIN_PX), math.ceil(bottom + MARGIN_PX))

    def at(self, q, level):
        o = self.offset[level]
        return (q[0] + o[0], q[1] + o[1])

    def block_of(self, e):
        lu, lv = self.plan.nodes[e["u"]].get("label", ""), self.plan.nodes[e["v"]].get("label", "")
        if (e["u"] != e["v"] and lu and lv and lu[-1:] in "AB" and lv[-1:] in "AB"
                and lu[:-1] == lv[:-1] and lu[:-1].isdigit()):
            return os_name(lu)          # the track between a crossover's two halves
        return f"Track {e['id']}"

    def _anchor(self, xy, run_anchors):
        self.n_anchor += 1
        ident = f"A{TAG}-{self.n_anchor}"
        el = ET.Element("positionablepoint", {"ident": ident, "type": "ANCHOR", "x": r1(xy[0]), "y": r1(xy[1])})
        self.points.append(el)
        run_anchors[ident] = el
        return ident, el

    def _segment(self, block, c1, t1, c2, t2, p0, p1, a0, a1, dashed, hidden):
        self.n_seg += 1
        ident = f"T{TAG}-{self.n_seg}"
        attrs = {"ident": ident, "blockname": block, "connect1name": c1, "type1": t1,
                 "connect2name": c2, "type2": t2, "dashed": "yes" if dashed else "no",
                 "mainline": "yes", "hidden": "yes" if hidden else "no"}
        el = ET.Element("tracksegment", attrs)
        if not hidden and a0 is not None and a1 is not None:
            chord = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
            off0 = (a0 - chord + math.pi) % (2 * math.pi) - math.pi
            off1 = (a1 - chord + math.pi) % (2 * math.pi) - math.pi
            if abs(off0) > 0.005 or abs(off1) > 0.005:       # not straight: a cubic Bezier with the arc's handles
                theta = off1 - off0
                L = math.dist(p0, p1)
                h = L / 3 if abs(theta) < 1e-6 else L * (4 / 3) * math.tan(theta / 4) / (2 * math.sin(theta / 2))
                el.set("bezier", "yes")
                el.set("hideConLines", "yes")
                cps = ET.SubElement(el, "controlpoints")
                for i, c in enumerate(((p0[0] + h * math.cos(a0), p0[1] + h * math.sin(a0)),
                                       (p1[0] - h * math.cos(a1), p1[1] - h * math.sin(a1)))):
                    ET.SubElement(cps, "controlpoint", {"index": str(i), "x": r1(c[0]), "y": r1(c[1])})
        el.set("class", CLASS["segment"])
        self.segments.append(el)
        return ident

    def _run(self, e):
        p = self.plan
        block = self.block_of(e)
        self.blocks.setdefault(block, 0.0)
        self.blocks[block] += e["cm"] * 10
        lu, lv = p.level[e["u"]], p.level[e["v"]]
        pts = e["pts"]
        cut = None
        if lu != lv:          # the vertex where the run reaches the other level's height
            for i in range(1, len(pts) - 1):
                if pts[i][2] is not None and p.point_level(pts[i][2], lu) == lv:
                    cut = i
                    break
            if cut is None:
                cut = len(pts) // 2 if len(pts) > 2 else None
            self.cuts[e["id"]] = cut
            if cut is None:          # no vertex to cut at: add the midpoint
                mid = ((pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2, None)
                pts = [pts[0], mid, pts[1]]
                cut = 1
        levels = [lu if (cut is None or i <= cut) else lv for i in range(len(pts))]
        # directions along the run at each vertex: each flex piece as near a circular arc as the joints allow,
        # the ends along the switch legs
        n = len(pts)
        free = e.get("free")
        d0 = (tangent_out(p, e["u"], e["up"])
              if p.nodes[e["u"]]["kind"] != "end" and free != (e["u"], e["up"]) else None)
        d1 = (tangent_out(p, e["v"], e["vp"])
              if p.nodes[e["v"]]["kind"] != "end" and free != (e["v"], e["vp"]) else None)
        ang = arc_tangents([q[:2] for q in pts], d0, (-d1[0], -d1[1]) if d1 else None)
        # connection names along the run
        names = [(self.ident[e["u"]], self._ctype(e["u"], e["up"]))]
        run_anchors: dict[str, ET.Element] = {}
        jump = {}
        for i in range(1, n - 1):
            ident, el = self._anchor(self.at(pts[i], levels[i]), run_anchors)
            names.append((ident, "POS_POINT"))
            if i == cut:
                ident2, el2 = self._anchor(self.at(pts[i], lv), run_anchors)
                jump[i] = (el, el2, ident2)
        names.append((self.ident[e["v"]], self._ctype(e["v"], e["vp"])))
        anchor_el = {}
        for k in range(n - 1):
            c1, t1 = names[k]
            c2, t2 = names[k + 1]
            q0 = self.at(pts[k], levels[k])
            q1 = self.at(pts[k + 1], levels[k + 1])
            if k in jump:        # this segment leaves the far side of the cut
                el, el2, ident2 = jump[k]
                c1 = ident2
                q0 = self.at(pts[k], lv)
            seg = self._segment(block, c1, t1, c2, t2, q0, q1, ang[k], ang[k + 1], e.get("hidden", False), False)
            for c, t in ((c1, t1), (c2, t2)):
                if t == "POS_POINT" and c.startswith("A"):
                    anchor_el.setdefault(c, []).append(seg)
                else:
                    self.conn[(c, t)] = seg
        for i, (el, el2, ident2) in jump.items():   # the hidden track across the gap between the levels
            hseg = self._segment(block, el.get("ident"), "POS_POINT", ident2, "POS_POINT",
                                 (float(el.get("x")), float(el.get("y"))),
                                 (float(el2.get("x")), float(el2.get("y"))), None, None, False, True)
            anchor_el.setdefault(el.get("ident"), []).append(hseg)
            anchor_el.setdefault(ident2, []).append(hseg)
        for ident, pt in run_anchors.items():
            segs = anchor_el.get(ident, [])
            if len(segs) != 2:
                raise BuildError(f"anchor {ident} has {len(segs)} tracks")
            pt.set("connect1name", segs[0])
            pt.set("connect2name", segs[1])
            pt.set("class", CLASS["point"])

    def _ctype(self, nid, port):
        return "POS_POINT" if self.plan.nodes[nid]["kind"] == "end" else f"TURNOUT_{port}"

    def _bumper(self, nid):
        p = self.plan
        q = self.at(p.nodes[nid]["xy"], p.level[nid])
        ident = self.ident[nid]
        el = ET.Element("positionablepoint", {"ident": ident, "type": "END_BUMPER", "x": r1(q[0]), "y": r1(q[1]),
                                              "connect1name": self.conn[(ident, "POS_POINT")],
                                              "class": CLASS["point"]})
        self.points.append(el)

    def _turnout(self, nid):
        p = self.plan
        n = p.nodes[nid]
        lv = p.level[nid]
        ident = self.ident[nid]
        P = {port: self.at(p.port_pt[(nid, port)], lv) for port in n["dirs"]}
        block = os_name(n["label"])
        self.blocks.setdefault(block, 0.0)
        if n["kind"] == "dx":
            ttype, ver = "DOUBLE_XOVER", "2"
            cen = (sum(q[0] for q in P.values()) / 4, sum(q[1] for q in P.values()) / 4)
            self.blocks[block] += math.dist(P["A"], P["B"]) / PX_PER_CM * 10
        else:
            ttype, ver = ("RH_TURNOUT" if n["hand"] > 0 else "LH_TURNOUT"), "1"
            cen = ((P["A"][0] + P["B"][0]) / 2, (P["A"][1] + P["B"][1]) / 2)
            self.blocks[block] += math.dist(P["A"], P["B"]) / PX_PER_CM * 10
        A = P["A"]
        D = P.get("D", A)
        attrs = {"ident": ident, "type": ttype, "hidden": "no", "disabled": "no", "disableWhenOccupied": "yes",
                 "continuing": "2", "xcen": r1(cen[0]), "ycen": r1(cen[1]), "xa": r1(A[0]), "ya": r1(A[1]),
                 "xb": r1(P["B"][0]), "yb": r1(P["B"][1]), "xc": r1(P["C"][0]), "yc": r1(P["C"][1]),
                 "xd": r1(D[0]), "yd": r1(D[1]), "ver": ver, "class": CLASS[ttype],
                 "turnoutname": f"Switch {n['label']}", "blockname": block}
        if ttype == "DOUBLE_XOVER":
            attrs.update(blockbname=block, blockcname=block, blockdname=block)
        for port in n["dirs"]:
            attrs[f"connect{port.lower()}name"] = self.conn[(ident, f"TURNOUT_{port}")]
        self.turnouts.append(ET.Element("layoutturnout", attrs))


def arc_tangents(pts, start=None, end=None):
    """Track direction (radians, y down) at each vertex of a run of flex pieces.

    Each piece between two joints is taken as a circular arc, whose end directions sit symmetrically about
    its chord: a[i] + a[i+1] = 2 * chord[i]. The ends follow the switch legs where there are any (start,
    end: unit vectors). Solved by least squares with a light pull toward the Catmull-Rom direction, so a
    run with a free end still has one answer.
    """
    n = len(pts)
    phi = []
    for p, q in zip(pts, pts[1:]):
        a = math.atan2(q[1] - p[1], q[0] - p[0])
        if phi:
            a = phi[-1] + (a - phi[-1] + math.pi) % (2 * math.pi) - math.pi
        phi.append(a)

    def near(a, ref):
        return ref + (a - ref + math.pi) % (2 * math.pi) - math.pi

    rows = []                       # (weights by index, value, row weight)
    for i, f in enumerate(phi):
        rows.append(({i: 1.0, i + 1: 1.0}, 2 * f, 1.0))
    for i in range(n):
        guide = phi[0] if i == 0 else phi[-1] if i == n - 1 else (phi[i - 1] + phi[i]) / 2
        rows.append(({i: 1.0}, guide, 0.05))
    if start is not None:
        rows.append(({0: 1.0}, near(math.atan2(start[1], start[0]), phi[0]), 10.0))
    if end is not None:
        rows.append(({n - 1: 1.0}, near(math.atan2(end[1], end[0]), phi[-1]), 10.0))
    M = [[0.0] * n for _ in range(n)]
    v = [0.0] * n
    for coef, val, w in rows:
        for i, ci in coef.items():
            v[i] += w * w * ci * val
            for j, cj in coef.items():
                M[i][j] += w * w * ci * cj
    for c in range(n):              # Gaussian elimination (M is symmetric positive definite)
        for r in range(c + 1, n):
            f = M[r][c] / M[c][c]
            if f:
                for k in range(c, n):
                    M[r][k] -= f * M[c][k]
                v[r] -= f * v[c]
    out = [0.0] * n
    for r in range(n - 1, -1, -1):
        out[r] = (v[r] - sum(M[r][k] * out[k] for k in range(r + 1, n))) / M[r][r]
    return out


def edge_sort(eid: str):
    head = eid.split("+")[0]
    digits = "".join(c for c in head if c.isdigit())
    return (int(digits or 0), eid)


# ---------------------------------------------------------------- tables

def check_hands(plan: Plan, hands_path: Path = HANDS) -> None:
    if not hands_path.exists():
        raise BuildError(f"{hands_path} is missing")
    with open(hands_path, newline="", encoding="utf-8") as fh:
        want = {r["switch"]: r["hand"] for r in csv.DictReader(fh)}
    bad = []
    for n in plan.nodes.values():
        if n["kind"] == "switch":
            got = "R" if n["hand"] > 0 else "L"
            if want.get(n["label"]) not in (None, got):
                bad.append(f"{n['label']} plan {got}, hands.csv {want[n['label']]}")
            if n["label"] not in want:
                bad.append(f"{n['label']} not in hands.csv")
    if bad:
        raise BuildError("hands disagree: " + "; ".join(bad))


def place(parent: ET.Element, new: list[ET.Element], depth: int, after: ET.Element | None = None) -> None:
    """Insert `new` into `parent` after `after` (default: at the end), indented as JMRI writes."""
    kids = list(parent)
    idx = kids.index(after) + 1 if after is not None else len(kids)
    prev = kids[idx - 1] if idx else None
    pad = "\n" + "  " * depth
    tail = prev.tail if prev is not None else parent.text
    for k, el in enumerate(new):
        ET.indent(el, space="  ", level=depth)
        parent.insert(idx + k, el)
        el.tail = pad
    if new:
        if prev is not None:
            prev.tail = pad
        else:
            parent.text = pad
        new[-1].tail = tail


def bean(tag: str, attrs: dict, sysname: str, user: str, *children) -> ET.Element:
    el = ET.Element(tag, attrs)
    ET.SubElement(el, "systemName").text = sysname
    ET.SubElement(el, "userName").text = user
    for t, v in children:
        ET.SubElement(el, t).text = v
    return el


def build(live_path: Path = paths.TABLES_XML) -> tuple[bytes, Plan, Panel]:
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    parts = json.loads(PARTS.read_text(encoding="utf-8"))
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    plan = Plan(graph, parts, overrides)
    check_hands(plan)
    panel = Panel(plan)
    doc = tables.load(live_path)
    root = doc.root

    if any(le.get("name") == PANEL_NAME for le in tables.layout_editors(root)):
        raise BuildError(f"{live_path} already has a panel named {PANEL_NAME}")
    taken_users = {tables.user_name(b) for b in tables.turnouts(root) + tables.blocks(root, full=False)
                   + tables.layout_blocks(root)}
    taken_sys = {tables.system_name(b) for b in tables.turnouts(root) + tables.blocks(root, full=False)
                 + tables.layout_blocks(root)}

    # turnouts: into the internal turnout manager
    internal = next(s for s in root.findall("turnouts") if "InternalTurnoutManager" in (s.get("class") or ""))
    new_t = []
    for lt in panel.turnouts:
        user = lt.get("turnoutname")
        sysname = TURNOUT_SYS + user.split(" ", 1)[1]
        new_t.append(bean("turnout", {"feedback": "DIRECT", "inverted": "false", "automate": "Off"}, sysname, user,
                          ("comment", COMMENT)))
    place(internal, new_t, 2)

    # blocks: the names-only pass, then the full pass, as JMRI stores them
    blocks_el = root.find("blocks")
    names = sorted(panel.blocks, key=block_sort)
    sysnames = {name: f"{BLOCK_SYS}{i:04d}" for i, name in enumerate(names, 1)}
    kids = [b for b in blocks_el.findall("block")]
    first_full = next(b for b in kids if b.get("length") is not None)
    last_short = kids[kids.index(first_full) - 1]
    place(blocks_el, [bean("block", {"systemName": sysnames[nm]}, sysnames[nm], nm) for nm in names], 2, last_short)
    place(blocks_el, [bean("block", {"systemName": sysnames[nm], "length": r1(panel.blocks[nm]), "curve": "0"},
                           sysnames[nm], nm, ("comment", COMMENT), ("permissive", "no")) for nm in names], 2)
    lbs = root.find("layoutblocks")
    place(lbs, [bean("layoutblock", {"systemName": f"ILB{LAYOUT_BLOCK_FIRST + i}", "occupiedsense": "2",
                                     "trackcolor": "gray", "occupiedcolor": "red", "extracolor": "white"},
                     f"ILB{LAYOUT_BLOCK_FIRST + i}", nm) for i, nm in enumerate(names)], 2)

    new_users = [t.get("turnoutname") for t in panel.turnouts] + names
    new_sys = ([TURNOUT_SYS + t.get("turnoutname").split(" ", 1)[1] for t in panel.turnouts]
               + list(sysnames.values()) + [f"ILB{LAYOUT_BLOCK_FIRST + i}" for i in range(len(names))])
    clash = sorted((set(new_users) & taken_users) | (set(new_sys) & taken_sys))
    if clash or len(set(new_users)) != len(new_users) or len(set(new_sys)) != len(new_sys):
        raise BuildError(f"names collide: {clash}")

    # the panel, after the last panel
    template = tables.layout_editor(root, TEMPLATE_PANEL)
    le = ET.Element("LayoutEditor", dict(template.attrib))
    le.set("name", PANEL_NAME)
    le.set("x", "0")
    le.set("y", "0")
    le.set("panelwidth", str(panel.size[0]))
    le.set("panelheight", str(panel.size[1]))
    le.set("windowwidth", "1600")
    le.set("windowheight", "1000")
    le.set("scrollable", "both")
    le.set("editable", "yes")
    le.set("autoblkgenerate", "no")
    opts = copy.deepcopy(template.find("layoutTrackDrawingOptions"))
    opts.set("name", PANEL_NAME)
    for el in [opts] + panel.turnouts + panel.segments + panel.points:
        le.append(el)
    last_le = tables.layout_editors(root)[-1]
    place(root, [le], 1, last_le)
    return doc.tobytes(), plan, panel


def block_sort(name: str):
    kind = 0 if name.startswith("OS ") else 1
    return (kind, edge_sort(name.split(" ")[-1]), name)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="regenerate in memory and fail if the trial file differs")
    ap.add_argument("--out", type=Path, default=TRIAL, help="where to write (default: the trial file)")
    args = ap.parse_args(argv)
    try:
        data, plan, panel = build()
    except BuildError as exc:
        print(f"ERROR: {exc}")
        return 1
    summary = (f"panel {PANEL_NAME!r}: {len(panel.turnouts)} turnouts, {len(panel.segments)} track segments, "
               f"{len(panel.points)} points, {len(panel.blocks)} blocks; {panel.size[0]}x{panel.size[1]} px")
    if args.check:
        if not args.out.exists() or args.out.read_bytes() != data:
            print(f"STALE: {paths.rel(args.out)}; run {paths.rel(Path(__file__))}")
            return 1
        print(f"ok: {paths.rel(args.out)} is current ({summary})")
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    doc = tables.loads(data, path=args.out)
    doc.save(args.out)
    print(f"wrote {paths.rel(args.out)}: {summary}")
    for note in plan.notes:
        print(f"  note: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
