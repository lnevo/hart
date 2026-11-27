# Generated, then the owner's, then frozen wiring: hand-off (2026-11-24)

Status: done (2026-11-25)

The plan for [ADR-033](../decisions/ADR-033-generated-then-owner.md): one flow for every level, where the generator names every device, the owner's values always win, and frozen wiring stays fixed. It takes in the parked [builder merge](../../archive/history/wiki/projects/builder-merge.md) (one bean, row and mast process), which no longer waits for main and upper wiring, and puts every name and every read of layout data behind `hartlib`. About 14 PRs and 13 to 16 agent-days.

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
| 2 | `id` column | 0.5 day | The builders write an ID on every row (decision 1); `check_rows` holds it unique per level. Only `devices_generated.csv` changes. **Done (2026-11-24):** see [Step 2 findings](#step-2-findings) |
| 3 | The name store | 1.5 days | Generator names every track from the plan; `hartlib.track_names` keeps the owner's names by ID and gives them to the plugin; readers by ID; a check stops a name in `plan_overrides.json`. Drawings byte-identical. **Done (2026-11-24):** 3a the store ([Step 3 findings](#step-3-findings)); 3b the readers by ID ([Step 3b findings](#step-3b-findings)) |
| 4 | Owner file keyed by ID | 1 day | `devices_field.csv` rekeyed on `(level, id)`; `user_name` becomes an owner cell. The build prints new and gone IDs against the last generated file and stops as decision 3 says; a rename lists the Operations Pro copies (decision 5) and warns on a mast rename (decision 6). **Done (2026-11-25):** see [Step 4 findings](#step-4-findings) |
| 5 | Files keyed by ID | 1.5 to 2 days | `wiring.csv`, `block_lengths.csv`, `block_numbering.csv`, `block_overrides.csv`, `main_lines.csv` and switches.csv's staging legs key on device IDs; their names come from the name store, so a rename touches no row. **Done (2026-11-25):** see [Step 5 findings](#step-5-findings); 5b, `preferences.json` and `stations.csv` by block ID: [Step 5b findings](#step-5b-findings) |
| 6 | Every read through `hartlib` | 1.5 days | `hartlib.hand_lists` reads `block_overrides.csv`, `main_lines.csv` and `mast_cells.csv`; `layout_facts.py`, `write_inventory.py`, `check_hart_phase02.py` and the speed-match routes go through `hartlib`; a check fails a script outside `hartlib` that names a layout data file, Jython listed by name. **Done (2026-11-25):** see [Step 6 findings](#step-6-findings) |
| 7 | Staging generated like main and upper | 1.5 days | `staging_rows` and `staging_wired_rows` go through the main and upper row makers; a staging device with no owner row gets generated values instead of stopping; `FIELD_LEVEL` goes. **Done (2026-11-25):** see [Step 7 findings](#step-7-findings) |
| 8 | Block names into the rows | 0.5 day | Builder merge step 2 (`block_numbering.csv` stays the source of main and upper numbers, owner 2026-11-23). **Done (2026-11-25):** see [Step 8 findings](#step-8-findings) |
| 9 | `start` column and comment data | 0.5 day | Builder merge step 3: main and upper rows carry `start` and `bean_comment`; `le_tables` reads them. **Done (2026-11-25):** see [Step 9 findings](#step-9-findings) |
| 10 | Bean shapes by column | 1 day | Builder merge step 4. **Done (2026-11-25):** see [Step 10 findings](#step-10-findings) |
| 11 | Every level through `master_beans` | 1 day | Builder merge step 5. **Done (2026-11-25), PanelPro-tested and deployed with `67b6d185` (2026-11-25 11:31):** see [Step 11 findings](#step-11-findings); a listed diff of 399 main and upper comments |
| 12 | One mast step | 1 to 1.5 days | Builder merge step 6. **Done (2026-11-25), pending the SML discovery and the owner's panel approval:** see [Step 12 findings](#step-12-findings); nine upper mast pairs swap letters |
| 13 | One reader | 1 day | Builder merge step 7, first half: `le_names.level_names` and `staging_device_map.load` become one reader keyed by ID. **Done (2026-11-25):** see [Step 13 findings](#step-13-findings) |
| 14 | Level tests to column tests, and a swap test | 1 day | Builder merge step 8. **Done (2026-11-25):** see [Step 14 findings](#step-14-findings). The sandbox swap of Switch 107 by its field row alone built, discovered and passed `make panelpro-test`, then was reverted |

## Step 1 findings (2026-11-24)

- `tools/schematic/tests/test_bean_goldens.py` pins both bean processes against the committed `tables.xml`, without the plugin: `tables_build.base` is the committed manager sections once `le_tables.strip_build_owned` has run (block paths and mast properties left out, as JMRI and discovery derive them); every main and upper bean is a line of `tests/fixtures/main_upper_beans.txt` (783 lines; a listed bean diff rewrites it with `--write`); `add_level_signals` on `masts.csv` alone makes the fixture's heads and masts.
- The row-to-bean map step 11 must keep: a main or upper switch gives one internal turnout and its LCC alias and feedback rows none (DIRECT feedback); every main and upper block row has assignment `none` today yet gets a names-only block, a full block and a layout block from `le_tables`, except the two helix blocks, which are staging's beans bound to a main and upper sensor; a detector gives one internal sensor and one `ActionSensor`, a turnout one `ActionTurnout`.
- The two block length formats (`le_tables.r1` and `master_beans`) agree on every committed length and every hundredth of an inch to 3000 in.
- `build_masts.generate` on staging and the device-master merge already had tests on the committed data (`test_build_masts.CommittedData`, `test_devices_pair`); `master_beans` now has a case per assignment (`MasterBeansByAssignment`).
- The data-check write guard (`repo_read_only`) refused `layer_files.view` swapping its cache link on the first build in a new worktree; it now judges a renamed or removed link by where it stands.

## Step 2 findings (2026-11-24)

- `hartlib.device_ids` holds the grammar: `switch:<n>`, `dcc:<n>`, `fb:<n>:N|R`; `block:<ends>` from the plan ends of its strands (`block:1B-3A:1/2`, `block:107B-107C#1`, `block:1C-5A#1+1C-5A#2`); `os:<n>`, a staging crossover half `os:<n>:A-<leg A end>` and the 225 corners by schematic leg (`os:225:D`); `det:<block id>`, `spare:<system name>`; a home mast `mast:<switch or half label>:<leg>:<dir>`, others `mast:<facing block id>:<dir>`; heads `<mast id>:top|bottom|single`; panel lamps `panel:status:<system name>` (they share one `panel_items.json` item). 772 IDs, unique per level; rows with no level have none.
- **Open for step 7:** staging's turnout, alias and feedback rows still come from the owner's rows and `wiring.csv`, so their switch number is read from the user name (`wired_id`; `check_switch_ids` stops the build if a number has no staging OS block in the plan). Step 7 derives them from the plan.
- **Open for step 12:** both halves of a staging crossover carry the label "7", so their home masts are `mast:7:A:west` and `mast:7:A:east`, unique only by direction; the uniqueness check stops a clash. Step 12 (one mast step) can key a half's mast like its OS block.

## Step 3 findings (2026-11-24)

- **The first check failed, then was fixed with the owner (2026-11-24).** Every track name came from the plan except
  the numbers of parallel tracks (two tracks between the same switches): `plan_tracks.track_names` ordered them by drawn
  row. They are now ordered by their ends' plan labels and legs (`plan_tracks.plan_order`, the order of their block IDs),
  and so is `block_overrides.csv`'s `parallel` (no row uses it). Five main and upper pairs traded their 1 and 2
  (Track 103-105, 209, 215, 243 and 245 Spur); staging has no such pair and is unchanged. The owner approved the
  Layout Editor panel and both CATS desks with the new names (2026-11-24); main and upper names are not fixed yet.
- **The name store is `hartlib.track_names`.** The owner layer is `devices_field.csv`: a block row with an `id` keeps
  its track's name by it (22 staging rows: every named track, bumper and helix end). A field `id` must be the
  generated one (`devices.merge` and `unmerge` stop otherwise: a track that moved in a new export, decision 3).
  `plan_overrides.json` holds no name: `end` entries are `[switch, leg, kind, to]`, `left_end` is `block:3B-end`, and
  every merge stops on a `name` edit or a named `end` entry (`hand_problems`). `layer_files.merged` makes the plugin's
  `name` edit from the rows, each track found in the plan graph by its ID's switch labels and legs (no drawing), with
  `name_main` now the runs of the staging main lines (`build_main_route.py`). The plugin's prepared staging graph was
  compared edge by edge with the old one: no difference; the published draft is byte-identical.
- **Main and upper generated names are not written to the plugin:** they are not drawn on the schematic, and drawing
  them would change it. They stay `block_layer.name_tracks`' end-switch rule, now a function of the plan alone.
- **Open for 3b:** `block_layer`, `cats_panel.py`, `build_masts.py` and `staging_device_map.py` still read staging names
  off the drawn strands (which now carry the store's names through the plugin); 3b makes them look up the store by ID.
- **Closed at step 12 (2026-11-25):** the swap below makes an A face Spur 1; Mast 210LA faces Track 209 Spur 1 in `devices_generated.csv`. Was: a mast's letter (210LA, 210LB) is still ordered by drawn row, so after the renumbering Mast 210LA
  faces Track 209 Spur 2. Mast names were left alone (a rename needs SML discovery and approval, decision 6).
- **Closed at step 5 (2026-11-25):** `main_lines.csv` keys by block ID (`5;7@block:5B-7A`). Was: `main_lines.csv` and `milepost_route` still name staging tracks (`7@East Ext`), and
  `stations.csv` station tracks (W-1, W-2) are names too.

## Step 3b findings (2026-11-24)

- **The readers take names by ID.** `hartlib.track_names.piece_names` gives a drawn piece ("37C-39C #2", its ID part
  from `staging_device_map.band_refs`) its store name; a main or upper helix track takes its staging block's name
  through the `helix` map. `block_layer.tracks` (through `store_names`) puts the names on each track entry, so `name_tracks`, `half_block` and `check` never read the drawing;
  `cats_panel.py` (`staging_names`), `build_masts.plan_edge` and `staging_device_map.check_helix` take them as an
  argument. Outputs are byte-identical: `make panels CHECK=1 FULL=1` all current, `check_approved.py --check` all
  matching, an uncached `publish_draft.py --check` current.
- **One difference in what is named, none in what is built:** the plugin draws Brick-Plane's name on one of its two
  pieces (1C-5A #2); the store names both. Every reader gives the same block either way.
- **Review nits from 3a done:** one end key (`track_names.end_key`, `edge_run`) for `plan_runs` and
  `build_main_route.staging_keys`; the store reads only the folder it is given (a missing plan graph or
  `devices_field.csv` stops), and a test opts in with `track_names.repo_inputs` (`test_railroad.Copy`,
  `test_layer_files`). A section that draws no level and fills nothing reads no store.
- **Code review (medium):** a name now reaches only the pieces the owner named (pieces from #1 with no gap, and
  each drawn piece of a run named by piece needs its own); two drawn tracks up the helix from one `helix` switch
  stop; `staging_names` and `check_helix` take the data folder from their caller; `build_signals.py` names its
  tracks with `build_device_map.named_tracks`, as the device map does.
- **Closed (2026-11-25, PR #1114):** the drawing stamp keys on `hartlib` code. Was: `publish_draft.check_digest` keys the drawing stamp on the data, the plugin and the field file,
  not on `hartlib` code, so a `hartlib` change to the plugin's view is not redrawn by `--check` until the data
  changes (it was checked uncached here). Main and upper loop-half names still go onto the drawing from the device
  master (`cats_panel.name_loop_halves`, `le_names`), as step 13 plans.

## Step 4 findings (2026-11-25)

- **The field file is keyed by ID.** `hartlib.devices.KEY` is `(level, id)`; `key_of` gives it (a Store's level-less row,
  which has no id, keeps `("", layer, user_name)`), `name_key` and `row_text` name a row in messages as before. A
  field row with a level must carry its id and holds its `layer` (checked against its id's row) and `FIELD_COLUMNS`,
  which now include `user_name`. The 148 field rows that had none got their id copied from `devices_generated.csv`;
  no other cell changed. The generated file keeps every row's name, so `unmerge` leaves `user_name` like `id`, and
  `redundant` skips it.
- **What a write changes** is `hartlib.device_changes`, run by every `outputs_after_rows`: new and gone IDs per level
  and layer (to stderr or a `warn` callable); a gone ID with owner's cells stops, naming the cells and the new IDs of
  its level and layer (decision 3); a rename lists the lines of `jmri/layouts/hart/operations/*.xml` that hold the old
  name, or a track's bare name as an attribute value, as Operations Pro names tracks (decision 5); a mast rename warns
  that it needs SML discovery and panel approval (decision 6). Nothing prints today: every ID and name is unchanged.
- **Staging's builder finds its field rows by ID** (`staging_field`): an owner's new name for a staging block or
  detector renames the row, and a part's `part_of` and the detector's `blocks` follow; a turnout, alias or feedback
  row's `wiring.csv` row is found by the generated name its id gives (`wired_name`, which replaces `wired_id`).
  `track_names.owner_names` reads only `block:` ids now that OS rows carry theirs.
- **Main and upper, my call under the owner's rule of 2026-11-25:** their builders take no owner's name yet, so a
  main or upper field `user_name` other than the generated one stops the write (`unmerge` names both and says to drop
  the cell); step 7 brings them onto the staging path. Staging's masts and heads are the rule's, so `build_masts.py`
  still matches its two field rows by name and the same stop applies.
- **Outputs byte-identical:** `make panels CHECK=1 FULL=1` all current, `check_approved.py --check` all matching.
- **Code review (medium), fixed:** the LCC contract pairs a turnout and its alias by id; a turnout bound by its user
  name (its field `jmri_name`, Q13) renamed without its `jmri_name` stops, naming both cells; an alias's note names
  its turnout's owner name; the Operations Pro search counts a bare track name only as a track or location `name`
  and not the tail of a longer name; the changes are said once, after the write merges back, marked check-only on a
  `--check` run; a nameless field row is found by its id.
- **Closed at step 5 (2026-11-25):** `devices.follow_renames` carries a block rename into `facing` and `protects` (Step 5 findings). Was: a staging rename still breaks the files keyed by name (`wiring.csv`'s detector rows,
  `block_lengths.csv`, `stations.csv` tracks, `masts.csv` `facing`), and names derived from a renamed block (a mast's
  `facing`) are not followed. A trial rename of OS Switch 19 in the field file left only `devices_generated.csv` stale;
  the other files were not traced one by one.

## Step 5 findings (2026-11-25)

- **The keys.** `wiring.csv`: an `id` per device row (switch:35, fb:35:N, a head's mast:5:B:west:single, a detector's
  det:<block id>); `device` is only a button's, relay's or calibration relay's label, and main and upper track
  detectors keep their plan key (switch_a, switch_b, parallel, half). `hartlib.wiring.read` names each row from the
  name store (`hartlib.devices.user_names`); the builders find pins, turnouts and the helix detectors by ID (the
  helix through `plan_overrides.json`'s `helix` map). `block_lengths.csv`: `(level, id)`, its `user_name` a label the
  new `length-labels` step writes (`plan_lengths.py --labels`, no plan file), so the speed-match copy on the Pi still
  reads names. `block_overrides.csv`: a `track` row's `block` is an OS block ID. `block_numbering.csv`: an `id` per
  live block, a retired block's old name in `retired`. `main_lines.csv`: tracks by block ID (`35@block:33A-35A`,
  `block:39B-helix`); `milepost_route` is written with the store's names, so it follows a rename.
- **Also rekeyed, not in the plan's list:** `switches.csv`'s staging legs (`os_id`, `closed_id`, `thrown_id`; the
  name columns are labels the hands step writes). A track rename stopped `plan_lengths.py` without it.
- **The merged view follows a rename.** `devices.merge` carries a block's owner's name into the generated cells that
  name it (`part_of`, `blocks`, `facing`, `protects`; `follow_renames`), and `build_masts.py` takes a home mast's OS
  block by its ID, so a mast's `facing` and `protects` follow too.
- **My calls (owner's rule of 2026-11-25):** `masts.csv` keeps its columns: it is written again on every build from
  the merged view, so its names follow; ID columns would add nothing a reader uses yet. A crossover half's
  `block_overrides.csv` row keeps its half's generated name (OS Switch 7b): that row names the half. `mast_cells.csv`
  stays as it is: parked with the USS machine, and two of its masts (2035, 2036) no longer exist; key it by mast ID
  on unpark.
- **The rename proof.** `tools/hartlib/tests/test_rename_by_id.py` renames Track East Lead and OS Switch 19 in a copy's
  field file and checks every rekeyed reader. A scratch copy of the repo with the same two renames in
  `devices_field.csv` alone ran `make panels`: every step to `schematic` passed; `sml-current` stopped, as a block's
  name is in the discovery base (on the Mac `make panels` discovers itself); `tables`, the desks, `sync_signals` and
  `check_device_master` then passed by hand, and the approvals showed the renamed labels. The build rewrote only
  generated files and the labels; `wiring.csv`, `main_lines.csv`, `block_overrides.csv` and `block_numbering.csv` did
  not change.
- **Outputs byte-identical:** `make panels CHECK=1 FULL=1` all current, `check_approved.py --check` all matching.
- **Open:** `preferences.json` names tracks (staging `min_cells`, `turnbacks`, `le_labels`; main and upper
  `optional_block_contents`, `hidden_names`, `track_labels`): renaming Track S-1 stopped the Layout Editor labels.
  It needs run keys the name store resolves in `layer_files.view`, as the `name` edit has. `stations.csv`'s `tracks`
  (W-1;W-2) needs block IDs or run keys, read through `hartlib.railroad.read_stations` and `read_places`. A renamed
  crossover half stops (`railroad_facts.os_label`): its half letter comes from its name. The speed-match routes in
  `analyze.py` name blocks (step 6). A helix track rename was not tried.

## Step 5b findings (2026-11-25)

- **The keys.** `preferences.json`: every track key holds block IDs: staging's `min_cells` track names, `turnbacks`,
  `le_labels` (`extra_steps`, `extra_follow`, `name_columns`, `name_steps`, `optional_block_contents`), main's and
  upper's `le_band_labels` (`hidden_names`, `optional_block_contents`) and `track_labels` (by the staging helix block,
  `block:39B-helix`). `layer_files.merged(data, "preferences")` names them (`track_names.pref_section`: "Track S-1"
  or "S-1", as each key takes it), so the plugin's folder holds the same names as before; `pref_problems` stops a
  hand section with a non-ID in a track key or a "Track ..." string anywhere. `stations.csv`'s `tracks`:
  `block:3B-end;block:3C-end`, checked by `read_stations` and named by `railroad_facts.station_tracks` for
  `read_places` and `build_staging_sets.py`. Both go through `track_names.names_by_id`: the owner's name, else the
  generated one in `devices_generated.csv`.
- **Also changed:** `read_helix_tracks` and `build_main_route.prepared` read the merged preferences, not the hand
  file. `publish_draft.check_digest` hashes the merged view, as a generated name can change it with no hand file
  changed (stamp version 3).
- **The rename proof.** `test_rename_by_id.RenameInPreferencesAndStations` renames Track S-1 and Track W-1 in a copy's
  field file. A scratch copy of the repo with the same two renames (no git there, so the steps were run one by one, the
  plugin given as the copy's own pinned submodule through `SCHEMATIC_PLUGIN`): every step passed to `schematic`, which
  reported the drawing and five station sheets changed as expected; `sml-current` stopped, as expected; `tables`,
  `sync_signals`, `check_device_master` and the desks then passed. `preferences.json` and `stations.csv` did not
  change; `plan_generated.json`'s `station_tracks` and `signals.json` took the new name.
- **Outputs byte-identical:** the merged view's names unchanged, `make panels CHECK=1 FULL=1` all current,
  `check_approved.py --check` all matching. No main or upper change.
- **Build order, my call (owner's rule of 2026-11-25):** 39 of the 54 IDs in `preferences.json` are main and upper
  blocks or staging parts with generated names only, which are the device-map step's output. Naming them from the
  plan inside hartlib is out of reach: the rule (`block_layer.name_tracks`, the parallel numbers, parts, loop halves
  and `block_numbering.csv`) runs on the solved drawing, and the solve reads the view. Steps cannot be reordered
  either: device-map's solve needs main-route's output. So the view keeps an ID with no name yet as it is (no step
  before device-map reads those keys: they are the Layout Editor's labels), and `layer_files.unnamed_preferences`,
  in `check_device_master.py --check` after device-map, stops on one (decision 3). The steps before device-map read
  the last build's generated names, which differ only for a block whose generated name changed.
- **Code review (medium), fixed:** IDs match on their sheet's levels (`track_labels` on every level, a station's
  on its own) and a block of two levels is a clash; two `track_labels` keys for one track stop; `pref_problems`
  names a track key of the wrong shape and scans the keys as written; an empty `tracks` entry stops with its own
  message; `read_helix_tracks` refuses a plan name in `track_labels`; the `devices_generated.csv` readers are on
  the pipeline map.
- **Open:** a field `jmri_comment` is free text (W-1's still says "Brick yard Track W-1"); a rename does not reach it.

## Step 6 findings (2026-11-25)

- **The readers.** `hartlib.hand_lists` is the one reader of `block_overrides.csv` (`read_block_overrides`,
  `os_block_name`), `main_lines.csv` (`read_main_lines`, `resolve_stop`) and the parked USS board (`read_mast_cells`,
  `read_uss_cells`, `read_uss_plants`), each stopping with `HandListError` (a `ValueError`) naming the file and line.
  `block_override_rows.read_block_overrides`, `build_main_route.read_lines` and `layout_facts.load_*` are thin wrappers that keep
  their callers' errors (`MapError`, `RouteError`). `railroad.Sources` gained `stations`.
- **The scripts.** `layout_facts.py` opens no file: switches, stations and interlockings through `hartlib.railroad`,
  the board through `hand_lists`. `write_inventory.py` reads `lcos_nodes.csv` with `railroad.read_lcos_nodes` (which
  also stops on a node given twice or a row with no area) and `switches.csv` with `read_switch_rows`.
  `check_hart_phase02.py` takes staging's rows from `read_switch_rows`, so the whole file is held to its shape. Mast
  rows were already read only through `hartlib.level_masts` (every `masts.csv` reader calls `level_masts.read` or
  `read_masts`); nothing changed there.
- **The speed-match routes, my call:** `analyze.py` types each route's blocks by staging device ID
  (`block:5B-7A`, `os:7:A-5B`); `build_routes.py` names them from the name store and takes their sensors from
  `tables.xml`, and `routes.json` keeps the IDs beside the pairs (`ids`) for `load_routes` to check. `analyze.py` still
  reads `block_lengths.csv` itself, by the label the length-labels step writes: the Pi's live publisher runs it with a
  copy of the file and no hartlib (`tools/hosts/deploy/stage.sh`), so the check allows it by name.
- **The check.** `tools/audit/check_data_readers.py` (job `data-readers` in `check.sh`, tests in
  `tools/audit/tests/test_check_data_readers.py`) fails a tracked script outside `tools/hartlib/` (tests, `reference/`,
  `archive/` and `external/` left out) whose strings name a file under `jmri/layouts/hart/data/`, unless `ALLOWED` lists
  that script and file with a reason; an allowed pair no longer named fails too. Jython (imports jmri or java, or
  Python 2 only) must name none but `JYTHON_ALLOWED`'s: `loco_roster_import.py` and `new_locos.json`. 62 pairs in 31
  scripts are allowed today: writers of their own output (approvals, baselines, the template), plan inputs
  (`inputs/*.json`), stamp hashes, a text search (`check_name_copies.py`), paths handed to a hartlib reader, and ten
  direct readers not moved yet.
- **Open, for a later step:** the direct readers the check lists as not moved: `block_lengths.csv` in
  `export_track_lengths.py`, `infer_block_lengths.py` (also its writer), `levels_page.py`, `build_layout_docs.py` and
  `archive/code/ap-electrical/make_drawings.py`; `signals.json` in `render_le_layout.py`; `panel_items.json` (tools/schematic
  `panel_items.load`), `block_numbering.csv` (`le_tables.load_numbering`), `retired_virtual_masts.csv`
  (`mast_plan.read_retired`) and `sheets.csv` (`build_staging_sets.read_sheets`). The check sees names only: a path
  built from pieces or read from a config is not seen.
- **Outputs byte-identical:** the outputs of `write_inventory.py` (every cell and fill), `check_hart_phase02.py`,
  `layout_facts.py`'s loaders, `analyze.py` (its routes, lengths and a run over two logs rebuilt from the 2026-11-08
  transits) and both hand-list readers were dumped before and after: no difference. `routes.json`'s pairs are
  unchanged (it gained `ids`). `make panels CHECK=1 FULL=1` all current, `check_approved.py --check` all matching. No
  main or upper change.

## Step 7 findings (2026-11-25)

- **One row path.** `tools/schematic/device_map_rows.py` holds the row makers every level uses: `device_row` (the
  body of `build`'s `add`), `switch_device_rows` (a switch's turnout, LCC alias and two feedback rows; `build`'s
  `switch_rows` and `staging_wired_rows` both call it) and `owner_over` (a device's field row over its generated row,
  description rewritten). `build_device_map.master_outputs` writes every level: `owned_rows` puts the owner's cells
  over main and upper's rows and parts and follows a block rename into `blocks`, `part_of`, `facing` and `protects`
  (`devices.follow_renames`); their virtual JMRI names stay the generated ones.
- **Staging from the plan.** `staging_wired_rows` makes rows for each switch of the staging plan graph
  (`track_names.plan_switches`, relabelled), so a switch number comes from the plan, not from a field row's id
  (step 2's open item closed; `check_switch_ids` still holds the plan graph to the drawing). `staging_rows` generates
  each block and detector (role from its id or its track's ends, an OS block's cp its interlocking's, a comment
  marking its detector) and then takes the owner's row. A block with no field row is numbered as a part is
  (`part_bean_names`, assignment virtual, the builder's name memory); a turnout with none is bound to its address;
  an alias takes the owner's DCC address from the turnout's or its own field row, and a switch with none has no
  alias. `wiring.read` names a staging turnout or feedback with no field row by its id (Switch <n>).
- **Still stops:** a staging device with no `wiring.csv` row (staging's nodes are as built; the builder proposes
  none), a field or wiring row whose id the plan has not, a staging turnout bound by its old user name (Q13).
- **`FIELD_LEVEL` is gone** from `hartlib.devices` and `device_map_inputs`; the readers that filtered staging's
  rows by it use `railroad.STAGING_LEVEL` (`wiring._Names`, the mimic, `check_name_copies.py`,
  `build_layout_index.py`, `audit_panel_contracts.py`, `refresh_bean_comments.py`). `wired_name` and `WIRED_ID` went.
- **Tests:** `tools/schematic/tests/test_one_row_path.py`: the committed files come back byte-identical; Switch 9's
  and Track Barn's field rows taken out are generated instead of stopping; a field row naming main's Track 103 Spur
  "Track Coal Spur" reaches the device master, its detector's `blocks` follows and the rename is said.
  `test_block_layer`, `test_device_map_helpers`, `test_track_names` and `test_wiring` follow.
- **Outputs byte-identical:** `devices_generated.csv` unchanged, `make panels CHECK=1 FULL=1` all current,
  `check_approved.py --check` all matching, `test_blocks_every_level` and `test_bean_goldens` pass. No main or upper
  change.
- **Code review (medium), fixed:** a staging block whose field row gives no bean names is numbered (memory by
  id, so a rename keeps the numbers; one of the two names alone stops); `owner_over` keeps a filled generated
  comment over a templated field one; the binding check holds feedback rows too; an alias with no DCC address
  anywhere stops; `wiring.read` stops on a staging turnout or feedback id whose switch the staging plan lacks;
  renames are followed over every level's rows at once (`master_outputs`). My call (main and upper): an owner's
  `jmri_name` goes over a virtual one, as a swap is one row edit (ADR-028).
- **Open, for later steps:** staging's masts and heads are still `build_masts.py`'s, its two field rows matched by
  name (step 12). A main or upper turnout or block given an owner's name passes the builder, but
  `railroad.check_virtual_names` and the `device-map` invariant still read a switch number and a block's sensor from
  the user name, so `python3 -m hartlib.railroad check` would flag it (step 13 or 14: read them by id). A main
  detector's user name ("BS 103 Spur") does not follow its block's owner name, as staging's does. Wired or proposed
  is still per level in the callers (staging bound to its addresses, main and upper virtual), not data.

## Step 8 findings (2026-11-25)

- **One numbering, in hartlib.** `hartlib.block_numbering` is `block_numbering.csv`'s one reader (`read`, a
  `NumberingError`) and the rule (`block_sort`, `order`, `bean_names`: IB:C3:<nnnn> and ILB<1000 + nnnn>,
  `level_devices.LAYOUT_BLOCK_FIRST`). `le_tables.load_numbering` and `numbered_blocks` wrap it; the data-readers
  check no longer allows `le_tables.py` to name the file.
- **The builder writes the names.** `build_device_map.block_beans` gives every main and upper block row (parts too;
  not the two helix rows, whose beans are staging's) its `jmri_name` and `layout_block`; `IB:C3:` is an internal
  prefix (`devices.SOURCE_PREFIXES`), so those rows are `assignment` virtual. `devices_generated.csv`: 120 rows (48
  main, 72 upper), columns `assignment` (none to virtual), `jmri_name` and `layout_block`; every value is the bean
  `tables.xml` already held.
- **`le_tables` reads them** (`level_block_beans`) and numbers nothing; it still stops on a stale numbering row or a
  retired block drawn again, on a drawn block whose row has no names, and on a name of the wrong form or given twice.
  `check_device_master.check_tables` now holds a block's bean and layout block to its row's names.
- **My call (owner's rule of 2026-11-25):** the blocks are numbered over the generated names, not the owner's, so an
  owner's rename keeps every number. Before, the build sorted the merged names, and a main or upper rename with no
  `numbered_as` row would have shifted every block after it.
- **Tests:** `tools/hartlib/tests/test_block_numbering.py` (the rule; the committed rows hold the file's numbers);
  `test_one_row_path` (a row's names come from the file: a copy that appends Track 227-241 1 moves it last and the
  blocks after it up one; an owner's rename keeps the numbers); `test_le_tables` (the build follows a row's changed
  number); `test_check_device_master`, `test_build_device_map` follow.
- **Outputs byte-identical:** `make panels CHECK=1 FULL=1` all current, `check_approved.py --check` all matching,
  `build_tables.py --base-hash` unchanged against main, `test_bean_goldens` unchanged. No visible main or upper change.
- **Code review (medium), fixed:** `le_tables` stops when a row's layout block is not its block's ILB pair or the
  generated rows are stale against `block_numbering.csv` (`stale_block_beans`: run `build_device_map.py`); an owner's
  field `jmri_name` is not judged. A Store rename of a built block says to rename its `devices_field.csv` row. A
  numbering message names the file read (`Numbering.source`). The committed-rows test numbers over the generated names.

## Step 9 findings (2026-11-25)

- **Two new generated columns.** `start` (the bean's state when the tables load: `inactive` on a detector, `closed` or
  `thrown` on a turnout; `hartlib.devices.START`, checked by `check_rows`) and `bean_comment` (the bean's JMRI
  comment). `build_device_map.master_outputs` writes them on the merged rows (`device_map_rows.bean_cells`), so an
  owner's cp or notes reach the text; staging rows leave both empty. The words are `hartlib.level_devices`'
  (`LEVEL_COMMENT`, `sensor_comment`, `signal_note`), the text `tables.xml` already held.
- **The rule moved.** `startup_thrown` (thrown where the main route runs through leg C: 227 and 229) is
  `build_device_map`'s now; `build_layout_le.startup_thrown` is gone.
- **`le_tables` reads the cells** (`level_cells`, `cell_of`): each turnout's, block's, sensor's, head's and mast's
  comment and each turnout's startup position come from its row, and a row with none, or a sensor whose start is not
  inactive, stops with "run build_device_map.py". Breaking one cell in a copy made `build_tables.py --check` stale.
  `check_device_master.check_bean_cells` holds `tables.xml`'s comments and startup LogixNG to the rows.
- **`devices_generated.csv` diff:** two columns after `dir` on every row; 400 main and upper rows filled (39 turnouts,
  2 of them thrown; 120 blocks; 97 detectors; 68 masts; 76 heads). `devices_field.csv` gains the two empty columns
  (the files share one header). No other cell changed.
- **Tests:** `test_bean_goldens.RowCellsAreTheGoldenBeans` (each golden bean's comment is its row's `bean_comment`;
  the LogixNG sets each row's `start`; `bean_cells` gives the committed cells back), `test_le_tables` (comments and
  start from the rows), `test_level_signal_comments` (moved to `bean_cells`), `test_turnout_startup`,
  `test_check_device_master.BeanCellsCheck`, `test_devices` (the start rule). `test_blocks_every_level`'s digests
  skip the two columns, which the golden test pins.
- **Outputs byte-identical:** `make panels CHECK=1 FULL=1` all current, `check_approved.py --check` all matching,
  `build_tables.py --base-hash` unchanged against main's stamp, `test_bean_goldens`' fixture unchanged. No visible
  main or upper change.
- **Code review (medium), fixed:** only the rows the build makes a bean for get cells (`device_map_rows.makes_bean`:
  no spare detector, helix block, LCC alias or feedback row); a thrown switch with no main or upper turnout row stops
  `bean_cells`; `level_cells` stops on a layer and name on both levels; `check_bean_cells` says when a bean is missing
  or given twice; one main and upper level constant (`level_devices.LEVELS`); the cells are read once per build
  (`build_layout_le.build`) and handed down.
- **For step 11:** a main or upper bean is now its row's names, length, `start` and `bean_comment`; step 11 changes
  `bean_cells`' words to staging's (the listed comment diff) and makes the LogixNG from `start`.

## Step 10 findings (2026-11-25)

- **Shapes by column.** `tables_build.master_beans(rows, lengths, levels=GENERATED_LEVELS)` makes each bean from its
  row: `bean_name` (`system_name` on a field turnout, else `jmri_name`), `row_comment` (`bean_comment` where set, else the
  wiring columns), `turnout_feedback` (TWOSENSOR on the two `fb:<n>:R|N` rows of the turnout's level when both give
  beans, DIRECT when neither does on a virtual turnout, a stop on one or on a field turnout with none), `alias_is_turnout` (an LCC alias naming its turnout's bean gives
  none) and `start_actions` (an ActionSensor or ActionTurnout per virtual row with a `start`, under `START_ACTIONS`,
  in the LogixNG's socket order). Which beans a layer gives is `LAYER_BEANS`. A block takes the detector of its own level
  that names it; a helix detector (role helix) binds staging's helix block (`HELIX_LEVEL`).
  `le_tables.add_level_clear` builds its actions with the same `start_action`.
- **Still staging only:** `build_tables.py` and `base()` run `GENERATED_LEVELS`; `base()` stops on a staging row with
  a `start` until step 11 makes the LogixNG frame there.
- **master_beans against the golden.** `test_bean_goldens.MasterBeansOnEveryLevel` runs it over levels 1 to 3: 780 of
  the fixture's 783 lines match (39 turnouts, 97 sensors, 240 block passes, 120 layout blocks, 76 heads, 68 masts,
  136 startup actions, the 4 helix detector lines). The 3 left are the startup LogixNG's frame (its LogixNG,
  ConditionalNG and DigitalMany), which `add_level_clear` builds around the actions: step 11 moves it. The comments
  do not differ: `master_beans` reads `bean_comment`, which step 9 filled with today's words; step 11's listed comment
  diff is the change to `device_map_rows.bean_cells`' words. Staging's beans over every level are the staging-only
  ones but for the two helix blocks' and layout blocks' sensor.
- **My calls (owner's rule of 2026-11-25):** feedback and aliases are found by id (`switch:<n>`, `dcc:<n>`,
  `fb:<n>:R|N`) on the turnout's own level among every row, not by user name; a turnout row with no such id, or an alias with no
  turnout row, stops. A `start` on a row that is not virtual stops (a field device reports its own state).
- **Code review (medium), fixed:** a field turnout with no feedback beans stops, as before; `bean_name` keeps the old
  rule (system_name only for a field turnout), since ADR-028 makes a swap a `jmri_name` edit and `system_name` stays
  the main and upper draft; the block-to-detector map is keyed by level and only a helix detector crosses levels; an
  alias whose turnout row is missing or has assignment none stops; the mast message says bean name.
- **Tests:** `test_tables_build.ShapeByColumn` (a rule each, on a small main level run with staging);
  `test_tables_build`'s staging fixture rows got their ids.
- **Outputs byte-identical:** `make panels CHECK=1 FULL=1` all current, `check_approved.py --check` all matching,
  `build_tables.py --base-hash` the committed discovery stamp's, `test_bean_goldens`' fixture unchanged. No visible
  main or upper change.

## Step 11 findings (2026-11-25)

- **One bean process.** `tables_build.base` runs `master_beans` over every level's rows and wraps the startup actions
  in the startup LogixNG (`start_logixng`, placed as `add_level_clear` placed it). The Layout Editor build adds no
  bean: `le_tables.add_level_*`, `level_cells`, `level_sensors`, `strip_build_owned`, `GENERATED_LEVELS` and
  `le_common.BASE_LEVELS` (now `STAGING_LEVELS`: the level says only where a band's names come from) are gone.
  `check_bound` holds every band to the base; `check_level_blocks` keeps the numbering checks and stops on a drawn main
  or upper block with no occupancy sensor. `is_level_bean` finds a main or upper bean by its rows
  (`level_bean_names`), not by name grammar.
- **No virtual-name pattern left** in `cats_panel.py` (a switch binds the turnout `tables.xml` holds for it,
  `split_system_name`) or `le_tables.py`; `sync_signals.py` takes the bean classes from `tables_build`.
- **Comments in staging's form, my wording (owner's rule):** " | " parts, place first (the row's `jmri_comment`),
  `internal, not wired` on a bean no field device drives, then `planned <device> (draft)` or `not on a node yet`
  (ADR-028); a block names its detector first. Before/after, Switch 107: "Main and upper level, internal until the
  import (device map name; build_layout_le.py)" / "CP 107 | Switch 107 | internal, not wired | planned M2T3308
  (draft)"; Track 107-109: same / "BS 107-109 / IS:HART:C3:B:107-109; CP 107"; BS 107-109: "Main and upper level
  occupancy, virtual (device map; build_layout_le.py); planned M2S3306 (draft)" / "internal, not wired | planned
  M2S3306 (draft)"; Mast 108LA: "CP 107 | Switch 107 | West | virtual (device map); planned IF$shsm:...(IH3332)(IH3333)"
  / "CP 107 | Switch 107 | West | planned IF$shsm:...(IH3332)(IH3333) (draft)"; Head 108LA Top: "CP 107 | Switch 107 |
  virtual (device map); planned IH3332" / "CP 107 | Switch 107 | internal, not wired | planned IH3332 (draft)". A
  hidden mast with no cp gains its place ("Peninsula | buffer stop | East").
- **My call:** `bean_cells` gives `start` only to a virtual row, so a swapped (field) row never asks the startup LogixNG
  to set it.
- **The diff, classified by a script over main's and this `tables.xml`:** 399 changed lines, every one a `<comment>`
  line; 0 other differences (tree walk: same elements, attributes and texts but 399 bean comments): 120 blocks, 97
  internal sensors, 76 heads, 44 head masts, 23 virtual masts, 39 internal turnouts, all main and upper. Staging's
  beans are byte-identical. `devices_generated.csv`: 399 `bean_comment` cells only (Mast 120RC's text was already
  this form). `build_tables.py --base-hash` unchanged (`b2fe5165...`), no SML rediscovery; `make panels CHECK=1
  FULL=1` all current; `check_approved.py --check` all matching. The golden fixture is rewritten (the 399 lines).
- **Tests:** `test_bean_goldens` (base() makes the fixture's beans; staging alone is the same but the helix sensor),
  `test_le_tables` (`check_level_blocks`, `check_bound` on every band, `is_level_bean` by rows), `test_tables_build`
  (`start_logixng`), `test_turnout_startup`, `test_level_signal_comments` (each kind's words),
  `test_build_cats_panel_bindings` (a swapped turnout binds), `test_cats_panel`, `test_build_layout_le`,
  `test_le_cutover`, `test_helix_blocks` follow.
- **Code review (medium), fixed:** a swapped (not virtual) row's comment carries its wiring, not the note or a planned
  device, and a mast whose planned name is its own is not "not on a node yet"; the CATS desk checks and the desk
  build pick main and upper plants by the rows' turnouts (`tables_build.level_turnouts`), not the `IT` prefix;
  `level_bean_names` names a row whose start has no action; `is_level_bean` takes its names; `with_direction` lost
  its dead branch. No output changed. `panelpro_smoke_test.py` (Jython) keeps the virtual prefix: it checks the
  turnouts the startup LogixNG sets, which a swapped turnout leaves.
- **Open:** the main session runs `make panelpro-test` and the deploy (`--pi --win`).

## Step 12 findings (2026-11-25)

- **One writer.** `build_masts.py` part 1 is `tools/schematic/device_map_masts.py`; `build_device_map.master_outputs`
  runs it (`staging_masts`) on the block rows it makes in the same run (`staging_device_map.load(master_rows=...)`),
  not on its last output, and writes staging's mast and head rows. `build_masts.py` writes `masts.csv` alone (it reads
  staging's plan facts from the same plan and stops when the master's staging masts are not the rule's);
  `devices.WRITERS` is `build_device_map.py` and `panel_items.json`. Block lengths are read by `(level, id)`.
- **By ID.** Wired heads are `wiring.csv`'s rows by head ID, the owner's cells by mast or head ID, and a mast's field
  `user_name` names the mast and its heads on every level (`device_map_masts.owner_names`,
  `build_device_map.owner_mast_names`). A virtual mast keeps its ordinal by ID. A staging crossover half's mast is
  keyed like its OS block: `mast:7:A-13C:B:east` (nine staging IDs changed, no name).
- **One anchor rule and the head prefix as data** on every level: `file_rows` takes a home mast at no switch on any
  level as an anchor mast that must protect an OS block (`ANCHOR_LEVELS` gone); every builder names heads with
  `level_masts.head_name` (`HEAD_PREFIXES`).
- **Letters, my call (owner's rule of 2026-11-25):** A and B follow the plan order of the tracks the masts face
  (`plan_tracks.letter_order`, then a loop's half and the leg); virtual masts by the switch leg their track leaves.
  No plan rule keeps every staging letter: this one would swap 6LA/6LB and 8RA/8RB (the 5-7 pair's plan order is
  the reverse of its rows), so those four keep their names as owner names in `devices_field.csv` (heads follow).
- **Changed masts (upper only; old name, new name, what it faces):** 204RA to 204RB (Track 203-207), 204RB to 204RA
  (203-211), 212LA to 212LB (207-211), 212LB to 212LA (203-211), 218RA to 218RB (217-219), 218RB to 218RA (217-221),
  222LA to 222LB (221-223), 222LB to 222LA (217-221), 230LA to 230LB (229-241), 230LB to 230LA (229-233); virtual
  210LA/LB (209 Spur 2/1), 216LA/LB (215 Spur 2/1), 244RA/RB (243 Spur 2/1), 246LA/LB (245 Spur 2/1) swap, so an A
  faces Spur 1. Draft LCOS heads follow the names (placed in name order). Main and staging: no change.
- **Outputs:** `devices_generated.csv`, `devices_field.csv` (3 name rows), `masts.csv`, `signals.json`, the schematic
  and station sheets (upper renames; the others a revision stamp), the desks (26 lines, `cats-ctc` and `cats-abs` no
  longer match), the bean golden fixture (from the new discovery base). Discovery base hash `b2fe5165...` to
  `843f47e4...`. `tables.xml` is unchanged here: the main session runs the discovery and the approval.
- **Also fixed:** `freeze_wiring.track_keys` numbered parallel tracks by row while `resolve_track` reads plan order.
- **Code review (medium), fixed:** a staging block with no plan length no longer stops the device map before it
  writes (it keeps staging's last mast rows, writes, and exits 2, so `plan_lengths.py` can add the length); a dropped
  virtual mast's old name now taken by a new ID stops instead of handing it the ordinal; a half ID takes every end
  `end_key` gives (`A-helix`, `A-end`) and a bad mast ID is a RuleError; the staging band levels are read on first
  use. The device map reads `block_lengths.csv` by `(level, id)`, and length-labels after it rewrites the file only
  when a label changes, so the device-map stamp breaks once after a rename (its output unchanged), then holds.

## Step 13 findings (2026-11-25)

- **One reader, keyed by ID.** `hartlib.drawing_keys.read(levels)` turns each turnout and block row's `trial_name` keys
  into its device ID ({key: id}, {id: merged row}), parts among them, no LCC alias, and stops on a row with no key or
  id, a key or id given twice, or a part of no block row. A key's name is its ID's row in the merged view: the
  owner's, else the generated. `le_names.device_names` (main and upper), `staging_device_map.load` (staging) and the
  CATS desks (`cats_panel.drawn_keys`, `part_blocks`) read it; `name_loop_halves` names each balloon-loop half by ID
  this way (Step 3b's open item). What stays per level is the drawing side: staging's k/n pieces, switch idents,
  normal legs and masts; main and upper's crossover insides, connectors and lengths.
- **The railroad check by ID** (Step 7's open item). `DeviceRow` carries its `id`; `DeviceMap.turnouts` and
  `check_virtual_names` take a turnout's switch number from it (`turnout_switch`); `read_device_map` and
  `check_virtual_names` pair a block with its detector as `det:<block id>`. A virtual name stays the generated one
  after an owner's rename, and the generated file keeps the owner's name, so a device the owner names in
  `devices_field.csv` (the invariant passes their IDs) has its occupancy sensor and heads held to their form only.
  `test_one_row_path`'s Track Coal Spur rename now passes the check.
- **Direct readers** (Step 6's open item, by a helper agent): `export_track_lengths.py`, `levels_page.py`,
  `build_layout_docs.py` and `make_drawings.py` read `block_lengths.csv` through `railroad.read_block_lengths()`
  (default path, a `note` field); `render_le_layout.py` takes `signals.json` from `layer_files.path`;
  `hand_lists.read_panel_items`, `read_retired_masts` and `read_sheet_rows` serve `panel_items.py`,
  `mast_plan.read_retired` and `build_staging_sets.read_sheets`. `infer_block_lengths.py` stays allowed as the file's
  writer (`WRITES`); `LATER` is gone; the Jython list is unchanged.
- **Tests:** `tools/hartlib/tests/test_drawing_keys.py`, `test_railroad` (the rule by ID),
  `test_cats_panel.LoopHalvesByID` (an owner's name reaches a loop half), `test_staging_device_map` and
  `test_build_layout_le` (the reader's messages), plus the helper's tests for each moved reader.
- **Outputs byte-identical:** `make panels CHECK=1 FULL=1` all current (the discovery stamp matches its base),
  `check_approved.py --check` all matching, `publish_draft.py --check` current, `test_bean_goldens` unchanged.
- **Code review (medium), fixed:** keys by `(level, id)`, the master's key; a part's block on its own level; an LCC
  alias with a key and a staging key with a plan "*" stop; `device_names` holds only generated names to the name
  form; `cats_panel.drawn_keys` stops on a device map made in memory instead of reading the committed one;
  `check_virtual_names` pairs blocks and detectors row by row and names rows with no id; a row whose `jmri_name` the
  owner gives (a swap) is held to no virtual-name rule; `MAIN_UPPER` is `level_devices.LEVELS`.
  `render_le_layout.py`'s signals path comes from hartlib, which the copied script in `test_layout_index_check` still
  imports (checked).
- **Open, for step 14:** a swapped main or upper detector still stops `read_device_map` (its occupancy
  `jmri_name` must be a virtual block sensor); step 14 swaps a turnout. The desks' `device_name`, `inside_os` and
  `level_signals` still match tracks through `DeviceMap` rows (tests build those by hand); a main detector's user name
  still does not follow its block's owner name (Step 7). Not this step's: `docs/ap/electrical/test_build_soq.py`
  fails on main too (57 detected sections in `block_lengths.csv`, the text says 43).

## Step 14 findings (2026-11-25)

- **A swap is one row edit.** A main or upper turnout or detector takes its physical name from its `devices_field.csv`
  row alone (`assignment` field, `jmri_name` and `system_name` its LCOS address). `device_map_rows.switch_shape` gives a
  switch's alias and feedback rows the shape of its turnout's assignment, not its level: a field turnout's LCC alias
  is a turnout of its own (MTT<dcc>) and its feedback rows are their planned M2S sensors (TWOSENSOR); a virtual one's
  alias names its bean and its feedback has none (DIRECT). `follow_swaps` applies it after the owner's rows go over
  the generated ones, and wires a swapped detector. My call (owner's rule of 2026-11-25): the feedback comes with the
  turnout, as staging's does, since `master_beans` stops a field turnout with none; a field row of its own overrides it.
  A field `jmri_name` with no field `assignment` sets the assignment the name gives (`owner_over`), so the swap is that
  one cell (code review).
- **Step 13's open items closed.** `read_device_map` holds a field occupancy row to its wired M2S sensor, a virtual one
  to its IS:HART:C3:B: sensor (`DeviceRow.assignment`, `swapped`); `check_virtual_names` exempts a field row by its
  column, so the invariant no longer reads the field file for swaps. The desks' `device_name`, `inside_os` and
  `level_signals` find blocks through `hartlib.drawing_keys` (`drawn_keys`), not the rows' `trial` cells, and an OS
  block by its drawing key's name, so an owner's name reaches them. `check_layout_facts.py` takes a swapped detector's
  field sensor (`field_sensors`).
- **Level tests that became column tests:** `switches.csv`'s row shape (`SwitchRow.by_os`: keyed by its OS block's ID,
  or by its half; a main or upper row keyed by its OS block still stops until its switches are bound to the live
  panels, as `staging_switches` reads its turnout on staging, code review), `staging_switches` and `hands` by that key, `build_hands.py`'s two passes, the Store split's rename
  instruction for any builder-made turnout or feedback row (`store_split`), the alias and feedback shape above.
- **Kept as real level facts, with why:** the drawing bands (`le_common.STAGING_LEVELS`, the staging band bound to the
  field, `build_cats_panel.BOUND_LEVEL`, `plan_lengths.MAIN_UPPER`); staging's plan graph, its masts
  (`device_map_masts`) and its drawing keys with no plan "*" (`drawing_keys`); staging's LCOS nodes as built
  (`build_device_map.Nodes`, the device-map invariant; wiring.csv's frozen rows already make main wiring data per
  device); interlocking areas (staging's are `stations.csv` desk codes); `wiring.csv`'s main and upper detectors keyed
  by plan key and its staging names read before the generated file exists (`wiring._Names`); bean comments
  (`device_map_rows.BEAN_LEVELS`: staging's come from its wiring columns, a different words path); the head rules that
  keep main and upper heads off MQTT until a head is swapped (`level_masts.WIRED_LEVELS`, `wiring.digicon_rows`: the
  next swap, a head, needs them to read the head row's assignment); the main and upper device-map view and mast name
  memory (`read_device_map`, `build_device_map.master_virtual_names`); level number checks.
- **The swap test.** `tools/schematic/tests/test_swap_by_row.py` adds two field rows to a copy (Switch 107 to M2T3308,
  BS 107 Loop 1 to M2S3305) and runs the device map, `tables_build.base`, every railroad invariant,
  `check_device_master.check_tables` and `check_bean_cells`, and the CATS desks on it (each desk build reads the
  drawing keys once per device map, code review): the beans are M2T3308 (TWOSENSOR
  on M2S3367 and M2S3368), MTT123 and M2S3305, the desks' IOSPECs M2T 3308 and M2S 3305; only those six rows, their
  beans and IOSPECs change. A scratch copy of the repo with the same two rows ran every `make panels` step:
  all passed but `sml-current` (the discovery base changed) and `check_approved.py` (the desk fingerprints hold the
  bindings).
- **Outputs byte-identical:** `make panels CHECK=1 FULL=1` all current, `check_approved.py --check` all matching,
  `build_tables.py --base-hash` unchanged, `test_bean_goldens` unchanged.
- **For the main session's sandbox swap:** two rows at the end of `devices_field.csv` (it has no main or upper row
  yet; level, then layer order), `2,,turnout,,switch:107,,field,M2T3308,M2T3308,,,,,,,,,,,,,,,,,,,,` and
  `2,,occupancy,,det:block:107B-107C#1,,field,M2S3305,M2S3305,,,,,,,,,,,,,,,,,,,,`; then `make panels` (it rediscovers
  SML on the Mac, writes the desks, then stops at `approved-desks`; `approved-live` is not reached),
  `make panelpro-test`, then restore every changed file from git.

### The sandbox swap (main session, 2026-11-25)

- **A turnout swap is one row.** On main at 5599f8d3, in a scratch worktree, one `devices_field.csv` row (level 2,
  turnout, `switch:107`, assignment field, `system_name` and `jmri_name` M2T3308) and `HART_TABLES_REVIEW=1 make
  panels`: every step ran, the SML discovery included; `tables.xml` binds Switch 107 to M2T3308 with its two physical
  feedback sensors (TWOSENSOR), and the startup LogixNG no longer sets it; the Layout Editor panel fingerprint is
  unchanged and only the desk fingerprints change (their bindings). `make panelpro-test`: ok (98 masts, 97 block
  sensors clear, main and upper turnouts 36 closed, 2 thrown). Reverted; nothing committed.
- **A detector swap builds but fails the smoke test.** With a second row (`det:block:107B-107C#1` to M2S3305) every
  build step passed, but `panelpro_smoke_test.py` (Jython, inside JMRI) stops: "main and upper blocks with no virtual
  occupancy sensor: Track 107 Loop 1". It still expects every main and upper block to have a virtual sensor; it must
  accept a block whose occupancy row is a field sensor before the first detector swap.

## Left after the plan

- Done (2026-11-25, follow-up): `panelpro_smoke_test.py` accepts a swapped (field) main or upper detector. The
  wrapper passes the main and upper blocks whose tables bind a non-virtual sensor (`HART_FIELD_DETECTED`, from
  `hartlib.level_devices.field_detected` over the `tables.xml` PanelPro loads); the smoke test holds each to that
  sensor, every other block to its virtual one, and a block with no sensor still fails
  (`jmri/layouts/hart/scripts/tests/test_panelpro_smoke_blocks.py`, `test_swap_by_row`'s smoke test).
- Done (2026-11-25, follow-up): a head swap is one row. `device_map_rows.mast_on_heads` puts a mast on its heads'
  JMRI names when one is a field head (heads found by ID: mast ID and place); `level_masts.read` takes a wired head
  that is its row's planned physical head at its place (`WIRED_LEVELS` is gone: staging's rows are bound as built);
  `wiring.digicon_rows` takes staging's wired rows and each main or upper head whose row is field (`field_heads`, its
  pins from the row's wiring text), so `digicon_masts` boots its SML disabled for `signal_coordinator.py`.
  `tools/schematic/tests/test_swap_head_by_row.py` swaps Mast 108LA's two heads (IH3332, IH3333) in a copy.
- **Done (2026-11-25):** `publish_draft --check` keys its drawing stamp on the whole `tools/hartlib/src` tree too
  (`STAMP_VERSION` 4): the view is built by `layer_files`, `track_names`, `devices` and what they import, so the
  whole tree is simpler and safer than a list; a `hartlib` edit costs one drawing.
- **Done (2026-11-25):** a staging crossover half can be renamed by its `devices_field.csv` row alone.
  `block_overrides.csv`'s `crossover_half` rows give the half's OS block ID (`os:23:A-1A`) and its letter in
  `parallel` (1 a, 2 b; `hand_lists.half_letters`); the generator names the half `OS Switch <n><letter>` (the field
  row's name wins, so `OS Switch 7` stays). The CATS half label (`cats_panel.half_label`), the desk plate of a renamed
  OS block (`os_plates`: its number and letter, not the first word of its name) and the desk-area label
  (`railroad_facts.os_label`) take the letter by ID. A trial in the worktree renamed OS Switch 23a, OS Switch 7 and
  OS Switch 35b in the field file only and ran every `make panels` step but `sml-current` by hand: the device master,
  `switches.csv`, `block_lengths.csv`, `masts.csv`, `tables.xml` and both desks took the new names, the labels stayed
  23A, 7A, 35B, and only the approvals (renamed labels; the Princess plate moved three cells) and the SML stamp went
  stale; reverted. `test_rename_by_id.RenameCrossoverHalf` pins the readers. Outputs on the committed data are
  byte-identical.
- Done (2026-11-25, main session): in a scratch worktree on 67b6d185, a detector (`det:block:107B-107C#1` to
  M2S3305) and Mast 108LA's two heads (IH3332, IH3333) swapped by three `devices_field.csv` rows alone: `HART_TABLES_REVIEW=1
  make panels` ran through SML discovery (only the desk approvals changed, their bindings), the mast became
  `two-searchlight(IH3332)(IH3333)`, and `make panelpro-test` passed (96 main and upper block sensors clear, the
  swapped block on its field sensor). Reverted; nothing committed.
- ~~`docs/ap/electrical/test_build_soq.py` counts 57 detected sections where its text says 43~~ Closed 2026-11-25: the SOQ is frozen and its tests are removed (owner); the layout documentation page reads its names by block ID from the device master.

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
