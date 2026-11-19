"""build_signals.py [--check]

Generate the schematic's layer 1 masts, jmri/layouts/hart/data/schematic/<name>.signals.json, from the staging
masts in the staging device map's form: staging_signals.csv (each mast's plan facts) and staging_masts.csv (its
blocks and slot kind), read by staging_device_map.load_signal_masts; kept by hand since the device-map switch-over
(2026-11-17), first read from the hand-drawn panel by the schematic-maps plugin's signal reader. Main and upper are dark territory (no masts) until the owner's signal plan; add a level to LEVELS
when it has masts.

Each mast's schematic run (schematic_edge, schematic_toward_node) is checked against the plan graph in inputs/ with
the plan overrides' edits: the edge must exist, run between the switches named in `run`, carry the track names in
`names`, and end at the node it heads for, whose switch is `toward`. Its lengths are checked against the staging
tracks (staging_device_map.staging_chains) and block_lengths.csv, as the signal reader measured them (a block with no length
counts as zero there too): edge_cm is the length of the track holding the mast's facing block, and cm_from_toward
is 0 at a turnout leg, the whole run at an end bumper, and at an anchor the length from one end of that track to the
boundary between the facing and protected blocks (within TOLERANCE_CM). A mast that does not fit fails the run, with
or without --check.

--check regenerates in memory and compares (exit 1 if a file is stale). When SCHEMATIC_PLUGIN is not set and the
plugin submodule is not checked out or not at its pinned commit, --check prints SKIPPED and exits 0, so a checkout
without submodules still runs check.sh; with SCHEMATIC_REQUIRED=1 (set in CI) that skip is a failure instead.
"""
import csv
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
from hartlib import railroad  # noqa: E402  block_lengths.csv, read and checked once

LEVELS = [("staging.json", "staging"), ("main.json", "main_upper")]   # plan graph in inputs/, layer file stem
SCHEMA = "schematic.signals/1"
BLOCK_LENGTHS = railroad.Sources.under().block_lengths
TOLERANCE_CM = 0.2          # the reader rounds each length to 0.1 cm
STAGGER_CM = 30.0           # a balloon loop's APB pair: the westbound mast this far back, so both are drawn


def block_cm(path=BLOCK_LENGTHS) -> dict:
    """{block: cm} from block_lengths.csv (inches, hartlib.railroad.read_block_lengths); a blank length is zero, as
    the signal reader reads it."""
    try:
        lengths = railroad.read_block_lengths(path)
    except railroad.FactsError as exc:
        sys.exit(str(exc))
    return {name: (b.inches or 0.0) * 2.54 for name, b in lengths.items()}


def check_lengths(masts: list[dict], chains: list[dict], cm: dict) -> list[str]:
    """Problems with each mast's edge_cm and cm_from_toward against the frozen tracks' block lengths."""
    bad = []
    near = lambda a, b: abs(a - b) <= TOLERANCE_CM      # noqa: E731
    for m in masts:
        tracks = [c for c in chains if m["facing"] in c["blocks"]]
        totals = [sum(cm.get(b, 0.0) for b in c["blocks"]) for c in tracks]
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
                bl, total = c["blocks"], sum(cm.get(b, 0.0) for b in c["blocks"])
                for i in range(len(bl) - 1):
                    if {bl[i], bl[i + 1]} == {m["facing"], *m["protects"]}:
                        d = sum(cm.get(b, 0.0) for b in bl[:i + 1])
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
    overrides = layers.load(name, str(pd.DATA), preferences=False)
    g = json.loads((pd.GRAPHS / graph_name).read_text(encoding="utf-8"))
    edits.apply_edits(g, overrides.get("edits", []))
    return g


