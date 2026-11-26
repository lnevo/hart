# ADR-029 — `tables.xml` is an output of one device master and a template

- **Status:** Accepted. Amended 2026-11-21: the device master is two files (see the amendment at the end; built 2026-11-21).
- **Date:** 2026-11-20
- **Deciders:** lnevo
- **Builds on:** ADR-008 (one tables file), ADR-014 (hosts load `preference:tables.xml`), ADR-027 (staging from its device map), ADR-028 (main and upper on virtual devices)

## Context

Device facts are kept three times: `public_name_map.csv`, `device_map_staging.csv` and `device_map_main_upper.csv` each hold parts of them, and `tables.xml` holds them again. The DCC group is parsed from JMRI comments, and the build finds its own items by comment and name. Staging has no generator: `build_layout_le.py` builds on the live `tables.xml`, so for staging `tables.xml` is still a source. The inventory and design are in the project-health hand-off, row 9 ([`projects/project-health-handoff.md`](../../archive/history/wiki/projects/project-health-handoff.md)).

## Decision

**`tables.xml` is an output.** It is the file PanelPro and CATS load. Nothing reads it as a source. A pulled Store is the one exception: it is split back into the sources. (Owner, 2026-11-20.)

**The device master**
- `jmri/layouts/hart/data/devices.csv` holds every device on all three levels in one structure. Staging, main and upper differ only by column values.
- `devices.columns.csv` describes every column. A test checks it against the header.
- Every row has a `description`.
- `assignment` says how the device is in JMRI now: `field`, `virtual` (ADR-028), `none` (no bean yet) or `spare`. Swapping a physical device in for a virtual one edits that row only.
- `role` says what the device is (W6 row 8). Readers test `role`, never a name prefix.
- `written_by` names the script that owns the row, or is empty for a hand-kept row. The allowed values are one constant, so merging builders changes one place. Each script rewrites only its own rows.
- The DCC address is a column. Nothing parses it from a comment.
- JMRI comments are generated from the wiring columns, as they were first derived from the wiring documents. They are not stored as free text.
- The pre-ADR-005 alias names are dropped. Retired identity names are dropped. The two spare detectors stay as `spare` rows.

**The template**
- What PanelPro owns and the build does not generate (memories, the "Hide windows on start" LogixNG, clock and turnout-manager settings, `blockrouting`) is kept in one JMRI-format template file.
- Discovered Signal Mast Logic is its own file, written only by the discovery wrapper.
- What JMRI writes on every Store (the header comment, `jmriversion`, `filehistory`, the clock time, memory values) is a fixed envelope in the build and is dropped on a pull. The old file history is lost once.
- The saved block paths on the staging blocks are dropped once a sandbox PanelPro load shows JMRI rebuilds them from the panel.
- The deploy-time rewrite of `tables.xml` (`disable_digicon_sml_in_tables.py`) moves into the generator, so the hosts get exactly the committed bytes.

**Pulls**
- `make tables-pull` and `make tables-pull-pi` keep the Store with its base, and `tools/schematic/split_store.py` compares the Store, the base and the generated file item by item.
- Amended by the owner, 2026-11-20 (R9d): the default is to keep the Store. What the template holds, and anything new the owner made that the build does not claim, goes into the template. The repo wins on what the build makes (the `devices.csv` beans, the panel, the logic, the Digicon rule), and each dropped edit is listed. A rename or comment on a hand-kept `devices.csv` row, and any item both the repo and the Store changed, is reviewed: the owner merges or drops each one. A Store counts as taken only once its split is merged (`data/store_splits.csv`).
- Amended by the owner, 2026-11-20 (after the first live split): a device added in PanelPro is added to `devices.csv`, not dropped. Not every device is a layout element (a test turnout, a DCC accessory added as a turnout), so its row has no level, cp or role until the owner gives them, and its beans are kept exactly as the Store wrote them, as JSON in the `jmri_bean` column, which the build copies into `tables.xml`. A later Store's change to that device updates the row. Nothing lists these rows as waiting.

**Cut-over gate**
- The first generated `tables.xml` matches the committed one byte for byte after a defined normalisation. A sandbox PanelPro load and Store returns the same bytes. Every remaining difference is listed and explained before the switch.

The `AGENTS.md` rule "fix the data in `tables.xml`" becomes "fix the source data or the template".

## Consequences

- One place to change a device, for every level.
- `public_name_map.csv` and the two device maps are generated from the master during the change-over, then retired (R9e).
- An old Store or document that uses pre-ADR-005 names can no longer be converted automatically.
- Builders that write device rows must name themselves in `written_by`.

## Open

