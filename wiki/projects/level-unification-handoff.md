# Level unification: hand-off (2026-11-20)

## Why

The owner (2026-11-20): too many places keep staging and the main and upper levels in separate files, scripts and
processes. Staging was built and approved first (ADR-024, ADR-027) and main and upper were added on their own path.
The goal: one file per kind of fact and one builder per job, the level (or sheet) a column, and no hand-drawn facts
where a rule can do the work.

Out of scope here, because the [project health plan](project-health-handoff.md) covers them: the one device master
and `tables.xml` as an output (row 9, R9a to R9e, which also retire `sync_staging_signals.py`), the name-prefix rules
(row 8) and the drawing workarounds (row 10).

## Owner decisions (2026-11-20)

- **Masts:** no hand-drawn facts where possible; one rule for every level. Decided item by item after the
  comparison (see [Masts](#masts)).
- **Sheets:** the drawings stay two sheets (staging; main and upper). Files that hold facts for both get a `sheet`
  (or `level`) column, a section per sheet, not a file per sheet. Preferences stay per sheet, as a section of one
  preferences file (step 3).

## Where the split is (2026-11-20)

| Area | Staging | Main and upper |
|---|---|---|
| Plan input and sheet | `inputs/staging.json`; the `staging` section of `plan_overrides.json`, `preferences.json` and `signals.json` (step 3) | `inputs/main.json`; the `main_upper` sections of the same three files |
| Groupings | `control_points_staging.csv` (station groups with desk codes), `stations.csv`, `sheets.csv` (level 1 rows only so far), `interlockings_staging.csv` (the signal rule's control points) | `control_points_main_upper.csv` (the signal rule's control points, also drawn as the stations); detail sheets by hand in `preferences.json`'s `main_upper` section |
| Hand lists | `short_tracks_staging.csv` | `running_tracks_`, `signalled_spurs_`, `split_tracks_`, `local_switches_main_upper.csv`; short tracks by a rule (`SHORT_CM` in `build_device_map.py`) |
| Masts | `build_staging_masts.py`: `mast_rule.masts()` plus intermediates, anchor masts, virtual masts, interlockings | `build_device_map.py`: `mast_rule.masts()` plus running, spur and split lists, double-crossover corners; `build_main_upper_masts.py` copies them to `main_upper_masts.csv` |
| Builders | `build_staging_sets.py`, `staging_device_map.py` | `build_device_map.py` (the CATS desk bindings are one builder for every level since step 4: `cats_panel.py`) |
| Approval | `approved_staging.sha256` | its own fingerprints |

About 20 scripts in `tools/schematic` and hartlib branch on the level; the most are in `build_layout_le.py`,
`staging_device_map.py` and `railroad_invariants.py`.

Both levels already share the core home-mast rule (`mast_rule.masts()`); the main and upper masts are not hand-placed.
What differs is what each level adds around it.

## Steps

### 1. One file per kind of fact (no drawing changes)

- **Main lines: done** (branch `agent/claude/level-unification`). `main_lines.csv` replaces `main_lines_staging.csv`
  and `main_lines_main_upper.csv`, with a `sheet` column (staging, main_upper); `count` is read on staging only and
  refused elsewhere. `build_main_route.py --check` unchanged apart from the note it writes.
- **Groupings: needs the owner first.** The two levels use "control point" for different things. Staging has three:
  station groups (`control_points_staging.csv`, with desk codes), stations, and interlockings (the signal rule's
  control points). Main and upper have one file that is all three. Model, one file each with a `level` column:
  `interlockings.csv` (signal rule; owner, 2026-11-20), `stations.csv`, `sheets.csv`, and the station groups as desk
  areas.
  Main and upper's control points become its interlockings, and its stations stay empty until the owner defines
  them in PanelPro (memory: Dispatcher stations for new levels). Wait for the mast result (step 2), since the
  interlockings are its input.
- **Stations and sheets: done** (owner, 2026-11-20). `stations.csv` and `sheets.csv` replace `stations_staging.csv`
  and `sheets_staging.csv`, with a `level` column. A sheet is a station detail sheet (the drawings in
  `docs/ops/stations/`). Only staging has stations; a main or upper row stops `build_staging_sets.py` until it
  builds those levels. The main and upper levels' two whole-level sheets stay in `preferences.json`'s `main_upper` section: they
  list every switch drawn on a band, not stations, and the builder does not read the bands.
  When main and upper stations come, station names are unique across levels or keyed by level: decide then
  (the `station_tracks` and `detail_sheets` keys are by name).
- **Short tracks:** staging lists them by hand, main and upper use a rule (`SHORT_CM`). Proposed: the rule for every
  level, with the file kept only for owner exceptions (35 to 37 is one, a block decided by the owner), level column.
- **Hand lists:** running track and signalled spurs become rules; split tracks stay owner data in
  `block_splits.csv` (step 2, [Masts](#masts)).

### 2. Masts: one rule for every level

**Done** (#786, 2026-11-20, approved by the owner and deployed). See [Masts](#masts). Any change to where masts stand needs stock discovery in a sandbox, `make panels CHECK=1`, the
approval fingerprints rule and the owner's approval of the new panel and desks, with the candidate installed in the
Mac's `~/JMRI_UserFiles` first.

### 3. One file per layer kind, a section per sheet

**Done** (2026-11-20, after R9b-2 #790). Owner decisions: one file per layer kind with a section per sheet; the two
plan graphs `inputs/staging.json` and `inputs/main.json` are kept (no single graph). `plan_overrides.json`,
`preferences.json` and `signals.json` in `jmri/layouts/hart/data/schematic/` each hold `"_sections": true`, a
`_note` and the sections `staging` and `main_upper`, exactly the six old files' contents (the `level` keys of #787
kept, so `mast_rule.band_levels` reads the same). schematic-maps 0.1.49 (model-railroad-skills #82) reads the
sections and stops on an input with both its own `<name>.<kind>.json` and a section. Every hart reader and writer
goes through `hartlib.layer_files` (one JSON format, a missing section is an error, an old per-sheet file beside the
new one stops); the page's preferences are `map_revision.page_prefs()`, the `main_upper` section. Every generated
output was unchanged. Track names: a `name` stays optional on every level (main and upper's end-switch rule today);
that belongs to step 4.

### 4. Level-blind builders (after 1 to 3, tests first)

`cats_panel_staging.py` and `cats_panel_levels.py` become one (done: `cats_panel.py`, every binding made by one set of helpers, its level's facts read from switches.csv and switch_legs.csv for staging and devices.csv for main and upper until steps 5 and 6 put staging's legs and detectors in the device master; pinned by `tools/schematic/tests/test_cats_panel.py`, desks byte-identical); `build_staging_sets.py` builds every level;
`staging_device_map.py` becomes a check of the device master for every level; `build_layout_le.py`, `le_tables.py`
and `railroad_invariants.py` lose their level branches; approval fingerprints are kept per panel and desk. Tests come
first (AGENTS.md "Working on existing scripts").

**Layout Editor part: done** (branch `agent/claude/level-step4-le`, 2026-11-20; candidates byte-identical, pinned by
`tools/schematic/tests/test_le_tables.py` and `test_build_layout_le.BaseNames`). `build_layout_le.py`, `le_tables.py`
and `le_checks.py` read a band's level from its plan-overrides section (`le_common.band_levels`) and which levels the
base holds from `tables_build.GENERATED_LEVELS` (`le_common.BASE_LEVELS`), not band index 0 or the `--levels` flag:
the staging guard (`level_items`, `check_staging_unchanged`: the staging candidate's bands), the panel frame and the
startup positions follow that. One mast check for every level (`le_checks.check_masts`, with each mast file's switch
turnout from `mast_turnouts`) replaces `check_device_masts` and `check_level_slots`; one bound-names check
(`le_tables.check_bound`: a base level's names against the base as it was before the build adds beans, the others
against the tables after, and a base band drawing only blocks its names hold) replaces the three staging-only
checks. Left, as
real facts until steps 5 and 6 or outside these files:
- staging's names come from `staging_device_map.load` (switches.csv, switch_legs.csv, `staging_masts.csv`), main and
  upper's from devices.csv and `main_upper_masts.csv` (`le_names.level_names`, `read_level_masts`): two sources until
  staging's legs and detectors are in the device master;
- staging alone is drawn at its blocks' plan lengths (`staging_lengths`) and with `joins: other` when the levels are
  drawn with it; giving main and upper the same would move their track (geometry is fixed);
- the staging candidate is the approved base the three-level candidate is drawn on and guarded against (`--levels`
  stays as the choice of candidate);
- `le_names.py` (placeholder names, `level_masts`, `shared_turnouts`, `named_bands`) still skips the band keyed
  `Staging`; it was outside this part.

Device-map part (2026-11-20, PR #798): the check moved out of `staging_device_map.py` (which keeps staging's
loaders, the builders' import) into `check_device_master.py`, which holds every level of `devices.csv` to one set of
rules: fact columns, a control point of the row's own level (or, for a block or its detector, the control point of
an end switch of its track on another level: a row's level is the band its track is drawn on, so Track 127-221 on
the upper band is in main level CP 127), all three names on a field device, trial names, hand-kept rows are field
devices, a detector wired exactly when the row is a field device, and every row against its `tables.xml` bean. The
rules between rows (one occupancy row per block on any level, only the helix blocks on two levels, no system name,
user name, jmri_name or DCC address twice, one LCC alias per turnout) are `hartlib.railroad_invariants
.device_row_problems`, run by the check and by the device-map invariant, so `hartlib.railroad check --upto
device_map` finds them before `tables.xml` is built. Staging-only parts are the files only staging has: its
hand-kept rows read against the staging band (`load`), its helix drawing and its mast files.
`railroad_invariants`: one switch-numbers rule for every level, one mast rule over both mast files. One discrepancy
is listed in the check (`KNOWN_STOP`), not fixed: the helix blocks' main and upper rows leave `stop` empty, where the
staging rows and `tables.xml` mark a station. Main and upper have no stations until the owner defines them (step 7),
so `build_device_map.py` writes no stop.

### 5. One block layer (with step 4)

Staging's block rows were kept by hand in its device rows (until part 1, below), with lengths in `block_lengths.csv`;
main and upper generate theirs from the drawing (`build_device_map.py`). One block builder for every level, with hand data only for real
exceptions: owner block decisions (the 35 to 37 short track, `block_splits.csv`) and measured lengths. This takes in
step 1's short-tracks item (the `SHORT_CM` rule for every level, `short_tracks_staging.csv` kept only for
exceptions, level column).

**Comparison (2026-11-20, read-only):** main and upper's block process over the staging band gave 55 blocks for
staging's 45: 7 the same, 17 renamed, 12 OS blocks smaller (their short links became blocks of their own), 2 changed
(OS 7, Scale), 7 gone (OS 7b, 23a, 23b, 35a, 35b, K-1, K-2) and 17 added (OS 23, OS 35, Track 37-39 and 14 links).
Masts: the same 23 home and 5 virtual masts; 8RA anchor to turnout mast; 8LB/8RB, 24L/24RA/24RB, 36RA/36RB protect
the joined crossover OS blocks; 32R faces a link; Masts 67 and 68 gone. Staging's helix needs a `helix` key in its
plan overrides section (or the strand names) for the rule to name it. Most differences are staging's field wiring.

**Owner decisions (2026-11-20):**

| Item | Decision |
|---|---|
| Short pieces between two switches | Join a neighbouring switch's OS block on every level, as staging's wiring does: the lower-numbered switch's unless the wiring says otherwise. **`part_of` in `devices.csv` is the standard way** (owner, 2026-11-20): every track has a block row, and one inside another block names it in `part_of` (role `part`: no JMRI block, layout block or occupancy row of its own; the block it names exists, is on the track's level and is no part itself). Staging's wiring facts stay data in one exceptions file with a level column, `block_exceptions.csv` (35-37 in 35a, 13-15 to 15, 23-31 to 31, the piece of Scale in OS 7, a part per end for 1-3 and 35-39). Main and upper's 21 dark link blocks go: a panel change (SML rediscovery, approval); the CATS desks already draw them so |
| Crossover OS blocks | A crossover half gets its own OS block when it has its own detector (staging 7, 23, 35); otherwise one OS block per crossover |
| K-1/K-2 | Kept split: a level 1 row (37, 39) in `block_splits.csv`, an owner choice like 227-241. Masts 67 and 68 stay |
| Scale and OS 7 | OS 7 ends at the switch; Track Scale is one block and 8RA becomes a turnout mast (panel approval). In the field OS 7's detector still covers about 23 cm of Scale, so a train standing there shows OS 7. Confirmed (owner, 2026-11-20): the 23 cm stays part of Track Scale; part 1 keeps the "Track Scale at 7" row (no output change), part 2 removes it |
| Track names | The plan's name when the track has one (all staging names stay), else from its end switches (main and upper stay). Nothing renamed |
| Block lengths | `plan_lengths.py` (AnyRail 5.3c) for every level. Measured lengths are for speed profiling only, not block lengths: `block_lengths.csv` keeps `measured_in`, but JMRI's block takes `plan_in` (today the 21 timed staging blocks take `measured_in`, `export_track_lengths.py`). Main and upper's intermediates are placed by length: check none moves |
| Helix | Named through `helix_tracks.csv` on every level and emitted once across levels (needed whatever else) |

**Part 1: done** (branch `agent/claude/step5-one-block-builder`, 2026-11-20). One block process for every level,
`tools/schematic/block_layer.py`; `build_device_map.py` writes staging's block and occupancy rows from it (written_by
`build_device_map.py`) beside the main and upper rows. tables.xml, the CATS desks, the Layout Editor candidates and
every approval fingerprint are unchanged; `devices.csv` changed only as follows: the `part_of` column (empty on every
old row), written_by on staging's 90 block and occupancy rows (the two spare detectors included), 17 new part rows,
and 14 staging OS rows' trial names, which lost the link pieces the part rows now carry.
- Parts: "Track 9-11" and the like for a whole link (by the rule: 9-11, 11-13, 15-17, 17-19, 19-21, 25-27, 27-29,
  29-31, 31-33; by `block_exceptions.csv`: 13-15, 23-31, 35-37), "Track 1-3 at 1" / "at 3" and "Track 35-39 at 35" /
  "at 39" for a track split between two OS blocks, "Track Scale at 7" for OS 7's reach onto Scale.
- The rule: a track between two switches under `LINK_CM` (50 cm) is part of the lower-numbered switch's OS block (the
  half at that end, for a crossover whose halves have their own). 50, not `SHORT_CM` (30): staging's wiring folds
  9-11 (38.7 cm) and 11-13 (42 cm) by the rule, and its next track between switches is Barn at 92 cm.
- `block_exceptions.csv` (level, kind, switch_a, switch_b, parallel, end, block, cm, notes) replaces
  `short_tracks_staging.csv`: kind `track` rows give a track (or the piece at one end switch) to an OS block, kind
  `crossover_half` rows name the own-detector halves (7 and 7b, 23a and 23b, 35a and 35b). `cm` is the length of a
  piece at one end whose track keeps the rest (Scale's 23 cm in OS 7; the rest of Scale is its block's length).
  Level 1 rows only until part 2 (a main or upper row would reach the mast plan and not the device rows). A row that
  matches nothing, or applies twice, or gives a block that is not the OS block at its end, stops the build.
- A staging block that a new row makes a part loses its JMRI block: its part row has no name-map columns, its
  detector becomes a spare row named by its node input ("unused Block 1-7"), and both old keys are dropped from the
  name map on purpose (`build_device_map.freed_spare`, `drops`). That is a tables.xml change, so it needs the
  panel approvals like any block change.
- `block_splits.csv` has a level 1 row (37, 39) for K-1 and K-2; a half takes its strand's plan name.
- Track names: the plan's strand name ("Track Scale"), a helix track's block from `helix_tracks.csv` by its plan
  name on every level (no `helix` key needed in staging's overrides), else the end-switch rule.
- Helix: one block across levels. Its block row stays on each level it is drawn on (staging and main or upper, as
  before), and its occupancy row is only on the main or upper level (the detector on node 41).
- Staging's field facts stay in its rows and ride along (system and layout-block names, node, wiring, comment,
  notes, detector, stop, the station group in `cp`, the name-map columns, lengths in `block_lengths.csv`). **A
  staging block change made in PanelPro is carried by hand into the builder's data** (`block_exceptions.csv`,
  `block_splits.csv`, `helix_tracks.csv`), not into `devices.csv`; a field fact (a new detector or system name) is
  still edited in its row, which the builder keeps. A new staging block needs a hand-kept row with its field facts
  first, which the builder then adopts.
- Readers: `staging_device_map.load` gives a part's pieces to its `part_of` block and stops on a piece on no row or
  on two (the short-tracks fallback is gone); every device-map reader skips parts (`hartlib.devices.OUT_OF_MAPS`),
  and `tables_build` skips `part_of` rows by name.
- Pinned by `tools/schematic/tests/test_blocks_every_level.py` (every level's block and occupancy rows, staging's
  reader layer) and `tests/test_block_layer.py` (the rule, the exceptions and their stops, the staging writer);
  the `part_of` invariants by `tools/hartlib/tests/test_devices.py` (TheParts).

**Part 2 (next, a panel change: stock discovery in a sandbox, approvals, `--pi --win`):**
- OS 7 ends at the switch: drop the "Track Scale at 7" row from `block_exceptions.csv`; Scale is one block, 8RA a
  turnout mast (mast_plan over the new layer; the staging masts and signals rebuild).
- Main and upper links folded: set `block_layer.FOLD_LINKS` true for levels 2 and 3 and remove the setting, and
  let `read_exceptions` take level 2 and 3 rows. `LINK_CM` stays 50 on every level (owner, 2026-11-20), so all 25
  main and upper short pieces join: the 21 dark link blocks under 30 cm and 231-237 (39.5 cm), 113-115 (44.2),
  239-245 (45.8) and 229-233 (48.2); none has a detector planned. `build_device_map.build` then writes main and upper part
  rows with `part_row` and leaves the folded links out of its track loop, the LCOS detector allocation and the
  occupancy rows; `SHORT_CM` and its "short link" notes go; a link ending at a connector (the 127/131 halves) needs
  the far switch's OS block (`block_layer.layer` stops on it today).
- Plan lengths: JMRI's block length from `plan_in` for every level (`hartlib.railroad_facts.BlockLength`'s JMRI
  length takes `measured_in` when `source` is timed; `tables_build.master_beans` writes it), after `plan_lengths.py`
  (private plan, the Mac) refreshes `block_lengths.csv`; check no main or upper intermediate moves.
- Main and upper trial names in staging's switch-and-leg keys (they still use plan edge ids, `Track e33`), if wanted,
  so one grammar serves every level.

Part 2 progress (branch `agent/claude/step5-part2`):
- 2026-11-20: links folded on every level (FOLD_LINKS gone, 25 main and upper part rows, the 225 links in their
  corner block), the mast-edge rule (`block_layer.masted_block`), OS 7 ends at the switch (8RA a turnout mast); masts
  and devices.csv regenerated, tests pass. Next: plan lengths, `make panels`, sandbox discovery, before/after.
- 2026-11-20: plan lengths done: JMRI takes plan_in everywhere (`BlockLength.jmri_in` gone), main and upper's 95
  blocks in block_lengths.csv (`plan_lengths.main_upper_lengths`, a #5 turnout class added); intermediates checked:
  none moves (A83/A84 MP 8.395 to 8.397, B92/B93 9.269 to 9.274 with plan lengths; the mast places keep the
  drawing's lengths). Next: `make panels`, sandbox discovery, before/after.

### 6. One wiring file per kind (with the device master's owners)

`lcos_nodes_main_upper.csv` and `detector_pins_main_upper.csv` exist only for main and upper; staging's wiring is in
`switches.csv`, `switch_legs.csv` and its device rows. One node file and one detector-pin file with a level column.
Overlaps the device master (R9), so agree it with the project-health session first.

### 7. Main and upper stations and sheets (waits on the owner)

`stations.csv` and `sheets.csv` take level 1 rows only; the main and upper whole-level sheets stay in
`preferences.json`'s `main_upper` section. Once the owner defines main and upper stations in PanelPro, the builder takes every
level and the hand-kept sheet lists go. Decide then whether station names are unique across levels.

### 8. Retire the older `control_points.csv`

Still generated in the old shape for the website build, `check_layout_facts.py` and the scripts that run in JMRI.
Move those readers to `interlockings.csv` and `stations.csv` (or the device master), then stop generating it.

### 9. Internal name prefixes: left as they are (recommended)

Staging heads are `IH:HART:C1:`, main and upper `C3`; virtual masts are numbered from `$1001`, `$2001` and `$3001`.
They are JMRI system names: changing them renames beans and needs discovery again, for labels that are not a separate
process. Listed so it is a decision, not an omission.

Kept by the owner's choice: two drawings (staging; main and upper), preferences per sheet.

## Order

Steps 1, 2, 3 and 8 are done (step 1's short tracks move to step 5). Step 4 with 5 next. Step 6 comes after the
project-health session's R9c (the generated tables.xml), keyed to devices.csv. Step 7 waits on the owner's main and
upper stations. Step 9 is not planned.

### Next session (owner, 2026-11-20)

A fresh session takes steps 4 and 5. Before starting:

- Wait for the project-health session's boundaries PR (it retires `le_signal_boundaries.csv`, `hartlib.boundaries`
  and `apply_le_sml_facing.py`, and edits `build_layout_le.py` and `le_checks.py`) to merge; steps 4 and 5 change the
  same files. Ask that session (it goes by hart-dc) for its state and tell it when 4 and 5 open a PR, since R9c
  builds `tables.xml` and needs byte-identical outputs.
- R9b-2 (#790) moved every device and name reader to `hartlib.devices`: `replace_rows` and the other writers fail when
  a row with a `pnm_order` would disappear unless `drops=` names it, which a renamed or removed block in step 5 needs.
- Owner's Mac has a CPU limit (2026-11-20): at most about two heavy local jobs at once; `./tools/check.sh` once before
  the commit, single test files while iterating.
- Step 5 may move blocks on the panel: that needs stock SML discovery in a sandbox, a before/after crop and the
  owner's approval per the approval fingerprints rule, then `--pi --win` and the website deploy. A small shift is
  fine if it stays inside the Pi's PanelPro frame (about 160 px spare on the right, 13 px at the bottom).
- Tests first for the scripts merged in step 4 (AGENTS.md, "Working on existing scripts").

## Masts

### What the comparison found (2026-11-20, read-only, nothing committed)

Staging's whole process (`build_staging_masts.py`: home masts, intermediates, anchor and virtual masts, interlockings
as control points) was run over the main and upper bands and compared with the 44 committed masts in
`main_upper_masts.csv`:

- 33 the same, 9 changed, 2 gone, 102 hidden virtual masts added.
- Changed: six searchlights would become dwarfs (120RB, 124LB, 212RA, 218LA, 218RA, 220R) because the passing sidings
  in `running_tracks_main_upper.csv` no longer count as running track; 242L (the exit dwarf from Track 241 Spur)
  would become hidden; A83 and A84 swap direction (staging has no balloon-loop direction rule).
- Gone: B92 and B93, the upper intermediates on 227-241, because staging's intermediate rule needs both ends in an
  interlocking and Switch 241 is in none.
- With the running and spur lists fed in, 40 of 44 match and only the intermediates differ.
- The reverse: staging's station groups as the rule's control points break staging (23 home masts become 34 and the
  build stops), so staging keeps a separate interlockings list. Main and upper's `control_points_main_upper.csv`
  already holds only interlockings.
- `reaches_signal` pruning is in `mast_rule.masts()`, so both levels already use it.

Three hand lists reproduce exactly as rules, checked against the drawing:
- running track: a non-main track joining two interlockings, through a crossover's through route (the 4 rows);
- signalled spur: a spur off a main track at a switch in no interlocking (Track 241 Spur);
- split track: a main track folded at one turnback with both halves over `LONG_CM` (107 Loop, 227-241).

### Owner decisions (2026-11-20)

| Item | Decision |
|---|---|
| Interlockings | One `interlockings.csv` with a `level` column, from `interlockings_staging.csv` and `control_points_main_upper.csv`. Staging's station groups stay separate (desk areas) |
| Running track | The rule on every level; on staging it makes Scale running track, so 6LA and 8RA turn from dwarf to searchlight (a panel approval) |
| Spur exit dwarf | The rule on every level; 242L stays visible; `signalled_spurs_main_upper.csv` goes |
| Split tracks | **Not a rule.** A rule would catch every intermediate loop. They stay the owner's choice, kept as data in `block_splits.csv` (all levels, `level` column, marked as owner choices), replacing `split_tracks_main_upper.csv` |
| Intermediates | One merged rule: one interlocking end is enough, the line code kept (A main, B upper, staging as today), main and upper's loop direction used; B92 and B93 stay, staging unchanged |
| Virtual masts | Only as destinations (owner, 2026-11-20, after the count): place and prune the visible masts first (`reaches_signal` counts visible masts only, so 126L stays dropped), then walk every route of each kept visible mast; a route that reaches a buffer stop before a visible mast gets a virtual bumper mast there, facing it. Nothing else. 29 in all: staging 5 (4LA, 4LB, 10LA, 10LB, 12L), main 10, upper 14. Staging loses 8LC, 10RA, 10RB, 12R and 14R, so no Signal Mast Logic starts from the engine house tracks and westbound routes over Scale run to 6LA (accepted). Main and upper letters close up (102RA, 102RB); a clash with a visible name takes the next letter (120RC) |

Hand facts left under the one process: `interlockings.csv`, `block_splits.csv`, the local-switch areas,
`helix_tracks.csv`, staging's block rows and `block_lengths.csv` (main and upper still generate their own block
layer, so the block layer is not yet one process), the wired heads and `retired_virtual_masts.csv`.

### Next

1. Virtual mast count: done and approved (29).
2. Build, one PR, tests first: `interlockings.csv` and `block_splits.csv`; the running-track, spur and intermediate
   rules in `mast_rule`; one mast builder for every level (`build_staging_masts.py` and the mast part of
   `build_device_map.py`). Then stock discovery in a sandbox, `make panels CHECK=1`, before/after crops for the
   changed masts (6LA, 8RA, the five staging virtual masts dropped, the 24 added on main and upper), the candidate installed in the Mac's `~/JMRI_UserFiles`,
   owner approval, `make panelpro-test`, deploy `--pi --win`.
   Build done on `agent/claude/l2-one-mast-process` (2026-11-20, pins in `tests/test_masts_every_level.py`,
   rules in `tests/test_mast_plan.py`): `mast_plan.plan` is the one mast process; `build_staging_masts.py` and
   `build_device_map.py` (plan_masts) call it over their own block layer and write their own rows, so the
   devices.csv WRITERS are unchanged. Left: `sync_staging_signals.py` with JMRI closed (tables.xml), stock discovery
   in a sandbox, the staging and candidate approvals.