def check_runs(plugin, graph_name: str, name: str, rows: list[dict]) -> list[str]:
    """Problems with the masts' schematic runs against the plan graph (with the overrides' edits)."""
    if str(plugin) not in sys.path:
        sys.path.insert(0, str(plugin))
    layers = importlib.import_module("schematic.layers")
    edits = importlib.import_module("schematic.edits")
    overrides = layers.load(name, str(pd.DATA), preferences=False)
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
    the staging band, so the schematic is solved, and the solve reads staging.signals.json (a layer file), the file
    this script writes. Its masts do not change the band's tracks, so a stale file is harmless; one that does not
    load stops here, naming the file to restore (git checkout) before running this again."""
    try:
        masts = sdm.load_signal_masts()
    except sdm.StagingMapError as exc:
        sys.exit(f"ERROR: staging device map: {exc}")
    signals = pd.DATA / "staging.signals.json"
    try:
        with pd.cache_on():
            band, _opts, _core = sdm.staging_band()
    except (sdm.StagingMapError, sdm.lc.BuildError, ValueError, KeyError, OSError) as exc:
        sys.exit(f"ERROR: cannot solve the staging band for its tracks ({type(exc).__name__}: {exc}). The solve "
                 f"reads {signals.name}, which this script writes: if that file is damaged, restore it "
                 f"(git checkout -- {pd.paths.rel(signals)}) and run this again")
    try:
        return masts, sdm.staging_chains(band, sdm.load(band))
    except (sdm.StagingMapError, sdm.lc.BuildError) as exc:      # the map against the drawing
        sys.exit(f"ERROR: staging device map: {exc}")


def main_upper_rows() -> list[dict]:
    """The main and upper masts (main_upper_masts.csv, the owner's approved plan of 2026-11-19) as signal rows: each
    home mast at its switch's leg on the track it faces, each APB intermediate on its loop or split track at the
    turnback, measured from the switch the track starts at (half of the track's length)."""
    import build_device_map as bdm
    import mast_rule as mr
    from hartlib import level_masts as lm
    bands, joined, runs, corners = bdm.solve()
    ov = json.loads(bdm.OVERRIDES.read_text(encoding="utf-8"))
    found = mr.tracks(bands, runs, joined, mr.helix_tags(bands, ov))
    mr.track_names(found)
    rr = railroad.Railroad(bdm.sources(), upto="inputs")
    sw = railroad.join_main_upper(rr.level_control_points, rr.local_switches, bdm.LOCAL.name)
    cp_of = {s: v.cp for s, v in sw.items() if v.cp}
    dxs = {bdm.base(d["label"]) for t, b, _ in bands if bdm.band_level(t) for d in b["nodes"].values()
           if d["kind"] == "dx"}
    cb = {s: bdm.xover_corners(s, corners[s]) for s in dxs}
    lists = [{r["track"] for r in csv.DictReader(open(p, newline="", encoding="utf-8"))}
             for p in (bdm.RUNNING, bdm.SPURS)]
    placed = {m["name"]: m for m in mr.masts(bands, None, found, cp_of, cb, running_extra=lists[0], spurs=lists[1],
                                             split=set(bdm.split_edges().values()))}
    by_name = {t["name"]: t for t in found}
    plan = lambda sid, band: re.sub(r"(\.\d+|(?<=\d)[xy])$", "", band["strands"][sid]["edge"])   # noqa: E731
    rows = []
    for r in lm.read():
        name = r["mast"].removeprefix("Mast ")
        heads = len(r["heads"])
        if r["switch"]:
            m = placed[name]
            band = bands[m["band"]][1]
            t = by_name[m["track"].rsplit(" ", 1)[0]] if m["track"] not in by_name else by_name[m["track"]]
            far = [v for (n, p), (k, v) in zip(t["legs"], reversed(t["ends"])) if (n, p) == (m["node"], m["leg"])]
            rows.append(dict(mast=name, toward=r["switch"], run=[r["switch"], far[0] if far and far[0] else ""],
                             edge=plan(m["strand"], band), node=m["node"], edge_cm=t["cm"], cm_from_toward=0.0,
                             dir="west" if m["letter"] == "L" else "east", heads=heads))
        else:
            # an APB pair at a turnback: each drawn from the switch its move heads for (the protected half's end),
            # as staging's 67 and 68 are, so the two stand apart; a balloon loop's halves both end at its switch, so
            # its westbound mast stands STAGGER_CM back from the boundary
            track = re.sub(r" [12]$", "", r["facing"])
            t = by_name[track]
            band = bands[t["band"]][1]
            node_of = {v: n for (n, _p), (k, v) in zip(t["legs"], t["ends"]) if k == "sw"}
            ends = sorted(node_of, key=bdm.natural)
            half = int(r["protects"][-1])
            label = ends[0] if t["loop"] else ends[half - 1]       # half 1 is at the lower-numbered switch
            west = int(re.sub(r"\D", "", name)) % 2 == 1
            cm = t["cm"] / 2 - (STAGGER_CM if t["loop"] and west else 0.0)
            other = [e for e in ends if e != label] or [label]
            rows.append(dict(mast=name, toward=label, run=[label, other[0]], edge=plan(t["strands"][0], band),
                             node=node_of[label], edge_cm=t["cm"], cm_from_toward=round(cm, 1),
                             dir="west" if west else "east", heads=heads))
    return [dict(mast=x["mast"], toward=x["toward"], run=x["run"], names=[], edge_cm=x["edge_cm"],
                 cm_from_toward=x["cm_from_toward"], dir=x["dir"], kind="planned", heads=x["heads"],
                 source="main_upper_masts.csv", _edge=x["edge"], _toward_node=x["node"]) for x in rows]


def generate(plugin, graph, name) -> str:
    """The signals file's text for one level: staging from staging_signals.csv and staging_masts.csv, main and upper
    from main_upper_masts.csv (main_upper_rows); stops on a mast whose run is not in the plan."""
    if name == "main_upper":
        rows = main_upper_rows()
        g = plan_graph(plugin, graph, name)
        nodes, edges = g["nodes"], {e["id"]: e for e in g["edges"]}
        lab = lambda n: (nodes[n].get("label") or "").rstrip("*") if nodes[n]["kind"] != "end" else ""   # noqa: E731
        for r in rows:          # toward and run as the plan graph labels them (crossover halves 119A, a helix end "")
            e = edges.get(r["_edge"])
            if e is None:
                continue        # check_runs names it
            far = e["v"] if r["_toward_node"] == e["u"] else e["u"]
            r["names"], r["toward"], r["run"] = e["names"], lab(r["_toward_node"]), [lab(r["_toward_node"]), lab(far)]
        bad = check_runs(plugin, graph, name, rows)
        if bad:
            sys.exit(f"{name}: {len(bad)} masts do not fit the plan graph: " + "; ".join(bad))
        return json.dumps(dict(schema=SCHEMA, source="main_upper_masts.csv", signals=rows, unplaced=[]), indent=1)
    masts, chains = staging_facts()
    rows = sdm.signal_rows(masts)
    bad = check_runs(plugin, graph, name, rows) + check_lengths(masts, chains, block_cm())
    if bad:
        sys.exit(f"{name}: {len(bad)} masts do not fit the plan graph: " + "; ".join(bad))
    return json.dumps(dict(schema=SCHEMA, source=sdm.SIGNALS_SOURCE, signals=rows, unplaced=[]), indent=1)


def main(argv):
    check = "--check" in argv
    if not check:
        pd.paths.exit_if_overridden(Path(__file__).name)
    try:
        plugin = pd.plugin()
    except SystemExit as e:             # submodule missing or off its pin, and no SCHEMATIC_PLUGIN
        if not check:
            raise
        print(f"SKIPPED schematic signals check: {e.code}")
        return 1 if os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0
    stale = 0
    for graph, name in LEVELS:
        target = pd.DATA / f"{name}.signals.json"
        new, old = generate(plugin, graph, name), (target.read_text() if target.exists() else "")
        if new == old:
            print(f"{target.name} is current")
        elif check:
            stale = 1
            print(f"{target.name} is stale; run python3 tools/schematic/build_signals.py")
            sys.stdout.writelines(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                                       target.name, "fresh", n=1))
        else:
            target.write_text(new)
            print(f"wrote {target.relative_to(pd.REPO)}")
    return stale


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
