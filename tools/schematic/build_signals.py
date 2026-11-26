"""build_signals.py [--check]

Generate the schematic's layer 1 masts, a section per sheet of jmri/layouts/hart/data/schematic/signals.json
(hartlib.layer_files), from the staging
masts in the staging device map's form: masts.csv's staging rows (each mast's plan facts, blocks and slot kind), read
by staging_device_map.load_signal_masts; kept by hand since the device-map switch-over
(2026-11-17), first read from the hand-drawn panel by the schematic-maps plugin's signal reader. Main and upper are dark territory (no masts) until the owner's signal plan; add a level to LEVELS
when it has masts.

Each mast's schematic run (schematic_edge, schematic_toward_node) is checked against the plan graph in inputs/ with
the plan overrides' edits: the edge must exist, run between the switches named in `run`, carry the track names in
`names`, and end at the node it heads for, whose switch is `toward`. Its lengths are checked against the staging
tracks (staging_device_map.staging_chains) and block_lengths.csv's plan lengths: edge_cm is the length of the track holding the mast's facing block, and cm_from_toward
is 0 at a turnout leg, the whole run at an end bumper, and at an anchor the length from one end of that track to the
boundary between the facing and protected blocks (within TOLERANCE_CM). A mast that does not fit fails the run, with
or without --check. A mast on a balloon loop (an edge with both ends at one switch, the 107 Loop) names the switch leg
its half leaves from in "leg" (the plugin's signals field, schematic-maps 0.1.46), which the plugin needs to tell the
two halves apart: a switch's mast the leg it stands at, an APB intermediate the leg of the half its block is
(mast_rule.LOOP_HALF); no other mast names one.

--check regenerates in memory and compares (exit 1 if a section is stale). When SCHEMATIC_PLUGIN is not set and the
plugin submodule is not checked out or not at its pinned commit, --check prints SKIPPED and exits 0, so a checkout
without submodules still runs check.sh; with SCHEMATIC_REQUIRED=1 (set in CI) that skip is a failure instead.
"""
import difflib
import importlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA, GRAPHS, hartlib paths and the pinned plugin
import staging_device_map as sdm  # noqa: E402  the staging masts' plan facts, tracks and signal rows
from hartlib import block_lengths, layer_files, level_masts, railroad  # noqa: E402  the signals file; masts.csv; plan lengths

LEVELS = [("staging.json", "staging"), ("main.json", "main_upper")]   # plan graph in inputs/, section of signals.json
SCHEMA = "schematic.signals/1"
BLOCK_LENGTHS = block_lengths.PLAN
TOLERANCE_CM = 0.2          # the reader rounds each length to 0.1 cm
TURNBACK_CM = 1.0           # a mast measured from a turnback stands just off it (not "at the points")


class SignalsError(Exception):
    """A mast, a length or the staging map does not fit the plan; the message names it. main() prints it and exits 1."""


def block_cm(path=BLOCK_LENGTHS) -> dict:
    """{block: cm} of the plan lengths in block_lengths.csv (hartlib.block_lengths.plan_cm): the masts stand on the drawn
    geometry, so a timed length never moves one."""
    try:
        return block_lengths.plan_cm(path)
    except railroad.FactsError as exc:
        raise SignalsError(str(exc)) from exc


