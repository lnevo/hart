"""build_signals.py [--check]

Generate the schematic's layer 1 masts, jmri/layouts/hart/data/schematic/<name>.signals.json, from the Layout
Editor panel in tables.xml with the schematic-maps plugin's `signals` command, the plan graph in inputs/, the
switch numbers in switches.csv and the run lengths in block_lengths.csv. Only staging has masts on the panel;
add a level to LEVELS when its masts are placed.

--check regenerates into a temporary folder and compares (exit 1 if a file is stale). Masts the plugin could
not place fail the run, with or without --check. When SCHEMATIC_PLUGIN is not set and the plugin submodule
is not checked out or not at its pinned commit, --check prints SKIPPED and exits 0, so a checkout without submodules still runs
check.sh; with SCHEMATIC_REQUIRED=1 (set in CI) that skip is a failure instead.
"""
import json
import os
import difflib
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA, GRAPHS, hartlib paths and the pinned plugin

LEVELS = [("staging.json", "staging")]     # plan graph in inputs/, layer file stem
TABLES = pd.paths.TABLES_XML
FACTS = pd.paths.LAYOUT_DATA


def generate(plugin, graph, name, out):
    run = subprocess.run([str(plugin / "bin/schematic"), "signals", str(TABLES), str(pd.GRAPHS / graph), name,
                          str(out), "--data", str(pd.DATA), "--numbers", str(FACTS / "switches.csv"),
                          "--lengths", str(FACTS / "block_lengths.csv")], capture_output=True, text=True)
    print(run.stdout + run.stderr, end="")
    if run.returncode:
        sys.exit(run.returncode)
    unplaced = json.loads(out.read_text()).get("unplaced")
    if unplaced is None:
        sys.exit(f"{out.name} has no unplaced list; has the plugin's output changed?")
    if unplaced:
        sys.exit(f"{name}: {len(unplaced)} masts not placed (listed above); fix the panel or the layer files")


def main(argv):
    check = "--check" in argv
    try:
        plugin = pd.plugin()
    except SystemExit as e:             # submodule missing or off its pin, and no SCHEMATIC_PLUGIN
        if not check:
            raise
        print(f"SKIPPED schematic signals check: {e.code}")
        return 1 if os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0
    stale = 0
    with tempfile.TemporaryDirectory() as tmp:
        for graph, name in LEVELS:
            target = pd.DATA / f"{name}.signals.json"
            fresh = Path(tmp) / target.name
            generate(plugin, graph, name, fresh)
            new, old = fresh.read_text(), (target.read_text() if target.exists() else "")
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
