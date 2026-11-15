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
  (media/hart-research/wiring-drafts/lcos-node-grid-2025-10-06b.xlsx, local), where an address 0XN is device X off
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
  number, as the Layout Editor trial has it), occupancy "BS <block without Track>".
- Track "Track <a>-<b>" from its end switches (numbers, H1 or H2 for a helix), "Track <n> Spur" to a bumper,
  "Track <n> Loop" back to the same switch; parallel tracks between the same ends take " 1", " 2" from the top row.
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
UID = {"block": 0, "turnout": 8, "signal": 32, "sensor": 67}
COLUMNS = ["level", "cp", "layer", "user_name", "system_name", "node", "dcc", "comment", "trial_name", "notes"]
DCC_FIRST = 120                       # staging uses 100-119 (MTT100-MTT119); the owner continues from 120
TAU = {"A": -1, "B": 1, "C": 1, "D": -1}      # the plugin's leg sides (schematic.core.TAU)


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
        return ("helix", helix_tag[band_level(bands[bi][0])])
    if d.get("sub") == "link" and (bi, node_id) in joined:
        bj, m = joined[(bi, node_id)]
        other = bands[bj][1]
        sid = next(iter(list(other["nodes"][m]["ins"].values()) + list(other["nodes"][m]["outs"].values())))
        s = other["strands"][sid]
        far = s["dst"][0] if s["src"][0] == m else s["src"][0]
        return end_ref(bands, joined, bj, far, helix_tag)
    return ("bumper", None)


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
            la, lb = nodes[start[0]].get("label", ""), nodes[end[0]].get("label", "")
            if a[0] == b[0] == "sw" and a[1] == b[1] and la != lb and la[-1:] in "AB" and lb[-1:] in "AB":
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


# ---------------------------------------------------------------- the map

def masts(bands, cps, found, cp_of) -> list[dict]:
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
                if kind == "bumper" or (kind == "sw" and cp_of.get(far) == cp):
                    continue
                eastward = TAU[p] * rail[n] == 1
                sid = d["ins"].get(p) or d["outs"].get(p)
                out.append(dict(level=lv, cp=cp, switch=num, number=int(num) + 1, letter="L" if eastward else "R",
                                heads=2 if (p == "A" or d["kind"] == "dx") else 1, row=srow.get(sid, 0),
                                track=t["name"], band=bi))
    groups = defaultdict(list)
    for m in out:
        groups[(m["number"], m["letter"])].append(m)
    for (num, letter), ms in groups.items():
        if len(ms) > 2:
            raise MapError(f"switch {num - 1}: {len(ms)} masts for direction {letter}; ADR-005 names two (A and B)")
        ms.sort(key=lambda m: (m["band"], m["row"]))
        for i, m in enumerate(ms):
            m["name"] = f"{num}{letter}" + ("AB"[i] if len(ms) == 2 else "")
    return out