def check_lengths(masts: list[dict], chains: list[dict], cm: dict) -> list[str]:
    """Problems with each mast's edge_cm and cm_from_toward against the frozen tracks' block lengths."""
    near = lambda a, b: abs(a - b) <= TOLERANCE_CM      # noqa: E731
    missing = sorted({b for c in chains for b in c["blocks"]} - set(cm))
    bad = [f"block_lengths.csv has no plan length for {missing}"] if missing else []
    if bad:
        return bad
    for m in masts:
        tracks = [c for c in chains if m["facing"] in c["blocks"]]
        totals = [sum(cm[b] for b in c["blocks"]) for c in tracks]
        if not any(near(t, m["edge_cm"]) for t in totals):
            bad.append(f"{m['signal']}: edge_cm {m['edge_cm']} is not the length of a track holding "
                       f"{m['facing']} ({', '.join(f'{t:.1f}' for t in totals) or 'no such track'})")
            continue
        if m["kind"] == "turnout":
            want = [0.0]
        elif m["kind"] == "end bumper":
            want = [m["edge_cm"]]
        else:
            want = []
            for c in tracks:
                bl, total = c["blocks"], sum(cm[b] for b in c["blocks"])
                for i in range(len(bl) - 1):
                    if {bl[i], bl[i + 1]} == {m["facing"], *m["protects"]}:
                        d = sum(cm[b] for b in bl[:i + 1])
                        want += [d, total - d]
        if not any(near(w, m["cm_from_toward"]) for w in want):
            bad.append(f"{m['signal']}: cm_from_toward {m['cm_from_toward']} is not where its {m['kind']} stands "
                       f"({', '.join(f'{w:.1f}' for w in want) or 'no boundary of its blocks on the track'})")
    return bad


def plan_graph(plugin, graph_name: str, name: str) -> dict:
    """The plan graph of a level after the overrides' edits."""
    if str(plugin) not in sys.path:
        sys.path.insert(0, str(plugin))
    layers = importlib.import_module("schematic.layers")
    edits = importlib.import_module("schematic.edits")
    overrides = layers.load(name, str(layer_files.view(pd.DATA)), preferences=False)
    g = json.loads((pd.GRAPHS / graph_name).read_text(encoding="utf-8"))
    edits.apply_edits(g, overrides.get("edits", []))
    return g


def leg_problems(row: dict, edge: dict) -> list[str]:
    """Problems with a signal row's "leg" on its plan edge: a balloon loop (both ends at one switch) must name one of
    its two legs, since the plugin draws the mast on the half that leaves from it; any other edge names none."""
    if edge["u"] == edge["v"]:
        if row.get("leg") not in (edge["up"], edge["vp"]):
            return [f"{row['mast']}: edge {row['_edge']} is a loop at legs {edge['up']} and {edge['vp']} of one "
                    f"switch, so its leg must be one of them, not {row.get('leg')!r}"]
    elif "leg" in row:
        return [f"{row['mast']}: edge {row['_edge']} is no loop, but its row names leg {row['leg']!r}"]
    return []


def check_runs(plugin,graph_name: str, name: str, rows: list[dict]) -> list[str]:
    """Problems with the masts' schematic runs against the plan graph (with the overrides' edits)."""
    if str(plugin) not in sys.path:
        sys.path.insert(0, str(plugin))
    layers = importlib.import_module("schematic.layers")
    edits = importlib.import_module("schematic.edits")
    overrides = layers.load(name, str(layer_files.view(pd.DATA)), preferences=False)
    g = json.loads((pd.GRAPHS / graph_name).read_text(encoding="utf-8"))
    edits.apply_edits(g, overrides.get("edits", []))
    nodes, edges = g["nodes"], {e["id"]: e for e in g["edges"]}

    def lab(n):
        return (nodes[n].get("label") or "").rstrip("*") if nodes[n]["kind"] != "end" else ""
    bad = []
    for r in rows:
        e = edges.get(r["_edge"])
        if e is None:
            bad.append(f"{r['mast']}: schematic edge {r['_edge']} is not in the plan graph")
            continue
        bad += leg_problems(r, e)
        if r["_toward_node"].startswith("turn:") and r["_edge"] == r["_toward_node"].removeprefix("turn:"):
            continue            # measured from the turnback of its own folded edge (a balloon loop's APB mast)
        if r["_toward_node"] not in (e["u"], e["v"]):
            bad.append(f"{r['mast']}: node {r['_toward_node']} is not an end of edge {r['_edge']}")
            continue
        far = e["v"] if r["_toward_node"] == e["u"] else e["u"]
        toward = lab(r["_toward_node"]) or nodes[r["_toward_node"]].get("label", "")
        if r["toward"] != toward:
            bad.append(f"{r['mast']}: toward {r['toward']!r}, but node {r['_toward_node']} is switch {toward!r}")
        if [lab(r["_toward_node"]), lab(far)] != r["run"]:
            bad.append(f"{r['mast']}: edge {r['_edge']} runs {lab(r['_toward_node'])} to {lab(far)}, masts.csv says "
                       f"{r['run']}")
        if e["names"] != r["names"]:
            bad.append(f"{r['mast']}: edge {r['_edge']} carries {e['names']}, masts.csv says {r['names']}")
    return bad


