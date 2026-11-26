# Waking up a parked feature

Lists what must be rebuilt to wake a parked feature (NX, Dispatcher System, USS CTC) and every warning, skip and stale name the parked features leave behind.

Owner, 2026-11-21: when one of the parked features comes back, its scripts are rebuilt to read today's sources and
to generate their panels and pages from the data and the schematic. Until then, warnings that come only from a
parked feature are ignored in normal runs and listed here.

The parked data and its own notes stay in [`jmri/layouts/hart/parked/README.md`](../../jmri/layouts/hart/parked/README.md)
(what each feature holds, the snapshot file, the unpark steps for the tables, the hidden yard throats). This page
lists what has to be rebuilt, and every warning, skip and stale name the parked features leave behind.

## 1. What is parked

| Feature | Parked since | Where its data lives |
|---------|--------------|----------------------|
| Entry/Exit (NX): 36 pairs, 23 ISNX sensors, their panel slots | 2026-11-17 (helix-join release) | `jmri/layouts/hart/parked/tables_parked.xml` (feature `nx`) |
| Stock Dispatcher System: 197 sections, 187 transits, its panel, 377 sensors, the MoveTo and move-in-progress icons, its Logix and LogixNG | 2026-11-17 | `tables_parked.xml` (feature `dispatcher`); the 374 traininfo files and `dispatcheroptions.xml` in `jmri/layouts/hart/dispatcher/` |
| Dispatcher System: the 12 yard throat blocks, with their 10 yard-end masts and the 2 Dispatcher rear masts (36L, 40RB) | 2026-11-20 | `jmri/layouts/hart/data/schematic/retired_virtual_masts.csv`; the throat rows at commit 5a5bff0a (parked README, "Hidden yard throats") |
| USS CTC machine: `<ctcdata>` (20 code buttons), its Panel Editor panel, 264 sensors, its Logix and LogixNG | 2026-11-17 | `tables_parked.xml` (feature `uss`); `GUIObjects.xml` and icons in `jmri/layouts/hart/ctc/`; `data/mast_cells.csv`, `data/uss_board_cells.csv`, `data/uss_board_plants.csv` |
| Dispatcher System: occupancy lamps and station clusters (79 panel items) | 2026-11-17 off the staging panel; 2026-11-21 on every level, with their code and checks | `jmri/layouts/hart/parked/staging_panel_lamps.json`, `parked/occupancy_lamps_display_only.py` and its test; the two staging `le_labels` rules in `preferences.json` |
| Dispatcher System: the stations, the `; stop` at the end of 12 staging block comments and the master's `stop` column (empty, kept in the schema) | 2026-11-22, with the stations topic | The station list and the rule below |

`tables_parked.xml` is a frozen snapshot of the deployed tables at commit 3bd3ac64, before the helix was joined.
`python3 -m hartlib.parked check` (in `tools/check.sh`) holds it and `tables.xml` apart. The CATS desks, the signal
masts and Signal Mast Logic stay live.

## 2. Waking one up

### Rules that stand for every feature

- `tables.xml` is an output (ADR-029). Nothing is patched into it by hand or by a script, and no Store is copied
  over it. A feature that comes back is built from source data by `tools/schematic/build_tables.py` and the Layout
  Editor build, or its Store is taken back through `make tables-pull` and `tools/schematic/split_store.py`.
- The level is a column (ADR-030). A reader takes a device's kind, level and role from its device-master row (`devices_field.csv` + `devices_generated.csv`)
  (`layer`, `level`, `role`, through `hartlib.devices`), never from its name. Jython inside JMRI is the one
  exception, since it cannot import `hartlib`.
- Never run CATS CTC and the USS CTC machine at the same time, and never run the Dispatcher System from inside
  CATS.
