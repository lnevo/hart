"""build_signals.py [--check]

Generate the schematic's layer 1 masts, jmri/layouts/hart/data/schematic/<name>.signals.json, from the frozen mast
facts in jmri/layouts/hart/data/schematic/staging_le/masts.csv (le_inputs.py; LE cut-over Phase 3b, 2026-11-15).
That file is the one source of the staging masts: the Layout Editor build (build_layout_le.py) places them from it
too. It was read once from the hand-drawn panel by the schematic-maps plugin's signal reader
(build_layout_le.py --freeze); edit it there, not in a panel. Main and upper are dark territory (no masts) until the
owner's signal plan; add a level to LEVELS when it has masts.

Each mast's schematic run (schematic_edge, schematic_toward_node) is checked against the plan graph in inputs/ with
the plan overrides' edits: the edge must exist, run between the switches named in `run`, carry the track names in
`names`, and end at the node it heads for, whose switch is `toward`. Its lengths are checked against the frozen
tracks (staging_le/tracks.csv) and block_lengths.csv, as the signal reader measured them (a block with no length
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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import le_inputs  # noqa: E402  the frozen staging facts
import publish_draft as pd  # noqa: E402  DATA, GRAPHS, hartlib paths and the pinned plugin

LEVELS = [("staging.json", "staging")]     # plan graph in inputs/, layer file stem
SCHEMA = "schematic.signals/1"
BLOCK_LENGTHS = pd.paths.LAYOUT_DATA / "block_lengths.csv"
TOLERANCE_CM = 0.2          # the reader rounds each length to 0.1 cm


def block_cm(path=BLOCK_LENGTHS) -> dict:
    """{block: cm} from block_lengths.csv (inches); a blank length is zero, as the signal reader reads it."""
    out = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for k, r in enumerate(csv.DictReader(fh), 2):
            try:
                out[r["user_name"]] = float(r["inches"] or 0) * 2.54
            except (KeyError, ValueError):
                sys.exit(f"{path.name} line {k}: no user_name or inches {r.get('inches')!r} is not a number")
    return out


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


def generate(plugin, graph, name) -> str:
    """The signals file's text for one level, from masts.csv; stops on a mast whose run is not in the plan."""
    try:
        inputs = le_inputs.load()
    except le_inputs.InputsError as exc:
        sys.exit(f"ERROR: {exc}")
    rows = le_inputs.signal_rows(inputs.masts)
    bad = check_runs(plugin, graph, name, rows) + check_lengths(inputs.masts, inputs.chains, block_cm())
    if bad:
        sys.exit(f"{name}: {len(bad)} masts do not fit the plan graph: " + "; ".join(bad))
    return json.dumps(dict(schema=SCHEMA, source=le_inputs.SIGNALS_SOURCE, signals=rows, unplaced=[]), indent=1)


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