def staging_facts() -> tuple[list[dict], list[dict]]:
    """(the staging masts, the staging tracks with their blocks) from the staging device map's files
    (staging_device_map.load_signal_masts and staging_chains). The masts come from the files alone; the tracks need
    the staging band, so the schematic is solved, and the solve reads signals.json (a layer file), the file this
    script writes. Its masts do not change the band's tracks, so a stale file is harmless; one that does not
    load raises SignalsError, naming the file to restore (git checkout) before running this again."""
    try:
        masts = sdm.load_signal_masts()
    except sdm.StagingMapError as exc:
        raise SignalsError(f"ERROR: staging device map: {exc}") from exc
    signals = layer_files.path("signals", pd.DATA)
    try:
        with pd.cache_on():
            band, _opts, _core = sdm.staging_band()
    except (sdm.StagingMapError, sdm.lc.BuildError, ValueError, KeyError, OSError) as exc:
        raise SignalsError(f"ERROR: cannot solve the staging band for its tracks ({type(exc).__name__}: {exc}). The "
                           f"solve reads {signals.name}, which this script writes: if that file is damaged, restore it "
                           f"(git checkout -- {pd.paths.rel(signals)}) and run this again") from exc
    try:
        return masts, sdm.staging_chains(band, sdm.load(band))
    except (sdm.StagingMapError, sdm.lc.BuildError) as exc:      # the map against the drawing
        raise SignalsError(f"ERROR: staging device map: {exc}") from exc


