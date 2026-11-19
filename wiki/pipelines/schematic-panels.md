# Pipeline 19 — Panels from the schematic

Every panel is drawn from the approved schematic: the switch hands, the signal plan, the device map for the main and
upper levels, the published schematic and station sheets, the CATS desks and the Layout Editor panel (built as
a candidate beside `tables.xml`). The schematic-maps plugin (`external/model-railroad-skills`) solves the sheet; the scripts in
`tools/schematic/` turn it into each output. This replaced the AnyRail pipeline ([jmri-anyrail.md](jmri-anyrail.md)).

**Status:** Live. The Layout Editor cut-over (2026-11-16) and the CATS desks (ADR-023) are built this way.

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
| staging-map | `staging_device_map.py --check` | nothing: checks the hand-kept staging device map (`device_map_staging.csv`, `control_points_staging.csv`, `staging_masts.csv`, `staging_signals.csv`) against `tables.xml` and the schematic |
| signals | `build_signals.py` | `<name>.signals.json` from the plan graph and the staging masts (`staging_signals.csv`, `staging_masts.csv`) |
| device-map | `build_device_map.py` | `device_map_main_upper.csv` and the layer overrides the schematic reads |
| main-upper-masts | `build_main_upper_masts.py` | `main_upper_masts.csv` for the Layout Editor builds |
| schematic | `publish_draft.py` | the schematic sheets and station pages |
| cats | `build_cats_panel.py` | `cats/panels/HART_CTC.xml`, `HART_ABS.xml` and `HART_CTC.bindings.json` |
| approved-desks | `check_approved.py cats-ctc cats-abs` | nothing: stops the run when a desk no longer matches the fingerprint the owner approved |
| le-cutover | `build_layout_le.py --as-live` | the cut-over candidate `output/trial/tables_cutover.xml`, every level from its device map and the panel's own items from `panel_items.json`, and the staging candidate it holds, `tables_cutover_staging.xml`. Both are built on the live `tables.xml` less what the build owns (`strip_build_owned`: the main and upper objects, the Signal Mast Logic and block paths that name them, and the generated panel it replaces); everything else in `tables.xml` carries through. The live `tables.xml` is that candidate with Signal Mast Logic from stock discovery in a sandbox. A gitignored candidate built before a change to `tables.xml` or to this rule shows STALE in `make panels CHECK=1` until `make panels` is run again. The viewing trials (`tables_layout.xml`, `tables_layout_staging.xml`, a "Layout (generated)" panel beside the live one) are retired (owner, 2026-11-17): `build_layout_le.py` without `--as-live` stops with an error. Copies of those two files left in a checkout's gitignored `output/trial/` are stale: delete them |
| approved-candidate | `check_approved.py le-candidate` | nothing: stops when the cut-over candidate drifts from the approved fingerprint |
| approved-live | `check_approved.py le-panel` | nothing: stops when the live panel in `tables.xml` drifts from the approved fingerprint |

