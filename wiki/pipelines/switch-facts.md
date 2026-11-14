# Switch facts

Where the facts about each switch, mast and control point live, how to change one, and the check that holds the Layout Editor, the CATS desks, the USS CTC and the website indexes to them.

## The files

All in `jmri/layouts/hart/data/`, read through `jmri/layouts/hart/scripts/layout_facts.py`.

| File | One row per | Holds |
|------|-------------|-------|
| `switches.csv` | switch | `level`, `switch` number, Layout Editor turnout (`le_ident`), `cats_inverted` (CATS Normal is the thrown leg: Switch 1 only), USS lever sensors (`ctc_is`), whether the USS column has signal levers (`ctc_signals`), `hand` (L or R; blank until someone records it, only Switch 9 so far) |
| `switch_legs.csv` | OS block at the points | `closed_leg` and `thrown_leg`: the block each leg leads to. A crossover has two rows; the first is its main OS block |
| `control_points.csv` | control point | its `level` and the switches it holds. Engine House (Switches 9, 11, 13) has a row though the desk has no plate for it |
| `mast_cells.csv` | mast on the CATS desk | the desk cell (`x`, `y`) and `edge` of its lamp, how the USS board draws it (`uss_facing`, `uss_kind` h2 or d1, `uss_head` for d1), and a lamp placement the Designer save gets wrong (`sig_location`, `sig_orient`). Row order is the USS drawing order |
| `public_name_map.csv` (rows where current = proposed) | device | hardware ID, `dcc` address (turnouts), control point (`cp`), wiring `comment` |

Switch numbers are the plate numbers and are unique across the whole railroad, every level included. `layout_facts.py` refuses a second row for a number, an OS block, a USS lever, a mast or a desk cell, and names both rows.

**Level** is held twice only where it is a fact of its own: per switch and per control point. Everything else takes it from those (`layout_facts.name_map_levels`): a switch's turnout, LCC alias and feedback sensors take the switch's; an OS block or a block a switch leg leads to takes its switch's (a Layout Editor throat block such as Track S-R West through its track, by their shared occupancy sensor); any other mast, head, block or sensor takes its `cp`'s. A main between control points (Track Main West) has no `cp`; the check gives it the one level of the blocks its paths join. There is no district column: nothing groups control points yet (one desk, one Dispatcher). When the new levels need one, it goes on `control_points.csv` beside `level`.

Track names are the CATS occupancy names (`Track S-R`). A Layout Editor throat block such as `Track S-R West`, on the same occupancy sensor, counts as `Track S-R`. `wire_digicon.py` takes each CATS Normal leg, inversion, turnout binding and mast name from these files, and `gen_ctc_track_plan.py` takes the USS lever columns, points dots, signal icons and station plates. CATS plant cells stay in `wire_digicon.py` (`PLANT_CELLS`), block names in `ANCHORS`.

## Changing a switch

Example: after a rewiring, Switch 9 normal leads to EH-2 and thrown to EH-3.

1. Edit its row in `switch_legs.csv` (and `switches.csv` if its inversion, lever or hand changes).
2. In PanelPro, set the turnout's continuing sense and fix the OS block paths, then Store and run `make tables-pull` (ADR-008). Nothing edits `tables.xml` by script for this.
3. If the CATS drawing needs other track names, change `ANCHORS` in `wire_digicon.py` or the Designer save, then run `python3 cats/scripts/wire_digicon.py`. It stops if a desk leg cannot reach the block the data names.
4. Rebuild the USS panel: `python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py`. This rewrites `GUIObjects.xml` and the panel in `tables.xml`. If the rebuild clears a difference listed in `KNOWN` in the check (empty since the 2026-11-12 rebuild), that entry then fails as "no longer happens", so remove it in the same commit as the rebuild.
5. Run `./tools/check.sh` (or just `python3 tools/audit/check_layout_facts.py`). Each failure names the switch or track and the two sources that disagree.

