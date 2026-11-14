# System schematic sheet (draft)

This is the sheet drawn by the `schematic-maps` plugin (model-railroad-skills) from the layer files, with no hand edits. `tools/schematic/publish_draft.py` draws it, adds the DRAFT mark and prints the PDF; `--check` says whether the published copy is current. It stays a draft until the main and upper levels have names. Last drawn 2026-11-14 (Switch 13 to 15 one cell, East Lead and West Ext lengthened, owner's request).

- Drawing: [schematic-system-draft.svg](schematic-system-draft.svg)
- Print copy, Letter landscape: [schematic-system-draft.pdf](schematic-system-draft.pdf)
- Shows staging, main and upper level as built. Track only; no custom objects or buildings.
- Staging masts come from the Layout Editor panel, drawn in the style of the NYAMR Physical Characteristics Book: a stem, an arm and one circle per head, on the right-hand side of the track for the direction the mast governs. Dashed masts at Princess are placeholders with no hardware yet. Dispatcher-only (virtual) masts are not drawn.
- Every switch number, track name and mast name is placed clear of track and of each other (label check: 0 faults).
- The copies in this folder add a red DRAFT mark in the title block. The drawing itself is unchanged.

Inputs: the layer files and `staging.signals.json` in [`jmri/layouts/hart/data/schematic/`](../../jmri/layouts/hart/data/schematic/) (plan overrides, the owner's preferences, the old hand hints kept for comparison runs, and the masts generated from `tables.xml`); the plan graphs stay beside the owner's AnyRail plan, outside the repo. Specification: [`SCHEMATIC_SPEC.md`](SCHEMATIC_SPEC.md).
