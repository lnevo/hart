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
  (or `level`) column, a section per sheet, not a file per sheet. Preferences stay per sheet.

## Where the split is (2026-11-20)

| Area | Staging | Main and upper |
|---|---|---|
| Plan input and sheet | `inputs/staging.json`, `staging.plan_overrides.json`, `staging.preferences.json`, `staging.signals.json` | `inputs/main.json`, `main_upper.*` (the same four) |
| Groupings | `control_points_staging.csv` (station groups with desk codes), `stations.csv`, `sheets.csv` (level 1 rows only so far), `interlockings_staging.csv` (the signal rule's control points) | `control_points_main_upper.csv` (the signal rule's control points, also drawn as the stations); detail sheets by hand in `main_upper.preferences.json` |
| Hand lists | `short_tracks_staging.csv` | `running_tracks_`, `signalled_spurs_`, `split_tracks_`, `local_switches_main_upper.csv`; short tracks by a rule (`SHORT_CM` in `build_device_map.py`) |
| Masts | `build_staging_masts.py`: `mast_rule.masts()` plus intermediates, anchor masts, virtual masts, interlockings | `build_device_map.py`: `mast_rule.masts()` plus running, spur and split lists, double-crossover corners; `build_main_upper_masts.py` copies them to `main_upper_masts.csv` |
| Builders | `build_staging_sets.py`, `cats_panel_staging.py`, `staging_device_map.py` | `build_device_map.py`, `cats_panel_levels.py` |
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
  builds those levels. The main and upper levels' two whole-level sheets stay in `main_upper.preferences.json`: they
  list every switch drawn on a band, not stations, and the builder does not read the bands.
- **Short tracks:** staging lists them by hand, main and upper use a rule (`SHORT_CM`). Proposed: the rule for every
  level, with the file kept only for owner exceptions (35 to 37 is one, a block decided by the owner), level column.
- **Hand lists:** running track and signalled spurs become rules; split tracks stay owner data in
  `block_splits.csv` (step 2, [Masts](#masts)).

### 2. Masts: one rule for every level

See [Masts](#masts). Any change to where masts stand needs stock discovery in a sandbox, `make panels CHECK=1`, the
approval fingerprints rule and the owner's approval of the new panel and desks, with the candidate installed in the
Mac's `~/JMRI_UserFiles` first.

### 3. One plan graph and one overrides file (after R9b)

One graph from 5.3c with a level on every part (the plugin already cuts the helix at -5 cm), and one
`plan_overrides.json` with a section per sheet: relabel, names, ends, helix. Track names: a `name` is optional on
every level; with none the name comes from the end switches (main and upper's rule today). Preferences: one file with
a section per sheet, or the two files kept; owner's choice, layer 3 either way.

### 4. Level-blind builders (after 1 to 3, tests first)

`cats_panel_staging.py` and `cats_panel_levels.py` become one; `build_staging_sets.py` builds every level;
`staging_device_map.py` becomes a check of the device master for every level; `build_layout_le.py`, `le_tables.py`
and `railroad_invariants.py` lose their level branches; approval fingerprints are kept per panel and desk. Tests come
first (AGENTS.md "Working on existing scripts").

## Order

Step 1's main lines are done. The groupings and hand lists wait for the mast result and the owner. Steps 3 and 4 wait
for R9b (the device master), which changes the same readers (hartlib `names.py`, `railroad.py`, `le_tables.py`).

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
