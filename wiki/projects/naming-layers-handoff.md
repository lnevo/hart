# Generated, then the owner's, then frozen wiring: hand-off (2026-11-24)

Status: active

The plan for [ADR-033](../decisions/ADR-033-generated-then-owner.md): one flow for every level, where the generator names every device, the owner's values always win, and frozen wiring stays fixed. It takes in the parked [builder merge](builder-merge.md) (one bean, row and mast process), which no longer waits for main and upper wiring, and puts every name and every read of layout data behind `hartlib`. About 14 PRs and 13 to 16 agent-days.

## What the generator does today (checked 2026-11-24 at 33abbf05; the pipeline review that closed after it changed `make panels` steps, not these)

- **Geometry and names are already one process.** Every level's blocks come from the solved schematic (`inputs/staging.json`, `inputs/main.json`, from plan 5.3c) through `block_layer.tracks` and `name_tracks`: the plan's name, else the end-switch rule. Staging's track names come from the owner's `name` edit in `plan_overrides.json`, keyed by end switches (`['17', '29', 'S-1']`); main and upper have no name edit, so theirs come from the rule. Masts are planned by one `mast_plan.plan` for every level.
- **Rows are not.** `device_map_staging.staging_rows` builds each staging block and detector on its owner row and stops on a drawn block with none ("no row in devices_field.csv"). Staging's turnout, alias and feedback rows come from `wiring.csv` and the owner rows (`staging_wired_rows`); main and upper's from `build_device_map.switch_rows`, which proposes pins and keeps frozen ones (`frozen_wires`).
- **Beans are not.** Staging's come from `tables_build.master_beans` (`GENERATED_LEVELS = ("1",)`); main and upper's from `le_tables.add_level_*` while the panel is drawn, with fixed `IT:HART:C3:<n>` names. That is why a physical swap stops `make panels`.
- **Rows are keyed by name.** `KEY = ("level", "layer", "user_name")` in `hartlib/devices.py`.
- **An ID is half there.** Every block row carries `trial_name`, a key from its end switches and legs (`Track 1B-3A 1/2`, `OS 7 A-13C`); switch numbers are owner values (the `relabel` edits). Turnouts, detectors, heads and masts carry no such key.

- **Track names go two ways.** Staging: the owner's `name` edit, then the plugin draws it, then `block_layer` reads it off the drawing into the device master (the drawing is the source). Main and upper: the rule, then the device master, then `cats_panel.py` and `le_names.py` write the names back onto the drawing (the device master is the source).
- **`plan_overrides.json` mixes three kinds of data:** switch numbers for AnyRail parts (`relabel`), the owner's names (staging's `name` and `end` edits, `left_end`), and railroad facts and drawing settings (level titles, milepost origin, helix, `levels`, scale, mast prefix).
- **Files keyed by a user name:** `block_lengths.csv`, `block_numbering.csv`, `wiring.csv`, `mast_cells.csv`, and the `facing` and `protects` columns of `masts.csv`; `block_overrides.csv` and `main_lines.csv` key partly by names. A rename breaks each.
- **Readers outside `hartlib`:** `block_overrides.csv`, `main_lines.csv` and `mast_cells.csv` have no `hartlib` reader; `jmri/layouts/hart/scripts/layout_facts.py` is a second, staging-only loader of `switches.csv`, `stations.csv` and `mast_cells.csv`; `tools/wiring/write_inventory.py`, `jmri/scripts/check_hart_phase02.py` and the speed-matching `analyze.py` read `switches.csv` themselves. Several builders read `plan_overrides.json` sections directly through `layer_files.read`. Nothing stops a new script doing the same.
- **Signals are devices:** 98 masts and 112 heads are device-master rows, written by `build_masts.py` (staging) and `build_device_map.py` (main and upper) through one `mast_plan.plan`. JMRI's Signal Mast Logic is keyed by mast user name (`discovered_sml.xml`: `<sourceSignalMast>Mast 4RA`).

So step 7 below (staging generated like main and upper) is a medium change, not a rewrite: the geometry is already shared, and the work is in the names, rows and beans.

## Owner decisions

