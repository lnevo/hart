# Generated, then the owner's, then frozen wiring: hand-off (2026-11-24)

Status: active

The plan for [ADR-033](../decisions/ADR-033-generated-then-owner.md): one flow for every level, where the generator names every device, the owner's values always win, and frozen wiring stays fixed. It takes in the parked [builder merge](builder-merge.md) (one bean, row and mast process), which no longer waits for main and upper wiring. About 11 PRs and 10 to 12 agent-days.

## What the generator does today (checked 2026-11-24 at 33abbf05; the pipeline review that closed after it changed `make panels` steps, not these)

- **Geometry and names are already one process.** Every level's blocks come from the solved schematic (`inputs/staging.json`, `inputs/main.json`, from plan 5.3c) through `block_layer.tracks` and `name_tracks`: the plan's name, else the end-switch rule. Staging's track names come from the owner's `name` edit in `plan_overrides.json`, keyed by end switches (`['17', '29', 'S-1']`); main and upper have no name edit, so theirs come from the rule. Masts are planned by one `mast_plan.plan` for every level.
- **Rows are not.** `device_map_staging.staging_rows` builds each staging block and detector on its owner row and stops on a drawn block with none ("no row in devices_field.csv"). Staging's turnout, alias and feedback rows come from `wiring.csv` and the owner rows (`staging_wired_rows`); main and upper's from `build_device_map.switch_rows`, which proposes pins and keeps frozen ones (`frozen_wires`).
- **Beans are not.** Staging's come from `tables_build.master_beans` (`GENERATED_LEVELS = ("1",)`); main and upper's from `le_tables.add_level_*` while the panel is drawn, with fixed `IT:HART:C3:<n>` names. That is why a physical swap stops `make panels`.
- **Rows are keyed by name.** `KEY = ("level", "layer", "user_name")` in `hartlib/devices.py`.
- **An ID is half there.** Every block row carries `trial_name`, a key from its end switches and legs (`Track 1B-3A 1/2`, `OS 7 A-13C`); switch numbers are owner values (the `relabel` edits). Turnouts, detectors, heads and masts carry no such key.

So step 4 below (staging generated like main and upper) is a medium change, not a rewrite: the geometry is already shared, and the work is in the rows and beans.

## Owner decisions before building

| # | Question | Answer |
|---|---|---|
| 1 | What is a device's ID? | **Open.** Proposed: the plan geometry (switch number and half; a block by the objects at its ends; a detector by its block; a mast by the switch, leg and direction it protects), with the tracks at a switch's legs used only on a re-import, to match a replaced switch part to its old ID. The owner asked whether the objects at each end should be part of the ID itself (2026-11-24). |
| 2 | Where do the owner's track names live? | **Open.** Proposed: stay in `plan_overrides.json`'s `name` edit (names on the drawing, read by the plugin, keyed by end switches); `devices_field.csv` keeps the owner's JMRI-side values. |
| 3 | A new AnyRail file drops an ID that has owner values | **Decided (owner, 2026-11-24): stop and list it;** the owner moves the values to the new ID or drops them. |
| 4 | What gets named, and the order | **Decided (owner, 2026-11-24):** nothing is named before the owner is ready. The control points in `interlockings.csv` are owner values and stay; every other main and upper name stays generated or blank. This plan needs no new names; the main and upper station maps wait until the owner names those stations. |

## Staged plan

Each PR leaves `tables.xml`, the desks, the Layout Editor panel and the approved fingerprints byte-identical unless it lists a diff, and passes `make panels CHECK=1`, `./tools/check.sh` (`FULL=1` through `make remote` for bean PRs) and, when beans change, `make panelpro-test`. Code PRs get `/code-review medium`.

| # | Step | Size | Notes |
|---|---|---|---|
| 1 | Tests first | 1 day | Builder merge step 1: golden tests of every main and upper bean `le_tables` makes, unit tests of `master_beans` per assignment, `build_masts.generate` on staging, and the device-master merge |
| 2 | `id` column | 0.5 day | The builders write an ID on every row (decision 1); `check_rows` holds it unique per level. Only `devices_generated.csv` changes |
| 3 | Owner file keyed by ID | 1 day | `devices_field.csv` rekeyed on `(level, id)`; `user_name` becomes an owner cell. The build prints new and gone IDs against the last generated file and stops as decision 3 says |
| 4 | Staging generated like main and upper | 1.5 days | `staging_rows` and `staging_wired_rows` go through the main and upper functions; a staging device with no owner row gets generated values instead of stopping; `FIELD_LEVEL` goes. Staging's owner values still win, so outputs stay the same |
| 5 | Block names into the rows | 0.5 day | Builder merge step 2 (`block_numbering.csv` stays the source of main and upper numbers, owner 2026-11-23) |
| 6 | `start` column and comment data | 0.5 day | Builder merge step 3 |
| 7 | Bean shapes by column | 1 day | Builder merge step 4 |
| 8 | Every level through `master_beans` | 1 day | Builder merge step 5: deletes `add_level_*` and the `IT:HART:C3` patterns in `cats_panel.py` and `le_tables.py`, so the bean name is always the row's `jmri_name`. Listed comment diff (owner's 2026-11-23 answer), `make panelpro-test`, deploy |
| 9 | One mast step | 1 to 1.5 days | Builder merge step 6; any main or upper mast change goes to panel approval |
| 10 | One reader | 1 to 1.5 days | Builder merge step 7, with the `switches.csv` readers moved onto `hartlib.railroad` |
| 11 | Level tests to column tests, and a swap test | 1 day | Builder merge step 8, then in the sandbox swap one main or upper turnout to a physical name by its owner row alone: `make panels`, `make panelpro-test`, then revert. ADR-033 goes to Accepted |

## How to run this

- Wait for the owner's answers to decisions 1 and 2; record them in the table above and in ADR-033.
- One PR per step, in order, each in its own `make wt` worktree. Steps 2 to 4 are `hartlib` and `tools/schematic/` work (`schematic-builder`); steps 8 and 11 need the Mac's PanelPro and stay in the main session.
- Steps that add or move a pipeline step update `docs/pipeline-map/pipeline_map.json`.
- Docs to update as steps land: `tools/hartlib/README.md` (`hartlib.devices`), `wiki/pipelines/schematic-panels.md`, `jmri/layouts/hart/data/devices.columns.csv`, ADR-027, 028 and 029 (amended by 033).

## Risks

- `build_device_map.py` (833 lines), `device_map_staging.py` (448) and `tables_build.py` (963) are partly untested; step 1 is not optional.
- Step 3 changes the key every writer and test uses (`hartlib.devices.KEY`); run the full suite through `make remote`.
- It shares readers with the station maps (`stations.csv`, `sheets.csv`); do not run the two at once.
