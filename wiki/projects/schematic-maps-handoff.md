# Schematic maps: hand-off after the proof

- **Written:** 2026-11-13, at the end of the stage 0 session.
- **Read with:** [`schematic-maps.md`](schematic-maps.md) (plan, references, as-built notes) and the spike's `README.md`.
- **Where the work is:** branch `agent/claude/schematic-spike`, draft PR #423, folder `tools/schematic/spike/`. The owner approved the look of `system_sample.svg` there.

## The one thing to get right

The spike mixes three kinds of input in two options files (`staging_opts.json`, `main_asbuilt_opts.json`). They must be separated, because only the first two are the product:

1. **Plan overrides.** Facts about the railroad that AnyRail's plan does not hold or holds wrongly. They override the plan and every output uses them (schematic, CATS, station pages, Layout Editor).
2. **Generation.** Rules that turn plan plus overrides into a clean, stretched-out main line and track plan with no hand input.
3. **Preferences.** The owner's choices about how one sheet looks. Optional, applied last, never needed for a correct drawing.

**Test of the separation:** with layer 3 switched off, layers 1 and 2 alone must draw all three levels with no crossings or overlaps, the main line straight through every switch, and yard ladders stepping diagonally with their tracks level. Today that only happens with hints, so several hints below have to become rules.

## Layer 1: plan overrides (feed these over the AnyRail plan)

Source of track: AnyRail's JMRI export of plan 5.3b, read by the plugin's `plan` command into the track graphs in `jmri/layouts/hart/data/schematic/inputs/` (since 2026-11-14; recipe in `docs/ops/schematic-system-draft.md`). The `.any` file and its XML export stay in `~/Documents/Layout/`, outside the repo. Heights come from the `.any` file, matched to the export by position (export scale is 120 px per inch of plan).

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

## Layer 2: generation rules

Already rules in the spike:

- One band per level; a run that joins two levels is cut and shown as lettered connectors. Level by height (below 5 cm: main; above: upper).
- Each switch faces left or right; runs that must double back are folded, choosing the folds that are U-turns on the layout, and keeping the choice that draws with the fewest faults.
- Tracks are ordered top to bottom from each switch's hand; a loop's two tracks are stacked by which way the loop bends.
- A double crossover's two tracks sit on neighbouring rows.
- Spare length along a band is shared in proportion to real track length; switches joined by short links move as blocks; track ends and folds travel with their switch; a long track always gets a level run; a connector gets one short cell.
- The drawing is checked for lines that cross or lie on top of each other, and the solver adds clearance until none do.

Must become rules (today they are hints):

| Hint used today | Rule to write |
|-----------------|---------------|
| `level_leg` on 18 switches of the main and upper bands and 4 of staging | The main route runs level through every switch on it |
| `level_leg` on Switches 13, 15, 17, 19 | In a ladder, the yard track runs level and the short link to the next switch slopes; a lead runs straight into the first ladder switch |
| `keep_close`, some `shorten` and `min_cells` | Rows should only be kept apart for tracks that really overlap along the band (the spike uses its working order, which is stricter) |
| Trial of T300's hand | Hands of added or moved switches come from layer 1, never from trial |

Known gaps: labels are not checked for collisions; the three bare export numbers (12, 50, 51) and the upper double crossover's 23 are closed by the owner's numbering (2026-11-14), and a staging crossover already prints one number; no page folding; no capacity placeholder.

## Layer 3: the owner's preferences for this sheet

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

## Work to do, in parallel

The three layers above are the contract between the streams. Keep the spike's edit operations and hint names as the first file format, so every stream can start at once.

