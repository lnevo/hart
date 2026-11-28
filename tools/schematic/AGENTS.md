# Schematic and panel builders

Rules for work under `tools/schematic/`, on top of the root [`AGENTS.md`](../../AGENTS.md). The `schematic-builder` agent carries the same rules.

- Geometry **1:1**; new track is **Mainline → Yes** (`mainline="yes"`). Hart has no `export_options.json`.
- Do not run `fit_panel_height`, `fit_panel_canvas`, `polish_layout_geometry` or 2× draw scale unless asked.
- Check facts from the source files (the AnyRail plan, the data CSVs) before a geometry build.
- `make panels CHECK=1` before a commit; outputs stay byte-identical unless the task changes them. Approval fingerprints: [`panel-approval` skill](../../.claude/skills/panel-approval/SKILL.md).
- Code here gets `/code-review high` before merge.

## Owner rulings

- **Approved track geometry is frozen during label work.** Grid, rows, cuts and anchors stay put, and a label step must not change a track coordinate (check it). If labels do not fit, change the label approach or ask; never stretch the layout, and do not turn an observation in a hand-off into a layout change unasked. Owner, 2026-11-16, after a staging panel was spread to fit readouts: "an awful regression from the schematic ... The sizing was good, positioning of some labels was bad, but the layout did not need to be reworked this bad and I'm afraid plugin decisions were impacted by those changes."
- **Label placement is free.** Labels, readouts and station buttons go anywhere that fits cleanly: take ranked candidate spots with a hard no-overlap check and use the first clean one. Do not ask for a side or spot rule. Owner, 2026-11-15: "the placement doesn't matter so long as everything fits cleanly. sometimes the tracks are too short or are curved for your question to have a straight answer."
- **Main and upper are yours to decide.** Their names and devices are not fixed; only staging must match exactly, with names, outputs and rows byte-identical. On a conflict that touches only main or upper, pick a strategy, record it in the PR and go on (owner, 2026-11-24/25: "If a conflict impacts main/upper you should be able to decide a strategy and continue"). A main or upper fingerprint change still needs the owner's approval; list the visible change.
- **Physical distances feed, the approved schematic ends.** Measured distances (timed switch positions, block lengths, plan geometry) serve speed profiling, Operations Pro and the to-scale plans, and may influence the schematic, the Layout Editor panel and the CATS panels. The approved sheet stays the end product (owner, 2026-11-14). Update `cm_from_first` in `jmri/layouts/hart/data/schematic/*.plan_overrides.json` from `block_lengths.csv` only with a regenerate-and-compare; if the look moves, restore it through the layer 3 preferences, not stale distances. Do not commit a redrawn schematic the owner has not seen.
- **DCC name versus address.** A DCC twin's name ("DCC Switch 101", `MTTnnn`) follows the switch number; its address is the `dcc` column (staging Switch 1-39 use 100-119, main 120-135, upper 136-158, assigned in order by `build_device_map.py`). So "DCC Switch 101" has address 120 (`MTT120`), and address 101 is staging Switch 3 (`MTT101`). Always give both ("main Switch 101's DCC twin, address 120 (MTT120)"); never write "DCC 101" for a switch number. Owner, 2026-11-20: "be careful when using DCC address with the switch name".
- AnyRail readers and exports: [`tools/anyrail/README.md`](../anyrail/README.md).
