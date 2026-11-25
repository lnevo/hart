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
| 2 | `id` column | 0.5 day | The builders write an ID on every row (decision 1); `check_rows` holds it unique per level. Only `devices_generated.csv` changes. **Done (2026-11-24):** see [Step 2 findings](#step-2-findings) |
| 3 | The name store | 1.5 days | Generator names every track from the plan; `hartlib.track_names` keeps the owner's names by ID and gives them to the plugin; readers by ID; a check stops a name in `plan_overrides.json`. Drawings byte-identical. **Done (2026-11-24):** 3a the store ([Step 3 findings](#step-3-findings)); 3b the readers by ID ([Step 3b findings](#step-3b-findings)) |
| 4 | Owner file keyed by ID | 1 day | `devices_field.csv` rekeyed on `(level, id)`; `user_name` becomes an owner cell. The build prints new and gone IDs against the last generated file and stops as decision 3 says; a rename lists the Operations Pro copies (decision 5) and warns on a mast rename (decision 6). **Done (2026-11-25):** see [Step 4 findings](#step-4-findings) |
| 5 | Files keyed by ID | 1.5 to 2 days | `wiring.csv`, `block_lengths.csv`, `block_numbering.csv`, `block_overrides.csv`, `main_lines.csv` and switches.csv's staging legs key on device IDs; their names come from the name store, so a rename touches no row. **Done (2026-11-25):** see [Step 5 findings](#step-5-findings); 5b, `preferences.json` and `stations.csv` by block ID: [Step 5b findings](#step-5b-findings) |
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

## Step 2 findings (2026-11-24)

- `hartlib.device_ids` holds the grammar: `switch:<n>`, `dcc:<n>`, `fb:<n>:N|R`; `block:<ends>` from the plan ends of its strands (`block:1B-3A:1/2`, `block:107B-107C#1`, `block:1C-5A#1+1C-5A#2`); `os:<n>`, a staging crossover half `os:<n>:A-<leg A end>` and the 225 corners by schematic leg (`os:225:D`); `det:<block id>`, `spare:<system name>`; a home mast `mast:<switch or half label>:<leg>:<dir>`, others `mast:<facing block id>:<dir>`; heads `<mast id>:top|bottom|single`; panel lamps `panel:status:<system name>` (they share one `panel_items.json` item). 772 IDs, unique per level; rows with no level have none.
- **Open for step 7:** staging's turnout, alias and feedback rows still come from the owner's rows and `wiring.csv`, so their switch number is read from the user name (`wired_id`; `check_switch_ids` stops the build if a number has no staging OS block in the plan). Step 7 derives them from the plan.
- **Open for step 12:** both halves of a staging crossover carry the label "7", so their home masts are `mast:7:A:west` and `mast:7:A:east`, unique only by direction; the uniqueness check stops a clash. Step 12 (one mast step) can key a half's mast like its OS block.

## Step 3 findings (2026-11-24)

- **The first check failed, then was fixed with the owner (2026-11-24).** Every track name came from the plan except
  the numbers of parallel tracks (two tracks between the same switches): `mast_rule.track_names` ordered them by drawn
  row. They are now ordered by their ends' plan labels and legs (`mast_rule.plan_order`, the order of their block IDs),
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
- **Open for step 12:** a mast's letter (210LA, 210LB) is still ordered by drawn row, so after the renumbering Mast 210LA
  faces Track 209 Spur 2. Mast names were left alone (a rename needs SML discovery and approval, decision 6).
- **Open for step 5:** `main_lines.csv` and `milepost_route` still name staging tracks (`7@East Ext`), and
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
- **Open, not 3b's:** `publish_draft.check_digest` keys the drawing stamp on the data, the plugin and the field file,
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
- **Open for step 5:** a staging rename still breaks the files keyed by name (`wiring.csv`'s detector rows,
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
- **Open:** a field `jmri_comment` is free text (W-1's still says "Brick yard Track W-1"); a rename does not reach it.

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