def build(bands, joined, runs, overrides, cps, node_rows, local=()) -> tuple[dict, list[dict]]:
    """(control_points, device map rows). `local`: the switches in no control point (local_switches_main_upper.csv
    rows). Every switch on the main and upper bands must be in exactly one of the two."""
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
    ms = masts(bands, cps, found, cp_of)
    nodes = Nodes(node_rows)
    rows = []

    def add(level, cp, layer, user, system="", node="", comment="", trial="", notes="", dcc=""):
        rows.append(dict(level=level, cp=cp, layer=layer, user_name=user, system_name=system,
                         node=node, dcc=dcc, comment=comment, trial_name=trial, notes=notes))

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
        if not detect:
            add(lv, name, "block", f"OS Switch {s}", "", "", comment, f"OS Switch {s}",
                "no detector: off the main line")
            return
        bnode = nodes.pick(lv, area, "block", prefer=[home[s]])
        k, packed = nodes.take(bnode, "block")
        add(lv, name, "block", f"OS Switch {s}", "", bnode, comment, f"OS Switch {s}")
        add(lv, name, "occupancy", f"BS Switch {s}", f"M2S{packed}", bnode, f"Node: {bnode} Block: {k + 1}")

    for cp in cps:
        lv, area, name = cp["level"], cp["area"], cp["cp_name"]
        node = nodes.pick(lv, area, "turnout", len(cp["switches"]))
        for s in cp["switches"]:
            switch_rows(lv, area, name, s, node)
        for s in cp["switches"]:
            os_rows(lv, area, name, s, name)
        for m in sorted((m for m in ms if m["cp"] == name), key=lambda m: natural(m["name"])):
            hnode = nodes.pick(lv, area, "signal", m["heads"], prefer=[node])
            heads = []
            for part in (["Top", "Bottom"] if m["heads"] == 2 else [""]):
                k, packed = nodes.take(hnode, "signal")
                heads.append((f"Head {m['name']}" + (f" {part}" if part else ""), f"IH{packed}", k))
            kind = "two-searchlight" if m["heads"] == 2 else "one-low"
            sysname = f"IF$shsm:basic:{kind}(" + ")(".join(h[1] for h in heads) + ")"
            add(lv, name, "mast", f"Mast {m['name']}", sysname, hnode, f"{name} | Switch {m['switch']}",
                notes=f"home signal from {m['track']}")
            for user, sysn, k in heads:
                add(lv, name, "head", user, sysn, hnode, f"Node: {hnode} Signal: {k}")

    for s in sorted(loc, key=natural):          # no control point: turnout and detection, no signals
        r = loc[s]
        node = nodes.pick(r["level"], r["area"], "turnout")
        switch_rows(r["level"], r["area"], "", s, node, "no control point: " + r["notes"])
        os_rows(r["level"], r["area"], "", s, r["area"], detect=False)

    for t in sorted(found, key=lambda t: natural(t["name"])):
        sws = [v for k, v in t["ends"] if k == "sw"]
        ends_cp = sorted({cp_of[v] for v in sws if v in cp_of}, key=natural)
        cp = ends_cp[0] if ends_cp else ""
        short = t["cm"] < SHORT_CM and all(k == "sw" for k, _ in t["ends"])
        note = f"{t['cm']} cm" + (" short link: inside the OS blocks of its switches, no detector" if short else
                                  "" if t["main"] else " no detector: off the main line")
        add(t["level"], cp, "block", t["name"], "", "", " / ".join(ends_cp), ", ".join(t["trial"]), note)
        if short or not t["main"] or not sws:
            continue
        sws.sort(key=lambda s: area_of[s][0] != t["level"])      # a node on the track's own level first
        lv, area = area_of[sws[0]]
        bnode = nodes.pick(lv, area, "block", prefer=[home[s] for s in sws])
        k, packed = nodes.take(bnode, "block")
        add(t["level"], cp, "occupancy", "BS " + t["name"].removeprefix("Track "), f"M2S{packed}", bnode,
            f"Node: {bnode} Block: {k + 1}")
    order = {"turnout": 0, "fb": 1, "block": 2, "occupancy": 3, "mast": 4, "head": 5}
    rows.sort(key=lambda r: (r["level"], order[r["layer"]], natural(r["user_name"])))
    return cp_keys, rows


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
    built = sheet.build([(json.loads((pd.GRAPHS / g).read_text(encoding="utf-8")), n) for g, n in pd.INPUTS],
                        str(pd.DATA))
    return built.bands, le_mod.partners(built.bands), bl.runs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if an output is stale")
    args = ap.parse_args(argv)
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    import build_layout_le as bl
    try:
        bands, joined, runs = solve()
    except bl.BuildError as exc:
        if not args.check:
            raise
        print(f"SKIPPED device map check: {exc}")
        return 1 if os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0
    try:
        cp_keys, rows = build(bands, joined, runs, overrides, load_cps(), read_csv(NODES), read_csv(LOCAL))
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