Each step reads the plugin's cache (`~/.cache/hart/schematic`), so a run after a small change redoes only what that
change reaches. `tools/check.sh` runs `--check` on the hands, staging map, signals, device map, main and upper masts and CATS steps, and the approved fingerprints (`check_approved.py`); `make panels
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

Source of track: AnyRail's JMRI export of plan 5.3b, read by the plugin's `plan` command into the track graphs in `jmri/layouts/hart/data/schematic/inputs/` (since 2026-11-14; recipe in `docs/ops/schematic-system-draft.md`). The `.any` file and its XML export stay in `~/Documents/Layout/`, outside the repo. Heights come from the `.any` file, matched to the export by position (the 5.3b export is a 2664 x 3840 px panel at about 12.0 px per inch of plan, within 0.4% of the plugin's default; the plugin fits the scale by least squares against the parts list).

| Override | Staging | Main and upper |
|----------|---------|----------------|
| Switch numbers for plan parts | T46=3, T116=1, T106=5, T52=15, T133=17, T73=19, T123=21, T68=25, T95=27, T94=29, T59=31, T77=33, T58+T118=23, T55+T98=35, T56=39, T129=37 | Owner's numbers (2026-11-14), a `relabel` edit in `main_upper.plan_overrides.json`: main level 101 to 135, upper level 201 to 245, odd only, left to right as drawn on the approved sheet, the main line first at the same position, then top to bottom. A crossover is one number with A and B (A the left half): the three-way's halves pair with T183 and T194 as 101 and 103, the helix-top crossovers T199/T285 and T175/T251 are main level (129, 135), the double crossover is one part (225). The T-names stay as aliases, so the other layer files still use them |
| Not built | Crossover T41/T43 between Main West and S-R | — |
| Built but not in the plan | Switch 7 crossover (Scale / East Ext), Switch 13, Switches 11 and 9 with EH-1 to EH-3 | Closet junction: T300 moved onto the 4.25 in track |
| Moved | — | T300: out of the height-0 main, into the run between the double crossover and T237, about 292 cm from the crossover, right-hand (owner confirmed right-hand; the distance is the plan's old run length) |
| Heights | — | Peninsula top 1 in → 4.25 in |
| Track names | Main West, West Ext, East Ext, Main East, East Lead, Brick-Plane, Scale, Barn, S-R, S-1 to S-4, K-1, K-2, W-1, W-2, EH-1 to EH-3 | None yet |
| Track ends | W-1, W-2 bumpers | — |
| Helix tracks | From Switch 39: McKees Rocks (H1). From Switch 37: McKeesport (H2) | From T175: McKees Rocks (H1). From T251: McKeesport (H2). Owner confirmed |
| Main route | Main West, West Ext, Brick-Plane, East Ext, Main East, East Lead, the two throats from 35 to 37 and 39, both helix tracks | H2, T251, T285, the rise to T262, diverge to T275, round the west loop by T273, T256, T233 to T274 and T237, T300, both tracks to the double crossover, round the peninsula loop by T241 and T253. H1, T175, T199, T184, diverge at T187 on the long track to T153, T165, T160, T155, round the loop at T196. The T237–T262 crossover is not main |
| Stations | Brick (1, 3), Plane (5), Barn (7), South Yard (15–21), East End (23–33), Princess (35–39), as `control_points.csv` | None yet |
| West end | W-1 | — |

Also a reader rule, not an override: two track ends on the same spot in the export are one track and are joined (two pairs in 5.3b, one of them the main level's loop at T196).

Hands and legs of the added staging switches are taken from the Layout Editor panel in `tables.xml`, which is the source for them (owner, 2026-11-13):

| Switch | Hand | Straight leg | Diverging leg |
|--------|------|--------------|---------------|
| 7 | Left-hand crossover | Scale to Barn; East Ext to Main East | The crossover |
| 13 | Right | Barn | Switch 11 |
| 11 | Left | EH-1 | Switch 9 |
| 9 | Right | EH-3 | EH-2 (its normal route: the panel's continuing sense is thrown) |

Where they sit along their runs comes from `block_lengths.csv`, since the panel is not to scale: East Ext is measured (140.8 in, from the timed loop); Scale, Barn and EH-1 to EH-3 are 24 in estimates.

### Layer 2: generation rules

Already rules in the spike:

- One band per level; a run that joins two levels is cut and shown as lettered connectors. Level by height (below 5 cm: main; above: upper).
- Each switch faces left or right; runs that must double back are folded, choosing the folds that are U-turns on the layout, and keeping the choice that draws with the fewest faults.
- Tracks are ordered top to bottom from each switch's hand; a loop's two tracks are stacked by which way the loop bends.
- A double crossover's two tracks sit on neighbouring rows.
- Spare length along a band is shared in proportion to real track length; switches joined by short links move as blocks; track ends and folds travel with their switch; a long track always gets a level run; a connector gets one short cell.
- The drawing is checked for lines that cross or lie on top of each other, and the solver adds clearance until none do.

### Layer 3: the owner's preferences for this sheet

- Order from the top: staging, main, upper (owner, 2026-11-14, REV 3). Helix at the east end of every band (a 180-degree turn of the two upper bands was tried and undone; east and west on the looped mains are to be settled later by following the main line, perhaps on the CATS diagram; ADR-022 stands meanwhile).
- All bands the same width; main band 95% and nudged left; upper band nudged so H2 sits under H1.
- Helix marks: three-turn coil with H1 or H2 and "Helix to …". Connectors between main and upper: circled A and B.
- The helix-top switches T285 and T251 are drawn on the upper band (they are at height 0), T199 and T175 on the main band.
- Main level: the loop at T196 above the main, the three yard tracks below it (drawn sides flipped for T196, T155, T160, T162, T194, T183, 50, 51).
- Lengths: staging: Plane to the right of Brick, Switches 7 and 13 further east, Switch 13 to 15 one cell, drawn short like T274 to T237 (owner, 2026-11-14; the cells given to East Lead, now 7, and West Ext), long yard tracks. Main: yard throat level with the loop's edge, a long run between T1 and 12, room between T160 and T165. Upper: T237 to T300 short, T262 to T285 five cells.
- NYAMR drafting style, Letter landscape, title block, station brackets under staging.
- Facing letters (owner, 2026-11-14, plugin 0.1.3; **off since REV 5**, both files `false`, see ADR-022 amendment): when on, `facing_letters` prints R or L after each switch number, R when the points meet an eastward train first (the sense of the mast names). East follows the main route in timetable order: on staging as drawn (west end W-1); on the main and upper levels outward from the helix, so the helix is their west end even though the sheet keeps it at the right, and those bands carry a small EAST arrow on each main run. On the main level the balloon at T196 and the three yard tracks are the east end (Neville Island), toward the helix is westward to West Yard. The double crossover 225 prints no letter; crossover halves did (REV 4: 101AL/101BR, 103AL/103BR, 119AL/119BR, 129AL/129BR, 135AR/135BL). To check if the letters come back: 121L (T15, a wye) and 227L (T253, where the upper main turns back round the peninsula loop).
- Capacity (owner, 2026-11-14, REV 4, plugin 0.1.5): counts are in 50 ft cars (7.4 in each), from whole-track lengths with no room left for an engine, and printed after the name, or alone on an unnamed track. Staging uses the lengths in `block_lengths.csv` (measured, timed or estimated, as its flag column says; EH-1 to EH-3 are 24 in estimates), which `publish_draft.py` copies into `track_lengths_in` in `staging.plan_overrides.json` (`--check` fails if they go stale). The main and upper levels use plan lengths, with each unnamed yard track summed over its pieces. Each station bar shows a total, counted at the track's west end. Barn now spans Switches 7, 9, 11 and 13 so the engine house counts there; Scale stays with Plane.
- Title block fields (owner, 2026-11-14): `date`, `revision` and `sheet` in `main_upper.preferences.json` print in a ruled column at the right of the title box (NOV 14, 2026 / REV 1 / SHEET 1 OF 1; plugin 0.1.2). `publish_draft.py` sets today's date and adds 1 to the revision whenever the drawing itself changes; `--check` never changes them.

## Decisions that hold

- **Rules (2026-11-17):** stock JMRI SML discovery is the reference; fix the tables, never patch JMRI or the Dispatcher System. Staging stays as the owner approved it (`approved_staging.sha256` guards it). Main and upper objects stay on internal names (`IT:HART:C3`, `IB:C3`, `IH9` heads, `IS:HART:C3` virtual sensors), numbers appended, never shifted. Read the data before building; take before and after pictures (`tools/hosts/sandbox/panel_snapshot.sh`); the sandbox is set up from `tools/hosts/sandbox/README.md`.
- **Side by side (owner, 2026-11-14, ADR-023):** a new generated panel, desk or crew page is written beside the live one and replaces it only on the owner's approval, then in one cut-over.
- **Switch hands (owner, 2026-11-14):** main and upper hands come from the plan geometry (`hands.csv`, `build_hands.py`, `--check` in `check.sh`; 50 switches, 225 left out as a double crossover). Staging Switches 9 and 13 stay as the Layout Editor has them (both drawn right-hand; 9 normal is EH-2, 13 normal is Barn); `switches.csv` `hand` stays L for both, the physical hand.
- **Helix joined (owner, 2026-11-17, release approved in a sandbox PanelPro and CATS):** staging's end bumpers at McKees Rocks and McKeesport are joins; `approved_staging.sha256` was unchanged. The system schematic and station sheets carry no DRAFT mark (revision 10; files keep their `-draft` names so links stay).
- **CATS desks:** main and upper are CTC on the CTC desk, so a route up the helix stops at Mast 136RA (main, via 135-H1) or Mast 136RB (upper, via 135-H2); the ABS desk is all ABS. Every main and upper block has a virtual sensor (`IS:HART:C3:B:<block>`); a physical detector is swapped in through the device map's `jmri_name` column.
- **Switch 225 (owner, 2026-11-17):** the CATS desks show OS Switch 225a to d, one block per corner, each bound to its planned detector, plus a middle block for the crossing cells with no detector (CATS cannot put a block boundary where two blocks meet on one side of a crossing). The middle stays dark; occupancy shows in the four corners and CATS still locks the crossing. Revisit only if the diamond is gapped as its own section when 225 is wired. The 107 Loop is two desk blocks.
- **Layout Editor geometry (2026-11-17):** the geometry once set by constants in `build_layout_le.py` is layer 3 preferences the plugin reads (`le_shift`, `le_crossover_angle`, `le_labels`, `le_band_labels`, `le_longer_straights`, `le_title_clear`, `le_stretch`, `le_window` in `staging.preferences.json` and `main_upper.preferences.json`). `build_layout_le.py` is split into `le_common.py`, `le_names.py`, `le_checks.py` and `le_tables.py`, with the staging approval fingerprint in `approval.py`. Check crossover slants in real PanelPro or with the plugin's JMRI port (`tests/jmri_xover.py`), never from the XML attributes alone.
- **Parked:** NX, the Dispatcher System and the USS CTC (see [`STATUS.md`](../STATUS.md)); unparking means refreshing `parked/tables_parked.xml` per its README.
History of how this was built (spike, cut-over, hand-offs): [`wiki/projects/schematic-maps-handoff.md`](../projects/schematic-maps-handoff.md).