| Stream | Work | Who | Done when |
|--------|------|-----|-----------|
| A1 | Split the two options files into `plan_overrides` (layer 1) and `preferences` (layer 3) files per level under `jmri/layouts/hart/data/schematic/`; make the spike read them | Agent (Sonnet) | The spike draws the same sheet from the split files |
| A2 | Draw the **baseline**: layers 1 and 2 only. Record every fault and every place the main is not straight; that list is B's work list | Agent (Sonnet) | Baseline SVG and fault list committed beside the sample |
| A3 | Publish the approved sheet as PDF and SVG in `docs/ops/`, marked draft; run `evolution.py` after each committed drawing | Agent (Sonnet) | Done. Since 2026-11-14 the sheet is drawn by the plugin: `tools/schematic/publish_draft.py` (draw, DRAFT mark, PDF; `--check`), then `tools/schematic/evolution.py` after the commit |
| B1 | Specification: file formats for the three layers, each rule, and golden drawings (baseline and approved sheet) | Main session | Reviewed by the owner |
| B2 | Tested modules in `model-railroad-skills`, with the hint-to-rule changes above and a made-up public example. Only track may be published from the owner's plan, never its custom objects or buildings | Agents (Sonnet); main session reviews the rules | Baseline is clean with no hints; the approved sheet reproduces with layer 3 |
| B3 | Skill text and style reference from `tools/schematic/spike/research/` | Agent (Sonnet) | Done 2026-11-14 (model-railroad-skills PR #20, 0.1.1): `references/style.md` with each rule's sources and whether the tool draws it, `references/cats-grid.md` for C1; marketplace install tested on the example. The style rules not yet drawn (capacity, mileposts, interlocking limits, title block date and revision, page folding, detail sheets and others) are listed in `style.md` |
| C1 | CATS panel for the main and upper levels from the same grid (CATS cell rules are in `research/survey_2.md`); settle east and west by following the main; carry facing and trailing per switch | Main session designs; agent builds | Owner approves the panel in CATS Designer |
| C2 | Station pages and deck track maps | Agents | After B2 |
| D1 | Signals: masts from the Layout Editor panel as layer 1 (`signal_reader.py`), drawn in the NYAMR Physical Characteristics Book style (stem, arm, one circle per head, right-hand side for the direction); labels placed by R12. Done on staging (PR #431, merged into the spike branch 2026-11-13): owner approved the look; label check 0 faults with East Lead 4 cells and South Yard 4 (owner's length change). Same placements to seed CATS signal icons in C1. Still open: labels claiming grid room in the layout (R12), so tight spots need no length preference | Main session | Done for staging; main levels when they have masts |
| C2a | One generated station page (South Yard) from the same grid, compared with the hand-drawn `www/crew/maps/south-yard/` page: what is missing (capacity, spots, west/east arrows) | Agent | Side-by-side for the owner |
| C3 | Layout Editor import of the main levels; switch facts for the new levels | Main session | After the owner's names |

## Other open items

- **Side by side (owner, 2026-11-14, ADR-023):** C1, C2a and the Layout Editor regeneration each write new files beside the live desk, panel or crew page, and swap in only on the owner's approval.
- **To do: main and upper switch hands (owner, 2026-11-14, saved for later).** The owner wants the main and upper switch hands taken from the schematic drawing for now, and kept off the sheet. Read as each switch node's `hand` from `sheet.build` (diverging side seen from the points). On staging this agrees with the owner's `switches.csv` hands on 21 of 23. Drawn hands on REV 5:
  - Main: R 101A, 101B, 105, 107, 115, 119A, 119B, 123, 127, 133, 135A; L 103A, 103B, 109, 111, 113, 117, 121, 125, 129A, 131.
  - Upper: R 135B, 213A, 213B, 221A, 221B, 223 (T300, owner-confirmed R), 227, 231, 233, 235, 239; L 129B, 201, 203, 205, 207, 209, 211, 215, 217A, 217B, 219, 229, 237, 241A, 241B, 243, 245A, 245B. 225 is the double crossover (no hand).
  - (1) Settled (owner, 2026-11-14): 101A/B, 103A/B, 105, 107, 109, 111 are `flip`ped on the sheet; their hands are recorded from the plan geometry, not as drawn. (2) Settled (owner, 2026-11-14): staging 9 and 13 stay as the Layout Editor has them (both drawn right-hand; 9 normal = EH-2, its diverging leg; 13 normal = Barn). The schematic, CATS and the Layout Editor follow that; `switch_legs.csv` agrees. `switches.csv` `hand` stays L for both: it is the physical hand (9 and 13 are left-hand turnouts; 13 is wired with its diverging route as normal), read by the track plan article. A trial with 9 and 13 left-hand on the sheet put EH-2 between EH-1 and EH-3 and was rejected.
  - Home until the import: the generated `jmri/layouts/hart/data/schematic/hands.csv` (switch, hand, source "plan geometry (provisional)"), written by `tools/schematic/build_hands.py` with a `--check` in `check.sh`. `switches.csv` can't take main and upper rows yet: `check_layout_facts.py` needs a Layout Editor turnout, CATS binding and USS lever per row.
  - Done (2026-11-14): `jmri/layouts/hart/data/schematic/hands.csv` exists, built by `tools/schematic/build_hands.py` (with `--check` in `check.sh`) from the plan geometry, source "plan geometry (provisional)"; 50 switches, 225 left out (double crossover). The eight flipped switches are the opposite of the drawn hands above.
- **B2, model-railroad-skills PR #18 (`plugins/schematic-maps`), merged 2026-11-13.** Reproduces the approved sheet byte for byte from layers 1 to 3 with no hints. R5 and R6 are weighted (`rule_weight` 2) at the owner's request (2026-11-13), so the approved loop entries and peninsula ladder come from the rules; the only `level_leg` pins left are T210 and T212, the owner's free choices. `ladder_link_max_cm` is 40 (60 would turn T143 and T226 into ladders). Layer files on main carry the keys it reads (`source`, `helix_side`, `helix_to`, `level_title`, mast name pattern). Since its review fixes, a mast on a fold stays on its toward end's half, so the planned Princess masts 2035 and 2036 draw near the K-1/K-2 turnback (they stand mid-run on the panel); the published draft shows this since 2026-11-14. The spike (PR #423) is closed; the plugin is the tool. R12 grid room merged the same day (model-railroad-skills PR #19): a label with no free position lengthens its own track and that input is laid out again, so the rules-only sheet has 0 label faults and the East Lead and South Yard length preferences are now the owner's look, not a fix.
- **Rename East Ext / West Ext, PR #425.** Merged and deployed 2026-11-13; the run's logs in `~/speedmatch-logs/2026-11-13/` are converted (originals in `2026-11-13-before-rename/`).
- **Mast 32L renamed 16R, PR #441.** Hidden S-R east mast; merged and deployed 2026-11-13. `staging.signals.json` regenerated.
- **Spike, PR #423.** Draft; the layer split and baseline (#430) and signals and labels (#431) are merged into its branch after review. Keep as the reference; do not merge as the product. Review findings left for B2 (tested modules): label text measured with a macOS font file (needs a fallback), helix boxes and station brackets drawn after the label placer, the placer's speed, `schem.py`'s single-band entry no longer reads the layered files, run matching by end switches can tie on two stubs off one switch.
- **Hardening (2026-11-14):** the font fallback and drawing the helix boxes and station brackets before the labels were already done. Speed (about 30 s a draw, 28,000 row solves) was dropped by the owner, since it can't be cut without changing the search. Run hints may now list their tracks, and the run stops on a hint that reaches no track, or reaches two without saying which (plugin 0.1.4). Helix level heights: not drawn on the schematic (owner, 2026-11-14). The helix plans in `docs/benchwork/helix/` are authoritative for heights (BUILD_STATUS first): plywood tops at staging −15.000 in, main 0.000 in, upper (D01) +4.250 in, relative to the main level.
- **Plugin 0.1.7 (2026-11-14):** fixes the review findings on the band-directions work (model-railroad-skills PR #25, from another session) in PR #27. A turned band now gets its own reversed legend, `band_gap` measures a turned band correctly, `track_directions` asks for the leg on parallel tracks, and a band setting naming no band stops the run. Still open from those reviews: `edits` entries (`on`, `onto`, `side`) still silently take the longer of two parallel tracks; a declared track drawn only on a slope gets no arrow; a band can get two arrows when it is split by a stub under a cell; the run-merging code is duplicated between `track_arrows` and `direction_arrows`.
- **REV 5 (2026-11-14):** facing letters off on both preferences files, by the owner, who is not yet confident in the switch assignments (ADR-022 amendment). The signals staleness check shipped in PR #477.
- **REV 6 and station sheets (2026-11-14, plugin 0.1.8, hart PR #482):** model-railroad-skills PRs #28 (0.1.7 review leftovers), #29 (page folding, opt-in; HART does not fold, it is height-bound at Letter), #30 (`schematic detail` station sheets, cut from the solved overall grid), #31 (interlocking limits, detail sheets only by owner choice), #32 (mileposts), #33 (release). Layer 1: `control_points` from `control_points.csv`, now with short codes (BK, PL, BN, EH, SY, EE, PR: made up at the owner's request, letters not yet reviewed); milepost facts made up by the owner's request (Switch 1 = MP 0.0, HO 1:87.1, helix 690 in estimated from the helix grades). Layer 3: `detail_sheets` (Brick, Plane, West Yard, Barn, South Yard 7 to 21, East End, Princess; may overlap `stations`), `mileposts: true` on every sheet. `publish_draft.py` now also writes `docs/ops/stations/*.svg` and `--check` covers them; detail sheets are drawn from both inputs so the coil helix and mileposts reach them.
- **REV 7 (2026-11-14, plugin 0.1.11, model-railroad-skills PR #38):** mast 34R moved by the owner from the bottom bend of Main East to the slope just below Switch 33, beside 32R. A rule, not a nudge: a mast at a switch whose track leaves it on a slope over 2.5 cells stands on that slope. Only 34R moves (system sheet, East End, South Yard and East End).
- **C3 Layout Editor panel, schematic look (2026-11-14):** the owner found the physical C3 panel too physical and asked for one that looks like the schematic (rounded bends, like the NER Coupler 303 track diagram). `tools/schematic/build_layout_le.py` writes the trial tables copy `jmri/layouts/hart/output/trial/tables_layout.xml` (gitignored, generated on demand; `--check`) with a third Layout Editor panel "Layout (generated)" drawn by the plugin's `schematic le` from the solved bands: all three levels stacked as on the sheet, straight rows, corners rounded by circle arcs, half-circle turnbacks, helix and connector circles, switch numbers, track and station names, hidden track segments joining the helix tracks and connectors A and B. Staging binds to the live names (turnouts and blocks of "HART Railroad", via `switches.csv`, the live panel's tracks and `switch_legs.csv` closed legs; 7, 23 and 35 are single crossovers as live), so it can replace the live panel at the one cut-over. Main and upper keep the C3 placeholders (51 turnouts `Switch 101A`.. internal `IT:HART:C3:*`, 121 blocks `Track e<id>` and `OS Switch <n>`). The physical builder `tools/anyrail/build_main_upper_le.py` is retired. No masts, sensors or icons yet. Owner opens it in PanelPro; cut-over with the rest.
- **C1 CATS panel (2026-11-14, plugin 0.1.12, model-railroad-skills PR #39):** `tools/schematic/build_cats_panel.py` writes `cats/panels/generated/HART_Main_Upper.xml` from the main and upper bands (`schematic cats`): track, switch points (leg B normal), OS and track blocks, labels, joins at links A and B. No JMRI bindings or signals yet (the levels have no JMRI objects). Validated by `validate_cats_panel.py` in check.sh; not deployed (sync installs only HART_CTC and HART_ABS). Owner opens it in CATS Designer; cut-over with the rest (owner, 2026-11-14: everything side by side, one cut-over).
- **Next session:** swap the hand-drawn `www/crew/maps/` images (old switch numbers) for the station sheets, owner approves before deploy; then C1 (CATS panel) and C3 (Layout Editor import), last by the owner's order.
- **Owner's names** for the main and upper levels (stations, tracks, level names): pending by the owner's choice. Switch numbers are set (2026-11-14, layer 1 above).
- **Princess masts 2035 and 2036** drawn near the K-1/K-2 turnback rather than mid-run: accepted by the owner (2026-11-14); they are placeholders and the fold rule stands.
- **Evolution record.** `~/Documents/Layout/schematic-evolution/` holds every committed drawing and `evolution.gif`; refresh it after each drawing commit with `tools/schematic/evolution.py` (spike samples, then every commit of `docs/ops/schematic-system-draft.svg`).
