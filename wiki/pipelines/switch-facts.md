# Switch facts

Where the facts about each switch, mast and control point live, how to change one, and the check that holds the Layout Editor, the CATS desks, the USS CTC and the website indexes to them.

## The files

All in `jmri/layouts/hart/data/`, read through `jmri/layouts/hart/scripts/layout_facts.py`.

| File | One row per | Holds |
|------|-------------|-------|
| `switches.csv` | switch | `level`, `switch` number, Layout Editor turnout (`le_ident`), `cats_inverted` (CATS Normal is the thrown leg: Switch 1 only), USS lever sensors (`ctc_is`), whether the USS column has signal levers (`ctc_signals`), `hand` (L or R, seen from the points; blank where nobody has recorded it). The single turnouts in plan 5.3b come from its part geometry, checked against the Peco catalogue number. The owner gave the rest on 2026-11-14: Switch 5 is a curved left hand, crossovers 7 and 35 are left hand and 23 right hand, and the as-built Switches 9, 11 and 13 are left hand. Switch 13's normal route is its diverging leg (closed leg Track Barn) |
| `switch_legs.csv` | OS block at the points | `closed_leg` and `thrown_leg`: the block each leg leads to. A crossover has two rows; the first is its main OS block |
| `control_points.csv` | control point | its `level` and the switches it holds. Engine House (Switches 9, 11, 13) has a row though the desk has no plate for it |
| `mast_cells.csv` | mast on the USS CTC board | its cell (`x`, `y`) on the board's grid (`uss_board_cells.csv`, the hand-wired desk's grid frozen 2026-11-15) and how the board draws it (`uss_facing`, `uss_kind` h2 or d1, `uss_head` for d1). For the hand-wired CATS desks only: the `edge` of its lamp in that cell and a lamp placement the Designer save gets wrong (`sig_location`, `sig_orient`); the generated desks do not read this file. Row order is the USS drawing order |
| `uss_board_cells.csv`, `uss_board_plants.csv` | cell of the USS CTC board's grid; switch plant | each cell's track, label and block edges, and each OS block's plant cell, frozen from `HART_CTC.xml` and `PLANT_CELLS` on 2026-11-15 so the board builds without a desk. Plant row order is the drawing order |
| `public_name_map.csv` (rows where current = proposed) | device | hardware ID, `dcc` address (turnouts), control point (`cp`), wiring `comment` |

Switch numbers are the plate numbers and are unique across the whole railroad, every level included. `layout_facts.py` refuses a second row for a number, an OS block, a USS lever, a mast or a desk cell, and names both rows.

**Level** is held twice only where it is a fact of its own: per switch and per control point. Everything else takes it from those (`layout_facts.name_map_levels`): a switch's turnout, LCC alias and feedback sensors take the switch's; an OS block or a block a switch leg leads to takes its switch's (a Layout Editor throat block such as Track S-R West through its track, by their shared occupancy sensor); any other mast, head, block or sensor takes its `cp`'s. A main between control points (Track Main West) has no `cp`; the check gives it the one level of the blocks its paths join. There is no district column: nothing groups control points yet (one desk, one Dispatcher). When the new levels need one, it goes on `control_points.csv` beside `level`.

Track names are the CATS occupancy names (`Track S-R`). A Layout Editor throat block such as `Track S-R West`, on the same occupancy sensor, counts as `Track S-R`. `wire_digicon.py` takes each CATS Normal leg, inversion, turnout binding and mast name from these files, and `gen_ctc_track_plan.py` takes the USS lever columns, points dots, signal icons and station plates. CATS plant cells are in `uss_board_plants.csv` (the USS board and `wire_digicon.py` read them), block names in `wire_digicon.py` `ANCHORS`.

## Three views of a switch

Every switch is seen three ways, and they must agree (owner, 2026-11-18):

- **Schematic:** the straight leg (B, the normal route) level, the diverging leg (C) angled. Whether it diverges north or south does not matter; east or west does. The plugin draws this by itself (schematic-maps rule R8), after the main (R5) and yard ladders (R6).
- **AnyRail part:** left- or right-hand, and which way it faces (`hands.csv` from the plan, `switches.csv` `hand`).
- **Layout Editor:** drawn from the schematic. Leg B is the leg in line with A, and `continuing="2"` when the closed leg (`switch_legs.csv`) is leg B.