| # | Question | Answer |
|---|---|---|
| 1 | What is a device's ID? | **Decided (owner, 2026-11-24): keep it simple.** A switch by its number and half, a block by the objects at its ends, a detector by its block, a mast by the switch, leg and direction it protects. On a re-import, a switch whose ID is gone but whose three tracks match a new switch is listed as the likely match; the owner confirms. |
| 2 | Where do names live? | **Decided (owner, 2026-11-24): in one `hartlib` name store** that every output reads; the plugin draws the owner's name if defined, else the generated one. `plan_overrides.json` keeps switch numbers and drawing settings, holds no names, and nothing writes it. Detail: [The name store](#the-name-store). |
| 3 | A new AnyRail file drops an ID that has owner values | **Decided (owner, 2026-11-24): stop and list it;** the owner moves the values to the new ID or drops them. |
| 4 | What gets named, and the order | **Decided (owner, 2026-11-24):** nothing is named before the owner is ready. The control points in `interlockings.csv` are owner values and stay; every other main and upper name stays generated or blank. This plan needs no new names; the main and upper station maps wait until the owner names those stations. |
| 5 | Copies of names in other systems | **Decided (owner, 2026-11-24):** Operations Pro (`OperationsLocationRoster.xml`, the car roster) and STS keep their own names. A rename lists the copies found in the repo's Operations Pro files (as `check_name_copies.py` does for hand files); nothing rewrites them. STS is not checked. |
| 6 | Mast renames | **Decided (owner, 2026-11-24):** JMRI keys Signal Mast Logic by mast user name and stays stock, so a mast rename, or a rule change that renumbers masts, needs a new SML discovery and the owner's panel approval. The build warns before it. |

## The name store

For every device the store gives the generated name, then the owner's if set, then the display label (`track_labels`). The Layout Editor panel, the CATS desks, the schematic and `tables.xml` read names only from it. The owner's track and bumper names (today the `name` and `end` edits in `plan_overrides.json`) move to the owner layer, keyed by ID. `hartlib` writes the resolved name of every track into the folder the plugin reads (`layer_files.view`), the same way the generated stations reach it today; that folder is rebuilt on every build and nobody edits it.

## Staged plan

Each PR leaves `tables.xml`, the desks, the Layout Editor panel and the approved fingerprints byte-identical unless it lists a diff, and passes `make panels CHECK=1`, `./tools/check.sh` (`FULL=1` through `make remote` for bean PRs) and, when beans change, `make panelpro-test`. Code PRs get `/code-review medium`.

| # | Step | Size | Notes |
|---|---|---|---|
| 1 | Tests first | 1 day | Builder merge step 1: golden tests of every main and upper bean `le_tables` makes, unit tests of `master_beans` per assignment, `build_masts.generate` on staging, and the device-master merge. **Done (2026-11-24):** see [Step 1 findings](#step-1-findings) |
| 2 | `id` column | 0.5 day | The builders write an ID on every row (decision 1); `check_rows` holds it unique per level. Only `devices_generated.csv` changes |
| 3 | The name store | 1.5 days | Check first that the generator can name every track from the plan before the drawing (the end switches come from the plan graph). Then `hartlib` resolves every name (decision 2); the `name` and `end` edits move to the owner layer, keyed by ID; `layer_files.view` writes them for the plugin; `cats_panel.py` and `le_names.py` read names from the store instead of the drawing. A check fails if `plan_overrides.json` holds a name again. Drawings byte-identical |
| 4 | Owner file keyed by ID | 1 day | `devices_field.csv` rekeyed on `(level, id)`; `user_name` becomes an owner cell. The build prints new and gone IDs against the last generated file and stops as decision 3 says; a rename lists the Operations Pro copies (decision 5) and warns on a mast rename (decision 6) |
| 5 | Files keyed by ID | 1.5 to 2 days | `block_lengths.csv`, `block_numbering.csv`, `wiring.csv`, `mast_cells.csv`, `masts.csv` (`facing`, `protects`), `block_overrides.csv` and `main_lines.csv` key on device IDs, so a rename touches no row. Frozen wiring rows keep their pins; their labels follow the name store |
| 6 | Every read through `hartlib` | 1.5 days | `hartlib` readers for `block_overrides.csv`, `main_lines.csv` and `mast_cells.csv`; `layout_facts.py`, `write_inventory.py`, `check_hart_phase02.py` and `analyze.py` onto `hartlib.railroad` (was builder merge step 7, second half); mast rows read only through `hartlib.level_masts`. Then a check fails when a script outside `hartlib` opens a layout data file. Jython inside JMRI cannot import `hartlib` and reads only generated outputs; the check lists those scripts by name |
| 7 | Staging generated like main and upper | 1.5 days | `staging_rows` and `staging_wired_rows` go through the main and upper functions; a staging device with no owner row gets generated values instead of stopping; `FIELD_LEVEL` goes. Staging's owner values still win, so outputs stay the same |
| 8 | Block names into the rows | 0.5 day | Builder merge step 2 (`block_numbering.csv` stays the source of main and upper numbers, owner 2026-11-23) |
| 9 | `start` column and comment data | 0.5 day | Builder merge step 3 |
| 10 | Bean shapes by column | 1 day | Builder merge step 4 |
| 11 | Every level through `master_beans` | 1 day | Builder merge step 5: deletes `add_level_*` and the `IT:HART:C3` patterns in `cats_panel.py` and `le_tables.py`, so the bean name is always the row's `jmri_name`. Listed comment diff (owner's 2026-11-23 answer), `make panelpro-test`, deploy |
| 12 | One mast step | 1 to 1.5 days | Builder merge step 6: `build_masts.py` part 1 into the builder, so one writer makes every level's mast and head rows; any main or upper mast change goes to panel approval |
| 13 | One reader | 1 day | Builder merge step 7, first half: `le_names.level_names` and `staging_device_map.load` become one reader keyed by ID |
| 14 | Level tests to column tests, and a swap test | 1 day | Builder merge step 8, then in the sandbox swap one main or upper turnout to a physical name by its owner row alone: `make panels`, `make panelpro-test`, then revert |

