# System schematic sheet

This is the sheet drawn by the `schematic-maps` plugin (model-railroad-skills) from the layer files, with no hand edits. `tools/schematic/publish_draft.py` draws it and prints the PDF; `--check` says whether the published copy is current. The DRAFT mark came off when the owner approved the helix-join release (2026-11-17); the files keep their `-draft` names so links stay. Last drawn 2026-11-14 (Switch 13 to 15 one cell, East Lead and West Ext lengthened, owner's request).

Status: current. This is the source page of the published system schematic sheet; the `-draft` file names stay so links keep working.

- Drawing: [schematic-system-draft.svg](schematic-system-draft.svg)
- Print copy, Letter landscape: [schematic-system-draft.pdf](schematic-system-draft.pdf)
- Shows staging, main and upper level as built. Track only; no custom objects or buildings.
- Staging masts come from the Layout Editor panel, drawn in the style of the NYAMR Physical Characteristics Book: a stem, an arm and one circle per head, on the right-hand side of the track for the direction the mast governs. Dashed masts at Princess are placeholders with no hardware yet. Dispatcher-only (virtual) masts are not drawn.
- Every switch number, track name and mast name is placed clear of track and of each other (label check: 0 faults).

Inputs: the layer files `plan_overrides.json`, `preferences.json` and `signals.json` (one file per kind, a section per sheet: `staging`, `main_upper`; read and written through `hartlib.layer_files`) in [`jmri/layouts/hart/data/schematic/`](../../jmri/layouts/hart/data/schematic/) (plan overrides, the owner's preferences, and the masts generated from `tables.xml`), and the plan graphs in its `inputs/` folder. Specification: [`SCHEMATIC_SPEC.md`](SCHEMATIC_SPEC.md). `--preview DIR` draws the SVG and PDF into DIR for the owner to look at, without touching this folder or the title block's date and revision.

Solved-sheet cache: solving the sheet takes 30 to 60 s, so publishing and the LE, CATS and device-map builds keep one solve in `~/.cache/hart/schematic` (the plugin's `SCHEMATIC_CACHE`, private to the user) and read it back while the plugin code the solve runs, the graphs and the layer files are unchanged. A change to the title block's date, revision or sheet alone, or to the plugin's Layout Editor or CATS code, keeps the solve. The Layout Editor build keeps its panels there too, so a run whose inputs are unchanged draws nothing again. `make panels` rebuilds everything drawn from the schematic in order (`make panels CHECK=1` checks it); about 12 s when nothing changed. `SCHEMATIC_CACHE= python3 tools/schematic/publish_draft.py` solves without it; deleting the folder clears it. A test that patches plugin code before a solve sets `SCHEMATIC_CACHE` to empty.

## Plan inputs

`jmri/layouts/hart/data/schematic/inputs/` holds the track taken from the owner's AnyRail plan 5.3c (since Phase 2, 2026-11-19; 5.3b before): `staging.json` and `main.json` (track graphs) and `parts.json` (390 track parts; any maker's). Track exports of the plan may be public; its custom objects and buildings, the `.any` file and its JMRI XML export may not, so those stay in `~/Documents/Layout/` and are never committed.

Regenerate after a new AnyRail export, from the worktree root with the plugin submodule checked out (`P=external/model-railroad-skills/plugins/schematic-maps/bin/schematic`, `A` the plan's `.any` file, `X` its XML export, `I=jmri/layouts/hart/data/schematic/inputs`):

    python3 tools/anyrail/anyplan.py "$A" --parts $I/parts.json
    $P plan "$X" $I/staging.json --section +Staging --parts $I/parts.json --z-range -100 -5
    $P plan "$X" $I/main.json --section Staging --parts $I/parts.json --z-range -5 100
    python3 -c 'import json,sys; ds={f: json.load(open(f)) for f in sys.argv[1:]}; [open(f,"w").write(json.dumps({k: v for k, v in d.items() if k != "notes"}, indent=1)) for f, d in ds.items()]' $I/staging.json $I/main.json
    python3 tools/anyrail/anyplan.py "$A" --cut -5 --stubs $I/staging.json $I/main.json

The plugin drops the notes list it adds (what it joined and matched). The section filters leave out each helix run, which joins a staging switch to a main-level one; the last command gives each graph its share of every run that climbs through -5 cm, as a track to an end marked `cut` (lengths from the `.any` file, each flex piece's share by its grade), so the helix count needs no `helix_length_in` (schematic-maps 0.1.45). A rerun refuses a graph that already has its stubs. The T labels are part numbers in `parts.json` order, so a new plan renumbers them: re-key the layer files by position (see [`archive/wiki/projects/anyrail-5-3c-handoff.md`](../../archive/wiki/projects/anyrail-5-3c-handoff.md)). The three-way's halves (51, 50) are the only junctions no part names.

The staging masts, `signals.json`'s `staging` section, come from the staging rows of `masts.csv` in `jmri/layouts/hart/data/schematic/` (every level's masts, written by `build_masts.py`; the generated Layout Editor panel places its masts from the same file): `python3 tools/schematic/build_signals.py` regenerates them, checking each run against the plan graph, and `--check` (in `tools/check.sh`) fails when they are stale.