Exceptions are made only on purpose, each with its reason beside it:

| Switch | Exception | Why |
|--------|-----------|-----|
| 13 | Barn (diverging, leg C) is the normal, closed route | wired so (Peco #7 curved, left-hand) |
| 1, 33 | the main runs through the diverging leg | closed is the straight leg, shown Normal |
| 33, 37, 39 | continuous running in staging needs them thrown | they start up normal, toward the helix |
| 115 | diverging leg drawn level (`level_leg`) | straight-level puts Track 101B-111's climb in the Track 113 siding's CATS desk cell |
| 231, 237 | diverging leg drawn level (`level_leg`) | earlier owner choice |
| 235, 243 | diverging leg drawn level (`level_leg`) | straight-level widens the upper level past the desk and the Layout Editor panel |
| 127/131 | 131's straight leg is a crossover diagonal | one crossover on the ground (`le_crossover_pairs`) |

## Changing a switch

1. Edit its rows in `switch_legs.csv` (closed and thrown legs) and `switches.csv` (hand, lever, inversion). A switch the AnyRail plan lacks or holds wrongly goes in `staging.plan_overrides.json` (`hand`, legs `b` and `c`; `branch_leg: "B"` when the added branch is the straight leg).
2. When edge ids move (`n1`...), rebind `device_map_staging.csv` (`trial_name`) and `staging_signals.csv` (`schematic_edge`).
3. Run `make panels`. A mast boundary that moves stops the build with the rows to rewrite in `le_signal_boundaries.csv`.
4. Install the candidate in `~/JMRI_UserFiles`, relaunch PanelPro and get the owner's approval; then record it (`check_approved.py --approve`, `build_layout_le.py --approve-staging`) and take Signal Mast Logic from stock discovery in a sandbox (`tools/hosts/sandbox/README.md`).
5. Run `./tools/check.sh`. Each failure names the switch or track and the two sources that disagree.

## Changing a mast

- **Rename** (as 32L to 16R, PR #441): rename it in PanelPro and Store (`make tables-pull`), set `proposed` on its identity row in `public_name_map.csv` and apply it (ADR-005, `wiki/pipelines/public-names.md`). If it is on the CATS desk, change its `mast` in `mast_cells.csv` and run `wire_digicon.py` and `gen_ctc_track_plan.py`. Then rebuild the derived files that `check.sh` names as stale: `capture_public_name_baseline.py`, `www/scripts/build_tables_browser.py`, `www/scripts/build_layout_index.py`, then `www/scripts/build_cats_layout_index.py`.
- **Move on the desk:** change its `x`, `y` or `edge` in `mast_cells.csv` (the Designer save must have a SECSIGNAL there), then run both generators. The check fails if either desk has another lamp in that cell or the mast's heads in `tables.xml` do not fit its `uss_kind`.

## Rename checklist (a track, block or mast)

1. **PanelPro:** rename it, Store, then `make tables-pull`. JMRI owns `tables.xml`; nothing renames there by script.
2. **Name map:** apply the rename to `public_name_map.csv` (ADR-005, `wiki/pipelines/public-names.md`). The identity row takes the new name; a historical alias row keeps the old one. Do not add an identity row for a hidden throat block (Track S-R West and the others); `tables.xml` holding the block is what makes it current.
3. **Data files** that key on the name: `mast_cells.csv` (`mast`), `switch_legs.csv` (legs), `block_lengths.csv` (`user_name`), `le_signal_boundaries.csv`, `cats/data/occupancy_bindings.csv`, and the wiring CSVs under `docs/wiring/`.
4. **CATS:** if the desk shows the name, rename it in the Designer save (`HART_Digicon.xml`) or `ANCHORS` in `wire_digicon.py` (plant cells: `uss_board_plants.csv`), then run `wire_digicon.py` and `gen_ctc_track_plan.py`.
5. **Dispatcher:** traininfo files carry block names; regenerate them in PanelPro (Dispatcher System) if a station block was renamed.
6. **Derived files:** run `capture_public_name_baseline.py`, `www/scripts/build_tables_browser.py`, `build_layout_index.py` and `build_cats_layout_index.py`.
7. **Speed-match logs:** if a block on a test route, or its sensor, was renamed, run `python3 jmri/layouts/hart/scripts/speedmatch/build_routes.py` (its `--check` in `check.sh` fails until then). Then convert the speed-match logs and data recorded before the rename, as `speedmatch/rename_extension_tracks.py` does for the 2026-11-13 extension tracks. The analysis stops on a log with a sensor that is not on its route, and names that sensor.
8. **Check:** `./tools/check.sh`. `tools/audit/check_name_copies.py` lists every hand-kept copy of the old name (file and line) in code, data and site pages. Change each one to the new name, or better, look it up from the data. Markdown is prose and is not read. A dated record that must keep the old name goes in its `ALLOW`, with the reason.

The speed-match routes (`speedmatch/analyze.py`) hold only the running order of block names. `build_routes.py` writes each block's occupancy sensor from `tables.xml` into `speedmatch/routes.json`, which `analyze.py` reads with the standard library only, since the Pi's speed-match live publisher has neither hartlib nor `tables.xml`.

## Changing a level or a control point

- Move a control point to another level: change `level` in `control_points.csv` and the `level` of its switches in `switches.csv` together; the check fails if they differ.
- A new `cp` value in the name map needs a `control_points.csv` row first, or the check fails.

## Adding a level

- **Data:** add `switches.csv` rows with the new `level` value and new switch numbers (numbers are never reused), and `control_points.csv` rows with that level for its control points.
- **CATS:** draw the plants in the Designer save, put their cells in `uss_board_plants.csv`, name the blocks in `ANCHORS`, and give each mast a `mast_cells.csv` row.
- **USS CTC:** this is not automatic. The board is one row of lever columns, column (N - 1) / 2 for plate N. A plate number no switch uses gets a blank column. How a second level fits the machine (a wider board, a second panel, its own columns) is a design decision still to be made. Until then `gen_ctc_track_plan.py` stops when `switches.csv` holds a level outside `USS_LEVELS`.

## What the check covers

`tools/audit/check_layout_facts.py`, in `tools/check.sh`:

- **Layout Editor:** turnout hardware and DCC address, layout turnout name and OS block, the leg the continuing sense closes to, and the stored block paths for both legs.
- **CATS desks** (`HART_CTC.xml`, `HART_ABS.xml`): the turnout on each plant, where the close and throw legs lead, which leg is Normal, that every desk block is a Layout Editor block, and that each named lamp is the `mast_cells.csv` mast for that cell and edge.
- **Masts:** each `mast_cells.csv` mast is in the name map and `tables.xml`, with one head (the one named) for d1 and two for h2.
- **Levels:** a control point's switches are on its level, every block's control point agrees with the switches whose legs reach it (throat blocks included), every `cp` has a row, and every mast and block resolves to one level.
- **USS CTC:** each code button's turnout, OS sensors, lever and signal levers. In both copies of the panel, each column's lever and points dot, and the track jewels and labels matching a fresh build from the CATS desk.

`KNOWN` in the check lists differences already reported to the owner, each by its exact message. They print without failing. Any other message fails, even on the same switch or track, and an entry that stops happening fails until someone removes it.

Derived files with a `--check` in `check.sh`: the rename baselines, `www/data/tables-browser.json`, `www/data/layout-index.json` and `www/data/layout-index-cats.json`. The two index files record `image.inputs_sha256`, a hash of what their PNG is drawn from (panel geometry or desk track plan, and the renderer), so a PNG that needs re-rendering fails too; pixels are not compared because the renderers' fonts differ by machine; the CATS desks by `tools/schematic/build_cats_panel.py --check`. Also `jmri/layouts/hart/data/schematic/staging.signals.json`, by `tools/schematic/build_signals.py --check` (from the frozen `schematic/staging_le/masts.csv`, each run checked against the plan graph in `schematic/inputs/`; skipped with a notice when the plugin submodule is absent, CI checks it out). The hand-kept device JSON and the two stale Designer CSVs are gone (2026-11-14); the layout index reads its devices from `tables.xml`. Hand-kept copies of track, block and mast names are held by `tools/audit/check_name_copies.py` (see the rename checklist).
