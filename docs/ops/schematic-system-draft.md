# System schematic sheet (draft)

This is the sheet drawn by the `schematic-maps` plugin (model-railroad-skills) from the layer files, with no hand edits. `tools/schematic/publish_draft.py` draws it, adds the DRAFT mark and prints the PDF; `--check` says whether the published copy is current. It stays a draft until the main and upper levels have names. Last drawn 2026-11-14 (Switch 13 to 15 one cell, East Lead and West Ext lengthened, owner's request).

- Drawing: [schematic-system-draft.svg](schematic-system-draft.svg)
- Print copy, Letter landscape: [schematic-system-draft.pdf](schematic-system-draft.pdf)
- Shows staging, main and upper level as built. Track only; no custom objects or buildings.
- Staging masts come from the Layout Editor panel, drawn in the style of the NYAMR Physical Characteristics Book: a stem, an arm and one circle per head, on the right-hand side of the track for the direction the mast governs. Dashed masts at Princess are placeholders with no hardware yet. Dispatcher-only (virtual) masts are not drawn.
- Every switch number, track name and mast name is placed clear of track and of each other (label check: 0 faults).
- The copies in this folder add a red DRAFT mark in the title block. The drawing itself is unchanged.

Inputs: the layer files and `staging.signals.json` in [`jmri/layouts/hart/data/schematic/`](../../jmri/layouts/hart/data/schematic/) (plan overrides, the owner's preferences, the old hand hints kept for comparison runs, and the masts generated from `tables.xml`), and the plan graphs in its `inputs/` folder. Specification: [`SCHEMATIC_SPEC.md`](SCHEMATIC_SPEC.md). `--preview DIR` draws the SVG and PDF into DIR for the owner to look at, without touching this folder or the title block's date and revision.

## Plan inputs

`jmri/layouts/hart/data/schematic/inputs/` holds the track taken from the owner's AnyRail plan 5.3b: `staging.json` and `main.json` (track graphs) and `parts.json` (361 track parts, Peco code 83 and one Walthers part). Track exports of the plan may be public; its custom objects and buildings, the `.any` file and its JMRI XML export may not, so those stay in `~/Documents/Layout/` and are never committed.

Regenerate after a new AnyRail export, from the worktree root with the plugin submodule checked out (`P=external/model-railroad-skills/plugins/schematic-maps/bin/schematic`, `X` the plan's XML export, `I=jmri/layouts/hart/data/schematic/inputs`):

    $P plan "$X" $I/staging.json --section +Staging --parts $I/parts.json --z-range -100 -5
    $P plan "$X" $I/main.json --section Staging --parts $I/parts.json --z-range -5 100

Checked 2026-11-14: both reproduce the committed graphs (the plugin adds a `notes` list of what it did). `parts.json` comes from the `.any` file through the AnyRail reader in `tools/anyrail/prototype/` (`parse1.py`, then `parse2.py`), run in a scratch folder outside the repo; check it still holds track parts only before committing a new one.

The staging masts, `staging.signals.json`, come from `tables.xml`, `switches.csv` and `block_lengths.csv`: `python3 tools/schematic/build_signals.py` regenerates them and `--check` (in `tools/check.sh`) fails when they are stale.
