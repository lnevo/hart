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

- **Masts:** no hand-drawn facts where possible. Check what changes if every level's masts come from one rule
  (see [Masts](#masts)), then decide.
- **Sheets:** the drawings stay two sheets (staging; main and upper). Files that hold facts for both get a `sheet`
  (or `level`) column, a section per sheet, not a file per sheet. Preferences stay per sheet.

## Where the split is (2026-11-20)

| Area | Staging | Main and upper |
|---|---|---|
| Plan input and sheet | `inputs/staging.json`, `staging.plan_overrides.json`, `staging.preferences.json`, `staging.signals.json` | `inputs/main.json`, `main_upper.*` (the same four) |
| Groupings | `control_points_staging.csv` (station groups with desk codes), `stations_staging.csv`, `sheets_staging.csv`, `interlockings_staging.csv` (the signal rule's control points) | `control_points_main_upper.csv` (the signal rule's control points, also drawn as the stations); detail sheets by hand in `main_upper.preferences.json` |
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
  control points). Main and upper have one file that is all three. Proposed model, one file each with a `level`
  column: `interlockings.csv` (signal rule), `stations.csv`, `sheets.csv`, and the station groups as desk areas.
  Main and upper's control points become its interlockings, and its stations stay empty until the owner defines
  them in PanelPro (memory: Dispatcher stations for new levels). Wait for the mast result (step 2), since the
  interlockings are its input.
- **Short tracks:** staging lists them by hand, main and upper use a rule (`SHORT_CM`). Proposed: the rule for every
  level, with the file kept only for owner exceptions (35 to 37 is one, a block decided by the owner), level column.
- **Hand lists** (running, signalled spurs, split): wait for step 2; some may become rules.

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

Pending: a read-only run of staging's whole process over the main and upper bands, compared with the committed masts.
