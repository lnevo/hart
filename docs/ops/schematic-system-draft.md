# System schematic sheet

This is the sheet drawn by the `schematic-maps` plugin (model-railroad-skills) from the layer files, with no hand edits. `tools/schematic/publish_draft.py` draws it and prints the PDF; `--check` says whether the published copy is current. The DRAFT mark came off when the owner approved the helix-join release (2026-11-17); the files keep their `-draft` names so links stay. Last drawn 2026-11-14 (Switch 13 to 15 one cell, East Lead and West Ext lengthened, owner's request).

- Drawing: [schematic-system-draft.svg](schematic-system-draft.svg)
- Print copy, Letter landscape: [schematic-system-draft.pdf](schematic-system-draft.pdf)
- Shows staging, main and upper level as built. Track only; no custom objects or buildings.
- Staging masts come from the Layout Editor panel, drawn in the style of the NYAMR Physical Characteristics Book: a stem, an arm and one circle per head, on the right-hand side of the track for the direction the mast governs. Dashed masts at Princess are placeholders with no hardware yet. Dispatcher-only (virtual) masts are not drawn.
- Every switch number, track name and mast name is placed clear of track and of each other (label check: 0 faults).

Inputs: the layer files and `staging.signals.json` in [`jmri/layouts/hart/data/schematic/`](../../jmri/layouts/hart/data/schematic/) (plan overrides, the owner's preferences, and the masts generated from `tables.xml`), and the plan graphs in its `inputs/` folder. Specification: [`SCHEMATIC_SPEC.md`](SCHEMATIC_SPEC.md). `--preview DIR` draws the SVG and PDF into DIR for the owner to look at, without touching this folder or the title block's date and revision.

Solved-sheet cache: solving the sheet takes 30 to 60 s, so publishing and the LE, CATS and device-map builds keep one solve in `~/.cache/hart/schematic` (the plugin's `SCHEMATIC_CACHE`, private to the user) and read it back while the plugin code the solve runs, the graphs and the layer files are unchanged. A change to the title block's date, revision or sheet alone, or to the plugin's Layout Editor or CATS code, keeps the solve. The Layout Editor build keeps its panels there too, so a run whose inputs are unchanged draws nothing again. `make panels` rebuilds everything drawn from the schematic in order (`make panels CHECK=1` checks it); about 12 s when nothing changed. `SCHEMATIC_CACHE= python3 tools/schematic/publish_draft.py` solves without it; deleting the folder clears it. A test that patches plugin code before a solve sets `SCHEMATIC_CACHE` to empty.

## Plan inputs

`jmri/layouts/hart/data/schematic/inputs/` holds the track taken from the owner's AnyRail plan 5.3b: `staging.json` and `main.json` (track graphs) and `parts.json` (361 track parts, Peco code 83 and one Walthers part). Track exports of the plan may be public; its custom objects and buildings, the `.any` file and its JMRI XML export may not, so those stay in `~/Documents/Layout/` and are never committed.

Regenerate after a new AnyRail export, from the worktree root with the plugin submodule checked out (`P=external/model-railroad-skills/plugins/schematic-maps/bin/schematic`, `X` the plan's XML export, `I=jmri/layouts/hart/data/schematic/inputs`):

    $P plan "$X" $I/staging.json --section +Staging --parts $I/parts.json --z-range -100 -5
    $P plan "$X" $I/main.json --section Staging --parts $I/parts.json --z-range -5 100

Checked 2026-11-14: both reproduce the committed graphs except for a `notes` list the plugin adds (what it joined and matched); delete that key before committing. `parts.json` comes from the `.any` file through the AnyRail reader in `tools/anyrail/prototype/` (`parse1.py`, then `parse2.py`), run in a scratch folder outside the repo. Keep only each part's `name` and its end points' `x`, `y` and `z` (the plugin uses nothing else, and the list order gives the `T` labels, so drop no parts), and drop any end point whose `sys` differs from its part's, which is a misread of the next record. In plan 5.3b that is part 0, an SL-8351 whose third end point is unreadable. It never matched a junction, because the misread point pulled its centre far off. With two end points it is left out of the matching, and the graphs are the same either way. The test allows part 0 only, so a new short turnout is caught. `tools/audit/tests/test_publish_draft.py` fails on any other field:

    python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); json.dump([{"name": p["name"], "eps": [{k: e[k] for k in "xyz"} for e in p["eps"] if e["sys"] == p["sys"]]} for p in d], open(sys.argv[2], "w"), separators=(",", ":"))' raw_parts.json $I/parts.json

The staging masts, `staging.signals.json`, come from the staging device map's `staging_signals.csv` and `staging_masts.csv` in `jmri/layouts/hart/data/schematic/` (kept by hand since the device-map switch-over, 2026-11-17; the generated Layout Editor panel places its masts from the same files): `python3 tools/schematic/build_signals.py` regenerates them, checking each run against the plan graph, and `--check` (in `tools/check.sh`) fails when they are stale.
