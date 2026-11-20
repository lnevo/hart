# Hand-off, 2026-11-19: bring the AnyRail plan 5.3c in (Phase 2)

For a fresh agent session. Read `AGENTS.md`, then this page, then
[`pipelines/schematic-panels.md`](../pipelines/schematic-panels.md) and
[ADR-024](../decisions/ADR-024-signals-by-rule.md).

## Why

The owner made `~/Documents/Layout/Lee Nevo Design Version 5.3c.any` the good copy of the layout
(2026-11-19). The schematic inputs still come from the 5.3b export plus overrides. 5.3c draws
what those overrides describe, and it renumbers every T name.

The plan files stay private in `~/Documents/Layout` and are never committed: the custom objects
in them are third-party copyright.

## State when this was written

- **Export ready:** `Lee Nevo Design Version 5.3c.xml` and `.jpg`, saved 16:17 on 2026-11-19,
  a minute after the `.any`. The image is 2664×3840 (about 12.0 px/in); the XML holds 74
  turnouts and 539 track segments.
- **Phase 1 is merged** (hart #692): `tools/anyrail/anyplan.py` reads any maker's `.any`
  (`--report`, `--parts`); its tests run on the owner's plans when they are present.
- **5.3c checks out:** one connected piece, every turnout level, no near misses, a maximum
  grade of 2.25%. The helix runs are Switch 39 to 135A, 947.19 in, and Switch 37 to 135B,
  916.50 in.
- **Already taken from 5.3c** (hart #689): the engine house lengths EH-1 49, EH-2 28 and
  EH-3 28 in (drawn length rounded down, less 2 in; flag `plan` in `block_lengths.csv`), and the
  helix lengths in `staging.plan_overrides.json` `helix_length_in`.
- **Plugin scale fix:** model-railroad-skills PR #74 (branch `agent/claude/plan-scale`,
  schematic-maps 0.1.44) has unmerged commits. Its lengths use the export's fitted scale instead of
  a fixed 12 px/in, a change of 0.1–0.4%. It sits on hart-e5's crossover changes (0.1.42 and
  0.1.43) and waits to be merged with this phase.
- **Mast B93** lacks the intermediateSignal flag. That is correct stock behaviour: its route
  crosses Switch 239 (ADR-024).

## Unblocked

hart #693 (the crossover renumber) merged on 2026-11-19 (e7b6198b) after the owner approved the
panel and desks. Re-key from its numbers: main level 121A/B (T15/T1), 123 (T187), 125A/B
(T184/T14), 127A/B, 129, 131A/B; upper level 207/209 swapped, 211A/B, 213, 231/233 swapped, 239,
241, 243A/B (the relabel map in `main_upper.plan_overrides.json`). The plugin submodule is at
0.1.43 (f471d9af); #74 (0.1.44) is rebased on it. Mast 126L is gone by the reaches-a-signal rule
(`mast_rule.reaches_signal`, ADR-024): 93 masts, 182 SML pairs. If the plugin's main moves again,
merge it into #74 and take the next version number (both `plugin.json` files and the README
"Since 0.1.4x" note).

## Steps

1. Make `jmri/layouts/hart/data/schematic/inputs/parts.json` from
   `python3 tools/anyrail/anyplan.py --parts` on the 5.3c `.any`. Map the old T names to the new
   ones by position.
2. Merge plugin #74 and move the submodule to it.
3. Take the helix from the plan: the levels meet at the −5 cm cut. Remove `helix_length_in` and
   the 24 in McKees Rocks and McKeesport stub estimates from `staging.plan_overrides.json`. The
   owner wants these lengths from AnyRail, not measured.
4. Drop the overrides 5.3c now covers in `staging.plan_overrides.json` and
   `main_upper.plan_overrides.json`.
5. Re-key the edge and node ids in `split_tracks_main_upper.csv`, `staging_signals.csv`,
   `staging_signals_virtual.csv` and `device_map_staging.csv`.
6. Fix the "planned ?" head comments: `tools/schematic/le_tables.py` writes
   `device.get(h, '?')` after `SIGNAL_NOTE`.
7. Run `make panels`, stock Signal Mast Logic discovery in a sandbox, `./tools/check.sh` and
   `make panelpro-test`. The milepost-named masts (A83/A84, B92/B93) will probably rename;
   update ADR-024 and STATUS when they do.
8. Install the candidate `tables.xml` in `~/JMRI_UserFiles`, relaunch the Mac's PanelPro, and ask
   the owner for one approval of the panel and desks. Then refresh the fingerprints with
   `check_approved.py --approve`.