- Never patch the Dispatcher System package (`CreateTransits`, `CreateIcons`, `Startup.py`,
  `TransitCreationTool`). Fix the source data that `tables.xml` is built from, so that stock Discover and Stage 1
  succeed. The known traps are in [`DISPATCHER_LAYOUT_HOOPS.md`](../../jmri/layouts/hart/parked/DISPATCHER_LAYOUT_HOOPS.md).
- Try the feature in a sandbox first (`tools/hosts/sandbox/README.md`), then get the owner's approval of any panel
  it changes.
- Names come from the device master (owner, 2026-11-22). A rebuilt script looks every track, block and mast name up
  in the master, `switches.csv` or `masts.csv` and types none. The parked scripts still hold their own copies, which
  `tools/audit/check_name_copies.py` keeps current but does not remove. On 2026-11-22 the copies typed in quotes were:
  `reconcile_dispatcher_stations.py` (48, the 12 stations and their icons), `check_bean_comments.py` (59 block
  comments in `BLOCK_COMMENTS`, the same text the master's `jmri_comment` holds), `nx_contract.py` (23),
  `ctc_logic_smoke.py` (23), `gen_ctc_track_plan.py` (18, board positions by block name), `build_ctc_full_15col.py`
  (14), `discover_nx.py` (11) and the `STATIONS` list in `panelpro_smoke_test.py` (12). The live audit reads none of
  them: `audit_panel_contracts.station_comments` takes the stations from the master's staging rows marked `stop`,
  which is none while the stations are parked (it still imports `nx_contract.py` for the ISNX names).

### Today's sources

A rebuilt script reads these and nothing older:

- The device master through `hartlib.devices` (role, level, cp, system_name, dcc, wiring, jmri_comment, notes):
  `devices_generated.csv` (written by the build scripts) and `devices_field.csv` (the owner's cells and Store-added
  devices), split on 2026-11-21 (ADR-029 amendment). The `pnm_*` columns, `public_name_map.csv` and the device-map
  files are gone.
- `jmri/layouts/hart/data/switches.csv`, one row per OS block on every level (`hand_source` says where the hand
  comes from). `switch_legs.csv`, `hands.csv` and `local_switches_main_upper.csv` are gone.
- `jmri/layouts/hart/data/schematic/block_overrides.csv` with its `kind` column (`split`, `track`,
  `crossover_half`), read by `hartlib.hand_lists.read_block_overrides`. It replaced `block_exceptions.csv` and
  `block_splits.csv`.
- `jmri/layouts/hart/data/schematic/masts.csv`, every level's masts, through `hartlib.level_masts`. It replaced
  `staging_masts.csv`, `main_upper_masts.csv`, `staging_masts_virtual.csv` and `le_signal_boundaries.csv`. Hidden
  masts are placed by rule (`mast_plan.py`; `build_device_map.py` writes their rows, `build_masts.py` the file).
- The helix is two blocks, Track Helix Outer and Track Helix Inner, named by their plan names in
  `plan_overrides.json` (`hartlib.railroad.read_helix_tracks`; `helix_tracks.csv` is gone). McKees Rocks and
  McKeesport are only labels, from the `track_labels` preference in `preferences.json[main_upper]`.
- `block_lengths.csv` `plan_in` for block lengths (the AnyRail plan 5.3c).
- The layer files `plan_overrides.json`, `preferences.json` and `signals.json`, read through `hartlib.layer_files`.

### Generated like the CATS desks and the Layout Editor panel

The CATS desks (`tools/schematic/build_cats_panel.py`) and the Layout Editor panel
(`tools/schematic/build_layout_le.py`) are drawn from the approved schematic and the data on every
`make panels` run ([pipeline 19](../../wiki/pipelines/schematic-panels.md)). Each parked feature should come back the
same way: a builder in `tools/schematic/` that writes its panel, its tables sections and its page from the data and
the schematic, with a `--check` mode in `make panels` and `tools/check.sh`, and an approved fingerprint where the
owner approves a panel. The hand-drawn and one-off scripts below are where its rules are written down today, not the
way to rebuild it.

### Entry/Exit (NX)

| Script | What it reads or does today | Rebuild against |
|--------|-----------------------------|-----------------|
| `jmri/layouts/hart/parked/apply_nx_layer.py` | writes ISNX sensors and slot bindings into `tables.xml` by default (`paths.TABLES_XML`) | a step of the Layout Editor and tables build, from `masts.csv` and the device master; never an edit of `tables.xml` |
| `jmri/layouts/hart/scripts/run_nx_discover.sh` | sets `blockrouting="yes"` in `tables.xml` by text replacement, then Stores NX Discover over `tables.xml` | Store to the pulled folder, as `run_panelpro_stage1.sh` does, and split it back with `split_store.py`; `blockrouting` from the template |
| `jmri/layouts/hart/scripts/discover_nx.py` (Jython) | finds block sensors by the `BS ` name prefix | the prefix is allowed in Jython; pass the sensor list in from a CPython step if it needs roles |
| `jmri/scripts/generate_nx_pairs.py` | writes a pair list for adding by hand | the pairs from Discover, kept as source data like `discovered_sml.stamp` |
| `jmri/layouts/hart/scripts/nx_contract.py` | names the ISNX system; still imported by `audit_panel_contracts.py` and `hartlib.parked` | keep, then take its names from the builder |

### Dispatcher System

| Script | What it reads or does today | Rebuild against |
|--------|-----------------------------|-----------------|
| `jmri/layouts/hart/scripts/run_panelpro_stage1.sh`, `run_dispatcher_stage1.py` | runs stock Stage 1 and Stores to the pulled folder; its header says to decide how Stage 1's output becomes source data before relying on it | sections, transits and traininfo as source data the tables build writes, refreshed by a sandbox Stage 1 run and split back |
| `jmri/layouts/hart/scripts/check_bean_comments.py` (a repair step of the Stage 1 wrapper) | now only checks the staging head comments in the device master; it no longer writes comments | drop the step: `build_tables.py` writes every comment from the device master |
| `jmri/layouts/hart/scripts/reconcile_dispatcher_stations.py` | the 12 stations as a hard-coded `STATIONS` list of block names, cluster icons placed from a reference panel | the stations from the block comments or a `stations.csv` column, the clusters from `staging_panel_lamps.json` through `panel_items.json` |
| `jmri/layouts/hart/parked/polish_hart_layout_editor.py` | puts Stage 1's lamps and labels back after the Store; finds block sensors by the `BS ` prefix | gone once the lamps and labels are drawn by the build; any reader that stays takes the role from the device master |
| `jmri/layouts/hart/parked/retarget_dispatcher_traininfo_transits.py`, `repair_dispatcher_traininfo.py`, `fix_traininfo_detection.py`, `run_panelpro_traininfo_repair.sh` | edit the 374 traininfo files, which name the 3bd3ac64 transits and masts; the retarget script defaults to the Pi's `tables.xml` path | traininfo generated from the transits the build writes, with HEAD_AND_TAIL detection set by the generator |
| `jmri/layouts/hart/parked/occupancy_lamps_display_only.py` | the lamps' display-only check, out of `tools/check.sh` | back into `tools/check.sh` with the lamps |
| The hidden yard throats | Stage 1 needs the 12 throat blocks and their 12 masts (the rows of `retired_virtual_masts.csv` marked "restore on unpark") | a rule in `mast_plan.py` (staging's rows: `device_map_masts.py`) and `block_overrides.csv` rows, as the parked README describes |

**The stations (parked 2026-11-22).** The stock Dispatcher System has no station table: a station is a block whose
JMRI comment is "stop" or ends "; stop". Until 2026-11-22 the device master's `stop` column was `yes` on 12 staging
blocks and the builders added "; stop" to their comments: Track K-1, Track K-2, Track East Lead, Track EH-1, Track EH-2,
Track EH-3, Track Scale, Track Barn, Track W-1, Track W-2, Track Helix Outer and Track Helix Inner (commit 8066d2a6 has
them). `build_device_map.py` also marked the main and upper helix rows a stop at their main-level switch (Switch 131A
and 131B; `helix_stops`, removed the same day). To bring stations back, the owner first decides them for every level
(the stations topic), then sets `stop` to `yes` in `devices_field.csv` (for a generated row, in its builder) and puts "; stop" back in those rows'
`jmri_comment`; `check_device_master.py` and `audit_panel_contracts.py` hold `tables.xml` to the column.

Put back with it: `audit_panel_contracts.py` `EXPECTED_GRAPH`, the counts in `panelpro_smoke_test.py`, the two
checks taken out of `tools/check.sh` (`reconcile_dispatcher_stations.py --check --no-sync` and
`parked/polish_hart_layout_editor.py --check`), the South Yard `lamp_columns` in `preferences.json[staging]`
`le_labels`, and the station clusters as plugin `extras`.

### USS CTC machine

| Script | What it reads or does today | Rebuild against |
|--------|-----------------------------|-----------------|
| `jmri/layouts/hart/scripts/gen_ctc_track_plan.py` | draws the board from `uss_board_cells.csv` and `uss_board_plants.csv` (frozen from the hand-wired CATS desk on 2026-11-15), `mast_cells.csv` (masts before ADR-024) and `switches.csv`; refuses to write the checkout's `tables.xml` while parked | a board drawn from the schematic and `masts.csv`, as the CATS desks are; the frozen grid files retired |
| `jmri/layouts/hart/scripts/uss_switch_only_columns.py`, `cleanup_uss_ctc_leftovers.py` | `--apply` refuses to write `tables.xml` (ADR-029); both print SKIPPED while parked | lever columns and CTC sensors written by the tables build from `switches.csv` and `masts.csv` |
| `jmri/layouts/hart/scripts/build_ctc_full_15col.py` | built the machine that is parked; unsafe to re-run (ADR-005) | not rebuilt; the generator replaces it |
| `jmri/layouts/hart/scripts/ctc_logic_smoke.py` | names the masts of 2026-11-17 | the masts from `masts.csv` |

`gen_ctc_track_plan.py` and `uss_switch_only_columns.py` must keep working while parked: `check_layout_facts.py` and
the CATS desk tests read the USS board grid through them.

## 3. Warning log

Every warning, skip, failing or stale check, stale name and known gap that comes from a parked element, as of
2026-11-21 (origin/main 8fca5a18, full `tools/check.sh` with the portal build and `make panels CHECK=1`, both on the
Windows box). Normal runs print none of these as a warning.

| # | Where | What it says | Feature | On wake-up |
|---|-------|--------------|---------|------------|
| 1 | `jmri/layouts/hart/scripts/tests/test_gen_ctc_track_plan.py` (`setUpModule`); the unclosed `Image.open` calls at `gen_ctc_track_plan.py:298`, `:302` and `:1217` | `ResourceWarning: unclosed file <...gif>`, eight per run in `tools/check.sh`; now hidden in that test module only | USS | close the PIL images in the generator (`with Image.open(...)`), fix its bare `assert`s in `main()` (project-health hand-off), and remove the filter |
| 2 | `jmri/layouts/hart/scripts/tests/test_ctc_signal_heads.py:69`, `:92` | two tests skipped: the board's `SIGNALS` predate the ADR-024 staging masts (Mast 67/68, head counts, 8L/40L letters) | USS | redraw the board's signals from `masts.csv`, take the `skipTest` out |
| 3 | `jmri/layouts/hart/scripts/reconcile_dispatcher_stations.py:749`, run by `test_reconcile_dispatcher_stations.py` | `SKIPPED: the Dispatcher System is parked ...`; the test now captures it, so `tools/check.sh` no longer prints it | Dispatcher | the skip goes away with `PARKED` |
| 4 | `reconcile_dispatcher_stations.py:783` | `SKIPPED deployment ...: the Dispatcher System is parked there` (only when run by hand with sync) | Dispatcher | as 3 |
| 5 | `jmri/layouts/hart/scripts/uss_switch_only_columns.py:221`, `cleanup_uss_ctc_leftovers.py:72` | `SKIPPED: the USS CTC machine is parked ...` (only when run by hand) | USS | as 3; their `--apply` also refuses `tables.xml` (ADR-029), so rebuild them as build steps |
| 6 | `gen_ctc_track_plan.py:1315` | `<path>: not changed, the USS CTC machine is parked` | USS | goes with `PARKED` |
| 7 | `gen_ctc_track_plan.py:35`, `:1332` | guards `tables/tables.xml`, a repo-root path that no longer exists (before ADR-007) | USS | drop the guard; the generator never writes `tables.xml` |
| 8 | `jmri/layouts/hart/parked/polish_hart_layout_editor.py` (tested by `scripts/tests/test_polish_hart_layout_editor.py:274`) | `SKIPPED: the Dispatcher System is parked` | Dispatcher | goes with `PARKED`; the script itself goes once the build draws the lamps |
| 9 | `tools/hosts/deploy/ship_mac.sh:30`, `:134` | every deploy prints `Dispatcher traininfo parked: not installed; ... left as it is` and `USS CTC icons parked: not installed; ... left as it is` | Dispatcher, USS | recorded, not changed; the lines go when the folders ship again |
| 10 | `tools/check.sh` (`sml-invariants`, `parked` jobs) | `OK: Entry/Exit parked, no ISNX sensor in tables.xml` and `ok: tables.xml holds no parked element or name; parked: nx (82 items); dispatcher (955 items); uss (292 items)` | all | information lines, left as they are; `tools/audit/check_sml_invariants.py:52` and `hartlib.parked check` turn into the feature's own checks |
| 11 | `tools/check.sh` | `reconcile_dispatcher_stations.py --check --no-sync` and `parked/polish_hart_layout_editor.py --check` taken out (both printed SKIPPED); `parked/tests/test_occupancy_lamps_display_only.py` out of the suite | Dispatcher, lamps | put back (section 2) |
| 12 | `tools/audit/check_layout_facts.py:731` | the `mast_cells.csv` check against the USS board grid is off while the board is parked | USS | runs again on unpark; `mast_cells.csv` needs the ADR-024 masts first |
| 13 | `tools/audit/check_name_copies.py:76`-`:111` (`ALLOW`) | old names allowed in `tables_parked.xml`, `dispatcher/traininfo/`, `ctc/GUIObjects.xml`, `data/mast_cells.csv`, `discover_nx.py`, `nx_contract.py`, `parked/apply_nx_layer.py`, `retired_virtual_masts.csv`, `ctc_logic_smoke.py`, `build_ctc_full_15col.py` | all | each entry goes when its file is regenerated with current names |
| 14 | `jmri/layouts/hart/scripts/audit_panel_contracts.py` `EXPECTED_GRAPH`, `panelpro_smoke_test.py` | expect 0 sections and transits and no parked window while parked | Dispatcher, USS, NX | put the counts back |
| 15 | `jmri/layouts/hart/parked/tables_parked.xml` | the snapshot matches the 3bd3ac64 geometry (helix unjoined, the throats still there) | all | refresh by Stage 1 or NX Discover in a sandbox, as data the build takes in |
| 16 | `jmri/layouts/hart/dispatcher/traininfo/` (374 files) | name the 3bd3ac64 transits and the masts of that day | Dispatcher | regenerate after Stage 1 on the rule-built masts |
| 17 | `jmri/layouts/hart/parked/staging_panel_lamps.json` | one block is gone from the device master: `Track K-1 West` (a throat block, dropped 2026-11-20) | lamps, Dispatcher | restore the throat or move the lamp to Track K-1 |
| 18 | `jmri/layouts/hart/data/schematic/retired_virtual_masts.csv` | the 19 hidden masts dropped 2026-11-20, with their system names; 12 are the Dispatcher's (yard-end and rear masts, marked "restore on unpark"), the other 7 went for reasons of their own (helix ends, anchor and stub-leaving masts) | Dispatcher | restore the 12 by a rule in `build_masts.py`, reusing their system names |
| 19 | `jmri/layouts/hart/data/schematic/preferences.json` `staging.le_labels` `extra_steps`, `extra_follow` | the two label rules kept only for the parked station clusters (EH-1 to EH-3 step alike, W-2 follows W-1); `test_build_layout_le.py:961`, `test_le_cutover.py:493` hold them | lamps, Dispatcher | used again when the clusters return as plugin `extras` |
| 20 | `preferences.json` `staging.le_labels` `lamp_columns` (removed); `test_le_cutover.py` lamp-offset check (retired) | the South Yard lamp column is gone | lamps | give `lamp_columns` back and the lamp-offset check with it |
| 21 | the station clusters as plugin `extras` (the retired `le_overlay.station_extras`) | without them 14 block contents icons sit elsewhere than they did with the clusters (OS Switch 7, OS Switch 9, Barn, EH-2, EH-3, East Lead, East Lead East, K-1, K-2, McKees Rocks, McKeesport, Scale, W-1, W-2) | lamps, Dispatcher | give the clusters to the plugin again |
| 22 | `jmri/layouts/hart/scripts/render_le_layout.py:248`, `:344`, `:446` | finds MoveTo sensors and OS blocks by name prefix; kept on purpose (source-data hand-off row 8): it draws any panel file, including old and trial panels whose blocks the device master lacks | Dispatcher | keep the prefix test, or pass roles in when it draws only current panels |
| 23 | `jmri/layouts/hart/scripts/check_bean_comments.py` | check-only since R9c; still a "repair" step in `run_panelpro_stage1.sh:83`, where it no longer restores comments | Dispatcher | drop the step (section 2) |
| 24 | `wiki/pipelines/public-names.md:23` | lists `check_bean_comments.py` as a step that writes comments | Dispatcher | update with the Stage 1 rebuild |
| 25 | `jmri/layouts/hart/parked/DISPATCHER_LAYOUT_HOOPS.md:75` | says the Stage 1 wrapper restores bean comments through `refresh_bean_comments.py` | Dispatcher | update with the Stage 1 rebuild |
| 26 | `jmri/layouts/hart/ctc/DISPATCHER_GUIDE.md:62`, `:63`, `:140` | Digicon-era OS names "OS K-2", "OS McKeesport", "OS K-1", "OS McKees Rocks"; today OS Switch 37 and OS Switch 39 | USS | rename with the guide when the machine returns |
| 27 | `docs/ctc/TURNOUT_STATE_SOURCES.md:11`, `:12`, `:43`, `:44`, `:59` | the same Digicon-era OS names for switches 114 and 115 | USS | rename to OS Switch 37 and 39 |
| 28 | `docs/ctc/SIGNAL_FACING.md:100` | "OS McKees Rocks/OS McKeesport" | USS | rename to OS Switch 37 and 39 |
| 29 | `jmri/layouts/hart/parked/apply_nx_layer.py`, `run_nx_discover.sh` | write `tables.xml` directly | NX | rebuild (section 2) |
| 30 | `jmri/layouts/hart/scripts/discover_nx.py`, `parked/polish_hart_layout_editor.py` | read block sensors by the `BS ` prefix | NX, Dispatcher | Jython may keep it; CPython takes the role from the device master (ADR-030) |

Checked and clean: `jmri/scripts/check_hart_phase02.py` prints nothing from a parked feature. `make panels CHECK=1`
prints no parked line. The portal build prints no parked line; the tables page shows the parked features as a note
(`www/scripts/tables_page.py` `PARKED_NOTE`), which is content, not a warning.
