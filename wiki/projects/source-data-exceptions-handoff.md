# Hand-off, 2026-11-20: what still builds the layout besides the plan and structured data

For a fresh agent session. Read `AGENTS.md`, then this page, then
[`pipelines/schematic-panels.md`](../pipelines/schematic-panels.md).

## Why

The owner's goal (2026-11-20): the AnyRail plan 5.3c and structured data build the layout. Exceptions, one-offs
and rules read from names or free text should go. The 5.3c clean-up branch (`agent/claude/plan-5-3c-cleanup`) moved
these to plan or data:
- lengths;
- the helix blocks;
- the hidden staging masts;
- the yard throats;
- the device-map facts;
- the main/upper main route;
- the block numbering;
- the 35-37 short track.

A read-only audit of that branch then listed what is left. This page is that list, for the owner to review and
order; rows 1 to 7 are done.

**Owner decision (2026-11-20): the track-plan page is regenerated from 5.3c (item 6), not retired.**

## What stays: railroad facts the plan cannot hold

- **Wiring and addresses:**
  - `devices.csv` (the one device master, ADR-029: the device maps and `public_name_map.csv` were folded into it);
  - `lcos_nodes.csv` (every level's nodes);
  - `wiring.csv` (the physical wiring: every wired device, and the detectors the owner placed on main and upper);
  - `switches.csv`.
- **The owner's choices:**
  - switch numbers (the relabel maps);
  - control points and stations;
  - `block_numbering.csv`;
  - the helix track names (`plan_overrides.json`, was `helix_tracks.csv`) and their labels (`track_labels`);
  - `block_overrides.csv` (was `short_tracks_staging.csv`, then `block_exceptions.csv` and `block_splits.csv`,
    merged 2026-11-21);
  - `main_lines.csv`;
  - the milepost origin (Switch 1 is MP 5.7).
- **Measured facts:**
  - the timed lengths (`block_lengths.csv` `measured_in`);
  - the physical hands of Switches 9 and 13.

## Progress (2026-11-20)

Done on branch `agent/claude/source-data-rows-2-3-7`, with every desk, panel and fingerprint unchanged:
- **Row 1:** every override and preference ref outside the `relabel` edit is a switch number, or `number@track` at
  a crossover half (about 95 refs). Six stayed part numbers: the first track named at each half of Switches 7, 23
  and 35 in the staging `name` edit, since no track had a name yet for `@track` to use.
- **Row 2:** `mast_dir_pattern` and `signals_planned` deleted, the `move` hand branch gone from `build_hands.py`,
  comments corrected (127 and 131 at the helix top since the 2026-11-19 renumber).
- **Row 3:** a mast's direction is the `dir` column (east or west) of the device maps and `masts.csv` (its level column), set where the mast rule places it; no reader parses it from the name.
- **Row 7:** a turnout's class (#6 or #8) comes from the angle of its leg ends; the Peco part table is gone.

Merged as #754. Then, on branch `agent/claude/source-data-rows-4-5`, also with nothing drawn changed:
- **Row 4:** staging's control points (the desk areas of `stations.csv` since 2026-11-20), stations (`stations_staging.csv`), detail
  sheets (`sheets_staging.csv`) and main lines (`main_lines_staging.csv`) each have one master file (on 2026-11-20
  these became `stations.csv`, `sheets.csv` and `main_lines.csv`, one file for every level, #769 and #775);
  `build_staging_sets.py` and `build_main_route.py` write every other copy (the older `data/control_points.csv`
  went on 2026-11-20, its readers now build its rows from the master), and `make panels CHECK=1` fails on drift.
- **Row 5:** the main/upper hand lists (running, signalled spurs, split tracks, detector pins) are keyed by
  `switch_a,switch_b` (and `parallel` or `half` where needed), so a renumber no longer strands them. The
  `le_band_labels` names in `preferences.json` (main_upper section) stay track and block names (owner, 2026-11-20): a main or
  upper name is built from its end switches, so a renumber changes a switch pair just as it changes the name, and a
  stale name already stops the build (`hidden_names`) or leaves an icon unplaced, which fails the label check.

Then, on branch `agent/claude/label-refs-by-switch` (schematic-maps 0.1.47), with nothing drawn changed: those six
reach their half as `number@neighbour` (`23@1`: the half a track joins to Switch 1), so no part number is left
outside the `relabel` edit; `test_override_refs.py` checks each finds the half its part number did.

Row 6 (track-plan page, regenerated from 5.3c: `levels_svg.py` draws all three levels from the `.any` through `anyplan.py`) is merged from another session (#749). Rows 8, 9 and 10 wait (owner, 2026-11-20).

## What is left to remove, ranked

Rows 1 to 7 are done (#749, #754, #757 and the label-refs branch, above); the table keeps the open rows with their original numbers.

| # | Item | Where | Replace with | Effort |
|---|---|---|---|---|
| 8 | **Closed 2026-11-21.** Kind and level read from name prefixes ("Track ", "OS Switch ", "BS ", "Mast "), the crossover half from A or B, a balloon loop from a name ending " Loop", the level from a band title's first word | hartlib (`level_devices`, `railroad`), `le_names`, `staging_device_map`, `build_device_map`, `build_cats_panel`, `mast_rule` | `kind`, `level` and `role` columns on the device-map rows | several small steps. Done in #787 for the mast rule and CATS: band level (explicit `level` in the plan overrides), crossover half (no suffix test) and loop (the track's flag). The `le_common`/`le_names` title words went in #817 (bands found by level and height); the last two, `block_layer`'s level-to-drawing branch and `build_device_map`'s first-word band key, went on 2026-11-21 (the drawing is the plan-overrides section that holds the level; the key is the plugin's `band_key`). Part A (2026-11-21, owner: fix it now, reversing level unification step 9's "left as they are"; CPython only): the readers take a device's kind from its row through `hartlib.devices` (`row_role`, `is_os`, `index()`), with an error naming the file and line when a row is missing or has no role and no fallback to the name: `check_layout_facts` (crossover corners), `plan_lengths` (OS blocks), `staging_device_map.load_masts` (turnouts, not LCC aliases), `freeze_wiring` (OS detectors, LCC aliases), `write_inventory.block_name` (the `blocks` column only), `export_track_lengths`, `build_layout_index` (os block), `lcos_mqtt_mimic` and `build_lcos_signal_manager_plan` (detectors and turnouts), and `build_device_map` keeps a carried staging row's own role. All outputs are byte-identical. Part B (2026-11-21) closes the row: the writers state every row's role, so nothing stamps one from a name. `devices.role_of` and `block_role` are gone; `master_row` takes the row's own `role` and stops on none, and `railroad.DeviceRow` has no role default. `build_device_map` gives each row the role of what it builds (a line block's from its track's ends, `line_role`), and `build_masts` gives each mast the role the rule placed it with (`with_roles`). `build_masts.file_rows` takes an anchor mast's OS block from the protected block's row. `le_names.named_bands` takes a track block from the master's role (`index().role`, a part among the line roles). `le_tables.level_sensors` and `cats_panel.virtual_sensor`/`planned_sensor` find a block's occupancy row by its `blocks` column (`DeviceMap.occupancy`), not by building the sensor's name. All outputs are byte-identical. Kept on purpose: display text and name relations (a switch number or a crossover's middle block read out of an OS block's name, trial placeholders, label text, a head's name from its mast's, `Mast <key>` keys in `build_masts`, `mast_plan` and `build_signals`, and `le_checks`' `Switch <n>`); `level_devices.block_key`/`occupancy_user`, the owner's 2026-11-17 rule that builds a sensor's name from its block's name, with the checks that hold the rows to it (`railroad_facts.read_device_map`, `check_virtual_names`, `railroad_invariants`' helix sensors); a mast's JMRI class read from its system name (`IF$vsm:` is a VirtualSignalMast: `level_masts`, `sync_signals`, `le_checks`, `build_signals`; masts.csv has no role column); the build-owned beans of tables.xml found by the naming rule (`sync_signals.is_mast`/`is_head`, `le_tables`' `is_level_name`: a stale bean has no row left to ask); `le_tables.block_sort`, whose order numbers the main and upper block system names and reads names `block_numbering.csv` maps, some retired with no row; `le_names.device_names`' name check (a grammar check, not a kind); `render_le_layout`, which draws any panel file it is given (old, archived and trial panels whose blocks devices.csv lacks), so a role lookup would fail or need the name fallback this row forbids, and its OS test only picks label text; the speedmatch guard list (`make_job.guard_for` guards every `BS ` sensor the tables hold, listed in devices.csv or not), the text scanner `check_name_copies`, and the Jython inside JMRI |
| 9 | Device facts kept three times (addresses, DCC, node comments in `public_name_map.csv`, `device_map_staging.csv` and `tables.xml`); the DCC group parsed from `tables.xml` comments; build-owned items found by comment and name | hartlib `names.py`, `le_tables.py` | One master with the others generated; an explicit owner column | 1–2 days. The device maps and the name map were retired in R9e (ADR-029: `devices.csv` is the one master, `tables.xml` generated from it, `written_by` the owner column). The pnm-columns PR (2026-11-21) removes the last copy: the six `pnm_` columns of `devices.csv` are gone and every reader reads `cp`, `system_name`, `dcc`, `wiring`, `jmri_comment` and `notes`; staging's line blocks carry their station in `cp`; Head 6LB's note is the 2026-11-19 one; `lcc_turnout_contract.py` takes the DCC address from the `dcc` column, not a comment (`check_layout_facts.py` still reads it out of the built comment, as a witness of `tables.xml` against the master). Left: `le_tables.py`'s build-owned items found by name, which row 8 part B kept on purpose: a stale bean in tables.xml has no devices.csv row left to ask, so the naming rule is how the build knows it owns the bean |
| 10 | Drawing workarounds in preferences | Dead entries removed 2026-11-21 (owner: dead entries only; [below](#row-10-dead-entries-2026-11-21)): `level_leg` 233 and 237, four main/upper `min_cells`, upper `le_name_room`, `crowded_block_contents`, staging `shorten`. Left, each live: `level_leg` 115, 235, 239, `le_shift`, the `le_labels` name groupings, `turnbacks`, the other `min_cells`, `le_longer_straights` and the rest listed below; `extra_steps`/`extra_follow` act only on parked items. Done before: `le_tight_crossovers`/`le_split_crossovers` (101/103) replaced by the schematic-maps 0.1.48 three-way rule (#785) | Plugin rules (for example: choose the level leg when the straight-level rule would collide), owner to discuss | 1–2 days |

### Row 10: dead entries (2026-11-21)

Owner, 2026-11-21: remove only the `preferences.json` entries whose removal changes no output, and replace nothing
with a plugin rule. Each entry was taken out alone and everything rebuilt (`make panels`, `levels_page.py`,
`map_revision.py`), then compared byte for byte with the state before it: `tables.xml`, the CATS desks and bindings,
both Layout Editor candidates in `output/trial/`, the approved fingerprints, the schematic SVG and PDF, the station
sheets, the crew map pages, `crew.json`, `publications.json` and `track-plan.html`. A drawing change shows as a
revision bump, so it cannot slip through.

**Removed** (dead alone, and dead all together, `make panels FULL=1`): `main_upper` `level_leg` 233 and 237;
`main_upper` `min_cells` 111-101B, 105-103A, 111-117 and 221B-127B; `main_upper` `le_name_room` Upper;
`main_upper` `le_band_labels` Upper `crowded_block_contents` (OS Switch 235's icon is placed now without it);
`staging` `shorten` 13-15.

**Kept, dead alone but not together:** `staging` `min_cells` 5-7 Scale and 5-7 East Ext. Take both out and the
staging drawing and its Layout Editor panel change, so both stay. Staging `shorten` is dead with either one of them.

**Kept, parked only:** `staging` `le_labels` `extra_steps` and `extra_follow` change nothing today ("the panel has no
caller's items"): they step the occupancy lamps and station buttons, which are parked (`parked/README.md`) and may
come back.

**Kept, live.** What each removal changes:

| Entry | Without it |
|---|---|
| `main_upper` `level_leg` 115 | main level redrawn (sheet, main-level sheet, LE candidate); the approved-candidate fingerprint fails |
| `main_upper` `level_leg` 235 | `plan_lengths.py` stops: `le_longer_straights` finds no climb at switch 235 |
| `main_upper` `level_leg` 239 | upper level redrawn; the LE build stops (no clean spot for OS Switch 233's block contents) |
| `main_upper` `min_cells` 105-103B, 107, 121B-119B | main level redrawn; LE candidate changes, the approved-candidate check fails |
| `main_upper` `min_cells` 221A-223 | upper level redrawn; the LE build stops: panel shape 1.642 against the window's 1.743 (`le_stretch`) |
| `main_upper` `shorten` 221A-223 | upper level redrawn; the staging guard stops the LE build |
| `main_upper` `le_longer_straights` | LE candidate changes (Track 235-243's bend); the approved-candidate check fails |
| `main_upper` `levels.assign` 127B | `plan_lengths.py` stops (a label reaches no track) |
| `main_upper` `levels.assign` 131B | `build_signals.py` stops (block error) |
| `main_upper` `le_band_labels` Main `numbers_below` | LE candidate: SW-101's number moves; the approved-candidate check fails |
| `main_upper` `le_band_labels` Main `hidden_names` | the staging guard stops the LE build |
| `main_upper` `le_mast_room` Main, Upper | LE candidate changes (mast room); the approved-candidate check fails |
| `main_upper` `le_name_room` Main | LE candidate changes (track names on main); the approved-candidate check fails |
| `main_upper` `band_shift` Main, Upper | system sheet only (bands move); every other output the same |
| `main_upper` `band_width` | system sheet and LE candidate; the approved-candidate check fails |
| `main_upper` `edits` (flip) | main level flipped: sheet, LE candidate, `devices.csv`, `signals.json` |
| `staging` `le_shift` | the staging LE panel changes; it is no longer the approved one |
| `staging` `le_labels` `name_columns`, `name_steps` | the staging LE panel's S-R or EH-3 label moves; it is no longer the approved one |
| `staging` `turnbacks` | `plan_lengths.py` stops: track 1A-23A has no block row |
| `staging` `min_cells` 7-13, 1-5, 21-25 S-3/S-4, 33-35 | staging drawing and station sheets redrawn; the staging LE panel is no longer the approved one |
| `staging` `station_side` | staging drawing redrawn; the LE build stops (the title is placed off the panel) |
| `staging` `le_band_align` | the staging guard stops the LE build |

Not tested: the owner's look settings (titles, dates, `capacity`, `detail_sheets`, `host_screen`, the `cats_*` and
`le_stretch` sizes, `le_crossover_angle`, `track_labels`) and `optional_block_contents`, which
`test_blocks_every_level` holds to the parts in `devices.csv`.

Also open, smaller:
- (done 2026-11-20: `le_signal_boundaries.csv` retired; the deploy audit reads `staging_masts.csv` instead);
- (done 2026-11-21: the screen sizes are one `host_screen` setting, the layout hosts' screen; `le_window` and `cats_window` are derived from it);
- the band names and the 5 cm cut kept in `plan_overrides.json` (main_upper section) `levels` "until B2";

## Not checked by the audit

- the plugin's label, band and CATS internals beyond its signal reader and mileposts;
- some function bodies (`build_layout_le.py`, `le_tables.py`, `le_checks.py`, `publish_draft.py`, `panel_items.py`);
- the scripts that run inside JMRI;
- the parked folder.

## How to take it on

1. The owner reviews the table and orders it.
2. One PR per row, each through `make panels`, `./tools/check.sh` and, where the panel changes, one owner approval.