def main_upper_rows() -> list[dict]:
    """The main and upper masts (masts.csv's rows of the device map's levels, the owner's approved plan of
    2026-11-19) as signal rows: each
    home mast at its switch's leg on the track it faces, each APB intermediate on its loop or split track at the
    turnback, measured from the switch the track starts at (half of the track's length)."""
    import build_device_map as bdm
    from hartlib import level_masts as lm
    bands, joined, runs, corners = bdm.solve()
    found = bdm.named_tracks(bands, joined, runs)       # as build_device_map.py names them: the store, then the rule
    rr = railroad.Railroad(bdm.sources(), upto="inputs")
    sw = railroad.join_main_upper(rr.level_control_points, rr.local_switches, bdm.SWITCHES.name)
    cp_of = {s: v.cp for s, v in sw.items() if v.cp}
    planned, _corner_blocks, _split, _layer = bdm.plan_masts(bands, joined, runs, found, cp_of, corners)   # mast_plan.plan
    placed = {m["name"]: m for m in planned["home"]}
    destinations = {m["name"]: m for m in planned["virtual"]}
    by_name = {t["name"]: t for t in found}
    plan = lambda sid, band: re.sub(r"(\.\d+|(?<=\d)[xy])$", "", band["strands"][sid]["edge"])   # noqa: E731
    rows = []
    dm_levels = {r.level for r in railroad.Railroad(bdm.sources(), upto="device_map").device_map.rows}
    for r in lm.read(levels=tuple(sorted(dm_levels))):
        name = r["mast"].removeprefix("Mast ")
        heads = len(r["heads"])
        if lm.is_level_virtual(r["system_name"]):
            # a hidden destination mast at the buffer stop of the track its switch leg leaves by, measured from the
            # switch (the whole track: an end bumper), as staging's virtual masts are
            m = destinations.get(name)
            if m is None:
                raise SignalsError(f"{r['mast']}: {lm.PATH.name} names a virtual mast the rule no longer places; "
                                   "rebuild it with build_device_map.py (every level's mast rows) and build_masts.py")
            band = bands[m["band"]][1]
            d = band["nodes"][m["node"]]
            t = by_name.get(r["facing"])
            if t is None:
                raise SignalsError(f"{r['mast']}: faces {r['facing']!r}, which is no whole track of the plan")
            sid = d["ins"].get(m["leg"]) or d["outs"].get(m["leg"])
            rows.append(dict(mast=name, toward=m["switch"], run=[m["switch"], ""], edge=plan(sid, band),
                             node=m["node"], edge_cm=t["cm"], cm_from_toward=t["cm"], dir=r["dir"], heads=1,
                             leg=None, kind="virtual"))
            continue
        if r["switch"]:
            m = placed[name]
            band = bands[m["band"]][1]
            t = by_name[m["track"].rsplit(" ", 1)[0]] if m["track"] not in by_name else by_name[m["track"]]
            far = [v for (n, p), (k, v) in zip(t["legs"], reversed(t["ends"])) if (n, p) == (m["node"], m["leg"])]
            rows.append(dict(mast=name, toward=r["switch"], run=[r["switch"], far[0] if far and far[0] else ""],
                             edge=plan(m["strand"], band), node=m["node"], edge_cm=t["cm"], cm_from_toward=0.0,
                             dir=r["dir"], heads=heads,
                             leg=m["leg"] if t["loop"] else None))
            if t["loop"] and loop_leg(r["facing"]) != m["leg"]:
                raise SignalsError(f"{r['mast']}: stands on leg {m['leg']} of Switch {r['switch']}, but faces "
                                   f"{r['facing']}, the half that leaves from leg {loop_leg(r['facing'])}")
        else:
            # an APB pair at a turnback: each drawn from the switch its move heads for (the protected half's end),
            # as staging's 67 and 68 are, so the two stand apart. A balloon loop's halves both end at its switch, and
            # the plugin points a mast by the end it is measured from, so the loop's westbound mast is measured from
            # the turnback itself: the pair stands back to back at the boundary
            track = re.sub(r" [12]$", "", r["facing"])
            t = by_name[track]
            band = bands[t["band"]][1]
            node_of = {v: n for (n, _p), (k, v) in zip(t["legs"], t["ends"]) if k == "sw"}
            ends = sorted(node_of, key=bdm.natural)
            half = int(r["protects"][-1])
            label = ends[0] if t["loop"] else ends[half - 1]       # half 1 is at the lower-numbered switch
            west = r["dir"] == "west"
            other = [e for e in ends if e != label] or [label]
            node, cm = node_of[label], t["cm"] / 2
            if t["loop"] and west:
                node = next(n for sid in t["strands"] for n in (band["strands"][sid]["src"][0],
                                                                 band["strands"][sid]["dst"][0])
                            if band["nodes"][n]["kind"].startswith("turn"))
                label, cm = "", TURNBACK_CM
            rows.append(dict(mast=name, toward=label, run=[label, other[0]], edge=plan(t["strands"][0], band),
                             node=node, edge_cm=t["cm"], cm_from_toward=round(cm, 1),
                             dir=r["dir"], heads=heads,
                             leg=loop_leg(r["facing"]) if t["loop"] else None))
    return [dict(mast=x["mast"], toward=x["toward"], run=x["run"], names=[], edge_cm=x["edge_cm"],
                 cm_from_toward=x["cm_from_toward"], dir=x["dir"], kind=x.get("kind", "planned"), heads=x["heads"],
                 source=level_masts.PATH.name, _edge=x["edge"], _toward_node=x["node"],
                 **({"leg": x["leg"]} if x["leg"] else {})) for x in rows]


def loop_leg(facing: str) -> str:
    """The switch leg a balloon loop's half leaves from, by the half its block is ("Track 107 Loop 2": its half 2),
    as mast_rule.LOOP_HALF numbers them: the leg a mast standing on that half names in the signals file ("leg")."""
    import mast_rule as mr
    m = re.fullmatch(r".* Loop ([12])", facing)
    if not m:
        raise SignalsError(f"{level_masts.PATH.name}: a mast on a balloon loop faces {facing!r}, not one of its "
                           "halves (Loop 1, Loop 2)")
    return {half: leg for leg, half in mr.LOOP_HALF.items()}[int(m.group(1))]