## Changing a mast

- **Rename** (as 32L to 16R, PR #441): rename it in PanelPro and Store (`make tables-pull`), set `proposed` on its identity row in `public_name_map.csv` and apply it (ADR-005, `wiki/pipelines/public-names.md`). If it is on the CATS desk, change its `mast` in `mast_cells.csv` and run `wire_digicon.py` and `gen_ctc_track_plan.py`. Then rebuild the derived files that `check.sh` names as stale: `capture_public_name_baseline.py`, `www/scripts/build_tables_browser.py`, `www/scripts/build_layout_index.py`, then `www/scripts/build_cats_layout_index.py`.
- **Move on the desk:** change its `x`, `y` or `edge` in `mast_cells.csv` (the Designer save must have a SECSIGNAL there), then run both generators. The check fails if either desk has another lamp in that cell or the mast's heads in `tables.xml` do not fit its `uss_kind`.

## Changing a level or a control point

- Move a control point to another level: change `level` in `control_points.csv` and the `level` of its switches in `switches.csv` together; the check fails if they differ.
- A new `cp` value in the name map needs a `control_points.csv` row first, or the check fails.

## Adding a level

- **Data:** add `switches.csv` rows with the new `level` value and new switch numbers (numbers are never reused), and `control_points.csv` rows with that level for its control points.
- **CATS:** draw the plants in the Designer save, put their cells in `PLANT_CELLS`, name the blocks in `ANCHORS`, and give each mast a `mast_cells.csv` row.
- **USS CTC:** this is not automatic. The board is one row of lever columns, column (N - 1) / 2 for plate N. A plate number no switch uses gets a blank column. How a second level fits the machine (a wider board, a second panel, its own columns) is a design decision still to be made. Until then `gen_ctc_track_plan.py` stops when `switches.csv` holds a level outside `USS_LEVELS`.

## What the check covers

`tools/audit/check_layout_facts.py`, in `tools/check.sh`:

- **Layout Editor:** turnout hardware and DCC address, layout turnout name and OS block, the leg the continuing sense closes to, and the stored block paths for both legs.
- **CATS desks** (`HART_CTC.xml`, `HART_ABS.xml`): the turnout on each plant, where the close and throw legs lead, which leg is Normal, that every desk block is a Layout Editor block, and that each named lamp is the `mast_cells.csv` mast for that cell and edge.
- **Masts:** each `mast_cells.csv` mast is in the name map and `tables.xml`, with one head (the one named) for d1 and two for h2.
- **Levels:** a control point's switches are on its level, every block's control point agrees with the switches whose legs reach it (throat blocks included), every `cp` has a row, and every mast and block resolves to one level.
- **USS CTC:** each code button's turnout, OS sensors, lever and signal levers. In both copies of the panel, each column's lever and points dot, and the track jewels and labels matching a fresh build from the CATS desk.

`KNOWN` in the check lists differences already reported to the owner, each by its exact message. They print without failing. Any other message fails, even on the same switch or track, and an entry that stops happening fails until someone removes it.

Derived files with a `--check` in `check.sh`: the rename baselines, `www/data/tables-browser.json`, `www/data/layout-index.json` and `www/data/layout-index-cats.json`. The two index files record `image.inputs_sha256`, a hash of what their PNG is drawn from (panel geometry or desk track plan, and the renderer), so a PNG that needs re-rendering fails too; pixels are not compared because the renderers' fonts differ by machine; `cats/scripts/tests/test_desks_match_source.py` rebuilds the desks. Also `jmri/layouts/hart/data/schematic/staging.signals.json`, by `tools/schematic/build_signals.py --check` (the schematic-maps plugin's `signals` command over the plan graph in `schematic/inputs/`; skipped with a notice when the plugin submodule is absent, CI checks it out). The hand-kept device JSON and the two stale Designer CSVs are gone (2026-11-14); the layout index reads its devices from `tables.xml`.