9. Deploy to the Pi and Windows together (`./tools/hosts/sync_hart_package.sh --pi --win`).

## Progress (2026-11-19, Phase 2 branch `agent/claude/anyrail-5-3c-phase2`)

Steps 1 to 7 are done and step 8's candidate is installed on the Mac; the owner's approval, `--approve` and the deploy are left.

- **T names** (5.3b → 5.3c, by position; switch number in brackets): T1→T10 (121B), T6→T6 (129), T14→T20 (125B), T15→T5 (121A), T46→T45 (3), T52→T49 (15), T55→T54 and T98→T95 (35), T56→T55 (39), T58→T57 and T118→T126 (23), T59→T40 (31), T68→T65 (25), T73→T96 (19), T77→T106 (33), T94→T84 (29), T95→T109 (27), T106→T114 (5), T116→T124 (1), T123→T73 (21), T129→T78 (37), T133→T71 (17), T141→T157 (113), T143→T159 (115), T153→T165 (119A), T155→T166 (109), T160→T178 (111), T161→T179 (the crossing), T162→T169 (105), T165→T181 (117), T175→T210 (131A), T183→T196 (103B), T184→T194 (125A), T187→T200 (123), T194→T202 (101B), T196→T204 (107), T199→T215 (127A), T210→T225 (233), T211→T226 (243B), T212→T227 (237), T214→T233 (245A), T217→T234 (231), T220→T239 (235), T224→T241 (245B), T226→T242 (239), T227→T243 (243A), T231→T259 (207), T233→T261 (201), T237→T289 (221A), T239→T266 (229), T241→T268 (241), T251→T281 (131B), T253→T270 (227), T256→T283 (203), T260→T292 (211A), T262→T294 (221B), T268→T299 (217B), T273→T310 (211B), T274→T307 (219), T275→T316 (217A), T285→T311 (127B), T300→T331 (223, moved 6.4 cm and up to 10.8 cm), T329→T359 (215), T340→T366 (209), T343→T375 (205), T345→T374 (213). The junctions the old reader could not name are parts now: 12→T12 (119B), 23→T322 (225). Not in 5.3c: T41, T43. New in 5.3c: T33 and T139 (7), T135 (13), T137 (11), T136 (9). The three-way halves 51 and 50 still match no part.
- **Helix:** `anyplan.py --cut -5 --stubs` gives each graph its share: McKees Rocks 689.0 in on staging and 258.2 in on the main level (947.2 in), McKeesport 644.6 and 271.9 in (916.5 in). `block_lengths.csv` (and the two blocks' lengths in `tables.xml`) carry staging's share, flag `plan`.
- **Re-keyed:** staging and main/upper overrides and preferences, `split_tracks_main_upper.csv` (e64 → e63), the trial names in `device_map_staging.csv`, `staging_signals_virtual.csv`, `le_signal_boundaries.csv` (four anchors renumbered).
- **Kept as approved:** `turnbacks: ["Brick-Plane"]` (plugin 0.1.45) keeps staging's fold; with 5.3c lengths the cheapest drawing turned Main West back.
- **Masts and SML:** 93 masts and the same 182 pairs from stock discovery in a sandbox; no mast renamed (the helix totals equal the old `helix_length_in` sums).

### Draft 2 (owner, 2026-11-20)

- McKees Rocks and McKeesport blocks are the whole helix run, 947.2 and 916.5 in (`block_lengths.csv`, IB23/IB24): their detectors cover all of it. The sheet and the milepost count keep each level's share (`publish_draft.py` no longer copies the helix tracks into `track_lengths_in`), so no mast renames. Another session makes each helix track one JMRI block on helix node 41 after #732 merges.
- OS Switch 235's block contents icon is drawn again, overlaps allowed (`crowded_block_contents`, schematic-maps 0.1.45), for the owner's review.
- The Main West turnback the owner asked for is not in this draft: with Main West folded, W-1 and W-2 are drawn east of Switch 3, so the mast rule renames 4RA/4RB to 4LA/4LB, which are the names of the hand-kept virtual masts at those bumpers, and the build stops. It needs the owner's call (see #732).

## Also open

The Windows deploy of hart #689 has not run, because Windows (minipc-e5h6x.local, 10.0.0.28:2222)
was unreachable. The Pi has that commit. The deploy in step 9 catches Windows up; if Windows comes
back sooner, run `--win` alone from the main checkout.