def generate(plugin: Path, graph: str, name: str) -> dict:
    """The signals section of one sheet: staging from its masts.csv rows' plan facts, main and upper from theirs
    placed by the plan graph (main_upper_rows); SignalsError on a mast whose run is not in the plan."""
    if name == "main_upper":
        rows = main_upper_rows()
        g = plan_graph(plugin, graph, name)
        nodes, edges = g["nodes"], {e["id"]: e for e in g["edges"]}
        lab = lambda n: (nodes[n].get("label") or "").rstrip("*") if nodes[n]["kind"] != "end" else ""   # noqa: E731
        for r in rows:          # toward and run as the plan graph labels them (crossover halves 119A, a helix end "")
            e = edges.get(r["_edge"])
            if e is None or r["_toward_node"].startswith("turn:"):
                if e is not None:
                    r["names"] = e["names"]
                continue        # check_runs names an unknown edge; a turnback is no plan node
            far = e["v"] if r["_toward_node"] == e["u"] else e["u"]
            r["names"], r["toward"], r["run"] = e["names"], lab(r["_toward_node"]), [lab(r["_toward_node"]), lab(far)]
        bad = check_runs(plugin, graph, name, rows)
        if bad:
            raise SignalsError(f"{name}: {len(bad)} masts do not fit the plan graph: " + "; ".join(bad))
        return dict(schema=SCHEMA, source=level_masts.PATH.name, signals=rows, unplaced=[])
    masts, chains = staging_facts()
    rows = sdm.signal_rows(masts)
    bad = check_runs(plugin, graph, name, rows) + check_lengths(masts, chains, block_cm())
    if bad:
        raise SignalsError(f"{name}: {len(bad)} masts do not fit the plan graph: " + "; ".join(bad))
    return dict(schema=SCHEMA, source=sdm.SIGNALS_SOURCE, signals=rows, unplaced=[])


def main(argv: list[str]) -> int:
    if {"-h", "--help"} & set(argv):     # help wins over --check and over a typo beside it: it only prints
        print(__doc__ or "build_signals.py [--check]")       # python -OO strips the docstring
        return 0
    unknown = [a for a in argv if a != "--check"]
    if unknown:         # a typo must not fall through to a rebuild
        print(f"build_signals.py: unknown argument {unknown[0]!r}; usage: build_signals.py [--check] (--help for more)",
              file=sys.stderr)
        return 2
    check = "--check" in argv
    if not check:
        pd.paths.exit_if_overridden(Path(__file__).name)
    try:
        plugin = pd.plugin()
    except pd.PluginMissing as e:       # submodule missing or off its pin, and no SCHEMATIC_PLUGIN
        if not check:
            sys.exit(str(e))
        print(f"SKIPPED schematic signals check: {e}")
        return 1 if os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0
    try:
        updates = {("signals", name): generate(plugin, graph, name) for graph, name in LEVELS}
        want = layer_files.texts(updates, pd.DATA)
        old = {name: layer_files.read("signals", name, pd.DATA) for _graph, name in LEVELS}
    except layer_files.LayerFileError as exc:
        sys.exit(f"build_signals.py: {exc}")
    except SignalsError as exc:
        sys.exit(str(exc))
    target = layer_files.path("signals", pd.DATA)
    stale = 0
    for (_kind, name), new in updates.items():
        where = f"{target.name}[{name}]"
        if new == old[name]:
            print(f"{where} is current")
        elif check:
            stale = 1
            print(f"{where} is stale; run python3 tools/schematic/build_signals.py")
            lines = lambda section: layer_files.dumps(section).splitlines(True)      # noqa: E731
            sys.stdout.writelines(difflib.unified_diff(lines(old[name]), lines(new), where, "fresh", n=1))
    if target.read_text(encoding="utf-8") != want[target]:
        if check:
            if not stale:
                print(f"{target.name}'s formatting is stale; run python3 tools/schematic/build_signals.py")
            stale = 1
        else:
            target.write_text(want[target], encoding="utf-8")
            print(f"wrote {target.relative_to(pd.REPO)}")
    return stale


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
