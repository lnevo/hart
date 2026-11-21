# Pipeline 19 — Panels from the schematic

Every panel is drawn from the approved schematic: the switch hands, the signal plan, the device map for the main and
upper levels, the published schematic and station sheets, the CATS desks and the Layout Editor panel (built as
a candidate beside `tables.xml`). The schematic-maps plugin (`external/model-railroad-skills`) solves the sheet; the scripts in
`tools/schematic/` turn it into each output. This replaced the AnyRail pipeline ([jmri-anyrail.md](jmri-anyrail.md)).

**Status:** Live. The Layout Editor cut-over (2026-11-16) and the CATS desks (ADR-023) are built this way.

**Layer files (level-unification step 3, 2026-11-20):** `jmri/layouts/hart/data/schematic/` holds one file per layer
kind, `plan_overrides.json`, `preferences.json` and `signals.json`, each with `"_sections": true` and a section per
sheet (`staging`, `main_upper`, the input names in `publish_draft.INPUTS`). The plugin reads the sections itself
(schematic-maps 0.1.49); every hart script reads and writes them through `hartlib.layer_files`, which keeps the JSON
format in one place and stops on a missing section or an old `<sheet>.<kind>.json` left beside the file.

## Run

```bash
make panels           # rebuild every output, in order; stops at the first failure
make panels CHECK=1   # check every output; names each stale one
make desks            # only the CATS desks, then validate them
```

`tools/schematic/build_panels.sh` runs the steps in the order they depend on each other:

| Step | Script | Writes |
|------|--------|--------|
| hands | `build_hands.py` | `hands.csv` from the plan graph |
| staging-sets | `build_staging_sets.py` | in `plan_overrides.json`'s `staging` section the `control_points`, `stations` and `station_tracks` keys, in `preferences.json`'s `staging` section the `detail_sheets` key, from `control_points_staging.csv`, `stations.csv` and `sheets.csv`; stops with file and line on an unknown switch, a switch in two control points, or a station or sheet naming something that is not there |
| main-route | `build_main_route.py` | the `main_route` key of `plan_overrides.json`'s `main_upper` section and, for staging, the `main` flags of its `name` edit and its `milepost_route`. Both from `main_lines.csv`, one file with a `sheet` column (staging or main_upper). Main and upper: worked out from its main_upper rows (the two main lines by helix end, end switch, turnback and double tracks) and the plan graph; stops when a stretch has two equally short ways or a pair of switches has two tracks nobody declared; staging: from its staging rows, each line naming the junctions it passes (a track must join each to the next; `count` yes marks the lines the mileposts run along) |
| plan-lengths | `plan_lengths.py --check` | nothing: stops when `block_lengths.csv`'s `plan_in` no longer matches the AnyRail plan 5.3c (the track runs need the private plan file; without it only the OS rows, from `parts.json`, are checked). Run `plan_lengths.py` by hand to write them |
| staging-masts | `build_staging_masts.py --check` | nothing: stops when `staging_masts.csv`, `staging_signals.csv` or the staging mast and head rows of `devices.csv` (and the three files it generates) no longer match the staging signal rule. Run `build_staging_masts.py` by hand to write them |
| signals | `build_signals.py` | `signals.json` (a section per sheet) from the plan graph, the staging masts (`staging_signals.csv`, `staging_masts.csv`) and `main_upper_masts.csv` |
| device-map | `build_device_map.py` | the levels 2 and 3 rows of `devices.csv` (and `device_map_main_upper.csv`, generated from it) and the layer overrides the schematic reads |
| main-upper-masts | `build_main_upper_masts.py` | `main_upper_masts.csv` for the Layout Editor builds |
| schematic | `publish_draft.py` | the schematic sheets and station pages |
| le-cutover | `build_layout_le.py --as-live` | the cut-over candidate `output/trial/tables_cutover.xml`, every level from its device map and the panel's own items from `panel_items.json`, and the staging candidate it holds, `tables_cutover_staging.xml`. Both are built on the generator's base (`hartlib.tables_build.base`: `data/tables_template.xml` and the staging beans of `devices.csv`; ADR-029), never on `tables.xml`. The viewing trials (`tables_layout.xml`, `tables_layout_staging.xml`) are retired (owner, 2026-11-17): `build_layout_le.py` without `--as-live` stops with an error |
| approved-candidate | `check_approved.py le-candidate` | nothing: stops when the cut-over candidate drifts from the approved fingerprint |
| tables | `build_tables.py` | `output/tables.xml`, the file PanelPro and CATS load (ADR-029: an output): the template, the staging beans of `devices.csv`, the Layout Editor build, the discovered Signal Mast Logic (`data/schematic/discovered_sml.xml`, written only by `run_sml_discover.sh`) and the Digicon boot rule, in a fixed envelope. `--check` (also in `tools/check.sh`) fails on any difference. A PanelPro Store is never copied over it: `make tables-pull` keeps it in `~/JMRI_UserFiles-pulled/` until R9d splits it into the sources. `--discovery-base` writes it with no Signal Mast Logic, for `run_sml_discover.sh` |
| staging-sync | `sync_staging_signals.py --check` | nothing: stops when the staging heads and masts in `tables.xml` differ from `staging_masts.csv`. It runs after `tables`, which generates them from `devices.csv` |
| staging-map | `staging_device_map.py --check` | nothing: checks the staging device map files against `tables.xml` and the schematic, after `tables` writes it. The staging rows of `devices.csv` that carry no `written_by` (turnouts, feedback, blocks, detectors) are kept by hand; `staging_masts.csv`, `staging_signals.csv` and the mast and head rows are generated (staging-masts above). `device_map_staging.csv` is generated from `devices.csv` |
| cats | `build_cats_panel.py` | `cats/panels/HART_CTC.xml`, `HART_ABS.xml` and `HART_CTC.bindings.json`; it runs after `tables`, whose turnouts, sensors and masts the desks read. The bindings for every level come from one builder, `cats_panel.py` (facts in `cats_panel_facts.py`, header and plate in `cats_panel_dress.py`) |
| approved-desks | `check_approved.py cats-ctc cats-abs` | nothing: stops the run when a desk no longer matches the fingerprint the owner approved |
| approved-live | `check_approved.py le-panel` | nothing: stops when the live panel in `tables.xml` drifts from the approved fingerprint |

