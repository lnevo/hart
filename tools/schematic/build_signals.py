"""build_signals.py [--check]

Generate the schematic's layer 1 masts, jmri/layouts/hart/data/schematic/<name>.signals.json, from the frozen mast
facts in jmri/layouts/hart/data/schematic/staging_le/masts.csv (le_inputs.py; LE cut-over Phase 3b, 2026-11-15).
That file is the one source of the staging masts: the Layout Editor build (build_layout_le.py) places them from it
too. It was read once from the hand-drawn panel by the schematic-maps plugin's signal reader
(build_layout_le.py --freeze); edit it there, not in a panel. Main and upper are dark territory (no masts) until the
owner's signal plan; add a level to LEVELS when it has masts.

Each mast's schematic run (schematic_edge, schematic_toward_node) is checked against the plan graph in inputs/ with
the plan overrides' edits: the edge must exist, run between the switches named in `run`, carry the track names in
`names`, and end at the node it heads for. A mast that does not fit fails the run, with or without --check.

--check regenerates in memory and compares (exit 1 if a file is stale). When SCHEMATIC_PLUGIN is not set and the
plugin submodule is not checked out or not at its pinned commit, --check prints SKIPPED and exits 0, so a checkout
without submodules still runs check.sh; with SCHEMATIC_REQUIRED=1 (set in CI) that skip is a failure instead.
"""
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
        if [lab(r["_toward_node"]), lab(far)] != r["run"]:
            bad.append(f"{r['mast']}: edge {r['_edge']} runs {lab(r['_toward_node'])} to {lab(far)}, masts.csv says "
                       f"{r['run']}")
        if e["names"] != r["names"]:
            bad.append(f"{r['mast']}: edge {r['_edge']} carries {e['names']}, masts.csv says {r['names']}")
    return bad


def generate(plugin, graph, name) -> str:
    """The signals file's text for one level, from masts.csv; stops on a mast whose run is not in the plan."""
    try:
        masts = le_inputs.load_masts()
    except le_inputs.InputsError as exc:
        sys.exit(f"ERROR: {exc}")
    rows = le_inputs.signal_rows(masts)
    bad = check_runs(plugin, graph, name, rows)
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