- R9b to R9e were built in that order and are done (2026-11-21; [`project-health-handoff.md`](../../archive/history/wiki/projects/project-health-handoff.md)). `devices.csv` in the Decision above is now two files, merged by `hartlib.devices` (amendment below).

## Amendment 2026-11-21: the device master is two files

Decided by the owner on 2026-11-21, from the pipeline-efficiency review (T6a). Built on 2026-11-21 (branch `agent/claude/devices-two-files`): the merged view of the two files is the last `devices.csv` byte for byte, and `make panels` gives every output unchanged.

**Why:** No row of `devices.csv` is hand-kept any more, because the builders took over the last ones on 2026-11-20. The owner's facts survive only as staging cells that `build_device_map.py` and the mast builder copy forward from the file's previous contents. So each builder reads its own last output to recover the owner's cells, and a Store split writes into a file the builders also write.

**Decision:**
- `devices_generated.csv` holds every row, written only by the build scripts. `written_by` still names the owning script.
- `devices_field.csv` holds the owner's cells. Each row is keyed by (`level`, `layer`, `user_name`) and carries only the hand-owned columns (amended by ADR-033, naming-layers step 4, 2026-11-25: a row is keyed by (`level`, `id`), the device's ID from the plan, and `user_name` is one of the owner's cells): `dcc`, `layout_block`, `jmri_comment`, `notes`, `detector`, `stop` and `cp`; `system_name` and `jmri_name` on staging blocks; and the node and notes of a wired mast or head. A device added in PanelPro and taken in by a Store split is kept here in full, with no level and its `jmri_bean`.
- `hartlib.devices` merges the two into the one view every reader gets. A field cell wins over the generated one.
- Builders read `devices_field.csv` as an input and write `devices_generated.csv`. They never read their own last output.
- `split_store.py` writes only to `devices_field.csv` and the template.
- Checks and messages name a row by its key, not a line number. The row-order rule applies to each file on its own.

**What changes in this ADR:** "one structure" now means one merged view, not one file. An empty `written_by` no longer marks a hand row (there are none), and the `adopts` mechanism goes. `devices.columns.csv` describes both files.

**As built (2026-11-21):**
- `FIELD_COLUMNS` are the cells the builders carried before: `role`, `assignment`, `cp`, `system_name`, `jmri_name`, `node`, `dcc`, `jmri_comment`, `trial_name`, `notes`, `detector`, `stop`, `layout_block`. The field file has 170 rows: staging's 80 turnouts, LCC aliases and feedback sensors, 45 blocks and 43 occupancy sensors (each with its identity, `role` and `assignment`), the wired Mast 6LB's node and Head 6LB's notes. `devices.columns.csv` says which file may hold each column. `tools/schematic/split_device_master.py` made the split once; it and its test were deleted on 2026-11-22 (see git history at commit 6889bf0c), and `hartlib.devices` checks the column rule.
- A wired block's comment is the owner's words with `{occupancy}` where the builder puts the detector's `wiring.csv` text, so a moved pin changes no hand file (`hartlib.devices.OCCUPANCY_MARK`).
- A spare detector has no field row: `wiring.csv`'s spare inputs make it, and it holds no owner cell.
- The one read-back a builder makes of its own output is its name numbering (`hartlib.devices.allocated_names`): staging parts' block and layout-block numbers and the virtual masts' ordinals on every level. The builders cannot write the owner's file, and numbering again would shift names, so they keep the numbers they gave. No owner cell is ever read back.
- A block that becomes a part stops the build while its field rows stand, naming them: its names and comment are the owner's and would be lost. Once the owner removes them, its input becomes a spare.
- A writer does not read the old merged view, so a field row the owner removed or renamed never blocks the rebuild that makes the pair whole again.

**Acceptance:** the split is a pure refactor. `tables.xml`, the CATS desks, the Layout Editor panel and the approved fingerprints come out byte-identical, so the owner approves nothing again.


**Amended by ADR-033, naming-layers step 7 (2026-11-25):** a staging device no longer needs a field row. The builder makes every level's rows from the plan and puts each device's field row over its generated row by id, so the owner's values still win and a device with no field row keeps the generated values (a staging block is numbered as a part is, a staging turnout is bound to its address). A field row is the owner's cells only; the main and upper builder takes the owner's name the same way. `FIELD_LEVEL` is gone.

**Amended by ADR-033, naming-layers step 11 (2026-11-25):** one bean process. `hartlib.tables_build.base` makes every level's beans from the device master (`master_beans`, and the startup LogixNG, `start_logixng`); the Layout Editor build adds only the panels and checks that every name they bind is a bean of the base. `GENERATED_LEVELS` and `le_tables.add_level_*` are gone, and with them the build's strip of its own beans from earlier tables (`strip_build_owned`): the build never starts from `tables.xml`.
