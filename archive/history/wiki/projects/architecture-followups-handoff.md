# Architecture follow-ups: hand-off (2026-11-14)

These are the items left from the 2026-11-14 re-review (senior architect, site reviewer and repo auditor) that had not been put to the owner. The owner decided each one below. The rest of that review is done or parked by the owner's earlier decisions: the import ADR waits until the upper level is drawn; Dispatcher, NX and the USS CTC for the new levels wait; the portal build stays out of CI.

## 1. One place for each track and mast name — do now

**Owner (2026-11-14):** do it now, so the repo is clean before the main and upper levels add their names.

**Problem.** Renaming one mast (16R, PR #441) touched 13 files. Most were generated (baselines, `staging.signals.json`, `www/data/*.json`) and are caught by their `--check`. The rest are names typed by hand into code and docs, for example `apply_yard_throat_blocks.py` and `jmri/layouts/hart/parked/DISPATCHER_LAYOUT_HOOPS.md`. With two more levels coming, each hand-typed copy is a rename that can be missed.

**Goal.**
- A track, block or mast name is typed in one data file: `public_name_map.csv`, `switch_legs.csv`, `mast_cells.csv` or `control_points.csv` (ADR-021).
- Every other copy is either generated from that data, with a `--check` in `tools/check.sh`, or looked up from it at run time.
- `tables.xml` stays JMRI's file. PanelPro owns it and the rename path through `public_name_map.csv` stays as it is.

**Work.**
1. List every hand-kept copy of a track, block or mast name in code, data, site pages and docs. Leave out generated files that already have a check, `archive/`, and dated history.
2. Move each copy onto the data files, or into generated output with a check. Generated outputs must stay byte-identical (CATS panels, USS track plan, site JSON).
3. Add a rename test. In a temporary copy, rename one mast and one track in the data files, regenerate, and confirm that every check passes and no hand-kept file still holds the old name.
4. Add a rename checklist to `wiki/pipelines/switch-facts.md`.
5. Prose in the wiki and docs may keep names. A record of what happened is not a copy to maintain.

**Inventory (2026-11-14, step 1 only).** The full list is in the draft PR on branch `agent/claude/names-one-place`. Outside the generated and checked files there are:
- 50 CPython scripts: 38 to move, 12 that hold names only in comments or dated records;
- 5 Jython scripts, left alone;
- 16 data files besides the six sources: 9 to move, 7 owned by JMRI, the Designer or Operations Pro;
- 38 tests;
- 10 site pages and 29 docs, mostly prose.

Thirteen of the scripts are over 500 lines and need tests before they change. Several also need a new home for a drawing fact: CATS cells, desk anchors, USS labels, NX numbers, stations, throat splits. The estimate is 2 to 3 weeks, not a day, so the work stopped at the inventory.

The PR proposes these phases:
- **Phase 0, half a day:** a stale-name check in `check.sh`.
- **Phase 1:** item 2 and the small lookups.
- **Phase 2:** the desk, USS and Layout Editor generators.
- **Phase 3:** wiring, mimic and publications.
- **Retire instead:** a few one-shot scripts. `sim_hart_train_mqtt.py` already uses a name retired before 16R.

**Owner (2026-11-14):** do Phase 0, Phase 1 and the deletions now. Phases 2 and 3 are deferred to the import of the main and upper levels.

**Done (PR #483):**
- **Phase 0:** `tools/audit/check_name_copies.py` is in `check.sh`. It fails on any Track, OS or Mast name in a hand-kept code, data or site file that is not current: the map's identity rows, plus the block user names in `tables.xml`, which is how the hidden throat blocks count. Its tests rename a mast and a track in temporary copies and expect every stale copy to fail. The rename checklist is in `wiki/pipelines/switch-facts.md`.
- **Phase 1:** the speed-match routes are a running order of block names, with the sensors written from `tables.xml` into `speedmatch/routes.json` by `build_routes.py` (`--check` in `check.sh`); `analyze.py` reads that file with the standard library, so the Pi live view needs no hartlib. `audit_panel_contracts.py`, `check_hart_phase02.py` and `infer_block_lengths.py` look up what they typed, and `validate_cats_panel.py` lost its unused name sets.
- **Deleted:** `sim_hart_train_mqtt.py`, `annotate_mqtt_sensors_and_dispatcher.py`, `patch_ctc_locking.py`, `render_ctc_panel.py` and `apply_sml_cats_pairs.py`. The CATS pairs and the script that compared them were removed on 2026-11-16.

## 2. Speed-match test routes from the data — do now

**Owner (2026-11-14):** yes. `jmri/layouts/hart/scripts/speedmatch/analyze.py` types its test routes as (block sensor, track) pairs. Tests check them against `switch_legs.csv`, but they are still a third place that holds track names. Build the routes from the data files, or keep only the running order (the route) and look the names up. This is part of item 1 and is done in the same work.

## 3. Tests for the AnyRail reader without the plan files

**Owner's question (2026-11-14):** what tests can we write without AnyRail test files the owner doesn't have?

`tools/anyrail/prototype/` reads `.any` files by matching byte patterns:
- a length-prefixed part name and track system;
- an endpoint record, `X\0`, then two u32 ids, four doubles (x, y, z, angle) and a length-prefixed system name;
- length-prefixed Bézier point lists.

The prototype is still used by `infer_block_lengths.py`; `tools/anyrail/anyplan.py` (with synthetic-fixture tests in `tools/anyrail/tests/test_anyplan.py`) now writes `parts.json`, so this item is done. Options, none of which needs a real plan file:
- **Synthetic byte fixtures.** A test helper writes small byte strings in exactly the record shapes the reader looks for: one turnout with three endpoints, a flex track with a Bézier list, a record with a non-finite or out-of-range coordinate, and a record whose system name differs from its part's, which is the misread found in plan 5.3b. Tests check the decoded names, endpoints, the grouping of endpoints into parts (the offset limits), the filters, and the Bézier length against a straight line and a quarter circle of known length. These prove the reader matches its own idea of the format, not that AnyRail writes it that way.
- **Checks on the committed outputs.** `parts.json` already has invariants in `tools/audit/tests/test_publish_draft.py`: only names and x, y, z; no point at the origin; only part 0 is a short turnout. Both graphs regenerate the same from it.
- **A local-only test against the owner's plan.** If `~/Documents/Layout/Lee Nevo Design Version 5.3b.any` is present, run the reader and compare with the committed `parts.json` after the same strip. It is skipped everywhere else, CI included. This is the only test that proves the format against a real file.

**Owner (2026-11-14):** deferred. The three options stay as written for when it is picked up.

## 4. USS lever numbering

The USS track plan assumes odd plate numbers on one row. This belongs to the USS board for the new levels, one board per level, which the owner has parked. It is listed here so it is on that list. There is no work now.

## 5. Website items — do now

**Owner (2026-11-14):** ok.
- `www/ai/speed-runs.html`: the byline says "Behind the Scenes" on a page in the AI section; make it match the section.
- The browser title ("Speed Matching 2121 and 2738") and the heading ("Speed matching CSX 2121 and 2738") should use the same words.
- Check `www/build/track-plan.html` at phone width (`python3 tools/ops/screenshot.py`) and fix what breaks.

The site is deployed with `./www/scripts/deploy_hartrailroad.sh` after the merge. Check the Build counts.

## Status

| Item | State |
|------|-------|
| 1 and 2 | Phase 0, Phase 1 and the deletions done (PR #483). Phases 2 and 3 deferred to the level import (owner, 2026-11-14) |
| 3 | Deferred (owner) |
| 4 | Parked with the USS work |
| 5 | Done (62bf8841, 2026-11-14) |