Each step reads the plugin's cache (`~/.cache/hart/schematic`), so a run after a small change redoes only what that
change reaches. `tools/check.sh` runs `--check` on the hands, main route, staging masts, staging sync, staging map, signals, device map, main and upper masts and CATS steps, and the approved fingerprints (`check_approved.py`); `make panels
CHECK=1` checks them all.

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

Source of track: AnyRail's JMRI export of plan 5.3c (5.3b until Phase 2, 2026-11-19), read by the plugin's `plan` command into the track graphs in `jmri/layouts/hart/data/schematic/inputs/` (recipe in `docs/ops/schematic-system-draft.md`), with the parts list from `tools/anyrail/anyplan.py` and the helix from the plan: each level's graph takes its share of a helix track up to the -5 cm cut (`anyplan.py --cut -5 --stubs`). T names are 5.3c part numbers (re-keyed from 5.3b by position). The `.any` file and its XML export stay in `~/Documents/Layout/`, outside the repo. Heights come from the `.any` file, matched to the export by position (the 5.3b export is a 2664 x 3840 px panel at about 12.0 px per inch of plan, within 0.4% of the plugin's default; the plugin fits the scale by least squares against the parts list).

| Override | Staging | Main and upper |
|----------|---------|----------------|
| Switch numbers for plan parts | T45=3, T124=1, T114=5, T49=15, T71=17, T96=19, T73=21, T65=25, T109=27, T84=29, T40=31, T106=33, T57+T126=23, T54+T95=35, T55=39, T78=37 | Owner's numbers (2026-11-14, both levels renumbered by the rule 2026-11-19), a `relabel` edit in `plan_overrides.json`'s `main_upper` section: main level 101 to 131, upper level 201 to 245, odd only, left to right as drawn on the approved sheet, the main line first at the same position, then top to bottom. A crossover is one number with A and B (A the left half), numbered where its A half stands: the three-way's halves pair with T196 and T202 as 101 and 103, T5/T10 and T194/T20 are one crossover each on the ground (121, 125), the helix-top crossovers T215/T311 and T210/T281 are main level (127, 131), the double crossover is one part (225). Upper renumber (2026-11-19): 207 and 209 swapped, the 213 crossover became 211 and 211 became 213, 231 and 233 swapped, 239 became 241, the 241 crossover 243, and 243 became 239. The plan joins 121's and 125's halves leg C to leg B (AnyRail's leg B of T10 and T20 is the diagonal), and the plugin (schematic-maps 0.1.42, `crossover_halves`) pairs lettered halves joined B to C as one single crossover: each half is closed on its through leg (121B and 125B on their leg C) on the Layout Editor panel and the CATS desks, and the log asks for their machines to be wired reversed. The T-names stay as aliases, so the other layer files still use them |
| Not built | None since 5.3c (it has no crossover T41/T43) | — |
| Built but not in the plan | None since 5.3c: it draws the Switch 7 crossover (T33, T139), Switch 13 (T135), Switches 11 (T137) and 9 (T136) with EH-1 to EH-3, all left-hand; they are relabelled and named like the rest | — |
| Moved | — | None since 5.3c: it draws 223 (T331) on the 4.25 in track where it is built |
| Heights | — | None since 5.3c: the peninsula is at 10.8 cm (4.25 in) in the plan |
| Track names | Main West, West Ext, East Ext, Main East, East Lead, Brick-Plane, Scale, Barn, S-R, S-1 to S-4, K-1, K-2, W-1, W-2, EH-1 to EH-3 | None yet |
| Track ends | W-1, W-2 and EH-1 to EH-3 bumpers | — |
| Helix tracks | From Switch 39: McKees Rocks (H1). From Switch 37: McKeesport (H2) | From T210: McKees Rocks (H1). From T281: McKeesport (H2). Owner confirmed |
| Main route | Main West, West Ext, Brick-Plane, East Ext, Main East, East Lead, the two throats from 35 to 37 and 39, both helix tracks | H2, T281, T311, the rise to T294, diverge to T316, round the west loop by T310, T283, T261 to T307 and T289, T331, both tracks to the double crossover, round the peninsula loop by T268 and T270. H1, T210, T215, T194, diverge at T200 on the long track to T165, T181, T178, T166, round the loop at T204. The T289–T294 crossover is not main |
| Stations | Brick (1, 3), Plane (5), Barn (7), South Yard (15–21), East End (23–33), Princess (35–39), as `control_points_staging.csv` | None yet |
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
- **Switch hands (owner, 2026-11-14):** main and upper hands come from the plan geometry (`hands.csv`, `build_hands.py`, `--check` in `check.sh`; 50 switches, 225 left out as a double crossover). The halves of crossovers 121 and 125 have opposite hands in `hands.csv` (121A L, 121B R; 125A R, 125B L), and that is real, not an error: the plan lays T1 and T14 with their straight route on the diagonal, so their leg B is the crossover's diagonal and the hand is read from it. Staging Switches 9 and 13 stay as the Layout Editor has them (both drawn right-hand; 9 normal is EH-2, 13 normal is Barn); `switches.csv` `hand` stays L for both, the physical hand.
- **Helix joined (owner, 2026-11-17, release approved in a sandbox PanelPro and CATS):** staging's end bumpers at McKees Rocks and McKeesport are joins; `approved_staging.sha256` was unchanged. The system schematic and station sheets carry no DRAFT mark (revision 10; files keep their `-draft` names so links stay).
- **CATS desks:** main and upper are CTC on the CTC desk, so a route up the helix stops at Mast 132RA (main, via 131-H1) or Mast 132RB (upper, via 131-H2); the ABS desk is all ABS. Every main and upper block has a virtual sensor (`IS:HART:C3:B:<block>`); a physical detector is swapped in through the device map's `jmri_name` column.
- **Switch 225 (owner, 2026-11-17):** the CATS desks show OS Switch 225a to d, one block per corner, each bound to its planned detector, plus a middle block for the crossing cells with no detector (CATS cannot put a block boundary where two blocks meet on one side of a crossing). The middle stays dark; occupancy shows in the four corners and CATS still locks the crossing. Revisit only if the diamond is gapped as its own section when 225 is wired. The 107 Loop is two desk blocks.
- **Layout Editor geometry (2026-11-17):** the geometry once set by constants in `build_layout_le.py` is layer 3 preferences the plugin reads (`le_shift`, `le_crossover_angle`, `le_labels`, `le_band_labels`, `le_longer_straights`, `le_title_clear`, `le_stretch`, `le_window` in `preferences.json`'s `staging` and `main_upper` sections). `build_layout_le.py` is split into `le_common.py`, `le_names.py`, `le_checks.py` and `le_tables.py`, with the staging approval fingerprint in `approval.py`. Check crossover slants in real PanelPro or with the plugin's JMRI port (`tests/jmri_xover.py`), never from the XML attributes alone.
- **Parked:** NX, the Dispatcher System and the USS CTC (see [`STATUS.md`](../STATUS.md)); unparking means refreshing `parked/tables_parked.xml` per its README.
## Background

- **Goal:** turn the AnyRail plan into a logical (not physical) view of the railroad and draw maps from it: the system schematic, the station pages, the CATS desks and the Layout Editor panel. The generic reader, layout engine, style and skill are in the public `model-railroad-skills` plugin (`plugins/schematic-maps`); HART's names, numbers and finished maps stay in this repo.
- **Owner decisions (2026-11-13):** the system schematic came first and the other outputs followed; the tool proposes stations, tracks and roles in draft files and the owner edits them; the look is NYAMR drafting style (black line work, heavy main and light secondary track, capitals, little colour); Letter landscape.
- **Timetable direction** follows the route, not the room ([ADR-022](../decisions/ADR-022-timetable-direction-follows-route.md)): eastward from staging stays eastward on every level, so every band has east on the right.
- **Exports of the owner's plan may be public.** The custom objects and buildings in the plan may not (their author holds the copyright), and the `.any` files stay out of every repo.
- **Rules the references agree on:** the main is one horizontal line per level; other tracks leave at 45 degrees and run parallel; the main is heavier than sidings and yard tracks; hidden track is dashed; a direction legend on every sheet; "To X" at open ends; a title block with date and revision; black on white first.
- **References:** the North Western Vermont schematic (NER Coupler 303, pp. 22-23: rows across a page, yard tracks with capacity, yard limit marks); the NYAMR [orthogonal schematic](https://davebarraza.wordpress.com/wp-content/uploads/2021/02/nyamr-orthagonal-schematic-210210-1.pdf) (one band per level, helix letters, station bars, title block), [Physical Characteristics Book](https://davebarraza.wordpress.com/wp-content/uploads/2026/04/nyamr-physical-characteristics-book-260415.pdf) (one location per page, capacity in 50-foot cars) and [deck track maps](https://davebarraza.wordpress.com/wp-content/uploads/2022/05/nyamr-overhead-view-2022.pdf); the [St Charles Branch crew track chart](https://appalachianrailroadmodeling.com/stcharlesbranch/?p=796) (multi-deck, helix on one straightened line); the PRR [Walbridge interlocking sheet](https://www.redoveryellow.com/position-light/PRR_Diagrams/walbridge.gif) (switch and signal numbering); Luteberget and Johansen, "Drawing with SAT", and [railplot](https://github.com/luteberget/railplot) as prior art for automatic schematics (licence not confirmed, so no code reuse).

History of how this was built (spike, cut-over, hand-offs, the stage plan and as-built notes against plan 5.3b): [`archive/wiki/projects/schematic-maps-handoff.md`](../../archive/wiki/projects/schematic-maps-handoff.md) and [`archive/wiki/projects/schematic-maps.md`](../../archive/wiki/projects/schematic-maps.md).
