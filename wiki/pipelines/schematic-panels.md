# Pipeline 19 — Panels from the schematic

Every panel is drawn from the approved schematic: the switch hands, the signal plan, the device map for the main and
upper levels, the published schematic and station sheets, the CATS desks and the Layout Editor panel (built as
a candidate beside `tables.xml`). The schematic-maps plugin (`external/model-railroad-skills`) solves the sheet; the scripts in
`tools/schematic/` turn it into each output. This replaced the AnyRail pipeline ([jmri-anyrail.md](jmri-anyrail.md)).

**Status:** Live. The Layout Editor cut-over (2026-11-16) and the CATS desks (ADR-023) are built this way.

**Layer files (level-unification step 3, 2026-11-20):** `jmri/layouts/hart/data/schematic/` holds one file per layer
kind, `plan_overrides.json`, `preferences.json` and `signals.json`, each with `"_sections": true` and a section per
sheet (`staging`, `main_upper`, the input names in `publish_draft.INPUTS`). The plugin reads the sections itself
(schematic-maps 0.1.49); `plan_overrides.json` holds only the owner's hand edits, and what the three builders write lives in `plan_generated.json` (same sections, T6b): `layer_files.merged` is the view every output is drawn from (hand values win), and `layer_files.view` gives the plugin a merged folder under the shared cache; every hart script reads and writes them through `hartlib.layer_files`, which keeps the JSON
format in one place and stops on a missing section or an old `<sheet>.<kind>.json` left beside the file.

**One block process (level unification step 5 parts 1 and 2, owner 2026-11-20):** `tools/schematic/block_layer.py` makes
the block layer of every level from the drawing: an OS block per switch (a single crossover's halves each their own
when they have their own detectors, staging 7, 23 and 35), a block per track named by the plan's name, else by its end
switches, halves from `block_overrides.csv` kind `split` (every level, the owner's choice: 227-241, staging's K-1 and K-2), helix blocks
by the same rule (each helix track's two pieces, staging's and main or upper's, cut at the level split, carry one plan
name, Helix Outer or Helix Inner, so they are one block, "Track <plan name>"; `plan_overrides.json` gives the names,
the staging helix ends and the main_upper `helix` map, read by `hartlib.railroad.read_helix_tracks`, which replaced
`helix_tracks.csv` on 2026-11-21), and parts. A part is a piece of track inside another block: a device-master row (`devices_field.csv` + `devices_generated.csv`, read by `hartlib.devices`) with
`part_of` naming that block, role `part`, no occupancy row or detector of its own (the device maps skip it:
`hartlib.devices.OUT_OF_MAPS`). That is the standard way to put a short piece in an OS
block. The rule, on every level: a track between two switches under 50 cm (`LINK_CM`) is part of the lower-numbered
switch's OS block (at a double crossover, the corner block of its leg), but where a home mast stands at a switch's
points facing it, part of the OS block at its other end, so the block boundary is at the mast (`block_layer
.masted_block`; a mast at both ends stops the build). On every level a part is a JMRI block, layout block and
track on the panel whose occupancy sensor is its OS block's (owner, 2026-11-20: main and upper's 25, staging's 14).
Main and upper's are numbered by the Layout Editor build; staging's carry their names in their rows
(`build_device_map.part_bean_names`: IB:AUTO:<n> and ILB<n>, the next free number, never shifted), since the
generator writes staging's beans. The masts read a part inside its OS block (`staging_device_map.os_layer`, as
`block_layer.Layer.bands` on main and upper) and face the JMRI block next to them (Mast 32R faces Track 29-31).
A part's block contents icon is optional on every level: `optional_block_contents` in `preferences.json` lists
every level's parts (the plugin takes the list from the preferences only; `test_blocks_every_level` holds it to
the device master). A piece that `block_overrides.csv` marks `inside` stays inside its OS block with no JMRI or
layout block of its own (owner, 2026-11-20: the two halves of 35-39, in OS 35b and OS 39, so Mast 36RB's route
to Mast 68 is shorter than the wrong way round the Princess balloon, which JMRI's discovery otherwise follows
until its ttlSize and drops the pair). `data/schematic/block_overrides.csv` (a `level` column, rows of any level, a
`kind` per row) is the one file of the owner's hand facts about blocks: kind `split` (a track parted into two blocks
at its turnback, the owner's choice, not a rule), kind `track` (the wiring facts where the wiring says otherwise:
13-15 in OS 15, 23-31 in OS 31, 35-37 in 35a, a part per end for 1-3 and 35-39; `inside` yes on a track row keeps
the piece inside its OS block) and kind `crossover_half` (the crossover halves with detectors of their own).
`mast_rule.read_block_overrides` reads it and checks every row's shape for its kind, naming the file and line; it
replaced `block_exceptions.csv` and `block_splits.csv` (2026-11-21). What a reader sees for a track can differ from its
plan name: `preferences.json[main_upper]` `track_labels` (the schematic-maps plugin's sheet-wide preference, since
plugin 0.1.50) maps a plan name to the label drawn, McKees Rocks for Helix Outer and McKeesport for Helix Inner until
the layout expands. The plugin draws it on every output it makes: the schematic and station sheets (helix letters
follow the labels, so H1 is still the outer track), the Layout Editor panel and the CATS desks; `levels_page` reads the
same key for the track-plan article. The desks' bindings stay keyed by plan name (Helix Outer, Helix Inner). `build_device_map.py` writes staging's block and occupancy rows
from it (written_by `build_device_map.py`), each built on the owner's row of its name in `devices_field.csv`: the
system and layout-block names, comment, stop, notes, detector and an OS block's control point; the node, wiring and
the detector's part of the comment (`{occupancy}` in the field text) come from `wiring.csv`, so a moved pin changes
no hand file. A staging block change made in PanelPro is carried by hand into those three data files and the field
row.

