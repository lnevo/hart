"""build_cats_panel.py [--check]

Generate a CATS Designer panel for the main and upper levels from the schematic grid, with the schematic-maps
plugin's `cats` command, into cats/panels/generated/HART_Main_Upper.xml. It sits beside the live desks (ADR-023):
cats/panels/HART_CTC.xml, HART_ABS.xml and HART_Digicon.xml are not touched, and the deploy installs only its
LIVE_PANELS list, so this file is not deployed. tools/check.sh validates it with cats/scripts/validate_cats_panel.py.

The plugin draws every input (staging carries the milepost origin), then keeps the Main and Upper bands; staging
stays on the live desk. Main and upper have no JMRI objects yet, so the panel has track, switch points (normal =
the band's leg B), blocks and labels, and no sensor, turnout or signal bindings. The owner opens it in the Designer.
Inputs and plugin are the same as tools/schematic/publish_draft.py (SCHEMATIC_PLUGIN for other plugin code).

--check regenerates into a temporary folder and compares (exit 1 if the file is stale). When SCHEMATIC_PLUGIN is
not set and the plugin submodule is not checked out or not at its pinned commit, --check prints SKIPPED and exits 0
(a failure with SCHEMATIC_REQUIRED=1).
"""
import difflib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA, GRAPHS, INPUTS, hartlib paths and the pinned plugin

BANDS = ["Main", "Upper"]          # band titles start with these; staging stays on the live desk
OUT = pd.REPO / "cats/panels/generated/HART_Main_Upper.xml"


def generate(plugin, out):
    run = subprocess.run([str(plugin / "bin/schematic"), "cats", str(out), "--data", str(pd.DATA),
                          *(f"{pd.GRAPHS}/{g}:{n}" for g, n in pd.INPUTS),
                          *(a for b in BANDS for a in ("--band", b))],
                         capture_output=True, text=True)
    print(run.stdout + run.stderr, end="")
    if run.returncode:
        sys.exit(run.returncode)


def main(argv):
    check = "--check" in argv
    try:
        plugin = pd.plugin()
    except SystemExit as e:
        if not check:
            raise
        print(f"SKIPPED CATS panel check: {e.code}")
        return 1 if os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp) / OUT.name
        generate(plugin, fresh)
        new, old = fresh.read_text(encoding="utf-8"), (OUT.read_text(encoding="utf-8") if OUT.exists() else "")
        if new == old:
            print(f"{OUT.relative_to(pd.REPO)} is current")
        elif check:
            print(f"{OUT.relative_to(pd.REPO)} is stale; run python3 tools/schematic/build_cats_panel.py")
            sys.stdout.writelines(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                                       OUT.name, "fresh", n=1))
            return 1
        else:
            OUT.parent.mkdir(parents=True, exist_ok=True)
            OUT.write_text(new, encoding="utf-8")
            print(f"wrote {OUT.relative_to(pd.REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
