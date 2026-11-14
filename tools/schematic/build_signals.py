"""build_signals.py [--check]

Generate the schematic's layer 1 masts, jmri/layouts/hart/data/schematic/<name>.signals.json, from the Layout
Editor panel in tables.xml with the schematic-maps plugin's `signals` command, the plan graph in inputs/, the
switch numbers in switches.csv and the run lengths in block_lengths.csv. Only staging has masts on the panel;
add a level to LEVELS when its masts are placed.

--check regenerates into a temporary folder and compares (exit 1 if a file is stale). When the plugin
submodule is not checked out it says so and exits 0, so a checkout without submodules still runs check.sh.
"""
import difflib
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  REPO, DATA, GRAPHS and the pinned plugin

LEVELS = [("staging.json", "staging")]     # plan graph in inputs/, layer file stem
TABLES = pd.REPO / "jmri/layouts/hart/output/tables.xml"
FACTS = pd.REPO / "jmri/layouts/hart/data"


def generate(graph, name, out):
    run = subprocess.run([str(pd.plugin() / "bin/schematic"), "signals", str(TABLES), str(pd.GRAPHS / graph), name,
                          str(out), "--data", str(pd.DATA), "--numbers", str(FACTS / "switches.csv"),
                          "--lengths", str(FACTS / "block_lengths.csv")], capture_output=True, text=True)
    print(run.stdout + run.stderr, end="")
    if run.returncode:
        sys.exit(run.returncode)


def main(argv):
    check = "--check" in argv
    if check and not (pd.REPO / "external/model-railroad-skills/plugins/schematic-maps/bin/schematic").exists():
        print("schematic signals check skipped: plugin submodule external/model-railroad-skills not checked out")
        return 0
    stale = 0
    with tempfile.TemporaryDirectory() as tmp:
        for graph, name in LEVELS:
            target = pd.DATA / f"{name}.signals.json"
            fresh = Path(tmp) / target.name
            generate(graph, name, fresh)
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