Main and upper wiring goes one way: the device map's rule proposes it in `devices_generated.csv` on every build, `make wiring-freeze` is the only writer into `wiring.csv` (a control point's proposal copied in as wired rows), and for a frozen control point `build_device_map.py` reads `wiring.csv` (`hartlib.wiring.held`) and proposes nothing. `check_wiring_frozen.py` (in `check.sh`) fails on any other change to `wiring.csv`. The step stamps follow what each step reads (traced), so `wiring.csv` is an input of the device map because it reads it, and the freeze is no step.

The device master is two files (ADR-029 amendment, built 2026-11-21): `devices_generated.csv`, every row the builders
make, written only by `build_device_map.py`, `build_masts.py` and `panel_items.py`, and `devices_field.csv`, the
owner's cells keyed by level, layer and user name (`hartlib.devices.FIELD_COLUMNS`) and a Store's level-less devices.
`hartlib.devices` merges them into the one view every reader gets. A builder reads the owner's cells from the field
file, never back from its own last output; its one read-back is its name numbering (`devices.allocated_names`: a
part's block numbers, a virtual mast's ordinal), so a name never shifts. A builder that would drop a key the field
file names stops: rename or remove the field row. `split_store.py` writes only the field file. Main and upper write their part rows the same
way (25 links). Block lengths: JMRI's block takes `block_lengths.csv`'s `plan_in` on every level (`plan_lengths.py`,
main and upper's rows too); a measured length is for speed profiling only. To review a candidate before the owner
approves its staging panel: `build_layout_le.py --as-live --review`, `build_tables.py --review` and
`HART_TABLES_REVIEW=1 run_sml_discover.sh` (sandbox). Pinned by `tests/test_blocks_every_level.py` and
`tests/test_block_layer.py`.

## Run

```bash
make panels           # rebuild every output, in order; stops at the first failure
make panels CHECK=1   # check every output; names each stale one
make desks            # only the CATS desks, then validate them
```

`tools/schematic/build_panels.sh` runs the steps in the order they depend on each other:

| Step | Script | Writes |
|------|--------|--------|
| hands | `build_hands.py` | the hands of `switches.csv`'s plan rows, from the plan graph (owner rows are left alone) |
| staging-sets | `build_staging_sets.py` | in `plan_generated.json`'s `staging` section the `control_points`, `stations` and `station_tracks` keys, in `preferences.json`'s `staging` section the `detail_sheets` key, from `stations.csv` (the control points are its desk areas: the stations that share a `desk_code`, a nested station's switches its own) and `sheets.csv`. Detail: [Row staging-sets: what it checks](#row-staging-sets-what-it-checks). |
| main-route | `build_main_route.py` | the `main_route` key of `plan_generated.json`'s `main_upper` section and, for staging, `name_main` (which tracks of the `name` edit are main, by position) and `milepost_route`. Detail: [Row main-route: how the routes are found](#row-main-route-how-the-routes-are-found). |
| plan-lengths | `plan_lengths.py --check` | nothing: stops when `block_lengths.csv`'s `plan_in` no longer matches the AnyRail plan 5.3c (the track runs need the private plan file; without it only the OS rows, from `parts.json`, are checked). Run `plan_lengths.py` by hand to write them |
| device-map | `build_device_map.py` | `devices_generated.csv` (reading `devices_field.csv`): the levels 2 and 3 rows, staging's block and occupancy rows (the one block process, below), and the `control_points` and `stations` keys of `plan_generated.json`'s `main_upper` section, which the schematic reads |
| masts | `build_masts.py` | `masts.csv`, every level's masts with a `level` column (hartlib.level_masts), from the mast and head rows of the device master (it writes staging's into `devices_generated.csv`, a wired mast's node and head's notes from `devices_field.csv`): staging's rows planned here by the mast rule over its device map (with their plan facts, where the drawing puts each), main and upper's written by `build_device_map.py`. After device-map, whose rows it reads |
| signals | `build_signals.py` | `signals.json` (a section per sheet) from the plan graph and `masts.csv`: staging's rows by their plan facts, main and upper's placed from the plan graph. After masts, so one run draws the masts it writes; nothing before it reads `signals.json` (device-map and masts give the same outputs with every signal dropped from it), so there is no cycle |
| head-plan | `build_hart_signal_heads.py --wiring-only` | `jmri/layouts/hart/output/signal_head_plan.csv` from `wiring.csv`'s wired heads (`--check` compares in memory). The CATS desks read its templates, so it runs before `cats` |
| schematic | `publish_draft.py` | the schematic sheets and station pages |
| le-cutover | `build_layout_le.py --as-live` | the cut-over candidate `output/trial/tables_cutover.xml`, every level from its device map and the panel's own items from `panel_items.json`, and the staging candidate it holds, `tables_cutover_staging.xml`. Detail: [Row le-cutover: how it is built](#row-le-cutover-how-it-is-built). |
| approved-candidate | `check_approved.py le-candidate` | nothing: stops when the cut-over candidate drifts from the approved fingerprint |
| sml-current | `check_sml_current.py` | nothing: stops when `data/schematic/discovered_sml.stamp` (the sha256 of the discovery base `run_sml_discover.sh` discovered on) is not the base the sources give now (`build_tables.py --base-hash`). Run the discovery on the Mac, then `make panels`. Runs in both modes, before `tables` |
| tables | `build_tables.py` | `output/tables.xml`, the file PanelPro and CATS load (ADR-029: an output): the template, the staging beans of the device master, the Layout Editor build, the discovered Signal Mast Logic (`data/schematic/discovered_sml.xml`, written only by `run_sml_discover.sh`) and the Digicon boot rule, in a fixed envelope. Detail: [Row tables: check and Store handling](#row-tables-check-and-store-handling). |
| signals-sync | `sync_signals.py --check` | nothing: stops when the heads and masts of any level in `tables.xml` differ from `masts.csv`. It runs after `tables`, which generates them from the device master and the Layout Editor build |
| device-master | `check_device_master.py --check` | nothing: checks every level of the device master against `tables.xml` and the schematic, after `tables` writes it, with one set of rules for every level (a rule that reads a file only one level has is that file's, not a level test). Detail: [Row device-master: which rows are read how](#row-device-master-which-rows-are-read-how). |
| cats | `build_cats_panel.py` | `cats/panels/HART_CTC.xml`, `HART_ABS.xml` and `HART_CTC.bindings.json`; it runs after `tables`, whose turnouts, sensors and masts the desks read. The bindings for every level come from one builder, `cats_panel.py` (facts in `cats_panel_facts.py`, header and plate in `cats_panel_dress.py`). The control point plates (BRICK, PLANE, BARN, EAST END, PRINCESS; owner, 2026-11-21) come from `stations.csv`'s `desk_plate` column: each in the free cell nearest its switches' plants, on both desks; the desk never grows, and a plate with no free cell stops the build (`cats_panel_dress.station_plates`) |
| approved-desks | `check_approved.py cats-ctc cats-abs` | nothing: stops the run when a desk no longer matches the fingerprint the owner approved |
| approved-live | `check_approved.py le-panel` | nothing: stops when the live panel in `tables.xml` drifts from the approved fingerprint |

Each step reads the plugin's cache (`.cache/hart/schematic` in the main checkout, shared by every worktree), so a run after a small change redoes only what that
change reaches. `tools/check.sh` runs `--check` on the hands, main route, masts, signals sync, staging map, signals, device map and CATS steps, and the approved fingerprints (`check_approved.py`); `make panels
CHECK=1` checks them all.

### Row staging-sets: what it checks

Stops with file, line and station on an unknown switch, a staging switch in no desk area, stations that partly overlap, a switch in two nested stations, a missing or double desk code, or a sheet naming a station that is not there

### Row main-route: how the routes are found

Both from `main_lines.csv`, one file with a `sheet` column (staging or main_upper). Main and upper: worked out from its main_upper rows (the two main lines by helix end, end switch, turnback and double tracks) and the plan graph; stops when a stretch has two equally short ways or a pair of switches has two tracks nobody declared; staging: from its staging rows, each line naming the junctions it passes (a track must join each to the next; `count` yes marks the lines the mileposts run along)

### Row le-cutover: how it is built

Both are built on the generator's base (`hartlib.tables_build.base`: `data/tables_template.xml` and the staging beans of the device master; ADR-029), never on `tables.xml`. A band's level comes from its plan-overrides section; a level the base holds beans for (`tables_build.GENERATED_LEVELS`, staging) binds them, every other level's beans the build adds, virtual. One mast check (`le_checks.check_masts`) and one bound-names check (`le_tables.check_bound`) cover every level. The viewing trials (`tables_layout.xml`, `tables_layout_staging.xml`) are retired (owner, 2026-11-17): `build_layout_le.py` without `--as-live` stops with an error

### Row tables: check and Store handling

`--check` (also in `tools/check.sh`) fails on any difference. A PanelPro Store is never copied over it: `make tables-pull` keeps it in `media/pulled-stores/` in the main checkout, and `split_store.py` splits it into the template and the device master (R9d: the owner's settings kept, device changes reviewed, the repo wins on what the build makes). `--discovery-base` writes it with no Signal Mast Logic, for `run_sml_discover.sh`

### Row device-master: which rows are read how

The staging rows that carry no `written_by` (turnouts, feedback) are kept by hand and read against the staging band here, as are staging's block and occupancy rows, which `build_device_map.py` writes; `masts.csv` and the staging mast and head rows are generated (masts above), and the main and upper rows are `build_device_map.py`'s, whose `--check` reads them against the drawing

## A memory, clock or setting change

For a memory or clock change, use `tools/schematic/template_edit.py` instead of a Store. It edits `data/tables_template.xml` (memories, the clock, blockrouting, Signal Mast Logic delay and the default turnout and block speeds) in the form JMRI writes, then runs `build_tables.py` and its `--check`: `template_edit.py list`, `memory add|set|remove`, `clock set rate=2.0`, `setting set blockrouting=no`. `--dry-run` shows the change and writes nothing. A memory's value is not kept in the template (a Store drops it). LogixNG parts and anything else a Store brings still go through a pull and `split_store.py`.

## After a run

- `tables.xml` changed: `make panelpro-test`, then deploy (AGENTS.md close-out).
- A schematic drawing changed: refresh the evolution GIF (`tools/schematic/evolution.py`).

Detail: [`docs/ops/schematic-system-draft.md`](../../docs/ops/schematic-system-draft.md)

## Inputs: three layers

Every output reads the same three kinds of input, kept apart under `jmri/layouts/hart/data/schematic/` (moved here from the schematic-maps hand-off, 2026-11-18). Only the first two are the product.

1. **Plan overrides.** Facts about the railroad that AnyRail's plan does not hold or holds wrongly. They override the plan and every output uses them (schematic, CATS, station pages, Layout Editor).
2. **Generation.** Rules that turn plan plus overrides into a clean, stretched-out main line and track plan with no hand input.
3. **Preferences.** The owner's choices about how one sheet looks. Optional, applied last, never needed for a correct drawing.

Test of the separation: with layer 3 switched off, layers 1 and 2 alone draw all three levels with no crossings or overlaps, the main line straight through every switch, and yard ladders stepping diagonally with their tracks level. The plugin (model-railroad-skills PR #18, 2026-11-13) reproduces the approved sheet from the three layers with no hints.

### Layer 1: plan overrides (fed over the AnyRail plan)

Source of track: AnyRail's JMRI export of plan 5.3c (5.3b until Phase 2, 2026-11-19), read by the plugin's `plan` command into the track graphs in `jmri/layouts/hart/data/schematic/inputs/` (recipe in `docs/ops/schematic-system-draft.md`), with the parts list from the plugin's `anyplan` command (the `.any` file read directly; `anyplan --parts`) and the helix from the plan: each level's graph takes its share of a helix track up to the -5 cm cut (`anyplan --cut -5 --stubs`). T names are 5.3c part numbers (re-keyed from 5.3b by position). The `.any` file and its XML export stay in `~/Documents/Layout/`, outside the repo. Heights come from the `.any` file, matched to the export by position (the 5.3b export is a 2664 x 3840 px panel at about 12.0 px per inch of plan, within 0.4% of the plugin's default; the plugin fits the scale by least squares against the parts list).

| Override | Staging | Main and upper |
|----------|---------|----------------|
| Switch numbers for plan parts | T45=3, T124=1, T114=5, T49=15, T71=17, T96=19, T73=21, T65=25, T109=27, T84=29, T40=31, T106=33, T57+T126=23, T54+T95=35, T55=39, T78=37 | Owner's numbers (2026-11-14, both levels renumbered by the rule 2026-11-19), a `relabel` edit in `plan_overrides.json`'s `main_upper` section: main level 101 to 131, upper level 201 to 245, odd only, left to right as drawn on the approved sheet, the main line first at the same position, then top to bottom. Detail: [Main and upper switch numbers: crossovers and renumbering](#main-and-upper-switch-numbers-crossovers-and-renumbering). |
| Not built | None since 5.3c (it has no crossover T41/T43) | — |
| Built but not in the plan | None since 5.3c: it draws the Switch 7 crossover (T33, T139), Switch 13 (T135), Switches 11 (T137) and 9 (T136) with EH-1 to EH-3, all left-hand; they are relabelled and named like the rest | — |
| Moved | — | None since 5.3c: it draws 223 (T331) on the 4.25 in track where it is built |
| Heights | — | None since 5.3c: the peninsula is at 10.8 cm (4.25 in) in the plan |
| Track names | Main West, West Ext, East Ext, Main East, East Lead, Brick-Plane, Scale, Barn, S-R, S-1 to S-4, K-1, K-2, W-1, W-2, EH-1 to EH-3 | None yet |
| Track ends | W-1, W-2 and EH-1 to EH-3 bumpers | — |
| Helix tracks | From Switch 39: McKees Rocks (H1). From Switch 37: McKeesport (H2) | From T210: McKees Rocks (H1). From T281: McKeesport (H2). Owner confirmed |
| Main route | Main West, West Ext, Brick-Plane, East Ext, Main East, East Lead, the two throats from 35 to 37 and 39, both helix tracks | H2, T281, T311, the rise to T294, diverge to T316, round the west loop by T310, T283, T261 to T307 and T289, T331, both tracks to the double crossover, round the peninsula loop by T268 and T270. H1, T210, T215, T194, diverge at T200 on the long track to T165, T181, T178, T166, round the loop at T204. The T289–T294 crossover is not main |
| Stations | Brick (1, 3), Plane (5), Barn (7), South Yard (15–21), East End (23–33), Princess (35–39), Engine House (9–13, nested in Barn), the desk areas of `stations.csv` | None yet |
| West end | W-1 | — |

Also a reader rule, not an override: two track ends on the same spot in the export are one track and are joined (two pairs in 5.3b, one of them the main level's loop at T204).

Hands and legs of the staging switches 5.3b lacked were taken from the Layout Editor panel in `tables.xml` (owner, 2026-11-13); plan 5.3c draws them the same way:

| Switch | Hand | Straight leg | Diverging leg |
|--------|------|--------------|---------------|
| 7 | Left-hand crossover | Scale to Barn; East Ext to Main East | The crossover |
| 13 | Right | Barn | Switch 11 |
| 11 | Left | EH-1 | Switch 9 |
| 9 | Right | EH-3 | EH-2 (its normal route: the panel's continuing sense is thrown) |

Where they sit along their runs comes from the plan 5.3c lengths in `block_lengths.csv` (`plan_in`, `plan_lengths.py`; owner, 2026-11-20): every block is drawn to its plan share, and the measured lengths never move a mast.

#### Main and upper switch numbers: crossovers and renumbering

A crossover is one number with A and B (A the left half), numbered where its A half stands: the three-way's halves pair with T196 and T202 as 101 and 103, T5/T10 and T194/T20 are one crossover each on the ground (121, 125), the helix-top crossovers T215/T311 and T210/T281 are main level (127, 131), the double crossover is one part (225). Upper renumber (2026-11-19): 207 and 209 swapped, the 213 crossover became 211 and 211 became 213, 231 and 233 swapped, 239 became 241, the 241 crossover 243, and 243 became 239. The plan joins 121's and 125's halves leg C to leg B (AnyRail's leg B of T10 and T20 is the diagonal), and the plugin (schematic-maps 0.1.42, `crossover_halves`) pairs lettered halves joined B to C as one single crossover: each half is closed on its through leg (121B and 125B on their leg C) on the Layout Editor panel and the CATS desks, and the log asks for their machines to be wired reversed. The T-names stay as aliases, so the other layer files still use them

### Layer 2: generation rules

Already rules in the spike:

- One band per level; a run that joins two levels is cut and shown as lettered connectors. Level by height (below 5 cm: main; above: upper).
- Each switch faces left or right; runs that must double back are folded, choosing the folds that are U-turns on the layout, and keeping the choice that draws with the fewest faults.
- Tracks are ordered top to bottom from each switch's hand; a loop's two tracks are stacked by which way the loop bends.
- A double crossover's two tracks sit on neighbouring rows.
- Spare length along a band is shared in proportion to real track length; switches joined by short links move as blocks; track ends and folds travel with their switch; a long track always gets a level run; a connector gets one short cell.
- The drawing is checked for lines that cross or lie on top of each other, and the solver adds clearance until none do.

### Layer 3: the owner's preferences for this sheet

- Turnbacks: staging's Brick-Plane is drawn as the turnback (`turnbacks` in `preferences.json`'s `staging` section, plugin 0.1.45), as approved; with the 5.3c lengths the cheapest drawing would turn Main West back instead.
- Order from the top: staging, main, upper (owner, 2026-11-14, REV 3). Helix at the east end of every band (a 180-degree turn of the two upper bands was tried and undone; east and west on the looped mains are to be settled later by following the main line, perhaps on the CATS diagram; ADR-022 stands meanwhile).
- All bands the same width; main band 95% and nudged left; upper band nudged so H2 sits under H1.
- Helix marks: three-turn coil with H1 or H2 and "Helix to …". Connectors between main and upper: circled A and B.
- The helix-top switches T285 and T251 are drawn on the upper band (they are at height 0), T199 and T175 on the main band.
- Main level: the loop at T196 above the main, the three yard tracks below it (drawn sides flipped for T196, T155, T160, T162, T194, T183, 50, 51).
- Lengths: staging: Plane to the right of Brick, Switches 7 and 13 further east, Switch 13 to 15 one cell, drawn short like T274 to T237 (owner, 2026-11-14; the cells given to East Lead, now 7, and West Ext), long yard tracks. Main: yard throat level with the loop's edge, a long run between T1 and 12, room between T160 and T165. Upper: T237 to T300 short, T262 to T285 five cells.
- NYAMR drafting style, Letter landscape, title block, station brackets under staging.
- Facing letters (owner, 2026-11-14, plugin 0.1.3; **off since REV 5**, both files `false`, see ADR-022 amendment): when on, `facing_letters` prints R or L after each switch number, R when the points meet an eastward train first (the sense of the mast names). East follows the main route in timetable order: on staging as drawn (west end W-1); on the main and upper levels outward from the helix, so the helix is their west end even though the sheet keeps it at the right, and those bands carry a small EAST arrow on each main run. On the main level the balloon at T196 and the three yard tracks are the east end (Neville Island), toward the helix is westward to West Yard. The double crossover 225 prints no letter; crossover halves did (REV 4: 101AL/101BR, 103AL/103BR, 119AL/119BR, 129AL/129BR, 135AR/135BL). To check if the letters come back: 121L (T15, a wye) and 227L (T253, where the upper main turns back round the peninsula loop).
- Capacity (owner, 2026-11-14, REV 4, plugin 0.1.5): counts are in 50 ft cars (7.4 in each), from whole-track lengths with no room left for an engine, and printed after the name, or alone on an unnamed track. Every level uses the plan's lengths (since 2026-11-20: staging's copy of the measured lengths, `track_lengths_in`, is gone), with each unnamed yard track summed over its pieces. Each station bar shows a total, counted at the track's west end. Barn now spans Switches 7, 9, 11 and 13 so the engine house counts there; Scale stays with Plane.
- Title block fields (owner, 2026-11-14): `date`, `revision` and `sheet` in `preferences.json`'s `main_upper` section print in a ruled column at the right of the title box (NOV 14, 2026 / REV 1 / SHEET 1 OF 1; plugin 0.1.2). `publish_draft.py` sets today's date and adds 1 to the revision whenever the drawing itself changes; `--check` never changes them.

## Decisions that hold

- **Rules (2026-11-17):** stock JMRI SML discovery is the reference; fix the tables, never patch JMRI or the Dispatcher System. Staging stays as the owner approved it (`approved_staging.sha256` guards it). Main and upper objects stay on internal names (`IT:HART:C3`, `IB:C3`, `IH9` heads, `IS:HART:C3` virtual sensors), numbers appended, never shifted. Read the data before building; take before and after pictures (`tools/hosts/sandbox/panel_snapshot.sh`); the sandbox is set up from `tools/hosts/sandbox/README.md`.
- **Side by side (owner, 2026-11-14, ADR-023):** a new generated panel, desk or crew page is written beside the live one and replaces it only on the owner's approval, then in one cut-over.
- **Switch hands (owner, 2026-11-14):** main and upper hands come from the plan geometry (the `plan` rows of `switches.csv`, written by `build_hands.py`, `--check` in `check.sh`; 50 switch halves, 225 has a row and no hand as a double crossover; a row the owner sets to `hand_source` `owner` is never rewritten, 2026-11-21). The halves of crossovers 121 and 125 have opposite hands in `switches.csv` (121A L, 121B R; 125A R, 125B L), and that is real, not an error: the plan lays T1 and T14 with their straight route on the diagonal, so their leg B is the crossover's diagonal and the hand is read from it. Staging Switches 9 and 13 stay as the Layout Editor has them (both drawn right-hand; 9 normal is EH-2, 13 normal is Barn); `switches.csv` `hand` stays L for both, the physical hand.
- **Helix joined (owner, 2026-11-17, release approved in a sandbox PanelPro and CATS):** staging's end bumpers at McKees Rocks and McKeesport are joins; `approved_staging.sha256` was unchanged. The system schematic and station sheets carry no DRAFT mark (revision 10; files keep their `-draft` names so links stay).
- **CATS desks:** main and upper are CTC on the CTC desk, so a route up the helix stops at Mast 132RA (main, via 131-H1) or Mast 132RB (upper, via 131-H2); the ABS desk is all ABS. Every main and upper block has a virtual sensor (`IS:HART:C3:B:<block>`); a physical detector is swapped in through the device map's `jmri_name` column.
- **Switch 225 (owner, 2026-11-17):** the CATS desks show OS Switch 225a to d, one block per corner, each bound to its planned detector, plus a middle block for the crossing cells with no detector (CATS cannot put a block boundary where two blocks meet on one side of a crossing). The middle stays dark; occupancy shows in the four corners and CATS still locks the crossing. Revisit only if the diamond is gapped as its own section when 225 is wired. The 107 Loop is two desk blocks.
- **Layout Editor geometry (2026-11-17):** the geometry once set by constants in `build_layout_le.py` is layer 3 preferences the plugin reads (`le_shift`, `le_crossover_angle`, `le_labels`, `le_band_labels`, `le_longer_straights`, `le_title_clear`, `le_stretch` in `preferences.json`'s `staging` and `main_upper` sections). The panel's and the CATS desks' windows (`le_window`, `cats_window`) are not set there: since 2026-11-21 both come from `main_upper`'s `host_screen`, the layout hosts' 1920 x 1080 screen less a 48 px taskbar, derived in `tools/schematic/host_screen.py`. `build_layout_le.py` is split into `le_common.py`, `le_names.py`, `le_checks.py` and `le_tables.py`, with the staging approval fingerprint in `approval.py`. Check crossover slants in real PanelPro or with the plugin's JMRI port (`tests/jmri_xover.py`), never from the XML attributes alone.
- **Layout Editor rules are preferences; bands are found by level (owner, 2026-11-20):** each sheet's section of `preferences.json` holds its Layout Editor label and look rules. Staging's `le_labels` (`extra_steps`, `extra_follow`, `name_columns`, `name_steps`, `lamp_columns`) go through the plugin's one reader (`le_labels.options`), the same reader as main and upper's `le_labels` and `le_band_labels`. Staging's place against the left edge of the three-level panel is `le_band_align` (`{level: side}`), which `le_common.le_band_align` reads for every section and passes on as the plugin's page `band_align`; the published sheet does not read it. HART code finds a band by its level and height (`below`) from `plan_overrides.json`, through `le_common.find_band` (`base_band` and `base_keys` for the staging candidate's band), never by its title. A band with no level, two bands at one level and height, and a rule naming a level no band of its section is at each stop the build. Tests: `tools/schematic/tests/test_band_find.py`.
- **Parked:** NX, the Dispatcher System and the USS CTC (see [`STATUS.md`](../STATUS.md)); unparking means refreshing `parked/tables_parked.xml` per its README.
## Background

- **Goal:** turn the AnyRail plan into a logical (not physical) view of the railroad and draw maps from it: the system schematic, the station pages, the CATS desks and the Layout Editor panel. The generic reader, layout engine, style and skill are in the public `model-railroad-skills` plugin (`plugins/schematic-maps`); HART's names, numbers and finished maps stay in this repo.
- **Owner decisions (2026-11-13):** the system schematic came first and the other outputs followed; the tool proposes stations, tracks and roles in draft files and the owner edits them; the look is NYAMR drafting style (black line work, heavy main and light secondary track, capitals, little colour); Letter landscape.
- **Timetable direction** follows the route, not the room ([ADR-022](../decisions/ADR-022-timetable-direction-follows-route.md)): eastward from staging stays eastward on every level, so every band has east on the right.
- **Exports of the owner's plan may be public.** The custom objects and buildings in the plan may not (their author holds the copyright), and the `.any` files stay out of every repo.
- **Rules the references agree on:** the main is one horizontal line per level; other tracks leave at 45 degrees and run parallel; the main is heavier than sidings and yard tracks; hidden track is dashed; a direction legend on every sheet; "To X" at open ends; a title block with date and revision; black on white first.
- **References:** the North Western Vermont schematic (NER Coupler 303, pp. 22-23: rows across a page, yard tracks with capacity, yard limit marks); the NYAMR [orthogonal schematic](https://davebarraza.wordpress.com/wp-content/uploads/2021/02/nyamr-orthagonal-schematic-210210-1.pdf) (one band per level, helix letters, station bars, title block), [Physical Characteristics Book](https://davebarraza.wordpress.com/wp-content/uploads/2026/04/nyamr-physical-characteristics-book-260415.pdf) (one location per page, capacity in 50-foot cars) and [deck track maps](https://davebarraza.wordpress.com/wp-content/uploads/2022/05/nyamr-overhead-view-2022.pdf); the [St Charles Branch crew track chart](https://appalachianrailroadmodeling.com/stcharlesbranch/?p=796) (multi-deck, helix on one straightened line); the PRR [Walbridge interlocking sheet](https://www.redoveryellow.com/position-light/PRR_Diagrams/walbridge.gif) (switch and signal numbering); Luteberget and Johansen, "Drawing with SAT", and [railplot](https://github.com/luteberget/railplot) as prior art for automatic schematics (licence not confirmed, so no code reuse).

History of how this was built (spike, cut-over, hand-offs, the stage plan and as-built notes against plan 5.3b): [`archive/wiki/projects/schematic-maps-handoff.md`](../../archive/wiki/projects/schematic-maps-handoff.md) and [`archive/wiki/projects/schematic-maps.md`](../../archive/wiki/projects/schematic-maps.md).


**Stamps.** Each writing step (not the guards) has a traced stamp in `.cache/panel-stamps/` (gitignored, per checkout; `tools/schematic/panel_stamps.py`, the hook and read sets in `tools/audit/traced.py`, shared with `check.sh`). A step runs under a hook that logs every repo file its Python processes (the step and its Python children, such as the plugin's `bin/schematic`) open, probe and find absent, and list; after a pass the stamp holds that read set with its hashes, the output of each read-only git command it ran, and a key over its command, outputs, all hartlib and `tools/schematic` code, the plugin's commit and the Python. While all of it matches, the step prints `current, skipped`, so an edit to one data file re-runs only the steps that read it (`sheets.csv`: staging-sets alone, 7 s instead of 46 s). `.cache/` reads are left out (keyed on content; a link from the plan-merged view counts as a read of its data file). A step that runs a program the hook cannot see records nothing and always runs, unless `STEPS` names it (`schematic`: Chrome, which prints the drawn sheet, an output). `make panels FULL=1` ignores the stamps and records; `panel_stamps.py why <step>` names the first difference. `tests/test_panel_stamps.py` runs each step under both the trace and an independent audit hook and fails when the trace lacks a read the audit saw.