## Step 1 findings (2026-11-24)

- `tools/schematic/tests/test_bean_goldens.py` pins both bean processes against the committed `tables.xml`, without the plugin: `tables_build.base` is the committed manager sections once `le_tables.strip_build_owned` has run (block paths and mast properties left out, as JMRI and discovery derive them); every main and upper bean is a line of `tests/fixtures/main_upper_beans.txt` (783 lines; a listed bean diff rewrites it with `--write`); `add_level_signals` on `masts.csv` alone makes the fixture's heads and masts.
- The row-to-bean map step 11 must keep: a main or upper switch gives one internal turnout and its LCC alias and feedback rows none (DIRECT feedback); every main and upper block row has assignment `none` today yet gets a names-only block, a full block and a layout block from `le_tables`, except the two helix blocks, which are staging's beans bound to a main and upper sensor; a detector gives one internal sensor and one `ActionSensor`, a turnout one `ActionTurnout`.
- The two block length formats (`le_tables.r1` and `master_beans`) agree on every committed length and every hundredth of an inch to 3000 in.
- `build_masts.generate` on staging and the device-master merge already had tests on the committed data (`test_build_masts.CommittedData`, `test_devices_pair`); `master_beans` now has a case per assignment (`MasterBeansByAssignment`).
- The data-check write guard (`repo_read_only`) refused `layer_files.view` swapping its cache link on the first build in a new worktree; it now judges a renamed or removed link by where it stands.

## How to run this

- Started 2026-11-24 (ADR-033 Accepted). While the Mac is loaded (owner's Repo-audit session, 2026-11-24): one agent and one step at a time, only the new tests on the Mac, every full `check.sh` or suite through `make remote`; step 2 waits until the check-speed hand-off has merged.
- One PR per step, in order, each in its own `make wt` worktree. Steps 2 to 7 are `hartlib` and `tools/schematic/` work (`schematic-builder`); steps 11 and 14 need the Mac's PanelPro and stay in the main session.
- Steps that add or move a pipeline step update `docs/pipeline-map/pipeline_map.json`.
- Docs to update as steps land: `tools/hartlib/README.md` (`hartlib.devices`), `wiki/pipelines/schematic-panels.md`, `jmri/layouts/hart/data/devices.columns.csv`, ADR-027, 028 and 029 (amended by 033).

## Risks

- `build_device_map.py` (833 lines), `device_map_staging.py` (448) and `tables_build.py` (963) are partly untested; step 1 is not optional.
- Steps 4 and 5 change the key every writer and test uses (`hartlib.devices.KEY` and the data files'); run the full suite through `make remote`.
- Step 3 depends on the generator naming tracks before the drawing; if it cannot, the plugin keeps drawing staging's names from the view and the main and upper names stay after the drawing, and the step says so before going on.
- It shares readers with the station maps (`stations.csv`, `sheets.csv`); do not run the two at once.
